"""The drafter's legal check v2 (2026-10-15): the failures seen in eval
drafter_v2 (results/v2_r1), case by case. A fixture index with headings from
the official CrPC/PPC texts (pakistancode.gov.pk) and the corpus; a fixture
CPC Order/Rule catalogue in the shape of civil_collection__ident_v1."""
from __future__ import annotations

import pytest

from app.ai import corpus_index as ci

CRPC = {"154": "Information in cognizable cases", "420": "Procedure when appellant in jail", "203": "Dismissal of complaints", "354": "Language of record of evidence",
        "426": "Suspension of sentence pending appeal. Release of appellant on bail", "496": "In what cases bail to be taken",
        "497": "When bail may be taken in case of non-bailable offence", "498": "Power to direct admission to bail or reduction of bail",
        "499": "Bond of accused and sureties", "500": "Discharge from custody", "501": "Power to order sufficient bail when that first taken is insufficient",
        "502": "Discharge of sureties", "561-A": "Saving of inherent power of High Court", "57": "Refusal to give name and residence",
        "91": "Power to take bond for appearance", "526": "High Court may transfer case or itself try it",
        "126": "Discharge of sureties", "185": "Power to take cognizance"}
CPC = {"1": "Short title, commencement and extent", "4": "Savings", "9": "Courts to try all civil suits unless barred",
       "10": "Stay of suit", "11": "Res judicata", "13": "When foreign judgment not conclusive",
       "151": "Saving of inherent powers of Court", "158": "Repeal and savings",
       "20": "Other suits to be instituted where defendants reside or cause of action arises"}
PPC = {"406": "Punishment for criminal breach of trust", "420": "Cheating and dishonestly inducing delivery of property",
       "489": "Tampering with property mark with intent to cause injury", "489-F": "Dishonestly issuing a cheque",
       "302": "Punishment of qatl-i-amd"}
SUCC = {"373": "Procedure on application", "372": "Application for certificate", "370": "Restriction on grant of certificates",
        "371": "Court having jurisdiction to grant certificate", "374": "Contents of certificate"}
GWA = {"17": "Matters to be considered by the Court in appointing guardian", "24": "Duties of guardian of the person",
       "25": "Title of guardian to custody of ward", "7": "Power of the Court to make order as to guardianship",
       "12": "Power to make interlocutory order"}
DIV = {"41": "Power to make orders as to custody of children in suit for separation", "10": "When husband or wife may petition for dissolution",
       "7": "Court to act on principles of English Divorce Court", "17": "Confirmation of decree for dissolution",
       "45": "Code of Civil Procedure to apply"}
MFLO = {"7": "Talaq", "8": "Dissolution of marriage otherwise than by talaq", "9": "Maintenance", "5": "Registration of marriages",
        "6": "Polygamy"}
TEXT = {("CrPC", "561-A"): "561-A. Saving of inherent power of High Court. Nothing in this Code shall be deemed to limit or "
                           "affect the inherent power of the High Court to make such orders as may be necessary to give effect "
                           "to any order under this Code, or to prevent abuse of the process of any Court or otherwise to "
                           "secure the ends of justice.",
        ("PPC", "489-F"): "489-F. Dishonestly issuing a cheque. Whoever dishonestly issues a cheque towards re-payment of a "
                          "loan or fulfilment of an obligation which is dishonoured on presentation, shall be punishable ...",
        ("CrPC", "502"): "502. Discharge of sureties.__ (1) All or any sureties for the attendance and appearance of a person "
                         "released on bail may at any time apply to a Magistrate to discharge the bond. (2) On such application "
                         "being made, the Magistrate shall issue his warrant of arrest directing that the person so released be "
                         "brought before him. (3) On the appearance of such person ...",
        ("MFLO", "7"): "7. Talaq.-- (1) Any man who wishes to divorce his wife shall, as soon as may be after the "
                       "pronouncement of talaq in any form whatsoever, give the Chairman notice in writing of his having done so ...",
        ("PPC", "420"): "420. Cheating and dishonestly inducing delivery of property. Whoever cheats ... shall be punished with "
                        "imprisonment of either description for a term which may extend to seven years, and shall also be liable to fine."}


def _cov(statute, provisions):
    provisions = {k: (v,) for k, v in provisions.items()}
    nums = frozenset(int(k.split("-")[0]) for k in provisions)
    return ci.StatuteCoverage(statute=statute, sections=frozenset(provisions), numbered=nums,
                              highest=max(nums), artifacts=0, provisions=provisions)


INDEX = ci.CorpusIndex({"CrPC 1898": _cov("CrPC 1898", CRPC), "CPC 1908": _cov("CPC 1908", CPC),
                        "PPC 1860": _cov("PPC 1860", PPC), "Succession Act 1925": _cov("Succession Act 1925", SUCC),
                        "Guardians and Wards Act 1890": _cov("Guardians and Wards Act 1890", GWA),
                        "Divorce Act 1869": _cov("Divorce Act 1869", DIV),
                        "Muslim Family Laws Ordinance 1961": _cov("Muslim Family Laws Ordinance 1961", MFLO),
                        "Christian Marriage Act 1872": _cov("Christian Marriage Act 1872", {
                            "5": "Persons by whom marriages may be solemnized", "4": "Marriages to be solemnized according to Act",
                            "6": "Places in which marriages may be solemnized", "7": "Time for solemnizing marriages",
                            "10": "Time during which marriages may be solemnized"})})


def _catalogue():
    from app.ai import cpc_provisions as cp
    rules = (("VII", "1", "Particulars to be contained in plaint"), ("VII", "10", "Return of plaint"),
             ("VII", "11", "Rejection of plaint"), ("VII", "12", "Procedure on rejecting plaint"),
             ("VII", "13", "Where rejection of plaint does not preclude presentation of fresh plaint"),
             ("VI", "17", "Amendment of pleadings"), ("I", "10", "Suit in name of wrong plaintiff"),
             ("XXIII", "1", "Withdrawal of suit or abandonment of part of claim"), ("IX", "4", "Plaintiff may bring fresh suit"),
             ("IX", "12", "Consequence of non-attendance"), ("IX", "14", "No decree to be set aside without notice to opposite party"),
             # real CPC headings that also carry "plaint": as in the index, "plaint" is a common word (11 headings)
             ("IV", "1", "Suit to be commenced by plaint"), ("VII", "3", "Where the subject-matter of the suit is immovable property"),
             ("VII", "5", "Defendant's interest and liability to be shown in plaint"),
             ("VII", "6", "Grounds of exemption from limitation law to be shown in plaint"),
             ("VII", "9", "Procedure on admitting plaint"), ("VII", "14", "Production of document on which plaintiff sues in plaint"),
             ("VII", "17", "Production of shop-book with plaint"),
             ("XI", "17", "Time for inspection when notice given"),
             # "notice" is a common CPC heading word (23 headings in the index)
             ("V", "1", "Summons"), ("VI", "11", "Notice"), ("XXI", "22", "Notice to show cause against execution in certain cases"),
             ("XXI", "37", "Discretionary power to permit judgment-debtor to show cause"), ("XLIII", "3", "Notice before presentation of appeal"),
             ("XXXIX", "3", "Before granting injunction, Court to direct notice to opposite party"), ("XLI", "14", "Publication and service of notice of day for hearing appeal"),
             ("XXI", "16", "Application for execution by transferee of decree"), ("XXV", "1", "When security for costs may be required from plaintiff"),
             ("XII", "2", "Notice to admit documents"), ("XII", "4", "Notice to admit facts"), ("XII", "8", "Notice to produce documents"),
             ("XXI", "66", "Proclamation of sales by public auction"), ("XLVII", "4", "Application where rejected"),
             ("XXVII", "1", "Suits by or against the Government"), ("XXVII", "2", "Persons authorised to act for Government"))
    rows = [({"statute": "CPC 1908", "provision_kind": "order_rule", "provision_label": f"Order {o} Rule {r}"},
             f"{r}. {h}.- the rule ...") for o, r, h in rules]
    rows += [({"statute": "CPC 1908", "provision_kind": "section", "section_number": n}, f"{n}. {h}.- ...") for n, h in CPC.items()]
    return cp.build_catalogue(rows)


CAT = _catalogue()


@pytest.fixture
def corpus(monkeypatch):
    from app.ai import cpc_provisions, exact_provision
    monkeypatch.setattr(ci, "get_index", lambda: INDEX)
    monkeypatch.setattr(ci, "get_drafter_index", lambda: INDEX)
    monkeypatch.setattr(cpc_provisions, "catalogue", lambda: CAT)

    def fetch(cits, research=False, strict=False):
        out = {}
        for c in cits:
            fam = c.statute.split()[0]
            fam = "MFLO" if "Muslim Family" in c.statute else fam
            heads = {"CrPC": CRPC, "PPC": PPC, "CPC": CPC, "MFLO": MFLO}.get(fam, {})
            text = TEXT.get((fam, c.section)) or (f"{c.section}. {heads[c.section]}. ..." if c.section in heads else None)
            out[exact_provision.label(c)] = [{"statute": fam, "content": text, "section_number": c.section}] if text else []
        return out
    monkeypatch.setattr(exact_provision, "fetch", fetch)
    return INDEX


