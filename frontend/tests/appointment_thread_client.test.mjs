/* The appointment message thread on the CLIENT (2026-10-12): the Appointments
 * page and Tracking's cards use the same entry and the same thread, and the
 * server's `can_send` decides whether it can be written. */
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/appointments" });
function define(name, value) { Object.defineProperty(globalThis, name, { value, writable: true, configurable: true }); }
for (const name of ["window", "document", "navigator", "HTMLElement", "HTMLTextAreaElement", "Element", "Node", "Event",
                    "CustomEvent", "MouseEvent", "KeyboardEvent", "MutationObserver", "getComputedStyle", "localStorage",
                    "requestAnimationFrame", "cancelAnimationFrame", "CSS"]) define(name, dom.window[name]);
if (!globalThis.CSS) define("CSS", { escape: s => String(s) });
define("IS_REACT_ACT_ENVIRONMENT", true);
dom.window.HTMLElement.prototype.scrollIntoView = function () {};

const React = (await import("react")).default;
const { act } = await import("react");
const { createRoot } = await import("react-dom/client");
const api = await import("./support/api-stub.mjs");
const h = React.createElement;
const realSetTimeout = setTimeout;
const nav = () => (globalThis.__nav ||= { pushed: [], replaced: [], params: new Map() });
const settle = (ms = 50) => act(async () => { await new Promise(r => realSetTimeout(r, ms)); });

const inHours = n => new Date(Date.now() + n * 36e5).toISOString();
const appt = (over = {}) => ({ id: "a-up", lawyer_id: "L1", lawyer_name: "Kamran Aziz Malik", scheduled_at: inHours(30),
    end_at: inHours(31), duration_minutes: 60, mode: "video", status: "confirmed", case_id: null, schedule_version: 1, ...over });
const msg = (id, text, over = {}) => ({ id, appointment_id: "a-up", sender_id: "L1", sender_role: "lawyer",
    sender_name: "Kamran Aziz Malik", text, created_at: "2026-10-12T07:00:00Z", from_me: false, client_key: null, ...over });
const page = (items, over = {}) => ({ data: { items, next_cursor: null, can_send: true, send_state: "open", appointment_status: "confirmed", ...over }, error: null, status: 200 });

async function mountPage({ standalone = "appointments" } = {}) {
    const Module7 = (await import("../src/components/client/ModTracking.jsx")).default;
    const { CaseCtx } = await import("../src/components/shared/CaseContext.jsx");
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    const ctx = { notifications: [], markNotificationDone: () => {}, markAllNotificationsDone: () => {}, appointmentMilestones: [] };
    await act(async () => { root.render(h(CaseCtx.Provider, { value: ctx }, h(Module7, { isDark: true, standalone }))); });
    await settle(80);
    return {
        container,
        text: () => container.textContent,
        button: (label, scope = container) => [...scope.querySelectorAll("button")].find(b => b.textContent.trim() === label),
        thread: () => container.querySelector("[data-appointment-thread]"),
        unmount: async () => { await act(async () => root.unmount()); container.remove(); },
    };
}
const click = async (el) => { assert.ok(el, "control missing"); await act(async () => { el.dispatchEvent(new MouseEvent("click", { bubbles: true })); }); await settle(); };
async function type(el, value) {
    Object.getOwnPropertyDescriptor(dom.window.HTMLTextAreaElement.prototype, "value").set.call(el, value);
    await act(async () => { el.dispatchEvent(new Event("input", { bubbles: true })); });
}
const sendKeys = () => api.__calls("sendAppointmentMessage").map(c => c.args[1].idempotency_key);

test.beforeEach(() => {
    api.__reset();
    nav().params = new Map([["appointment", "a-up"]]);
    api.__respond("bootstrapAuth", true);
    api.__respond("getMe", { data: { _id: "c1", role: "client" } });
    api.__respond("getNotifications", { data: { items: [] } });
    api.__respond("listCases", { data: { items: [] } });
    api.__respond("listEngagements", { data: [] });
    api.__respond("listMeetingProposals", { data: [] });
});
test.after(() => dom.window.close());

test("a confirmed appointment offers Message lawyer; the thread shows who said what, oldest first", async () => {
    api.__respond("listAppointments", { data: { items: [appt()] } });
    api.__respond("listAppointmentMessages", page([msg("m1", "Please bring the notice"), msg("m2", "Will do", { sender_role: "client", from_me: true, created_at: "2026-10-12T07:05:00Z" })]));
    const ui = await mountPage();
    await click(ui.button("Message Kamran"));
    const th = ui.thread();
    assert.equal(th.getAttribute("data-thread-state"), "open");
    const items = [...th.querySelectorAll("[data-message]")].map(li => li.textContent);
    assert.match(items[0], /Kamran Aziz Malik · .* PKT.*Please bring the notice/);
    assert.match(items[1], /^You · .*Will do/);
    assert.ok(th.querySelector("textarea"), "no composer on an open thread");
    await ui.unmount();
});

