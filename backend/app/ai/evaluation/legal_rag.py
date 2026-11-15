"""Legal RAG evaluation: the dataset schema and the metrics (Batch 1, 2026-10-12).

Pure functions only. Nothing here touches Chroma, Mongo or an LLM, so every
metric is unit-tested on hand-built rankings; the runner
(scripts/eval_legal_rag.py) supplies real rankings.

WHAT A "RELEVANT" PASSAGE IS
----------------------------
Relevance is judged by LEGAL IDENTITY (instrument + provision), not by chunk id:
a contextual or re-chunked index (Batch 5) gives the same provision different
ids, and a metric keyed on ids would call the better index worse.

Each target carries two section fields because the current index is known to
be lossy: lettered sections lost their letter at ingestion (PPC 489-F is
stored as section "489"; measured on 72 PPC chunks, 2026-10-12).
  section        the true provision label, what a lawyer would cite
  index_section  what the CURRENT index stores for it, when that differs
Matching uses index_section when present, so the metric measures retrieval,
not the ingestion defect -- and the defect stays visible in the dataset instead
of being silently "fixed" by a looser matcher.

A target with section=None is instrument-level: any passage of that
instrument counts (used where the right provision is a judgement call).
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Optional

SCHEMA_VERSION = "legal-rag-eval-v1"

LANGUAGES = ("en", "ur", "roman_ur", "code_switched")
PURPOSES = ("intake", "client_chat", "lawyer_research")
QUESTION_TYPES = (
    "ordinary", "multi_issue", "ambiguous", "wrong_jurisdiction_trap",
    "similar_statute_trap", "superseded_law_trap", "live_rate", "court_statistic",
    "personal_record", "outcome_prediction", "no_corpus_evidence",
    "exact_citation", "negation",
    # Batch 5 (release-grade harness) categories.
    "simple_lookup", "factual_scenario", "unsupported_instrument", "federal_provincial_conflict",
)
SPLITS = ("dev", "regression", "holdout")
REVIEW_STATUSES = ("unreviewed_silver", "engineer_checked", "lawyer_reviewed")
# Lawyer review is only "gold" once agreed or adjudicated; a disputed item is
# not gold and must not be scored as such.
ADJUDICATION_STATUSES = ("not_reviewed", "agreed", "adjudicated", "disputed")
GOLD_ADJUDICATIONS = ("agreed", "adjudicated")
# What the corpus can do for this request, independent of retrieval.
CAPABILITY_CLASSES = ("corpus_capable", "instrument_not_in_corpus", "live_rate", "court_statistic",
                      "personal_record", "outcome_prediction", "mixed_supported_unsupported")
ANSWERABILITY_CLASSES = ("answerable", "partially_answerable", "unanswerable")
# The categories a release-grade set must cover (Batch 5). `category_coverage`
# reports which are missing rather than letting a thin set look complete.
REQUIRED_CATEGORIES = (
    "simple_lookup", "exact_citation", "factual_scenario", "multi_issue", "ambiguous", "negation",
    "unsupported_instrument", "live_rate", "personal_record", "federal_provincial_conflict",
    "wrong_jurisdiction_trap", "superseded_law_trap",
    "lang:en", "lang:ur", "lang:roman_ur", "lang:code_switched",
)


@dataclass
class IssueAnnotation:
    """One issue of a multi-issue request, annotated separately."""
    issue_id: str
    text: str
    answerable: bool
    relevant: list = field(default_factory=list)          # list[Target]
    unanswerable_reason: Optional[str] = None


@dataclass
class Target:
    statute: str
    section: Optional[str] = None          # true provision label; None = instrument-level
    index_section: Optional[str] = None    # what the current index stores, if different

    def match_section(self) -> Optional[str]:
        return self.index_section if self.index_section else self.section


@dataclass
class ExpectedFact:
    fact_key: str
    value: Optional[bool]                  # True / False / None (= unknown)


@dataclass
class EvalItem:
    query_id: str
    semantic_group_id: str
    query: str
    language: str
    purpose: str
    case_type: str
    province: str
    question_type: str
    answerable_by_corpus: bool
    split: str = "dev"
    review_status: str = "unreviewed_silver"
    unanswerable_reason: Optional[str] = None
    relevant: list[Target] = field(default_factory=list)
    acceptable_alternatives: list[Target] = field(default_factory=list)
    wrong_instruments: list[str] = field(default_factory=list)   # traps: retrieving these is an error
    required_issues: list[str] = field(default_factory=list)
    expected_facts: list[ExpectedFact] = field(default_factory=list)
    as_of: Optional[str] = None
    annotator: str = ""
    notes: str = ""
    # Free subset labels for slicing a report (e.g. "citation:lettered").
    tags: list[str] = field(default_factory=list)
    # ── Batch 5: review provenance and decomposed expectations ──────────
    label_version: str = "v1"
    reviewer_code: str = ""            # anonymised reviewer, e.g. "LR-03"; empty until reviewed
    reviewed_at: Optional[str] = None  # ISO timestamp of the review
    adjudication_status: str = "not_reviewed"
    capability_class: Optional[str] = None      # None = derived from question_type
    answerability_class: Optional[str] = None   # None = derived from answerable_by_corpus
    acceptable_abstention: Optional[bool] = None  # may the system decline without penalty?
    issues: list[IssueAnnotation] = field(default_factory=list)
    provenance_notes: str = ""
    schema_version: str = SCHEMA_VERSION

    def is_gold(self) -> bool:
        return self.review_status == "lawyer_reviewed" and self.adjudication_status in GOLD_ADJUDICATIONS

    def expected_capability(self) -> str:
        if self.capability_class:
            return self.capability_class
        derived = {"live_rate": "live_rate", "court_statistic": "court_statistic",
                   "personal_record": "personal_record", "outcome_prediction": "outcome_prediction",
                   "unsupported_instrument": "instrument_not_in_corpus"}
        if self.question_type in derived:
            return derived[self.question_type]
        if self.unanswerable_reason == "instrument_not_in_corpus":
            return "instrument_not_in_corpus"
        return "corpus_capable"

    def expected_answerability(self) -> str:
        if self.answerability_class:
            return self.answerability_class
        return "answerable" if self.answerable_by_corpus else "unanswerable"

    def may_abstain(self) -> bool:
        if self.acceptable_abstention is not None:
            return self.acceptable_abstention
        return not self.answerable_by_corpus


class DatasetError(ValueError):
    pass


def _target(d) -> Target:
    return d if isinstance(d, Target) else Target(**d)


def item_from_dict(d: dict) -> EvalItem:
    d = dict(d)
    d["relevant"] = [_target(t) for t in d.get("relevant") or []]
    d["acceptable_alternatives"] = [_target(t) for t in d.get("acceptable_alternatives") or []]
    d["expected_facts"] = [f if isinstance(f, ExpectedFact) else ExpectedFact(**f)
                           for f in d.get("expected_facts") or []]
    d["issues"] = [i if isinstance(i, IssueAnnotation) else IssueAnnotation(
        **{**i, "relevant": [_target(t) for t in i.get("relevant") or []]}) for i in d.get("issues") or []]
    item = EvalItem(**d)
    validate_item(item)
    return item


def validate_item(item: EvalItem) -> None:
    def bad(msg):
        raise DatasetError(f"{item.query_id}: {msg}")
    if not item.query_id or not item.semantic_group_id or not item.query.strip():
        bad("query_id, semantic_group_id and query are required")
    if item.language not in LANGUAGES:
        bad(f"language {item.language!r}")
    if item.purpose not in PURPOSES:
        bad(f"purpose {item.purpose!r}")
    if item.question_type not in QUESTION_TYPES:
        bad(f"question_type {item.question_type!r}")
    if item.split not in SPLITS:
        bad(f"split {item.split!r}")
    if item.review_status not in REVIEW_STATUSES:
        bad(f"review_status {item.review_status!r}")
    if item.answerable_by_corpus and not item.relevant:
        bad("an answerable item needs at least one relevant target")
    if not item.answerable_by_corpus and not item.unanswerable_reason:
        bad("an unanswerable item needs unanswerable_reason")
    if item.split == "holdout" and item.review_status != "lawyer_reviewed":
        bad("the holdout split is lawyer-reviewed only")
    if item.adjudication_status not in ADJUDICATION_STATUSES:
        bad(f"adjudication_status {item.adjudication_status!r}")
    if item.capability_class is not None and item.capability_class not in CAPABILITY_CLASSES:
        bad(f"capability_class {item.capability_class!r}")
    if item.answerability_class is not None and item.answerability_class not in ANSWERABILITY_CLASSES:
        bad(f"answerability_class {item.answerability_class!r}")
    # A review is a claim about a person's work: it must be complete or absent.
    if item.review_status == "lawyer_reviewed":
        if not item.reviewer_code or not item.reviewed_at or item.adjudication_status == "not_reviewed":
            bad("lawyer_reviewed needs reviewer_code, reviewed_at and an adjudication_status")
    elif item.reviewer_code or item.reviewed_at or item.adjudication_status != "not_reviewed":
        bad("review fields set on an item that is not lawyer_reviewed")
    for issue in item.issues:
        if issue.answerable and not issue.relevant:
            bad(f"issue {issue.issue_id}: an answerable issue needs a relevant target")
        if not issue.answerable and not issue.unanswerable_reason:
            bad(f"issue {issue.issue_id}: an unanswerable issue needs unanswerable_reason")


def load_jsonl(path: str | Path) -> list[EvalItem]:
    items = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if line.strip() and not line.lstrip().startswith("//"):
            try:
                items.append(item_from_dict(json.loads(line)))
            except (TypeError, json.JSONDecodeError) as exc:
                raise DatasetError(f"{path}:{n}: {exc}") from exc
    check_dataset(items)
    return items


def dump_jsonl(items: Iterable[EvalItem], path: str | Path) -> None:
    Path(path).write_text("\n".join(json.dumps(asdict(i), ensure_ascii=False) for i in items) + "\n",
                          encoding="utf-8")


def check_dataset(items: list[EvalItem]) -> None:
    """Whole-set rules: unique ids, and NO semantic group split across splits.

    Translations and paraphrases of one question share a semantic_group_id; if
    the English version is in dev and the Urdu one in holdout, the holdout is
    not held out.
    """
    seen, group_split = set(), {}
    for it in items:
        if it.query_id in seen:
            raise DatasetError(f"duplicate query_id {it.query_id}")
        seen.add(it.query_id)
        prev = group_split.setdefault(it.semantic_group_id, it.split)
        if prev != it.split:
            raise DatasetError(f"semantic group {it.semantic_group_id} spans splits {prev} and {it.split}")


def holdout_leakage(train: list[EvalItem], holdout: list[EvalItem]) -> list[str]:
    """Holdout items whose target provisions also appear in train (a true
    holdout experiment must report or exclude them)."""
    def keys(it):
        return {(t.statute, t.match_section()) for t in it.relevant}
    train_keys = set().union(*(keys(i) for i in train)) if train else set()
    return [h.query_id for h in holdout if keys(h) & train_keys]


# ── matching ─────────────────────────────────────────────────────────────────

_SEC = re.compile(r"[\s\-_.]")


def norm_section(sec) -> str:
    s = str(sec or "").strip().lower()
    s = re.sub(r"^(section|sec\.?|s\.|article|art\.?)\s*", "", s)
    return _SEC.sub("", s)


def is_relevant(passage: dict, targets: list[Target]) -> bool:
    """passage: {"statute": ..., "section": ...} from the ranked list."""
    st = (passage.get("statute") or "").strip()
    sec = norm_section(passage.get("section"))
    for t in targets:
        if st != t.statute:
            continue
        if t.match_section() is None or norm_section(t.match_section()) == sec:
            return True
    return False


def _target_hit(passage: dict, t: Target) -> bool:
    return is_relevant(passage, [t])


# ── retrieval metrics (ranked list of passages) ──────────────────────────────

def recall_at_k(ranked: list[dict], targets: list[Target], k: int) -> float:
    """Fraction of DISTINCT targets found in the top k."""
    if not targets:
        return 0.0
    top = ranked[:k]
    return sum(1 for t in targets if any(_target_hit(p, t) for p in top)) / len(targets)


def precision_at_k(ranked: list[dict], targets: list[Target], k: int) -> float:
    top = ranked[:k]
    if not top:
        return 0.0
    return sum(1 for p in top if is_relevant(p, targets)) / len(top)


def mrr(ranked: list[dict], targets: list[Target]) -> float:
    for i, p in enumerate(ranked, 1):
        if is_relevant(p, targets):
            return 1.0 / i
    return 0.0


def ndcg_at_k(ranked: list[dict], targets: list[Target], k: int) -> float:
    """Binary-gain nDCG; a provision counts once (its first occurrence)."""
    credited, dcg = set(), 0.0
    for i, p in enumerate(ranked[:k], 1):
        for j, t in enumerate(targets):
            if j not in credited and _target_hit(p, t):
                credited.add(j)
                dcg += 1.0 / math.log2(i + 1)
                break
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(targets), k) + 1))
    return dcg / ideal if ideal else 0.0


def wrong_instrument_rate(ranked: list[dict], wrong: list[str], k: int) -> float:
    """Share of the top k that comes from an instrument the item marks as a trap."""
    top = ranked[:k]
    if not top or not wrong:
        return 0.0
    return sum(1 for p in top if (p.get("statute") or "") in wrong) / len(top)


def jurisdiction_accuracy(ranked: list[dict], province: str, k: int) -> Optional[float]:
    """Share of the top k that is federal or from the item's own province."""
    top = ranked[:k]
    if not top:
        return None
    ok = {"federal", (province or "").lower()}
    return sum(1 for p in top if (p.get("province") or "").lower() in ok) / len(top)


