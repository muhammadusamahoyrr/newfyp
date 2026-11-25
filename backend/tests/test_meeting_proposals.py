"""Meeting proposals: a lawyer proposes times on a case they hold; the client
chooses one and it becomes a CONFIRMED appointment (2026-10-12).

The proposal reserves nothing. Choosing a time goes through the booking slot
rules, so a time taken since is refused and the proposal stays open.
"""
import secrets
from datetime import datetime, timedelta, timezone

import pytest

from app.core.exceptions import AppValidationError, ConflictError, ForbiddenError, NotFoundError

pytestmark = pytest.mark.integration


def _aligned(days, hour=0):
    base = datetime.now(timezone.utc) + timedelta(days=days, hours=hour)
    return base.replace(minute=0, second=0, microsecond=0)


@pytest.fixture
async def world(app_indexes):
    from app.db.collections import (get_appointments_col, get_cases_col, get_meeting_proposals_col,
                                    get_notifications_col, get_users_col)
    tag = secrets.token_hex(4)
    lawyer, other, client = f"MP-L-{tag}", f"MP-O-{tag}", f"MP-C-{tag}"
    now = datetime.now(timezone.utc)
    lp = {"specializations": ["civil"], "kyc_verified": True, "availability": True}
    await get_users_col().insert_many([
        {"_id": lawyer, "role": "lawyer", "is_active": True, "full_name": "Adv Proposer",
         "email": f"mp-l-{tag}@test.invalid", "created_at": now, "lawyer_profile": lp},
        {"_id": other, "role": "lawyer", "is_active": True, "full_name": "Adv Other",
         "email": f"mp-o-{tag}@test.invalid", "created_at": now, "lawyer_profile": lp},
        {"_id": client, "role": "client", "is_active": True, "full_name": "Client Chooser",
         "email": f"mp-c-{tag}@test.invalid", "created_at": now},
    ])
    case_id, walk_in = f"MP-K-{tag}", f"MP-W-{tag}"
    await get_cases_col().insert_many([
        {"_id": case_id, "client_id": client, "lawyer_id": lawyer, "title": "Rent dispute",
         "case_number": f"MP-{tag}-1", "status": "in_progress", "created_at": now},
        {"_id": walk_in, "client_id": None, "lawyer_id": lawyer, "title": "Walk-in matter",
         "case_number": f"MP-{tag}-2", "status": "in_progress", "walk_in": True, "created_at": now},
    ])
    yield {"lawyer": lawyer, "other": other, "client": client, "case": case_id, "walk_in": walk_in}
    users = [lawyer, other, client]
    await get_meeting_proposals_col().delete_many({"lawyer_id": {"$in": [lawyer, other]}})
    await get_appointments_col().delete_many({"client_id": client})
    await get_notifications_col().delete_many({"user_id": {"$in": users}})
    await get_cases_col().delete_many({"_id": {"$in": [case_id, walk_in]}})
    await get_users_col().delete_many({"_id": {"$in": users}})


def _body(w, **over):
    return {"case_id": w["case"], "options": [_aligned(3), _aligned(4)], "duration_minutes": 60,
            "mode": "video", "agenda": "Prepare for the hearing", "meeting_link": None, **over}


async def _last_notice(user_id):
    from app.db.collections import get_notifications_col
    rows = [n async for n in get_notifications_col().find({"user_id": user_id}).sort("created_at", -1).limit(1)]
    return rows[0] if rows else None


async def test_a_proposal_asks_the_client_and_holds_nothing(world):
    from app.services import meeting_proposal_service as svc
    out = await svc.propose(world["lawyer"], _body(world))
    assert out["status"] == "open" and len(out["options"]) == 2
    note = await _last_notice(world["client"])
    assert note["type"] == "appointment_proposed" and "Prepare for the hearing" in note["body"]
    from app.db.collections import get_appointments_col
    assert await get_appointments_col().count_documents({"client_id": world["client"]}) == 0
    with pytest.raises(ConflictError):
        await svc.propose(world["lawyer"], _body(world))


