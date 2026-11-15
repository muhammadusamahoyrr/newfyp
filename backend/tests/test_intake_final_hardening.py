"""Final intake hardening (2026-10-13): fact concepts for retrieval, the
deterministic formal-legal-action classifier, and the Urdu rendering fallback.

Offline: no Chroma, no LLM (fakes only).
"""
from __future__ import annotations

import asyncio

import pytest

from app.ai import intake_output_guard as guard
from app.ai.legal_terms import augment, legal_concepts

M001 = ("My friend gave me a cheque to repay the loan he owed me and it bounced. "
        "When I asked him for the money he threatened to kill me.")


def concepts(text):
    return [c["concept"] for c in legal_concepts(text)]


# ── Batch 1: fact concepts (retrieval vocabulary, never sections) ───────────

@pytest.mark.parametrize("text", [
    "Cheque issued to repay my loan bounced.",
    "Cheque was for repayment of an existing obligation and was dishonoured.",
    "میرے دوست نے قرض کی واپسی کے لیے چیک دیا جو باؤنس ہو گیا۔",
    "dost ne qarz wapis karne ke liye cheque diya jo bounce ho gaya",
])
def test_a_dishonoured_repayment_cheque_is_recognised(text):
    found = legal_concepts(text)
    assert [c["concept"] for c in found] == ["dishonoured_cheque"]
    assert "repayment of loan obligation" in found[0]["terms"]


@pytest.mark.parametrize("text", [
    "He threatened to kill me.",
    "اس نے مجھے جان سے مارنے کی دھمکی دی۔",
    "usne mujhe jaan se maarne ki dhamki di",
])
def test_a_death_threat_is_recognised(text):
    found = legal_concepts(text)
    assert [c["concept"] for c in found] == ["criminal_intimidation"]
    assert "threat to cause death" in found[0]["terms"]


def test_the_two_issue_story_carries_both_concepts_in_one_query():
    assert concepts(M001) == ["dishonoured_cheque", "criminal_intimidation"]
    q = augment(M001)
    assert q.startswith(M001), "the client's words are kept"
    assert "dishonoured cheque" in q and "criminal intimidation" in q
    assert not any(ch.isdigit() for ch in q[len(M001):]), "no section number is injected"


def test_an_unpaid_debt_without_a_cheque_adds_no_cheque_concept():
    assert concepts("He owes me money and has not paid it back.") == []


def test_a_cheque_without_a_stated_purpose_does_not_assume_repayment():
    found = legal_concepts("He gave me a cheque and it bounced.")
    assert [c["concept"] for c in found] == ["dishonoured_cheque"]
    assert "repayment" not in found[0]["terms"]


def test_a_broken_promise_is_not_cheating():
    assert concepts("He promised to return my money but did not.") == []
    assert "cheating" not in augment("He promised to return my money but did not.")


def test_a_bounced_cheque_alone_never_adds_cheating():
    assert "cheating" not in augment(M001)


def test_explicit_deception_may_add_cheating():
    assert concepts("He tricked me into paying for land he did not own.") == ["cheating"]


@pytest.mark.parametrize("text", ["He did not threaten me, he just shouted.", "usne koi dhamki nahi di",
                                  "There was no threat from him."])
def test_a_negated_threat_is_not_an_issue(text):
    assert "criminal_intimidation" not in concepts(text)


def test_intake_retrieval_query_carries_the_concepts(monkeypatch):
    from app.ai.nodes import retrieval_node as rn
    seen = {}

    async def no_expand(q):
        seen["q"] = q
        return q

    class R:
        def invoke(self, q):
            return []

    async def none(*a, **k):
        return []
    monkeypatch.setattr(rn, "_expand_query", no_expand)
    monkeypatch.setattr(rn, "build_retriever", lambda *a, **k: R())
    monkeypatch.setattr(rn, "_graph_hop2", lambda *a, **k: [])
    monkeypatch.setattr(rn, "_retrieve_case_law", none)
    asyncio.run(rn.retrieval_node({"query": M001, "user_text": M001, "case_type": "criminal",
                                   "province": "punjab", "retrieval_policy": {"purpose": "intake"}}))
    assert "criminal intimidation" in seen["q"] and "dishonoured cheque" in seen["q"]


