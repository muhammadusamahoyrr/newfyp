/* The agreement you are about to sign must be on the screen.
 *
 * THE REGRESSION THIS EXISTS FOR. Gate 3F made `GET /agreements` return light
 * rows without `body_html` -- correct on its own, and tested on its own. Both
 * screens then derived the displayed body from the list row, so after 3F every
 * agreement opened showing "No content." while the Sign button kept working.
 * A party could put their name to a contract whose text the UI could not
 * display, engagement letters included, and those gate all billing.
 *
 * Nothing caught it. The backend tests correctly asserted the list OMITS the
 * body; the frontend tests asserted the right calls were made. No test had
 * ever rendered a detail modal from a light row -- the composer tests handed
 * the component a full draft object directly. Asserting the call and never the
 * outcome is the same gap that hid two weak tests in 3F and 3E.
 *
 * So these tests mount the REAL screens against a LIGHT row, open the thing a
 * user would open, and read what is on screen.
 *
 * WHAT IS MOCKED: the API client's return contract, and nothing else. The test
 * loader swaps `@/lib/api.js` for spies whenever component code imports it
 * (tests/support/jsx-loader.mjs), so the outermost seam available to a mounted
 * test is the api function's `{data, error, status}` -- the same shape
 * `apiFetch` returns. The components, their state and their rendering are all
 * real.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>",
                      { url: "http://localhost/" });

function define(name, value) {
    Object.defineProperty(globalThis, name, { value, writable: true, configurable: true });
}
for (const name of ["window", "document", "navigator", "HTMLElement", "Element",
                    "Node", "Event", "CustomEvent", "MutationObserver",
                    "getComputedStyle", "requestAnimationFrame",
                    "cancelAnimationFrame"]) {
    define(name, dom.window[name]);
}
define("IS_REACT_ACT_ENVIRONMENT", true);
define("localStorage", {
    _v: {},
    getItem(k) { return this._v[k] ?? null; },
    setItem(k, v) { this._v[k] = String(v); },
    removeItem(k) { delete this._v[k]; },
});
define("BroadcastChannel", class {
    constructor() { this.onmessage = null; }
    postMessage() {}
    close() {}
});

const React = (await import("react")).default;
const { act } = await import("react");
const { createRoot } = await import("react-dom/client");
const { __calls, __respond, __reset } = await import("./support/api-stub.mjs");
const { AgreementsPage } = await import("../src/components/lawyer/AgreementsPage.jsx");
const { DraftComposer } = await import("../src/components/lawyer/DraftComposer.jsx");
const ModAgreements = (await import("../src/components/client/ModAgreements.jsx")).default;
const { AuthProvider } = await import("../src/context/AuthContext.jsx");

const { createElement: h } = React;

const ME = "L1";
const THEM = "C1";
const BODY = "Fees are 40% of net recovery, payable on settlement.";

/* A row exactly as GET /agreements returns it after 3F: no body_html. */
const lightRow = (over = {}) => ({
    id: "A1", _id: "A1", title: "Retainer", status: "pending",
    created_by: ME, version: 3,
    parties: [{ user_id: ME, full_name: "Adv Khan", signed: false },
              { user_id: THEM, full_name: "The Client", signed: false }],
    created_at: "2026-03-01T00:00:00Z",
    ...over,
});

/* The full document, as GET /agreements/{id} returns it. */
const fullDoc = (over = {}) => ({ ...lightRow(), body_html: BODY, ...over });

const ok = (data) => ({ data, error: null, status: 200 });
const page = (items) => ok({
    items, total: items.length, page: 1, page_size: 20,
    pages: Math.max(1, Math.ceil(items.length / 20)),
});

/* Sign the test in as a real party.
 *
 * AuthProvider hydrates through `bootstrapAuth()` then `getMe()`, BOTH of
 * which the loader stubs -- so writing localStorage did nothing and `user`
 * stayed null. That silently made every "is the sign button gated?" test
 * vacuous: the button was absent because nobody was recognised as a party,
 * not because of the gate under test. Caught by the prove-it run, which
 * reverted the gate and saw the tests stay green. */
function signedInAs(userId) {
    __respond("bootstrapAuth", () => true);
    __respond("getMe", () => ({
        data: { _id: userId, full_name: "Adv Khan", role: "lawyer" },
        error: null, status: 200,
    }));
}

/* Every screen a test mounts is unmounted after it. Left mounted, a screen's
 * own timers (the 3.2 s toast) fired during a LATER test, outside act -- the
 * "not wrapped in act(...)" warnings. */
const mounted = [];
test.afterEach(async () => {
    while (mounted.length) {
        const { root, host } = mounted.pop();
        await act(async () => { root.unmount(); });
        host.remove();
    }
});

