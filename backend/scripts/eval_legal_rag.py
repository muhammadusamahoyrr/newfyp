"""eval_legal_rag.py — run the Legal RAG evaluation set against the PRODUCTION
retrieval stage and save a versioned baseline artifact (Batch 1, 2026-10-12).

What is measured, and what is not
---------------------------------
  * Retrieval: the real `retrieval_node` (Chroma + BM25 + graph hop-2 + topic
    rules + named-statute affinity), not a re-implementation. Ranking is taken
    BEFORE the LLM grader, so the run needs no LLM unless --expand is given
    (the fast-tier query rewrite; costs Groq calls and is non-deterministic).
  * Selective behaviour: what each purpose's CURRENT policy would decline.
    Chat/research decline via the query-side answerability check; intake has no
    decline path today (it always generates), which is what the baseline shows.
  * NOT measured here: generation, fact fidelity, claim grounding. They need the
    full LLM graph per item; they are reported as "not_measured", never zero.

Chroma is embedded. Stop the backend first (scripts/serve.py stop): a second
process opening the same store triggered a compaction error during this work.

Usage:
  python scripts/eval_legal_rag.py --dataset evals/legal_rag/datasets/dev_v1.jsonl
         [--expand] [--split dev] [--out evals/legal_rag/results/baseline.json]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import subprocess
import sys
import time
from collections import defaultdict
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

KS = (1, 3, 5, 10)


def _git_revision() -> dict:
    def run(*args):
        try:
            return subprocess.run(["git", *args], cwd=BACKEND_DIR, capture_output=True,
                                  text=True, timeout=20).stdout.strip()
        except Exception:
            return ""
    return {"commit": run("rev-parse", "HEAD"), "dirty": bool(run("status", "--porcelain"))}


def _passages(chunks: list[dict]) -> list[dict]:
    return [{"statute": c.get("statute") or (c.get("metadata") or {}).get("statute", ""),
             "section": c.get("section_number") or c.get("section")
                        or (c.get("metadata") or {}).get("section_number", ""),
             "province": c.get("province") or (c.get("metadata") or {}).get("province", ""),
             "chunk_id": c.get("chunk_id") or (c.get("metadata") or {}).get("chunk_id", "")}
            for c in chunks]


async def _retrieve(item: E.EvalItem, expand: bool, policy: str = "current",
                    multi_query: bool = False, expansion_skip: bool = False) -> tuple[list[dict], dict]:
    from app.ai.nodes import retrieval_node as rn
    from app.ai.nodes.intake_evidence_gate_node import scope_issues, strip_unsupported
    state = {"query": item.query, "case_type": item.case_type, "province": item.province,
             "retrieval_attempts": 0, "known_facts": []}
    issue_scope = None
    if policy == "intake":
        # The intake channels as convert_to_case sets them, including the
        # issue binding of _run_intake_ai.
        scope = scope_issues(item.query)
        supplement = item.query
        if scope["unsupported"] and not scope["pure"] and not scope["missing_instruments"]:
            supplement = strip_unsupported(item.query, scope) or scope["supported_text"]
            issue_scope = {**scope, "retrieval_bound": True}
        state.update({"user_text": item.query, "retrieval_query_supplement": supplement,
                      "issue_scope": issue_scope,
                      "retrieval_policy": {"purpose": "intake", "min_chunks": 0,
                                           "include_ungraded": False, "case_law": False,
                                           "multi_query": multi_query,
                                           "expansion_skip": expansion_skip}})
    elif expansion_skip:
        state["retrieval_policy"] = {"expansion_skip": True}
    t0 = time.perf_counter()
    out = await rn.retrieval_node(state)
    dt = (time.perf_counter() - t0) * 1000
    chunks = out.get("reranked_chunks") or out.get("retrieved_chunks") or []
    extra = {}
    if policy == "intake":
        from app.ai.nodes.intake_evidence_gate_node import decide
        _, gate = decide(chunks=chunks, retrieval_error=bool(out.get("retrieval_error")),
                         province=item.province, user_text=item.query, relevance_score=None,
                         issue_scope=issue_scope)
        extra["gate_status"] = gate["status"]
    return _passages(chunks), {
        "retrieval_ms": round(dt, 1), "retrieval_error": bool(out.get("retrieval_error")), **extra}


def _declines(item: E.EvalItem, policy: str = "current", timing: dict | None = None) -> bool:
    """The decline decision for the item's purpose under the policy measured."""
    if policy == "intake":
        # The evidence gate WITHOUT the LLM grader: structural + capability only.
        return (timing or {}).get("gate_status") not in ("supported", "partially_supported")
    if item.purpose == "intake":
        return False                       # intake always generates today
    from app.ai.pipelines.answerability import check
    return check(item.query) is not None


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="evals/legal_rag/datasets/dev_v1.jsonl")
    ap.add_argument("--split", default=None, help="only this split (dev/regression/holdout)")
    ap.add_argument("--expand", action="store_true", help="use the LLM query rewrite (Groq)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--label", default="baseline")
    ap.add_argument("--index", default="base", help="retrieval index variant: base | ctx_v1 | sec_v1 | sec_v2")
    ap.add_argument("--strict-labels", action="store_true",
                    help="score on true section labels even on the base index (metadata correctness)")
    ap.add_argument("--policy", choices=("current", "intake"), default="current",
                    help="intake = intake channels + evidence gate (structural/capability, no LLM grader)")
    ap.add_argument("--multi-query", action="store_true", help="A/B arm: intake multi-query (default off)")
    ap.add_argument("--expansion-cache", default=None,
                    help="JSON file of LLM rewrites keyed by query: read when present, written after the run. "
                         "Lets two arms share ONE rewrite per query, so an A/B differs only by the policy under test")
    ap.add_argument("--expansion-skip", action="store_true",
                    help="A/B arm: skip the LLM rewrite when the query holds an exact citation")
    args = ap.parse_args()

    items = E.load_jsonl(BACKEND_DIR / args.dataset)
    if args.split:
        items = [i for i in items if i.split == args.split]

    limitations = []
    from app.ai.nodes import retrieval_node as rn
    if not args.expand:
        async def _identity(q: str) -> str:
            return q
        rn._expand_query = _identity
        limitations.append("query expansion disabled (deterministic run; production uses the LLM rewrite)")
    exp_cache: dict = {}
    exp_log: dict = {}
    if args.expand:
        cache_path = Path(args.expansion_cache) if args.expansion_cache else None
        if cache_path and cache_path.exists():
            exp_cache = json.loads(cache_path.read_text(encoding="utf-8"))
        real_expand = rn._expand_query

        async def _counted(q: str) -> str:
            t0 = time.perf_counter()
            if q in exp_cache:
                out, ms, cached = exp_cache[q]["expanded"], exp_cache[q]["ms"], True
            else:
                out = await real_expand(q)
                ms, cached = round((time.perf_counter() - t0) * 1000, 1), False
                exp_cache[q] = {"expanded": out, "ms": ms}
            exp_log["calls"] = exp_log.get("calls", 0) + 1
            exp_log["ms"] = exp_log.get("ms", 0.0) + ms
            exp_log["wall_ms"] = exp_log.get("wall_ms", 0.0) + (time.perf_counter() - t0) * 1000
            exp_log["cached"] = exp_log.get("cached", 0) + int(cached)
            return out
        rn._expand_query = _counted

    from app.db.chroma import connect_chroma
    try:
        connect_chroma()
    except Exception as exc:
        print(f"Chroma unavailable: {exc}. No baseline written.", file=sys.stderr)
        return 2
    from app.ai.pipelines.retriever import MODEL_NAME
    from app.core.config import settings
    settings.retrieval_index_variant = args.index
    if args.strict_labels or args.index in ("sec_v1", "sec_v2"):
        # A repaired index stores the TRUE provision label (489F), and a strict
        # run scores every index that way: a right passage under a wrong label
        # (base: 489-F stored as "489") is not counted as correct.
        for it in items:
            for t in it.relevant + it.acceptable_alternatives:
                t.index_section = None
        limitations.append("strict labels: targets matched on their true section label (index_section ignored)")

    rows, per_item = [], []
    for it in items:
        exp_log.clear()
        ranked, timing = await _retrieve(it, args.expand, args.policy, args.multi_query, args.expansion_skip)
        # Retrieval time without the rewrite, then the MODELED total: plus the
        # rewrite's measured latency when this policy calls it. A cached rewrite
        # is charged at the latency measured when it was really made.
        retrieval_only = max(timing["retrieval_ms"] - exp_log.get("wall_ms", 0.0), 0.0)
        timing.update({"expansion_calls": exp_log.get("calls", 0),
                       "expansion_cached": exp_log.get("cached", 0),
                       "expansion_ms": round(exp_log.get("ms", 0.0), 1),
                       "retrieval_only_ms": round(retrieval_only, 1),
                       "modeled_total_ms": round(retrieval_only + exp_log.get("ms", 0.0), 1)})
        rec = {"query_id": it.query_id, "language": it.language, "purpose": it.purpose,
               "question_type": it.question_type, "answerable": it.answerable_by_corpus,
               "tags": list(it.tags), "zero_result": not ranked,
               **timing, "top": [f"{p['statute']} s.{p['section']}" for p in ranked[:5]]}
        if it.answerable_by_corpus:
            targets = it.relevant + it.acceptable_alternatives
            for k in KS:
                rec[f"recall@{k}"] = E.recall_at_k(ranked, it.relevant, k)
                rec[f"precision@{k}"] = E.precision_at_k(ranked, targets, k)
            rec["mrr"] = E.mrr(ranked, targets)
            rec["ndcg@5"] = E.ndcg_at_k(ranked, it.relevant, 5)
            rec["ndcg@10"] = E.ndcg_at_k(ranked, it.relevant, 10)
            rec["exact_section@1"] = E.exact_hit_at_1(ranked, it.relevant)
            rec["off_target_instrument@1"] = E.off_target_instrument_at_1(ranked, it.relevant)
        rec["wrong_instrument@5"] = E.wrong_instrument_rate(ranked, it.wrong_instruments, 5) if it.wrong_instruments else None
        rec["jurisdiction_acc@5"] = E.jurisdiction_accuracy(ranked, it.province, 5)
        rec["wrong_jurisdiction@5"] = (None if rec["jurisdiction_acc@5"] is None
                                       else round(1 - rec["jurisdiction_acc@5"], 4))
        rec["declined"] = _declines(it, args.policy, timing)
        per_item.append(rec)
        rows.append((it.answerable_by_corpus, rec["declined"]))
        print(f"{it.query_id} {it.language:8} {rec.get('recall@5', '-')!s:5} {timing['retrieval_ms']:7.0f}ms  {rec['top'][:2]}")

    def agg(recs: list[dict]) -> dict:
        ans = [r for r in recs if r["answerable"]]
        out = {"n": len(recs), "n_answerable": len(ans)}
        for key in ([f"recall@{k}" for k in KS] + [f"precision@{k}" for k in KS]
                    + ["mrr", "ndcg@5", "ndcg@10", "exact_section@1", "off_target_instrument@1"]):
            out[key] = E.mean(r.get(key) for r in ans if r.get(key) is not None)
        out["wrong_jurisdiction@5"] = E.mean(r["wrong_jurisdiction@5"] for r in recs
                                             if r["wrong_jurisdiction@5"] is not None)
        out["zero_result_rate"] = E.mean(1.0 if r["zero_result"] else 0.0 for r in recs)
        out["expansion_calls"] = sum(r.get("expansion_calls", 0) for r in recs)
        tot = [r["modeled_total_ms"] for r in recs if "modeled_total_ms" in r]
        out["modeled_total_ms_p50"] = E.percentile(tot, 0.5)
        out["modeled_total_ms_p95"] = E.percentile(tot, 0.95)
        out["wrong_instrument@5"] = E.mean(r["wrong_instrument@5"] for r in recs)
        out["jurisdiction_acc@5"] = E.mean(r["jurisdiction_acc@5"] for r in recs)
        lat = [r["retrieval_ms"] for r in recs]
        out["retrieval_ms_p50"] = E.percentile(lat, 0.5)
        out["retrieval_ms_p95"] = E.percentile(lat, 0.95)
        out["retrieval_errors"] = sum(1 for r in recs if r["retrieval_error"])
        return out

    by_lang, by_purpose, by_type = defaultdict(list), defaultdict(list), defaultdict(list)
    by_tag = defaultdict(list)
    for r in per_item:
        for tag in r.get("tags") or ["untagged"]:
            by_tag[tag].append(r)
        by_lang[r["language"]].append(r)
        by_purpose[r["purpose"]].append(r)
        by_type[r["question_type"]].append(r)
    selective = {p: E.selective_metrics([(r["answerable"], r["declined"]) for r in rs])
                 for p, rs in by_purpose.items()}

    artifact = {
        "schema": "legal-rag-eval-result-v1",
        "label": args.label,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dataset": {"path": args.dataset, "schema_version": E.SCHEMA_VERSION, "n_items": len(items),
                    "split": args.split or "all", "review_status": sorted({i.review_status for i in items}),
                    "labels": E.label_summary(items), "category_coverage": E.category_coverage(items)},
        "code": _git_revision(),
        "index": {"embedding_model": MODEL_NAME, "store": "chroma_data (embedded)", "variant": args.index,
                  "collections": ["civil_collection", "criminal_collection", "family_collection",
                                  "constitutional_collection", "judgments_collection"]},
        "policy": {"name": args.policy, "query_expansion": bool(args.expand),
                   "multi_query": bool(args.multi_query), "expansion_skip": bool(args.expansion_skip), "ranking_measured": "retrieval_node output, before the LLM grader",
                   "intake_decline_policy": "none (always generates)", "chat_decline_policy": "answerability.check"},
        "environment": {"python": platform.python_version(), "platform": platform.platform(), "cpu_only": True},
        "limitations": limitations + [
            "silver labels (engineer-authored, not lawyer-reviewed)",
            "lettered sections are stored without their letter in this index (e.g. PPC 489-F as 489); targets use index_section",
            "generation, fact fidelity and claim grounding: not_measured in this run",
        ],
        "metrics": {"overall": agg(per_item),
                    "by_language": {k: agg(v) for k, v in by_lang.items()},
                    "by_purpose": {k: agg(v) for k, v in by_purpose.items()},
                    "by_question_type": {k: agg(v) for k, v in by_type.items()},
                    "by_tag": {k: agg(v) for k, v in by_tag.items()},
                    "selective_by_purpose": selective,
                    "generation": "not_measured"},
        "items": per_item,
    }
    out = Path(args.out) if args.out else BACKEND_DIR / "evals" / "legal_rag" / "results" / (
        f"{args.label}_{datetime.now().strftime('%Y-%m-%d_%H%M')}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    if args.expand and args.expansion_cache:
        Path(args.expansion_cache).write_text(json.dumps(exp_cache, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
    o = artifact["metrics"]["overall"]
    print(f"\nwrote {out}\noverall: R@1 {o['recall@1']} R@5 {o['recall@5']} R@10 {o['recall@10']} "
          f"MRR {o['mrr']} nDCG@10 {o['ndcg@10']} p50 {o['retrieval_ms_p50']}ms p95 {o['retrieval_ms_p95']}ms")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
