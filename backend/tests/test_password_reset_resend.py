"""Asking for a second password-reset link (2026-10-20).

One active link per account stays the rule (unique index
`uniq_active_password_reset_email`). What changed is the second request:

  * moments after the first (a double click) it keeps the first link -- that
    email is still on its way, and replacing it would kill the message the
    user is about to open;
  * later than that, the person is asking because the first email never came,
    so the unused link is replaced and a new email is sent. It used to send
    nothing for an hour while the page said "sent";
  * if that new email cannot be sent, the old link is put back, so the email
    the user already has keeps working.
"""
import secrets
from datetime import datetime, timedelta, timezone

import pytest

from app.services import auth_service as auth

pytestmark = pytest.mark.integration


@pytest.fixture
async def account(app_indexes, monkeypatch):
    from app.db.collections import get_password_reset_col

    email = f"reset-{secrets.token_hex(4)}@test.invalid"
    sent = []

    async def user(_email):
        return {"_id": "u-reset", "email": email}

    async def deliver(_address, token):
        sent.append(token)
        return True

    monkeypatch.setattr(auth.user_repo, "find_by_email", user)
    monkeypatch.setattr(auth, "send_password_reset_email", deliver)
    yield {"email": email, "sent": sent}
    await get_password_reset_col().delete_many({"email": email})


async def _rows(email):
    from app.db.collections import get_password_reset_col
    return await get_password_reset_col().find({"email": email}).to_list(None)


async def _age(email, minutes):
    from app.db.collections import get_password_reset_col
    await get_password_reset_col().update_many(
        {"email": email},
        {"$set": {"created_at": datetime.now(timezone.utc) - timedelta(minutes=minutes)}})


async def test_a_double_click_keeps_the_first_link(account):
    await auth.forgot_password(account["email"])
    await auth.forgot_password(account["email"])

    rows = await _rows(account["email"])
    assert len(account["sent"]) == 1
    assert len(rows) == 1
    assert rows[0]["token"] == auth._reset_token_key(account["sent"][0])


async def test_a_later_request_sends_a_new_working_link(account):
    await auth.forgot_password(account["email"])
    await _age(account["email"], 5)

    await auth.forgot_password(account["email"])

    rows = await _rows(account["email"])
    assert len(account["sent"]) == 2
    assert len(rows) == 1, "still one active link per account"
    assert rows[0]["token"] == auth._reset_token_key(account["sent"][1])
    assert datetime.now(timezone.utc) - rows[0]["created_at"].replace(tzinfo=timezone.utc) \
        < timedelta(minutes=1), "the new link gets its own hour"


async def test_a_link_being_used_is_not_replaced(account):
    from app.db.collections import get_password_reset_col
    await auth.forgot_password(account["email"])
    await _age(account["email"], 5)
    await get_password_reset_col().update_one(
        {"email": account["email"]}, {"$set": {"claimed_at": datetime.now(timezone.utc)}})

    await auth.forgot_password(account["email"])

    rows = await _rows(account["email"])
    assert len(account["sent"]) == 1
    assert rows[0]["token"] == auth._reset_token_key(account["sent"][0])


@pytest.mark.parametrize("failure", [False, RuntimeError("smtp down")])
async def test_a_failed_resend_puts_the_old_link_back(account, monkeypatch, failure):
    await auth.forgot_password(account["email"])
    first = account["sent"][0]
    await _age(account["email"], 5)
    before = (await _rows(account["email"]))[0]

    async def broken(_address, _token):
        if isinstance(failure, Exception):
            raise failure
        return failure
    monkeypatch.setattr(auth, "send_password_reset_email", broken)

    assert await auth.forgot_password(account["email"]) is None

    rows = await _rows(account["email"])
    assert len(rows) == 1
    assert rows[0]["token"] == auth._reset_token_key(first), "the email already sent must keep working"
    assert rows[0]["created_at"] == before["created_at"]