test("a pending request has no thread, only an explanation", async () => {
    api.__respond("listAppointments", { data: { items: [appt({ status: "pending" })] } });
    const ui = await mountPage();
    assert.equal(ui.button("Message Kamran"), undefined);
    assert.ok(ui.container.querySelector("[data-thread-pending]"));
    assert.equal(api.__calls("listAppointmentMessages").length, 0);
    await ui.unmount();
});

test("an ended appointment shows its history read-only, with no composer", async () => {
    api.__respond("listAppointments", { data: { items: [appt({ status: "completed", scheduled_at: inHours(-30), end_at: inHours(-29) })] } });
    api.__respond("listAppointmentMessages", page([msg("m1", "Thanks")], { can_send: false, send_state: "read_only", appointment_status: "completed" }));
    const ui = await mountPage();
    await click(ui.button("View messages"));
    const th = ui.thread();
    assert.equal(th.getAttribute("data-thread-state"), "read_only");
    assert.equal(th.querySelector("textarea"), null);
    assert.match(th.querySelector("[data-thread-closed]").textContent, /read-only/);
    assert.match(th.textContent, /Thanks/);
    await ui.unmount();
});

test("inside the cancellation cutoff, Message lawyer opens the thread", async () => {
    api.__respond("listAppointments", { data: { items: [appt({ scheduled_at: inHours(1), end_at: inHours(2) })] } });
    api.__respond("listAppointmentMessages", page([]));
    const ui = await mountPage();
    await click(ui.container.querySelector("[data-cutoff-message]"));
    assert.ok(ui.thread(), "the cutoff note led nowhere");
    await ui.unmount();
});

test("a sent message appears once and the draft clears", async () => {
    api.__respond("listAppointments", { data: { items: [appt()] } });
    api.__respond("listAppointmentMessages", page([]));
    api.__respond("sendAppointmentMessage", (_id, body) => ({ data: msg("m9", body.text, { from_me: true, sender_role: "client", client_key: body.idempotency_key }), error: null, status: 201 }));
    const ui = await mountPage();
    await click(ui.button("Message Kamran"));
    await type(ui.thread().querySelector("textarea"), "  Running late  ");
    await click(ui.thread().querySelector("[data-thread-send]"));
    assert.equal(api.__calls("sendAppointmentMessage")[0].args[1].text, "Running late");
    assert.equal(ui.thread().querySelectorAll("[data-message]").length, 1);
    assert.equal(ui.thread().querySelector("textarea").value, "");
    await ui.unmount();
});

test("a refused send shows why, keeps the draft, and shows no bubble", async () => {
    api.__respond("listAppointments", { data: { items: [appt()] } });
    api.__respond("listAppointmentMessages", page([]));
    api.__respond("sendAppointmentMessage", { data: null, error: { message: "Write a message first" }, status: 422 });
    const ui = await mountPage();
    await click(ui.button("Message Kamran"));
    await type(ui.thread().querySelector("textarea"), "x");
    await click(ui.thread().querySelector("[data-thread-send]"));
    assert.match(ui.thread().querySelector("[data-thread-error]").textContent, /Write a message first/);
    assert.equal(ui.thread().querySelectorAll("[data-message]").length, 0);
    assert.equal(ui.thread().querySelector("textarea").value, "x");
    await ui.unmount();
});

test("a failed read is an error with Retry, not an empty thread", async () => {
    let n = 0;
    api.__respond("listAppointments", { data: { items: [appt()] } });
    api.__respond("listAppointmentMessages", () => (++n === 1 ? { data: null, error: { message: "down" }, status: 503 } : page([msg("m1", "Hello")])));
    const ui = await mountPage();
    await click(ui.button("Message Kamran"));
    assert.equal(ui.thread().getAttribute("data-thread-state"), "error");
    assert.doesNotMatch(ui.thread().textContent, /No messages yet/);
    await click(ui.button("Retry", ui.thread()));
    assert.match(ui.thread().textContent, /Hello/);
    await ui.unmount();
});

