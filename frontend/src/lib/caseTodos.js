/* "Your to-do" on a case (Tracking v2, 2026-11-23): only what the CLIENT can
 * move, each with one button. Built from real records: the hire request on
 * this case, fees requested on it, its documents that came back from the
 * lawyer or need sending again, and meeting times the lawyer proposed. An
 * empty list is a real answer ("nothing is waiting on you"), never padded.
 *
 * `action` is a name the page maps to a handler: "engagement", "pay",
 * "documents", "proposals". */
import { formatPkt } from "./bookingTime.js";
import { documentStatusView } from "./documentStatus.js";

const DUE = new Set(["created", "pending"]);
const day = iso => (iso ? formatPkt(iso, { day: "numeric", month: "short" }) : null);
const money = n => `PKR ${Number(n || 0).toLocaleString()}`;
const same = (a, b) => a != null && b != null && String(a) === String(b);

export function caseTodos({ caseId, engagement = null, feeText = "", payments = [], proposals = [], docs = [] } = {}) {
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
            chip: p.expires_at ? `Pay by ${day(p.expires_at)}` : "Fee due",
            title: `Pay the ${p.purpose === "peshi_fee" ? "appearance (peshi) fee" : "professional fee"}`,
            sub: [money(p.amount), p.created_at ? `requested ${day(p.created_at)}` : null].filter(Boolean).join(" · "),
            cta: "Pay now", action: "pay", id: p.id, primary: true,
        }));
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

    // The first one that needs paying or answering leads.
    return out.map((t, i) => ({ ...t, primary: i === 0 }));
}
