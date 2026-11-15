"""Validate the legal assertions in the FINAL visible research answer
(lawyer research, safeguards on; 2026-10-14).

A chip saying "unresolved" or "unsupported" beside a sentence does not stop a
lawyer from reading the sentence. Live eval RU2 (on_d2): the visible answer
advised bail "under Section 438 CrPC" (omitted in Pakistan), called criminal
breach of trust "Section 406 CrPC" (CrPC 406 is an appeal from a security
order; the offence is PPC 406) and listed "437-438 CrPC". E11 (on_d2): two
retrieved sections became "the Act itself is silent on the limitation period".
E11 (on_d1): a "Period not verified ... withheld" notice sat beside the
verified period it claimed to withhold.

Run in the finalizer on the text the lawyer will see, BEFORE citation chips,
the cache write, stored history and provenance read it -- nothing rewrites the
answer afterwards. Deterministic; every check reads the corpus (exact provision
text via exact_provision.fetch, headings via corpus_index), never a model.

  whole_act_silence  "the Act is silent / does not specify ..." -> replaced by
                     what the sources DO show, naming the provision whose own
                     heading governs the issue when the index knows one.
  precise_notice     the generic period notice, reworded when every withheld
                     period is still shown, verified, elsewhere.
  authorities        each Act + section the visible text names is checked:
                       omitted   its own text in the corpus is "[Omitted]"
                       absent    a statute held complete has no such section
                       mispaired the sentence describes an offence but cites a
                                 procedural code, or its words match another
                                 Act's same-numbered section and not this one
                       unverified no text, statute not held completely
                     The unit (sentence, list item or table row) is withheld
                     with a precise note; valid units are kept. When most of
                     the answer rests on invalid authority, a limited answer
                     is returned instead.

Lexical, stated: an invalid authority named without its Act ("s.438"), or a
wrong proposition about a VALID section, is not caught here.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

GUARD_VERSION = "visible-authority-v1"

# ── whole-Act silence ────────────────────────────────────────────────────────

# Case-SENSITIVE inside a case-insensitive pattern: an Act name starts with a
# capital. Folded, "that does not mean the Punjab ... Act" read as one name and
# swallowed the negation.
_ACT_NAME = r"(?-i:(?:[A-Z][\w‑\-]*(?:\s+(?:\([^)]{1,40}\)|[A-Z][\w‑\-]*|of|the|and))*\s+(?:Act|Ordinance|Code|Order))(?:,?\s*\d{4})?)"
_SILENT = re.compile(
    rf"(?P<act>\b(?:the|this)\s+(?:Act|Ordinance|Code)|{_ACT_NAME})(?:\s+itself)?,?\s+"
    r"(?:is\s+silent|remains\s+silent|(?:does\s+not|doesn't|did\s+not)\s+(?:itself\s+)?"
    r"(?:specify|prescribe|provide|contain|lay\s+down|mention|set\s+out|fix|stipulate)|contains\s+no|"
    r"has\s+no|provides\s+no|prescribes\s+no)\b"
    r"|\bno\s+(?:provision|period|time[- ]limit)\s+(?:is\s+)?(?:prescribed\s+|provided\s+)?(?:in|by|under)\s+the\s+"
    r"(?:Act|Ordinance|Code)\b"
    r"|(?:ایکٹ|آرڈیننس|قانون)\s+(?:خود\s+)?(?:اس\s+(?:بارے|معاملے)\s+میں\s+)?خاموش"
    r"|(?:ایکٹ|آرڈیننس)[^۔\n]{0,40}میں\s+کوئی[^۔\n]{0,40}(?:مقرر|درج|موجود)\s+نہیں",
    re.IGNORECASE)
# A sentence scoped to what was retrieved is honest, not an Act-wide claim.
_SCOPED = re.compile(r"\b(?:retrieved|supplied|provided|available|cited|given|quoted|these|above|excerpts?)\b"
                     r"|(?:فراہم|دستیاب|حاصل)\s*(?:کردہ|شدہ)"
                     # negated -- "that does not mean the Act is silent" is this guard's own wording
                     r"|\bdoes(?:\s+not|n't)\s+mean\b|مطلب\s+یہ\s+نہیں", re.IGNORECASE)

_SILENCE_EN = ("The sources used for this answer do not establish this point; that does not mean the {act} is "
               "silent on it.")
_SILENCE_GOVERNING_EN = ("The sources used for this answer do not establish this point; that does not mean the "
                         "{act} is silent on it -- its Section {section} is headed \"{heading}\" and should be read "
                         "directly.")
_SILENCE_UR = "اس جواب کے ماخذ یہ نکتہ ثابت نہیں کرتے؛ اس کا مطلب یہ نہیں کہ {act} اس بارے میں خاموش ہے۔"
# A later Act-wide sentence (e.g. the Conclusion repeating it) gets the short
# form, so a section heading is not left empty.
_SILENCE_AGAIN_EN = "The sources used for this answer do not establish this point (see above)."
_SILENCE_AGAIN_UR = "اس جواب کے ماخذ یہ نکتہ ثابت نہیں کرتے (اوپر دیکھیں)۔"
_SILENCE_GOVERNING_UR = ("اس جواب کے ماخذ یہ نکتہ ثابت نہیں کرتے؛ اس کا مطلب یہ نہیں کہ {act} اس بارے میں خاموش ہے — "
                         "اس کی دفعہ {section} کا عنوان \"{heading}\" ہے، اسے براہِ راست پڑھیں۔")

# Never after "Sec." (2026-10-15): the drafter's normaliser writes Urdu "سیکشن" / "دفعہ" as "Sec." (same length) and
# the sentence was cut there -- "... درخواست Sec. | 354، CrPC 1898 کے تحت ..." -- so the claim and its citation were
# judged apart (an Urdu citation's subject became "unreadable", and S3 read "354" as a bare number).
_UNIT_SPLIT = re.compile(r"(?<!\bSec\.)(?<=[.!?۔])\s+(?=\S)")
_LIST_ITEM = re.compile(r"^\s*(?:\d{1,2}[.)]|[-*•])\s")


def _units(text: str) -> list[tuple[int, int]]:
    """(start, end) of each line; within a non-table line, each sentence."""
    spans, pos = [], 0
    for line in text.split("\n"):
        start = pos
        pos += len(line) + 1
        if not line.strip():
            continue
        # A table row or a list item is ONE unit: splitting "3. **s.239 and
        # 437-438 CrPC** ..." after "3." left the bare marker behind.
        if line.lstrip().startswith("|") or _LIST_ITEM.match(line):
            spans.append((start, start + len(line)))
            continue
        cut = start
        for m in _UNIT_SPLIT.finditer(line):
            spans.append((cut, start + m.start()))
            cut = start + m.end()
        spans.append((cut, start + len(line)))
    return [(a, b) for a, b in spans if text[a:b].strip()]


def whole_act_silence(answer: str, question: str, province: str | None, urdu: bool) -> tuple[str, list[str]]:
    """(answer, replaced sentences). A sentence asserting a whole Act is silent
    is replaced, once, by what the sources do and do not show."""
    from app.ai import issue_lookup
    hits = []
    for a, b in _units(answer):
        unit = answer[a:b]
        m = _SILENT.search(unit)
        if m and not _SCOPED.search(unit[: m.start()] + unit[m.end(): m.end() + 30]):
            hits.append((a, b, (m.groupdict().get("act") or "").strip()))
    if not hits:
        return answer, []
    governing = issue_lookup.governing_label(question, province)
    named = next((h[2] for h in hits if h[2] and not re.match(r"(?i)(?:the|this)\s", h[2])), "")
    act = (governing[0][0] if governing else "") or named or ("ایکٹ" if urdu else "Act")
    if governing:
        statute, section, heading = governing[0]
        repl = (_SILENCE_GOVERNING_UR if urdu else _SILENCE_GOVERNING_EN).format(
            act=statute, section=section, heading=heading)
    else:
        repl = (_SILENCE_UR if urdu else _SILENCE_EN).format(act=act)
    out, last, replaced = [], 0, []
    for i, (a, b, _) in enumerate(hits):
        out.append(answer[last:a])
        out.append(repl if i == 0 else (_SILENCE_AGAIN_UR if urdu else _SILENCE_AGAIN_EN))
        replaced.append(answer[a:b])
        last = b
    out.append(answer[last:])
    return re.sub(r"\n{3,}", "\n\n", "".join(out)), replaced


# ── period notice precision ──────────────────────────────────────────────────

PRECISE_NOTICE_EN = ("Note: a further statement using this period was withheld because the cited provision does "
                     "not state it for that point; the period shown here is the one the cited provision states.")
PRECISE_NOTICE_UR = ("نوٹ: اسی مدت کو استعمال کرنے والا ایک اور بیان روک لیا گیا کیونکہ حوالہ دی گئی دفعہ اسے اس نکتے کے "
                     "لیے بیان نہیں کرتی؛ یہاں دکھائی گئی مدت وہی ہے جو دفعہ میں درج ہے۔")


def precise_notice(answer: str, removed: list[str], notice: str, urdu: bool) -> str:
    """Reword the period notice when every withheld period is still shown,
    verified, elsewhere -- "not verified ... withheld" beside a verified
    "four months" told the lawyer the opposite of the truth."""
    from app.ai import period_support
    if not removed or notice not in answer:
        return answer
    withheld = {p for s in removed for p, _ in period_support.periods_in(s)}
    shown = {p for p, _ in period_support.periods_in(answer.replace(notice, " "))}
    if withheld and withheld <= shown:
        return answer.replace(notice, PRECISE_NOTICE_UR if urdu else PRECISE_NOTICE_EN)
    # Partly shown (live e1 RU2 / C2, e2 E9): the generic notice beside a
    # visible period read as if THAT period were withheld. Name exactly the
    # period(s) withheld and not shown.
    hidden = sorted(withheld - shown)
    if hidden and withheld & shown:
        names = (" / " if urdu else ", ").join(_period_name(p, urdu) for p in hidden)
        return answer.replace(notice, (NAMED_NOTICE_UR if urdu else NAMED_NOTICE_EN).format(periods=names))
    return answer


NAMED_NOTICE_EN = ("Period not verified: a statement giving {periods} could not be verified against the provision "
                   "that governs this matter and has been withheld. Other periods shown are stated by their cited "
                   "provisions.")
NAMED_NOTICE_UR = ("مدت کی تصدیق نہیں ہوئی: {periods} بیان کرنے والا جملہ اس معاملے پر لاگو دفعہ سے تصدیق نہیں ہو سکا اور "
                   "روک لیا گیا ہے۔ دکھائی گئی دوسری مدتیں اپنی حوالہ دی گئی دفعات میں درج ہیں۔")
_UNIT_UR = {"day": "دن", "week": "ہفتے", "month": "ماہ", "year": "سال"}


def _period_name(period: tuple[int, str], urdu: bool) -> str:
    n, unit = period
    return f"{n} {_UNIT_UR.get(unit, unit)}" if urdu else f"{n} {unit}{'' if n == 1 else 's'}"


# ── authorities named in the visible text ────────────────────────────────────

_OMITTED_TEXT = re.compile(r"^\W*\d{1,3}\s*-?\s*[A-Z]?\s*\.\s*\d*\s*\[?\s*(?:omitted|repealed|\*\s*\*)", re.IGNORECASE)
# The unit talks ABOUT the omission / repeal -- a correct statement.
_DESCRIBES_OMISSION = re.compile(r"omitted|repealed|no longer|deleted|substituted|حذف|منسوخ|ختم\s+کر", re.IGNORECASE)
_FOREIGN = re.compile(r"\bIndia(?:n)?\b|\bBharat|بھارت|ہندوستان", re.IGNORECASE)
_OFFENCE_CONTEXT = re.compile(r"\boffen[cs]es?\b|\bcrime\b|\bpunish|\baccused\b|\bcharged\b|\bjurm|\bsaza|"
                              r"جرم|جرائم|ملزم|سزا", re.IGNORECASE)
_PROCEDURAL = {"CRPC", "CPC"}
_OFFENCE_HEADING = re.compile(r"punish|offen[cs]e|whoever", re.IGNORECASE)
_RANGE = re.compile(r"(?<![\w.-])(\d{1,3})\s*-\s*(\d{1,3})\s+(PPC|CrPC|CPC)\b")
_HEADING_STOP = frozenset("the of for and or to in by on a an any from with section order rule its".split())
_LIMITED_SHARE = 0.5

WITHHELD_EN = {
    "omitted": "{label} has been omitted from the Code and is not current law",
    "absent": "{label} does not exist in the {statute} as held in the corpus",
    "mispaired": "{label} is \"{heading}\", not what the statement describes{hint}",
    "unverified": "{label} could not be checked against the corpus",
    "off_subject": "{label} is \"{heading}\", which does not support what this sentence relies on it for{hint}",
    "contradicted": "{label}'s own text says otherwise{hint}",
}
WITHHELD_UR = {
    "omitted": "{label} ضابطے سے حذف ہو چکی ہے اور نافذ قانون نہیں",
    "absent": "{label} کارپس میں موجود {statute} میں نہیں",
    "mispaired": "{label} کا موضوع \"{heading}\" ہے، بیان کردہ بات نہیں{hint}",
    "unverified": "{label} کی کارپس سے تصدیق نہیں ہو سکی",
    "off_subject": "{label} کا عنوان \"{heading}\" ہے، جو اس جملے کے دعوے کی تائید نہیں کرتا{hint}",
    "contradicted": "{label} کا اپنا متن اس کے برعکس کہتا ہے{hint}",
}


def _expand_ranges(text: str) -> str:
    def repl(m):
        a, b = int(m.group(1)), int(m.group(2))
        if not (0 < b - a <= 10):
            return m.group(0)
        return ", ".join(f"Section {n} {m.group(3)}" for n in range(a, b + 1))
    return _RANGE.sub(repl, text)


def _terms(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", (text or "").lower()) if w not in _HEADING_STOP}


def _claim_terms(unit: str, ref) -> set[str]:
    """What the sentence SAYS, without the name of the Act it cites.

    "...cheating punishable under Section 420 of the Code of Criminal
    Procedure" shared "procedure" with s.420 CrPC's heading ("Procedure when
    appellant in jail") through the Act's own name, so the mispairing passed
    (live browser check, 2026-10-14); the short form "420 CrPC" was caught."""
    from app.ai.answer_citations import statute_alias_map
    text = unit
    for name in sorted({*statute_alias_map(), str(getattr(ref, "statute", "") or "")}, key=len, reverse=True):
        if name.strip():
            text = re.sub(re.escape(name), " ", text, flags=re.I)
    return _terms(text)


# ── does the cited provision deal with what the sentence relies on it for? ──
# (the drafter only, 2026-10-14). "Entitled to post-arrest bail under s.499
# CrPC" cites a real, in-force section of the right Act -- whose subject is the
# BOND, not the grant of bail -- and every other check passed it. The test is a
# comparison of the sentence's own subject words with the cited provision's
# HEADING, and it only fires when a DIFFERENT section of the same Act is
# headed with those words (so the Act itself says where that subject lives).
# Words every sentence and heading share (parties, "court", "power") and
# procedural verbs ("registered", "granted") never decide it.
_GENERIC = frozenset("""
accused applicant applicants petitioner petitioners respondent respondents plaintiff plaintiffs defendant defendants
appellant appellants complainant opposite party parties court courts judge magistrate person persons case cases code
act acts law laws power powers may shall can must certain matters matter such other under provision provisions provided
clause subsection sub this that these those which whom when where who whose hereby herein said same also further
honourable learned present instant above mentioned therefore humbly prayed pray respectfully sheweth
high supreme district sessions session
tenant tenants landlord landlords husband wife
ppc crpc cpc qso mflo peca dmma gwa fca tpa prpa sro sec sect
name names date dated place amount address number particulars
wholly insofar either partly entirely thereof therein accordingly respectively forthwith only even
application applications authorises authorizes authorise authorize authorised authorized empowers empowered empower vested vests
pakistan government state public officer officers any all each every his her their its him them they has have had
been being was were will would should not nor but than then thus there here into upon within without against
""".split())
_PROCEDURAL_VERBS = frozenset("""
registered filed granted grant grants made make taken take issued issue given give passed pass recorded record
entitled entitle sought seek claimed claim provides provide allowed allow applied apply required require read
relied rely invoked invoke cited cite stated state held hold deemed deem liable
relates relate related relating regarding concerning seeks seek requirement requirements contrary pursuant accordance virtue terms
""".split())
# A few fixed equivalences the Act's own headings use for a practice term.
_ALIAS = {"fir": ("information",), "khula": ("dissolution",), "talb": ("demand",), "muwathibat": ("demand",),
          "ishhad": ("demand",), "release": ("discharge",), "released": ("discharge",), "khulla": ("dissolution",)}
_RELIES = re.compile(r"\b(?:under|u/s|in\s+terms\s+of|pursuant\s+to|by\s+virtue\s+of|as\s+provided\s+(?:in|by|under)|"
                     r"read\s+with|in\s+accordance\s+with|according\s+to|as\s+per|(?:as\s+)?(?:required|prescribed|mandated)\s+(?:by|under)|"
                     r"requirements?\s+of)\b", re.IGNORECASE)


def _stem(word: str) -> str:
    for suffix, repl in (("ities", "ity"), ("ments", ""), ("ment", ""), ("ions", ""), ("ion", ""), ("ies", "y"),
                         ("ing", ""), ("able", ""),
                         ("ed", ""), ("es", ""), ("s", "")):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)] + repl
    return word


def _same(a: str, b: str) -> bool:
    sa, sb = _stem(a), _stem(b)
    if sa == sb:
        return True
    n = 0
    for x, y in zip(sa, sb):
        if x != y:
            break
        n += 1
    # 7, not 5: "dishonoured" and "dishonestly" share six letters (eval set).
    return n >= 7


# Urdu legal terms -> the English words the Acts' headings use (the drafter, 2026-10-15). With an Urdu sentence no
# longer cut at its section word, its citation is judged -- and an Urdu subject was unreadable, so "دفعہ ۴۹۷ ضابطہ
# فوجداری کے تحت" for bail was never verified while "سیکشن 526 ... ضمانت" (bail under the TRANSFER section) could not
# be told apart from it. Standard legal vocabulary only; nothing is guessed from other words.
_URDU_TERMS = {
    "ضمانت": "bail", "قبل از گرفتاری": "arrest", "بعد از گرفتاری": "arrest", "گرفتاری": "arrest",
    "انکوائری": "inquiry", "تفتیش": "investigation", "ضامن": "surety", "مچلکہ": "bond", "اپیل": "appeal",
    "نظرثانی": "revision", "نگرانی": "revision", "اخراج": "quash", "خارج": "dismissal", "استغاثہ": "complaint",
    "شکایت": "complaint", "ڈگری": "decree", "یکطرفہ": "parte", "عرضی دعویٰ": "plaint", "دعویٰ": "suit",
    "حکم امتناعی": "injunction", "نان نفقہ": "maintenance", "خلع": "dissolution", "طلاق": "talaq",
    "حوالگی": "custody", "ولایت": "guardian", "سرپرست": "guardian", "بیدخلی": "eviction", "کرایہ": "rent",
    "میعاد": "limitation", "تاخیر": "delay", "التوا": "adjournment", "سپرداری": "custody", "چیک": "cheque",
    "دھوکہ دہی": "cheating", "امانت میں خیانت": "breach", "قتل": "qatl", "ورثاء": "representatives",
}


def urdu_subject_words(text: str) -> set[str]:
    return {en for ur, en in _URDU_TERMS.items() if ur in (text or "")}


def _subject_words(unit: str, ref) -> set[str]:
    words = {w for w in _claim_terms(unit, ref) if w not in _GENERIC and w not in _PROCEDURAL_VERBS
             and not w.isdigit()}
    for w in list(words):
        words.update(_ALIAS.get(w, ()))
    return words


def _subject_mismatch(unit: str, ref, heading: str, corpus) -> str | None:
    """A hint naming the section(s) of the SAME Act headed with the sentence's
    subject, when the cited one is not; None when they agree or it cannot tell."""
    if not heading or not _RELIES.search(unit):
        return None
    claim = _subject_words(unit, ref)
    head = {w for w in _terms(heading) if w not in _GENERIC}
    if not claim or not head or any(_same(c, h) for c in claim for h in head):
        return None
    cov = corpus.coverage(ref.statute)
    provisions = getattr(cov, "provisions", None) or {}
    heads = {sec: {w for w in _terms(hs[0]) if w not in _GENERIC} for sec, hs in provisions.items() if hs}
    if len(heads) < 5:
        return None
    from collections import Counter
    df = Counter(s for h in heads.values() for s in {_stem(w) for w in h})
    cited = str(ref.section).upper().replace("-", "")
    found = []
    for sec, h in heads.items():
        if str(sec).upper().replace("-", "") == cited:
            continue
        shared = {c for c in claim if df[_stem(c)] <= 12 and any(_same(c, w) for w in h)}
        if shared:
            found.append((len(shared), sec, provisions[sec][0], shared))
    if not found:
        return None

    def _num(sec):
        m = re.match(r"\d+", str(sec))
        return int(m.group(0)) if m else 10 ** 6
    found.sort(key=lambda f: (-f[0], _num(f[1])))
    about = sorted({w for f in found[:2] for w in f[3]})
    see = "; ".join(f"s.{sec} \"{h}\"" for _, sec, h, _ in found[:2])
    return f" (the sentence relies on it for {', '.join(about)}; see {see})"


class _Corpus:
    """Per-answer cache of corpus facts about cited provisions."""

    def __init__(self, research: bool, strict: bool = False, drafter: bool = False):
        self.research = research
        self.drafter = drafter
        # strict (the drafter, 2026-10-14): a corpus that cannot be read RAISES
        # instead of reading as "not found" -- otherwise every authority became
        # "unverified", hedged ones passed, and the check reported success
        # having checked nothing. Raised lazily, only when an authority is
        # actually looked up: a reply citing nothing needs no corpus.
        self.strict = strict
        self.exact: dict = {}
        try:
            from app.ai import corpus_index
            self.index = corpus_index.get_drafter_index() if drafter else corpus_index.get_index()
        except Exception:
            logger.warning("visible_authority: corpus index unavailable", exc_info=True)
            self.index = None
        if self.index is not None and strict:
            try:
                empty = not list(getattr(self.index, "statutes", None) or [])
            except Exception:
                empty = True
            if empty:              # no statute collection could be read at all
                logger.warning("visible_authority: corpus index is empty")
                self.index = None

    def require(self) -> None:
        if self.strict and self.index is None:
            from app.ai.exact_provision import CorpusUnavailable
            raise CorpusUnavailable("corpus index unavailable")

    def chunks(self, ref) -> list[dict]:
        from app.ai import exact_provision
        key = ref.key
        if key not in self.exact:
            try:
                found = (exact_provision.fetch([ref], self.research, strict=True) if self.strict
                         else exact_provision.fetch([ref], self.research))
                self.exact[key] = found.get(exact_provision.label(ref)) or []
            except Exception:
                if self.strict:
                    raise
                self.exact[key] = []
        return self.exact[key]

    def coverage(self, statute: str):
        try:
            return self.index.coverage(statute) if self.index is not None else None
        except Exception:
            return None

    def heading(self, statute: str, section: str) -> str:
        cov = self.coverage(statute)
        heads = cov.headings(section) if cov is not None else ()
        return (heads or ("",))[0]

    def other_headings(self, ref) -> list[tuple[str, str]]:
        """(statute, heading) of OTHER statutes' same-numbered section."""
        out = []
        if self.index is None:
            return out
        from app.ai.answer_citations import normalise_statute
        for statute in getattr(self.index, "statutes", []) or []:
            if normalise_statute(statute) == ref.key[0]:
                continue
            cov = self.coverage(statute)
            heads = cov.headings(ref.section) if cov is not None else ()
            if heads:
                out.append((statute, heads[0]))
        return out