# Punjab by default (2026-10-16): the CPC text on file is the PUNJAB Code's, and
# these tests are about Order/Rule matching. Outside Punjab a CPC citation is
# never "supported" (ai/source_currency.py) -- pinned by the wrong-province test
# at the end of this file and in tests/test_source_currency.py.
def check(text, question="x", context="", province="punjab", topic=None):
    from app.ai import draft_guard
    return draft_guard.check(text, question, [], province, topic, context=context)


def reasons(g):
    return " | ".join(r for w in g["withheld"] for r in w["reasons"])

# ── CPC: Section versus Order/Rule (V01-V06) ────────────────────────────────

def test_v01_rejection_of_plaint_under_a_bare_section_is_withheld_and_points_to_the_rule(corpus):
    g = check("That the plaint ought to be rejected pursuant to CPC 1908 Section 13.")
    assert g["counts"]["withheld_sentences"] == 1
    assert '"When foreign judgment not conclusive"' in reasons(g) and "see " not in reasons(g)


@pytest.mark.parametrize("sentence", [
    "That the plaint is liable to be rejected under Order VII Rule 11 CPC as it discloses no cause of action.",
    "That the plaint is liable to be rejected under O.7 r.11 of the Code of Civil Procedure.",
    "That the plaint is liable to be rejected under Order 7, Rule 11 CPC.",
])
def test_v01_the_rule_itself_is_supported_in_every_spelling(corpus, sentence):
    g = check(sentence)
    assert g["withheld"] == [] and g["supported"] == ["Order VII Rule 11 CPC"], g


def test_v02_return_of_plaint_under_the_rejection_rule_is_withheld(corpus):
    g = check("That the plaint be returned for presentation to the proper court under Order VII Rule 11 CPC.")
    assert g["counts"]["withheld_sentences"] == 1 and "return" in reasons(g) and "see " not in reasons(g)
    ok = check("That the plaint be returned for presentation to the proper court under Order VII Rule 10 CPC.")
    assert ok["supported"] == ["Order VII Rule 10 CPC"]


def test_v06_withdrawal_under_section_1_is_withheld(corpus):
    g = check("That the plaintiff seeks to withdraw the suit in accordance with Section 1 of the Code of Civil Procedure, 1908.")
    assert g["counts"]["withheld_sentences"] == 1 and "withdraw" in reasons(g) and "see " not in reasons(g)


def test_a_cpc_section_is_never_read_as_an_order_rule_or_the_reverse(corpus):
    g = check("That the matter is res judicata under Section 11 CPC, and the plaint is rejected under Order VII Rule 11 CPC.")
    assert "Order VII Rule 11 CPC" in g["supported"]
    assert any(s.startswith("Section 11 CPC") for s in g["supported"])

# ── malformed / nonexistent / not in our copy (V23) ─────────────────────────

@pytest.mark.parametrize("sentence,needle", [
    ("That this notice is required under Section 1956 of the Code of Civil Procedure, 1908.", "Section 1956"),
    ("That the plaint is liable to be rejected under Order VII Rule 99 CPC.", "Order VII Rule 99"),
    ("That the plaint is liable to be rejected under Order 60 Rule 1 CPC.", "Order LX Rule 1"),
])
def test_v23_a_provision_the_code_does_not_have_is_withheld(corpus, sentence, needle):
    g = check(sentence)
    assert g["counts"]["withheld_sentences"] == 1, g
    assert g["supported"] == []


def test_a_real_provision_our_copy_lacks_is_not_verified_never_withheld(corpus):
    g = check("That this review petition is filed under Section 114 of the Code of Civil Procedure, 1908.")
    assert g["withheld"] == [] and g["supported"] == []
    assert any(s.startswith("Section 114") for s in g["not_checked"])
    g = check("That the ex parte decree be set aside under Order IX Rule 13 CPC.")
    assert g["withheld"] == [] and any("Order IX Rule 13" in s and "not in our copy" in s for s in g["not_checked"])

# ── subject: the clause the citation sits in (V11, V12) ─────────────────────

def test_v11_pre_arrest_bail_on_the_dismissal_section_is_withheld(corpus):
    g = check("That the complaint lodged is mala fide and, having no sufficient ground for proceeding, the applicant is "
              "entitled to pre-arrest protective bail pursuant to Section 203 of the Code of Criminal Procedure, 1898.")
    assert g["counts"]["withheld_sentences"] == 1 and "bail" in reasons(g)
    ok = check("That the Court may, under Section 203 of the Code of Criminal Procedure, 1898, dismiss the complaint.")
    assert ok["withheld"] == [] and ok["supported"]


@pytest.mark.parametrize("sentence", [
    "That the Magistrate may issue a warrant of arrest directing the accused to appear before this Court in accordance with Section 502(2) of the Code of Criminal Procedure, 1898.",
    "That the Applicant, [Name of Surety], is a surety for the bail bond executed in favour of the accused, [Name of Accused], under Section 502 of the Code of Criminal Procedure, 1898.",
    "That the applicant seeks to be discharged from the said bond, either wholly or insofar as it relates to the applicant, pursuant to Section 502 of the Code of Criminal Procedure, 1898.",
])
def test_v12_valid_uses_of_502_are_never_withheld(corpus, sentence):
    g = check(sentence)
    assert g["withheld"] == [], reasons(g)
    assert g["supported"] == ["Section 502 CrPC 1898"]


def test_punishable_under_420_is_supported_from_the_provision_text(corpus):
    g = check("That the offence under Section 420 PPC is punishable with up to seven years and fine.")
    assert g["supported"] == ["Section 420 PPC"] or g["supported"] == ["Section 420 PPC 1860"], g


def test_v07_an_irrelevant_authority_is_not_supported_merely_because_it_exists(corpus):
    g = check("That this Court may fix an early date of hearing under Section 373 of the Succession Act, 1925.")
    assert g["supported"] == []
    assert any(s.startswith("Section 373") for s in g["not_checked"]) or g["withheld"]

# ── Urdu, Roman Urdu, Unicode (V13, V09) ────────────────────────────────────

def test_v13_an_urdu_section_reference_is_read_and_judged(corpus):
    text = "یہ کہ ملزم کے خلاف مزید انکوائری درکار ہے، اس لیے ضمانت بعد از گرفتاری کی درخواست سیکشن 354، CrPC 1898 کے تحت کی جاتی ہے۔"
    g = check(text)
    assert g["supported"] == [], "an unreadable citation passed silently"
    assert g["withheld"] or any("354" in s for s in g["not_checked"])
    if g["withheld"]:
        assert g["withheld"][0]["text"].startswith("یہ کہ ملزم"), "the withheld span does not map onto the original text"


def test_urdu_digits_and_urdu_act_names(corpus):
    g = check("یہ کہ ملزم ضمانت کا حقدار ہے کیونکہ مقدمہ مزید انکوائری کا ہے، دفعہ ۴۹۷ ضابطہ فوجداری کے تحت۔")
    assert len(g["supported"]) == 1 and g["supported"][0].startswith("Section 497 CrPC"), g


def test_roman_urdu_dafa(corpus):
    g = check("That the applicant deserves bail under dafa 497 CrPC as the case calls for further inquiry.")
    assert g["supported"] and "497" in g["supported"][0]


def test_v09_a_non_breaking_hyphen_is_the_same_provision(corpus):
    g = check("That the High Court may exercise its inherent power under Section 561‑A of the Code of Criminal Procedure, 1898, to prevent abuse of process.")
    assert g["supported"] and "561-A" in g["supported"][0], g
    assert g["text"].count("‑") == 1, "the lawyer's own characters were changed"

# ── personal law (V15) ──────────────────────────────────────────────────────

def test_v15_a_christian_act_in_a_custody_matter_of_unknown_community_is_not_verified(corpus):
    g = check("That custody be given to the mother under Section 41 of the Divorce Act, 1869, as the welfare of the minor requires.")
    assert not any("Divorce" in s for s in g["supported"])
    assert any("Divorce" in s and "Christian" in s for s in g["not_checked"]) or g["withheld"]


def test_a_christian_act_in_a_muslim_matter_is_withheld(corpus):
    g = check("That custody be given to the mother under Section 41 of the Divorce Act, 1869.",
              question="Draft a custody ground after khula")
    assert g["counts"]["withheld_sentences"] == 1 and "Christian" in reasons(g)


@pytest.mark.parametrize("community_hint,expect_mflo,expect_divorce", [
    ("Draft a ground in the wife's suit after talaq", "supported", "withheld"),          # known Muslim
    ("Draft a ground for a Christian couple's custody matter", "withheld", "supported"),  # known Christian
    ("Draft a custody and maintenance ground", "not_verified", "not_verified"),          # unknown: nothing presumed
])
def test_personal_law_by_known_or_unknown_community(corpus, community_hint, expect_mflo, expect_divorce):
    def outcome(sentence):
        g = check(sentence, question=community_hint)
        if g["withheld"]:
            return "withheld"
        return "supported" if g["supported"] else ("not_verified" if g["not_checked"] else "?")
    mflo = outcome("That the wife's maintenance is claimed under Section 9 of the Muslim Family Laws Ordinance, 1961.")
    divorce = outcome("That custody of the children be given to the mother under Section 41 of the Divorce Act, 1869.")
    assert (mflo, divorce) == (expect_mflo, expect_divorce)


