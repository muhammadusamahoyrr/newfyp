"""
triage_node.py — LLM-based legal intent classifier.

Runs AFTER classifier_node (which does fast keyword triage).
Confirms or overrides the classifier's case_type with richer LLM reasoning.
"""
from __future__ import annotations

import asyncio
import logging
import re

from langchain_core.messages import AIMessage
from pydantic import BaseModel, Field

from app.ai.graph.state import AgentState
from app.ai.llm import get_structured_llm
from app.ai.provider_health import PURPOSE_TRIAGE
from app.ai.nodes._history import format_history
from app.ai.response_policy import presentation_base_query

logger = logging.getLogger(__name__)

# ── Canned responses ──────────────────────────────────────────────────────────

_CANNED_OFF_TOPIC = (
    "I can only assist with Pakistani legal matters. "
    "Please describe a legal issue or question related to Pakistani law."
)

# A client "make it short" / "explain in detail" turn whose area of law could
# not be established. Retrieval would fall back to the civil collection, which
# is the wrong law for a criminal question, so the turn ends here instead.
_UNTYPED_FOLLOWUP_EN = (
    "I couldn't tell which area of law your previous question falls under, so I "
    "can't safely re-answer it in a different length. Please ask the question "
    "again, with a little detail about your situation."
)
_UNTYPED_FOLLOWUP_UR = (
    "میں یہ طے نہیں کر سکا کہ آپ کا پچھلا سوال قانون کے کس شعبے سے متعلق ہے، اس لیے "
    "اسے مختصر یا تفصیل سے دوبارہ محفوظ طریقے سے نہیں بتا سکتا۔ براہِ کرم اپنا سوال "
    "اپنی صورتحال کی تھوڑی تفصیل کے ساتھ دوبارہ پوچھیں۔"
)

_CANNED_GIBBERISH = (
    "I didn't quite understand that. Could you describe your legal issue "
    "in a little more detail? For example: 'My landlord won't return my deposit' "
    "or 'I was assaulted and want to file an FIR'."
)

_CANNED_AFFIRM = (
    "Understood. Feel free to ask any follow-up questions or describe another "
    "legal matter you need help with."
)

_MIN_REAL_WORDS = 2


def _is_gibberish(query: str) -> bool:
    words = re.findall(r'[a-zA-Z؀-ۿ]{3,}', query)
    return len(words) < _MIN_REAL_WORDS


# Arabic/Urdu script block. Presence or absence of these characters is a FACT
# about the string, so it beats the model's opinion about which script it is.
_URDU_SCRIPT_RE = re.compile(r'[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]')

# Strong Roman-Urdu function words. Two are required so an English legal
# question containing one borrowed word ("talaq", "nikah", "khula") stays
# English, while ordinary Roman Urdu remains detectable without asking an LLM
# that has also been shown the conversation history.
_ROMAN_URDU_WORD_RE = re.compile(
    r"\b(?:aap|ap|mein|main|mujhe|mera|meri|mere|hum|hamara|kya|kia|kyun|kaise|"
    r"hai|hain|tha|thi|nahi|nahin|ko|se|ke|ki|ka|kar|karein|karun|raha|rahi|"
    r"wala|wali|chahiye|batao|batayein|qanoon|wakeel|shohar|biwi)\b",
    re.IGNORECASE,
)


EN_INVARIANT_VIOLATION = "triage_en_normalization"


