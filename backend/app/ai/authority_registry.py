"""Authority-capability registry (batch 10, 2026-10-17).

Which authorities the corpus HOLDS, and for which jurisdiction, is recorded here
from VERIFIED provenance -- the source file each chunk was ingested from -- read
from the verified snapshot. The chunk's `province` field is not consulted: the
Punjab Code CPC is labelled `federal` today and `punjab` after a relabel.

Only verified entries are listed. Coverage is never inferred for another
province, and a law named in a test fixture is not thereby in the corpus.

A question that clearly REQUIRES a registered authority (an explicit reference,
or a precise issue phrase) in a matter where that authority is not held must not
be answered -- or marked "supported" -- from whatever other law retrieval left.
Detection is deliberately narrow: bare "rent", "property", "court",
"application" or "appeal" never count.
"""
from __future__ import annotations

import re

from app.ai import source_currency as sc

EVIDENCE = ("verified snapshot chroma_data_20261017T024819Z (civil_collection, __ident_v1, __ident_v2: "
            "identical counts per source file); app/ai/data/corpus_instruments.json")

PUNJAB = "punjab"

# key -> held_for (jurisdictions whose text the corpus holds, by provenance),
#        sources (source_file -> jurisdiction), chunks (per collection), title.
REGISTRY: dict[str, dict] = {
    "cpc": {
        "title": "Code of Civil Procedure, 1908",
        "short": "the Code of Civil Procedure",
        "short_ur": "ضابطہ دیوانی",
        "sources": dict(sc.CPC_SOURCES),       # Punjab Code consolidation (sha256 528384…)
        "held_for": {PUNJAB},
        "chunks": 1967,
    },
    "pre_emption": {
        "title": "Punjab Pre-emption Act, 1991",
        "short": "pre-emption law",
        "short_ur": "حق شفع کا قانون",
        "sources": {"punjab-pre-emption-act-1991.pdf": PUNJAB,                         # 50 chunks
                    "punjab-pre-emption-removal-of-doubts-ordinance-1972.pdf": PUNJAB},  # 10 chunks
        "held_for": {PUNJAB},
        "chunks": 60,
    },
    "rented_premises": {
        "title": "Punjab Rented Premises Act, 2009",
        "short": "rented-premises (tenant eviction) law",
        "short_ur": "کرایہ داری (بے دخلی) کا قانون",
        "sources": {"punjab-rented-premises-act-2009.pdf": PUNJAB},                     # 61 chunks
        "held_for": {PUNJAB},
        "chunks": 61,
    },
    "specific_relief": {
        # 0 chunks in every collection and absent from corpus_instruments.json.
        "title": "Specific Relief Act, 1877",
        "short": "the Specific Relief Act",
        "short_ur": "قانون دادرسی خاص",
        "sources": {},
        "held_for": set(),
        "chunks": 0,
    },
}

# Statute labels that identify a registered authority even when a chunk's
# source_file is missing (e.g. a fixture or an exact-lookup row).
_STATUTE_KEY = [
    (re.compile(r"(?i)pre-?emption"), "pre_emption"),
    (re.compile(r"(?i)rented\s+premises"), "rented_premises"),
    (re.compile(r"(?i)specific\s+relief"), "specific_relief"),
]


def chunk_authority(chunk: dict) -> tuple[str, str] | None:
    """(registry key, jurisdiction by provenance) for a chunk of a registered
    authority; "unverified" for an unregistered source of one; None otherwise."""
    c = chunk or {}
    statute = str(c.get("statute") or "")
    src = str(c.get("source_file") or "").strip().lower()
    if sc.is_cpc(statute):
        return "cpc", REGISTRY["cpc"]["sources"].get(src, "unverified")
    for key, entry in REGISTRY.items():
        if src and src in entry["sources"]:
            return key, entry["sources"][src]
    for rx, key in _STATUTE_KEY:
        if rx.search(statute):
            return key, REGISTRY[key]["sources"].get(src, "unverified")
    return None


