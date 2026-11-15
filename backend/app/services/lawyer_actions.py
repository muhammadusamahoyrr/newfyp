"""What is waiting on the lawyer, counted ONCE (2026-10-20).

The Dashboard, the Appointments page and the Clients page each used to count
this their own way and disagreed: the dashboard's "upcoming" was every
pending + confirmed row with no time filter (a meeting that had ended still
counted), a meeting waiting for its outcome counted as nothing to do, and hire
requests were not read at all. Every surface now reads these numbers from here.

  appointment_requests  pending requests the lawyer can still answer
                        (not past their answer-by time)
  outcomes_to_record    confirmed meetings whose end time has passed. NO grace:
                        the action is shown the moment the meeting ends. The
                        two-hour grace in `appointment_outcomes` is for
                        reminders only, so a meeting that runs late is not nagged.
  hire_requests         engagements `requested` -- the lawyer owes terms
  upcoming              confirmed meetings that have not ended yet

  waiting_for_client    engagements `terms_proposed`. Reported, but it is NOT a
                        lawyer action: the client owes the answer.

`next` holds the oldest item of each action queue, so a button can open the
one to do first.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.db.collections import get_appointments_col, get_engagements_col

ACTION_KEYS = ("appointment_requests", "outcomes_to_record", "hire_requests")


async def _oldest(col, query: dict, sort_field: str) -> str | None:
    row = await col.find_one(query, {"_id": 1}, sort=[(sort_field, 1), ("_id", 1)])
    return str(row["_id"]) if row else None


def queries(lawyer_id: str, now: datetime) -> dict:
    """THE predicates, as database filters. The Clients index groups the same
    filters by client, so a card can never disagree with these counts.
    Keys: requests, outcomes, upcoming (appointments); hire, waiting (engagements)."""
    return {
        "requests": {"lawyer_id": lawyer_id, "status": "pending",
                     "$or": [{"expires_at": None}, {"expires_at": {"$gt": now}}]},
        "outcomes": {"lawyer_id": lawyer_id, "status": "confirmed", "end_at": {"$lt": now}},
        "upcoming": {"lawyer_id": lawyer_id, "status": "confirmed", "end_at": {"$gte": now}},
        "hire": {"lawyer_id": lawyer_id, "status": "requested"},
        "waiting": {"lawyer_id": lawyer_id, "status": "terms_proposed"},
    }


async def action_counts(lawyer_id: str, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    appts, engs = get_appointments_col(), get_engagements_col()

    q = queries(lawyer_id, now)
    q_requests, q_outcomes, q_upcoming, q_hire, q_waiting = (
        q["requests"], q["outcomes"], q["upcoming"], q["hire"], q["waiting"])

    counts = {
        "appointment_requests": await appts.count_documents(q_requests),
        "outcomes_to_record": await appts.count_documents(q_outcomes),
        "hire_requests": await engs.count_documents(q_hire),
        "upcoming": await appts.count_documents(q_upcoming),
        "waiting_for_client": await engs.count_documents(q_waiting),
    }
    return {
        **counts,
        "to_do": sum(counts[k] for k in ACTION_KEYS),
        "next": {
            "appointment_request": await _oldest(appts, q_requests, "scheduled_at") if counts["appointment_requests"] else None,
            "outcome": await _oldest(appts, q_outcomes, "end_at") if counts["outcomes_to_record"] else None,
            "hire_request": await _oldest(engs, q_hire, "created_at") if counts["hire_requests"] else None,
        },
        "as_of": now,
    }
