"""Appointment-scoped messages (2026-10-12).

Before a lawyer is hired, the client and lawyer had no way to reach each other
about a consultation: the cancellation cutoff told a client to "contact your
lawyer" and nothing let them. This is a small thread for ONE appointment.

ACCESS. Only that appointment's own client and lawyer -- matched against the
stored `client_id` / `lawyer_id`. Not admins (unlike the appointment record:
these are private words between two people), not other parties. A thread that
is not yours and a thread that does not exist are refused the same way (403),
the appointment API's existing policy, so ids cannot be probed.

LIFECYCLE. One rule, `thread_state`, read by both the listing (to tell the UI)
and the send (to enforce): writable only while the appointment is CONFIRMED;
read-only once it is completed, cancelled, a no-show or expired; not yet open
while it is a pending request. A reschedule keeps the same appointment id and
so the same thread.

SENDING is retry-safe: the client sends an idempotency key, unique per
(appointment, sender, key) in the database, and a retry -- or a race between
two -- returns the one stored message. The other participant is notified once
per message (a logical event id), without the message text.

SEND vs. AN ENDING APPOINTMENT. The lifecycle check and the insert run in ONE
transaction that first writes the appointment itself, conditional on it still
being confirmed. A cancel/complete that commits first makes that write match
nothing and the send is refused; one that comes after waits on the
transaction, so the message is ordered before the ending. No message can be
stored against an appointment that had already ended.

THE NOTICE IS DURABLE. A message is stored with `notify: "pending"` and marked
"sent" once its notice exists. If the process dies in between, the next read
or send of that thread delivers what is still owed; the logical event id makes
a second delivery of the same notice a no-op.
"""
import logging
import secrets
from datetime import datetime, timezone

from pymongo import DESCENDING
from pymongo.errors import DuplicateKeyError

from app.core.constants import AppointmentStatus, NotificationType
from app.core.exceptions import AppValidationError, ConflictError, ForbiddenError, ServiceUnavailableError
from app.db.collections import get_appointment_messages_col, get_appointments_col
from app.repositories.appointment_repo import AppointmentRepository
from app.repositories.user_repo import UserRepository

logger = logging.getLogger(__name__)

appt_repo = AppointmentRepository()
user_repo = UserRepository()

DEFAULT_PAGE_SIZE = 30
#: Owed notices delivered per thread read/send; the rest wait for the next one.
PENDING_NOTICE_BATCH = 20
_TXN_UNAVAILABLE = "Messages are unavailable on this server right now. Nothing was sent."
MAX_PAGE_SIZE = 100
_DENIED = "You do not have access to this appointment."
_READ_ONLY = {
    AppointmentStatus.COMPLETED.value, AppointmentStatus.CANCELLED.value,
    AppointmentStatus.NO_SHOW.value, AppointmentStatus.EXPIRED.value,
}


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def thread_state(appt: dict) -> dict:
    """THE lifecycle rule, for both reading and sending."""
    status = str(appt.get("status") or "")
    if status == AppointmentStatus.CONFIRMED.value:
        return {"can_send": True, "send_state": "open", "appointment_status": status}
    if status == AppointmentStatus.PENDING.value:
        return {"can_send": False, "send_state": "awaiting_confirmation", "appointment_status": status}
    # Terminal, or a status this build does not know: readable, never writable.
    return {"can_send": False, "send_state": "read_only", "appointment_status": status}


async def _load_participant(appointment_id: str, user: dict) -> tuple[dict, str]:
    """The appointment and the caller's role in it, or one indistinguishable refusal."""
    role = user.get("role")
    uid = user.get("_id")
    appt = await appt_repo.find_by_id(appointment_id) if appointment_id else None
    if (not appt or role not in ("client", "lawyer")
            or (role == "client" and appt.get("client_id") != uid)
            or (role == "lawyer" and appt.get("lawyer_id") != uid)):
        logger.info("appointment_message_access_denied role=%s reason=%s",
                    role, "not_a_party" if appt else "no_such_appointment")
        raise ForbiddenError(_DENIED)
    return appt, role


