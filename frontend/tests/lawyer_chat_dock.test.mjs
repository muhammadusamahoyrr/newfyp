/* The lawyer's floating chat windows (2026-10-19).
 *
 * "Message client" opens a small window in the corner -- the page does not
 * jump to the calendar. An open window marks its thread read; a minimised one
 * shows the server's unread count; at most three are open. Cards show the
 * card says when the client wrote: a chat icon with the count in its corner. */
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/" });
function define(name, value) {
    Object.defineProperty(globalThis, name, { value, writable: true, configurable: true });
}
for (const name of ["window", "document", "navigator", "HTMLElement", "Element", "Node", "Event",
                    "CustomEvent", "MouseEvent", "KeyboardEvent", "MutationObserver", "getComputedStyle", "localStorage",
                    "requestAnimationFrame", "cancelAnimationFrame", "sessionStorage"]) {
    define(name, dom.window[name]);
}
define("IS_REACT_ACT_ENVIRONMENT", true);
dom.window.HTMLElement.prototype.scrollIntoView = function () {};

const liveTimers = new Set();
const realSetInterval = globalThis.setInterval;
const realClearInterval = globalThis.clearInterval;
const realSetTimeout = globalThis.setTimeout;
const realClearTimeout = globalThis.clearTimeout;
define("setInterval", (...a) => { const id = realSetInterval(...a); liveTimers.add(id); return id; });
define("clearInterval", id => { liveTimers.delete(id); return realClearInterval(id); });
define("setTimeout", (...a) => { const id = realSetTimeout(...a); liveTimers.add(id); return id; });
define("clearTimeout", id => { liveTimers.delete(id); return realClearTimeout(id); });

const React = (await import("react")).default;
const { act } = await import("react");
const { createRoot } = await import("react-dom/client");
const api = await import("./support/api-stub.mjs");
const { ChatDockProvider, useChatDock } = await import("../src/components/lawyer/ChatDock.jsx");
const h = React.createElement;
const settle = () => act(async () => { await new Promise(r => realSetTimeout(r, 30)); });
const click = async (el) => {
    assert.ok(el, "control missing");
    await act(async () => { el.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true, cancelable: true })); });
    await settle();
};

test.beforeEach(() => {
    api.__reset();
    api.__respond("bootstrapAuth", true);
    api.__respond("getMe", { data: { _id: "l1", role: "lawyer" } });
    api.__respond("listAppointmentMessages", { data: { items: [], can_send: true, send_state: "open", next_cursor: null } });
    api.__respond("markThreadRead", { data: { ok: true }, error: null });
    document.body.innerHTML = "";
    // These tests use the small floating windows; the docked panel has its own below.
    localStorage.setItem("attorney:lawyer-chat-docked", "0");
});
test.after(() => {
    for (const id of liveTimers) { realClearInterval(id); realClearTimeout(id); }
    dom.window.close();
});

async function mountDock() {
    let dock;
    function Grab() { dock = useChatDock(); return null; }
    const box = document.createElement("div");
    document.body.appendChild(box);
    const root = createRoot(box);
    await act(async () => root.render(h(ChatDockProvider, null, h(Grab))));
    return { box, dock: () => dock, unmount: () => act(async () => root.unmount()) };
}

test("a chat opens in the corner and marks its thread read", async () => {
    const ui = await mountDock();
    await act(async () => ui.dock().openChat({ id: "a1", client: "Ayesha Bibi", at: new Date().toISOString() }));
    await settle();
    const win = document.querySelector('[data-chat-window="a1"]');
    assert.ok(win, "no chat window");
    assert.match(win.textContent, /Ayesha Bibi/);
    assert.ok(win.querySelector('[data-appointment-thread="a1"]'), "the thread is not in the window");
    assert.deepEqual(api.__calls("markThreadRead").map(c => c.args[0]), ["a1"]);
    await ui.unmount();
});

