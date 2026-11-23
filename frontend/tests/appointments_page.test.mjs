/* The Appointments page (2026-10-12).
 *
 * Appointments have a page of their own in the client sidebar. It is the SAME
 * list Tracking shows (ModTracking in standalone mode), so there is one set of
 * rules for cancel, reschedule, disputes and hire. Each card shows where the
 * appointment stands and what to do now.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>",
                      { url: "http://localhost/appointments?appointment=a-up" });
function define(name, value) {
    Object.defineProperty(globalThis, name, { value, writable: true, configurable: true });
}
for (const name of ["window", "document", "navigator", "HTMLElement", "Element", "Node", "Event",
                    "CustomEvent", "MouseEvent", "MutationObserver", "getComputedStyle", "localStorage",
                    "requestAnimationFrame", "cancelAnimationFrame", "CSS"]) {
    define(name, dom.window[name]);
}
if (!globalThis.CSS) define("CSS", { escape: s => String(s) });
define("IS_REACT_ACT_ENVIRONMENT", true);
dom.window.HTMLElement.prototype.scrollIntoView = function () {};

const React = (await import("react")).default;
const { act } = await import("react");
const { createRoot } = await import("react-dom/client");
const api = await import("./support/api-stub.mjs");
const h = React.createElement;
const realSetTimeout = setTimeout;

const inHours = n => new Date(Date.now() + n * 36e5).toISOString();
function appt(over) {
    return { id: "a1", lawyer_id: "L1", lawyer_name: "Kamran Aziz Malik", scheduled_at: inHours(3),
             end_at: inHours(4), duration_minutes: 60, mode: "video", status: "confirmed",
             case_id: null, schedule_version: 1, ...over };
}

async function mountPage({ standalone = "appointments" } = {}) {
    const Module7 = (await import("../src/components/client/ModTracking.jsx")).default;
    const { CaseCtx } = await import("../src/components/shared/CaseContext.jsx");
    const container = dom.window.document.createElement("div");
    dom.window.document.body.appendChild(container);
    const root = createRoot(container);
    const ctx = { notifications: [], markNotificationDone: () => {}, markAllNotificationsDone: () => {}, appointmentMilestones: [] };
    await act(async () => {
        root.render(h(CaseCtx.Provider, { value: ctx }, h(Module7, { isDark: true, standalone })));
    });
    await act(async () => { await new Promise(r => realSetTimeout(r, 60)); });
    return { container, text: () => container.textContent,
             unmount: async () => { await act(async () => root.unmount()); container.remove(); } };
}

test.beforeEach(() => {
    api.__reset();
    api.__respond("bootstrapAuth", true);
    api.__respond("getMe", { data: { _id: "c1", role: "client" } });
    api.__respond("getNotifications", { data: { items: [] } });
    api.__respond("listCases", { data: { items: [{ _id: "C1", title: "Bail matter", status: "open" }] } });
});
test.after(() => dom.window.close());

const click = async el => { await act(async () => { el.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); }); await act(async () => { await new Promise(r => realSetTimeout(r, 30)); }); };

const card = { specializations: ["criminal"], experience_years: 19, rating: 4.8, total_reviews: 71,
                office_address: "Jinnah Avenue, Blue Area, Islamabad", lat: 33.72, lng: 73.08 };

test("the page lists the appointments beside a calendar and the next one, without Tracking's navigation", async () => {
    api.__respond("listAppointments", { data: { items: [appt({ id: "a-other", lawyer_card: card })] } });
    const ui = await mountPage();
    assert.ok(ui.container.querySelector("[data-appointments-hub]"));
    assert.ok(ui.container.querySelector("[data-mini-calendar]"));
    assert.match(ui.container.querySelector("[data-next-appointment]").textContent, /Kamran Aziz Malik · Video call/);
    assert.equal([...ui.container.querySelectorAll("div")].some(d => d.textContent.trim() === "Case Timeline"), false);
    const row = ui.container.querySelector('[data-hub-row="a-other"]');
    assert.match(row.textContent, /Kamran Aziz Malik.*Criminal · Jinnah Avenue, Blue Area, Islamabad.*Video consultation.*Confirmed · in \d+ h/s);
    await ui.unmount();
});

test("the tabs split upcoming, past and cancelled; a confirmed video row can be joined straight away", async () => {
    api.__respond("listAppointments", { data: { items: [
        appt({ id: "a-done", status: "completed", scheduled_at: inHours(-30), end_at: inHours(-29) }),
        appt({ id: "a-other", meeting_link: "https://meet.example.com/x" }),
        appt({ id: "a-wait", status: "pending", scheduled_at: inHours(30), end_at: inHours(31) }),
        appt({ id: "a-gone", status: "cancelled", scheduled_at: inHours(40), end_at: inHours(41) }),
    ] } });
    const ui = await mountPage();
    const rows = () => [...ui.container.querySelectorAll("[data-hub-row]")].map(r => r.dataset.hubRow);
    assert.deepEqual(rows(), ["a-other", "a-wait"], "upcoming, soonest first");
    assert.ok([...ui.container.querySelectorAll('[data-hub-row="a-other"] a')].some(a => a.textContent === "Join meeting"));
    await click(ui.container.querySelector('[data-hub-tab="past"]'));
    assert.deepEqual(rows(), ["a-done"]);
    // Hire opens the hire dialog on this page (2026-10-20), not the Lawyers page.
    const hire = ui.container.querySelector('[data-hub-row="a-done"] [data-row-hire]');
    assert.equal(hire?.tagName, "BUTTON", "Hire still leaves the page");
    await click(ui.container.querySelector('[data-hub-tab="cancelled"]'));
    assert.deepEqual(rows(), ["a-gone"]);
    await ui.unmount();
});

test("a video appointment's page: the lawyer, how to join, the checklist, and the way back", async () => {
    api.__respond("listAppointments", { data: { items: [appt({ id: "a-other", meeting_link: "https://meet.example.com/x", case_id: "C1", notes: "FIR last week", lawyer_card: card })] } });
    const ui = await mountPage();
    await click(ui.container.querySelector('[data-hub-row="a-other"] [data-open-appt]'));
    const page = ui.container.querySelector('[data-appointment-detail="a-other"]');
    assert.ok(page, "the appointment page did not open");
    assert.match(page.textContent, /Lawyer · Criminal · 19 years experience.*4\.8.*71 reviews/s);
    assert.match(page.textContent, /Bail matter/);
    const panel = page.querySelector('[data-mode-panel="video"]');
    assert.ok([...panel.querySelectorAll("a")].some(a => a.textContent === "Join meeting" && a.href.includes("meet.example.com")));
    assert.match(page.textContent, /Preparation checklist.*1 of 4 completed/s);
    assert.ok(page.querySelector("[data-add-calendar]"), "add to calendar is offered, as an option");
    assert.ok([...page.querySelectorAll("button")].some(b => b.textContent.includes("Cancel appointment")));
    await click(page.querySelector("[data-back-to-hub]"));
    assert.ok(ui.container.querySelector("[data-appointments-hub]"));
    await ui.unmount();
});

test("an in-person request still waiting: where to go, and a warning not to travel yet", async () => {
    api.__respond("listAppointments", { data: { items: [appt({ id: "a-up", status: "pending", mode: "in_person", lawyer_card: card })] } });
    const ui = await mountPage();   // the URL names a-up
    const page = ui.container.querySelector('[data-appointment-detail="a-up"]');
    assert.ok(page, "not opened on the linked appointment");
    const panel = page.querySelector('[data-mode-panel="in_person"]');
    assert.match(panel.textContent, /Jinnah Avenue, Blue Area, Islamabad/);
    assert.ok([...panel.querySelectorAll("a")].some(a => a.textContent === "View on map" && a.href.includes("33.72")));
    assert.match(page.querySelector("[data-waiting-note]").textContent, /don't travel until it's confirmed/);
    assert.ok([...page.querySelectorAll("button")].some(b => b.textContent.includes("Change time")));
    assert.equal(page.querySelector("[data-add-calendar]"), null, "nothing to add to a calendar until it is confirmed");
    await ui.unmount();
});

test("a confirmed phone consultation shows the lawyer's number; no join button", async () => {
    api.__respond("listAppointments", { data: { items: [appt({ id: "a-up", mode: "phone", lawyer_card: { ...card, phone: "+92-301-3330201" } })] } });
    const ui = await mountPage();
    const page = ui.container.querySelector('[data-appointment-detail="a-up"]');
    const panel = page.querySelector('[data-mode-panel="phone"]');
    assert.match(panel.textContent, /\+92-301-3330201/);
    assert.equal([...page.querySelectorAll("a")].some(a => a.textContent === "Join meeting"), false);
    await ui.unmount();
});

test("Tracking has no Appointments tab of its own: one list, on /appointments (2026-11-23)", async () => {
    api.__respond("listAppointments", { data: { items: [appt({ id: "a-up" })] } });
    const ui = await mountPage({ standalone: null });
    assert.equal(ui.container.querySelector("[data-appointments-hub]"), null);
    // /tracking opens on My matters (v2): open a case to see its tabs.
    const open = ui.container.querySelector("[data-open-matter]");
    if (open) {
        await act(async () => { open.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
        await act(async () => { await new Promise(r => setTimeout(r, 30)); });
    }
    const tabs = [...ui.container.querySelectorAll("[data-case-tab]")].map(b => b.textContent.trim());
    assert.ok(tabs.includes("Overview"), "the case tabs were not found");
    assert.ok(!tabs.includes("Appointments"), "Tracking still has its own Appointments tab");
    await ui.unmount();
});

test("a request the lawyer turned down is called declined, not cancelled (2026-10-12)", async () => {
    api.__respond("listAppointments", { data: { items: [appt({ id: "a-up", status: "cancelled",
        cancelled_by: "lawyer", cancelled_from: "pending", cancel_reason: "Not available at that time", lawyer_card: card })] } });
    const ui = await mountPage();   // the URL names a-up
    const page = ui.container.querySelector('[data-appointment-detail="a-up"]');
    assert.match(page.textContent, /Your request was declined/);
    assert.match(page.textContent, /Your lawyer declined this request\./);
    assert.match(page.textContent, /Not available at that time/);
    assert.doesNotMatch(page.textContent, /cancelled this appointment/);
    await ui.unmount();
});

test("a confirmed appointment the lawyer called off is still a cancellation", async () => {
    api.__respond("listAppointments", { data: { items: [appt({ id: "a-up", status: "cancelled",
        cancelled_by: "lawyer", cancelled_from: "confirmed", lawyer_card: card })] } });
    const ui = await mountPage();
    const page = ui.container.querySelector('[data-appointment-detail="a-up"]');
    assert.match(page.textContent, /This appointment was cancelled/);
    assert.match(page.textContent, /Your lawyer cancelled this appointment\./);
    await ui.unmount();
});

test("after a consultation, follow-up leads to THAT lawyer, and the review opens right here", async () => {
    api.__respond("listAppointments", { data: { items: [appt({ id: "a-up", status: "completed",
        scheduled_at: inHours(-30), end_at: inHours(-29), lawyer_card: card })] } });
    const ui = await mountPage();
    const page = ui.container.querySelector('[data-appointment-detail="a-up"]');
    const href = label => [...page.querySelectorAll("a")].find(a => a.textContent === label)?.getAttribute("href");
    assert.equal(href("Pick a time"), "/lawyers?lawyer=L1&lawyer_name=Kamran%20Aziz%20Malik&action=book");
    // The review is a dialog on this page (2026-10-20), for THAT lawyer.
    api.__respond("getReviewEligibility", { data: { can_review: true, already_reviewed: false }, error: null });
    await click(page.querySelector("[data-detail-review]"));
    assert.equal(api.__calls("getReviewEligibility")[0].args[0], "L1");
    assert.equal(dom.window.document.querySelector("[data-review-dialog]")?.getAttribute("data-review-dialog"), "can");
    await ui.unmount();
});

/* ── meetings the lawyer proposed (2026-10-12) ─────────────────────────────── */

