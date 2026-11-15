"""In-app video through Daily.co (2026-10-19, Marhala 3). Daily is faked."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.db.collections import get_appointments_col
from app.db.mongodb import get_database
from app.services import appointment_video as av

pytestmark = pytest.mark.integration

CLIENT, LAWYER, OTHER = {"_id": "av-client"}, {"_id": "av-lawyer", "full_name": "Adv. Test"}, {"_id": "av-other"}
APPT = "av-appt"
START = datetime(2030, 1, 7, 5, 0, tzinfo=timezone.utc)
END = START + timedelta(minutes=30)
MONTH = START.strftime("%Y-%m")


class FakeDaily:
    def __init__(self):
        self.calls = []
        self.fail = False
        self.meetings = {"data": []}     # Daily's /meetings report

    async def __call__(self, method, path, json=None):
        self.calls.append((method, path, json))
        if self.fail:
            return 500, {}
        if method == "POST" and path == "/rooms":
            return 200, {"url": f"https://x.daily.co/{json['name']}", "name": json["name"]}
        if method == "POST" and path == "/meeting-tokens":
            return 200, {"token": "tok-" + json["properties"]["room_name"]}
        if method == "GET" and path.startswith("/meetings"):
            return 200, self.meetings
        return 200, {}


@pytest.fixture(autouse=True)
async def _setup(mongo, monkeypatch):
    monkeypatch.setattr(settings, "daily_api_key", "test-key")
    monkeypatch.setattr(settings, "daily_monthly_minutes_budget", 1000)
    fake = FakeDaily()
    monkeypatch.setattr(av, "_daily", fake)
    db = get_database()
    await get_appointments_col().delete_many({"_id": APPT})
    await get_appointments_col().insert_one({
        "_id": APPT, "client_id": CLIENT["_id"], "lawyer_id": LAWYER["_id"], "status": "confirmed",
        "mode": "video", "scheduled_at": START, "end_at": END, "schedule_version": 0})
    await db["appointment_video_rooms"].delete_many({"_id": APPT})
    await db["video_usage"].delete_many({"_id": MONTH})
    yield fake
    await get_appointments_col().delete_many({"_id": APPT})
    await db["appointment_video_rooms"].delete_many({"_id": APPT})
    await db["video_usage"].delete_many({"_id": MONTH})


async def _set(**fields):
    await get_appointments_col().update_one({"_id": APPT}, {"$set": fields})


async def test_join_gives_a_short_token_for_a_private_room_without_recording(_setup):
    out = await av.join(APPT, LAWYER, now=START - timedelta(minutes=5))
    assert out["token"].startswith("tok-aai-") and out["room_url"].startswith("https://x.daily.co/aai-")
    assert out["expires_at"] == END + av.AFTER_END
    room = next(c[2] for c in _setup.calls if c[1] == "/rooms")
    assert room["privacy"] == "private"
    assert not any("record" in k or "transcri" in k for k in room["properties"])
    assert APPT not in room["name"], "the room name must not reveal the appointment id"
    token = next(c[2] for c in _setup.calls if c[1] == "/meeting-tokens")["properties"]
    assert token["is_owner"] is True and "enable_recording" not in token
    assert token["user_id"] == LAWYER["_id"], "Daily must be able to say who was in the call"


async def test_the_client_joins_the_same_room_not_as_owner(_setup):
    await av.join(APPT, LAWYER, now=START)
    await av.join(APPT, CLIENT, now=START)
    rooms = [c for c in _setup.calls if c[1] == "/rooms"]
    assert len(rooms) == 1, "one room per appointment"
    owners = [c[2]["properties"]["is_owner"] for c in _setup.calls if c[1] == "/meeting-tokens"]
    assert owners == [True, False]


async def test_no_key_means_no_video_and_no_call_to_daily(_setup, monkeypatch):
    monkeypatch.setattr(settings, "daily_api_key", "")
    assert (await av.status_for(APPT, CLIENT))["configured"] is False
    with pytest.raises(HTTPException) as e:
        await av.join(APPT, CLIENT, now=START)
    assert e.value.status_code == 503 and _setup.calls == []


@pytest.mark.parametrize("when,ok", [(-24 * 60 - 1, False), (-24 * 60, True), (45, True), (46, False)])
async def test_join_opens_a_day_early_and_closes_15_after(when, ok):
    call = av.join(APPT, CLIENT, now=START + timedelta(minutes=when))
    if ok:
        await call
    else:
        with pytest.raises(HTTPException) as e:
            await call
        assert e.value.status_code == 409


@pytest.mark.parametrize("fields", [{"status": "pending"}, {"status": "cancelled"}, {"mode": "in_person"}])
async def test_only_a_confirmed_video_appointment(fields):
    await _set(**fields)
    with pytest.raises(HTTPException) as e:
        await av.join(APPT, CLIENT, now=START)
    assert e.value.status_code == 409


async def test_strangers_get_not_found(_setup):
    for call in (av.join(APPT, OTHER, now=START), av.status_for(APPT, OTHER)):
        with pytest.raises(HTTPException) as e:
            await call
        assert e.value.status_code == 404
    assert _setup.calls == []


async def test_a_moved_appointment_gets_a_new_room_and_the_old_one_is_deleted(_setup):
    await av.join(APPT, CLIENT, now=START)
    old = next(c[2]["name"] for c in _setup.calls if c[1] == "/rooms")
    await _set(schedule_version=1)
    await av.join(APPT, CLIENT, now=START)
    assert ("DELETE", f"/rooms/{old}", None) in _setup.calls
    names = [c[2]["name"] for c in _setup.calls if c[1] == "/rooms"]
    assert len(names) == 2 and names[1].endswith("-v1")


async def test_close_room_deletes_and_never_raises(_setup):
    await av.join(APPT, CLIENT, now=START)
    _setup.fail = True
    await av.close_room(APPT)                       # Daily failing must not raise
    row = await get_database()["appointment_video_rooms"].find_one({"_id": APPT})
    assert row["deleted_at"] is not None
    assert any(c[0] == "DELETE" for c in _setup.calls)


async def test_the_monthly_budget_refuses_new_joins_but_counts_a_rejoin_once(monkeypatch):
    monkeypatch.setattr(settings, "daily_monthly_minutes_budget", 50)
    await av.join(APPT, CLIENT, now=START)          # reserves 30 + 15 = 45 minutes
    await av.join(APPT, CLIENT, now=START)          # re-join: not counted again
    usage = await get_database()["video_usage"].find_one({"_id": MONTH})
    assert usage["total"] == 45
    with pytest.raises(HTTPException) as e:
        await av.join(APPT, LAWYER, now=START)
    assert e.value.status_code == 409 and "used up" in e.value.detail


async def test_daily_failing_is_a_clear_503(_setup):
    _setup.fail = True
    with pytest.raises(HTTPException) as e:
        await av.join(APPT, CLIENT, now=START)
    assert e.value.status_code == 503 and "meeting link" in e.value.detail


def test_a_reminder_says_when_a_video_consultation_has_no_link_yet():
    from app.services.appointment_reminders import _body
    assert "hasn't added a meeting link" in _body("24h", "Mon 10:00", "Adv. X", True, True)
    assert "Add one from the appointment" in _body("24h", "Mon 10:00", "Client", False, True)
    assert "link" not in _body("24h", "Mon 10:00", "Adv. X", True, False)


async def test_the_single_process_lock_is_opt_in_and_exclusive(monkeypatch):
    from app.core import redis_client
    monkeypatch.setattr(redis_client, "get_redis", lambda: None)
    monkeypatch.setattr(redis_client, "_LOCAL_LOCKS", {})
    monkeypatch.setattr(settings, "scheduler_single_process", False)
    assert await redis_client.acquire_period_lock_strict("k", 60, "j") is False, "fails closed by default"
    monkeypatch.setattr(settings, "scheduler_single_process", True)
    assert await redis_client.acquire_period_lock_strict("k", 60, "j") is True
    assert await redis_client.acquire_period_lock_strict("k", 60, "j") is False, "held for its period"


async def test_an_early_join_reserves_the_meeting_not_the_token(_setup):
    """A Join a day before still counts the meeting's length + 15, once."""
    await av.join(APPT, CLIENT, now=START - timedelta(hours=20))
    await av.join(APPT, CLIENT, now=START)
    usage = await get_database()["video_usage"].find_one({"_id": MONTH})
    assert usage["total"] == 45


