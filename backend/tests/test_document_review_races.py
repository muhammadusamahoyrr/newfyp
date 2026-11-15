"""Client document review races (audit 2026-10-15).

B1 -- an approval must be pinned to the exact reviewed revision. A client draft made while the document was with its
lawyer, followed by the lawyer approving the submitted version, used to leave the document "approved" with a newer
current file the lawyer never saw. Now a client generation is refused while submitted (atomically, in the version
reservation), and an approval is refused atomically unless the current revision IS the submitted one.

B2 -- deleting a document closes its quick-review requests (kept, with an audit entry), accepting a request for a
deleted document closes it instead of reopening it, and a delete racing an accept can never remove a document the
lawyer now holds.

Real services on a real Mongo. The transaction paths need a replica set (AAI_TEST_MONGO_URL); the races are run many
times with the two operations started together so they interleave at their awaits."""
from __future__ import annotations

import asyncio
import random
import secrets

import pytest
from fastapi import HTTPException

import app.api.v1.routes.documents_v2 as v2api
from app.core.config import settings

from app.db.collections import (get_deleted_documents_col, get_document_revisions_col, get_documents_col,
                                get_notifications_col, get_users_col)
from app.db.mongodb import get_database
from app.services import artifact_store as store
from app.services import document_v2_service as v2svc
from app.services import quick_review as qr
from app.services import vault_deletion as vd
from tests._engagement_support import disengage, engage  # D1: sharing needs an accepted engagement

pytestmark = pytest.mark.integration

CLIENT = {"_id": "race-client", "role": "client", "full_name": "Race Client"}
LAWYER = {"_id": "race-lawyer", "role": "lawyer"}
PEOPLE = [CLIENT["_id"], LAWYER["_id"]]
ROUNDS = 12


def key() -> str:
    return secrets.token_urlsafe(12)


def _qr():
    return get_database()["quick_review_requests"]


@pytest.fixture(autouse=True)
def enabled(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "documents_v2", True)
    monkeypatch.setattr(settings, "upload_root", str(tmp_path))
    store.ensure_dirs()


@pytest.fixture(autouse=True)
async def _world(mongo):
    qr._indexes_ready = False

    async def wipe():
        for col in (get_documents_col(), get_deleted_documents_col()):
            async for doc in col.find({"client_id": CLIENT["_id"]}):
                await get_document_revisions_col().delete_many({"document_id": doc["_id"]})
            await col.delete_many({"client_id": CLIENT["_id"]})
        await _qr().delete_many({"client_id": CLIENT["_id"]})
        await get_notifications_col().delete_many({"user_id": {"$in": PEOPLE}})
        await get_users_col().delete_many({"_id": {"$in": PEOPLE}})
        await disengage(*PEOPLE)

    await wipe()
    await get_users_col().insert_one({**CLIENT, "email": "race-client@test.invalid"})
    await get_users_col().insert_one({**LAWYER, "email": "race-lawyer@test.invalid",
                                      "full_name": "Adv. Race", "lawyer_profile": {}})
    await qr.set_offer(LAWYER["_id"], enabled=True, fee_pkr=3000, turnaround_hours=48)
    yield
    await wipe()


FIELDS = {"sender_name": "A", "recipient_name": "B"}


async def _new_with_v1():
    doc = await v2api.create_document_v2(v2api.CreateBody(template_type="legal_notice", title="A notice"),
                                         idempotency_key=key(), current_user=CLIENT)
    rev = await v2api.generate_revision_v2(
        doc["id"], v2api.GenerateBody(template_type="legal_notice", fields={**FIELDS, "demand": "first"}),
        idempotency_key=key(), current_user=CLIENT)
    return doc["id"], rev


async def _submit(doc_id, rev):
    # Sending to a lawyer needs an accepted engagement (B1 tests only: a quick
    # review, B2, is for a lawyer the client has NOT hired).
    from app.db.collections import get_engagements_col
    if not await get_engagements_col().find_one({"client_id": CLIENT["_id"], "lawyer_id": LAWYER["_id"]}):
        await engage(CLIENT["_id"], LAWYER["_id"])
    await v2api.submit_document(doc_id, v2api.SubmitBody(expected_version=rev["version"],
                                                         expected_pdf_sha256=rev["pdf_sha256"],
                                                         lawyer_id=LAWYER["_id"]),
                                idempotency_key=key(), current_user=CLIENT)


async def _approve(doc_id, rev):
    await v2api.review_document(doc_id, v2api.ReviewBody(action="approve", expected_version=rev["version"],
                                                         expected_pdf_sha256=rev["pdf_sha256"], note="ok"),
                                idempotency_key=key(), current_user=LAWYER)


async def _client_generate(doc_id, demand):
    return await v2api.generate_revision_v2(
        doc_id, v2api.GenerateBody(template_type="legal_notice", fields={**FIELDS, "demand": demand}),
        idempotency_key=key(), current_user=CLIENT)


async def _jitter():
    await asyncio.sleep(random.random() * 0.01)