const proposal = (over = {}) => ({ id: "P1", status: "open", lawyer_name: "Kamran Aziz Malik", case_title: "Bail matter",
    agenda: "Prepare for the hearing", mode: "video", duration_minutes: 60,
    options: [inHours(50), inHours(74)], option_passed: [false, false], ...over });

test("a proposed meeting is shown, and choosing a time opens the confirmed appointment", async () => {
    api.__respond("listMeetingProposals", { data: [proposal()] });
    api.__respond("acceptMeetingProposal", { data: { proposal: { id: "P1", status: "accepted" }, appointment: { id: "a-new" } } });
    api.__respond("listAppointments", { data: { items: [appt({ id: "a-new", case_id: "C1", scheduled_at: inHours(74), end_at: inHours(75), lawyer_card: card })] } });
    const ui = await mountPage();
    const box = ui.container.querySelector('[data-proposal="P1"]');
    assert.ok(box, "the proposal was not shown");
    assert.match(box.textContent, /Kamran Aziz Malik would like to meet about “Bail matter”.*Prepare for the hearing · Video call · 60 minutes/s);
    await click(box.querySelector('[data-proposal-option="1"]'));
    assert.deepEqual(api.__calls("acceptMeetingProposal").map(c => c.args), [["P1", 1]]);
    assert.ok(ui.container.querySelector('[data-appointment-detail="a-new"]'), "the confirmed appointment did not open");
    await ui.unmount();
});

