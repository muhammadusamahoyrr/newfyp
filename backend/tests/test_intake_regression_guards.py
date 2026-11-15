"""Guards for the intake defects found in the 2026-09-10 audit.

Each test here failed before its fix and names the defect it protects, because
every one of these survived by being invisible: a missing import that the
surrounding `except Exception` reported as a provider outage, five validation
models imported by nothing, and three screens of collected answers that the
analysis never read.

The clarification tests assert on WHETHER THE MODEL WAS REACHED, not on what it
said. That is the property that broke — the call site raised NameError while
evaluating its own argument, so the provider was never contacted and the code
logged nothing and returned "no questions needed".
"""
from __future__ import annotations

import asyncio

import pytest

from app.core.exceptions import AppValidationError
from app.services import intake_service


TOKEN = "tok-guard"
CLIENT = "client-guard"


class FakeIntakeRepo:
    def __init__(self, doc):
        self.doc = doc
        self.saved_qa = None

    async def find_by_token(self, token):
        return dict(self.doc)

    async def save_clarification_qa(self, token, qa_list):
        self.saved_qa = qa_list
        return True

    async def update_step(self, token, step, data):
        self.doc[f"step{step}"] = data
        return True


def _doc(**over):
    d = {
        "_id": "i-guard",
        "session_token": TOKEN,
        "client_id": CLIENT,
        "completed": False,
        "case_id": None,
        "step1": {"province": "punjab"},
        "step2": {"case_type": "civil", "urgency": "medium"},
        "step3": {"incident_description": "My landlord locked my shop in Lahore."},
        "clarification_qa": [],
    }
    d.update(over)
    return d


# ── 1. the clarification LLM is actually reached ────────────────────────────

@pytest.fixture
def spy_llms(monkeypatch):
    """Replace both LLM factories with counters that refuse to do any work.

    Raising means no network, no provider key and no tokens are needed, while
    still proving the call site got far enough to ask for a model.
    """
    calls = {"llm": 0, "fast": 0}

    import app.ai.llm as llm_mod

    def spy(kind):
        def _f(*a, **k):
            calls[kind] += 1
            raise RuntimeError("spy: no provider in tests")
        return _f

    monkeypatch.setattr(llm_mod, "get_llm", spy("llm"))
    monkeypatch.setattr(llm_mod, "get_fast_llm", spy("fast"))
    return calls


async def test_clarification_reaches_the_model(spy_llms, monkeypatch):
    repo = FakeIntakeRepo(_doc())
    monkeypatch.setattr(intake_service, "intake_repo", repo)

    await intake_service.get_clarification(TOKEN, CLIENT, None)

    assert spy_llms["llm"] == 1, (
        "get_clarification returned without ever asking for a model — "
        "the PURPOSE_INTAKE_EXTRACTION NameError is back"
    )


async def test_low_confidence_classification_reaches_the_fast_model(spy_llms):
    # A description with no legal keywords scores 0.0, which is what sends the
    # decision to the LLM. Asserted rather than assumed, so this test cannot
    # quietly stop exercising the branch it exists for.
    from app.ai.nodes.classifier_node import _score_query

    description = "ambiguous zzz qqq nothing legal here"
    _, (best_score, _) = max(_score_query(description).items(), key=lambda x: x[1][0])
    assert best_score < 0.30, "fixture no longer exercises the low-confidence branch"

    await intake_service._ai_classify_case_type(description, "civil")

    assert spy_llms["fast"] == 1


async def test_a_provider_failure_still_lets_the_client_through(spy_llms, monkeypatch):
    """The fallback is correct behaviour and must survive the fix."""
    repo = FakeIntakeRepo(_doc())
    monkeypatch.setattr(intake_service, "intake_repo", repo)

    result = await intake_service.get_clarification(TOKEN, CLIENT, None)

    assert result["done"] is True
    assert result["question"] is None
    # ...but says WHY, so the UI does not claim no questions were needed.
    assert result["ai_unavailable"] is True


