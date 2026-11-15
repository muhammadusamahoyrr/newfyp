"""A lawyer suggests other times for a pending request; the client picks one
and it is confirmed there (2026-10-19)."""
import secrets
from datetime import datetime, timedelta, timezone

import pytest

from app.core.constants import AppointmentMode
from app.core.exceptions import AppValidationError, ConflictError, ForbiddenError

pytestmark = pytest.mark.integration


@pytest.fixture
async def parties(app_indexes):
    from app.db.collections import get_appointments_col, get_notifications_col, get_users_col

    tag = secrets.token_hex(4)
    lawyer_id, other_lawyer = f"SG-L-{tag}", f"SG-L2-{tag}"
    client_id, other_client = f"SG-C-{tag}", f"SG-C2-{tag}"
    now = datetime.now(timezone.utc)

    def _lawyer(_id):
        return {"_id": _id, "role": "lawyer", "is_active": True, "email": f"{_id}@test.invalid",
                "full_name": "Adv One", "province": "punjab", "created_at": now,
                "lawyer_profile": {"specializations": ["criminal"], "kyc_verified": True, "rating": 4.0,
                                   "total_reviews": 0, "availability": True, "experience_years": 5}}

    await get_users_col().insert_many([
        _lawyer(lawyer_id), _lawyer(other_lawyer),
        {"_id": client_id, "role": "client", "is_active": True, "email": f"{client_id}@test.invalid",
         "full_name": "Client One", "created_at": now},
        {"_id": other_client, "role": "client", "is_active": True, "email": f"{other_client}@test.invalid",
         "full_name": "Client Two", "created_at": now},
    ])
    ids = {"lawyer_id": lawyer_id, "other_lawyer": other_lawyer,
           "client_id": client_id, "other_client": other_client}
    yield ids
    await get_users_col().delete_many({"_id": {"$in": list(ids.values())}})
    await get_appointments_col().delete_many({"client_id": {"$in": [client_id, other_client]}})
    await get_notifications_col().delete_many({"user_id": {"$in": list(ids.values())}})


def _slot(hours_ahead: int) -> datetime:
    base = datetime.now(timezone.utc) + timedelta(hours=hours_ahead)
    return base.replace(minute=0, second=0, microsecond=0)


async def _book(parties, client="client_id", when=None):
    from app.services import appointment_service
    return await appointment_service.book_appointment(
        client_id=parties[client], lawyer_id=parties["lawyer_id"], case_id=None,
        scheduled_at=when or _slot(48), duration_minutes=60, mode=AppointmentMode.VIDEO, notes=None)


async def test_the_lawyer_suggests_and_the_client_is_told(parties):
    from app.db.collections import get_notifications_col
    from app.services import appointment_suggestions as sg

    appt = await _book(parties)
    out = await sg.suggest_times(appt["id"], parties["lawyer_id"], [_slot(72), _slot(96)], "In court that day")
    assert [o for o in out["time_suggestion"]["options"]] == sorted([_slot(72), _slot(96)])
    assert out["status"] == "pending", "suggesting must not move or confirm anything"
    note = await get_notifications_col().find_one({"user_id": parties["client_id"], "title": "Your lawyer suggested other times"})
    assert note and "In court that day" in note["body"]


async def test_picking_a_suggestion_moves_and_confirms_it(parties):
    from app.services import appointment_service
    from app.services import appointment_suggestions as sg

    appt = await _book(parties)
    await sg.suggest_times(appt["id"], parties["lawyer_id"], [_slot(72)], None)
    out = await sg.accept_suggestion(appt["id"], parties["client_id"], _slot(72), appt["schedule_version"])
    assert out["suggestion_confirmed"] is True
    assert out["status"] == "confirmed"
    stored = await appointment_service.get_appointment(appt["id"], parties["client_id"], "client")
    assert stored["scheduled_at"].replace(tzinfo=timezone.utc) == _slot(72)
    assert "time_suggestion" not in stored


async def test_only_an_offered_time_can_be_picked(parties):
    from app.services import appointment_suggestions as sg

    appt = await _book(parties)
    await sg.suggest_times(appt["id"], parties["lawyer_id"], [_slot(72)], None)
    with pytest.raises(AppValidationError):
        await sg.accept_suggestion(appt["id"], parties["client_id"], _slot(80), appt["schedule_version"])


async def test_a_stale_version_is_refused(parties):
    from app.services import appointment_suggestions as sg

    appt = await _book(parties)
    await sg.suggest_times(appt["id"], parties["lawyer_id"], [_slot(72)], None)
    with pytest.raises(ConflictError):
        await sg.accept_suggestion(appt["id"], parties["client_id"], _slot(72), appt["schedule_version"] + 5)


async def test_a_suggested_time_already_booked_is_not_double_booked(parties):
    from app.services import appointment_suggestions as sg

    taken = await _book(parties, client="other_client", when=_slot(72))
    assert taken["status"] == "pending"
    appt = await _book(parties)
    await sg.suggest_times(appt["id"], parties["lawyer_id"], [_slot(72)], None)
    with pytest.raises(ConflictError):
        await sg.accept_suggestion(appt["id"], parties["client_id"], _slot(72), appt["schedule_version"])


async def test_only_this_appointments_lawyer_can_suggest(parties):
    from app.services import appointment_suggestions as sg

    appt = await _book(parties)
    with pytest.raises(ForbiddenError):
        await sg.suggest_times(appt["id"], parties["other_lawyer"], [_slot(72)], None)
    with pytest.raises(ForbiddenError):
        await sg.accept_suggestion(appt["id"], parties["other_client"], _slot(72), 0)


@pytest.mark.parametrize("options", [
    "none",                                        # none
    "past",                                        # in the past
    "four",                                        # too many
    "misaligned",                                  # not on the half hour
])
async def test_bad_suggestions_are_refused(parties, options):
    from app.services import appointment_suggestions as sg

    appt = await _book(parties)
    opts = {"past": [_slot(-5)], "four": [_slot(h) for h in (60, 72, 84, 96)],
            "misaligned": [_slot(72) + timedelta(minutes=7)], "none": []}[options]
    with pytest.raises(AppValidationError):
        await sg.suggest_times(appt["id"], parties["lawyer_id"], opts, None)


async def test_a_confirmed_appointment_takes_no_suggestions(parties):
    from app.services import appointment_service
    from app.services import appointment_suggestions as sg

    appt = await _book(parties)
    await appointment_service.confirm_appointment(appt["id"], parties["lawyer_id"], expected_version=appt["schedule_version"])
    with pytest.raises(ConflictError):
        await sg.suggest_times(appt["id"], parties["lawyer_id"], [_slot(72)], None)
