"""General guidance instead of a blank refusal -- lawyer research, and (2026-10-20) the
client chat in plain language; and questions ABOUT the assistant answered as such."""
from __future__ import annotations

import pytest

from app.ai import general_guidance
from app.ai.graph.edges import is_general_question, route_after_triage
from app.ai.nodes import finalizer_node as fin


@pytest.fixture
def guidance(monkeypatch):
    calls = []

    async def fake(state, audience="lawyer"):
        calls.append((state.get("query"), audience))
        return general_guidance.HEADER_EN + "\n\n**Fundamental rights** — Part II, Chapter 1 of the Constitution."
    monkeypatch.setattr(general_guidance, "write", fake)
    return calls


async def test_a_lawyer_gets_labelled_guidance_not_a_blank_refusal(guidance):
    out = await fin.finalizer_node({"query": "what are the fundamental rights?", "surface": "research",
                                    "arbitration_output": "refuse", "arbitration_source": "llm"})
    assert out["convergence_status"] == "general_guidance"
    assert out["answer"].startswith("General guidance — not from the AttorneyAI legal library")
    assert out["is_grounded"] is False and out["confidence"] == 0.0


async def test_the_client_gets_plain_general_information_not_a_blank_refusal(guidance):
    out = await fin.finalizer_node({"query": "what are the fundamental rights?", "surface": "client",
                                    "arbitration_output": "refuse"})
    assert out["convergence_status"] == "general_guidance"
    assert guidance == [("what are the fundamental rights?", "client")], "the client got the lawyer's version"


async def test_an_unknown_surface_still_refuses(guidance):
    out = await fin.finalizer_node({"query": "what are the fundamental rights?", "surface": "chat",
                                    "arbitration_output": "refuse"})
    assert out["answer"] == fin._REFUSE and guidance == []


async def test_a_fault_is_never_dressed_up_as_guidance(guidance):
    out = await fin.finalizer_node({"query": "q", "surface": "research", "retrieval_error": True})
    assert out["answer"] == fin._REFUSE_ERROR and guidance == []


async def test_a_refusal_given_for_a_reason_stands(guidance):
    out = await fin.finalizer_node({"query": "current stamp duty rate?", "surface": "research",
                                    "refusal_reason": "The rate is set by notification, not statute."})
    assert out["convergence_status"] == "unanswerable" and guidance == []


async def test_if_the_model_fails_the_refusal_stands(monkeypatch):
    async def none(state, audience="lawyer"):
        return None
    monkeypatch.setattr(general_guidance, "write", none)
    out = await fin.finalizer_node({"query": "q", "surface": "research"})
    assert out["answer"] == fin._REFUSE


@pytest.mark.parametrize("q,general", [
    ("can you tell me whats the five main civil rights ?", True),
    ("What are the fundamental rights in the Constitution?", True),
    ("explain bail before arrest", True),
    ("My landlord kept my deposit, what can I do?", False),
    ("I was arrested yesterday, what are my rights?", False),
    ("Section 302 PPC", False),
    # 2026-10-21: a length word first, Roman Urdu and Urdu
    ("Briefly, what is khula?", True),
    ("In simple words: what is bail?", True),
    ("chori ki saza kya hai?", True),
    ("khula kise kehte hain", True),
    ("خلع کیا ہے؟", True),
    ("ضمانت سے کیا مراد ہے", True),
    ("What are the main fundamental rights?", True),
    ("meri biwi ghar chor gayi hai ab kya hota hai", False),
    ("maine cheque diya tha jo bounce ho gaya, kya hai saza?", False),
    ("kya main bail le sakta hun", False),
    ("میرے شوہر نے طلاق دے دی، اب کیا ہے؟", False),
    ("Briefly, my landlord kept my deposit", False),
])
def test_general_questions_are_told_apart_from_a_matter(q, general):
    assert is_general_question(q) is general


@pytest.mark.parametrize("q", ["Briefly, what is khula?", "chori ki saza kya hai?", "خلع کیا ہے؟"])
def test_a_general_client_question_in_any_language_is_answered_not_questioned(q):
    state = {"query": q, "surface": "client", "province": "unknown", "case_type": "unknown",
             "routing_mode": "hybrid", "classifier_confidence": 0.0}
    assert route_after_triage(state) == "fact_gap_node"


async def test_fact_gap_does_not_question_a_general_question(monkeypatch):
    from app.ai.nodes import fact_gap_node as fg

    def no_llm(*a, **k):
        raise AssertionError("fact_gap must not ask the model about a general question")
    monkeypatch.setattr(fg, "get_llm", no_llm)
    out = await fg.fact_gap_node({"query": "chori ki saza kya hai?", "surface": "client",
                                  "complexity": "complex", "known_facts": []})
    assert out["needs_clarification"] is False


