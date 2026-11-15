/* Lawyer Cases redesign: the list sorted by what needs doing, and a workspace
 * with Overview / Schedule / Messages / Tasks / Documents.
 *
 * UI only over existing routes. What these pin down:
 *   * The list groups cases by what the lawyer must do next and hides closed
 *     ones behind History; new client requests are actionable from the list.
 *   * "Send terms" still goes through the fee step: a request is never
 *     accepted without a price the client sees first.
 *   * The workspace's counts come from the server (tasks, messages), quick
 *     replies only prefill, templates create real tasks, and the Documents
 *     tab lists the case's server documents.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/" });
function define(name, value) {
    Object.defineProperty(globalThis, name, { value, writable: true, configurable: true });
}
for (const name of ["window", "document", "navigator", "HTMLElement", "HTMLInputElement", "Element",
                    "Node", "Event", "CustomEvent", "MouseEvent", "KeyboardEvent", "MutationObserver",
                    "getComputedStyle", "localStorage", "sessionStorage"]) {
    define(name, dom.window[name]);
}
define("IS_REACT_ACT_ENVIRONMENT", true);

const React = (await import("react")).default;
const { act, useState } = await import("react");
const { createRoot } = await import("react-dom/client");
const api = await import("./support/api-stub.mjs");
const { CaseCtx } = await import("../src/components/lawyer/theme.js");
const { CasesPage } = await import("../src/components/lawyer/CasesPage.jsx");
const { pktToday } = await import("../src/lib/bookingTime.js");
const h = React.createElement;

const settle = (ms = 40) => act(async () => { await new Promise(r => setTimeout(r, ms)); });

function addDays(n) {
    const d = new Date(`${pktToday()}T12:00:00Z`);
    d.setUTCDate(d.getUTCDate() + n);
    return d.toISOString().slice(0, 10);
}
const hearing = (id, date, purpose, extra = {}) =>
    ({ _id: id, date: `${date}T00:00:00Z`, time: "10:00", court: "Civil Court Lahore", judge: "", purpose, ...extra });
const kase = (n, status, hearings = []) => ({
    _id: `665f0000000000000000000${n}`, case_number: `CIV-2026-00${n}`, title: `Matter ${n}`,
    client_name: `Client ${n}`, province: "punjab", case_type: "civil", status, hearing_dates: hearings,
});
const SOON = kase(1, "in_progress", [hearing("h1", addDays(5), "Framing of issues")]);
const LATER = kase(2, "in_progress", [hearing("h2", addDays(40), "Evidence")]);
const NONE = kase(3, "open");
const SHUT = kase(4, "closed");
const REQUEST = { id: "e1", status: "requested", case_id: "c9", case_title: "Inheritance claim",
                  case_number: "CIV-2026-009", case_type: "family", client_name: "Sara Khan",
                  message: "Please take my case", created_at: `${addDays(-2)}T09:00:00Z` };

function Host({ openAt = null, pages = [] }) {
    const [openCaseId, setOpenCaseId] = useState(openAt);
    return h(CaseCtx.Provider, {
        value: { openCaseId, setOpenCaseId, activeCase: null, setActiveCase: () => {}, docs: {}, setDocs: () => {},
                 setPage: p => pages.push(p) },
    }, h(CasesPage));
}
async function mount(props = {}) {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => { root.render(h(Host, props)); });
    await settle();
    // Queries run from <body>: the page's dialogs render there (a portal), not
    // inside the page's own container.
    return { container: document.body, unmount: async () => { await act(async () => root.unmount()); container.remove(); } };
}
const allButtons = (root) => [...root.querySelectorAll("button")];
const buttonText = (root, text) => allButtons(root).find(b => b.textContent.trim() === text);
const tab = (root, name) => [...root.querySelectorAll('[role="tab"]')].find(b => b.textContent.startsWith(name));
async function click(el) {
    assert.ok(el, "element to click was not found");
    await act(async () => { el.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    await settle();
}
async function type(el, value) {
    const proto = el.tagName === "TEXTAREA" ? dom.window.HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
    await act(async () => { el.dispatchEvent(new Event("input", { bubbles: true })); });
}
const sectionTitles = (root) => [...root.querySelectorAll("span")]
    .map(s => s.textContent.trim()).filter(t => ["New hire requests", "No hearing yet", "Active", "History"].includes(t));

test.beforeEach(() => {
    api.__reset();
    api.__respond("listCases", { data: { items: [LATER, SOON, NONE, SHUT] }, error: null });
    api.__respond("listEngagements", { data: [REQUEST], error: null });
    api.__respond("listTasks", { data: [], error: null });
    api.__respond("listMessages", { data: [], error: null });
    api.__respond("listDocuments", { data: [], error: null });
});

/* ── list ─────────────────────────────────────────────────────────────── */

test("the list groups by what to do next, sorts by next hearing, and hides closed cases", async () => {
    const view = await mount();
    const text = view.container.textContent;
    assert.match(text, /4 cases/);
    assert.match(text, /1 new request to accept/);
    // Requests first, then cases with no date, then active by next hearing.
    const order = ["Inheritance claim", "CIV-2026-003", "CIV-2026-001", "CIV-2026-002"].map(t => text.indexOf(t));
    assert.ok(order.every(i => i >= 0) && order.every((v, i) => !i || v > order[i - 1]), `wrong order: ${order}`);
    assert.doesNotMatch(text, /CIV-2026-004/, "a closed case is in the live list");
    assert.match(text, /in 5 days/);

    await click(allButtons(view.container).find(b => b.getAttribute("role") === "tab" && b.textContent.trim().startsWith("Closed")));
    assert.match(view.container.textContent, /CIV-2026-004/);
    await view.unmount();
});

test("search filters every group by title, client or case number", async () => {
    const view = await mount();
    await type(view.container.querySelector('input[placeholder^="Search"]'), "client 2");
    const text = view.container.textContent;
    assert.match(text, /CIV-2026-002/);
    assert.doesNotMatch(text, /CIV-2026-001|CIV-2026-003|Inheritance claim/);
    await view.unmount();
});

