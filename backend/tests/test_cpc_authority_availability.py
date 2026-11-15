"""Authority availability: no "supported" on leftover law when the CPC a question
needs is not held for the matter's province (2026-10-17; release blocker found by
the scratch CPC-relabel experiment, evals/legal_sources/SCRATCH_CPC_RELABEL_2026-10-17.md).

The indexed CPC is the Punjab Code text. Its jurisdiction is read from its
recorded PROVENANCE (source file), never from the chunk's `province` field --
which is wrongly `federal` today and `punjab` after the scratch relabel; both
states are tested. When a question requires the CPC and no CPC text applicable to
the matter's province is held, the intake evidence gate returns
`source_unavailable_for_jurisdiction` BEFORE any judge can treat unrelated
chunks as support. Non-CPC questions, mixed questions' non-CPC part, and
facts-only analysis are not blocked.

Read through the real gate `decide`, the gate node, `_run_intake_ai` and the
chat finalizer. No store, no model.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from app.ai import source_currency as sc
from app.ai.nodes import intake_evidence_gate_node as gate

CPC_FILE = "code of civil procedure 1908.pdf"
SOURCE_UNAVAILABLE = "source_unavailable_for_jurisdiction"


def cpc(section, province="federal"):
    return {"statute": "CPC 1908", "section_number": section, "source_file": CPC_FILE, "province": province,
            "content": f"{section}. (CPC text)", "chunk_id": f"cpc-{section}-{province}"}


def other(statute, section, province="federal"):
    return {"statute": statute, "section_number": section, "province": province,
            "content": f"{section}. ({statute})", "chunk_id": f"{statute}-{section}"}


LEFTOVERS = [other("Limitation Act 1908", "3"), other("Transfer of Property Act 1882", "54")]
CPC_CURRENT = [cpc("94"), cpc("151"), cpc("O39R1")]                   # today's metadata: federal
CPC_RELABELLED = [cpc("94", "punjab"), cpc("151", "punjab"), cpc("O39R1", "punjab")]
PROC_Q = "My neighbour is about to sell the plot; can I get a temporary injunction to restrain the defendant?"


def decide(chunks, province, text=PROC_Q, **kw):
    return gate.decide(chunks=chunks, retrieval_error=False, province=province, user_text=text,
                       relevance_score=None, index=_INDEX, **kw)


class _Idx:
    """Minimal corpus index so the gate's provision parser runs without a store."""
    statutes = ["CPC 1908", "Limitation Act 1908", "Specific Relief Act 1877", "PPC 1860"]

    def canonical(self, name):
        from app.ai.answer_citations import normalise_statute
        return next((s for s in self.statutes if normalise_statute(s) == normalise_statute(name)), None)

    def coverage(self, statute):
        return None


_INDEX = _Idx()


# ── the experiment's failure, reproduced ────────────────────────────────────

@pytest.mark.parametrize("province", ["sindh", "kpk", "balochistan", "federal"])
def test_relabelled_index_leftover_law_is_never_supported(province):
    """Scratch relabel: the CPC is filtered out for this province, only unrelated
    law is left -- that must not be 'supported'."""
    admissible, rec = decide(LEFTOVERS, province)
    assert rec["status"] == SOURCE_UNAVAILABLE
    assert rec["authority"]["cpc_required"] and not rec["authority"]["cpc_available"]


@pytest.mark.parametrize("province", ["sindh", "kpk", "balochistan", "federal"])
def test_current_index_punjab_cpc_is_not_support_outside_punjab(province):
    """Today's metadata calls the Punjab CPC 'federal', so it IS retrieved here;
    provenance, not that label, decides it is not this province's law."""
    admissible, rec = decide(CPC_CURRENT + LEFTOVERS, province)
    assert rec["status"] == SOURCE_UNAVAILABLE
    assert not any(c["statute"] == "CPC 1908" for c in admissible)


@pytest.mark.parametrize("chunks", [CPC_CURRENT, CPC_RELABELLED], ids=["current", "relabelled"])
def test_confirmed_punjab_keeps_its_cpc(chunks):
    admissible, rec = decide(chunks + LEFTOVERS, "punjab")
    assert rec["status"] == gate.SUPPORTED and rec["authority"]["cpc_available"]
    assert sum(c["statute"] == "CPC 1908" for c in admissible) == 3


@pytest.mark.parametrize("chunks", [CPC_CURRENT, CPC_RELABELLED], ids=["current", "relabelled"])
def test_unknown_province_is_not_punjab_and_asks_for_it(chunks):
    admissible, rec = decide(chunks + LEFTOVERS, "")
    assert rec["status"] == SOURCE_UNAVAILABLE
    assert any("province" in r for r in rec["reasons"])


def test_inferred_punjab_is_not_confirmed():
    admissible, rec = decide(CPC_RELABELLED, "punjab", basis="inferred_from_query", inferred=True)
    assert rec["status"] == SOURCE_UNAVAILABLE


# ── what must NOT be blocked ────────────────────────────────────────────────

