/* The agreement builder actually RENDERS, step by step.
 *
 * WHY THIS FILE EXISTS. Every other test of this screen either reads the source
 * as text or mounts the list and opens a row. None of them ever rendered
 * `PageCreate`, and the builder is where the work happens -- so three separate
 * runtime errors shipped with a clean build and a green suite:
 *
 *   - `setSignName is not defined`, after the typed-name box was replaced
 *   - `sendError is not defined`, after a refactor deleted four useState lines
 *     that the JSX below still referenced
 *   - the drawn signature read off a canvas that had already unmounted
 *
 * A webpack build does not catch an undeclared identifier, and a source-text
 * assertion cannot notice one. Only rendering does. These tests are deliberately
 * shallow -- they walk the four steps and assert each one paints -- because the
 * failure mode they guard is "the screen throws", not "the wording is wrong".
 */
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>",
                      { url: "http://localhost/" });

/* `globalThis.navigator` is getter-only on modern Node, so assignment throws.
   Same defineProperty setup the other DOM tests use. */
function define(name, value) {
    Object.defineProperty(globalThis, name, { value, writable: true, configurable: true });
}
for (const name of ["window", "document", "navigator", "HTMLElement", "Element",
                    "Node", "Event", "CustomEvent", "MouseEvent", "MutationObserver",
                    "getComputedStyle", "FileReader", "DOMParser"]) {
    define(name, dom.window[name]);
}
// jsdom only provides these with pretendToBeVisual, so copying them from the
// window lands `undefined` on the global and anything that calls one throws.
define("requestAnimationFrame", (cb) => setTimeout(() => cb(Date.now()), 0));
define("cancelAnimationFrame", (id) => clearTimeout(id));
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

// The builder is on only when the SERVER says so (GET /agreements/capabilities,
// 2026-11-25) -- there is no build-time flag any more. signedIn() answers it.

// jsdom has no canvas backend. The signature pad only needs these to exist;
// what it draws is not what these tests are about.
dom.window.HTMLCanvasElement.prototype.getContext = () => ({
    clearRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {},
    drawImage() {},
});
dom.window.HTMLCanvasElement.prototype.toDataURL = () => "data:image/png;base64,AAAA";

const React = (await import("react")).default;
const { act } = await import("react");
const { createRoot } = await import("react-dom/client");
const { __respond, __reset, __calls } = await import("./support/api-stub.mjs");
const ModAgreements = (await import("../src/components/client/ModAgreements.jsx")).default;
// Page navigation is the client sidebar's since 2026-10-11 (lib/agreementsNav.js).
const agreementsNav = await import("../src/lib/agreementsNav.js");
const { AuthProvider } = await import("../src/context/AuthContext.jsx");
const builderSwitch = await import("../src/components/client/useAgreementBuilder.js");

const { createElement: h } = React;
const ME = "C1";

function signedIn(builder = true) {
    __respond("getAgreementCapabilities", () => ({ data: { diy_builder: builder }, error: null, status: 200 }));
    __respond("bootstrapAuth", () => true);
    __respond("getMe", () => ({
        data: { _id: ME, full_name: "Test Client", role: "client" },
        error: null, status: 200,
    }));
    __respond("listAgreements", () => ({
        data: { items: [], total: 0, page: 1, page_size: 20, pages: 1 },
        error: null, status: 200,
    }));
    __respond("searchLawyers", () => ({
        data: { items: [{ _id: "L9", full_name: "Adv Verified", specializations: ["civil"] }] },
        error: null, status: 200,
    }));
}

async function mount() {
    const host = dom.window.document.createElement("div");
    dom.window.document.body.appendChild(host);
    const root = createRoot(host);
    await act(async () => { root.render(h(AuthProvider, null, h(ModAgreements))); });
    await act(async () => {});

    const api = {
        host,
        text: () => host.textContent,
        /* The builder is opened from the client sidebar's "Agreements > Create",
           which asks the module through lib/agreementsNav.js. */
        /* The drafting bar's buttons are icons; each is named by its title. */
        async clickTitle(title) {
            const el = host.querySelector(`button[title="${title}"]`);
            assert.ok(el, `no button titled ${JSON.stringify(title)}`);
            await act(async () => {
                el.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
            });
            await act(async () => {});
        },
        async openPage(view) {
            await act(async () => { agreementsNav.requestAgreementsView(view); });
            await act(async () => {});
        },
        /* Opens the builder and writes a line into the rich editor, because
           the first step will not move on without words. */
        async openCreate(html = "<p>Fees are 40% of recovery.</p>") {
            await act(async () => { agreementsNav.requestAgreementsView("create"); });
            await act(async () => {});
            const paper = host.querySelector("[data-ag-paper]");
            if (paper && html) {
                await act(async () => {
                    paper.innerHTML = html;
                    paper.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
                });
            }
        },
        async clickText(label) {
            const all = [...host.querySelectorAll("button,div,span,a")].reverse();
            // Exact first, then endsWith, then a substring match restricted to
            // BUTTONS. The last fallback exists because a dropdown renders its
            // caret inside the same button ("Clause library ▼"), so neither
            // of the stricter tests can reach it; limiting it to buttons keeps a
            // wrapping <div> that merely contains the words from being clicked
            // instead of the control.
            const el = all.find(e => e.textContent.trim() === label)
                || all.find(e => e.textContent.trim().endsWith(label))
                || all.find(e => e.tagName === "BUTTON" && e.textContent.includes(label));
            assert.ok(el, `nothing to click labelled ${JSON.stringify(label)}`);
            await act(async () => {
                el.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
            });
            await act(async () => {});
        },
    };
    return api;
}

test.beforeEach(() => {
    __reset();
    builderSwitch.__resetAgreementBuilder();
    signedIn();
    // EVERY mount appends a fresh host and nothing removed the old ones, so a
    // document-wide querySelector returned the first editor ever rendered in
    // this file instead of the one under test. Cheap to clear; confusing to
    // leave.
    dom.window.document.body.innerHTML = "";
});

test("the Create step renders without throwing", async () => {
    // `sendError is not defined` was a ReferenceError thrown from this render.
    // The build was clean and 961 tests were green, because nothing mounted it.
    const ui = await mount();
    await ui.openCreate();
    assert.ok(ui.text().includes("Edit Agreement"),
              "the builder's first step did not render");
});

/* The step bar is SEGMENTED (option D, 2026-11-25): one bar per step; finished
 * = brand, current = brand gradient + aria-current, future = muted. */
