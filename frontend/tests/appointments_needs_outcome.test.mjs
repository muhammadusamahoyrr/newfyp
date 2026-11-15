/* The lawyer's "Needs outcome" queue -- since 2026-10-20 its own TAB on the
 * Appointments list (it was a strip above the tabs), listed the moment a
 * meeting ends (`immediate`), each row the ordinary appointment card with the
 * one four-option "Record outcome" dialog.
 *
 * A CONFIRMED appointment goes nowhere on its own: only the lawyer can move it
 * to Completed or No Show, and if they never do it stays `confirmed` for ever.
 * That withholds something real — a completed consultation is what gates the
 * client's right to review the lawyer — so the absence of an action quietly
 * removes a right from somebody who is not in the room.
 *
 * TWO THINGS THIS COMPONENT MUST NOT DO, and both are tested here rather than
 * reasoned about:
 *
 *   * It must not filter the page above. The appointment list fetches fifty
 *     rows and never asks for a second page, so a local filter would show a
 *     backlog that stops exactly where that page ends — and the rows worth
 *     surfacing are the ones that fell off it. This reads its own endpoint.
 *
 *   * It must not turn a failed read into an empty queue. `apiFetch` RESOLVES
 *     on failure with `{data: null, error}` rather than throwing, so an
 *     unchecked `data?.items || []` renders a confident "nothing to do" out of
 *     a network error — telling a lawyer their record is clear when nobody
 *     managed to ask.
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
                    "KeyboardEvent", "MutationObserver", "getComputedStyle",
                    "localStorage", "sessionStorage", "requestAnimationFrame",
                    "cancelAnimationFrame"]) {
    define(name, dom.window[name]);
}
define("IS_REACT_ACT_ENVIRONMENT", true);

if (!dom.window.matchMedia) {
    dom.window.matchMedia = (query) => ({
        matches: false, media: query, onchange: null,
        addEventListener() {}, removeEventListener() {},
        addListener() {}, removeListener() {},
        dispatchEvent() { return false; },
    });
}

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

/** A queue row as the endpoint returns one. */
function pending(over = {}) {
    const ended = new Date(Date.now() - 5 * 36e5);
    return {
        id: "apt-1",
        client_name: "Ayesha Bibi",
        scheduled_at: new Date(ended.getTime() - 36e5).toISOString(),
        end_at: ended.toISOString(),
        duration_minutes: 60,
        status: "confirmed",
        mode: "video",
        schedule_version: 0,
        ...over,
    };
}

function page(items, next_cursor = null) {
    return {
        data: {
            items,
            next_cursor,
            cutoff: new Date(Date.now() - 2 * 36e5).toISOString(),
        },
        error: null,
        status: 200,
    };
}

async function mount({ tab = true } = {}) {
    const { AppointmentsPage } =
        await import("../src/components/lawyer/AppointmentsPage.jsx");
    const { NotifCtx } = await import("../src/components/lawyer/theme.js");

    const container = dom.window.document.createElement("div");
    dom.window.document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => {
        root.render(h(NotifCtx.Provider, { value: { addNotif: () => {} } },
                      h(AppointmentsPage)));
    });
    await act(async () => { await new Promise(r => realSetTimeout(r, 40)); });
    if (tab) {
        const t = [...container.querySelectorAll('[role="tab"]')].find(b => /^Needs outcome/.test(b.textContent.trim()));
        assert.ok(t, "no Needs outcome tab");
        await act(async () => { t.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true, cancelable: true })); });
        await act(async () => { await new Promise(r => realSetTimeout(r, 40)); });
    }

    const buttons = () => [...container.querySelectorAll("button")];
    const byText = (label) => buttons().find(b => b.textContent.trim() === label);

    return {
        container,
        text: () => container.textContent,
        buttons,
        byText,
        // ONE "Record outcome" on the row's card opens the four-option dialog;
        // this records one of its choices.
        record: async (choice) => {
            const press = async (el) => {
                assert.ok(el, "control missing");
                await act(async () => { el.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true, cancelable: true })); });
                await act(async () => { await new Promise(r => realSetTimeout(r, 30)); });
            };
            await press([...container.querySelectorAll("button")].find(b => b.textContent.trim() === "Record outcome"));
            await press([...container.querySelectorAll("[role=\"radio\"]")].find(b => b.textContent.trim() === choice));
            await press(container.querySelector("[data-close-confirm]"));
        },
        click: async (label) => {
            const btn = byText(label);
            assert.ok(btn, `no control labelled ${label}`);
            await act(async () => {
                btn.dispatchEvent(new dom.window.MouseEvent(
                    "click", { bubbles: true, cancelable: true }));
            });
            await act(async () => { await new Promise(r => realSetTimeout(r, 30)); });
        },
        settle: async (ms = 40) => {
            await act(async () => { await new Promise(r => realSetTimeout(r, ms)); });
        },
        unmount: async () => { await act(async () => root.unmount()); },
    };
}

