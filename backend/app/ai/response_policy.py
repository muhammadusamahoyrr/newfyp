"""Response-length policy for chat answers (2026-10-13, client chat only).

Every chat answer used to be forced into the same six-section IRAC report, so
"What is Section 489-F?" got the same shape and length as a multi-issue case.
This module decides, DETERMINISTICALLY (no model call), how long and how
structured the visible answer should be. Reasoning, retrieval, citations and
checks are untouched: only the visible answer's shape and budget change.

MODES (soft budgets in the prompt; nothing is truncated)
  brief          definitions, explicit "short" requests       ~60-120 words
  standard       ordinary questions and procedures            ~150-300 words
  case_analysis  substantial facts / complex matters          ~300-600 words (compact IRAC)
  detailed       explicit "explain in detail" requests        up to ~900 words

PRECEDENCE
  1. not the client surface -> "legacy" (lawyer research is unchanged);
  2. policy flag off -> "legacy", EXCEPT the socket's "make it short" turn
     (followup_intent "format"), which now runs through the checked graph and
     must still answer briefly;
  3. policy on: an explicit request for less / more detail wins; then
     complex or fact-heavy -> case_analysis; definition-shaped -> brief;
     otherwise standard.

`surface` comes ONLY from the trusted route (the client chat socket sets
"client"); lawyer research leaves it unset and keeps the legacy behaviour.
"""
from __future__ import annotations

import re

POLICY_VERSION = "resp-policy-v2"  # v2: one closing question when the answer turns on a missing fact
CLIENT_GUARD_VERSION = "client-guard-v3"  # v3: corrected divorce issue routing and output language
LEGACY = "legacy"
BRIEF, STANDARD, CASE, DETAILED = "brief", "standard", "case_analysis", "detailed"
MODES = (BRIEF, STANDARD, CASE, DETAILED)
SURFACE_CLIENT = "client"

_BRIEF_WORDS = re.compile(
    r"\b(brief(ly)?|short(er)?|in short|summari[sz]e|tl;?dr|concise|in a few words|one line|"
    r"mukhtasar|mukhtsar|short mein|chota|thora sa)\b|مختصر|خلاصہ|مختصراً", re.IGNORECASE)
_DETAIL_WORDS = re.compile(
    r"\b(in detail|detailed|elaborate|explain more|more detail|tafseel|tafsil|tafseeli|detail mein|"
    r"tafseel se)\b|تفصیل|تفصیلی|وضاحت سے", re.IGNORECASE)
_DEFINITION = re.compile(
    r"^\s*(what (is|does|are)|define|meaning of|explain section)\b|\b(kya (hai|hota|hoti|hain))\b|"
    r"کیا ہے|کیا ہوتا|کیا ہوتی|کسے کہتے", re.IGNORECASE)
_FIRST_PERSON = re.compile(r"\b(my|me|i|we|our|mera|meri|mere|mujhe|hum|hamara)\b|میرا|میری|میرے|مجھے|ہم",
                           re.IGNORECASE)


def explicit_request(query: str, followup_intent: str | None = None) -> str | None:
    """BRIEF / DETAILED when the user asked for it, else None."""
    if followup_intent == "format" or _BRIEF_WORDS.search(query or ""):
        return BRIEF
    if followup_intent == "deepen" or _DETAIL_WORDS.search(query or ""):
        return DETAILED
    return None


def decide_mode(*, query: str, followup_intent: str | None, complexity: str | None,
                surface: str | None, enabled: bool) -> str:
    """The response mode for one turn. Pure."""
    if surface != SURFACE_CLIENT:
        return LEGACY                      # lawyer research: unchanged in this batch
    if not enabled:
        # Policy off: the old prompts, except the socket's "make it short"
        # turn -- that path now runs through the checked graph instead of an
        # unchecked rewrite, and it must still answer briefly.
        return BRIEF if followup_intent == "format" else LEGACY
    asked = explicit_request(query, followup_intent)
    if asked:
        return asked
    words = len((query or "").split())
    if complexity == "complex" or (words >= 25 and _FIRST_PERSON.search(query or "")):
        return CASE
    if _DEFINITION.search(query or "") and words <= 15:
        return BRIEF
    return STANDARD


def mode_for_state(state: dict) -> str:
    """decide_mode from graph state + settings (used by cache read, cache write
    and generation alike, so all three agree)."""
    from app.core.config import settings
    return decide_mode(query=state.get("query") or "", followup_intent=state.get("followup_intent"),
                       complexity=state.get("complexity"), surface=state.get("surface"),
                       enabled=bool(getattr(settings, "chat_adaptive_length_client", False)))


