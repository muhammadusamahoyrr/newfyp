"""Exact-provision integrity (ai/exact_provision.py, 2026-10-14). Offline:
Chroma is replaced by an in-memory collection holding real corpus texts.

Live failure: "What is Section 489-F PPC?" was answered as "a definitional
clause ... the person in whose favour a cheque is issued", from a CrPC
schedule row; the PPC 489-F text was never retrieved (the base index labels it
"489").
"""
from __future__ import annotations

import asyncio

import pytest

from app.ai import exact_provision as X

# Real corpus texts (statutes_ppc_1860_*, statutes_crpc_1898_*), trimmed.
PPC_489F = {"statute": "PPC 1860", "section_number": "489F", "chunk_id": "statutes_ppc_1860_0760",
            "content": "489- F.  Dishonestly issuing a cheque:  Whoever dishonestly issues a cheque towards "
                       "repayment of a loan or fulfilment of an obligation which is dishonoured on presentation, "
                       "shall be punishable with imprisonment which may extend to three years, or with fine, or with both"}
PPC_489 = {"statute": "PPC 1860", "section_number": "489", "chunk_id": "statutes_ppc_1860_0753",
           "content": "489. Tampering with property mark with intent to cause injury:  Whoever removes, destroys, "
                      "defaces or adds to any property mark"}
PPC_489A = {"statute": "PPC 1860", "section_number": "489", "chunk_id": "statutes_ppc_1860_0754",
            "content": "489- A.  Counterfeiting currency-notes or bank-notes:  Whoever counterfeits"}
PPC_302 = {"statute": "PPC 1860", "section_number": "302", "chunk_id": "statutes_ppc_1860_0439",
           "content": "302. Punishment of qatl-i-amd:  Whoever commits qatl-e-amd shall, subject to the provisions "
                      "of this Chapter be: (a) punished with death as qisas"}
PPC_506 = {"statute": "PPC 1860", "section_number": "506", "chunk_id": "statutes_ppc_1860_0794",
           "content": "506. Punishment for criminal intimidation:  Whoever commences the offence of criminal "
                      "intimidation shall be punished with imprisonment"}
CRPC_ROW_489F = {"statute": "CrPC 1898", "section_number": "489", "chunk_id": "statutes_crpc_1898_1380",
                 "content": "489- F Dishonestly issuing a cheque May arrest without warrant Ditto Bailable "
                            "Compoundable Imprisonment which may extend to three years"}
CRPC_345_ROW = {"statute": "CrPC 1898", "section_number": "345", "chunk_id": "statutes_crpc_1898_0928",
                "content": "Dishonestly issuing a cheque. 489-F The person in whose favour the cheque is issued."}


class _Collection:
    def __init__(self, docs):
        self.docs = docs

    def get(self, where=None, include=None, limit=None):
        wanted = set(where["section_number"]["$in"])
        hits = [d for d in self.docs if d["section_number"] in wanted]
        return {"documents": [d["content"] for d in hits],
                "metadatas": [{k: v for k, v in d.items() if k != "content"} for d in hits]}


class _Client:
    def __init__(self, by_name):
        self.by_name = by_name

    def get_collection(self, name):
        if name not in self.by_name:
            raise ValueError(name)
        return self.by_name[name]


@pytest.fixture
def corpus(monkeypatch):
    """The versioned index carries the lettered relabel ("489F"); the base
    index labels 489-F as "489", exactly like the real corpus."""
    sec_v2 = _Collection([PPC_489F, PPC_489, {**PPC_489A, "section_number": "489A"}, PPC_302, PPC_506,
                          CRPC_ROW_489F, CRPC_345_ROW])
    base = _Collection([{**PPC_489F, "section_number": "489"}, PPC_489, PPC_489A, PPC_302, PPC_506,
                        CRPC_ROW_489F, CRPC_345_ROW])
    client = _Client({"criminal_collection__sec_v2": sec_v2, "criminal_collection": base,
                      "civil_collection": _Collection([]), "family_collection": _Collection([]),
                      "constitutional_collection": _Collection([])})
    monkeypatch.setattr("app.db.chroma.get_chroma", lambda: client)
    return client


def _ids(q):
    return {k: [c["chunk_id"] for c in v] for k, v in X.fetch(X.requested(q)).items()}


