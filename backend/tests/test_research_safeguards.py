"""Lawyer research answer safeguards (ai/answer_safeguards.py, 2026-10-14).

Unit tests for each guard, then ROUTE-LEVEL tests: the real `ai_research`
handler (real case authorization over stubbed repositories, fake conversation
and turn stores), the REAL compiled chat graph with an in-memory checkpointer,
and the real triage / fact-gap / generation / judge / finalizer nodes. Only
model calls and the retrieval / decision / tool layer are scripted.

Regressions for the live probe (evals/chat_length/results/research_probe_*):
R1 489-F from schedule rows, R2 Article 58 limitation, R3 irrelevant Land
Revenue Act + "CPC Section 17", R3.2 "make it short" -> clarification citing
Indian s.138, R6 Urdu citations without chips.
"""
from __future__ import annotations

import asyncio

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver

import app.api.v1.routes.ai as ai_routes
from app.ai import answer_safeguards as S
from app.ai import cache, issue_relevance, jurisdiction_guard, period_support, research_followup
from app.ai.answer_citations import extract_citations
from app.core.config import settings
from app.services import provenance_outbox

LAWYER = {"_id": "lawyer-A", "role": "lawyer"}


# ── unit: which safeguards apply ─────────────────────────────────────────────

@pytest.mark.parametrize("surface,flag,on,research", [
    ("client", False, True, False), ("client", True, True, False),
    ("research", False, False, False), ("research", True, True, True),
    (None, True, False, False), ("lawyer", True, False, False),
])
def test_safeguards_by_surface_and_flag(monkeypatch, surface, flag, on, research):
    monkeypatch.setattr(settings, "research_answer_safeguards", flag)
    st = {"surface": surface}
    assert S.on(st) is on and S.research_on(st) is research


def test_research_cache_identity_follows_the_flag(monkeypatch):
    from app.ai import response_policy as R
    st = {"query": "What is 302 PPC?", "surface": "research", "complexity": "simple"}
    monkeypatch.setattr(settings, "research_answer_safeguards", False)
    assert R.cache_variant(st) == R.LEGACY                       # rollback: exactly as before
    monkeypatch.setattr(settings, "research_answer_safeguards", True)
    assert R.cache_variant(st) == f"{R.LEGACY}|research|{S.RESEARCH_GUARD_VERSION}"
    assert R.cache_variant({**st, "surface": None}) == R.LEGACY  # other callers untouched


@pytest.mark.parametrize("urdu,expected", [
    ("پی پی سی دفعہ 302 — قتلِ عمد [1]", ("PPC", "302")),
    ("تعزیرات پاکستان کی دفعہ ۳۰۲ کے تحت", ("PPC", "302")),
    ("ضابطہ فوجداری کی دفعہ 497 کے تحت ضمانت", ("CRPC", "497")),
    ("دفعہ 489-ایف پی پی سی", ("PPC", "489-F")),
])
def test_urdu_citations_resolve_to_the_same_authority_as_english(urdu, expected):
    assert [c.key for c in extract_citations(S.urdu_citation_forms(urdu))] == [expected]


def test_a_bare_urdu_section_number_without_its_act_resolves_to_nothing():
    assert extract_citations(S.urdu_citation_forms("دفعہ 302 کی سزا کیا ہے")) == []


def test_client_citation_text_is_exactly_the_previous_normalisation(monkeypatch):
    monkeypatch.setattr(settings, "research_answer_safeguards", True)
    t = "Section 489‑F — پی پی سی دفعہ 302"
    assert S.citation_text(t, {"surface": "client"}) == period_support.normalise(t)
    assert S.citation_text(t, {"surface": None}) == t


# ── unit: issue relevance (R3) ───────────────────────────────────────────────

LAND_REVENUE_91 = {"id": "8", "kind": "statute", "statute": "Punjab Land Revenue Act 1967", "section": "91",
                   "content": "91. Remedy when liability for an arrear is denied.- If any person paying an arrear of "
                              "land revenue under protest institutes a suit for recovery of the amount so paid..."}
PPC_489F = {"id": "1", "kind": "statute", "statute": "PPC 1860", "section": "489F",
            "content": "489- F.  Dishonestly issuing a cheque:  Whoever dishonestly issues a cheque towards repayment "
                       "of a loan or fulfilment of an obligation which is dishonoured on presentation, shall be "
                       "punishable with imprisonment which may extend to three years"}
