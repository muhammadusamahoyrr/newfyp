/* Bail checker V4 (2026-11-27): matches appear as cards while typing, each
 * card's Before / After arrest asks the server, and a slow reply for an older
 * search never replaces the newer results.
 *
 * The real component is mounted against the API stub.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/" });
function define(name, value) {
    Object.defineProperty(globalThis, name, { value, writable: true, configurable: true });
}
for (const name of ["window", "document", "navigator", "HTMLElement", "Element", "Node",
                    "Event", "CustomEvent", "MutationObserver", "getComputedStyle", "sessionStorage", "localStorage"]) {
    define(name, dom.window[name]);
}
define("IS_REACT_ACT_ENVIRONMENT", true);

const React = (await import("react")).default;
const { act } = await import("react");
const { createRoot } = await import("react-dom/client");
const api = await import("./support/api-stub.mjs");
const { BailCheckerPage } = await import("../src/components/lawyer/LegalToolsPage.jsx");
const { createElement: h } = React;

const wait = (ms) => act(async () => { await new Promise(r => setTimeout(r, ms)); });
async function mount() {
    const container = dom.window.document.createElement("div");
    dom.window.document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => { root.render(h(BailCheckerPage)); });
    await wait(20);
    return { container, unmount: async () => { await act(async () => root.unmount()); container.remove(); } };
}
async function type(el, value) {
    Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value").set.call(el, value);
    await act(async () => { el.dispatchEvent(new dom.window.Event("input", { bubbles: true })); });
}
async function press(el) {
    assert.ok(el, "control missing");
    await act(async () => { el.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
    await wait(20);
}

const HIT = { id: "ppc-302", law: "PPC", section: "302", title: "Qatl-i-amd", bailable: false, punishment: "P", court: "C" };
const CHECK = { found: true, confidence: "established",
    offence: { law: "PPC", section: "302", title: "Qatl-i-amd", bailable: false, cognizable: true, compoundable: true, prohibitory: true },
    guidance: { summary: "Apply to the court", sections: ["CrPC 497"], steps: ["First step", "Second step"] },
    legal_basis: "Basis", disclaimer: "Disclaimer" };

test("typing shows the matches as cards, without pressing anything", async () => {
    api.__reset();
    api.__respond("bailSearch", { data: { results: [HIT] } });
    const ui = await mount();
    await type(ui.container.querySelector("[data-bail-search]"), "302");
    await wait(450);
    assert.equal(api.__calls("bailSearch").length, 1);
    assert.equal(api.__calls("bailSearch")[0].args[0], "302");
    assert.ok(ui.container.querySelector('[data-bail-hit="ppc-302"]'), "no card for the match");
    await ui.unmount();
});

test("After arrest on a card checks that offence as arrested and shows its steps", async () => {
    api.__reset();
    api.__respond("bailSearch", { data: { results: [HIT] } });
    api.__respond("bailCheck", { data: CHECK });
    const ui = await mount();
    await type(ui.container.querySelector("[data-bail-search]"), "302");
    await wait(450);
    const card = ui.container.querySelector('[data-bail-hit="ppc-302"]');
    await press([...card.querySelectorAll("button")].find(b => b.textContent === "After arrest"));
    const call = api.__calls("bailCheck")[0].args[0];
    assert.deepEqual(call, { law: "PPC", section: "302", arrested: true });
    const result = ui.container.querySelector("[data-bail-result]");
    assert.match(result.textContent, /after arrest/);
    assert.match(result.textContent, /First step/);
    assert.match(result.textContent, /prohibitory clause/);
    await ui.unmount();
});

test("a slow reply for an older search does not replace the newer results", async () => {
    api.__reset();
    let release;
    const slow = new Promise(r => { release = r; });
    let n = 0;
    api.__respond("bailSearch", () => (++n === 1 ? slow : { data: { results: [HIT] } }));
    const ui = await mount();
    const input = ui.container.querySelector("[data-bail-search]");
    await type(input, "30");
    await wait(450);
    await type(input, "302");
    await wait(450);
    assert.ok(ui.container.querySelector('[data-bail-hit="ppc-302"]'));
    await act(async () => { release({ data: { results: [] } }); });
    await wait(20);
    assert.ok(ui.container.querySelector('[data-bail-hit="ppc-302"]'), "the older empty reply wiped the newer results");
    await ui.unmount();
});
