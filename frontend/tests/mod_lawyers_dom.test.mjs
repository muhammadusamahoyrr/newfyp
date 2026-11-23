/* ModLawyers — the real component, mounted.
 *
 * The backend matcher has 83 tests. This file had none, and the defects that
 * mattered most to a user were all on this side of the wire: a fabricated
 * `BAR-API-001` shown as a bar council registration number, "null km" printed
 * as a distance, a "Find Nearby" button with no handler, and a constant
 * "Mon–Fri: 9am–5pm" presented as each lawyer's own office hours. None of those
 * are visible from a backend test, and `next build` proving the file parses is
 * not the same as knowing what it renders.
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
                    "Element", "Node", "Event", "CustomEvent",
                    "MutationObserver", "getComputedStyle", "localStorage",
                    "requestAnimationFrame", "cancelAnimationFrame"]) {
    define(name, dom.window[name]);
}
define("IS_REACT_ACT_ENVIRONMENT", true);

/* Component code uses the GLOBAL timers, which `window.close()` does not
 * release — the process then outlives the runner with every test passing.
 * Same tracking as mod_documents_dom. */
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

/* Set a controlled input's value the way a user does.
 *
 * React installs its own `value` setter on the element and tracks the last
 * value it wrote; assigning `el.value` directly updates the DOM but leaves that
 * tracker unchanged, so React treats the following `input` event as a no-op and
 * the component never re-renders. Going through the prototype setter is what
 * makes the change visible to React.
 */
function setNativeValue(el, value) {
    const proto = Object.getPrototypeOf(el);
    const desc = Object.getOwnPropertyDescriptor(proto, "value");
    if (desc && desc.set) desc.set.call(el, value);
    else el.value = value;
}

/* A lawyer as the BACKEND actually returns one: `lawyer_profile` is a
 * pass-through dict, so absent fields are simply absent. The fabrication bugs
 * all lived in what the UI substituted for these. */
function lawyer(id, over = {}) {
    return {
        _id: id,
        full_name: `Adv ${id}`,
        role: "lawyer",
        province: "punjab",
        is_active: true,
        lawyer_profile: {
            specializations: ["criminal"],
            rating: 4.5,
            total_reviews: 5,
            availability: true,
            experience_years: 10,
            ...over,
        },
    };
}

async function mountLawyers() {
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
              h(HeaderActionsCtx.Provider,
                { value: { setHeaderActions: () => {} } },
                h(ToastContainer, { theme: DARK },
                  h(CaseProvider, null, h(ModLawyers)))))));
    });
    await act(async () => { await new Promise(r => setTimeout(r, 30)); });
    return {
        container,
        text: () => container.textContent,
        settle: async (ms = 60) => {
            await act(async () => { await new Promise(r => setTimeout(r, ms)); });
        },
        unmount: async () => { await act(async () => root.unmount()); },
    };
}

/* My Hire Requests moved to Tracking (2026-11-23) as its own component. */
async function mountHireRequests() {
    const { default: HireRequests } = await import("../src/components/client/HireRequests.jsx");
    const { ToastContainer } = await import("../src/components/shared/Toast.jsx");
    const { DARK } = await import("../src/components/admin/themes.js");
    const { ThemeCtx } = await import("../src/components/client/theme.js");
    const container = dom.window.document.createElement("div");
    dom.window.document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => {
        root.render(h(ThemeCtx.Provider, { value: DARK },
            h(ToastContainer, { theme: DARK }, h(HireRequests))));
    });
    await act(async () => { await new Promise(r => setTimeout(r, 30)); });
    return {
        container,
        unmount: async () => { await act(async () => root.unmount()); },
    };
}

/* Click through to a lawyer's profile.
 *
 * Several fields the fabrication bugs lived in — office hours, bar number,
 * reviews — appear ONLY on the profile view, so a list-only assertion about
 * them cannot fail and proves nothing. Finds the lawyer's name and clicks the
 * nearest ancestor carrying a click handler.
 */
async function openProfile(ui) {
    const nameNode = [...ui.container.querySelectorAll("div")]
        .reverse()
        .find(el => /^Adv /.test(el.textContent.trim())
                    && el.children.length === 0);
    assert.ok(nameNode, "no lawyer card was rendered to open");

    let node = nameNode;
    for (let i = 0; i < 8 && node; i++) {
        await act(async () => {
            node.dispatchEvent(new dom.window.MouseEvent(
                "click", { bubbles: true, cancelable: true }));
        });
        await ui.settle(30);
        if (/Working Hours|Bar No:/.test(ui.text())) return;
        node = node.parentElement;
    }
    throw new Error("could not open the lawyer profile view");
}

test.beforeEach(() => {
    api.__reset();
    api.__respond("bootstrapAuth", true);
    api.__respond("getMe", { data: { _id: "u1", role: "client" } });
    api.__respond("listCases", { data: [] });
    api.__respond("listEngagements", { data: [] });
});

test.after(() => {
    for (const id of liveTimers) { realClearInterval(id); realClearTimeout(id); }
    liveTimers.clear();
    dom.window.close();
});

/* ── fabricated data ──────────────────────────────────────────────────────── */

test("a lawyer with no bar number is not given a generated one", async () => {
    // THE defect. `BAR-API-${idx+1}` was displayed as a bar council
    // registration number for a real, KYC-verified advocate — and numbered by
    // position in the page, so the same lawyer's "registration number" changed
    // when the list was re-sorted. Inventing a professional registration is not
    // a display placeholder.
    api.__respond("searchLawyers", { data: { items: [lawyer("L1")] } });
    const ui = await mountLawyers();
    await ui.settle();

    assert.ok(!/BAR-API-/.test(ui.text()),
              "a bar council registration number was fabricated");
    await ui.unmount();
});

test("a real bar number is still shown", async () => {
    api.__respond("searchLawyers",
        { data: { items: [lawyer("L1", { bar_number: "PBC/12345/2019" })] } });
    const ui = await mountLawyers();
    await ui.settle();

    assert.match(ui.text(), /PBC\/12345\/2019/);
    await ui.unmount();
});

test("office hours are not invented on the profile", async () => {
    // Every profile used to claim "Mon–Fri: 9am–5pm" as that lawyer's own
    // schedule. Nothing collects office hours anywhere in the product, and a
    // client could act on it and find a closed office.
    //
    // This MUST open the profile. Office hours are not on the list view at all,
    // so a list-only assertion passes whether or not the bug is present —
    // verified by restoring the bug and watching it still pass. A test that
    // cannot fail is worse than no test.
    api.__respond("searchLawyers", { data: { items: [lawyer("L1")] } });
    const ui = await mountLawyers();
    await ui.settle();
    await openProfile(ui);

    assert.match(ui.text(), /Working Hours/,
                 "the profile view did not open — the assertion below is vacuous");
    assert.ok(!/9am[\s–-]*5pm/.test(ui.text()),
              "a fixed office-hours string was presented as the lawyer's own");
    assert.match(ui.text(), /Not provided/,
                 "an absent field was not labelled unavailable");
    await ui.unmount();
});

