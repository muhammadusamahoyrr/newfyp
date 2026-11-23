/* Hiring a lawyer starts from a COMPLETED consultation.
 *
 * AGREEMENTS_PRODUCT_PLAN.md §17 R5-1, R5-11 step 7. The server refuses a hire
 * request that does not name a completed consultation with that lawyer, and
 * only the lawyer can mark one completed. So the client needs the offer at the
 * one place it can succeed -- their finished consultation -- and it must not
 * appear anywhere it cannot.
 *
 * Two halves, both here because they are one journey:
 *   1. the appointment card offers it, and only when completed;
 *   2. the lawyers page opens the hire form on that consultation.
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
                    "localStorage", "requestAnimationFrame",
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

function nav() {
    return (globalThis.__nav ||= { pushed: [], replaced: [], params: new Map() });
}

async function settle(ms = 40) {
    await act(async () => { await new Promise(r => realSetTimeout(r, ms)); });
}

/* ── half 1: the appointment card ────────────────────────────────────────── */

function appointment(over = {}) {
    const when = new Date(Date.now() - 48 * 36e5);
    when.setUTCMinutes(0, 0, 0);
    return {
        id: "apt-1",
        scheduled_at: when.toISOString(),
        end_at: new Date(when.getTime() + 36e5).toISOString(),
        duration_minutes: 60,
        status: "completed",
        mode: "video",
        lawyer_id: "L1",
        lawyer_name: "Adv Ayesha Khan",
        client_name: "Test Client",
        notes: null,
        case_id: null,
        timezone: "Asia/Karachi",
        ...over,
    };
}

async function mountTracking(appts) {
    api.__respond("listAppointments", { data: { items: appts }, error: null, status: 200 });
    const ModTracking = (await import("../src/components/client/ModTracking.jsx")).default;
    const { CaseCtx } = await import("../src/components/shared/CaseContext.jsx");

    const container = dom.window.document.createElement("div");
    dom.window.document.body.appendChild(container);
    const root = createRoot(container);
    const ctx = {
        notifications: [],
        markNotificationDone: () => {},
        markAllNotificationsDone: () => {},
        appointmentMilestones: [],
    };
    await act(async () => {
        root.render(h(CaseCtx.Provider, { value: ctx }, h(ModTracking, { isDark: true, standalone: "appointments" })));
    });
    await settle();

    // The /appointments page (2026-11-23: the Tracking tab that used to show
    // these cards was a duplicate, removed). A finished consultation sits
    // under Past; its hire opens a dialog on this page (2026-10-20), not a
    // link to the Lawyers page.
    const past = container.querySelector('[data-hub-tab="past"]');
    if (past) {
        await act(async () => { past.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true, cancelable: true })); });
        await settle();
    }

    return {
        container,
        hireEntry: () => container.querySelector("[data-row-hire], [data-next-hire]") || undefined,
        click: async (el) => {
            await act(async () => { el.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true, cancelable: true })); });
            await settle();
        },
        unmount: async () => { await act(async () => root.unmount()); },
    };
}

test.beforeEach(() => {
    api.__reset();
    nav().params = new Map();
    api.__respond("listCases", { data: { items: [] } });
    api.__respond("listPayments", { data: [] });
    api.__respond("listAppointmentDisputes", { data: [] });
    api.__respond("listEngagements", { data: [] });
});

test.after(() => {
    for (const id of liveTimers) { realClearInterval(id); realClearTimeout(id); }
    liveTimers.clear();
    dom.window.close();
});

test("a completed consultation offers the hire, carrying the lawyer and itself",
     async () => {
    const ui = await mountTracking([appointment()]);
    const entry = ui.hireEntry();

    assert.ok(entry, "no hire entry on a completed consultation");
    await ui.click(entry);
    const dialog = dom.window.document.querySelector("[data-hire-dialog]");
    assert.ok(dialog, "the hire did not open");
    assert.match(dialog.textContent, /Ayesha/, "the hire is not for this consultation's lawyer");
    await ui.unmount();
});

