"""Intake evidence gate (Batch 4, 2026-10-12).

Between grading and generation. The intake graph used to go straight from the
grader to the analysis, so whatever survived grading -- including the three
weak chunks the scorer guaranteed and the ungraded tail -- became "the law" of
the client's case. This node decides, auditably, whether a LEGAL analysis can
be grounded at all, and in what state.

FOUR SEPARATE QUESTIONS, NOT ONE SCORE
  1. Did retrieval run?                 retrieval_error  vs  everything else
  2. Is each passage admissible?        jurisdiction, omitted/superseded section
  3. Can this corpus answer this kind   live rates, court statistics, personal
     of request at all?                 records (query-side, intake-specific)
  4. Is anything left?                  supported / partially_supported / why not

Retrieval confidence is ONE input to the supported/partial split. It is not
used to decide answerability: measured on this corpus, answerable and
unanswerable scores overlap (0.309-0.662 vs 0.273-0.412).

A case is created whatever this decides. A non-supported status only means the
analysis is limited to the client's own facts: no legal conclusion, no cited
law, no invented recommendation.

CAPABILITY IS DECIDED BEFORE EVIDENCE (v2, 2026-10-13 acceptance review)
v1 let a capability failure through as "partially_supported" whenever ANY
chunk survived, and partial generated a full legal analysis -- so an
unrelated federal chunk plus a live-rate question, or an unrelated CPC chunk
plus "under the Contract Act", became a legal answer. Now:
  * a request the corpus cannot answer (pure live rate / court statistic /
    personal record, or a named instrument the corpus does not hold) is
    `corpus_not_capable` whatever was retrieved;
  * `partially_supported` exists ONLY for a request decomposed into issues
    (`scope_issues`) whose retrieval was run on the supported issue alone
    (`issue_scope.retrieval_bound`). Unbound mixed requests are facts-only;
  * weak relevance / dropped passages / a failed branch no longer make a
    "partial" -- they are recorded caveats on a supported status.

THE PROVISION THE CLIENT NAMED (v3, 2026-10-13 corrective batch)
v2 checked whether RETRIEVED passages were omitted, never whether the
provision the client explicitly asked about is. "Can a first offender be
released on probation under section 562 of the CrPC?" retrieved CrPC s.388,
the gate said "supported", and the analysis advised filing under s.562 --
omitted in 1960. Now every explicit citation in the client's text (parsed by
the strict citation parser, canonicalised against the corpus index) is
checked against the CONFIRMED omission records first:
  * a sentence whose only named provisions are confirmed omitted is an
    unsupported issue of kind `omitted_provision` -- pure: not capable;
    mixed: the existing issue binding applies;
  * a live, held provision the client named must actually be among the
    admissible passages, or the status is no_relevant_evidence -- a
    neighbouring section never answers a question about a named one;
  * a lettered provision (489-F) is never judged by its parent's status.
"""
from __future__ import annotations

import logging
import re

from app.ai.graph.state import AgentState

logger = logging.getLogger(__name__)

GATE_VERSION = "intake-evidence-gate-v5"       # v4: CPC by provenance; v5: authority registry
ISSUE_SCOPE_VERSION = "intake-issue-scope-v1"

SUPPORTED = "supported"
PARTIAL = "partially_supported"
NEEDS_CLARIFICATION = "needs_clarification"
NOT_CAPABLE = "corpus_not_capable"
NO_EVIDENCE = "no_relevant_evidence"
WRONG_JURISDICTION = "wrong_jurisdiction"
SUPERSEDED = "outdated_or_superseded"
RETRIEVAL_ERROR = "retrieval_error"
# Batch 9: the question needs the CPC, and no CPC text applicable to the
# matter's province is held (ai/source_currency.py).
SOURCE_UNAVAILABLE = "source_unavailable_for_jurisdiction"

