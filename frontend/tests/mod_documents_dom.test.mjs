/* ModDocuments — the actual component, mounted.
 *
 * Since 2026-10-19 the module is a thin shell: the Documents home, the drafting
 * workspace and the Vault. The template guided flow (Draft details, Review,
 * Send to lawyer, Final & export) was removed: a template's details are filled
 * on its own text in the template editor, and "Create draft" makes the
 * document and opens it in the drafting workspace -- the one editor for every
 * draft. The tests of that flow's internals (field review, regenerate, retry
 * keys, refresh-resume, the case selector, its citation badge) went with it;
 * the workspace's own behaviour is tested in docs_drafts_*,
 * docs_send_from_workspace and review_requests_*.
 *
 * The component reaches for a lot of context, so the providers it needs are
 * the real ones; only the API is stubbed.
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
                    "MutationObserver", "getComputedStyle", "localStorage", "sessionStorage", "DOMParser",
                    "requestAnimationFrame", "cancelAnimationFrame"]) {
    define(name, dom.window[name]);
}
define("IS_REACT_ACT_ENVIRONMENT", true);

/* Component code uses the GLOBAL timers (Node's), not jsdom's, so
 * `window.close()` does not release them and the process stays alive past the
 * runner's timeout. Tracked here and cleared at the end. */
const liveTimers = new Set();
const realSetInterval = globalThis.setInterval;
const realClearInterval = globalThis.clearInterval;
const realSetTimeout = globalThis.setTimeout;
const realClearTimeout = globalThis.clearTimeout;
define("setInterval", (...args) => {
    const id = realSetInterval(...args);
    liveTimers.add(id);
    return id;
});
define("clearInterval", id => { liveTimers.delete(id); return realClearInterval(id); });
define("setTimeout", (...args) => {
    const id = realSetTimeout(...args);
    liveTimers.add(id);
    return id;
});
define("clearTimeout", id => { liveTimers.delete(id); return realClearTimeout(id); });

const React = (await import("react")).default;
const { act } = await import("react");
const { createRoot } = await import("react-dom/client");
const api = await import("./support/api-stub.mjs");
const { resetTemplateTextCache } = await import("../src/components/client/documents/TemplateEditor.jsx");
const { rememberDraft, DRAFT_KEY_PREFIX } =
    await import("../src/lib/documentResume.js");
const { requestDocumentsView } = await import("../src/lib/documentsNav.js");

const { createElement: h } = React;

/* jsdom gives a real localStorage; clear it between tests so one test's
   remembered draft or saved template copy cannot satisfy another's assertion. */
function clearStorage() {
    for (const key of Object.keys(dom.window.localStorage)) {
        if (key.startsWith(DRAFT_KEY_PREFIX) || key.startsWith("attorney.templateCopy.")) {
            dom.window.localStorage.removeItem(key);
        }
    }
}

const CASES = [{ _id: "case-1", title: "A matter" },
               { _id: "case-2", title: "Another matter" }];
const SHA = "a".repeat(64);
const BAIL = { template_type: "bail_application", label: "Bail Application",
    category: "Criminal", description: "Application for bail.",
    fields: ["accused_name", "grounds"], structured_fields: [], drafting_mode: "manual" };
const NOTICE = { template_type: "legal_notice", label: "Legal Notice",
    category: "Civil", description: "A formal legal notice.",
    fields: ["sender_name", "demand"], structured_fields: [], drafting_mode: "ai" };

async function mountDocuments() {
    const { default: ModDocuments } =
        await import("../src/components/client/ModDocuments.jsx");
    const { CaseProvider } = await import("../src/components/shared/CaseContext.jsx");
    const { AuthProvider } = await import("../src/context/AuthContext.jsx");
    const { ToastContainer } = await import("../src/components/shared/Toast.jsx");
    const { DARK } = await import("../src/components/admin/themes.js");
    const { ThemeCtx, HeaderActionsCtx } =
        await import("../src/components/client/theme.js");

    const container = dom.window.document.createElement("div");
    dom.window.document.body.appendChild(container);
    const root = createRoot(container);
    // The REAL providers, not fakes: a stubbed context can satisfy a component
    // that would break against the real one.
    await act(async () => {
        root.render(h(
            AuthProvider, null,
            h(ThemeCtx.Provider, { value: DARK },
              h(HeaderActionsCtx.Provider,
                { value: { setHeaderActions: () => {} } },
                h(ToastContainer, { theme: DARK },
                  h(CaseProvider, null, h(ModDocuments)))))));
    });
    // Effects that fetch settle on a later tick.
    await act(async () => { await new Promise(r => setTimeout(r, 20)); });
    return {
        container,
        text: () => container.textContent,
        settle: async (ms = 40) => { await act(async () => {
            await new Promise(r => setTimeout(r, ms));
        }); },
        unmount: async () => { await act(async () => root.unmount()); container.remove(); },
    };
}