def _enforce_en_invariant(
    query: str, language: str, normalized: str
) -> tuple[str, str | None]:
    """An English query passes through untouched. Returns (normalized, flag).

    The prompt states this ("If language is 'en': return the original query
    unchanged") and nothing enforced it until FAILURE_CASE_001, where "What is
    the punishment for theft under the Pakistan Penal Code?" was labelled "en"
    and rewritten into corrupted Urdu injecting سرکاری ("official") three times.
    That matters more than a mangled string: normalized_query is what retrieval
    searches AND what the answer cache is keyed on, so the corruption sent
    retrieval after a different concept -- 18 chunks, none of them PPC 379 --
    and the answer cited the wrong section while every downstream gate reported
    success, because each of them trusted this field.

    REPAIRS rather than raises. The contract names the correct value, so failing
    the turn would deny a user an answer over a fault we can fix exactly. But it
    is never a silent repair: the caller flags the record, so a turn built from
    corrupted input cannot be graded as though the pipeline had behaved.

    Compared stripped -- trailing whitespace is not corruption. An empty
    normalized is the caller's own fallback to the raw query, not a violation.
    """
    if language != "en" or not normalized.strip():
        return normalized, None
    if normalized.strip() == query.strip():
        return normalized, None

    logger.error(
        "triage: INVARIANT VIOLATED — language='en' must return the query "
        "unchanged. Repairing to the original. query=%r normalized=%r",
        query[:200], normalized[:200],
    )
    return query, EN_INVARIANT_VIOLATION


def _reconcile_language(query: str, language: str) -> str:
    """
    Correct the LLM's language label against the script actually present.

    Observed in production: "mera shohar mujhe kharch nahi deta, maintenance ka
    kya tareeqa hai?" was labelled "ur". It contains no Urdu characters at all.
    That mislabel matters twice — triage only transliterates when it believes the
    input is Roman Urdu, and generation answers in the language it was told, so
    a user typing Latin script got an Urdu-script reply.
    """
    # The model sees conversation history as well as this message. Its label can
    # therefore describe the conversation's language instead of the current
    # question's language. Script is conclusive; Roman Urdu needs two
    # characteristic words; everything else is English. The model's label is
    # deliberately not a tie-breaker.
    if _URDU_SCRIPT_RE.search(query):
        return "ur"
    if len(_ROMAN_URDU_WORD_RE.findall(query or "")) >= 2:
        return "roman_urdu"
    return "en"


def _prefer_fast() -> bool:
    """Use the fast tier (Gemini Flash) when its key is set, else the capable tier."""
    from app.core.config import settings
    return bool(settings.gemini_api_key)


def _resolved_case_type(state: AgentState) -> str:
    """Best available case type when the triage LLM returns "unknown".

    classifier_node runs first and scores the query on keywords, but it only
    promotes its finding into `case_type` above a HIGH confidence bar. Below
    that it writes only `classifier_case_type`, and triage used to fall back to
    `case_type` alone — so a correct classification was computed and then
    thrown away.

    Observed live: "What are the grounds for khula under Pakistani family law?"
    scored classifier_case_type='family' at 0.35, the triage LLM answered
    "unknown", and the turn was routed to clarification and never retrieved
    anything. The word "khula" is in the classifier's family keywords; nothing
    was missing except this handoff.
    """
    existing = str(state.get("case_type") or "").strip()
    if existing and existing != "unknown":
        return existing

    hinted = str(state.get("classifier_case_type") or "").strip()
    if hinted and hinted != "unknown" and (state.get("classifier_confidence") or 0) > 0:
        return hinted

    return "unknown"


# ── Follow-up intent detection (LLM structured output) ───────────────────────

_INTENT_SYSTEM = """\
You are classifying a user's follow-up intent in a Pakistani legal AI assistant.

Given the AI's previous response and the user's new message, classify the intent
into exactly one of four categories:

"format"  — The user wants the SAME content presented differently: shorter,
            simpler, or in a different structure. The topic does NOT change.
            Examples: "explain it briefly", "briefly", "in brief please",
            "tldr", "bullet points", "simpler terms", "shorten this",
            "summarize that", "be more concise"

"deepen"  — The user wants MORE information on the same or a directly related
            sub-topic. Examples: "tell me more", "elaborate on point 2",
            "what are the penalties?", "and what about bail?"

"affirm"  — The user is acknowledging, not asking anything new.
            Examples: "ok", "yes", "got it", "thanks", "theek hai", "shukria"

"new"     — The user introduces a completely different legal question or scenario.

Rules:
- "format" wins whenever phrasing is about HOW information is delivered.
- "new" wins when a new legal entity, statute, or fact pattern appears.
- Urdu/Roman Urdu affirmations ("theek hai", "acha", "shukria") -> "affirm".

Return JSON only: { "intent": "...", "confidence": 0.0 }"""