test("a lost reply is reconciled by reading back, and a retry reuses the same key", async () => {
    api.__respond("listAppointments", { data: { items: [appt()] } });
    let stored = null;
    api.__respond("listAppointmentMessages", () => page(stored ? [stored] : []));
    let calls = 0;
    api.__respond("sendAppointmentMessage", (_id, body) => {
        calls += 1;
        if (calls === 1) return { data: null, error: { message: "" }, status: 0 };   // lost, NOT stored
        stored = msg("m5", body.text, { from_me: true, sender_role: "client", client_key: body.idempotency_key });
        return calls === 2 ? { data: null, error: { message: "" }, status: 0 } : { data: stored, error: null, status: 201 };  // lost, stored
    });
    const ui = await mountPage();
    await click(ui.button("Message Kamran"));
    await type(ui.thread().querySelector("textarea"), "Is the link working?");
    await click(ui.thread().querySelector("[data-thread-send]"));
    assert.match(ui.thread().querySelector("[data-thread-error]").textContent, /could not confirm/);
    assert.equal(ui.thread().querySelectorAll("[data-message]").length, 0, "an unconfirmed message was shown as sent");
    await click(ui.thread().querySelector("[data-thread-send]"));
    const keys = sendKeys();
    assert.equal(keys.length, 2);
    assert.equal(keys[0], keys[1], "the retry used a new key");
    assert.equal(ui.thread().querySelectorAll("[data-message]").length, 1, "the stored message was not found on read-back");
    assert.equal(ui.thread().querySelector("[data-thread-error]"), null);
    await ui.unmount();
});

test("a message notification for THIS appointment refreshes; another appointment's does not", async () => {
    api.__respond("listAppointments", { data: { items: [appt()] } });
    let items = [msg("m1", "First")];
    api.__respond("listAppointmentMessages", () => page(items));
    const ui = await mountPage();
    await click(ui.button("Message Kamran"));
    const { broadcastNotification } = await import("../src/lib/notificationTarget.js");
    const before = api.__calls("listAppointmentMessages").length;
    await act(async () => { broadcastNotification({ id: "n1", type: "appointment_message", payload: { appointment_id: "other" } }); });
    await settle();
    assert.equal(api.__calls("listAppointmentMessages").length, before, "another appointment's message refreshed this thread");
    items = [...items, msg("m2", "Second", { created_at: "2026-10-12T07:10:00Z" })];
    await act(async () => { broadcastNotification({ id: "n2", type: "appointment_message", payload: { appointment_id: "a-up" } }); });
    await settle();
    assert.match(ui.thread().textContent, /Second/);
    await ui.unmount();
});

test("older messages load from the cursor and come before the newer ones", async () => {
    api.__respond("listAppointments", { data: { items: [appt()] } });
    api.__respond("listAppointmentMessages", (_id, opts = {}) => (opts.before_id
        ? page([msg("m0", "Oldest", { created_at: "2026-10-12T06:00:00Z" })])
        : page([msg("m1", "Newer")], { next_cursor: { before_created_at: "2026-10-12T07:00:00Z", before_id: "m1" } })));
    const ui = await mountPage();
    await click(ui.button("Message Kamran"));
    await click(ui.thread().querySelector("[data-thread-older]"));
    assert.deepEqual(api.__calls("listAppointmentMessages").at(-1).args[1], { before_created_at: "2026-10-12T07:00:00Z", before_id: "m1" });
    const texts = [...ui.thread().querySelectorAll("[data-message]")].map(li => li.textContent);
    assert.ok(/Oldest/.test(texts[0]) && /Newer/.test(texts[1]), `order: ${texts}`);
    await ui.unmount();
});

test("long words wrap inside the bubble instead of widening the page", async () => {
    api.__respond("listAppointments", { data: { items: [appt()] } });
    api.__respond("listAppointmentMessages", page([msg("m1", "x".repeat(400))]));
    const ui = await mountPage();
    await click(ui.button("Message Kamran"));
    const li = ui.thread().querySelector("[data-message]");
    assert.match(li.getAttribute("style"), /max-width: min\(88%, 520px\)/);
    assert.match(li.lastElementChild.getAttribute("style"), /overflow-wrap: anywhere/);
    await ui.unmount();
});

test("a message notification's link opens the appointment ON its thread", async () => {
    nav().params = new Map([["appointment", "a-up"], ["thread", "open"]]);
    api.__respond("listAppointments", { data: { items: [appt()] } });
    api.__respond("listAppointmentMessages", page([msg("m1", "Hello")]));
    const ui = await mountPage();
    assert.ok(ui.container.querySelector('[data-appointment-detail="a-up"]'));
    assert.ok(ui.thread(), "the thread did not open from the link");
    await ui.unmount();
});

test("Tracking's card uses the same entry and the same thread", async () => {
    nav().params = new Map();
    api.__respond("listAppointments", { data: { items: [appt()] } });
    api.__respond("listAppointmentMessages", page([msg("m1", "From Tracking")]));
    const ui = await mountPage({ standalone: null });
    // Tracking's own navigation (a div), as the other Tracking tests open it.
    await click([...ui.container.querySelectorAll("div")].find(el => el.textContent.trim() === "Appointments"));
    await click(ui.button("Message Kamran"));
    assert.equal(ui.thread()?.getAttribute("data-appointment-thread"), "a-up");
    assert.match(ui.thread().textContent, /From Tracking/);
    await ui.unmount();
});
