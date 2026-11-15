"""The client's template preview shows the template's real wording.

Before 2026-10-19 the preview and "Edit wording first" drew an outline (title
and field names), so every template looked empty although its builder holds
the full text. These pin the text endpoint and two builder bugs found on the way.
"""
from __future__ import annotations

import re

import pytest
from fastapi import HTTPException

from app.api.v1.routes.documents import template_text
from app.services import template_registry as reg
from app.services.pdf_generator import _as_items, template_html

pytestmark = pytest.mark.asyncio

USER = {"_id": "u1", "role": "client"}


def _tokens(html: str) -> set[str]:
    return set(re.findall(r"\[\[([A-Z_]+)\]\]", html))


async def test_fir_preview_is_the_real_application_with_every_detail_marked():
    out = await template_text("fir_application", current_user=USER)
    html = out["text_html"]
    assert "Station House Officer" in html
    assert "section 154" in html
    # Every field the text prints is a named blank, including those the PDF
    # would otherwise print as "______", and the complainant's identity.
    assert _tokens(html) == {k.upper() for k in reg.fields_for("fir_application")}


async def test_a_key_that_only_switches_wording_is_not_marked():
    # `pre_arrest` picks the pre- or post-arrest wording and never prints.
    # Marking it would show the other branch without saying so.
    html = template_html("bail_application", {}, mark_all=True)
    assert "PRE_ARREST" not in _tokens(html)
    assert "POST-ARREST BAIL" in html


async def test_pdf_only_templates_say_so_instead_of_inventing_text():
    for t in ("inheritance_settlement", "labour_demand", "urdu_pleading", "wasiyyat_nama"):
        out = await template_text(t, current_user=USER)
        assert out["text_html"] is None, t


async def test_unknown_system_and_freeform_types_are_not_found():
    for t in ("no_such_template", "payment_receipt", "lawyer_draft", "edited_document"):
        with pytest.raises(HTTPException) as err:
            await template_text(t, current_user=USER)
        assert err.value.status_code == 404, t


async def test_every_listed_prose_template_has_text():
    for item in reg.listing():
        t = item["template_type"]
        out = await template_text(t, current_user=USER)
        if reg.text_editable(t):
            assert out["text_html"] and _tokens(out["text_html"]), t


# ── numbered-list fields typed as text ────────────────────────────────────────

async def test_list_fields_typed_as_text_are_one_item_per_line():
    # Iterating a string numbered every CHARACTER: "1. A", "2. b", "3. c".
    assert _as_items("1. Innocent\n2) No record\n\n- Will join") == [
        "Innocent", "No record", "Will join"]
    assert _as_items(["a", "b"]) == ["a", "b"]
    assert _as_items(None) == [] and _as_items("") == []


@pytest.mark.parametrize("template, key", [
    ("bail_application", "grounds"),
    ("power_of_attorney", "powers"),
    ("dispute_petition", "facts"),
])
async def test_builders_number_typed_lines_not_characters(template, key):
    html = template_html(template, {key: "First point\nSecond point"}, placeholders=False)
    text = re.sub(r"<[^>]+>", "|", html)
    assert "1. First point" in text and "2. Second point" in text
    assert "1. F|" not in text and "2. i|" not in text
