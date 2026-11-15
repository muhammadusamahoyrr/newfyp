"""What the indexed CPC and Constitution texts ARE, and what they are not (2026-10-16).

Two facts about the corpus (evals/legal_sources/BATCH2_PARSER_STATUS_INDEX.md §3),
both established from the source documents, neither from a model:

* The indexed Code of Civil Procedure is the PUNJAB CODE consolidation
  (sha256 528384...), carrying Punjab's own amendments -- its footnotes cite the
  Code of Civil Procedure (Punjab Amendment) Act 2018 (XIV of 2018), Punjab
  Gazette (Extraordinary) 20 March 2018. It is labelled "federal" in the index.
  It is therefore Punjab's text: it must not be presented as the CPC of
  Islamabad, Sindh, Khyber Pakhtunkhwa or Balochistan, nor as "national" law.
  The federal and other-province texts are not in the corpus.

* The indexed Constitution is the National Assembly text "as modified up to
  28 February 2012". Amendments after that date (including the 26th, 2024, and
  the 27th, Act No. XXXII of 2025, in force 13 Nov 2025, which created the
  Federal Constitutional Court) are NOT in it. It must not be called current.

This module only LABELS and GATES: it never supplies the missing text, and it
never makes the 2012 text current. Labels are provisional (developer-verified
sources, not lawyer-validated); a lawyer must review the interpretation before
any court-ready claim.
"""
from __future__ import annotations

import re

CPC_SOURCE_JURISDICTION = "punjab"
CPC_SOURCE = "Punjab Code consolidation (Punjab amendments incl. Act XIV of 2018)"
CONSTITUTION_AS_OF = "28 February 2012"

# ── the Constitution (Twenty-seventh Amendment) Act, 2025 ───────────────────
#
# Read from the Gazette itself: Gazette of Pakistan, Extraordinary, Part I,
# 13 Nov 2025, Act No. XXXII of 2025, https://www.na.gov.pk/uploads/documents/
# 691ec19a6a212_270.pdf (sha256 303d09fa...; 23 PDF pages; scanned, OCR read).
# One row per amending section: (section, Article, what it does, PDF page(s)).
#   article_omitted      the WHOLE Article is omitted ("Article N shall be omitted")
#   article_substituted  the whole Article is replaced by new text (it still exists)
#   article_inserted     a new Article
#   amended              words / clauses changed inside a surviving Article
#   clause_omitted       a clause / proviso / paragraph omitted -- the Article survives
# Full evidence table: evals/legal_sources/BATCH4_CONSTITUTION_GATE.md §1.
GAZETTE_27TH: tuple[tuple[int, str, str, str], ...] = (
    (2, "6", "amended", "2"), (3, "10", "amended", "2"), (4, "17", "amended", "2"), (5, "59", "amended", "2"),
    (6, "63A", "amended", "2"), (7, "68", "amended", "2"), (8, "78", "amended", "2"), (9, "81", "amended", "2-3"),
    (10, "93", "amended", "3"), (11, "100", "amended", "3"), (12, "105", "amended", "3"),
    (13, "114", "amended", "3"), (14, "130", "clause_omitted", "3"), (15, "146", "amended", "3"),
    (16, "152", "amended", "3"), (17, "159", "amended", "3"), (18, "165A", "amended", "3-4"),
    (19, "175", "amended", "4"), (20, "175A", "clause_omitted", "4-7"),
    (21, "175B", "article_inserted", "7"), (21, "175C", "article_inserted", "8"),
    (21, "175D", "article_inserted", "8"), (21, "175E", "article_inserted", "9"),
    (21, "175F", "article_inserted", "9"), (21, "175G", "article_inserted", "10"),
    (21, "175H", "article_inserted", "10"), (21, "175I", "article_inserted", "10"),
    (21, "175J", "article_inserted", "10"), (21, "175K", "article_inserted", "11"),
    (21, "175L", "article_inserted", "11"),
    (22, "176", "amended", "11-12"), (23, "177", "amended", "12"), (24, "178", "amended", "12"),
    (25, "179", "amended", "12"), (26, "180", "amended", "12"), (27, "182", "amended", "12"),
    (28, "183", "clause_omitted", "12"), (29, "184", "article_omitted", "12"),
    (30, "185", "article_substituted", "12-13"), (31, "186", "article_omitted", "13"),
    (32, "186A", "article_omitted", "13"), (33, "187", "amended", "14"),
    (34, "189", "article_substituted", "14"), (35, "190", "amended", "14"),
    (36, "191", "article_substituted", "14-15"), (37, "191A", "article_omitted", "15"),
    (38, "192", "amended", "15"), (39, "193", "clause_omitted", "15"), (40, "199", "amended", "15"),
    (41, "200", "article_substituted", "15-16"), (42, "202A", "amended", "16"), (43, "204", "amended", "16"),
    (44, "205", "amended", "16"), (45, "206", "amended", "16"), (46, "207", "clause_omitted", "16-17"),
    (47, "208", "amended", "17"), (48, "209", "amended", "17-19"), (49, "210", "amended", "19-20"),
    (50, "239", "amended", "20"), (51, "243", "amended", "20-21"), (52, "248", "amended", "21"),
    (53, "260", "amended", "21-22"),
)
# What a clause-level omission removed (the Article itself survives).
CLAUSE_OMITTED = {"130": "a proviso", "175A": "provisos", "183": "clause (3)", "193": "clause (3)",
                  "207": "paragraph (c)"}
_BY_ARTICLE = {art: (sec, kind, page) for sec, art, kind, page in GAZETTE_27TH}
OMITTED_ARTICLES = frozenset(a for a, (_, k, _) in _BY_ARTICLE.items() if k == "article_omitted")
INSERTED_ARTICLES = frozenset(a for a, (_, k, _) in _BY_ARTICLE.items() if k == "article_inserted")
CHANGED_ARTICLES = frozenset(_BY_ARTICLE)
# Backward-compatible name used by batch 3.
OMITTED_AFTER_TEXT_ON_FILE = OMITTED_ARTICLES

_PROVINCE_NAMES = {"sindh": "Sindh", "kpk": "Khyber Pakhtunkhwa", "kp": "Khyber Pakhtunkhwa",
                   "khyber pakhtunkhwa": "Khyber Pakhtunkhwa", "balochistan": "Balochistan",
                   "federal": "Islamabad / federal", "ict": "Islamabad", "islamabad": "Islamabad"}
# Provinces KNOWN not to be Punjab (an unknown province is not one of them).
KNOWN_NON_PUNJAB = frozenset(_PROVINCE_NAMES)

_CPC = re.compile(r"(?i)\bCPC\b|\bC\.P\.C\b|Code\s+of\s+Civil\s+Procedure|Civil\s+Procedure\s+Code")
_CONSTITUTION = re.compile(r"(?i)^\s*Article\s|\bConstitution\b")
_URDU_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")   # 1:1, offsets kept

# "Article 186", "Art. 186", "ARTICLE 186-A", "Articles 184 and 186", "(Article 186)",
# Roman Urdu "aain ka article 186", Urdu "آرٹیکل 186" / "آرٹیکل ۱۸۶".
_ART_WORD = re.compile(r"(?i)\b(?:Articles?|Arts?\.)\s*|(?:آرٹیکلز?|ارٹیکل)\s*")
_ART_NUM = re.compile(r"(\d{1,3})(?:\s*-\s*([A-Za-z])|([A-Za-z]))?(?![A-Za-z\d])")
_ART_SEP = re.compile(r"(?i)\s*(?:,|&|/|\band\b|\bor\b|اور)\s*(?:(?:Articles?|Arts?\.)\s*|(?:آرٹیکل)\s*)?")
_CONSTITUTION_CONTEXT = re.compile(r"(?i)Constitution|constitutional|\baa?in\b|\bayeen\b|\bdastoor\b|آئین|دستور")
_OTHER_ARTICLE_INSTRUMENT = re.compile(r"(?i)Limitation|Qanun|Shahadat|\bQSO\b|Schedule")
# Framing that makes a mention HISTORY, not a statement of current law.
_HISTORICAL = re.compile(
    r"(?i)\b(?:before|prior\s+to|until)\s+(?:its\s+)?(?:omission|the\s+(?:27th|twenty[-\s]seventh)|"
    r"(?:13\s+)?november\s+2025|2025)|\b(?:formerly|previously|historically)\b|"
    r"\b(?:was|were|has\s+been|have\s+been|stands?)\s+omitted\b|\bno\s+longer\b|\bthe\s+(?:former|then)\b|"
    r"\b(?:pehle|pehlay)\b|سابقہ|پہلے|حذف")
