"""No silent fallback from a required identity index to the base one (2026-10-16).

The lawyer drafter and lawyer research read the verified identity indexes
(criminal `__sec_v2`, civil `__ident_v2`). A missing, unreadable or unverified
one used to be replaced by the BASE collection without a word, so the output
looked identity-checked when it was not. Now the drafter refuses before any
retrieval or model call, and research reports a retrieval error.

Everything here runs against a FAKE Chroma client (no store is opened; the
conftest isolation also refuses the live path). The visible outcome is tested
where one exists: the draft-assist SSE events the lawyer's panel reads, and the
retrieval result the research answer is built from.
"""
from __future__ import annotations

import asyncio
import json

import pytest

import app.api.v1.routes.ai as ai_routes
from app.ai import corpus_index, cpc_provisions, exact_provision, index_health
from app.ai.citation_verification import ParsedCitation  # noqa: F401  (import check only)
from app.ai.pipelines import retriever

LAWYER = {"_id": "lawyer-1", "role": "lawyer"}
SEC, IDENT = "criminal_collection__sec_v2", "civil_collection__ident_v2"


class _NotFound(Exception):
    pass


class FakeCol:
    def __init__(self, name, n=0, metadata=None, fail=None):
        self.name, self.n, self.metadata, self.fail = name, n, metadata or {}, fail
        self.where_calls = []

    def count(self):
        if self.fail == "count":
            raise RuntimeError("database disk image is malformed")
        return self.n

    def get(self, **kw):
        if self.fail == "get":
            raise RuntimeError("hnsw segment unreadable")
        if kw.get("where"):
            self.where_calls.append(kw["where"])
        return {"ids": [], "metadatas": [], "documents": []}


class FakeClient:
    def __init__(self, cols):
        self.cols = {c.name: c for c in cols}

    def get_collection(self, name):
        if name not in self.cols:
            raise _NotFound(f"Collection [{name}] does not exist")
        return self.cols[name]


def healthy(**override):
    cols = {
        SEC: FakeCol(SEC, 3305, {"sec_schema": "sec-v2", "split_version": "section-split-v2"}),
        IDENT: FakeCol(IDENT, 4648, {"ident_version": "ident-v2",
                                     "build_run_id": "646c85cde01548758dc06f97f8938b86"}),
    }
    for base in ("criminal_collection", "civil_collection", "family_collection", "constitutional_collection"):
        cols[base] = FakeCol(base, 10)
    for name, col in override.items():
        if col is None:
            cols.pop(name)
        else:
            cols[name] = col
    return FakeClient(cols.values())


@pytest.fixture
def store(monkeypatch):
    """Install a fake client everywhere get_chroma is read; clear every cache."""
    def install(client):
        monkeypatch.setattr("app.db.chroma.get_chroma", lambda: client)
        monkeypatch.setattr(retriever, "get_chroma", lambda: client)
        index_health.clear_cache()
        corpus_index.set_drafter_index(None)
        cpc_provisions.set_catalogue(None)
        return client
    yield install
    index_health.clear_cache()
    corpus_index.set_drafter_index(None)
    cpc_provisions.set_catalogue(None)


# ── index_health: the four states ────────────────────────────────────────────

def test_a_verified_build_is_ok(store):
    store(healthy())
    assert index_health.check(IDENT).ok and index_health.check(SEC).ok


@pytest.mark.parametrize("override, problem", [
    ({IDENT: None}, "missing"),
    ({IDENT: FakeCol(IDENT, 4648, {"ident_version": "ident-v2",
                                   "build_run_id": "646c85cde01548758dc06f97f8938b86"}, fail="count")}, "unreadable"),
    ({IDENT: FakeCol(IDENT, 4648, {"ident_version": "ident-v2",
                                   "build_run_id": "646c85cde01548758dc06f97f8938b86"}, fail="get")}, "unreadable"),
    ({IDENT: FakeCol(IDENT, 4648, {"ident_version": "ident-v1"})}, "unverified"),
    ({IDENT: FakeCol(IDENT, 4000, {"ident_version": "ident-v2",
                                   "build_run_id": "646c85cde01548758dc06f97f8938b86"})}, "unverified"),
])
def test_every_unhealthy_state_is_named(store, override, problem):
    store(healthy(**override))
    h = index_health.check(IDENT)
    assert not h.ok and h.status == problem
    with pytest.raises(index_health.IdentityIndexUnavailable) as exc:
        index_health.require(IDENT)
    assert exc.value.as_dict() == {"status": "identity_index_unavailable", "collection": IDENT, "problem": problem}
    assert isinstance(exc.value, exact_provision.CorpusUnavailable)   # every fail-closed path handles it


