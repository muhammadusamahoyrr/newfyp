import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/" });
function define(name, value) {
    Object.defineProperty(globalThis, name, { value, writable: true, configurable: true });
}
for (const name of ["window", "document", "navigator", "HTMLElement", "HTMLInputElement", "Element",
                    "Node", "Event", "CustomEvent", "MouseEvent", "KeyboardEvent", "MutationObserver",
                    "getComputedStyle", "localStorage", "sessionStorage", "requestAnimationFrame",
                    "cancelAnimationFrame"]) {
    define(name, dom.window[name]);
}
if (!dom.window.HTMLElement.prototype.scrollIntoView) dom.window.HTMLElement.prototype.scrollIntoView = () => {};
dom.window.confirm = () => true;
define("confirm", dom.window.confirm);
define("IS_REACT_ACT_ENVIRONMENT", true);

const React = (await import("react")).default;
const { act } = await import("react");
const { createRoot } = await import("react-dom/client");
const api = await import("./support/api-stub.mjs");
const { AuthProvider } = await import("../src/context/AuthContext.jsx");
const { CaseCtx } = await import("../src/components/lawyer/theme.js");
const { AILegalPage } = await import("../src/components/lawyer/AILegalPage.jsx");
const h = React.createElement;

const settle = (ms = 40) => act(async () => { await new Promise(r => setTimeout(r, ms)); });

function serve({ turn, rows = [] } = {}) {
    api.__reset();
    api.__respond("bootstrapAuth", true);
    api.__respond("getMe", { data: { _id: "l1", role: "lawyer", full_name: "Lawyer" }, error: null });
    api.__respond("listCases", { data: { items: [] }, error: null });
    api.__respond("listResearchConversations", { data: { conversations: rows, next_cursor: null }, error: null });
    api.__respond("createResearchConversation", { data: { session_id: "s1" }, error: null });
    api.__respond("getResearchConversation", (sid) => ({ data: { session_id: sid, case_id: null, messages: [] }, error: null }));
    if (turn) api.__respond("aiResearch", turn);
}

async function mount() {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => {
        root.render(h(AuthProvider, null,
            h(CaseCtx.Provider, { value: { activeCase: null, setActiveCase: () => {} } }, h(AILegalPage))));
    });
    await settle(150);
    return { container, unmount: async () => { await act(async () => root.unmount()); container.remove(); } };
}

async function ask(container, question = "What applies?") {
    const box = container.querySelector('textarea[placeholder="Ask Attorney AI..."]');
    const setter = { call: (el, v) => Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), "value").set.call(el, v) };
    await act(async () => { setter.call(box, question); box.dispatchEvent(new Event("input", { bubbles: true })); });
    await act(async () => { box.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })); });
    await settle(100);
}


/* Leaving the research page stops its background requests (audit 2026-11-22 #10).
 *
 * WHAT WAS WRONG. Nothing ran on unmount. A lawyer who asked a question and
 * opened another page left behind: the stage poll (one request every 2 s until
 * the answer landed, up to 150 s), the retry after a dropped send, and the
 * busy-wait resend loop (every 5 s for up to another 150 s).
 *
 * The question itself is still answered and filed by the server; only the
 * page's own polling stops.
 */
test("leaving mid-answer stops the stage poll and the retry", async () => {
    serve();
    api.__respond("researchTurnStatus", { data: { status: "in_progress", label: "Searching" }, error: null });
    // Slow, then an AMBIGUOUS failure (502): on a page that is still open this
    // is retried with the same id. After leaving it must not be.
    api.__respond("aiResearch", () => new Promise(r => setTimeout(
        () => r({ data: null, status: 502, error: { message: "Bad gateway" } }), 2600)));

    const view = await mount();
    await ask(view.container);
    assert.equal(api.__calls("aiResearch").length, 1);
    await view.unmount();

    // Past the first 2 s stage tick and past the slow send's failure.
    await new Promise(r => setTimeout(r, 3200));
    assert.equal(api.__calls("researchTurnStatus").length, 0, "the stage poll kept running after leaving");
    assert.equal(api.__calls("aiResearch").length, 1, "the send was retried after leaving");
});

test("while the page stays open the stage poll still runs", async () => {
    serve();
    api.__respond("researchTurnStatus", { data: { status: "in_progress", label: "Searching" }, error: null });
    api.__respond("aiResearch", () => new Promise(r => setTimeout(
        () => r({ data: { answer: "Done.", citations: [], request_id: "r1" }, error: null, status: 200 }), 2600)));

    const view = await mount();
    await ask(view.container);
    await settle(2800);
    assert.ok(api.__calls("researchTurnStatus").length >= 1, "the guard stopped a poll on an open page");
    await view.unmount();
});
