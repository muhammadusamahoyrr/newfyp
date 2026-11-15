"""POST /cases/{id}/hearings/{hid}/cancel, over HTTP (2026-10-19).

A hearing entered by mistake could not be taken off the schedule: there was no
way to remove one at all. Cancelling takes an UPCOMING hearing (no outcome)
off the schedule, keeps a copy on the case with when and why, and tells the
client. A hearing with an outcome is part of what happened and stays.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration


def _day(n: int) -> datetime:
    d = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return d + timedelta(days=n)


@pytest.fixture
async def case(app_indexes):
    from app.db.collections import get_cases_col, get_notifications_col

    tag = secrets.token_hex(4)
    ids = {"case": f"HC-C-{tag}", "lawyer": f"HC-L-{tag}", "other": f"HC-O-{tag}", "client": f"HC-CL-{tag}"}
    await get_cases_col().insert_one({
        "_id": ids["case"], "title": "Rent dispute", "client_id": ids["client"], "lawyer_id": ids["lawyer"],
        "status": "in_progress", "case_type": "civil", "province": "punjab", "description": "x",
        "created_at": datetime.now(timezone.utc),
        "hearing_dates": [
            {"_id": "h-up", "date": _day(10), "time": "10:00", "court": "Civil Court Lahore", "purpose": "Framing of issues", "outcome": None},
            {"_id": "h-done", "date": _day(-5), "time": "10:00", "court": "Civil Court Lahore", "purpose": "Issues", "outcome": "adjourned"},
        ],
    })
    yield ids
    await get_cases_col().delete_one({"_id": ids["case"]})
    await get_notifications_col().delete_many({"user_id": ids["client"]})


@pytest.fixture(autouse=True)
def _clear_overrides():
    from app.main import app
    yield
    app.dependency_overrides.clear()


def _as_lawyer(user_id: str) -> AsyncClient:
    from app.dependencies import get_current_user, require_lawyer
    from app.main import app

    who = {"_id": user_id, "role": "lawyer"}
    app.dependency_overrides[get_current_user] = lambda: who
    app.dependency_overrides[require_lawyer] = lambda: who
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api/v1")


def _url(case, hid="h-up"):
    return f"/cases/{case['case']}/hearings/{hid}/cancel"


async def test_the_assigned_lawyer_cancels_and_a_copy_is_kept(case):
    from app.db.collections import get_cases_col, get_notifications_col

    async with _as_lawyer(case["lawyer"]) as c:
        resp = await c.post(_url(case), json={"reason": "Entered by mistake"})
    assert resp.status_code == 200, resp.text
    assert [h["_id"] for h in resp.json()["hearing_dates"]] == ["h-done"]

    stored = await get_cases_col().find_one({"_id": case["case"]})
    assert [h["_id"] for h in stored["hearing_dates"]] == ["h-done"]
    kept = stored["cancelled_hearings"]
    assert len(kept) == 1 and kept[0]["_id"] == "h-up"
    assert kept[0]["cancel_reason"] == "Entered by mistake"
    assert kept[0]["purpose"] == "Framing of issues" and kept[0]["cancelled_at"]

    note = await get_notifications_col().find_one({"user_id": case["client"]})
    assert note is not None, "the client was not told"
    assert "cancelled" in note["body"] and "Entered by mistake" in note["body"]


async def test_a_repeat_cancel_is_not_an_error_and_changes_nothing(case):
    from app.db.collections import get_cases_col, get_notifications_col

    async with _as_lawyer(case["lawyer"]) as c:
        first = await c.post(_url(case), json={})
        again = await c.post(_url(case), json={})
    assert first.status_code == 200 and again.status_code == 200, again.text
    stored = await get_cases_col().find_one({"_id": case["case"]})
    assert len(stored["cancelled_hearings"]) == 1
    assert await get_notifications_col().count_documents({"user_id": case["client"]}) == 1


async def test_another_lawyer_cannot_cancel(case):
    async with _as_lawyer(case["other"]) as c:
        resp = await c.post(_url(case), json={})
    assert resp.status_code == 403


async def test_a_hearing_with_an_outcome_cannot_be_cancelled(case):
    from app.db.collections import get_cases_col

    async with _as_lawyer(case["lawyer"]) as c:
        resp = await c.post(_url(case, "h-done"), json={})
    assert resp.status_code == 409
    assert "outcome" in resp.text
    stored = await get_cases_col().find_one({"_id": case["case"]})
    assert len(stored["hearing_dates"]) == 2


async def test_unknown_hearing_is_404(case):
    async with _as_lawyer(case["lawyer"]) as c:
        resp = await c.post(_url(case, "nope"), json={})
    assert resp.status_code == 404


@pytest.mark.parametrize("body", [
    {"reason": "x" * 301},           # too long
    {"lawyer_id": "x"},              # unknown field
])
async def test_invalid_bodies_are_refused(case, body):
    async with _as_lawyer(case["lawyer"]) as c:
        resp = await c.post(_url(case), json=body)
    assert resp.status_code == 422, resp.text


async def test_a_closed_case_cannot_have_hearings_cancelled(case):
    from app.db.collections import get_cases_col

    await get_cases_col().update_one({"_id": case["case"]}, {"$set": {"status": "closed"}})
    async with _as_lawyer(case["lawyer"]) as c:
        resp = await c.post(_url(case), json={})
    assert resp.status_code in (403, 409), resp.text
    stored = await get_cases_col().find_one({"_id": case["case"]})
    assert len(stored["hearing_dates"]) == 2
