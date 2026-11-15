"""Provincial-authority availability on Intake, client Chat and lawyer Research (batch 10, 2026-10-17).

A question that clearly requires an authority the corpus does not hold for the
matter's CONFIRMED province must not be "supported" -- or answered confidently --
from unrelated retrieved law. The registry (app/ai/authority_registry.py) is
built from the verified snapshot's provenance (source files), not from the
`province` labels:

    CPC 1908               -> Punjab only (Punjab Code text; labelled `federal`)
    Punjab Pre-emption law -> Punjab only
    Punjab Rented Premises -> Punjab only
    Specific Relief Act    -> NOT in the corpus (0 chunks)

Evidence here is SYNTHETIC (chunk dicts shaped like the corpus, both label
states) and the generators/judges are STUBS. Measured real-corpus retrieval is
in evals/legal_sources/BATCH10_AUTHORITY_REGISTRY.md, separately.
"""
from __future__ import annotations

import asyncio

import pytest

from app.ai import authority_registry as ar
from app.ai.nodes import intake_evidence_gate_node as gate
from tests.test_chat_followup_integration import _converse, _state, world  # noqa: F401  (fixture)

SOURCE_UNAVAILABLE = "source_unavailable_for_jurisdiction"


def chunk(statute, section, province, src):
    return {"statute": statute, "section_number": section, "province": province, "source_file": src,
            "content": f"{section}. ({statute}) text", "chunk_id": f"{statute}-{section}-{province}"}


def CPC(p="federal"):
    return [chunk("CPC 1908", s, p, "code of civil procedure 1908.pdf") for s in ("94", "151", "O39R1")]


PRE = [chunk("Punjab Pre-emption Act 1991", "13", "punjab", "punjab-pre-emption-act-1991.pdf")]
RENT = [chunk("Punjab Rented Premises Act 2009", "15", "punjab", "punjab-rented-premises-act-2009.pdf")]
LIM = [chunk("Limitation Act 1908", "3", "federal", "limitation act 1908.pdf")]
TPA = [chunk("Transfer of Property Act 1882", "54", "federal", "transfer of property act 1882.pdf")]
LEFTOVER = LIM + TPA


class _Idx:
    statutes = ["CPC 1908", "Limitation Act 1908", "Transfer of Property Act 1882", "PPC 1860",
                "Punjab Pre-emption Act 1991", "Punjab Rented Premises Act 2009"]

    def canonical(self, name):
        from app.ai.answer_citations import normalise_statute
        return next((s for s in self.statutes if normalise_statute(s) == normalise_statute(name)), None)

    def coverage(self, statute):
        return None


def decide(chunks, province, text, **kw):
    return gate.decide(chunks=chunks, retrieval_error=False, province=province, user_text=text,
                       relevance_score=None, index=_Idx(), **kw)


Q = {
    "cpc": "Can I get a temporary injunction to stop the defendant selling the plot?",
    "pre_emption": "My neighbour sold his land; can I claim my right of pre-emption?",
    "rented": "How can I seek eviction of a tenant who has not paid rent for six months?",
    "specific_relief": "Can the buyer get specific performance of the agreement to sell?",
}
OWN = {"cpc": lambda p: CPC(p), "pre_emption": lambda p: PRE, "rented": lambda p: RENT,
       "specific_relief": lambda p: []}
NON_PUNJAB = ["sindh", "kpk", "balochistan", "federal"]


# ── the registry is the verified provenance ─────────────────────────────────

def test_the_registry_records_verified_provenance_only():
    reg = ar.REGISTRY
    assert reg["cpc"]["held_for"] == {"punjab"} and reg["cpc"]["chunks"] == 1967
    assert reg["pre_emption"]["held_for"] == {"punjab"} and reg["pre_emption"]["chunks"] == 60
    assert reg["rented_premises"]["held_for"] == {"punjab"} and reg["rented_premises"]["chunks"] == 61
    assert reg["specific_relief"]["held_for"] == set() and reg["specific_relief"]["chunks"] == 0
    assert "20261017T024819Z" in ar.EVIDENCE


@pytest.mark.parametrize("c, expected", [
    (CPC("federal")[0], ("cpc", "punjab")), (CPC("punjab")[0], ("cpc", "punjab")),
    (PRE[0], ("pre_emption", "punjab")), (RENT[0], ("rented_premises", "punjab")), (LIM[0], None),
])
def test_chunk_authority_comes_from_provenance_not_the_label(c, expected):
    assert ar.chunk_authority(c) == expected


