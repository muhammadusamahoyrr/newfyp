"""The consultation behind a hire request and a case (2026-10-20, Batch D):
stored links only, never a guess by client and date."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.exceptions import ForbiddenError
from app.db.collections import get_appointments_col, get_cases_col, get_engagements_col
from app.services import case_consultations as cc
from app.services import engagement_service

pytestmark = pytest.mark.integration

L, C, OTHER = "cc-lawyer", "cc-client", "cc-other"
T = datetime(2030, 5, 1, 4, 0, tzinfo=timezone.utc)


async def _appt(_id, *, client=C, lawyer=L, case=None, days=0, status="completed", note="Land dispute"):
    start = T + timedelta(days=days)
    await get_appointments_col().insert_one({
        "_id": _id, "client_id": client, "lawyer_id": lawyer, "case_id": case, "status": status, "mode": "video",
        "scheduled_at": start.replace(tzinfo=None), "end_at": (start + timedelta(minutes=30)).replace(tzinfo=None),
        "duration_minutes": 30, "notes": note, "lawyer_notes": "PRIVATE"})


async def _eng(_id, *, case="cc-k1", appointment=None, status="requested", days=0, lawyer=L, client=C):
    doc = {"_id": _id, "case_id": case, "client_id": client, "lawyer_id": lawyer, "status": status,
           "created_at": T + timedelta(days=days)}
    if appointment is not None:
        doc["appointment_id"] = appointment
    await get_engagements_col().insert_one(doc)


@pytest.fixture(autouse=True)
async def _setup(mongo):
    async def clean():
        await get_appointments_col().delete_many({"_id": {"$regex": "^cc-"}})
        await get_engagements_col().delete_many({"_id": {"$regex": "^cc-"}})
        await get_cases_col().delete_many({"_id": {"$regex": "^cc-"}})
    await clean()
    await get_cases_col().insert_one({"_id": "cc-k1", "client_id": C, "lawyer_id": L, "status": "in_progress", "title": "Land"})
    yield
    await clean()


async def test_a_hire_request_carries_its_own_consultation():
    await _appt("cc-a1")
    await _appt("cc-a2", days=3)        # a later meeting of the same pair: must not be picked
    await _eng("cc-e1", appointment="cc-a1")
    [e] = [x for x in await engagement_service.list_engagements(L, "lawyer") if x["id"] == "cc-e1"]
    assert e["consultation"]["id"] == "cc-a1"
    assert e["consultation"]["note"] == "Land dispute"
    assert e["consultation"]["scheduled_at"].endswith("+00:00"), "a time without its offset reads as local"
    assert "PRIVATE" not in str(e["consultation"]), "the lawyer's private notes left the appointment"
    assert e["consultation_unavailable"] is False


async def test_a_legacy_request_without_a_stored_link_is_unavailable_not_guessed():
    await _appt("cc-a1")
    await _eng("cc-e1")                                     # no appointment_id
    await _eng("cc-e2", case="cc-k2", appointment="cc-gone")  # a link to nothing
    rows = {x["id"]: x for x in await engagement_service.list_engagements(L, "lawyer") if x["id"].startswith("cc-")}
    for eid in ("cc-e1", "cc-e2"):
        assert rows[eid]["consultation"] is None
        assert rows[eid]["consultation_unavailable"] is True


async def test_a_stored_link_to_someone_elses_meeting_is_not_shown():
    await _appt("cc-a1", client=OTHER)
    await _eng("cc-e1", appointment="cc-a1")
    [e] = [x for x in await engagement_service.list_engagements(L, "lawyer") if x["id"] == "cc-e1"]
    assert e["consultation"] is None and e["consultation_unavailable"] is True


async def test_the_case_shows_its_origin_and_only_its_own_meetings():
    await _appt("cc-a1")                                    # the consultation
    await _eng("cc-e1", appointment="cc-a1", status="accepted")
    await _appt("cc-m1", case="cc-k1", days=10, status="confirmed")
    await _appt("cc-m2", case="cc-k1", days=20, status="completed")
    await _appt("cc-x1", days=15)                           # the client's, not this case's
    await _appt("cc-x2", case="cc-k1", lawyer="cc-l2", days=12)   # another lawyer's
    r = await cc.for_case("cc-k1", L)
    assert r["originating"]["id"] == "cc-a1"
    assert r["originating_unavailable"] is False
    assert [x["id"] for x in r["linked"]] == ["cc-m2", "cc-m1"], "unrelated meetings were mixed in"


async def test_a_case_whose_hire_has_no_link_says_unavailable():
    await _eng("cc-e1", status="accepted")
    r = await cc.for_case("cc-k1", L)
    assert r["originating"] is None and r["originating_unavailable"] is True and r["has_hire"] is True


async def test_a_walk_in_case_has_no_hire_and_is_not_called_unavailable():
    r = await cc.for_case("cc-k1", L)
    assert r == {"originating": None, "originating_unavailable": False, "has_hire": False, "linked": []}


async def test_only_the_cases_lawyer_may_read_it():
    with pytest.raises(ForbiddenError):
        await cc.for_case("cc-k1", "cc-l2")