def cache_variant(state: dict) -> str:
    """Part of the result-cache identity: an answer written for one mode or
    policy version is never served to another."""
    mode = mode_for_state(state)
    variant = LEGACY if mode == LEGACY else f"{mode}|{POLICY_VERSION}"
    # Client answers are post-processed (unsupported periods removed, see
    # ai/period_support.py) and research answers are not, so the two must never
    # share an entry -- in either direction. The guard version also retires
    # every client entry written before the guard existed. Research keeps the
    # bare "legacy" key, i.e. its cache is untouched.
    if state.get("surface") == SURFACE_CLIENT:
        variant = f"{variant}|client|{CLIENT_GUARD_VERSION}"
    else:
        # Lawyer research with its safeguards on: its own key, so an answer
        # cached before the guards existed is never replayed as a guarded one
        # (and the reverse after a rollback). Flag off: the bare legacy key,
        # exactly as before.
        from app.ai import answer_safeguards
        if answer_safeguards.research_on(state):
            variant = f"{variant}|research|{answer_safeguards.RESEARCH_GUARD_VERSION}"
    return variant


def presentation_base_query(state: dict) -> str | None:
    """The previous question a client "make it short" / "explain in detail"
    turn re-answers, or None for every other turn.

    Its own words ("make it short") carry no legal matter: classifying them, or
    asking a fact question about them, sends the turn to clarification instead
    of re-answering. Only the client chat route sets `followup_base_query`, so
    lawyer research never takes this path -- except the research route with
    its safeguards on, which sets it the same way for a lawyer's "make it
    short" (api/v1/routes/ai.py)."""
    if (state.get("surface") in (SURFACE_CLIENT, "research")
            and state.get("followup_intent") in ("format", "deepen")):
        return state.get("followup_base_query") or None
    return None


# ── prompts ──────────────────────────────────────────────────────────────────

_COMMON_EN = """\
Rules for every answer:
- Use ONLY the law sections provided. Cite ONLY section numbers that appear in them -- never invent one.
- Write every section WITH its Act, exactly as the source names it (e.g. "Section 15 of the Punjab
  Rented Premises Act 2009", "Section 489-F PPC"). A bare "Section 15" cannot be checked.
- Each source is numbered. When a sentence states a legal proposition drawn from one, end it with that
  source's marker, e.g. "... [1]". Use only the numbers shown; omit the marker when no source supports it.
- NEVER drop, whatever the length: the provision that answers the question, any time limit or deadline,
  an urgent safety step (e.g. call 15 / go to the police) when someone is in danger, a jurisdiction note
  when the rule is provincial, and material uncertainty. If the provided sections do not answer the
  question, say so plainly in one sentence and name the fact or document that is missing -- do not guess.
- Plain language a non-lawyer understands. No repeated points, no filler, no headings you do not need.
- If the exact answer depends on a fact the user has not given (e.g. the value stolen, a child's age,
  whether the marriage is registered), give the general rule first, then close the answer (before the confidence line) with ONE short question
  asking for that fact. Do not ask a question when the answer does not depend on one.
- On the very last line, output ONLY this JSON (nothing else after it): {"confidence": 0.85}"""

_MODE_EN = {
    BRIEF: """\
You are a Pakistani legal assistant. Give a SHORT answer: about 60-120 words, 2-5 sentences, no headings.
Start with the direct answer, name the provision(s) that apply, and add one next step only if useful.""",
    STANDARD: """\
You are a Pakistani legal assistant. Answer in about 150-300 words, in this order:
1. The direct answer in 1-2 sentences.
2. **Applicable law:** only the sections that matter, one line each.
3. **What you can do:** at most 3 numbered, practical steps.
4. **Caution:** only if there is a deadline, risk or real uncertainty (one or two lines).""",
    CASE: """\
You are a Pakistani legal assistant analysing a client's situation. Answer in about 300-600 words:
**Answer:** the direct conclusion in 2-3 sentences.
**Applicable law:** only the relevant sections.
**Analysis:** apply each section to the stated facts; flag facts that are missing or unclear.
**What you can do:** at most 3 numbered steps.
**Caution:** deadlines, risks or uncertainty, if any.""",
    DETAILED: """\
You are a Pakistani legal assistant. The user asked for a DETAILED explanation (up to about 900 words).
Start with the direct answer, then explain the applicable law, how it applies, the procedure, and the
risks and time limits. Use headings where they help; do not pad.""",
}

