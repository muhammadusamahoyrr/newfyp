"""The contract between the deterministic legal tools, retrieved statute text,
generation and claim verification (2026-10-14).

Reproduced failure (research eval E1): "punishment for cheating under Section
420 PPC". PPC 420's own text was retrieved as evidence [1]. The model called
find_offence_sections("Section 420 PPC"); the lookup compared the WHOLE query
string to section numbers and returned {"error": "No offence matched ..."}.
Generation was told engine output "OVERRIDES anything in the retrieved text",
so the answer said the offence "does not match any known provision"; the judge
was told engine output is "computed ground truth", so two "no offence matches"
claims were marked supported -- citing [1], the source that IS Section 420.

What this module fixes, as a contract rather than a prompt tweak:

1. ONE parser for explicit references (`provision_refs`): the citation parser
   the exact-provision guard already uses (exact_provision.requested), fed the
   same dash/space and Urdu/Roman-Urdu folding research citations use. No new
   normalisation rules.
2. Lookup outcomes are distinguished (`OUTCOME_*`): found / ambiguous /
   not_in_table / error. The offence table holds ~40 rows; "not in this table"
   says nothing about whether the provision exists.
3. Before generation (`reconcile`): a lookup MISS for a provision whose own text
   is in the retrieved sources is dropped -- the source supersedes it -- and
   the conflict is recorded. The model never sees both as equal facts.
4. After generation (`false_denial_claims`, `contradicted_provisions`): a
   claim, or an answer, that says a provision was not found / does not exist
   while that provision's text is in the evidence is contradicted by its own
   evidence -- never `supported`, and never shown as the answer.

Lexical, stated: a denial worded in a way `_DENIAL` does not know is not
caught by the backstop (the reconciliation before generation still applies).
"""
from __future__ import annotations

import re

CONTRACT_VERSION = "tool-contract-v1"

OUTCOME_FOUND = "found"
OUTCOME_AMBIGUOUS = "ambiguous"
OUTCOME_NOT_IN_TABLE = "not_in_table"
OUTCOME_ERROR = "error"
_MISSES = (OUTCOME_NOT_IN_TABLE, OUTCOME_ERROR)

# Tools whose miss is pure IDENTIFICATION: a retrieved source that is the named
# provision answers the same question better. (A bail-classification miss is
# not dropped: the source text does not say whether an offence is bailable.)
_IDENTIFYING_TOOLS = {"find_offence_sections"}

NOT_IN_TABLE_NOTE = (
    "This small offence lookup table does not cover {what}. That is NOT evidence that the provision "
    "does not exist: answer from the statute text if it is in the sources, and otherwise say the point "
    "could not be verified. Never state that the provision does not exist.")


_BARE_NUMBER_ACT = re.compile(r"(?<![\w.-])(\d{1,3}(?:-[A-Za-z])?)\s+(PPC|CrPC|CPC)\b")
# A number after one of these words is NOT a section: "Order XXXIX Rule 1 CPC"
# is a rule of the First Schedule, never CPC section 1 (the confusion the
# identity index exists to prevent). The word before the number decides.
_NOT_A_SECTION = re.compile(r"(?:\b(?:rule|rules|r|order|o|article|art|schedule|para|paragraph|clause|"
                            r"section|sec|s)\.?|\b[IVXLC]+|رول|قاعدہ|آرڈر|حکم|دفعہ)\s*$", re.IGNORECASE)
# ... and a number CONTINUING such a list: "Rules 1 and 2 CPC" is Order/Rule
# 1 and 2, never CPC section 2 (2026-10-16, batch 6; it was read as s.2).
_LIST_OF_NOT_SECTIONS = re.compile(
    r"(?:\b(?:rules?|r|articles?|art|paras?|paragraphs?|clauses?)\.?|رول|قاعدہ)\s*\d{1,3}[A-Za-z]?"
    r"(?:\s*\(\w{1,3}\))*(?:\s*(?:,|and|&|اور)\s*\d{1,3}[A-Za-z]?(?:\s*\(\w{1,3}\))*)*\s*(?:,|and|&|اور)\s*$",
    re.IGNORECASE)


