/* The lawyer's Clients page (LD-05; Marhala 4; Batch C 2026-10-20).
 *
 * Everything comes from /lawyer-clients (the server groups the shared action
 * predicates by client). The page shows the relationship (`stage`), the ONE
 * next step (`next_action`, exact target) as the main button, the rest of the
 * waiting work as chips, and routes Message: an engaged client's case on
 * Messages, a prospective client's appointment chat.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/" });
function define(name, value) {
    Object.defineProperty(globalThis, name, { value, writable: true, configurable: true });
}
for (const name of ["window", "document", "navigator", "HTMLElement", "Element", "Node", "Event",
                    "CustomEvent", "MouseEvent", "KeyboardEvent", "MutationObserver",
                    "getComputedStyle", "localStorage", "sessionStorage"]) {
    define(name, dom.window[name]);
}
define("IS_REACT_ACT_ENVIRONMENT", true);

const React = (await import("react")).default;
const { act } = await import("react");
const { createRoot } = await import("react-dom/client");
const api = await import("./support/api-stub.mjs");
const { CaseCtx, NotifCtx } = await import("../src/components/lawyer/theme.js");
const { ClientsPage } = await import("../src/components/lawyer/ClientsPage.jsx");
const h = React.createElement;

const settle = (ms = 30) => act(async () => { await new Promise(r => setTimeout(r, ms)); });
const counts = (over = {}) => ({ requests: 0, upcoming: 0, consultations: 0, open_cases: 0, closed_cases: 0, ...over });
function client(over) {
    return { client_id: "cl1", name: "Ayesha Khan", email: null, province: "punjab", stage: "Engaged", counts: counts(),
             needs_outcome: false, next_appointment: null, latest_appointment_id: null, pending_request_id: null,
             next_action: null, pending: { hire_requests: 0, outcomes: 0, appointment_requests: 0 }, waiting_for_client: 0,
             targets: {}, message: null,
             cases: [], since: null, last_activity: null, ...over };
}

async function mount(items, totals = {}) {
    api.__reset();
    api.__respond("listMyClients", { data: { items, totals, total: items.length }, error: null });
    const opened = [];
    const pages = [];
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => {
        root.render(h(NotifCtx.Provider, { value: { addNotif: () => {} } },
            h(CaseCtx.Provider, { value: { setOpenCaseId: id => opened.push(id), setPage: p => pages.push(p) } },
                h(ClientsPage))));
    });
    await settle();
    const button = (text) => [...container.querySelectorAll("button")].find(b => b.textContent.trim().endsWith(text));
    const events = [];
    const listen = e => events.push([e.type, e.detail]);
    window.addEventListener("attorney:open-request", listen);
    window.addEventListener("attorney:record-outcome", listen);
    const click = async (text) => {
        const b = button(text);
        assert.ok(b, `no "${text}" button`);
        await act(async () => { b.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
        await settle();
    };
    const done = async () => {
        window.removeEventListener("attorney:open-request", listen);
        window.removeEventListener("attorney:record-outcome", listen);
        await act(async () => root.unmount()); container.remove(); sessionStorage.clear();
    };
    return { container, opened, pages, events, button, click, done };
}

const CASE = { id: "665f00000000000000000001", case_number: "CIV-2026-001", title: "Rent dispute", status: "in_progress" };
const engaged = (over = {}) => client({ cases: [CASE], counts: counts({ open_cases: 1 }),
    next_action: { kind: "open_case", target_id: CASE.id }, targets: { case_id: CASE.id, case_number: CASE.case_number },
    message: { kind: "case", target_id: CASE.id, case_number: CASE.case_number }, ...over });

test("Engaged: Message opens the case on its Messages tab, by case number", async () => {
    const v = await mount([engaged()]);
    await v.click("Message");
    assert.deepEqual(v.opened, ["CIV-2026-001"]);
    assert.deepEqual(v.pages, ["cases"]);
    assert.equal(sessionStorage.getItem("attorney:lawyer-case-tab"), "messages");
    await v.done();
});

test("Message falls back to the database id when there is no case number", async () => {
    const v = await mount([engaged({ cases: [{ ...CASE, case_number: null }], message: { kind: "case", target_id: CASE.id, case_number: null } })]);
    await v.click("Message");
    assert.deepEqual(v.opened, ["665f00000000000000000001"]);
    await v.done();
});

test("a prospective client's Message opens that appointment's chat", async () => {
    const v = await mount([client({ stage: "Consultation scheduled", next_action: { kind: "view_appointment", target_id: "ap-5" },
        targets: { next_appointment_id: "ap-5" }, message: { kind: "appointment", target_id: "ap-5" } })]);
    await v.click("Message");
    assert.equal(sessionStorage.getItem("attorney:lawyer-open-appointment"), "ap-5");
    assert.equal(sessionStorage.getItem("attorney:lawyer-open-appointment-thread"), "ap-5");
    assert.deepEqual(v.pages, ["appointments"]);
    assert.deepEqual(v.opened, [], "a prospective client was sent to a case");
    await v.done();
});

test("Suggest a meeting opens the proposal dialog for that client's case; it books nothing", async () => {
    const v = await mount([engaged()]);
    await v.click("Suggest a meeting");
    assert.ok(document.querySelector("[data-propose-meeting]"), "proposal dialog did not open");
    assert.equal(api.__calls("proposeMeeting").length, 0);
    assert.deepEqual(v.pages, []);
    await v.done();
});

test("a requested client: Answer appointment request opens that request; no Message before a meeting is confirmed", async () => {
    const v = await mount([client({ stage: "Appointment requested", pending_request_id: "ap-9", counts: counts({ requests: 1 }),
        next_action: { kind: "answer_request", target_id: "ap-9" }, pending: { hire_requests: 0, outcomes: 0, appointment_requests: 1 },
        targets: { pending_appointment_id: "ap-9" } })]);
    assert.equal(v.button("Message"), undefined);
    assert.equal(v.button("Suggest a meeting"), undefined);
    await v.click("Answer appointment request");
    assert.equal(sessionStorage.getItem("attorney:lawyer-open-appointment"), "ap-9");
    assert.deepEqual(v.pages, ["appointments"]);
    assert.deepEqual(v.opened, []);
    await v.done();
});

test("combined state: Send terms is the main button; the outcome and the request stay as chips", async () => {
    // Ahmed: hire request + a meeting waiting for its outcome + a new request.
    const v = await mount([client({ client_id: "ahmed", name: "Ahmed Raza", stage: "Hire request",
        next_action: { kind: "send_terms", target_id: "eng-1" },
        pending: { hire_requests: 1, outcomes: 1, appointment_requests: 1 }, counts: counts({ requests: 1, consultations: 1 }),
        targets: { engagement_id: "eng-1", outcome_appointment_id: "ap-out", pending_appointment_id: "ap-req" },
        message: { kind: "appointment", target_id: "ap-out" } })]);
    const card = v.container.querySelector('[data-client-card="ahmed"]');
    const primary = card.querySelector("[data-client-primary]");
    assert.equal(primary.textContent.trim(), "Send terms");
    const chips = [...card.querySelectorAll("[data-client-chip]")].map(b => b.getAttribute("data-client-chip"));
    assert.deepEqual(chips, ["record_outcome", "answer_request"], "the other waiting work was hidden");
    assert.match(card.textContent, /1 outcome to record/);
    assert.match(card.textContent, /1 appointment request/);
    assert.doesNotMatch(card.textContent, /\b1 request\b/, "a bare '1 request' does not say which kind");

    // Send terms opens the terms dialog on this page (2026-10-20).
    api.__respond("listEngagements", { data: [{ id: "eng-1", status: "requested", client_name: "Ahmed Raza", case_title: "Land" }], error: null });
    await act(async () => { primary.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    await settle(60);
    assert.ok(document.querySelector("[data-terms]"), "Send terms did not open the dialog here");
    assert.deepEqual(v.pages, []);
    await act(async () => { [...document.querySelectorAll("[data-terms] button")].find(b => b.textContent === "Cancel").dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    await act(async () => { card.querySelector('[data-client-chip="record_outcome"]').dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    assert.equal(sessionStorage.getItem("attorney:lawyer-record-outcome"), "ap-out");
    assert.deepEqual(v.events, [["attorney:record-outcome", "ap-out"]]);
    assert.deepEqual(v.pages, ["appointments"]);
    await v.done();
});

test("an engaged client who owes an outcome: Record outcome leads, the stage stays Engaged", async () => {
    const v = await mount([engaged({ next_action: { kind: "record_outcome", target_id: "ap-7" },
        pending: { hire_requests: 0, outcomes: 1, appointment_requests: 0 },
        targets: { case_id: CASE.id, outcome_appointment_id: "ap-7" } })]);
    const card = v.container.querySelector("[data-client-card]");
    assert.equal(card.getAttribute("data-stage"), "Engaged");
    assert.equal(card.querySelector("[data-client-primary]").textContent.trim(), "Record outcome");
    assert.equal(card.querySelector("[data-client-chips]"), null, "the primary action was repeated as a chip");
    await v.done();
});

test("terms already sent read 'Waiting for client', not a lawyer action", async () => {
    const v = await mount([client({ stage: "Hire request", waiting_for_client: 1, latest_appointment_id: "ap-1",
        targets: { waiting_engagement_id: "eng-2" } })]);
    const card = v.container.querySelector("[data-client-card]");
    assert.ok(card.querySelector("[data-client-waiting]"));
    assert.equal(card.querySelector("[data-client-primary]"), null, "waiting for the client was shown as the lawyer's step");
    assert.equal(v.button("Send terms"), undefined);
    await v.done();
});

test("stages show as given, with filter chips counted from the server totals", async () => {
    const items = [
        client({ client_id: "a", name: "A One", stage: "Engaged", cases: [CASE] }),
        client({ client_id: "b", name: "B Two", stage: "Hire request", latest_appointment_id: "x" }),
        client({ client_id: "c", name: "C Three", stage: "Closed", latest_appointment_id: "y" }),
    ];
    const v = await mount(items, { "Engaged": 1, "Hire request": 1, "Closed": 1 });
    assert.match(v.container.textContent, /3 clients · from your appointments and cases/);
    const chip = v.container.querySelector('[data-stage-filter="Closed"]');
    await act(async () => chip.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    const shown = [...v.container.querySelectorAll("[data-client-card]")].map(e => e.getAttribute("data-client-card"));
    assert.deepEqual(shown, ["c"]);
    await v.done();
});

test("arriving from a case's Profile, that client's card is marked", async () => {
    sessionStorage.setItem("attorney:lawyer-focus-client", "b");
    const v = await mount([client({ client_id: "a", name: "A One" }), client({ client_id: "b", name: "B Two" })]);
    assert.ok(v.container.querySelector('[data-client-card="b"][data-focused]'), "the client was not marked");
    assert.equal(v.container.querySelector('[data-client-card="a"][data-focused]'), null);
    assert.equal(sessionStorage.getItem("attorney:lawyer-focus-client"), null, "the focus was kept for the next visit");
    await v.done();
});

test("a failed read says so and can be retried — it is not 'no clients'", async () => {
    api.__reset();
    api.__respond("listMyClients", { data: null, error: { message: "boom" } });
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => {
        root.render(h(NotifCtx.Provider, { value: { addNotif: () => {} } },
            h(CaseCtx.Provider, { value: { setOpenCaseId: () => {}, setPage: () => {} } }, h(ClientsPage))));
    });
    await settle();
    assert.ok(container.querySelector("[data-clients-error]"));
    assert.doesNotMatch(container.textContent, /No clients yet/);
    assert.equal(container.querySelector("[data-client-chips]"), null);
    await act(async () => root.unmount());
    container.remove();
});

test("Send terms opens the terms dialog right here, not on Cases; after sending the list is re-read", async () => {
    const v = await mount([client({ client_id: "ahmed", name: "Ahmed Raza", stage: "Hire request",
        next_action: { kind: "send_terms", target_id: "eng-1" }, pending: { hire_requests: 1, outcomes: 0, appointment_requests: 0 },
        targets: { engagement_id: "eng-1" } })]);
    api.__respond("listEngagements", { data: [{ id: "eng-1", status: "requested", client_name: "Ahmed Raza", case_title: "Land sold without consent", case_number: "ATT-1" }], error: null });
    api.__respond("proposeEngagementTerms", { data: { status: "terms_proposed" }, error: null });
    api.__respond("listMyClients", { data: { items: [], totals: {}, total: 0 }, error: null });
    await act(async () => { v.container.querySelector("[data-client-primary]").dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    await settle(60);
    assert.deepEqual(v.pages, [], "Send terms left the Clients page");
    const dlg = document.querySelector("[data-terms]");
    assert.ok(dlg, "the terms dialog did not open here");
    assert.match(dlg.textContent, /Land sold without consent/);
    const fee = dlg.querySelector('input[type="number"]');
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set.call(fee, "45000");
    await act(async () => { fee.dispatchEvent(new Event("input", { bubbles: true })); });
    await act(async () => { dlg.querySelector("[data-terms-send]").dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    await settle(60);
    assert.equal(api.__calls("proposeEngagementTerms")[0].args[0], "eng-1");
    assert.equal(document.querySelector("[data-terms]"), null, "the dialog stayed open after sending");
    assert.ok(api.__calls("listMyClients").length >= 2, "the clients were not re-read after sending");
    await v.done();
});

test("Send terms on a request no longer waiting says so instead of opening an empty dialog", async () => {
    const v = await mount([client({ client_id: "ahmed", name: "Ahmed Raza", stage: "Hire request",
        next_action: { kind: "send_terms", target_id: "eng-gone" }, targets: { engagement_id: "eng-gone" } })]);
    api.__respond("listEngagements", { data: [], error: null });
    await act(async () => { v.container.querySelector("[data-client-primary]").dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    await settle(60);
    assert.equal(document.querySelector("[data-terms]"), null);
    assert.match(v.container.textContent, /no longer waiting for your terms/);
    await v.done();
});
