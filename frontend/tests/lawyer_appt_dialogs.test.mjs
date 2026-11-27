/* Lawyer AppointmentsPage — the Accept and Complete dialogs (2026-10-12).
 *
 * Accept shows what is being agreed to and, for a video request, takes the
 * joining link WITH the confirmation. Complete records the outcome: it took
 * place (with private notes) or the client did not attend. Nothing is sent
 * until the lawyer confirms in the dialog.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/" });
function define(name, value) {
    Object.defineProperty(globalThis, name, { value, writable: true, configurable: true });
}
for (const name of ["window", "document", "navigator", "HTMLElement", "Element", "Node", "Event",
                    "CustomEvent", "MouseEvent", "MutationObserver", "getComputedStyle", "localStorage",
                    "requestAnimationFrame", "cancelAnimationFrame", "sessionStorage"]) {
    define(name, dom.window[name]);
}
define("IS_REACT_ACT_ENVIRONMENT", true);

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
const { createElement: h } = React;

function appointment(over = {}) {
    const when = new Date(Date.now() + 48 * 36e5);
    return {
        id: "apt-1", scheduled_at: when.toISOString(), end_at: new Date(when.getTime() + 36e5).toISOString(),
        duration_minutes: 60, client_name: "Ayesha Bibi", mode: "video", notes: "Rent notice",
        status: "pending", case_id: null, schedule_version: 2, ...over,
    };
}

async function mount(items) {
    api.__respond("listAppointments", { data: { items } });
    const { AppointmentsPage } = await import("../src/components/lawyer/AppointmentsPage.jsx");
    const { NotifCtx } = await import("../src/components/lawyer/theme.js");
    const container = dom.window.document.createElement("div");
    dom.window.document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => {
        root.render(h(NotifCtx.Provider, { value: { addNotif: () => {} } }, h(AppointmentsPage)));
    });
    await act(async () => { await new Promise(r => realSetTimeout(r, 30)); });
    const button = (label, scope = container) => [...scope.querySelectorAll("button")]
        .find(b => b.textContent.trim() === label);
    return {
        container, button,
        dialog: () => container.querySelector('[role="dialog"]'),
        press: async (el) => {
            assert.ok(el, "control missing");
            await act(async () => { el.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true, cancelable: true })); });
            await act(async () => { await new Promise(r => realSetTimeout(r, 30)); });
        },
        type: async (el, value) => {
            const proto = el.tagName === "TEXTAREA" ? dom.window.HTMLTextAreaElement : dom.window.HTMLInputElement;
            const setter = Object.getOwnPropertyDescriptor(proto.prototype, "value").set;
            await act(async () => { setter.call(el, value); el.dispatchEvent(new dom.window.Event("input", { bubbles: true })); });
        },
        unmount: async () => { await act(async () => root.unmount()); },
    };
}

test.beforeEach(() => {
    api.__reset();
    api.__respond("bootstrapAuth", true);
    api.__respond("getMe", { data: { _id: "l1", role: "lawyer" } });
});

test.after(() => {
    for (const id of liveTimers) { realClearInterval(id); realClearTimeout(id); }
    dom.window.close();
});

test("Accept on a video request sends the joining link with the confirmation", async () => {
    api.__respond("confirmAppointment", { data: { success: true }, error: null, status: 200 });
    const ui = await mount([appointment()]);
    await ui.press(ui.button("Accept"));
    assert.ok(ui.dialog(), "Accept did not open a dialog");
    assert.match(ui.dialog().textContent, /When.*How.*Video call.*About.*General consultation.*Your diary/s);
    assert.equal(api.__calls("confirmAppointment").length, 0, "confirmed before the lawyer said so");
    await ui.type(ui.dialog().querySelector("#ld-link"), "https://meet.example.com/room-1");
    await ui.press(ui.container.querySelector("[data-accept-confirm]"));
    assert.deepEqual(api.__calls("confirmAppointment")[0].args,
                     ["apt-1", { schedule_version: 2, meeting_link: "https://meet.example.com/room-1" }]);
    assert.equal(ui.dialog(), null, "the dialog stayed open");
    await ui.unmount();
});

test("a link that is not https is refused before anything is sent", async () => {
    const ui = await mount([appointment()]);
    await ui.press(ui.button("Accept"));
    await ui.type(ui.dialog().querySelector("#ld-link"), "meet.example.com/room-1");
    assert.equal(ui.container.querySelector("[data-accept-confirm]").disabled, true);
    assert.match(ui.dialog().textContent, /starting with https:\/\//);
    await ui.unmount();
});

test("an in-person request has no link field", async () => {
    const ui = await mount([appointment({ mode: "in_person" })]);
    await ui.press(ui.button("Accept"));
    assert.equal(ui.dialog().querySelector("#ld-link"), null);
    await ui.unmount();
});

test("Complete records private notes; the client-didn't-attend choice records a no-show", async () => {
    const past = new Date(Date.now() - 3 * 36e5);
    const ended = appointment({ status: "confirmed", scheduled_at: past.toISOString(),
                                end_at: new Date(past.getTime() + 36e5).toISOString() });
    api.__respond("completeAppointment", { data: { success: true }, error: null, status: 200 });
    const ui = await mount([ended]);
    await ui.press(ui.button("Record outcome"));
    assert.match(ui.dialog().textContent, /What happened\?/);
    await ui.type(ui.dialog().querySelector("#ld-notes"), "Discussed the notice.");
    await ui.press(ui.container.querySelector("[data-close-confirm]"));
    assert.deepEqual(api.__calls("completeAppointment")[0].args, ["apt-1", { lawyer_notes: "Discussed the notice." }]);
    await ui.unmount();

    api.__respond("markNoShow", { data: { success: true }, error: null, status: 200 });
    const ui2 = await mount([ended]);
    await ui2.press(ui2.button("Record outcome"));
    await ui2.press(ui2.button("The client didn't attend", ui2.dialog()));
    await ui2.press(ui2.container.querySelector("[data-close-confirm]"));
    assert.equal(api.__calls("markNoShow").length, 1);
    await ui2.unmount();
});

/* ── a clash with the lawyer's diary (2026-10-12) ─────────────────────────── */
// The server does not check hearings or diary entries on confirm. The card says
// so, the dialog needs an explicit "accept anyway", and Accept all leaves a
// clashing request out.

