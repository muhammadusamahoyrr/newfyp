"""An admin cannot read case or document CONTENTS through the ordinary routes.

The admin panel shows an allowlist of case fields and ends cases through its
own audited route. `_assert_access` and `get_document` used to wave the admin
role straight through, so the same account could read every case's messages,
tasks and documents via /cases and /documents, with no audit record.
"""
import asyncio

import pytest

from app.core.exceptions import ForbiddenError, NotFoundError
from app.services import case_service, document_service

CASE = {"_id": "c1", "client_id": "client-1", "lawyer_id": "lawyer-1"}


def test_admin_is_refused_case_access():
    with pytest.raises(ForbiddenError):
        case_service._assert_access(CASE, "admin-1", "admin")


def test_the_cases_own_parties_still_get_in():
    case_service._assert_access(CASE, "client-1", "client")
    case_service._assert_access(CASE, "lawyer-1", "lawyer")


def test_admin_cannot_open_someone_elses_document(monkeypatch):
    doc = {"_id": "d1", "client_id": "client-1", "case_id": "c1"}

    async def _find(_id):
        return dict(doc)

    monkeypatch.setattr(document_service.doc_repo, "find_by_id", _find)
    with pytest.raises((ForbiddenError, NotFoundError)):
        asyncio.run(document_service.get_document("d1", "admin-1", "admin"))


def test_admin_case_document_listing_is_not_the_whole_case(monkeypatch):
    seen = {}

    async def _find_by_case(case_id, owner_id=None):
        seen["owner_id"] = owner_id
        return []

    monkeypatch.setattr(document_service.doc_repo, "find_by_case", _find_by_case)
    asyncio.run(document_service.list_documents("c1", "admin-1", "admin"))
    # Filtered to the admin's own documents, never the unfiltered case listing.
    assert seen["owner_id"] == "admin-1"