_COMMON_UR = """\
ہر جواب کے لیے قواعد:
- صرف دی گئی قانونی دفعات استعمال کریں۔ صرف وہی دفعہ نمبر لکھیں جو ان میں موجود ہوں -- کوئی نیا نمبر نہ بنائیں۔
- ہر دفعہ کے ساتھ اس کے قانون کا نام ویسے ہی لکھیں جیسے ماخذ میں ہے (مثلاً "Section 489-F PPC")۔ صرف "دفعہ 15" لکھنا کافی نہیں۔
- ہر ماخذ کا نمبر دیا گیا ہے۔ جس جملے میں کسی ماخذ سے قانونی بات ہو، اس کے آخر میں اس کا نشان لکھیں، مثلاً "... [1]"۔
- لمبائی کچھ بھی ہو، یہ کبھی نہ چھوڑیں: سوال کا جواب دینے والی دفعہ، کوئی بھی مدت یا آخری تاریخ، خطرے کی صورت میں فوری
  حفاظتی قدم (مثلاً 15 پر کال / پولیس)، صوبائی قانون ہو تو صوبے کا ذکر، اور اہم غیر یقینی بات۔ اگر دی گئی دفعات
  سوال کا جواب نہیں دیتیں تو ایک جملے میں صاف بتائیں اور لکھیں کون سی معلومات یا دستاویز درکار ہے -- اندازہ نہ لگائیں۔
- آسان زبان، کوئی دہرائی ہوئی بات یا غیر ضروری سرخی نہیں۔
- اگر درست جواب کسی ایسی بات پر منحصر ہو جو صارف نے نہیں بتائی (مثلاً چوری شدہ مال کی مالیت، بچے کی عمر، نکاح رجسٹرڈ ہے یا نہیں)،
  تو پہلے عام قانون بتائیں، پھر جواب کے آخر میں (confidence والی لائن سے پہلے) اس بات کے بارے میں صرف ایک مختصر سوال پوچھیں۔ جہاں جواب کسی بات پر منحصر نہ ہو وہاں سوال نہ پوچھیں۔
- آخری لائن میں صرف یہ JSON لکھیں: {"confidence": 0.85}"""

_MODE_UR = {
    BRIEF: "آپ ایک پاکستانی قانونی معاون ہیں۔ مختصر جواب دیں: تقریباً 60 سے 120 الفاظ، 2 سے 5 جملے، کوئی سرخی نہیں۔ "
           "پہلے سیدھا جواب، پھر متعلقہ دفعہ، اور ضرورت ہو تو صرف ایک اگلا قدم۔",
    STANDARD: "آپ ایک پاکستانی قانونی معاون ہیں۔ تقریباً 150 سے 300 الفاظ میں اس ترتیب سے جواب دیں:\n"
              "1. ایک یا دو جملوں میں سیدھا جواب۔\n2. **متعلقہ قانون:** صرف ضروری دفعات، ہر ایک ایک لائن میں۔\n"
              "3. **آپ کیا کر سکتے ہیں:** زیادہ سے زیادہ 3 عملی قدم۔\n4. **احتیاط:** صرف اگر کوئی مدت، خطرہ یا غیر یقینی ہو۔",
    CASE: "آپ ایک پاکستانی قانونی معاون ہیں اور مؤکل کے معاملے کا تجزیہ کر رہے ہیں۔ تقریباً 300 سے 600 الفاظ:\n"
          "**جواب:** 2-3 جملوں میں نتیجہ۔\n**متعلقہ قانون:** صرف متعلقہ دفعات۔\n"
          "**تجزیہ:** ہر دفعہ کا حقائق پر اطلاق؛ جو حقائق غائب یا غیر واضح ہیں ان کی نشاندہی۔\n"
          "**آپ کیا کر سکتے ہیں:** زیادہ سے زیادہ 3 قدم۔\n**احتیاط:** مدت، خطرات یا غیر یقینی، اگر ہوں۔",
    DETAILED: "آپ ایک پاکستانی قانونی معاون ہیں۔ صارف نے تفصیلی وضاحت مانگی ہے (تقریباً 900 الفاظ تک)۔ "
              "پہلے سیدھا جواب، پھر متعلقہ قانون، اس کا اطلاق، طریقہ کار، خطرات اور مدتیں۔ غیر ضروری بات نہ بڑھائیں۔",
}

_FOLLOWUP_EN = """
This is a FOLLOW-UP in an ongoing conversation (see "Conversation context"). Answer ONLY the new point.
Do not repeat the earlier explanation; restate a provision, deadline or caveat only where this point needs it."""
_FOLLOWUP_UR = """
یہ جاری گفتگو میں اگلا سوال ہے ("Conversation context" دیکھیں)۔ صرف نیا نکتہ جواب دیں۔
پچھلی وضاحت نہ دہرائیں؛ کوئی دفعہ، مدت یا احتیاط صرف وہاں دوبارہ لکھیں جہاں اس نکتے کے لیے ضروری ہو۔"""
_SHORTEN_EN = """
The user asked for a SHORTER version of your previous answer to the question below. Re-answer that question
briefly from the law sections provided -- keep its provisions, deadlines and warnings; do not add new law."""
_SHORTEN_UR = """
صارف نے نیچے والے سوال کے پچھلے جواب کا مختصر نسخہ مانگا ہے۔ دی گئی دفعات سے اسی سوال کا مختصر جواب دیں --
دفعات، مدتیں اور تنبیہات برقرار رکھیں؛ کوئی نیا قانون شامل نہ کریں۔"""


def system_prompt(mode: str, urdu: bool, *, followup: bool, shorten: bool) -> str:
    base = (_MODE_UR if urdu else _MODE_EN)[mode]
    parts = [base, _COMMON_UR if urdu else _COMMON_EN]
    if shorten:
        parts.append(_SHORTEN_UR if urdu else _SHORTEN_EN)
    elif followup:
        parts.append(_FOLLOWUP_UR if urdu else _FOLLOWUP_EN)
    return "\n\n".join(parts)