def test_an_acts_own_name_is_not_evidence_of_the_parties_community(corpus):
    # "...under the CHRISTIAN Marriage Act" must not make the matter Christian.
    g = check("That the marriage was solemnized by a person authorised under Section 5 of the Christian Marriage Act, 1872.")
    assert g["supported"] == [] and any("Christian" in s and "confirm" in s for s in g["not_checked"])


def test_no_community_is_presumed_and_the_reason_says_so(corpus):
    g = check("That the wife's maintenance is claimed under Section 9 of the Muslim Family Laws Ordinance, 1961.")
    assert g["supported"] == []
    assert any("Muslims only" in s and "confirm" in s for s in g["not_checked"])


# ── what stays untouched ────────────────────────────────────────────────────

def test_a_filled_template_without_citations_is_unchanged(corpus):
    text = "SWORN STATEMENT\nDeponent: Sana Ahmed\nParent: Tariq Ahmed\nIdentity card: [CNIC]\nAffirmed at Lahore."
    g = check(text)
    assert g["text"] == text and g["withheld"] == [] and g["counts"] == {"supported": 0, "withheld_sentences": 0, "not_checked": 0}


def test_withheld_text_is_reported_not_silently_erased(corpus):
    g = check("That the plaint ought to be rejected pursuant to CPC 1908 Section 13.")
    assert g["text"] == "" and g["withheld"][0]["text"].startswith("That the plaint") and g["withheld"][0]["reasons"]


def test_research_is_unchanged(corpus):
    from app.ai import visible_authority
    s = "That the plaint ought to be rejected pursuant to CPC 1908 Section 13."
    assert visible_authority.authorities(s, "x", False)[1] == []          # research: not judged for subject

# ── the law context the model sees ──────────────────────────────────────────

def test_the_law_context_names_each_provision_by_what_it_is():
    from app.api.v1.routes.ai import _law_label
    assert _law_label({"provision_label": "Order XXIII Rule 1", "section_number": ""}) == "Order XXIII Rule 1"
    assert _law_label({"section_number": "151"}) == "Section 151"
    assert _law_label({"section_number": "1956"}) == "provision not identified"
    assert _law_label({"section_number": ""}) == "provision not identified"


def test_a_named_order_rule_is_fetched_exactly_and_first(monkeypatch):
    from app.ai import cpc_provisions
    from app.api.v1.routes import ai as routes
    monkeypatch.setattr(cpc_provisions, "catalogue", lambda: CAT)
    got = routes._exact_provisions_for("Add a ground under Order VII Rule 11 CPC")
    assert got and got[0]["exact_provision"] == "Order VII Rule 11 CPC" and "Rejection of plaint" in got[0]["content"]


def test_the_prompt_forbids_section_for_order_rule_and_extra_authorities():
    from app.api.v1.routes.ai import _DRAFT_SYSTEM
    assert "never as a \"Section\"" in _DRAFT_SYSTEM
    assert "provision not identified" in _DRAFT_SYSTEM
    assert "add NO legal citations" in _DRAFT_SYSTEM


def test_drafting_retrieval_reads_the_identity_index_and_labels_chunks(monkeypatch):
    """The base index filed CPC Order rules as sections; the drafter now asks
    for the identity indexes and prints each chunk's real identity."""
    from app.ai.nodes import retrieval_node
    from app.ai.pipelines import retriever
    from app.api.v1.routes import ai as routes
    seen = {}

    class _R:
        def invoke(self, q):
            return ["doc"]
    monkeypatch.setattr(retriever, "build_retriever", lambda ct, pr, variant=None: (seen.update(variant=variant), _R())[1])
    monkeypatch.setattr(retrieval_node, "_docs_to_chunks", lambda docs, prov: [
        {"statute": "CPC 1908", "section_number": "", "provision_kind": "order_rule", "provision_label": "Order XXIII Rule 1",
         "content": "1. Withdrawal of suit ..."},
        {"statute": "CPC 1908", "section_number": "1956", "content": "footnote ..."}])
    law = routes._retrieve_law_context("withdraw the suit", "civil", "sindh")
    assert seen["variant"] == "research_ident"
    assert "CPC 1908 — Order XXIII Rule 1" in law
    assert "Section 1956" not in law and "CPC 1908 — provision not identified" in law


def test_a_dense_but_incomplete_copy_never_withholds_a_missing_section(monkeypatch, corpus):
    """CPC-like: most sections held (dense), some missing (s.114). A missing
    section inside the Act's range is NOT VERIFIED -- our copy is incomplete,
    so 'not held' is not 'does not exist'. In a complete copy it is withheld."""
    held_gappy = {str(n): f"Heading {n}" for n in range(1, 101) if n not in (57, 61, 63, 64, 65, 67, 70, 71, 72, 73)}
    held_full = {str(n): f"Heading {n}" for n in range(1, 101) if n != 57}
    idx = ci.CorpusIndex({**{k: INDEX.coverage(k) for k in INDEX.statutes},
                          "Gappy Act 2000": _cov("Gappy Act 2000", held_gappy),
                          "Complete Act 2001": _cov("Complete Act 2001", held_full)})
    assert idx.coverage("Gappy Act 2000").dense and idx.coverage("Gappy Act 2000").ratio < 0.98
    monkeypatch.setattr(ci, "get_drafter_index", lambda: idx)
    gappy = check("That relief is claimed under Section 57 of the Gappy Act, 2000.")
    assert gappy["withheld"] == [] and any(s.startswith("Section 57") for s in gappy["not_checked"])
    full = check("That relief is claimed under Section 57 of the Complete Act, 2001.")
    assert full["counts"]["withheld_sentences"] == 1



# ── fresh-run (v2_r2) DEV failures, by the dev outputs' own sentences ───────

def _not_supported(g):
    return not g["supported"] and (g["withheld"] or g["not_checked"])


@pytest.mark.parametrize("sentence", [
    # V13 r1: a bracketed citation was never checked -- s.526 for bail SUPPORTED
    "That further inquiry is needed, so post-arrest bail is sought for the accused. (Section 526 CrPC 1898)",
    # V05 r2: bracketed Order/Rule for service of an ex parte decree
    "That the decree was passed ex parte without the plaintiff being served notice as required by law. (Order IX Rule 12 CPC)",
    # V23 r2: one shared word ("notice") made Order XI Rule 17 relevant
    "That this notice is served in accordance with Order XI Rule 17 CPC, which mandates that a statutory notice be given to the Federal Government prior to instituting any suit against it.",
    # V13 r2: an Urdu-only claim cannot be read -> never supported
    "یہ کہ ملزم کے خلاف مزید انکوائری درکار ہے، اس لیے ضمانت کی درخواست سیکشن 526، CrPC 1898 کے تحت کی جاتی ہے۔",
])
def test_false_supports_seen_in_the_fresh_run(corpus, sentence):
    g = check(sentence)
    assert _not_supported(g), g


def test_v23_our_internal_label_never_reaches_the_draft(corpus):
    text = ("That this notice constitutes the statutory notice required under CPC 1908 \u2014 provision not identified "
            "before instituting any suit against the Federal Government.")
    g = check(text)
    assert g["text"] == "" and "internal label" in reasons(g)
    assert "provision not identified" not in g["text"]


def test_v02_a_correct_return_of_plaint_is_kept(corpus):
    s = ("That the plaint is returned to the plaintiff because this Court lacks territorial jurisdiction over the cause "
         "of action, under Order VII Rule 10 CPC, for presentation to the proper Court.")
    g = check(s)
    assert g["withheld"] == [] and g["supported"] == ["Order VII Rule 10 CPC"], reasons(g)


def test_v12_a_title_line_is_neither_withheld_nor_counted(corpus):
    text = ("APPLICATION UNDER SECTION 502 CRPC\n\n"
            "That the Applicant, [NAME OF SURETY], is a surety who seeks to be discharged from the bail bond under "
            "Section 502 of the Code of Criminal Procedure, 1898.")
    g = check(text)
    assert g["withheld"] == [], reasons(g)
    assert g["supported"] == ["Section 502 CrPC 1898"]
    assert not any("502" in x for x in g["not_checked"]), "a supported provision is also listed as not verified"


def test_v12_generic_verbs_never_decide(corpus):
    g = check("That the Applicant also relies upon Section 126 of the Code of Criminal Procedure, 1898, which authorises "
              "the Magistrate to discharge the surety.")
    assert "authorises" not in reasons(g)
    assert g["withheld"] == []


@pytest.mark.parametrize("sentence,expect", [
    ("That the proceedings are an abuse of the process of law and the High Court is empowered to quash such proceedings "
     "under Section 561-A of the Code of Criminal Procedure, 1898.", "561-A"),
    ("That, the cheque having been dishonoured, criminal proceedings will be instituted against the drawer under "
     "Section 489-F of the Pakistan Penal Code.", "489-F"),
])
def test_correct_lettered_citations_are_supported(corpus, sentence, expect):
    g = check(sentence)
    assert g["withheld"] == [] and g["supported"] and expect in g["supported"][0], g


def test_withheld_reasons_never_suggest_what_to_cite(corpus):
    for s in ("That the plaint ought to be rejected pursuant to CPC 1908 Section 13.",
              "That the applicant is entitled to post-arrest bail under Section 499 CrPC.",
              "That the plaint be returned for presentation to the proper court under Order VII Rule 11 CPC.",
              "That the accused is charged with cheating punishable under Section 420 CrPC."):
        r = reasons(check(s))
        assert r and "see " not in r and "it matches" not in r and "is defined in" not in r, r