async def test_an_empty_model_reply_is_not_stored_as_a_question(monkeypatch):
    """A blank reply used to become {"q": "", "a": None}: a question nobody
    could see, which the next answer was then bound to."""
    repo = FakeIntakeRepo(_doc())
    monkeypatch.setattr(intake_service, "intake_repo", repo)
    import app.ai.llm as llm_mod

    class Blank:
        def invoke(self, messages):
            return type("R", (), {"content": "   "})()
    monkeypatch.setattr(llm_mod, "get_llm", lambda *a, **k: Blank())

    result = await intake_service.get_clarification(TOKEN, CLIENT, None)

    assert result == {"question": None, "done": True, "round": 0, "ai_unavailable": True}
    assert not any((qa or {}).get("q") == "" for qa in (repo.saved_qa or []))


async def test_a_real_done_is_not_reported_as_unavailable(monkeypatch):
    repo = FakeIntakeRepo(_doc())
    monkeypatch.setattr(intake_service, "intake_repo", repo)
    import app.ai.llm as llm_mod

    class Done:
        def invoke(self, messages):
            return type("R", (), {"content": "DONE"})()
    monkeypatch.setattr(llm_mod, "get_llm", lambda *a, **k: Done())

    result = await intake_service.get_clarification(TOKEN, CLIENT, None)

    assert result["done"] is True and not result.get("ai_unavailable")


async def test_a_provider_failure_is_logged_not_swallowed(spy_llms, monkeypatch, caplog):
    """A silent `except Exception` is how the NameError hid for so long."""
    repo = FakeIntakeRepo(_doc())
    monkeypatch.setattr(intake_service, "intake_repo", repo)

    with caplog.at_level("ERROR"):
        await intake_service.get_clarification(TOKEN, CLIENT, None)

    assert any("clarification" in r.message.lower() for r in caplog.records)


async def test_classification_failure_is_logged_not_swallowed(spy_llms, caplog):
    with caplog.at_level("ERROR"):
        await intake_service._ai_classify_case_type("ambiguous zzz qqq", "civil")

    assert any("classification" in r.message.lower() for r in caplog.records)


# ── 7. the step schemas are the contract ────────────────────────────────────

@pytest.mark.parametrize("step,data,bad_field", [
    (1, {"province": "Atlantis"}, "province"),
    (2, {"case_type": "banana", "urgency": "medium"}, "case_type"),
    (2, {"case_type": "civil", "urgency": "apocalyptic"}, "urgency"),
    (3, {"incident_description": "x" * 20_001}, "incident_description"),
    (4, {"has_evidence": True, "evidence_description": "y" * 5_001}, "evidence_description"),
    (5, {"desired_outcome": "z" * 5_001}, "desired_outcome"),
])
def test_invalid_step_data_is_rejected(step, data, bad_field):
    with pytest.raises(AppValidationError) as exc:
        intake_service._validate_step(step, data)
    assert bad_field in str(exc.value.detail)


def test_unknown_fields_are_rejected_not_stored():
    with pytest.raises(AppValidationError):
        intake_service._validate_step(1, {"province": "punjab", "smuggled": "x"})


def test_every_step_has_a_schema():
    assert set(intake_service.STEP_SCHEMAS) == {1, 2, 3, 4, 5}


@pytest.mark.parametrize("step,data", [
    (1, {"province": "punjab", "party_role": "plaintiff"}),
    (2, {"case_type": "civil", "urgency": "urgent"}),
    (3, {"incident_description": "A tenancy dispute.", "incident_date": None}),
    (4, {"has_evidence": True, "evidence_description": "Two receipts.", "opposing_party": None}),
    (5, {"desired_outcome": "Recover arrears", "additional_notes": None}),
])
def test_what_the_ui_actually_sends_is_accepted(step, data):
    """The schemas describe the real client, not an imagined one.

    They were written for a step 1 that collected a full name and a step 2
    whose urgency could be "emergency" — neither of which the intake UI has
    ever sent. Turning them on without this test would have rejected every
    real submission.
    """
    assert intake_service._validate_step(step, data)


def test_enums_are_stored_as_plain_strings():
    cleaned = intake_service._validate_step(1, {"province": "punjab"})
    assert cleaned["province"] == "punjab"
    assert type(cleaned["province"]) is str


