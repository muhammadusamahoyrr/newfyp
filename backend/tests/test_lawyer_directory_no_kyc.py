"""The public lawyer view carries no KYC data (audit 2026-11-22, low #1).

The shared sanitizer keeps lawyer_profile.kyc_* for the lawyer's OWN profile;
the directory/matching view leaked uploaded KYC file names, an admin's
rejection reason and erasure bookkeeping to every client.
"""
from app.services import lawyer_service, user_service

LAWYER = {
    "_id": "l1", "role": "lawyer", "full_name": "Adv Test", "password_hash": "x",
    "lawyer_profile": {
        "bar_number": "LHC/1/2026", "specializations": ["civil"],
        "kyc_status": "rejected", "kyc_verified": False,
        "kyc_rejection_reason": "CNIC photo is blurred",
        "kyc_documents": [{"filename": "my-cnic-front.jpg"}],
        "kyc_erasure_pending": True,
        "specialization_embedding": [0.1] * 4,
    },
}


def test_public_view_has_no_kyc_fields():
    out = lawyer_service._sanitize(LAWYER)
    lp = out["lawyer_profile"]
    assert not [k for k in lp if k.startswith("kyc_")]
    assert lp["bar_number"] == "LHC/1/2026" and lp["specializations"] == ["civil"]
    assert "password_hash" not in out and "specialization_embedding" not in lp


def test_the_lawyers_own_profile_still_has_them():
    own = user_service._sanitize(LAWYER)["lawyer_profile"]
    assert own["kyc_rejection_reason"] == "CNIC photo is blurred"
    assert own["kyc_documents"][0]["filename"] == "my-cnic-front.jpg"


def test_the_input_is_not_mutated():
    lawyer_service._sanitize(LAWYER)
    assert "kyc_documents" in LAWYER["lawyer_profile"]