TPA_54 = {"id": "2", "kind": "statute", "statute": "Transfer of Property Act 1882", "section": "54",
          "content": "54. Sale defined.- Sale is a transfer of ownership in exchange for a price paid or promised."}


def _claim(text, ids, support="supported"):
    return {"index": 1, "text": text, "source_ids": ids, "citation_status": "matched", "support": support}


def test_r3_an_irrelevant_but_matched_source_is_not_supported():
    q = "My client's business partner gave him a cheque of 5 lakh which bounced. What remedies does he have?"
    claims = issue_relevance.downgrade(
        [_claim("Section 91 of the Punjab Land Revenue Act lets him recover the amount [8].", ["8"])],
        [LAND_REVENUE_91], q)
    assert claims[0]["support"] == "unassessed" and "relevance" in claims[0]["support_reason"]


@pytest.mark.parametrize("question,source", [
    ("My tenant has not paid rent for six months; how do I evict him?", LAND_REVENUE_91),
    ("My brother was arrested for theft; can he get bail?", TPA_54),
])
def test_relevance_is_not_specific_to_the_cheque_example(question, source):
    claims = issue_relevance.downgrade([_claim("It applies here [x].", [source["id"]])], [source], question)
    assert claims[0]["support"] == "unassessed"


def test_a_relevant_source_keeps_its_verdict():
    q = "My client's partner's cheque bounced; what offence is it?"
    claims = issue_relevance.downgrade([_claim("It is an offence under 489-F [1].", ["1"])], [PPC_489F], q)
    assert claims[0]["support"] == "supported"


def test_a_question_without_subject_terms_downgrades_nothing():
    claims = issue_relevance.downgrade([_claim("x [8].", ["8"])], [LAND_REVENUE_91], "What is Section 91?")
    assert claims[0]["support"] == "supported"


# ── unit: foreign law (R3.2) ─────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "Has he served a notice (e.g., a criminal complaint under Section 138 of the Negotiable Instruments Act)?",
    "He can also complain under Section 420 IPC. Recovery is by a civil suit.",
    "As held by the Supreme Court of India, the drawer is liable. Recovery is by a civil suit.",
])
def test_indian_law_is_removed_from_a_pakistani_answer(text):
    out, removed = jurisdiction_guard.strip_foreign(text, "My client's cheque bounced; what can he do?")
    assert removed and not jurisdiction_guard.markers_in(out.replace(jurisdiction_guard.NOTE_EN, ""))
    assert jurisdiction_guard.NOTE_EN in out


def test_pakistani_text_that_mentions_historic_indian_acts_is_kept():
    t = "Substituted by the Indian Limitation (Amendment) Act, 1922 in the Limitation Act 1908."
    assert jurisdiction_guard.strip_foreign(t, "limitation for a debt?") == (t, [])


def test_a_comparative_question_keeps_foreign_law():
    t = "India punishes cheque dishonour under Section 138 of the Negotiable Instruments Act."
    assert jurisdiction_guard.strip_foreign(t, "How does India compare with Pakistan?")[1] == []


# ── unit: research follow-ups ────────────────────────────────────────────────

@pytest.mark.parametrize("message,kind", [
    ("make it short", "format_brief"), ("mukhtasar mein batao", "format_brief"), ("مختصر بتائیں", "format_brief"),
    ("explain in detail", "format_detail"), ("tafseel se batao", "format_detail"), ("تفصیل سے بتائیں", "format_detail"),
    ("explain bail in detail", None), ("make it short and add the limitation period", None), ("Is bail available?", None),
])
def test_presentation_requests_are_recognised_only_when_they_name_no_subject(message, kind):
    assert research_followup.presentation_intent(message) == kind


def test_a_follow_up_reanswers_the_previous_question_with_its_case_terms():
    history = [{"role": "user", "content": "What can my client do about the bounced cheque?"},
               {"role": "assistant", "content": "Under 489-F PPC ... [1]"}]
    prev = {"query": "What can my client do about the bounced cheque?", "case_type": "criminal",
            "case_type_confidence": 0.9}
    case = {"title": "State v. Partner", "description": "cheque of Rs 5 lakh dishonoured"}
    out = research_followup.overrides("make it short", history, prev, "unknown", case)
    assert out["followup_intent"] == "format" and out["followup_base_query"] == history[0]["content"]
    assert out["case_type"] == "criminal"
    assert out["retrieval_query_supplement"].startswith(history[0]["content"])


# ── unit: identity index plan (scripts/build_ident_index.py) ─────────────────