test("an absent bar number is labelled on the profile, not filled in", async () => {
    api.__respond("searchLawyers", { data: { items: [lawyer("L1")] } });
    const ui = await mountLawyers();
    await ui.settle();
    await openProfile(ui);

    assert.match(ui.text(), /Bar No:/);
    assert.ok(!/BAR-API-/.test(ui.text()));
    await ui.unmount();
});

test("review text absent is not shown as no reviews", async () => {
    // `reviewList` is null (there is no endpoint for review text) and [] means
    // genuinely none. Collapsing the two would tell a client that a lawyer with
    // five reviews has none.
    api.__respond("searchLawyers",
        { data: { items: [lawyer("L1", { total_reviews: 5, rating: 4.6 })] } });
    const ui = await mountLawyers();
    await ui.settle();
    await openProfile(ui);

    assert.ok(!/No reviews yet/.test(ui.text()),
              "a lawyer with 5 reviews was shown as having none");
    assert.match(ui.text(), /Loading 5 reviews/);
    await ui.unmount();
});

/* ── location honesty ─────────────────────────────────────────────────────── */

test("no distance is rendered, and never the string null", async () => {
    // `distance` was hardcoded null and interpolated straight into the markup,
    // so the page showed "null km" and "nullkm" to users.
    api.__respond("searchLawyers", { data: { items: [lawyer("L1")] } });
    const ui = await mountLawyers();
    await ui.settle();

    const text = ui.text();
    assert.ok(!/null/i.test(text), `"null" leaked into the UI: ${text.slice(0, 200)}`);
    assert.ok(!/\bkm\b/.test(text), "a distance was shown though none is computed");
    await ui.unmount();
});

test("proximity sorting is not offered when no distance exists", async () => {
    // The option compared `null - null` for every pair, returned the list
    // untouched, and presented that as a proximity ranking.
    api.__respond("searchLawyers", { data: { items: [lawyer("L1")] } });
    const ui = await mountLawyers();
    await ui.settle();

    assert.ok(!/Distance: Nearest/.test(ui.text()));
    await ui.unmount();
});

/* ── filters reach the server ─────────────────────────────────────────────── */

test("the directory is fetched on mount", async () => {
    api.__respond("searchLawyers", { data: { items: [lawyer("L1")] } });
    const ui = await mountLawyers();
    await ui.settle();

    assert.ok(api.__calls("searchLawyers").length >= 1,
              "the lawyer directory was never requested");
    await ui.unmount();
});

test("a lawyer returned by the server is rendered", async () => {
    api.__respond("searchLawyers",
        { data: { items: [lawyer("L1"), lawyer("L2")] } });
    const ui = await mountLawyers();
    await ui.settle();

    assert.match(ui.text(), /Adv L1/);
    assert.match(ui.text(), /Adv L2/);
    await ui.unmount();
});

/* ── empty and failed results ─────────────────────────────────────────────── */

test("an empty directory does not crash or invent a lawyer", async () => {
    api.__respond("searchLawyers", { data: { items: [] } });
    const ui = await mountLawyers();
    await ui.settle();

    assert.ok(!/BAR-API-/.test(ui.text()));
    assert.ok(!/Adv /.test(ui.text()), "a lawyer appeared from nowhere");
    await ui.unmount();
});

test("a failed directory fetch does not crash the page", async () => {
    api.__respond("searchLawyers", { data: null, error: { detail: "boom" } });
    const ui = await mountLawyers();
    await ui.settle();

    assert.ok(ui.container.textContent.length > 0, "the page rendered nothing");
    await ui.unmount();
});

test("a malformed payload is tolerated", async () => {
    // The component accepts either a bare array or {items}. Neither shape may
    // throw when the server returns something else entirely.
    api.__respond("searchLawyers", { data: { unexpected: true } });
    const ui = await mountLawyers();
    await ui.settle();

    assert.ok(ui.container.textContent.length > 0);
    await ui.unmount();
});

/* ── reviews now have a read endpoint ─────────────────────────────────────── */

test("loaded reviews are rendered on the profile", async () => {
    // The rating and the count were always reachable; the review TEXT had no
    // read endpoint at all, so a client saw "4.6 (5)" with nothing behind it.
    api.__respond("searchLawyers", { data: { items: [lawyer("L1")] } });
    api.__respond("getLawyerReviews", { data: { items: [
        { id: "r1", stars: 5, comment: "Clear advice, well prepared.",
          created_at: "2026-08-01T00:00:00Z", reviewer: "Muhammad K." },
    ], total: 1, page: 1, page_size: 10, pages: 1 } });

    const ui = await mountLawyers();
    await ui.settle();
    await openProfile(ui);
    await ui.settle();

    assert.match(ui.text(), /Clear advice, well prepared\./);
    assert.match(ui.text(), /Muhammad K\./);
    await ui.unmount();
});

test("a lawyer with genuinely no reviews says so", async () => {
    api.__respond("searchLawyers", { data: { items: [lawyer("L1")] } });
    api.__respond("getLawyerReviews",
        { data: { items: [], total: 0, page: 1, page_size: 10, pages: 0 } });

    const ui = await mountLawyers();
    await ui.settle();
    await openProfile(ui);
    await ui.settle();

    assert.match(ui.text(), /No reviews yet/);
    await ui.unmount();
});

test("a failed review fetch does not claim there are none", async () => {
    // The distinction that matters: "could not load" is not "has none", and
    // saying the latter misrepresents a lawyer whose count says otherwise.
    api.__respond("searchLawyers", { data: { items: [lawyer("L1")] } });
    api.__respond("getLawyerReviews", { data: null, error: { detail: "boom" } });

    const ui = await mountLawyers();
    await ui.settle();
    await openProfile(ui);
    await ui.settle();

    assert.ok(!/No reviews yet/.test(ui.text()),
              "a failed fetch was reported as the lawyer having no reviews");
    await ui.unmount();
});

test("a reviewer is never identified beyond what the API returns", async () => {
    api.__respond("searchLawyers", { data: { items: [lawyer("L1")] } });
    api.__respond("getLawyerReviews", { data: { items: [
        { id: "r1", stars: 4, comment: "Good.", created_at: "2026-08-01T00:00:00Z",
          reviewer: "Ayesha B." },
    ], total: 1, page: 1, page_size: 10, pages: 1 } });

    const ui = await mountLawyers();
    await ui.settle();
    await openProfile(ui);
    await ui.settle();

    assert.match(ui.text(), /Ayesha B\./);
    assert.ok(!/@/.test(ui.text()), "an email address reached the review list");
    await ui.unmount();
});

/* ── directory paging, and the filters that used to be page-local ─────────── */
//
// The page fetched `page_size: 20` and nothing else, then applied the search
// box, the price and experience sliders and all seven sort options IN THE
// BROWSER to those 20 rows. Each answered a question about one page while
// appearing to answer it about the directory, and the 21st lawyer was
// unreachable by any combination of controls.

function pageOf(items, { page = 1, total = 40, pages = 2 } = {}) {
    return { data: { items, total, pages, page, page_size: 20 } };
}

