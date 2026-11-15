"""Identity parsing for Pakistani legal sources. Pure functions.

Two jobs, kept apart because mixing them is how this corpus went wrong before:

1. INSTRUMENT identity -- the number an instrument is known by:
     "Act No. II of 2025", "Punjab Act XIV of 2018", "Ordinance No. V of 2020",
     "S.R.O. 169(I)/2025", "BPRD Circular No. 03 of 2024".
2. PROVISION identity -- WHICH part of an instrument a reference names. Five
   kinds that share digits and must never share a key:
     section        "section 489-F", "s. 7(2)", "u/s 22-A"
     order_rule     "Order XXXIX Rule 1", "O. 39 r. 2", "Order XXVII-A Rule 1"  (CPC)
     schedule_entry "Article 58 of the First Schedule"  (e.g. Limitation Act)
     article        "Article 199"  (Constitution)
     court_rule     "Volume V, Chapter 1, Part A, Rule 5"  (High Court rules)
   The base index once stored CPC Order rules as "sections" and Limitation Act
   schedule articles as section numbers; a reference parser that cannot tell
   these apart reproduces that defect at query time.
"""
from __future__ import annotations

import re

_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def roman_to_int(numeral: str) -> int | None:
    """"XXXIX" -> 39. None for anything that is not a well-formed numeral."""
    s = (numeral or "").strip().upper()
    if not s or any(c not in _ROMAN for c in s):
        return None
    total = 0
    for i, c in enumerate(s):
        v = _ROMAN[c]
        total += -v if i + 1 < len(s) and _ROMAN[s[i + 1]] > v else v
    # Reject non-canonical forms ("IIII", "VX") by round-tripping.
    return total if int_to_roman(total) == s else None


