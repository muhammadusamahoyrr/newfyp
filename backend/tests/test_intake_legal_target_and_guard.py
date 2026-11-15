"""Corrective batch 2026-10-13: the provision the client NAMED (gate v3) and
the intake output contract (intake_output_guard).

d037: "probation under section 562 of the CrPC" retrieved CrPC s.388, the gate
said "supported", and the analysis advised filing under s.562 (omitted 1960).
m004: an action "register the case under Section 381 PPC" was judged
`unsupported` against the bound PPC 381-A passage and was still shown.

Offline: hand-built corpus index, the repository's real omission records.
"""
from __future__ import annotations

import pytest

from app.ai import intake_output_guard as guard
from app.ai.corpus_index import CorpusIndex, StatuteCoverage
from app.ai.nodes import intake_evidence_gate_node as gate


def _cov(statute, secs):
    nums = frozenset(int("".join(ch for ch in s if ch.isdigit())) for s in secs)
    return StatuteCoverage(statute=statute, sections=frozenset(secs), numbered=nums, highest=max(nums),
                           artifacts=frozenset(), ceiling_outliers=frozenset(), omitted=frozenset(),
                           omission_records={})


@pytest.fixture
def idx():
    return CorpusIndex({
        "PPC 1860": _cov("PPC 1860", [str(n) for n in range(1, 512)] + ["489F", "381A"]),
        "CrPC 1898": _cov("CrPC 1898", [str(n) for n in range(1, 566)]),
    })


def ch(statute, section, content="text"):
    return {"statute": statute, "section_number": section, "province": "federal", "content": content,
            "chunk_id": f"{statute}:{section}"}


D037 = "Can a first offender be released on probation under section 562 of the CrPC?"
D038 = "What are the powers of an executive magistrate under section 10 CrPC?"


def decide(idx, chunks, text, **kw):
    return gate.decide(chunks=chunks, retrieval_error=False, province="punjab", user_text=text,
                       relevance_score=None, index=idx, **kw)


# ── Batch 1: the requested provision ────────────────────────────────────────

def test_d037_omitted_562_with_unrelated_388_is_not_supported(idx):
    kept, rec = decide(idx, [ch("CrPC 1898", "388", "388. Suspension of execution of sentence")], D037)
    assert rec["status"] == "corpus_not_capable" and rec["capability"] == "omitted_provision"
    target = rec["requested_provisions"][0]
    assert target["omitted"] and "Probation of Offenders Ordinance" in target["omitted_by"]


def test_d038_omitted_crpc_10_is_not_supported_by_another_section(idx):
    _, rec = decide(idx, [ch("CrPC 1898", "107"), ch("CrPC 1898", "145")], D038)
    assert rec["status"] == "corpus_not_capable" and rec["capability"] == "omitted_provision"


def test_a_live_named_provision_with_matching_evidence_stays_supported(idx):
    _, rec = decide(idx, [ch("CrPC 1898", "154", "154. Information in cognizable cases")],
                    "Section 154 CrPC information in cognizable cases")
    assert rec["status"] == "supported"


def test_a_live_named_provision_with_only_unrelated_evidence_is_no_evidence(idx):
    _, rec = decide(idx, [ch("CrPC 1898", "155"), ch("CrPC 1898", "156")],
                    "Section 154 CrPC information in cognizable cases")
    assert rec["status"] == "no_relevant_evidence"


def test_489f_is_not_its_parent_489(idx):
    _, parent_only = decide(idx, [ch("PPC 1860", "489", "489. Tampering with property mark")],
                            "Section 489-F PPC dishonestly issuing a cheque")
    assert parent_only["status"] == "no_relevant_evidence"
    _, lettered = decide(idx, [ch("PPC 1860", "489", "489-\nF. \nDishonestly issuing a cheque")],
                         "Section 489-F PPC dishonestly issuing a cheque")
    assert lettered["status"] == "supported", "the header-repaired passage IS 489-F"
    assert lettered["requested_provisions"][0]["omitted"] is False


def test_a_parent_omission_never_applies_to_a_lettered_child(idx, monkeypatch):
    from app.ai import statute_omissions as so
    real = so.record_for

    def fake(statute, section):
        if (statute, section) == ("PPC 1860", 489):
            return so.OmissionRecord(section=489, status="omitted", instrument="X", date="2000-01-01")
        return real(statute, section)
    monkeypatch.setattr(so, "record_for", fake)
    assert gate.requested_provisions("Section 489-F PPC", idx)[0]["omitted"] is False
    assert gate.requested_provisions("Section 489 PPC", idx)[0]["omitted"] is True


