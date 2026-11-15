/* The client chat's answer actions (2026-10-19): Copy, Helpful, Not helpful as
 * plain line icons -- no emoji, no reference chip -- as chat apps show them. */
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/" });
for (const name of ["window", "document", "navigator", "HTMLElement", "Element", "Node", "Event"]) {
    Object.defineProperty(globalThis, name, { value: dom.window[name], writable: true, configurable: true });
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const copied = [];
Object.defineProperty(dom.window.navigator, "clipboard", { value: { writeText: async v => { copied.push(v); } }, configurable: true });

const React = (await import("react")).default;
const { act } = await import("react");
const { createRoot } = await import("react-dom/client");
const { MessageActions } = await import("../src/components/client/ModChatbot.jsx");

const T = { textMuted: "#888", text: "#fff", border: "#333" };
async function mount(props) {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => { root.render(React.createElement(MessageActions, { t: T, text: "The answer.", ...props })); });
    return { container, rerender: p => act(async () => root.render(React.createElement(MessageActions, { t: T, text: "The answer.", ...props, ...p }))),
             unmount: () => act(async () => root.unmount()) };
}
const click = el => act(async () => { el.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });

test("Copy, Helpful and Not helpful are icon buttons with names, and no emoji or reference chip", async () => {
    const p = await mount({ canRate: true, rated: null, onRate: () => {} });
    const labels = [...p.container.querySelectorAll("button")].map(b => b.getAttribute("aria-label"));
    assert.deepEqual(labels, ["Copy", "Helpful", "Not helpful"]);
    assert.equal(p.container.querySelectorAll("button svg").length, 3, "every action is a line icon");
    assert.doesNotMatch(p.container.textContent, /👍|👎|ref /, "an emoji or the reference chip is back");
    await p.unmount();
});

test("Copy copies the answer and turns into a check for a moment", async () => {
    const p = await mount({ canRate: false });
    await click(p.container.querySelector('[aria-label="Copy"]'));
    assert.deepEqual(copied.slice(-1), ["The answer."]);
    assert.ok(p.container.querySelector('[aria-label="Copied"]'), "no sign that it was copied");
    await p.unmount();
});

test("a rating sends once, then only the chosen icon stays, filled", async () => {
    const rated = [];
    const p = await mount({ canRate: true, rated: null, onRate: r => rated.push(r) });
    await click(p.container.querySelector('[aria-label="Not helpful"]'));
    assert.deepEqual(rated, ["down"]);
    await p.rerender({ rated: "down" });
    const left = [...p.container.querySelectorAll("button")].map(b => b.getAttribute("aria-label"));
    assert.deepEqual(left, ["Copy", "Not helpful"]);
    const chosen = p.container.querySelector('[aria-label="Not helpful"]');
    assert.equal(chosen.getAttribute("aria-pressed"), "true");
    assert.equal(chosen.disabled, true, "a second rating could be sent");
    assert.equal(chosen.querySelector("svg").getAttribute("fill"), "currentColor");
    await p.unmount();
});

test("an answer that cannot be rated still offers Copy", async () => {
    const p = await mount({ canRate: false });
    assert.deepEqual([...p.container.querySelectorAll("button")].map(b => b.getAttribute("aria-label")), ["Copy"]);
    await p.unmount();
});

test("Regenerate is offered only when the caller asks for it, and is a small line icon", async () => {
    let asked = 0;
    const p = await mount({ canRate: true, rated: null, onRate: () => {}, onRegenerate: () => { asked += 1; } });
    const labels = [...p.container.querySelectorAll("button")].map(b => b.getAttribute("aria-label"));
    assert.deepEqual(labels, ["Copy", "Helpful", "Not helpful", "Regenerate"]);
    await click(p.container.querySelector('[aria-label="Regenerate"]'));
    assert.equal(asked, 1);
    assert.equal(p.container.querySelector("svg").getAttribute("width"), "15", "the icons are not the smaller size");
    await p.unmount();
    const q = await mount({ canRate: false });
    assert.equal(q.container.querySelector('[aria-label="Regenerate"]'), null, "Regenerate shown on an answer that is not the last");
    await q.unmount();
});
