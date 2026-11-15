"""Release blockers from the tool-contract evals (2026-10-14): what the lawyer
finally SEES must not assert what the system cannot stand behind.

E11 (evals/research/results/on_d1, on_d2): "Within what time must a suit for
pre-emption be filed in Punjab?"
  d2 -- retrieval missed Punjab Pre-emption Act s.30 (heading "Limitation"),
        so the answer said "the Act itself is silent on the limitation period"
        and sent the lawyer to the general Limitation Act. s.30 exists: four
        months (corpus text = the official text).
  d1 -- s.30 WAS retrieved and "four months" was shown, verified -- beside a
        "Period not verified ... withheld" notice. The notice contradicted the
        answer.
RU2 d2: the visible answer advised bail "under Section 438 CrPC" (omitted in
Pakistan -- official CrPC: "438. [Omitted]"), called criminal breach of trust
"Section 406 CrPC" (CrPC 406 = appeal from an order requiring security; the
offence is PPC 406) and listed "437-438 CrPC" (437 omitted by the Law Reforms
Ordinance 1972). Unresolved / unsupported chips sat beside them; the
propositions stayed visible.

ROUTE-LEVEL tests run the real ai_research handler and the real graph
(fixture from test_research_safeguards); model calls are scripted and the
corpus heading index is a fixture.
"""
from __future__ import annotations

import pytest

from tests.test_research_safeguards import ask, research  # noqa: F401  (fixture)

PPA = "Punjab Pre-emption Act 1991"
S30 = {"statute": PPA, "section_number": "30", "chunk_id": "statutes_punjab_pre_emption_act_1991_0074",
       "province": "punjab", "source_file": "ppa.pdf",
       "content": "30. Limitation.– The period of limitation for a suit to enforce a right of pre-emption under "
                  "this Act shall be four months from the date– (a) of the registration of the sale deed; (b) of "
                  "the attestation of the mutation, if the sale is made other wise than through a registered sale "
                  "deed; (c) on which the vendee takes physical possession of the property if the sale is made "
                  "otherwise than through a registered sale deed or a mutation; or (d) of knowledge by the "
                  "pre -emptor, if the sale is not covered under paragraph (a) or paragraph (b) or paragraph (c)."}
S1 = {"statute": PPA, "section_number": "1", "chunk_id": "statutes_punjab_pre_emption_act_1991_0001",
      "province": "punjab", "source_file": "ppa.pdf",
      "content": "1. Short title, extent and commencement .– (1) This Act may be called the Punjab Pre-emption "
                 "Act, 1991. (2) It extends to the whole of the Province of the Punjab."}
S11 = {"statute": PPA, "section_number": "11", "chunk_id": "statutes_punjab_pre_emption_act_1991_0040",
       "province": "punjab", "source_file": "ppa.pdf",
       "content": "11. Sale of appurtenances of land.– Where only trees or a building is sold without land, no "
                  "right of pre-emption shall exist."}
PPC_420 = {"statute": "PPC 1860", "section_number": "420", "chunk_id": "statutes_ppc_1860_0661",
           "province": "federal", "source_file": "ppc.pdf",
           "content": "420. Cheating and dishonestly inducing delivery of property: Whoever cheats and thereby "
                      "dishonestly induces the person deceived to deliver any property ... shall be punished with "
                      "imprisonment of either description for a term which may extend to seven years, and shall "
                      "also be liable to fine."}
CRPC_438 = {"statute": "CrPC 1898", "section_number": "438", "chunk_id": "crpc_438", "province": "federal",
            "source_file": "crpc.pdf", "content": "438. [Omitted]."}
CRPC_437 = {"statute": "CrPC 1898", "section_number": "437", "chunk_id": "crpc_437", "province": "federal",
            "source_file": "crpc.pdf", "content": "437. [Omitted by Law Reforms Ordinance, XII of 1972, Sch.]"}
CRPC_406 = {"statute": "CrPC 1898", "section_number": "406", "chunk_id": "crpc_406", "province": "federal",
            "source_file": "crpc.pdf",
            "content": "406. Appeal from order requiring security for keeping the peace or for good behaviour. Any "
                       "person who has been ordered by a Magistrate under section 118 to give security ..."}
CRPC_239 = {"statute": "CrPC 1898", "section_number": "239", "chunk_id": "crpc_239", "province": "federal",
            "source_file": "crpc.pdf", "content": "239. What persons may be charged jointly. The following persons ..."}
