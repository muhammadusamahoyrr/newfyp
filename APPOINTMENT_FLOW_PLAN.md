# Appointment flow plan (2026-10-19)

Appointments = meetings, Cases = legal work, Clients = relationship index.
Every action lives on ONE page; the others only link to it.

## Locked rules

### Access and privacy
- Pending appointment: the lawyer sees the client's name, booking note, category and proposed time.
- Confirmed appointment: the lawyer may open documents the client explicitly uploaded TO THAT APPOINTMENT.
  (Supersedes the 2026-10-19 "file names visible while pending" rule — to be applied in Marhala 2;
  the per-file "show before accept" opt-in stays, off by default.)
- Case / AI intake summary: only through a separate, explicit client share (Marhala 2):
  preview + edit before sharing, sensitive identifiers (CNIC, phone, address) redacted by default,
  a SNAPSHOT is stored at share time (a regenerated summary never reaches the lawyer automatically).
- Revoking a share removes FUTURE in-app access at once; copies already viewed/downloaded cannot be
  recalled, and the UI says so. Shares and revocations are audit-logged.
- "About this client": only THIS lawyer's appointments with THIS client — never other lawyers'.
- Every document/case read is authorised on the backend; hiding a button is never the control.
- A lawyer without access to a case is never offered "Open case".

### Rescheduling a CONFIRMED appointment (Marhala 1)
- Either party may propose ONE new time; at most one active proposal per appointment.
- The confirmed time stays in force until the other party accepts.
- The proposer can withdraw; the other party can decline; a proposal expires (at the latest when the
  current time starts, or 48h after it was made).
- Accept re-checks availability atomically (unique slot indexes + schedule_version CAS + proposal id);
  on any conflict the appointment is left unchanged.
- Accept bumps schedule_version, so reminder ids (which carry the version) are new for the new time.
- Times are stored in UTC; the UI shows PKT.

### Outcomes (Marhala 1)
- An ended appointment is never auto-completed; it goes to "Needs outcome".
- Outcomes: Completed · Client didn't attend (no_show) · Lawyer couldn't attend · Didn't take place.
  The last two are recorded as CANCELLED (from confirmed) with an `outcome_code`
  (`lawyer_no_show` / `did_not_take_place`) — no new status, the client is never blamed.
- An ended appointment is not shown as "Upcoming".

### Separation
- Appointment chat and case messages are separate threads on the backend (already true).
- Appointment documents stay on the appointment; moving one into a case is an explicit "Add to case".
- Completing an appointment never creates a case; a case is created only by an accepted engagement.
- Clients page statuses: Appointment requested · Consultation scheduled · Consultation completed ·
  Engaged · Closed — computed from source records, nothing duplicated or editable.

### Video (Marhala 3, Daily.co)
- API key only on the backend (demo overlay env), never in the browser or chat.
- Short-lived meeting tokens issued at Join; cancel/reschedule expires old access.
- Recording and transcription OFF.
- Usage guard: a monthly minutes budget the server refuses to exceed, plus a usage alert —
  Daily keeps billing past the free allowance.

## Order
1. Access/privacy rules + backend authorisation
2. Marhala 1: confirmed reschedule proposals, outcomes, Needs-outcome display, Open-case dead end, labels
3. Marhala 2: sharing (preview, redaction, snapshot, revoke, audit), document visibility rule
4. Marhala 3: Daily video + durable reminders
5. Marhala 4: Clients page aggregation

## Marhala 3 — built 2026-10-19 (uncommitted)
- `services/appointment_video.py` + routes `/appointment-video/{id}` (status) and `/{id}/join`.
  Private room per appointment + schedule version (opaque name), created at first Join;
  token = min(end + 15 min, now + 2 h), lawyer is owner; Join only for a confirmed video
  appointment, from 10 min before start to 15 min after end. Cancel and an accepted move
  delete the room (best-effort, never fails the cancel). No recording/transcription set.
- Budget: `DAILY_MONTHLY_MINUTES_BUDGET` (default 8000 participant-minutes); each Join
  reserves its token's minutes once per person per version, atomically; refused past the
  budget; warning logged at 80%.
- No `DAILY_API_KEY` -> the Join button does not render; paste-a-link stays as before.
- UI: `components/shared/VideoJoin.jsx` (iframe call + Leave) in the client appointment
  detail and the lawyer Join-call dialog.
- Reminders: on in the demo overlay (`APPOINTMENT_REMINDERS_ENABLED`, plus
  `SCHEDULER_SINGLE_PROCESS` = in-process lock because the demo has no Redis). A video
  appointment with no link and no in-app video gets "no meeting link yet" in its reminder.
- To use real video: the user adds `DAILY_API_KEY=` to `backend/.env.analyzer-demo.local`.

## Marhala 4 — built 2026-10-19 (uncommitted)
- `services/lawyer_clients.py` + `GET /lawyer-clients` (lawyer only): stage per client computed
  from THIS lawyer's appointments and cases, first match wins — Engaged (open case) ·
  Consultation scheduled (confirmed) · Appointment requested (pending) · Consultation
  completed · Closed (only finished cases). Only-cancelled/expired/no-show clients are not listed.
  Email only for engaged clients. Counts, next appointment, needs-outcome, cases list.
- `lawyer/ClientsPage.jsx` rebuilt: stage chips with server totals, search, error + retry.
  Actions: Engaged → Message (case) + Suggest a meeting (existing case proposal dialog,
  books nothing); requested/scheduled/completed → opens that appointment; Closed → Open case.