test("none of the proposed times: the client can say so", async () => {
    api.__respond("listMeetingProposals", { data: [proposal()] });
    api.__respond("declineMeetingProposal", { data: { id: "P1", status: "declined" } });
    api.__respond("listAppointments", { data: { items: [] } });
    const ui = await mountPage();
    const btn = [...ui.container.querySelectorAll("button")].find(b => b.textContent === "None of these work for me");
    await click(btn);
    await click(ui.container.querySelector("[data-proposal-decline]"));
    assert.equal(api.__calls("declineMeetingProposal").length, 1);
    assert.equal(ui.container.querySelector('[data-proposal="P1"]'), null);
    await ui.unmount();
});

/* ── after asking to hire (2026-10-12) ─────────────────────────────────────── */

test("a consultation whose hire request has terms shows them, not 'Hire' again", async () => {
    api.__respond("listEngagements", { data: [{ id: "E1", appointment_id: "a-up", status: "terms_proposed", fee_amount: 25000 }] });
    api.__respond("listAppointments", { data: { items: [appt({ id: "a-up", status: "completed",
        scheduled_at: inHours(-30), end_at: inHours(-29), lawyer_card: card })] } });
    const ui = await mountPage();
    const page = ui.container.querySelector('[data-appointment-detail="a-up"]');
    assert.match(page.textContent, /Kamran sent you terms.*Fee Rs 25,000/s);
    const review = page.querySelector("[data-detail-hire]");
    assert.equal(review?.textContent, "Review terms", "Review terms is not a dialog on this page");
    assert.ok(![...page.querySelectorAll("a")].some(a => a.textContent === "Request to hire"), "the hire was offered again");
    await click(page.querySelector("[data-back-to-hub]"));
    await click(ui.container.querySelector('[data-hub-tab="past"]'));
    const row = ui.container.querySelector('[data-hub-row="a-up"]');
    assert.ok(row.querySelector('[data-hire-state="terms_proposed"]'));
    assert.ok(![...row.querySelectorAll("a, button")].some(a => a.textContent === "Hire"));
    await ui.unmount();
});