def _cpc(n, text, sec=""):
    return (f"id{n}", text, {"statute": "CPC 1908", "chunk_id": f"statutes_cpc_1908_{n:04d}", "section_number": sec})


def test_order_and_rule_identities_are_planned_from_heading_and_sequence():
    import sys
    sys.path.insert(0, "scripts")
    import build_ident_index as B
    rows = [_cpc(1, "158. Repeal. ...\nTHE FIRST SCHEDULE\nORDER I\nPARTIES TO SUITS", "158"),
            _cpc(2, "1. Who may be joined as plaintiffs.- All persons ...", "1"),
            _cpc(3, "ends Order I.\nORDER II\nFrame of Suit", "1"),
            _cpc(4, "1. Frame of suit._ Every suit shall ...", "1"),
            _cpc(5, "text continues without a heading ...", "2"),
            _cpc(6, "ORDER V\nIssue and service of summons", ""),       # II -> V: not consecutive
            _cpc(7, "1. Summons._ When a suit has been ...", "1")]
    plan = B.plan_identities(rows)
    assert plan["id2"]["provision_label"] == "Order I Rule 1" and plan["id2"]["section_number"] == ""
    assert plan["id4"]["provision_label"] == "Order II (rule not shown)" or \
        plan["id4"]["provision_label"].startswith("CPC First Schedule")   # II -> V gap: never guessed
    assert plan["id1"]["provision_kind"] == "section"                       # opens in section text


def test_limitation_articles_come_from_the_chunks_own_entry_headers():
    import sys
    sys.path.insert(0, "scripts")
    import build_ident_index as B
    lim = lambda n, t, s="": (f"l{n}", t, {"statute": "Limitation Act 1908",
                                           "chunk_id": f"statutes_limitation_act_1908_{n:04d}", "section_number": s})
    rows = [lim(1, "THE FIRST SCHEDULE (See section 3.) First Division: Suits. Description of suit.", "5"),
            lim(2, "57.- For money payable for money lent. [Three years]. 58.- Like suit when the lender has "
                   "given a cheque for the money. [Three years].", "6"),
            lim(3, "the plaintiff has notice. [Three years]. When the contract is broken.", "6")]
    plan = B.plan_identities(rows)
    assert plan["l2"]["provision_label"] == "First Schedule, Articles 57–58" and plan["l2"]["section_number"] == ""
    assert plan["l3"]["provision_label"] == "First Schedule (article not shown)"


def test_the_research_index_variant_maps_per_collection(monkeypatch):
    from app.ai.pipelines import retriever

    class _C:
        def get_collection(self, name):
            return object()
    monkeypatch.setattr(retriever, "get_chroma", lambda: _C())
    # The mapping only; whether the index is the verified build is
    # tests/test_identity_index_safety.py's job.
    from app.ai import index_health
    monkeypatch.setattr(index_health, "require", lambda name, client=None: name)
    assert retriever._index_collection("civil_collection", "research_ident") == "civil_collection__ident_v2"   # switched 2026-10-15 after the pre-registered gate passed
    assert retriever._index_collection("criminal_collection", "research_ident") == "criminal_collection__sec_v2"
    assert retriever._index_collection("family_collection", "research_ident") == "family_collection"


# ── route level: real ai_research + real graph ───────────────────────────────

LIM_ART_58 = {"statute": "Limitation Act 1908", "section_number": "", "chunk_id": "lim-0128",
              "province": "federal", "source_file": "limitation.pdf",
              "provision_kind": "schedule_article", "provision_label": "First Schedule, Articles 57–59",
              "content": "57.- For money payable for money lent. 4 [Three years]. When the loan is made. "
                         "58.- Like suit when the lender has given a cheque for the money. 5 [Three years]. "
                         "When the cheque is paid. 59.- For money lent under an agreement that it shall be "
                         "payable on demand. 6 [Three years]. When the loan is made."}
PPC_489F_CHUNK = {"statute": "PPC 1860", "section_number": "489F", "chunk_id": "statutes_ppc_1860_0760",
                  "province": "federal", "source_file": "ppc.pdf", "content": PPC_489F["content"]}
CRPC_345_ROW = {"statute": "CrPC 1898", "section_number": "345", "chunk_id": "statutes_crpc_1898_0928",
                "province": "federal", "source_file": "crpc.pdf",
                "content": "Dishonestly issuing a cheque. 489-F The person in whose favour the cheque is issued."}