test("a consultation that has not completed offers nothing", async () => {
    for (const status of ["pending", "confirmed", "cancelled", "no_show", "expired"]) {
        const ui = await mountTracking([appointment({ status })]);
        assert.equal(ui.hireEntry(), undefined,
                     `the hire entry appeared on a ${status} consultation`);
        await ui.unmount();
    }
});

/* ── half 2: the lawyers page opens on that consultation ─────────────────── */

function consult(id, over = {}) {
    return { id, lawyer_id: "L1", client_id: "u1", case_id: null,
             status: "completed", scheduled_at: "2026-09-01T10:00:00Z", ...over };
}

function hireableCase(id) {
    return { _id: id, title: `Case ${id}`, case_number: `ATT-${id}`,
             status: "open", lawyer_id: null };
}

async function mountLawyersFromLink(consults, params, cases = [hireableCase("C1"), hireableCase("C2")], directory = []) {
    for (const [k, v] of Object.entries(params)) nav().params.set(k, v);
    api.__respond("bootstrapAuth", true);
    api.__respond("getMe", { data: { _id: "u1", role: "client" } });
    api.__respond("searchLawyers", { data: { items: directory } });
    api.__respond("listCases", { data: { items: cases } });
    api.__respond("listHireConsultations", { data: consults });
    api.__respond("requestEngagement", { data: { id: "E1" } });

    const { default: ModLawyers } =
        await import("../src/components/client/ModLawyers.jsx");
    const { CaseProvider } = await import("../src/components/client/CaseContext.jsx");
    const { AuthProvider } = await import("../src/context/AuthContext.jsx");
    const { ToastContainer } = await import("../src/components/shared/Toast.jsx");
    const { DARK } = await import("../src/components/admin/themes.js");
    const { ThemeCtx, HeaderActionsCtx } =
        await import("../src/components/client/theme.js");

    const container = dom.window.document.createElement("div");
    dom.window.document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => {
        root.render(h(
            AuthProvider, null,
            h(ThemeCtx.Provider, { value: DARK },
              h(HeaderActionsCtx.Provider, { value: { setHeaderActions: () => {} } },
                h(ToastContainer, { theme: DARK },
                  h(CaseProvider, null, h(ModLawyers)))))));
    });
    await settle(60);

    const field = (label) => {
        const el = [...dom.window.document.querySelectorAll("label")]
            .find(l => l.textContent.trim() === label);
        return el ? el.parentElement.querySelector("select") : null;
    };
    const click = async (label) => {
        const btn = [...dom.window.document.querySelectorAll("button")]
            .find(b => b.textContent.trim().startsWith(label));
        assert.ok(btn, `no "${label}" button`);
        await act(async () => {
            btn.dispatchEvent(new dom.window.MouseEvent(
                "click", { bubbles: true, cancelable: true }));
        });
        await settle(30);
    };
    return {
        text: () => dom.window.document.body.textContent,
        field, click,
        unmount: async () => { await act(async () => root.unmount()); },
    };
}

test("arriving from a consultation opens the hire form on that consultation",
     async () => {
    const ui = await mountLawyersFromLink(
        [consult("A-old", { scheduled_at: "2026-08-01T10:00:00Z" }),
         consult("A-new", { scheduled_at: "2026-09-10T10:00:00Z" })],
        { hire: "L1", hire_name: "Adv Ayesha Khan", appointment: "A-old" });

    assert.match(ui.text(), /Request to Hire/);
    // Several exist, so nothing would be chosen -- except that the client
    // arrived from one, and THAT one is selected.
    assert.equal(ui.field("Consultation *").value, "A-old");

    await ui.click("Send Hire Request");
    const calls = api.__calls("requestEngagement");
    assert.equal(calls.length, 1);
    assert.equal(calls[0].args[0].appointment_id, "A-old");
    assert.equal(calls[0].args[0].lawyer_id, "L1");
    await ui.unmount();
});

