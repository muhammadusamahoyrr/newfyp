"""The lawyer's Clients index, computed from source (2026-10-19, Marhala 4;
stage + next_action + chips, 2026-10-20 Batch C)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db.collections import get_appointments_col, get_cases_col, get_engagements_col, get_users_col
from app.services import lawyer_clients as lc
from app.services.appointment_slots import occupied_slots

pytestmark = pytest.mark.integration

L, OTHER_L = "lc-lawyer", "lc-lawyer-2"
NOW = datetime(2030, 3, 1, 9, 0, tzinfo=timezone.utc)
CLIENTS = [f"lc-c{i}" for i in range(1, 8)]


async def _appt(_id, client, status, hours, lawyer=L, expires_hours=None):
    start = NOW + timedelta(hours=hours)
    await get_appointments_col().insert_one({"_id": _id, "client_id": client, "lawyer_id": lawyer, "status": status,
                                             "scheduled_at": start, "end_at": start + timedelta(minutes=30), "mode": "video",
                                             "occupied_slots": occupied_slots(start, 30),
                                             "expires_at": None if expires_hours is None else NOW + timedelta(hours=expires_hours)})


async def _eng(_id, client, status, lawyer=L, hours_ago=1):
    await get_engagements_col().insert_one({"_id": _id, "client_id": client, "lawyer_id": lawyer, "case_id": f"x-{_id}",
                                            "status": status, "created_at": NOW - timedelta(hours=hours_ago)})


async def _case(_id, client, status, lawyer=L):
    await get_cases_col().insert_one({"_id": _id, "client_id": client, "lawyer_id": lawyer, "status": status,
                                      "title": f"Case {_id}", "case_number": f"LC-{_id}", "province": "punjab", "created_at": NOW - timedelta(days=5)})


@pytest.fixture(autouse=True)
async def _setup(mongo):
    async def clean():
        await get_appointments_col().delete_many({"_id": {"$regex": "^lc-"}})
        await get_cases_col().delete_many({"_id": {"$regex": "^lc-"}})
        await get_engagements_col().delete_many({"_id": {"$regex": "^lc-"}})
        await get_users_col().delete_many({"_id": {"$in": CLIENTS}})
    await clean()
    await get_users_col().insert_many([{"_id": c, "full_name": f"Name {c}", "email": f"{c}@x.pk", "role": "client"}
                                       for c in CLIENTS])
    yield
    await clean()


async def _by_id():
    out = await lc.list_clients(L, now=NOW)
    return out, {x["client_id"]: x for x in out["items"]}


async def test_each_stage_is_derived_from_the_records():
    await _appt("lc-a1", "lc-c1", "pending", 24)                       # requested
    await _appt("lc-a2", "lc-c2", "confirmed", 26)                     # scheduled (not lc-a1's slot)
    await _appt("lc-a3", "lc-c3", "completed", -48)                    # completed
    await _case("lc-k4", "lc-c4", "in_progress")                       # engaged
    await _appt("lc-a4", "lc-c4", "completed", -72)
    await _case("lc-k5", "lc-c5", "closed")                            # closed
    await _appt("lc-a5", "lc-c5", "completed", -200)                   # ...after a consultation
    await _appt("lc-a6", "lc-c6", "completed", -60)                    # hire request
    await _eng("lc-e6", "lc-c6", "requested")
    out, by = await _by_id()
    assert {c: by[c]["stage"] for c in by} == {
        "lc-c1": lc.REQUESTED, "lc-c2": lc.SCHEDULED, "lc-c3": lc.COMPLETED,
        "lc-c4": lc.ENGAGED, "lc-c5": lc.CLOSED, "lc-c6": lc.HIRE}
    assert out["totals"] == {lc.ENGAGED: 1, lc.HIRE: 1, lc.SCHEDULED: 1, lc.REQUESTED: 1, lc.CLOSED: 1, lc.COMPLETED: 1}
    assert [x["stage"] for x in out["items"]] == list(lc.STAGES), "ordered by stage"


async def test_a_closed_request_alone_is_not_a_client():
    await _appt("lc-a1", "lc-c1", "cancelled", 24)
    await _appt("lc-a2", "lc-c2", "expired", 24)
    await _appt("lc-a3", "lc-c3", "no_show", -24)
    out, _ = await _by_id()
    assert out["items"] == []


async def test_only_this_lawyers_records_count():
    await _appt("lc-a1", "lc-c1", "confirmed", 24, lawyer=OTHER_L)
    await _case("lc-k1", "lc-c1", "open", lawyer=OTHER_L)
    await _case("lc-k2", "lc-c2", "open", lawyer=None)
    out, _ = await _by_id()
    assert out["items"] == []


async def test_counts_next_appointment_cases_and_needs_outcome():
    await _case("lc-k1", "lc-c1", "open")
    await _case("lc-k2", "lc-c1", "closed")
    await _appt("lc-a1", "lc-c1", "confirmed", 48)
    await _appt("lc-a2", "lc-c1", "confirmed", 24)
    await _appt("lc-a3", "lc-c1", "confirmed", -24)                   # ended, no outcome
    await _appt("lc-a4", "lc-c1", "completed", -96)
    _, by = await _by_id()
    c = by["lc-c1"]
    assert c["counts"] == {"requests": 0, "upcoming": 2, "consultations": 1, "open_cases": 1, "closed_cases": 1}
    assert c["next_appointment"]["id"] == "lc-a2"
    assert c["needs_outcome"] is True
    assert c["latest_appointment_id"] == "lc-a1"
    assert {k["id"] for k in c["cases"]} == {"lc-k1", "lc-k2"}
    assert c["name"] == "Name lc-c1" and c["province"] == "punjab"


async def test_a_prospective_clients_email_is_not_shown():
    await _appt("lc-a1", "lc-c1", "pending", 24)
    await _case("lc-k2", "lc-c2", "open")
    _, by = await _by_id()
    assert by["lc-c1"]["email"] is None
    assert by["lc-c2"]["email"] == "lc-c2@x.pk"
    assert by["lc-c1"]["pending_request_id"] == "lc-a1"


async def test_combined_state_primary_is_send_terms_and_the_rest_stay_visible():
    """Ahmed: a hire request, a meeting waiting for its outcome and a new
    appointment request, all at once."""
    await _appt("lc-a1", "lc-c1", "completed", -72)
    await _eng("lc-e1", "lc-c1", "requested")
    await _appt("lc-a2", "lc-c1", "confirmed", -2)                    # ended, no outcome
    await _appt("lc-a3", "lc-c1", "pending", 72, expires_hours=48)
    _, by = await _by_id()
    c = by["lc-c1"]
    assert c["stage"] == lc.HIRE
    assert c["next_action"] == {"kind": "send_terms", "target_id": "lc-e1"}
    assert c["pending"] == {"hire_requests": 1, "outcomes": 1, "appointment_requests": 1}
    t = c["targets"]
    assert (t["engagement_id"], t["outcome_appointment_id"], t["pending_appointment_id"]) == ("lc-e1", "lc-a2", "lc-a3")
    assert c["message"] == {"kind": "appointment", "target_id": "lc-a2"}


async def test_an_engaged_client_still_owes_an_outcome():
    await _case("lc-k1", "lc-c1", "in_progress")
    await _appt("lc-a1", "lc-c1", "confirmed", -3)
    await _appt("lc-a2", "lc-c1", "confirmed", 30)
    _, by = await _by_id()
    c = by["lc-c1"]
    assert c["stage"] == lc.ENGAGED, "the relationship is engaged"
    assert c["next_action"] == {"kind": "record_outcome", "target_id": "lc-a1"}, "the outcome is the action"
    assert c["message"] == {"kind": "case", "target_id": "lc-k1", "case_number": "LC-lc-k1"}
    assert c["targets"]["next_appointment_id"] == "lc-a2"


async def test_terms_sent_is_waiting_for_the_client_not_a_lawyer_action():
    await _appt("lc-a1", "lc-c1", "completed", -72)
    await _eng("lc-e1", "lc-c1", "terms_proposed")
    _, by = await _by_id()
    c = by["lc-c1"]
    assert c["stage"] == lc.HIRE
    assert c["waiting_for_client"] == 1
    assert c["pending"]["hire_requests"] == 0
    assert c["next_action"] is None or c["next_action"]["kind"] != "send_terms"
    assert c["targets"]["waiting_engagement_id"] == "lc-e1"


async def test_next_action_priority_and_targets():
    # answer_request beats viewing the next appointment
    await _appt("lc-a1", "lc-c1", "confirmed", 10)
    await _appt("lc-a2", "lc-c1", "pending", 50, expires_hours=40)
    await _appt("lc-a3", "lc-c1", "pending", 60, expires_hours=20)
    # only an upcoming meeting
    await _appt("lc-b1", "lc-c2", "confirmed", 30)
    # only a closed case
    await _case("lc-k3", "lc-c3", "closed")
    _, by = await _by_id()
    assert by["lc-c1"]["next_action"] == {"kind": "answer_request", "target_id": "lc-a3"}, "nearest answer-by first"
    assert by["lc-c2"]["next_action"] == {"kind": "view_appointment", "target_id": "lc-b1"}
    assert by["lc-c2"]["message"] == {"kind": "appointment", "target_id": "lc-b1"}
    assert by["lc-c3"]["next_action"] == {"kind": "open_case", "target_id": "lc-k3"}


async def test_a_request_past_its_answer_time_is_not_work():
    await _appt("lc-a1", "lc-c1", "pending", 30, expires_hours=-1)
    out, _ = await _by_id()
    assert out["items"] == [], "a lapsed request made a client"
