import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from pymongo.errors import DuplicateKeyError

from app.core.config import settings
from app.core.constants import PRIVACY_VERSION, TERMS_VERSION, KycStatus
from app.core.exceptions import (
    AppValidationError,
    AuthError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    TOKENS_VALID_FROM,
    password_change_cutoff,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    token_storage_key,
    token_predates_password_change,
    verify_password,
)
from app.db.collections import (
    get_email_verification_col,
    get_password_reset_col,
    get_refresh_blocklist_col,
)
from app.repositories.user_repo import UserRepository
from app.schemas.auth import RegisterRequest
from app.services import auth_sessions
from app.utils.email import send_password_reset_email, send_verification_email
from app.utils.validators import PASSWORD_POLICY, validate_password_strength

user_repo = UserRepository()
logger = logging.getLogger(__name__)

_BLOCKLIST_FALLBACK_TTL = timedelta(days=7)
_RESET_TOKEN_PREFIX = "sha256:"
_VERIFY_TTL = timedelta(hours=24)
EMAIL_NOT_VERIFIED = "email_not_verified"


def email_verification_active() -> bool:
    """Whether new accounts must confirm their email. Needs SMTP: without it
    the link can never arrive and the account could never sign in."""
    return settings.email_verification_required and bool(settings.smtp_user)


def initial_kyc_fields() -> dict:
    """KYC state for a lawyer account at creation.

    With LAWYER_AUTO_APPROVE (demo policy) the account is approved straight
    away and never enters the admin queue; nothing about the Bar license has
    been checked, so the UI says "registered", never "verified". The directory
    still hides a profile until it has a bar number and a practice area."""
    if settings.lawyer_auto_approve:
        # The marker lets the booking and hire gates tell an account approved
        # before onboarding from one an admin approved after reviewing it.
        return {"kyc_verified": True, "kyc_status": KycStatus.APPROVED.value,
                "kyc_auto_approved": True}
    return {"kyc_verified": False, "kyc_status": KycStatus.PENDING.value}


def _reset_token_key(token: str) -> str:
    """Return the one-way lookup key stored for a reset bearer secret."""
    return _RESET_TOKEN_PREFIX + hashlib.sha256(token.encode()).hexdigest()


def _revocation_record(token: str, payload: dict) -> dict:
    """Build a blocklist row which expires when its JWT expires.

    New rows intentionally omit ``created_at``. Deployed databases still have
    the original seven-day TTL on that field; writing an access-token row with
    a back-dated value would make that legacy index delete the revocation
    immediately. The old index continues cleaning old rows, while the precise
    ``expires_at`` index owns all new rows.
    """
    now = datetime.now(timezone.utc)
    try:
        expires_at = datetime.fromtimestamp(float(payload["exp"]), timezone.utc)
    except (KeyError, TypeError, ValueError, OSError):
        expires_at = now + _BLOCKLIST_FALLBACK_TTL
    return {
        "token": token_storage_key(token),
        "token_type": payload.get("type"),
        "expires_at": expires_at,
    }


async def _revoke_idempotently(token: str | None, expected_type: str) -> None:
    """Revoke a valid JWT; repeated and concurrent revocations succeed."""
    if not token:
        return
    payload = decode_token(token)
    if not payload or payload.get("type") != expected_type:
        return
    try:
        await get_refresh_blocklist_col().update_one(
            {"token": token_storage_key(token)},
            {"$setOnInsert": _revocation_record(token, payload)},
            upsert=True,
        )
    except DuplicateKeyError:
        # Another worker won the same unique-token upsert.
        return


def new_lawyer_profile() -> dict:
    """The lawyer sub-document an account needs before any lawyer-profile
    write can land (they all `$set lawyer_profile.<field>`). Used at sign-up
    and when an admin moves an existing account onto the lawyer role."""
    return {
        "bar_number": None,
        "specializations": [],
        **initial_kyc_fields(),
        "kyc_rejection_reason": None,
        "rating": 0.0,
        "total_reviews": 0,
        "availability": True,
        "bio": None,
    }


