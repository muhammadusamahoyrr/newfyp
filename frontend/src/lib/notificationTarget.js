/* Where a notification leads, and how open pages hear about it.
 *
 * WHAT WAS WRONG. The lawyer's notification panel navigated only when a row
 * carried `payload.route`, which almost none do (two dispute notices). Every
 * appointment, hearing, message and engagement notice marked itself read and
 * went nowhere. Its icons were keyed on types the server never sends
 * ("message", "hearing"), so every row showed the same bell, and the sidebar
 * counted unread "message" rows, a type that does not exist: case messages
 * arrive as "case_message".
 *
 * The server's types are the contract (app/core/constants.py NotificationType).
 */

/** The broad kind of a notification type: drives its icon and colour. */
export function notificationCategory(type) {
    const t = String(type || "");
    if (t === "case_message") return "message";
    if (t === "hearing_scheduled" || t === "hearing_reminder" || t === "causelist_listed") return "hearing";
    if (t.startsWith("appointment_")) return "appointment";
    if (t.startsWith("document_") || t.startsWith("review_request_") || t.startsWith("agreement_")
        || t.startsWith("quick_review_")) return "document";
    if (t.startsWith("engagement_") || t === "lawyer_assigned" || t === "case_update") return "case";
    if (t.startsWith("payment_") || t.startsWith("subscription_")) return "payment";
    if (t.startsWith("dispute_")) return "dispute";
    return "info";
}

/** The lawyer page a notification opens, and the case to open on it.
 *  Returns null when there is nowhere better than where the lawyer is. */
export function lawyerNotificationTarget(type, payload = {}) {
    const t = String(type || "");
    // Ids are used only when they are real strings; otherwise the page opens
    // without them (its list), never on a malformed id.
    const idOf = v => (typeof v === "string" && v.trim() ? v : null);
    const caseId = idOf(payload?.case_id);
    const appointmentId = idOf(payload?.appointment_id);
    // Meeting proposals (2026-10-12): an answered-no or lapsed proposal is acted
    // on from its CASE (propose new times there); an accepted one is the
    // appointment it became.
    if (t === "appointment_proposal_declined" || t === "appointment_proposal_expired"
        || t === "appointment_proposal_withdrawn") {
        return { page: "cases", caseId };
    }
    if (t === "case_message" || t === "case_update" || t === "hearing_scheduled" || t === "hearing_reminder"
        || t === "lawyer_assigned" || t.startsWith("engagement_")) {
        return { page: "cases", caseId };
    }
    // A message opens THAT appointment on its thread (before the generic rule).
    if (t === "appointment_message") {
        return appointmentId ? { page: "appointments", caseId: null, appointmentId, thread: true } : { page: "appointments", caseId: null };
    }
    if (t.startsWith("appointment_")) {
        return appointmentId ? { page: "appointments", caseId: null, appointmentId } : { page: "appointments", caseId: null };
    }
    // The document itself, not just the inbox: Document review opens it (2026-10-09).
    if (t.startsWith("document_")) return { page: "documents", caseId: null, docId: payload?.doc_id || null };
    if (t.startsWith("review_request_")) return { page: "review-queue", caseId: null };
    // Quick review requests are answered from the Document review inbox.
    if (t.startsWith("quick_review_")) return { page: "documents", caseId: null };
    // An agreement opens THAT agreement on Agreements (restored 2026-11-25):
    // the case page shows no agreements, so it was a dead end for signing.
    if (t.startsWith("agreement_")) {
        return { page: "agreements", caseId: null, agreementId: idOf(payload?.agreement_id) };
    }
    // Payments is still hidden from the lawyer UI (App.jsx HIDDEN_PAGES).
    // Open the case the notice is about instead; with no case, stay put.
    if (t.startsWith("payment_")) {
        return caseId ? { page: "cases", caseId } : null;
    }
    if (t.startsWith("dispute_")) return { page: "overseas-disputes", caseId: null };
    if (t === "causelist_listed") return { page: "causelist", caseId: null };
    if (t.startsWith("kyc_") || t === "review_received") return { page: "profile", caseId: null };
    return null;
}

/** One case in My Matters (the /tracking page): `/tracking?case=…&tab=…`,
 *  plus `&engagement=…` to open and highlight one hire request. With no case
 *  id it opens My Matters without choosing one. Tabs: summary, timeline,
 *  documents, messages, payments; `&payment=…` opens and highlights one fee. */