test("minimised, it is a bubble with the server's unread count; clicking opens it again", async () => {
    api.__respond("getThreadSummary", { data: { items: { a1: { unread: 3, last: { text: "hi", from_me: false } } } } });
    const ui = await mountDock();
    await act(async () => ui.dock().openChat({ id: "a1", client: "Ayesha Bibi" }));
    await settle();
    await click(document.querySelector("[data-chat-min]"));
    const pill = document.querySelector('[data-chat-pill="a1"]');
    assert.ok(pill, "no bubble");
    assert.equal(pill.querySelector("[data-chat-unread]").textContent, "3");
    await click(pill);
    assert.ok(document.querySelector('[data-chat-window="a1"]'));
    await ui.unmount();
});

test("at most three windows: a fourth closes the oldest", async () => {
    const ui = await mountDock();
    for (const id of ["a1", "a2", "a3", "a4"]) await act(async () => ui.dock().openChat({ id, client: `Client ${id}` }));
    await settle();
    const open = [...document.querySelectorAll("[data-chat-window]")].map(w => w.getAttribute("data-chat-window"));
    assert.deepEqual(open, ["a2", "a3", "a4"]);
    await click(document.querySelector('[data-chat-window="a2"] [data-chat-close]'));
    assert.equal(document.querySelector('[data-chat-window="a2"]'), null);
    await ui.unmount();
});

test("on the appointments page: the card shows what is new, and Message opens the chat without leaving the list", async () => {
    const when = new Date(Date.now() + 48 * 36e5);
    api.__respond("listAppointments", { data: { items: [{
        id: "apt-1", scheduled_at: when.toISOString(), end_at: new Date(when.getTime() + 36e5).toISOString(),
        duration_minutes: 60, client_name: "Ayesha Bibi", mode: "video", status: "confirmed", case_id: null, schedule_version: 1,
    }] } });
    api.__respond("getThreadSummary", { data: { items: { "apt-1": { unread: 2, last: { text: "hey ustad", from_me: false } } } } });
    const { AppointmentsPage } = await import("../src/components/lawyer/AppointmentsPage.jsx");
    const { NotifCtx } = await import("../src/components/lawyer/theme.js");
    const box = document.createElement("div");
    document.body.appendChild(box);
    const root = createRoot(box);
    await act(async () => root.render(h(NotifCtx.Provider, { value: { addNotif: () => {} } },
        h(ChatDockProvider, null, h(AppointmentsPage)))));
    await settle(); await settle();
    const preview = box.querySelector('[data-thread-preview="apt-1"]');
    assert.ok(preview, "no thread preview on the card");
    assert.equal(preview.querySelector("b").textContent, "2");
    assert.match(preview.getAttribute("aria-label"), /2 new messages/);
    assert.ok(preview.classList.contains("lc-newmsg") && !preview.closest(".lc-actions"), "the new-message icon sits in the card corner");
    assert.match(preview.getAttribute("title"), /hey ustad/);
    assert.match(box.querySelector("[data-message-client]").textContent, /Message client \(2\)/);
    await click(box.querySelector("[data-message-client]"));
    assert.ok(document.querySelector('[data-chat-window="apt-1"]'), "Message did not open the chat");
    assert.ok(box.querySelector("[data-appt-card], .lc"), "the list was replaced");
    assert.equal(box.querySelector("[data-appointment-detail]"), null, "it jumped to the calendar detail");
    await act(async () => root.unmount());
});

test("an empty chat offers quick replies; one click fills the composer, nothing is sent", async () => {
    const ui = await mountDock();
    await act(async () => ui.dock().openChat({ id: "a9", client: "Ayesha Bibi" }));
    await settle(); await settle();
    const win = document.querySelector('[data-chat-window="a9"]');
    assert.match(win.querySelector("[data-thread-empty]").textContent, /Start the conversation with Ayesha/);
    const chip = [...win.querySelectorAll("[data-thread-suggestion]")].find(b => /running 10 minutes late/.test(b.textContent));
    await click(chip);
    assert.equal(win.querySelector("textarea").value, "I'm running 10 minutes late.");
    assert.equal(api.__calls("sendAppointmentMessage").length, 0);
    assert.ok(win.querySelector("[data-thread-compose] [data-thread-send]"), "compact composer with its send button");
    await ui.unmount();
});


