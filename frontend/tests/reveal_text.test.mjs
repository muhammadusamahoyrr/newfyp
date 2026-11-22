/* RevealText types out an already-checked answer (2026-11-22). */
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/" });
for (const n of ["window", "document", "navigator", "HTMLElement", "Node", "Event", "MouseEvent"]) {
    Object.defineProperty(globalThis, n, { value: dom.window[n], writable: true, configurable: true });
}
Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { value: true, writable: true, configurable: true });

// A hand-driven clock: each frame advances time by `step` ms.
let now = 0; let queue = [];
window.requestAnimationFrame = (cb) => { queue.push(cb); return queue.length; };
window.cancelAnimationFrame = () => {};
globalThis.performance = { now: () => now };
async function frames(n, step = 100) {
    for (let i = 0; i < n; i++) {
        now += step; const q = queue; queue = [];
        await act(async () => { q.forEach(cb => cb(now)); });
    }
}

const React = (await import("react")).default;
const { act } = await import("react");
const { createRoot } = await import("react-dom/client");
const RevealText = (await import("../src/components/shared/RevealText.jsx")).default;
const RichText = (await import("../src/components/shared/RichText.jsx")).default;
const h = React.createElement;

async function mount(props) {
    const el = document.createElement("div"); document.body.appendChild(el);
    const root = createRoot(el);
    await act(async () => { root.render(h(RevealText, { render: t => h(RichText, { text: t }), ...props })); });
    return { el, unmount: async () => { await act(async () => root.unmount()); el.remove(); } };
}

const ANSWER = "Theft is punished under **section 379 PPC** with imprisonment of up to three years, a fine, or both. "
    + "Consult a lawyer for your facts.";

test("a live answer types out, and ends complete with onDone once", async () => {
    now = 0; queue = [];
    let done = 0;
    const ui = await mount({ text: ANSWER, animate: true, onDone: () => done++ });
    await frames(3);
    const partial = ui.el.textContent;
    assert.ok(partial.length > 0 && partial.length < ANSWER.replace(/\*\*/g, "").length, "it did not type");
    assert.ok(!partial.includes("**"), "raw asterisks were shown while typing");
    await frames(30);
    assert.equal(ui.el.textContent, ANSWER.replace(/\*\*/g, ""));
    assert.ok(ui.el.querySelector("strong"), "bold did not render");
    assert.equal(done, 1);
    await ui.unmount();
});

test("it never takes longer than about two seconds", async () => {
    now = 0; queue = [];
    const long = Array.from({ length: 900 }, (_, i) => `word${i}`).join(" ");
    const ui = await mount({ text: long, animate: true });
    await frames(21, 100);                       // 2.1 s
    assert.equal(ui.el.textContent, long);
    await ui.unmount();
});

test("a click shows the whole answer at once", async () => {
    now = 0; queue = [];
    let done = 0;
    const ui = await mount({ text: ANSWER, animate: true, onDone: () => done++ });
    await frames(1);
    await act(async () => { ui.el.querySelector("[data-revealing-text]").dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    assert.equal(ui.el.textContent, ANSWER.replace(/\*\*/g, ""));
    assert.equal(done, 1);
    await ui.unmount();
});

test("restored history (animate off) is shown immediately", async () => {
    now = 0; queue = [];
    const ui = await mount({ text: ANSWER, animate: false });
    assert.equal(ui.el.textContent, ANSWER.replace(/\*\*/g, ""));
    assert.equal(queue.length, 0, "it scheduled frames for an answer that should not type");
    await ui.unmount();
});