test("the step bar is one segment per step, marking done / current / to do", async () => {
    const ui = await mount();
    await ui.openCreate();
    const bar = ui.host.querySelector("[data-step-bar]");
    assert.ok(bar, "no step bar");
    const states = () => [...bar.querySelectorAll("li")].map(li => li.getAttribute("data-step"));
    assert.deepEqual(states(), ["current", "todo", "todo", "todo"]);
    await ui.clickText("Next");
    assert.deepEqual(states(), ["done", "current", "todo", "todo"]);
    const cur = bar.querySelector('[aria-current="step"]');
    assert.match(cur.textContent, /Add Signers/);
    assert.match(cur.querySelector("span").style.background, /--brand-solid/);
    assert.match(bar.querySelector('[data-step="done"]').textContent, /\(completed\)/, "finished steps are not announced as completed");
});

test("every step of the wizard paints", async () => {
    const ui = await mount();
    await ui.openCreate();

    // Step 1 -> 2. The title defaults, so Next is allowed.
    await ui.clickText("Next");
    assert.ok(ui.text().includes("Signers"), "the Add Signers step did not render");

    // A signer is required before the signature step.
    await ui.clickText("+ Add");
    await ui.clickText("Next");
    assert.ok(ui.text().includes("Your Signature") || ui.text().includes("Draw"),
              "the signature step did not render");
});

test("the review step renders, which is where the send button lives", async () => {
    // This is the exact screen that threw: it reads `sendError`, `sentLinks`
    // and `submitting`, all of which a refactor had deleted.
    const ui = await mount();
    await ui.openCreate();
    await ui.clickText("Next");
    await ui.clickText("+ Add");
    await ui.clickText("Next");

    // Type mode gives a signature without needing a real canvas.
    await ui.clickText("Type");
    const input = [...dom.window.document.querySelectorAll("input")]
        .find(i => (i.placeholder || "").startsWith("Type your name"));
    assert.ok(input, "the signature pad's typed field is missing");
    const setter = Object.getOwnPropertyDescriptor(
        dom.window.HTMLInputElement.prototype, "value").set;
    await act(async () => {
        setter.call(input, "Test Client");
        input.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
    });

    await ui.clickText("Next");
    assert.ok(ui.text().includes("Signing Order"),
              "the review step did not render");
    assert.ok(ui.text().includes("Sign & Send"),
              "the send button is missing from the review step");
});

/* Board 2 (2026-11-25): started from a matter, /agreements?case=…, the builder
 * is FOR that matter: its lawyer is already a required signer, and the send
 * carries case_id. Without the lawyer the server refuses a linked agreement. */
function startFromMatter(caseId = "K1") {
    globalThis.__nav.params.clear();
    globalThis.__nav.params.set("case", caseId);
    dom.window.history.replaceState(null, "", `/agreements?case=${caseId}`);
}
function leaveMatter() {
    globalThis.__nav.params.clear();
    dom.window.history.replaceState(null, "", "/");
}

test("from a matter: the For bar names it, and its lawyer is a required signer", async () => {
    startFromMatter();
    __respond("getCase", () => ({ data: { _id: "K1", title: "Rent dispute with landlord", case_number: "ATT-0142", lawyer_id: "L7" }, error: null }));
    __respond("listEngagements", () => ({ data: [{ case_id: "K1", lawyer_id: "L7", lawyer_name: "Adv Ayesha Khan", status: "accepted" }], error: null }));
    __respond("previewAgreementBody", () => ({ data: { body_html: "<p>Rent is due on the 5th.</p>", has_text: true }, error: null }));
    __respond("createAgreement", () => ({ data: { _id: "A9", parties: [] }, error: null, status: 201 }));
    try {
        const ui = await mount();
        await act(async () => { await new Promise(r => setTimeout(r, 20)); });
        const bar = host => host.querySelector("[data-agreement-matter]");
        assert.ok(bar(ui.host), "no For bar");
        assert.match(bar(ui.host).textContent, /^Rent dispute with landlord · ATT-0142/);
        assert.match(bar(ui.host).getAttribute("title"), /Adv Ayesha Khan, your lawyer on this matter, signs it too/);   // one-line chip: the lawyer is in its tooltip

        const paper = ui.host.querySelector("[data-ag-paper]");
        await act(async () => { paper.innerHTML = "<p>Rent is due on the 5th.</p>"; paper.dispatchEvent(new dom.window.Event("input", { bubbles: true })); });
        await ui.clickText("Next");
        assert.ok(ui.host.querySelector("[data-signer-required]"), "the lawyer is not marked Required");
        assert.match(ui.text(), /Adv Ayesha Khan/);
        const removes = [...ui.host.querySelectorAll("button")].filter(b => b.textContent.trim() === "Remove");
        assert.equal(removes.length, 0, "the required lawyer can be removed");

        await ui.clickText("Next");   // the lawyer counts as a signer already
        await ui.clickText("Type");
        const input = [...dom.window.document.querySelectorAll("input")].find(i => (i.placeholder || "").startsWith("Type your name"));
        const setter = Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value").set;
        await act(async () => { setter.call(input, "Test Client"); input.dispatchEvent(new dom.window.Event("input", { bubbles: true })); });
        await ui.clickText("Next");
        await act(async () => { await new Promise(r => setTimeout(r, 20)); });
        await ui.clickText("Sign & Send");
        await act(async () => { await new Promise(r => setTimeout(r, 20)); });
        const sent = __calls("createAgreement")[0]?.args[0];
        assert.ok(sent, "nothing was sent");
        assert.equal(sent.case_id, "K1", "the agreement was not linked to the matter");
        assert.deepEqual(sent.party_ids, [{ user_id: "L7" }], "the matter's lawyer is not a signer");
    } finally { leaveMatter(); }
});

test("from a matter with no lawyer: it says so instead of a builder the server would refuse", async () => {
    startFromMatter("K2");
    __respond("getCase", () => ({ data: { _id: "K2", title: "Khula petition", lawyer_id: null }, error: null }));
    try {
        const ui = await mount();
        await act(async () => { await new Promise(r => setTimeout(r, 20)); });
        const note = ui.host.querySelector('[data-agreement-matter-state="no_lawyer"]');
        assert.ok(note, "no 'has no lawyer' notice");
        assert.match(note.textContent, /Khula petition has no lawyer yet/);
        assert.equal(ui.host.querySelector("[data-ag-paper]"), null, "the builder opened anyway");
    } finally { leaveMatter(); }
});

