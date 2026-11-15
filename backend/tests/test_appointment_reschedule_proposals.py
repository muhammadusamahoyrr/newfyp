"""Moving a CONFIRMED appointment by agreement, and the outcomes an ended one
can get (2026-10-19, APPOINTMENT_FLOW_PLAN.md)."""
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
    ids = {"lawyer": f"RP-L-{tag}", "client": f"RP-C-{tag}", "other": f"RP-O-{tag}"}
    now = datetime.now(timezone.utc)
    await get_users_col().insert_many([
        {"_id": ids["lawyer"], "role": "lawyer", "is_active": True, "email": f"{ids['lawyer']}@t.invalid",
         "full_name": "Adv One", "province": "punjab", "created_at": now,
         "lawyer_profile": {"specializations": ["civil"], "kyc_verified": True, "rating": 4.0,
                            "total_reviews": 0, "availability": True, "experience_years": 5}},
        {"_id": ids["client"], "role": "client", "is_active": True, "email": f"{ids['client']}@t.invalid",
         "full_name": "Client One", "created_at": now},
        {"_id": ids["other"], "role": "client", "is_active": True, "email": f"{ids['other']}@t.invalid",
         "full_name": "Client Two", "created_at": now},
    ])
    yield ids
    await get_users_col().delete_many({"_id": {"$in": list(ids.values())}})
    await get_appointments_col().delete_many({"lawyer_id": ids["lawyer"]})
    await get_notifications_col().delete_many({"user_id": {"$in": list(ids.values())}})


def _slot(h: int) -> datetime:
    return (datetime.now(timezone.utc) + timedelta(hours=h)).replace(minute=0, second=0, microsecond=0)


def U(parties, who):
    return {"_id": parties[who], "role": "lawyer" if who == "lawyer" else "client"}


async def _confirmed(parties, client="client", when=None):
    from app.services import appointment_service as svc
    a = await svc.book_appointment(client_id=parties[client], lawyer_id=parties["lawyer"], case_id=None,
                                   scheduled_at=when or _slot(48), duration_minutes=60,
                                   mode=AppointmentMode.VIDEO, notes=None)
    await svc.confirm_appointment(a["id"], parties["lawyer"], expected_version=a["schedule_version"])
    return await svc.get_appointment(a["id"], parties["client"] if client == "client" else parties[client], "client")


async def test_either_side_proposes_and_the_other_accepts(parties):
    from app.services import appointment_reschedule_proposals as rp
    appt = await _confirmed(parties)
    out = await rp.propose(appt["id"], U(parties, "lawyer"), _slot(72), "Hearing that morning")
    p = out["reschedule_proposal"]
    assert p["by"] == "lawyer" and out["status"] == "confirmed"
    assert out["scheduled_at"].replace(tzinfo=timezone.utc) == _slot(48), "the old time stays until accepted"
    moved = await rp.accept(appt["id"], U(parties, "client"), p["id"])
    assert moved["scheduled_at"].replace(tzinfo=timezone.utc) == _slot(72)
    assert moved["schedule_version"] == appt["schedule_version"] + 1
    assert "reschedule_proposal" not in moved and moved["status"] == "confirmed"


async def test_only_one_active_proposal(parties):
    from app.services import appointment_reschedule_proposals as rp
    appt = await _confirmed(parties)
    await rp.propose(appt["id"], U(parties, "client"), _slot(72), None)
    with pytest.raises(ConflictError):
        await rp.propose(appt["id"], U(parties, "lawyer"), _slot(96), None)
    with pytest.raises(ConflictError):
        await rp.propose(appt["id"], U(parties, "client"), _slot(96), None)


async def test_withdraw_and_decline_leave_the_time_unchanged(parties):
    from app.services import appointment_reschedule_proposals as rp
    appt = await _confirmed(parties)
    await rp.propose(appt["id"], U(parties, "client"), _slot(72), None)
    with pytest.raises(ConflictError):
        await rp.withdraw(appt["id"], U(parties, "lawyer"))     # not theirs
    out = await rp.withdraw(appt["id"], U(parties, "client"))
    assert "reschedule_proposal" not in out
    await rp.propose(appt["id"], U(parties, "client"), _slot(73), None)
    with pytest.raises(ConflictError):
        await rp.decline(appt["id"], U(parties, "client"))      # own proposal
    out = await rp.decline(appt["id"], U(parties, "lawyer"))
    assert "reschedule_proposal" not in out
    assert out["scheduled_at"].replace(tzinfo=timezone.utc) == _slot(48)


async def test_the_proposer_cannot_accept_their_own(parties):
    from app.services import appointment_reschedule_proposals as rp
    appt = await _confirmed(parties)
    out = await rp.propose(appt["id"], U(parties, "lawyer"), _slot(72), None)
    with pytest.raises(ConflictError):
        await rp.accept(appt["id"], U(parties, "lawyer"), out["reschedule_proposal"]["id"])


