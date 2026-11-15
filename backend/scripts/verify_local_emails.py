"""Mark existing accounts on the LOCAL demo database as email-confirmed (2026-10-18).

Email confirmation applies to accounts created from now on. Older accounts have
no `email_verified` field and can already sign in; this records them as
confirmed explicitly so the demo data is consistent. An account still waiting
on a real confirmation link (`email_verified: false`) is left alone, as are
closed accounts.

Only the local replica set is accepted (see approve_local_lawyers.local_only).

    python scripts/verify_local_emails.py            # dry run
    python scripts/verify_local_emails.py --apply    # writes
"""
import argparse
from datetime import datetime, timezone

from pymongo import MongoClient

from approve_local_lawyers import DEFAULT_DB, DEFAULT_URL, local_only


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    args = ap.parse_args()

    local_only(args.url)
    users = MongoClient(args.url, serverSelectionTimeoutMS=3000)[args.db]["users"]
    query = {"email_verified": {"$exists": False}, "is_closed": {"$ne": True}}
    found = list(users.find(query, {"role": 1, "email": 1}))
    for u in found:
        print(f"  {u.get('role', '?'):<7} {u.get('email')}")
    print(f"{len(found)} account(s) to mark confirmed; "
          f"{users.count_documents({'email_verified': False})} waiting on a link left alone.")
    if not args.apply:
        print("Dry run. Nothing written. Re-run with --apply.")
        return
    if found:
        now = datetime.now(timezone.utc)
        result = users.update_many(
            {"_id": {"$in": [u["_id"] for u in found]}, **query},
            {"$set": {"email_verified": True, "email_verified_at": now}},
        )
        print(f"Marked {result.modified_count}.")


if __name__ == "__main__":
    main()
