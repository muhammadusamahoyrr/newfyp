"""Restoring an older version brings it back as the NEXT version (2026-10-19).

Nothing is rewritten: the old revision's own stored source is rendered again as
a new, guarded revision that records where it came from. Owner-only, refused
while under review, refused against a stale screen, and wording a lawyer wrote
keeps that attribution.
"""
from __future__ import annotations

import secrets

import pytest
from fastapi import HTTPException

import app.api.v1.routes.documents_v2 as api
from app.core.config import settings
from app.db.collections import get_document_revisions_col, get_documents_col
from app.services import artifact_store as store

pytestmark = pytest.mark.integration

CLIENT = {"_id": "restore-client", "role": "client", "full_name": "Client Owner"}
OTHER = {"_id": "restore-other", "role": "client"}


def key() -> str:
    return secrets.token_urlsafe(16)


@pytest.fixture
def enabled(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "documents_v2", True)
    monkeypatch.setattr(settings, "upload_root", str(tmp_path))
    store.ensure_dirs()


@pytest.fixture(autouse=True)
async def clean(mongo):
    flt = {"document_id": {"$regex": "^restore-doc-"}}
    await get_document_revisions_col().delete_many(flt)
    await get_documents_col().delete_many({"_id": {"$regex": "^restore-doc-"}})
    yield
    await get_document_revisions_col().delete_many(flt)
    await get_documents_col().delete_many({"_id": {"$regex": "^restore-doc-"}})


async def seed_two_versions() -> tuple[str, dict, dict]:
    """v1 seeded as generated; v2 made through a real save."""
    doc_id = f"restore-doc-{secrets.token_hex(5)}"
    v1_id = f"restore-rev-{secrets.token_hex(5)}"
    await get_documents_col().insert_one({
        "_id": doc_id, "client_id": CLIENT["_id"], "schema_version": 2,
        "title": "Notice", "template_type": "legal_notice",
        "current_revision_id": v1_id, "current_version": 1,
        "rev_seq": 1, "content_epoch": 0, "review_status": "none",
    })
    v1 = {"_id": v1_id, "document_id": doc_id, "version": 1, "status": "generated",
          "template_type": "legal_notice", "idempotency_key": key(),
          "fields": {"notice_body": "The first wording."},
          "artifact_key": "unused", "pdf_sha256": "a" * 64}
    await get_document_revisions_col().insert_one(v1)
    v2 = await api.save_document_workspace_v2(
        doc_id, api.WorkspaceSaveBody(fields={"notice_body": "The second wording."},
                                      expected_revision_id=v1_id, expected_version=1,
                                      expected_content_epoch=0),
        idempotency_key=key(), current_user=CLIENT)
    return doc_id, v1, v2


def guard(doc: dict) -> api.RestoreBody:
    return api.RestoreBody(expected_revision_id=doc["current_revision_id"],
                           expected_version=doc["current_version"],
                           expected_content_epoch=doc["content_epoch"])


async def test_restoring_an_older_version_makes_it_the_next_version(enabled):
    doc_id, v1, v2 = await seed_two_versions()
    doc = await get_documents_col().find_one({"_id": doc_id})
    restored = await api.restore_revision_v2(doc_id, v1["_id"], guard(doc),
                                             idempotency_key=key(), current_user=CLIENT)

    assert restored["version"] == 3
    assert restored["restored_from"] == {"revision_id": v1["_id"], "version": 1}
    stored = await get_document_revisions_col().find_one({"_id": restored["revision_id"]})
    assert stored["fields"] == {"notice_body": "The first wording."}
    # Nothing was rewritten: v1 and v2 are still there, unchanged.
    assert await get_document_revisions_col().count_documents({"document_id": doc_id}) == 3
    old = await get_document_revisions_col().find_one({"_id": v2["revision_id"]})
    assert old["fields"] == {"notice_body": "The second wording."}
    fresh = await get_documents_col().find_one({"_id": doc_id})
    assert fresh["current_revision_id"] == restored["revision_id"]


async def test_restoring_the_current_version_is_refused(enabled):
    doc_id, _v1, v2 = await seed_two_versions()
    doc = await get_documents_col().find_one({"_id": doc_id})
    with pytest.raises(HTTPException) as caught:
        await api.restore_revision_v2(doc_id, v2["revision_id"], guard(doc),
                                      idempotency_key=key(), current_user=CLIENT)
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "already_current"


async def test_only_the_owner_can_restore(enabled):
    doc_id, v1, _ = await seed_two_versions()
    doc = await get_documents_col().find_one({"_id": doc_id})
    with pytest.raises(HTTPException) as caught:
        await api.restore_revision_v2(doc_id, v1["_id"], guard(doc),
                                      idempotency_key=key(), current_user=OTHER)
    assert caught.value.status_code == 404


async def test_a_document_under_review_cannot_be_restored(enabled):
    doc_id, v1, _ = await seed_two_versions()
    await get_documents_col().update_one({"_id": doc_id}, {"$set": {"review_status": "submitted"}})
    doc = await get_documents_col().find_one({"_id": doc_id})
    with pytest.raises(HTTPException) as caught:
        await api.restore_revision_v2(doc_id, v1["_id"], guard(doc),
                                      idempotency_key=key(), current_user=CLIENT)
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "revision_under_review"


async def test_a_stale_screen_cannot_restore_over_a_newer_version(enabled):
    doc_id, v1, _ = await seed_two_versions()
    stale = api.RestoreBody(expected_revision_id=v1["_id"], expected_version=1, expected_content_epoch=0)
    with pytest.raises(Exception) as caught:
        await api.restore_revision_v2(doc_id, v1["_id"], stale,
                                      idempotency_key=key(), current_user=CLIENT)
    assert getattr(caught.value, "status_code", None) == 409
    assert await get_document_revisions_col().count_documents({"document_id": doc_id}) == 2


async def test_a_lawyers_wording_keeps_its_attribution_when_restored(enabled):
    doc_id, v1, _ = await seed_two_versions()
    lawyer = {"role": "lawyer", "user_id": "restore-lawyer", "name": "Adv. Test"}
    await get_document_revisions_col().update_one({"_id": v1["_id"]}, {"$set": {"edited_by": lawyer}})
    doc = await get_documents_col().find_one({"_id": doc_id})
    restored = await api.restore_revision_v2(doc_id, v1["_id"], guard(doc),
                                             idempotency_key=key(), current_user=CLIENT)
    assert restored["edited_by"] == lawyer


async def test_a_revision_that_never_generated_cannot_be_restored(enabled):
    doc_id, v1, _ = await seed_two_versions()
    await get_document_revisions_col().update_one({"_id": v1["_id"]}, {"$set": {"status": "failed"}})
    doc = await get_documents_col().find_one({"_id": doc_id})
    with pytest.raises(HTTPException) as caught:
        await api.restore_revision_v2(doc_id, v1["_id"], guard(doc),
                                      idempotency_key=key(), current_user=CLIENT)
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "revision_not_restorable"
