"""A stated period must be stated FOR THIS MATTER by a source the sentence
relies on (ai/period_support.py, 2026-10-13). Offline, no model.

The evidence texts are shaped on the real corpus: the chunk labelled
"Limitation Act 1908, s.6" is a slice of the First Schedule (Articles 113-115,
contract suits, "Three years").
"""
from __future__ import annotations

import pytest

from app.ai import period_support as P
from app.ai.answer_citations import split_claims

SCHEDULE_AS_S6 = {
    "id": "2", "kind": "statute", "statute": "Limitation Act 1908", "section": "6",
    "content": ("113.- For specific performance of a contract. [Three years]. The date fixed for the "
                "performance, or, if no such date is fixed, when the plaintiff has notice that "
                "performance is refused. 114.- For the rescission of a contract. [Three years]. When "
                "the facts entitling the plaintiff to have the contract rescinded first become known "
                "to him. 115.- For compensation for the breach of any contract, express or implied, "
                "not in writing registered. [Three years]. When the contract is broken."),
}
CPC_34 = {"id": "1", "kind": "statute", "statute": "CPC 1908", "section": "34",
          "content": "34. Interest.- Where and in so far as a decree is for the payment of money, "
                     "the Court may order interest at such rate as it deems reasonable."}
LIMITATION_S9 = {"id": "1", "kind": "statute", "statute": "Limitation Act 1908", "section": "9",
                 "content": "9. Continuous running of time.- Where once time has begun to run, no "
                            "subsequent disability or inability to sue stops it."}
PTA_S81 = {"id": "1", "kind": "statute", "statute": "Punjab Tenancy Act 1887", "section": "81",
           "content": "81. Limitation for appeals.- An appeal shall be preferred (a) to the Collector "
                      "within thirty days; (b) to the Commissioner within sixty days; (c) to the "
                      "Board of Revenue within ninety days, from the date of the order of the "
                      "Revenue Officer."}
RENT_S15 = {"id": "1", "kind": "statute", "statute": "Punjab Rented Premises Act 2009", "section": "15",
            "content": "15. Eviction of tenant.- A Rent Tribunal shall order the tenant to put the "
                       "landlord in possession if the tenant has failed to pay the rent within thirty "
                       "days of its becoming due."}


# ── c23: the period is in the cited text, but for a different matter ─────────

C23_ANSWER = (
    "The partner can be sued for the Rs 5 lakh within three years of the cheque’s dishonour, "
    "and the court may award interest on the amount from the date of suit to payment. [2][1]\n\n"
    "**Applicable law:**\n"
    "- Section 6 of the Limitation Act 1908 (three‑year limitation for recovery of a cheque). [2]\n"
    "- Section 34 of the Code of Civil Procedure 1908 (court may order interest on money decreed). [1]\n\n"
    "**Caution:** The suit must be instituted within three years from the date the cheque was "
    "bounced, otherwise the claim becomes time‑barred. [2]"
)


def test_c23_three_years_for_a_cheque_is_not_supported_by_a_contract_article():
    assert P.unsupported_periods(
        "A suit on a dishonoured cheque must be filed within three years [2].", [SCHEDULE_AS_S6]) \
        == [(3, "year")]


def test_c23_the_same_period_for_the_matter_the_source_names_is_kept():
    """Kept only when the sentence names the ARTICLE that sets it."""
    assert P.unsupported_periods(
        "Under Article 114, a suit for rescission of a contract must be filed within three years [2].",
        [SCHEDULE_AS_S6]) == []
    assert P.unsupported_periods(
        "A suit for rescission of a contract must be filed within three years [2].",
        [SCHEDULE_AS_S6]) == [(3, "year")]


# The real chunk the live c23.1 answer cited as "[6] Limitation Act 1908, s.6"
# (corpus id statutes_limitation_act_1908_0128): First Schedule Articles 57-62.
SCHEDULE_ART_58 = {
    "id": "6", "kind": "statute", "statute": "Limitation Act 1908", "section": "6",
    "content": ("57.- For money payable for money lent. 4 [Three years]. When the loan is made. "
                "58.- Like suit when the lender has given a cheque for the money. 5 [Three years]. "
                "When the cheque is paid. 59.- For money lent under an agreement that it shall be "
                "payable on demand. 6 [Three years]. When the loan is made."),
}


