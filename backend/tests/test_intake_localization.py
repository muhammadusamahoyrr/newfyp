"""Urdu rendering of a verified intake analysis (2026-10-12).

The analysis is generated and judged in English; the Urdu version is a
controlled rendering of the finished result. These tests hold the controls:
identifiers survive verbatim, structure is preserved, any violation falls back
to English, and the canonical analysis is never touched.
"""
from __future__ import annotations

import copy
import secrets
from datetime import datetime, timezone

import pytest

from app.ai import intake_localization as loc
from app.ai.nodes.intake_hallucination_node import _CAUTION
from app.services import intake_service

ANALYSIS = {
    "summary": "The cheque of Rs. 250,000 dated 12/03/2024 was dishonoured; Section 489-F PPC may apply." + _CAUTION,
    "recommended_actions": [
        "Preserve the original cheque and the bank return memo.",
        "Send a legal notice within 15 days.",
    ],
    "law_citations": [
        {"evidence_id": "2", "statute": "Pakistan Penal Code", "section": "489-F",
         "description": "Dishonestly issuing a cheque that is dishonoured.", "status": "bound"},
    ],
    "risk_level": "high",
    "grounding_status": "unverified",
}


class FakeLLM:
    """Returns a translation built from the tokens it was given."""

    def __init__(self, mutate=None):
        self.mutate = mutate
        self.calls = 0

    def invoke(self, messages):
        import json
        self.calls += 1
        src = json.loads(messages[-1]["content"])
        toks = lambda t: " ".join(loc._TOKEN.findall(t) and [f"[[T{n}]]" for n in loc._TOKEN.findall(t)])
        # A faithful translator uses the required glossary words.
        terms = lambda t: " ".join(loc.GLOSSARY[x] for x in loc._glossary_hits(t))
        item = lambda prefix, t: f"{prefix} {terms(t)} {toks(t)}".strip()
        out = {
            "summary": item("اردو خلاصہ", src["summary"]),
            "recommended_actions": [item("اردو قدم", a) for a in src["recommended_actions"]],
            "citation_notes": [item("اردو وضاحت", n) for n in src["citation_notes"]],
        }
        if self.mutate:
            self.mutate(out)
        return loc.LocalizedIntakeOutput(**out)


def test_identifiers_survive_verbatim_and_structure_is_kept():
    before = copy.deepcopy(ANALYSIS)
    out = loc.localize(ANALYSIS, "ur", llm=FakeLLM())
    assert out["status"] == "ok"
    for kept in ("Rs. 250,000", "12/03/2024", "Section 489-F", "PPC"):
        assert kept in out["summary"], f"{kept} was lost in translation"
    assert len(out["recommended_actions"]) == 2 and "15" in out["recommended_actions"][1]
    assert len(out["citation_notes"]) == 1
    assert ANALYSIS == before, "the canonical analysis was modified"


def test_the_judges_caution_is_a_key_not_translated_prose():
    out = loc.localize(ANALYSIS, "ur", llm=FakeLLM())
    assert out["cautions"] == [loc.CAUTION_PARTIAL]
    assert "could not be fully verified" not in out["summary"]


@pytest.mark.parametrize("mutate", [
    lambda o: o["recommended_actions"].pop(),                                   # an action dropped
    lambda o: o["citation_notes"].append("زائد"),                               # a note added
    lambda o: o.__setitem__("summary", o["summary"].replace("[[T1]]", "")),     # a token lost
    lambda o: o.__setitem__("summary", o["summary"] + " [[T1]]"),               # a token duplicated
    lambda o: o.__setitem__("summary", o["summary"] + " ۲۵۰"),                  # a number of its own
    lambda o: o["recommended_actions"].__setitem__(0, "نیا مشورہ " * 80),        # advice added
    lambda o: o["recommended_actions"].__setitem__(0, " "),                     # an item emptied
])
def test_any_violation_falls_back_to_english(mutate):
    out = loc.localize(ANALYSIS, "ur", llm=FakeLLM(mutate))
    assert out["language"] == "ur" and out["status"] == "failed"
    # The failure is named (2026-10-13): every violation here is a meaning one.
    assert out["reason"] == loc.FAIL_MEANING and out["detail"].startswith("LocalizationError")
    assert set(out) == {"language", "status", "reason", "detail"}, "no partial rendering leaks out"


def test_a_legal_term_must_use_its_one_urdu_word():
    """"cheque" is in the analysis: an Urdu without چیک is refused."""
    def drop(o):
        o["recommended_actions"][0] = o["recommended_actions"][0].replace("چیک", "کاغذ")
    assert loc.localize(ANALYSIS, "ur", llm=FakeLLM(drop))["status"] == "failed"


