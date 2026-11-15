"""The isolated parsing pilot (scripts/pilot_legal_sources.py): its checks find
the three splitter defects seen in official Pakistan Code PDFs, and it refuses
to write inside a data store. Synthetic text only; no PDF, no Chroma."""
import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "pilot_legal_sources", Path(__file__).resolve().parents[1] / "scripts" / "pilot_legal_sources.py")
pilot = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(pilot)


def _row(label, text, kind="section"):
    return {"provision_label": label, "provision_kind": kind, "text": text,
            "provision_status": "not_recorded", "amendment_refs": [], "amending_instruments": []}


def test_an_inserted_section_behind_a_footnote_marker_is_reported_with_where_it_was_filed():
    rows = [_row("26", "26. Spoofing.— Whoever ... with both. 1[26A, Punishment for false and fake information.— Whoever"),
            _row("27", "27. Legal recognition of offences ...")]
    assert pilot._bracketed_insertions(rows) == [{"provision": "26-A", "filed_under": "26"}]
    # Once 26-A is its own provision, nothing is reported.
    rows.append(_row("26-A", "26A. Punishment for false and fake information ..."))
    assert pilot._bracketed_insertions(rows) == []
    # A schedule article is not a section.
    assert pilot._bracketed_insertions([_row("Schedule I", "2[13A. Plaint ...", kind="schedule")]) == []


def test_asterisk_omissions_and_buried_headings_are_reported():
    rows = [_row("2", "2. 4[* * * * * * *]"),
            _row("19-G", "19G. Executors ... after discovery of underpayment. 19H. Notice of applications for probate"),
            _row("20", "20. Rules as to costs of processes ...")]
    rep = pilot.checks(rows, body_found=True)
    assert rep["asterisk_omitted_recorded_as_sections"] == ["2"]
    assert rep["buried_lettered_headings"] == [{"inside": "19-G", "heading": "19-H"}]


@pytest.mark.parametrize("path", ["backend/chroma_data/pilot", "x/chroma_data_backup_2026/out", "y/chroma_db"])
def test_the_pilot_refuses_to_write_inside_a_store(path, tmp_path):
    with pytest.raises(SystemExit):
        pilot._refuse_store_path(tmp_path / path)
    pilot._refuse_store_path(tmp_path / "scratch" / "legal_pilot")      # a scratch dir is fine