# Reliance on the Article as law, immediately around the citation.
_RELY_BEFORE = re.compile(
    r"(?i)(?:\bunder|\bin\s+exercise\s+of|\bpursuant\s+to|\bin\s+terms\s+of|\bby\s+virtue\s+of|\binvok\w*|"
    r"\bconferred\s+by|\bvested\s+by|\bas\s+provided\s+(?:in|by))\s+(?:the\s+)?(?:said\s+)?"
    r"(?:(?:powers?|jurisdiction)\s+(?:under|of|conferred\s+by)\s+)?(?:the\s+)?$")
_RELY_AFTER = re.compile(r"(?i)^\s*(?:of\s+the\s+Constitution\s*)?(?:کے\s+تحت|ke\s+t[ae]?h[ae]?t\b)")

# A question or instruction that needs constitutional law made after 2012.
_POST_2012 = re.compile(
    r"(?i)Federal\s+Constitutional\s+Court|\bFCCP\b|constitutional\s+benche?s?|"
    r"\b(?:26th|27th|twenty[-\s]?sixth|twenty[-\s]?seventh)\s+(?:constitutional\s+)?amendment|"
    r"\bArticle\s+184\s*\(\s*3\s*\)")


def province_label(province: str | None) -> str:
    p = (province or "").strip().lower()
    return _PROVINCE_NAMES.get(p, "this jurisdiction")


def is_cpc(label: str) -> bool:
    return bool(_CPC.search(label or ""))


def is_constitution(label: str) -> bool:
    return bool(_CONSTITUTION.search(label or "")) and not is_cpc(label)


def article_refs(text: str) -> list[tuple[str, int, int]]:
    """[(Article, start, end)] for every Article number cited, lists included.
    `start` is where the citing WORD begins ("Article", "Art.", "آرٹیکل") --
    for "Articles 184 and 186" both numbers share it -- so what precedes the
    citation ("under ...") is read from there. Pure string scan; Urdu digits
    read as digits (1:1, offsets unchanged)."""
    t = (text or "").translate(_URDU_DIGITS)
    out = []
    for w in _ART_WORD.finditer(t):
        pos = w.end()
        while True:
            m = _ART_NUM.match(t, pos)
            if not m:
                break
            out.append((f"{m.group(1)}{(m.group(2) or m.group(3) or '').upper()}", w.start(), m.end()))
            sep = _ART_SEP.match(t, m.end())
            if not sep or not _ART_NUM.match(t, sep.end()):
                break
            pos = sep.end()
    return out


def article_of(label: str) -> str | None:
    refs = article_refs(label)
    return refs[0][0] if refs else None


def _constitutional(unit: str) -> bool:
    if _CONSTITUTION_CONTEXT.search(unit):
        return True
    return bool(article_refs(unit)) and not _OTHER_ARTICLE_INSTRUMENT.search(unit)


def cpc_note(province: str | None) -> str | None:
    """Why a CPC citation cannot be marked checked here; None in Punjab."""
    if (province or "").strip().lower() == CPC_SOURCE_JURISDICTION:
        return None
    return (f"the CPC text on file is the Punjab version; the {province_label(province)} text "
            "has not been verified")


def constitution_note(label: str) -> str:
    art = article_of(label)
    hit = _BY_ARTICLE.get(art or "")
    if hit:
        sec, kind, page = hit
        where = f"Constitution (Twenty-seventh Amendment) Act 2025, s.{sec} (Gazette p.{page})"
        if kind == "article_omitted":
            return f"Article {art} was omitted by the {where}; the text on file predates it"
        if kind == "article_substituted":
            return f"Article {art} was replaced by the {where}; the current text is not on file"
        if kind == "article_inserted":
            return f"Article {art} was inserted by the {where}; it is not in the text on file"
        if kind == "clause_omitted":
            return (f"Article {art} was amended ({CLAUSE_OMITTED[art]} omitted) by the {where}; "
                    "the current text is not on file")
        return f"Article {art} was amended by the {where}; the current text is not on file"
    return f"the Constitution text on file is as modified up to {CONSTITUTION_AS_OF}; later amendments are not checked"


def needs_post_2012_constitution(text: str) -> bool:
    if _POST_2012.search(text or ""):
        return True
    return any(a in OMITTED_ARTICLES or a in INSERTED_ARTICLES for a, _, _ in article_refs(text or ""))


def gate_supported(supported: list[str], province: str | None) -> tuple[list[str], list[str]]:
    """(still supported, moved to not-checked with the reason). Pure.

    A CPC citation outside Punjab, and any Constitution citation, is never
    "supported": the text it was checked against is not the text that governs.
    """
    keep, moved = [], []
    for s in supported:
        if is_cpc(s):
            note = cpc_note(province)
            if note:
                moved.append(f"{s} ({note})")
                continue
        elif is_constitution(s):
            moved.append(f"{s} ({constitution_note(s)})")
            continue
        keep.append(s)
    return keep, moved


def annotate_not_checked(not_checked: list[str], province: str | None) -> list[str]:
    """Every not-checked CPC (outside Punjab) and Constitution entry says WHY the
    text on file cannot settle it, not just "(not checked)"."""
    def add(s: str, note: str) -> str:
        if s.endswith(" (not checked)"):
            return f"{s[:-len(' (not checked)')]} (not checked: {note})"
        return f"{s} ({note})"
    out = []
    for s in not_checked:
        if is_cpc(s) and cpc_note(province) and "Punjab version" not in s:
            s = add(s, cpc_note(province))
        elif is_constitution(s) and CONSTITUTION_AS_OF not in s and "Twenty-seventh" not in s:
            s = add(s, constitution_note(s))
        out.append(s)
    return out


def omitted_article_check(units, norm: str) -> tuple[list[dict], list[tuple]]:
    """(withheld units, [(unit span, not-checked note)]) for Articles the 27th Amendment OMITTED
    WHOLE (184, 186, 186A, 191A -- never a clause-level omission).

    Fail-closed: a unit relying on the Article ("under Article 186") is withheld
    even if it also says "omitted"; a unit framed as history ("Before its
    omission, Article 186 provided ...") stays, listed as a historical
    reference, never supported; any other mention is withheld.

    Citations are found in the WHOLE text and mapped back to units: the
    sentence splitter ends a unit at the full stop of "Art.", leaving
    "186 of the Constitution" in the next unit without its "Art.".
    """
    scan = (norm or "").translate(_URDU_DIGITS)
    spans = [tuple(u) for u in units]

    def unit_at(pos):
        return next((u for u in spans if u[0] <= pos < u[1]), None)

    groups: dict[tuple, list] = {}
    for art, s, e in article_refs(norm):
        if art not in OMITTED_ARTICLES:
            continue
        end_unit, start_unit = unit_at(e - 1), unit_at(s)
        if end_unit is None:
            continue
        span = (min(end_unit[0], (start_unit or end_unit)[0]), end_unit[1])
        groups.setdefault(span, []).append((art, s, e))
    withheld, notes = [], []
    for (a, b), hits in sorted(groups.items()):
        ctx = scan[a:b]
        if not _constitutional(ctx):
            continue
        relied = any(_RELY_BEFORE.search(scan[max(0, s - 60):s]) or _RELY_AFTER.match(scan[e:e + 40])
                     for _, s, e in hits)
        arts = sorted({art for art, _, _ in hits})
        if not relied and _HISTORICAL.search(ctx):
            for art in arts:
                sec, _, page = _BY_ARTICLE[art]
                note = (f"Article {art} Constitution (historical reference: omitted by the Constitution "
                        f"(Twenty-seventh Amendment) Act 2025, s.{sec}, Gazette p.{page}; not checked)")
                if ((a, b), note) not in notes:
                    notes.append(((a, b), note))
            continue
        reasons = []
        for art in arts:
            sec, _, page = _BY_ARTICLE[art]
            reasons.append(f"Article {art} of the Constitution was omitted by the Constitution (Twenty-seventh "
                           f"Amendment) Act, 2025 (s.{sec}, Gazette p.{page}); it is not current law and the "
                           "current text is not on file.")
        withheld.append({"span": (a, b), "text": None, "reasons": reasons})
    return withheld, notes


