"""Admin panel hardening (2026-11-18): what an admin may do, and see.

- the case list carries metadata only, never the client's story;
- an admin can only END a case (close/dismiss), with a reason both parties get;
- a KYC rejection needs a reason;
- searches treat the admin's text as text, not as a regex;
- the dashboard's pending-KYC count is the queue's definition;
- a deleted account cannot be reactivated;
- creating a user sets no admin-known password and emails a set-up link.
"""
import secrets
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.core.exceptions import AppValidationError

pytestmark = pytest.mark.integration

ADMIN = {"_id": "hard-admin", "role": "admin"}


def _t() -> str:
    return secrets.token_hex(4)


@pytest.fixture
async def case_with_parties(mongo):
    from app.db.collections import get_cases_col, get_notifications_col, get_users_col
    t = _t()
    client, lawyer, case_id = f"HC-C-{t}", f"HC-L-{t}", f"HC-CASE-{t}"
    now = datetime.now(timezone.utc)
    await get_users_col().insert_many([
        {"_id": client, "role": "client", "full_name": "Hard Client", "email": f"hc-{t}@x.test", "is_active": True},
        {"_id": lawyer, "role": "lawyer", "full_name": "Hard Lawyer", "email": f"hl-{t}@x.test", "is_active": True},
    ])
    await get_cases_col().insert_one({
        "_id": case_id, "case_number": f"HC/{t}", "title": "Rent dispute",
        "client_id": client, "lawyer_id": lawyer, "status": "in_progress",
        "description": "PRIVATE FACTS the admin must not see",
        "ai_summary": "PRIVATE SUMMARY", "created_at": now, "updated_at": now})
    yield {"client": client, "lawyer": lawyer, "case_id": case_id, "tag": t}
    await get_cases_col().delete_one({"_id": case_id})
    await get_users_col().delete_many({"_id": {"$in": [client, lawyer]}})
    await get_notifications_col().delete_many({"user_id": {"$in": [client, lawyer]}})


async def test_the_admin_case_list_carries_no_case_contents(case_with_parties):
    from app.services import admin_service

    page = await admin_service.list_admin_cases(1, 50, None, f"HC/{case_with_parties['tag']}")

    (row,) = page["items"]
    assert row["client_name"] == "Hard Client" and row["lawyer_name"] == "Hard Lawyer"
    assert "PRIVATE" not in str(row), "case contents reached the admin list"
    assert "description" not in row and "ai_summary" not in row


async def test_ending_a_case_tells_both_parties_why(case_with_parties):
    from app.db.collections import get_cases_col, get_notifications_col
    from app.services import admin_service

    await admin_service.end_case(case_with_parties["case_id"], "dismissed",
                                 "Duplicate of another case on file", ADMIN)

    stored = await get_cases_col().find_one({"_id": case_with_parties["case_id"]})
    assert stored["status"] == "dismissed" and stored["closed_at"] is not None
    for who in ("client", "lawyer"):
        n = await get_notifications_col().find_one({"user_id": case_with_parties[who]})
        assert n and "Duplicate of another case" in n["body"]


async def test_the_case_search_treats_brackets_as_text(case_with_parties):
    from app.services import admin_service
    # Unescaped, "(" is an invalid regex and the whole query failed.
    page = await admin_service.list_admin_cases(1, 10, None, "(rent[")
    assert page["items"] == []


async def test_the_user_search_treats_brackets_as_text(mongo):
    from app.services import admin_service
    page = await admin_service.list_users(1, 10, None, "a(b[c+")
    assert page["items"] == []


def test_a_kyc_rejection_needs_a_reason():
    from app.schemas.admin import KYCAction
    with pytest.raises(ValidationError):
        KYCAction(approved=False, rejection_reason=None)
    with pytest.raises(ValidationError):
        KYCAction(approved=False, rejection_reason="  ")
    assert KYCAction(approved=False, rejection_reason="Certificate unreadable").approved is False
    assert KYCAction(approved=True).approved is True


async def test_the_dashboard_counts_the_same_pending_kyc_as_the_queue(mongo):
    from app.db.collections import get_users_col
    from app.services import admin_service
    t = _t()
    rows = [
        # In the queue: has a bar number, active, pending.
        {"_id": f"HK-1-{t}", "role": "lawyer", "is_active": True, "email": f"hk1-{t}@x.test",
         "lawyer_profile": {"kyc_verified": False, "bar_number": "B-1", "kyc_status": "pending"}},
        # Not in the queue: no bar number yet / deactivated.
        {"_id": f"HK-2-{t}", "role": "lawyer", "is_active": True, "email": f"hk2-{t}@x.test",
         "lawyer_profile": {"kyc_verified": False, "bar_number": None, "kyc_status": "pending"}},
        {"_id": f"HK-3-{t}", "role": "lawyer", "is_active": False, "email": f"hk3-{t}@x.test",
         "lawyer_profile": {"kyc_verified": False, "bar_number": "B-3", "kyc_status": "pending"}},
    ]
    await get_users_col().insert_many(rows)
    try:
        queue = await admin_service.list_pending_kyc()
        overview = await admin_service.get_analytics()
        assert overview["pending_kyc"] == len(queue)
    finally:
        await get_users_col().delete_many({"_id": {"$in": [r["_id"] for r in rows]}})