test("Send terms asks for a fee before anything is sent", async () => {
    api.__respond("proposeEngagementTerms", { data: { status: "terms_proposed" }, error: null });
    const view = await mount();
    await click(buttonText(view.container, "Send terms"));
    assert.match(view.container.textContent, /Send your terms/);
    const dlg = view.container.querySelector("[data-terms]");
    // Who and what it is for (2026-10-20): the client and the case, not a
    // case title run into the instructions.
    assert.match(dlg.textContent, /Sara Khan/);
    assert.match(dlg.textContent, /Inheritance claim/);
    const send = dlg.querySelector("[data-terms-send]");
    assert.equal(send.textContent, "Send terms to Sara");
    await click(send);
    assert.equal(api.__calls("proposeEngagementTerms").length, 0, "terms were sent without a fee");
    assert.match(dlg.querySelector("[data-terms-error]").textContent, /Enter the fee/, "the missing fee was not said in the dialog");

    await type(dlg.querySelector('input[type="number"]'), "50000");
    assert.equal(dlg.querySelector("[data-terms-error]"), null, "the error stayed after a fee was typed");
    assert.match(dlg.querySelector("[data-terms-preview]").textContent, /Sara will see Rs 50,000 · Fixed fee \(whole case\)/);
    await click(dlg.querySelector('[data-fee-type="per_hearing"]'));
    assert.match(dlg.querySelector("[data-terms-preview]").textContent, /Per hearing/);
    await click(send);
    const [id, body] = api.__calls("proposeEngagementTerms")[0].args;
    assert.equal(id, "e1");
    assert.equal(body.fee_amount, 50000);
    assert.equal(body.fee_type, "per_hearing");
    await view.unmount();
});

test("Export downloads the cases as CSV", async () => {
    let blob = null;
    const realCreate = URL.createObjectURL;
    URL.createObjectURL = (b) => { blob = b; return "blob:x"; };
    URL.revokeObjectURL = () => {};
    try {
        const view = await mount();
        await click(view.container.querySelector('button[aria-label="Export cases"]'));
        const csv = (await blob.text()).replace(/^﻿/, "");
        const lines = csv.trim().split("\r\n");
        assert.match(lines[0], /^"Case no.","Title","Client"/);
        assert.equal(lines.length, 5);
        await view.unmount();
    } finally {
        URL.createObjectURL = realCreate;
    }
});

/* ── workspace ────────────────────────────────────────────────────────── */

test("the header shows the stage; the tabs count what the server holds", async () => {
    api.__respond("listTasks", { data: [{ _id: "t1", title: "Brief", done: true }, { _id: "t2", title: "Witnesses", done: false }], error: null });
    api.__respond("listMessages", { data: [{ _id: "m1", sender_role: "client", text: "Salam", sender_name: "Client 1" }], error: null });
    const view = await mount({ openAt: SOON.case_number });
    const text = view.container.textContent;
    assert.match(text, /Hearing set/);
    // The open-task count rides on the Tasks tab (2026-10-09: the count strip
    // was replaced by tab badges), and the next date leads the Overview.
    assert.match(tab(view.container, "Tasks").textContent, /^Tasks1$/);
    assert.match(tab(view.container, "Messages").textContent, /^Messages1$/);
    assert.match(text, /in 5 days · \w{3} \d{1,2} \w{3}, 10:00 AM/);
    assert.match(text, /Next: \w{3} \d{1,2} \w{3}/, "the current stage does not say when the next step is");
    const header = view.container.querySelector('[aria-label^="Stage:"]');
    assert.equal(header.getAttribute("aria-label"), "Stage: Hearing set");
    await view.unmount();
});

test("with no hearing, the next step saves one from the overview", async () => {
    api.__respond("addHearing", { data: { ...NONE, hearing_dates: [hearing("hx", addDays(10), "Hearing")] }, error: null });
    const view = await mount({ openAt: NONE.case_number });
    assert.match(view.container.textContent, /Set the first hearing date/);
    const labelled = (name) => [...view.container.querySelectorAll("label")].find(l => l.textContent.trim() === name).parentElement.querySelector("input");
    await type(labelled("Date"), addDays(10));
    await type(labelled("Court"), "Civil Court Lahore");
    await click(buttonText(view.container, "Save hearing"));
    const [caseId, body] = api.__calls("addHearing")[0].args;
    assert.equal(caseId, NONE._id);
    assert.equal(body.court, "Civil Court Lahore");
    assert.match(view.container.textContent, /Prepare for/, "the next step did not move on");
    await view.unmount();
});

test("a quick reply only fills the box; Send sends it", async () => {
    api.__respond("sendMessage", { data: { _id: "m9", sender_role: "lawyer", text: "x" }, error: null });
    const view = await mount({ openAt: SOON.case_number });
    await click(tab(view.container, "Messages"));
    await click(buttonText(view.container, "Share next hearing date"));
    assert.equal(api.__calls("sendMessage").length, 0, "a quick reply sent a message by itself");
    const box = view.container.querySelector('input[placeholder^="Write to"]');
    assert.match(box.value, /next hearing is on .* Civil Court Lahore/);
    await click(view.container.querySelector('button[aria-label="Send message"]'));
    assert.equal(api.__calls("sendMessage")[0].args[0], SOON._id);
    await view.unmount();
});

test("a task template creates each task through the server", async () => {
    let n = 0;
    api.__respond("addTask", (caseId, body) => ({ data: { _id: `t${++n}`, title: body.title, done: false }, error: null }));
    const view = await mount({ openAt: SOON.case_number });
    await click(tab(view.container, "Tasks"));
    await click(allButtons(view.container).find(b => b.textContent.includes("Pre-hearing checklist")));
    await settle(60);
    const titles = api.__calls("addTask").map(c => c.args[1].title);
    assert.equal(titles.length, 5);
    assert.equal(titles[0], "File vakalatnama");
    assert.match(view.container.textContent, /0\/5/);
    await view.unmount();
});

