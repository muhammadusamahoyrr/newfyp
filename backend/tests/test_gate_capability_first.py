"""Intake evidence gate v2 -- the 2026-10-13 acceptance-review corrections.

Gate v1 let a capability failure through as "partially_supported" whenever ANY
chunk survived, and partial generated a full legal analysis. These are the
mutation tests the review asked for, plus the issue-binding contract:

  * an unrelated federal chunk + a live-rate request   -> no legal generation
  * an unrelated CPC chunk + "under the Contract Act" -> no legal generation
  * a genuinely mixed request -> legal analysis on the supported issue only,
    and only when retrieval was bound to that issue

Offline: no Chroma, no LLM, no Mongo.
"""
from __future__ import annotations

import json

import pytest

from app.ai.nodes import intake_evidence_gate_node as gate

MIXED = ("My landlord locked my shop and threw out my goods last week. "
         "What is the dollar rate today?")
RATE_SENTENCE = "What is the dollar rate today?"


def chunk(statute="PPC 1860", section="379", province="federal", content="Whoever commits theft"):
    return {"statute": statute, "section_number": section, "province": province, "content": content,
            "chunk_id": f"{statute}:{section}"}


def _gate_node(state):
    import asyncio
    return asyncio.run(gate.intake_evidence_gate_node(state))


# ── the two capability bypasses ─────────────────────────────────────────────

def test_unrelated_federal_chunk_and_a_live_rate_request_is_not_capable():
    state = {"reranked_chunks": [chunk("Customs Act 1969", "25", "federal", "value of imported goods")],
             "province": "punjab", "user_text": "What is the current gold rate in Lahore today?",
             "relevance_score": 0.8}
    out = _gate_node(state)
    assert out["evidence_gate"]["status"] == "corpus_not_capable"
    assert out["evidence_gate"]["capability"] == "live_rate"
    assert out["reranked_chunks"] == [], "a not-capable request must reach generation with NO law"


def test_unrelated_cpc_chunk_and_a_missing_contract_act_is_not_capable():
    state = {"reranked_chunks": [chunk("CPC 1908", "12", "federal", "Bar to further suit")],
             "province": "punjab",
             "user_text": "My supplier did not deliver the goods I paid for. I want to sue him under the Contract Act.",
             "relevance_score": 0.9}
    out = _gate_node(state)
    assert out["evidence_gate"]["status"] == "corpus_not_capable"
    assert out["evidence_gate"]["missing_instruments"] == ["Contract Act"]
    assert out["reranked_chunks"] == []


@pytest.mark.parametrize("text,kind", [
    ("What is the current gold rate in Lahore today?", "live_rate"),
    ("what is the current stamp duty rate for my house transfer", "live_rate"),
])
def test_a_pure_capability_request_is_not_capable_even_with_strong_chunks(text, kind):
    _, rec = gate.decide(chunks=[chunk(), chunk("CPC 1908", "12")], retrieval_error=False,
                         province="punjab", user_text=text, relevance_score=0.95)
    assert rec["status"] == "corpus_not_capable" and rec["capability"] == kind


def test_capability_is_decided_before_retrieval_errors():
    _, rec = gate.decide(chunks=[], retrieval_error=True, province="punjab",
                         user_text="What is the current gold rate in Lahore today?", relevance_score=None)
    assert rec["status"] == "corpus_not_capable"


# ── partial exists only with issue binding ──────────────────────────────────

def test_issue_scope_splits_the_answerable_story_from_the_rate_question():
    scope = gate.scope_issues(MIXED)
    assert [i["text"] for i in scope["unsupported"]] == [RATE_SENTENCE]
    assert scope["unsupported"][0]["kind"] == "live_rate"
    assert "dollar" not in scope["supported_text"] and "landlord" in scope["supported_text"]
    assert not scope["pure"]
    assert gate.strip_unsupported(MIXED, scope) == scope["supported_text"]


def test_a_mixed_request_without_binding_is_facts_only():
    _, rec = gate.decide(chunks=[chunk("PPC 1860", "441")], retrieval_error=False, province="punjab",
                         user_text=MIXED, relevance_score=0.8)
    assert rec["status"] == "corpus_not_capable"
    assert rec["issue_scope"]["retrieval_bound"] is False


def test_a_mixed_request_with_a_stale_binding_is_facts_only():
    stale = {"retrieval_bound": True, "unsupported": [{"text": "What is the gold rate?", "kind": "live_rate"}]}
    _, rec = gate.decide(chunks=[chunk("PPC 1860", "441")], retrieval_error=False, province="punjab",
                         user_text=MIXED, relevance_score=0.8, issue_scope=stale)
    assert rec["status"] == "corpus_not_capable"


def test_a_bound_mixed_request_is_partial_and_names_its_supported_issue():
    scope = {**gate.scope_issues(MIXED), "retrieval_bound": True}
    kept, rec = gate.decide(chunks=[chunk("PPC 1860", "441")], retrieval_error=False, province="punjab",
                            user_text=MIXED, relevance_score=0.8, issue_scope=scope)
    assert rec["status"] == "partially_supported"
    assert rec["issue_scope"]["supported_issue"] == scope["supported_text"]
    assert [i["text"] for i in rec["issue_scope"]["unsupported_issues"]] == [RATE_SENTENCE]
    assert kept


