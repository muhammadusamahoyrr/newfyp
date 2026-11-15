"""The intake analysis output contract -- one choke point (2026-10-13).

Every intake analysis that came out of the graph passes through `enforce`
inside `_run_intake_ai`, AFTER the evidence gate's verdict is applied and
BEFORE provenance is recorded, the result localised, stored or returned. So
the stored analysis, the client-facing analysis, the provenance record and a
retry's result are the same object.

WHY
The pipeline already KNEW what was wrong and showed it anyway: m004's action
"register the case under Section 381 of the PPC" was judged `unsupported`
against the bound passage (PPC 381-A), and d037's "file an application for
probation under Section 562" (omitted in 1960) was flagged as an uncited legal
action -- both reached the client as instructions, with a caution appended
below. A caution is not a substitute for removing the instruction.

THE RULES (deterministic; no model call)
  1. A LEGAL action is shown only when its claim is `matched` to a bound
     passage, the judge did not call it `unsupported`, and it is not in the
     uncited-legal list. Otherwise it is REMOVED (never silently re-cited: a
     wrong section is not corrected to the passage's section, because the judge
     already said the passage does not support the action as written).
  2. Any action that names a provision the gate recorded as omitted is
     removed, whatever its kind ("obtain the full text of s.562" presents dead
     law as live).
  3. When the gate did not ground the analysis (facts-only), every legal
     action is removed.
  4. For a partial analysis, any summary sentence or action that is itself an
     unsupported issue (a live rate, a statistic, a personal record, an
     omitted provision) is removed.
  5. Citations that did not bind to evidence are withheld from
     `law_citations` / `applicable_laws` and kept under `withheld_citations`
     for audit; they can no longer support anything.
  6. Removed legal actions are replaced by ONE neutral lawyer-review step.
  7. With no legal substance left (no bound citation, no supported legal
     action) a supported/partial analysis is downgraded: not grounded, no
     risk reading, status `no_supported_legal_content`.
  8. An omitted requested provision gets a deterministic currency notice from
     the omission record (instrument and date) -- never the provision's text.
  9. (v2) The model's own legal/general label cannot exempt an action: a
     deterministic classifier (`is_formal_legal_action`) marks formal legal
     steps -- filing, lodging, applying for bail/probation/stay, serving a
     legal notice, proceeding under a named section -- as legal whatever the
     label says. d037's "If advised, prepare and file an application for
     probation" was labelled "general" by the model and survived v1.
 10. (v2) A formal legal step must rest on a claim judged fully `supported`
     when the analysis is partial or the claim itself is only partially
     supported; otherwise it is withheld.
 11. (v2) A SUMMARY the judge called `unsupported` is replaced by a fixed
     notice plus the client's own words in a PARTIAL analysis, or whenever no
     fully supported legal action remains -- and in that second case the
     citations are withheld too and the analysis is downgraded. (Observed: a
     theft + gold-rate story whose factual summary was judged unsupported but
     stayed beside a supported action; and a theft story whose
     retrieval returned only private-defence and evidence-law sections got
     the summary "constituting a criminal theft under Pakistani law" judged
     unsupported -- and shown.)
 12. (v3) VISIBLE PROVISION CONSISTENCY. A section the client READS must be
     the section the claim is bound to. The binder took a citation's identity
     from its passage (PPC 381-A) while the model's prose still said "Section
     381" -- and the claim judge called that action supported. Deterministic,
     claim by claim: every explicit section/article named in a visible action
     must be among the canonical provisions its claim's evidence is bound to
     (any bound provision, for a summary sentence or an action with no claim
     record). 381 != 381-A, 489 != 489-F, 489F == 489-F; a sub-section "7(2)"
     is compared as section 7 and its wording is never altered. A mismatched
     action is removed; a mismatched summary sentence is replaced by a fixed
     neutral sentence. The rejected text is kept only in `output_guard`.
     No number is ever rewritten.
"""
from __future__ import annotations

import re

GUARD_VERSION = "intake-output-guard-v3"
PROVISION_MISMATCH_SENTENCE = ("A section reference in the generated text did not match the law sections "
                               "found and was withheld; please confirm the applicable provision with a lawyer.")
VISIBLE_MISMATCH = "visible_provision_mismatch"
# An explicit provision named in prose: "Section 381", "s. 489-F", "section
# 489F", "Article 199", "dafa 302", "Section 7(2)". A letter counts only when
# attached or hyphenated, so "Section 302 PPC" is section 302.
_MENTION = re.compile(r"\b(?:section|sec\.?|s\.|article|art\.?|dafa)\s*(\d+)(?:\s*-\s*([A-Z]{1,2})|([A-Z]{1,2}))?"
                      r"(?![A-Za-z])", re.IGNORECASE)