test("the Documents tab lists the case's documents from the server", async () => {
    api.__respond("listDocuments", { data: [{ _id: "d1", title: "Plaint draft", template_type: "civil_plaint", status: "draft" }], error: null });
    const pages = [];
    const view = await mount({ openAt: SOON.case_number, pages });
    await click(tab(view.container, "Documents"));
    assert.equal(api.__calls("listDocuments")[0].args[0], SOON._id);
    assert.match(view.container.textContent, /Plaint draft/);
    await click(buttonText(view.container, "Draft a document"));
    assert.deepEqual(pages, ["doc-automation"]);
    await view.unmount();
});

/* ── the filter bar, + Task, follow-up tasks after an outcome ────────── */

test("the bar: chips, History on the right, then search, Sort and Filter", async () => {
    const view = await mount();
    const chips = [...view.container.querySelectorAll('[role="tablist"][aria-label="Filter cases"] [role="tab"]')]
        .map(b => b.textContent.replace(/\d+$/, "").trim());
    // Closed is one of the views since 2026-10-11, not a separate History box.
    assert.deepEqual(chips, ["All", "Needs me", "New hire requests", "Not filed yet", "Active", "Closed"]);
    assert.ok(allButtons(view.container).some(b => /^Closed\s*1$/.test(b.textContent.trim())));
    assert.ok(view.container.querySelector('input[aria-label="Search cases"]'));
    assert.ok(allButtons(view.container).some(b => b.textContent.trim() === "Sort"));
    assert.ok(allButtons(view.container).some(b => b.textContent.trim().startsWith("Filter")));
    await view.unmount();
});

test("Needs me shows requests, cases with no date and outcomes due, nothing else", async () => {
    const OVERDUE = kase(5, "in_progress", [hearing("h5", addDays(-2), "Arguments")]);
    api.__respond("listCases", { data: { items: [LATER, SOON, NONE, SHUT, OVERDUE] }, error: null });
    const view = await mount();
    const chip = tab(view.container, "Needs me");
    assert.match(chip.textContent, /3$/, "the chip does not count request + no date + outcome due");
    await click(chip);
    const text = view.container.textContent;
    assert.match(text, /Inheritance claim/);
    assert.match(text, /CIV-2026-003/);
    assert.match(text, /CIV-2026-005/);
    assert.match(text, /Outcome due/);
    assert.doesNotMatch(text, /CIV-2026-001|CIV-2026-002/, "a case with an upcoming hearing is in Needs me");
    await view.unmount();
});

test("Sort reorders the cases: by next hearing, then Title A–Z", async () => {
    const zed = { ...kase(6, "in_progress", [hearing("h6", addDays(2), "Arguments")]), title: "Zebra lease" };
    const alpha = { ...kase(7, "in_progress", [hearing("h7", addDays(30), "Evidence")]), title: "Apple contract" };
    api.__respond("listCases", { data: { items: [zed, alpha] }, error: null });
    const view = await mount();
    // The order of the LIST: the week-in-court strip above it also names cases.
    const at = (t) => view.container.querySelector('section[aria-label="Cases"]').textContent.indexOf(t);
    assert.ok(at("Zebra lease") < at("Apple contract"), "by default the sooner hearing comes first");
    await click(allButtons(view.container).find(b => b.textContent.trim() === "Sort"));
    await click([...view.container.querySelectorAll('[role="menuitemradio"]')].find(b => b.textContent.startsWith("Title")));
    assert.ok(at("Apple contract") < at("Zebra lease"), "Title A–Z did not reorder");
    assert.equal(view.container.querySelector('[role="menu"]'), null, "the menu stayed open after choosing");
    await view.unmount();
});

test("Filter: every type and province as tiles with counts; choices apply only on Apply", async () => {
    const fam = { ...kase(8, "open"), title: "Custody matter", case_type: "family" };
    api.__respond("listCases", { data: { items: [SOON, fam] }, error: null });
    const view = await mount();
    const filterBtn = () => allButtons(view.container).find(b => b.textContent.trim().startsWith("Filter"));
    const panel = () => view.container.querySelector("[data-filter-panel]");
    const press = (label) => click([...panel().querySelectorAll("button")].find(b => b.textContent.trim() === label));
    await click(filterBtn());
    const keys = (group) => [...panel().querySelectorAll(`[role="group"][aria-label="${group}"] [data-option]`)].map(b => b.getAttribute("data-option"));
    assert.deepEqual(keys("Case type"), ["civil", "criminal", "constitutional", "family"], "Civil, Criminal, then Constitutional, Family");
    assert.deepEqual(keys("Province"), ["punjab", "sindh", "kpk", "balochistan", "federal"]);
    const tile = (k) => panel().querySelector(`[data-option="${k}"]`);
    assert.match(tile("family").textContent, /Family2$/, "Family counts the request and the case");
    assert.match(tile("sindh").textContent, /Sindh0$/);
    assert.equal(tile("civil").style.height, "36px", "tiles are compact");
    assert.equal(panel().querySelector("[data-option-grid]").style.gridTemplateColumns, "repeat(2, minmax(max-content, 1fr))", "two equal columns");
    assert.match(tile("kpk").textContent, /^KPK\d+$/, "KPK, short");
    assert.equal(tile("kpk").getAttribute("title"), "Khyber Pakhtunkhwa");
    assert.match(tile("federal").textContent, /^Federal \/ Islamabad\d+$/);
    assert.equal(tile("federal").style.gridColumn, "1 / -1", "Federal / Islamabad takes the whole row");
    assert.match(panel().textContent, /Showing 3 of 3 results/);

    await click(tile("family"));
    assert.equal(tile("family").getAttribute("aria-checked"), "true");
    assert.match(panel().textContent, /1 selected/);
    assert.match(panel().textContent, /Showing 2 of 3 results/, "the preview counts the draft");
    assert.match(view.container.textContent, /CIV-2026-001/, "the list changed before Apply");

    await press("Apply");
    assert.equal(panel(), null, "Apply did not close the panel");
    assert.doesNotMatch(view.container.textContent, /CIV-2026-001/);
    assert.match(view.container.textContent, /Custody matter/);
    assert.match(filterBtn().textContent, /1/);

    // A draft closed without Apply changes nothing.
    await click(filterBtn());
    await click(tile("criminal"));
    await click(filterBtn());
    assert.match(view.container.textContent, /Custody matter/, "an unapplied draft was applied");

    await click(filterBtn());
    assert.equal(tile("criminal").getAttribute("aria-checked"), "false", "the discarded draft came back");
    await press("Clear all");
    await press("Apply");
    assert.match(view.container.textContent, /CIV-2026-001/);
    await view.unmount();
});