test("a sent hire request says it is waiting", async () => {
    api.__respond("listEngagements", { data: [{ id: "E1", appointment_id: "a-up", status: "requested" }] });
    api.__respond("listAppointments", { data: { items: [appt({ id: "a-up", status: "completed",
        scheduled_at: inHours(-30), end_at: inHours(-29), lawyer_card: card })] } });
    const ui = await mountPage();
    const page = ui.container.querySelector('[data-appointment-detail="a-up"]');
    assert.match(page.textContent, /Hire request sent.*Waiting for Kamran to send their fee and scope/s);
    await ui.unmount();
});

/* ── after the consultation, on the page's front (2026-10-20) ──────────── */

const done = (over = {}) => appt({ id: "a-done", status: "completed", scheduled_at: inHours(-30), end_at: inHours(-29), lawyer_card: card, ...over });

test("a finished consultation's hire and review are on the front of the page, not only under Past", async () => {
    api.__respond("listEngagements", { data: [] });
    api.__respond("listAppointments", { data: { items: [done(), appt({ id: "a-next", scheduled_at: inHours(30), end_at: inHours(31) })] } });
    const ui = await mountPage();
    await click(ui.container.querySelector("[data-back-to-hub]") || ui.container);
    const step = ui.container.querySelector('[data-next-step="a-done"]');
    assert.ok(step, "no next step for the finished consultation on the default view");
    assert.equal(step.getAttribute("data-hire-state"), "none");
    const hire = step.querySelector("[data-next-hire]");
    assert.equal(hire.textContent, "Request to hire");
    assert.equal(hire.tagName, "BUTTON", "Request to hire still leaves the page");
    assert.equal(step.querySelector("[data-next-review]").tagName, "BUTTON", "Review still leaves the page");
    await ui.unmount();
});

