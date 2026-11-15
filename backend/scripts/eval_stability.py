"""eval_stability.py — repeated-run stability of the intake analysis, with
SEPARATE dimensions (2026-10-13 closure patch).

  python scripts/eval_stability.py --runs R1.jsonl,R2.jsonl,R3.jsonl --ids d007,m001 [--out S.json]

A single "stable" flag conflated SAFE with ACCURATE: an item whose runs were
all "acceptable" was stable even with incomplete issue coverage, a different
provision set every run, or an extra provision. Each property is now its own
field, and a reader cannot mistake one for another:

  structurally_safe_all_runs           no structural unsafe reason in any run
  available_all_runs                   no pipeline/provider failure in any run
  gate_status_stable                   one gate status across runs
  expected_issue_coverage_all_runs     every answerable issue covered every run (None: unanswerable)
  provision_set_stable                 one canonical visible provision set across runs
  no_wrong_provision_runs / no_unsupported_extra_provision_runs
  localization_stable                  Urdu: every run rendered OR used the explicit safe fallback
  legally_stable_all_runs              answerable: safe + covered + no wrong/extra + same provisions;
                                       unanswerable: safe + safe abstention + no visible provisions
  demo_stable                          safe + available + no wrong provision + coverage + safe localisation
                                       (provision variance is still reported)

Runs are combined ONLY when every record carries the same source fingerprint,
dataset hash and evaluator version (app/ai/evaluation/artifact.combinable).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from app.ai.evaluation import artifact  # noqa: E402
from app.ai.evaluation import legal_rag as E  # noqa: E402

_spec = importlib.util.spec_from_file_location("eval_generation", BACKEND_DIR / "scripts" / "eval_generation.py")
G = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(G)

STABILITY_SCHEMA = "stability-v2"
LEGALLY_GOOD = ("legally_supported_answer",)


def run_view(item: E.EvalItem, rec: dict, run_no: int) -> dict:
    r = G.assess_one(item, rec)
    an = rec.get("analysis") or {}
    prov = rec.get("provenance") or {}
    loc_state = (an.get("localization_state") or {})
    return {
        "run": run_no,
        "pipeline_failed": an.get("grounding_status") == "pipeline_failed" or prov.get("pipeline_failed", False),
        "providers_used": prov.get("providers_used", []),
        "provider_limit_hit": prov.get("provider_limit_hit", False),
        "gate": r["gate_status"], "grounding": an.get("grounding_status"),
        "visible": r["L_provisions"]["visible_provisions"],
        "issue_coverage": r["L_provisions"]["issue_coverage"],
        "full_issue_coverage": r["L_provisions"]["full_issue_coverage"],
        "wrong_provisions": r["L_provisions"]["wrong_provisions"],
        "missing_expected": r["L_provisions"]["missing_expected"],
        "legal_outcome": r["L_provisions"]["outcome"],
        "unsafe": r["unsafe_reasons"],
        "visible_provision_mismatch": r.get("visible_provision_mismatch", []),
        "localization": rec.get("localization_status") or {},
        "localization_state": loc_state.get("status"),
        "latency_ms": rec.get("latency_ms"),
    }


def item_report(item: E.EvalItem, runs: list[dict]) -> dict:
    n = len(runs)
    answerable = item.answerable_by_corpus and item.expected_capability() in ("corpus_capable",
                                                                             "mixed_supported_unsupported")
    safe = n > 0 and all(not x["unsafe"] for x in runs)
    available = n > 0 and all(not x["pipeline_failed"] for x in runs)
    gate_stable = len({x["gate"] for x in runs}) == 1 and n > 0
    coverage = (all(x["full_issue_coverage"] and not x["pipeline_failed"] for x in runs) and n > 0) \
        if answerable else None
    prov_stable = len({tuple(x["visible"]) for x in runs}) == 1 and n > 0
    no_wrong = all(x["legal_outcome"] != "wrong_provision_answer" for x in runs)
    no_extra = all(x["legal_outcome"] != "unsupported_extra_provision" for x in runs)
    urdu = item.language == "ur"
    loc_ok = all(x["localization_state"] in ("rendered", "fallback_english")
                 or x["localization"].get("ur") in ("ok", "failed") for x in runs) if urdu else None
    if answerable:
        legally = safe and available and bool(coverage) and no_wrong and no_extra and prov_stable \
            and all(x["legal_outcome"] in LEGALLY_GOOD for x in runs)
    else:
        legally = safe and all(x["legal_outcome"] == "safe_abstention" and not x["visible"] for x in runs)
    demo = safe and available and no_wrong and (coverage is not False) and (loc_ok is not False)
    return {
        "n_runs": n,
        "answerable": answerable,
        "structurally_safe_all_runs": safe,
        "available_all_runs": available,
        "gate_status_stable": gate_stable,
        "expected_issue_coverage_all_runs": coverage,
        "provision_set_stable": prov_stable,
        "no_wrong_provision_runs": no_wrong,
        "no_unsupported_extra_provision_runs": no_extra,
        "localization_stable": loc_ok,
        "urdu_rendered_runs": sum(1 for x in runs if x["localization"].get("ur") == "ok") if urdu else None,
        "urdu_safe_fallback_runs": sum(1 for x in runs if x["localization"].get("ur") == "failed") if urdu else None,
        "legally_stable_all_runs": legally,
        "demo_stable": demo,
        "distinct_provision_sets": len({tuple(x["visible"]) for x in runs}),
        "distinct_gate_status": sorted({x["gate"] for x in runs}),
        "outcomes": [x["legal_outcome"] for x in runs],
        "runs": runs,
    }


def build(run_paths: list[str], ids: list[str], datasets: list[str]) -> dict:
    items = {i.query_id: i for ds in datasets
             for i in E.load_jsonl(BACKEND_DIR / "evals" / "legal_rag" / "datasets" / f"{ds}.jsonl")}
    records = []
    for run_no, path in enumerate(run_paths, 1):
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                if rec["query_id"] in ids:
                    records.append((run_no, rec))
    ok, why = artifact.combinable([r for _, r in records])
    if not ok:
        return {"schema": STABILITY_SCHEMA, "refused": True, "reason": why, "runs": run_paths}
    per = {q: [] for q in ids}
    for run_no, rec in records:
        per[rec["query_id"]].append(run_view(items[rec["query_id"]], rec, run_no))
    reports = {q: item_report(items[q], runs) for q, runs in per.items()}
    lat = [x["latency_ms"] for v in reports.values() for x in v["runs"] if x["latency_ms"]]
    prov = records[0][1]["provenance"] if records else {}
    return {
        "schema": STABILITY_SCHEMA, "refused": False, "labels": "silver",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_fingerprint": prov.get("source_fingerprint"), "git_commit": prov.get("git_commit"),
        "worktree_dirty": prov.get("worktree_dirty"), "datasets": prov.get("datasets"),
        "evaluator_version": prov.get("evaluator_version"), "gate_version": prov.get("gate_version"),
        "output_guard_version": prov.get("output_guard_version"), "index_variant": prov.get("index_variant"),
        "run_files": run_paths,
        "items": reports,
        "totals": {
            "structurally_unsafe_runs": sum(1 for v in reports.values() for x in v["runs"] if x["unsafe"]),
            "pipeline_failed_runs": sum(1 for v in reports.values() for x in v["runs"] if x["pipeline_failed"]),
            "items_structurally_safe": sum(1 for v in reports.values() if v["structurally_safe_all_runs"]),
            "items_legally_stable": sum(1 for v in reports.values() if v["legally_stable_all_runs"]),
            "items_demo_stable": sum(1 for v in reports.values() if v["demo_stable"]),
        },
        "latency_ms": {"p50": E.percentile(lat, .5), "p95": E.percentile(lat, .95)},
        "note": "structurally safe != legally accurate; silver labels; see each dimension separately",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", required=True)
    ap.add_argument("--ids", required=True)
    ap.add_argument("--datasets", default="dev_v1,coverage_v1,multi_issue_v1")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    rep = build(args.runs.split(","), args.ids.split(","), args.datasets.split(","))
    if args.out:
        Path(args.out).write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    if rep.get("refused"):
        print("REFUSED to combine runs:", rep["reason"])
        return 2
    cols = ("structurally_safe_all_runs", "available_all_runs", "expected_issue_coverage_all_runs",
            "provision_set_stable", "no_wrong_provision_runs", "legally_stable_all_runs", "demo_stable")
    print("source", rep["source_fingerprint"], "| evaluator", rep["evaluator_version"])
    for q, v in rep["items"].items():
        print(f"{q}: " + " ".join(f"{c.replace('_all_runs', '').replace('_runs', '')}={v[c]}" for c in cols))
        for x in v["runs"]:
            print(f"    r{x['run']} {x['gate']:22} {x['legal_outcome']:28} {x['visible']} "
                  f"unsafe={x['unsafe']} loc={x['localization']} via={x['providers_used'][:2]} "
                  f"{round((x['latency_ms'] or 0) / 1000)}s")
    print("totals:", rep["totals"], "latency:", rep["latency_ms"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