async function mount(element) {
    const host = dom.window.document.createElement("div");
    dom.window.document.body.appendChild(host);
    const root = createRoot(host);
    mounted.push({ root, host });
    await act(async () => { root.render(element); });
    await act(async () => {});
    await act(async () => {});

    const api = {
        host,
        text: () => host.textContent,
        buttons: () => [...host.querySelectorAll("button")],
        button(label) {
            return api.buttons().find(
                b => b.textContent.replace(/\s+/g, " ").includes(label));
        },
        async click(el) {
            assert.ok(el, "nothing to click");
            await act(async () => {
                el.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
            });
            await act(async () => {});
        },
        async clickButton(label) {
            const el = api.button(label);
            assert.ok(el, `no button matching ${JSON.stringify(label)} -- saw: `
                + api.buttons().map(b => JSON.stringify(b.textContent.trim())).join(" | "));
            await api.click(el);
        },
        /* Clicks whatever carries this text -- the client sidebar and the
           filter pills are clickable <div>s, not <button>s. Picks the
           innermost match so the click lands on the handler's own element
           rather than a wrapper that happens to contain the word. */
        async clickText(label) {
            const matches = [...host.querySelectorAll("div, button, span")]
                .filter(el => el.textContent.replace(/\s+/g, " ").trim() === label);
            const el = matches[matches.length - 1]
                || [...host.querySelectorAll("div, button")]
                    .filter(e => e.textContent.includes(label)).pop();
            assert.ok(el, `nothing clickable with text ${JSON.stringify(label)}`);
            await api.click(el);
        },
        /* The row is a div with an onClick; React delegates, so clicking any
           descendant carrying the title bubbles to it. */
        async openRow(title) {
            const candidates = [...host.querySelectorAll("div")]
                .filter(d => d.textContent.includes(title));
            const deepest = candidates[candidates.length - 1];
            assert.ok(deepest, `no row containing ${JSON.stringify(title)}`);
            await api.click(deepest);
        },
        async type(placeholder, value) {
            const el = host.querySelector(`[placeholder="${placeholder}"]`);
            assert.ok(el, `no field with placeholder ${JSON.stringify(placeholder)}`);
            const proto = el.tagName === "TEXTAREA"
                ? dom.window.HTMLTextAreaElement.prototype
                : dom.window.HTMLInputElement.prototype;
            const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
            await act(async () => {
                setter.call(el, value);
                el.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
            });
        },
    };
    return api;
}

const lawyerScreen = () => h(AuthProvider, null, h(AgreementsPage));
const clientScreen = () => h(AuthProvider, null, h(ModAgreements));

test.beforeEach(() => {
    __reset();
    signedInAs(ME);
    // Both screens keep the open agreement in the address (?agreement=), and
    // every test here shares one window: start each from a clean address.
    dom.window.history.replaceState(null, "", "/");
});

// ── the body reaches the screen ─────────────────────────────────────────────

test("lawyer: opening an agreement shows its text, fetched by id", async () => {
    __respond("listAgreements", () => page([lightRow()]));
    __respond("getAgreement", () => ok(fullDoc()));

    const ui = await mount(lawyerScreen());
    await ui.openRow("Retainer");

    assert.ok(ui.text().includes(BODY),
        "the agreement text is not on screen; the list row's empty body was "
        + "rendered instead of the fetched document");
    assert.ok(!ui.text().includes("No content."),
        '"No content." was shown for an agreement that has text');
    assert.equal(__calls("getAgreement").length, 1,
        "the screen must fetch the document, not trust the list row");
});

test("client: opening an agreement shows its text, fetched by id", async () => {
    __respond("listAgreements", () => page([lightRow()]));
    __respond("getAgreement", () => ok(fullDoc()));

    const ui = await mount(clientScreen());
    await ui.clickText("See all");
    await ui.openRow("Retainer");

    assert.ok(ui.text().includes(BODY), "the agreement text is not on screen");
    assert.ok(!ui.text().includes("No content."));
    assert.equal(__calls("getAgreement").length, 1);
});

/* 2026-11-25: a declined agreement said "Rejected" and nothing else -- the
 * reason was only in the notification. The server now sends `declined`. */
test("client: a declined agreement says who declined it and why", async () => {
    const declined = lightRow({ status: "cancelled",
        declined: { by_user_id: THEM, by_name: "The Client", at: "2026-11-25T09:00:00Z",
                    reason: "The fee clause is wrong." } });
    __respond("listAgreements", () => page([declined]));
    __respond("getAgreement", () => ok({ ...declined, body_html: BODY }));

    const ui = await mount(clientScreen());
    await ui.clickText("See all");
    await ui.openRow("Retainer");

    const box = ui.host.querySelector("[data-agreement-declined]");
    assert.ok(box, "no decline note on the declined agreement");
    assert.match(box.textContent, /Declined by The Client on Nov 25, 2026/);
    assert.match(box.textContent, /Reason: The fee clause is wrong\./);
});

