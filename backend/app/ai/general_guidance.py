"""General guidance for a LAWYER when the library has nothing to ground an
answer (2026-10-20).

The research pipeline refuses when retrieval finds too little ("I was unable to
provide a reliable answer…"). For a client that is the honest answer. For a
lawyer -- a professional who will check what they are told -- a blank refusal
on a basic question ("what are the fundamental rights in the Constitution?")
is simply unhelpful, and the library does not hold every topic.

So, on the lawyer's research surface ONLY, the refusal is replaced by an
openly-labelled orientation:
  * it says first that nothing in AttorneyAI's verified library supported it;
  * it explains the concept, names where the law is usually found, and lists
    what to verify -- it does not quote statute text;
  * any article / section numbers are general knowledge and are flagged as
    unverified (the UI shows the same warning, and the answer is never cached
    or counted as grounded).
It never replaces a refusal the pipeline gave for a REASON (a fact the corpus
cannot hold, a law unavailable for the province, a technical fault): those
stay as they are. If the model call fails, the original refusal stands.
"""
from __future__ import annotations

import asyncio
import logging
import re

from app.ai.llm import get_llm
from app.ai.provider_health import PURPOSE_ANSWER_GENERATION

logger = logging.getLogger(__name__)

HEADER_EN = ("General guidance — not from the AttorneyAI legal library. Nothing in the verified "
             "library supported a sourced answer, so this is orientation only. Verify every "
             "article, section and rule against the official text before relying on it.")
HEADER_UR = ("عمومی رہنمائی — یہ AttorneyAI کی قانونی لائبریری سے نہیں۔ لائبریری میں اس کا مستند جواب "
             "نہیں ملا، اس لیے یہ صرف رہنمائی ہے۔ کسی بھی آرٹیکل یا دفعہ پر انحصار سے پہلے سرکاری متن سے تصدیق کریں۔")

_SYSTEM = """\
You are assisting a Pakistani advocate. AttorneyAI's verified legal library returned nothing that \
supports a sourced answer to their question, so you give GENERAL ORIENTATION from general knowledge.

Rules:
- Be useful and concrete: explain the concept, the usual legal framework in Pakistan, and where the \
law is normally found (e.g. "Part II, Chapter 1 of the Constitution of 1973 — Fundamental Rights").
- You may name articles / sections you are confident of, but never quote statutory text, never \
invent case citations, and never give a reporter citation (PLD, SCMR, CLC, …).
- If the question is ambiguous, answer the most likely reading and say which reading you took.
- End with a short "Verify before relying" list: the 2–4 primary sources to check.
- Pakistan only. Do not use Indian or other foreign law.
- Use short **bold** headings and bullet points. No tables. If you name an article or section, say what it covers in a few words, and only name ones you are sure of.
{language}"""

# The CLIENT's version (2026-10-20): a member of the public, not an advocate.
CLIENT_HEADER_EN = ("General information — not from the AttorneyAI legal library. This is a general "
                    "explanation to help you understand your situation, not legal advice. Confirm it with a "
                    "lawyer before you act.")
CLIENT_HEADER_UR = ("عمومی معلومات — یہ AttorneyAI کی قانونی لائبریری سے نہیں۔ یہ آپ کی صورتِ حال سمجھانے کے لیے "
                    "عمومی وضاحت ہے، قانونی مشورہ نہیں۔ کوئی قدم اٹھانے سے پہلے وکیل سے تصدیق کریں۔")
CLIENT_HEADER_ROMAN = ("Aam maloomat — yeh AttorneyAI ki qanooni library se nahi. Yeh aap ki soorat-e-haal samjhane ke "
                       "liye aam wazahat hai, qanooni mashwara nahi. Koi qadam uthane se pehle wakeel se tasdeeq karein.")

_CLIENT_SYSTEM = """\
You are helping an ordinary person in Pakistan (not a lawyer) understand a legal question. \
AttorneyAI's verified legal library returned nothing that supports a sourced answer, so you give \
GENERAL INFORMATION from general knowledge, in plain, kind, simple language.

Rules:
- Start with a direct, plain answer in 1–2 sentences.
- Then: what the law in Pakistan generally says about it, and the practical next steps (where to go — \
police station, family court, union council, NADRA, etc. — and what papers to keep or bring).
- Do NOT name any Act, Ordinance, Code, section or article: nothing here was checked against the \
law's text, and a wrong name misleads more than none. Describe what the law generally provides in \
plain words and say a lawyer can point to the exact provision. Never invent case names or citations.
- No legal jargon without explaining it. Short **bold** headings and bullet points. No tables. Keep it under 220 words.
- End with one line advising them to confirm with a lawyer for their own case.
- Pakistan only. Do not use Indian or other foreign law.
{language}"""


# A line naming a law or a provision (2026-10-21). The client's guidance has
# no verified source, so such a line is removed rather than shown: one fallback
# tied khula to the Muslim Family Laws Ordinance, which no retrieved source said.
# Capitalised "Act" / "Ordinance" only: "act quickly" is not a law.
_NAMED_LAW = re.compile(
    r"\b(?:Act|Ordinance|Code|Constitution)\b|\b(?:PPC|CrPC|CPC|MFLO|QSO|PECA)\b|"
    r"(?i:\b(?:section|sec\.|article|art\.|s\.|dafa)\s*\d)|"
    r"دفعہ|آرٹیکل|ایکٹ|آرڈیننس|آئین")


def drop_named_law(body: str) -> str:
    """`body` without the lines that name a law or a provision."""
    kept = [line for line in (body or "").splitlines() if not _NAMED_LAW.search(line)]
    return "\n".join(kept).strip()


async def write(state: dict, audience: str = "lawyer") -> str | None:
    """The labelled guidance, or None (keep the refusal) if the model fails."""
    question = (state.get("query") or "").strip()
    if not question:
        return None
    urdu = state.get("language") == "ur"
    roman = state.get("language") == "roman_urdu"
    context = []
    if state.get("case_type") and state.get("case_type") != "unknown":
        context.append(f"Area: {state['case_type']}")
    if state.get("province") and state.get("province") != "unknown":
        context.append(f"Province: {state['province']}")
    try:
        llm = get_llm(purpose=PURPOSE_ANSWER_GENERATION)
        response = await asyncio.to_thread(llm.invoke, [
            {"role": "system", "content": (_CLIENT_SYSTEM if audience == "client" else _SYSTEM).format(
                language="Answer in Urdu (Urdu script)." if urdu
                else "Answer in Roman Urdu (Urdu written in English letters), as the question was." if roman and audience == "client"
                else "Answer in English.")},
            {"role": "user", "content": question + (("\n\n" + "\n".join(context)) if context else "")},
        ])
        body = (getattr(response, "content", "") or "").strip()
    except Exception as exc:  # noqa: BLE001 -- a refusal is the safe fallback
        logger.warning("general_guidance: model call failed (%s)", type(exc).__name__)
        return None
    if audience == "client":
        body = drop_named_law(body)
    if len(body) < 40:
        return None
    if audience == "client":
        header = CLIENT_HEADER_UR if urdu else CLIENT_HEADER_ROMAN if roman else CLIENT_HEADER_EN
    else:
        header = HEADER_UR if urdu else HEADER_EN
    return f"{header}\n\n{body}"
