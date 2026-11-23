/* My Matters (/tracking) opens the EXACT case a link names (2026-11-23).
 *
 * Tracking kept the open case in React state only and always chose the
 * newest of the first 20 cases, so "Open case" and every notification opened
 * the wrong case. Hire requests were also listed for EVERY case above the
 * selected one, so a client on Case A saw terms for Case B as if they were A's.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/tracking" });
function define(name, value) {
    Object.defineProperty(globalThis, name, { value, writable: true, configurable: true });
}
for (const name of ["window", "document", "navigator", "HTMLElement", "Element", "Node", "Event",
                    "CustomEvent", "MouseEvent", "MutationObserver", "getComputedStyle", "localStorage",
                    "requestAnimationFrame", "cancelAnimationFrame"]) {
    define(name, dom.window[name]);
}
define("IS_REACT_ACT_ENVIRONMENT", true);
dom.window.HTMLElement.prototype.scrollIntoView = function () {};

const React = (await import("react")).default;
const { act } = await import("react");
const { createRoot } = await import("react-dom/client");
const api = await import("./support/api-stub.mjs");
const h = React.createElement;
const realSetTimeout = setTimeout;
const nav = () => (globalThis.__nav ||= { pushed: [], replaced: [], params: new Map() });

async function mountTracking(params = {}) {
    nav().params.clear();
    for (const [k, v] of Object.entries(params)) nav().params.set(k, v);
    const Module7 = (await import("../src/components/client/ModTracking.jsx")).default;
    const { CaseCtx } = await import("../src/components/shared/CaseContext.jsx");
    const container = dom.window.document.createElement("div");
    dom.window.document.body.appendChild(container);
    const root = createRoot(container);
    const ctx = { notifications: [], markNotificationDone: () => {}, markAllNotificationsDone: () => {}, appointmentMilestones: [] };
    await act(async () => { root.render(h(CaseCtx.Provider, { value: ctx }, h(Module7, { isDark: true }))); });
    await act(async () => { await new Promise(r => realSetTimeout(r, 80)); });
    return { container, text: () => container.textContent,
             unmount: async () => { await act(async () => root.unmount()); container.remove(); } };
}

const caseRow = (id, title) => ({ _id: id, title, status: "open", case_number: id });

test.beforeEach(() => {
    api.__reset();
    api.__respond("bootstrapAuth", true);
    api.__respond("getMe", { data: { _id: "u1", role: "client" } });
    api.__respond("getNotifications", { data: { items: [] } });
    api.__respond("listAppointments", { data: { items: [] } });
    api.__respond("listCases", { data: { items: [caseRow("C1", "Newest matter"), caseRow("C2", "Rent dispute")] } });
    // Successful, empty reads by default: an unanswered read is a FAILED read
    // (and says so), not "nothing" (2026-11-23).
    api.__respond("listPayments", { data: [] });
    api.__respond("listMeetingProposals", { data: [] });
    api.__respond("myDocumentsV2", { data: { items: [] } });
    api.__respond("listDocuments", { data: [] });
    api.__respond("listMessages", { data: [] });
    api.__respond("listEngagements", { data: [
        { id: "E1", case_id: "C1", status: "requested", lawyer_name: "Adv Omar", case_title: "Newest matter" },
        { id: "E2", case_id: "C2", status: "terms_proposed", lawyer_name: "Adv Sana", case_title: "Rent dispute", fee_amount: 5000 },
    ] });
});
test.after(() => dom.window.close());

test("?case= opens that case, not the newest", async () => {
    const ui = await mountTracking({ case: "C2", tab: "summary" });
    assert.match(ui.text(), /Rent dispute/);
    assert.doesNotMatch(ui.text(), /Newest matter — /, "the newest case is shown as chosen");
    await ui.unmount();
});

test("a case outside the loaded list is read directly", async () => {
    api.__respond("getCase", { data: caseRow("C99", "Old land case") });
    const ui = await mountTracking({ case: "C99" });
    assert.equal(api.__calls("getCase").length, 1);
    assert.equal(api.__calls("getCase")[0].args[0], "C99");
    assert.match(ui.text(), /Old land case/);
    await ui.unmount();
});

test("a case that cannot be opened says so, and shows no other case instead", async () => {
    api.__respond("getCase", { data: null, error: { message: "Case not found" }, status: 404 });
    const ui = await mountTracking({ case: "GONE" });
    const box = ui.container.querySelector("[data-case-link-error]");
    assert.ok(box, "no cannot-open state");
    assert.match(box.textContent, /could not be opened/);
    assert.doesNotMatch(ui.text(), /Hire requests for this case|Adv Omar/, "another case's data was shown instead");
    await ui.unmount();
});

test("a draft case named in a link points to the intake", async () => {
    api.__respond("getCase", { data: { _id: "D1", title: "Draft", status: "draft" } });
    const ui = await mountTracking({ case: "D1" });
    assert.equal(ui.container.querySelector("[data-case-link-error]")?.getAttribute("data-case-link-error"), "draft");
    await ui.unmount();
});

test("hire requests belong to the open case; another case's terms are a link, not a row", async () => {
    const ui = await mountTracking({ case: "C1", tab: "summary" });
    const box = ui.container.querySelector("[data-hire-requests]");
    assert.ok(box, "hire requests missing");
    assert.match(box.textContent, /Hire requests for this case/);
    assert.ok(box.querySelector('[data-engagement="E1"]'), "this case's request is missing");
    assert.equal(box.querySelector('[data-engagement="E2"]'), null, "Case B's terms were listed as Case A's");
    const other = box.querySelector("[data-elsewhere-actions]");
    assert.ok(other, "terms waiting on another case were hidden");
    assert.match(other.textContent, /Adv Sana proposed terms for Rent dispute/);
    const open = [...other.querySelectorAll("button")].find(b => /Open case/.test(b.textContent));
    await act(async () => { open.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
    assert.equal(nav().pushed.at(-1), "/tracking?case=C2&tab=summary&engagement=E2");
    await ui.unmount();
});

test("?engagement= highlights that request", async () => {
    const ui = await mountTracking({ case: "C2", engagement: "E2" });
    const row = ui.container.querySelector('[data-engagement="E2"]');
    assert.ok(row, "the linked request is not on screen");
    assert.ok(row.hasAttribute("data-focused"), "the linked request is not highlighted");
    await ui.unmount();
});

test("a failed read of hire requests says so instead of hiding them", async () => {
    api.__respond("listEngagements", { data: null, error: { message: "Network error" }, status: 0 });
    const ui = await mountTracking({ case: "C1" });
    const err = ui.container.querySelector("[data-hire-requests-error]");
    assert.ok(err, "a failed read looked like 'no requests'");
    assert.match(err.textContent, /Couldn't load your hire requests/);
    await ui.unmount();
});

/* ── item 4: a failed read is never "nothing" (2026-11-23) ───────────────── */

