"""A lawyer suggests other times for a PENDING request (2026-10-19).

The lawyer cannot move an appointment on their own (a confirmed one is an
agreement, and a pending one is the client's request -- see
`appointment_service.reschedule_appointment`). What they can do is OFFER: up to
three times, with a short note. The client then picks one, and because the
lawyer has already agreed to every time they offered, picking one moves the
request there AND confirms it.

Picking reuses the two existing guarded paths in order, rather than writing
the row a third way:
  1. `reschedule_appointment` (the client's own move): alignment, future-only,
     the version CAS and the unique slot indexes that stop a double booking;
  2. `confirm_appointment` (the lawyer's accept), at the version step 1
     produced.
If step 2 cannot happen (the request expired meanwhile), the request has still
moved to the chosen time and stays pending for the lawyer to accept -- never a
confirmed appointment at a time nobody saw.

A suggestion is stored on the appointment (`time_suggestion`) and shown to both
sides; it is ignored once the request is no longer pending.
"""
from __future__ import annotations

from datetime import datetime, timezone

from pymongo import ReturnDocument

from app.core.constants import AppointmentStatus, NotificationType
from app.core.exceptions import AppValidationError, ConflictError
from app.services import appointment_service as svc
from app.services.appointment_slots import alignment_error

MAX_OPTIONS = 3
NOTE_MAX = 300


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AppValidationError("Each time must include a UTC offset.")
    return value.astimezone(timezone.utc)


async def suggest_times(appt_id: str, lawyer_id: str, options: list[datetime], note: str | None) -> dict:
    appt = await svc._load_for_actor(appt_id, lawyer_id, "lawyer")
    if svc._current_status(appt) is not AppointmentStatus.PENDING:
        raise ConflictError("Only a pending request can get other suggested times.")
    now = datetime.now(timezone.utc)
    if now >= svc._as_utc(appt["scheduled_at"]):
        raise AppValidationError(
            "This request's time has already passed, so it can no longer be moved. Decline it instead.")
    if not options or len(options) > MAX_OPTIONS:
        raise AppValidationError(f"Suggest between 1 and {MAX_OPTIONS} times.")
    clean: list[datetime] = []
    for raw in options:
        when = _utc(raw)
        bad = alignment_error(when)
        if bad:
            raise AppValidationError(bad)
        if when <= now:
            raise AppValidationError("Every suggested time must be in the future.")
        if when == svc._as_utc(appt["scheduled_at"]):
            raise AppValidationError("That is already the requested time — accept it instead.")
        if when not in clean:
            clean.append(when)
    note = (note or "").strip()
    if len(note) > NOTE_MAX:
        raise AppValidationError(f"The note can be at most {NOTE_MAX} characters.")

    suggestion = {"options": sorted(clean), "note": note or None, "at": now,
                  "for_version": svc.schedule_version_of(appt)}
    updated = await svc.appt_repo.col.find_one_and_update(
        {"_id": appt_id, "lawyer_id": lawyer_id, "status": AppointmentStatus.PENDING.value},
        {"$set": {"time_suggestion": suggestion, "updated_at": now}},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise ConflictError("This request changed a moment ago. Reload it and try again.")

    lawyer_name = await svc._name_for_notice(lawyer_id, "Your lawyer", appt_id=appt_id, transition="suggest")
    times = "; ".join(svc._slot_text(t) for t in suggestion["options"])
    await svc._notify(
        appt_id, "suggest",
        user_id=updated["client_id"],
        type=NotificationType.APPOINTMENT_PROPOSED,
        title="Your lawyer suggested other times",
        body=f"{lawyer_name} can't make the time you asked for and suggested: {times}." + (f" Note: {note}" if note else ""),
        payload={"appointment_id": appt_id},
        logical_event_id=f"appointment:{appt_id}:suggested:{int(now.timestamp())}",
    )
    return svc._sanitize(updated, for_lawyer=True)


async def accept_suggestion(appt_id: str, client_id: str, scheduled_at: datetime, expected_version: int) -> dict:
    appt = await svc._load_for_actor(appt_id, client_id, "client")
    if svc._current_status(appt) is not AppointmentStatus.PENDING:
        raise ConflictError("This request is no longer pending.")
    suggestion = appt.get("time_suggestion") or {}
    chosen = _utc(scheduled_at)
    offered = [svc._as_utc(t) for t in suggestion.get("options") or []]
    if chosen not in offered:
        raise AppValidationError("Pick one of the times your lawyer suggested.")

    moved = await svc.reschedule_appointment(appt_id, client_id, chosen, expected_version)
    confirmed = None
    try:
        confirmed = await svc.confirm_appointment(
            appt_id, appt["lawyer_id"], expected_version=moved["schedule_version"])
    except ConflictError:
        # Moved but not confirmed (e.g. it expired meanwhile): it stays a
        # pending request at the chosen time, for the lawyer to accept.
        pass
    await svc.appt_repo.col.update_one({"_id": appt_id}, {"$unset": {"time_suggestion": ""}})
    current = await svc.appt_repo.find_for_actor(appt_id, {"client_id": client_id})
    result = svc._sanitize(current or moved)
    result["suggestion_confirmed"] = confirmed is not None
    return result
