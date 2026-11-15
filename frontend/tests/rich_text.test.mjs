/* RichText (2026-10-20): model markdown shown as text, safely. */
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>");
for (const n of ["window", "document", "HTMLElement", "Node"]) Object.defineProperty(globalThis, n, { value: dom.window[n], configurable: true, writable: true });
Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { value: true, configurable: true, writable: true });
const React = (await import("react")).default;
const { act } = await import("react");
const { createRoot } = await import("react-dom/client");
const RichText = (await import("../src/components/shared/RichText.jsx")).default;

async function render(text) {
    const box = document.createElement("div");
    document.body.appendChild(box);
    const root = createRoot(box);
    await act(async () => root.render(React.createElement(RichText, { text })));
    return { box, done: () => act(async () => root.unmount()) };
}

test("bold, headings and lists become elements; no asterisks are left", async () => {
    const v = await render("**Issue:**\nWhat is it?\n\n### Applicable law\n- PPC 379\n- CrPC 260\n1. First\n2. Second");
    assert.equal(v.box.querySelector("strong").textContent, "Issue:");
    assert.equal(v.box.querySelectorAll("ul li").length, 2);
    assert.equal(v.box.querySelectorAll("ol li").length, 2);
    assert.doesNotMatch(v.box.textContent, /\*\*|###/);
    await v.done();
});

test("a markdown table becomes a table, without the |---| rule", async () => {
    const v = await render("| # | Right |\n|---|---|\n| 1 | **Life** |\n| 2 | Equality |");
    assert.deepEqual([...v.box.querySelectorAll("th")].map(e => e.textContent), ["#", "Right"]);
    assert.equal(v.box.querySelectorAll("tbody tr").length, 2);
    assert.equal(v.box.querySelector("td strong").textContent, "Life");
    await v.done();
});

test("markup in an answer stays text — nothing is injected", async () => {
    const v = await render("<img src=x onerror=alert(1)> **ok**");
    assert.equal(v.box.querySelector("img"), null);
    assert.match(v.box.textContent, /<img src=x/);
    await v.done();
});

test("italics render without their asterisks; lists keep their bullets", async () => {
    const { box: c, done } = await render("*This is general information.*\n\n- one\n- two\n\n3 * 4 = 12");
    assert.equal(c.querySelector("em")?.textContent, "This is general information.");
    assert.doesNotMatch(c.textContent, /\*This/);
    assert.equal(c.querySelector("ul").style.listStyle, "disc");
    assert.match(c.textContent, /3 \* 4 = 12/, "a lone asterisk in a sum became italics");
});
