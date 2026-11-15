"""c23 / c26 through the REAL client socket and the REAL chat graph (2026-10-13).

What is real: chat_socket.chat_endpoint (intent routing, server-side history,
session-thread checkpoint, resume detection, follow-up overrides, the output
choke point), the compiled chat_graph topology (build_chat_graph, every edge),
and the gatekeeper / classifier / triage / fact-gap / clarification / cache /
generation / grounding-judge / finalizer nodes.

What is stubbed: every model call (scripted replies), and the retrieval,
grader, decision and tool nodes (a fixed evidence set, an "answer" verdict) --
Chroma and the Decision Engine are not under test here. The checkpointer is
in-memory; the topology is the production one.

The grounding judge is scripted as OVER-TRUSTING (every claim "supported"),
which is how the live c23 deadline got through: the deterministic period check
must not depend on the judge being right.
"""
from __future__ import annotations

import asyncio

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver

import app.websockets.chat_socket as cs
from app.ai import cache, period_support
from app.ai.graph import supervisor
from app.ai.nodes import clarification_node as cn
from app.ai.nodes import fact_gap_node as fg
from app.ai.nodes import gatekeeper_node as gk
from app.ai.nodes import generation_node as gn
from app.ai.nodes import hallucination_node as hn
from app.ai.nodes import triage_node as tn
from app.core.config import settings
from app.services import provenance_outbox
from tests._conversation_fakes import FakeConversations, FakeTurns

PPC_506 = {"statute": "PPC 1860", "section_number": "506", "chunk_id": "ppc-506", "province": "federal",
           "source_file": "ppc.pdf",
           "content": ("506. Punishment for criminal intimidation.- Whoever commits the offence of criminal "
                       "intimidation shall be punished with imprisonment of either description for a term "
                       "which may extend to two years, or with fine, or with both; if threat be to cause "
                       "death or grievous hurt, etc.- and if the threat be to cause death or grievous hurt "
                       "shall be punished with imprisonment for a term which may extend to seven years.")}
CPC_34 = {"statute": "CPC 1908", "section_number": "34", "chunk_id": "cpc-34", "province": "federal",
          "source_file": "cpc.pdf",
          "content": ("34. Interest.- Where and in so far as a decree is for the payment of money, the Court "
                      "may order interest at such rate as it deems reasonable.")}
# The real corpus labels a slice of the First Schedule as "s.6".
LIMITATION_SCHEDULE_AS_S6 = {
    "statute": "Limitation Act 1908", "section_number": "6", "chunk_id": "lim-0150",
    "province": "federal", "source_file": "limitation.pdf",
    "content": ("113.- For specific performance of a contract. [Three years]. The date fixed for the "
                "performance. 114.- For the rescission of a contract. [Three years]. When the facts "
                "entitling the plaintiff to have the contract rescinded first become known to him. "
                "115.- For compensation for the breach of any contract, express or implied. [Three "
                "years]. When the contract is broken.")}

CONF = '\n{"confidence": 0.8}'


class _WS:
    def __init__(self, script):
        self.script, self.sent = list(script), []

    async def accept(self):
        pass

    async def close(self, code=1000):
        self.closed = code

    async def send_json(self, payload):
        self.sent.append(payload)

    async def receive_json(self):
        if not self.script:
            raise cs.WebSocketDisconnect(1000)
        return self.script.pop(0)

    def frames(self, kind):
        return [f for f in self.sent if f.get("type") == kind]


class _Reply:
    def __init__(self, content):
        self.content = content


