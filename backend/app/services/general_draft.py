"""The AI writes a client's document from their own description (2026-10-19).

Used by the drafting plan when no named template fits ("Employment contract for
a sales manager"). The user chose this over refusing such requests, on the
condition that it runs through the SAME safety path as the lawyer's Draft
Assistant (routes/ai.py ai_draft_stream):

  1. FAIL-CLOSED CORPUS: the drafter's verified identity indexes must be
     readable, or no model is called.
  2. GROUNDING: Pakistani statute and case-law context is retrieved and the
     model is told to cite only what it was given, and to write a
     [placeholder] for every fact the client did not give.
  3. FAIL-CLOSED GUARD: `draft_guard.check` removes unsupported or foreign
     authority, malformed CPC references and invented facts. If the check
     cannot run, NOTHING is returned -- an unchecked draft is never stored.

The result is plain text turned into simple editor HTML (headings and
paragraphs only, escaped, then sanitised). The document is labelled as an AI
draft for a lawyer to check, on the client's screen and in its catalogue entry.
"""
from __future__ import annotations

import asyncio
import html
import logging
import re

from app.core.exceptions import ServiceUnavailableError

logger = logging.getLogger(__name__)

MAX_TITLE = 90

_CLIENT_RIDER = """

WHO IS ASKING: a member of the public in Pakistan, not a lawyer. They described the document they need in their own words.
WHAT TO RETURN: the COMPLETE document, ready for them to fill in and have a lawyer check -- a title on the first line in CAPITALS, then the parties, recitals, numbered clauses or paragraphs, and signature / witness blocks where the document type needs them.
- Use ONLY the facts in their description. Every name, date, amount, address or term they did not give is a [placeholder] in square brackets.
- Prefer clear, plain clauses. Add NO legal citations -- no section, article, order, rule or case reference, not even in brackets -- unless the client's description asks for one; a lawyer adds authority when they check it. Write "under the applicable law" instead.
- FORMAT: plain text only, no markdown. A heading goes on its own line in CAPITALS; paragraphs are separated by a blank line."""


_SMALL = {"a", "an", "and", "as", "at", "by", "for", "in", "of", "on", "or", "the", "to", "with"}
_ACRONYMS = {"CNIC", "NICOP", "NDA", "FIR", "FIA", "CPC", "PPC", "CRPC", "NOC", "POA", "LLC", "LTD",
             "PVT", "SECP", "FBR", "NTN", "CEO", "HR", "IT", "PK", "UAE", "UK", "USA", "NADRA", "SP", "SHO"}


def _soft_title(heading: str) -> str:
    """"AFFIDAVIT FOR LOST CNIC" -> "Affidavit for Lost CNIC": short all-capital
    words (CNIC, NDA, FIR) stay acronyms; small joining words stay lower."""
    words = heading.split()
    out = []
    for i, w in enumerate(words):
        low = w.lower()
        if i and low in _SMALL:
            out.append(low)
        elif w.strip(".,:;()").upper() in _ACRONYMS:
            out.append(w)
        else:
            out.append(w[:1] + w[1:].lower())
    return " ".join(out)


def _title_from(text: str, prompt: str) -> str:
    """The document's own first heading, else the client's description."""
    for line in text.splitlines():
        line = _plain(line.strip()).strip("#*").strip()
        if line:
            candidate = line
            break
    else:
        candidate = ""
    if not candidate or len(candidate) > MAX_TITLE:
        candidate = " ".join(prompt.split())[:MAX_TITLE]
    title = _soft_title(candidate) if candidate.isupper() else candidate
    return title[:MAX_TITLE].strip() or "General document"


def _is_heading(line: str) -> bool:
    letters = re.sub(r"[^A-Za-z]", "", line)
    return 2 <= len(letters) and line.upper() == line and len(line) <= 90 and not line.endswith(".")


_MD_HEADING = re.compile(r"^(?:#{1,6}\s+(.+?)|\*\*(.+?)\*\*:?)$")
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")


def _plain(line: str) -> str:
    """A markdown heading line ("## X" or a line that is all "**X**") as text."""
    m = _MD_HEADING.match(line)
    return (m.group(1) or m.group(2)).strip() if m else line


def _inline(line: str) -> str:
    """Escape, then turn the model's **bold** (it uses it despite being told
    not to) into real bold -- the only markup made from model text."""
    return _MD_BOLD.sub(r"<strong>\1</strong>", html.escape(line))


_BRACKET = re.compile(r"(?<!\[)\[([^\[\]\n]{1,60})\](?!\])")
# Bracketed notes the model writes that are not details to fill in.
_NOT_PLACEHOLDERS = {"END_OF_DOCUMENT", "END", "END_OF_AFFIDAVIT", "END_OF_AGREEMENT",
                     "END_OF_CONTRACT", "END_OF_NOTICE", "INTENTIONALLY_LEFT_BLANK"}


def placeholder_token(label: str) -> str:
    """"Father’s Name" -> "FATHERS_NAME": the [[TOKEN]] form templates use."""
    label = label.replace("’", "").replace("'", "")
    return re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_").upper()[:40]