def test_the_mixed_partial_restriction_is_unchanged():
    from app.ai.nodes import intake_evidence_gate_node as gate
    scope = gate.scope_issues("My cheque bounced and he threatened to kill me. What is the gold rate today?")
    assert [i["kind"] for i in scope["unsupported"]] == ["live_rate"] and not scope["pure"]


# ── Batch 3: the formal-legal-action classifier ─────────────────────────────

@pytest.mark.parametrize("text", [
    "If advised, prepare and file an application for probation in the appropriate court.",
    "Lodge an FIR at the nearest police station.",
    "File a civil suit to recover the loan amount.",
    "عدالت میں درخواست دائر کریں۔",
    "adalat mein darkhwast dair karein",
    "Send a legal notice to the tenant.",
    "Apply for bail before the Sessions Court.",
    "Request that the case be registered under Section 381 of the PPC.",
])
def test_formal_legal_steps_are_recognised(text):
    assert guard.is_formal_legal_action(text)


@pytest.mark.parametrize("text", [
    "Collect all documents related to the offence.",
    "Consult a qualified lawyer.",
    "Report the death threat immediately to the police so they can provide protection.",
    "Write down the dates and times of every incident.",
    "Obtain the full text of Section 10 CrPC.",
    "Call 15 emergency services if you are in danger.",
    "Keep copies of the FIR and your complaint safe.",
])
def test_ordinary_steps_are_not_legal_instructions(text):
    assert not guard.is_formal_legal_action(text)


D037_ACTION = "If advised, prepare and file an application for probation in the appropriate court."
KEEP = "Collect all documents related to the offence."
CONSULT = "Consult a qualified lawyer."


def _an(actions, kinds, claims=(), status="supported", cites=()):
    return {"summary": "s", "recommended_actions": list(actions), "recommended_action_kinds": list(kinds),
            "claim_assessments": list(claims), "law_citations": list(cites), "applicable_laws": [],
            "evidence_gate": {"status": status}, "grounding_status": status, "grounded": False,
            "risk_level": "low", "uncited_legal_actions": []}


def test_d037_general_labelled_filing_is_withheld_when_not_grounded():
    out = guard.enforce(_an([D037_ACTION, KEEP, CONSULT], ["general"] * 3, status="corpus_not_capable"))
    assert D037_ACTION not in out["recommended_actions"]
    assert KEEP in out["recommended_actions"] and CONSULT in out["recommended_actions"]
    assert out["output_guard"]["removed_actions"][0]["kind"] == "legal"


@pytest.mark.parametrize("action", ["Lodge an FIR at the nearest police station.",
                                    "File a civil suit to recover the loan amount.",
                                    "عدالت میں درخواست دائر کریں۔", "adalat mein darkhwast dair karein"])
def test_a_general_label_cannot_exempt_an_uncited_filing(action):
    out = guard.enforce(_an([action, KEEP], ["general", "general"], status="supported",
                            cites=[{"statute": "PPC 1860", "section": "379", "status": "bound"}]))
    assert action not in out["recommended_actions"] and KEEP in out["recommended_actions"]


BOUND = {"statute": "PPC 1860", "section": "489-F", "status": "bound"}
FILE_489F = "Lodge an FIR under Section 489-F PPC for the dishonoured cheque."


def test_a_supported_formal_action_on_bound_law_remains():
    claim = {"index": "2", "kind": "action", "action_kind": "legal", "text": FILE_489F,
             "citation_status": "matched", "support": "supported"}
    out = guard.enforce(_an([FILE_489F, KEEP], ["legal", "general"], [claim], cites=[BOUND]))
    assert out["recommended_actions"] == [FILE_489F, KEEP]