def mentioned_provisions(text: str) -> list[str]:
    """Canonical provisions explicitly named in `text` (sub-sections dropped
    for COMPARISON only)."""
    from app.ai.corpus_index import canonical_section
    out = []
    for m in _MENTION.finditer(text or ""):
        letter = (m.group(2) or m.group(3) or "").upper()
        out.append(canonical_section(m.group(1) + (f"-{letter}" if letter else "")))
    return out


def _bound_provisions(cites: list[dict]) -> set[str]:
    from app.ai.corpus_index import canonical_section
    return {canonical_section(str(c.get("section") or "")) for c in cites if c.get("section")}


def _claim_provisions(claim: dict, cites: list[dict]) -> set[str] | None:
    """The bound provisions a claim's evidence ids resolve to; None when the
    claim names no evidence (then any bound provision is the reference)."""
    ids = claim.get("source_ids") or []
    if isinstance(ids, str):
        ids = re.findall(r"\d+", ids)
    ids = {str(i) for i in ids}
    if not ids:
        return None
    from app.ai.corpus_index import canonical_section
    return {canonical_section(str(c.get("section") or "")) for c in cites
            if str(c.get("evidence_id") or "") in ids and c.get("section")}


def _mismatch(text: str, allowed: set[str]) -> list[str]:
    return [p for p in mentioned_provisions(text) if p not in allowed]


SUMMARY_WITHHELD = ("The legal summary could not be verified against the law sections found, so no legal "
                    "conclusion is shown. Please have a qualified Pakistani lawyer review your matter.")
LAWYER_REVIEW_STEP = ("Ask a qualified Pakistani lawyer which legal provision applies before taking any "
                      "legal step; a suggested legal step was withheld because it could not be verified "
                      "against the law sections found.")
NO_LEGAL_CONTENT = "no_supported_legal_content"
_GROUNDED = ("supported", "partially_supported")


# ── deterministic formal-legal-action classifier ────────────────────────────
# A formal step = a procedural VERB acting on a legal INSTRUMENT of procedure
# (within a few words), or applying for a court remedy, or proceeding under a
# named provision. Ordinary steps (gather documents, consult a lawyer, call
# emergency services, report danger to the police for protection) are not.
_FILE_VERB = r"(?:file|filing|lodge|lodging|submit|register|institute|initiate|bring|move|present|prepare and file)"
_PROC_NOUN = (r"(?:application|petition|plaint|complaint|fir|f\.i\.r|first information report|suit|appeal|"
              r"revision|writ|case|prosecution|proceedings|reference|claim)")
_FORMAL_EN = [
    re.compile(rf"\b{_FILE_VERB}\b(?:\W+\w+){{0,6}}?\W+{_PROC_NOUN}\b", re.IGNORECASE),
    re.compile(r"\b(?:send|serve|issue)\b(?:\W+\w+){0,3}?\W+legal notice\b", re.IGNORECASE),
    re.compile(r"\bapply\b(?:\W+\w+){0,3}?\W+(?:for\W+)?(?:bail|probation|stay|injunction|khula|"
               r"maintenance|custody|guardianship|succession certificate|protection order|anticipatory)\b",
               re.IGNORECASE),
    re.compile(r"\b(?:invoke|proceed|act|prosecute|charge)\w*\b(?:\W+\w+){0,4}?\W+under\W+(?:section|"
               r"article|s\.)\s*\d+", re.IGNORECASE),
    re.compile(r"\b(?:register\w*|initiat\w*|start\w*)\b(?:\W+\w+){0,4}?\W+under\W+(?:section|s\.)\s*\d+",
               re.IGNORECASE),
    re.compile(r"\bregistered under (?:section|s\.)\s*\d+", re.IGNORECASE),
]
_FORMAL_UR = re.compile(
    r"(?:درخواست|دعویٰ|دعوی|مقدمہ|ایف آئی آر|اپیل|رٹ|نوٹس|شکایت)[^.۔؟]{0,25}(?:دائر|درج|جمع|بھیج)")
_FORMAL_ROMAN = re.compile(
    r"\b(?:darkhwast|darkhast|dawa|muqadma|muqadda?ma|case|fir|appeal|notice|shikayat)\b(?:\W+\w+){0,4}?"
    r"\W+(?:dair|dayar|darj|jama|file|bhej)\w*", re.IGNORECASE)


def is_formal_legal_action(text: str) -> bool:
    """True for a formal legal step, whatever label the model gave it."""
    t = text or ""
    return (any(p.search(t) for p in _FORMAL_EN) or bool(_FORMAL_UR.search(t))
            or bool(_FORMAL_ROMAN.search(t)))


def _claims_by_action(analysis: dict) -> dict[str, dict]:
    return {str(c.get("text") or "").strip(): c for c in analysis.get("claim_assessments") or []
            if c.get("kind") == "action"}


