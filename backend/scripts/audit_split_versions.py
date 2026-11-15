"""Before/after audit of the statute splitter: section-split-v2 vs v3 (2026-10-16).

For each PDF, splits the same extracted text with both versions and reports
what v3 changes: provisions it ADDS (and which v2 provision their text used to
sit in), provisions it marks omitted, v2 labels it would LOSE (must be none),
and v2 blocks whose text v3 shortens. Pure; reads PDFs, writes a JSON report.
Never touches Chroma, MongoDB or the network.

    python scripts/audit_split_versions.py --pdf a.pdf --pdf b.pdf --out <scratch>/split_audit.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.ai.section_repair import (  # noqa: E402
    SPLIT_VERSION, SPLIT_VERSION_V3, section_label, split_provisions,
)


def extract(pdf: Path) -> str:
    """EXACTLY the text ingestion would split: its own extraction and its own
    contents-page removal (scripts/ingest_statutes.py). Importing that script
    creates no Chroma client -- only its `connect_chroma()` does, never called."""
    import contextlib
    import importlib.util
    import io
    spec = importlib.util.spec_from_file_location("ingest_statutes", BACKEND / "scripts" / "ingest_statutes.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with contextlib.redirect_stdout(io.StringIO()):
        return mod.extract_text(pdf)


def compare(text: str) -> dict:
    v2 = split_provisions(text, SPLIT_VERSION)
    v3 = split_provisions(text, SPLIT_VERSION_V3)
    c2 = Counter(b["section"] for b in v2 if b["region"] != "schedule")
    c3 = Counter(b["section"] for b in v3 if b["region"] != "schedule")
    added = sorted((c3 - c2).elements(), key=lambda s: (len(s or ""), s or ""))
    lost = sorted((c2 - c3).elements(), key=lambda s: (len(s or ""), s or ""))

    def holder(sec: str) -> str | None:
        """The v2 provision whose text contained this v3 provision's heading."""
        b3 = next(b for b in v3 if b["section"] == sec)
        probe = b3["text"][:80]
        for b in v2:
            if b["region"] != "schedule" and probe in b["text"] and b["section"] != sec:
                return section_label(b["section"]) if b["section"] else "(preamble)"
        return None

    v2_text = {}
    for b in v2:
        v2_text.setdefault(b["section"], []).append(b["text"])
    shortened = []
    for b in v3:
        olds = v2_text.get(b["section"]) or []
        if b["region"] != "schedule" and olds and b["text"] not in olds:
            shortened.append(section_label(b["section"]))
    omitted_v2 = {section_label(b["section"]) for b in v2 if b["provision_status"] == "omitted"}
    return {
        "blocks": {"v2": len(v2), "v3": len(v3)},
        "added_by_v3": [{"provision": section_label(s), "was_inside_v2": holder(s),
                         "heading_rule": next(b["heading_rule"] for b in v3 if b["section"] == s)} for s in added],
        "lost_by_v3": [section_label(s) for s in lost],
        "newly_marked_omitted": sorted({section_label(b["section"]) for b in v3
                                        if b["provision_status"] == "omitted"} - omitted_v2),
        "v2_blocks_shortened": sorted(set(shortened), key=lambda s: (len(s), s)),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pdf", action="append", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    if any(p.lower().startswith("chroma") for p in a.out.resolve().parts):
        raise SystemExit("refusing to write inside a data store")
    report = {"schema": "split-version-audit-v1", "from": SPLIT_VERSION, "to": SPLIT_VERSION_V3, "documents": {}}
    for pdf in a.pdf:
        rep = compare(extract(pdf))
        rep["sha256"] = hashlib.sha256(pdf.read_bytes()).hexdigest()
        report["documents"][pdf.name] = rep
        print(f"{pdf.name}: +{len(rep['added_by_v3'])} provisions, -{len(rep['lost_by_v3'])} lost, "
              f"{len(rep['newly_marked_omitted'])} newly omitted, {len(rep['v2_blocks_shortened'])} v2 blocks shortened")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
