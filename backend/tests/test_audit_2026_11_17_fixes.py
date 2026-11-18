"""Regression tests for the fixes from the 2026-11-17 project audit
(AUDIT_2026-11-17.md). One test per behaviour that was wrong.

Payments, subscriptions, engagement races, the past-reviewer document view,
withdrawing a second-opinion request, the admin role change, second-annotator
labels and the abandoned quick-review claim.
"""
import secrets
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.core.exceptions import AppValidationError, ConflictError

pytestmark = pytest.mark.integration


def _tag() -> str:
    return secrets.token_hex(4)


# ── payments ─────────────────────────────────────────────────────────────────

@pytest.fixture
async def fee(app_indexes):
    """A raised fee request, owned by a fresh lawyer/client pair."""
    from app.db.collections import (
        get_cases_col, get_engagements_col, get_payment_events_col,
        get_payments_col, get_users_col,
    )
    from app.services import payment_service as ps

    now = datetime.now(timezone.utc)
    t = _tag()
    lawyer, client = f"AU-L-{t}", f"AU-C-{t}"
    case_id, eng_id = f"AU-CASE-{t}", f"AU-ENG-{t}"
    await get_users_col().insert_many([
        {"_id": lawyer, "role": "lawyer", "is_active": True, "full_name": "Adv A",
         "email": f"au-l-{t}@test.invalid", "created_at": now},
        {"_id": client, "role": "client", "is_active": True, "full_name": "Client A",
         "email": f"au-c-{t}@test.invalid", "created_at": now},
    ])
    await get_cases_col().insert_one({
        "_id": case_id, "lawyer_id": lawyer, "client_id": client,
        "title": "Audit case", "status": "in_progress", "created_at": now})
    await get_engagements_col().insert_one({
        "_id": eng_id, "case_id": case_id, "lawyer_id": lawyer,
        "client_id": client, "status": "accepted", "created_at": now})
    made = await ps.create_fee_request(lawyer, {
        "case_id": case_id, "amount": 10_000,
        "purpose": "professional_fee", "engagement_id": eng_id})
    pid = made["id"]
    yield {"payment_id": pid, "payer": client, "payee": lawyer}
    await get_payments_col().delete_one({"_id": pid})
    await get_payment_events_col().delete_many({"payment_id": pid})
    await get_cases_col().delete_one({"_id": case_id})
    await get_engagements_col().delete_one({"_id": eng_id})
    await get_users_col().delete_many({"_id": {"$in": [lawyer, client]}})


def _body(ref, event_id, status="paid"):
    import json
    return json.dumps({"event_id": event_id, "provider_ref": ref,
                       "status": status}).encode()


async def _payment(pid):
    from app.db.collections import get_payments_col
    return await get_payments_col().find_one({"_id": pid})


async def test_paying_in_the_first_of_two_checkout_tabs_still_settles(fee):
    """Pay pressed twice: the second checkout replaced the tracker, and the
    webhook for the FIRST tab was ignored while the money had been taken."""
    from app.services import payment_service as ps

    await ps.create_checkout(fee["payment_id"], fee["payer"])
    first_ref = (await _payment(fee["payment_id"]))["provider_ref"]
    await ps.create_checkout(fee["payment_id"], fee["payer"])
    assert (await _payment(fee["payment_id"]))["provider_ref"] != first_ref

    out = await ps.handle_webhook({}, _body(first_ref, f"evt-{_tag()}"))

    assert out == {"status": "paid"}
    assert (await _payment(fee["payment_id"]))["status"] == "paid"


async def test_a_failed_payment_can_be_paid_again(fee):
    from app.services import payment_service as ps

    await ps.create_checkout(fee["payment_id"], fee["payer"])
    ref = (await _payment(fee["payment_id"]))["provider_ref"]
    await ps.handle_webhook({}, _body(ref, f"evt-{_tag()}", status="failed"))
    assert (await _payment(fee["payment_id"]))["status"] == "failed"

    retry = await ps.create_checkout(fee["payment_id"], fee["payer"])

    assert retry["payment_id"] == fee["payment_id"]
    assert (await _payment(fee["payment_id"]))["status"] == "pending"


async def test_a_non_final_provider_state_does_not_fail_the_payment(fee):
    from app.services import payment_service as ps

    await ps.create_checkout(fee["payment_id"], fee["payer"])
    ref = (await _payment(fee["payment_id"]))["provider_ref"]

    out = await ps.handle_webhook({}, _body(ref, f"evt-{_tag()}", status="started"))

    assert out.get("ignored") is True
    assert (await _payment(fee["payment_id"]))["status"] == "pending"


