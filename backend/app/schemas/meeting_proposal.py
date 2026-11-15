"""Meeting proposals: a lawyer proposes up to three times on a case they hold,
and the client chooses one (2026-10-12).

A proposal is not an appointment. It holds no slots; the appointment is made
only when the client chooses a time, through the same slot rules as a booking.
"""
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.core.constants import AppointmentMode
from app.schemas.appointment import validate_https_meeting_link

MAX_PROPOSED_TIMES = 3


class MeetingProposalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1, max_length=64)
    options: list[AwareDatetime] = Field(min_length=1, max_length=MAX_PROPOSED_TIMES)
    duration_minutes: int = Field(default=60, ge=30, le=180)
    mode: AppointmentMode
    agenda: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=300)]
    meeting_link: str | None = Field(default=None, max_length=500)

    _check_link = field_validator("meeting_link")(validate_https_meeting_link)

    @field_validator("mode")
    @classmethod
    def _video_or_in_person(cls, value: AppointmentMode) -> AppointmentMode:
        # The product offers video and in-person consultations only.
        if value not in (AppointmentMode.VIDEO, AppointmentMode.IN_PERSON):
            raise ValueError("Choose a video or an in-person meeting")
        return value

    @model_validator(mode="after")
    def _link_only_for_video(self) -> "MeetingProposalCreate":
        if self.meeting_link and self.mode != AppointmentMode.VIDEO:
            raise ValueError("A joining link is only for a video meeting")
        return self


class MeetingProposalAccept(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_index: int = Field(ge=0, lt=MAX_PROPOSED_TIMES)


class MeetingProposalDecline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=500)
