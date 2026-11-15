"""Clarifying questions ask the CLIENT for facts, never for legal conclusions.

Measured 2026-10-19 on a Punjab pre-emption intake (a land sale) that the
browser had typed "constitutional" because the story said "my right of
pre-emption". The client was asked:
  "Which fundamental right under the Constitution ... do you allege is being violated ...?"
  "Which government authority ... would you approach to enforce your claimed right ...?"
  "Do you have any clause in your title deed ... that expressly grants you a right of pre-emption ...?"
A client cannot answer these; deciding them is the lawyer's job.
"""
from __future__ import annotations

import pytest

from app.services import intake_service
from app.services.intake_service import _CLARIFY_TEMPLATES, _asks_for_legal_conclusion

REPORTED = [
    "Do you have any clause in your title deed or a prior agreement that expressly grants you "
    "a right of pre‑emption over your neighbour’s adjoining land?",
    "Which fundamental right under the Constitution of Pakistan 1973 do you allege is being "
    "violated by the sale of the adjoining land?",
    "Which government authority (e.g., revenue department, land record office, or court) would "
    "you approach to enforce your claimed right of pre‑emption over the adjoining land?",
]
FACT_QUESTIONS = [
    "Is the boundary between your 4 kanal plot and the adjoining 2 kanal plot marked in the revenue records?",
    "On what date did you send the notice to Tariq, and do you have the postal receipt?",
    "Has an FIR been registered, and at which police station?",
    "Which court did the other side file their case in, and what is the next hearing date?",
    "Which government office refused your application, and when?",
]
PRE_EMPTION = ("I own 4 kanal next to my neighbour's 2 kanal in Kasur. He sold it to an outsider on "
               "3 August 2026 and the intiqal was attested on 12 August. I want to claim my right of "
               "pre-emption.")
GOOD_Q = "On what date did you first learn that the land had been sold?"


@pytest.mark.parametrize("q", REPORTED)
def test_the_reported_questions_are_recognised(q):
    assert _asks_for_legal_conclusion(q)


@pytest.mark.parametrize("q", FACT_QUESTIONS)
def test_fact_questions_pass(q):
    assert not _asks_for_legal_conclusion(q)


def test_no_template_asks_for_a_legal_conclusion():
    for case_type, template in _CLARIFY_TEMPLATES.items():
        for line in template.splitlines()[1:]:
            assert not _asks_for_legal_conclusion(line), (case_type, line)
        assert "fundamental right" not in template.lower()


# ── the service ──────────────────────────────────────────────────────────────

class FakeRepo:
    def __init__(self, doc):
        self.doc = doc

    async def find_by_token(self, token):
        return dict(self.doc)

    async def save_clarification_qa(self, token, qa_list):
        self.doc["clarification_qa"] = qa_list
        return True


def _doc(case_type="constitutional", desc=PRE_EMPTION):
    return {"_id": "i-1", "session_token": "t", "client_id": "c", "completed": False,
            "step1": {"province": "punjab"}, "step2": {"case_type": case_type},
            "step3": {"incident_description": desc}, "clarification_qa": []}


class _Reply:
    def __init__(self, content):
        self.content = content


@pytest.fixture
def model(monkeypatch):
    state = {"replies": [], "prompts": []}

    class _LLM:
        def invoke(self, messages):
            state["prompts"].append(messages)
            return _Reply(state["replies"].pop(0))

    import app.ai.llm as llm_mod
    monkeypatch.setattr(llm_mod, "get_llm", lambda **k: _LLM())

    async def never_same(q, qa):
        return False
    monkeypatch.setattr(intake_service, "_means_the_same", never_same)
    return state


async def test_the_prompt_forbids_legal_conclusions(monkeypatch, model):
    monkeypatch.setattr(intake_service, "intake_repo", FakeRepo(_doc()))
    model["replies"] = [GOOD_Q]
    await intake_service.get_clarification("t", "c", None)
    system = model["prompts"][0][0]["content"]
    assert "NEVER ask them to name or decide a law" in system


async def test_a_land_sale_typed_constitutional_gets_the_civil_list(monkeypatch, model):
    monkeypatch.setattr(intake_service, "intake_repo", FakeRepo(_doc()))
    model["replies"] = [GOOD_Q]
    await intake_service.get_clarification("t", "c", None)
    user = model["prompts"][0][1]["content"]
    assert "Civil case key facts" in user
    assert "government office" not in user


async def test_a_real_government_matter_keeps_its_list(monkeypatch, model):
    desc = "The LDA sealed my shop on 2 May without any notice and refuses to give me the order."
    monkeypatch.setattr(intake_service, "intake_repo", FakeRepo(_doc(desc=desc)))
    model["replies"] = [GOOD_Q]
    await intake_service.get_clarification("t", "c", None)
    assert "Matter against a government office" in model["prompts"][0][1]["content"]


async def test_a_legal_conclusion_question_is_rewritten(monkeypatch, model):
    repo = FakeRepo(_doc())
    monkeypatch.setattr(intake_service, "intake_repo", repo)
    model["replies"] = [REPORTED[1], GOOD_Q]

    result = await intake_service.get_clarification("t", "c", None)

    assert result["question"] == GOOD_Q
    assert len(model["prompts"]) == 2
    assert [qa["q"] for qa in repo.doc["clarification_qa"]] == [GOOD_Q]


async def test_a_model_that_keeps_asking_for_law_shows_no_question(monkeypatch, model):
    repo = FakeRepo(_doc())
    monkeypatch.setattr(intake_service, "intake_repo", repo)
    model["replies"] = [REPORTED[1], REPORTED[2]]

    result = await intake_service.get_clarification("t", "c", None)

    assert result["done"] is True and result["question"] is None
    assert repo.doc["clarification_qa"] == []