# ── selective behaviour ──────────────────────────────────────────────────────

def selective_metrics(rows: list[tuple[bool, bool]]) -> dict:
    """rows: (answerable_by_corpus, system_declined).

    "Positive" = the corpus CANNOT answer. Precision/recall of declining, plus
    false-refusal rate on answerable items and unsafe-answer rate on
    unanswerable ones.
    """
    tp = sum(1 for a, d in rows if not a and d)
    fp = sum(1 for a, d in rows if a and d)
    fn = sum(1 for a, d in rows if not a and not d)
    answerable = sum(1 for a, _ in rows if a)
    unanswerable = len(rows) - answerable
    return {
        "decline_precision": tp / (tp + fp) if tp + fp else None,
        "decline_recall": tp / (tp + fn) if tp + fn else None,
        "false_refusal_rate": fp / answerable if answerable else None,
        "unsafe_answer_rate": fn / unanswerable if unanswerable else None,
        "coverage": sum(1 for _, d in rows if not d) / len(rows) if rows else None,
        "n_answerable": answerable,
        "n_unanswerable": unanswerable,
    }


def percentile(values: list[float], p: float) -> Optional[float]:
    if not values:
        return None
    v = sorted(values)
    idx = (len(v) - 1) * p
    lo, hi = math.floor(idx), math.ceil(idx)
    return v[lo] + (v[hi] - v[lo]) * (idx - lo)


