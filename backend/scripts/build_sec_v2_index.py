"""build_sec_v2_index.py — rebuild the criminal statute index with the
section-split-v2 parser, as a VERSIONED collection (2026-10-13).

  python scripts/build_sec_v2_index.py --plan                # dry run: diff + cost, writes nothing
  python scripts/build_sec_v2_index.py --build [--resume]    # writes criminal_collection__sec_v2
  python scripts/build_sec_v2_index.py --audit               # base vs sec_v1 vs sec_v2 report

WHAT IS REBUILT
  PPC 1860 and CrPC 1898 are re-split from their source PDFs with
  app/ai/section_repair.split_provisions (the parser scripts/ingest_statutes.py
  now uses). Every other statute in the collection is copied unchanged,
  embeddings included.

EMBEDDINGS
  A rebuilt chunk whose text is byte-identical to a base chunk reuses that
  chunk's embedding and id (and is recorded with `base_chunk_id`). A chunk
  whose text or boundary changed is re-embedded with the production model
  (multilingual-e5-base, "passage:" prefix) and gets a `secv2_` id.

NEVER WRITTEN: criminal_collection (base) and criminal_collection__sec_v1.
A non-empty target is refused without --resume (which skips ids present).
Stop the backend first: Chroma is embedded.

Known limit: the law graph (hop 2) is keyed on base chunk ids; a re-embedded
sec_v2 chunk has a new id, so hop 2 falls back to its text query for it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "scripts"))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import ingest_statutes as ING  # noqa: E402
from app.ai.contextual_index import collection_for  # noqa: E402
from app.ai.section_repair import (DEFERRED_LETTER_HEADING, SPLIT_VERSION,  # noqa: E402
                                   buried_lettered_headings, section_label)

BASE = "criminal_collection"
VARIANT = "sec_v2"
SCHEMA = "sec-v2"
SOURCE_DIR = Path(r"C:\Users\The Laptop Hut\Desktop\specific_case_data")
REBUILT = {
    "PPC 1860": ("PAKISTAN PENAL CODE.pdf", "criminal", "federal"),
    "CrPC 1898": ("Code_of_criminal_procedure_1898.pdf", "criminal", "federal"),
}
# Schedule parts and how retrieval must treat them (same treatment the base
# index's tags gave them: tables carry PPC numbers that are not this statute's
# sections; forms are reference-only).
_SCHEDULE_TAGS = {
    "V": {"text_kind": "forms", "retrieval_scope": "reference_only", "attribution_status": "misattributed"},
}
_TABLE_TAGS = {"text_kind": "table", "retrieval_scope": "default", "attribution_status": "misattributed"}

# The provisions this rebuild exists to get right (the acceptance list).
EXPECTED = {
    "PPC 1860": ["108A", "120A", "120B", "165A", "165B", "216A", "216B", "298A", "298B", "298C",
                 "337", "337A", "489", "489A", "489B", "489C", "489D", "489E", "489F"],
    "CrPC 1898": ["22", "22A", "22B", "154", "497", "561A"],
}

# The pre-2026-10-13 heading pattern, kept ONLY to prove the base index is
# reproducible from these PDFs (traceability), never to build anything.
_OLD_SECTION_RE = re.compile(r"^\s*(\d+[A-Z]?)\s*[.\-]\s+(?=\S)", re.M)


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


def _old_chunk_texts(text: str) -> set[str]:
    splits, last_end, last_sec = [], 0, None
    for m in _OLD_SECTION_RE.finditer(text):
        if m.start() > last_end:
            splits.append((last_sec, text[last_end:m.start()].strip()))
        last_sec, last_end = m.group(1), m.start()
    splits.append((last_sec, text[last_end:].strip()))
    out = set()
    for _, block in splits:
        for part in ([block] if len(block) <= ING.CHUNK_SIZE else ING._slide(block)):
            if part.strip():
                out.add(part.strip())
    return out


def _page_index(pdf: Path) -> tuple[str, list[int]]:
    from pypdf import PdfReader
    pages = [(p.extract_text() or "") for p in PdfReader(str(pdf)).pages]
    starts, pos = [], 0
    for p in pages:
        starts.append(pos)
        pos += len(p) + 1
    return "\n".join(pages), starts


def _page_of(raw: str, starts: list[int], part: str, hint: int) -> tuple[int, int]:
    probe = part[:60]
    at = raw.find(probe, hint)
    if at < 0:
        at = raw.find(probe)
    if at < 0:
        return 0, hint
    page = max(i for i, s in enumerate(starts) if s <= at) + 1
    return page, at


def _clean(meta: dict) -> dict:
    """Chroma rejects None metadata values."""
    return {k: v for k, v in meta.items() if v is not None}


def plan(client) -> dict:
    """Every sec_v2 chunk, with its embedding source. Writes nothing."""
    base = _all(client.get_collection(BASE), ["metadatas", "documents", "embeddings"])
    by_text: dict[str, int] = {}
    for k, d in enumerate(base["documents"]):
        by_text.setdefault(d, k)

    rows, report = [], {"statutes": {}}
    used_ids: set[str] = set()
    for statute, (fname, law_type, province) in REBUILT.items():
        pdf = SOURCE_DIR / fname
        text = ING.extract_text(pdf)
        raw, starts = _page_index(pdf)
        base_texts = {d for d, m in zip(base["documents"], base["metadatas"])
                      if (m or {}).get("statute") == statute and (m or {}).get("source_file") == fname}
        old = _old_chunk_texts(text)
        # Pinned: sec_v2 is the section-split-v2 index; v3 never builds it.
        chunks = ING.make_chunks(text, statute, law_type, fname, province, SPLIT_VERSION)
        reused = changed = 0
        hint = 0
        for c in chunks:
            meta = dict(c["meta"])
            sched = meta.get("schedule") or ""
            if meta.get("source_region") == "schedule":
                meta.update(_SCHEDULE_TAGS.get(sched, _TABLE_TAGS))
            sec = meta.get("section_number") or ""
            page, hint = _page_of(raw, starts, c["content"], hint)
            meta.update({
                "sec_schema": SCHEMA, "instrument": statute, "jurisdiction": province,
                "document_type": "statute", "section_label": section_label(sec),
                "section_normalized": sec, "source_page": page,
            })
            k = by_text.get(c["content"])
            base_id = base["ids"][k] if k is not None else None
            if base_id and base_id not in used_ids:
                cid, emb = base_id, base["embeddings"][k]
                meta.update({"base_chunk_id": base_id, "embedding_reused": True, "boundary_changed": False})
                reused += 1
            else:
                cid, emb = c["id"].replace("statutes_", "secv2_", 1), None
                meta.update({"base_chunk_id": "", "embedding_reused": False, "boundary_changed": True})
                changed += 1
            used_ids.add(cid)
            meta["chunk_id"] = cid
            rows.append((cid, c["content"], _clean(meta), emb))
        report["statutes"][statute] = {
            "source_pdf": fname,
            "base_chunks": len(base_texts),
            "base_reproducible_by_old_parser": round(len(base_texts & old) / max(len(base_texts), 1), 4),
            "sec_v2_chunks": len(chunks),
            "embedding_reused": reused,
            "re_embedded": changed,
            "base_chunks_dropped": len(base_texts - {c["content"] for c in chunks}),
        }

    copied = 0
    for cid, meta, doc, emb in zip(base["ids"], base["metadatas"], base["documents"], base["embeddings"]):
        m = meta or {}
        if m.get("statute") in REBUILT and m.get("source_file") == REBUILT[m["statute"]][0]:
            continue
        m = dict(m)
        m.update({"sec_schema": SCHEMA, "base_chunk_id": cid, "embedding_reused": True,
                  "boundary_changed": False})
        rows.append((cid, doc, _clean(m), emb))
        copied += 1
    report["copied_unchanged"] = copied
    report["total"] = len(rows)
    report["to_embed"] = sum(1 for r in rows if r[3] is None)
    return {"rows": rows, "report": report}


def build(client, resume: bool) -> int:
    target_name = collection_for(BASE, VARIANT)
    if target_name in (BASE, collection_for(BASE, "sec_v1")):
        print("refusing: the target is a protected collection", file=sys.stderr)
        return 2
    p = plan(client)
    base_col = client.get_collection(BASE)
    target = client.get_or_create_collection(target_name, metadata={
        **(base_col.metadata or {}), "sec_schema": SCHEMA, "split_version": SPLIT_VERSION,
        "base_collection": BASE})
    existing = set(_all(target, [])["ids"])
    if existing and not resume:
        print(f"refusing: {target_name} already holds {len(existing)} chunks (use --resume)", file=sys.stderr)
        return 3
    rows = [r for r in p["rows"] if r[0] not in existing]
    from app.ai.pipelines.retriever import _embeddings
    model = None
    t0, done = time.perf_counter(), 0
    for k in range(0, len(rows), 48):
        part = rows[k:k + 48]
        need = [i for i, r in enumerate(part) if r[3] is None]
        vecs = {}
        if need:
            model = model or _embeddings()
            got = model.embed_documents([part[i][1] for i in need])
            vecs = dict(zip(need, got))
        target.add(ids=[r[0] for r in part], documents=[r[1] for r in part],
                   metadatas=[r[2] for r in part],
                   embeddings=[list(vecs[i]) if r[3] is None else list(r[3]) for i, r in enumerate(part)])
        done += len(part)
        if need:
            print(f"{done}/{len(rows)} written ({time.perf_counter() - t0:.0f}s)", flush=True)
    print(f"built {target_name}: {done} chunks in {time.perf_counter() - t0:.0f}s; report:")
    print(json.dumps(p["report"], indent=2))
    return 0


# ── audit: base vs sec_v1 vs sec_v2 ─────────────────────────────────────────

_HEAD_AT_START = re.compile(r"^\s*(\d+)(?:\s*-?\s*([A-Z]{1,2})[ \t]*(?:[.:]|(?=\n))|\s*[.\-]\s)")


def _audit_collection(col) -> dict:
    g = _all(col, ["metadatas", "documents"])
    rows = list(zip(g["ids"], g["metadatas"], g["documents"]))
    out: dict = {"chunks": len(rows), "by_statute": {}}
    for statute in list(REBUILT):
        mine = [(i, m or {}, d) for i, m, d in rows if (m or {}).get("statute") == statute
                and (m or {}).get("source_file") == REBUILT[statute][0]]
        live = [(i, m, d) for i, m, d in mine
                if m.get("attribution_status") != "misattributed" and m.get("provision_status") != "omitted"]
        secs = Counter(str(m.get("section_number") or "") for _, m, _ in live if m.get("section_number"))
        heading_chunks = Counter()
        malformed = []
        for i, m, d in live:
            h = _HEAD_AT_START.match(d or "")
            dl = DEFERRED_LETTER_HEADING.match(d or "")
            if h:
                # "298- Title: B." carries its letter after the title.
                label = (dl.group(1) + dl.group(2)) if dl else h.group(1) + (h.group(2) or "")
                heading_chunks[label] += 1
                if str(m.get("section_number") or "") != label:
                    malformed.append({"chunk_id": i, "stored": m.get("section_number"), "heading": label})
        lettered = sorted(s for s in secs if re.search(r"[A-Z]$", s))
        out["by_statute"][statute] = {
            "chunks": len(mine),
            "provisions": len(secs),
            "lettered_provisions": len(lettered),
            "heading_label_mismatch": len(malformed),
            "heading_label_mismatch_examples": malformed[:15],
            "buried_lettered_headings": sum(len(buried_lettered_headings(d)) for _, _, d in live),
            "duplicate_heading_chunks": sorted(k for k, v in heading_chunks.items() if v > 1),
            "omitted_quotes_marked": sum(1 for _, m, _ in mine if m.get("provision_status") == "omitted"),
            "missing_expected": [e for e in EXPECTED[statute] if e not in secs
                                 and not any(m.get("section_number") == e for _, m, _ in mine)],
            "expected_present": {e: secs.get(e, 0) for e in EXPECTED[statute]},
            "traceable_source_file": sum(1 for _, m, _ in mine if m.get("source_file")),
            "traceable_page": sum(1 for _, m, _ in mine if m.get("source_page")),
            "boundary_changed": sum(1 for _, m, _ in mine if m.get("boundary_changed")),
            "re_embedded": sum(1 for _, m, _ in mine if m.get("embedding_reused") is False),
        }
    return out


def audit(client) -> dict:
    rep = {"schema": "section-index-audit-v2", "split_version": SPLIT_VERSION,
           "timestamp": datetime.now(timezone.utc).isoformat(), "collections": {}}
    for name in (BASE, collection_for(BASE, "sec_v1"), collection_for(BASE, VARIANT)):
        try:
            col = client.get_collection(name)
        except Exception:
            rep["collections"][name] = "not built"
            continue
        rep["collections"][name] = _audit_collection(col)
        ids = _all(col, [])["ids"]
        rep["collections"][name]["id_fingerprint"] = hashlib.sha256("\n".join(sorted(ids)).encode()).hexdigest()[:16]
    return rep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--audit", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    from app.db.chroma import connect_chroma, get_chroma
    connect_chroma()
    client = get_chroma()
    if args.plan:
        rep = plan(client)["report"]
        rate = 2.0   # measured on this CPU during the ctx_v1 build, chunks/s
        rep["estimated_embed_seconds"] = round(rep["to_embed"] / rate)
        print(json.dumps(rep, indent=2))
    if args.build:
        rc = build(client, args.resume)
        if rc:
            return rc
    if args.audit:
        rep = audit(client)
        out = Path(args.out or BACKEND_DIR / "evals" / "legal_rag" / "results" /
                   f"sec_index_audit_{datetime.now().strftime('%Y-%m-%d_%H%M')}.json")
        out.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"report: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
