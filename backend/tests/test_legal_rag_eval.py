"""The Legal RAG evaluation schema and metrics (Batch 1). Pure functions only."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.ai.evaluation import legal_rag as E

DEV = Path(__file__).resolve().parent.parent / "evals" / "legal_rag" / "datasets" / "dev_v1.jsonl"


def P(statute, section, province="federal"):
    return {"statute": statute, "section": section, "province": province}


T = E.Target


def test_identity_matching_uses_the_index_section_and_normalises():
    t = T("PPC 1860", "489-F", index_section="489")
    assert E.is_relevant(P("PPC 1860", "489"), [t])
    assert not E.is_relevant(P("PPC 1860", "489-F"), [t]), "the index stores 489; 489-F must not match the index label"
    assert E.is_relevant(P("Constitution of Pakistan 1973", "Article 199"), [T("Constitution of Pakistan 1973", "199")])
    assert not E.is_relevant(P("CrPC 1898", "199"), [T("Constitution of Pakistan 1973", "199")]), "same number, other instrument"
    assert E.is_relevant(P("Punjab Rented Premises Act 2009", "15"), [T("Punjab Rented Premises Act 2009")]), "instrument-level target"


def test_ranking_metrics_on_a_hand_built_ranking():
    targets = [T("PPC 1860", "379"), T("PPC 1860", "380")]
    ranked = [P("PPC 1860", "302"), P("PPC 1860", "379"), P("PPC 1860", "379"), P("PPC 1860", "380")]
    assert E.recall_at_k(ranked, targets, 1) == 0.0
    assert E.recall_at_k(ranked, targets, 2) == 0.5
    assert E.recall_at_k(ranked, targets, 4) == 1.0
    assert E.precision_at_k(ranked, targets, 4) == 0.75
    assert E.mrr(ranked, targets) == 0.5
    # A provision is credited once: the duplicate 379 at rank 3 adds nothing.
    import math
    want = (1 / math.log2(3) + 1 / math.log2(5)) / (1 + 1 / math.log2(3))
    assert E.ndcg_at_k(ranked, targets, 4) == pytest.approx(want)


def test_trap_and_jurisdiction_metrics():
    ranked = [P("Punjab Tenancy Act 1887", "39", "punjab"), P("Punjab Rented Premises Act 2009", "15", "punjab"),
              P("PPC 1860", "379", "federal"), P("Sindh Act", "1", "sindh")]
    assert E.wrong_instrument_rate(ranked, ["Punjab Tenancy Act 1887"], 2) == 0.5
    assert E.jurisdiction_accuracy(ranked, "punjab", 4) == 0.75
    assert E.jurisdiction_accuracy(ranked, "sindh", 4) == 0.5


def test_selective_metrics_separate_false_refusals_from_unsafe_answers():
    rows = [(True, False), (True, True), (False, True), (False, False), (False, True)]
    m = E.selective_metrics(rows)
    assert m["false_refusal_rate"] == 0.5
    assert m["unsafe_answer_rate"] == pytest.approx(1 / 3)
    assert m["decline_precision"] == pytest.approx(2 / 3)
    assert m["decline_recall"] == pytest.approx(2 / 3)
    assert m["coverage"] == 0.4


def test_a_semantic_group_cannot_span_splits():
    a = E.item_from_dict({"query_id": "a", "semantic_group_id": "g", "query": "q", "language": "en",
                          "purpose": "intake", "case_type": "civil", "province": "punjab",
                          "question_type": "ordinary", "answerable_by_corpus": True,
                          "relevant": [{"statute": "X"}]})
    b = E.item_from_dict({**E.asdict(a), "query_id": "b", "language": "ur", "split": "regression"})
    with pytest.raises(E.DatasetError, match="spans splits"):
        E.check_dataset([a, b])


def test_holdout_must_be_lawyer_reviewed_and_leakage_is_reported():
    base = {"semantic_group_id": "h", "query": "q", "language": "en", "purpose": "intake",
            "case_type": "civil", "province": "punjab", "question_type": "ordinary",
            "answerable_by_corpus": True, "relevant": [{"statute": "PPC 1860", "section": "379"}]}
    with pytest.raises(E.DatasetError, match="lawyer-reviewed"):
        E.item_from_dict({**base, "query_id": "h1", "split": "holdout"})
    h = E.item_from_dict({**base, "query_id": "h1", "split": "holdout", "review_status": "lawyer_reviewed",
                          "reviewer_code": "LR-01", "reviewed_at": "2026-10-13T00:00:00Z",
                          "adjudication_status": "agreed"})
    d = E.item_from_dict({**base, "query_id": "d1", "semantic_group_id": "d"})
    assert E.holdout_leakage([d], [h]) == ["h1"]


def test_unanswerable_items_need_a_reason_and_answerable_items_a_target():
    base = {"query_id": "x", "semantic_group_id": "x", "query": "q", "language": "en", "purpose": "intake",
            "case_type": "civil", "province": "punjab", "question_type": "live_rate"}
    with pytest.raises(E.DatasetError, match="unanswerable_reason"):
        E.item_from_dict({**base, "answerable_by_corpus": False})
    with pytest.raises(E.DatasetError, match="relevant target"):
        E.item_from_dict({**base, "answerable_by_corpus": True})


def test_the_dev_set_loads_and_is_marked_silver():
    items = E.load_jsonl(DEV)
    assert len(items) >= 40
    assert {i.review_status for i in items} == {"unreviewed_silver"}, "dev labels must not claim lawyer review"
    assert not [i for i in items if i.split == "holdout"], "the dev file must not carry a holdout"
    langs = {i.language for i in items}
    assert langs == {"en", "ur", "roman_ur"}
    assert any(i.question_type == "negation" and i.expected_facts for i in items)


# ── Batch 5: release-grade schema ────────────────────────────────────────────

_BASE = {"query_id": "r1", "semantic_group_id": "r", "query": "q", "language": "en", "purpose": "intake",
         "case_type": "criminal", "province": "punjab", "question_type": "ordinary",
         "answerable_by_corpus": True, "relevant": [{"statute": "PPC 1860", "section": "379"}]}


def test_a_lawyer_review_must_be_complete():
    with pytest.raises(E.DatasetError, match="reviewer_code"):
        E.item_from_dict({**_BASE, "review_status": "lawyer_reviewed"})
    with pytest.raises(E.DatasetError, match="reviewer_code"):
        E.item_from_dict({**_BASE, "review_status": "lawyer_reviewed", "reviewer_code": "LR-01"})
    ok = E.item_from_dict({**_BASE, "review_status": "lawyer_reviewed", "reviewer_code": "LR-01",
                           "reviewed_at": "2026-10-13T00:00:00Z", "adjudication_status": "agreed"})
    assert ok.is_gold()


def test_a_disputed_review_is_not_gold():
    d = E.item_from_dict({**_BASE, "review_status": "lawyer_reviewed", "reviewer_code": "LR-01",
                          "reviewed_at": "2026-10-13T00:00:00Z", "adjudication_status": "disputed"})
    assert not d.is_gold()


def test_silver_cannot_carry_review_fields():
    with pytest.raises(E.DatasetError, match="not lawyer_reviewed"):
        E.item_from_dict({**_BASE, "reviewer_code": "LR-01"})
    with pytest.raises(E.DatasetError, match="not lawyer_reviewed"):
        E.item_from_dict({**_BASE, "adjudication_status": "agreed"})


def test_capability_and_answerability_classes_are_validated_and_derived():
    with pytest.raises(E.DatasetError, match="capability_class"):
        E.item_from_dict({**_BASE, "capability_class": "magic"})
    live = E.item_from_dict({**_BASE, "question_type": "live_rate", "answerable_by_corpus": False,
                             "relevant": [], "unanswerable_reason": "live_rate"})
    assert live.expected_capability() == "live_rate" and live.expected_answerability() == "unanswerable"
    assert live.may_abstain()
    assert E.item_from_dict(_BASE).expected_capability() == "corpus_capable"


def test_multi_issue_annotations_are_validated():
    with pytest.raises(E.DatasetError, match="issue x"):
        E.item_from_dict({**_BASE, "issues": [{"issue_id": "x", "text": "t", "answerable": True}]})
    with pytest.raises(E.DatasetError, match="issue y"):
        E.item_from_dict({**_BASE, "issues": [{"issue_id": "y", "text": "t", "answerable": False}]})
    it = E.item_from_dict({**_BASE, "issues": [
        {"issue_id": "a", "text": "theft", "answerable": True, "relevant": [{"statute": "PPC 1860", "section": "379"}]},
        {"issue_id": "b", "text": "gold rate", "answerable": False, "unanswerable_reason": "live_rate"}]})
    assert isinstance(it.issues[0].relevant[0], E.Target)


def test_category_coverage_reports_gaps_as_zeros():
    cov = E.category_coverage([E.item_from_dict(_BASE)])
    assert set(cov) == set(E.REQUIRED_CATEGORIES)
    assert cov["lang:en"] == 1 and cov["federal_provincial_conflict"] == 0


def test_label_summary_never_calls_silver_gold():
    assert E.label_summary([E.item_from_dict(_BASE)])["status"] == "silver"


def test_exact_and_off_target_instrument_at_1():
    targets = [T("PPC 1860", "489-F")]
    assert E.exact_hit_at_1([P("PPC 1860", "489F")], targets) == 1.0
    assert E.exact_hit_at_1([P("PPC 1860", "489")], targets) == 0.0
    assert E.off_target_instrument_at_1([P("CPC 1908", "9")], targets) == 1.0
    assert E.off_target_instrument_at_1([P("PPC 1860", "1")], targets) == 0.0
    assert E.off_target_instrument_at_1([], targets) is None


@pytest.mark.parametrize("name", ["citation_probe_v1", "coverage_v1", "multi_issue_v1", "lettered_probe_v1"])
def test_the_supplementary_sets_load_and_are_silver(name):
    items = E.load_jsonl(DEV.parent / f"{name}.jsonl")
    assert items and E.label_summary(items)["status"] == "silver"