def omitted_article_units(units, norm: str) -> list[dict]:
    """Withheld units only (batch-3 name)."""
    return omitted_article_check(units, norm)[0]


def drafting_rider(law_context: str, instruction: str, province: str | None) -> str:
    """Source notes for the drafting prompt -- only when the context or the
    request involves these two texts."""
    notes = []
    if _CPC.search(law_context or "") and cpc_note(province):
        notes.append(f"Code of Civil Procedure text above is the PUNJAB version ({CPC_SOURCE}); the "
                     f"{province_label(province)} text is not available. Do not quote its wording as the law of "
                     "this jurisdiction -- write [CPC provision as applicable in this jurisdiction] where the "
                     "draft needs it.")
    if re.search(r"(?i)Constitution", law_context or "") or needs_post_2012_constitution(instruction):
        notes.append(f"Constitution text above is as modified up to {CONSTITUTION_AS_OF}; the 26th and 27th "
                     "Amendments (including the Federal Constitutional Court) are NOT in it. Articles 184, 186, "
                     "186A and 191A were omitted in 2025 -- never rely on them. Do not state current "
                     "constitutional provisions from it -- write [current constitutional provision] where the "
                     "draft needs one.")
    return ("\n\nSOURCE NOTES:\n- " + "\n- ".join(notes)) if notes else ""


def research_rider(question: str, is_urdu: bool = False) -> str:
    """Lawyer research: a question that needs post-2012 constitutional law, or
    asks about an Article the 27th Amendment omitted (answered as HISTORY)."""
    if not needs_post_2012_constitution(question):
        return ""
    omitted = sorted({a for a, _, _ in article_refs(question) if a in OMITTED_ARTICLES})
    if is_urdu:
        note = ("\n\nآئین کا جو متن دستیاب ہے وہ 28 فروری 2012 تک کا ہے؛ 26ویں اور 27ویں ترامیم (بشمول وفاقی آئینی "
                "عدالت) اس میں شامل نہیں۔ موجودہ آئینی حکم اس متن سے بیان نہ کریں؛ واضح کہیں کہ تازہ متن تصدیق شدہ نہیں۔")
        if omitted:
            note += (f" آرٹیکل {', '.join(omitted)} کو 27ویں ترمیم (2025) نے حذف کر دیا ہے: اس کا ذکر صرف تاریخ کے طور پر "
                     "کریں اور واضح لکھیں کہ یہ اب نافذ نہیں۔")
        return note
    note = (f"\n\nCONSTITUTION SOURCE NOTE: the Constitution text available is as modified up to "
            f"{CONSTITUTION_AS_OF}. The 26th and 27th Amendments (including the Federal Constitutional Court, "
            "Act No. XXXII of 2025) are NOT in it. Do not state current constitutional provisions from it; "
            "say plainly that the current text has not been verified here.")
    if omitted:
        refs = ", ".join(f"Article {a} (s.{_BY_ARTICLE[a][0]})" for a in omitted)
        note += (f" {refs} WAS OMITTED by the Constitution (Twenty-seventh Amendment) Act, 2025. Describe it "
                 "only as history -- what it said before its omission -- and state that it is no longer in force.")
    return note


def downgrade_wrong_province_cpc(claims: list[dict], evidence: list[dict] | None,
                                 province: str | None) -> list[dict]:
    """Chat and research claims: for a turn in a province KNOWN not to be Punjab,
    a claim whose statute sources are all the (Punjab) CPC is not "supported"
    or "partial" -- "unassessed", with why. Downgrade-only; an unknown province
    is left as it was."""
    if (province or "").strip().lower() not in KNOWN_NON_PUNJAB:
        return claims
    by_id = {e.get("id"): e for e in evidence or []}
    for claim in claims or []:
        if claim.get("support") not in ("supported", "partial"):
            continue
        sources = [by_id[i] for i in claim.get("source_ids") or [] if i in by_id]
        statutes = [s for s in sources if s.get("kind", "statute") == "statute"]
        if statutes and all(is_cpc(s.get("statute", "")) for s in statutes) and len(statutes) == len(sources):
            claim["support"] = "unassessed"
            claim["support_reason"] = cpc_note(province)
    return claims


# ── CPC: jurisdiction scope, clause-level edits (drafter), visible notice ──
#
# Batch 5 (2026-10-16). The CPC on file is Punjab's. A province is CONFIRMED
# Punjab only when the user / the case record says so -- a province the model
# INFERRED from the question text is not confirmation, and an unknown province
# is unknown, never Punjab.

SCOPE_PUNJAB, SCOPE_OTHER, SCOPE_UNKNOWN = "punjab", "other", "unknown"


def cpc_scope(province: str | None, basis: str | None = None, inferred: bool = False) -> str:
    p = (province or "").strip().lower()
    if inferred or basis == "inferred_from_query":
        return SCOPE_UNKNOWN
    if p == CPC_SOURCE_JURISDICTION:
        return SCOPE_PUNJAB
    if p in KNOWN_NON_PUNJAB:
        return SCOPE_OTHER
    return SCOPE_UNKNOWN


def _where(province: str | None, scope: str) -> str:
    return province_label(province) if scope == SCOPE_OTHER else "your province"


def cpc_placeholder(province: str | None, scope: str | None = None) -> str:
    scope = scope or cpc_scope(province)
    return f"[Verify the applicable CPC provision for {_where(province, scope)}]"


_N = r"\d{1,3}(?:\s*-?\s*(?-i:[A-Z])(?![A-Za-z]))?(?:\s*\(\s*[0-9A-Za-z]{1,3}\s*\))*"
_SEC = rf"(?:Sections?|Secs?\.|Ss?\.|u/s\.?)\s*{_N}(?:\s*(?:,|and|&|/)\s*{_N})*"
_ORD = (rf"(?:Order|O\.|\bO(?=\s+(?:[IVXLC]{{1,7}}|\d{{1,2}})\s*,?\s*R))\s*(?:[IVXLC]{{1,7}}|\d{{1,2}})\s*,?\s*"
        rf"(?:Rules?|R\.|r\.|\bR(?=\s*\d))\s*{_N}(?:\s*(?:,|and|&)\s*{_N})*")
_ORD_UR = (r"(?:آرڈر|حکم)\s*(?:[IVXLC]{1,7}|[\d۰-۹]{1,2})\s*[،,]?\s*(?:رول|قاعدہ)\s*[\d۰-۹]{1,3}"
           r"(?:\s*(?:ضابطہ\s*دیوانی|سی\s*پی\s*سی|CPC))?")
_CODE = (r"(?:(?:of|under)\s+)?(?:the\s+)?(?:Code\s+of\s+Civil\s+Procedure(?:\s*,?\s*(?:\(\s*V\s+of\s+1908\s*\)|1908))*"
         r"|Civil\s+Procedure\s+Code|C\.\s?P\.\s?C\.?|CPC)(?:\s*,?\s*1908)?")
