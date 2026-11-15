import re

from langchain_core.messages import AIMessage

from app.ai import answer_safeguards, cache, exact_provision, period_support
from app.ai.answer_citations import annotate_citations_from_evidence, apply_currency
from app.ai.source_links import apply_source_links
from app.ai.graph.state import AgentState
import logging

from app.ai.nodes.cache_node import (
    cache_block_reason,
    effective_language,
)
from app.ai.response_policy import cache_variant
from app.utils.pii import scrub_pii as _scrub_pii

_REFUSE = (
    "I was unable to provide a reliable answer based on the available Pakistani legal documents. "
    "Please consult a qualified Pakistani lawyer for accurate advice on your specific situation."
)

# Distinct message for a retrieval FAULT. Telling a user no relevant law was
# found, when in fact the search itself failed, is a false statement about the
# law — and it discourages them from simply retrying.
_REFUSE_ERROR = (
    "I hit a technical problem searching the legal documents and could not "
    "complete your request. Please try again in a moment. If it keeps happening, "
    "please consult a qualified Pakistani lawyer for your specific situation."
)

# Prompt leakage artifacts from LLM output
_LEAK_RE  = re.compile(
    r'(?im)^(System:|Human:|Assistant:|<\|im_start\||<\|im_end\||\[INST\]|<<SYS>>|Note to AI:|###\s*System).*$'
)

logger = logging.getLogger(__name__)


def _remove_leakage(text: str) -> str:
    return _LEAK_RE.sub('', text)


def _clean_markdown(text: str) -> str:
    # Collapse 3+ consecutive blank lines to 2
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Remove trailing whitespace on each line
    text = '\n'.join(line.rstrip() for line in text.splitlines())
    return text.strip()


def _sanitise(text: str) -> str:
    text = _remove_leakage(text)
    text = _scrub_pii(text)
    text = _clean_markdown(text)
    return text


def _sanitised_claims(claims: list[dict]) -> list[dict]:
    """Claim text goes through the same scrubbing the answer does.

    The claims were split from the PRE-sanitise answer inside hallucination_node,
    so a CNIC or phone number masked in the answer would otherwise survive
    verbatim in the claim quoted beside it — and the provenance record and the
    user-facing answer are supposed to redact identically.

    The verdicts are carried across unchanged rather than recomputed: re-splitting
    the sanitised text could renumber the claims and silently attach a verdict to
    a different sentence than the one it was made about.
    """
    return [{**claim, "text": _scrub_pii(claim.get("text", ""))} for claim in claims]


def _mark_removed(claims: list[dict], final_answer: str) -> list[dict]:
    """Claims whose sentence is no longer in the answer the user reads.

    Kept in the record (the audit should show what was withdrawn and why) but
    flagged, so nothing counts them as statements the answer still makes."""
    visible = period_support.normalise(final_answer)
    for claim in claims:
        text = period_support.normalise(claim.get("text", "")).strip()
        if text and text not in visible:
            claim["removed_from_answer"] = True
            claim["support"] = "unsupported"
    return claims


def _answer_llm_for_cache():
    """Attribution for the answer being cached. None when nothing generated it."""
    try:
        from app.ai.provider_health import current_turn
        turn = current_turn()
        return turn.answer_llm() if turn else None
    except Exception:
        return None


