"""A client-approved summary for the lawyer of an appointment (2026-10-19)."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.db.collections import get_appointments_col, get_cases_col
from app.db.mongodb import get_database
from app.services import appointment_files as af
from app.services import appointment_summary_share as ss

pytestmark = pytest.mark.integration

CLIENT, LAWYER, OTHER = {"_id": "ss-client"}, {"_id": "ss-lawyer"}, {"_id": "ss-other"}
APPT, CASE = "ss-appt", "ss-case"


async def _status(s):
    await get_appointments_col().update_one({"_id": APPT}, {"$set": {"status": s}})


@pytest.fixture(autouse=True)
async def _setup(mongo):
    db = get_database()
    await get_appointments_col().delete_many({"_id": APPT})
    await get_cases_col().delete_many({"_id": CASE})
    await get_cases_col().insert_one({"_id": CASE, "client_id": CLIENT["_id"], "lawyer_id": None, "status": "open",
                                      "title": "Shop rent dispute", "case_type": "civil", "province": "punjab",
                                      "description": "Landlord kept my deposit. CNIC 35202-1234567-1, call 0300-1234567."})
    await get_appointments_col().insert_one({"_id": APPT, "client_id": CLIENT["_id"], "lawyer_id": LAWYER["_id"],
                                             "status": "pending", "case_id": CASE, "notes": "Deposit back"})
    for c in ("appointment_summaries", "appointment_share_audit"):
        await db[c].delete_many({"appointment_id": APPT} if c.endswith("audit") else {"_id": APPT})
    yield
    await get_appointments_col().delete_many({"_id": APPT})
    await get_cases_col().delete_many({"_id": CASE})
    await db["appointment_summaries"].delete_many({"_id": APPT})
    await db["appointment_share_audit"].delete_many({"appointment_id": APPT})


async def test_the_draft_comes_from_the_case_with_identifiers_hidden():
    d = await ss.draft(APPT, CLIENT)
    assert d["source"] == "case" and "Shop rent dispute" in d["text"]
    assert "35202" not in d["text"] and "0300" not in d["text"]
    assert "[CNIC hidden]" in d["text"] and "[phone hidden]" in d["text"] and d["hidden"] == 2


async def test_nothing_reaches_the_lawyer_until_the_client_shares():
    assert (await ss.read(APPT, LAWYER)) == {"shared": False}
    await ss.share(APPT, CLIENT, "My edited summary")
    assert (await ss.read(APPT, LAWYER))["text"] == "My edited summary"


async def test_the_lawyer_gets_the_snapshot_not_a_later_case_edit():
    await ss.share(APPT, CLIENT, "Snapshot text")
    await get_cases_col().update_one({"_id": CASE}, {"$set": {"description": "Changed later"}})
    assert (await ss.read(APPT, LAWYER))["text"] == "Snapshot text"


async def test_revoke_removes_in_app_access_and_is_audited():
    await ss.share(APPT, CLIENT, "Text")
    await ss.revoke(APPT, CLIENT)
    assert (await ss.read(APPT, LAWYER)) == {"shared": False}
    row = await get_database()["appointment_summaries"].find_one({"_id": APPT})
    assert "text" not in row, "the revoked text must not be kept"
    actions = [a["action"] async for a in get_database()["appointment_share_audit"].find({"appointment_id": APPT}).sort("at", 1)]
    assert actions == ["share", "revoke"]


async def test_summary_and_documents_are_separate_permissions():
    PDF = b"%PDF-1.4\n%%EOF\n"
    await af.upload(APPT, CLIENT, PDF, "a.pdf", None, False)
    await ss.share(APPT, CLIENT, "Text")
    assert (await af.list_for(APPT, LAWYER))["items"] == [], "sharing the summary leaked a document"
    await ss.revoke(APPT, CLIENT)
    await _status("confirmed")
    assert len((await af.list_for(APPT, LAWYER))["items"]) == 1, "revoking the summary hid a document"
    await get_database()["appointment_files"].delete_many({"appointment_id": APPT})


@pytest.mark.parametrize("status", ["cancelled", "expired"])
async def test_a_closed_request_gives_the_lawyer_nothing(status):
    await ss.share(APPT, CLIENT, "Text")
    await _status(status)
    assert (await ss.read(APPT, LAWYER)) == {"shared": False}


async def test_only_the_client_shares_and_strangers_get_not_found():
    with pytest.raises(HTTPException) as e:
        await ss.share(APPT, LAWYER, "x")
    assert e.value.status_code == 404
    for call in (ss.read(APPT, OTHER), ss.draft(APPT, OTHER), ss.share(APPT, OTHER, "x")):
        with pytest.raises(HTTPException) as e:
            await call
        assert e.value.status_code == 404


async def test_no_sharing_after_the_request_is_closed():
    await _status("cancelled")
    with pytest.raises(HTTPException) as e:
        await ss.share(APPT, CLIENT, "x")
    assert e.value.status_code == 409
