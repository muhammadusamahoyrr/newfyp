from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.core.constants import CaseStatus, UserRole


class KYCAction(BaseModel):
    approved: bool
    rejection_reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _reason_for_rejection(self):
        # A lawyer told "Reason: Not specified" cannot fix anything. The
        # reason is shown to them in-app and by email.
        if not self.approved and len((self.rejection_reason or "").strip()) < 5:
            raise ValueError("Give the lawyer a reason for the rejection (at least 5 characters).")
        return self


class AnalyticsOverview(BaseModel):
    total_users: int
    users_by_role: dict[str, int]
    total_cases: int
    cases_by_type: dict[str, int]
    cases_by_status: dict[str, int]
    pending_kyc: int
    total_agreements: int
    total_documents: int


class AdminUserUpdate(BaseModel):
    full_name: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None


class AdminUserCreate(BaseModel):
    """No password: the new user sets their own from an emailed link, so no
    admin ever knows another person's password."""
    full_name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    role: UserRole = UserRole.CLIENT


class CaseEnd(BaseModel):
    """The ONE status change an admin may make: ending a case that the
    parties cannot (abuse, abandonment, a dispute decision). The reason is
    recorded and sent to both parties."""
    status: Literal["closed", "dismissed"]
    reason: str = Field(min_length=10, max_length=500)


class AdminCaseRow(BaseModel):
    """What the admin case list shows: who, what kind, which state, when.
    Deliberately NOT the client's description, facts, AI summary, documents or
    hearings: a lawyer-client matter is confidential, and overseeing the
    platform does not need its contents."""
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    case_number: str | None = None
    title: str | None = None
    case_type: str | None = None
    status: str | None = None
    province: str | None = None
    client_id: str | None = None
    client_name: str | None = None
    lawyer_id: str | None = None
    lawyer_name: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    closed_at: datetime | None = None


class LawyerMonitoringItem(BaseModel):
    """One row of the admin lawyer-monitoring table. The service builds this as
    an explicit flat allowlist (no raw user doc), so no embedding/hash can leak;
    ``specializations`` is ``list[str]`` (not the enum) to tolerate free-text."""
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    full_name: str | None = None
    email: str | None = None
    bar_number: str | None = None
    specializations: list[str] = Field(default_factory=list)
    kyc_verified: bool = False
    rating: float = 0.0
    total_reviews: int = 0
    experience_years: int = 0
    active_cases: int = 0
    completed_cases: int = 0
    is_active: bool = False