CRPC_302 = {"statute": "CrPC 1898", "section_number": "302", "chunk_id": "crpc_302", "province": "federal",
            "source_file": "crpc.pdf", "content": "302. Power to withdraw from prosecution in trial ..."}


class _Cov:
    def __init__(self, provisions, dense=True):
        self.provisions, self.sections, self.dense = provisions, set(provisions), dense

    def headings(self, section):
        return self.provisions.get(section, ())

    def has(self, section):
        return section in self.provisions

    def is_omitted(self, section):
        return False


class _Index:
    def __init__(self, cov):
        self.cov = cov

    @property
    def statutes(self):
        return list(self.cov)

    def coverage(self, statute):
        from app.ai.answer_citations import normalise_statute
        for name, c in self.cov.items():
            if normalise_statute(name) == normalise_statute(statute):
                return c
        return None


INDEX = _Index({
    PPA: _Cov({"1": ("Short title, extent and commencement",), "11": ("Sale of appurtenances of land",),
               "12": ("Right to revoke sale",), "13": ("Demand of pre-emption",), "30": ("Limitation",)}),
    "Punjab Pre-emption (Removal of Doubts) Ordinance 1972": _Cov({"1": ("Short title",)}, dense=False),
    "Sindh Pre-emption Act 1994": _Cov({"31": ("Limitation",)}),
    "Limitation Act 1908": _Cov({"3": ("Dismissal of suits, etc., instituted after period of limitation",)}),
    "PPC 1860": _Cov({"302": ("Punishment of qatl-i-amd",), "406": ("Punishment for criminal breach of trust",),
                      "420": ("Cheating and dishonestly inducing delivery of property",)}),
    "CrPC 1898": _Cov({"154": ("Information in cognizable cases",), "239": ("What persons may be charged jointly",), "302": ("Power to withdraw from prosecution",),
                       "406": ("Appeal from order requiring security for keeping the peace or for good behaviour",),
                       "437": (), "438": (), "439": ("High Court's powers of revision",), "497": ("When bail may be taken in case of non-bailable offence",),
                       "498": ("Power to direct admission to bail or reduction of bail",)}),
})


@pytest.fixture
def corpus(research, monkeypatch):
    from app.ai import corpus_index
    monkeypatch.setattr(corpus_index, "get_index", lambda: INDEX)
    research["exact"].update({"Section 30 Punjab": [S30], "Section 438 CrPC": [CRPC_438],
                              "Section 437 CrPC": [CRPC_437], "Section 406 CrPC": [CRPC_406],
                              "Section 239 CrPC": [CRPC_239], "Section 420 PPC": [PPC_420],
                              "Section 302 CrPC": [CRPC_302]})
    research["triage"] = ["civil"]
    return research


# ── E11 d2: whole-Act silence from a few retrieved sections ──────────────────

E11_D2 = ("**Applicable Law:**\n- Punjab Pre‑emption Act 1991 — Section 1 (short title, extent and "
          "commencement) [1]\n\n**Legal Analysis:**\nSection 1 of the Punjab Pre‑emption Act, 1991 merely states "
          "that the Act is in force throughout Punjab and does not contain any provision on limitation periods for a "
          "pre‑emption suit [1].\nSince the Act itself is silent on the limitation period, the time for filing "
          "such a suit must be determined from the general limitation provisions applicable to civil suits in Punjab "
          "(e.g., the Limitation Act, 1908).\n\n**Conclusion:**\nThe Punjab Pre‑emption Act, 1991 does not "
          "specify a time limit for filing a pre‑emption suit; the suit must be filed within the ordinary "
          "limitation period for civil actions.")
WHOLE_ACT_SILENT = r"(?i)act itself is silent|act,? 1991 does not specify|act (?:does not|doesn't) (?:specify|prescribe|contain)"


def test_e11_the_governing_provision_is_found_by_its_heading(corpus):
    corpus["chunks"] = [S1, S11]                       # the d2 retrieval: s.30 missed
    corpus["gen"] = ["Section 30 of the Punjab Pre-emption Act 1991 fixes four months from the registration "
                     "of the sale deed [1]."]
    ask("Within what time must a suit for pre-emption be filed in Punjab?", session="va-e11-head")
    prompt = corpus["gen_calls"][-1][-1]["content"]
    assert "30. Limitation" in prompt, "s.30 (heading 'Limitation') was not brought into the evidence"
    assert prompt.index("30. Limitation") < prompt.index("1. Short title"), "the governing provision comes first"