test("the lawyer need not be on the current directory page", async () => {
    // `searchLawyers` returns nobody, so the form can only have opened from
    // the link itself.
    const ui = await mountLawyersFromLink(
        [consult("A1")], { hire: "L1", hire_name: "Adv Ayesha Khan", appointment: "A1" });

    assert.match(ui.text(), /Adv Ayesha Khan/);
    await ui.click("Send Hire Request");
    assert.equal(api.__calls("requestEngagement")[0].args[0].appointment_id, "A1");
    await ui.unmount();
});

test("a consultation the server no longer lists is not sent", async () => {
    // The link names A-gone; the server lists two others. The client chooses.
    const ui = await mountLawyersFromLink(
        [consult("A1"), consult("A2")],
        { hire: "L1", hire_name: "Adv Ayesha Khan", appointment: "A-gone" });

    assert.equal(ui.field("Consultation *").value, "",
                 "a consultation the server did not list was pre-selected");
    await ui.click("Send Hire Request");
    assert.equal(api.__calls("requestEngagement").length, 0);
    await ui.unmount();
});

test("no hire link, no hire form", async () => {
    const ui = await mountLawyersFromLink([consult("A1")], {});
    assert.ok(!/Send Hire Request/.test(ui.text()));
    assert.equal(api.__calls("listHireConsultations").length, 0);
    await ui.unmount();
});

/* ── which cases can be sent: open negotiations, read fresh ─────────────── */
//
// The picker counted only `requested` engagements as pending, so a case with
// terms already proposed was offered again (the server refuses it: both are
// open). And the cases were read once per visit, so after an engagement
// changed the picker still showed the old answer.

const caseOptions = (ui) => [...(ui.field("Case *")?.querySelectorAll("option") || [])]
    .map(o => o.value).filter(Boolean);

test("a case with terms proposed is not offered again", async () => {
    api.__respond("listEngagements", { data: [{ id: "E9", case_id: "C1", status: "terms_proposed", lawyer_id: "L2" }] });
    const ui = await mountLawyersFromLink([consult("A1")], { hire: "L1", hire_name: "Adv Ayesha Khan", appointment: "A1" });
    assert.match(ui.text(), /Request to Hire/);
    assert.deepEqual(caseOptions(ui), ["C2"]);
    await ui.unmount();
});

test("opening the hire form re-reads engagements, and offers a new matter when every case is now taken", async () => {
    let reads = 0;
    api.__respond("listEngagements", () => {
        reads += 1;
        // At page load nothing is pending; by the time the form opens, both
        // cases are under negotiation with someone.
        return { data: reads === 1 ? [] : [
            { id: "E1", case_id: "C1", status: "requested", lawyer_id: "L2" },
            { id: "E2", case_id: "C2", status: "terms_proposed", lawyer_id: "L3" },
        ] };
    });
    const ui = await mountLawyersFromLink([consult("A1")], { hire: "L1", hire_name: "Adv Ayesha Khan", appointment: "A1" });
    assert.ok(reads >= 2, "engagements were not re-read when the form opened");
    // Hiring needs a matter, not the intake (2026-10-12): the taken cases are
    // not offered, and the client can describe a new one instead.
    assert.match(ui.text(), /Send Hire Request/);
    const offered = [...dom.window.document.querySelectorAll("option")].map(o => o.value);
    assert.ok(!offered.includes("C1") && !offered.includes("C2"), `a case already under negotiation was offered: ${offered}`);
    assert.ok(dom.window.document.querySelector("[data-new-matter]"), "no way to describe a new matter");
    await ui.unmount();
});

/* ── no case to send: a new matter, or a confirmed draft (2026-10-12) ─────── */

async function typeInto(el, value) {
    const proto = el.tagName === "TEXTAREA" ? dom.window.HTMLTextAreaElement
        : el.tagName === "SELECT" ? dom.window.HTMLSelectElement : dom.window.HTMLInputElement;
    await act(async () => {
        Object.getOwnPropertyDescriptor(proto.prototype, "value").set.call(el, value);
        el.dispatchEvent(new dom.window.Event(el.tagName === "SELECT" ? "change" : "input", { bubbles: true }));
    });
}