def test_a_term_inside_a_longer_one_is_not_required_twice():
    assert loc._glossary_hits("File in the civil court and the Family Court") == ["family court", "civil court"]
    assert loc._glossary_hits("the court may grant bail") == ["court", "bail"]


def test_statutes_get_their_fixed_urdu_name_beside_the_english():
    out = loc.localize(ANALYSIS, "ur", llm=FakeLLM())
    assert out["statute_names"] == ["مجموعہ تعزیرات پاکستان"]
    assert loc.statute_name_ur("Pakistan Penal Code, 1860") == "مجموعہ تعزیرات پاکستان"
    assert loc.statute_name_ur("An Act nobody has named") is None


def test_a_model_error_falls_back_to_english():
    class Boom:
        def invoke(self, messages):
            raise RuntimeError("provider down")
    assert loc.localize(ANALYSIS, "ur", llm=Boom())["status"] == "failed"


def test_english_needs_no_translation_call():
    llm = FakeLLM()
    assert loc.localize(ANALYSIS, "en", llm=llm)["status"] == "unsupported"
    assert llm.calls == 0


async def test_the_service_adds_urdu_beside_the_canonical_analysis(monkeypatch):
    seen = []
    monkeypatch.setattr(loc, "localize", lambda a, lang, llm=None: seen.append(lang) or {"language": lang, "status": "ok"})
    en = await intake_service._with_localization(copy.deepcopy(ANALYSIS), "en")
    assert en["output_language"] == "en" and "localized" not in en and seen == []
    ur = await intake_service._with_localization(copy.deepcopy(ANALYSIS), "ur")
    assert ur["output_language"] == "ur" and ur["localized"]["ur"]["status"] == "ok"
    assert ur["summary"] == ANALYSIS["summary"], "the canonical summary changed"


# ── through conversion and retry, on the real database ─────────────────────

@pytest.fixture
async def client(app_indexes):
    from app.db.collections import get_cases_col, get_intakes_col, get_users_col
    uid = f"LOC-C-{secrets.token_hex(4)}"
    await get_users_col().insert_one({"_id": uid, "role": "client", "is_active": True,
                                      "email": f"{uid}@test.invalid", "full_name": uid,
                                      "created_at": datetime.now(timezone.utc)})
    yield uid
    await get_cases_col().delete_many({"client_id": uid})
    await get_intakes_col().delete_many({"client_id": uid})
    await get_users_col().delete_one({"_id": uid})


async def _convert(uid, language, monkeypatch, result):
    seen = {}

    async def fake_classify(description, user_selected):
        return user_selected, False

    async def fake_run_ai(**kw):
        seen["language"] = kw["language"]
        return await intake_service._with_localization(copy.deepcopy(result), kw["language"])
    monkeypatch.setattr(intake_service, "_ai_classify_case_type", fake_classify)
    monkeypatch.setattr(intake_service, "_run_intake_ai", fake_run_ai)
    token = (await intake_service.start_intake(uid))["session_token"]
    for step, data in [(1, {"province": "punjab", "party_role": "plaintiff"}),
                       (2, {"case_type": "criminal", "urgency": "high"}),
                       (3, {"incident_description": "میرا چیک باؤنس ہو گیا", "incident_date": None, "incident_location": None}),
                       (4, {"has_evidence": False, "evidence_description": None, "opposing_party": None}),
                       (5, {"desired_outcome": "رقم واپس", "additional_notes": None})]:
        await intake_service.save_step(token, step, data, uid)
    done = await intake_service.convert_to_case(token, uid, language=language)
    return token, done, seen


async def test_an_urdu_case_keeps_english_canonical_and_stores_urdu_beside_it(client, monkeypatch):
    from app.db.collections import get_cases_col
    monkeypatch.setattr(loc, "localize", lambda a, lang, llm=None: {
        "language": lang, "status": "ok", "summary": "اردو خلاصہ",
        "recommended_actions": ["قدم ایک", "قدم دو"], "citation_notes": ["وضاحت"], "cautions": []})
    good = {**ANALYSIS, "grounding_status": "grounded"}
    token, done, _ = await _convert(client, "ur", monkeypatch, good)
    case = await get_cases_col().find_one({"_id": done["case_id"]})
    assert case["ai_summary"] == good["summary"], "the lawyer-facing summary is no longer canonical English"
    assert case["ai_summary_localized"]["ur"] == "اردو خلاصہ"
    assert case["ai_actions_localized"]["ur"] == ["قدم ایک", "قدم دو"]