def own_jurisdiction(province: str | None, basis: str | None = None, inferred: bool = False) -> str | None:
    """The CONFIRMED jurisdiction, or None. Unknown or model-inferred is never Punjab."""
    scope = sc.cpc_scope(province, basis, inferred)
    if scope == sc.SCOPE_UNKNOWN:
        return None
    return PUNJAB if scope == sc.SCOPE_PUNJAB else (province or "").strip().lower() or None


def available(key: str, province: str | None, basis: str | None = None, inferred: bool = False) -> bool:
    own = own_jurisdiction(province, basis, inferred)
    return own is not None and own in REGISTRY[key]["held_for"]


# ── requirement detection (conservative; see the negative controls in tests) ──

def _rx(*patterns: str) -> list[re.Pattern]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


_DETECT: dict[str, list[re.Pattern]] = {
    "pre_emption": _rx(
        r"\bpre-?emption\b(?!\s*-?\s*(?:strike|attack|war))",   # "pre-emptive" never matches (\b)
        r"\bpre-?emptor\b",
        r"\bhaq[- ]?(?:e|i)?[- ]?shuf(?:a|aa|ah)\b", r"\bshuf(?:a|aa)\s+(?:ka|ki)\b",
        r"\btalb[- ]?(?:e|i)?[- ]?(?:muwathibat|muwasibat|ishhad|khusumat)\b",
        r"حق\s*شف[عه]", r"شفع[ہه]?\s*(?:کا|کی)", r"طلب\s*مواثبت",
    ),
    "rented_premises": _rx(
        r"\brented\s+premises\b", r"\brent\s+(?:controller|tribunal)\b",
        r"\b(?:evict(?:ion|ed|ing)?|eject(?:ment|ed|ing)?)\s+(?:of\s+)?(?:the\s+|a\s+|my\s+|our\s+|his\s+|her\s+)?tenants?\b",
        r"\b(?:evict|eject)\s+(?:him|her|them)\b.{0,40}\b(?:tenant|rent)\b",
        r"\btenants?\b.{0,60}\b(?:evict(?:ion|ed)?|eject(?:ment|ed)?)\b",
        r"\bkiray[ae]?\s*dar\b.{0,40}\bbe\s*dakh?li\b", r"\bbe\s*dakh?li\b.{0,40}\bkiray[ae]?\s*dar\b",
        r"کرای[ہه]\s*دار.{0,30}بے\s*دخل", r"بے\s*دخل.{0,30}کرای[ہه]\s*دار",
    ),
    "specific_relief": _rx(
        r"\bspecific\s+relief\b", r"\bspecific\s+performance\b",
        r"تعمیل\s*خاص", r"قانون\s*دادرسی\s*خاص",
    ),
}


def required(text: str) -> dict[str, list[str]]:
    """{registry key: [matched forms]} for every registered authority the text
    clearly requires. CPC uses the batch-9 detector (explicit + precise phrases)."""
    t = text or ""
    out: dict[str, list[str]] = {}
    cpc = sc.cpc_requirement(t)
    if cpc["required"]:
        out["cpc"] = cpc["explicit"] + cpc["procedural"]
    for key, patterns in _DETECT.items():
        hits = [m.group(0) for rx in patterns for m in [rx.search(t)] if m]
        if hits:
            out[key] = hits
    return out


# Other law the question itself names, beyond the registered authorities --
# a mixed question keeps that part.
_REGISTERED_NAME = re.compile(r"(?i)civil\s+procedure|pre-?emption|rented\s+premises|specific\s+relief")


# A limitation / time-limit issue is answerable from the Limitation Act, which
# the corpus holds -- "limitation period for specific performance" keeps that
# part (mixed) instead of being refused whole.
_LIMITATION_ISSUE = re.compile(
    r"(?i)\blimitation\s+(?:period|act)\b|\bperiod\s+of\s+limitation\b|\btime[- ]?(?:limit|bar(?:red)?)\b|"
    r"\bwithin\s+how\s+(?:long|many\s+(?:days|months|years))\b|\bmi[iy]?a{1,2}d\b|میعاد|مدت\s*سماعت")