test("with no case to send, a new matter is created and then named by the request", async () => {
    api.__respond("createCase", { data: { _id: "NEW1", status: "open" } });
    const ui = await mountLawyersFromLink([consult("A1")],
        { hire: "L1", hire_name: "Adv Ayesha Khan", appointment: "A1" }, []);
    const form = dom.window.document.querySelector("[data-new-matter]");
    assert.ok(form, "the new-matter fields did not open");

    await ui.click("Send Hire Request");
    assert.equal(api.__calls("createCase").length, 0, "an empty matter was created");

    await typeInto(form.querySelector('[aria-label="Matter title"]'), "Security deposit not returned");
    await typeInto(form.querySelector('[aria-label="Area of law"]'), "civil");
    await typeInto(form.querySelector('[aria-label="Province"]'), "punjab");
    await typeInto(form.querySelector('[aria-label="What the lawyer should handle"]'), "My landlord kept the deposit after I moved out.");
    await ui.click("Send Hire Request");

    assert.deepEqual(api.__calls("createCase")[0].args[0], {
        title: "Security deposit not returned", case_type: "civil", province: "punjab",
        description: "My landlord kept the deposit after I moved out.",
    });
    const sent = api.__calls("requestEngagement");
    assert.equal(sent.length, 1);
    assert.equal(sent[0].args[0].case_id, "NEW1");
    assert.equal(sent[0].args[0].appointment_id, "A1");
    await ui.unmount();
});

test("an intake draft is offered, and confirmed before it is sent", async () => {
    api.__respond("confirmCase", { data: { _id: "D1", status: "open" } });
    const ui = await mountLawyersFromLink([consult("A1")],
        { hire: "L1", hire_name: "Adv Ayesha Khan", appointment: "A1" },
        [{ _id: "D1", title: "Tenancy dispute", status: "draft", lawyer_id: null }]);
    assert.equal(ui.field("Case *").value, "draft:D1");
    assert.match(ui.text(), /from your intake/);

    await ui.click("Send Hire Request");
    assert.deepEqual(api.__calls("confirmCase").map(c => c.args[0]), ["D1"]);
    assert.equal(api.__calls("requestEngagement")[0].args[0].case_id, "D1");
    await ui.unmount();
});

test("a consultation booked for a case offers no new matter", async () => {
    const ui = await mountLawyersFromLink([consult("A1", { case_id: "C2" })],
        { hire: "L1", hire_name: "Adv Ayesha Khan", appointment: "A1" });
    assert.deepEqual(caseOptions(ui), ["C2"]);
    assert.ok(!/Describe a new matter/.test(ui.text()));
    await ui.unmount();
});

/* ── a link to one lawyer: book again, or review (2026-10-12) ────────────── */

const listed = { _id: "L1", full_name: "Adv Ayesha Khan", province: "punjab",
                 lawyer_profile: { availability: true, kyc_verified: true, specializations: ["civil"] } };

test("a 'book again' link opens that lawyer's booking, found by name", async () => {
    api.__respond("getBookableSlots", { data: { configured: false, enforced: false, days: [] }, error: null });
    const ui = await mountLawyersFromLink([], { lawyer: "L1", lawyer_name: "Adv Ayesha Khan", action: "book" }, [], [listed]);
    await settle(60);
    assert.ok(api.__calls("searchLawyers").some(c => c.args[0]?.q === "Adv Ayesha Khan"), "the lawyer was not looked up by name");
    const dialog = dom.window.document.querySelector("[data-booking-dialog]");
    assert.ok(dialog, "the booking did not open");
    assert.match(dialog.textContent, /Adv Ayesha Khan/);
    await ui.unmount();
});

