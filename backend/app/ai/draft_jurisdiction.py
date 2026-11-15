"""Which province's law a lawyer's draft is written under (2026-10-14).

The drafter used to send no province for a document without a case, and the
retriever then searched EVERY jurisdiction: a Sindh tenancy notice could be
grounded in, and confidently cite, the Punjab Rented Premises Act. Now:

* a case-bound draft takes the province stored on the case (the server's
  `case_context`, never the UI);
* a caseless draft takes the province the lawyer chose -- one of the existing
  values in `ai/jurisdiction.py`, nothing new;
* "not chosen" (empty or `jurisdiction.UNSPECIFIED`) is a JURISDICTION-NEUTRAL
  draft: federal law only is retrieved, the model is told to leave a
  placeholder wherever provincial law governs, and any unit that names a
  provincial statute anyway is withheld from the proposal.

A unit naming ANOTHER province's statute (a Punjab Act in a Sindh draft, or any
provincial Act in a federal draft) is withheld the same way. This is a name
check on provincial Acts, not a check that the right law was applied.
"""
from __future__ import annotations

import re

from app.ai import jurisdiction

# Display names, as in the lawyer Cases page.
LABELS = {
    "punjab": "Punjab", "sindh": "Sindh", "kpk": "Khyber Pakhtunkhwa",
    "balochistan": "Balochistan", "federal": "Federal / Islamabad",
}

BASIS_CASE = "case"
BASIS_SELECTED = "selected"
BASIS_NEUTRAL = "neutral"

# A provincial statute NAMED in the text: the province word followed, within a
# few capitalised words, by Act / Ordinance / Rules / Regulations. "resident of
# Lahore, Punjab" is not one; "the Punjab Rented Premises Act, 2009" is.
_PROVINCE_WORD = {
    "punjab": "punjab", "sindh": "sindh", "khyber pakhtunkhwa": "kpk", "kpk": "kpk", "kp": "kpk",
    "nwfp": "kpk", "n.w.f.p.": "kpk", "n.w.f.p": "kpk", "balochistan": "balochistan", "baluchistan": "balochistan",
}
_PROVINCIAL_ACT = re.compile(
    r"\b(Punjab|Sindh|Khyber\s+Pakhtunkhwa|KPK|KP|NWFP|N\.W\.F\.P\.?|Balochistan|Baluchistan)"
    r"\s+(?:[A-Z][\w'()&-]*\s+){0,8}?(Act|Ordinance|Rules|Regulations)\b")


def resolve(case_bound: bool, province: str | None) -> tuple[str, str]:
    """(province, basis) for retrieval and the prompt. `province` is already
    validated by the caller (a VALID_PROVINCES value or UNSPECIFIED)."""
    p = jurisdiction.normalise(province)
    if p == jurisdiction.UNSPECIFIED:
        return jurisdiction.UNSPECIFIED, BASIS_NEUTRAL
    return p, (BASIS_CASE if case_bound else BASIS_SELECTED)


def is_valid_choice(raw: str | None) -> bool:
    """A caseless request's province: empty / UNSPECIFIED (neutral) or a known
    province. Anything else ("Punjab Province", "national") is refused rather
    than quietly read as neutral."""
    v = (raw or "").strip().lower()
    return v in ("", jurisdiction.UNSPECIFIED) or jurisdiction.is_known(v)


def retrieval_province(province: str) -> str:
    """Neutral drafts read federal law only -- never every province mixed."""
    return "federal" if province == jurisdiction.UNSPECIFIED else province


def rider(province: str, basis: str) -> str:
    """The prompt's jurisdiction instruction."""
    if basis == BASIS_NEUTRAL:
        return ("\n\nJURISDICTION NOT CHOSEN: the lawyer has not chosen a province, so only federal law was "
                "retrieved. Do NOT cite, name or rely on any provincial statute (Punjab, Sindh, Khyber "
                "Pakhtunkhwa, Balochistan). Where the governing law depends on the province (rent and tenancy, "
                "pre-emption, land revenue, local government and similar), write [applicable provincial law -- "
                "confirm jurisdiction] instead of naming an Act.")
    label = LABELS.get(province, province)
    out = f"\n\nJURISDICTION: this document is for {label}."
    if province != "federal":
        out += " Do not cite a statute of any other province."
        if not jurisdiction.has_corpus(province):
            out += (f" The library holds no {label} provincial statutes, only federal law: do not name a {label} "
                    f"statute from memory -- write [applicable {label} law -- verify] where provincial law governs.")
    else:
        out += " Do not cite any provincial statute."
    return out


def foreign_units(text: str, province: str) -> list[dict]:
    """Units naming a provincial statute this draft's jurisdiction excludes:
    [{span, text, reasons}], in order."""
    from app.ai.visible_authority import _units
    allowed = province if province in jurisdiction.VALID_PROVINCES and province != "federal" else None
    out = []
    for a, b in _units(text):
        unit = text[a:b]
        names = []
        for m in _PROVINCIAL_ACT.finditer(unit):
            prov = _PROVINCE_WORD.get(re.sub(r"\s+", " ", m.group(1)).lower())
            if prov and prov != allowed:
                names.append((prov, m.group(0).strip()))
        if not names:
            continue
        if allowed is None and province == jurisdiction.UNSPECIFIED:
            why = "no jurisdiction was chosen for this draft, so it names no provincial statute"
        elif allowed is None:
            why = "this draft is under federal law"
        else:
            why = f"this draft is for {LABELS[allowed]}"
        reasons = [f"{name} is {LABELS[prov]} law, and {why}." for prov, name in names]
        out.append({"span": (a, b), "text": unit, "reasons": reasons})
    return out


