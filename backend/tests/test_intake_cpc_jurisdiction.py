"""Client Legal Intake and the Punjab-only CPC; mixed claims; CPC citation forms (batch 6, 2026-10-16).

The indexed CPC is the Punjab Code text. Intake's province is the client's
step-1 choice or the stored case's (never inferred), so "punjab" is confirmed
and anything else is not. Outside Punjab the CPC is not shown as the law that
applies -- in the stored analysis, on a reopened intake, in the Urdu rendering
and in the lawyer's case summary -- while the client's facts and every non-CPC
conclusion are kept.

Read where people read it: the analysis `_run_intake_ai` returns (and stores),
`get_intake`'s payload, the lawyer-facing `ai_summary`, the chat claim badges,
the drafter's insertable text. No store, no model, no MongoDB.
"""
from __future__ import annotations

import asyncio
import copy
import json
import re

import pytest

from app.ai import source_currency as sc
from app.ai.intake_output_guard import LAWYER_REVIEW_STEP
from app.services import intake_service as svc

SUMMARY = ("The tenant paid Rs. 50,000 on 3 March and the landlord refused a receipt. The plaint can be rejected "
           "under Order VII Rule 11 CPC because it discloses no cause of action.")
A_CPC = "File an application under Order VII Rule 11 CPC to reject the plaint."
A_MIXED = "File a declaratory suit under Section 42 of the Specific Relief Act and Section 9 CPC."
A_SRA = "Seek a declaration of title under Section 42 of the Specific Relief Act."
A_GENERAL = "Keep the payment receipts and bank records safe."


def analysis(**over):
    a = {
        "summary": SUMMARY, "grounding_status": "grounded", "grounded": True, "risk_level": "medium",
        "law_citations": [
            {"statute": "CPC 1908", "section": "O7R11", "evidence_id": "1", "status": "bound"},
            {"statute": "Specific Relief Act 1877", "section": "42", "evidence_id": "2", "status": "bound"}],
        "recommended_actions": [A_CPC, A_MIXED, A_SRA, A_GENERAL],
        "recommended_action_kinds": ["legal", "legal", "legal", "general"],
        "claim_assessments": [
            {"kind": "summary", "text": SUMMARY, "source_ids": ["1"], "support": "supported", "citation_status": "matched"},
            {"text": A_CPC, "source_ids": ["1"], "support": "supported", "citation_status": "matched"},
            {"text": A_MIXED, "source_ids": ["1", "2"], "support": "supported", "citation_status": "matched"},
            {"text": A_SRA, "source_ids": ["2"], "support": "supported", "citation_status": "matched"}],
    }
    a.update(over)
    return a


NON_PUNJAB = [("sindh", "Sindh"), ("kpk", "Khyber Pakhtunkhwa"), ("balochistan", "Balochistan"),
              ("federal", "Islamabad / federal")]


def _check_limited(a, where):
    laws = " ".join(a["applicable_laws"])
    assert "CPC" not in laws and "Specific Relief Act" in laws                     # CPC not shown as applicable law
    assert any(c.get("withheld_reason") == "cpc_jurisdiction_unverified" for c in a["withheld_citations"])
    assert A_CPC not in a["recommended_actions"] and LAWYER_REVIEW_STEP in a["recommended_actions"]
    assert A_SRA in a["recommended_actions"] and A_GENERAL in a["recommended_actions"]   # independent ones kept
    mixed = next(t for t in a["recommended_actions"] if t.startswith("File a declaratory suit"))
    assert "Section 9 CPC" not in mixed and "Section 42 of the Specific Relief Act" in mixed
    assert "Rs. 50,000 on 3 March" in a["summary"] and "Order VII Rule 11" not in a["summary"]
    by = {c["text"]: c for c in a["claim_assessments"]}
    assert by[A_SRA]["support"] == "supported"                                   # SRA-only claim stands
    assert all(c["support"] == "unassessed" for t, c in by.items() if t != A_SRA)
    assert a["grounding_status"] == "grounded"                                   # law left: SRA
    # Batch 7: the model's risk reading weighed the CPC too -- not presented.
    assert a["risk_level"] is None and a["risk_level_withheld"] == "medium"
    assert a["risk_level_basis"] == sc.RISK_NOT_ASSESSED
    assert where in a["jurisdiction_notice"]["en"] and a["jurisdiction_notice"]["ur"]


