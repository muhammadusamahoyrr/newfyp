"""What waits on the lawyer, counted once (2026-10-20)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db.collections import get_appointments_col, get_engagements_col
from app.services import lawyer_actions as la
from app.services.appointment_slots import occupied_slots

pytestmark = pytest.mark.integration

L, OTHER_L = "la-lawyer", "la-lawyer-2"
NOW = datetime(2030, 3, 1, 9, 0, tzinfo=timezone.utc)


async def _appt(_id, status, minutes, lawyer=L, expires_in=None):
    start = NOW + timedelta(minutes=minutes)
    await get_appointments_col().insert_one({
        "_id": _id, "client_id": "la-c1", "lawyer_id": lawyer, "status": status, "mode": "video",
        "scheduled_at": start, "end_at": start + timedelta(minutes=30),
        "occupied_slots": occupied_slots(start, 30),
        "expires_at": None if expires_in is None else NOW + timedelta(minutes=expires_in)})


async def _eng(_id, status, lawyer=L, minutes_ago=60):
    await get_engagements_col().insert_one({
        "_id": _id, "client_id": "la-c1", "lawyer_id": lawyer, "case_id": f"case-{_id}",
        "status": status, "created_at": NOW - timedelta(minutes=minutes_ago)})


@pytest.fixture(autouse=True)
async def _setup(mongo):
    async def clean():
        await get_appointments_col().delete_many({"_id": {"$regex": "^la-"}})
        await get_engagements_col().delete_many({"_id": {"$regex": "^la-"}})
    await clean()
    yield
    await clean()


async def test_nothing_waiting():
    r = await la.action_counts(L, now=NOW)
    assert r["to_do"] == 0
    assert r["next"] == {"appointment_request": None, "outcome": None, "hire_request": None}


async def test_a_meeting_needs_its_outcome_the_moment_it_ends_and_is_not_upcoming():
    await _appt("la-ended", "confirmed", -31)        # ended a minute ago: no grace
    await _appt("la-live", "confirmed", -10)         # still running
    await _appt("la-later", "confirmed", 120)
    r = await la.action_counts(L, now=NOW)
    assert r["outcomes_to_record"] == 1
    assert r["next"]["outcome"] == "la-ended"
    assert r["upcoming"] == 2, "an ended meeting was counted as upcoming"


async def test_requests_past_their_answer_time_are_not_counted():
    await _appt("la-open", "pending", 600, expires_in=60)
    await _appt("la-noexp", "pending", 900)
    await _appt("la-lapsed", "pending", 300, expires_in=-5)
    r = await la.action_counts(L, now=NOW)
    assert r["appointment_requests"] == 2
    assert r["next"]["appointment_request"] == "la-open"


async def test_hire_requests_are_actions_terms_sent_are_not():
    await _eng("la-e1", "requested", minutes_ago=30)
    await _eng("la-e2", "requested", minutes_ago=90)
    await _eng("la-e3", "terms_proposed")
    await _eng("la-e4", "accepted")
    r = await la.action_counts(L, now=NOW)
    assert r["hire_requests"] == 2
    assert r["next"]["hire_request"] == "la-e2", "the oldest request is not first"
    assert r["waiting_for_client"] == 1
    assert r["to_do"] == 2


async def test_only_this_lawyers_rows():
    await _appt("la-x1", "confirmed", -60, lawyer=OTHER_L)
    await _appt("la-x2", "pending", 600, lawyer=OTHER_L)
    await _eng("la-x3", "requested", lawyer=OTHER_L)
    r = await la.action_counts(L, now=NOW)
    assert (r["to_do"], r["upcoming"], r["waiting_for_client"]) == (0, 0, 0)


async def test_to_do_is_the_sum_of_the_three_action_queues():
    await _appt("la-p", "pending", 600)
    await _appt("la-o", "confirmed", -60)
    await _eng("la-h", "requested")
    await _appt("la-u", "confirmed", 700)   # not 600: one lawyer, one slot (la-p holds it)
    await _eng("la-w", "terms_proposed")
    r = await la.action_counts(L, now=NOW)
    assert r["to_do"] == 3