async def test_public_proposal_history_is_paginated(world):
    from app.db.collections import get_meeting_proposals_col
    from app.services import meeting_proposal_service as svc
    now = datetime.now(timezone.utc)
    rows = [{"_id": f"MP-PAGE-{i}-{world['lawyer']}", "lawyer_id": world["lawyer"],
             "client_id": world["client"], "case_id": world["case"],
             "status": "declined", "options": [_aligned(3 + i)],
             "created_at": now - timedelta(minutes=i)} for i in range(3)]
    await get_meeting_proposals_col().insert_many(rows)
    first = await svc.list_page_for(world["lawyer"], "lawyer", world["case"],
                                    page=1, page_size=2)
    second = await svc.list_page_for(world["lawyer"], "lawyer", world["case"],
                                     page=2, page_size=2)
    assert first["total"] == 3 and first["pages"] == 2 and len(first["items"]) == 2
    assert len(second["items"]) == 1


async def test_only_the_cases_own_lawyer_with_a_platform_client_may_propose(world):
    from app.services import meeting_proposal_service as svc
    with pytest.raises(ForbiddenError):
        await svc.propose(world["other"], _body(world))
    with pytest.raises(AppValidationError):
        await svc.propose(world["lawyer"], _body(world, case_id=world["walk_in"]))
    with pytest.raises(AppValidationError):
        await svc.propose(world["lawyer"], _body(world, options=[_aligned(-1)]))
    with pytest.raises(AppValidationError):
        await svc.propose(world["lawyer"], _body(world, options=[_aligned(3) + timedelta(minutes=10)]))


async def test_choosing_a_time_makes_a_confirmed_appointment_on_the_case(world):
    from app.services import meeting_proposal_service as svc
    p = await svc.propose(world["lawyer"], _body(world, meeting_link="https://meet.example.com/r1"))
    res = await svc.accept(p["id"], world["client"], 1)
    appt = res["appointment"]
    assert appt["status"] == "confirmed" and appt["case_id"] == world["case"]
    assert appt["meeting_link"] == "https://meet.example.com/r1" and appt["notes"] == "Prepare for the hearing"
    assert res["proposal"]["status"] == "accepted" and res["proposal"]["appointment_id"] == appt["id"]
    assert (await _last_notice(world["lawyer"]))["type"] == "appointment_proposal_accepted"
    with pytest.raises(ConflictError):
        await svc.accept(p["id"], world["client"], 0)


async def test_a_time_taken_since_is_refused_and_the_proposal_stays_open(world):
    from app.services import appointment_service, meeting_proposal_service as svc
    from app.core.constants import AppointmentMode
    p = await svc.propose(world["lawyer"], _body(world))
    # The client books another lawyer at the first proposed time.
    await appointment_service.book_appointment(
        client_id=world["client"], lawyer_id=world["other"], case_id=None,
        scheduled_at=_aligned(3), duration_minutes=60, mode=AppointmentMode.VIDEO, notes=None)
    with pytest.raises(ConflictError):
        await svc.accept(p["id"], world["client"], 0)
    still = await svc.list_for(world["client"], "client")
    assert [x["status"] for x in still if x["id"] == p["id"]] == ["open"]
    res = await svc.accept(p["id"], world["client"], 1)
    assert res["appointment"]["status"] == "confirmed"


async def test_decline_and_withdraw_tell_the_other_side(world):
    from app.services import meeting_proposal_service as svc
    p = await svc.propose(world["lawyer"], _body(world))
    out = await svc.decline(p["id"], world["client"], "Travelling that week")
    assert out["status"] == "declined"
    note = await _last_notice(world["lawyer"])
    assert note["type"] == "appointment_proposal_declined" and "Travelling that week" in note["body"]

    p2 = await svc.propose(world["lawyer"], _body(world))
    with pytest.raises(NotFoundError):
        await svc.withdraw(p2["id"], world["other"])
    assert (await svc.withdraw(p2["id"], world["lawyer"]))["status"] == "withdrawn"
    assert (await _last_notice(world["client"]))["type"] == "appointment_proposal_withdrawn"
    with pytest.raises(ConflictError):
        await svc.accept(p2["id"], world["client"], 0)


