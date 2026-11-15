"""eval_capability.py — capability / answerability classification, measured on
its own (Batch 5). Query-side only: no retrieval, no model, deterministic.

  python scripts/eval_capability.py [--datasets dev_v1,citation_probe_v1,coverage_v1,multi_issue_v1,lettered_probe_v1]

Predicts what the intake gate decides BEFORE evidence (gate v2): a named
instrument the corpus lacks, a pure live-rate / court-statistic /
personal-record request, a mixed request, an outcome prediction (which intake
still analyses), or corpus_capable. Compared with each item's expected
capability class. Reported separately from retrieval, grounding, fidelity
and abstention -- never folded into one score.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.ai.evaluation import legal_rag as E  # noqa: E402

NOT_CAPABLE = {"instrument_not_in_corpus", "live_rate", "court_statistic", "personal_record"}


def predict(query: str) -> str:
    from app.ai.nodes.intake_evidence_gate_node import scope_issues
    from app.ai.pipelines.answerability import check
    sc = scope_issues(query)
    if sc["missing_instruments"]:
        return "instrument_not_in_corpus"
    if sc["unsupported"]:
        return sc["unsupported"][0]["kind"] if sc["pure"] else "mixed_supported_unsupported"
    v = check(query)
    if v and v.kind == "outcome_prediction":
        return "outcome_prediction"
    return "corpus_capable"


def evaluate(items: list[E.EvalItem]) -> dict:
    rows = [{"query_id": i.query_id, "language": i.language, "expected": i.expected_capability(),
             "predicted": predict(i.query)} for i in items]
    confusion = Counter((r["expected"], r["predicted"]) for r in rows)
    exp_nc = [r for r in rows if r["expected"] in NOT_CAPABLE]
    exp_ok = [r for r in rows if r["expected"] not in NOT_CAPABLE]
    by_lang = defaultdict(list)
    for r in rows:
        by_lang[r["language"]].append(r)
    acc = lambda rs: (sum(r["expected"] == r["predicted"] for r in rs) / len(rs)) if rs else None  # noqa: E731
    return {
        "schema": "capability-eval-v1", "timestamp": datetime.now(timezone.utc).isoformat(),
        "labels": E.label_summary(items), "n": len(rows),
        "accuracy": acc(rows),
        "accuracy_by_language": {k: acc(v) for k, v in by_lang.items()},
        # The two errors that matter, separately.
        "missed_not_capable": [r["query_id"] for r in exp_nc if r["predicted"] not in NOT_CAPABLE],
        "false_not_capable": [r["query_id"] for r in exp_ok if r["predicted"] in NOT_CAPABLE],
        "confusion": {f"{e} -> {p}": n for (e, p), n in sorted(confusion.items())},
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", default="dev_v1,citation_probe_v1,coverage_v1,multi_issue_v1,lettered_probe_v1")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    items = []
    for ds in args.datasets.split(","):
        items += E.load_jsonl(BACKEND_DIR / "evals" / "legal_rag" / "datasets" / f"{ds}.jsonl")
    rep = evaluate(items)
    out = Path(args.out or BACKEND_DIR / "evals" / "legal_rag" / "results" /
               f"capability_eval_{datetime.now().strftime('%Y-%m-%d_%H%M')}.json")
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in rep.items() if k != "rows"}, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