def _compact_form(m: re.Match) -> str:
    if _NOT_A_SECTION.search(m.string[max(0, m.start() - 24): m.start()]) \
            or _LIST_OF_NOT_SECTIONS.search(m.string[max(0, m.start() - 60): m.start()]):
        return m.group(0)                 # already a section ref, or a rule / article / order number
    return f"Section {m.group(1)} {m.group(2)}"


_CODE_ORDER = re.compile(r"\b(Criminal|Civil)\s+Procedure\s+Code\b", re.IGNORECASE)


def provision_refs(text: str) -> list:
    """Explicit Act + provision references in `text`, canonical, de-duplicated.

    "Section 420 PPC" -> (PPC, 420); "489‑F PPC" -> (PPC, 489-F), never 489;
    "پی پی سی دفعہ 302" and "dafa 302 PPC" -> (PPC, 302). A bare "420" names no
    statute and yields nothing (the caller falls back to its own search).
    """
    from app.ai import answer_safeguards, exact_provision, period_support
    folded = answer_safeguards.urdu_citation_forms(period_support.normalise(text or ""))
    # "Criminal Procedure Code" / "Civil Procedure Code": the shared parser
    # knows only the "Code of ..." order and read these as unknown statutes.
    folded = _CODE_ORDER.sub(lambda m: f"Code of {m.group(1).title()} Procedure", folded)
    # The compact form a tool argument often takes ("489-F PPC", "302 PPC"):
    # the citation parser wants a section word before a number that precedes
    # its Act. Only a number directly followed by a known Act name is touched.
    folded = _BARE_NUMBER_ACT.sub(_compact_form, folded)
    out, seen = [], set()
    for cit in exact_provision.requested(folded):
        if cit.key not in seen:
            seen.add(cit.key)
            out.append(cit)
    return out


def outcome_of(result) -> str | None:
    """The lookup outcome of one tool payload; legacy payloads are read by
    their old shape (an `error` key was the only miss signal)."""
    if not isinstance(result, dict):
        return None
    if result.get("outcome"):
        return result["outcome"]
    if "error" in result:
        return OUTCOME_ERROR
    if result.get("found") is False:
        return OUTCOME_NOT_IN_TABLE
    return None


def _exact_sources(ref, sources: list[dict] | None) -> list[dict]:
    from app.ai import exact_provision
    return [s for s in sources or [] if s.get("kind", "statute") == "statute" and exact_provision.is_exact(s, ref)]


def reconcile(tool_results: list[dict] | None, sources: list[dict] | None) -> tuple[list[dict], list[dict]]:
    """(tool results to give generation, conflicts found).

    `sources` are retrieved statute chunks (or evidence items): anything with
    `statute` and `content`. A lookup miss for a provision whose own text is
    among them is superseded and dropped; any other result is kept unchanged.
    """
    kept, conflicts = [], []
    for res in tool_results or []:
        name = res.get("tool")
        outcome = outcome_of(res.get("result"))
        if name in _IDENTIFYING_TOOLS and outcome in _MISSES:
            args = res.get("args") or {}
            refs = provision_refs(" ".join(str(v) for v in args.values()))
            covered = [r for r in refs if _exact_sources(r, sources)]
            if covered:
                from app.ai import exact_provision
                conflicts.append({"tool": name, "outcome": outcome,
                                  "provisions": [exact_provision.label(r) for r in covered],
                                  "resolution": "lookup_miss_superseded_by_exact_source"})
                continue
        kept.append(res)
    return kept, conflicts


# A denial counts only when it is ABOUT the named provision -- the provision is
# the subject or object of the denial, inside one clause:
#   ref AFTER the trigger:  "no offence matching <X>", "no offence matches the
#                           query <X>", "I couldn't find (the text of) <X>"
#   ref BEFORE the trigger: "<X> was not found", "<X> does not exist",
#                           "<X> ... does not match any known provision",
#                           "<X> is not a valid section", "<X> ... نہیں ملی"
# Live eval E11 (2026-10-14) is why: "No provision on pre-emption time limits
# is found in the supplied sections (... s.75; ... s.24)" is a TRUE statement
# about what those sections contain, and the first version of this check --
# any denial word plus any provision anywhere in the sentence -- withheld it.
_DENY_THEN_REF = re.compile(
    r"\bno (?:such )?(?:offen[cs]e|section|provision|law)s?\s+(?:match(?:es|ing)?|named|called|titled)\b"
    r"|\b(?:could(?: not|n't)|can(?:not|'t)|did(?: not|n't)|unable to) find\b",
    re.IGNORECASE)
