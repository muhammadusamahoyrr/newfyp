"""Offline generation / abstention assessment (Batch 6). Deterministic checks
on hand-built generation records -- no model, no Chroma."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from app.ai.evaluation import legal_rag as E

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "eval_generation.py"


@pytest.fixture(scope="module")
def G():
    spec = importlib.util.spec_from_file_location("eval_generation_under_test", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _item(**kw):
    base = {"query_id": "g1", "semantic_group_id": "g", "query": "My friend's cheque of 50000 bounced.",
            "language": "en", "purpose": "intake", "case_type": "criminal", "province": "punjab",
            "question_type": "ordinary", "answerable_by_corpus": True,
            "relevant": [{"statute": "PPC 1860", "section": "489-F"}]}
    return E.item_from_dict({**base, **kw})


def _gen(status="supported", cites=None, actions=None, evidence=None, summary="A cheque of 50000 bounced.",
         gate=None, claims=None):
    return {"query_id": "g1", "latency_ms": 10.0,
            "analysis": {"summary": summary, "recommended_actions": actions or [],
                         "law_citations": cites or [], "evidence_gate": {"status": status, **(gate or {})},
                         "grounding_status": status, "uncited_legal_actions": [],
                         "claim_assessments": claims or []},
            "evidence": evidence if evidence is not None else
            [{"statute": "PPC 1860", "section": "489-F", "province": "federal", "content": "cheque"}]}


CITE = {"statute": "PPC 1860", "section": "489-F", "status": "bound", "province": "federal"}


def test_a_grounded_answer_with_bound_evidence_is_clean(G):
    r = G.assess_one(_item(), _gen(cites=[CITE]))
    assert r["C_abstention"] == "answered"
    assert r["B_authority"]["not_in_retrieved_evidence"] == 0 and r["B_authority"]["wrong_jurisdiction"] == 0
    assert r["B_authority"]["instrument_match_vs_silver"] == 1.0


def test_a_not_capable_request_with_law_is_an_unsafe_answer(G):
    item = _item(question_type="live_rate", answerable_by_corpus=False, relevant=[],
                 unanswerable_reason="live_rate")
    assert G.assess_one(item, _gen(status="corpus_not_capable", cites=[CITE]))["C_abstention"] == "UNSAFE_ANSWER"
    legal_action = [{"kind": "legal", "text": "File under s.489-F"}]
    assert G.assess_one(item, _gen(status="corpus_not_capable", actions=legal_action))["C_abstention"] == \
        "UNSAFE_ANSWER"
    assert G.assess_one(item, _gen(status="corpus_not_capable"))["C_abstention"] == "correct_abstention"


def test_declining_an_answerable_request_is_a_false_abstention(G):
    assert G.assess_one(_item(), _gen(status="no_relevant_evidence"))["C_abstention"] == "false_abstention"


def test_a_citation_absent_from_the_retrieved_passages_is_flagged(G):
    cite = {**CITE, "section": "420"}
    r = G.assess_one(_item(), _gen(cites=[cite]))
    assert r["B_authority"]["not_in_retrieved_evidence"] == 1


def test_a_wrong_province_citation_is_flagged(G):
    r = G.assess_one(_item(), _gen(cites=[{**CITE, "province": "sindh"}]))
    assert r["B_authority"]["wrong_jurisdiction"] == 1


def test_fidelity_catches_an_invented_number(G):
    r = G.assess_one(_item(), _gen(cites=[CITE], summary="A cheque of 90000 bounced."))
    assert r["A_fidelity"]["status"] == "issues"
    assert r["A_fidelity"]["version"] == "input-fact-fidelity-v1-limited"


def test_multilingual_consistency_compares_signatures(G):
    en = _item(query_id="g1")
    ur = _item(query_id="g2", language="ur", query="میرا چیک باؤنس ہو گیا")
    gens = [_gen(cites=[CITE]), {**_gen(status="no_relevant_evidence"), "query_id": "g2"}]
    rep = G.assess([en, ur], gens)
    d = rep["D_multilingual_consistency"]
    assert d["groups"] == 1 and d["same_abstention_rate"] == 0.0
    assert d["detail"]["g"]["core_conclusion"] == "not_measured"
    assert rep["labels"]["status"] == "silver"


BOUND_SCOPE = {"issue_scope": {"retrieval_bound": True}}


def test_a_clean_mixed_partial_is_correct_and_an_unbound_one_is_not(G):
    item = _item(capability_class="mixed_supported_unsupported")
    clean = G.assess_one(item, _gen(status="partially_supported", cites=[CITE], gate=BOUND_SCOPE))
    assert clean["C_abstention"] == "correct_partial" and clean["unsafe_reasons"] == []
    bad = {**CITE, "status": "mismatched", "chunk_id": "x", "section": "420"}
    r = G.assess_one(item, _gen(status="partially_supported", cites=[bad], gate=BOUND_SCOPE))
    assert r["C_abstention"] == "failed_partial"
    assert "unbound or mismatched citation" in r["partial_failures"]
    assert "failed_partial" in r["unsafe_reasons"]


def test_a_partial_without_issue_binding_is_not_correct(G):
    r = G.assess_one(_item(capability_class="mixed_supported_unsupported"),
                     _gen(status="partially_supported", cites=[CITE]))
    assert r["C_abstention"] == "failed_partial"
    assert "retrieval not bound to the supported issue" in r["partial_failures"]


M004_ACTION = "Lodge an FIR under Section 381 of the PPC."


def test_m004_unsupported_action_prevents_correct_partial(G):
    claims = [{"index": "2", "kind": "action", "action_kind": "legal", "text": M004_ACTION,
               "citation_status": "matched", "support": "unsupported"}]
    r = G.assess_one(_item(capability_class="mixed_supported_unsupported"),
                     _gen(status="partially_supported", cites=[CITE], gate=BOUND_SCOPE,
                          actions=[M004_ACTION], claims=claims))
    assert r["C_abstention"] == "failed_partial"
    assert "legal action judged unsupported is shown" in r["partial_failures"]
    assert "unsupported_legal_action_shown" in r["unsafe_reasons"]


def test_answered_unanswerable_counts_as_unsafe(G):
    item = _item(question_type="superseded_law_trap", answerable_by_corpus=False, relevant=[],
                 unanswerable_reason="omitted_provision")
    rep = G.assess([item], [_gen(cites=[CITE])])
    assert rep["C_abstention"] == {"answered_unanswerable": 1}
    assert rep["unsafe_answer_total"] == 1 and rep["answered_unanswerable_total"] == 1


D037_TARGET = {"statute": "CrPC 1898", "section": "562", "omitted": True,
               "omitted_by": "omitted by Probation of Offenders Ordinance XLV of 1960, s.16"}


def test_d037_style_output_is_unsafe(G):
    item = _item(query="Can a first offender be released on probation under section 562 of the CrPC?",
                 question_type="superseded_law_trap", answerable_by_corpus=False, relevant=[],
                 unanswerable_reason="omitted_provision")
    gen = _gen(cites=[{"statute": "CrPC 1898", "section": "388", "status": "bound", "province": "federal"}],
               actions=["If eligible, file an application for probation under Section 562 with the court."],
               gate={"requested_provisions": [D037_TARGET]},
               evidence=[{"statute": "CrPC 1898", "section": "388", "province": "federal", "content": "388."}])
    r = G.assess_one(item, gen)
    assert "answered_unanswerable" in r["unsafe_reasons"]
    assert "omitted_provision_presented" in r["unsafe_reasons"]


def test_the_currency_notice_alone_is_not_presenting_dead_law(G):
    notice = "CrPC 1898 section 562 is recorded as omitted by Probation of Offenders Ordinance."
    item = _item(question_type="superseded_law_trap", answerable_by_corpus=False, relevant=[],
                 unanswerable_reason="omitted_provision")
    gen = _gen(status="corpus_not_capable", summary=notice, gate={"requested_provisions": [D037_TARGET]})
    gen["analysis"]["currency_notice"] = notice
    r = G.assess_one(item, gen)
    assert r["unsafe_reasons"] == [] and r["C_abstention"] == "correct_abstention"


def test_zero_unsafe_is_impossible_with_any_unsafe_category(G):
    item = _item(capability_class="mixed_supported_unsupported")
    rep = G.assess([item], [_gen(status="partially_supported", cites=[CITE])])
    assert rep["unsafe_answer_total"] == 1 and rep["unsafe_answer_rate"] == 1.0
    assert rep["failed_partials"]["g1"]


def test_the_language_mapping_is_explicit(G):
    assert G.GENERATION_LANGUAGE == {"en": "en", "ur": "ur", "roman_ur": "en", "code_switched": "en"}


@pytest.mark.parametrize("query_lang,expected", [("en", "en"), ("ur", "ur"), ("roman_ur", "en")])
def test_generation_routes_the_items_language(G, monkeypatch, tmp_path, query_lang, expected):
    """The Urdu item runs the Urdu path; Roman Urdu's mapping is recorded."""
    import asyncio
    import json as _json
    from app.ai.graph import supervisor
    from app.services import intake_service as svc
    calls = {}

    async def fake_run(query, case_type, province, session_id, case_id, language="en", **k):
        calls["language"] = language
        return {"summary": "s", "recommended_actions": [], "grounding_status": "supported",
                "localized": ({"ur": {"status": "ok"}} if language == "ur" else {})}

    class G2:
        async def ainvoke(self, state):
            return {}
    monkeypatch.setattr(svc, "_run_intake_ai", fake_run)
    monkeypatch.setattr(supervisor, "intake_graph", G2())
    monkeypatch.setattr("app.db.chroma.connect_chroma", lambda: None)
    out = tmp_path / "g.jsonl"
    asyncio.run(G._generate([_item(language=query_lang)], out))
    rec = _json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    assert calls["language"] == expected
    assert rec["query_language"] == query_lang and rec["effective_generation_language"] == expected
    assert bool(rec["localization_status"]) is (expected == "ur")


