"""Draft Assistant modes (2026-10-14).

The lawyer's AI panel used to overwrite the whole formatted document with the
reply. Now the reply is a proposal the lawyer inserts, and the request says what
to return: "full" (the default -- the complete document, exactly as before),
"clause" (only the new clause), "rewrite" (only the selected passage, rewritten)
or "answer" (a reply, not document text).

These call the real route with retrieval and the model faked, and read the
exact messages the model would have received.
"""
from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

import app.api.v1.routes.ai as ai_routes

LAWYER = {"_id": "lawyer-1", "role": "lawyer"}


@pytest.fixture
def run(monkeypatch):
    seen = {}

    def law(q, ct, pr, also_query=""):
        seen.setdefault("query", q)
        seen.setdefault("also_query", also_query)     # the lawyer's own words, searched too
        seen["province"] = pr
        return "LAW"
    monkeypatch.setattr(ai_routes, "_retrieve_law_context", law)
    # A healthy identity store (missing / unhealthy ones: test_identity_index_safety.py).
    from app.ai import index_health
    monkeypatch.setattr(index_health, "require_all", lambda names, client=None: list(names))
    monkeypatch.setattr(ai_routes, "_exact_provisions_for", lambda text: list(seen.get("exact", [])))

    async def no_case_law(q):
        return ""
    monkeypatch.setattr(ai_routes, "_retrieve_case_law_context", no_case_law)

    async def verification(payload):
        seen["verified"] = payload
        return {"ran": False}
    monkeypatch.setattr(ai_routes, "_verification_record", verification)

    async def record(**kw):
        seen.setdefault("recorded", []).append(kw)
        return None
    monkeypatch.setattr(ai_routes.provenance_service, "record_answer", record)

    class _Chunk:
        def __init__(self, content):
            self.content = content

    class _LLM:
        async def astream(self, messages):
            seen["messages"] = messages
            yield _Chunk(seen.get("reply", "NEW CLAUSE"))
    monkeypatch.setattr("app.ai.llm.get_llm", lambda **k: _LLM())

    def go(**body):
        async def main():
            resp = await ai_routes.ai_draft_stream(ai_routes.DraftRequest(**body), current_user=LAWYER)
            return [part async for part in resp.body_iterator]
        seen["events"] = asyncio.run(main())
        return seen
    go.seen = seen  # lets a test set the model's reply / exact texts before the call
    return go


def test_the_default_request_is_unchanged(run):
    s = run(instruction="Add a jurisdiction paragraph", document="IN THE COURT ...", template="Bail Application")
    system = s["messages"][0]["content"]
    assert "COMPLETE updated document" in system
    assert "RETURN FORMAT" not in system
    assert "SELECTED PASSAGE" not in s["messages"][-1]["content"]


def test_clause_mode_asks_for_only_the_new_clause(run):
    s = run(instruction="Add a confidentiality clause", document="LEASE AGREEMENT ...", template="Lease Agreement",
            mode="clause")
    system = s["messages"][0]["content"]
    assert "ONLY the new clause" in system
    assert "never the whole document" in system


def test_rewrite_mode_sends_the_selection_and_asks_for_only_that_passage(run):
    passage = "That the Applicant is innocent and denies all allegations."
    s = run(instruction="Make this stronger", document="... " + passage + " ...", template="Bail Application",
            mode="rewrite", selection=passage)
    assert "ONLY that passage rewritten" in s["messages"][0]["content"]
    user = s["messages"][-1]["content"]
    assert "SELECTED PASSAGE" in user and passage in user
    # retrieval reads the passage too ("make this stronger" names no law)
    assert "innocent" in s["query"]


def test_rewrite_without_a_selection_is_refused(run):
    from app.core.exceptions import AppValidationError
    with pytest.raises(AppValidationError):
        run(instruction="Make this stronger", document="x", mode="rewrite", selection="   ")


def test_answer_mode_asks_for_a_reply_not_document_text(run):
    s = run(instruction="What are the risks for my client?", document="LOAN AGREEMENT ...", mode="answer")
    assert "Do not return document text" in s["messages"][0]["content"]


def test_an_unknown_mode_is_rejected_by_the_request_model():
    with pytest.raises(ValidationError):
        ai_routes.DraftRequest(instruction="x", mode="overwrite")