const buttons = (el, text) => [...el.querySelectorAll("button")]
    .filter(b => (b.textContent || "").includes(text));
const byLabel = (el, label) => [...el.querySelectorAll("button")]
    .find(b => b.getAttribute("aria-label") === label);
async function press(p, el) {
    assert.ok(el, "nothing to click");
    await act(async () => {
        el.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
    });
    await p.settle();
}
async function type(p, input, value) {
    assert.ok(input, "no such field");
    const proto = input.tagName === "TEXTAREA" ? dom.window.HTMLTextAreaElement.prototype
        : input.tagName === "SELECT" ? dom.window.HTMLSelectElement.prototype
        : dom.window.HTMLInputElement.prototype;
    await act(async () => {
        Object.getOwnPropertyDescriptor(proto, "value").set.call(input, value);
        input.dispatchEvent(new dom.window.Event(input.tagName === "SELECT" ? "change" : "input", { bubbles: true }));
    });
    await p.settle(10);
}
const editor = () => document.querySelector('[aria-label="Customize template"]');

/* The drafting workspace opens on the document it is given. */
function respondWorkspace(id, templateType = "bail_application") {
    api.__respond("getDocumentWorkspaceV2", { data: {
        document_id: id, title: "Bail Application draft", source: "structured_fields",
        template_type: templateType, fields: { accused_name: "Ali Raza" }, body_html: null,
        base_revision_id: "rev-1", base_version: 1, content_epoch: 0, review_status: "none" } });
    api.__respond("getDocumentV2", { data: {
        id, title: "Bail Application draft", template_type: templateType, review_status: "none",
        current_version: 1, current_revision: { revision_id: "rev-1", pdf_sha256: SHA, version: 1,
            created_at: "2026-10-19T10:00:00Z", compliance: null, verification: { ran: true, counts: { total: 0 } } } } });
}

test.beforeEach(() => {
    // The open document rides in the address (?doc=); each test starts clean.
    dom.window.history.replaceState(null, "", "/");
    api.__reset();
    resetTemplateTextCache();
    clearStorage();
    // Signed in through the stub, so the REAL CaseProvider actually fetches.
    api.__respond("bootstrapAuth", true);
    api.__respond("getMe", { data: { _id: "u1", role: "client" } });
    api.__respond("listCases", { data: CASES });
    api.__respond("getCases", { data: CASES });
    api.__respond("myDocumentsV2", { data: { items: [], has_more: false } });
    api.__respond("listTemplates", { data: [BAIL, NOTICE] });
});

test.after(() => {
    for (const id of liveTimers) { realClearInterval(id); realClearTimeout(id); }
    liveTimers.clear();
    dom.window.close();
});

/* ── the home ─────────────────────────────────────────────────────────────── */

test("Documents opens on the home, never on a remembered draft", async () => {
    // A remembered draft used to take over the page and drop the user into the
    // old flow's review step. The draft stays one click away in My Documents.
    rememberDraft("case-1", "doc-remembered", dom.window.localStorage);
    const p = await mountDocuments();
    assert.match(p.text(), /Start from a template/);
    assert.equal(api.__calls("getDocumentV2").length, 0, "a remembered draft was fetched and opened");
    assert.equal(api.__calls("getDocumentWorkspaceV2").length, 0);
    await p.unmount();
});

test("a sidebar 'New document' request shows the home", async () => {
    requestDocumentsView("new");
    const p = await mountDocuments();
    assert.match(p.text(), /Start from a template/);
    await p.unmount();
});

test("the document dashboard lists documents the client owns", async () => {
    api.__respond("myDocumentsV2", {
        data: {
            items: [{ id: "own-1", title: "An earlier notice",
                      review_status: "approved", revision_id: "rev-own-1",
                      pdf_sha256: "c".repeat(64), version: 1,
                      downloadable: true }],
            has_more: false,
        },
    });
    const p = await mountDocuments();
    assert.ok(api.__calls("myDocumentsV2").length >= 1,
              "the client's own documents were never requested");
    assert.match(p.text(), /My Documents/);
    assert.match(p.text(), /An earlier notice/);
    await p.unmount();
});

test("opening a row in My Documents opens it in the drafting workspace", async () => {
    api.__respond("myDocumentsV2", { data: { items: [{ id: "own-1", title: "Bail Application draft",
        review_status: "none", revision_id: "rev-1", pdf_sha256: SHA, version: 1, downloadable: true }], has_more: false } });
    respondWorkspace("own-1");
    const p = await mountDocuments();
    const open = [...p.container.querySelectorAll("#my-documents button")].find(b => b.textContent.trim() === "Open");
    await press(p, open);
    await p.settle(60);
    assert.ok(p.container.querySelector("[data-document-workspace]"), "Open did not go to the workspace");
    assert.equal(api.__calls("getDocumentWorkspaceV2").at(-1)?.args[0], "own-1");
    assert.doesNotMatch(p.text(), /Draft details|Final & export/, "the old guided flow is back");
    await p.unmount();
});

