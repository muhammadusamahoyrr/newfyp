"""Legacy case summaries through the real /cases API and a real (throwaway) MongoDB (batch 7).

A case stored the way a pre-batch-6 conversion wrote it -- `ai_summary` with a
CPC citation, no `ai_summary_cpc_checked` -- is read back over HTTP by the
assigned lawyer and the client. The response carries the warning first and no
CPC citation; the stored document is byte-for-byte unchanged.

Integration tier: needs MongoDB (AAI_TEST_MONGO_URL; the conftest refuses any
database whose name lacks the test suffix).
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration

SUMMARY = ("The tenant paid Rs. 50,000 on 3 March. The plaint can be rejected under Order VII Rule 11 CPC "
           "because it discloses no cause of action.")


@pytest.fixture
async def world(mongo):
    from app.db.collections import get_cases_col

    tag = secrets.token_hex(4)
    lawyer, client = f"CCV-L-{tag}", f"CCV-C-{tag}"
    now = datetime.now(timezone.utc)

    def case(n, province, **extra):
        return {"_id": f"CCV-{tag}-{n}", "case_number": f"CCV-{tag}-{n}", "title": f"Matter {n}",
                "client_id": client, "lawyer_id": lawyer, "status": "open", "province": province,
                "case_type": "civil", "ai_summary": SUMMARY, "milestones": [], "hearing_dates": [],
                "created_at": now, "updated_at": now, **extra}

    docs = [case("sindh", "sindh"), case("punjab", "punjab"),
            case("checked", "sindh", ai_summary="The tenant paid Rs. 50,000.",
                 ai_summary_cpc_checked="intake-cpc-jurisdiction-v2")]
    await get_cases_col().insert_many(docs)
    yield {"lawyer": lawyer, "client": client, "ids": {d["province"] if "checked" not in d["_id"] else "checked": d["_id"]
                                                       for d in docs}}
    await get_cases_col().delete_many({"_id": {"$in": [d["_id"] for d in docs]}})


@pytest.fixture(autouse=True)
def _clear_overrides():
    from app.main import app
    yield
    app.dependency_overrides.clear()


def _as(user_id: str, role: str) -> AsyncClient:
    from app.dependencies import get_current_user
    from app.main import app
    app.dependency_overrides[get_current_user] = lambda: {"_id": user_id, "role": role}
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api/v1")


async def _get(user, role, cid):
    async with _as(user, role) as c:
        resp = await c.get(f"/cases/{cid}")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_a_legacy_sindh_case_is_served_with_the_warning_and_stored_unchanged(world):
    from app.db.collections import get_cases_col
    cid = world["ids"]["sindh"]
    before = await get_cases_col().find_one({"_id": cid})
    for user, role in ((world["lawyer"], "lawyer"), (world["client"], "client")):
        body = await _get(user, role, cid)
        assert body["ai_summary"].startswith("Jurisdiction warning:") and "Sindh" in body["ai_summary"]
        assert "Order VII Rule 11" not in body["ai_summary"]
        assert body["ai_summary_jurisdiction"]["status"] == "legacy_unverified"
    assert await get_cases_col().find_one({"_id": cid}) == before


async def test_the_case_list_carries_the_same_view(world):
    async with _as(world["lawyer"], "lawyer") as c:
        resp = await c.get("/cases?page_size=50")
    assert resp.status_code == 200, resp.text
    by_id = {c["_id"]: c for c in resp.json()["items"]}
    assert by_id[world["ids"]["sindh"]]["ai_summary"].startswith("Jurisdiction warning:")
    assert by_id[world["ids"]["punjab"]]["ai_summary"] == SUMMARY


async def test_punjab_and_checked_cases_are_served_as_written(world):
    assert (await _get(world["lawyer"], "lawyer", world["ids"]["punjab"]))["ai_summary"] == SUMMARY
    checked = await _get(world["lawyer"], "lawyer", world["ids"]["checked"])
    assert checked["ai_summary"] == "The tenant paid Rs. 50,000."
    assert checked["ai_summary_jurisdiction"]["status"] == "checked"
