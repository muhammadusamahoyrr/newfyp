"""Foreign (Indian) law presented as Pakistani authority (lawyer research,
2026-10-14).

Live probe R3.2: a Pakistani dishonoured-cheque matter was answered with a
reference to "Section 138 of the Negotiable Instruments Act" -- the Indian
cheque-dishonour offence (inserted in India in 1988; Pakistan's corresponding
offence is PPC s.489-F). The model draws on far more Indian than Pakistani
legal text, so this is a CLASS of error, not one phrase.

Detection is a set of India-SPECIFIC markers -- statutes that exist only in
India or only in their Indian form/year, Indian courts, Indian-only offence
numbering -- deliberately NOT the bare word "Indian": Pakistani statutes are
full of "Substituted by the Indian Limitation (Amendment) Act, 1922", because
pre-1947 Indian Acts are Pakistani law.

Applied only when the question does not ask for comparative/foreign law. A
sentence carrying a marker is removed and one plain note says so; a marker
inside parentheses removes just the parenthetical. Never adds law.
"""
from __future__ import annotations

import re

_F = re.IGNORECASE
_MARKERS = [
    # Statutes that are Indian, or Indian in this form/year.
    r"\bIndian Penal Code\b", r"\bI\.?P\.?C\.?\b(?!\s*-)",
    r"\bBharatiya\b", r"\bBNSS?\b", r"\bBSA\s*,?\s*2023\b",
    r"\b(?:Code of Criminal Procedure|Cr\.?\s*P\.?\s*C\.?)\s*,?\s*1973\b",
    r"\bLimitation Act\s*,?\s*1963\b", r"\bSpecific Relief Act\s*,?\s*1963\b",
    r"\bArbitration and Conciliation Act\b", r"\bHindu (?:Marriage|Succession|Adoptions and Maintenance) Act\b",
    r"\bIndian (?:Evidence|Contract|Easements) Act\s*,?\s*18\d\d\b(?![^.]{0,40}\b(?:Pakistan|adapted)\b)",
    r"\bInformation Technology Act\s*,?\s*2000\b", r"\bConsumer Protection Act\s*,?\s*(?:1986|2019)\b",
    # India's cheque-dishonour offence (Pakistan: PPC 489-F).
    r"\bSection\s*138\b[^.\n]{0,80}\bNegotiable Instruments\b",
    r"\bNegotiable Instruments Act\b[^.\n]{0,60}\b(?:Section|s\.)\s*138\b",
    r"\bN\.?\s?I\.?\s*Act\b[^.\n]{0,30}\b138\b|\b138\b[^.\n]{0,30}\bN\.?\s?I\.?\s*Act\b",
    # Indian courts.
    r"\bSupreme Court of India\b",
    r"\b(?:Delhi|Bombay|Madras|Calcutta|Allahabad|Karnataka|Kerala|Gujarat|Rajasthan|Punjab and Haryana)\s+High Court\b",
    r"\bAIR\s+\d{4}\s+SC\b", r"\bSCC\b",
]
_MARKER = re.compile("|".join(f"(?:{m})" for m in _MARKERS), _F)
_COMPARATIVE = re.compile(r"\b(?:india|indian|comparative|compare|foreign|other jurisdictions?)\b|بھارت|انڈیا", _F)
_PAREN = re.compile(r"\s*\([^()]*\)")
_SENT = re.compile(r"(?<=[.!?۔])\s+")

NOTE_EN = ("Note: a reference to Indian law was removed from this answer. It addresses Pakistani law only; "
           "ask explicitly if you want a comparative view.")
NOTE_UR = "نوٹ: اس جواب سے بھارتی قانون کا حوالہ ہٹا دیا گیا ہے۔ یہ صرف پاکستانی قانون سے متعلق ہے۔"


def asks_comparative(question: str) -> bool:
    return bool(_COMPARATIVE.search(question or ""))


def markers_in(text: str) -> list[str]:
    return [m.group(0) for m in _MARKER.finditer(text or "")]


def strip_foreign(text: str, question: str, urdu: bool = False) -> tuple[str, list[str]]:
    """Remove foreign-law references unless comparative law was asked for.
    Returns (text, removed fragments)."""
    if asks_comparative(question) or not _MARKER.search(text or ""):
        return text, []
    removed: list[str] = []
    out_lines = []
    for line in (text or "").split("\n"):
        # A marker inside parentheses: drop the parenthetical only.
        def _paren(m):
            if _MARKER.search(m.group(0)):
                removed.append(m.group(0).strip())
                return ""
            return m.group(0)
        line = _PAREN.sub(_paren, line)
        kept = []
        for part in _SENT.split(line):
            if _MARKER.search(part):
                removed.append(part.strip())
            else:
                kept.append(part)
        if kept or not line.strip():
            out_lines.append(" ".join(kept) if kept else line)
    out = "\n".join(out_lines).strip()
    note = NOTE_UR if urdu else NOTE_EN
    return (f"{out}\n\n{note}" if out else note), removed
