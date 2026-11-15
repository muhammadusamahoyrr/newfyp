"""Client-chat response-length policy and the repaired "make it short" path
(2026-10-13). Offline: no Chroma, no live model (the LLM is a capturing fake)."""
from __future__ import annotations

import asyncio

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.ai import response_policy as R


# ── the policy ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("query,complexity,expected", [
    ("What is Section 489-F PPC?", "simple", R.BRIEF),
    ("khula kya hota hai?", "simple", R.BRIEF),
    ("تعزیرات پاکستان کی دفعہ 420 کیا ہے؟", "simple", R.BRIEF),
    ("How do I register an FIR in Punjab?", "simple", R.STANDARD),
    ("My partner gave me a cheque of 5 lakh rupees to repay what he owed me and it bounced last week "
     "and he refuses to pay", "simple", R.CASE),
    ("How do I evict a tenant?", "complex", R.CASE),
    ("Explain bail in detail", "simple", R.DETAILED),
    ("short mein batao bail kaise milti hai", "simple", R.BRIEF),
])
def test_modes_for_the_client_with_the_policy_on(query, complexity, expected):
    assert R.decide_mode(query=query, followup_intent=None, complexity=complexity,
                         surface="client", enabled=True) == expected


def test_an_explicit_request_beats_complexity():
    q = "My partner's cheque of 5 lakh bounced and he refuses to pay, tell me in short"
    assert R.decide_mode(query=q, followup_intent=None, complexity="complex", surface="client",
                         enabled=True) == R.BRIEF


@pytest.mark.parametrize("surface", [None, "research", "lawyer", ""])
def test_lawyer_research_and_unknown_surfaces_stay_legacy(surface):
    for fi in (None, "format", "deepen"):
        assert R.decide_mode(query="Explain bail in detail", followup_intent=fi, complexity="complex",
                             surface=surface, enabled=True) == R.LEGACY


def test_policy_off_keeps_legacy_except_the_make_it_short_turn():
    kw = dict(complexity="simple", surface="client", enabled=False)
    assert R.decide_mode(query="What is 302 PPC?", followup_intent=None, **kw) == R.LEGACY
    assert R.decide_mode(query="explain in detail", followup_intent="deepen", **kw) == R.LEGACY
    assert R.decide_mode(query="make it short", followup_intent="format", **kw) == R.BRIEF


def test_the_surface_is_never_read_from_the_browser_payload():
    """_build_state takes the client's raw `data`; a forged surface there must
    not reach the graph state (the route sets it)."""
    from app.websockets.chat_socket import _build_state
    st = _build_state("q", "s", {}, {"surface": "client", "language": "en"}, history=[])
    assert "surface" not in st


@pytest.mark.parametrize("mode", R.MODES)
@pytest.mark.parametrize("urdu", [False, True])
def test_every_prompt_keeps_the_mandatory_rules(mode, urdu):
    p = R.system_prompt(mode, urdu, followup=False, shorten=False)
    assert '{"confidence": 0.85}' in p and "[1]" in p
    assert ("15" in p) and (("deadline" in p) or ("مدت" in p))


# ── the client follow-up overrides ───────────────────────────────────────────

HISTORY = [{"role": "user", "content": "My partner's cheque bounced. What can I do?"},
           {"role": "assistant", "content": "Under Section 489-F PPC [1] ..."}]


def test_make_it_short_reanswers_the_previous_question_through_the_graph():
    from app.websockets.chat_socket import client_turn_overrides
    out = client_turn_overrides("format_brief", HISTORY, "Under Section 489-F PPC [1] ...")
    assert out == {"followup_intent": "format",
                   "followup_base_query": HISTORY[0]["content"],
                   "retrieval_query_supplement": HISTORY[0]["content"]}


def test_explain_in_detail_also_searches_the_previous_question():
    from app.websockets.chat_socket import client_turn_overrides
    out = client_turn_overrides("format_detail", HISTORY, "x")
    assert out["followup_intent"] == "deepen" and out["retrieval_query_supplement"] == HISTORY[0]["content"]


