"""A description no named template fits is written by the AI (2026-10-19).

The user's choice over refusing it ("We couldn't tell which document this is").
The plan asks nothing, the text is written once and kept on the plan, the
document is a `general_document` rendered from that text, and the writer is
fail-closed: when its legal check cannot run, nothing is stored.
"""
from __future__ import annotations

import secrets

import pytest

from app.core.config import settings
from app.core.exceptions import AppValidationError, ServiceUnavailableError
from app.db.collections import (
    get_document_draft_plans_col,
    get_document_revisions_col,
    get_documents_col,
)
from app.repositories import revision_repo
from app.services import artifact_store as store
from app.services import document_draft_plan_service as plans
from app.services import document_v2_service as v2
from app.services import general_draft, template_registry

pytestmark = pytest.mark.integration

OWNER = "general-draft-client"
PROMPT = "Employment contract for a sales manager"


def key() -> str:
    return secrets.token_urlsafe(12)


@pytest.fixture(autouse=True)
async def _enabled_and_clean(mongo, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "documents_v2", True)
    monkeypatch.setattr(settings, "upload_root", str(tmp_path))
    store.ensure_dirs()

    async def wipe():
        docs = [d async for d in get_documents_col().find({"client_id": OWNER})]
        if docs:
            await get_document_revisions_col().delete_many(
                {"document_id": {"$in": [d["_id"] for d in docs]}})
        await get_documents_col().delete_many({"client_id": OWNER})
        await get_document_draft_plans_col().delete_many({"owner_id": OWNER})

    await wipe()
    yield
    await wipe()


@pytest.fixture
def rendered(monkeypatch):
    seen = {}

    async def render(*, revision_id, document_id, version, template_type,
                     fields, fence, worker_id):
        seen["template_type"], seen["fields"] = template_type, fields
        payload = b"%PDF-1.4 general"
        artifact_key = store.write_final(revision_id, fence, payload)
        promoted = await revision_repo.promote(revision_id, worker_id, fence, {
            "artifact_key": artifact_key, "pdf_sha256": store.sha256_bytes(payload),
            "text_sha256": "t" * 64, "body_text": "text", "extraction_status": "ok",
            "verification": {"ran": True, "counts": {"total": 0}}, "compliance": {"checked": False},
        })
        await revision_repo.repoint_document(document_id, revision_id, version)
        return promoted
    monkeypatch.setattr(v2, "_render_and_select", render)
    return seen


@pytest.fixture
def writer(monkeypatch):
    calls = []

    async def write(prompt, *, case=None, province=""):
        calls.append(prompt)
        return {"title": "Employment Contract", "withheld": [],
                "body_html": "<h1>EMPLOYMENT CONTRACT</h1><p>Between [Employer] and [Employee].</p>"}
    monkeypatch.setattr(general_draft, "write", write)
    return calls


async def _plan():
    return await plans.create_plan(owner_id=OWNER, prompt=PROMPT, template_type=None,
                                   title=None, case_id=None, idempotency_key=key())


async def _confirmed():
    plan = await _plan()
    return await plans.confirm_plan(owner_id=OWNER, plan_id=plan["id"],
                                    expected_version=plan["version"], skip_missing=False)


async def test_an_unmatched_description_becomes_a_ready_general_document():
    plan = await _plan()
    assert plan["template_type"] == "general_document"
    assert plan["status"] == "ready" and plan["questions"] == []
    assert plan["title"] == PROMPT


async def test_a_matched_description_still_uses_its_template(monkeypatch):
    async def extract(_p, _t):
        return {}
    monkeypatch.setattr(plans.document_service, "extract_fields_from_text", extract)
    plan = await plans.create_plan(owner_id=OWNER, prompt="A rent agreement for a shop in Lahore",
                                   template_type=None, title=None, case_id=None, idempotency_key=key())
    assert plan["template_type"] == "rental_agreement"


async def test_a_general_plan_takes_no_field_answers():
    plan = await _plan()
    with pytest.raises(AppValidationError):
        await plans.answer_plan(owner_id=OWNER, plan_id=plan["id"],
                                expected_version=plan["version"], answers={"body_html": "<p>x</p>"})


async def test_it_confirms_without_details_and_generates_one_general_document(writer, rendered):
    plan = await _confirmed()
    idem = key()
    made = await plans.generate_plan(owner_id=OWNER, plan_id=plan["id"],
                                     expected_version=plan["version"], idempotency_key=idem)
    again = await plans.generate_plan(owner_id=OWNER, plan_id=plan["id"],
                                      expected_version=plan["version"], idempotency_key=idem)
    assert made["status"] == "generated" and made["generation"] == again["generation"]
    assert writer == [PROMPT], "the AI must write once, not on every retry"
    assert rendered["template_type"] == "general_document"
    assert "EMPLOYMENT CONTRACT" in rendered["fields"]["body_html"]
    doc = await get_documents_col().find_one({"_id": made["generation"]["document_id"]})
    assert doc["template_type"] == "general_document"
    assert doc["title"] == "Employment Contract"