_LINK = r"\s*(?:,|\band\b|&|\bread\s+with\b|\br/w\b)\s*"
_DAFA = r"(?:dafa(?:'?a)?|dafah)"
_CPC_CITATION = re.compile(
    rf"(?i)(?:(?:{_SEC}|{_ORD})(?:{_LINK}(?:{_SEC}|{_ORD}))*\s*,?\s*{_CODE}"     # ... Section 9 of the CPC
    rf"|{_CODE}\s*,?\s*(?:(?:کی|کے|کا|ki|ke|ka)\s+)?(?:{_SEC}|{_ORD})"            # CPC Section 9 / "CPC کی Sec. 9"
    rf"|{_ORD}(?:{_LINK}(?:{_SEC}|{_ORD}))*"                                       # Order VII Rule 11 (the CPC's)
    rf"|{_ORD_UR}"                                                                 # آرڈر 7 رول 11
    r"|(?:ضابطہ\s*دیوانی|سی\s*پی\s*سی)\s*(?:کی|کے|کا)?\s*(?:دفعہ|دفعات)\s*[\d۰-۹]{1,3}"
    r"|(?:دفعہ|دفعات)\s*[\d۰-۹]{1,3}\s*[،,]?\s*(?:ضابطہ\s*دیوانی|سی\s*پی\s*سی)"
    rf"|\bCPC\s*(?:ki|ke|ka)?\s*{_DAFA}\s*\d{{1,3}}"
    rf"|\b{_DAFA}\s*\d{{1,3}}\s*(?:CPC|C\.P\.C\.?))")
_NOT_CPC_ORDER = re.compile(r"(?i)Supreme\s+Court\s+Rules|High\s+Court\s+Rules|Rules\s+of\s+(?:the\s+)?(?:Supreme|High)")
_PREP = re.compile(
    r"(?i)(?:\bunder|\bin\s+terms\s+of|\bby\s+virtue\s+of|\bpursuant\s+to|\bas\s+per|\bvide|\bread\s+with|"
    r"\bin\s+exercise\s+of(?:\s+(?:the\s+|its\s+)?(?:inherent\s+)?(?:powers?|jurisdiction)\s+(?:under|conferred\s+by))?|"
    r"\bas\s+provided\s+(?:in|by|under))\s+(?:the\s+)?(?:provisions?\s+of\s+(?:the\s+)?)?$")
_PREP_AFTER = re.compile(r"(?i)^\s*(?:کے\s+تحت|ke\s+t[ae]?h[ae]?t\b)")
# "... Section 42 of the Specific Relief Act and Section 9 CPC": a CPC citation
# that only ENDS a list of citations is dropped together with its "and".
_LIST_JOIN = re.compile(r"(?i)(?:\d[\w)]*|\bAct|\bOrdinance|\bOrder|\bRules?|\bCode|\bPPC|\bCrPC)(?:,?\s*\d{4})?"
                        r"(?P<join>\s*(?:,|\band|&)\s*)$")


def cpc_citations(text: str) -> list[tuple[int, int]]:
    """Spans of CPC citations (Section .. of the CPC, Order .. Rule .., Urdu/Roman forms).
    An Order/Rule of the Supreme Court or High Court Rules is not the CPC's."""
    t = text or ""
    hits = [(m.start(), m.end()) for m in _CPC_CITATION.finditer(t)]
    if _NOT_CPC_ORDER.search(t):
        hits = [(s, e) for s, e in hits if _CPC.search(t[s:e])]
    return hits


def _norm_ws(s: str) -> str:
    return " ".join((s or "").split()).lower()


def cpc_clause_edits(units, norm: str, province: str | None, own_text: str = "",
                     skip: set | None = None) -> dict:
    """The drafter's CPC policy for one draft, outside a confirmed-Punjab matter.

    Per CPC citation in an AI-written unit (units in `skip` -- already withheld
    for another reason -- and units copied from the lawyer's own text are left
    alone):
      * after "under / in terms of / pursuant to / read with ..." or inside
        brackets: the MAIN proposal drops just that authority clause;
      * anywhere else (the citation is the subject or object of the sentence):
        the MAIN proposal puts the placeholder in its place;
      * the ALTERNATIVE puts the placeholder in place of every such citation;
      * a unit framed as history with no reliance is kept, listed not checked.
    Nothing else in the sentence is touched.
    Returns {"main": [edits], "alt": [edits], "withheld": [...], "notes": [...]}
    with each edit {"span": (a, b), "replacement": str} (offsets into `norm`).
    """
    scope = cpc_scope(province)
    out = {"main": [], "alt": [], "withheld": [], "notes": []}
    if scope == SCOPE_PUNJAB:
        return out
    where = _where(province, scope)
    ph = cpc_placeholder(province, scope)
    own = _norm_ws(own_text)
    skip = skip or set()
    for a, b in units:
        if (a, b) in skip:
            continue
        unit = norm[a:b]
        cites = cpc_citations(unit)
        if not cites:
            continue
        if own and len(unit.strip()) >= 12 and _norm_ws(unit) in own:
            out["notes"].append(f"CPC citation in your own text, not changed: \"{unit.strip()[:80]}\" "
                                f"(the CPC text on file is the Punjab version; not verified for {where})")
            continue
        relied = any(_PREP.search(unit[max(0, s - 80):s]) or _PREP_AFTER.match(unit[e:e + 30]) for s, e in cites)
        if not relied and _HISTORICAL.search(unit):
            out["notes"].append(f"CPC reference in a historical sentence, kept: \"{unit.strip()[:80]}\" "
                                "(not checked; the CPC text on file is the Punjab version)")
            continue
        for s, e in cites:
            label = " ".join(unit[s:e].split())
            window = unit[max(0, s - 80):s]
            pre = _PREP.search(window)
            after = _PREP_AFTER.match(unit[e:e + 30])
            before_txt = unit[:s].rstrip()
            after_txt = unit[e:]
            if before_txt.endswith("(") and after_txt.lstrip().startswith(")"):
                ms = a + len(before_txt) - 1
                me = a + e + (len(after_txt) - len(after_txt.lstrip())) + 1
                main = {"span": (ms, me), "replacement": ""}
            elif pre:
                main = {"span": (a + s - (len(window) - pre.start()), a + e), "replacement": ""}
            elif after:
                main = {"span": (a + s, a + e + after.end()), "replacement": ""}
            elif _LIST_JOIN.search(window):
                j = _LIST_JOIN.search(window)
                main = {"span": (a + s - (len(window) - j.start("join")), a + e), "replacement": ""}
            else:
                main = {"span": (a + s, a + e), "replacement": ph}
            out["main"].append(main)
            out["alt"].append({"span": (a + s, a + e), "replacement": ph})
            out["withheld"].append({"span": main["span"], "text": label, "cpc_clause": True, "reasons": [
                f"{label}: the CPC text on file is the Punjab version and this matter is not confirmed as "
                f"Punjab ({where}), so the citation was taken out of this proposal. A version with "
                f"{ph} is offered separately."]})
    return out


def apply_edits(text: str, removals, edits: list[dict]) -> str:
    """`text` with whole spans removed and sub-spans replaced, tidied ONLY at the
    edited boundaries (no space left before punctuation, no double space)."""
    ops = [((a, b), "") for a, b in removals] + [(tuple(e["span"]), e["replacement"]) for e in edits]
    ops.sort(key=lambda o: (o[0][0], -o[0][1]))
    out, last = [], 0
    for (a, b), rep in ops:
        if a < last:
            continue
        left = text[last:a]
        nxt = text[b:b + 1]
        if rep == "" and nxt and nxt in " ,.;:)\n" and left.endswith(" "):
            left = left.rstrip(" ")
        out.append(left + rep)
        last = b
    out.append(text[last:])
    joined = re.sub(r"[ \t]+\n", "\n", "".join(out))
    return re.sub(r"\n{3,}", "\n\n", joined).strip()


# ── chat / research: claims, citations and the visible notice ───────────────

NOTICE_MARK_EN = "Note on the Code of Civil Procedure"
NOTICE_MARK_UR = "ضابطہ دیوانی کے بارے میں نوٹ"