test("the header buttons match the bar's height", async () => {
    const view = await mount();
    const exportBtn = view.container.querySelector('button[aria-label="Export cases"]');
    const newBtn = allButtons(view.container).find(b => b.textContent.trim() === "New case");
    const sortBtn = allButtons(view.container).find(b => b.textContent.trim() === "Sort");
    assert.equal(exportBtn.style.height, "44px");
    assert.equal(newBtn.style.height, "44px");
    // Sort sits in the one-line filter bar (2026-10-11), at the tab group's height.
    assert.equal(sortBtn.style.height, "44px");
    await view.unmount();
});

test("Add task opens Tasks with the new-task box focused", async () => {
    const view = await mount({ openAt: SOON.case_number });
    await click(buttonText(view.container, "Add task"));
    const input = view.container.querySelector('input[placeholder^="Add a task"]');
    assert.ok(input, "the Tasks tab did not open");
    assert.equal(document.activeElement, input);
    await view.unmount();
});

test("recording an outcome creates the ticked follow-up tasks before the next date", async () => {
    let n = 0;
    api.__respond("recordHearingOutcome", { data: SOON, error: null });
    api.__respond("addTask", (caseId, body) => ({ data: { _id: `t${++n}`, title: body.title, due: body.due, done: false }, error: null }));
    const view = await mount({ openAt: SOON.case_number });
    await click(tab(view.container, "Schedule"));
    await click(buttonText(view.container, "Record outcome"));
    const next = addDays(30);
    const field = [...view.container.querySelectorAll("label")].find(l => l.textContent.trim() === "Next hearing date (auto-schedules)").parentElement.querySelector("input");
    await type(field, next);
    // Untick one suggestion; it must not be created.
    const box = [...view.container.querySelectorAll('[role="checkbox"]')].find(b => b.textContent.includes("Update the client"));
    await click(box);
    await click(buttonText(view.container, "Record & Notify Client"));
    await settle(60);
    const calls = api.__calls("addTask").map(c => c.args[1]);
    assert.deepEqual(calls.map(c => c.title), ["Review the other side's latest filing", "Prepare for the next hearing"]);
    const fiveBefore = (() => { const d = new Date(`${next}T12:00:00Z`); d.setUTCDate(d.getUTCDate() - 5); return d.toISOString().slice(0, 10); })();
    assert.equal(calls[0].due, fiveBefore);
    assert.ok(calls.every(c => c.due < next), "a follow-up is not due before the next date");
    await view.unmount();
});

/* ── reschedule ───────────────────────────────────────────────────────── */

test("Reschedule moves an upcoming hearing and shows where it moved from", async () => {
    const newDate = addDays(12);
    api.__respond("rescheduleHearing", (caseId, hearingId, body) => ({ data: { ...SOON, hearing_dates: [
        hearing("h1", newDate, "Framing of issues", { time: body.time, reschedules: [{ from_date: `${addDays(5)}T00:00:00Z`, from_time: "10:00" }] }),
    ] }, error: null }));
    const view = await mount({ openAt: SOON.case_number });
    await click(tab(view.container, "Schedule"));
    await click(buttonText(view.container, "Reschedule"));
    assert.match(view.container.textContent, /Reschedule hearing/);
    // Nothing is sent without a date.
    assert.equal(buttonText(view.container, "Reschedule & notify client").disabled, true);

    const field = (name) => [...view.container.querySelectorAll('[role="dialog"] label')].find(l => l.textContent.trim() === name).parentElement.querySelector("input, textarea");
    await type(field("New date *"), newDate);
    await type(field("Time"), "11:30");
    await type(field("Reason (shown to the client)"), "Judge on leave");
    await click(buttonText(view.container, "Reschedule & notify client"));

    const [caseId, hearingId, body] = api.__calls("rescheduleHearing")[0].args;
    assert.equal(caseId, SOON._id);
    assert.equal(hearingId, "h1");
    assert.equal(body.date, new Date(newDate).toISOString());
    assert.equal(body.time, "11:30");
    assert.equal(body.reason, "Judge on leave");
    assert.match(view.container.textContent, /Rescheduled from/);
    await view.unmount();
});

test("a refused reschedule keeps the form open and says why", async () => {
    api.__respond("rescheduleHearing", { data: null, status: 422, error: { message: "Pick a date from today onwards" } });
    const view = await mount({ openAt: SOON.case_number });
    await click(tab(view.container, "Schedule"));
    await click(buttonText(view.container, "Reschedule"));
    const date = [...view.container.querySelectorAll("label")].find(l => l.textContent.trim() === "New date *").parentElement.querySelector("input");
    await type(date, addDays(3));
    await click(buttonText(view.container, "Reschedule & notify client"));
    assert.match(view.container.textContent, /Pick a date from today onwards/);
    assert.match(view.container.textContent, /Reschedule hearing/, "the form closed on a failure");
    await view.unmount();
});

/* ── closed cases are read-only ───────────────────────────────────────── */

test("a closed case opens read-only: no hearing, task or message controls", async () => {
    const CLOSED = kase(8, "closed", [hearing("h8", addDays(5), "Arguments")]);
    api.__respond("listCases", { data: { items: [CLOSED] }, error: null });
    const view = await mount({ openAt: CLOSED.case_number });
    const text = () => view.container.textContent;
    assert.match(text(), /This case is closed\./);
    for (const label of ["Add task", "Add hearing"]) {
        assert.equal(buttonText(view.container, label), undefined, `${label} is offered on a closed case`);
    }
    await click(tab(view.container, "Schedule"));
    for (const label of ["Schedule Hearing", "Reschedule", "Record outcome"]) {
        assert.equal(buttonText(view.container, label), undefined, `${label} is offered on a closed case`);
    }
    await click(tab(view.container, "Messages"));
    assert.equal(view.container.querySelector('input[placeholder^="Write to"]'), null, "the composer is shown on a closed case");
    assert.match(text(), /no new messages can be sent/);
    await click(tab(view.container, "Tasks"));
    assert.equal(view.container.querySelector('input[placeholder^="Add a task"]'), null);
    await view.unmount();
});

