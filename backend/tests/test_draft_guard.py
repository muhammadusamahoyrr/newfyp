"""The lawyer drafter's legal check (app/ai/draft_guard.py), 2026-10-14.

Four gaps found by the drafter eval (evals/drafter, base_r1) and a live run:
  1. a real section of the right Act that does not deal with what the sentence
     relies on it for ("post-arrest bail under s.499 CrPC" -- s.499 is the bond);
  2. a jurisdiction-neutral draft confidently citing a federal provision for an
     issue each province's own law governs (TPA s.113 in an eviction notice);
  3. the guard and the citation checker disagreeing on the same citation (CPC
     numbers the corpus files several provisions under; "Pakistan Penal Code,
     1860" read as a second, unknown statute);
  4. counts that included provisions from withheld sentences.

One REAL CorpusIndex fixture, read by both checkers, with provision headings
taken from the official CrPC/PPC texts (pakistancode.gov.pk) and the corpus.
"""
from __future__ import annotations

import pytest

from app.ai import corpus_index as ci

CRPC = {"57": "Refusal to give name and residence", "154": "Information in cognizable cases",
        "420": "Procedure when appellant in jail", "426": "Suspension of sentence pending appeal. Release of appellant on bail",
        "435": "Power to call for records of inferior Courts", "439": "High Court's powers of revision",
        "491": "Power to issue directions of the nature of a habeas corpus",
        "496": "In what cases bail to be taken", "497": "When bail may be taken in case of non-bailable offence",
        "498": "Power to direct admission to bail or reduction of bail", "499": "Bond of accused and sureties",
        "500": "Discharge from custody", "501": "Power to order sufficient bail when that first taken is insufficient",
        "502": "Discharge of sureties", "512": "Record of evidence in absence of accused"}
PPC = {"6": "Definitions in the Code to be understood subject to exceptions",
       "406": "Punishment for criminal breach of trust", "420": "Cheating and dishonestly inducing delivery of property",
       "489": "Tampering with property mark with intent to cause injury", "506": "Punishment for criminal intimidation"}
TPA = {"54": "Sale defined", "105": "Lease defined", "106": "Duration of certain leases in absence of written contract",
       "108": "Rights and liabilities of lessor and lessee", "111": "Determination of lease", "113": "Waiver of notice to quit"}
CPC = {"8": ("Presidency Small Cause Courts", "Procedure where defendant appears"), "9": ("Courts to try all civil suits unless barred",
       "Joinder of parties"), "11": ("Res judicata", "Delivery of interrogatories")}
CONTRACT = {"73": "Compensation for loss or damage caused by breach of contract"}


def _cov(statute, provisions):
    provisions = {k: (v if isinstance(v, tuple) else (v,)) for k, v in provisions.items()}
    nums = frozenset(int(k) for k in provisions if k.isdigit())
    return ci.StatuteCoverage(statute=statute, sections=frozenset(provisions), numbered=nums,
                              highest=max(nums), artifacts=0, omitted=frozenset({437, 438}) if statute == "CrPC 1898" else frozenset(),
                              provisions=provisions)


def _cpc_catalogue():
    from app.ai import cpc_provisions as cp
    rows = [({"statute": "CPC 1908", "provision_kind": "order_rule", "provision_label": f"Order {o} Rule {r}"},
             f"{r}. {h}.- text of the rule ...") for o, r, h in (
        ("VII", "10", "Return of plaint"), ("VII", "11", "Rejection of plaint"), ("VII", "12", "Procedure on rejecting plaint"),
        ("VI", "17", "Amendment of pleadings"), ("I", "10", "Suit in name of wrong plaintiff"),
        ("XXIII", "1", "Withdrawal of suit or abandonment of part of claim"), ("IX", "4", "Plaintiff may bring fresh suit"),
        ("VIII", "1", "Written statement"))]
    rows += [({"statute": "CPC 1908", "provision_kind": "section", "section_number": n}, f"{n}. {h}.- text ...") for n, h in (
        ("4", "Savings"), ("9", "Courts to try all civil suits unless barred"), ("11", "Res judicata"),
        ("151", "Saving of inherent powers of Court"), ("13", "When foreign judgment not conclusive"))]
    return cp.build_catalogue(rows)


CPC_CATALOGUE = _cpc_catalogue()

INDEX = ci.CorpusIndex({"CrPC 1898": _cov("CrPC 1898", CRPC), "PPC 1860": _cov("PPC 1860", PPC),
                        "Transfer of Property Act 1882": _cov("Transfer of Property Act 1882", TPA),
                        "CPC 1908": _cov("CPC 1908", CPC), "Contract Act 1872": _cov("Contract Act 1872", CONTRACT)})