# ── Intake: reproduce the leftover-"supported" failure, both label states ──

@pytest.mark.parametrize("key", ["cpc", "pre_emption", "rented"])
@pytest.mark.parametrize("province", NON_PUNJAB)
@pytest.mark.parametrize("state", ["current", "relabelled"])
def test_intake_never_supports_an_unheld_authority_from_leftovers(key, province, state):
    # relabelled: retrieval already filtered the Punjab text out -> only leftovers;
    # current: the CPC still arrives labelled "federal" (the others are labelled punjab either way)
    own = OWN[key]("federal" if state == "current" else "punjab")
    chunks = LEFTOVER + (own if (state == "current" and key == "cpc") else [])
    admissible, rec = decide(chunks, province, Q[key])
    assert rec["status"] == SOURCE_UNAVAILABLE, (key, province, state, rec["status"])
    assert not any(ar.chunk_authority(c) for c in admissible)


def test_specific_relief_is_unavailable_everywhere_including_punjab():
    for p in NON_PUNJAB + ["punjab"]:
        _, rec = decide(LEFTOVER, p, Q["specific_relief"])
        assert rec["status"] == SOURCE_UNAVAILABLE, p


@pytest.mark.parametrize("key", ["cpc", "pre_emption", "rented"])
def test_confirmed_punjab_keeps_its_own_law(key):
    admissible, rec = decide(LEFTOVER + OWN[key]("punjab"), "punjab", Q[key])
    assert rec["status"] == gate.SUPPORTED
    assert any(ar.chunk_authority(c) for c in admissible)


@pytest.mark.parametrize("key", ["cpc", "pre_emption", "rented"])
def test_unknown_or_inferred_province_is_not_punjab(key):
    for kw in ({}, {"basis": "inferred_from_query", "inferred": True}):
        p = "" if not kw else "punjab"
        _, rec = decide(LEFTOVER + OWN[key]("punjab"), p, Q[key], **kw)
        assert rec["status"] == SOURCE_UNAVAILABLE, (key, kw)


def test_a_mixed_question_keeps_its_held_issue_and_marks_the_other():
    text = ("My neighbour sold his land; can I claim pre-emption, and what limitation period applies under "
            "the Limitation Act?")
    admissible, rec = decide(LIM + PRE, "sindh", text)
    assert rec["status"] == gate.SUPPORTED
    assert [c["statute"] for c in admissible] == ["Limitation Act 1908"]
    assert rec["authority"]["unavailable"] == ["pre_emption"]
    assert any("pre-emption" in c for c in rec["caveats"])


def test_mixed_current_label_cpc_is_not_admitted():
    # The Punjab CPC arrives labelled "federal": a label rule alone would admit it.
    text = "Can I get a temporary injunction, and what limitation period applies under the Limitation Act?"
    admissible, rec = decide(LIM + CPC("federal"), "sindh", text)
    assert rec["status"] == gate.SUPPORTED
    assert [c["statute"] for c in admissible] == ["Limitation Act 1908"]


@pytest.mark.parametrize("text", [
    "حق شفع کا دعویٰ کیسے کروں؟", "haq e shufa ka dawa kaise karun", "kirayedar ko bedakhli kaise karwaun",
    "کرایہ دار کی بے دخلی کیسے ہو؟", "مجھے حکم امتناعی چاہیے", "Section 13 of the Punjab Pre-emption Act",
    "under the Punjab Rented Premises Act, 2009", "Order XXXIX Rule 1 CPC",
])
def test_urdu_roman_urdu_and_explicit_references_are_recognised(text):
    assert ar.required(text), text


@pytest.mark.parametrize("text", [
    "I pay rent every month.", "My property was damaged in the rain.", "I went to court with an application.",
    "Can I file an appeal?", "The tenant paid the rent late once.", "What is a pre-emptive strike?",
    "The landlord wants to sell the property.", "What is Section 186 PPC?",
])
def test_negative_controls_are_not_hard_refusals(text):
    assert ar.required(text) == {}, text


@pytest.mark.parametrize("text, chunks", [
    ("What is the limitation period to recover money lent?", LIM),
    ("Can the court transfer property by sale under the Transfer of Property Act?", TPA),
    ("I pay rent every month and the landlord wants to sell the property.", LEFTOVER),
])
def test_unrelated_valid_law_is_still_supported(text, chunks):
    _, rec = decide(chunks, "sindh", text)
    assert rec["status"] == gate.SUPPORTED