/* ── failures are said, not swallowed ─────────────────────────────────── */

test("a message that fails to send keeps the text and says why", async () => {
    api.__respond("sendMessage", { data: null, error: { message: "This case is closed, so it can no longer be changed." }, status: 409 });
    const view = await mount({ openAt: SOON.case_number });
    await click(tab(view.container, "Messages"));
    const box = view.container.querySelector('input[placeholder^="Write to"]');
    await type(box, "Please bring the deed.");
    await click(view.container.querySelector('button[aria-label="Send message"]'));
    assert.equal(view.container.querySelector('input[placeholder^="Write to"]').value, "Please bring the deed.");
    assert.match(view.container.querySelector('[role="alert"]')?.textContent || "", /can no longer be changed/);
    await view.unmount();
});

test("a task that cannot be ticked flips back and says why", async () => {
    api.__respond("listTasks", { data: [{ _id: "t1", title: "File reply", done: false }], error: null });
    api.__respond("toggleTask", { data: null, error: { message: "Task not found" }, status: 404 });
    const view = await mount({ openAt: SOON.case_number });
    await click(tab(view.container, "Tasks"));
    const box = view.container.querySelector('[role="checkbox"][aria-label="File reply"]');
    await click(box);
    await settle(40);
    assert.equal(view.container.querySelector('[role="checkbox"][aria-label="File reply"]').getAttribute("aria-checked"), "false");
    assert.match(view.container.textContent, /Task not found/);
    await view.unmount();
});

test("cases past the first page of 50 are listed too", async () => {
    const extra = { ...LATER, _id: "665f00000000000000000099", case_number: "CIV-2026-099", title: "Page two matter" };
    api.__respond("listCases", ({ page } = {}) => (page === 2
        ? { data: { items: [extra], total: 5, pages: 2 }, error: null }
        : { data: { items: [LATER, SOON, NONE, SHUT], total: 5, pages: 2 }, error: null }));
    const view = await mount();
    assert.match(view.container.textContent, /Page two matter/);
    await view.unmount();
});

/* ── + New case: a walk-in client case ────────────────────────────────── */

async function openNewCase(view) {
    await click(allButtons(view.container).find(b => b.textContent.trim() === "New case"));
    const form = (ph) => view.container.querySelector(`input[placeholder="${ph}"]`);
    return form;
}

test("New case validates, creates through the API, then opens the new case", async () => {
    const MADE = { _id: "665f00000000000000000077", case_number: "ATT-2026-ABCD1234", title: "Rent recovery", client_id: null,
        walk_in: true, client_name: "Muhammad Aslam", client_phone: "+92 300 1234567", province: "punjab", case_type: "civil",
        status: "in_progress", hearing_dates: [] };
    let created = false;
    api.__respond("createWalkInCase", (body) => { created = true; return { data: { ...MADE, title: body.title }, error: null }; });
    api.__respond("listCases", () => ({ data: { items: created ? [LATER, SOON, NONE, SHUT, MADE] : [LATER, SOON, NONE, SHUT] }, error: null }));
    const view = await mount();
    const field = await openNewCase(view);
    await click(allButtons(view.container).find(b => b.textContent.trim() === "Create case"));
    assert.match(view.container.querySelector('[role="alert"]')?.textContent || "", /title/i);
    assert.equal(api.__calls("createWalkInCase").length, 0, "an empty form was sent");

    await type(field("e.g. Rent recovery — Mr. Aslam"), "Rent recovery");
    await type(field("Full name"), "Muhammad Aslam");
    await type(field("+92 300 1234567"), "+92 300 1234567");
    await type(field("e.g. Civil Court Lahore"), "Civil Court Lahore");
    await click(allButtons(view.container).find(b => b.textContent.trim() === "Create case"));
    await settle(60);
    assert.deepEqual(api.__calls("createWalkInCase")[0].args[0], {
        title: "Rent recovery", case_type: "civil", province: "punjab", client_name: "Muhammad Aslam",
        client_phone: "+92 300 1234567", court: "Civil Court Lahore", court_case_number: null, description: "",
    });
    assert.ok(view.container.querySelector('[aria-label="Case sections"]'), "the new case did not open");
    assert.match(view.container.textContent, /ATT-2026-ABCD1234/);

    await click(tab(view.container, "Messages"));
    const note = view.container.querySelector("[data-walk-in-note]");
    assert.ok(note, "a walk-in case offered a message box");
    assert.match(note.textContent, /\+92 300 1234567/);
    assert.equal(view.container.querySelector('input[placeholder^="Write to"]'), null);
    await view.unmount();
});

test("a refused New case keeps the form and shows the server's reason", async () => {
    api.__respond("createWalkInCase", { data: null, error: { detail: [{ loc: ["body", "client_phone"], msg: "String should match pattern" }] }, status: 422 });
    const view = await mount();
    const field = await openNewCase(view);
    await type(field("e.g. Rent recovery — Mr. Aslam"), "Rent recovery");
    await type(field("Full name"), "Muhammad Aslam");
    await click(allButtons(view.container).find(b => b.textContent.trim() === "Create case"));
    await settle(40);
    assert.match(view.container.querySelector('[role="alert"]').textContent, /client_phone: String should match pattern/);
    assert.ok(allButtons(view.container).some(b => b.textContent.trim() === "Create case"), "the form closed on failure");
    await view.unmount();
});

/* ── Cases Workspace v2 layout (2026-10-09) ─────────────────────────────── */

