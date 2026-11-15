"""build_v20.py -- final-paper wording fixes: FIT_paper_v19.docx -> FIT_paper_v20.docx.

v19 is not modified. Only three sentences change; no number, table or claim changes.

1. Section V-B ("Style or source?"): the paper said "23 developer-written queries"
   and, in the same paragraph, "+40.0 ... on the 25 with unseen gold passages",
   which reads as 25 out of 23. Both are right: 25 developer-written queries have
   gold passages unseen by the general model (analysis_thirdstyle.txt), and the
   style grid keeps the 23 of them whose gold SECTION is also unseen
   (build_stylegrid.py DEV23, section_leak.py; the two dropped are l004, l007).
   Now: the 23 have gold sections "not just passages" unseen.
2. Same paragraph: the "+40.0" parenthesis now names the 25 as those "whose gold
   passages alone are unseen", i.e. the superset.
3. Section IV: "the 9,042-passage corpus of the training bundle" next to the
   10,042-chunk index of Section III-A read as a typo. The bundle's corpus is a
   snapshot read from the four statute collections when the bundle was built,
   generated Q&A pairs excluded (backend/scripts/build_general_bundle.py); now
   "the 9,042-chunk statute snapshot frozen in the training bundle".
Wording is length-matched: a longer first draft pushed Word's closing
column-balance paragraph onto a 7th page.

Usage: backend/venv/Scripts/python.exe paper/build_v20.py
Then:  powershell -File paper/export_pdf_msword.ps1 -Src paper/FIT_paper_v20.docx -Out paper/FIT_paper_v20.pdf
"""
from pathlib import Path

import docx

HERE = Path(__file__).resolve().parent
SRC = HERE / "FIT_paper_v19.docx"
DST = HERE / "FIT_paper_v20.docx"

FIXES = [
    ("and 23 developer-written queries, a third source whose gold sections are absent from the general "
     "model’s training data.",
     "and 23 developer-written queries, a third source whose gold sections, not just passages, are unseen "
     "in the general model’s training."),
    ("(+40.0, p = 0.002, on the 25 with unseen gold passages)",
     "(+40.0, p = 0.002, on the 25 whose gold passages alone are unseen)"),
    ("ranking the 9,042-passage corpus of the training bundle",
     "ranking the 9,042-chunk statute snapshot frozen in the training bundle"),
]


def replace_in_paragraph(p, old, new):
    """Replace old with new inside one paragraph, keeping run formatting.

    The span may cross runs; the replacement text goes into the first run the
    span touches, and the rest of the span is removed from the following runs.
    """
    runs = p.runs
    text = "".join(r.text for r in runs)
    start = text.index(old)
    end = start + len(old)
    pos = 0
    placed = False
    for r in runs:
        r_start, r_end = pos, pos + len(r.text)
        pos = r_end
        if r_end <= start or r_start >= end:
            continue
        a = max(start, r_start) - r_start
        b = min(end, r_end) - r_start
        if not placed:
            r.text = r.text[:a] + new + r.text[b:]
            placed = True
        else:
            r.text = r.text[:a] + r.text[b:]


d = docx.Document(SRC)
for old, new in FIXES:
    hits = [p for p in d.paragraphs if old in "".join(r.text for r in p.runs)]
    assert len(hits) == 1, (old[:50], len(hits))
    replace_in_paragraph(hits[0], old, new)
    assert new in hits[0].text and old not in hits[0].text
d.save(DST)
print(f"wrote {DST}")
