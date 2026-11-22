"""Exact-provision integrity for client questions that name an Act and a
section (client chat, 2026-10-14).

THE FAILURE THIS CLOSES
-----------------------
"What is Section 489-F PPC?" was answered as "a definitional clause ... the
person in whose favour a cheque is issued", citing a CrPC schedule ROW. All
eight evidence chunks were CrPC schedule rows that merely mention 489-F; the
PPC text was never retrieved. Two causes:
  * the base `criminal_collection` labels the 489-F chunk as section "489"
    (with 489-A..E) -- the lettered-section relabel exists only in the
    versioned `criminal_collection__sec_v1/__sec_v2` indexes;
  * nothing required the answer to rest on the provision the user named, so a
    table row that mentions it stood in for its text.

WHAT THIS DOES (client surface only; research and intake untouched)
  1. `requested()` reads the provisions the USER named (their words, never the
     model's), after normalising "489 F", "dafa", "دفعہ", "تعزیرات پاکستان".
  2. `fetch()` looks each one up READ-ONLY by metadata, preferring the
     versioned `__sec_v2` index (no corpus is rewritten), and accepts a chunk
     only if its statute matches AND its text opens with that section's own
     heading -- so "489" never stands in for "489-F", nor the reverse, and a
     schedule row ("489- F Dishonestly issuing ... May arrest ...") is not the
     section.
  3. `pin()` puts the exact text first, so the grader cannot drop it.
  4. When the provision is not found, generation is told so, and `enforce()`
     makes the visible answer say so instead of defining it from elsewhere.
"""
from __future__ import annotations

import logging
import re

from app.ai.answer_citations import (
    ParsedCitation,
    extract_citations,
    normalise_statute,
)
from app.ai.corpus_index import canonical_section, section_key, split_section

logger = logging.getLogger(__name__)

INTEGRITY_VERSION = "exact-provision-v1"

_BASE_COLLECTIONS = ("criminal_collection", "civil_collection", "family_collection",
                     "constitutional_collection")
_PREFERRED_VARIANT = "sec_v2"
_MAX_PROVISIONS = 3

# Words people use for "section" / the PPC, normalised before parsing.
_REWRITES = (
    (re.compile(r"\b(?:dafa|dafaa|daf'a|dafah)\b", re.IGNORECASE), "Section"),
    (re.compile(r"دفعہ"), "Section"),
    (re.compile(r"تعزیراتِ? پاکستان|پاکستان پینل کوڈ"), "PPC"),
    (re.compile(r"ضابطہ فوجداری"), "CrPC"),
    # Urdu order: "PPC کی Section 420" -> "Section 420 PPC"
    (re.compile(r"\b(PPC|CrPC|CPC)\s+(?:کی|کے|کا)\s+Section\s+(\d{1,3}(?:\s*-?\s*[A-Za-z])?)\b"),
     r"Section \2 \1"),
    (re.compile(r"\b(\d{1,3})\s+([A-Za-z])\b(?=\s*(?:of\s+(?:the\s+)?)?(?:PPC|CrPC|CPC|Pakistan Penal))"),
     r"\1-\2"),
)
_DIGITS = str.maketrans({**{a: b for a, b in zip("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")},
                         # "489‑F" with a non-breaking hyphen must not read as 489
                         **dict.fromkeys("‐‑‒–—", "-"),
                         **dict.fromkeys("   ", " ")})


# Lettered sections written with Urdu letter NAMES ("489-ایف"). Read as plain
# "489" they would fetch a different provision -- the lookalike error.
_URDU_LETTERS = {"اے": "A", "بی": "B", "سی": "C", "ڈی": "D", "ای": "E", "ایف": "F", "جی": "G", "ایچ": "H"}
_URDU_LETTERED = re.compile(r"(\d{1,3})\s*-?\s*(" + "|".join(sorted(_URDU_LETTERS, key=len, reverse=True))
                            + r")(?![؀-ۿ])")


def requested(question: str) -> list[ParsedCitation]:
    """Provisions the user explicitly named (Act + section)."""
    text = (question or "").translate(_DIGITS)
    text = _URDU_LETTERED.sub(lambda m: f"{m.group(1)}-{_URDU_LETTERS[m.group(2)]}", text)
    for pattern, repl in _REWRITES:
        text = pattern.sub(repl, text)
    return extract_citations(text)[:_MAX_PROVISIONS]