test.beforeEach(() => {
    try { dom.window.sessionStorage.clear(); } catch { /* none */ }
    api.__reset();
    api.__respond("bootstrapAuth", true);
    api.__respond("getMe", { data: { _id: "l1", role: "lawyer" } });
    api.__respond("listAppointments", { data: { items: [] } });
    api.__respond("listCases", { data: { items: [] } });
    api.__respond("getNotifications", { data: { items: [] } });
    api.__respond("getAppointment", { data: null, error: { message: "not stubbed" }, status: 404 });
    // The page now also loads the lawyer's working hours. Stubbed so these
    // tests exercise the outcome queue rather than an unrelated error panel.
    api.__respond("getMyWorkingHours", {
        data: {
            lawyer_id: "l1", configured: false, enforced: false,
            timezone: "Asia/Karachi", working_hours: [], exceptions: [],
            updated_at: null,
        },
        error: null, status: 200,
    });
});

test.after(() => {
    for (const id of liveTimers) { realClearInterval(id); realClearTimeout(id); }
    liveTimers.clear();
    dom.window.close();
});

/* ── the tab, and the three states kept apart ──────────────────────────────── */

test("the queue is its own tab: nothing is read for it, and no strip shows, until the tab is opened", async () => {
    api.__respond("listPendingOutcomes", page([pending()]));
    const ui = await mount({ tab: false });
    assert.equal(api.__calls("listPendingOutcomes").length, 0, "the queue was read outside its tab");
    assert.doesNotMatch(ui.text(), /Ayesha Bibi/);
    await ui.unmount();
});

test("it is listed the moment a meeting ends: the queue is read with `immediate`", async () => {
    api.__respond("listPendingOutcomes", page([pending()]));
    const ui = await mount();
    const calls = api.__calls("listPendingOutcomes");
    assert.equal(calls.length, 1);
    assert.equal(calls[0].args[0].immediate, true, "the two-hour reminder grace reached the list");
    assert.match(ui.text(), /Ayesha Bibi/);
    await ui.unmount();
});

test("the tab count is the shared server count; an unknown count is not shown as zero", async () => {
    api.__respond("listPendingOutcomes", page([]));
    api.__respond("getLawyerActions", { data: { outcomes_to_record: 3, appointment_requests: 0, hire_requests: 0, upcoming: 0, to_do: 3, next: {} }, error: null });
    let ui = await mount({ tab: false });
    const label = () => [...ui.container.querySelectorAll('[role="tab"]')].find(b => /^Needs outcome/.test(b.textContent.trim())).textContent;
    assert.match(label(), /Needs outcome\s*\(3\)/);
    await ui.unmount();
    api.__respond("getLawyerActions", { data: null, error: { message: "down" }, status: 0 });
    ui = await mount({ tab: false });
    assert.doesNotMatch(label(), /\(0\)/, "a failed count read was shown as zero");
    await ui.unmount();
});

