"""Does a cited source concern the QUESTION's subject at all? (lawyer research,
2026-10-14)

A grounding judge checks whether a claim follows from the text it cites. It
does not check whether that text is about the lawyer's problem. Live probe R3:
a dishonoured-cheque question got "Punjab Land Revenue Act s.91 -- remedy when
liability for an arrear [of land revenue] is denied" applied to it, and the
judge marked 14 of 15 claims "Supported". Each claim did follow from its
source; the sources were about something else.

So, deterministically and downgrade-only: a claim the judge called supported
or partial keeps that verdict only if at least one source it cites shares a
SUBJECT term with the question (its own words plus any case facts). If none
does, the verdict becomes `unassessed` with the reason "issue relevance not
established". Generic legal vocabulary ("suit", "court", "remedy", "client",
"section", "limitation", ...) does not count: it occurs in every source.

Limits, stated: lexical. A relevant source written in entirely different words
from the question is downgraded too (safe direction: the lawyer sees
"unassessed", not "supported"); an irrelevant source that happens to share a
subject word still passes. Engine output is computed for the question itself
and is not checked. When the question has no subject terms at all (e.g. "What
is Section 506 PPC?"), nothing is downgraded -- there is nothing to compare.
"""
from __future__ import annotations

from app.ai import period_support

# Words a lawyer's question uses that say nothing about the subject.
_QUESTION_GENERIC = frozenset("""
client clients party parties remedy remedies relief what which when where whom whose does have must
should could would advise advice options option available action actions step steps proceed procedure
time limit limits case matter lawyer advocate pakistan pakistani punjab law laws legal under section
explain tell about kindly please brief detail detailed possible
pay paid pays paying payable owe owed owes received receive given gave give took taken made done
""".split())
# ^ Verbs of payment and transfer say WHAT HAPPENED, not which body of law: a
#   rent question ("has not paid rent") and a land-revenue section ("person
#   paying an arrear") shared "paid" and the irrelevant section passed.


def question_terms(question: str, case_context: dict | None = None) -> set[str]:
    from app.ai.legal_terms import legal_terms
    text = question or ""
    if case_context:
        text += " " + " ".join(str(case_context.get(k) or "") for k in ("title", "description", "case_type"))
    terms = period_support.subject_terms(text) | period_support.subject_terms(" ".join(legal_terms(text)))
    return {t for t in terms if t not in _QUESTION_GENERIC}


def downgrade(claims: list[dict], evidence: list[dict] | None, question: str,
              case_context: dict | None = None) -> list[dict]:
    qterms = question_terms(question, case_context)
    if not qterms:
        return claims
    by_id = {e["id"]: e for e in evidence or []}
    # A source that IS a provision the question names is on the question's
    # issue by definition. Live eval A4 ("Punishment for 420 PPC?",
    # 2026-10-14): "punishment" does not stem-match "punished", so PPC 420's
    # own text was ruled irrelevant to a question about PPC 420 and every
    # claim fell to `unassessed` (ai/tool_contract.py).
    from app.ai import exact_provision, tool_contract
    named = tool_contract.provision_refs(question)
    for claim in claims or []:
        if claim.get("support") not in ("supported", "partial"):
            continue
        sources = [by_id[i] for i in claim.get("source_ids") or [] if i in by_id]
        if not sources or any(s.get("kind") == "engine" for s in sources):
            continue
        if any(exact_provision.is_exact(s, ref) for s in sources for ref in named):
            continue
        if not any(qterms & period_support.subject_terms(s.get("content", "")) for s in sources):
            claim["support"] = "unassessed"
            claim["support_reason"] = "issue relevance not established by the automated check"
    return claims