def test_a_bound_mixed_request_with_no_admissible_law_is_not_partial():
    scope = {**gate.scope_issues(MIXED), "retrieval_bound": True}
    _, rec = gate.decide(chunks=[], retrieval_error=False, province="punjab",
                         user_text=MIXED, relevance_score=0.0, issue_scope=scope)
    assert rec["status"] == "no_relevant_evidence"


def test_partial_is_never_reached_without_an_unsupported_issue():
    """Weak relevance, dropped passages and failed branches are caveats."""
    _, rec = gate.decide(chunks=[chunk(), chunk("Sindh Act", "5", "sindh")], retrieval_error=True,
                         province="punjab", user_text="someone stole my motorcycle from my house",
                         relevance_score=0.1)
    assert rec["status"] == "supported"
    assert set(rec["caveats"]) == {"some retrieval branches failed", "inadmissible passages removed",
                                   "low retrieval relevance"}


# ── the service binds retrieval to the supported issue ──────────────────────

async def test_the_service_retrieves_on_the_supported_issue_only(monkeypatch):
    from app.ai.graph import supervisor
    from app.services import intake_service as svc
    seen = {}

    class FakeGraph:
        async def ainvoke(self, state):
            seen["state"] = state
            _, record = gate.decide(chunks=[chunk("PPC 1860", "441")], retrieval_error=False,
                                    province=state["province"], user_text=state["user_text"],
                                    relevance_score=0.8, issue_scope=state.get("issue_scope"))
            return {"answer": json.dumps({"summary": "s", "recommended_actions": [], "risk_level": "low"}),
                    "evidence_gate": record, "citations": [{"statute": "PPC 1860", "section": "441"}]}

    async def no_provenance(*a, **k):
        return None
    monkeypatch.setattr(supervisor, "intake_graph", FakeGraph())
    monkeypatch.setattr(svc, "_record_intake_provenance", no_provenance)
    out = await svc._run_intake_ai(MIXED, "criminal", "punjab", "sess", "case",
                                   retrieval_query=MIXED + "\nShop: yes", user_text=MIXED)
    st = seen["state"]
    assert "dollar" not in st["retrieval_query_supplement"].lower()
    assert "landlord" in st["retrieval_query_supplement"] and "Shop: yes" in st["retrieval_query_supplement"]
    assert st["issue_scope"]["retrieval_bound"] is True
    assert out["evidence_gate"]["status"] == "partially_supported"


async def test_the_service_does_not_bind_a_missing_instrument_request(monkeypatch):
    from app.ai.graph import supervisor
    from app.services import intake_service as svc
    seen = {}
    text = "My supplier did not deliver the goods I paid for. I want to sue him under the Contract Act."

    class FakeGraph:
        async def ainvoke(self, state):
            seen["state"] = state
            _, record = gate.decide(chunks=[chunk("CPC 1908", "12")], retrieval_error=False,
                                    province=state["province"], user_text=state["user_text"],
                                    relevance_score=0.9, issue_scope=state.get("issue_scope"))
            return {"answer": json.dumps({"summary": "s", "recommended_actions": [], "risk_level": "low",
                                          "applicable_laws": ["CPC 1908 s.12"]}),
                    "evidence_gate": record, "citations": [{"statute": "CPC 1908", "section": "12"}]}

    async def no_provenance(*a, **k):
        return None
    monkeypatch.setattr(supervisor, "intake_graph", FakeGraph())
    monkeypatch.setattr(svc, "_record_intake_provenance", no_provenance)
    out = await svc._run_intake_ai(text, "civil", "punjab", "sess", "case", user_text=text)
    assert seen["state"]["issue_scope"] is None
    assert out["grounding_status"] == "corpus_not_capable"
    assert out["law_citations"] == [] and out["applicable_laws"] == [] and out["risk_level"] is None


# ── generation: facts-only vs issue-scoped ──────────────────────────────────

class _CaptureLLM:
    def __init__(self):
        self.messages = None

    def invoke(self, messages):
        from app.ai.nodes.intake_node import IntakeOutput
        self.messages = messages
        return IntakeOutput(summary="s", risk_level="low")


def _run_intake_node(monkeypatch, gate_record, chunks):
    from app.ai.nodes import intake_node as node
    llm = _CaptureLLM()
    monkeypatch.setattr(node, "get_structured_llm", lambda *a, **k: llm)
    out = node.intake_node({"query": MIXED, "province": "punjab", "case_type": "criminal",
                            "reranked_chunks": chunks, "case_law_chunks": [],
                            "evidence_gate": gate_record})
    return out, llm.messages


def test_not_capable_generation_sees_no_law(monkeypatch):
    _, rec = gate.decide(chunks=[chunk("Customs Act 1969", "25")], retrieval_error=False,
                         province="punjab", user_text="What is the current gold rate in Lahore today?",
                         relevance_score=0.8)
    out, messages = _run_intake_node(monkeypatch, rec, [chunk("Customs Act 1969", "25")])
    assert out["generation_evidence"] == []
    assert "(none retrieved)" in messages[1]["content"]
    assert "NO ADMISSIBLE LAW" in messages[0]["content"]