GROUNDED_STATUSES = (SUPPORTED, PARTIAL)
ALL_STATUSES = (SUPPORTED, PARTIAL, NEEDS_CLARIFICATION, NOT_CAPABLE, NO_EVIDENCE,
                WRONG_JURISDICTION, SUPERSEDED, RETRIEVAL_ERROR)

# Kinds of request a statutory corpus cannot answer, whatever is retrieved.
# "outcome_prediction" is deliberately NOT here: a client asking "will I win?"
# at intake still has a case worth analysing.
_INTAKE_NOT_CAPABLE = {"live_rate", "court_statistic", "personal_record"}
_MIN_STORY_WORDS = 5
_RELEVANCE_SUPPORTED = 0.4      # one input among several, never the decider of answerability


# An instrument the CLIENT names ("under the Contract Act") that the corpus
# does not hold. Retrieval then returns neighbouring law (CPC) that reads as
# relevant; measured on the dev set, the Contract Act question came back
# "supported" on CPC. Deterministic: corpus list + the shared name normaliser.
_NAMED = re.compile(r"((?:[A-Za-z][\w'()-]*\s+){1,5}(?:act|ordinance|order|code))\b", re.IGNORECASE)
_NAME_STOP = {"the", "this", "that", "a", "an", "under", "of", "my", "our", "which", "any", "in", "to",
              "per", "as", "by", "for", "ke", "ka", "ki", "tehat"}


def _corpus_keys() -> list[str]:
    import json
    from pathlib import Path
    from app.ai.answer_citations import normalise_statute
    data = json.loads((Path(__file__).resolve().parent.parent / "data" / "corpus_instruments.json")
                      .read_text(encoding="utf-8"))
    return [normalise_statute(n) for n in data.get("instruments") or []]


def named_missing_instruments(text: str) -> list[str]:
    """Instruments named in `text` that match nothing in the corpus."""
    try:
        from app.ai.answer_citations import normalise_statute
        keys = _corpus_keys()
    except Exception:  # noqa: BLE001 -- unknown corpus: claim nothing
        return []
    missing = []
    for m in _NAMED.finditer(text or ""):
        words = m.group(1).split()
        known, core = False, None
        # "claim under the Contract Act": when the name is written in capitals,
        # it starts at a capitalised word. All-lowercase (Roman Urdu) is taken as is.
        has_caps = any(w[:1].isupper() for w in words[:-1])
        for k in range(2, len(words) + 1):
            cand = words[-k:]
            if cand[0].lower() in _NAME_STOP or cand[0] == "I":
                continue
            if has_caps and not all(w[:1].isupper() or w.lower() in ("of", "and", "for", "on")
                                    for w in cand[:-1]):
                continue
            key = normalise_statute(" ".join(cand))
            core = " ".join(cand)          # longest name without a leading stop word
            if any(key == ck or key in ck or ck in key for ck in keys if ck):
                known = True
                break
        if not known and core and core not in missing:
            missing.append(core)
    return missing


_SENTENCE = re.compile("[^.?!\u061f\u06d4\u0964\n]+[.?!\u061f\u06d4\u0964]*")


def _sentences(text: str) -> list[str]:
    return [m.group(0).strip() for m in _SENTENCE.finditer(text or "") if m.group(0).strip()]


def requested_provisions(text: str, index=None) -> list[dict]:
    """Explicit section/article citations in `text`, with CONFIRMED currency.

    Reuses the strict citation parser (an explicit marker and a named
    instrument are required), so a fact story never yields a target. Only a
    confirmed omission record (named instrument and date) makes a provision
    `omitted`; a lettered provision is never matched to its parent's record.
    """
    try:
        from app.ai.citation_verification import parse_statute_citations
        from app.ai.corpus_index import canonical_section, get_index
        idx = index if index is not None else get_index()
        cites = parse_statute_citations(text or "", idx)
    except Exception:  # noqa: BLE001 -- no parser/index: no targets claimed
        return []
    out, seen = [], set()
    for c in cites:
        if c.unit not in ("section", "article"):
            continue
        statute = idx.canonical(c.statute)
        section = canonical_section(c.section)
        if (statute or c.statute, section) in seen:
            continue
        seen.add((statute or c.statute, section))
        rec = None
        if statute and re.fullmatch(r"\d+", section or ""):
            try:
                from app.ai.statute_omissions import record_for
                found = record_for(statute, int(section))
                rec = found if found is not None and found.is_omitted else None
            except Exception:  # noqa: BLE001 -- unknown currency is not "omitted"
                rec = None
        out.append({"statute": statute or c.statute, "section": section, "in_corpus": bool(statute),
                    "omitted": rec is not None,
                    "omitted_by": rec.cite() if rec is not None else "",
                    "omission": rec.to_dict() if rec is not None else None})
    return out


