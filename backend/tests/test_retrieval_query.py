"""Client chat English retrieval query (ai/retrieval_query.py, 2026-10-21).

Live: "Briefly, what is khula?" and "خلع کیا ہے؟" retrieved Family Courts Act
s.10 but scored too low to answer; "chori ki saza kya hai?" was searched in
Urdu script and missed PPC s.379. One general-information fallback tied khula
to the Muslim Family Laws Ordinance with no source.
"""
import pytest
from langchain_core.documents import Document

from app.ai import general_guidance, retrieval_query as rq
from app.ai.graph.edges import route_after_triage
from app.ai.scoring import score_retrieval_batch


# ── the query ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("q,normalized,expected", [
    ("Briefly, what is khula?", None, "what is khula? khula dissolution of marriage"),
    ("خلع کیا ہے؟", None, "khula dissolution of marriage"),
    ("khula kise kehte hain", None, "khula dissolution of marriage"),
    ("chori ki saza kya hai?", "چوری کی سزا کیا ہے؟", "theft punishment"),
    ("zamanat kya hoti hai", None, "bail"),
    # statute names and section numbers survive, in order
    ("dafa 302 PPC ki saza kya hai", None, "section 302 PPC punishment"),
    ("دفعہ 379 PPC کی سزا کیا ہے؟", None, "section 379 PPC punishment"),
    # English: only the leading length word goes
    ("In simple words: what is bail before arrest?", None, "what is bail before arrest?"),
])
def test_general_questions_get_an_english_retrieval_query(q, normalized, expected):
    assert rq.build(q, normalized) == expected


@pytest.mark.parametrize("q", [
    "What is Section 489-F PPC?",                      # English, nothing to add: unchanged
    "what is bail?",
    "My landlord kept my deposit of Rs 100,000 in Lahore",
    # a person's own matter keeps the existing path -- no fact is dropped
    "meri biwi ghar chor kar chali gayi hai",
    "mera bhai giraftar hua hai zamanat kaise hogi",
    "کرایہ دار نے کرایہ نہیں دیا",
    "aaj mausam kaisa hai",                            # no legal term to anchor on
    "",
])
def test_everything_else_keeps_the_existing_query(q):
    assert rq.build(q) is None


def test_an_english_matter_keeps_every_word_it_states():
    out = rq.build("Briefly, my landlord in Lahore kept my deposit of Rs 100,000 under Section 15")
    assert out == "my landlord in Lahore kept my deposit of Rs 100,000 under Section 15"


@pytest.mark.parametrize("state", [
    {"surface": "research", "query": "خلع کیا ہے؟"},
    {"surface": None, "query": "خلع کیا ہے؟"},
    {"surface": "client", "query": "خلع کیا ہے؟", "retrieval_query_supplement": "case words"},
    {"surface": "client", "query": "خلع کیا ہے؟", "retrieval_policy": {"purpose": "intake"}},
])
def test_only_client_chat_uses_it(state):
    assert rq.for_state(state) is None


# ── the score it produces (lexical signal; embedding and LLM grade fixed) ────

_S10 = ("10. Pre-trial proceeding. (4) If no compromise or reconciliation is possible the Family Court "
        "shall pass a decree for dissolution of marriage forthwith on the ground of khula and restore "
        "to the husband the haq mehr received by the wife.")
_OTHER = "17. Guardian of the person of a minor. The court shall be guided by the welfare of the minor."


@pytest.mark.parametrize("q", ["Briefly, what is khula?", "خلع کیا ہے؟", "khula kise kehte hain"])
def test_the_english_query_scores_the_khula_provision_higher(q):
    chunks = [{"content": _S10}, {"content": _OTHER}]
    def agg(query):
        return score_retrieval_batch(query_text=query, chunks=chunks, embedding_scores=[0.5, 0.5],
                                     llm_grades=[1, 1])[1].lexical
    assert agg(rq.build(q)) > agg(q)


# ── retrieval node + grader wiring ───────────────────────────────────────────

class _Retriever:
    def __init__(self):
        self.queries = []

    def invoke(self, q):
        self.queries.append(q)
        return [Document(page_content=_S10, metadata={"chunk_id": "fca_10", "statute": "Family Courts Act 1964",
                                                      "section_number": "10"})]