async def test_the_language_pinned_at_step_2_beats_the_request(client, monkeypatch):
    seen = []

    async def fake_classify(description, user_selected):
        return user_selected, False

    async def fake_run_ai(**kw):
        seen.append(kw["language"])
        return {**ANALYSIS, "grounding_status": "grounded"}
    monkeypatch.setattr(intake_service, "_ai_classify_case_type", fake_classify)
    monkeypatch.setattr(intake_service, "_run_intake_ai", fake_run_ai)
    token = (await intake_service.start_intake(client))["session_token"]
    for step, data in [(1, {"province": "punjab", "party_role": "plaintiff"}),
                       (2, {"case_type": "criminal", "urgency": "high", "output_language": "ur"}),
                       (3, {"incident_description": "My cheque bounced", "incident_date": None, "incident_location": None}),
                       (4, {"has_evidence": False, "evidence_description": None, "opposing_party": None}),
                       (5, {"desired_outcome": "money", "additional_notes": None})]:
        await intake_service.save_step(token, step, data, client)
    await intake_service.convert_to_case(token, client, language="en")
    assert seen == ["ur"], "the language chosen at step 2 was overridden by the request"


async def test_a_failed_rendering_stores_no_urdu(client, monkeypatch):
    from app.db.collections import get_cases_col
    monkeypatch.setattr(loc, "localize", lambda a, lang, llm=None: {"language": lang, "status": "failed"})
    _, done, _ = await _convert(client, "ur", monkeypatch, {**ANALYSIS, "grounding_status": "grounded"})
    case = await get_cases_col().find_one({"_id": done["case_id"]})
    assert "ai_summary_localized" not in case


async def test_a_retry_keeps_the_language_chosen_at_conversion(client, monkeypatch):
    failed = {"summary": "AI structuring unavailable — case created successfully.", "applicable_laws": [],
              "recommended_actions": [], "risk_level": None, "grounded": False,
              "grounding_status": "pipeline_failed", "output_language": "ur"}

    async def fake_classify(description, user_selected):
        return user_selected, False
    calls = []

    async def fake_run_ai(**kw):
        calls.append(kw["language"])
        return dict(failed) if len(calls) == 1 else {**ANALYSIS, "grounding_status": "grounded",
                                                     "output_language": kw["language"]}
    monkeypatch.setattr(intake_service, "_ai_classify_case_type", fake_classify)
    monkeypatch.setattr(intake_service, "_run_intake_ai", fake_run_ai)
    token = (await intake_service.start_intake(client))["session_token"]
    for step, data in [(1, {"province": "punjab", "party_role": "plaintiff"}),
                       (2, {"case_type": "criminal", "urgency": "high"}),
                       (3, {"incident_description": "cheque", "incident_date": None, "incident_location": None}),
                       (4, {"has_evidence": False, "evidence_description": None, "opposing_party": None}),
                       (5, {"desired_outcome": "money", "additional_notes": None})]:
        await intake_service.save_step(token, step, data, client)
    await intake_service.convert_to_case(token, client, language="ur")
    await intake_service.retry_analysis(token, client, language="en")
    assert calls == ["ur", "ur"], "the retry switched the output language"


def test_a_plain_text_json_reply_is_parsed_and_a_bad_one_is_retried_once():
    """The real path asks for a JSON reply (a tool call with long Urdu came
    back malformed: Groq 400 tool_use_failed). One malformed reply is retried."""
    good = FakeLLM()

    class TextThenJson:
        def __init__(self):
            self.calls = 0

        def invoke(self, messages):
            self.calls += 1
            if self.calls == 1:
                return type("R", (), {"content": "Sorry, here it is: {not json"})()
            typed = good.invoke(messages)
            return type("R", (), {"content": "```json\n" + typed.model_dump_json() + "\n```"})()

    llm = TextThenJson()
    out = loc.localize(ANALYSIS, "ur", llm=llm)
    assert out["status"] == "ok" and llm.calls == 2


def test_a_statute_name_without_its_year_is_kept_verbatim():
    terms = loc._citation_terms([{"statute": "Code of Civil Procedure 1908"}])
    assert "Code of Civil Procedure" in terms
    table = {}
    masked = loc.protect("Under the Code of Civil Procedure the suit is filed.", terms, table)
    assert "Code of Civil Procedure" not in masked and "Code of Civil Procedure" in table.values()
