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
// The name as the lawyer gave it, without the title: "Test Lawyer", "Hina
// Tariq". A first name alone read "Test is working on your case" (2026-11-25).
const fullName = name => String(name || "").replace(/^(adv\.?|advocate)\s+/i, "").trim() || "Your lawyer";

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

/** The case's JOURNEY, for a case whose lawyer has added no milestones yet
 *  (2026-11-25, as the approved preview draws it). Five fixed stages, each
 *  marked done only from a real fact -- never guessed:
 *    Problem described   always (the case exists), dated by its creation
 *    Choosing a lawyer / Lawyer hired   done once a hire request is accepted
 *                        (or a lawyer is assigned)
 *    Case filed          done once the court has a hearing for it, or it closed
 *    Hearings            dated by the next hearing; done when it closed
 *    Decision            done when it closed
 *  The first stage not done is "now" ("You are here"). */
export function journeyStages({ caseInfo = null, engagement = null, nextHearing = null, hadHearing = false } = {}) {
    const closed = CLOSED.has(String(caseInfo?.status || ""));
    const hired = engagement?.status === "accepted" || !!caseInfo?.lawyerAssigned;
    const created = caseInfo?.filed && caseInfo.filed !== "—" ? caseInfo.filed : "";
    const list = [
        { title: "Problem described", when: created, done: true },
        { title: hired ? "Lawyer hired" : "Choosing a lawyer",
          when: engagement?.status === "accepted" && engagement.accepted_at ? shortDate(engagement.accepted_at) : "", done: hired },
        { title: "Case filed", when: "", done: !!(nextHearing || hadHearing || closed) },
        { title: "Hearings", when: nextHearing ? shortDate(nextHearing.date) : "", done: closed },
        { title: "Decision", when: "", done: closed },
    ];
    let now = list.findIndex(s => !s.done);
    if (now === -1) now = list.length;
    return list.map((s, i) => ({
        title: s.title,
        when: i === now ? "You are here" : s.when,
        state: i < now ? "done" : i === now ? "now" : "next",
    }));
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
        // The to-do's "Answer the terms" lives here now, not in a second card.
        waiting: true, note: "Read the scope and fee, then accept or decline.",
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
            // Review terms is the lawyer panel's button: not a second one here (2026-11-25).
            primary: null, secondary: null };
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
    return { ...base, headline: `${engaged ? fullName(lawyer) : "Your lawyer"} is working on your case`,
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