def test_the_insertable_text_is_the_original_minus_withheld_sentences(corpus):
    good = "That the applicant is entitled to bail under Section 497 CrPC as the offence is non-bailable."
    bad = "That the applicant is entitled to post-arrest bail under Section 499 CrPC."
    urdu = "یہ کہ ملزم ضمانت کا حقدار ہے کیونکہ مقدمہ مزید انکوائری کا ہے، دفعہ ۴۹۷ ضابطہ فوجداری کے تحت۔"
    g = check(f"{good}\n\n{bad}\n\n{urdu}")
    assert g["text"] == f"{good}\n\n{urdu}", "the lawyer would insert something other than the checked text"


def test_a_provision_whose_heading_cannot_be_read_is_never_withheld_by_subject(corpus, monkeypatch):
    """489-F's stored heading is broken by line breaks: no heading -> only its
    text can confirm it; otherwise not verified -- never withheld."""
    from app.ai import exact_provision
    real = exact_provision.fetch

    def fetch(cits, research=False, strict=False):
        out = real(cits, research, strict)
        for c in cits:
            if c.section == "489-F":
                out[exact_provision.label(c)] = [{"statute": "PPC", "section_number": "489-F",
                                                  # no readable heading at all
                                                  "content": "Whoever dishonestly issues a cheque towards re-payment of a loan "
                                                             "... which is dishonoured on presentation ..."}]
        return out
    monkeypatch.setattr(exact_provision, "fetch", fetch)
    monkeypatch.setattr(ci, "get_drafter_index", lambda: ci.CorpusIndex(
        {**{k: INDEX.coverage(k) for k in INDEX.statutes if k != "PPC 1860"},
         "PPC 1860": _cov("PPC 1860", {**{k: v for k, v in PPC.items() if k != "489-F"},
                                       "503": "Criminal intimidation", "405": "Criminal breach of trust",
                                       "120-B": "Punishment of criminal conspiracy", "447": "Punishment for criminal trespass",
                                       "415": "Cheating"})}))
    g = check("That the payor shall pay the amount of the dishonoured cheque within fifteen days, failing which criminal "
              "proceedings will be instituted under Section 489-F of the Pakistan Penal Code.")
    assert g["withheld"] == [], reasons(g)
    assert g["supported"] and "489-F" in g["supported"][0]          # its TEXT says cheque + dishonoured


# ── retrieval: why Order VII Rule 11 was missed ─────────────────────────────

def test_drafting_words_are_dropped_from_the_retrieval_query():
    from app.api.v1.routes.ai import _retrieval_query
    q = _retrieval_query("Plaint", "Draft the grounds for an application seeking rejection of the plaint because it "
                                   "discloses no cause of action. Cite the provision.", "")
    for w in ("Draft", "grounds", "application", "seeking", "Cite", "provision"):
        assert w.lower() not in q.lower().split(), w
    for w in ("rejection", "plaint", "discloses", "cause", "action"):
        assert w in q
    assert _retrieval_query("Bail Application", "Add", "") == "Bail Application Add"   # too little left: unchanged


def test_appendix_forms_never_enter_the_law_context(monkeypatch):
    from app.ai.nodes import retrieval_node
    from app.ai.pipelines import retriever
    from app.api.v1.routes import ai as routes

    class _R:
        def invoke(self, q):
            return ["doc"]
    monkeypatch.setattr(retriever, "build_retriever", lambda ct, pr, variant=None: _R())
    monkeypatch.setattr(retrieval_node, "_docs_to_chunks", lambda docs, prov: [
        {"statute": "CPC 1908", "provision_kind": "appendix", "provision_label": "CPC Appendix", "content": "FORM No. 1 ..."},
        {"statute": "CPC 1908", "provision_kind": "order_rule", "provision_label": "Order VII Rule 11",
         "content": "11. Rejection of plaint ..."}])
    law = routes._retrieve_law_context("rejection plaint", "civil", "sindh")
    assert "Order VII Rule 11" in law and "Appendix" not in law and "FORM No. 1" not in law


def test_a_title_line_with_subject_words_is_never_withheld(corpus):
    g = check("APPLICATION UNDER SECTION 499 CRPC FOR POST-ARREST BAIL")
    assert g["withheld"] == [], reasons(g)
    assert g["supported"] == [] and any("heading line" in x for x in g["not_checked"])


# ── applicability beyond a matching heading (2026-10-15, eval v2 dev) ───────
# Three wrong citations were SUPPORTED because the cited heading agreed with
# some words of the sentence. Each is now NOT VERIFIED with its reason -- never
# withheld (the sentence may be partly right), never supported -- and the
# valid uses around them are unchanged.

TEXT.update({
    ("CrPC", "126"): "126. Discharge of sureties.-- (1) Any surety for the peaceable conduct or good behaviour of another "
                     "person may at any time apply to a Magistrate to cancel any bond executed under this Chapter within "
                     "the local limits of his jurisdiction.",
    ("CrPC", "203"): "203. Dismissal of complaint.-- The Magistrate before whom a complaint is made may dismiss the "
                     "complaint, if, after considering the statement on oath of the complainant, there is in his judgment "
                     "no sufficient ground for proceeding.",
})
_BAIL_BOND = "Draft an application by a surety asking to be discharged from the bail bond. Cite the provision."
_PRE_ARREST = "Draft a ground for pre-arrest (protective) bail citing mala fide on the part of the complainant."


def _with_order_titles(monkeypatch):
    """The fixture catalogue plus Order XXXVII, whose title -- as in the
    identity index -- sits at the end of the previous Order's last rule."""
    from app.ai import cpc_provisions as cp
    rows = [({"statute": "CPC 1908", "provision_kind": "order_rule", "provision_label": f"Order {o} Rule {r}"}, doc)
            for o, r, doc in (
                ("XXXVI", "5", "5. Where value of subject-matter must be stated.- ... ORDER XXXVII \nSUMMARY PROCEDURE ON "
                               "NEGOTIABLE INSTRUMENTS \n"),
                ("XXXVII", "2", "2. Institution of summary suits upon bills of exchange, etc.- (1) All suits upon bills "
                                "of exchange, hundies or promissory notes may ... be instituted ..."),
                ("XXXVII", "4", "4. Power to set aside decree.- After decree the Court may, under special circumstances, "
                                "set aside the decree, and if necessary stay or set aside execution ..."),
            )]
    base = [({"statute": "CPC 1908", "provision_kind": "order_rule", "provision_label": p.label}, p.content)
            for p in CAT["provisions"].values() if p.kind == "order_rule"]
    base += [({"statute": "CPC 1908", "provision_kind": "section", "section_number": p.number}, p.content)
             for p in CAT["provisions"].values() if p.kind == "section"]
    cat = cp.build_catalogue(base + rows)
    monkeypatch.setattr(cp, "catalogue", lambda: cat)
    return cat


_O37 = ("That, pursuant to Order XXXVII Rule 4 CPC, the Court has power to set aside the decree and, if necessary, "
        "stay or set aside its execution.")


def test_v05_a_summary_suit_rule_is_not_verified_for_an_ordinary_ex_parte_decree(corpus, monkeypatch):
    _with_order_titles(monkeypatch)
    g = check(_O37, question="Draft grounds to set aside an ex parte decree obtained by fraud and misrepresentation.")
    assert g["supported"] == []
    assert any("applies only to summary procedure on negotiable instruments" in x for x in g["not_checked"]), g
    assert g["withheld"] == [] and g["text"] == _O37, "a scope doubt must not withhold the sentence"


def test_the_summary_suit_rule_is_supported_in_a_summary_suit(corpus, monkeypatch):
    _with_order_titles(monkeypatch)
    g = check(_O37, question="Draft grounds to set aside the decree in a summary suit on a negotiable instrument.")
    assert g["supported"] == ["Order XXXVII Rule 4 CPC"], g


def test_order_titles_are_read_from_the_code_and_only_class_of_suit_orders_are_scoped(monkeypatch):
    from app.ai import cpc_provisions as cp
    cat = _with_order_titles(monkeypatch)
    assert cp.order_titles(cat)[37] == "SUMMARY PROCEDURE ON NEGOTIABLE INSTRUMENTS"
    title, words = cp.order_scope(cat, 37)
    assert {"summary", "negotiable", "instruments"} <= words and "procedure" not in words
    assert cp.order_scope(cat, 7) is None, "an Order whose title our copy lacks has no scope check"
    fake = {"provisions": {"x": cp.Provision("order_rule", 38, "1", "x", "h", "ORDER XXXIX \nTEMPORARY INJUNCTIONS AND "
                                                                             "INTERLOCUTORY ORDERS")}}
    assert cp.order_titles(fake)[39].startswith("TEMPORARY INJUNCTIONS") and cp.order_scope(fake, 39) is None


