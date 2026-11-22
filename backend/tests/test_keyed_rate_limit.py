"""Pre-auth limits are keyed on the account, not the (shared) proxy IP.

Every browser request arrives through the Next rewrite proxy, which adds no
X-Forwarded-For, so the remote address is 127.0.0.1 for everyone. An IP-keyed
"5/minute" on /auth/login was therefore one bucket for all visitors.
"""
import asyncio

import pytest
from slowapi import Limiter

import app.core.rate_limit as rl


@pytest.fixture
def mem_limiter(monkeypatch):
    # Never the app singleton: that one may point at hosted Redis.
    fresh = Limiter(key_func=lambda r: "x", storage_uri="memory://", swallow_errors=True)
    monkeypatch.setattr(rl, "limiter", fresh)
    return fresh


def _run(coro):
    return asyncio.run(coro)


def test_one_account_exhausting_its_limit_does_not_block_another(mem_limiter):
    for _ in range(5):
        _run(rl.enforce_keyed_limit("5/minute", "login", "attacker@example.com"))
    with pytest.raises(rl.KeyedRateLimited):
        _run(rl.enforce_keyed_limit("5/minute", "login", "attacker@example.com"))
    # A different person, same (proxy) IP: still allowed.
    _run(rl.enforce_keyed_limit("5/minute", "login", "someone.else@example.com"))


def test_key_is_case_and_space_insensitive(mem_limiter):
    for _ in range(2):
        _run(rl.enforce_keyed_limit("2/minute", "login", "A@Example.com"))
    with pytest.raises(rl.KeyedRateLimited):
        _run(rl.enforce_keyed_limit("2/minute", "login", "  a@example.com "))


def test_scopes_are_separate(mem_limiter):
    _run(rl.enforce_keyed_limit("1/minute", "login", "a@example.com"))
    _run(rl.enforce_keyed_limit("1/minute", "forgot-password", "a@example.com"))


def test_storage_outage_fails_open(mem_limiter, monkeypatch):
    def _boom(*_a, **_k):
        raise ConnectionError("Connection closed by server.")
    monkeypatch.setattr(mem_limiter.limiter, "hit", _boom)
    for _ in range(10):
        _run(rl.enforce_keyed_limit("1/minute", "login", "a@example.com"))


def test_login_route_answers_429_from_the_keyed_limit(mem_limiter, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services import auth_service

    async def _bad_login(*_a, **_k):
        from app.core.exceptions import AuthError
        raise AuthError("Invalid email or password")

    monkeypatch.setattr(auth_service, "login", _bad_login)
    body = {"email": "victim@example.com", "password": "Wrong-pass-1"}
    # No `with`: the lifespan (DB connections) is not run; login is stubbed.
    c = TestClient(app, raise_server_exceptions=False)
    codes = [c.post("/api/v1/auth/login", json=body).status_code for _ in range(6)]
    other = c.post("/api/v1/auth/login",
                   json={"email": "other@example.com", "password": "Wrong-pass-1"})
    assert codes[:5] == [401] * 5
    assert codes[5] == 429
    assert other.status_code == 401
