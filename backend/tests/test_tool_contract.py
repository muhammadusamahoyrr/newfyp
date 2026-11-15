"""The contract between the deterministic legal tools, retrieved statute text,
generation and claim verification (2026-10-14).

Reproduced failure (evals/research/results/on_r1_2026-10-14.jsonl, item E1):
"What is the punishment for cheating under Section 420 PPC?" -- the turn
retrieved PPC 420's own text as evidence [1], the model called
find_offence_sections("Section 420 PPC"), the lookup returned
{"error": "No offence matched 'Section 420 PPC'."} (it compared the whole query
string against section numbers), the generation rider told the model engine
output "OVERRIDES anything in the retrieved text", and the answer said the
offence "does not match any known provision". The judge -- told engine output
is "computed ground truth" -- marked two "no offence matches" claims supported,
citing [1], the very source that IS Section 420.

ROUTE-LEVEL tests here run the real ai_research handler and the real graph
(fixture from test_research_safeguards) with the REAL find_offence_sections
tool in place of the scripted tool layer; only model calls are scripted. The
generator stub behaves like the live model did: it follows a "no match" lookup
over the statute text it was given.
"""
from __future__ import annotations

import re

import pytest

from app.ai.tools.legal_tools import find_offence_sections
from tests.test_research_safeguards import ask, research  # noqa: F401  (fixture)

PPC_420 = {"statute": "PPC 1860", "section_number": "420", "chunk_id": "statutes_ppc_1860_0612",
           "province": "federal", "source_file": "ppc.pdf",
           "content": "420. Cheating and dishonestly inducing delivery of property: Whoever cheats and thereby "
                      "dishonestly induces the person deceived to deliver any property to any person, or to make, "
                      "alter or destroy the whole or any part of a valuable security, shall be punished with "
                      "imprisonment of either description for a term which may extend to seven years, and shall "
                      "also be liable to fine."}
PPC_417 = {"statute": "PPC 1860", "section_number": "417", "chunk_id": "statutes_ppc_1860_0609",
           "province": "federal", "source_file": "ppc.pdf",
           "content": "417. Punishment for cheating: Whoever cheats shall be punished with imprisonment of either "
                      "description for a term which may extend to one year, or with fine, or with both."}

# How a model states that a provision does not exist / was not found.
DENIAL = re.compile(r"no offence match|does not match any (?:known )?provision|not found|could not be found|"
                    r"does not exist|no (?:such )?(?:section|provision|offence) (?:was )?found", re.I)

BAD_420 = ("**Applicable Law:** None – the statutory determination indicates that no offence matching "
           "“Section 420 PPC” was found [1].\n\nThe precise punishment for Section 420 PPC cannot be "
           "confirmed because the referenced offence does not match any known provision [1].")
GOOD_420 = ("Under Section 420 PPC, cheating and dishonestly inducing delivery of property is punishable with "
            "imprisonment of either description for a term which may extend to seven years, and the offender "
            "is also liable to fine [1].")
BAD_417 = "No offence matching Section 417 PPC was found, so its punishment cannot be stated [1]."
GOOD_417 = ("Under Section 417 PPC, cheating is punishable with imprisonment of either description for a term "
            "which may extend to one year, or with fine, or with both [1].")


def _with_real_tool(research, monkeypatch, query):
    """Swap the scripted tool layer for the REAL find_offence_sections, called
    with the argument the live model used, and rebuild the graph."""
    from langgraph.checkpoint.memory import MemorySaver

    from app.ai.graph import supervisor

    async def tool_layer(state):
        out = await find_offence_sections.ainvoke({"query": query})
        research["tool_out"] = out
        return {"tool_results": [{"tool": "find_offence_sections", "args": {"query": query}, "result": out}],
                "tool_calls_made": ["find_offence_sections"]}
    monkeypatch.setattr(supervisor, "tool_node", tool_layer)
    graph = supervisor.build_chat_graph(checkpointer=MemorySaver())
    monkeypatch.setattr("app.ai.graph.supervisor.chat_graph", graph)


def _model_follows_engine(research, bad, good, miss_marker="No offence matched"):
    """The live model's behaviour: when the prompt carries a lookup miss, it
    answers from the miss; otherwise from the statute text."""
    from app.ai.nodes import generation_node as gn
    from langchain_core.messages import AIMessage

    class _Gen:
        def invoke(self, messages):
            research["gen_calls"].append(messages)
            prompt = messages[-1]["content"]
            research["prompt"] = prompt
            return AIMessage(content=(bad if miss_marker in prompt else good) + '\n{"confidence": 0.8}')
    return gn, _Gen


