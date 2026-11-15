"""The lawyer's Clients index. See services/lawyer_clients."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import require_lawyer
from app.services import lawyer_actions, lawyer_clients

# Its own prefix: /lawyers/{id} would shadow or be shadowed by a /lawyers/me path.
router = APIRouter(prefix="/lawyer-clients", tags=["lawyer-clients"])


@router.get("")
async def my_clients(current_user: dict = Depends(require_lawyer)):
    return await lawyer_clients.list_clients(str(current_user["_id"]))


# What is waiting on the lawyer, counted once for every page (2026-10-20).
actions_router = APIRouter(prefix="/lawyer-actions", tags=["lawyer-clients"])


@actions_router.get("")
async def my_actions(current_user: dict = Depends(require_lawyer)):
    return await lawyer_actions.action_counts(str(current_user["_id"]))