test("This week in court: seven days from today, each hearing on its day, and a click opens the case", async () => {
    const pages = [];
    const view = await mount({ pages });
    const week = view.container.querySelector("[data-court-week]");
    assert.ok(week, "no week strip");
    const days = [...week.querySelectorAll("[data-day]")];
    assert.equal(days.length, 7);
    assert.equal(days[0].getAttribute("data-day"), pktToday(), "the week does not start today");
    assert.match(days[0].textContent, /^Today/);
    // SOON's hearing is in 5 days; LATER's (40 days) is not this week.
    assert.match(week.querySelector(`[data-day="${addDays(5)}"]`).textContent, /Matter 1/);
    assert.doesNotMatch(week.textContent, /Matter 2/);
    assert.match(week.textContent, /1 hearing in the next 7 days/);
    await click(buttonText(week, "Open cause list →"));
    assert.deepEqual(pages, ["causelist"]);
    await click([...week.querySelectorAll("button")].find(b => b.textContent.includes("Matter 1")));
    assert.ok(view.container.querySelector('[aria-label="Case sections"]'), "the hearing did not open its case");
    await view.unmount();
});

test("the week strip folds away and stays folded", async () => {
    localStorage.removeItem("attorney:lawyer-cases-week-open");
    let view = await mount();
    await click(buttonText(view.container, "Hide"));
    assert.equal(view.container.querySelectorAll("[data-day]").length, 0);
    await view.unmount();
    view = await mount();
    assert.equal(view.container.querySelectorAll("[data-day]").length, 0, "the fold was not remembered");
    await click(buttonText(view.container, "Show"));
    assert.equal(view.container.querySelectorAll("[data-day]").length, 7);
    await view.unmount();
    localStorage.removeItem("attorney:lawyer-cases-week-open");
});

test("Ctrl K focuses the one search; Enter opens the case when the search leaves exactly one", async () => {
    const view = await mount();
    const input = view.container.querySelector('input[aria-label="Search cases"]');
    await act(async () => { window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true, bubbles: true })); });
    assert.equal(document.activeElement, input, "Ctrl K did not focus the search");
    assert.equal(view.container.querySelectorAll('input[aria-label="Search cases"]').length, 1, "more than one case search");
    await type(input, "client 2");
    await act(async () => { input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })); });
    await settle();
    assert.ok(view.container.querySelector('[aria-label="Case sections"]'), "Enter did not open the only match");
    await view.unmount();
});

test("the Documents tab shows what the client sent on this case, opened at the revision sent", async () => {
    api.__respond("reviewQueueV2", { data: { items: [
        { id: "cd1", title: "Plaint — recovery", case_id: SOON._id, review_status: "returned", client_name: "Ayesha",
          submitted_version: 2, reviewed_revision_id: "rev-2", reviewed_pdf_sha256: "hash-2" },
        { id: "other", title: "Some other case's notice", case_id: "elsewhere", review_status: "submitted" },
        { id: "pend", title: "Notice waiting", case_id: SOON._id, review_status: "submitted", client_name: "Ayesha",
          submitted_version: 1, submitted_revision_id: "rev-p", submitted_pdf_sha256: "hash-p" },
    ], next_cursor: null }, error: null });
    api.__respond("fetchRevisionPreview", { data: { url: "blob:x" }, error: null });
    const view = await mount({ openAt: SOON.case_number });
    await click(tab(view.container, "Documents"));
    const row = view.container.querySelector('[data-case-doc="cd1"]');
    assert.ok(row, "the client's document is not listed on its case");
    assert.match(row.textContent, /Sent by Ayesha · v2/);
    assert.match(row.textContent, /Returned/);
    assert.equal(view.container.querySelector('[data-case-doc="other"]'), null, "another case's document leaked in");
    const pending = view.container.querySelector('[data-case-doc="pend"]');
    assert.match(pending.textContent, /Waiting for you/);
    assert.equal([...pending.querySelectorAll("button")].find(b => b.textContent.trim() === "Open").disabled, false,
        "a document waiting for the lawyer cannot be opened");
    const realOpen = window.open; window.open = () => ({});
    await click([...row.querySelectorAll("button")].find(b => b.textContent.trim() === "Open"));
    window.open = realOpen;
    const [id, opts] = api.__calls("fetchRevisionPreview")[0].args;
    assert.equal(id, "cd1");
    assert.deepEqual(opts, { revisionId: "rev-2", expectedPdfSha256: "hash-2" });
    await view.unmount();
});

test("Your files: listed for this case, uploaded through the API, and marked as private", async () => {
    api.__respond("listCaseFiles", { data: { items: [
        { id: "f1", name: "summons.pdf", content_type: "application/pdf", size: 2048, created_at: "2026-10-11T10:00:00Z" },
    ] }, error: null });
    api.__respond("uploadCaseFile", { data: { id: "f2", name: "order.png", content_type: "image/png", size: 4096 }, error: null, status: 201 });
    const view = await mount({ openAt: SOON.case_number });
    await click(tab(view.container, "Documents"));
    assert.equal(api.__calls("listCaseFiles")[0].args[0], SOON._id);
    const box = view.container.querySelector("[data-case-files]");
    assert.match(box.textContent, /Only you can see these/);
    assert.ok(box.querySelector('[data-case-file="f1"]'));
    const input = box.querySelector('input[type="file"]');
    const file = new File(["\x89PNG"], "order.png", { type: "image/png" });
    Object.defineProperty(input, "files", { value: [file], configurable: true });
    await act(async () => { input.dispatchEvent(new Event("change", { bubbles: true })); });
    await new Promise(r => setTimeout(r, 30));
    const [caseId, sent] = api.__calls("uploadCaseFile")[0].args;
    assert.equal(caseId, SOON._id);
    assert.equal(sent.name, "order.png");
    assert.ok(view.container.querySelector('[data-case-file="f2"]'), "the uploaded file is not listed");
    await view.unmount();
});

/* ── propose a meeting to the client (2026-10-12) ─────────────────────────── */

async function pick(el, value) {
    const proto = el.tagName === "SELECT" ? dom.window.HTMLSelectElement.prototype
        : el.tagName === "TEXTAREA" ? dom.window.HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
    await act(async () => { el.dispatchEvent(new Event(el.tagName === "SELECT" ? "change" : "input", { bubbles: true })); });
}