def label(cit: ParsedCitation) -> str:
    return f"Section {cit.section} {cit.statute.split()[0]}"


def _heading(cit: ParsedCitation) -> re.Pattern:
    num, letter = split_section(cit.section)
    if letter:
        # Plus the two OCR layouts the PPC source files use for lettered
        # headings (2026-10-14: 90 of 254 lettered criminal chunks were not
        # recognised, and E4 answered "couldn't find Section 337-A" beside
        # its own text):  "120- A Definition of ..."  (no stop after the
        # letter) and  "337- Punishment of shajjah: \nA. Whoever ..."  (the
        # letter split onto the next line). Never "489." for 489-F, never
        # "489- F" for a different letter.
        # Case-sensitive on purpose: the split layout is recognised by its
        # heading WORD ("Punishment", Capital + lowercase) straight after
        # "337- " -- "86-A. Procedure ...\nC." is section 86-A whose next line
        # happens to start "C.", not section 86-C.
        return re.compile(rf"^\W*{num}\s*-?\s*(?i:{letter})\s*\."
                          rf"|^\W*{num}\s*-\s*(?i:{letter})\s+[\"'“A-Z]"
                          rf"|^\W*{num}\s*-\s+[A-Z][a-z][^\n]{{0,100}}\n\s*(?i:{letter})\s*\.")
    # "489." -- never "489-A." or "489- F."
    return re.compile(rf"^\W*{num}\s*\.(?!\s*-)\s")


def is_exact(chunk: dict, cit: ParsedCitation) -> bool:
    """Same Act, and the text opens with THIS section's own heading."""
    if normalise_statute(chunk.get("statute", "")) != cit.key[0]:
        return False
    return bool(_heading(cit).match(chunk.get("content") or ""))


# Lawyer research reads the versioned IDENTITY indexes: civil adds CPC
# Order/Rule and Limitation Schedule/Article identities, so "Section 17 CPC"
# can no longer resolve to Order XI Rule 17 (scripts/build_ident_index.py).
_RESEARCH_VARIANTS = {"criminal_collection": "sec_v2", "civil_collection": "ident_v2"}   # 2026-10-15 (rollback: ident_v1)


def _collections(research: bool = False) -> list[str]:
    from app.ai.contextual_index import collection_for
    from app.db.chroma import get_chroma
    client = get_chroma()
    out = []
    for base in _BASE_COLLECTIONS:
        variant = _RESEARCH_VARIANTS.get(base, "base") if research else _PREFERRED_VARIANT
        name = collection_for(base, variant)
        if research and variant != "base":
            # Lawyer research and the drafter (2026-10-16): the verified identity
            # index or IdentityIndexUnavailable -- never the base collection
            # presented as if the identity lookup had run.
            from app.ai import index_health
            out.append(index_health.require(name, client))
            continue
        try:
            client.get_collection(name)
            out.append(name)
        except Exception:  # variant not built for this collection
            # Client chat: base where sec_v2 was never built (civil, family,
            # constitutional) is its established policy, unchanged. Logged so a
            # MISSING criminal sec_v2 is visible rather than silent.
            if name in _CLIENT_EXPECTED_VARIANTS:
                logger.warning("exact_provision: %s missing -- client lookup reads %s", name, base)
            out.append(base)
    return out


# Variants client chat expects to exist (a missing one is logged, not refused).
_CLIENT_EXPECTED_VARIANTS = frozenset({"criminal_collection__sec_v2"})


class CorpusUnavailable(RuntimeError):
    """strict=True only: the statute corpus could not be read, so "not found"
    would be a guess. Carries no answer or document text."""