def _omitted_only(sentence: str, index=None) -> bool:
    targets = requested_provisions(sentence, index)
    return bool(targets) and all(t["omitted"] for t in targets)


def _chunk_provision(chunk: dict) -> tuple[str, str]:
    """(statute, canonical provision) of a passage, the lost letter restored
    from its own header -- the binder's rule."""
    from app.ai.corpus_index import canonical_section
    from app.ai.intake_evidence import canonical_section as from_header
    sec = from_header({"section": chunk.get("section_number") or chunk.get("section") or "",
                       "content": chunk.get("content") or ""})
    return (chunk.get("statute") or "").strip(), canonical_section(sec)


def _capability_kind(text: str) -> str | None:
    try:
        from app.ai.pipelines.answerability import check
        verdict = check(text or "")
    except Exception:  # noqa: BLE001 -- an unknown kind claims nothing
        return None
    return verdict.kind if verdict and verdict.kind in _INTAKE_NOT_CAPABLE else None


def scope_issues(text: str, index=None) -> dict:
    """Decompose a request into the issues the corpus can and cannot address.

    Sentence-level and deterministic. A sentence asking for a live rate, a
    court statistic or a personal record is an UNSUPPORTED issue; the rest of
    the story is the supported issue. A named instrument the corpus does not
    hold is not decomposed: it is the law the client says governs the whole
    dispute, so neighbouring law must not stand in for it.
    """
    unsupported, kept = [], []
    for sent in _sentences(text):
        kind = _capability_kind(sent) or ("omitted_provision" if _omitted_only(sent, index) else None)
        if kind:
            unsupported.append({"text": sent, "kind": kind})
        else:
            kept.append(sent)
    whole = _capability_kind(text)
    if not unsupported and whole:
        # Matched only across sentence boundaries: the whole text is the issue.
        unsupported, kept = [{"text": (text or "").strip(), "kind": whole}], []
    supported_text = " ".join(kept).strip()
    return {
        "version": ISSUE_SCOPE_VERSION,
        "unsupported": unsupported,
        "supported_text": supported_text,
        "pure": bool(unsupported) and len(supported_text.split()) < _MIN_STORY_WORDS,
        "missing_instruments": named_missing_instruments(text or ""),
    }


def strip_unsupported(text: str, scope: dict) -> str:
    """`text` without the unsupported issue sentences (for the retrieval query)."""
    out = text or ""
    for issue in (scope or {}).get("unsupported") or []:
        out = out.replace(issue["text"], " ")
    return " ".join(out.split())


def _bound(issue_scope: dict | None, scope: dict) -> bool:
    """Was retrieval run on the supported issue only, for THIS decomposition?"""
    if not issue_scope or not issue_scope.get("retrieval_bound"):
        return False
    return ([i.get("text") for i in issue_scope.get("unsupported") or []]
            == [i["text"] for i in scope["unsupported"]])


def _section_int(section) -> int | None:
    m = re.match(r"\s*(\d+)", str(section or ""))
    return int(m.group(1)) if m else None


def _omitted(statute: str, section) -> bool:
    """True only for a section CONFIRMED omitted. Lettered sections (489-F) are
    not the omitted parent (489) and must not be dropped by number alone."""
    if re.search(r"\d\s*-?\s*[A-Za-z]", str(section or "")):
        return False
    n = _section_int(section)
    if n is None:
        return False
    try:
        from app.ai.statute_omissions import omitted_for
        return n in omitted_for(statute)
    except Exception:  # noqa: BLE001 -- unknown currency is not "omitted"
        return False