@pytest.mark.parametrize("question,label,chunk", [
    ("What is Section 489-F PPC?", "Section 489-F PPC", "statutes_ppc_1860_0760"),
    ("What does Section 302 PPC say?", "Section 302 PPC", "statutes_ppc_1860_0439"),
    ("What is Section 506 PPC?", "Section 506 PPC", "statutes_ppc_1860_0794"),
    ("dafa 489 F PPC kya hai", "Section 489-F PPC", "statutes_ppc_1860_0760"),
    ("تعزیرات پاکستان کی دفعہ ۴۸۹-ایف کیا ہے؟", "Section 489-F PPC", "statutes_ppc_1860_0760"),
])
def test_the_named_provision_is_fetched_by_identity(corpus, question, label, chunk):
    assert _ids(question) == {label: [chunk]}


@pytest.mark.parametrize("question,label,chunk", [
    ("What is Section 489 PPC?", "Section 489 PPC", "statutes_ppc_1860_0753"),      # not 489-F / 489-A
    ("What is Section 489-A PPC?", "Section 489-A PPC", "statutes_ppc_1860_0754"),  # not 489 / 489-F
])
def test_lettered_lookalikes_never_stand_in_for_each_other(corpus, question, label, chunk):
    assert _ids(question) == {label: [chunk]}


def test_a_schedule_row_or_another_act_is_never_the_provision(corpus):
    for chunk in (CRPC_ROW_489F, CRPC_345_ROW):
        assert not X.is_exact(chunk, X.requested("What is Section 489-F PPC?")[0])


def test_a_provision_not_in_the_corpus_is_reported_missing(corpus):
    assert _ids("What is Section 999 PPC?") == {"Section 999 PPC": []}


def test_issue_lookup_fetches_the_next_chunk_of_a_long_section(monkeypatch):
    from app.ai.answer_citations import ParsedCitation, normalise_statute

    mflo = "Muslim Family Laws Ordinance 1961"
    source = "mflo.pdf"
    rows = [
        {"statute": mflo, "section_number": "7", "source_file": source,
         "chunk_id": "statutes_mflo_0007", "content": "7. Talaq. (1) Any man who wishes to divorce his wife shall give written notice."},
        {"statute": mflo, "section_number": "7", "source_file": source,
         "chunk_id": "statutes_mflo_0008", "content": "(3) A talaq takes effect after ninety days from notice."},
        {"statute": "Another Act", "section_number": "7", "source_file": "other.pdf",
         "chunk_id": "statutes_other_0009", "content": "(3) An unrelated period is seven days."},
    ]
    client = _Client({"family_collection": _Collection(rows),
                      "criminal_collection": _Collection([]), "civil_collection": _Collection([]),
                      "constitutional_collection": _Collection([])})
    monkeypatch.setattr("app.db.chroma.get_chroma", lambda: client)
    citation = ParsedCitation(mflo, "7", (normalise_statute(mflo), "7"))

    ordinary = X.fetch([citation])[X.label(citation)]
    complete = X.fetch([citation], include_continuations=True)[X.label(citation)]

    assert [c["chunk_id"] for c in ordinary] == ["statutes_mflo_0007"]
    assert [c["chunk_id"] for c in complete] == ["statutes_mflo_0007", "statutes_mflo_0008"]
    assert "ninety days" in complete[1]["content"]


def test_no_named_provision_no_lookup():
    assert X.requested("My cheque bounced, what can I do?") == []


EV_ROWS = [{"id": "1", "kind": "statute", "statute": "CrPC 1898", "section": "345",
            "content": CRPC_345_ROW["content"]},
           {"id": "2", "kind": "statute", "statute": "CrPC 1898", "section": "489",
            "content": CRPC_ROW_489F["content"]}]
WRONG = ("Section 489-F of the Pakistan Penal Code defines “the person in whose favour a cheque is issued.” "
         "It is a definitional clause used to identify the payee [1].")


def test_a_short_question_without_the_provision_text_gets_an_honest_answer():
    out, missing = X.enforce(WRONG, "What is Section 489-F PPC?", EV_ROWS, urdu=False, disclaimer="D")
    assert missing == ["Section 489-F PPC"]
    assert "definitional" not in out and "couldn't find the text of Section 489-F PPC" in out


def test_with_the_provision_text_the_answer_is_left_alone():
    ev = EV_ROWS + [{"id": "3", "kind": "statute", "statute": "PPC 1860", "section": "489F",
                     "content": PPC_489F["content"]}]
    ok = "Section 489-F PPC makes dishonestly issuing a cheque an offence [3]."
    assert X.enforce(ok, "What is Section 489-F PPC?", ev, urdu=False) == (ok, [])