def test_a_partial_answer_cannot_keep_a_formal_step_that_is_not_fully_supported():
    claim = {"index": "2", "kind": "action", "action_kind": "legal", "text": FILE_489F,
             "citation_status": "matched", "support": "partially_supported"}
    out = guard.enforce(_an([FILE_489F, KEEP], ["legal", "general"], [claim], status="partially_supported",
                            cites=[BOUND]))
    assert FILE_489F not in out["recommended_actions"]
    assert out["output_guard"]["removed_actions"][0]["reason"] == "formal_action_not_fully_supported"


def test_the_guard_does_not_remove_every_action():
    out = guard.enforce(_an([KEEP, CONSULT, "Write down the dates."], ["general"] * 3, status="supported",
                            cites=[BOUND]))
    assert len(out["recommended_actions"]) == 3 and out["output_guard"]["removed_actions"] == []


def test_returned_and_stored_analysis_stay_identical_for_a_general_labelled_filing(monkeypatch):
    import json
    from app.ai.graph import supervisor
    from app.services import intake_service as svc
    seen = {}

    class FakeGraph:
        async def ainvoke(self, state):
            return {"answer": json.dumps({"summary": "s", "recommended_actions": [D037_ACTION, KEEP],
                                          "recommended_action_kinds": ["general", "general"], "risk_level": "low"}),
                    "evidence_gate": {"status": "corpus_not_capable"}, "citations": [], "claim_assessments": []}

    async def capture(result, analysis, *a, **k):
        seen["prov"] = json.loads(json.dumps(analysis, default=str))
    monkeypatch.setattr(supervisor, "intake_graph", FakeGraph())
    monkeypatch.setattr(svc, "_record_intake_provenance", capture)
    out = asyncio.run(svc._run_intake_ai("probation for a first offender", "criminal", "punjab", "s", "c"))
    assert D037_ACTION not in out["recommended_actions"]
    assert seen["prov"]["recommended_actions"] == out["recommended_actions"]


# ── Batch 4: the Urdu rendering fallback ────────────────────────────────────

from app.ai import intake_localization as L  # noqa: E402
from app.services import intake_service as svc  # noqa: E402

ANALYSIS = {"summary": "Your cheque was dishonoured.", "recommended_actions": ["Keep the cheque safe."],
            "law_citations": [{"statute": "PPC 1860", "section": "489-F", "status": "bound"}]}


class _LLM:
    def __init__(self, reply=None, exc=None):
        self.reply, self.exc, self.calls = reply, exc, 0

    def invoke(self, messages):
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.reply


def test_urdu_rendering_success():
    reply = L.LocalizedIntakeOutput(summary="آپ کا چیک باؤنس ہو گیا۔", recommended_actions=["چیک محفوظ رکھیں۔"],
                                    citation_notes=[""])
    r = L.localize(ANALYSIS, "ur", llm=_LLM(reply))
    assert r["status"] == "ok"


@pytest.mark.parametrize("exc,reason", [
    (RuntimeError("503 from provider"), L.FAIL_PROVIDER),
    (TimeoutError(), L.FAIL_TIMEOUT),
])
def test_provider_and_timeout_failures_are_named(exc, reason):
    r = L.localize(ANALYSIS, "ur", llm=_LLM(exc=exc))
    assert r["status"] == "failed" and r["reason"] == reason


def test_a_truncated_reply_is_malformed():
    class Msg:
        content = '{"summary": "آپ کا چیک'
    r = L.localize(ANALYSIS, "ur", llm=_LLM(Msg()))
    assert r["reason"] == L.FAIL_MALFORMED


def test_a_missing_glossary_term_fails_and_is_named():
    reply = L.LocalizedIntakeOutput(summary="آپ کا چیک واپس ہو گیا۔", recommended_actions=["محفوظ رکھیں۔"],
                                    citation_notes=[""])
    a = {**ANALYSIS, "summary": "Ask your lawyer about the cheque."}
    r = L.localize(a, "ur", llm=_LLM(reply))
    assert r["status"] == "failed" and r["reason"] == L.FAIL_GLOSSARY