@pytest.fixture
def world(monkeypatch):
    w = {"intents": [], "triage": [], "triage_calls": [], "gen": [], "gen_calls": [],
         "retrieval_calls": [], "clarify_calls": 0, "chunks": [], "support": ""}

    # ── socket collaborators (as in tests/test_chat_socket.py) ──────────────
    async def ticket(t):
        return "u1"

    class _Users:
        async def find_one(self, q):
            return {"_id": "u1", "is_active": True, "role": "client"}

    async def record_outcome(**kw):
        return provenance_outbox.DURABLE, "req-1"

    async def no_lawyers(session, n=3, signals=None):
        return {"matched_lawyers": [], "result_kind": "unavailable", "notice": None}

    monkeypatch.setattr("app.core.ws_ticket.consume_ticket", ticket)
    monkeypatch.setattr(cs, "get_users_col", lambda: _Users())
    monkeypatch.setattr(cs.provenance_service, "record_outcome", record_outcome)
    monkeypatch.setattr(cs, "_fetch_matched_lawyers", no_lawyers)
    w["conversations"] = FakeConversations(
        session={"_id": "doc-s1", "session_id": "s1", "client_id": "u1", "messages": []},
        owner_field="client_id")
    monkeypatch.setattr(cs, "conversations", w["conversations"])
    monkeypatch.setattr(cs, "turns", FakeTurns())

    class _Intent:
        def __init__(self, name):
            self.intent, self.confidence, self.source, self.latency_ms = name, 0.95, "test", 1.0

    async def classify(**kw):
        return _Intent(w["intents"].pop(0))
    monkeypatch.setattr("app.ai.intent.classify", classify)
    monkeypatch.setattr(settings, "chat_adaptive_length_client", True)

    # ── model calls ─────────────────────────────────────────────────────────
    monkeypatch.setattr(gk, "llm_injection_reason", lambda q: None)

    class _Triage:
        def invoke(self, messages):
            text = messages[-1]["content"]
            w["triage_calls"].append(text)
            case_type = w["triage"].pop(0) if w["triage"] else "unknown"
            urdu = any("؀" <= ch <= "ۿ" for ch in text)
            return tn.TriageOutput(category="legal", language="ur" if urdu else "en", normalized_query=text,
                                   case_type=case_type, case_type_confidence=0.9 if case_type != "unknown" else 0.0,
                                   complexity="simple", urgency="low", province="punjab", known_facts=[],
                                   reason="test")

    class _NewQuestion:                    # triage's own follow-up detector
        def invoke(self, messages):
            return tn.FollowupIntent(intent="new", confidence=0.9)

    monkeypatch.setattr(tn, "get_structured_llm",
                        lambda schema, *a, **k: _Triage() if schema is tn.TriageOutput else _NewQuestion())

    class _Proceed:
        def invoke(self, messages):
            return _Reply("PROCEED")
    monkeypatch.setattr(fg, "get_llm", lambda **k: _Proceed())

    class _Clarify:
        def invoke(self, messages):
            w["clarify_calls"] += 1
            return _Reply("Could you describe your situation?")
    monkeypatch.setattr(cn, "get_fast_llm", lambda **k: _Clarify())

    class _Gen:
        def invoke(self, messages):
            w["gen_calls"].append(messages)
            reply = w["gen"][0] if len(w["gen"]) == 1 else w["gen"].pop(0)
            return AIMessage(content=reply + CONF)
    monkeypatch.setattr(gn, "get_llm", lambda **k: _Gen())

    class _Judge:                                    # over-trusting on purpose
        def invoke(self, messages):
            claims = messages[-1]["content"].split("Claims to assess:")[-1]
            n = sum(1 for line in claims.splitlines() if line[:1].isdigit())
            return hn.GroundingOutput(is_grounded=True, reason="ok",
                                      claim_support=",".join(f"{i}:supported" for i in range(1, n + 1)))
    monkeypatch.setattr(hn, "get_structured_llm", lambda *a, **k: _Judge())

    # ── retrieval / decision layer: fixed evidence, "answer" ────────────────
    # The exact-provision step is the REAL one (retrieval_node's own function);
    # only its corpus lookup is scripted: w["exact"] = {label: [chunks]}.
    from app.ai import exact_provision
    from app.ai.nodes.retrieval_node import apply_client_exact_provisions
    w["exact"] = {}
    monkeypatch.setattr(exact_provision, "fetch",
                        lambda cits: {exact_provision.label(c): list(w["exact"].get(exact_provision.label(c), []))
                                      for c in cits})

    async def retrieval(state):
        w["retrieval_calls"].append({"query": state.get("normalized_query") or state.get("query"),
                                     "case_type": state.get("case_type")})
        chunks, found = await apply_client_exact_provisions(state, list(w["chunks"]))
        return {"reranked_chunks": chunks, "retrieved_chunks": chunks, "requested_provisions": found,
                "case_law_chunks": [], "relevance_score": 0.9,
                "retrieval_attempts": state.get("retrieval_attempts", 0) + 1}

    async def nothing(state):
        return {}

    w["decision"] = "answer"

    def decide(state):
        return {"arbitration_output": w["decision"], "arbitration_source": "test"}

    monkeypatch.setattr(supervisor, "retrieval_node", retrieval)
    monkeypatch.setattr(supervisor, "retrieval_grader_node", nothing)
    monkeypatch.setattr(supervisor, "tool_node", nothing)
    monkeypatch.setattr(supervisor, "run_decision_engine", decide)

    monkeypatch.setattr(cache, "get_redis", lambda: None)
    cache._result_store.clear()

    w["graph"] = supervisor.build_chat_graph(checkpointer=MemorySaver())
    monkeypatch.setattr("app.ai.graph.supervisor.chat_graph", w["graph"])
    return w