def fetch(citations: list[ParsedCitation], research: bool = False,
          strict: bool = False, include_continuations: bool = False) -> dict[str, list[dict]]:
    """{label: [exact chunks]} -- read-only metadata lookups. Never raises:
    a lookup failure means "not found", which the answer then says.

    strict=True (the drafter's legal check, 2026-10-14): a corpus that could not
    be read raises CorpusUnavailable instead -- there "not found" would be
    reported as a checked result when nothing was checked."""
    from app.ai.contextual_index import strip_context
    from app.ai.source_text_clean import clean_statute_text  # footnote markers (2026-11-22)
    from app.db.chroma import get_chroma
    found: dict[str, list[dict]] = {}
    try:
        client = get_chroma()
        names = _collections(research)
    except Exception as exc:
        logger.warning("exact_provision: corpus unavailable", exc_info=True)
        if strict:
            if isinstance(exc, CorpusUnavailable):      # keeps which identity index and why
                raise
            raise CorpusUnavailable("statute corpus unavailable") from exc
        return {label(c): [] for c in citations}
    for cit in citations:
        num, _ = split_section(cit.section)
        candidates = sorted({section_key(cit.section), canonical_section(cit.section), num})
        hits: list[dict] = []
        failed = 0
        for name in names:
            try:
                res = client.get_collection(name).get(
                    where={"section_number": {"$in": candidates}},
                    include=["documents", "metadatas"], limit=60)
            except Exception:
                failed += 1
                continue
            for doc, meta in zip(res.get("documents") or [], res.get("metadatas") or []):
                chunk = {"content": clean_statute_text(strip_context(doc, meta)), "statute": meta.get("statute", ""),
                         "section_number": cit.section, "source_file": meta.get("source_file", ""),
                         "chunk_id": meta.get("chunk_id", ""), "province": meta.get("province", "federal"),
                         "law_type": meta.get("law_type", ""), "exact_provision": label(cit),
                         "exact_index": name}
                if is_exact(chunk, cit) and chunk["chunk_id"] not in {h["chunk_id"] for h in hits}:
                    hits.append(chunk)
            if hits:
                if include_continuations:
                    # Long provisions are sliding 800-character chunks sharing
                    # section metadata. Only the first starts with "7. Talaq";
                    # the following chunk can hold the deadline. Follow the
                    # same source's consecutive chunk IDs, never another Act's
                    # section 7 or a non-section schedule row.
                    anchor = hits[0]
                    match = re.match(r"^(.+_)(\d+)$", anchor.get("chunk_id") or "")
                    if match:
                        prefix, position = match.group(1), int(match.group(2))
                        continuations = []
                        for doc, meta in zip(res.get("documents") or [], res.get("metadatas") or []):
                            chunk_id = meta.get("chunk_id") or ""
                            other = re.match(r"^(.+_)(\d+)$", chunk_id)
                            if (not other or other.group(1) != prefix or int(other.group(2)) <= position
                                    or normalise_statute(meta.get("statute", "")) != cit.key[0]
                                    or section_key(str(meta.get("section_number") or "")) != section_key(cit.section)
                                    or meta.get("source_file", "") != anchor.get("source_file", "")):
                                continue
                            continuations.append((int(other.group(2)), {
                                "content": clean_statute_text(strip_context(doc, meta)), "statute": meta.get("statute", ""),
                                "section_number": cit.section, "source_file": meta.get("source_file", ""),
                                "chunk_id": chunk_id, "province": meta.get("province", "federal"),
                                "law_type": meta.get("law_type", ""), "exact_provision": label(cit),
                                "exact_index": name,
                            }))
                        hits.extend(c for _, c in sorted(continuations)[:2]
                                    if c["chunk_id"] not in {h["chunk_id"] for h in hits})
                break
        if strict and failed == len(names):
            raise CorpusUnavailable("no statute collection could be read")
        found[label(cit)] = hits[:3 if include_continuations else 2]
    return found


def pin(chunks: list[dict], exact: list[dict]) -> list[dict]:
    """Exact provision text first; the same chunk is never listed twice."""
    ids = {c.get("chunk_id") for c in exact}
    return list(exact) + [c for c in chunks or [] if c.get("chunk_id") not in ids]


def exact_from(chunks: list[dict] | None) -> list[dict]:
    return [c for c in chunks or [] if c.get("exact_provision")]


def in_evidence(cit: ParsedCitation, evidence: list[dict] | None) -> bool:
    """Is the provision's own text (or a deterministic engine result naming
    it) among the evidence the model saw?"""
    for item in evidence or []:
        if item.get("kind") == "statute" and is_exact(item, cit):
            return True
        if item.get("kind") == "engine":
            law = cit.key[0].split()[0]
            if re.search(rf"\b{law}\s*:\s*{re.escape(section_key(cit.section))}\b",
                         item.get("content", ""), re.IGNORECASE):
                return True
    return False