def test_a_changed_action_count_is_a_meaning_failure():
    reply = L.LocalizedIntakeOutput(summary="چیک", recommended_actions=["ایک", "دو"], citation_notes=[""])
    r = L.localize(ANALYSIS, "ur", llm=_LLM(reply))
    assert r["reason"] == L.FAIL_MEANING


def _localize_returning(result):
    return lambda analysis, lang, **k: result


def test_failed_rendering_keeps_the_english_analysis_with_a_fixed_urdu_notice(monkeypatch):
    monkeypatch.setattr(L, "localize", _localize_returning({"language": "ur", "status": "failed",
                                                            "reason": L.FAIL_GLOSSARY}))
    a = asyncio.run(svc._with_localization(dict(ANALYSIS), "ur"))
    st = a["localization_state"]
    assert st == {"requested": "ur", "rendered": "en", "status": "fallback_english", "reason": "glossary_check",
                  "notice": svc.URDU_FALLBACK_NOTICE, "retry": "localization_only"}
    assert a["summary"] == ANALYSIS["summary"], "the English analysis is intact (no half translation)"
    assert a["output_language"] == "ur", "the selected language stays Urdu for a retry"
    assert a["law_citations"] == ANALYSIS["law_citations"], "no duplicated citations"
    assert svc._localized_case_fields(a) == {}, "nothing is stored as an Urdu rendering"


def test_a_successful_rendering_is_recorded_as_rendered(monkeypatch):
    monkeypatch.setattr(L, "localize", _localize_returning({"language": "ur", "status": "ok", "summary": "x",
                                                            "recommended_actions": ["y"]}))
    a = asyncio.run(svc._with_localization(dict(ANALYSIS), "ur"))
    assert a["localization_state"]["status"] == "rendered" and a["localization_state"]["rendered"] == "ur"


def test_a_slow_rendering_times_out_to_the_fallback(monkeypatch):
    import time
    monkeypatch.setattr(svc, "_LOCALIZATION_TIMEOUT_S", 0.2)
    monkeypatch.setattr(L, "localize", lambda a, lang, **k: time.sleep(2) or {"status": "ok"})
    a = asyncio.run(svc._with_localization(dict(ANALYSIS), "ur"))
    assert a["localization_state"]["status"] == "fallback_english" and a["localization_state"]["reason"] == "timeout"


def test_retry_rerenders_only_and_never_reruns_the_analysis(monkeypatch):
    from app.ai.graph import supervisor

    class Boom:
        async def ainvoke(self, state):
            raise AssertionError("retrieval/analysis must not rerun for a translation retry")
    monkeypatch.setattr(supervisor, "intake_graph", Boom())
    monkeypatch.setattr(L, "localize", _localize_returning({"language": "ur", "status": "failed",
                                                            "reason": L.FAIL_PROVIDER}))
    a = asyncio.run(svc._with_localization(dict(ANALYSIS), "ur"))
    monkeypatch.setattr(L, "localize", _localize_returning({"language": "ur", "status": "ok", "summary": "x",
                                                            "recommended_actions": ["y"]}))
    a = asyncio.run(svc.retry_localization(a))
    assert a["localization_state"]["status"] == "rendered"
    assert a["law_citations"] == ANALYSIS["law_citations"]


def test_english_needs_no_rendering():
    a = asyncio.run(svc._with_localization(dict(ANALYSIS), "en"))
    assert a["localization_state"] == {"requested": "en", "rendered": "en", "status": "not_needed"}


# ── an unsupported legal summary (observed in a theft + gold-rate run) ──────

THEFT = "Someone stole my motorcycle from outside my house last night."