test("previewing a row previews that row's own document, in the Vault", async () => {
    api.__respond("myDocumentsV2", { data: { items: [{ id: "other-doc", title: "Another notice",
        review_status: "none", revision_id: "rev-other", pdf_sha256: "d".repeat(64), version: 1,
        downloadable: true }], has_more: false } });
    api.__respond("getDocumentV2", { data: { id: "other-doc", title: "Another notice", review_status: "none",
        current_version: 1, current_revision: { revision_id: "rev-other", pdf_sha256: "d".repeat(64) } } });
    const p = await mountDocuments();
    const previewBtn = [...p.container.querySelectorAll("#my-documents button")]
        .find(b => b.textContent.includes("Preview"));
    assert.ok(previewBtn, "no Preview control was rendered");
    await press(p, previewBtn);
    await p.settle(60);
    assert.ok(p.container.querySelector("[data-client-vault]"), "Preview did not open the Vault");
    assert.ok(api.__calls("getDocumentV2").some(c => c.args[0] === "other-doc"),
              "previewed a different document from the row that was clicked");
    await p.unmount();
});

/* ── a template becomes a draft in the workspace (2026-10-19) ─────────────── */

test("Use template → Create draft makes the document and opens it in the workspace", async () => {
    api.__respond("createDocumentV2", { data: { id: "doc-new" } });
    api.__respond("generateRevisionV2", { data: { revision_id: "rev-1", pdf_sha256: SHA, version: 1 } });
    respondWorkspace("doc-new");
    const p = await mountDocuments();
    const card = p.container.querySelector('[data-template="bail_application"]');
    await press(p, buttons(card, "Use template")[0]);
    assert.ok(editor(), "Use template did not open the template to fill");
    assert.equal(api.__calls("createDocumentV2").length, 0, "a document was made before any detail");

    await type(p, editor().querySelector("#cz_accused_name"), "Ali Raza");
    await type(p, editor().querySelector("#cz_grounds"), "The applicant was in Lahore.");
    await press(p, buttons(editor(), "Create draft")[0]);
    await p.settle(60);

    const [created, createKey] = api.__calls("createDocumentV2")[0].args;
    assert.equal(created.templateType, "bail_application");
    assert.equal(created.caseId, null, "a standalone draft was filed under a case");
    const [docId, gen] = api.__calls("generateRevisionV2")[0].args;
    assert.equal(docId, "doc-new");
    assert.deepEqual(gen.fields, { accused_name: "Ali Raza", grounds: "The applicant was in Lahore." });
    assert.ok(createKey, "the create carried no idempotency key");
    assert.equal(editor(), null, "the editor stayed open");
    assert.ok(p.container.querySelector("[data-document-workspace]"), "the draft did not open in the workspace");
    assert.equal(api.__calls("getDocumentWorkspaceV2").at(-1)?.args[0], "doc-new");
    assert.equal(api.__calls("saveDocumentWorkspaceV2").length, 0, "unchanged wording made an edited revision");
    assert.doesNotMatch(p.text(), /Draft details|Final & export/, "the old guided flow is back");
    await p.unmount();
});

test("a draft filled from a case is made under that case", async () => {
    api.__respond("extractDocumentFields", { data: { fields: { sender_name: "Ayesha Khan", demand: "Pay Rs 500,000" } } });
    api.__respond("createDocumentV2", { data: { id: "doc-case" } });
    api.__respond("generateRevisionV2", { data: { revision_id: "rev-1", pdf_sha256: SHA, version: 1 } });
    respondWorkspace("doc-case", "legal_notice");
    const p = await mountDocuments();
    await press(p, buttons(p.container.querySelector('[data-template="legal_notice"]'), "Use template")[0]);
    await type(p, editor().querySelector("#te-case"), "case-1");
    await press(p, buttons(editor(), "Fill")[0]);
    assert.deepEqual(api.__calls("extractDocumentFields")[0].args, ["case-1", "legal_notice"]);
    assert.equal(editor().querySelector("#cz_sender_name").value, "Ayesha Khan");
    assert.match(editor().textContent, /Filled 2 details from the case\. Check each one\./);
    await press(p, buttons(editor(), "Create draft")[0]);
    await p.settle(60);
    assert.equal(api.__calls("createDocumentV2")[0].args[0].caseId, "case-1");
    assert.deepEqual(api.__calls("generateRevisionV2")[0].args[1].fields,
        { sender_name: "Ayesha Khan", demand: "Pay Rs 500,000" });
    await p.unmount();
});

