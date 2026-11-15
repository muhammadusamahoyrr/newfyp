"""Constitution omission gate from the 27th Amendment Gazette, and "never Supported"
for the wrong-province CPC (2026-10-16, batch 4).

Evidence: Gazette of Pakistan, Extra., 13 Nov 2025, Act No. XXXII of 2025
(evals/legal_sources/BATCH4_CONSTITUTION_GATE.md §1). Batch 3 missed Article
186 (s.31, PDF p.13); these tests pin every whole-Article omission and the
difference between an omitted ARTICLE and an omitted CLAUSE.

Outcomes are read where the lawyer reads them: the draft-assist stream's final
insertable text and its Supported / Not checked / Withheld lists; and the
claim badge chat and research show. No store, no model.
"""
from __future__ import annotations

import asyncio
import json

import pytest

import app.api.v1.routes.ai as ai_routes
from app.ai import draft_guard
from app.ai import source_currency as sc

GAZETTE_URL = "https://www.na.gov.pk/uploads/documents/691ec19a6a212_270.pdf"


# ── the evidence table ───────────────────────────────────────────────────────

def test_the_whole_article_omissions_are_exactly_those_the_gazette_shows():
    assert sc.OMITTED_ARTICLES == {"184", "186", "186A", "191A"}
    assert {a: (sec, page) for sec, a, kind, page in sc.GAZETTE_27TH if kind == "article_omitted"} == {
        "184": (29, "12"), "186": (31, "13"), "186A": (32, "13"), "191A": (37, "15")}


def test_a_clause_omission_or_substitution_is_not_an_article_omission():
    kinds = {a: k for _, a, k, _ in sc.GAZETTE_27TH}
    for art in ("130", "175A", "183", "193", "207"):
        assert kinds[art] == "clause_omitted" and art not in sc.OMITTED_ARTICLES
    for art in ("185", "189", "191", "200"):
        assert kinds[art] == "article_substituted" and art not in sc.OMITTED_ARTICLES


def test_the_new_chapter_inserts_175b_to_175l_including_175i():
    assert sc.INSERTED_ARTICLES == {f"175{c}" for c in "BCDEFGHIJKL"}


def test_every_amending_section_2_to_53_is_in_the_table():
    assert {sec for sec, *_ in sc.GAZETTE_27TH} == set(range(2, 54))


# ── citation forms ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("text, arts", [
    ("under Article 186 of the Constitution", ["186"]), ("(Article 186)", ["186"]), ("Art. 186-A", ["186A"]),
    ("ARTICLE 191A", ["191A"]), ("Articles 184 and 186", ["184", "186"]), ("Article 184(3)", ["184"]),
    ("aain ke article 186a ke tehat", ["186A"]), ("آئین کے آرٹیکل ۱۸۶ کے تحت", ["186"]),
    ("Article 186 And", ["186"]), ("section 186 PPC", []), ("Section 186 CrPC", []),
])
def test_article_citation_forms(text, arts):
    assert [a for a, _, _ in sc.article_refs(text)] == arts


# ── the drafter's legal check (real draft_guard, fake library) ──────────────

@pytest.fixture
def library(monkeypatch):
    from app.ai import corpus_index, cpc_provisions, exact_provision
    from tests import test_visible_authority as V
    idx = V._Index({**V.INDEX.cov,
                    "PPC 1860": V._Cov({**V.INDEX.cov["PPC 1860"].provisions,
                                        "186": ("Obstructing public servant in discharge of public functions",)}),
                    "Constitution of Pakistan 1973": V._Cov({
                        "184": ("Original jurisdiction of Supreme Court",), "186": ("Advisory jurisdiction",),
                        "186A": ("Power of Supreme Court to transfer cases",),
                        "191A": ("Constitutional Benches of the Supreme Court",),
                        "193": ("Appointment of High Court Judges",), "199": ("Jurisdiction of High Court",),
                        "185": ("Appellate jurisdiction of Supreme Court",)}),
                    "CPC 1908": V._Cov({"9": ("Courts to try all civil suits unless barred",)})})
    monkeypatch.setattr(corpus_index, "get_index", lambda: idx)
    monkeypatch.setattr(corpus_index, "get_drafter_index", lambda: idx)
    monkeypatch.setattr(exact_provision, "fetch", lambda cits, research=False, strict=False:
                        {exact_provision.label(c): [] for c in cits})
    monkeypatch.setattr(cpc_provisions, "catalogue", lambda: {"provisions": {}, "orders": {}})
    return idx


def check(text, province="federal", question="draft"):
    return draft_guard.check(text, question, [], province, None, _alternative=False)


@pytest.mark.parametrize("art, sec", [("184", 29), ("186", 31), ("186A", 32), ("191A", 37)])
def test_every_omitted_article_relied_on_is_withheld(library, art, sec):
    g = check(f"That this petition is filed under Article {art} of the Constitution.")
    assert g["text"].strip() == "" and g["supported"] == []
    assert any(f"s.{sec}" in r and "omitted" in r for w in g["withheld"] for r in w["reasons"])


