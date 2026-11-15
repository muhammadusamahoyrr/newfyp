"""Bounded agentic issue decomposition -- an OFFLINE EXPERIMENT (Batch 8, 2026-10-13).

NOT wired into any route and NOT the intake default. It runs only when
`settings.agentic_decomposition_enabled` is true or the caller passes
`offline=True` (the evaluation runner). Ordinary intake keeps the single-query,
capability-first path.

THE ORCHESTRATOR, BOUNDED
  1. detect issues      one fast-LLM planner call; every issue must quote the
                        client's own words VERBATIM (anything else is discarded),
                        falling back to sentence decomposition when the planner
                        fails or returns nothing usable
  2. plan               at most MAX_ISSUES issues -> at most MAX_BRANCHES
                        retrievals; the model-call budget is checked before
                        every call
  3. retrieve per issue the production retrieval node, one issue per branch,
                        bounded concurrency, per-branch timeout
  4. check per issue    corpus capability (query-side) and the evidence gate
                        (jurisdiction, omitted provisions) on each issue alone
  5. merge              evidence keeps the issue it was retrieved for
  6/7. generate         NOT done here: the packet says which issues are
                        supported; a generator may draw only from those
                        packets, and every claim keeps its issue's citations
  No recursion, no replanning, no tool other than legal retrieval.

PER-ISSUE STATES
  supported | unsupported (capability or missing instrument) | ambiguous (too
  few words to retrieve on) | missing_facts (no admissible evidence) |
  conflicting_authority (admissible evidence from more than one instrument
  of different jurisdictions -- flagged, never resolved here).
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time

logger = logging.getLogger(__name__)

DECOMPOSITION_VERSION = "agentic-decomposition-v1-offline"
MAX_ISSUES = 3
MAX_BRANCHES = 3
MAX_MODEL_CALLS = 4          # 1 planner + up to 3 query rewrites
BRANCH_TIMEOUT_S = 30.0
TOTAL_TIMEOUT_S = 90.0
_MIN_ISSUE_WORDS = 4

_PLANNER_PROMPT = (
    "Split the client's message into its SEPARATE legal issues (at most 3). For each issue return "
    "the exact words from the message that describe it, copied verbatim. Do not add facts, law, or "
    "advice. Reply with JSON only: {\"issues\": [{\"title\": \"...\", \"quote\": \"...\"}]}. If "
    "there is only one issue, return one."
)


class Budget:
    def __init__(self, max_calls: int = MAX_MODEL_CALLS):
        self.max_calls, self.calls = max_calls, 0

    def take(self) -> bool:
        if self.calls >= self.max_calls:
            return False
        self.calls += 1
        return True


def _sentences(text: str) -> list[str]:
    from app.ai.nodes.intake_evidence_gate_node import _sentences as split
    return split(text)


def _validate_plan(raw: str, text: str) -> list[dict]:
    """Planner output -> issues whose quote is verbatim in the client's text."""
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        return []
    try:
        issues = json.loads(m.group(0)).get("issues") or []
    except (ValueError, AttributeError):
        return []
    norm = " ".join((text or "").split()).casefold()
    out = []
    for i in issues[:MAX_ISSUES]:
        quote = " ".join(str((i or {}).get("quote") or "").split())
        if quote and quote.casefold() in norm and quote not in [o["text"] for o in out]:
            out.append({"title": str((i or {}).get("title") or "")[:120], "text": quote, "source": "planner"})
    return out


async def detect_issues(text: str, budget: Budget, planner=None) -> list[dict]:
    issues: list[dict] = []
    if budget.take():
        try:
            if planner is None:
                from app.ai.llm import get_fast_llm
                from app.ai.provider_health import PURPOSE_UNKNOWN
                llm = get_fast_llm(purpose=PURPOSE_UNKNOWN)
                planner = lambda msgs: llm.invoke(msgs).content  # noqa: E731
            raw = await asyncio.wait_for(asyncio.to_thread(planner, [
                {"role": "system", "content": _PLANNER_PROMPT},
                {"role": "user", "content": text}]), BRANCH_TIMEOUT_S)
            issues = _validate_plan(raw, text)
        except Exception:  # noqa: BLE001 -- the fallback below is deterministic
            logger.warning("agentic: planner failed; sentence fallback", exc_info=True)
    if not issues:
        issues = [{"title": "", "text": s, "source": "sentence"} for s in _sentences(text)][:MAX_ISSUES]
    return issues[:MAX_ISSUES]


