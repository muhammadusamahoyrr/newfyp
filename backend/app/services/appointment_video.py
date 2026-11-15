"""In-app video for a confirmed consultation, through Daily.co
(2026-10-19, APPOINTMENT_FLOW_PLAN.md, Marhala 3).

THE SAFEGUARDS (locked in the plan):

  * The API key stays on the backend. The browser only ever gets a meeting
    TOKEN for one private room, minted when someone presses Join, and it
    expires with the appointment (end + 15 minutes, at most 2 hours ahead).
    Join opens a day before the start, so both can test their camera early.
  * A room exists per appointment AND schedule version. After a move the old
    room is deleted and a new one made; a cancelled appointment's room is
    deleted, and Join refuses for anything not confirmed. Rooms also carry
    their own expiry, so a missed delete cannot leave one open for long.
  * Recording and transcription are never enabled.
  * A monthly participant-minute budget: each person's first Join for a
    schedule reserves the appointment's length + 15 minutes; when the month's budget would be passed, Join refuses and
    the paste-a-link path is the way to meet. A warning is logged at 80%.
  * No key configured -> `configured` is False and nothing here calls Daily.

Rooms are tracked in `appointment_video_rooms`, not on the appointment: the
appointment row is written only by its own state machine.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError, ServiceUnavailableError
from app.db.mongodb import get_database

logger = logging.getLogger(__name__)

JOIN_EARLY = timedelta(hours=24)        # Join opens a day before the start (2026-10-19)
# Time in the room this close to the start counts as attending (video_attended).
JOIN_MET_WINDOW = timedelta(minutes=15)
AFTER_END = timedelta(minutes=15)       # and the room lasts 15 minutes past the end
MAX_TOKEN = timedelta(hours=2)
NOT_SET_UP = "In-app video isn't set up. Use the meeting link instead."


def configured() -> bool:
    return bool((settings.daily_api_key or "").strip())


def _rooms():
    return get_database()["appointment_video_rooms"]


def _usage():
    return get_database()["video_usage"]


def _as_utc(v: datetime) -> datetime:
    return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _version(appt: dict) -> int:
    v = appt.get("schedule_version")
    return v if isinstance(v, int) and not isinstance(v, bool) else 0


def room_name(appt: dict) -> str:
    # Opaque: the appointment id is not readable from the room's URL.
    digest = hashlib.sha256(str(appt["_id"]).encode()).hexdigest()[:20]
    return f"aai-{digest}-v{_version(appt)}"


async def _daily(method: str, path: str, json: dict | None = None) -> tuple[int, dict]:
    """One call to Daily's REST API. The only place the key is used."""
    async with httpx.AsyncClient(base_url=settings.daily_api_base, timeout=10.0) as client:
        resp = await client.request(method, path, json=json, headers={
            "Authorization": f"Bearer {settings.daily_api_key}"})
    try:
        body = resp.json()
    except ValueError:
        body = {}
    return resp.status_code, body if isinstance(body, dict) else {}


async def _delete_room(name: str) -> None:
    try:
        status, _ = await _daily("DELETE", f"/rooms/{name}")
        if status not in (200, 404):
            logger.warning("video_room_delete_failed status=%s", status)
    except httpx.HTTPError as exc:
        logger.warning("video_room_delete_failed error=%s", type(exc).__name__)


async def close_room(appt_id: str) -> None:
    """Best-effort: the appointment was cancelled or moved. Never raises."""
    if not configured():
        return
    try:
        row = await _rooms().find_one({"_id": appt_id})
        if row and not row.get("deleted_at"):
            await _delete_room(row["room_name"])
            await _rooms().update_one({"_id": appt_id}, {"$set": {"deleted_at": datetime.now(timezone.utc)}})
    except Exception as exc:                       # a cancel must never fail on video
        logger.warning("video_room_close_failed error=%s", type(exc).__name__)


