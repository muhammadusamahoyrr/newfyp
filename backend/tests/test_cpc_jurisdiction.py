"""The Punjab-only CPC text: final visible output by surface and province (batch 5, 2026-10-16).

The indexed CPC is the Punjab Code text (app/ai/source_currency.py). Outside a
CONFIRMED-Punjab matter (selected / case record -- not inferred, not unknown):

  * Draft Assistant: an AI-written CPC authority clause never reaches the
    insertable text -- only that clause is taken out (or, where removing it
    would break the sentence, replaced by "[Verify the applicable CPC provision
    for <province>]"). A separate placeholder version is offered, checked
    again in full. The lawyer's own text is never rewritten.
  * Chat and Research: a claim resting only on the CPC is not "supported", the
    CPC citation's currency is "unknown", and one plain notice in the answer
    says why -- on fresh answers, cache hits and follow-ups.

Read where the user reads it: the draft-assist stream's guard frame (the text
"Insert" uses, Supported / Not checked / Withheld, the placeholder version) and
the chat finalizer's answer / claims / citations. No store, no model.
"""
from __future__ import annotations

import asyncio
import json
import re

import pytest

import app.api.v1.routes.ai as ai_routes
from app.ai import source_currency as sc

# ── drafter: the real route, a fake library, a stubbed model ────────────────


@pytest.fixture
def library(monkeypatch):
    from app.ai import corpus_index, cpc_provisions, exact_provision
    from tests import test_visible_authority as V
    class _Idx(V._Index):
        """+ canonical(): the real index's statute-name lookup, which the citation
        parser calls for a name it does not abbreviate (e.g. the Specific Relief Act)."""
        def canonical(self, name):
            from app.ai.answer_citations import normalise_statute
            return next((s for s in self.cov if normalise_statute(s) == normalise_statute(name)), None)
    idx = _Idx({**V.INDEX.cov,
                    "Specific Relief Act 1877": V._Cov({"42": ("Discretion of court as to declaration of status or right",)}),
                    "PPC 1860": V._Cov({**V.INDEX.cov["PPC 1860"].provisions,
                                        "186": ("Obstructing public servant in discharge of public functions",)}),
                    # No s.2 on purpose (batch 6): "Rules 1 and 2 CPC" used to be read as
                    # Section 2 CPC and withheld the whole sentence; it no longer is.
                    "CPC 1908": V._Cov({"7": ("Provincial Small Cause Courts",),
                                        "9": ("Courts to try all civil suits unless barred",),
                                        "20": ("Other suits to be instituted where defendants reside or cause of action arises",),
                                        "151": ("Saving of inherent powers of Court",)})})
    monkeypatch.setattr(corpus_index, "get_index", lambda: idx)
    monkeypatch.setattr(corpus_index, "get_drafter_index", lambda: idx)
    monkeypatch.setattr(exact_provision, "fetch", lambda cits, research=False, strict=False:
                        {exact_provision.label(c): [] for c in cits})
    monkeypatch.setattr(cpc_provisions, "catalogue", lambda: {"provisions": {}, "orders": {}})
    return idx


@pytest.fixture
def draft(monkeypatch, library):
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

    def go(reply, province="sindh", instruction="Add a paragraph", document="PLAINT ...", mode="clause"):
        seen["reply"] = reply

        async def main():
            body = ai_routes.DraftRequest(instruction=instruction, document=document, template="Civil Plaint",
                                          case_type="civil", province=province, mode=mode)
            resp = await ai_routes.ai_draft_stream(body, current_user={"_id": "l1", "role": "lawyer"})
            return [p if isinstance(p, str) else p.decode() async for p in resp.body_iterator]
        events = asyncio.run(main())
        return next(json.loads(e[6:])["guard"] for e in events if e.startswith("data: {") and '"guard"' in e)
    go.seen = seen
    return go


NON_PUNJAB = [("sindh", "Sindh"), ("kpk", "Khyber Pakhtunkhwa"), ("balochistan", "Balochistan"),
              ("federal", "Islamabad / federal"), ("", "your province"), ("unknown", "your province")]
MIXED = "That the defendant resides in Karachi and this Court has jurisdiction under Section 20 of the Code of Civil Procedure, 1908."
KARACHI = "the defendant resides in Karachi"


