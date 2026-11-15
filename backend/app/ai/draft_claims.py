"""What a drafted sentence CLAIMS, checked against the cited provision's own text and the lawyer's own input
(the lawyer drafter, 2026-10-15; evals/drafter_v2/OPEN_ISSUES.md).

Word agreement shows a provision is ABOUT a sentence's topic, not that it supports what the sentence says (eval
v2_r3 dev): "under Order XIV Rule 5 the Court may amend the parties" was SUPPORTED -- r.5 lets the Court amend
ISSUES; "contravenes Section 341 CrPC, rendering the proceedings invalid" was SUPPORTED -- s.341 says the Court "may
proceed with the trial"; and "the accused, though not insane, is unable to understand the proceedings" -- a fact the
lawyer never gave, copied from s.341's own text in the law context -- was insertable.

  S1 claim_object     an action the clause relies on the provision for ("amend the parties") must appear in the
                      provision's text with the same object ("amend the issues" does not cover it). A mismatch is
                      NOT VERIFIED only -- a lexical check cannot prove the claim wrong.
  S2 claimed_effect   a legal consequence the sentence attributes to the provision (invalid, void, vitiated ...)
                      must be stated in its text. Text that says the opposite ("may proceed", "shall not be
                      invalid") -> CONTRADICTED (withheld, the text quoted); silent text -> NOT VERIFIED.
  S3 invented_facts   a fact about a person or event (a condition, a number, a name) that is not in the lawyer's
                      INPUT -- instruction, selection, document, case record; never the law context -- makes the
                      sentence non-insertable. Lexical: paraphrases can escape (measured, not assumed).
"""
from __future__ import annotations

import re

# ── S1: the object of the action ────────────────────────────────────────────
_VERB_FORMS = {
    "amend": "amend amends amended amending amendment amendments",
    "add": "add adds added adding addition",
    "strike": "strike strikes struck striking",
    "return": "return returns returned returning",
    "reject": "reject rejects rejected rejecting rejection",
    "dismiss": "dismiss dismisses dismissed dismissing dismissal",
    "discharge": "discharge discharges discharged discharging",
    "cancel": "cancel cancels cancelled canceled cancelling cancellation",
    "transfer": "transfer transfers transferred transferring",
    "withdraw": "withdraw withdraws withdrawn withdrawing withdrawal",
    "attach": "attach attaches attached attaching attachment",
    "appoint": "appoint appoints appointed appointing appointment",
    "implead": "implead impleads impleaded impleading impleadment",
    "substitute": "substitute substitutes substituted substituting substitution",
    "frame": "frame frames framed framing",
    "release": "release releases released releasing",
    "restore": "restore restores restored restoring restoration",
    "extend": "extend extends extended extending extension",
    "quash": "quash quashes quashed quashing",
    "grant": "grant grants granted granting",
}
_FORM_TO_VERB = {f: v for v, forms in _VERB_FORMS.items() for f in forms.split()}
_SKIP = frozenset("""the a an any such said his her their its all of or and additional fresh new further ex parte
early present instant same other whole part entire this that these those name names out aside up off as
""".split())
# Statutory equivalences: "'Pleading' shall mean plaint or written statement" (CPC O.VI r.1); parties to a suit
# are named as plaintiff / defendant / person (O.I). Nothing else is equated.
_KIND = {"plaint": "pleading", "pleading": "pleading", "pleadings": "pleading", "statement": "pleading",
         "party": "party", "parties": "party", "plaintiff": "party", "plaintiffs": "party", "defendant": "party",
         "defendants": "party", "person": "party", "persons": "party", "applicant": "party", "respondent": "party"}
# the lawyer asking the Court (active voice): "the Court may amend the parties", "be pleased to strike out ..."
_ACTIVE = re.compile(r"(?i)\b(?:may|shall|should|must|will|can|to)\s+(?:also\s+)?(?:be\s+pleased\s+to\s+)?([a-z]+)\b")


_CITE_ASIDE = re.compile(r"(?i),\s*(?:under|pursuant\s+to|in\s+accordance\s+with|by\s+virtue\s+of|as\s+per|in\s+terms\s+of)"
                         r"\s+[^,]{1,90},")


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z]+", (text or "").lower())


