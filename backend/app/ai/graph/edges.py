"""
edges.py — LangGraph conditional edge routing functions.

Fixes vs previous version
--------------------------
  FIX 1: route_after_triage — hybrid + confidence > 0 now correctly routes to
          fact_gap_node (intentional overlap) instead of clarification_node.
          Only hybrid + confidence == 0.0 (zero signals / gibberish) goes to
          clarification_node.
  FIX 2: Province check now considers classifier-inferred province stored in
          state["province"] — previously only checked raw state value which
          hadn't been updated yet when edges.py ran.
  FIX 3: route_after_triage off_topic check moved to top — always checked first
          before any confidence/province logic runs.
"""

import re

from app.ai.graph.state import AgentState
from app.ai.response_policy import presentation_base_query

# ── Thresholds ────────────────────────────────────────────────────────────────
_RELEVANCE_THRESHOLD           = 0.40  # below → retry retrieval if budget allows
_CONVERGENCE_MIN_DELTA         = 0.05  # improvement < this → stop retrying
_MAX_RETRIEVAL_ATTEMPTS        = 3
_MAX_GENERATION_ATTEMPTS       = 2
_MAX_INTAKE_RETRIEVAL_ATTEMPTS = 2     # intake uses tighter budget than chat
_CLASSIFIER_CONFIDENCE_THRESHOLD = 0.85


# ── Routing functions ─────────────────────────────────────────────────────────

def route_after_gatekeeper(state: AgentState) -> str:
    """
    Entry-node router. The gatekeeper blocks prompt-injection / jailbreak attempts
    by setting convergence_status="off_topic" + a canned refusal answer (mirroring
    the off-topic exit). A clean query proceeds to the normal classifier pass.
    """
    if state.get("convergence_status") == "off_topic":
        return "finalizer_node"
    return "classifier_node"


def route_after_classifier(state: AgentState) -> str:
    """
    Always route to triage_node first.
    Ensures gibberish and off-topic queries are filtered BEFORE
    we interrupt the user for clarification.
    """
    return "triage_node"


_GENERAL_QUESTION = re.compile(
    r"^\s*(?:please\s+)?(?:can\s+you\s+|could\s+you\s+)?"
    r"(?:what\s+(?:is|are|does|do)\b|what'?s\b|which\b|list\b|name\b|explain\b|define\b|describe\b|"
    r"tell\s+me\b|give\s+me\b|how\s+many\b|overview\b|summari[sz]e\b|difference\s+between\b)",
    re.IGNORECASE)
# "Briefly, what is khula?" asks the same general question (2026-10-21).
_LENGTH_PREFIX = re.compile(
    r"^\s*(?:briefly|in\s+short|shortly|quickly|simply|in\s+simple\s+(?:words|terms)|in\s+detail)"
    r"\s*[,:\-]?\s*", re.IGNORECASE)
# Roman Urdu and Urdu put the question word last ("chori ki saza kya hai?",
# "خلع کیا ہے؟"), so these are searched anywhere, not anchored (2026-10-21).
_GENERAL_QUESTION_UR = re.compile(
    r"\b(?:kya|kia)\s+(?:hai|hain|he|hota|hoti|hote|matlab)\b|\bkis(?:e|ay|ko)\s+kehte\b|\bka\s+matlab\b|"
    r"کیا\s*ہے|کیا\s*ہیں|کیا\s*ہوتا|کیا\s*ہوتی|کیا\s*ہوتے|کسے\s*کہتے|سے\s*کیا\s*مراد|کا\s*مطلب",
    re.IGNORECASE)
# The asker's own matter ("my landlord...", "I was arrested", "meri biwi...",
# "میرے شوہر...") is not a general question.
_OWN_MATTER = re.compile(
    r"\b(?:my|mine|our|i\s+(?:am|was|have|had|got)|we\s+(?:are|were|have|had))\b|"
    r"\b(?:mera|meri|mere|mujhe|mujh|maine|main\s+ne|hamara|hamari|hamare|humne|hum\s+ne)\b|"
    r"\b(?:sakta|sakti|chahta|chahti)\s+(?:hun|hoon|hu)\b|"
    r"میرا|میری|میرے|مجھے|مجھ\s|ہمارا|ہماری|ہمارے|میں\s*نے|ہم\s*نے", re.IGNORECASE)


