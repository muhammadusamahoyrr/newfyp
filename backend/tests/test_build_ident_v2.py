"""scripts/build_ident_v2.py write safety (2026-10-15), on an in-memory fake Chroma client -- no real collection is read
or written. The build may never overwrite an existing ident_v2, may remove only the collection THIS run created
(carrying this run's id), and applies only a diff whose sha256 matches its lock."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_ident_v2 as B  # noqa: E402


class _Col:
    def __init__(self, name, metadata=None):
        self.name, self.metadata, self.rows = name, metadata or {}, {}
        self.fail_add = False

    def add(self, ids, documents, embeddings, metadatas):
        if self.fail_add:
            raise RuntimeError("disk full")
        for i, d, e, m in zip(ids, documents, embeddings, metadatas):
            self.rows[i] = (d, dict(m), list(e))

    def count(self):
        return len(self.rows)

    def get(self, include, limit, offset):
        ids = sorted(self.rows)[offset:offset + limit]
        return {"ids": ids, "documents": [self.rows[i][0] for i in ids], "metadatas": [self.rows[i][1] for i in ids],
                "embeddings": [self.rows[i][2] for i in ids]}


class _Client:
    def __init__(self):
        self.cols, self.deleted = {}, []

    def list_collections(self):
        return list(self.cols.values())

    def get_collection(self, name):
        return self.cols[name]

    def create_collection(self, name, metadata=None):
        assert name not in self.cols, "overwrote an existing collection"
        self.cols[name] = _QCol(name, metadata)      # defined below; has an exact query
        return self.cols[name]

    def delete_collection(self, name):
        self.deleted.append(name)
        del self.cols[name]


V1 = {"c1": ("1. Text.", {"provision_label": "Order I Rule 1"}, [0.1, 0.2]),
      "c2": ("more text", {"provision_label": "Order I (rule not shown)"}, [0.3, 0.4])}
PLAN = {"c2": {"provision_label": "Order I Rule 1", "ident_version": "ident-v2"}}


def _client_with_source():
    c = _Client()
    src = c.create_collection(B.SOURCE, {"k": "v"})
    for i, (d, m, e) in V1.items():
        src.rows[i] = (d, dict(m), list(e))
    return c, src


def test_an_existing_ident_v2_is_never_overwritten_or_removed():
    c, src = _client_with_source()
    theirs = c.create_collection(B.TARGET, {"build_run_id": "someone-else"})
    theirs.rows["x"] = ("keep", {}, [0.0])
    with pytest.raises(B.Refused):
        B.build_and_verify(c, src, V1, PLAN, "run-1")
    assert c.deleted == [] and c.cols[B.TARGET] is theirs and theirs.rows["x"][0] == "keep"


def test_a_good_build_writes_only_the_planned_metadata():
    c, src = _client_with_source()
    post, facts = B.build_and_verify(c, src, V1, PLAN, "run-1", floor=0)       # 2 vectors: floor tested apart
    assert post == [] and facts["chunks_written"] == 2 and facts["metadata_changed"] == 1
    assert facts["embeddings"]["byte_identical"] == 2 and facts["embeddings"]["exact_topk_identical"] == 2
    dst = c.cols[B.TARGET]
    assert dst.metadata["build_run_id"] == "run-1"
    assert dst.rows["c1"] == ("1. Text.", V1["c1"][1], V1["c1"][2]) and dst.rows["c2"][1] == PLAN["c2"]
    assert src.rows["c1"][1] == {"provision_label": "Order I Rule 1"}, "the source changed"


def test_a_failed_write_removes_only_this_runs_own_collection():
    c, src = _client_with_source()
    real_create = c.create_collection

    def create(name, metadata=None):
        col = real_create(name, metadata)
        col.fail_add = True
        return col
    c.create_collection = create
    with pytest.raises(RuntimeError):
        B.build_and_verify(c, src, V1, PLAN, "run-1")
    assert c.deleted == [B.TARGET] and B.TARGET not in c.cols and B.SOURCE in c.cols


def test_remove_own_never_deletes_a_collection_another_run_made():
    c, _ = _client_with_source()
    c.create_collection(B.TARGET, {"build_run_id": "other-run"})
    assert B.remove_own(c, "run-1", created_here=True) is False
    assert B.remove_own(c, "other-run", created_here=False) is False, "not created in this run"
    assert c.deleted == []
    assert B.remove_own(c, "other-run", created_here=True) is True        # only its own creator, in the same run


def test_the_source_is_never_a_deletion_target():
    c, _ = _client_with_source()
    c.cols[B.SOURCE].metadata["build_run_id"] = "run-1"
    assert B.remove_own(c, "run-1", created_here=True) is False and c.deleted == []


def _frozen(tmp_path, body: dict, tamper: bool = False):
    p = tmp_path / "ident_v2_metadata_diff.vT.json"
    raw = (json.dumps(body, indent=1, sort_keys=True) + "\n").encode()
    p.write_bytes(raw)
    (tmp_path / "ident_v2_metadata_diff.vT.lock.json").write_text(json.dumps(
        {"sha256": hashlib.sha256(raw).hexdigest(), "counts": body["counts"]}))
    if tamper:
        p.write_bytes(raw.replace(b"Order I Rule 1", b"Order I Rule 2"))
    return p


_BODY = {"counts": {"A": 1, "B": 0, "REVIEW": 0, "changes": 1},
         "changes_and_reviews": [{"chunk_id": "c2", "class": "A: x", "current_label": "Order I (rule not shown)",
                                  "new_label": "Order I Rule 1", "also_rules": [],
                                  "official_rules_spanned": ["Order I Rule 1"]}]}


def test_only_the_frozen_diff_is_accepted(tmp_path):
    diff, lock = B.load_frozen_diff(_frozen(tmp_path, _BODY))
    assert lock["counts"] == _BODY["counts"] and diff["changes_and_reviews"][0]["chunk_id"] == "c2"
    with pytest.raises(B.Refused, match="sha256"):
        B.load_frozen_diff(_frozen(tmp_path, _BODY, tamper=True))
    nolock = tmp_path / "other.json"
    nolock.write_text("{}")
    with pytest.raises(B.Refused, match="no lock"):
        B.load_frozen_diff(nolock)


def test_counts_that_disagree_with_the_lock_are_refused(tmp_path):
    body = json.loads(json.dumps(_BODY))
    body["counts"] = {"A": 2, "B": 0, "REVIEW": 0, "changes": 2}
    with pytest.raises(B.Refused, match="counts"):
        B.load_frozen_diff(_frozen(tmp_path, body))


def test_the_shipped_v3_diff_is_frozen_with_233_changes():
    diff, lock = B.load_frozen_diff(B.DIFF)
    assert lock["counts"] == {"A": 213, "B": 20, "REVIEW": 16, "changes": 233}
    moved = {r["chunk_id"] for r in diff["changes_and_reviews"] if r["class"].startswith("REVIEW: the official text puts")}
    assert moved == {"statutes_cpc_1908_1185", "statutes_cpc_1908_1260", "statutes_cpc_1908_1626", "statutes_cpc_1908_1629"}
    targets = {r["chunk_id"]: r for r in diff["changes_and_reviews"]}
    assert targets["statutes_cpc_1908_0998"]["new_label"] == "Order I Rule 10"
    assert targets["statutes_cpc_1908_1153"]["also_rules"] == ["Order IX Rule 13"]
    assert targets["statutes_cpc_1908_1154"]["new_label"] == "Order IX Rule 13"


# ── measured embedding tolerance (2026-10-15) ───────────────────────────────

class _QCol(_Col):
    """A fake collection with an EXACT query (stands in for HNSW)."""

    def query(self, query_embeddings, n_results, include):
        import numpy as np
        ids = sorted(self.rows)
        embs = np.asarray([self.rows[i][2] for i in ids], dtype=np.float32)
        out = []
        for q in query_embeddings:
            order = np.argsort(-(embs @ np.asarray(q, dtype=np.float32)), kind="stable")[:n_results]
            out.append([ids[j] for j in order])
        return {"ids": out}


def _unit_rows(n=40, seed=0):
    import numpy as np
    rng = np.random.default_rng(seed)
    e = rng.normal(size=(n, 16)).astype(np.float32)
    e /= np.linalg.norm(e, axis=1, keepdims=True)
    return {f"c{i:03d}": (f"doc {i}", {"k": i}, [float(x) for x in e[i]]) for i in range(n)}


def _cols(v1, v2):
    src, dst = _QCol("src"), _QCol("dst")
    src.rows = {i: (d, m, list(e)) for i, (d, m, e) in v1.items()}
    dst.rows = {i: (d, m, list(e)) for i, (d, m, e) in v2.items()}
    return src, dst


def _nudge(v, ids, ulps):
    import numpy as np
    out = dict(v)
    for i in ids:
        d, m, e = out[i]
        a = np.asarray(e, dtype=np.float32)
        for _ in range(ulps):
            a = np.nextafter(a, np.float32(2.0), dtype=np.float32)
        out[i] = (d, m, [float(x) for x in a])
    return out


def test_one_ulp_rounding_passes_the_measured_tolerance():
    v1 = _unit_rows()
    v2 = _nudge(v1, ["c001", "c007"], 1)
    problems, facts = B.embedding_tolerance(*_cols(v1, v2), v1, v2, floor=0)
    assert problems == [], problems
    assert facts["within_1_ulp_not_identical"] == 2 and facts["exact_topk_identical"] == 40


def test_more_than_one_ulp_fails():
    v1 = _unit_rows()
    v2 = _nudge(v1, ["c003"], 3)
    problems, facts = B.embedding_tolerance(*_cols(v1, v2), v1, v2, floor=0)
    assert any("more than 1 ULP" in p for p in problems) and facts["over_tolerance"] == 1


def test_a_changed_neighbourhood_fails_even_within_the_vector_check():
    v1 = _unit_rows()
    v2 = dict(v1)
    d, m, e = v1["c005"]
    v2["c005"] = (d, m, list(v1["c006"][2]))          # a real change: c005 now sits where c006 is
    problems, _ = B.embedding_tolerance(*_cols(v1, v2), v1, v2, floor=0)
    assert any("neighbours changed" in p for p in problems), problems


def test_build_on_the_live_store_is_refused_without_explicit_approval(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["build_ident_v2.py", "--build"])
    assert B.main() == 2
    assert "needs --live-approved" in capsys.readouterr().out


# ── pre-registered gate (2026-10-15) ────────────────────────────────────────

def test_the_index_floor_is_the_pre_registered_number_not_a_comparison_with_the_source():
    v1 = _unit_rows()
    src, dst = _cols(v1, v1)
    ok, facts = B.embedding_tolerance(src, dst, v1, v1, floor=40)
    assert ok == [] and facts["hnsw_floor"] == 40
    bad, _ = B.embedding_tolerance(src, dst, v1, v1, floor=41)
    assert any("below the pre-registered floor 41" in p for p in bad)
    assert B.HNSW_FLOOR == 4569


def test_the_build_refuses_when_the_gate_file_is_not_the_locked_one(tmp_path):
    gate = tmp_path / "PREREGISTERED_GATE.md"
    gate.write_text("gate v1")
    (tmp_path / "PREREGISTERED_GATE.lock.json").write_text(
        json.dumps({"sha256": hashlib.sha256(b"gate v1").hexdigest()}))
    assert B.check_gate_lock(gate)["sha256"]
    gate.write_text("gate v1 -- floor lowered")
    with pytest.raises(B.Refused, match="changed"):
        B.check_gate_lock(gate)


def test_the_shipped_gate_is_locked_and_matches():
    lock = B.check_gate_lock()
    assert lock["sha256"].startswith("04806e18")


def test_build_embedding_check_uses_the_pre_registered_floor_by_default():
    v1 = _unit_rows()
    problems, facts = B.embedding_tolerance(*_cols(v1, v1), v1, v1)       # 40 vectors can never reach 4,569
    assert facts["hnsw_floor"] == 4569 and any("pre-registered floor 4569" in p for p in problems)