test("the directory reports the total, not just the page size", async () => {
    api.__respond("searchLawyers",
        pageOf([lawyer("L1"), lawyer("L2")], { total: 42, pages: 3 }));
    const ui = await mountLawyers();
    await ui.settle();

    // "Showing 2 of 42 lawyers" — it used to say only "Showing 2 lawyers"
    // whether the directory held 2 or 2000.
    assert.match(ui.text(), /of\s*42\s*lawyers/);
    await ui.unmount();
});

test("pagination controls appear only when there is more than one page", async () => {
    api.__respond("searchLawyers",
        pageOf([lawyer("L1")], { total: 1, pages: 1 }));
    const one = await mountLawyers();
    await one.settle();
    assert.ok(!/Previous/.test(one.text()), "paging offered for a single page");
    await one.unmount();

    api.__reset();
    api.__respond("bootstrapAuth", true);
    api.__respond("getMe", { data: { _id: "u1", role: "client" } });
    api.__respond("listCases", { data: [] });
    api.__respond("listEngagements", { data: [] });
    api.__respond("searchLawyers",
        pageOf([lawyer("L1")], { total: 40, pages: 2 }));
    const many = await mountLawyers();
    await many.settle();
    assert.match(many.text(), /Previous/);
    assert.match(many.text(), /Next/);
    await many.unmount();
});

test("Next asks the server for the following page", async () => {
    // THE defect: lawyers past the first page had no route to the screen.
    api.__respond("searchLawyers",
        pageOf([lawyer("L1")], { total: 40, pages: 2 }));
    const ui = await mountLawyers();
    await ui.settle();

    const next = [...ui.container.querySelectorAll("button")]
        .find(b => /Next/.test(b.textContent));
    assert.ok(next, "no Next control");
    await act(async () => {
        next.dispatchEvent(new dom.window.MouseEvent(
            "click", { bubbles: true, cancelable: true }));
    });
    await ui.settle(400);

    const pages = api.__calls("searchLawyers").map(c => c.args[0]?.page);
    assert.ok(pages.includes(2), `never requested page 2; asked for ${pages}`);
    await ui.unmount();
});

test("the search box is sent to the server, not applied to the page", async () => {
    api.__respond("searchLawyers", pageOf([lawyer("L1")]));
    const ui = await mountLawyers();
    await ui.settle();

    const box = [...ui.container.querySelectorAll("input")]
        .find(i => /search/i.test(i.getAttribute("placeholder") || ""));
    assert.ok(box, "no search input found");
    await act(async () => {
        setNativeValue(box, "Bilal");
        box.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
    });
    await ui.settle(500);

    const sent = api.__calls("searchLawyers").map(c => c.args[0]?.q).filter(Boolean);
    assert.ok(sent.includes("Bilal"),
              `the query never reached the server; sent: ${JSON.stringify(sent)}`);
    await ui.unmount();
});

test("a sort choice is sent as a server sort key", async () => {
    // Sorting a page is not sorting a list: the cheapest lawyer overall is
    // very unlikely to be among the 20 rows the client happens to hold.
    api.__respond("searchLawyers", pageOf([lawyer("L1")]));
    const ui = await mountLawyers();
    await ui.settle();

    const select = [...ui.container.querySelectorAll("select")]
        .find(s => [...s.options].some(o => /Price: Low to High/.test(o.textContent)));
    assert.ok(select, "no sort control found");
    await act(async () => {
        setNativeValue(select, "Price: Low to High");
        select.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
    });
    await ui.settle(500);

    const sorts = api.__calls("searchLawyers").map(c => c.args[0]?.sort);
    assert.ok(sorts.includes("fee_asc"),
              `sort was not sent to the server; sent: ${JSON.stringify(sorts)}`);
    await ui.unmount();
});

test("the first request carries a page and a sort", async () => {
    api.__respond("searchLawyers", pageOf([lawyer("L1")]));
    const ui = await mountLawyers();
    await ui.settle();

    const first = api.__calls("searchLawyers")[0].args[0];
    assert.equal(first.page, 1);
    assert.equal(first.page_size, 20);
    assert.equal(first.sort, "rating_desc");
    // Fee and experience are not filters, so no bound is ever sent for them.
    for (const gone of ["min_fee", "max_fee", "min_experience", "max_experience"]) {
        assert.equal(first[gone], undefined, `${gone} is still being sent`);
    }
    await ui.unmount();
});

test("the server's page is rendered as given, not re-filtered locally", async () => {
    // Re-applying the filters to a server page can only remove rows the server
    // has already decided belong, leaving a short page and a count that
    // disagrees with it.
    api.__respond("searchLawyers", pageOf(
        [lawyer("A1", { experience_years: 1, hourly_rate: 100, rating: 1.0 }),
         lawyer("A2", { experience_years: 40, hourly_rate: 99999, rating: 5.0 })],
        { total: 2, pages: 1 }));
    const ui = await mountLawyers();
    await ui.settle();

    assert.match(ui.text(), /Adv A1/);
    assert.match(ui.text(), /Adv A2/);
    await ui.unmount();
});

test("matching is untouched by the directory changes", async () => {
    // matchLawyers must keep its own call shape.
    api.__respond("searchLawyers", pageOf([lawyer("L1")]));
    const ui = await mountLawyers();
    await ui.settle();
    assert.equal(api.__calls("matchLawyers").length, 0,
                 "the directory fetch triggered a match request");
    await ui.unmount();
});

/* ── directions and location honesty ──────────────────────────────────────── */
//
// `_inject_coords` fills a missing pin with a province centre plus a
// deterministic offset of up to 0.4 degrees — roughly 44 km — and wrote it into
// the same lat/lng fields as a genuinely geocoded address. The UI could not
// tell them apart and offered "Get Directions" for both, so a client could be
// given turn-by-turn navigation to a point this system invented. The address
// fallback was no better: `encodeURIComponent(null)` is the string "null",
// which was being sent to Google Maps as the destination.

function openedUrls() {
    return (globalThis.__opened ||= []);
}

// Stub `dom.window.open`, NOT `globalThis.open`. The component calls
// `window.open(...)`, and `window` here is the jsdom window — so a stub on
// globalThis is never consulted and every maps URL sails past unrecorded,
// leaving the assertions below unable to fail.
Object.defineProperty(dom.window, "open", {
    value: (url) => { openedUrls().push(url); return null; },
    writable: true, configurable: true,
});

test.beforeEach(() => { openedUrls().length = 0; });

test("a lawyer with a real address is offered directions", async () => {
    api.__respond("searchLawyers", { data: { items: [lawyer("L1", {
        address: "12 Mall Road, Lahore", lat: 31.5497, lng: 74.3436,
        location_precision: "exact",
    })] }, total: 1, pages: 1 });
    const ui = await mountLawyers();
    await ui.settle();
    await openProfile(ui);

    assert.match(ui.text(), /Get Directions/);
    await ui.unmount();
});

