"""section-split-v3 (app/ai/section_repair.py) against official text, 2026-10-16.

Fixtures are contiguous, unedited excerpts of official PDFs as extracted by
scripts/ingest_statutes.extract_text (tests/fixtures/statute_split/MANIFEST.json
records URL, sha256 and offsets). They pin:

* v3 splits every provision the isolated pilot found misfiled (PECA 26-A inside
  26, PPC 489-F inside 489-D, ...), marks omitted provisions omitted, ignores a
  contents page and drops footnotes v2 read as sections;
* v2 -- the parser behind the existing indexes -- is UNCHANGED on the same text;
* adversarial text (subsections, footnotes, inline markers, out-of-order
  numbers) never becomes a section;
* mutation: disabling any one critical rule makes these checks fail.
Pure: no Chroma, no database.
"""
import json
from pathlib import Path

import pytest

import app.ai.section_repair as sr
from app.ai.section_repair import SPLIT_VERSION, SPLIT_VERSION_V3, section_label, split_provisions

FIX = Path(__file__).resolve().parent / "fixtures" / "statute_split"


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _labels(text: str, version: str) -> list[str]:
    """section label, or region; "+" suffix = recorded omitted."""
    return [(section_label(b["section"]) if b["section"] else b["region"])
            + ("+" if b["provision_status"] == "omitted" else "")
            for b in split_provisions(text, version)]


def _block(text: str, label: str, version: str = SPLIT_VERSION_V3) -> dict:
    hits = [b for b in split_provisions(text, version) if section_label(b["section"]) == label]
    assert hits, f"{label} not split out"
    return hits[0]


# name: (v2 labels -- frozen, v3 labels)
EXPECTED = {
    "court_fees_11.txt": (["preamble"], ["11"]),
    "court_fees_16_17.txt": (["16", "17"], ["16+", "17"]),
    "court_fees_19g_19j.txt": (["19-G"], ["19-G", "19-H", "19-I"]),
    "court_fees_35_36.txt": (["35"], ["35", "35-A"]),
    "cpc_116_117.txt": (["116", "117"], ["116", "117"]),
    "cpc_6_9.txt": (["6", "9"], ["6", "7+", "9"]),
    "crpc_10_14.txt": (["10", "11", "13"], ["10+", "11+", "12", "13+", "14", "14-A"]),
    "crpc_22a_22b.txt": (["22-A"], ["22-A"]),
    "dmma_2.txt": (["2"], ["2"]),
    "limitation_29_schedule.txt": (["29", "32"], ["29", "32"]),
    "peca_22_22b.txt": (["22", "22-B", "22-C"], ["22", "22-A", "22-B", "22-C"]),
    "peca_26_27.txt": (["26"], ["26", "26-A"]),
    "peca_28_31.txt": (["28", "30-B", "30-C", "30-D"], ["28", "29", "30", "30-A", "30-B", "30-C", "30-D"]),
    "peca_2e_2g.txt": (["preamble"], ["2-E", "2-F"]),
    "peca_2r_2u.txt": (["2-R"], ["2-R", "2-S", "2-T"]),
    "ppc_489d_490.txt": (["489-D"], ["489-D", "489-E", "489-F"]),
    "ppc_footnote_artifact_153b.txt": (["preamble", "155", "1-S"], ["preamble", "155"]),
}


def test_every_fixture_is_from_its_recorded_official_source():
    manifest = json.loads((FIX / "MANIFEST.json").read_text(encoding="utf-8"))["fixtures"]
    assert set(EXPECTED) | {"court_fees_contents_and_start.txt"} == set(manifest)
    for name, rec in manifest.items():
        assert rec["official_url"].startswith("https://") and len(rec["source_sha256"]) == 64
        assert (FIX / name).stat().st_size > 0


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_v2_is_unchanged_on_official_text(name):
    assert _labels(_fx(name), SPLIT_VERSION) == EXPECTED[name][0]


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_v3_on_official_text(name):
    assert _labels(_fx(name), SPLIT_VERSION_V3) == EXPECTED[name][1]


def test_default_is_still_v2_and_unknown_versions_are_refused():
    t = _fx("peca_26_27.txt")
    assert split_provisions(t) == split_provisions(t, SPLIT_VERSION)
    with pytest.raises(ValueError):
        split_provisions(t, "section-split-v9")


# ── the boundaries that matter ───────────────────────────────────────────────

def test_peca_26_and_26a_never_share_a_block():
    t = _fx("peca_26_27.txt")
    s26, s26a = _block(t, "26"), _block(t, "26-A")
    assert "Spoofing" in s26["text"] and "false and fake" not in s26["text"]
    assert "false and fake" in s26a["text"] and "Spoofing" not in s26a["text"]
    assert s26a["text"].startswith("1[26A") and s26a["heading_rule"] == "bracketed_insertion"
    assert "1[26A" in split_provisions(t, SPLIT_VERSION)[0]["text"], "v2 filed 26-A inside 26 (the defect)"


