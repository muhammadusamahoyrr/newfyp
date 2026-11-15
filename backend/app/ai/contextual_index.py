"""Deterministic contextual indexing (Batch 5, 2026-10-12).

A statute section embedded on its own loses its context ("under this Act...",
a section number with no instrument). Contextual retrieval prepends a short
header before embedding and BM25 indexing. Here the header is built ONLY from
canonical metadata -- never by a model -- so it cannot invent a chapter,
jurisdiction, status or amendment:

    Instrument: PPC 1860
    Provision: Section 489-F
    Jurisdiction: federal
    Area of law: criminal
    Status: in force (no omission on record)   | omitted (<instrument>, <date>)
    Chapter: unknown

Missing metadata stays "unknown", never guessed. The lettered-section loss in
the current index (PPC 489-F stored as "489") is repaired from the passage's
own header, the same rule the citation binder uses.

The contextual index is a SEPARATE, versioned collection (`<base>__ctx_v1`)
next to the production one; the production index is never modified. The raw
legal text is preserved: the stored document is `prefix + raw`, and
`context_prefix_len` lets readers strip the prefix back off before the text
reaches generation.
"""
from __future__ import annotations

import re

CONTEXT_SCHEMA = "ctx-v1"
INDEX_VARIANTS = ("base", "ctx_v1")

from app.ai.section_repair import LETTERED_HEADING as _LETTERED_HEADER  # noqa: E402 -- one shared rule


def collection_for(base_collection: str, variant: str | None) -> str:
    v = (variant or "base").strip().lower()
    return base_collection if v in ("", "base") else f"{base_collection}__{v}"


def provision_label(meta: dict, text: str) -> str:
    sec = str((meta or {}).get("section_number") or "").strip()
    m = _LETTERED_HEADER.match(text or "")
    if m and sec and sec == m.group(1):
        return f"{m.group(1)}-{m.group(2)}"
    return sec


def _status(statute: str, label: str) -> str:
    n = re.match(r"(\d+)$", label or "")
    if not statute or not n:
        return "unknown"
    try:
        from app.ai.statute_omissions import confirmed_records, get_records
        if statute not in get_records():
            return "unknown"          # no omission data for this instrument at all
        rec = confirmed_records(statute).get(int(n.group(1)))
    except Exception:  # noqa: BLE001
        return "unknown"
    if rec is None:
        return "no omission on record"
    return f"omitted ({rec.instrument or 'instrument not recorded'}, {rec.date or 'date not recorded'})"


def contextual_prefix(meta: dict, text: str) -> str:
    meta = meta or {}
    statute = (meta.get("statute") or "").strip()
    label = provision_label(meta, text)
    lines = [
        f"Instrument: {statute or 'unknown'}",
        f"Provision: {'Section ' + label if label else 'unknown'}",
        f"Jurisdiction: {(meta.get('province') or 'unknown').strip()}",
        f"Area of law: {(meta.get('law_type') or 'unknown').strip()}",
        f"Status: {_status(statute, label)}",
        "Chapter: unknown",
    ]
    return "\n".join(lines) + "\n\n"


def contextualize(meta: dict, text: str) -> tuple[str, dict]:
    """(document to store and embed, metadata for the contextual collection)."""
    prefix = contextual_prefix(meta, text)
    new_meta = dict(meta or {})
    new_meta.update({"context_schema": CONTEXT_SCHEMA, "context_prefix_len": len(prefix),
                     "provision_label": provision_label(meta, text)})
    return prefix + (text or ""), new_meta


def strip_context(text: str, meta: dict) -> str:
    """The raw legal text back from a contextual document."""
    n = (meta or {}).get("context_prefix_len")
    try:
        n = int(n)
    except (TypeError, ValueError):
        return text
    return text[n:] if 0 < n <= len(text or "") else text