def tokenise_placeholders(text: str) -> str:
    """The model's [Full Name] -> [[FULL_NAME]] (2026-10-19), so the workspace's
    Fill placeholders panel lists, highlights and fills them exactly as it does
    for a template. A bracket with no letter in it ([1], [ ]) is left alone."""
    def swap(m: re.Match) -> str:
        token = placeholder_token(m.group(1))
        if token in _NOT_PLACEHOLDERS:
            return ""                      # "[End of Document]": not a detail to fill
        return f"[[{token}]]" if re.search(r"[A-Z]", token) else m.group(0)
    return _BRACKET.sub(swap, text or "")


def text_to_html(text: str) -> str:
    """Plain draft text -> simple editor HTML (escaped; headings + paragraphs)."""
    text = tokenise_placeholders(text)
    blocks = [b.strip() for b in re.split(r"\n\s*\n", (text or "").replace("\r\n", "\n")) if b.strip()]
    out: list[str] = []
    first = True
    for block in blocks:
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        # A heading line on top of a paragraph block: split it off.
        while lines and (_MD_HEADING.match(lines[0]) or _is_heading(lines[0])):
            tag = "h1" if first else "h2"
            out.append(f"<{tag}>{html.escape(_plain(lines.pop(0)))}</{tag}>")
            first = False
        if lines:
            out.append("<p>" + "<br>".join(_inline(ln) for ln in lines) + "</p>")
            first = False
    return "".join(out)


async def write(prompt: str, *, case: dict | None = None, province: str = "") -> dict:
    """{"title", "body_html", "withheld": [...]} for the client's description.

    Raises ServiceUnavailableError when the corpus is unreadable, the model
    fails, or the legal check cannot run (fail-closed: no unchecked text).
    """
    # Imported here: these live with the lawyer's drafter in the AI route
    # module, and importing that module at load time would be circular.
    from app.ai import draft_guard, draft_jurisdiction, index_health, source_currency
    from app.ai.llm import get_llm
    from app.ai.provider_health import PURPOSE_DRAFT_STREAM
    from app.api.v1.routes import ai as ai_routes
    from app.services.case_context import build_case_context, context_block, resolve_general

    case_block = ""
    if case:
        ctx = build_case_context(case)
        case_type, prov = ctx["case_type"] or "civil", ctx["province"]
        case_block = context_block(ctx)
    else:
        case_type, prov = resolve_general("civil", province or "")
    prov, basis = draft_jurisdiction.resolve(bool(case), prov)
    topic = draft_jurisdiction.topic_for(prompt)

    try:
        await asyncio.to_thread(index_health.require_all, ai_routes.DRAFTER_IDENTITY_INDEXES)
    except index_health.IdentityIndexUnavailable:
        raise ServiceUnavailableError(
            "The legal library the drafter checks against is unavailable, so nothing was drafted. Try again later.")

    query = ai_routes._retrieval_query("general document", prompt, "")
    statute_law = await asyncio.to_thread(
        ai_routes._retrieve_law_context, query, case_type,
        draft_jurisdiction.retrieval_province(prov), prompt)
    case_law = await ai_routes._retrieve_case_law_context(query)
    exact_chunks = await asyncio.to_thread(ai_routes._exact_provisions_for, prompt)
    exact_block = "\n\n".join(
        f"[EXACT TEXT] {c['exact_provision']} ({c.get('statute', '')})\n{(c.get('content') or '')[:1200]}"
        for c in exact_chunks)
    law = ((exact_block + "\n\n") if exact_block else "") + statute_law + (("\n\n" + case_law) if case_law else "")

    system = (ai_routes._DRAFT_SYSTEM.format(template="the document the client describes", law=law)
              + source_currency.drafting_rider(law, prompt, prov)
              + draft_jurisdiction.rider(prov, basis)
              + draft_jurisdiction.topic_rider(prov, topic)
              + _CLIENT_RIDER)
    user = (case_block + "\n\n" if case_block else "") + f"Instruction: Draft this document: {prompt}"
    try:
        reply = await get_llm(purpose=PURPOSE_DRAFT_STREAM).ainvoke(
            [{"role": "system", "content": system}, {"role": "user", "content": user}])
        drafted = str(getattr(reply, "content", reply) or "").strip()
    except Exception:
        logger.exception("general draft: model call failed")
        raise ServiceUnavailableError("The AI could not write this document right now. Try again.")
    if not drafted:
        raise ServiceUnavailableError("The AI returned an empty document. Try again.")

    try:
        guard = draft_guard.check(
            drafted, prompt, [{**c, "kind": "statute"} for c in exact_chunks], prov, topic,
            context=f"{prompt} {case_block}", own_text=prompt)
    except Exception as exc:
        # Where it failed, never what it was checking (the text is the client's).
        logger.error("general draft: legal check did not run (%s)", type(exc).__name__)
        raise ServiceUnavailableError(
            "The legal check on the draft could not run, so nothing was saved. Try again.")
    if not guard.get("ran") or not str(guard.get("text") or "").strip():
        raise ServiceUnavailableError(
            "The legal check on the draft could not run, so nothing was saved. Try again.")

    text = guard["text"]
    from app.services.document_service import _clean_draft_html
    body_html = _clean_draft_html(text_to_html(text))
    return {
        "title": _title_from(text, prompt),
        "body_html": body_html,
        "withheld": guard.get("withheld") or [],
        "jurisdiction": {"province": prov, "basis": basis},
    }
