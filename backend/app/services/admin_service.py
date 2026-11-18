import logging
import re
import secrets
from datetime import datetime, timezone

from app.core.constants import (
    TERMINAL_CASE_STATUSES,
    CaseStatus,
    KycStatus,
    NotificationType,
)
from app.core.exceptions import AppValidationError, ConflictError, NotFoundError
from app.core.security import TOKENS_VALID_FROM, hash_password, password_change_cutoff
from app.db.collections import (
    get_admin_audit_col,
    get_agreements_col,
    get_cases_col,
    get_documents_col,
    get_users_col,
)
from app.repositories.case_repo import CaseRepository
from app.repositories.user_repo import UserRepository
from app.services.auth_service import initial_kyc_fields
from app.services.notification_service import create_notification
from app.utils.email import send_kyc_result_email
from app.utils.validators import PASSWORD_POLICY, validate_password_strength

logger = logging.getLogger(__name__)

user_repo = UserRepository()
case_repo = CaseRepository()


_SECRET_TOP_LEVEL = ("password_hash", "cnic_encrypted")


async def _audit(actor: dict, action: str, target_id: str | None, detail: dict | None = None) -> None:
    """Record which admin did what. Never raises.

    An audit write must not fail the action it describes — a failed insert here
    would otherwise turn a successful KYC approval into a 500 and leave the
    lawyer verified but the admin believing it had not worked. The failure is
    logged loudly instead, matching provenance_service.record_answer.
    """
    try:
        await get_admin_audit_col().insert_one({
            "_id": secrets.token_urlsafe(16),
            "action": action,
            "actor_id": (actor or {}).get("_id"),
            "actor_email": (actor or {}).get("email"),
            "target_id": target_id,
            "detail": detail or {},
            "timestamp": datetime.now(timezone.utc),
        })
    except Exception:
        logger.exception("admin audit write failed: action=%s target=%s", action, target_id)


def _is_self(actor: dict, target_id: str) -> bool:
    return bool(actor) and actor.get("_id") == target_id


async def _assert_not_last_admin(target_id: str) -> None:
    """Refuse to remove the last admin's access.

    Deactivating or demoting the only remaining admin locks everyone out of
    every admin route, and there is no provisioning path back in:
    auth_service.register explicitly refuses the admin role, so recovery would
    mean editing the database by hand.
    """
    target = await user_repo.find_by_id(target_id)
    if not target or target.get("role") != "admin":
        return
    remaining = await get_users_col().count_documents(
        {"role": "admin", "is_active": True, "_id": {"$ne": target_id}}
    )
    if remaining == 0:
        raise AppValidationError(
            "This is the last active admin account. Promote another admin "
            "before removing this one, or the system will have no administrator."
        )


def _safe_user(u: dict) -> dict:
    """Admin-facing view of a user document.

    Also drops lawyer_profile.specialization_embedding — 384 floats of internal
    matching state that user_service._sanitize already strips for exactly this
    reason. UserProfileResponse passes lawyer_profile through as a raw dict, so
    anything left in the sub-document reaches the client.
    """
    out = {k: v for k, v in u.items() if k not in _SECRET_TOP_LEVEL}
    lp = out.get("lawyer_profile")
    if isinstance(lp, dict) and "specialization_embedding" in lp:
        lp = dict(lp)
        lp.pop("specialization_embedding", None)
        out["lawyer_profile"] = lp
    return out


def _pending_kyc_filter() -> dict:
    """THE definition of "waiting for KYC review". The queue and the
    dashboard count both read it, so the two numbers cannot disagree."""
    return {
            "role": "lawyer",
            "lawyer_profile.kyc_verified": False,
            "lawyer_profile.bar_number": {"$ne": None},
            "is_active": True,
            # Rejected lawyers are NOT pending. Previously nothing distinguished
            # them, so a rejection reappeared in this queue on every load and was
            # re-reviewed forever with no sign a decision had been taken.
            #
            # A MISSING kyc_status counts as pending: documents written before
            # this field existed are genuinely awaiting review, and excluding
            # them would silently empty the queue on deploy.
            "$or": [
                {"lawyer_profile.kyc_status": KycStatus.PENDING.value},
                {"lawyer_profile.kyc_status": {"$exists": False}},
                {"lawyer_profile.kyc_status": None},
            ],
    }