def _assert_no_false_denial(resp):
    assert not DENIAL.search(resp["answer"]), f"answer denies a provision whose text it was given:\n{resp['answer']}"
    false_supported = [c for c in resp["claims"]
                       if c.get("support") in ("supported", "partial") and DENIAL.search(c.get("text", ""))]
    assert not false_supported, f"a 'not found' claim was marked supported: {false_supported}"


def test_e1_section_420_exists_in_evidence_and_the_lookup_must_not_override_it(research, monkeypatch):
    research["chunks"] = [PPC_420]
    research["triage"] = ["criminal"]
    _with_real_tool(research, monkeypatch, "Section 420 PPC")
    gn, gen = _model_follows_engine(research, BAD_420, GOOD_420)
    monkeypatch.setattr(gn, "get_llm", lambda **k: gen())
    resp = ask("What is the punishment for cheating under Section 420 PPC?", session="tc-e1")
    _assert_no_false_denial(resp)
    assert re.search(r"seven years", resp["answer"])


def test_a_lookup_miss_for_a_provision_outside_the_table_does_not_override_its_retrieved_text(research, monkeypatch):
    # PPC 417 is not one of the lookup table's rows. A miss there is "not
    # covered by this table", never "this provision does not exist".
    research["chunks"] = [PPC_417]
    research["triage"] = ["criminal"]
    _with_real_tool(research, monkeypatch, "Section 417 PPC")
    gn, gen = _model_follows_engine(research, BAD_417, GOOD_417)
    monkeypatch.setattr(gn, "get_llm", lambda **k: gen())
    resp = ask("What is the punishment under Section 417 PPC?", session="tc-417")
    _assert_no_false_denial(resp)


def test_a_denial_the_model_writes_anyway_is_not_supported_and_not_shown(research, monkeypatch):
    # The reconciliation stops the miss reaching the model; this is the
    # backstop for a model that denies the provision on its own.
    research["chunks"] = [PPC_420]
    research["triage"] = ["criminal"]
    research["gen"] = [BAD_420]
    resp = ask("What is the punishment for cheating under Section 420 PPC?", session="tc-stubborn")
    _assert_no_false_denial(resp)
    assert "could not produce a verified answer" in resp["answer"]
    assert all(c.get("removed_from_answer") for c in resp["claims"] if DENIAL.search(c.get("text", "")))


# ── Phase 2: the tool's structured outcomes ──────────────────────────────────

from app.ai import tool_contract as T  # noqa: E402


def _ids(r):
    return [f"{m['law']}:{m['section']}" for m in r.get("matches", [])]


@pytest.mark.parametrize("query,outcome,ids", [
    ("Section 420 PPC", "found", ["PPC:420"]),
    ("What is the punishment for cheating under Section 420 PPC?", "found", ["PPC:420"]),
    ("s.489-F PPC", "found", ["PPC:489-F"]),
    ("489‑F PPC", "found", ["PPC:489-F"]),            # non-breaking hyphen
    ("Section 302 PPC", "found", ["PPC:302"]),
    ("پی پی سی دفعہ 302", "found", ["PPC:302"]),  # Urdu "PPC dafa 302"
    ("dafa 302 PPC", "found", ["PPC:302"]),
    ("302", "found", ["PPC:302"]),                         # bare number: the old search path
    ("qatl-e-amd", "found", ["PPC:302"]),
])
def test_explicit_references_resolve_to_their_table_row(query, outcome, ids):
    r = find_offence_sections.invoke({"query": query})
    assert r["outcome"] == outcome
    assert _ids(r) == ids
    assert "error" not in r


def test_489_is_never_confused_with_489_f():
    r = find_offence_sections.invoke({"query": "Section 489 PPC"})
    assert r["outcome"] == "not_in_table"
    assert "PPC:489-F" not in _ids(r)


def test_an_unknown_section_is_outside_the_table_not_nonexistent():
    r = find_offence_sections.invoke({"query": "Section 999 PPC"})
    assert r["outcome"] == "not_in_table" and r["not_in_table"] is True
    assert "error" not in r and "matches" not in r
    assert "NOT evidence that the provision does not exist" in r["note"]