async def register(data: RegisterRequest) -> dict:
    # Public registration is client/lawyer only — admins are provisioned by an existing admin
    if data.role.value not in ("client", "lawyer"):
        raise AppValidationError("Invalid role")

    if not validate_password_strength(data.password):
        raise AppValidationError(PASSWORD_POLICY)
    if not data.accepted_terms:
        raise AppValidationError("Please accept the Terms and Privacy Policy.")

    existing = await user_repo.find_by_email(data.email)
    if existing:
        raise ConflictError("Email already registered")

    user_id = secrets.token_urlsafe(16)
    now = datetime.now(timezone.utc)
    must_verify = email_verification_active()
    if settings.email_verification_required and not must_verify:
        logger.warning("Email verification skipped for a new account: SMTP is not configured")
    doc = {
        "_id": user_id,
        "role": data.role.value,
        # False = must confirm before signing in (login checks `is False`, so
        # accounts from before this field existed keep working).
        "email_verified": not must_verify,
        "email_verified_at": None if must_verify else now,
        # What the sign-up checkbox agreed to, and when.
        "terms_consent": {"terms_version": TERMS_VERSION,
                          "privacy_version": PRIVACY_VERSION, "accepted_at": now},
        "email": data.email.lower(),
        "password_hash": hash_password(data.password),
        "full_name": data.full_name,
        "phone": data.phone,
        "province": None,
        "avatar_url": None,
        "is_active": True,
        "lawyer_profile": new_lawyer_profile() if data.role.value == "lawyer" else None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    # cnic_encrypted intentionally omitted when not provided — sparse unique index
    # only skips documents where the field is absent (not where it's null)
    try:
        await user_repo.insert(doc)
    except DuplicateKeyError as e:
        detail = str(e)
        if "email" in detail:
            raise ConflictError("Email already registered")
        raise ConflictError("Account already exists")
    return doc


async def login(email: str, password: str, *, user_agent: str = "") -> dict:
    user = await user_repo.find_by_email(email)

    # Same work whatever the address turns out to be. Guarding this behind
    # `if user` skipped bcrypt entirely for an unknown address, so the response
    # came back in microseconds instead of ~250ms and the timing said what the
    # message no longer does. Always exactly one checkpw, against a real hash.
    password_ok = verify_password(
        password, user["password_hash"] if user else DUMMY_PASSWORD_HASH
    )

    # One message for all three failures: unknown address, wrong password, and
    # deactivated account. A distinct "Account deactivated" confirmed BOTH that
    # the address is registered and that the password supplied was correct —
    # a stronger disclosure than plain enumeration, handed out before any
    # authenticated session exists. forgot_password is already careful about
    # this; login was not.
    #
    # A deactivated user is told nothing here on purpose. They cannot act on it
    # anyway, and support can say so through a channel that knows who it is
    # talking to.
    if not user or not password_ok or not user.get("is_active"):
        raise AuthError("Invalid email or password")

    # Only after the password is proven: saying "confirm your email" to anyone
    # who typed an address would reveal that the account exists.
    if user.get("email_verified") is False:
        raise ForbiddenError({
            "code": EMAIL_NOT_VERIFIED,
            "message": "Please confirm your email first. We sent a link to your inbox.",
        })

    session_id = auth_sessions.new_session_id()
    refresh_token_id = auth_sessions.new_token_id()
    refresh_token = create_refresh_token(
        user["_id"], session_id, refresh_token_id)
    refresh_payload = decode_token(refresh_token) or {}
    expires_at = datetime.fromtimestamp(
        float(refresh_payload["exp"]), timezone.utc)
    await auth_sessions.create(
        session_id=session_id,
        user_id=user["_id"],
        refresh_token_id=refresh_token_id,
        expires_at=expires_at,
        user_agent=user_agent,
    )
    access_token = create_access_token(user["_id"], user["role"], session_id)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "role": user["role"],
        "user_id": user["_id"],
    }