def test_e11_a_few_sections_never_become_a_whole_act_silence_claim(corpus):
    import re
    corpus["chunks"] = [S1, S11]
    corpus["gen"] = [E11_D2]                            # the d2 answer, verbatim in substance
    resp = ask("Within what time must a suit for pre-emption be filed in Punjab?", session="va-e11-silent")
    assert not re.search(WHOLE_ACT_SILENT, resp["answer"]), resp["answer"]
    assert "Section 30" in resp["answer"] and "Limitation" in resp["answer"], \
        "the visible answer must point to the provision whose heading governs the issue"


def test_e11_a_withheld_notice_never_contradicts_a_verified_visible_period(corpus):
    corpus["chunks"] = [S30]
    corpus["gen"] = ["Section 30 of the Punjab Pre-emption Act 1991 provides that a suit to enforce a right of "
                     "pre-emption must be filed within four months from the registration of the sale deed [1].\n"
                     "The buyer must also pay the price within four months [1]."]
    resp = ask("Within what time must a suit for pre-emption be filed in Punjab?", session="va-e11-notice")
    assert "four months from the registration" in resp["answer"]
    assert "Period not verified: a time limit or term stated in the draft answer could not be verified" \
        not in resp["answer"], "generic 'not verified' notice beside the verified period"
    assert "pay the price within four months" not in resp["answer"]


# ── RU2 d2: invalid authorities in the visible answer ────────────────────────

RU2_D2 = ("1. **سیکشن 420 PPC** – Cheating and dishonestly inducing delivery of "
          "property [1]\n"
          "سیکشن 420 PPC کے تحت سزا قید "
          "seven years تک اور fine ہے [1]۔\n"
          "3. **سیکشن 239 اور 437‑438 CrPC** – ضمانت "
          "کے اصول\n"
          "| **قابلِ ضمانت** | سیکشن 420 "
          "غیر قابلِ ضمانت ہے، "
          "لیکن **سیکشن 438 CrPC** کے تحت "
          "عدالت کی صوابدید سے "
          "ضمانت دی جا سکتی ہے۔ |\n"
          "| **متعلقہ جرائم** | اگر criminal "
          "breach of trust (Section 406 CrPC) شامل ہو تو ملزم "
          "کو متعدد سیکشنز کے تحت "
          "ملزم بنایا جا سکتا ہے۔ |")


def test_ru2_omitted_and_mispaired_authorities_are_not_left_visible(corpus):
    corpus["triage"] = ["criminal"]
    corpus["chunks"] = [PPC_420]
    corpus["gen"] = [RU2_D2]
    resp = ask("Section 420 PPC kya kehta hai? detail mein batao", session="va-ru2")
    shown = resp["answer"]
    assert "438 CrPC" not in shown.split("Withheld")[0], "bail under omitted CrPC 438 left visible"
    assert "437‑438 CrPC" not in shown and "437-438 CrPC" not in shown
    assert "(Section 406 CrPC)" not in shown, "criminal breach of trust named as a CrPC section"
    assert "Cheating and dishonestly inducing delivery of property [1]" in shown, "the valid part was lost"
    assert "Withheld" in shown or "روک" in shown, "the lawyer is not told what was withheld"


# ── generalisation: the guard reads the corpus, it does not ban strings ──────

@pytest.fixture
def va(monkeypatch):
    """visible_authority against the fixture corpus, without the graph."""
    from app.ai import corpus_index, exact_provision
    from app.ai import visible_authority as V
    monkeypatch.setattr(corpus_index, "get_index", lambda: INDEX)
    texts = {"Section 438 CrPC": [CRPC_438], "Section 437 CrPC": [CRPC_437], "Section 406 CrPC": [CRPC_406],
             "Section 239 CrPC": [CRPC_239], "Section 420 PPC": [PPC_420], "Section 302 CrPC": [CRPC_302],
             "Section 497 CrPC": [{"statute": "CrPC 1898", "content": "497. When bail may be taken in case of "
                                   "non-bailable offence. (1) When any person accused ..."}],
             "Section 406 PPC": [{"statute": "PPC 1860", "content": "406. Punishment for criminal breach of trust: "
                                  "Whoever commits criminal breach of trust shall be punished ..."}],
             "Section 302 PPC": [{"statute": "PPC 1860", "content": "302. Punishment of qatl-i-amd: Whoever ..."}],
             "Section 30 Punjab": [S30]}
    monkeypatch.setattr(exact_provision, "fetch",
                        lambda cits, research=False: {exact_provision.label(c): texts.get(exact_provision.label(c), [])
                                                      for c in cits})
    return V