async def test_a_taken_slot_refuses_and_leaves_the_old_time(parties):
    from app.services import appointment_service as svc
    from app.services import appointment_reschedule_proposals as rp
    appt = await _confirmed(parties)
    out = await rp.propose(appt["id"], U(parties, "lawyer"), _slot(72), None)
    # Meanwhile another client books the proposed slot.
    await svc.book_appointment(client_id=parties["other"], lawyer_id=parties["lawyer"], case_id=None,
                               scheduled_at=_slot(72), duration_minutes=60, mode=AppointmentMode.VIDEO, notes=None)
    with pytest.raises(ConflictError):
        await rp.accept(appt["id"], U(parties, "client"), out["reschedule_proposal"]["id"])
    after = await svc.get_appointment(appt["id"], parties["client"], "client")
    assert after["scheduled_at"].replace(tzinfo=timezone.utc) == _slot(48)
    assert after["schedule_version"] == appt["schedule_version"]


async def test_an_expired_proposal_cannot_be_accepted(parties):
    from app.db.collections import get_appointments_col
    from app.services import appointment_reschedule_proposals as rp
    appt = await _confirmed(parties)
    out = await rp.propose(appt["id"], U(parties, "lawyer"), _slot(72), None)
    await get_appointments_col().update_one(
        {"_id": appt["id"]}, {"$set": {"reschedule_proposal.expires_at": datetime.now(timezone.utc) - timedelta(minutes=1)}})
    with pytest.raises(ConflictError):
        await rp.accept(appt["id"], U(parties, "client"), out["reschedule_proposal"]["id"])
    # ...and a new one can now be made.
    await rp.propose(appt["id"], U(parties, "client"), _slot(80), None)


async def test_bad_proposals_are_refused(parties):
    from app.services import appointment_reschedule_proposals as rp
    appt = await _confirmed(parties)
    for when in (_slot(-3), _slot(48), _slot(72) + timedelta(minutes=7)):
        with pytest.raises(AppValidationError):
            await rp.propose(appt["id"], U(parties, "lawyer"), when, None)


async def test_a_pending_request_uses_the_suggest_path_not_this(parties):
    from app.services import appointment_service as svc
    from app.services import appointment_reschedule_proposals as rp
    a = await svc.book_appointment(client_id=parties["client"], lawyer_id=parties["lawyer"], case_id=None,
                                   scheduled_at=_slot(48), duration_minutes=60, mode=AppointmentMode.VIDEO, notes=None)
    with pytest.raises(ConflictError):
        await rp.propose(a["id"], U(parties, "lawyer"), _slot(72), None)


async def test_strangers_cannot_touch_it(parties):
    from app.services import appointment_reschedule_proposals as rp
    appt = await _confirmed(parties)
    with pytest.raises(ForbiddenError):
        await rp.propose(appt["id"], U(parties, "other"), _slot(72), None)


async def test_outcome_codes_are_lawyer_only_and_only_after_the_start(parties):
    from app.db.collections import get_appointments_col
    from app.services import appointment_service as svc
    appt = await _confirmed(parties)
    with pytest.raises(AppValidationError):
        await svc.cancel_appointment(appt["id"], parties["lawyer"], "lawyer", None, outcome_code="lawyer_no_show")
    past = datetime.now(timezone.utc) - timedelta(hours=3)
    await get_appointments_col().update_one({"_id": appt["id"]},
                                            {"$set": {"scheduled_at": past, "end_at": past + timedelta(hours=1)}})
    with pytest.raises(AppValidationError):
        await svc.cancel_appointment(appt["id"], parties["client"], "client", None, outcome_code="did_not_take_place")
    out = await svc.cancel_appointment(appt["id"], parties["lawyer"], "lawyer", None, outcome_code="lawyer_no_show")
    assert out["status"] == "cancelled" and out["outcome_code"] == "lawyer_no_show"
    assert out["cancelled_from"] == "confirmed"


async def test_a_proposal_expires_no_later_than_the_proposed_start(parties):
    """Correction 2026-10-19: min(48h, current start, PROPOSED start)."""
    from app.services import appointment_reschedule_proposals as rp
    appt = await _confirmed(parties, when=_slot(72))
    out = await rp.propose(appt["id"], U(parties, "lawyer"), _slot(3), None)   # earlier than now+48h
    exp = out["reschedule_proposal"]["expires_at"].replace(tzinfo=timezone.utc)
    assert exp == _slot(3), "an earlier proposed time must cap the proposal's life"


def test_no_show_needs_fifteen_minutes_after_the_start():
    """Correction 2026-10-19: a no-show is a mark against someone; give them time."""
    from app.core.constants import AppointmentStatus
    from app.services.appointment_transitions import NO_SHOW_GRACE, timing_error
    start = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=1)
    assert NO_SHOW_GRACE == timedelta(minutes=15)
    assert timing_error(AppointmentStatus.NO_SHOW, start, end, start) is not None
    assert timing_error(AppointmentStatus.NO_SHOW, start, end, start + timedelta(minutes=14, seconds=59)) is not None
    assert timing_error(AppointmentStatus.NO_SHOW, start, end, start + timedelta(minutes=15)) is None