def test_v12_a_twin_heading_for_another_kind_of_bond_is_not_verified(corpus):
    accurate = ("That the Applicant also relies upon Section 126 of the Code of Criminal Procedure, 1898, which authorises "
                "any surety for the peaceable conduct or good behaviour of another person to apply to the Magistrate to "
                "cancel any bond executed under this Chapter.")
    g = check(accurate, question=_BAIL_BOND)
    assert g["supported"] == [], g
    assert any(x.startswith("Section 126") and "same heading" in x and "bail" in x for x in g["not_checked"]), g
    assert g["withheld"] == []
    # ... and is supported where the request IS about a peace bond.
    ok = check(accurate, question="Draft an application by a surety for good behaviour asking to cancel the bond.")
    assert ok["supported"] == ["Section 126 CrPC 1898"], ok


def test_v12_a_provision_doubted_in_one_sentence_is_not_listed_as_supported(corpus):
    text = ("That the Applicant also relies upon Section 126 of the Code of Criminal Procedure, 1898, which authorises "
            "any surety for the peaceable conduct or good behaviour of another person to apply to cancel the bond.\n\n"
            "That the Applicant be discharged from the bail bond, in accordance with Sections 502 and 126 of the Code of "
            "Criminal Procedure, 1898.\n\n"
            "That the applicant seeks to be discharged from the said bond pursuant to Section 502 of the Code of Criminal "
            "Procedure, 1898.")
    g = check(text, question=_BAIL_BOND)
    assert "Section 126 CrPC 1898" not in g["supported"], g
    assert any(x.startswith("Section 126") for x in g["not_checked"])
    assert "Section 502 CrPC 1898" in g["supported"], "the valid twin was doubted too"
    assert g["withheld"] == [] and g["text"] == text


@pytest.mark.parametrize("hyphen", ["-", "‑", "‐"])
def test_v11_one_clause_relying_on_a_section_for_two_things_is_not_verified(corpus, hyphen):
    text = (f"That the complaint filed against the Applicant is mala fide, lacking any sufficient ground for proceeding, "
            f"and consequently, in accordance with Section 203 CrPC, the Court may dismiss the complaint and grant "
            f"pre{hyphen}arrest (protective) bail.")
    g = check(text, question=_PRE_ARREST)
    assert g["supported"] == [], g
    assert any(x.startswith("Section 203") and "also relies on it for" in x and "bail" in x for x in g["not_checked"]), g
    assert g["withheld"] == [], "a partly right sentence is not withheld"


def test_the_dismissal_section_alone_is_still_supported(corpus):
    g = check("That the complaint is liable to be dismissed under Section 203 CrPC as there is no sufficient ground for "
              "proceeding.", question="Draft a ground for dismissal of the complaint. Cite the provision.")
    assert g["supported"] == ["Section 203 CrPC 1898"], g


@pytest.mark.parametrize("sentence, question", [
    # V07: the residual inherent power supports an early hearing
    ("That this Court, by virtue of its inherent powers under Section 151 CPC, may fix an early date for the hearing "
     "of this application and issue such notice as may be necessary to secure the ends of justice.",
     "Draft an application asking the court to fix an early hearing date using its inherent powers."),
    # V12: s.502(2) for the warrant, in a bail-bond request
    ("That the Magistrate may issue a warrant of arrest directing the accused to appear before this Court in "
     "accordance with Section 502(2) of the Code of Criminal Procedure, 1898.", _BAIL_BOND),
    # V24: "payment" is covered by the text's "re-payment"
    ("That the payee demands payment of the dishonoured cheque, failing which criminal proceedings will be instituted "
     "under Section 489-F PPC.",
     "Draft a paragraph demanding payment of a dishonoured cheque within fifteen days and warning of criminal proceedings."),
])
def test_valid_uses_in_the_same_requests_stay_supported(corpus, sentence, question):
    g = check(sentence, question=question)
    assert g["supported"] and not g["withheld"], g
    assert not any("also relies on it for" in x or "same heading" in x for x in g["not_checked"]), g


def test_subject_blocks_follow_runs_of_consecutive_headings():
    from app.ai import visible_authority as va
    rows = [("s", int(k), v) for k, v in CRPC.items() if k.isdigit()]
    blocks = va.subject_blocks(rows)
    assert ("s", 497) in blocks[va._stem("bail")] and ("s", 203) not in blocks[va._stem("bail")]
    assert va._stem("surety") not in blocks and va._stem("dismissal") not in blocks, "a scattered word is no block"


def test_the_foreign_subject_must_be_in_the_request_too(corpus):
    """A word the lawyer did not ask about never makes a citation mixed."""
    g = check("That, in accordance with Section 203 CrPC, the Court may dismiss the complaint and grant bail.",
              question="Draft a ground for dismissal of the complaint.")
    assert g["supported"] == ["Section 203 CrPC 1898"], g


# ── nothing left to insert: what to do next (Phase 3) ──────────────────────

def test_an_empty_proposal_carries_a_next_step_by_its_reason(corpus):
    g = check("That this notice constitutes the statutory notice required under CPC 1908 — provision not identified "
              "before instituting any suit against the Federal Government.")
    assert g["text"] == "" and g["next_step"]["kind"] == "not_found"
    assert "[PROVISION]" in g["next_step"]["text"]
    g = check("That the complaint lodged is mala fide and, having no sufficient ground for proceeding, the applicant is "
              "entitled to pre-arrest protective bail pursuant to Section 203 of the Code of Criminal Procedure, 1898.")
    assert g["text"] == "" and g["next_step"]["kind"] == "wrong_authority"
    for step in (g["next_step"]["text"],):
        assert not __import__("re").search(r"Section \d|Order [IVX]+", step), "a next step never names an authority"


def test_a_proposal_with_text_has_no_next_step(corpus):
    g = check("That the Court may, under Section 203 of the Code of Criminal Procedure, 1898, dismiss the complaint.")
    assert g["text"] and g["next_step"] is None


def test_drafter_reasons_name_the_act_in_full(corpus):
    g = check("That the Court may fix an early date of hearing under Section 373 of the Succession Act, 1925, because "
              "the applicant was charged.")
    for r in (r for w in g["withheld"] for r in w["reasons"]):
        assert "Section 373 Succession Act" in r, r


# ── retrieval: practice words -> the statute's own words (Phase 2) ─────────

@pytest.mark.parametrize("instruction, added", [
    ("Draft an application for condonation of a 12-day delay in filing an appeal. Cite the provision.",
     "extension of period sufficient cause"),
    ("Draft grounds to condone the delay.", "extension of period sufficient cause"),
    ("Draft grounds for an application to be added as a necessary party (intervener) to a pending suit.",
     "strike out or add parties"),
    ("Draft an impleadment application.", "strike out or add parties"),
])
def test_practice_terms_add_the_statutes_words_and_keep_the_lawyers(instruction, added):
    from app.api.v1.routes.ai import _retrieval_query
    q = _retrieval_query("Application", instruction, "")
    assert q.endswith(added)
    assert not __import__("re").search(r"\b(?:Section|Order|Rule|Article)\s+\d", q), "a provision number was added"


def test_other_requests_get_no_practice_words():
    from app.api.v1.routes.ai import _retrieval_query
    q = _retrieval_query("Plaint", "Draft the grounds for rejection of the plaint because it discloses no cause of "
                                   "action. Cite the provision.", "")
    assert "extension" not in q and "strike out" not in q


# ── mutation-test gaps (2026-10-15) ─────────────────────────────────────────

def test_a_residual_inherent_power_is_never_mixed(corpus):
    """s.561-A supports any order the ends of justice need -- 'bail' (a CrPC
    block subject) in the same clause does not make it mixed."""
    g = check("That, in exercise of its inherent power under Section 561-A CrPC, the High Court may make such order as "
              "is necessary to secure the ends of justice, including admitting the accused to bail.",
              question="Draft a ground asking the High Court to use its inherent power to grant bail.")
    assert g["supported"] == ["Section 561-A CrPC 1898"], g


def test_a_prefixed_word_in_the_text_covers_the_sentence_word():
    from app.ai import visible_authority as va
    assert va._covers("repayment", "payment") and va._covers("discharge", "discharged")
    assert not va._covers("payment", "repayment"), "only the provision's word may carry the prefix"
    assert not va._covers("rebail", "ba"), "too short to be a stem"


def test_a_provision_valid_in_one_sentence_and_doubted_in_another_is_not_supported(corpus):
    text = ("Section 126 CrPC also deals with the discharge of sureties.\n\n"
            "That the Applicant also relies upon Section 126 of the Code of Criminal Procedure, 1898, which authorises "
            "any surety for the peaceable conduct or good behaviour of another person to apply to cancel the bond.")
    g = check(text, question=_BAIL_BOND)
    assert "Section 126 CrPC 1898" not in g["supported"], g
    assert any(x.startswith("Section 126") and "same heading" in x for x in g["not_checked"]), g


def test_an_order_rule_relied_on_for_another_orders_subject_is_not_verified(corpus):
    g = check("That, pursuant to Order XXIII Rule 1 CPC, the plaintiff may withdraw the suit and the plaint be rejected.",
              question="Draft grounds to withdraw the suit and for rejection of the plaint.")
    assert g["supported"] == [], g
    assert any(x.startswith("Order XXIII Rule 1") and "also relies on it for" in x and "plaint" in x
               for x in g["not_checked"]), g
    ok = check("That, pursuant to Order XXIII Rule 1 CPC, the plaintiff may withdraw the suit.",
               question="Draft grounds to withdraw the suit and for rejection of the plaint.")
    assert ok["supported"] == ["Order XXIII Rule 1 CPC"], ok