@pytest.mark.parametrize("sentence,status", [
    ("Pre-arrest bail can be sought under Section 438 CrPC.", "omitted"),                 # English
    ("\u0636\u0627\u0628\u0637\u06c1 \u0641\u0648\u062c\u062f\u0627\u0631\u06cc \u06a9\u06cc \u062f\u0641\u0639\u06c1 "
     "438 \u06a9\u06d2 \u062a\u062d\u062a \u0636\u0645\u0627\u0646\u062a \u0645\u0644 \u0633\u06a9\u062a\u06cc \u06c1\u06d2\u06d4",
     "omitted"),                                                                        # Urdu
    ("dafa 438 CrPC ke tehat zamanat mil sakti hai.", "omitted"),                       # Roman Urdu
    ("Bail under Section\u00a0438\u202fCrPC is discretionary.", "omitted"),            # Unicode spaces
    ("The accused is charged with murder under Section 302 CrPC.", "mispaired"),       # offence in a procedural code
    ("Criminal breach of trust is punishable under Section 406 CrPC.", "mispaired"),
    ("Section 999 PPC punishes cheating.", "absent"),                                  # no such section, complete Act
])
def test_invalid_or_mispaired_authorities_are_withheld(va, sentence, status):
    shown, withheld = va.authorities(f"Intro [1].\n{sentence}\nSection 420 PPC punishes cheating with seven years [1].",
                                     "What is the law?", urdu=False)
    assert [p["status"] for w in withheld for p in w["problems"]] == [status], withheld
    assert sentence not in shown
    assert "Section 420 PPC punishes cheating with seven years [1]." in shown          # the valid part kept


@pytest.mark.parametrize("sentence", [
    "Bail in a non-bailable offence is governed by Section 497 CrPC.",                  # valid procedural
    "Criminal breach of trust is punishable under Section 406 PPC.",                    # correct pairing
    "Section 438 CrPC has been omitted in Pakistan; pre-arrest bail is sought under Section 498 CrPC.",
    "Murder (qatl-i-amd) is punishable under Section 302 PPC.",
])
def test_valid_authorities_and_statements_about_omission_are_kept(va, sentence):
    shown, withheld = va.authorities(sentence, "What is the law?", urdu=False)
    assert withheld == [] and shown == sentence


def test_a_comparative_question_may_discuss_indian_provisions(va):
    s = "In India, anticipatory bail is granted under Section 438 CrPC; Pakistan uses Section 498 CrPC."
    shown, withheld = va.authorities(s, "How does India's Section 438 CrPC compare with Pakistan's bail law?",
                                     urdu=False)
    assert withheld == [] and shown == s


def test_most_of_an_answer_on_invalid_authority_becomes_a_limited_answer(va):
    s = ("Bail is under Section 438 CrPC.\nAlso Section 437 CrPC lets the court grant bail.\n"
         "And Section 999 PPC adds a penalty.")
    shown, withheld = va.authorities(s, "bail?", urdu=False)
    assert shown.startswith("I could not produce a reliable answer") and len(withheld) == 3


def test_whole_act_silence_is_scoped_but_an_honest_scoped_sentence_is_kept(va):
    shown, replaced = va.whole_act_silence(
        "The supplied sections of the Act do not specify the period.", "pre-emption limitation", "punjab", False)
    assert replaced == []
    shown, replaced = va.whole_act_silence(
        "The Punjab Pre-emption Act 1991 does not prescribe a limitation period.",
        "Within what time must a suit for pre-emption be filed in Punjab?", "punjab", False)
    assert replaced and "Section 30" in shown and "Limitation" in shown
    shown, replaced = va.whole_act_silence(
        "\u0627\u06cc\u06a9\u0679 \u0627\u0633 \u0628\u0627\u0631\u06d2 \u0645\u06cc\u06ba \u062e\u0627\u0645\u0648\u0634 "
        "\u06c1\u06d2\u06d4", "pre-emption limitation punjab", "punjab", True)
    assert replaced                                                                    # Urdu "the Act is silent"


def test_the_period_notice_is_precise_only_when_the_period_is_still_shown(va):
    from app.ai import period_support as P
    notice = P.RESEARCH_NOTICE_EN
    kept = f"{notice}\nThe suit lies within four months [1]."
    assert va.precise_notice(kept, ["The buyer pays within four months [1]."], notice, False).startswith("Note: a further")
    gone = f"{notice}\nThe suit must be filed promptly."
    assert va.precise_notice(gone, ["The suit lies within four months [1]."], notice, False) == gone


