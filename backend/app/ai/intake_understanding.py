"""Structured Intake Understanding (Batch 2, 2026-10-12).

WHY
---
Clarification answers used to reach retrieval and generation as raw text:

    Q: Do you have a written contract?
    A: No

The client said NO, but the words "written contract" -- the AI's own question
-- were part of the retrieval query, pulling contract law towards a matter
with no contract. And a model reading "Q/A" text can, and did, turn a question
into an asserted fact.

This module turns an intake into an auditable ledger instead:

  facts          confirmed (value True or a stated value) and negated (False),
                 each with where it came from
  unknown_facts  "I don't know" -- unknown, never negative
  original_story the client's own words, unchanged

and derives TWO texts from it, never one:

  retrieval_text   the client's own words only: the story, their free-text
                   answers, and positively CONFIRMED facts. No AI-authored
                   question text, and no negated fact (a "no contract" must not
                   search for contracts).
  analysis_context the same facts LABELLED for the model, negations stated as
                   negations, so the analysis can use them without mistaking a
                   question for a claim.

Deterministic and pure. Nothing here calls a model; structured model output
(a question's fact_key) is validated before it is trusted.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

UNDERSTANDING_VERSION = "intake-understanding-v1"

POLARITY_YES = "yes"
POLARITY_NO = "no"
POLARITY_UNKNOWN = "unknown"
POLARITY_FREE = "freeform"

SOURCES = ("typed_story", "voice_transcription", "client_answer", "uploaded_document", "user_selected")

_FACT_KEY = re.compile(r"^[a-z][a-z0-9_]{2,60}$")


def _clean(text: str) -> str:
    t = unicodedata.normalize("NFKC", text or "").lower().strip()
    t = t.replace("’", "'").replace("‘", "'")
    t = re.sub(r"[^\w\s']", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# Order matters: "pata nahi" (don't know) contains "nahi" (no), so UNKNOWN is
# checked first, and only short answers are classified at all -- "No, but my
# brother has a copy" is a statement, not a bare negation.
_UNKNOWN = [
    r"i ?don'?t know", r"don'?t know", r"dont know", r"do not know", r"not sure", r"no idea", r"unsure",
    r"i'?m not sure", r"can'?t say", r"cannot say", r"idk", r"unknown", r"maybe", r"perhaps",
    r"pata nahi?n?", r"nahi?n? pata", r"maloom nahi?n?", r"malum nahi?n?", r"nahi?n? maloom", r"yaad nahi?n?",
    r"shayad", r"yaqeen nahi?n?",
    r"معلوم نہیں", r"نہیں معلوم", r"پتا نہیں", r"پتہ نہیں", r"یقین نہیں", r"یاد نہیں", r"شاید",
]
_NO = [
    r"no", r"nope", r"nah", r"never", r"none", r"not at all", r"no it is not", r"no there is not",
    r"not available", r"not available with me", r"i do not have", r"i don'?t have", r"we don'?t have",
    r"there is no\w*", r"no written \w+", r"never happened", r"it never happened", r"did not happen",
    r"nahi?n?", r"bilkul nahi?n?", r"koi nahi?n?", r"nahi?n? hai", r"nahi?n? hain", r"mere paas nahi?n?( hai)?",
    r"kabhi nahi?n?", r"aisa nahi?n? hua", r"nahi?n? hua",
    r"نہیں", r"جی نہیں", r"بالکل نہیں", r"کوئی نہیں", r"نہیں ہے", r"میرے پاس نہیں ہے", r"کبھی نہیں", r"ایسا نہیں ہوا",
]
_YES = [
    r"yes", r"yeah", r"yep", r"yup", r"sure", r"of course", r"correct", r"right", r"yes i do", r"yes there is",
    r"i have", r"we have", r"haa?n", r"ha+n", r"ji", r"ji haa?n", r"jee", r"bilkul", r"zaroor", r"mere paas hai",
    r"ہاں", r"جی ہاں", r"جی", r"بالکل", r"ضرور", r"میرے پاس ہے",
]


def _matches(patterns: list[str], text: str) -> bool:
    return any(re.fullmatch(p, text) for p in patterns)


def answer_polarity(answer: Optional[str]) -> str:
    """yes / no / unknown / freeform for one clarification answer.

    Never infers "yes" from a non-empty answer: anything that is not a bare
    yes/no/unknown is FREEFORM, kept as the client's statement.
    """
    text = _clean(answer or "")
    if not text:
        return POLARITY_UNKNOWN
    # Bare answers only: a long reply is a statement, whatever word it starts with.
    if len(text.split()) > 6:
        return POLARITY_FREE
    if _matches(_UNKNOWN, text):
        return POLARITY_UNKNOWN
    if _matches(_NO, text):
        return POLARITY_NO
    if _matches(_YES, text):
        return POLARITY_YES
    return POLARITY_FREE


def valid_fact_key(key) -> Optional[str]:
    """A model-proposed fact key, only if it is a plain snake_case identifier."""
    k = str(key or "").strip().lower()
    return k if _FACT_KEY.fullmatch(k) else None


def humanize(fact_key: str) -> str:
    return fact_key.replace("_", " ")


def build_understanding(*, story: str, story_source: str = "typed_story",
                        clarification_qa: list | None = None,
                        jurisdiction: str = "", desired_outcome: str = "",
                        party_role: str = "", language: str = "",
                        evidence_files: list | None = None) -> dict:
    """The ledger for one intake. Works on old records (no question ids or
    fact keys): their answers become labelled statements, never inferred facts."""
    facts, unknown, statements = [], [], []
    for n, qa in enumerate(clarification_qa or [], 1):
        q, a = (qa or {}).get("q") or "", (qa or {}).get("a")
        if a is None:
            continue
        qid = (qa or {}).get("question_id") or f"q{n}"
        key = valid_fact_key((qa or {}).get("fact_key"))
        pol = answer_polarity(a)
        ref = {"question_id": qid, "question": q, "answer": a}
        if pol == POLARITY_UNKNOWN:
            unknown.append({"fact_key": key, "question_id": qid, "question": q, "source": "client_answer"})
        elif pol in (POLARITY_YES, POLARITY_NO) and key:
            facts.append({"fact_key": key, "value": pol == POLARITY_YES,
                          "status": "confirmed" if pol == POLARITY_YES else "negated",
                          "source": "client_answer", "question_id": qid,
                          "source_reference": ref, "confidence": 1.0})
        else:
            # A free-text answer, or a yes/no to a question with no valid key:
            # kept as the client's own statement, tied to its question.
            statements.append({"question_id": qid, "question": q, "answer": a.strip(),
                               "polarity": pol, "source": "client_answer"})
    docs = [{"file_id": f.get("file_id"), "filename": f.get("filename"), "source": "uploaded_document"}
            for f in (evidence_files or []) if isinstance(f, dict)]
    return {
        "version": UNDERSTANDING_VERSION,
        "original_story": story or "",
        "story_source": story_source if story_source in SOURCES else "typed_story",
        "facts": facts,
        "unknown_facts": unknown,
        "statements": statements,
        "documents": docs,
        "legal_issues": [],               # proposed later; never alters jurisdiction
        "desired_outcome": (desired_outcome or "").strip(),
        "jurisdiction": (jurisdiction or "").strip().lower(),
        "jurisdiction_source": "user_selected",
        "party_role": (party_role or "").strip().lower(),
        "language": language or "",
    }


def retrieval_text(u: dict) -> str:
    """The client's own words for the retriever: story + free-text answers +
    CONFIRMED facts. No AI question text; no negated or unknown fact."""
    parts = [u.get("original_story") or ""]
    for s in u.get("statements") or []:
        if s.get("polarity") == POLARITY_FREE and s.get("answer"):
            parts.append(s["answer"])
    for f in u.get("facts") or []:
        if f.get("status") == "confirmed":
            parts.append(humanize(f["fact_key"]))
    return "\n".join(p for p in parts if p and p.strip()).strip()


def ledger_sections(u: dict) -> list[str]:
    """The clarification ledger as labelled blocks (no story, no outcome)."""
    out = []
    confirmed = [humanize(f["fact_key"]) for f in u.get("facts") or [] if f.get("status") == "confirmed"]
    negated = [humanize(f["fact_key"]) for f in u.get("facts") or [] if f.get("status") == "negated"]
    if confirmed:
        out.append("Facts the client CONFIRMED:\n" + "\n".join(f"- {c}" for c in confirmed))
    if negated:
        out.append("Facts the client said are NOT the case (do not treat them as true):\n"
                   + "\n".join(f"- NOT: {c}" for c in negated))
    stated = [s for s in u.get("statements") or [] if s.get("answer")]
    if stated:
        out.append("The client's answers to clarifying questions (the QUESTIONS are not facts):\n"
                   + "\n".join(f'- Asked: "{s["question"]}" — client answered: "{s["answer"]}"' for s in stated))
    # Only KEYED unknowns are listed: an unkeyed one would carry the AI's
    # question text, and "unknown" must not reintroduce its vocabulary.
    unknown = [humanize(s["fact_key"]) for s in u.get("unknown_facts") or [] if s.get("fact_key")]
    if unknown:
        out.append("Unknown to the client (do not assume either way):\n" + "\n".join(f"- {k}" for k in unknown))
    return out


def analysis_context(u: dict) -> str:
    """The story and the ledger, labelled for the analysis model."""
    lines = [f"Client's account (their own words):\n{u.get('original_story') or ''}".rstrip()]
    lines += ledger_sections(u)
    if u.get("desired_outcome"):
        lines.append(f"Desired outcome:\n{u['desired_outcome']}")
    if u.get("party_role"):
        lines.append(f"The client is the {u['party_role']} in this matter.")
    return "\n\n".join(lines)


