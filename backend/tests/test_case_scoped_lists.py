"""Case-scoped lists (2026-11-23, review item 5).

The client's case page downloaded every fee, hire request, agreement and
appointment and
filtered them in the browser. With a cap on each list (200 fees, 50
agreements) a case's own records could fall off the end. The lists now take
`case_id`, applied INSIDE the caller's own scope: it can only narrow what the
caller already sees, never widen it to someone else's records.
"""
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.integration

NOW = datetime.now(timezone.utc)


@pytest.fixture
async def seeded(mongo):
    from app.db.collections import get_agreements_col, get_appointments_col, get_engagements_col, get_payments_col
    client, other, lawyer = "CS-CLIENT", "CS-OTHER", "CS-LAWYER"
    pays = [
        {"_id": "CS-P1", "kind": "fee", "status": "created", "amount": 100, "payer_id": client, "payee_id": lawyer, "case_id": "CS-A", "created_at": NOW},
        {"_id": "CS-P2", "kind": "fee", "status": "paid", "amount": 200, "payer_id": client, "payee_id": lawyer, "case_id": "CS-B", "created_at": NOW - timedelta(minutes=1)},
        # someone else's fee on the SAME case id: never the client's
        {"_id": "CS-P3", "kind": "fee", "status": "created", "amount": 300, "payer_id": other, "payee_id": lawyer, "case_id": "CS-A", "created_at": NOW},
    ]
    engs = [
        {"_id": "CS-E1", "client_id": client, "lawyer_id": lawyer, "case_id": "CS-A", "status": "accepted", "created_at": NOW},
        {"_id": "CS-E2", "client_id": client, "lawyer_id": lawyer, "case_id": "CS-B", "status": "requested", "created_at": NOW},
        {"_id": "CS-E3", "client_id": other, "lawyer_id": lawyer, "case_id": "CS-A", "status": "requested", "created_at": NOW},
    ]
    party = lambda uid: {"user_id": uid, "signed": False}
    agrs = [
        {"_id": "CS-G1", "case_id": "CS-A", "status": "pending", "created_by": lawyer, "parties": [party(lawyer), party(client)], "created_at": NOW, "title": "A"},
        {"_id": "CS-G2", "case_id": "CS-B", "status": "pending", "created_by": lawyer, "parties": [party(lawyer), party(client)], "created_at": NOW, "title": "B"},
        {"_id": "CS-G3", "case_id": "CS-A", "status": "pending", "created_by": lawyer, "parties": [party(lawyer), party(other)], "created_at": NOW, "title": "C"},
        # a draft is private to its author even when the case matches
        {"_id": "CS-G4", "case_id": "CS-A", "status": "draft", "created_by": lawyer, "parties": [party(lawyer), party(client)], "created_at": NOW, "title": "D"},
    ]
    appts = [
        {"_id": "CS-A1", "client_id": client, "lawyer_id": lawyer, "case_id": "CS-A", "status": "pending",
         "scheduled_at": NOW + timedelta(days=1), "occupied_slots": [NOW + timedelta(days=1)],
         "time_suggestion": {"options": [NOW + timedelta(days=2)]}},
        {"_id": "CS-A2", "client_id": client, "lawyer_id": lawyer, "case_id": "CS-B", "status": "confirmed",
         "scheduled_at": NOW + timedelta(days=3), "occupied_slots": [NOW + timedelta(days=3)],
         "reschedule_proposal": {"by": "lawyer", "scheduled_at": NOW + timedelta(days=4), "expires_at": NOW + timedelta(days=1)}},
        {"_id": "CS-A3", "client_id": client, "lawyer_id": lawyer, "case_id": "CS-A", "status": "confirmed",
         "scheduled_at": NOW + timedelta(days=5), "occupied_slots": [NOW + timedelta(days=5)]},
        {"_id": "CS-A4", "client_id": other, "lawyer_id": lawyer, "case_id": "CS-A", "status": "pending",
         "scheduled_at": NOW + timedelta(days=6), "occupied_slots": [NOW + timedelta(days=6)],
         "time_suggestion": {"options": [NOW + timedelta(days=7)]}},
    ]
    # A setup interrupted by an assertion/index failure has no chance to run
    # its yield teardown. Make the fixture retry-safe without touching any row
    # outside its explicit synthetic ids.
    await get_payments_col().delete_many({"_id": {"$in": [p["_id"] for p in pays]}})
    await get_engagements_col().delete_many({"_id": {"$in": [e["_id"] for e in engs]}})
    await get_agreements_col().delete_many({"_id": {"$in": [a["_id"] for a in agrs]}})
    await get_appointments_col().delete_many({"_id": {"$in": [a["_id"] for a in appts]}})
    await get_payments_col().insert_many(pays)
    await get_engagements_col().insert_many(engs)
    await get_agreements_col().insert_many(agrs)
    await get_appointments_col().insert_many(appts)
    yield {"client": client, "other": other, "lawyer": lawyer}
    await get_payments_col().delete_many({"_id": {"$in": [p["_id"] for p in pays]}})
    await get_engagements_col().delete_many({"_id": {"$in": [e["_id"] for e in engs]}})
    await get_agreements_col().delete_many({"_id": {"$in": [a["_id"] for a in agrs]}})
    await get_appointments_col().delete_many({"_id": {"$in": [a["_id"] for a in appts]}})


