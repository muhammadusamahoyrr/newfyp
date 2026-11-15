"""Immediate-safety guidance for a client who says they are in danger now
(client chat, 2026-10-14).

THE FAILURE THIS CLOSES
-----------------------
"My husband beats me every day and threatened to kill me tonight. What should I
do?" ended in the generic 28-word refusal ("I was unable to provide a reliable
answer ...") because the Decision Engine found no evidence it trusted. A person
describing a threat to their life tonight got nothing they could act on.

WHAT THIS DOES
--------------
`detect()` is deterministic (no model call, so it cannot fail with the
provider). It fires only when a message describes violence or a threat of it
AIMED AT A PERSON ("beats me", "hit my sister", "threatened to kill", "jaan se
maarne", "مجھے مارتا ہے") that is happening NOW, TONIGHT, or REPEATEDLY. A
violence word alone is not enough: "a truck hit my car today", "he threatened
to sue me", "what is the punishment for murder" do not trigger it.

`guidance()` is practical safety advice only. It states NO legal right and NO
legal conclusion -- those still come from the checked answer, if there is one.

EMERGENCY NUMBERS -- VERIFIED SOURCES ONLY (checked 2026-10-14)
  * 15   Police emergency -- punjabpolice.gov.pk: "In Case of an Emergency,
         Call 15"; Helplines: "Police Emergency 15".
  * 1122 Rescue -- rescue.gov.pk (Emergency Services Department, Government
         of the Punjab): Helplines "Emergency Number 1122"; medical
         emergencies, road crashes, fires.
Both are Punjab Government sources and neither states coverage elsewhere, so
the numbers are shown ONLY when the conversation's province is Punjab.
Elsewhere the text says "the police emergency number" without inventing one.
No women's helpline number is shown: none was verified.
"""
from __future__ import annotations

import re

GUIDANCE_VERSION = "safety-v1"

_F = re.IGNORECASE

_VERB = (r"(?:kill|murder|beat|hit|attack|stab|shoot|strangl|chok|burn|hurt|harm|slap|kidnap|abduct|"
         r"rape|assault|tortur|punch|kick)\w*")
_VICTIM = (r"(?:me|us|myself|my\s+(?:wife|husband|child|children|kids?|son|daughter|mother|mom|father|"
           r"sister|brother|family|baby))")

# Violence or a threat of it, aimed at a person.
_AGAINST_PERSON = re.compile(
    rf"\b{_VERB}\s+(?:\w+\s+){{0,2}}{_VICTIM}\b"
    r"|\bthreat\w*\s+(?:\w+\s+){0,2}(?:to\s+)?(?:kill|murder|hurt|harm|beat|attack|shoot|stab|burn|throw\s+acid)\b"
    r"|\b(?:will|going\s+to|gonna|wants?\s+to|trying\s+to)\s+(?:kill|murder|hurt|harm|beat|attack|shoot|stab)"
    r"\s+(?:me|us|my)\b"
    r"|\bjaan\s+se\s+maar|\bqatl\s+kar|\bmaar\s*(?:d(?:e|o|ega|egi|unga|alega|alunga|alenge)\b|ne\s+ki\b)"
    r"|\b(?:mujhe|mujh|hamein|humein|meri\s+\w+|mere\s+\w+)\s+(?:\w+\s+){0,3}"
    r"(?:maar|maarta|maarti|maarte|peet|peetta|peetti|zakhmi|tezab)\w*"
    r"|\bdhamki\w*"
    r"|جان سے مار|قتل کی دھمکی|قتل کر|مارپیٹ|تشدد|تیزاب|دھمکی"
    r"|(?:مجھے|ہمیں|میری\s+\S+|میرے\s+\S+)\s+(?:\S+\s+){0,3}(?:مارتا|مارتی|مارتے|مار|پیٹتا|پیٹتی|زخمی)",
    _F)

# Now, tonight, or ongoing.
_NOW = re.compile(
    r"\b(?:now|right\s+now|tonight|today|this\s+(?:evening|night|morning)|currently|at\s+the\s+moment|"
    r"every\s+day|everyday|daily|every\s+night|again\s+and\s+again|keeps|still|"
    r"outside\s+my|at\s+my\s+door|locked\s+me|abhi|aaj\s+raat|aaj|roz|har\s+roz|rozana|har\s+din|"
    r"is\s+waqt|raha\s+hai|rahi\s+hai|rahe\s+hain)\b"
    r"|ابھی|آج رات|آج|روز|ہر روز|روزانہ|ہر دن|اس وقت|رہا ہے|رہی ہے|رہے ہیں",
    _F)

# Present-tense violence against the speaker is ongoing by itself, and a
# threat to life is treated as live.
_ONGOING = re.compile(
    rf"\b(?:beats|hits|hurts|slaps|tortures|abuses|kicks|punches)\s+(?:\w+\s+){{0,1}}{_VICTIM}\b"
    r"|\b(?:will|going\s+to|gonna)\s+(?:kill|murder)\b"
    r"|\bthreat\w*\s+(?:\w+\s+){0,2}(?:to\s+)?(?:kill|murder)\b"
    r"|\bjaan\s+se\s+maar|مارتا ہے|مارتی ہے|جان سے مار|قتل کی دھمکی",
    _F)