def remove(text: str, units: list[dict]) -> str:
    """The text without `units` (no note written in)."""
    out, last = [], 0
    for u in sorted(units, key=lambda u: u["span"]):
        a, b = u["span"]
        if a < last:
            continue
        out.append(text[last:a])
        last = b
    out.append(text[last:])
    joined = re.sub(r"[ \t]+\n", "\n", "".join(out))
    return re.sub(r"\n{3,}", "\n\n", joined).strip()

# ── issues whose governing law is PROVINCIAL (fix 2, 2026-10-14) ─────────────
# In a jurisdiction-neutral draft the model filled a tenancy notice with the
# federal Transfer of Property Act (ss.111/113) -- confidently, and for an issue
# each province's rent law governs. For these issues a neutral draft must say
# the law depends on the province and leave a placeholder; a unit that cites a
# federal provision the provincial law may displace is withheld. Other federal
# law in the draft (the Contract Act on damages, the CPC on procedure) stays.
# NEEDS LAWYER REVIEW: which federal provisions each provincial law displaces
# (the lists below are deliberately narrow).
TOPICS = {
    "tenancy": {
        "label": "tenancy and eviction", "law": "rent law",
        "ask": re.compile(r"(?i)\b(?:tenan\w*|evict\w*|landlord|rent(?:al|ed)?\b|rented\s+premises)"),
        "displaced": [(re.compile(r"(?i)Transfer\s+of\s+Property|\bTPA\b"), range(105, 118))],
    },
    "employment": {
        "label": "terms and termination of employment", "law": "labour (standing orders) law",
        "ask": re.compile(r"(?i)\b(?:labou?r\s+law|standing\s+orders?|workm[ae]n|employment\s+contract|employee|employer)\b"),
        "displaced": [(re.compile(r"(?i)Standing\s+Orders"), None)],
    },
    "pre-emption": {
        "label": "pre-emption", "law": "pre-emption law",
        "ask": re.compile(r"(?i)\b(?:pre-?\s?emption|talb|shuf'?a)"),
        "displaced": [],
    },
}


def topic_for(request: str) -> str | None:
    """The province-dependent issue a request is about, if any."""
    for key, t in TOPICS.items():
        if t["ask"].search(request or ""):
            return key
    return None


def topic_rider(province: str, topic: str | None) -> str:
    if province != jurisdiction.UNSPECIFIED or not topic:
        return ""
    t = TOPICS[topic]
    return (f"\n\nTHIS ISSUE DEPENDS ON THE PROVINCE: {t['label']} is governed by provincial {t['law']}, and no "
            f"jurisdiction was chosen. Do not cite any statute for it (federal or provincial). Write "
            f"[applicable provincial {t['law']} -- choose jurisdiction] where the authority would go.")


def neutral_units(text: str, province: str, topic: str | None) -> list[dict]:
    """Neutral draft, province-dependent issue: units that cite a federal
    provision the provincial law may displace for that issue."""
    if province != jurisdiction.UNSPECIFIED or not topic or not TOPICS[topic]["displaced"]:
        return []
    from app.ai import tool_contract
    from app.ai.visible_authority import _units
    t = TOPICS[topic]
    out = []
    for a, b in _units(text):
        # A [placeholder] is what the rider asks for, never a citation: the
        # rule once withheld its own "[applicable provincial labour (standing
        # orders) law -- choose jurisdiction]" (eval after_r1, A4).
        unit = re.sub(r"\[[^\]]*\]", " ", text[a:b])
        names = []
        for ref in tool_contract.provision_refs(unit):
            for rx, sections in t["displaced"]:
                m = re.match(r"\d+", str(ref.section))
                if rx.search(ref.statute or "") and (sections is None or (m and int(m.group(0)) in sections)):
                    names.append(f"Section {ref.section} {ref.statute}".strip())
        if not names and any(rx.search(unit) and sections is None for rx, sections in t["displaced"]):
            names.append(next(rx.search(unit).group(0) for rx, s in t["displaced"] if rx.search(unit)))
        if names:
            out.append({"span": (a, b), "text": text[a:b], "reasons": [
                f"{n} is federal law that may not govern {t['label']}: provincial {t['law']} applies, and no "
                f"jurisdiction was chosen for this draft." for n in dict.fromkeys(names)]})
    return out


_PLACEHOLDER = re.compile(r"(?i)\[[^\]]{0,80}(?:law|act|jurisdiction|province|provincial|statute|ordinance)[^\]]{0,80}\]")


def clarification(province: str, topic: str | None, final_text: str) -> dict | None:
    """What the lawyer is told when a neutral draft touches a province-dependent
    issue -- shown beside the proposal, never written into it."""
    if province != jurisdiction.UNSPECIFIED or not topic:
        return None
    t = TOPICS[topic]
    return {"topic": topic,
            "message": f"{t['label'].capitalize()} depends on the province's {t['law']}. Choose a jurisdiction "
                       f"to cite it; until then this draft should name no statute for it.",
            "placeholder": bool(_PLACEHOLDER.search(final_text or ""))}
