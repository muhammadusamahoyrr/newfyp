"""Concurrency and transport contracts for authentication hardening.

Pure fakes deliberately force the interleavings that ordinary sequential tests
cannot reach. No provider, Redis, production database, or email server is used.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pymongo.errors import DuplicateKeyError
from starlette.requests import Request
from starlette.responses import Response

from app.core.exceptions import AuthError


class _RefreshClaim:
    def __init__(self):
        self.claimed = False

    async def insert_one(self, _row):
        if self.claimed:
            raise DuplicateKeyError("duplicate")
        self.claimed = True


@pytest.mark.asyncio
async def test_concurrent_refresh_has_one_winner_and_one_controlled_401(monkeypatch):
    from app.services import auth_service as auth

    col = _RefreshClaim()
    monkeypatch.setattr(auth, "get_refresh_blocklist_col", lambda: col)
    monkeypatch.setattr(
        auth, "decode_token",
        lambda _token: {"sub": "u1", "type": "refresh", "iat": 1, "exp": 9999999999},
    )

    async def user(_uid):
        return {"_id": "u1", "role": "client", "is_active": True}

    monkeypatch.setattr(auth.user_repo, "find_by_id", user)
    monkeypatch.setattr(auth, "token_predates_password_change", lambda *_: False)
    monkeypatch.setattr(auth, "create_access_token", lambda *_: "new-access")
    monkeypatch.setattr(auth, "create_refresh_token", lambda *_: "new-refresh")

    import asyncio
    results = await asyncio.gather(
        auth.refresh("same-token"), auth.refresh("same-token"),
        return_exceptions=True,
    )

    assert sum(isinstance(item, dict) for item in results) == 1
    losers = [item for item in results if isinstance(item, Exception)]
    assert len(losers) == 1 and isinstance(losers[0], AuthError)
    assert losers[0].status_code == 401


class _IdempotentRevocations:
    def __init__(self):
        self.tokens = set()

    async def update_one(self, query, _update, upsert=False):
        assert upsert is True
        self.tokens.add(query["token"])


@pytest.mark.asyncio
async def test_logout_is_repeat_safe_and_revokes_both_tokens(monkeypatch):
    from app.services import auth_service as auth
    from app.core.security import token_storage_key

    col = _IdempotentRevocations()
    monkeypatch.setattr(auth, "get_refresh_blocklist_col", lambda: col)
    monkeypatch.setattr(
        auth, "decode_token",
        lambda token: {
            "type": "refresh" if token == "refresh" else "access",
            "exp": 9999999999,
        },
    )

    await auth.logout("refresh", "access")
    await auth.logout("refresh", "access")
    assert col.tokens == {
        token_storage_key("refresh"), token_storage_key("access")}


class _AtomicResetTokens:
    """One reset row with Mongo's claim / release / delete semantics."""

    def __init__(self, row):
        self.row = {"_id": "r1", **row}

    async def find_one_and_update(self, query, change):
        # The claim filter only matches an unclaimed row; the update is atomic.
        if self.row is None or "claimed_at" in self.row:
            return None
        before = dict(self.row)
        self.row.update(change["$set"])
        return before

    async def update_one(self, _query, change):
        if self.row is not None:
            for key in change.get("$unset", {}):
                self.row.pop(key, None)

    async def delete_one(self, _query):
        self.row = None


@pytest.mark.asyncio
async def test_concurrent_reset_consumes_the_token_before_password_update(monkeypatch):
    from app.services import auth_service as auth

    col = _AtomicResetTokens({
        "email": "user@example.test",
        "created_at": datetime.now(timezone.utc),
    })
    monkeypatch.setattr(auth, "get_password_reset_col", lambda: col)

    async def by_email(_email):
        return {"_id": "u1"}

    updates = []

    async def update(_query, change):
        updates.append(change["$set"]["password_hash"])

    monkeypatch.setattr(auth.user_repo, "find_by_email", by_email)
    monkeypatch.setattr(auth.user_repo, "update_one", update)
    async def _fake_hash(password):
        return "hash:" + password
    monkeypatch.setattr(auth, "hash_password_async", _fake_hash)

    import asyncio
    results = await asyncio.gather(
        auth.reset_password("same", "Password1"),
        auth.reset_password("same", "Password2"),
        return_exceptions=True,
    )

    assert sum(item is None for item in results) == 1
    assert sum(isinstance(item, AuthError) for item in results) == 1
    assert len(updates) == 1
    assert col.row is None, "a used link must be gone"