test("client: a decline with no reason says so, and the decliner sees 'You declined'", async () => {
    const declined = lightRow({ status: "cancelled",
        declined: { by_user_id: ME, by_name: "Adv Khan", at: null, reason: null } });
    __respond("listAgreements", () => page([declined]));
    __respond("getAgreement", () => ok({ ...declined, body_html: BODY }));

    const ui = await mount(clientScreen());
    await ui.clickText("See all");
    await ui.openRow("Retainer");

    const box = ui.host.querySelector("[data-agreement-declined]");
    assert.match(box.textContent, /You declined this agreement/);
    assert.match(box.textContent, /No reason was given\./);
});

/* LIVE (2026-11-25): a lawyer signing or declining left the client's
 * Agreements page saying "Pending" until a manual reload. */
test("client: a signed/declined notice refreshes the list and the open agreement", async () => {
    const { broadcastNotification } = await import("../src/lib/notificationTarget.js");
    const pending = lightRow({ created_by: THEM });
    __respond("listAgreements", () => page([pending]));
    __respond("getAgreement", () => ok({ ...pending, body_html: BODY }));

    const ui = await mount(clientScreen());
    await ui.clickText("See all");
    await ui.openRow("Retainer");
    assert.equal(ui.host.querySelector("[data-agreement-declined]"), null);
    const listReads = __calls("listAgreements").length;

    const declined = lightRow({ created_by: THEM, status: "cancelled",
        declined: { by_user_id: THEM, by_name: "The Client", at: null, reason: "Not now." } });
    __respond("listAgreements", () => page([declined]));
    __respond("getAgreement", () => ok({ ...declined, body_html: BODY }));
    await act(async () => { broadcastNotification({ type: "agreement_declined", payload: { agreement_id: "A1" } }); });
    await act(async () => {});
    await act(async () => {});

    assert.ok(__calls("listAgreements").length > listReads, "the list was not re-read");
    const box = ui.host.querySelector("[data-agreement-declined]");
    assert.ok(box, "the open agreement still shows the old pending state");
    assert.match(box.textContent, /Reason: Not now\./);
});

test("client: two quick notices — the older answer never replaces the newer status", async () => {
    const { broadcastNotification } = await import("../src/lib/notificationTarget.js");
    const pending = lightRow({ created_by: THEM });
    __respond("listAgreements", () => page([pending]));
    __respond("getAgreement", () => ok({ ...pending, body_html: BODY }));
    const ui = await mount(clientScreen());
    await ui.clickText("See all");
    await ui.openRow("Retainer");

    // First notice: its read is SLOW and answers "still pending".
    let releaseOld;
    const old = new Promise(r => { releaseOld = r; });
    __respond("getAgreement", () => old);
    await act(async () => { broadcastNotification({ type: "agreement_signed", payload: { agreement_id: "A1" } }); });
    // Second notice: answers at once with the newer state, declined.
    const declined = lightRow({ created_by: THEM, status: "cancelled",
        declined: { by_user_id: THEM, by_name: "The Client", at: null, reason: "Newest." } });
    __respond("getAgreement", () => ok({ ...declined, body_html: BODY }));
    await act(async () => { broadcastNotification({ type: "agreement_declined", payload: { agreement_id: "A1" } }); });
    await act(async () => {});
    assert.ok(ui.host.querySelector("[data-agreement-declined]"), "precondition: the newer state is shown");

    await act(async () => { releaseOld(ok({ ...pending, body_html: BODY })); });
    await act(async () => {});
    assert.ok(ui.host.querySelector("[data-agreement-declined]"), "the older answer replaced the newer status");
});

test("client: a notice about something else does not re-read the list", async () => {
    const { broadcastNotification } = await import("../src/lib/notificationTarget.js");
    __respond("listAgreements", () => page([lightRow()]));
    const ui = await mount(clientScreen());
    await ui.clickText("See all");
    const reads = __calls("listAgreements").length;
    await act(async () => { broadcastNotification({ type: "case_message", payload: { case_id: "C1" } }); });
    assert.equal(__calls("listAgreements").length, reads);
    void ui;
});

/* D1 + B3 (2026-11-25): the agreement view uses the builder's typeface, keeps
 * the agreement's own text in its document face, and shows no emoji icons. */
test("client: the agreement view is in the builder's typeface, with icons not emoji", async () => {
    __respond("listAgreements", () => page([lightRow()]));
    __respond("getAgreement", () => ok(fullDoc()));
    const ui = await mount(clientScreen());
    await ui.clickText("See all");
    await ui.openRow("Retainer");
    const modal = [...ui.host.querySelectorAll("[data-ag-font]")].find(el => el.textContent.includes(BODY));
    assert.ok(modal, "the agreement view is outside the typeface wrapper");
    const body = [...modal.querySelectorAll("[data-keep-font]")].find(el => el.textContent.includes(BODY));
    assert.ok(body, "the agreement's own text would be forced into the UI font");
    assert.doesNotMatch(modal.textContent, /[\u{1F300}-\u{1FAFF}✅⏰✍⚖]/u, "emoji used as an icon");
});

test("client: a pending agreement has no decline note", async () => {
    __respond("listAgreements", () => page([lightRow()]));
    __respond("getAgreement", () => ok(fullDoc()));
    const ui = await mount(clientScreen());
    await ui.clickText("See all");
    await ui.openRow("Retainer");
    assert.equal(ui.host.querySelector("[data-agreement-declined]"), null);
});

