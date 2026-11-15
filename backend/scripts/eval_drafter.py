"""Lawyer drafter eval: the REAL `/ai/draft/stream` handler on a labelled set.

    python scripts/eval_drafter.py inventory [--src DIR]
    python scripts/eval_drafter.py run   --label base_r1 --repeat 2 [--split dev|holdout|all] [--src DIR]
    python scripts/eval_drafter.py score evals/drafter/results/base_r1.jsonl [evals/drafter/results/after_r1.jsonl]

What is real: `ai_draft_stream` (request model, jurisdiction resolution,
statute retrieval over the embedded Chroma corpus, exact-provision grounding,
the live `draft_stream` model, the legal-authority guard, the citation check).

What is replaced, and why:
  * provenance.record_answer -> a no-op, so a run writes no audit records;
  * case-law retrieval (citator) -> "" : it reads the hosted citator store,
    and this eval measures statute authorities only;
  * settings -> the local overlay (.env.analyzer-demo.local), as every eval.

Documents: each case names a template exported from aiattorney.com.pk
(`source_docx`). Its text is read from --src at run time and its sha256 is
checked against evals/drafter/provenance.json; the template text itself is not
copied into the repo or the results. Results hold the synthetic request, the
model's output (synthetic facts only) and the scores.

Scores are CHECKLIST matches (regexes over the final visible proposal), not a
judgment that the draft is legally correct. See cases_v1.jsonl's header.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import json
import re
import sys
import time
import zipfile
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "scripts"))
for _s in (sys.stdout, sys.stderr):
    _s.reconfigure(encoding="utf-8", errors="replace")

EVAL_DIR = BACKEND_DIR / "evals" / "drafter"
CASES = EVAL_DIR / "cases_v1.jsonl"
PROVENANCE = EVAL_DIR / "provenance.json"
RESULTS = EVAL_DIR / "results"
DEFAULT_SRC = Path.home() / "Downloads"
_EXPORT = re.compile(r"^(?P<name>.+?)_(?P<ts>\d{4}-\d{2}-\d{2}T[\d-]+Z)\.docx$")
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# ── documents ────────────────────────────────────────────────────────────────

def docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml")
    # Third-party files: a DOCX part never needs a DTD, so one that declares a
    # DOCTYPE or ENTITY is refused before parsing (no entity expansion / XXE).
    if re.search(rb"<!(?:DOCTYPE|ENTITY)", xml, re.I):
        raise ValueError(f"{path.name}: document.xml declares a DTD; refusing to parse")
    root = ET.fromstring(xml)
    paras = []
    for p in root.iter(_W + "p"):
        paras.append("".join(t.text or "" for t in p.iter(_W + "t")))
    return "\n".join(x for x in paras if x.strip())


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _exports(src: Path) -> dict[str, Path]:
    out = {}
    for p in sorted(src.glob("*.docx")):
        m = _EXPORT.match(p.name)
        if m:
            out[m.group("name")] = p
    return out


# PII detectors: COUNTS only are ever printed or stored, never the values.
_PII = {
    "cnic": re.compile(r"\b\d{5}-\d{7}-\d\b"),
    "phone": re.compile(r"(?:\+92|\b0)3\d{2}[-\s]?\d{7}\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"),
    "fir_number": re.compile(r"(?i)FIR\s*No\.?\s*\d+"),
}
_PROVINCES = {"punjab": r"\bPunjab\b", "sindh": r"\bSindh\b", "kpk": r"Khyber|\bKPK?\b|NWFP",
              "balochistan": r"Baloch|Baluch", "islamabad": r"Islamabad"}


def inventory(src: Path) -> dict:
    rows = []
    for name, path in _exports(src).items():
        data = path.read_bytes()
        text = docx_text(path)
        rows.append({
            "file": path.name, "folder": str(path.parent), "format": "docx (Office Open XML)",
            "bytes": len(data), "sha256": _sha(data),
            "doc_type": name, "words": len(text.split()),
            "placeholders": len(re.findall(r"\[[^\]]{1,60}\]", text)),
            "jurisdiction_mentions": {k: len(re.findall(v, text)) for k, v in _PROVINCES.items() if re.search(v, text)},
            "pii_counts": {k: len(rx.findall(text)) for k, rx in _PII.items()},
            "origin": "exported from the aiattorney.com.pk drafter on 2026-10-14 (third-party template; "
                      "user-authorised copy for this project). Not a client draft.",
            "copyright": "third-party (aiattorney.com.pk)",
        })
    doc = {"generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "source_folder": str(src), "files": rows,
           "note": "Template text is not copied into the repo; cases reference files by doc_type and sha256."}
    PROVENANCE.parent.mkdir(parents=True, exist_ok=True)
    PROVENANCE.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    return doc


def load_cases(split: str = "all") -> list[dict]:
    out = []
    for line in CASES.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("//"):
            c = json.loads(line)
            if split in ("all", c["split"]):
                out.append(c)
    return out


def _documents(src: Path) -> dict[str, str]:
    prov = {r["doc_type"]: r for r in json.loads(PROVENANCE.read_text(encoding="utf-8"))["files"]}
    out = {}
    for name, path in _exports(src).items():
        if name in prov and _sha(path.read_bytes()) != prov[name]["sha256"]:
            raise SystemExit(f"{path.name} changed since the provenance manifest was written")
        out[name] = docx_text(path)
    return out

# ── checklist matching ───────────────────────────────────────────────────────

ACTS = {
    "CrPC": r"(?:Cr\.?\s?P\.?\s?C\.?|Code\s+of\s+Criminal\s+Procedure|Criminal\s+Procedure\s+Code)",
    "PPC": r"(?:P\.?\s?P\.?\s?C\.?|Pakistan\s+Penal\s+Code)",
    "CPC": r"(?:(?<![A-Za-z])C\.?\s?P\.?\s?C\.?(?![A-Za-z])|Code\s+of\s+Civil\s+Procedure|Civil\s+Procedure\s+Code)",
    "GWA": r"Guardians?\s+(?:and|&)\s+Wards?\s+Act", "FCA": r"Family\s+Courts?\s+Act",
    "DMMA": r"Dissolution\s+of\s+Muslim\s+Marriages?\s+Act", "MFLO": r"(?:Muslim\s+Family\s+Laws?\s+Ordinance|MFLO)",
    "TPA": r"Transfer\s+of\s+Property\s+Act", "PRPA": r"Punjab\s+Rented\s+Premises\s+Act",
    "SRPO": r"Sindh\s+Rented\s+Premises\s+Ordinance", "RA": r"Registration\s+Act", "CA": r"Contract\s+Act",
    "SRA": r"Specific\s+Relief\s+Act", "LA": r"Limitation\s+Act", "NIA": r"Negotiable\s+Instruments?\s+Act",
    "Constitution": r"Constitution", "PPA": r"Punjab\s+Pre-?\s?emption\s+Act",
}
_MARK = r"(?<![A-Za-z])(?:Sections?|Secs?\.?|S\.|s\.|u/s\.?|Articles?|Art\.)"
_NOT_ACT = r"(?:(?!\bAct\b|\bCode\b|\bOrdinance\b)[^.\n])"


def cite_re(sec: str, act: str) -> re.Pattern:
    if act == "CPC-order":
        return re.compile(rf"Order\s+(?:{sec})(?![\dA-Z])", re.I)
    a = ACTS[act]
    s = rf"(?:{sec})(?![\d])(?:\s*\(\s*\w+\s*\))*"
    lst = r"(?:[\dA-Z\-]+(?:\(\w+\))*\s*(?:,|and|&|/|or)\s*)*"
    return re.compile(rf"{_MARK}\s*{lst}{s}{_NOT_ACT}{{0,80}}?{a}"
                      rf"|{a}[^.\n]{{0,40}}?{_MARK}\s*{s}"
                      rf"|(?<![\d]){s}\s*,?\s*(?:of\s+(?:the\s+)?)?{a}", re.I)


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z\[(])|\n+", text or "") if s.strip()]


def _hit(spec: dict, sentence: str) -> bool:
    if "cite" in spec and not cite_re(spec["cite"], spec["act"]).search(sentence):
        return False
    if "text" in spec and not re.search(spec["text"], sentence):
        return False
    if spec.get("sentence_has") and not any(re.search(p, sentence) for p in spec["sentence_has"]):
        return False
    if spec.get("sentence_lacks") and any(re.search(p, sentence) for p in spec["sentence_lacks"]):
        return False
    return True


def _hits(specs: list[dict], text: str) -> list[str]:
    out = []
    for spec in specs:
        if any(_hit(spec, s) for s in sentences(text)):
            out.append(f"{spec.get('cite', '')} {spec.get('act', '')}".strip() or spec.get("text", ""))
    return out


_PROV_ACT = re.compile(r"\b(Punjab|Sindh|Khyber\s+Pakhtunkhwa|KPK|Balochistan|Baluchistan|Islamabad)\b"
                       r"(?:\s+[A-Z][\w'()-]*){0,6}?\s+(Act|Ordinance|Rules)\b")
_PROV_KEY = {"punjab": "punjab", "sindh": "sindh", "khyber pakhtunkhwa": "kpk", "kpk": "kpk",
             "balochistan": "balochistan", "baluchistan": "balochistan", "islamabad": "federal"}
_PLACEHOLDER = re.compile(r"(?i)\[[^\]]{0,80}(?:law|act|jurisdiction|province|provincial|statute|section|ordinance)"
                          r"[^\]]{0,80}\]|depends on the province|confirm (?:the )?jurisdiction")


def _cite_key(section: str, statute: str) -> tuple[str, str]:
    from app.ai.answer_citations import normalise_statute
    return (re.sub(r"[^0-9A-Z]", "", str(section).upper()), normalise_statute(statute or ""))


def assess(case: dict, row: dict) -> dict:
    guard = row.get("guard") or {}
    final = guard.get("text", "") if guard.get("ran") else ""
    raw = row.get("raw", "")
    m = {}
    m["guard_ran"] = bool(guard.get("ran"))
    m["completed"] = bool(row.get("done")) and not row.get("error")
    m["empty_final"] = not final.strip()
    m["unsupported_final"] = _hits(case.get("forbid", []), final)
    m["unsupported_raw"] = _hits(case.get("forbid", []), raw)
    m["supported_final"] = _hits(case.get("support", []), final)
    m["missing_required"] = [r["what"] for r in case.get("required", [])
                             if not any(re.search(p, final) for p in r["any"])]
    wrongly = []
    for w in guard.get("withheld", []) or []:
        t = w.get("text", "")
        if _hits(case.get("support", []), t) and not _hits(case.get("forbid", []), t):
            wrongly.append({"text": t[:160], "reasons": w.get("reasons", [])})
    m["wrongly_withheld"] = wrongly
    prov = (case.get("province") or "unknown").lower()
    jur = []
    for mm in _PROV_ACT.finditer(final):
        key = _PROV_KEY.get(re.sub(r"\s+", " ", mm.group(1)).lower())
        if key != prov or prov in ("unknown", "federal"):
            jur.append(f"names {mm.group(0)} in a {prov} draft")
    if case.get("expect_placeholder") and final.strip() and not _PLACEHOLDER.search(final):
        jur.append("no placeholder/clarification where provincial law governs")
    m["jurisdiction_mistakes"] = jur
    # The two checkers on the same citations still in the final text: the
    # verifier's per-citation status against what the guard counted. A
    # disagreement = the guard counted it as supported (new rows: in
    # `supported`; old rows: not in `unverified`) while the verifier could not
    # verify it, or the reverse.
    v = row.get("verification") or {}
    def keys(items):
        out = set()
        for it in items or []:
            mm = re.match(r"Section\s+(\S+)\s+(.+?)(?:\s+\(several.*)?$", it)
            if mm:
                out.add(_cite_key(mm.group(1), mm.group(2)))
        return out
    new_format = "supported" in guard
    g_supported, g_unchecked = keys(guard.get("supported")), keys(guard.get("not_checked") or guard.get("unverified"))
    dis = []
    for c in v.get("checks", []) or []:
        canon = c.get("canonical") or ""
        mm = re.match(r"(.+?)\s+(?:s\.|Art\.|Article\s)\s*(\S+)$", canon)
        if not mm:
            continue
        key = _cite_key(mm.group(2), mm.group(1))
        status = str(c.get("status") or "").upper()
        verified = status == "VERIFIED"
        counted = key in g_supported if new_format else key not in g_unchecked
        if counted and not verified:
            dis.append(f"guard counted {canon} as supported; verifier: {status}")
        elif verified and key in g_unchecked:
            dis.append(f"verifier VERIFIED {canon}; guard: not checked")
    m["checker_disagreement"] = dis
    # Every cited provision in the final text that the case's checklist does
    # not list as permissible: for REVIEW, not automatically wrong.
    from app.ai import tool_contract
    unlisted = []
    for sent in sentences(final):
        for ref in tool_contract.provision_refs(sent):
            if not _hits(case.get("support", []), sent) and not _hits(case.get("forbid", []), sent):
                lbl = f"s.{ref.section} {ref.statute}"
                if lbl not in unlisted:
                    unlisted.append(lbl)
    m["unlisted_authorities"] = unlisted
    m["latency_s"] = row.get("latency_s")
    m["first_token_s"] = row.get("first_token_s")
    return m

# ── running ──────────────────────────────────────────────────────────────────

async def _one(r, case: dict, document: str) -> dict:
    from app.api.v1.routes import ai as routes
    body = {k: case[k] for k in ("instruction", "template", "case_type", "province", "mode") if k in case}
    body["document"] = document
    if case.get("selection"):
        body["selection"] = case["selection"]
    t0 = time.perf_counter()
    first = None
    raw, guard, verif, done, err = "", None, None, False, None
    try:
        resp = await routes.ai_draft_stream(routes.DraftRequest(**body), current_user={"_id": "eval-lawyer", "role": "lawyer"})
        async for part in resp.body_iterator:
            part = part if isinstance(part, str) else part.decode()
            for line in part.splitlines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    done = True
                    continue
                obj = json.loads(data)
                if "content" in obj:
                    first = first if first is not None else time.perf_counter() - t0
                    raw += obj["content"]
                if "guard" in obj:
                    guard = obj["guard"]
                if "verification" in obj:
                    verif = obj["verification"]
                if "error" in obj:
                    err = obj["error"]
    except Exception as exc:          # recorded per row, never fatal to the run
        err = f"{type(exc).__name__}"
    return {"raw": raw, "guard": guard, "verification": verif, "done": done, "error": err,
            "latency_s": round(time.perf_counter() - t0, 2),
            "first_token_s": round(first, 2) if first is not None else None}


def _identity() -> dict:
    files = ["app/api/v1/routes/ai.py", "app/ai/visible_authority.py", "app/ai/draft_jurisdiction.py",
             "app/ai/exact_provision.py", "app/ai/citation_verification.py", "app/ai/answer_citations.py",
             "app/ai/draft_guard.py", "app/ai/llm.py"]
    return {f: _sha((BACKEND_DIR / f).read_bytes()) for f in files if (BACKEND_DIR / f).exists()}


async def run(label: str, repeat: int, split: str, src: Path, pause: float) -> Path:
    import eval_chat_length as E
    E._apply_overlay()
    from app.db.chroma import connect_chroma
    connect_chroma()
    from app.api.v1.routes import ai as routes

    async def _no_record(**kw):
        return None

    async def _no_case_law(q):
        return ""
    routes.provenance_service.record_answer = _no_record
    routes._retrieve_case_law_context = _no_case_law

    docs = _documents(src)
    cases = load_cases(split)
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"{label}.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for rep in range(1, repeat + 1):
            for case in cases:
                row = await _one(routes, case, docs.get(case["source_docx"], "")[:8000])
                rec = {"id": case["id"], "rep": rep, "split": case["split"], "category": case["category"],
                       "province": case["province"], "mode": case["mode"], **row}
                rec["raw"] = rec["raw"][:3000]
                if rec["guard"] and rec["guard"].get("text"):
                    rec["guard"]["text"] = rec["guard"]["text"][:3000]
                rec["metrics"] = assess(case, rec)
                fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
                fh.flush()
                mm = rec["metrics"]
                print(f"{label} r{rep} {case['id']:<3} {rec['latency_s']:>5}s "
                      f"unsupported={len(mm['unsupported_final'])} raw_unsup={len(mm['unsupported_raw'])} "
                      f"wrong_withheld={len(mm['wrongly_withheld'])} jur={len(mm['jurisdiction_mistakes'])} "
                      f"missing={len(mm['missing_required'])} disagree={len(mm['checker_disagreement'])} "
                      f"guard={'ran' if mm['guard_ran'] else 'NO'} empty={mm['empty_final']}", flush=True)
                await asyncio.sleep(pause)
    (RESULTS / f"{label}.manifest.json").write_text(json.dumps({
        "label": label, "when": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "repeat": repeat, "split": split, "cases": len(cases), "dataset_sha256": _sha(CASES.read_bytes()),
        "code": _identity(), "stubbed": ["provenance.record_answer", "case-law retrieval"],
        "model_purpose": "draft_stream"}, indent=1), encoding="utf-8")
    return out

# ── scoring ──────────────────────────────────────────────────────────────────

METRICS = ("unsupported_final", "unlisted_authorities", "unsupported_raw", "wrongly_withheld",
           "jurisdiction_mistakes", "missing_required", "checker_disagreement")


def summarise(path: Path) -> dict:
    cases = {c["id"]: c for c in load_cases("all")}
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    by = defaultdict(lambda: defaultdict(float))
    for r in rows:
        m = assess(cases[r["id"]], r)        # re-scored with the CURRENT checklist
        for key in (r["category"], f"split:{r['split']}", "ALL"):
            b = by[key]
            b["rows"] += 1
            for k in METRICS:
                b[k] += len(m[k])
            b["empty_final"] += m["empty_final"]
            b["guard_not_run"] += not m["guard_ran"]
            b["latency_s"] += m["latency_s"] or 0
    return {k: {**{x: (round(v, 2) if x != "latency_s" else round(v / b["rows"], 1)) for x, v in b.items()}}
            for k, b in sorted(by.items())}


def per_case(path: Path) -> dict:
    cases = {c["id"]: c for c in load_cases("all")}
    out = defaultdict(list)
    for x in path.read_text(encoding="utf-8").splitlines():
        if x.strip():
            r = json.loads(x)
            m = assess(cases[r["id"]], r)
            out[r["id"]].append({k: m[k] for k in METRICS if m[k]} | ({"empty": True} if m["empty_final"] else {}))
    return out


def subject_suite() -> dict:
    """Fix 1 on the REAL corpus index, no model: each sentence through draft_guard."""
    import eval_chat_length as E
    E._apply_overlay()
    from app.db.chroma import connect_chroma
    connect_chroma()
    from app.ai import draft_guard
    rows = []
    for line in (EVAL_DIR / "subject_adversarial_v1.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("//"):
            continue
        item = json.loads(line)
        g = draft_guard.check(item["text"], "x", [], "punjab", None)
        got = "withhold" if g["counts"]["withheld_sentences"] else "keep"
        rows.append({**item, "got": got, "reasons": [r for w in g["withheld"] for r in w["reasons"]],
                     "supported": g["supported"], "not_checked": g["not_checked"]})
    scored = [r for r in rows if r["expect"] != "review"]
    return {"rows": rows,
            "false_withhold": [r["id"] for r in scored if r["expect"] == "keep" and r["got"] == "withhold"],
            "missed": [r["id"] for r in scored if r["expect"] == "withhold" and r["got"] == "keep"],
            "correct": sum(r["expect"] == r["got"] for r in scored), "scored": len(scored)}


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("inventory"); i.add_argument("--src", type=Path, default=DEFAULT_SRC)
    r = sub.add_parser("run"); r.add_argument("--label", required=True); r.add_argument("--repeat", type=int, default=1)
    r.add_argument("--split", default="all"); r.add_argument("--src", type=Path, default=DEFAULT_SRC)
    r.add_argument("--pause", type=float, default=1.0)
    sub.add_parser("subject")
    s = sub.add_parser("score"); s.add_argument("paths", nargs="+", type=Path); s.add_argument("--cases", action="store_true")
    a = ap.parse_args()
    if a.cmd == "inventory":
        doc = inventory(a.src)
        for f in doc["files"]:
            pii = {k: v for k, v in f["pii_counts"].items() if v}
            print(f"{f['doc_type']:<38} {f['words']:>4}w {f['placeholders']:>3} blanks "
                  f"jur={f['jurisdiction_mentions'] or '-'} pii={pii or 'none'}")
        print(f"{len(doc['files'])} files -> {PROVENANCE}")
    elif a.cmd == "subject":
        res = subject_suite()
        for r in res["rows"]:
            mark = "ok " if r["expect"] in (r["got"], "review") else "XX "
            print(f"{mark}{r['id']} expect={r['expect']:<8} got={r['got']:<8} "
                  f"{(r['reasons'][0][:150] if r['reasons'] else (r['supported'] or r['not_checked']))}")
        print(f"\nscored {res['scored']}: correct {res['correct']}, false withhold {res['false_withhold']}, "
              f"missed {res['missed']}")
    elif a.cmd == "run":
        print("wrote", asyncio.run(run(a.label, a.repeat, a.split, a.src, a.pause)))
    else:
        sums = [(p.stem, summarise(p)) for p in a.paths]
        keys = sorted({k for _, s in sums for k in s})
        cols = ("rows",) + METRICS + ("empty_final", "guard_not_run", "latency_s")
        for k in keys:
            print(f"\n[{k}]")
            for name, s in sums:
                row = s.get(k, {})
                print(f"  {name:<14} " + " ".join(f"{c.replace('_final', '').replace('unsupported', 'unsup')}={row.get(c, 0)}" for c in cols))
        if a.cases:
            for name, _ in sums:
                print(f"\n== per case: {name}")
                for cid, reps in per_case(Path(next(p for p in a.paths if p.stem == name))).items():
                    if any(reps):
                        print(f"  {cid}: {reps}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
