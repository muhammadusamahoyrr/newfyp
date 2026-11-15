"""The lawyer drafter's legal check on a finished AI reply (2026-10-14, v2 2026-10-15).

One place for what used to be three steps in the route, so that every check
looks at the SAME sentences and the counts describe the text the lawyer is
actually shown:

  * the legal-authority check (ai/visible_authority.py) with the corpus
    REQUIRED, read from the drafter's IDENTITY index, and the drafter-only
    subject check (a provision of the right Act that does not deal with what
    the sentence relies on it for);
  * CPC Order/Rule citations, by their real identity (ai/cpc_provisions.py):
    an Order or Rule the Code does not have is withheld; one our copy lacks
    is "not verified"; one cited for a subject it does not cover is withheld
    or "not verified";
  * personal-law Acts cited outside their community (the Divorce Act 1869 in
    a Muslim custody matter), or where the community is not known;
  * another province's Act, or a provincial Act in a neutral draft, and a
    federal provision the provincial law may displace in a neutral draft
    (ai/draft_jurisdiction).

The checks read a NORMALISED copy of the reply -- Urdu/Arabic digits, Unicode
hyphens, "سیکشن"/"دفعہ"/"dafa" and Urdu Act names mapped to the forms the
parsers read -- built to the SAME LENGTH, so a withheld span maps onto the
lawyer's original text exactly. ("سیکشن 354، CrPC" was invisible to both
checkers; "561‑A" with a non-breaking hyphen too.)

Withheld sentences are removed with no note in the text; their reasons travel
in the result. Counts:
  supported   -- provisions cited in the FINAL text that the library holds and
                 that passed every check. "Found and consistent", NOT "the
                 claim is legally right".
  withheld    -- sentences removed, each with its reasons.
  not_checked -- provisions cited in the final text that could not be
                 verified: not in our copy, several provisions under one
                 number, a subject that does not match, applicability unknown
                 -- each with its reason. Never presented as verified.
A provision cited only in a withheld sentence is in none of the final counts.

Raises whatever the checks raise (exact_provision.CorpusUnavailable when the
corpus cannot be read); the caller fails closed.
"""
from __future__ import annotations

import re

from app.ai import draft_jurisdiction

# ── normalisation (same length) ─────────────────────────────────────────────
_SAME_LENGTH = [
    (re.compile(r"[‐-―−﹘﹣－]"), lambda m: "-"),
    (re.compile(r"[    ]"), lambda m: " "),
    (re.compile("،"), lambda m: ","),
]
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_WORDS = [  # (pattern, replacement padded to the match's length)
    (r"مجموعہ\s+ضابطہ\s+فوجداری|ضابطہ\s+فوجداری", "CrPC"),
    (r"مجموعہ\s+تعزیرات\s+پاکستان|تعزیرات\s+پاکستان", "PPC"),
    (r"مجموعہ\s+ضابطہ\s+دیوانی|ضابطہ\s+دیوانی", "CPC"),
    (r"سیکشن|سکشن|سیکشن|دفعہ|دفعات|\bdaf'?a\b|\bdafa\b", "Sec."),
]


_ABBREV_DOT = re.compile(r"\b(No|Nos|Mr|Mrs|Ms|Mst|Dr|vs|etc|Sr|Jr|St)\.(?=\s)")


def normalise(text: str) -> str:
    """A copy of `text`, the same length, that the citation parsers can read."""
    out = (text or "").translate(_DIGITS)
    for rx, fn in _SAME_LENGTH:
        out = rx.sub(fn, out)
    # "FIR No. 12/2026" must not end a sentence for the checks ("No." split the
    # citation away from its subject). Same length: the dot becomes "·".
    out = _ABBREV_DOT.sub(lambda m: m.group(1) + "·", out)
    for pattern, repl in _WORDS:
        def pad(m, repl=repl):
            n = len(m.group(0))
            return (repl + " " * n)[:n] if n >= len(repl) else repl[:n]
        out = re.sub(pattern, pad, out, flags=re.IGNORECASE)
    assert len(out) == len(text or ""), "normalisation must keep offsets"
    return out

