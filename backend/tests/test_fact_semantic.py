"""Dev-only semantic fact-fidelity (app/ai/fact_semantic.py, NOT wired into the guard) and the Urdu sentence
boundary (2026-10-15). Fake embeddings: no model is loaded."""
from __future__ import annotations

import numpy as np
import pytest

from app.ai import fact_semantic as fs


@pytest.mark.parametrize("sentence, expect", [
    ("That the accused, though not insane, is unable to understand the proceedings.", 1),
    ("That the fraud was discovered by the plaintiff within three years of the decree.", 1),
    ("That, under Section 561-A CrPC, the High Court may quash the proceedings.", 0),     # law, not a fact
    ("That the applicant respectfully prays that the delay be condoned.", 0),             # a request
    # a KNOWN false-flag source of this method (measured, not tuned away): the event stays a factual clause
    # when only its detail is a [placeholder]; the dev labels count such sentences as "ok"
    ("That the applicant was served on [date].", 1),
    ("ملزم ذہنی مریض ہے اور مقدمے کی کارروائی نہیں سمجھ سکتا۔", 1),
    ("یہ درخواست دفعہ 497 ضابطہ فوجداری کے تحت دائر کی جاتی ہے۔", 0),
])
def test_factual_clauses_keep_facts_and_drop_law_requests_and_placeholders(sentence, expect):
    assert len(fs.factual_clauses(sentence)) == expect, fs.factual_clauses(sentence)


def test_support_is_the_best_match_against_the_input_only():
    vocab = {"insane": np.array([1, 0, 0], np.float32), "quash": np.array([0, 1, 0], np.float32),
             "abuse": np.array([0, 0.6, 0.8], np.float32)}

    def vec(t):
        v = sum((vocab[w] for w in vocab if w in t.lower()), np.zeros(3, np.float32))
        n = np.linalg.norm(v)
        return (v / n).tolist() if n else [0.0, 0.0, 1.0]
    out = fs.support_scores(["That the accused is insane and cannot follow it."],
                            "Quash the proceedings, an abuse of process.", vec, lambda xs: [vec(x) for x in xs])
    assert out[0] and out[0][0][1] < 0.5, out


@pytest.mark.parametrize("text, units", [
    ("یہ کہ ملزم کی درخواست سیکشن 354، CrPC 1898 کے تحت کی جاتی ہے۔ دوسرا جملہ۔", 2),
    ("یہ کہ دفعہ 497 ضابطہ فوجداری کے تحت ضمانت دی جائے۔ مزید انکوائری درکار ہے۔ ملزم بے گناہ ہے۔", 3),
    ("That bail be granted under Sec. 497 CrPC. The inquiry is incomplete.", 2),
])
def test_an_urdu_section_word_never_ends_a_sentence(text, units):
    from app.ai import draft_guard
    from app.ai.visible_authority import _units
    assert len(_units(draft_guard.normalise(text))) == units


def test_urdu_reliance_and_subject_words_are_read():
    from app.ai import visible_authority as va
    assert va._relied_on("یہ درخواست دفعہ 497 ضابطہ فوجداری کے تحت دائر کی جاتی ہے")
    assert va.urdu_subject_words("ضمانت بعد از گرفتاری، مزید انکوائری") >= {"bail", "arrest", "inquiry"}