def other_law(text: str) -> list[str]:
    named = sc.cpc_requirement(text or "")["other_law"]
    out = {n for n in named if not _REGISTERED_NAME.search(n)}
    if _LIMITATION_ISSUE.search(text or ""):
        out.add("Limitation Act 1908 (limitation issue)")
    return sorted(out)


def assess(text: str, province: str | None, basis: str | None = None, inferred: bool = False) -> dict:
    """{"required": {key: forms}, "unavailable": [keys], "other_law": [...],
        "own": jurisdiction|None}."""
    req = required(text)
    return {"required": req,
            "unavailable": sorted(k for k in req if not available(k, province, basis, inferred)),
            "other_law": other_law(text),
            "own": own_jurisdiction(province, basis, inferred)}


def chunk_admissible(chunk: dict, own: str | None) -> bool | None:
    """None for a non-registered chunk (the caller's ordinary rules apply);
    otherwise whether its provenance jurisdiction is this matter's own."""
    a = chunk_authority(chunk)
    if a is None:
        return None
    return own is not None and a[1] == own


def unavailable_reason(keys: list[str], province: str | None, basis: str | None = None,
                       inferred: bool = False) -> str:
    names = ", ".join(REGISTRY[k]["short"] for k in keys)
    if own_jurisdiction(province, basis, inferred) is None:
        return (f"the question needs {names}, the province of this matter is not confirmed, and the text "
                "held is not verified for every province -- add the province")
    held = [k for k in keys if REGISTRY[k]["held_for"]]
    where = sc.province_label(province)
    if held and len(held) == len(keys):
        return f"the question needs {names}, and the only text held is the Punjab version, which is not verified for {where}"
    return f"the question needs {names}, which the law library does not hold for {where}"


def limitation_message(keys: list[str], province: str | None, basis: str | None = None,
                       inferred: bool = False, urdu: bool = False, answered_rest: bool = False) -> str:
    """The honest, user-facing limitation (client Chat and lawyer Research)."""
    unknown = own_jurisdiction(province, basis, inferred) is None
    if urdu:
        names = "، ".join(REGISTRY[k]["short_ur"] for k in keys)
        if unknown:
            return (f"آپ کا سوال {names} سے متعلق ہے۔ آپ کا صوبہ معلوم نہیں، اور ہمارے پاس یہ قانون ہر صوبے کے لیے "
                    "موجود نہیں۔ براہ کرم اپنا صوبہ بتائیں۔")
        lead = "باقی حصے کا جواب اوپر دیا گیا ہے۔ " if answered_rest else ""
        return (f"{lead}{names} ہماری قانونی لائبریری میں {sc.province_label(province)} کے لیے موجود نہیں، "
                "اس لیے اس حصے کا قانونی جواب نہیں دیا جا رہا۔ اپنے صوبے کے کسی وکیل سے مشورہ کریں۔")
    names = ", ".join(REGISTRY[k]["short"] for k in keys)
    if unknown:
        return (f"Your question turns on {names}. Your province is not confirmed, and that law is not held "
                "here for every province, so no legal answer is given yet. Please tell me your province.")
    lead = "The rest of your question is answered above. " if answered_rest else ""
    return (f"{lead}Your question turns on {names}, which is not held in this law library for "
            f"{sc.province_label(province)}, so that part is not answered from other law. "
            "A lawyer in your province should advise on it.")


# ── client Chat / lawyer Research: BEFORE the answer writer sees any law ────

def _question(state: dict) -> str:
    from app.ai.response_policy import presentation_base_query
    return presentation_base_query(state) or state.get("query") or ""


def assess_state(state: dict) -> dict:
    return assess(_question(state), state.get("province"), state.get("jurisdiction_basis"),
                  bool(state.get("province_inferred")))