@pytest.mark.parametrize("text, chunks", [
    ("What is the limitation period for a suit to recover money I lent?", [other("Limitation Act 1908", "3")]),
    ("My neighbour obstructed the officer; is that an offence under Section 186 PPC?", [other("PPC 1860", "186")]),
    ("I filed an application in the court about my shop and the court fixed a date.", LEFTOVERS),
    ("The family court passed a decree of dissolution of marriage last year.", LEFTOVERS),
    ("Is there a time limit to file an appeal in the High Court?", LEFTOVERS),
])
def test_non_cpc_questions_and_generic_words_are_not_blocked(text, chunks):
    admissible, rec = decide(chunks, "sindh", text)
    assert rec["status"] == gate.SUPPORTED, (text, rec["status"], rec.get("authority"))
    assert not rec["authority"]["cpc_required"]


def test_specific_performance_is_not_supported_by_a_fixture_specific_relief_chunk():
    """Correction (batch 10): this file used to assert that a specific-performance
    question was "supported" by a `Specific Relief Act 1877` chunk. The real
    corpus holds 0 chunks of that Act (verified snapshot 2026-10-17;
    corpus_instruments.json): a fixture is not corpus coverage. Such a chunk is
    an unverified source, and the question is source-unavailable everywhere."""
    for province in ("sindh", "punjab"):
        admissible, rec = decide([other("Specific Relief Act 1877", "12")] + LEFTOVERS, province,
                                 "Can the buyer get specific performance of the agreement to sell?")
        assert rec["status"] == SOURCE_UNAVAILABLE, province
        assert not any("Specific Relief" in c["statute"] for c in admissible)


@pytest.mark.parametrize("chunks", [CPC_CURRENT, CPC_RELABELLED], ids=["current", "relabelled"])
def test_a_mixed_question_keeps_its_non_cpc_law(chunks):
    # (The Specific Relief Act is not in the corpus at all -- the gate's existing
    # capability check answers that -- so the mixed case names a held Act.)
    text = ("Can I get a temporary injunction, and what limitation period applies to my suit under the "
            "Limitation Act?")
    admissible, rec = decide(chunks + [other("Limitation Act 1908", "3")], "sindh", text)
    assert rec["status"] == gate.SUPPORTED                       # the Limitation Act part stands
    assert [c["statute"] for c in admissible] == ["Limitation Act 1908"]
    assert any("CPC" in c for c in rec["caveats"])


def test_facts_only_follows_a_source_unavailable_gate():
    """The gate node hands no law forward, so the analysis is facts-only."""
    state = {"reranked_chunks": CPC_CURRENT + LEFTOVERS, "province": "sindh", "user_text": PROC_Q}
    out = asyncio.run(gate.intake_evidence_gate_node(state))
    assert out["evidence_gate"]["status"] == SOURCE_UNAVAILABLE and out["reranked_chunks"] == []


# ── the question forms that require the CPC ─────────────────────────────────

@pytest.mark.parametrize("text", [
    "Is my suit maintainable under Section 9 CPC?", "Can the plaint be rejected under Order VII Rule 11 CPC?",
    "Application under O VII R 11", "an application under Order XXXIX Rules 1 and 2",
    "rejection of the plaint because it discloses no cause of action", "setting aside an ex parte decree",
    "execution of the decree by attachment of property", "time to file the written statement",
    "ضابطہ دیوانی کی دفعہ 20 کے تحت دعویٰ", "CPC ki dafa 20 ke tehat case", "مجھے حکم امتناعی چاہیے",
    "kya mujhe hukm imtinai mil sakta hai", "yakterfa decree khatam karwani hai",
])
def test_cpc_requirement_is_recognised(text):
    assert sc.cpc_requirement(text)["required"], text


@pytest.mark.parametrize("text", [
    "I went to court with an application.", "The court passed a decree.", "My suit is pending.",
    "Section 186 PPC", "bail application under section 497 CrPC", "Order of the Supreme Court Rules 1980",
    "an order of the court", "the injunction of my doctor was to rest",
])
def test_generic_words_do_not_require_the_cpc(text):
    assert not sc.cpc_requirement(text)["required"], text


@pytest.mark.parametrize("chunk, expected", [
    (cpc("9"), "punjab"), (cpc("9", "punjab"), "punjab"),
    ({"statute": "CPC 1908", "source_file": "some_other_cpc.pdf", "province": "federal"}, "unverified"),
    (other("Limitation Act 1908", "3"), None),
])
def test_cpc_jurisdiction_comes_from_provenance_not_the_label(chunk, expected):
    assert sc.cpc_chunk_jurisdiction(chunk) == expected


# ── chat / research final answer: CPC required, only leftover law cited ────

