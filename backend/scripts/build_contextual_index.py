"""build_contextual_index.py — build the versioned contextual collection for one
base collection (Batch 5, 2026-10-12).

  python scripts/build_contextual_index.py --collection criminal_collection [--resume]

Reads the base collection (never writes it) and writes `<base>__ctx_v1`:
same ids, same metadata plus context fields, document = deterministic prefix +
raw text, embedded with the production model (multilingual-e5-base, "passage:"
prefix). Synthetic Q&A chunks are copied unchanged (retrieval excludes them).

Refuses to write into a non-empty target unless --resume (which skips ids
already present). Stop the backend first: Chroma is embedded, and a second
process on the same store raised a compaction error during this work.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from app.ai.contextual_index import CONTEXT_SCHEMA, collection_for, contextualize  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--collection", required=True)
    ap.add_argument("--variant", default="ctx_v1")
    ap.add_argument("--batch", type=int, default=48)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="only the first N chunks (smoke runs)")
    args = ap.parse_args()

    from app.db.chroma import connect_chroma, get_chroma
    from app.ai.pipelines.retriever import _embeddings
    connect_chroma()
    client = get_chroma()
    base = client.get_collection(args.collection)
    target_name = collection_for(args.collection, args.variant)
    if target_name == args.collection:
        print("refusing: the target is the base collection", file=sys.stderr)
        return 2
    target = client.get_or_create_collection(target_name, metadata={
        **(base.metadata or {}), "context_schema": CONTEXT_SCHEMA, "base_collection": args.collection})
    existing = set()
    off = 0
    while True:
        g = target.get(limit=2000, offset=off, include=[])
        if not g["ids"]:
            break
        existing.update(g["ids"])
        off += 2000
    if existing and not args.resume:
        print(f"refusing: {target_name} already holds {len(existing)} chunks (use --resume)", file=sys.stderr)
        return 3

    model = _embeddings()
    t0, done, off = time.perf_counter(), 0, 0
    while True:
        g = base.get(limit=500, offset=off, include=["documents", "metadatas"])
        if not g["ids"]:
            break
        off += 500
        rows = [(i, d, m) for i, d, m in zip(g["ids"], g["documents"], g["metadatas"]) if i not in existing]
        for k in range(0, len(rows), args.batch):
            part = rows[k:k + args.batch]
            docs, metas = [], []
            for _, text, meta in part:
                if (meta or {}).get("synthetic"):
                    docs.append(text)
                    metas.append(meta)
                else:
                    d, m = contextualize(meta, text)
                    docs.append(d)
                    metas.append(m)
            vecs = model.embed_documents(docs)
            target.add(ids=[i for i, _, _ in part], embeddings=vecs, documents=docs, metadatas=metas)
            done += len(part)
            rate = done / max(time.perf_counter() - t0, 1e-6)
            print(f"{done} chunks  ({rate:.1f}/s)", flush=True)
            if args.limit and done >= args.limit:
                print(f"stopped at --limit {args.limit}")
                return 0
    print(f"built {target_name}: {done} new chunks in {time.perf_counter() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