test("a genuine empty queue says there is nothing waiting", async () => {
    api.__respond("listPendingOutcomes", page([]));
    const ui = await mount();
    assert.ok(ui.container.querySelector("[data-outcomes-empty]"), "an empty queue did not say so");
    assert.doesNotMatch(ui.text(), /Could not load outstanding outcomes/);
    await ui.unmount();
});

test("a failed read is NOT reported as an empty queue", async () => {
    // `apiFetch` resolves with `{data: null, error}` on failure, so an
    // unchecked `data?.items || []` would render "nothing to do" out of a
    // network error.
    api.__respond("listPendingOutcomes",
                  { data: null, error: { message: "network down" }, status: 0 });
    const ui = await mount();
    assert.match(ui.text(), /Could not load outstanding outcomes/);
    assert.equal(ui.container.querySelector("[data-outcomes-empty]"), null, "a failed read looked like an empty queue");
    await ui.unmount();
});

test("a failed read says it does not know, rather than guessing", async () => {
    api.__respond("listPendingOutcomes",
                  { data: null, error: { message: "boom" }, status: 500 });
    const ui = await mount();
    assert.match(ui.text(), /we do not know/i);
    assert.ok(ui.byText("Try again"), "no way to retry a failed read");
    await ui.unmount();
});

test("a failed read can be retried and then succeeds", async () => {
    let call = 0;
    api.__respond("listPendingOutcomes", () => {
        call += 1;
        return call === 1
            ? { data: null, error: { message: "down" }, status: 0 }
            : page([pending()]);
    });
    const ui = await mount();
    assert.match(ui.text(), /Could not load outstanding outcomes/);
    await ui.click("Try again");
    assert.match(ui.text(), /Ayesha Bibi/);
    await ui.unmount();
});

/* ── recording an outcome ─────────────────────────────────────────────────── */

test("the row's only outcome control is Record outcome -- no standalone No Show", async () => {
    api.__respond("listPendingOutcomes", page([pending()]));
    const ui = await mount();
    assert.ok(ui.byText("Record outcome"));
    const list = ui.container.querySelector(".lc-list");
    assert.equal([...list.querySelectorAll("button")].filter(b => /^No[- ]?Show$/i.test(b.textContent.trim())).length, 0, "a standalone No Show button is back");
    await ui.unmount();
});

test("It took place goes through the guarded endpoint", async () => {
    api.__respond("listPendingOutcomes", page([pending()]));
    api.__respond("completeAppointment", { data: { status: "completed" } });
    const ui = await mount();
    await ui.record("It took place");
    const calls = api.__calls("completeAppointment");
    assert.equal(calls.length, 1, "the existing complete endpoint was not used");
    assert.equal(calls[0].args[0], "apt-1");
    await ui.unmount();
});

test("a no-show is recorded from the dialog, through the guarded endpoint", async () => {
    api.__respond("listPendingOutcomes", page([pending()]));
    api.__respond("markNoShow", { data: { status: "no_show" } });
    const ui = await mount();
    await ui.record("The client didn't attend");
    const calls = api.__calls("markNoShow");
    assert.equal(calls.length, 1);
    assert.equal(calls[0].args[0], "apt-1");
    await ui.unmount();
});

test("after an outcome the queue, the list and the counts are all re-read", async () => {
    let call = 0;
    api.__respond("listPendingOutcomes", () => {
        call += 1;
        return call === 1 ? page([pending()]) : page([]);
    });
    api.__respond("completeAppointment", { data: { status: "completed" } });
    const ui = await mount();
    const counts = api.__calls("getLawyerActions").length;
    await ui.record("It took place");
    await ui.settle(60);
    assert.ok(api.__calls("listPendingOutcomes").length >= 2, "the queue was not re-read from the server");
    assert.ok(api.__calls("getLawyerActions").length > counts, "the counts were not re-read");
    assert.ok(ui.container.querySelector("[data-outcomes-empty]"), "the recorded row is still shown");
    await ui.unmount();
});