def test_the_stream_still_ends_with_verification_and_done(run):
    s = run(instruction="Add a clause", document="x", mode="clause")
    joined = "".join(e if isinstance(e, str) else e.decode() for e in s["events"])
    assert '"content": "NEW CLAUSE"' in joined
    assert '"verification"' in joined
    assert joined.rstrip().endswith("data: [DONE]")


# ── the legal-authority guard on the finished draft (2026-10-14) ─────────────

def _events(seen):
    import json
    out = []
    for e in seen["events"]:
        e = e if isinstance(e, str) else e.decode()
        if e.startswith("data: {"):
            out.append(json.loads(e[len("data: "):]))
    return out


@pytest.fixture
def corpus(monkeypatch):
    """The fake corpus index and provision texts from the visible-authority tests."""
    from app.ai import corpus_index, exact_provision
    from tests import test_visible_authority as V
    monkeypatch.setattr(corpus_index, "get_index", lambda: V.INDEX)
    monkeypatch.setattr(corpus_index, "get_drafter_index", lambda: V.INDEX)
    texts = {"Section 438 CrPC": [V.CRPC_438], "Section 497 CrPC": [{"statute": "CrPC 1898", "content":
             "497. When bail may be taken in case of non-bailable offence. (1) When any person ..."}],
             "Section 420 PPC": [V.PPC_420]}
    monkeypatch.setattr(exact_provision, "fetch",
                        lambda cits, research=False, strict=False: {
                            exact_provision.label(c): texts.get(exact_provision.label(c), []) for c in cits})
    return V


def test_an_omitted_section_is_withheld_from_the_proposal_with_its_reason(run, corpus):
    run.seen["reply"] = ("That the Applicant is entitled to bail under Section 497 CrPC.\n\n"
                     "That pre-arrest bail may also be granted under Section 438 CrPC.")
    seen = run(instruction="Add a ground for bail", document="BAIL APPLICATION ...", template="Bail Application",
               mode="clause")
    guard = next(e["guard"] for e in _events(seen) if "guard" in e)
    assert guard["ran"] is True
    assert "497 CrPC" in guard["text"] and "438" not in guard["text"]
    assert "Withheld" not in guard["text"], "a note was written into the draft text"
    assert any("omitted" in r for w in guard["withheld"] for r in w["reasons"])
    # the citation check and the audit read the GUARDED text
    assert "438" not in seen["verified"]["draft"]


def test_a_clean_draft_passes_unchanged(run, corpus):
    run.seen["reply"] = "That the offence under Section 420 PPC is punishable with up to seven years and fine."
    seen = run(instruction="x", document="x", mode="clause")
    guard = next(e["guard"] for e in _events(seen) if "guard" in e)
    assert guard["ran"] is True and guard["text"] == seen["reply"] and guard["withheld"] == []
    assert guard["supported"] == ["Section 420 PPC 1860"] and guard["counts"] == {
        "supported": 1, "withheld_sentences": 0, "not_checked": 0}
    frames = _frames(seen)
    # the guard precedes verification; [DONE] is last; the audit holds the checked text
    assert [i for i, f in enumerate(frames) if '"guard"' in f][0] < [i for i, f in enumerate(frames) if '"verification"' in f][0]
    assert frames[-1].strip() == "data: [DONE]"
    assert seen["recorded"][0]["state"]["answer"] == seen["reply"]


def _frames(seen):
    return [e if isinstance(e, str) else e.decode() for e in seen["events"]]


def test_a_failed_check_sends_no_text_and_nothing_runs_on_the_unchecked_draft(run, monkeypatch, caplog):
    """FAIL-CLOSED: the guard frame carries no text, there is no citation check
    and no answer in the audit store, and the stream still terminates."""
    from app.ai import visible_authority

    def boom(*a, **k):
        raise RuntimeError("boom: SECRET CLIENT FACT")
    monkeypatch.setattr(visible_authority, "authorities", boom)
    run.seen["reply"] = "That the SECRET CLIENT FACT is pleaded under Section 497 CrPC."
    seen = run(instruction="x", document="x", mode="clause")
    events = _events(seen)
    guard = next(e["guard"] for e in events if "guard" in e)
    assert guard["ran"] is False and guard["reason"] == "check_failed"
    assert guard["text"] == "" and guard["withheld"] == []
    assert not any("verification" in e for e in events), "a citation check ran on unchecked text"
    assert "verified" not in seen and "recorded" not in seen, "the unchecked draft reached verification / audit"
    assert _frames(seen)[-1].strip() == "data: [DONE]"
    # diagnostics say where, never what: no draft text, no exception message
    logged = caplog.text                      # messages AND any formatted traceback
    assert "check_failed" in logged and "RuntimeError" in logged
    assert "SECRET CLIENT FACT" not in logged


