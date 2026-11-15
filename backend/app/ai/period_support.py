"""Does the evidence actually state a period that a client answer asserts?

WHY THIS EXISTS (2026-10-13, client chat)
-----------------------------------------
A live answer said a dishonoured-cheque claim must be sued on "within three
years ... under Section 6 of the Limitation Act", and the grounding judge
marked it supported. The chunk cited as "Limitation Act 1908, s.6" is really
a slice of the First Schedule (the corpus labels schedule text under s.6), and
it does contain "Three years" -- for specific performance, rescission and
breach of contract (Articles 113-115), not for a cheque. A citation that
resolves, and even a source that contains the same number, is not support.

So a period (N days / weeks / months / years) stated in an answer passes only
when a source the sentence relies on (1) states that same period and (2) states
it NEXT TO the sentence's own subject matter: the passage around the period
shares at least one subject term with the sentence ("cheque", "rent", "decree",
...). Generic procedure words ("suit", "appeal", "limitation", "court") do not
count -- they occur beside every period in a limitation schedule. And (3) when
the period sits inside a SCHEDULE ENTRY ("58.- Like suit when the lender has
given a cheque ... [Three years]"), the sentence must name that article: the
live run cited "Section 6" for a cheque deadline, found "cheque" beside
"Three years" in Article 58 (a loan paid by the lender's cheque), and one
shared word was enough to pass. A shared word is not legal support; the
article that sets the period is.

Deliberately conservative, and deterministic (no model call):
  * it can only REMOVE an asserted period, never add or change one;
  * a correct period whose source words it differently ("a month" vs "30
    days", "cheque" vs "bill of exchange") is removed too -- the answer then
    says the period could not be confirmed, which is the safe failure;
  * hours are not checked, so urgent safety text ("within 24 hours", "call
    15") is never touched;
  * an Urdu-script sentence is compared through its Latin-script words and
    the deterministic Urdu legal-term map (ai/legal_terms.py); when neither
    yields a subject term the period counts as unverifiable and is removed.

No period is ever supplied from outside the evidence: there is no table of
"correct" limitation periods here, by design.
"""
from __future__ import annotations

import re

from app.ai.answer_citations import (
    _MARKERS_ONLY,
    _marker_ids,
    attach_trailing_markers,
    evidence_index,
    extract_citations,
)

# ── period mentions ──────────────────────────────────────────────────────────

_ONES = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
         "ninety": 90}
_EN_NUM = {
    **_ONES, **_TENS,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
    # Compounds: "twenty-five years" (PPC 302(c)) was read as FIVE years.
    **{f"{t}-{o}": tv + ov for t, tv in _TENS.items() for o, ov in _ONES.items()},
    **{f"{t} {o}": tv + ov for t, tv in _TENS.items() for o, ov in _ONES.items()},
}
_UR_NUM = {
    "ایک": 1, "دو": 2, "تین": 3, "چار": 4, "پانچ": 5, "چھ": 6, "سات": 7, "آٹھ": 8,
    "نو": 9, "دس": 10, "بارہ": 12, "پندرہ": 15, "بیس": 20, "تیس": 30, "ساٹھ": 60,
    "نوے": 90,
}
_ROMAN_NUM = {
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "panch": 5, "paanch": 5,
    "chay": 6, "chhe": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10, "barah": 12,
    "pandrah": 15, "bees": 20, "tees": 30, "saath": 60, "nawway": 90, "nabbe": 90,
}
_UNITS = {
    "day": "day", "days": "day", "din": "day", "دن": "day", "یوم": "day", "ایام": "day",
    "week": "week", "weeks": "week", "hafta": "week", "hafte": "week", "ہفتہ": "week",
    "ہفتے": "week",
    "month": "month", "months": "month", "mahina": "month", "mahine": "month",
    "maah": "month", "ماہ": "month", "مہینہ": "month", "مہینے": "month",
    "year": "year", "years": "year", "saal": "year", "sal": "year", "baras": "year",
    "سال": "year", "برس": "year",
}
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_SPACES = str.maketrans({" ": " ", " ": " ", " ": " ", " ": " ",
                         "‐": "-", "‑": "-", "‒": "-", "–": "-",
                         "—": "-"})

_NUM_ALT = "|".join(sorted((re.escape(w) for w in [*_EN_NUM, *_UR_NUM, *_ROMAN_NUM]),
                           key=len, reverse=True))