def test_a_statute_mismatch_names_where_the_section_does_exist():
    r = find_offence_sections.invoke({"query": "Section 20 PPC"})
    assert r["outcome"] == "not_in_table"
    assert r["section_found_under"] == ["PECA 2016"]
    assert "matches" not in r                               # never PECA's offence for a PPC question


def test_a_colloquial_offence_stays_ambiguous():
    r = find_offence_sections.invoke({"query": "fraud"})
    assert r["outcome"] == "ambiguous" and r["ambiguous"] is True
    assert set(_ids(r)) == {"PPC:406", "PPC:420", "PPC:468"}


def test_a_named_section_split_into_sub_clauses_is_resolved_to_its_own_rows():
    r = find_offence_sections.invoke({"query": "Section 337-A PPC"})
    assert r["outcome"] in ("found", "ambiguous")
    assert _ids(r) and all(i.startswith("PPC:337-A") for i in _ids(r))


def test_a_lookup_failure_is_an_error_outcome(monkeypatch):
    from app.services import bail_checker

    def boom(*a, **k):
        raise RuntimeError("table unavailable")
    monkeypatch.setattr(bail_checker, "rows_for_reference", boom)
    r = find_offence_sections.invoke({"query": "Section 420 PPC"})
    assert r["outcome"] == "error" and "error" in r


def test_bail_check_is_unchanged_for_a_found_offence():
    from app.ai.tools.legal_tools import check_bail_eligibility
    r = check_bail_eligibility.invoke({"law": "PPC", "section": "420"})
    assert r["found"] is True and r["offence"]["section"] == "420"
    assert "if_already_arrested" in r["guidance"]


# ── Phase 3: reconciliation, the claim guard, the answer backstop ────────────

EV_420 = {"id": "1", "kind": "statute", "statute": "PPC 1860", "section": "420", "content": PPC_420["content"]}
EV_417 = {"id": "2", "kind": "statute", "statute": "PPC 1860", "section": "417", "content": PPC_417["content"]}
MISS = {"tool": "find_offence_sections", "args": {"query": "Section 420 PPC"},
        "result": {"error": "No offence matched 'Section 420 PPC'."}}          # the live E1 payload (legacy shape)


def test_a_lookup_miss_is_superseded_by_the_exact_source_and_recorded():
    kept, conflicts = T.reconcile([MISS], [PPC_420])
    assert kept == []
    assert conflicts == [{"tool": "find_offence_sections", "outcome": "error", "provisions": ["Section 420 PPC"],
                          "resolution": "lookup_miss_superseded_by_exact_source"}]


def test_a_miss_is_kept_when_no_source_is_that_provision():
    # PPC 417's text does not open with "420." -- it is not Section 420.
    kept, conflicts = T.reconcile([MISS], [PPC_417])
    assert kept == [MISS] and conflicts == []


def test_a_successful_result_is_never_dropped():
    found = {"tool": "find_offence_sections", "args": {"query": "Section 420 PPC"},
             "result": find_offence_sections.invoke({"query": "Section 420 PPC"})}
    bail = {"tool": "check_bail_eligibility", "args": {"law": "PPC", "section": "420"},
            "result": {"found": False, "error": "x"}}                       # bail misses are not identification
    kept, conflicts = T.reconcile([found, bail], [PPC_420])
    assert kept == [found, bail] and conflicts == []


def test_a_not_found_claim_is_unsupported_when_its_source_is_that_provision():
    claims = [{"text": "No offence matching Section 420 PPC was found.", "support": "supported", "source_ids": ["1"]},
              {"text": "Section 420 PPC is punishable with up to seven years.", "support": "supported",
               "source_ids": ["1"]},
              {"text": "Section 999 PPC could not be found.", "support": "supported", "source_ids": ["1"]}]
    out = T.false_denial_claims(claims, [EV_420])
    assert [c["support"] for c in out] == ["unsupported", "supported", "supported"]
    assert "contradicts" in out[0]["support_reason"]


def test_the_answer_backstop_names_only_provisions_whose_text_is_in_evidence():
    answer = ("Section 420 PPC does not exist in the code. Section 417 PPC is the general offence. "
              "No evidence was found of intent.")
    assert T.contradicted_provisions(answer, [EV_420, EV_417]) == ["Section 420 PPC"]
    assert T.contradicted_provisions("Section 420 PPC does not exist.", [EV_417]) == []
    urdu = "دفعہ 420 تعزیرات پاکستان نہیں ملی۔"
    assert T.contradicted_provisions(urdu, [EV_420]) == ["Section 420 PPC"]