def is_general_question(query: str | None) -> bool:
    """An educational question about the law, not one about the asker's matter."""
    q = (query or "").strip()
    if not q or len(q) > 300 or _OWN_MATTER.search(q):
        return False
    return bool(_GENERAL_QUESTION.search(_LENGTH_PREFIX.sub("", q)) or _GENERAL_QUESTION_UR.search(q))


def route_after_triage(state: AgentState) -> str:
    # A question ABOUT the assistant ("can you guide me?", "kya aap meri madad
    # kar sakte hain?") has no facts to search: the finalizer answers it in the
    # asker's language (ai/client_help.py, 2026-10-20).
    from app.ai.client_help import is_capability_question
    if is_capability_question(state.get("query")):
        return "finalizer_node"

    # FIX 3: off_topic check always runs first — never falls through to
    # province/confidence logic on dead-end queries.
    if state.get("convergence_status") == "off_topic":
        return "finalizer_node"

    # A client "make it short" / "explain in detail" turn re-answers a question
    # the user already asked: never ask them a new question about it. With a
    # case type it goes on to the normal checked path; without one it ends with
    # the honest message triage set, rather than searching the civil default.
    # The confidence logic below must not decide this -- the keyword classifier
    # scores many valid questions at 0.0 ("What is Section 506 PPC?").
    # presentation_base_query is None for lawyer research, so research routing
    # is unchanged.
    if presentation_base_query(state):
        if state.get("case_type") in ("civil", "criminal", "family", "constitutional"):
            return "fact_gap_node"
        return "finalizer_node"

    # A LAWYER's general / educational question ("what are the fundamental
    # rights?", "explain bail before arrest") is not a matter with a province
    # or facts to pin down: asking for them sent a basic question round two
    # clarifications (2026-10-20). Research proceeds; if the library holds too
    # little, the lawyer gets labelled general guidance (ai/general_guidance.py).
    # The same holds for a CLIENT asking what the law is ("What is khula and
    # how can a wife get it?", 2026-10-20): it is answered, not questioned.
    if state.get("surface") in ("research", "client") and is_general_question(state.get("query")):
        return "fact_gap_node"

    routing_mode = state.get("routing_mode", "single")

    # FIX 2: Province is checked from state directly — classifier_node already
    # wrote the inferred province into state["province"] before this runs.
    province  = state.get("province",  "unknown")
    case_type = state.get("case_type", "unknown")

    # Confidence: prefer classifier_confidence (keyword-based, fast),
    # fall back to case_type_confidence (LLM-based from triage).
    confidence = state.get("classifier_confidence") or state.get("case_type_confidence", 0.0)

    # FIX 1: Hybrid routing has two sub-cases:
    #   a) confidence == 0.0 → zero keyword signals → genuinely unknown → clarify
    #   b) confidence >  0.0 → intentional overlap (e.g. criminal+civil) → proceed
    if routing_mode == "hybrid":
        if confidence == 0.0:
            # Zero signals fired — needs clarification to determine category
            return "clarification_node"
        else:
            # Overlap detected — hybrid retrieval will cover both collections
            # No clarification needed; fact_gap handles any missing details
            return "fact_gap_node"

    # Province unknown — ask before retrieval so filter doesn't silently fail
    if province == "unknown":
        return "clarification_node"

    # Case type still unresolved after both classifier and triage
    if case_type == "unknown":
        return "clarification_node"

    return "fact_gap_node"


def route_after_fact_gap(state: AgentState) -> str:
    """
    fact_gap_node uses LangGraph v1.0 interrupt() internally.
    The graph never reaches this router with needs_clarification=True —
    interrupt() suspends execution INSIDE the node and resumes in-place.
    This router always proceeds to retrieval.
    """
    return "retrieval_node"