async def _run(monkeypatch, state):
    from app.ai.nodes import retrieval_node as rn
    seen = {}

    async def expand(q, english=False):
        seen["expand"] = (q, english)
        return q

    async def no_case_law(q, province=None):
        return []
    r = _Retriever()
    monkeypatch.setattr(rn, "_expand_query", expand)
    monkeypatch.setattr(rn, "_retrieve_case_law", no_case_law)
    monkeypatch.setattr(rn, "build_retriever", lambda *a, **k: r)
    monkeypatch.setattr(rn, "_graph_hop2", lambda *a, **k: [])
    monkeypatch.setattr(rn, "_docs_to_chunks", lambda docs, prov="", **k: [
        {**d.metadata, "content": d.page_content} for d in docs])

    async def no_exact(state, chunks):
        return chunks, {}
    monkeypatch.setattr(rn, "apply_client_exact_provisions", no_exact)
    out = await rn.retrieval_node({"case_type": "family", "province": "unknown", **state})
    return out, r.queries, seen


async def test_client_urdu_question_is_searched_in_english_and_keeps_the_users_words(monkeypatch):
    state = {"query": "خلع کیا ہے؟", "surface": "client", "language": "ur"}
    out, queries, seen = await _run(monkeypatch, state)
    assert queries[0] == "khula dissolution of marriage"
    # The deterministic query is the search query: the LLM rewrite was measured
    # adding wrong law ("CrPC Section 379", "IPC") and is not asked.
    assert "expand" not in seen
    assert out["expanded_query"] == "khula dissolution of marriage"
    assert out["retrieval_query"] == "khula dissolution of marriage"
    assert "query" not in out, "the user's words are never replaced"


async def test_research_retrieval_is_unchanged(monkeypatch):
    out, queries, seen = await _run(monkeypatch, {"query": "خلع کیا ہے؟", "surface": "research"})
    assert queries[0] == "خلع کیا ہے؟" and seen["expand"] == ("خلع کیا ہے؟", False)
    assert out["retrieval_query"] is None


async def test_a_client_matter_is_searched_with_its_own_words(monkeypatch):
    q = "meri biwi ghar chor kar chali gayi hai"
    out, queries, seen = await _run(monkeypatch, {"query": q, "surface": "client"})
    assert queries[0] == q and out["retrieval_query"] is None
    assert seen["expand"] == (q, True), "only the LLM rewrite is asked for English; it is appended"


async def test_the_grader_scores_with_the_retrieval_query(monkeypatch):
    from app.ai.nodes import retrieval_grader_node as g
    seen = {}

    class LLM:
        def invoke(self, msgs):
            seen["grader_prompt"] = msgs[1]["content"]
            return type("R", (), {"content": "[2]"})()

    def sims(query, chunks, case_type):
        seen["embedding_query"] = query
        return [0.5] * len(chunks)
    async def no_record(state, aggregate):
        return None
    monkeypatch.setattr(g, "get_fast_llm", lambda **k: LLM())
    monkeypatch.setattr(g, "similarity_scores", sims)
    monkeypatch.setattr(g, "_record_observation", no_record)
    await g.retrieval_grader_node({
        "query": "خلع کیا ہے؟", "normalized_query": "خلع کیا ہے؟", "case_type": "family",
        "retrieval_query": "khula dissolution of marriage",
        "retrieved_chunks": [{"content": _S10, "statute": "Family Courts Act 1964", "section_number": "10"}]})
    assert seen["embedding_query"] == "khula dissolution of marriage"
    assert "خلع کیا ہے؟" in seen["grader_prompt"], "the LLM grader still reads the user's words"


# ── routing is untouched: general answered, a matter still asked for facts ───

def test_a_personal_matter_still_goes_to_clarification():
    state = {"query": "meri biwi ghar chor kar chali gayi hai", "surface": "client",
             "province": "unknown", "case_type": "family", "routing_mode": "single"}
    assert route_after_triage(state) == "clarification_node"


# ── weak / no retrieval: no invented law ─────────────────────────────────────