async def test_an_open_proposal_whose_times_have_passed_reads_as_expired(world):
    from app.db.collections import get_meeting_proposals_col
    from app.services import meeting_proposal_service as svc
    now = datetime.now(timezone.utc)
    await get_meeting_proposals_col().insert_one({
        "_id": f"old-{secrets.token_hex(3)}", "lawyer_id": world["lawyer"], "client_id": world["client"],
        "case_id": world["case"], "mode": "video", "duration_minutes": 60, "agenda": "Old",
        "options": [now - timedelta(days=2)], "status": "open", "created_at": now, "updated_at": now})
    rows = await svc.list_for(world["client"], "client")
    assert [r["status"] for r in rows if r["agenda"] == "Old"] == ["expired"]


# ── integrity (2026-10-12 review) ────────────────────────────────────────────

async def test_a_stale_open_proposal_is_written_expired_and_does_not_block_a_new_one(world):
    from app.db.collections import get_meeting_proposals_col
    from app.services import meeting_proposal_service as svc
    now = datetime.now(timezone.utc)
    old_id = f"stale-{secrets.token_hex(3)}"
    await get_meeting_proposals_col().insert_one({
        "_id": old_id, "lawyer_id": world["lawyer"], "client_id": world["client"], "case_id": world["case"],
        "mode": "video", "duration_minutes": 60, "agenda": "Old", "options": [now - timedelta(days=1)],
        "status": "open", "created_at": now, "updated_at": now})
    out = await svc.propose(world["lawyer"], _body(world))
    assert out["status"] == "open"
    assert (await get_meeting_proposals_col().find_one({"_id": old_id}))["status"] == "expired"


async def test_choosing_a_time_rechecks_the_case(world):
    from app.db.collections import get_cases_col
    from app.services import meeting_proposal_service as svc
    p = await svc.propose(world["lawyer"], _body(world))
    await get_cases_col().update_one({"_id": world["case"]}, {"$set": {"lawyer_id": world["other"]}})
    with pytest.raises(ConflictError, match="case has changed"):
        await svc.accept(p["id"], world["client"], 0)
    rows = await svc.list_for(world["client"], "client")
    assert [r["status"] for r in rows if r["id"] == p["id"]] == ["cancelled"]
    from app.db.collections import get_appointments_col
    assert await get_appointments_col().count_documents({"client_id": world["client"]}) == 0


async def test_a_diary_entry_or_hearing_at_the_time_is_a_clash(world):
    from app.db.collections import get_cases_col, get_lawyer_events_col
    from app.services import meeting_proposal_service as svc
    at = _aligned(3)
    ev = {"_id": f"ev-{secrets.token_hex(3)}", "lawyer_id": world["lawyer"], "kind": "meeting", "title": "Other",
          "starts_at": at, "duration_minutes": 60, "priority": "medium", "created_at": datetime.now(timezone.utc)}
    await get_lawyer_events_col().insert_one(ev)
    try:
        with pytest.raises(AppValidationError, match="clashes"):
            await svc.propose(world["lawyer"], _body(world, options=[at]))
    finally:
        await get_lawyer_events_col().delete_one({"_id": ev["_id"]})

    # Sent while free; a hearing is then fixed at that time -> choosing it is refused.
    p = await svc.propose(world["lawyer"], _body(world, options=[at, _aligned(4)]))
    pkt = at + timedelta(hours=5)
    await get_cases_col().update_one({"_id": world["case"]}, {"$push": {"hearing_dates": {
        "_id": "h1", "date": datetime(pkt.year, pkt.month, pkt.day, tzinfo=timezone.utc),
        "time": pkt.strftime("%H:%M"), "court": "Civil Court", "purpose": "Evidence"}}})
    with pytest.raises(ConflictError, match="no longer free"):
        await svc.accept(p["id"], world["client"], 0)
    res = await svc.accept(p["id"], world["client"], 1)
    assert res["appointment"]["status"] == "confirmed"


