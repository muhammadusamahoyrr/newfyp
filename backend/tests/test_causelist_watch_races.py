"""Cause-list watches hold their limits under a double click.

`create_watch` reads first (already watching? free plan already used?) and then
inserts, so two simultaneous submits both passed both reads. The unique indexes
in `_causelist_indexes` make the database the guard.
"""
import asyncio
import secrets

import pytest

from app.core.exceptions import AppValidationError

pytestmark = pytest.mark.integration


@pytest.fixture
async def indexed(mongo, monkeypatch):
    from app.db.indexes import _causelist_indexes
    from app.services import subscription_service

    await _causelist_indexes()
    paid = {"value": False}

    async def _is_paid(_lawyer_id):
        return paid["value"]

    monkeypatch.setattr(subscription_service, "is_paid", _is_paid)
    return paid


def _lawyer() -> str:
    return f"CL-L-{secrets.token_hex(4)}"


async def _count(lawyer_id: str) -> int:
    from app.db.collections import get_causelist_watches_col
    return await get_causelist_watches_col().count_documents({"lawyer_id": lawyer_id})


async def test_a_double_click_on_the_same_case_makes_one_watch(indexed):
    from app.services import causelist_service as svc
    lawyer = _lawyer()
    results = await asyncio.gather(
        svc.create_watch(lawyer, "39043/26"), svc.create_watch(lawyer, "39043/26"),
        return_exceptions=True)
    assert sum(isinstance(r, dict) for r in results) == 1
    assert sum(isinstance(r, AppValidationError) for r in results) == 1
    assert await _count(lawyer) == 1


async def test_two_quick_submits_cannot_beat_the_free_plan_limit(indexed):
    from app.services import causelist_service as svc
    lawyer = _lawyer()
    results = await asyncio.gather(
        svc.create_watch(lawyer, "100/26"), svc.create_watch(lawyer, "200/26"),
        return_exceptions=True)
    assert sum(isinstance(r, dict) for r in results) == 1
    refused = [r for r in results if isinstance(r, AppValidationError)]
    assert len(refused) == 1 and "free plan" in refused[0].detail
    assert await _count(lawyer) == 1


async def test_a_paid_lawyer_still_gets_many_watches(indexed):
    from app.services import causelist_service as svc
    indexed["value"] = True
    lawyer = _lawyer()
    await asyncio.gather(svc.create_watch(lawyer, "1/26"), svc.create_watch(lawyer, "2/26"),
                         svc.create_watch(lawyer, "3/26"))
    assert await _count(lawyer) == 3


async def test_deleting_the_free_watch_frees_the_slot(indexed):
    from app.services import causelist_service as svc
    lawyer = _lawyer()
    first = await svc.create_watch(lawyer, "10/26")
    await svc.delete_watch(first["_id"], lawyer)
    await svc.create_watch(lawyer, "11/26")
    assert await _count(lawyer) == 1
