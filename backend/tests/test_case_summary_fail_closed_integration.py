"""Fail-closed AI summary and safe extraction input, through the real HTTP API and a test MongoDB (batch 8).

Integration tier: needs MongoDB (AAI_TEST_MONGO_URL). The model is stubbed;
nothing leaves the machine.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration

LEGACY = ("The tenant paid Rs. 50,000 on 3 March. The plaint can be rejected under Order VII Rule 11 CPC "
          "because it discloses no cause of action.")


@pytest.fixture
async def world(mongo):
    from app.db.collections import get_cases_col
    tag = secrets.token_hex(4)
    lawyer, client = f"CFC-L-{tag}", f"CFC-C-{tag}"
    now = datetime.now(timezone.utc)

    def case(n, **extra):
        return {"_id": f"CFC-{tag}-{n}", "case_number": f"CFC-{tag}-{n}", "title": f"Matter {n}",
                "client_id": client, "lawyer_id": lawyer, "status": "open", "province": "sindh",
                "case_type": "civil", "description": "My landlord locked my shop.", "ai_summary": LEGACY,
                "ai_summary_localized": {"ur": "آرڈر 7 رول 11 ضابطہ دیوانی"},
                "milestones": [], "hearing_dates": [], "created_at": now, "updated_at": now, **extra}
    docs = [case("with-desc"), case("no-desc", description="")]
    await get_cases_col().insert_many(docs)
    yield {"lawyer": lawyer, "client": client, "with": docs[0]["_id"], "without": docs[1]["_id"]}
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


async def test_a_failed_view_serves_the_case_without_any_ai_summary(world, monkeypatch):
    from app.ai import source_currency as sc
    from app.db.collections import get_cases_col

    def boom(c):
        raise RuntimeError("view broke")
    monkeypatch.setattr(sc, "case_cpc_view", boom)
    before = await get_cases_col().find_one({"_id": world["with"]})
    async with _as(world["lawyer"], "lawyer") as c:
        resp = await c.get(f"/cases/{world['with']}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ai_summary"] is None and "ai_summary_localized" not in body
    assert body["ai_summary_jurisdiction"]["status"] == "review_unavailable"
    assert "Order VII" not in resp.text
    assert await get_cases_col().find_one({"_id": world["with"]}) == before


async def test_extraction_refuses_a_legacy_summary_and_calls_no_model(world, monkeypatch):
    calls = []

    class _LLM:
        def invoke(self, messages):
            calls.append(messages)
            return SimpleNamespace(content='{"facts": "x"}')
    monkeypatch.setattr("app.ai.llm.get_llm", lambda **k: _LLM())
    async with _as(world["client"], "client") as c:
        resp = await c.post("/documents/extract", json={"case_id": world["without"], "template_type": "plaint_civil"})
    assert resp.status_code == 422, resp.text
    assert "Add the case facts to the case description" in resp.text
    assert calls == []


async def test_extraction_uses_the_clients_description_when_present(world, monkeypatch):
    calls = []

    class _LLM:
        def invoke(self, messages):
            calls.append(messages)
            return SimpleNamespace(content='{"facts": "x"}')
    monkeypatch.setattr("app.ai.llm.get_llm", lambda **k: _LLM())
    async with _as(world["client"], "client") as c:
        resp = await c.post("/documents/extract", json={"case_id": world["with"], "template_type": "plaint_civil"})
    assert resp.status_code == 200, resp.text
    sent = calls[-1][-1]["content"]
    assert "My landlord locked my shop." in sent and "Order VII" not in sent