test("directions navigate to the geocoded point, never to the string null",
     async () => {
    api.__respond("searchLawyers", { data: { items: [lawyer("L1", {
        address: "12 Mall Road, Lahore", lat: 31.5497, lng: 74.3436,
        location_precision: "exact",
    })] }, total: 1, pages: 1 });
    const ui = await mountLawyers();
    await ui.settle();
    await openProfile(ui);

    const btn = [...ui.container.querySelectorAll("button")]
        .find(b => /Get Directions/.test(b.textContent));
    await act(async () => {
        btn.dispatchEvent(new dom.window.MouseEvent(
            "click", { bubbles: true, cancelable: true }));
    });

    const url = openedUrls().at(-1) || "";
    assert.match(url, /destination=31\.5497,74\.3436/);
    assert.ok(!/null/.test(url), `"null" reached a maps URL: ${url}`);
    await ui.unmount();
});

test("an approximate pin is NOT offered directions", async () => {
    // THE defect. This coordinate is a province centre plus an invented offset;
    // routing a client to it would send them up to ~44 km from their lawyer.
    api.__respond("searchLawyers", { data: { items: [lawyer("L1", {
        lat: 31.1704, lng: 72.7097, location_precision: "approximate",
    })] }, total: 1, pages: 1 });
    const ui = await mountLawyers();
    await ui.settle();
    await openProfile(ui);

    assert.ok(!/Get Directions/.test(ui.text()),
              "directions were offered to a fabricated coordinate");
    assert.ok(!/View on Map/.test(ui.text()));
    await ui.unmount();
});

test("an approximate pin explains itself instead", async () => {
    api.__respond("searchLawyers", { data: { items: [lawyer("L1", {
        lat: 31.1704, lng: 72.7097, location_precision: "approximate",
    })] }, total: 1, pages: 1 });
    const ui = await mountLawyers();
    await ui.settle();
    await openProfile(ui);

    assert.match(ui.text(), /has not published an office address/);
    assert.match(ui.text(), /directions are not available/);
    await ui.unmount();
});

test("no maps URL is ever opened for a lawyer without a real address",
     async () => {
    api.__respond("searchLawyers", { data: { items: [lawyer("L1", {
        lat: 31.1704, lng: 72.7097, location_precision: "approximate",
    })] }, total: 1, pages: 1 });
    const ui = await mountLawyers();
    await ui.settle();
    await openProfile(ui);

    for (const b of [...ui.container.querySelectorAll("button")]) {
        await act(async () => {
            b.dispatchEvent(new dom.window.MouseEvent(
                "click", { bubbles: true, cancelable: true }));
        });
    }
    assert.deepEqual(openedUrls().filter(u => /google\.com\/maps/.test(u)), [],
                     "a maps link was opened for an invented location");
    await ui.unmount();
});

test("a missing address is labelled, not rendered blank", async () => {
    api.__respond("searchLawyers", { data: { items: [lawyer("L1", {
        lat: 31.1704, lng: 72.7097, location_precision: "approximate",
    })] }, total: 1, pages: 1 });
    const ui = await mountLawyers();
    await ui.settle();
    await openProfile(ui);

    assert.match(ui.text(), /Not provided/);
    await ui.unmount();
});

test("the map list button is labelled for what it does", async () => {
    // It read "Directions" and opened the profile — it has never navigated.
    api.__respond("searchLawyers", { data: { items: [lawyer("L1")] },
                                     total: 1, pages: 1 });
    const ui = await mountLawyers();
    await ui.settle();

    const src = await import("node:fs");
    const file = src.readFileSync(
        "src/components/client/ModLawyers.jsx", "utf8");
    assert.ok(!/>Directions<\/BtnOutline>/.test(file),
              "a button still says Directions while only opening the profile");
    await ui.unmount();
});

