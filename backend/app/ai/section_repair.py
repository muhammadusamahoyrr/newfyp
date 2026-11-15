"""Lettered-section repair for the statute index (2026-10-13).

THE DEFECT
The statute PDFs print an amendment-inserted section heading across two lines:

    489-
    F.
    Dishonestly issuing a cheque: ...

`scripts/ingest_statutes.py` split sections with `^\\s*(\\d+[A-Z]?)\\s*[.\\-]\\s+`,
which reads "489-" + newline as a complete heading, so PPC 489-A..489-F were
all stored as section "489" -- the same section as "Tampering with property
mark". Audited 2026-10-13: 85 PPC heading chunks + 21 continuations carry a
lettered provision under the bare number (an earlier count of "72 PPC + 1
CrPC" missed headings without a full stop, and the "CrPC" chunk was a
Schedule II table row, not a section). A window-split
continuation of such a section has no heading at all (PPC chunk 0759, the tail
of 489-E), so the runtime header repair (`intake_evidence.canonical_section`)
cannot reach it.

THE REPAIR (no re-embedding)
The text of every chunk is unchanged, so its embedding is unchanged; only the
`section_number` metadata is wrong. `repair_labels` derives the right label
from each chunk's own heading and carries it to the heading-less continuation
chunks that follow it under the same stored number. The result is written to a
VERSIONED copy (`<base>__sec_v1`, scripts/build_section_index.py); the base
collection is never modified.

A lettered heading buried in the MIDDLE of a chunk (one found: PPC 216-B)
cannot be fixed by relabelling -- that needs re-chunking from the source PDF
with the fixed parser, which is a separate, re-embedding rebuild.

Labels use the corpus's stored form: "489F" (corpus_index.section_key).
"""
from __future__ import annotations

import re

REPAIR_VERSION = "section-repair-v1"

# "489-\nF." / "489-F." / "108-\nA \nAbetment" at the very start of the chunk:
# the letter, then a full stop / colon or the end of its line. "12- A person"
# is NOT a heading letter. Shared with the runtime fallbacks
# (intake_evidence, contextual_index) so all three read a heading the same way.
LETTERED_HEADING = re.compile(r"^\s*(\d+)\s*-?\s*([A-Z]{1,2})[ \t]*(?:[.:]|(?=\n))")
_LETTERED_HEAD = LETTERED_HEADING
# "489." -- a plain heading, which ends any lettered run.
_PLAIN_HEAD = re.compile(r"^\s*(\d+)\s*\.\s")
_ORDER = re.compile(r"_(\d+)$")
# Any heading-shaped "294-B" opening (also split across lines), with or
# without the full stop: it ends a continuation run (a new provision or a
# table row starts here).
_ANY_LETTERED = re.compile(r"^\s*\d+\s*-\s*[A-Z]{1,2}\b")
# "298- Misuse of epithets..." -- the PDF prints the letter AFTER the title
# ("...places: \nB. ("), so it is not visible at the chunk start. sec_v1 reports
# it as unresolved and carries nothing into it; sec_v2 (split_provisions,
# DEFERRED_LETTER_HEADING) resolves it as 298-B from the source text.
_LETTERLESS_HEAD = re.compile(r"^\s*(\d+)\s*-\s+(?![A-Z]{1,2}\s*\.)")
# How far a stored number may fall below the statute's running maximum before
# the chunk is treated as out of sequence (schedule/table), not a section.
_SEQUENCE_SLACK = 5


def _order(chunk_id: str) -> tuple[str, int]:
    m = _ORDER.search(chunk_id or "")
    return ((chunk_id or "")[: m.start()], int(m.group(1))) if m else (chunk_id or "", -1)


