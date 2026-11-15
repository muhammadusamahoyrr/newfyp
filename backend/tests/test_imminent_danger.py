"""Imminent-danger detection and guidance (ai/imminent_danger.py, 2026-10-14).

Live failure (c19): "My husband beats me every day and threatened to kill me
tonight. What should I do?" ended in the generic 28-word refusal.
"""
from __future__ import annotations

import pytest

from app.ai import imminent_danger as D

DANGER = [
    "My husband beats me every day and threatened to kill me tonight. What should I do?",
    "koi mujhe abhi jaan se maarne ki dhamki de raha hai, main kya karun?",
    "میرا شوہر مجھے روز مارتا ہے اور آج رات جان سے مارنے کی دھمکی دی ہے",
    "Someone is outside my door threatening to kill me right now",
    "My father beats my mother every day, what can we do?",
    "mera shohar mujhe roz maarta hai",
]
NOT_DANGER = [
    "What is the punishment for murder under Section 302 PPC?",
    "What is Section 506 PPC?",
    "My neighbour threatened to sue me",
    "A truck hit my car today, can I claim compensation?",
    "My brother was arrested for theft yesterday",
    "What is the bail for attempt to murder?",
    "My neighbour built a wall on my land and when I objected he beat me and broke my arm. "
    "What legal action can I take?",
    "Police arrested my son three days ago and have not produced him before any magistrate. What can we do?",
    "What does criminal intimidation mean if someone threatens to kill?",
    "khula kya hota hai?",
    "chori ke case mein bail kaise milti hai?",
    "تعزیرات پاکستان کی دفعہ 420 کیا ہے؟",
    "My landlord keeps threatening to evict me",
]


@pytest.mark.parametrize("text", DANGER)
def test_a_current_threat_to_the_speaker_is_detected(text):
    assert D.detect(text)


@pytest.mark.parametrize("text", NOT_DANGER)
def test_ordinary_legal_questions_do_not_trigger(text):
    assert not D.detect(text)


def test_guidance_matches_the_users_language():
    assert D.guidance(DANGER[0], "en", "punjab").startswith("**If you are in danger right now")
    assert D.guidance(DANGER[1], "en", "punjab").startswith("**Agar aap abhi khatre mein hain")
    assert D.guidance(DANGER[2], "ur", "punjab").startswith("**اگر آپ ابھی خطرے میں ہیں")


def test_verified_numbers_only_and_only_for_punjab():
    punjab = D.guidance(DANGER[0], "en", "punjab")
    assert "(15)" in punjab and "Rescue 1122" in punjab
    elsewhere = D.guidance(DANGER[0], "en", "sindh") + D.guidance(DANGER[0], "en", None)
    assert "15" not in elsewhere and "1122" not in elsewhere
    import re
    numbers = set(re.findall(r"\d{2,}", punjab))
    assert numbers == {"15", "1122"}, "no unverified number may appear"


def test_guidance_states_no_legal_right_or_conclusion():
    for text, lang in ((DANGER[0], "en"), (DANGER[1], "en"), (DANGER[2], "ur")):
        g = D.guidance(text, lang, "punjab").lower()
        for word in ("section", "ppc", "crpc", "right to", "entitled", "punishable", "dafa", "دفعہ", "حق"):
            assert word not in g


def test_guidance_is_prepended_once():
    once = D.with_guidance("Answer.", DANGER[0], "en", "punjab")
    assert D.with_guidance(once, DANGER[0], "en", "punjab") == once and once.endswith("Answer.")