def test_the_conflict_answer_is_not_itself_a_denial():
    for urdu in (False, True):
        assert T.contradicted_provisions(T.conflict_answer(["Section 420 PPC"], urdu), [EV_420]) == []


def test_legacy_payloads_are_read_by_their_old_shape():
    assert T.outcome_of({"error": "x"}) == "error"
    assert T.outcome_of({"found": False}) == "not_in_table"
    assert T.outcome_of({"matches": [], "ambiguous": False}) is None
    assert T.outcome_of("text") is None


def test_provenance_records_the_outcome_and_the_superseded_miss():
    from app.services import provenance_service
    state = {"tool_results": [MISS], "tool_conflicts": [
        {"tool": "find_offence_sections", "outcome": "error", "provisions": ["Section 420 PPC"],
         "resolution": "lookup_miss_superseded_by_exact_source"}]}
    entry = provenance_service._tool_evidence(state)[0]
    assert entry["outcome"] == "error" and entry["superseded_by_source"] is True


def test_e1_uses_the_found_lookup_and_cites_section_420(research, monkeypatch):
    research["chunks"] = [PPC_420]
    research["triage"] = ["criminal"]
    _with_real_tool(research, monkeypatch, "Section 420 PPC")
    gn, gen = _model_follows_engine(research, BAD_420, GOOD_420)
    monkeypatch.setattr(gn, "get_llm", lambda **k: gen())
    resp = ask("What is the punishment for cheating under Section 420 PPC?", session="tc-e1b")
    assert research["tool_out"]["outcome"] == "found"
    assert "OVERRIDES anything in the retrieved text" not in " ".join(research["gen_calls"][-1][0]["content"].split())
    assert ("420", "matched") in {(c.get("section"), c.get("status")) for c in resp["citations"]}
    assert resp["claims"] and all(c["support"] == "supported" for c in resp["claims"])


def test_a_miss_superseded_by_its_source_never_reaches_the_prompt(research, monkeypatch):
    # PPC 417 is outside the table: the lookup misses, the source supersedes it.
    research["chunks"] = [PPC_417]
    research["triage"] = ["criminal"]
    _with_real_tool(research, monkeypatch, "Section 417 PPC")
    gn, gen = _model_follows_engine(research, BAD_417, GOOD_417, miss_marker="not_in_table")
    monkeypatch.setattr(gn, "get_llm", lambda **k: gen())
    resp = ask("What is the punishment under Section 417 PPC?", session="tc-417b")
    assert research["tool_out"]["outcome"] == "not_in_table"
    assert "not_in_table" not in research["prompt"]
    assert "one year" in resp["answer"]


def test_research_flag_off_keeps_the_previous_rider(research, monkeypatch):
    # Rollback: with the flag off, research generation is exactly as before.
    # (The tool itself now finds 420 either way -- a shared lookup bug fix.)
    from app.core.config import settings
    monkeypatch.setattr(settings, "research_answer_safeguards", False)
    research["chunks"] = [PPC_420]
    research["triage"] = ["criminal"]
    _with_real_tool(research, monkeypatch, "Section 420 PPC")
    gn, gen = _model_follows_engine(research, BAD_420, GOOD_420)
    monkeypatch.setattr(gn, "get_llm", lambda **k: gen())
    ask("What is the punishment for cheating under Section 420 PPC?", session="tc-off")
    assert "OVERRIDES anything in the retrieved text" in " ".join(research["gen_calls"][-1][0]["content"].split())


def test_the_judge_stage_itself_never_supports_a_denial_of_a_provision_in_evidence(monkeypatch):
    # Defence in depth: the finalizer backstop would also catch this, so it is
    # (Terse "Section 420 PPC carries up to seven years" is withdrawn by the
    # existing period guard -- no shared subject term; reported, out of scope.)
    # checked at the judge node directly, with an over-trusting judge.
    import asyncio

    from app.ai.nodes import hallucination_node as hn

    class _Judge:
        def invoke(self, messages):
            return hn.GroundingOutput(is_grounded=True, reason="ok", claim_support="1:supported,2:supported")
    monkeypatch.setattr(hn, "get_structured_llm", lambda *a, **k: _Judge())
    state = {"surface": "client", "language": "en",
             "answer": ("No offence matching Section 420 PPC was found [1]. Section 420 PPC is punishable with "
                        "imprisonment which may extend to seven years [1]."),
             "generation_evidence": [EV_420], "reranked_chunks": [PPC_420], "tool_results": []}
    out = asyncio.run(hn.hallucination_node(state))
    support = [c["support"] for c in out["claim_assessments"]]
    assert support == ["unsupported", "supported"]