@pytest.mark.asyncio
async def test_failed_password_write_keeps_the_reset_link_usable(monkeypatch):
    """The link used to be deleted before the password was written, so a
    database failure burned it and left the old password in place."""
    from app.services import auth_service as auth

    col = _AtomicResetTokens({
        "email": "user@example.test",
        "created_at": datetime.now(timezone.utc),
    })
    monkeypatch.setattr(auth, "get_password_reset_col", lambda: col)

    async def by_email(_email):
        return {"_id": "u1"}

    calls = {"n": 0}
    stored = []

    async def update(_query, change):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("mongo write failed")
        stored.append(change["$set"]["password_hash"])

    async def no_revoke(*_a, **_k):
        return None

    monkeypatch.setattr(auth.user_repo, "find_by_email", by_email)
    monkeypatch.setattr(auth.user_repo, "update_one", update)
    async def _fake_hash(password):
        return "hash:" + password
    monkeypatch.setattr(auth, "hash_password_async", _fake_hash)
    monkeypatch.setattr(auth.auth_sessions, "revoke_all_best_effort", no_revoke)

    with pytest.raises(RuntimeError):
        await auth.reset_password("same", "Password1")
    assert col.row is not None and "claimed_at" not in col.row, "the failed attempt burned the link"

    await auth.reset_password("same", "Password1")
    assert stored == ["hash:Password1"]
    assert col.row is None


class _ResetStore:
    def __init__(self):
        self.rows = []

    async def delete_many(self, query):
        self.rows = [row for row in self.rows if row.get("email") != query["email"]]

    async def insert_one(self, row):
        self.rows.append(dict(row))

    async def delete_one(self, query):
        self.rows = [row for row in self.rows if row.get("token") != query["token"]]


@pytest.mark.asyncio
async def test_new_reset_secret_is_hashed_at_rest(monkeypatch):
    from app.services import auth_service as auth

    store = _ResetStore()
    sent = {}
    monkeypatch.setattr(auth, "get_password_reset_col", lambda: store)

    async def user(_email):
        return {"_id": "u1"}

    async def email(_address, token):
        sent["token"] = token
        return True

    monkeypatch.setattr(auth.user_repo, "find_by_email", user)
    monkeypatch.setattr(auth, "send_password_reset_email", email)
    await auth.forgot_password("USER@example.test")

    assert len(store.rows) == 1
    assert store.rows[0]["token"].startswith("sha256:")
    assert store.rows[0]["token"] != sent["token"]
    assert sent["token"] not in repr(store.rows[0])


@pytest.mark.asyncio
@pytest.mark.parametrize("delivery", [False, RuntimeError("smtp down")])
async def test_delivery_failure_is_publicly_silent_and_removes_token(
    monkeypatch, delivery,
):
    from app.services import auth_service as auth

    store = _ResetStore()
    monkeypatch.setattr(auth, "get_password_reset_col", lambda: store)

    async def user(_email):
        return {"_id": "u1"}

    async def email(_address, _token):
        if isinstance(delivery, Exception):
            raise delivery
        return delivery

    monkeypatch.setattr(auth.user_repo, "find_by_email", user)
    monkeypatch.setattr(auth, "send_password_reset_email", email)

    assert await auth.forgot_password("user@example.test") is None
    assert store.rows == []


def test_revocation_ttl_tracks_the_jwt_expiry():
    from app.services.auth_service import _revocation_record

    expiry = datetime.now(timezone.utc) + timedelta(days=31)
    row = _revocation_record("token", {"type": "refresh", "exp": expiry.timestamp()})
    assert row["expires_at"] == expiry
    assert "created_at" not in row, "legacy TTL must not shorten new revocations"
    assert row["token"].startswith("sha256:")
    assert "token" != row["token"]


@pytest.mark.asyncio
async def test_current_user_refuses_a_revoked_access_token(monkeypatch):
    from app import dependencies
    from app.core.security import create_access_token

    class Blocklist:
        async def find_one(self, _query):
            return {"token_type": "access"}

    class Users:
        async def find_one(self, _query):
            raise AssertionError("revocation must stop before loading the user")

    monkeypatch.setattr(dependencies, "get_refresh_blocklist_col", lambda: Blocklist())
    monkeypatch.setattr(dependencies, "get_users_col", lambda: Users())
    request = SimpleNamespace(state=SimpleNamespace())
    credentials = SimpleNamespace(credentials=create_access_token("u1", "client"))

    with pytest.raises(AuthError, match="revoked"):
        await dependencies.get_current_user(request, credentials)


def _request(*, cookie: str = "", bearer: str = "") -> Request:
    headers = []
    if cookie:
        headers.append((b"cookie", f"refresh_token={cookie}".encode()))
    if bearer:
        headers.append((b"authorization", f"Bearer {bearer}".encode()))
    return Request({
        "type": "http", "method": "POST", "path": "/auth/test",
        "headers": headers, "query_string": b"", "server": ("test", 80),
        "client": ("test", 1), "scheme": "http",
    })