def test_c23_live_answer_section_6_three_years_for_a_cheque_is_unsupported():
    """Live fresh run: "cheque" sits beside "Three years" in Article 58, which
    is a LOAN the lender paid by cheque, not a suit on a dishonoured cheque --
    and it is an Article, not Section 6. One shared word is not support."""
    live = "- Section 6 of the *Limitation Act 1908* – three‑year limitation for a suit on a cheque. [6]"
    assert P.unsupported_periods(live, [SCHEDULE_ART_58]) == [(3, "year")]
    uncited = ("Send a formal legal notice to the partner demanding payment, citing the cheque’s "
               "status as a bill of exchange and the three‑year limitation.")
    assert P.unsupported_periods(uncited, [SCHEDULE_ART_58]) == [(3, "year")]


def test_c23_naming_the_article_that_sets_the_period_is_supported():
    assert P.unsupported_periods(
        "Under Article 58 of the Limitation Act, a suit for money lent where the lender gave a cheque "
        "must be brought within three years of the cheque being paid [6].", [SCHEDULE_ART_58]) == []


def test_c23_answer_loses_every_unsupported_deadline_and_says_so():
    out, removed = P.strip_unsupported_periods(C23_ANSWER, [CPC_34, SCHEDULE_AS_S6])
    low = P.normalise(out).lower()
    assert "three years" not in low and "three-year" not in low
    assert len(removed) == 3
    assert P.NOTICE_EN in out
    # the supported, period-free statement survives, and no orphan "[2][1]" line
    assert "Section 34 of the Code of Civil Procedure" in out
    assert "\n[2][1]" not in out and not any(l.strip() in ("[2]", "[2][1]") for l in out.split("\n"))


def test_c23_short_follow_up_cannot_repeat_the_unsupported_deadline():
    short = ("You can sue to recover the cheque amount within three years [2]. "
             "The court may also award interest [1].")
    out, removed = P.strip_unsupported_periods(short, [CPC_34, SCHEDULE_AS_S6])
    assert "three years" not in out and "award interest" in out and removed


def test_c23_urdu_follow_up_cannot_repeat_it_either():
    urdu = "چیک باؤنس ہونے پر رقم کی وصولی کا مقدمہ تین سال میں دائر کریں [2]۔"
    out, _ = P.strip_unsupported_periods(urdu, [SCHEDULE_AS_S6], urdu=True)
    assert "تین سال" not in out and P.NOTICE_UR in out


# ── c17 / c18: "Limitation" or "three years" in the text is not support ─────

def test_c17_appeal_period_from_a_revenue_provision_is_not_support_for_a_civil_decree():
    """Old c17 answered a civil-appeal question from the Punjab Tenancy Act
    s.81 (revenue appeals) and passed the silver check on the word
    "Limitation"."""
    sentence = "An appeal against a civil court decree must be filed within ninety days [1]."
    assert P.unsupported_periods(sentence, [PTA_S81]) == [(90, "day")]
    out, _ = P.strip_unsupported_periods(
        "**Applicable law:** Punjab Tenancy Act 1887 Section 81 — Limitation for appeals [1]\n"
        + sentence, [PTA_S81])
    assert "ninety" not in out and "Limitation for appeals" in out


def test_c17_the_revenue_period_for_a_revenue_appeal_is_kept():
    assert P.unsupported_periods(
        "An appeal to the Board of Revenue must be filed within 90 days [1].", [PTA_S81]) == []


def test_c18_three_years_cited_to_a_section_that_states_no_period_is_removed():
    sentence = "A suit to recover money someone owes you must be filed within three years [1]."
    assert P.unsupported_periods(sentence, [LIMITATION_S9]) == [(3, "year")]


def test_a_period_citing_a_provision_absent_from_the_evidence_is_unsupported():
    assert P.unsupported_periods(
        "Under Section 6 of the Limitation Act the period is three years.", [CPC_34]) == [(3, "year")]


# ── correctly supported deadlines and urgent warnings are preserved ──────────

def test_a_supported_deadline_survives_with_digits_against_words():
    text = "The Tribunal can order eviction if the tenant fails to pay rent within 30 days [1]."
    out, removed = P.strip_unsupported_periods(text, [RENT_S15])
    assert out == text and removed == []