def _converse(world, messages, language="en", session="s1", province="punjab"):
    if session != "s1":
        world["conversations"].sessions[session] = {"_id": f"doc-{session}", "session_id": session,
                                                    "client_id": "u1", "messages": []}
    ws = _WS([{"content": m, "language": language, "province": province,
               "client_message_id": f"{session}-m{i}"} for i, m in enumerate(messages)])
    asyncio.run(cs.chat_endpoint(ws, session, ticket="t"))
    return ws


def _state(world, session="s1"):
    snap = asyncio.run(world["graph"].aget_state({"configurable": {"thread_id": session}}))
    return snap.values


def _statuses(frame):
    return {(c.get("section"), c.get("status")) for c in frame.get("citations") or []}


# ── c26: "explain in detail" after "What is Section 506 PPC?" ────────────────

@pytest.mark.parametrize("request_text", ["explain in detail", "tafseel se batao"])
def test_c26_explain_in_detail_reanswers_506_from_the_criminal_law(world, request_text):
    world["chunks"] = [PPC_506]
    world["intents"] = ["new_query", "format_detail"]
    # Turn 1 is typed criminal. Any LATER triage call returns "unknown": the
    # live triage model did so for this exact question in 2 of 3 calls.
    world["triage"] = ["criminal"]
    world["gen"] = ["Section 506 PPC punishes criminal intimidation [1].",
                    "Section 506 PPC makes criminal intimidation an offence punishable with imprisonment "
                    "which may extend to two years, or seven years where the threat is to cause death or "
                    "grievous hurt [1]."]

    ws = _converse(world, ["What is Section 506 PPC?", request_text])

    assert ws.frames("clarification") == [] and world["clarify_calls"] == 0
    finals = ws.frames("final")
    assert len(finals) == 2
    # the follow-up re-searched the PREVIOUS question, in the criminal law,
    # with the case type the server resolved on turn 1 (no second triage call)
    assert world["retrieval_calls"][1] == {"query": "What is Section 506 PPC?", "case_type": "criminal"}
    assert len(world["triage_calls"]) == 1
    detail = finals[1]
    assert "seven years" in detail["content"], "a SUPPORTED period must survive"
    assert ("506", "matched") in _statuses(detail)
    assert not [c for c in detail["claims"] if c.get("support") == "unsupported"]
    assert _state(world)["response_mode"] == "detailed"


def test_c26_with_no_server_owned_case_type_ends_honestly_without_searching(world):
    """The record holds the earlier exchange but this worker has no usable
    checkpoint, and re-typing fails: the turn must neither ask about
    "explain in detail" nor search the civil default."""
    conv = world["conversations"]
    conv.messages += [{"role": "user", "content": "What is Section 506 PPC?", "_turn": "old", "id": "x1"},
                      {"role": "assistant", "content": "Section 506 PPC ... [1]", "_turn": "old", "id": "x2"}]
    world["chunks"] = [PPC_506]
    world["intents"] = ["format_detail"]
    world["triage"] = ["unknown"]

    ws = _converse(world, ["explain in detail"])

    assert ws.frames("clarification") == [] and world["clarify_calls"] == 0
    assert world["retrieval_calls"] == [], "an untyped follow-up must not search any collection"
    final = ws.frames("final")[0]
    assert final["content"] == tn._UNTYPED_FOLLOWUP_EN


# ── c23: the unsupported cheque deadline, and "make it short" ────────────────

C23_Q = "My business partner's cheque of 5 lakh bounced and he refuses to pay. What can I do?"
C23_ANSWER = (
    "The partner can be sued for the Rs 5 lakh within three years of the cheque’s dishonour, and the "
    "court may award interest on the amount from the date of suit to payment. [2][1]\n\n"
    "**Applicable law:**\n"
    "- Section 6 of the Limitation Act 1908 (three‑year limitation for recovery of a cheque). [2]\n"
    "- Section 34 of the Code of Civil Procedure 1908 (court may order interest on money decreed). [1]\n\n"
    "**Caution:** The suit must be instituted within three years from the date the cheque was bounced, "
    "otherwise the claim becomes time‑barred. [2]")


