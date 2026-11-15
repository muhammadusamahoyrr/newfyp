"""A lawyer's "make it short" / "explain in detail" (research, 2026-10-14).

Research has no intent classifier in its route; triage's own follow-up
detector used to tag such a message but then retrieved, graded and judged the
literal words "make it short". Live probe R3.2: the turn became a clarifying
question (that also cited an Indian provision).

Deterministic and cheap: a presentation request is recognised only when the
message is short AND carries no subject matter of its own once the
presentation words are removed -- "explain bail in detail" is a new question,
"tafseel se batao" is not. English, Roman Urdu and Urdu forms.
"""
from __future__ import annotations

import re

_F = re.IGNORECASE
_BRIEF = re.compile(
    r"\b(?:make it (?:short|shorter|brief|concise)|shorter|in short|briefly|brief(?:er)?|summar(?:y|ise|ize)|"
    r"tl;?dr|concise(?:ly)?|to the point|short version|mukhtasar|mukhtasir|short mein|chota karo|kam alfaz)\b"
    r"|مختصر|خلاصہ|اختصار", _F)
_DETAIL = re.compile(
    r"\b(?:in (?:more )?detail|more detail(?:s|ed)?|elaborate|explain (?:more|further|again)|expand|go deeper|"
    r"tell me more|full analysis|tafseel(?: se)?|tafsil(?: se)?|detail (?:mein|me)|aur batao|wazahat)\b"
    r"|تفصیل|وضاحت|مزید بتائیں", _F)
_MAX_WORDS = 12
_FILLER = frozenset("""
please kindly this that it the a an answer explain make give me mein main se ko karo kariye zara thoda
version can you could would now again batao bataen batain bataiye samjhao
بتائیں بتاؤ سے میں کریں ذرا کو یہ اسے
""".split())


def presentation_intent(message: str) -> str | None:
    """"format_brief" / "format_detail" for a pure presentation request, else None."""
    text = (message or "").strip()
    if not text or len(text.split()) > _MAX_WORDS:
        return None
    kind = "format_brief" if _BRIEF.search(text) else "format_detail" if _DETAIL.search(text) else None
    if not kind:
        return None
    rest = _DETAIL.sub(" ", _BRIEF.sub(" ", text)).lower()
    # ANY word left beyond these means the message asks for something more
    # than a re-presentation ("... and add the limitation period"): it goes
    # through the pipeline as a new question rather than losing that request.
    leftover = [w for w in re.findall(r"[a-z]+|[؀-ۿ]+", rest) if w not in _FILLER]
    if leftover or re.search(r"\d", rest):
        return None
    return kind


def overrides(message: str, history: list[dict], previous_state: dict | None,
              selected_case_type: str | None, case_context: dict | None) -> dict:
    """Graph-state overrides re-answering the PREVIOUS lawyer question through
    the normal checked pipeline. Server-owned inputs only: the stored history
    and this conversation's checkpoint."""
    from app.ai import case_context as case_context_mod
    from app.websockets.chat_socket import client_turn_overrides
    kind = presentation_intent(message)
    if not kind:
        return {}
    last_ai = next((m.get("content") for m in reversed(history or [])
                    if m.get("role") == "assistant" and m.get("content")), None)
    out = client_turn_overrides(kind, history, last_ai, previous_state=previous_state,
                                selected_case_type=selected_case_type)
    base = out.get("followup_base_query")
    if base:
        # The case-bound search terms still apply to the re-answered question.
        out["retrieval_query_supplement"] = case_context_mod.augment_query(base, case_context)
    return out