def test_an_unsupported_summary_without_supported_actions_is_withheld():
    a = _an([KEEP, "Do not confront the thief; rely on the police."], ["general", "legal"],
            [{"index": "1", "kind": "summary", "text": "s", "citation_status": "matched", "support": "unsupported"},
             {"index": "3", "kind": "action", "action_kind": "legal", "citation_status": "matched",
              "text": "Do not confront the thief; rely on the police.", "support": "supported"}],
            status="partially_supported", cites=[{"statute": "PPC 1860", "section": "105", "status": "bound"}])
    a["summary"] = "Your motorcycle was stolen, constituting a criminal theft under Pakistani law."
    a["claim_assessments"][1]["support"] = "partially_supported"
    out = guard.enforce(a, story=THEFT)
    assert out["summary"].startswith(guard.SUMMARY_WITHHELD) and THEFT in out["summary"]
    assert "constituting" not in out["summary"]
    assert out["law_citations"] == [] and out["output_guard"]["summary_withheld"]
    assert out["grounding_status"] == guard.NO_LEGAL_CONTENT and out["risk_level"] is None
    assert KEEP in out["recommended_actions"], "safe general steps stay"


def test_a_supported_summary_is_untouched():
    a = _an([KEEP], ["general"], [{"index": "1", "kind": "summary", "text": "s", "citation_status": "matched",
                                   "support": "supported"}], cites=[BOUND])
    a["summary"] = "Your cheque was dishonoured."
    out = guard.enforce(a, story="my cheque bounced")
    assert out["summary"] == "Your cheque was dishonoured." and out["law_citations"] == [BOUND]


def test_a_partial_answer_never_shows_an_unsupported_summary_but_keeps_supported_law():
    action = "Lodge an FIR for theft of a motor vehicle under Section 381-A PPC."
    a = _an([action, KEEP], ["legal", "general"],
            [{"index": "1", "kind": "summary", "text": "s", "citation_status": "matched", "support": "unsupported"},
             {"index": "2", "kind": "action", "action_kind": "legal", "text": action,
              "citation_status": "matched", "support": "supported"}],
            status="partially_supported",
            cites=[{"statute": "PPC 1860", "section": "381-A", "status": "bound"}])
    a["summary"] = "The client's motorcycle was stolen and they seek legal advice."
    out = guard.enforce(a, story=THEFT)
    assert out["summary"].startswith(guard.SUMMARY_WITHHELD)
    assert action in out["recommended_actions"] and out["law_citations"], "supported law stays"
    assert out["output_guard"]["summary_withheld"] and not out["output_guard"]["downgraded"]


# ── visible provision consistency (381 shown, 381-A bound) ──────────────────

C381A = {"statute": "PPC 1860", "section": "381-A", "status": "bound", "evidence_id": "1"}
C506 = {"statute": "PPC 1860", "section": "506", "status": "bound", "evidence_id": "2"}
C489F = {"statute": "PPC 1860", "section": "489-F", "status": "bound", "evidence_id": "3"}
MFLO7 = {"statute": "Muslim Family Laws Ordinance 1961", "section": "7", "status": "bound", "evidence_id": "4"}


def _claim(text, ids, support="supported"):
    return {"index": "9", "kind": "action", "action_kind": "legal", "text": text,
            "citation_status": "matched", "support": support, "source_ids": ids}


def _visible(actions, claims, cites, summary="s", status="supported", kinds=None):
    a = _an(actions, kinds or ["legal"] * len(actions), claims, status=status, cites=cites)
    a["summary"] = summary
    return guard.enforce(a, story="my motorcycle was stolen")


def test_visible_381_with_bound_381a_is_caught_even_if_the_judge_said_supported():
    t = "Pursue a case under Section 381 of the PPC 1860."
    out = _visible([t], [_claim(t, ["1"], "supported")], [C381A])
    assert t not in out["recommended_actions"]
    mm = out["output_guard"]["visible_provision_mismatches"]
    assert mm[0]["named"] == ["381"] and mm[0]["bound"] == ["381-A"] and mm[0]["text"] == t
    assert out["grounded"] is False


def test_visible_489_with_bound_489f_is_caught():
    t = "File a complaint under Section 489 PPC for the bounced cheque."
    out = _visible([t], [_claim(t, ["3"])], [C489F])
    assert t not in out["recommended_actions"]


