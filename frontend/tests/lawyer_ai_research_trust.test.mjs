/* Lawyer AI Research: what the claim checks claim, and where a question goes
 * when something fails (2026-10-14).
 *
 * WHAT WAS WRONG.
 *   * A claim the automated checks passed was labelled "Supported ✓ — cited
 *     source establishes this". A live probe showed that label on a wrong
 *     limitation period and on an irrelevant statute. It read as a verified
 *     legal conclusion; it is the output of a model judge plus fixed rules.
 *   * A guard's reason for downgrading a claim ("issue relevance not
 *     established ...") was sent by the server and never shown.
 *   * send() emptied the box BEFORE creating the conversation, so a failed
 *     create threw the lawyer's question away.
 *   * Switching case emptied the box, so a typed question was lost -- and the
 *     "Key arguments" button, which sets the case and the question together,
 *     lost its question immediately.
 */
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
define("IS_REACT_ACT_ENVIRONMENT", true);

const React = (await import("react")).default;
const { act, useState } = await import("react");
const { createRoot } = await import("react-dom/client");
const api = await import("./support/api-stub.mjs");
const { AuthProvider } = await import("../src/context/AuthContext.jsx");
const { CaseCtx } = await import("../src/components/lawyer/theme.js");
const { AILegalPage } = await import("../src/components/lawyer/AILegalPage.jsx");
const h = React.createElement;

const settle = (ms = 40) => act(async () => { await new Promise(r => setTimeout(r, ms)); });

const CASES = [
    { _id: "665f00000000000000000001", case_number: "CIV-2026-001", title: "Rent dispute",
      case_type: "civil", province: "punjab", client_name: "Ayesha" },
    { _id: "665f00000000000000000002", case_number: "CRM-2026-002", title: "Cheque case",
      case_type: "criminal", province: "punjab", client_name: "Bilal" },
];

function serve({ create = null, turn = null } = {}) {
    let n = 0;
    // The page remembers the open conversation; a test must start without one.
    localStorage.clear(); sessionStorage.clear();
    api.__reset();
    api.__respond("bootstrapAuth", true);
    api.__respond("getMe", { data: { _id: "l1", role: "lawyer", full_name: "Lawyer" }, error: null });
    api.__respond("listCases", { data: { items: CASES }, error: null });
    api.__respond("listResearchConversations", { data: { conversations: [], next_cursor: null }, error: null });
    api.__respond("createResearchConversation", create
        || (({ caseId } = {}) => ({ data: { session_id: `s${++n}`, case_id: caseId || null }, error: null })));
    api.__respond("getResearchConversation", (sid) => ({ data: { session_id: sid, case_id: null, messages: [] }, error: null }));
    if (turn) api.__respond("aiResearch", turn);
}

// The case context is real state here, so a test can switch case the way the
// case switcher does.
let switchCase;
function Host() {
    const [activeCase, setActiveCase] = useState(null);
    switchCase = setActiveCase;
    return h(CaseCtx.Provider, { value: { activeCase, setActiveCase } }, h(AILegalPage));
}

async function mount() {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => { root.render(h(AuthProvider, null, h(Host))); });
    await settle(150);
    return { container, unmount: async () => { await act(async () => root.unmount()); container.remove(); } };
}

const box = (c) => c.querySelector('input[placeholder="Ask Attorney AI..."]');

async function type(container, text) {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
    await act(async () => { setter.call(box(container), text); box(container).dispatchEvent(new Event("input", { bubbles: true })); });
}

async function enter(container) {
    await act(async () => { box(container).dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })); });
    await settle(100);
}

const answered = (claims) => ({
    data: { answer: "Section 489-F PPC applies.", citations: [], claims }, error: null, status: 200,
});

test("claim verdicts say they are automated checks, not established law", async () => {
    serve({ turn: answered([
        { text: "Section 489-F PPC covers a dishonoured cheque.", support: "supported", source_ids: ["S1"] },
        { text: "The limitation period is three years.", support: "unsupported", source_ids: ["S2"] },
        { text: "Something unchecked.", support: "unassessed", source_ids: [] },
    ]) });
    const view = await mount();
    await type(view.container, "What applies to a bounced cheque?");
    await enter(view.container);
    const text = view.container.textContent;
    assert.match(text, /Automated evidence check \(3 claims\)/);
    assert.match(text, /Automated check: supported/);
    assert.match(text, /Automated check: not supported/);
    assert.match(text, /Not verified/);
    assert.match(text, /not a guarantee of legal correctness/);
    // The old wording asserted a legal conclusion.
    assert.doesNotMatch(text, /cited source establishes this/);
    assert.doesNotMatch(text, /Claim support/);
    await view.unmount();
});

test("a guard's reason for downgrading a claim is shown", async () => {
    serve({ turn: answered([
        { text: "Land Revenue Act s.91 gives a remedy.", support: "unassessed", source_ids: ["S1"],
          support_reason: "issue relevance not established by the automated check" },
    ]) });
    const view = await mount();
    await type(view.container, "Remedy for unpaid rent?");
    await enter(view.container);
    assert.match(view.container.textContent, /issue relevance not established by the automated check/);
    await view.unmount();
});

test("a failed conversation create keeps the question in the box", async () => {
    serve({
        create: { data: null, status: 500, error: { message: "Server down" } },
        turn: answered([]),
    });
    const view = await mount();
    await type(view.container, "Is a pre-arrest bail available under 489-F?");
    await enter(view.container);
    assert.equal(box(view.container).value, "Is a pre-arrest bail available under 489-F?");
    assert.match(view.container.textContent, /still in the box/);
    assert.equal(api.__calls("aiResearch").length, 0, "a turn was sent without a conversation");
    await view.unmount();
});

test("switching case keeps a typed question", async () => {
    serve({ turn: answered([]) });
    const view = await mount();
    await type(view.container, "Draft the key grounds of appeal");
    const created = api.__calls("createResearchConversation").length;
    await act(async () => { switchCase(CASES[1].case_number); });
    await settle(150);
    assert.ok(api.__calls("createResearchConversation").length > created, "switching case did not start a bound conversation");
    assert.equal(box(view.container).value, "Draft the key grounds of appeal");
    await view.unmount();
});

test("claims withdrawn from the answer are counted, not listed as if the answer made them", async () => {
    // Live eval F1 (2026-10-14): the answer was replaced by "couldn't find the
    // text of Section 337-A", yet five draft claims were still listed under it.
    serve({ turn: answered([
        { text: "Section 337-A PPC applies.", support: "supported", source_ids: ["S1"] },
        { text: "Shajjah-i-khafifah carries two years.", support: "unsupported", source_ids: ["S1"],
          removed_from_answer: true },
        { text: "It is compoundable.", support: "unsupported", source_ids: ["S1"], removed_from_answer: true },
    ]) });
    const view = await mount();
    await type(view.container, "What is Section 337-A PPC?");
    await enter(view.container);
    const text = view.container.textContent;
    assert.match(text, /Automated evidence check \(1 claim\)/);
    assert.match(text, /2 statements from the draft were withdrawn/);
    assert.doesNotMatch(text, /carries two years/);
    assert.doesNotMatch(text, /It is compoundable/);
    await view.unmount();
});