@pytest.mark.parametrize("name,inserted", [
    ("peca_22_22b.txt", "22-A"), ("peca_28_31.txt", "30-A"), ("peca_28_31.txt", "29"), ("peca_28_31.txt", "30"),
    ("court_fees_19g_19j.txt", "19-H"), ("court_fees_35_36.txt", "35-A"), ("ppc_489d_490.txt", "489-F"),
])
def test_inserted_provisions_carry_their_own_text(name, inserted):
    b = _block(_fx(name), inserted)
    assert b["provision_status"] == "not_recorded" and len(b["text"]) > 80


def test_ppc_489f_is_the_cheque_offence_not_part_of_489d():
    t = _fx("ppc_489d_490.txt")
    assert "Dishonestly issuing a cheque" in _block(t, "489-F")["text"]
    assert "Dishonestly issuing a cheque" not in _block(t, "489-D")["text"]


@pytest.mark.parametrize("name,label", [("court_fees_16_17.txt", "16"), ("cpc_6_9.txt", "7"),
                                        ("crpc_10_14.txt", "10"), ("crpc_10_14.txt", "13")])
def test_omitted_provisions_are_never_operative(name, label):
    assert _block(_fx(name), label)["provision_status"] == "omitted"


def test_a_live_section_with_some_words_omitted_stays_live():
    assert _block(_fx("cpc_116_117.txt"), "116")["provision_status"] == "not_recorded"


def test_the_contents_page_is_not_read_as_the_act():
    t = _fx("court_fees_contents_and_start.txt")
    v3 = split_provisions(t, SPLIT_VERSION_V3)
    assert v3[0]["region"] == "contents"
    assert [b for b in v3 if b["region"] == "schedule"] == []
    assert "This Act may be called" in _block(t, "1")["text"]
    # v2 read the contents entries as sections and the Act as schedules
    v2 = split_provisions(t, SPLIT_VERSION)
    assert any(b["region"] == "schedule" for b in v2)


def test_a_footnote_is_not_a_section():
    v3 = _labels(_fx("ppc_footnote_artifact_153b.txt"), SPLIT_VERSION_V3)
    assert not any(l.endswith("-S") for l in v3)


# ── adversarial: section-like text that is NOT a section ─────────────────────

def _v3(text):
    return [section_label(b["section"]) for b in split_provisions(text, SPLIT_VERSION_V3) if b["section"]]


def test_an_inserted_subsection_that_fits_the_order_is_still_not_a_section():
    text = ("2. Definitions.__ (1) In this Act, unless the context otherwise requires.\n"
            "(2A) Notwithstanding anything contained in sub-section (2), the agency may act.\n"
            "3. Application.__ It applies.\n")
    assert _v3(text) == ["2", "3"]


def test_cpc_order_rules_restarting_at_1_after_a_heading_are_kept():
    text = ("158. Repeal and savings.__ The enactments are repealed.\n"
            "ORDER I\nPARTIES TO SUITS\n"
            "1. Who may be joined as plaintiffs. All persons may be joined.\n"
            "2. Power of Court to order separate trial. Where it appears.\n")
    assert _v3(text) == ["158", "1", "2"]


def test_subsections_and_inserted_subsections_are_not_sections():
    text = ("30. Power to investigate.__ (1) Only an authorized officer shall have the powers.\n"
            "(2) The Federal Government may by notification designate officers.\n"
            "(2A) Notwithstanding anything contained in sub-section (2), the agency may act.\n"
            "31. Expedited preservation.__ (1) If an authorized officer is satisfied that data is needed.\n")
    assert _v3(text) == ["30", "31"]


def test_footnote_lines_and_inline_markers_are_not_headings():
    text = ("1. Short title.__ This Act may be called the Example Act.\n"
            "2. Definitions.__ In this Act, 2[Appropriate Government] means the Government.\n"
            "1[(iv) “Authority” means the Authority established under section 2A;]\n"
            "2Ins. by A. O., 1937.\n"
            "1Subs. by Act No. II of 2025, s.2.\n"
            "3. Application.__ It applies to every citizen.\n")
    assert _v3(text) == ["1", "2", "3"]


def test_a_bracketed_number_out_of_order_is_not_admitted():
    text = ("30. Power to investigate.__ It applies.\n"
            "1[5. Misplaced heading. Whoever does this shall be punished.\n"
            "31. Expedited preservation.__ It applies.\n")
    assert _v3(text) == ["30", "31"]


@pytest.mark.xfail(strict=True, reason=(
    "KNOWN LIMITATION inherited from v2: a sentence wrapped so that a line starts '5. Thousand ...' "
    "reads as section 5. A fix that dropped backward-numbered headings after a lowercase line was "
    "REJECTED by the full-document audit: it deleted 32 real CPC Order 'Rule 1' headings and CrPC "
    "ss.94, 126, 165. Needs a different signal before it can be fixed."))
def test_section_like_text_mid_sentence_is_not_a_heading():
    text = ("20. Offences.__ Whoever does so shall be punished with fine which may extend to\n"
            "5. Thousand rupees, or with both.\n"
            "21. Next offence.__ Whoever does so.\n")
    assert _v3(text) == ["20", "21"]


