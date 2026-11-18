"""Admin service — the module's first tests.

304 lines gating KYC verification, user creation, role changes, password resets
and account deactivation, with no test referencing it directly or through HTTP.
Access control itself was already sound (every route sits behind require_admin,
and role_required re-reads the role from Mongo), so these start with the
mutations rather than the gate.

Ordered by blast radius: the password-reset revocation gap first, because an
admin reset is usually incident response and the attacker's session was
outliving it.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.exceptions import AppValidationError, NotFoundError
from app.core.security import (
    TOKENS_VALID_FROM,
    hash_password,
    token_predates_password_change,
)


@pytest.fixture
async def admin_and_users(mongo):
    """One admin plus a client and a lawyer to act on."""
    from app.db.collections import get_users_col

    docs = [
        {"_id": "ADM-1", "role": "admin", "email": "adm1@x.test",
         "password_hash": hash_password("Str0ngPass1"), "full_name": "Admin One",
         "is_active": True},
        {"_id": "ADM-CLIENT", "role": "client", "email": "ac@x.test",
         "password_hash": hash_password("Str0ngPass1"), "full_name": "A Client",
         "is_active": True},
        {"_id": "ADM-LAWYER", "role": "lawyer", "email": "al@x.test",
         "password_hash": hash_password("Str0ngPass1"), "full_name": "A Lawyer",
         "is_active": True,
         "lawyer_profile": {"bar_number": "BAR-1", "kyc_verified": False,
                            "kyc_rejection_reason": None, "specializations": [],
                            "rating": 0.0, "availability": True,
                            "specialization_embedding": [0.1] * 384}},
    ]
    await get_users_col().insert_many(docs)
    yield {"admin": "ADM-1", "client": "ADM-CLIENT", "lawyer": "ADM-LAWYER"}
    await get_users_col().delete_many(
        {"_id": {"$in": ["ADM-1", "ADM-CLIENT", "ADM-LAWYER"]}})


@pytest.fixture
def reset_email_works(monkeypatch):
    """The reset path sends the link FIRST and changes nothing if it cannot.
    Tests that exercise the lock-out need a link that 'goes'."""
    from app.services import auth_service

    async def delivered(email):
        return True
    monkeypatch.setattr(auth_service, "issue_reset_link", delivered)


# ── an admin password reset ends the user's sessions ─────────────────────────

@pytest.mark.integration
async def test_an_admin_reset_revokes_the_users_existing_sessions(admin_and_users, reset_email_works):
    """The path an admin reaches for when an account is suspected compromised:
    every existing token must stop working."""
    from app.db.collections import get_users_col
    from app.services import admin_service

    uid = admin_and_users["client"]
    await admin_service.reset_user_password(uid)

    user = await get_users_col().find_one({"_id": uid})
    assert user.get(TOKENS_VALID_FROM) is not None, "no revocation cutoff written"
    stale = {"sub": uid, "type": "refresh",
             "iat": (datetime.now(timezone.utc) - timedelta(minutes=5)).timestamp()}
    assert token_predates_password_change(stale, user) is True


@pytest.mark.integration
async def test_an_admin_reset_locks_out_the_old_password_and_sets_none_the_admin_knows(admin_and_users, reset_email_works):
    """The admin no longer chooses the new password: the old one stops working
    and the owner sets a new one from the emailed link."""
    from app.core.exceptions import AuthError
    from app.services import admin_service, auth_service

    await admin_service.reset_user_password(admin_and_users["client"])

    with pytest.raises(AuthError):
        await auth_service.login("ac@x.test", "Str0ngPass1")


@pytest.mark.integration
async def test_resetting_an_unknown_user_is_refused(admin_and_users):
    from app.services import admin_service

    with pytest.raises(NotFoundError):
        await admin_service.reset_user_password("NO-SUCH-USER")


# ── the admin view never carries internal state ──────────────────────────────

def test_the_admin_view_drops_secrets_and_the_matching_embedding():
    """UserProfileResponse passes lawyer_profile through as a raw dict, so
    anything left in the sub-document reaches the client. user_service._sanitize
    already strips this vector for the same reason."""
    from app.services.admin_service import _safe_user

    out = _safe_user({
        "_id": "u1", "email": "e@x.test",
        "password_hash": "$2b$12$abc", "cnic_encrypted": "gAAAA",
        "lawyer_profile": {"bar_number": "B1",
                           "specialization_embedding": [0.1] * 384},
    })

    assert "password_hash" not in out
    assert "cnic_encrypted" not in out
    assert "specialization_embedding" not in out["lawyer_profile"]
    assert out["lawyer_profile"]["bar_number"] == "B1", "real profile data must survive"


def test_the_admin_view_does_not_mutate_the_document_it_was_given():
    """Motor hands back live dicts; stripping in place would corrupt the caller's
    copy and, for a cached document, everyone else's."""
    from app.services.admin_service import _safe_user

    original = {"_id": "u1", "password_hash": "x",
                "lawyer_profile": {"specialization_embedding": [0.1] * 384}}
    _safe_user(original)

    assert "password_hash" in original
    assert "specialization_embedding" in original["lawyer_profile"]


def test_a_client_document_survives_the_admin_view():
    """lawyer_profile is None on clients — the strip must not assume a dict."""
    from app.services.admin_service import _safe_user

    out = _safe_user({"_id": "u1", "role": "client", "lawyer_profile": None,
                      "password_hash": "x"})

    assert out["lawyer_profile"] is None
    assert "password_hash" not in out


@pytest.mark.integration
async def test_every_admin_listing_uses_the_shared_view(admin_and_users):
    """list_pending_kyc had its own inline copy of the strip, which is how it
    would have kept leaking after the shared helper was fixed."""
    from app.services import admin_service

    pending = await admin_service.list_pending_kyc()
    listed = await admin_service.list_users(1, 50, None, None)

    for row in pending + listed["items"]:
        assert "password_hash" not in row
        lp = row.get("lawyer_profile")
        if isinstance(lp, dict):
            assert "specialization_embedding" not in lp


@pytest.mark.integration
async def test_a_reset_whose_email_cannot_go_changes_nothing(admin_and_users, monkeypatch):
    """Replacing the password with no link to set a new one would lock the
    user out for good."""
    from app.services import admin_service, auth_service

    async def not_delivered(email):
        return False
    monkeypatch.setattr(auth_service, "issue_reset_link", not_delivered)

    assert await admin_service.reset_user_password(admin_and_users["client"]) is False
    assert await auth_service.login("ac@x.test", "Str0ngPass1")   # still works


@pytest.mark.integration
async def test_an_admin_cannot_reset_their_own_password_here(admin_and_users, reset_email_works):
    from app.services import admin_service

    me = {"_id": admin_and_users["client"], "role": "admin"}
    with pytest.raises(AppValidationError):
        await admin_service.reset_user_password(admin_and_users["client"], actor=me)
