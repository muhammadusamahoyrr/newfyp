"""The Punjab-sourced CPC and the 2012 Constitution are never shown as current
national law (app/ai/source_currency.py, 2026-10-16).

Pure checks plus the drafter's visible outcome: the legal check's
supported / not-checked / withheld lists the panel shows, and the source notes
in the prompt. No store, no model.
"""
from __future__ import annotations

import pytest

from app.ai import draft_guard, source_currency as sc


# ── jurisdiction gate for the CPC ────────────────────────────────────────────

@pytest.mark.parametrize("province, where", [
    ("sindh", "Sindh"), ("kpk", "Khyber Pakhtunkhwa"), ("balochistan", "Balochistan"),
    ("federal", "Islamabad / federal"), ("unknown", "this jurisdiction"), ("", "this jurisdiction")])
def test_outside_punjab_a_cpc_citation_is_never_supported(province, where):
    keep, moved = sc.gate_supported(["Section 9 CPC 1908", "Order VII Rule 11 CPC", "Section 302 PPC"], province)
    assert keep == ["Section 302 PPC"]
    assert all("Punjab version" in m and where in m for m in moved) and len(moved) == 2


def test_in_punjab_the_cpc_text_on_file_is_the_right_one():
    keep, moved = sc.gate_supported(["Section 9 CPC 1908", "Order VII Rule 11 CPC"], "punjab")
    assert keep == ["Section 9 CPC 1908", "Order VII Rule 11 CPC"] and moved == []
    assert sc.cpc_note("Punjab") is None


def test_other_codes_are_not_mistaken_for_the_cpc():
    for label in ("Section 497 CrPC", "Section 154 Code of Criminal Procedure", "Section 3 Limitation Act 1908"):
        assert not sc.is_cpc(label)


# ── as-of gate for the Constitution ──────────────────────────────────────────

def test_no_constitution_citation_is_supported_as_current():
    keep, moved = sc.gate_supported(["Article 10A Constitution of Pakistan 1973"], "punjab")
    assert keep == [] and "28 February 2012" in moved[0]


def test_articles_changed_by_the_27th_amendment_say_so():
    # Batch 4: notes name the Gazette section and page (BATCH4_CONSTITUTION_GATE.md §1).
    assert "amended by the Constitution (Twenty-seventh Amendment) Act 2025, s.40" in sc.constitution_note("Article 199 Constitution")
    assert "Article 184 was omitted" in sc.constitution_note("Article 184 Constitution")
    assert "Article 186 was omitted" in sc.constitution_note("Article 186 Constitution")
    assert "omitted" in sc.constitution_note("Article 191A Constitution")


@pytest.mark.parametrize("text", [
    "Can I file directly in the Federal Constitutional Court?", "What did the 27th Amendment change?",
    "constitutional benches of the High Court", "jurisdiction under Article 175E", "a petition under Article 184(3)",
    "twenty-sixth amendment"])
def test_questions_needing_post_2012_constitutional_law_are_recognised(text):
    assert sc.needs_post_2012_constitution(text)


@pytest.mark.parametrize("text", [
    "writ under Article 199", "Article 175A appointment of judges", "Section 175 PPC", "Article 10A fair trial",
    "the FCC registration"])
def test_ordinary_questions_are_not_flagged(text):
    assert not sc.needs_post_2012_constitution(text)


def test_reliance_on_an_omitted_article_is_withheld():
    norm = "The petition is filed under Article 184(3) of the Constitution. Relief under Article 199 is sought."
    units = [(0, 59), (60, len(norm))]
    out = sc.omitted_article_units(units, norm)
    assert [u["span"] for u in out] == [(0, 59)]
    assert "Twenty-seventh" in out[0]["reasons"][0]
    assert sc.omitted_article_units([(0, 30)], "Section 184 PPC punishes it.  ") == []


# ── the drafter's legal check: what the panel shows ─────────────────────────

@pytest.fixture
def guard(monkeypatch):
    """draft_guard.check with the corpus-reading checks replaced by a fixed
    result: every cited provision 'valid' in the library."""
    from app.ai import visible_authority

    def authorities(norm, question, urdu, stats=None, **kw):
        units = visible_authority._units(norm)
        refs = {"Section 9": "Section 9 CPC 1908", "Article 199": "Article 199 Constitution of Pakistan 1973",
                "Section 302": "Section 302 PPC"}
        stats["units"] = [{"span": (a, b), "refs": [{"status": "valid", "shown": shown}
                                                   for key, shown in refs.items() if key in norm[a:b]]}
                          for a, b in units]
        return norm, []
    monkeypatch.setattr(visible_authority, "authorities", authorities)
    monkeypatch.setattr(draft_guard, "_malformed", lambda units, norm: [])
    monkeypatch.setattr(draft_guard, "_cpc_rules", lambda units, norm, request="": ([], [], []))
    monkeypatch.setattr(draft_guard, "next_step", lambda text, withheld: None)
    return lambda text, province: draft_guard.check(text, "draft", [], province, None, _alternative=False)


DRAFT = "That this Court has jurisdiction under Section 9 of the Code of Civil Procedure."


def test_sindh_draft_shows_the_cpc_as_not_checked(guard):
    # Batch 5 policy: only the CPC authority clause leaves the proposal; the
    # sentence stays, and the reason is listed under Withheld.
    g = guard(DRAFT, "sindh")
    assert g["ran"] and "Section 9 CPC 1908" not in g["supported"]
    assert g["text"].strip() == "That this Court has jurisdiction."
    assert any("Punjab version" in r and "Sindh" in r for w in g["withheld"] for r in w["reasons"])


def test_punjab_draft_keeps_the_cpc_supported(guard):
    g = guard(DRAFT, "punjab")
    assert "Section 9 CPC 1908" in g["supported"]
    assert not any("Punjab version" in x for x in g["not_checked"])


def test_a_constitution_citation_is_never_shown_as_checked(guard):
    g = guard("That the petition is maintainable under Article 199 of the Constitution.", "punjab")
    assert g["supported"] == []
    assert any("Article 199" in x and "Twenty-seventh" in x and "s.40" in x for x in g["not_checked"])


def test_a_draft_relying_on_an_omitted_article_is_withheld(guard):
    g = guard("That this petition is filed under Article 184(3) of the Constitution.", "federal")
    assert g["text"].strip() == ""
    assert any("Twenty-seventh" in r for w in g["withheld"] for r in w["reasons"])


# ── the source notes the model is given ─────────────────────────────────────

def test_the_prompt_says_the_cpc_text_is_punjabs_outside_punjab():
    law = "[STATUTE] CPC 1908 — Section 9\nThe Courts shall ..."
    assert "PUNJAB version" in sc.drafting_rider(law, "add jurisdiction", "sindh")
    assert sc.drafting_rider(law, "add jurisdiction", "punjab") == ""


def test_the_prompt_says_the_constitution_is_the_2012_text():
    r = sc.drafting_rider("", "draft a petition to the Federal Constitutional Court", "federal")
    assert "28 February 2012" in r and "[current constitutional provision]" in r
    assert "28 February 2012" in sc.research_rider("Which court hears Article 184(3) petitions now?")
    assert sc.research_rider("bail under section 497 CrPC") == ""


def test_the_drafter_and_research_actually_use_the_riders():
    import inspect
    import app.api.v1.routes.ai as ai_routes
    from app.ai.nodes import generation_node
    assert "source_currency.drafting_rider(" in inspect.getsource(ai_routes.ai_draft_stream)
    assert "source_currency.research_rider(" in inspect.getsource(generation_node)