@pytest.mark.parametrize("urdu", [False, True])
def test_the_guards_own_wording_is_never_flagged_again(va, urdu):
    # The scorer reads the FINAL answer with the same detector; a replacement
    # that re-matched would count a fixed answer as a violation (and a second
    # pass would mangle it).
    for tmpl in ((va._SILENCE_GOVERNING_UR, va._SILENCE_UR, va._SILENCE_AGAIN_UR) if urdu else
                 (va._SILENCE_GOVERNING_EN, va._SILENCE_EN, va._SILENCE_AGAIN_EN)):
        text = tmpl.format(act=PPA, section="30", heading="Limitation")
        assert va.whole_act_silence(text, "q", "punjab", urdu)[1] == []


# ── precision: false positives found by hand-checking the d2 run ────────────

@pytest.mark.parametrize("sentence", [
    # U2: a correct statement ABOUT s.154 that mentions an offence
    "\u0636\u0627\u0628\u0637\u06c1 \u0641\u0648\u062c\u062f\u0627\u0631\u06cc \u06a9\u06cc \u062f\u0641\u0639\u06c1 154 "
    "\u06cc\u06c1 \u062d\u06a9\u0645 \u062f\u06cc\u062a\u06cc \u06c1\u06d2 \u06a9\u06c1 \u06a9\u0633\u06cc \u0628\u06be\u06cc "
    "\u0642\u0627\u0628\u0644\u0650 \u06af\u0631\u0641\u062a\u0627\u0631\u06cc \u062c\u0631\u0645 \u06a9\u06cc "
    "\u0645\u0639\u0644\u0648\u0645\u0627\u062a \u062a\u062d\u0631\u06cc\u0631\u06cc \u06c1\u0648\u06ba\u06d4",
    # F1: a procedural section that lists offences (summary trial)
    "Because Section 337-A is listed in Section 239 CrPC as an offence, joint charges are possible.",
    # E2: long-form Act name
    "When is bail permissible for a non-bailable offence under Section 497 of the Criminal Procedure Code?",
    # N1: an unverifiable authority, explicitly hedged
    "Section 73 of the Contract Act (text not available here) ordinarily provides compensation for breach.",
])
def test_correct_or_hedged_statements_are_kept(va, sentence):
    from app.ai import exact_provision
    shown, withheld = va.authorities(sentence, "q", urdu=False)
    assert withheld == [], withheld
    assert shown == sentence


def test_the_urdu_parenthetical_offence_in_a_procedural_code_is_still_caught(va):
    # The live RU2 d2 row: an Urdu offence description, then "(Section 406 CrPC)".
    row = ("| **\u0645\u062a\u0639\u0644\u0642\u06c1 \u062c\u0631\u0627\u0626\u0645** | \u0627\u06af\u0631 "
           "\u062c\u0627\u0626\u06cc\u062f\u0627\u062f \u06a9\u06cc **\u063a\u06cc\u0631 \u0642\u0627\u0646\u0648\u0646\u06cc "
           "\u0642\u0628\u0636\u06c1** (Section 406 CrPC) \u0634\u0627\u0645\u0644 \u06c1\u0648 |")
    shown, withheld = va.authorities(f"Intro [1].\n{row}", "q", urdu=True)
    assert [p["status"] for w in withheld for p in w["problems"]] == ["mispaired"]
    assert "(Section 406 CrPC)" not in shown


@pytest.mark.parametrize("sentence,kept", [
    ("Whether a court may grant a declaration under Section 42 of the Specific Relief Act, 1877.", True),
    ("1. Obtain the full text of Section 42 of the Specific Relief Act, 1877 from an official source.", True),
    ("What compensation is available under Section 73 of the Contract Act?", True),
    ("Section 42 of the Specific Relief Act grants a declaratory decree to any person entitled to property.", False),
])
def test_an_unverifiable_authority_is_withheld_only_where_it_is_asserted_as_advice(va, sentence, kept):
    shown, withheld = va.authorities(sentence, "q", urdu=False)
    assert (withheld == []) is kept, withheld


# ── the heading lookup: jurisdiction and Act selection ───────────────────────

