"""A lawyer turning down a REQUEST is a decline, not a cancellation (2026-10-12).

The cancellation records the status it ended (`cancelled_from`), so the client
can be told "declined your request" for a pending one and "cancelled" for a
confirmed one. The booking notice names the mode in words ("an in-person"),
not the stored enum value.
"""
import secrets
from datetime import datetime, timedelta, timezone

import pytest

from app.core.constants import AppointmentMode

pytestmark = pytest.mark.integration


@pytest.fixture
async def parties(app_indexes):
    from app.db.collections import get_appointments_col, get_notifications_col, get_users_col

    tag = secrets.token_hex(4)
    lawyer_id, client_id = f"DW-L-{tag}", f"DW-C-{tag}"
    now = datetime.now(timezone.utc)
    await get_users_col().insert_many([
        {"_id": lawyer_id, "role": "lawyer", "is_active": True, "full_name": "Adv Decline",
         "email": f"dw-l-{tag}@test.invalid", "province": "punjab", "created_at": now,
         "lawyer_profile": {"specializations": ["civil"], "kyc_verified": True, "availability": True}},
        {"_id": client_id, "role": "client", "is_active": True, "full_name": "Client Decline",
         "email": f"dw-c-{tag}@test.invalid", "created_at": now},
    ])
    yield {"lawyer_id": lawyer_id, "client_id": client_id}
    await get_notifications_col().delete_many({"user_id": {"$in": [lawyer_id, client_id]}})
    await get_appointments_col().delete_many({"client_id": client_id})
    await get_users_col().delete_many({"_id": {"$in": [lawyer_id, client_id]}})


def _aligned(days):
    base = datetime.now(timezone.utc) + timedelta(days=days)
    return base.replace(minute=0, second=0, microsecond=0)


async def _book(parties, mode=AppointmentMode.IN_PERSON, days=3):
    from app.services import appointment_service
    return await appointment_service.book_appointment(
        client_id=parties["client_id"], lawyer_id=parties["lawyer_id"], case_id=None,
        scheduled_at=_aligned(days), duration_minutes=60, mode=mode, notes=None)


async def _notices(user_id):
    from app.db.collections import get_notifications_col
    return [n async for n in get_notifications_col().find({"user_id": user_id}).sort("created_at", 1)]


async def test_a_declined_request_is_called_a_decline(parties):
    from app.services import appointment_service
    appt = await _book(parties)
    out = await appointment_service.cancel_appointment(appt["id"], parties["lawyer_id"], "lawyer", "Not available")
    assert out["cancelled_from"] == "pending"
    seen = await appointment_service.get_appointment(appt["id"], parties["client_id"], "client")
    assert seen["cancelled_by"] == "lawyer" and seen["cancelled_from"] == "pending"
    last = (await _notices(parties["client_id"]))[-1]
    assert last["title"] == "Request Declined"
    assert "declined your consultation request" in last["body"] and "Reason: Not available" in last["body"]


async def test_a_cancelled_confirmed_appointment_stays_a_cancellation(parties):
    from app.services import appointment_service
    appt = await _book(parties, days=4)
    await appointment_service.confirm_appointment(appt["id"], parties["lawyer_id"], expected_version=0)
    out = await appointment_service.cancel_appointment(appt["id"], parties["lawyer_id"], "lawyer", None)
    assert out["cancelled_from"] == "confirmed"
    last = (await _notices(parties["client_id"]))[-1]
    assert last["title"] == "Appointment Cancelled"
    assert "cancelled the appointment" in last["body"]


async def test_the_booking_notice_names_the_mode_in_words(parties):
    await _book(parties, mode=AppointmentMode.IN_PERSON, days=5)
    body = (await _notices(parties["lawyer_id"]))[-1]["body"]
    assert "requested an in-person consultation" in body
    assert "in_person" not in body