function clashing() {
    const at = new Date(Date.now() + 48 * 36e5);
    at.setUTCMinutes(0, 0, 0);
    const iso = d => d.toISOString();
    return [
        appointment({ id: "apt-1", client_name: "Ayesha Bibi", scheduled_at: iso(at), end_at: iso(new Date(+at + 36e5)) }),
        appointment({ id: "apt-2", client_name: "Bilal Raza", status: "confirmed", scheduled_at: iso(at), end_at: iso(new Date(+at + 36e5)) }),
        appointment({ id: "apt-3", client_name: "Sana Ali", scheduled_at: iso(new Date(+at + 5 * 36e5)), end_at: iso(new Date(+at + 6 * 36e5)) }),
    ];
}

test("a request that clashes is flagged, and accepting it needs an explicit tick", async () => {
    api.__respond("confirmAppointment", { data: { success: true }, error: null, status: 200 });
    const ui = await mount(clashing());
    const card = ui.container.querySelector('[data-appt-card="apt-1"]');
    assert.match(card.textContent, /Clashes with: Appointment · Bilal Raza/);
    await ui.press(ui.button("Accept", card));
    const confirm = ui.container.querySelector("[data-accept-confirm]");
    assert.equal(confirm.textContent.trim(), "Accept anyway");
    assert.equal(confirm.disabled, true, "a clash was accepted without being acknowledged");
    await ui.press(ui.dialog().querySelector("[data-clash-ack] input"));
    assert.equal(ui.container.querySelector("[data-accept-confirm]").disabled, false);
    await ui.press(ui.container.querySelector("[data-accept-confirm]"));
    assert.equal(api.__calls("confirmAppointment")[0].args[0], "apt-1");
    await ui.unmount();
});

