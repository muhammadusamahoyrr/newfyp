"""Source registry rules (app/ai/legal_sources/registry.py). Pure.

Pins: lanes never mix; "in force" only on verified commencement; a provincial
change to a federal text is its own amendment record; service data is fresh or
stale, never in force; verification services and datasets are never authority.
"""
from datetime import date

from app.ai.legal_sources.registry import (
    SourceRecord, ingestion_blockers, is_official_url, lane_filter,
    provincial_variant_conflicts, service_status, temporal_status, validate,
)

TODAY = date(2026, 10, 16)
SHA = "a" * 64


def rec(**kw):
    base = dict(source_id="pk.fed.example", title="Example Act", issuer="Ministry of Law and Justice",
                source_type="statute_consolidated", jurisdiction="federal",
                official_url="https://pakistancode.gov.pk/x.pdf", url_status="ok",
                verification_date=TODAY, document_hash=SHA,
                commencement_evidence="on_enactment_clause", commencement_date=date(1870, 4, 1),
                licence_status="public_official_information_only")
    base.update(kw)
    return SourceRecord(**base)


# ── temporal status ──────────────────────────────────────────────────────────

def test_a_verified_commencement_is_in_force():
    assert temporal_status(rec(), TODAY) == "in_force_per_registry"


def test_an_enacted_code_without_a_confirmed_commencement_is_never_in_force():
    labour = rec(source_id="pk.punjab.labour-code-2026", jurisdiction="punjab",
                 official_url="https://punjablaws.gov.pk/x", commencement_evidence="not_notified",
                 commencement_date=None, publication_date=date(2026, 2, 10))
    assert temporal_status(labour, TODAY) == "commencement_unverified"
    # A date typed in without evidence does not change that, and is flagged.
    guessed = rec(commencement_evidence="unverified", commencement_date=date(2026, 6, 1))
    assert temporal_status(guessed, TODAY) == "commencement_unverified"
    assert any("without verified commencement" in p for p in validate(guessed))


def test_future_ended_and_stale():
    assert temporal_status(rec(commencement_date=date(2027, 1, 1),
                               commencement_evidence="commencement_notification"), TODAY) == "not_yet_commenced"
    assert temporal_status(rec(effective_to=date(2025, 12, 31)), TODAY) == "no_longer_in_force"
    old = rec(verification_date=date(2025, 1, 1))
    assert temporal_status(old, TODAY) == "verification_stale"
    assert temporal_status(rec(verification_date=None), TODAY) == "verification_stale"


def test_forms_and_service_data_are_never_in_force():
    form = rec(source_id="pk.ihc.form.x", source_type="court_form", forum="IHC",
               commencement_evidence="not_applicable", commencement_date=None,
               official_url="https://mis.ihc.gov.pk/frmDownloads")
    assert temporal_status(form, TODAY) == "not_applicable"
    guide = rec(source_id="pk.svc.nccia", source_type="service_guide", official_url="https://nccia.gov.pk/faqs.php",
                commencement_evidence="not_applicable", commencement_date=None,
                verification_date=date(2026, 6, 1))
    assert service_status(guide, TODAY) == "stale"            # 90-day recheck
    assert service_status(rec(source_type="service_guide", verification_date=date(2026, 9, 1)), TODAY) == "fresh"


# ── lanes and authority ──────────────────────────────────────────────────────

def test_each_type_has_one_lane_and_some_have_none():
    assert rec().lane == "law"
    assert rec(source_type="judgment", forum="FCCP").lane == "judgments"
    assert rec(source_type="ombudsman_decision", forum="FTO").authority == "decision_non_precedential"
    assert rec(source_type="court_form", forum="IHC").authority == "form_not_proof_of_completeness"
    assert rec(source_type="verification_service").lane is None
    assert rec(source_type="evaluation_dataset").lane is None
    assert "never retrieved as legal authority" in " ".join(
        ingestion_blockers(rec(source_type="evaluation_dataset")))


def test_lane_filter_keeps_lanes_apart_and_respects_province_and_date():
    fed = rec()
    punjab_amend = rec(source_id="pk.punjab.cpc-amend", source_type="amendment_instrument",
                       jurisdiction="punjab", amendment_of="pk.fed.example",
                       official_url="https://punjablaws.gov.pk/a")
    sindh_law = rec(source_id="pk.sindh.x", jurisdiction="sindh", official_url="https://sindhlaws.gov.pk/x")
    unstarted = rec(source_id="pk.punjab.labour", jurisdiction="punjab", commencement_evidence="not_notified",
                    commencement_date=None, official_url="https://punjablaws.gov.pk/l")
    judgment = rec(source_id="pk.fccp.j1", source_type="judgment", forum="FCCP",
                   official_url="https://www.fccp.gov.pk/judgements")
    allr = [fed, punjab_amend, sindh_law, unstarted, judgment]
    law_pb = lane_filter("law", allr, jurisdiction="punjab", on=TODAY)
    assert [r.source_id for r in law_pb] == ["pk.fed.example"], "Sindh law, an amendment, an unstarted code or a judgment leaked"
    assert [r.source_id for r in lane_filter("version_history", allr, jurisdiction="punjab")] == ["pk.punjab.cpc-amend"]
    assert lane_filter("version_history", allr, jurisdiction="sindh") == []