# ── client Chat: the REAL socket and graph, stubbed models ─────────────────

def _final(ws):
    finals = ws.frames("final")
    assert finals, ws.sent
    return finals[-1]


@pytest.mark.parametrize("key, text", [
    ("cpc", Q["cpc"]), ("pre_emption", Q["pre_emption"]), ("rented", Q["rented"]),
    ("cpc_ur", "مجھے حکم امتناعی چاہیے، کیا ملے گا؟"), ("pre_ur", "haq e shufa ka dawa kaise karun?"),
    ("exact", "Is my suit maintainable under Section 9 CPC?"),
])
@pytest.mark.parametrize("province", ["sindh", "kpk", "balochistan", "federal"])
def test_chat_gives_a_limitation_not_a_confident_answer(world, key, text, province):
    world["chunks"] = LEFTOVER + (CPC("federal") if key.startswith("cpc") or key == "exact" else [])
    world["intents"], world["triage"] = ["new_query"], ["civil"]
    world["gen"] = ["You can obtain this relief under the law [1]."]
    ws = _converse(world, [text], province=province)
    final = _final(ws)
    assert world["gen_calls"] == [], "the answer writer was called on unavailable law"
    assert "not held" in final["content"] or "نہیں" in final["content"]
    assert not [c for c in final.get("claims") or [] if c.get("support") == "supported"]


def test_chat_inferred_punjab_asks_for_the_province(world):
    world["chunks"] = LEFTOVER + CPC("federal")
    world["intents"], world["triage"] = ["new_query"], ["civil"]
    world["gen"] = ["You can obtain this relief under the law [1]."]
    ws = _converse(world, [Q["cpc"]], province=None)           # triage stub infers "punjab"
    assert world["gen_calls"] == [] and "province" in _final(ws)["content"].lower()


def test_chat_confirmed_punjab_is_answered(world):
    world["chunks"] = CPC("federal")
    world["intents"], world["triage"] = ["new_query"], ["civil"]
    world["gen"] = ["A temporary injunction may be granted under Order XXXIX Rule 1 CPC [1]."]
    ws = _converse(world, [Q["cpc"]], province="punjab")
    assert world["gen_calls"] and "temporary injunction" in _final(ws)["content"]


def test_chat_unrelated_valid_law_is_answered_in_sindh(world):
    world["chunks"] = LIM
    world["intents"], world["triage"] = ["new_query"], ["civil"]
    world["gen"] = ["A suit to recover money lent is governed by the Limitation Act [1]."]
    ws = _converse(world, ["What is the limitation period to recover money lent?"], province="sindh")
    assert world["gen_calls"] and "governed by the Limitation Act" in _final(ws)["content"]


def test_chat_mixed_question_answers_the_held_issue_and_marks_the_other(world):
    world["chunks"] = LIM + PRE
    world["intents"], world["triage"] = ["new_query"], ["civil"]
    world["gen"] = ["A suit to recover money lent is governed by the Limitation Act [1]."]
    text = ("Can I claim pre-emption on my neighbour's land, and what limitation period applies under the "
            "Limitation Act?")
    ws = _converse(world, [text], province="sindh")
    final = _final(ws)
    assert world["gen_calls"], "the held issue must still be answered"
    sent_law = world["gen_calls"][-1][-1]["content"] + world["gen_calls"][-1][0]["content"]
    assert "Pre-emption Act" not in sent_law, "unavailable law reached the answer writer"
    assert "pre-emption" in final["content"].lower() and "not held" in final["content"]


def test_chat_cache_hit_cannot_serve_a_confident_answer(world):
    from app.ai import cache
    world["chunks"] = LEFTOVER
    world["intents"], world["triage"] = ["new_query", "new_query"], ["civil", "civil"]
    world["gen"] = ["You can get an injunction [1]."]
    # a confident answer cached for Sindh BEFORE this fix (written directly)
    key = cache._make_key(Q["cpc"], "civil", "sindh", "en", "default")
    cache._result_store[key] = {"payload": {"answer": "You can get an injunction under Order XXXIX [1].",
                                            "claims": [], "citations": [], "confidence": 0.9,
                                            "is_grounded": True}, "ts": 9e18}
    ws = _converse(world, [Q["cpc"]], province="sindh")
    assert "Order XXXIX" not in _final(ws)["content"] and "not held" in _final(ws)["content"]