test("Accept all leaves out a request that clashes with the diary", async () => {
    api.__respond("confirmAppointment", { data: { success: true }, error: null, status: 200 });
    const ui = await mount(clashing());
    const pending = ui.container.querySelector('[data-stat="pending"]');
    await ui.press(ui.button("Accept all", pending));
    assert.match(pending.textContent, /Accept 1 request \(1 clashes with your diary — accept it one by one\)\?/);
    await ui.press(ui.button("Confirm", pending));
    assert.deepEqual(api.__calls("confirmAppointment").map(c => c.args[0]), ["apt-3"]);
    await ui.unmount();
});

/* ── after a completed consultation (2026-10-12) ──────────────────────────── */

function completed(over = {}) {
    const past = new Date(Date.now() - 30 * 36e5);
    return appointment({ status: "completed", scheduled_at: past.toISOString(),
        end_at: new Date(past.getTime() + 36e5).toISOString(), lawyer_notes: "Advised a legal notice.", ...over });
}

test("a completed consultation shows the lawyer's notes and says nothing more is needed", async () => {
    api.__respond("listEngagements", { data: [] });
    const ui = await mount([completed()]);
    const card = ui.container.querySelector('[data-appt-card="apt-1"]');
    assert.match(card.textContent, /Your notes \(only you\) · Advised a legal notice\./);
    assert.ok(card.querySelector('[data-after="none"]'), "no 'no further action' line");
    assert.match(card.textContent, /No further action needed/);
    await ui.unmount();
});

test("a hire request that followed the consultation is shown on its card", async () => {
    api.__respond("listEngagements", { data: [{ id: "E1", appointment_id: "apt-1", status: "requested", case_id: "C1" }] });
    const ui = await mount([completed()]);
    const card = ui.container.querySelector('[data-appt-card="apt-1"]');
    assert.ok(card.querySelector('[data-after="requested"]'));
    assert.ok(ui.button("Review request", card), "no way to the request");
    await ui.unmount();
});

/* ── a notification opens THAT appointment (2026-10-12) ───────────────────── */

test("an appointment named by a notification opens in the calendar's detail", async () => {
    const ui = await mount([appointment({ id: "apt-1", status: "confirmed" })]);
    await act(async () => { window.dispatchEvent(new window.CustomEvent("attorney:open-appointment", { detail: "apt-1" })); });
    await act(async () => { await new Promise(r => realSetTimeout(r, 40)); });
    assert.ok(ui.container.querySelector('[data-appointment-detail="apt-1"]'), "the appointment did not open");
    await ui.unmount();
});

test("an unknown appointment id leaves the page as it is", async () => {
    const ui = await mount([appointment({ id: "apt-1", status: "confirmed" })]);
    await act(async () => { window.dispatchEvent(new window.CustomEvent("attorney:open-appointment", { detail: "nope" })); });
    await act(async () => { await new Promise(r => realSetTimeout(r, 40)); });
    assert.equal(ui.container.querySelector("[data-appointment-detail]"), null);
    assert.ok(ui.container.querySelector('[data-appt-card="apt-1"]'), "the list was lost");
    await ui.unmount();
});
/* ── Review request opens THAT request (2026-10-12) ───────────────────────── */

test("Review request stores and announces the exact request", async () => {
    api.__respond("listEngagements", { data: [{ id: "E7", appointment_id: "apt-1", status: "requested", case_id: "C1" }] });
    const heard = [];
    const on = (e) => heard.push(e.detail);
    window.addEventListener("attorney:open-request", on);
    const ui = await mount([completed()]);
    await ui.press(ui.button("Review request", ui.container.querySelector('[data-appt-card="apt-1"]')));
    window.removeEventListener("attorney:open-request", on);
    assert.equal(window.sessionStorage.getItem("attorney:lawyer-open-request"), "E7");
    assert.deepEqual(heard, ["E7"]);
    window.sessionStorage.removeItem("attorney:lawyer-open-request");
    await ui.unmount();
});
/* ── the appointment's message thread, lawyer side (2026-10-12) ───────────── */