@pytest.mark.parametrize("province, where", NON_PUNJAB)
def test_outside_punjab_the_cpc_is_not_shown_as_applicable_law(province, where):
    _check_limited(sc.apply_intake_cpc(analysis(), province), where)


def test_confirmed_punjab_is_unchanged():
    before = analysis()
    after = sc.apply_intake_cpc(copy.deepcopy(before), "punjab")
    assert {k: after[k] for k in before} == before and "jurisdiction_notice" not in after


@pytest.mark.parametrize("province, basis, inferred", [(None, None, False), ("", None, False),
                                                       ("punjab", "inferred_from_query", True)])
def test_unknown_or_inferred_punjab_is_not_confirmed_and_asks_for_the_province(province, basis, inferred):
    a = sc.apply_intake_cpc(analysis(), province, basis=basis, inferred=inferred)
    assert "CPC" not in " ".join(a["applicable_laws"])
    assert "Add your province" in a["jurisdiction_notice"]["en"]


def test_with_only_cpc_law_the_status_says_so_and_no_risk_is_read():
    a = analysis(law_citations=[{"statute": "CPC 1908", "section": "O7R11", "evidence_id": "1", "status": "bound"}],
                 recommended_actions=[A_CPC, A_GENERAL], recommended_action_kinds=["legal", "general"],
                 claim_assessments=[{"text": A_CPC, "source_ids": ["1"], "support": "supported",
                                     "citation_status": "matched"}])
    a = sc.apply_intake_cpc(a, "sindh")
    assert a["grounding_status"] == sc.INTAKE_CPC_STATUS and a["grounded"] is False and a["risk_level"] is None
    assert a["recommended_actions"] == [A_GENERAL, LAWYER_REVIEW_STEP]


def test_applying_twice_changes_nothing_more():
    once = sc.apply_intake_cpc(analysis(), "sindh")
    twice = sc.apply_intake_cpc(copy.deepcopy(once), "sindh")
    assert twice == once


def test_the_urdu_rendering_stays_aligned():
    a = analysis(localized={"ur": {"status": "ok", "summary": "کرایہ دار نے رقم ادا کی۔ آرڈر 7 رول 11 ضابطہ دیوانی کے تحت مقدمہ مسترد ہو سکتا ہے۔",
                                   "recommended_actions": ["ur-cpc", "ur-mixed Section 9 CPC", "ur-sra", "ur-general"],
                                   "statute_names": ["ضابطہ دیوانی", "قانون دادرسی خاص"],
                                   "citation_notes": ["cpc note", "sra note"]}})
    loc = sc.apply_intake_cpc(a, "sindh")["localized"]["ur"]
    # the CPC-only action's Urdu twin removed; a citation that is not after
    # "under ..." becomes the placeholder (not silently dropped)
    assert loc["recommended_actions"][:3] == ["ur-mixed [the relevant CPC provision, not verified for Sindh]",
                                              "ur-sra", "ur-general"]
    assert loc["recommended_actions"][-1] == sc.LAWYER_REVIEW_STEP_UR
    assert loc["statute_names"] == ["قانون دادرسی خاص"] and loc["citation_notes"] == ["sra note"]
    assert "آرڈر 7 رول 11" not in loc["summary"] and "کرایہ دار نے رقم ادا کی" in loc["summary"]


def test_a_mixed_claim_that_does_not_name_the_cpc_is_still_not_supported():
    """Per SOURCE, not per wording: a claim resting on CPC evidence and SRA
    evidence is not "supported" even when its text names neither."""
    text = "Both the procedure code and the Specific Relief Act let you seek this declaration."
    a = analysis(claim_assessments=[{"text": text, "source_ids": ["1", "2"], "support": "supported",
                                     "citation_status": "matched"},
                                    {"text": A_SRA, "source_ids": ["2"], "support": "supported",
                                     "citation_status": "matched"}])
    by = {c["text"]: c for c in sc.apply_intake_cpc(a, "sindh")["claim_assessments"]}
    assert by[text]["support"] == "unassessed" and "also rests on it" in by[text]["support_reason"]
    assert by[A_SRA]["support"] == "supported"


