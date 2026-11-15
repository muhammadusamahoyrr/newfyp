"""The V2 drafter evaluation harness (scripts/eval_drafter_v2.py): dataset
integrity, holdout lock, privacy exclusions, source-wording guard, scoring.
Local only: a tiny synthetic source folder, no model, no real collection."""
from __future__ import annotations

import json
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import eval_drafter_v2 as V  # noqa: E402

DOCX_XML = ('<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body>{}</w:body></w:document>')


def _docx(path: Path, paragraphs: list[str]):
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", DOCX_XML.format(body))


@pytest.fixture
def v2(tmp_path, monkeypatch):
    """A copy of the real V2 dataset files in tmp, so tests can tamper safely."""
    d = tmp_path / "drafter_v2"
    shutil.copytree(V.V2_DIR, d, ignore=shutil.ignore_patterns("results", "transmit_preview.json"))
    for name, attr in (("cases_v2.jsonl", "CASES"), ("legal_sources.json", "SOURCES"),
                       ("source_audit.json", "AUDIT"), ("holdout.lock.json", "HOLDOUT_LOCK")):
        monkeypatch.setattr(V, attr, d / name)
    monkeypatch.setattr(V, "V2_DIR", d)
    return d


@pytest.fixture
def source(tmp_path):
    """A synthetic two-collection folder shaped like the real one."""
    s = tmp_path / "src"
    ld = s / "legaldocs.pk" / "affidavits" / "sample-affidavit"
    ld.mkdir(parents=True)
    _docx(ld / "sample-affidavit.docx", ["I [Full Name] affirm"])
    (ld / "sample-affidavit.md").write_text("I [Full Name] solemnly affirm the river flows quietly past the old mill today",
                                            encoding="utf-8")
    (s / "legaldocs.pk" / "documents.csv").write_text(
        "Category,Title,Urdu Title,Slug,Fields,Has English,Has Urdu,Path,Source URL\n"
        "Affidavits,Sample Affidavit,x,sample-affidavit,1,True,True,affidavits/sample-affidavit/,https://example.invalid\n",
        encoding="utf-8")
    dd = s / "drive-drafts" / "court"
    dd.mkdir(parents=True)
    _docx(dd / "Clean.docx", ["APPLICATION UNDER ____ for ____"])
    (dd / "Clean.md").write_text("APPLICATION UNDER ____ for ____", encoding="utf-8")
    _docx(dd / "Filled.docx", ["Applicant holds CNIC 35202-1234567-1 and lives at House No. 12"])
    (dd / "Filled.md").write_text("x", encoding="utf-8")
    (s / "drive-drafts" / "files.csv").write_text(
        "Category,Title,File,Format,Path,Markdown,Bytes\n"
        "Court,Clean,Clean.docx,docx,court/Clean.docx,court/Clean.md,1\n"
        "Court,Filled,Filled.docx,docx,court/Filled.docx,court/Filled.md,1\n", encoding="utf-8")
    return s

# ── dataset integrity ───────────────────────────────────────────────────────

def test_the_shipped_dataset_is_valid(v2):
    assert V.validate(None) == []


def test_every_track_has_dev_and_holdout_and_both_languages():
    cases = V.load_cases()
    for track in V.TRACKS:
        assert {c["split"] for c in cases if c["track"] == track} == {"dev", "holdout"}
    assert {c["lang"] for c in cases} == {"en", "ur"}
    assert {"unknown", "punjab", "sindh"} <= {c["province"] for c in cases}


def test_definitive_labels_rest_only_on_official_text_checked_sections():
    sources = json.loads(V.SOURCES.read_text(encoding="utf-8"))["sources"]
    for c in V.load_cases():
        if c["label_status"] != "definitive":
            continue
        for l in c["allow"] + c["forbid"]:
            if "cite" in l and l.get("kind", "section") == "section":
                src = sources[l["source"]]
                assert src["url"] and l["cite"] in src["checked_sections"] and not l.get("review"), (c["id"], l)


def test_a_cpc_label_can_never_be_definitive_without_an_official_source():
    sources = json.loads(V.SOURCES.read_text(encoding="utf-8"))["sources"]
    assert sources["cpc_1908"]["url"] is None
    assert all(c["label_status"] != "definitive" for c in V.load_cases()
               if any(l.get("source") == "cpc_1908" and l.get("kind", "section") == "section" for l in c["allow"] + c["forbid"]))

# ── holdout lock ────────────────────────────────────────────────────────────