def test_chat_follow_up_on_an_unavailable_question_stays_limited(world):
    world["chunks"] = LEFTOVER
    world["intents"], world["triage"] = ["new_query", "format_detail"], ["civil"]
    world["gen"] = ["You can get an injunction [1]."]
    ws = _converse(world, [Q["cpc"], "explain in detail"], province="sindh")
    finals = ws.frames("final")
    assert len(finals) == 2 and world["gen_calls"] == []
    assert all("not held" in f["content"] for f in finals)


# ── lawyer Research: the same gate at the decision node, lawyer surface ────

def test_research_decision_node_refuses_before_generation():
    from app.ai.graph import supervisor
    from app.ai.nodes.finalizer_node import finalizer_node
    state = {"query": Q["pre_emption"], "surface": "research", "province": "kpk",
             "jurisdiction_basis": "user_selected", "reranked_chunks": LEFTOVER, "relevance_score": 0.8,
             "language": "en"}
    out = supervisor._decision_node(state)
    assert out["arbitration_output"] == "refuse" and out["refusal_kind"] == SOURCE_UNAVAILABLE
    final = asyncio.run(finalizer_node({**state, **out}))
    assert "not held" in final["answer"] and final["is_grounded"] is False


def test_research_punjab_passes_through_to_the_engine(monkeypatch):
    from app.ai.graph import supervisor
    monkeypatch.setattr(supervisor, "run_decision_engine", lambda s: {"arbitration_output": "answer"})
    state = {"query": Q["pre_emption"], "surface": "research", "province": "punjab",
             "jurisdiction_basis": "user_selected", "reranked_chunks": PRE + LIM}
    assert supervisor._decision_node(state)["arbitration_output"] == "answer"


# ── mutation ────────────────────────────────────────────────────────────────

def _fails(fn, *a, **k):
    with pytest.raises((AssertionError, KeyError, TypeError, pytest.fail.Exception)):
        fn(*a, **k)


def test_mutant_registry_trusts_the_label(monkeypatch):
    monkeypatch.setattr(ar, "chunk_authority", lambda c: None)
    _fails(test_mixed_current_label_cpc_is_not_admitted)


def test_mutant_registry_claims_sindh_coverage(monkeypatch):
    monkeypatch.setitem(ar.REGISTRY["pre_emption"], "held_for", {"punjab", "sindh"})
    _fails(test_intake_never_supports_an_unheld_authority_from_leftovers, "pre_emption", "sindh", "relabelled")


def test_mutant_broad_rent_detection(monkeypatch):
    real = ar.required
    monkeypatch.setattr(ar, "required", lambda t: real(t) or ({"rented_premises": ["rent"]} if "rent" in t.lower() else {}))
    _fails(test_negative_controls_are_not_hard_refusals, "I pay rent every month.")


def test_mutant_unknown_means_punjab(monkeypatch):
    real = ar.available
    monkeypatch.setattr(ar, "available", lambda key, p, basis=None, inferred=False: True if not p else real(key, p, basis, inferred))
    _fails(test_unknown_or_inferred_province_is_not_punjab, "pre_emption")


def test_mutant_without_the_chat_gate(world, monkeypatch):
    from app.ai.graph import supervisor
    monkeypatch.setattr(supervisor, "_authority_gate", lambda state: None)
    _fails(test_chat_gives_a_limitation_not_a_confident_answer, world, "cpc", Q["cpc"], "sindh")


# ── further paths: Urdu output, the final backstop, engines, exact lookups ──

def test_chat_urdu_limitation_is_in_urdu(world):
    world["chunks"] = LEFTOVER
    world["intents"], world["triage"] = ["new_query"], ["civil"]
    world["gen"] = ["آپ حق شفع کا دعویٰ کر سکتے ہیں [1]۔"]
    ws = _converse(world, ["حق شفع کا دعویٰ کیسے کروں؟"], language="ur", province="sindh")
    assert world["gen_calls"] == [] and "موجود نہیں" in _final(ws)["content"]


