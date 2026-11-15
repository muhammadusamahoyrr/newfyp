"""Evidence-gated, multilingual intake RAG (Batches 2-4 and 6, 2026-10-12).

The numbered required regressions from the remediation brief, mostly without a
model, Mongo or network. Each test names the guarantee it holds.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from app.ai import fact_fidelity
from app.ai.intake_understanding import (analysis_context, answer_polarity, build_understanding,
                                         retrieval_text)
from app.ai.nodes import intake_evidence_gate_node as gate
from app.ai.scoring import score_retrieval_batch


def chunk(statute="PPC 1860", section="379", province="federal", content="Whoever commits theft"):
    return {"statute": statute, "section_number": section, "province": province, "content": content,
            "chunk_id": f"{statute}:{section}"}


# 1 / 2 ── no forced weak chunks for intake; chat keeps its contract ─────────

def test_1_intake_policy_allows_zero_retained_chunks():
    weak = [chunk(content="unrelated text"), chunk(section="380", content="unrelated")]
    kept, _ = score_retrieval_batch("cheque bounced", weak, embedding_scores=[0.0, 0.0],
                                    llm_grades=[0, 0], min_chunks=0)
    assert kept == [], "intake received weak chunks the threshold rejected"


def test_2_chat_keeps_its_minimum_of_three():
    weak = [chunk(section=str(s), content="unrelated") for s in (1, 2, 3, 4)]
    kept, _ = score_retrieval_batch("cheque bounced", weak, embedding_scores=[0.0] * 4, llm_grades=[0] * 4)
    assert len(kept) == 3


async def test_1b_the_grader_drops_the_ungraded_tail_under_intake_policy(monkeypatch):
    from app.ai.nodes import retrieval_grader_node as g

    class Grades:
        def invoke(self, messages):
            return type("R", (), {"content": json.dumps([0] * 8)})()
    monkeypatch.setattr(g, "get_fast_llm", lambda *a, **k: Grades())
    monkeypatch.setattr(g, "similarity_scores", lambda *a, **k: [0.0] * 8)
    many = [chunk(section=str(s), content="unrelated") for s in range(1, 13)]
    base = {"query": "x", "retrieved_chunks": many, "case_type": "criminal"}
    intake = await g.retrieval_grader_node({**base, "retrieval_policy": {"min_chunks": 0, "include_ungraded": False}})
    chat = await g.retrieval_grader_node(base)
    assert intake["reranked_chunks"] == []
    assert len(chat["reranked_chunks"]) == 3 + 4, "chat contract changed (3 kept + 4 ungraded)"


# 3 / 11 / 12 ── the gate's separate decisions ───────────────────────────────

def test_3_retriever_failure_and_no_evidence_are_different_statuses():
    _, failed = gate.decide(chunks=[], retrieval_error=True, province="punjab",
                            user_text="my landlord kept my deposit after I left", relevance_score=None)
    _, empty = gate.decide(chunks=[], retrieval_error=False, province="punjab",
                           user_text="my landlord kept my deposit after I left", relevance_score=0.0)
    assert failed["status"] == "retrieval_error"
    assert empty["status"] == "no_relevant_evidence"


def test_11_wrong_jurisdiction_evidence_is_rejected():
    kept, rec = gate.decide(chunks=[chunk("Punjab Rented Premises Act 2009", "15", "punjab")],
                            retrieval_error=False, province="sindh",
                            user_text="my landlord in Karachi wants to evict me", relevance_score=0.6)
    assert kept == [] and rec["status"] == "wrong_jurisdiction"


def test_12_an_omitted_section_is_not_presented_as_current():
    kept, rec = gate.decide(chunks=[chunk("CrPC 1898", "562", "federal", "562. Power of Court ...")],
                            retrieval_error=False, province="federal",
                            user_text="can a first offender get probation", relevance_score=0.7)
    assert kept == [] and rec["status"] == "outdated_or_superseded"


def test_12b_a_lettered_section_is_not_dropped_as_its_omitted_parent():
    assert not gate._omitted("CrPC 1898", "10-A")


def test_weak_relevance_is_a_caveat_never_a_partial():
    """Gate v2: "partially_supported" is reserved for an issue-bound request;
    low relevance is recorded as a caveat on the status it would have had."""
    _, ok = gate.decide(chunks=[chunk()], retrieval_error=False, province="punjab",
                        user_text="someone stole my motorcycle from my house", relevance_score=0.7)
    _, weak = gate.decide(chunks=[chunk()], retrieval_error=False, province="punjab",
                          user_text="someone stole my motorcycle from my house", relevance_score=0.2)
    assert ok["status"] == "supported" and ok["caveats"] == []
    assert weak["status"] == "supported" and "low retrieval relevance" in weak["caveats"]


def test_gate_capability_is_intake_specific():
    _, rec = gate.decide(chunks=[], retrieval_error=False, province="punjab",
                         user_text="what is the current stamp duty rate for my house transfer", relevance_score=0.0)
    assert rec["status"] == "corpus_not_capable"
    # "Will I win?" is not a reason to refuse an intake analysis.
    _, rec2 = gate.decide(chunks=[chunk()], retrieval_error=False, province="punjab",
                          user_text="someone stole my motorcycle, will I win the case?", relevance_score=0.7)
    assert rec2["status"] == "supported"


# 4 / 5 / 18 / 19 ── the fact ledger ─────────────────────────────────────────

def test_4_a_no_to_a_contract_question_is_a_negated_fact_and_never_searched():
    u = build_understanding(story="My landlord kept my deposit.", clarification_qa=[
        {"q": "Do you have a written contract?", "a": "No", "fact_key": "written_contract_exists"}])
    assert len(u["facts"]) == 1 and u["facts"][0]["value"] is False
    assert u["facts"][0]["status"] == "negated"
    assert "contract" not in retrieval_text(u).lower()
    assert "NOT: written contract exists" in analysis_context(u)


def test_5_i_dont_know_stays_unknown():
    for a in ["I don't know", "pata nahi", "معلوم نہیں", "Not sure"]:
        assert answer_polarity(a) == "unknown", a
    u = build_understanding(story="x", clarification_qa=[{"q": "Written contract?", "a": "pata nahi",
                                                          "fact_key": "written_contract_exists"}])
    assert u["facts"] == [] and u["unknown_facts"][0]["fact_key"] == "written_contract_exists"


def test_4b_a_non_empty_answer_is_never_inferred_as_yes():
    assert answer_polarity("2 lakh rupees, paid in cash") == "freeform"
    assert answer_polarity("No, but my brother has a copy") == "freeform"


def test_18_the_same_facts_in_english_urdu_and_roman_urdu():
    stories = {"en": "No", "ur": "نہیں", "roman_ur": "nahi"}
    ledgers = [build_understanding(story="s", clarification_qa=[
        {"q": "q", "a": a, "fact_key": "written_agreement_exists"}])["facts"] for a in stories.values()]
    values = [(f[0]["fact_key"], f[0]["value"]) for f in ledgers]
    assert len(set(values)) == 1 and values[0] == ("written_agreement_exists", False)


def test_19_old_records_without_ids_or_keys_still_read():
    u = build_understanding(story="x", clarification_qa=[{"q": "Did he sign?", "a": "No"},
                                                         {"q": "When?", "a": "Last March"}])
    assert u["facts"] == [], "an unkeyed yes/no must not become an inferred fact"
    assert [s["question_id"] for s in u["statements"]] == ["q1", "q2"]


# 6 / 7 / 8 / 9 / 10 ── multi-query retrieval ────────────────────────────────

def test_6_the_original_story_stays_a_retrieval_channel():
    from app.ai.nodes.retrieval_node import _query_variants
    st = {"retrieval_policy": {"purpose": "intake", "multi_query": True}, "user_text": "my brother stole my bike"}
    v = dict(_query_variants(st, "my brother stole my bike\nlast week", "theft PPC 379 motorcycle"))
    assert v["story"] == "my brother stole my bike" and v["expanded"].startswith("theft")
    assert "client_words" in v


def test_9_variants_are_deduplicated_and_chat_stays_single():
    from app.ai.nodes.retrieval_node import _query_variants
    st = {"retrieval_policy": {"purpose": "intake", "multi_query": True}, "user_text": "Same  text"}
    assert len(_query_variants(st, "same text", "SAME TEXT")) == 1
    assert _query_variants({}, "a", "b") == [("expanded", "b")]


class _Doc:
    def __init__(self, cid, statute="PPC 1860", section="379"):
        self.page_content = cid
        self.metadata = {"chunk_id": cid, "statute": statute, "section_number": section, "province": "federal"}


class _Retriever:
    def __init__(self, fail=()):
        self.fail, self.calls = set(fail), []

    def invoke(self, q):
        self.calls.append(q)
        if q in self.fail:
            raise RuntimeError("branch down")
        return [_Doc(f"{q}-a"), _Doc("shared")]


async def test_10_one_failed_branch_does_not_discard_the_others():
    from app.ai.nodes.retrieval_node import _run_branches
    r = _Retriever(fail={"q2"})
    out = dict(await _run_branches(r, [("a", "q1"), ("b", "q2"), ("c", "q3")]))
    assert out["b"] is None and out["a"] and out["c"]


async def _run_node(monkeypatch, retriever, state):
    from app.ai.nodes import retrieval_node as rn
    seen = {}

    async def no_expand(q):
        return "EXPANDED " + q

    async def case_law(q, province=None):
        seen["case_law_query"] = q
        return []

    def affinity(chunks, text):
        seen["affinity_text"] = text
        return chunks, None
    monkeypatch.setattr(rn, "_expand_query", no_expand)
    monkeypatch.setattr(rn, "_retrieve_case_law", case_law)
    monkeypatch.setattr(rn, "build_retriever", lambda *a, **k: retriever)
    monkeypatch.setattr(rn, "apply_affinity", affinity)
    monkeypatch.setattr(rn, "_graph_hop2", lambda *a, **k: [])
    monkeypatch.setattr(rn, "_docs_to_chunks", lambda docs, prov="", **k: [
        {**d.metadata, "content": d.page_content} for d in docs])
    out = await rn.retrieval_node({"case_type": "criminal", "province": "punjab", **state})
    return out, seen


async def test_7_and_8_raw_words_drive_case_law_and_user_words_drive_affinity(monkeypatch):
    out, seen = await _run_node(monkeypatch, _Retriever(), {
        "query": "Client's account...\nAsked: \"Under Section 489-F?\"", "user_text": "my cheque bounced",
        "retrieval_query_supplement": "my cheque bounced\n2 lakh", "retrieval_policy": {"purpose": "chat"}})
    assert seen["case_law_query"] == "my cheque bounced\n2 lakh", "case law must use the client's words, not the rewrite"
    assert seen["affinity_text"] == "my cheque bounced", "affinity read AI-authored question text"


async def test_9b_fusion_is_deterministic_and_every_chunk_records_its_variants(monkeypatch):
    st = {"query": "q", "user_text": "story words", "retrieval_query_supplement": "client words",
          "retrieval_policy": {"purpose": "intake", "case_law": False, "multi_query": True}}
    a, _ = await _run_node(monkeypatch, _Retriever(), st)
    b, _ = await _run_node(monkeypatch, _Retriever(), st)
    ids_a = [c["chunk_id"] for c in a["retrieved_chunks"]]
    assert ids_a == [c["chunk_id"] for c in b["retrieved_chunks"]]
    assert ids_a.count("shared") == 1, "a chunk found by several queries must appear once"
    shared = next(c for c in a["retrieved_chunks"] if c["chunk_id"] == "shared")
    assert set(shared["retrieved_by"]) == {"expanded", "client_words", "story"}
    assert a["retrieval_trace"] and a["retrieval_error"] is False


async def test_3b_all_branches_failing_is_a_retrieval_error(monkeypatch):
    st = {"query": "q", "user_text": "s", "retrieval_query_supplement": "c",
          "retrieval_policy": {"purpose": "intake", "case_law": False}}
    r = _Retriever(fail={"EXPANDED c", "c", "s"})
    out, _ = await _run_node(monkeypatch, r, st)
    assert out["retrieval_error"] is True and out["retrieved_chunks"] == []


# 13 / 15 / 16 ── legal authority audit ───────────────────────────────────────

def _analysis(actions, citations):
    return json.dumps({"summary": "The client was cheated.", "law_citations": citations,
                       "recommended_actions": actions, "risk_level": "medium"})


def _judge_says_grounded(monkeypatch):
    import app.ai.nodes.intake_hallucination_node as node

    class Judge:
        def invoke(self, messages):
            return node.IntakeGroundingOutput(is_grounded=True, reason="ok", claim_support="1: supported\n2: supported\n3: supported")
    monkeypatch.setattr(node, "get_structured_llm", lambda *a, **k: Judge())
    return node


def test_13_an_uncited_legal_action_blocks_grounded(monkeypatch):
    node = _judge_says_grounded(monkeypatch)
    out = node.intake_hallucination_node({
        "answer": _analysis([{"text": "File a complaint under section 420", "kind": "legal", "evidence_ids": ["1"]},
                             {"text": "Claim damages of twice the amount", "kind": "legal", "evidence_ids": []}],
                            [{"evidence_id": "1", "statute": "PPC 1860", "section": "420", "note": "cheating"}]),
        "reranked_chunks": [chunk(section="420", content="420. Cheating")]})
    assert out["grounding_status"] != "grounded"
    assert out.get("uncited_legal_actions")


def test_13b_uncited_general_guidance_does_not_block_grounded(monkeypatch):
    node = _judge_says_grounded(monkeypatch)
    out = node.intake_hallucination_node({
        "answer": _analysis([{"text": "File a complaint under section 420", "kind": "legal", "evidence_ids": ["1"]},
                             {"text": "Keep copies of all receipts", "kind": "general", "evidence_ids": []}],
                            [{"evidence_id": "1", "statute": "PPC 1860", "section": "420", "note": "cheating"}]),
        "reranked_chunks": [chunk(section="420", content="420. Cheating")]})
    assert out["grounding_status"] == "grounded"


def test_15_citation_identity_comes_from_the_evidence():
    from app.ai.intake_evidence import bind_intake_citations
    ev = [{"id": "1", "kind": "statute", "statute": "PPC 1860", "section": "489",
           "content": "489- F.  Dishonestly issuing a cheque"}]
    good, _ = bind_intake_citations([{"evidence_id": "1", "statute": "Pakistan Penal Code", "section": "489-F"}], ev)
    assert (good[0]["status"], good[0]["statute"], good[0]["section"]) == ("bound", "PPC 1860", "489-F")
    bad, _ = bind_intake_citations([{"evidence_id": "1", "statute": "Code of Criminal Procedure", "section": "489"}], ev)
    assert bad[0]["status"] == "mismatched", "another instrument's name beside a real id was accepted"


def test_16_a_verification_outage_is_unchecked_not_verified(monkeypatch):
    import app.ai.nodes.intake_hallucination_node as node

    def boom(*a, **k):
        raise RuntimeError("provider down")
    monkeypatch.setattr(node, "get_structured_llm", boom)
    out = node.intake_hallucination_node({
        "answer": _analysis([{"text": "File under 420", "kind": "legal", "evidence_ids": ["1"]}],
                            [{"evidence_id": "1", "statute": "PPC 1860", "section": "420"}]),
        "reranked_chunks": [chunk(section="420", content="420. Cheating")]})
    assert out["grounding_status"] == "judge_failed" and out["is_grounded"] is False


# 14 ── input fact fidelity ───────────────────────────────────────────────────

def test_14_a_summary_cannot_invert_a_negation():
    u = build_understanding(story="My landlord kept my deposit of 200000 rupees.", clarification_qa=[
        {"q": "Written agreement?", "a": "No", "fact_key": "written_agreement_exists"}])
    inverted = fact_fidelity.check(summary="Under the written agreement the deposit was 200,000.", actions=[], understanding=u)
    kept = fact_fidelity.check(summary="There is no written agreement; the deposit was 200,000.", actions=[], understanding=u)
    invented = fact_fidelity.check(summary="The deposit was Rs. 250,000.", actions=[], understanding=u)
    assert any(i["type"] == "negation_inverted" for i in inverted["issues"])
    assert kept["status"] == "consistent"
    assert invented["issues"] == [{"type": "unsupported_number", "value": "250000"}]
    assert fact_fidelity.check(summary="", actions=[], understanding=u)["status"] == "unchecked"


# 21 / 22 ── caching and the reranker ────────────────────────────────────────

def test_21_the_intake_graph_has_no_response_cache():
    """Intake answers are built from one client's facts; the intake graph has
    no cache node, so nothing user-specific can be served to another user."""
    from app.ai.graph.supervisor import build_intake_graph
    assert not [n for n in build_intake_graph().nodes if "cache" in n]


def test_22_the_generic_ms_marco_cross_encoder_stays_off():
    """Measured and reverted (reranker.py): no code path may construct one."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent / "app"
    offenders = [str(p) for p in root.rglob("*.py") if "CrossEncoder(" in p.read_text(encoding="utf-8", errors="ignore")]
    assert offenders == []