def cpc_notice(province: str | None, scope: str, urdu: bool = False) -> str:
    if urdu:
        if scope == SCOPE_OTHER:
            return (f"{NOTICE_MARK_UR}: یہاں دستیاب ضابطہ دیوانی (CPC) کا متن پنجاب کا ہے۔ اوپر دی گئی CPC دفعات "
                    f"{province_label(province)} کے لیے تصدیق شدہ نہیں؛ ان پر انحصار سے پہلے وہاں کا متن دیکھیں۔")
        return (f"{NOTICE_MARK_UR}: یہاں دستیاب ضابطہ دیوانی (CPC) کا متن پنجاب کا ہے اور آپ کا صوبہ معلوم نہیں۔ "
                "اوپر دی گئی CPC دفعات آپ کے صوبے کے لیے تصدیق شدہ نہیں — اپنا صوبہ بتائیں، یا انحصار سے پہلے وہاں کا متن دیکھیں۔")
    if scope == SCOPE_OTHER:
        return (f"{NOTICE_MARK_EN}: the CPC text this answer was checked against is the Punjab version. The CPC "
                f"provisions above are not verified for {province_label(province)}; check them against the "
                f"{province_label(province)} text before relying on them.")
    return (f"{NOTICE_MARK_EN}: the CPC text this answer was checked against is the Punjab version, and your "
            "province is not known. The CPC provisions above are not verified for your province: tell me your "
            "province, or check the CPC as it applies there before relying on them.")


def cpc_needed_notice(province: str | None, scope: str, urdu: bool = False) -> str:
    where = province_label(province) if scope == SCOPE_OTHER else "your province"
    if urdu:
        return (f"{NOTICE_MARK_UR}: یہ سوال دیوانی طریقۂ کار سے متعلق ہے، اور یہاں ضابطہ دیوانی کا صرف پنجاب کا متن موجود ہے جو "
                f"{where if scope == SCOPE_OTHER else 'آپ کے صوبے'} کے لیے تصدیق شدہ نہیں۔ اوپر کا جواب ضابطہ دیوانی پر مبنی نہیں؛ "
                "لاگو طریقۂ کار کسی وکیل سے معلوم کریں۔")
    ask = " Tell me your province, or" if scope != SCOPE_OTHER else ""
    return (f"{NOTICE_MARK_EN}: this question turns on civil procedure, and the only Code of Civil Procedure text "
            f"held here is the Punjab version, which is not verified for {where}. The answer above does not rely "
            f"on the CPC.{ask} check the procedure that applies with a lawyer.")


def apply_cpc_jurisdiction(claims: list[dict], citations: list[dict], answer: str,
                           province: str | None, basis: str | None = None, inferred: bool = False,
                           urdu: bool = False, question: str = "") -> tuple[list[dict], list[dict], str, dict]:
    """Chat and research, on the final answer (fresh or cached). Outside a
    confirmed-Punjab turn: a claim resting only on the CPC is not
    supported/partial but "unassessed" with why; a CPC citation's currency is
    "unknown" with why; and when the answer cites the CPC, one plain notice is
    appended (once). Confirmed Punjab: unchanged. Downgrade-only."""
    scope = cpc_scope(province, basis, inferred)
    info = {"scope": scope, "downgraded": 0, "notice": False}
    if scope == SCOPE_PUNJAB:
        return claims, citations, answer, info
    reason = ("the CPC text on file is the Punjab version; not verified for "
              + (province_label(province) if scope == SCOPE_OTHER else "your province (not known)"))
    for claim in claims or []:
        srcs = [s.get("statute", "") for s in claim.get("sources") or []]
        cpc_srcs = [s for s in srcs if is_cpc(s)]
        named = bool(cpc_citations(str(claim.get("text") or "")))
        if claim.get("support") in ("supported", "partial") and (cpc_srcs or named):
            # Per source: a claim resting on the CPC -- alone OR beside another
            # statute -- is not verified here. The other statute's own claims
            # are untouched; this one cannot be split safely, so it alone goes.
            claim["support"] = "unassessed"
            claim["support_reason"] = reason + ("" if srcs and len(cpc_srcs) == len(srcs)
                                                else "; this statement also rests on it")
            info["downgraded"] += 1
    cited = False
    for c in citations or []:
        if c.get("type") != "judgment" and is_cpc(c.get("statute", "")):
            c["currency"] = "unknown"
            c["jurisdiction_note"] = reason
            # Only a CPC provision the answer CITES calls for the notice; one
            # merely consulted ("retrieved") does not.
            cited = cited or c.get("status") != "retrieved"
    cited = cited or info["downgraded"] > 0 or bool(cpc_citations(answer))
    # Batch 9: the QUESTION needs the CPC, but no applicable CPC text is held --
    # an answer built from other law must still say so (relabelled index:
    # the Punjab CPC is no longer retrieved here at all).
    needed = not cited and question and cpc_requirement(question)["required"] \
        and not cpc_text_available(province, basis, inferred)
    if (cited or needed) and NOTICE_MARK_EN not in answer and NOTICE_MARK_UR not in answer:
        answer = f"{answer.rstrip()}\n\n{cpc_notice(province, scope, urdu) if cited else cpc_needed_notice(province, scope, urdu)}"
        info["notice"] = True
    return claims, citations, answer, info


# ── Client Legal Intake (batch 6) ──────────────────────────────────────────
#
# The stored intake analysis (`ai_structured_case`) is the client's screen, the
# print / text export, and -- through `ai_summary` -- the lawyer's case summary
# and the drafter's case context. Outside a confirmed-Punjab matter the Punjab
# CPC is not shown as applicable law there: applied once, deterministically, on
# the FINAL analysis (after the output contract), and again to a COPY whenever
# a stored analysis is read, so analyses saved before this rule are corrected on
# screen without rewriting any record. Additive fields only:
#   jurisdiction_notice   {"scope", "province", "en", "ur"}
#   cpc_jurisdiction      {"version", "scope", ...counts}
#   withheld_citations[]  CPC entries gain "withheld_reason": "cpc_jurisdiction_unverified"
# Existing fields keep their meaning; a new grounding_status value
# "cpc_jurisdiction_unverified" is used only when NO law is left.

# v2 (batch 7): the risk rating is withheld too. Bumped so a stored v1
# analysis is re-viewed (read-time) with the risk rule applied.
INTAKE_CPC_VERSION = "intake-cpc-jurisdiction-v2"
RISK_NOT_ASSESSED = "not_assessed_cpc_jurisdiction"
LAWYER_REVIEW_STEP_UR = ("کوئی بھی قانونی قدم اٹھانے سے پہلے کسی مستند پاکستانی وکیل سے پوچھیں کہ کون سی قانونی دفعہ لاگو ہوتی ہے؛ "
                         "ایک تجویز کردہ قانونی قدم روک دیا گیا کیونکہ اس کی تصدیق نہیں ہو سکی۔")
INTAKE_CPC_STATUS = "cpc_jurisdiction_unverified"


def intake_placeholder(province: str | None, scope: str) -> str:
    return f"[the relevant CPC provision, not verified for {_where(province, scope)}]"


def intake_notice(province: str | None, scope: str) -> dict:
    where = _where(province, scope)
    if scope == SCOPE_OTHER:
        en = (f"{NOTICE_MARK_EN}: our law library holds only the Punjab version of the CPC, so CPC provisions are "
              f"not shown here as the law that applies in {where}. A lawyer practising in {where} should confirm "
              "the civil procedure that applies.")
        ur = (f"{NOTICE_MARK_UR}: ہماری قانونی لائبریری میں ضابطہ دیوانی (CPC) کا صرف پنجاب کا متن ہے، اس لیے یہاں CPC کی "
              f"دفعات {province_label(province)} پر لاگو قانون کے طور پر نہیں دکھائی گئیں۔ وہاں کے کسی وکیل سے لاگو طریقۂ کار کی تصدیق کریں۔")
    else:
        en = (f"{NOTICE_MARK_EN}: our law library holds only the Punjab version of the CPC, and the province for "
              "this matter is not recorded, so CPC provisions are not shown here as applicable law. Add your "
              "province to the case, or ask a lawyer which civil procedure applies.")
        ur = (f"{NOTICE_MARK_UR}: ہماری قانونی لائبریری میں ضابطہ دیوانی (CPC) کا صرف پنجاب کا متن ہے اور اس معاملے کا صوبہ "
              "درج نہیں، اس لیے CPC کی دفعات لاگو قانون کے طور پر نہیں دکھائی گئیں۔ اپنا صوبہ درج کریں یا کسی وکیل سے پوچھیں۔")
    return {"scope": scope, "province": (province or "").lower() or None, "en": en, "ur": ur}


