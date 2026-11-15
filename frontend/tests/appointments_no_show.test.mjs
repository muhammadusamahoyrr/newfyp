/* Lawyer AppointmentsPage — the no-show action and its label.
 *
 * A half-built feature. The endpoint (`PATCH /appointments/{id}/no-show`), the
 * API client function (`markNoShow`), the `NO_SHOW` status and the CLIENT-side
 * rendering ("👻 No Show" in ModTracking) all existed. The lawyer — the only
 * person who can record a no-show — had no control for it, and the lawyer's own
 * status map read:
 *
 *     no_show: "Cancelled"
 *
 * so an appointment the client failed to attend was reported to the lawyer as
 * one that had been called off. That is a different fact, and the only one of
 * the two that is the client's fault. The two sides of a single appointment
 * disagreed with each other.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>",
                      { url: "http://localhost/" });
function define(name, value) {
    Object.defineProperty(globalThis, name, {
        value, writable: true, configurable: true,
    });
}
for (const name of ["window", "document", "navigator", "HTMLElement",
                    "Element", "Node", "Event", "CustomEvent", "MouseEvent",
                    "MutationObserver", "getComputedStyle", "localStorage",
                    "requestAnimationFrame", "cancelAnimationFrame"]) {
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

/* An appointment as the API returns one. `status` is the BACKEND value; the
 * page maps it to a display label, and that mapping is what is under test. */
function appointment(over = {}) {
    const when = new Date(Date.now() + 36e5).toISOString();
    return {
        id: "apt-1",
        scheduled_at: when,
        client_name: "Ayesha Bibi",
        duration_minutes: 30,
        mode: "video",
        notes: "Consultation",
        status: "confirmed",
        case_id: null,
        ...over,
    };
}

async function mountAppointments(items) {
    api.__respond("listAppointments", { data: { items } });
    // Named export, not default.
    const { AppointmentsPage } =
        await import("../src/components/lawyer/AppointmentsPage.jsx");

    const { NotifCtx } = await import("../src/components/lawyer/theme.js");

    const container = dom.window.document.createElement("div");
    dom.window.document.body.appendChild(container);
    const root = createRoot(container);
    // NotifCtx is required, not optional: `useNotif()` falls back to `{}` when
    // unprovided, so `addNotif` would be undefined and EVERY action handler on
    // this page — confirm, cancel, complete, no-show — would throw on use.
    await act(async () => {
        root.render(h(NotifCtx.Provider, { value: { addNotif: () => {} } },
                      h(AppointmentsPage)));
    });
    await act(async () => { await new Promise(r => setTimeout(r, 30)); });

    return {
        container,
        text: () => container.textContent,
        settle: async (ms = 40) => {
            await act(async () => { await new Promise(r => setTimeout(r, ms)); });
        },
        // Status badges only, and identified structurally.
        //
        // Two other things on this page render the same words: the tab strip
        // ("Cancelled", "No Show" as filters) and the stat cards ("Upcoming",
        // "Pending", "Completed" as counters). A whole-page text scan, or a
        // scan of every <span>, matches those too and would report a badge that
        // is not there — so this selects on what makes a StatusBadge unique:
        // it is the only one of the three that wraps a nested dot <span>.
        badges: () => [...container.querySelectorAll("span")]
            .filter(el => el.querySelector("span"))
            .map(el => el.textContent.trim())
            .filter(txt => ["Upcoming", "Pending", "Completed",
                            "Cancelled", "No Show"].includes(txt)),
        click: async (label) => {
            const btn = [...container.querySelectorAll('button:not([role="tab"])')]
                .find(b => b.textContent.trim() === label);
            assert.ok(btn, `no button labelled ${label!== undefined ? JSON.stringify(label) : label}`);
            await act(async () => {
                btn.dispatchEvent(new dom.window.MouseEvent(
                    "click", { bubbles: true, cancelable: true }));
            });
            await act(async () => { await new Promise(r => setTimeout(r, 30)); });
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
    liveTimers.clear();
    dom.window.close();
});

/* ── the label ────────────────────────────────────────────────────────────── */

test("a no-show appointment is labelled No Show, not Cancelled", async () => {
    // THE defect. `no_show` was mapped to "Cancelled" in the lawyer's view.
    const ui = await mountAppointments([appointment({ status: "no_show" })]);

    assert.deepEqual(ui.badges(), ["No Show"],
                     "a no-show was not badged as No Show");
    assert.ok(!ui.badges().includes("Cancelled"),
              "a no-show was still reported to the lawyer as a cancellation");
    await ui.unmount();
});

test("a cancelled appointment is still labelled Cancelled", async () => {
    // The other half: fixing one label must not swallow the other.
    const ui = await mountAppointments([appointment({ status: "cancelled" })]);

    assert.deepEqual(ui.badges(), ["Cancelled"]);
    await ui.unmount();
});

test("the two statuses are distinguishable side by side", async () => {
    const ui = await mountAppointments([
        appointment({ id: "a1", status: "no_show", client_name: "Absent Client" }),
        appointment({ id: "a2", status: "cancelled", client_name: "Called Off" }),
    ]);

    assert.deepEqual(ui.badges().sort(), ["Cancelled", "No Show"]);
    await ui.unmount();
});

/* ── the action ───────────────────────────────────────────────────────────── */

/* An appointment that has already begun.
 *
 * The server will not record a no-show for a meeting that has not started —
 * the client cannot yet have failed to attend it — so this is the state the
 * action actually applies to. The default fixture is an hour in the FUTURE,
 * which is now deliberately not actionable. */
function started(over = {}) {
    return appointment({
        scheduled_at: new Date(Date.now() - 36e5).toISOString(),
        status: "confirmed",
        ...over,
    });
}

/* ONE outcome interface (2026-10-20): there is no standalone "No Show"
 * button. "Record outcome" opens the four-option dialog, whose "The client
 * didn't attend" records the no-show through the same endpoint. */
const listButtons = (ui) => [...ui.container.querySelectorAll('button:not([role="tab"])')];
async function press(ui, el) {
    assert.ok(el, "control missing");
    await act(async () => { el.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true, cancelable: true })); });
    await act(async () => { await new Promise(r => setTimeout(r, 30)); });
}
async function recordNoShow(ui) {
    await press(ui, listButtons(ui).find(b => b.textContent.trim() === "Record outcome"));
    await press(ui, [...dom.window.document.querySelectorAll('[role="radio"]')].find(b => b.textContent.trim() === "The client didn't attend"));
    await press(ui, dom.window.document.querySelector("[data-close-confirm]"));
}

