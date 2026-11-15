"""Language label vs. script actually present.

Observed in production: a Roman-Urdu maintenance query was labelled "ur" (Urdu
script) despite containing no Urdu characters. Triage only transliterates when
it believes the input is Roman Urdu, and generation answers in the language it
was told — so the mislabel both skipped normalisation and replied in the wrong
script. Which script a string uses is a fact, so it overrides the model.
"""
import pytest

from app.ai.nodes.triage_node import _URDU_SCRIPT_RE, _reconcile_language

ROMAN_URDU = "mera shohar mujhe kharch nahi deta, maintenance ka kya tareeqa hai?"
URDU_SCRIPT = "میرے والد کی جائیداد میں میرا حصہ کتنا ہے؟"
ENGLISH = "What is the punishment for theft under the Pakistan Penal Code?"


# ── the observed failure ──────────────────────────────────────────────────────

def test_the_production_mislabel_is_corrected():
    """Regression pin: this exact query was labelled 'ur' and refused."""
    assert _reconcile_language(ROMAN_URDU, "ur") == "roman_urdu"


def test_latin_text_can_never_be_labelled_urdu_script():
    assert _reconcile_language(ROMAN_URDU, "ur") == "roman_urdu"
    for text in (ENGLISH, "thank you", "What is talaq?"):
        assert _reconcile_language(text, "ur") == "en"


def test_urdu_script_is_not_mislabelled_as_roman():
    assert _reconcile_language(URDU_SCRIPT, "roman_urdu") == "ur"


# ── correct labels are left alone ─────────────────────────────────────────────

@pytest.mark.parametrize("text,label", [
    (ROMAN_URDU, "roman_urdu"),
    (URDU_SCRIPT, "ur"),
    (ENGLISH, "en"),
])
def test_correct_labels_pass_through_unchanged(text, label):
    assert _reconcile_language(text, label) == label


def test_current_message_overrides_the_models_history_influenced_label():
    """The model sees history; the current message is the language authority."""
    assert _reconcile_language(URDU_SCRIPT, "en") == "ur"
    assert _reconcile_language(ENGLISH, "en") == "en"


def test_an_earlier_urdu_turn_cannot_make_an_english_legal_question_urdu():
    question = ("Under the Muslim Family Laws Ordinance 1961, what is the "
                "procedure and timeline for a husband sending a divorce notice?")
    assert _reconcile_language(question, "ur") == "en"


# ── the script detector itself ────────────────────────────────────────────────

def test_script_detector_finds_urdu_characters():
    assert _URDU_SCRIPT_RE.search(URDU_SCRIPT)
    assert _URDU_SCRIPT_RE.search("قتل")


def test_script_detector_ignores_latin_and_digits():
    for text in (ROMAN_URDU, ENGLISH, "PPC 302", "35202-1234567-1", ""):
        assert not _URDU_SCRIPT_RE.search(text)


def test_mixed_script_counts_as_urdu_script():
    """A query mixing scripts still contains Urdu, so transliteration is not
    needed and 'ur' is the right label."""
    assert _reconcile_language("PPC 302 کے تحت سزا کیا ہے؟", "roman_urdu") == "ur"


def test_english_answer_is_repaired_once_without_losing_source_markers():
    import asyncio
    from app.ai.nodes.generation_node import _repair_english_script

    class _LLM:
        calls = 0

        def invoke(self, _messages):
            self.calls += 1
            return type("Response", (), {"content": "A husband must send notice to the Chairman [1].\n"
                                                    '{"confidence": 0.8}'})()

    llm = _LLM()
    repaired, mismatch = asyncio.run(_repair_english_script(
        llm, "شوہر کو چیئرمین کے پاس تحریری نوٹس بھیجنا ہوگا [1]."))
    assert repaired == "A husband must send notice to the Chairman [1]."
    assert mismatch is False and llm.calls == 1


def test_failed_language_repair_keeps_the_answer_instead_of_refusing():
    import asyncio
    from app.ai.nodes.generation_node import _repair_english_script

    class _LLM:
        def invoke(self, _messages):
            return type("Response", (), {"content": "English answer with a lost marker."})()

    original = "شوہر کو چیئرمین کے پاس تحریری نوٹس بھیجنا ہوگا [1]."
    assert asyncio.run(_repair_english_script(_LLM(), original)) == (original, True)