test("a refused generate keeps the editor open, and a retry reuses the same document", async () => {
    api.__respond("createDocumentV2", { data: { id: "doc-retry" } });
    let attempt = 0;
    api.__respond("generateRevisionV2", () => {
        attempt += 1;
        return attempt === 1
            ? { data: null, error: { message: "The revision could not be generated.", code: "generation_failed" }, status: 503 }
            : { data: { revision_id: "rev-1", pdf_sha256: SHA, version: 1 } };
    });
    respondWorkspace("doc-retry");
    const p = await mountDocuments();
    await press(p, buttons(p.container.querySelector('[data-template="bail_application"]'), "Use template")[0]);
    await type(p, editor().querySelector("#cz_accused_name"), "Ali Raza");
    await press(p, buttons(editor(), "Create draft")[0]);
    assert.ok(editor(), "the editor closed on a refused generate");
    assert.match(editor().querySelector('[role="alert"]').textContent, /could not be generated/);
    assert.equal(p.container.querySelector("[data-document-workspace]"), null, "a failed draft was reported as made");

    await press(p, buttons(editor(), "Create draft")[0]);
    await p.settle(60);
    const creates = api.__calls("createDocumentV2");
    assert.equal(creates.length, 2);
    assert.equal(creates[0].args[1], creates[1].args[1], "the retry made a second document");
    const gens = api.__calls("generateRevisionV2");
    assert.notEqual(gens[0].args[2], gens[1].args[2], "a failed generate's key was replayed");
    assert.ok(p.container.querySelector("[data-document-workspace]"));
    await p.unmount();
});

test("with Documents V2 off, Create draft says so instead of failing silently", async () => {
    api.__respond("createDocumentV2", { data: null, error: { message: "Not found", code: "feature_disabled" }, status: 404 });
    const p = await mountDocuments();
    await press(p, buttons(p.container.querySelector('[data-template="bail_application"]'), "Use template")[0]);
    await type(p, editor().querySelector("#cz_accused_name"), "Ali Raza");
    await press(p, buttons(editor(), "Create draft")[0]);
    assert.match(editor().querySelector('[role="alert"]').textContent, /needs Documents V2/);
    assert.equal(api.__calls("generateRevisionV2").length, 0);
    await p.unmount();
});

test("wording changed in the template editor becomes the drafted document's text", async () => {
    api.__respond("templateText", { data: { template_type: "bail_application",
        text_html: "<p>The applicant [[ACCUSED_NAME]] prays for bail.</p>" } });
    api.__respond("createDocumentV2", { data: { id: "doc-edit" } });
    api.__respond("generateRevisionV2", { data: { revision_id: "rev-1", pdf_sha256: SHA, version: 1 } });
    respondWorkspace("doc-edit");
    api.__respond("saveDocumentWorkspaceV2", { data: {
        revision_id: "rev-2", pdf_sha256: "b".repeat(64), version: 2, template_type: "edited_document" } });

    const p = await mountDocuments();
    await press(p, [...p.container.querySelector('[data-template="bail_application"]').querySelectorAll("button")]
        .find(b => b.textContent.trim() === "Use template"));   // the Edit button is gone (2026-11-22)
    const page = editor().querySelector('[aria-label="Document text"]');
    assert.match(page.textContent, /prays for bail/);
    // The client rewrites a sentence, keeping the detail's placeholder.
    await act(async () => {
        page.querySelector("p").firstChild.textContent = "Most respectfully, the applicant ";
        page.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
    });
    await type(p, editor().querySelector("#cz_accused_name"), "Ali <Khan>");
    await press(p, buttons(editor(), "Create draft")[0]);
    await p.settle(60);

    const saves = api.__calls("saveDocumentWorkspaceV2");
    assert.equal(saves.length, 1, "the edited wording was dropped");
    const [docId, payload] = saves[0].args;
    assert.equal(docId, "doc-edit");
    assert.match(payload.bodyHtml, /Most respectfully, the applicant Ali &lt;Khan&gt; prays for bail\./);
    assert.equal(payload.expectedRevisionId, "rev-1");
    assert.equal(payload.fields ?? null, null);
    assert.ok(p.container.querySelector("[data-document-workspace]"));
    await p.unmount();
});

test("edited wording is filled as text, and a blank detail prints as a line", async () => {
    const { fillWordingTokens } = await import("../src/components/client/ModDocuments.jsx");
    assert.equal(fillWordingTokens("<p>[[A_B]] and [[C]]</p>", { a_b: "x & y" }), "<p>x &amp; y and ______</p>");
});