def _no_three_years(text):
    low = period_support.normalise(text).lower()
    return not any(p == (3, "year") for p, _ in period_support.periods_in(low))


def test_c23_unsupported_deadline_is_removed_from_answer_and_short_follow_up(world):
    world["chunks"] = [CPC_34, LIMITATION_SCHEDULE_AS_S6]
    world["intents"] = ["new_query", "format_brief"]
    world["triage"] = ["civil"]
    world["gen"] = [C23_ANSWER, C23_ANSWER,          # first answer (+ its grounding retry)
                    "You can sue to recover the cheque amount within three years [2]. "
                    "The court may also award interest on the amount under Section 34 of the "
                    "Code of Civil Procedure 1908 [1]."]

    ws = _converse(world, [C23_Q, "make it short"])

    assert ws.frames("clarification") == []
    first, short = ws.frames("final")
    for frame in (first, short):
        assert _no_three_years(frame["content"]), frame["content"]
        assert period_support.NOTICE_EN in frame["content"]
        # no claim that still asserts the period is reported as supported
        for claim in frame["claims"]:
            if not _no_three_years(claim.get("text", "")):
                assert claim["support"] == "unsupported"
    assert ("34", "matched") in _statuses(short) and "award interest" in short["content"]
    assert world["retrieval_calls"][1] == {"query": C23_Q, "case_type": "civil"}


def test_c23_urdu_short_follow_up_cannot_repeat_the_deadline(world):
    q = "میرے کاروباری شریک کا 5 لاکھ کا چیک باؤنس ہو گیا ہے اور وہ ادائیگی سے انکار کر رہا ہے۔ میں کیا کروں؟"
    world["chunks"] = [CPC_34, LIMITATION_SCHEDULE_AS_S6]
    world["intents"] = ["new_query", "format_brief"]
    world["triage"] = ["civil"]
    urdu = ("چیک باؤنس ہونے پر رقم کی وصولی کا مقدمہ تین سال میں دائر کریں [2]۔ "
            "عدالت رقم پر سود بھی دے سکتی ہے [1]۔")
    world["gen"] = [urdu, urdu, urdu]

    ws = _converse(world, [q, "مختصر بتائیں"], language="ur")

    assert ws.frames("clarification") == []
    for frame in ws.frames("final"):
        assert "تین سال" not in frame["content"]
        assert period_support.NOTICE_UR in frame["content"]
    assert world["retrieval_calls"][1]["case_type"] == "civil"


def test_a_new_question_after_a_follow_up_does_not_inherit_its_supplement(world):
    """The session thread carries state between turns: a key the socket does
    not reset survives into the next question."""
    world["chunks"] = [PPC_506]
    world["intents"] = ["new_query", "format_brief", "new_query"]
    world["triage"] = ["criminal", "criminal"]
    world["gen"] = ["Section 506 PPC punishes criminal intimidation [1]."]

    _converse(world, ["What is Section 506 PPC?", "make it short", "What is bail?"])

    values = _state(world)
    assert values.get("retrieval_query_supplement") is None
    assert values.get("followup_base_query") is None
    assert world["retrieval_calls"][-1]["query"] != "What is Section 506 PPC?"


