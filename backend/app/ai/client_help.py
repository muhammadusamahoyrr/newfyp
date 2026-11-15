"""Questions ABOUT the assistant, answered as such (2026-10-20).

"Can you guide me on my legal matter?", "kya aap meri rehnumai kar sakte
hain?", "کیا آپ میری مدد کر سکتے ہیں؟", "what can you do?" -- these ask whether
and how the assistant helps. They hold no facts to search the law for, so the
pipeline either asked for clarification or refused ("I was unable to provide a
reliable answer…"), which reads as a broken product.

They now get a short, fixed answer in the asker's language: yes, what it can
do, what to tell it, and that a lawyer can be booked. Nothing is retrieved or
generated, so nothing can be wrong about the law; the answer is never cached
and never counted as grounded.

Detection is deliberately narrow: a short message that is ONLY such a
request. "Can you help me, my landlord locked me out" carries a matter and goes
the normal way.
"""
from __future__ import annotations

import re

_MAX_LEN = 90

_EN = re.compile(
    r"^\s*(?:hi|hello|hey|salam|assalam[ou]\s*alaikum)?[\s,!.]*"
    r"(?:(?:can|could|will|would)\s+you\s+(?:please\s+)?(?:help|guide|assist|advise|support)\s+me"
    r"(?:\s+(?:with|on|in|about|regarding))?(?:\s+(?:my|a|the|any))?"
    r"(?:\s+(?:legal|law|court|case|matter|problem|issue|issues|situation|query|question|questions)){0,3}"
    r"|what\s+(?:can|do)\s+you\s+do|who\s+are\s+you|how\s+(?:can|do)\s+you\s+help(?:\s+me)?"
    r"|i\s+need\s+(?:legal\s+)?(?:help|guidance|advice)"
    r"|help(?:\s+me)?)"
    r"\s*[?.!]*\s*$",
    re.IGNORECASE)

_ROMAN = re.compile(
    r"^\s*(?:kya|kia|ap|aap|tum|aap\s+meri|tum\s+meri)?[\s\w]{0,40}?"
    r"(?:madad|rehnumai|rahnumai|rehnmai|rahnmai|guide|help|guidance)\s+(?:kar|kr)\s*(?:sakte|sakti|skte|skti|saktay)"
    r"(?:\s+(?:ho|hain|hen|hai|he))?\s*[?.!]*\s*$",
    re.IGNORECASE)

_URDU = re.compile(r"(?:مدد|رہنمائی|رہنمائ|راہنمائی)[\s\S]{0,20}(?:کر\s*سکت|کرسکت)")


def is_capability_question(query: str | None) -> bool:
    q = (query or "").strip()
    if not q or len(q) > _MAX_LEN:
        return False
    return bool(_EN.match(q) or _ROMAN.match(q) or _URDU.search(q))


ANSWER_EN = """Yes — I can help you understand your legal position under Pakistani law and what you can do next.

**What I can do**
- Explain the law that applies to your situation in simple words — family, criminal, civil, property, tenancy and constitutional matters.
- Tell you the usual steps: where to go, what documents you need, and what to expect.
- Help you prepare before you meet a lawyer, and show you lawyers who handle your kind of case.

**To help you properly, tell me:**
- What happened, in a few lines
- Who is involved (family member, landlord, employer, police…)
- Your city or province, and when it happened
- What you want to achieve

For example: *"My landlord in Lahore is not returning my security deposit after I moved out."*

This is general legal information, not a lawyer's advice. For your specific case you can book a registered lawyer from **Lawyers**."""

ANSWER_UR = """جی ہاں — میں پاکستانی قانون کے تحت آپ کے معاملے کو سمجھنے اور اگلے قدم جاننے میں آپ کی رہنمائی کر سکتا ہوں۔

**میں کیا کر سکتا ہوں**
- آپ کی صورتِ حال پر لاگو قانون آسان الفاظ میں سمجھانا — خاندانی، فوجداری، دیوانی، جائیداد، کرایہ داری اور آئینی معاملات۔
- عام طریقۂ کار بتانا: کہاں جانا ہے، کون سے کاغذات درکار ہیں، اور کیا توقع رکھیں۔
- وکیل سے ملنے سے پہلے تیاری میں مدد، اور آپ کے کیس جیسے معاملات دیکھنے والے وکیل دکھانا۔

**بہتر رہنمائی کے لیے مجھے بتائیں:**
- کیا ہوا، چند سطروں میں
- معاملے میں کون شامل ہے (خاندان کا فرد، مالک مکان، آجر، پولیس…)
- آپ کا شہر یا صوبہ، اور یہ کب ہوا
- آپ کیا چاہتے ہیں

مثال: *"لاہور میں میرا مالک مکان مکان خالی کرنے کے بعد میری سیکیورٹی رقم واپس نہیں کر رہا۔"*

یہ عمومی قانونی معلومات ہیں، وکیل کا مشورہ نہیں۔ اپنے مخصوص کیس کے لیے آپ **Lawyers** سے رجسٹرڈ وکیل بک کر سکتے ہیں۔"""

ANSWER_ROMAN = """Ji haan — main Pakistani qanoon ke tehat aap ke maamle ko samajhne aur agle qadam jaanne mein aap ki rehnumai kar sakta hoon.

**Main kya kar sakta hoon**
- Aap ki soorat-e-haal par laagu qanoon aasaan alfaaz mein samjhana — family, criminal, civil, property, kirayadari aur constitutional maamlaat.
- Aam tareeqa-e-kaar batana: kahan jaana hai, kaun se kaghzaat chahiye, aur kya umeed rakhein.
- Wakeel se milne se pehle tayyari mein madad, aur aap ke case jaise maamlaat dekhne wale wakeel dikhana.

**Behtar rehnumai ke liye mujhe batayein:**
- Kya hua, chand lines mein
- Maamle mein kaun shaamil hai (ghar ka fard, landlord, employer, police…)
- Aap ka shehar ya soobah, aur yeh kab hua
- Aap kya chahte hain

Misaal: *"Lahore mein mera landlord ghar khaali karne ke baad meri security wapas nahi kar raha."*

Yeh aam qanooni maloomat hain, wakeel ka mashwara nahi. Apne case ke liye aap **Lawyers** se registered wakeel book kar sakte hain."""


def capability_answer(language: str | None, query: str | None = None) -> str:
    """The fixed answer in the asker's language (Urdu script, Roman Urdu, English)."""
    q = query or ""
    if language == "ur" or _URDU.search(q):
        return ANSWER_UR
    if language == "roman_urdu" or _ROMAN.match(q.strip()):
        return ANSWER_ROMAN
    return ANSWER_EN