/* Board 4: started from Agreements, "For:" is chosen above step 1. */
const MATTERS = () => {
    __respond("listCases", () => ({ data: { items: [
        { _id: "K1", title: "Rent dispute with landlord", case_number: "ATT-0142", lawyer_id: "L7", status: "in_progress" },
        { _id: "K3", title: "Property transfer", case_number: "ATT-0160", lawyer_id: "L8", status: "open" },
        { _id: "K2", title: "Khula petition", lawyer_id: null, status: "open" },
        { _id: "K4", title: "Old closed matter", lawyer_id: "L7", status: "closed" },
    ], pages: 1 }, error: null }));
    __respond("listEngagements", () => ({ data: [
        { case_id: "K1", lawyer_id: "L7", lawyer_name: "Adv Ayesha Khan", status: "accepted" },
        { case_id: "K3", lawyer_id: "L8", lawyer_name: "Adv Bilal Ahmed", status: "accepted" },
    ], error: null }));
};
const pick = async (caseId) => {
    const sel = dom.window.document.querySelector("[data-agreement-for-select]");
    const setter = Object.getOwnPropertyDescriptor(dom.window.HTMLSelectElement.prototype, "value").set;
    await act(async () => { setter.call(sel, caseId); sel.dispatchEvent(new dom.window.Event("change", { bubbles: true })); });
    await act(async () => {});
};