@pytest.mark.parametrize("sentence, art", [
    ("That the petition is maintainable under Article 199 of the Constitution.", "199"),
    ("That Judges are appointed under Article 193 of the Constitution.", "193"),       # clause (3) omitted only
    ("That an appeal lies under Article 185 of the Constitution.", "185"),             # substituted, not omitted
])
def test_an_amended_article_is_kept_never_supported_and_says_why(library, sentence, art):
    g = check(sentence, province="punjab")
    assert g["text"].strip() == sentence and g["withheld"] == [] and g["supported"] == []
    assert any(x.startswith(f"Article {art}") and "Twenty-seventh" in x for x in g["not_checked"])


def test_article_186_of_the_constitution_is_not_section_186_ppc(library):
    assert check("That the accused obstructed the officer, an offence under Section 186 PPC.")["withheld"] == []
    assert check("That the reference lies under Article 186 of the Constitution.")["text"].strip() == ""


@pytest.mark.parametrize("sentence", [
    "ARTICLE 186 OF THE CONSTITUTION: the President seeks the opinion of the Court on this question of law.",
    "That the President's reference (Article 186 of the Constitution) be heard.",
    "That the opinion of the Court is sought under Art. 186 of the Constitution.",
    "That this Court may hear it under Articles 184 and 186 of the Constitution.",
    "That aain ke article 186 ke tehat reference dair kiya jata hai.",
])
def test_headings_parentheses_lists_and_roman_urdu_are_caught(library, sentence):
    assert check(sentence)["text"].strip() == ""


def test_urdu_script_reliance_is_withheld():
    norm = "آئین کے آرٹیکل ۱۸۶ کے تحت ریفرنس دائر کیا جاتا ہے۔"
    withheld, notes = sc.omitted_article_check([(0, len(norm))], norm)
    assert len(withheld) == 1 and notes == []


def test_a_historical_mention_stays_as_history_not_current_law(library):
    sentence = ("Before its omission by the Twenty-seventh Amendment, Article 186 of the Constitution "
                "provided for an advisory reference by the President.")
    g = check(sentence, question="Explain what Article 186 said before the Twenty-seventh Amendment")
    assert g["text"].strip() == sentence and g["withheld"] == [] and g["supported"] == []
    assert any("historical reference" in x and "s.31" in x for x in g["not_checked"])
    # reliance still wins over historical words
    g2 = check("That under Article 186, which was omitted by the Twenty-seventh Amendment, the reference is filed.")
    assert g2["text"].strip() == ""


def test_research_answers_an_omitted_article_question_as_history():
    r = sc.research_rider("What did Article 186 say before 2025?")
    assert "Article 186 (s.31) WAS OMITTED" in r and "no longer in force" in r
    assert "28 February 2012" in r
    assert sc.research_rider("writ under Article 199") == ""


# ── the final insertable text, through the real draft-assist route ─────────

@pytest.fixture
def route(monkeypatch, library):
    seen = {}
    from app.ai import index_health
    monkeypatch.setattr(index_health, "require_all", lambda names, client=None: list(names))
    monkeypatch.setattr(ai_routes, "_retrieve_law_context", lambda *a, **k: "LAW")
    monkeypatch.setattr(ai_routes, "_exact_provisions_for", lambda text: [])

    async def none(*a, **k):
        return ""
    monkeypatch.setattr(ai_routes, "_retrieve_case_law_context", none)

    async def verification(payload):
        seen["verified"] = payload
        return {"ran": False}
    monkeypatch.setattr(ai_routes, "_verification_record", verification)

    async def record(**kw):
        seen["recorded"] = kw
    monkeypatch.setattr(ai_routes.provenance_service, "record_answer", record)

    class _C:
        def __init__(self, c):
            self.content = c

    class _LLM:
        async def astream(self, messages):
            yield _C(seen["reply"])
    monkeypatch.setattr("app.ai.llm.get_llm", lambda **k: _LLM())

    def go(reply, **body):
        seen["reply"] = reply

        async def main():
            resp = await ai_routes.ai_draft_stream(ai_routes.DraftRequest(**body), current_user={"_id": "l1", "role": "lawyer"})
            return [p if isinstance(p, str) else p.decode() async for p in resp.body_iterator]
        events = asyncio.run(main())
        return next(json.loads(e[6:])["guard"] for e in events if e.startswith("data: {") and '"guard"' in e)
    go.seen = seen
    return go


def test_the_insertable_text_drops_article_186_and_keeps_article_199(route):
    reply = ("That the petition is maintainable under Article 199 of the Constitution.\n\n"
             "That the matter may alternatively be referred under Article 186 of the Constitution.")
    g = route(reply, instruction="Add a maintainability paragraph", document="WRIT PETITION ...",
              template="Writ Petition", case_type="constitutional", province="punjab", mode="clause")
    assert g["ran"] is True
    assert "Article 199" in g["text"] and "186" not in g["text"]          # what "Insert" would put in
    assert g["supported"] == []
    assert any(x.startswith("Article 199") and "s.40" in x for x in g["not_checked"])
    assert any("s.31" in r for w in g["withheld"] for r in w["reasons"])
    assert "186" not in route.seen["verified"]["draft"]                    # audit/verification read the guarded text