async def test_one_open_proposal_per_case_is_enforced_by_the_database(world):
    from pymongo.errors import DuplicateKeyError
    from app.db.collections import get_meeting_proposals_col
    now = datetime.now(timezone.utc)
    row = {"lawyer_id": world["lawyer"], "client_id": world["client"], "case_id": world["case"],
           "mode": "video", "duration_minutes": 60, "agenda": "x", "options": [_aligned(3)],
           "status": "open", "created_at": now, "updated_at": now}
    await get_meeting_proposals_col().insert_one({"_id": f"a-{secrets.token_hex(3)}", **row})
    with pytest.raises(DuplicateKeyError):
        await get_meeting_proposals_col().insert_one({"_id": f"b-{secrets.token_hex(3)}", **row})


def test_an_in_person_meeting_carries_no_joining_link():
    from pydantic import ValidationError
    from app.schemas.meeting_proposal import MeetingProposalCreate
    with pytest.raises(ValidationError, match="only for a video meeting"):
        MeetingProposalCreate(case_id="c", options=[_aligned(3)], mode="in_person",
                              agenda="Sign the papers", meeting_link="https://meet.example.com/x")


async def test_a_consultation_already_used_for_a_hire_is_not_offered_again(world):
    from app.db.collections import get_appointments_col, get_engagements_col
    from app.services import appointment_service
    past = _aligned(-3)
    appt_id = f"done-{secrets.token_hex(3)}"
    await get_appointments_col().insert_one({
        "_id": appt_id, "client_id": world["client"], "lawyer_id": world["lawyer"], "case_id": None,
        "scheduled_at": past, "end_at": past + timedelta(hours=1), "duration_minutes": 60,
        "status": "completed", "mode": "video", "schedule_version": 0,
        "created_at": past, "updated_at": past})
    offered = await appointment_service.list_consultations_for_hire(world["client"], world["lawyer"])
    assert appt_id in [a["id"] for a in offered]
    eng_id = f"eng-{secrets.token_hex(3)}"
    await get_engagements_col().insert_one({"_id": eng_id, "client_id": world["client"], "lawyer_id": world["lawyer"],
                                            "case_id": world["case"], "appointment_id": appt_id, "status": "declined"})
    try:
        offered = await appointment_service.list_consultations_for_hire(world["client"], world["lawyer"])
        assert appt_id not in [a["id"] for a in offered]
    finally:
        await get_engagements_col().delete_one({"_id": eng_id})


# ── expiry: one compare-and-set per proposal, one notice to the lawyer ──────

async def _stale(world, status="open", days_ago=1, **extra):
    from app.db.collections import get_meeting_proposals_col
    now = datetime.now(timezone.utc)
    _id = f"exp-{secrets.token_hex(4)}"
    await get_meeting_proposals_col().insert_one({
        "_id": _id, "lawyer_id": world["lawyer"], "client_id": world["client"], "case_id": world["case"],
        "case_title": "Rent dispute", "client_name": "Client Chooser", "mode": "video", "duration_minutes": 60,
        "agenda": "Prep", "options": [now - timedelta(days=days_ago)], "status": status,
        "created_at": now, "updated_at": now, **extra})
    return _id


async def _expiry_notices(user_id):
    from app.db.collections import get_notifications_col
    return [n async for n in get_notifications_col().find({"user_id": user_id, "type": "appointment_proposal_expired"})]


async def test_a_stale_proposal_expires_once_and_tells_only_the_lawyer(world):
    from app.db.collections import get_meeting_proposals_col
    from app.services import meeting_proposal_service as svc
    pid = await _stale(world)
    for _ in range(3):   # repeated reads and sweeps
        await svc.list_for(world["lawyer"], "lawyer")
        await svc.sweep_expired()
    row = await get_meeting_proposals_col().find_one({"_id": pid})
    assert row["status"] == "expired" and row["expiry_notice"] == "sent" and row.get("expired_at")
    notes = await _expiry_notices(world["lawyer"])
    assert len(notes) == 1
    assert notes[0]["payload"] == {"proposal_id": pid, "case_id": world["case"]}
    assert "did not choose" in notes[0]["body"] and "declin" not in notes[0]["body"].lower()
    assert await _expiry_notices(world["client"]) == []


