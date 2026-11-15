"""Lawyer Draft Assistant evaluation V2 (2026-10-15).

    python scripts/eval_drafter_v2.py audit    [--src DIR]   # local privacy/provenance audit, no model
    python scripts/eval_drafter_v2.py validate                # dataset integrity checks, no model
    python scripts/eval_drafter_v2.py transmit-preview        # EXACTLY what a model run would send (synthetic only)
    python scripts/eval_drafter_v2.py run --label X --approved # real model -- only after the user approves
    python scripts/eval_drafter_v2.py score results/X.jsonl

V2 is a SEPARATE benchmark from V1 (evals/drafter, 29 aiattorney cases).
Their scores must never be compared directly.

Source collection (read-only): a folder of third-party Pakistani templates
and practitioner drafts (legaldocs.pk rebuilt templates; a public "Drafts"
Drive folder). The audit reads it LOCALLY and records only hashes,
categories, counts and risk flags -- never names, numbers, addresses or
template wording. V2 cases are SYNTHETIC: written for this eval, inspired by
the collection's CATEGORIES, with no source wording, and the document each
request carries is a synthetic skeleton written here. Nothing from the source
folder is ever sent to a model.
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "scripts"))
for _s in (sys.stdout, sys.stderr):
    _s.reconfigure(encoding="utf-8", errors="replace")

V2_DIR = BACKEND_DIR / "evals" / "drafter_v2"
CASES = V2_DIR / "cases_v2.jsonl"
SOURCES = V2_DIR / "legal_sources.json"
AUDIT = V2_DIR / "source_audit.json"
HOLDOUT_LOCK = V2_DIR / "holdout.lock.json"
RESULTS = V2_DIR / "results"
DEFAULT_SRC = Path.home() / "Desktop" / "error"
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml")
    if re.search(rb"<!(?:DOCTYPE|ENTITY)", xml, re.I):     # third-party file: no DTDs
        raise ValueError("document.xml declares a DTD")
    root = ET.fromstring(xml)
    return "\n".join("".join(t.text or "" for t in p.iter(_W + "t")) for p in root.iter(_W + "p"))

# ── privacy screen: COUNTS ONLY ──────────────────────────────────────────────
# A zero here is not proof of no personal data; every practitioner draft is
# flagged for manual review regardless.
_PII = {
    "cnic": re.compile(r"\b\d{5}-?\d{7}-?\d\b"),
    "mobile": re.compile(r"(?:\+92|\b0)3\d{2}[-\s]?\d{7}\b"),
    "landline": re.compile(r"\b0\d{2,3}[-\s]\d{6,8}\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"),
    "case_number": re.compile(r"(?i)\b(?:Suit|Petition|Appeal|Case|F\.?I\.?R|C\.?P|Cr\.?\s?Misc)\.?\s*No\.?\s*\d{1,6}\s*(?:/|of)\s*(?:19|20)\d{2}"),
    "relation_name": re.compile(r"\b(?:[SDW]/[Oo]|son of|daughter of|wife of)\.?\s+[A-Z][a-z]{2,}"),
    "titled_name": re.compile(r"\b(?:Mr|Mst|Mrs|Miss|Syed|Muhammad|Mohammad|Malik|Ch)\.?\s+[A-Z][a-z]{2,}"),
    "address": re.compile(r"(?i)\b(?:House|Plot|Flat|Shop|Office)\s*(?:No\.?|#)\s*[\dA-Z/-]{1,8}\b|\bStreet\s*(?:No\.?|#)\s*\d+|\bSector\s*[A-Z]-?\d+"),
    "filled_date": re.compile(r"\b\d{1,2}[-./]\d{1,2}[-./](?:19|20)\d{2}\b"),
    "amount": re.compile(r"(?i)\bRs\.?\s*[\d,]{5,}"),
}
_STRONG = ("cnic", "mobile", "landline", "email", "case_number", "relation_name", "address")
_BLANKS = re.compile(r"_{3,}|\.{5,}|\[[^\]]{1,60}\]")
_JUR = {"punjab": r"\bPunjab\b|\bLahore\b|Rawalpindi|Faisalabad|Multan", "sindh": r"\bSindh\b|\bKarachi\b|Hyderabad|Sukkur",
        "kpk": r"Khyber|\bKPK?\b|Peshawar|N\.?W\.?F\.?P", "balochistan": r"Balochistan|Baluchistan|Quetta",
        "islamabad": r"Islamabad"}


def screen(text: str) -> dict:
    counts = {k: len(rx.findall(text)) for k, rx in _PII.items()}
    strong = sum(counts[k] for k in _STRONG)
    return {"pii_counts": counts, "blanks": len(_BLANKS.findall(text)),
            "jurisdiction_mentions": {k: n for k, rx in _JUR.items() if (n := len(re.findall(rx, text)))},
            "strong_signals": strong}


def _risk(collection: str, s: dict) -> str:
    """exclude > manual_review > template_low. Practitioner drafts are never
    'low': automated zero is not proof of no personal data."""
    c = s["pii_counts"]
    if s["strong_signals"] or c["titled_name"] >= 3:
        return "exclude"
    if collection == "drive-drafts" or c["titled_name"] or c["filled_date"] or c["amount"]:
        return "manual_review"
    return "template_low"


def audit(src: Path) -> dict:
    docs = []
    # legaldocs.pk: one document per slug folder; the .docx is the original,
    # .md/.html/.json are derived copies of the same document.
    ld = src / "legaldocs.pk"
    for row in csv.DictReader(open(ld / "documents.csv", encoding="utf-8-sig")):
        folder = ld / row["Path"]
        slug = row["Slug"]
        orig = folder / f"{slug}.docx"
        md = folder / f"{slug}.md"
        text = md.read_text(encoding="utf-8", errors="replace") if md.exists() else ""
        s = screen(text)
        docs.append({"collection": "legaldocs.pk", "category": row["Category"].strip(), "doc_type": row["Title"].strip(),
                     "format": "docx", "has_urdu": row.get("Has Urdu") == "True",
                     "sha256": _sha(orig.read_bytes()) if orig.exists() else None,
                     "text_sha256": _sha(re.sub(r"\s+", " ", text).strip().encode()), **s,
                     "risk": _risk("legaldocs.pk", s), "source": "legaldocs.pk (rebuilt from the site's editor page)"})
    # drive-drafts: the Word file is the original; the .md is its text copy.
    dd = src / "drive-drafts"
    for row in csv.DictReader(open(dd / "files.csv", encoding="utf-8-sig")):
        orig = dd / row["Path"]
        md = dd / row["Markdown"] if row.get("Markdown") else None
        text = ""
        if orig.suffix.lower() == ".docx":
            try:
                text = _docx_text(orig)
            except Exception:
                text = ""
        if not text and md and md.exists():
            text = md.read_text(encoding="utf-8", errors="replace")
        s = screen(text)
        docs.append({"collection": "drive-drafts", "category": row["Category"].strip(), "doc_type": row["Title"].strip(),
                     "format": orig.suffix.lower().lstrip("."), "has_urdu": bool(re.search(r"[؀-ۿ]", text)),
                     "sha256": _sha(orig.read_bytes()) if orig.exists() else None,
                     "text_sha256": _sha(re.sub(r"\s+", " ", text).strip().encode()), **s,
                     "risk": _risk("drive-drafts", s), "source": "public Google Drive folder 'Drafts' (as downloaded)"})
    # duplicates: identical bytes, or identical normalised text
    for key in ("sha256", "text_sha256"):
        groups = collections.defaultdict(list)
        for i, d in enumerate(docs):
            if d[key]:
                groups[d[key]].append(i)
        for ids in groups.values():
            if len(ids) > 1:
                for i in ids:
                    docs[i].setdefault("duplicate_of", [])
                    docs[i]["duplicate_of"] += [docs[j]["sha256"][:12] for j in ids if j != i and docs[j]["sha256"]]
    for d in docs:
        if "duplicate_of" in d:
            d["duplicate_of"] = sorted(set(d["duplicate_of"]))
        # doc_type is a template NAME; it must not itself look like a person
        if _PII["titled_name"].search(d["doc_type"]) or _PII["relation_name"].search(d["doc_type"]):
            d["doc_type"] = "[title withheld]"
    summary = {
        "documents": len(docs),
        "by_collection": dict(collections.Counter(d["collection"] for d in docs)),
        "by_risk": dict(collections.Counter(d["risk"] for d in docs)),
        "by_format": dict(collections.Counter(f"{d['collection']}:{d['format']}" for d in docs)),
        "with_urdu": sum(d["has_urdu"] for d in docs),
        "jurisdiction_docs": dict(collections.Counter(k for d in docs for k in d["jurisdiction_mentions"])),
        "duplicate_docs": sum("duplicate_of" in d for d in docs),
    }
    out = {"generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "note": "Counts, hashes, categories and flags only. No source text, names or numbers. "
                   "A zero count is not proof of no personal data; 'manual_review' and 'exclude' files are "
                   "not used for anything that leaves this machine. Licence: third-party; not redistributed.",
           "summary": summary, "documents": docs}
    V2_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return out


# ── dataset ──────────────────────────────────────────────────────────────────

TRACKS = ("free_drafting", "template_fill")
SPLITS = ("dev", "holdout")
CASE_FIELDS = ("id", "split", "track", "lang", "category", "province", "case_type", "mode", "document", "instruction",
               "inspired_by", "required", "allow", "forbid", "citation", "expect", "label_status", "synthetic")


def load_cases(split: str = "all", track: str = "all") -> list[dict]:
    out = []
    for line in CASES.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("//"):
            c = json.loads(line)
            if split in ("all", c["split"]) and track in ("all", c["track"]):
                out.append(c)
    return out


def case_lines() -> dict[str, str]:
    return {json.loads(l)["id"]: l for l in CASES.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.lstrip().startswith("//")}


def label_status(case: dict, sources: dict) -> str:
    labels = [l for l in case.get("allow", []) + case.get("forbid", [])
              if "cite" in l and l.get("kind", "section") == "section"]
    if not labels:
        return "no_authority_labels"
    ok = all(sources.get(l["source"], {}).get("url") and l["cite"] in sources[l["source"]].get("checked_sections", {})
             and not l.get("review") for l in labels)
    return "definitive" if ok else "provisional"


def validate(src: Path | None = None) -> list[str]:
    """Problems with the dataset; [] = valid. Local only."""
    problems = []
    cases = load_cases()
    sources = json.loads(SOURCES.read_text(encoding="utf-8"))["sources"]
    ids = [c["id"] for c in cases]
    if len(ids) != len(set(ids)):
        problems.append("duplicate case ids")
    for c in cases:
        miss = [f for f in CASE_FIELDS if f not in c]
        if miss:
            problems.append(f"{c.get('id')}: missing {miss}")
            continue
        if c["track"] not in TRACKS or c["split"] not in SPLITS:
            problems.append(f"{c['id']}: bad track/split")
        if c["synthetic"] is not True:
            problems.append(f"{c['id']}: not marked synthetic")
        for l in c["allow"] + c["forbid"]:
            if "cite" in l and l.get("source") not in sources:
                problems.append(f"{c['id']}: label source {l.get('source')} not in legal_sources.json")
        if label_status(c, sources) != c["label_status"]:
            problems.append(f"{c['id']}: label_status {c['label_status']} != computed {label_status(c, sources)}")
        if c["track"] == "template_fill" and not c.get("facts"):
            problems.append(f"{c['id']}: template_fill case without facts")
        if c["expect"] == "clarify_or_placeholder" and c["province"] != "unknown":
            problems.append(f"{c['id']}: clarification expected but a province is set")
    for t in TRACKS:
        if not any(c["track"] == t and c["split"] == "holdout" for c in cases):
            problems.append(f"no holdout case in track {t}")
    lock = json.loads(HOLDOUT_LOCK.read_text(encoding="utf-8"))["cases"]
    lines = case_lines()
    for cid, h in lock.items():
        if cid not in lines:
            problems.append(f"holdout {cid} missing from cases")
        elif _sha(lines[cid].encode("utf-8")) != h:
            problems.append(f"holdout {cid} changed after it was locked")
    for c in cases:
        if c["split"] == "holdout" and c["id"] not in lock:
            problems.append(f"{c['id']}: holdout case not in the lock")
    problems += privacy_problems()
    if src is not None and src.exists():
        problems += copied_wording(src, cases)
    return problems


def privacy_problems() -> list[str]:
    """The repo artefacts themselves must carry no personal-data shapes and
    no source text. Run over every V2 file that is committed-to-be."""
    out = []
    audit_doc = json.loads(AUDIT.read_text(encoding="utf-8")) if AUDIT.exists() else {"documents": []}
    allowed_keys = {"collection", "category", "doc_type", "format", "has_urdu", "sha256", "text_sha256", "pii_counts",
                    "blanks", "jurisdiction_mentions", "strong_signals", "risk", "source", "duplicate_of"}
    for d in audit_doc["documents"]:
        extra = set(d) - allowed_keys
        if extra:
            out.append(f"audit record carries unexpected fields {sorted(extra)}")
            break
    for f in (CASES, AUDIT, SOURCES, HOLDOUT_LOCK):
        if not f.exists():
            continue
        text = f.read_text(encoding="utf-8")
        for name in ("cnic", "mobile", "email", "case_number", "relation_name", "address"):
            if _PII[name].search(text):
                out.append(f"{f.name}: contains a {name}-shaped string")
    return out


def _shingles(text: str, n: int = 8) -> set:
    w = re.findall(r"[\w؀-ۿ]+", (text or "").lower())
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}


def copied_wording(src: Path, cases: list[dict]) -> list[str]:
    """No 8-word run of any source document may appear in a case (computed
    locally, in memory; nothing is stored)."""
    src_sh = set()
    for md in list((src / "legaldocs.pk").rglob("*.md")) + list((src / "drive-drafts").rglob("*.md")):
        src_sh |= _shingles(md.read_text(encoding="utf-8", errors="replace"))
    out = []
    for c in cases:
        hits = _shingles(" ".join([c["instruction"], c["document"], c.get("selection", "")])) & src_sh
        if hits:
            out.append(f"{c['id']}: {len(hits)} 8-word run(s) shared with the source collection")
    return out

# ── matching ─────────────────────────────────────────────────────────────────

_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XXI": 21,
          "XXIII": 23, "XXXIX": 39, "XLI": 41, "XLVII": 47}


def cite_pattern(label: dict) -> re.Pattern:
    import eval_drafter as E
    if label["act"] == "CPC-order":
        order = label["cite"]
        alts = [order] + ([str(_ROMAN[order])] if order in _ROMAN else [])
        o = "(?:" + "|".join(alts) + ")"
        rule = label.get("rule")
        r = rf"\s*,?\s*(?:Rule|R\.?|r\.?)\s*{rule}(?!\d)" if rule else ""
        return re.compile(rf"(?:Order|O\.)\s*{o}(?![IVXL\d]){r}", re.I)
    return E.cite_re(label["cite"], label["act"])


_ORDER_RULE = re.compile(r"(?i)(?:Order|O\.)\s*[IVXL\d]+\s*,?\s*(?:Rule|R\.?|r\.?)\s*\d+[A-Z]?")


def _sent_hit(label: dict, sentence: str) -> bool:
    # "Order VII Rule 11 CPC" is not "Section 11 CPC": a plain CPC section is
    # matched only after Order/Rule references are taken out of the sentence.
    probe = _ORDER_RULE.sub(" ", sentence) if label.get("act") == "CPC" else sentence
    if "cite" in label and not cite_pattern(label).search(probe):
        return False
    if "text" in label and not re.search(label["text"], sentence):
        return False
    if label.get("sentence_has") and not any(re.search(p, sentence) for p in label["sentence_has"]):
        return False
    if label.get("sentence_lacks") and any(re.search(p, sentence) for p in label["sentence_lacks"]):
        return False
    return True


def hits(labels: list[dict], text: str) -> list[dict]:
    import eval_drafter as E
    sents = E.sentences(text)
    return [l for l in labels if any(_sent_hit(l, s) for s in sents)]


def _name(l: dict) -> str:
    if "cite" in l:
        return f"{'Order ' + l['cite'] + (' r.' + l['rule'] if l.get('rule') else '') if l['act'] == 'CPC-order' else 's.' + l['cite'] + ' ' + l['act']}"
    return l.get("why", l.get("text", "?"))


_PLACEHOLDER = re.compile(r"(?i)\[[^\]]{0,80}(?:law|act|jurisdiction|province|provincial|statute|ordinance|section)[^\]]{0,80}\]"
                          r"|depends on the province|choose (?:a )?jurisdiction")
_BLANK = re.compile(r"\[[^\]]{1,60}\]|_{3,}|\.{5,}")


def assess(case: dict, row: dict) -> dict:
    """Scores the FINAL VISIBLE proposal (guard text), never the raw output."""
    import eval_drafter as E
    guard = row.get("guard") or {}
    final = guard.get("text", "") if guard.get("ran") else ""
    m = {"completed": bool(row.get("done")) and not row.get("error"), "guard_ran": bool(guard.get("ran")),
         "empty": not final.strip(), "latency_s": row.get("latency_s")}
    forbid = case.get("forbid", [])
    fh = hits(forbid, final)
    m["wrong_provision"] = [_name(l) for l in fh if l.get("kind", "section") == "section" and "cite" in l]
    m["jurisdiction_errors"] = [_name(l) for l in fh if l.get("kind") == "jurisdiction"]
    m["foreign_law"] = [_name(l) for l in fh if l.get("kind") == "foreign_law"]
    # Input-fact fidelity (2026-10-15): a fact the request does not give, stated
    # as true in the final text (v2_r3 V09: "the accused, though not insane, is
    # unable to understand the proceedings"). Reported on its own, never mixed
    # with citation errors.
    m["invented_facts"] = [_name(l) for l in fh if l.get("kind") == "invented_fact"]
    m["forbidden_text"] = [_name(l) for l in fh if "text" in l and l.get("kind") != "invented_fact"]
    allowed = hits(case.get("allow", []), final)
    m["allowed_cited"] = [_name(l) for l in allowed]
    m["missing_required"] = [r["what"] for r in case.get("required", []) if not any(re.search(p, final) for p in r["any"])]
    m["missing_citation"] = (case["citation"] == "must_cite_allowed" and bool(final.strip()) and not allowed)
    # cited provisions the case neither allows nor forbids -- for review
    from app.ai import tool_contract
    unlisted = []
    for sent in E.sentences(final):
        for ref in tool_contract.provision_refs(sent):
            if not any(_sent_hit(l, sent) for l in case.get("allow", []) + forbid):
                lbl = f"s.{ref.section} {ref.statute}"
                if lbl not in unlisted:
                    unlisted.append(lbl)
    m["unsupported_authorities"] = unlisted
    if case["expect"] == "clarify_or_placeholder":
        m["placeholder_or_clarification"] = bool(_PLACEHOLDER.search(final) or guard.get("clarify"))
    wrongly = []
    for w in guard.get("withheld", []) or []:
        t = w.get("text", "")
        if hits(case.get("allow", []), t) and not hits(forbid, t):
            wrongly.append(t[:120])
    m["wrongly_withheld"] = wrongly
    m["checker_disagreement"] = E.assess({"support": [], "forbid": [], "required": [], "province": case["province"]},
                                         row)["checker_disagreement"]
    if case["track"] == "template_fill":
        m["facts_placed"] = sum(f in final for f in case.get("facts", [])) / max(len(case.get("facts", [])), 1)
        m["blanks_kept"] = bool(_BLANK.search(final))
        m["citations_added"] = len(tool_contract.provision_refs(final))
    return m


FAIL_KEYS = ("wrong_provision", "jurisdiction_errors", "foreign_law", "forbidden_text", "invented_facts", "missing_required",
             "unsupported_authorities", "wrongly_withheld", "checker_disagreement")


def failed(m: dict) -> list[str]:
    out = [k for k in FAIL_KEYS if m.get(k)]
    if m.get("empty"):
        out.append("empty")
    if m.get("missing_citation"):
        out.append("missing_citation")
    if m.get("placeholder_or_clarification") is False:
        out.append("no_placeholder")
    if m.get("facts_placed") is not None and m["facts_placed"] < 1:
        out.append("facts_missing")
    if m.get("blanks_kept") is False:
        out.append("blanks_filled_in")
    return out


def summarise(rows: list[dict], scorer: str = "v1") -> dict:
    """Per TRACK (never combined), then per split and label_status. Variance
    = cases whose failure set differs between repeats."""
    cases = {c["id"]: c for c in load_cases()}
    out = {}
    for track in TRACKS:
        tr = [r for r in rows if cases[r["id"]]["track"] == track]
        if not tr:
            continue
        groups = collections.defaultdict(list)
        per_case = collections.defaultdict(list)
        for r in tr:
            c = cases[r["id"]]
            m = assess_v2(c, r) if scorer == "v2" else assess(c, r)
            f = failed_v2(m) if scorer == "v2" else failed(m)
            per_case[r["id"]].append(tuple(sorted(f)))
            for g in ("ALL", f"split:{c['split']}", f"labels:{c['label_status']}", f"category:{c['category']}"):
                groups[g].append((m, f))
        block = {}
        for g, items in sorted(groups.items()):
            n = len(items)
            counts = collections.Counter(k for _, f in items for k in f)
            lat = [m["latency_s"] for m, _ in items if m["latency_s"] is not None]
            block[g] = {"rows": n, "clean_rows": sum(not f for _, f in items), **dict(counts),
                        "latency_s_median": sorted(lat)[len(lat) // 2] if lat else None}
        block["variance_cases"] = sorted(cid for cid, fs in per_case.items() if len(set(fs)) > 1)
        out[track] = block
    return out

# ── what a model run would transmit ─────────────────────────────────────────

def transmit_preview() -> dict:
    """EXACTLY the request bodies a run sends to the drafter route. The route
    adds its own system prompt (instructions + statute text retrieved from
    the local corpus) before calling the external model; no case contains any
    source-collection text (copied_wording checks that)."""
    items = []
    for c in load_cases():
        body = {k: c[k] for k in ("instruction", "document", "case_type", "province", "mode")}
        body["template"] = c["category"].replace("_", " ")
        if c.get("selection"):
            body["selection"] = c["selection"]
        items.append({"id": c["id"], "split": c["split"], "track": c["track"], "request": body})
    return {"route": "POST /api/v1/ai/draft/stream (in-process handler)", "model_purpose": "draft_stream (groq5)",
            "also_sent_by_the_route": ["system prompt: drafting instructions + mode/jurisdiction riders",
                                       "statute text retrieved from the LOCAL corpus for the request",
                                       "exact text of any provision the instruction names (local corpus)"],
            "never_sent": ["any file from the source collection", "audit records", "labels/checklists"],
            "requests": items}


# ── scorer v2 (2026-10-15) ───────────────────────────────────────────────────
# Fixes two scorer-v1 bugs found in results/v2_r1, WITHOUT changing labels,
# cases or v1 (v1 stays reproducible: `score --scorer v1`):
#   1. Unicode hyphens / Urdu digits: "561‑A" (U+2011) did not match "561-A",
#      so a correct citation scored as missing.
#   2. Template fill: v1 failed a row as "blanks_filled_in" when the model
#      REMOVED the [BLANK] marker and left the field empty -- nothing invented.
#      v2 separates blank_kept / blank_emptied (a fidelity note) from
#      fact_invented (a failure).
SCORER_VERSION = "v2"
_HYPHENS = re.compile(r"[‐-―−﹘﹣－]")
_SPACES = re.compile(r"[    ]")
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalise_text(text: str) -> str:
    return _SPACES.sub(" ", _HYPHENS.sub("-", (text or "").translate(_DIGITS)))


def _normalised_row(row: dict) -> dict:
    r = json.loads(json.dumps(row))
    if r.get("guard") and r["guard"].get("text"):
        r["guard"]["text"] = normalise_text(r["guard"]["text"])
    for w in (r.get("guard") or {}).get("withheld", []) or []:
        w["text"] = normalise_text(w.get("text", ""))
    r["raw"] = normalise_text(r.get("raw", ""))
    return r


def _field_states(case: dict, final: str) -> dict:
    """For each fact the request did NOT give: "kept" (marker still there),
    "emptied" (marker removed, nothing put in its place), "filled" (something
    put there = invented) or "unlocated". Located between the skeleton's own
    text before and after the [LABEL] marker."""
    out = {}
    for label in case.get("missing", []):
        m = re.search(r"([^\n\[\]]{0,40})\[" + re.escape(label) + r"\]([^\n\[]{0,20})", case["document"])
        prefix, suffix = (m.group(1).strip(), m.group(2).strip()) if m else ("", "")
        anchor = prefix[-14:]
        hit = re.search(re.escape(anchor) + r"([^\n]{0,80})", final) if anchor else None
        if not hit:
            out[label] = "unlocated"
            continue
        after = hit.group(1)
        if suffix:
            cut = after.find(suffix[:6])
            if cut >= 0:
                after = after[:cut]
        after = after.strip(" :,.-\u2013\u060c\u06d4")
        if not after:
            out[label] = "emptied"
        elif re.fullmatch(r"(?:\[[^\]]*\]|_{2,}|\.{3,}|\s)+", after):     # one or several blank markers
            out[label] = "kept"
        else:
            out[label] = "filled"
    return out


def assess_v2(case: dict, row: dict) -> dict:
    m = assess(case, _normalised_row(row))
    m["scorer"] = SCORER_VERSION
    if case["track"] == "template_fill":
        final = normalise_text((row.get("guard") or {}).get("text", "")) if (row.get("guard") or {}).get("ran") else ""
        states = _field_states(case, final)
        m["field_states"] = states
        m["fact_invented"] = [k for k, v in states.items() if v == "filled"]
        m["blank_emptied"] = [k for k, v in states.items() if v == "emptied"]
        m.pop("blanks_kept", None)
    return m


def failed_v2(m: dict) -> list[str]:
    out = [k for k in failed(m) if k != "blanks_filled_in"]
    if m.get("fact_invented"):
        out.append("fact_invented")
    return out


# ── payload capture + privacy check (pilot) ─────────────────────────────────

def _install_capture(store: list) -> None:
    """Wrap the model client so the EXACT messages sent to the provider are
    recorded (in memory / local file only), then passed through unchanged."""
    import app.ai.llm as llm_mod
    original = llm_mod.get_llm

    def capturing(*a, **kw):
        inner = original(*a, **kw)

        class _Capture:
            async def astream(self, messages):
                store.append([{"role": m.get("role"), "content": m.get("content")} if isinstance(m, dict)
                              else {"role": getattr(m, "type", "?"), "content": getattr(m, "content", "")} for m in messages])
                async for chunk in inner.astream(messages):
                    yield chunk
        return _Capture()
    llm_mod.get_llm = capturing


def payload_check(payloads: list, src: Path) -> dict:
    """Every captured payload against the source collection (8-word runs) and
    the personal-data detectors. Returns counts and locations only."""
    src_sh = set()
    if src.exists():
        for md in list((src / "legaldocs.pk").rglob("*.md")) + list((src / "drive-drafts").rglob("*.md")):
            src_sh |= _shingles(md.read_text(encoding="utf-8", errors="replace"))
    report = []
    for i, msgs in enumerate(payloads):
        parts = {}
        for j, m in enumerate(msgs):
            text = m["content"] if isinstance(m["content"], str) else json.dumps(m["content"])
            shared = len(_shingles(text) & src_sh)
            pii = {k: len(_PII[k].findall(text)) for k in ("cnic", "mobile", "email", "case_number", "relation_name", "address")}
            parts[f"{j}:{m['role']}"] = {"chars": len(text), "source_8word_runs": shared,
                                         "pii": {k: v for k, v in pii.items() if v},
                                         "statute_blocks": len(re.findall(r"\[(?:STATUTE|EXACT TEXT)\]", text))}
        report.append(parts)
    leaks = sum(p["source_8word_runs"] for r in report for p in r.values())
    pii = sum(sum(p["pii"].values()) for r in report for p in r.values())
    return {"payloads": len(payloads), "source_8word_runs_total": leaks, "pii_matches_total": pii, "per_payload": report}

# ── failure report (written BEFORE any full run; formatting only) ───────────

def failure_report(rows: list[dict], scorer: str = "v1") -> dict:
    """Per failing row: final visible proposal, cited authorities, checker
    decisions (guard + citation checker), latency, failure categories.
    Legal-correctness counts use DEFINITIVE-label cases only; provisional
    cases are listed as observations, never scored as correctness."""
    import eval_drafter as E
    cases = {c["id"]: c for c in load_cases()}
    out = {"definitive": [], "provisional_observations": [], "other": []}
    correctness = {"definitive_rows": 0, "definitive_rows_with_legal_error": 0}
    for r in rows:
        c = cases[r["id"]]
        m = assess_v2(c, r) if scorer == "v2" else assess(c, r)
        f = failed_v2(m) if scorer == "v2" else failed(m)
        guard = r.get("guard") or {}
        if c["label_status"] == "definitive":
            correctness["definitive_rows"] += 1
            legal = [k for k in ("wrong_provision", "jurisdiction_errors", "foreign_law", "missing_citation") if k in f]
            correctness["definitive_rows_with_legal_error"] += bool(legal)
        if not f:
            continue
        item = {"id": r["id"], "rep": r["rep"], "track": c["track"], "split": c["split"], "categories": f,
                "final_visible_proposal": (guard.get("text") or "")[:900],
                "cited_authorities": sorted(set(m["allowed_cited"] + m["wrong_provision"] + m["unsupported_authorities"]
                                                + m["jurisdiction_errors"] + m["foreign_law"])),
                "guard_decision": {"ran": guard.get("ran"), "reason": guard.get("reason"), "supported": guard.get("supported"),
                                   "not_checked": guard.get("not_checked"),
                                   "withheld": [{"text": w.get("text", "")[:200], "reasons": w.get("reasons")}
                                                for w in guard.get("withheld", []) or []],
                                   "clarify": guard.get("clarify")},
                "citation_checker": [{"canonical": x.get("canonical"), "status": x.get("status")}
                                     for x in (r.get("verification") or {}).get("checks", []) or []],
                "latency_s": r.get("latency_s"), "error": r.get("error"),
                "detail": {k: m[k] for k in ("wrong_provision", "jurisdiction_errors", "foreign_law", "forbidden_text",
                                             "missing_required", "unsupported_authorities", "wrongly_withheld",
                                             "checker_disagreement", "fact_invented", "blank_emptied", "field_states") if m.get(k)}}
        bucket = "definitive" if c["label_status"] == "definitive" else \
            "provisional_observations" if c["label_status"] == "provisional" else "other"
        out[bucket].append(item)
    return {"scorer": scorer, "legal_correctness_definitive_only": correctness, **out}


async def _run(label: str, repeat: int, split: str, pause: float, ids: list | None = None,
               capture: list | None = None) -> Path:
    import asyncio
    import eval_chat_length as EC
    import eval_drafter as E
    EC._apply_overlay()
    from app.db.chroma import connect_chroma
    connect_chroma()
    from app.api.v1.routes import ai as routes

    async def _none(**kw):
        return None

    async def _no_case_law(q):
        return ""
    routes.provenance_service.record_answer = _none
    routes._retrieve_case_law_context = _no_case_law
    if capture is not None:
        _install_capture(capture)
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"{label}.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for rep in range(1, repeat + 1):
            for item in transmit_preview()["requests"]:
                if split not in ("all", item["split"]) or (ids and item["id"] not in ids):
                    continue
                c = next(x for x in load_cases() if x["id"] == item["id"])
                row = await E._one(routes, {**item["request"], "province": c["province"]}, item["request"]["document"])
                rec = {"id": c["id"], "rep": rep, **row}
                rec["raw"] = rec["raw"][:3000]
                fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
                fh.flush()
                print(label, rep, c["id"], rec["latency_s"], failed(assess(c, rec)), flush=True)
                await asyncio.sleep(pause)
    return out


def replay(src_label: str, label: str) -> Path:
    """The CURRENT guard over SAVED model outputs (no model call): what the
    guard alone changes. Retrieval and prompt changes are not reflected --
    those need a fresh run. Statute citation checks only (the case-law check
    reads the hosted store)."""
    import eval_chat_length as EC
    EC._apply_overlay()
    from app.db.chroma import connect_chroma
    connect_chroma()
    from app.ai import draft_guard, draft_jurisdiction, jurisdiction
    from app.ai.citation_verification import verify_statutes
    cases = {c["id"]: c for c in load_cases()}
    rows = [json.loads(x) for x in (RESULTS / f"{src_label}.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    out = RESULTS / f"{label}.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for r in rows:
            c = cases[r["id"]]
            template = c["category"].replace("_", " ")
            prov, _basis = draft_jurisdiction.resolve(False, jurisdiction.normalise(c["province"]))
            topic = draft_jurisdiction.topic_for(f"{template} {c['instruction']} {c.get('selection', '')}")
            g = draft_guard.check(r["raw"], f"{c['instruction']} {c.get('selection', '')}", [], prov, topic,
                                  context=f"{template} {c['document']}")
            v = {"checks": [x.to_dict() for x in verify_statutes(g["text"])]} if g["text"].strip() else None
            fh.write(json.dumps({**r, "guard": g, "verification": v, "replay_of": src_label}, ensure_ascii=False,
                                default=str) + "\n")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("audit"); a.add_argument("--src", type=Path, default=DEFAULT_SRC)
    v = sub.add_parser("validate"); v.add_argument("--src", type=Path, default=DEFAULT_SRC)
    sub.add_parser("transmit-preview")
    r = sub.add_parser("run"); r.add_argument("--label", required=True); r.add_argument("--repeat", type=int, default=2)
    r.add_argument("--split", default="all"); r.add_argument("--pause", type=float, default=1.5)
    r.add_argument("--approved", action="store_true", help="the user approved sending transmit-preview's requests")
    r.add_argument("--ids", default="", help="comma-separated case ids (pilot)")
    r.add_argument("--capture", action="store_true", help="record the exact model payloads and check them")
    r.add_argument("--src", type=Path, default=DEFAULT_SRC)
    fr = sub.add_parser("failures"); fr.add_argument("path", type=Path); fr.add_argument("--scorer", choices=("v1", "v2"), default="v1")
    rp = sub.add_parser("replay"); rp.add_argument("--from", dest="src_label", required=True); rp.add_argument("--label", required=True)
    s = sub.add_parser("score"); s.add_argument("path", type=Path); s.add_argument("--scorer", choices=("v1", "v2"), default="v1")
    args = ap.parse_args()
    if args.cmd == "audit":
        print(json.dumps(audit(args.src)["summary"], indent=1, ensure_ascii=False))
    elif args.cmd == "validate":
        probs = validate(args.src)
        print("\n".join(probs) if probs else "valid")
        return 1 if probs else 0
    elif args.cmd == "transmit-preview":
        prev = transmit_preview()
        (V2_DIR / "transmit_preview.json").write_text(json.dumps(prev, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"{len(prev['requests'])} requests -> {V2_DIR / 'transmit_preview.json'}")
    elif args.cmd == "run":
        if not args.approved:
            print("Refusing: a real-model run needs --approved, given only after the user approves transmit-preview.")
            return 2
        import asyncio
        ids = [x.strip() for x in args.ids.split(",") if x.strip()] or None
        cap = [] if args.capture else None
        out = asyncio.run(_run(args.label, args.repeat, args.split, args.pause, ids, cap))
        print("wrote", out)
        if cap is not None:
            chk = payload_check(cap, args.src)
            (RESULTS / f"{args.label}.payload_check.json").write_text(json.dumps(chk, indent=1, ensure_ascii=False), encoding="utf-8")
            (RESULTS / f"{args.label}.payloads.json").write_text(json.dumps(cap, indent=1, ensure_ascii=False), encoding="utf-8")
            print(json.dumps({k: v for k, v in chk.items() if k != "per_payload"}))
    elif args.cmd == "replay":
        print("wrote", replay(args.src_label, args.label))
    elif args.cmd == "failures":
        rows = [json.loads(x) for x in args.path.read_text(encoding="utf-8").splitlines() if x.strip()]
        rep = failure_report(rows, scorer=args.scorer)
        (args.path.with_suffix(f".failures{'' if args.scorer == 'v1' else '.scorer_v2'}.json")).write_text(json.dumps(rep, indent=1, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(rep["legal_correctness_definitive_only"]), {k: len(v) for k, v in rep.items() if isinstance(v, list)})
    else:
        rows = [json.loads(x) for x in args.path.read_text(encoding="utf-8").splitlines() if x.strip()]
        print(json.dumps(summarise(rows, scorer=args.scorer), indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