def test_make_it_short_with_nothing_to_shorten_is_an_ordinary_question():
    from app.websockets.chat_socket import client_turn_overrides
    assert client_turn_overrides("format_brief", [], None) == {}
    assert client_turn_overrides("new_query", HISTORY, "x") == {}


@pytest.mark.parametrize("q,reshape", [
    ("make it short", True),
    ("aur batao", True),
    ("explain in more detail", True),
    ("can you explain this in more detail please", True),
    ("isko mukhtasar kar ke batao", True),
    ("Explain in simple words the punishment for theft", False),
    ("What further remedies does a tenant have against eviction", False),
    ("tell me more about khula in family court", False),
])
def test_a_new_question_with_a_format_word_is_not_a_reshape(q, reshape):
    from app.websockets.chat_socket import client_turn_overrides, is_reshape_request
    assert is_reshape_request(q) is reshape
    out = client_turn_overrides("format_brief", HISTORY, "x", query=q)
    assert bool(out) is reshape, q


@pytest.mark.parametrize("q,canned", [
    ("ok", True), ("thanks", True), ("got it", True), ("theek hai", True),
    ("thank you so much", True), ("bas", True),
    ("Okay, now tell me how to file an FIR", False),
    ("ok what is bail", False),
    ("yes kya mujhe khula mil sakta hai", False),
    ("Is there enough evidence?", False),
    ("Yes, I want to file for khula in Lahore", False),
])
def test_a_canned_reply_is_only_for_a_short_message_that_asks_nothing(q, canned):
    from app.websockets.chat_socket import allows_canned_reply
    assert allows_canned_reply(q) is canned


def test_format_brief_is_answered_by_the_graph_not_a_shortcut():
    from app.websockets import chat_socket as cs
    import inspect
    src = inspect.getsource(cs)
    assert "format_brief" not in cs._SHORTCUT_INTENTS
    assert "_reformat(" not in src
    assert 'state["surface"] = "client"' in src and "client_turn_overrides(" in src


# ── generation uses the policy; old chips are never carried over ────────────

class _CaptureLLM:
    def __init__(self, reply="Short answer under Section 489-F PPC [1].\n{\"confidence\": 0.8}"):
        self.reply, self.messages = reply, None

    def invoke(self, messages):
        self.messages = messages
        return AIMessage(content=self.reply)


CHUNK = {"statute": "PPC 1860", "section_number": "489-F", "content": "489-F. Dishonestly issuing a cheque",
         "chunk_id": "c1", "province": "federal", "source_file": "ppc.pdf"}


def _gen(monkeypatch, *, enabled, **state):
    from app.ai.nodes import generation_node as g
    from app.core.config import settings
    llm = _CaptureLLM()
    monkeypatch.setattr(g, "get_llm", lambda **k: llm)
    monkeypatch.setattr(settings, "chat_adaptive_length_client", enabled)
    base = {"query": "What is Section 489-F PPC?", "language": "en", "reranked_chunks": [CHUNK],
            "case_law_chunks": [], "tool_results": [], "messages": [], "province": "punjab",
            "case_type": "criminal"}
    out = asyncio.run(g.generation_node({**base, **state}))
    return out, llm.messages


def test_policy_on_client_definition_gets_the_brief_prompt(monkeypatch):
    out, msgs = _gen(monkeypatch, enabled=True, surface="client")
    assert out["response_mode"] == R.BRIEF and "SHORT answer" in msgs[0]["content"]
    assert "**Issue:**" not in msgs[0]["content"]


def test_policy_off_is_the_old_irac_prompt(monkeypatch):
    out, msgs = _gen(monkeypatch, enabled=False, surface="client")
    assert out["response_mode"] == R.LEGACY and "**Issue:**" in msgs[0]["content"]


def test_lawyer_research_prompt_is_unchanged_with_the_policy_on(monkeypatch):
    out, msgs = _gen(monkeypatch, enabled=True)               # no surface: research route
    assert out["response_mode"] == R.LEGACY and "**Issue:**" in msgs[0]["content"]