# ── personal law ────────────────────────────────────────────────────────────
# Acts that apply to one community's marriages and family matters only.
# NEEDS LAWYER REVIEW: the list is deliberately short.
_PERSONAL_LAW = [
    (re.compile(r"(?i)\bDivorce\s+Act\b"), "christian", "the Christian community"),
    (re.compile(r"(?i)Christian\s+Marriage\s+Act"), "christian", "the Christian community"),
    (re.compile(r"(?i)Parsi\s+Marriage"), "parsi", "the Parsi community"),
    (re.compile(r"(?i)Hindu\s+Marriage|Hindu\s+Disposition|Hindu\s+Inheritance"), "hindu", "the Hindu community"),
    (re.compile(r"(?i)Muslim\s+Family\s+Laws|Dissolution\s+of\s+Muslim\s+Marriages"), "muslim", "Muslims"),
]
_COMMUNITY = {
    "christian": re.compile(r"(?i)\bchristian|\bchurch\b"),
    "hindu": re.compile(r"(?i)\bhindu|\bmandir\b"),
    "parsi": re.compile(r"(?i)\bparsi"),
    "muslim": re.compile(r"(?i)\bmuslim|\bkhula|\btalaq|\bnikah|\biddat|haq\s*mehr|\bdower\b|خلع|طلاق|نکاح|عدت|حق\s*مہر"),
}


def community_of(context: str) -> str | None:
    """The matter's community from what the request/draft SAYS about the
    parties -- never from the name of an Act it cites ("... under the Muslim
    Family Laws Ordinance" would otherwise vouch for itself)."""
    text = context or ""
    for rx, _comm, _who in _PERSONAL_LAW:
        text = rx.sub(" ", text)
    text = re.sub(r"(?i)Muslim\s+Family\s+Laws\s+Ordinance|Dissolution\s+of\s+Muslim\s+Marriages\s+Act", " ", text)
    found = {k for k, rx in _COMMUNITY.items() if rx.search(text)}
    return found.pop() if len(found) == 1 else None


def _personal_law(units, norm: str, community: str | None) -> tuple[list[dict], list[str]]:
    """(withheld units, not-checked labels): a community's Act cited in
    another community's matter is withheld; where the matter's community is
    not known, it is not verified."""
    from app.ai import tool_contract
    withheld, unknown = [], []
    for a, b in units:
        for ref in tool_contract.provision_refs(norm[a:b]):
            for rx, comm, who in _PERSONAL_LAW:
                if not rx.search(ref.statute or ""):
                    continue
                shown = f"Section {ref.section} {ref.statute}".strip()
                # No community is presumed -- not even Muslim (2026-10-15, user
                # decision): an unknown community makes EVERY personal-law Act
                # "not verified".
                if community is None:
                    unknown.append(f"{shown} (applies to {who} only -- confirm the parties' personal law)")
                elif community != comm:
                    withheld.append({"span": (a, b), "text": None, "reasons": [
                        f"{shown} applies to {who}; this matter is under {community.capitalize()} personal law."]})
    return withheld, unknown

# ── CPC Order/Rule citations ────────────────────────────────────────────────

