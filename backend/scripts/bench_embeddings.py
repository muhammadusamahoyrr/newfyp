"""bench_embeddings.py — offline dense-retrieval benchmark of an embedding
model against the production one (Batch 7, 2026-10-13). NEVER downloads.

  python scripts/bench_embeddings.py --candidate <hf-id-or-local-path> [--collections criminal_collection,...]
         [--datasets dev_v1,citation_probe_v1,coverage_v1] [--k 50] [--max-chunks N] [--candidate-prefix e5|none]

WHAT IS COMPARED
  Dense retrieval only (no BM25, no grader, no reranker), so the number moves
  with the embedding model and nothing else:
    baseline   the production vectors already stored in Chroma
               (intfloat/multilingual-e5-base), query embedded with the same model
    candidate  the same chunks re-embedded in memory by the candidate model
  Same chunk set, same province filter (federal + the item's province), same
  candidate depth k, same scoring (cosine). Candidate vectors are cached under
  evals/legal_rag/cache/ (outside Chroma -- no collection is created).

AVAILABILITY
  The model is loaded with local_files_only=True. On 2026-10-13 the two local
  candidates (usama1111/e5-pakistani-legal, usama1111/e5-pak-legal-constitutional)
  hold only `.incomplete` weight blobs and BGE-M3 is absent, so this exits with
  "candidate not available locally". Download is a separate, explicit decision.

The generic MS-MARCO cross-encoder is out of scope by decision (it harmed
legal ranking when measured) and is refused here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.ai.evaluation import legal_rag as E  # noqa: E402

REFUSED = ("ms-marco",)
CASE_TO_COLLECTION = {"criminal": "criminal_collection", "civil": "civil_collection",
                      "family": "family_collection", "constitutional": "constitutional_collection"}


def _load_model(name: str):
    if any(r in name.lower() for r in REFUSED):
        raise SystemExit(f"refused: {name} (generic MS-MARCO models are excluded by decision)")
    try:
        from sentence_transformers import SentenceTransformer
        t0 = time.perf_counter()
        m = SentenceTransformer(name, device="cpu", local_files_only=True)
        return m, (time.perf_counter() - t0) * 1000
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"candidate not available locally: {name} ({type(exc).__name__}: {exc}). "
                         "Nothing was downloaded.")


def _chunks(client, collections, max_chunks):
    rows = []
    for name in collections:
        col = client.get_collection(name)
        off = 0
        while True:
            g = col.get(limit=500, offset=off, include=["metadatas", "documents", "embeddings"])
            if not g["ids"]:
                break
            for i, m, d, e in zip(g["ids"], g["metadatas"], g["documents"], g["embeddings"]):
                m = m or {}
                if m.get("synthetic") or m.get("retrieval_scope") == "reference_only":
                    continue
                rows.append({"id": i, "collection": name, "statute": m.get("statute", ""),
                             "section": m.get("section_number", ""), "province": (m.get("province") or "federal").lower(),
                             "text": d, "base_vec": e})
            off += 500
            if max_chunks and len(rows) >= max_chunks:
                return rows[:max_chunks]
    return rows


def _rank(np, qv, mat, rows, item, k):
    ok = {"federal", (item.province or "").lower()}
    col = CASE_TO_COLLECTION.get(item.case_type)
    mask = np.array([r["province"] in ok and (col is None or r["collection"] == col) for r in rows])
    scores = mat @ qv
    scores = np.where(mask, scores, -np.inf)
    top = np.argsort(-scores)[:k]
    return [{"statute": rows[i]["statute"], "section": rows[i]["section"], "province": rows[i]["province"]}
            for i in top if np.isfinite(scores[i])]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--candidate-prefix", choices=("e5", "none"), default="e5",
                    help='e5 = "query: "/"passage: " prefixes (e5-family models)')
    ap.add_argument("--collections", default="criminal_collection,civil_collection,family_collection,constitutional_collection")
    ap.add_argument("--datasets", default="dev_v1,citation_probe_v1,coverage_v1")
    ap.add_argument("--k", type=int, default=50)
    ap.add_argument("--max-chunks", type=int, default=0, help="smoke runs only")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    import numpy as np
    cand, cand_load_ms = _load_model(args.candidate)
    from app.ai.pipelines.retriever import MODEL_NAME
    base, base_load_ms = _load_model(MODEL_NAME)
    from app.db.chroma import connect_chroma, get_chroma
    connect_chroma()
    rows = _chunks(get_chroma(), args.collections.split(","), args.max_chunks)

    qp, pp = ("query: ", "passage: ") if args.candidate_prefix == "e5" else ("", "")
    cache = BACKEND_DIR / "evals" / "legal_rag" / "cache" / (
        hashlib.sha256(f"{args.candidate}|{args.candidate_prefix}|{len(rows)}|{rows[0]['id'] if rows else ''}"
                       .encode()).hexdigest()[:16] + ".npy")
    t0 = time.perf_counter()
    if cache.exists():
        cmat = np.load(cache)
    else:
        cmat = np.asarray(cand.encode([pp + r["text"] for r in rows], batch_size=32,
                                      normalize_embeddings=True, show_progress_bar=True))
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.save(cache, cmat)
    index_ms = (time.perf_counter() - t0) * 1000
    bmat = np.asarray([r["base_vec"] for r in rows], dtype=np.float32)

    items = []
    for ds in args.datasets.split(","):
        items += E.load_jsonl(BACKEND_DIR / "evals" / "legal_rag" / "datasets" / f"{ds}.jsonl")

    per = {"baseline": [], "candidate": []}
    for it in items:
        for arm, model, mat, prefix in (("baseline", base, bmat, "query: "), ("candidate", cand, cmat, qp)):
            t1 = time.perf_counter()
            qv = np.asarray(model.encode([prefix + it.query], normalize_embeddings=True))[0]
            q_ms = (time.perf_counter() - t1) * 1000
            ranked = _rank(np, qv, mat, rows, it, args.k)
            rec = {"query_id": it.query_id, "language": it.language, "question_type": it.question_type,
                   "tags": it.tags, "query_ms": q_ms, "answerable": it.answerable_by_corpus}
            if it.answerable_by_corpus:
                targets = it.relevant + it.acceptable_alternatives
                for k in (1, 3, 5, 10):
                    rec[f"recall@{k}"] = E.recall_at_k(ranked, it.relevant, k)
                rec["mrr"] = E.mrr(ranked, targets)
                rec["ndcg@10"] = E.ndcg_at_k(ranked, it.relevant, 10)
                rec["off_target_instrument@1"] = E.off_target_instrument_at_1(ranked, it.relevant)
            ja = E.jurisdiction_accuracy(ranked, it.province, 5)
            rec["wrong_jurisdiction@5"] = None if ja is None else 1 - ja
            rec["wrong_instrument@5"] = (E.wrong_instrument_rate(ranked, it.wrong_instruments, 5)
                                         if it.wrong_instruments else None)
            per[arm].append(rec)

    def agg(recs):
        ans = [r for r in recs if r["answerable"]]
        out = {"n": len(recs)}
        for key in ("recall@1", "recall@3", "recall@5", "recall@10", "mrr", "ndcg@10", "off_target_instrument@1"):
            out[key] = E.mean(r[key] for r in ans if r.get(key) is not None)
        for key in ("wrong_jurisdiction@5", "wrong_instrument@5"):
            out[key] = E.mean(r[key] for r in recs if r.get(key) is not None)
        lat = [r["query_ms"] for r in recs]
        out["query_ms_p50"], out["query_ms_p95"] = E.percentile(lat, .5), E.percentile(lat, .95)
        return out

    def sliced(recs):
        groups = defaultdict(list)
        for r in recs:
            groups[f"lang:{r['language']}"].append(r)
            groups[f"type:{r['question_type']}"].append(r)
            for t in r["tags"]:
                groups[f"tag:{t}"].append(r)
        return {k: agg(v) for k, v in sorted(groups.items())}

    report = {
        "schema": "embedding-bench-v1", "timestamp": datetime.now(timezone.utc).isoformat(),
        "baseline_model": MODEL_NAME, "candidate_model": args.candidate,
        "labels": E.label_summary(items), "chunks": len(rows), "k": args.k,
        "measured": "dense retrieval only (no BM25/grader/reranker); same chunks, filter and depth",
        "cold_load_ms": {"baseline": base_load_ms, "candidate": cand_load_ms},
        "candidate_index_ms": index_ms,
        "index_size_bytes": {"baseline": int(bmat.nbytes), "candidate": int(cmat.nbytes)},
        "overall": {arm: agg(v) for arm, v in per.items()},
        "slices": {arm: sliced(v) for arm, v in per.items()},
        "items": per,
    }
    out = Path(args.out or BACKEND_DIR / "evals" / "legal_rag" / "results" /
               f"embed_bench_{datetime.now().strftime('%Y-%m-%d_%H%M')}.json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print(json.dumps(report["overall"], indent=1, default=float))
    print(f"report: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