def test_identity_is_matched_by_passage_not_by_label(G):
    """The binder restores 489-F from the header; the base index says 489."""
    ev = [{"statute": "PPC 1860", "section": "489", "province": "federal", "content": "cheque", "chunk_id": "c760"}]
    r = G.assess_one(_item(), _gen(cites=[{**CITE, "chunk_id": "c760"}], evidence=ev))
    assert r["B_authority"]["not_in_retrieved_evidence"] == 0


def test_string_actions_use_the_recorded_kinds(G):
    gen = _gen(status="corpus_not_capable")
    gen["analysis"]["recommended_actions"] = ["File an FIR under s.489-F"]
    gen["analysis"]["recommended_action_kinds"] = ["legal"]
    item = _item(question_type="live_rate", answerable_by_corpus=False, relevant=[], unanswerable_reason="live_rate")
    assert G.assess_one(item, gen)["C_abstention"] == "UNSAFE_ANSWER"
    del gen["analysis"]["recommended_action_kinds"]
    assert G.assess_one(item, gen)["B_authority"]["legal_actions"] == "not_recorded"


def test_an_unsupported_claim_the_guard_removed_does_not_fail_a_clean_partial(G):
    claims = [{"index": "2", "kind": "action", "action_kind": "legal", "text": M004_ACTION,
               "citation_status": "matched", "support": "unsupported"}]
    gen = _gen(status="partially_supported", cites=[CITE], gate=BOUND_SCOPE, actions=[], claims=claims)
    gen["analysis"]["output_guard"] = {"removed_actions": [{"text": M004_ACTION, "reason": "judged_unsupported"}]}
    r = G.assess_one(_item(capability_class="mixed_supported_unsupported"), gen)
    assert r["C_abstention"] == "correct_partial" and r["unsafe_reasons"] == []
    assert r["unsupported_claims_removed_by_guard"] == 1, "removed, and still reported"


