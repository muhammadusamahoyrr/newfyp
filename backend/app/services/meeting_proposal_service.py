"""Meeting proposals (2026-10-12).

After a lawyer is hired, meeting the client again is ordinary work: hearing
preparation, signing, an update after a hearing. Appointments could only be
BOOKED by the client, and the lawyer's own diary meetings are private, so the
lawyer had no way to ask the client to meet.

A proposal is the lawyer asking: up to three times on a case they hold, a mode
and an agenda. It reserves nothing. When the client chooses a time, the
appointment is created CONFIRMED through `appointment_service`, under the same
slot rules and unique indexes as any booking -- so a time that has been taken
since is refused, and the client chooses another. The client may also decline,
and the lawyer may withdraw an open proposal.

Lifecycle: open -> accepted | declined | withdrawn | expired | cancelled.
"accepting" is a short claim held while the appointment is written, so two
clicks cannot create two appointments; it is released to "open" if the write is
refused. "expired" (every time has passed) is WRITTEN, not only displayed, so a
stale proposal never blocks a new one; "cancelled" means the case changed under
it (closed, or no longer this lawyer's or this client's).

Scheduling rules. Choosing a time re-checks the lawyer's appointments (the
unique slot indexes are the guarantee) and their diary entries and hearings,
which may have been added after the proposal was sent. Working hours are NOT
applied: the lawyer chose these times themselves.
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone

from pymongo.errors import DuplicateKeyError

from app.core.constants import AppointmentMode, CaseStatus, NotificationType
from app.core.exceptions import AppValidationError, ConflictError, ForbiddenError, NotFoundError
from app.db.collections import get_cases_col, get_lawyer_events_col, get_meeting_proposals_col
from app.repositories.appointment_repo import AppointmentRepository
from app.repositories.case_repo import CaseRepository
from app.repositories.user_repo import UserRepository
from app.services import appointment_service
from app.services.appointment_slots import alignment_error, duration_error

logger = logging.getLogger(__name__)

case_repo = CaseRepository()
user_repo = UserRepository()
appt_repo = AppointmentRepository()

OPEN, ACCEPTING, ACCEPTED, DECLINED, WITHDRAWN = "open", "accepting", "accepted", "declined", "withdrawn"
EXPIRED, CANCELLED = "expired", "cancelled"
# A hearing has a date and a time but no length; it is counted as this long,
# from 10:00 when no time was given (the lawyer's calendar does the same).
HEARING_MINUTES = 60
_ENDED_CASE = (CaseStatus.CLOSED.value, CaseStatus.DISMISSED.value)
# How far ahead a lawyer may propose. A proposal for next year is a diary
# entry, not a request for an answer.
MAX_DAYS_AHEAD = 90
_MODE_WORDS = {"video": "video", "in_person": "in-person"}


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


async def _notify(proposal_id: str, **kwargs) -> None:
    """Best-effort, like every appointment notice: the proposal is already
    written, and a delivery failure must not report the action as failed."""
    from app.services.notification_service import create_notification
    try:
        await create_notification(**kwargs)
    except Exception as exc:
        logger.warning("meeting_proposal_notification_failed proposal_id=%s error=%s",
                       proposal_id, type(exc).__name__)


async def _name(user_id: str | None, fallback: str) -> str:
    user = await user_repo.find_by_id(user_id) if user_id else None
    return (user or {}).get("full_name") or fallback


# EXPIRY (2026-10-12). An open proposal whose every time has passed becomes
# `expired`, and its LAWYER is told once ("the client did not choose a time").
#
# Each row is moved by its own compare-and-set (`open` -> `expired`, only if
# still open and still past), so the processes that may run it -- a list, a
# propose, an accept, a future sweep -- each learn exactly which rows THEY
# moved, and a racing accept (which claims `open` -> `accepting`) and an expiry
# cannot both succeed. The move also writes `expiry_notice: "pending"`: the
# notice is owed until it is created, then marked `sent`. A crash in between
# leaves it pending for the next run, and the notice's logical event id makes
# a second creation a no-op -- so it is neither lost nor sent twice. Rows that
# expired before this existed carry no marker and are not notified (no
# backlog is sent).
EXPIRY_NOTICE_PENDING, EXPIRY_NOTICE_SENT = "pending", "sent"
EXPIRY_BATCH = 100


def _stale_filter(now: datetime) -> dict:
    return {"status": OPEN, "options": {"$not": {"$elemMatch": {"$gt": now}}}}


async def _deliver_expiry_notice(doc: dict) -> bool:
    """Create the lawyer's one-time notice, then mark it sent. False if it
    could not be created now (it stays pending for the next run)."""
    from app.services.notification_service import create_notification
    try:
        await create_notification(
            user_id=doc["lawyer_id"],
            type=NotificationType.APPOINTMENT_PROPOSAL_EXPIRED,
            title="Proposed times passed",
            body=(f"{doc.get('client_name') or 'Your client'} did not choose any of the times you "
                  f"proposed for “{doc.get('case_title') or 'the case'}”. You can propose new times."),
            payload={"proposal_id": doc["_id"], "case_id": doc.get("case_id")},
            logical_event_id=f"meeting_proposal:{doc['_id']}:expired:lawyer",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("meeting_proposal_expiry_notice_failed proposal_id=%s error=%s",
                       doc.get("_id"), exc.__class__.__name__)
        return False
    await get_meeting_proposals_col().update_one(
        {"_id": doc["_id"], "expiry_notice": EXPIRY_NOTICE_PENDING},
        {"$set": {"expiry_notice": EXPIRY_NOTICE_SENT, "expiry_notice_at": datetime.now(timezone.utc)}})
    return True


async def expire_stale(query: dict | None = None, *, limit: int = EXPIRY_BATCH) -> dict:
    """Expire stale open proposals matching `query` (at most `limit`), one
    compare-and-set each, and deliver every owed notice in the same scope.
    Returns counts. Used lazily by reads and actions, and by `sweep_expired`."""
    query = dict(query or {})
    col = get_meeting_proposals_col()
    now = datetime.now(timezone.utc)
    expired = 0
    ids = [d["_id"] async for d in col.find({**query, **_stale_filter(now)}, {"_id": 1}).limit(limit)]
    for pid in ids:
        moved = await col.find_one_and_update(
            {"_id": pid, **_stale_filter(now)},
            {"$set": {"status": EXPIRED, "expired_at": now, "updated_at": now,
                      "expiry_notice": EXPIRY_NOTICE_PENDING}},
            return_document=True)
        if moved is not None:
            expired += 1
    delivered = 0
    async for doc in col.find({**query, "status": EXPIRED, "expiry_notice": EXPIRY_NOTICE_PENDING}).limit(limit):
        if await _deliver_expiry_notice(doc):
            delivered += 1
    return {"expired": expired, "notices_delivered": delivered}


async def sweep_expired(batch_size: int = EXPIRY_BATCH) -> dict:
    """A bounded pass over ALL proposals, for a future scheduled job.

    NOT scheduled anywhere. Lazy expiry on proposal reads and actions already
    covers every proposal someone looks at; a scheduler would only tell a
    lawyer sooner about one nobody opened. Wiring it in is a decision with
    its own activation step: a dedicated flag, off by default like the
    appointment jobs, plus the backlog decision (rows expired lazily before
    the marker existed are never notified).
    """
    return await expire_stale({}, limit=max(1, int(batch_size)))


async def _expire_stale(query: dict) -> None:
    """The lazy path used by reads and actions (kept name)."""
    await expire_stale(query)


async def _diary_clash(lawyer_id: str, at: datetime, minutes: int) -> bool:
    """Whether [at, at + minutes) overlaps one of the lawyer's diary entries or
    an upcoming hearing on one of their open cases."""
    end = at + timedelta(minutes=minutes)
    async for e in get_lawyer_events_col().find(
            {"lawyer_id": lawyer_id, "starts_at": {"$gte": at - timedelta(hours=13), "$lt": end}}):
        starts = _as_utc(e["starts_at"])
        if starts < end and starts + timedelta(minutes=int(e.get("duration_minutes") or 60)) > at:
            return True
    day0 = (at + timedelta(hours=5)).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=5)
    query = {"lawyer_id": lawyer_id, "status": {"$nin": list(_ENDED_CASE)},
             "hearing_dates": {"$elemMatch": {"date": {"$gte": day0 - timedelta(days=1), "$lt": day0 + timedelta(days=2)}}}}
    async for c in get_cases_col().find(query, {"hearing_dates": 1}):
        for h in c.get("hearing_dates") or []:
            if h.get("outcome") or not h.get("date"):
                continue
            d = _as_utc(h["date"]) if isinstance(h["date"], datetime) else None
            if d is None:
                continue
            hh, mm = (str(h.get("time") or "10:00").split(":") + ["0"])[:2]
            try:
                local_midnight = datetime(d.year, d.month, d.day, tzinfo=timezone.utc) - timedelta(hours=5)
                starts = local_midnight + timedelta(hours=int(hh), minutes=int(mm))
            except ValueError:
                continue
            if starts < end and starts + timedelta(minutes=HEARING_MINUTES) > at:
                return True
    return False


def _out(doc: dict, *, now: datetime | None = None) -> dict:
    """The proposal as a response. An open proposal whose times have all
    passed is reported as expired; nothing sweeps it."""
    now = now or datetime.now(timezone.utc)
    options = [_as_utc(o) for o in doc.get("options", [])]
    status = doc.get("status")
    if status == OPEN and options and all(o <= now for o in options):
        status = "expired"
    return {
        "id": doc["_id"],
        "case_id": doc.get("case_id"),
        "case_title": doc.get("case_title"),
        "lawyer_id": doc.get("lawyer_id"),
        "lawyer_name": doc.get("lawyer_name"),
        "client_id": doc.get("client_id"),
        "client_name": doc.get("client_name"),
        "mode": doc.get("mode"),
        "duration_minutes": doc.get("duration_minutes"),
        "agenda": doc.get("agenda"),
        "meeting_link": doc.get("meeting_link"),
        "options": [o.isoformat() for o in options],
        "option_passed": [o <= now for o in options],
        "status": status,
        "appointment_id": doc.get("appointment_id"),
        "chosen_index": doc.get("chosen_index"),
        "decline_reason": doc.get("decline_reason"),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


async def propose(lawyer_id: str, data: dict) -> dict:
    case = await case_repo.find_by_id(data["case_id"])
    if not case:
        raise NotFoundError("Case")
    if case.get("lawyer_id") != lawyer_id:
        raise ForbiddenError("This case is not assigned to you")
    if not case.get("client_id"):
        raise AppValidationError(
            "This client is not on Attorney.AI, so they cannot be asked. "
            "Add the meeting to your own diary instead.")
    if case.get("status") in _ENDED_CASE:
        raise AppValidationError("This case is closed.")

    duration = int(data.get("duration_minutes") or 60)
    bad_duration = duration_error(duration)
    if bad_duration:
        raise AppValidationError(bad_duration)
    now = datetime.now(timezone.utc)
    options = sorted({_as_utc(o).astimezone(timezone.utc) for o in data["options"]})
    if len(options) != len(data["options"]):
        raise AppValidationError("Each proposed time must be different.")
    for at in options:
        misaligned = alignment_error(at)
        if misaligned:
            raise AppValidationError(misaligned)
        if at <= now:
            raise AppValidationError("Every proposed time must be in the future.")
        if at > now + timedelta(days=MAX_DAYS_AHEAD):
            raise AppValidationError(f"Propose times within the next {MAX_DAYS_AHEAD} days.")
        # The lawyer's own appointments: proposing a time they are already
        # booked for would only ever end in a refused choice.
        if await appt_repo.has_conflict(lawyer_id, at, duration):
            raise AppValidationError(
                f"You already have an appointment at {appointment_service._slot_text(at)}.")
        if await _diary_clash(lawyer_id, at, duration):
            raise AppValidationError(
                f"{appointment_service._slot_text(at)} clashes with a hearing or an entry in your diary.")

    col = get_meeting_proposals_col()
    await _expire_stale({"case_id": case["_id"]})
    # One open proposal per case: two would ask the client the same question
    # twice. This read gives the friendly message; the unique partial index on
    # case_id (open/accepting) is what makes it hold under a race.
    if await col.find_one({"case_id": case["_id"], "status": {"$in": [OPEN, ACCEPTING]}}):
        raise ConflictError(
            "A meeting proposal on this case is already waiting for the client. "
            "Withdraw it first to propose different times.")

    lawyer_name = await _name(lawyer_id, "Your lawyer")
    client_name = await _name(case["client_id"], "Client")
    doc = {
        "_id": secrets.token_urlsafe(16),
        "lawyer_id": lawyer_id,
        "client_id": case["client_id"],
        "case_id": case["_id"],
        "case_title": case.get("title") or "your case",
        "lawyer_name": lawyer_name,
        "client_name": client_name,
        "mode": AppointmentMode(data["mode"]).value,
        "duration_minutes": duration,
        "agenda": data["agenda"],
        "meeting_link": data.get("meeting_link"),
        "options": options,
        "status": OPEN,
        "created_at": now,
        "updated_at": now,
    }
    try:
        await col.insert_one(doc)
    except DuplicateKeyError:
        raise ConflictError(
            "A meeting proposal on this case is already waiting for the client. "
            "Withdraw it first to propose different times.")
    n = len(options)
    await _notify(
        doc["_id"],
        user_id=case["client_id"],
        type=NotificationType.APPOINTMENT_PROPOSED,
        title="Meeting proposed",
        body=(f"{lawyer_name} proposed a {_MODE_WORDS.get(doc['mode'], '')} meeting about "
              f"“{doc['case_title']}”: {doc['agenda']} Choose "
              + ("the time" if n == 1 else f"one of {n} times") + " on your Appointments page."),
        payload={"proposal_id": doc["_id"], "case_id": case["_id"]},
    )
    return _out(doc, now=now)


async def list_for(user_id: str, role: str, case_id: str | None = None,
                   status: str | None = None) -> list[dict]:
    query: dict = {"client_id": user_id} if role == "client" else {"lawyer_id": user_id}
    await _expire_stale(dict(query))
    if case_id:
        query["case_id"] = case_id
    if status:
        query["status"] = status
    rows = await get_meeting_proposals_col().find(query).sort("created_at", -1).to_list(length=100)
    now = datetime.now(timezone.utc)
    return [_out(r, now=now) for r in rows]


async def _load(proposal_id: str, *, client_id: str | None = None, lawyer_id: str | None = None) -> dict:
    query: dict = {"_id": proposal_id}
    if client_id:
        query["client_id"] = client_id
    if lawyer_id:
        query["lawyer_id"] = lawyer_id
    doc = await get_meeting_proposals_col().find_one(query)
    if not doc:
        # Someone else's proposal reads as missing, not as forbidden.
        raise NotFoundError("Meeting proposal")
    return doc


async def accept(proposal_id: str, client_id: str, option_index: int) -> dict:
    await _expire_stale({"_id": proposal_id, "client_id": client_id})
    doc = await _load(proposal_id, client_id=client_id)
    if doc.get("status") != OPEN:
        raise ConflictError("This meeting proposal is no longer open.")
    # THE CASE AS IT IS NOW. It may have closed, or changed hands, since the
    # proposal was sent; a meeting on a case this lawyer no longer holds must
    # not be booked.
    case = await case_repo.find_by_id(doc["case_id"])
    if (not case or case.get("lawyer_id") != doc["lawyer_id"]
            or case.get("client_id") != client_id or case.get("status") in _ENDED_CASE):
        await get_meeting_proposals_col().update_one(
            {"_id": proposal_id, "status": OPEN},
            {"$set": {"status": CANCELLED, "updated_at": datetime.now(timezone.utc)}})
        raise ConflictError("This case has changed, so the proposed meeting no longer applies.")
    options = [_as_utc(o) for o in doc.get("options", [])]
    if option_index >= len(options):
        raise AppValidationError("Choose one of the proposed times.")
    at = options[option_index]
    if at <= datetime.now(timezone.utc):
        raise AppValidationError("That time has already passed. Please choose another.")

    if await _diary_clash(doc["lawyer_id"], at, int(doc.get("duration_minutes") or 60)):
        raise ConflictError(
            "That time is no longer free in the lawyer's diary. Please choose "
            "another of the proposed times.")

    col = get_meeting_proposals_col()
    # THE CLAIM: only one choice may proceed to write an appointment.
    claimed = await col.update_one(
        {"_id": proposal_id, "client_id": client_id, "status": OPEN},
        {"$set": {"status": ACCEPTING, "updated_at": datetime.now(timezone.utc)}})
    if claimed.modified_count != 1:
        raise ConflictError("This meeting proposal is no longer open.")
    try:
        appt = await appointment_service.create_confirmed_from_proposal(
            client_id=client_id, lawyer_id=doc["lawyer_id"], case_id=doc["case_id"],
            scheduled_at=at, duration_minutes=int(doc.get("duration_minutes") or 60),
            mode=AppointmentMode(doc["mode"]), notes=doc.get("agenda"),
            meeting_link=doc.get("meeting_link"), proposal_id=proposal_id)
    except Exception:
        # Released, so the client can choose another of the times.
        await col.update_one({"_id": proposal_id, "status": ACCEPTING},
                             {"$set": {"status": OPEN, "updated_at": datetime.now(timezone.utc)}})
        raise
    now = datetime.now(timezone.utc)
    await col.update_one({"_id": proposal_id, "status": ACCEPTING}, {"$set": {
        "status": ACCEPTED, "appointment_id": appt["id"], "chosen_index": option_index,
        "updated_at": now}})
    doc.update(status=ACCEPTED, appointment_id=appt["id"], chosen_index=option_index, updated_at=now)
    await _notify(
        proposal_id,
        user_id=doc["lawyer_id"],
        type=NotificationType.APPOINTMENT_PROPOSAL_ACCEPTED,
        title="Meeting confirmed",
        body=(f"{doc.get('client_name') or 'Your client'} chose "
              f"{appointment_service._slot_text(at)} for the meeting about “{doc.get('case_title')}”."),
        payload={"proposal_id": proposal_id, "appointment_id": appt["id"], "case_id": doc["case_id"]},
    )
    return {"proposal": _out(doc, now=now), "appointment": appt}


async def decline(proposal_id: str, client_id: str, reason: str | None) -> dict:
    reason = (reason or "").strip() or None
    now = datetime.now(timezone.utc)
    res = await get_meeting_proposals_col().find_one_and_update(
        {"_id": proposal_id, "client_id": client_id, "status": OPEN},
        {"$set": {"status": DECLINED, "decline_reason": reason, "updated_at": now}},
        return_document=True)
    if not res:
        await _load(proposal_id, client_id=client_id)   # 404 when not theirs
        raise ConflictError("This meeting proposal is no longer open.")
    await _notify(
        proposal_id,
        user_id=res["lawyer_id"],
        type=NotificationType.APPOINTMENT_PROPOSAL_DECLINED,
        title="Meeting times declined",
        body=(f"{res.get('client_name') or 'Your client'} could not make the proposed times for "
              f"“{res.get('case_title')}”." + (f" They said: {reason}" if reason else "")),
        payload={"proposal_id": proposal_id, "case_id": res["case_id"]},
    )
    return _out(res, now=now)


async def withdraw(proposal_id: str, lawyer_id: str) -> dict:
    now = datetime.now(timezone.utc)
    res = await get_meeting_proposals_col().find_one_and_update(
        {"_id": proposal_id, "lawyer_id": lawyer_id, "status": OPEN},
        {"$set": {"status": WITHDRAWN, "updated_at": now}},
        return_document=True)
    if not res:
        await _load(proposal_id, lawyer_id=lawyer_id)
        raise ConflictError("This meeting proposal is no longer open.")
    await _notify(
        proposal_id,
        user_id=res["client_id"],
        type=NotificationType.APPOINTMENT_PROPOSAL_WITHDRAWN,
        title="Meeting proposal withdrawn",
        body=f"{res.get('lawyer_name') or 'Your lawyer'} withdrew the proposed meeting about “{res.get('case_title')}”.",
        payload={"proposal_id": proposal_id, "case_id": res["case_id"]},
    )
    return _out(res, now=now)