def repair_labels(rows: list[tuple[str, dict, str]]) -> dict[str, dict]:
    """{chunk_id: {"section_number", "original", "how"}} for every chunk whose
    stored section must change. `rows` = (chunk_id, metadata, text) of one
    collection, in any order. Pure."""
    out: dict[str, dict] = {}
    ordered = sorted(rows, key=lambda r: _order(r[0]))
    prev_prefix, prev_stored, carry, high = None, None, None, 0
    for cid, meta, text in ordered:
        prefix, _ = _order(cid)
        stored = str((meta or {}).get("section_number") or "").strip()
        if prefix != prev_prefix:
            high = 0
        if prefix != prev_prefix or stored != prev_stored:
            carry = None
        num = int(stored) if stored.isdigit() else None
        m = _LETTERED_HEAD.match(text or "")
        if num is not None and num < high - _SEQUENCE_SLACK:
            # Out of sequence: a schedule/table row (CrPC Schedule II lists
            # PPC offences by PPC number -- "294-A ... Ditto Summons" is not
            # CrPC s.294-A). Never relabelled; reported by the audit.
            carry = None
            if m or _ANY_LETTERED.match(text or ""):
                out[cid] = {"section_number": stored, "original": stored, "how": "skipped_out_of_sequence"}
        elif m and stored == m.group(1):
            carry = f"{m.group(1)}{m.group(2)}"
            out[cid] = {"section_number": carry, "original": stored, "how": "heading"}
        elif _LETTERLESS_HEAD.match(text or ""):
            carry = None
            out[cid] = {"section_number": stored, "original": stored, "how": "unresolved_letterless_heading"}
        elif _PLAIN_HEAD.match(text or "") or _ANY_LETTERED.match(text or ""):
            carry = None
        elif carry and stored == re.match(r"\d+", carry).group(0):
            out[cid] = {"section_number": carry, "original": stored, "how": "continuation"}
        if num is not None:
            high = max(high, num)
        prev_prefix, prev_stored = prefix, stored
    return out


def relabels(fixes: dict[str, dict]) -> dict[str, dict]:
    """Only the entries that actually change a label."""
    return {k: v for k, v in fixes.items() if v["how"] in ("heading", "continuation")}


def buried_lettered_headings(text: str) -> list[str]:
    """Lettered headings that start mid-chunk (need re-chunking, not relabelling)."""
    return [f"{m.group(1)}{m.group(2)}"
            for m in re.finditer(r"\n\s*(\d+)\s*-\s*\n?\s*([A-Z]{1,2})\s*\.\s", (text or "")[5:])]


# ── sec_v2: provision splitting at the source (2026-10-13) ───────────────────
#
# sec_v1 relabels chunks whose TEXT is right. sec_v2 re-splits the source text,
# because three defects are boundary defects, not label defects:
#   * "216-B. Definition..." on one line never matched the old pattern, so it
#     sat inside another chunk -- and it is not a live provision at all: the
#     PDF prints it inside footnote 76, "The following was omitted by Penal
#     Code (Amendment) Act, VIII of 1942, S.3 : :". Nine such quoted, omitted
#     provisions exist in the PPC text (13, 15, 18, 58, 61, 138-A, 216-B, 226,
#     366); the base index stores them as if they were in force.
#   * "298- Misuse of epithets ...: \nB. (" prints the letter AFTER the title
#     (PPC 298-B; the same shape is PPC 337-A, "Punishment of shajjah").
#   * the CrPC body schedules (II: tabular statement of PPC offences, V: forms)
#     list offences by PPC number; "294-\nA \n. Keeping lottery office" is a
#     table row, never CrPC s.294-A.
# One parser serves ingestion (scripts/ingest_statutes.py) and the sec_v2
# build, so a future re-ingest cannot drift from the index it produced.

SPLIT_VERSION = "section-split-v2"

# A body heading at the start of a line: "489. ", "489-\nF. ", "108-\nA \n",
# "22-A. ". The letter counts only before a full stop or the end of its line.
SECTION_HEADING = re.compile(
    r"^\s*(\d+)(?:\s*-?\s*([A-Z]{1,2})[ \t]*(?:\.|(?=\n))|\s*[.\-])\s+(?=\S)", re.M)
# The letter printed after the title: "298- Misuse of epithets ...: \nB. ("
DEFERRED_LETTER_HEADING = re.compile(
    r"^[ \t]*(\d+)[ \t]*-[ \t]+[^\n]{3,200}:[ \t]*\n[ \t]*([A-Z]{1,2})[ \t]*\.", re.M)
# A footnote quoting the text of a provision that was omitted.
_OMITTED_MARKER = re.compile(r"(?mi)^[^\n]*?\bomitted by\b([^\n]*?)\s*:\s*:[ \t]*$")
_QUOTED_HEAD = re.compile(r"\s*(\d+)(?:\s*-\s*([A-Z]{1,2}))?(?=[\s.])")
# A body schedule heading on a line of its own ("SCHEDULE  I", "SCHEDULE - V").
# The contents page reads "SCHEDULE I.- [Repealed]." and never matches.
_SCHEDULE_LINE = re.compile(r"(?m)^[ \t]*SCHEDULE[^\w\n]*(V|IV|I{1,3})[ \t]*$")


