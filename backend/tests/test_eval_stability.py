"""Stability dimensions and artifact provenance (2026-10-13 closure patch).

SAFE is not ACCURATE: each stability property is its own field, and runs from
different source states are never combined. Offline, synthetic records.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from app.ai.evaluation import artifact
from app.ai.evaluation import legal_rag as E

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "eval_stability.py"


@pytest.fixture(scope="module")
def S():
    spec = importlib.util.spec_from_file_location("eval_stability_under_test", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _m001():
    return E.item_from_dict({
        "query_id": "m001", "semantic_group_id": "mg01", "language": "en", "purpose": "intake",
        "case_type": "criminal", "province": "punjab", "question_type": "multi_issue", "answerable_by_corpus": True,
        "query": "My friend's cheque to repay a loan bounced. He threatened to kill me.",
        "relevant": [{"statute": "PPC 1860", "section": "489-F"}, {"statute": "PPC 1860", "section": "506"}],
        "issues": [{"issue_id": "cheque", "text": "c", "answerable": True,
                    "relevant": [{"statute": "PPC 1860", "section": "489-F"}]},
                   {"issue_id": "threat", "text": "t", "answerable": True,
                    "relevant": [{"statute": "PPC 1860", "section": "506"}]}]})


def _single(lang="en"):
    return E.item_from_dict({
        "query_id": "d007", "semantic_group_id": "g", "language": lang, "purpose": "intake",
        "case_type": "criminal", "province": "punjab", "question_type": "ordinary", "answerable_by_corpus": True,
        "query": "My brother was arrested. How can he get bail?",
        "relevant": [{"statute": "CrPC 1898", "section": "497"}]})


def _unanswerable():
    return E.item_from_dict({
        "query_id": "d040", "semantic_group_id": "g2", "language": "en", "purpose": "intake",
        "case_type": "civil", "province": "punjab", "question_type": "live_rate", "answerable_by_corpus": False,
        "unanswerable_reason": "live_rate", "query": "What is the gold rate today?"})


def rec(sections, status="supported", loc=None, failed=False, statute="PPC 1860"):
    cites = [{"statute": st, "section": s, "status": "bound", "province": "federal"} for st, s in
             [(statute, s) if isinstance(s, str) else s for s in sections]]
    return {"query_id": "x", "latency_ms": 1000.0,
            "localization_status": loc or {},
            "analysis": {"summary": "s", "recommended_actions": [], "law_citations": cites,
                         "evidence_gate": {"status": status},
                         "grounding_status": "pipeline_failed" if failed else status,
                         "uncited_legal_actions": [], "claim_assessments": []},
            "evidence": []}


def report(S, item, recs):
    return S.item_report(item, [S.run_view(item, r, i + 1) for i, r in enumerate(recs)])


def test_incomplete_coverage_is_safe_but_not_legally_stable(S):
    r = report(S, _m001(), [rec(["489-F", "506"]), rec(["489-F", "506"]), rec(["489-F"])])
    assert r["structurally_safe_all_runs"] and not r["expected_issue_coverage_all_runs"]
    assert not r["legally_stable_all_runs"] and not r["demo_stable"]


def test_changing_provision_sets_are_not_provision_set_stable(S):
    r = report(S, _single(), [rec([("CrPC 1898", "497")]), rec([("CrPC 1898", "497"), ("CrPC 1898", "496")]),
                              rec([("CrPC 1898", "497"), ("CrPC 1898", "60")])])
    assert not r["provision_set_stable"] and r["distinct_provision_sets"] == 3
    assert not r["legally_stable_all_runs"]


def test_unsupported_extra_provisions_are_not_legally_stable(S):
    r = report(S, _single(), [rec([("CrPC 1898", "497"), ("CrPC 1898", "60")])] * 3)
    assert r["provision_set_stable"] and not r["no_unsupported_extra_provision_runs"]
    assert not r["legally_stable_all_runs"] and r["demo_stable"], "demo-usable, but not accurate"


def test_a_wrong_provision_is_not_legally_or_demo_stable(S):
    r = report(S, _single(), [rec([("CrPC 1898", "60")])] * 3)
    assert not r["no_wrong_provision_runs"] and not r["legally_stable_all_runs"] and not r["demo_stable"]


def test_safe_abstention_on_an_unanswerable_request_is_legally_stable(S):
    r = report(S, _unanswerable(), [rec([], status="corpus_not_capable")] * 3)
    assert r["legally_stable_all_runs"] and r["expected_issue_coverage_all_runs"] is None


def test_urdu_safe_fallback_is_safe_but_not_a_successful_rendering(S):
    item = _single("ur")
    r = report(S, item, [rec([("CrPC 1898", "497")], loc={"ur": "ok"}),
                         rec([("CrPC 1898", "497")], loc={"ur": "failed"}),
                         rec([("CrPC 1898", "497")], loc={"ur": "ok"})])
    assert r["localization_stable"] and r["urdu_rendered_runs"] == 2 and r["urdu_safe_fallback_runs"] == 1


def test_one_unsafe_run_makes_structural_safety_false(S):
    bad = rec([("CrPC 1898", "497")])
    bad["analysis"]["recommended_actions"] = ["File under Section 498 CrPC."]
    bad["analysis"]["recommended_action_kinds"] = ["legal"]
    r = report(S, _single(), [rec([("CrPC 1898", "497")]), bad, rec([("CrPC 1898", "497")])])
    assert not r["structurally_safe_all_runs"]


def test_m001_like_two_of_three_threat_coverage_is_not_legally_stable(S):
    r = report(S, _m001(), [rec(["489-F", "503"]), rec(["489-F", "503", "506"]), rec(["489-F", "506"])])
    assert not r["expected_issue_coverage_all_runs"] and not r["legally_stable_all_runs"]


def test_a_pipeline_failure_is_an_availability_failure_not_a_pass(S):
    r = report(S, _single(), [rec([], failed=True), rec([("CrPC 1898", "497")]), rec([("CrPC 1898", "497")])])
    assert not r["available_all_runs"] and not r["demo_stable"] and not r["legally_stable_all_runs"]


# ── provenance ───────────────────────────────────────────────────────────────

def _prov(fp="aaaa", ds="h1", ev=artifact.EVALUATOR_VERSION):
    return {"provenance": {"source_fingerprint": fp, "datasets": {"d.jsonl": ds}, "evaluator_version": ev}}


def test_runs_from_one_contract_combine():
    assert artifact.combinable([_prov(), _prov()])[0]


@pytest.mark.parametrize("other", [_prov(fp="bbbb"), _prov(ds="h2"), _prov(ev="old")])
def test_runs_from_different_source_dataset_or_evaluator_are_refused(other):
    ok, why = artifact.combinable([_prov(), other])
    assert not ok and "contracts" in why


def test_a_record_without_provenance_is_refused():
    assert not artifact.combinable([_prov(), {"query_id": "x"}])[0]


def test_the_stability_report_refuses_mixed_runs(S, tmp_path):
    import json
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    a.write_text(json.dumps({**rec([]), "query_id": "d040", **_prov()}) + "\n", encoding="utf-8")
    b.write_text(json.dumps({**rec([]), "query_id": "d040", **_prov(fp="zzzz")}) + "\n", encoding="utf-8")
    out = S.build([str(a), str(b)], ["d040"], ["dev_v1"])
    assert out["refused"] is True


def test_the_fingerprint_changes_with_pipeline_source(tmp_path):
    (tmp_path / "x.py").write_text("a = 1\n", encoding="utf-8")
    one = artifact.source_fingerprint(("x.py",), tmp_path)
    (tmp_path / "x.py").write_text("a = 2\n", encoding="utf-8")
    assert artifact.source_fingerprint(("x.py",), tmp_path) != one


def test_the_env_file_is_never_fingerprinted():
    assert not any(".env" in f for f in artifact.PIPELINE_FILES)


def test_provider_events_keep_only_safe_fields():
    ev = [{"provider": "groq3", "model": "m", "outcome": "failure", "kind": "rate_limit", "status_code": 429,
           "secret_detail": "Bearer gsk_XXXX", "error": "org_123"}]
    safe = artifact.safe_events(ev)
    assert safe == [{"provider": "groq3", "model": "m", "outcome": "failure", "kind": "rate_limit",
                     "status_code": 429}]
    rr = artifact.run_record({"source_fingerprint": "f"}, ev, pipeline_failed=False, language="en")
    assert rr["provider_limit_hit"] is True and "gsk_" not in str(rr) and "org_123" not in str(rr)