async def finalizer_node(state: AgentState) -> dict:
    # "Can you help me?" -- a fixed answer about what the assistant does, in the
    # asker's language; nothing retrieved, nothing cached (ai/client_help.py).
    from app.ai.client_help import is_capability_question, capability_answer
    if is_capability_question(state.get("query")) and not state.get("is_grounded"):
        text = capability_answer(state.get("language"), state.get("query"))
        return {
            "answer":             text,
            "confidence":         0.0,
            "is_grounded":        False,
            "convergence_status": "capability",
            "messages":           [AIMessage(content=text[:500])],
        }

    # Off-topic: triage_node already set the answer — just sanitise it.
    if state.get("convergence_status") == "off_topic":
        answer = state.get("answer", "")
        if answer:
            clean = _sanitise(answer)
            return {"answer": clean, "messages": [AIMessage(content=clean[:500])]}
        return {}

    # No answer was ever generated.
    if not state.get("answer"):
        failed = (state.get("arbitration_source") == "error"
                  or state.get("retrieval_error"))

        # A refusal the user can act on. "I couldn't find that" is indistinguish-
        # able from a retrieval miss, so a user asking for the current stamp duty
        # rate would simply rephrase and try again — the corpus will never hold
        # the answer, and saying so is more useful than another empty search.
        reason = state.get("refusal_reason")
        if reason and not failed:
            redirect = state.get("refusal_redirect")
            msg = reason + (f" You'll want {redirect} for that." if redirect else "")
            return {
                "answer":             msg,
                "confidence":         0.0,
                "is_grounded":        False,
                "convergence_status": "unanswerable",
                "messages":           [AIMessage(content=msg)],
            }

        # A LAWYER researching gets labelled general guidance instead of a
        # blank refusal when the library simply held too little (never on a
        # fault, and never in place of a refusal given for a reason above).
        # Not grounded, not cached, says so first. See ai/general_guidance.py.
        # And a CLIENT (2026-10-20) gets plain-language general information,
        # labelled the same way and pointing to a lawyer, instead of "I was
        # unable to provide a reliable answer" on a basic question.
        if not failed:
            from app.ai.answer_safeguards import SURFACE_CLIENT, SURFACE_RESEARCH
            if state.get("surface") in (SURFACE_RESEARCH, SURFACE_CLIENT):
                from app.ai import general_guidance
                guidance = await general_guidance.write(
                    state, audience="client" if state.get("surface") == SURFACE_CLIENT else "lawyer")
                if guidance:
                    return {
                        "answer":             guidance,
                        "confidence":         0.0,
                        "is_grounded":        False,
                        "convergence_status": "general_guidance",
                        "messages":           [AIMessage(content=guidance[:500])],
                    }

        msg = _REFUSE_ERROR if failed else _REFUSE
        return {
            "answer":             msg,
            "confidence":         0.0,
            "is_grounded":        False,
            # "error" keeps a fault out of the abstention statistics; a genuine
            # evidence-based refusal stays "max_attempts".
            "convergence_status": "error" if failed else "max_attempts",
            "messages":           [AIMessage(content=msg)],
        }

    is_grounded = state.get("is_grounded", False)
    clean       = _sanitise(state["answer"])

    # Label each citation by where it came from, against the FINAL answer text —
    # after sanitising, so the list describes exactly the words the user reads.
    #
    # Matched against `generation_evidence`, NOT reranked_chunks: a citation may
    # only be called "matched" against a source the model actually saw. Matching
    # on the full graded set let a chunk that never entered the prompt be
    # reported as the answer's source — a claim the system cannot support.
    # A citation to anything outside that set is `unresolved`, which is correct.
    #
    # Skipped on a cache hit: that path has an answer but no retrieval, so every
    # citation would match against an empty evidence set and be relabelled
    # "unresolved". The stored list was already annotated when it was written.
    citations = state.get("citations", [])
    claims = _sanitised_claims(state.get("claim_assessments") or [])
    removed: list[str] = []   # client chat: period statements withdrawn (audited)

    # Client chat: a stated period that no relied-on source states for this
    # matter is removed from the visible answer and replaced by one plain
    # notice (ai/period_support.py). Before citation annotation and the cache
    # write, so neither describes or stores text the user will not see. Not on
    # a cache hit: that entry was already cleaned when it was written.
    # Lawyer research gets the same guards when its safeguards are on
    # (ai/answer_safeguards.py), with lawyer-worded notices and a foreign-law
    # check; off, research is unchanged (rollback).
    research = answer_safeguards.research_on(state)
    urdu = state.get("language") == "ur"
    tool_conflicts = list(state.get("tool_conflicts") or [])
    if answer_safeguards.on(state) and not state.get("cache_hit"):
        # An answer that says a provision was not found / does not exist while
        # that provision's own text is in its evidence contradicts its evidence
        # (eval E1, ai/tool_contract.py). Generation no longer sees a lookup
        # miss for such a provision; this is the backstop for a model that
        # denies it anyway. Not repairable sentence by sentence -- the rest of
        # the answer is built on the false premise -- so it is withheld whole,
        # before citations, the cache write and provenance read it.
        from app.ai import tool_contract
        contradicted = tool_contract.contradicted_provisions(clean, state.get("generation_evidence") or [])
        if contradicted:
            from app.ai.nodes.generation_node import DISCLAIMER
            logger.info("finalizer: answer denied provision(s) present in evidence: %s", contradicted)
            clean = tool_contract.conflict_answer(contradicted, urdu=state.get("language") == "ur",
                                                  disclaimer=DISCLAIMER.strip())
            claims = _mark_removed(claims, clean)
            tool_conflicts.append({"tool": None, "provisions": contradicted,
                                   "resolution": "answer_withheld_denied_provision_in_evidence"})
        clean, removed = period_support.strip_unsupported_periods(
            clean, state.get("generation_evidence") or [], urdu=urdu,
            notice=((period_support.RESEARCH_NOTICE_UR if urdu else period_support.RESEARCH_NOTICE_EN)
                    if research else None))
        if removed:
            logger.info("finalizer: removed %d unsupported period statement(s)", len(removed))
            claims = _mark_removed(claims, clean)
        # A provision the user named whose text the model never saw may not be
        # explained from elsewhere (ai/exact_provision.py).
        from app.ai.nodes.generation_node import DISCLAIMER
        from app.ai.response_policy import presentation_base_query
        enforced, missing = exact_provision.enforce(
            clean, presentation_base_query(state) or state.get("query", ""),
            state.get("generation_evidence") or [], urdu=state.get("language") == "ur",
            disclaimer=DISCLAIMER.strip())
        if missing:
            logger.info("finalizer: named provision(s) not in evidence: %s", missing)
            clean = enforced
            claims = _mark_removed(claims, clean)
        # Research: Indian law presented as Pakistani authority is removed with
        # a note, unless the lawyer asked for a comparative view.
        if research:
            from app.ai import jurisdiction_guard
            clean, foreign = jurisdiction_guard.strip_foreign(
                clean, presentation_base_query(state) or state.get("query", ""), urdu=urdu)
            if foreign:
                logger.info("finalizer: removed %d foreign-law reference(s)", len(foreign))
                claims = _mark_removed(claims, clean)
            # The FINAL visible assertions (ai/visible_authority.py): no
            # "the Act is silent" from a few retrieved sections (eval E11 d2),
            # no period notice contradicting a verified period (E11 d1), no
            # omitted / mispaired / unverifiable authority left visible beside
            # a warning chip (RU2 d2). Last text change before citations, the
            # cache write, history and provenance.
            from app.ai import visible_authority
            question = presentation_base_query(state) or state.get("query", "")
            notice = period_support.RESEARCH_NOTICE_UR if urdu else period_support.RESEARCH_NOTICE_EN
            clean, silenced = visible_authority.whole_act_silence(clean, question, state.get("province"), urdu)
            clean, withheld = visible_authority.authorities(clean, question, urdu, research=True,
                                                            evidence=state.get("generation_evidence") or [])
            # Last: the notice must describe the text as it is finally shown
            # (eval V4 -- a sentence carrying the period was replaced AFTER the
            # notice had been worded "the period shown here").
            clean = visible_authority.precise_notice(clean, removed, notice, urdu)
            if silenced or withheld:
                logger.info("finalizer: whole-Act silence %d, authorities withheld %d", len(silenced), len(withheld))
                claims = _mark_removed(claims, clean)
                tool_conflicts += [{"tool": None, "resolution": "whole_act_silence_replaced", "text": s[:200]}
                                   for s in silenced]
                tool_conflicts += [{"tool": None, "resolution": "authority_withheld",
                                    "problems": w["problems"], "text": w["text"][:200]} for w in withheld]

    if not state.get("cache_hit"):
        # Client chat matches citations on dash/space-normalised text: models
        # write "489‑F" with a non-breaking hyphen, which parsed as section
        # "489" -- a DIFFERENT provision -- and the correct 489-F citation was
        # shown as an unresolved "489". Research keeps its existing matching.
        cite_text = answer_safeguards.citation_text(clean, state)
        citations = annotate_citations_from_evidence(
            cite_text, state.get("generation_evidence") or [])

    # Stamp repeal currency onto the citations and the claims resting on them.
    # Deterministic, no model, no extra call — it reads the same omission map
    # the drafting-path verifier uses. Two values only: `repealed` when the Act
    # declares the section omitted, `unknown` otherwise. Never `in_force`:
    # repeal data covers 4 of 43 statutes and is a lower bound, so silence is
    # absence of evidence, not evidence of currency.
    #
    # Applied on the cache-hit path too. A cached answer is served precisely
    # because it looks identical, and a provision repealed since the entry was
    # written must not inherit that entry's silence.
    apply_currency(citations, claims, province=state.get("province", "") or "")

    # The CPC on file is the PUNJAB Code text (ai/source_currency.py, batch 5).
    # Unless the turn's province is CONFIRMED Punjab (selected / case record --
    # not inferred, not unknown): a claim resting only on the CPC is not
    # "supported", a CPC citation's currency is "unknown", and one plain notice
    # says so in the answer. Every chat-graph surface; on cache hits too (an
    # entry written before this rule may carry "supported"); before the write.
    from app.ai import source_currency
    claims, citations, clean, _cpc = source_currency.apply_cpc_jurisdiction(
        claims, citations, clean, state.get("province"), state.get("jurisdiction_basis"),
        bool(state.get("province_inferred")), urdu=urdu,
        question=state.get("query") or "")

    # Authority availability (ai/authority_registry.py, batch 10) on the FINAL
    # visible answer -- fresh, follow-up or cache hit. The decision node already
    # refused a question that needs only unavailable law, and removed that
    # law's text from a mixed question's evidence; here the answered part is
    # marked plainly. An answer that reached this point WITHOUT that gate (a
    # cache entry, or any other bypass) is not shown from other law at all.
    from app.ai import authority_registry
    authority_withheld = False
    limits = state.get("authority_limits") or {}
    if limits.get("unavailable"):
        keys = [k for k in limits["unavailable"] if not (k == "cpc" and _cpc.get("notice"))]
        if keys:
            clean = clean.rstrip() + "\n\n" + authority_registry.limitation_message(
                keys, state.get("province"), state.get("jurisdiction_basis"),
                bool(state.get("province_inferred")), urdu=urdu, answered_rest=True)
    else:
        unavailable = authority_registry.assess_state(state)["unavailable"]
        if unavailable:
            logger.info("finalizer: answer withheld -- needs unavailable authority %s (gate not run)", unavailable)
            clean = authority_registry.limitation_message(
                unavailable, state.get("province"), state.get("jurisdiction_basis"),
                bool(state.get("province_inferred")), urdu=urdu)
            claims = _mark_removed(claims, clean)
            citations = []
            is_grounded = False
            authority_withheld = True

    # Write-through: cache generic, grounded answers so an identical later query
    # skips the retrieval→generation chain.
    #
    # Eligibility is `cache_block_reason` — THE SAME function the lookup node
    # consults. It used to be a separate expression here that happened to agree
    # with the one over there, which is not a property but a coincidence with a
    # maintenance schedule: a rule added to one file was a rule missing from the
    # other, and the direction that failed was always the same one — something
    # got written that should not have been.
    #
    # The two conditions below are genuinely write-only and stay here: an
    # ungrounded answer is not worth serving again, and a cache-hit passthrough
    # would rewrite the entry it just read.
    blocked = cache_block_reason(state)
    if blocked:
        logger.debug("cache: write-back declined (%s)", blocked)
    if (
        is_grounded
        and not blocked
        and not state.get("cache_hit")
        # Do not replay an Urdu-script answer to the next English asker if the
        # one-shot language repair failed. The current answer still goes out.
        and not state.get("language_mismatch")
        and not state.get("followup_intent")
    ):
        try:
            await cache.set_result(
                state.get("normalized_query") or state["query"],
                state.get("case_type", ""),
                state.get("province", ""),
                {
                    "answer":      clean,
                    # The ANNOTATED list, so a cache hit serves citations that
                    # still say which of them the answer actually cited.
                    "citations":   citations,
                    # Without this a cache hit would serve an answer whose every
                    # claim reads "unassessed" — a quality cliff invisible to the
                    # user, on a path chosen precisely because it looks identical.
                    "claims":      claims,
                    "confidence":  state.get("confidence", 0.0),
                    "is_grounded": True,
                    # Stored so a later cache hit can report the signals that
                    # were actually measured when this answer was produced,
                    # instead of the 0.0 initialisers of a turn where retrieval
                    # never ran. A hit is not evidence that the evidence was bad.
                    "relevance_score": state.get("relevance_score", 0.0),
                    "bm25_confidence": state.get("bm25_confidence", 0.0),
                    "signal_variance": state.get("signal_variance", 0.0),
                    # Who wrote this answer, recorded WHEN IT WAS WRITTEN. A
                    # later cache hit runs no generation, so without this the
                    # served answer has no author at all — and the previous
                    # design filled that gap with whatever model the current
                    # turn happened to touch last.
                    "answer_llm": _answer_llm_for_cache(),
                },
                # None → invalidate on TTL + embedding/chunking version only.
                # Collection-version busting activates once the ingest pipeline
                # calls cache.invalidate_collection (a later enhancement).
                collection_names=None,
                # Same identity the lookup will use. Written by the same helper
                # so the read and the write cannot disagree about which bucket
                # this answer belongs in.
                language=effective_language(state),
                variant=cache_variant(state),
            )
        except Exception:
            pass  # cache is best-effort — never fail the response on a cache error

    # Stamp a link onto every citation whose source document is actually held
    # here. Deliberately AFTER the cache write: a URL is derived from what is on
    # disk right now, so freezing one into a cache entry would outlive the file
    # it points at. A cache hit re-enters this line and is linked afresh.
    apply_source_links(citations)

    return {
        "answer":             clean,
        "citations":          citations,
        "claim_assessments":  claims,
        # The exact sentences the period guard removed, so every withdrawal can
        # be reviewed -- cited or not (claims cover only cited sentences).
        "periods_removed":    removed,
        "tool_conflicts":     tool_conflicts,
        "convergence_status": "converged" if is_grounded else "max_attempts",
        "messages":           [AIMessage(content=clean[:500])],
        **({"is_grounded": False, "confidence": 0.0, "refusal_kind": "source_unavailable_for_jurisdiction"}
           if authority_withheld else {}),
    }