const threadPage = (over = {}) => ({ data: { items: [{ id: "m1", appointment_id: "apt-1", sender_id: "c1", sender_role: "client",
    sender_name: "Ayesha Bibi", text: "Link not opening", created_at: "2026-10-12T07:00:00Z", from_me: false, client_key: null }],
    next_cursor: null, can_send: true, send_state: "open", appointment_status: "confirmed", ...over }, error: null, status: 200 });

test("Message client on a confirmed card opens that appointment's thread in the detail", async () => {
    api.__respond("listAppointmentMessages", threadPage());
    const ui = await mount([appointment({ id: "apt-1", status: "confirmed" })]);
    await ui.press(ui.button("Message client", ui.container.querySelector('[data-appt-card="apt-1"]')));
    const th = ui.container.querySelector('[data-appointment-thread="apt-1"]');
    assert.ok(ui.container.querySelector('[data-appointment-detail="apt-1"]'), "the detail did not open");
    assert.ok(th, "the thread did not open");
    assert.match(th.textContent, /Ayesha Bibi .*Link not opening/s);
    assert.ok(th.querySelector("textarea"), "no composer on an open thread");
    await ui.unmount();
});

test("a pending request offers no message thread", async () => {
    const ui = await mount([appointment({ id: "apt-1", status: "pending" })]);
    assert.equal(ui.container.querySelector("[data-message-client]"), null);
    await act(async () => { window.dispatchEvent(new window.CustomEvent("attorney:open-appointment", { detail: "apt-1" })); });
    await act(async () => { await new Promise(r => realSetTimeout(r, 40)); });
    const detail = ui.container.querySelector('[data-appointment-detail="apt-1"]');
    assert.ok(detail);
    assert.equal(ui.button("Message client", detail), undefined);
    await ui.unmount();
});

test("an ended appointment's thread is read-only for the lawyer", async () => {
    api.__respond("listAppointmentMessages", threadPage({ can_send: false, send_state: "read_only", appointment_status: "completed" }));
    const past = new Date(Date.now() - 30 * 36e5);
    const ui = await mount([appointment({ id: "apt-1", status: "completed", scheduled_at: past.toISOString(), end_at: new Date(+past + 36e5).toISOString() })]);
    await act(async () => { window.dispatchEvent(new window.CustomEvent("attorney:open-appointment", { detail: "apt-1" })); });
    await act(async () => { await new Promise(r => realSetTimeout(r, 40)); });
    await ui.press(ui.button("View messages", ui.container.querySelector('[data-appointment-detail="apt-1"]')));
    const th = ui.container.querySelector('[data-appointment-thread="apt-1"]');
    assert.equal(th.getAttribute("data-thread-state"), "read_only");
    assert.equal(th.querySelector("textarea"), null);
    await ui.unmount();
});

test("a message notification opens the appointment on its thread", async () => {
    api.__respond("listAppointmentMessages", threadPage());
    window.sessionStorage.setItem("attorney:lawyer-open-appointment", "apt-1");
    window.sessionStorage.setItem("attorney:lawyer-open-appointment-thread", "apt-1");
    const ui = await mount([appointment({ id: "apt-1", status: "confirmed" })]);
    assert.ok(ui.container.querySelector('[data-appointment-thread="apt-1"]'), "the thread did not open from the notification");
    assert.equal(window.sessionStorage.getItem("attorney:lawyer-open-appointment-thread"), null);
    await ui.unmount();
});

/* Suggest other times (2026-10-19): the lawyer offers PKT times on the half
 * hour; nothing moves or confirms until the client picks one. */