PPC_302 = {"statute": "PPC 1860", "section_number": "302", "chunk_id": "statutes_ppc_1860_0439",
           "province": "federal", "source_file": "ppc.pdf",
           "content": "302. Punishment of qatl-i-amd:  Whoever commits qatl-e-amd shall be punished with death as "
                      "qisas, or with death or imprisonment for life as ta'zir, or imprisonment which may extend "
                      "to twenty-five years where qisas is not applicable."}
LRA_91_CHUNK = {"statute": "Punjab Land Revenue Act 1967", "section_number": "91", "chunk_id": "plra-91",
                "province": "punjab", "source_file": "plra.pdf", "content": LAND_REVENUE_91["content"]}
CONF = '\n{"confidence": 0.8}'


class _Body:
    def __init__(self, message, session_id="rs1", language="en", case_id=None):
        self.message, self.session_id, self.language = message, session_id, language
        self.province, self.history, self.case_id, self.client_message_id = "punjab", [], case_id, None


@pytest.fixture
def research(monkeypatch):
    from app.ai.graph import supervisor
    from app.ai.nodes import clarification_node as cn
    from app.ai.nodes import fact_gap_node as fg
    from app.ai.nodes import gatekeeper_node as gk
    from app.ai.nodes import generation_node as gn
    from app.ai.nodes import hallucination_node as hn
    from app.ai.nodes import triage_node as tn
    from app.ai import exact_provision
    from app.ai.nodes.retrieval_node import apply_client_exact_provisions
    from tests import _conversation_fakes as fakes

    w = {"triage": [], "gen": [], "gen_calls": [], "retrieval_calls": [], "chunks": [], "exact": {},
         "records": [], "clarify": 0, "fetch_research": []}
    conv, turns = fakes.install(monkeypatch, ai_routes)

    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(turns, "record_stage", _noop, raising=False)

    async def record_outcome(**kw):
        w["records"].append(kw)
        return provenance_outbox.DURABLE, "req-1"
    monkeypatch.setattr(ai_routes.provenance_service, "record_outcome", record_outcome)

    monkeypatch.setattr(gk, "llm_injection_reason", lambda q: None)

    class _Triage:
        def invoke(self, messages):
            text = messages[-1]["content"]
            ct = w["triage"].pop(0) if w["triage"] else "unknown"
            urdu = any("؀" <= ch <= "ۿ" for ch in text)
            return tn.TriageOutput(category="legal", language="ur" if urdu else "en", normalized_query=text,
                                   case_type=ct, case_type_confidence=0.9 if ct != "unknown" else 0.0,
                                   complexity="simple", urgency="low", province="punjab", known_facts=[],
                                   reason="t")

    class _New:
        def invoke(self, messages):
            return tn.FollowupIntent(intent="new", confidence=0.9)
    monkeypatch.setattr(tn, "get_structured_llm",
                        lambda schema, *a, **k: _Triage() if schema is tn.TriageOutput else _New())

    class _Reply:
        def __init__(self, c):
            self.content = c

    class _Proceed:
        def invoke(self, m):
            return _Reply("PROCEED")
    monkeypatch.setattr(fg, "get_llm", lambda **k: _Proceed())

    class _Clarify:
        def invoke(self, m):
            w["clarify"] += 1
            return _Reply("Has your client served a notice (or a complaint under Section 138 of the "
                          "Negotiable Instruments Act)?")
    monkeypatch.setattr(cn, "get_fast_llm", lambda **k: _Clarify())

    class _Gen:
        def invoke(self, messages):
            w["gen_calls"].append(messages)
            reply = w["gen"][0] if len(w["gen"]) == 1 else w["gen"].pop(0)
            return AIMessage(content=reply + CONF)
    monkeypatch.setattr(gn, "get_llm", lambda **k: _Gen())

    class _Judge:                                              # over-trusting on purpose
        def invoke(self, messages):
            claims = messages[-1]["content"].split("Claims to assess:")[-1]
            n = sum(1 for line in claims.splitlines() if line[:1].isdigit())
            return hn.GroundingOutput(is_grounded=True, reason="ok",
                                      claim_support=",".join(f"{i}:supported" for i in range(1, n + 1)))
    monkeypatch.setattr(hn, "get_structured_llm", lambda *a, **k: _Judge())

    def fetch(cits, research=False):
        w["fetch_research"].append(research)
        return {exact_provision.label(c): list(w["exact"].get(exact_provision.label(c), [])) for c in cits}
    monkeypatch.setattr(exact_provision, "fetch", fetch)

    async def retrieval(state):
        w["retrieval_calls"].append({"query": state.get("normalized_query") or state.get("query"),
                                     "case_type": state.get("case_type"),
                                     "policy": dict(state.get("retrieval_policy") or {}),
                                     "supplement": state.get("retrieval_query_supplement")})
        chunks, found = await apply_client_exact_provisions(state, list(w["chunks"]))
        return {"reranked_chunks": chunks, "retrieved_chunks": chunks, "requested_provisions": found,
                "case_law_chunks": [], "relevance_score": 0.9,
                "retrieval_attempts": state.get("retrieval_attempts", 0) + 1}

    async def nothing(state):
        return {}
    monkeypatch.setattr(supervisor, "retrieval_node", retrieval)
    monkeypatch.setattr(supervisor, "retrieval_grader_node", nothing)
    monkeypatch.setattr(supervisor, "tool_node", nothing)
    monkeypatch.setattr(supervisor, "run_decision_engine",
                        lambda s: {"arbitration_output": "answer", "arbitration_source": "test"})
    monkeypatch.setattr(cache, "get_redis", lambda: None)
    cache._result_store.clear()
    w["graph"] = supervisor.build_chat_graph(checkpointer=MemorySaver())
    monkeypatch.setattr("app.ai.graph.supervisor.chat_graph", w["graph"])
    monkeypatch.setattr(settings, "research_answer_safeguards", True)
    w["conv"] = conv
    return w


