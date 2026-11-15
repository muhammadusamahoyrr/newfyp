"""Both lawyer AI surfaces must send the case's DATABASE id, and only that.

A lawyer asks the AI about a case on the AI Legal page (with a case selector).
It calls `aiResearch`. (The case workspace's AI tab was a second surface until
commit 1ba40e7 deleted it as never rendered -- 2026-10-17 contract update: the
AI Legal page is the ONE research surface, and any new `aiResearch` call site
must be declared below so it cannot bypass this contract.) Surfaces used to
hand the model case FACTS composed in the browser — a `caseContext` object of title, description and parties, dropped
into `history` as free text. That meant the client, not the server, decided
what the model believed about a matter, with nothing checking the sender was
assigned to it.

The replacement sends `case_id` and nothing else. Two things can silently
break that and neither shows up as a test failure elsewhere:

  * sending `c.id` — the DISPLAY case number ("CIV-2026-001") — instead of
    `c._id`. The server looks cases up by `_id`, so this now resolves to
    "case not available" for every request rather than working by accident;
  * re-adding any case-facts payload, which restores the original hole.

There is no JS test runner in this repo, so these assert on the call sites
themselves. That is weaker than executing the component, but it does catch
the two regressions that actually matter, and it fails loudly if either call
site is edited back.
"""
import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"

# Every component that calls `aiResearch` -- enforced by
# test_every_research_call_site_is_a_declared_surface below.
SURFACES = {
    "AI Legal page": FRONTEND / "components" / "lawyer" / "AILegalPage.jsx",
}
# The case workspace no longer has an AI tab (commit 1ba40e7). It must still
# never compose case facts for a model; if a research entry returns there, it
# must be added to SURFACES (the discovery test fails until it is).
CASE_WORKSPACE = FRONTEND / "components" / "lawyer" / "CasesPage.jsx"

# The `case_id:` line inside an aiResearch(...) options object.
_CASE_ID_ARG = re.compile(r"case_id:\s*([^,\n]+)")


def _source(path: Path) -> str:
    if not path.exists():
        pytest.skip(f"frontend source not present: {path}")
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("name,path", sorted(SURFACES.items()))
def test_the_surface_sends_a_case_id_to_ai_research(name, path):
    src = _source(path)
    assert "aiResearch(" in src, f"{name} no longer calls the research API"
    assert _CASE_ID_ARG.search(src), f"{name} calls aiResearch without a case_id"


@pytest.mark.parametrize("name,path", sorted(SURFACES.items()))
def test_the_surface_sends_the_database_id_not_the_display_number(name, path):
    """`_id` is the key the server queries; `id` is the label on the screen."""
    src = _source(path)
    for match in _CASE_ID_ARG.finditer(src):
        expr = match.group(1).strip()
        assert "._id" in expr, (
            f"{name} sends {expr!r} as case_id; the server resolves cases by _id, "
            f"so a display case number silently becomes 'case not available'")


@pytest.mark.parametrize("name,path", sorted(SURFACES.items()))
def test_the_surface_sends_no_case_facts(name, path):
    """The browser must not compose what the model believes about a case."""
    src = _source(path)
    assert "caseContext" not in src, (
        f"{name} builds a case-facts payload again — case facts must come from "
        f"the authorised server-side record, not the client")


def test_the_api_helper_forwards_case_id_and_nothing_else():
    api = _source(FRONTEND / "lib" / "api.js")
    body = re.search(
        r"export async function aiResearch\(.*?\n\}", api, re.S)
    assert body, "aiResearch is no longer defined in lib/api.js"
    text = body.group(0)
    assert "case_id" in text, "the helper drops case_id before it reaches the server"
    for leak in ("case_context", "caseContext", "description", "client_name"):
        assert leak not in text, f"the helper sends {leak} to the server"


def test_every_research_call_site_is_a_declared_surface():
    """A new place that calls aiResearch (e.g. a restored case-workspace tab)
    is held to the same contract: it must be listed in SURFACES."""
    if not FRONTEND.exists():
        pytest.skip("frontend source not present")
    callers = {p.resolve() for p in FRONTEND.rglob("*.jsx")
               if "aiResearch(" in p.read_text(encoding="utf-8", errors="replace")}
    callers |= {p.resolve() for p in (FRONTEND / "components").rglob("*.js")
                if "aiResearch(" in p.read_text(encoding="utf-8", errors="replace")}
    declared = {p.resolve() for p in SURFACES.values()}
    undeclared = sorted(str(p) for p in callers - declared)
    assert not undeclared, f"aiResearch is called from undeclared surfaces: {undeclared}"
    assert declared <= callers, "a declared research surface no longer calls aiResearch"


def test_the_case_workspace_sends_no_case_facts():
    assert "caseContext" not in _source(CASE_WORKSPACE), (
        "the case workspace builds a case-facts payload -- case facts must come from the "
        "authorised server-side record, not the client")