def test_gate_runs_between_grader_and_analysis():
    from app.ai.graph.supervisor import build_intake_graph
    g = build_intake_graph().get_graph()
    edges = {(e.source, e.target) for e in g.edges}
    assert ("retrieval_grader_node", "intake_evidence_gate_node") in edges
    assert ("intake_evidence_gate_node", "intake_node") in edges
    assert ("retrieval_grader_node", "retrieval_node") not in edges, "the identical retry loop is back"


# ── an instrument the client names that the corpus does not hold ─────────────

@pytest.mark.parametrize("text,missing", [
    ("What damages can I claim under the Contract Act?", ["Contract Act"]),
    ("contract act ke tehat kitna harjana mil sakta hai", ["contract act"]),
    ("Can I file under the Specific Relief Act?", ["Specific Relief Act"]),
    ("Sindh Rented Premises Ordinance 1979 applies to my flat", ["Sindh Rented Premises Ordinance"]),
    ("theft under the Pakistan Penal Code", []),
    ("my rights under the Punjab Rented Premises Act", []),
    ("under the Transfer of Property Act", []),
    ("this Act says nothing", []),
    ("an act of violence by my neighbour", []),
])
def test_named_instruments_missing_from_the_corpus(text, missing):
    assert gate.named_missing_instruments(text) == missing


def test_a_missing_named_instrument_is_not_capable_whatever_was_retrieved():
    """Measured on the dev set: the Contract Act question came back 'supported'
    on CPC sections. Gate v1 made it 'partially_supported' -- which still
    generated law. Gate v2: not capable, chunks or not."""
    _, rec = gate.decide(chunks=[chunk("CPC 1908", "12")], retrieval_error=False, province="punjab",
                         user_text="What damages can I claim under the Contract Act?", relevance_score=0.7)
    assert rec["status"] == "corpus_not_capable" and rec["capability"] == "instrument_not_in_corpus"
    _, none = gate.decide(chunks=[], retrieval_error=False, province="punjab",
                          user_text="What damages can I claim under the Contract Act?", relevance_score=0.0)
    assert none["status"] == "corpus_not_capable"