def _edit_text(text: str, province: str | None, scope: str) -> tuple[str, int]:
    """CPC citation clauses in one piece of client-facing text: dropped with
    their "under ..." / brackets, or replaced by the intake placeholder."""
    if not text or not cpc_citations(text):
        return text, 0
    edits = cpc_clause_edits([(0, len(text))], text, province)
    if not edits["main"]:
        return text, 0                        # historical / own-text: left as is
    ph = intake_placeholder(province, scope)
    main = [{**e, "replacement": ph if e["replacement"] else ""} for e in edits["main"]]
    return apply_edits(text, [], main), len(main)


def _ids(claim: dict) -> set[str]:
    ids = claim.get("source_ids") or []
    if isinstance(ids, str):
        ids = re.findall(r"\d+", ids)
    return {str(i) for i in ids}


def apply_intake_cpc(analysis: dict, province: str | None, basis: str | None = "user_selected",
                     inferred: bool = False) -> dict:
    """Outside a confirmed-Punjab matter, the Punjab CPC is not presented as the
    law that applies. In place; idempotent; returns `analysis`.

    * CPC citations leave `law_citations` / `applicable_laws` for
      `withheld_citations` (reason recorded); every other citation stays.
    * A claim whose sources include a CPC citation -- alone OR beside another
      statute -- is not "supported"/"partial": "unassessed", with why. A valid
      non-CPC source does not carry an unverified CPC assertion.
    * A LEGAL action resting only on CPC sources is removed (the "ask a lawyer"
      step is added); in any other action, summary sentence or claim text only
      the CPC citation clause is taken out.
    * With no law left, the status becomes "cpc_jurisdiction_unverified": not
      grounded, no risk reading. Otherwise the status stands for the law left.
    * `jurisdiction_notice` says why, in English and Urdu; it asks for the
      province only when none is recorded.
    The client's facts and every non-CPC conclusion are untouched.
    """
    if not isinstance(analysis, dict):
        return analysis
    scope = cpc_scope(province, basis, inferred)
    done = analysis.get("cpc_jurisdiction") or {}
    if done.get("version") == INTAKE_CPC_VERSION and done.get("scope") == scope \
            and done.get("province") == ((province or "").lower() or None):
        return analysis
    record = {"version": INTAKE_CPC_VERSION, "scope": scope, "province": (province or "").lower() or None,
              "withheld_citations": 0, "downgraded_claims": 0, "removed_actions": 0, "edited_texts": 0}
    if scope == SCOPE_PUNJAB:
        analysis["cpc_jurisdiction"] = record
        return analysis

    cites = list(analysis.get("law_citations") or [])
    cpc_cites = [c for c in cites if is_cpc(str(c.get("statute") or ""))]
    cpc_cite_idx = {i for i, c in enumerate(cites) if c in cpc_cites}
    cpc_ids = {str(c.get("evidence_id")) for c in cpc_cites if c.get("evidence_id") is not None}
    reason = ("the CPC text on file is the Punjab version; not verified for "
              + (province_label(province) if scope == SCOPE_OTHER else "this matter (province not recorded)"))

    # Citations: the CPC is not shown as applicable law.
    if cpc_cites:
        analysis["law_citations"] = [c for c in cites if c not in cpc_cites]
        moved = [{**c, "withheld_reason": "cpc_jurisdiction_unverified", "jurisdiction_note": reason}
                 for c in cpc_cites]
        analysis["withheld_citations"] = list(analysis.get("withheld_citations") or []) + moved
        from app.ai.intake_evidence import render_applicable_laws
        analysis["applicable_laws"] = render_applicable_laws(analysis["law_citations"])
        record["withheld_citations"] = len(cpc_cites)

    # Claims: per source -- any CPC source means the claim is not verified here.
    claims = list(analysis.get("claim_assessments") or [])
    cpc_only_texts = set()
    for claim in claims:
        ids = _ids(claim)
        text_cpc = bool(cpc_citations(str(claim.get("text") or "")))
        touches = bool(ids & cpc_ids) or text_cpc
        if not touches:
            continue
        if ids and ids <= cpc_ids:
            cpc_only_texts.add(str(claim.get("text") or "").strip())
        if claim.get("support") in ("supported", "partial", "partially_supported"):
            claim["support"] = "unassessed"
            claim["support_reason"] = reason + ("" if ids <= cpc_ids else "; this claim also rests on it")
            record["downgraded_claims"] += 1

    # Actions: a legal step resting only on the CPC goes; elsewhere only the clause.
    from app.ai.intake_output_guard import LAWYER_REVIEW_STEP, is_formal_legal_action
    actions = list(analysis.get("recommended_actions") or [])
    kinds = list(analysis.get("recommended_action_kinds") or [])
    if len(kinds) != len(actions):
        kinds = [None] * len(actions)
    by_text = {str(c.get("text") or "").strip(): c for c in claims}
    kept, kept_kinds, removed, removed_idx = [], [], [], set()
    for i, (text, kind) in enumerate(zip(actions, kinds)):
        t = str(text or "").strip()
        legal = (kind or "legal") == "legal" or is_formal_legal_action(t)
        if legal and t in cpc_only_texts:
            removed.append({"text": t, "kind": "legal", "reason": "cpc_jurisdiction_unverified"})
            removed_idx.add(i)
            continue
        new, n = _edit_text(t, province, scope)
        if n:
            record["edited_texts"] += 1
            if t in by_text:
                by_text[t]["text"] = new
        kept.append(new if n else text)
        kept_kinds.append(kind)
    if removed:
        if LAWYER_REVIEW_STEP not in kept:
            kept.append(LAWYER_REVIEW_STEP)
            kept_kinds.append("general")
        guard = analysis.setdefault("output_guard", {})
        guard["removed_actions"] = list(guard.get("removed_actions") or []) + removed
        record["removed_actions"] = len(removed)
    analysis["recommended_actions"] = kept
    analysis["recommended_action_kinds"] = kept_kinds

    # Summary and claim texts: only the CPC citation clause.
    summary, n = _edit_text(str(analysis.get("summary") or ""), province, scope)
    if n:
        analysis["summary"] = summary
        record["edited_texts"] += 1
    for claim in claims:
        new, n = _edit_text(str(claim.get("text") or ""), province, scope)
        if n:
            claim["text"] = new
    analysis["claim_assessments"] = claims

    # A stored rendering (Urdu) is aligned by position with the English lists:
    # the same entries go, the same clauses are edited.
    added_review = bool(removed) and LAWYER_REVIEW_STEP in kept and LAWYER_REVIEW_STEP not in actions
    for lang, loc in list((analysis.get("localized") or {}).items()):
        if not isinstance(loc, dict) or loc.get("status") != "ok":
            continue
        loc_actions = [a for i, a in enumerate(loc.get("recommended_actions") or []) if i not in removed_idx]
        loc_actions = [_edit_text(str(a), province, scope)[0] for a in loc_actions]
        if added_review:
            loc_actions.append(LAWYER_REVIEW_STEP_UR if lang == "ur" else LAWYER_REVIEW_STEP)
        loc["recommended_actions"] = loc_actions
        for key in ("statute_names", "citation_notes"):
            if isinstance(loc.get(key), list) and len(loc[key]) == len(cites):
                loc[key] = [x for i, x in enumerate(loc[key]) if i not in cpc_cite_idx]
        if loc.get("summary"):
            loc["summary"] = _edit_text(str(loc["summary"]), province, scope)[0]

    touched = any(record[k] for k in ("withheld_citations", "downgraded_claims", "removed_actions", "edited_texts"))
    # A stored v1 analysis was already edited (nothing left to touch now) but
    # carries its notice: the risk rule below still applies to it.
    if touched or analysis.get("jurisdiction_notice"):
        analysis["jurisdiction_notice"] = intake_notice(province, scope)
        supported_legal = [t for t, k in zip(kept, kept_kinds) if k == "legal" and t != LAWYER_REVIEW_STEP]
        if not analysis.get("law_citations") and not supported_legal \
                and analysis.get("grounding_status") in ("grounded", "partially_supported", "supported", None):
            analysis["grounding_status"] = INTAKE_CPC_STATUS
            analysis["grounded"] = False
            analysis["risk_level"] = None
        # Batch 7: the model's risk reading was made WITH the CPC in view and
        # is not recomputed, so it is not presented. Backward-compatible:
        # `risk_level` null is what every existing reader already treats as
        # "no rating" (screen, print, export); `risk_level_basis` says why; the
        # model's value is kept for audit only, never displayed.
        if analysis.get("risk_level"):
            analysis["risk_level_withheld"] = analysis["risk_level"]
            analysis["risk_level"] = None
        analysis["risk_level_basis"] = RISK_NOT_ASSESSED
        record["risk_withheld"] = True
    analysis["cpc_jurisdiction"] = record
    return analysis