def _cpc_rules(units, norm: str, request: str = "") -> tuple[list[dict], list[tuple], list[str]]:
    """(withheld, [(supported label, unit span)], not-checked labels) for every Order/Rule
    citation. A unit naming another Act's "Order" (Supreme Court Rules ...)
    is not read as the CPC."""
    from app.ai import cpc_provisions, draft_claims
    from app.ai import visible_authority as va
    withheld, supported, unknown = [], [], []
    try:
        cat = cpc_provisions.catalogue()
    except Exception:
        cat = None
    for a, b in units:
        unit = norm[a:b]
        refs = cpc_provisions.parse_refs(unit)
        if not refs or re.search(r"(?i)Supreme\s+Court\s+Rules|High\s+Court\s+Rules", unit):
            continue
        for order, rule, s0, s1 in refs:
            label = f"{cpc_provisions.label_for(order, rule)} CPC"
            if cat is None:
                unknown.append(f"{label} (the CPC index could not be read)")
                continue
            prov = cat["provisions"].get(cpc_provisions.label_for(order, rule))
            if prov is None:
                rules = [int(re.match(r"\d+", p.number).group(0)) for p in cat["provisions"].values()
                         if p.kind == "order_rule" and p.order == order]
                n = int(re.match(r"\d+", rule).group(0))
                if order > 51 or (rules and n > max(rules) + 3):
                    withheld.append({"span": (a, b), "text": None, "reasons": [
                        f"{label} does not exist: the CPC has {'51 Orders' if order > 51 else f'{max(rules)} rules in Order {cpc_provisions.roman(order)}'}."]})
                else:
                    unknown.append(f"{label} (not in our copy of the Code)")
                continue
            if va.is_title(unit):
                unknown.append(f"{label} (named in a heading line; a heading is not a legal claim)")
                continue
            if not va._relied_on(unit):
                supported.append((label, (a, b)))     # a mention, not reliance: not judged
                continue
            # S2 (draft_claims): a stated legal effect the rule's text contradicts
            effect, said = draft_claims.claimed_effect(unit, prov.content)
            if effect == "contradicted":
                withheld.append({"span": (a, b), "text": None, "reasons": [
                    f"{label}'s own text says otherwise: \"{said}\"."]})
                continue
            window = va.clause_window(unit, s0, s1, _NoRef)
            words = va._subject_words(window, _NoRef) | va.urdu_subject_words(window)
            if not words:
                unknown.append(f"{label} (what the sentence relies on it for could not be read, so it was not checked)")
                continue
            df = _cpc_df(cat)
            head = {w for w in va._terms(prov.heading) if w not in va._GENERIC}
            # The words around the citation can be the wrong clause: "the plaint is returned ... for filing in the
            # appropriate court, as this Court lacks such jurisdiction, in accordance with Order VII Rule 10" read only
            # "lacks such jurisdiction" and WITHHELD a correct rule (eval v2_r4 dev, V02). The whole sentence agreeing
            # with the rule's heading counts too -- and still goes through the scope, mixed-clause, S1 and S2 checks.
            whole = va._subject_words(re.sub(r"\[[^\]]*\]", " ", unit), _NoRef) | va.urdu_subject_words(unit)
            if va._agrees(words, head, df) or va._agrees(whole, head, df) or _rule_text_agrees(unit, prov, df):
                # Agreement with the heading is not enough (eval v2 dev, V05):
                # a rule of an Order limited to one class of suit applies only
                # when the sentence or the request shows that class, and a
                # clause that ALSO relies on the rule for another provision's
                # subject is not supported by it.
                scope = cpc_provisions.order_scope(cat, order)
                if scope is not None:
                    seen = va._terms(re.sub(r"\[[^\]]*\]", " ", f"{unit} {request}"))
                    if not any(va._same(w, x) for w in scope[1] for x in seen):
                        unknown.append(f"{label} (Order {cpc_provisions.roman(order)} applies only to "
                                       f"{scope[0].lower()}; nothing in the request or this sentence shows such a "
                                       f"suit, so its use here was not verified)")
                        continue
                covered = head | {w for w in va._terms(" ".join((prov.content or "")[:4000].split()))
                                  if w not in va._GENERIC}
                foreign = va.foreign_subject(
                    va._subject_words(re.sub(r"\[[^\]]*\]", " ", unit), _NoRef), va.request_words(request, _NoRef),
                    covered, _cpc_blocks(cat), (order, int(re.match(r"\d+", rule).group(0))),
                    bool(va._RESIDUAL.search(f"{prov.heading} {prov.content}")))
                if foreign:
                    unknown.append(f"{label} (the sentence also relies on it for {', '.join(foreign)}, which "
                                   f"\"{prov.heading}\" does not cover)")
                    continue
                # S1 / S2 (draft_claims): the action relied on, with its object, and
                # any stated legal effect must be in the rule's own text.
                obj = draft_claims.claim_object(unit, prov.content)   # the whole sentence: the window drops the commas around "under X,"
                if obj:
                    unknown.append(f"{label}{obj}")
                    continue
                if effect == "silent":
                    unknown.append(f"{label} (its text does not say this makes anything {said})")
                    continue
                supported.append((label, (a, b)))
                continue
            # A DISTINCTIVE word of the claim heads another provision of the
            # Code: the cited rule is the wrong one. Withheld, naming the
            # subject -- not a replacement we have not verified.
            distinctive = {w for w in words if df.get(va._stem(w), 0) <= va._DISTINCTIVE_DF}
            others = [p.heading for lab, p in cat["provisions"].items() if lab != prov.label and p.heading]
            hit = sorted(w for w in distinctive if any(any(va._same(w, x) for x in va._terms(h)) for h in others))
            if hit:
                withheld.append({"span": (a, b), "text": None, "reasons": [
                    f"{label} is \"{prov.heading}\", which does not support what this sentence relies on it for "
                    f"({', '.join(hit)})."]})
            else:
                unknown.append(f"{label} (\"{prov.heading}\" does not match what the sentence relies on it for)")
    return withheld, supported, unknown