test("an engagement letter is fetched the same way", async () => {
    // Engagement letters travel the same list and gate all billing, so they
    // are the worst thing to render as "No content." beside a Sign button.
    const letter = lightRow({ id: "E9", _id: "E9", engagement_id: "ENG-1",
                              title: "Engagement letter" });
    __respond("listAgreements", () => page([letter]));
    __respond("getAgreement", () => ok({ ...letter, body_html: BODY }));

    const ui = await mount(lawyerScreen());
    await ui.openRow("Engagement letter");

    assert.ok(ui.text().includes(BODY));
    assert.equal(__calls("getAgreement")[0].args[0], "E9");
});

// ── failure must not leave a signable blank ─────────────────────────────────

test("lawyer: a failed fetch shows an error and no way to sign", async () => {
    __respond("listAgreements", () => page([lightRow()]));
    __respond("getAgreement", () => ({
        data: null, error: { message: "Network error" }, status: 0 }));

    const ui = await mount(lawyerScreen());
    await ui.openRow("Retainer");

    assert.match(ui.text(), /could not be loaded|network error/i,
        "the failure was silent");
    assert.equal(ui.button("Sign Agreement"), undefined,
        "signing was offered for text the user was never shown");
    assert.equal(ui.button("Decline…"), undefined,
        "declining was offered for text the user was never shown");
});

test("client: a failed fetch shows an error and no way to sign", async () => {
    __respond("listAgreements", () => page([lightRow()]));
    __respond("getAgreement", () => ({
        data: null, error: { message: "Network error" }, status: 0 }));

    const ui = await mount(clientScreen());
    await ui.clickText("See all");
    await ui.openRow("Retainer");

    assert.match(ui.text(), /could not be loaded|network error/i);
    assert.equal(ui.button("Sign Agreement"), undefined);
});

test('a genuinely empty body still reads "No content."', async () => {
    // The legitimate case, kept so the fix above is not over-applied: an
    // agreement whose stored body really is empty must say so, rather than
    // reporting a load failure that did not happen.
    __respond("listAgreements", () => page([lightRow()]));
    __respond("getAgreement", () => ok(fullDoc({ body_html: "" })));

    const ui = await mount(lawyerScreen());
    await ui.openRow("Retainer");

    assert.ok(ui.text().includes("No content."));
    assert.ok(!/could not be loaded/i.test(ui.text()),
        "an empty body is not a load failure");
});

// ── the draft editor ────────────────────────────────────────────────────────

test("composer: opens populated from the fetch, and not dirty", async () => {
    __respond("getAgreement", () => ok(fullDoc({ status: "draft", version: 4 })));

    const ui = await mount(h(DraftComposer, {
        draft: lightRow({ status: "draft" }), onClose() {}, onSaved() {},
    }));

    const textarea = ui.host.querySelector("textarea");
    assert.ok(textarea, "no editor rendered");
    assert.equal(textarea.value, BODY,
        "the editor opened blank; saving would replace the real wording");
    assert.ok(!ui.text().includes("Unsaved changes"),
        "a freshly opened draft must not claim unsaved edits");
    assert.ok(ui.text().includes("version 4"),
        "the version must come from the fetched draft");
});

test("composer: a failed fetch disables saving so nothing is overwritten", async () => {
    __respond("getAgreement", () => ({
        data: null, error: { message: "Network error" }, status: 0 }));

    const ui = await mount(h(DraftComposer, {
        draft: lightRow({ status: "draft" }), onClose() {}, onSaved() {},
    }));

    assert.match(ui.text(), /could not be loaded|network error/i);

    // There must be NO EDITABLE SURFACE at all. Asserting only "the Save
    // button is disabled" passed trivially, because a failed load renders no
    // Save button either way -- the test could not tell a guarded editor from
    // an absent one.
    assert.equal(ui.host.querySelector("textarea"), null,
        "an editable textarea over an unloaded draft is one Save away from "
        + "replacing the real terms with an empty string");
    const save = ui.button("Save");
    assert.ok(!save || save.disabled, "saving was possible while unloaded");

    // And nothing may reach the server even if something did click.
    assert.equal(__calls("updateDraft").length, 0);
});

test("composer: a save after a successful load sends the loaded body", async () => {
    __respond("getAgreement", () => ok(fullDoc({ status: "draft", version: 4 })));
    __respond("updateDraft", () => ok(fullDoc({ status: "draft", version: 5 })));

    const ui = await mount(h(DraftComposer, {
        draft: lightRow({ status: "draft" }), onClose() {}, onSaved() {},
    }));
    await ui.type("Write the terms of this agreement…", BODY + " Addendum.");
    await ui.clickButton("Save changes");

    const [, payload] = __calls("updateDraft")[0].args;
    assert.equal(payload.body_html, BODY + " Addendum.");
    assert.equal(payload.expected_version, 4,
        "the version must be the fetched one, not the list row's");
});