def mean(values) -> Optional[float]:
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def exact_hit_at_1(ranked: list[dict], targets: list[Target]) -> float:
    """1.0 when the top passage IS a target provision (instrument and section)."""
    return 1.0 if ranked and any(t.match_section() is not None and _target_hit(ranked[0], t)
                                 for t in targets) else 0.0


def off_target_instrument_at_1(ranked: list[dict], targets: list[Target]) -> Optional[float]:
    """1.0 when the top passage comes from an instrument no target names (the
    "wrong instrument" rate for answerable items without listed traps)."""
    if not ranked or not targets:
        return None
    return 0.0 if (ranked[0].get("statute") or "") in {t.statute for t in targets} else 1.0


def category_coverage(items: list[EvalItem]) -> dict:
    """{category: item count} for every REQUIRED category, zeros included, so
    a gap in the set is reported instead of hidden behind an average."""
    counts = {c: 0 for c in REQUIRED_CATEGORIES}
    for it in items:
        if it.question_type in counts:
            counts[it.question_type] += 1
        key = f"lang:{it.language}"
        if key in counts:
            counts[key] += 1
    return counts


def label_summary(items: list[EvalItem]) -> dict:
    """How much of a set is gold. Reported with every result."""
    gold = sum(1 for i in items if i.is_gold())
    return {"n": len(items), "gold": gold, "silver_or_unadjudicated": len(items) - gold,
            "label_versions": sorted({i.label_version for i in items}),
            "status": "gold" if items and gold == len(items) else ("mixed" if gold else "silver")}
