"""The legal-source registry: one record per source document, with enough
provenance to answer "may this be retrieved, as what, and is it in force?".

Pure code; see the package docstring. Nothing here decides legal correctness:
it records what has and has not been VERIFIED, and refuses to report more.

THREE RULES THE CODE ENFORCES

1. Lanes are not interchangeable. A statute, a court practice rule, a judgment,
   a regulator circular, an official form and a "how to complain" page are
   different kinds of authority. Each source type maps to exactly one retrieval
   lane, and some types (verification services, evaluation datasets) map to
   none: they are never legal authority.
2. "In force" is earned. A record reports `in_force_per_registry` only when its
   commencement was verified from an official notification or the Act itself,
   the date has arrived, nothing has ended it, and the verification is not
   stale. Otherwise it says which of those is missing -- an enacted Act whose
   commencement notification is unconfirmed is `commencement_unverified`.
3. Provinces do not overwrite the Federation. A provincial amendment is its own
   record that names what it amends; it can never share an id with the federal
   text, and the federal record is never edited to absorb it.
4. One failed fetch is not "missing". A URL's status is derived from its
   recorded checks: a 403 is `blocked`, a timeout is `timeout`, and a 404 is
   only `not_found_confirmed` after repeated 404s at least a day apart with no
   success since. A consolidated informational text (Pakistan Code, Punjab
   Code) is also recorded as such: it is not its Gazette authority.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from urllib.parse import urlparse

# ── vocabularies ─────────────────────────────────────────────────────────────

JURISDICTIONS = frozenset({
    "federal", "punjab", "sindh", "kp", "balochistan", "islamabad_capital_territory",
    "gilgit_baltistan", "ajk",
})

# source_type -> retrieval lane. None = never retrieved as legal authority.
LANE_OF: dict[str, str | None] = {
    "statute_consolidated": "law",
    "statute_original": "law",
    "subordinate_rules": "law",
    "constitution": "law",
    "amendment_instrument": "version_history",
    "commencement_notification": "version_history",
    "court_rules": "court_rules",
    "judgment": "judgments",
    "tribunal_decision": "decisions",
    "ombudsman_decision": "decisions",
    "regulator_decision": "decisions",
    "regulator_circular": "regulatory",
    "sro": "regulatory",
    "court_form": "forms",
    "official_form": "forms",
    "service_guide": "service",
    "verification_service": None,
    "evaluation_dataset": None,
}
SOURCE_TYPES = frozenset(LANE_OF)

# What a retrieved item may be presented AS. Ordered strongest first for
# display, but lanes are filtered, not merged: a form never outranks a statute
# because they are never in the same result list.
AUTHORITY_OF: dict[str, str] = {
    "constitution": "primary_law",
    "statute_consolidated": "primary_law",
    "statute_original": "primary_law",
    "subordinate_rules": "subordinate_law",
    "amendment_instrument": "primary_law",
    "commencement_notification": "primary_law",
    "court_rules": "court_rules",
    "judgment": "precedent",                 # binding scope needs the court + a lawyer's review
    "tribunal_decision": "decision",
    "ombudsman_decision": "decision_non_precedential",
    "regulator_decision": "decision_non_precedential",
    "regulator_circular": "regulatory_instrument",
    "sro": "regulatory_instrument",
    "court_form": "form_not_proof_of_completeness",
    "official_form": "form_not_proof_of_completeness",
    "service_guide": "service_information",
    "verification_service": "not_legal_authority",
    "evaluation_dataset": "not_legal_authority",
}

# Courts and forums carry their own identity: FCCP and the Federal Shariat
# Court are NOT the Supreme Court, and an ombudsman is not a court.
FORUMS = frozenset({
    "SC", "FCCP", "FSC", "LHC", "SHC", "PHC", "BHC", "IHC",
    "NIRC", "FOSPAH", "FTO", "BANKING_MOHTASIB", "NEPRA", "CCP", "SBP", "SECP", "FBR",
})

COMMENCEMENT_EVIDENCE = frozenset({
    "commencement_notification",   # a gazetted notification fixing the date
    "on_enactment_clause",         # the Act says it comes into force at once / on a date
    "unverified",
    "not_notified",                # the Act needs a notification and none is confirmed
    "not_applicable",              # forms, service data, datasets
})

URL_STATUS = frozenset({
    "ok",                      # latest check succeeded
    "moved",                   # official redirect to a different page (recorded, re-pointed)
    "blocked",                 # 401/403/429: exists, refuses automated access
    "timeout",                 # no answer in time -- says nothing about existence
    "not_found_unconfirmed",   # 404/410, but not yet repeated a day apart
    "not_found_confirmed",     # repeated 404/410 >= 1 day apart, no success since
    "error",                   # DNS/TLS/5xx
    "unverified",              # never checked
})
_CONFIRM_404_AFTER_SECONDS = 24 * 3600

# What the text at the URL IS -- separate from whether the law is in force.
TEXT_AUTHORITY = frozenset({
    "gazette",                              # the Gazette notification itself
    "official_enacted_text",                # the Act as passed/assented on a legislature site
    "official_consolidated_informational",  # Pakistan Code / Punjab Code: "Gazette governs"
    "official_bill_record",                 # a bill page; not law
    "official_listing",                     # an index or feed page
    "secondary_lead",                       # law firm, news, encyclopaedia: a lead only
    "unverified",
})

LICENCE_STATUS = frozenset({
    "public_official_no_restriction_stated",
    "public_official_information_only",   # e.g. Pakistan Code: "information purposes only ... refer to Gazette"
    "restricted_download_without_permission",
    "all_rights_reserved_unclear_reuse",
    "third_party_licence",
    "unknown",
})
_INGESTIBLE_LICENCE = frozenset({"public_official_no_restriction_stated", "public_official_information_only"})

# Official domains by suffix. A URL elsewhere can be a lead, never a source.
OFFICIAL_DOMAIN_SUFFIXES = (".gov.pk", ".gos.pk", ".gob.pk", ".org.pk")
# .org.pk is not inherently official: only these .org.pk hosts are.
_OFFICIAL_ORG_PK = frozenset({"nepra.org.pk", "sbp.org.pk", "sunwai.sbp.org.pk", "pbbarcouncil.com",
                              "ibc.org.pk"})

_SOURCE_ID = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
DEFAULT_RECHECK_DAYS = {"service_guide": 90, "official_form": 180, "court_form": 180}
DEFAULT_RECHECK_DAYS_OTHER = 365


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    title: str
    issuer: str
    source_type: str
    jurisdiction: str
    official_url: str
    verification_date: date | None = None
    url_status: str = "unverified"             # ok | moved | not_found | blocked | unverified
    country: str = "PK"
    forum: str | None = None
    document_hash: str | None = None           # sha256 of the exact bytes retrieved
    publication_date: date | None = None
    commencement_date: date | None = None
    commencement_evidence: str = "unverified"
    effective_to: date | None = None
    amendment_of: str | None = None
    superseded_by: str | None = None
    instrument_number: str | None = None       # "Act No. II of 2025", "S.R.O. 169(I)/2025"
    licence_status: str = "unknown"
    licence_note: str | None = None
    ocr_quality: str | None = None             # text_layer | ocr_ok | ocr_poor | image_only
    blockers: tuple[str, ...] = field(default_factory=tuple)
    recheck_after_days: int | None = None
    # Each: {"checked_at": ISO datetime (UTC), "result": HTTP code | "timeout" | "error",
    #        "method": "HEAD"/"GET", "note": ...}. url_status must agree with them.
    url_checks: tuple[dict, ...] = field(default_factory=tuple)
    text_authority: str = "unverified"
    gazette_reference: str | None = None       # e.g. "Gazette of Pakistan, Extra., 13 Nov 2025"

    @property
    def lane(self) -> str | None:
        return LANE_OF.get(self.source_type)

    @property
    def authority(self) -> str:
        return AUTHORITY_OF.get(self.source_type, "not_legal_authority")


def _check_kind(result) -> str:
    if result == "timeout":
        return "timeout"
    if not isinstance(result, int):
        return "error"
    if 200 <= result < 300:
        return "ok"
    if result in (404, 410):
        return "not_found"
    if result in (401, 403, 429):
        return "blocked"
    return "error"


def url_status_from_checks(checks) -> str:
    """The status recorded checks support -- never stronger than them.

    The LATEST check decides, except that a 404 becomes `not_found_confirmed`
    only when every check since the last success is a 404/410 and those 404s
    span at least a day (and there are two or more of them). A timeout or 403
    between them breaks the run: that is not proof of absence.
    """
    if not checks:
        return "unverified"
    ordered = sorted(checks, key=lambda c: datetime.fromisoformat(str(c["checked_at"]).replace("Z", "+00:00")))
    kind = _check_kind(ordered[-1]["result"])
    if kind != "not_found":
        return kind
    run = []
    for c in reversed(ordered):
        if _check_kind(c["result"]) != "not_found":
            break
        run.append(datetime.fromisoformat(str(c["checked_at"]).replace("Z", "+00:00")))
    span = (run[0] - run[-1]).total_seconds()
    return "not_found_confirmed" if len(run) >= 2 and span >= _CONFIRM_404_AFTER_SECONDS         else "not_found_unconfirmed"


def is_official_url(url: str) -> bool:
    host = (urlparse(url or "").hostname or "").lower()
    if not host or urlparse(url).scheme != "https":
        return False
    if host.endswith(".org.pk") or host.endswith(".com"):
        return host in _OFFICIAL_ORG_PK or any(host.endswith("." + h) for h in _OFFICIAL_ORG_PK)
    return host.endswith(OFFICIAL_DOMAIN_SUFFIXES)


def validate(rec: SourceRecord, *, known_ids: set[str] | None = None) -> list[str]:
    """Problems with a record. Empty means structurally sound -- not legally correct."""
    p: list[str] = []
    if not _SOURCE_ID.match(rec.source_id or ""):
        p.append("source_id: lowercase words joined by . _ or -")
    if rec.source_type not in SOURCE_TYPES:
        p.append(f"source_type: unknown {rec.source_type!r}")
    if rec.country != "PK":
        p.append("country: only Pakistani sources belong here (India also has a 'Punjab')")
    if rec.jurisdiction not in JURISDICTIONS:
        p.append(f"jurisdiction: unknown {rec.jurisdiction!r}")
    if rec.forum is not None and rec.forum not in FORUMS:
        p.append(f"forum: unknown {rec.forum!r}")
    if rec.source_type in {"judgment", "court_rules", "court_form", "tribunal_decision",
                           "ombudsman_decision", "regulator_decision"} and not rec.forum:
        p.append("forum: required for court, tribunal and ombudsman sources")
    if rec.lane is not None and not is_official_url(rec.official_url):
        p.append("official_url: not an https URL on an official domain")
    if rec.commencement_evidence not in COMMENCEMENT_EVIDENCE:
        p.append(f"commencement_evidence: unknown {rec.commencement_evidence!r}")
    if rec.licence_status not in LICENCE_STATUS:
        p.append(f"licence_status: unknown {rec.licence_status!r}")
    if rec.commencement_date and rec.commencement_evidence in {"unverified", "not_notified"}:
        p.append("commencement_date given without verified commencement evidence")
    if rec.source_type == "amendment_instrument":
        if not rec.amendment_of:
            p.append("amendment_of: an amendment must name what it amends")
        elif rec.amendment_of == rec.source_id:
            p.append("amendment_of: cannot amend itself")
    if rec.amendment_of and known_ids is not None and rec.amendment_of not in known_ids:
        p.append(f"amendment_of: {rec.amendment_of!r} is not in the registry")
    if rec.document_hash and not re.fullmatch(r"[0-9a-f]{64}", rec.document_hash):
        p.append("document_hash: sha256 hex of the retrieved bytes")
    if rec.url_status not in URL_STATUS:
        p.append(f"url_status: unknown {rec.url_status!r}")
    elif rec.url_checks and url_status_from_checks(rec.url_checks) != rec.url_status:
        p.append(f"url_status: {rec.url_status!r} is not what its checks show "
                 f"({url_status_from_checks(rec.url_checks)!r})")
    if rec.text_authority not in TEXT_AUTHORITY:
        p.append(f"text_authority: unknown {rec.text_authority!r}")
    if rec.text_authority == "gazette" and not rec.gazette_reference:
        p.append("gazette_reference: a Gazette text must say which Gazette issue")
    return p


def provincial_variant_conflicts(records: list[SourceRecord]) -> list[str]:
    """A provincial amendment of a federal text must be its own record."""
    by_id = {r.source_id: r for r in records}
    out = []
    for r in records:
        target = by_id.get(r.amendment_of or "")
        if target and target.jurisdiction == "federal" and r.jurisdiction != "federal" \
                and r.source_type not in {"amendment_instrument"}:
            out.append(f"{r.source_id}: a provincial change to a federal text must be an amendment_instrument")
    return out


def ingestion_blockers(rec: SourceRecord) -> list[str]:
    """Why this record may not be ingested as legal authority. Empty = may be piloted."""
    out = list(rec.blockers)
    if rec.lane is None:
        out.append(f"{rec.source_type} is never retrieved as legal authority")
    if rec.url_status != "ok":
        out.append(f"official URL not verified ({rec.url_status})")
    if rec.licence_status not in _INGESTIBLE_LICENCE:
        out.append(f"licence/access: {rec.licence_status}")
    if not rec.document_hash and rec.lane in {"law", "version_history", "court_rules"}:
        out.append("no hash of the exact document retrieved")
    return out


def temporal_status(rec: SourceRecord, on: date, today: date | None = None) -> str:
    """Whether the registry can say this source is in force on `on`.

    in_force_per_registry      commencement verified, started, not ended, check fresh
    not_yet_commenced          verified commencement date is after `on`
    commencement_unverified    enacted/published, but when it starts is not established
    no_longer_in_force         ended (effective_to) or superseded before `on`
    verification_stale         would be in force, but the check is older than its recheck period
    not_applicable             forms, service data, datasets: not "in force" at all
    """
    if rec.commencement_evidence == "not_applicable" or rec.lane in {None, "service", "forms"}:
        return "not_applicable"
    if rec.effective_to and on > rec.effective_to:
        return "no_longer_in_force"
    if rec.commencement_evidence not in {"commencement_notification", "on_enactment_clause"} \
            or rec.commencement_date is None:
        return "commencement_unverified"
    if on < rec.commencement_date:
        return "not_yet_commenced"
    if rec.verification_date is None:
        return "verification_stale"
    period = rec.recheck_after_days or DEFAULT_RECHECK_DAYS.get(rec.source_type, DEFAULT_RECHECK_DAYS_OTHER)
    if ((today or on) - rec.verification_date).days > period:
        return "verification_stale"
    return "in_force_per_registry"


def service_status(rec: SourceRecord, today: date) -> str:
    """Service data (complaint routes, legal aid) is fresh or stale; it is never 'in force'."""
    if rec.verification_date is None:
        return "unverified"
    period = rec.recheck_after_days or DEFAULT_RECHECK_DAYS.get(rec.source_type, DEFAULT_RECHECK_DAYS_OTHER)
    return "fresh" if (today - rec.verification_date).days <= period else "stale"


def lane_filter(lane: str, records: list[SourceRecord], *, jurisdiction: str | None,
                on: date | None = None, today: date | None = None) -> list[SourceRecord]:
    """Records retrievable in one lane for one jurisdiction (federal law applies
    everywhere; a provincial record only in its province). With `on`, only
    records the registry can call in force on that date."""
    out = []
    for r in records:
        if r.lane != lane:
            continue
        if jurisdiction and r.jurisdiction not in {jurisdiction, "federal"}:
            continue
        if on is not None and lane in {"law", "version_history", "court_rules", "regulatory"} \
                and temporal_status(r, on, today) != "in_force_per_registry":
            continue
        out.append(r)
    return out


def from_dict(d: dict) -> SourceRecord:
    """Build a record from registry JSON (ISO dates)."""
    def _d(k):
        v = d.get(k)
        return date.fromisoformat(v) if v else None
    keep = {k: d[k] for k in ("source_id", "title", "issuer", "source_type", "jurisdiction",
                              "official_url", "url_status", "country", "forum", "document_hash",
                              "commencement_evidence", "amendment_of", "superseded_by",
                              "instrument_number", "licence_status", "licence_note", "ocr_quality",
                              "recheck_after_days", "text_authority", "gazette_reference")
            if k in d and d[k] is not None}
    return SourceRecord(**keep,
                        verification_date=_d("verification_date"), publication_date=_d("publication_date"),
                        commencement_date=_d("commencement_date"), effective_to=_d("effective_to"),
                        blockers=tuple(d.get("blockers") or ()),
                        url_checks=tuple(d.get("url_checks") or ()))