test("a failed timeline read says so and can be retried", async () => {
    api.__respond("getCaseTimeline", { data: null, error: { message: "Network error" }, status: 0 });
    const ui = await mountTracking({ case: "C1", tab: "timeline" });
    const box = ui.container.querySelector('[data-timeline-state="error"]');
    assert.ok(box, "a failed timeline read looked like 'no hearings'");
    assert.match(box.textContent, /Couldn't load this case's timeline/);
    const calls = api.__calls("getCaseTimeline").length;
    api.__respond("getCaseTimeline", { data: { milestones: [], hearing_dates: [] } });
    const retry = [...box.querySelectorAll("button")].find(b => /Try again/.test(b.textContent));
    await act(async () => { retry.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
    await act(async () => { await new Promise(r => realSetTimeout(r, 60)); });
    assert.ok(api.__calls("getCaseTimeline").length > calls, "Try again did not read again");
    assert.equal(ui.container.querySelector('[data-timeline-state="error"]'), null);
    await ui.unmount();
});

test("payments under a case show ONLY that case's fees; All my payments holds the rest", async () => {
    api.__respond("listPayments", { data: [
        { id: "P1", case_id: "C1", amount: 3000, status: "paid", purpose: "peshi_fee", case_snapshot: { title: "Newest matter" } },
        { id: "P2", case_id: "C2", amount: 9000, status: "created", purpose: "professional_fee", case_snapshot: { title: "Rent dispute" } },
    ] });
    const ui = await mountTracking({ case: "C1", tab: "payments" });
    assert.match(ui.text(), /PKR 3,000/);
    assert.doesNotMatch(ui.text(), /PKR 9,000/, "another case's fee was listed under this case");
    // One case means one case (review item 4): no cross-case switch or note here.
    assert.equal(ui.container.querySelector("[data-payments-elsewhere]"), null);
    assert.equal([...ui.container.querySelectorAll("button")].find(b => b.textContent === "This case"), undefined);
    await click(ui.container.querySelector("[data-open-all-payments]"));
    assert.ok(ui.container.querySelector("[data-all-payments]"), "the link did not open All my payments");
    assert.equal(ui.container.querySelector("[data-case-bar]"), null);
    assert.match(ui.text(), /PKR 9,000/);
    await ui.unmount();
});

test("a failed payments read says a fee may be due, not 'no fee requests'", async () => {
    api.__respond("listPayments", { data: null, error: { message: "Network error" }, status: 0 });
    const ui = await mountTracking({ case: "C1", tab: "payments" });
    const err = ui.container.querySelector("[data-payments-error]");
    assert.ok(err, "a failed read looked like 'no fee requests'");
    assert.match(err.textContent, /A fee may be due/);
    assert.equal(ui.container.querySelector("[data-payments-empty]"), null);
    await ui.unmount();
});

test("?payment= opens that fee, switching to all payments when it is on another case", async () => {
    api.__respond("listPayments", { data: [
        { id: "P1", case_id: "C1", amount: 3000, status: "paid", purpose: "peshi_fee" },
        { id: "P3", case_id: "C2", amount: 9000, status: "failed", purpose: "professional_fee" },
    ] });
    // A link with a payment but no case opens All my payments (review item 2).
    const ui = await mountTracking({ tab: "payments", payment: "P3" });
    await act(async () => { await new Promise(r => realSetTimeout(r, 30)); });
    const row = ui.container.querySelector('[data-payment="P3"]');
    assert.ok(row, "the linked fee was hidden by the case filter");
    assert.ok(row.hasAttribute("data-focused"), "the linked fee is not highlighted");
    await ui.unmount();
});

test("a link to a payment that is not listed says so", async () => {
    api.__respond("listPayments", { data: [{ id: "P1", case_id: "C1", amount: 3000, status: "paid" }] });
    const ui = await mountTracking({ case: "C1", tab: "payments", payment: "GONE" });
    assert.ok(ui.container.querySelector("[data-payment-missing]"), "a missing payment was not mentioned");
    await ui.unmount();
});

/* ── item 7: decline / end / complete use an in-app dialog (2026-11-23) ──── */

const click = async el => { await act(async () => { el.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); }); };
const typeInto = async (el, value) => {
    const setter = Object.getOwnPropertyDescriptor(dom.window.HTMLTextAreaElement.prototype, "value").set;
    await act(async () => { setter.call(el, value); el.dispatchEvent(new dom.window.Event("input", { bubbles: true })); });
};
const btnIn = (root, re) => [...root.querySelectorAll("button")].find(b => re.test(b.textContent));
const dialog = () => dom.window.document.querySelector("[data-note-dialog]");

test("no browser prompt is used for hire request actions", async () => {
    const fs = await import("node:fs");
    const src = fs.readFileSync(new URL("../src/components/client/HireRequests.jsx", import.meta.url), "utf8");
    assert.doesNotMatch(src, /window\.prompt/);
});

test("Decline opens a dialog; Cancel sends nothing, Confirm sends the reason", async () => {
    let prompted = false;
    dom.window.prompt = () => { prompted = true; return ""; };
    api.__respond("declineEngagementTerms", { data: { id: "E2", status: "declined" } });
    const ui = await mountTracking({ case: "C2" });
    await click(btnIn(ui.container.querySelector('[data-engagement="E2"]'), /^Decline$/));
    assert.equal(prompted, false, "a browser prompt opened");
    assert.equal(dialog()?.getAttribute("data-note-dialog"), "decline");
    await click(dialog().querySelector("[data-note-cancel]"));
    assert.equal(dialog(), null, "Cancel did not close the dialog");
    assert.equal(api.__calls("declineEngagementTerms").length, 0, "Cancel declined the terms");

    await click(btnIn(ui.container.querySelector('[data-engagement="E2"]'), /^Decline$/));
    await typeInto(dialog().querySelector("textarea"), "  Too expensive  ");
    await click(dialog().querySelector("[data-note-confirm]"));
    const calls = api.__calls("declineEngagementTerms");
    assert.equal(calls.length, 1);
    assert.deepEqual(calls[0].args, ["E2", "Too expensive"]);
    assert.equal(dialog(), null, "the dialog stayed open after success");
    await ui.unmount();
});

test("ending an engagement needs a reason before it can be confirmed", async () => {
    api.__respond("listEngagements", { data: [{ id: "E5", case_id: "C1", status: "accepted", lawyer_name: "Adv Omar", case_title: "Newest matter" }] });
    api.__respond("terminateEngagement", { data: { id: "E5", status: "terminated" } });
    const ui = await mountTracking({ case: "C1" });
    await click(btnIn(ui.container.querySelector('[data-engagement="E5"]'), /End engagement/));
    assert.equal(dialog()?.getAttribute("data-note-dialog"), "end");
    assert.match(dialog().textContent, /released/);
    const confirm = dialog().querySelector("[data-note-confirm]");
    assert.ok(confirm.disabled, "End could be confirmed without a reason");
    await typeInto(dialog().querySelector("textarea"), "   ");
    assert.ok(dialog().querySelector("[data-note-confirm]").disabled, "a blank reason was accepted");
    await typeInto(dialog().querySelector("textarea"), "Moving abroad");
    await click(dialog().querySelector("[data-note-confirm]"));
    assert.deepEqual(api.__calls("terminateEngagement")[0].args, ["E5", "Moving abroad"]);
    await ui.unmount();
});

test("a failed action keeps the dialog open with the text", async () => {
    api.__respond("listEngagements", { data: [{ id: "E6", case_id: "C1", status: "accepted", lawyer_name: "Adv Omar", completion_proposed_by: "lawyer" }] });
    api.__respond("completeEngagement", { data: null, error: { message: "Network error" }, status: 0 });
    const ui = await mountTracking({ case: "C1" });
    await click(btnIn(ui.container.querySelector('[data-engagement="E6"]'), /Confirm complete/));
    assert.equal(dialog()?.getAttribute("data-note-dialog"), "confirmComplete");
    await typeInto(dialog().querySelector("textarea"), "Settled");
    await click(dialog().querySelector("[data-note-confirm]"));
    assert.deepEqual(api.__calls("completeEngagement")[0].args, ["E6", { note: "Settled" }]);
    assert.ok(dialog(), "a failed request closed the dialog and lost the note");
    assert.equal(dialog().querySelector("textarea").value, "Settled");
    await click(dialog().querySelector("[data-note-cancel]"));
    await ui.unmount();
});

/* ── item 8: controls that looked saved but were not (2026-11-23) ────────── */

const sideNav = async (ui, label) => {
    // Sidebar items are clickable divs; the label's own element bubbles the click up.
    const target = [...ui.container.querySelectorAll("div, span")].find(n => n.children.length === 0 && n.textContent.trim() === label);
    assert.ok(target, `no "${label}" in the sidebar`);
    await click(target);
    await act(async () => { await new Promise(r => realSetTimeout(r, 30)); });
};

test("timeline milestones have no browser-only 'Add Note / Tag Lawyer'", async () => {
    api.__respond("getCaseTimeline", { data: { milestones: [{ title: "Plaint filed", date: "2026-11-01T10:00:00Z", completed: true }], hearing_dates: [] } });
    const ui = await mountTracking({ case: "C1", tab: "timeline" });
    assert.match(ui.text(), /Plaint filed/);
    assert.doesNotMatch(ui.text(), /Add Note|Tag lawyer|Save Note/i);
    await ui.unmount();
});

test("no Reminders page or reminder controls remain (v2: what is due is on the Overview's to-do)", async () => {
    const ui = await mountTracking({ case: "C1" });
    assert.doesNotMatch(ui.text(), /All Events & Deadlines|New Reminder|Create Reminder|Set Custom Reminder|Action Required/);
    await ui.unmount();
});


/* ── item 9: one notification list, the app's drawer (2026-11-23) ────────── */

test("Tracking has no notifications list or bell of its own: the app sidebar's bell is the one", async () => {
    const ui = await mountTracking({ case: "C1" });
    const tabs = [...ui.container.querySelectorAll("[data-case-tab]")].map(b => b.textContent.trim());
    assert.ok(tabs.includes("Overview"), "the case tabs were not found");
    assert.ok(!tabs.includes("Notifications"), "Tracking still has its own Notifications page");
    assert.equal(ui.container.querySelector('button[aria-label="Notifications"]'), null, "Tracking still draws its own bell");
    assert.doesNotMatch(ui.text(), /Mark All Read|Sorted by urgency/, "a Tracking notifications list is still drawn");
    await ui.unmount();
});

/* ── v2 step A: one case bar, no second sidebar or top bar (2026-11-23) ───── */

test("the case bar names the case by title, never by its database id", async () => {
    api.__respond("listCases", { data: { items: [
        { ...caseRow("C1", "Newest matter"), case_number: "ATT-1" },
        { ...caseRow("C2", "Rent dispute"), case_number: "ATT-2" },
    ] } });
    const ui = await mountTracking({ case: "C2" });
    const bar = ui.container.querySelector("[data-case-bar]");
    assert.ok(bar, "no case bar");
    assert.equal(bar.querySelector("[data-case-bar-title]").textContent, "Rent dispute");
    assert.doesNotMatch(bar.textContent, /C2 —/, "the raw id is shown as the case's name");
    assert.equal(ui.container.querySelector('button[aria-label="Notifications"]'), null, "a second bell is drawn");
    await ui.unmount();
});

test("Switch lists the other cases by title and number, and opens the one chosen", async () => {
    api.__respond("listCases", { data: { items: [
        { ...caseRow("C1", "Newest matter"), case_number: "ATT-1" },
        { ...caseRow("C2", "Rent dispute"), case_number: "ATT-2" },
    ] } });
    const ui = await mountTracking({ case: "C2" });
    await click(ui.container.querySelector("[data-case-switch]"));
    const opts = [...ui.container.querySelectorAll("[data-case-option]")];
    assert.deepEqual(opts.map(o => o.textContent), ["Newest matter · ATT-1"], "the open case was offered, or ids were shown");
    await click(opts[0]);
    assert.equal(ui.container.querySelector("[data-case-bar-title]").textContent, "Newest matter");
    await ui.unmount();
});

test("the case's sections are real tabs, and the open one is marked", async () => {
    const ui = await mountTracking({ case: "C1", tab: "payments" });
    const tabs = [...ui.container.querySelectorAll("[data-case-tab]")];
    assert.deepEqual(tabs.map(b => b.textContent.trim()), ["Overview", "Timeline", "Documents", "Messages", "Payments"]);
    assert.ok(tabs.every(b => b.tagName === "BUTTON"), "a tab is not a button");
    assert.equal(ui.container.querySelector('[data-case-tab][aria-current="page"]').textContent, "Payments");
    await click(tabs[1]);
    assert.equal(ui.container.querySelector('[data-case-tab][aria-current="page"]').textContent, "Timeline");
    await ui.unmount();
});

/* ── v2 step B: the status card (2026-11-23) ─────────────────────────────── */

test("the status card leads with the next hearing, not a ring, a bar and the raw id", async () => {
    const { pktToday } = await import("../src/lib/bookingTime.js");
    const d = new Date(`${pktToday()}T12:00:00Z`); d.setUTCDate(d.getUTCDate() + 5);
    api.__respond("getCaseTimeline", { data: { milestones: [
        { title: "Notice sent", date: "2026-11-01T10:00:00Z", completed: true },
        { title: "First hearing", date: d.toISOString(), completed: false },
    ], hearing_dates: [{ _id: "h1", date: d.toISOString(), time: "10:00", court: "Civil Court, Lahore", outcome: null }] } });
    const ui = await mountTracking({ case: "C1" });
    const hero = ui.container.querySelector("[data-case-hero]");
    assert.ok(hero, "no status card");
    assert.equal(hero.querySelector("[data-hero-headline]").textContent, "Your next hearing is in 5 days");
    assert.match(hero.textContent, /Civil Court, Lahore/);
    assert.deepEqual([...hero.querySelectorAll("[data-stage]")].map(s => s.getAttribute("data-stage")), ["done", "now"]);
    assert.doesNotMatch(ui.text(), /CASE ID|\d+% ?done/, "the old card's id box or ring is still there");
    await ui.unmount();
});

test("terms on this case lead the card, and Review terms highlights the request below it", async () => {
    const ui = await mountTracking({ case: "C2" });
    const hero = ui.container.querySelector("[data-case-hero]");
    assert.equal(hero.getAttribute("data-case-hero"), "warn");
    assert.equal(hero.querySelector("[data-hero-headline]").textContent, "Adv Sana sent you terms");
    assert.equal(ui.container.querySelector('[data-engagement="E2"]').hasAttribute("data-focused"), false);
    await click(hero.querySelector('[data-hero-action="engagement"]'));
    assert.ok(ui.container.querySelector('[data-engagement="E2"]').hasAttribute("data-focused"), "the request was not highlighted");
    await ui.unmount();
});

test("with no milestones the stage line says so instead of drawing empty steps", async () => {
    api.__respond("getCaseTimeline", { data: { milestones: [], hearing_dates: [] } });
    const ui = await mountTracking({ case: "C1" });
    assert.ok(ui.container.querySelector("[data-hero-no-stages]"));
    assert.equal(ui.container.querySelector("[data-hero-headline]").textContent, "Waiting for Adv Omar to reply");
    await ui.unmount();
});

/* ── v2 step C: your to-do (2026-11-23) ──────────────────────────────────── */

test("a fee due on the case is on the to-do, and Pay now opens that fee in Payments", async () => {
    api.__respond("listPayments", { data: [
        { id: "P1", case_id: "C1", amount: 5000, status: "created", purpose: "peshi_fee" },
        { id: "P2", case_id: "C2", amount: 9000, status: "created", purpose: "professional_fee" },
    ] });
    const ui = await mountTracking({ case: "C1" });
    const box = ui.container.querySelector("[data-case-todos]");
    assert.ok(box, "no to-do");
    const cards = [...box.querySelectorAll("[data-todo]")];
    assert.deepEqual(cards.map(c => c.getAttribute("data-todo")), ["pay"], "another case's fee, or nothing, was listed");
    assert.match(cards[0].textContent, /PKR 5,000/);
    await click([...cards[0].querySelectorAll("button")].find(b => /Pay now/.test(b.textContent)));
    await act(async () => { await new Promise(r => realSetTimeout(r, 40)); });
    assert.equal(ui.container.querySelector('[data-case-tab][aria-current="page"]').textContent, "Payments");
    assert.ok(ui.container.querySelector('[data-payment="P1"]')?.hasAttribute("data-focused"), "the fee was not opened");
    await ui.unmount();
});

test("with nothing waiting, the to-do says so instead of showing empty cards", async () => {
    api.__respond("listPayments", { data: [] });
    const ui = await mountTracking({ case: "C1" });
    const box = ui.container.querySelector("[data-case-todos]");
    assert.equal(box.getAttribute("data-case-todos"), "0");
    assert.match(box.textContent, /Nothing is waiting on you right now/);
    assert.equal(box.querySelectorAll("[data-todo]").length, 0);
    await ui.unmount();
});

/* ── v2 step D: updates feed + reply + details (2026-11-23) ──────────────── */

const withLawyer = () => api.__respond("listEngagements", { data: [
    { id: "E9", case_id: "C1", status: "accepted", lawyer_name: "Adv. Ayesha Khan", fee_amount: 40000, fee_type: "fixed", accepted_at: "2026-11-10T09:00:00Z" },
] });
const typeIn = async (input, value) => {
    const setter = Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value").set;
    await act(async () => { setter.call(input, value); input.dispatchEvent(new dom.window.Event("input", { bubbles: true })); });
};

test("the updates feed shows the case's real messages and fees, newest first", async () => {
    withLawyer();
    api.__respond("listMessages", { data: [
        { _id: "m1", sender_role: "lawyer", sender_name: "Adv. Ayesha Khan", text: "Hearing fixed for 2 Dec.", created_at: "2026-11-22T06:00:00Z" },
        { _id: "m0", sender_role: "client", text: "Any news?", created_at: "2026-11-20T06:00:00Z" },
    ] });
    api.__respond("listPayments", { data: [{ id: "P1", case_id: "C1", amount: 3000, status: "paid", purpose: "professional_fee", paid_at: "2026-11-21T06:00:00Z", created_at: "2026-11-19T06:00:00Z" }] });
    const ui = await mountTracking({ case: "C1" });
    const feed = ui.container.querySelector("[data-case-updates]");
    assert.ok(feed, "no updates feed");
    const kinds = [...feed.querySelectorAll("[data-update]")].map(u => u.getAttribute("data-update"));
    assert.deepEqual(kinds, ["msg", "fee", "msg", "fee"], "not newest first, or an invented update");
    assert.match(feed.textContent, /Hearing fixed for 2 Dec\./);
    assert.match(feed.textContent, /You paid/);
    await ui.unmount();
});

test("a reply is sent to the case conversation and the feed re-reads", async () => {
    withLawyer();
    api.__respond("listMessages", { data: [] });
    api.__respond("sendMessage", { data: { _id: "m2", sender_role: "client", text: "Thanks", created_at: new Date().toISOString() } });
    const ui = await mountTracking({ case: "C1" });
    const input = ui.container.querySelector("[data-case-reply]");
    assert.ok(input, "no reply box with a lawyer on the case");
    assert.match(input.getAttribute("placeholder"), /Write to Ayesha/);
    await typeIn(input, "Thanks");
    const reads = api.__calls("listMessages").length;
    await click(ui.container.querySelector("[data-case-send]"));
    await act(async () => { await new Promise(r => realSetTimeout(r, 30)); });
    assert.deepEqual(api.__calls("sendMessage")[0].args, ["C1", "Thanks"]);
    assert.ok(api.__calls("listMessages").length > reads, "the feed did not re-read after sending");
    await ui.unmount();
});

test("a failed send keeps the text and says why", async () => {
    withLawyer();
    api.__respond("sendMessage", { data: null, error: { message: "Network error" }, status: 0 });
    const ui = await mountTracking({ case: "C1" });
    await typeIn(ui.container.querySelector("[data-case-reply]"), "Hello");
    await click(ui.container.querySelector("[data-case-send]"));
    assert.equal(ui.container.querySelector("[data-case-reply]").value, "Hello");
    assert.match(ui.text(), /Network error/);
    await ui.unmount();
});

test("with no lawyer on the case there is no reply box, and it says when there will be", async () => {
    const ui = await mountTracking({ case: "C1" });
    assert.equal(ui.container.querySelector("[data-case-reply]"), null);
    assert.match(ui.container.querySelector("[data-case-updates]").textContent, /once a lawyer takes your case/);
    await ui.unmount();
});

test("details show the agreed fee, what was paid and what is due, from real records", async () => {
    withLawyer();
    api.__respond("listPayments", { data: [
        { id: "P1", case_id: "C1", amount: 3000, status: "paid" },
        { id: "P2", case_id: "C1", amount: 5000, status: "created" },
        { id: "P3", case_id: "C2", amount: 9000, status: "created" },
    ] });
    const ui = await mountTracking({ case: "C1" });
    const money = ui.container.querySelector('[data-details="money"]');
    assert.match(money.textContent, /Agreed feePKR 40,000/);
    assert.match(money.textContent, /PaidPKR 3,000/);
    assert.match(money.textContent, /DuePKR 5,000/, "another case's fee was counted, or the due fee is missing");
    await click([...money.querySelectorAll("button")].find(b => b.textContent === "Payments"));
    assert.equal(ui.container.querySelector('[data-case-tab][aria-current="page"]').textContent, "Payments");
    await ui.unmount();
});

/* ── v2 step E: My matters (2026-11-23) ──────────────────────────────────── */

test("/tracking with no case opens My matters, not silently the newest case", async () => {
    const ui = await mountTracking({});
    assert.ok(ui.container.querySelector("[data-my-matters]"), "the newest case was opened instead of the list");
    assert.equal(ui.container.querySelector("[data-case-hero]"), null);
    const rows = [...ui.container.querySelectorAll("[data-matter]")];
    assert.equal(rows.length, 2);
    // Terms waiting on Rent dispute (C2) put it first, with the same sentence as its status card.
    assert.equal(rows[0].getAttribute("data-matter"), "C2");
    assert.equal(rows[0].querySelector("[data-matter-headline]").textContent, "Adv Sana sent you terms");
    assert.match(ui.container.querySelector("[data-matters-summary]").textContent, /1 thing is waiting on you/);
    await ui.unmount();
});

test("Open case opens that case, and My matters in the case bar goes back to the list", async () => {
    const ui = await mountTracking({});
    await click(ui.container.querySelector('[data-open-matter="C1"]'));
    assert.equal(ui.container.querySelector("[data-case-bar-title]").textContent, "Newest matter");
    assert.ok(ui.container.querySelector("[data-case-hero]"));
    await click(ui.container.querySelector("[data-to-matters]"));
    assert.ok(ui.container.querySelector("[data-my-matters]"), "My matters did not go back to the list");
    await ui.unmount();
});

test("a link naming only a tab still opens a case (old notices without a case id)", async () => {
    const ui = await mountTracking({ tab: "payments" });
    assert.equal(ui.container.querySelector("[data-my-matters]"), null);
    assert.equal(ui.container.querySelector('[data-case-tab][aria-current="page"]').textContent, "Payments");
    await ui.unmount();
});

test("no matters yet says so, with a way to start one", async () => {
    api.__respond("listCases", { data: { items: [] } });
    const ui = await mountTracking({});
    assert.ok(ui.container.querySelector("[data-matters-empty]"));
    assert.match(ui.text(), /No matters yet/);
    await ui.unmount();
});

test("a failed read of the matters says so instead of 'no matters'", async () => {
    api.__respond("listCases", { data: null, error: { message: "Network error" }, status: 0 });
    const ui = await mountTracking({});
    assert.ok(ui.container.querySelector("[data-matters-error]"));
    assert.equal(ui.container.querySelector("[data-matters-empty]"), null);
    await ui.unmount();
});

/* ── review item 1: a failed read is never "nothing waiting" (2026-11-23) ─── */

const FAIL = { data: null, error: { message: "Network error" }, status: 0 };

test("a failed fees read says the to-do could not be checked, never 'Nothing is waiting'", async () => {
    api.__respond("listPayments", FAIL);
    const ui = await mountTracking({ case: "C1" });
    const box = ui.container.querySelector("[data-case-todos]");
    assert.equal(box.getAttribute("data-todos-state"), "error");
    assert.doesNotMatch(box.textContent, /Nothing is waiting/);
    assert.match(box.textContent, /Couldn't check your fees\. Something may be waiting on you\./);
    // Try again re-reads, and a good answer clears it.
    api.__respond("listPayments", { data: [] });
    const calls = api.__calls("listPayments").length;
    await click([...box.querySelectorAll("button")].find(b => b.textContent === "Try again"));
    await act(async () => { await new Promise(r => realSetTimeout(r, 30)); });
    assert.ok(api.__calls("listPayments").length > calls, "Try again did not read again");
    assert.match(ui.container.querySelector("[data-case-todos]").textContent, /Nothing is waiting on you right now/);
    await ui.unmount();
});

test("V2 documents switched off are 'none', not a failure", async () => {
    api.__respond("myDocumentsV2", { data: null, status: 404, error: { code: "feature_disabled", message: "off" } });
    const ui = await mountTracking({ case: "C1" });
    assert.equal(ui.container.querySelector("[data-case-todos]").getAttribute("data-todos-state"), "ready");
    await ui.unmount();
});

test("a failed hire-request read never claims 'No lawyer on this case yet'", async () => {
    api.__respond("listEngagements", FAIL);
    api.__respond("getCaseTimeline", { data: { milestones: [], hearing_dates: [] } });
    const ui = await mountTracking({ case: "C1" });
    const hero = ui.container.querySelector("[data-case-hero]");
    assert.equal(hero.querySelector("[data-hero-headline]").textContent, "Couldn't check this case's latest status");
    assert.doesNotMatch(hero.textContent, /No lawyer on this case yet|Find a lawyer/);
    api.__respond("listEngagements", { data: [] });
    await click(hero.querySelector('[data-hero-action="retry-engagements"]'));
    await act(async () => { await new Promise(r => realSetTimeout(r, 30)); });
    assert.equal(ui.container.querySelector("[data-hero-headline]").textContent, "No lawyer on this case yet");
    await ui.unmount();
});

test("details say a failed read instead of PKR 0 or 0 documents", async () => {
    api.__respond("listPayments", FAIL);
    api.__respond("listDocuments", FAIL);
    const ui = await mountTracking({ case: "C1" });
    const money = ui.container.querySelector('[data-details="money"]');
    const files = ui.container.querySelector('[data-details="files"]');
    assert.match(money.textContent, /Couldn't load the fees on this case/);
    assert.doesNotMatch(money.textContent, /PKR 0/);
    assert.match(files.textContent, /Couldn't load this case's documents/);
    assert.match(ui.container.querySelector("[data-case-updates]").textContent, /Couldn't load the fees and documents on this case/);
    assert.equal(ui.container.querySelector("[data-updates-empty]"), null, "'Nothing has happened' was shown over failed reads");
    await ui.unmount();
});

test("My matters says it could not check, instead of 'Nothing is waiting'", async () => {
    api.__respond("listMeetingProposals", FAIL);
    api.__respond("listEngagements", { data: [] });
    const ui = await mountTracking({});
    const summary = ui.container.querySelector("[data-matters-summary]");
    assert.match(summary.textContent, /Couldn't check your meeting times/);
    assert.doesNotMatch(summary.textContent, /Nothing is waiting/);
    assert.ok([...ui.container.querySelectorAll("[data-matter]")].every(r => /Couldn't check/.test(r.textContent)), "a case claimed nothing was waiting");
    await ui.unmount();
});

/* ── review item 1, round 2: stale data, assigned lawyers, partial counts ─── */

const notify = async (n) => {
    const { broadcastNotification } = await import("../src/lib/notificationTarget.js");
    await act(async () => { broadcastNotification(n); });
    await act(async () => { await new Promise(r => realSetTimeout(r, 30)); });
};

test("an empty list that then fails to refresh no longer says 'Nothing is waiting'", async () => {
    const ui = await mountTracking({ case: "C1" });
    const box = () => ui.container.querySelector("[data-case-todos]");
    assert.match(box().textContent, /Nothing is waiting on you right now/);
    // A fee is requested; the refresh its notification triggers fails.
    api.__respond("listPayments", FAIL);
    await notify({ type: "payment_requested", payload: { case_id: "C1", payment_id: "P9" } });
    assert.equal(box().getAttribute("data-todos-state"), "error");
    assert.doesNotMatch(box().textContent, /Nothing is waiting/);
    assert.match(box().textContent, /Couldn't check your fees/);
    await ui.unmount();
});

test("a case WITH a lawyer whose hire request cannot be read shows a warning and Try again", async () => {
    api.__respond("listCases", { data: { items: [{ ...caseRow("C1", "Newest matter"), lawyer_id: "L1" }] } });
    api.__respond("listEngagements", FAIL);
    api.__respond("getCaseTimeline", { data: { milestones: [], hearing_dates: [] } });
    const ui = await mountTracking({ case: "C1" });
    const hero = ui.container.querySelector("[data-case-hero]");
    assert.equal(hero.querySelector("[data-hero-headline]").textContent, "Couldn't check this case's latest status");
    assert.doesNotMatch(hero.textContent, /is working on your case/, "the card claimed the lawyer is working over a failed read");
    assert.ok(hero.querySelector('[data-hero-action="retry-engagements"]'), "no Try again");
    await ui.unmount();
});

test("a hearing still leads when the hire request cannot be read, but a warning says it may be out of date", async () => {
    const { pktToday } = await import("../src/lib/bookingTime.js");
    const d = new Date(`${pktToday()}T12:00:00Z`); d.setUTCDate(d.getUTCDate() + 3);
    api.__respond("listCases", { data: { items: [{ ...caseRow("C1", "Newest matter"), lawyer_id: "L1" }] } });
    api.__respond("listEngagements", FAIL);
    api.__respond("getCaseTimeline", { data: { milestones: [], hearing_dates: [{ _id: "h1", date: d.toISOString(), outcome: null }] } });
    const ui = await mountTracking({ case: "C1" });
    const hero = ui.container.querySelector("[data-case-hero]");
    assert.equal(hero.querySelector("[data-hero-headline]").textContent, "Your next hearing is in 3 days");
    assert.match(hero.querySelector("[data-hero-warning]").textContent, /Couldn't check the latest on your hire request/);
    await ui.unmount();
});

test("My matters marks a partial count as unfinished while a check is still running", async () => {
    api.__respond("listPayments", { data: [{ id: "P1", case_id: "C1", amount: 5000, status: "created" }] });
    api.__respond("listMeetingProposals", () => new Promise(() => {}));   // still loading
    api.__respond("listEngagements", { data: [] });
    const ui = await mountTracking({});
    const summary = ui.container.querySelector("[data-matters-summary]").textContent;
    assert.match(summary, /1 thing found so far · Still checking…/);
    assert.doesNotMatch(summary, /is waiting on you across your matters/, "a partial count was shown as final");
    await ui.unmount();
});

test("the to-do marks a partial list as unfinished while a check is still running", async () => {
    api.__respond("listPayments", { data: [{ id: "P1", case_id: "C1", amount: 5000, status: "created" }] });
    api.__respond("listMeetingProposals", () => new Promise(() => {}));
    const ui = await mountTracking({ case: "C1" });
    assert.match(ui.container.querySelector("[data-case-todos]").textContent, /1 found so far · Still checking…/);
    await ui.unmount();
});

test("hire requests that fail to refresh keep the list but say it may be out of date", async () => {
    const ui = await mountTracking({ case: "C1" });
    assert.equal(ui.container.querySelector("[data-hire-requests-stale]"), null);
    api.__respond("listEngagements", FAIL);
    await notify({ type: "engagement_terms_proposed", payload: { case_id: "C1", engagement_id: "E1" } });
    assert.ok(ui.container.querySelector("[data-hire-requests-stale]"), "a failed refresh was shown as current");
    assert.ok(ui.container.querySelector('[data-engagement="E1"]'), "the list was dropped");
    await ui.unmount();
});

/* ── review item 2: a fee link without a case opens All my payments ───────── */

test("a fee link with no case opens All my payments with no case header", async () => {
    api.__respond("listPayments", { data: [
        { id: "P1", case_id: "C1", amount: 3000, status: "paid", purpose: "peshi_fee" },
        { id: "P3", case_id: "C2", amount: 9000, status: "failed", purpose: "professional_fee" },
    ] });
    const ui = await mountTracking({ view: "payments", payment: "P3" });
    await act(async () => { await new Promise(r => realSetTimeout(r, 30)); });
    assert.ok(ui.container.querySelector("[data-all-payments]"), "not the All my payments view");
    assert.equal(ui.container.querySelector("[data-case-bar]"), null, "a case header was shown over the fee");
    assert.equal(ui.container.querySelector("[data-case-hero]"), null);
    assert.ok(ui.container.querySelector('[data-payment="P1"]') && ui.container.querySelector('[data-payment="P3"]'), "not every fee is listed");
    assert.ok(ui.container.querySelector('[data-payment="P3"]').hasAttribute("data-focused"));
    await ui.unmount();
});

test("an old link naming a payment but no case also opens All my payments", async () => {
    api.__respond("listPayments", { data: [{ id: "P3", case_id: "C2", amount: 9000, status: "failed" }] });
    const ui = await mountTracking({ tab: "payments", payment: "P3" });
    assert.ok(ui.container.querySelector("[data-all-payments]"));
    assert.equal(ui.container.querySelector("[data-case-bar]"), null);
    await ui.unmount();
});

test("My matters links to All my payments, and back", async () => {
    const ui = await mountTracking({});
    await click(ui.container.querySelector("[data-open-all-payments]"));
    assert.ok(ui.container.querySelector("[data-all-payments]"));
    await click(ui.container.querySelector("[data-all-payments] [data-to-matters]"));
    assert.ok(ui.container.querySelector("[data-my-matters]"));
    await ui.unmount();
});

/* ── review item 3: Back and Forward step through Tracking (2026-11-23) ───── */

const back = async () => { await act(async () => { dom.window.history.back(); await new Promise(r => realSetTimeout(r, 60)); }); };
const forward = async () => { await act(async () => { dom.window.history.forward(); await new Promise(r => realSetTimeout(r, 60)); }); };
const activeTab = ui => ui.container.querySelector('[data-case-tab][aria-current="page"]')?.textContent;

test("a tab is a history entry: Back returns to the previous tab, Forward again", async () => {
    dom.window.history.replaceState(null, "", "/tracking");
    const ui = await mountTracking({ case: "C1" });
    assert.equal(activeTab(ui), "Overview");
    await click(ui.container.querySelector('[data-case-tab="timeline"]'));
    assert.equal(dom.window.location.search, "?case=C1&tab=timeline");
    assert.equal(activeTab(ui), "Timeline");
    await back();
    assert.equal(activeTab(ui), "Overview", "Back did not return to the previous tab");
    await forward();
    assert.equal(activeTab(ui), "Timeline", "Forward did not return to the tab");
    await ui.unmount();
});

test("opening a case from My matters is a history entry: Back returns to My matters", async () => {
    dom.window.history.replaceState(null, "", "/tracking");
    const ui = await mountTracking({});
    await click(ui.container.querySelector('[data-open-matter="C2"]'));
    assert.equal(dom.window.location.search, "?case=C2&tab=summary");
    assert.ok(ui.container.querySelector("[data-case-hero]"));
    await back();
    assert.ok(ui.container.querySelector("[data-my-matters]"), "Back did not return to My matters");
    await ui.unmount();
});

test("All my payments is a history entry, and its back link is a visible button", async () => {
    dom.window.history.replaceState(null, "", "/tracking");
    const ui = await mountTracking({});
    await click(ui.container.querySelector("[data-open-all-payments]"));
    assert.equal(dom.window.location.search, "?view=payments");
    const link = ui.container.querySelector("[data-all-payments] [data-to-matters]");
    assert.equal(link.tagName, "BUTTON");
    assert.match(link.textContent, /My matters/);
    assert.ok(link.querySelector("svg"), "the back link has no arrow");
    await back();
    assert.ok(ui.container.querySelector("[data-my-matters]"), "Back did not leave All my payments");
    await ui.unmount();
});

/* ── Documents + Payments tabs, redesigned (2026-11-23, approved preview) ─── */

const v2doc = (id, title, review_status, over = {}) => ({ id, title, review_status, case_id: "C1", revision_id: "r" + id,
    pdf_sha256: "h" + id, downloadable: true, created_at: "2026-11-20T05:00:00Z", ...over });

test("documents: a returned document leads under Needs you, once, and the rest is a plain list", async () => {
    api.__respond("myDocumentsV2", { data: { items: [v2doc("v1", "Written statement", "returned"), v2doc("v2", "Plaint", "approved")] } });
    const ui = await mountTracking({ case: "C1", tab: "documents" });
    const need = ui.container.querySelector("[data-docs-needs-you]");
    assert.ok(need, "no Needs you section");
    assert.ok(need.querySelector('[data-doc="v1"]'), "the returned document is not under Needs you");
    assert.match(need.textContent, /Your lawyer sent it back/);
    assert.equal(ui.container.querySelectorAll('[data-doc="v1"]').length, 1, "the returned document is listed twice");
    const row = ui.container.querySelector('[data-doc="v2"]');
    assert.equal(row.querySelector("[data-doc-status]").textContent, "Final", "not the app's own status word");
    const labels = [...row.querySelectorAll("button")].map(b => b.textContent);
    assert.deepEqual(labels, ["Open", "Download"]);
    assert.doesNotMatch(ui.text(), /from your lawyer|from you/, "who shared it is not on record");
    await ui.unmount();
});

test("documents: nothing on the case is one friendly panel, with no toolbar or '0 files'", async () => {
    const ui = await mountTracking({ case: "C1", tab: "documents" });
    const empty = ui.container.querySelector("[data-docs-empty]");
    assert.ok(empty, "no empty state");
    assert.match(empty.textContent, /No documents on this case yet/);
    assert.ok(empty.querySelector("[data-draft-document]"));
    assert.equal(ui.container.querySelector('select[aria-label="Sort documents"]'), null);
    assert.doesNotMatch(ui.text(), /0 files/);
    await ui.unmount();
});

test("documents: search appears only above 5, and a version without a PDF says so", async () => {
    const six = ["a", "b", "c", "d", "e", "f"].map(k => v2doc(k, "Doc " + k, "approved"));
    api.__respond("myDocumentsV2", { data: { items: six } });
    let ui = await mountTracking({ case: "C1", tab: "documents" });
    assert.ok(ui.container.querySelector('input[placeholder="Search"]'), "no search with 6 documents");
    await ui.unmount();
    api.__respond("myDocumentsV2", { data: { items: [v2doc("a", "Doc a", "approved"), v2doc("b", "Doc b", "none", { downloadable: false })] } });
    ui = await mountTracking({ case: "C1", tab: "documents" });
    assert.equal(ui.container.querySelector('input[placeholder="Search"]'), null, "search over 2 documents");
    const noPdf = ui.container.querySelector('[data-doc="b"]');
    assert.match(noPdf.textContent, /PDF not ready yet/);
    assert.equal(noPdf.querySelectorAll("button").length, 0, "Open/Download offered without a PDF");
    await ui.unmount();
});

test("payments: one fee due is the big card with one Pay, and is not repeated in the history", async () => {
    api.__respond("listPayments", { data: [
        { id: "P1", case_id: "C1", amount: 5000, status: "created", purpose: "peshi_fee", expires_at: "2026-11-27T10:00:00Z", payee_snapshot: { name: "Adv. Ayesha" } },
        { id: "P2", case_id: "C1", amount: 3000, status: "paid", purpose: "professional_fee", paid_at: "2026-11-11T10:00:00Z" },
    ] });
    const ui = await mountTracking({ case: "C1", tab: "payments" });
    const card = ui.container.querySelector("[data-amount-due]");
    assert.ok(card, "no amount-due card");
    assert.match(card.textContent, /PKR 5,000/);
    assert.match(card.textContent, /Pay by 27 Nov/);
    assert.equal(ui.container.querySelectorAll('[data-payment="P1"]').length, 1, "the due fee is shown twice");
    const hist = ui.container.querySelector("[data-payment-history]");
    assert.ok(hist.querySelector('[data-payment="P2"]'));
    assert.match(hist.textContent, /Receipt ↓/);
    await ui.unmount();
});

test("payments: two fees due show their total and one Pay each; nothing due says so", async () => {
    api.__respond("listPayments", { data: [
        { id: "P1", case_id: "C1", amount: 5000, status: "created", purpose: "peshi_fee" },
        { id: "P3", case_id: "C1", amount: 2000, status: "failed", purpose: "professional_fee" },
    ] });
    let ui = await mountTracking({ case: "C1", tab: "payments" });
    const card = ui.container.querySelector("[data-amount-due]");
    assert.match(card.textContent, /2 fees due/);
    assert.match(card.textContent, /PKR 7,000/);
    const pays = [...card.querySelectorAll("button")].map(b => b.textContent);
    assert.equal(pays.length, 2);
    assert.ok(pays.some(l => /Try again · Pay PKR 2,000/.test(l)), "a failed fee is not payable again");
    await ui.unmount();
    api.__respond("listPayments", { data: [{ id: "P2", case_id: "C1", amount: 3000, status: "paid", purpose: "professional_fee" }] });
    ui = await mountTracking({ case: "C1", tab: "payments" });
    assert.ok(ui.container.querySelector("[data-nothing-due]"), "no 'nothing due' line");
    assert.equal(ui.container.querySelector("[data-amount-due]"), null);
    await ui.unmount();
});

test("payments: the agreed-fee line counts professional fees only, and only for a fixed fee", async () => {
    api.__respond("listEngagements", { data: [{ id: "E9", case_id: "C1", status: "accepted", fee_amount: 40000, fee_type: "fixed" }] });
    api.__respond("listPayments", { data: [
        { id: "P2", case_id: "C1", amount: 3000, status: "paid", purpose: "professional_fee" },
        { id: "P4", case_id: "C1", amount: 5000, status: "paid", purpose: "peshi_fee" },
    ] });
    let ui = await mountTracking({ case: "C1", tab: "payments" });
    const line = ui.container.querySelector("[data-agreed-fee]");
    assert.match(line.textContent, /PKR 3,000 paid of PKR 40,000 agreed/, "a peshi fee was counted toward the agreed fee");
    assert.match(line.textContent, /PKR 37,000 left/);
    await ui.unmount();
    api.__respond("listEngagements", { data: [{ id: "E9", case_id: "C1", status: "accepted", fee_amount: 3000, fee_type: "per_hearing" }] });
    ui = await mountTracking({ case: "C1", tab: "payments" });
    const rate = ui.container.querySelector("[data-agreed-fee]");
    assert.match(rate.textContent, /Agreed rate: PKR 3,000\/hearing/);
    assert.doesNotMatch(rate.textContent, /left/, "a per-hearing rate showed an amount left");
    await ui.unmount();
});