def test_urgent_safety_text_is_never_touched():
    text = ("If you are in danger, call 15 immediately and go to the nearest police station.\n"
            "The police must produce an arrested person before a magistrate within 24 hours.")
    out, removed = P.strip_unsupported_periods(text, [CPC_34])
    assert out == text and removed == []


def test_section_numbers_and_years_of_acts_are_not_periods():
    assert P.periods_in("Section 15 of the Punjab Rented Premises Act 2009 and PPC 489-F") == []


@pytest.mark.parametrize("text,period", [
    ("within three-year", None),
    ("within three‑year limitation", None),
    ("thirty (30) days", (30, "day")),
    ("۹۰ دن", (90, "day")),
    ("تین سال", (3, "year")),
    ("teen saal", (3, "year")),
    ("six months", (6, "month")),
])
def test_period_forms(text, period):
    found = [p for p, _ in P.periods_in(text)]
    if period is None:
        assert found and found[0][1] == "year"
    else:
        assert found == [period]


# ── claims: the judge cannot pass an unsupported period ──────────────────────

def test_a_judge_supported_claim_with_an_unsupported_period_is_withdrawn():
    claims = split_claims(C23_ANSWER, [CPC_34, SCHEDULE_AS_S6], attach_markers=True)
    for c in claims:
        c["support"] = "supported"                # an over-trusting judge
    P.withdraw_claims(claims, [CPC_34, SCHEDULE_AS_S6])
    by_text = {c["text"][:30]: c["support"] for c in claims}
    assert by_text["The partner can be sued for th"] == "unsupported"
    assert by_text["- Section 34 of the Code of Ci"] == "supported"


def test_trailing_markers_join_the_sentence_they_belong_to():
    text = "The partner can be sued within three years. [2][1]"
    attached = split_claims(text, [CPC_34, SCHEDULE_AS_S6], attach_markers=True)
    assert len(attached) == 1 and attached[0]["source_ids"] == ["2", "1"]
    assert "three years" in attached[0]["text"]


def test_research_claim_splitting_is_unchanged_by_default():
    text = "The partner can be sued within three years. [2][1]"
    legacy = split_claims(text, [CPC_34, SCHEDULE_AS_S6])
    assert [c["text"] for c in legacy] == ["[2][1]"]


# ── 2026-10-14 review: schedule false passes and wrong-Act citations ─────────

CONTINUATION_NO_HEADING = {
    "id": "6", "kind": "statute", "statute": "Limitation Act 1908", "section": "6",
    "content": ("the dishonoured cheque or bill of exchange is presented and refused payment. "
                "5 [Three years]. When the cheque is dishonoured by the bank and notice is given."),
}
CRPC_OTHER = {"id": "1", "kind": "statute", "statute": "CrPC 1898", "section": "417",
              "content": "417. Appeal in case of acquittal ... a suit on a cheque must be brought within "
                         "three years of the cheque being dishonoured ..."}
PTA_S81_REAL = {"id": "1", "kind": "statute", "statute": "Punjab Tenancy Act 1887", "section": "81",
                "content": ("81. Limitation for appeals.- The period of limitation for an appeal under the last "
                            "foregoing section shall run from the date of the order or decree appealed against, "
                            "and shall be as follows, that is to say- (a) when the appeal lies to the Collector - "
                            "thirty days; (b) when the appeal lies to the 100 [Commissioner] - sixty days; (c) "
                            "when the appeal lies to the 101 [Board of Revenue] - ninety days.")}
ENGINE_506 = {"id": "9", "kind": "engine", "statute": "find_offence_sections (computed)", "section": "",
              "content": "{'matches': [{'id': 'PPC:506', 'law': 'PPC', 'section': '506', 'title': "
                         "'Criminal intimidation', 'punishment': 'Part I: up to 2 years; Part II: up to 7 years'}]}"}


def test_review_case_a_schedule_continuation_without_a_heading_fails_closed():
    """No article heading in the chunk: which article sets the period is
    unknowable, whatever words surround it."""
    s = "Under Section 6 of the Limitation Act, a suit on a dishonoured cheque must be filed within three years [6]."
    assert P.unsupported_periods(s, [CONTINUATION_NO_HEADING]) == [(3, "year")]


