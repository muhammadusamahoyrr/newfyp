/* Case law and Cause lists in the app's theme (2026-11-27).
 *
 * The two pages were restyled; these pin what a lawyer relies on: one search
 * box whose mode decides which lookup runs, an empty library that says so, and
 * a cause-list listing that shows its date, case and court.
 *
 * The real components are mounted against the API stub.
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
const { CaseLawPage } = await import("../src/components/lawyer/CaseLawPage.jsx");
const { CauselistPage } = await import("../src/components/lawyer/CauselistPage.jsx");
const { createElement: h } = React;

const settle = () => act(async () => { await new Promise(r => setTimeout(r, 20)); });
async function mount(Comp) {
    const container = dom.window.document.createElement("div");
    dom.window.document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => { root.render(h(Comp)); });
    await settle();
    return { container, unmount: async () => { await act(async () => root.unmount()); container.remove(); } };
}
async function press(el) {
    assert.ok(el, "control missing");
    await act(async () => { el.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
    await settle();
}
async function type(el, value) {
    Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value").set.call(el, value);
    await act(async () => { el.dispatchEvent(new dom.window.Event("input", { bubbles: true })); });
}
const button = (root, text) => [...root.querySelectorAll("button")].find(b => b.textContent.trim() === text);

test("case law: an empty library says so instead of a blank page", async () => {
    api.__reset();
    api.__respond("citatorStats", { data: { judgments: 0, citation_edges: 0 } });
    const ui = await mount(CaseLawPage);
    assert.equal(ui.container.querySelector("[data-caselaw-empty]").getAttribute("data-caselaw-empty"), "library");
    assert.match(ui.container.querySelector("[data-caselaw-stats]").textContent, /0 judgments/);
    await ui.unmount();
});

test("case law: the mode tab decides which lookup the one box runs", async () => {
    api.__reset();
    api.__respond("citatorStats", { data: { judgments: 5, citation_edges: 9 } });
    api.__respond("citatorSearch", { data: [{ id: "j1", title: "Ali v. State", pdf_url: "https://x/1.pdf" }] });
    api.__respond("citatorCitedBy", { data: { citation: "PLD 2019 SC 675", count: 0, cited_by: [] } });
    const ui = await mount(CaseLawPage);
    const input = () => ui.container.querySelector("[data-caselaw] input");

    await type(input(), "bail in narcotics");
    await press(button(ui.container, "Search"));
    assert.equal(api.__calls("citatorSearch").length, 1);
    assert.match(ui.container.querySelector("[data-caselaw-results]").textContent, /Ali v\. State/);

    await press(button(ui.container, "Who cites this?"));
    await type(input(), "PLD 2019 SC 675");
    await press(button(ui.container, "Find citing judgments"));
    assert.equal(api.__calls("citatorCitedBy").length, 1);
    assert.equal(api.__calls("citatorCitedBy")[0].args[0], "PLD 2019 SC 675");
    assert.equal(api.__calls("citatorSearch").length, 1, "the citator ran a text search too");
    await ui.unmount();
});

test("cause lists: a listing shows its case and court, and a watch can be removed", async () => {
    api.__reset();
    api.__respond("listCauselistWatches", { data: [{ id: "w1", case_no: "39043/26", title_hint: "Fayyaz bail" }] });
    api.__respond("listCauselistEntries", { data: [{ id: "e1", case_no: "39043/26", title: "Fayyaz v. State",
        hearing_date: "2026-12-01", judge: "Mr. Justice A", court_room: "Court 4", seq: 12, list_type: "Main" }] });
    api.__respond("deleteCauselistWatch", { data: {} });
    const ui = await mount(CauselistPage);
    const row = ui.container.querySelector('[data-listing="e1"]');
    assert.ok(row, "the listing is not shown");
    assert.match(row.textContent, /39043\/26/);
    assert.match(row.textContent, /Mr\. Justice A · Court 4 · Seq #12/);
    await press(ui.container.querySelector('[aria-label="Stop watching 39043/26"]'));
    assert.equal(api.__calls("deleteCauselistWatch")[0].args[0], "w1");
    await ui.unmount();
});

/* 2026-11-28 (layout A): the paste box is folded until asked for, and the
 * watch bar sits first. */
test("cause lists: the paste box opens on 'Paste a list' and then scans the text", async () => {
    api.__reset();
    api.__respond("listCauselistWatches", { data: [] });
    api.__respond("listCauselistEntries", { data: [] });
    api.__respond("matchCauselistText", { data: [{ case_no: "39043/26", line: "12. 39043/26 Fayyaz v State" }] });
    const ui = await mount(CauselistPage);
    const paste = ui.container.querySelector("[data-paste]");
    assert.equal(paste.querySelector("textarea"), null, "the paste box is open before it was asked for");
    const first = ui.container.querySelector("[data-causelist] section");
    assert.ok(first.hasAttribute("data-watch-bar"), "the watch bar is not the first section");
    await press(button(paste, "Paste a list ▾"));
    const box = paste.querySelector("textarea");
    assert.ok(box, "Paste a list did not open the box");
    Object.getOwnPropertyDescriptor(dom.window.HTMLTextAreaElement.prototype, "value").set.call(box, "12. 39043/26 Fayyaz v State");
    await act(async () => { box.dispatchEvent(new dom.window.Event("input", { bubbles: true })); });
    await press(button(paste, "Find my cases"));
    assert.equal(api.__calls("matchCauselistText").length, 1);
    assert.match(paste.textContent, /1 match found/);
    await ui.unmount();
});
