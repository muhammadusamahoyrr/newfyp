"""Deterministic Urdu / Roman-Urdu legal terms for RETRIEVAL (2026-10-13).

The statute corpus is English. An Urdu-script query ("میرے بھائی کو گرفتار
کر لیا گیا ہے۔ اس کی ضمانت کیسے ہوگی؟") gives BM25 nothing to match and the
LLM rewrite returned it unchanged (traced: d007, a bail question, retrieved no
bail provision at all). The intake retrieval query therefore gets the English
legal TERM for each Urdu or Roman-Urdu legal word it contains.

Rules:
  * a word-for-word term map, no model: the Urdu side is the intake
    localisation GLOSSARY reversed (the same draft list the Urdu rendering is
    held to), plus a few unambiguous everyday words for the same terms;
  * terms are APPENDED to the retrieval query only -- never to the client's
    words (affinity, gate, generation and the grader read those unchanged);
  * intake policy only; chat and research retrieval are untouched;
  * a term names a legal concept, never a section: mapping facts to a
    provision is a legal judgement this module does not make.

FACT CONCEPTS (v2, 2026-10-13 final hardening)
Traced on a two-issue story (a repayment cheque that bounced + a threat to
kill): the whole story ranked the cheque provision 11th -- below the grader's
8-passage window -- and the threat provision not at all, because the client's
words ("bounced", "threatened to kill") are not the statute's words
("dishonoured", "criminal intimidation"). Each concept below adds the legal
vocabulary for ONE fact pattern, only when its own trigger facts are stated:
  * dishonoured cheque  -- a cheque AND a bounce/dishonour; the repayment /
    obligation words only when a loan, debt or obligation is stated;
  * criminal intimidation -- a threat that is not negated; "threat to cause
    death" only when killing is stated;
  * cheating -- only on explicit deception/fraud words; a broken promise or a
    bounced cheque alone never adds it.
One retrieval query carries all of them; no multi-query, no per-issue branch.
"""
from __future__ import annotations

import re

TERMS_VERSION = "legal-terms-v2"

# Urdu script -> English legal term.
_URDU: dict[str, str] = {
    "ضمانت": "bail",
    "گرفتار": "arrest",
    "گرفتاری": "arrest",
    "ایف آئی آر": "FIR",
    "قانونی نوٹس": "legal notice",
    "دعویٰ": "plaint suit",
    "وراثت": "inheritance succession",
    "نان نفقہ": "maintenance",
    "نفقہ": "maintenance",
    "خلع": "khula dissolution of marriage",
    "طلاق": "talaq divorce",
    "جہیز": "dowry",
    "حق مہر": "dower",
    "قبضہ": "possession",
    "حکم امتناعی": "stay order injunction",
    "چوری": "theft",
}

# Roman Urdu (whole words, case-insensitive) -> English legal term.
_ROMAN: dict[str, str] = {
    "zamanat": "bail",
    "giraftar": "arrest",
    "giraftari": "arrest",
    "talaq": "talaq divorce",
    "khula": "khula dissolution of marriage",
    "nafqa": "maintenance",
    "nan nafqa": "maintenance",
    "jahez": "dowry",
    "jahaiz": "dowry",
    "haq mehr": "dower",
    "qabza": "possession",
    "wirasat": "inheritance succession",
    "virasat": "inheritance succession",
    "chori": "theft",
}


_NEGATION = re.compile(r"(?:\bnot\b|\bnever\b|\bno\b|n't\b|\bnahi\b|\bnahin\b|\bna\b|نہیں|نہ)",
                       re.IGNORECASE)


def _sentences(text: str) -> list[str]:
    return [x for x in re.split(r"[.?!\u061f\u06d4\n]+", text or "") if x.strip()]


def _stated(pattern: re.Pattern, text: str) -> bool:
    """`pattern` occurs in a sentence that does not negate it."""
    for sent in _sentences(text):
        m = pattern.search(sent)
        if m and not _NEGATION.search(sent[: m.start()][-40:]) and not _NEGATION.search(sent[m.end(): m.end() + 25]):
            return True
    return False


_CHEQUE = re.compile(r"\b(?:cheque|check|chek)s?\b|چیک", re.IGNORECASE)
_DISHONOUR = re.compile(r"bounc|dishono(?:u)?r|returned unpaid|insufficient funds|باؤنس|bounce", re.IGNORECASE)
_OBLIGATION = re.compile(r"\b(?:loan|debt|owed|owe|repay\w*|dues|payment|qarz|qarza|udhaar|udhar)\b|قرض|ادھار|ادائیگی",
                         re.IGNORECASE)
_THREAT = re.compile(r"\bthreat\w*|\bdhamki\w*|دھمکی|دھمکیاں", re.IGNORECASE)
_KILL = re.compile(r"\bkill\w*|\bdeath\b|\bmurder\w*|jaan se|maar d|جان سے|قتل", re.IGNORECASE)
_DECEIT = re.compile(r"\b(?:deceiv\w*|tricked|fraud\w*|dhoka\w*|dhokay\w*|swindl\w*|conned)\b|دھوکہ|دھوکے|فراڈ",
                     re.IGNORECASE)


def legal_concepts(text: str) -> list[dict]:
    """[{concept, terms}] for the fact patterns `text` actually states."""
    text = text or ""
    out = []
    if _stated(_CHEQUE, text) and _stated(_DISHONOUR, text):
        terms = "dishonoured cheque"
        if _stated(_OBLIGATION, text):
            terms += " repayment of loan obligation"
        out.append({"concept": "dishonoured_cheque", "terms": terms})
    if _stated(_THREAT, text):
        terms = "criminal intimidation threat"
        if _KILL.search(text):
            terms += " threat to cause death"
        out.append({"concept": "criminal_intimidation", "terms": terms})
    if _stated(_DECEIT, text):
        out.append({"concept": "cheating", "terms": "cheating dishonest inducement"})
    return out


def legal_terms(text: str) -> list[str]:
    """English legal terms for the Urdu / Roman-Urdu legal words and the fact
    concepts stated in `text`."""
    text = text or ""
    found: list[str] = [c["terms"] for c in legal_concepts(text)]
    for word, term in _URDU.items():
        if word in text and term not in found:
            found.append(term)
    for word, term in _ROMAN.items():
        if re.search(rf"(?<![A-Za-z]){re.escape(word)}(?![A-Za-z])", text, re.IGNORECASE) and term not in found:
            found.append(term)
    return found


def augment(query: str) -> str:
    """`query` plus the English terms it lacks (unchanged when none apply)."""
    terms = [t for t in legal_terms(query) if t.lower() not in (query or "").lower()]
    return f"{query} {' '.join(terms)}" if terms else query