def test_an_unreadable_corpus_is_not_reported_as_a_checked_draft(run, monkeypatch):
    """The corpus index failed to load and every lookup fails: the check used to
    treat each authority as merely 'unverified', pass the hedged ones, and say
    ran:true. It now reports corpus_unavailable."""
    from app.ai import corpus_index
    from app.db import chroma

    def down(*a, **k):
        raise RuntimeError("ChromaDB client not initialized")
    monkeypatch.setattr(corpus_index, "get_index", down)
    monkeypatch.setattr(chroma, "get_chroma", down)
    run.seen["reply"] = "That pre-arrest bail may perhaps be sought under Section 438 CrPC."
    seen = run(instruction="x", document="x", mode="clause")
    guard = next(e["guard"] for e in _events(seen) if "guard" in e)
    assert guard == {"ran": False, "reason": "corpus_unavailable", "text": "", "withheld": [],
                     "jurisdiction": {"province": "unknown", "basis": "neutral"}}


def test_a_reply_citing_nothing_needs_no_corpus(run, monkeypatch):
    from app.ai import corpus_index

    def down(*a, **k):
        raise RuntimeError("ChromaDB client not initialized")
    monkeypatch.setattr(corpus_index, "get_index", down)
    seen = run(instruction="x", document="x", mode="clause")   # "NEW CLAUSE"
    guard = next(e["guard"] for e in _events(seen) if "guard" in e)
    assert guard["ran"] is True and guard["counts"]["supported"] == 0 and guard["text"] == "NEW CLAUSE"


def test_a_named_provision_is_fetched_and_put_first_in_the_law_context(run):
    run.seen["exact"] = [{"exact_provision": "Section 497 CrPC", "statute": "CrPC 1898",
                      "content": "497. When bail may be taken in case of non-bailable offence."}]
    seen = run(instruction="Add a ground under Section 497 CrPC", document="x", mode="clause")
    system = seen["messages"][0]["content"]
    assert "[EXACT TEXT] Section 497 CrPC" in system
    assert system.index("[EXACT TEXT]") < system.index("\n\nLAW"), "the exact text must come first"


def test_a_cited_provision_the_library_lacks_is_named_as_not_checked(run, corpus):
    run.seen["reply"] = "That the lease may perhaps be forfeited under Section 113 of the Transfer of Property Act."
    seen = run(instruction="x", document="x", mode="clause")
    guard = next(e["guard"] for e in _events(seen) if "guard" in e)
    assert guard["ran"] is True and guard["text"] == run.seen["reply"]
    assert guard["supported"] == [], "a provision the library does not hold was counted as supported"
    assert guard["not_checked"] == ["Section 113 Transfer of Property Act (not in our copy)"]


# ── jurisdiction (2026-10-14) ───────────────────────────────────────────────

def test_an_unchosen_jurisdiction_is_a_neutral_draft_on_federal_law_only(run, corpus):
    """Not 'every province mixed': federal law is retrieved, the model is told
    to leave a placeholder, and a provincial Act it names anyway is withheld."""
    run.seen["reply"] = ("That the tenancy is terminated.\n\n"
                         "That the tenant is liable to eviction under the Punjab Rented Premises Act, 2009.")
    seen = run(instruction="Draft an eviction notice", document="x", mode="clause")
    assert seen["province"] == "federal"
    assert "JURISDICTION NOT CHOSEN" in seen["messages"][0]["content"]
    guard = next(e["guard"] for e in _events(seen) if "guard" in e)
    assert guard["jurisdiction"] == {"province": "unknown", "basis": "neutral"}
    assert guard["text"] == "That the tenancy is terminated."
    assert any("no jurisdiction was chosen" in r for w in guard["withheld"] for r in w["reasons"])