TEXTS = {("CrPC", "438"): "438. [Omitted]"}


@pytest.fixture
def corpus(monkeypatch):
    from app.ai import cpc_provisions, exact_provision
    monkeypatch.setattr(ci, "get_index", lambda: INDEX)
    monkeypatch.setattr(ci, "get_drafter_index", lambda: INDEX)
    cpc_provisions.set_catalogue(CPC_CATALOGUE)
    monkeypatch.setattr(cpc_provisions, "catalogue", lambda: CPC_CATALOGUE)

    def fetch(cits, research=False, strict=False):
        out = {}
        for c in cits:
            fam = c.statute.split()[0]
            heads = {"CrPC": CRPC, "PPC": PPC}.get(fam, {})
            text = TEXTS.get((fam, c.section)) or (f"{c.section}. {heads[c.section]}. ..." if c.section in heads else None)
            out[exact_provision.label(c)] = ([{"statute": f"{fam}", "content": text, "section_number": c.section}]
                                             if text else [])
        return out
    monkeypatch.setattr(exact_provision, "fetch", fetch)
    return INDEX


def _check(text, province="punjab", topic=None, question="x"):
    from app.ai import draft_guard
    return draft_guard.check(text, question, [], province, topic)


# ── 1. the right Act, the wrong subject ─────────────────────────────────────

def test_bail_under_the_bond_section_is_withheld_and_points_to_the_bail_sections(corpus):
    g = _check("That the Applicant is entitled to post-arrest bail under Section 499 CrPC.")
    assert g["text"] == "" and g["counts"]["withheld_sentences"] == 1
    reason = g["withheld"][0]["reasons"][0]
    assert '"Bond of accused and sureties"' in reason and "bail" in reason
    assert "see " not in reason, "an unverified corrective suggestion was offered"


@pytest.mark.parametrize("sentence", [
    "That the Applicant is ready to execute a bond with two sureties under Section 499 CrPC.",
    "That the Applicant be released on bail upon executing a bond under Section 499 CrPC.",
    "That the Applicant is entitled to bail under Section 497 CrPC as the offence is non-bailable.",
    "That the Applicant shall be released from jail under Section 500 CrPC once the bond is executed.",
    "That FIR No. 12/2026 was registered under Section 154 CrPC.",
    "That execution of the sentence be suspended and the appellant released on bail under Section 426 CrPC pending the appeal.",
    "That the High Court may direct production of the detenu under Section 491 CrPC.",
    "That the Respondent committed cheating punishable under Section 420 PPC.",
])
def test_valid_uses_are_kept_and_counted(corpus, sentence):
    # The FIR number is a FACT: the lawyer gives it (draft_claims S3 withholds one
    # they did not give -- test_draft_guard_v2 covers that).
    g = _check(sentence, question="FIR No. 12/2026")
    assert g["withheld"] == [], g["withheld"]
    assert g["text"] == sentence and g["counts"]["supported"] == 1


def test_a_mere_mention_is_not_judged_for_its_subject(corpus):
    # no "under / pursuant to": the sentence does not rely on s.499 for anything
    g = _check("Section 499 CrPC also mentions bail.")
    assert g["withheld"] == []


@pytest.mark.parametrize("sentence,cited", [
    ("That the applicant will furnish a surety bond for bail under Section 57 CrPC.", "57"),
    ("That the cheque was dishonoured and an offence is made out under Section 489 PPC.", "489"),
])
def test_other_off_subject_sections_seen_in_the_eval(corpus, sentence, cited):
    g = _check(sentence)
    if cited == "57":     # 57 "Refusal to give name and residence" vs bond/bail: the Act heads them elsewhere
        assert g["withheld"] and "Refusal to give name" in g["withheld"][0]["reasons"][0]
    else:                 # 489 "Tampering with property mark": no PPC heading here says cheque -> cannot tell, kept
        assert g["withheld"] == []


def test_research_keeps_its_behaviour(corpus):
    from app.ai import visible_authority
    s = "That the Applicant is entitled to post-arrest bail under Section 499 CrPC."
    assert visible_authority.authorities(s, "x", False)[1] == []          # research default: not judged


# ── 2. neutral draft, province-dependent issue ──────────────────────────────