# ── measured on the live model the same day ──────────────────────────────────

def test_a_statute_classification_question_is_recognised():
    assert _asks_for_legal_conclusion(
        "Is the 2 kanal plot that was sold to Mr. Tariq Javed classified as agricultural "
        "land under the Punjab Land Revenue Act?")
    assert not _asks_for_legal_conclusion("What did you pay under the agreement with Tariq?")


def test_a_shorter_restatement_is_a_repeat():
    from app.services.intake_service import _repeats_a_question
    first = ("Is Mr. Tariq Javed, the purchaser of Rashid Mehmood\u2019s plot, a farmer/agriculturist "
             "or does he belong to a non\u2011agricultural background?")
    again = "Is Mr. Tariq Javed a farmer/agriculturist (i.e., does he belong to an agricultural background)?"
    assert _repeats_a_question(again, [{"q": first}])
    assert not _repeats_a_question("On what date did Tariq Javed buy the plot?",
                                   [{"q": "Did Tariq Javed pay the full price for the plot?"}])


def test_asking_the_client_to_prove_a_right_is_recognised():
    assert _asks_for_legal_conclusion(
        "Do you have any written agreement, document or other evidence that confirms you have "
        "a right of pre\u2011emption over Rashid Mehmood\u2019s 2 kanal plot?")
    assert not _asks_for_legal_conclusion("Do you have the postal receipt that shows you sent the notice?")


async def test_the_model_is_told_who_is_answering(monkeypatch, model):
    doc = _doc()
    doc["step1"]["party_role"] = "plaintiff"
    monkeypatch.setattr(intake_service, "intake_repo", FakeRepo(doc))
    model["replies"] = [GOOD_Q]
    await intake_service.get_clarification("t", "c", None)
    assert "The person answering is the plaintiff" in model["prompts"][0][1]["content"]


def test_past_tense_grant_and_a_reworded_document_question():
    from app.services.intake_service import _repeats_a_question
    assert _asks_for_legal_conclusion(
        "Do you have any written agreement or document from Rashid Mehmood that gave you a right "
        "of pre\u2011emption over his land?")
    q3 = ("Do you have a copy of the sale deed or any document showing the agreement between Rashid "
          "Mehmood and Mr Tariq Javed for the 2 kanal land (including the sale price and date)?")
    q4 = ("Do you have a certified copy of the sale deed between Rashid Mehmood and Mr Tariq Javed "
          "that shows the sale price and date?")
    assert _repeats_a_question(q4, [{"q": q3}])


@pytest.mark.parametrize("q", [
    "Do you have any written agreement or document from Rashid Mehmood confirming your right of "
    "pre\u2011emption over his adjoining land?",
    "Is there any paper that proves your right to buy the land first?",
])
def test_asking_for_a_document_that_confirms_a_right_is_recognised(q):
    assert _asks_for_legal_conclusion(q)


@pytest.mark.parametrize("q", [
    "Did you send the notice claiming the land to Tariq by registered post?",
    "Did you see Tariq Javed or his workers start using the 2 kanal plot after the sale?",
    "When was the sale deed of Rashid Mehmood\u2019s land to Mr Tariq Javed registered?",
])
def test_the_live_fact_questions_still_pass(q):
    assert not _asks_for_legal_conclusion(q)


# ── every candidate is checked, the rewrite included ─────────────────────────

LEGAL_Q = ("Do you have any written agreement, letter, or document from Rashid Mehmood that "
           "acknowledges your right of pre\u2011emption over his 2 kanal plot?")


def test_a_document_that_acknowledges_a_right_is_recognised():
    assert _asks_for_legal_conclusion(LEGAL_Q)


def test_the_same_object_with_a_different_fact_is_not_a_repeat():
    from app.services.intake_service import _repeats_a_question
    copy_q = "Do you have a copy of the sale deed that Rashid Mehmood signed when he sold the 2 kanal plot to Tariq Javed?"
    date_q = "What is the date written on the sale deed that Rashid Mehmood signed when he sold the 2 kanal plot to Tariq Javed?"
    assert not _repeats_a_question(date_q, [{"q": copy_q}])


async def test_a_rewrite_after_a_repeat_is_checked_for_law_too(monkeypatch, model):
    first = "Do you have a copy of the sale deed?"
    repo = FakeRepo(_doc())
    repo.doc["clarification_qa"] = [{"q": first, "a": None}]
    monkeypatch.setattr(intake_service, "intake_repo", repo)
    model["replies"] = [first, LEGAL_Q, GOOD_Q]

    result = await intake_service.get_clarification("t", "c", "Yes")

    assert result["question"] == GOOD_Q
    assert len(model["prompts"]) == 3


async def test_two_rewrites_are_allowed_for_a_legal_question(monkeypatch, model):
    monkeypatch.setattr(intake_service, "intake_repo", FakeRepo(_doc()))
    model["replies"] = [REPORTED[1], LEGAL_Q, GOOD_Q]

    result = await intake_service.get_clarification("t", "c", None)

    assert result["question"] == GOOD_Q


def test_a_topic_the_client_does_not_know_is_not_asked_again():
    from app.services.intake_service import _repeats_a_question
    q3 = ("Do you have a copy of the sale deed or contract that Rashid Mehmood signed when he sold his "
          "2 kanal plot to Mr. Tariq Javed, showing the sale price and terms?")
    q4 = ("Do you have a copy of the sale deed or any document that shows the sale price and terms of "
          "the sale between Rashid Mehmood and Mr. Tariq Javed?")
    assert _repeats_a_question(q4, [{"q": q3, "a": "I don't know"}])