test("the front card follows the hire: terms to review, then gone once hired", async () => {
    api.__respond("listEngagements", { data: [{ id: "E1", appointment_id: "a-done", status: "terms_proposed", fee_amount: 25000 }] });
    api.__respond("listAppointments", { data: { items: [done(), appt({ id: "a-next", scheduled_at: inHours(30), end_at: inHours(31) })] } });
    let ui = await mountPage();
    let step = ui.container.querySelector('[data-next-step="a-done"]');
    assert.equal(step.querySelector("[data-next-hire]").textContent, "Review terms");
    await ui.unmount();
    api.__respond("listEngagements", { data: [{ id: "E1", appointment_id: "a-done", status: "accepted" }] });
    ui = await mountPage();
    assert.equal(ui.container.querySelector('[data-next-step="a-done"]'), null, "a settled hire still asks for a next step");
    await ui.unmount();
});

test("a Past row of a finished consultation has a Review button", async () => {
    api.__respond("listEngagements", { data: [] });
    api.__respond("listAppointments", { data: { items: [done(), appt({ id: "a-next", scheduled_at: inHours(30), end_at: inHours(31) })] } });
    const ui = await mountPage();
    await click(ui.container.querySelector('[data-hub-tab="past"]'));
    const row = ui.container.querySelector('[data-hub-row="a-done"]');
    assert.ok(row.querySelector("[data-row-review]"), "no Review on the finished consultation's row");
    await ui.unmount();
});

/* ── the review dialog, on this page (2026-10-20) ──────────────────────── */

async function openReview(elig) {
    api.__respond("listEngagements", { data: [] });
    api.__respond("listAppointments", { data: { items: [done(), appt({ id: "a-next", scheduled_at: inHours(30), end_at: inHours(31) })] } });
    api.__respond("getReviewEligibility", elig);
    const ui = await mountPage();
    // From the Past row, which offers Review whatever the front card shows.
    await click(ui.container.querySelector('[data-hub-tab="past"]'));
    await click(ui.container.querySelector('[data-hub-row="a-done"] [data-row-review]'));
    return { ui, dlg: () => dom.window.document.querySelector("[data-review-dialog]") };
}

test("Review opens a dialog here; a rating is needed, then the review is sent for that lawyer", async () => {
    const { ui, dlg } = await openReview({ data: { can_review: true, already_reviewed: false }, error: null });
    assert.ok(dlg(), "the review did not open on this page");
    api.__respond("submitReview", { data: { ok: true }, error: null });
    await click(dlg().querySelector("[data-review-submit]"));
    assert.equal(api.__calls("submitReview").length, 0, "a review was sent without a rating");
    assert.match(dlg().querySelector("[data-review-error]").textContent, /Choose a rating/);
    await click(dlg().querySelector('[data-review-star="4"]'));
    const box = dlg().querySelector("textarea");
    Object.getOwnPropertyDescriptor(dom.window.HTMLTextAreaElement.prototype, "value").set.call(box, "Clear advice");
    await act(async () => { box.dispatchEvent(new dom.window.Event("input", { bubbles: true })); });
    await click(dlg().querySelector("[data-review-submit]"));
    assert.deepEqual(api.__calls("submitReview")[0].args, ["L1", 4, "Clear advice"]);
    assert.match(dlg().textContent, /Thank you/);
    await ui.unmount();
});

test("the review dialog says 'already reviewed', 'not yet', and a failed check honestly", async () => {
    for (const [elig, state, text] of [
        [{ data: { can_review: false, already_reviewed: true }, error: null }, "done", /already reviewed/],
        [{ data: { can_review: false, already_reviewed: false }, error: null }, "not-eligible", /after a completed consultation/],
        [{ data: null, error: { message: "down" }, status: 0 }, "error", /Could not check/],
    ]) {
        const { ui, dlg } = await openReview(elig);
        assert.equal(dlg().getAttribute("data-review-dialog"), state);
        assert.match(dlg().textContent, text);
        assert.equal(dlg().querySelector("[data-review-submit]"), null);
        await ui.unmount();
    }
});

