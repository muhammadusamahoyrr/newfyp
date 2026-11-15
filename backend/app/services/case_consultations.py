"""The consultations behind a case and a hire request (2026-10-20, Batch D).

ONLY STORED LINKS, NEVER GUESSES. The consultation a hire request followed is
the engagement's own `appointment_id` (written when the client asked, §17
R5-1). Nothing here matches a client and a date to find "probably that one":
a legacy engagement without the field, or one whose appointment is gone, is
reported as unavailable rather than filled with a nearby meeting.

A case's own meetings are the appointments whose `case_id` is that case (booked
for it, or confirmed from a meeting proposal on it), with that case's lawyer.
A client's other appointments are not part of the case and are not listed.

Rows are the few fields the UI shows; nothing private (the lawyer's notes stay
on the appointment page).
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.core.exceptions import ForbiddenError, NotFoundError
from app.db.collections import get_appointments_col, get_cases_col, get_engagements_col

_FIELDS = {"scheduled_at": 1, "end_at": 1, "duration_minutes": 1, "mode": 1, "status": 1, "notes": 1,
           "client_id": 1, "lawyer_id": 1, "case_id": 1}
_LINKED_LIMIT = 50


def _iso(v):
    """An instant WITH its offset: Mongo hands back naive UTC, which a browser
    would read as local time."""
    if not isinstance(v, datetime):
        return None
    return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()


def row(a: dict) -> dict:
    return {"id": str(a["_id"]), "scheduled_at": _iso(a.get("scheduled_at")), "end_at": _iso(a.get("end_at")),
            "duration_minutes": a.get("duration_minutes"), "mode": a.get("mode"),
            "status": a.get("status"), "note": a.get("notes") or ""}


async def consultations_for(engagements: list[dict]) -> dict[str, dict | None]:
    """engagement id -> its consultation row, or None when unavailable.

    One read for all of them. An appointment counts only if it is between the
    engagement's own client and lawyer -- a stored id pointing elsewhere is
    treated as unavailable, not shown."""
    ids = {e.get("appointment_id") for e in engagements if e.get("appointment_id")}
    found = {}
    if ids:
        async for a in get_appointments_col().find({"_id": {"$in": list(ids)}}, _FIELDS):
            found[a["_id"]] = a
    out = {}
    for e in engagements:
        a = found.get(e.get("appointment_id"))
        ok = a is not None and a.get("client_id") == e.get("client_id") and a.get("lawyer_id") == e.get("lawyer_id")
        out[str(e.get("_id") or e.get("id"))] = row(a) if ok else None
    return out


async def for_case(case_id: str, lawyer_id: str) -> dict:
    """The case's originating consultation and its own linked meetings, for
    the lawyer the case is assigned to."""
    case = await get_cases_col().find_one({"_id": case_id}, {"lawyer_id": 1, "client_id": 1})
    if not case:
        raise NotFoundError("Case")
    if case.get("lawyer_id") != lawyer_id:
        raise ForbiddenError("This case is not assigned to you")

    # The hire that gave this lawyer the case: the accepted engagement, else
    # the newest one between them on this case.
    eng = None
    async for e in get_engagements_col().find(
            {"case_id": case_id, "lawyer_id": lawyer_id},
            {"appointment_id": 1, "client_id": 1, "lawyer_id": 1, "status": 1, "created_at": 1}
    ).sort([("created_at", -1), ("_id", -1)]).limit(20):
        if eng is None or (e.get("status") == "accepted" and eng.get("status") != "accepted"):
            eng = e
    originating = (await consultations_for([eng]))[str(eng["_id"])] if eng else None

    linked = [row(a) async for a in get_appointments_col().find(
        {"case_id": case_id, "lawyer_id": lawyer_id}, _FIELDS,
    ).sort([("scheduled_at", -1), ("_id", -1)]).limit(_LINKED_LIMIT)]
    if originating:
        linked = [r for r in linked if r["id"] != originating["id"]]

    return {
        "originating": originating,
        # A hire with no usable stored link (legacy, or the record is gone).
        # A walk-in case has no hire at all: then it is simply absent.
        "originating_unavailable": bool(eng) and originating is None,
        "has_hire": bool(eng),
        "linked": linked,
    }