def _no_cpc_supported(g):
    assert not any(sc.is_cpc(s) for s in g["supported"]), g["supported"]
    alt = g.get("placeholder_alternative") or {}
    assert not any(sc.is_cpc(s) for s in alt.get("supported") or [])


def test_punjab_drafts_keep_the_cpc(draft):
    g = draft(MIXED, province="punjab", instruction=f"Add jurisdiction; {KARACHI}")
    assert g["text"].strip() == MIXED and g["withheld"] == [] and g.get("placeholder_alternative") is None


@pytest.mark.parametrize("province, where", NON_PUNJAB)
def test_outside_punjab_only_the_cpc_clause_leaves_the_insertable_text(draft, province, where):
    g = draft(MIXED, province=province, instruction=f"Add jurisdiction; {KARACHI}")
    assert g["text"].strip() == "That the defendant resides in Karachi and this Court has jurisdiction."
    assert [w["text"] for w in g["withheld"]] == ["Section 20 of the Code of Civil Procedure, 1908"]
    assert any(where in r for r in g["withheld"][0]["reasons"])
    alt = g["placeholder_alternative"]
    assert alt["text"].strip() == ("That the defendant resides in Karachi and this Court has jurisdiction under "
                                   f"[Verify the applicable CPC provision for {where}].")
    assert alt["label"] == "With a [Verify ...] placeholder for the CPC provision"
    assert alt["withheld"] == [] and not sc.cpc_citations(alt["text"])       # re-checked: nothing left to take out
    _no_cpc_supported(g)
    assert "Section 20" not in draft.seen["verified"]["draft"]               # verification + audit read the checked text


@pytest.mark.parametrize("reply, main", [
    ("That the plaint is liable to be rejected under Order VII Rule 11 CPC as it discloses no cause of action.",
     "That the plaint is liable to be rejected as it discloses no cause of action."),
    ("That the plaint is liable to be rejected under O.7 r.11 of the Code of Civil Procedure.",
     "That the plaint is liable to be rejected."),
    ("That interim relief is sought under Section 151 read with Order XXXIX Rules 1 and 2 CPC pending the suit.",
     "That interim relief is sought pending the suit."),
    ("That the suit is properly valued (Section 7 CPC) and the court fee is paid.",
     "That the suit is properly valued and the court fee is paid."),
    ("That the suit is maintainable under Section 9 of the Civil Procedure Code.",
     "That the suit is maintainable."),
    ("That the plaint is liable to be rejected under O VII R 11 CPC.", "That the plaint is liable to be rejected."),
    ("That the suit lies under Section 42 of the Specific Relief Act and Section 9 CPC.",
     "That the suit lies under Section 42 of the Specific Relief Act."),
    ("Section 9 CPC gives civil courts jurisdiction over all suits of a civil nature.",
     "[Verify the applicable CPC provision for Sindh] gives civil courts jurisdiction over all suits of a civil nature."),
])
def test_order_rule_and_section_forms_lose_only_the_authority(draft, reply, main):
    g = draft(reply)
    assert g["text"].strip() == main
    _no_cpc_supported(g)


def test_urdu_and_roman_urdu_citations(draft):
    urdu = "یہ عدالت ضابطہ دیوانی کی دفعہ 20 کے تحت مجاز ہے۔"
    g = draft(urdu)
    assert "ضابطہ دیوانی کی دفعہ" not in g["text"] and "یہ عدالت" in g["text"] and "مجاز ہے" in g["text"]
    roman = "Yeh adalat CPC ki dafa 20 ke tehat mujaz hai."
    assert draft(roman)["text"].strip() == "Yeh adalat mujaz hai."
    assert draft("Yeh adalat CPC ki dafa 20 Ke Tahat mujaz hai.")["text"].strip() == "Yeh adalat mujaz hai."


def test_urdu_order_rule_is_taken_out(draft):
    g = draft("مدعی کی درخواست آرڈر 7 رول 11 ضابطہ دیوانی کے تحت مسترد کی جائے۔")
    assert "آرڈر 7 رول 11" not in g["text"] and "مسترد کی جائے" in g["text"]
    _no_cpc_supported(g)