# ── the drafter: the panel's visible outcome ─────────────────────────────────

@pytest.fixture
def draft(monkeypatch):
    seen = {"model_calls": 0, "retrievals": 0, "recorded": 0}

    def law(*a, **k):
        seen["retrievals"] += 1
        return "LAW"
    monkeypatch.setattr(ai_routes, "_retrieve_law_context", law)
    monkeypatch.setattr(ai_routes, "_exact_provisions_for", lambda text: [])

    async def no_case_law(q):
        return ""
    monkeypatch.setattr(ai_routes, "_retrieve_case_law_context", no_case_law)

    async def verification(payload):
        return {"ran": False}
    monkeypatch.setattr(ai_routes, "_verification_record", verification)

    async def record(**kw):
        seen["recorded"] += 1
    monkeypatch.setattr(ai_routes.provenance_service, "record_answer", record)

    class _Chunk:
        def __init__(self, content):
            self.content = content

    class _LLM:
        async def astream(self, messages):
            seen["model_calls"] += 1
            yield _Chunk("That the petitioner relies on Order VII Rule 11 CPC.")
    monkeypatch.setattr("app.ai.llm.get_llm", lambda **k: _LLM())
    # The real legal check needs a real corpus; the healthy case asserts the
    # route reached it, not what it decided.
    from app.ai import draft_guard
    monkeypatch.setattr(draft_guard, "check", lambda drafted, *a, **k: {
        "ran": True, "text": drafted, "withheld": [], "supported": [], "not_checked": []})

    def go(**body):
        async def main():
            resp = await ai_routes.ai_draft_stream(ai_routes.DraftRequest(**body), current_user=LAWYER)
            return [p if isinstance(p, str) else p.decode() for p in [x async for x in resp.body_iterator]]
        seen["events"] = asyncio.run(main())
        seen["parsed"] = [json.loads(e[6:]) for e in seen["events"] if e.startswith("data: {")]
        return seen
    return go


BODY = dict(instruction="Add a ground for rejection of the plaint", document="IN THE COURT ...",
            template="Civil Plaint", case_type="civil", mode="clause")


@pytest.mark.parametrize("override, collection, problem", [
    ({IDENT: None}, IDENT, "missing"),
    ({SEC: None}, SEC, "missing"),
    ({IDENT: FakeCol(IDENT, 4648, {"ident_version": "ident-v2",
                                   "build_run_id": "646c85cde01548758dc06f97f8938b86"}, fail="count")}, IDENT, "unreadable"),
    ({SEC: FakeCol(SEC, 3000, {"sec_schema": "sec-v2", "split_version": "section-split-v2"})}, SEC, "unverified"),
])
def test_the_drafter_refuses_and_says_which_index(store, draft, override, collection, problem):
    store(healthy(**override))
    s = draft(**BODY)
    guards = [e["guard"] for e in s["parsed"] if "guard" in e]
    assert len(guards) == 1
    g = guards[0]
    assert g["ran"] is False and g["text"] == ""
    assert g["reason"] == "corpus_unavailable"            # the panel's existing message for it
    assert g["index"] == {"status": "identity_index_unavailable", "collection": collection, "problem": problem}
    # Nothing ran on unverified law: no retrieval, no model, no content, no audit "answer".
    assert s["retrievals"] == 0 and s["model_calls"] == 0 and s["recorded"] == 0
    assert not any("content" in e for e in s["parsed"])
    assert s["events"][-1].strip() == "data: [DONE]"


def test_a_healthy_store_drafts_normally(store, draft):
    store(healthy())
    s = draft(**BODY)
    assert s["retrievals"] == 1 and s["model_calls"] == 1
    assert any("content" in e for e in s["parsed"])
    g = [e["guard"] for e in s["parsed"] if "guard" in e][0]
    assert g["ran"] is True and "index" not in g


# ── research: the retrieval result the answer is built from ─────────────────

def test_research_retrieval_reports_an_error_instead_of_reading_base(store):
    store(healthy(**{IDENT: None}))
    from app.ai.nodes.retrieval_node import retrieval_node
    q = "What is the limitation for a suit for possession?"
    state = {"query": q, "case_type": "civil", "province": "punjab", "retrieval_attempts": 0,
             "expansion_for": q, "expanded_query": q, "surface": "research",
             "retrieval_policy": {"index_variant": "research_ident", "case_law": False}}
    out = asyncio.run(retrieval_node(state))
    assert out["retrieval_error"] is True
    assert out["retrieved_chunks"] == [] and out["reranked_chunks"] == []