# ── the drafter's subject check v2 (2026-10-15) ─────────────────────────────
# Eval drafter_v2 (v2_r1) showed three gaps in the v1 check above:
#   * it read the WHOLE sentence: "the complaint is mala fide ... the applicant
#     is entitled to pre-arrest bail pursuant to Section 203 CrPC" matched
#     s.203's heading ("Dismissal of complaint") on the word "complaint", and
#     a pre-arrest bail ground was SUPPORTED by the dismissal section;
#   * a cited SUBSECTION was judged by the section heading: "warrant of arrest
#     ... in accordance with Section 502(2)" was withheld because s.502 is
#     headed "Discharge of sureties" -- but s.502(2) IS the warrant power;
#   * no overlap and no better sibling meant "valid": an irrelevant authority
#     (Succession Act s.373 in an application for an early hearing) was
#     counted as supported because its text exists.
# Now: the words AROUND the citation decide; a cited subsection is compared
# with that subsection's own text; CPC Order/Rule headings count as siblings
# of CPC sections; and "nothing agrees, nothing else fits" is UNCONFIRMED --
# shown to the lawyer as not verified, never counted as supported, never
# withheld (we cannot show it is wrong).
_COMPLETE_COPY = 0.98


def _beyond_range(section: str, cov) -> bool:
    m = re.match(r"(\d+)", str(section or ""))
    if not m:
        return False
    n = int(m.group(1))
    highest = int(getattr(cov, "highest", 0) or 0)
    if n >= 1000:
        return True
    return highest > 0 and n > highest + max(10, highest // 10)


def _window(unit: str, ref) -> tuple[str, str | None] | None:
    """(words around the citation, cited subsection or None). The citation is
    the occurrence of the section number next to a section marker or followed
    by its Act; 12 words before it and 10 after it."""
    m0 = re.match(r"\d+", str(ref.section or ""))
    if not m0:
        return None
    num = m0.group(0)
    for m in re.finditer(rf"(?<![\d.]){num}(?!\d)", unit):
        before = unit[max(0, m.start() - 30):m.start()]
        after = unit[m.end():m.end() + 60]
        if re.search(r"(?i)(?:sections?|sec\.?|s\.|u/s\.?|articles?|art\.)\s*(?:[\w\-()]+\s*(?:,|and|&|/)\s*)*$", before) \
                or re.match(r"(?i)\s*(?:-?\s*[A-Z](?![a-z]))?\s*(?:\(\s*\w+\s*\)\s*)*,?\s*(?:of\s+(?:the\s+)?)?[A-Z]", after):
            sub = re.match(r"\s*(?:-?\s*[A-Z](?![a-z]))?\s*\(\s*(\d+)\s*\)", after)
            # The CLAUSE the citation sits in, extended backwards clause by
            # clause until it holds two subject words (or 25 words): "... the
            # complaint is mala fide, the applicant is entitled to pre-arrest
            # bail pursuant to s.203" is about bail, not the complaint; "...
            # discharged from the said bond, either wholly or insofar as it
            # relates to the applicant, pursuant to s.502" is about discharge.
            # [Placeholders] never count ("[Name of Surety]" is not a subject).
            return clause_window(unit, m.start(), m.end(), ref), (sub.group(1) if sub else None)
    return None


def clause_window(unit: str, start: int, end: int, ref) -> str:
    """The words a citation at unit[start:end] is relied on for: its own
    clause, extended backwards clause by clause until it holds two subject
    words (or 25 words), plus the 10 words after it. [Placeholders] never
    count."""
    head = re.sub(r"\[[^\]]*\]|_{2,}", " ", unit[:start])
    clauses = re.split(r"[,;:]|\band\b", head)
    picked: list[str] = []
    for clause in reversed(clauses):
        picked.insert(0, clause)
        text = " ".join(picked)
        if len(_subject_words(text, ref)) >= 2 or len(text.split()) >= 25:
            break
    words_after = re.sub(r"\[[^\]]*\]|_{2,}", " ", unit[end:]).split()[:10]
    return " ".join(" ".join(picked).split()[-25:] + words_after)


def _subsection_text(chunks: list[dict], sub: str) -> str:
    for c in chunks or []:
        text = c.get("content") or ""
        m = re.search(rf"\(\s*{re.escape(sub)}\s*\)(.*?)(?=\(\s*\d+\s*\)|$)", text, re.S)
        if m:
            return m.group(1)[:600]
    return ""


def _sibling_heads(ref, corpus) -> dict[str, str]:
    """Other provisions of the SAME Act, label -> heading. For the CPC, the
    First Schedule Order/Rules too (cpc_provisions; identity index)."""
    cov = corpus.coverage(ref.statute)
    provisions = getattr(cov, "provisions", None) or {}
    out = {f"s.{sec}": hs[0] for sec, hs in provisions.items() if hs}
    if str(ref.key[0]).upper() == "CPC":
        try:
            from app.ai import cpc_provisions
            for lab, p in cpc_provisions.catalogue()["provisions"].items():
                if p.kind == "order_rule" and p.heading:
                    out[lab] = p.heading
        except Exception:      # identity index unavailable: sections only
            pass
    return out


def _relied_on(unit: str) -> bool:
    """Does the sentence RELY on a provision it cites? A reliance phrase
    ("under", "pursuant to" ...) or a citation in brackets: "... the bail
    application is made. (Section 526 CrPC)" relies on s.526 as surely as
    "under Section 526" -- it used to pass unchecked (eval v2_r2, V13/V05)."""
    return bool(_RELIES.search(unit) or _BRACKETED_CITE.search(unit) or _RELIES_ON.search(unit))


# "The Applicant also relies upon Section 126 CrPC" relies on it in so many
# words, and read as a mere mention (eval v2 dev, V12). Drafter only.
# "... contravenes Section 341 CrPC, rendering the proceedings invalid" relies on
# s.341 for a legal consequence -- read as a mere mention, it was never judged
# and listed as SUPPORTED (eval v2_r3 dev, V09).
_RELIES_ON = re.compile(r"(?i)\b(?:rel(?:y|ies|ied|ying)|placed?\s+reliance)\s+(?:up)?on\b"
                        r"|\bcontraven(?:e|es|ed|ing)\b|\bin\s+(?:contravention|violation|breach)\s+of\b"
                        r"|\bviolat(?:e|es|ed|ing)\b"
                        # Urdu: "under", "pursuant to", "by virtue of", "in accordance with" -- with the
                        # Urdu sentence no longer cut at "Sec." its citation was read as a mere mention
                        r"|کے\s+تحت|بموجب|کی\s+رو\s+سے|کے\s+مطابق")
_BRACKETED_CITE = re.compile(r"[(\[]\s*(?:Sections?|Sec\.?|s\.|u/s\.?|Order|O\.|Articles?|Art\.)\s*[\w\-]", re.IGNORECASE)
_TITLE = re.compile(r"^\W*(?:[A-Z0-9][A-Z0-9.,()\-'/&]*\s+){1,14}[A-Z0-9.,()\-'/&]*\W*$")


def is_title(unit: str) -> bool:
    """A heading line ("APPLICATION UNDER SECTION 502 CRPC"): it names a
    provision, it makes no legal claim -- it neither supports nor refutes."""
    text = (unit or "").strip()
    return bool(text) and len(text.split()) <= 15 and bool(_TITLE.match(text))


# One shared heading word supports a citation only when it is DISTINCTIVE in
# that Act -- in at most this many of its headings. "notice" is in 23 CPC
# headings and "Order XI Rule 17" ("Time for inspection when notice given")
# was SUPPORTED for a notice to the Federal Government (eval v2_r2, V23/T05);
# "bail" is in 4 CrPC headings, "return" in 7 CPC ones. Measured 2026-10-15.
_DISTINCTIVE_DF = 8


def _head_df(ref, corpus) -> dict:
    key = ("df", ref.key[0] if hasattr(ref, "key") else ref.statute)
    cache = getattr(corpus, "_df_cache", None)
    if cache is None:
        cache = corpus._df_cache = {}
    if key not in cache:
        from collections import Counter
        heads = _sibling_heads(ref, corpus).values()
        cache[key] = Counter(s for h in heads for s in {_stem(w) for w in _terms(h) if w not in _GENERIC})
    return cache[key]


def _agrees(claim: set, words: set, df) -> bool:
    shared = {c for c in claim if any(_same(c, w) for w in words)}
    return len(shared) >= 2 or any(df.get(_stem(c), 0) <= _DISTINCTIVE_DF for c in shared)


# ── applicability beyond a matching heading (2026-10-15, eval v2 dev) ───────
# Three wrong citations were SUPPORTED because the cited heading agreed with
# some words of the sentence:
#   * "... the Court may dismiss the complaint and grant pre-arrest bail, in
#     accordance with Section 203 CrPC" -- s.203 ("Dismissal of complaints")
#     covers the dismissal and says nothing of bail: ONE clause relies on it
#     for two things (V11). -> foreign_subject();
#   * s.126 CrPC is headed "Discharge of sureties", exactly like s.502 -- its
#     text is about sureties for keeping the peace or good behaviour, and it
#     was cited for a BAIL bond (V12). A heading shared by two provisions
#     cannot tell them apart; their texts can. -> _twin_scope();
#   * Order XXXVII Rule 4 ("Power to set aside decree") belongs to the Order
#     on summary suits on negotiable instruments; it was cited for an ordinary
#     ex parte decree (V05). -> draft_guard._cpc_rules (Order scope).
# Each makes the citation NOT VERIFIED with the reason -- never withheld (the
# sentence may be partly right), never "supported", and never a replacement.
_INSTRUCTION_WORDS = frozenset("""
draft drafting drafted cite citing cited paragraph paragraphs ground grounds clause clauses write writing add
asking ask asks request requests relevant governing proper correct note insert template letter
""".split())


def _body_words(chunks: list[dict], limit: int = 1200) -> set[str]:
    return {w for c in chunks or [] for w in _terms(" ".join((c.get("content") or "")[:limit].split()))
            if w not in _GENERIC}


# A subject the Act gives a BLOCK of consecutive provisions -- a chapter in
# all but name: "bail" heads CrPC ss.496, 497, 498; "warrant" ss.77-80. Single
# shared heading words could not separate a wrong use from a right one (eval
# v2 dev: "bail" is in 4 CrPC headings, "appear" in 4, CPC "action" in 3), and
# neither could a conjunct-by-conjunct reading ("under s.151 ... fix an early
# date and issue notice" is built exactly like "under s.203 ... dismiss the
# complaint and grant pre-arrest bail"). What separates them is structure.
_BLOCK_SIZE, _BLOCK_SPAN = 3, 3
# A residual power ("Saving of inherent powers of Court", s.151 CPC; s.561-A
# CrPC) supports any order the ends of justice need: never "mixed".
_RESIDUAL = re.compile(r"(?i)inherent\s+powers?")
_CONNECTIVES = frozenset("consequently hence moreover furthermore however whereas thereafter therein".split())


def subject_blocks(numbered_heads) -> dict[str, list[tuple[int, int]]]:
    """numbered_heads: iterable of (group, number, heading) -> stem -> [(group, number)]
    of the provisions in a block of _BLOCK_SIZE consecutive ones headed with it."""
    from collections import defaultdict
    seen: dict[str, set] = defaultdict(set)
    for group, n, heading in numbered_heads:
        for w in _terms(heading):
            if w not in _GENERIC:
                seen[_stem(w)].add((group, n))
    out: dict[str, list] = {}
    for stem, items in seen.items():
        block = set()
        for group in {g for g, _ in items}:
            nums = sorted(n for g, n in items if g == group)
            for i in range(len(nums) - _BLOCK_SIZE + 1):
                if nums[i + _BLOCK_SIZE - 1] - nums[i] <= _BLOCK_SPAN:
                    block.update((group, n) for n in nums[i:i + _BLOCK_SIZE])
        if block:
            out[stem] = sorted(block)
    return out


_PREFIXES = ("re", "un", "dis", "non", "pre", "mis")


def _covers(word: str, w: str) -> bool:
    """Does `word` (from the provision) cover `w` (from the sentence)? Also
    through a prefix: s.489-F's "repayment" covers "payment" (eval v2 dev, V24)."""
    if _same(word, w):
        return True
    sw, sx = _stem(w), _stem(word)
    return len(sw) >= 3 and any(sx == p + sw for p in _PREFIXES)


def foreign_subject(sentence: set, request: set, covered: set, blocks: dict, cited: tuple, residual: bool) -> list[str]:
    """Words the clause relies on the citation for that it does not provide:
    in the sentence AND the lawyer's request, absent from the cited heading and
    text, and the subject of a block of OTHER provisions of the same Act."""
    if residual:
        return []
    out = []
    for w in sentence:
        if w in _CONNECTIVES or w in _INSTRUCTION_WORDS or any(_covers(x, w) for x in covered):
            continue
        if not any(_same(w, r) for r in request):
            continue
        block = blocks.get(_stem(w)) or []
        if block and cited not in block:
            out.append(w)
    return sorted(out)


def _section_blocks(ref, corpus) -> dict:
    key = ("blocks", ref.key[0])
    cache = getattr(corpus, "_df_cache", None)
    if cache is None:
        cache = corpus._df_cache = {}
    if key not in cache:
        cov = corpus.coverage(ref.statute)
        provisions = getattr(cov, "provisions", None) or {}
        rows = []
        for sec, hs in provisions.items():
            m = re.fullmatch(r"(\d+)", str(sec))           # lettered sections are not part of a run
            if hs and m:
                rows.append(("s", int(m.group(1)), hs[0]))
        cache[key] = subject_blocks(rows)
    return cache[key]


def _twin_scope(ref, heading: str, corpus, chunks: list[dict], request: str) -> str | None:
    """A hint when another provision of the same Act has the SAME heading and
    the request matches only that one's text; None otherwise."""
    if not request or not heading:
        return None
    mine_head = _terms(heading)
    cov = corpus.coverage(ref.statute)
    provisions = getattr(cov, "provisions", None) or {}
    cited = str(ref.section).upper().replace("-", "")
    twins = [sec for sec, hs in provisions.items()
             if hs and str(sec).upper().replace("-", "") != cited and _terms(hs[0]) == mine_head]
    if not twins:
        return None
    from app.ai.answer_citations import ParsedCitation
    req = request_words(request, ref)
    own = _body_words(chunks)
    if not req or not own:
        return None
    for sec in twins:
        try:
            other = _body_words(corpus.chunks(ParsedCitation(ref.statute, str(sec), (ref.key[0], str(sec)))))
        except Exception:
            continue
        mine = {w for w in own if not any(_same(w, x) for x in other)}
        theirs = {w for w in other if not any(_same(w, x) for x in own)}
        hit = sorted(r for r in req if any(_same(r, w) for w in theirs))
        if other and hit and not any(_same(r, w) for r in req for w in mine):
            return (f" (another provision of this Act has the same heading; this one's text does not cover what the "
                    f"request is about: {', '.join(hit)})")
    return None


def request_words(request: str, ref) -> set[str]:
    return {w for w in _subject_words(re.sub(r"\[[^\]]*\]", " ", request or ""), ref) if w not in _INSTRUCTION_WORDS}


def _confirm(unit: str, ref, heading: str, corpus, chunks: list[dict], request: str) -> tuple[str, str]:
    """A citation whose heading or text agrees with the claim: still NOT
    VERIFIED when the sentence also relies on it for a subject another block of
    the Act governs, or when its heading is shared and the request fits only
    the other provision."""
    covered = {w for w in _terms(heading) if w not in _GENERIC} | _body_words(chunks, 4000)
    m = re.fullmatch(r"(\d+)", str(ref.section))
    foreign = foreign_subject(
        _subject_words(re.sub(r"\[[^\]]*\]", " ", unit), ref), request_words(request, ref), covered,
        _section_blocks(ref, corpus), ("s", int(m.group(1))) if m else ("s", -1),
        bool(_RESIDUAL.search(heading or "") or any(_RESIDUAL.search(c.get("content") or "") for c in chunks or [])))
    if foreign:
        what = f"\"{heading}\"" if heading else "its text"
        return "unconfirmed", (f" (the sentence also relies on it for {', '.join(foreign)}, which {what} does not "
                               f"cover)")
    twin = _twin_scope(ref, heading, corpus, chunks, request)
    if twin:
        return "unconfirmed", twin
    chapter = _chapter_scope(ref, chunks, request, covered, corpus)
    if chapter:
        return "unconfirmed", chapter
    # S1 / S2 (draft_claims): the action the clause relies on it for must be in
    # its text with the same object; a stated legal effect must be in its text.
    from app.ai import draft_claims
    text = " ".join(c.get("content") or "" for c in chunks or [])
    win = _window(unit, ref)
    obj = draft_claims.claim_object(unit, text)   # the whole sentence (eval v2_r4 dev, V04)
    if obj:
        return "unconfirmed", obj
    effect, word = draft_claims.claimed_effect(unit, text)
    if effect == "silent":
        return "unconfirmed", f" (its text does not say this makes anything {word})"
    return "valid", ""


# A provision whose own text confines it to its Chapter (eval v2_r3 dev, V12):
# s.122 CrPC ("Power to reject sureties" -- "... under this Chapter", the
# Chapter on security for keeping the peace) was SUPPORTED in an application to
# be discharged from a BAIL bond. When the request is about a subject another
# block of the Act governs and the provision's text does not mention it, the
# use is not verified.
_THIS_CHAPTER = re.compile(r"(?i)\b(?:under|of|in|by)\s+this\s+Chapter\b")


def _chapter_scope(ref, chunks: list[dict], request: str, covered: set, corpus) -> str | None:
    text = " ".join(c.get("content") or "" for c in chunks or [])
    if not request or not _THIS_CHAPTER.search(text):
        return None
    m = re.fullmatch(r"(\d+)", str(ref.section))
    cited = ("s", int(m.group(1))) if m else ("s", -1)
    blocks = _section_blocks(ref, corpus)
    outside = sorted(w for w in request_words(request, ref)
                     if not any(_covers(x, w) for x in covered)
                     and (blocks.get(_stem(w)) or []) and cited not in blocks[_stem(w)])
    if not outside:
        return None
    return (f" (its text limits it to its own Chapter, and the request is about {', '.join(outside)}, which other "
            f"provisions of the Act govern)")


def _drafter_subject(unit: str, ref, heading: str, corpus, chunks: list[dict],
                     request: str = "") -> tuple[str, str]:
    """("valid" | "off_subject" | "unconfirmed", hint). Never a suggestion of
    what to cite instead: a pointer we have not verified is not offered."""
    if is_title(unit):
        return "unconfirmed", " (named in a heading line; a heading is not a legal claim)"
    if not _relied_on(unit):
        return "valid", ""                    # a mention, not reliance: not judged
    # S2 (draft_claims): a legal consequence the sentence attributes to the
    # provision that its own text contradicts is WITHHELD, the text quoted.
    from app.ai import draft_claims
    effect, said = draft_claims.claimed_effect(unit, " ".join(c.get("content") or "" for c in chunks or []))
    if effect == "contradicted":
        return "contradicted", f': "{said}"'
    win = _window(unit, ref)
    claim = _subject_words(win[0] if win else unit, ref) | urdu_subject_words(win[0] if win else unit)
    if not claim:
        # The sentence relies on the provision, but its subject could not be
        # read (Urdu text, or only generic words): NOT VERIFIED, never valid.
        return "unconfirmed", " (what the sentence relies on it for could not be read, so it was not checked)"
    head = {w for w in _terms(heading) if w not in _GENERIC}
    if win and win[1]:
        head |= {w for w in _terms(_subsection_text(chunks, win[1])) if w not in _GENERIC}
    df = _head_df(ref, corpus)
    heads = {lab: {w for w in _terms(h) if w not in _GENERIC} for lab, h in _sibling_heads(ref, corpus).items()}
    cited = f"s.{str(ref.section).upper().replace('-', '')}"
    heads = {lab: h for lab, h in heads.items() if lab.upper().replace("-", "") != cited.upper()}
    if head and _agrees(claim, head, df):
        return _confirm(unit, ref, heading, corpus, chunks, request)
    # Another provision of the same Act headed with a DISTINCTIVE word of the
    # claim: the cited one is the wrong provision. Withheld -- naming the
    # subject, not a replacement.
    distinctive = {c for c in claim if df.get(_stem(c), 0) <= _DISTINCTIVE_DF}
    # Only when we KNOW what the cited provision is headed: with no readable
    # heading there is nothing to say it is the wrong one (489-F, whose stored
    # heading is broken by line breaks, was withheld this way).
    if head and len(heads) >= 5 and any(any(_same(c, w) for w in h) for h in heads.values() for c in distinctive):
        about = sorted(c for c in distinctive if any(any(_same(c, w) for w in h) for h in heads.values()))
        return "off_subject", f" (the sentence relies on it for {', '.join(about)})"
    # The provision's OWN TEXT, against the WHOLE sentence, two meaningful
    # words ("abuse of the process ... under s.561-A" -- its text says "abuse
    # of the process"). After the sibling check, so a passing word in a text
    # ("released on bail" in s.499) cannot rescue a claim another provision is
    # headed with.
    # (Also when no heading could be read: "489-F" stored with line breaks
    # inside its heading lost the heading, and the TEXT still decides.)
    body = {w for c in chunks or [] for w in _terms(" ".join((c.get("content") or "")[:1200].split())) if w not in _GENERIC}
    sentence = _subject_words(re.sub(r"\[[^\]]*\]", " ", unit), ref) | urdu_subject_words(unit)
    if len({c for c in sentence if any(_same(c, w) for w in body)}) >= 2:
        return _confirm(unit, ref, heading, corpus, chunks, request)
    if not head:
        return "unconfirmed", " (its heading is not in our copy, so what it covers was not checked)"
    return "unconfirmed", f" (\"{heading}\" does not match what the sentence relies on it for)"


_ATTRIBUTION_BEFORE = re.compile(
    r"\b(?:punish\w*|offen[cs]es?|charged|crime|guilty|convicted|booked)\b[^.;:|\n]{0,40}?"
    r"\b(?:under|u/s\.?|of)\s*\**\s*(?:Section|Sec\.?|s\.)?\s*$"
    r"|(?:جرم|سزا)[^۔|\n]{0,30}$", re.IGNORECASE)
_ACT_TOKEN = {"CRPC": r"(?:CrPC|Code\s+of\s+Criminal\s+Procedure|Criminal\s+Procedure\s+Code|ضابطہ\s+فوجداری)",
              "CPC": r"(?:CPC|Code\s+of\s+Civil\s+Procedure|Civil\s+Procedure\s+Code|ضابطہ\s+دیوانی)"}


def _cited_as_offence(unit: str, ref) -> bool:
    """Is THIS citation presented as the offence itself? Both "420 CrPC" and
    "420 of the Code of Criminal Procedure" (the long form was missed)."""
    from app.ai import period_support
    text = period_support.normalise(unit)
    act = _ACT_TOKEN.get(ref.key[0], re.escape(ref.key[0]))
    num = re.escape(ref.section)
    for m in re.finditer(rf"(?:\(\s*\**\s*)?(?:Section|Sec\.?|s\.|دفعہ|سیکشن)?\s*\**\s*{num}\s*\**\s*,?\s*(?:of\s+(?:the\s+)?)?{act}"
                         rf"|{act}\s*(?:کی|کے|کا)?\s*(?:Section|دفعہ|سیکشن)\s*{num}", text, re.IGNORECASE):
        before = text[max(0, m.start() - 60): m.start()]
        if m.group(0).lstrip().startswith("(") and _OFFENCE_CONTEXT.search(text):
            return True
        if _ATTRIBUTION_BEFORE.search(before):
            return True
    return False


# A unit that itself says the provision's text was not available is hedged,
# not confident advice; an unverifiable (not omitted / mispaired) authority
# there is left visible.
_HEDGED = re.compile(r"not (?:available|provided|included|among|in the (?:sources|material))|"
                     r"could not be (?:verified|checked)|not verified|unverified|دستیاب نہیں|شامل نہیں", re.IGNORECASE)


# What an unverifiable authority must NOT be left doing: asserting its content
# as advice. A restated question ("Whether a court may grant ... under s.42?")
# or an instruction to read it ("Obtain the full text of s.42") asserts nothing.
_ASSERTS = re.compile(
    r"\b(?:provides?|grants?|allows?|states?|says|prescribes?|punish\w*|entitles?|empowers?|lays?\s+down|"
    r"permits?|requires?|mandates?|is\s+available|(?:may|can|must|shall)\s+be\s+(?:granted|sought|filed|"
    r"claimed|awarded|obtained))\b|کے\s+تحت|دیتی\s+ہے|دیتا\s+ہے|مل\s+سکتی|ملتی\s+ہے", re.IGNORECASE)
_NOT_ADVICE = re.compile(r"^\W*(?:\d+[.)]\s*)?\W*(?:whether|obtain|check|verify|consult|review|read|refer|see)\b"
                         r"|[?؟]\s*\**\s*$", re.IGNORECASE)


def _asserts(unit: str) -> bool:
    return bool(_ASSERTS.search(unit)) and not _NOT_ADVICE.search(unit.strip())


# "(e.g. section 437 or 439)" with no Act: when the WHOLE answer names exactly
# one Act, a bare section number is read as that Act's (eval V3: omitted CrPC
# 437 offered after "ضابطہ فوجداری کی دفعہ 438"). With two or more Acts named
# a bare number is ambiguous and is left alone.
_BARE = re.compile(r"(?:\bSection|\bSec\.|\bs\.|دفعہ|سیکشن|\bdafa)\s*(\d{1,3}(?:-[A-Z])?)\b"
                   r"((?:\s*(?:,|or|and|یا|اور|/)\s*\d{1,3}(?:-[A-Z])?\b)*)", re.IGNORECASE)


def _single_act(answer: str):
    from app.ai import period_support, tool_contract
    keys = {}
    for ref in tool_contract.provision_refs(period_support.normalise(answer)):
        keys.setdefault(ref.key[0], ref.statute)
    return next(iter(keys.items())) if len(keys) == 1 else None


def _bare_refs(unit: str, default_act) -> list:
    if not default_act:
        return []
    from app.ai import period_support
    from app.ai.answer_citations import ParsedCitation
    from app.ai.corpus_index import canonical_section
    key, statute = default_act
    out = []
    for m in _BARE.finditer(period_support.normalise(unit)):
        tail = period_support.normalise(unit)[m.end(): m.end() + 14]
        if re.match(r"\s*\**\s*(?:of\s+the\s+)?[A-Z][A-Za-z]{1,10}\b", tail):      # an Act IS named: not bare
            continue
        numbers = [m.group(1)] + re.findall(r"\d{1,3}(?:-[A-Z])?", m.group(2) or "")
        out += [ParsedCitation(statute, canonical_section(n), (key, canonical_section(n))) for n in numbers]
    return out


def _status(ref, unit: str, corpus: _Corpus, evidence: list[dict] | None = None,
            drafter: bool = False, request: str = "") -> tuple[str, str, str]:
    """(status, heading, hint): valid / omitted / absent / mispaired / unverified.

    The answer's OWN evidence first: an exact text of the provision there
    verifies it (and gives its heading) without another corpus lookup; only a
    provision outside the evidence is looked up."""
    from app.ai import corpus_index, exact_provision
    corpus.require()
    own = [e for e in evidence or [] if e.get("kind", "statute") == "statute" and exact_provision.is_exact(e, ref)]
    chunks = own or corpus.chunks(ref)
    if any(_OMITTED_TEXT.match(c.get("content") or "") for c in chunks):
        return "omitted", "", ""
    cov = corpus.coverage(ref.statute)
    # The drafter (2026-10-14): a number under which the corpus files SEVERAL
    # different provisions (every CPC section shares its number with Order
    # rules; TPA lease sections with footnotes) cannot be checked by number --
    # the same rule, and the same corpus fact, the citation checker uses
    # (citation_verification SECTION_NOT_CHECKABLE). Not withheld, never counted
    # as supported. Research keeps its behaviour.
    if drafter and cov is not None and _beyond_range(ref.section, cov):
        # "Section 1956 CPC": the Code has 158 sections. A number this far
        # past the Act's last section is not a gap in our copy -- it does
        # not exist (a year or page number read as a section).
        return "absent", "", ""
    if drafter and cov is not None and getattr(cov, "ambiguous", None) and cov.ambiguous(ref.section):
        return "ambiguous", "", ""
    if not chunks:
        if cov is not None and getattr(cov, "dense", False) and not cov.has(ref.section):
            # The drafter: inside the Act's range, in a copy that is not
            # complete, "not held" is not "does not exist" (CPC s.114 is a
            # real section our copy lacks). Not verified -- never withheld.
            if drafter and getattr(cov, "ratio", 1.0) < _COMPLETE_COPY:
                return "unverified", "", ""
            return "absent", "", ""
        if cov is not None and cov.has(ref.section):
            heading = corpus.heading(ref.statute, ref.section)
        else:
            return "unverified", "", ""
    else:
        heading = (corpus.heading(ref.statute, ref.section)
                   or next((h for h in (corpus_index.heading_of(c.get("content") or "", ref.section) for c in chunks)
                            if h), "") or "")
    # Mispairing: the sentence's own words against this provision's heading.
    words = _claim_terms(unit, ref)
    own = _terms(heading)
    others = corpus.other_headings(ref)
    best = max(((len(words & _terms(h)), s, h) for s, h in others), default=(0, "", ""))
    if heading and not (words & own) and best[0] >= 2:
        return "mispaired", heading, f" (it matches {best[1]} s.{ref.section}: \"{best[2]}\")"
    # A procedural code cited AS the offence: "punishable / offence / charged
    # ... under Section N CrPC", or "(Section N CrPC)" beside the act described.
    # Mentioning an offence near a procedural section is not that ("s.154 CrPC
    # requires information about a cognizable offence ..." is correct).
    if (ref.key[0] in _PROCEDURAL and heading and not _OFFENCE_HEADING.search(heading)
            and not (words & own) and _cited_as_offence(unit, ref)):
        offence = next(((s, h) for s, h in others if _OFFENCE_HEADING.search(h) or s.startswith("PPC")), None)
        hint = f" (an offence is defined in {offence[0]} s.{ref.section}: \"{offence[1]}\")" if offence else ""
        return "mispaired", heading, hint
    if drafter:
        verdict, hint = _drafter_subject(unit, ref, heading, corpus, chunks, request)
        if verdict != "valid":
            return verdict, heading, hint
    return "valid", heading, ""


def authorities(answer: str, question: str, urdu: bool, research: bool = True,
                evidence: list[dict] | None = None, inline_notice: bool = True,
                require_corpus: bool = False, stats: dict | None = None,
                drafter: bool = False, request: str = "") -> tuple[str, list[dict]]:
    """(answer, withheld units). Units naming an invalid authority are
    withheld with one precise note; valid units are kept.

    inline_notice=False (a DRAFT the lawyer will insert into a filing): the
    units are removed and NO note is written into the text -- each withheld
    unit carries its reasons (`reasons`) for the caller to show beside it, and
    there is no "limited answer" replacement.

    require_corpus=True: a corpus that cannot be read raises
    exact_provision.CorpusUnavailable rather than passing what it could not
    check. `stats`, when given, receives {"checked": provisions found in the
    library and compared, "unverified": labels of cited provisions the library
    does not hold (looked up, not checked)}. `request` (the drafter): what
    the lawyer asked for and the document, for applicability checks."""
    from app.ai import exact_provision, jurisdiction_guard, tool_contract
    corpus = _Corpus(research, strict=require_corpus, drafter=drafter)
    checked = 0
    unverified: list[tuple[str, str]] = []
    unit_log: list[dict] = []          # every unit's cited provisions and their status (stats["units"])
    comparative = jurisdiction_guard.asks_comparative(question or "")
    default_act = _single_act(answer)
    withheld = []
    for a, b in _units(answer):
        unit = answer[a:b]
        if _DESCRIBES_OMISSION.search(unit) or (comparative and _FOREIGN.search(unit)):
            continue
        # A restated question ("Is bail available under s.438 CrPC?") or an
        # instruction to read a provision asserts nothing about it (eval V1/V3).
        if _NOT_ADVICE.search(unit.strip()):
            continue
        from app.ai import period_support
        refs = tool_contract.provision_refs(_expand_ranges(period_support.normalise(unit)))
        # An INFERRED Act is weak evidence: an inherited bare number is only
        # ever withheld as OMITTED ("Section 337-A" beside "Section 239 CrPC"
        # is a PPC section, not a missing CrPC one).
        inferred = {r.key for r in _bare_refs(unit, default_act)} - {x.key for x in refs}
        refs += [r for r in _bare_refs(unit, default_act) if r.key in inferred]
        # "I couldn't find the text of Section 489-F PPC" (the exact-provision
        # guard's own refusal) does not ASSERT 489-F: a provision the unit
        # reports missing is not an authority it relies on.
        reported_missing = {r.key for r in tool_contract._denied_refs(unit)}
        problems = []
        seen_refs = []
        for ref in refs:
            if ref.key in reported_missing:
                continue
            status, heading, hint = _status(ref, unit, corpus, evidence, drafter=drafter, request=request)
            seen_refs.append({"label": exact_provision.label(ref), "status": status, "hint": hint,
                              "shown": f"Section {ref.section} {ref.statute}".strip()})
            # "checked" = found in the library and compared. A provision the
            # library does not hold was looked up, NOT checked, and is reported
            # as such (it used to be counted, and the card said "1 checked"
            # for a section the citation check found 0 of -- browser check).
            if status == "unverified":
                shown = f"Section {ref.section} {ref.statute}".strip()
                if (exact_provision.label(ref), shown) not in unverified:
                    unverified.append((exact_provision.label(ref), shown))
            else:
                checked += 1
            if ref.key in inferred and status != "omitted":
                continue
            if status == "unverified" and (_HEDGED.search(unit) or not _asserts(unit)):
                continue
            if status in ("omitted", "absent", "mispaired", "unverified", "off_subject", "contradicted"):
                # The drafter names the Act in full: "Section 17 West" was the
                # first word of "West Pakistan Family Courts Act 1964" (eval v2
                # dev, V16). Research keeps its short label.
                problems.append({"label": exact_provision.label(ref), "statute": ref.statute,
                                 "status": status, "heading": heading, "hint": hint,
                                 "shown": f"Section {ref.section} {ref.statute}".strip() if drafter else None})
        if seen_refs:
            unit_log.append({"span": (a, b), "refs": seen_refs})
        if problems:
            withheld.append({"span": (a, b), "text": unit, "problems": problems})
    if stats is not None:
        stats["checked"] = checked
        # withheld ones are reported with their reasons instead
        gone = {p["label"] for w in withheld for p in w["problems"]}
        stats["unverified"] = [shown for label, shown in unverified if label not in gone]
        stats["units"] = unit_log
    if not withheld:
        return answer, []

    body = len(answer.strip()) or 1
    removed_share = sum(b - a for a, b in (w["span"] for w in withheld)) / body
    notes = []
    for w in withheld:
        w["reasons"] = []
        for p in w["problems"]:
            tmpl = (WITHHELD_UR if urdu else WITHHELD_EN)[p["status"]]
            note = tmpl.format(label=p.get("shown") or p["label"], statute=p["statute"], heading=p["heading"],
                               hint=p["hint"])
            w["reasons"].append(note)
            if note not in notes:
                notes.append(note)
    if not inline_notice:
        out, last = [], 0
        for w in withheld:
            a, b = w["span"]
            out.append(answer[last:a])
            last = b
        out.append(answer[last:])
        text = re.sub(r"[ \t]+\n", "\n", "".join(out))
        return re.sub(r"\n{3,}", "\n\n", text).strip(), withheld
    lead = "روکا گیا: " if urdu else "Withheld: "
    notice = lead + "; ".join(notes) + ("۔" if urdu else ".")

    if removed_share > _LIMITED_SHARE:
        limited = ("میں اس سوال کا قابلِ اعتماد جواب تیار نہیں کر سکا: مسودے کا بڑا حصہ ایسے قانونی حوالوں پر مبنی تھا جن کی تصدیق نہیں ہو سکی۔ "
                   if urdu else
                   "I could not produce a reliable answer to this question: most of the draft rested on legal "
                   "authorities that could not be verified. ")
        return limited + notice, withheld

    out, last = [], 0
    for i, w in enumerate(withheld):
        a, b = w["span"]
        out.append(answer[last:a])
        if i == 0:
            out.append(notice)
        last = b
    out.append(answer[last:])
    text = re.sub(r"[ \t]+\n", "\n", "".join(out))
    return re.sub(r"\n{3,}", "\n\n", text), withheld