def test_the_party_role_is_normalised():
    """The UI labels its cards "Plaintiff"/"Defendant" and sends them as shown."""
    cleaned = intake_service._validate_step(1, {"province": "punjab", "party_role": "Plaintiff"})
    assert cleaned["party_role"] == "plaintiff"


def test_saving_one_step_does_not_backfill_defaults():
    cleaned = intake_service._validate_step(4, {"has_evidence": True})
    assert cleaned == {"has_evidence": True}


# ── 5. collected answers reach the case and the analysis ────────────────────

@pytest.fixture
def converted(monkeypatch):
    """Run a full conversion over fakes and hand back what each layer saw."""
    seen = {}
    doc = _doc(
        step1={"province": "punjab", "party_role": "defendant"},
        step2={"case_type": "civil", "urgency": "high"},
        step4={"has_evidence": True, "evidence_description": "Two rent receipts.",
               "opposing_party": "Mr Ahmed Khan"},
        step5={"desired_outcome": "Recover the arrears", "additional_notes": "Urdu preferred."},
        evidence_files=[{"file_id": "f1"}, {"file_id": "f2"}],
    )

    class Repo(FakeIntakeRepo):
        async def claim_conversion(self, token, ttl, owner): self.owner = owner; return 1
        async def renew_conversion(self, token, owner, ttl): return owner == self.owner
        async def release_conversion(self, token, owner): return owner == self.owner
        async def attach_case(self, token, case_id, owner): self.doc["case_id"] = case_id; return True
        async def mark_completed(self, token, case_id, owner, **kw): self.doc["completed"] = True; return True
        async def save_ai_structured_case(self, token, data, owner): return True

    class CaseRepo:
        async def find_by_id(self, cid): return None
        # No case exists for this intake yet — the ordinary first conversion.
        async def find_by_intake(self, intake_id): return None
        async def update_one(self, f, u): return True

    async def fake_create_case(client_id, data, status="open"):
        # Mirrors the real signature; intake passes status=draft.
        seen["case_data"] = data
        seen["case_status"] = status
        return {"_id": "case-x"}

    async def fake_classify(desc, user_sel):
        seen["classified_on"] = desc
        return user_sel, False

    async def fake_run_ai(**kw):
        seen["ai_query"] = kw["query"]
        seen["ai_urgency"] = kw["urgency"]
        return {"summary": "ok"}

    async def fake_match(cid): pass

    monkeypatch.setattr(intake_service, "intake_repo", Repo(doc))
    monkeypatch.setattr(intake_service, "case_repo", CaseRepo())
    monkeypatch.setattr(intake_service, "create_case", fake_create_case)
    monkeypatch.setattr(intake_service, "_ai_classify_case_type", fake_classify)
    monkeypatch.setattr(intake_service, "_run_intake_ai", fake_run_ai)
    return seen


async def test_the_desired_outcome_reaches_the_analysis(converted):
    await intake_service.convert_to_case(TOKEN, CLIENT)
    await asyncio.sleep(0)
    assert "Recover the arrears" in converted["ai_query"]


async def test_the_evidence_reaches_the_analysis(converted):
    await intake_service.convert_to_case(TOKEN, CLIENT)
    await asyncio.sleep(0)
    assert "Two rent receipts." in converted["ai_query"]
    assert "2 file(s)" in converted["ai_query"]


async def test_the_party_role_reaches_the_analysis(converted):
    await intake_service.convert_to_case(TOKEN, CLIENT)
    await asyncio.sleep(0)
    assert "defendant" in converted["ai_query"]


async def test_the_opposing_party_reaches_the_analysis(converted):
    await intake_service.convert_to_case(TOKEN, CLIENT)
    await asyncio.sleep(0)
    assert "Mr Ahmed Khan" in converted["ai_query"]


async def test_the_case_carries_the_collected_answers(converted):
    await intake_service.convert_to_case(TOKEN, CLIENT)
    await asyncio.sleep(0)
    data = converted["case_data"]
    assert data["party_role"] == "defendant"
    assert data["desired_outcome"] == "Recover the arrears"
    assert data["evidence_count"] == 2
    assert data["has_evidence"] is True
    assert data["urgency"] == "high"