def _object_after(words: list[str], i: int) -> str | None:
    for w in words[i + 1:i + 6]:
        if w not in _SKIP and w not in _FORM_TO_VERB:     # "amend, and strike out, issues": the object is issues
            return w
    return None


def _same_object(a: str, b: str) -> bool:
    from app.ai import visible_authority as va
    if va._same(a, b):
        return True
    return _KIND.get(a) is not None and _KIND.get(a) == _KIND.get(b)


def claim_object(clause: str, provision_text: str) -> str | None:
    """A hint when the clause relies on the provision for VERB + OBJECT and the provision's text has that verb only
    with other objects; None when they agree, or when it cannot tell (no active verb, or the text lacks the verb)."""
    clause = re.sub(r"\[[^\]]*\]", " ", clause or "")
    # "the Court may, under Order XIV Rule 5 CPC, amend the parties" -- a citation between the modal and the verb hid
    # the action (eval v2_r4 dev, V04): the parenthetical citation phrase is taken out first.
    clause = _CITE_ASIDE.sub(" ", clause)
    claims = []
    for m in _ACTIVE.finditer(clause):
        verb = _FORM_TO_VERB.get(m.group(1).lower())
        if verb:
            obj = _object_after(_words(clause[m.end(1):]), -1)
            if obj:
                claims.append((verb, obj))
    if not claims:
        return None
    words = _words(provision_text)
    for verb, obj in claims:
        objects = []
        for i, w in enumerate(words):
            if _FORM_TO_VERB.get(w) != verb:
                continue
            after = _object_after(words, i)
            if after:
                objects.append(after)
            # passive: "the name of any party ... be struck out"
            if i >= 1 and words[i - 1] in ("be", "been", "is", "are"):
                objects += [x for x in words[max(0, i - 10):i - 1] if x not in _SKIP]
        if not objects:
            continue                                   # the text never uses the verb: S1 cannot judge
        if not any(_same_object(obj, o) for o in objects):
            seen = sorted({o for o in objects if o in _KIND or len(o) > 3})[:3]
            doing = (verb[:-1] if verb.endswith("e") else verb) + "ing"
            return f" (its text provides for {doing} {', '.join(seen) or 'something else'}, not {obj})"
    return None


# ── S2: a stated legal effect ───────────────────────────────────────────────
_EFFECT = re.compile(r"(?i)\b(?:invalid\w*|void|null(?:ity)?|vitiat\w*|illegal\w*|unlawful\w*|without\s+jurisdiction|"
                     r"of\s+no\s+(?:legal\s+)?effect|bad\s+in\s+law)\b")
_NEGATED = re.compile(r"(?i)\b(?:not|no|never|cannot|nor)\b[^.;:]{0,30}$")
_CONTRARY = re.compile(r"(?i)\b(?:may|shall)\s+proceed\b|\bshall\s+not\s+(?:be\s+)?(?:deemed\s+)?(?:invalid|void|vitiat\w*|"
                       r"invalidat\w*)|\bnot\s+(?:be\s+)?(?:invalid|void)\b|\bshall\s+not\s+(?:by\s+reason\s+only\s+of\s+)?"
                       r"[^.;]{0,40}\bbe\s+(?:set\s+aside|reversed)")


def _asserted(pattern: re.Pattern, text: str) -> list[re.Match]:
    return [m for m in pattern.finditer(text or "") if not _NEGATED.search((text or "")[max(0, m.start() - 40):m.start()])]


def claimed_effect(sentence: str, provision_text: str) -> tuple[str, str]:
    """("none" | "stated" | "contradicted" | "silent", detail). `detail` quotes the provision's contrary words."""
    claims = _asserted(_EFFECT, re.sub(r"\[[^\]]*\]", " ", sentence or ""))
    if not claims:
        return "none", ""
    text = " ".join((provision_text or "").split())
    contrary = _CONTRARY.search(text)
    if contrary:
        start = max(text.rfind(".", 0, contrary.start()) + 1, contrary.start() - 160)
        end = text.find(";", contrary.end())
        end = min(end if end > 0 else len(text), contrary.end() + 80)
        return "contradicted", text[start:end].strip(" ;,")
    if _asserted(_EFFECT, text):
        return "stated", ""
    return "silent", claims[0].group(0).lower()


