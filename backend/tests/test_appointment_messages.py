"""Appointment-scoped messages (2026-10-12): access, lifecycle, validation,
ordering, idempotency and notification. See appointment_message_service."""
from __future__ import annotations

import asyncio
import secrets
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.exceptions import AppValidationError, ConflictError, ForbiddenError

pytestmark = pytest.mark.integration


@pytest.fixture
async def world(app_indexes):
    from app.db.collections import (get_appointment_messages_col, get_appointments_col,
                                    get_notifications_col, get_users_col)
    tag = secrets.token_hex(4)
    ids = {k: f"AM-{k}-{tag}" for k in ("client", "lawyer", "client2", "lawyer2", "admin")}
    now = datetime.now(timezone.utc)
    lp = {"kyc_verified": True, "specializations": ["civil"], "availability": True}
    await get_users_col().insert_many([
        {"_id": ids["client"], "role": "client", "full_name": "Client One", "email": f"c1-{tag}@t.invalid", "is_active": True},
        {"_id": ids["client2"], "role": "client", "full_name": "Client Two", "email": f"c2-{tag}@t.invalid", "is_active": True},
        {"_id": ids["lawyer"], "role": "lawyer", "full_name": "Adv One", "email": f"l1-{tag}@t.invalid", "is_active": True, "lawyer_profile": lp},
        {"_id": ids["lawyer2"], "role": "lawyer", "full_name": "Adv Two", "email": f"l2-{tag}@t.invalid", "is_active": True, "lawyer_profile": lp},
        {"_id": ids["admin"], "role": "admin", "full_name": "Admin", "email": f"a-{tag}@t.invalid", "is_active": True},
    ])
    yield ids
    users = list(ids.values())
    appts = [a["_id"] async for a in get_appointments_col().find({"client_id": {"$in": users}}, {"_id": 1})]
    await get_appointment_messages_col().delete_many({"appointment_id": {"$in": appts}})
    await get_appointments_col().delete_many({"_id": {"$in": appts}})
    await get_notifications_col().delete_many({"user_id": {"$in": users}})
    await get_users_col().delete_many({"_id": {"$in": users}})