async def _ensure_room(appt: dict, room_exp: datetime) -> str:
    name = room_name(appt)
    row = await _rooms().find_one({"_id": appt["_id"]})
    if row and row.get("room_name") == name and not row.get("deleted_at"):
        return row["room_url"]
    if row and row.get("room_name") != name and not row.get("deleted_at"):
        await _delete_room(row["room_name"])      # the appointment moved
    try:
        status, body = await _daily("POST", "/rooms", {
            "name": name,
            "privacy": "private",
            "properties": {
                "exp": int(room_exp.timestamp()),
                "eject_at_room_exp": True,
                # The app has its own join screen (camera check); Daily's would
                # be a second "ready to join?" step.
                "enable_prejoin_ui": False,
                "enable_knocking": False,
                "max_participants": 4,
            },
        })
        if status >= 400 and "already exists" in str(body.get("info", "")):
            status, body = await _daily("GET", f"/rooms/{name}")
    except httpx.HTTPError as exc:
        logger.warning("video_room_create_failed error=%s", type(exc).__name__)
        raise ServiceUnavailableError("The video service did not answer. Try again, or use the meeting link.")
    if status >= 400 or not body.get("url"):
        logger.warning("video_room_create_failed status=%s", status)
        raise ServiceUnavailableError("The video room could not be prepared. Try again, or use the meeting link.")
    await _rooms().update_one({"_id": appt["_id"]}, {"$set": {
        "room_name": name, "room_url": body["url"], "version": _version(appt),
        "created_at": datetime.now(timezone.utc), "deleted_at": None}}, upsert=True)
    return body["url"]


async def _reserve_minutes(appt: dict, user_id: str, minutes: int, now: datetime) -> None:
    """Count this participant's minutes once per appointment version, atomically."""
    from pymongo import ReturnDocument
    from pymongo.errors import DuplicateKeyError

    budget = settings.daily_monthly_minutes_budget
    month = now.strftime("%Y-%m")
    key = f"{appt['_id']}:v{_version(appt)}:{user_id}"
    try:
        await _usage().update_one({"_id": month}, {"$setOnInsert": {"total": 0, "keys": []}}, upsert=True)
    except DuplicateKeyError:
        pass                                       # another join created the month
    res = await _usage().find_one_and_update(
        {"_id": month, "keys": {"$ne": key}, "total": {"$lte": budget - minutes}},
        {"$inc": {"total": minutes}, "$push": {"keys": key}},
        return_document=ReturnDocument.AFTER)
    if res is None:
        if await _usage().find_one({"_id": month, "keys": key}, {"_id": 1}):
            return                                 # a re-join: already counted
        logger.warning("video_budget_exhausted month=%s budget=%s", month, budget)
        raise ConflictError("This month's in-app video minutes are used up. Use the meeting link instead.")
    used = int(res.get("total", 0))
    if budget and used >= 0.8 * budget > used - minutes:
        logger.warning("video_budget_80_percent month=%s used=%s budget=%s", month, used, budget)


async def status_for(appt_id: str, user: dict) -> dict:
    """What the Join button needs: is video possible, and from when."""
    appt = await _appointment(appt_id, user)
    start, end = _as_utc(appt["scheduled_at"]), _as_utc(appt["end_at"])
    return {
        "configured": configured(),
        "eligible": str(appt.get("mode")) == "video" and str(appt.get("status")) == "confirmed",
        "opens_at": start - JOIN_EARLY,
        "closes_at": end + AFTER_END,
    }


async def _appointment(appt_id: str, user: dict) -> dict:
    from app.db.collections import get_appointments_col
    appt = await get_appointments_col().find_one({"_id": appt_id})
    uid = str(user.get("_id"))
    if not appt or uid not in (str(appt.get("client_id")), str(appt.get("lawyer_id"))):
        raise NotFoundError("Appointment")
    return appt


