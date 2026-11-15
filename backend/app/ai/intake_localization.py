"""Client-facing Urdu version of a VERIFIED intake analysis (2026-10-12).

WHY NOT ANALYSE IN URDU

The analysis is generated in English and judged against English law sections:
the grounding judge compares the claims with the statutes it was shown. Asking
the model to write the analysis in Urdu would put Urdu claims in front of an
English judge, and the verdict would get weaker exactly for Urdu clients. So
the canonical analysis stays English -- it is what the lawyer's AI context, the
audit record and any re-verification read -- and THIS module produces a
controlled Urdu rendering of the finished, already-judged result.

WHAT IS CONTROLLED

  * Only prose is translated: the summary, each recommended action, each
    citation note. Evidence ids, statute names, section numbers, amounts,
    dates, risk level and every status value are never handed to the model as
    words: identifiers inside the prose are swapped for [[T1]]-style tokens
    first and restored afterwards.
  * The output must have the same number of actions and notes, in the same
    order; every token must come back exactly once; no digit may appear outside
    a token (a translated "Section 489-F" or amount would show up here); and no
    item may balloon (a translator adding advice).
  * Any failure -> status "failed" and the client sees the English original.
    Never a half-translated analysis.

The grounding cautions the judge appends to the English summary are NOT
translated by the model. They are stripped and reported as keys, and the UI
shows its own fixed wording for each -- a legal warning should be the same
sentence every time, and testable.
"""
from __future__ import annotations

import json
import logging
import re

from pydantic import BaseModel

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = ("ur",)

# The judge's appended cautions (intake_hallucination_node), by key.
CAUTION_PARTIAL = "partially_unverified"
CAUTION_CITATION = "citation_unmatched"


def _cautions() -> dict[str, str]:
    from app.ai.nodes.intake_hallucination_node import _CAUTION, _CITATION_CAUTION
    return {CAUTION_PARTIAL: _CAUTION, CAUTION_CITATION: _CITATION_CAUTION}


class LocalizedIntakeOutput(BaseModel):
    summary: str
    recommended_actions: list[str]
    citation_notes: list[str]


_SYSTEM = """\
You translate a finished legal case analysis from English into Urdu (Urdu script) for the client to read.

Rules — all of them are checked, and any violation discards your output:
- Translate faithfully. Do not add, remove, merge, split or reorder items. Do not add any advice or legal opinion of your own.
- recommended_actions must have exactly as many items as given, in the same order. The same for citation_notes.
- Tokens like [[T1]], [[T2]] stand for law names, section numbers, amounts and dates. Copy every token exactly as written, exactly once, in the place it belongs. Never translate, change or drop a token.
- Write no digits of your own (neither 0-9 nor Urdu digits). Any number is already inside a token.
- Plain, respectful Urdu a non-lawyer understands.
- When a "required terms" list is given, use exactly those Urdu words for those English terms.
Reply with ONLY one JSON object with keys: summary, recommended_actions, citation_notes. No other text."""

# Identifiers that must survive verbatim. Longest statute names first, so a
# shorter name inside a longer one never splits it.
_ID_PATTERNS = [
    r"\b(?:Section|Sections|Sec\.|Article|Articles|Order|Rule)\s+[0-9IVXLC][\w\-/().]*",
    r"\b(?:Rs\.?|PKR)\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:lakh|crore|million|thousand))?",
    r"\b\d{1,4}[/-]\d{1,2}[/-]\d{1,4}\b",
    r"\b\d[\d,]*(?:\.\d+)?(?:-[A-Z])?(?:\s*%)?",
    r"\b(?:PPC|CrPC|Cr\.P\.C\.|CPC|C\.P\.C\.|MFLO|PECA|NIA)\b",
]

# ONE Urdu word per legal term (2026-10-12): the model otherwise picks a
# different word each time ("رد" / "باؤنس"), and one case can use two. Each
# term found in an English item is required in that item's Urdu. A DRAFT list
# of common, unambiguous usage -- to be reviewed by a lawyer before launch.
GLOSSARY: dict[str, str] = {
    "FIR": "ایف آئی آر",
    "bail": "ضمانت",
    "legal notice": "قانونی نوٹس",
    "plaint": "دعویٰ",
    "civil court": "دیوانی عدالت",
    "family court": "فیملی کورٹ",
    "court": "عدالت",
    "lawyer": "وکیل",
    "advocate": "وکیل",
    "inheritance": "وراثت",
    "maintenance": "نان نفقہ",
    "khula": "خلع",
    "divorce": "طلاق",
    "dowry": "جہیز",
    "dower": "حق مہر",
    "possession": "قبضہ",
    "stay order": "حکم امتناعی",
    "cheque": "چیک",
}