def test_a_source_marked_omitted_lettered_chunk_is_excluded(idx):
    kept, rec = decide(idx, [{**ch("PPC 1860", "216B", "216-B. Definition of harbour"),
                              "provision_status": "omitted"}],
                       "someone is hiding a robber in his house near me")
    assert kept == [] and rec["dropped"]["omitted_section"] == 1


def test_a_fact_story_without_a_citation_is_not_over_restricted(idx):
    _, rec = decide(idx, [ch("PPC 1860", "379", "379. Punishment for theft")],
                    "Someone stole my motorcycle from outside my house last night")
    assert rec["status"] == "supported" and rec["requested_provisions"] == []


def test_a_missing_instrument_stays_capability_first(idx):
    _, rec = decide(idx, [ch("CPC 1908", "9")], "Can I claim damages under section 73 of the Contract Act?")
    assert rec["status"] == "corpus_not_capable" and rec["capability"] == "instrument_not_in_corpus"


def test_mixed_supported_and_omitted_issue_needs_binding(idx):
    text = "Someone stole my motorcycle from outside my house last night. Can I get probation under section 562 of the CrPC?"
    scope = gate.scope_issues(text, idx)
    assert [i["kind"] for i in scope["unsupported"]] == ["omitted_provision"] and not scope["pure"]
    _, unbound = decide(idx, [ch("PPC 1860", "379")], text)
    assert unbound["status"] == "corpus_not_capable"
    _, bound = decide(idx, [ch("PPC 1860", "379")], text, issue_scope={**scope, "retrieval_bound": True})
    assert bound["status"] == "partially_supported"
    assert "562" not in bound["issue_scope"]["supported_issue"]


# ── Batch 2: the output contract ────────────────────────────────────────────

def _analysis(actions, kinds, claims, cites, gate_status="supported", **extra):
    return {"summary": extra.pop("summary", "Your motorcycle was stolen."), "recommended_actions": actions,
            "recommended_action_kinds": kinds, "claim_assessments": claims, "law_citations": cites,
            "applicable_laws": [f"{c['statute']} s.{c['section']}" for c in cites],
            "evidence_gate": {"status": gate_status, **extra.pop("gate", {})},
            "grounding_status": "claims_disagree", "grounded": False, "risk_level": "medium",
            "uncited_legal_actions": extra.pop("uncited", []), **extra}


BOUND_381A = {"statute": "PPC 1860", "section": "381-A", "status": "bound", "chunk_id": "c601"}
FIR_381 = "Lodge an FIR and request registration under Section 381 of the PPC."
KEEP_EVIDENCE = "Collect and preserve photographs, CCTV footage and ownership documents."


def test_m004_wrong_section_action_judged_unsupported_is_removed():
    a = _analysis([FIR_381, KEEP_EVIDENCE], ["legal", "general"],
                  [{"index": "2", "kind": "action", "action_kind": "legal", "text": FIR_381,
                    "citation_status": "matched", "support": "unsupported"}], [BOUND_381A],
                  gate_status="partially_supported")
    out = guard.enforce(a)
    assert FIR_381 not in out["recommended_actions"]
    assert KEEP_EVIDENCE in out["recommended_actions"]
    assert guard.LAWYER_REVIEW_STEP in out["recommended_actions"]
    assert out["output_guard"]["removed_actions"][0]["reason"] == "judged_unsupported"
    assert "381" not in " ".join(out["recommended_actions"]), "never silently re-cited as 381-A"


def test_an_unsupported_action_on_a_bound_non_supporting_citation_is_removed():
    t = "File a complaint under Section 420 PPC."
    out = guard.enforce(_analysis([t], ["legal"], [{"index": "2", "kind": "action", "action_kind": "legal",
                                                     "text": t, "citation_status": "matched",
                                                     "support": "unsupported"}], [BOUND_381A]))
    assert t not in out["recommended_actions"]