async def test_a_proposal_with_any_future_time_stays_open(world):
    from app.db.collections import get_meeting_proposals_col
    from app.services import meeting_proposal_service as svc
    p = await svc.propose(world["lawyer"], _body(world))
    await svc.sweep_expired()
    assert (await get_meeting_proposals_col().find_one({"_id": p["id"]}))["status"] == "open"


@pytest.mark.parametrize("status", ["accepted", "declined", "withdrawn"])
async def test_a_finished_proposal_never_expires(world, status):
    from app.db.collections import get_meeting_proposals_col
    from app.services import meeting_proposal_service as svc
    pid = await _stale(world, status=status)
    await svc.sweep_expired()
    assert (await get_meeting_proposals_col().find_one({"_id": pid}))["status"] == status
    assert await _expiry_notices(world["lawyer"]) == []


async def test_concurrent_expiry_moves_it_once_and_notifies_once(world):
    import asyncio
    from app.services import meeting_proposal_service as svc
    await _stale(world)
    results = await asyncio.gather(*[svc.expire_stale({"case_id": world["case"]}) for _ in range(5)])
    assert sum(r["expired"] for r in results) == 1
    assert len(await _expiry_notices(world["lawyer"])) == 1


async def test_accept_racing_expiry_has_one_outcome(world):
    import asyncio
    from app.db.collections import get_appointments_col, get_meeting_proposals_col
    from app.services import meeting_proposal_service as svc
    pid = await _stale(world)
    out = await asyncio.gather(svc.accept(pid, world["client"], 0), svc.expire_stale({"_id": pid}),
                               return_exceptions=True)
    assert isinstance(out[0], (ConflictError, AppValidationError))
    assert (await get_meeting_proposals_col().find_one({"_id": pid}))["status"] == "expired"
    assert await get_appointments_col().count_documents({"client_id": world["client"]}) == 0
    assert len(await _expiry_notices(world["lawyer"])) == 1