def test_english_mflo_question_ignores_earlier_urdu_history_and_uses_section_7(world, monkeypatch):
    from app.ai import issue_lookup
    mflo7 = {
        "statute": "Muslim Family Laws Ordinance 1961", "section_number": "7",
        "chunk_id": "mflo-7", "province": "federal", "source_file": "mflo.pdf",
        "content": ("7. Talaq. A man shall give the Chairman written notice and a copy to the wife. "
                    "Talaq is effective after ninety days; the Chairman constitutes an Arbitration "
                    "Council within thirty days."),
        "issue_provision": {"statute": "Muslim Family Laws Ordinance 1961",
                            "section": "7", "heading": "Talaq"},
    }
    mflo8 = {
        "statute": "Muslim Family Laws Ordinance 1961", "section_number": "8",
        "chunk_id": "mflo-8", "province": "federal", "source_file": "mflo.pdf",
        "content": "8. Dissolution of marriage otherwise than by talaq.",
    }
    world["conversations"].messages += [
        {"role": "user", "content": "کیا آپ میری رہنمائی کر سکتے ہیں؟", "_turn": "old", "id": "u-old"},
        {"role": "assistant", "content": "جی ہاں۔", "_turn": "old", "id": "a-old"},
    ]
    monkeypatch.setattr(issue_lookup, "fetch_governing", lambda *a, **k: [mflo7])
    world["chunks"] = [mflo8]
    world["intents"] = ["new_query"]
    world["triage"] = ["family"]
    world["gen"] = [("Section 7 requires written notice to the Chairman and a copy to the wife; "
                     "the talaq takes effect after ninety days [1].")]
    question = ("Under the Muslim Family Laws Ordinance 1961, what is the procedure and "
                "timeline for a husband sending a divorce notice in Pakistan?")

    frame = _only_frame(_converse(world, [question]))

    assert "Section 7" in frame["content"] and "ninety days" in frame["content"]
    system = world["gen_calls"][0][0]["content"]
    prompt = world["gen_calls"][0][1]["content"]
    assert "Section 7" in system and "governs this issue" in system
    assert "Answer only in English" in system
    assert prompt.index("7. Talaq") < prompt.index("8. Dissolution")


def test_english_turn_keeps_its_answer_when_translation_fails_but_does_not_cache_urdu(world):
    world["chunks"] = [{"statute": "Muslim Family Laws Ordinance 1961", "section_number": "7",
                        "chunk_id": "mflo7", "province": "federal", "source_file": "mflo.pdf",
                        "content": "7. Talaq. Any man wishing to divorce his wife must give written notice to the Chairman."}]
    world["intents"] = ["new_query"]
    world["triage"] = ["family"]
    # The model ignores the translation request too. The user still receives
    # the answer, but a later English user must not receive this Urdu cache entry.
    world["gen"] = ["شوہر کو چیئرمین کے پاس تحریری نوٹس بھیجنا ہوگا [1]."]

    ws = _converse(world, ["What notice must a husband send for talaq under the Muslim Family Laws Ordinance 1961?"])

    assert ws.frames("final") and "نوٹس" in ws.frames("final")[0]["content"]
    assert _state(world)["language_mismatch"] is True
    assert not cache._result_store


# ── 2026-10-14 release blockers, on the FINAL socket frame ───────────────────

C19 = "My husband beats me every day and threatened to kill me tonight. What should I do?"
C19_ROMAN = "koi mujhe abhi jaan se maarne ki dhamki de raha hai, main kya karun?"
C19_URDU = "میرا شوہر مجھے روز مارتا ہے اور آج رات جان سے مارنے کی دھمکی دی ہے۔ میں کیا کروں؟"
PWAVA = {"statute": "Punjab Protection of Women against Violence Act 2016", "section_number": "7",
         "chunk_id": "pwava-7", "province": "punjab", "source_file": "pwava.pdf",
         "content": "7. Protection order.- The Court may pass a protection order directing the defendant not to "
                    "commit violence against the aggrieved person."}
SAFETY_EN = "**If you are in danger right now"


def _frame_text(frame):
    return frame.get("content") or frame.get("question") or ""


def _only_frame(ws):
    frames = ws.frames("final") + ws.frames("clarification") + ws.frames("error")
    assert len(frames) == 1
    return frames[0]


@pytest.mark.parametrize("flag", [True, False])
def test_c19_decision_engine_refusal_still_carries_safety_guidance(world, monkeypatch, flag):
    monkeypatch.setattr(settings, "chat_adaptive_length_client", flag)
    world["chunks"] = [PWAVA]
    world["intents"] = ["new_query"]
    world["triage"] = ["criminal"]
    world["decision"] = "refuse"                      # the live c19 exit
    text = _frame_text(_only_frame(_converse(world, [C19])))
    assert text.startswith(SAFETY_EN)
    assert "(15)" in text and "Rescue 1122" in text
    assert "I was unable to provide a reliable answer" in text, "the refusal is kept, not hidden"


def test_c19_normal_answer_carries_it_too(world):
    world["chunks"] = [PWAVA]
    world["intents"] = ["new_query"]
    world["triage"] = ["criminal"]
    world["gen"] = ["You can apply for a protection order under Section 7 of the Punjab Protection of "
                    "Women against Violence Act 2016 [1]."]
    text = _frame_text(_only_frame(_converse(world, [C19])))
    assert text.startswith(SAFETY_EN) and "protection order" in text


