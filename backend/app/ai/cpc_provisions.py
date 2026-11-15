"""CPC provisions by their REAL identity, for the lawyer drafter (2026-10-15).

The base civil index files every First Schedule ORDER RULE under a section
number: the drafter's law context told the model "CPC 1908 -- Section 1:
Withdrawal of suit" (that is Order XXIII Rule 1), and the model cited
"Section 1 CPC" (eval drafter_v2, results/v2_r1). The versioned identity
index `civil_collection__ident_v1` (scripts/build_ident_index.py) already
labels each chunk `provision_kind` = section | order_rule | appendix with a
`provision_label` such as "Order VII Rule 11". This module reads it --
read-only, nothing re-indexed -- and offers:

  * catalogue()        every CPC section and Order/Rule the index holds, with
                       its heading (from the chunk's own leading heading);
  * parse_refs(text)   "Order VII Rule 11", "O.7 r.11", "order 7 rule 11",
                       "آرڈر 7 رول 11" -> (order, rule); Urdu digits too;
  * lookup(...)        one provision, or None when the index does not hold it;
Heading-word matching (request -> provision) was tried and dropped: on the
eval's civil requests it put unrelated rules first (Section 20 ahead of
Order VII Rule 11 for "rejection of plaint"; Order IX Rule 4 for "withdraw
with permission to file a fresh suit"), and text presented to the model as
the governing provision must not be a guess.

The index holds 136 of the Code's 158 sections (s.114 among the missing) and
628 Order/Rule labels; "Order X (rule not shown)" chunks are never guessed.
"""
from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass

logger = logging.getLogger(__name__)

IDENT_COLLECTION = "civil_collection__ident_v2"   # 2026-10-15 switch (rollback: ident_v1); evals/drafter_v2/INDEX_REPAIR_PROPOSAL.md
STATUTE = "CPC 1908"