def test_the_research_retriever_never_substitutes_base(store):
    store(healthy(**{IDENT: None}))
    with pytest.raises(index_health.IdentityIndexUnavailable):
        retriever._index_collection("civil_collection", "research_ident")
    store(healthy())
    assert retriever._index_collection("civil_collection", "research_ident") == IDENT
    assert retriever._index_collection("criminal_collection", "research_ident") == SEC
    assert retriever._index_collection("family_collection", "research_ident") == "family_collection"


def test_client_and_intake_retrieval_policy_is_unchanged(store, monkeypatch):
    """Base by policy, and a missing NON-identity variant still falls back as before."""
    store(healthy(**{IDENT: None, SEC: None}))
    from app.core.config import settings
    monkeypatch.setattr(settings, "retrieval_index_variant", "base")
    assert retriever._index_collection("civil_collection", None) == "civil_collection"
    assert retriever._index_collection("civil_collection", "base") == "civil_collection"
    assert retriever._index_collection("civil_collection", "contextual") == "civil_collection"


# ── exact provisions ─────────────────────────────────────────────────────────

def _cit(text):
    from app.ai import tool_contract
    return tool_contract.provision_refs(text)


def test_research_exact_lookup_never_reads_base_civil(store):
    client = store(healthy(**{IDENT: None}))
    cits = _cit("Section 9 CPC")
    with pytest.raises(index_health.IdentityIndexUnavailable):
        exact_provision.fetch(cits, research=True, strict=True)
    got = exact_provision.fetch(cits, research=True)            # non-strict: "not found", never base text
    assert all(v == [] for v in got.values())
    assert client.cols["civil_collection"].where_calls == []


def test_client_exact_lookup_keeps_its_policy(store):
    client = store(healthy(**{SEC: None}))
    names = exact_provision._collections(research=False)
    assert names[0] == "criminal_collection"                     # unchanged: base where sec_v2 is absent
    assert "civil_collection" in names
    assert client  # no exception


def test_the_drafter_index_and_cpc_catalogue_refuse_too(store):
    store(healthy(**{IDENT: None}))
    with pytest.raises(index_health.IdentityIndexUnavailable):
        corpus_index.get_drafter_index()
    with pytest.raises(index_health.IdentityIndexUnavailable):
        cpc_provisions.catalogue()


# ── mutation: a return of silent fallback must be caught ────────────────────

def _fallback_require(name, client=None):
    return name.split("__")[0]          # the old behaviour: base collection, no error


_REGRESSIONS = {
    "drafter_stream": lambda store, draft: test_the_drafter_refuses_and_says_which_index(
        store, draft, {IDENT: None}, IDENT, "missing"),
    "research_retriever": lambda store, draft: test_the_research_retriever_never_substitutes_base(store),
    "exact_lookup": lambda store, draft: test_research_exact_lookup_never_reads_base_civil(store),
    "drafter_index_and_catalogue": lambda store, draft: test_the_drafter_index_and_cpc_catalogue_refuse_too(store),
}


@pytest.mark.parametrize("name", sorted(_REGRESSIONS))
def test_the_regression_tests_fail_if_silent_fallback_returns(store, draft, monkeypatch, name):
    """Mutation: require() falls back to the base collection silently (the old
    behaviour). Each regression test above must then FAIL."""
    monkeypatch.setattr(index_health, "require", _fallback_require)
    monkeypatch.setattr(index_health, "require_all",
                        lambda names, client=None: [_fallback_require(n) for n in names])
    monkeypatch.setattr(corpus_index, "build_index", lambda names: names)
    with pytest.raises((AssertionError, pytest.fail.Exception)):
        _REGRESSIONS[name](store, draft)


# ── 2026-10-19: the drafter index builds on a healthy store ─────────────────

def test_the_drafter_index_builds_when_identity_builds_are_verified(store, monkeypatch):
    """family / constitutional have no identity build; demanding a recorded
    one made get_drafter_index refuse on EVERY store, so the legal check
    never had its index."""
    store(healthy())
    built = []
    monkeypatch.setattr(corpus_index, "build_index", lambda names: built.append(names) or "INDEX")
    assert corpus_index.get_drafter_index() == "INDEX"
    assert set(built[0]) == {SEC, IDENT, "family_collection", "constitutional_collection"}


def test_the_drafter_index_still_refuses_a_missing_base_collection(store):
    store(healthy(**{"family_collection": None}))
    with pytest.raises(index_health.IdentityIndexUnavailable) as e:
        corpus_index.get_drafter_index()
    assert e.value.health.collection == "family_collection" and e.value.health.status == "missing"
