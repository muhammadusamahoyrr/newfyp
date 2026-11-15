"""trace_intake_retrieval.py — stage-by-stage trace of one intake retrieval
(false-abstention diagnosis, 2026-10-13). Read-only; writes a JSON trace.

  python scripts/trace_intake_retrieval.py --ids d007,d014 [--datasets dev_v1,multi_issue_v1] --out T.json

For each item, the production intake path WITHOUT generation:
  query -> issue scope -> expansion -> retrieval (+ topic rules, affinity)
  -> grader (per-chunk keyword / embedding / LLM grade / score vs threshold)
  -> evidence gate.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from app.ai.evaluation import legal_rag as E  # noqa: E402


def _short(c: dict) -> str:
    return f"{c.get('statute')} s.{c.get('section_number')}"


async def trace(item: E.EvalItem) -> dict:
    from app.ai import scoring
    from app.ai.nodes import retrieval_node as rn
    from app.ai.nodes.intake_evidence_gate_node import decide, scope_issues, strip_unsupported
    from app.ai.nodes.retrieval_grader_node import retrieval_grader_node

    scope = scope_issues(item.query)
    query, issue_scope = item.query, None
    if scope["unsupported"] and not scope["pure"] and not scope["missing_instruments"]:
        query = strip_unsupported(item.query, scope) or scope["supported_text"]
        issue_scope = {**scope, "retrieval_bound": True}
    state = {"query": item.query, "user_text": item.query, "retrieval_query_supplement": query,
             "issue_scope": issue_scope, "case_type": item.case_type, "province": item.province,
             "retrieval_attempts": 0, "known_facts": [], "language": "en",
             "retrieval_policy": {"purpose": "intake", "min_chunks": 0, "include_ungraded": False,
                                  "case_law": False}}
    out = await rn.retrieval_node(state)
    retrieved = out.get("retrieved_chunks") or out.get("reranked_chunks") or []

    scored = []
    real = scoring.score_chunk_with_variance

    def spy(query_text, chunk_text, embedding_score, llm_grade, **kw):
        s, v = real(query_text, chunk_text, embedding_score, llm_grade, **kw)
        scored.append({"head": (chunk_text or "")[:60], "embedding": round(float(embedding_score), 3),
                       "llm_grade": llm_grade, "score": s})
        return s, v
    scoring.score_chunk_with_variance = spy
    try:
        graded = await retrieval_grader_node({**state, **out, "retrieved_chunks": retrieved})
    finally:
        scoring.score_chunk_with_variance = real
    kept = graded.get("reranked_chunks") or []
    _, gate = decide(chunks=kept, retrieval_error=bool(out.get("retrieval_error")), province=item.province,
                     user_text=item.query, relevance_score=graded.get("relevance_score"), issue_scope=issue_scope)
    targets = [f"{t.statute} s.{t.section}" for t in item.relevant]
    hit = lambda cs: [_short(c) for c in cs if E.is_relevant(  # noqa: E731
        {"statute": c.get("statute"), "section": c.get("section_number")}, item.relevant)]
    return {
        "query_id": item.query_id, "query": item.query, "language": item.language,
        "intended": targets, "issue_scope": {"unsupported": scope["unsupported"], "bound": bool(issue_scope)},
        "expanded_query": out.get("expanded_query"),
        "retrieved": [_short(c) for c in retrieved],
        "target_in_retrieved": hit(retrieved),
        "grader": {"threshold": scoring._DEFAULT_KEEP_THRESHOLD, "aggregate": graded.get("relevance_score"),
                   "scores": scored},
        "kept_after_grader": [_short(c) for c in kept],
        "target_kept": hit(kept),
        "gate": {k: gate.get(k) for k in ("status", "reasons", "capability", "dropped", "requested_provisions")},
    }


async def main_async(args) -> list[dict]:
    from app.db.chroma import connect_chroma
    connect_chroma()
    items = []
    for ds in args.datasets.split(","):
        items += E.load_jsonl(BACKEND_DIR / "evals" / "legal_rag" / "datasets" / f"{ds}.jsonl")
    want = args.ids.split(",")
    return [await trace(i) for i in items if i.query_id in want]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True)
    ap.add_argument("--datasets", default="dev_v1,multi_issue_v1,coverage_v1")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    traces = asyncio.run(main_async(args))
    Path(args.out).write_text(json.dumps(traces, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    for t in traces:
        print(f"{t['query_id']} target={t['intended']} in_retrieved={t['target_in_retrieved']} "
              f"kept={t['kept_after_grader']} target_kept={t['target_kept']} gate={t['gate']['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