// ── nothing is invisible ────────────────────────────────────────────────────

test("lawyer: the 51st agreement is reachable and the count is honest", async () => {
    const many = Array.from({ length: 51 }, (_, i) => lightRow({
        id: `A${i + 1}`, _id: `A${i + 1}`, title: `Agreement ${i + 1}`,
    }));
    __respond("listAgreements", (opts = {}) => {
        const size = opts.page_size || 20;
        const p = opts.page || 1;
        const slice = many.slice((p - 1) * size, p * size);
        return ok({ items: slice, total: many.length, page: p,
                    page_size: size, pages: Math.ceil(many.length / size) });
    });
    __respond("getAgreement", () => ok(fullDoc()));

    const ui = await mount(lawyerScreen());

    assert.match(ui.text(), /of 51/,
        "the screen does not say how many agreements exist, so a truncated "
        + "list is indistinguishable from a complete one");

    assert.ok(!ui.text().includes("Agreement 51"), "sanity: not shown yet");

    // Keep loading while the affordance is offered. "Reachable" means the UI
    // can get there, not that it arrives in one click -- how many pages that
    // takes is a page-size detail the test should not encode.
    for (let guard = 0; guard < 10 && ui.button("Load more"); guard += 1) {
        await ui.clickButton("Load more");
    }

    assert.ok(ui.text().includes("Agreement 51"),
        "the 51st agreement is unreachable");
    assert.equal(ui.button("Load more"), undefined,
        "the screen still offers more when everything is already shown");
});

test("lawyer: changing the status filter returns to the first page", async () => {
    const many = Array.from({ length: 51 }, (_, i) => lightRow({
        id: `A${i + 1}`, _id: `A${i + 1}`, title: `Agreement ${i + 1}`,
    }));
    __respond("listAgreements", (opts = {}) => {
        const size = opts.page_size || 20;
        const p = opts.page || 1;
        return ok({ items: many.slice((p - 1) * size, p * size),
                    total: many.length, page: p, page_size: size,
                    pages: Math.ceil(many.length / size) });
    });

    const ui = await mount(lawyerScreen());
    await ui.clickButton("Load more");

    const before = __calls("listAgreements").length;
    assert.ok((__calls("listAgreements").at(-1).args[0]?.page || 1) > 1,
        "sanity: Load more should have advanced the page");

    // The status filter is a folder now (V5, 2026-11-26): "Completed" asks
    // the server for executed agreements.
    await ui.clickText("Signed");

    // ASSERT ON THE RECORDED CALL, not inside the stub. A throw inside the
    // responder becomes a rejected promise that the screen's own .catch()
    // swallows, so the test passed no matter what the component did.
    const after = __calls("listAgreements").slice(before);
    assert.ok(after.length > 0, "the filter did not reload the list");
    assert.equal(after.at(-1).args[0]?.page || 1, 1,
        "a filter change kept the old page, so the user sees page 3 of a "
        + "list they just narrowed");
    assert.equal(after.at(-1).args[0]?.status, "executed",
        "the filter value did not reach the server");
});

test("client: the 51st agreement is reachable and the count is honest", async () => {
    const many = Array.from({ length: 51 }, (_, i) => lightRow({
        id: `A${i + 1}`, _id: `A${i + 1}`, title: `Agreement ${i + 1}`,
    }));
    __respond("listAgreements", (opts = {}) => {
        const size = opts.page_size || 20;
        const p = opts.page || 1;
        return ok({ items: many.slice((p - 1) * size, p * size),
                    total: many.length, page: p, page_size: size,
                    pages: Math.ceil(many.length / size) });
    });
    __respond("getAgreement", () => ok(fullDoc()));

    const ui = await mount(clientScreen());
    await ui.clickText("See all");

    assert.match(ui.text(), /of 51/,
        "the screen does not say how many agreements exist");
    assert.ok(!ui.text().includes("Agreement 51"), "sanity: not shown yet");

    for (let guard = 0; guard < 10 && ui.button("Load more"); guard += 1) {
        await ui.clickButton("Load more");
    }
    assert.ok(ui.text().includes("Agreement 51"),
        "the 51st agreement is unreachable");
});

// ── a slow answer must not overwrite a newer question ───────────────────────

test("lawyer: a late fetch for A does not overwrite the open B", async () => {
    // Open A, open B before A answers, then let A answer. If the late reply
    // wins, the modal shows B's title above A's terms -- one agreement's
    // wording under another's heading, on a signing surface.
    const rowA = lightRow({ id: "A1", _id: "A1", title: "Agreement A" });
    const rowB = lightRow({ id: "B2", _id: "B2", title: "Agreement B" });
    __respond("listAgreements", () => page([rowA, rowB]));

    const pending = [];
    __respond("getAgreement", (id) => new Promise(resolve => {
        pending.push(() => resolve(ok({
            ...(id === "A1" ? rowA : rowB),
            body_html: id === "A1" ? "TERMS OF A" : "TERMS OF B",
        })));
    }));

    const ui = await mount(lawyerScreen());
    await ui.openRow("Agreement A");   // A in flight
    await ui.openRow("Agreement B");   // B in flight
    assert.equal(pending.length, 2, "both fetches should be in flight");

    await act(async () => { pending[1](); });   // B answers
    await act(async () => { pending[0](); });   // A answers LATE
    await act(async () => {});

    assert.ok(ui.text().includes("TERMS OF B"), "B's terms are not shown");
    assert.ok(!ui.text().includes("TERMS OF A"),
        "a stale reply overwrote the open agreement: the reader sees one "
        + "agreement's heading above another's wording");
});

