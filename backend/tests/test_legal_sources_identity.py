"""Source and provision identity parsing (app/ai/legal_sources/identity.py).

The corpus has stored CPC Order rules as "sections" and Limitation Act schedule
articles as section numbers. These tests pin the five provision kinds apart,
and the instrument numbers (Act, S.R.O., circular) that registry ids rest on.
Pure: no database, no Chroma.
"""
import pytest

from app.ai.legal_sources.identity import (
    classify_reference, int_to_roman, parse_circular, parse_instrument_number,
    parse_sro, roman_to_int,
)


@pytest.mark.parametrize("numeral,value", [("I", 1), ("IV", 4), ("IX", 9), ("XIV", 14),
                                           ("XXVII", 27), ("XXXIX", 39), ("XLVII", 47)])
def test_roman_numerals_round_trip(numeral, value):
    assert roman_to_int(numeral) == value
    assert int_to_roman(value) == numeral


@pytest.mark.parametrize("bad", ["", "IIII", "VX", "ABC", "IC"])
def test_malformed_numerals_are_refused(bad):
    assert roman_to_int(bad) is None


# ── provision kinds that share digits ─────────────────────────────────────────

@pytest.mark.parametrize("text,key", [
    ("Order XXXIX Rule 1 CPC", "O39-R1"),
    ("O. 39 r. 2", "O39-R2"),
    ("under Order 7, Rule 11", "O7-R11"),
    ("Order XXVII-A Rule 1", "O27A-R1"),       # filed as XXVII in the base index
    ("Order XXI Rule 58-A", "O21-R58A"),
])
def test_cpc_order_rules_are_never_sections(text, key):
    ref = classify_reference(text)
    assert ref["kind"] == "order_rule" and ref["key"] == key


def test_order_rule_label_is_canonical():
    assert classify_reference("O. 39 r. 2")["label"] == "Order XXXIX Rule 2"
    assert classify_reference("Order XXVII-A Rule 1")["label"] == "Order XXVII-A Rule 1"


@pytest.mark.parametrize("text,key,sub", [
    ("section 489-F PPC", "s489F", None),
    ("s. 7(2) of the Court-fees Act", "s7", 2),
    ("u/s 22-A CrPC", "s22A", None),
    ("Section 26A PECA", "s26A", None),
])
def test_sections_keep_their_letters_and_subsections(text, key, sub):
    ref = classify_reference(text)
    assert ref["kind"] == "section" and ref["key"] == key and ref["subsection"] == sub


def test_a_schedule_article_is_not_a_constitutional_article():
    sched = classify_reference("Article 58 of the First Schedule to the Limitation Act")
    assert sched["kind"] == "schedule_entry" and sched["key"] == "S1-A58"
    const = classify_reference("Article 199 of the Constitution")
    assert const["kind"] == "article" and const["key"] == "A199"
    assert classify_reference("Article 10A")["key"] == "A10A"


def test_a_court_practice_rule_is_its_own_kind():
    ref = classify_reference("Lahore High Court Rules and Orders, Volume V, Chapter 1, Part A, Rule 5")
    assert ref["kind"] == "court_rule" and ref["key"] == "V5-C1-PA-R5"
    assert classify_reference("Vol. III, Chapter 24-B, Rule 3")["key"] == "V3-C24B-R3"


def test_nothing_recognisable_returns_none():
    assert classify_reference("the tenant has not paid rent") is None
    assert classify_reference("") is None


# ── instrument numbers ────────────────────────────────────────────────────────

def test_act_numbers_with_and_without_province():
    assert parse_instrument_number("The Prevention of Electronic Crimes (Amendment) Act, 2025 (Act No. II of 2025)") == {
        "kind": "act", "number": 2, "year": 2025, "jurisdiction": None}
    assert parse_instrument_number("Punjab Act XIV of 2018") == {
        "kind": "act", "number": 14, "year": 2018, "jurisdiction": "punjab"}
    assert parse_instrument_number("Khyber Pakhtunkhwa Act No. 5 of 2020")["jurisdiction"] == "kp"
    assert parse_instrument_number("Sindh Payment of Wages Act, 2015 (VI of 2017)") == {
        "kind": "act", "number": 6, "year": 2017, "jurisdiction": None}
    # A missing provincial prefix is UNKNOWN, never assumed federal.
    assert parse_instrument_number("Act No. IX of 2026")["jurisdiction"] is None
    assert parse_instrument_number("no number here") is None


@pytest.mark.parametrize("text,key", [
    ("S.R.O. 169 (I)/2025 dated 18-02-2025", "SRO-169(I)/2025"),
    ("S.R.O1829(I)/2026", "SRO-1829(I)/2026"),
    ("SRO No. 1430(I)/2026", "SRO-1430(I)/2026"),
])
def test_sro_numbers(text, key):
    assert parse_sro(text)["key"] == key


def test_circulars_are_keyed_by_department():
    a = parse_circular("BPRD Circular No. 03 of 2024")
    b = parse_circular("FE Circular No. 03 of 2024")
    assert a["key"] == "BPRD-3/2024" and b["key"] == "FE-3/2024" and a["key"] != b["key"]
    assert parse_circular("PSD Circular No. 1/2025")["key"] == "PSD-1/2025"
    assert parse_circular("circular") is None