# ── S3: facts the lawyer did not give ───────────────────────────────────────
_CONDITION = re.compile(
    r"(?i)\b(?:insan\w*|unsound\s+mind|lunatic\w*|mentally\s+\w+|psychiatric\w*|"
    r"(?:unable|incapable)\s+(?:to\s+)?(?:understand|comprehend)\w*|cannot\s+(?:be\s+made\s+to\s+)?understand|"
    r"deaf|dumb|blind|ill(?:ness)?|sick\w*|hospitali[sz]\w*|minor|minority|juvenile|pregnan\w*|abscond\w*|fugitive|"
    r"threat\w*|intoxicat\w*|drunk\w*|disabled|disabilit\w*|bedridden|elderly|widow\w*|deceased|died|dead)\b")
_NAME = re.compile(r"\b(?:Mr|Mrs|Ms|Mst|Miss|Dr|Syed)\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})"
                   r"|\b(?:s/o|d/o|w/o|son\s+of|daughter\s+of|wife\s+of|resident\s+of|residing\s+at|named|namely)\s+"
                   # "namely Section 7" is a citation, not a person (eval v2_r4 dev, V16: a false flag)
                   r"(?!(?:Sections?|Order|Rules?|Articles?|Act|Ordinance|Code|Schedule|Chapter|Part|Clause)\b)"
                   r"([A-Z][\w-]+(?:\s+[A-Z][\w-]+){0,3})")
_NUMBER = re.compile(r"(?<![\w/])\d(?:[\d,]*\d)?(?:\.\d+)?(?:[-/.]\d+)*(?![\w/])")
_CITATION_NUMBER = re.compile(
    r"(?i)(?:\b(?:sections?|sec|ss|s|u/s|articles?|art|orders?|o|rules?|r|chapter|schedule|clause|sub-?section|"
    r"sub-?rule|item|no|nos)\.?\s*(?:\d[\w-]*\s*(?:,|and|&|to|-)\s*)*$|\b(?:act|ordinance|code|order|rules|regulations?),?\s*$"
    r"|\(\s*$)")
_STATUTE_YEAR = re.compile(r"\b(?:Act|Ordinance|Code|Order|Procedure|Rules|Regulations?|Constitution|Law|Laws|"
                           r"Penal|Evidence|Shahadat|CPC|CrPC|PPC|QSO|MFLO)\b[^.;]{0,25}[,(]?\s*$")
_UNITS = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
          "seventeen eighteen nineteen twenty").split()