# ── section-split-v3 (2026-10-16): additions for FUTURE ingestion only ────────
#
# v2 stays exactly as it was: scripts/build_sec_v2_index.py reproduces the live
# criminal__sec_v2 index with it, and existing chunks are never relabelled by a
# parser change. v3 is opt-in (`version=SPLIT_VERSION_V3`) and ADDS three rules
# found by the isolated legal-sources pilot on official Pakistan Code PDFs:
#
#   1. An INSERTED section printed behind its amendment footnote marker:
#        "1[26A, Punishment for false and fake information.--Whoever ..."
#        " 4[35A. Variation of rates. ___(1) The ad valorem fees ..."
#      v2's line-anchored heading needs the digits first, so these were filed
#      under the PRECEDING section (PECA s.26-A inside s.26 "Spoofing").
#   2. A lettered section printed in parentheses with a heading dash:
#        "(2E) Removal of Chairperson and members.__ (1) The Federal ..."
#      Accepted only with a letter suffix AND a short title ending in a heading
#      dash -- "(2) The Federal Government ..." and "(2A) Notwithstanding ..."
#      (subsections) never qualify.
#   3. An omitted/repealed provision printed as its number and asterisks or a
#      bare marker -- "16. 3[*  *  *  *  *  *  *]", "2. [Repealed]" -- is
#      recorded `provision_status="omitted"`, never as operative text.
#
# Rules 1 and 2 only ADD headings, and only where the new heading fits the
# order of its neighbours (26-A after 26 and before 27): a footnote number or a
# subsection can never take a section's place. Footnote lines at page bottoms
# ("2Ins. by A. O., 1937", "1Subs. by Act No. II of 2025") are untouched by
# design and pinned by tests.
SPLIT_VERSION_V3 = "section-split-v3"
SPLIT_VERSIONS = (SPLIT_VERSION, SPLIT_VERSION_V3)

_BRACKETED_HEADING = re.compile(
    r"^[ \t]*\d{1,2}\[[ \t]*(\d{1,3})(?:[ \t]*-?[ \t]*([A-Z]{1,2}))?[ \t]*[.,][ \t]+(?=[A-Z\"'“‘(])",
    re.M)
_PAREN_HEADING = re.compile(
    # The title ends in "." -- or "," as printed in "(2T) Social Media Complaint
    # Council,__" -- and then the heading dash, which a subsection never has.
    r"^[ \t]*\((\d{1,3})([A-Z]{1,2})\)[ \t]+(?=[A-Z][^\n]{2,160}?[.,][ \t]*(?:_{1,3}|[—–]|--))",
    re.M)
# 5. A heading whose full stop is followed directly by the PDF's underscore
#    dash, with no space: "11.___Procedure in suits ...", "19I.___ Payment
#    ...". v2 needs whitespace after the stop and missed both.
_UNDERSCORE_HEADING = re.compile(
    r"^[ \t]*(\d{1,3})(?:[ \t]*-?[ \t]*([A-Z]{1,2}))?[ \t]*\.[ \t]*_{2,}[ \t]*(?=[A-Z])", re.M)
# 6. A FOOTNOTE that v2 read as a section: "14 S. 123A ins. by the Pakistan
#    Penal Code (Amdt.) Act, 1950" and "1S. 153B was ins. by ..." -- "S." is
#    "Section", not a section letter. v3 never treats these as provisions.
_FOOTNOTE_ARTIFACT = re.compile(
    r"\d{1,3}[ \t]*-?[ \t]*S[ \t]*\.[ \t]*\d{1,3}[A-Z]{0,2}[ \t,]+(?:was[ \t]+)?"
    r"(?:ins|subs|omitted|rep|added|renumbered|substituted|inserted)\b", re.I)
_OMITTED_BODY = re.compile(
    r"^\s*\d{1,3}(?:\s*-?\s*[A-Z]{1,2})?\s*[.\-]\s*(?:\d{1,2}\s*)?"
    r"(?:\[\s*\*(?:[\s*]*)\]|\[?\s*(?:Omitted|Repealed)\b[^\n\]]{0,80}\]?)\s*\.?\s*$", re.I)


# 4. A contents page that lists the schedules ("SCHEDULE I / SCHEDULE II" on
#    lines of their own) ends v2's body at the CONTENTS page, so every real
#    section after it is filed as "schedule" text and only contents stubs are
#    "sections" (Court-Fees Act, Pakistan Code PDF). v3 treats the text before
#    the Act restarts at "1." -- after a schedule line -- as a contents region.
# The Act restarts at section 1, "Short title ..." -- not at item 1 of a
# numbered schedule ("SCHEDULE I / 1. Plaint ...").
_SECTION_ONE = re.compile(r"(?m)^[ \t]*1[ \t]*\.[ \t]*_*[ \t]*Short[ \t]+title")
_HEADING_LINE = re.compile(
    r"(?m)^[ \t]*(?:CHAPTER|PART|ORDER)\b[^\n]*$"            # CHAPTER V / PART I / ORDER XLVI
    r"|^[ \t]*[A-Z][A-Z ,.'&-]{3,80}[ \t]*$"                 # OF THE MODE OF LEVYING FEES
    r"|^[ \t]*[A-Z][ \t]*\.[ \t]*[–—-]{1,2}[^\n]{0,100}$")   # D.- Conferment, Continuance ...