def test_a_longer_question_keeps_its_answer_behind_a_plain_note():
    q = "My partner's cheque bounced and he refuses to pay; can I file a case under Section 489-F PPC and recover?"
    out, missing = X.enforce("You can sue for recovery [1].", q, EV_ROWS, urdu=False)
    assert missing and out.startswith("Note: the text of Section 489-F PPC was not found")


def test_engine_output_naming_the_provision_counts_as_available():
    ev = [{"id": "9", "kind": "engine", "statute": "find_offence_sections (computed)", "section": "",
           "content": "{'matches': [{'id': 'PPC:506', 'law': 'PPC', 'section': '506'}]}"}]
    assert X.in_evidence(X.requested("What is Section 506 PPC?")[0], ev)


def test_a_claim_naming_the_ppc_but_citing_a_crpc_row_is_unsupported():
    from app.ai.answer_citations import split_claims
    claims = split_claims(WRONG, EV_ROWS, attach_markers=True)
    for c in claims:
        c["support"] = "supported"                    # an over-trusting judge
    X.misattributed(claims, EV_ROWS)
    named = [c for c in claims if "489" in c["text"]]
    assert named and all(c["support"] == "unsupported" for c in named)


def test_the_retrieval_step_pins_the_exact_text_for_client_chat_only(corpus):
    from app.ai.nodes.retrieval_node import apply_client_exact_provisions
    rows = [{**CRPC_345_ROW, "section_number": "345"}, {**CRPC_ROW_489F}]
    client = {"query": "What is Section 489-F PPC?", "surface": "client"}
    chunks, found = asyncio.run(apply_client_exact_provisions(client, list(rows)))
    assert chunks[0]["chunk_id"] == "statutes_ppc_1860_0760" and found == {"Section 489-F PPC": True}
    research = {"query": "What is Section 489-F PPC?"}
    assert asyncio.run(apply_client_exact_provisions(research, list(rows))) == (rows, {})


def test_client_topic_lookup_pins_the_governing_provision_even_when_no_section_is_named(monkeypatch):
    from app.ai import issue_lookup
    from app.ai.nodes.retrieval_node import apply_client_exact_provisions
    s7 = {"statute": "Muslim Family Laws Ordinance 1961", "section_number": "7",
          "chunk_id": "mflo-7", "content": "7. Talaq. Any man who wishes to divorce his wife...",
          "issue_provision": {"statute": "Muslim Family Laws Ordinance 1961",
                              "section": "7", "heading": "Talaq"}}
    s8 = {"statute": "Muslim Family Laws Ordinance 1961", "section_number": "8",
          "chunk_id": "mflo-8", "content": "8. Dissolution of marriage otherwise than by talaq."}
    monkeypatch.setattr(issue_lookup, "fetch_governing", lambda *a, **k: [s7])
    state = {"surface": "client", "query": ("Under the Muslim Family Laws Ordinance 1961, what is the "
                                               "procedure for a husband sending a divorce notice?")}

    out, named = asyncio.run(apply_client_exact_provisions(state, [s8]))

    assert out[0]["chunk_id"] == "mflo-7"
    assert named == {}, "topic lookup is governing-law selection, not a user-named section"


def test_the_grader_keeps_the_exact_text_first_for_client_chat_only():
    import inspect
    from app.ai.nodes import retrieval_grader_node
    src = inspect.getsource(retrieval_grader_node.retrieval_grader_node)
    # Gated in one place (ai/answer_safeguards.py): client always, research by flag.
    assert "answer_safeguards.on(state)" in src and "exact_provision.pin(ordered" in src


def test_a_lettered_section_gets_its_label_back_from_its_own_heading(corpus):
    """Live final run: the base index labels the 489-F passage "489"; the model
    copied it and called the cheque offence "Section 489" (property marks)."""
    from app.ai.nodes.retrieval_node import apply_client_exact_provisions
    base_489f = {**PPC_489F, "section_number": "489"}          # as the base index stores it
    chunks = [base_489f, PPC_489, {**CRPC_ROW_489F}]
    client = {"query": "My partner's cheque bounced, can I file a criminal case?", "surface": "client"}
    out, _ = asyncio.run(apply_client_exact_provisions(client, list(chunks)))
    labels = {c["chunk_id"]: c["section_number"] for c in out}
    assert labels["statutes_ppc_1860_0760"] == "489-F"
    assert labels["statutes_ppc_1860_0753"] == "489"            # the real s.489 stays 489
    assert labels["statutes_crpc_1898_1380"] == "489"           # a schedule row is not relabelled
    research = {"query": client["query"]}
    assert asyncio.run(apply_client_exact_provisions(research, list(chunks)))[0] == chunks
