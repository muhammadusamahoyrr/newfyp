"""eval_agentic.py — offline A/B: production intake retrieval vs bounded agentic
issue decomposition (Batch 8, 2026-10-13).

  python scripts/eval_agentic.py [--datasets multi_issue_v1] [--out R.json]

  baseline  the production intake path: issue binding (scope_issues) + ONE
            expanded query + the capability-first evidence gate
  agentic   app/ai/agentic_decomposition.decompose(offline=True): planner,
            per-issue retrieval and gate, merged per-issue evidence

Measured per item: issue coverage (answerable issues whose target provision
is retrieved), item recall, unsupported-issue leakage (an unsupported issue
that ends up with legal evidence), latency, model calls. The baseline is
reported at top-5 AND at the agentic arm's passage budget (5 x issues), so a
gain cannot come from simply returning more passages. Generation and citation
correctness are NOT measured here (retrieval-level experiment).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from app.ai.evaluation import legal_rag as E  # noqa: E402


def _hit(passages: list[dict], targets) -> bool:
    return any(E.is_relevant({"statute": p.get("statute"), "section": p.get("section_number")}, targets)
               for p in passages)


async def _baseline(it: E.EvalItem, calls: dict) -> dict:
    from app.ai.nodes import retrieval_node as rn
    from app.ai.nodes.intake_evidence_gate_node import decide, scope_issues, strip_unsupported
    scope = scope_issues(it.query)
    query, issue_scope = it.query, None
    if scope["unsupported"] and not scope["pure"] and not scope["missing_instruments"]:
        query = strip_unsupported(it.query, scope) or scope["supported_text"]
        issue_scope = {**scope, "retrieval_bound": True}
    t0 = time.perf_counter()
    calls["n"] = 0
    out = await rn.retrieval_node({"query": it.query, "user_text": it.query, "retrieval_query_supplement": query,
                                   "issue_scope": issue_scope, "case_type": it.case_type, "province": it.province,
                                   "retrieval_attempts": 0, "known_facts": [],
                                   "retrieval_policy": {"purpose": "intake", "min_chunks": 0,
                                                        "include_ungraded": False, "case_law": False}})
    chunks = out.get("reranked_chunks") or out.get("retrieved_chunks") or []
    kept, gate = decide(chunks=chunks, retrieval_error=bool(out.get("retrieval_error")), province=it.province,
                        user_text=it.query, relevance_score=None, issue_scope=issue_scope)
    grounded = gate["status"] in ("supported", "partially_supported")
    return {"latency_ms": (time.perf_counter() - t0) * 1000, "model_calls": calls["n"],
            "gate": gate["status"], "passages": kept if grounded else []}


async def main_async(args) -> dict:
    from app.ai import agentic_decomposition as AD
    from app.ai.nodes import retrieval_node as rn
    from app.db.chroma import connect_chroma
    connect_chroma()
    calls = {"n": 0}
    real_expand = rn._expand_query

    async def counted(q):
        calls["n"] += 1
        return await real_expand(q)
    rn._expand_query = counted

    items = []
    for ds in args.datasets.split(","):
        items += [i for i in E.load_jsonl(BACKEND_DIR / "evals" / "legal_rag" / "datasets" / f"{ds}.jsonl")
                  if i.issues]
    rows = []
    for it in items:
        base = await _baseline(it, calls)
        calls["n"] = 0
        ag = await AD.decompose(it.query, it.case_type, it.province, offline=True)
        ag_passages = [e for p in ag["issues"] for e in p.get("evidence") or []]
        budget = 5 * max(1, len(ag["issues"]))
        answerable = [i for i in it.issues if i.answerable]
        unsupported = [i for i in it.issues if not i.answerable]
        row = {"query_id": it.query_id, "language": it.language,
               "baseline_gate": base["gate"],
               "agentic_states": [{"text": p["text"], "state": p["state"], "source": p.get("source")}
                                  for p in ag["issues"]],
               "agentic_model_calls": ag["model_calls"],
               "agentic_planner_calls_counted_in_budget": True,
               "baseline_model_calls": base["model_calls"],
               "baseline_latency_ms": round(base["latency_ms"], 1), "agentic_latency_ms": ag["latency_ms"],
               "agentic_timed_out": ag["timed_out"]}
        for name, passages in (("baseline@5", base["passages"][:5]),
                               (f"baseline@budget", base["passages"][:budget]),
                               ("agentic", ag_passages)):
            row[name] = {
                "issue_coverage": (sum(1 for i in answerable if _hit(passages, i.relevant)) / len(answerable)
                                   if answerable else None),
                "item_recall": E.recall_at_k([{"statute": p.get("statute"), "section": p.get("section_number")}
                                              for p in passages], it.relevant, len(passages) or 1),
                "passages": len(passages),
            }
        # Leakage: an unsupported issue carrying legal evidence.
        # Deterministic: a packet that carries evidence while its own text still
        # contains a capability-unsupported sentence (the planner merged the
        # unanswerable question into an answerable issue).
        from app.ai.nodes.intake_evidence_gate_node import scope_issues
        row["agentic_unsupported_leakage"] = sum(
            1 for p in ag["issues"] if p["state"] in ("supported", "conflicting_authority")
            and (scope_issues(p["text"])["unsupported"] or scope_issues(p["text"])["missing_instruments"]))
        row["unsupported_issues_annotated"] = len(unsupported)
        rows.append(row)
        print(json.dumps({k: row[k] for k in ("query_id", "baseline_gate", "agentic_model_calls")}
                         | {"cov": {n: row[n]["issue_coverage"] for n in ("baseline@5", "baseline@budget", "agentic")}}),
              flush=True)
    rn._expand_query = real_expand

    def mean(key, sub):
        return E.mean(r[key][sub] for r in rows if r[key][sub] is not None)
    return {
        "schema": "agentic-eval-v1", "timestamp": datetime.now(timezone.utc).isoformat(),
        "labels": E.label_summary(items), "n": len(rows),
        "summary": {arm: {"issue_coverage": mean(arm, "issue_coverage"), "item_recall": mean(arm, "item_recall"),
                          "passages": mean(arm, "passages")}
                    for arm in ("baseline@5", "baseline@budget", "agentic")},
        "latency_ms": {"baseline_mean": E.mean(r["baseline_latency_ms"] for r in rows),
                       "agentic_mean": E.mean(r["agentic_latency_ms"] for r in rows)},
        "model_calls": {"baseline_mean": E.mean(r["baseline_model_calls"] for r in rows),
                        "agentic_mean": E.mean(r["agentic_model_calls"] for r in rows)},
        "agentic_unsupported_leakage_total": sum(r["agentic_unsupported_leakage"] for r in rows),
        "not_measured": ["generation", "citation correctness", "unsupported legal claims in generated text"],
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", default="multi_issue_v1,dev_v1")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    rep = asyncio.run(main_async(args))
    out = Path(args.out or BACKEND_DIR / "evals" / "legal_rag" / "results" /
               f"agentic_eval_{datetime.now().strftime('%Y-%m-%d_%H%M')}.json")
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: rep[k] for k in ("n", "summary", "latency_ms", "model_calls",
                                         "agentic_unsupported_leakage_total")}, indent=1))
    print(f"report: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