async def test_payments_filter_to_one_case_inside_the_callers_own(seeded):
    from app.services import payment_service as ps
    ids = lambda rows: sorted(r["id"] for r in rows)
    assert ids(await ps.list_payments(seeded["client"], "client")) == ["CS-P1", "CS-P2"]
    assert ids(await ps.list_payments(seeded["client"], "client", "CS-A")) == ["CS-P1"]
    assert ids(await ps.list_payments(seeded["client"], "client", "CS-B")) == ["CS-P2"]
    # another client's fee on the same case never appears
    assert "CS-P3" not in ids(await ps.list_payments(seeded["client"], "client", "CS-A"))


async def test_hire_requests_filter_to_one_case_inside_the_callers_own(seeded):
    from app.services import engagement_service as es
    ids = lambda rows: sorted(r["id"] for r in rows)
    assert ids(await es.list_engagements(seeded["client"], "client")) == ["CS-E1", "CS-E2"]
    assert ids(await es.list_engagements(seeded["client"], "client", None, "CS-A")) == ["CS-E1"]
    # the lawyer sees both clients' requests on the case, and only that case
    assert ids(await es.list_engagements(seeded["lawyer"], "lawyer", None, "CS-A")) == ["CS-E1", "CS-E3"]


async def test_agreements_filter_to_one_case_without_widening_visibility(seeded):
    from app.services import agreement_service as ag
    ids = lambda res: sorted(r["_id"] if "_id" in r else r["id"] for r in res["items"])
    assert ids(await ag.list_agreements(seeded["client"], status="pending")) == ["CS-G1", "CS-G2"]
    assert ids(await ag.list_agreements(seeded["client"], status="pending", case_id="CS-A")) == ["CS-G1"]
    # not a party to CS-G3, and CS-G4 is someone else's draft: neither appears
    assert ids(await ag.list_agreements(seeded["client"], case_id="CS-A")) == ["CS-G1"]


async def test_appointment_actions_filter_to_one_case_inside_the_callers_own(seeded):
    from app.repositories.appointment_repo import AppointmentRepository
    repo = AppointmentRepository()
    result = await repo.find_for_client(
        seeded["client"], None, 1, 50, case_id="CS-A", needs_action=True)
    assert [row["_id"] for row in result.items] == ["CS-A1"]


def test_the_routes_accept_case_id():
    """The query parameter is declared on every case-scoped list route."""
    import inspect
    from app.api.v1.routes import agreements, appointments, engagements, payments
    for fn in (payments.list_mine, engagements.list_engagements, agreements.list_agreements,
               appointments.list_appointments):
        assert "case_id" in inspect.signature(fn).parameters, fn.__name__
    assert "needs_action" in inspect.signature(appointments.list_appointments).parameters
