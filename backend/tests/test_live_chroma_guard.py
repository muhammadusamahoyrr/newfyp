"""The test run can never touch the live Chroma store (tests/conftest.py).

Every probe first proves the guard on a DECOY `chroma_data` folder inside
tmp_path. Only then does it aim at the real backend/chroma_data, and only with
probes that could create or change nothing even if the guard were missing:
read-only opens of names that do not exist.
"""
import os
import shutil
import sqlite3
import sys

import pytest

conftest = next(m for m in sys.modules.values() if hasattr(m, "LiveChromaAccessBlocked"))
Blocked = conftest.LiveChromaAccessBlocked

pytestmark = pytest.mark.skipif(conftest.ALLOW_LIVE_CHROMA, reason="guard disabled by AAI_ALLOW_LIVE_CHROMA=1")


@pytest.fixture
def decoy(tmp_path):
    return tmp_path / "chroma_data"


def test_the_app_store_points_at_a_temporary_directory_not_the_live_one():
    import app.db.chroma as chroma
    assert chroma._CHROMA_PATH == conftest.TEST_CHROMA_PATH
    assert not conftest._touches_live_chroma(chroma._CHROMA_PATH)
    assert conftest._touches_live_chroma(conftest.LIVE_CHROMA_PATH)


def test_python_file_access_under_a_chroma_data_path_is_refused_before_it_happens(decoy):
    with pytest.raises(Blocked):
        os.mkdir(decoy)
    assert not decoy.exists()
    with pytest.raises(Blocked):
        open(decoy / "probe.txt", "w")
    with pytest.raises(Blocked):
        sqlite3.connect(str(decoy / "chroma.sqlite3"))
    with pytest.raises(Blocked):
        sqlite3.connect(f"file:{(decoy / 'chroma.sqlite3').as_posix()}?mode=ro", uri=True)
    with pytest.raises(Blocked):
        os.listdir(decoy)
    src = decoy.parent / "src"
    src.mkdir()
    with pytest.raises(Blocked):
        shutil.copytree(src, decoy)
    with pytest.raises(Blocked):
        os.rename(src, decoy)              # caught on the DESTINATION
    assert not decoy.exists()


def test_every_chromadb_client_on_a_chroma_data_path_is_refused(decoy, monkeypatch):
    import chromadb
    import app.db.chroma as chroma
    with pytest.raises(Blocked):
        chromadb.PersistentClient(path=str(decoy))
    monkeypatch.setattr(chroma, "_CHROMA_PATH", decoy)
    with pytest.raises(Blocked):
        chroma.connect_chroma()
    assert not decoy.exists()


def test_the_real_live_path_is_refused(decoy):
    # Prove the guard on the decoy first; without it, nothing below runs.
    with pytest.raises(Blocked):
        open(decoy / "x", "rb")
    live = conftest.LIVE_CHROMA_PATH
    missing = live / "__aai_guard_probe_does_not_exist__"
    with pytest.raises(Blocked):           # unguarded this would be FileNotFoundError
        open(missing, "rb")
    with pytest.raises(Blocked):
        sqlite3.connect(f"file:{missing.as_posix()}.sqlite3?mode=ro", uri=True)
    with pytest.raises(Blocked):
        os.listdir(missing)


def test_the_law_graph_file_inside_the_live_store_is_refused(decoy):
    with pytest.raises(Blocked):
        open(decoy / "x", "rb")
    from app.ai.pipelines import law_graph
    with pytest.raises(Blocked):
        open(law_graph.GRAPH_PATH, "rb")


def test_a_normal_connect_uses_the_temporary_store():
    import app.db.chroma as chroma
    assert chroma._CHROMA_PATH == conftest.TEST_CHROMA_PATH      # never connect unless redirected
    chroma.connect_chroma()
    try:
        assert (conftest.TEST_CHROMA_PATH / "chroma.sqlite3").exists()
    finally:
        chroma.close_chroma()