@pytest.mark.parametrize("province, name", [("sindh", "Sindh"), ("kpk", "Khyber Pakhtunkhwa"),
                                            ("balochistan", "Balochistan"), ("federal", "Islamabad")])
def test_a_wrong_province_cpc_citation_is_never_supported_in_the_panel(route, province, name):
    reply = "That this Court has jurisdiction under Section 9 of the Code of Civil Procedure, 1908."
    g = route(reply, instruction="Add jurisdiction", document="PLAINT ...", template="Civil Plaint",
              case_type="civil", province=province, mode="clause")
    assert not any(sc.is_cpc(s) for s in g["supported"])
    # Batch 5 policy (chosen): only the CPC authority clause leaves the
    # insertable text; a separate, re-checked placeholder version names the province.
    assert g["text"].strip() == "That this Court has jurisdiction."
    assert any("Punjab version" in r and name in r for w in g["withheld"] for r in w["reasons"])
    alt = g["placeholder_alternative"]
    assert f"[Verify the applicable CPC provision for {name}" in alt["text"] and "CPC provision" in alt["label"]


# ── chat and research: the claim badge ──────────────────────────────────────

def _claims(statutes):
    evidence = [{"id": str(i + 1), "kind": "statute", "statute": s, "section": "9", "content": "x"}
                for i, s in enumerate(statutes)]
    claims = [{"index": 1, "text": "Civil courts try all civil suits [1].", "source_ids": [e["id"] for e in evidence],
               "citation_status": "matched", "support": "supported"}]
    return claims, evidence


@pytest.mark.parametrize("province", ["sindh", "Sindh", "kpk", "balochistan", "federal", "islamabad"])
def test_a_cpc_claim_in_a_known_other_province_is_not_supported(province):
    claims, evidence = _claims(["CPC 1908"])
    out = sc.downgrade_wrong_province_cpc(claims, evidence, province)
    assert out[0]["support"] == "unassessed" and "Punjab version" in out[0]["support_reason"]


@pytest.mark.parametrize("province, statutes", [("punjab", ["CPC 1908"]), (None, ["CPC 1908"]),
                                                ("unknown", ["CPC 1908"]), ("sindh", ["CPC 1908", "PPC 1860"]),
                                                ("sindh", ["PPC 1860"])])
def test_the_downgrade_touches_nothing_else(province, statutes):
    claims, evidence = _claims(statutes)
    assert sc.downgrade_wrong_province_cpc(claims, evidence, province)[0]["support"] == "supported"


def test_the_grounding_node_leaves_jurisdiction_to_the_finalizer(monkeypatch):
    """Batch 5: the CPC jurisdiction downgrade moved to finalizer_node (fresh AND
    cached answers, after the grounding verdict). The judge's verdict here stays
    as given -- jurisdiction doubt is not a grounding failure. The visible badge
    is tested in tests/test_cpc_jurisdiction.py."""
    from app.ai.nodes import hallucination_node as hn

    class _Judge:
        def invoke(self, messages):
            return hn.GroundingOutput(is_grounded=True, reason="ok", claim_support="1:supported")
    monkeypatch.setattr(hn, "get_structured_llm", lambda *a, **k: _Judge())
    evidence = [{"id": "1", "kind": "statute", "statute": "CPC 1908", "section": "9",
                 "content": "9. Courts to try all civil suits unless barred."}]
    state = {"answer": "Civil courts try all civil suits under Section 9 CPC [1].", "surface": "client",
             "province": "sindh", "reranked_chunks": [{"statute": "CPC 1908"}], "generation_evidence": evidence,
             "query": "Can a civil court hear my suit?", "confidence": 0.8}
    out = asyncio.run(hn.hallucination_node(state))
    assert out["is_grounded"] is True and out["claim_assessments"][0]["support"] == "supported"


# ── mutation: the regression tests must catch both defects ─────────────────

def test_mutant_without_article_186_is_caught(library, monkeypatch):
    """The batch-3 list (no 186) must fail the 186 regression test."""
    monkeypatch.setattr(sc, "OMITTED_ARTICLES", frozenset({"184", "186A", "191A"}))
    with pytest.raises(AssertionError):
        test_every_omitted_article_relied_on_is_withheld(library, "186", 31)
    with pytest.raises(AssertionError):
        test_article_186_of_the_constitution_is_not_section_186_ppc(library)


def test_mutant_that_treats_a_clause_omission_as_an_article_omission_is_caught(library, monkeypatch):
    """Withholding Article 193 because clause (3) went must fail the amended-Article test."""
    monkeypatch.setattr(sc, "OMITTED_ARTICLES", sc.OMITTED_ARTICLES | {"193", "183", "130", "207"})
    with pytest.raises(AssertionError):
        test_an_amended_article_is_kept_never_supported_and_says_why(
            library, "That Judges are appointed under Article 193 of the Constitution.", "193")
    with pytest.raises(AssertionError):
        test_the_whole_article_omissions_are_exactly_those_the_gazette_shows()


# (The CPC-downgrade mutant moved with the downgrade: tests/test_cpc_jurisdiction.py.)
