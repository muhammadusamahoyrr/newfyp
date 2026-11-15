"""ISOLATED parsing pilot for the legal-source registry (2026-10-16).

Reads one official PDF, splits it into provisions with the SAME splitter the
statute ingestion uses (app.ai.section_repair.split_provisions), and writes
provisions plus provenance to a JSONL file in a directory you name. Then runs
the parsing checks and writes a report next to it.

It never opens Chroma, MongoDB or the network, and refuses to write inside the
repository's data stores:

    python scripts/pilot_legal_sources.py --pdf <file.pdf> --source-id pk.fed.court-fees-act-1870 \
        --out <scratch dir>

What it records per provision: source_id, sha256 of the exact PDF bytes, page,
provision kind and label, region (body / schedule / footnote quote), and the
amending instruments named in that provision's footnotes ("Subs. by Act II of
2025") -- the pointer a version-history lane needs. It does NOT claim the text
is current: Pakistan Code states its texts are for information and the Gazette
governs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.ai.legal_sources.identity import parse_instrument_number  # noqa: E402
from app.ai.section_repair import SPLIT_VERSION, section_label, split_provisions  # noqa: E402

PILOT_VERSION = "legal-sources-pilot-v1"
_FORBIDDEN = ("chroma_data", "chroma_db")

# The body starts where "1. Short title" is followed by the Act's own words,
# not where the contents page lists it.
_BODY_START = re.compile(r"(?m)^\s*1\.\s*Short title[^\n]{0,80}\n?[\s\S]{0,40}?(?:This Act|\(1\)\s*This Act)")
_FOOTNOTE_AMEND = re.compile(
    r"(?i)\b(?:Subs(?:tituted)?|Ins(?:erted)?|Added|Omitted|Renumbered|Amended)\.?\s+(?:by|vide)\s+([^\n;]{3,160})")
_PAGE_MARK = re.compile(r"Page\s+\d+\s+of\s+\d+")
# Pakistan Code prints a repealed/omitted provision as its number and asterisks:
# "2. 4[* * * * * * *]". The shared splitter records these as ordinary sections.
_ASTERISK_BODY = re.compile(r"^\s*\d{1,3}[A-Z]{0,2}\s*[.\-]\s*\d*\s*\[\s*\*(?:\s*\*)+\s*\]\s*$")
# A lettered heading printed mid-line ("...underpayment. 19H. Notice of ...")
# that the line-anchored splitter cannot see.
_MIDLINE_LETTERED = re.compile(r"(?<![\w(])(\d{1,3})\s*-?\s*([A-Z]{1,2})\.\s*_*\s*[A-Z][a-z]")


def _refuse_store_path(out: Path) -> None:
    parts = {p.lower() for p in out.resolve().parts}
    if any(f in parts for f in _FORBIDDEN) or any(p.startswith("chroma_data") for p in parts):
        raise SystemExit(f"refusing to write inside a data store: {out}")


def extract_pages(pdf: Path) -> list[str]:
    from pypdf import PdfReader
    return [(p.extract_text() or "") for p in PdfReader(str(pdf)).pages]


def _page_of(offsets: list[int], pos: int) -> int:
    page = 1
    for i, start in enumerate(offsets):
        if pos >= start:
            page = i + 1
    return page


def run(pdf: Path, source_id: str, out_dir: Path) -> dict:
    _refuse_store_path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = pdf.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    pages = extract_pages(pdf)
    offsets, buf = [], []
    pos = 0
    for t in pages:
        offsets.append(pos)
        t = _PAGE_MARK.sub("", t) + "\n"
        buf.append(t)
        pos += len(t)
    text = "".join(buf)

    m = _BODY_START.search(text)
    body_from = m.start() if m else 0
    blocks = split_provisions(text[body_from:])

    rows, cursor = [], body_from
    for i, b in enumerate(blocks):
        found = text.find(b["text"][:60], cursor)
        start = found if found >= 0 else cursor
        cursor = max(cursor, start)
        refs = sorted({" ".join(r.split()) for r in _FOOTNOTE_AMEND.findall(b["text"])})
        nums = [n for n in (parse_instrument_number(r) for r in refs) if n]
        kind = "schedule" if b["region"] == "schedule" else ("preamble" if b["section"] is None else "section")
        rows.append({
            "chunk_id": f"{source_id}#{i:04d}",
            "source_id": source_id,
            "document_hash": sha,
            "provision_kind": kind,
            "provision_label": (f"Schedule {b['schedule']}" if kind == "schedule"
                                else section_label(b["section"]) if b["section"] else None),
            "region": b["region"],
            "heading_rule": b["heading_rule"],
            "provision_status": b["provision_status"],
            "omitted_by": b["omitted_by"],
            "source_page": _page_of(offsets, start),
            "amendment_refs": refs,
            "amending_instruments": [f"{n['kind'].title()} {n['number']} of {n['year']}"
                                     + (f" ({n['jurisdiction']})" if n["jurisdiction"] else "")
                                     for n in nums],
            "split_version": SPLIT_VERSION,
            "pilot_version": PILOT_VERSION,
            "text": b["text"],
        })

    report = checks(rows, body_found=bool(m))
    report.update({"source_id": source_id, "pdf": pdf.name, "document_hash": sha, "pages": len(pages),
                   "bytes": len(raw), "split_version": SPLIT_VERSION, "pilot_version": PILOT_VERSION})
    stem = source_id.replace("/", "_")
    (out_dir / f"{stem}.provisions.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    (out_dir / f"{stem}.report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


_BRACKETED_INSERTION = re.compile(r"\d{1,2}\[\s*(\d{1,3})\s*-?\s*([A-Z]{1,2})\s*[.,]\s*[A-Z]")


def _bracketed_insertions(rows: list[dict]) -> list[dict]:
    labels = {r["provision_label"] for r in rows}
    out = []
    for r in rows:
        if r["provision_kind"] != "section":
            continue                      # "13-A" inside a schedule is a schedule article
        for m in _BRACKETED_INSERTION.finditer(r["text"]):
            lab = f"{m.group(1)}-{m.group(2)}"
            if lab not in labels:
                out.append({"provision": lab, "filed_under": r["provision_label"]})
    return out


def checks(rows: list[dict], body_found: bool) -> dict:
    """Controlled parsing checks. Each is a fact about the output, not a verdict on the law."""
    sections = [r["provision_label"] for r in rows if r["provision_kind"] == "section"]
    numeric = []
    for s in sections:
        mm = re.match(r"^(\d+)", s or "")
        if mm:
            numeric.append(int(mm.group(1)))
    dupes = sorted({s for s in sections if sections.count(s) > 1})
    backwards = [(a, b) for a, b in zip(numeric, numeric[1:]) if b + 5 < a]   # a big step back = mis-split
    tiny = [r["provision_label"] for r in rows if r["provision_kind"] == "section" and len(r["text"]) < 40]
    asterisk = [r["provision_label"] for r in rows if r["provision_kind"] == "section"
                and _ASTERISK_BODY.match((r["text"] or "").strip().splitlines()[0])
                and len(r["text"].strip()) < 200]
    buried = []
    for r in rows:
        if r["provision_kind"] != "section" or not r["provision_label"]:
            continue
        base = re.match(r"^(\d+)", r["provision_label"]).group(1)
        for m in _MIDLINE_LETTERED.finditer(r["text"][8:]):
            if m.group(1) == base and f"{m.group(1)}-{m.group(2)}" != r["provision_label"]:
                buried.append({"inside": r["provision_label"], "heading": f"{m.group(1)}-{m.group(2)}"})
    return {
        "body_start_found": body_found,
        "provisions": len(rows),
        "sections": len(sections),
        "lettered_sections": sorted({s for s in sections if s and "-" in s}),
        "schedules": [r["provision_label"] for r in rows if r["provision_kind"] == "schedule"],
        "duplicate_section_labels": dupes,
        "out_of_order_jumps": backwards[:20],
        "very_short_sections": tiny[:20],
        "omitted_provisions": [r["provision_label"] for r in rows if r["provision_status"] == "omitted"],
        # Defects the shared splitter does not handle; reported, not repaired here.
        "asterisk_omitted_recorded_as_sections": asterisk,
        "buried_lettered_headings": buried[:30],
        # An INSERTED provision printed behind its footnote marker -- "1[26A,
        # Punishment for false and fake information" -- is invisible to the
        # line-anchored splitter, so its text is filed under the PRECEDING
        # section (PECA 26A inside 26). Reported; repairing it changes the
        # shared splitter, which is a separate decision.
        "footnote_bracketed_insertions_not_split": _bracketed_insertions(rows),
        "provisions_with_amendment_refs": sum(1 for r in rows if r["amendment_refs"]),
        "amending_instruments_named": sorted({a for r in rows for a in r["amending_instruments"]}),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pdf", required=True, type=Path)
    ap.add_argument("--source-id", required=True)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    rep = run(a.pdf, a.source_id, a.out)
    print(json.dumps({k: v for k, v in rep.items() if k not in {"amending_instruments_named"}}, indent=2))
    print("amending instruments named:", len(rep["amending_instruments_named"]))


if __name__ == "__main__":
    main()
