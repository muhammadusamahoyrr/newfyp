"""Which answer safeguards apply to a turn, decided in ONE place (2026-10-14).

Two surfaces run the same chat graph:
  * client chat   -- `surface = "client"` (set by the client socket). Its
    safeguards (exact provision, period support, misattribution, marker /
    hyphen handling) shipped earlier and are ALWAYS on there; unchanged here.
  * lawyer research -- `surface = "research"` (set by the authenticated
    /ai/research route, never by the browser). The same safeguards plus the
    research-only ones (versioned identity index, Urdu citation forms, issue
    relevance, foreign-law guard, research follow-ups) apply ONLY when
    `RESEARCH_ANSWER_SAFEGUARDS` is on. Off = the previous research behaviour,
    kept as ROLLBACK -- not a statement that those answers are reliable.

Every node asks `on(state)` / `research_on(state)` rather than testing the
surface itself, so the two surfaces cannot drift apart silently and a new
surface gets nothing by accident.
"""
from __future__ import annotations

import re

SURFACE_CLIENT = "client"
SURFACE_RESEARCH = "research"
RESEARCH_GUARD_VERSION = "research-guard-v1"
RESEARCH_INDEX_VARIANT = "research_ident"   # resolved per collection in retriever


def research_on(state: dict) -> bool:
    from app.core.config import settings
    return state.get("surface") == SURFACE_RESEARCH and bool(settings.research_answer_safeguards)


def on(state: dict) -> bool:
    """The shared answer safeguards: always for client chat, flag-gated for research."""
    return state.get("surface") == SURFACE_CLIENT or research_on(state)


# ── citation text for MATCHING (the displayed answer is never rewritten) ──────

_DASHES = str.maketrans({**dict.fromkeys("‐‑‒–—", "-"),
                         **dict.fromkeys("    ", " ")})
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_URDU_LETTERS = {"اے": "A", "بی": "B", "سی": "C", "ڈی": "D", "ای": "E", "ایف": "F", "جی": "G", "ایچ": "H"}
# Act names as Urdu answers write them. An Urdu citation resolves ONLY with its
# Act: a bare "دفعہ 302" names no statute and stays unresolved.
_URDU_ACTS = (
    (re.compile(r"تعزیراتِ?\s*پاکستان|پاکستان\s*پینل\s*کوڈ|پی\s*پی\s*سی"), "PPC"),
    (re.compile(r"ضابطہ\s*فوجداری|سی\s*آر\s*پی\s*سی"), "CrPC"),
    (re.compile(r"ضابطہ\s*دیوانی|(?<!آر\s)سی\s*پی\s*سی"), "CPC"),
)
_SECTION_WORD = re.compile(r"دفعہ|\b(?:dafa|dafaa|daf'a|dafah)\b|سیکشن", re.IGNORECASE)
_URDU_LETTERED = re.compile(r"(\d{1,3})\s*-?\s*(" + "|".join(sorted(_URDU_LETTERS, key=len, reverse=True))
                            + r")(?![؀-ۿ])")
# Urdu word order "PPC کی Section 302" -> "Section 302 PPC"
_URDU_ORDER = re.compile(r"\b(PPC|CrPC|CPC)\s+(?:کی|کے|کا)\s+(Section\s+\d{1,3}(?:-[A-Z])?)")


def urdu_citation_forms(text: str) -> str:
    """Rewrite Urdu / Roman-Urdu citation forms into the English forms the
    citation parser reads ("پی پی سی دفعہ 302" -> "PPC Section 302")."""
    t = (text or "").translate(_DIGITS)
    t = _URDU_LETTERED.sub(lambda m: f"{m.group(1)}-{_URDU_LETTERS[m.group(2)]}", t)
    for pattern, act in _URDU_ACTS:
        t = pattern.sub(f" {act} ", t)
    t = _SECTION_WORD.sub(" Section ", t)
    t = _URDU_ORDER.sub(r"\2 \1", t)
    return t


def citation_text(text: str, state: dict) -> str:
    """The text citations are MATCHED on. Client chat: dash/space normalised
    (as before). Research with safeguards: also Urdu citation forms. Anything
    else: unchanged."""
    from app.ai import period_support
    if state.get("surface") == SURFACE_CLIENT:
        return period_support.normalise(text)            # exactly as before
    if research_on(state):
        return urdu_citation_forms(period_support.normalise(text))
    return text or ""


def restore_claim_texts(claims: list[dict], original: str, matched_on: str) -> list[dict]:
    """Show each claim in the answer's ORIGINAL wording. Claims are split from
    the normalised copy (citation matching needs it); normalisation rewrites
    words, never sentence punctuation, so the two split identically. If they
    ever do not, the normalised text is kept rather than guessed."""
    from app.ai.answer_citations import _SENTENCE_SPLIT, attach_trailing_markers
    if original == matched_on:
        return claims
    a = [p.strip() for p in attach_trailing_markers(_SENTENCE_SPLIT.split(original or ""))]
    b = [p.strip() for p in attach_trailing_markers(_SENTENCE_SPLIT.split(matched_on or ""))]
    if len(a) != len(b):
        return claims
    back = {nb: na for na, nb in zip(a, b) if nb}
    for claim in claims:
        claim["text"] = back.get(claim.get("text", "").strip(), claim.get("text", ""))
    return claims