def test_schedule_articles_stay_in_the_schedule():
    text = ("31. Repeal.__ The enactments are repealed.\n"
            "SCHEDULE I\n1. Plaint or memorandum of appeal. Ten rupees.\n2. Copy of decree. One rupee.\n")
    blocks = split_provisions(text, SPLIT_VERSION_V3)
    assert _v3(text) == ["31"] and blocks[-1]["region"] == "schedule"


def test_cpc_order_rule_references_are_not_sections():
    from app.ai.legal_sources.identity import classify_reference
    assert classify_reference("Order XXXIX Rule 1")["kind"] == "order_rule"
    assert classify_reference("section 26-A")["key"] == "s26A"


# ── mutation: each critical rule, disabled, must be caught ───────────────────

def _violations() -> list[str]:
    """The invariants above, as a list of failures (empty = all hold)."""
    out = []
    t = _fx("peca_26_27.txt")
    if "26-A" not in _v3(t):
        out.append("26-A not split")
    if _labels(_fx("court_fees_16_17.txt"), SPLIT_VERSION_V3)[0] != "16+":
        out.append("omission not recorded")
    if _block(_fx("cpc_116_117.txt"), "116")["provision_status"] != "not_recorded":
        out.append("live s.116 marked omitted")
    if _v3("30. A.__ x\n1[5. Misplaced heading. Whoever.\n31. B.__ y\n") != ["30", "31"]:
        out.append("out-of-order heading admitted")
    if _v3("30. A.__ x\n(2A) Notwithstanding anything contained in it.\n31. B.__ y\n") != ["30", "31"]:
        out.append("subsection read as section")
    # Here ORDER cannot help ((2A) fits between 2 and 3): only the heading-dash rule does.
    if _v3("2. Definitions.__ x\n(2A) Notwithstanding anything contained in sub-section (2), it applies.\n"
           "3. B.__ y\n") != ["2", "3"]:
        out.append("subsection read as section (in-order)")
    if any(l.endswith("-S") for l in _labels(_fx("ppc_footnote_artifact_153b.txt"), SPLIT_VERSION_V3)):
        out.append("footnote read as section")
    if split_provisions(_fx("court_fees_contents_and_start.txt"), SPLIT_VERSION_V3)[0]["region"] != "contents":
        out.append("contents page read as the Act")
    if "2-E" not in _v3(_fx("peca_2e_2g.txt")):
        out.append("parenthesised heading missed")
    return out


def test_no_violations_on_the_real_parser():
    assert _violations() == []


_NEVER = __import__("re").compile(r"(?!)")


@pytest.mark.parametrize("attr,mutant", [
    ("_BRACKETED_HEADING", _NEVER),
    ("_PAREN_HEADING", _NEVER),
    ("_PAREN_HEADING", __import__("re").compile(r"^[ \t]*\((\d{1,3})([A-Z]{1,2})\)[ \t]+", __import__("re").M)),
    ("_FOOTNOTE_ARTIFACT", _NEVER),
    ("_marked_omitted", lambda part: False),
    ("_marked_omitted", lambda part: True),
    ("_contents_end", lambda text: 0),
    ("_admit_in_order", lambda heads, extra: heads.update({p: h for p, h in extra.items() if p not in heads})),
])
def test_mutants_are_caught(monkeypatch, attr, mutant):
    monkeypatch.setattr(sr, attr, mutant)
    assert _violations(), f"disabling {attr} went unnoticed"


# -- ingestion wiring: v3 is opt-in, the sec_v2 build stays on v2 --

@pytest.fixture(scope="module")
def ingest():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "ingest_statutes_v3_under_test", Path(__file__).resolve().parent.parent / "scripts" / "ingest_statutes.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_ingestion_defaults_to_v2_and_v3_is_opt_in(ingest):
    t = _fx("peca_26_27.txt")
    v2 = ingest.make_chunks(t, "PECA 2016", "criminal", "peca.pdf")
    v3 = ingest.make_chunks(t, "PECA 2016", "criminal", "peca.pdf", split_version=SPLIT_VERSION_V3)
    assert {c["meta"]["split_version"] for c in v2} == {SPLIT_VERSION}
    assert {c["meta"]["split_version"] for c in v3} == {SPLIT_VERSION_V3}
    assert "26A" not in {c["meta"]["section_number"] for c in v2}
    assert "26A" in {c["meta"]["section_number"] for c in v3}


def test_v3_ingestion_never_chunks_the_contents_page(ingest):
    chunks = ingest.make_chunks(_fx("court_fees_contents_and_start.txt"), "Court-Fees Act 1870", "civil",
                                "court-fees.pdf", split_version=SPLIT_VERSION_V3)
    assert chunks and all(c["meta"]["source_region"] != "contents" for c in chunks)


def test_the_sec_v2_build_is_pinned_to_v2():
    src = (Path(__file__).resolve().parent.parent / "scripts" / "build_sec_v2_index.py").read_text(encoding="utf-8")
    assert "make_chunks(text, statute, law_type, fname, province, SPLIT_VERSION)" in src
    assert "SPLIT_VERSION_V3" not in src