test("an outcome already recorded in another tab: the dialog closes, it says so, the row is re-read", async () => {
    api.__respond("listPendingOutcomes", page([pending()]));
    api.__respond("completeAppointment",
                  { data: null, error: { message: "already completed" }, status: 409 });
    const ui = await mount();
    const reads = api.__calls("listPendingOutcomes").length;
    await ui.record("It took place");
    await ui.settle(60);
    assert.equal(dom.window.document.querySelector('[aria-label="Complete the consultation"]'), null, "the stale dialog stayed open");
    assert.match(dom.window.document.body.textContent, /already completed/);
    assert.ok(api.__calls("listPendingOutcomes").length > reads, "the stale row was not re-read");
    await ui.unmount();
});

test("a refused outcome for another reason keeps the dialog and says why", async () => {
    api.__respond("listPendingOutcomes", page([pending()]));
    api.__respond("completeAppointment", { data: null, error: { message: "server busy" }, status: 503 });
    const ui = await mount();
    await ui.record("It took place");
    assert.ok(dom.window.document.querySelector("[data-outcome-refused]"), "the reason was not shown in the dialog");
    assert.match(ui.text(), /Ayesha Bibi/, "a refused outcome removed the row anyway");
    await ui.unmount();
});

test("nothing is auto-completed by merely opening the queue", async () => {
    api.__respond("listPendingOutcomes", page([pending()]));
    const ui = await mount();
    assert.equal(api.__calls("completeAppointment").length, 0);
    assert.equal(api.__calls("markNoShow").length, 0);
    await ui.unmount();
});

/* ── the Dashboard's deep link ────────────────────────────────────────────── */

test("Record outcome from the Dashboard opens THAT meeting's dialog, and again after a refresh", async () => {
    dom.window.sessionStorage.setItem("attorney:lawyer-record-outcome", "apt-7");
    api.__respond("listPendingOutcomes", page([pending({ id: "apt-7", client_name: "Bilal Khan" })]));
    api.__respond("getAppointment", { data: pending({ id: "apt-7", client_name: "Bilal Khan" }), error: null, status: 200 });
    let ui = await mount({ tab: false });
    await ui.settle(60);
    const dlg = () => dom.window.document.querySelector('[aria-label="Complete the consultation"]');
    assert.ok(dlg(), "the outcome dialog did not open");
    assert.match(dlg().textContent, /Bilal Khan/);
    assert.equal(api.__calls("getAppointment")[0].args[0], "apt-7");
    const selected = [...ui.container.querySelectorAll('[role="tab"]')].find(b => b.getAttribute("aria-selected") === "true");
    assert.match(selected.textContent, /^Needs outcome/);
    await ui.unmount();
    // A refresh with the dialog still open opens it again.
    ui = await mount({ tab: false });
    await ui.settle(60);
    assert.ok(dlg(), "a refresh lost the deep link");
    await ui.unmount();
});

test("a deep link to a meeting no longer needing an outcome falls back to the tab", async () => {
    dom.window.sessionStorage.setItem("attorney:lawyer-record-outcome", "apt-gone");
    api.__respond("listPendingOutcomes", page([]));
    api.__respond("getAppointment", { data: pending({ id: "apt-gone", status: "completed" }), error: null, status: 200 });
    const ui = await mount({ tab: false });
    await ui.settle(60);
    assert.equal(dom.window.document.querySelector('[aria-label="Complete the consultation"]'), null);
    assert.match(dom.window.document.body.textContent, /no longer needs an outcome/);
    assert.equal(dom.window.sessionStorage.getItem("attorney:lawyer-record-outcome"), null, "the stale link was kept");
    assert.ok(ui.container.querySelector("[data-outcomes-empty]"), "it did not fall back to the Needs outcome tab");
    await ui.unmount();
});

/* ── paging ───────────────────────────────────────────────────────────────── */