# Urdu names SHOWN BESIDE a statute's English name -- never replacing it, and
# never produced by the model. Only the long-established names; a DRAFT for
# lawyer review like the glossary.
STATUTE_NAMES_UR: dict[str, str] = {
    "pakistan penal code": "مجموعہ تعزیرات پاکستان",
    "code of criminal procedure": "ضابطہ فوجداری",
    "code of civil procedure": "ضابطہ دیوانی",
    "constitution of pakistan": "آئین پاکستان",
    "constitution of the islamic republic of pakistan": "آئین پاکستان",
    "qanun-e-shahadat order": "قانون شہادت آرڈر",
}


def _glossary_hits(text: str) -> list[str]:
    """Glossary terms in `text`, longest first; a term inside a longer one that
    matched ("court" in "civil court") is not required separately."""
    rest = text or ""
    hits = []
    for term in sorted(GLOSSARY, key=len, reverse=True):
        pattern = rf"\b{re.escape(term)}s?\b"
        if re.search(pattern, rest, flags=re.IGNORECASE):
            hits.append(term)
            rest = re.sub(pattern, " ", rest, flags=re.IGNORECASE)
    return hits


def statute_name_ur(statute: str) -> str | None:
    name = re.sub(r"[,\s]*\d{4}\s*$", "", (statute or "").strip()).lower()
    return STATUTE_NAMES_UR.get(name)
_TOKEN = re.compile(r"\[\[T(\d+)\]\]")
_DIGIT = re.compile(r"[0-9۰-۹٠-٩]")
_MAX_GROWTH = 3.0      # an Urdu rendering is about as long as its English source


LOCALIZATION_MAX_TOKENS = 6000


class LocalizationError(Exception):
    pass


# WHY a rendering failed (2026-10-13). A bare "failed" made a failure
# undiagnosable: the one Urdu failure in the 34-item evaluation (d020) left no
# record of whether the provider, the JSON, the glossary or the meaning
# checks refused it. The reason is recorded; the safeguards are unchanged.
FAIL_PROVIDER = "provider_error"
FAIL_TIMEOUT = "timeout"
FAIL_MALFORMED = "malformed_response"
FAIL_GLOSSARY = "glossary_check"
FAIL_MEANING = "meaning_preservation"


def failure_reason(exc: BaseException) -> str:
    if isinstance(exc, TimeoutError):
        return FAIL_TIMEOUT
    if isinstance(exc, LocalizationError):
        msg = str(exc)
        if msg.startswith("glossary term not used"):
            return FAIL_GLOSSARY
        if msg in ("action count changed", "citation note count changed", "an item was emptied", "an item grew",
                   "tokens changed", "a digit outside a token"):
            # Protected identifiers (sections, names, numbers) altered or
            # invented: a meaning failure, not a formatting one.
            return FAIL_MEANING
        return FAIL_MALFORMED
    if isinstance(exc, (ValueError, json.JSONDecodeError)):
        return FAIL_MALFORMED
    return FAIL_PROVIDER


def protect(text: str, terms: list[str], table: dict[str, str]) -> str:
    """Replace identifiers with [[Tn]] tokens. `table` maps token -> original
    and is shared across all fields, so one value keeps one token."""
    by_value = {v: k for k, v in table.items()}

    def token_for(value: str) -> str:
        if value not in by_value:
            tok = f"[[T{len(table) + 1}]]"
            table[tok] = value
            by_value[value] = tok
        return by_value[value]

    out = text or ""
    for term in sorted({t for t in terms if t and len(t) > 2}, key=len, reverse=True):
        out = re.sub(re.escape(term), lambda m: token_for(m.group(0)), out)
    for pattern in _ID_PATTERNS:
        out = re.sub(pattern, lambda m: token_for(m.group(0)) if not _inside_token(m) else m.group(0), out)
    return out


def _inside_token(m: re.Match) -> bool:
    s, start = m.string, m.start()
    before = s.rfind("[[", 0, start)
    return before != -1 and s.find("]]", before) >= start


def restore(text: str, source: str, table: dict[str, str]) -> str:
    """Put the originals back; refuse anything that does not match the source."""
    want = sorted(_TOKEN.findall(source))
    got = sorted(_TOKEN.findall(text))
    if want != got:
        raise LocalizationError("tokens changed")
    if _DIGIT.search(_TOKEN.sub("", text)):
        raise LocalizationError("a digit outside a token")
    return _TOKEN.sub(lambda m: table[f"[[T{m.group(1)}]]"], text)


def strip_cautions(summary: str) -> tuple[str, list[str]]:
    keys = []
    text = summary or ""
    for key, caution in _cautions().items():
        if caution.strip() and caution.strip() in text:
            text = text.replace(caution, "").replace(caution.strip(), "")
            keys.append(key)
    return text.strip(), keys