async def test_classification_still_runs_on_the_bare_description(converted):
    """The enrichment must not leak into the classifier's input.

    Steps 4 and 5 are full of domain words — "arrears", "receipts" — and the
    keyword classifier scores exactly those. Feeding it the enriched text would
    let the client's wish list decide the case type.
    """
    await intake_service.convert_to_case(TOKEN, CLIENT)
    await asyncio.sleep(0)
    assert converted["classified_on"] == "My landlord locked my shop in Lahore."


async def test_the_case_title_stays_the_clients_own_words(converted):
    await intake_service.convert_to_case(TOKEN, CLIENT)
    await asyncio.sleep(0)
    assert converted["case_data"]["title"].startswith("My landlord locked my shop")


async def test_conversion_creates_the_case_as_a_draft(converted):
    """The case must exist for the analysis, but not as a live case.

    Creating it OPEN is what made the "review and confirm before saving" screen
    describe a save that had already happened.
    """
    await intake_service.convert_to_case(TOKEN, CLIENT)
    await asyncio.sleep(0)
    assert converted["case_status"] == "draft"


# ── 2026-10-11: a re-sent answer after DONE must not open a new round ────────
#
# Before /convert the client re-sends its last answer in case the call that
# carried it was lost. When the model had said DONE after fewer than four
# rounds, nothing was outstanding, and the service asked the model for another
# question -- appending an unanswered round the client never saw.

async def test_a_resent_answer_after_done_asks_no_new_question(spy_llms, monkeypatch):
    qa = [{"q": "When did it happen?", "a": "March 2023"},
          {"q": "Do you have the lease?", "a": "Yes"}]
    repo = FakeIntakeRepo(_doc(clarification_qa=qa))
    monkeypatch.setattr(intake_service, "intake_repo", repo)

    result = await intake_service.get_clarification(TOKEN, CLIENT, "Yes")

    assert result == {"question": None, "done": True, "round": 2}
    assert spy_llms["llm"] == 0, "a re-sent answer reached the model for a new question"
    assert repo.saved_qa is None, "a re-sent answer rewrote the stored Q&A"


async def test_an_answer_to_an_outstanding_question_is_still_saved(spy_llms, monkeypatch):
    qa = [{"q": "When did it happen?", "a": None}]
    repo = FakeIntakeRepo(_doc(clarification_qa=qa))
    monkeypatch.setattr(intake_service, "intake_repo", repo)

    await intake_service.get_clarification(TOKEN, CLIENT, "March 2023")

    assert repo.saved_qa[0]["a"] == "March 2023"


# ── no repeated questions, no dead-end rounds (2026-10-12) ──────────────────

def _reply(monkeypatch, text, calls):
    import app.ai.llm as llm_mod

    class Fixed:
        def invoke(self, messages):
            calls.append(messages)
            return type("R", (), {"content": text})()
    monkeypatch.setattr(llm_mod, "get_llm", lambda *a, **k: Fixed())


async def test_a_reworded_repeat_of_an_earlier_question_ends_the_questions(monkeypatch):
    qa = [{"q": "آپ کے سول کیس کا بنیادی تنازعہ یا قانونی مسئلہ کیا ہے؟", "a": "زمین کا جھگڑا"}]
    repo = FakeIntakeRepo(_doc(clarification_qa=qa))
    monkeypatch.setattr(intake_service, "intake_repo", repo)
    _reply(monkeypatch, "آپ کے کیس میں اصل تنازعہ یا قانونی مسئلہ کیا ہے؟", [])

    result = await intake_service.get_clarification(TOKEN, CLIENT, None)

    assert result["done"] is True and result["question"] is None
    assert not result.get("ai_unavailable"), "a repeat is not an outage"
    assert len(repo.saved_qa or qa) == 1, "the repeated question was stored"


async def test_a_new_question_is_still_asked(monkeypatch):
    qa = [{"q": "What is the core dispute in your case?", "a": "My brother took the plot"}]
    repo = FakeIntakeRepo(_doc(clarification_qa=qa))
    monkeypatch.setattr(intake_service, "intake_repo", repo)
    _reply(monkeypatch, "Do you hold the fard or any title document for the plot?", [])

    result = await intake_service.get_clarification(TOKEN, CLIENT, None)

    assert result["done"] is False and "fard" in result["question"]


