"""The lawyer's Clients page: an INDEX computed from the source records
(2026-10-19, APPOINTMENT_FLOW_PLAN.md, Marhala 4; reworked 2026-10-20, Batch C).

Nothing here is stored or editable. Every field is derived, every time, from
this lawyer's appointments, cases and hire requests (engagements).

TWO THINGS, KEPT APART.

  `stage`        the RELATIONSHIP, one of STAGES. The first that applies wins:
                   Engaged                 an open case assigned to this lawyer
                   Hire request            asked to take a case (requested, or
                                           terms sent and awaiting the client)
                   Consultation scheduled  a confirmed meeting (upcoming, or
                                           ended and waiting for its outcome)
                   Appointment requested   a pending request still answerable
                   Closed                  cases with this lawyer, all finished
                   Consultation completed  only completed consultations
  `next_action`  the ONE thing the lawyer should do next, whatever the stage:
                   send_terms > record_outcome > answer_request >
                   view_appointment (next one) > open_case
                 and `pending`, every piece of waiting work, so the card can show
                 the rest as chips instead of hiding them behind the primary one.

An Engaged client can still have a meeting waiting for its outcome; a client
with a hire request can still have a new appointment request. The stage says
where the relationship is; the action says what to do.

THE PREDICATES ARE `lawyer_actions.queries`, the same filters the Dashboard
and the Appointments tabs count with, grouped here by client. Terms already
sent (`terms_proposed`) are NOT a lawyer action: the client owes the answer, so
it is `waiting_for_client`.

A client whose only history with this lawyer is a declined, cancelled, expired
or no-show request is not listed: there is no relationship to show.

PRIVACY. Only this lawyer's own rows are read. Cases listed are the ones the
lawyer can open (assigned to them). A prospective client's email is not shown:
contact details belong to an engagement, not to a booking.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.db.collections import (
    get_appointments_col, get_cases_col, get_engagements_col, get_users_col,
)
from app.services.lawyer_actions import queries

ENGAGED = "Engaged"
HIRE = "Hire request"
SCHEDULED = "Consultation scheduled"
REQUESTED = "Appointment requested"
CLOSED = "Closed"
COMPLETED = "Consultation completed"
STAGES = (ENGAGED, HIRE, SCHEDULED, REQUESTED, CLOSED, COMPLETED)

_CLOSED_CASE = {"closed", "dismissed"}
_LIMIT = 2000


def _utc(v):
    if not isinstance(v, datetime):
        return None
    return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def stage_of(rec: dict) -> str | None:
    if any(str(c.get("status")) not in _CLOSED_CASE for c in rec["cases"]):
        return ENGAGED
    if rec["hire"] or rec["waiting"]:
        return HIRE
    if rec["outcomes"] or rec["upcoming"]:
        return SCHEDULED
    if rec["requests"]:
        return REQUESTED
    if rec["cases"]:
        return CLOSED
    if rec["completed"]:
        return COMPLETED
    return None


def next_action(t: dict) -> dict | None:
    """The one primary step, by the agreed priority, with its exact target."""
    for kind, key in (("send_terms", "engagement_id"), ("record_outcome", "outcome_appointment_id"),
                      ("answer_request", "pending_appointment_id"), ("view_appointment", "next_appointment_id"),
                      ("open_case", "case_id")):
        if t.get(key):
            return {"kind": kind, "target_id": t[key]}
    return None


async def list_clients(lawyer_id: str, now: datetime | None = None) -> dict:
    now = _utc(now) or datetime.now(timezone.utc)
    q = queries(lawyer_id, now)
    appts_col, engs_col = get_appointments_col(), get_engagements_col()
    keep = {"client_id": 1, "status": 1, "scheduled_at": 1, "end_at": 1, "expires_at": 1, "mode": 1, "created_at": 1}

    async def rows(col, query, sort):
        return [r async for r in col.find(query, keep).sort(sort).limit(_LIMIT)]

    groups = {
        "requests": await rows(appts_col, q["requests"], [("expires_at", 1), ("scheduled_at", 1), ("_id", 1)]),
        "outcomes": await rows(appts_col, q["outcomes"], [("end_at", 1), ("_id", 1)]),
        "upcoming": await rows(appts_col, q["upcoming"], [("scheduled_at", 1), ("_id", 1)]),
        "completed": await rows(appts_col, {"lawyer_id": lawyer_id, "status": "completed"}, [("scheduled_at", -1), ("_id", 1)]),
        "hire": await rows(engs_col, q["hire"], [("created_at", 1), ("_id", 1)]),
        "waiting": await rows(engs_col, q["waiting"], [("created_at", 1), ("_id", 1)]),
    }
    cases = [c async for c in get_cases_col().find(
        {"lawyer_id": lawyer_id},
        {"client_id": 1, "status": 1, "title": 1, "case_number": 1, "province": 1,
         "case_type": 1, "created_at": 1, "updated_at": 1},
    ).limit(_LIMIT)]

    by_client: dict[str, dict] = {}

    def rec_for(cid):
        return by_client.setdefault(str(cid), {k: [] for k in (*groups, "cases")})

    for key, items in groups.items():
        for r in items:          # already in each queue's own order
            if r.get("client_id"):
                rec_for(r["client_id"])[key].append(r)
    for c in cases:
        if c.get("client_id"):
            rec_for(c["client_id"])["cases"].append(c)

    users = {}
    if by_client:
        async for u in get_users_col().find(
                {"_id": {"$in": list(by_client)}}, {"full_name": 1, "email": 1, "province": 1}):
            users[str(u["_id"])] = u

    first_id = lambda xs: str(xs[0]["_id"]) if xs else None
    items = []
    for cid, rec in by_client.items():
        stage = stage_of(rec)
        if stage is None:
            continue
        user = users.get(cid, {})
        open_cases = sorted((c for c in rec["cases"] if str(c.get("status")) not in _CLOSED_CASE),
                            key=lambda c: _utc(c.get("updated_at") or c.get("created_at")) or now, reverse=True)
        all_cases = sorted(rec["cases"], key=lambda c: _utc(c.get("updated_at") or c.get("created_at")) or now, reverse=True)
        preferred_case = (open_cases or all_cases or [None])[0]
        targets = {
            "engagement_id": first_id(rec["hire"]),
            "outcome_appointment_id": first_id(rec["outcomes"]),
            "pending_appointment_id": first_id(rec["requests"]),
            "next_appointment_id": first_id(rec["upcoming"]),
            "case_id": str(preferred_case["_id"]) if preferred_case else None,
            "case_number": preferred_case.get("case_number") if preferred_case else None,
            "waiting_engagement_id": first_id(rec["waiting"]),
        }
        # Where "Message" goes: an engaged client's case Messages tab; a
        # prospective client's appointment chat (the next meeting, else the
        # one waiting for its outcome, else the latest held). None before any
        # meeting is confirmed -- a pending request has no chat yet.
        if open_cases:
            message = {"kind": "case", "target_id": targets["case_id"], "case_number": targets["case_number"]}
        else:
            thread = targets["next_appointment_id"] or targets["outcome_appointment_id"] or first_id(rec["completed"])
            message = {"kind": "appointment", "target_id": thread} if thread else None

        dated = rec["requests"] + rec["outcomes"] + rec["upcoming"] + rec["completed"]
        dates = [d for d in ([_utc(a.get("scheduled_at")) for a in dated]
                             + [_utc(c.get("updated_at") or c.get("created_at")) for c in rec["cases"]]) if d]
        first = [d for d in ([_utc(a.get("scheduled_at")) for a in dated]
                             + [_utc(c.get("created_at")) for c in rec["cases"]]) if d]
        engaged = bool(rec["cases"])
        nxt = rec["upcoming"][0] if rec["upcoming"] else None
        items.append({
            "client_id": cid,
            "name": (user.get("full_name") or "").strip() or "Client",
            # Contact details come with an engagement, not with a booking.
            "email": user.get("email") if engaged else None,
            "province": next((c.get("province") for c in rec["cases"] if c.get("province")), None)
                        or user.get("province"),
            "stage": stage,
            "next_action": next_action(targets),
            "pending": {
                "hire_requests": len(rec["hire"]),
                "outcomes": len(rec["outcomes"]),
                "appointment_requests": len(rec["requests"]),
            },
            "waiting_for_client": len(rec["waiting"]),
            "targets": targets,
            "message": message,
            "counts": {
                "requests": len(rec["requests"]),
                "upcoming": len(rec["upcoming"]),
                "consultations": len(rec["completed"]),
                "open_cases": len(open_cases),
                "closed_cases": len(rec["cases"]) - len(open_cases),
            },
            "needs_outcome": bool(rec["outcomes"]),
            "next_appointment": ({"id": str(nxt["_id"]), "at": nxt.get("scheduled_at"), "mode": nxt.get("mode")}
                                 if nxt else None),
            "latest_appointment_id": (str(max(dated, key=lambda a: _utc(a.get("scheduled_at")) or now)["_id"])
                                      if dated else None),
            "pending_request_id": targets["pending_appointment_id"],
            "cases": [{"id": str(c["_id"]), "case_number": c.get("case_number"), "title": c.get("title") or "Untitled case",
                       "status": c.get("status")}
                      for c in sorted(rec["cases"], key=lambda c: _utc(c.get("created_at")) or now, reverse=True)],
            "since": min(first) if first else None,
            "last_activity": max(dates) if dates else None,
        })

    order = {s: i for i, s in enumerate(STAGES)}
    items.sort(key=lambda x: (order[x["stage"]], -(x["last_activity"].timestamp() if x["last_activity"] else 0)))
    totals = {s: sum(1 for x in items if x["stage"] == s) for s in STAGES}
    return {"items": items, "totals": totals, "total": len(items)}
