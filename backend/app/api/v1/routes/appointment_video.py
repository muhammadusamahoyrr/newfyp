"""In-app video for a confirmed consultation. See services/appointment_video."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user
from app.services import appointment_video

# Its own prefix, like /appointment-files, so it cannot collide with a
# parameter of the /appointments router.
router = APIRouter(prefix="/appointment-video", tags=["appointment-video"])


@router.get("")
async def video_config(current_user: dict = Depends(get_current_user)):
    """Is in-app video set up at all? Lets the UI word its buttons ("Join
    video" vs "Add joining link") without asking per appointment."""
    return {"configured": appointment_video.configured()}


@router.get("/{appointment_id}")
async def video_status(appointment_id: str, current_user: dict = Depends(get_current_user)):
    return await appointment_video.status_for(appointment_id, current_user)


@router.post("/{appointment_id}/join")
async def join_video(appointment_id: str, current_user: dict = Depends(get_current_user)):
    return await appointment_video.join(appointment_id, current_user)


@router.post("/{appointment_id}/attendance")
async def video_attendance(appointment_id: str, current_user: dict = Depends(get_current_user)):
    """Ask Daily whether both people really met in this room; records it if so."""
    return await appointment_video.check_attendance(appointment_id, current_user)