class FollowupIntent(BaseModel):
    intent:     str
    confidence: float = Field(ge=0.0, le=1.0)


def _last_ai_content(state: AgentState) -> str | None:
    for msg in reversed(state.get("messages") or []):
        if isinstance(msg, AIMessage):
            return msg.content[:600]
    return None


async def _detect_intent(query: str, last_ai: str) -> FollowupIntent:
    """LLM intent classification. Falls back to intent='new' on any error."""
    try:
        llm = get_structured_llm(FollowupIntent, fast=_prefer_fast(),
                                 purpose=PURPOSE_TRIAGE)
        return await asyncio.to_thread(llm.invoke, [
            {"role": "system", "content": _INTENT_SYSTEM},
            {"role": "user",   "content": (
                f"Previous AI response:\n{last_ai}\n\n"
                f"User's message: {query}"
            )},
        ])
    except Exception:
        return FollowupIntent(intent="new", confidence=0.0)


# ── LLM triage system prompt ──────────────────────────────────────────────────

_SYSTEM = """\
You are a legal triage specialist for an AI system focused exclusively on Pakistani law.

Analyze the user's query and return JSON with these fields:

category:
  "legal"     — relates to Pakistani law, courts, rights, contracts, crimes, property, family law, documents
  "off_topic" — unrelated to law (greetings, tech, cooking, etc.)
  "gibberish" — random characters, meaningless text, cannot be interpreted

language:
  "en"         — English query
  "ur"         — Urdu script query
  "roman_urdu" — Urdu written in Roman/Latin script (e.g. "mujhe police ne mara")

normalized_query:
  If language is "roman_urdu": transliterate to standard Urdu script (e.g. مجھے پولیس نے مارا).
  If language is "ur": return as-is.
  If language is "en": return the original query unchanged.

case_type:
  "civil" | "criminal" | "family" | "constitutional" | "unknown"

case_type_confidence:
  Float 0.0-1.0. High (0.85+) if explicit signals present (e.g. "FIR" -> criminal 0.95).
  Medium (0.55-0.84) if inferable. Low (0.3-0.54) if ambiguous. Use 0.0 if unknown.

complexity:
  "simple"  — single clear legal question, well-defined facts, no multi-party conflict
  "complex" — multi-party dispute, contradictory facts, overlapping legal domains

urgency:
  "critical" — immediate legal danger (arrest, custody, eviction notice, court order tomorrow)
  "high"     — court date within a week, limitation period running, FIR just filed
  "medium"   — ongoing dispute, awaiting response, case in progress
  "low"      — informational query, future planning, general legal question

province:
  "punjab" | "sindh" | "kpk" | "balochistan" | "federal" | "unknown"

known_facts:
  List of up to 5 short factual statements verbatim from the query.

reason:
  One sentence explaining the category classification.

Use "unknown" for case_type/province only when genuinely impossible to infer."""


class TriageOutput(BaseModel):
    category:             str
    language:             str
    normalized_query:     str
    case_type:            str
    case_type_confidence: float = Field(ge=0.0, le=1.0)
    complexity:           str
    urgency:              str
    province:             str
    known_facts:          list[str]
    reason:               str


# ── Node ──────────────────────────────────────────────────────────────────────