@pytest.mark.parametrize("text", ["Order XXXIX Rule 1 CPC", "Order VII Rule 11 CPC", "O. 39 r. 1 CPC",
                                  "Article 58 CPC", "Order XXX Rule 5 CPC"])
def test_an_order_rule_or_article_is_never_read_as_a_section(text):
    # The compact-form rewrite ("302 PPC") must not turn "Rule 1 CPC" into
    # CPC section 1 -- the confusion the identity index exists to prevent.
    assert T.provision_refs(text) == []


def test_issue_relevance_accepts_the_provision_the_question_names():
    # Live eval A4: "Punishment for 420 PPC?" -- "punishment" does not
    # stem-match "punished", and PPC 420's own text was ruled irrelevant.
    from app.ai import issue_relevance
    claims = [{"text": "Section 420 carries up to seven years and fine [1].", "support": "supported",
               "source_ids": ["1"]}]
    out = issue_relevance.downgrade(claims, [EV_420], "Punishment for 420 PPC?")
    assert out[0]["support"] == "supported"
    # ...while an unrelated source still gets no such pass.
    lra = {"id": "3", "kind": "statute", "statute": "Punjab Land Revenue Act 1967", "section": "91",
           "content": "91. Remedy when liability for an arrear is denied: a person paying an arrear under protest."}
    claims = [{"text": "Section 91 gives a remedy [3].", "support": "supported", "source_ids": ["3"]}]
    out = issue_relevance.downgrade(claims, [lra], "Punishment for 420 PPC?")
    assert out[0]["support"] == "unassessed"


# ── found by the full ON evals (2026-10-14) ─────────────────────────────────

def test_a_true_statement_listing_sections_is_not_a_denial_of_them():
    # Live eval E11: the backstop withheld a TRUE answer. The sentence says
    # what the listed sections do not contain; it denies none of them.
    s = ("*No provision on pre-emption time limits is found in the supplied sections (Punjab Land Revenue "
         "Act 1967 \u00a775; Punjab Tenancy Act 1887 \u00a724; Punjab Consumer Protection Act 2005 \u00a728).*")
    assert T._denied_refs(s) == []
    assert T._denied_refs("No evidence was found that Section 420 PPC applies here.") == []
    assert [r.key for r in T._denied_refs("I couldn't find the text of Section 337-A PPC.")] == [("PPC", "337-A")]


def test_ocr_split_lettered_headings_are_recognised_without_confusing_letters():
    # Live eval E4: PPC 337-A's own chunk was in evidence, and the answer said
    # "couldn't find the text of Section 337-A" -- its heading is OCR-split.
    from app.ai import exact_provision
    ref = T.provision_refs("Section 337-A PPC")[0]
    split = {"statute": "PPC 1860", "content": "337- Punishment of shajjah: \nA. Whoever, by doing any act ..."}
    spaced = {"statute": "PPC 1860", "content": "120- A Definition of criminal conspiracy: When two or more ..."}
    joined = {"statute": "PPC 1860", "content": "138-A Application of foregoing sections to the Marine ..."}
    assert exact_provision.is_exact(split, ref)
    assert exact_provision.is_exact(spaced, T.provision_refs("Section 120-A PPC")[0])
    assert exact_provision.is_exact(joined, T.provision_refs("Section 138-A PPC")[0])
    # A later line starting "C." does not make 86-A into 86-C; 489 is never 489-F.
    other = {"statute": "CrPC 1898", "content": "86-A. Procedure for removal in custody to Tribal Areas.\nC. ..."}
    assert not exact_provision.is_exact(other, T.provision_refs("Section 86-C CrPC")[0])
    assert not exact_provision.is_exact(spaced, T.provision_refs("Section 120-B PPC")[0])
    assert not exact_provision.is_exact({"statute": "PPC 1860", "content": "489- F Dishonestly issuing ..."},
                                        T.provision_refs("Section 489 PPC")[0])
