/* Calculators, style A (2026-11-27): the result side is laid out before the
 * first calculation (chosen heirs as rows with no numbers yet), the server's
 * answer then fills it, and the labour total sits on top.
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
const { CalculatorsPage } = await import("../src/components/lawyer/LegalToolsPage.jsx");
const { createElement: h } = React;

const wait = (ms = 20) => act(async () => { await new Promise(r => setTimeout(r, ms)); });
async function mount() {
    const container = dom.window.document.createElement("div");
    dom.window.document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => { root.render(h(CalculatorsPage)); });
    await wait();
    return { container, unmount: async () => { await act(async () => root.unmount()); container.remove(); } };
}
async function press(el) {
    assert.ok(el, "control missing");
    await act(async () => { el.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
    await wait();
}
async function type(el, value) {
    Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value").set.call(el, value);
    await act(async () => { el.dispatchEvent(new dom.window.Event("input", { bubbles: true })); });
}
const button = (root, text) => [...root.querySelectorAll("button")].find(b => b.textContent.trim() === text);

test("inheritance: chosen heirs show as rows before any calculation, with no numbers", async () => {
    api.__reset();
    const ui = await mount();
    await press(button(ui.container, "Inheritance"));
    await press(ui.container.querySelector('[aria-label="More Sons"]'));
    await press(ui.container.querySelector('[aria-label="More Sons"]'));
    await press(ui.container.querySelector('[aria-label="More Wives"]'));
    const rows = [...ui.container.querySelectorAll("[data-pending-heir]")];
    assert.deepEqual(rows.map(r => r.getAttribute("data-pending-heir")), ["wives", "sons"]);
    assert.match(rows[1].textContent, /Sons \(2\)/);
    assert.doesNotMatch(rows[1].textContent, /Rs/, "a number was shown before the server answered");
    assert.equal(api.__calls("inheritanceCalculate").length, 0);
    await ui.unmount();
});

test("inheritance: Calculate shares sends the heirs and fills the table from the answer", async () => {
    api.__reset();
    api.__respond("inheritanceCalculate", { data: { estate_value: 1000, school: "Hanafi",
        breakdown: [{ heir: "Son", fraction: "1/1", percentage: 100, amount: 1000 }], notes: [], warnings: [], disclaimer: "D" } });
    const ui = await mount();
    await press(button(ui.container, "Inheritance"));
    await press(ui.container.querySelector('[aria-label="More Sons"]'));
    await type(ui.container.querySelector("#ih-estate"), "1000");
    await press(button(ui.container, "Calculate shares"));
    const [estate, heirs] = api.__calls("inheritanceCalculate")[0].args;
    assert.equal(estate, 1000);
    assert.equal(heirs.sons, 1);
    const box = ui.container.querySelector('[data-calc-result="inheritance"]');
    assert.match(box.textContent, /Distribution of Rs 1,000/);
    assert.equal(box.querySelector("[data-pending-heir]"), null, "the placeholder rows stayed after the answer");
    await ui.unmount();
});

test("labour dues: the total sits on top once calculated, a dash before", async () => {
    api.__reset();
    api.__respond("labourDuesCalculate", { data: { total: 75000, breakdown: [{ item: "Gratuity", amount: 75000 }],
        legal_basis: "Basis", remedy: "Claim at the labour court", disclaimer: "D" } });
    const ui = await mount();
    await press(button(ui.container, "Labour dues"));
    const box = () => ui.container.querySelector('[data-calc-result="labour"]');
    assert.match(box().textContent, /Rs —/);
    await type(ui.container.querySelector("#ld-monthly_wage"), "50000");
    await press(button(ui.container, "Calculate dues"));
    assert.match(box().querySelector(".lt-band").textContent, /Rs 75,000/);
    assert.match(box().textContent, /Claim at the labour court/);
    await ui.unmount();
});