async def _retrieve_issue(issue: dict, case_type: str, province: str, budget: Budget, retrieve=None) -> dict:
    from app.ai.nodes import retrieval_node as rn
    state = {"query": issue["text"], "user_text": issue["text"], "case_type": case_type, "province": province,
             "retrieval_attempts": 0, "known_facts": [],
             "retrieval_policy": {"purpose": "intake", "min_chunks": 0, "include_ungraded": False,
                                  "case_law": False,
                                  # no budget left -> no rewrite (raw query), never an extra call
                                  "expansion_skip_all": not budget.take()}}
    run = retrieve or rn.retrieval_node
    return await asyncio.wait_for(run(state), BRANCH_TIMEOUT_S)


def _conflict(chunks: list[dict]) -> bool:
    provs = {(c.get("province") or "federal").lower() for c in chunks}
    insts = {c.get("statute") for c in chunks}
    return len(insts) > 1 and len(provs) > 1


async def decompose(text: str, case_type: str, province: str, *, offline: bool = False,
                    planner=None, retrieve=None) -> dict:
    """The per-issue packet. Raises unless enabled or explicitly offline."""
    from app.core.config import settings
    if not (offline or getattr(settings, "agentic_decomposition_enabled", False)):
        raise RuntimeError("agentic decomposition is an offline experiment and is disabled")
    from app.ai.nodes.intake_evidence_gate_node import decide, scope_issues
    t0 = time.perf_counter()
    budget = Budget()

    async def run() -> dict:
        issues = await detect_issues(text, budget, planner)
        packets, branches = [], 0
        for issue in issues:
            scope = scope_issues(issue["text"])
            if scope["missing_instruments"] or (scope["unsupported"] and scope["pure"]):
                packets.append({**issue, "state": "unsupported",
                                "reason": scope["missing_instruments"] or [u["kind"] for u in scope["unsupported"]],
                                "evidence": []})
                continue
            if len(issue["text"].split()) < _MIN_ISSUE_WORDS:
                packets.append({**issue, "state": "ambiguous", "reason": "too few words", "evidence": []})
                continue
            if branches >= MAX_BRANCHES:
                packets.append({**issue, "state": "ambiguous", "reason": "branch budget exhausted", "evidence": []})
                continue
            branches += 1
            try:
                out = await _retrieve_issue(issue, case_type, province, budget, retrieve)
            except Exception as exc:  # noqa: BLE001
                packets.append({**issue, "state": "missing_facts", "reason": f"retrieval failed: {type(exc).__name__}",
                                "evidence": [], "retrieval_error": True})
                continue
            kept, gate = decide(chunks=out.get("reranked_chunks") or out.get("retrieved_chunks") or [],
                                retrieval_error=bool(out.get("retrieval_error")), province=province,
                                user_text=issue["text"], relevance_score=None)
            if gate["status"] not in ("supported", "partially_supported"):
                packets.append({**issue, "state": "missing_facts" if gate["status"] == "no_relevant_evidence"
                                else "unsupported", "reason": gate["status"], "evidence": [], "gate": gate})
                continue
            evidence = [{**c, "issue": issue["text"]} for c in kept[:5]]
            packets.append({**issue, "state": "conflicting_authority" if _conflict(evidence) else "supported",
                            "evidence": evidence, "gate": gate})
        return {"issues": packets}

    try:
        result = await asyncio.wait_for(run(), TOTAL_TIMEOUT_S)
        result["timed_out"] = False
    except asyncio.TimeoutError:
        result = {"issues": [], "timed_out": True}
    result.update({"version": DECOMPOSITION_VERSION, "model_calls": budget.calls,
                   "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                   "limits": {"max_issues": MAX_ISSUES, "max_branches": MAX_BRANCHES,
                              "max_model_calls": MAX_MODEL_CALLS, "total_timeout_s": TOTAL_TIMEOUT_S}})
    return result