def test_an_unsupported_summary_still_fails_the_partial(G):
    claims = [{"index": "1", "kind": "summary", "text": "Theft of a car is punishable.",
               "citation_status": "matched", "support": "unsupported"}]
    gen = _gen(status="partially_supported", cites=[CITE], gate=BOUND_SCOPE, claims=claims,
               summary="Theft of a car is punishable.")
    r = G.assess_one(_item(capability_class="mixed_supported_unsupported"), gen)
    assert r["C_abstention"] == "failed_partial"


def test_numbers_from_the_currency_notice_and_cited_instruments_are_sourced(G):
    notice = "CrPC 1898 section 562 is recorded as omitted by Ordinance XLV of 1960, s.16 dated 1960-11-01."
    item = _item(query="Can I get probation under section 562 of the CrPC?", question_type="superseded_law_trap",
                 answerable_by_corpus=False, relevant=[], unanswerable_reason="omitted_provision")
    gen = _gen(status="corpus_not_capable", summary=notice)
    gen["analysis"]["currency_notice"] = notice
    assert G.assess_one(item, gen)["A_fidelity"]["status"] == "consistent"


# ── provision-level legal accuracy ──────────────────────────────────────────

def _m001():
    return E.item_from_dict({
        "query_id": "m001", "semantic_group_id": "mg01", "language": "en", "purpose": "intake",
        "case_type": "criminal", "province": "punjab", "question_type": "multi_issue",
        "answerable_by_corpus": True,
        "query": "My friend gave me a cheque to repay the loan he owed me and it bounced. He threatened to kill me.",
        "relevant": [{"statute": "PPC 1860", "section": "489-F"}, {"statute": "PPC 1860", "section": "506"}],
        "issues": [{"issue_id": "cheque", "text": "cheque", "answerable": True,
                    "relevant": [{"statute": "PPC 1860", "section": "489-F"}]},
                   {"issue_id": "threat", "text": "threat", "answerable": True,
                    "relevant": [{"statute": "PPC 1860", "section": "506"}]}]})