# The rule's own TEXT, not only its heading (eval v2_r3 dev, 2026-10-15): "the
# plaint does not disclose any cause of action, contrary to Order VII Rule 11"
# and "the plaint is returned ... to be instituted in the Court having
# jurisdiction, in accordance with Order VII Rule 10" were WITHHELD -- "plaint"
# heads 11 CPC headings, so the heading alone could not agree, and Rule 11's
# text literally says "does not disclose a cause of action". Stricter than the
# sections' text check (2 words): THREE subject words of the sentence in the
# rule's own text (its slice only -- cpc_provisions.split_rules), one of them
# distinctive in the Code's headings, so a common word ("notice", "suit")
# cannot carry it (Order XI Rule 17 for a notice to the Government stays out).
_TEXT_MIN_SHARED = 3


def _rule_text_agrees(unit: str, prov, df) -> bool:
    from app.ai import visible_authority as va
    sentence = va._subject_words(re.sub(r"\[[^\]]*\]", " ", unit), _NoRef) | va.urdu_subject_words(unit)
    body = {w for w in va._terms(" ".join((prov.content or "")[:4000].split())) if w not in va._GENERIC}
    shared = {w for w in sentence if any(va._covers(x, w) for x in body)}
    return len(shared) >= _TEXT_MIN_SHARED and any(df.get(va._stem(w), 0) <= va._DISTINCTIVE_DF for w in shared)


class _NoRef:                 # _subject_words strips the cited Act's name; none here
    statute = ""


_CPC_DF: dict = {}


def _cpc_blocks(cat: dict) -> dict:
    """Subject blocks of the Code: sections by number, each Order's rules by
    rule number (visible_authority.subject_blocks)."""
    if "blocks" not in cat:
        from app.ai import visible_authority as va
        rows = []
        for p in cat["provisions"].values():
            m = re.fullmatch(r"(\d+)", str(p.number))
            if p.heading and m:
                rows.append((p.order if p.kind == "order_rule" else 0, int(m.group(1)), p.heading))
        cat["blocks"] = va.subject_blocks(rows)
    return cat["blocks"]


