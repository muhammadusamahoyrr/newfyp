"""Moving a CONFIRMED appointment by agreement (2026-10-19, APPOINTMENT_FLOW_PLAN.md).

A confirmed appointment is an agreement between two people, so neither may move
it alone (`appointment_service.reschedule_appointment` is pending-only). Instead
either party PROPOSES one new time and the other accepts or declines.

THE RULES
  * At most ONE active proposal per appointment. A party with something to say
    about someone else's proposal answers it (accept/decline) or, if it is
    their own, withdraws it first.
  * The confirmed time stays in force until the proposal is accepted.
  * A proposal expires at the earliest of 48 hours after it was made, the
    start of the current time (a meeting cannot be moved once it has begun)
    and the proposed start (a time that has passed cannot be agreed to).
    An expired proposal is simply inactive; nothing has to sweep it.
  * ACCEPT IS ONE CONDITIONAL WRITE: still confirmed, still at the schedule
    version the proposal was made against, still carrying this proposal, not
    expired. The new slots are claimed in the same update, so the unique slot
    indexes refuse a double booking; on any refusal nothing changes and the
    old time stands.
  * Accept bumps `schedule_version`, so reminder ids (which carry the version)
    are new for the new time, and anything composed against the old time is
    refused.
Times are stored in UTC.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.constants import AppointmentStatus, NotificationType
from app.core.exceptions import AppValidationError, ConflictError
from app.services import appointment_service as svc
from app.services.appointment_slots import alignment_error, occupied_slots

LIFETIME = timedelta(hours=48)
NOTE_MAX = 300


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _active(appt: dict, now: datetime | None = None) -> dict | None:
    p = appt.get("reschedule_proposal")
    if not p:
        return None
    exp = p.get("expires_at")
    if exp is not None and svc._as_utc(exp) <= (now or _now()):
        return None
    return p


async def _load_confirmed(appt_id: str, user: dict) -> tuple[dict, str]:
    role = user.get("role")
    if role not in ("client", "lawyer"):
        raise ConflictError("Only the client or the lawyer of this appointment can change its time.")
    appt = await svc._load_for_actor(appt_id, str(user["_id"]), role)
    if svc._current_status(appt) is not AppointmentStatus.CONFIRMED:
        raise ConflictError("Only a confirmed appointment can be moved this way.")
    return appt, role


async def _tell(appt: dict, role: str, title: str, body: str, event: str) -> None:
    recipient = appt["lawyer_id"] if role == "client" else appt["client_id"]
    await svc._notify(appt["_id"], event, user_id=recipient, type=NotificationType.APPOINTMENT_PROPOSED,
                      title=title, body=body, payload={"appointment_id": appt["_id"]},
                      logical_event_id=f"appointment:{appt['_id']}:{event}:{secrets.token_hex(4)}")


def _view(appt: dict, role: str) -> dict:
    return svc._sanitize(appt, for_lawyer=role == "lawyer")


async def propose(appt_id: str, user: dict, scheduled_at: datetime, note: str | None) -> dict:
    appt, role = await _load_confirmed(appt_id, user)
    now = _now()
    current_start = svc._as_utc(appt["scheduled_at"])
    if now >= current_start:
        raise AppValidationError("This appointment has already started, so its time can no longer be changed.")
    if scheduled_at.tzinfo is None or scheduled_at.utcoffset() is None:
        raise AppValidationError("The new time must include a UTC offset.")
    new_start = scheduled_at.astimezone(timezone.utc)
    bad = alignment_error(new_start)
    if bad:
        raise AppValidationError(bad)
    if new_start <= now:
        raise AppValidationError("The new time must be in the future.")
    if new_start == current_start:
        raise AppValidationError("That is already the appointment's time.")
    note = (note or "").strip()
    if len(note) > NOTE_MAX:
        raise AppValidationError(f"The note can be at most {NOTE_MAX} characters.")
    existing = _active(appt, now)
    if existing:
        if existing.get("by") == role:
            raise ConflictError("You already proposed a new time. Withdraw it first to propose another.")
        raise ConflictError("The other side has proposed a new time. Accept or decline it first.")

    proposal = {
        "id": secrets.token_urlsafe(8), "by": role, "by_id": str(user["_id"]),
        "scheduled_at": new_start, "note": note or None, "at": now,
        # The earliest of 48h, the current start and the PROPOSED start: a
        # proposed time that has passed can never be accepted.
        "expires_at": min(now + LIFETIME, current_start, new_start),
        "for_version": svc.schedule_version_of(appt),
    }
    stale = {"$or": [{"reschedule_proposal": None}, {"reschedule_proposal": {"$exists": False}},
                     {"reschedule_proposal.expires_at": {"$lte": now}}]}
    updated = await svc.appt_repo.col.find_one_and_update(
        {"_id": appt_id, "status": AppointmentStatus.CONFIRMED.value, **stale},
        {"$set": {"reschedule_proposal": proposal, "updated_at": now}},
        return_document=ReturnDocument.AFTER)
    if not updated:
        raise ConflictError("This appointment changed a moment ago. Reload it and try again.")
    who = await svc._name_for_notice(str(user["_id"]), role.title(), appt_id=appt_id, transition="propose")
    await _tell(updated, role, "New time proposed",
                f"{who} proposed moving your appointment from {svc._slot_text(current_start)} to "
                f"{svc._slot_text(new_start)}." + (f" Note: {note}" if note else ""), "reschedule-proposed")
    return _view(updated, role)


async def _clear(appt_id: str, user: dict, *, own: bool, verb: str) -> dict:
    appt, role = await _load_confirmed(appt_id, user)
    p = _active(appt)
    if not p:
        raise ConflictError("There is no active proposal to " + verb + ".")
    if own and p.get("by") != role:
        raise ConflictError("Only the side that proposed the new time can withdraw it.")
    if not own and p.get("by") == role:
        raise ConflictError("You cannot decline your own proposal — withdraw it instead.")
    updated = await svc.appt_repo.col.find_one_and_update(
        {"_id": appt_id, "reschedule_proposal.id": p["id"]},
        {"$unset": {"reschedule_proposal": ""}, "$set": {"updated_at": _now()}},
        return_document=ReturnDocument.AFTER)
    if not updated:
        raise ConflictError("This proposal changed a moment ago. Reload and try again.")
    who = await svc._name_for_notice(str(user["_id"]), role.title(), appt_id=appt_id, transition=verb)
    await _tell(updated, role, "Proposal " + ("withdrawn" if own else "declined"),
                f"{who} {'withdrew' if own else 'declined'} the proposal to move the appointment. "
                f"It stays at {svc._slot_text(updated['scheduled_at'])}.", f"reschedule-{verb}")
    return _view(updated, role)


async def withdraw(appt_id: str, user: dict) -> dict:
    return await _clear(appt_id, user, own=True, verb="withdraw")


async def decline(appt_id: str, user: dict) -> dict:
    return await _clear(appt_id, user, own=False, verb="decline")


async def accept(appt_id: str, user: dict, proposal_id: str) -> dict:
    appt, role = await _load_confirmed(appt_id, user)
    now = _now()
    p = _active(appt, now)
    if not p or p.get("id") != proposal_id:
        raise ConflictError("That proposal is no longer active. Reload the appointment.")
    if p.get("by") == role:
        raise ConflictError("The other side has to accept your proposal.")
    duration = appt.get("duration_minutes") or 60
    new_start = svc._as_utc(p["scheduled_at"])
    if new_start <= now:
        raise ConflictError("The proposed time has already passed.")
    old_start = svc._as_utc(appt["scheduled_at"])
    version = svc.schedule_version_of(appt)
    flt = {"_id": appt_id, "status": AppointmentStatus.CONFIRMED.value,
           "reschedule_proposal.id": proposal_id, "reschedule_proposal.expires_at": {"$gt": now}}
    flt.update({"schedule_version": version} if version else
               {"$or": [{"schedule_version": 0}, {"schedule_version": {"$exists": False}}]})
    try:
        updated = await svc.appt_repo.col.find_one_and_update(
            flt,
            {"$set": {"scheduled_at": new_start, "end_at": new_start + timedelta(minutes=duration),
                      "occupied_slots": occupied_slots(new_start, duration), "updated_at": now},
             "$inc": {"schedule_version": 1},
             # Attendance belongs to the old time (and the old room): a
             # meeting at the new time has to be shown again (2026-10-21).
             "$unset": {"reschedule_proposal": "", "video_attended": "", "video_joined": ""},
             "$push": {"reschedule_history": {"from": old_start, "to": new_start, "proposed_by": p["by"],
                                              "accepted_by": role, "at": now}}},
            return_document=ReturnDocument.AFTER)
    except DuplicateKeyError:
        raise ConflictError("That time is no longer free. The appointment stays at its current time.")
    if not updated:
        raise ConflictError("This appointment changed a moment ago. It stays at its current time — reload it.")
    who = await svc._name_for_notice(str(user["_id"]), role.title(), appt_id=appt_id, transition="accept-move")
    await _tell(updated, role, "Appointment moved",
                f"{who} accepted: the appointment moved from {svc._slot_text(old_start)} to "
                f"{svc._slot_text(new_start)}.", "reschedule-accepted")
    # The old time's video room must not stay open (best-effort, never raises).
    from app.services import appointment_video
    await appointment_video.close_room(appt_id)
    return _view(updated, role)
