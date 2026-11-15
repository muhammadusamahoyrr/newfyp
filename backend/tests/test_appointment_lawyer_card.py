"""The client's appointment carries who the lawyer is (2026-10-12).

Public profile facts (practice, experience, rating, office) on every client
row, so the appointment page can introduce the lawyer without a second fetch.
The lawyer's phone number is released only for a CONFIRMED phone consultation;
a pending request, or another mode, never carries it. The lawyer's own view
gets no card at all.
"""
import secrets
from datetime import datetime, timedelta, timezone

import pytest

from app.core.constants import AppointmentMode

pytestmark = pytest.mark.integration


@pytest.fixture
async def parties(app_indexes):
    from app.db.collections import get_appointments_col, get_users_col

    tag = secrets.token_hex(4)
    lawyer_id, client_id = f"LC-L-{tag}", f"LC-C-{tag}"
    now = datetime.now(timezone.utc)
    await get_users_col().insert_many([
        {"_id": lawyer_id, "role": "lawyer", "is_active": True, "phone": "+92-300-0000000",
         "email": f"lc-l-{tag}@test.invalid", "full_name": "Adv Card", "province": "punjab",
         "created_at": now,
         "lawyer_profile": {"specializations": ["family", "civil"], "kyc_verified": True,
                            "rating": 4.5, "total_reviews": 31, "availability": True,
                            "experience_years": 9, "address": "Model Town, Lahore",
                            "lat": 31.48, "lng": 74.32}},
        {"_id": client_id, "role": "client", "is_active": True,
         "email": f"lc-c-{tag}@test.invalid", "full_name": "Client Card", "created_at": now},
    ])
    yield {"lawyer_id": lawyer_id, "client_id": client_id}
    await get_users_col().delete_many({"_id": {"$in": [lawyer_id, client_id]}})
    await get_appointments_col().delete_many({"client_id": client_id})


def _aligned(days):
    base = datetime.now(timezone.utc) + timedelta(days=days)
    return base.replace(minute=0, second=0, microsecond=0)


async def _book(parties, mode, days=3):
    from app.services import appointment_service
    return await appointment_service.book_appointment(
        client_id=parties["client_id"], lawyer_id=parties["lawyer_id"], case_id=None,
        scheduled_at=_aligned(days), duration_minutes=60, mode=mode, notes=None)


async def _client_rows(parties):
    from app.services import appointment_service
    page = await appointment_service.list_appointments(parties["client_id"], "client", None, 1, 20)
    return {r["id"]: r for r in page["items"]}


async def test_a_client_row_introduces_the_lawyer(parties):
    appt = await _book(parties, AppointmentMode.IN_PERSON)
    card = (await _client_rows(parties))[appt["id"]]["lawyer_card"]
    assert card["specializations"] == ["family", "civil"]
    assert card["experience_years"] == 9 and card["rating"] == 4.5 and card["total_reviews"] == 31
    assert card["office_address"] == "Model Town, Lahore"
    assert "phone" not in card and "_phone" not in card


async def test_the_phone_number_only_for_a_confirmed_phone_consultation(parties):
    from app.services import appointment_service
    appt = await _book(parties, AppointmentMode.PHONE)
    assert "phone" not in (await _client_rows(parties))[appt["id"]]["lawyer_card"], "pending: no number"
    await appointment_service.confirm_appointment(appt["id"], parties["lawyer_id"], expected_version=0)
    rows = await _client_rows(parties)
    assert rows[appt["id"]]["lawyer_card"]["phone"] == "+92-300-0000000"
    one = await appointment_service.get_appointment(appt["id"], parties["client_id"], "client")
    assert one["lawyer_card"]["phone"] == "+92-300-0000000"


async def test_a_confirmed_video_consultation_does_not_carry_the_number(parties):
    from app.services import appointment_service
    appt = await _book(parties, AppointmentMode.VIDEO)
    await appointment_service.confirm_appointment(appt["id"], parties["lawyer_id"], expected_version=0)
    assert "phone" not in (await _client_rows(parties))[appt["id"]]["lawyer_card"]


async def test_the_lawyer_view_has_no_card(parties):
    from app.services import appointment_service
    appt = await _book(parties, AppointmentMode.PHONE)
    page = await appointment_service.list_appointments(parties["lawyer_id"], "lawyer", None, 1, 20)
    row = next(r for r in page["items"] if r["id"] == appt["id"])
    assert "lawyer_card" not in row
