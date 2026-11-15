"""May the signed-in client review this lawyer NOW (2026-10-12).

Asked before the review form is shown, under the same rules as submitting:
a completed appointment or a retained engagement, and one review per
(client, lawyer). Per-client state, so its own authenticated read.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.exceptions import NotFoundError

CLIENT, LAWYER = "RE-CLIENT", "RE-LAWYER"


@pytest.fixture
async def people(mongo):
    from app.db.collections import (get_appointments_col, get_engagements_col,
                                    get_lawyer_reviews_col, get_users_col)
    await get_users_col().insert_many([
        {"_id": CLIENT, "full_name": "Client", "role": "client", "email": "c@re.test"},
        {"_id": LAWYER, "full_name": "Lawyer", "role": "lawyer", "email": "l@re.test", "is_active": True,
         "lawyer_profile": {"kyc_verified": True, "specializations": ["civil"]}},
    ])
    yield
    await get_users_col().delete_many({"_id": {"$in": [CLIENT, LAWYER]}})
    await get_engagements_col().delete_many({"client_id": CLIENT})
    await get_appointments_col().delete_many({"client_id": CLIENT})
    await get_lawyer_reviews_col().delete_many({"client_id": CLIENT})


async def _completed_appointment():
    from app.db.collections import get_appointments_col
    past = datetime.now(timezone.utc) - timedelta(days=2)
    await get_appointments_col().insert_one({
        "_id": secrets.token_urlsafe(8), "client_id": CLIENT, "lawyer_id": LAWYER, "status": "completed",
        "scheduled_at": past, "end_at": past + timedelta(hours=1), "duration_minutes": 60, "mode": "video"})


async def _engagement(status):
    from app.db.collections import get_engagements_col
    await get_engagements_col().insert_one({
        "_id": secrets.token_urlsafe(8), "case_id": secrets.token_urlsafe(8), "client_id": CLIENT,
        "lawyer_id": LAWYER, "status": status, "created_at": datetime.now(timezone.utc)})


async def _elig():
    from app.services import lawyer_service
    return await lawyer_service.review_eligibility(LAWYER, CLIENT)


async def test_no_relationship_cannot_review(people):
    assert await _elig() == {"can_review": False, "already_reviewed": False, "reason": "no_completed_relationship"}


async def test_a_completed_consultation_allows_a_review(people):
    await _completed_appointment()
    assert (await _elig())["can_review"] is True


async def test_an_accepted_engagement_allows_a_review(people):
    await _engagement("accepted")
    assert (await _elig())["can_review"] is True


async def test_an_engagement_that_never_began_does_not(people):
    await _engagement("requested")
    assert (await _elig())["can_review"] is False


async def test_once_reviewed_it_says_so(people):
    from app.services import lawyer_service
    await _completed_appointment()
    await lawyer_service.submit_review(LAWYER, CLIENT, 5, "Good")
    assert await _elig() == {"can_review": False, "already_reviewed": True, "reason": "already_reviewed"}


async def test_an_unknown_lawyer_is_not_found(people):
    from app.services import lawyer_service
    with pytest.raises(NotFoundError):
        await lawyer_service.review_eligibility("RE-NOBODY", CLIENT)


# ── the route: clients only, signed in ──

def _http(user: dict | None) -> AsyncClient:
    from app.main import app
    from app.dependencies import get_current_user
    app.dependency_overrides.clear()
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api/v1")


async def test_the_route_answers_a_client(people):
    await _completed_appointment()
    async with _http({"_id": CLIENT, "role": "client", "is_active": True}) as c:
        r = await c.get(f"/lawyers/{LAWYER}/review-eligibility")
    from app.main import app
    app.dependency_overrides.clear()
    assert r.status_code == 200 and r.json()["can_review"] is True


async def test_the_route_refuses_another_role_and_the_signed_out(people):
    from app.main import app
    async with _http({"_id": LAWYER, "role": "lawyer", "is_active": True}) as c:
        wrong = await c.get(f"/lawyers/{LAWYER}/review-eligibility")
    async with _http(None) as c:
        anon = await c.get(f"/lawyers/{LAWYER}/review-eligibility")
    app.dependency_overrides.clear()
    assert wrong.status_code == 403
    assert anon.status_code == 401