def ask(message, session="rs1", language="en", case_id=None):
    return asyncio.run(ai_routes.ai_research(_Body(message, session, language, case_id), current_user=LAWYER))


def _statuses(resp):
    return {(c.get("section"), c.get("status")) for c in resp.get("citations") or []}


R2_ANSWER = ("**Applicable Law:**\n- Limitation Act 1908 Section 6 — limitation for suits on cheques (three years) [1]\n"
             "**Legal Analysis:** Under Article 58, a suit to recover a dishonoured cheque must be filed within "
             "three years of the date the cheque was presented [1].\n**Conclusion:** File the suit promptly.")


def test_r2_wrong_article_limitation_is_withheld_and_never_supported(research):
    research["chunks"] = [LIM_ART_58]
    research["triage"] = ["civil"]
    research["gen"] = [R2_ANSWER]
    resp = ask("What is the limitation period for filing a suit on a dishonoured cheque?")
    assert resp["type"] == "final"
    assert not any(p == (3, "year") for p, _ in period_support.periods_in(resp["answer"]))
    assert period_support.RESEARCH_NOTICE_EN in resp["answer"]
    for c in resp["claims"]:
        if any(p == (3, "year") for p, _ in period_support.periods_in(c.get("text", ""))):
            assert c["support"] == "unsupported"
    # The literal, not the module constant: a test comparing the route with the
    # same constant it reads passes whatever that constant becomes.
    assert research["retrieval_calls"][0]["policy"].get("index_variant") == "research_ident"


def test_r2_flag_off_is_rollback_not_a_safety_claim(research, monkeypatch):
    """Off, research behaves exactly as before -- including the unsafe period."""
    monkeypatch.setattr(settings, "research_answer_safeguards", False)
    research["chunks"] = [LIM_ART_58]
    research["triage"] = ["civil"]
    research["gen"] = [R2_ANSWER]
    resp = ask("What is the limitation period for filing a suit on a dishonoured cheque?")
    assert "three years" in resp["answer"]
    assert research["retrieval_calls"][0]["policy"] == {}


def test_r1_a_named_provision_is_answered_from_its_own_text(research):
    research["chunks"] = [CRPC_345_ROW]
    research["exact"] = {"Section 489-F PPC": [{**PPC_489F_CHUNK, "exact_provision": "Section 489-F PPC"}]}
    research["triage"] = ["criminal"]
    research["gen"] = ["Section 489‑F PPC makes it an offence to dishonestly issue a cheque that is dishonoured on "
                       "presentation, punishable with imprisonment which may extend to three years [1]."]
    resp = ask("What is Section 489-F PPC?")
    assert ("489-F", "matched") in _statuses(resp)
    assert research["fetch_research"] == [True]
    assert "Its own text is the FIRST source" in research["gen_calls"][0][0]["content"]