async def refresh(refresh_token: str, access_token: str | None = None) -> dict:
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise AuthError("Invalid refresh token")

    user = await user_repo.find_by_id(payload["sub"])
    if not user or not user.get("is_active"):
        raise AuthError("User not found")

    # Issued before the last password change — the reset that ended this session
    # may well have been performed because this token was stolen.
    if token_predates_password_change(payload, user):
        raise AuthError("Session ended by a password change — please sign in again")

    session_id = payload.get("sid")
    token_id = payload.get("jti")
    if session_id and token_id:
        next_token_id = auth_sessions.new_token_id()
        next_refresh = create_refresh_token(
            user["_id"], session_id, next_token_id)
        next_payload = decode_token(next_refresh) or {}
        await auth_sessions.rotate(
            session_id=session_id,
            user_id=user["_id"],
            presented_token_id=token_id,
            next_token_id=next_token_id,
            next_expires_at=datetime.fromtimestamp(
                float(next_payload["exp"]), timezone.utc),
        )
    else:
        # Rollout compatibility: cookies minted before token families existed
        # have no sid. They retain the old atomic one-use rotation until expiry.
        try:
            await get_refresh_blocklist_col().insert_one(
                _revocation_record(refresh_token, payload)
            )
        except DuplicateKeyError:
            raise AuthError("Refresh token revoked")
        next_refresh = create_refresh_token(user["_id"])

    # Retire the access token being replaced as part of this session's rotation.
    await _revoke_idempotently(access_token, "access")
    return {
        "access_token": create_access_token(
            user["_id"], user["role"], session_id),
        "refresh_token": next_refresh,
    }


async def logout(refresh_token: str | None, access_token: str | None = None) -> None:
    # Only blocklist valid JWTs — prevents collection flooding with garbage strings
    for token in (refresh_token, access_token):
        payload = decode_token(token) if token else None
        if payload and payload.get("sid") and payload.get("sub"):
            await auth_sessions.revoke(
                payload["sid"], payload["sub"], reason="logout")
    await _revoke_idempotently(refresh_token, "refresh")
    await _revoke_idempotently(access_token, "access")


async def logout_all(user_id: str) -> int:
    """End every token family and invalidate rollout-era sid-less tokens."""
    count = await auth_sessions.revoke_all(user_id)
    await user_repo.update_one(
        {"_id": user_id, "is_active": True},
        {"$set": {
            TOKENS_VALID_FROM: password_change_cutoff(),
            "updated_at": datetime.now(timezone.utc),
        }},
    )
    return count


async def send_email_verification(email: str) -> None:
    """Email a fresh confirmation link to an unconfirmed account. Silent for an
    unknown or already-confirmed address, like forgot_password."""
    user = await user_repo.find_by_email(email)
    if not user or user.get("email_verified") is not False or not email_verification_active():
        return
    token = secrets.token_urlsafe(32)
    key = _reset_token_key(token)
    col = get_email_verification_col()
    # One link per account: a resend replaces the previous one.
    await col.replace_one(
        {"user_id": user["_id"]},
        {"user_id": user["_id"], "email": user["email"], "token": key,
         "created_at": datetime.now(timezone.utc)},
        upsert=True,
    )
    try:
        if not await send_verification_email(user["email"], token):
            raise RuntimeError("email_not_configured")
    except Exception as exc:
        await col.delete_one({"token": key})
        logger.warning("Verification email was not delivered; error_type=%s", type(exc).__name__)


async def verify_email(token: str) -> None:
    """Confirm the address a link was sent to. Single use."""
    record = await get_email_verification_col().find_one_and_delete(
        {"token": _reset_token_key(token)})
    created_at = (record or {}).get("created_at")
    if created_at is not None and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    if not record or (created_at and datetime.now(timezone.utc) - created_at > _VERIFY_TTL):
        raise AppValidationError("This confirmation link is invalid or has expired.")
    now = datetime.now(timezone.utc)
    # Matched on the email too: a link must not confirm an address the
    # account no longer has.
    await user_repo.update_one(
        {"_id": record["user_id"], "email": record["email"]},
        {"$set": {"email_verified": True, "email_verified_at": now, "updated_at": now}},
    )


async def forgot_password(email: str) -> None:
    user = await user_repo.find_by_email(email)
    if not user:
        return  # silent — don't leak whether email exists

    reset_token = secrets.token_urlsafe(32)
    token_key = _reset_token_key(reset_token)
    try:
        await get_password_reset_col().insert_one(
            {
                "token": token_key,
                "email": email.lower(),
                "active_slot": True,
                "created_at": datetime.now(timezone.utc),
            }
        )
    except DuplicateKeyError:
        # One active link per account. A request moments after the last one (a
        # double click) keeps that link: its email is still on the way, and
        # replacing it would silently kill the message the user is about to
        # open. Later than that, the person is asking BECAUSE the first email
        # never arrived (2026-10-20: they used to get nothing for an hour while
        # the page said "sent"), so the unused link is swapped for a new one.
        previous = await _replace_reset_link(email.lower(), token_key)
        if previous is None:
            return
        await _send_reset_link(email, reset_token, token_key, previous)
        return
    await _send_reset_link(email, reset_token, token_key, None)