async def _settle(*coros):
    """Start together; collect each outcome (a result or the exception)."""
    async def run(c):
        await _jitter()
        return await c
    return await asyncio.gather(*(run(c) for c in coros), return_exceptions=True)


def _refused(outcome) -> bool:
    return isinstance(outcome, HTTPException) and getattr(outcome, "status_code", 409) == 409


def _assert_approval_pinned(doc: dict) -> None:
    if doc.get("review_status") == "approved":
        assert doc["approved_revision_id"] == doc["current_revision_id"], \
            "approved, but the current file is not the revision the lawyer approved"


# ── B1 ───────────────────────────────────────────────────────────────────────

async def test_b1_a_client_cannot_make_a_new_version_while_the_document_is_under_review():
    doc_id, v1 = await _new_with_v1()
    await _submit(doc_id, v1)
    with pytest.raises(HTTPException) as caught:
        await _client_generate(doc_id, "second")
    assert caught.value.status_code == 409 and "withdraw" in str(caught.value.detail).lower()
    assert await get_document_revisions_col().count_documents({"document_id": doc_id}) == 1


async def test_b1_concurrent_client_generate_and_approve_never_leaves_an_unreviewed_file_approved():
    for _ in range(ROUNDS):
        doc_id, v1 = await _new_with_v1()
        await _submit(doc_id, v1)
        gen, appr = await _settle(_client_generate(doc_id, "second"), _approve(doc_id, v1))
        assert not isinstance(appr, Exception), f"the clean approval failed: {appr!r}"
        doc = await get_documents_col().find_one({"_id": doc_id})
        assert doc["approved_revision_id"] == v1["revision_id"]
        if _refused(gen):
            # the generation came while it was still under review: refused, nothing new
            assert doc["review_status"] == "approved" and doc["current_revision_id"] == v1["revision_id"]
        else:
            # the approval came first; a new version AFTER it is the client's right -- and it can never read
            # as approved: the approval stays pinned to v1 and the document needs re-approval
            assert not isinstance(gen, Exception), f"unexpected failure: {gen!r}"
            assert doc["current_revision_id"] == gen["revision_id"] != v1["revision_id"]
            assert doc["review_status"] == "needs_reapproval"
        _assert_approval_pinned(doc)


async def test_b1_a_generation_racing_the_submit_can_never_be_approved_unseen():
    """The one window the refusal cannot close: a version RESERVED before the submit and FINISHED after it. The
    approval pin is the guarantee: approved => the current file is the approved revision."""
    approved = refused = 0
    for _ in range(ROUNDS):
        doc_id, v1 = await _new_with_v1()
        gen, sub = await _settle(_client_generate(doc_id, "second"), _submit(doc_id, v1))
        doc = await get_documents_col().find_one({"_id": doc_id})
        if doc.get("review_status") != "submitted":
            continue                         # the submit lost the race (v1 no longer current): fine
        submitted = {"version": doc["submitted_version"], "pdf_sha256": doc["submitted_pdf_sha256"]}
        try:
            await _approve(doc_id, submitted)
            approved += 1
        except HTTPException as exc:
            assert exc.status_code == 409
            refused += 1
        _assert_approval_pinned(await get_documents_col().find_one({"_id": doc_id}))
    assert approved + refused > 0


async def test_b1_an_approval_with_a_newer_current_file_is_refused_atomically_and_writes_nothing():
    doc_id, v1 = await _new_with_v1()
    await _submit(doc_id, v1)
    # a leftover from before the fix: a client draft made while under review
    await v2svc.generate_revision(document_id=doc_id, template_type="legal_notice",
                                  fields={**FIELDS, "demand": "private"}, idempotency_key=key(),
                                  refuse_when_submitted=False)
    before = await get_documents_col().find_one({"_id": doc_id})
    with pytest.raises(HTTPException) as caught:
        await _approve(doc_id, v1)
    assert caught.value.status_code == 409 and "not the version submitted" in str(caught.value.detail)
    after = await get_documents_col().find_one({"_id": doc_id})
    assert after["review_status"] == "submitted" and not after.get("approved_revision_id")
    assert after.get("review_cycles") == before.get("review_cycles")


async def test_b1_a_submit_waits_for_a_version_still_being_made():
    """Re-check 2026-10-15: a version rendering when the client submits would become current AFTER the
    submit -- the lawyer would hold a file that is no longer the client's. Refused while the render is live;
    an abandoned render (lease lapsed) does not lock the document."""
    from datetime import datetime, timedelta, timezone
    doc_id, v1 = await _new_with_v1()
    pending = {"_id": f"race-pending-{key()}", "document_id": doc_id, "version": 2, "status": "pending",
               "idempotency_key": key(), "lease_owner": "elsewhere", "fence": 0,
               "lease_expires_at": datetime.now(timezone.utc) + timedelta(minutes=2)}
    await get_document_revisions_col().insert_one(pending)
    with pytest.raises(HTTPException) as caught:
        await _submit(doc_id, v1)
    assert caught.value.status_code == 409 and "still being made" in str(caught.value.detail)
    assert (await get_documents_col().find_one({"_id": doc_id}))["review_status"] != "submitted"

    await get_document_revisions_col().update_one(
        {"_id": pending["_id"]}, {"$set": {"lease_expires_at": datetime.now(timezone.utc) - timedelta(minutes=5)}})
    await _submit(doc_id, v1)
    assert (await get_documents_col().find_one({"_id": doc_id}))["review_status"] == "submitted"


