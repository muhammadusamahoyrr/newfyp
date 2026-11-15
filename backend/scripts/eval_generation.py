"""eval_generation.py — offline evaluation of final intake analyses (Batch 6).

  python scripts/eval_generation.py generate --datasets dev_v1,coverage_v1 [--ids d001,d002] [--limit N] --out G.jsonl
  python scripts/eval_generation.py assess --generations G.jsonl [--out R.json]

TWO PHASES, KEPT APART
  generate  runs the REAL intake analysis (_run_intake_ai: retrieval, grader,
            evidence gate, analysis, citation binding, claim judge) on each
            query. It sees only what a client would supply -- the query, the
            case type and the province -- never the expected labels. It stores
            the raw answer, the passages it was built on, the bound citations,
            the gate record and the pipeline's own claim assessments.
            Provenance writes are disabled (no database rows are created).
  assess    reads ONLY the stored generations plus the dataset labels and
            runs deterministic checks. Nothing here calls a model.

WHAT IS ASSESSED (separately -- there is no combined score)
  A  input_fact_fidelity (LIMITED: numbers + basic negation; not truth checking)
  B  legal authority: every citation bound to a retrieved passage; instrument,
     provision and jurisdiction of that passage; uncited legal actions; cited
     instrument vs the (silver) expected instrument. Whether the passage SUPPORTS
     the proposition is reported only as the pipeline's own claim-judge verdict,
     an LLM signal, never a release gate.
  C  abstention: not-capable requests must carry no law and no legal action;
     answerable requests that were declined are counted as false abstentions.
  D  multilingual consistency within a semantic group: gate decision, cited
     instruments, cited provisions, abstention. The core legal CONCLUSION is
     not compared (no deterministic way) and is reported as not_measured.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from app.ai.evaluation import legal_rag as E  # noqa: E402
from app.ai.evaluation.artifact import EVALUATOR_VERSION  # noqa: E402

GROUNDED = ("supported", "partially_supported")

# THE LANGUAGE CONTRACT. The intake API takes output_language in {"en", "ur"}
# only (schemas/intake.py), and "ur" means the controlled Urdu-SCRIPT
# rendering (ai/intake_localization.py). Roman Urdu and code-switched text are
# written in Latin script; the product has no Roman-Urdu rendering, so they are
# generated in English -- recorded per item as effective_generation_language,
# never reported as "Urdu evaluated".
GENERATION_LANGUAGE = {"en": "en", "ur": "ur", "roman_ur": "en", "code_switched": "en"}

# Outcomes that count toward the unsafe total. Category names stay for
# diagnosis; none of them is excluded from the total.
UNSAFE_OUTCOMES = ("UNSAFE_ANSWER", "answered_unanswerable", "failed_partial")


def _load(datasets: str) -> list[E.EvalItem]:
    items = []
    for ds in datasets.split(","):
        items += E.load_jsonl(BACKEND_DIR / "evals" / "legal_rag" / "datasets" / f"{ds}.jsonl")
    return items


# ── generate ─────────────────────────────────────────────────────────────────

async def _generate(items: list[E.EvalItem], out: Path, pause: float = 0.0,
                    dataset_paths: tuple = ()) -> None:
    from app.ai import provider_health
    from app.ai.evaluation import artifact
    from app.ai.graph import supervisor
    from app.db.chroma import connect_chroma
    from app.services import intake_service as svc
    connect_chroma()
    real_graph = supervisor.intake_graph
    captured: dict = {}

    class Capture:
        async def ainvoke(self, state):
            result = await real_graph.ainvoke(state)
            captured["result"] = result
            return result

    async def no_provenance(*a, **k):
        return None
    supervisor.intake_graph = Capture()
    svc._record_intake_provenance = no_provenance

    # One code/config identity for the whole run; every record carries it.
    header = artifact.run_header(list(dataset_paths))
    with out.open("w", encoding="utf-8") as fh:
        for it in items:
            captured.clear()
            t0 = time.perf_counter()
            # ONLY client-side inputs reach the system.
            lang = GENERATION_LANGUAGE.get(it.language, "en")
            with provider_health.turn_scope(f"eval-{it.query_id}") as usage:
                analysis = await svc._run_intake_ai(it.query, it.case_type, it.province, f"eval-{it.query_id}",
                                                    "", language=lang, retrieval_query=it.query,
                                                    user_text=it.query)
                events = usage.all_events()
            ms = (time.perf_counter() - t0) * 1000
            res = captured.get("result") or {}
            rec = {
                "query_id": it.query_id, "query": it.query, "case_type": it.case_type, "province": it.province,
                "latency_ms": round(ms, 1),
                "query_language": it.language, "effective_generation_language": lang,
                "provenance": artifact.run_record(
                    header, events, language=lang,
                    pipeline_failed=analysis.get("grounding_status") == "pipeline_failed"),
                "localization_status": {k: (v or {}).get("status")
                                        for k, v in (analysis.get("localized") or {}).items()},
                "analysis": {k: analysis.get(k) for k in (
                    "summary", "recommended_actions", "risk_level", "law_citations", "applicable_laws",
                    "grounded", "grounding_status", "evidence_gate", "uncited_legal_actions",
                    "claim_assessments", "binding_mode", "recommended_action_kinds", "output_guard",
                    "withheld_citations", "currency_notice", "localization_state")},
                "evidence": [{k: e.get(k) for k in ("id", "statute", "section", "province", "chunk_id")}
                             | {"content": (e.get("content") or "")[:600]}
                             for e in res.get("generation_evidence") or []],
            }
            if pause:
                await asyncio.sleep(pause)
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            fh.flush()
            print(f"{it.query_id} {analysis.get('grounding_status')!s:24} "
                  f"cites={len(analysis.get('law_citations') or [])} {ms:7.0f}ms", flush=True)
    supervisor.intake_graph = real_graph


# ── assess ───────────────────────────────────────────────────────────────────

def _action_kinds(an: dict) -> list[str] | None:
    """Per-action kind. After the finalizer the actions are strings and the
    kinds live in `recommended_action_kinds`; None when neither is recorded."""
    actions = an.get("recommended_actions") or []
    if actions and all(isinstance(a, dict) for a in actions):
        return [(a or {}).get("kind", "legal") for a in actions]
    kinds = an.get("recommended_action_kinds")
    return list(kinds) if isinstance(kinds, list) and len(kinds) == len(actions) else None


def _action_text(a) -> str:
    return (a or {}).get("text", "") if isinstance(a, dict) else str(a or "")


# ── provision-level legal accuracy (2026-10-13 final hardening) ─────────────
# Instrument match is not enough: PPC 415 and PPC 489-F are one instrument and
# two different offences. Identity is (instrument, canonical provision):
# "489-F" == "489F", "489" != "489-F", a sub-section tail "7(2)" keeps its
# section identity "7" (the corpus indexes sections, not sub-sections), and a
# schedule row (empty section) is never a provision.
LEGAL_OUTCOMES = ("legally_supported_answer", "incomplete_issue_coverage", "wrong_provision_answer",
                  "unsupported_extra_provision", "safe_abstention", "false_abstention",
                  "structurally_unsafe_answer")


def _prov(statute: str, section) -> tuple[str, str] | None:
    from app.ai.corpus_index import canonical_section
    sec = re.sub(r"\s*\(.*$", "", str(section or "").strip())
    sec = re.sub(r"^(?:section|sec\.?|s\.|article|art\.?)\s*", "", sec, flags=re.IGNORECASE)
    if not sec:
        return None
    return ((statute or "").strip(), canonical_section(sec))


def _hits(target: E.Target, provs: set) -> bool:
    if target.section is None:                       # instrument-level target
        return any(st == target.statute for st, _ in provs)
    return _prov(target.statute, target.section) in provs


def provision_eval(item: E.EvalItem, an: dict, evidence: list[dict], structurally_unsafe: bool,
                   declined: bool) -> dict:
    """Separate legal-accuracy measures for one answer. Uses the TRUE target
    labels (never index_section): a right passage under a wrong label is not a
    right provision unless the runtime binder repaired its identity."""
    visible = {p for p in (_prov(c.get("statute"), c.get("section"))
                           for c in an.get("law_citations") or []) if p}
    expected, alts = list(item.relevant), list(item.acceptable_alternatives)
    exp_hit = [t for t in expected if _hits(t, visible)]
    alt_hit = [t for t in alts if _hits(t, visible)]
    good = {p for p in visible if any(_hits(t, {p}) for t in expected + alts)}
    wrong = sorted(f"{st} s.{sec}" for st, sec in visible - good)
    issues = [i for i in item.issues if i.answerable]
    covered = [i.issue_id for i in issues if any(_hits(t, visible) for t in i.relevant)]
    full_cover = (len(covered) == len(issues)) if issues else (bool(expected) and len(exp_hit) == len(expected))

    # What the visible LEGAL actions rest on (claim -> evidence ids -> passage).
    from app.ai.intake_evidence import canonical_section as from_header
    ev_prov = {str(e.get("id")): _prov(e.get("statute"), from_header(
        {"section": e.get("section"), "content": e.get("content")})) for e in evidence if e.get("id") is not None}
    kinds = an.get("recommended_action_kinds") or []
    shown_legal = {str(a).strip() for a, k in zip(an.get("recommended_actions") or [], kinds) if k == "legal"}
    reliance = {"expected": 0, "alternative": 0, "unexpected": 0}
    for c in an.get("claim_assessments") or []:
        if c.get("kind") != "action" or str(c.get("text") or "").strip() not in shown_legal:
            continue
        ids = c.get("source_ids") or []
        if isinstance(ids, str):
            ids = re.findall(r"\d+", ids)
        for i in ids:
            p = ev_prov.get(str(i))
            if p is None:
                continue
            if any(_hits(t, {p}) for t in expected):
                reliance["expected"] += 1
            elif any(_hits(t, {p}) for t in alts):
                reliance["alternative"] += 1
            else:
                reliance["unexpected"] += 1

    answerable = item.answerable_by_corpus and item.expected_capability() in ("corpus_capable",
                                                                             "mixed_supported_unsupported")
    if structurally_unsafe:
        outcome = "structurally_unsafe_answer"
    elif not answerable:
        outcome = "safe_abstention" if not visible else "wrong_provision_answer"
    elif declined or not visible:
        outcome = "false_abstention"
    elif not exp_hit and not alt_hit:
        outcome = "wrong_provision_answer"
    elif not full_cover:
        outcome = "incomplete_issue_coverage"
    elif wrong:
        outcome = "unsupported_extra_provision"
    else:
        outcome = "legally_supported_answer"
    return {
        "outcome": outcome,
        "visible_provisions": sorted(f"{st} s.{sec}" for st, sec in visible),
        "expected_instrument_recall": (sum(1 for t in expected if any(st == t.statute for st, _ in visible))
                                       / len(expected)) if expected else None,
        "expected_provision_recall": (len(exp_hit) / len(expected)) if expected else None,
        "alternative_provision_recall": (len(alt_hit) / len(alts)) if alts else None,
        "provision_precision": (len(good) / len(visible)) if visible else None,
        "exact_provision_match": bool(expected) and len(exp_hit) == len(expected) and not wrong,
        "wrong_provisions": wrong,
        "missing_expected": [f"{t.statute} s.{t.section}" for t in expected if t not in exp_hit],
        "issue_coverage": {"covered": covered, "total": len(issues)} if issues else None,
        "full_issue_coverage": full_cover,
        "legal_action_reliance": reliance,
    }


def assess_one(item: E.EvalItem, gen: dict) -> dict:
    from app.ai.fact_fidelity import check
    from app.ai.intake_understanding import build_understanding
    from app.ai.corpus_index import canonical_section
    an = gen["analysis"]
    gate = an.get("evidence_gate") or {}
    status = gate.get("status") or an.get("grounding_status")
    cites = an.get("law_citations") or []
    actions = an.get("recommended_actions") or []
    evidence = gen.get("evidence") or []
    ev_keys = {(e.get("statute"), canonical_section(str(e.get("section") or ""))) for e in evidence}
    ev_ids = {e.get("chunk_id") for e in evidence if e.get("chunk_id")}
    ok_prov = {"federal", (item.province or "").lower()}

    # A. input fact fidelity (limited)
    fid = check(summary=an.get("summary") or "", actions=[_action_text(a) for a in actions],
                understanding=build_understanding(story=item.query),
                extra_sources=[e["content"] for e in evidence]
                + [" ".join(f"{c.get('statute', '')} {c.get('section', '')}" for c in cites),
                   str(an.get("currency_notice") or "")])

    # B. legal authority
    bound = [c for c in cites if c.get("status") == "bound"]
    unbound = [c for c in cites if c.get("status") != "bound"]
    # Identity by the passage itself (chunk id). Section labels cannot be
    # compared directly: the binder restores "489-F" from the passage header
    # while the base index stores "489".
    off_evidence = [c for c in cites
                    if not (c.get("chunk_id") and c["chunk_id"] in ev_ids)
                    and (c.get("statute"), canonical_section(str(c.get("section") or ""))) not in ev_keys]
    bad_jur = [c for c in cites if c.get("province") and c["province"].lower() not in ok_prov]
    kinds = _action_kinds(an)
    legal_actions = [a for a, k in zip(actions, kinds or []) if k == "legal"]
    uncited = an.get("uncited_legal_actions") or []
    expected_statutes = {t.statute for t in item.relevant + item.acceptable_alternatives}
    instrument_match = (None if not (cites and expected_statutes)
                        else sum(1 for c in cites if c.get("statute") in expected_statutes) / len(cites))
    claims = an.get("claim_assessments") or []
    judged = [c for c in claims if c.get("support") in ("supported", "unsupported", "partially_supported")]

    removed_texts = {str(r.get("text") or "").strip()
                     for r in (an.get("output_guard") or {}).get("removed_actions") or []}
    # Uncited legal actions the client still SEES (the guard may have removed some).
    uncited_shown = [c for c in claims if str(c.get("index")) in {str(i) for i in uncited}
                     and str(c.get("text") or "").strip() not in removed_texts]
    # Legal actions the pipeline itself judged unsupported, still shown.
    shown = {str(a).strip() for a in actions}
    unsupported_shown = [c for c in claims if c.get("kind") == "action"
                         and (c.get("action_kind") or "legal") == "legal"
                         and c.get("support") == "unsupported" and str(c.get("text") or "").strip() in shown]
    # A provision the gate recorded as omitted, presented in an action or in
    # the summary (the deterministic currency notice excluded).
    from app.ai.intake_output_guard import _mentions
    omitted = [t for t in gate.get("requested_provisions") or [] if t.get("omitted")]
    summary_wo_notice = (an.get("summary") or "").replace(an.get("currency_notice") or "", "")
    omitted_presented = bool(omitted) and (any(_mentions(str(a), omitted) for a in actions)
                                           or _mentions(summary_wo_notice, omitted))
    # Unsupported-issue leakage in a partial answer.
    from app.ai.intake_output_guard import _unsupported_issue
    from app.ai.nodes.intake_evidence_gate_node import _sentences
    leaked = [x for x in [*_sentences(an.get("summary") or ""), *map(str, actions)]
              if status == "partially_supported" and _unsupported_issue(x)]

    # A section the client READS that is not the section its claim is bound to
    # (deterministic; the claim judge cannot override it).
    from app.ai.intake_output_guard import _bound_provisions, _claim_provisions, mentioned_provisions
    bound_all = _bound_provisions([c for c in cites if c.get("status") == "bound"])
    by_text = {str(c.get("text") or "").strip(): c for c in claims if c.get("kind") == "action"}
    visible_mismatch = []
    for a in actions:
        cl = by_text.get(str(a).strip())
        own = _claim_provisions(cl, cites) if cl else None
        ref = own if own is not None else bound_all
        visible_mismatch += [p for p in mentioned_provisions(str(a)) if p not in ref]
    notice = an.get("currency_notice") or ""
    for sent in _sentences(an.get("summary") or ""):
        if notice and sent in notice:
            continue
        visible_mismatch += [p for p in mentioned_provisions(sent) if p not in bound_all]

    # C. abstention
    capability = item.expected_capability()
    declined = status not in GROUNDED
    carries_law = bool(cites) or bool(legal_actions) or bool(uncited_shown)
    if capability in ("instrument_not_in_corpus", "live_rate", "court_statistic", "personal_record"):
        # Must not become a legal answer.
        abstention = "correct_abstention" if declined and not carries_law else "UNSAFE_ANSWER"
    elif capability == "mixed_supported_unsupported":
        # May answer the supported issue only. Every reason it fails is kept.
        partial_failures = []
        if status != "partially_supported":
            partial_failures.append(f"gate status {status}")
        if not (gate.get("issue_scope") or {}).get("retrieval_bound"):
            partial_failures.append("retrieval not bound to the supported issue")
        if off_evidence:
            partial_failures.append("citation outside retrieved evidence")
        if unbound:
            partial_failures.append("unbound or mismatched citation")
        if uncited_shown:
            partial_failures.append("uncited legal action")
        if unsupported_shown:
            partial_failures.append("legal action judged unsupported is shown")
        # A claim judged unsupported that the client still SEES. Claims the
        # output guard removed are reported separately (not hidden), because
        # what reaches the client is what can be unsafe.
        if any(c.get("support") == "unsupported" and str(c.get("text") or "").strip() not in removed_texts
               for c in claims):
            partial_failures.append("a legal claim was judged unsupported")
        if leaked:
            partial_failures.append("unsupported issue leaks into the answer")
        if not partial_failures:
            abstention = "correct_partial"
        elif declined and not carries_law:
            abstention = "declined_mixed"
        else:
            abstention = "failed_partial"
    elif capability == "outcome_prediction":
        # Intake analyses the matter; whether it PREDICTS an outcome is a
        # conclusion check this runner cannot make deterministically.
        abstention = "outcome_question_not_measured" if not off_evidence else "UNSAFE_ANSWER"
    elif not item.answerable_by_corpus:
        # e.g. an omitted provision or no corpus evidence: any law carried is
        # law about something else, reported for review.
        abstention = "correct_abstention" if not carries_law else "answered_unanswerable"
    else:
        abstention = "false_abstention" if declined else "answered"

    unsafe_reasons = []
    if abstention in UNSAFE_OUTCOMES:
        unsafe_reasons.append(abstention)
    if unsupported_shown:
        unsafe_reasons.append("unsupported_legal_action_shown")
    if omitted_presented:
        unsafe_reasons.append("omitted_provision_presented")
    if leaked:
        unsafe_reasons.append("unsupported_issue_leak")
    if visible_mismatch:
        unsafe_reasons.append("visible_provision_mismatch")

    return {
        "query_id": item.query_id, "language": item.language, "group": item.semantic_group_id,
        "question_type": item.question_type, "expected_capability": capability, "gate_status": status,
        "latency_ms": gen.get("latency_ms"),
        "A_fidelity": {"status": fid.get("status"), "issues": fid.get("issues"), "version": fid.get("version")},
        "B_authority": {
            "citations": len(cites), "bound": len(bound), "unbound": len(unbound),
            "not_in_retrieved_evidence": len(off_evidence), "wrong_jurisdiction": len(bad_jur),
            "legal_actions": len(legal_actions) if kinds is not None else "not_recorded",
            "uncited_legal_actions": len(uncited),
            "instrument_match_vs_silver": instrument_match,
            "pipeline_judge_supported_rate": (sum(1 for c in judged if c["support"] == "supported") / len(judged)
                                              if judged else None),
        },
        "C_abstention": abstention,
        "partial_failures": partial_failures if capability == "mixed_supported_unsupported" else None,
        "unsafe_reasons": unsafe_reasons,
        "visible_provision_mismatch": sorted(set(visible_mismatch)),
        "query_language": gen.get("query_language", item.language),
        "effective_generation_language": gen.get("effective_generation_language", "en"),
        "localization_status": gen.get("localization_status") or {},
        "withheld_citations": len(an.get("withheld_citations") or []),
        "guard_removed_actions": len((an.get("output_guard") or {}).get("removed_actions") or []),
        "unsupported_claims_removed_by_guard": sum(1 for c in claims if c.get("support") == "unsupported"
                                                   and str(c.get("text") or "").strip() in removed_texts),
        "L_provisions": provision_eval(item, an, evidence, bool(unsafe_reasons),
                                       declined or an.get("grounding_status") == "no_supported_legal_content"),
        "D_signature": {"declined": declined,
                        "instruments": sorted({c.get("statute") for c in cites if c.get("statute")}),
                        "provisions": sorted({f"{c.get('statute')} {c.get('section')}" for c in cites})},
    }


def assess(items: list[E.EvalItem], gens: list[dict]) -> dict:
    by_id = {i.query_id: i for i in items}
    rows = [assess_one(by_id[g["query_id"]], g) for g in gens if g["query_id"] in by_id]

    groups = defaultdict(list)
    for r in rows:
        groups[r["group"]].append(r)
    consistency = {}
    for gid, rs in groups.items():
        if len({r["language"] for r in rs}) < 2:
            continue
        sig = [r["D_signature"] for r in rs]
        consistency[gid] = {
            "languages": sorted(r["language"] for r in rs),
            "same_abstention": len({s["declined"] for s in sig}) == 1,
            "same_instruments": len({tuple(s["instruments"]) for s in sig}) == 1,
            "same_provisions": len({tuple(s["provisions"]) for s in sig}) == 1,
            "core_conclusion": "not_measured",
        }

    def rate(pred, pool):
        pool = list(pool)
        return (sum(1 for r in pool if pred(r)) / len(pool)) if pool else None

    abst = defaultdict(int)
    for r in rows:
        abst[r["C_abstention"]] += 1
    unsafe = [r for r in rows if r["unsafe_reasons"]]

    def by_language(lang_rows):
        return {"n": len(lang_rows),
                "unsafe": sum(1 for r in lang_rows if r["unsafe_reasons"]),
                "false_abstention": sum(1 for r in lang_rows if r["C_abstention"] == "false_abstention"),
                "answered": sum(1 for r in lang_rows if r["C_abstention"] == "answered"),
                "effective_generation_language": sorted({r["effective_generation_language"] for r in lang_rows}),
                "urdu_rendering_ran": sum(1 for r in lang_rows if r["localization_status"]),
                "urdu_rendering_ok": sum(1 for r in lang_rows
                                         if any(v == "ok" for v in r["localization_status"].values()))}
    langs = defaultdict(list)
    for r in rows:
        langs[r["query_language"]].append(r)
    cited = [r for r in rows if r["B_authority"]["citations"]]
    return {
        "schema": "generation-eval-v1", "evaluator_version": EVALUATOR_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "labels": E.label_summary([by_id[r["query_id"]] for r in rows]),
        "n": len(rows),
        "A_input_fact_fidelity_limited": {
            "issues_rate": rate(lambda r: r["A_fidelity"]["status"] == "issues", rows),
            "unchecked_rate": rate(lambda r: r["A_fidelity"]["status"] == "unchecked", rows)},
        "B_legal_authority": {
            "answers_with_citations": len(cited),
            "citation_not_in_retrieved_evidence_rate": rate(
                lambda r: r["B_authority"]["not_in_retrieved_evidence"] > 0, cited),
            "unbound_citation_rate": rate(lambda r: r["B_authority"]["unbound"] > 0, cited),
            "wrong_jurisdiction_citation_rate": rate(lambda r: r["B_authority"]["wrong_jurisdiction"] > 0, cited),
            "answers_with_uncited_legal_action": sum(1 for r in rows if r["B_authority"]["uncited_legal_actions"]),
            "instrument_match_vs_silver_mean": E.mean(r["B_authority"]["instrument_match_vs_silver"] for r in rows
                                                      if r["B_authority"]["instrument_match_vs_silver"] is not None),
            "pipeline_judge_supported_mean (LLM signal, not a gate)": E.mean(
                r["B_authority"]["pipeline_judge_supported_rate"] for r in rows
                if r["B_authority"]["pipeline_judge_supported_rate"] is not None)},
        "C_abstention": dict(abst),
        # NEVER report zero unsafe while any unsafe category is present.
        "unsafe_answer_total": len(unsafe),
        # LEGAL ACCURACY, reported apart from structural safety (silver labels).
        "L_legal_accuracy": {
            "outcomes": {o: sum(1 for r in rows if r["L_provisions"]["outcome"] == o) for o in LEGAL_OUTCOMES},
            "provision_recall_mean": E.mean(r["L_provisions"]["expected_provision_recall"] for r in rows
                                            if r["L_provisions"]["expected_provision_recall"] is not None
                                            and r["L_provisions"]["outcome"] != "safe_abstention"),
            "provision_precision_mean": E.mean(r["L_provisions"]["provision_precision"] for r in rows
                                               if r["L_provisions"]["provision_precision"] is not None),
            "full_issue_coverage_rate": E.mean(1.0 if r["L_provisions"]["full_issue_coverage"] else 0.0
                                               for r in rows if by_id[r["query_id"]].answerable_by_corpus),
            "exact_provision_match_rate": E.mean(1.0 if r["L_provisions"]["exact_provision_match"] else 0.0
                                                 for r in rows if by_id[r["query_id"]].answerable_by_corpus),
            "wrong_provision_answer_total": sum(1 for r in rows
                                                if r["L_provisions"]["outcome"] == "wrong_provision_answer"),
            "incomplete_issue_coverage_total": sum(1 for r in rows
                                                   if r["L_provisions"]["outcome"] == "incomplete_issue_coverage"),
            "unsupported_extra_provision_total": sum(1 for r in rows if r["L_provisions"]["wrong_provisions"]
                                                     and r["L_provisions"]["outcome"] != "wrong_provision_answer"),
            "labels": "silver",
        },
        "unsafe_answer_rate": (len(unsafe) / len(rows)) if rows else None,
        "unsafe_detail": {r["query_id"]: r["unsafe_reasons"] for r in unsafe},
        "answered_unanswerable_total": abst.get("answered_unanswerable", 0),
        "failed_partials": {r["query_id"]: r["partial_failures"] for r in rows
                            if r["C_abstention"] == "failed_partial"},
        "unsupported_legal_actions_shown": sum(1 for r in rows
                                               if "unsupported_legal_action_shown" in r["unsafe_reasons"]),
        "withheld_citations_total": sum(r["withheld_citations"] for r in rows),
        "unsupported_claims_removed_by_guard_total": sum(r["unsupported_claims_removed_by_guard"] for r in rows),
        "guard_removed_actions_total": sum(r["guard_removed_actions"] for r in rows),
        "by_language": {k: by_language(v) for k, v in sorted(langs.items())},
        "D_multilingual_consistency": {
            "groups": len(consistency),
            "same_abstention_rate": rate(lambda g: g["same_abstention"], consistency.values()),
            "same_instruments_rate": rate(lambda g: g["same_instruments"], consistency.values()),
            "same_provisions_rate": rate(lambda g: g["same_provisions"], consistency.values()),
            "core_conclusion": "not_measured", "detail": consistency},
        "latency_ms": {"p50": E.percentile([r["latency_ms"] for r in rows], .5),
                       "p95": E.percentile([r["latency_ms"] for r in rows], .95)},
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--datasets", default="dev_v1,coverage_v1")
    g.add_argument("--ids", default="")
    g.add_argument("--limit", type=int, default=0)
    g.add_argument("--out", required=True)
    g.add_argument("--pause", type=float, default=0.0,
                   help="seconds between items (provider per-minute token limits)")
    a = sub.add_parser("assess")
    a.add_argument("--datasets", default="dev_v1,citation_probe_v1,coverage_v1")
    a.add_argument("--generations", required=True)
    a.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.cmd == "generate":
        items = _load(args.datasets)
        if args.ids:
            want = set(args.ids.split(","))
            items = [i for i in items if i.query_id in want]
        if args.limit:
            items = items[: args.limit]
        asyncio.run(_generate(items, Path(args.out), args.pause,
                              tuple(f"evals/legal_rag/datasets/{d}.jsonl" for d in args.datasets.split(","))))
        return 0
    items = _load(args.datasets)
    gens = [json.loads(l) for l in Path(args.generations).read_text(encoding="utf-8").splitlines() if l.strip()]
    rep = assess(items, gens)
    out = Path(args.out or BACKEND_DIR / "evals" / "legal_rag" / "results" /
               f"generation_eval_{datetime.now().strftime('%Y-%m-%d_%H%M')}.json")
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in rep.items() if k not in ("rows", "D_multilingual_consistency")},
                     indent=1, default=str))
    print("consistency:", json.dumps({k: v for k, v in rep["D_multilingual_consistency"].items() if k != "detail"}))
    print(f"report: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