_UNIT_ALT = "|".join(sorted((re.escape(u) for u in _UNITS), key=len, reverse=True))
# Word boundaries by lookaround: \b is unreliable around Urdu script.
_PERIOD = re.compile(
    rf"(?<![\w])(\d{{1,3}}|{_NUM_ALT})[\s\-]*(?:\(\s*\d{{1,3}}\s*\)\s*)?({_UNIT_ALT})(?![\w])",
    re.IGNORECASE,
)


def normalise(text: str) -> str:
    return (text or "").translate(_SPACES).translate(_DIGITS)


def _value(token: str) -> int | None:
    low = token.lower()
    if low.isdigit():
        return int(low)
    return _EN_NUM.get(low) or _UR_NUM.get(token) or _ROMAN_NUM.get(low)


def periods_in(text: str) -> list[tuple[tuple[int, str], int]]:
    """[((value, unit), position)] for every period mention, in order."""
    out = []
    for m in _PERIOD.finditer(normalise(text)):
        n = _value(m.group(1))
        unit = _UNITS.get(m.group(2).lower()) or _UNITS.get(m.group(2))
        if n and unit:
            out.append(((n, unit), m.start()))
    return out


# ── subject terms ─────────────────────────────────────────────────────────────

_GENERIC = frozenset("""
section sections act acts law laws code ordinance order article articles schedule rule rules
limitation limitations period periods time date dates within under from when which where there
their these those that this with without against shall must have will would should could after
before being upon made such other than into also only more less about apply applies applied
suit suits sued sue suing appeal appeals appealed application applications apply file filed filing
files institute instituted institution court courts case cases claim claims legal right rights
year years month months week weeks days provided provides provision provisions under clause
pakistan pakistani punjab sindh federal province penal criminal civil procedure qanun shahadat
first second third part chapter note notes general description beginning runs begins
recovery recover recovering
gave give given gives giving brought bring brings taken take takes make makes done become becomes
means mean must also like said same ditto prescribed prescribes prescribe required requires
""".split())
_WORD = re.compile(r"[a-z]{4,}")
_URDU = re.compile(r"[؀-ۿ]")
_WINDOW = 300