async def triage_node(state: AgentState) -> dict:
    existing_type     = state.get("case_type")  or None
    existing_province = state.get("province")   or None

    query = state["query"]

    # ── "Can you help me?" ────────────────────────────────────────────────────
    # A question ABOUT the assistant goes straight to the finalizer's fixed
    # answer (ai/client_help.py). Checked before the gibberish guard ("help me"
    # has one 3+ letter word) and before the model, which may call "what can
    # you do?" off-topic -- both mark the turn grounded, which skipped it.
    from app.ai.client_help import is_capability_question, _ROMAN
    if is_capability_question(query):
        return {
            "language":           "ur" if _URDU_SCRIPT_RE.search(query)
                                  else "roman_urdu" if _ROMAN.match(query.strip()) else "en",
            "normalized_query":   query,
            "case_type":          _resolved_case_type(state),
            "province":           existing_province or "unknown",
            "known_facts":        state.get("known_facts", []),
            "followup_intent":    None,
            "convergence_status": "pending",
        }

    # ── Gibberish guard ───────────────────────────────────────────────────────
    if _is_gibberish(query):
        return {
            "answer":             _CANNED_GIBBERISH,
            "convergence_status": "off_topic",
            "is_grounded":        True,
            "confidence":         1.0,
            "language":           "en",
            "case_type":          _resolved_case_type(state),
            "province":           existing_province or "unknown",
            "known_facts":        state.get("known_facts", []),
            "followup_intent":    None,
        }

    # ── Honour pre-set intent injected by chat_socket ────────────────────────
    pre_intent = state.get("followup_intent")
    if pre_intent in ("format", "deepen"):
        case_type = _resolved_case_type(state)
        case_conf = state.get("case_type_confidence", 0.0)
        base_query = presentation_base_query(state)
        # A client "make it short" turn normally arrives with the case type the
        # server resolved for the previous answer (chat_socket reads it from the
        # session checkpoint). When there is none, type the question being
        # re-answered with the same triage call a new question gets -- client
        # follow-ups only; research keeps the old path. If it is STILL unknown,
        # routing ends the turn honestly (edges.route_after_triage) instead of
        # asking about "make it short" or searching the civil default.
        if base_query and case_type in ("", "unknown", None):
            try:
                llm = get_structured_llm(TriageOutput, fast=_prefer_fast(), purpose=PURPOSE_TRIAGE)
                result: TriageOutput = await asyncio.to_thread(llm.invoke, [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user",   "content": base_query},
                ])
                if result.case_type not in ("unknown", None, ""):
                    case_type = result.case_type
                    # Routing reads this when the keyword classifier found
                    # nothing (hybrid, 0.0): carrying the old 0.0 sent the
                    # typed turn to clarification anyway.
                    case_conf = result.case_type_confidence
            except Exception:
                logger.warning("triage: could not type the re-answered question", exc_info=True)
        untyped = {}
        if base_query and case_type in ("", "unknown", None):
            untyped = {"refusal_reason": _UNTYPED_FOLLOWUP_UR if state.get("language") == "ur"
                       else _UNTYPED_FOLLOWUP_EN}
        return {
            **untyped,
            "followup_intent":      pre_intent,
            "language":             state.get("language", "en"),
            # A client "make it short" turn is graded, judged and answered on
            # the question it re-answers: graded against the literal words
            # "make it short", every chunk scored irrelevant and the turn was
            # refused. Lawyer research (no client surface) keeps `query`.
            "normalized_query":     base_query or query,
            "case_type":            case_type,
            "case_type_confidence": case_conf,
            "complexity":           state.get("complexity", "simple"),
            "urgency":              state.get("urgency", "low"),
            "province":             existing_province or "unknown",
            "known_facts":          state.get("known_facts", []),
            "convergence_status":   "pending",
        }

    # ── Follow-up intent detection (fallback when chat_socket had no history) ─
    # Only run for short messages — long messages are almost certainly new legal questions.
    # Avoids LLM cost + misrouting on multi-sentence queries that follow any prior AI reply.
    last_ai = _last_ai_content(state)
    if last_ai and len(query.split()) <= 20:
        intent_result = await _detect_intent(query, last_ai)
        if intent_result.confidence >= 0.65 and intent_result.intent != "new":
            intent = intent_result.intent
            base = {
                "followup_intent":      intent,
                "language":             state.get("language", "en"),
                "normalized_query":     query,
                "case_type":            _resolved_case_type(state),
                "case_type_confidence": state.get("case_type_confidence", 0.0),
                "complexity":           state.get("complexity", "simple"),
                "urgency":              state.get("urgency", "low"),
                "province":             existing_province or "unknown",
                "known_facts":          state.get("known_facts", []),
                "convergence_status":   "pending",
            }
            if intent == "affirm":
                base["answer"]             = _CANNED_AFFIRM
                base["convergence_status"] = "off_topic"
                base["is_grounded"]        = True
                base["confidence"]         = 1.0
            return base

    # ── Full LLM triage ───────────────────────────────────────────────────────
    llm = get_structured_llm(TriageOutput, fast=_prefer_fast(),
                             purpose=PURPOSE_TRIAGE)

    words      = query.split()
    safe_query = (
        " ".join(words[:1500]) + " ... [TRUNCATED]"
        if len(words) > 1500
        else query
    )

    history      = format_history(state)
    user_content = safe_query
    if history:
        user_content = (
            f"Conversation so far:\n{history}\n\n"
            f"Current message: {safe_query}"
        )

    result: TriageOutput = await asyncio.to_thread(llm.invoke, [
        {"role": "system", "content": _SYSTEM},
        {"role": "user",   "content": user_content},
    ])

    if result.category in ("off_topic", "gibberish"):
        return {
            "answer":             _CANNED_OFF_TOPIC,
            "convergence_status": "off_topic",
            "is_grounded":        True,
            "confidence":         1.0,
            "language":           result.language,
            "case_type":          _resolved_case_type(state),
            "province":           existing_province or "unknown",
            "known_facts":        state.get("known_facts", []),
            "followup_intent":    None,
        }

    case_type = (
        result.case_type
        if result.case_type != "unknown"
        else _resolved_case_type(state)
    )
    # Jurisdiction resolution, in precedence order.
    #
    # An explicit user choice WINS over the model's inference. It did not
    # before: whatever the LLM returned for `province` overrode the province the
    # user had selected, so a Punjab client whose question the model read as
    # Sindh was answered from the wrong provincial code with no trace of the
    # substitution. A stated jurisdiction is a fact, not a hypothesis.
    #
    # The model's value is also validated rather than trusted: it has been
    # observed returning "National" for this field, which matches no province in
    # the corpus and would silently behave as unknown.
    from app.ai import jurisdiction

    province, jurisdiction_basis = jurisdiction.resolve(
        requested=existing_province,
        requested_basis=state.get("jurisdiction_basis"),
        inferred=result.province,
    )

    language = _reconcile_language(query, result.language)
    normalized = result.normalized_query or query
    invariant_violation = None

    # INVARIANT: an English query passes through untouched.
    #
    # The prompt states this ("If language is 'en': return the original query
    # unchanged"), and until this check existed nothing enforced it. Observed in
    # production (FAILURE_CASE_001.md, request 37a76e77): "What is the punishment
    # for theft under the Pakistan Penal Code?" was labelled "en" and then
    # rewritten into corrupted Urdu that injected سرکاری ("official") three
    # times. Retrieval faithfully searched that instead and returned 18 chunks,
    # none of them PPC 379; the answer cited the wrong section and no gate
    # downstream noticed, because every one of them trusted normalized_query.
    #
    # This REPAIRS rather than raises. The contract names the correct value --
    # the original query -- so failing the turn would deny a user an answer over
    # a fault we can fix exactly. But the repair is never silent: it logs at
    # ERROR and flags the record, because an answer produced from a corrupted
    # query must not be gradeable as if the pipeline had behaved.
    #
    # Compared stripped: trailing whitespace is not corruption.
    normalized, invariant_violation = _enforce_en_invariant(
        query, language, normalized
    )

    if language != result.language:
        logger.info(
            "triage: language corrected %s -> %s by script check | query=%r",
            result.language, language, query[:120],
        )
        # The model believed this was already Urdu script, so it returned the
        # text unchanged instead of transliterating. Fall back to the raw query
        # rather than presenting un-transliterated text as if it were normalised.
        if language == "roman_urdu" and not _URDU_SCRIPT_RE.search(normalized):
            normalized = query

    return {
        "language":             language,
        "normalized_query":     normalized,
        "case_type":            case_type,
        "case_type_confidence": result.case_type_confidence,
        "complexity":           result.complexity,
        "urgency":              result.urgency,
        "province":             province,
        "province_inferred":    jurisdiction_basis == "inferred_from_query",
        "jurisdiction_basis":   jurisdiction_basis,
        "known_facts":          result.known_facts,
        "convergence_status":   "pending",
        "followup_intent":      None,
        "invariant_violation":  invariant_violation,
    }