_TENS = {"thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}


def _input_numbers(text: str) -> set[str]:
    nums = {re.sub(r"[,]", "", n) for n in _NUMBER.findall(text)}
    low = text.lower()
    for i, w in enumerate(_UNITS):
        if re.search(rf"\b{w}\b", low):
            nums.add(str(i))
    for w, v in _TENS.items():
        if re.search(rf"\b{w}\b", low):
            nums.add(str(v))
    return nums


_CITES = re.compile(r"(?i)\b(?:sections?|sec\.|s\.|u/s|articles?|art\.|order|rule)\s*\d|\b(?:PPC|CrPC|CPC|QSO|MFLO)\b"
                    r"|\b[A-Z][a-z]+(?:\s+[A-Z][a-z()-]+)*\s+(?:Act|Ordinance|Code|Order)\b|دفعہ|سیکشن")
_AFTER_CITATION = re.compile(r"\s*[,،]?\s*(?:CPC|CrPC|PPC|QSO|of\s+the|of\s+[A-Z]|پاکستان|ضابطہ|تعزیرات|قانون|"
                             r"کے\s+تحت|آرڈر|رول)")
# a quantity in words, alone or with its digits: "twelve (12) months", "thirty days" (eval v2_r3 V20: an invented
# non-compete period was missed -- "(12)" read like a sub-clause number, and words were not checked at all)
_WORD_QUANTITY = re.compile(
    r"(?i)\b(" + "|".join(_UNITS[1:] + list(_TENS)) + r")(?:[\s-]+(?:" + "|".join(_UNITS[1:10]) + r"))?"
    r"(?:\s*\(\s*\d+\s*\))?\s+(?:days?|weeks?|months?|years?|hours?|rupees|lakhs?|crores?|percent|per\s+cent)\b")


def invented_facts(sentence: str, given: str, lead: str = "") -> list[str]:
    """Facts in `sentence` (a condition, a number, a quantity, a name) absent from the lawyer's input `given`.
    [Placeholders], list and clause numbers, citation numbers and Act years never count. `lead` = the text just before
    the sentence (a citation word the sentence splitter left there: "Section." | "354, CrPC ...")."""
    s = re.sub(r"\[[^\]]*\]", " ", sentence or "")
    g = (given or "").lower()
    out: list[str] = []
    for m in _CONDITION.finditer(s):
        w = m.group(0).lower()
        root = re.match(r"[a-z]+", w).group(0)[:6]
        if root not in g and w not in g:
            out.append(m.group(0))
    nums = _input_numbers(given or "")
    cites_law = bool(_CITES.search(s))
    for m in _WORD_QUANTITY.finditer(s):
        word = m.group(1).lower()
        # a PERIOD in a sentence citing a provision is the law's ("punishable with up to seven years under s.420",
        # "the limitation of four months under s.30"); an amount is always the case's
        if cites_law and re.search(r"(?i)(?:days?|weeks?|months?|years?|hours?)$", m.group(0)):
            continue
        value = str(_UNITS.index(word)) if word in _UNITS else str(_TENS[word])
        if value not in nums and word not in g:
            out.append(" ".join(m.group(0).split()))
    # a list or clause marker is not a fact: "1.", "(a)", "2.1", "3.2.1"
    body = re.sub(r"^\s*(?:\(?\d{1,2}(?:\.\d{1,2})*[.)]?|\(?[a-z][.)])\s+", " ", s)
    ctx = (lead or "")[-40:] + " "
    for m in _NUMBER.finditer(body):
        n = m.group(0)
        before = (ctx + body[:m.start()])[-30:]
        if _CITATION_NUMBER.search(before) or _AFTER_CITATION.match(body[m.end():]):
            continue
        if re.search(rf"(?i)\b(?:{'|'.join(_UNITS[1:] + list(_TENS))})\s*\(\s*$", body[max(0, m.start() - 25):m.start()]):
            continue                                   # "twelve (12)": judged above as a quantity in words
        # the year of an Act ("the Code of Criminal Procedure, 1898") is part of the citation
        if re.fullmatch(r"1[89]\d\d|20\d\d", n) and _STATUTE_YEAR.search(body[max(0, m.start() - 90):m.start()]):
            continue
        if re.sub(r",", "", n) in nums or n in (given or ""):
            continue
        out.append(n)
    for m in _NAME.finditer(s):
        name = (m.group(1) or m.group(2) or "").strip()
        if name and name.lower() not in g and not all(t.lower() in g for t in name.split()):
            out.append(name)
    return list(dict.fromkeys(out))


def with_placeholders(sentence: str, facts: list[str]) -> str:
    """The sentence with each invented fact replaced: a condition's whole clause, a number or name in place."""
    out = sentence
    for f in facts:
        if _CONDITION.fullmatch(f):
            parts = re.split(r"([,;])", out)
            out = "".join("[fact to be supplied]" if re.search(rf"(?i)\b{re.escape(f)}\b", p) and p not in ",;" else p
                          for p in parts)
            out = re.sub(r"(?:\s*,?\s*\[fact to be supplied\])+", lambda m: (", " if m.group(0).lstrip().startswith(",")
                                                                         else " ") + "[fact to be supplied]", out)
        else:
            out = re.sub(rf"(?<![\w]){re.escape(f)}(?![\w])", "[placeholder]", out)
    return re.sub(r"\s{2,}", " ", out)
