"""Read receipts for appointment threads. See services/appointment_thread_reads."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_current_user
from app.services import appointment_thread_reads

# Its own prefix, so it cannot collide with a parameter of /appointments.
router = APIRouter(prefix="/appointment-threads", tags=["appointment-threads"])


@router.get("/summary")
async def thread_summary(ids: str = Query("", max_length=4000), current_user: dict = Depends(get_current_user)):
    return await appointment_thread_reads.summary([i.strip() for i in ids.split(",")], current_user)


@router.post("/{appointment_id}/read")
async def mark_thread_read(appointment_id: str, current_user: dict = Depends(get_current_user)):
    return await appointment_thread_reads.mark_read(appointment_id, current_user)