def route_after_cache(state: AgentState) -> str:
    """Cache hit → straight to finalizer (skip retrieval + generation).
    Miss → tool_node, which decides whether a deterministic engine (bail, court
    fee, inheritance, case law) can compute part of the answer before retrieval
    runs. tool_node is a no-op for the majority of queries that need no tool."""
    return "finalizer_node" if state.get("cache_hit") else "tool_node"


def _has_engine_answer(state: AgentState) -> bool:
    """Did a deterministic engine already answer this question successfully?"""
    for call in state.get("tool_results", []) or []:
        result = call.get("result")
        if isinstance(result, dict):
            if not result.get("error"):
                return True
        elif isinstance(result, list):
            if any(isinstance(r, dict) and not r.get("error") for r in result):
                return True
    return False


def _retry_is_worthwhile(state: AgentState) -> bool:
    """
    Is another retrieval pass justified? This is a graph-level *budget* question,
    deliberately kept out of the Decision Engine: the engine judges evidence
    quality, the graph decides whether it can afford to look again.
    """
    score    = state.get("relevance_score", 0.0)
    prev     = state.get("prev_relevance_score", 0.0)
    attempts = state.get("retrieval_attempts", 1)

    # No new facts added since last retrieval → re-running won't help
    if state.get("fact_delta", 1) == 0 and attempts > 1:
        return False

    still_improving = (score - prev) > _CONVERGENCE_MIN_DELTA or attempts == 1
    budget_left     = attempts < _MAX_RETRIEVAL_ATTEMPTS
    return budget_left and still_improving


def route_after_decision(state: AgentState) -> str:
    """
    Reads the Decision Engine's verdict — it does NOT recompute confidence.

    arbitration_output is one of:
      "answer"  → generate
      "defer"   → retrieve again if the budget allows, else generate with what we have
      "refuse"  → skip generation entirely; finalizer emits the refusal message

    The engine's own clarification-depth cap means "defer" cannot recur forever:
    after MAX_CLARIFICATION_DEPTH defers it switches to binary answer/refuse.
    """
    # A deterministic engine (bail / court fee / inheritance) already produced the
    # answer. Retrieval here only supplies *supplementary* statute context, so a
    # low relevance score is not worth a retry — and refusing a correct computed
    # figure because the surrounding statute context scored poorly would be
    # strictly worse than answering. This guard runs before the verdict is read.
    if _has_engine_answer(state):
        return "generation_node"

    action = state.get("arbitration_output", "answer")

    if action == "refuse":
        return "finalizer_node"

    if action == "defer":
        return "retrieval_node" if _retry_is_worthwhile(state) else "generation_node"

    return "generation_node"


def route_after_grader_intake(state: AgentState) -> str:
    """Same logic as route_after_grader but capped at _MAX_INTAKE_RETRIEVAL_ATTEMPTS."""
    score    = state.get("relevance_score", 0.0)
    prev     = state.get("prev_relevance_score", 0.0)
    attempts = state.get("retrieval_attempts", 1)
    delta    = score - prev

    if state.get("fact_delta", 1) == 0 and attempts > 1:
        return "intake_node"

    still_improving = delta > _CONVERGENCE_MIN_DELTA or attempts == 1
    budget_left     = attempts < _MAX_INTAKE_RETRIEVAL_ATTEMPTS

    if score < _RELEVANCE_THRESHOLD and budget_left and still_improving:
        return "retrieval_node"
    return "intake_node"


def route_after_hallucination(state: AgentState) -> str:
    if state.get("is_grounded"):
        return "finalizer_node"

    confidence = state.get("confidence", 0.0)
    prev_conf  = state.get("prev_confidence", 0.0)
    attempts   = state.get("generation_attempts", 1)
    delta      = confidence - prev_conf

    still_improving = delta > _CONVERGENCE_MIN_DELTA or attempts == 1
    budget_left     = attempts < _MAX_GENERATION_ATTEMPTS

    if budget_left and still_improving:
        return "generation_node"
    return "finalizer_node"