test("client: a late fetch for A does not overwrite the open B", async () => {
    const rowA = lightRow({ id: "A1", _id: "A1", title: "Agreement A" });
    const rowB = lightRow({ id: "B2", _id: "B2", title: "Agreement B" });
    __respond("listAgreements", () => page([rowA, rowB]));

    const pending = [];
    __respond("getAgreement", (id) => new Promise(resolve => {
        pending.push(() => resolve(ok({
            ...(id === "A1" ? rowA : rowB),
            body_html: id === "A1" ? "TERMS OF A" : "TERMS OF B",
        })));
    }));

    const ui = await mount(clientScreen());
    await ui.clickText("See all");
    await ui.openRow("Agreement A");
    await ui.openRow("Agreement B");
    assert.equal(pending.length, 2);

    await act(async () => { pending[1](); });
    await act(async () => { pending[0](); });
    await act(async () => {});

    assert.ok(ui.text().includes("TERMS OF B"));
    assert.ok(!ui.text().includes("TERMS OF A"),
        "a stale reply overwrote the open agreement");
});

// ── after acting, what is on screen is what the server says ─────────────────

test("lawyer: after signing, the list shows the server's new status", async () => {
    let signed = false;
    __respond("listAgreements", () => page([
        lightRow(signed
            ? { status: "executed",
                parties: [{ user_id: ME, full_name: "Adv Khan", signed: true },
                          { user_id: THEM, full_name: "The Client", signed: true }] }
            : {}),
    ]));
    __respond("getAgreement", () => ok(fullDoc()));
    __respond("signAgreement", () => { signed = true; return ok(fullDoc({ status: "executed" })); });

    const ui = await mount(lawyerScreen());
    await ui.openRow("Retainer");
    const before = __calls("listAgreements").length;

    // THE SIGNING UI IS NO LONGER A NAME BOX. A counter-signer now gets the
    // same draw/type/upload pad the sender always had, so the typed mode has
    // to be selected before there is a field to type into. Driving the real
    // control is the point -- asserting on a placeholder that no longer exists
    // would only prove the test was written against the old screen.
    // The 4-step flow (2026-11-26): start screen, "Sign here" on the paper,
    // the signature popup, then Finish in the top bar.
    await ui.clickButton("Sign here");
    await ui.clickButton("Type");
    await ui.type("Type your name…", "Adv Khan");
    const consent = ui.host.querySelector('input[type="checkbox"]');
    assert.ok(consent, "the signing consent checkbox is missing");
    await ui.click(consent);
    await ui.clickButton("Use this signature");
    await ui.clickButton("Finish");
    await act(async () => {});

    // COUNTED RELATIVE TO THE ACTION. Auth hydration fires its own reload
    // when `user` arrives, so an absolute count asserts a property of the
    // test harness rather than of the screen.
    assert.ok(__calls("listAgreements").length > before,
        "the list was not refreshed from the server after signing");
    assert.ok(ui.text().includes("Executed"),
        "the screen still shows the pre-signature status");
});

test("lawyer: after declining, the refreshed row comes from the server", async () => {
    let declined = false;
    __respond("listAgreements", () => page([
        lightRow(declined ? { status: "cancelled" } : {}),
    ]));
    __respond("getAgreement", () => ok(fullDoc()));
    __respond("declineAgreement", () => { declined = true; return ok(fullDoc({ status: "cancelled" })); });

    const ui = await mount(lawyerScreen());
    await ui.openRow("Retainer");
    const before = __calls("listAgreements").length;

    await ui.click(ui.host.querySelector("[data-more-actions]"));
    await ui.clickButton("Decline to sign");
    await ui.clickButton("Confirm decline");
    await act(async () => {});

    assert.ok(__calls("listAgreements").length > before,
        "no refresh after declining");
    assert.match(ui.text(), /Declined/, "the refreshed row does not show the decline");
});

// ── paging asks the server for the next page ────────────────────────────────

