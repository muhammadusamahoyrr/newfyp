"""Read receipts for appointment threads (2026-10-19)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.db.collections import get_appointment_messages_col, get_appointments_col
from app.db.mongodb import get_database
from app.services import appointment_thread_reads as tr

pytestmark = pytest.mark.integration

CLIENT = {"_id": "tr-client", "role": "client"}
LAWYER = {"_id": "tr-lawyer", "role": "lawyer"}
OTHER = {"_id": "tr-other", "role": "lawyer"}
A1, A2 = "tr-appt-1", "tr-appt-2"
T0 = datetime(2030, 1, 1, 9, 0, tzinfo=timezone.utc)


async def _msg(appt, sender, text, minutes):
    await get_appointment_messages_col().insert_one({
        "_id": f"tr-m-{appt}-{minutes}", "appointment_id": appt, "sender_id": sender["_id"],
        "sender_role": sender["role"], "text": text, "created_at": T0 + timedelta(minutes=minutes)})


@pytest.fixture(autouse=True)
async def _setup(mongo):
    async def clean():
        await get_appointments_col().delete_many({"_id": {"$in": [A1, A2]}})
        await get_appointment_messages_col().delete_many({"appointment_id": {"$in": [A1, A2]}})
        await get_database()["appointment_thread_reads"].delete_many({"appointment_id": {"$in": [A1, A2]}})
    await clean()
    for a in (A1, A2):
        await get_appointments_col().insert_one({"_id": a, "client_id": CLIENT["_id"], "lawyer_id": LAWYER["_id"], "status": "confirmed"})
    yield
    await clean()


async def test_unread_counts_only_the_other_partys_messages_and_the_last_is_previewed():
    await _msg(A1, CLIENT, "hey ustad", 1)
    await _msg(A1, LAWYER, "hello", 2)
    await _msg(A1, CLIENT, "can we   move it\nto 11?", 3)
    s = (await tr.summary([A1, A2], LAWYER))["items"]
    assert s[A1]["unread"] == 2
    assert s[A1]["last"]["text"] == "can we move it to 11?" and s[A1]["last"]["from_me"] is False
    assert A2 not in s, "a thread with no messages has nothing to summarise"


async def test_reading_clears_the_count_until_a_new_message_arrives():
    await _msg(A1, CLIENT, "one", 1)
    await tr.mark_read(A1, LAWYER)
    assert (await tr.summary([A1], LAWYER))["items"][A1]["unread"] == 0
    await get_appointment_messages_col().insert_one({
        "_id": "tr-m-late", "appointment_id": A1, "sender_id": CLIENT["_id"], "sender_role": "client",
        "text": "two", "created_at": T0 + timedelta(minutes=5)})
    assert (await tr.summary([A1], LAWYER))["items"][A1]["unread"] == 1


async def test_each_party_has_its_own_receipt():
    await _msg(A1, LAWYER, "from lawyer", 1)
    await tr.mark_read(A1, LAWYER)
    assert (await tr.summary([A1], CLIENT))["items"][A1]["unread"] == 1


async def test_strangers_get_nothing_and_cannot_mark_read():
    await _msg(A1, CLIENT, "private", 1)
    assert (await tr.summary([A1], OTHER))["items"] == {}
    with pytest.raises(HTTPException) as e:
        await tr.mark_read(A1, OTHER)
    assert e.value.status_code == 403


async def test_a_long_message_is_cut_for_the_preview():
    await _msg(A1, CLIENT, "x" * 300, 1)
    text = (await tr.summary([A1], LAWYER))["items"][A1]["last"]["text"]
    assert len(text) == tr.PREVIEW + 1 and text.endswith("…")