def _contents_end(text: str) -> int:
    """Offset where the Act restarts after a contents page, or 0."""
    first_sched = _SCHEDULE_LINE.search(text)
    if not first_sched:
        return 0
    for m in _SECTION_ONE.finditer(text):
        if m.start() > first_sched.start():
            return m.start()
    return 0


# "9A. [Power to dispense with notices ...] Omitted by F.A.O. 1975, Art.2 ..."
_BRACKETED_TITLE_OMITTED = re.compile(
    r"^\s*\d{1,3}(?:\s*-?\s*[A-Z]{1,2})?\s*\.\s*\[[^\]\n]{1,200}\]\s*\.?\s*"
    r"(?:Omitted|Repealed|Rep\.)\s+by\b[^\n]{0,200}$", re.I)
_STAR_RUN = re.compile(r"\*(?:[\s*]*\*)?")
_STAR_MARK = re.compile(r"\d{0,2}\[\s*\*[\s*]*\]")
# A title ENDS at its dash: "7. Provincial Small Cause Courts.- ". Any words
# after the dash are operative text ("116. Part to apply ...- This Part applies
# only to High Courts 4[* * *]" is LIVE with some words omitted, not omitted).
_TITLE_SEGMENT = re.compile(r"\s*\d{1,3}[A-Z]{0,2}\s*\.\s*[^\n–—]{1,120}?[–—]\s*")


def _only_titles_and_asterisks(text: str) -> bool:
    """'6[7. Provincial Small Cause Courts.- * * * *] 7 [8. Presidency ...- * * *]':
    nothing but section titles and omission asterisks -- no operative words."""
    if "*" not in text:
        return False
    rest = _STAR_RUN.sub(" ", text)
    rest = re.sub(r"\d{0,2}\s*\[|\]", " ", rest).strip()
    segments = [s for s in re.split(r"(?=(?<!\d)\d{1,3}[A-Z]{0,2}\s*\.\s)", rest) if s.strip()]
    return bool(segments) and all(_TITLE_SEGMENT.fullmatch(s) for s in segments)


def _marked_omitted(part: str) -> bool:
    """'16. 3[* * *]', '24. [Repealed] CHAPTER V ...', '9A. [Title] Omitted by
    ...' -- the provision itself is only a marker; trailing chapter/part
    heading lines are not its text."""
    lines = (part or "").strip().splitlines()
    # "FEES IN THE HIGH COURTS 1[* * *]" is still a heading line: its own
    # omission marker is not operative text.
    while len(lines) > 1 and (not lines[-1].strip()
                              or _HEADING_LINE.match(_STAR_MARK.sub("", lines[-1]).rstrip())):
        lines.pop()
    body = "\n".join(lines)
    flat = " ".join(body.split())
    return bool(_OMITTED_BODY.match(body) or _BRACKETED_TITLE_OMITTED.match(flat)
                or _only_titles_and_asterisks(flat))


def _order_key(section: str) -> tuple[int, str]:
    m = re.match(r"^(\d+)([A-Z]{0,2})$", section or "")
    return (int(m.group(1)), m.group(2)) if m else (-1, "")


def _admit_in_order(heads: dict[int, dict], extra: dict[int, dict]) -> None:
    """Add v3 candidate headings that fit strictly between their neighbours."""
    for pos in sorted(extra):
        if pos in heads:
            continue
        before = [p for p in heads if p < pos]
        after = [p for p in heads if p > pos]
        key = _order_key(extra[pos]["section"])
        prev_key = _order_key(heads[max(before)]["section"]) if before else (-1, "")
        next_key = _order_key(heads[min(after)]["section"]) if after else (10 ** 6, "")
        if prev_key < key < next_key:
            heads[pos] = extra[pos]