def test_a_neutral_tenancy_notice_cannot_rest_on_the_tpa_lease_sections(corpus):
    from app.ai import draft_jurisdiction as dj
    text = ("That you are required to vacate for non-payment of rent under Section 113 of the Transfer of Property Act, 1882.\n\n"
            "That you are also liable for compensation for breach under Section 73 of the Contract Act, 1872.")
    topic = dj.topic_for("Notice Letter Add a paragraph calling on the tenant to vacate for non-payment of rent")
    assert topic == "tenancy"
    g = _check(text, province="unknown", topic=topic)
    assert "Transfer of Property" not in g["text"]
    assert "Section 73 of the Contract Act" in g["text"], "genuinely federal law was removed"
    assert any("provincial rent law applies" in r for w in g["withheld"] for r in w["reasons"])
    assert g["clarify"]["topic"] == "tenancy" and g["clarify"]["placeholder"] is False


def test_a_placeholder_is_recognised(corpus):
    g = _check("That you must vacate for non-payment of rent under [applicable provincial rent law -- choose jurisdiction].",
               province="unknown", topic="tenancy")
    assert g["withheld"] == [] and g["clarify"]["placeholder"] is True


def test_a_chosen_province_is_not_treated_as_neutral(corpus):
    g = _check("That you must vacate for non-payment of rent under Section 111 of the Transfer of Property Act.",
               province="punjab", topic="tenancy")
    assert g["clarify"] is None
    assert not any("no jurisdiction was chosen" in r for w in g["withheld"] for r in w["reasons"])


@pytest.mark.parametrize("request_text,topic", [
    ("Lease Agreement Add a clause on the landlord's right to evict for personal use", "tenancy"),
    ("Employment Contract Add a termination clause citing labour law", "employment"),
    ("Plaint Add the talb-e-muwathibat paragraph", "pre-emption"),
    ("Bail Application Add a ground for bail", None),
    ("Loan Agreement Add a clause for the current interest rate", None),     # "current" is not "rent"
])
def test_topic_detection(request_text, topic):
    from app.ai import draft_jurisdiction as dj
    assert dj.topic_for(request_text) == topic


def test_the_neutral_rider_asks_for_a_placeholder():
    from app.ai import draft_jurisdiction as dj
    r = dj.topic_rider("unknown", "tenancy")
    assert "Do not cite any statute for it" in r and "[applicable provincial rent law" in r
    assert dj.topic_rider("punjab", "tenancy") == ""


# ── 3. the two checkers on the same citations ───────────────────────────────

SHARED = [
    # (sentence, verifier status, guard bucket)
    ("This petition seeks review under Section 8 of the Code of Civil Procedure, 1908.", "SECTION_NOT_CHECKABLE", "not_checked"),
    ("The suit lies under Section 9 CPC.", "SECTION_NOT_CHECKABLE", "not_checked"),
    ("The Respondent committed cheating and dishonestly induced delivery of property under Section 420 of the Pakistan Penal Code, 1860.", "VERIFIED", "supported"),
    ("The Respondent committed criminal breach of trust punishable under Section 406 PPC.", "VERIFIED", "supported"),
    ("Compensation is payable under Section 73 of the Contract Act, 1872.", "VERIFIED", "supported"),
]


@pytest.mark.parametrize("sentence,verifier,bucket", SHARED)
def test_both_checkers_agree_on_the_same_citation(corpus, sentence, verifier, bucket):
    from app.ai.citation_verification import verify_statutes
    checks = verify_statutes(sentence, index=INDEX)
    assert [c.status for c in checks] == [verifier], [(c.canonical, c.status) for c in checks]
    g = _check(sentence)
    other = "not_checked" if bucket == "supported" else "supported"
    assert len(g[bucket]) == 1 and g[other] == [], g


def test_the_long_form_act_name_is_one_citation_not_two(corpus):
    from app.ai.citation_verification import verify_statutes
    checks = verify_statutes("liable under Section 420 of the Pakistan Penal Code, 1860, and Section 420 PPC", index=INDEX)
    assert [(c.canonical, c.status) for c in checks] == [("PPC 1860 s.420", "VERIFIED")]


def test_found_is_not_supported(corpus):
    """The verifier checks existence; the guard also checks the subject. A
    real, findable section cited for the wrong thing is VERIFIED by one and
    withheld by the other -- by design, and never counted as supported."""
    from app.ai.citation_verification import verify_statutes
    s = "That the Applicant is entitled to post-arrest bail under Section 499 CrPC."
    assert [c.status for c in verify_statutes(s, index=INDEX)] == ["VERIFIED"]
    g = _check(s)
    assert g["supported"] == [] and g["counts"]["withheld_sentences"] == 1


# ── 4. counts describe the final text ───────────────────────────────────────

def test_a_provision_in_a_withheld_sentence_is_in_no_count(corpus):
    g = _check("That bail lies under Section 497 CrPC.\n\nThat pre-arrest bail also lies under Section 438 CrPC.")
    assert g["supported"] == ["Section 497 CrPC 1898"]
    assert g["counts"] == {"supported": 1, "withheld_sentences": 1, "not_checked": 0}
    assert all("438" not in s for s in g["supported"] + g["not_checked"])