async def list_pending_kyc() -> list[dict]:
    users = await user_repo.find_many(_pending_kyc_filter())
    # _safe_user rather than an inline copy of it — the duplicate here is how
    # this endpoint would have kept leaking the embedding after the shared
    # helper was fixed.
    return [_safe_user(u) for u in users]


def _matchability_gaps(lawyer: dict) -> list[str]:
    """What is missing before this lawyer could ever be matched to a case.

    Every filtered query in the system keys off the top-level `province` and
    `lawyer_profile.specializations`. A lawyer approved without them is verified
    and invisible: `find_lawyers` filters them out, and their embedding carries
    no domain signal. Before this check existed, 17 of 25 verified lawyers had
    no province and 16 of 25 had no specialization.

    A lawyer who genuinely practises nationwide is `province: "federal"` — which
    `query_similar_lawyers` already treats as matching every province. `None`
    means "unknown", never "everywhere", and is what this refuses.
    """
    gaps = []
    if not lawyer.get("province"):
        gaps.append(
            "a province (use 'federal' for a nationwide practice)"
        )
    if not (lawyer.get("lawyer_profile") or {}).get("specializations"):
        gaps.append("at least one specialization")
    return gaps


async def process_kyc(lawyer_id: str, approved: bool, reason: str | None,
                      actor: dict | None = None) -> None:
    # Imported here, not at module scope: app.ai pulls in chromadb and the
    # embedding model, and admin_service is imported by routes that never
    # touch either.
    from app.ai.lawyer_embeddings import forget_lawyers, schedule_embed

    lawyer = await user_repo.find_by_id(lawyer_id)
    if not lawyer or lawyer.get("role") != "lawyer":
        raise NotFoundError("Lawyer")

    if approved:
        # Approving an unmatchable profile is a silent failure: the lawyer is
        # told they can now receive cases, and then never appears in a single
        # search or match. Refuse, and say exactly what the profile needs.
        gaps = _matchability_gaps(lawyer)
        if gaps:
            raise AppValidationError(
                "This profile cannot be approved yet — it is missing "
                + " and ".join(gaps)
                + ". Without these the lawyer is verified but will never appear "
                  "in a client's search or match results. Ask them to complete "
                  "their profile, then approve."
            )

        await user_repo.update_one(
            {"_id": lawyer_id},
            {
                "$set": {
                    "lawyer_profile.kyc_verified": True,
                    "lawyer_profile.kyc_status": KycStatus.APPROVED.value,
                    "lawyer_profile.kyc_rejection_reason": None,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        await create_notification(
            lawyer_id,
            NotificationType.KYC_APPROVED,
            "KYC Approved",
            "Your lawyer profile has been verified. You can now receive cases.",
        )
        try:
            await send_kyc_result_email(lawyer["email"], approved=True)
        except Exception:
            # Decision + in-app notification are already persisted; the failed
            # delivery is logged loudly by the email util.
            logger.error("KYC approval email not delivered to %s", lawyer["email"])
        await _audit(actor, "kyc.approved", lawyer_id)
        # Approval is what makes a lawyer matchable, so it is what indexes them.
        # This used to be a manual admin endpoint nobody called, which is why
        # the vector store held two smoke-test rows and no real lawyer at all.
        # Scheduled after the decision is committed and cannot undo it.
        schedule_embed(lawyer_id)
    else:
        await user_repo.update_one(
            {"_id": lawyer_id},
            {
                "$set": {
                    "lawyer_profile.kyc_verified": False,
                    "lawyer_profile.kyc_status": KycStatus.REJECTED.value,
                    "lawyer_profile.kyc_rejection_reason": reason or "Not specified",
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        await create_notification(
            lawyer_id,
            NotificationType.KYC_REJECTED,
            "KYC Rejected",
            f"Your verification was rejected. Reason: {reason or 'Not specified'}",
        )
        try:
            await send_kyc_result_email(lawyer["email"], approved=False, reason=reason)
        except Exception:
            logger.error("KYC rejection email not delivered to %s", lawyer["email"])
        await _audit(actor, "kyc.rejected", lawyer_id, {"reason": reason or "Not specified"})
        # A rejected lawyer must leave the candidate pool. Rejection can follow
        # an earlier approval, and nothing used to remove a vector once written.
        forget_lawyers([lawyer_id])


async def get_analytics() -> dict:
    users_col = get_users_col()
    cases_col = get_cases_col()

    total_users = await users_col.count_documents({})
    total_cases = await cases_col.count_documents({})
    total_agreements = await get_agreements_col().count_documents({})
    total_documents = await get_documents_col().count_documents({})
    # Counts what the QUEUE shows. Using kyc_verified alone would include
    # rejected lawyers, so the dashboard number and the review list disagreed.
    pending_kyc = await users_col.count_documents(_pending_kyc_filter())

    users_by_role: dict[str, int] = {}
    for role in ["client", "lawyer", "admin"]:
        users_by_role[role] = await users_col.count_documents({"role": role})

    cases_by_type: dict[str, int] = {}
    for ct in ["civil", "criminal", "constitutional", "family"]:
        cases_by_type[ct] = await cases_col.count_documents({"case_type": ct})

    # Derived from the enum, not hand-listed.
    #
    # The hand-written list was exactly `CaseStatus` minus `DRAFT`, because it
    # predated drafts existing. `total_cases` counts every row, so the breakdown
    # silently stopped summing to the total the moment intake began producing
    # unconfirmed drafts — and the missing count was invisible rather than wrong,
    # which is worse. Reading the enum means a future status cannot go unreported
    # the same way.
    cases_by_status: dict[str, int] = {}
    for st in [s.value for s in CaseStatus]:
        cases_by_status[st] = await cases_col.count_documents({"status": st})

    return {
        "total_users": total_users,
        "users_by_role": users_by_role,
        "total_cases": total_cases,
        "cases_by_type": cases_by_type,
        "cases_by_status": cases_by_status,
        "pending_kyc": pending_kyc,
        "total_agreements": total_agreements,
        "total_documents": total_documents,
    }


# ── User management ──────────────────────────────────────────────────────────

async def list_users(page: int, page_size: int, role: str | None, search: str | None) -> dict:
    query: dict = {}
    if role and role != "all":
        query["role"] = role
    if search:
        # Escaped: the admin types text, not a pattern. Raw, "(" or "[" made
        # an invalid regex (the list came back as "no users"), and a crafted
        # pattern could make every search scan expensively.
        pattern = re.escape(search.strip()[:100])
        query["$or"] = [
            {"full_name": {"$regex": pattern, "$options": "i"}},
            {"email": {"$regex": pattern, "$options": "i"}},
        ]
    result = await user_repo.paginate(query, page, page_size)
    return {
        "items": [_safe_user(u) for u in result.items],
        "total": result.total,
        "page": result.page,
        "page_size": result.page_size,
        "pages": result.pages,
    }


async def create_user(full_name: str, email: str, role: str,
                      actor: dict | None = None) -> dict:
    """Create an account and email its owner a link to set their password.

    The admin used to type the password, so an admin knew it and could sign
    in as that person. The stored hash is now of a random secret nobody sees;
    the account becomes usable when its owner follows the link.
    """
    password = secrets.token_urlsafe(32)
    existing = await user_repo.find_by_email(email)
    if existing:
        raise ConflictError("Email already registered")
    user_id = secrets.token_urlsafe(16)
    doc = {
        "_id": user_id,
        "role": role,
        "email": email.lower(),
        "password_hash": hash_password(password),
        "full_name": full_name,
        "phone": None,
        "province": None,
        "avatar_url": None,
        "is_active": True,
        "lawyer_profile": {"bar_number": None, "specializations": [],
                           **initial_kyc_fields(),
                           "rating": 0.0, "total_reviews": 0, "availability": True, "bio": None,
                           "experience_years": 0, "hourly_rate": None} if role == "lawyer" else None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    await user_repo.insert(doc)
    await _audit(actor, "user.created", user_id, {"role": role, "email": email.lower()})
    from app.services.auth_service import issue_reset_link
    delivered = await issue_reset_link(email.lower())
    out = _safe_user(doc)
    out["setup_link_sent"] = delivered is not False   # None = a recent link still valid
    return out


async def update_user(user_id: str, data: dict, actor: dict | None = None) -> dict:
    user = await user_repo.find_by_id(user_id)
    if not user:
        raise NotFoundError("User")
    updates = {k: v for k, v in data.items() if v is not None}
    # A closed account has been anonymised. Switching it back on would revive
    # an empty shell and break the promise that deleting means deleted.
    if user.get("is_closed"):
        raise AppValidationError("This account was deleted and cannot be changed or reactivated.")

    # An admin removing their OWN access is almost always a misclick, and it is
    # unrecoverable from inside the app: register() refuses the admin role, so
    # nobody can grant it back.
    losing_admin = (updates.get("is_active") is False
                    or (updates.get("role") is not None and updates["role"] != "admin"))
    if losing_admin and _is_self(actor, user_id):
        raise AppValidationError(
            "You cannot remove your own admin access. Ask another admin to do it."
        )
    if losing_admin:
        await _assert_not_last_admin(user_id)

    # Promoting an account to lawyer: it has no lawyer sub-document (a client's
    # is null), and every lawyer-profile write is `$set lawyer_profile.<x>`,
    # which Mongo refuses inside null. Give it the same one sign-up creates.
    if updates.get("role") == "lawyer" and not isinstance(user.get("lawyer_profile"), dict):
        from app.services.auth_service import new_lawyer_profile
        updates["lawyer_profile"] = new_lawyer_profile()

    updates["updated_at"] = datetime.now(timezone.utc)
    await user_repo.update_one({"_id": user_id}, {"$set": updates})
    await _audit(actor, "user.updated", user_id,
                 {k: v for k, v in updates.items() if k != "updated_at"})

    updated = await user_repo.find_by_id(user_id)
    # Deactivating a lawyer, or moving them off the lawyer role, does not go
    # through the closure path — so keep the vector store honest here too.
    # Everything in that collection is someone a client can be shown.
    if user.get("role") == "lawyer" or updated.get("role") == "lawyer":
        from app.ai.lawyer_embeddings import forget_lawyers, schedule_embed
        lp = updated.get("lawyer_profile") or {}
        was_matchable = (
            user.get("role") == "lawyer"
            and user.get("is_active", True)
            and (user.get("lawyer_profile") or {}).get("kyc_verified")
        )
        still_matchable = (
            updated.get("role") == "lawyer"
            and updated.get("is_active", True)
            and lp.get("kyc_verified")
        )
        if not still_matchable:
            forget_lawyers([user_id])
        elif not was_matchable:
            # The other half of the same rule, and it was missing. Deactivating
            # a lawyer dropped their vector; REACTIVATING them put nothing back,
            # so they returned verified, active and searchable in MongoDB while
            # permanently absent from semantic matching — until they happened to
            # edit their bio or an admin remembered the manual embed endpoint.
            # A membership rule that only ever removes is not a membership rule.
            schedule_embed(user_id)

    return _safe_user(updated)


async def reset_user_password(user_id: str, actor: dict | None = None) -> bool:
    """Sign the user out everywhere and email them a reset link.

    The admin no longer chooses the new password (and so never knows it). The
    old password is replaced with a random secret straight away, which is what
    an admin reset is for: the account is locked to its owner, who sets a new
    password from the link. Returns whether the email was delivered.
    """
    user = await user_repo.find_by_id(user_id)
    if not user:
        raise NotFoundError("User")
    if user.get("is_closed"):
        raise AppValidationError("This account was deleted.")
    if _is_self(actor, user_id):
        # Locking yourself out from here is unrecoverable if the email does
        # not arrive. Admins change their own password under Account.
        raise AppValidationError("Change your own password under Account.")

    # The link FIRST. If it cannot be sent, nothing is changed: replacing the
    # password with no way to set a new one would lock the user out for good.
    # None = a link sent moments ago is still valid, which counts as sent.
    from app.services.auth_service import issue_reset_link
    delivered = await issue_reset_link(user["email"])
    if delivered is False:
        return False
    await user_repo.update_one(
        {"_id": user_id},
        {"$set": {
            "password_hash": hash_password(secrets.token_urlsafe(32)),
            # The THIRD password-change path, and the one most likely to be
            # incident response: an admin resets a password precisely when an
            # account is suspected compromised. Without this the attacker's
            # refresh token outlived the reset by up to 7 days.
            # auth_service.reset_password and user_service.change_password
            # already do this; leaving one of the three out is the trap.
            TOKENS_VALID_FROM: password_change_cutoff(),
            "updated_at": datetime.now(timezone.utc),
        }},
    )
    await _audit(actor, "user.password_reset", user_id)
    from app.services import auth_sessions
    await auth_sessions.revoke_all_best_effort(user_id, reason="admin_password_reset")
    return True


async def delete_user(user_id: str, actor: dict | None = None) -> None:
    user = await user_repo.find_by_id(user_id)
    if not user:
        raise NotFoundError("User")
    if _is_self(actor, user_id):
        raise AppValidationError(
            "You cannot delete your own admin account. Ask another admin to do it."
        )
    await _assert_not_last_admin(user_id)

    # ONE deletion semantic. This used to flip `is_active` to False and nothing
    # else: no obligation check, so an admin could strand a client's lawyer
    # mid-engagement or a lawyer's clients; and no anonymisation, so a route
    # named DELETE reported success while every personal detail stayed in the
    # document. It now takes the same path as a user closing their own account
    # — refuse while engagements or payments are open, then erase.
    from app.services.user_service import _close_account_record

    await _close_account_record(user, reason="closed_by_admin")
    await _audit(actor, "user.deleted", user_id, {"role": user.get("role")})


# ── Case management ───────────────────────────────────────────────────────────

async def list_admin_cases(page: int, page_size: int, status: str | None, search: str | None) -> dict:
    query: dict = {}
    if status and status != "all":
        query["status"] = status
    if search:
        pattern = re.escape(search.strip()[:100])   # text, not a pattern
        query["$or"] = [
            {"case_number": {"$regex": pattern, "$options": "i"}},
            {"title": {"$regex": pattern, "$options": "i"}},
        ]
    result = await case_repo.paginate(query, page, page_size)

    # Batch-fetch all referenced users in one query (fixes N+1)
    user_ids = {c.get("client_id") for c in result.items if c.get("client_id")}
    user_ids |= {c.get("lawyer_id") for c in result.items if c.get("lawyer_id")}
    user_docs = await user_repo.find_many({"_id": {"$in": list(user_ids)}}) if user_ids else []
    user_map = {u["_id"]: u for u in user_docs}

    # An ALLOWLIST, not the case document: the admin oversees the platform
    # and does not read the client's story, facts, AI summary or documents.
    enriched = []
    for c in result.items:
        client = user_map.get(c.get("client_id") or "")
        lawyer = user_map.get(c.get("lawyer_id") or "")
        enriched.append({
            "_id": c["_id"],
            "case_number": c.get("case_number"),
            "title": c.get("title"),
            "case_type": c.get("case_type"),
            "status": c.get("status"),
            "province": c.get("province"),
            "client_id": c.get("client_id"),
            "client_name": (client or {}).get("full_name"),
            "lawyer_id": c.get("lawyer_id"),
            "lawyer_name": (lawyer or {}).get("full_name"),
            "created_at": c.get("created_at"),
            "updated_at": c.get("updated_at"),
            "closed_at": c.get("closed_at"),
        })
    return {
        "items": enriched,
        "total": result.total,
        "page": result.page,
        "page_size": result.page_size,
        "pages": result.pages,
    }


async def end_case(case_id: str, status: str, reason: str,
                   actor: dict | None = None) -> dict:
    """End a case as an administrator: `closed` or `dismissed`, with a reason.

    This replaces a control that could set ANY status in one click -- including
    moving a live matter back to `draft` -- with no rule, no confirmation and no
    word to the people whose case it is. A case's lifecycle belongs to its
    client and lawyer; the admin's only intervention is ending one that cannot
    end normally, and both parties are told why.
    """
    if status not in TERMINAL_CASE_STATUSES:
        raise AppValidationError("An admin can only close or dismiss a case.")
    reason = (reason or "").strip()
    if len(reason) < 10:
        raise AppValidationError("Give a reason of at least 10 characters; both parties will see it.")
    case = await case_repo.find_by_id(case_id)
    if not case:
        raise NotFoundError("Case")
    if case.get("status") in TERMINAL_CASE_STATUSES:
        raise ConflictError("This case has already ended.")

    # A hired lawyer's engagement has its own exits (complete / terminate),
    # with their consequences for the case. Ending the case under it would
    # leave an active engagement on an ended case.
    from app.db.collections import get_engagements_col
    engagements = get_engagements_col()
    if await engagements.find_one({"case_id": case_id, "status": "accepted"}, {"_id": 1}):
        raise ConflictError(
            "A lawyer is engaged on this case. The client or lawyer must complete "
            "or end that engagement first.")

    now = datetime.now(timezone.utc)
    # Guarded on the status read above, so two admins cannot both end it and
    # an end cannot land on a case that changed meanwhile.
    changed = await case_repo.update_one(
        {"_id": case_id, "status": case.get("status")},
        {"$set": {"status": status, "updated_at": now, "closed_at": now,
                  "ended_by_admin": {"status": status, "reason": reason, "at": now}}},
    )
    if not changed:
        raise ConflictError("This case changed just now. Reload and try again.")
    # Requests still waiting on the case end with it, so accepting old terms
    # cannot bring the case back.
    await engagements.update_many(
        {"case_id": case_id, "status": {"$in": ["requested", "terms_proposed"]}},
        {"$set": {"status": "cancelled", "cancelled_by": "support",
                  "updated_at": now, "responded_at": now}})
    await _audit(actor, "case.ended_by_admin", case_id,
                 {"from": case.get("status"), "to": status, "reason": reason})

    label = "closed" if status == "closed" else "dismissed"
    title = case.get("title") or case.get("case_number") or "your case"
    for party in {case.get("client_id"), case.get("lawyer_id")} - {None}:
        try:
            await create_notification(
                party, NotificationType.CASE_UPDATE, f"Case {label} by support",
                f'"{title}" was {label} by the platform support team. Reason: {reason}',
                payload={"case_id": case_id},
            )
        except Exception:  # noqa: BLE001 -- the decision stands; logged
            logger.exception("case-ended notification to %s failed", party)

    return {"_id": case_id, "status": status}


# ── Lawyer monitoring ─────────────────────────────────────────────────────────

async def list_lawyers_monitoring() -> list[dict]:
    lawyers = await user_repo.find_many({"role": "lawyer"})
    if not lawyers:
        return []

    lawyer_ids = [lw["_id"] for lw in lawyers]
    cases_col = get_cases_col()

    # Batch aggregate active + completed counts — 2 queries instead of 2*N (fixes N+1)
    active_agg = await cases_col.aggregate([
        {"$match": {"lawyer_id": {"$in": lawyer_ids}, "status": {"$in": ["open", "in_progress"]}}},
        {"$group": {"_id": "$lawyer_id", "count": {"$sum": 1}}},
    ]).to_list(None)
    active_map = {r["_id"]: r["count"] for r in active_agg}

    completed_agg = await cases_col.aggregate([
        {"$match": {"lawyer_id": {"$in": lawyer_ids}, "status": "closed"}},
        {"$group": {"_id": "$lawyer_id", "count": {"$sum": 1}}},
    ]).to_list(None)
    completed_map = {r["_id"]: r["count"] for r in completed_agg}

    result = []
    for lw in lawyers:
        lw = _safe_user(lw)
        lawyer_id = lw["_id"]
        lp = lw.get("lawyer_profile") or {}
        result.append({
            "_id": lawyer_id,
            "full_name": lw.get("full_name", ""),
            "email": lw.get("email", ""),
            "bar_number": lp.get("bar_number"),
            "specializations": lp.get("specializations", []),
            "kyc_verified": lp.get("kyc_verified", False),
            "rating": lp.get("rating", 0.0),
            "total_reviews": lp.get("total_reviews", 0),
            "experience_years": lp.get("experience_years", 0),
            "active_cases": active_map.get(lawyer_id, 0),
            "completed_cases": completed_map.get(lawyer_id, 0),
            "is_active": lw.get("is_active", False),
        })
    return result


async def purge_intake_retention(
    *,
    dry_run: bool = True,
    limit: int | None = None,
    actor: dict | None = None,
) -> dict:
    """Run the intake retention sweep as an administrator, and record who did.

    Here rather than in `intake_deletion` so that auditing stays where every
    other privileged action's auditing lives, and the retention service stays
    free of it: the sweep is meant to be callable by something other than an
    admin — a scheduled job has no acting user to record — and a service that
    demanded one would have to be given a fake.

    `intake_deletion.purge` owns every safety decision. This adds the audit
    line and nothing else: the dry-run default, the configuration flag and the
    per-record legal-hold re-read are all enforced there, and passing through
    this function cannot relax any of them.
    """
    from app.services.intake_deletion import purge

    result = await purge(limit, dry_run=dry_run)
    totals = result.get("totals") or {}
    await _audit(
        actor, "retention.intakes_purge", None,
        {
            "dry_run": dry_run,
            "enabled": result.get("enabled"),
            "eligible": totals.get("eligible"),
            "deleted": totals.get("deleted"),
            "held_skipped": totals.get("held_skipped"),
            "failed": totals.get("failed"),
        },
    )
    return result