_ROMAN = [(50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]


def roman(n: int) -> str:
    out = ""
    for v, s in _ROMAN:
        while n >= v:
            out += s
            n -= v
    return out


def to_int(token: str) -> int | None:
    t = (token or "").strip().upper()
    if t.isdigit():
        return int(t)
    vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
    if not t or any(ch not in vals for ch in t):
        return None
    total = 0
    for i, ch in enumerate(t):
        v = vals[ch]
        total += -v if i + 1 < len(t) and vals[t[i + 1]] > v else v
    return total if roman(total) == t else None


_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_ORDER_RULE = re.compile(
    r"(?<![A-Za-z])(?:Order|O\.|O(?=\s+(?:[IVXLC]{1,7}|\d{1,2})\s*,?\s*R)|آرڈر|آرڈ ر)\s*([IVXLC]{1,7}|\d{1,2})(?![A-Za-z\d])\s*,?\s*"
    r"(?:Rule|Rules|R\.|r\.|R(?=\s*\d)|r(?=\s*\d)|رول|قاعدہ)\s*(\d{1,3})(?:-?([A-Z])(?![A-Za-z]))?(?![\d])", re.IGNORECASE)


@dataclass(frozen=True)
class Provision:
    kind: str            # "section" | "order_rule"
    order: int | None
    number: str          # section number, or the rule number
    label: str           # "Section 151" | "Order VII Rule 11"
    heading: str
    content: str


def label_for(order: int, rule: str) -> str:
    return f"Order {roman(order)} Rule {rule}"


def parse_refs(text: str) -> list[tuple[int, str, int, int]]:
    """(order, rule, start, end) for each Order/Rule reference, in order."""
    t = (text or "").translate(_DIGITS)
    out = []
    for m in _ORDER_RULE.finditer(t):
        order = to_int(m.group(1))
        if order is None or not 1 <= order <= 99:     # >51 is kept: the guard reports it as nonexistent
            continue
        rule = m.group(2) + ((m.group(3) or "").upper())
        out.append((order, rule, m.start(), m.end()))
    return out


_lock = threading.Lock()
_cache: dict | None = None


def _heading(text: str, number: str) -> str:
    from app.ai.corpus_index import heading_of
    return (heading_of(text or "", number) or "").strip()


# ── one chunk, several rules (2026-10-15) ───────────────────────────────────
# A chunk can hold the end of one rule and the start of the next: chunk
# "Order IX Rule 12" of the identity index also holds "2 [13. Setting aside
# decree ex-parte against defendant._ (1)] In any case in which a decree is
# passed ex parte ..." (checked against the official Pakistan Code PDF). Filed
# whole under Rule 12, a claim relying on Rule 12 for setting aside an ex parte
# decree was compared with Rule 13's words and SUPPORTED (eval v2_r2, V05).
# Each rule now gets only ITS text: the chunk is cut where the next rule's
# heading begins -- at the offsets the index records (`rule_spans`, ident_v2,
# from the official text), or else at a rule heading found in the text itself
# (a later number of the same Order, followed by the heading's own "._" / ".__"
# / ".-" mark, which footnotes and cross-references do not have).
_IN_TEXT_RULE = re.compile(
    r"(?:(?<=\s)|^)(?:\d{1,2}\s*\[\s*|\[\s*)?(\d{1,3}[A-Z]?)\s*\.\s*([A-Z][^\n]{2,110}?)\s*(?:\._|\.\s*[–\-]|_{2})")
_SPAN = re.compile(r"^\s*(Order\s+[IVXLC]+\s+Rule\s+\d+[A-Z]?)\s*@\s*(\d+)\s*$")


def group_heading_start(doc: str, cut: int) -> int:
    """Where the next rule's text really begins: a short group heading right
    before it ("... who do not appear. Setting aside Decree ex parte 2 [13.")
    belongs to the NEXT rule -- left on the previous one it gave Rule 12 the
    words "setting aside decree ex parte"."""
    before = doc[max(0, cut - 90):cut]
    m = re.search(r"[.:;]\s+([^.:;]{3,80})$", before)
    if m and len(m.group(1).split()) <= 8 and m.group(1).strip()[:1].isupper():
        return cut - len(m.group(1))
    return cut


def _rule_key(rule: str) -> tuple[int, str]:
    m = re.match(r"(\d+)([A-Z]?)", str(rule))
    return (int(m.group(1)), m.group(2)) if m else (0, "")


def split_rules(doc: str, label: str, spans: str = "") -> list[tuple[str, str]]:
    """[(label, text)] -- the chunk cut at each rule boundary, its own label
    first. `spans` ("Order IX Rule 12@0;Order IX Rule 13@612") wins when given;
    a malformed one is ignored, never half-applied."""
    doc = doc or ""
    if spans:
        parts = [_SPAN.match(x) for x in spans.split(";") if x.strip()]
        if parts and all(parts):
            cuts = sorted((int(m.group(2)), " ".join(m.group(1).split())) for m in parts)
            if cuts[0][0] == 0 and all(0 <= a < len(doc) for a, _ in cuts) and len({a for a, _ in cuts}) == len(cuts):
                return [(lab, doc[a:(cuts[i + 1][0] if i + 1 < len(cuts) else len(doc))])
                        for i, (a, lab) in enumerate(cuts)]
        logger.warning("cpc_provisions: malformed rule_spans for %s ignored", label)
    m = re.match(r"Order\s+([IVXLC]+)\s+Rule\s+(\d+[A-Z]?)$", label or "")
    if not m:
        return [(label, doc)]
    order, current = to_int(m.group(1)), m.group(2)
    cuts = [(0, label)]
    for h in _IN_TEXT_RULE.finditer(doc):
        if h.start() == 0:
            continue
        r = h.group(1)
        (n, letter), (cn, cletter) = _rule_key(r), _rule_key(current)
        if cn < n <= cn + 6 or (n == cn and letter > cletter):
            cuts.append((group_heading_start(doc, h.start()), label_for(order, r)))
            current = r
    return [(lab, doc[a:(cuts[i + 1][0] if i + 1 < len(cuts) else len(doc))]) for i, (a, lab) in enumerate(cuts)]


def build_catalogue(rows) -> dict:
    """rows: iterable of (metadata, document), in chunk order. -> {"provisions": {label: Provision}, "orders": set}
    A rule's content is its OWN text only (split_rules); a chunk that continues
    a rule without a heading of its own (ident_v2 continuations) is appended to it."""
    provisions: dict[str, Provision] = {}
    orders: set[int] = set()
    label_re = re.compile(r"Order\s+([IVXLC]+)\s+Rule\s+(\d+[A-Z]?)$")
    for md, doc in rows:
        if not str(md.get("statute") or "").startswith("CPC"):
            continue
        kind = md.get("provision_kind") or "section"
        if kind == "order_rule":
            lab = str(md.get("provision_label") or "")
            om = re.match(r"Order\s+([IVXLC]+)\b", lab)
            if om and to_int(om.group(1)):
                orders.add(to_int(om.group(1)))
            if not label_re.match(lab):
                continue                         # "(rule not shown)": never guessed
            pieces = split_rules(doc or "", lab, str(md.get("rule_spans") or ""))
        elif kind == "section":
            sec = str(md.get("section_number") or "").strip()
            if not sec:
                continue
            pieces = [(f"Section {sec}", doc or "")]
        else:
            continue
        for plab, text in pieces:
            m = label_re.match(plab)
            if m:
                order, number = to_int(m.group(1)), m.group(2)
                # the heading follows the rule's number -- after a group heading
                # ("Setting aside Decree ex parte") or an amendment mark ("2 [")
                at = re.search(rf"(?:\d{{1,2}}\s*\[\s*|\[\s*)?(?<![\d.]){re.escape(number)}\s*\.", text[:160])
                head = _heading(re.sub(r"^\s*(?:\d{1,2}\s*)?\[\s*", "", text[at.start():] if at else text), number)
                prov = Provision("order_rule", order, number, plab, head, text)
            else:
                number = plab.split()[-1]
                prov = Provision("section", None, number, plab, _heading(text, number), text)
            old = provisions.get(prov.label)
            if old is None or (not old.heading and prov.heading):
                provisions[prov.label] = prov
            elif not prov.heading and old.heading and text.strip() and text not in old.content:
                # the rest of the same rule, in the next chunk
                provisions[prov.label] = Provision(old.kind, old.order, old.number, old.label, old.heading,
                                                   f"{old.content}\n{text}")
    return {"provisions": provisions, "orders": orders}


def catalogue() -> dict:
    global _cache
    with _lock:
        if _cache is None:
            from app.ai import index_health
            from app.db.chroma import get_chroma
            client = get_chroma()
            index_health.require(IDENT_COLLECTION, client)   # verified build, or IdentityIndexUnavailable
            got = client.get_collection(IDENT_COLLECTION).get(
                where={"statute": {"$eq": STATUTE}}, include=["metadatas", "documents"])
            # chunk order: a rule continued in the next chunk is appended in sequence
            rows = sorted(zip(got.get("ids") or [], got.get("metadatas") or [], got.get("documents") or []),
                          key=lambda r: r[0])
            _cache = build_catalogue((md, doc) for _, md, doc in rows)
            logger.info("cpc_provisions: %d provisions, %d orders", len(_cache["provisions"]), len(_cache["orders"]))
        return _cache


def set_catalogue(cat: dict | None) -> None:
    """Install a catalogue (tests) or clear the cache with None."""
    global _cache
    with _lock:
        _cache = cat


def lookup(order: int | None, number: str) -> Provision | None:
    cat = catalogue()["provisions"]
    return cat.get(label_for(order, number) if order else f"Section {number}")


def order_known(order: int) -> bool:
    return order in catalogue()["orders"]


# ── Order titles and scope (2026-10-15) ─────────────────────────────────────
# Some Orders apply only to one class of suit: Order XXXVII is "Summary
# procedure on negotiable instruments", and its Rule 4 ("Power to set aside
# decree") was SUPPORTED for an ordinary ex parte decree (eval v2 dev, V05).
# The title of each Order is in the source text itself -- at the end of the
# previous Order's last rule ("... ORDER XXXVII \nSUMMARY PROCEDURE ON
# NEGOTIABLE INSTRUMENTS") -- so the scope is READ from the Code, not written
# here. An Order whose title was not recovered has no scope check.
_TITLE = re.compile(r"ORDER\s+([XVIL]+)\s*\.?\s*\n\s*((?:[A-Z][A-Z,'\-]*[ \t]*){1,16})")
# Appeal and review Orders too (eval v2_r3 dev, V07): "Order XLI Rule 12" --
# the APPELLATE court fixing the day for hearing an appeal -- was SUPPORTED
# for an early hearing of an application in a suit.
_SCOPED_TITLE = re.compile(r"^(?:SUITS\b|SUMMARY\s+PROCEDURE\b|INTERPLEADER\b|(?:PAUPER\s+)?APPEALS\b|REVIEW\b)")
_TITLE_STOP = frozenset("suits suit by or against relating to of on in the their and procedure persons "
                        "from original decrees orders supreme court".split())


def order_titles(cat: dict) -> dict[int, str]:
    if "titles" not in cat:
        titles: dict[int, str] = {}
        for p in cat["provisions"].values():
            for m in _TITLE.finditer(p.content or ""):
                n = to_int(m.group(1))
                title = " ".join(m.group(2).split())
                if n and len(title) >= 8:
                    titles.setdefault(n, title)
        cat["titles"] = titles
    return cat["titles"]


def order_scope(cat: dict, order: int) -> tuple[str, set[str]] | None:
    """(title, scope words) for an Order limited to one class of suit; None
    for a general Order or one whose title our copy does not show."""
    title = order_titles(cat).get(order)
    if not title or not _SCOPED_TITLE.match(title):
        return None
    words = {w for w in re.findall(r"[a-z]{3,}", title.lower()) if w not in _TITLE_STOP}
    return (title, words) if words else None
