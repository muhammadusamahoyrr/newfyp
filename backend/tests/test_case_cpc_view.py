"""Legacy lawyer case summaries and the withheld risk rating (batch 7, 2026-10-16).

1. A case converted before the CPC jurisdiction check carries an `ai_summary`
   written with the Punjab-only CPC in view. Every case leaving the API goes
   through case_service._public_case, and the drafter's case context is built
   from its output. A legacy non-Punjab summary is shown with CPC citations cut
   AND an explicit warning first -- never as "fully sanitised". Records are
   never rewritten.
2. A non-Punjab intake analysis whose risk rating was made with the CPC in view
   does not present that rating: `risk_level` null (what every existing reader
   treats as "no rating"), `risk_level_basis` "not_assessed_cpc_jurisdiction",
   the model's value kept as `risk_level_withheld` for audit only.

Read through the real read paths (get_case, list_cases, get_intake,
_run_intake_ai, build_case_context) with the repositories, the graph and the
model stubbed. No store, no model, no MongoDB.
"""
from __future__ import annotations

import asyncio
import copy
import json
from types import SimpleNamespace

import pytest

from app.ai import source_currency as sc
from app.services import case_service, intake_service as svc
from app.services.case_context import build_case_context

LEGACY_SUMMARY = ("The tenant paid Rs. 50,000 on 3 March and was locked out. The plaint can be rejected under "
                  "Order VII Rule 11 CPC because it discloses no cause of action.")
PARAPHRASE = "The tenant was locked out; the court can reject a plaint that shows no cause of action."


def case(**over):
    c = {"_id": "c1", "client_id": "u1", "lawyer_id": "l1", "province": "sindh", "status": "active",
         "case_type": "civil", "description": "My landlord locked my shop.", "ai_summary": LEGACY_SUMMARY,
         "ai_summary_localized": {"ur": "کرایہ دار نے رقم ادا کی۔ آرڈر 7 رول 11 ضابطہ دیوانی کے تحت مقدمہ مسترد ہو سکتا ہے۔"},
         "ai_actions_localized": {"ur": ["آرڈر 7 رول 11 ضابطہ دیوانی کے تحت درخواست دیں۔", "رسیدیں محفوظ رکھیں۔"]}}
    c.update(over)
    return c


# ── 1. the case summary, through the real read paths ───────────────────────

@pytest.fixture
def repos(monkeypatch):
    store = {"c1": case()}

    async def find_by_id(cid):
        return store.get(cid)

    async def by_lawyer(uid, page, size, status=None):
        items = [c for c in store.values() if c.get("lawyer_id") == uid]
        return SimpleNamespace(items=items, total=len(items), page=1, page_size=size, pages=1)

    async def user(uid):
        return {"_id": uid, "full_name": "Client", "email": "c@example.com"}

    async def users(q):
        return []
    monkeypatch.setattr(case_service.case_repo, "find_by_id", find_by_id)
    monkeypatch.setattr(case_service.case_repo, "find_by_lawyer", by_lawyer)
    monkeypatch.setattr(case_service.user_repo, "find_by_id", user)
    monkeypatch.setattr(case_service.user_repo, "find_many", users)
    return store


def _get(role="lawyer", uid="l1"):
    return asyncio.run(case_service.get_case("c1", uid, role))


@pytest.mark.parametrize("province, where", [("sindh", "Sindh"), ("kpk", "Khyber Pakhtunkhwa"),
                                             ("balochistan", "Balochistan"), ("federal", "Islamabad / federal"),
                                             (None, "your province")])
def test_a_legacy_non_punjab_summary_is_shown_with_its_warning_first(repos, province, where):
    repos["c1"]["province"] = province
    pristine = copy.deepcopy(repos["c1"])
    out = _get()
    assert out["ai_summary"].startswith("Jurisdiction warning:") and where in out["ai_summary"]
    assert "Order VII Rule 11" not in out["ai_summary"] and "Rs. 50,000 on 3 March" in out["ai_summary"]
    j = out["ai_summary_jurisdiction"]
    assert j["status"] == "legacy_unverified" and j["cpc_citations_removed"] == 1
    assert out["ai_summary_localized"]["ur"].startswith("دائرۂ اختیار کی تنبیہ")
    assert "آرڈر 7 رول 11" not in out["ai_summary_localized"]["ur"]
    assert all("آرڈر 7 رول 11" not in a for a in out["ai_actions_localized"]["ur"])
    assert repos["c1"] == pristine                                    # the record is never rewritten


