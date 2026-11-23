/* The status card at the top of a case (Tracking v2, 2026-11-23).
 *
 * One plain sentence answers "where is my case and what happens next", the
 * way an order-tracking page leads with the delivery date. Everything here is
 * read from real records: the case, its hearings, the milestones the lawyer
 * marks, and the hire request on this case. Nothing is invented: with no
 * hearing date the card says there is none yet, and with no milestones the
 * stage line says the lawyer has not added them.
 */
import { formatPkt, pktToday, pktDayKey } from "./bookingTime.js";

const CLOSED = new Set(["closed", "dismissed", "completed", "withdrawn"]);
const LIVE_ENGAGEMENT = new Set(["terms_proposed", "accepted", "requested"]);

/** Whole days from today (Pakistan) to `iso`'s Pakistan day; null if unknown. */
export function daysUntil(iso, today = pktToday()) {
    if (!iso) return null;
    const day = pktDayKey(iso);
    const a = Date.parse(`${today}T00:00:00Z`), b = Date.parse(`${day}T00:00:00Z`);
    if (Number.isNaN(a) || Number.isNaN(b)) return null;
    return Math.round((b - a) / 86400000);
}

/** The hire request that matters on this case: terms to answer first, then
 *  the engaged lawyer, then a request still waiting. Ended ones never. */
export function pickEngagement(list = [], caseId = null) {
    if (!caseId || !Array.isArray(list)) return null;
    const mine = list.filter(e => e && String(e.case_id || "") === String(caseId) && LIVE_ENGAGEMENT.has(e.status));
    const rank = e => (e.status === "terms_proposed" ? 0 : e.status === "accepted" ? 1 : 2);
    return mine.sort((x, y) => rank(x) - rank(y))[0] || null;
}

const dayWords = n => (n === 0 ? "today" : n === 1 ? "tomorrow" : `in ${n} days`);
const shortDate = iso => (iso ? formatPkt(iso, { day: "numeric", month: "short" }) : null);
const firstName = name => String(name || "").replace(/^(adv\.?|advocate)\s+/i, "").split(" ")[0] || "your lawyer";

/** Up to five steps around the current one: the last two done, the one in
 *  progress ("now"), then what follows. `steps` are mapped milestones
 *  ({ event, date, status: "done" | other }), in the lawyer's order. */
export function stageWindow(steps = []) {
    if (!steps.length) return [];
    let now = steps.findIndex(s => s.status !== "done");
    const allDone = now === -1;
    if (allDone) now = steps.length;
    const start = Math.max(0, Math.min(now - 2, steps.length - 5));
    return steps.slice(start, start + 5).map((s, i) => {
        const at = start + i;
        return {
            title: s.event,
            when: at === now ? "You are here" : (s.date || ""),
            state: at < now ? "done" : at === now ? "now" : "next",
        };
    });
}

/** What the card says. `actions` are names the page maps to handlers:
 *  "engagement" (open the hire request), "timeline", "messages", "find-lawyer",
 *  "book" (book the engaged lawyer). */
