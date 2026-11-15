"""A failed intake analysis is a STATUS, and the client can retry it (2026-10-12).

The pipeline-failure fallback used to be stored as the case's `ai_summary`, so
the lawyer's case context read "AI structuring unavailable — case created
successfully." as the AI's account of the matter, and the intake was completed
with no way to run the analysis again. Now the case carries
`analysis_status: failed` and no summary, and `retry_analysis` re-runs it for
the client's own draft case, one retry at a time.
"""
from __future__ import annotations

import asyncio
import json
import secrets
from datetime import datetime, timezone

import pytest

from app.core.exceptions import ConflictError, NotFoundError
from app.services import case_service, intake_service

pytestmark = pytest.mark.integration

FAILED = {
    "summary": "AI structuring unavailable — case created successfully.",
    "applicable_laws": [], "recommended_actions": ["Consult a qualified Pakistani lawyer for advice."],
    "risk_level": None, "grounded": False, "grounding_status": "pipeline_failed",
}
GOOD = {
    "summary": "An inheritance dispute over a plot in Lahore.",
    "applicable_laws": ["Succession Act 1925"], "recommended_actions": ["Apply for a succession certificate"],
    "risk_level": "medium", "grounded": False, "grounding_status": "stubbed_in_test",
}


@pytest.fixture
async def clients(app_indexes):
    from app.db.collections import get_cases_col, get_intakes_col, get_users_col
    tag = secrets.token_hex(4)
    ids = [f"IR-C1-{tag}", f"IR-C2-{tag}"]
    now = datetime.now(timezone.utc)
    await get_users_col().insert_many([
        {"_id": i, "role": "client", "is_active": True, "email": f"{i}@test.invalid",
         "full_name": i, "province": "punjab", "created_at": now} for i in ids])
    yield ids
    await get_cases_col().delete_many({"client_id": {"$in": ids}})
    await get_intakes_col().delete_many({"client_id": {"$in": ids}})
    await get_users_col().delete_many({"_id": {"$in": ids}})


@pytest.fixture
def ai(monkeypatch):
    """The analysis the next call returns; every database write stays real."""
    state = {"next": FAILED, "calls": 0, "gate": None}

    async def fake_classify(description, user_selected):
        return user_selected, False

    async def fake_run_ai(**kw):
        state["calls"] += 1
        if state["gate"] is not None:
            await state["gate"].wait()
        return dict(state["next"])

    monkeypatch.setattr(intake_service, "_ai_classify_case_type", fake_classify)
    monkeypatch.setattr(intake_service, "_run_intake_ai", fake_run_ai)
    return state


async def _convert(client_id: str) -> dict:
    token = (await intake_service.start_intake(client_id))["session_token"]
    await intake_service.save_step(token, 1, {"province": "punjab", "party_role": "plaintiff"}, client_id)
    await intake_service.save_step(token, 2, {"case_type": "civil", "urgency": "medium"}, client_id)
    await intake_service.save_step(token, 3, {"incident_description": "My brother holds our late father's plot.",
                                              "incident_date": None, "incident_location": None}, client_id)
    await intake_service.save_step(token, 4, {"has_evidence": False, "evidence_description": None,
                                              "opposing_party": None}, client_id)
    await intake_service.save_step(token, 5, {"desired_outcome": "My share", "additional_notes": None}, client_id)
    return {"token": token, **(await intake_service.convert_to_case(token, client_id))}


async def _case(case_id):
    from app.db.collections import get_cases_col
    return await get_cases_col().find_one({"_id": case_id})


async def test_a_failed_analysis_is_a_status_not_the_case_summary(clients, ai):
    done = await _convert(clients[0])
    case = await _case(done["case_id"])
    assert case["analysis_status"] == "failed"
    assert case.get("ai_summary") is None, "the failure placeholder was stored as the case summary"
    assert case["status"] == "draft" and done["completed"] is True


async def test_a_good_analysis_is_marked_done(clients, ai):
    ai["next"] = GOOD
    done = await _convert(clients[0])
    case = await _case(done["case_id"])
    assert case["analysis_status"] == "done" and case["ai_summary"] == GOOD["summary"]


async def test_retry_replaces_the_failure_with_the_analysis(clients, ai):
    done = await _convert(clients[0])
    ai["next"] = GOOD
    assert await intake_service.retry_analysis(done["token"], clients[0]) == {"analysis_status": "done"}
    case = await _case(done["case_id"])
    assert case["analysis_status"] == "done" and case["ai_summary"] == GOOD["summary"]
    detail = await intake_service.get_intake(done["token"], clients[0])
    assert detail["ai_structured_case"]["grounding_status"] == "stubbed_in_test"
    # Nothing left to redo: a repeat does not run the model again.
    calls = ai["calls"]
    assert await intake_service.retry_analysis(done["token"], clients[0]) == {"analysis_status": "done"}
    assert ai["calls"] == calls


async def test_a_retry_that_fails_again_changes_nothing_and_can_be_retried(clients, ai):
    done = await _convert(clients[0])
    assert await intake_service.retry_analysis(done["token"], clients[0]) == {"analysis_status": "failed"}
    case = await _case(done["case_id"])
    assert case["analysis_status"] == "failed" and case.get("ai_summary") is None
    ai["next"] = GOOD
    assert (await intake_service.retry_analysis(done["token"], clients[0]))["analysis_status"] == "done"


async def test_only_the_owner_may_retry(clients, ai):
    done = await _convert(clients[0])
    with pytest.raises(NotFoundError):
        await intake_service.retry_analysis(done["token"], clients[1])