test("Suggest other times sends PKT options and a note, and the card says what was offered", async () => {
    const day = new Date(Date.now() + 5 * 36e5 + 3 * 864e5).toISOString().slice(0, 10);
    api.__respond("suggestAppointmentTimes", { data: appointment(), error: null });
    const ui = await mount([appointment()]);
    // After sending, the page re-reads: the row now carries the suggestion.
    api.__respond("listAppointments", { data: { items: [appointment({ time_suggestion: { options: [`${day}T10:00:00Z`], note: "In court" } })] } });
    await ui.press(ui.container.querySelector("[data-suggest-times]"));
    const dlg = ui.container.querySelector("[data-suggest-dialog]");
    assert.ok(dlg, "the dialog did not open");
    assert.equal(api.__calls("confirmAppointment").length, 0);
    const date = dlg.querySelector('[data-suggest-row="0"] input[type="date"]');
    await ui.type(date, day);
    const select = dlg.querySelector('[data-suggest-row="0"] select');
    await act(async () => {
        Object.getOwnPropertyDescriptor(dom.window.HTMLSelectElement.prototype, "value").set.call(select, "15:00");
        select.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
    });
    await ui.type(dlg.querySelector("#sg-note"), "In court");
    await ui.press(dlg.querySelector("[data-suggest-send]"));
    const call = api.__calls("suggestAppointmentTimes").at(-1);
    assert.equal(call?.args?.[0], "apt-1");
    assert.deepEqual(call.args[1].options, [`${day}T10:00:00.000Z`], "15:00 PKT is 10:00 UTC");
    assert.equal(call.args[1].note, "In court");
    assert.equal(api.__calls("confirmAppointment").length, 0, "suggesting must not confirm");
    assert.equal(ui.container.querySelector("[data-suggest-dialog]"), null, "the dialog stayed open");
    assert.match(ui.container.querySelector("[data-suggested-times]")?.textContent || "", /You suggested/);
    await ui.unmount();
});

/* Moving a CONFIRMED appointment by agreement (2026-10-19). */
test("Propose new time sends a PKT time; a client's proposal can be accepted, keeping the old time until then", async () => {
    const day = new Date(Date.now() + 5 * 36e5 + 4 * 864e5).toISOString().slice(0, 10);
    api.__respond("proposeNewTime", { data: appointment({ status: "confirmed" }), error: null });
    const ui = await mount([appointment({ status: "confirmed" })]);
    await ui.press(ui.container.querySelector("[data-propose-time]"));
    const dlg = ui.container.querySelector("[data-propose-dialog]");
    assert.ok(dlg, "the dialog did not open");
    await ui.type(dlg.querySelector('input[type="date"]'), day);
    const select = dlg.querySelector("select");
    await act(async () => {
        Object.getOwnPropertyDescriptor(dom.window.HTMLSelectElement.prototype, "value").set.call(select, "16:30");
        select.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
    });
    await ui.press(dlg.querySelector("[data-propose-send]"));
    const call = api.__calls("proposeNewTime").at(-1);
    assert.equal(call?.args?.[0], "apt-1");
    assert.equal(call.args[1].scheduledAt, `${day}T11:30:00.000Z`, "16:30 PKT is 11:30 UTC");
    await ui.unmount();

    const proposal = { id: "p1", by: "client", scheduled_at: `${day}T11:30:00Z`, note: "Clash at work",
                       expires_at: new Date(Date.now() + 864e5).toISOString() };
    api.__respond("acceptNewTime", { data: appointment({ status: "confirmed" }), error: null });
    const ui2 = await mount([appointment({ status: "confirmed", reschedule_proposal: proposal })]);
    assert.ok(ui2.container.querySelector('[data-proposal="client"]'), "the client's proposal is not shown");
    assert.equal(ui2.container.querySelector("[data-propose-time]"), null, "a second proposal must wait");
    await ui2.press(ui2.container.querySelector("[data-accept-proposal]"));
    assert.deepEqual(api.__calls("acceptNewTime").at(-1)?.args, ["apt-1", "p1"]);
    await ui2.unmount();
});