def test_an_unbound_citation_is_withheld_but_a_bound_one_stays():
    bad = {"statute": "CrPC 1898", "section": "489-F", "status": "mismatched", "chunk_id": "c928"}
    out = guard.enforce(_analysis([KEEP_EVIDENCE], ["general"], [], [BOUND_381A, bad]))
    assert out["law_citations"] == [BOUND_381A]
    assert out["withheld_citations"] == [bad]
    assert all("CrPC" not in law for law in out["applicable_laws"])


def test_a_supported_legal_action_is_unchanged():
    t = "Lodge an FIR for theft of a motor vehicle under Section 381-A PPC."
    a = _analysis([t, KEEP_EVIDENCE], ["legal", "general"],
                  [{"index": "2", "kind": "action", "action_kind": "legal", "text": t,
                    "citation_status": "matched", "support": "supported"}], [BOUND_381A])
    out = guard.enforce(a)
    assert out["recommended_actions"] == [t, KEEP_EVIDENCE]
    assert out["output_guard"]["removed_actions"] == [] and not out["output_guard"]["downgraded"]


def test_removing_every_legal_claim_downgrades_the_analysis():
    t = "File under Section 379 PPC."
    out = guard.enforce(_analysis([t, KEEP_EVIDENCE], ["legal", "general"],
                                  [{"index": "2", "kind": "action", "action_kind": "legal", "text": t,
                                    "citation_status": "unresolved", "support": "unassessed"}], [],
                                  uncited=["2"]))
    assert out["grounding_status"] == guard.NO_LEGAL_CONTENT
    assert out["grounded"] is False and out["risk_level"] is None


def test_a_partial_answer_cannot_mention_the_unsupported_issue():
    leak = "Check today's gold rate in Lahore with your bank."
    out = guard.enforce(_analysis([KEEP_EVIDENCE, leak], ["general", "general"], [], [BOUND_381A],
                                  gate_status="partially_supported",
                                  summary="Your motorcycle was stolen. What is the current gold rate in Lahore today?"))
    assert leak not in out["recommended_actions"]
    assert "gold" not in out["summary"].lower()


def test_d037_style_omitted_provision_actions_are_removed_and_currency_stated(idx):
    _, rec = decide(idx, [ch("CrPC 1898", "388")], D037)
    file_562 = "If eligible, file an application for probation under Section 562 with the court."
    text_562 = "Obtain the full text of Section 562 CrPC and any relevant case law."
    a = _analysis([file_562, text_562, "Gather all documents related to the offence."],
                  ["legal", "general", "general"], [], [], gate_status=rec["status"],
                  gate=rec, summary="Section 562 allows probation for first offenders.")
    out = guard.enforce(a)
    assert not any("562" in x for x in out["recommended_actions"])
    assert "Section 562 allows" not in out["summary"]
    assert "Probation of Offenders Ordinance" in out["currency_notice"]
    assert out["law_citations"] == []


def test_stored_and_returned_analysis_are_the_same_object(monkeypatch):
    """_run_intake_ai applies the guard BEFORE provenance and return."""
    import asyncio
    import json
    from app.ai.graph import supervisor
    from app.services import intake_service as svc
    seen = {}

    class FakeGraph:
        async def ainvoke(self, state):
            return {"answer": json.dumps({"summary": "s", "recommended_actions": [FIR_381, KEEP_EVIDENCE],
                                          "recommended_action_kinds": ["legal", "general"],
                                          "risk_level": "low"}),
                    "evidence_gate": {"status": "supported"}, "citations": [BOUND_381A],
                    "claim_assessments": [{"index": "2", "kind": "action", "action_kind": "legal",
                                           "text": FIR_381, "citation_status": "matched",
                                           "support": "unsupported"}]}

    async def capture(result, analysis, *a, **k):
        seen["provenance"] = json.loads(json.dumps(analysis, default=str))
    monkeypatch.setattr(supervisor, "intake_graph", FakeGraph())
    monkeypatch.setattr(svc, "_record_intake_provenance", capture)
    out = asyncio.run(svc._run_intake_ai("my bike was stolen from my house", "criminal", "punjab", "s", "c"))
    assert FIR_381 not in out["recommended_actions"]
    assert seen["provenance"]["recommended_actions"] == out["recommended_actions"]
    assert seen["provenance"]["output_guard"] == out["output_guard"]


# ── Batch 4: citation identity normalisation ────────────────────────────────

from app.ai.intake_evidence import bind_intake_citations  # noqa: E402