/* ── docked: a full-height side panel; the page makes room (2026-10-20) ── */

test("docked (the default), the chat is a full-height panel OVER the page, which is dimmed, not squeezed", async () => {
    localStorage.removeItem("attorney:lawyer-chat-docked");
    const ui = await mountDock();
    await settle();
    await act(async () => ui.dock().openChat({ id: "d1", client: "Ayesha Bibi" }));
    await settle();
    const panel = document.querySelector("[data-chat-panel]");
    assert.ok(panel, "no docked panel");
    assert.equal(panel.getAttribute("data-chat-window"), "d1");
    assert.ok(!document.documentElement.hasAttribute("data-chat-docked"), "the page must not be squeezed");
    const scrim = document.querySelector("[data-chat-scrim]");
    assert.ok(scrim, "the page behind is not dimmed");
    assert.deepEqual(api.__calls("markThreadRead").map(c => c.args[0]), ["d1"]);
    // A second chat is a tab; only the chat on screen is marked read.
    await act(async () => ui.dock().openChat({ id: "d2", client: "Bilal Khan" }));
    await settle();
    assert.deepEqual([...document.querySelectorAll("[data-chat-tab]")].map(t => t.getAttribute("data-chat-tab")), ["d1", "d2"]);
    assert.equal(document.querySelector("[data-chat-panel]").getAttribute("data-chat-window"), "d2");
    await click(document.querySelector('[data-chat-tab="d1"]'));
    assert.equal(document.querySelector("[data-chat-panel]").getAttribute("data-chat-window"), "d1");
    // "–" tucks them into bubbles and lifts the dim.
    await click(document.querySelector("[data-chat-min]"));
    assert.equal(document.querySelector("[data-chat-panel]"), null);
    assert.equal(document.querySelector("[data-chat-scrim]"), null);
    assert.equal(document.querySelectorAll("[data-chat-pill]").length, 2);
    await click(document.querySelector('[data-chat-pill="d2"]'));
    assert.equal(document.querySelector("[data-chat-panel]").getAttribute("data-chat-window"), "d2");
    await ui.unmount();
});

test("the lawyer can pop the docked chat out into a small window, and the choice is remembered", async () => {
    localStorage.removeItem("attorney:lawyer-chat-docked");
    const ui = await mountDock();
    await settle();
    await act(async () => ui.dock().openChat({ id: "d1", client: "Ayesha Bibi" }));
    await settle();
    await click(document.querySelector("[data-chat-mode]"));
    assert.equal(document.querySelector("[data-chat-panel]"), null);
    assert.ok(document.querySelector('.cd-win[data-chat-window="d1"]'), "no floating window");
    assert.equal(localStorage.getItem("attorney:lawyer-chat-docked"), "0");
    await ui.unmount();
});


test("nothing new from the client: no chip, the row stays clean", async () => {
    const when = new Date(Date.now() + 48 * 36e5);
    api.__respond("listAppointments", { data: { items: [{
        id: "apt-2", scheduled_at: when.toISOString(), end_at: new Date(when.getTime() + 36e5).toISOString(),
        duration_minutes: 60, client_name: "Bilal Khan", mode: "video", status: "confirmed", case_id: null, schedule_version: 1,
    }] } });
    api.__respond("getThreadSummary", { data: { items: { "apt-2": { unread: 0, last: { text: "Please bring your documents.", from_me: true } } } } });
    const { AppointmentsPage } = await import("../src/components/lawyer/AppointmentsPage.jsx");
    const { NotifCtx } = await import("../src/components/lawyer/theme.js");
    const box = document.createElement("div");
    document.body.appendChild(box);
    const root = createRoot(box);
    await act(async () => root.render(h(NotifCtx.Provider, { value: { addNotif: () => {} } },
        h(ChatDockProvider, null, h(AppointmentsPage)))));
    await settle(); await settle();
    assert.equal(box.querySelector("[data-thread-preview]"), null);
    assert.equal(box.querySelector("[data-message-client]").textContent, "Message client");
    await act(async () => root.unmount());
});
