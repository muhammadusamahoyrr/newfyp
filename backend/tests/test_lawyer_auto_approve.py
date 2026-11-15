"""LAWYER_AUTO_APPROVE (demo policy, 2026-10-18).

New lawyer accounts are approved at creation instead of waiting in the admin
KYC queue. Approval then comes BEFORE onboarding, so the directory and the
matcher must hide a profile until it has a bar number and a practice area.
"""
import pytest

from app.core.config import settings
from app.core.constants import KycStatus
from app.repositories.user_repo import UserRepository
from app.schemas.auth import RegisterRequest


class _Repo:
    def __init__(self):
        self.inserted = []

    async def find_by_email(self, email):
        return None

    async def insert(self, doc):
        self.inserted.append(doc)


@pytest.fixture
def repo(monkeypatch):
    from app.services import admin_service, auth_service

    r = _Repo()
    monkeypatch.setattr(auth_service, "user_repo", r)
    monkeypatch.setattr(admin_service, "user_repo", r)

    async def no_audit(*a, **k):
        return None

    monkeypatch.setattr(admin_service, "_audit", no_audit)
    return r


def _register(role):
    return RegisterRequest(full_name="Ayesha Khan", email=f"{role}@example.com",
                           password="Str0ngPass", role=role, accepted_terms=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("auto, verified, status", [
    (True, True, KycStatus.APPROVED.value),
    (False, False, KycStatus.PENDING.value),
])
async def test_registration_follows_the_setting(repo, monkeypatch, auto, verified, status):
    from app.services import auth_service

    monkeypatch.setattr(settings, "lawyer_auto_approve", auto)
    await auth_service.register(_register("lawyer"))
    lp = repo.inserted[-1]["lawyer_profile"]
    assert lp["kyc_verified"] is verified and lp["kyc_status"] == status
    # Approval does not invent a profile: onboarding still has to fill these.
    assert lp["bar_number"] is None and lp["specializations"] == []


@pytest.mark.asyncio
async def test_client_registration_has_no_lawyer_profile(repo, monkeypatch):
    from app.services import auth_service

    monkeypatch.setattr(settings, "lawyer_auto_approve", True)
    await auth_service.register(_register("client"))
    assert repo.inserted[-1]["lawyer_profile"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("auto, verified", [(True, True), (False, False)])
async def test_admin_created_lawyer_follows_the_setting(repo, monkeypatch, auto, verified):
    from app.services import admin_service

    monkeypatch.setattr(settings, "lawyer_auto_approve", auto)
    await admin_service.create_user("Bilal Ahmed", "bilal@example.com", "lawyer", "Str0ngPass")
    assert repo.inserted[-1]["lawyer_profile"]["kyc_verified"] is verified


def test_directory_requires_a_complete_profile():
    f = UserRepository.lawyer_filter()
    assert {"lawyer_profile.specializations.0": {"$exists": True}} in f["$and"]
    bar = next(c for c in f["$and"] if "lawyer_profile.bar_number" in c)
    assert bar["lawyer_profile.bar_number"]["$type"] == "string"


def test_completeness_does_not_collide_with_search_filters():
    """Bar-number search and the practice-area filter set their own keys on the
    same fields; the completeness rule must survive alongside them."""
    f = UserRepository.lawyer_filter(bar_number="LHC", specialization="family", q="ali")
    assert f["lawyer_profile.bar_number"]["$regex"] == "LHC"
    assert f["lawyer_profile.specializations"] == "family"
    assert len(f["$and"]) == 3                      # 2 completeness + text search
    assert {"lawyer_profile.specializations.0": {"$exists": True}} in f["$and"]


@pytest.mark.parametrize("profile, listable", [
    ({"bar_number": "LHC-2016-7821", "specializations": ["family"]}, True),
    ({"bar_number": None, "specializations": ["family"]}, False),
    ({"bar_number": "   ", "specializations": ["family"]}, False),
    ({"bar_number": "LHC-2016-7821", "specializations": []}, False),
    ({}, False),
])
def test_matcher_uses_the_same_completeness_rule(profile, listable):
    from app.services.lawyer_service import _has_listable_profile

    assert _has_listable_profile({"lawyer_profile": profile}) is listable


@pytest.mark.asyncio
async def test_semantic_hit_still_onboarding_is_skipped_not_deleted(monkeypatch):
    """An approved lawyer without a profile yet is not a ghost row: removing it
    from the vector store would only make the reconcile sweep re-add it."""
    from app.services import lawyer_service

    hits = [{"lawyer_id": "a", "semantic_score": 0.9},
            {"lawyer_id": "b", "semantic_score": 0.8}]
    docs = [
        {"_id": "a", "role": "lawyer", "is_active": True,
         "lawyer_profile": {"kyc_verified": True, "bar_number": "LHC-1", "specializations": ["family"]}},
        {"_id": "b", "role": "lawyer", "is_active": True,
         "lawyer_profile": {"kyc_verified": True, "bar_number": None, "specializations": []}},
    ]
    removed = []

    async def fake_find_many(query, *a, **k):
        return docs

    monkeypatch.setattr(lawyer_service.user_repo, "find_many", fake_find_many)
    import app.ai.lawyer_embeddings as emb

    async def fake_query(**k):
        return hits

    monkeypatch.setattr(emb, "query_similar_lawyers", fake_query)
    monkeypatch.setattr(emb, "forget_lawyers", lambda ids: removed.extend(ids))
    out = await lawyer_service._semantic_candidates("custody of children", "punjab", 10)
    assert list(out) == ["a"]
    assert "b" not in removed


def test_production_refuses_auto_approve():
    """Demo-only policy: a production config must run the admin KYC queue."""
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError, match="LAWYER_AUTO_APPROVE"):
        Settings(app_env="production", frontend_url="https://example.com",
                 lawyer_auto_approve=True)
    Settings(app_env="production", frontend_url="https://example.com",
             lawyer_auto_approve=False, smtp_user="mailer")


@pytest.mark.asyncio
@pytest.mark.parametrize("module", ["appointment_service", "engagement_service"])
async def test_booking_gates_refuse_an_auto_approved_unfinished_profile(monkeypatch, module):
    """Approved at sign-up is not listed: an id from outside the directory
    must not reach a lawyer who has not finished onboarding."""
    import importlib

    from app.core.exceptions import AppValidationError
    from app.services.auth_service import initial_kyc_fields

    monkeypatch.setattr(settings, "lawyer_auto_approve", True)
    svc = importlib.import_module(f"app.services.{module}")
    lawyer = {"_id": "L1", "role": "lawyer", "is_active": True,
              "lawyer_profile": {**initial_kyc_fields(), "bar_number": None, "specializations": []}}

    async def find_by_id(_id):
        return lawyer

    monkeypatch.setattr(svc.user_repo, "find_by_id", find_by_id)
    with pytest.raises(AppValidationError, match="not finished"):
        await svc._get_verified_lawyer("L1")
    lawyer["lawyer_profile"].update(bar_number="LHC-1", specializations=["family"])
    assert (await svc._get_verified_lawyer("L1"))["_id"] == "L1"
