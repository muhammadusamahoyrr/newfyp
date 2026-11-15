"""Documents a client attaches to an appointment (2026-10-19).

WHO SEES WHAT, by the appointment's status (the user's rules):

  * The CLIENT who booked always sees and can open their own files, and can
    add or remove them while the request is pending or confirmed.
  * The LAWYER of the appointment:
      - pending   -> sees ONLY the files the client ticked "show to the lawyer
                     before they accept" (2026-10-19 rule: no names otherwise).
      - confirmed, completed, no_show (i.e. once accepted) -> can open all.
      - cancelled, expired (declined, withdrawn or never answered) -> nothing:
                     not the list, not a file. Ever.
  * Anyone else gets "not found", never "forbidden": an id tells them nothing.

WHAT IS ACCEPTED is decided from the bytes (PDF, PNG, JPEG; at most 10 MB), as
for case files; the stored name is a server id, the client's filename only a
cleaned label.
"""
from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import AppValidationError, ConflictError, NotFoundError
from app.db.mongodb import get_database
from app.services.case_files import MAX_BYTES, clean_name, sniff

MAX_FILES = 5
NOTE_MAX = 300
_OPEN_TO_CLIENT = {"pending", "confirmed"}            # client may add / remove
_ACCEPTED = {"confirmed", "completed", "no_show"}      # lawyer may open all
_CLOSED_TO_LAWYER = {"cancelled", "expired"}           # lawyer sees nothing


def _col():
    return get_database()["appointment_files"]


def _root() -> Path:
    return Path(settings.upload_root).resolve() / "appointment_files"


def _path_for(file_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", file_id or ""):
        raise NotFoundError("File")
    root = _root()
    path = (root / file_id).resolve()
    if root not in path.parents:
        raise NotFoundError("File")
    return path


async def _appointment(appointment_id: str, user: dict) -> tuple[dict, str]:
    """The appointment and the caller's side of it ("client" / "lawyer")."""
    from app.db.collections import get_appointments_col

    appt = await get_appointments_col().find_one({"_id": appointment_id})
    uid = str(user.get("_id"))
    if appt and str(appt.get("client_id")) == uid:
        return appt, "client"
    if appt and str(appt.get("lawyer_id")) == uid:
        return appt, "lawyer"
    raise NotFoundError("Appointment")


def _status(appt: dict) -> str:
    return str(appt.get("status") or "").lower()


def _lawyer_can_open(appt: dict, row: dict) -> bool:
    status = _status(appt)
    if status in _ACCEPTED:
        return True
    return status == "pending" and bool(row.get("share_before_accept"))


def _public(row: dict, appt: dict, side: str) -> dict:
    out = {
        "id": row["_id"],
        "name": row["name"],
        "content_type": row["content_type"],
        "size": row["size"],
        "note": row.get("note") or "",
        "created_at": row["created_at"],
    }
    if side == "client":
        out["share_before_accept"] = bool(row.get("share_before_accept"))
        out["lawyer_can_open"] = _lawyer_can_open(appt, row)
    else:
        out["can_open"] = _lawyer_can_open(appt, row)
    return out


async def upload(appointment_id: str, user: dict, data: bytes, filename: str | None,
                 note: str | None, share_before_accept: bool) -> dict:
    appt, side = await _appointment(appointment_id, user)
    if side != "client":
        raise NotFoundError("Appointment")
    if _status(appt) not in _OPEN_TO_CLIENT:
        raise ConflictError("Files can only be added while the appointment is pending or confirmed.")
    note = (note or "").strip()
    if len(note) > NOTE_MAX:
        raise AppValidationError(f"The note can be at most {NOTE_MAX} characters.")
    if not data:
        raise AppValidationError("The file is empty.")
    if len(data) > MAX_BYTES:
        raise AppValidationError("The file is larger than 10 MB.")
    ctype, ext = sniff(data)
    if await _col().count_documents({"appointment_id": appointment_id}) >= MAX_FILES:
        raise ConflictError(f"An appointment can hold at most {MAX_FILES} files. Remove one first.")

    file_id = secrets.token_urlsafe(16)
    path = _path_for(file_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(file_id + ".part")
    tmp.write_bytes(data)
    tmp.replace(path)

    row = {
        "_id": file_id,
        "appointment_id": appointment_id,
        "client_id": str(appt.get("client_id")),
        "lawyer_id": str(appt.get("lawyer_id")),
        "name": clean_name(filename, ext),
        "content_type": ctype,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "note": note or None,
        "share_before_accept": bool(share_before_accept),
        "created_at": datetime.now(timezone.utc),
    }
    try:
        await _col().insert_one(row)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return _public(row, appt, "client")


async def list_for(appointment_id: str, user: dict) -> dict:
    appt, side = await _appointment(appointment_id, user)
    if side == "lawyer" and _status(appt) in _CLOSED_TO_LAWYER:
        return {"items": [], "status": _status(appt)}
    cursor = _col().find({"appointment_id": appointment_id}).sort("created_at", 1).limit(MAX_FILES * 2)
    rows = [r async for r in cursor]
    if side == "lawyer":
        # APPOINTMENT_FLOW_PLAN.md (2026-10-19): while a request is pending the
        # lawyer sees NOTHING of a document -- not even its name -- unless the
        # client chose to show that file early. Once accepted, all of them.
        rows = [r for r in rows if _lawyer_can_open(appt, r)]
    return {"items": [_public(r, appt, side) for r in rows], "status": _status(appt)}


async def read(appointment_id: str, file_id: str, user: dict) -> tuple[dict, bytes]:
    appt, side = await _appointment(appointment_id, user)
    row = await _col().find_one({"_id": file_id, "appointment_id": appointment_id})
    if not row:
        raise NotFoundError("File")
    if side == "lawyer" and not _lawyer_can_open(appt, row):
        # Not found, not forbidden: a pending or closed request does not even
        # confirm to the lawyer that the bytes are reachable.
        raise NotFoundError("File")
    path = _path_for(row["_id"])
    if not path.exists():
        raise NotFoundError("File")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != row.get("sha256"):
        raise ConflictError("The stored file does not match what was uploaded.")
    return row, data


async def delete(appointment_id: str, file_id: str, user: dict) -> None:
    appt, side = await _appointment(appointment_id, user)
    if side != "client":
        raise NotFoundError("File")
    if _status(appt) not in _OPEN_TO_CLIENT:
        raise ConflictError("Files can no longer be changed on this appointment.")
    row = await _col().find_one({"_id": file_id, "appointment_id": appointment_id})
    if not row:
        raise NotFoundError("File")
    await _col().delete_one({"_id": row["_id"]})
    _path_for(row["_id"]).unlink(missing_ok=True)
