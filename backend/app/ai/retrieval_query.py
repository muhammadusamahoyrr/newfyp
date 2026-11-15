"""English retrieval query for a client chat question (2026-10-21).

The statute corpus is English. A short client question in Urdu script or Roman
Urdu ("خلع کیا ہے؟", "chori ki saza kya hai?") or one opening with a length word
("Briefly, what is khula?") was searched and SCORED with its own words:
  * BM25 has nothing to match in Urdu script, and the Roman question words
    ("kise", "kehte") are not statute words;
  * the scorer weights a query term found in no candidate as an unmet
    requirement (scoring._term_weights), so "briefly", "کیا", "kehte" held the
    relevance score down even when Family Courts Act s.10 was retrieved.
Measured offline (neutral LLM grade): "Briefly, what is khula?" 0.44 -> 0.81,
"خلع کیا ہے؟" 0.45 -> 0.81, "chori ki saza kya hai?" 0.39 -> 0.78 with PPC
s.379 retrieved. Fusing the raw Urdu / Roman branch back in (RRF) LOWERED both
the score and the top results, so a non-English question is searched with the
English query alone.

Rules:
  * deterministic: a fixed term map (ai/legal_terms.py plus the few question
    words below), no model;
  * RETRIEVAL and SCORING only. The user's words stay in state["query"], and
    generation, the LLM grader, statute affinity and the cache read those;
  * nothing the user stated is dropped from an English question: only a
    leading length word is removed. Statute names, section numbers and digits
    are always kept;
  * a term names a legal concept, never a section;
  * returns None when it has nothing to add, so every other question keeps the
    existing path exactly.
"""
from __future__ import annotations

import re

from app.ai.legal_terms import _ROMAN, legal_terms

VERSION = "retrieval-query-v1"

# Question words a definition asks with, not covered by legal_terms (whose map
# is shared with intake and stays as it is).
_EXTRA_URDU: dict[str, str] = {
    "سزا": "punishment",
    "جرمانہ": "fine",
    "قتل": "murder qatl",
    "دفعہ": "section",
    "نکاح": "nikah marriage",
    "مہر": "dower",
    "کرایہ دار": "tenant",
    "کرایہ": "rent",
}
_EXTRA_ROMAN: dict[str, str] = {
    "saza": "punishment",
    "sazaa": "punishment",
    "jurmana": "fine",
    "qatl": "murder qatl",
    "dafa": "section",
    "nikah": "nikah marriage",
    "mehr": "dower",
    "kirayedar": "tenant",
    "kiraya": "rent",
}

_LENGTH_PREFIX = re.compile(
    r"^\s*(?:briefly|in\s+short|shortly|quickly|simply|in\s+simple\s+(?:words|terms)|in\s+detail|"
    r"mukhtasar(?:an)?|short\s+mein)\s*[,:\-]?\s*", re.IGNORECASE)

_URDU_SCRIPT = re.compile(r"[؀-ۿ]")
# Roman-Urdu function words: they carry no legal term and no fact.
_ROMAN_FUNCTION = frozenset("""
kya kia hai hain he hota hoti hote ki ka ke ko se mein me main aur ya kise kisay kehte kahte
matlab batao bataen batayein btao bataiye kaise kaisay kab kahan kitni kitna kitne liye lie
wala wali walay bare baray mutaliq mutalliq hum ap aap tum yeh ye woh wo
""".split())
# Enough of these and the question is Roman Urdu, whatever triage labelled it
# ("khula kise kehte hain" came back as "en").
_ROMAN_MARKERS = frozenset("kya kia hai hain kise kehte kahte hota hoti hote ki ka ke ko mein kaise batao matlab".split())
# Single-word Roman glossary, legal_terms' and this module's.
_ROMAN_ALL = {k: v for k, v in (*_ROMAN.items(), *_EXTRA_ROMAN.items()) if " " not in k}
# Kept from an Urdu-script question: statute abbreviations and section numbers.
_LATIN_OR_NUMBER = re.compile(r"[A-Za-z][A-Za-z.\-]*|\d+(?:[-‑][A-Za-z])?")


def _urdu_terms(text: str) -> list[str]:
    return [term for word, term in _EXTRA_URDU.items() if word in text]


def _dedupe(terms: list[str]) -> list[str]:
    out: list[str] = []
    for t in terms:
        if t and t not in out:
            out.append(t)
    return out


def is_roman_urdu(text: str) -> bool:
    words = re.findall(r"[a-z]+", (text or "").lower())
    return sum(w in _ROMAN_MARKERS for w in words) >= 2


def build(query: str | None, normalized: str | None = None) -> str | None:
    """The English retrieval/scoring query for `query`, or None to keep the
    existing behaviour. `normalized` is triage's Urdu-script rendering of a
    Roman-Urdu question, read for terms only.

    Urdu-script and Roman-Urdu questions are rewritten only when they are
    GENERAL ("what is X?"): the rewrite keeps legal terms, statute names and
    numbers but not the rest of the sentence, and a person's own matter must
    keep every fact it states. Those keep the existing path."""
    from app.ai.graph.edges import is_general_question

    raw = (query or "").strip()
    if not raw:
        return None
    text = _LENGTH_PREFIX.sub("", raw).strip() or raw
    stripped = text != raw

    if _URDU_SCRIPT.search(text):
        terms = _dedupe(legal_terms(text) + _urdu_terms(text))
        if not terms or not is_general_question(raw):
            return None
        if "section" in terms:                       # "دفعہ 379" -> "section 379"
            terms = ["section"] + [t for t in terms if t != "section"]
            return " ".join(_dedupe(terms[:1] + _LATIN_OR_NUMBER.findall(text) + terms[1:]))
        return " ".join(_dedupe(_LATIN_OR_NUMBER.findall(text) + terms))

    if is_roman_urdu(text):
        if not is_general_question(raw):
            return None
        # In order: function words go, a glossary word becomes its English
        # term ("dafa 302 PPC ki saza" -> "section 302 PPC punishment").
        out = []
        for tok in _LATIN_OR_NUMBER.findall(text):
            low = tok.lower()
            if low in _ROMAN_FUNCTION:
                continue
            out.append(_ROMAN_ALL.get(low, tok))
        terms = legal_terms(text) + _urdu_terms(normalized or "")
        if not any(t in _ROMAN_ALL.values() for t in out) and not terms:
            return None                              # no legal term to anchor on
        return " ".join(_dedupe(out + terms))

    # English: the user's sentence, a leading length word removed, plus any
    # English term it lacks. Nothing the user wrote is dropped.
    extra = [t for t in _dedupe(legal_terms(text)) if t.lower() not in text.lower()]
    if not extra and not stripped:
        return None
    return f"{text} {' '.join(extra)}".strip()


def for_state(state: dict) -> str | None:
    """build() for the client chat surface; None everywhere else and when a
    case-derived supplement already drives retrieval."""
    if state.get("surface") != "client" or state.get("retrieval_query_supplement"):
        return None
    if (state.get("retrieval_policy") or {}).get("purpose") == "intake":
        return None
    return build(state.get("query"), state.get("normalized_query"))