def test_review_case_b_article_58_does_not_cover_a_dishonoured_cheque_suit():
    """A matching number, article label and the word "cheque" are not
    applicability: Article 58 is a loan the LENDER paid by cheque."""
    s = "Under Article 58, a dishonoured-cheque suit must be filed within three years [6]."
    assert P.unsupported_periods(s, [SCHEDULE_ART_58]) == [(3, "year")]


def test_a_period_attributed_to_a_named_provision_needs_that_provisions_text():
    """Names the Limitation Act s.6; its marker points at a CrPC passage that
    happens to contain the period. The named provision is not in evidence."""
    s = "Under Section 6 of the Limitation Act, a suit on a dishonoured cheque must be filed within three years [1]."
    assert P.unsupported_periods(s, [CRPC_OTHER]) == [(3, "year")]


def test_a_section_saying_period_of_limitation_is_not_mistaken_for_a_schedule():
    """Punjab Tenancy Act s.81 says "the period of limitation" and lists real
    periods; those must survive (live c17)."""
    s = ("The appeal must be filed within the period prescribed by the Punjab Tenancy Act 1887 – 30 days if "
         "the appeal is to the Collector, 60 days if to the Commissioner, and 90 days if to the Board of Revenue [1].")
    assert P.unsupported_periods(s, [PTA_S81_REAL]) == []


def test_engine_output_naming_the_provision_supports_its_punishment_periods():
    s = ("Section 506 of the Pakistan Penal Code (PPC) defines criminal intimidation; it is punishable with up "
         "to two years’ imprisonment for simple intimidation and up to seven years for aggravated intimidation [9].")
    assert P.unsupported_periods(s, [ENGINE_506]) == []


def test_one_shared_word_beside_a_period_is_not_enough_in_section_text():
    """The live c10 caution: "30 days after the NOTICE ... before filing the
    eviction" -- s.15(b) runs 30 days from the rent falling due, and shares
    only "eviction" with the claim."""
    s = "Caution: The 30‑day period after the notice must elapse before filing the eviction application."
    # The REAL s.15 wording (corpus chunk), where clause (b) stands apart from
    # the heading: thirty days after the period stipulated in s.7, not after a
    # notice.
    real_s15 = {"id": "1", "kind": "statute", "statute": "Punjab Rented Premises Act 2009", "section": "15",
                "content": ("15. Grounds for eviction.- A landlord may seek eviction of the tenant if- (a) the "
                            "period of tenancy has expired; (b) the tenant has failed to pay or tender the rent "
                            "within a period of thirty days after the expiry of the period stipulated in section 7;")}
    assert P.unsupported_periods(s, [real_s15]) == [(30, "day")]
    assert P.unsupported_periods(
        "The landlord may seek eviction if the tenant fails to pay the rent within thirty days [1].",
        [real_s15]) == []


def test_a_period_from_another_clause_of_the_same_section_is_not_support():
    """Adversarial p08: s.81's ninety days is "(c) when the appeal lies to the
    Board of Revenue"; "decree" in the section's opening words does not make it
    the period for a civil-court decree."""
    s = ("Under Section 81 of the Punjab Tenancy Act, an appeal against a civil court decree must be filed "
         "within ninety days [1].")
    assert P.unsupported_periods(s, [PTA_S81_REAL]) == [(90, "day")]
    ok = "Under Section 81 of the Punjab Tenancy Act, an appeal to the Board of Revenue lies within ninety days [1]."
    assert P.unsupported_periods(ok, [PTA_S81_REAL]) == []


# ── over-removals found in the final live runs (2026-10-14) ──────────────────

PPC_506_REAL = {"id": "1", "kind": "statute", "statute": "PPC 1860", "section": "506",
                "content": ("506. Punishment for criminal intimidation:  Whoever commences the offence of criminal "
                            "intimidation shall be punished with imprisonment of either description for a term which "
                            "may extend to two years, or with fine, or with both; If threat be to cause death or "
                            "grievous hurt, etc.: And if the threat be to cause death or grievous hurt, or to cause "
                            "the destruction of any property by fire, or to cause an offence punishable with death or "
                            "imprisonment for life, or with imprisonment for a term which may extend to seven years, "
                            "or to impute unchastity to a woman, shall be punished with imprisonment")}