async def test_a_redelivered_failure_is_deduped(fee):
    from app.services import payment_service as ps

    await ps.create_checkout(fee["payment_id"], fee["payer"])
    ref = (await _payment(fee["payment_id"]))["provider_ref"]
    body = _body(ref, f"evt-{_tag()}", status="failed")

    assert await ps.handle_webhook({}, body) == {"status": "failed"}
    assert await ps.handle_webhook({}, body) == {"deduped": True}


async def test_a_settlement_left_half_done_is_finished_by_the_redelivery(fee):
    """Crash between recording the event and marking the payment paid: the
    redelivery used to be deduped forever, leaving the payment pending."""
    from app.db.collections import get_payment_events_col
    from app.services import payment_service as ps

    await ps.create_checkout(fee["payment_id"], fee["payer"])
    ref = (await _payment(fee["payment_id"]))["provider_ref"]
    event_id = f"evt-{_tag()}"
    # What the dead process left behind: the event row, unapplied, minutes old.
    await get_payment_events_col().insert_one({
        "event_id": event_id, "payment_id": fee["payment_id"], "outcome": "paid",
        "applied": False,
        "created_at": datetime.now(timezone.utc) - timedelta(minutes=5)})

    out = await ps.handle_webhook({}, _body(ref, event_id))

    assert out == {"status": "paid"}
    assert (await _payment(fee["payment_id"]))["status"] == "paid"


async def test_the_unsigned_mock_webhook_is_refused_outside_dry_run(fee, monkeypatch):
    from app.services import payment_service as ps
    from app.services.payments.base import WebhookSignatureError

    await ps.create_checkout(fee["payment_id"], fee["payer"])
    ref = (await _payment(fee["payment_id"]))["provider_ref"]
    monkeypatch.setattr(settings, "payments_dry_run", False)
    monkeypatch.setattr(settings, "safepay_secret_key", "")

    with pytest.raises(WebhookSignatureError):
        await ps.handle_webhook({}, _body(ref, f"evt-{_tag()}"))
    assert (await _payment(fee["payment_id"]))["status"] == "pending"


# ── subscriptions ────────────────────────────────────────────────────────────

@pytest.fixture
async def subscribed(mongo):
    from app.db.collections import get_subscriptions_col
    lawyer = f"AU-SUB-{_tag()}"
    now = datetime.now(timezone.utc)
    await get_subscriptions_col().insert_one({
        "_id": secrets.token_urlsafe(8), "lawyer_id": lawyer,
        "tier": "professional", "cycle": "monthly", "status": "active",
        "current_period_start": now - timedelta(days=5),
        "current_period_end": now + timedelta(days=25)})
    yield lawyer
    await get_subscriptions_col().delete_many({"lawyer_id": lawyer})


async def test_a_cancelled_plan_keeps_its_paid_features_until_the_period_ends(subscribed):
    from app.services import subscription_service as ss

    await ss.cancel(subscribed)

    assert await ss.is_paid(subscribed) is True


async def test_a_cancelled_plan_lapses_after_its_period(subscribed):
    from app.db.collections import get_subscriptions_col
    from app.services import subscription_service as ss

    await ss.cancel(subscribed)
    await get_subscriptions_col().update_one(
        {"lawyer_id": subscribed},
        {"$set": {"current_period_end": datetime.now(timezone.utc) - timedelta(days=1)}})

    assert await ss.is_paid(subscribed) is False


async def test_renewing_the_same_plan_extends_it_instead_of_resetting(subscribed):
    from app.db.collections import get_subscriptions_col
    from app.services import subscription_service as ss

    before = (await get_subscriptions_col().find_one({"lawyer_id": subscribed}))["current_period_end"]
    await ss.activate({"_id": "pay-x", "payer_id": subscribed,
                       "meta": {"tier": "professional", "cycle": "monthly"}})
    after = (await get_subscriptions_col().find_one({"lawyer_id": subscribed}))["current_period_end"]

    # The new 30 days start where the paid period ended, not today.
    assert abs((after - before) - timedelta(days=30)) < timedelta(seconds=5)


async def test_switching_plan_mid_period_is_refused(subscribed):
    from app.services import subscription_service as ss

    with pytest.raises(AppValidationError):
        await ss.subscribe(subscribed, "firm", "monthly")


# ── engagement races ─────────────────────────────────────────────────────────

@pytest.fixture
async def proposed(mongo):
    from app.db.collections import get_cases_col, get_engagements_col
    t = _tag()
    eng = {"_id": f"AU-E-{t}", "case_id": f"AU-EC-{t}", "lawyer_id": f"AU-EL-{t}",
           "client_id": f"AU-ECL-{t}", "status": "terms_proposed",
           "fee_amount": 1000, "fee_type": "fixed",
           "created_at": datetime.now(timezone.utc)}
    await get_engagements_col().insert_one(eng)
    await get_cases_col().insert_one({"_id": eng["case_id"], "client_id": eng["client_id"],
                                      "lawyer_id": None, "status": "pending_lawyer"})
    yield eng
    await get_engagements_col().delete_one({"_id": eng["_id"]})
    await get_cases_col().delete_one({"_id": eng["case_id"]})