def test_c19_clarification_exit_carries_it(world, monkeypatch):
    world["chunks"] = [PWAVA]
    world["intents"] = ["new_query"]
    world["triage"] = ["criminal"]

    class _AsksAQuestion:                             # fact-gap interrupts
        def invoke(self, messages):
            return _Reply("Are you somewhere safe right now?")
    monkeypatch.setattr(fg, "get_llm", lambda **k: _AsksAQuestion())
    ws = _converse(world, [C19])
    question = ws.frames("clarification")[0]["question"]
    assert question.startswith(SAFETY_EN) and question.endswith("Are you somewhere safe right now?")


def test_c19_provider_fault_exit_carries_it(world, monkeypatch):
    world["chunks"] = [PWAVA]
    world["intents"] = ["new_query"]
    world["triage"] = ["criminal"]

    class _Boom:
        def invoke(self, messages):
            raise RuntimeError("provider down")
    monkeypatch.setattr(gn, "get_llm", lambda **k: _Boom())
    frame = _only_frame(_converse(world, [C19]))
    assert frame["type"] == "error" and frame["content"].startswith(SAFETY_EN)


def test_c19_cache_hit_exit_carries_it(world, monkeypatch):
    """A personal message is normally NOT cached (cache_block_reason:
    personalised). The block is bypassed here to prove that, if a cached
    answer is ever served for a danger message, the socket still adds the
    guidance -- it is applied after the graph, on every exit."""
    from app.ai.nodes import cache_node, finalizer_node
    monkeypatch.setattr(cache_node, "cache_block_reason", lambda state: None)
    monkeypatch.setattr(finalizer_node, "cache_block_reason", lambda state: None)
    world["chunks"] = [PWAVA]
    world["intents"] = ["new_query", "new_query"]
    world["triage"] = ["criminal", "criminal"]
    world["gen"] = ["You can apply for a protection order under Section 7 of the Punjab Protection of "
                    "Women against Violence Act 2016 [1]."]
    _converse(world, [C19])
    ws2 = _converse(world, [C19], session="s2")       # a new conversation: served from cache
    assert _state(world, "s2").get("cache_hit") is True
    assert _frame_text(_only_frame(ws2)).startswith(SAFETY_EN)


@pytest.mark.parametrize("text,language,header", [
    (C19_ROMAN, "en", "**Agar aap abhi khatre mein hain"),
    (C19_URDU, "ur", "**اگر آپ ابھی خطرے میں ہیں"),
])
def test_c19_guidance_in_urdu_and_roman_urdu(world, text, language, header):
    world["chunks"] = [PWAVA]
    world["intents"] = ["new_query"]
    world["triage"] = ["criminal"]
    world["decision"] = "refuse"
    assert _frame_text(_only_frame(_converse(world, [text], language=language))).startswith(header)


def test_c19_numbers_are_withheld_outside_punjab(world):
    world["chunks"] = [PWAVA]
    world["intents"] = ["new_query"]
    world["triage"] = ["criminal"]
    world["decision"] = "refuse"
    text = _frame_text(_only_frame(_converse(world, [C19], province="sindh")))
    assert text.startswith(SAFETY_EN) and "15" not in text and "1122" not in text


def test_an_ordinary_question_gets_no_emergency_message(world):
    world["chunks"] = [PPC_506]
    world["intents"] = ["new_query"]
    world["triage"] = ["criminal"]
    world["gen"] = ["Section 506 PPC punishes criminal intimidation [1]."]
    text = _frame_text(_only_frame(_converse(world, ["What is Section 506 PPC?"])))
    assert "danger" not in text.lower() and "(15)" not in text


# c01: "What is Section 489-F PPC?" ----------------------------------------------

PPC_489F_CHUNK = {"statute": "PPC 1860", "section_number": "489F", "chunk_id": "statutes_ppc_1860_0760",
                  "province": "federal", "source_file": "ppc.pdf", "exact_provision": "Section 489-F PPC",
                  "content": "489- F.  Dishonestly issuing a cheque:  Whoever dishonestly issues a cheque towards "
                             "repayment of a loan or fulfilment of an obligation which is dishonoured on "
                             "presentation, shall be punishable with imprisonment which may extend to three "
                             "years, or with fine, or with both"}