def test_finalizer_backstop_withholds_a_cached_answer_even_if_the_cache_rule_is_gone():
    """The final visible answer is checked on its own: a cache hit that reached
    the finalizer (the decision node never ran) is not shown from other law."""
    from app.ai.nodes.finalizer_node import finalizer_node
    state = {"query": Q["rented"], "surface": "client", "province": "sindh",
             "jurisdiction_basis": "user_selected", "cache_hit": True, "is_grounded": True, "language": "en",
             "answer": "Under Section 15 the Rent Controller can order eviction [1].",
             "citations": [{"statute": "Punjab Rented Premises Act 2009", "section": "15", "status": "cited"}],
             "claim_assessments": [{"text": "Under Section 15 the Rent Controller can order eviction [1].",
                                    "support": "supported"}]}
    out = asyncio.run(finalizer_node(state))
    assert "Section 15" not in out["answer"] and "not held" in out["answer"]
    assert out["is_grounded"] is False and out["citations"] == []
    assert all(c["support"] != "supported" for c in out["claim_assessments"])


def test_cache_rule_declines_lookup_and_write_for_unavailable_authority():
    from app.ai.nodes.cache_node import cache_block_reason
    base = {"surface": "client", "province": "sindh", "jurisdiction_basis": "user_selected"}
    assert cache_block_reason({**base, "query": Q["pre_emption"]}) == "authority_unavailable"
    assert cache_block_reason({**base, "query": "What is the limitation period to recover money lent?"}) is None
    assert cache_block_reason({**base, "province": "punjab", "query": Q["pre_emption"]}) is None


def test_mixed_engine_answer_is_not_refused_but_marked():
    engine = {"tool": "court_fee", "args": {}, "result": {"fee": 15000, "legal_basis": "Court Fees Act"}}
    state = {"query": "What court fee is payable on a suit for specific performance of my agreement?",
             "province": "sindh", "jurisdiction_basis": "user_selected", "reranked_chunks": LIM,
             "tool_results": [engine]}
    out = ar.chat_gate(state)
    assert out.get("arbitration_output") != "refuse"
    assert out["tool_results"] == [engine] and out["authority_limits"]["unavailable"] == ["specific_relief"]
    assert "Specific Relief" in ar.generation_rider(out["authority_limits"])


def test_exact_lookup_text_of_an_unheld_authority_is_removed():
    lookup = {"tool": "statute_lookup", "args": {}, "result": [
        {"statute": "Punjab Pre-emption Act 1991", "section": "13", "text": "talb-i-muwathibat ..."},
        {"statute": "Limitation Act 1908", "section": "3", "text": "..."}]}
    state = {"query": "Section 13 of the Punjab Pre-emption Act and the Limitation Act -- which applies?",
             "province": "kpk", "jurisdiction_basis": "user_selected", "reranked_chunks": PRE + LIM,
             "tool_results": [lookup]}
    out = ar.chat_gate(state)
    assert [c["statute"] for c in out["reranked_chunks"]] == ["Limitation Act 1908"]
    assert [r["statute"] for r in out["tool_results"][0]["result"]] == ["Limitation Act 1908"]


def test_mutant_without_the_final_backstop(monkeypatch):
    real = ar.assess_state
    calls = {"n": 0}

    def blind(state):            # the finalizer's own check sees nothing
        calls["n"] += 1
        return {**real(state), "unavailable": []}
    monkeypatch.setattr(ar, "assess_state", blind)
    _fails(test_finalizer_backstop_withholds_a_cached_answer_even_if_the_cache_rule_is_gone)


@pytest.mark.parametrize("text", [
    "What is the limitation period for a suit for specific performance?",
    "Is there a time limit to claim pre-emption after the sale?",
    "haq e shufa ka dawa kitni miyad me karna hota hai?",
])
def test_a_limitation_issue_is_kept_not_refused_whole(text):
    _, rec = decide(LIM, "sindh", text)
    assert rec["status"] == gate.SUPPORTED, text
    assert rec["authority"]["unavailable"]                      # still marked
    out = ar.chat_gate({"query": text, "province": "sindh", "jurisdiction_basis": "user_selected",
                        "reranked_chunks": LIM})
    assert out.get("arbitration_output") != "refuse" and out["authority_limits"]["unavailable"]


def test_mutant_limitation_issue_ignored(monkeypatch):
    monkeypatch.setattr(ar, "_LIMITATION_ISSUE", __import__("re").compile(r"(?!x)x"))
    _fails(test_a_limitation_issue_is_kept_not_refused_whole,
           "What is the limitation period for a suit for specific performance?")
