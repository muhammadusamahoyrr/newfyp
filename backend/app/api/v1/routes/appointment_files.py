"""Documents a client attaches to an appointment. See services/appointment_files."""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile

from app.core.exceptions import AppValidationError
from app.dependencies import get_current_user
from app.services import appointment_files

# Its own prefix, like /case-files: a new path under /appointments could be
# shadowed by, or shadow, one of that router's parameters.
router = APIRouter(prefix="/appointment-files", tags=["appointment-files"])

_FORM_OVERHEAD = 64 * 1024


@router.post("/{appointment_id}", status_code=201)
async def upload_appointment_file(
    appointment_id: str,
    request: Request,
    file: UploadFile = File(...),
    note: str | None = Form(default=None),
    share_before_accept: bool = Form(default=False),
    current_user: dict = Depends(get_current_user),
):
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > appointment_files.MAX_BYTES + _FORM_OVERHEAD:
        raise AppValidationError("The file is larger than 10 MB.")
    data = await file.read(appointment_files.MAX_BYTES + 1)
    await file.close()
    return await appointment_files.upload(
        appointment_id, current_user, data, file.filename, note, share_before_accept)


@router.get("/{appointment_id}")
async def list_appointment_files(appointment_id: str, current_user: dict = Depends(get_current_user)):
    return await appointment_files.list_for(appointment_id, current_user)


@router.get("/{appointment_id}/{file_id}/download")
async def download_appointment_file(appointment_id: str, file_id: str,
                                    current_user: dict = Depends(get_current_user)):
    row, data = await appointment_files.read(appointment_id, file_id, current_user)
    ascii_name = row["name"].encode("ascii", "ignore").decode() or "file"
    ascii_name = ascii_name.replace('"', "")
    return Response(
        content=data,
        media_type=row["content_type"],
        headers={
            "Content-Disposition": f"inline; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(row['name'])}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete("/{appointment_id}/{file_id}", status_code=204)
async def delete_appointment_file(appointment_id: str, file_id: str,
                                  current_user: dict = Depends(get_current_user)):
    await appointment_files.delete(appointment_id, file_id, current_user)
    return Response(status_code=204)