@pytest.mark.asyncio
async def test_logout_forwards_both_tokens_and_always_deletes_cookie(monkeypatch):
    from app.api.v1.routes import auth as routes

    seen = {}

    async def fail(refresh, access):
        seen.update(refresh=refresh, access=access)
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(routes.auth_service, "logout", fail)
    response = Response()
    with pytest.raises(RuntimeError, match="database unavailable"):
        await routes.logout(_request(cookie="refresh", bearer="access"), response)

    assert seen == {"refresh": "refresh", "access": "access"}
    cookie = response.headers.get("set-cookie", "")
    assert "refresh_token=" in cookie
    assert "Max-Age=0" in cookie


def test_refresh_cookie_contract_tracks_configuration(monkeypatch):
    from app.api.v1.routes import auth as routes

    monkeypatch.setattr(routes.settings, "app_env", "production")
    response = Response()
    routes._set_refresh_cookie(response, "secret")
    cookie = response.headers["set-cookie"]

    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "Secure" in cookie
    assert f"Max-Age={routes.settings.refresh_token_expire_days * 86400}" in cookie


def test_access_tokens_minted_in_one_second_are_still_distinct():
    from app.core.security import create_access_token

    assert create_access_token("u1", "client") != create_access_token("u1", "client")


@pytest.mark.asyncio
async def test_concurrent_self_service_password_changes_have_one_winner(monkeypatch):
    from app.services import user_service
    from app.core.exceptions import ConflictError

    class Repo:
        def __init__(self):
            self.current_hash = "old-hash"

        async def find_by_id(self, _uid):
            return {"_id": "u1", "password_hash": "old-hash", "is_active": True}

        async def update_one(self, query, update):
            if query.get("password_hash") != self.current_hash:
                return False
            self.current_hash = update["$set"]["password_hash"]
            return True

    repo = Repo()
    monkeypatch.setattr(user_service, "user_repo", repo)
    async def _always_ok(*_):
        return True
    monkeypatch.setattr(user_service, "verify_password_async", _always_ok)
    monkeypatch.setattr(user_service, "validate_password_strength", lambda *_: True)
    async def _fake_hash_us(value):
        return "hash:" + value
    monkeypatch.setattr(user_service, "hash_password_async", _fake_hash_us)

    import asyncio
    results = await asyncio.gather(
        user_service.change_password("u1", "old", "Password1"),
        user_service.change_password("u1", "old", "Password2"),
        return_exceptions=True,
    )
    assert sum(item is None for item in results) == 1
    assert sum(isinstance(item, ConflictError) for item in results) == 1


@pytest.mark.parametrize("overrides", [
    {"secret_key": "short"},
    {"secret_key": "change-this-to-a-secure-random-string-at-least-32-chars"},
    {"algorithm": "none"},
    {"access_token_expire_minutes": 0},
    {"refresh_token_expire_days": -1},
    {"app_env": "production", "frontend_url": "http://example.test"},
])
def test_unsafe_auth_configuration_fails_at_startup(overrides):
    from pydantic import ValidationError
    from app.core.config import Settings

    safe = {
        "secret_key": "s" * 64,
        "encryption_key": "not-used-by-this-validation-test",
        "app_env": "development",
        "frontend_url": "http://localhost:3000",
    }
    safe.update(overrides)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **safe)


@pytest.mark.asyncio
async def test_forgot_password_answers_before_doing_the_account_work(monkeypatch):
    """Awaiting the lookup + token write + SMTP inside the request made a real
    account answer measurably slower than an unknown email (timing enumeration).
    The route now queues the work and answers at once, for every address."""
    from fastapi import BackgroundTasks
    from app.api.v1.routes import auth as routes
    from app.schemas.auth import ForgotPasswordRequest

    ran = []

    async def slow_work(email):
        ran.append(email)

    monkeypatch.setattr(routes.auth_service, "forgot_password", slow_work)
    tasks = BackgroundTasks()
    endpoint = getattr(routes.forgot_password, "__wrapped__", routes.forgot_password)
    result = await endpoint(None, ForgotPasswordRequest(email="someone@example.com"), tasks)

    assert result.success is True
    assert ran == [], "the account work ran inside the request"
    assert len(tasks.tasks) == 1
    await tasks()
    assert ran == ["someone@example.com"]


@pytest.mark.asyncio
async def test_forgot_password_background_failure_is_logged_not_raised(monkeypatch):
    from app.api.v1.routes import auth as routes

    async def boom(_email):
        raise RuntimeError("mongo down")

    monkeypatch.setattr(routes.auth_service, "forgot_password", boom)
    assert await routes._forgot_password_quietly("x@example.test") is None