async def test_a_failed_write_marks_the_plan_failed_and_stores_nothing(monkeypatch, rendered):
    async def broken(prompt, *, case=None, province=""):
        raise ServiceUnavailableError("The legal check on the draft could not run, so nothing was saved.")
    monkeypatch.setattr(general_draft, "write", broken)
    plan = await _confirmed()
    with pytest.raises(ServiceUnavailableError):
        await plans.generate_plan(owner_id=OWNER, plan_id=plan["id"],
                                  expected_version=plan["version"], idempotency_key=key())
    stored = await get_document_draft_plans_col().find_one({"_id": plan["id"]})
    assert stored["status"] == "generation_failed" and stored["generation_error"] == "draft_failed"
    assert not (stored.get("fields") or {}).get("body_html")
    assert await get_documents_col().count_documents({"client_id": OWNER}) == 0


def test_general_document_is_freeform_and_not_offered_as_a_template():
    assert "general_document" in template_registry.FREEFORM
    assert template_registry.known("general_document")
    assert "general_document" not in [i["template_type"] for i in template_registry.listing()]
    assert "general_document" not in plans.supported_template_types()


def test_draft_text_becomes_escaped_headings_and_paragraphs():
    out = general_draft.text_to_html(
        "EMPLOYMENT CONTRACT\n\nThis agreement is between [Employer] <b>and</b> [Employee].\n\n"
        "1. DUTIES\nThe employee shall sell.")
    assert out.startswith("<h1>EMPLOYMENT CONTRACT</h1>")
    assert "&lt;b&gt;and&lt;/b&gt;" in out, "model text must never pass through as markup"
    assert "<h2>1. DUTIES</h2>" in out or "1. DUTIES" in out


async def test_the_writer_stores_nothing_when_the_corpus_is_unreadable(monkeypatch):
    from app.ai import index_health

    class Down(index_health.IdentityIndexUnavailable):
        def __init__(self):
            Exception.__init__(self, "identity index down")

    def unavailable(_indexes):
        raise Down()
    monkeypatch.setattr(index_health, "require_all", unavailable)
    with pytest.raises(ServiceUnavailableError):
        await general_draft.write(PROMPT)


async def test_the_writer_stores_nothing_when_the_legal_check_cannot_run(monkeypatch):
    from app.ai import draft_guard, index_health
    from app.api.v1.routes import ai as ai_routes

    monkeypatch.setattr(index_health, "require_all", lambda _i: None)
    monkeypatch.setattr(ai_routes, "_retrieve_law_context", lambda *a, **k: "")

    async def no_case_law(_q):
        return ""
    monkeypatch.setattr(ai_routes, "_retrieve_case_law_context", no_case_law)
    monkeypatch.setattr(ai_routes, "_exact_provisions_for", lambda _t: [])

    class Reply:
        content = "EMPLOYMENT CONTRACT\n\nBetween [Employer] and [Employee]."

    class LLM:
        async def ainvoke(self, _messages):
            return Reply()
    import app.ai.llm as llm_mod
    monkeypatch.setattr(llm_mod, "get_llm", lambda **_k: LLM())

    def boom(*_a, **_k):
        raise RuntimeError("guard down")
    monkeypatch.setattr(draft_guard, "check", boom)
    with pytest.raises(ServiceUnavailableError):
        await general_draft.write(PROMPT)

    monkeypatch.setattr(draft_guard, "check", lambda *a, **k: {"ran": True, "withheld": [],
                                                              "text": Reply.content})
    written = await general_draft.write(PROMPT)
    assert written["title"] == "Employment Contract"
    assert "<h1>EMPLOYMENT CONTRACT</h1>" in written["body_html"]


def test_markdown_the_model_adds_anyway_becomes_real_headings_and_bold():
    out = general_draft.text_to_html("**RECITALS**\n\n1. **[Employer Name]** <i>x</i>\n\n## Duties\nText")
    assert "**" not in out and "##" not in out
    assert "<h1>RECITALS</h1>" in out and "<h2>Duties</h2>" in out
    assert "<strong>[[EMPLOYER_NAME]]</strong>" in out
    assert "&lt;i&gt;x&lt;/i&gt;" in out, "only bold is made from model text; other markup stays escaped"


def test_titles_keep_acronyms_and_small_words():
    assert general_draft._soft_title("AFFIDAVIT FOR LOST CNIC") == "Affidavit for Lost CNIC"
    assert general_draft._soft_title("EMPLOYMENT CONTRACT") == "Employment Contract"
    assert general_draft._soft_title("NDA WITH A DESIGNER") == "NDA with a Designer"


def test_the_client_rider_forbids_citations_the_client_did_not_ask_for():
    assert "Add NO legal citations" in general_draft._CLIENT_RIDER


def test_the_models_placeholders_become_fillable_tokens():
    out = general_draft.text_to_html(
        "I, [Full Name], son of [Father’s Name], residing at [Complete Residential Address].\n\n"
        "See clause [1]. Already a token: [[DATE]].")
    assert "[[FULL_NAME]]" in out and "[[FATHERS_NAME]]" in out
    assert "[[COMPLETE_RESIDENTIAL_ADDRESS]]" in out
    assert "[1]" in out, "a bracket with no letters is not a placeholder"
    assert "[[DATE]]" in out and "[[[" not in out


def test_closing_notes_in_brackets_are_not_placeholders():
    out = general_draft.text_to_html("Signed.\n\n[End of Document]")
    assert "END_OF_DOCUMENT" not in out and "End of Document" not in out