/* ── hiring on this page (2026-10-20) ────────────────────────────────────── */

async function openHire(engs) {
    api.__respond("listEngagements", { data: engs });
    api.__respond("listAppointments", { data: { items: [done(), appt({ id: "a-next", scheduled_at: inHours(30), end_at: inHours(31) })] } });
    api.__respond("listCases", { data: { items: [{ _id: "C1", title: "Bail matter", status: "open", lawyer_id: null }], total: 1, pages: 1 } });
    const ui = await mountPage();
    await click(ui.container.querySelector('[data-next-step="a-done"] [data-next-hire]'));
    await act(async () => { await new Promise(r => realSetTimeout(r, 60)); });
    return { ui, dlg: () => dom.window.document.querySelector("[data-hire-dialog]") };
}

test("Request to hire opens here and sends the request for THIS consultation and the chosen case", async () => {
    const { ui, dlg } = await openHire([]);
    assert.equal(dlg()?.getAttribute("data-hire-dialog"), "request", "the hire did not open on this page");
    assert.equal(dlg().querySelector("[data-hire-case]").value, "C1");
    api.__respond("requestEngagement", { data: { id: "E9", status: "requested" }, error: null });
    await click(dlg().querySelector("[data-hire-send]"));
    assert.deepEqual(api.__calls("requestEngagement")[0].args[0], { case_id: "C1", lawyer_id: "L1", appointment_id: "a-done", message: null });
    assert.equal(dlg().getAttribute("data-hire-dialog"), "done");
    await ui.unmount();
});

test("a failed request is said in the dialog, which stays open", async () => {
    const { ui, dlg } = await openHire([]);
    api.__respond("requestEngagement", { data: null, error: { message: "You already have a pending request for this case." }, status: 409 });
    await click(dlg().querySelector("[data-hire-send]"));
    assert.match(dlg().querySelector("[data-hire-error]").textContent, /pending request/);
    assert.equal(dlg().getAttribute("data-hire-dialog"), "request");
    await ui.unmount();
});

test("View request (from its Past row) shows where it stands and can withdraw it, after a confirmation", async () => {
    api.__respond("listEngagements", { data: [{ id: "E1", appointment_id: "a-done", status: "requested", case_title: "Bail matter", message: "Please help" }] });
    api.__respond("listAppointments", { data: { items: [done(), appt({ id: "a-next", scheduled_at: inHours(30), end_at: inHours(31) })] } });
    const ui = await mountPage();
    await click(ui.container.querySelector('[data-hub-tab="past"]'));
    await click(ui.container.querySelector('[data-hub-row="a-done"] [data-hire-state="requested"]'));
    const dlg = () => dom.window.document.querySelector("[data-hire-dialog]");
    assert.equal(dlg().getAttribute("data-hire-dialog"), "sent");
    assert.match(dlg().textContent, /Bail matter/);
    api.__respond("cancelEngagement", { data: { status: "cancelled" }, error: null });
    await click(dlg().querySelector("[data-hire-withdraw]"));
    assert.equal(api.__calls("cancelEngagement").length, 0, "withdrawn without a confirmation");
    await click(dlg().querySelector("[data-hire-withdraw-confirm]"));
    assert.equal(api.__calls("cancelEngagement")[0].args[0], "E1");
    await ui.unmount();
});

test("Review terms shows the fee and accepts or declines here", async () => {
    const terms = { id: "E1", appointment_id: "a-done", status: "terms_proposed", fee_amount: 45000, fee_type: "per_hearing", scope_note: "Every hearing", case_title: "Bail matter" };
    let { ui, dlg } = await openHire([terms]);
    assert.equal(dlg().getAttribute("data-hire-dialog"), "terms");
    assert.match(dlg().querySelector("[data-hire-fee]").textContent, /Rs 45,000/);
    assert.match(dlg().textContent, /Per hearing \(peshi\).*Every hearing/s);
    api.__respond("acceptEngagementTerms", { data: { status: "accepted" }, error: null });
    await click(dlg().querySelector("[data-hire-accept]"));
    assert.equal(api.__calls("acceptEngagementTerms")[0].args[0], "E1");
    await ui.unmount();

    ({ ui, dlg } = await openHire([terms]));
    api.__respond("declineEngagementTerms", { data: { status: "declined" }, error: null });
    await click(dlg().querySelector("[data-hire-decline]"));
    const box = dlg().querySelector("textarea");
    Object.getOwnPropertyDescriptor(dom.window.HTMLTextAreaElement.prototype, "value").set.call(box, "Too high");
    await act(async () => { box.dispatchEvent(new dom.window.Event("input", { bubbles: true })); });
    await click(dlg().querySelector("[data-hire-decline-confirm]"));
    assert.deepEqual(api.__calls("declineEngagementTerms")[0].args, ["E1", "Too high"]);
    await ui.unmount();
});