def test_a_different_provinces_act_is_never_offered():
    from app.ai import issue_lookup as L
    assert L.acts_named("Within what time must a suit for pre-emption be filed in Sindh?", "sindh", INDEX)         == ["Sindh Pre-emption Act 1994"]
    assert L.acts_named("Within what time must a suit for pre-emption be filed in Punjab?", "punjab", INDEX)         == ["Punjab Pre-emption Act 1991"]


def test_naming_the_issue_does_not_select_the_limitation_act(monkeypatch):
    from app.ai import corpus_index
    from app.ai import issue_lookup as L
    monkeypatch.setattr(corpus_index, "get_index", lambda: INDEX)
    q = "Does the Punjab Pre-emption Act 1991 itself prescribe a limitation period?"
    assert "Limitation Act 1908" not in L.acts_named(q, "punjab", INDEX)
    assert [(c.statute, c.section, h) for c, h in L.governing(q, "punjab")] == [(PPA, "30", "Limitation")]
    assert L.governing("What is the punishment under Section 420 PPC?", "punjab") == []     # not a limitation issue


def test_husbands_talaq_notice_maps_to_mflo_section_7_not_section_8(monkeypatch):
    from app.ai import corpus_index
    from app.ai import issue_lookup as L
    mflo = "Muslim Family Laws Ordinance 1961"
    index = _Index({
        mflo: _Cov({"7": ("Talaq",),
                    "8": ("Dissolution of marriage otherwise than by talaq",)}),
    })
    monkeypatch.setattr(corpus_index, "get_index", lambda: index)
    q = ("Under the Muslim Family Laws Ordinance 1961, what is the procedure "
         "and timeline for a husband sending a divorce notice in Pakistan?")

    assert [(c.statute, c.section, h) for c, h in L.governing(q, "punjab")] == [
        (mflo, "7", "Talaq")
    ]


@pytest.mark.parametrize("question", [
    "Under the Muslim Family Laws Ordinance 1961, how can a wife divorce her husband?",
    "Under the Muslim Family Laws Ordinance 1961, what is the procedure for delegated divorce by a wife?",
    "Under the Muslim Family Laws Ordinance 1961, what is the divorce notice procedure?",
])
def test_wife_or_ambiguous_divorce_question_does_not_pin_husbands_section(monkeypatch, question):
    from app.ai import corpus_index, issue_lookup as L
    mflo = "Muslim Family Laws Ordinance 1961"
    monkeypatch.setattr(corpus_index, "get_index", lambda: _Index({
        mflo: _Cov({"7": ("Talaq",), "8": ("Dissolution of marriage otherwise than by talaq",)}),
    }))
    assert L.governing(question, "punjab") == []


def test_client_heading_lookup_failure_does_not_stop_the_answer(monkeypatch):
    from app.ai import corpus_index, exact_provision, issue_lookup as L
    mflo = "Muslim Family Laws Ordinance 1961"
    monkeypatch.setattr(corpus_index, "get_index", lambda: _Index({
        mflo: _Cov({"7": ("Talaq",)}),
    }))
    monkeypatch.setattr(exact_provision, "fetch", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("offline")))
    q = "Under the Muslim Family Laws Ordinance 1961, what is the procedure for a husband sending divorce notice?"
    assert L.fetch_governing(q, "punjab", research=False) == []


# ── found by the focused live run (focus4) ───────────────────────────────────

def test_the_governing_provision_supports_its_own_period_in_any_wording():
    # V4 / V6: correct restatements of s.30's four months were withdrawn for
    # lacking a shared subject word -- and every Urdu one.
    from app.ai import period_support as P
    governing = {"id": "1", "kind": "statute", "statute": PPA, "section": "30", "content": S30["content"],
                 "issue_provision": {"statute": PPA, "section": "30", "heading": "Limitation"}}
    plain = {k: v for k, v in governing.items() if k != "issue_provision"}
    en = "Thus, the Act itself prescribes a four-month limitation period [1]."
    ur = "\u067e\u0646\u062c\u0627\u0628 \u0645\u06cc\u06ba \u0634\u0641\u0639\u06c1 \u06a9\u0627 \u062f\u0639\u0648\u06cc\u0670 \u0686\u0627\u0631 \u0645\u0627\u06c1 \u06a9\u06d2 \u0627\u0646\u062f\u0631 \u062f\u0627\u0626\u0631 \u06a9\u0631\u0646\u0627 \u0644\u0627\u0632\u0645\u06cc \u06c1\u06d2 [1]\u06d4"
    assert P.unsupported_periods(en, [governing]) == [] and P.unsupported_periods(ur, [governing]) == []
    assert P.unsupported_periods(en, [plain]) != []            # without the governing flag: as before
    # a period the governing text does NOT state is still withheld
    assert P.unsupported_periods("The suit must be filed within six months [1].", [governing]) == [(6, "month")]


