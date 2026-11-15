"""A case's consultations, for its lawyer (2026-10-20). See services/case_consultations."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import require_lawyer
from app.services import case_consultations

# Its own prefix, not /cases/...: the cases router owns that space.
router = APIRouter(prefix="/case-consultations", tags=["case-consultations"])


@router.get("/{case_id}")
async def case_consultations_for(case_id: str, current_user: dict = Depends(require_lawyer)):
    return await case_consultations.for_case(case_id, str(current_user["_id"]))