def _ev(i, statute, section, content):
    return {"id": str(i), "kind": "statute", "statute": statute, "section": section, "content": content,
            "chunk_id": f"c{i}", "province": "federal"}


MFLO7 = _ev(1, "Muslim Family Laws Ordinance 1961", "7", "7. Talaq. (1) Any man who wishes to divorce")
PPWVA8 = _ev(2, "Punjab Protection of Women against Violence Act 2016", "8", "8. Residence order")
PPC489F = _ev(3, "PPC 1860", "489", "489-\nF. \nDishonestly issuing a cheque")
CRPC345 = _ev(4, "CrPC 1898", "345", "whom criminal force is used")
SCHEDULE_ROW = _ev(5, "CrPC 1898", "", "489-\nF \nDishonestly issuing \na cheque Ditto")


def _bind(cite, *ev):
    out, _ = bind_intake_citations([cite], list(ev))
    return out[0]


@pytest.mark.parametrize("section", ["7", "Section 7", "s. 7", "7(2)", "7(30 days)", "Section 7(5)"])
def test_written_forms_of_the_same_provision_bind(section):
    c = _bind({"evidence_id": "1", "statute": "Muslim Family Laws Ordinance 1961", "section": section}, MFLO7)
    assert c["status"] == "bound" and c["section"] == "7"


def test_a_different_section_on_the_passage_is_still_mismatched():
    c = _bind({"evidence_id": "2", "statute": "Punjab Protection of Women against Violence Act 2016",
               "section": "Section 7"}, PPWVA8)
    assert c["status"] == "mismatched"


def test_the_header_repaired_lettered_passage_shows_its_true_identity():
    c = _bind({"evidence_id": "3", "statute": "PPC 1860", "section": "489-F"}, PPC489F)
    assert c["status"] == "bound" and c["section"] == "489-F"


def test_a_wrong_instrument_on_a_real_passage_stays_mismatched():
    c = _bind({"evidence_id": "4", "statute": "CrPC 1898", "section": "489-F"}, CRPC345)
    assert c["status"] == "mismatched"


def test_a_schedule_row_is_never_bound_as_a_section():
    c = _bind({"evidence_id": "5", "statute": "CrPC 1898", "section": "489-F"}, SCHEDULE_ROW)
    assert c["status"] == "mismatched"


# ── Batch 5: Urdu / Roman-Urdu legal terms for intake retrieval ─────────────

from app.ai import legal_terms  # noqa: E402

D007 = "میرے بھائی کو گرفتار کر لیا گیا ہے۔ اس کی ضمانت کیسے ہوگی؟"


def test_urdu_bail_question_gets_english_legal_terms():
    assert legal_terms.legal_terms(D007) == ["bail", "arrest"]
    assert legal_terms.augment(D007).endswith("bail arrest")


def test_roman_urdu_terms_are_whole_words():
    assert legal_terms.legal_terms("bhai ki zamanat kaise hogi") == ["bail"]
    assert legal_terms.legal_terms("zamanatnama") == [], "no match inside a longer word"


def test_english_and_term_free_text_are_unchanged():
    q = "My brother has been arrested. How can he apply for bail?"
    assert legal_terms.augment(q) == q
    assert legal_terms.augment("someone hit my car") == "someone hit my car"


async def _retrieval_query_seen(monkeypatch, purpose):
    from app.ai.nodes import retrieval_node as rn
    seen = {}

    async def no_expand(q):
        seen["expand_input"] = q
        return q

    class R:
        def invoke(self, q):
            return []
    monkeypatch.setattr(rn, "_expand_query", no_expand)
    monkeypatch.setattr(rn, "build_retriever", lambda *a, **k: R())
    monkeypatch.setattr(rn, "_graph_hop2", lambda *a, **k: [])

    async def no_case_law(*a, **k):
        return []
    monkeypatch.setattr(rn, "_retrieve_case_law", no_case_law)
    await rn.retrieval_node({"query": D007, "user_text": D007, "case_type": "criminal", "province": "punjab",
                             "retrieval_policy": {"purpose": purpose, "case_law": False}})
    return seen["expand_input"]


async def test_intake_retrieval_query_carries_the_terms(monkeypatch):
    assert (await _retrieval_query_seen(monkeypatch, "intake")).endswith("bail arrest")


async def test_chat_retrieval_query_is_unchanged(monkeypatch):
    assert await _retrieval_query_seen(monkeypatch, "chat") == D007