# ── B2 ───────────────────────────────────────────────────────────────────────

@pytest.fixture(params=[True, False], ids=["transactional", "plain"])
def deletion(request, monkeypatch):
    monkeypatch.setattr(settings, "document_review_requests", request.param)
    return request.param


async def _requested():
    doc_id, v1 = await _new_with_v1()
    req = await qr.create_request(client_id=CLIENT["_id"], doc_id=doc_id, lawyer_id=LAWYER["_id"],
                                  expected_version=v1["version"], expected_pdf_sha256=v1["pdf_sha256"],
                                  note="Check the amount")
    return doc_id, v1, req


async def test_b2_deleting_a_document_closes_its_request_and_keeps_its_record(deletion):
    doc_id, _v1, req = await _requested()
    await vd.delete_document(client_id=CLIENT["_id"], document_id=doc_id)
    stored = await _qr().find_one({"_id": req["id"]})
    assert stored is not None, "the request record was removed"
    assert stored["status"] == qr.CANCELLED and stored["closed_reason"] == qr.DOCUMENT_DELETED
    assert stored["note"] == "Check the amount" and stored["lawyer_id"] == LAWYER["_id"]
    assert stored["audit"][-1]["event"] == "closed" and stored["audit"][-1]["reason"] == qr.DOCUMENT_DELETED
    assert await qr.inbox(LAWYER["_id"]) == []
    note = await get_notifications_col().find_one({"user_id": LAWYER["_id"], "payload.request_id": req["id"],
                                                   "title": "Review request withdrawn"})
    assert note is not None


async def test_b2_accepting_a_request_whose_document_was_deleted_closes_it_never_reopens(deletion):
    doc_id, _v1, req = await _requested()
    # the document disappears without the request being closed (a request made before this fix)
    await get_documents_col().delete_one({"_id": doc_id})
    with pytest.raises(HTTPException) as caught:
        await qr.accept(lawyer_id=LAWYER["_id"], request_id=req["id"])
    assert caught.value.status_code == 409
    stored = await _qr().find_one({"_id": req["id"]})
    assert stored["status"] == qr.CANCELLED and stored["closed_reason"] == qr.DOCUMENT_DELETED
    with pytest.raises(HTTPException):                                      # and it stays closed
        await qr.accept(lawyer_id=LAWYER["_id"], request_id=req["id"])


async def test_b2_delete_racing_accept_never_deletes_a_document_under_review(deletion):
    for _ in range(ROUNDS):
        doc_id, _v1, req = await _requested()
        dele, acc = await _settle(vd.delete_document(client_id=CLIENT["_id"], document_id=doc_id),
                                  qr.accept(lawyer_id=LAWYER["_id"], request_id=req["id"]))
        live = await get_documents_col().find_one({"_id": doc_id})
        trashed = await get_deleted_documents_col().find_one({"_id": doc_id})
        stored = await _qr().find_one({"_id": req["id"]})
        if live is not None:
            # the accept won: the lawyer holds it, the delete was refused, nothing in the trash
            assert isinstance(dele, Exception) and getattr(dele, "status", getattr(dele, "status_code", 0)) == 409
            assert live["review_status"] == "submitted" and trashed is None
            assert stored["status"] == qr.ACCEPTED
        else:
            # the delete won: in the trash, never under review, and the request closed -- not reopened
            assert trashed is not None and trashed.get("review_status") != "submitted"
            assert isinstance(acc, Exception)
            assert stored["status"] == qr.CANCELLED and stored["closed_reason"] == qr.DOCUMENT_DELETED
        assert stored["status"] != qr.OPEN


async def test_b2_two_deletes_at_once_never_lose_the_document(deletion):
    """Re-check 2026-10-15: on the plain path the losing delete removed "its" trash entry -- which had replaced
    the winner's, so the document was in neither collection. Whoever wins, it is in the trash, once."""
    for _ in range(ROUNDS):
        doc_id, _v1 = await _new_with_v1()
        outcomes = await _settle(vd.delete_document(client_id=CLIENT["_id"], document_id=doc_id),
                                 vd.delete_document(client_id=CLIENT["_id"], document_id=doc_id))
        assert await get_documents_col().find_one({"_id": doc_id}) is None
        assert await get_deleted_documents_col().count_documents({"_id": doc_id}) == 1, "the document was lost"
        assert any(isinstance(o, dict) for o in outcomes)
        for o in outcomes:
            # the loser answers like a repeat delete; a transaction conflict may surface as a typed 503
            assert isinstance(o, dict) or getattr(o, "status", None) == 503, repr(o)