async def _names(appt: dict) -> dict:
    ids = [i for i in (appt.get("client_id"), appt.get("lawyer_id")) if i]
    rows = await user_repo.find_many({"_id": {"$in": ids}}) if ids else []
    return {str(r["_id"]): r.get("full_name") or "" for r in rows}


def _out(doc: dict, viewer_id: str, names: dict) -> dict:
    mine = doc.get("sender_id") == viewer_id
    return {
        "id": doc["_id"],
        "appointment_id": doc["appointment_id"],
        "sender_id": doc["sender_id"],
        "sender_role": doc["sender_role"],
        "sender_name": names.get(doc["sender_id"], ""),
        "text": doc["text"],
        "created_at": _utc(doc["created_at"]),
        "from_me": mine,
        "client_key": doc.get("idempotency_key") if mine else None,
    }


async def list_messages(appointment_id: str, user: dict, *, page_size: int = DEFAULT_PAGE_SIZE,
                        before_created_at: datetime | None = None, before_id: str | None = None) -> dict:
    if (before_created_at is None) != (before_id is None):
        # A half cursor would silently restart at the newest page.
        raise AppValidationError("Pass both before_created_at and before_id, or neither.")
    appt, _role = await _load_participant(appointment_id, user)
    size = max(1, min(int(page_size or DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE))
    query: dict = {"appointment_id": appt["_id"]}
    if before_created_at is not None:
        at = _utc(before_created_at)
        query["$or"] = [{"created_at": {"$lt": at}},
                        {"created_at": at, "_id": {"$lt": before_id}}]
    rows = await get_appointment_messages_col().find(query).sort(
        [("created_at", DESCENDING), ("_id", DESCENDING)]).limit(size + 1).to_list(length=size + 1)
    more = len(rows) > size
    rows = rows[:size]
    names = await _names(appt)
    await _deliver_pending_notices(appt, names)
    items = [_out(r, user["_id"], names) for r in reversed(rows)]
    next_cursor = ({"before_created_at": _utc(rows[-1]["created_at"]), "before_id": rows[-1]["_id"]}
                   if more and rows else None)
    return {"items": items, "next_cursor": next_cursor, **thread_state(appt)}


async def _notify_other(appt: dict, msg: dict, sender_role: str, names: dict) -> bool:
    """Once per message (logical event id), then marked sent; a failure leaves
    it pending for the next read or send. No message text: a notification can
    surface on a lock screen; the words stay in the app."""
    recipient = appt["lawyer_id"] if sender_role == "client" else appt["client_id"]
    if not recipient:
        await _mark_notified(msg)
        return True
    from app.services.notification_service import create_notification
    sender = names.get(msg["sender_id"]) or ("Your client" if sender_role == "client" else "Your lawyer")
    try:
        await create_notification(
            user_id=recipient,
            type=NotificationType.APPOINTMENT_MESSAGE,
            title="New message about your appointment",
            body=f"{sender} sent you a message about your appointment.",
            payload={"appointment_id": appt["_id"], "message_id": msg["_id"]},
            logical_event_id=f"appointment_message:{msg['_id']}:{recipient}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("appointment_message_notification_failed appointment_id=%s error=%s",
                       appt["_id"], exc.__class__.__name__)
        return False
    await _mark_notified(msg)
    return True


async def _mark_notified(msg: dict) -> None:
    try:
        await get_appointment_messages_col().update_one(
            {"_id": msg["_id"], "notify": "pending"},
            {"$set": {"notify": "sent", "notified_at": datetime.now(timezone.utc)}})
    except Exception as exc:  # noqa: BLE001 -- left pending; redelivery is a no-op
        logger.warning("appointment_message_notify_mark_failed error=%s", exc.__class__.__name__)


async def _deliver_pending_notices(appt: dict, names: dict) -> None:
    """Deliver the notices this thread still owes (a send that died between
    storing the message and notifying). Never fails the read or send."""
    try:
        owed = await get_appointment_messages_col().find(
            {"appointment_id": appt["_id"], "notify": "pending"}
        ).sort("created_at", 1).limit(PENDING_NOTICE_BATCH).to_list(length=PENDING_NOTICE_BATCH)
    except Exception as exc:  # noqa: BLE001
        logger.warning("appointment_message_pending_read_failed error=%s", exc.__class__.__name__)
        return
    for msg in owed:
        await _notify_other(appt, msg, msg.get("sender_role") or "", names)


async def _insert_while_confirmed(appt_id: str, doc: dict) -> bool:
    """Store `doc` only if the appointment is STILL confirmed, atomically.

    The conditional write on the appointment serialises this send with any
    status change to it: whichever commits second sees the first. False means
    the appointment is no longer confirmed and nothing was stored. A duplicate
    key (a raced retry) propagates; the transaction is rolled back first.
    """
    from pymongo.errors import OperationFailure

    from app.db.mongodb import get_client

    async def operation(session):
        res = await get_appointments_col().update_one(
            {"_id": appt_id, "status": AppointmentStatus.CONFIRMED.value},
            {"$set": {"last_message_at": doc["created_at"]}}, session=session)
        if res.matched_count == 0:
            return False
        await get_appointment_messages_col().insert_one(doc, session=session)
        return True

    try:
        async with await get_client().start_session() as session:
            return await session.with_transaction(operation)
    except OperationFailure as exc:
        text = str(exc)
        if "replica set" in text or "Transaction numbers" in text:
            # Standalone mongod: refuse rather than a non-atomic write.
            raise ServiceUnavailableError(_TXN_UNAVAILABLE) from exc
        raise


async def send_message(appointment_id: str, user: dict, text: str, idempotency_key: str) -> dict:
    appt, role = await _load_participant(appointment_id, user)
    col = get_appointment_messages_col()
    key_filter = {"appointment_id": appt["_id"], "sender_id": user["_id"], "idempotency_key": idempotency_key}
    names = await _names(appt)
    await _deliver_pending_notices(appt, names)

    # A RETRY RETURNS WHAT WAS STORED, even if the thread has since closed: the
    # message was sent while it was open. Checked before the lifecycle rule.
    existing = await col.find_one(key_filter)
    if existing is not None:
        return await _replay(appt, existing, text, role, user, names)

    state = thread_state(appt)
    if not state["can_send"]:
        raise ConflictError(
            "Messages open once the lawyer confirms this appointment."
            if state["send_state"] == "awaiting_confirmation"
            else "This conversation is closed: the appointment has ended. You can still read it.")

    doc = {
        "_id": secrets.token_urlsafe(16),
        "appointment_id": appt["_id"],
        "sender_id": user["_id"],
        "sender_role": role,
        "text": text,
        "idempotency_key": idempotency_key,
        "created_at": datetime.now(timezone.utc),
        "notify": "pending",
    }
    try:
        stored = await _insert_while_confirmed(appt["_id"], doc)
    except DuplicateKeyError:
        # Two sends with one key raced; the other one stored it.
        existing = await col.find_one(key_filter)
        if existing is None:
            raise ConflictError("This message could not be sent. Please try again.")
        return await _replay(appt, existing, text, role, user, names)
    if not stored:
        # It ended between the read above and this write.
        raise ConflictError("This conversation is closed: the appointment has ended. You can still read it.")
    await _notify_other(appt, doc, role, names)
    return {**_out(doc, user["_id"], names), "replayed": False}


async def _replay(appt: dict, existing: dict, text: str, role: str, user: dict, names: dict) -> dict:
    if existing.get("text") != text:
        raise ConflictError("This send key was already used for a different message.")
    # The first attempt may have stored the message and failed before
    # notifying; the logical event id makes this a no-op when it did not.
    if existing.get("notify") == "pending":
        await _notify_other(appt, existing, role, names)
    return {**_out(existing, user["_id"], names), "replayed": True}