async def test_fact_gap_still_questions_the_asker_s_own_matter(monkeypatch):
    from app.ai.nodes import fact_gap_node as fg
    calls = []

    class LLM:
        def invoke(self, msgs):
            calls.append(msgs)
            return type("R", (), {"content": "PROCEED"})()
    monkeypatch.setattr(fg, "get_llm", lambda **k: LLM())
    await fg.fact_gap_node({"query": "meri biwi ghar chor gayi hai", "surface": "client",
                            "complexity": "complex", "known_facts": [], "case_type": "family"})
    assert calls, "a matter still goes through the fact-gap check"


def test_client_prompts_ask_one_question_only_when_a_fact_decides_the_answer():
    from app.ai import response_policy as R
    for urdu in (False, True):
        for mode in R.MODES:
            p = R.system_prompt(mode, urdu, followup=False, shorten=False)
            assert ("ONE short question" in p) or ("صرف ایک مختصر سوال" in p)
    assert R.POLICY_VERSION == "resp-policy-v2"


def test_a_general_research_question_is_not_sent_round_clarification():
    state = {"query": "what are the fundamental rights?", "surface": "research",
             "province": "unknown", "case_type": "unknown"}
    assert route_after_triage(state) == "fact_gap_node"
    # The client chat keeps its own routing.
    assert route_after_triage({**state, "surface": "chat"}) == "clarification_node"


# ── questions ABOUT the assistant (ai/client_help.py) ────────────────────────

from app.ai import client_help  # noqa: E402


@pytest.mark.parametrize("q,yes", [
    ("can you guide me on my legal matter", True),
    ("Can you help me?", True),
    ("I need legal help", True),
    ("what can you do?", True),
    ("kya aap meri madad kar sakte hain", True),
    ("کیا لیگل معاملے میں تم میری رہنمائی کر سکتے ہو؟", True),
    ("Can you help me, my landlord locked me out of the house yesterday in Lahore", False),
    ("what is bail", False),
    ("Section 302 PPC", False),
])
def test_capability_questions_are_told_apart(q, yes):
    assert client_help.is_capability_question(q) is yes


async def test_a_capability_question_is_answered_in_the_askers_language(guidance):
    for q, lang, start in [("can you guide me on my legal matter", "en", "Yes — I can help"),
                           ("کیا لیگل معاملے میں تم میری رہنمائی کر سکتے ہو؟", "ur", "جی ہاں"),
                           ("kya aap meri madad kar sakte hain", "roman_urdu", "Ji haan")]:
        assert route_after_triage({"query": q, "surface": "client", "province": "unknown", "case_type": "unknown"}) == "finalizer_node"
        out = await fin.finalizer_node({"query": q, "language": lang, "surface": "client", "convergence_status": "off_topic",
                                        "answer": "That is not a legal question."})
        assert out["convergence_status"] == "capability"
        assert out["answer"].startswith(start), q
        assert out["is_grounded"] is False
    assert guidance == [], "a capability answer called the model"


async def test_triage_lets_a_capability_question_through_ungrounded(monkeypatch):
    # "help me" has one 3+ letter word (the gibberish guard) and the model may
    # call "what can you do?" off-topic; both marked the turn grounded, so the
    # finalizer skipped the capability answer.
    from app.ai.nodes import triage_node as tri

    def no_model(*a, **k):
        raise AssertionError("triage called the model for a capability question")
    monkeypatch.setattr(tri, "get_structured_llm", no_model)
    for q, lang in [("help me", "en"), ("what can you do?", "en"),
                    ("kya aap meri madad kar sakte hain", "roman_urdu"),
                    ("کیا آپ میری مدد کر سکتے ہیں؟", "ur")]:
        out = await tri.triage_node({"query": q, "messages": []})
        assert not out.get("is_grounded") and "answer" not in out, q
        assert out["language"] == lang, q
        fin_out = await fin.finalizer_node({**out, "query": q, "surface": "client"})
        assert fin_out["convergence_status"] == "capability", q


def test_a_clients_general_question_is_answered_not_sent_round_clarification():
    state = {"query": "What is khula in Pakistan and how can a wife get it?", "surface": "client",
             "province": "unknown", "case_type": "unknown"}
    assert route_after_triage(state) == "fact_gap_node"
    # A client's own matter still gets its questions.
    own = {**state, "query": "My husband left me, what can I do?"}
    assert route_after_triage(own) != "fact_gap_node" or own["case_type"] != "unknown"