export function matterHref(caseId, { tab = "summary", engagement = null, payment = null, document = null, agreement = null } = {}) {
    const q = new URLSearchParams();
    if (caseId) q.set("case", String(caseId));
    if (tab) q.set("tab", tab);
    if (engagement) q.set("engagement", String(engagement));
    if (payment) q.set("payment", String(payment));
    if (document) q.set("document", String(document));
    // One agreement on the matter's Documents tab, highlighted (2026-11-25).
    if (agreement) q.set("agreement", String(agreement));
    const s = q.toString();
    return s ? `/tracking?${s}` : "/tracking";
}

/** The CLIENT page a notification opens (2026-10-12), or null for none.
 *  Clicking one used to only mark it read: "Meeting proposed", "Appointment
 *  confirmed", "Request declined" or "Terms received" led nowhere. */
export function clientNotificationTarget(type, payload = {}) {
    const t = String(type || "");
    const apptId = payload?.appointment_id || null;
    // A message opens the appointment ON its thread.
    if (t === "appointment_message") {
        return apptId ? `/appointments?appointment=${encodeURIComponent(apptId)}&thread=open` : "/appointments";
    }
    // A proposal is answered on the Appointments page; once accepted, it is
    // the appointment it became.
    if (t.startsWith("appointment_propos")) {
        if (t === "appointment_proposed" && payload?.proposal_id) {
            return `/appointments?section=proposals&proposal=${encodeURIComponent(payload.proposal_id)}`;
        }
        return apptId ? `/appointments?appointment=${encodeURIComponent(apptId)}` : "/appointments";
    }
    if (t.startsWith("appointment_")) {
        return apptId ? `/appointments?appointment=${encodeURIComponent(apptId)}` : "/appointments";
    }
    // Hire requests and proposed terms live on the case in My Matters
    // (2026-11-23; they used to be on the Lawyers page). Every link carries
    // the case AND the request, so the exact one opens and is highlighted.
    const caseId = payload?.case_id || null;
    if (t.startsWith("engagement_") || t === "lawyer_assigned") {
        return caseId ? matterHref(caseId, { tab: "summary", engagement: payload?.engagement_id || null }) : "/tracking";
    }
    if (t === "case_message") return caseId ? matterHref(caseId, { tab: "messages" }) : "/tracking";
    if (t.startsWith("hearing_")) return caseId ? matterHref(caseId, { tab: "timeline" }) : "/tracking";
    if (t === "case_update") return caseId ? matterHref(caseId, { tab: "summary" }) : "/tracking";
    // A fee requested, paid or failed opens THAT payment on its case (2026-11-23;
    // it used to open nothing). A notice with no case id (sent before
    // "failed" carried one) opens All my payments, a view with NO case
    // header: opening it under a case put one case's name over another's fee.
    if (t.startsWith("payment_")) {
        const pay = payload?.payment_id || null;
        if (caseId) return matterHref(caseId, { tab: "payments", payment: pay });
        return pay ? `/tracking?view=payments&payment=${encodeURIComponent(pay)}` : "/tracking?view=payments";
    }
    if (t.startsWith("agreement_")) {
        const agreement = payload?.agreement_id || null;
        return agreement ? `/agreements?agreement=${encodeURIComponent(agreement)}` : "/agreements";
    }
    return null;
}

const EVENT = "aai:notification";

/** Tell every open page a notification arrived (from the live socket). */
export function broadcastNotification(n) {
    if (typeof window === "undefined" || !n) return;
    try { window.dispatchEvent(new window.CustomEvent(EVENT, { detail: n })); } catch { /* no DOM */ }
}

/** Listen for live notifications. Returns the unsubscribe function. */
export function onNotification(handler) {
    if (typeof window === "undefined") return () => {};
    const listener = (ev) => { try { handler(ev.detail || {}); } catch { /* a page's handler must not break others */ } };
    window.addEventListener(EVENT, listener);
    return () => window.removeEventListener(EVENT, listener);
}

/** Delay before reconnect attempt `n` (0-based): 1s, 2s, 4s … capped at 30s. */
export function reconnectDelay(n) {
    return Math.min(30000, 1000 * 2 ** Math.max(0, n));
}