def test_a_withheld_reason_names_a_multi_word_act_in_full(corpus):
    g = check("That the custody of the minor be given to the mother under Section 99 of the Guardians and Wards Act, 1890.",
              question="Draft a ground for custody of the minor with the mother.")
    assert g["withheld"], g
    # the authority check's own reason (not the malformed-number one), Act in full
    assert __import__("re").search(r"Section 99 Guardians and Wards Act[^|]*does not exist in the", reasons(g)), reasons(g)


# ── v2_r3 dev (2026-10-15): rule text, rule splitting, procedural scope ─────

_O9_R12 = ("12. Consequence of non-attendance, without sufficient cause shown, of party ordered to appear in person._ "
           "Where a plaintiff or defendant, who has been ordered to appear in person, does not appear in person, or show "
           "sufficient cause to the satisfaction of the Court for failing so to appear, he shall be subject to all the "
           "provisions of the foregoing rules applicable to plaintiffs and defendants, respectively, who do not appear. "
           "Setting aside Decree ex parte 2 [13. Setting aside decree ex­parte against defendant._ (1)] In any case "
           "in which a decree is passed ex parte against a defendant, he may apply to the Court by which the decree was "
           "passed for an order to set it aside; and if he satisfies the Court that the summons was not duly served ...")
_O9_R12_CONT = ("the Court shall make an order setting aside the decree as against him upon such terms as to costs, payment "
                "into Court or otherwise as it thinks fit, and shall appoint a day for proceeding with the suit.")
_O7 = {
    "10": "10. Return of plaint._ (1) Subject to the provisions of rule 10A, the plaint shall at any stage of the suit be "
          "returned to be presented to the Court in which the suit should have been instituted. (2) On returning a "
          "plaint the Judge shall endorse thereon the date of its presentation and return, the name of the party "
          "presenting it, and a brief statement of the reasons for returning it.",
    "11": "11. Rejection of plaint._ The plaint shall be rejected in the following cases:- (a) where it does not disclose "
          "a cause of action; (b) where the relief claimed is undervalued ...",
}


def _cat_with(monkeypatch, extra_rows, sections_extra=()):
    from app.ai import cpc_provisions as cp
    base = [({"statute": "CPC 1908", "provision_kind": "order_rule", "provision_label": p.label}, p.content)
            for p in CAT["provisions"].values() if p.kind == "order_rule"
            and p.label not in {lab for lab, _ in [(m["provision_label"], d) for m, d in extra_rows]}]
    base += [({"statute": "CPC 1908", "provision_kind": "section", "section_number": p.number}, p.content)
             for p in CAT["provisions"].values() if p.kind == "section"]
    cat = cp.build_catalogue(base + list(extra_rows))
    monkeypatch.setattr(cp, "catalogue", lambda: cat)
    return cat


def _rule_row(label, doc, **md):
    return ({"statute": "CPC 1908", "provision_kind": "order_rule", "provision_label": label, **md}, doc)


def test_a_chunk_holding_two_rules_gives_each_rule_only_its_own_text():
    from app.ai import cpc_provisions as cp
    pieces = cp.split_rules(_O9_R12, "Order IX Rule 12")
    assert [lab for lab, _ in pieces] == ["Order IX Rule 12", "Order IX Rule 13"]
    r12, r13 = pieces[0][1], pieces[1][1]
    assert "set" not in r12.lower().replace("subject", "") or "set aside" not in r12.lower()
    assert "ex parte" not in r12 and "decree" not in r12, "Rule 12 still carries Rule 13's words"
    assert r13.startswith("Setting aside Decree ex parte"), "the group heading belongs to the next rule"
    assert "".join(t for _, t in pieces) == _O9_R12, "splitting must not lose or add text"


def test_recorded_offsets_win_and_a_malformed_record_is_ignored():
    from app.ai import cpc_provisions as cp
    cut = _O9_R12.index("Setting aside Decree")
    spans = f"Order IX Rule 12@0;Order IX Rule 13@{cut}"
    assert [t for _, t in cp.split_rules(_O9_R12, "Order IX Rule 12", spans)] == [_O9_R12[:cut], _O9_R12[cut:]]
    for bad in ("Order IX Rule 12@5;Order IX Rule 13@9", f"Order IX Rule 13@{len(_O9_R12) + 5};Order IX Rule 12@0",
                "nonsense"):
        assert [lab for lab, _ in cp.split_rules(_O9_R12, "Order IX Rule 12", bad)] == \
            ["Order IX Rule 12", "Order IX Rule 13"], bad          # falls back to the text's own headings


def test_a_numbered_cross_reference_is_not_a_rule_heading():
    from app.ai import cpc_provisions as cp
    doc = ("5. Procedure when summons not served._ (1) Where the summons is not duly served the Court shall direct a "
           "second summons under rule 8. The Court may also, under rule 9. Postpone the hearing (see Act 5 of 1908. "
           "Section 7).")
    assert [lab for lab, _ in cp.split_rules(doc, "Order IX Rule 5")] == ["Order IX Rule 5"]


def test_the_catalogue_files_rule_13_and_its_continuation_separately_from_rule_12(monkeypatch):
    cat = _cat_with(monkeypatch, [
        _rule_row("Order IX Rule 12", _O9_R12),
        _rule_row("Order IX Rule 13", _O9_R12_CONT),     # ident_v2: the continuation, labelled by the official text
    ])
    r12, r13 = cat["provisions"]["Order IX Rule 12"], cat["provisions"]["Order IX Rule 13"]
    assert "ex parte" not in r12.content and "setting aside the decree" in r13.content
    assert r13.heading.lower().startswith("setting aside decree ex") and _O9_R12_CONT in r13.content


def test_a_rule_12_claim_for_setting_aside_is_not_supported_and_rule_13_is(corpus, monkeypatch):
    _cat_with(monkeypatch, [_rule_row("Order IX Rule 12", _O9_R12), _rule_row("Order IX Rule 13", _O9_R12_CONT)])
    q = "Draft grounds to set aside an ex parte decree."
    bad = check("That the ex parte decree be set aside as the summons was not duly served, under Order IX Rule 12 CPC.",
                question=q)
    assert "Order IX Rule 12 CPC" not in bad["supported"], bad
    good = check("That the ex parte decree be set aside as the summons was not duly served, under Order IX Rule 13 CPC.",
                 question=q)
    assert good["supported"] == ["Order IX Rule 13 CPC"], good


def test_the_law_context_shows_each_rule_under_its_own_label(monkeypatch):
    from app.ai.nodes import retrieval_node
    from app.ai.pipelines import retriever
    from app.api.v1.routes import ai as routes

    class _R:
        def invoke(self, q):
            return ["doc"]
    monkeypatch.setattr(retriever, "build_retriever", lambda ct, pr, variant=None: _R())
    monkeypatch.setattr(retrieval_node, "_docs_to_chunks", lambda docs, prov: [
        {"statute": "CPC 1908", "provision_kind": "order_rule", "provision_label": "Order IX Rule 12", "content": _O9_R12}])
    law = routes._retrieve_law_context("set aside ex parte decree", "civil", "sindh")
    r12_block = law.split("[STATUTE] CPC 1908 — Order IX Rule 13")[0]
    assert "[STATUTE] CPC 1908 — Order IX Rule 13" in law
    assert "ex parte" not in r12_block, "Rule 13 text shown under Rule 12's label"


@pytest.mark.parametrize("sentence, label", [
    # v2_r3 V01 r1: withheld -- "plaint" is too common a heading word; the rule's TEXT says it
    ("That the plaint does not disclose any cause of action, contrary to the requirement of Order VII Rule 11 CPC.",
     "Order VII Rule 11 CPC"),
    # v2_r3 V02 r1/r2: withheld
    ("1. That the plaint is returned to the Court in which the suit should have been instituted, as the present Court "
     "lacks territorial jurisdiction over the subject matter, in accordance with Order VII Rule 10 CPC.",
     "Order VII Rule 10 CPC"),
    ("2. That, pursuant to Order VII Rule 10 CPC, the Judge shall endorse the date of presentation and return, the name "
     "of the party presenting it, and a brief statement of the reasons for returning it.", "Order VII Rule 10 CPC"),
])
def test_v01_v02_a_rule_supported_by_its_own_text_is_not_withheld(corpus, monkeypatch, sentence, label):
    _cat_with(monkeypatch, [_rule_row(f"Order VII Rule {n}", d) for n, d in _O7.items()])
    g = check(sentence, question="Draft grounds for returning the plaint or for rejection of the plaint.")
    assert g["withheld"] == [], reasons(g)
    assert g["supported"] == [label], g


def test_one_common_word_in_a_rules_text_still_does_not_support_it(corpus, monkeypatch):
    _cat_with(monkeypatch, [_rule_row("Order XI Rule 17", "17. Time for inspection when notice given._ The party to "
                                      "whom notice is given shall within ten days deliver notice stating a time for "
                                      "inspection of the documents at the office of his pleader.")])
    g = check("That this notice is served in accordance with Order XI Rule 17 CPC, which mandates that a statutory notice "
              "be given to the Federal Government prior to instituting any suit against it.")
    assert "Order XI Rule 17 CPC" not in g["supported"], g