def test_rules_1_and_2_keep_their_sentence_in_punjab(draft):
    """Batch 6: no phantom "Section 2 CPC" withholds a Punjab sentence."""
    reply = "That interim relief is sought under Section 151 read with Order XXXIX Rules 1 and 2 CPC pending the suit."
    g = draft(reply, province="punjab")
    assert g["text"].strip() == reply
    assert not any("Section 2" in r for w in g["withheld"] for r in w["reasons"])


def test_the_said_section_is_never_supported(draft):
    g = draft("That relief may be granted under the said section.", province="punjab")
    assert g["supported"] == [] and g["text"].strip() == "That relief may be granted under the said section."


def test_a_historical_cpc_sentence_is_kept_and_listed_not_checked(draft):
    reply = "Before the Punjab amendment, Section 7 CPC formerly applied to Provincial Small Cause Courts."
    g = draft(reply, instruction="Explain how the Punjab amendment changed small cause courts")
    assert g["text"].strip() == reply and g["withheld"] == []
    assert any("historical" in x for x in g["not_checked"])
    _no_cpc_supported(g)


def test_the_lawyers_own_cpc_text_is_never_rewritten(draft):
    own = "That this Court has jurisdiction under Section 9 of the Code of Civil Procedure."
    reply = f"{own}\n\nThat the defendant resides within jurisdiction under Section 20 CPC."
    g = draft(reply, document=f"PLAINT\n\n{own}", mode="full",
              instruction="Add a paragraph that the defendant resides within jurisdiction")
    assert own in g["text"]                                              # the lawyer's sentence, unchanged
    assert "Section 20 CPC" not in g["text"]                             # the AI's new citation, taken out
    assert any("your own text" in x for x in g["not_checked"])
    _no_cpc_supported(g)


@pytest.mark.parametrize("reply", [
    "That the accused obstructed the officer, an offence under Section 186 PPC.",
    "That the offence under Section 420 PPC is punishable with up to seven years and fine.",
])
def test_unrelated_statutes_are_untouched(draft, reply):
    g = draft(reply)
    assert g["text"].strip() == reply and g["withheld"] == [] and g.get("placeholder_alternative") is None


def test_an_invented_fact_and_a_cpc_citation_share_one_rechecked_alternative(draft):
    reply = "That summons were served on 3 March 2026 and the suit lies under Section 20 CPC."
    g = draft(reply, instruction="Add a service paragraph")
    alt = g["placeholder_alternative"]
    assert "facts you did not give" in alt["label"] and "CPC provision" in alt["label"]
    assert "[Verify the applicable CPC provision for Sindh]" in alt["text"] and "2026" not in alt["text"]
    assert "Section 20" not in g["text"]
    _no_cpc_supported(g)


# ── chat and research: the finalizer's visible answer ──────────────────────

EVIDENCE = [{"id": "1", "kind": "statute", "statute": "CPC 1908", "section": "9",
             "content": "9. The Courts shall have jurisdiction to try all suits of a civil nature."},
            {"id": "2", "kind": "statute", "statute": "PPC 1860", "section": "420",
             "content": "420. Cheating and dishonestly inducing delivery of property."}]
CPC_ANSWER = "Civil courts can try all suits of a civil nature under Section 9 CPC [1]."


def _claim(text, ids, statutes):
    return {"index": 1, "text": text, "source_ids": ids, "citation_status": "matched", "support": "supported",
            "sources": [{"id": i, "statute": s, "section": "9"} for i, s in zip(ids, statutes)]}


@pytest.fixture
def finalize(monkeypatch):
    from app.ai import cache
    from app.ai.nodes import finalizer_node as F
    writes = []

    async def store(*a, **k):
        writes.append(a)
    monkeypatch.setattr(cache, "set_result", store)

    def go(answer=CPC_ANSWER, province="sindh", basis="user_selected", surface="client", language="en",
           claims=None, **extra):
        state = {"query": "Can a civil court hear my suit?", "answer": answer, "is_grounded": True,
                 "confidence": 0.8, "surface": surface, "province": province, "jurisdiction_basis": basis,
                 "province_inferred": basis == "inferred_from_query", "language": language, "case_type": "civil",
                 "generation_evidence": EVIDENCE, "reranked_chunks": [{"statute": "CPC 1908"}],
                 "claim_assessments": claims if claims is not None else [_claim(answer, ["1"], ["CPC 1908"])],
                 **extra}
        return asyncio.run(F.finalizer_node(state))
    go.writes = writes
    return go


