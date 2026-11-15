"""A client shares a short case summary with the lawyer of an appointment
(2026-10-19, APPOINTMENT_FLOW_PLAN.md, Marhala 2).

SEPARATE FROM DOCUMENTS. This is its own permission: sharing or revoking the
summary never touches the appointment's documents, and the other way round.

THE FLOW
  1. `draft` builds a starting text from what the client already wrote (their
     linked case's title, type, province and description, else the booking
     note) and REDACTS identifiers by default -- CNIC numbers, phone numbers and
     email addresses. Addresses cannot be found reliably, so the client is told
     to check for them.
  2. The client edits that text and `share`s it. What is stored is a SNAPSHOT
     of exactly what they approved: a later edit of the case, or a regenerated
     summary, never reaches the lawyer by itself.
  3. `revoke` removes the lawyer's in-app access at once. A copy the lawyer has
     already read cannot be recalled, and the client is told so.
  Every share, update and revoke is written to an audit log.

WHO READS IT: the client who booked, and the lawyer of that appointment while
it is pending, confirmed or completed -- never after a decline, cancellation or
expiry, and never anyone else (they get "not found").
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from app.core.exceptions import AppValidationError, ConflictError, NotFoundError
from app.db.mongodb import get_database

MAX_TEXT = 3000
_SHAREABLE = {"pending", "confirmed"}                      # client may share / change
_LAWYER_READS = {"pending", "confirmed", "completed", "no_show"}

_CNIC = re.compile(r"\b\d{5}[-\s]?\d{7}[-\s]?\d\b")
_PHONE = re.compile(r"(?<!\d)(?:\+92|0092|0)\s?3\d{2}[-\s]?\d{7}(?!\d)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _summaries():
    return get_database()["appointment_summaries"]


def _audit():
    return get_database()["appointment_share_audit"]


def redact(text: str) -> tuple[str, int]:
    """Identifiers replaced by a marker; returns (text, how many)."""
    count = 0
    for pattern, marker in ((_CNIC, "[CNIC hidden]"), (_PHONE, "[phone hidden]"), (_EMAIL, "[email hidden]")):
        text, n = pattern.subn(marker, text)
        count += n
    return text, count


async def _appointment(appt_id: str, user: dict) -> tuple[dict, str]:
    from app.db.collections import get_appointments_col
    appt = await get_appointments_col().find_one({"_id": appt_id})
    uid = str(user.get("_id"))
    if appt and str(appt.get("client_id")) == uid:
        return appt, "client"
    if appt and str(appt.get("lawyer_id")) == uid:
        return appt, "lawyer"
    raise NotFoundError("Appointment")


def _status(appt: dict) -> str:
    return str(appt.get("status") or "").lower()


async def _log(appt: dict, action: str, chars: int = 0) -> None:
    await _audit().insert_one({
        "appointment_id": appt["_id"], "client_id": appt.get("client_id"),
        "lawyer_id": appt.get("lawyer_id"), "action": action, "chars": chars,
        "at": datetime.now(timezone.utc),
    })


async def draft(appt_id: str, user: dict) -> dict:
    appt, side = await _appointment(appt_id, user)
    if side != "client":
        raise NotFoundError("Appointment")
    parts: list[str] = []
    source = "note"
    if appt.get("case_id"):
        from app.repositories.case_repo import CaseRepository
        case = await CaseRepository().find_by_id(appt["case_id"])
        if case and str(case.get("client_id")) == str(user.get("_id")):
            source = "case"
            if case.get("title"):
                parts.append(f"Matter: {case['title']}")
            kind = " · ".join(str(x).replace("_", " ").title() for x in (case.get("case_type"), case.get("province")) if x)
            if kind:
                parts.append(f"Type: {kind}")
            if case.get("description"):
                parts.append(str(case["description"]).strip())
    if appt.get("notes"):
        parts.append(f"What I want to discuss: {str(appt['notes']).strip()}")
    text, hidden = redact("\n\n".join(parts).strip()[:MAX_TEXT])
    return {"text": text, "hidden": hidden, "source": source}


async def share(appt_id: str, user: dict, text: str) -> dict:
    appt, side = await _appointment(appt_id, user)
    if side != "client":
        raise NotFoundError("Appointment")
    if _status(appt) not in _SHAREABLE:
        raise ConflictError("A summary can be shared only while the appointment is pending or confirmed.")
    text = (text or "").strip()
    if not text:
        raise AppValidationError("Write the summary you want to share.")
    if len(text) > MAX_TEXT:
        raise AppValidationError(f"The summary can be at most {MAX_TEXT} characters.")
    now = datetime.now(timezone.utc)
    existing = await _summaries().find_one({"_id": appt_id})
    await _summaries().update_one(
        {"_id": appt_id},
        {"$set": {"text": text, "shared_at": now, "client_id": appt.get("client_id"),
                  "lawyer_id": appt.get("lawyer_id"), "revoked_at": None}},
        upsert=True)
    await _log(appt, "update" if existing and not existing.get("revoked_at") else "share", len(text))
    return await read(appt_id, user)


async def revoke(appt_id: str, user: dict) -> dict:
    appt, side = await _appointment(appt_id, user)
    if side != "client":
        raise NotFoundError("Appointment")
    row = await _summaries().find_one({"_id": appt_id})
    if not row or row.get("revoked_at"):
        return {"shared": False}
    # The text is removed, not merely flagged: nothing remains for the lawyer
    # to read in-app. The audit keeps that it happened, not what it said.
    await _summaries().update_one({"_id": appt_id},
                                  {"$set": {"revoked_at": datetime.now(timezone.utc)}, "$unset": {"text": ""}})
    await _log(appt, "revoke")
    return {"shared": False}


async def read(appt_id: str, user: dict) -> dict:
    appt, side = await _appointment(appt_id, user)
    if side == "lawyer" and _status(appt) not in _LAWYER_READS:
        return {"shared": False}
    row = await _summaries().find_one({"_id": appt_id})
    if not row or row.get("revoked_at") or not row.get("text"):
        return {"shared": False}
    return {"shared": True, "text": row["text"], "shared_at": row.get("shared_at")}
