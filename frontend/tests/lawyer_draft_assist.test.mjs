/* Lawyer Draft Assistant (2026-10-14): the reply is a proposal, never an overwrite.
 *
 * THE BUG. `sendToAI` set `editor.innerText = reply` whenever the reply looked
 * long enough to be a document. A template's centred headings, numbered "That
 * ..." paragraphs and bold clause titles were wiped by any request -- even "add
 * a confidentiality clause" -- and the lawyer could not get them back.
 *
 * Now: the reply appears as a card; the lawyer inserts it at the cursor, swaps
 * it for the selected text, or explicitly replaces the draft. A selection makes
 * the request a REWRITE of that passage only.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

import { quickActionsFor, modeFor, proposalToHtml, MODES } from "../src/lib/draftAssist.js";

/* ── pure rules ──────────────────────────────────────────────────────────── */

test("quick actions fit the document type", () => {
    const labels = cat => quickActionsFor(cat).map(a => a.label);
    assert.ok(labels("Application / Petition").includes("Stronger prayer"));
    assert.ok(labels("Agreement / Contract").includes("Confidentiality"));
    assert.ok(!labels("Notice / Letter").includes("Stronger prayer"), "a letter has no prayer");
    assert.ok(labels("Notice / Letter").includes("Formal tone"));
    for (const cat of ["Application / Petition", "Agreement / Contract", "Business / Commercial", "Notice / Letter", "General"]) {
        for (const a of quickActionsFor(cat)) assert.ok(MODES[a.mode], `${cat}/${a.label}: unknown mode ${a.mode}`);
    }
});

test("a selection means rewrite; nothing selected never means overwrite", () => {
    assert.equal(modeFor({ chosen: null, hasSelection: true }), "rewrite");
    assert.equal(modeFor({ chosen: null, hasSelection: false }), "clause");
    assert.equal(modeFor({ chosen: "rewrite", hasSelection: false }), "clause", "nothing to rewrite");
    assert.equal(modeFor({ chosen: "full", hasSelection: true }), "full", "an explicit choice is kept");
});

test("a short numbered clause title is bold; a numbered 'That ...' paragraph is not", () => {
    assert.equal(proposalToHtml("10. CONFIDENTIALITY"), "<p><strong>10. CONFIDENTIALITY</strong></p>");
    assert.equal(proposalToHtml("4. Security Deposit"), "<p><strong>4. Security Deposit</strong></p>");
    assert.doesNotMatch(proposalToHtml("5. That the Applicant has no previous criminal record."), /<strong>/);
    assert.doesNotMatch(proposalToHtml("5. That the Applicant undertakes to appear"), /<strong>/);
});

test("a proposal becomes escaped paragraphs with bold headings", () => {
    const html = proposalToHtml("CONFIDENTIALITY\n\nEach party shall keep <secret> terms confidential.\nThis survives termination.\n\n**Exceptions:**");
    assert.equal(html, "<p><strong>CONFIDENTIALITY</strong></p>" +
        "<p>Each party shall keep &lt;secret&gt; terms confidential.<br>This survives termination.</p>" +
        "<p><strong>Exceptions:</strong></p>");
    assert.doesNotMatch(proposalToHtml("<img src=x onerror=alert(1)>"), /<img/);
    assert.equal(proposalToHtml("```\n1. That the applicant ...\n```"), "<p>1. That the applicant ...</p>", "fences dropped; a numbered line is not a heading");
});

/* ── the page, mounted ───────────────────────────────────────────────────── */

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/" });
function define(name, value) {
    Object.defineProperty(globalThis, name, { value, writable: true, configurable: true });
}
for (const name of ["window", "document", "navigator", "HTMLElement", "Element", "Node",
                    "Event", "CustomEvent", "MutationObserver", "getComputedStyle",
                    "localStorage", "requestAnimationFrame", "cancelAnimationFrame"]) {
    define(name, dom.window[name]);
}
define("IS_REACT_ACT_ENVIRONMENT", true);
dom.window.HTMLElement.prototype.scrollIntoView = function () {};
Object.defineProperty(dom.window.HTMLElement.prototype, "innerText", {
    get() { return this.textContent; }, set(v) { this.textContent = v; }, configurable: true,
});
dom.window.document.queryCommandState = () => false;
// jsdom has no execCommand: just enough of insertHTML / selectAll, on its real Range API.
dom.window.document.execCommand = (cmd, _ui, value) => {
    const sel = dom.window.getSelection();
    if (cmd === "selectAll") {
        const ed = dom.window.document.querySelector(".de-paper");
        const r = dom.window.document.createRange(); r.selectNodeContents(ed);
        sel.removeAllRanges(); sel.addRange(r);
    } else if (cmd === "insertParagraph" && sel.rangeCount) {
        // A new empty paragraph after the caret's block; the caret moves into it.
        const r = sel.getRangeAt(0);
        const ed = dom.window.document.querySelector(".de-paper");
        let block = r.startContainer.nodeType === 1 ? r.startContainer : r.startContainer.parentElement;
        while (block && block.parentElement !== ed && block !== ed) block = block.parentElement;
        const p = dom.window.document.createElement("p");
        if (block && block !== ed) block.after(p); else ed.appendChild(p);
        const nr = dom.window.document.createRange(); nr.selectNodeContents(p);
        sel.removeAllRanges(); sel.addRange(nr);
    } else if (cmd === "insertHTML" && sel.rangeCount) {
        const r = sel.getRangeAt(0);
        r.deleteContents();
        r.insertNode(r.createContextualFragment(value));
    }
    return true;
};
let confirmAnswer = true;
dom.window.confirm = () => confirmAnswer;

const React = (await import("react")).default;
const { act } = await import("react");
const { createRoot } = await import("react-dom/client");
const api = await import("./support/api-stub.mjs");
const { createElement: h } = React;

let reply = "";
// The server's legal-check frame. undefined = a passing check of `reply` (what
// a healthy server sends); null = no guard frame at all; an object = that frame.
let guard;
// Runs inside the request, before the reply arrives: the lawyer acting while
// the model is still writing.
let during = null;
// Every request the page sent (its instruction etc.).
let sent = [];
function stubAI() {
    api.__respond("aiDraftStream", async (args, onToken, onEvent) => {
        sent.push(args);
        if (during) await during();
        if (reply) onToken(reply);
        const g = guard === undefined ? { ran: true, text: reply, withheld: [], supported: [], not_checked: [] } : guard;
        if (g && onEvent) onEvent({ guard: g });
    });
}