def int_to_roman(n: int) -> str:
    pairs = [(100, "C"), (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
             (5, "V"), (4, "IV"), (1, "I")]
    out = []
    for v, sym in pairs:
        while n >= v:
            out.append(sym)
            n -= v
    return "".join(out)


def _number(token: str) -> int | None:
    token = (token or "").strip()
    return int(token) if token.isdigit() else roman_to_int(token)


# ── instrument identity ──────────────────────────────────────────────────────

_PROVINCES = {
    "punjab": "punjab", "sindh": "sindh", "khyber pakhtunkhwa": "kp", "kp": "kp",
    "k.p.": "kp", "nwfp": "kp", "n.-w.f.p.": "kp", "balochistan": "balochistan",
    "baluchistan": "balochistan",
}
_INSTRUMENT_NO = re.compile(
    r"(?i)\b(?:(Punjab|Sindh|Khyber\s+Pakhtunkhwa|KP|NWFP|Balochistan|Baluchistan)\s+)?"
    r"(Act|Ordinance|Order|Regulation)\s*(?:No\.?\s*)?([IVXLC]+|\d{1,3})\s+of\s+((?:19|20)\d{2})\b")
# "(VI of 2017)" -- the number in brackets after a title.
_BRACKETED_NO = re.compile(r"\(\s*([IVXLC]+|\d{1,3})\s+of\s+((?:19|20)\d{2})\s*\)")


def parse_instrument_number(text: str) -> dict | None:
    """The first Act/Ordinance number in `text`, or None.

    {"kind": "act", "number": 2, "year": 2025, "jurisdiction": None|"punjab"...}
    A provincial prefix is recorded when written; its ABSENCE does not mean
    federal (a Sindh Act is often written "Act No. VI of 2017" in its own
    gazette), so `jurisdiction` is None, not "federal", in that case.
    """
    t = text or ""
    m = _INSTRUMENT_NO.search(t)
    if m:
        num = _number(m.group(3))
        if num is None:
            return None
        prov = _PROVINCES.get(" ".join((m.group(1) or "").lower().split())) if m.group(1) else None
        return {"kind": m.group(2).lower(), "number": num, "year": int(m.group(4)), "jurisdiction": prov}
    m = _BRACKETED_NO.search(t)
    if m and (num := _number(m.group(1))) is not None:
        return {"kind": "act", "number": num, "year": int(m.group(2)), "jurisdiction": None}
    return None


# "S.R.O. 169(I)/2025", "SRO 1829(I)/2026", "S.R.O1829(I)/2026", "SRO No. 1430(I)/2026"
_SRO = re.compile(r"(?i)\bS\.?\s*R\.?\s*O\.?\s*(?:No\.?\s*)?(\d{1,5})\s*\(\s*([IVX]+)\s*\)\s*/\s*((?:19|20)\d{2})\b")


def parse_sro(text: str) -> dict | None:
    """{"number": 169, "part": "I", "year": 2025, "key": "SRO-169(I)/2025"} or None."""
    m = _SRO.search(text or "")
    if not m:
        return None
    number, part, year = int(m.group(1)), m.group(2).upper(), int(m.group(3))
    return {"number": number, "part": part, "year": year, "key": f"SRO-{number}({part})/{year}"}


# SBP circulars are numbered within a DEPARTMENT and year: "BPRD Circular No. 03
# of 2024" and "FE Circular No. 03 of 2024" are different instruments.
_CIRCULAR = re.compile(
    r"(?i)\b([A-Z][A-Z&]{1,7})\s+Circular(?:\s+Letter)?\s*(?:No\.?\s*)?(\d{1,3})\s*(?:of|/)\s*((?:19|20)\d{2})\b")


def parse_circular(text: str) -> dict | None:
    """{"department": "BPRD", "number": 3, "year": 2024, "key": "BPRD-3/2024"} or None."""
    m = _CIRCULAR.search(text or "")
    if not m:
        return None
    dept, number, year = m.group(1).upper(), int(m.group(2)), int(m.group(3))
    return {"department": dept, "number": number, "year": year, "key": f"{dept}-{number}/{year}"}


# ── provision identity ───────────────────────────────────────────────────────

_ORDER_RULE = re.compile(
    r"(?i)\b(?:Order|O\.)\s*([IVXLC]+|\d{1,2})(?:\s*-?\s*(?-i:([A-Z]))\b)?\s*,?\s*"
    r"(?:Rule|R\.|r\.|rr\.)\s*(\d{1,3})(?:\s*-?\s*(?-i:([A-Z]))\b)?")
_COURT_RULE = re.compile(
    r"(?i)\bVol(?:ume|\.)?\s*([IVX]+|\d)\s*,?\s*Chapter\s*(\d{1,2}(?:\s*-?\s*[A-Z])?)\s*,?\s*"
    r"(?:Part\s*([A-Z])\s*,?\s*)?Rule\s*(\d{1,3})")
_SCHEDULE_ENTRY = re.compile(
    r"(?i)\bArt(?:icle|\.)?\s*(\d{1,3})(?:\s*-?\s*(?-i:([A-Z]))\b)?\s+(?:of|in)\s+the\s+"
    r"(First|Second|Third|Fourth|Fifth|Sixth|[IVX]+)\s+Schedule")
# The letter suffix is UPPERCASE and attached ("10A", "489-F"): "Article 199 of"
# is Article 199, not 199-OF.
_ARTICLE = re.compile(r"(?i)\bArt(?:icle|\.)?\s*(\d{1,3})(?:-?(?-i:([A-Z]{1,2}))\b)?(?:\s*\((\d{1,2})\))?")
_SECTION = re.compile(
    r"(?i)(?:\bsection|\bsec\.|\bs\.|\bu/s|\bss\.)\s*(\d{1,3})(?:\s*-?\s*(?-i:([A-Z]{1,2}))\b)?(?:\s*\((\d{1,2})\))?")


def _letter(m: re.Match, i: int) -> str:
    return (m.group(i) or "").upper()


def classify_reference(text: str) -> dict | None:
    """What kind of provision `text` names, and its normalised key. None if none.

    Checked most-specific first: an Order/Rule and a schedule entry both CONTAIN
    something that looks like a rule or an article, and the plain-article and
    plain-section patterns would otherwise claim them.
    """
    t = text or ""
    m = _ORDER_RULE.search(t)
    if m:
        order = _number(m.group(1))
        if order is not None:
            o_letter, rule, r_letter = _letter(m, 2), int(m.group(3)), _letter(m, 4)
            label = f"Order {int_to_roman(order)}{'-' + o_letter if o_letter else ''} Rule {rule}{'-' + r_letter if r_letter else ''}"
            return {"kind": "order_rule", "order": order, "order_letter": o_letter or None,
                    "rule": rule, "rule_letter": r_letter or None, "label": label,
                    "key": f"O{order}{o_letter}-R{rule}{r_letter}"}
    m = _COURT_RULE.search(t)
    if m:
        vol = _number(m.group(1))
        chapter = re.sub(r"\s*-?\s*", "", m.group(2)).upper()
        part = (m.group(3) or "").upper() or None
        rule = int(m.group(4))
        return {"kind": "court_rule", "volume": vol, "chapter": chapter, "part": part, "rule": rule,
                "label": f"Vol. {int_to_roman(vol or 0)}, Ch. {chapter}{', Part ' + part if part else ''}, Rule {rule}",
                "key": f"V{vol}-C{chapter}{'-P' + part if part else ''}-R{rule}"}
    m = _SCHEDULE_ENTRY.search(t)
    if m:
        art, letter, sched = int(m.group(1)), _letter(m, 2), m.group(3)
        sched_n = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
                   "sixth": 6}.get(sched.lower(), roman_to_int(sched))
        return {"kind": "schedule_entry", "schedule": sched_n, "article": art,
                "article_letter": letter or None,
                "label": f"Schedule {int_to_roman(sched_n or 0)}, Article {art}{'-' + letter if letter else ''}",
                "key": f"S{sched_n}-A{art}{letter}"}
    m = _ARTICLE.search(t)
    if m:
        art, letter, clause = int(m.group(1)), _letter(m, 2), m.group(3)
        return {"kind": "article", "article": art, "letter": letter or None,
                "clause": int(clause) if clause else None,
                "label": f"Article {art}{letter}{f'({clause})' if clause else ''}",
                "key": f"A{art}{letter}"}
    m = _SECTION.search(t)
    if m:
        sec, letter, sub = int(m.group(1)), _letter(m, 2), m.group(3)
        return {"kind": "section", "section": sec, "letter": letter or None,
                "subsection": int(sub) if sub else None,
                "label": f"section {sec}{'-' + letter if letter else ''}{f'({sub})' if sub else ''}",
                "key": f"s{sec}{letter}"}
    return None