def test_r1_without_its_text_a_schedule_row_is_not_passed_off_as_the_section(research):
    research["chunks"] = [CRPC_345_ROW]
    research["triage"] = ["criminal"]
    research["gen"] = ["Section 489-F of the PPC defines the person in whose favour a cheque is issued [1]."]
    resp = ask("What is Section 489-F PPC?")
    assert resp["answer"].startswith("I couldn't find the text of Section 489-F PPC")
    assert not [c for c in resp["claims"] if "489" in c.get("text", "") and c.get("support") == "supported"
                and not c.get("removed_from_answer")]


def test_r3_an_irrelevant_provision_is_not_shown_as_supported(research):
    research["chunks"] = [LRA_91_CHUNK]
    research["triage"] = ["civil"]
    research["gen"] = ["If the partner denies liability, Section 91 of the Punjab Land Revenue Act 1967 allows "
                       "a suit for recovery of the amount [1]."]
    resp = ask("My client's business partner gave him a cheque of 5 lakh which bounced. What remedies does he have?")
    lra = [c for c in resp["claims"] if "Land Revenue" in c.get("text", "")]
    assert lra and all(c["support"] == "unassessed" for c in lra)


def test_r3_2_make_it_short_reanswers_and_carries_no_indian_law(research):
    research["chunks"] = [PPC_489F_CHUNK]
    research["triage"] = ["criminal"]
    research["gen"] = ["Under Section 489-F PPC the drawer commits an offence punishable up to three years [1].",
                       "Briefly: it is an offence under Section 489-F PPC [1]. He may also complain under Section "
                       "138 of the Negotiable Instruments Act."]
    first_q = "My client's business partner's cheque bounced. What remedies does he have?"
    ask(first_q)
    resp = ask("make it short")
    assert resp["type"] == "final" and research["clarify"] == 0
    assert research["retrieval_calls"][-1]["query"] == first_q
    assert not jurisdiction_guard.markers_in(resp["answer"].replace(jurisdiction_guard.NOTE_EN, ""))
    assert "SHORTER version of the analysis" in research["gen_calls"][-1][0]["content"]


def test_r3_2_a_clarifying_question_carries_no_indian_law(research):
    research["chunks"] = [PPC_489F_CHUNK]
    research["triage"] = ["unknown"]                       # routing asks a question
    resp = ask("My client was given a cheque that bounced")
    assert resp["type"] == "clarification" and research["clarify"] == 1
    assert not jurisdiction_guard.markers_in(resp["question"].replace(jurisdiction_guard.NOTE_EN, ""))


def test_r6_urdu_citations_get_chips(research):
    research["chunks"] = [PPC_302]
    research["triage"] = ["criminal"]
    research["gen"] = ["پی پی سی دفعہ 302 کے تحت قتلِ عمد کی سزا موت ہے [1]۔ دفعہ 999 کا ذکر بغیر قانون کے ہے۔"]
    resp = ask("دفعہ 302 تعزیرات پاکستان کی سزا کیا ہے؟", language="ur")
    assert ("302", "matched") in _statuses(resp)
    assert not [c for c in resp["citations"] if c.get("section") == "999"]
    assert any("دفعہ 302" in c.get("text", "") for c in resp["claims"]), "claims keep the original Urdu wording"


def test_the_surface_is_set_by_the_route_and_the_case_version_reaches_provenance(research, monkeypatch):
    from app.services import case_service
    case = {"_id": "case-9", "case_number": "CR-1", "title": "State v. Partner", "case_type": "criminal",
            "province": "punjab", "status": "open", "description": "cheque dishonoured",
            "client_id": "client-1", "lawyer_id": "lawyer-A", "updated_at": "2026-10-10T10:00:00+00:00"}

    async def find_by_id(cid):
        return case if cid == "case-9" else None

    async def find_user(uid):
        return {"_id": uid, "full_name": "X", "email": "x@example.com"}
    monkeypatch.setattr(case_service.case_repo, "find_by_id", find_by_id)
    monkeypatch.setattr(case_service.user_repo, "find_by_id", find_user)
    research["chunks"] = [PPC_489F_CHUNK]
    research["triage"] = ["criminal"]
    research["gen"] = ["Under Section 489-F PPC it is an offence [1]."]
    ask("What offence is committed?", session="rs-case", case_id="case-9")
    state = research["records"][-1]["state"]
    assert state["surface"] == "research"
    assert state.get("case_record_version"), "an ordinary turn must record the case version"
    assert research["retrieval_calls"][-1]["supplement"], "case terms widen retrieval"