async def test_two_dont_knows_in_a_row_end_the_questions_without_a_model_call(monkeypatch):
    qa = [{"q": "Is there a written agreement?", "a": "Not sure"},
          {"q": "What amount is in dispute?", "a": None}]
    repo = FakeIntakeRepo(_doc(clarification_qa=qa))
    monkeypatch.setattr(intake_service, "intake_repo", repo)
    calls = []
    _reply(monkeypatch, "Another question?", calls)

    result = await intake_service.get_clarification(TOKEN, CLIENT, "I don't know")

    assert result["done"] is True and calls == [], "a model call was spent after two non-answers"


def test_real_answers_are_not_mistaken_for_dont_know():
    for real in ["Yes, both documents are with me.", "My brother has it", "2019", "ہاں، فرد میرے پاس ہے"]:
        assert not intake_service._is_non_answer(real)
    for none in ["I don't know", "Not sure", "معلوم نہیں", "no idea.", " "]:
        assert intake_service._is_non_answer(none)


async def test_a_rephrased_repeat_is_caught_by_meaning(monkeypatch):
    """Word overlap 0.36, same question: "how much money…" / "approximate amount…"."""
    qa = [{"q": "How much money did your landlord receive from you that has not been returned?", "a": "Not sure"}]
    repo = FakeIntakeRepo(_doc(clarification_qa=qa))
    monkeypatch.setattr(intake_service, "intake_repo", repo)
    _reply(monkeypatch, "What is the approximate amount of money you paid to the landlord that has not been returned?", [])
    monkeypatch.setattr(intake_service, "_question_vectors", lambda texts: [[1.0, 0.1]] + [[1.0, 0.12]] * (len(texts) - 1))

    result = await intake_service.get_clarification(TOKEN, CLIENT, None)

    assert result["done"] is True and not result.get("ai_unavailable")


async def test_a_different_question_passes_the_meaning_check(monkeypatch):
    qa = [{"q": "How much money is owed?", "a": "Two lakh"}]
    repo = FakeIntakeRepo(_doc(clarification_qa=qa))
    monkeypatch.setattr(intake_service, "intake_repo", repo)
    _reply(monkeypatch, "Do you have a written rent agreement?", [])
    monkeypatch.setattr(intake_service, "_question_vectors", lambda texts: [[1.0, 0.0]] + [[0.0, 1.0]] * (len(texts) - 1))

    result = await intake_service.get_clarification(TOKEN, CLIENT, None)

    assert result["done"] is False and "agreement" in result["question"]


def test_the_meaning_check_never_loads_the_embedder(monkeypatch):
    from app.ai.pipelines import retriever
    fn = retriever._embeddings
    if not hasattr(fn, "cache_info"):
        return
    fn.cache_clear()
    assert intake_service._question_vectors(["a", "b"]) is None
    assert fn.cache_info().currsize == 0, "a clarification call loaded the embedding model"


async def test_a_repeat_asks_again_for_a_different_question_instead_of_ending(monkeypatch):
    """One question then done: the answer lacked the amount, the model asked
    for the amount again, and the repeat check ended the questions."""
    import app.ai.llm as llm_mod
    qa = [{"q": "How much money is the landlord keeping from you?", "a": "He is not returning my money"}]
    repo = FakeIntakeRepo(_doc(clarification_qa=qa))
    monkeypatch.setattr(intake_service, "intake_repo", repo)
    replies = iter(["How much money is the landlord keeping from you?",
                    "Do you have a written rent agreement with the landlord?"])

    class TwoReplies:
        def invoke(self, messages):
            return type("R", (), {"content": next(replies)})()
    monkeypatch.setattr(llm_mod, "get_llm", lambda *a, **k: TwoReplies())

    result = await intake_service.get_clarification(TOKEN, CLIENT, None)

    assert result["done"] is False, "a single repeat ended the questions"
    assert "agreement" in result["question"]