CRPC_345_ROW = {"statute": "CrPC 1898", "section_number": "345", "chunk_id": "statutes_crpc_1898_0928",
                "province": "federal", "source_file": "crpc.pdf",
                "content": "Dishonestly issuing a cheque. 489-F The person in whose favour the cheque is issued."}
WRONG_489F = ("Section 489‑F of the Pakistan Penal Code defines “the person in whose favour a cheque is "
              "issued.” It is a definitional clause used to identify the payee [1].")


@pytest.mark.parametrize("flag", [True, False])
def test_c01_answer_rests_on_the_exact_489f_text(world, monkeypatch, flag):
    monkeypatch.setattr(settings, "chat_adaptive_length_client", flag)
    world["chunks"] = [CRPC_345_ROW]                  # what similarity search found live
    world["exact"] = {"Section 489-F PPC": [PPC_489F_CHUNK]}
    world["intents"] = ["new_query"]
    world["triage"] = ["criminal"]
    # Written with a NON-BREAKING hyphen (U+2011), as the live model did: it
    # used to parse as section "489" and show the right citation unresolved.
    world["gen"] = ["Section 489‑F PPC makes it an offence to dishonestly issue a cheque towards repayment of "
                    "a loan or fulfilment of an obligation that is dishonoured on presentation [1]."]
    frame = _only_frame(_converse(world, ["What is Section 489-F PPC?"]))
    assert ("489", "unresolved") not in _statuses(frame)
    assert ("489-F", "matched") in _statuses(frame)
    system, user = world["gen_calls"][0][0]["content"], world["gen_calls"][0][1]["content"]
    assert "Its own text is the FIRST source" in system
    assert user.index("Dishonestly issuing a cheque:") < user.index("The person in whose favour")
    assert "couldn't find" not in frame["content"]


@pytest.mark.parametrize("flag", [True, False])
def test_c01_without_the_489f_text_it_says_so_instead_of_defining_it(world, monkeypatch, flag):
    monkeypatch.setattr(settings, "chat_adaptive_length_client", flag)
    world["chunks"] = [CRPC_345_ROW]
    world["exact"] = {}                               # not in the corpus
    world["intents"] = ["new_query"]
    world["triage"] = ["criminal"]
    world["gen"] = [WRONG_489F]                       # the live confident wrong answer
    frame = _only_frame(_converse(world, ["What is Section 489-F PPC?"]))
    assert "definitional" not in frame["content"]
    assert frame["content"].startswith("I couldn't find the text of Section 489-F PPC")
    assert "is NOT among the sources" in world["gen_calls"][0][0]["content"]
    assert not [c for c in frame["claims"] if "489" in c.get("text", "") and c.get("support") == "supported"
                and not c.get("removed_from_answer")]


# flag OFF: the follow-up and deadline fixes do not depend on the length policy -----

def test_c26_flag_off_explain_in_detail_still_reanswers_without_clarification(world, monkeypatch):
    monkeypatch.setattr(settings, "chat_adaptive_length_client", False)
    world["chunks"] = [PPC_506]
    world["intents"] = ["new_query", "format_detail"]
    world["triage"] = ["criminal"]
    world["gen"] = ["Section 506 PPC punishes criminal intimidation [1].",
                    "Section 506 PPC makes criminal intimidation punishable with imprisonment which may extend "
                    "to two years [1]."]
    ws = _converse(world, ["What is Section 506 PPC?", "explain in detail"])
    assert ws.frames("clarification") == [] and len(ws.frames("final")) == 2
    assert world["retrieval_calls"][1] == {"query": "What is Section 506 PPC?", "case_type": "criminal"}
    assert _state(world)["response_mode"] == "legacy"


def test_c23_flag_off_deadline_is_still_removed(world, monkeypatch):
    monkeypatch.setattr(settings, "chat_adaptive_length_client", False)
    world["chunks"] = [CPC_34, LIMITATION_SCHEDULE_AS_S6]
    world["intents"] = ["new_query", "format_brief"]
    world["triage"] = ["civil"]
    world["gen"] = [C23_ANSWER, C23_ANSWER, "You can sue to recover the cheque amount within three years [2]."]
    ws = _converse(world, [C23_Q, "make it short"])
    for frame in ws.frames("final"):
        assert _no_three_years(frame["content"])
