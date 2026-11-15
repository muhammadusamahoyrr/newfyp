"""build_section_index.py — audit / rebuild the lettered-section labels as a
VERSIONED collection (2026-10-13).

  python scripts/build_section_index.py --audit
  python scripts/build_section_index.py --build --collection criminal_collection [--resume]

--audit   reads every statute collection and writes a JSON report of chunks
          whose stored section lost its letter, how each would be repaired,
          and lettered headings buried mid-chunk (which need re-chunking).
--build   copies the base collection into `<base>__sec_v1` with repaired
          `section_number` (+ `section_number_original`, `section_repair`).
          Documents and EMBEDDINGS are copied unchanged -- the text did not
          change, so nothing is re-embedded. The base collection is never
          written; a non-empty target is refused without --resume.

Selecting it for A/B: settings.retrieval_index_variant = "sec_v1" (falls back
to the base collection, logged, wherever no sec_v1 copy exists).

Stop the backend first: Chroma is embedded.

THE PLAN, versioned
  sec_v1  relabel copy (this script)     -- 73 chunks, no re-embedding
  sec_v2  full re-ingest from the PDFs with the fixed ingest_statutes.py
          parser -- also splits the one buried heading (PPC 216-B); needs
          re-embedding (~3.3k criminal chunks at ~2 chunks/s on this CPU)
          and a fresh eval run before any promotion.
"""
from __future__ import annotations

import argparse
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

from app.ai.contextual_index import collection_for  # noqa: E402
from app.ai.section_repair import REPAIR_VERSION, buried_lettered_headings, relabels, repair_labels  # noqa: E402

STATUTE_COLLECTIONS = ("criminal_collection", "civil_collection", "family_collection",
                       "constitutional_collection")
VARIANT = "sec_v1"


def _all(col, include):
    out = {"ids": [], "metadatas": [], "documents": [], "embeddings": []}
    off = 0
    while True:
        g = col.get(limit=500, offset=off, include=include)
        if not g["ids"]:
            return out
        for k in out:
            if g.get(k) is not None:
                out[k].extend(list(g[k]))
        off += 500


def audit(client) -> dict:
    report = {"schema": "section-audit-v1", "repair_version": REPAIR_VERSION,
              "timestamp": datetime.now(timezone.utc).isoformat(), "collections": {}}
    for name in STATUTE_COLLECTIONS:
        g = _all(client.get_collection(name), ["metadatas", "documents"])
        rows = list(zip(g["ids"], g["metadatas"], g["documents"]))
        all_fixes = repair_labels(rows)
        fixes = relabels(all_fixes)
        buried = [{"chunk_id": i, "stored": (m or {}).get("section_number"), "buried": b}
                  for i, m, d in rows for b in [buried_lettered_headings(d)] if b]
        by_statute: dict[str, int] = {}
        meta = {i: m for i, m, _ in rows}
        for cid in fixes:
            st = (meta[cid] or {}).get("statute") or "?"
            by_statute[st] = by_statute.get(st, 0) + 1
        report["collections"][name] = {
            "chunks": len(rows), "relabel": len(fixes), "by_statute": by_statute,
            "skipped_out_of_sequence": sorted(k for k, v in all_fixes.items() if v["how"] == "skipped_out_of_sequence"),
            "unresolved_letterless_heading": sorted(k for k, v in all_fixes.items()
                                                    if v["how"] == "unresolved_letterless_heading"),
            "fixes": [{"chunk_id": k, "statute": (meta[k] or {}).get("statute"), **v}
                      for k, v in sorted(fixes.items())],
            "buried_mid_chunk": buried,
        }
    return report


def build(client, base_name: str, resume: bool) -> int:
    target_name = collection_for(base_name, VARIANT)
    if target_name == base_name:
        print("refusing: the target is the base collection", file=sys.stderr)
        return 2
    base = client.get_collection(base_name)
    target = client.get_or_create_collection(target_name, metadata={
        **(base.metadata or {}), "section_repair": REPAIR_VERSION, "base_collection": base_name})
    existing = set(_all(target, [])["ids"])
    if existing and not resume:
        print(f"refusing: {target_name} already holds {len(existing)} chunks (use --resume)", file=sys.stderr)
        return 3
    g = _all(base, ["metadatas", "documents", "embeddings"])
    fixes = relabels(repair_labels(list(zip(g["ids"], g["metadatas"], g["documents"]))))
    ids, docs, metas, vecs = [], [], [], []
    for cid, meta, doc, vec in zip(g["ids"], g["metadatas"], g["documents"], g["embeddings"]):
        if cid in existing:
            continue
        meta = dict(meta or {})
        fix = fixes.get(cid)
        if fix:
            meta.update({"section_number": fix["section_number"],
                         "section_number_original": fix["original"],
                         "section_repair": f"{REPAIR_VERSION}:{fix['how']}"})
        ids.append(cid)
        docs.append(doc)
        metas.append(meta)
        vecs.append(list(vec))
    for k in range(0, len(ids), 500):
        target.add(ids=ids[k:k + 500], documents=docs[k:k + 500],
                   metadatas=metas[k:k + 500], embeddings=vecs[k:k + 500])
    print(f"built {target_name}: {len(ids)} chunks copied, {sum(1 for i in ids if i in fixes)} relabelled")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", action="store_true")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--collection", default="criminal_collection")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    from app.db.chroma import connect_chroma, get_chroma
    connect_chroma()
    client = get_chroma()
    if args.audit:
        rep = audit(client)
        out = Path(args.out or BACKEND_DIR / "evals" / "legal_rag" / "results" /
                   f"section_audit_{datetime.now().strftime('%Y-%m-%d_%H%M')}.json")
        out.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
        for name, c in rep["collections"].items():
            print(f"{name}: {c['chunks']} chunks, relabel {c['relabel']} {c['by_statute']}, "
                  f"buried {len(c['buried_mid_chunk'])}")
        print(f"report: {out}")
    if args.build:
        return build(client, args.collection, args.resume)
    return 0


if __name__ == "__main__":
    sys.exit(main())