# ── validation ───────────────────────────────────────────────────────────────

def test_courts_need_a_forum_and_fccp_fsc_are_distinct_from_the_supreme_court():
    assert any("forum" in p for p in validate(rec(source_type="judgment", forum=None)))
    for forum in ("FCCP", "FSC", "SC", "IHC"):
        assert validate(rec(source_type="judgment", forum=forum)) == []
    assert any("forum" in p for p in validate(rec(source_type="judgment", forum="SUPREME")))


def test_amendments_name_their_target_and_provinces_never_overwrite_the_federation():
    assert any("must name" in p for p in validate(rec(source_type="amendment_instrument")))
    assert any("cannot amend itself" in p for p in validate(
        rec(source_type="amendment_instrument", amendment_of="pk.fed.example")))
    fed = rec()
    good = rec(source_id="pk.punjab.cpc-amend", source_type="amendment_instrument",
               jurisdiction="punjab", amendment_of="pk.fed.example", official_url="https://punjablaws.gov.pk/a")
    bad = rec(source_id="pk.punjab.cpc-consolidated", jurisdiction="punjab",
              amendment_of="pk.fed.example", official_url="https://punjablaws.gov.pk/b")
    assert provincial_variant_conflicts([fed, good]) == []
    assert provincial_variant_conflicts([fed, bad]) == [
        "pk.punjab.cpc-consolidated: a provincial change to a federal text must be an amendment_instrument"]
    assert any("not in the registry" in p for p in validate(good, known_ids={"pk.other"}))


def test_only_official_https_urls_are_sources():
    assert is_official_url("https://pakistancode.gov.pk/english/")
    assert is_official_url("https://dglabour.gos.pk/laws-Policies/")
    assert is_official_url("https://balochistancode.gob.pk/")
    assert is_official_url("https://nepra.org.pk/")
    assert not is_official_url("http://pakistancode.gov.pk/")              # not https
    assert not is_official_url("https://khalidzafar.com/laws-of-pakistan/x")
    assert not is_official_url("https://clr.org.pk/Labour-Laws/x.pdf")      # .org.pk is not enough
    assert not is_official_url("https://www.punjabassembly.gov.in/x.pdf")  # India
    assert any("Pakistani" in p for p in validate(rec(country="IN")))


def test_ingestion_needs_a_verified_url_a_usable_licence_and_a_hash():
    assert ingestion_blockers(rec()) == []
    lhc = rec(source_id="pk.lhc.rules-orders.v3", source_type="court_rules", forum="LHC", jurisdiction="punjab",
              official_url="https://library.lhc.gov.pk/pdf/RulesAndOrders/volume3.pdf",
              licence_status="restricted_download_without_permission", document_hash=None)
    reasons = " | ".join(ingestion_blockers(lhc))
    assert "restricted_download_without_permission" in reasons and "no hash" in reasons
    assert "not verified" in " ".join(ingestion_blockers(rec(url_status="blocked")))


# ── the candidate registry file itself ───────────────────────────────────────

import json
from pathlib import Path

from app.ai.legal_sources.registry import from_dict

_REG = json.loads((Path(__file__).resolve().parents[1] / "data" / "legal_sources"
                   / "candidate_registry_v0.json").read_text(encoding="utf-8"))
_DOCS = [from_dict(d) for d in _REG["documents"]]
_BY_ID = {r.source_id: r for r in _DOCS}


def test_every_candidate_record_is_structurally_valid_and_ids_are_unique():
    ids = [r.source_id for r in _DOCS]
    assert len(ids) == len(set(ids))
    problems = {r.source_id: validate(r, known_ids=set(ids)) for r in _DOCS}
    assert {k: v for k, v in problems.items() if v} == {}
    assert provincial_variant_conflicts(_DOCS) == []


def test_every_family_a_to_g_is_represented():
    families = {d["family"] for d in _REG["documents"]} | {f["family"] for f in _REG["feeds"]}
    assert families >= set("ABCDEFG")


def test_the_registry_never_calls_an_unverified_commencement_current_law():
    assert temporal_status(_BY_ID["pk.punjab.labour-code-2026"], TODAY) == "commencement_unverified"
    assert temporal_status(_BY_ID["pk.fed.peca-2016"], TODAY) == "commencement_unverified"
    in_force = [r.source_id for r in _DOCS if temporal_status(r, TODAY) == "in_force_per_registry"]
    # The only commencements read from the documents themselves: the Court-Fees
    # Act's own clause, and the 27th Amendment Gazette's "come into force at once".
    assert in_force == ["pk.fed.court-fees-act-1870", "pk.fed.constitution-27th-amendment-2025"]
    assert ingestion_blockers(_BY_ID["pk.fed.court-fees-act-1870"]), "its currency blockers were dropped"