def _rewrite(path: Path, cid: str, mutate):
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("//") and json.loads(line)["id"] == cid:
            c = json.loads(line); mutate(c); line = json.dumps(c, ensure_ascii=False)
        out.append(line)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def test_editing_a_locked_holdout_case_is_detected(v2):
    hold = next(c for c in V.load_cases() if c["split"] == "holdout")
    _rewrite(V.CASES, hold["id"], lambda c: c.update(instruction=c["instruction"] + " (tuned)"))
    assert any("changed after it was locked" in p for p in V.validate(None))


def test_moving_a_dev_case_into_the_holdout_without_relocking_is_detected(v2):
    dev = next(c for c in V.load_cases() if c["split"] == "dev")
    _rewrite(V.CASES, dev["id"], lambda c: c.update(split="holdout"))
    assert any("not in the lock" in p for p in V.validate(None))

# ── privacy ─────────────────────────────────────────────────────────────────

def test_a_cnic_shaped_string_in_a_case_file_is_flagged(v2):
    dev = next(c for c in V.load_cases() if c["split"] == "dev")
    _rewrite(V.CASES, dev["id"], lambda c: c.update(instruction=c["instruction"] + " CNIC 35202-1234567-1"))
    assert any("cnic-shaped" in p for p in V.validate(None))


def test_an_audit_record_carrying_text_is_flagged(v2):
    doc = json.loads(V.AUDIT.read_text(encoding="utf-8"))
    doc["documents"][0]["text"] = "anything"
    V.AUDIT.write_text(json.dumps(doc), encoding="utf-8")
    assert any("unexpected fields" in p for p in V.validate(None))


def test_the_audit_counts_originals_once_and_flags_filled_drafts(v2, source):
    out = V.audit(source)
    assert out["summary"]["documents"] == 3                       # .docx + .md = one document
    risks = {d["doc_type"]: d["risk"] for d in out["documents"]}
    assert risks == {"Sample Affidavit": "template_low", "Clean": "manual_review", "Filled": "exclude"}
    stored = V.AUDIT.read_text(encoding="utf-8")
    assert "35202" not in stored and "river flows quietly" not in stored, "the audit stored source text or a CNIC"


def test_the_shipped_audit_never_uses_excluded_files_and_holds_no_text():
    doc = json.loads(V.AUDIT.read_text(encoding="utf-8"))
    assert doc["summary"]["by_risk"].get("exclude", 0) >= 1
    import re
    for c in V.load_cases():
        assert not re.search(r"\.(?:docx?|md|pdf|html)\b|[0-9a-f]{12}", c["inspired_by"]),             "a case names a source FILE or hash, not a category"


def test_copied_source_wording_is_detected(v2, source):
    case = dict(V.load_cases()[0])
    case["instruction"] = "Please draft: I [Full Name] solemnly affirm the river flows quietly past the old mill"
    assert V.copied_wording(source, [case])
    case["instruction"] = "Please draft an affidavit about a missing card for my client."
    assert V.copied_wording(source, [case]) == []

# ── scoring (the final visible proposal) ────────────────────────────────────

def _row(final, raw=None, guard_extra=None, rep=1, cid="V01"):
    return {"id": cid, "rep": rep, "raw": raw if raw is not None else final, "done": True, "error": None, "latency_s": 2.0,
            "guard": {"ran": True, "text": final, "withheld": [], **(guard_extra or {})}, "verification": {"checks": []}}


def _case(cid):
    return next(c for c in V.load_cases() if c["id"] == cid)


def test_order_rule_near_misses():
    c = _case("V01")       # rejection of plaint: Order VII Rule 11 allowed, Section 11 forbidden
    ok = V.assess(c, _row("That the plaint discloses no cause of action and be rejected under Order VII Rule 11 CPC."))
    assert ok["allowed_cited"] and not ok["wrong_provision"] and not ok["missing_citation"]
    arabic = V.assess(c, _row("The plaint discloses no cause of action and is liable to be rejected under Order 7 Rule 11 CPC."))
    assert arabic["allowed_cited"]
    wrong = V.assess(c, _row("The plaint discloses no cause of action and must be rejected under Section 11 CPC."))
    assert wrong["wrong_provision"] and wrong["missing_citation"]
    # both in one sentence: the Order/Rule is allowed, and the bare s.11 is still caught
    both = V.assess(c, _row("The plaint is liable to be rejected under Order VII Rule 11 and Section 11 CPC."))
    assert both["allowed_cited"] and both["wrong_provision"]
    c2 = _case("V02")      # return of plaint: Rule 10 allowed, Rule 11 forbidden when the sentence returns
    m = V.assess(c2, _row("The plaint be returned for want of territorial jurisdiction under Order VII Rule 11 CPC."))
    assert m["wrong_provision"] and not m["allowed_cited"]
    m = V.assess(c2, _row("The plaint be returned for want of territorial jurisdiction under Order VII Rule 10 CPC."))
    assert m["allowed_cited"] and not m["wrong_provision"]