# Abstract legal questions that only mention violence words.
_ABSTRACT = re.compile(
    r"\b(?:punishment|penalty|sentence|section|article|define|definition|meaning\s+of|difference\s+between|"
    r"ingredients|bail\s+(?:in|for))\b|سزا کیا|دفعہ",
    _F)
# The speaker (or someone with them) must be involved: "if someone threatens to
# kill" in a question about the law describes nobody's situation.
_SELF = re.compile(r"\b(?:me|my|us|our|i|i'm|im|we|mujhe|mujh|mera|meri|mere|hum|hamein|humein|hamara|"
                   r"hamari)\b|مجھے|مجھ|میرا|میری|میرے|ہمیں|ہمارا|ہماری|ہم", _F)
_URGENT_TIME = re.compile(r"\b(?:tonight|right\s+now|abhi|aaj\s+raat)\b|ابھی|آج رات", _F)

_ROMAN = re.compile(r"\b(?:mujhe|mera|meri|mere|hai|kya|karun|karoon|raha|rahi|abhi|aaj|jaan|nahi|"
                    r"maar|dhamki|kar|ko|se|ke|ki|ka)\b", _F)
_URDU_SCRIPT = re.compile(r"[؀-ۿ]")


def detect(text: str) -> bool:
    """True only for violence or a threat AIMED AT A PERSON that is happening
    now, tonight, or repeatedly."""
    t = (text or "").strip()
    if not t or not _AGAINST_PERSON.search(t) or not _SELF.search(t):
        return False
    if not (_NOW.search(t) or _ONGOING.search(t)):
        return False
    # "What does intimidation mean if someone threatens to kill?" is a
    # question ABOUT the law, not a report of the speaker's situation.
    if _ABSTRACT.search(t) and not _ONGOING.search(t) and not _URGENT_TIME.search(t):
        return False
    return True


def _register(text: str, language: str | None) -> str:
    if (language or "").lower() == "ur" or _URDU_SCRIPT.search(text or ""):
        return "ur"
    if len(_ROMAN.findall(text or "")) >= 2:
        return "roman"
    return "en"


_EN = {
    "head": "**If you are in danger right now, your safety comes first:**",
    "call": "- Call the police emergency number{num} immediately.",
    "leave": ("- If you can do so safely, go to a safe place now — a trusted neighbour, relative, "
              "or a busy public place — and stay where other people are."),
    "med": "- If you are injured, get medical help{med}, and keep any medical record of the injuries.",
    "tell": "- Tell someone you trust where you are, and keep your phone with you.",
    "after": "The legal information below is general; it is not a substitute for getting safe first.",
}
_ROMAN_TXT = {
    "head": "**Agar aap abhi khatre mein hain, to sab se pehle apni hifazat karein:**",
    "call": "- Foran police emergency number{num} par call karein.",
    "leave": ("- Agar mehfooz tareeqe se mumkin ho to abhi kisi mehfooz jagah chale jayein — kisi bharose "
              "ke parosi, rishtedar, ya kisi aisi jagah jahan log maujood hon."),
    "med": "- Agar aap zakhmi hain to medical madad lein{med}, aur zakhmon ka medical record sambhal kar rakhein.",
    "tell": "- Kisi bharose wale shakhs ko batayein ke aap kahan hain, aur apna phone apne paas rakhein.",
    "after": "Neeche di gayi qanooni maloomat aam hai; pehle apni hifazat zaroori hai.",
}
_UR = {
    "head": "**اگر آپ ابھی خطرے میں ہیں تو سب سے پہلے اپنی حفاظت کریں:**",
    "call": "- فوراً پولیس ایمرجنسی نمبر{num} پر کال کریں۔",
    "leave": ("- اگر محفوظ طریقے سے ممکن ہو تو ابھی کسی محفوظ جگہ چلے جائیں — کسی قابلِ اعتماد پڑوسی، "
              "رشتہ دار، یا ایسی جگہ جہاں لوگ موجود ہوں۔"),
    "med": "- اگر آپ زخمی ہیں تو طبی مدد لیں{med}، اور زخموں کا طبی ریکارڈ محفوظ رکھیں۔",
    "tell": "- کسی قابلِ اعتماد شخص کو بتائیں کہ آپ کہاں ہیں، اور اپنا فون اپنے پاس رکھیں۔",
    "after": "نیچے دی گئی قانونی معلومات عمومی ہیں؛ پہلے اپنی حفاظت ضروری ہے۔",
}


def guidance(text: str, language: str | None, province: str | None) -> str:
    """The safety block, in the user's register, with verified numbers only."""
    reg = _register(text, language)
    t = {"en": _EN, "roman": _ROMAN_TXT, "ur": _UR}[reg]
    punjab = (province or "").strip().lower() == "punjab"
    num = " (15)" if punjab else ""
    med = ((" (ریسکیو 1122)" if reg == "ur" else " (Rescue 1122)") if punjab else "")
    lines = [t["head"], t["call"].format(num=num), t["leave"], t["med"].format(med=med), t["tell"]]
    return "\n".join(lines) + "\n\n" + t["after"]


def with_guidance(content: str, text: str, language: str | None, province: str | None) -> str:
    """Prepend the safety block once (idempotent)."""
    block = guidance(text, language, province)
    if (content or "").startswith(block.split("\n", 1)[0]):
        return content
    return f"{block}\n\n{content}" if content else block
