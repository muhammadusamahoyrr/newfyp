/* The client Overview names a meeting the lawyer proposed (2026-10-12): under
 * "Needs you", with the lawyer, case, agenda and times, and "Choose a time".
 * A failed read is not "nothing needs you"; accepted or declined ones go. */
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/dashboard" });
function define(name, value) { Object.defineProperty(globalThis, name, { value, writable: true, configurable: true }); }
for (const name of ["window", "document", "navigator", "HTMLElement", "Element", "Node", "Event", "CustomEvent",
                    "MouseEvent", "KeyboardEvent", "MutationObserver", "getComputedStyle", "localStorage",
                    "requestAnimationFrame", "cancelAnimationFrame"]) define(name, dom.window[name]);
define("IS_REACT_ACT_ENVIRONMENT", true);
if (!dom.window.matchMedia) {
    dom.window.matchMedia = (q) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
}

const React = (await import("react")).default;
const { act } = await import("react");
const { createRoot } = await import("react-dom/client");
const api = await import("./support/api-stub.mjs");
const h = React.createElement;
const realSetTimeout = setTimeout;
const nav = () => (globalThis.__nav ||= { pushed: [], replaced: [], params: new Map() });
const settle = (ms = 60) => act(async () => { await new Promise(r => realSetTimeout(r, ms)); });

const proposal = (over = {}) => ({ id: "P1", status: "open", lawyer_name: "Bilal Ahmed Sheikh", case_title: "Rent dispute",
    agenda: "Go through the receipts", options: ["2026-11-02T06:00:00Z", "2026-11-03T11:30:00Z"], option_passed: [false, false], ...over });

async function mount() {
    const ModOverview = (await import("../src/components/client/ModOverview.jsx")).default;
    const { CaseProvider } = await import("../src/components/shared/CaseContext.jsx");
    const { AuthProvider } = await import("../src/context/AuthContext.jsx");
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => { root.render(h(AuthProvider, null, h(CaseProvider, null, h(ModOverview)))); });
    await settle(80);
    return {
        container,
        text: () => container.textContent,
        need: () => container.querySelector("[data-need]"),
        button: (label) => [...container.querySelectorAll("button")].find(b => b.textContent.trim().startsWith(label)),
        unmount: async () => { await act(async () => root.unmount()); container.remove(); },
    };
}

const click = (el) => act(async () => { el.dispatchEvent(new MouseEvent("click", { bubbles: true })); });

test.beforeEach(() => {
    api.__reset();
    nav().pushed = [];
    api.__respond("bootstrapAuth", true);
    api.__respond("getMe", { data: { _id: "u1", role: "client", full_name: "UI Check" } });
    api.__respond("listAppointments", { data: { items: [], page: 1, pages: 1, total: 0 } });
    api.__respond("listCases", { data: { items: [] } });
    api.__respond("getNotifications", { data: [] });
    api.__respond("listEngagements", { data: [] });
});
test.after(() => dom.window.close());

test("an open proposal is named under Needs you, and Choose a time opens the proposals", async () => {
    api.__respond("listMeetingProposals", { data: [proposal()] });
    const ui = await mount();
    assert.equal(ui.need().getAttribute("data-need"), "meeting");
    assert.match(ui.need().textContent, /Bilal Ahmed Sheikh proposed a meeting about “Rent dispute”/);
    assert.match(ui.need().querySelector("[data-need-sub]").textContent, /Go through the receipts · .+ \/ .+ PKT/);
    await click(ui.button("Choose a time"));
    assert.deepEqual(nav().pushed, ["/appointments?section=proposals"]);
    await ui.unmount();
});

test("several proposals are counted", async () => {
    api.__respond("listMeetingProposals", { data: [proposal(), proposal({ id: "P2", case_title: "Loan" })] });
    const ui = await mount();
    assert.match(ui.need().textContent, /Needs you · 2/);
    await ui.unmount();
});

test("only OPEN proposals count", async () => {
    api.__respond("listMeetingProposals", { data: [proposal({ status: "accepted" }), proposal({ id: "P2", status: "declined" })] });
    const ui = await mount();
    assert.notEqual(ui.need().getAttribute("data-need"), "meeting");
    assert.match(ui.text(), /all caught up/);
    await ui.unmount();
});

test("a failed read is not 'all caught up', and Retry asks again", async () => {
    let n = 0;
    api.__respond("listMeetingProposals", () => (++n === 1 ? { data: null, error: { message: "down" } } : { data: [proposal()], error: null }));
    const ui = await mount();
    assert.equal(ui.need().getAttribute("data-need"), "unknown");
    assert.doesNotMatch(ui.text(), /all caught up|Nothing needs you/);
    await click(ui.button("Retry"));
    await settle();
    assert.equal(ui.need().getAttribute("data-need"), "meeting");
    await ui.unmount();
});

test("an accepted or declined proposal leaves the Overview when told", async () => {
    let open = true;
    api.__respond("listMeetingProposals", () => ({ data: open ? [proposal()] : [], error: null }));
    const ui = await mount();
    assert.equal(ui.need().getAttribute("data-need"), "meeting");
    open = false;
    const { broadcastNotification } = await import("../src/lib/notificationTarget.js");
    await act(async () => { broadcastNotification({ id: "n1", type: "appointment_proposal_accepted", payload: {} }); });
    await settle();
    assert.notEqual(ui.need().getAttribute("data-need"), "meeting");
    await ui.unmount();
});

test("long lines truncate rather than push the layout on a narrow screen", async () => {
    api.__respond("listMeetingProposals", { data: [proposal({ agenda: "A very long agenda ".repeat(12) })] });
    const ui = await mount();
    assert.ok(ui.need().querySelector("[data-need-sub]").classList.contains("ov-clip"));
    await ui.unmount();
});

test("hero colours (option 1, 2026-11-25): the appointment box is the teal one, Book a meeting the cyan button", async () => {
    const ui = await mount();
    const appt = ui.container.querySelector("[data-ov-appt]");
    assert.ok(appt, "no appointment box");
    assert.ok(appt.classList.contains("ov-appt"));
    const book = [...appt.querySelectorAll("button")].find(b => /Book a meeting/.test(b.textContent));
    assert.ok(book && book.classList.contains("cy"), "Book a meeting is not the cyan button");
    const css = [...ui.container.querySelectorAll("style")].map(s => s.textContent).join("");
    assert.match(css, /\.ov-need:not\(\.calm\)\{border-color:color-mix\(in srgb,var\(--gold\)/, "the needs-you box is not gold");
    await ui.unmount();
});