def test_make_it_short_reanswers_the_base_question_briefly(monkeypatch):
    prev_q = "My partner's cheque bounced. What can I do?"
    out, msgs = _gen(monkeypatch, enabled=False, surface="client", query="make it short",
                     followup_intent="format", followup_base_query=prev_q,
                     messages=[HumanMessage(content=prev_q), AIMessage(content="Long answer [1]"),
                               HumanMessage(content="make it short")])
    assert out["response_mode"] == R.BRIEF
    assert f"Question: {prev_q}" in msgs[1]["content"]
    assert "SHORTER version" in msgs[0]["content"]


def test_a_new_claim_in_a_shortened_answer_is_checked_not_inherited():
    """The shortened text is citation-matched like any answer: a provision the
    rewrite introduces that is not in the evidence is flagged `unresolved`,
    and nothing from the previous turn's chips is copied onto it."""
    from app.ai.answer_citations import annotate_citations_from_evidence
    from app.ai.answer_citations import build_generation_evidence
    evidence = build_generation_evidence([CHUNK], [], [], statute_limit=8)
    text = "Issuing a bad cheque is an offence under Section 489-F PPC [1]. You may also sue under Section 999 PPC."
    cites = annotate_citations_from_evidence(text, evidence)
    status = {c["section"]: c["status"] for c in cites if c.get("status") in ("matched", "unresolved")}
    assert status.get("489-F") == "matched" and status.get("999") == "unresolved"


def test_a_shortened_answer_that_drops_every_citation_has_none_to_show():
    from app.ai.answer_citations import annotate_citations_from_evidence, build_generation_evidence
    evidence = build_generation_evidence([CHUNK], [], [], statute_limit=8)
    cites = annotate_citations_from_evidence("You should talk to a lawyer.", evidence)
    assert not [c for c in cites if c.get("status") == "matched"], "no chip is claimed for an uncited answer"


# ── the result cache keeps modes apart ───────────────────────────────────────

def test_brief_and_detailed_answers_never_share_a_cache_entry(monkeypatch):
    from app.ai import cache
    monkeypatch.setattr(cache, "get_redis", lambda: None)
    cache._result_store.clear()
    payload = {"answer": "short", "citations": [], "claims": [], "confidence": 0.8, "is_grounded": True}

    async def go():
        await cache.set_result("what is 489-f", "criminal", "punjab", payload, variant="brief|resp-policy-v1")
        hit_same = await cache.get_result("what is 489-f", "criminal", "punjab", variant="brief|resp-policy-v1")
        hit_detail = await cache.get_result("what is 489-f", "criminal", "punjab",
                                            variant="detailed|resp-policy-v1")
        hit_legacy = await cache.get_result("what is 489-f", "criminal", "punjab")
        return hit_same, hit_detail, hit_legacy
    same, detail, legacy = asyncio.run(go())
    assert same and same["answer"] == "short"
    assert detail is None and legacy is None


def test_a_policy_version_change_never_reads_old_entries():
    from app.ai import cache
    assert cache._make_key("q", "c", "p", "en", "brief|resp-policy-v1") != \
        cache._make_key("q", "c", "p", "en", "brief|resp-policy-v2")
    assert cache._make_key("q", "c", "p", "en") != cache._make_key("q", "c", "p", "en", "brief|resp-policy-v1")


def test_read_and_write_use_the_same_variant(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "chat_adaptive_length_client", True)
    st = {"query": "What is 302 PPC?", "surface": "client", "complexity": "simple"}
    assert R.cache_variant(st) == f"{R.BRIEF}|{R.POLICY_VERSION}|client|{R.CLIENT_GUARD_VERSION}"
    # Research keeps its exact pre-existing key: its cache is untouched.
    assert R.cache_variant({**st, "surface": None}) == R.LEGACY


