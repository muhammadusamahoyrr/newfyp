"""Lookup indexes for collections that had none (audit 2026-11-22, low #8)."""
import pytest

pytestmark = pytest.mark.integration

EXPECTED = {
    "property_disputes": {"property_dispute_by_client", "property_dispute_by_lawyer"},
    "case_files": {"case_files_by_case_owner"},
    "appointment_files": {"appointment_files_by_appointment"},
    "appointment_thread_reads": {"appointment_thread_reads_by_user"},
}


async def test_lookup_indexes_are_created_and_used(mongo):
    from app.db.indexes import _lookup_indexes
    from app.db.mongodb import get_database

    await _lookup_indexes()
    await _lookup_indexes()                         # idempotent: a restart re-runs it
    db = get_database()
    for col, names in EXPECTED.items():
        have = set((await db[col].index_information()).keys())
        assert names <= have, f"{col} missing {names - have}"

    # The case files query the service runs is answered by the index.
    plan = await db["case_files"].find({"case_id": "k", "owner_id": "l"}).sort("created_at", -1).explain()
    assert "case_files_by_case_owner" in str(plan["queryPlanner"]["winningPlan"])