async def test_a_withdrawal_that_lost_the_race_cannot_overwrite_an_acceptance(proposed):
    """Both parties read `terms_proposed`; the client's Accept lands first.
    The lawyer's withdrawal used to overwrite it with `declined`, leaving the
    case held by a lawyer with no accepted engagement."""
    from app.db.collections import get_engagements_col
    from app.services import engagement_service as es

    # The client's acceptance wins between the lawyer's read and write.
    await get_engagements_col().update_one(
        {"_id": proposed["_id"]}, {"$set": {"status": "accepted"}})

    with pytest.raises(ConflictError):
        await es._transition_or_conflict(
            proposed["_id"], "terms_proposed", "declined", {"declined_by": "lawyer"})
    row = await get_engagements_col().find_one({"_id": proposed["_id"]})
    assert row["status"] == "accepted"


# ── admin role change ────────────────────────────────────────────────────────

async def test_promoting_a_client_to_lawyer_gives_the_account_a_lawyer_profile(mongo):
    from app.db.collections import get_users_col
    from app.services import admin_service, user_service

    uid = f"AU-PROMO-{_tag()}"
    await get_users_col().insert_one({
        "_id": uid, "role": "client", "is_active": True, "full_name": "To Promote",
        "email": f"{uid.lower()}@test.invalid", "lawyer_profile": None,
        "created_at": datetime.now(timezone.utc)})
    try:
        await admin_service.update_user(uid, {"role": "lawyer"})
        # The write that used to fail with "Cannot create field ... in null".
        await user_service.update_lawyer_profile(uid, {"bio": "Advocate"})
        row = await get_users_col().find_one({"_id": uid})
        assert row["lawyer_profile"]["bio"] == "Advocate"
    finally:
        await get_users_col().delete_one({"_id": uid})


# ── second annotator ─────────────────────────────────────────────────────────

async def test_two_annotators_can_label_the_same_turn(app_indexes):
    from app.db.collections import get_retrieval_labels_col
    from app.db.indexes import create_all_indexes

    await create_all_indexes()   # the per-annotator unique index
    rid = f"AU-REQ-{_tag()}"
    col = get_retrieval_labels_col()
    try:
        for who in ("ann_a", "ann_b"):
            await col.replace_one({"request_id": rid, "labeler": who},
                                  {"request_id": rid, "labeler": who, "answer_verdict": "correct"},
                                  upsert=True)
        assert await col.count_documents({"request_id": rid}) == 2
    finally:
        await col.delete_many({"request_id": rid})


# ── quick review stuck in `accepting` ────────────────────────────────────────

async def test_an_abandoned_accepting_claim_is_released(mongo):
    from app.db.collections import get_documents_col
    from app.services import quick_review as qr

    t = _tag()
    rid, doc_id = f"AU-QR-{t}", f"AU-QD-{t}"
    await get_documents_col().insert_one({"_id": doc_id, "client_id": "c", "quick_review_id": None})
    await qr._col().insert_one({
        "_id": rid, "doc_id": doc_id, "client_id": "c", "lawyer_id": "l",
        "status": "accepting",
        "accepting_since": datetime.now(timezone.utc) - timedelta(minutes=10),
        "expires_at": datetime.now(timezone.utc) + timedelta(days=1)})
    try:
        await qr._recover_stuck_accepting({"doc_id": doc_id})
        assert (await qr._col().find_one({"_id": rid}))["status"] == "requested"
    finally:
        await qr._col().delete_one({"_id": rid})
        await get_documents_col().delete_one({"_id": doc_id})


async def test_an_accepting_claim_whose_submission_landed_becomes_accepted(mongo):
    from app.db.collections import get_documents_col
    from app.services import quick_review as qr

    t = _tag()
    rid, doc_id = f"AU-QR-{t}", f"AU-QD-{t}"
    await get_documents_col().insert_one({"_id": doc_id, "client_id": "c", "quick_review_id": rid})
    await qr._col().insert_one({
        "_id": rid, "doc_id": doc_id, "client_id": "c", "lawyer_id": "l",
        "status": "accepting", "turnaround_hours": 24,
        "accepting_since": datetime.now(timezone.utc) - timedelta(minutes=10),
        "expires_at": datetime.now(timezone.utc) + timedelta(days=1)})
    try:
        await qr._recover_stuck_accepting({"doc_id": doc_id})
        row = await qr._col().find_one({"_id": rid})
        assert row["status"] == "accepted" and row.get("due_at")
    finally:
        await qr._col().delete_one({"_id": rid})
        await get_documents_col().delete_one({"_id": doc_id})