def _cite(st, sec):
    return {"statute": st, "section": sec, "status": "bound", "province": "federal"}


def _L(G, item, cites, status="supported"):
    return G.assess_one(item, _gen(status=status, cites=cites, summary="s", evidence=[]))["L_provisions"]


def test_m001_with_415_and_police_order_4_is_a_wrong_provision_answer(G):
    r = _L(G, _m001(), [_cite("PPC 1860", "415"), _cite("Police Order 2002", "4")])
    assert r["outcome"] == "wrong_provision_answer"
    assert r["missing_expected"] == ["PPC 1860 s.489-F", "PPC 1860 s.506"]
    assert r["expected_instrument_recall"] == 1.0 and r["expected_provision_recall"] == 0.0, \
        "same instrument, wrong provisions"


def test_m001_with_489f_and_506_covers_both_issues(G):
    r = _L(G, _m001(), [_cite("PPC 1860", "489-F"), _cite("PPC 1860", "506")])
    assert r["outcome"] == "legally_supported_answer" and r["full_issue_coverage"]
    assert r["issue_coverage"] == {"covered": ["cheque", "threat"], "total": 2}


@pytest.mark.parametrize("cites,covered", [([("PPC 1860", "489-F")], ["cheque"]), ([("PPC 1860", "506")], ["threat"])])
def test_m001_with_one_issue_is_incomplete(G, cites, covered):
    r = _L(G, _m001(), [_cite(*c) for c in cites])
    assert r["outcome"] == "incomplete_issue_coverage" and r["issue_coverage"]["covered"] == covered


def test_a_correct_answer_with_an_extra_provision_reports_it(G):
    r = _L(G, _m001(), [_cite("PPC 1860", "489-F"), _cite("PPC 1860", "506"), _cite("PPC 1860", "415")])
    assert r["outcome"] == "unsupported_extra_provision" and r["wrong_provisions"] == ["PPC 1860 s.415"]