def test_only_the_final_text_is_scored():
    c = _case("V10")
    m = V.assess(c, _row("That the case calls for further inquiry under Section 497 CrPC.",
                         raw="That bail lies under Section 438 CrPC. That the case calls for further inquiry under Section 497 CrPC."))
    assert not m["wrong_provision"]


def test_a_withheld_permitted_authority_is_counted_as_wrongly_withheld():
    c = _case("V10")
    m = V.assess(c, _row("That the case calls for further inquiry.",
                         guard_extra={"withheld": [{"text": "Bail is due under Section 497 CrPC.", "reasons": ["x"]}]}))
    assert m["wrongly_withheld"] and m["missing_citation"]


def test_neutral_cases_need_a_placeholder_or_clarification():
    c = _case("V17")
    assert V.assess(c, _row("Vacate for non-payment of rent under [applicable provincial rent law -- choose jurisdiction]."))[
        "placeholder_or_clarification"] is True
    m = V.assess(c, _row("Vacate for non-payment of rent under Section 111 of the Transfer of Property Act."))
    assert m["placeholder_or_clarification"] is False and m["wrong_provision"]
    assert "no_placeholder" in V.failed(m)


def test_jurisdiction_rules_are_reported_apart_from_wrong_sections():
    c = _case("V18")
    m = V.assess(c, _row("The landlord shall send the agreement to the Rent Registrar under Section 5 of the Sindh Rented Premises Ordinance."))
    assert m["jurisdiction_errors"] and not m["wrong_provision"]


def test_template_fill_scores_facts_blanks_and_invented_identifiers():
    c = _case("T01")
    good = ("Deponent: Sana Ahmed, parent Tariq Ahmed, lives at Lahore. Identity card: [CNIC]. Lost near Liberty Market; "
            "report lodged with [POLICE STATION].")
    m = V.assess(c, _row(good, cid="T01"))
    assert m["facts_placed"] == 1 and m["blanks_kept"] and not V.failed(m)
    bad = "Deponent: Sana Ahmed, parent Tariq Ahmed, Lahore, CNIC 35202-1234567-1, Liberty Market, Model Town police."
    m = V.assess(c, _row(bad, cid="T01"))
    assert m["forbidden_text"] and "blanks_filled_in" in V.failed(m)


def test_urdu_requirements_are_matched():
    c = _case("V13")
    assert not V.assess(c, _row("یہ کہ ملزم ضمانت کا حقدار ہے کیونکہ مزید انکوائری درکار ہے، دفعہ 497 ضابطہ فوجداری۔"))["missing_required"]


def test_tracks_are_never_combined_and_variance_is_reported():
    rows = [_row("That the case calls for further inquiry under Section 497 CrPC.", cid="V10", rep=1),
            _row("That bail lies under Section 438 CrPC for further inquiry.", cid="V10", rep=2),
            _row("Deponent: Sana Ahmed, Tariq Ahmed, Lahore, Liberty Market, [CNIC].", cid="T01")]
    s = V.summarise(rows)
    assert set(s) == {"free_drafting", "template_fill"}
    assert s["free_drafting"]["ALL"]["rows"] == 2 and s["template_fill"]["ALL"]["rows"] == 1
    assert s["free_drafting"]["variance_cases"] == ["V10"]


def test_a_model_run_refuses_without_approval(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["eval_drafter_v2.py", "run", "--label", "x"])
    assert V.main() == 2
    assert "needs --approved" in capsys.readouterr().out


def test_the_transmit_preview_contains_only_case_fields():
    prev = V.transmit_preview()
    assert len(prev["requests"]) == len(V.load_cases())
    for item in prev["requests"]:
        assert set(item["request"]) <= {"instruction", "document", "case_type", "province", "mode", "template", "selection"}


# ── scorer v2 (2026-10-15) ──────────────────────────────────────────────────

def test_scorer_v2_reads_unicode_hyphens_and_urdu_digits_v1_does_not():
    c = _case("V09")
    row = _row("That the inherent power of the High Court under Section 561\u2011A of the Code of Criminal Procedure, 1898 "
               "is invoked to quash these proceedings as an abuse of process.", cid="V09")
    v1, v2 = V.assess(c, row), V.assess_v2(c, row)
    assert v1["missing_citation"] is True, "scorer v1 must stay as it was (reproducible)"
    assert v2["missing_citation"] is False and v2["allowed_cited"]
    assert V.normalise_text("\u06f4\u06f9\u06f7") == "497"


