"""Appointment-scoped messages (2026-10-12).

A short thread between the two people on ONE appointment, before any hire:
"I am running late", "the link does not open", "which floor is the office".
It is not a case thread; it has its own access rule and lifecycle (see
`services/appointment_message_service.py`).
"""
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# Long enough for a practical note, short enough that this stays a message
# thread and not a document channel.
MAX_MESSAGE_LENGTH = 2000


class AppointmentMessageCreate(BaseModel):
    """What a participant may send. Nothing about WHO: the sender and the
    recipient come from the signed-in user and the stored appointment."""
    model_config = ConfigDict(extra="forbid")

    # Plain text, trimmed; empty after trimming is refused. Built-in
    # constraints, not a raising validator: the app's 422 handler cannot
    # serialise the exception a custom validator attaches.
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MESSAGE_LENGTH)]
    # REQUIRED: a lost reply is retried with the same key and returns the
    # message already stored instead of a second one.
    idempotency_key: str = Field(min_length=8, max_length=128)


class AppointmentMessageOut(BaseModel):
    id: str
    appointment_id: str
    sender_id: str
    sender_role: str
    sender_name: str = ""
    text: str
    created_at: datetime
    # True when the signed-in user sent it.
    from_me: bool = False
    # The sender's own idempotency key, returned ONLY to the sender, so a
    # client that lost a reply can tell whether its message was stored.
    client_key: str | None = None


class AppointmentMessageCursor(BaseModel):
    before_created_at: datetime
    before_id: str


class AppointmentMessagePage(BaseModel):
    """Oldest first within the page; `next_cursor` reads OLDER messages."""
    items: list[AppointmentMessageOut]
    next_cursor: AppointmentMessageCursor | None = None
    # The thread's state, decided by the server: the UI does not re-derive it.
    can_send: bool
    # "open" | "awaiting_confirmation" | "read_only"
    send_state: str
    appointment_status: str


class AppointmentMessageSent(AppointmentMessageOut):
    # True when this was a retry that returned the message already stored.
    replayed: bool = False