def prompt_rider(found: dict[str, bool], urdu: bool) -> str:
    """Generation instruction about the provisions the user named."""
    missing = [k for k, ok in found.items() if not ok]
    present = [k for k, ok in found.items() if ok]
    parts = []
    if present:
        parts.append(
            ("صارف نے " + "، ".join(present) + " کے بارے میں پوچھا ہے۔ اس کا اصل متن پہلا ماخذ ہے؛ جواب اسی پر رکھیں۔ "
             "شیڈول کی قطاریں یا دوسری دفعات جو صرف اس کا ذکر کرتی ہیں، اس کا متن نہیں ہیں۔") if urdu else
            (f"The user asked about {', '.join(present)}. Its own text is the FIRST source. Base the answer on "
             "that source. Schedule rows, tables or other provisions that merely mention it are NOT its text."))
    if missing:
        parts.append(
            ("، ".join(missing) + " کا متن دیے گئے ماخذ میں نہیں ہے۔ ایک جملے میں صاف بتائیں کہ اس کا متن یہاں دستیاب نہیں؛ "
             "اسے یادداشت سے یا کسی جدول/دوسرے قانون سے بیان نہ کریں۔") if urdu else
            (f"The text of {', '.join(missing)} is NOT among the sources. Say plainly, in one sentence, that its "
             "text is not available here. Do NOT define or describe it from memory, and do NOT treat a schedule "
             "row, table or another Act that mentions it as its text."))
    return "\n\n".join(parts)


NOT_FOUND_EN = ("I couldn't find the text of {p} in the legal sources available to me, so I can't reliably "
                "tell you what it says. Please check the official text of the law, or ask a lawyer.")
NOT_FOUND_UR = ("مجھے دستیاب قانونی ماخذ میں {p} کا متن نہیں ملا، اس لیے میں قابلِ اعتماد طور پر نہیں بتا سکتا کہ "
                "اس میں کیا لکھا ہے۔ براہِ کرم قانون کا سرکاری متن دیکھیں یا کسی وکیل سے رجوع کریں۔")
NOTE_EN = ("Note: the text of {p} was not found in the sources available here, so statements about it below "
           "are not verified against it.")
NOTE_UR = "نوٹ: {p} کا متن یہاں دستیاب ماخذ میں نہیں ملا، اس لیے نیچے اس کے بارے میں باتیں اس کے متن سے تصدیق شدہ نہیں ہیں۔"

_DEFINITIONAL = re.compile(
    r"^\s*(?:what\s+(?:is|does|are)|explain|define|meaning\s+of|tell\s+me\s+about)\b|\bkya\s+(?:hai|hota|kehta)\b"
    r"|کیا ہے|کیا کہتی|کیا کہتا", re.IGNORECASE)


def enforce(answer: str, question: str, evidence: list[dict] | None, urdu: bool,
            disclaimer: str = "") -> tuple[str, list[str]]:
    """The visible answer may not explain a named provision whose text the
    model never saw. Returns (answer, missing labels).

    A short "what is Section X" question is answered with an honest not-found
    message; a longer question keeps its answer behind a plain note."""
    cits = requested(question)
    missing = [label(c) for c in cits if not in_evidence(c, evidence)]
    if not missing:
        return answer, []
    names = ", ".join(missing)
    short = len((question or "").split()) <= 15 and _DEFINITIONAL.search(question or "")
    if short:
        body = (NOT_FOUND_UR if urdu else NOT_FOUND_EN).format(p=names)
        return (f"{body}\n\n{disclaimer}" if disclaimer else body), missing
    note = (NOTE_UR if urdu else NOTE_EN).format(p=names)
    return f"{note}\n\n{answer}", missing


def misattributed(claims: list[dict], evidence: list[dict] | None) -> list[dict]:
    """A claim that NAMES a provision absent from the evidence while its [n]
    markers point at a different Act's text is not supported by what it cites
    ("Section 489-F PPC defines the payee [6]", [6] = a CrPC schedule row).
    Downgrade-only."""
    by_id = {e["id"]: e for e in evidence or []}
    for claim in claims or []:
        if not claim.get("unresolved"):
            continue
        named = {normalise_statute(u.get("statute", "")) for u in claim["unresolved"]}
        cited = {normalise_statute(by_id[i].get("statute", "")) for i in claim.get("source_ids") or []
                 if i in by_id and by_id[i].get("kind") == "statute"}
        if cited and not (named & cited):
            claim["support"] = "unsupported"
            claim["support_reason"] = "names a provision but cites a different Act's text"
    return claims