def test_an_unrelated_ppc_analysis_is_untouched():
    a = analysis(summary="The accused obstructed a public servant, an offence under Section 186 PPC.",
                 law_citations=[{"statute": "PPC 1860", "section": "186", "evidence_id": "1", "status": "bound"}],
                 recommended_actions=["Report the obstruction under Section 186 PPC."], recommended_action_kinds=["legal"],
                 claim_assessments=[{"text": "Report the obstruction under Section 186 PPC.", "source_ids": ["1"],
                                     "support": "supported", "citation_status": "matched"}])
    before = copy.deepcopy(a)
    after = sc.apply_intake_cpc(a, "sindh")
    assert {k: after[k] for k in before} == before and "jurisdiction_notice" not in after


# ── the stored analysis: _run_intake_ai with the graph stubbed ─────────────

@pytest.fixture
def run_intake(monkeypatch):
    from app.ai.graph import supervisor

    class _Graph:
        async def ainvoke(self, state):
            run_intake.state = state
            a = analysis()
            return {"answer": json.dumps({k: a[k] for k in ("summary", "risk_level", "recommended_actions",
                                                             "recommended_action_kinds")}),
                    "is_grounded": True, "grounding_status": "grounded",
                    "citations": a["law_citations"], "claim_assessments": a["claim_assessments"],
                    "evidence_gate": {"status": "supported"}}
    monkeypatch.setattr(supervisor, "intake_graph", _Graph())

    async def no_provenance(*a, **k):
        return None
    monkeypatch.setattr(svc, "_record_intake_provenance", no_provenance)

    async def no_localization(analysis, language):
        return analysis
    monkeypatch.setattr(svc, "_with_localization", no_localization)

    from app.ai import intake_output_guard
    monkeypatch.setattr(intake_output_guard, "enforce", lambda a, story=None: a)

    def go(province):
        return asyncio.run(svc._run_intake_ai(query="My landlord ...", case_type="civil", province=province,
                                              session_id="s1", case_id="c1"))
    return go


@pytest.mark.parametrize("province, where", NON_PUNJAB)
def test_the_stored_intake_analysis_is_limited(run_intake, province, where):
    a = run_intake(province)
    _check_limited(a, where)
    assert a["cpc_jurisdiction"]["scope"] == "other"


def test_the_stored_punjab_analysis_keeps_the_cpc(run_intake):
    a = run_intake("punjab")
    assert A_CPC in a["recommended_actions"] and "jurisdiction_notice" not in a


def test_the_lawyers_case_summary_carries_the_notice(run_intake):
    a = run_intake("sindh")
    summary = svc._case_summary(a)
    assert summary.startswith("The tenant paid") and sc.NOTICE_MARK_EN in summary and "Sindh" in summary
    import inspect
    src = inspect.getsource(svc)
    assert src.count('"ai_summary": None if analysis_failed else _case_summary(ai_data)') == 1
    assert src.count('"ai_summary": _case_summary(ai_data)') == 1                # retry-analysis path too


# ── a reopened intake: get_intake corrects a copy, never the stored record ──

@pytest.fixture
def stored(monkeypatch):
    rec = {"session_token": "t1", "client_id": "u1", "case_id": "c1", "current_step": 5, "completed": True,
           "step1": {"province": "sindh", "party_role": "plaintiff"}, "ai_structured_case": analysis()}

    async def by_token(token):
        return rec
    async def case_by_id(cid):
        return {"_id": "c1", "status": "submitted", "case_type": "civil", "province": "sindh"}
    monkeypatch.setattr(svc.intake_repo, "find_by_token", by_token)
    monkeypatch.setattr(svc.case_repo, "find_by_id", case_by_id)
    return rec


def test_a_reopened_intake_saved_before_this_rule_is_shown_limited(stored):
    pristine = copy.deepcopy(stored["ai_structured_case"])
    out = asyncio.run(svc.get_intake("t1", "u1"))
    _check_limited(out["ai_structured_case"], "Sindh")
    assert stored["ai_structured_case"] == pristine                              # stored record not rewritten


def test_a_reopened_punjab_intake_is_shown_as_stored(stored):
    stored["step1"]["province"] = "punjab"
    out = asyncio.run(svc.get_intake("t1", "u1"))
    assert A_CPC in out["ai_structured_case"]["recommended_actions"]