@pytest.mark.parametrize("chosen,label", [("punjab", "Punjab"), ("Sindh", "Sindh")])
def test_a_chosen_province_narrows_retrieval_and_the_prompt(run, chosen, label):
    seen = run(instruction="Draft an eviction notice", document="x", province=chosen)
    assert seen["province"] == chosen.lower()
    system = seen["messages"][0]["content"]
    assert f"this document is for {label}" in system
    if chosen.lower() == "sindh":     # no Sindh statutes in the library: said, not implied
        assert "The library holds no Sindh provincial statutes" in system
    guard = next(e["guard"] for e in _events(seen) if "guard" in e)
    assert guard["jurisdiction"] == {"province": chosen.lower(), "basis": "selected"}


def test_another_provinces_act_is_withheld_from_a_sindh_draft(run, corpus):
    run.seen["reply"] = ("That notice is given under the Sindh Rented Premises Ordinance, 1979.\n\n"
                         "That the Punjab Rented Premises Act, 2009 also applies.")
    seen = run(instruction="x", document="x", mode="clause", province="sindh")
    guard = next(e["guard"] for e in _events(seen) if "guard" in e)
    assert "Sindh Rented Premises Ordinance" in guard["text"] and "Punjab" not in guard["text"]
    assert any("this draft is for Sindh" in r for w in guard["withheld"] for r in w["reasons"])


@pytest.mark.parametrize("bad", ["Punjab Province", "national", "ICT"])
def test_an_unknown_province_is_refused_not_read_as_neutral(run, bad):
    from app.core.exceptions import AppValidationError
    with pytest.raises(AppValidationError):
        run(instruction="x", document="x", province=bad)


@pytest.mark.parametrize("neutral", ["", "unknown", "  "])
def test_empty_or_unknown_is_the_neutral_draft(run, neutral):
    seen = run(instruction="x", document="x", province=neutral)
    assert seen["province"] == "federal"


def test_a_case_bound_draft_uses_the_case_province_not_the_request(run, monkeypatch):
    from app.services import case_service

    async def get_case(case_id, uid, role):
        return {"_id": case_id, "case_type": "civil", "province": "punjab", "status": "active",
                "title": "Rent dispute", "description": "tenant default"}
    monkeypatch.setattr(case_service, "get_case", get_case)
    monkeypatch.setattr(case_service, "assert_not_draft", lambda case, action: None)
    # the UI sends Sindh; the case says Punjab; "Punjab Province" would be refused if it were read
    seen = run(instruction="x", document="x", case_id="c1", province="Punjab Province")
    assert seen["province"] == "punjab"
    guard = next(e["guard"] for e in _events(seen) if "guard" in e)
    assert guard["jurisdiction"] == {"province": "punjab", "basis": "case"}



# ── fixes 1-4 through the route (2026-10-14) ──────────────────────────────────

def test_the_guard_frame_carries_honest_counts_and_withheld_reasons(run, corpus):
    run.seen["reply"] = ("That the Applicant is entitled to bail under Section 497 CrPC.\n\n"
                         "That pre-arrest bail may also be granted under Section 438 CrPC.")
    seen = run(instruction="Add a ground for bail", document="x", mode="clause", province="punjab")
    guard = next(e["guard"] for e in _events(seen) if "guard" in e)
    assert guard["counts"] == {"supported": 1, "withheld_sentences": 1, "not_checked": 0}
    assert guard["supported"] == ["Section 497 CrPC 1898"]
    assert seen["recorded"][0]["state"]["answer"] == guard["text"]


def test_a_neutral_eviction_draft_gets_the_topic_rider_and_a_clarification(run, corpus):
    run.seen["reply"] = "That you must vacate for non-payment of rent under Section 111 of the Transfer of Property Act."
    seen = run(instruction="Add a paragraph calling on the tenant to vacate for non-payment of rent", document="x",
               template="Notice Letter", mode="clause")
    assert "THIS ISSUE DEPENDS ON THE PROVINCE" in seen["messages"][0]["content"]
    guard = next(e["guard"] for e in _events(seen) if "guard" in e)
    assert guard["clarify"]["topic"] == "tenancy"
    assert "Transfer of Property" not in guard["text"]


def test_a_chosen_province_gets_no_neutral_rider(run, corpus):
    seen = run(instruction="Add a paragraph calling on the tenant to vacate for non-payment of rent", document="x",
               template="Notice Letter", mode="clause", province="punjab")
    assert "THIS ISSUE DEPENDS ON THE PROVINCE" not in seen["messages"][0]["content"]
    guard = next(e["guard"] for e in _events(seen) if "guard" in e)
    assert guard["clarify"] is None