def test_a_correct_abstention_is_not_wrong_law(G):
    item = _item(question_type="live_rate", answerable_by_corpus=False, relevant=[], unanswerable_reason="live_rate")
    assert _L(G, item, [], status="corpus_not_capable")["outcome"] == "safe_abstention"


def test_489_does_not_satisfy_489f_and_489F_does(G):
    assert _L(G, _item(), [_cite("PPC 1860", "489")])["outcome"] == "wrong_provision_answer"
    assert _L(G, _item(), [_cite("PPC 1860", "489F")])["outcome"] == "legally_supported_answer"


def test_an_acceptable_alternative_is_counted_separately(G):
    item = _item(relevant=[{"statute": "PPC 1860", "section": "380"}],
                 acceptable_alternatives=[{"statute": "PPC 1860", "section": "379"}])
    r = _L(G, item, [_cite("PPC 1860", "379")])
    assert r["expected_provision_recall"] == 0.0 and r["alternative_provision_recall"] == 1.0
    assert r["outcome"] == "incomplete_issue_coverage", "an alternative alone does not cover the primary target"


def test_a_supported_gate_with_no_visible_law_is_a_false_abstention(G):
    assert _L(G, _item(), [])["outcome"] == "false_abstention"


def test_the_aggregate_reports_the_new_metrics(G):
    rep = G.assess([_m001()], [{**_gen(cites=[_cite("PPC 1860", "415")], evidence=[], summary="s"),
                                "query_id": "m001"}])
    acc = rep["L_legal_accuracy"]
    for k in ("provision_recall_mean", "provision_precision_mean", "full_issue_coverage_rate",
              "wrong_provision_answer_total", "incomplete_issue_coverage_total",
              "unsupported_extra_provision_total", "exact_provision_match_rate"):
        assert k in acc
    assert acc["wrong_provision_answer_total"] == 1 and rep["unsafe_answer_total"] == 0, \
        "a wrong-law answer is a legal-accuracy failure, reported apart from structural safety"


def test_an_uncited_action_the_guard_removed_does_not_fail_the_partial(G):
    claims = [{"index": "2", "kind": "action", "action_kind": "legal", "text": "Lodge an FIR.",
               "citation_status": "unresolved", "support": "unassessed"}]
    gen = _gen(status="partially_supported", cites=[CITE], gate=BOUND_SCOPE, actions=[], claims=claims)
    gen["analysis"]["uncited_legal_actions"] = ["2"]
    gen["analysis"]["output_guard"] = {"removed_actions": [{"text": "Lodge an FIR.", "reason": "not_bound_to_evidence"}]}
    r = G.assess_one(_item(capability_class="mixed_supported_unsupported"), gen)
    assert r["C_abstention"] == "correct_partial"
    gen["analysis"]["output_guard"] = {"removed_actions": []}
    gen["analysis"]["recommended_actions"] = ["Lodge an FIR."]
    assert G.assess_one(_item(capability_class="mixed_supported_unsupported"), gen)["C_abstention"] == "failed_partial"


def test_a_leaked_visible_provision_mismatch_is_structurally_unsafe(G):
    t = "Pursue a case under Section 381 of the PPC 1860."
    cite = {"statute": "PPC 1860", "section": "381-A", "status": "bound", "evidence_id": "1",
            "province": "federal"}
    claims = [{"index": "2", "kind": "action", "action_kind": "legal", "text": t,
               "citation_status": "matched", "support": "supported", "source_ids": ["1"]}]
    r = G.assess_one(_item(relevant=[{"statute": "PPC 1860", "section": "381-A"}]),
                     _gen(cites=[cite], actions=[t], claims=claims, summary="s", evidence=[]))
    assert "visible_provision_mismatch" in r["unsafe_reasons"] and r["visible_provision_mismatch"] == ["381"]