async function mountOn(templateName, { jurisdiction = "unknown", activeCase = null } = {}) {
    const { DocAutomationPage } = await import("../src/components/lawyer/DocAutomationPage.jsx");
    const { AuthProvider } = await import("../src/context/AuthContext.jsx");
    const { ThemeCtx, CaseCtx, DARK } = await import("../src/components/lawyer/theme.js");
    const container = dom.window.document.createElement("div");
    dom.window.document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => {
        root.render(h(AuthProvider, null, h(ThemeCtx.Provider, { value: DARK },
            h(CaseCtx.Provider, { value: { activeCase, setPage() {} } }, h(DocAutomationPage)))));
    });
    const settle = async (ms = 30) => act(async () => { await new Promise(r => setTimeout(r, ms)); });
    await settle();
    const buttons = () => [...container.querySelectorAll("button")];
    const byText = re => buttons().find(b => re.test(b.textContent));
    const click = async el => {
        assert.ok(el, "button not found");
        await act(async () => { el.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
        await settle();
    };
    // open the template from the home grid
    const open = async (name) => {
        const card = [...container.querySelectorAll("[data-template]")].find(c => c.textContent.includes(name));
        await click([...card.querySelectorAll("button")].find(b => /Use template/.test(b.textContent)));
    };
    // null = "Draft with AI" from the home (2026-10-19), not a template card.
    if (templateName) await open(templateName);
    else await click(container.querySelector("[data-draft-with-ai]"));
    const paper = () => container.querySelector(".de-paper");
    const choose = async (value) => {
        const sel = container.querySelector("#de-juris");
        const setter = Object.getOwnPropertyDescriptor(dom.window.HTMLSelectElement.prototype, "value").set;
        await act(async () => { setter.call(sel, value); sel.dispatchEvent(new dom.window.Event("change", { bubbles: true })); });
        await settle();
    };
    if (jurisdiction && container.querySelector("#de-juris")) await choose(jurisdiction);
    return {
        container, click, byText, paper, settle, open, choose,
        async ask(text) {
            const ta = container.querySelector("textarea");
            const setter = Object.getOwnPropertyDescriptor(dom.window.HTMLTextAreaElement.prototype, "value").set;
            await act(async () => { setter.call(ta, text); ta.dispatchEvent(new dom.window.Event("input", { bubbles: true })); });
            await click(byText(/Generate/));
        },
        // Select the text of the first element in the paper that contains `needle`.
        async select(needle) {
            const el = [...paper().querySelectorAll("li, p")].find(e => e.textContent.includes(needle));
            const r = dom.window.document.createRange(); r.selectNodeContents(el);
            const sel = dom.window.getSelection(); sel.removeAllRanges(); sel.addRange(r);
            await act(async () => { paper().dispatchEvent(new dom.window.MouseEvent("mouseup", { bubbles: true })); });
            await settle();
        },
        async caretAtEnd() {
            const r = dom.window.document.createRange(); r.selectNodeContents(paper()); r.collapse(false);
            const sel = dom.window.getSelection(); sel.removeAllRanges(); sel.addRange(r);
            await act(async () => { paper().dispatchEvent(new dom.window.MouseEvent("mouseup", { bubbles: true })); });
            await settle();
        },
        unmount: async () => { await act(async () => root.unmount()); container.remove(); },
    };
}

test.beforeEach(() => {
    // A failed test never unmounts its page; it must not answer the next one's queries.
    dom.window.document.body.innerHTML = "";
    api.__reset();
    api.__respond("bootstrapAuth", true);
    api.__respond("getMe", { data: { _id: "lawyer-1", role: "lawyer", full_name: "Test Advocate" } });
    api.__respond("listCases", { data: { items: [] } });
    api.__respond("listDocDrafts", { data: [] });
    stubAI();
    reply = "";
    guard = undefined;
    during = null;
    sent = [];
    confirmAnswer = true;
});

test.after(() => { dom.window.close(); });

test("a reply is a proposal: the formatted template is untouched until the lawyer applies it", async () => {
    const page = await mountOn("Lease Agreement");
    const before = page.paper().innerHTML;
    assert.match(before, /<strong>1\. Premises Description<\/strong>/);
    reply = "CONFIDENTIALITY\n\nEach party shall keep the terms of this Agreement confidential.";
    await page.ask("Add a confidentiality clause");
    assert.equal(page.paper().innerHTML, before, "the draft changed without the lawyer applying anything");
    assert.ok(page.container.querySelector('[data-proposal="clause"]'), "no proposal card");
    const call = api.__calls("aiDraftStream").at(-1).args[0];
    assert.equal(call.mode, "clause");
    assert.equal(call.selection, "");
    await page.unmount();
});

test("Insert at cursor adds the clause and keeps every existing heading", async () => {
    const page = await mountOn("Lease Agreement");
    await page.caretAtEnd();
    reply = "CONFIDENTIALITY\n\nEach party shall keep the terms of this Agreement confidential.";
    await page.ask("Add a confidentiality clause");
    await page.click(page.byText(/Insert at cursor/));
    const html = page.paper().innerHTML;
    assert.match(html, /<strong>1\. Premises Description<\/strong>/, "the template's formatting was lost");
    assert.match(html, /<strong>CONFIDENTIALITY<\/strong>/);
    assert.match(html, /keep the terms of this Agreement confidential/);
    // Its own paragraph: never glued onto the line the cursor was on (live: "Witness 210. CONFIDENTIALITY").
    assert.match(html, /Witness 2<\/p>/, "the clause was glued onto the last line");
    assert.match(html, /<p><strong>CONFIDENTIALITY<\/strong><\/p>/, "the clause title is not its own bold paragraph");
    assert.ok(page.container.querySelector("[data-applied]"), "the card does not say it was applied");
    await page.unmount();
});

test("with text selected, the request is a rewrite of that passage only, and only it is replaced", async () => {
    const page = await mountOn("Bail Application");
    await page.select("is innocent and denies all allegations");
    assert.ok(page.container.querySelector("[data-selection-chip]"), "the selection is not shown");
    reply = "That the Applicant is wholly innocent, has been falsely implicated, and denies every allegation.";
    await page.ask("Make this stronger");
    const call = api.__calls("aiDraftStream").at(-1).args[0];
    assert.equal(call.mode, "rewrite");
    assert.match(call.selection, /is innocent and denies all allegations/);
    await page.click(page.byText(/Replace selected text/));
    const text = page.paper().textContent;
    assert.match(text, /wholly innocent, has been falsely implicated/);
    assert.doesNotMatch(text, /is innocent and denies all allegations leveled/, "the old passage is still there");
    assert.match(page.paper().innerHTML, /<strong>Respectfully Sheweth:<\/strong>/, "the rest of the draft changed");
    assert.match(text, /no previous criminal record/, "a neighbouring paragraph was lost");
    await page.unmount();
});

test("replacing the whole draft needs an explicit choice and a confirmation", async () => {
    const page = await mountOn("Notice Letter");
    await page.click(page.byText(/^Whole draft$/));
    reply = "Date: 14 October 2026\n\nDear Sir,\n\nThis is a polished notice.";
    await page.ask("Polish the whole letter");
    assert.equal(api.__calls("aiDraftStream").at(-1).args[0].mode, "full");
    confirmAnswer = false;
    const before = page.paper().innerHTML;
    await page.click(page.byText(/Replace whole draft/));
    assert.equal(page.paper().innerHTML, before, "replaced without confirmation");
    confirmAnswer = true;
    await page.click(page.byText(/Replace whole draft/));
    assert.match(page.paper().textContent, /This is a polished notice/);
    await page.unmount();
});

test("an answer is shown as text, with nothing to insert", async () => {
    const page = await mountOn("Loan Agreement");
    await page.click(page.byText(/^Ask$/));
    reply = "1. No security clause. 2. No default interest.";
    await page.ask("What are the risks for my client?");
    assert.equal(api.__calls("aiDraftStream").at(-1).args[0].mode, "answer");
    assert.equal(page.container.querySelector("[data-proposal]"), null);
    assert.match(page.container.textContent, /No security clause/);
    await page.unmount();
});

test("the quick actions on a letter are letter actions, and pick their mode", async () => {
    const page = await mountOn("Notice Letter");
    const quick = page.container.querySelector("[data-quick-actions]").textContent;
    assert.doesNotMatch(quick, /Stronger prayer/);
    await page.click(page.byText(/^Add a deadline$/));
    const pressed = [...page.container.querySelectorAll("[data-assist-modes] button")].find(b => b.getAttribute("aria-pressed") === "true");
    assert.equal(pressed.textContent, "Add to draft");
    await page.unmount();
});

test("the server's reason for a failure is shown, not 'Connection error'", async () => {
    api.__respond("aiDraftStream", async () => { throw new Error("You don't have access to that case."); });
    const page = await mountOn("Bail Application");
    await page.ask("Add a ground");
    assert.match(page.container.textContent, /You don't have access to that case\./);
    assert.doesNotMatch(page.container.textContent, /Connection error/);
    await page.unmount();
});

test("what the lawyer types survives a re-render (it used to snap back to the template)", async () => {
    // React 19 re-applies dangerouslySetInnerHTML when the prop OBJECT changes;
    // an inline {{ __html }} changed every render, so a word-count update while
    // typing reset the paper. The editor now holds one object for its lifetime.
    const page = await mountOn("Notice Letter");
    const p = page.paper();
    p.insertAdjacentHTML("beforeend", "<p>TYPED BY LAWYER two words</p>");
    await act(async () => { p.dispatchEvent(new dom.window.Event("input", { bubbles: true })); });
    await page.settle();
    assert.match(page.paper().innerHTML, /TYPED BY LAWYER/);
    await page.unmount();
});

test("an applied proposal no longer says 'not applied yet'", async () => {
    const page = await mountOn("Lease Agreement");
    await page.caretAtEnd();
    reply = "FORCE MAJEURE\n\nNeither party is liable for delay caused by events beyond its control.";
    await page.ask("Add a force majeure clause");
    const card = () => page.container.querySelector("[data-proposal]");
    assert.match(card().textContent, /not applied yet/);
    await page.click(page.byText(/Insert at cursor/));
    assert.doesNotMatch(card().textContent, /not applied yet/);
    await page.unmount();
});

// ── the server's legal-authority check (2026-10-14) ─────────────────────────

const RAW = "That the Applicant is entitled to bail under Section 497 CrPC.\n\nThat pre-arrest bail may also be granted under Section 438 CrPC.";
const REASON = "Section 438 CrPC is not stated here: its own text says it was omitted.";

test("a withheld sentence never reaches the proposal, and the card says what and why", async () => {
    const page = await mountOn("Bail Application");
    await page.caretAtEnd();
    reply = RAW;
    guard = { ran: true, text: "That the Applicant is entitled to bail under Section 497 CrPC.",
              withheld: [{ text: "That pre-arrest bail may also be granted under Section 438 CrPC.", reasons: [REASON] }] };
    await page.ask("Add a ground for bail");
    const card = page.container.querySelector("[data-proposal]");
    assert.doesNotMatch(card.querySelector(".de-prop-text").textContent, /438/, "the withheld sentence is in the proposal");
    const note = card.querySelector("[data-guard-withheld]");
    assert.ok(note, "the card does not say anything was withheld");
    assert.match(note.textContent, /its own text says it was omitted/);
    await page.click(page.byText(/Insert at cursor/));
    assert.match(page.paper().textContent, /Section 497 CrPC/);
    assert.doesNotMatch(page.paper().textContent, /438/, "the withheld sentence was inserted");
    await page.unmount();
});

test("when everything is withheld there is nothing to insert", async () => {
    const page = await mountOn("Bail Application");
    reply = "That pre-arrest bail may be granted under Section 438 CrPC.";
    guard = { ran: true, text: "", withheld: [{ text: reply, reasons: [REASON] }] };
    await page.ask("Add a ground for bail");
    assert.equal(page.container.querySelector("[data-proposal]"), null);
    assert.match(page.container.textContent, /withheld the whole reply/);
    assert.ok(page.container.querySelector("[data-guard-withheld]"));
    await page.unmount();
});

/* Empty proposals (eval v2 dev, 2026-10-15): 5 of 44 replies were withheld
   whole. The lawyer is told what to do next -- by WHY it was withheld -- and may
   ask again for a paragraph with no authority in it. The withheld text itself
   never becomes insertable, and the new reply is checked like any other. */
test("an empty proposal says what to do next, and offers only a placeholder re-ask", async () => {
    const page = await mountOn("Bail Application");
    reply = "That pre-arrest bail may be granted under Section 526 CrPC.";
    guard = { ran: true, text: "", withheld: [{ text: reply, reasons: [REASON] }],
              next_step: { kind: "wrong_authority", text: "The cited provision does not cover what the sentence relies on it for." } };
    await page.ask("Add a ground for pre-arrest bail");
    assert.equal(page.container.querySelector("[data-proposal]"), null);
    assert.match(page.container.textContent, /does not cover what the sentence relies on it for/);
    assert.equal(page.byText(/Insert at cursor|Replace/), undefined, "withheld text is insertable");
    const again = page.container.querySelector("[data-placeholder-ask]");
    assert.ok(again, "no placeholder re-ask offered");
    // The re-ask: no authority in it, checked by the server like any reply.
    reply = "That the complaint is mala fide and the applicant is entitled to pre-arrest bail under [PROVISION].";
    guard = { ran: true, text: reply, withheld: [], supported: [], not_checked: [] };
    await page.click(again);
    assert.equal(sent.length, 2);
    assert.match(sent[1].instruction, /Add a ground for pre-arrest bail/);
    assert.ok(sent[1].instruction.includes("Do not cite any provision or case. Where the law would be cited, write [PROVISION]"));
    const card = page.container.querySelector("[data-proposal]");
    assert.ok(card, "the checked placeholder reply is not a proposal");
    assert.ok(card.textContent.includes("[PROVISION]"));
    await page.unmount();
});

test("a placeholder re-ask that is withheld again is not offered a second time", async () => {
    const page = await mountOn("Bail Application");
    reply = "That bail may be granted under Section 526 CrPC.";
    guard = { ran: true, text: "", withheld: [{ text: reply, reasons: [REASON] }] };
    await page.ask("Add a ground for bail");
    assert.match(page.container.textContent, /Rephrase the request or name the provision you mean/, "no fallback next step");
    await page.click(page.container.querySelector("[data-placeholder-ask]"));
    assert.equal(sent.length, 2);
    assert.equal(page.container.querySelectorAll("[data-placeholder-ask]").length, 1, "the re-ask loops");
    await page.unmount();
});


test("a clean, checked reply carries no warning, and says what the check covered", async () => {
    const page = await mountOn("Bail Application", { jurisdiction: "punjab" });
    await page.caretAtEnd();
    reply = "That the Applicant is entitled to bail under Section 497 CrPC.";
    guard = { ran: true, text: reply, withheld: [], supported: ["Section 497 CrPC"], not_checked: [],
              jurisdiction: { province: "punjab", basis: "selected" } };
    await page.ask("Add a ground for bail");
    const card = page.container.querySelector("[data-proposal]");
    assert.equal(card.querySelector(".de-guard"), null);
    const scope = card.querySelector("[data-check-scope]").textContent;
    assert.match(scope, /1 cited provision found in the library and consistent with its subject \(Section 497 CrPC\)/);
    assert.match(scope, /does not confirm the claim is right; facts, remedies and case law are not checked/);
    assert.match(scope, /Punjab/);
    assert.doesNotMatch(card.textContent, /verified|fully checked/i, "the card overstates the check");
    await page.click(page.byText(/Insert at cursor/));
    assert.match(page.paper().textContent, /Section 497 CrPC/);
    await page.unmount();
});

/* ── fail-closed: nothing unchecked can be inserted (2026-10-14) ───────────── */

const buttonsOf = (page) => [...page.container.querySelectorAll("[data-drafter-editor] aside button")].map(b => b.textContent.trim());

async function assertRetryOnly(page, before, re) {
    assert.equal(page.container.querySelector("[data-proposal]"), null, "an unchecked reply became a proposal");
    const failed = [...page.container.querySelectorAll("[data-failed]")].at(-1);
    assert.ok(failed, "no failure message");
    assert.match(failed.textContent, re);
    assert.doesNotMatch(failed.textContent, /438/, "the unchecked text is shown");
    const actions = [...failed.querySelectorAll("button")].map(b => b.textContent.trim());
    assert.deepEqual(actions, ["Retry"], "the failure offers something other than Retry");
    const all = buttonsOf(page);
    for (const label of ["Insert at cursor", "Replace selected text", "Replace whole draft", "Copy"]) {
        assert.ok(!all.includes(label), `"${label}" is offered for an unchecked reply`);
    }
    assert.equal(page.paper().innerHTML, before, "the draft changed");
}

test("a check that failed on the server is a Retry, never a proposal", async () => {
    const page = await mountOn("Bail Application");
    const before = page.paper().innerHTML;
    reply = RAW;
    guard = { ran: false, reason: "check_failed", text: "", withheld: [] };
    await page.ask("Add a ground for bail");
    await assertRetryOnly(page, before, /legal check could not run/);
    await page.unmount();
});

test("an unreadable statute library is said, and is a Retry", async () => {
    const page = await mountOn("Bail Application");
    const before = page.paper().innerHTML;
    reply = RAW;
    guard = { ran: false, reason: "corpus_unavailable", text: "", withheld: [] };
    await page.ask("Add a ground for bail");
    await assertRetryOnly(page, before, /statute library could not be read/);
    await page.unmount();
});

test("a reply without the guard's result is a Retry, never a proposal", async () => {
    const page = await mountOn("Bail Application");
    const before = page.paper().innerHTML;
    reply = RAW;
    guard = null;
    await page.ask("Add a ground for bail");
    await assertRetryOnly(page, before, /result did not arrive/);
    await page.unmount();
});

test("a stream cut short is a Retry, never a proposal", async () => {
    // aiDraftStream itself throws stream_incomplete (tested against the real
    // api.js in lawyer_draft_stream_api.test.mjs); here: what the panel does.
    api.__respond("aiDraftStream", async (args, onToken) => {
        onToken(RAW);
        const e = new Error("The reply was cut off before the legal check finished. Nothing was added to the draft — please try again.");
        e.code = "stream_incomplete";
        throw e;
    });
    const page = await mountOn("Bail Application");
    const before = page.paper().innerHTML;
    await page.ask("Add a ground for bail");
    await assertRetryOnly(page, before, /cut off before the legal check finished/);
    await page.unmount();
});

test("Retry sends the same request again, and a checked reply becomes a proposal", async () => {
    const page = await mountOn("Bail Application", { jurisdiction: "sindh" });
    reply = RAW;
    guard = { ran: false, reason: "check_failed", text: "", withheld: [] };
    await page.ask("Add a ground for bail");
    const first = api.__calls("aiDraftStream").at(-1).args[0];
    guard = { ran: true, text: "That the Applicant is entitled to bail under Section 497 CrPC.", withheld: [], supported: ["Section 497 CrPC"] };
    await page.click(page.byText(/^Retry$/));
    const second = api.__calls("aiDraftStream").at(-1).args[0];
    for (const k of ["instruction", "mode", "selection", "province"]) assert.equal(second[k], first[k], k);
    const card = page.container.querySelector("[data-proposal]");
    assert.ok(card, "the retried, checked reply is not a proposal");
    assert.doesNotMatch(card.querySelector(".de-prop-text").textContent, /438/);
    await page.unmount();
});

/* ── jurisdiction for a caseless draft ─────────────────────────────────────── */

test("a caseless draft cannot be generated until a jurisdiction is chosen", async () => {
    const page = await mountOn("Notice Letter", { jurisdiction: null });
    const ta = page.container.querySelector("textarea");
    const setter = Object.getOwnPropertyDescriptor(dom.window.HTMLTextAreaElement.prototype, "value").set;
    await act(async () => { setter.call(ta, "Add a deadline"); ta.dispatchEvent(new dom.window.Event("input", { bubbles: true })); });
    await page.settle();
    assert.equal(page.byText(/Generate/).disabled, true, "Generate is live with no jurisdiction");
    assert.match(page.container.textContent, /Choose a jurisdiction to start drafting/);
    await act(async () => { ta.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Enter", bubbles: true })); });
    await page.settle();
    assert.equal(api.__calls("aiDraftStream").length, 0, "Enter sent a request with no jurisdiction");
    const options = [...page.container.querySelectorAll("#de-juris option")].map(o => o.value);
    assert.deepEqual(options, ["", "punjab", "sindh", "kpk", "balochistan", "federal", "unknown"]);
    await page.unmount();
});

for (const [value, re] of [["punjab", /Federal and Punjab law/], ["sindh", /no Sindh provincial statutes/],
                           ["unknown", /Federal law only\. Where provincial law governs/]]) {
    test(`choosing ${value} sends ${value} and says what law that covers`, async () => {
        const page = await mountOn("Notice Letter", { jurisdiction: value });
        assert.match(page.container.querySelector("[data-jurisdiction]").textContent, re);
        reply = "x";
        await page.ask("Add a deadline");
        assert.equal(api.__calls("aiDraftStream").at(-1).args[0].province, value);
        await page.unmount();
    });
}

test("a case-bound draft shows the case's province and sends no override", async () => {
    api.__respond("listCases", { data: { items: [{ _id: "c1", case_number: "C-1", title: "Rent dispute",
        client_name: "Client", province: "punjab", case_type: "civil", status: "active" }] } });
    const page = await mountOn("Notice Letter", { activeCase: "C-1" });
    assert.equal(page.container.querySelector("#de-juris"), null, "a case-bound draft offers a jurisdiction override");
    assert.match(page.container.querySelector("[data-jurisdiction-case]").textContent, /Punjab \(from the case\)/);
    reply = "x";
    await page.ask("Add a deadline");
    const call = api.__calls("aiDraftStream").at(-1).args[0];
    assert.equal(call.case_id, "c1");
    assert.equal(call.province, "");
    await page.unmount();
});

/* ── a rewrite never replaces a passage that changed ──────────────────────── */

const PASSAGE = "is innocent and denies all allegations";
const REWRITE = "That the Applicant is wholly innocent, has been falsely implicated, and denies every allegation.";
const passageEl = (page) => [...page.paper().querySelectorAll("li, p")].find(e => e.textContent.includes(PASSAGE));

test("an edit inside the selected passage during generation disables the replacement", async () => {
    const page = await mountOn("Bail Application");
    await page.select(PASSAGE);
    reply = REWRITE;
    during = async () => {           // the lawyer fixes a word while the model writes
        const t = [...passageEl(page).childNodes].find(n => n.nodeType === 3 && n.data.includes("innocent"));
        t.data = t.data.replace("innocent", "entirely innocent");
    };
    await page.ask("Make this stronger");
    const after = page.paper().innerHTML;
    const btn = page.container.querySelector("[data-replace-selection]");
    assert.ok(btn, "no replace button");
    assert.equal(btn.disabled, true, "a stale passage can still be replaced");
    assert.ok(page.container.querySelector("[data-stale-selection]"), "the card does not say why");
    await page.click(btn);
    assert.equal(page.paper().innerHTML, after, "something was replaced");
    assert.match(page.paper().textContent, /entirely innocent/, "the lawyer's edit was lost");
    // Insert at cursor still works
    await page.caretAtEnd();
    await page.click(page.byText(/Insert at cursor/));
    assert.match(page.paper().textContent, /falsely implicated/);
    await page.unmount();
});

test("a deleted passage is not replaced", async () => {
    const page = await mountOn("Bail Application");
    await page.select(PASSAGE);
    reply = REWRITE;
    during = async () => { passageEl(page).remove(); };
    await page.ask("Make this stronger");
    assert.equal(page.container.querySelector("[data-replace-selection]").disabled, true);
    assert.ok(page.container.querySelector("[data-stale-selection]"));
    await page.unmount();
});

test("an edit elsewhere in the draft does not stop the replacement, which hits only the passage", async () => {
    const page = await mountOn("Bail Application");
    await page.select(PASSAGE);
    reply = REWRITE;
    during = async () => {
        const p = dom.window.document.createElement("p");
        p.textContent = "ADDED WHILE WAITING";
        page.paper().appendChild(p);
    };
    await page.ask("Make this stronger");
    const btn = page.container.querySelector("[data-replace-selection]");
    assert.equal(btn.disabled, false);
    assert.equal(page.container.querySelector("[data-stale-selection]"), null);
    await page.click(btn);
    const text = page.paper().textContent;
    assert.match(text, /falsely implicated/);
    assert.doesNotMatch(text, /is innocent and denies all allegations leveled/);
    assert.match(text, /ADDED WHILE WAITING/, "the lawyer's other edit was lost");
    assert.match(page.paper().innerHTML, /<strong>Respectfully Sheweth:<\/strong>/, "the rest of the draft changed");
    await page.unmount();
});

test("an edit made after the reply arrived disables a pending replacement", async () => {
    const page = await mountOn("Bail Application");
    await page.select(PASSAGE);
    reply = REWRITE;
    await page.ask("Make this stronger");
    assert.equal(page.container.querySelector("[data-replace-selection]").disabled, false);
    const t = [...passageEl(page).childNodes].find(n => n.nodeType === 3 && n.data.includes("denies"));
    t.data = t.data.replace("denies", "firmly denies");
    await act(async () => { page.paper().dispatchEvent(new dom.window.Event("input", { bubbles: true })); });
    await page.settle();
    assert.equal(page.container.querySelector("[data-replace-selection]").disabled, true);
    await page.unmount();
});

test("a reply landing after the lawyer opened another template touches neither document", async () => {
    const page = await mountOn("Bail Application");
    await page.select(PASSAGE);
    reply = REWRITE;
    let release;
    during = () => new Promise(r => { release = r; });
    await page.ask("Make this stronger");                 // still waiting for the model
    await page.click(page.container.querySelector("[aria-label='Back to templates']"));
    await page.open("Notice Letter");
    const before = page.paper().innerHTML;
    await act(async () => { release(); });
    await page.settle();
    assert.equal(page.container.querySelector("[data-proposal]"), null, "the old reply appeared in the new document");
    assert.equal(page.paper().innerHTML, before, "the new document changed");
    assert.doesNotMatch(page.paper().textContent, /falsely implicated/);
    await page.unmount();
});

test("a cited provision the library lacks is named as not checked, never counted as checked", async () => {
    const page = await mountOn("Notice Letter");
    reply = "That the lease may be forfeited under Section 113 of the Transfer of Property Act, 1882.";
    guard = { ran: true, text: reply, withheld: [], supported: [], not_checked: ["Section 113 Transfer of Property Act"],
              jurisdiction: { province: "unknown", basis: "neutral" } };
    await page.ask("Add a forfeiture paragraph");
    const scope = page.container.querySelector("[data-proposal] [data-check-scope]");
    assert.match(scope.textContent, /none of the cited provisions could be checked/);
    assert.doesNotMatch(scope.textContent, /no statute provision cited|found in the library and consistent/, "it claims a check or no citation");
    const missing = scope.querySelector("[data-check-unverified]");
    assert.ok(missing, "the unchecked provision is not named");
    assert.match(missing.textContent, /Not verified — check these yourself: Section 113 Transfer of Property Act/);
    assert.doesNotMatch(missing.textContent, /\bverified\b(?! —)/i, "an unchecked authority reads as verified");
    await page.unmount();
});

/* ── fix 4: counts describe the final proposal; fix 2: neutral clarification ── */

test("a provision cited only in a withheld sentence is not counted as supported", async () => {
    const page = await mountOn("Bail Application", { jurisdiction: "punjab" });
    reply = RAW;
    guard = { ran: true, text: "That the Applicant is entitled to bail under Section 497 CrPC.",
              withheld: [{ text: "That pre-arrest bail may also be granted under Section 438 CrPC.", reasons: [REASON] }],
              supported: ["Section 497 CrPC"], not_checked: [] };
    await page.ask("Add a ground for bail");
    const scope = page.container.querySelector("[data-proposal] [data-check-scope]");
    assert.equal(scope.querySelector("[data-check-supported]").getAttribute("data-check-supported"), "1");
    assert.doesNotMatch(scope.textContent, /438/, "the withheld provision is counted or named as supported");
    assert.match(page.container.querySelector("[data-guard-withheld]").textContent, /Withheld by the legal check \(1\)/);
    await page.unmount();
});

test("a neutral draft on a province-dependent issue says so, with a way to choose a jurisdiction", async () => {
    const page = await mountOn("Notice Letter", { jurisdiction: "unknown" });
    reply = "That you are required to vacate the premises for non-payment of rent under [applicable provincial rent law -- choose jurisdiction].";
    guard = { ran: true, text: reply, withheld: [], supported: [], not_checked: [],
              jurisdiction: { province: "unknown", basis: "neutral" },
              clarify: { topic: "tenancy", placeholder: true,
                         message: "Tenancy and eviction depends on the province's rent law. Choose a jurisdiction to cite it; until then this draft should name no statute for it." } };
    await page.ask("Add an eviction paragraph");
    const c = page.container.querySelector("[data-proposal] [data-clarify='tenancy']");
    assert.ok(c, "no clarification shown");
    assert.match(c.textContent, /depends on the province's rent law/);
    assert.doesNotMatch(c.textContent, /no placeholder/);
    await page.click([...c.querySelectorAll("button")].find(b => /Choose jurisdiction/.test(b.textContent)));
    assert.equal(dom.window.document.activeElement?.id, "de-juris", "the jurisdiction control was not focused");
    await page.unmount();
});

test("a neutral clarification warns when the proposal has no placeholder", async () => {
    const page = await mountOn("Notice Letter", { jurisdiction: "unknown" });
    reply = "That you are required to vacate the premises for non-payment of rent.";
    guard = { ran: true, text: reply, withheld: [], supported: [], not_checked: [],
              clarify: { topic: "tenancy", placeholder: false, message: "Tenancy and eviction depends on the province's rent law." } };
    await page.ask("Add an eviction paragraph");
    assert.match(page.container.querySelector("[data-clarify]").textContent, /has no placeholder for it — add one/);
    await page.unmount();
});


test("each not-verified authority shows its reason, and none is counted as supported", async () => {
    const page = await mountOn("Bail Application");
    reply = "That custody be given to the mother under Section 41 of the Divorce Act, 1869.";
    guard = { ran: true, text: reply, withheld: [], supported: [],
              not_checked: ["Section 41 Divorce Act 1869 (applies to the Christian community only -- confirm the parties' personal law)",
                            "Section 114 CPC 1908 (not in our copy)"] };
    await page.ask("Add a custody ground");
    const scope = page.container.querySelector("[data-proposal] [data-check-scope]");
    assert.equal(scope.querySelector("[data-check-supported]").getAttribute("data-check-supported"), "0");
    const line = scope.querySelector("[data-check-unverified]").textContent;
    assert.match(line, /Christian community only/);
    assert.match(line, /Section 114 CPC 1908 \(not in our copy\)/);
    await page.unmount();
});

test("a fully withheld reply still shows what was withheld and why", async () => {
    const page = await mountOn("Bail Application");
    reply = "That the plaint ought to be rejected pursuant to CPC 1908 Section 13.";
    guard = { ran: true, text: "", supported: [], not_checked: [],
              withheld: [{ text: reply, reasons: ["Section 13 CPC is \"When foreign judgment not conclusive\" ... (see Order VII Rule 11 \"Rejection of plaint\")"] }] };
    await page.ask("Add a rejection ground");
    assert.equal(page.container.querySelector("[data-proposal]"), null);
    const note = page.container.querySelector("[data-guard-withheld]");
    assert.ok(note, "the withheld text vanished");
    assert.match(note.textContent, /ought to be rejected/);
    assert.match(note.textContent, /Order VII Rule 11/);
    await page.unmount();
});

/* ── final insertable text and the withheld-reason panel (2026-10-15) ───── */

test("Insert puts exactly the checked text into the draft, Urdu and special hyphens intact, and nothing withheld", async () => {
    const page = await mountOn("Bail Application");
    await page.caretAtEnd();
    const kept = "That the High Court may quash these proceedings under Section 561\u2011A CrPC as an abuse of process.\n\n"
        + "\u06cc\u06c1 \u06a9\u06c1 \u0645\u0644\u0632\u0645 \u0636\u0645\u0627\u0646\u062a \u06a9\u0627 \u062d\u0642\u062f\u0627\u0631 \u06c1\u06d2\u06d4";
    reply = kept + "\n\nThat the plaint is liable to be rejected pursuant to CPC 1908 Section 13.";
    guard = { ran: true, text: kept, supported: ["Section 561-A CrPC 1898"], not_checked: [],
              withheld: [{ text: "That the plaint is liable to be rejected pursuant to CPC 1908 Section 13.",
                           reasons: ["Section 13 CPC is \"When foreign judgment not conclusive\", which does not support what this sentence relies on it for (plaint, rejected)."] }] };
    await page.ask("Add grounds");
    await page.click(page.byText(/Insert at cursor/));
    const text = page.paper().textContent;
    assert.match(text, /561\u2011A/, "the lawyer's own hyphen was changed");
    assert.match(text, /\u0636\u0645\u0627\u0646\u062a/, "the Urdu sentence was lost");
    assert.doesNotMatch(text, /Section 13/, "a withheld sentence was inserted");
    await page.unmount();
});

test("the withheld-reason panel shows the reason verbatim and offers no replacement citation", async () => {
    const page = await mountOn("Bail Application");
    reply = "That the plaint is liable to be rejected pursuant to CPC 1908 Section 13.\n\nThat the applicant is innocent.";
    guard = { ran: true, text: "That the applicant is innocent.", supported: [], not_checked: [],
              withheld: [{ text: "That the plaint is liable to be rejected pursuant to CPC 1908 Section 13.",
                           reasons: ["Section 13 CPC is \"When foreign judgment not conclusive\", which does not support what this sentence relies on it for (plaint, rejected)."] }] };
    await page.ask("Add grounds");
    const note = page.container.querySelector("[data-proposal] [data-guard-withheld]");
    assert.ok(note);
    assert.match(note.textContent, /When foreign judgment not conclusive/);
    assert.doesNotMatch(note.textContent, /\bsee\b|instead|Order VII Rule 11/i, "the panel suggests a citation nobody verified");
    const scope = page.container.querySelector("[data-proposal] [data-check-scope]");
    assert.doesNotMatch(scope.textContent, /found in the library and consistent/, "nothing was supported, yet the panel says so");
    await page.unmount();
});


/* Invented facts (draft_claims S3, 2026-10-15): a sentence stating a fact the lawyer did not give is never
   insertable; the server's version with [placeholders] -- itself checked in full -- is a separate proposal. */
const FACT = "That the accused, though not insane, is unable to understand the proceedings.";
const ALT = "That the accused, [fact to be supplied].";
const KEEP = "That the proceedings are an abuse of process under Section 561-A CrPC.";

test("an invented fact is never in the proposal; the placeholder version is a separate, labelled proposal", async () => {
    const page = await mountOn("Bail Application");
    await page.caretAtEnd();
    reply = `${FACT} ${KEEP}`;
    guard = { ran: true, text: KEEP, supported: ["Section 561-A CrPC 1898"], not_checked: [],
              withheld: [{ text: FACT, reasons: ["This sentence states a fact you did not give: insane, unable to understand."] }],
              placeholder_alternative: { text: `${ALT} ${KEEP}`, supported: ["Section 561-A CrPC 1898"], not_checked: [], withheld: [] } };
    await page.ask("Add a ground to quash the proceedings");
    const cards = [...page.container.querySelectorAll("[data-proposal]")];
    assert.equal(cards.length, 2);
    assert.doesNotMatch(cards[0].querySelector(".de-prop-text").textContent, /insane|unable to understand/);
    assert.match(cards[0].querySelector("[data-guard-withheld]").textContent, /states a fact you did not give/);
    assert.equal(cards[1].querySelector("[data-prop-kind]").getAttribute("data-prop-kind"), "placeholder-alternative");
    assert.match(cards[1].querySelector(".de-prop-text").textContent, /\[fact to be supplied\]/);
    assert.doesNotMatch(cards[1].textContent, /insane/);
    await page.click([...cards[1].querySelectorAll("button")].find(b => /Insert at cursor/.test(b.textContent)));
    assert.match(page.paper().textContent, /\[fact to be supplied\]/);
    assert.doesNotMatch(page.paper().textContent, /insane/, "the invented fact reached the draft");
    await page.unmount();
});

test("with every sentence withheld, only the checked placeholder version can be inserted", async () => {
    const page = await mountOn("Bail Application");
    reply = FACT;
    guard = { ran: true, text: "", supported: [], not_checked: [],
              withheld: [{ text: FACT, reasons: ["This sentence states a fact you did not give: insane."] }],
              placeholder_alternative: { text: ALT, supported: [], not_checked: [], withheld: [] } };
    await page.ask("Add a ground");
    const cards = [...page.container.querySelectorAll("[data-proposal]")];
    assert.equal(cards.length, 1, "only the placeholder version is a proposal");
    assert.match(cards[0].textContent, /\[fact to be supplied\]/);
    assert.match(page.container.textContent, /withheld the whole reply/);
    await page.unmount();
});

test("no placeholder version when the server sends none", async () => {
    const page = await mountOn("Bail Application");
    reply = KEEP;
    guard = { ran: true, text: KEEP, supported: [], not_checked: [], withheld: [], placeholder_alternative: null };
    await page.ask("Add a ground");
    assert.equal(page.container.querySelectorAll("[data-proposal]").length, 1);
    assert.equal(page.container.querySelector("[data-prop-kind]"), null);
    await page.unmount();
});

/* Non-Punjab CPC (draft_guard batch 5, 2026-10-16): the CPC text on file is Punjab's. The citation leaves the
   proposal (only the clause); the [Verify ...] version is a separate proposal labelled by the SERVER. */
const CPC_REPLY = "That the defendant resides in Karachi and this Court has jurisdiction under Section 20 of the Code of Civil Procedure, 1908.";
const CPC_MAIN = "That the defendant resides in Karachi and this Court has jurisdiction.";
const CPC_ALT = "That the defendant resides in Karachi and this Court has jurisdiction under [Verify the applicable CPC provision for Sindh].";

test("a Sindh CPC citation: the main card drops only the clause; the labelled placeholder version inserts the placeholder", async () => {
    const page = await mountOn("Bail Application", { jurisdiction: "sindh" });
    await page.caretAtEnd();
    reply = CPC_REPLY;
    guard = { ran: true, text: CPC_MAIN, supported: [], not_checked: [],
              withheld: [{ text: "Section 20 of the Code of Civil Procedure, 1908", reasons: [
                  "Section 20 of the Code of Civil Procedure, 1908: the CPC text on file is the Punjab version and this matter is not confirmed as Punjab (Sindh), so the citation was taken out of this proposal."] }],
              placeholder_alternative: { text: CPC_ALT, supported: [], not_checked: [], withheld: [],
                                         label: "With a [Verify ...] placeholder for the CPC provision" } };
    await page.ask("Add a jurisdiction paragraph");
    const cards = [...page.container.querySelectorAll("[data-proposal]")];
    assert.equal(cards.length, 2);
    assert.equal(cards[0].querySelector(".de-prop-text").textContent, CPC_MAIN);
    assert.doesNotMatch(cards[0].querySelector(".de-prop-text").textContent, /Section 20|Code of Civil Procedure/);
    assert.match(cards[0].querySelector("[data-guard-withheld]").textContent, /Punjab version/);
    // "Not checked" is never phrased as a pass
    assert.doesNotMatch(cards[0].textContent, /found in the library and consistent/);
    assert.match(cards[1].querySelector("[data-prop-kind]").textContent, /placeholder for the CPC provision/);
    assert.doesNotMatch(cards[1].querySelector("[data-prop-kind]").textContent, /facts you did not give/);
    await page.click([...cards[1].querySelectorAll("button")].find(b => /Insert at cursor/.test(b.textContent)));
    assert.match(page.paper().textContent, /\[Verify the applicable CPC provision for Sindh\]/);
    assert.doesNotMatch(page.paper().textContent, /Section 20 of the Code/, "the unverified citation reached the draft");
    await page.unmount();
});

test("a placeholder version without a server label keeps the old wording", async () => {
    const page = await mountOn("Bail Application");
    reply = FACT;
    guard = { ran: true, text: "", supported: [], not_checked: [],
              withheld: [{ text: FACT, reasons: ["This sentence states a fact you did not give: insane."] }],
              placeholder_alternative: { text: ALT, supported: [], not_checked: [], withheld: [] } };
    await page.ask("Add a ground");
    assert.match(page.container.querySelector("[data-prop-kind]").textContent, /facts you did not give/);
    await page.unmount();
});

/* ── Draft with AI: no template (2026-10-19) ─────────────────────────────── */

import { tidyFullDraft, findPlaceholders, draftTitle } from "../src/lib/draftAssist.js";

test("a whole draft is tidied: a lone jurisdiction line goes, a numbering gap closes, a prayer's own list stays", () => {
    assert.equal(tidyFullDraft("Punjab\nLegal Notice\n\n1. A\n\n3. B\n\nPrayer\n1. x\n3. y"),
        "Legal Notice\n\n1. A\n\n2. B\n\nPrayer\n1. x\n3. y");
    assert.equal(tidyFullDraft("1. a\n2. b"), "1. a\n2. b", "nothing to fix");
    assert.equal(tidyFullDraft("Punjab Rented Premises Act notice\n1. a"), "Punjab Rented Premises Act notice\n1. a", "only a line that is just the jurisdiction");
    assert.deepEqual(findPlaceholders("[Address], ___ and [Address] ______"), [{ label: "[Address]", count: 2 }, { label: "___", count: 2 }]);
    assert.equal(draftTitle("Punjab\nLEGAL NOTICE\nTo,"), "Legal Notice");
    assert.equal(draftTitle("Ahmed Raza\nLahore\nSubject: Legal Notice for Unpaid Rent\nSir,"), "Legal Notice for Unpaid Rent",
        "a letter's first line is the sender, not the title");
});

test("Draft with AI starts on an empty page, asks for the facts, and is set to a whole draft", async () => {
    const page = await mountOn(null, { jurisdiction: "punjab" });
    assert.equal(page.paper().textContent, "", "the generic scaffold must not be loaded");
    assert.match(page.paper().getAttribute("data-empty"), /AI writes it here/);
    assert.ok(page.container.querySelector("[data-ai-first]"));
    assert.equal(page.container.querySelector("h1").textContent, "AI draft");
    await page.unmount();
});

test("on the empty page the whole draft is placed at once, titled, tidied, with its blanks listed", async () => {
    const page = await mountOn(null, { jurisdiction: "punjab" });
    reply = "Punjab\nLEGAL NOTICE\n\nTo,\nMr. Bilal Khan, [Address]\n\n1. My client owns the shop.\n\n3. Pay within ___ days.";
    await page.ask("Legal notice for unpaid rent of a shop in Lahore");
    assert.equal(sent[0].mode, "full");
    assert.equal(sent[0].template, "", "no 'Blank legal draft' template is sent to the drafter");
    const text = page.paper().textContent;
    assert.ok(text.startsWith("LEGAL NOTICE"), "the lone 'Punjab' line is dropped");
    assert.match(text, /2\. Pay within/, "numbering closed after a withheld paragraph");
    assert.equal(page.container.querySelector("h1").textContent, "Legal Notice");
    assert.match(page.container.textContent, /Placed in the draft/);
    // 2026-10-20: the blanks sit behind one toolbar button, not above the paper.
    const toggle = page.container.querySelector("[data-fields-toggle]");
    assert.match(toggle.textContent, /Placeholders\s*2/);
    assert.equal(page.container.querySelector("[data-field]"), null, "the list is shown before it is asked for");
    await page.click(toggle);
    const chips = [...page.container.querySelectorAll("[data-field]")].map(b => b.getAttribute("data-field"));
    assert.deepEqual(chips, ["[Address]", "___"]);
    // The panel takes the Draft Assistant's place on the right.
    assert.ok(page.container.querySelector("[data-fill-panel]"), "no Fill placeholders panel");
    assert.equal(page.container.querySelector('aside[aria-label="Draft Assistant"]').style.display, "none");
    // Find selects that blank on the page, ready to type over.
    await page.click(page.container.querySelector('[data-field="[Address]"]'));
    assert.equal(dom.window.getSelection().toString(), "[Address]");
    // Filling: a value replaces the placeholder in the draft; blanks are found one by one.
    const box = page.container.querySelector('[data-fill-row="[Address]"] textarea');
    const setter = Object.getOwnPropertyDescriptor(dom.window.HTMLTextAreaElement.prototype, "value").set;
    await act(async () => { setter.call(box, "House 12, Gulberg III, Lahore"); box.dispatchEvent(new dom.window.Event("input", { bubbles: true })); });
    await page.click(page.container.querySelector("[data-fill-go]"));
    assert.match(page.paper().textContent, /House 12, Gulberg III, Lahore/);
    assert.doesNotMatch(page.paper().textContent, /\[Address\]/);
    assert.match(page.container.querySelector("[data-fill-panel]").textContent, /1 of 1 filled/);
    assert.ok(page.container.querySelector('[data-fill-row="[Address]"].done'), "the row is not marked filled");
    assert.ok(page.container.querySelector("[data-fill-blanks]"), "blank lines are not listed");
    assert.match(page.container.querySelector("[data-fields-toggle]").textContent, /Placeholders\s*1/);
    await page.unmount();
});

test("when the guard offers a version with [placeholders], that version goes on the empty page", async () => {
    const page = await mountOn(null, { jurisdiction: "punjab" });
    reply = "Legal Notice\n\n1. My client owns the shop.";
    guard = { ran: true, text: reply, withheld: [{ sentence: "He paid nothing since May.", reason: "fact" }], supported: [], not_checked: [],
              placeholder_alternative: { text: "Legal Notice\n\n1. My client owns the shop.\n\n2. No rent was paid since [date].", withheld: [], supported: [], not_checked: [] } };
    await page.ask("Legal notice for unpaid rent");
    assert.match(page.paper().textContent, /since \[date\]/);
    await page.click(page.container.querySelector("[data-fields-toggle]"));
    assert.deepEqual([...page.container.querySelectorAll("[data-field]")].map(b => b.getAttribute("data-field")), ["[date]"]);
    await page.unmount();
});

test("a page with text is never overwritten by itself: the whole draft stays a proposal", async () => {
    const page = await mountOn(null, { jurisdiction: "punjab" });
    page.paper().innerHTML = "<p>My own opening line.</p>";
    reply = "Legal Notice\n\n1. Text.";
    await page.ask("Whole notice please");
    assert.equal(page.paper().textContent, "My own opening line.");
    assert.ok(page.byText(/Replace whole draft/));
    await page.unmount();
});

test("either right-hand panel expands to full height over a dimmed page; Esc or the page shrinks it", async () => {
    const page = await mountOn(null, { jurisdiction: "punjab" });
    const assist = () => page.container.querySelector('aside[aria-label="Draft Assistant"]');
    await page.click(assist().querySelector("[data-panel-expand]"));
    assert.ok(assist().classList.contains("big"), "the Draft Assistant did not expand");
    assert.ok(page.container.querySelector("[data-panel-scrim]"), "the page behind is not dimmed");
    await act(async () => { dom.window.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Escape", bubbles: true })); });
    await page.settle();
    assert.ok(!assist().classList.contains("big"));
    assert.equal(page.container.querySelector("[data-panel-scrim]"), null);
    // The fill panel too; a click on the dimmed page shrinks it, and Esc shrinks before it closes.
    reply = "LEGAL NOTICE\n\nTo Mr. X, [Address]";
    await page.ask("Legal notice");
    await page.click(page.container.querySelector("[data-fields-toggle]"));
    const fill = () => page.container.querySelector("[data-fill-panel]");
    await page.click(fill().querySelector("[data-panel-expand]"));
    assert.ok(fill().classList.contains("big"));
    await page.click(page.container.querySelector("[data-panel-scrim]"));
    assert.ok(fill() && !fill().classList.contains("big"), "the scrim closed the panel instead of shrinking it");
    await page.unmount();
});