test("Propose meeting sends the chosen times, then shows the proposal with Withdraw", async () => {
    const { pktSlotToUtcISO } = await import("../src/lib/bookingTime.js");
    let sent = false;
    const day = addDays(3);
    const open = { id: "P1", status: "open", agenda: "Hearing prep", mode: "video", options: [pktSlotToUtcISO(day, "11:00")] };
    api.__respond("listMeetingProposals", () => ({ data: sent ? [open] : [], error: null }));
    api.__respond("proposeMeeting", () => { sent = true; return { data: open, error: null }; });
    api.__respond("withdrawMeetingProposal", { data: { ...open, status: "withdrawn" }, error: null });
    const view = await mount({ openAt: SOON.case_number });
    await click(buttonText(view.container, "Propose meeting"));
    const form = view.container.querySelector("[data-propose-meeting]");
    assert.ok(form, "the proposal form did not open");

    await click(buttonText(form, "Send proposal"));
    assert.equal(api.__calls("proposeMeeting").length, 0, "an empty proposal was sent");

    await pick(form.querySelector('[aria-label="Date 1"]'), day);
    await pick(form.querySelector('[aria-label="Time 1"]'), "11:00");
    await pick(form.querySelector("textarea"), "Hearing prep");
    await click(buttonText(form, "Send proposal"));
    const [args] = api.__calls("proposeMeeting").map(c => c.args[0]);
    assert.equal(args.case_id, SOON._id, "the proposal was not bound to the case's database id");
    // The proposals are read by the database id too, never the case number.
    const reads = api.__calls("listMeetingProposals").map(c => c.args[0]);
    assert.ok(reads.length > 0, "the case's proposals were never read");
    for (const r of reads) assert.equal(r.case_id, SOON._id, "proposals were read by something other than the database id");
    assert.deepEqual(args.options, [pktSlotToUtcISO(day, "11:00")]);
    assert.equal(args.mode, "video");
    assert.equal(args.agenda, "Hearing prep");

    const strip = view.container.querySelector("[data-meeting-proposal]");
    assert.ok(strip, "the open proposal is not shown");
    assert.match(strip.textContent, /Meeting proposed — waiting for/);
    assert.equal(buttonText(view.container, "Propose meeting"), undefined, "a second proposal was offered while one waits");
    await click(buttonText(strip, "Withdraw"));
    assert.equal(api.__calls("withdrawMeetingProposal")[0].args[0], "P1");
    await view.unmount();
});

test("a walk-in case cannot propose a meeting: the client has no account", async () => {
    const WALK = { ...kase(7, "in_progress"), walk_in: true, client_id: null };
    api.__respond("listCases", { data: { items: [WALK] }, error: null });
    const view = await mount({ openAt: WALK.case_number });
    assert.equal(buttonText(view.container, "Propose meeting"), undefined);
    await view.unmount();
});

/* ── what happened to the last proposal (2026-10-12) ──────────────────────── */

const prop = (over) => ({ id: "P0", status: "declined", agenda: "Hearing prep", mode: "video",
    options: ["2026-11-02T06:00:00Z"], decline_reason: null, ...over });

test("a declined proposal shows its times, the client's reason, and Propose new times", async () => {
    api.__respond("listMeetingProposals", { data: [prop({ decline_reason: "Travelling that week" })], error: null });
    const view = await mount({ openAt: SOON.case_number });
    const rec = view.container.querySelector('[data-proposal-history="declined"]');
    assert.ok(rec, "no record of the declined proposal");
    assert.match(rec.textContent, /could not make the proposed times.*Hearing prep.*PKT.*“Travelling that week”/s);
    assert.ok(rec.querySelector("[data-propose-again]"), "no way to propose again");
    await view.unmount();
});

test("an expired proposal is shown as lapsed", async () => {
    api.__respond("listMeetingProposals", { data: [prop({ status: "expired" })], error: null });
    const view = await mount({ openAt: SOON.case_number });
    const rec = view.container.querySelector('[data-proposal-history="expired"]');
    assert.match(rec.textContent, /proposed times passed/);
    await view.unmount();
});

test("an open proposal stays the primary banner; the old record is shown after it without a button", async () => {
    api.__respond("listMeetingProposals", { data: [
        prop({ id: "P2", status: "open", agenda: "New try" }),
        prop({ id: "P1", status: "declined", decline_reason: "Busy" }),
    ], error: null });
    const view = await mount({ openAt: SOON.case_number });
    const open = view.container.querySelector("[data-meeting-proposal]");
    const rec = view.container.querySelector('[data-proposal-history="declined"]');
    assert.ok(open && rec);
    assert.ok(open.compareDocumentPosition(rec) & 4, "the old record came before the open proposal");
    assert.equal(rec.querySelector("[data-propose-again]"), null, "a second proposal was offered while one waits");
    assert.equal(buttonText(view.container, "Propose meeting"), undefined);
    await view.unmount();
});

test("an accepted proposal after a declined one leaves nothing to follow up", async () => {
    api.__respond("listMeetingProposals", { data: [prop({ id: "P2", status: "accepted" }), prop({ id: "P1" })], error: null });
    const view = await mount({ openAt: SOON.case_number });
    assert.equal(view.container.querySelector("[data-proposal-history]"), null);
    await view.unmount();
});

test("a closed case shows the record but offers no proposal", async () => {
    const CLOSED_CASE = { ...kase(8, "closed") };
    api.__respond("listCases", { data: { items: [CLOSED_CASE] }, error: null });
    api.__respond("listMeetingProposals", { data: [prop({})], error: null });
    const view = await mount({ openAt: CLOSED_CASE.case_number });
    assert.equal(buttonText(view.container, "Propose meeting"), undefined);
    assert.equal(view.container.querySelector("[data-propose-again]"), null);
    await view.unmount();
});
/* ── opening on a hire request (2026-10-12) ───────────────────────────────── */

test("a stored request opens New requests on that request (also after a reload)", async () => {
    window.sessionStorage.setItem("attorney:lawyer-open-request", REQUEST.id);
    const view = await mount();
    const row = view.container.querySelector(`[data-request-id="${REQUEST.id}"]`);
    assert.ok(row, "the request is not listed");
    assert.ok(row.hasAttribute("data-focused"), "the request was not focused");
    assert.equal(window.sessionStorage.getItem("attorney:lawyer-open-request"), null, "the request stayed pending after it was applied");
    await view.unmount();
});

