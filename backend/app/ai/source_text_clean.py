"""Remove PDF amendment-footnote markers from statute text (2026-11-22).

The statute PDFs mark every amended word with a raised footnote number that
points to the amending Act. Text extraction kept those numbers inline, on both
sides of the bracketed substitution:

    "...may extend to  160[seven] 160 years..."          stored (PPC s.406)
    "...may extend to seven years..."                    what the law says

Generation read "160 years", and the statement check -- comparing the answer
with the same text -- called it supported. In the live criminal index this
affects 57 places in the PPC alone, many of them punishments and fines
("38[one thousand five hundred rupees] 38").

This cleans the text where retrieved law enters the pipeline (retrieval_node),
so the answer AND the check both see clean text. The stored corpus is left
unchanged; re-extracting it is the proper long-term fix.

Rules, narrowest first. Each removes only a number GLUED to a bracket, which in
these statutes is a footnote marker; a number written as part of the law
("section 302", "Rs. 1,000", "(2)") is never touching a "[".
"""
from __future__ import annotations

import re

# "160[seven] 160" -> "seven"; "8[] 8" -> "" : the same number on both sides.
_BOTH_SIDES = re.compile(r"(?<![\w.,/-])(\d{1,4})\s*\[([^\[\]\n]{0,160})\]\s*\1(?!\w)")
# "1[(1) any citizen" -> "[(1) any citizen": a leading marker with no partner.
_LEADING = re.compile(r"(?<![\w.,/\[\]-])(\d{1,4})(?=\[)")
# A marker alone on its own line just before the bracket ("...by \n4\n[the ...").
# Only when the number is the WHOLE line: "under section 3\n[and" keeps its 3.
_LEADING_OWN_LINE = re.compile(r"(?m)^[ \t]*\d{1,4}[ \t]*\n(?=[ \t]*\[)")
# OCR: "snail be punished" (two places in the PPC).
_SNAIL = re.compile(r"\bsnail(\s+be\b)")
_SPACES = re.compile(r"[ \t]{2,}")


def clean_statute_text(text: str) -> str:
    """The statute text without inline footnote markers. Idempotent."""
    if not text or "[" not in text and "snail" not in text:
        return text or ""
    out = _BOTH_SIDES.sub(lambda m: m.group(2), text)
    out = _LEADING_OWN_LINE.sub("", out)
    out = _LEADING.sub("", out)
    out = _SNAIL.sub(r"shall\1", out)
    return _SPACES.sub(" ", out)