def case_summary_with_notice(analysis: dict) -> str | None:
    """The lawyer-facing `ai_summary`: the summary plus its jurisdiction notice,
    so the caveat travels with the summary into the case and the drafter."""
    summary = (analysis or {}).get("summary")
    notice = ((analysis or {}).get("jurisdiction_notice") or {}).get("en")
    if not summary or not notice or notice in summary:
        return summary
    return f"{summary}\n\n{notice}"


# ── the CASE record: lawyer-facing `ai_summary` (batch 7) ──────────────────
#
# Every case leaving the API passes through case_service._public_case, and the
# drafter's case context is built from that output. A case converted before
# batch 6 carries a summary written with the Punjab CPC in view and no
# jurisdiction note. It is free text: CPC CITATIONS can be taken out reliably,
# a paraphrase cannot -- so a legacy non-Punjab summary is never presented as
# cleaned. It gets an explicit "written before this check" warning. New
# conversions record `ai_summary_cpc_checked` and are left as written.
CASE_CPC_MARK = "ai_summary_cpc_checked"


def legacy_case_warning(province: str | None, scope: str) -> dict:
    where = _where(province, scope)
    en = ("Jurisdiction warning: this summary was written before the Code of Civil Procedure jurisdiction check "
          f"was added. It may rely on the Punjab version of the CPC, which is not verified for {where}. CPC "
          "citations found in it were taken out, but its other wording may still reflect that text. Treat it as "
          "unverified.")
    ur = ("دائرۂ اختیار کی تنبیہ: یہ خلاصہ ضابطہ دیوانی (CPC) کی جانچ شامل ہونے سے پہلے لکھا گیا تھا۔ اس میں پنجاب کے CPC "
          "متن پر انحصار ہو سکتا ہے جو آپ کے صوبے کے لیے تصدیق شدہ نہیں۔ اسے غیر تصدیق شدہ سمجھیں۔")
    return {"en": en, "ur": ur}


def case_cpc_view(case: dict) -> dict:
    """The case as it may be SHOWN (`case` is the caller's copy; nothing is
    written back).

    Adds `ai_summary_jurisdiction` {"status", ...} for a non-Punjab case with an
    AI summary:
      checked            written by a conversion that ran the CPC step
      legacy_unverified  written before it: CPC citations cut from the summary
                         and its Urdu twins, and the warning appended
    Confirmed-Punjab cases and cases without an AI summary are unchanged.
    """
    if not isinstance(case, dict) or not case.get("ai_summary"):
        return case
    province = case.get("province")
    scope = cpc_scope(province, "case_record")
    if scope == SCOPE_PUNJAB:
        return case
    summary = str(case["ai_summary"])
    if case.get(CASE_CPC_MARK) or NOTICE_MARK_EN in summary:
        case["ai_summary_jurisdiction"] = {"status": "checked", "scope": scope}
        return case
    warning = legacy_case_warning(province, scope)
    edited, n = _edit_text(summary, province, scope)
    # FIRST, not last: the drafter's case context caps the summary at 1,500
    # characters, and a warning at the end of a long summary would be cut off.
    case["ai_summary"] = warning["en"] + "\n\n" + edited.strip()
    loc = case.get("ai_summary_localized")
    if isinstance(loc, dict) and loc.get("ur"):
        ur = _edit_text(str(loc["ur"]), province, scope)[0].rstrip()
        case["ai_summary_localized"] = {**loc, "ur": warning["ur"] + "\n\n" + ur.strip()}
    acts = case.get("ai_actions_localized")
    if isinstance(acts, dict) and isinstance(acts.get("ur"), list):
        case["ai_actions_localized"] = {**acts, "ur": [_edit_text(str(x), province, scope)[0] for x in acts["ur"]]}
    case["ai_summary_jurisdiction"] = {"status": "legacy_unverified", "scope": scope,
                                       "cpc_citations_removed": n, "warning": warning}
    return case


# ── fail-closed summary handling (batch 8) ────────────────────────────────────

REVIEW_UNAVAILABLE = "review_unavailable"
_UNAVAILABLE_WARNING = {
    "en": ("AI summary withheld: the jurisdiction check for this case's AI summary could not run, so the "
           "summary is not shown. The case's own description is not affected."),
    "ur": ("اے آئی خلاصہ روک دیا گیا: اس کیس کے اے آئی خلاصے کی دائرۂ اختیار کی جانچ نہیں ہو سکی، اس لیے خلاصہ نہیں "
           "دکھایا گیا۔ کیس کی اپنی تفصیل متاثر نہیں۔"),
}
_AI_SUMMARY_FIELDS = ("ai_summary", "ai_summary_localized", "ai_actions_localized")


def case_summary_unavailable(case: dict) -> dict:
    """When `case_cpc_view` itself fails: the case stays readable, but NO AI
    summary text -- English, Urdu, or the Urdu actions -- leaves as if it had
    been checked. Plain dict operations only, so this cannot fail in turn."""
    if not isinstance(case, dict) or not any(case.get(k) for k in _AI_SUMMARY_FIELDS):
        return case
    case["ai_summary"] = None
    case.pop("ai_summary_localized", None)
    case.pop("ai_actions_localized", None)
    case["ai_summary_jurisdiction"] = {"status": REVIEW_UNAVAILABLE, "warning": dict(_UNAVAILABLE_WARNING)}
    return case


class SummaryUnusable(Exception):
    """The case's AI summary may not be used as model input; the message says
    what to do instead."""


_LEGACY_INPUT_MSG = ("This case has no description of its own, and its AI summary was written before the Code of "
                     "Civil Procedure jurisdiction check, so it cannot be used to fill in a document. Add the case "
                     "facts to the case description, then extract the fields again.")
_UNAVAILABLE_INPUT_MSG = ("This case has no description of its own, and the jurisdiction check for its AI summary "
                          "could not run just now, so the summary is not used. Add the case facts to the case "
                          "description, or try again later.")


def summary_for_model_input(case: dict) -> str | None:
    """The case's AI summary as text a model may be given, or None when there
    is none. Raises SummaryUnusable for a summary that must not be used:
    written before the CPC jurisdiction check in a non-Punjab / unknown-province
    case, or one whose check could not run. A checked non-Punjab summary is
    given without its jurisdiction notice (a caveat, not a fact)."""
    import copy
    if not isinstance(case, dict) or not case.get("ai_summary"):
        return None
    try:
        view = case_cpc_view(copy.deepcopy(case))
    except Exception as exc:  # noqa: BLE001 -- any failure: do not use the summary
        raise SummaryUnusable(_UNAVAILABLE_INPUT_MSG) from exc
    status = (view.get("ai_summary_jurisdiction") or {}).get("status")
    if status in ("legacy_unverified", REVIEW_UNAVAILABLE):
        raise SummaryUnusable(_LEGACY_INPUT_MSG if status == "legacy_unverified" else _UNAVAILABLE_INPUT_MSG)
    text = str(view.get("ai_summary") or "")
    if status == "checked":
        text = "\n\n".join(p for p in text.split("\n\n") if not p.strip().startswith(NOTICE_MARK_EN)).strip()
    return text or None