# ── who met (2026-10-21): read from Daily's record of the call, not from Join ──

def _p(uid, joined, minutes=None):
    """One participant row as Daily's /meetings report gives it."""
    row = {"user_id": uid, "join_time": joined.timestamp()}
    if minutes is not None:
        row["duration"] = minutes * 60
    return row


async def _row():
    return await get_appointments_col().find_one({"_id": APPT})


async def test_asking_for_a_token_records_no_attendance(_setup):
    await av.join(APPT, LAWYER, now=START)
    await av.join(APPT, CLIENT, now=START)
    row = await _row()
    from app.services.appointment_service import video_met
    assert not row.get("video_attended") and not row.get("video_joined")
    assert video_met(row) is False, "a token is not a meeting"


async def test_both_in_the_room_together_is_recorded_from_daily(_setup):
    _setup.meetings = {"data": [{"participants": [
        _p(LAWYER["_id"], START - timedelta(minutes=5), 20),
        _p(CLIENT["_id"], START + timedelta(minutes=2), 15)]}]}
    assert await av.verify_attendance(await _row(), now=START + timedelta(minutes=20)) is True
    row = await _row()
    from app.services.appointment_service import video_met
    assert video_met(row) is True
    assert row["video_attended"]["client"].replace(tzinfo=timezone.utc) == START + timedelta(minutes=2)
    assert any(c[0] == "GET" and c[1].startswith("/meetings?room=aai-") for c in _setup.calls)


async def test_someone_still_in_the_call_counts_until_now(_setup):
    _setup.meetings = {"data": [{"ongoing": True, "participants": [
        _p(LAWYER["_id"], START), _p(CLIENT["_id"], START + timedelta(minutes=1))]}]}
    assert await av.verify_attendance(await _row(), now=START + timedelta(minutes=5)) is True