/* ── the front is a to-do list, not a second history (2026-10-20) ─────────── */

test("a request waiting on the lawyer is not on the front; it stays in Past", async () => {
    api.__respond("listEngagements", { data: [{ id: "E1", appointment_id: "a-done", status: "requested" }] });
    api.__respond("listAppointments", { data: { items: [done(), appt({ id: "a-next", scheduled_at: inHours(30), end_at: inHours(31) })] } });
    const ui = await mountPage();
    assert.equal(ui.container.querySelector('[data-next-step="a-done"]'), null, "a waiting request is repeated on the front");
    await click(ui.container.querySelector('[data-hub-tab="past"]'));
    assert.ok(ui.container.querySelector('[data-hub-row="a-done"] [data-hire-state="requested"]'), "the request is not in Past");
    await ui.unmount();
});

test("only consultations from the last 30 days are on the front", async () => {
    api.__respond("listEngagements", { data: [] });
    api.__respond("listAppointments", { data: { items: [done({ id: "a-old", scheduled_at: inHours(-24 * 40), end_at: inHours(-24 * 40 + 1) }),
        appt({ id: "a-next", scheduled_at: inHours(30), end_at: inHours(31) })] } });
    const ui = await mountPage();
    assert.equal(ui.container.querySelector('[data-next-step="a-old"]'), null, "a 40-day-old consultation is still asking for a step");
    await ui.unmount();
});

test("once the lawyer is reviewed, the front card keeps Request to hire but drops Review", async () => {
    api.__respond("listEngagements", { data: [] });
    api.__respond("getReviewEligibility", { data: { can_review: false, already_reviewed: true }, error: null });
    api.__respond("listAppointments", { data: { items: [done(), appt({ id: "a-next", scheduled_at: inHours(30), end_at: inHours(31) })] } });
    const ui = await mountPage();
    await act(async () => { await new Promise(r => realSetTimeout(r, 40)); });
    const step = ui.container.querySelector('[data-next-step="a-done"]');
    assert.ok(step.querySelector("[data-next-hire]"));
    assert.equal(step.querySelector("[data-next-review]"), null, "Review is offered for a lawyer already reviewed");
    await ui.unmount();
});

test("a meeting the lawyer proposed shows its note as the lawyer's agenda, not 'Your note'", async () => {
    api.__respond("listEngagements", { data: [] });
    api.__respond("listAppointments", { data: { items: [appt({ id: "a-up", notes: "Discuss the documents", from_proposal: true, lawyer_card: card })] } });
    let ui = await mountPage();
    let page = ui.container.querySelector('[data-appointment-detail="a-up"]');
    assert.match(page.textContent, /Agenda from Kamran: “Discuss the documents”/);
    assert.doesNotMatch(page.textContent, /Your note/);
    await ui.unmount();
    api.__respond("listAppointments", { data: { items: [appt({ id: "a-up", notes: "My own note", lawyer_card: card })] } });
    ui = await mountPage();
    page = ui.container.querySelector('[data-appointment-detail="a-up"]');
    assert.match(page.textContent, /Your note: “My own note”/);
    await ui.unmount();
});

test("the client's row marks a meeting on a case the lawyer handles", async () => {
    api.__respond("listEngagements", { data: [] });
    api.__respond("listAppointments", { data: { items: [appt({ id: "a-c", case_meeting: true, case_number: "ATT-9" }), appt({ id: "a-g", scheduled_at: inHours(9), end_at: inHours(10) })] } });
    const ui = await mountPage();
    const row = ui.container.querySelector('[data-hub-row="a-c"]');
    assert.equal(row.querySelector("[data-case-meeting-chip]")?.textContent, "Case meeting · ATT-9");
    assert.equal(ui.container.querySelector('[data-hub-row="a-g"] [data-case-meeting-chip]'), null);
    await ui.unmount();
});