def test_a_restated_question_is_not_an_assertion_in_any_script(va):
    for q in ("Is pre-arrest bail available under Section 438 CrPC?",
              "\u0636\u0627\u0628\u0637\u06c1 \u0641\u0648\u062c\u062f\u0627\u0631\u06cc \u06a9\u06cc \u062f\u0641\u0639\u06c1 438 "
              "\u06a9\u06d2 \u062a\u062d\u062a \u0636\u0645\u0627\u0646\u062a \u06a9\u06cc\u0633\u06d2 \u0645\u0644\u062a\u06cc "
              "\u06c1\u06d2\u061f"):
        assert va.authorities(q, q, urdu=True)[1] == []


def test_bare_section_numbers_inherit_the_answers_only_act(va):
    # V3: "(e.g. section 437 or 439)" after "CrPC section 438" -- 437 is omitted.
    one_act = ("Pre-arrest bail is not available under Section 438 CrPC because it has been omitted.\n"
               "Courts usually entertain the application under other provisions (e.g. Section 437 or 439).")
    shown, withheld = va.authorities(one_act, "q", urdu=False)
    assert [(p["label"], p["status"]) for w in withheld for p in w["problems"]] == [("Section 437 CrPC", "omitted")]
    two_acts = ("Section 420 PPC punishes cheating. Section 497 CrPC governs bail.\n"
                "See also Section 437 for related powers.")
    assert va.authorities(two_acts, "q", urdu=False)[1] == []     # ambiguous: left alone


def test_the_notice_is_worded_after_every_other_change(corpus):
    # V4: the sentence carrying the period was removed AFTER the notice had
    # been reworded "the period shown here".
    corpus["chunks"] = [S30]
    corpus["gen"] = ["Under Section 438 CrPC the suit lies within four months [1].\n"
                     "The buyer must also pay the price within four months [1]."]
    resp = ask("Within what time must a suit for pre-emption be filed in Punjab?", session="va-order")
    shown = resp["answer"]
    if "the period shown here is the one the cited provision states" in shown:
        from app.ai import period_support as P
        visible = shown.replace("the period shown here is the one the cited provision states", "")
        assert (4, "month") in {p for p, _ in P.periods_in(visible)}, shown


def test_the_governing_period_is_not_lent_to_a_different_point():
    from app.ai import period_support as P
    governing = {"id": "1", "kind": "statute", "statute": PPA, "section": "30", "content": S30["content"],
                 "issue_provision": {"statute": PPA, "section": "30", "heading": "Limitation"}}
    assert P.unsupported_periods("The buyer must also pay the price within four months [1].", [governing]) \
        == [(4, "month")]


def test_a_partly_shown_period_set_names_only_what_was_withheld(va):
    # Live e1 RU2 / C2, e2 E9: some withheld periods were also shown elsewhere,
    # others were not -- the generic notice sat beside a visible period.
    from app.ai import period_support as P
    notice = P.RESEARCH_NOTICE_EN
    answer = f"{notice}\nThe offence carries up to seven years [1]."
    out = va.precise_notice(answer, ["It carries seven years [1].", "Appeal lies within thirty days [1]."], notice, False)
    assert notice not in out and "30 days" in out and "7 years" not in out.split("\n")[0]
    # nothing withheld is shown: the generic notice is accurate and stays
    alone = f"{notice}\nFile promptly."
    assert va.precise_notice(alone, ["Appeal lies within thirty days [1]."], notice, False) == alone


# ── require_corpus (the drafter, 2026-10-14) ─────────────────────────────────

from app.ai import visible_authority as _va  # noqa: E402

def _down(*a, **k):
    raise RuntimeError("ChromaDB client not initialized")


def test_research_default_is_unchanged_when_the_corpus_is_down(monkeypatch):
    from app.ai import corpus_index
    from app.db import chroma
    monkeypatch.setattr(corpus_index, "get_index", _down)
    monkeypatch.setattr(chroma, "get_chroma", _down)
    text = "Pre-arrest bail may perhaps be sought under Section 438 CrPC."
    out, withheld = _va.authorities(text, "bail", False)
    assert out == text and withheld == []        # hedged + unverifiable: passes, as before


