"""The provision of a statute whose own heading governs the question's issue
(lawyer research, 2026-10-14).

Live eval E11: "Within what time must a suit for pre-emption be filed in
Punjab?" -- Punjab Pre-emption Act 1991 s.30 is headed "Limitation" and holds
the answer (four months). Similarity retrieval depends on an LLM query
expansion: with "Pre-Emption Act ... filing period" added, s.30 ranked 7th; with
the bare question it was not in the top 28. When it was missed, the answer
declared the whole Act silent.

So, deterministically and bounded:
  1. the ISSUE is recognised from the question (only issues whose governing
     provision is conventionally headed by name -- limitation);
  2. the ACT is the corpus statute whose distinctive name words ALL appear in
     the question ("pre-emption"), never a different province's Act;
  3. the corpus heading index (corpus_index) is searched for that Act's
     provision headed by the issue ("Limitation");
  4. its exact text is fetched (exact_provision.fetch) and placed first.

Nothing is invented when a step finds nothing: retrieval proceeds as before,
and the answer guard (ai/visible_authority.py) still stops a few retrieved
sections from becoming "the Act is silent".
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

LOOKUP_VERSION = "issue-heading-v1"
_MAX_ACTS = 2
_MAX_PROVISIONS = 2

# (issue, how a question asks about it, how the governing provision is headed)
_ISSUES = (
    ("husband_talaq",
     re.compile(
         # The actor matters: "a wife divorcing her husband" must not pin
         # the husband's notice provision merely because it says "husband".
         r"\b(?:husband|shohar)\b.{0,100}\b(?:talaq|divorc(?:e|ed|ing))\b"
         r"|\b(?:talaq|divorc(?:e|ed|ing))\b.{0,80}\bby\s+(?:the\s+|my\s+|her\s+|a\s+)?(?:husband|shohar)\b",
         re.IGNORECASE),
     re.compile(r"^\s*talaq\s*$", re.IGNORECASE)),
    ("limitation",
     re.compile(r"\b(?:within (?:what|which|how much) time|time[- ]limit|limitation|how long (?:do|does|have|has|is)|"
                r"deadline|period (?:of|for) (?:filing|instituting|bringing|limitation)|time (?:to|for) "
                r"(?:file|sue|bring|institute)|kitn[ae] (?:din|waqt|arse|arsay|muddat)|muddat|miyad)\b"
                r"|مدت|میعاد|کتنے (?:دن|عرصے|وقت)", re.IGNORECASE),
     re.compile(r"\blimitation\b|\btime[- ]limit\b|period of limitation", re.IGNORECASE)),
)

# Words that name no particular statute.
_GENERIC = frozenset("""
act acts ordinance ordinances code order rules regulation regulations the of and for in on to by
punjab pakistan west khyber pakhtunkhwa sindh balochistan islamabad federal capital territory provincial
amendment amended
""".split())
_ISSUE_WORDS = frozenset({"limitation", "time", "period", "limit"})
_PROVINCES = {"punjab": "punjab", "sindh": "sindh", "khyber": "kp", "pakhtunkhwa": "kp",
              "balochistan": "balochistan", "islamabad": "islamabad"}
_WORD = re.compile(r"[a-z][a-z\-]+")


def _words(text: str) -> set[str]:
    from app.ai import period_support
    return set(_WORD.findall(period_support.normalise(text or "").lower()))


def issue_of(question: str):
    for name, asks, headed in _ISSUES:
        if asks.search(question or ""):
            return name, headed
    return None


def acts_named(question: str, province: str | None, index) -> list[str]:
    """Corpus statutes whose distinctive name words all appear in the question,
    most specific first; an Act of a different province is never offered."""
    q = _words(question)
    want = (province or "").lower()
    out = []
    for statute in index.statutes:             # a property on CorpusIndex
        words = _words(re.sub(r"\d+", " ", statute))
        distinctive = {w for w in words if w not in _GENERIC and len(w) > 2}
        if not distinctive or not distinctive <= q:
            continue
        # "Does the Pre-emption Act prescribe a LIMITATION period?" names the
        # issue, not the Limitation Act: a statute matched only by issue words
        # is not the Act the question is about.
        if distinctive <= _ISSUE_WORDS:
            continue
        act_province = next((p for w, p in _PROVINCES.items() if w in words), None)
        if act_province and want and want not in ("unknown", "federal") and act_province != want:
            continue
        out.append((len(distinctive), statute))
    return [s for _, s in sorted(out, key=lambda x: -x[0])][:_MAX_ACTS]


def governing(question: str, province: str | None) -> list:
    """[(ParsedCitation, heading)] for the issue's governing provision(s)."""
    from app.ai import corpus_index
    from app.ai.answer_citations import ParsedCitation, normalise_statute
    issue = issue_of(question)
    if not issue:
        return []
    _, headed = issue
    try:
        index = corpus_index.get_index()
    except Exception:
        logger.warning("issue_lookup: corpus index unavailable", exc_info=True)
        return []
    found = []
    for act in acts_named(question, province, index):
        cov = index.coverage(act)
        if cov is None:
            continue
        for section, headings in sorted((getattr(cov, "provisions", {}) or {}).items()):
            heading = next((h for h in headings or () if headed.search(h or "")), None)
            if heading:
                found.append((ParsedCitation(act, str(section), (normalise_statute(act), str(section))), heading))
            if len(found) >= _MAX_PROVISIONS:
                return found
    return found


def fetch_governing(question: str, province: str | None, research: bool = True) -> list[dict]:
    """Exact text of the governing provision(s), each chunk marked with the
    heading that made it governing. Empty when nothing qualifies."""
    from app.ai import exact_provision
    hits = governing(question, province)
    if not hits:
        return []
    citations = [cit for cit, _ in hits]
    # Keep lawyer research's established lookup untouched. Client chat needs
    # the following chunks too, because the first 800 characters of a long
    # provision can omit its operative period or exception.
    if research:
        fetched = exact_provision.fetch(citations, True)
    else:
        try:
            fetched = exact_provision.fetch(citations, include_continuations=True)
        except Exception:
            logger.warning("issue_lookup: client exact fetch unavailable; continuing normal retrieval", exc_info=True)
            return []
    out = []
    for cit, heading in hits:
        for chunk in fetched.get(exact_provision.label(cit)) or []:
            out.append({**chunk, "statute": chunk.get("statute") or cit.statute,
                        "issue_provision": {"statute": cit.statute, "section": cit.section, "heading": heading}})
    logger.info("issue_lookup: %s", [(c["issue_provision"]["statute"], c["issue_provision"]["section"]) for c in out])
    return out


def governing_label(question: str, province: str | None) -> list[tuple[str, str, str]]:
    """(statute, section, heading) known to govern the issue -- for the answer
    guard, which needs to know that such a provision EXISTS even when its text
    was not in the evidence."""
    return [(cit.statute, cit.section, heading) for cit, heading in governing(question, province)]