async def _appt(w, status="confirmed", hours=48):
    from app.db.collections import get_appointments_col
    start = (datetime.now(timezone.utc) + timedelta(hours=hours)).replace(minute=0, second=0, microsecond=0)
    _id = secrets.token_urlsafe(10)
    await get_appointments_col().insert_one({
        "_id": _id, "client_id": w["client"], "lawyer_id": w["lawyer"], "case_id": None,
        "scheduled_at": start, "end_at": start + timedelta(hours=1), "duration_minutes": 60,
        "status": status, "mode": "video", "schedule_version": 0, "notes": None,
        "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)})
    return _id


def _user(w, who):
    return {"_id": w[who], "role": "admin" if who == "admin" else ("lawyer" if who.startswith("lawyer") else "client")}


async def _send(w, appt_id, who, text="Hello", key=None):
    from app.services import appointment_message_service as svc
    return await svc.send_message(appt_id, _user(w, who), text, key or f"key-{secrets.token_hex(6)}")


async def _list(w, appt_id, who, **kw):
    from app.services import appointment_message_service as svc
    return await svc.list_messages(appt_id, _user(w, who), **kw)


async def _notices(user_id):
    from app.db.collections import get_notifications_col
    return [n async for n in get_notifications_col().find({"user_id": user_id, "type": "appointment_message"})]


# ── access ──

async def test_both_participants_read_and_send(world):
    a = await _appt(world)
    await _send(world, a, "client", "Running 10 minutes late")
    await _send(world, a, "lawyer", "No problem")
    page = await _list(world, a, "client")
    assert [m["text"] for m in page["items"]] == ["Running 10 minutes late", "No problem"]
    assert [m["sender_role"] for m in page["items"]] == ["client", "lawyer"]
    assert page["items"][0]["from_me"] is True and page["items"][1]["from_me"] is False
    assert page["can_send"] is True and page["send_state"] == "open"
    lawyer_view = await _list(world, a, "lawyer")
    assert lawyer_view["items"][1]["from_me"] is True


@pytest.mark.parametrize("who", ["client2", "lawyer2", "admin"])
async def test_anyone_else_is_refused(world, who):
    a = await _appt(world)
    with pytest.raises(ForbiddenError):
        await _list(world, a, who)
    with pytest.raises(ForbiddenError):
        await _send(world, a, who)


async def test_an_unknown_appointment_is_refused_like_a_foreign_one(world):
    with pytest.raises(ForbiddenError):
        await _list(world, "no-such-appointment", "client")


# ── lifecycle ──

async def test_a_pending_request_is_not_writable(world):
    a = await _appt(world, status="pending")
    page = await _list(world, a, "client")
    assert page["can_send"] is False and page["send_state"] == "awaiting_confirmation"
    with pytest.raises(ConflictError, match="once the lawyer confirms"):
        await _send(world, a, "client")


@pytest.mark.parametrize("status", ["completed", "cancelled", "no_show", "expired"])
async def test_an_ended_appointment_keeps_its_history_read_only(world, status):
    from app.db.collections import get_appointments_col
    a = await _appt(world)
    await _send(world, a, "client", "Before it ended")
    await get_appointments_col().update_one({"_id": a}, {"$set": {"status": status}})
    page = await _list(world, a, "lawyer")
    assert [m["text"] for m in page["items"]] == ["Before it ended"]
    assert page["can_send"] is False and page["send_state"] == "read_only"
    with pytest.raises(ConflictError, match="closed"):
        await _send(world, a, "lawyer")


async def test_a_rescheduled_appointment_keeps_its_thread(world):
    from app.services import appointment_service
    from app.db.collections import get_appointments_col
    a = await _appt(world, status="pending")
    new_time = (datetime.now(timezone.utc) + timedelta(hours=96)).replace(minute=0, second=0, microsecond=0)
    moved = await appointment_service.reschedule_appointment(a, world["client"], new_time, expected_version=0)
    assert moved["id"] == a
    await get_appointments_col().update_one({"_id": a}, {"$set": {"status": "confirmed"}})
    await _send(world, a, "lawyer", "See you at the new time")
    assert [m["text"] for m in (await _list(world, a, "client"))["items"]] == ["See you at the new time"]


# ── validation ──

def test_empty_and_overlong_messages_are_refused():
    from pydantic import ValidationError
    from app.schemas.appointment_message import AppointmentMessageCreate, MAX_MESSAGE_LENGTH
    with pytest.raises(ValidationError):
        AppointmentMessageCreate(text="   \n ", idempotency_key="k" * 10)
    with pytest.raises(ValidationError):
        AppointmentMessageCreate(text="x" * (MAX_MESSAGE_LENGTH + 1), idempotency_key="k" * 10)
    ok = AppointmentMessageCreate(text="  hi there \n", idempotency_key="k" * 10)
    assert ok.text == "hi there"
    with pytest.raises(ValidationError):
        AppointmentMessageCreate(text="hi", idempotency_key="k" * 10, sender_id="someone-else")


# ── order, paging ──

async def test_pages_are_stable_and_read_older_with_the_cursor(world):
    a = await _appt(world)
    for i in range(5):
        await _send(world, a, "client", f"m{i}")
    first = await _list(world, a, "client", page_size=2)
    assert [m["text"] for m in first["items"]] == ["m3", "m4"]
    cur = first["next_cursor"]
    second = await _list(world, a, "client", page_size=2, before_created_at=cur["before_created_at"], before_id=cur["before_id"])
    assert [m["text"] for m in second["items"]] == ["m1", "m2"]
    with pytest.raises(AppValidationError):
        await _list(world, a, "client", before_id="x")


# ── idempotency and notification ──

async def test_a_retried_send_stores_one_message_and_one_notice(world):
    a = await _appt(world)
    first = await _send(world, a, "client", "Link not working", key="retry-key-1")
    again = await _send(world, a, "client", "Link not working", key="retry-key-1")
    assert again["id"] == first["id"] and again["replayed"] is True
    assert len((await _list(world, a, "lawyer"))["items"]) == 1
    notes = await _notices(world["lawyer"])
    assert len(notes) == 1
    assert notes[0]["payload"]["appointment_id"] == a
    assert "Link not working" not in notes[0]["body"], "message text leaked into the notification"
    assert await _notices(world["client"]) == [], "the sender was notified of their own message"
    with pytest.raises(ConflictError, match="different message"):
        await _send(world, a, "client", "Something else", key="retry-key-1")


async def test_racing_sends_with_one_key_store_one_message(world):
    a = await _appt(world)
    results = await asyncio.gather(*[_send(world, a, "lawyer", "Same", key="race-key-1") for _ in range(4)],
                                   return_exceptions=True)
    ids = {r["id"] for r in results if isinstance(r, dict)}
    assert len(ids) == 1
    assert len((await _list(world, a, "client"))["items"]) == 1
    assert len(await _notices(world["client"])) == 1


# ── the HTTP boundary ──

def _http(user):
    from app.main import app
    from app.dependencies import get_current_user
    app.dependency_overrides.clear()
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api/v1")


async def test_the_routes_authenticate_and_never_take_the_sender_from_the_body(world):
    from app.main import app
    a = await _appt(world)
    async with _http(None) as c:
        anon = await c.get(f"/appointments/{a}/messages")
    async with _http({**_user(world, "client"), "is_active": True}) as c:
        forged = await c.post(f"/appointments/{a}/messages",
                              json={"text": "hi", "idempotency_key": "forge-key-1", "sender_id": world["lawyer"]})
        sent = await c.post(f"/appointments/{a}/messages", json={"text": "hi", "idempotency_key": "real-key-1"})
        empty = await c.post(f"/appointments/{a}/messages", json={"text": "  ", "idempotency_key": "real-key-2"})
        page = await c.get(f"/appointments/{a}/messages")
    async with _http({**_user(world, "client2"), "is_active": True}) as c:
        other = await c.get(f"/appointments/{a}/messages")
    app.dependency_overrides.clear()
    assert anon.status_code == 401
    assert forged.status_code == 422, "an unknown field naming the sender was accepted"
    assert sent.status_code == 201 and sent.json()["sender_id"] == world["client"] and sent.json()["sender_role"] == "client"
    assert empty.status_code == 422
    assert page.status_code == 200 and page.json()["can_send"] is True
    assert other.status_code == 403


# ── the notice is durable (2026-10-12) ──

async def _marker(msg_id):
    from app.db.collections import get_appointment_messages_col
    return (await get_appointment_messages_col().find_one({"_id": msg_id}))["notify"]


async def test_a_notice_that_failed_is_delivered_once_by_the_next_read(world, monkeypatch):
    from app.services import notification_service
    real = notification_service.create_notification

    async def down(**kw):
        raise RuntimeError("notifications down")
    monkeypatch.setattr(notification_service, "create_notification", down)
    a = await _appt(world)
    sent = await _send(world, a, "client", "Running late")
    assert sent["replayed"] is False, "the send must not fail because its notice did"
    assert await _marker(sent["id"]) == "pending"
    assert await _notices(world["lawyer"]) == []

    monkeypatch.setattr(notification_service, "create_notification", real)
    await _list(world, a, "client")
    await _list(world, a, "lawyer")
    assert len(await _notices(world["lawyer"])) == 1
    assert await _marker(sent["id"]) == "sent"


async def test_the_next_send_delivers_what_an_earlier_send_still_owes(world, monkeypatch):
    from app.services import notification_service
    real = notification_service.create_notification
    calls = {"n": 0}

    async def first_fails(**kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("blip")
        return await real(**kw)
    monkeypatch.setattr(notification_service, "create_notification", first_fails)
    a = await _appt(world)
    one = await _send(world, a, "client", "First")
    await _send(world, a, "client", "Second")
    notes = await _notices(world["lawyer"])
    assert sorted(n["payload"]["message_id"] for n in notes) == sorted([one["id"], (await _list(world, a, "lawyer"))["items"][1]["id"]])
    assert await _marker(one["id"]) == "sent"


async def test_a_crash_after_the_notice_but_before_marking_does_not_notify_twice(world, monkeypatch):
    from app.services import appointment_message_service as svc
    real_mark = svc._mark_notified

    async def crash(msg):
        return None
    monkeypatch.setattr(svc, "_mark_notified", crash)
    a = await _appt(world)
    sent = await _send(world, a, "lawyer", "See you")
    assert await _marker(sent["id"]) == "pending"
    monkeypatch.setattr(svc, "_mark_notified", real_mark)
    await _list(world, a, "client")
    await _list(world, a, "lawyer")
    assert len(await _notices(world["client"])) == 1
    assert await _marker(sent["id"]) == "sent"


# ── a send racing the appointment's end ──

async def test_a_send_that_loses_the_race_to_a_cancel_stores_nothing(world, monkeypatch):
    """The participant check read the appointment while it was confirmed; it
    was cancelled before the write. The transactional write must refuse."""
    from app.db.collections import get_appointment_messages_col, get_appointments_col
    from app.services import appointment_message_service as svc
    a = await _appt(world)
    stale = await get_appointments_col().find_one({"_id": a})
    await get_appointments_col().update_one({"_id": a}, {"$set": {"status": "cancelled"}})

    async def stale_read(_id):
        return dict(stale)
    monkeypatch.setattr(svc.appt_repo, "find_by_id", stale_read)
    with pytest.raises(ConflictError, match="closed"):
        await _send(world, a, "client", "Too late")
    assert await get_appointment_messages_col().count_documents({"appointment_id": a}) == 0
    assert await _notices(world["lawyer"]) == []


async def test_a_stored_message_is_ordered_on_the_appointment(world):
    from app.db.collections import get_appointments_col
    a = await _appt(world)
    sent = await _send(world, a, "client", "Hi")
    row = await get_appointments_col().find_one({"_id": a})
    assert row["status"] == "confirmed"
    assert row["last_message_at"] is not None and sent["id"]