def test_client_and_research_answers_never_share_a_cache_entry(monkeypatch):
    """Client answers have unsupported periods removed; research answers do
    not. With the flag off both used to map to "legacy"."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "chat_adaptive_length_client", False)
    st = {"query": "What is 302 PPC?", "complexity": "simple"}
    assert R.cache_variant({**st, "surface": "client"}) != R.cache_variant(st) == R.LEGACY


def test_history_dependent_and_follow_up_turns_stay_uncached():
    from app.ai import cache
    from app.ai.nodes.cache_node import cache_block_reason
    with_history = {"query": "and the penalty?", "messages": [HumanMessage(content="What is 489-F?"),
                                                               AIMessage(content="It is ..."),
                                                               HumanMessage(content="and the penalty?")]}
    assert cache_block_reason(with_history) == "personalised"
    for fi in ("format", "deepen"):
        assert asyncio.run(cache.get_result("q", "c", "p", fi)) is None


# ── eval-found fixes (after run, 2026-10-13) ─────────────────────────────────

def test_make_it_short_never_asks_a_new_fact_question(monkeypatch):
    """After run: "make it short" came back as a fact-gap QUESTION about the
    original matter. A presentation follow-up must re-answer, not interrogate."""
    from app.ai.nodes import fact_gap_node as fg

    def boom(**_):
        raise AssertionError("fact-gap model must not run for a client presentation follow-up")
    monkeypatch.setattr(fg, "get_llm", boom)
    st = {"query": "make it short", "complexity": "complex", "known_facts": [], "province": "punjab",
          "case_type": "criminal", "surface": "client", "followup_intent": "format",
          "followup_base_query": "My partner's cheque bounced. What can I do?"}
    out = asyncio.run(fg.fact_gap_node(st))
    assert out["needs_clarification"] is False


def test_the_fact_gap_skip_is_client_only(monkeypatch):
    """Without the client surface (lawyer research), the old checks still run."""
    from app.ai.nodes import fact_gap_node as fg
    called = {}

    class _L:
        def invoke(self, m):
            called["yes"] = True
            return AIMessage(content="PROCEED")
    monkeypatch.setattr(fg, "get_llm", lambda **k: _L())
    st = {"query": "make it short", "complexity": "complex", "known_facts": [], "province": "punjab",
          "case_type": "criminal", "followup_intent": "format", "followup_base_query": "x"}
    asyncio.run(fg.fact_gap_node(st))
    assert called.get("yes")


@pytest.mark.parametrize("mode", [R.BRIEF, R.STANDARD, R.CASE, R.DETAILED])
def test_policy_prompts_require_the_act_name_with_each_section(mode):
    """After run: a brief answer cited a bare "Section 15" and lost every chip."""
    assert "WITH its Act" in R.system_prompt(mode, False, followup=False, shorten=False)
    assert "Section 489-F PPC" in R.system_prompt(mode, True, followup=False, shorten=False)


def test_make_it_short_is_classified_on_the_question_it_reanswers():
    """Final after run: "make it short" was keyword-classified on its own words
    (no legal signal -> hybrid, confidence 0) and routed to clarification_node,
    so the user got a question back instead of a shorter answer."""
    from app.ai.nodes.classifier_node import classifier_node
    from app.ai.graph.edges import route_after_triage
    base = "Someone gave me a cheque and it bounced, the bank dishonoured it. Can I file an FIR?"
    st = {"query": "make it short", "province": "punjab", "case_type": "unknown", "surface": "client",
          "followup_intent": "format", "followup_base_query": base}
    out = classifier_node(st)
    assert out["classifier_confidence"] > 0.0
    assert route_after_triage({**st, **out, "case_type": out.get("case_type") or out["classifier_case_type"]}) \
        == "fact_gap_node"


def test_lawyer_research_classification_is_unchanged():
    from app.ai.nodes.classifier_node import classifier_node
    st = {"query": "make it short", "province": "punjab", "case_type": "unknown",
          "followup_intent": "format", "followup_base_query": "cheque bounced dishonoured FIR"}
    assert classifier_node(st) == classifier_node({k: v for k, v in st.items() if k != "followup_base_query"})
    assert R.presentation_base_query(st) is None


def test_make_it_short_is_graded_on_the_question_it_reanswers():
    """Follow-up recheck: with normalized_query = "make it short", the grader
    scored every chunk irrelevant and the decision engine refused the turn."""
    from app.ai.nodes.triage_node import triage_node
    base = "My partner's cheque bounced. What can I do?"
    st = {"query": "make it short", "language": "en", "province": "punjab", "case_type": "criminal",
          "messages": [], "surface": "client", "followup_intent": "format", "followup_base_query": base}
    assert asyncio.run(triage_node(st))["normalized_query"] == base
    lawyer = {k: v for k, v in st.items() if k != "surface"}
    assert asyncio.run(triage_node(lawyer))["normalized_query"] == "make it short"


def test_a_reanswered_followup_never_touches_the_cache(monkeypatch):
    """normalized_query now equals the earlier question, so the follow-up
    guard is what keeps a shortened answer out of that question's entry."""
    from app.ai import cache
    monkeypatch.setattr(cache, "get_redis", lambda: None)
    cache._result_store.clear()
    payload = {"answer": "full", "citations": [], "claims": [], "confidence": 0.8, "is_grounded": True}
    asyncio.run(cache.set_result("my partner's cheque bounced. what can i do?", "criminal", "punjab", payload))
    assert asyncio.run(cache.get_result("my partner's cheque bounced. what can i do?", "criminal", "punjab",
                                        "format")) is None