# A second request inside this window keeps the link already sent.
_RESET_RESEND_AFTER = timedelta(minutes=2)


async def _replace_reset_link(email: str, token_key: str) -> dict | None:
    """Swap the account's unused link for `token_key`. Returns the row as it
    was (so a failed send can put it back), or None when it is too recent,
    already being used, or gone."""
    now = datetime.now(timezone.utc)
    return await get_password_reset_col().find_one_and_update(
        {"email": email, "active_slot": True,
         "claimed_at": {"$exists": False},
         "created_at": {"$lte": now - _RESET_RESEND_AFTER}},
        {"$set": {"token": token_key, "created_at": now}},
    )


async def _send_reset_link(email: str, reset_token: str, token_key: str,
                           previous: dict | None) -> None:
    try:
        delivered = await send_password_reset_email(email, reset_token)
        if not delivered:
            raise RuntimeError("email_not_configured")
    except Exception as exc:
        # Existing and unknown accounts keep the same public response even
        # during an SMTP outage. Undo only what this request wrote: a new row
        # is removed; a replaced link gets its old token back, so the email the
        # user already has keeps working.
        col = get_password_reset_col()
        if previous is None:
            await col.delete_one({"token": token_key})
        else:
            await col.update_one(
                {"token": token_key, "claimed_at": {"$exists": False}},
                {"$set": {"token": previous["token"], "created_at": previous["created_at"]}},
            )
        logger.warning(
            "Password reset email was not delivered; error_type=%s",
            type(exc).__name__,
        )


async def reset_password(token: str, new_password: str) -> None:
    if not validate_password_strength(new_password):
        raise AppValidationError(PASSWORD_POLICY)

    # Single use = an atomic CLAIM, not an up-front delete. The link used to be
    # deleted before the password was written, so a hashing or database failure
    # after that point burned the link and left the old password in place. Now a
    # concurrent second use still loses the race (the claim filter excludes
    # claimed rows), a failed update releases the claim so the same link can be
    # retried, and the row is only deleted once the new password is stored.
    # The raw-token alternative keeps links issued by the previous release
    # usable during their one-hour TTL.
    col = get_password_reset_col()
    record = await col.find_one_and_update(
        {"token": {"$in": [_reset_token_key(token), token]}, "claimed_at": {"$exists": False}},
        {"$set": {"claimed_at": datetime.now(timezone.utc)}},
    )
    if not record:
        raise AuthError("Invalid or expired reset token")
    try:
        await _apply_password_reset(record, new_password)
    except Exception:
        await col.update_one({"_id": record["_id"]}, {"$unset": {"claimed_at": ""}})
        raise
    await col.delete_one({"_id": record["_id"]})


async def _apply_password_reset(record: dict, new_password: str) -> None:
    """Validate a claimed reset row and store the new password.

    Expiry and a missing user raise before anything is written; the caller then
    releases the claim, and the TTL index removes an expired row on its own."""

    # Motor is not tz_aware, so a datetime written as UTC-aware comes back
    # NAIVE. Subtracting it from an aware now() raised TypeError on every single
    # reset attempt — the endpoint 500'd instead of resetting anything, and the
    # expiry it was trying to enforce never ran. The TTL index on this
    # collection was the only thing actually expiring these tokens.
    created_at = record.get("created_at")
    if created_at is not None and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    if created_at and (datetime.now(timezone.utc) - created_at) > timedelta(hours=1):
        raise AuthError("Invalid or expired reset token")

    user = await user_repo.find_by_email(record["email"])
    if not user:
        raise NotFoundError("User")

    await user_repo.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "password_hash": hash_password(new_password),
                # End every existing session. A reset is very often triggered
                # BY a compromise, and without this the attacker's refresh
                # token stayed valid for up to 7 days afterwards.
                TOKENS_VALID_FROM: password_change_cutoff(),
                # The reset link reached this inbox, which proves the address.
                "email_verified": True,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    await auth_sessions.revoke_all_best_effort(
        user["_id"], reason="password_reset")