def _tool_ok(item, own: str | None) -> bool:
    return not isinstance(item, dict) or chunk_admissible(item, own) is not False


def _filter_tools(tool_results: list[dict], own: str | None) -> tuple[list[dict], int]:
    """Drop lookup text of a registered authority this matter does not hold."""
    kept, dropped = [], 0
    for call in tool_results or []:
        result = (call or {}).get("result")
        if isinstance(result, dict):
            if not _tool_ok(result, own):
                dropped += 1
                continue
        elif isinstance(result, list):
            items = [r for r in result if _tool_ok(r, own)]
            if len(items) != len(result):
                dropped += len(result) - len(items)
                if not items:
                    continue
                call = {**call, "result": items}
        kept.append(call)
    return kept, dropped


def _engine_answer(tool_results: list[dict]) -> bool:
    from app.ai.graph.edges import _has_engine_answer
    return _has_engine_answer({"tool_results": tool_results})


def chat_gate(state: dict) -> dict | None:
    """None when the question needs no unavailable authority. Otherwise either
    an honest refusal (nothing else in the question is answerable) or, for a
    mixed question, the evidence with the unavailable authority's text removed
    plus `authority_limits` for the rider and the final notice."""
    a = assess_state(state)
    if not a["unavailable"]:
        return None
    own = a["own"]
    chunks = [c for c in state.get("reranked_chunks") or [] if chunk_admissible(c, own) is not False]
    tools, tools_dropped = _filter_tools(state.get("tool_results") or [], own)
    limits = {"unavailable": a["unavailable"], "required": a["required"], "other_law": a["other_law"],
              "own": own, "province": state.get("province") or None,
              "chunks_dropped": len(state.get("reranked_chunks") or []) - len(chunks),
              "tools_dropped": tools_dropped, "question": _question(state)[:300]}
    if not a["other_law"] and not _engine_answer(tools):
        urdu = state.get("language") == "ur"
        return {"arbitration_output": "refuse", "arbitration_source": "authority_unavailable",
                "arbitration_confidence": 0.0,
                "refusal_reason": limitation_message(a["unavailable"], state.get("province"),
                                                     state.get("jurisdiction_basis"),
                                                     bool(state.get("province_inferred")), urdu=urdu),
                "refusal_redirect": "", "refusal_kind": sc.SOURCE_UNAVAILABLE,
                "reranked_chunks": [], "tool_results": tools, "authority_limits": limits}
    return {"reranked_chunks": chunks, "tool_results": tools, "authority_limits": limits}


def generation_rider(limits: dict | None, urdu: bool = False) -> str:
    if not limits or not limits.get("unavailable"):
        return ""
    if urdu:
        names = "، ".join(REGISTRY[k]["short_ur"] for k in limits["unavailable"])
        return (f"\n\nسوال کا وہ حصہ جو {names} پر منحصر ہے، اس کا جواب نہ دیں: یہ قانون اس صوبے کے لیے دستیاب نہیں۔ "
                "اسے کسی دوسرے قانون سے بیان نہ کریں۔ صرف باقی حصے کا جواب دیں۔")
    names = ", ".join(REGISTRY[k]["short"] for k in limits["unavailable"])
    return (f"\n\nDo NOT answer the part of the question that turns on {names}: that law is not held for "
            "this matter's province. Do not state it from memory or from any other law provided. "
            "Answer only the remaining part.")


def final_notice(state: dict) -> str | None:
    """The limitation shown on the FINAL visible answer (fresh, follow-up or
    cache hit). None when the question needs no unavailable authority."""
    limits = state.get("authority_limits")
    keys = (limits or {}).get("unavailable") or assess_state(state)["unavailable"]
    if not keys:
        return None
    return limitation_message(keys, state.get("province"), state.get("jurisdiction_basis"),
                              bool(state.get("province_inferred")), urdu=state.get("language") == "ur",
                              answered_rest=True)