def test_partial_generation_is_confined_to_the_supported_issue(monkeypatch):
    scope = {**gate.scope_issues(MIXED), "retrieval_bound": True}
    _, rec = gate.decide(chunks=[chunk("PPC 1860", "441")], retrieval_error=False, province="punjab",
                         user_text=MIXED, relevance_score=0.8, issue_scope=scope)
    out, messages = _run_intake_node(monkeypatch, rec, [chunk("PPC 1860", "441")])
    system = messages[0]["content"]
    assert "ONLY PART OF THIS REQUEST IS ANSWERABLE" in system
    assert scope["supported_text"] in system and RATE_SENTENCE in system
    assert "NO ADMISSIBLE LAW" not in system
    assert out["generation_evidence"], "the supported issue keeps its bound evidence"


def test_supported_generation_has_no_scope_rule(monkeypatch):
    _, rec = gate.decide(chunks=[chunk()], retrieval_error=False, province="punjab",
                         user_text="someone stole my motorcycle from my house", relevance_score=0.8)
    _, messages = _run_intake_node(monkeypatch, rec, [chunk()])
    assert "ONLY PART" not in messages[0]["content"] and "NO ADMISSIBLE LAW" not in messages[0]["content"]


# ── multi-query is an A/B arm, off by default ───────────────────────────────

def test_multi_query_is_off_by_default_for_intake():
    from app.ai.nodes.retrieval_node import _query_variants
    from app.core.config import settings
    assert settings.retrieval_multi_query is False
    st = {"retrieval_policy": {"purpose": "intake"}, "user_text": "my brother stole my bike"}
    assert _query_variants(st, "my brother stole my bike last week", "theft PPC 379") == [
        ("expanded", "theft PPC 379")]


def test_multi_query_arm_never_reintroduces_an_unsupported_sentence():
    from app.ai.nodes.retrieval_node import _query_variants
    scope = {**gate.scope_issues(MIXED), "retrieval_bound": True}
    st = {"retrieval_policy": {"purpose": "intake", "multi_query": True}, "user_text": MIXED,
          "issue_scope": scope}
    variants = dict(_query_variants(st, scope["supported_text"] + " shop", "trespass shop goods"))
    assert all("dollar" not in q.lower() for q in variants.values())


def _offline_index():
    from app.ai.corpus_index import CorpusIndex, StatuteCoverage

    def cov(statute, secs):
        nums = frozenset(int("".join(ch for ch in x if ch.isdigit())) for x in secs)
        return StatuteCoverage(statute=statute, sections=frozenset(secs), numbered=nums,
                               highest=max(nums), artifacts=frozenset(), ceiling_outliers=frozenset(),
                               omitted=frozenset(), omission_records={})
    return CorpusIndex({
        "PPC 1860": cov("PPC 1860", [str(n) for n in range(1, 512)] + ["489F"]),
        "CPC 1908": cov("CPC 1908", [str(n) for n in range(1, 159)]),
        "Constitution of Pakistan 1973": cov("Constitution of Pakistan 1973", [str(n) for n in range(1, 281)]),
    })


@pytest.mark.parametrize("query,skip", [
    ("section 379 PPC punishment", True),                       # act + section
    ("Section 489-F PPC cheque", True),                         # lettered
    ("Article 199 of the Constitution", True),                  # article
    ("section 379", False),                                     # instrument uncertain
    ("what does s. 489-F say", False),                          # instrument uncertain
    ("dafa 302 ppc", False),                                    # Roman Urdu marker: parser not confident
    ("Section 489-F PPC and section 420 PPC", False),           # two citations: ambiguous
    ("order 7 rule 11 CPC", False),                             # Order/Rule numbering space
    ("under section 9 of the Contract Act", False),             # instrument not in corpus
    ("section PPC theft", False),                               # malformed
    ("someone stole my bike", False),
])
def test_expansion_skip_only_for_a_confident_corpus_citation(query, skip):
    from app.ai.nodes.retrieval_node import _skip_expansion
    idx = _offline_index()
    assert _skip_expansion({"expansion_skip": True}, query, idx) is skip
    assert _skip_expansion({}, query, idx) is False, "production still always expands"


def test_an_unsupported_instrument_citation_still_fails_the_capability_gate():
    """Skipping expansion never bypasses the gate: capability is query-side."""
    _, rec = gate.decide(chunks=[chunk("CPC 1908", "9")], retrieval_error=False, province="punjab",
                         user_text="Can I claim damages under section 73 of the Contract Act?",
                         relevance_score=0.9)
    assert rec["status"] == "corpus_not_capable"


# ── honest fidelity label ───────────────────────────────────────────────────

def test_fidelity_version_says_it_is_limited():
    from app.ai.fact_fidelity import FIDELITY_VERSION
    assert FIDELITY_VERSION == "input-fact-fidelity-v1-limited"