test("lawyer: Load more requests page 2 and the count line moves", async () => {
    const many = Array.from({ length: 51 }, (_, i) => lightRow({
        id: `A${i + 1}`, _id: `A${i + 1}`, title: `Agreement ${i + 1}`,
    }));
    __respond("listAgreements", (opts = {}) => {
        const size = opts.page_size || 20;
        const p = opts.page || 1;
        return ok({ items: many.slice((p - 1) * size, p * size),
                    total: many.length, page: p, page_size: size,
                    pages: Math.ceil(many.length / size) });
    });

    const ui = await mount(lawyerScreen());
    const firstCount = ui.text().match(/Showing (\d+) of 51/)?.[1];
    assert.ok(firstCount, "no count line on the first page");

    await ui.clickButton("Load more");

    const pagesAsked = __calls("listAgreements").map(c => c.args[0]?.page || 1);
    assert.ok(pagesAsked.includes(2),
        `page 2 was never requested; asked for ${JSON.stringify(pagesAsked)}`);

    const secondCount = ui.text().match(/Showing (\d+) of 51/)?.[1];
    assert.ok(Number(secondCount) > Number(firstCount),
        `the count line did not move: ${firstCount} then ${secondCount}`);
});

/* ── lawyer V5 folders (2026-11-26) ─────────────────────────────────────── */

test("lawyer: folders count from the server, and Action required shows only what needs my signature", async () => {
    const mine = lightRow();                                                          // my signature missing
    const theirs = lightRow({ id: "A2", _id: "A2", title: "Settlement",
        parties: [{ user_id: ME, full_name: "Adv Khan", signed: true }, { user_id: THEM, full_name: "The Client", signed: false }] });
    const done = lightRow({ id: "A3", _id: "A3", title: "Old retainer", status: "executed",
        parties: [{ user_id: ME, signed: true }, { user_id: THEM, signed: true }] });
    __respond("listAgreements", (opts = {}) => page(
        opts.status === "pending" ? [mine, theirs] : opts.status === "executed" ? [done] : [mine, theirs, done]));
    const ui = await mount(lawyerScreen());
    // Client-style page (2026-11-27): a count line, status tabs, a table.
    assert.match(ui.host.querySelector("[data-agreements-count]").textContent, /^3 agreements · 1 needs your signature$/);
    assert.equal(ui.host.querySelector('[data-folder-count="action"]').textContent, "1");
    assert.deepEqual([...ui.host.querySelectorAll("[data-folder]")].map(b => b.textContent.replace(/\d+$/, "")),
        ["All", "Needs my signature", "Pending", "Signed", "Declined"]);
    assert.equal(ui.host.querySelector('[data-folder="drafts"]'), null, "a Drafts tab for a lawyer who cannot draft");

    await ui.click(ui.host.querySelector('[data-folder="action"]'));
    await act(async () => {});
    const rows = [...ui.host.querySelectorAll("[data-agreement-row]")].map(r => r.getAttribute("data-agreement-row"));
    assert.deepEqual(rows, ["A1"], "Action required lists an agreement that does not need my signature");
    assert.ok(ui.host.querySelector('[data-agreement-row="A1"]').hasAttribute("data-needs-me"));
    assert.match(ui.host.querySelector('[data-agreement-row="A1"] button').textContent, /Review & sign/);
    assert.ok(ui.host.querySelector(".al-table .al-th"), "no table header");
    assert.equal(__calls("listAgreements").at(-1).args[0]?.status, "pending", "the folder did not ask the server for pending");
    await ui.unmount?.();
});

test("lawyer flow: opens straight on the agreement with a locked Finish (2026-11-27)", async () => {
    __respond("listAgreements", () => page([lightRow({ parties: [
        { user_id: ME, full_name: "Adv Khan", signed: false },
        { user_id: THEM, full_name: "The Client", signed: true, signed_at: "2026-11-26T05:42:00Z" }] })]));
    __respond("getAgreement", () => ok(fullDoc({ parties: [
        { user_id: ME, full_name: "Adv Khan", signed: false },
        { user_id: THEM, full_name: "The Client", signed: true, signed_at: "2026-11-26T05:42:00Z" }] })));
    const ui = await mount(lawyerScreen());
    await ui.openRow("Retainer");
    // Straight into the agreement: no start screen (user, 2026-11-27).
    assert.equal(ui.host.querySelector("[data-sign-gate]"), null, "the start screen is back");
    // No "fields left" / Next in the bar (user, 2026-11-27): one field, on the paper.
    assert.equal(ui.host.querySelector("[data-fields-left]"), null);
    assert.equal(ui.host.querySelector("[data-next-field]"), null);
    assert.ok(ui.host.querySelector("[data-finish]").disabled, "Finish works before a signature is added");
    const paper = ui.host.querySelector("[data-agreement-paper]");
    assert.ok(paper.textContent.includes(BODY), "the text is not on the paper");
    assert.deepEqual([...paper.querySelectorAll("[data-party-line]")].map(n => n.getAttribute("data-party-line")), ["you", "signed"]);
    assert.ok(paper.querySelector("[data-sign-here]"), "no Sign here on the paper");
    await ui.unmount?.();
});

