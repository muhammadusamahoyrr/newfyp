"""Documents a client attaches to an appointment (2026-10-19).

The user's rules: while pending the lawyer sees only the name, type and note;
once accepted the lawyer can open the files; a declined, cancelled or expired
request never gives the lawyer access. A client may let one file be opened
before acceptance (off by default).
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.db.collections import get_appointments_col
from app.db.mongodb import get_database
from app.services import appointment_files as af

pytestmark = pytest.mark.integration

CLIENT, LAWYER, OTHER = {"_id": "af-client"}, {"_id": "af-lawyer"}, {"_id": "af-other"}
APPT = "af-appt"
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


async def _status(s):
    await get_appointments_col().update_one({"_id": APPT}, {"$set": {"status": s}})


@pytest.fixture(autouse=True)
async def _setup(mongo, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_root", str(tmp_path))
    col = get_appointments_col()
    await col.delete_many({"_id": APPT})
    await col.insert_one({"_id": APPT, "client_id": CLIENT["_id"], "lawyer_id": LAWYER["_id"], "status": "pending"})
    await get_database()["appointment_files"].delete_many({"appointment_id": APPT})
    yield
    await col.delete_many({"_id": APPT})
    await get_database()["appointment_files"].delete_many({"appointment_id": APPT})


async def test_the_client_uploads_lists_opens_and_removes():
    up = await af.upload(APPT, CLIENT, PDF, "agreement.pdf", "Signed copy", False)
    assert up["name"] == "agreement.pdf" and up["note"] == "Signed copy"
    assert up["share_before_accept"] is False and up["lawyer_can_open"] is False
    listed = await af.list_for(APPT, CLIENT)
    assert [f["id"] for f in listed["items"]] == [up["id"]]
    _, data = await af.read(APPT, up["id"], CLIENT)
    assert data == PDF
    await af.delete(APPT, up["id"], CLIENT)
    assert (await af.list_for(APPT, CLIENT))["items"] == []


async def test_pending_the_lawyer_sees_nothing_of_a_private_file():
    """2026-10-19 rule: not even the name, unless the client shows it early."""
    up = await af.upload(APPT, CLIENT, PDF, "agreement.pdf", "Signed copy", False)
    assert (await af.list_for(APPT, LAWYER))["items"] == []
    await _status("confirmed")
    seen = (await af.list_for(APPT, LAWYER))["items"]
    assert seen[0]["name"] == "agreement.pdf" and seen[0]["can_open"] is True
    assert "share_before_accept" not in seen[0]
    await _status("pending")
    with pytest.raises(HTTPException) as e:
        await af.read(APPT, up["id"], LAWYER)
    assert e.value.status_code == 404


async def test_a_file_shared_early_opens_for_the_lawyer_while_pending():
    up = await af.upload(APPT, CLIENT, PNG, "photo.png", None, True)
    assert (await af.list_for(APPT, LAWYER))["items"][0]["can_open"] is True
    _, data = await af.read(APPT, up["id"], LAWYER)
    assert data == PNG


@pytest.mark.parametrize("status", ["confirmed", "completed", "no_show"])
async def test_once_accepted_the_lawyer_can_open_every_file(status):
    up = await af.upload(APPT, CLIENT, PDF, "a.pdf", None, False)
    await _status(status)
    assert (await af.list_for(APPT, LAWYER))["items"][0]["can_open"] is True
    _, data = await af.read(APPT, up["id"], LAWYER)
    assert data == PDF


@pytest.mark.parametrize("status", ["cancelled", "expired"])
async def test_a_declined_cancelled_or_expired_request_gives_the_lawyer_nothing(status):
    up = await af.upload(APPT, CLIENT, PDF, "a.pdf", "note", True)   # even if shared early
    await _status(status)
    assert (await af.list_for(APPT, LAWYER))["items"] == []
    with pytest.raises(HTTPException) as e:
        await af.read(APPT, up["id"], LAWYER)
    assert e.value.status_code == 404
    # The client still has their own file.
    assert len((await af.list_for(APPT, CLIENT))["items"]) == 1


async def test_someone_else_gets_not_found_for_everything():
    up = await af.upload(APPT, CLIENT, PDF, "a.pdf", None, True)
    for call in (af.list_for(APPT, OTHER), af.read(APPT, up["id"], OTHER),
                 af.upload(APPT, OTHER, PDF, "x.pdf", None, False), af.delete(APPT, up["id"], OTHER)):
        with pytest.raises(HTTPException) as e:
            await call
        assert e.value.status_code == 404


async def test_only_the_client_uploads_or_removes():
    up = await af.upload(APPT, CLIENT, PDF, "a.pdf", None, False)
    with pytest.raises(HTTPException):
        await af.upload(APPT, LAWYER, PDF, "x.pdf", None, False)
    with pytest.raises(HTTPException):
        await af.delete(APPT, up["id"], LAWYER)


async def test_the_kind_comes_from_the_bytes_and_size_and_note_are_limited():
    with pytest.raises(HTTPException) as e:
        await af.upload(APPT, CLIENT, b"MZ\x90\x00 not a pdf", "evil.pdf", None, False)
    assert e.value.status_code == 422
    with pytest.raises(HTTPException):
        await af.upload(APPT, CLIENT, b"", "a.pdf", None, False)
    with pytest.raises(HTTPException):
        await af.upload(APPT, CLIENT, PDF + b"x" * af.MAX_BYTES, "big.pdf", None, False)
    with pytest.raises(HTTPException):
        await af.upload(APPT, CLIENT, PDF, "a.pdf", "x" * (af.NOTE_MAX + 1), False)


async def test_at_most_five_files_and_none_after_it_closes():
    for n in range(af.MAX_FILES):
        await af.upload(APPT, CLIENT, PDF, f"{n}.pdf", None, False)
    with pytest.raises(HTTPException) as e:
        await af.upload(APPT, CLIENT, PDF, "six.pdf", None, False)
    assert e.value.status_code == 409
    await _status("completed")
    with pytest.raises(HTTPException) as e:
        await af.delete(APPT, (await af.list_for(APPT, CLIENT))["items"][0]["id"], CLIENT)
    assert e.value.status_code == 409


async def test_a_path_in_the_name_is_only_a_label():
    up = await af.upload(APPT, CLIENT, PDF, "../../etc/passwd.pdf", None, False)
    assert up["name"] == "passwd.pdf"
