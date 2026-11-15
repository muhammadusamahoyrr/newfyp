"""Input fact fidelity (Batch 6A, 2026-10-12).

Checks the generated summary/actions against what the CLIENT supplied: their
story, their answers, their documents. Named for what it is -- fidelity to the
input -- not "truth": the system cannot know whether the client's account is
true, only whether the analysis says what the client said.

Deterministic and deliberately conservative. Two checks:

  unsupported_number  an amount, quantity or date in the SUMMARY that appears
                      in none of the client's material ("Rs. 250,000" when the
                      client never gave a figure). Law identifiers (section
                      numbers, statute years) are removed first.
  negation_inverted   a fact the client NEGATED ("no written agreement")
                      mentioned in the analysis with no negation nearby.

"unchecked" when there is nothing to check against -- never "consistent".
"""
from __future__ import annotations

import re

# Honest scope: numbers + basic negation only, not general fact fidelity.
FIDELITY_VERSION = "input-fact-fidelity-v1-limited"

_LAW_REF = re.compile(
    r"\b(?:section|sections|sec\.|s\.|article|articles|art\.|order|rule|chapter|clause)\s*[\w\-()./]+",
    re.IGNORECASE)
_STATUTE_YEAR = re.compile(r"\b(?:act|ordinance|order|code|constitution|rules?)\b[^.\n]{0,40}?\b(1[6-9]\d\d|20\d\d)\b",
                           re.IGNORECASE)
_NUMBER = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)(?![\w])")
_NEGATORS = re.compile(r"\b(no|not|without|never|none|lack|lacks|absence|absent|nahi|nahin|nai)\b|نہیں|بغیر",
                       re.IGNORECASE)
_STOP = {"exists", "exist", "the", "a", "an", "of", "is", "was", "has", "have", "any", "client"}


def _digits(n: str) -> str:
    return n.replace(",", "").lstrip("0") or "0"


def _numbers(text: str) -> set[str]:
    cleaned = _STATUTE_YEAR.sub(" ", _LAW_REF.sub(" ", text or ""))
    return {_digits(m.group(1)) for m in _NUMBER.finditer(cleaned)
            if len(_digits(m.group(1))) > 1 or m.group(1) not in {"0", "1"}}


def _fact_terms(fact_key: str) -> list[str]:
    words = [w for w in fact_key.split("_") if w and w not in _STOP]
    return words


def check(*, summary: str, actions: list[str] | None, understanding: dict | None,
          extra_sources: list[str] | None = None) -> dict:
    u = understanding or {}
    sources = [u.get("original_story") or "", u.get("desired_outcome") or ""]
    sources += [s.get("answer") or "" for s in u.get("statements") or []]
    sources += list(extra_sources or [])
    source_text = "\n".join(s for s in sources if s)
    analysis_text = "\n".join([summary or "", *[a for a in actions or [] if a]])
    if not source_text.strip() or not analysis_text.strip():
        return {"version": FIDELITY_VERSION, "status": "unchecked", "issues": []}

    issues = []
    # Numbers are checked in the SUMMARY only: it states the client's facts.
    # An action's deadline ("within 15 days") comes from the law and is the
    # legal-grounding audit's concern, not this one's.
    have = _numbers(source_text)
    for n in sorted(_numbers(summary or "") - have):
        issues.append({"type": "unsupported_number", "value": n})

    lowered = analysis_text.lower()
    for f in u.get("facts") or []:
        if f.get("status") != "negated":
            continue
        terms = _fact_terms(f.get("fact_key") or "")
        if not terms:
            continue
        # Every mention of the fact's head term must have a negator within a
        # short window; one bare mention is enough to flag a possible inversion.
        head = terms[-1] if len(terms) == 1 else terms[0]
        for m in re.finditer(rf"\b{re.escape(head)}\w*", lowered):
            window = lowered[max(0, m.start() - 60): m.end() + 40]
            if all(t in window for t in terms[:2]) and not _NEGATORS.search(window):
                issues.append({"type": "negation_inverted", "fact_key": f["fact_key"]})
                break

    return {"version": FIDELITY_VERSION, "status": "issues" if issues else "consistent", "issues": issues}