def _cpc_df(cat: dict) -> dict:
    key = id(cat)
    if key not in _CPC_DF:
        from collections import Counter
        from app.ai import visible_authority as va
        _CPC_DF.clear()
        _CPC_DF[key] = Counter(st for p in cat["provisions"].values() if p.heading
                               for st in {va._stem(w) for w in va._terms(p.heading) if w not in va._GENERIC})
    return _CPC_DF[key]


# ── our own labels must never become draft text ─────────────────────────────
# The law context names unidentified text "provision not identified"; the
# model copied it into a notice ("...required under CPC 1908 -- provision not
# identified", eval v2_r2 V23). Any sentence carrying one of our labels is
# withheld.
_INTERNAL_LABELS = re.compile(r"(?i)provision\s+not\s+identified|rule\s+not\s+shown|order\s+not\s+determined|"
                              r"CPC\s+Appendix|\[(?:STATUTE|EXACT\s+TEXT|CASE\s+LAW)\]|PAKISTANI\s+LAW\s+CONTEXT")


def _internal_labels(units, norm: str) -> list[dict]:
    return [{"span": (a, b), "text": None, "reasons": [
        "This sentence contains an internal label from the legal-text library, not a citation; "
        "the provision it was meant to cite is unknown."]}
        for a, b in units if _INTERNAL_LABELS.search(norm[a:b])]


# No corrective pointer we have not verified ("see Order VIII Rule 1", "it
# matches Constitution s.4", "an offence is defined in ..."): the reason says
# what is wrong, never what to cite instead.
_POINTERS = re.compile(r"\s*\((?:it matches|an offence is defined in)[^)]*\)|;\s*see [^)]*|\s*\(see [^)]*\)", re.IGNORECASE)


def _clean_reason(reason: str) -> str:
    return _POINTERS.sub("", reason)


# ── section numbers no Act has ──────────────────────────────────────────────

def _malformed(units, norm: str) -> list[dict]:
    """"Section 1956 CPC": the shared parser drops year-like numbers, so the
    authority check never saw it and it reached the proposal. Both parsers;
    a number of 1000+ (a year or page number) or far past the Act's last
    section is withheld as a provision the Act does not have."""
    from app.ai import corpus_index, tool_contract
    from app.ai import visible_authority as va
    from app.ai.citation_verification import parse_statute_citations
    try:
        index = corpus_index.get_drafter_index()
    except Exception:
        index = None
    out = []
    for a, b in units:
        unit = norm[a:b]
        cands = [(r.section, r.statute) for r in tool_contract.provision_refs(unit)]
        try:
            cands += [(c.section, c.statute) for c in parse_statute_citations(unit, index)
                      if getattr(c, "unit", "section") == "section"]
        except Exception:
            pass
        cands += [(m.group(1), m.group(2)) for m in re.finditer(
            r"(?i)\bSection\s+(\d{4})\s+(?:of\s+(?:the\s+)?)?((?:Code\s+of\s+Civil\s+Procedure|Code\s+of\s+Criminal\s+Procedure|CPC|CrPC|PPC|Pakistan\s+Penal\s+Code))", unit)]
        for section, statute in cands:
            m = re.match(r"(\d+)", str(section))
            if not m:
                continue
            cov = index.coverage(statute) if index is not None else None
            n = int(m.group(1))
            if n >= 1000 or (cov is not None and va._beyond_range(section, cov)):
                highest = getattr(cov, "highest", 0) if cov is not None else 0
                out.append({"span": (a, b), "text": None, "reasons": [
                    f"Section {section} {statute} does not exist" + (f": the Act's sections run to {highest}." if highest else
                                                                    " (a year or page number read as a section).")]})
                break
    return out


# ── the check ───────────────────────────────────────────────────────────────

_REASON = {"unverified": "not in our copy", "ambiguous": "several provisions share this number"}
_TITLE_HINT = "named in a heading line"