def _stem(word: str) -> str:
    """Crude, deterministic: "fails" / "failed" / "failing" -> "fail"."""
    for suffix in ("'s", "ies", "ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return word


def subject_terms(text: str) -> set[str]:
    words = _WORD.findall(normalise(text).lower())
    number_words = set(_EN_NUM) | set(_ROMAN_NUM)
    return {_stem(w) for w in words if w not in _GENERIC and w not in number_words
            and w not in _UNITS}


# ── support ──────────────────────────────────────────────────────────────────

def _sources_for(sentence: str, evidence: list[dict]) -> list[dict]:
    """The evidence a sentence relies on.

    A sentence that NAMES a provision rests on that provision alone: only the
    named provisions that resolve in the evidence count, and a [n] marker
    pointing elsewhere does not ("three years under Section 6 of the
    Limitation Act [1]" with [1] a CrPC passage is not supported by [1]). A
    named provision absent from the evidence supports nothing. A sentence that
    names nothing relies on its markers, or on any source if it has none."""
    by_id = {e["id"]: e for e in evidence}
    named = extract_citations(sentence)
    if named:
        # EVERY chunk of a named provision: a section is often split across
        # chunks (Limitation Act s.8: its rule and its illustrations), and the
        # index keeps only the first.
        keys = {c.key for c in named}
        hits = [e for e in evidence if e.get("kind") == "statute"
                and set(evidence_index([e])) & keys]
        # A deterministic engine result that names the provision ("PPC:506",
        # with its punishment) is that provision's computed data.
        for c in named:
            law, sec = c.key[0].split()[0], re.sub(r"\W", "", c.section)
            hits += [e for e in evidence if e.get("kind") == "engine" and re.search(
                rf"\b{law}\s*:\s*{sec}\b", e.get("content", ""), re.IGNORECASE)]
        return list({id(h): h for h in hits}.values())
    cited = [by_id[i] for i in _marker_ids(sentence, set(by_id))]
    return cited or list(evidence)


_CLAUSE = re.compile(r"[,;:()\[\]]|\s(?:and|but|or|while|whereas)\s", re.IGNORECASE)


def _clause_terms(sentence: str, period: tuple[int, str]) -> set[str]:
    """Subject terms of the clause that states `period` -- not the whole
    sentence: "sued within three years of the cheque's dishonour, and the court
    may award interest" makes two claims, and "interest" must not lend support
    to the period."""
    text = normalise(sentence)
    for p, pos in periods_in(text):
        if p != period:
            continue
        start = max((m.end() for m in _CLAUSE.finditer(text, 0, pos)), default=0)
        nxt = _CLAUSE.search(text, pos)
        clause = text[start: nxt.start() if nxt else len(text)]
        terms = subject_terms(_PERIOD.sub(" ", clause))
        if terms:
            return terms
    return subject_terms(_PERIOD.sub(" ", text))


def _urdu_terms(sentence: str) -> set[str]:
    """English subject terms for an Urdu-script sentence: its Latin-script
    words (statute names, English terms the model kept) plus the deterministic
    Urdu legal-term map. Usually small -- see period_supported."""
    from app.ai.legal_terms import legal_terms
    latin = subject_terms(_PERIOD.sub(" ", normalise(sentence)))
    return latin | subject_terms(" ".join(legal_terms(sentence)))


# A schedule ENTRY header ("58.- Like suit when ...", "113.- For specific
# performance ..."): limitation schedules list one article per suit, each with
# its own period. Section text is numbered "34. Interest.-", which this does
# not match.
_ENTRY = re.compile(r"(?<![\d.])(\d{1,3})\.\s*-\s*(?=[A-Z])")
_ARTICLE_REF = r"(?:Article|Art\.?)\s*{n}(?!\d)"


# Schedule text WITHOUT any entry header in the chunk: a continuation slice.
# Recognised by the schedule's own layout -- a bracketed period ("[Three
# years]", the amended-entry form) or the column headings.
# Column headings occur only in a schedule. A bracketed period ("[Three
# years]", the amended-entry form) marks schedule text only in a limitation
# statute: sections elsewhere carry bracketed amendments too, and the Punjab
# Tenancy Act s.81 even says "the period of limitation" in its own text.
_SCHEDULE_HEADINGS = re.compile(
    r"time\s+from\s+which\s+period\s+begins|description\s+of\s+(?:suit|application|appeal)", re.IGNORECASE)
_BRACKETED_PERIOD = re.compile(r"\[\s*(?:\w+|\d+)\s+(?:days?|weeks?|months?|years?)\s*\]", re.IGNORECASE)


def _schedule_layout(content: str, statute: str) -> bool:
    if _SCHEDULE_HEADINGS.search(content):
        return True
    return "limitation" in (statute or "").lower() and bool(_BRACKETED_PERIOD.search(content))
# Provision-level match inside a schedule entry (see period_supported).
_CLAIM_MISSING_MAX = 0.25
_ENTRY_COVERED_MIN = 0.5


def _schedule_entry(content: str, pos: int, statute: str = "") -> tuple[str | None, str, str] | None:
    """For a chunk that is a slice of a schedule: (article, entry text) of the
    entry holding the period at `pos`. None when the chunk is not a schedule.

    The article is None when the entry's header lies OUTSIDE the chunk -- the
    chunk began mid-entry, so which article sets this period is unknowable.
    The entry text runs from its header to the next one: a window crossing
    into the neighbouring article would borrow its words (the live c23 run
    matched "cheque" from Article 58 to a period of Article 57)."""
    headers = list(_ENTRY.finditer(content))
    if not headers:
        # No header at all, but schedule layout: a continuation slice whose
        # article is unknowable. Fail closed (article None).
        if _schedule_layout(content, statute):
            return None, content, ""
        return None
    before = [h for h in headers if h.start() <= pos]
    after = [h for h in headers if h.start() > pos]
    start = before[-1].start() if before else 0
    end = after[0].start() if after else len(content)
    # (article, whole entry, DESCRIPTION column = heading up to the period)
    return (before[-1].group(1) if before else None), content[start:end], content[start:pos]


# Limitation vocabulary (ai/issue_lookup.py's issue): a sentence stating WHEN a
# suit must be brought, when the period runs, or that a claim is time-barred.
_ISSUE_TALK = re.compile(
    r"\b(?:limitation|time[- ]?(?:limit|barred|bar)|barred|suit|sue|fil(?:e|ed|ing)|institut\w*|brought|"
    r"deadline|period|clock|starts?|runs?|begins?|computed|counted|expire\w*|lapse\w*)\b"
    r"|مدت|میعاد|دعو[یٰ]|دائر|مقدم[ہے]|شروع|شمار|زائد\s*المیعاد|dayar|muddat|miyad", re.IGNORECASE)


def period_supported(sentence: str, period: tuple[int, str], evidence: list[dict]) -> bool:
    # Dash/space-normalised first: "Section 489‑F" (non-breaking hyphen) read
    # as section 489 -- absent from the evidence -- and a true period of
    # 489-F was removed (live final run, c01 with the policy off).
    sentence = normalise(sentence)
    # Lawyer research: a source fetched as THE provision governing this
    # question's issue (its own heading names the issue -- "30. Limitation",
    # ai/issue_lookup.py) states the period for this matter by definition. The
    # subject-word test below withdrew "the Act itself prescribes a four-month
    # limitation period" and every Urdu "چار ماہ" while s.30 said exactly that
    # (eval V4 / V6). A sentence naming a DIFFERENT provision still rests on
    # that provision alone (_sources_for). Client chat never sets the flag.
    # The sentence must speak of the issue that provision governs: "the buyer
    # must pay the price within four months" borrows s.30's number for a
    # different point and is still withheld.
    if _ISSUE_TALK.search(sentence):
        for source in _sources_for(sentence, evidence):
            if source.get("issue_provision") and period in {
                    p for p, _ in periods_in(normalise(source.get("content", "")))}:
                return True
    sentence_terms = set() if _URDU.search(sentence) else subject_terms(_PERIOD.sub(" ", sentence))
    if _URDU.search(sentence):
        # The sources are English, so an Urdu sentence's subject can only be
        # read through _urdu_terms. When it yields nothing the period cannot be
        # tied to this matter, and an unverifiable period is treated as
        # unsupported: "تین سال" next to a contract article must not pass for
        # a cheque. This over-removes some correct Urdu periods -- the safe way
        # round.
        terms = _urdu_terms(sentence)
        if not terms:
            return False
    else:
        terms = _clause_terms(sentence, period)
    for source in _sources_for(sentence, evidence):
        content = normalise(source.get("content", ""))
        for found, pos in periods_in(content):
            if found != period:
                continue
            # A period inside a schedule entry is established by THAT article.
            # The corpus files schedule text under a section ("Limitation Act
            # 1908, s.6" holds Articles 57-62 and 113-117), so "three years
            # under Section 6" can find a "Three years" in the cited chunk --
            # Article 58, a LOAN the lender paid by cheque -- and still be
            # false. Without the article named, the entry does not support it.
            entry = _schedule_entry(content, pos, source.get("statute", ""))
            if entry is not None:
                article, window, description = entry
                if article is None or not re.search(_ARTICLE_REF.format(n=article),
                                                    normalise(sentence), re.IGNORECASE):
                    continue
                # PROVISION-LEVEL match: naming Article 58 and sharing the word
                # "cheque" does not make "a dishonoured-cheque suit" an Article
                # 58 suit (a loan the LENDER paid by cheque). The claim must
                # describe this entry's suit: nearly all of the claim's subject
                # terms appear in the entry, and most of the entry's DESCRIPTION
                # (the "description of suit" column) appears in the claim.
                entry_terms = subject_terms(_PERIOD.sub(" ", window))
                desc_terms = subject_terms(_PERIOD.sub(" ", description))
                if not desc_terms or not terms:
                    continue
                missing = len(terms - entry_terms) / len(terms)
                covered = len(desc_terms & terms) / len(desc_terms)
                if missing <= _CLAIM_MISSING_MAX and covered >= _ENTRY_COVERED_MIN:
                    return True
                continue
            window = content[max(0, pos - _WINDOW): pos + _WINDOW]
            if source.get("kind") == "engine":
                # Structured engine output naming this provision (selected in
                # _sources_for): terse, so one shared subject term suffices.
                if terms & subject_terms(window):
                    return True
                continue
            # Section text: the SOURCE's own clause stating this period must
            # share a subject term with the claim. "(c) when the appeal lies to
            # the Board of Revenue - ninety days" does not support ninety days
            # for a civil-court decree, though "decree" occurs in the section's
            # opening words; and s.15(b)'s thirty days (from the rent falling
            # due) does not support "30 days after the notice ... eviction".
            # (An earlier "half the claim's words" rule removed true periods --
            # 506's two years -- and is subsumed by this one.)
            local_terms = subject_terms(_PERIOD.sub(" ", _source_clause(content, pos)))
            # The claim's own clause first; if comma-splitting left it without
            # its subject ("..., potentially up to seven years"), the whole
            # sentence -- still checked against the source's clause.
            if terms & local_terms or sentence_terms & local_terms:
                return True
    return False


_SOURCE_BOUNDARY = re.compile(r";|\(\s*[a-z]{1,4}\s*\)|\(\s*\d{1,2}\s*\)|(?<=[a-z])\.\s+(?=[A-Z(])")


def _source_clause(content: str, pos: int) -> str:
    """The clause of the SOURCE that states the period at `pos`: bounded by
    ";", an enumeration marker "(a)" / "(2)", or a sentence end."""
    lo = max(0, pos - _WINDOW)
    start = max((m.end() for m in _SOURCE_BOUNDARY.finditer(content, lo, pos)), default=lo)
    nxt = _SOURCE_BOUNDARY.search(content, pos, min(len(content), pos + _WINDOW))
    return content[start: nxt.start() if nxt else min(len(content), pos + _WINDOW)]


def unsupported_periods(sentence: str, evidence: list[dict] | None) -> list[tuple[int, str]]:
    """Periods the sentence asserts that no relied-on source supports."""
    found = []
    for period, _ in periods_in(sentence):
        if period not in found and not period_supported(sentence, period, evidence or []):
            found.append(period)
    return found


# ── rewriting the visible answer ─────────────────────────────────────────────

NOTICE_EN = ("The exact period for this (such as a time limit or a term of punishment) could "
             "not be confirmed from the legal sources available here, so it is not stated. "
             "Please confirm it with a lawyer promptly — time limits can be strict.")
NOTICE_UR = ("اس معاملے کی درست مدت (مثلاً مقررہ وقت یا سزا کی مدت) دستیاب قانونی ماخذ سے تصدیق نہیں ہو "
             "سکی، اس لیے یہاں درج نہیں کی گئی۔ براہِ کرم جلد کسی وکیل سے تصدیق کریں — مدتیں سخت ہو سکتی ہیں۔")

_SENT = re.compile(r"(?<=[.!?۔])\s+")
_EMPTY_LINE = re.compile(r"^\s*(?:[-*•]|\d+[.)]|\*\*[^*]{0,40}\*\*\s*:?|#{1,6})?\s*$")


# Lawyer research (2026-10-14): the same withdrawal, worded for a lawyer who
# will go and check the provision -- never a silent erase.
RESEARCH_NOTICE_EN = ("Period not verified: a time limit or term stated in the draft answer could not be "
                      "verified against the retrieved provision that governs THIS matter (for limitation, "
                      "the specific First Schedule article), so it has been withheld. Verify it directly "
                      "before relying on any deadline.")
RESEARCH_NOTICE_UR = ("مدت کی تصدیق نہیں ہوئی: جواب میں بیان کردہ کوئی مدت اس معاملے پر لاگو حاصل شدہ دفعہ (حدِ میعاد "
                      "کے لیے متعلقہ آرٹیکل) سے تصدیق نہیں ہو سکی، اس لیے روک لی گئی ہے۔ کسی بھی مدت پر انحصار سے پہلے "
                      "براہِ راست تصدیق کریں۔")


def strip_unsupported_periods(answer: str, evidence: list[dict] | None,
                              urdu: bool = False, notice: str | None = None) -> tuple[str, list[str]]:
    """Remove every sentence asserting an unsupported period; put one notice
    where the first one was. Returns (new answer, removed sentences)."""
    removed: list[str] = []
    out_lines: list[str] = []
    notice_placed = False
    for line in (answer or "").split("\n"):
        parts = attach_trailing_markers(_SENT.split(line))
        kept = []
        for part in parts:
            if periods_in(part) and unsupported_periods(part, evidence):
                removed.append(part.strip())
                continue
            kept.append(part)
        if len(kept) == len(parts):
            out_lines.append(line)
            continue
        new_line = " ".join(kept).rstrip()
        if _MARKERS_ONLY.match(new_line):
            new_line = ""
        if not notice_placed:
            out_lines.append(notice or (NOTICE_UR if urdu else NOTICE_EN))
            notice_placed = True
        if new_line and not _EMPTY_LINE.match(new_line):
            out_lines.append(new_line)
    return "\n".join(out_lines), removed


def withdraw_claims(claims: list[dict], evidence: list[dict] | None) -> list[dict]:
    """Mark a claim asserting an unsupported period as unsupported, whatever
    the judge said. Only ever downgrades."""
    for claim in claims or []:
        bad = unsupported_periods(claim.get("text", ""), evidence)
        if bad:
            claim["support"] = "unsupported"
            claim["support_reason"] = "period_not_stated_for_this_matter_in_cited_source"
    return claims