def _uncited_texts(analysis: dict) -> set[str]:
    idx = {str(i) for i in analysis.get("uncited_legal_actions") or []}
    return {str(c.get("text") or "").strip() for c in analysis.get("claim_assessments") or []
            if str(c.get("index")) in idx}


def _mentions(text: str, targets: list[dict]) -> bool:
    for t in targets:
        num = re.escape(str(t.get("section") or "").replace("-", ""))
        letter = ""
        m = re.match(r"(\d+)-?([A-Z]{1,2})$", str(t.get("section") or ""))
        if m:
            num, letter = m.group(1), m.group(2)
        pat = (rf"\b(?:section|sec\.?|s\.|dafa|article|art\.?)\s*{num}"
               + (rf"\s*-?\s*{letter}\b" if letter else r"(?!\s*-?\s*[A-Za-z]\b)\b"))
        if re.search(pat, text or "", re.IGNORECASE):
            return True
    return False


def _unsupported_issue(text: str) -> bool:
    from app.ai.nodes.intake_evidence_gate_node import scope_issues
    try:
        sc = scope_issues(text or "")
    except Exception:  # noqa: BLE001
        return False
    return bool(sc["unsupported"]) or bool(sc["missing_instruments"])


def enforce(analysis: dict, story: str | None = None) -> dict:
    """Apply the output contract in place; returns the same dict. `story` is
    the client's own account, used only if the legal summary is withheld."""
    gate = analysis.get("evidence_gate") or {}
    status = gate.get("status")
    grounded_gate = (not gate) or status in _GROUNDED
    omitted_targets = [t for t in gate.get("requested_provisions") or [] if t.get("omitted")]

    actions = list(analysis.get("recommended_actions") or [])
    kinds = list(analysis.get("recommended_action_kinds") or [])
    if len(kinds) != len(actions):
        kinds = [None] * len(actions)
    claims = _claims_by_action(analysis)
    uncited = _uncited_texts(analysis)

    kept, kept_kinds, removed = [], [], []
    for text, kind in zip(actions, kinds):
        t = str(text or "").strip()
        claim = claims.get(t) or {}
        formal = is_formal_legal_action(t)
        # The model's label can make an action legal, never exempt it.
        is_legal = formal or (kind or claim.get("action_kind") or "legal") == "legal"
        if is_legal:
            kind = "legal"
        reason = None
        if omitted_targets and _mentions(t, omitted_targets):
            reason = "names_an_omitted_provision"
        elif is_legal and not grounded_gate:
            reason = "legal_action_without_admissible_law"
        elif is_legal and claim.get("support") == "unsupported":
            reason = "judged_unsupported"
        elif is_legal and (t in uncited or not claim or claim.get("citation_status") != "matched"):
            reason = "not_bound_to_evidence"
        elif formal and (status == "partially_supported" or claim.get("support") == "partially_supported") \
                and claim.get("support") != "supported":
            reason = "formal_action_not_fully_supported"
        elif status == "partially_supported" and _unsupported_issue(t):
            reason = "unsupported_issue_leak"
        if reason:
            removed.append({"text": t, "kind": kind or claim.get("action_kind") or "legal", "reason": reason})
        else:
            kept.append(text)
            kept_kinds.append(kind)
    if any(r["kind"] == "legal" or r["reason"] == "names_an_omitted_provision" for r in removed) \
            and LAWYER_REVIEW_STEP not in kept:
        kept.append(LAWYER_REVIEW_STEP)
        kept_kinds.append("general")

    # Summary: an unsupported issue never reappears in a partial analysis.
    summary = str(analysis.get("summary") or "")
    removed_sentences = []
    if status == "partially_supported" and summary:
        from app.ai.nodes.intake_evidence_gate_node import _sentences
        keep_s = []
        for sent in _sentences(summary):
            (removed_sentences if _unsupported_issue(sent) else keep_s).append(sent)
        if removed_sentences:
            summary = " ".join(keep_s)
    if omitted_targets:
        # Remove sentences presenting the omitted provision, then state its
        # currency from the record -- provenance-backed, no model words.
        from app.ai.nodes.intake_evidence_gate_node import _sentences
        keep_s = [s for s in _sentences(summary) if not _mentions(s, omitted_targets)]
        removed_sentences += [s for s in _sentences(summary) if _mentions(s, omitted_targets)]
        notice = " ".join(
            f"{t['statute']} section {t['section']} is recorded as {t['omitted_by']}; it is not "
            "presented here as current law. Please verify the current legal position with a "
            "qualified lawyer." for t in omitted_targets if t.get("omitted_by"))
        summary = " ".join([notice, *keep_s]).strip()
        analysis["currency_notice"] = notice

    # Citations: only bound citations remain as law.
    cites = list(analysis.get("law_citations") or [])
    bound = [c for c in cites if c.get("status") == "bound"]
    withheld = [c for c in cites if c.get("status") != "bound"]
    if not grounded_gate:
        withheld, bound = withheld + bound, []

    # An unsupported legal summary with nothing fully supported behind it.
    summary_claim = next((c for c in analysis.get("claim_assessments") or [] if c.get("kind") == "summary"), {})
    supported_kept = [t for t, k in zip(kept, kept_kinds)
                      if k == "legal" and (claims.get(str(t).strip()) or {}).get("support") == "supported"]
    unsupported_summary = summary_claim.get("support") == "unsupported"
    # A partial analysis may not show any legal claim the judge rejected, the
    # summary included; elsewhere the summary goes only when nothing fully
    # supported stands behind it.
    summary_withheld = unsupported_summary and (not supported_kept or status == "partially_supported")
    if summary_withheld:
        removed_sentences.append(summary)
        own = " ".join(str(story or "").split())
        summary = SUMMARY_WITHHELD + (f" Your account: \"{own}\"" if own else "")
    if summary_withheld and not supported_kept:
        # Nothing supported remains: no law is shown at all.
        withheld, bound = withheld + bound, []
        kept = [t for t, k in zip(kept, kept_kinds) if k != "legal"]
        kept_kinds = [k for k in kept_kinds if k != "legal"]
        if LAWYER_REVIEW_STEP not in kept:
            kept.append(LAWYER_REVIEW_STEP)
            kept_kinds.append("general")

    # 12. Visible provision consistency, claim by claim, against what is
    # actually bound and shown.
    all_bound = _bound_provisions(bound)
    visible_mismatches = []
    final_kept, final_kinds = [], []
    for t, k in zip(kept, kept_kinds):
        if t == LAWYER_REVIEW_STEP:
            final_kept.append(t)
            final_kinds.append(k)
            continue
        claim = claims.get(str(t).strip()) or {}
        own = _claim_provisions(claim, bound) if claim else None
        bad = _mismatch(str(t), own if own is not None else all_bound)
        if bad:
            visible_mismatches.append({"where": "action", "text": str(t), "named": bad,
                                       "bound": sorted(own if own is not None else all_bound)})
            removed.append({"text": str(t), "kind": k or "legal", "reason": VISIBLE_MISMATCH})
        else:
            final_kept.append(t)
            final_kinds.append(k)
    kept, kept_kinds = final_kept, final_kinds
    if any(r["reason"] == VISIBLE_MISMATCH for r in removed) and LAWYER_REVIEW_STEP not in kept:
        kept.append(LAWYER_REVIEW_STEP)
        kept_kinds.append("general")
    if summary and not summary_withheld:
        from app.ai.nodes.intake_evidence_gate_node import _sentences
        out_s, replaced = [], False
        notice_text = str(analysis.get("currency_notice") or "")
        for sent in _sentences(summary):
            if notice_text and sent in notice_text:
                # The deterministic currency notice (built from the omission
                # record, not model text) names the omitted section by design.
                out_s.append(sent)
                continue
            bad = _mismatch(sent, all_bound)
            if bad:
                visible_mismatches.append({"where": "summary", "text": sent, "named": bad,
                                           "bound": sorted(all_bound)})
                if not replaced:
                    out_s.append(PROVISION_MISMATCH_SENTENCE)
                    replaced = True
            else:
                out_s.append(sent)
        if visible_mismatches and replaced:
            summary = " ".join(out_s)
    if visible_mismatches:
        analysis["grounded"] = False
        if grounded_gate:
            analysis["grounding_status"] = VISIBLE_MISMATCH

    analysis["recommended_actions"] = kept
    analysis["recommended_action_kinds"] = kept_kinds
    analysis["summary"] = summary
    analysis["law_citations"] = bound
    if withheld:
        from app.ai.intake_evidence import render_applicable_laws
        analysis["applicable_laws"] = render_applicable_laws(bound)
        analysis["withheld_citations"] = withheld

    supported_legal = [k for k in kept_kinds if k == "legal"]
    downgraded = False
    if grounded_gate and not bound and not supported_legal and gate:
        analysis["grounding_status"] = NO_LEGAL_CONTENT
        analysis["grounded"] = False
        analysis["risk_level"] = None
        downgraded = True

    analysis["output_guard"] = {
        "version": GUARD_VERSION,
        "removed_actions": removed,
        "removed_summary_sentences": removed_sentences,
        "withheld_citations": len(withheld),
        "downgraded": downgraded,
        "summary_withheld": summary_withheld,
        "visible_provision_mismatches": visible_mismatches,
    }
    return analysis