# ── when the check leaves NOTHING to insert (2026-10-15) ─────────────────────
# Five of 44 dev replies (eval v2) were withheld whole: each a single sentence
# resting on a wrong or unknown authority. The empty state said only "rephrase".
# What the lawyer can do next depends on WHY -- and is never "insert it anyway":
# the withheld text stays out of the draft.
_NEXT_STEPS = (
    ("not_found", re.compile(r"(?i)internal label|not in our copy|could not be checked"),
     "The provision this point needs is not in our legal library. Name the provision you want cited, or ask "
     "for the paragraph with a [PROVISION] placeholder."),
    ("nonexistent", re.compile(r"(?i)does not exist"),
     "The reply cited a provision that does not exist. Name the provision you mean, or ask for the paragraph "
     "with a [PROVISION] placeholder."),
    ("applicability", re.compile(r"(?i)personal law|is \w+ law, and|no jurisdiction was chosen|may not govern"),
     "Whether the cited law applies depends on facts the request does not give (the parties' personal law or "
     "the province). State them, or ask for the paragraph with a [PROVISION] placeholder."),
    ("wrong_authority", re.compile(r"(?i)does not support|not what the statement describes|omitted"),
     "The cited provision does not cover what the sentence relies on it for. Name the provision you mean, or "
     "ask for the paragraph with a [PROVISION] placeholder."),
)


def next_step(text: str, withheld: list[dict]) -> dict | None:
    """{kind, text} when nothing survived the check; None otherwise."""
    if (text or "").strip() or not withheld:
        return None
    reasons = " ".join(r for w in withheld for r in w.get("reasons", []))
    for kind, pat, say in _NEXT_STEPS:
        if pat.search(reasons):
            return {"kind": kind, "text": say}
    return {"kind": "other", "text": "Name the provision you mean, or ask for the paragraph with a [PROVISION] "
                                     "placeholder."}