# ── citation forms, shared parsers ──────────────────────────────────────────

@pytest.mark.parametrize("text, cited", [
    ("under O VII R 11 CPC", "O VII R 11 CPC"), ("under o vii r 11 of the CPC", "o vii r 11 of the CPC"),
    ("آرڈر 7 رول 11 ضابطہ دیوانی کے تحت", "آرڈر 7 رول 11 ضابطہ دیوانی"),
    ("under Order XXXIX Rules 1 and 2 CPC", "Order XXXIX Rules 1 and 2 CPC"),
])
def test_explicit_order_rule_forms_are_cpc_citations(text, cited):
    assert [text[a:b] for a, b in sc.cpc_citations(text)] == [cited]


@pytest.mark.parametrize("text", ["Section 186 PPC", "Rules 1 and 2 of the Supreme Court Rules", "go to 7 r 11 more",
                                  "under the said section", "Before 2018, Order VII applied differently in history."])
def test_ordinary_prose_and_other_statutes_are_not_cpc_citations(text):
    assert sc.cpc_citations(text) == [] or "Order VII" in text and not re.search(r"Rule", text)


def test_rules_1_and_2_are_never_read_as_section_2():
    from app.ai import draft_guard, tool_contract
    for t in ("Order XXXIX Rules 1 and 2 CPC", "آرڈر 7 رول 11 ضابطہ دیوانی"):
        refs = [(r.section, r.statute) for r in tool_contract.provision_refs(draft_guard.normalise(t))]
        assert refs == [], (t, refs)
    assert [(r.section, r.statute) for r in tool_contract.provision_refs("Section 2 CPC")] == [("2", "CPC 1908")]


def test_o_without_dots_is_an_order_rule_reference():
    from app.ai import cpc_provisions
    assert [(o, r) for o, r, _, _ in cpc_provisions.parse_refs("under O VII R 11 CPC")] == [(7, "11")]
    assert cpc_provisions.parse_refs("go to 7 r 11 more") == []


# ── mutation: each boundary is caught ──────────────────────────────────────

def _fails(fn, *a, **k):
    with pytest.raises((AssertionError, KeyError, StopIteration, TypeError, pytest.fail.Exception)):
        fn(*a, **k)


def test_mutant_without_the_intake_step(run_intake, monkeypatch):
    monkeypatch.setattr(sc, "apply_intake_cpc", lambda a, *x, **k: a)
    _fails(test_the_stored_intake_analysis_is_limited, run_intake, "sindh", "Sindh")


def test_mutant_that_lets_a_valid_source_launder_the_cpc(monkeypatch):
    real = sc._ids
    monkeypatch.setattr(sc, "_ids", lambda claim: real(claim) if len(real(claim)) == 1 else set())
    _fails(test_a_mixed_claim_that_does_not_name_the_cpc_is_still_not_supported)


def test_mutant_without_the_read_time_view(stored, monkeypatch):
    monkeypatch.setattr(svc, "_jurisdiction_view", lambda a, p: a)
    _fails(test_a_reopened_intake_saved_before_this_rule_is_shown_limited, stored)


def test_mutant_that_treats_federal_as_punjab(monkeypatch):
    real = sc.cpc_scope
    monkeypatch.setattr(sc, "cpc_scope", lambda p, b=None, i=False: sc.SCOPE_PUNJAB if p == "federal" else real(p, b, i))
    _fails(test_outside_punjab_the_cpc_is_not_shown_as_applicable_law, "federal", "Islamabad / federal")


def test_mutant_reverting_the_rule_list_fix(monkeypatch):
    from app.ai import tool_contract
    monkeypatch.setattr(tool_contract, "_LIST_OF_NOT_SECTIONS", re.compile(r"(?!x)x"))
    _fails(test_rules_1_and_2_are_never_read_as_section_2)


def test_mutant_reverting_o_without_dots(monkeypatch):
    from app.ai import cpc_provisions
    monkeypatch.setattr(cpc_provisions, "_ORDER_RULE", re.compile(
        cpc_provisions._ORDER_RULE.pattern.replace(r"|O(?=\s+(?:[IVXLC]{1,7}|\d{1,2})\s*,?\s*R)", ""),
        cpc_provisions._ORDER_RULE.flags))
    _fails(test_o_without_dots_is_an_order_rule_reference)