_REF_THEN_DENY = re.compile(
    r"\b(?:was|were|is|are|could|can)\s*(?:not|n't)\s+(?:be\s+)?(?:found|located|identified)\b"
    r"|\bdoes(?: not|n't) (?:exist|match any)"
    r"|\bis not (?:a )?(?:valid|recogni[sz]ed|known) (?:section|provision|offen[cs]e)"
    r"|نہیں مل[اینے]|موجود نہیں",
    re.IGNORECASE)
# What ends the clause a denial speaks about.
_CLAUSE_END = re.compile(r"[;:()\[\]\n]|,\s|\s(?:and|but|while|whereas|because|so)\s|[.?!۔](?:\s|$)")
_SPAN = 90
# Any denial trigger at all -- the cheap pre-check, and what callers test.
_DENIAL = re.compile(f"(?:{_DENY_THEN_REF.pattern})|(?:{_REF_THEN_DENY.pattern})", re.IGNORECASE)


def _denied_refs(sentence: str) -> list:
    from app.ai import period_support
    text = period_support.normalise(sentence or "")
    out, seen = [], set()

    def take(span: str):
        for ref in provision_refs(span):
            if ref.key not in seen:
                seen.add(ref.key)
                out.append(ref)

    for m in _DENY_THEN_REF.finditer(text):
        after = text[m.end(): m.end() + _SPAN]
        stop = _CLAUSE_END.search(after)
        take(after[: stop.start()] if stop else after)
    for m in _REF_THEN_DENY.finditer(text):
        before = text[max(0, m.start() - _SPAN): m.start()]
        cut = max((x.end() for x in _CLAUSE_END.finditer(before)), default=0)
        take(before[cut:])
    return out


def false_denial_claims(claims: list[dict], evidence: list[dict] | None) -> list[dict]:
    """Downgrade-only: a claim that a provision was not found / does not exist
    can never be supported while that provision's own text is in the evidence."""
    for claim in claims or []:
        if claim.get("support") not in ("supported", "partial"):
            continue
        if any(_exact_sources(ref, evidence) for ref in _denied_refs(claim.get("text", ""))):
            claim["support"] = "unsupported"
            claim["support_reason"] = "the evidence contains this provision's text; the claim that it was not found contradicts it"
    return claims


def contradicted_provisions(answer: str, evidence: list[dict] | None) -> list[str]:
    """Labels of provisions the answer denies while their text is in evidence."""
    from app.ai import exact_provision, period_support
    from app.ai.answer_citations import _SENTENCE_SPLIT
    out: list[str] = []
    for sentence in _SENTENCE_SPLIT.split(period_support.normalise(answer or "")):
        for ref in _denied_refs(sentence):
            label = exact_provision.label(ref)
            if label not in out and _exact_sources(ref, evidence):
                out.append(label)
    return out


# Worded WITHOUT denial phrasing ("not found", "نہیں ملی"): this text is itself
# an answer, and must not read as one more denial of the provision.
CONFLICT_EN = ("I could not produce a verified answer to this question. The draft answer wrongly treated {p} as "
               "missing, yet the text of {p} is among the sources retrieved for it, so the draft contradicted its "
               "own evidence and has been withheld. Please read {p} directly in the sources listed, or ask again.")
CONFLICT_UR = ("میں اس سوال کا تصدیق شدہ جواب تیار نہیں کر سکا۔ مسودہ جواب میں {p} کو غلط طور پر غیر حاضر سمجھا گیا، حالانکہ "
               "{p} کا متن حاصل شدہ ماخذ میں شامل ہے، اس لیے یہ مسودہ اپنے ہی ماخذ سے متصادم تھا اور روک لیا گیا ہے۔ براہِ کرم "
               "{p} کو براہِ راست ماخذ میں پڑھیں یا دوبارہ پوچھیں۔")


def conflict_answer(labels: list[str], urdu: bool, disclaimer: str = "") -> str:
    body = (CONFLICT_UR if urdu else CONFLICT_EN).format(p=", ".join(labels))
    return f"{body}\n\n{disclaimer}" if disclaimer else body