function heroCore({ caseInfo, nextHearing = null, engagement = null, feeText = "", today = pktToday(), engagementState = "ready" } = {}) {
    const e = engagement;
    const lawyer = e?.lawyer_name || null;
    const engaged = e?.status === "accepted";
    // The hire requests are not read yet, or the read failed: "no lawyer",
    // "nothing pending" or "your lawyer is working" would be a guess -- the
    // unread request may hold terms, a completion to confirm, or an ending.
    // That holds with a lawyer already assigned too (2026-11-23).
    const unknown = engagementState !== "ready" && !e;
    const person = unknown ? {
        label: "Your lawyer", name: null,
        sub: engagementState === "error" ? "Couldn't check who is handling this case." : "Checking…",
        actions: engagementState === "error" ? [{ label: "Try again", action: "retry-engagements" }] : [],
    } : engaged ? {
        label: "Your lawyer", name: lawyer || "Your lawyer",
        sub: [e.accepted_at ? `Engaged since ${shortDate(e.accepted_at)}` : "Engaged", feeText ? `${feeText} agreed` : ""].filter(Boolean).join(" · "),
        actions: [{ label: "Message", action: "messages" }, { label: "Book a meeting", action: "book" }],
    } : e?.status === "terms_proposed" ? {
        label: "Offering to take your case", name: lawyer || "A lawyer",
        sub: feeText ? `Proposed fee ${feeText}` : "Sent you terms",
        actions: [{ label: "Review terms", action: "engagement" }],
    } : e?.status === "requested" ? {
        label: "You asked", name: lawyer || "A lawyer",
        sub: e.created_at ? `Request sent ${shortDate(e.created_at)}` : "Request sent",
        actions: [{ label: "View request", action: "engagement" }],
    } : caseInfo?.lawyerAssigned ? {
        label: "Your lawyer", name: "Your lawyer", sub: "Assigned to this case",
        actions: [{ label: "Message", action: "messages" }],
    } : {
        label: "No lawyer yet", name: null, sub: "Ask a registered lawyer to take this case on.",
        actions: [{ label: "Find a lawyer", action: "find-lawyer" }],
    };

    const base = { person, tone: "brand" };
    const status = String(caseInfo?.status || "");

    if (CLOSED.has(status)) {
        return { ...base, tone: "muted", headline: "This case is closed",
            sub: "Its timeline, documents and messages stay here for your records.",
            primary: { label: "Open timeline", action: "timeline" }, secondary: null };
    }
    if (e?.status === "terms_proposed") {
        return { ...base, tone: "warn", headline: `${lawyer || "A lawyer"} sent you terms`,
            sub: `${feeText ? `${feeText}${e.scope_note ? ` · ${e.scope_note}` : ""}. ` : ""}Nothing is agreed until you accept.`,
            primary: { label: "Review terms", action: "engagement" }, secondary: null };
    }
    if (engaged && e.completion_proposed_by === "lawyer") {
        return { ...base, tone: "warn", headline: `${lawyer || "Your lawyer"} says the work is finished`,
            sub: "Confirm it to close the engagement, or message them if something is still open.",
            primary: { label: "Review", action: "engagement" }, secondary: { label: "Message", action: "messages" } };
    }
    if (nextHearing) {
        const n = daysUntil(nextHearing.date, today);
        const when = formatPkt(nextHearing.date, { weekday: "short", day: "numeric", month: "short" });
        return { ...base, headline: `Your next hearing is ${n == null ? "coming up" : dayWords(n)}`,
            sub: [`${when}${nextHearing.time ? `, ${nextHearing.time}` : ""}`, nextHearing.court].filter(Boolean).join(" · "),
            primary: { label: "Open timeline", action: "timeline" },
            secondary: engaged || caseInfo?.lawyerAssigned ? { label: `Message ${engaged ? firstName(lawyer) : "your lawyer"}`, action: "messages" } : null };
    }
    if (unknown) {
        return engagementState === "error"
            ? { ...base, tone: "warn", headline: "Couldn't check this case's latest status",
                sub: "Your hire requests could not be loaded, so terms or a reply may be waiting. Try again.",
                primary: { label: "Try again", action: "retry-engagements" }, secondary: null }
            : { ...base, tone: "muted", headline: "Checking your case…", sub: "", primary: null, secondary: null };
    }
    if (e?.status === "requested") {
        return { ...base, tone: "warn", headline: `Waiting for ${lawyer || "the lawyer"} to reply`,
            sub: "You'll be told as soon as they send their fee and scope. Nothing is agreed until you accept.",
            primary: { label: "View request", action: "engagement" }, secondary: null };
    }
    if (!engaged && !caseInfo?.lawyerAssigned) {
        return { ...base, tone: "warn", headline: "No lawyer on this case yet",
            sub: "Find a lawyer and ask them to take it on. You see their fee before anything is agreed.",
            primary: { label: "Find a lawyer", action: "find-lawyer" }, secondary: null };
    }
    return { ...base, headline: `${engaged ? firstName(lawyer) : "Your lawyer"} is working on your case`,
        sub: "No hearing date yet. It appears here as soon as the court sets one.",
        primary: { label: `Message ${engaged ? firstName(lawyer) : "your lawyer"}`, action: "messages" },
        secondary: { label: "Open timeline", action: "timeline" } };
}

/** The card's content, plus `warning` when the hire requests could not be
 *  read (or a re-read failed) but the sentence still stands on other facts,
 *  e.g. a hearing date: the unread request may change what is next. */
export function caseHero(args = {}) {
    const h = heroCore(args);
    const failed = (args.engagementState ?? "ready") === "error";
    return { ...h, warning: failed && h.primary?.action !== "retry-engagements"
        ? "Couldn't check the latest on your hire request, so something here may be out of date." : null };
}
