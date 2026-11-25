/* "Your to-do" on a case (Tracking v2, 2026-11-23): only what the CLIENT can
 * move, each with one button. Built from real records: the hire request on
 * this case, fees requested on it, its documents that came back from the
 * lawyer or need sending again, meeting times the lawyer proposed, and
 * agreements on the case still waiting for the client's signature, and
 * appointment time changes the client must answer. An
 * empty list is a real answer ("nothing is waiting on you"), never padded.
 *
 * `action` is a name the page maps to a handler: "engagement", "pay",
 * "documents", "proposals", "agreements", "appointment". */
import { formatPkt } from "./bookingTime.js";
import { documentStatusView } from "./documentStatus.js";

const DUE = new Set(["created", "pending", "failed"]);
const day = iso => (iso ? formatPkt(iso, { day: "numeric", month: "short" }) : null);
const money = n => `PKR ${Number(n || 0).toLocaleString()}`;
const same = (a, b) => a != null && b != null && String(a) === String(b);

/** Appointment time choices the client can act on. `caseId: null` deliberately
 * means consultations that are not attached to a matter. */
export function appointmentTodos({ appointments = [], caseId = null, lawyerName = "Your lawyer" } = {}) {
    const out = [];
    const now = Date.now();
    (Array.isArray(appointments) ? appointments : [])
        .filter(a => a && (caseId == null ? a.case_id == null : same(a.case_id, caseId)))
        .forEach(a => {
            const who = a.lawyer_name || lawyerName;
            const suggestion = a.status === "pending" && Array.isArray(a.time_suggestion?.options)
                && a.time_suggestion.options.length ? a.time_suggestion : null;
            if (suggestion) {
                out.push({ key: `appt-suggestion-${a.id}`, warn: true, chip: "Waiting on you",
                    title: "Choose a consultation time",
                    sub: `${who} suggested ${suggestion.options.length} time${suggestion.options.length === 1 ? "" : "s"}`,
                    cta: "Review times", action: "appointment", id: a.id });
            }
            const move = a.status === "confirmed" && a.reschedule_proposal?.by === "lawyer"
                && (!a.reschedule_proposal.expires_at || new Date(a.reschedule_proposal.expires_at).getTime() > now)
                ? a.reschedule_proposal : null;
            if (move) {
                out.push({ key: `appt-move-${a.id}`, warn: true, chip: "Waiting on you",
                    title: "Answer the proposed new time",
                    sub: move.scheduled_at ? `${who} proposed ${formatPkt(move.scheduled_at, { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" })}` : `${who} proposed a new time`,
                    cta: "Review new time", action: "appointment", id: a.id });
            }
        });
    return out;
}

export function caseTodos({ caseId, engagement = null, feeText = "", payments = [], proposals = [], appointments = [], docs = [], agreements = [], userId = null } = {}) {
    if (!caseId) return [];
    const out = [];
    const e = engagement;
    const who = e?.lawyer_name || "Your lawyer";

    if (e?.status === "terms_proposed") {
        out.push({ key: `eng-${e.id}`, warn: true, chip: "Waiting on you", title: `Answer ${who}'s terms`,
            sub: feeText ? `${feeText} · nothing is agreed until you accept` : "Nothing is agreed until you accept",
            cta: "Review terms", action: "engagement", id: e.id, primary: true });
    }
    if (e?.status === "accepted" && e.completion_proposed_by === "lawyer") {
        out.push({ key: `done-${e.id}`, warn: true, chip: "Waiting on you", title: "Confirm the work is finished",
            sub: `${who} marked it complete${e.completion_proposed_at ? ` on ${day(e.completion_proposed_at)}` : ""}`,
            cta: "Review", action: "engagement", id: e.id });
    }
    (Array.isArray(payments) ? payments : [])
        .filter(p => p && same(p.case_id, caseId) && DUE.has(p.status))
        .sort((x, y) => new Date(x.expires_at || x.created_at || 0) - new Date(y.expires_at || y.created_at || 0))
        .forEach(p => out.push({
            key: `pay-${p.id}`, warn: true,
            chip: p.status === "failed" ? "Payment failed" : p.expires_at ? `Pay by ${day(p.expires_at)}` : "Fee due",
            title: `Pay the ${p.purpose === "peshi_fee" ? "appearance (peshi) fee" : "professional fee"}`,
            sub: [money(p.amount), p.created_at ? `requested ${day(p.created_at)}` : null].filter(Boolean).join(" · "),
            cta: p.status === "failed" ? "Try payment again" : "Pay now", action: "pay", id: p.id, primary: true,
        }));
    // An agreement on this case waiting for THIS client's signature (2026-11-23).
    // Only a pending agreement, and only when the unsigned party is the client.
    (Array.isArray(agreements) ? agreements : [])
        .filter(a => a && same(a.case_id, caseId) && a.status === "pending" && userId
            && (a.parties || []).some(p => p && same(p.user_id, userId) && !p.signed))
        .forEach(a => out.push({ key: `agr-${a.id || a._id}`, warn: true, chip: "Waiting on you",
            title: `Sign \u201c${a.title || "the agreement"}\u201d`,
            sub: a.total_parties ? `${a.signed_count || 0} of ${a.total_parties} have signed` : "Your signature is needed",
            cta: "Review & sign", action: "agreements", id: a.id || a._id }));
    (Array.isArray(docs) ? docs : []).forEach(d => {
        if (!d) return;
        const v = documentStatusView(d);
        const name = d.title || d.name || d.filename || "A document";
        if (v.isRecovery) {
            out.push({ key: `doc-${d.id}`, warn: true, chip: "Needs you", title: v.headline, sub: name,
                cta: "Open in Documents", action: "documents", id: d.id });
        } else if (d.review_status === "returned") {
            out.push({ key: `doc-${d.id}`, warn: false, chip: "From your lawyer", title: `Read "${name}"`,
                sub: "Your lawyer sent it back to you", cta: "Open in Documents", action: "documents", id: d.id });
        }
    });
    (Array.isArray(proposals) ? proposals : [])
        .filter(p => p && same(p.case_id, caseId) && p.status === "open")
        .forEach(p => out.push({ key: `prop-${p.id}`, warn: true, chip: "Waiting on you", title: "Choose a meeting time",
            sub: `${p.lawyer_name || who} proposed ${Array.isArray(p.options) && p.options.length ? `${p.options.length} time${p.options.length === 1 ? "" : "s"}` : "times"} to meet`,
            cta: "Choose a time", action: "proposals", id: p.id }));

    out.push(...appointmentTodos({ appointments, caseId, lawyerName: who }));

    // The first one that needs paying or answering leads.
    return out.map((t, i) => ({ ...t, primary: i === 0 }));
}