def test_489F_and_489_dash_F_match():
    t = "Lodge an FIR under Section 489F PPC."
    out = _visible([t], [_claim(t, ["3"])], [C489F])
    assert t in out["recommended_actions"] and out["output_guard"]["visible_provision_mismatches"] == []


def test_a_correct_section_506_remains():
    t = "Report the threat under Section 506 PPC (criminal intimidation)."
    out = _visible([t], [_claim(t, ["2"])], [C506])
    assert t in out["recommended_actions"]


def test_a_correct_subsection_remains_with_its_wording():
    t = "Send the notice required by Section 7(1) of the MFLO to the Chairman."
    out = _visible([t], [_claim(t, ["4"])], [MFLO7])
    assert t in out["recommended_actions"]


def test_a_summary_mismatch_is_neutralised_and_kept_for_audit():
    s = "The theft falls under Section 381 PPC. The client wants advice."
    out = _visible([], [], [C381A], summary=s)
    assert "Section 381 PPC" not in out["summary"] and guard.PROVISION_MISMATCH_SENTENCE in out["summary"]
    assert "The client wants advice." in out["summary"]
    assert out["output_guard"]["visible_provision_mismatches"][0]["where"] == "summary"


def test_a_general_action_without_a_section_remains():
    out = _visible([KEEP], [], [C381A], kinds=["general"])
    assert KEEP in out["recommended_actions"]


def test_multiple_citations_are_checked_claim_by_claim():
    ok = "Report the threat under Section 506 PPC."
    wrong = "Report the threat under Section 381-A PPC."      # real bound law, but not THIS claim's
    out = _visible([ok, wrong], [_claim(ok, ["2"]), {**_claim(wrong, ["2"]), "index": "10"}], [C381A, C506])
    assert ok in out["recommended_actions"] and wrong not in out["recommended_actions"]


def test_mismatch_detection_works_when_the_judge_failed():
    t = "Pursue a case under Section 381 of the PPC."
    out = _visible([t], [_claim(t, ["1"], "unassessed")], [C381A])
    assert t not in out["recommended_actions"]


def test_the_currency_notice_may_name_the_omitted_section():
    a = _an([], [], status="corpus_not_capable")
    a["summary"] = "x"
    a["evidence_gate"]["requested_provisions"] = [{"statute": "CrPC 1898", "section": "562", "omitted": True,
                                                   "omitted_by": "omitted by Ordinance XLV of 1960"}]
    out = guard.enforce(a, story="probation")
    assert "section 562" in out["summary"] and out["output_guard"]["visible_provision_mismatches"] == []


def test_stored_returned_and_provenance_agree_on_a_visible_mismatch(monkeypatch):
    import json
    from app.ai.graph import supervisor
    from app.services import intake_service as svc
    seen = {}
    t = "Pursue a case under Section 381 of the PPC 1860."

    class FakeGraph:
        async def ainvoke(self, state):
            return {"answer": json.dumps({"summary": "Theft of a motorcycle.", "recommended_actions": [t, KEEP],
                                          "recommended_action_kinds": ["legal", "general"], "risk_level": "low"}),
                    "evidence_gate": {"status": "supported"}, "citations": [C381A],
                    "claim_assessments": [_claim(t, ["1"])]}

    async def capture(result, analysis, *a, **k):
        seen["prov"] = json.loads(json.dumps(analysis, default=str))
    monkeypatch.setattr(supervisor, "intake_graph", FakeGraph())
    monkeypatch.setattr(svc, "_record_intake_provenance", capture)
    out = asyncio.run(svc._run_intake_ai("my motorcycle was stolen", "criminal", "punjab", "s", "c"))
    assert t not in out["recommended_actions"] and out["grounding_status"] == guard.VISIBLE_MISMATCH
    assert seen["prov"]["recommended_actions"] == out["recommended_actions"]
    assert seen["prov"]["output_guard"]["visible_provision_mismatches"] == \
        out["output_guard"]["visible_provision_mismatches"]