test("an ended meeting offers Record outcome, and no standalone No Show button", async () => {
    const ui = await mountAppointments([started()]);
    const rec = listButtons(ui).find(b => b.textContent.trim() === "Record outcome");
    assert.ok(rec, "no Record outcome on an ended confirmed appointment");
    assert.equal(rec.disabled, false, "it must be usable, not merely present");
    assert.equal(listButtons(ui).filter(b => /^No[- ]?Show$/i.test(b.textContent.trim())).length, 0, "a standalone No Show button is back");
    await ui.unmount();
});

test("a meeting under way: Record outcome opens with only 'The client didn't attend' open", async () => {
    const ui = await mountAppointments([appointment({ scheduled_at: new Date(Date.now() - 20 * 6e4).toISOString(), duration_minutes: 60 })]);
    await press(ui, listButtons(ui).find(b => b.textContent.trim() === "Record outcome"));
    const radios = [...dom.window.document.querySelectorAll('[role="radio"]')];
    const opt = label => radios.find(b => b.textContent.trim() === label);
    assert.equal(opt("The client didn't attend").disabled, false);
    assert.equal(opt("The client didn't attend").getAttribute("aria-checked"), "true", "the only open choice was not preselected");
    assert.equal(opt("It took place").disabled, true, "a meeting not yet ended could be completed");
    await ui.unmount();
});

test("No outcome control before the appointment starts", async () => {
    // Outcome controls appear when they apply instead of sitting disabled.
    const ui = await mountAppointments([appointment({ status: "confirmed" })]);
    assert.equal(listButtons(ui).find(b => /^(No Show|Record outcome)$/.test(b.textContent.trim())), undefined,
        "a future appointment offered an outcome");
    assert.equal(api.__calls("markNoShow").length, 0);
    await ui.unmount();
});

test("a no-show recorded from the dialog calls the existing endpoint and updates the row",
     async () => {
    api.__respond("markNoShow", { data: { success: true } });
    const ui = await mountAppointments([started()]);
    // The server now holds a no-show; the re-read after recording shows it.
    api.__respond("listAppointments", () => ({ data: { items: [started({ status: "no_show" })] } }));

    // An ended confirmed appointment reads "Needs outcome" (2026-10-19).
    assert.ok(ui.container.querySelector("[data-needs-outcome]"),
              "the row did not start as a confirmed appointment awaiting its outcome");

    await recordNoShow(ui);

    // The EXISTING API function, with the appointment id — no new endpoint.
    const calls = api.__calls("markNoShow");
    assert.equal(calls.length, 1, "markNoShow was not called exactly once");
    assert.deepEqual(calls[0].args, ["apt-1"]);
    assert.deepEqual(ui.badges(), ["No Show"]);
    await ui.unmount();
});

test("a refused no-show leaves the appointment unchanged", async () => {
    // The row must not optimistically flip on a failure.
    api.__respond("markNoShow",
                  { data: null, error: { message: "An appointment in 'cancelled' status cannot be marked 'no_show'." } });
    const ui = await mountAppointments([started()]);

    await recordNoShow(ui);

    assert.equal(api.__calls("markNoShow").length, 1);
    assert.ok(ui.container.querySelector("[data-needs-outcome]"),
              "the row changed despite the server refusing");
    assert.deepEqual(ui.badges(), []);
    await ui.unmount();
});

test("a completed appointment offers no No Show action", async () => {
    // The server accepts a no-show only from `confirmed`, so offering it
    // elsewhere would present an action the API would refuse.
    const ui = await mountAppointments([appointment({ status: "completed" })]);

    const labels = [...ui.container.querySelectorAll('button:not([role="tab"])')]
        .map(b => b.textContent.trim());
    assert.ok(!labels.includes("No Show"),
              `No Show offered on a completed appointment; buttons: ${labels}`);
    await ui.unmount();
});

/* ── a case meeting is marked apart (2026-10-20) ─────────────────────────── */

test("a meeting on an engaged case carries a Case meeting chip and edge; a consultation does not", async () => {
    const ui = await mountAppointments([
        appointment({ id: "a-case", case_meeting: true, case_number: "ATT-2026-1" }),
        appointment({ id: "a-cons", scheduled_at: new Date(Date.now() + 5 * 36e5).toISOString() }),
    ]);
    const caseCard = ui.container.querySelector('[data-appt-card="a-case"]');
    assert.ok(caseCard.classList.contains("case-meet"), "the case meeting is not marked");
    assert.equal(caseCard.querySelector("[data-case-meeting-chip]")?.textContent, "Case meeting · ATT-2026-1");
    const cons = ui.container.querySelector('[data-appt-card="a-cons"]');
    assert.ok(!cons.classList.contains("case-meet"));
    assert.equal(cons.querySelector("[data-case-meeting-chip]"), null);
    await ui.unmount();
});