async def test_a_crash_before_the_notice_is_retried_without_a_duplicate(world, monkeypatch):
    from app.db.collections import get_meeting_proposals_col
    from app.services import meeting_proposal_service as svc
    from app.services import notification_service
    pid = await _stale(world)
    real = notification_service.create_notification
    calls = {"n": 0}

    async def flaky(**kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("socket died")
        return await real(**kw)
    monkeypatch.setattr(notification_service, "create_notification", flaky)
    await svc.expire_stale({"_id": pid})
    row = await get_meeting_proposals_col().find_one({"_id": pid})
    assert row["status"] == "expired" and row["expiry_notice"] == "pending"
    assert await _expiry_notices(world["lawyer"]) == []

    # Crash AFTER the notice was created but before it was marked sent:
    await svc.expire_stale({"_id": pid})
    await get_meeting_proposals_col().update_one({"_id": pid}, {"$set": {"expiry_notice": "pending"}})
    await svc.expire_stale({"_id": pid})
    assert len(await _expiry_notices(world["lawyer"])) == 1
    assert (await get_meeting_proposals_col().find_one({"_id": pid}))["expiry_notice"] == "sent"


async def test_rows_expired_before_the_marker_are_not_notified(world):
    from app.services import meeting_proposal_service as svc
    await _stale(world, status="expired")   # an old row: no expiry_notice field
    await svc.sweep_expired()
    assert await _expiry_notices(world["lawyer"]) == []


# ── an accept that never finished (audit 2026-11-22, #12) ───────────────────
#
# accept() claims the proposal (`accepting`), writes the appointment, then
# marks it accepted. A crash in between used to leave it `accepting` forever:
# the unique index counts that as open, and withdraw/decline/accept/expiry all
# match only `open`, so the case could never get another proposal. A cancelled
# request is the realistic crash: CancelledError is not an Exception, so the
# release in accept()'s `except` never runs.

import asyncio  # noqa: E402


async def _crash_accept(svc, monkeypatch, proposal_id, client, *, after_write):
    from app.services import appointment_service
    real = appointment_service.create_confirmed_from_proposal

    async def dying(**kw):
        if after_write:
            await real(**kw)
        raise asyncio.CancelledError()

    monkeypatch.setattr(appointment_service, "create_confirmed_from_proposal", dying)
    with pytest.raises(asyncio.CancelledError):
        await svc.accept(proposal_id, client, 0)
    monkeypatch.setattr(appointment_service, "create_confirmed_from_proposal", real)


async def _age_claim(proposal_id, minutes=3):
    from app.db.collections import get_meeting_proposals_col
    await get_meeting_proposals_col().update_one(
        {"_id": proposal_id},
        {"$set": {"accepting_since": datetime.now(timezone.utc) - timedelta(minutes=minutes)}})


async def _raw(proposal_id):
    from app.db.collections import get_meeting_proposals_col
    return await get_meeting_proposals_col().find_one({"_id": proposal_id})


async def test_a_crash_before_the_booking_reopens_the_proposal(world, monkeypatch):
    from app.services import meeting_proposal_service as svc
    p = await svc.propose(world["lawyer"], _body(world))
    await _crash_accept(svc, monkeypatch, p["id"], world["client"], after_write=False)
    assert (await _raw(p["id"]))["status"] == "accepting"          # the stuck state

    # While fresh it is left alone: an accept may genuinely still be running.
    await svc.list_for(world["client"], "client")
    assert (await _raw(p["id"]))["status"] == "accepting"

    await _age_claim(p["id"])
    await svc.list_for(world["client"], "client")
    raw = await _raw(p["id"])
    assert raw["status"] == "open" and "accepting_since" not in raw
    # Open again: the client can choose a time, and nothing was booked twice.
    res = await svc.accept(p["id"], world["client"], 1)
    assert res["proposal"]["status"] == "accepted"
    from app.db.collections import get_appointments_col
    assert await get_appointments_col().count_documents({"proposal_id": p["id"]}) == 1


async def test_the_lawyer_can_withdraw_a_stuck_proposal_and_propose_again(world, monkeypatch):
    from app.services import meeting_proposal_service as svc
    p = await svc.propose(world["lawyer"], _body(world))
    await _crash_accept(svc, monkeypatch, p["id"], world["client"], after_write=False)
    with pytest.raises(ConflictError):                              # blocked while stuck
        await svc.propose(world["lawyer"], _body(world))
    await _age_claim(p["id"])
    out = await svc.withdraw(p["id"], world["lawyer"])
    assert out["status"] == "withdrawn"
    again = await svc.propose(world["lawyer"], _body(world))
    assert again["status"] == "open"


async def test_a_crash_after_the_booking_settles_as_accepted(world, monkeypatch):
    from app.services import meeting_proposal_service as svc
    p = await svc.propose(world["lawyer"], _body(world))
    await _crash_accept(svc, monkeypatch, p["id"], world["client"], after_write=True)
    from app.db.collections import get_appointments_col
    appt = await get_appointments_col().find_one({"proposal_id": p["id"]})
    assert appt is not None and (await _raw(p["id"]))["status"] == "accepting"

    await _age_claim(p["id"])
    rows = await svc.list_for(world["lawyer"], "lawyer")
    mine = [r for r in rows if r["id"] == p["id"]][0]
    assert mine["status"] == "accepted" and mine["appointment_id"] == appt["_id"]
    assert (await _raw(p["id"]))["chosen_index"] == 0
    # The case is free again for a new proposal.
    assert (await svc.propose(world["lawyer"], _body(world, options=[_aligned(6)])))["status"] == "open"


async def test_a_claim_from_before_this_fix_is_recovered(world):
    """Rows stuck before `accepting_since` existed carry no timestamp."""
    from app.db.collections import get_meeting_proposals_col
    from app.services import meeting_proposal_service as svc
    p = await svc.propose(world["lawyer"], _body(world))
    await get_meeting_proposals_col().update_one({"_id": p["id"]}, {"$set": {"status": "accepting"}})
    await svc.list_for(world["lawyer"], "lawyer")
    assert (await _raw(p["id"]))["status"] == "open"