test("more rows are reachable than one page holds", async () => {
    const cursor = {
        after_end_at: new Date(Date.now() - 4 * 36e5).toISOString(),
        after_id: "apt-25",
        cutoff: new Date(Date.now() - 2 * 36e5).toISOString(),
    };
    let call = 0;
    api.__respond("listPendingOutcomes", () => {
        call += 1;
        return call === 1
            ? page([pending({ id: "apt-1", client_name: "First Client" })], cursor)
            : page([pending({ id: "apt-2", client_name: "Second Client" })]);
    });
    const ui = await mount();
    assert.match(ui.text(), /First Client/);
    assert.ok(!ui.text().includes("Second Client"));
    await ui.click("Load more");
    assert.match(ui.text(), /Second Client/);
    assert.match(ui.text(), /First Client/, "the first page was discarded");
    await ui.unmount();
});

test("the whole cursor is sent back, not half of it", async () => {
    const cursor = {
        after_end_at: new Date(Date.now() - 4 * 36e5).toISOString(),
        after_id: "apt-25",
        cutoff: new Date(Date.now() - 2 * 36e5).toISOString(),
    };
    let call = 0;
    api.__respond("listPendingOutcomes", () => {
        call += 1;
        return call === 1 ? page([pending()], cursor) : page([]);
    });
    const ui = await mount();
    await ui.click("Load more");
    const second = api.__calls("listPendingOutcomes")[1].args[0];
    assert.deepEqual(second.cursor, cursor);
    assert.equal(second.immediate, true);
    await ui.unmount();
});

test("no Load more control when the server says there is no next page", async () => {
    api.__respond("listPendingOutcomes", page([pending()]));
    const ui = await mount();
    assert.equal(ui.byText("Load more"), undefined);
    await ui.unmount();
});

test("a failed Load more keeps the rows already shown", async () => {
    const cursor = {
        after_end_at: new Date(Date.now() - 4 * 36e5).toISOString(),
        after_id: "apt-25",
        cutoff: new Date(Date.now() - 2 * 36e5).toISOString(),
    };
    let call = 0;
    api.__respond("listPendingOutcomes", () => {
        call += 1;
        return call === 1
            ? page([pending({ client_name: "Kept Client" })], cursor)
            : { data: null, error: { message: "down" }, status: 0 };
    });
    const ui = await mount();
    await ui.click("Load more");
    assert.match(ui.text(), /Kept Client/, "a failed second page discarded the first");
    assert.match(ui.text(), /down|Could not load more outcomes/i, "the failed second page was silent");
    await ui.unmount();
});

test("a 400 refusal is shown in the dialog, not treated as a stale row", async () => {
    // QA 2026-10-20: only 404 (gone) and 409 (changed meanwhile) are stale.
    api.__respond("listPendingOutcomes", page([pending()]));
    api.__respond("completeAppointment", { data: null, error: { message: "Not yet ended" }, status: 400 });
    const ui = await mount();
    await ui.record("It took place");
    assert.ok(dom.window.document.querySelector('[aria-label="Complete the consultation"]'), "the dialog closed on a 400");
    assert.match(dom.window.document.querySelector("[data-outcome-refused]").textContent, /Not yet ended/);
    assert.equal(ui.container.querySelector("[data-list-notice]"), null, "a 400 was reported as 'refreshed'");
    await ui.unmount();
});

test("a refresh keeps the rows on screen instead of a Loading placeholder", async () => {
    let release;
    let call = 0;
    api.__respond("listPendingOutcomes", () => {
        call += 1;
        return call === 1 ? page([pending()]) : new Promise(r => { release = () => r(page([pending()])); });
    });
    api.__respond("completeAppointment", { data: null, error: { message: "gone" }, status: 409 });
    const ui = await mount();
    await ui.record("It took place");          // stale -> refresh in flight
    assert.match(ui.text(), /Ayesha Bibi/, "the rows were swapped for a placeholder during a refresh");
    assert.doesNotMatch(ui.text(), /Loading meetings that need an outcome/);
    release?.();
    await ui.settle(40);
    await ui.unmount();
});