async def test_a_deleted_account_cannot_be_reactivated(mongo):
    from app.db.collections import get_users_col
    from app.services import admin_service
    uid = f"HD-{_t()}"
    await get_users_col().insert_one({"_id": uid, "role": "client", "is_active": False,
                                      "is_closed": True, "email": f"closed+{uid}@deleted.invalid"})
    try:
        with pytest.raises(AppValidationError):
            await admin_service.update_user(uid, {"is_active": True}, actor=ADMIN)
        assert (await get_users_col().find_one({"_id": uid}))["is_active"] is False
    finally:
        await get_users_col().delete_one({"_id": uid})


async def test_a_created_user_gets_a_setup_link_and_no_admin_known_password(mongo, monkeypatch):
    from app.db.collections import get_users_col
    from app.services import admin_service, auth_service

    sent = []

    async def fake_forgot(email):
        sent.append(email)
        return True
    monkeypatch.setattr(auth_service, "issue_reset_link", fake_forgot)

    email = f"new-{_t()}@x.test"
    out = await admin_service.create_user("New Person", email, "client", actor=ADMIN)
    try:
        assert sent == [email]
        assert out["setup_link_sent"] is True
    finally:
        await get_users_col().delete_one({"_id": out["_id"]})


async def test_ending_a_case_cancels_its_waiting_requests_so_it_cannot_be_revived(case_with_parties):
    """Old terms accepted after support dismissed the case used to claim it
    again (dismissed -> in_progress)."""
    from app.db.collections import get_cases_col, get_engagements_col
    from app.services import admin_service, engagement_service

    await get_cases_col().update_one({"_id": case_with_parties["case_id"]},
                                     {"$set": {"lawyer_id": None, "status": "pending_lawyer"}})
    eng_id = f"HE-{case_with_parties['tag']}"
    await get_engagements_col().insert_one({
        "_id": eng_id, "case_id": case_with_parties["case_id"],
        "client_id": case_with_parties["client"], "lawyer_id": case_with_parties["lawyer"],
        "status": "terms_proposed", "fee_amount": 1000, "fee_type": "fixed"})
    try:
        await admin_service.end_case(case_with_parties["case_id"], "dismissed",
                                     "Client asked support to withdraw", ADMIN)
        assert (await get_engagements_col().find_one({"_id": eng_id}))["status"] == "cancelled"

        # Even an engagement left accepted cannot pull the case back.
        await get_engagements_col().update_one({"_id": eng_id}, {"$set": {"status": "accepted"}})
        await engagement_service._ensure_case_claimed(await get_engagements_col().find_one({"_id": eng_id}))
        assert (await get_cases_col().find_one({"_id": case_with_parties["case_id"]}))["status"] == "dismissed"
    finally:
        await get_engagements_col().delete_one({"_id": eng_id})


async def test_a_case_with_a_hired_lawyer_cannot_be_ended_by_support(case_with_parties):
    from app.core.exceptions import ConflictError
    from app.db.collections import get_engagements_col
    from app.services import admin_service

    eng_id = f"HA-{case_with_parties['tag']}"
    await get_engagements_col().insert_one({
        "_id": eng_id, "case_id": case_with_parties["case_id"],
        "client_id": case_with_parties["client"], "lawyer_id": case_with_parties["lawyer"],
        "status": "accepted"})
    try:
        with pytest.raises(ConflictError):
            await admin_service.end_case(case_with_parties["case_id"], "closed",
                                         "Lawyer stopped responding", ADMIN)
    finally:
        await get_engagements_col().delete_one({"_id": eng_id})


async def test_a_second_paid_plan_never_downgrades_a_running_period(mongo):
    from datetime import timedelta
    from app.db.collections import get_subscriptions_col
    from app.services import subscription_service as ss

    lawyer = f"HS-{_t()}"
    now = datetime.now(timezone.utc)
    await get_subscriptions_col().insert_one({
        "_id": secrets.token_urlsafe(8), "lawyer_id": lawyer, "tier": "firm",
        "cycle": "monthly", "status": "active",
        "current_period_start": now, "current_period_end": now + timedelta(days=20)})
    try:
        await ss.activate({"_id": "p2", "payer_id": lawyer,
                           "meta": {"tier": "professional", "cycle": "monthly"}})
        row = await get_subscriptions_col().find_one({"lawyer_id": lawyer})
        assert row["tier"] == "firm"
    finally:
        await get_subscriptions_col().delete_many({"lawyer_id": lawyer})