def test_v07_an_appeal_rule_is_not_verified_for_an_application_in_a_suit(corpus, monkeypatch):
    cat = _cat_with(monkeypatch, [
        _rule_row("Order XL Rule 5", "5. Collector may be appointed receiver._ ... ORDER XLI \nAPPEALS FROM ORIGINAL DECREES \n"),
        _rule_row("Order XLI Rule 12", "12. Day for hearing appeal._ (1) Unless the Appellate Court dismisses the appeal "
                                       "under rule 11, it shall fix a day for hearing the appeal."),
    ])
    from app.ai import cpc_provisions as cp
    assert cp.order_scope(cat, 41)[1] == {"appeals"}
    text = ("That, in accordance with Order XLI Rule 12 CPC, the Court fix a day for hearing the application, taking into "
            "account the urgency of the matter.")
    g = check(text, question="Draft an application asking the court to fix an early hearing date using its inherent powers.")
    assert g["supported"] == [] and any("applies only to appeals" in x for x in g["not_checked"]), g
    ok = check("That, under Order XLI Rule 12 CPC, the Appellate Court shall fix a day for hearing the appeal.",
               question="Draft a paragraph asking the appellate court to fix a day for hearing the appeal.")
    assert ok["supported"] == ["Order XLI Rule 12 CPC"], ok


def test_v12_a_chapter_bound_section_is_not_verified_for_a_bail_bond(corpus):
    TEXT[("CrPC", "122")] = ("122. Power to reject sureties.-- A Magistrate may refuse to accept any particular person "
                             "as surety for good behaviour or for keeping the peace under this Chapter, on the ground "
                             "that such person is an unfit person.")
    CRPC["122"] = "Power to reject sureties"
    try:
        text = ("That under Section 122 CrPC 1898 a Magistrate is empowered to reject or discharge any surety who is "
                "deemed unfit, and the applicant submits that the circumstances satisfy the criteria for such discharge.")
        g = check(text, question=_BAIL_BOND)
        assert g["supported"] == [], g
        assert any(x.startswith("Section 122") and "own Chapter" in x and "bail" in x for x in g["not_checked"]), g
        assert g["withheld"] == []
        ok = check(text, question="Draft an application to reject an unfit surety offered for keeping the peace.")
        assert ok["supported"] == ["Section 122 CrPC 1898"], ok
    finally:
        TEXT.pop(("CrPC", "122")); CRPC.pop("122")


def test_a_chapter_bound_section_on_its_own_subject_is_still_supported(corpus):
    """s.502's own text mentions bail: a bail-bond request is its subject."""
    g = check("That the applicant seeks to be discharged from the said bond pursuant to Section 502 of the Code of "
              "Criminal Procedure, 1898.", question=_BAIL_BOND)
    assert g["supported"] == ["Section 502 CrPC 1898"], g


def test_both_queries_reach_the_law_context_and_neither_loses_its_best_hits(monkeypatch):
    from app.ai.nodes import retrieval_node
    from app.ai.pipelines import retriever
    from app.api.v1.routes import ai as routes
    asked = []

    class _R:
        def invoke(self, q):
            asked.append(q)
            return [q]
    monkeypatch.setattr(retriever, "build_retriever", lambda ct, pr, variant=None: _R())
    hits = {"clean": [("CPC 1908", "Order VII Rule 11", "11. Rejection of plaint")] + [("X", f"Section {i}", f"c{i}") for i in range(6)],
            "raw": [("CrPC 1898", "Section 502", "502. Discharge of sureties")] + [("Y", f"Section {i}", f"r{i}") for i in range(6)]}
    monkeypatch.setattr(retrieval_node, "_docs_to_chunks", lambda docs, prov: [
        {"statute": s, "section_number": lab.split()[-1], "content": t} for s, lab, t in hits[docs[0]]])
    law = routes._retrieve_law_context("clean", "civil", "sindh", "raw")
    assert asked == ["clean", "raw"]
    assert "Section 11" in law and "Section 502" in law and law.count("[STATUTE]") == 8, "6 cleaned + 2 raw"
    assert law.index("Section 11") < law.index("c4") < law.index("Section 502"), "the cleaned top six keep their places"


def test_raw_hits_are_added_after_the_cleaned_six_never_instead():
    from app.api.v1.routes.ai import _with_raw_hits
    a = [{"statute": "A", "content": str(i)} for i in range(8)]
    b = [{"statute": "A", "content": "2"}, {"statute": "B", "content": "9"}, {"statute": "B", "content": "8"},
         {"statute": "B", "content": "7"}]
    assert [c["content"] for c in _with_raw_hits(a, b)] == ["0", "1", "2", "3", "4", "5", "9", "8"]
    assert _with_raw_hits(a, []) == a[:6]


def test_the_prompt_forbids_stating_facts_the_lawyer_did_not_give():
    from app.api.v1.routes.ai import _DRAFT_SYSTEM
    assert "Never state a fact the lawyer has not given" in _DRAFT_SYSTEM
    assert "[placeholder]" in _DRAFT_SYSTEM


def test_one_distinctive_word_shared_with_a_rules_text_does_not_support_it(corpus, monkeypatch):
    _cat_with(monkeypatch, [_rule_row(f"Order VII Rule {n}", d) for n, d in _O7.items()])
    g = check("That the respondent shall endorse the cheque in favour of the applicant, under Order VII Rule 10 CPC.",
              question="Draft a ground about the cheque.")
    assert "Order VII Rule 10 CPC" not in g["supported"], g


def test_recorded_offsets_cut_where_the_text_shows_no_heading():
    """ident_v2 offsets come from the official text; they cut even where the
    chunk's own text has no recognisable heading for the next rule."""
    from app.ai import cpc_provisions as cp
    doc = "4. First rule text ends here. the second rule begins without a numbered heading in this copy."
    cut = doc.index("the second")
    assert [lab for lab, _ in cp.split_rules(doc, "Order X Rule 4")] == ["Order X Rule 4"]
    pieces = cp.split_rules(doc, "Order X Rule 4", f"Order X Rule 4@0;Order X Rule 5@{cut}")
    assert pieces == [("Order X Rule 4", doc[:cut]), ("Order X Rule 5", doc[cut:])]


# ── S1-S3: what the sentence CLAIMS (draft_claims, 2026-10-15) ───────────────

_O14_R5 = ("5. Power to amend, and strike out, issues.__ (1) The Court may at any time before passing a decree amend the "
           "issues or frame additional issues on such terms as it thinks fit, and all such amendments or additional issues "
           "as may be necessary for determining the matters in controversy between the parties shall be so made or framed. "
           "(2) The Court may also, at any time before passing a decree, strike out any issues that appear to it to be "
           "wrongly framed or introduced.")
_O6_R17 = ("17. Amendment of pleadings._ The Court may at any stage of the proceedings allow either party to alter or amend "
           "his pleadings in such manner and on such terms as may be just.")
_S341 = ("341. Procedure where accused does not understand proceedings.-- If the accused, though not insane, cannot be made "
         "to understand the proceedings, the Court may proceed with the trial; and, in the case of a Court other than a "
         "High Court, if such trial results in a conviction, the proceedings shall be forwarded to the High Court.")


def _claims_cat(monkeypatch):
    _cat_with(monkeypatch, [_rule_row("Order XIV Rule 5", _O14_R5), _rule_row("Order VI Rule 17", _O6_R17)])


def test_s1_v04_amending_parties_under_the_issues_rule_is_not_verified_never_withheld(corpus, monkeypatch):
    _claims_cat(monkeypatch)
    text = ("That, under Order XIV Rule 5 CPC, the Court may amend the parties before passing a decree, to prevent "
            "multiplicity of proceedings.")
    g = check(text, question="Draft grounds for an application to be added as a necessary party.")
    assert g["supported"] == [] and g["withheld"] == [] and g["text"] == text, g
    assert any(x.startswith("Order XIV Rule 5") and "amending issues" in x and "not parties" in x
               for x in g["not_checked"]), g


@pytest.mark.parametrize("sentence, label", [
    ("That, under Order XIV Rule 5 CPC, the Court may amend the issues before passing a decree.", "Order XIV Rule 5 CPC"),
    ("That the plaintiff may be allowed to amend the plaint under Order VI Rule 17 CPC.", "Order VI Rule 17 CPC"),
])
def test_s1_the_same_action_on_the_same_object_stays_supported(corpus, monkeypatch, sentence, label):
    _claims_cat(monkeypatch)
    g = check(sentence, question="Draft grounds for amending the pleadings and the issues.")
    assert g["supported"] == [label], g


def test_s1_a_passive_clause_is_not_judged_by_the_object_check(corpus, monkeypatch):
    _claims_cat(monkeypatch)
    g = check("That the issues be amended under Order XIV Rule 5 CPC before the decree is passed.",
              question="Draft grounds for amending the issues.")
    assert not any("provides for" in x for x in g["not_checked"]), g


def _with_341():
    TEXT[("CrPC", "341")] = _S341
    CRPC["341"] = "Procedure where accused does not understand proceedings"


def _without_341():
    TEXT.pop(("CrPC", "341"), None)
    CRPC.pop("341", None)


def test_s2_v09_an_effect_the_provision_contradicts_is_withheld_with_its_text(corpus):
    _with_341()
    try:
        text = ("That the trial of the accused, who cannot understand the proceedings, contravenes Section 341 CrPC, "
                "rendering the proceedings invalid.")
        g = check(text, question="Draft grounds: the accused cannot understand the proceedings; quash them.")
        assert g["text"] == "" and "own text says otherwise" in reasons(g) and "may proceed with the trial" in reasons(g), g
    finally:
        _without_341()