def _citation_terms(citations: list[dict]) -> list[str]:
    """Statute names to keep verbatim -- with AND without the year, because
    the prose says "Code of Civil Procedure" while the citation reads "Code of
    Civil Procedure 1908" (measured: the bare name was translated)."""
    terms = []
    for c in citations or []:
        for key in ("statute", "act", "title"):
            if c.get(key):
                name = str(c[key]).strip()
                terms.append(name)
                bare = re.sub(r"[,\s]*\(?\d{4}\)?\s*$", "", name).strip()
                if bare and bare != name:
                    terms.append(bare)
    return terms


def _parse_output(result) -> LocalizedIntakeOutput:
    """The model's answer as the schema, whether it came back typed (tests) or
    as plain text holding a JSON object."""
    if isinstance(result, LocalizedIntakeOutput):
        return result
    text = str(getattr(result, "content", result) or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise LocalizationError("no JSON object in the reply")
    return LocalizedIntakeOutput(**json.loads(text[start:end + 1]))


def localize(analysis: dict, language: str, *, llm=None) -> dict:
    """The client-facing rendering of `analysis` in `language`, or a failure.

    Never raises. `analysis` is not modified.
    """
    if language not in SUPPORTED_LANGUAGES:
        return {"language": language, "status": "unsupported"}
    try:
        summary, cautions = strip_cautions(analysis.get("summary") or "")
        actions = [str(a) for a in (analysis.get("recommended_actions") or [])]
        citations = list(analysis.get("law_citations") or [])
        notes = [str(c.get("description") or c.get("note") or "") for c in citations]

        table: dict[str, str] = {}
        terms = _citation_terms(citations)
        src_summary = protect(summary, terms, table)
        src_actions = [protect(a, terms, table) for a in actions]
        src_notes = [protect(n, terms, table) for n in notes]

        if llm is None:
            # A plain JSON reply, NOT a tool call: long Urdu inside tool-call
            # arguments came back as malformed JSON and Groq refused it
            # (400 tool_use_failed), on both keys -- every Urdu client then got
            # English. The reply is parsed and validated below either way.
            from app.ai.llm import get_llm
            from app.ai.provider_health import PURPOSE_INTAKE_EXTRACTION
            # OUTPUT BUDGET (2026-10-13). The shared 2,000-token cap counts the
            # reasoning model's hidden reasoning too: on a five-action analysis
            # ~1,480 tokens went to reasoning and the Urdu JSON was cut off
            # mid-summary (finish_reason "length", every time) -- reported as a
            # malformed reply. The rendering call alone gets room to finish.
            # No safeguard below is relaxed.
            base = get_llm(purpose=PURPOSE_INTAKE_EXTRACTION)

            class _Budgeted:
                def invoke(self, msgs):
                    return base.invoke(msgs, max_tokens=LOCALIZATION_MAX_TOKENS)
            llm = _Budgeted()
        hits = sorted({t for text in [summary, *actions, *notes] for t in _glossary_hits(text)})
        payload = {
            "summary": src_summary,
            "recommended_actions": src_actions,
            "citation_notes": src_notes,
        }
        if hits:
            payload["required_terms"] = {t: GLOSSARY[t] for t in hits}
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        try:
            result = _parse_output(llm.invoke(messages))
        except (LocalizationError, ValueError):
            # One more try: a reply that was not valid JSON is usually a
            # one-off, and the alternative is English for an Urdu client.
            result = _parse_output(llm.invoke(messages))

        if len(result.recommended_actions) != len(src_actions):
            raise LocalizationError("action count changed")
        if len(result.citation_notes) != len(src_notes):
            raise LocalizationError("citation note count changed")

        def one(translated: str, source: str, english: str) -> str:
            if not source.strip():
                return ""
            if not translated.strip():
                raise LocalizationError("an item was emptied")
            if len(translated) > max(len(source) * _MAX_GROWTH, len(source) + 120):
                raise LocalizationError("an item grew")
            for term in _glossary_hits(english):
                if GLOSSARY[term] not in translated:
                    raise LocalizationError(f"glossary term not used: {term}")
            return restore(translated.strip(), source, table)

        return {
            "language": language,
            "status": "ok",
            "summary": one(result.summary, src_summary, summary),
            "recommended_actions": [one(t, s, e) for t, s, e in zip(result.recommended_actions, src_actions, actions)],
            "citation_notes": [one(t, s, e) for t, s, e in zip(result.citation_notes, src_notes, notes)],
            # Fixed names, not model output: shown beside the English name.
            "statute_names": [statute_name_ur(c.get("statute") or "") for c in citations],
            "cautions": cautions,
        }
    except Exception as exc:  # noqa: BLE001 -- the client then sees the English original
        reason = failure_reason(exc)
        logger.warning("intake localization to %s failed: %s (%s)", language, reason, exc.__class__.__name__)
        return {"language": language, "status": "failed", "reason": reason,
                "detail": f"{exc.__class__.__name__}: {str(exc)[:160]}"}