def test_require_corpus_raises_instead_of_passing_what_it_could_not_check(monkeypatch):
    from app.ai import corpus_index, exact_provision
    from app.db import chroma
    monkeypatch.setattr(corpus_index, "get_index", _down)
    monkeypatch.setattr(chroma, "get_chroma", _down)
    with pytest.raises(exact_provision.CorpusUnavailable):
        _va.authorities("Pre-arrest bail may perhaps be sought under Section 438 CrPC.", "bail", False,
                       require_corpus=True)


def test_an_empty_index_counts_as_unavailable(monkeypatch):
    from app.ai import corpus_index, exact_provision
    monkeypatch.setattr(corpus_index, "get_index", lambda: corpus_index.CorpusIndex({}))
    # the provision lookups themselves are healthy: only the empty index is wrong
    monkeypatch.setattr(exact_provision, "fetch", lambda cits, research=False, strict=False: {
        exact_provision.label(c): [{"statute": "CrPC 1898", "content": "497. When bail may be taken ..."}] for c in cits})
    with pytest.raises(exact_provision.CorpusUnavailable):
        _va.authorities("Bail under Section 497 CrPC.", "bail", False, require_corpus=True)


def _with_crpc_420(monkeypatch, va):
    from app.ai import exact_provision
    base = exact_provision.fetch
    extra = {"Section 420 CrPC": [{"statute": "CrPC 1898", "content": "420. Procedure when appellant in jail. "
                                   "If the appellant is in jail, he may present his petition of appeal ..."}]}
    monkeypatch.setattr(exact_provision, "fetch", lambda cits, research=False, strict=False: {
        **base(cits, research), **{k: v for k, v in extra.items() if k in {exact_provision.label(c) for c in cits}}})


@pytest.mark.parametrize("sentence", [
    "That the accused is charged with cheating punishable under Section 420 CrPC.",
    "That the accused is charged with cheating punishable under Section 420 of the Code of Criminal Procedure, 1898.",
])
def test_a_wrong_act_is_caught_in_its_long_form_too(va, monkeypatch, sentence):
    """The Act's own name ("...Criminal PROCEDURE") must not count as the
    sentence agreeing with s.420 CrPC's heading ("PROCEDURE when appellant
    in jail") -- it let the long form through in the browser check."""
    _with_crpc_420(monkeypatch, va)
    shown, withheld = va.authorities(sentence, "x", False)
    assert withheld and withheld[0]["problems"][0]["status"] == "mispaired"


def test_a_sentence_about_procedure_still_matches_a_procedural_heading(va, monkeypatch):
    _with_crpc_420(monkeypatch, va)
    s = "That an appellant in jail may present the appeal through the jail authorities under Section 420 CrPC."
    assert va.authorities(s, "x", False)[1] == []


def test_checked_counts_only_provisions_the_library_holds(va):
    stats = {}
    va.authorities("Bail may perhaps be sought under Section 497 CrPC and Section 113 of the Transfer of Property Act.",
                   "x", False, stats=stats)
    assert stats["checked"] == 1
    assert stats["unverified"] == ["Section 113 Transfer of Property Act"]


def test_a_withheld_provision_is_not_also_listed_as_unchecked(va):
    stats = {}
    va.authorities("The applicant is entitled to bail under Section 9999 of the Imaginary Relief Act.", "x", False,
                   stats=stats)
    assert stats["unverified"] == []


def test_require_corpus_with_nothing_cited_needs_no_corpus(monkeypatch):
    from app.ai import corpus_index
    monkeypatch.setattr(corpus_index, "get_index", _down)
    stats = {}
    assert _va.authorities("The tenancy is terminated.", "x", False, require_corpus=True, stats=stats) == \
        ("The tenancy is terminated.", [])
    assert stats == {"checked": 0, "unverified": [], "units": []}


def test_strict_fetch_raises_when_every_collection_fails(monkeypatch):
    from app.ai import exact_provision, tool_contract
    from app.db import chroma

    class _Client:
        def get_collection(self, name):
            raise RuntimeError("collection unreadable")
    monkeypatch.setattr(chroma, "get_chroma", lambda: _Client())
    monkeypatch.setattr(exact_provision, "_collections", lambda research=False: ["a", "b"])
    refs = tool_contract.provision_refs("Section 497 CrPC")
    assert exact_provision.fetch(refs) == {exact_provision.label(refs[0]): []}   # lenient: unchanged
    with pytest.raises(exact_provision.CorpusUnavailable):
        exact_provision.fetch(refs, strict=True)