async def test_a_confirmed_case_is_not_re_analysed_here(clients, ai):
    done = await _convert(clients[0])
    await case_service.confirm_case(done["case_id"], clients[0], case_type="civil")
    with pytest.raises(ConflictError, match="already open"):
        await intake_service.retry_analysis(done["token"], clients[0])


async def test_an_unconverted_intake_has_nothing_to_retry(clients, ai):
    token = (await intake_service.start_intake(clients[0]))["session_token"]
    with pytest.raises(ConflictError, match="not produced a case"):
        await intake_service.retry_analysis(token, clients[0])


async def test_two_retries_at_once_run_the_analysis_once(clients, ai):
    done = await _convert(clients[0])
    ai["next"], ai["gate"] = GOOD, asyncio.Event()
    calls = ai["calls"]
    first = asyncio.create_task(intake_service.retry_analysis(done["token"], clients[0]))
    await asyncio.sleep(0.2)
    with pytest.raises(ConflictError, match="already being retried"):
        await intake_service.retry_analysis(done["token"], clients[0])
    ai["gate"].set()
    assert (await first)["analysis_status"] == "done"
    assert ai["calls"] == calls + 1


# ── the analysis rests only on what the client said (2026-10-12) ───────────

async def test_dont_know_answers_are_not_fed_to_the_analysis(clients, monkeypatch):
    """"Q: written contract? A: I don't know" seeded an analysis about a
    contract the client never mentioned."""
    from app.db.collections import get_intakes_col
    seen = {}

    async def fake_classify(description, user_selected):
        return user_selected, False

    async def fake_run_ai(**kw):
        seen["query"] = kw["query"]
        return dict(GOOD)
    monkeypatch.setattr(intake_service, "_ai_classify_case_type", fake_classify)
    monkeypatch.setattr(intake_service, "_run_intake_ai", fake_run_ai)
    token = (await intake_service.start_intake(clients[0]))["session_token"]
    for n, body in [(1, {"province": "punjab", "party_role": "plaintiff"}), (2, {"case_type": "civil", "urgency": "medium"}),
                    (3, {"incident_description": "My landlord kept my deposit.", "incident_date": None, "incident_location": None}),
                    (4, {"has_evidence": False, "evidence_description": None, "opposing_party": None}),
                    (5, {"desired_outcome": "My deposit back", "additional_notes": None})]:
        await intake_service.save_step(token, n, body, clients[0])
    await get_intakes_col().update_one({"session_token": token}, {"$set": {"clarification_qa": [
        {"q": "Is there a written contract?", "a": "I don't know"},
        {"q": "How much was the deposit?", "a": "Two lakh rupees"},
    ]}})
    await intake_service.convert_to_case(token, clients[0])
    assert "Two lakh rupees" in seen["query"]
    assert "written contract" not in seen["query"], "a question answered 'I don't know' reached the analysis"


def test_the_analysis_prompt_forbids_invented_facts():
    from app.ai.nodes.intake_node import SYSTEM_PROMPT
    assert "ONLY on what the client actually stated" in SYSTEM_PROMPT
    assert "has not yet described their situation" in SYSTEM_PROMPT


# ── the evidence gate's verdict reaches the case (Batch 4, 2026-10-12) ─────

async def test_17_gate_verdict_becomes_the_status_and_the_case_is_still_created(clients, monkeypatch):
    """No admissible law: the case exists, the analysis says so, no law and no
    risk reading are attached."""
    import app.ai.graph.supervisor as sup
    from app.db.collections import get_cases_col

    async def fake_classify(description, user_selected):
        return user_selected, False

    async def fake_graph(state):
        return {"answer": json.dumps({"summary": "The client says their landlord kept the deposit.",
                                      "law_citations": [], "recommended_actions": ["Consult a lawyer."],
                                      "risk_level": "medium"}),
                "evidence_gate": {"status": "no_relevant_evidence"}, "grounding_status": "no_bound_citations"}

    async def no_provenance(*a, **k):
        return None
    monkeypatch.setattr(intake_service, "_ai_classify_case_type", fake_classify)
    monkeypatch.setattr(sup.intake_graph, "ainvoke", fake_graph)
    monkeypatch.setattr(intake_service, "_record_intake_provenance", no_provenance)
    done = await _convert(clients[0])
    case = await get_cases_col().find_one({"_id": done["case_id"]})
    assert case["status"] == "draft"
    detail = await intake_service.get_intake(done["token"], clients[0])
    a = detail["ai_structured_case"]
    assert a["grounding_status"] == "no_relevant_evidence" and a["risk_level"] is None and a["law_citations"] == []
    assert a["evidence_gate"]["status"] == "no_relevant_evidence"
    assert "intake_understanding" in a and a["input_fact_fidelity"]["status"] in ("consistent", "issues", "unchecked")


async def test_20_a_retrieval_failure_is_retryable_and_the_retry_is_safe(clients, ai, monkeypatch):
    from app.db.collections import get_cases_col
    ai["next"] = {**FAILED, "grounding_status": "retrieval_error", "summary": "x"}
    done = await _convert(clients[0])
    case = await get_cases_col().find_one({"_id": done["case_id"]})
    assert case["analysis_status"] == "retrieval_failed"
    ai["next"] = GOOD
    assert (await intake_service.retry_analysis(done["token"], clients[0]))["analysis_status"] == "done"
    calls = ai["calls"]
    assert (await intake_service.retry_analysis(done["token"], clients[0]))["analysis_status"] == "done"
    assert ai["calls"] == calls, "a finished retry ran the model again"