# ── authority availability: does the corpus hold the CPC this matter needs? ──
# (batch 9, 2026-10-17; release blocker found by the scratch CPC-relabel
# experiment, evals/legal_sources/SCRATCH_CPC_RELABEL_2026-10-17.md)
#
# A CPC chunk's jurisdiction is read from its recorded PROVENANCE -- the source
# file it was ingested from -- never from its `province` field, which is wrongly
# "federal" today and "punjab" after the scratch relabel. A CPC source that is
# not in this registry is "unverified" and is not anyone's applicable law.
CPC_SOURCES = {
    # Punjab Code consolidation, sha256 528384375982b48f0398da46e70606524a8e3db7590dbf087e9b6b86d926a795
    # (BATCH2 §3; verified snapshot 2026-10-17). Its footnotes cite the
    # Code of Civil Procedure (Punjab Amendment) Act 2018 (XIV of 2018).
    "code of civil procedure 1908.pdf": "punjab",
}
SOURCE_UNAVAILABLE = "source_unavailable_for_jurisdiction"


def cpc_chunk_jurisdiction(chunk: dict) -> str | None:
    """None for a non-CPC chunk; otherwise the jurisdiction its SOURCE is the
    text of ("punjab"), or "unverified" for an unregistered CPC source."""
    if not is_cpc(str((chunk or {}).get("statute") or "")):
        return None
    src = str((chunk or {}).get("source_file") or "").strip().lower()
    return CPC_SOURCES.get(src, "unverified")


def cpc_text_available(province: str | None, basis: str | None = None, inferred: bool = False) -> bool:
    """Does the corpus hold CPC text applicable to this matter's province?
    Unknown or model-inferred provinces are never assumed to be Punjab."""
    scope = cpc_scope(province, basis, inferred)
    if scope == SCOPE_UNKNOWN:
        return False
    held = set(CPC_SOURCES.values())
    if scope == SCOPE_PUNJAB:
        return "punjab" in held
    return (province or "").strip().lower() in held


# Civil-procedure questions the CPC governs. Precise phrases only: "court",
# "application", "suit", "decree", "order" alone never count.
_CPC_PROCEDURAL = [(re.compile(p, re.IGNORECASE), label) for p, label in (
    (r"\b(?:temporary|interim|ad[- ]?interim)\s+injunctions?\b", "temporary injunction"),
    (r"\bex[- ]?parte\s+decrees?\b", "ex parte decree"),
    (r"\bset(?:ting)?\s+aside\s+(?:an?\s+|the\s+)?(?:ex[- ]?parte\s+)?(?:decree|judg(?:e)?ment)\b", "setting aside a decree"),
    (r"\bexecution\s+of\s+(?:a\s+|the\s+|his\s+|her\s+|my\s+|this\s+)?decrees?\b", "execution of a decree"),
    (r"\b(?:judg(?:e)?ment[- ]debtor|decree[- ]holder)s?\b", "execution of a decree"),
    (r"\battachment\s+before\s+judg(?:e)?ment\b", "attachment before judgment"),
    (r"\breject(?:ion|ed|ing)?\s+(?:of\s+)?(?:the\s+|a\s+)?plaint\b", "rejection of plaint"),
    (r"\breturn\s+of\s+(?:the\s+|a\s+)?plaint\b", "return of plaint"),
    (r"\bwritten\s+statements?\b", "written statement"),
    (r"\bres\s+judicata\b|\bres\s+sub[- ]judice\b", "res judicata"),
    (r"\bpecuniary\s+jurisdiction\b", "pecuniary jurisdiction"),
    (r"\bwhere\s+the\s+defendants?\s+(?:resides?|lives?|carr(?:y|ies)\s+on\s+business)\b", "place of suing"),
    (r"\bamend(?:ment)?\s+(?:of\s+)?(?:the\s+)?(?:plaint|pleadings?)\b", "amendment of pleadings"),
    (r"\bimplead(?:ment|ed|ing)?\b", "impleadment"),
    (r"\bcivil\s+revision\b", "civil revision"),
    (r"حکم\s*امتناعی", "temporary injunction"),
    (r"یک\s*طرفہ\s*(?:ڈگری|فیصلہ)", "ex parte decree"),
    (r"اجرائے\s*ڈگری|ڈگری\s*(?:کا|کی)\s*اجراء?", "execution of a decree"),
    (r"عرضی\s*دعو[یٰى]+\s*(?:کو\s*)?(?:مسترد|خارج)", "rejection of plaint"),
    (r"جواب\s*دعو[یٰى]+", "written statement"),
    (r"\bhukm[- ]?e?[- ]?imtinai\b", "temporary injunction"),
    (r"\byak\s*t[ae]r(?:a)?fa\s+(?:decree|digree|faisla)\b", "ex parte decree"),
    (r"\bdecree\s+ka\s+ijra\b|\bijra[- ]e[- ]decree\b", "execution of a decree"),
    (r"\bjawab[- ]?e?[- ]?dawa\b", "written statement"),
)]
# A bare mention of the Code itself (no section) also requires it.
_CPC_NAMED = re.compile(r"\bCPC\b|\bC\.P\.C\b|Code\s+of\s+Civil\s+Procedure|Civil\s+Procedure\s+Code|ضابطہ\s*دیوانی",
                        re.IGNORECASE)
# Other law the question itself names (a mixed question keeps that part).
_OTHER_ACT = re.compile(r"\b((?:[A-Z][\w'()-]*\s+){1,6}(?:Act|Ordinance))\b")
_OTHER_LAW_WORDS = re.compile(
    r"(?i)\b(?:specific\s+relief|limitation\s+act|contract\s+act|transfer\s+of\s+property|rented\s+premises|"
    r"pre-?emption\s+act|family\s+courts?\s+act|guardians?\s+and\s+wards|succession\s+act|registration\s+act|"
    r"stamp\s+act|court\s+fees?\s+act|PPC|Pakistan\s+Penal\s+Code|CrPC|Qanun-?e-?Shahadat)\b")


def cpc_requirement(text: str) -> dict:
    """Does `text` require the CPC? {"required", "explicit", "procedural",
    "other_law"}. Explicit = a CPC citation or the Code named; procedural = a
    precise civil-procedure phrase; other_law = another statute the question
    itself names (so a mixed question keeps its non-CPC part)."""
    t = text or ""
    explicit = [t[a:b] for a, b in cpc_citations(t)]
    if not explicit and _CPC_NAMED.search(t):
        explicit = [_CPC_NAMED.search(t).group(0)]
    procedural = sorted({label for rx, label in _CPC_PROCEDURAL if rx.search(t)})
    other = [m.group(1).strip() for m in _OTHER_ACT.finditer(t)
             if not re.search(r"(?i)civil\s+procedure", m.group(1))]
    other += [m.group(0) for m in _OTHER_LAW_WORDS.finditer(t)]
    return {"required": bool(explicit or procedural), "explicit": explicit, "procedural": procedural,
            "other_law": sorted(set(other))}


def cpc_unavailable_reason(province: str | None, basis: str | None = None, inferred: bool = False) -> str:
    scope = cpc_scope(province, basis, inferred)
    if scope == SCOPE_UNKNOWN:
        return ("the question needs the Code of Civil Procedure, the province of this matter is not recorded, "
                "and the only CPC text held is the Punjab version -- add the province")
    return ("the question needs the Code of Civil Procedure, and the only CPC text held is the Punjab version, "
            f"which is not verified for {province_label(province)}")