@pytest.mark.parametrize("people", [
    # only the lawyer came
    [("L", 0, 30)],
    # never at the same time: the lawyer left before the client arrived
    [("L", 0, 5), ("C", 10, 10)],
    # together, but a day early (camera test), not at the meeting
    [("L", -24 * 60, 10), ("C", -24 * 60, 10)],
    # someone else in the room is not the client
    [("L", 0, 20), ("X", 0, 20)],
])
async def test_no_meeting_is_recorded_without_both_together_near_the_time(_setup, people):
    ids = {"L": LAWYER["_id"], "C": CLIENT["_id"], "X": OTHER["_id"]}
    _setup.meetings = {"data": [{"participants": [
        _p(ids[who], START + timedelta(minutes=at), mins) for who, at, mins in people]}]}
    assert await av.verify_attendance(await _row(), now=START + timedelta(minutes=25)) is False
    assert not (await _row()).get("video_attended")


async def test_daily_not_answering_fails_closed(_setup):
    _setup.fail = True
    assert await av.verify_attendance(await _row(), now=START + timedelta(minutes=10)) is False
    assert not (await _row()).get("video_attended")


async def test_no_key_means_no_attendance_and_no_call(_setup, monkeypatch):
    monkeypatch.setattr(settings, "daily_api_key", "")
    assert await av.verify_attendance(await _row()) is False
    assert not any(c[1].startswith("/meetings") for c in _setup.calls)


async def test_a_stranger_cannot_ask(_setup):
    with pytest.raises(HTTPException):
        await av.check_attendance(APPT, OTHER)


async def test_completion_before_the_end_needs_both_to_have_met():
    from app.core.constants import AppointmentStatus
    from app.services import appointment_transitions as tr
    mid = START + timedelta(minutes=10)
    assert tr.timing_error(AppointmentStatus.COMPLETED, scheduled_at=START, end_at=END, now=mid), "completed early without meeting"
    assert tr.timing_error(AppointmentStatus.COMPLETED, scheduled_at=START, end_at=END, now=mid, met=True) is None
    assert tr.timing_error(AppointmentStatus.COMPLETED, scheduled_at=START, end_at=END,
                           now=START - timedelta(minutes=5), met=True), "completed before it even started"


async def test_the_appointment_response_says_whether_they_met():
    from app.services.appointment_service import _sanitize
    assert _sanitize({"_id": "x", "video_attended": {"lawyer": START}})["video_met"] is False
    assert _sanitize({"_id": "x", "video_attended": {"lawyer": START, "client": START}})["video_met"] is True
    # The old token-time record proves nothing and no longer counts.
    assert _sanitize({"_id": "x", "video_joined": {"lawyer": START, "client": START}})["video_met"] is False
    assert "video_attended" not in _sanitize({"_id": "x", "video_attended": {"lawyer": START, "client": START}}), "join times leaked"


async def test_a_meeting_from_a_proposal_is_flagged_without_its_id():
    from app.services.appointment_service import _sanitize
    out = _sanitize({"_id": "x", "proposal_id": "P1", "notes": "Agenda"})
    assert out["from_proposal"] is True and "proposal_id" not in out
    assert _sanitize({"_id": "y", "notes": "Mine"})["from_proposal"] is False


# ── completing before the booked end asks Daily, server-side (2026-10-21) ────

LIVE = "av-appt-live"


@pytest.fixture
async def live_appt(_setup):
    """A video consultation happening right now (the real clock)."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=10)
    await get_appointments_col().delete_many({"_id": LIVE})
    await get_appointments_col().insert_one({
        "_id": LIVE, "client_id": CLIENT["_id"], "lawyer_id": LAWYER["_id"], "status": "confirmed",
        "mode": "video", "scheduled_at": start, "end_at": start + timedelta(minutes=60),
        "duration_minutes": 60, "schedule_version": 0})
    yield start
    await get_appointments_col().delete_many({"_id": LIVE})
    await get_database()["notifications"].delete_many({"payload.appointment_id": LIVE})


async def test_early_completion_is_refused_when_daily_shows_no_meeting(live_appt):
    from app.core.exceptions import AppValidationError
    from app.services import appointment_service as svc
    with pytest.raises(AppValidationError, match="not finished yet"):
        await svc.complete_appointment(LIVE, LAWYER["_id"], None, None)
    assert (await get_appointments_col().find_one({"_id": LIVE}))["status"] == "confirmed"


async def test_early_completion_works_when_daily_shows_both_met(live_appt, _setup):
    from app.services import appointment_service as svc
    _setup.meetings = {"data": [{"participants": [
        _p(LAWYER["_id"], live_appt, 8), _p(CLIENT["_id"], live_appt + timedelta(minutes=1), 7)]}]}
    out = await svc.complete_appointment(LIVE, LAWYER["_id"], "Advice given.", None)
    assert out["status"] == "completed" and out["video_met"] is True
