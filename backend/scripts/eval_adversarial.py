"""Score the deterministic client-chat checks against the hand-labelled
adversarial set (evals/chat_length/adversarial_v1.jsonl). Offline, no model.

  python scripts/eval_adversarial.py [--out evals/chat_length/results/adversarial_v1_score.json]

The labels come from scripts/build_adversarial_set.py (assigned by hand from
the statute text), so this is NOT the checker grading itself.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
for _s in (sys.stdout,):
    _s.reconfigure(encoding="utf-8", errors="replace")
DATA = BACKEND / "evals" / "chat_length" / "adversarial_v1.jsonl"


def main() -> int:
    from app.ai import exact_provision, imminent_danger, period_support
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    rows = [json.loads(l) for l in DATA.read_text(encoding="utf-8").splitlines() if l.strip()]
    results = []
    for r in rows:
        if r["kind"] == "period":
            got = "unsupported" if period_support.unsupported_periods(r["sentence"], r["evidence"]) else "supported"
        elif r["kind"] == "provision":
            cits = exact_provision.requested(r["question"])
            got = bool(cits) and exact_provision.is_exact(r["chunk"], cits[0])
        else:
            got = imminent_danger.detect(r["text"])
        results.append({"id": r["id"], "category": r["category"], "label": r["label"], "got": got,
                        "correct": got == r["label"], "basis": r["basis"]})
    by_cat = defaultdict(list)
    for x in results:
        by_cat[x["category"]].append(x)
    summary = {c: {"n": len(v), "correct": sum(x["correct"] for x in v)} for c, v in sorted(by_cat.items())}
    # The two directions that matter most, separately.
    period = [x for x in results if x["category"] in ("wrong_article", "missing_heading", "wrong_act",
                                                       "valid_period")]
    summary["_period_false_pass"] = sum(1 for x in period if x["label"] == "unsupported" and x["got"] == "supported")
    summary["_period_over_removal"] = sum(1 for x in period if x["label"] == "supported" and x["got"] == "unsupported")
    danger = by_cat["imminent_danger"]
    summary["_danger_missed"] = sum(1 for x in danger if x["label"] and not x["got"])
    summary["_danger_false_alarm"] = sum(1 for x in danger if not x["label"] and x["got"])
    print(json.dumps(summary, indent=1))
    for x in results:
        if not x["correct"]:
            print(f"  WRONG {x['id']} {x['category']}: label={x['label']} got={x['got']} -- {x['basis']}")
    if args.out:
        Path(args.out).write_text(json.dumps({"dataset": str(DATA.relative_to(BACKEND)), "summary": summary,
                                              "results": results}, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
