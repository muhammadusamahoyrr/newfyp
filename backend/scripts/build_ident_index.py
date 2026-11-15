"""Versioned provision-IDENTITY index for the civil corpus (2026-10-14).

  python scripts/build_ident_index.py            # dry run: report only, writes nothing
  python scripts/build_ident_index.py --build    # create civil_collection__ident_v1

WHY
---
The base `civil_collection` files two kinds of text under the wrong identity:
  * CPC First Schedule ORDER RULES as "sections": "17. Time for inspection when
    notice given" is Order XI Rule 17, stored as CPC section 17, and research
    answered "CPC Section 17";
  * the Limitation Act FIRST SCHEDULE (articles, "[Three years]") under section
    numbers such as 5 and 6, so "Article 58" text was cited as "Section 6".

WHAT THIS DOES -- metadata only, nothing re-embedded, nothing deleted
  * copies every chunk of `civil_collection` (same ids, same documents, the
    SAME embeddings) into a NEW collection `civil_collection__ident_v1`; the
    base collection is untouched, for rollback and A/B comparison;
  * gives every chunk `provision_kind` / `provision_label`:
      section          -- unchanged identity (a lettered label restored from
                          the chunk's own heading where that applies);
      order_rule       -- CPC First Schedule: the Order is the latest
                          "ORDER <roman>" heading in DOCUMENT ORDER (chunk ids
                          are sequential), the Rule is the chunk's OWN leading
                          heading. No leading heading -> "Order X (rule not
                          shown)": never guessed;
      schedule_article -- Limitation Act First Schedule: the article numbers are
                          the entry headers ("58.-") IN THIS CHUNK; a chunk
                          with none is "article not shown";
      appendix         -- CPC appendices (forms);
  * clears `section_number` for every order_rule / schedule_article / appendix
    chunk, so a "Section N" citation can no longer resolve to text that is not
    section N.
Chunk boundaries are unchanged, so no re-chunking or re-embedding is needed.
The criminal side needs no new index: `criminal_collection__sec_v2` already
carries lettered labels and cleared CrPC schedule-row sections.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
for _s in (sys.stdout,):
    _s.reconfigure(encoding="utf-8", errors="replace")

SOURCE = "civil_collection"
TARGET = "civil_collection__ident_v1"
IDENT_VERSION = "ident-v1"
BATCH = 200

_ORDER = re.compile(r"\bORDER\s+([IVXLC]+)\b")
# A HEADING: "ORDER XI" alone on its line (optionally "[TITLE]"), not a
# cross-reference such as "under ORDER X, rule 2".
_ORDER_HEADING = re.compile(r"(?m)^[ \t]*ORDER\s+([IVXLC]+)\b[ \t]*(?:\[[^\]\n]{0,80}\])?[ \t]*$")


def _roman(s: str) -> int:
    vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
    total = 0
    for a, b in zip(s, s[1:] + " "):
        v = vals[a]
        total += -v if b in vals and vals[b] > v else v
    return total
_FIRST_SCHEDULE_CPC = re.compile(r"THE FIRST SCHEDULE\s*\n?\s*ORDER\s+I\b")
_APPENDIX = re.compile(r"\bAPPENDIX\s+[A-H]\b")
_LIM_SCHEDULE = re.compile(r"THE FIRST SCHEDULE[\s\S]{0,200}Description of suit", re.IGNORECASE)
_LEADING_RULE = re.compile(r"^\W*(\d{1,3}[A-Z]?)\s*\.\s*[\-–_ ]*[A-Z(]")
_ENTRY = re.compile(r"(?<![\d.])(\d{1,3})\.\s*[\-–]\s*(?=[A-Z])")


def _overlay():
    spec = importlib.util.spec_from_file_location("serve", BACKEND / "scripts" / "serve.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    os.environ.update(mod.read_env_overlay(BACKEND / ".env.analyzer-demo.local"))


def _ordered(rows, statute):
    return sorted([r for r in rows if r[2].get("statute") == statute], key=lambda r: r[2].get("chunk_id", ""))


def plan_identities(rows):
    """rows: [(id, document, metadata)] -> {id: new metadata} (pure; testable)."""
    from app.ai.contextual_index import provision_label
    plan = {}
    for cid, doc, meta in rows:
        label = provision_label({"section_number": meta.get("section_number", "")}, doc)
        plan[cid] = {**meta, "provision_kind": "section", "provision_label": label or "",
                     "ident_version": IDENT_VERSION}
        if label and label != meta.get("section_number"):
            plan[cid]["section_number"] = label

    # CPC First Schedule: Orders and Rules, then appendices.
    #
    # The corpus holds the schedule TWICE (a partial copy whose ORDER headings
    # jump I -> IV -> V -> XII..., then the complete I..LI). "Latest heading"
    # would therefore guess: rules after a lone "ORDER I" may be Order II or
    # III. A chunk is given Order N only when its segment is bounded by
    # CONSECUTIVE headings (N then N+1, a repeat of N, or the schedule's end);
    # otherwise it is "order not determined". Never guessed.
    cpc = _ordered(rows, "CPC 1908")
    start = next((i for i, (_, d, _) in enumerate(cpc) if _FIRST_SCHEDULE_CPC.search(d)), None)
    if start is not None:
        app = next((i for i, (_, d, _) in enumerate(cpc) if i > start and _APPENDIX.search(d)), len(cpc))
        heads = [(i, m.start(), m.group(1)) for i, (_, d, _) in enumerate(cpc[start:app], start)
                 for m in _ORDER_HEADING.finditer(d)]

        def order_at(i: int, pos: int):
            before = [h for h in heads if (h[0], h[1]) <= (i, pos)]
            if not before:
                return None
            cur = before[-1]
            nxt = next((h for h in heads if (h[0], h[1]) > (cur[0], cur[1])), None)
            ok = nxt is None or _roman(nxt[2]) in (_roman(cur[2]), _roman(cur[2]) + 1)
            return cur[2] if ok else None

        for i, (cid, doc, meta) in enumerate(cpc[start:], start):
            if i == start:
                continue                         # opens in section text; heading mid-chunk
            if i >= app:
                plan[cid].update(section_number="", provision_kind="appendix", provision_label="CPC Appendix",
                                 source_region="schedule", schedule="First Schedule", ident_basis="sequence")
                continue
            head = _LEADING_RULE.match(doc)
            order = order_at(i, 0)
            base = dict(section_number="", provision_kind="order_rule", source_region="schedule",
                        schedule="First Schedule", order=order or "")
            if head and order and head.group(1) == str(meta.get("section_number")):
                plan[cid].update(**base, provision_label=f"Order {order} Rule {head.group(1)}",
                                 rule=head.group(1), ident_basis="sequence+heading")
            else:
                plan[cid].update(**base, rule="", ident_basis="sequence",
                                 provision_label=(f"Order {order} (rule not shown)" if order
                                                  else "CPC First Schedule (order not determined)"))

    # Limitation Act First Schedule: articles from this chunk's own entry headers.
    lim = _ordered(rows, "Limitation Act 1908")
    lstart = next((i for i, (_, d, _) in enumerate(lim) if _LIM_SCHEDULE.search(d)), None)
    if lstart is not None:
        for cid, doc, meta in lim[lstart + 1:]:
            arts = [m.group(1) for m in _ENTRY.finditer(doc)]
            if arts:
                lbl = (f"First Schedule, Article {arts[0]}" if len(set(arts)) == 1
                       else f"First Schedule, Articles {arts[0]}–{arts[-1]}")
            else:
                lbl = "First Schedule (article not shown)"
            plan[cid].update(section_number="", provision_kind="schedule_article", provision_label=lbl,
                             articles=",".join(arts), source_region="schedule", schedule="First Schedule",
                             ident_basis="heading")
    return plan


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    args = ap.parse_args()
    _overlay()
    from app.db.chroma import connect_chroma, get_chroma
    connect_chroma()
    client = get_chroma()
    src = client.get_collection(SOURCE)
    total = src.count()
    ids, docs, metas = [], [], []
    for off in range(0, total, 1000):
        got = src.get(include=["documents", "metadatas"], limit=1000, offset=off)
        ids += got["ids"]; docs += got["documents"]; metas += got["metadatas"]
    rows = list(zip(ids, docs, metas))
    plan = plan_identities(rows)
    kinds = Counter(m["provision_kind"] for m in plan.values())
    changed = sum(1 for cid, _, m in rows if plan[cid].get("section_number") != m.get("section_number"))
    print(f"source {SOURCE}: {total} chunks | kinds {dict(kinds)} | section_number changed on {changed}")
    for want in ("Time for inspection when notice given", "Like suit when the lender has given a cheque"):
        for cid, d, m in rows:
            if want in d:
                p = plan[cid]
                print(f"  sample {m.get('chunk_id')}: section {m.get('section_number')!r} -> "
                      f"{p.get('section_number')!r} | {p['provision_kind']} | {p['provision_label']}")
                break
    order_labels = Counter(p["provision_label"].split(" Rule")[0] for p in plan.values()
                           if p["provision_kind"] == "order_rule")
    print("  orders labelled:", len(order_labels), "e.g.", list(order_labels.items())[:6])
    if not args.build:
        print("dry run -- nothing written (use --build)")
        return 0
    names = [getattr(c, "name", c) for c in client.list_collections()]
    if TARGET in names:
        print(f"{TARGET} already exists -- refusing to overwrite (delete it explicitly to rebuild)")
        return 1
    dst = client.create_collection(TARGET, metadata={**(src.metadata or {}), "base_collection": SOURCE,
                                                     "ident_version": IDENT_VERSION})
    for off in range(0, total, BATCH):
        got = src.get(include=["documents", "metadatas", "embeddings"], limit=BATCH, offset=off)
        dst.add(ids=got["ids"], documents=got["documents"], embeddings=got["embeddings"],
                metadatas=[plan[i] for i in got["ids"]])
    print(f"built {TARGET}: {dst.count()} chunks (source {total})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