test("the directory makes no real-time schedule claim or sensitive browser log", async () => {
    const fs = await import("node:fs");
    const source = fs.readFileSync("src/components/client/ModLawyers.jsx", "utf8");
    assert.doesNotMatch(source, /real-time availability|Available Now/);
    assert.doesNotMatch(source, /console\.(?:log|warn|error)\s*\(/);
    assert.match(source, /request a consultation time/);
});

/* ── the demo dataset, end to end ─────────────────────────────────────────── */
//
// Six seeded lawyers carry a real office address with pinned coordinates and
// must offer directions; six carry none and must not. Both halves are asserted
// against the SAME component, using payloads shaped exactly as the seeded rows
// reach the client.

test("a seeded lawyer with a real office offers directions to it", async () => {
    // Kamran Aziz Malik, Jinnah Avenue, Blue Area, Islamabad.
    api.__respond("searchLawyers", { data: { items: [lawyer("L1", {
        address: "Jinnah Avenue, Blue Area, Islamabad",
        lat: 33.723619, lng: 73.081890, location_precision: "exact",
    })] }, total: 1, pages: 1 });
    const ui = await mountLawyers();
    await ui.settle();
    await openProfile(ui);

    assert.match(ui.text(), /Jinnah Avenue, Blue Area, Islamabad/);
    assert.match(ui.text(), /Get Directions/);

    const btn = [...ui.container.querySelectorAll("button")]
        .find(b => /Get Directions/.test(b.textContent));
    await act(async () => {
        btn.dispatchEvent(new dom.window.MouseEvent(
            "click", { bubbles: true, cancelable: true }));
    });

    const url = openedUrls().at(-1) || "";
    assert.match(url, /destination=33\.723619,73\.08189/);
    await ui.unmount();
});

test("a seeded lawyer with no office still cannot generate directions",
     async () => {
    // Rabia Kazmi (sindh) — no address in the roster, so the backend supplies a
    // province-centre pin and marks it approximate. The demo must not relax it.
    api.__respond("searchLawyers", { data: { items: [lawyer("L1", {
        lat: 25.8943, lng: 68.5247, location_precision: "approximate",
    })] }, total: 1, pages: 1 });
    const ui = await mountLawyers();
    await ui.settle();
    await openProfile(ui);

    assert.ok(!/Get Directions/.test(ui.text()));
    assert.match(ui.text(), /directions are not available/);
    await ui.unmount();
});

test("a lawyer with no location at all cannot generate directions", async () => {
    api.__respond("searchLawyers", { data: { items: [lawyer("L1", {
        location_precision: "none",
    })] }, total: 1, pages: 1 });
    const ui = await mountLawyers();
    await ui.settle();
    await openProfile(ui);

    assert.ok(!/Get Directions/.test(ui.text()));
    await ui.unmount();
});

/* ── hiring follows a completed consultation (§17 R5-1) ──────────────────── */

/* The server refuses a hire request that does not name a COMPLETED
 * consultation with the same lawyer, and it is the server that says which
 * consultations qualify (`listHireConsultations`, scoped to one lawyer). These
 * pin the UI side: no consultation, no request; a failed read is not "none";
 * one consultation is filled in; several are the CLIENT's choice. */

function hireableCase(id, over = {}) {
    return { _id: id, title: `Case ${id}`, case_number: `ATT-${id}`,
             status: "open", lawyer_id: null, ...over };
}

function consult(id, over = {}) {
    return { id, lawyer_id: "L1", client_id: "u1", case_id: null,
             status: "completed", scheduled_at: "2026-09-01T10:00:00Z", ...over };
}

/* The hire form is a portal on document.body, outside `ui.container`. */
async function clickText(ui, label) {
    const btn = [...dom.window.document.querySelectorAll("button")]
        .find(b => b.textContent.trim().startsWith(label));
    assert.ok(btn, `no "${label}" button was rendered`);
    await act(async () => {
        btn.dispatchEvent(new dom.window.MouseEvent(
            "click", { bubbles: true, cancelable: true }));
    });
    await ui.settle(30);
}

function pageText() { return dom.window.document.body.textContent; }

/* The select under a hire-form label ("Consultation *" or "Case *"). */
function fieldSelect(labelText) {
    const label = [...dom.window.document.querySelectorAll("label")]
        .find(l => l.textContent.trim() === labelText);
    return label ? label.parentElement.querySelector("select") : null;
}

async function choose(ui, select, value) {
    await act(async () => {
        setNativeValue(select, value);
        select.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
    });
    await ui.settle(30);
}

async function openHireFor(consults) {
    // A test that failed before `unmount` leaves its portal behind; start clean
    // so one failure cannot masquerade as several.
    for (const el of [...dom.window.document.body.children]) el.remove();
    api.__respond("searchLawyers", { data: { items: [lawyer("L1")] } });
    api.__respond("listCases",
        { data: { items: [hireableCase("C1"), hireableCase("C2")] } });
    api.__respond("listHireConsultations", consults);
    api.__respond("requestEngagement", { data: { id: "E1" } });
    const ui = await mountLawyers();
    await ui.settle();
    await openProfile(ui);
    await clickText(ui, "Request to Hire");
    return ui;
}

test("the server is asked for this lawyer's consultations, not a diary page",
     async () => {
    const ui = await openHireFor({ data: [consult("A1")] });
    const calls = api.__calls("listHireConsultations");
    assert.equal(calls.length, 1);
    assert.equal(calls[0].args[0], "L1");
    await ui.unmount();
});

test("without a completed consultation, no hire request can be made",
     async () => {
    const ui = await openHireFor({ data: [] });
    assert.ok(!/Send Hire Request/.test(pageText()), "the hire form opened");
    assert.match(pageText(), /Book a consultation with/);
    assert.equal(api.__calls("requestEngagement").length, 0);
    await ui.unmount();
});

test("a failed read is not reported as having no consultation", async () => {
    const ui = await openHireFor(
        { data: null, error: { message: "Network down" }, status: 0 });
    assert.ok(!/Book a consultation with/.test(pageText()),
              "a read failure was presented as a fact about the client");
    assert.ok(!/Send Hire Request/.test(pageText()));
    assert.equal(api.__calls("requestEngagement").length, 0);
    await ui.unmount();
});

test("a single consultation is filled in and named by the request", async () => {
    const ui = await openHireFor({ data: [consult("A1")] });
    assert.equal(fieldSelect("Consultation *"), null,
                 "one consultation should be stated, not offered as a choice");
    await clickText(ui, "Send Hire Request");

    const calls = api.__calls("requestEngagement");
    assert.equal(calls.length, 1);
    assert.equal(calls[0].args[0].appointment_id, "A1");
    assert.equal(calls[0].args[0].lawyer_id, "L1");
    await ui.unmount();
});

test("with several consultations none is chosen for the client", async () => {
    const ui = await openHireFor({ data: [
        consult("A-new", { scheduled_at: "2026-09-10T10:00:00Z" }),
        consult("A-old", { scheduled_at: "2026-08-01T10:00:00Z" }),
    ] });
    const picker = fieldSelect("Consultation *");
    assert.ok(picker, "several consultations were not offered as a choice");
    assert.equal(picker.value, "", "a consultation was pre-selected");

    await clickText(ui, "Send Hire Request");
    assert.equal(api.__calls("requestEngagement").length, 0,
                 "a request was sent before the client chose");
    await ui.unmount();
});

test("the consultation the client chooses is the one the request names",
     async () => {
    const ui = await openHireFor({ data: [
        consult("A-new", { scheduled_at: "2026-09-10T10:00:00Z" }),
        consult("A-old", { scheduled_at: "2026-08-01T10:00:00Z" }),
    ] });
    await choose(ui, fieldSelect("Consultation *"), "A-old");
    await clickText(ui, "Send Hire Request");

    const calls = api.__calls("requestEngagement");
    assert.equal(calls.length, 1);
    assert.equal(calls[0].args[0].appointment_id, "A-old");
    await ui.unmount();
});

test("a case-bound consultation offers only its own case", async () => {
    const ui = await openHireFor({ data: [consult("A1", { case_id: "C2" })] });
    const options = [...fieldSelect("Case *").querySelectorAll("option")]
        .map(o => o.value);
    assert.deepEqual(options, ["C2"]);
    await ui.unmount();
});

/* ── booking form: typing keeps focus; only an offered time can be booked ── */

async function openBookingFor(ui) {
    await openProfile(ui);
    const book = [...ui.container.querySelectorAll("button")].find(b => b.textContent.trim() === "Book Appointment");
    assert.ok(book, "no Book Appointment button");
    await act(async () => { book.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
    await ui.settle(80);
    // TOMORROW, not the default "today": a slot earlier than the current
    // PKT time is (correctly) refused as past, which made these tests depend
    // on the hour they ran at.
    const { pktToday } = await import("../src/lib/bookingTime.js");
    const d = new Date(`${pktToday()}T12:00:00Z`);
    d.setUTCDate(d.getUTCDate() + 1);
    const dateInput = dom.window.document.body.querySelector('input[type="date"]');
    if (dateInput) {
        setNativeValue(dateInput, d.toISOString().slice(0, 10));
        await act(async () => { dateInput.dispatchEvent(new dom.window.Event("change", { bubbles: true })); });
        await ui.settle(60);
    }
    return dom.window.document.body;
}
const slotsFor = (times) => ({ data: { configured: true, enforced: false, days: [{ date: "x", slots: times.map(t => ({ start: `s-${t}`, local_time: t })) }] }, error: null });

test("typing in the booking notes keeps focus (the form is not remounted per key)", async () => {
    api.__respond("searchLawyers", { data: { items: [lawyer("L1")] } });
    api.__respond("getBookableSlots", slotsFor(["11:00"]));
    const ui = await mountLawyers();
    const body = await openBookingFor(ui);
    const box = [...body.querySelectorAll("textarea")].at(-1);
    assert.ok(box, "no notes box");
    box.focus();
    for (const ch of "Rent") {
        const current = [...body.querySelectorAll("textarea")].at(-1);
        setNativeValue(current, current.value + ch);
        await act(async () => { current.dispatchEvent(new dom.window.Event("input", { bubbles: true })); });
    }
    const after = [...body.querySelectorAll("textarea")].at(-1);
    assert.equal(after, box, "the notes box was replaced by a new element while typing");
    assert.equal(after.value, "Rent");
    assert.equal(dom.window.document.activeElement, box, "focus was lost while typing");
    await ui.unmount();
});

test("booking sends only a time the client picked from the offered slots", async () => {
    api.__respond("searchLawyers", { data: { items: [lawyer("L1")] } });
    api.__respond("getBookableSlots", slotsFor(["11:00", "11:30"]));
    api.__respond("bookAppointment", { data: { id: "a1", status: "pending" }, error: null });
    const ui = await mountLawyers();
    const body = await openBookingFor(ui);
    const confirm = () => [...body.querySelectorAll("button")].find(b => b.textContent.includes("Send request"));

    // Nothing picked yet: no default 10:00 is sent.
    await act(async () => { confirm().dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
    await ui.settle();
    assert.equal(api.__calls("bookAppointment").length, 0, "a time the client never chose was booked");

    const slot = [...body.querySelectorAll("button")].find(b => b.textContent.trim() === "11:30");
    await act(async () => { slot.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
    await act(async () => { confirm().dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
    await ui.settle();
    const sent = api.__calls("bookAppointment");
    assert.equal(sent.length, 1);
    assert.match(sent[0].args[0].scheduled_at, /T06:30:00/, "11:30 PKT is 06:30 UTC");
    await ui.unmount();
});

test("a refused time is explained inside the dialog and cannot be sent again (2026-10-12)", async () => {
    api.__respond("searchLawyers", { data: { items: [lawyer("L1")] } });
    api.__respond("getBookableSlots", slotsFor(["11:00", "11:30"]));
    api.__respond("bookAppointment", { data: null, status: 409,
        error: { message: "You already have an appointment during this time. Please choose a different time." } });
    const ui = await mountLawyers();
    const body = await openBookingFor(ui);
    const send = () => [...body.querySelectorAll("button")].find(b => b.textContent.includes("Send request"));
    const slot = () => [...body.querySelectorAll("[data-booking-dialog] button")].find(b => b.textContent.trim() === "11:00");
    assert.equal(send().disabled, true, "Send request was enabled with no time chosen");

    await act(async () => { slot().dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
    assert.equal(send().disabled, false);
    await act(async () => { send().dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
    await ui.settle();

    const alert = body.querySelector("[data-booking-error]");
    assert.ok(alert, "the refusal was not shown in the dialog");
    assert.match(alert.textContent, /already have an appointment/);
    assert.equal(slot().disabled, true, "the refused time can be picked again");
    assert.equal(send().disabled, true, "the refused time is still selected");
    await ui.unmount();
});

test("a lawyer with no published hours cannot be booked at a guessed time", async () => {
    api.__respond("searchLawyers", { data: { items: [lawyer("L1")] } });
    api.__respond("getBookableSlots", { data: { configured: false, enforced: false, days: [] }, error: null });
    const ui = await mountLawyers();
    const body = await openBookingFor(ui);
    const confirm = [...body.querySelectorAll("button")].find(b => b.textContent.includes("Send request"));
    await act(async () => { confirm.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
    await ui.settle();
    assert.equal(api.__calls("bookAppointment").length, 0);
    await ui.unmount();
});

/* The booking dialog, 2026-10-12: times re-read on every open, the case
 * chosen in the dialog, and the earliest open time one click away. */
test("reopening the booking for the same lawyer and day asks for the times again", async () => {
    api.__respond("searchLawyers", { data: { items: [lawyer("L1")] } });
    api.__respond("getBookableSlots", slotsFor(["11:00"]));
    const ui = await mountLawyers();
    await openProfile(ui);
    // Same lawyer, same (default) day both times: nothing the old effect
    // depended on changes between the two opens.
    const book = () => [...ui.container.querySelectorAll("button")].find(b => b.textContent.trim() === "Book Appointment");
    await act(async () => { book().dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
    await ui.settle(80);
    const close = dom.window.document.body.querySelector('[data-booking-dialog] button[aria-label="Close"]');
    await act(async () => { close.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
    await ui.settle();
    const before = api.__calls("getBookableSlots").length;
    await act(async () => { book().dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
    await ui.settle(80);
    assert.ok(api.__calls("getBookableSlots").length > before, "the times were not fetched again");
    const body = dom.window.document.body;
    assert.doesNotMatch(body.querySelector("[data-booking-dialog]").textContent, /Choose a date to see times/);
    await ui.unmount();
});

test("the booking is about the case the client picks, and only cases that can take one are offered", async () => {
    api.__respond("searchLawyers", { data: { items: [lawyer("L1")] } });
    api.__respond("getBookableSlots", slotsFor(["11:00"]));
    api.__respond("listCases", { data: { items: [
        hireableCase("C1", { title: "Bail matter" }),
        hireableCase("C2", { title: "Old draft", status: "draft" }),
        hireableCase("C3", { title: "Finished", status: "closed" }),
    ] } });
    api.__respond("bookAppointment", { data: { id: "a1", status: "pending" }, error: null });
    const ui = await mountLawyers();
    await ui.settle();
    const body = await openBookingFor(ui);
    const select = body.querySelector("[data-appt-case]");
    const labels = [...select.options].map(o => o.textContent);
    assert.equal(select.value, "", "a general consultation unless the client says otherwise");
    assert.ok(labels.some(l => l.includes("Bail matter")));
    assert.ok(!labels.some(l => l.includes("Old draft") || l.includes("Finished")), `offered: ${labels}`);
    setNativeValue(select, "C1");
    await act(async () => { select.dispatchEvent(new dom.window.Event("change", { bubbles: true })); });
    const slot = [...body.querySelectorAll("button")].find(b => b.textContent.trim() === "11:00");
    await act(async () => { slot.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
    const send = [...body.querySelectorAll("button")].find(b => b.textContent.includes("Send request"));
    await act(async () => { send.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
    await ui.settle();
    assert.equal(api.__calls("bookAppointment")[0].args[0].case_id, "C1");
    await ui.unmount();
});

test("the earliest open time can be taken in one click", async () => {
    api.__respond("searchLawyers", { data: { items: [lawyer("L1")] } });
    const { pktToday } = await import("../src/lib/bookingTime.js");
    const d = new Date(`${pktToday()}T12:00:00Z`);
    d.setUTCDate(d.getUTCDate() + 1);
    const day = d.toISOString().slice(0, 10);
    api.__respond("getBookableSlots", { data: { configured: true, enforced: false,
        days: [{ date: day, slots: [{ start: "s1", local_time: "09:30" }] }] }, error: null });
    const ui = await mountLawyers();
    const body = await openBookingFor(ui);   // opens on tomorrow already
    const chip = body.querySelector("[data-earliest]");
    assert.ok(chip, "no earliest-time shortcut");
    assert.match(chip.textContent, /09:30/);
    await act(async () => { chip.querySelector("button").dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
    await ui.settle();
    const picked = [...body.querySelectorAll('[data-booking-dialog] [aria-pressed="true"]')].map(b => b.textContent.trim());
    assert.ok(picked.includes("09:30"), `picked: ${picked}`);
    await ui.unmount();
});

test("a lawyer with no published hours can be ASKED for a time the client picks, while hours are not enforced", async () => {
    api.__respond("searchLawyers", { data: { items: [lawyer("L1")] } });
    api.__respond("getBookableSlots", { data: { configured: false, enforced: false, days: [] }, error: null });
    api.__respond("bookAppointment", { data: { id: "a1", status: "pending" }, error: null });
    const ui = await mountLawyers();
    const body = await openBookingFor(ui);
    // A future date, so every request time is still open.
    const date = body.querySelector("#appt-date");
    await act(async () => {
        Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value").set.call(date, "2099-01-05");
        date.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
    });
    await ui.settle();
    const slot = [...body.querySelectorAll("button")].find(b => b.textContent.trim() === "15:00");
    assert.ok(slot, "no time to request was offered");
    await act(async () => { slot.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
    const send = [...body.querySelectorAll("button")].find(b => b.textContent.includes("Send request"));
    await act(async () => { send.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
    await ui.settle();
    const sent = api.__calls("bookAppointment");
    assert.equal(sent.length, 1);
    assert.match(sent[0].args[0].scheduled_at, /2099-01-05T10:00:00/, "15:00 PKT is 10:00 UTC");
    await ui.unmount();
});

test("a sent booking is reported as a request, and the real appointments are re-read", async () => {
    // It used to add a timeline milestone saying the consultation was
    // "confirmed" (the lawyer had not accepted anything) plus a second,
    // browser-only notice next to the one the server already sends.
    api.__respond("searchLawyers", { data: { items: [lawyer("L1")] } });
    api.__respond("getBookableSlots", slotsFor(["11:00"]));
    api.__respond("bookAppointment", { data: { id: "a1", status: "pending" }, error: null });
    const ui = await mountLawyers();
    const body = await openBookingFor(ui);
    const before = api.__calls("listAppointments").length;
    const slot = [...body.querySelectorAll("button")].find(b => b.textContent.trim() === "11:00");
    await act(async () => { slot.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
    const confirm = [...body.querySelectorAll("button")].find(b => b.textContent.includes("Send request"));
    await act(async () => { confirm.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
    await ui.settle(60);
    assert.equal(api.__calls("bookAppointment").length, 1);
    assert.match(body.textContent, /Request sent/);
    // The dialog says what happens next and leads to the appointment itself.
    const sent = body.querySelector("[data-booking-sent]");
    assert.ok(sent, "no Request sent view");
    assert.match(sent.textContent, /confirms or declines/);
    await act(async () => { sent.querySelector("[data-view-appointment]").dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
    assert.equal(globalThis.__nav.pushed.at(-1), "/appointments?appointment=a1");
    assert.doesNotMatch(body.textContent, /Appointment booked!/);
    assert.ok(api.__calls("listAppointments").length > before, "the appointments were not re-read after booking");
    await ui.unmount();
});

test("declined and ended engagements stay visible, with the reason", async () => {
    api.__respond("searchLawyers", { data: { items: [lawyer("L1")] } });
    api.__respond("listEngagements", { data: [
        { id: "E1", status: "declined", declined_by: "lawyer", decline_reason: "Conflict of interest",
          lawyer_name: "Adv Sana", case_title: "Rent dispute", updated_at: "2026-10-01T05:00:00Z" },
        { id: "E2", status: "terminated", termination_reason: "Moved to another city",
          lawyer_name: "Adv Bilal", case_title: "Land case", updated_at: "2026-10-03T05:00:00Z" },
        { id: "E3", status: "requested", lawyer_name: "Adv Omar", case_title: "Fee case" },
    ] });
    // The list lives on Tracking now (2026-11-23).
    const ui = await mountHireRequests();
    const past = ui.container.querySelector("[data-ended-engagements]");
    assert.ok(past, "ended engagements are not shown");
    const text = past.textContent;
    assert.match(text, /Adv Sana declined this request\. Reason: Conflict of interest/);
    assert.match(text, /The engagement was ended\. Reason: Moved to another city/);
    assert.ok(text.indexOf("Adv Bilal") < text.indexOf("Adv Sana"), "newest first");
    assert.doesNotMatch(text, /Adv Omar/, "a live request is not history");
    await ui.unmount();
});

test("the Lawyers page no longer carries hire requests, the trust ticks or the waiting line (2026-11-23)", async () => {
    api.__respond("searchLawyers", { data: { items: [lawyer("L1")] } });
    api.__respond("listEngagements", { data: [
        { id: "E3", status: "requested", lawyer_name: "Adv Omar", case_title: "Fee case" },
    ] });
    const ui = await mountLawyers();
    const text = ui.text();
    assert.equal(ui.container.querySelector("#my-hire-requests"), null, "hire requests are still on Lawyers");
    assert.doesNotMatch(text, /My Hire Requests/);
    assert.doesNotMatch(text, /Bar number on every profile|Fees shown before you book|Hire only after a consultation/);
    assert.doesNotMatch(text, /to answer your request/);
    await ui.unmount();
});

test("the top container: registered not verified, a working tile filter, one match card (2026-11-23)", async () => {
    api.__respond("searchLawyers", { data: { items: [lawyer("L1")] } });
    const ui = await mountLawyers();
    await ui.settle();
    const hero = ui.container.querySelector("[data-lawyers-hero]");
    assert.ok(hero, "the container is gone");
    const text = hero.textContent;
    assert.doesNotMatch(text, /All verified/, "lawyers are registered, not verified");
    assert.match(text, /All registered/);
    assert.match(text, /Find the right lawyer/);
    assert.doesNotMatch(text, /Legal directory|Find Expert Legal Counsel/i);
    assert.doesNotMatch(text, /AI match\b/i, "the sparkle 'AI match' label is back");
    // The Accepting tile shows when its filter is on, and the same tile clears it.
    const tile = [...hero.querySelectorAll("button.lh-stat")].find(b => /Accepting requests/.test(b.textContent));
    assert.equal(tile.getAttribute("aria-pressed"), "false");
    await act(async () => { tile.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
    await ui.settle();
    assert.equal(tile.getAttribute("aria-pressed"), "true");
    assert.match(tile.textContent, /Showing only these · Clear/);
    await act(async () => { tile.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
    await ui.settle();
    assert.equal(tile.getAttribute("aria-pressed"), "false");
    // The separate dashed banner is gone; its box opens from the card's link.
    assert.equal(ui.container.querySelector("[data-ai-ask]"), null, "the duplicate banner is back");
    await act(async () => { hero.querySelector("[data-open-ask]").dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
    await ui.settle();
    assert.ok(ui.container.querySelector("[data-ai-ask] input"), "the describe-your-problem box did not open");
    await ui.unmount();
});

test("hire requests keep every action on their new page", async () => {
    api.__respond("listEngagements", { data: [
        { id: "R1", status: "requested", lawyer_name: "Adv Omar", case_title: "Fee case" },
        { id: "T1", status: "terms_proposed", lawyer_name: "Adv Sana", case_title: "Rent", fee_amount: 5000, fee_type: "per_hearing" },
        { id: "A1", status: "accepted", lawyer_name: "Adv Bilal", case_title: "Land" },
    ] });
    const ui = await mountHireRequests();
    const labels = [...ui.container.querySelectorAll("button")].map(b => b.textContent.trim());
    for (const want of ["Withdraw", "Decline", "Accept terms", "Mark complete", "End engagement"]) {
        assert.ok(labels.includes(want), `${want} is missing`);
    }
    assert.match(ui.container.textContent, /Adv Sana proposed PKR 5,000\/hearing\. Nothing is agreed until you accept\./);
    await ui.unmount();
});

/* ── review eligibility follows the lawyer on screen (2026-10-12) ──────────── */

async function openProfileOf(ui, name) {
    let node = [...ui.container.querySelectorAll("div")]
        .find(el => el.textContent.trim() === name && el.children.length === 0);
    assert.ok(node, `no card for ${name}`);
    for (let i = 0; i < 8 && node; i++) {
        await act(async () => { node.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true, cancelable: true })); });
        await ui.settle(30);
        if (/Bar No:/.test(ui.text())) return;
        node = node.parentElement;
    }
    throw new Error(`could not open ${name}`);
}

test("switching lawyers resets the review state to the new lawyer's answer", async () => {
    api.__respond("searchLawyers", { data: { items: [lawyer("L1"), lawyer("L2")] } });
    api.__respond("getReviewEligibility", (id) => ({ data: id === "L1"
        ? { can_review: false, already_reviewed: true, reason: "already_reviewed" }
        : { can_review: false, already_reviewed: false, reason: "no_completed_relationship" }, error: null }));
    const ui = await mountLawyers();
    await ui.settle();
    await openProfileOf(ui, "Adv L1");
    await ui.settle(40);
    assert.match(ui.text(), /Review submitted — thank you/);
    const back = [...ui.container.querySelectorAll("button")].find(b => /Back to Lawyers/.test(b.textContent));
    await act(async () => { back.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
    await ui.settle(40);
    await openProfileOf(ui, "Adv L2");
    await ui.settle(40);
    assert.ok(!/Review submitted/.test(ui.text()), "the first lawyer's answer was shown on the second");
    assert.match(ui.text(), /You can review Adv after a completed consultation/);
    await ui.unmount();
});

/* ── case states behind "Find My Match" (2026-10-16) ─────────────────────────
 *
 * The page matches automatically on every visit, against the case the last
 * intake saved. A draft case was refused with an error toast on every visit,
 * and a deleted one polled for ~12 s and then said "still processing" -- for a
 * case that no longer existed, and again on the next visit. Each now has its
 * own message and next step, and a dead saved id is forgotten. */
const { readIntakeValue: readSaved, writeIntakeValue: saveIntake } =
    await import("../src/lib/intakeStorage.js");
const nav = () => (globalThis.__nav ||= { pushed: [], replaced: [], params: new Map() });
const buttonByText = (ui, re) =>
    [...ui.container.querySelectorAll("button")].find(b => re.test(b.textContent.trim()));

function caseStateSetup(caseId = "C-1") {
    nav().pushed.length = 0; nav().replaced.length = 0; nav().params.clear();
    saveIntake("aai-case-id", "u1", caseId);
    api.__respond("searchLawyers", pageOf([lawyer("L1")]));
}

test("a draft case says to finish the intake, offers it, and keeps the saved id", async () => {
    caseStateSetup();
    api.__respond("matchLawyers", { data: null, status: 422, error: {
        code: "case_draft",
        message: "This case is still a draft, so it cannot be matched to lawyers yet. Confirm it at the end of the intake first." } });
    const ui = await mountLawyers();
    await ui.settle(600);
    assert.equal(api.__calls("matchLawyers").length, 1, "a draft was polled as if it were processing");
    assert.match(ui.text(), /Finish your Legal Intake first/);
    assert.match(ui.text(), /still a draft/);
    assert.doesNotMatch(ui.text(), /still processing/);
    const next = buttonByText(ui, /^Finish intake$/);
    assert.ok(next, "no next step was offered for the draft");
    await act(async () => { next.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
    assert.ok(nav().pushed.includes("/intake"));
    assert.equal(readSaved("aai-case-id", "u1"), "C-1", "a draft is still the client's case");
    await ui.unmount();
});

test("a deleted case is said to be gone, its saved id is cleared, and a refresh does not ask again", async () => {
    caseStateSetup();
    api.__respond("matchLawyers", { data: null, status: 404, error: { message: "Case not found" } });
    const ui = await mountLawyers();
    await ui.settle(3800);                       // one retry, ~3 s, for a case still being created
    assert.equal(api.__calls("matchLawyers").length, 2, "expected exactly one retry for a missing case");
    assert.match(ui.text(), /Your earlier case is no longer available/);
    assert.match(ui.text(), /could not find your earlier case/);
    assert.doesNotMatch(ui.text(), /still processing/);
    assert.equal(readSaved("aai-case-id", "u1"), null, "the dead id was kept");
    assert.ok(buttonByText(ui, /^Start intake/), "no way forward was offered");
    await ui.unmount();

    // a refresh: the dead id is not asked for again
    const again = await mountLawyers();
    await again.settle(600);
    assert.equal(api.__calls("matchLawyers").length, 2, "the refresh asked for the deleted case again");
    assert.match(again.text(), /Fill in your Legal Intake first/);
    await again.unmount();
});

test("another account's saved case is not retried, and is forgotten", async () => {
    caseStateSetup("C-OTHER");
    api.__respond("matchLawyers", { data: null, status: 403, error: { message: "You can only match lawyers for your own cases" } });
    const ui = await mountLawyers();
    await ui.settle(600);
    assert.equal(api.__calls("matchLawyers").length, 1);
    assert.match(ui.text(), /Your earlier case is no longer available/);
    assert.equal(readSaved("aai-case-id", "u1"), null);
    await ui.unmount();
});

test("a deleted case named in the address is dropped from the address", async () => {
    caseStateSetup();
    saveIntake("aai-case-id", "u1", null);
    nav().params.set("case_id", "C-URL");
    api.__respond("matchLawyers", { data: null, status: 404, error: { message: "Case not found" } });
    const ui = await mountLawyers();
    await ui.settle(3800);
    assert.equal(api.__calls("matchLawyers")[0].args[0], "C-URL");
    assert.ok(nav().replaced.includes("/lawyers"), "the dead case id stayed in the address");
    assert.match(ui.text(), /Your earlier case is no longer available/);
    nav().params.clear();
    await ui.unmount();
});

test("a real match is still presented as one", async () => {
    caseStateSetup();
    api.__respond("matchLawyers", { data: { result_kind: "matched", notice: null,
        matches: [{ ...lawyer("L1"), match_score: 0.81, match_reason: "specializes in civil" }] } });
    const ui = await mountLawyers();
    await ui.settle(600);
    assert.match(ui.text(), /AI-Recommended Match/);
    assert.match(ui.text(), /81% match score/);
    await ui.unmount();
});

test("View on Map opens the app's map page on this lawyer, not Google Maps", async () => {
    api.__respond("searchLawyers", { data: { items: [lawyer("L1", {
        address: "12 Mall Road, Lahore", lat: 31.5497, lng: 74.3436,
        location_precision: "exact",
    })] }, total: 1, pages: 1 });
    const ui = await mountLawyers();
    await ui.settle();
    await openProfile(ui);

    const btn = [...ui.container.querySelectorAll("button")].find(b => /View on Map/.test(b.textContent));
    await act(async () => {
        btn.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true, cancelable: true }));
    });

    assert.ok(ui.container.querySelector("[data-lawyers-map-page]"), "the map page did not open");
    assert.equal(openedUrls().length, 0, "View on Map left the app");
    const pop = ui.container.querySelector(".lm-pop");
    assert.ok(pop, "the lawyer was not selected on the map");
    assert.match(pop.textContent, /12 Mall Road, Lahore/);
    await ui.unmount();
});
