"""Bounded agentic issue decomposition (Batch 8) -- an offline experiment.

Pins: it is off unless explicitly enabled or offline; planner issues must quote
the client verbatim; every limit (issues, branches, model calls, timeout)
holds; unsupported issues never get legal evidence. Offline: fake planner and
fake retrieval, no Chroma, no LLM.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from app.ai import agentic_decomposition as AD

TEXT = ("My friend gave me a cheque to repay the loan and it bounced. "
        "When I asked for the money he threatened to kill me. "
        "Also, what is the current gold rate in Lahore today?")


def _planner(issues):
    return lambda msgs: json.dumps({"issues": issues})


def _retrieve(log):
    async def run(state):
        log.append(state["query"])
        return {"reranked_chunks": [{"statute": "PPC 1860", "section_number": "506", "province": "federal",
                                     "content": "criminal intimidation", "chunk_id": f"c{len(log)}"}]}
    return run


def test_it_refuses_to_run_unless_enabled_or_offline():
    with pytest.raises(RuntimeError, match="offline experiment"):
        asyncio.run(AD.decompose(TEXT, "criminal", "punjab"))


def test_the_flag_is_off_by_default():
    from app.core.config import settings
    assert settings.agentic_decomposition_enabled is False


def test_planner_quotes_must_be_verbatim():
    plan = json.dumps({"issues": [{"title": "a", "quote": "cheque to repay the loan and it bounced"},
                                  {"title": "b", "quote": "he defamed me on Facebook"}]})
    out = AD._validate_plan(plan, TEXT)
    assert [i["text"] for i in out] == ["cheque to repay the loan and it bounced"]


def test_garbage_planner_output_falls_back_to_sentences():
    out = asyncio.run(AD.detect_issues(TEXT, AD.Budget(), planner=lambda m: "no json here"))
    assert [i["source"] for i in out] == ["sentence"] * 3


def test_issue_cap_holds():
    many = [{"title": str(n), "quote": w} for n, w in enumerate(["cheque", "loan", "bounced", "money", "kill"])]
    out = asyncio.run(AD.detect_issues(TEXT, AD.Budget(), planner=_planner(many)))
    assert len(out) == AD.MAX_ISSUES


def test_unsupported_issue_gets_no_evidence_and_supported_ones_keep_their_issue():
    log = []
    plan = [{"title": "cheque", "quote": "a cheque to repay the loan and it bounced"},
            {"title": "threat", "quote": "When I asked for the money he threatened to kill me."},
            {"title": "rate", "quote": "what is the current gold rate in Lahore today?"}]
    res = asyncio.run(AD.decompose(TEXT, "criminal", "punjab", offline=True,
                                   planner=_planner(plan), retrieve=_retrieve(log)))
    states = {p["title"]: p for p in res["issues"]}
    assert states["rate"]["state"] == "unsupported" and states["rate"]["evidence"] == []
    assert states["threat"]["state"] == "supported"
    assert all(e["issue"] == states["threat"]["text"] for e in states["threat"]["evidence"])
    assert "gold" not in " ".join(log), "an unsupported issue must never be retrieved for"


def test_model_call_budget_is_never_exceeded():
    log = []
    plan = [{"title": str(n), "quote": q} for n, q in enumerate(
        ["a cheque to repay the loan and it bounced", "he threatened to kill me", "When I asked for the money"])]
    res = asyncio.run(AD.decompose(TEXT, "criminal", "punjab", offline=True,
                                   planner=_planner(plan), retrieve=_retrieve(log)))
    assert res["model_calls"] <= AD.MAX_MODEL_CALLS
    assert len(log) <= AD.MAX_BRANCHES


def test_a_slow_branch_cannot_exceed_the_total_timeout(monkeypatch):
    monkeypatch.setattr(AD, "TOTAL_TIMEOUT_S", 0.2)

    async def slow(state):
        await asyncio.sleep(5)
        return {}
    res = asyncio.run(AD.decompose(TEXT, "criminal", "punjab", offline=True,
                                   planner=_planner([{"title": "x", "quote": "he threatened to kill me"}]),
                                   retrieve=slow))
    assert res["timed_out"] is True and res["issues"] == []


def test_a_short_issue_is_ambiguous_not_retrieved():
    log = []
    res = asyncio.run(AD.decompose("Cheque bounced.", "criminal", "punjab", offline=True,
                                   planner=_planner([{"title": "c", "quote": "Cheque bounced."}]),
                                   retrieve=_retrieve(log)))
    assert res["issues"][0]["state"] == "ambiguous" and log == []


def test_the_retrieval_node_honours_the_budget_skip():
    from app.ai.nodes.retrieval_node import _skip_expansion
    assert _skip_expansion({"expansion_skip_all": True}, "anything at all") is True
    assert _skip_expansion({}, "anything at all") is False