@pytest.mark.parametrize("surface", ["client", "research"])
@pytest.mark.parametrize("basis", ["user_selected", "case_record"])
def test_confirmed_punjab_answers_are_unchanged(finalize, surface, basis, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "research_answer_safeguards", True)
    out = finalize(province="punjab", basis=basis, surface=surface)
    assert out["claim_assessments"][0]["support"] == "supported"
    assert sc.NOTICE_MARK_EN not in out["answer"]


@pytest.mark.parametrize("surface", ["client", "research"])
@pytest.mark.parametrize("province, basis, where", [
    ("sindh", "user_selected", "Sindh"), ("kpk", "user_selected", "Khyber Pakhtunkhwa"),
    ("balochistan", "case_record", "Balochistan"), ("federal", "user_selected", "Islamabad"),
    ("unknown", "unspecified", "your province"), (None, None, "your province"),
    ("punjab", "inferred_from_query", "your province"),           # inferred is not confirmed
])
def test_outside_confirmed_punjab_the_answer_says_so_and_nothing_is_supported(finalize, surface, province,
                                                                              basis, where, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "research_answer_safeguards", True)
    out = finalize(province=province, basis=basis, surface=surface)
    claim = out["claim_assessments"][0]
    assert claim["support"] == "unassessed" and "Punjab version" in claim["support_reason"]
    assert out["answer"].count(sc.NOTICE_MARK_EN) == 1 and where in out["answer"]
    if where == "your province":
        assert "tell me your province" in out["answer"]                # ask only when it matters
    cpc = [c for c in out.get("citations") or [] if sc.is_cpc(c.get("statute", ""))]
    assert all(c.get("currency") == "unknown" for c in cpc)


def test_an_urdu_answer_gets_the_notice_in_urdu(finalize):
    out = finalize(answer="سیکشن 9 CPC کے تحت دیوانی عدالتیں تمام دیوانی مقدمات سن سکتی ہیں [1]۔", language="ur",
                   province="sindh")
    assert sc.NOTICE_MARK_UR in out["answer"] and sc.NOTICE_MARK_EN not in out["answer"]


def test_an_answer_without_the_cpc_is_untouched(finalize):
    answer = "Cheating is punishable under Section 420 PPC [2]."
    out = finalize(answer=answer, claims=[_claim(answer, ["2"], ["PPC 1860"])], province="sindh")
    assert out["claim_assessments"][0]["support"] == "supported" and sc.NOTICE_MARK_EN not in out["answer"]


def test_a_mixed_claim_is_downgraded_but_an_unrelated_claim_is_not(finalize):
    """Batch 6: support is per source. A valid PPC source does not carry the
    unverified CPC assertion into "supported"; the PPC-only claim stands."""
    mixed = "Under Section 9 CPC [1] and Section 420 PPC [2] the suit and the complaint may both proceed."
    ppc = "Cheating is punishable under Section 420 PPC [2]."
    claims = [_claim(mixed, ["1", "2"], ["CPC 1908", "PPC 1860"]), {**_claim(ppc, ["2"], ["PPC 1860"]), "index": 2}]
    out = finalize(answer=f"{mixed} {ppc}", claims=claims, province="sindh")
    assert out["claim_assessments"][0]["support"] == "unassessed"
    assert "also rests on it" in out["claim_assessments"][0]["support_reason"]
    assert out["claim_assessments"][1]["support"] == "supported"
    assert sc.NOTICE_MARK_EN in out["answer"]


def test_an_order_rule_answer_is_noted(finalize):
    answer = "A plaint that discloses no cause of action is rejected under Order VII Rule 11 CPC [1]."
    assert sc.NOTICE_MARK_EN in finalize(answer=answer, province="kpk")["answer"]


def test_a_cache_hit_written_before_this_rule_is_corrected_once(finalize):
    cached_claims = [_claim(CPC_ANSWER, ["1"], ["CPC 1908"])]
    cited = [{"statute": "CPC 1908", "section": "9", "status": "matched", "currency": "unknown"}]
    out = finalize(cache_hit=True, citations=cited, claims=cached_claims, province="sindh")
    assert out["claim_assessments"][0]["support"] == "unassessed"
    assert out["answer"].count(sc.NOTICE_MARK_EN) == 1
    again = finalize(answer=out["answer"], cache_hit=True, citations=cited,
                     claims=[_claim(CPC_ANSWER, ["1"], ["CPC 1908"])], province="sindh")
    assert again["answer"].count(sc.NOTICE_MARK_EN) == 1                   # never stacked