test("For: lists only live matters with a lawyer, and says which were left out", async () => {
    MATTERS();
    const ui = await mount();
    await ui.openCreate();
    await act(async () => { await new Promise(r => setTimeout(r, 20)); });
    const opts = [...ui.host.querySelectorAll("[data-agreement-for-select] option")].map(o => o.textContent);
    assert.equal(opts[0], "Not linked to a matter");
    assert.equal(opts.length, 3, "a matter without a lawyer, or a closed one, was offered");
    assert.match(opts[1], /Rent dispute with landlord · ATT-0142 — Adv Ayesha Khan signs too/);
    // A COUNT, never the titles: a matter's title is often the client's whole intake question.
    const help = ui.host.querySelector("[data-agreement-for-help]").textContent;
    assert.match(help, /1 matter without a lawyer isn't listed\./);
    assert.doesNotMatch(help, /Khula/);
});

test("For: on step 1 the select sits in the header; later steps show a chip with Change, not the select", async () => {
    MATTERS();
    const ui = await mount();
    await ui.openCreate();
    await act(async () => { await new Promise(r => setTimeout(r, 20)); });
    assert.ok(ui.host.querySelector("[data-agreement-for-slot] [data-agreement-for-select]"), "the select is not in the header slot");
    await ui.clickText("Next");
    assert.equal(ui.host.querySelector("[data-agreement-for-select]"), null, "the select stays on every step");
    const chip = ui.host.querySelector("[data-agreement-unlinked]");
    assert.ok(chip, "no compact chip on step 2");
    assert.match(chip.textContent, /^Not linked to a matter/);
    assert.doesNotMatch(chip.textContent, /standalone/, "the chip is one line now (the standalone note is its tooltip)");
    // Change and Done stand apart from the dark card: the soft brand tint.
    const change = chip.querySelector("[data-agreement-matter-change]");
    assert.match(change.style.background, /brand-soft/);
    await ui.clickText("Change");
    assert.ok(ui.host.querySelector("[data-agreement-for-select]"), "Change does not bring the select back");
    const done = [...ui.host.querySelectorAll("[data-agreement-for] button")].find(b => b.textContent === "Done");
    assert.match(done.style.background, /brand-soft/);
});

test("For: the select and Done sit in one pill like the chip, and the note is one line", async () => {
    const ui = await mount();
    await ui.openCreate();
    await act(async () => { await new Promise(r => setTimeout(r, 20)); });
    await ui.clickText("Next");
    await ui.clickText("Change");
    const pill = ui.host.querySelector("[data-agreement-for-pill]");
    assert.ok(pill, "no pill around the select");
    assert.equal(pill.style.borderRadius, "999px");
    assert.ok(pill.querySelector("[data-agreement-for-select]"), "the select is outside the pill");
    // No dead space before the arrow: the select fits its text instead of filling the slot.
    const sel = pill.querySelector("[data-agreement-for-select]");
    assert.notEqual(sel.style.flex, "1 1 0%", "the select stretches across the slot");
    assert.equal(sel.style.maxWidth, "300px");
    assert.equal(pill.style.display, "inline-flex");
    assert.ok([...pill.querySelectorAll("button")].some(b => b.textContent === "Done"), "Done is outside the pill");
    const help = ui.host.querySelector("[data-agreement-for-help]");
    assert.equal(help.style.whiteSpace, "nowrap", "the note can wrap to a second line");
    assert.equal(help.getAttribute("title"), help.textContent, "the full note is not in the tooltip");
});

test("a long intake-style matter title is cut short in the dropdown", async () => {
    const long = "My name is Imran Ali and I live in Village Chak 45, Tehsil Kasur, District Kasur and my landlord will not return the deposit";
    __respond("listCases", () => ({ data: { items: [{ _id: "K9", title: long, lawyer_id: "L7", status: "open" }], pages: 1 }, error: null }));
    __respond("listEngagements", () => ({ data: [{ case_id: "K9", lawyer_id: "L7", lawyer_name: "Adv A", status: "accepted" }], error: null }));
    const ui = await mount();
    await ui.openCreate();
    await act(async () => { await new Promise(r => setTimeout(r, 20)); });
    const opt = [...ui.host.querySelectorAll("[data-agreement-for-select] option")][1].textContent;
    assert.ok(opt.length < 110, `option too long (${opt.length})`);
    assert.match(opt, /…/);
});

test("signers: Invite by email has an icon (no emoji) and Remove is a full-size button", async () => {
    const ui = await mount();
    await ui.openCreate();
    await ui.clickText("Next");
    const invite = ui.host.querySelector("[data-invite-email]");
    assert.ok(invite.querySelector("svg"), "no icon on Invite by email");
    // Soft brand tint, no border (the chosen style, 2026-11-25).
    assert.match(invite.style.background, /brand-soft/);
    assert.match(invite.style.color, /brand-text/);
    assert.match(invite.style.border, /^(0|none|0px)/);
    assert.doesNotMatch(invite.textContent, /✉/);
    // Before adding: the lawyer row (and its + Add) is still in the list.
    assert.ok(ui.host.querySelector(".ag-pick .ag-add"), "a lawyer row's + Add has no hover state");
    await ui.clickText("+ Add");
    const remove = ui.host.querySelector("[data-remove-signer]");
    assert.ok(remove, "no Remove button");
    assert.equal(remove.style.height, "34px");
    // Destructive: the theme's danger colour.
    assert.match(remove.style.color, /--danger/);
    // Hover / press feedback (2026-11-25): each action carries its class, and the rules exist.
    assert.ok(invite.classList.contains("ag-tint"), "Invite by email has no hover state");
    assert.ok(remove.classList.contains("ag-danger"), "Remove has no hover state");
    const rules = [...ui.host.querySelectorAll("style")].map(s => s.textContent).join("\n");
    for (const sel of [".ag-tint:hover", ".ag-danger:hover", ".ag-pick:hover", ".ag-back:hover"]) {
        assert.ok(rules.includes(sel), `no ${sel} rule`);
    }
    assert.doesNotMatch(rules, /\.ag-back:hover\{background:#3ee0a1/, "the back button still flashes a hard-coded mint");
    assert.match(remove.style.background, /--danger-soft/);
    // The title edits in place at the width of its text, not a 560px box on focus.
    const css = [...ui.host.querySelectorAll("style")].map(s => s.textContent).join("\n");
    assert.match(css, /\.ag-title\{[^}]*field-sizing:content/);
    assert.doesNotMatch(css, /\.ag-title\{[^}]*[;{]width:min\(560px/, "a fixed 560px width (max-width is fine)");
});

test("For: every page of matters is read, not just the first 500", async () => {
    // 12 pages of 50: the old reader stopped silently after page 10.
    __respond("listCases", ({ page } = {}) => ({ data: { items: [
        { _id: `P${page}`, title: `Matter on page ${page}`, case_number: `N-${page}`, lawyer_id: "L7", status: "open" },
    ], pages: 12 }, error: null }));
    __respond("listEngagements", () => ({ data: [], error: null }));
    const { loadMatterOptions } = await import("../src/components/client/ModAgreements.jsx");
    const r = await loadMatterOptions();
    assert.equal(r.state, "ready");
    assert.ok(r.options.some(o => o.caseId === "P12"), "a matter after page 10 was dropped");
    assert.equal(r.truncated, false);
    assert.equal(__calls("listCases").length, 12);
});

test("For: choosing a matter adds its lawyer as Required; switching swaps the lawyer and keeps others; Not linked removes them", async () => {
    MATTERS();
    const ui = await mount();
    await ui.openCreate();
    await act(async () => { await new Promise(r => setTimeout(r, 20)); });
    await pick("K1");
    assert.match(ui.host.querySelector("[data-agreement-matter]").textContent, /^Rent dispute with landlord/);
    await ui.clickText("Next");
    await ui.clickText("+ Add");                       // a hand-added signer (Adv Verified)
    // The signers step only, not the For dropdown (its options name every lawyer).
    const signersText = () => ui.text().replace(ui.host.querySelector("[data-agreement-for]")?.textContent || "", "");
    assert.ok(ui.host.querySelector("[data-signer-required]"));
    assert.match(signersText(), /Adv Ayesha Khan/);
    assert.match(signersText(), /Adv Verified/);

    await ui.clickText("Change");
    await pick("K3");
    await confirmChange();
    assert.match(signersText(), /Adv Bilal Ahmed/);
    assert.doesNotMatch(signersText(), /Adv Ayesha Khan/, "the old matter's lawyer stayed");
    assert.match(signersText(), /Adv Verified/, "a hand-added signer was dropped");
    assert.equal(ui.host.querySelectorAll("[data-signer-required]").length, 1);

    await ui.clickText("Change");
    await pick("");
    await confirmChange();
    assert.equal(ui.host.querySelector("[data-signer-required]"), null);
    assert.doesNotMatch(signersText(), /Adv Bilal Ahmed/);
    assert.match(signersText(), /Adv Verified/);
});

/* Board 5: changing a matter already chosen says what changes, and waits. */
const dialog = () => dom.window.document.querySelector("[data-change-matter]");
const press = async (el) => { assert.ok(el, "nothing to press"); await act(async () => { el.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); }); await act(async () => {}); };
async function confirmChange() { await press(dialog()?.querySelector("[data-change-confirm]")); }

test("Change matter: the dialog names who goes, who comes in, and who stays — and nothing changes until yes", async () => {
    MATTERS();
    const ui = await mount();
    await ui.openCreate();
    await act(async () => { await new Promise(r => setTimeout(r, 20)); });
    await pick("K1");
    assert.equal(dialog(), null, "the first choice should not ask (nothing is taken away)");
    await ui.clickText("Next");
    await ui.clickText("+ Add");
    await ui.clickText("Change");
    await pick("K3");

    const d = dialog();
    assert.ok(d, "no confirm before changing the matter");
    assert.match(d.textContent, /Link it to "Property transfer" instead\?/);
    assert.match(d.querySelector("[data-change-removed]").textContent, /Adv Ayesha Khan is removed/);
    assert.match(d.querySelector("[data-change-added]").textContent, /Adv Bilal Ahmed is added as a required signer/);
    assert.match(d.querySelector("[data-change-kept]").textContent, /Adv Verified stays/);
    // Still the old matter while the question is open.
    assert.match(ui.host.querySelector("[data-agreement-matter]")?.textContent || ui.host.querySelector("[data-agreement-for-select]").value, /Rent dispute|K1/);

    await press(d.querySelector("[data-change-keep]"));
    assert.equal(dialog(), null);
    const signers = ui.text().replace(ui.host.querySelector("[data-agreement-for]")?.textContent || "", "");
    assert.match(signers, /Adv Ayesha Khan/, "Keep changed the signers anyway");
    assert.doesNotMatch(signers, /Adv Bilal Ahmed/);
});

test("Change matter: back to Not linked asks too, and says the link goes", async () => {
    MATTERS();
    const ui = await mount();
    await ui.openCreate();
    await act(async () => { await new Promise(r => setTimeout(r, 20)); });
    await pick("K1");
    await ui.clickText("Change");
    await pick("");
    const d = dialog();
    assert.ok(d);
    assert.match(d.textContent, /Send it without a matter\?/);
    assert.match(d.querySelector("[data-change-removed]").textContent, /Adv Ayesha Khan is removed/);
    assert.equal(d.querySelector("[data-change-added]"), null);
    await confirmChange();
    assert.equal(ui.host.querySelector("[data-agreement-matter]"), null);
});

test("For: no room for the matter's lawyer leaves everything as it was and says why", async () => {
    MATTERS();
    __respond("searchLawyers", () => ({ data: { items: [
        { _id: "L9", full_name: "Adv Verified", specializations: ["civil"] },
        { _id: "L10", full_name: "Adv Second", specializations: ["civil"] },
    ] }, error: null, status: 200 }));
    const ui = await mount();
    await ui.openCreate();
    await act(async () => { await new Promise(r => setTimeout(r, 20)); });
    await ui.clickText("Next");
    await ui.clickText("+ Add");
    await ui.clickText("+ Add");                       // two signers: full
    await ui.clickText("Change");                      // past step 1 the select is behind Change
    await pick("K1");
    assert.match(ui.host.querySelector("[data-agreement-for-note]").textContent, /Adv Ayesha Khan must sign an agreement on "Rent dispute with landlord"\. Remove a signer first/);
    assert.equal(ui.host.querySelector("[data-agreement-matter]"), null, "linked anyway");
    assert.equal(ui.host.querySelector("[data-signer-required]"), null);
});

/* Board 6: Review says what it is linked to; after sending, back where they started. */
async function writeSignAndReview(ui) {
    const paper = ui.host.querySelector("[data-ag-paper]");
    await act(async () => { paper.innerHTML = "<p>Rent is due on the 5th.</p>"; paper.dispatchEvent(new dom.window.Event("input", { bubbles: true })); });
    await ui.clickText("Next");
    await ui.clickText("Next");
    await ui.clickText("Type");
    const input = [...dom.window.document.querySelectorAll("input")].find(i => (i.placeholder || "").startsWith("Type your name"));
    const setter = Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value").set;
    await act(async () => { setter.call(input, "Test Client"); input.dispatchEvent(new dom.window.Event("input", { bubbles: true })); });
    await ui.clickText("Next");
    await act(async () => { await new Promise(r => setTimeout(r, 20)); });
}
const SENT_TO_LAWYER = () => __respond("createAgreement", () => ({ data: { _id: "A9", parties: [],
    account_notifications: [{ user_id: "L7", full_name: "Adv Ayesha Khan", in_app: true, emailed: false, reason: "email_not_configured" }] }, error: null, status: 201 }));
const pressIn = async (sel) => {
    const el = dom.window.document.querySelector(sel);
    assert.ok(el, `no ${sel}`);
    await act(async () => { el.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
    await act(async () => {});
};

test("Review shows Linked to … with Change; from a matter, the sent screen leads Back to matter", async () => {
    startFromMatter();
    __respond("getCase", () => ({ data: { _id: "K1", title: "Rent dispute with landlord", case_number: "ATT-0142", lawyer_id: "L7" }, error: null }));
    __respond("listEngagements", () => ({ data: [{ case_id: "K1", lawyer_id: "L7", lawyer_name: "Adv Ayesha Khan", status: "accepted" }], error: null }));
    __respond("previewAgreementBody", () => ({ data: { body_html: "<p>Rent is due on the 5th.</p>", has_text: true }, error: null }));
    SENT_TO_LAWYER();
    try {
        const ui = await mount();
        await act(async () => { await new Promise(r => setTimeout(r, 20)); });
        await writeSignAndReview(ui);
        const linked = ui.host.querySelector("[data-review-linked]");
        assert.ok(linked, "Review does not say what it is linked to");
        assert.match(linked.textContent, /Linked to\s*Rent dispute with landlord · ATT-0142/);
        assert.ok(linked.querySelector("[data-review-change]"));

        await ui.clickText("Sign & Send");
        await act(async () => { await new Promise(r => setTimeout(r, 20)); });
        assert.ok(dom.window.document.querySelector("[data-sent-back-to-agreements]"));
        await pressIn("[data-sent-back-to-matter]");
        assert.equal(globalThis.__nav.pushed.at(-1), "/tracking?case=K1&tab=documents&agreement=A9", "not back on the matter with the new agreement highlighted");
    } finally { leaveMatter(); }
});

test("linked from Agreements: the sent screen offers Done (the list) and Open matter", async () => {
    MATTERS();
    __respond("previewAgreementBody", () => ({ data: { body_html: "<p>Rent is due on the 5th.</p>", has_text: true }, error: null }));
    SENT_TO_LAWYER();
    const ui = await mount();
    await ui.openCreate(null);
    await act(async () => { await new Promise(r => setTimeout(r, 20)); });
    await pick("K1");
    await writeSignAndReview(ui);
    await ui.clickText("Sign & Send");
    await act(async () => { await new Promise(r => setTimeout(r, 20)); });
    assert.equal(dom.window.document.querySelector("[data-sent-back-to-matter]"), null, "they did not come from the matter");
    assert.ok(dom.window.document.querySelector("[data-sent-done]"));
    await pressIn("[data-sent-open-matter]");
    assert.equal(globalThis.__nav.pushed.at(-1), "/tracking?case=K1&tab=documents&agreement=A9", "not back on the matter with the new agreement highlighted");
});

/* ONE SWITCH (2026-11-25): the server's. Off there = no builder anywhere here,
 * including a /agreements?case=… link -- never a wizard whose send would 403. */
test("builder off on the server: no New agreement, and ?case= does not open a builder", async () => {
    signedIn(false);
    startFromMatter();
    __respond("getCase", () => ({ data: { _id: "K1", title: "Rent dispute", lawyer_id: "L7" }, error: null }));
    try {
        const ui = await mount();
        await act(async () => { await new Promise(r => setTimeout(r, 20)); });
        assert.equal(ui.host.querySelector("[data-ag-paper]"), null, "a builder opened while the server has it off");
        assert.equal(ui.host.querySelector("[data-agreement-matter]"), null);
        assert.doesNotMatch(ui.text(), /New agreement|Create an agreement/);
        assert.equal(__calls("getAgreementCapabilities").length > 0, true, "the server was not asked");
    } finally { leaveMatter(); }
});

test("a failed capabilities read hides the builder (fail closed) and is asked again next time", async () => {
    __respond("getAgreementCapabilities", () => ({ data: null, error: { message: "offline" }, status: 0 }));
    let ui = await mount();
    await act(async () => { await new Promise(r => setTimeout(r, 20)); });
    assert.doesNotMatch(ui.text(), /New agreement|Create an agreement/);
    const asked = __calls("getAgreementCapabilities").length;
    signedIn(true);
    ui = await mount();
    await act(async () => { await new Promise(r => setTimeout(r, 20)); });
    assert.ok(__calls("getAgreementCapabilities").length > asked, "a failure was remembered as 'off'");
    assert.match(ui.text(), /New agreement|Create an agreement/);
});

test("standalone (no ?case=): no For bar, no required signer, no case_id", async () => {
    const ui = await mount();
    await ui.openCreate();
    assert.equal(ui.host.querySelector("[data-agreement-matter]"), null);
    await ui.clickText("Next");
    assert.equal(ui.host.querySelector("[data-signer-required]"), null);
});

/* The Overview's typefaces for the whole module (2026-11-25): body in the
 * client theme's Hanken Grotesk, page titles in Nunito Sans -- not the
 * all-Nunito it had, which read differently from the dashboard. */
test("the Agreements module uses the Overview's fonts, set once at its root", async () => {
    const ui = await mount();
    const root = ui.host.querySelector("[data-ag-font]");
    assert.ok(root, "no font root");
    assert.equal(ui.host.querySelectorAll("[data-ag-font]").length, 1, "font rule set in more than one place");
    const css = [...root.querySelectorAll("style")].map(s => s.textContent).join("\n");
    assert.match(css, /\[data-ag-font\][^{]*\{\s*font-family:\s*"Hanken Grotesk"/, "body text is not the Overview's Hanken Grotesk");
    assert.match(css, /\[data-ag-font\] h1[^{]*\{\s*font-family:\s*'Nunito Sans'/, "page titles are not Nunito Sans like the Overview heading");
    assert.match(css, /:not\(\[data-keep-font\]\)/, "the agreement's own text would be forced too");
});

/* B1 + C2 (2026-11-25): no emoji icons on any step of the builder; the typed
 * signature keeps its script face under the builder's forced typeface. */
test("no step of the builder uses emoji as icons", async () => {
    __respond("previewAgreementBody", () => ({ data: { body_html: "<p>Fees are 40% of recovery.</p>", has_text: true }, error: null }));
    const ui = await mount();
    await ui.openCreate();
    const EMOJI = /[\u{1F300}-\u{1FAFF}✅⏰✍⚖✉⚠]/u;
    const seen = [];
    const look = (label) => { if (EMOJI.test(ui.text())) seen.push(label); };
    look("edit");
    await ui.clickText("Next"); look("signers");
    await ui.clickText("+ Add");
    await ui.clickText("Next"); look("signature");
    await ui.clickText("Type");
    const input = [...dom.window.document.querySelectorAll("input")].find(i => (i.placeholder || "").startsWith("Type your name"));
    const setter = Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value").set;
    await act(async () => { setter.call(input, "Test Client"); input.dispatchEvent(new dom.window.Event("input", { bubbles: true })); });
    await ui.clickText("Next");
    await act(async () => { await new Promise(r => setTimeout(r, 20)); });
    look("review");
    assert.deepEqual(seen, [], `emoji on: ${seen.join(", ")}`);
    const typed = [...ui.host.querySelectorAll("span")].find(s => s.textContent === "Test Client" && /cursive/.test(s.style.fontFamily));
    assert.ok(typed?.closest("[data-keep-font]"), "the typed signature would be forced into the UI font");
});

test("the signature pad offers all three methods inside the builder", async () => {
    const ui = await mount();
    await ui.openCreate();
    await ui.clickText("Next");
    await ui.clickText("+ Add");
    await ui.clickText("Next");

    const text = ui.text();
    for (const mode of ["Draw", "Type", "Upload"]) {
        assert.ok(text.includes(mode), `the pad is missing the ${mode} tab`);
    }
});

// ── the All Agreements table renders with its new columns ──────────────────

function listWith(rows) {
    __respond("listAgreements", () => ({
        data: { items: rows, total: rows.length, page: 1, page_size: 20, pages: 1 },
        error: null, status: 200,
    }));
}

const ok = (data) => ({ data, error: null, status: 200 });
const fullRow = () => row();

const row = (over = {}) => ({
    id: "A1", _id: "A1", title: "NDA", status: "pending",
    created_by: ME, version: 1,
    signed_count: 1, total_parties: 3,
    parties: [
        { user_id: ME, full_name: "Test Client", signed: true },
        { user_id: "U2", full_name: "Adv Khan", signed: false },
        { party_id: "P3", email: "guest@example.pk", external: true, signed: false },
    ],
    created_at: "2026-09-26T00:00:00Z",
    ...over,
});

test("the list renders every column header", async () => {
    listWith([row()]);
    const ui = await mount();
    await ui.openPage("all");

    for (const h of ["DOCUMENT", "PARTIES", "STATUS", "PROGRESS", "ACTIONS"]) {
        assert.ok(ui.text().includes(h), `the ${h} column header is missing`);
    }
});

/* Board 7 (2026-11-25): each row names its matter; the list filters by matter
 * on the SERVER (case_id), like the status filter. */
test("each row shows its matter by name, or Not linked — never a raw id", async () => {
    MATTERS();
    listWith([row({ id: "A1", _id: "A1", title: "Rent agreement", case_id: "K1" }),
              row({ id: "A2", _id: "A2", title: "Car sale receipt", case_id: null }),
              row({ id: "A3", _id: "A3", title: "Someone else's matter", case_id: "ZZZ-raw-id" })]);
    const ui = await mount();
    await ui.openPage("all");
    await act(async () => { await new Promise(r => setTimeout(r, 20)); });
    const chip = id => ui.host.querySelector(`[data-agreement="${id}"] [data-matter-chip]`).textContent;
    assert.equal(chip("A1"), "Rent dispute with landlord");
    assert.equal(chip("A2"), "Not linked");
    assert.equal(chip("A3"), "On a matter", "an unknown matter must not show its raw id");
    assert.doesNotMatch(ui.text(), /ZZZ-raw-id/);
});

test("the Matter filter asks the server for that matter only", async () => {
    MATTERS();
    listWith([row()]);
    const ui = await mount();
    await ui.openPage("all");
    await act(async () => { await new Promise(r => setTimeout(r, 20)); });
    const sel = ui.host.querySelector("[data-matter-filter]");
    assert.ok(sel, "no Matter filter");
    const names = [...sel.querySelectorAll("option")].map(o => o.textContent);
    assert.equal(names[0], "All matters");
    assert.ok(names.includes("Rent dispute with landlord"));
    const setter = Object.getOwnPropertyDescriptor(dom.window.HTMLSelectElement.prototype, "value").set;
    await act(async () => { setter.call(sel, "K1"); sel.dispatchEvent(new dom.window.Event("change", { bubbles: true })); });
    await act(async () => { await new Promise(r => setTimeout(r, 20)); });
    const last = __calls("listAgreements").at(-1).args[0];
    assert.equal(last.case_id, "K1", "the matter filter was not sent to the server");
    assert.equal(last.page, 1, "a new filter must start from page 1");
    await act(async () => { setter.call(sel, ""); sel.dispatchEvent(new dom.window.Event("change", { bubbles: true })); });
    await act(async () => { await new Promise(r => setTimeout(r, 20)); });
    assert.equal(__calls("listAgreements").at(-1).args[0].case_id, null);
    assert.equal(__calls("listAgreements").at(-1).args[0].unlinked, undefined);

    // "Not linked to a matter": the server's unlinked filter, never a fake case id.
    assert.equal(names[1], "Not linked to a matter");
    const notLinked = sel.querySelectorAll("option")[1].value;
    await act(async () => { setter.call(sel, notLinked); sel.dispatchEvent(new dom.window.Event("change", { bubbles: true })); });
    await act(async () => { await new Promise(r => setTimeout(r, 20)); });
    const nl = __calls("listAgreements").at(-1).args[0];
    assert.equal(nl.unlinked, true);
    assert.equal(nl.case_id, undefined, "Not linked must not send a case_id");
});

/* "Network error" over a list that was fine a second later (2026-11-25): a
 * read that cannot reach the server is retried once, quietly. */
test("the list retries once when the server could not be reached, and shows no error", async () => {
    const ui = await mount();          // the dashboard reads first; count from here
    let calls = 0;
    __respond("listAgreements", () => (++calls === 1
        ? { data: null, error: { message: "Network error. Please check your connection." }, status: 0 }
        : { data: { items: [row()], total: 1, page: 1, page_size: 25, pages: 1 }, error: null, status: 200 }));
    await ui.openPage("all");
    await act(async () => { await new Promise(r => setTimeout(r, 1700)); });
    assert.equal(calls, 2, "no retry after a network failure");
    assert.equal(ui.host.querySelector("[data-agreements-error]"), null, "the error stayed after a successful retry");
    assert.match(ui.text(), /NDA/);
});

test("a real error (not a network blip) is shown at once, without a retry", async () => {
    const ui = await mount();
    let calls = 0;
    __respond("listAgreements", () => { calls += 1; return { data: null, error: { message: "Forbidden" }, status: 403 }; });
    await ui.openPage("all");
    await act(async () => { await new Promise(r => setTimeout(r, 50)); });
    assert.ok(ui.host.querySelector("[data-agreements-error]"));
    assert.equal(calls, 1);
});

test("dropdown options use the theme's colours (the native list drew white)", async () => {
    const ui = await mount();
    const css = [...ui.host.querySelectorAll("[data-ag-font] style")].map(s => s.textContent).join("\n");
    assert.match(css, /select option\s*\{[^}]*background:\s*var\(--surface/);
    assert.match(css, /select option\s*\{[^}]*color:\s*var\(--ink/);
});

test("a row shows its title, progress and party labels", async () => {
    listWith([row()]);
    const ui = await mount();
    await ui.openPage("all");

    const text = ui.text();
    assert.ok(text.includes("NDA"), "the document title is missing");
    // Three parties, one signed -- the count comes from the server's own
    // signed_count/total_parties, not from counting the rows client-side.
    assert.ok(text.includes("1/3"), "the progress count is missing or wrong");
    assert.ok(text.includes("Sender"), "the sender label is missing");
    assert.ok(/Recipients \(2\)/.test(text),
              "a three-party agreement must not be shown as one recipient");
});

test("an agreement waiting on you reads as Needs you", async () => {
    // Derived from needsMySig, not a stored status: pending AND unsigned by me.
    listWith([row({
        parties: [
            { user_id: ME, full_name: "Test Client", signed: false },
            { user_id: "U2", full_name: "Adv Khan", signed: true },
        ],
        signed_count: 1, total_parties: 2,
    })]);
    const ui = await mount();
    await ui.openPage("all");

    assert.ok(ui.text().includes("Needs you"),
              "an agreement awaiting my signature should say so");
    assert.ok(ui.text().includes("Sign"), "it should offer the sign action");
});

test("an executed agreement is not marked as needing you", async () => {
    listWith([row({
        status: "executed", signed_count: 2, total_parties: 2,
        parties: [
            { user_id: ME, full_name: "Test Client", signed: true },
            { user_id: "U2", full_name: "Adv Khan", signed: true },
        ],
    })]);
    const ui = await mount();
    await ui.openPage("all");

    assert.ok(ui.text().includes("Signed"));
    assert.ok(!ui.text().includes("Needs you"));
    assert.ok(ui.text().includes("2/2"));
});

test("the total is stated, so a full page does not look like the whole list", async () => {
    __respond("listAgreements", () => ({
        data: { items: [row()], total: 25, page: 1, page_size: 20, pages: 2 },
        error: null, status: 200,
    }));
    const ui = await mount();
    await ui.openPage("all");

    assert.ok(/Showing 1 of 25/.test(ui.text()),
              "the row count must name the total, not just what is loaded");
});

// ── the row action menu ────────────────────────────────────────────────────

test("the menu opens and offers open + remove", async () => {
    listWith([row()]);
    const ui = await mount();
    await ui.openPage("all");

    assert.ok(!ui.text().includes("Remove from my list"),
              "the menu should start closed");
    await ui.clickText("⋮");

    assert.ok(ui.text().includes("Open"), "the menu is missing Open");
    assert.ok(ui.text().includes("Remove from my list"),
              "the menu is missing the remove action");
});

test("it says Remove from my list, never Delete", async () => {
    // A sent agreement is a record the other parties hold too; the server's
    // delete_draft refuses anything except an unsent draft for that reason.
    // The wording has to match what actually happens.
    listWith([row()]);
    const ui = await mount();
    await ui.openPage("all");
    await ui.clickText("⋮");

    const text = ui.text();
    assert.ok(!/\bDelete\b/.test(text),
              "the menu must not offer a delete it cannot perform");
    assert.ok(text.includes("Remove from my list"));
});

test("Download PDF is offered only once the agreement is executed", async () => {
    // The server refuses a PDF before every party has signed, so offering it
    // earlier would be an action that always fails.
    listWith([row()]);                       // pending
    let ui = await mount();
    await ui.openPage("all");
    await ui.clickText("⋮");
    assert.ok(!ui.text().includes("Download PDF"),
              "a pending agreement must not offer a download");

    __reset(); signedIn();
    listWith([row({ status: "executed", signed_count: 2, total_parties: 2 })]);
    ui = await mount();
    await ui.openPage("all");
    await ui.clickText("⋮");
    assert.ok(ui.text().includes("Download PDF"),
              "an executed agreement should offer its PDF");
});

test("removing calls archive, not any delete endpoint", async () => {
    listWith([row()]);
    let archived = null;
    __respond("archiveAgreement", (id) => { archived = id; return ok(fullRow()); });

    const ui = await mount();
    await ui.openPage("all");
    await ui.clickText("⋮");
    await ui.clickText("Remove from my list");

    assert.equal(archived, "A1", "the archive endpoint was not called");
});

test("the Archived view asks the server for archived rows", async () => {
    const seen = [];
    __respond("listAgreements", (args) => {
        seen.push(args || {});
        return { data: { items: [], total: 0, page: 1, page_size: 20, pages: 1 },
                 error: null, status: 200 };
    });
    const ui = await mount();
    await ui.openPage("all");
    await ui.clickText("Archived");

    assert.ok(seen.some(a => a.archived === true),
              "switching to Archived must request archived rows");
    // And it must not also send a status, or it would show only one of them.
    const archivedCall = seen.find(a => a.archived === true);
    assert.ok(!archivedCall.status,
              "Archived is a view across all statuses, not a status itself");
});

// ── the rich editor (2026-10-11) ────────────────────────────────────────────
//
// The body is `body_format: "html"`. The plain-text line tools that were
// tested here (case, duplicate, move, find and replace) went with the plain
// text editor; formatting is the browser's editing commands, which jsdom does
// not implement, so these tests pin the parts that are ours: the controls, the
// template's arrival, Insert, the sticky bar, and that Review sends exactly the
// server's canonical text, as html.

const paperOf = (ui) => ui.host.querySelector("[data-ag-paper]");

test("the editor is a rich, editable page", async () => {
    listWith([]);
    const ui = await mount();
    await ui.openCreate("");
    const paper = paperOf(ui);
    assert.ok(paper, "the editable page is missing");
    assert.equal(paper.getAttribute("contenteditable"), "true");
    assert.ok(!ui.host.querySelector("textarea"), "the plain-text box should be gone");
});

test("every formatting control is there and named", async () => {
    listWith([]);
    const ui = await mount();
    await ui.openCreate("");
    const titles = new Set([...ui.host.querySelectorAll("[data-ag-tb] button[title]")].map(b => b.title));
    for (const t of ["Undo", "Redo", "Bold", "Italic", "Underline", "Subscript", "Superscript",
                     "Strikethrough", "Align left", "Centre", "Align right", "Justify",
                     "Bulleted list", "Numbered list", "Heading 1", "Heading 2", "Heading 3",
                     "Quote", "Link", "Divider", "Clear formatting"]) {
        assert.ok(titles.has(t), `the toolbar is missing ${t}`);
    }
    assert.ok(ui.host.querySelector('button[aria-label="Font"]'), "no font picker");
    assert.ok(ui.host.querySelector('button[aria-label="Text size"]'), "no size picker");
    assert.ok(ui.host.querySelector('input[type="color"]'), "no colour picker");
    assert.ok(/300,000/.test(ui.text()), "the size limit is not shown");
});

test("the toolbar sticks while the page scrolls", async () => {
    listWith([]);
    const ui = await mount();
    await ui.openCreate("");
    const css = [...ui.host.querySelectorAll("style")].map(x => x.textContent).join("");
    assert.match(css, /\[data-ag-tb\]\{position:sticky;top:0/);
});

test("a template's text arrives as escaped paragraphs", async () => {
    listWith([]);
    const ui = await mount();
    await ui.openPage("templates");
    await ui.clickText("Employment Contract");
    const html = paperOf(ui).innerHTML;
    assert.ok(html.startsWith("<p>[UNREVIEWED SAMPLE - NOT LEGAL CONTENT]</p>"),
              "each line of the template should be its own paragraph");
});

test("Insert puts a placeholder into the text", async () => {
    listWith([]);
    const ui = await mount();
    await ui.openCreate("<p>Between</p>");
    await ui.clickText("Insert");
    await ui.clickText("[PARTY NAME]");
    assert.ok(paperOf(ui).textContent.includes("[PARTY NAME]"));
});

test("the font picker offers its families, each in its own face", async () => {
    listWith([]);
    const ui = await mount();
    await ui.openCreate("");
    const picker = ui.host.querySelector('button[aria-label="Font"]');
    await act(async () => { picker.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
    const opts = [...dom.window.document.querySelectorAll('[role="listbox"][aria-label="Font"] [role="option"]')];
    assert.ok(opts.length >= 9, `only ${opts.length} fonts offered`);
    assert.ok(opts.some(o => o.textContent.includes("Verdana") && /Verdana/.test(o.getAttribute("style") || "")));
});

test("the title is edited in the header, not in a separate box", async () => {
    listWith([]);
    const ui = await mount();
    await ui.openCreate("");
    const field = ui.host.querySelector('input[aria-label="Agreement title"]');
    assert.ok(field, "the header title field is missing");
    assert.ok(!ui.text().includes("Agreement Title"), "the old title box is still there");
});

test("the first step will not move on without words", async () => {
    listWith([]);
    const ui = await mount();
    await ui.openCreate("<p><br></p>");
    await ui.clickText("Next");
    assert.ok(!/Search (verified )?lawyers|Loading (verified )?lawyers/.test(ui.text() + [...document.querySelectorAll("input")].map(i => i.placeholder).join(" ")),
        "it moved on with an empty agreement");
});

async function toReview(ui) {
    await ui.clickText("Next");
    await ui.clickText("+ Add");
    await ui.clickText("Next");
    await ui.clickText("Type");
    const input = [...dom.window.document.querySelectorAll("input")]
        .find(i => (i.placeholder || "").startsWith("Type your name"));
    const setter = Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value").set;
    await act(async () => {
        setter.call(input, "Test Client");
        input.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
    });
    await ui.clickText("Next");
    await act(async () => {});
}

test("Review shows the server's canonical text and sends exactly that, as html", async () => {
    listWith([]);
    __respond("previewAgreementBody", () => ok({ body_html: "<p>CANONICAL <b>TEXT</b></p>", has_text: true }));
    __respond("createAgreement", () => ({ data: null, error: { message: "stop here" }, status: 400 }));
    const ui = await mount();
    await ui.openCreate('<p onclick="x()">raw</p>');
    await toReview(ui);

    assert.equal(__calls("previewAgreementBody").at(-1).args[0], '<p onclick="x()">raw</p>',
                 "Review must ask the server for the canonical form of what was written");
    assert.ok(ui.text().includes("CANONICAL TEXT"), "Review must show the server's form");

    await ui.clickText("Sign & Send");
    const sent = __calls("createAgreement").at(-1)?.args[0];
    assert.ok(sent, "nothing was sent");
    assert.equal(sent.body_html, "<p>CANONICAL <b>TEXT</b></p>");
    assert.equal(sent.body_format, "html");
});

test("a body the server could not check is not sent", async () => {
    listWith([]);
    __respond("previewAgreementBody", () => ({ data: null, error: { message: "Could not check" }, status: 500 }));
    const ui = await mount();
    await ui.openCreate();
    await toReview(ui);
    assert.ok(ui.text().includes("Could not check"));
    await ui.clickText("Sign & Send");
    assert.equal(__calls("createAgreement").length, 0, "an unchecked body was sent");
});