def test_known_blockers_stay_blocking():
    assert any("CONFLICT" in b for b in ingestion_blockers(_BY_ID["pk.fed.banking-companies-ordinance-82d"]))
    assert "licence/access: restricted_download_without_permission" in ingestion_blockers(_BY_ID["pk.lhc.rules-orders"])
    ds = _BY_ID["eval.zenodo.21672295"]
    assert ds.lane is None and ds.authority == "not_legal_authority"
    assert _BY_ID["pk.punjab.cpc-amendment-2018"].amendment_of == "pk.fed.cpc-1908"
    assert _BY_ID["pk.punjab.cpc-amendment-2018"].jurisdiction == "punjab"


def test_marketplace_verification_feeds_are_never_rag_sources():
    for f in _REG["feeds"]:
        if f["family"] == "F":
            assert "never RAG" in f["notes"]


# ── URL status is derived from recorded checks, never from one failed fetch ──

from app.ai.legal_sources.registry import URL_STATUS, url_status_from_checks  # noqa: E402


def _c(at, result):
    return {"checked_at": at, "result": result, "method": "HEAD"}


def test_one_404_is_not_confirmed_missing():
    assert url_status_from_checks([_c("2026-10-16T09:00:00Z", 404)]) == "not_found_unconfirmed"
    # Repeats the same day are still one occasion.
    assert url_status_from_checks([_c("2026-10-16T09:00:00Z", 404),
                                   _c("2026-10-16T13:35:00Z", 404)]) == "not_found_unconfirmed"


def test_repeated_404s_a_day_apart_with_no_success_since_are_confirmed():
    assert url_status_from_checks([_c("2026-10-15T09:00:00Z", 404),
                                   _c("2026-10-16T09:00:00Z", 410)]) == "not_found_confirmed"


def test_a_timeout_or_403_is_never_read_as_missing():
    assert url_status_from_checks([_c("2026-10-16T09:00:00Z", "timeout")]) == "timeout"
    assert url_status_from_checks([_c("2026-10-16T09:00:00Z", 403)]) == "blocked"
    # A timeout between two 404s breaks the run: the 404s no longer span a day.
    assert url_status_from_checks([_c("2026-10-14T09:00:00Z", 404), _c("2026-10-15T09:00:00Z", "timeout"),
                                   _c("2026-10-16T09:00:00Z", 404)]) == "not_found_unconfirmed"


def test_the_latest_success_wins_over_earlier_failures():
    # The KP Code case: a failed fetch, then reachable.
    assert url_status_from_checks([_c("2026-10-14T09:00:00Z", 404), _c("2026-10-15T09:00:00Z", 404),
                                   _c("2026-10-16T13:35:28Z", 200)]) == "ok"
    assert url_status_from_checks([]) == "unverified"


def test_a_record_cannot_claim_a_stronger_status_than_its_checks():
    bad = rec(url_status="not_found_confirmed", url_checks=(_c("2026-10-16T09:00:00Z", 404),))
    assert any("not what its checks show" in p for p in validate(bad))
    assert any("unknown 'not_found'" in p for p in validate(rec(url_status="not_found")))


def test_a_gazette_text_must_name_its_issue_and_a_consolidation_is_not_the_gazette():
    assert any("gazette_reference" in p for p in validate(rec(text_authority="gazette")))
    assert validate(rec(text_authority="gazette", gazette_reference="Gazette of Pakistan, Extra., 13 Nov 2025")) == []
    assert any("text_authority" in p for p in validate(rec(text_authority="official")))


def test_every_feed_and_document_status_agrees_with_its_recorded_checks():
    entries = _REG["feeds"] + _REG["documents"]
    entries += [u for e in entries for u in e.get("secondary_urls", [])]
    for e in entries:
        name = e.get("feed_id") or e.get("source_id") or e.get("url")
        assert e["url_status"] in URL_STATUS, name
        if e.get("url_checks"):
            assert url_status_from_checks(e["url_checks"]) == e["url_status"], name


def test_the_punjab_cpc_text_is_kept_apart_from_the_federal_record():
    pj, fed = _BY_ID["pk.punjab.cpc-1908-punjab-code"], _BY_ID["pk.fed.cpc-1908"]
    assert pj.jurisdiction == "punjab" and fed.jurisdiction == "federal"
    assert pj.text_authority == "official_consolidated_informational"
    assert pj.document_hash != fed.document_hash
    assert _BY_ID["pk.punjab.cpc-amendment-2018"].instrument_number == "Act XIV of 2018"


def test_the_27th_amendment_is_its_own_gazette_record_not_a_consolidated_constitution():
    a = _BY_ID["pk.fed.constitution-27th-amendment-2025"]
    assert a.text_authority == "gazette" and a.gazette_reference and a.amendment_of == "pk.fed.constitution-current"
    assert temporal_status(_BY_ID["pk.fed.constitution-current"], TODAY) == "commencement_unverified"
    assert a.ocr_quality == "ocr_poor" and ingestion_blockers(a)


def test_kp_code_is_not_recorded_as_missing():
    kp = next(f for f in _REG["feeds"] if f["feed_id"] == "feed.kp-code")
    assert kp["url_status"] == "ok" and kp["url_checks"]