def test_a_follow_up_turn_is_corrected_too(finalize):
    out = finalize(followup_intent="format", province="balochistan")
    assert out["claim_assessments"][0]["support"] == "unassessed" and sc.NOTICE_MARK_EN in out["answer"]


def test_the_stored_cache_entry_already_carries_the_correction(finalize):
    finalize(province="sindh")
    if finalize.writes:                                                  # written only when the entry is cacheable
        payload = finalize.writes[-1][3]
        assert sc.NOTICE_MARK_EN in payload["answer"]
        assert payload["claims"][0]["support"] == "unassessed"


# ── mutation: each safety boundary must be caught ──────────────────────────

def _fails(fn, *a, **k):
    with pytest.raises((AssertionError, KeyError, TypeError, pytest.fail.Exception)):
        fn(*a, **k)


def test_mutant_inferred_punjab_counts_as_confirmed(finalize, monkeypatch):
    monkeypatch.setattr(sc, "cpc_scope", lambda province, basis=None, inferred=False:
                        sc.SCOPE_PUNJAB if (province or "").lower() == "punjab" else sc.SCOPE_OTHER)
    _fails(test_outside_confirmed_punjab_the_answer_says_so_and_nothing_is_supported, finalize, "client",
           "punjab", "inferred_from_query", "your province", monkeypatch)


def test_mutant_unknown_counts_as_punjab(finalize, monkeypatch):
    real = sc.cpc_scope
    monkeypatch.setattr(sc, "cpc_scope", lambda province, basis=None, inferred=False:
                        sc.SCOPE_PUNJAB if real(province, basis, inferred) == sc.SCOPE_UNKNOWN else real(province, basis, inferred))
    _fails(test_outside_confirmed_punjab_the_answer_says_so_and_nothing_is_supported, finalize, "client",
           "unknown", "unspecified", "your province", monkeypatch)


def test_mutant_without_the_drafter_clause_edits(draft, monkeypatch):
    monkeypatch.setattr(sc, "cpc_clause_edits", lambda *a, **k: {"main": [], "alt": [], "withheld": [], "notes": []})
    _fails(test_outside_punjab_only_the_cpc_clause_leaves_the_insertable_text, draft, "sindh", "Sindh")


def test_mutant_that_replaces_instead_of_dropping_an_under_clause(draft, monkeypatch):
    monkeypatch.setattr(sc, "_PREP", re.compile(r"(?!x)x"))              # never recognises "under ..."
    _fails(test_order_rule_and_section_forms_lose_only_the_authority, draft,
           "That the plaint is liable to be rejected under Order VII Rule 11 CPC as it discloses no cause of action.",
           "That the plaint is liable to be rejected as it discloses no cause of action.")


def test_mutant_that_ignores_the_lawyers_own_text(draft, monkeypatch):
    real = sc.cpc_clause_edits
    monkeypatch.setattr(sc, "cpc_clause_edits", lambda units, norm, province, own_text="", skip=None:
                        real(units, norm, province, "", skip))
    _fails(test_the_lawyers_own_cpc_text_is_never_rewritten, draft)


def test_mutant_without_the_chat_correction(finalize, monkeypatch):
    monkeypatch.setattr(sc, "apply_cpc_jurisdiction", lambda claims, citations, answer, *a, **k:
                        (claims, citations, answer, {}))
    _fails(test_outside_confirmed_punjab_the_answer_says_so_and_nothing_is_supported, finalize, "client",
           "sindh", "user_selected", "Sindh", monkeypatch)


def test_mutant_whose_cpc_pattern_also_matches_the_ppc(draft, monkeypatch):
    broad = re.compile(sc._CPC_CITATION.pattern + r"|Section\s+\d{1,3}\s+PPC", sc._CPC_CITATION.flags)
    monkeypatch.setattr(sc, "_CPC_CITATION", broad)
    _fails(test_unrelated_statutes_are_untouched, draft,
           "That the accused obstructed the officer, an offence under Section 186 PPC.")
