"""Semantic input-fact fidelity -- DEV ONLY, NOT WIRED into the drafter guard (2026-10-15).

The lexical check (draft_claims.invented_facts) catches facts of known shapes -- a condition word, a number, a name --
and misses paraphrases ("lacks the capacity to comprehend", "was in hospital", "no previous criminal record"). This
module tries MEANING: each factual-looking clause of a drafted sentence is compared with the lawyer's input using the
local multilingual embedding model the retriever already uses (intfloat/multilingual-e5-base, English and Urdu); a
clause no part of the input supports is flagged.

It is measured on evals/drafter_v2/fact_fidelity_dev.json (scripts/eval_fact_fidelity.py) before any use. Embedding
similarity cannot see negation or exact values ("insane" vs "not insane"), which is why it is measured alongside, not
instead of, the lexical check."""
from __future__ import annotations

import re

_CITATION = re.compile(
    r"(?i)\(?\s*(?:under|pursuant\s+to|in\s+accordance\s+with|as\s+per|by\s+virtue\s+of|read\s+with)?\s*"
    r"(?:sections?|sec\.|s\.|articles?|order\s+[ivxlc\d]+\s+rule|rule)\s*[\w\-()]+(?:\s+(?:of\s+the\s+)?[A-Z][\w,.\- ]{0,60}?"
    r"(?:Act|Code|Ordinance|CrPC|CPC|PPC|QSO)(?:,?\s*\d{4})?)?\s*\)?")
_CLAUSE_SPLIT = re.compile(r"[;:]|,\s+(?=(?:and|but|which|who|thereby|as|because|since|consequently|therefore)\b)|"
                           r"\s+(?:and|but|because|since|thereby|whereas)\s+|[،؛]")
# a statement of LAW or a request to the court, not a fact about the case
_LEGAL = re.compile(r"(?i)\b(?:may|shall|should|must|empower\w*|entitl\w*|liable|deemed|provid\w*|prescrib\w*|"
                    r"authoris\w*|authoriz\w*|pray\w*|request\w*|seeks?|seeking|submits?|invok\w*|respectfully|"
                    r"hereby|ready\s+to|undertak\w*|enforceable|jurisdiction\s+to)\b|کے\s+تحت|دفعہ|سیکشن")
# a fact asserted about a person or an event
_FACT_VERB = re.compile(r"(?i)\b(?:was|were|has|have|had|did|is|are|became|been)\b|\w+ed\b|"
                        r"\b(?:ہے|ہیں|تھا|تھی|تھے|گیا|گئی|گئے|کیا|دی)\b")


def factual_clauses(sentence: str) -> list[str]:
    s = re.sub(r"\[[^\]]*\]|_{2,}", " ", sentence or "")
    s = _CITATION.sub(" ", s)
    s = re.sub(r"^\W*(?:\d+(?:\.\d+)*[.)]?|[a-z][.)])?\s*(?:That\s+)?", "", s.strip())
    out = []
    for c in _CLAUSE_SPLIT.split(s):
        c = " ".join((c or "").split()).strip(" ,.;۔")
        if len(c.split()) >= 4 and _FACT_VERB.search(c) and not _LEGAL.search(c):
            out.append(c)
    return out


def input_pieces(given: str) -> list[str]:
    parts = re.split(r"(?<=[.!?۔])\s+|\n+|[;,،]\s*", given or "")
    pieces = [" ".join(p.split()) for p in parts if len(p.split()) >= 2]
    return pieces or [" ".join((given or "").split())]


def support_scores(sentences: list[str], given: str, embed_query, embed_docs) -> list[list[tuple[str, float]]]:
    """For each sentence: [(clause, max similarity to any input piece)]. Embedding functions are injected so the
    measurement (and tests) control the model."""
    import numpy as np
    pieces = input_pieces(given)
    P = np.asarray(embed_docs(pieces), dtype=np.float32)
    out = []
    for s in sentences:
        cl = factual_clauses(s)
        if not cl:
            out.append([])
            continue
        Q = np.asarray([embed_query(c) for c in cl], dtype=np.float32)
        sims = Q @ P.T
        out.append([(c, float(sims[i].max())) for i, c in enumerate(cl)])
    return out