test("lawyer flow: the signature is adopted onto the paper, Finish signs, and the window says 'You're all set' (2026-11-26)", async () => {
    let signed = false;
    __respond("listAgreements", () => page([lightRow(signed ? { status: "executed" } : {})]));
    __respond("getAgreement", () => ok(fullDoc()));
    __respond("getAgreement", () => ok(fullDoc({ eto_classification: "Typed name" })));
    __respond("signAgreement", () => { signed = true; return ok(fullDoc({ status: "executed", eto_classification: "Signature drawn in browser" })); });
    const ui = await mount(lawyerScreen());
    await ui.openRow("Retainer");
    await ui.clickButton("Sign here");
    assert.ok(ui.host.querySelector("[data-agreement-sign]"), "no signature popup");
    await ui.clickButton("Type");
    await ui.type("Type your name…", "Adv Khan");
    await ui.click(ui.host.querySelector('[data-agreement-sign] input[type="checkbox"]'));
    await ui.clickButton("Use this signature");
    assert.equal(__calls("signAgreement").length, 0, "adopting a signature already signed the agreement");
    assert.ok(ui.host.querySelector("[data-adopted-signature]"), "the signature is not shown on the paper");
    assert.equal(ui.host.querySelector("[data-finish]").disabled, false, "Finish stays locked after a signature is added");
    await ui.clickButton("Finish");
    await act(async () => {});
    assert.equal(__calls("signAgreement").length, 1);
    assert.match(ui.host.querySelector("[data-sign-done]").textContent, /You’re all set/);
    assert.match(ui.host.querySelector("[data-agreement-topbar]").textContent, /Executed/, "the header still says Pending behind 'You're all set'");
    assert.doesNotMatch(ui.host.querySelector("[data-agreement-topbar]").textContent, /Pending/);
    assert.match(ui.host.querySelector("[data-agreement-subtitle]").textContent, /Signing method: Signature drawn in browser/, "the signing method kept its pre-signature value");
    await ui.unmount?.();
});

test("lawyer: the window says where the agreement stands, not just 'Typed name' (2026-11-26)", async () => {
    __respond("listAgreements", () => page([lightRow()]));
    __respond("getAgreement", () => ok(fullDoc({ eto_classification: "Typed name" })));
    const ui = await mount(lawyerScreen());
    await ui.openRow("Retainer");
    const sub = ui.host.querySelector("[data-agreement-subtitle]").textContent;
    assert.match(sub, /^From The Client — waiting for your signature/, "no status in the subtitle");
    assert.match(sub, /Signing method: Typed name$/, "the method lost its label");
    await ui.unmount?.();
});

/* 2026-11-27: the client's agreement opens in the same window as the lawyer's —
 * the paper, "Sign here", the signature popup, Finish in the top bar. */
test("client flow: Sign here → Use this signature → Finish signs, and the window says 'You're all set'", async () => {
    let signed = false;
    __respond("listAgreements", () => page([lightRow(signed ? { status: "executed" } : {})]));
    __respond("getAgreement", () => ok(fullDoc()));
    __respond("signAgreement", () => { signed = true; return ok(fullDoc({ status: "executed", eto_classification: "Typed name" })); });
    const ui = await mount(clientScreen());
    await ui.clickText("See all");
    await ui.openRow("Retainer");
    const paper = ui.host.querySelector("[data-agreement-paper]");
    assert.ok(paper && paper.textContent.includes(BODY), "the text is not on the paper");
    assert.equal(ui.host.querySelector("[data-finish]").disabled, true, "Finish is open before any signature");
    await ui.clickButton("Sign here");
    assert.ok(ui.host.querySelector("[data-agreement-sign]"), "no signature popup");
    await ui.clickButton("Type");
    await ui.type("Type your name…", "The Client");
    await ui.click(ui.host.querySelector('[data-agreement-sign] input[type="checkbox"]'));
    await ui.clickButton("Use this signature");
    assert.equal(__calls("signAgreement").length, 0, "adopting a signature already signed the agreement");
    assert.ok(ui.host.querySelector("[data-adopted-signature]"), "the signature is not shown on the paper");
    await ui.clickButton("Finish");
    await act(async () => {});
    assert.equal(__calls("signAgreement").length, 1);
    assert.match(ui.host.querySelector("[data-sign-done]").textContent, /You’re all set/);
    assert.doesNotMatch(ui.host.querySelector("[data-agreement-topbar]").textContent, /Pending/);
    await ui.unmount?.();
});

test("client flow: decline is behind the ⋯ menu and a confirm", async () => {
    __respond("listAgreements", () => page([lightRow()]));
    __respond("getAgreement", () => ok(fullDoc()));
    __respond("declineAgreement", () => ok(fullDoc({ status: "cancelled" })));
    const ui = await mount(clientScreen());
    await ui.clickText("See all");
    await ui.openRow("Retainer");
    await ui.click(ui.host.querySelector("[data-more-actions]"));
    await ui.clickButton("Decline to sign");
    assert.equal(__calls("declineAgreement").length, 0, "one click declined");
    await ui.clickButton("Confirm decline");
    await act(async () => {});
    assert.equal(__calls("declineAgreement").length, 1);
    await ui.unmount?.();
});