def test_client_guidance_drops_every_line_that_names_a_law():
    body = ("**Khula** is a divorce the wife asks the court for.\n"
            "- Under the Muslim Family Laws Ordinance 1961, a woman can apply for khula.\n"
            "- The court may grant it under Section 10.\n"
            "- Chori PPC ke tehat jurm hai.\n"
            "- خلع کا حق مسلم فیملی لاز آرڈیننس کے تحت ہے۔\n"
            "- Go to the family court with your nikahnama and act quickly.")
    out = general_guidance.drop_named_law(body)
    assert "Ordinance" not in out and "Section" not in out and "PPC" not in out and "آرڈیننس" not in out
    assert "act quickly" in out and "family court" in out


async def test_client_guidance_never_shows_an_unsourced_law(monkeypatch):
    class LLM:
        def invoke(self, msgs):
            seen["system"] = msgs[0]["content"]
            return type("R", (), {"content": (
                "Khula is a divorce initiated by the wife through the family court.\n"
                "- Under the Muslim Family Laws Ordinance 1961 she may apply.\n"
                "- Take your nikahnama and CNIC to the family court in your district.")})()
    seen = {}
    monkeypatch.setattr(general_guidance, "get_llm", lambda **k: LLM())
    out = await general_guidance.write({"query": "Briefly, what is khula?", "language": "en"}, audience="client")
    assert out.startswith(general_guidance.CLIENT_HEADER_EN)
    assert "Muslim Family Laws Ordinance" not in out and "family court" in out
    assert "Do NOT name any Act" in seen["system"]


async def test_client_guidance_that_is_only_named_law_falls_back_to_the_refusal(monkeypatch):
    class LLM:
        def invoke(self, msgs):
            return type("R", (), {"content": "- Section 379 PPC punishes theft with three years.\n- See CrPC."})()
    monkeypatch.setattr(general_guidance, "get_llm", lambda **k: LLM())
    assert await general_guidance.write({"query": "chori ki saza kya hai?", "language": "roman_urdu"},
                                        audience="client") is None


async def test_lawyer_guidance_is_unchanged(monkeypatch):
    class LLM:
        def invoke(self, msgs):
            return type("R", (), {"content": "Article 199 of the Constitution covers writ jurisdiction of High Courts."})()
    monkeypatch.setattr(general_guidance, "get_llm", lambda **k: LLM())
    out = await general_guidance.write({"query": "what is a writ?", "language": "en"})
    assert "Article 199" in out


async def test_no_chunks_still_refuses():
    from app.ai.decision_engine import run_decision_engine
    out = run_decision_engine({"query": "خلع کیا ہے؟", "reranked_chunks": [], "retrieved_chunks": [],
                               "relevance_score": 0.0, "case_type": "family"})
    assert out["arbitration_output"] == "refuse"


# ── the LLM rewrite: English on request, bounded, failure-safe ───────────────

async def test_english_rewrite_is_appended_bounded_and_failure_safe(monkeypatch):
    from app.ai.nodes import retrieval_node as rn
    replies = {}

    class LLM:
        def invoke(self, msgs):
            replies["system"] = msgs[0]["content"]
            return type("R", (), {"content": replies["text"]})()
    monkeypatch.setattr(rn, "get_fast_llm", lambda **k: LLM())

    replies["text"] = "punishment for theft under Section 379 PPC"
    assert await rn._expand_query("chori", english=True) == "chori punishment for theft under Section 379 PPC"
    assert "in English" in replies["system"]

    replies["text"] = "theft " * 60                    # runaway: ignored
    assert await rn._expand_query("chori", english=True) == "chori"

    replies["text"] = "چوری کی سزا"                     # no English legal term: ignored
    assert await rn._expand_query("chori", english=True) == "chori"

    def boom(**k):
        raise RuntimeError("provider down")
    monkeypatch.setattr(rn, "get_fast_llm", boom)
    assert await rn._expand_query("chori", english=True) == "chori"

    monkeypatch.setattr(rn, "get_fast_llm", lambda **k: LLM())
    replies["text"] = "theft"
    await rn._expand_query("chori")
    assert "in English" not in replies["system"], "research / intake prompt unchanged"