async def join(appt_id: str, user: dict, now: datetime | None = None) -> dict:
    """A short-lived token for this person and this appointment's room."""
    appt = await _appointment(appt_id, user)
    if not configured():
        raise ServiceUnavailableError(NOT_SET_UP)
    if str(appt.get("mode")) != "video":
        raise ConflictError("This isn't a video consultation.")
    if str(appt.get("status")) != "confirmed":
        raise ConflictError("Video opens only for a confirmed appointment.")
    now = _as_utc(now or datetime.now(timezone.utc))
    start, end = _as_utc(appt["scheduled_at"]), _as_utc(appt["end_at"])
    if now < start - JOIN_EARLY:
        raise ConflictError("Video opens a day before the appointment starts.")
    if now > end + AFTER_END:
        raise ConflictError("This appointment's time has passed.")

    room_exp = end + AFTER_END
    token_exp = min(room_exp, now + MAX_TOKEN)
    is_lawyer = str(user.get("_id")) == str(appt.get("lawyer_id"))
    # The meeting's own length (+15 min), not the token's: a Join a day early
    # must not reserve two hours that the call will never use.
    await _reserve_minutes(appt, str(user.get("_id")),
                           max(1, int((room_exp - start).total_seconds() // 60)), now)
    url = await _ensure_room(appt, room_exp)
    name = (user.get("full_name") or ("Lawyer" if is_lawyer else "Client"))[:60]
    try:
        status, body = await _daily("POST", "/meeting-tokens", {"properties": {
            "room_name": room_name(appt),
            "exp": int(token_exp.timestamp()),
            "eject_at_token_exp": True,
            "is_owner": is_lawyer,
            "user_name": name,
            # Daily records this id on the participant, so attendance can be
            # read back from Daily itself (verify_attendance).
            "user_id": str(user.get("_id"))[:36],
            "enable_prejoin_ui": False,
        }})
    except httpx.HTTPError as exc:
        logger.warning("video_token_failed error=%s", type(exc).__name__)
        raise ServiceUnavailableError("The video service did not answer. Try again, or use the meeting link.")
    if status >= 400 or not body.get("token"):
        logger.warning("video_token_failed status=%s", status)
        raise ServiceUnavailableError("Could not open the video. Try again, or use the meeting link.")
    # Nothing about attendance is recorded here (2026-10-21). A token is only
    # permission to join: the browser may never connect (daily-js fails to
    # load, the network drops, the window is closed). Attendance is read back
    # from Daily's own record of the call -- verify_attendance.
    return {"room_url": url, "token": body["token"], "expires_at": token_exp}


# ── Attendance, from Daily's record of the call (2026-10-21) ─────────────────
#
# Early completion ("It took place" before the booked end) needs evidence that
# BOTH people were really in this appointment's room, at the same time, near
# the meeting's time. It used to be written when a token was handed out, which
# proves nobody joined anything. Daily's /meetings report lists each session's
# participants with the `user_id` from their token, a join time and a duration.

def _sessions_path(appt: dict) -> str:
    since = int((_as_utc(appt["scheduled_at"]) - JOIN_MET_WINDOW).timestamp())
    return f"/meetings?room={room_name(appt)}&timeframe_start={since}&limit=100"


def _intervals(body: dict, uid: str, now: datetime) -> list[tuple[datetime, datetime]]:
    """Every stretch `uid` spent in the room, from Daily's report."""
    out = []
    for session in body.get("data") or []:
        for p in session.get("participants") or []:
            if str(p.get("user_id") or "") != uid:
                continue
            try:
                joined = datetime.fromtimestamp(float(p["join_time"]), tz=timezone.utc)
            except (KeyError, TypeError, ValueError):
                continue
            dur = p.get("duration")
            # Still in the call: Daily gives no duration until they leave.
            left = joined + timedelta(seconds=float(dur)) if dur else now
            out.append((joined, max(left, joined)))
    return out


def _overlap(appt: dict, lawyer: list, client: list) -> tuple[datetime, datetime] | None:
    """The first moment both were in the room together, inside the meeting's
    window (from 15 minutes before the start to 15 minutes after the end), as
    (lawyer's join, client's join) -- or None."""
    lo = _as_utc(appt["scheduled_at"]) - JOIN_MET_WINDOW
    hi = _as_utc(appt["end_at"]) + AFTER_END
    for l_in, l_out in lawyer:
        for c_in, c_out in client:
            together_from, together_to = max(l_in, c_in, lo), min(l_out, c_out, hi)
            if together_from < together_to:
                return l_in, c_in
    return None


async def verify_attendance(appt: dict, now: datetime | None = None) -> bool:
    """Did the lawyer and the client really meet in this room? Asks Daily and,
    when they did, records it on the appointment (`video_attended`). Fails
    closed: no key, another mode, or Daily not answering -> False, and the
    booked end remains the earliest completion."""
    from app.db.collections import get_appointments_col

    attended = appt.get("video_attended") or {}
    if attended.get("lawyer") and attended.get("client"):
        return True
    if not configured() or str(appt.get("mode")) != "video":
        return False
    now = _as_utc(now or datetime.now(timezone.utc))
    try:
        status, body = await _daily("GET", _sessions_path(appt))
    except httpx.HTTPError as exc:
        logger.warning("video_attendance_check_failed error=%s", type(exc).__name__)
        return False
    if status >= 400:
        logger.warning("video_attendance_check_failed status=%s", status)
        return False
    met = _overlap(appt,
                   _intervals(body, str(appt.get("lawyer_id")), now),
                   _intervals(body, str(appt.get("client_id")), now))
    if met is None:
        return False
    await get_appointments_col().update_one({"_id": appt["_id"]}, {"$set": {
        "video_attended": {"lawyer": met[0], "client": met[1], "verified_at": now}}})
    return True


async def check_attendance(appt_id: str, user: dict) -> dict:
    """For either party, after a call (or when the other person joins):
    whether Daily shows that both met. Writes nothing the caller chooses."""
    appt = await _appointment(appt_id, user)
    return {"video_met": await verify_attendance(appt)}