def test_a_paraphrased_legacy_summary_is_warned_not_claimed_clean(repos):
    repos["c1"]["ai_summary"] = PARAPHRASE
    out = _get()
    assert out["ai_summary_jurisdiction"]["cpc_citations_removed"] == 0
    assert out["ai_summary"].startswith("Jurisdiction warning:") and "may still reflect" in out["ai_summary"]


def test_a_punjab_legacy_summary_is_shown_as_written(repos):
    repos["c1"]["province"] = "punjab"
    out = _get()
    assert out["ai_summary"] == LEGACY_SUMMARY and "ai_summary_jurisdiction" not in out


def test_a_summary_written_after_the_check_is_not_called_legacy(repos):
    repos["c1"].update(ai_summary="The tenant paid Rs. 50,000.", ai_summary_cpc_checked=sc.INTAKE_CPC_VERSION)
    out = _get()
    assert out["ai_summary"] == "The tenant paid Rs. 50,000." and out["ai_summary_jurisdiction"]["status"] == "checked"
    repos["c1"].pop("ai_summary_cpc_checked")
    repos["c1"]["ai_summary"] = "Summary.\n\n" + sc.NOTICE_MARK_EN + ": our law library holds only the Punjab version."
    assert _get()["ai_summary_jurisdiction"]["status"] == "checked"


def test_the_client_and_the_case_list_see_the_same_view(repos):
    assert _get(role="client", uid="u1")["ai_summary"].startswith("Jurisdiction warning:")
    listed = asyncio.run(case_service.list_cases("l1", "lawyer", 1, 20))["items"][0]
    assert listed["ai_summary"].startswith("Jurisdiction warning:")


def test_the_drafters_case_context_keeps_the_warning_even_when_capped(repos):
    repos["c1"]["ai_summary"] = LEGACY_SUMMARY + " Further detail." * 300          # far past the 1,500 cap
    ctx = build_case_context(_get())
    assert ctx["summary"].startswith("Jurisdiction warning:") and "not verified for Sindh" in ctx["summary"]


def test_new_conversions_record_the_check():
    import inspect
    src = inspect.getsource(svc)
    assert src.count('"ai_summary_cpc_checked": _cpc_version(),') == 2           # conversion AND retry-analysis


# ── 2. the risk rating ──────────────────────────────────────────────────────

def mixed_analysis(**over):
    a = {"summary": "The tenant paid Rs. 50,000. The plaint can be rejected under Order VII Rule 11 CPC.",
         "grounding_status": "grounded", "grounded": True, "risk_level": "high", "risk_level_basis": "model_judgment",
         "law_citations": [{"statute": "CPC 1908", "section": "O7R11", "evidence_id": "1", "status": "bound"},
                           {"statute": "Specific Relief Act 1877", "section": "42", "evidence_id": "2", "status": "bound"}],
         "recommended_actions": ["Seek a declaration under Section 42 of the Specific Relief Act."],
         "recommended_action_kinds": ["legal"],
         "claim_assessments": [{"text": "Seek a declaration under Section 42 of the Specific Relief Act.",
                                "source_ids": ["2"], "support": "supported", "citation_status": "matched"}]}
    a.update(over)
    return a


@pytest.mark.parametrize("province", ["sindh", "kpk", "balochistan", "federal", None])
def test_a_rating_made_with_the_cpc_in_view_is_not_presented(province):
    a = sc.apply_intake_cpc(mixed_analysis(), province)
    assert a["risk_level"] is None and a["risk_level_withheld"] == "high"
    assert a["risk_level_basis"] == sc.RISK_NOT_ASSESSED
    # the independent, supported non-CPC content stays
    assert a["recommended_actions"] == ["Seek a declaration under Section 42 of the Specific Relief Act."]
    assert a["claim_assessments"][0]["support"] == "supported"


def test_punjab_keeps_its_rating():
    a = sc.apply_intake_cpc(mixed_analysis(), "punjab")
    assert a["risk_level"] == "high" and "risk_level_withheld" not in a


def test_a_non_punjab_analysis_without_any_cpc_keeps_its_rating():
    a = mixed_analysis(summary="The tenant paid Rs. 50,000.",
                       law_citations=[{"statute": "Specific Relief Act 1877", "section": "42", "evidence_id": "2",
                                       "status": "bound"}])
    a = sc.apply_intake_cpc(a, "sindh")
    assert a["risk_level"] == "high" and "jurisdiction_notice" not in a