def check(drafted: str, question: str, evidence: list[dict], province: str, topic: str | None,
          context: str = "", _alternative: bool = True, own_text: str = "") -> dict:
    from app.ai import draft_claims, source_currency, visible_authority
    from app.ai.visible_authority import _units
    norm = normalise(drafted)
    urdu = bool(re.search(r"[؀-ۿ]", drafted))
    stats: dict = {}
    _, authority = visible_authority.authorities(
        norm, question, urdu, research=True, evidence=evidence, inline_notice=False,
        require_corpus=True, stats=stats, drafter=True, request=f"{question} {context}")
    units = _units(norm)
    malformed = _malformed(units, norm) + _internal_labels(units, norm)
    cpc_withheld, cpc_supported, cpc_unknown = _cpc_rules(units, norm, f"{question} {context}")
    pl_withheld, pl_unknown = _personal_law(units, norm, community_of(f"{question} {context} {norm}"))
    # S3 (draft_claims): a fact the lawyer did not give -- compared with the
    # lawyer's INPUT only (instruction, selection, document, case record), never
    # with the law context, where eval v2_r3 V09's invented fact came from.
    given = f"{question} {context}"
    fact_units = []
    for a, b in units:
        facts = draft_claims.invented_facts(norm[a:b], given, lead=norm[max(0, a - 40):a])
        if facts:
            fact_units.append({"span": (a, b), "text": None, "facts": facts, "reasons": [
                f"This sentence states a fact you did not give: {', '.join(facts)}."]})
    # Articles the 27th Amendment omitted WHOLE (184, 186, 186A, 191A):
    # reliance withheld, a historical mention kept and listed (source_currency).
    omitted_withheld, historical_notes = source_currency.omitted_article_check(units, norm)
    found = authority + malformed + cpc_withheld + pl_withheld + draft_jurisdiction.foreign_units(norm, province) \
        + draft_jurisdiction.neutral_units(norm, province, topic) + fact_units \
        + omitted_withheld

    merged: dict[tuple, dict] = {}
    for w in found:
        span = tuple(w["span"])
        m = merged.setdefault(span, {"span": span, "text": drafted[span[0]:span[1]], "reasons": []})
        for r in w.get("reasons", []):
            r = _clean_reason(r)
            if r not in m["reasons"]:
                m["reasons"].append(r)
    withheld = sorted(merged.values(), key=lambda w: w["span"])
    # The CPC on file is Punjab's (ai/source_currency.py, batch 5): outside a
    # confirmed-Punjab matter an AI-written CPC citation is taken out of the
    # proposal -- ONLY the citation (with its "under ..."), or replaced by a
    # [Verify ...] placeholder where removing it would break the sentence. The
    # rest of the sentence, the lawyer's own text and history are untouched.
    cpc = source_currency.cpc_clause_edits(units, norm, province, own_text, skip=set(merged))
    text = source_currency.apply_edits(drafted, [w["span"] for w in withheld], cpc["main"])
    withheld = withheld + [{"span": tuple(w["span"]), "text": w["text"], "reasons": w["reasons"]}
                           for w in cpc["withheld"]]

    supported, not_checked = [], []
    unconfirmed_reason = {}
    for unit in stats.get("units", []):
        if tuple(unit["span"]) in merged:
            continue
        for ref in unit["refs"]:
            st = ref["status"]
            if st == "valid":
                bucket, shown = supported, ref["shown"]
            elif st in _REASON:
                bucket, shown = not_checked, f"{ref['shown']} ({_REASON[st]})"
            elif st == "unconfirmed":
                # The specific reason (a heading line, a subject that could not
                # be read, a heading our copy lacks, a heading that does not match).
                bucket, shown = not_checked, f"{ref['shown']}{ref.get('hint') or ' (its subject does not match what the sentence relies on it for)'}"
            else:
                continue
            if shown not in bucket:
                bucket.append(shown)
    # CPC Order/Rule and personal-law results, for units that stay visible
    for lab, span in cpc_supported:
        if tuple(span) not in merged and lab not in supported:
            supported.append(lab)
    for lab in cpc_unknown + pl_unknown:
        if lab not in not_checked:
            not_checked.append(lab)
    # The CPC on file is Punjab's text, the Constitution on file is the 2012
    # one (ai/source_currency.py): outside Punjab a CPC citation, and anywhere a
    # Constitution citation, is never "supported" -- not checked, with why.
    supported, moved = source_currency.gate_supported(supported, province)
    for lab in moved:
        if lab not in not_checked:
            not_checked.append(lab)
    # Historical mentions in units that stay visible (one withheld for another
    # reason is not listed).
    historical_notes = list(dict.fromkeys(n for span, n in historical_notes if tuple(span) not in merged))
    if historical_notes:
        historic = {source_currency.article_of(n) for n in historical_notes}
        supported = [x for x in supported if not (source_currency.is_constitution(x)
                                                   and source_currency.article_of(x) in historic)]
        not_checked = [x for x in not_checked if not (source_currency.is_constitution(x)
                                                       and source_currency.article_of(x) in historic)]
        not_checked += historical_notes
    # Personal-law Acts are never "supported" while applicability is unknown.
    if pl_unknown:
        bare = {re.sub(r"\s+\(.*$", "", x) for x in pl_unknown}
        supported = [s for s in supported if s not in bare]
    # Anything still cited in the final text that no check accounted for is
    # NOT checked -- it must not vanish from the counts. Both parsers, on the
    # normalised final text.
    from app.ai import tool_contract
    from app.ai.answer_citations import normalise_statute
    from app.ai.citation_verification import parse_statute_citations

    def key(section, statute):
        return (str(section).upper().replace("-", ""), normalise_statute(re.sub(r"\s+\(.*$", "", statute)))
    accounted = set()
    for s in supported + not_checked:
        m = re.match(r"(?:Section|Article)\s+(\S+)\s+(.+)", s)
        if m:
            accounted.add(key(m.group(1), m.group(2)))
    final_norm = normalise(text)
    found = [(f"Section {r.section} {r.statute}", r.section, r.statute) for r in tool_contract.provision_refs(final_norm)]
    found += [(f"{'Article' if c.unit == 'article' else 'Section'} {c.section} {c.statute}", c.section, c.statute)
              for c in parse_statute_citations(final_norm) if getattr(c, "unit", "") != "order_rule"]
    for shown, section, statute in found:
        k = key(section, statute)
        if k not in accounted:
            accounted.add(k)
            not_checked.append(f"{shown.strip()} (not checked)")
    # A provision is SUPPORTED only when every sentence that relies on it is
    # (eval v2 dev, V12: s.126 CrPC, accurately described in one paragraph and
    # relied on for a bail bond in the prayer, was listed as supported and the
    # not-verified use vanished). Only a title line -- which makes no claim --
    # is folded into a supported entry.
    bare = lambda x: re.sub(r"\s+\(.*$", "", x)
    doubted = {bare(x) for x in not_checked if _TITLE_HINT not in x}
    supported = [s for s in supported if bare(s) not in doubted]
    sup_keys = {bare(x) for x in supported}
    not_checked = [x for x in not_checked if bare(x) not in sup_keys]
    # A CPC citation taken out of the text is no longer "cited"; what stayed
    # (the lawyer's own text, history) is listed with why.
    if cpc["main"] and not source_currency.cpc_citations(text):
        not_checked = [x for x in not_checked if not source_currency.is_cpc(x)]
    for note in cpc["notes"]:
        if note not in not_checked:
            not_checked.append(note)
    # Every not-checked CPC (outside Punjab) / Constitution entry says why.
    not_checked = source_currency.annotate_not_checked(not_checked, province)
    # The same draft with each invented fact replaced by a placeholder -- a
    # SEPARATE proposal, and checked again in full like any other reply.
    # The CPC citations get the [Verify ...] placeholder in it too (batch 5).
    alternative = None
    fact_spans = {tuple(f["span"]) for f in fact_units}
    cpc_alt = (source_currency.cpc_clause_edits(units, norm, province, own_text,
                                                skip=set(merged) - fact_spans)["alt"] if _alternative else [])
    if _alternative and (fact_units or cpc_alt):
        edits = [e for e in cpc_alt if not any(a <= e["span"][0] < b for a, b in fact_spans)]
        for f in sorted(fact_units, key=lambda f: f["span"]):
            a, b = f["span"]
            inner = [{"span": (e["span"][0] - a, e["span"][1] - a), "replacement": e["replacement"]}
                     for e in cpc_alt if a <= e["span"][0] < b]
            segment = source_currency.apply_edits(drafted[a:b], [], inner) if inner else drafted[a:b]
            edits.append({"span": (a, b), "replacement": draft_claims.with_placeholders(segment, f["facts"])})
        g2 = check(source_currency.apply_edits(drafted, [], edits), question, evidence, province, topic,
                   context=context, _alternative=False, own_text=own_text)
        if g2["text"].strip() and g2["text"].strip() != text.strip():
            alternative = {k: g2[k] for k in ("text", "supported", "not_checked", "withheld", "counts")}
            alternative["label"] = (
                "With [placeholders] for facts you did not give and for the CPC provision to verify"
                if fact_units and cpc_alt else
                "With [placeholders] for facts you did not give" if fact_units else
                "With a [Verify ...] placeholder for the CPC provision")
    return {
        "ran": True, "text": text,
        "placeholder_alternative": alternative,
        "next_step": next_step(text, withheld),
        "supported": supported, "not_checked": not_checked,
        "withheld": [{"text": w["text"][:240], "reasons": w["reasons"]} for w in withheld],
        "counts": {"supported": len(supported), "withheld_sentences": len(withheld), "not_checked": len(not_checked)},
        "clarify": draft_jurisdiction.clarification(province, topic, text),
    }