def test_an_untyped_make_it_short_is_typed_from_the_question_it_reanswers(monkeypatch):
    """Follow-up recheck: "cheque bounced" / "506 PPC" have no classifier
    keyword and the socket stores no case type, so "make it short" was routed
    to clarification. Triage now types the base question -- the same call a
    new question gets -- and only on this path."""
    from app.ai.nodes import triage_node as tn
    seen = {}

    class _L:
        def invoke(self, messages):
            seen["user"] = messages[-1]["content"]
            return tn.TriageOutput(category="legal", case_type="criminal", case_type_confidence=0.9,
                                   complexity="simple", urgency="low", province="unknown",
                                   language="en", normalized_query=seen["user"], known_facts=[], reason="t")
    monkeypatch.setattr(tn, "get_structured_llm", lambda *a, **k: _L())
    base = "My business partner's cheque of 5 lakh bounced and he refuses to pay."
    st = {"query": "make it short", "language": "en", "province": "punjab", "case_type": "unknown",
          "messages": [], "surface": "client", "followup_intent": "format", "followup_base_query": base}
    out = asyncio.run(tn.triage_node(st))
    assert seen["user"] == base and out["case_type"] == "criminal" and out["followup_intent"] == "format"
    # ...and the typed turn must ROUTE onward: the keyword classifier found
    # nothing (hybrid, 0.0), so routing reads the triage confidence.
    from app.ai.graph.edges import route_after_triage
    routed = {**st, "classifier_case_type": "unknown", "classifier_confidence": 0.0,
              "routing_mode": "hybrid", **out}
    assert route_after_triage(routed) == "fact_gap_node"


def test_research_followups_make_no_extra_triage_call(monkeypatch):
    from app.ai.nodes import triage_node as tn

    def boom(*a, **k):
        raise AssertionError("no triage call on a research follow-up")
    monkeypatch.setattr(tn, "get_structured_llm", boom)
    st = {"query": "make it short", "language": "en", "province": "punjab", "case_type": "unknown",
          "messages": [], "followup_intent": "format", "followup_base_query": "x"}
    assert asyncio.run(tn.triage_node(st))["normalized_query"] == "make it short"


def test_lawyer_research_and_legal_intake_never_enter_the_client_surface():
    """Every 2026-10-13/14 client-chat change (length policy, follow-up routing,
    period guard, exact provision, marker attachment) is gated on
    state["surface"] == "client", which only the client socket sets. If the
    research route or Legal Intake ever set it, they would silently change."""
    import inspect
    from app.api.v1.routes import ai as research_routes
    from app.services import intake_service
    from app.websockets import chat_socket
    # Research sets ITS OWN surface (2026-10-14, server-side) -- never client.
    research_src = inspect.getsource(research_routes)
    assert '"surface": "client"' not in research_src and 'state["surface"] = "client"' not in research_src
    assert 'state["surface"] = answer_safeguards.SURFACE_RESEARCH' in research_src
    intake_src = inspect.getsource(intake_service)
    assert 'state["surface"]' not in intake_src and '"surface":' not in intake_src
    assert inspect.getsource(chat_socket).count('state["surface"] = "client"') == 1
