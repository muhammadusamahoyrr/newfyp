"""Meeting proposals: a lawyer proposes times on a case, the client chooses one
(2026-10-12). See `services/meeting_proposal_service.py`."""
from fastapi import APIRouter, Depends, Query

from app.dependencies import get_current_user, require_client, require_lawyer
from app.schemas.meeting_proposal import (
    MeetingProposalAccept,
    MeetingProposalCreate,
    MeetingProposalDecline,
)
from app.services import meeting_proposal_service

router = APIRouter(prefix="/meeting-proposals", tags=["Meeting proposals"])


@router.post("", status_code=201)
async def propose_meeting(
    body: MeetingProposalCreate,
    current_user: dict = Depends(require_lawyer),
):
    """The lawyer proposes up to three times on a case they hold."""
    return await meeting_proposal_service.propose(current_user["_id"], body.model_dump())


@router.get("")
async def list_meeting_proposals(
    case_id: str | None = Query(None, max_length=64),
    status: str | None = Query(None, pattern="^(open|accepted|declined|withdrawn|expired|cancelled)$"),
    current_user: dict = Depends(get_current_user),
):
    """The caller's own proposals: those they sent (lawyer) or received (client)."""
    role = current_user.get("role")
    if role not in ("client", "lawyer"):
        return []
    return await meeting_proposal_service.list_for(current_user["_id"], role, case_id, status)


@router.post("/{proposal_id}/accept")
async def accept_meeting_proposal(
    proposal_id: str,
    body: MeetingProposalAccept,
    current_user: dict = Depends(require_client),
):
    """The client chooses a time; it becomes a confirmed appointment."""
    return await meeting_proposal_service.accept(proposal_id, current_user["_id"], body.option_index)


@router.post("/{proposal_id}/decline")
async def decline_meeting_proposal(
    proposal_id: str,
    body: MeetingProposalDecline,
    current_user: dict = Depends(require_client),
):
    return await meeting_proposal_service.decline(proposal_id, current_user["_id"], body.reason)


@router.post("/{proposal_id}/withdraw")
async def withdraw_meeting_proposal(
    proposal_id: str,
    current_user: dict = Depends(require_lawyer),
):
    return await meeting_proposal_service.withdraw(proposal_id, current_user["_id"])
