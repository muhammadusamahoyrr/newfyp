"""Lettered-section repair at the source (2026-10-13).

The statute PDFs print "489-\\nF.\\nDishonestly issuing a cheque", and the
ingestion parser stored PPC 489-A..489-F as "489" -- the section for
tampering with a property mark. These pin: the fixed parser, the versioned
relabel rule (heading, continuation, schedule rows, letterless headings), and
that 489 and 489-F stay separate provisions. Offline.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from app.ai.section_repair import LETTERED_HEADING, buried_lettered_headings, relabels, repair_labels

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "ingest_statutes.py"


@pytest.fixture(scope="module")
def ingest():
    spec = importlib.util.spec_from_file_location("ingest_statutes_under_test", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PPC_TEXT = (
    "489. Tampering with property mark with intent to cause injury: \nWhoever removes, destroys...\n"
    "489-\nE. \nMaking or using documents resembling currency-notes: \n(1) Whoever makes...\n"
    "489-\nF. \nDishonestly issuing a cheque: \nWhoever dishonestly issues a cheque...\n"
    "108-\nA \nAbetment in Pakistan of offences outside it: \nA person abets an offence...\n"
    "12- A person who is not a public servant...\n"
    "490. Omitted.\n"
)


def test_the_parser_keeps_the_letter(ingest):
    secs = [s for s, _ in ingest._split_sections(PPC_TEXT)]
    assert secs == ["489", "489E", "489F", "108A", "12", "490"]


def test_489_and_489f_are_separate_provisions(ingest):
    parts = dict(ingest._split_sections(PPC_TEXT))
    assert parts["489"].startswith("489. Tampering")
    assert "cheque" in parts["489F"] and "cheque" not in parts["489"]


def test_the_parser_still_reads_plain_and_compact_headings(ingest):
    secs = [s for s, _ in ingest._split_sections("52. Harbour.\n489F. Cheque.\n22-A. Justice of peace.\n")]
    assert secs == ["52", "489F", "22A"]


@pytest.mark.parametrize("text,expected", [
    ("489-\nF. \nDishonestly", ("489", "F")),
    ("108-\nA \nAbetment", ("108", "A")),
    ("22-A: Justice", ("22", "A")),
    ("12- A person who", None),
    ("337- Punishment of shajjah: \nA. Whoever", None),
    ("489. Tampering", None),
])
def test_the_shared_heading_rule(text, expected):
    m = LETTERED_HEADING.match(text)
    assert (m.groups() if m else None) == expected


def _row(n, section, text, prefix="statutes_ppc_1860"):
    return (f"{prefix}_{n:04d}", {"section_number": section}, text)


def test_relabel_heading_and_its_continuation_only():
    rows = [
        _row(753, "489", "489. Tampering with property mark: Whoever removes"),
        _row(758, "489", "489-\nE. \nMaking or using documents resembling currency-notes"),
        _row(759, "489", "was printed or otherwise made, he shall be punished"),
        _row(760, "489", "489-\nF. \nDishonestly issuing a cheque"),
        _row(761, "491", "491. Breach of contract to attend"),
    ]
    fixes = relabels(repair_labels(rows))
    assert {k[-4:]: v["section_number"] for k, v in fixes.items()} == {
        "0758": "489E", "0759": "489E", "0760": "489F"}
    assert fixes["statutes_ppc_1860_0759"]["how"] == "continuation"
    assert "statutes_ppc_1860_0753" not in fixes, "the real s.489 keeps its number"


def test_a_schedule_row_is_never_relabelled_as_a_section():
    """CrPC Schedule II lists PPC offences: '294-A ... Ditto Summons' is not CrPC s.294-A."""
    rows = [_row(1200, "561", "561-A. Saving of inherent power of High Court", "statutes_crpc_1898"),
            _row(1318, "294", "294-\nA \n. Keeping lottery office Ditto Summons", "statutes_crpc_1898"),
            _row(1319, "294", "294-\nB \nOffering of prize Ditto Ditto", "statutes_crpc_1898")]
    out = repair_labels(rows)
    assert out["statutes_crpc_1898_1318"]["how"] == "skipped_out_of_sequence"
    assert "statutes_crpc_1898_1318" not in relabels(out)
    assert "statutes_crpc_1898_1319" not in relabels(out)


def test_a_heading_whose_letter_is_missing_stops_the_carry():
    """'298- Misuse of epithets' is PPC 298-B; the PDF text lost the letter."""
    rows = [_row(429, "298", "298-\nA. \nUse of derogatory remarks"),
            _row(430, "298", "298- Misuse of epithets, descriptions and titles"),
            _row(431, "298", "an a member of the family of the Holy Prophet")]
    out = repair_labels(rows)
    assert relabels(out) == {"statutes_ppc_1860_0429": {"section_number": "298A", "original": "298",
                                                         "how": "heading"}}
    assert out["statutes_ppc_1860_0430"]["how"] == "unresolved_letterless_heading"


def test_carry_never_crosses_statutes():
    rows = [_row(10, "5", "5-\nA. \nSomething", "statutes_aaa"),
            _row(0, "5", "continues here", "statutes_bbb")]
    assert "statutes_bbb_0000" not in relabels(repair_labels(rows))


def test_a_buried_heading_is_reported_for_rechunking():
    assert buried_lettered_headings("62. Something\nlong text\n216-\nB. \nHarbouring") == ["216B"]


def test_the_runtime_fallback_uses_the_same_rule():
    from app.ai import contextual_index, intake_evidence
    assert intake_evidence._LETTERED_HEADER is LETTERED_HEADING
    assert contextual_index._LETTERED_HEADER is LETTERED_HEADING
    assert contextual_index.provision_label({"section_number": "108"}, "108-\nA \nAbetment") == "108-A"


# ── sec_v2: provision splitting at the source ───────────────────────────────
# Shapes copied from the extracted PDF text (pypdf), not idealised.

from app.ai.section_repair import section_label, split_provisions  # noqa: E402

PPC_V2 = (
    "108. Abettor: A person abets an offence...\n"
    "108-\nA \nAbetment in Pakistan of offences outside it: \nA person abets an offence...\n"
    "120-\nA \nDefinition of criminal conspiracy: \nWhen two or more persons agree...\n"
    "120-\nB. \nPunishment of criminal conspiracy: \n(1) Whoever is a party...\n"
    "165-\nA \nPunishment for abetment of offences defined in Sections 161 and 165: \nWhoever abets...\n"
    "165-\nB. \nCertain abettors excepted: \nNothing in Section 165-A shall apply...\n"
    "216-\nA \nPenalty for harbouring robbers or dacoits: \nWhoever, knowing...\n"
    "76   The following was omitted by Penal Code (Amendment) Act, VIII of 1942, S.3 : : \n"
    "216-B. Definition of \"harbour\" in Sections 212, 216 and 216-A. \n  \n"
    "217. Public servant disobeying direction of law: Whoever, being a public servant...\n"
    "298-\nA. \nUse of derogatory remarks, etc., in respect of holy personages: \nWhoever by words...\n"
    "298- Misuse of epithets, descriptions and titles, etc., reserved for certain holy personages or places: \n"
    "B. (1) Any person of the Quadiani group...\n"
    "298-\nC. \nPerson of Quadiani group, etc., calling himself a Muslim: \nAny person...\n"
    "489. Tampering with property mark with intent to cause injury: \nWhoever removes...\n"
    "489-\nF. \nDishonestly issuing a cheque: \nWhoever dishonestly issues a cheque...\n"
)


def _by_section(text):
    return {b["section"]: b for b in split_provisions(text)}


@pytest.mark.parametrize("section", ["108", "108A", "120A", "120B", "165A", "165B", "216A", "216B",
                                     "217", "298A", "298B", "298C", "489", "489F"])
def test_v2_every_listed_provision_is_its_own_block(section):
    secs = [b["section"] for b in split_provisions(PPC_V2)]
    assert secs.count(section) == 1


def test_v2_216b_is_an_omitted_footnote_quote_not_a_live_section():
    b = _by_section(PPC_V2)["216B"]
    assert b["region"] == "footnote_quote" and b["provision_status"] == "omitted"
    assert b["omitted_by"] == "Penal Code (Amendment) Act, VIII of 1942, S.3"
    assert b["text"].startswith("216-B. Definition of")
    assert _by_section(PPC_V2)["216A"]["provision_status"] == "not_recorded"


def test_v2_298b_letter_printed_after_the_title():
    b = _by_section(PPC_V2)["298B"]
    assert b["heading_rule"] == "deferred_letter" and "Misuse of epithets" in b["text"]
    assert "298B" not in _by_section(PPC_V2)["298A"]["text"].replace("-", "")


def test_v2_489_and_489f_never_merge():
    secs = _by_section(PPC_V2)
    assert "cheque" in secs["489F"]["text"] and "cheque" not in secs["489"]["text"]
    assert "property mark" not in secs["489F"]["text"]


def test_v2_337a_deferred_letter_does_not_take_section_337():
    text = ("337. Shajjah: \n(1) Whoever causes, on the head or face...\n"
            "337- Punishment of shajjah: \nA. Whoever, by doing any act with the intention...\n")
    assert [b["section"] for b in split_provisions(text)] == ["337", "337A"]


def test_v2_a_schedule_ii_row_is_never_a_section():
    text = ("565. Order for notifying address of previously convicted offender...\n"
            "SCHEDULE  I \n \nEnactments Repealed\n"
            "SCHEDULE \u2013 II \nExplanatory Note\n"
            "294-\nA \n. Keeping lottery office Ditto Summons Ditto Ditto \n"
            "SCHEDULE - V \nForms\n")
    blocks = split_provisions(text)
    assert [b["section"] for b in blocks if b["region"] == "body"] == ["565"]
    assert all(b["section"] == "" for b in blocks if b["region"] == "schedule")
    assert [b["schedule"] for b in blocks if b["region"] == "schedule"] == ["I", "II", "V"]
    assert not any(b["section"] == "294A" for b in blocks)


def test_v2_the_contents_line_is_not_a_schedule_start():
    text = "SCHEDULE I.-      [Repealed]. \n1. Short title: This Act may be called...\n"
    assert not any(b["region"] == "schedule" for b in split_provisions(text))


def test_v2_one_line_lettered_heading_is_split():
    text = ("22. Appointment of Justices of the Peace: The Provincial Government may...\n"
            "22-A.  Powers of Justices of the Peace:  A Justice of the Peace for any local area...\n")
    assert [b["section"] for b in split_provisions(text)] == ["22", "22A"]


def test_v2_continuation_chunks_inherit_their_provision(ingest):
    long_tail = "Whoever dishonestly issues a cheque towards repayment of a loan. " * 30
    text = "489-\nE. \nMaking documents resembling currency-notes: (1) Whoever makes...\n" \
           "489-\nF. \nDishonestly issuing a cheque: \n" + long_tail + "\n490. Omitted.\n"
    chunks = ingest.make_chunks(text, "PPC 1860", "criminal", "PAKISTAN PENAL CODE.pdf")
    f_chunks = [c for c in chunks if "cheque" in c["content"]]
    assert len(f_chunks) > 1, "the provision must be long enough to window-split"
    assert {c["meta"]["section_number"] for c in f_chunks} == {"489F"}
    assert all(c["meta"]["split_version"] == "section-split-v2" for c in chunks)


def test_v2_ingest_records_provision_metadata(ingest):
    chunks = ingest.make_chunks(PPC_V2, "PPC 1860", "criminal", "PAKISTAN PENAL CODE.pdf")
    quoted = [c for c in chunks if c["meta"]["section_number"] == "216B"]
    assert quoted and quoted[0]["meta"]["provision_status"] == "omitted"
    assert quoted[0]["meta"]["source_region"] == "footnote_quote"


def test_v2_section_label_form():
    assert section_label("489F") == "489-F" and section_label("489") == "489" and section_label("") == ""


def test_v2_gate_drops_a_source_marked_omitted_provision():
    from app.ai.nodes import intake_evidence_gate_node as gate
    kept, rec = gate.decide(chunks=[{"statute": "PPC 1860", "section_number": "216B", "province": "federal",
                                     "content": "216-B. Definition of harbour", "provision_status": "omitted"}],
                            retrieval_error=False, province="punjab",
                            user_text="someone is hiding a robber in his house near me", relevance_score=0.8)
    assert kept == [] and rec["dropped"]["omitted_section"] == 1


_PPC_PDF = Path(r"C:\Users\The Laptop Hut\Desktop\specific_case_data\PAKISTAN PENAL CODE.pdf")


@pytest.mark.skipif(not _PPC_PDF.exists(), reason="source PDF not on this machine")
def test_v2_the_real_ppc_source_yields_every_expected_provision_once(ingest):
    blocks = split_provisions(ingest.extract_text(_PPC_PDF))
    secs = [b["section"] for b in blocks if b["region"] in ("body", "footnote_quote")]
    for s in ["108A", "120A", "120B", "165A", "165B", "216A", "216B", "298A", "298B", "298C",
              "337A", "489", "489A", "489B", "489C", "489D", "489E", "489F"]:
        assert secs.count(s) == 1, s
    quoted = sorted(b["section"] for b in blocks if b["region"] == "footnote_quote")
    assert quoted == sorted(["13", "15", "18", "58", "61", "138A", "216B", "226", "366"])
