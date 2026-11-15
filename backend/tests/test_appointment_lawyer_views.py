"""The lawyer's appointment views (2026-10-20, Batch B).

  - Needs outcome lists a meeting the moment it ends (`immediate`), while the
    two-hour grace stays the default for reminders;
  - its keyset pages never skip a row, even while outcomes are being recorded;
  - Upcoming is confirmed AND not ended;
  - "All" (order=action) is worked top-down: needs outcome (oldest ended),
    requests (nearest answer-by), upcoming (earliest), then history (newest).
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.exceptions import AppValidationError
from app.db.collections import get_appointments_col
from app.repositories.appointment_repo import AppointmentRepository
from app.services import appointment_outcomes

pytestmark = pytest.mark.integration

NOW = datetime.now(timezone.utc).replace(microsecond=0)


@pytest.fixture
async def lawyer(app_indexes):
    tag = secrets.token_hex(4)
    lid = f"LV-L-{tag}"
    yield lid
    await get_appointments_col().delete_many({"lawyer_id": lid})


async def _appt(lawyer, _id, status, start_minutes, *, expires_minutes=None):
    start = NOW + timedelta(minutes=start_minutes)
    await get_appointments_col().insert_one({
        "_id": f"{lawyer}-{_id}", "lawyer_id": lawyer, "client_id": f"{lawyer}-c", "status": status,
        "scheduled_at": start, "end_at": start + timedelta(minutes=30), "duration_minutes": 30, "mode": "video",
        "expires_at": None if expires_minutes is None else NOW + timedelta(minutes=expires_minutes),
        "occupied_slots": [f"{lawyer}-{_id}"], "schedule_version": 1, "created_at": NOW, "updated_at": NOW,
    })
    return f"{lawyer}-{_id}"


@pytest.fixture(autouse=True)
def _clear_overrides():
    from app.main import app
    yield
    app.dependency_overrides.clear()


def _as(user_id: str) -> AsyncClient:
    from app.dependencies import get_current_user
    from app.main import app
    app.dependency_overrides[get_current_user] = lambda: {"_id": user_id, "role": "lawyer"}
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api/v1")


async def test_a_meeting_is_listed_for_its_outcome_the_moment_it_ends(lawyer):
    just = await _appt(lawyer, "just", "confirmed", -31)      # ended a minute ago
    await _appt(lawyer, "live", "confirmed", -10)             # still running
    async with _as(lawyer) as c:
        now_list = (await c.get("/appointments/outcomes/pending", params={"immediate": "true"})).json()
        grace_list = (await c.get("/appointments/outcomes/pending")).json()
    assert [r["id"] for r in now_list["items"]] == [just]
    assert grace_list["items"] == [], "the reminder grace moved into the list"


async def test_a_future_cutoff_is_refused():
    with pytest.raises(AppValidationError):
        await appointment_outcomes.outstanding_outcomes(
            lawyer_id="x", cutoff=datetime.now(timezone.utc) + timedelta(hours=1))


async def test_paging_26_plus_outcomes_skips_nothing_while_some_are_recorded(lawyer):
    ids = [await _appt(lawyer, f"o{i:02d}", "confirmed", -600 + i) for i in range(30)]
    seen, cursor, first = [], None, True
    async with _as(lawyer) as c:
        while first or cursor:
            params = {"immediate": "true", "page_size": 25}
            if cursor:
                params.update(cursor)
            page = (await c.get("/appointments/outcomes/pending", params=params)).json()
            seen += [r["id"] for r in page["items"]]
            if first:
                # Outcomes recorded (here: in another tab) between pages.
                await get_appointments_col().update_many({"_id": {"$in": ids[:5]}}, {"$set": {"status": "completed"}})
            first, cursor = False, page["next_cursor"]
    assert seen == ids, "a row was skipped or repeated"


async def test_upcoming_is_confirmed_and_not_ended(lawyer):
    await _appt(lawyer, "ended", "confirmed", -120)
    live = await _appt(lawyer, "live", "confirmed", -10)
    later = await _appt(lawyer, "later", "confirmed", 600)
    await _appt(lawyer, "req", "pending", 300)
    async with _as(lawyer) as c:
        r = (await c.get("/appointments", params={"upcoming_only": "true", "page_size": 50})).json()
    assert [x["id"] for x in r["items"]] == [live, later]
    assert r["total"] == 2


async def test_all_in_the_order_it_is_worked(lawyer):
    o_new = await _appt(lawyer, "o-new", "confirmed", -60)
    o_old = await _appt(lawyer, "o-old", "confirmed", -600)
    r_late = await _appt(lawyer, "r-late", "pending", 2000, expires_minutes=900)
    r_soon = await _appt(lawyer, "r-soon", "pending", 3000, expires_minutes=60)
    u_late = await _appt(lawyer, "u-late", "confirmed", 900)
    u_soon = await _appt(lawyer, "u-soon", "confirmed", 120)
    h_old = await _appt(lawyer, "h-old", "completed", -5000)
    h_new = await _appt(lawyer, "h-new", "cancelled", -1000)
    want = [o_old, o_new, r_soon, r_late, u_soon, u_late, h_new, h_old]
    async with _as(lawyer) as c:
        r = (await c.get("/appointments", params={"order": "action", "page_size": 50})).json()
        p1 = (await c.get("/appointments", params={"order": "action", "page_size": 3, "page": 1})).json()
        p2 = (await c.get("/appointments", params={"order": "action", "page_size": 3, "page": 2})).json()
    assert [x["id"] for x in r["items"]] == want
    assert r["total"] == 8
    assert [x["id"] for x in p1["items"] + p2["items"]] == want[:6]
    assert "_rank" not in r["items"][0] and "_key" not in r["items"][0]


async def test_default_listing_is_unchanged(lawyer):
    a = await _appt(lawyer, "a", "completed", -500)
    b = await _appt(lawyer, "b", "pending", 500)
    res = await AppointmentRepository().find_for_lawyer(lawyer, None, 1, 50)
    assert [x["_id"] for x in res.items] == [a, b]


async def test_a_lapsed_request_not_yet_swept_ranks_with_history(lawyer):
    """QA 2026-10-20: lawyer_actions does not count a pending request past its
    answer-by time, so "All" must not list it as work either."""
    live = await _appt(lawyer, "live", "pending", 3000, expires_minutes=600)
    lapsed = await _appt(lawyer, "lapsed", "pending", 100, expires_minutes=-5)
    noexp = await _appt(lawyer, "noexp", "pending", 4000)
    old = await _appt(lawyer, "old", "completed", -3000)
    async with _as(lawyer) as c:
        r = (await c.get("/appointments", params={"order": "action", "page_size": 50})).json()
    ids = [x["id"] for x in r["items"]]
    assert ids[:2] == [live, noexp], "answerable requests are not first"
    assert ids[2:] == [lapsed, old], "a lapsed request was ranked as work"


async def test_an_appointment_on_a_case_this_lawyer_handles_is_a_case_meeting(lawyer):
    from app.db.collections import get_cases_col
    from app.services.appointment_service import mark_case_meetings
    await get_cases_col().insert_many([
        {"_id": f"{lawyer}-k1", "client_id": "c", "lawyer_id": lawyer, "case_number": "ATT-1", "status": "in_progress"},
        {"_id": f"{lawyer}-k2", "client_id": "c", "lawyer_id": None, "case_number": "ATT-2", "status": "open"},
    ])
    try:
        raws = [{"case_id": f"{lawyer}-k1", "lawyer_id": lawyer},        # engaged: a case meeting
                {"case_id": f"{lawyer}-k2", "lawyer_id": lawyer},        # the client's, not given to him
                {"case_id": None, "lawyer_id": lawyer}]                  # a general consultation
        rows = await mark_case_meetings([{}, {}, {}], raws)
        assert [(r["case_meeting"], r["case_number"]) for r in rows] == [(True, "ATT-1"), (False, None), (False, None)]
        await _appt(lawyer, "cm", "confirmed", 600)
        await get_appointments_col().update_one({"_id": f"{lawyer}-cm"}, {"$set": {"case_id": f"{lawyer}-k1"}})
        async with _as(lawyer) as c:
            r = (await c.get("/appointments", params={"page_size": 50})).json()
        assert [(x["case_meeting"], x["case_number"]) for x in r["items"]] == [(True, "ATT-1")]
    finally:
        await get_cases_col().delete_many({"_id": {"$in": [f"{lawyer}-k1", f"{lawyer}-k2"]}})
