"""Fail-closed AI summaries, document extraction input, lawyer-matching evidence (batch 8, 2026-10-17).

1. If the CPC jurisdiction view of a case cannot run, the case is still served
   but NO AI summary text (English, Urdu, Urdu actions) leaves the API as if it
   were checked: `ai_summary` null, status "review_unavailable" with a warning.
2. Document field extraction never feeds the model an AI summary written
   before the CPC jurisdiction check in a non-Punjab / unknown-province case,
   nor one whose check failed: it stops with an actionable 422. The client's
   own description is always preferred.
3. Lawyer matching: the province and case-type filters come from the case
   record, not the summary; the summary is only similarity text (evidence for
   leaving the behaviour unchanged).

Read through the real `get_case`, `list_cases`, `build_case_context`,
`extract_fields` and `match_lawyers_for_case`, with repositories and the model
stubbed. No store, no model, no MongoDB.
"""
from __future__ import annotations

import asyncio
import copy
from types import SimpleNamespace

import pytest

from app.ai import source_currency as sc
from app.core.exceptions import AppValidationError
from app.services import case_service, document_service, lawyer_service
from app.services.case_context import build_case_context

LEGACY = ("The tenant paid Rs. 50,000 on 3 March. The plaint can be rejected under Order VII Rule 11 CPC "
          "because it discloses no cause of action.")


def case(**over):
    c = {"_id": "c1", "case_number": "ATT-1", "client_id": "u1", "lawyer_id": "l1", "province": "sindh",
         "status": "active", "case_type": "civil", "description": "My landlord locked my shop.",
         "ai_summary": LEGACY, "ai_summary_localized": {"ur": "آرڈر 7 رول 11 ضابطہ دیوانی"},
         "ai_actions_localized": {"ur": ["آرڈر 7 رول 11 کے تحت درخواست دیں۔"]}}
    c.update(over)
    return c


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
    for mod in (case_service, document_service, lawyer_service):
        if hasattr(mod, "case_repo"):
            monkeypatch.setattr(mod.case_repo, "find_by_id", find_by_id)
    monkeypatch.setattr(case_service.case_repo, "find_by_lawyer", by_lawyer)
    monkeypatch.setattr(case_service.user_repo, "find_by_id", user)
    monkeypatch.setattr(case_service.user_repo, "find_many", users)
    return store


def _boom(*a, **k):
    raise RuntimeError("view broke")


def _get():
    return asyncio.run(case_service.get_case("c1", "l1", "lawyer"))


# ── 1. fail-closed case view ────────────────────────────────────────────────

@pytest.mark.parametrize("province", ["sindh", "punjab", None])
def test_a_failed_view_never_releases_the_raw_summary(repos, monkeypatch, province):
    repos["c1"]["province"] = province
    pristine = copy.deepcopy(repos["c1"])
    monkeypatch.setattr(sc, "case_cpc_view", _boom)
    out = _get()
    assert out["case_number"] == "ATT-1" and out["description"] == "My landlord locked my shop."   # still accessible
    assert out["ai_summary"] is None
    assert "ai_summary_localized" not in out and "ai_actions_localized" not in out
    j = out["ai_summary_jurisdiction"]
    assert j["status"] == sc.REVIEW_UNAVAILABLE and "withheld" in j["warning"]["en"] and j["warning"]["ur"]
    assert repos["c1"] == pristine


def test_a_view_that_fails_half_way_still_releases_nothing(repos, monkeypatch):
    def half(c):
        c["ai_summary"] = "PARTLY EDITED " + c["ai_summary"]
        raise RuntimeError("after the first edit")
    monkeypatch.setattr(sc, "case_cpc_view", half)
    out = _get()
    assert out["ai_summary"] is None and out["ai_summary_jurisdiction"]["status"] == sc.REVIEW_UNAVAILABLE


def test_the_case_list_and_the_drafters_context_fail_closed_too(repos, monkeypatch):
    monkeypatch.setattr(sc, "case_cpc_view", _boom)
    listed = asyncio.run(case_service.list_cases("l1", "lawyer", 1, 20))["items"][0]
    assert listed["ai_summary"] is None and listed["ai_summary_jurisdiction"]["status"] == sc.REVIEW_UNAVAILABLE
    ctx = build_case_context(_get())
    assert ctx["summary"] == "My landlord locked my shop."          # the client's own words, not the AI summary
    assert "Order VII" not in ctx["summary"]


def test_a_case_without_an_ai_summary_is_untouched_by_a_failure(repos, monkeypatch):
    for k in ("ai_summary", "ai_summary_localized", "ai_actions_localized"):
        repos["c1"].pop(k)
    monkeypatch.setattr(sc, "case_cpc_view", _boom)
    assert "ai_summary_jurisdiction" not in _get()


def test_without_a_failure_the_batch7_view_is_unchanged(repos):
    out = _get()
    assert out["ai_summary"].startswith("Jurisdiction warning:")
    assert out["ai_summary_jurisdiction"]["status"] == "legacy_unverified"


# ── 2. document field extraction: what the model would be given ────────────