def split_provisions(text: str, version: str = SPLIT_VERSION) -> list[dict]:
    """Ordered provision blocks of one statute's text. Pure and deterministic.

    Each block: section ("489F", "" for a schedule, None before the first
    heading), text, region ("preamble" | "body" | "footnote_quote" |
    "schedule"), schedule (roman numeral or None), heading_rule ("standard" |
    "deferred_letter" | "footnote_quote" | v3: "bracketed_insertion" |
    "parenthesised" | None), provision_status ("omitted" only when the source
    says so, else "not_recorded"), omitted_by.

    `version` defaults to section-split-v2, the parser behind the existing
    indexes; pass SPLIT_VERSION_V3 for future ingestion (see above).
    """
    if version not in SPLIT_VERSIONS:
        raise ValueError(f"unknown split version {version!r}")
    v3 = version == SPLIT_VERSION_V3
    text = text or ""
    if v3:
        cut = _contents_end(text)
        if cut:
            # Kept, not dropped, but never read as provisions: region "contents".
            contents = text[:cut].strip()
            head = [{"section": None, "text": contents, "region": "contents", "schedule": None,
                     "heading_rule": None, "provision_status": "not_recorded", "omitted_by": None}] if contents else []
            return head + _split_body(text[cut:], v3=True)
    return _split_body(text, v3)


def _split_body(text: str, v3: bool) -> list[dict]:
    sched = list(_SCHEDULE_LINE.finditer(text))
    body_end = sched[0].start() if sched else len(text)
    body = text[:body_end]

    heads: dict[int, dict] = {}
    for m in SECTION_HEADING.finditer(body):
        heads[m.start(1)] = {"section": m.group(1) + (m.group(2) or ""), "heading_rule": "standard"}
    for m in DEFERRED_LETTER_HEADING.finditer(body):
        heads[m.start(1)] = {"section": m.group(1) + m.group(2), "heading_rule": "deferred_letter"}
    for m in _OMITTED_MARKER.finditer(body):
        q = _QUOTED_HEAD.match(body, m.end())
        if q:
            heads[q.start(1)] = {"section": q.group(1) + (q.group(2) or ""), "heading_rule": "footnote_quote",
                                 "omitted_by": " ".join(m.group(1).split()) or None}
    if v3:
        # Both patterns are line-anchored; a block starts at the first
        # non-blank character, so an inserted provision keeps its "1["
        # amendment pointer in its own text.
        def _first_char(m: re.Match) -> int:
            return m.start() + len(m.group(0)) - len(m.group(0).lstrip())
        for pos in [p for p, h in heads.items() if h["heading_rule"] == "standard"
                    and h["section"].endswith("S") and _FOOTNOTE_ARTIFACT.match(body, p)]:
            del heads[pos]
        extra: dict[int, dict] = {}
        for m in _UNDERSCORE_HEADING.finditer(body):
            extra[_first_char(m)] = {"section": m.group(1) + (m.group(2) or ""),
                                     "heading_rule": "underscore_dash"}
        for m in _BRACKETED_HEADING.finditer(body):
            extra[_first_char(m)] = {"section": m.group(1) + (m.group(2) or ""),
                                     "heading_rule": "bracketed_insertion"}
        for m in _PAREN_HEADING.finditer(body):
            extra[_first_char(m)] = {"section": m.group(1) + m.group(2), "heading_rule": "parenthesised"}
        _admit_in_order(heads, extra)

    blocks: list[dict] = []
    starts = sorted(heads)
    if not starts or starts[0] > 0:
        pre = body[: starts[0] if starts else len(body)].strip()
        if pre:
            blocks.append({"section": None, "text": pre, "region": "preamble", "schedule": None,
                           "heading_rule": None, "provision_status": "not_recorded", "omitted_by": None})
    for k, pos in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(body)
        h = heads[pos]
        part = body[pos:end].strip()
        if not part:
            continue
        quoted = h["heading_rule"] == "footnote_quote"
        # v3: "16. 3[* * *]" / "2. [Repealed]" -- the source says it is gone.
        marked = v3 and not quoted and _marked_omitted(part)
        blocks.append({"section": h["section"], "text": part,
                       "region": "footnote_quote" if quoted else "body", "schedule": None,
                       "heading_rule": h["heading_rule"],
                       "provision_status": "omitted" if (quoted or marked) else "not_recorded",
                       "omitted_by": h.get("omitted_by")})
    for k, m in enumerate(sched):
        end = sched[k + 1].start() if k + 1 < len(sched) else len(text)
        part = text[m.start():end].strip()
        if part:
            blocks.append({"section": "", "text": part, "region": "schedule", "schedule": m.group(1),
                           "heading_rule": None, "provision_status": "not_recorded", "omitted_by": None})
    return blocks


def section_label(section: str | None) -> str:
    """"489F" -> "489-F" (the human form); "" stays ""."""
    m = re.match(r"^(\d+)([A-Z]{1,2})$", section or "")
    return f"{m.group(1)}-{m.group(2)}" if m else (section or "")