def test_scorer_v2_separates_a_blank_left_empty_from_a_fact_invented():
    c = _case("T01")
    kept = _row("Deponent: Sana Ahmed\nParent: Tariq Ahmed\nLives at: Lahore\nIdentity card: [CNIC]\n"
                "(a) the identity card went missing on 2 October 2026, near Liberty Market;\n"
                "(b) a report has been lodged with [POLICE STATION].", cid="T01")
    emptied = _row("Deponent: Sana Ahmed\nParent: Tariq Ahmed\nLives at: Lahore\nIdentity card: \n"
                   "(a) the identity card went missing on 2 October 2026, near Liberty Market;\n"
                   "(b) a report has been lodged with .", cid="T01")
    invented = _row("Deponent: Sana Ahmed\nParent: Tariq Ahmed\nLives at: Lahore\nIdentity card: 35202-1234567-1\n"
                    "(a) the identity card went missing on 2 October 2026, near Liberty Market;\n"
                    "(b) a report has been lodged with Model Town police station.", cid="T01")
    assert V.assess_v2(c, kept)["field_states"] == {"CNIC": "kept", "POLICE STATION": "kept"}
    m = V.assess_v2(c, emptied)
    assert m["field_states"] == {"CNIC": "emptied", "POLICE STATION": "emptied"} and not V.failed_v2(m)
    assert "blanks_filled_in" in V.failed(V.assess(c, emptied)), "v1 called this a failure; v2 must not"
    m = V.assess_v2(c, invented)
    assert set(m["fact_invented"]) == {"CNIC", "POLICE STATION"} and "fact_invented" in V.failed_v2(m)


def test_scorer_v2_counts_several_blank_markers_as_kept():
    c = _case("T04")
    row = _row("GENERAL POWER OF ATTORNEY\nI, Kamran Shah, appoint Nadia Shah to act for me in bank accounts and property in Karachi.\n"
               "Witnesses: ______   ______\nDate: ______", cid="T04")
    assert V.assess_v2(c, row)["field_states"]["WITNESS 1"] == "kept"


def test_the_saved_v1_results_still_score_as_reported():
    rows = [json.loads(x) for x in (V.RESULTS / "v2_r1.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    rep = V.failure_report(rows, scorer="v1")["legal_correctness_definitive_only"]
    assert rep == {"definitive_rows": 14, "definitive_rows_with_legal_error": 4}
    rep2 = V.failure_report(rows, scorer="v2")["legal_correctness_definitive_only"]
    assert rep2 == {"definitive_rows": 14, "definitive_rows_with_legal_error": 2}


# ── holdout v3: blind until independently labelled (2026-10-15) ─────────────

def test_holdout_v3_requests_are_locked_unlabelled_and_new():
    import hashlib
    d = V.V2_DIR / "holdout_v3"
    lines = [l for l in (d / "requests.jsonl").read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("//")]
    lock = json.loads((d / "requests.lock.json").read_text(encoding="utf-8"))["cases"]
    rows = [json.loads(l) for l in lines]
    assert {r["id"] for r in rows} == set(lock)
    for r, l in zip(rows, lines):
        assert hashlib.sha256(l.encode("utf-8")).hexdigest() == lock[r["id"]], f"{r['id']} changed after it was locked"
        assert r["labels"] is None and r["label_status"] == "awaiting_independent_labeller"
    v2_texts = {c["instruction"] for c in V.load_cases()}
    assert not any(r["instruction"] in v2_texts for r in rows), "a v3 request reuses a v2 case"
    assert {r["track"] for r in rows} == {"free_drafting", "template_fill"} and {r["lang"] for r in rows} == {"en", "ur"}


# ── input-fact fidelity (2026-10-15, eval v2_r3 V09) ────────────────────────

def test_an_invented_fact_is_reported_on_its_own():
    """v2_r3 V09 rep 1 asserted the accused's mental state -- a fact the request
    never gave. It is reported as an invented fact, not as a citation error."""
    case = next(c for c in V.load_cases() if c["id"] == "V09")
    bad = _row("That the accused, though not insane, is unable to understand the proceedings, so the proceedings are "
               "an abuse of process to be quashed under Section 561-A CrPC.", cid="V09")
    m = V.assess_v2(case, bad)
    assert m["invented_facts"] and "invented_facts" in V.failed_v2(m)
    assert m["forbidden_text"] == [] and m["wrong_provision"] == [], "an invented fact is not a citation error"
    ok = _row("That the proceedings are an abuse of the process of the Court and are liable to be quashed under "
              "Section 561-A CrPC; [facts showing the abuse].", cid="V09")
    assert V.assess_v2(case, ok)["invented_facts"] == []


def test_the_invented_fact_label_is_on_a_dev_case_only():
    for c in V.load_cases():
        if any(l.get("kind") == "invented_fact" for l in c["forbid"]):
            assert c["split"] == "dev", c["id"]