@pytest.fixture
def extract(monkeypatch, repos):
    seen = {"calls": []}

    class _LLM:
        def invoke(self, messages):
            seen["calls"].append(messages)
            return SimpleNamespace(content='{"facts": "x"}')
    monkeypatch.setattr("app.ai.llm.get_llm", lambda **k: _LLM())

    def go(**over):
        repos["c1"].update(over)
        seen["calls"].clear()
        return asyncio.run(document_service.extract_fields("c1", "u1", "plaint_civil"))
    go.seen = seen
    return go


def _model_input(seen):
    return seen["calls"][-1][-1]["content"]


@pytest.mark.parametrize("province", ["sindh", "kpk", "balochistan", "federal", None])
def test_a_legacy_non_punjab_summary_is_never_given_to_the_model(extract, province):
    with pytest.raises(AppValidationError) as exc:
        extract(description="", province=province)
    assert exc.value.status_code == 422
    assert "written before the Code of Civil Procedure jurisdiction check" in exc.value.detail
    assert "Add the case facts to the case description" in exc.value.detail
    assert extract.seen["calls"] == []


def test_a_failed_check_stops_extraction_too(extract, monkeypatch):
    monkeypatch.setattr(sc, "case_cpc_view", _boom)
    with pytest.raises(AppValidationError) as exc:
        extract(description="")
    assert "could not run" in exc.value.detail and extract.seen["calls"] == []


def test_a_confirmed_punjab_summary_may_be_used(extract):
    extract(description="", province="punjab")
    assert "Order VII Rule 11 CPC" in _model_input(extract.seen)


def test_a_checked_non_punjab_summary_is_used_without_its_notice(extract):
    summary = ("The tenant paid Rs. 50,000 on 3 March.\n\n" + sc.NOTICE_MARK_EN
               + ": our law library holds only the Punjab version of the CPC.")
    extract(description="", ai_summary=summary, ai_summary_cpc_checked=sc.INTAKE_CPC_VERSION)
    text = _model_input(extract.seen)
    assert "Rs. 50,000 on 3 March" in text and sc.NOTICE_MARK_EN not in text


def test_the_clients_own_description_is_always_preferred(extract):
    extract(description="My landlord locked my shop on 2 March.")
    text = _model_input(extract.seen)
    assert "locked my shop on 2 March" in text and "Order VII" not in text


def test_no_description_and_no_summary_keeps_the_old_message(extract):
    with pytest.raises(AppValidationError) as exc:
        extract(description="", ai_summary=None)
    assert "no description to extract fields from" in exc.value.detail


# ── 3. lawyer matching: evidence for leaving it unchanged ──────────────────

def test_matching_filters_on_the_case_province_and_type_not_on_the_summary(repos, monkeypatch):
    """A legacy summary that even NAMES Punjab and the CPC does not move the
    jurisdiction filters: both pools are asked for the CASE's province and
    type. The summary is only the similarity text (limitation, documented)."""
    repos["c1"].update(description="", province="sindh",
                       ai_summary="Under the Punjab CPC, Order VII Rule 11 lets the court reject the plaint.")
    seen = {}

    async def semantic(query_text, province, limit):
        seen["semantic"] = (query_text, province)
        return {}

    async def mongo_pool(**kw):
        seen["mongo"] = (kw.get("province"), kw.get("case_type"))
        return SimpleNamespace(items=[], total=0)

    async def listing(province, top_n):
        seen["listing"] = province
        return None
    monkeypatch.setattr(lawyer_service, "_semantic_candidates", semantic)
    monkeypatch.setattr(lawyer_service.user_repo, "find_lawyers", mongo_pool)
    monkeypatch.setattr(lawyer_service, "_general_listing", listing)
    asyncio.run(lawyer_service.match_lawyers_for_case("c1"))
    assert seen["semantic"][1] == "sindh" and seen["mongo"] == ("sindh", "civil")
    assert "Punjab CPC" in seen["semantic"][0]                      # the raw summary IS the similarity text


# ── mutation ────────────────────────────────────────────────────────────────

def _fails(fn, *a, **k):
    with pytest.raises((AssertionError, KeyError, TypeError, pytest.fail.Exception)):
        fn(*a, **k)


def test_mutant_fail_open_again(repos, monkeypatch):
    monkeypatch.setattr(sc, "case_summary_unavailable", lambda c: c)
    _fails(test_a_failed_view_never_releases_the_raw_summary, repos, monkeypatch, "sindh")


def test_mutant_that_feeds_the_raw_summary_to_extraction(extract, monkeypatch):
    monkeypatch.setattr(sc, "summary_for_model_input", lambda c: c.get("ai_summary"))
    _fails(test_a_legacy_non_punjab_summary_is_never_given_to_the_model, extract, "sindh")


def test_mutant_that_ignores_a_failed_check_in_extraction(extract, monkeypatch):
    real = sc.summary_for_model_input

    def lenient(c):
        try:
            return real(c)
        except sc.SummaryUnusable:
            return c.get("ai_summary")
    monkeypatch.setattr(sc, "summary_for_model_input", lenient)
    _fails(test_a_failed_check_stops_extraction_too, extract, monkeypatch)