def decide(*, chunks: list[dict], retrieval_error: bool, province: str,
           user_text: str, relevance_score: float | None,
           issue_scope: dict | None = None, index=None,
           basis: str | None = None, inferred: bool = False) -> tuple[list[dict], dict]:
    """(admissible chunks, gate record). Pure: testable without a graph."""
    from app.ai import authority_registry as ar
    from app.ai import source_currency as sc
    province = (province or "").lower()
    # AUTHORITY AVAILABILITY (batch 9: CPC; batch 10: the registry in
    # ai/authority_registry.py -- CPC, Punjab pre-emption, Punjab rented
    # premises, Specific Relief). A chunk of a registered authority is
    # admissible only where its SOURCE is this matter's CONFIRMED law -- read
    # from provenance, not its `province` label. And a question that clearly
    # needs a registered authority this matter does not hold is answered as
    # `source_unavailable_for_jurisdiction` -- never "supported" on whatever
    # unrelated law retrieval left behind.
    need = sc.cpc_requirement(user_text or "")
    cpc_ok = sc.cpc_text_available(province, basis, inferred)
    cpc_scope = sc.cpc_scope(province, basis, inferred)
    authority = ar.assess(user_text or "", province, basis, inferred)
    own = authority["own"]
    blocked = authority["unavailable"]
    admissible, dropped = [], {"wrong_jurisdiction": 0, "omitted_section": 0, "cpc_not_applicable": 0}
    for c in chunks or []:
        ok = ar.chunk_admissible(c, own)
        if ok is not None:
            if not ok:
                dropped["cpc_not_applicable" if ar.chunk_authority(c)[0] == "cpc" else "wrong_jurisdiction"] += 1
                continue
        else:
            cprov = (c.get("province") or "federal").lower()
            if c.get("source_type", "statute") == "statute" and cprov not in ("federal", "", province):
                dropped["wrong_jurisdiction"] += 1
                continue
        if (c.get("provision_status") == "omitted"
                or _omitted(c.get("statute") or "", c.get("section_number"))):
            dropped["omitted_section"] += 1
            continue
        admissible.append(c)

    scope = scope_issues(user_text or "", index)
    requested = requested_provisions(user_text or "", index)
    missing_instruments = scope["missing_instruments"]
    capability = None
    if missing_instruments:
        capability = "instrument_not_in_corpus"
    elif scope["unsupported"]:
        capability = scope["unsupported"][0]["kind"]
    mixed = bool(scope["unsupported"]) and not scope["pure"] and not missing_instruments
    bound = mixed and _bound(issue_scope, scope)
    thin = len((user_text or "").split()) < _MIN_STORY_WORDS

    reasons, caveats = [], []
    # QUERY-SIDE CAPABILITY FIRST: no retrieved chunk can make these answerable.
    if missing_instruments:
        status = NOT_CAPABLE
        reasons.append("the request names law the corpus does not hold: " + ", ".join(missing_instruments))
    elif scope["unsupported"] and scope["pure"]:
        status = NOT_CAPABLE
        if capability == "omitted_provision":
            reasons.append("the provision requested is recorded as omitted: " + "; ".join(
                f"{t['statute']} s.{t['section']} {t['omitted_by']}".strip()
                for t in requested if t["omitted"]))
        else:
            reasons.append(f"the request is a {capability.replace('_', ' ')} the corpus cannot give")
    elif mixed and not bound:
        status = NOT_CAPABLE
        reasons.append("part of the request cannot be answered and the evidence was not bound "
                       "to the answerable part")
    elif blocked and not authority["other_law"]:
        # Structural, before any judge: no amount of other retrieved law is
        # support for a question whose governing law this matter does not hold.
        status = SOURCE_UNAVAILABLE
        reasons.append(sc.cpc_unavailable_reason(province, basis, inferred) if blocked == ["cpc"]
                       else ar.unavailable_reason(blocked, province, basis, inferred))
    elif retrieval_error and not admissible:
        status = RETRIEVAL_ERROR
        reasons.append("retrieval did not run")
    elif not admissible:
        if dropped["wrong_jurisdiction"] and not dropped["omitted_section"]:
            status = WRONG_JURISDICTION
        elif dropped["omitted_section"]:
            status = SUPERSEDED
        elif capability and not bound:
            status = NOT_CAPABLE
        elif thin:
            status = NEEDS_CLARIFICATION
        else:
            status = NO_EVIDENCE
        reasons.append("no admissible legal passage")
    else:
        if retrieval_error:
            caveats.append("some retrieval branches failed")
        if any(dropped.values()):
            caveats.append("inadmissible passages removed")
        for key in blocked:
            caveats.append("CPC not held for this province: the CPC part of the question is not answered"
                           if key == "cpc" else
                           f"{ar.REGISTRY[key]['short']} not held for this province: that part of the "
                           "question is not answered")
        if relevance_score is not None and relevance_score < _RELEVANCE_SUPPORTED:
            caveats.append("low retrieval relevance")
        # A provision the client NAMED (live, held by the corpus) must be among
        # the admissible passages; a neighbouring section is not an answer.
        live_targets = {(t["statute"], t["section"]) for t in requested
                        if t["in_corpus"] and not t["omitted"]
                        and (ar.chunk_authority({"statute": t["statute"]}) or ("",))[0] not in blocked}
        have = {_chunk_provision(c) for c in admissible}
        if live_targets and not (live_targets & have):
            status = NO_EVIDENCE
            reasons.append("the provision requested was not among the retrieved passages: " + ", ".join(
                f"{st} s.{sec}" for st, sec in sorted(live_targets)))
        elif bound:
            # The ONLY partial: legal analysis limited to the supported issue,
            # whose retrieval never saw the unsupported sentences.
            status = PARTIAL
            reasons.append("legal analysis limited to the answerable issue; "
                           + "; ".join(i["kind"].replace("_", " ") for i in scope["unsupported"])
                           + " not answerable from the corpus")
        else:
            status = SUPPORTED

    record = {
        "version": GATE_VERSION,
        "status": status,
        "reasons": reasons,
        "admissible": len(admissible),
        "considered": len(chunks or []),
        "dropped": dropped,
        "capability": capability,
        "missing_instruments": missing_instruments,
        "caveats": caveats,
        "requested_provisions": requested,
        "authority": {"cpc_required": need["required"], "explicit": need["explicit"],
                      "procedural": need["procedural"], "other_law": need["other_law"],
                      "cpc_available": cpc_ok, "scope": cpc_scope,
                      "required": authority["required"], "unavailable": blocked, "own": own},
        "issue_scope": {
            "version": scope["version"],
            "supported_issue": scope["supported_text"] if status == PARTIAL else None,
            "unsupported_issues": scope["unsupported"],
            "retrieval_bound": bound,
        },
        "relevance_score": relevance_score,
        "retrieval_error": bool(retrieval_error),
    }
    return admissible, record


async def intake_evidence_gate_node(state: AgentState) -> dict:
    admissible, record = decide(
        chunks=state.get("reranked_chunks") or [],
        retrieval_error=bool(state.get("retrieval_error")),
        province=state.get("province") or "",
        user_text=state.get("user_text") or state.get("query") or "",
        relevance_score=state.get("relevance_score"),
        issue_scope=state.get("issue_scope"),
        basis=state.get("jurisdiction_basis"),
        inferred=bool(state.get("province_inferred")),
    )
    logger.info("intake gate: %s (admissible %d of %d, dropped %s)",
                record["status"], record["admissible"], record["considered"], record["dropped"])
    return {"reranked_chunks": admissible if record["status"] in GROUNDED_STATUSES else [],
            "evidence_gate": record}
