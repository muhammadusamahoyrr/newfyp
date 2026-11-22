"""Email confirmation and Terms/Privacy consent at sign-up (2026-10-18).

A new account confirms its email before it can sign in, but only when SMTP is
configured: without it the link could never arrive. Accounts from before the
field existed have no `email_verified` and keep signing in. The sign-up
checkbox is required and the versions agreed to are stored on the account.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.core.constants import PRIVACY_VERSION, TERMS_VERSION
from app.core.exceptions import AppValidationError, AuthError, ForbiddenError
from app.schemas.auth import RegisterRequest


class _Users:
    def __init__(self):
        self.docs = {}
        self.updates = []

    async def find_by_email(self, email):
        return next((u for u in self.docs.values() if u["email"] == email.lower()), None)

    async def insert(self, doc):
        self.docs[doc["_id"]] = doc

    async def update_one(self, query, update):
        self.updates.append((query, update))
        u = self.docs.get(query["_id"])
        if u and all(u.get(k) == v for k, v in query.items()):
            u.update(update.get("$set", {}))


class _Tokens:
    def __init__(self):
        self.rows = []

    async def replace_one(self, query, doc, upsert=False):
        self.rows = [r for r in self.rows if r["user_id"] != query["user_id"]]
        self.rows.append(dict(doc))

    async def delete_one(self, query):
        self.rows = [r for r in self.rows if r["token"] != query["token"]]

    async def find_one_and_delete(self, query):
        row = next((r for r in self.rows if r["token"] == query["token"]), None)
        if row:
            self.rows.remove(row)
        return row


@pytest.fixture
def env(monkeypatch):
    from app.services import auth_service

    users, tokens, sent = _Users(), _Tokens(), []

    async def fake_send(email, token):
        sent.append((email, token))
        return True

    monkeypatch.setattr(auth_service, "user_repo", users)
    monkeypatch.setattr(auth_service, "get_email_verification_col", lambda: tokens)
    monkeypatch.setattr(auth_service, "send_verification_email", fake_send)
    monkeypatch.setattr(settings, "email_verification_required", True)
    monkeypatch.setattr(settings, "smtp_user", "configured")
    return auth_service, users, tokens, sent


def _req(**kw):
    return RegisterRequest(**{"full_name": "Ayesha Khan", "email": "ayesha@example.com",
                              "password": "Str0ngPass", "accepted_terms": True, **kw})


@pytest.mark.asyncio
async def test_sign_up_without_accepting_the_terms_is_refused(env):
    svc, users, *_ = env
    with pytest.raises(AppValidationError, match="Terms and Privacy"):
        await svc.register(_req(accepted_terms=False))
    assert users.docs == {}


@pytest.mark.asyncio
async def test_sign_up_records_which_terms_were_accepted(env):
    svc, users, *_ = env
    doc = await svc.register(_req())
    consent = doc["terms_consent"]
    assert consent["terms_version"] == TERMS_VERSION
    assert consent["privacy_version"] == PRIVACY_VERSION
    assert isinstance(consent["accepted_at"], datetime)


@pytest.mark.asyncio
async def test_with_smtp_a_new_account_starts_unconfirmed(env):
    svc, *_ = env
    doc = await svc.register(_req())
    assert doc["email_verified"] is False and doc["email_verified_at"] is None


@pytest.mark.asyncio
async def test_without_smtp_a_new_account_is_not_locked_out(env, monkeypatch):
    svc, *_ = env
    monkeypatch.setattr(settings, "smtp_user", "")
    doc = await svc.register(_req())
    assert doc["email_verified"] is True


@pytest.mark.asyncio
async def test_unconfirmed_login_is_refused_only_after_the_password_is_right(env, monkeypatch):
    svc, users, *_ = env
    await svc.register(_req())
    async def _verify(pw, h):
        return pw == "Str0ngPass"
    monkeypatch.setattr(svc, "verify_password_async", _verify)

    with pytest.raises(AuthError):         # wrong password: says nothing about the account
        await svc.login("ayesha@example.com", "nope")
    with pytest.raises(ForbiddenError) as exc:
        await svc.login("ayesha@example.com", "Str0ngPass")
    assert exc.value.detail["code"] == "email_not_verified"


@pytest.mark.asyncio
async def test_the_link_is_stored_hashed_and_a_resend_replaces_it(env):
    svc, users, tokens, sent = env
    await svc.register(_req())
    await svc.send_email_verification("ayesha@example.com")
    await svc.send_email_verification("ayesha@example.com")
    assert len(sent) == 2 and len(tokens.rows) == 1
    raw = sent[-1][1]
    assert tokens.rows[0]["token"] != raw and tokens.rows[0]["token"].startswith("sha256:")


@pytest.mark.asyncio
async def test_no_link_for_unknown_or_confirmed_accounts(env):
    svc, users, tokens, sent = env
    await svc.send_email_verification("nobody@example.com")
    users.docs["old"] = {"_id": "old", "email": "old@example.com"}      # legacy: no field
    await svc.send_email_verification("old@example.com")
    assert sent == [] and tokens.rows == []


@pytest.mark.asyncio
async def test_a_failed_send_leaves_no_usable_link(env, monkeypatch):
    svc, users, tokens, sent = env
    await svc.register(_req())

    async def broken(email, token):
        raise OSError("smtp down")

    monkeypatch.setattr(svc, "send_verification_email", broken)
    await svc.send_email_verification("ayesha@example.com")   # logged, not raised
    assert tokens.rows == []


@pytest.mark.asyncio
async def test_the_link_confirms_once(env):
    svc, users, tokens, sent = env
    doc = await svc.register(_req())
    await svc.send_email_verification("ayesha@example.com")
    raw = sent[-1][1]

    await svc.verify_email(raw)
    assert users.docs[doc["_id"]]["email_verified"] is True
    with pytest.raises(AppValidationError, match="invalid or has expired"):
        await svc.verify_email(raw)


@pytest.mark.asyncio
async def test_an_expired_link_is_refused(env):
    svc, users, tokens, sent = env
    doc = await svc.register(_req())
    await svc.send_email_verification("ayesha@example.com")
    tokens.rows[0]["created_at"] = datetime.now(timezone.utc) - timedelta(hours=25)
    with pytest.raises(AppValidationError):
        await svc.verify_email(sent[-1][1])
    assert users.docs[doc["_id"]]["email_verified"] is False


@pytest.mark.asyncio
async def test_a_link_does_not_confirm_an_address_the_account_no_longer_has(env):
    svc, users, tokens, sent = env
    doc = await svc.register(_req())
    await svc.send_email_verification("ayesha@example.com")
    users.docs[doc["_id"]]["email"] = "changed@example.com"
    await svc.verify_email(sent[-1][1])
    assert users.docs[doc["_id"]]["email_verified"] is False


def test_production_refuses_verification_without_smtp():
    from pydantic import ValidationError

    from app.core.config import Settings

    base = dict(app_env="production", frontend_url="https://example.com", lawyer_auto_approve=False)
    with pytest.raises(ValidationError, match="EMAIL_VERIFICATION_REQUIRED"):
        Settings(**base, email_verification_required=True, smtp_user="")
    Settings(**base, email_verification_required=True, smtp_user="mailer")
    Settings(**base, email_verification_required=False, smtp_user="")
