"""Read receipts for appointment message threads (2026-10-19).

Lets a card say "2 new · 'hey ustad'" without opening the thread. Kept on the
server, not in the browser, so the count is right on every device.

  * `mark_read`  -- the caller has seen everything in this thread up to now.
  * `summary`    -- for up to 100 of the caller's appointments: the last
                    message (a short preview) and how many messages from the
                    OTHER party arrived after the caller last read the thread.

Only a party to the appointment gets anything; other ids are silently left
out of the summary, and `mark_read` refuses exactly as the thread itself does.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.db.collections import get_appointment_messages_col, get_appointments_col
from app.db.mongodb import get_database
from app.services.appointment_message_service import _load_participant

MAX_IDS = 100
PREVIEW = 90


def _reads():
    return get_database()["appointment_thread_reads"]


def _utc(v: datetime) -> datetime:
    return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


async def mark_read(appointment_id: str, user: dict) -> dict:
    appt, _role = await _load_participant(appointment_id, user)
    # Read up to NOW or the newest message, whichever is later: a message
    # stamped a moment ahead (clock skew) must not stay "unread" after reading.
    now = datetime.now(timezone.utc)
    newest = await get_appointment_messages_col().find_one(
        {"appointment_id": appt["_id"]}, {"created_at": 1}, sort=[("created_at", -1)])
    if newest and _utc(newest["created_at"]) > now:
        now = _utc(newest["created_at"])
    uid = str(user["_id"])
    await _reads().update_one(
        {"_id": f"{appt['_id']}:{uid}"},
        {"$set": {"appointment_id": appt["_id"], "user_id": uid, "read_at": now}},
        upsert=True)
    return {"appointment_id": appt["_id"], "read_at": now}


async def summary(ids: list[str], user: dict) -> dict:
    uid = user.get("_id")
    role = user.get("role")
    ids = [i for i in dict.fromkeys(ids or []) if i][:MAX_IDS]
    if not ids or role not in ("client", "lawyer"):
        return {"items": {}}
    side = "lawyer_id" if role == "lawyer" else "client_id"
    mine = [a["_id"] async for a in get_appointments_col().find({"_id": {"$in": ids}, side: uid}, {"_id": 1})]
    if not mine:
        return {"items": {}}

    last = {}
    async for row in get_appointment_messages_col().aggregate([
        {"$match": {"appointment_id": {"$in": mine}}},
        {"$sort": {"created_at": -1, "_id": -1}},
        {"$group": {"_id": "$appointment_id", "text": {"$first": "$text"}, "sender_id": {"$first": "$sender_id"},
                    "created_at": {"$first": "$created_at"}}},
    ]):
        last[row["_id"]] = row
    reads = {r["appointment_id"]: _utc(r["read_at"])
             async for r in _reads().find({"appointment_id": {"$in": list(last)}, "user_id": str(uid)})}

    items = {}
    for appt_id, row in last.items():
        q = {"appointment_id": appt_id, "sender_id": {"$ne": uid}}
        if appt_id in reads:
            q["created_at"] = {"$gt": reads[appt_id]}
        unread = await get_appointment_messages_col().count_documents(q, limit=99)
        text = " ".join(str(row.get("text") or "").split())
        items[appt_id] = {
            "unread": unread,
            "last": {"text": text[:PREVIEW] + ("…" if len(text) > PREVIEW else ""),
                     "from_me": row.get("sender_id") == uid,
                     "created_at": _utc(row["created_at"])},
        }
    return {"items": items}