def test_a_valid_provision_in_a_jurisdiction_withheld_sentence_is_not_counted(corpus):
    g = _check("That the tenant defaulted under the Sindh Rented Premises Ordinance, 1979 and Section 420 PPC.",
               province="punjab")
    assert g["counts"]["withheld_sentences"] == 1 and g["supported"] == []


def test_a_sentence_with_two_problems_is_one_withheld_sentence_with_both_reasons(corpus):
    g = _check("That bail lies under Section 438 CrPC per the Sindh Rented Premises Ordinance, 1979.", province="punjab")
    assert g["counts"]["withheld_sentences"] == 1
    assert len(g["withheld"][0]["reasons"]) == 2


def test_an_ambiguous_number_is_not_checked_not_supported(corpus):
    g = _check("That this Court has jurisdiction under Section 9 CPC.")
    assert g["supported"] == []
    assert g["not_checked"] == ["Section 9 CPC 1908 (several provisions share this number)"]
    assert g["withheld"] == [] and g["text"]


def test_a_citation_in_a_sentence_the_check_skips_is_still_counted_as_not_checked(corpus):
    # "Review ..." reads as an instruction to the shared check, which skips it.
    g = _check("Review is sought under Section 8 of the Code of Civil Procedure, 1908.")
    assert g["supported"] == [] and g["not_checked"] and "Section 8" in g["not_checked"][0]


# ── refinements from the adversarial set (evals/drafter/subject_adversarial_v1.jsonl) ──

PRPA = {"5": "Agreement between landlord and tenant", "9": "Effect of non-compliance", "15": "Grounds for eviction",
        "19": "Filing of application", "20": "Procedure", "21": "Notice"}
PPA = {"13": "Demand of pre-emption", "30": "Limitation", "5": "Pre-emption", "6": "Right of pre-emption",
       "7": "Persons in whom the right vests", "8": "Exemption"}


@pytest.fixture
def corpus2(corpus, monkeypatch):
    idx = ci.CorpusIndex({**{k: INDEX.coverage(k) for k in INDEX.statutes},
                          "Punjab Rented Premises Act 2009": _cov("Punjab Rented Premises Act 2009", PRPA),
                          "Punjab Pre-emption Act 1991": _cov("Punjab Pre-emption Act 1991", PPA)})
    monkeypatch.setattr(ci, "get_index", lambda: idx)
    monkeypatch.setattr(ci, "get_drafter_index", lambda: idx)
    return idx


def test_party_words_do_not_make_a_heading_agree(corpus2):
    # "...landlord and TENANT" must not vouch for an eviction ground
    g = _check("That the tenant defaulted in rent, a ground for eviction under Section 5 of the Punjab Rented Premises Act, 2009.")
    assert g["counts"]["withheld_sentences"] == 1 and "eviction" in g["withheld"][0]["reasons"][0]
    assert "see " not in g["withheld"][0]["reasons"][0]
    ok = _check("That the landlord shall submit the tenancy agreement to the Rent Registrar under Section 5 of the Punjab Rented Premises Act, 2009.")
    assert ok["withheld"] == []


def test_as_required_by_is_reliance(corpus2):
    g = _check("That the talb-e-muwathibat was made as required by Section 30 of the Punjab Pre-emption Act, 1991.")
    assert g["counts"]["withheld_sentences"] == 1 and "demand" in g["withheld"][0]["reasons"][0]
    assert "see " not in g["withheld"][0]["reasons"][0]
    ok = _check("That the suit is within the limitation of four months under Section 30 of the Punjab Pre-emption Act, 1991.")
    assert ok["withheld"] == []


def test_a_constitution_article_is_counted_as_not_checked_not_dropped(corpus):
    g = _check("That the High Court may direct production of the detenu under Article 10 of the Constitution of Pakistan.")
    assert g["supported"] == [] and any(s.startswith("Article 10") for s in g["not_checked"]), g


def test_the_placeholder_the_rider_asks_for_is_never_withheld(corpus):
    # eval after_r1 A4: "[... (standing orders) law ...]" matched the employment rule
    text = "The termination of this Contract shall be governed by [applicable provincial labour (standing orders) law -- choose jurisdiction]."
    g = _check(text, province="unknown", topic="employment")
    assert g["withheld"] == [] and g["text"] == text and g["clarify"]["placeholder"] is True
    cited = _check("Termination is governed by the Industrial and Commercial Employment (Standing Orders) Ordinance, 1968.",
                   province="unknown", topic="employment")
    assert cited["counts"]["withheld_sentences"] == 1