@pytest.fixture
def run_intake(monkeypatch):
    from app.ai import intake_output_guard
    from app.ai.graph import supervisor

    class _Graph:
        async def ainvoke(self, state):
            a = mixed_analysis()
            return {"answer": json.dumps({k: a[k] for k in ("summary", "risk_level", "recommended_actions",
                                                             "recommended_action_kinds")}),
                    "is_grounded": True, "grounding_status": "grounded", "citations": a["law_citations"],
                    "claim_assessments": a["claim_assessments"], "evidence_gate": {"status": "supported"}}
    monkeypatch.setattr(supervisor, "intake_graph", _Graph())

    async def none(*a, **k):
        return None
    monkeypatch.setattr(svc, "_record_intake_provenance", none)

    async def same(analysis, language):
        return analysis
    monkeypatch.setattr(svc, "_with_localization", same)
    monkeypatch.setattr(intake_output_guard, "enforce", lambda a, story=None: a)
    return lambda province: asyncio.run(svc._run_intake_ai(
        query="q", case_type="civil", province=province, session_id="s", case_id="c"))


def test_a_fresh_or_retried_analysis_stores_no_presentable_rating(run_intake):
    # _run_intake_ai is the single path for conversion AND retry_analysis.
    assert run_intake("sindh")["risk_level"] is None
    assert run_intake("punjab")["risk_level"] == "high"


def test_a_stored_batch6_analysis_is_re_viewed_with_the_rule(monkeypatch):
    """A v1 record (batch 6) was edited but kept its rating; get_intake's view
    re-applies the step (version bumped) and withholds it, on a copy."""
    v1 = sc.apply_intake_cpc(mixed_analysis(), "sindh")
    v1.update(risk_level="high", risk_level_basis="model_judgment",
              cpc_jurisdiction={**v1["cpc_jurisdiction"], "version": "intake-cpc-jurisdiction-v1"})
    v1.pop("risk_level_withheld", None)
    rec = {"session_token": "t", "client_id": "u1", "case_id": "c1", "completed": True,
           "step1": {"province": "sindh"}, "ai_structured_case": v1}
    pristine = copy.deepcopy(rec)

    async def by_token(t):
        return rec

    async def case_by_id(cid):
        return {"_id": "c1", "status": "submitted", "case_type": "civil", "province": "sindh"}
    monkeypatch.setattr(svc.intake_repo, "find_by_token", by_token)
    monkeypatch.setattr(svc.case_repo, "find_by_id", case_by_id)
    shown = asyncio.run(svc.get_intake("t", "u1"))["ai_structured_case"]
    assert shown["risk_level"] is None and shown["risk_level_basis"] == sc.RISK_NOT_ASSESSED
    assert rec == pristine


# ── mutation ────────────────────────────────────────────────────────────────

def _fails(fn, *a, **k):
    with pytest.raises((AssertionError, KeyError, TypeError, pytest.fail.Exception)):
        fn(*a, **k)


def test_mutant_without_the_case_view(repos, monkeypatch):
    monkeypatch.setattr(sc, "case_cpc_view", lambda c: c)
    _fails(test_a_legacy_non_punjab_summary_is_shown_with_its_warning_first, repos, "sindh", "Sindh")


def test_mutant_that_calls_a_paraphrase_clean(repos, monkeypatch):
    real = sc.legacy_case_warning
    monkeypatch.setattr(sc, "legacy_case_warning", lambda p, s: {**real(p, s), "en": "Checked and cleaned."})
    _fails(test_a_paraphrased_legacy_summary_is_warned_not_claimed_clean, repos)


def test_mutant_with_the_warning_last(repos, monkeypatch):
    real = sc.case_cpc_view

    def last(c):
        out = real(c)
        if out.get("ai_summary_jurisdiction", {}).get("status") == "legacy_unverified":
            w = out["ai_summary_jurisdiction"]["warning"]["en"]
            out["ai_summary"] = out["ai_summary"].replace(w + "\n\n", "") + "\n\n" + w
        return out
    monkeypatch.setattr(sc, "case_cpc_view", last)
    _fails(test_the_drafters_case_context_keeps_the_warning_even_when_capped, repos)


def test_mutant_without_the_risk_rule(monkeypatch):
    real = sc.apply_intake_cpc

    def keep(a, *x, **k):
        risk = a.get("risk_level")
        out = real(a, *x, **k)
        out["risk_level"] = risk
        return out
    monkeypatch.setattr(sc, "apply_intake_cpc", keep)
    _fails(test_a_rating_made_with_the_cpc_in_view_is_not_presented, "sindh")


def test_mutant_that_ignores_the_conversion_marker(repos, monkeypatch):
    monkeypatch.setattr(sc, "CASE_CPC_MARK", "no_such_field")
    _fails(test_a_summary_written_after_the_check_is_not_called_legacy, repos)
