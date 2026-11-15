"""make_review_packet.py — build a lawyer-review packet from eval datasets (Batch 5).

  python scripts/make_review_packet.py --out evals/legal_rag/review/packet_2026-10-13.csv

Writes a CSV a reviewing lawyer fills in: the engineer's PROPOSED labels next to
blank review columns. Nothing here marks anything reviewed. A reviewed packet is
merged back by hand into the dataset with review_status "lawyer_reviewed",
reviewer_code, reviewed_at and adjudication_status -- the loader refuses a
partial review record.

Also appends the categories no dataset covers yet (e.g. a federal-vs-provincial
conflict) as blank rows whose query and label the reviewer supplies.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.ai.evaluation import legal_rag as E  # noqa: E402

DATASETS = ("dev_v1", "citation_probe_v1", "coverage_v1", "multi_issue_v1", "lettered_probe_v1")
COLUMNS = [
    "query_id", "label_version", "current_status", "language", "question_type", "purpose", "province",
    "query", "proposed_relevant", "proposed_alternatives", "proposed_capability", "proposed_answerability",
    "proposed_acceptable_abstention", "engineer_notes",
    # ── reviewer columns (blank) ──
    "reviewer_code", "reviewed_at", "agree_with_proposal (yes/no)", "corrected_relevant",
    "corrected_capability", "corrected_answerability", "acceptable_abstention (yes/no)",
    "issues (multi-issue: id | text | answerable | provisions)", "adjudication_status", "reviewer_notes",
]


def _targets(ts) -> str:
    return "; ".join(f"{t.statute} s.{t.section or '*'}" for t in ts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(BACKEND_DIR / "evals" / "legal_rag" / "review" / "packet.csv"))
    args = ap.parse_args()
    items = []
    for name in DATASETS:
        items += E.load_jsonl(BACKEND_DIR / "evals" / "legal_rag" / "datasets" / f"{name}.jsonl")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(COLUMNS)
        for it in items:
            w.writerow([it.query_id, it.label_version, it.review_status, it.language, it.question_type,
                        it.purpose, it.province, it.query, _targets(it.relevant),
                        _targets(it.acceptable_alternatives), it.expected_capability(),
                        it.expected_answerability(), "yes" if it.may_abstain() else "no", it.notes]
                       + [""] * 10)
        for cat, n in E.category_coverage(items).items():
            if n == 0:
                w.writerow([f"NEW-{cat}", "v1", "label_required", cat.replace("lang:", "") if cat.startswith("lang:") else "",
                            "" if cat.startswith("lang:") else cat, "", "",
                            "(reviewer to supply a query)", "", "", "", "", "",
                            f"no item covers required category '{cat}'"] + [""] * 10)
    print(f"packet: {out} ({len(items)} items; status of every item: not reviewed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