test("an ended appointment reads Needs outcome, and the outcome dialog offers I couldn't attend", async () => {
    const past = new Date(Date.now() - 3 * 36e5);
    const ended = appointment({ status: "confirmed", scheduled_at: past.toISOString(),
                                end_at: new Date(past.getTime() + 36e5).toISOString() });
    api.__respond("cancelAppointment", { data: { success: true }, error: null, status: 200 });
    const ui = await mount([ended]);
    assert.ok(ui.container.querySelector("[data-needs-outcome]"), "an ended appointment still reads Upcoming");
    await ui.press(ui.button("Record outcome"));
    const opt = [...ui.dialog().querySelectorAll('[role="radio"]')].find(b => /couldn't attend/.test(b.textContent));
    assert.ok(opt, "no 'I couldn't attend' outcome");
    await ui.press(opt);
    await ui.press(ui.container.querySelector("[data-close-confirm]"));
    assert.deepEqual(api.__calls("cancelAppointment").at(-1)?.args, ["apt-1", null, "lawyer_no_show"]);
    await ui.unmount();
});

/* One outcome interface (2026-10-19): the Needs-outcome strip opens the same
 * four-option dialog as the card instead of its own Completed / No Show. */
test("the Needs outcome tab: each row has one Record outcome that opens the same dialog", async () => {
    // 2026-10-20: the strip above the tabs became the "Needs outcome" tab, its
    // rows drawn as the ordinary card.
    const past = new Date(Date.now() - 5 * 36e5);
    const ended = appointment({ status: "confirmed", scheduled_at: past.toISOString(),
                                end_at: new Date(past.getTime() + 36e5).toISOString() });
    api.__respond("listPendingOutcomes", { data: { items: [{ ...ended, client_name: "Ayesha Bibi" }], next_cursor: null }, error: null });
    const ui = await mount([]);
    assert.equal(ui.container.querySelector("[data-strip-record]"), null, "the old strip is still above the tabs");
    await ui.press([...ui.container.querySelectorAll('[role="tab"]')].find(b => /^Needs outcome/.test(b.textContent.trim())));
    const list = ui.container.querySelector(".lc-list");
    const texts = [...list.querySelectorAll("button")].map(b => b.textContent.trim());
    assert.ok(!texts.includes("Completed"), "a row still has its own Completed button");
    await ui.press([...list.querySelectorAll("button")].find(b => b.textContent.trim() === "Record outcome"));
    const radios = [...ui.dialog().querySelectorAll('[role="radio"]')].map(b => b.textContent.trim());
    assert.deepEqual(radios, ["It took place", "The client didn't attend", "I couldn't attend", "It didn't take place"]);
    await ui.unmount();
});

/* 2026-11-27: the list reads like an agenda -- a heading per day, the time on
 * the left of each row, and no second "date" in the row itself. */
test("the list has one heading per day and the time on each row", async () => {
    const day1 = new Date(Date.UTC(2030, 0, 8, 6, 0));   // 11:00 PKT
    const day2 = new Date(Date.UTC(2030, 0, 9, 6, 0));
    const iso = d => d.toISOString();
    const ui = await mount([
        appointment({ id: "d1a", client_name: "Ayesha Bibi", scheduled_at: iso(day1), end_at: iso(new Date(+day1 + 36e5)) }),
        appointment({ id: "d1b", client_name: "Bilal Raza", scheduled_at: iso(new Date(+day1 + 2 * 36e5)), end_at: iso(new Date(+day1 + 3 * 36e5)) }),
        appointment({ id: "d2a", client_name: "Sana Ali", scheduled_at: iso(day2), end_at: iso(new Date(+day2 + 36e5)) }),
    ]);
    const heads = [...ui.container.querySelectorAll(".lc-list [data-day-head]")].map(h => h.textContent);
    assert.equal(heads.length, 2, `expected one heading per day, got ${JSON.stringify(heads)}`);
    const row = ui.container.querySelector('[data-appt-card="d1a"]');
    assert.match(row.querySelector(".lc-time").textContent, /11:00/);
    assert.equal(row.querySelector(".lc-day-small"), null, "the row repeats the day under its heading");
    await ui.unmount?.();
});