test("an unknown request id falls back to New requests with nothing focused", async () => {
    window.sessionStorage.setItem("attorney:lawyer-open-request", "nope");
    const view = await mount();
    assert.ok(view.container.querySelector(`[data-request-id="${REQUEST.id}"]`), "New requests did not open");
    assert.equal(view.container.querySelector("[data-focused]"), null);
    await view.unmount();
});

test("a request asked for while the page is open is focused too", async () => {
    const view = await mount();
    await act(async () => { window.dispatchEvent(new window.CustomEvent("attorney:open-request", { detail: REQUEST.id })); });
    await settle();
    assert.ok(view.container.querySelector(`[data-request-id="${REQUEST.id}"]`).hasAttribute("data-focused"));
    await view.unmount();
});

/* ── Batch D (2026-10-20): the consultation behind a hire and a case ────── */

const CONSULT = { id: "ap-1", scheduled_at: "2026-10-18T04:00:00+00:00", end_at: "2026-10-18T04:30:00+00:00",
                  duration_minutes: 30, mode: "video", status: "completed", note: "Uncle sold the land" };

test("a hire request says which consultation it followed, in PKT, and opens it", async () => {
    api.__respond("listEngagements", { data: [{ ...REQUEST, consultation: CONSULT, consultation_unavailable: false }], error: null });
    const pages = [];
    const view = await mount({ pages });
    const line = view.container.querySelector(`[data-request-id="${REQUEST.id}"] [data-request-consultation]`);
    assert.ok(line, "the request row does not name its consultation");
    assert.match(line.textContent, /After consultation on Sun, 18 Oct · 09:00 PKT · Video call/, "not the stored meeting, or not in PKT");
    assert.match(line.textContent, /Uncle sold the land/);
    await click(buttonText(line, "View consultation"));
    assert.equal(window.sessionStorage.getItem("attorney:lawyer-open-appointment"), "ap-1");
    assert.deepEqual(pages, ["appointments"]);
    window.sessionStorage.clear();
    await view.unmount();
});

test("a legacy hire request with no stored consultation says so, and guesses nothing", async () => {
    api.__respond("listEngagements", { data: [{ ...REQUEST, consultation: null, consultation_unavailable: true }], error: null });
    const view = await mount();
    const line = view.container.querySelector(`[data-request-id="${REQUEST.id}"] [data-request-consultation]`);
    assert.equal(line.getAttribute("data-request-consultation"), "unavailable");
    assert.match(line.textContent, /Consultation record unavailable/);
    assert.equal(buttonText(line, "View consultation"), undefined);
    await view.unmount();
});

test("the case shows the consultation it came from and only its own meetings", async () => {
    api.__respond("getCaseConsultations", { data: { originating: CONSULT, originating_unavailable: false, has_hire: true,
        linked: [{ ...CONSULT, id: "ap-2", scheduled_at: "2026-10-25T06:00:00+00:00", status: "confirmed", note: "" }] }, error: null });
    const view = await mount({ openAt: SOON.case_number });
    assert.equal(api.__calls("getCaseConsultations")[0].args[0], SOON._id, "read by something other than the database id");
    const card = view.container.querySelector("[data-case-consultations]");
    assert.ok(card, "no Consultations card");
    assert.deepEqual([...card.querySelectorAll("[data-case-consultation]")].map(e => e.getAttribute("data-case-consultation")), ["ap-1", "ap-2"]);
    assert.match(card.textContent, /The consultation that led to this case/);
    assert.match(card.textContent, /Meeting on this case/);
    await view.unmount();
});

test("a case whose hire has no stored consultation says 'record unavailable'", async () => {
    api.__respond("getCaseConsultations", { data: { originating: null, originating_unavailable: true, has_hire: true, linked: [] }, error: null });
    const view = await mount({ openAt: SOON.case_number });
    assert.ok(view.container.querySelector("[data-consultation-unavailable]"));
    await view.unmount();
});

test("a failed consultations read is not shown as none", async () => {
    api.__respond("getCaseConsultations", { data: null, error: { message: "down" }, status: 0 });
    const view = await mount({ openAt: SOON.case_number });
    const card = view.container.querySelector("[data-case-consultations]");
    assert.ok(card, "a failed read hid the card like an empty one");
    assert.match(card.textContent, /Could not load this case's consultations/);
    await view.unmount();
});

/* ── meetings with the client, joined from the case (2026-10-20) ──────────── */

test("the Schedule tab lists the case's meetings with the client, with their Join", async () => {
    const soon = new Date(Date.now() + 2 * 864e5).toISOString();
    const soonEnd = new Date(Date.now() + 2 * 864e5 + 36e5).toISOString();
    api.__respond("getCaseConsultations", { data: { originating: CONSULT, originating_unavailable: false, has_hire: true, linked: [
        { id: "ap-m", scheduled_at: soon, end_at: soonEnd, mode: "video", status: "confirmed", note: "Documents for the suit" },
        { id: "ap-old", scheduled_at: "2026-10-01T05:00:00+00:00", end_at: "2026-10-01T06:00:00+00:00", mode: "video", status: "completed", note: "" },
    ] }, error: null });
    const view = await mount({ openAt: SOON.case_number });
    await click(tab(view.container, "Schedule"));
    const card = view.container.querySelector("[data-case-meetings]");
    assert.ok(card, "no Meetings with client on the Schedule tab");
    assert.deepEqual([...card.querySelectorAll("[data-case-meeting]")].map(e => e.getAttribute("data-case-meeting")), ["ap-m"], "a past meeting was listed as ahead");
    assert.ok(card.querySelector('[data-case-meeting-join="ap-m"]'), "the meeting has no Join");
    assert.match(card.textContent, /Documents for the suit/);
    await view.unmount();
});

test("with no meeting booked, the Schedule tab says how to book one", async () => {
    api.__respond("getCaseConsultations", { data: { originating: null, originating_unavailable: false, has_hire: true, linked: [] }, error: null });
    const view = await mount({ openAt: SOON.case_number });
    await click(tab(view.container, "Schedule"));
    assert.match(view.container.querySelector("[data-case-meetings-empty]").textContent, /Propose meeting/);
    await view.unmount();
});