def test_s2_a_negated_effect_and_a_silent_text(corpus):
    _with_341()
    try:
        neg = check("That under Section 341 CrPC the trial does not become invalid where the accused cannot understand "
                    "the proceedings.", question="the accused cannot understand the proceedings")
        assert "says otherwise" not in reasons(neg), neg
    finally:
        _without_341()
    silent = check("That the complaint is void and is liable to be dismissed under Section 203 CrPC.",
                   question="Draft a ground for dismissal of the complaint.")
    assert silent["withheld"] == [] and silent["supported"] == [], silent
    assert any(x.startswith("Section 203") and "does not say this makes anything void" in x for x in silent["not_checked"])


_V09 = ("That the accused, though not insane, is unable to understand the proceedings, and the continuation of the trial "
        "is an abuse of the process of the Court under Section 561-A of the Code of Criminal Procedure, 1898.")
_V09_Q = "Draft grounds for a petition to the High Court to quash criminal proceedings that are an abuse of process."


def test_s3_v09_an_invented_fact_never_reaches_the_insertable_text(corpus):
    g = check(_V09, question=_V09_Q)
    assert "insane" not in g["text"] and "unable to understand" not in g["text"], g["text"]
    assert "states a fact you did not give" in reasons(g) and "insane" in reasons(g)


def test_s3_the_placeholder_alternative_is_itself_checked(corpus):
    g = check(_V09, question=_V09_Q)
    alt = g["placeholder_alternative"]
    assert alt and "[fact to be supplied]" in alt["text"] and "insane" not in alt["text"], g
    assert alt["supported"] == ["Section 561-A CrPC 1898"], alt
    _with_341()
    try:
        both = check(_V09.replace("an abuse of the process of the Court under Section 561-A of the Code of Criminal "
                                  "Procedure, 1898", "invalid under Section 341 CrPC"), question=_V09_Q)
        # the placeholder version still relies on s.341 for invalidity -- the guard withholds it there too
        assert not both["placeholder_alternative"] or "invalid" not in both["placeholder_alternative"]["text"], both
    finally:
        _without_341()


@pytest.mark.parametrize("sentence, given", [
    (_V09, "the accused, though not insane, is unable to understand the proceedings; quash them"),
    ("That the deponent Sana Ahmed d/o Tariq Ahmed resides in Lahore.", "name Sana Ahmed, father Tariq Ahmed, address Lahore"),
    ("That the payment be made within fifteen (15) days of this notice.", "demand payment within fifteen days"),
    ("That the minor children reside with the mother.", "custody of the minor children with the mother"),
    ("1. That under Section 489-F PPC and Order VII Rule 11 CPC, read with Article 95 of the Limitation Act, 1908, the "
     "suit lies.", "x"),
])
def test_s3_facts_the_lawyer_gave_and_citation_numbers_are_never_flagged(corpus, sentence, given):
    from app.ai import draft_claims
    assert draft_claims.invented_facts(sentence, given) == []


@pytest.mark.parametrize("sentence, expect", [
    ("That the cheque for Rs. 500,000 dated 12-03-2025 was dishonoured.", {"500,000", "12-03-2025"}),
    ("That the respondent Mr. Kamran Butt has absconded.", {"absconded", "Kamran Butt"}),
    ("That the accused is a juvenile and was hospitalised.", {"juvenile", "hospitalised"}),
])
def test_s3_numbers_names_and_conditions_not_given_are_flagged(sentence, expect):
    from app.ai import draft_claims
    assert set(draft_claims.invented_facts(sentence, "Draft a ground.")) == expect


def test_s3_an_urdu_draft_is_not_falsely_flagged(corpus):
    from app.ai import draft_claims, draft_guard
    text = draft_guard.normalise("یہ کہ ملزم کے خلاف مزید انکوائری درکار ہے، اس لیے درخواست سیکشن 497، CrPC 1898 کے تحت کی جاتی ہے۔")
    assert draft_claims.invented_facts(text, "x") == []


@pytest.mark.parametrize("sentence, lead", [
    # replay v2_r3 false flags (2026-10-15): clause numbers, and Urdu section numbers split from their "Section"
    ("2.1 The Consultant shall not compete with the business [placeholder].", ""),
    ("3.2.1 The parties agree to arbitration in Karachi.", ""),
    ("141، پاکستان پینل کوڈ کے تحت غیر قانونی اجتماع کا ہے۔", "یہ کہ مقدمہ Section."),
    ("35 کے تحت ہر شریک کو اسی طرح ذمہ دار ٹھہرایا جاتا ہے۔", "دفعہ Section."),
])
def test_s3_clause_numbers_and_split_urdu_citations_are_not_facts(sentence, lead):
    from app.ai import draft_claims
    assert draft_claims.invented_facts(sentence, "Add a clause; Karachi", lead=lead) == []


@pytest.mark.parametrize("sentence, given, expect", [
    # replay v2_r3 V20: an invented non-compete period was missed
    ("The Consultant shall not compete for a period of twelve (12) months after termination.",
     "Add a non-compete clause for after the consultant leaves.", ["twelve (12) months"]),
    ("The notice period shall be thirty days.", "Draft a notice clause.", ["thirty days"]),
    ("The notice period shall be thirty days.", "Draft a notice clause with a thirty day period.", []),
    ("Payment within fifteen (15) days.", "demand payment within fifteen days", []),
])
def test_s3_quantities_in_words_are_checked_against_the_input(sentence, given, expect):
    from app.ai import draft_claims
    assert draft_claims.invented_facts(sentence, given) == expect
    if expect:
        assert "[placeholder]" in draft_claims.with_placeholders(sentence, expect)


def test_s1_a_section_relied_on_for_another_object_is_not_verified(corpus):
    """s.502's text discharges the BOND / sureties, not the accused."""
    g = check("That the Magistrate may discharge the accused under Section 502 CrPC.", question=_BAIL_BOND)
    assert g["supported"] == [] and g["withheld"] == [], g
    assert any(x.startswith("Section 502") and "provides for discharging" in x and "not accused" in x
               for x in g["not_checked"]), g


def test_s3_a_citation_word_left_in_the_previous_unit_still_marks_the_number(corpus):
    """The Urdu normaliser turns "سیکشن" into "Sec." and the splitter cuts after it: "22" opens the next unit."""
    g = check("یہ کہ ملزم کی درخواست سیکشن 141 میں درج شرط کے مطابق ہے۔")    # 3 digits: never a list marker
    assert not any("fact you did not give" in r for w in g["withheld"] for r in w["reasons"]), g


# ── v2_r4 dev fixes (2026-10-15) ────────────────────────────────────────────

def test_s1_a_citation_between_the_modal_and_the_verb_does_not_hide_the_action(corpus, monkeypatch):
    _claims_cat(monkeypatch)
    g = check("That the Court may, under Order XIV Rule 5 CPC, amend the parties and issues before passing a decree.",
              question="Draft grounds for an application to be added as a necessary party.")
    assert "Order XIV Rule 5 CPC" not in g["supported"] and g["withheld"] == [], g
    assert any("not parties" in x for x in g["not_checked"]), g


def test_v02_a_correct_rule_read_from_its_whole_sentence_is_not_withheld(corpus, monkeypatch):
    _cat_with(monkeypatch, [_rule_row(f"Order VII Rule {n}", d) for n, d in _O7.items()])
    g = check("That the plaint is returned to the plaintiff for filing in the appropriate court having territorial "
              "jurisdiction, as this Court lacks such jurisdiction, in accordance with Order VII Rule 10.",
              question="Draft grounds for returning the plaint because this court lacks territorial jurisdiction.")
    assert g["withheld"] == [], reasons(g)
    assert g["supported"] == ["Order VII Rule 10 CPC"], g


def test_s3_namely_section_is_a_citation_not_a_name():
    from app.ai import draft_claims
    s = ("That the suit is instituted under the provisions of the Family Courts Act, 1964, namely Section 7, which "
         "authorises institution of suits.")
    assert draft_claims.invented_facts(s, "Draft the jurisdiction paragraph.") == []
    assert draft_claims.invented_facts("The witness, namely Asif Raza, saw the accused.", "Draft a ground.") == ["Asif Raza"]


# ── the CPC on file is Punjab's: a Sindh draft cannot have it "supported" ────

def test_a_cpc_rule_in_a_sindh_draft_is_not_checked_not_supported(corpus):
    text = "That the plaint is liable to be rejected under Order VII Rule 11 CPC as it discloses no cause of action."
    punjab, sindh = check(text, province="punjab"), check(text, province="sindh")
    assert "Order VII Rule 11 CPC" in punjab["supported"]
    assert "Order VII Rule 11 CPC" not in sindh["supported"]
    # Batch 5: only the authority clause is taken out; the ground itself stays,
    # and the separate placeholder version names Sindh.
    assert sindh["text"].strip() == "That the plaint is liable to be rejected as it discloses no cause of action."
    assert any("Punjab version" in r and "Sindh" in r for w in sindh["withheld"] for r in w["reasons"])
    assert "[Verify the applicable CPC provision for Sindh]" in sindh["placeholder_alternative"]["text"]