def test_chat_answer_from_leftover_law_says_the_cpc_is_not_held(monkeypatch):
    from app.ai import cache
    from app.ai.nodes import finalizer_node as F

    async def store(*a, **k):
        return None
    monkeypatch.setattr(cache, "set_result", store)
    evidence = [{"id": "1", "kind": "statute", "statute": "Limitation Act 1908", "section": "3", "province": "federal",
                 "content": "3. Dismissal of suits instituted after period of limitation."}]
    answer = "Suits filed after the limitation period are dismissed [1]."
    base = {"query": PROC_Q, "answer": answer, "is_grounded": True, "confidence": 0.8, "surface": "client",
            "language": "en", "case_type": "civil", "generation_evidence": evidence, "reranked_chunks": evidence,
            "claim_assessments": [{"index": 1, "text": answer, "source_ids": ["1"], "citation_status": "matched",
                                   "support": "supported",
                                   "sources": [{"id": "1", "statute": "Limitation Act 1908", "section": "3"}]}]}
    sindh = asyncio.run(F.finalizer_node({**base, "province": "sindh", "jurisdiction_basis": "user_selected"}))
    # Batch 10: such an answer reaching the finalizer WITHOUT the decision-node
    # authority gate is withheld whole, not just annotated (authority_registry).
    assert answer not in sindh["answer"]
    assert "Code of Civil Procedure" in sindh["answer"] and "not held" in sindh["answer"]
    assert "Sindh" in sindh["answer"] and sindh["is_grounded"] is False
    punjab = asyncio.run(F.finalizer_node({**base, "province": "punjab", "jurisdiction_basis": "user_selected"}))
    assert sc.NOTICE_MARK_EN not in punjab["answer"]


@pytest.mark.parametrize("meta_province", ["federal", "punjab"], ids=["current", "relabelled"])
@pytest.mark.parametrize("section", ["9", "20", "151", "O7R11"])
def test_exact_section_identity_is_kept_and_never_supported_outside_punjab(meta_province, section):
    label = {"9": "Section 9", "20": "Section 20", "151": "Section 151", "O7R11": "Order VII Rule 11"}[section]
    answer = f"Under {label} CPC [1] the court may act."
    claims = [{"index": 1, "text": answer, "source_ids": ["1"], "citation_status": "matched", "support": "supported",
               "sources": [{"id": "1", "statute": "CPC 1908", "section": section}]}]
    cites = [{"statute": "CPC 1908", "section": section, "status": "matched", "province": meta_province}]
    claims, cites, out, info = sc.apply_cpc_jurisdiction(claims, cites, answer, "sindh", "user_selected")
    assert claims[0]["support"] == "unassessed" and claims[0]["sources"][0]["section"] == section
    assert cites[0]["section"] == section and cites[0]["currency"] == "unknown"
    assert out.startswith(answer) and sc.NOTICE_MARK_EN in out


# ── mutation ────────────────────────────────────────────────────────────────

def _fails(fn, *a, **k):
    with pytest.raises((AssertionError, KeyError, TypeError, pytest.fail.Exception)):
        fn(*a, **k)


def test_mutant_that_trusts_the_province_label(monkeypatch):
    from app.ai import authority_registry as ar     # batch 10: the gate reads the registry
    monkeypatch.setattr(ar, "chunk_authority",
                        lambda c: ("cpc", c.get("province") or "federal") if sc.is_cpc(str(c.get("statute", ""))) else None)
    monkeypatch.setattr(ar, "available", lambda *a, **k: True)
    _fails(test_current_index_punjab_cpc_is_not_support_outside_punjab, "sindh")


def test_mutant_without_the_authority_check(monkeypatch):
    monkeypatch.setattr(sc, "cpc_requirement", lambda text: {"required": False, "explicit": [], "procedural": [],
                                                             "other_law": []})
    _fails(test_relabelled_index_leftover_law_is_never_supported, "sindh")


def test_mutant_with_broad_procedural_words(monkeypatch):
    real = sc.cpc_requirement
    monkeypatch.setattr(sc, "cpc_requirement",
                        lambda text: {**real(text), "required": real(text)["required"] or "court" in text.lower()})
    _fails(test_non_cpc_questions_and_generic_words_are_not_blocked,
           "I filed an application in the court about my shop and the court fixed a date.", LEFTOVERS)


def test_mutant_that_blocks_mixed_questions(monkeypatch):
    real = sc.cpc_requirement
    monkeypatch.setattr(sc, "cpc_requirement", lambda text: {**real(text), "other_law": []})
    from app.ai import authority_registry as ar     # batch 10: the gate reads the registry's other_law
    monkeypatch.setattr(ar, "other_law", lambda text: [])
    _fails(test_a_mixed_question_keeps_its_non_cpc_law, CPC_RELABELLED)


def test_mutant_that_assumes_punjab_when_unknown(monkeypatch):
    from app.ai import authority_registry as ar     # batch 10: the gate reads the registry
    real = ar.available
    monkeypatch.setattr(ar, "available",
                        lambda key, province, basis=None, inferred=False: True if not province else real(key, province, basis, inferred))
    _fails(test_unknown_province_is_not_punjab_and_asks_for_it, CPC_CURRENT)
