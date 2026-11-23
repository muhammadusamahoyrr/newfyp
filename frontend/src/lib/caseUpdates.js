/* The Overview's "Updates" feed and "Case details" (Tracking v2, 2026-11-23).
 *
 * Updates: what happened on the case, newest first, from real records only:
 * messages, documents added, steps the lawyer marked done, fees requested and
 * paid. Grouped by Pakistan day ("Today", "Yesterday", "20 Nov").
 * Details: the case's facts, money and files, each from what was read. A fact
 * that is not known is left out, never filled with "—" or a guess. */
import { formatPkt, pktToday, pktDayKey } from "./bookingTime.js";

const ts = v => { const n = v ? new Date(v).getTime() : NaN; return Number.isFinite(n) ? n : null; };
const money = n => `PKR ${Number(n || 0).toLocaleString()}`;
const clock = at => formatPkt(new Date(at).toISOString(), { hour: "numeric", minute: "2-digit" });

/** @returns {Array<{key, at, who, what, body, tag}>} newest first */
export function caseUpdates({ messages = [], docs = [], steps = [], payments = [], lawyerName = null } = {}) {
    const out = [];
    for (const m of messages || []) {
        const at = ts(m.created_at);
        if (at == null) continue;
        const lawyer = m.sender_role === "lawyer";
        out.push({ key: `m-${m._id || m.id || at}`, at, tag: "msg", mine: !lawyer,
            who: lawyer ? (m.sender_name || lawyerName || "Your lawyer") : "You",
            what: "sent a message", body: m.text || "" });
    }
    for (const d of docs || []) {
        if (!d?.at) continue;
        out.push({ key: `d-${d.id}`, at: d.at, tag: "doc", who: "Document added", what: `“${d.name}”`, body: "" });
    }
    for (const s of steps || []) {
        if (s?.status !== "done" || !s.at) continue;
        out.push({ key: `s-${s.id}`, at: s.at, tag: "step", who: s.event, what: "was marked done", body: "" });
    }
    for (const p of payments || []) {
        const kind = p.purpose === "peshi_fee" ? "appearance (peshi) fee" : "professional fee";
        if (p.status === "paid" && ts(p.paid_at || p.updated_at) != null) {
            out.push({ key: `pp-${p.id}`, at: ts(p.paid_at || p.updated_at), tag: "fee", who: "You paid", what: `the ${kind} of ${money(p.amount)}`, body: "" });
        }
        if (ts(p.created_at) != null) {
            out.push({ key: `pr-${p.id}`, at: ts(p.created_at), tag: "fee", who: lawyerName || "Your lawyer", what: `requested the ${kind} of ${money(p.amount)}`, body: "" });
        }
    }
    return out.sort((a, b) => b.at - a.at);
}

/** Updates in day groups, newest day first. */
export function groupByDay(updates = [], today = pktToday()) {
    const y = new Date(Date.parse(`${today}T00:00:00Z`) - 86400000).toISOString().slice(0, 10);
    const groups = [];
    for (const u of updates) {
        const iso = new Date(u.at).toISOString();
        const key = pktDayKey(iso);
        const label = key === today ? "Today" : key === y ? "Yesterday" : formatPkt(iso, { day: "numeric", month: "short" });
        let g = groups[groups.length - 1];
        if (!g || g.key !== key) { g = { key, label, items: [] }; groups.push(g); }
        g.items.push({ ...u, time: clock(u.at) });
    }
    return groups;
}

/** CASE / MONEY / FILES rows; each group links to its tab. */
export function caseDetails({ caseInfo = {}, engagement = null, feeText = "", payments = [], docs = [] } = {}) {
    const known = v => v && v !== "—";
    const type = caseInfo.type ? caseInfo.type.charAt(0).toUpperCase() + caseInfo.type.slice(1) : null;
    const caseRows = [["Type", type], ["Case no.", caseInfo.caseNumber], ["Court", caseInfo.court], ["Opened", caseInfo.filed]]
        .filter(([, v]) => known(v)).map(([k, v]) => ({ k, v }));
    const paid = payments.filter(p => p.status === "paid").reduce((s, p) => s + Number(p.amount || 0), 0);
    const due = payments.filter(p => p.status === "created" || p.status === "pending").reduce((s, p) => s + Number(p.amount || 0), 0);
    const moneyRows = [
        engagement?.status === "accepted" && feeText ? { k: "Agreed fee", v: feeText } : null,
        engagement?.status === "terms_proposed" && feeText ? { k: "Proposed fee", v: feeText } : null,
        { k: "Paid", v: money(paid) },
        due > 0 ? { k: "Due", v: money(due), warn: true } : null,
    ].filter(Boolean);
    const latest = [...docs].sort((a, b) => (b.at || 0) - (a.at || 0))[0] || null;
    const fileRows = [
        { k: "Documents", v: String(docs.length) },
        latest ? { k: "Last added", v: latest.name } : null,
    ].filter(Boolean);
    return [
        { key: "case", title: "Case", link: "Timeline", tab: "timeline", rows: caseRows },
        { key: "money", title: "Money", link: "Payments", tab: "payments", rows: moneyRows },
        { key: "files", title: "Files", link: "Documents", tab: "documents", rows: fileRows },
    ];
}
