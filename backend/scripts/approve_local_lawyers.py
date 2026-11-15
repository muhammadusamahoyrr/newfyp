"""Approve existing pending lawyers on the LOCAL demo database (2026-10-18).

LAWYER_AUTO_APPROVE approves new lawyer accounts at creation. Accounts made
before it still sit in the admin KYC queue; this script brings them in line.

Only the local replica set is accepted (127.0.0.1 / localhost). Hosted
databases (Atlas, mongodb+srv) are refused before any connection is made.

Approved: active lawyers whose kyc_status is pending or missing AND whose
profile is complete (bar number + at least one practice area), the same rule
the directory uses. Rejected accounts are left alone. Nothing is checked about
the Bar license, so nothing here should be described as verification.

    python scripts/approve_local_lawyers.py            # dry run: lists who
    python scripts/approve_local_lawyers.py --apply    # writes
"""
import argparse
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

from pymongo import MongoClient

DEFAULT_URL = "mongodb://127.0.0.1:27018/?replicaSet=rs0"
DEFAULT_DB = "attorney_ai_local"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}

PENDING = {"$or": [
    {"lawyer_profile.kyc_status": "pending"},
    {"lawyer_profile.kyc_status": {"$exists": False}},
    {"lawyer_profile.kyc_status": None},
]}
COMPLETE = [
    {"lawyer_profile.bar_number": {"$type": "string", "$regex": r"\S"}},
    {"lawyer_profile.specializations.0": {"$exists": True}},
]


def local_only(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "mongodb":
        sys.exit(f"Refusing: only mongodb:// on this machine is allowed (got {parsed.scheme}://).")
    hosts = [h.rsplit(":", 1)[0].strip("[]") for h in parsed.netloc.rsplit("@", 1)[-1].split(",")]
    if not hosts or any(h not in LOCAL_HOSTS for h in hosts):
        sys.exit("Refusing: the database is not on this machine.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    args = ap.parse_args()

    local_only(args.url)
    users = MongoClient(args.url, serverSelectionTimeoutMS=3000)[args.db]["users"]
    query = {
        "role": "lawyer",
        "is_active": True,
        "lawyer_profile.kyc_verified": {"$ne": True},
        "$and": [PENDING, *COMPLETE],
    }
    found = list(users.find(query, {"full_name": 1, "email": 1, "lawyer_profile.bar_number": 1}))
    for u in found:
        print(f"  {u['_id']}  {u.get('full_name')!s:<28} {u.get('email')}")
    skipped = users.count_documents({
        "role": "lawyer", "lawyer_profile.kyc_verified": {"$ne": True},
    }) - len(found)
    print(f"{len(found)} to approve; {skipped} other unapproved lawyer(s) left alone "
          "(inactive, rejected or incomplete profile).")

    if not args.apply:
        print("Dry run. Nothing written. Re-run with --apply.")
        return
    if not found:
        return
    now = datetime.now(timezone.utc)
    result = users.update_many(
        {"_id": {"$in": [u["_id"] for u in found]}, **query},
        {"$set": {
            "lawyer_profile.kyc_verified": True,
            "lawyer_profile.kyc_status": "approved",
            "lawyer_profile.kyc_rejection_reason": None,
            "updated_at": now,
        }},
    )
    print(f"Approved {result.modified_count}.")


if __name__ == "__main__":
    main()