PPC_489F_REAL = {"id": "1", "kind": "statute", "statute": "PPC 1860", "section": "489F",
                 "content": ("489- F.  Dishonestly issuing a cheque:  Whoever dishonestly issues a cheque towards "
                             "repayment of a loan or fulfilment of an obligation which is dishonoured on presentation, "
                             "shall be punishable with imprisonment which may extend to three years, or with fine, "
                             "or with both")}
LIM_S8_ILLUSTRATIONS = {"id": "1", "kind": "statute", "statute": "Limitation Act 1908", "section": "8",
                        "content": ("Illustrations (a) A right to sue for an hereditary office accrues to A who at the "
                                    "time is insane. Six years after the accruer A recovers his reason. (b) A dies "
                                    "three years after the accruer, his idiocy continuing up to the date of his death.")}
LIM_S8_RULE = {"id": "3", "kind": "statute", "statute": "Limitation Act 1908", "section": "8",
               "content": ("8. Special exceptions.- Nothing in section 6 or section 7 applies to suits to enforce "
                           "rights of pre-emption, or shall be deemed to extend, for more than three years from the "
                           "cessation of the disability or the death of the person affected thereby, the period "
                           "within which any suit must be instituted or application made.")}


def test_both_506_periods_survive_when_commas_split_the_claim():
    s = ("Section 506 of the PPC criminalises intimidation and sets a maximum penalty of two years’ imprisonment "
         "(or fine) for ordinary threats, while threats of death, serious injury, major property damage, or "
         "imputing unchastity carry potentially up to seven years [1].")
    assert P.unsupported_periods(s, [PPC_506_REAL]) == []
    # The comma-split clause ("potentially reaching seven years") has no
    # subject of its own; the sentence does.
    s2 = "Section 506 PPC punishes threats to cause death with imprisonment, potentially reaching seven years [1]."
    assert P.unsupported_periods(s2, [PPC_506_REAL]) == []


def test_the_acts_name_does_not_strip_the_claims_subject():
    """"Punjab RENTED Premises Act" stemmed to "rent" and removed the subject
    "rent" from a true s.15(b) claim."""
    real_s15 = {"id": "4", "kind": "statute", "statute": "Punjab Rented Premises Act 2009", "section": "15",
                "content": ("15. Grounds for eviction.- A landlord may seek eviction of the tenant if- (a) the "
                            "period of tenancy has expired; (b) the tenant has failed to pay or tender the rent "
                            "within a period of thirty days after the expiry of the period stipulated in section 7;")}
    s = ("- Section 15 of the Punjab Rented Premises Act 2009 - grounds for eviction, including non-payment of "
         "rent after 30 days. [4]")
    assert P.unsupported_periods(s, [real_s15]) == []


def test_every_chunk_of_a_named_provision_is_considered():
    """Limitation Act s.8 sits in two chunks; only the first (illustrations)
    used to be read."""
    s = "- Section 8 of the Limitation Act 1908 - special three-year ceiling on extensions for such disabilities [3]"
    assert P.unsupported_periods(s, [LIM_S8_ILLUSTRATIONS, LIM_S8_RULE]) == []


def test_a_non_breaking_hyphen_does_not_turn_489f_into_489():
    # "PPC Section 489‑F" (non-breaking hyphen) used to parse as PPC 489.
    s = "Under PPC Section 489‑F, the punishment is imprisonment which may extend to three years [1]."
    assert P.unsupported_periods(s, [PPC_489F_REAL]) == []


def test_a_compound_number_is_read_whole():
    """"twenty-five years" (PPC 302(c)) was read as FIVE years and removed."""
    ppc_302 = {"id": "1", "kind": "statute", "statute": "PPC 1860", "section": "302",
               "content": ("302. Punishment of qatl-i-amd:  Whoever commits qatl-e-amd shall, subject to the provisions "
                           "of this Chapter be: (a) punished with death as qisas; (b) punished with death or "
                           "imprisonment for life as ta'zir having regard to the facts and circumstances of the case, "
                           "if the proof in either of the forms specified in section 304 is not available; or (c) "
                           "punished with imprisonment of either description for a term which may extend to "
                           "twenty-five years, where according to the Injunctions of Islam the punishment of qisas is "
                           "not applicable")}
    s = ("Section 302 PPC: up to 25 years' imprisonment when qisas is not applicable under Islamic law [1].")
    assert P.periods_in("twenty-five years")[0][0] == (25, "year")
    assert P.unsupported_periods(s, [ppc_302]) == []