test("a 'review' link opens that lawyer's review form", async () => {
    api.__respond("getReviewEligibility", { data: { can_review: true, already_reviewed: false, reason: null } });
    const ui = await mountLawyersFromLink([], { lawyer: "L1", lawyer_name: "Adv Ayesha Khan", action: "review" }, [], [listed]);
    await settle(60);
    assert.match(ui.text(), /Your Rating/);
    await ui.unmount();
});

test("a lawyer no longer listed is said so, and nothing opens", async () => {
    const ui = await mountLawyersFromLink([], { lawyer: "L9", lawyer_name: "Adv Gone", action: "book" }, [], [listed]);
    await settle(60);
    assert.match(ui.text(), /Adv Gone is not listed right now/);
    assert.equal(dom.window.document.querySelector("[data-booking-dialog]"), null);
    await ui.unmount();
});

test("after a hire request, Tracking shows where it stands, not 'Hire' again (2026-10-12)", async () => {
    api.__respond("listEngagements", { data: [{ id: "E1", appointment_id: "apt-1", status: "requested", lawyer_id: "L1" }] });
    const ui = await mountTracking([appointment()]);
    assert.equal(ui.container.querySelector("[data-row-hire]"), null, "the page still offers the hire");
    const box = ui.container.querySelector('[data-hire-state="requested"]');
    assert.ok(box, "no hire state on the card");
    assert.match(box.textContent, /Hire requested/);
    await ui.unmount();
});

test("an accepted hire's 'Open case' opens that case (2026-11-23)", async () => {
    api.__respond("listEngagements", { data: [{ id: "E7", appointment_id: "apt-1", case_id: "C9", status: "accepted", lawyer_id: "L1" }] });
    const ui = await mountTracking([appointment()]);
    const open = ui.container.querySelector('[data-hire-state="accepted"]');
    assert.ok(open, "no Open case on the card");
    assert.equal(open.getAttribute("href"), "/tracking?case=C9&tab=summary&engagement=E7");
    await ui.unmount();
});

/* ── who may review: asked before the form (2026-10-12) ────────────────────── */

const reviewState = () => dom.window.document.querySelector("[data-review-form]")?.getAttribute("data-review-state");
const openReviewOf = (elig) => {
    api.__respond("getReviewEligibility", elig);
    return mountLawyersFromLink([], { lawyer: "L1", lawyer_name: "Adv Ayesha Khan", action: "review" }, [], [listed]);
};

test("a client with no consultation is told when they can review, and gets no form", async () => {
    const ui = await openReviewOf({ data: { can_review: false, already_reviewed: false, reason: "no_completed_relationship" } });
    await settle(60);
    assert.equal(reviewState(), "not-eligible");
    assert.match(ui.text(), /You can review Adv after a completed consultation/);
    assert.ok(!/Your Rating|Write a Review/.test(ui.text()), "the form was offered anyway");
    await ui.unmount();
});

test("an already-reviewed lawyer says so instead of a second form", async () => {
    const ui = await openReviewOf({ data: { can_review: false, already_reviewed: true, reason: "already_reviewed" } });
    await settle(60);
    assert.equal(reviewState(), "done");
    assert.match(ui.text(), /Review submitted — thank you/);
    assert.ok(!/Your Rating/.test(ui.text()));
    await ui.unmount();
});

test("a failed eligibility read fails closed, and Retry asks again", async () => {
    let calls = 0;
    api.__respond("getReviewEligibility", () => (++calls === 1
        ? { data: null, error: { message: "down" }, status: 503 }
        : { data: { can_review: true, already_reviewed: false, reason: null }, error: null, status: 200 }));
    const ui = await mountLawyersFromLink([], { lawyer: "L1", lawyer_name: "Adv Ayesha Khan", action: "review" }, [], [listed]);
    await settle(60);
    assert.equal(reviewState(), "error");
    assert.ok(!/Your Rating/.test(ui.text()), "the form showed without an answer");
    await ui.click("Retry");
    await settle(60);
    assert.equal(reviewState(), "can");
    assert.ok(calls >= 2);
    await ui.unmount();
});
