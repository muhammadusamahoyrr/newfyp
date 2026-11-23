/* ModIntake, mounted. The test that was missing.
 *
 * WHY THIS FILE EXISTS
 *
 * Intake gained ~100 tests across the service layer, the graph, the HTTP
 * contracts and four source-reading frontend files. Two critical defects
 * survived all of them:
 *
 *   the intake token was cleared at CONVERSION while confirmation happened on
 *   the next screen, so a refresh in between started a fresh intake and left
 *   the draft unreachable — and permanently unconfirmable
 *
 *   confirmation scheduled lawyer matching, and the client's category
 *   correction was saved on the screen AFTER it, so matching cached results for
 *   the category they had just rejected
 *
 * Both are ORDERING across a refresh boundary. A service test cannot see the
 * order the browser calls things in; a source-reading test cannot see what a
 * remount restores. Only driving the real component can.
 *
 * So these tests assert on the SEQUENCE of API calls and on what survives a
 * remount, not on rendered markup — markup changes with design, and the
 * ordering is the contract.
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
                    "MutationObserver", "getComputedStyle", "localStorage", "sessionStorage",
                    "requestAnimationFrame", "cancelAnimationFrame", "Blob",
                    "FileReader", "URL"]) {
    define(name, dom.window[name]);
}
define("IS_REACT_ACT_ENVIRONMENT", true);

/* jsdom has no `matchMedia`, and `useIsMobile` calls it on mount (i18n.jsx:53).
 * Stubbed on the window rather than the global because that is where the hook
 * looks. Reports desktop: the intake layout differs by breakpoint and these
 * tests are about call ordering, not layout. */
dom.window.matchMedia = (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
});

/* Component code uses the GLOBAL timers, which `window.close()` does not
 * release — the process then outlives the runner with every test passing. */
const liveTimers = new Set();
const realSetInterval = globalThis.setInterval;
const realClearInterval = globalThis.clearInterval;
const realSetTimeout = globalThis.setTimeout;
const realClearTimeout = globalThis.clearTimeout;
define("setInterval", (...a) => { const id = realSetInterval(...a); liveTimers.add(id); return id; });
define("clearInterval", id => { liveTimers.delete(id); return realClearInterval(id); });
define("setTimeout", (...a) => { const id = realSetTimeout(...a); liveTimers.add(id); return id; });
define("clearTimeout", id => { liveTimers.delete(id); return realClearTimeout(id); });

const React = (await import("react")).default;
const { act } = await import("react");
const { createRoot } = await import("react-dom/client");
const api = await import("./support/api-stub.mjs");

const { createElement: h } = React;

const TOKEN = "tok-mounted";
const CASE_ID = "case-mounted";

/* The intake as the server holds it once conversion has happened: completed,
 * with a case that is still a DRAFT awaiting confirmation. */
function convertedIntake(over = {}) {
    return {
        session_token: TOKEN,
        current_step: 5,
        completed: true,
        case_id: CASE_ID,
        case_status: "draft",
        ai_structured_case: {
            summary: "A tenancy arrears claim.",
            applicable_laws: ["PPC Section 302 — example"],
            recommended_actions: ["File a suit"],
            risk_level: "medium",
            grounded: true,
            grounding_status: "grounded",
        },
        steps: {
            1: { province: "punjab", party_role: "plaintiff" },
            2: { case_type: "civil", urgency: "medium" },
            3: { incident_description: "My landlord seized my shop." },
        },
        clarification_qa: [],
        evidence_files: [],
        ...over,
    };
}

/* A pending draft is now offered as a choice (2026-10-12). Most tests are
 * about what happens AFTER resuming it, so the default is to take
 * "Continue that case"; `{ draftChoice: "leave" }` keeps the card up. */
async function mountIntake({ draftChoice = "continue" } = {}) {
    const { default: ModIntake } =
        await import("../src/components/client/ModIntake.jsx");
    const { CaseProvider } = await import("../src/components/client/CaseContext.jsx");
    const { AuthProvider } = await import("../src/context/AuthContext.jsx");
    const { ToastContainer } = await import("../src/components/shared/Toast.jsx");
    const { DARK } = await import("../src/components/admin/themes.js");
    const { ThemeCtx, HeaderActionsCtx } =
        await import("../src/components/client/theme.js");

    const container = dom.window.document.createElement("div");
    dom.window.document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => {
        root.render(h(
            AuthProvider, null,
            h(ThemeCtx.Provider, { value: DARK },
              h(HeaderActionsCtx.Provider,
                { value: { setHeaderActions: () => {} } },
                h(ToastContainer, { theme: DARK },
                  h(CaseProvider, null, h(ModIntake)))))));
    });
    await act(async () => { await new Promise(r => setTimeout(r, 40)); });
    const choice = container.querySelector("[data-continue-draft]");
    if (choice && draftChoice === "continue") {
        await act(async () => { choice.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
        await act(async () => { await new Promise(r => setTimeout(r, 30)); });
    }
    return {
        container,
        unmount: async () => {
            await act(async () => { root.unmount(); });
            container.remove();
        },
    };
}

/* The key ModIntake actually reads: user-scoped, per lib/intakeStorage.js. */
const TOKEN_KEY = "aai-intake:u1:aai-intake-token";

function seedToken(value = TOKEN) {
    dom.window.localStorage.setItem(TOKEN_KEY, value);
}

function storedToken() {
    return dom.window.localStorage.getItem(TOKEN_KEY);
}

function reset() {
    api.__reset();
    try { dom.window.localStorage.clear(); } catch { /* ignore */ }
    api.__respond("getMe", { data: { _id: "u1", role: "client", full_name: "C" } });
    api.__respond("bootstrapAuth", { data: { _id: "u1", role: "client" } });
    api.__respond("getNotifications", { data: [] });
    api.__respond("listCases", { data: { items: [] } });
    api.__respond("listAppointments", { data: { items: [] } });
    api.__respond("intakeStart", { data: { session_token: TOKEN } });
    api.__respond("intakeGet", { data: convertedIntake() });
    api.__respond("intakeSaveStep", { data: { current_step: 2 } });
    api.__respond("intakeClarify", { data: { question: null, done: true, round: 0 } });
    api.__respond("intakeConvert", { data: { case_id: CASE_ID, completed: true } });
    api.__respond("confirmCase", { data: { _id: CASE_ID, status: "open" } });
    api.__respond("updateCase", { data: { _id: CASE_ID, status: "open" } });
    // Default: the server has nothing to resume. Tests that care override it.
    api.__respond("getResumableIntake", { data: null });
}

function names() {
    return api.__calls().map(c => c.name);
}

function findButton(container, text) {
    return [...container.querySelectorAll("button")]
        .find(b => (b.textContent || "").includes(text));
}

async function click(el) {
    await act(async () => {
        el.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
    });
    await act(async () => { await new Promise(r => setTimeout(r, 30)); });
}

async function confirmFinalCategory(container) {
    await click(findButton(container, "Continue to category"));
    const complete = findButton(container, "Confirm & open case");
    assert.ok(complete, "the final category confirmation screen did not open");
    await click(complete);
}

// ── #1: the draft must stay reachable across a refresh ─────────────────────

test("the intake token survives conversion, so a refresh can still reach the draft", async () => {
    reset();
    seedToken();
    const { unmount } = await mountIntake();

    // Resuming a CONVERTED intake whose case is still a draft — the state a
    // refresh on the review screen lands in. The token must still be stored: it
    // is the only route back to an unconfirmed draft.
    assert.ok(storedToken() === TOKEN,
        "the intake token was cleared before confirmation — a refresh here "
        + "starts a new intake and the draft becomes unconfirmable for ever");
    await unmount();
});

test("a remount after conversion resumes the intake rather than starting a new one", async () => {
    reset();
    seedToken();
    const first = await mountIntake();
    await first.unmount();

    // Re-stub everything EXCEPT localStorage: the point is that the browser
    // still holds the token across the remount. Auth included — without it
    // `user` is null and the resume effect returns before it can run.
    api.__reset();
    api.__respond("bootstrapAuth", { data: { _id: "u1", role: "client" } });
    api.__respond("getMe", { data: { _id: "u1", role: "client" } });
    api.__respond("getNotifications", { data: [] });
    api.__respond("listCases", { data: { items: [] } });
    api.__respond("listAppointments", { data: { items: [] } });
    api.__respond("intakeGet", { data: convertedIntake() });
    api.__respond("intakeStart", { data: { session_token: "tok-SHOULD-NOT-HAPPEN" } });

    const second = await mountIntake();

    assert.equal(api.__calls("intakeStart").length, 0,
        "the refresh minted a NEW intake, abandoning the draft");
    assert.ok(api.__calls("intakeGet").length >= 1,
        "the refresh did not resume the existing intake");
    await second.unmount();
});

test("the token is cleared only once the case is confirmed", async () => {
    reset();
    seedToken();
    const { container, unmount } = await mountIntake();

    await confirmFinalCategory(container);

    assert.equal(api.__calls("confirmCase").length, 1,
        "the confirm button did not call the server");

    assert.equal(storedToken(), null, "the token outlived the completed intake");
    await unmount();
});

test("OCR text must be reviewed and confirmed before analysis can continue", async () => {
    reset();
    seedToken();
    const paused = convertedIntake({
        completed: false,
        case_id: null,
        case_status: null,
        ai_structured_case: null,
        ocr_review_required: true,
        evidence_files: [{
            file_id: "file-ocr",
            filename: "notice-scan.pdf",
            content_type: "application/pdf",
            ocr_review_required: true,
        }],
    });
    api.__respond("intakeGet", { data: paused });
    api.__respond("getIntakeOcrReview", { data: [{
        revision_id: "rev-1",
        file_id: "file-ocr",
        page_number: 1,
        source_sha256: "a".repeat(64),
        text_sha256: "b".repeat(64),
        text: "The flne is 1000 rupees",
        confirmed: false,
        review_state: "pending_confirmation",
    }] });
    api.__respond("confirmIntakeOcrPage", { data: {
        revision_id: "rev-1", confirmed: true,
    } });
    api.__respond("intakeConvert", { data: {
        case_id: CASE_ID, completed: true, ai_case_type: "civil",
    } });

    const mounted = await mountIntake();
    assert.match(mounted.container.textContent, /Review Extracted Text/);
    const editor = mounted.container.querySelector(
        'textarea[aria-label="Extracted text page 1"]');
    assert.ok(editor, "the OCR page text is not visible for review");
    assert.equal(editor.value, "The flne is 1000 rupees");

    const continueButton = findButton(mounted.container, "Continue analysis");
    assert.equal(continueButton.disabled, true,
        "analysis can continue before the OCR page is confirmed");
    await click(findButton(mounted.container, "Confirm this page"));
    assert.equal(api.__calls("confirmIntakeOcrPage").length, 1);
    assert.equal(continueButton.disabled, false);

    await click(continueButton);
    assert.equal(api.__calls("intakeConvert").length, 1,
        "confirmation did not resume the paused conversion");
    await mounted.unmount();
});

test("a failed OCR-review load has a visible retry and does not strand the intake", async () => {
    reset();
    seedToken();
    api.__respond("intakeGet", { data: convertedIntake({
        completed: false,
        case_id: null,
        case_status: null,
        ai_structured_case: null,
        ocr_review_required: true,
        evidence_files: [{
            file_id: "file-ocr", filename: "notice-scan.pdf",
            content_type: "application/pdf", ocr_review_required: true,
        }],
    }) });
    let attempts = 0;
    api.__respond("getIntakeOcrReview", () => {
        attempts += 1;
        if (attempts === 1) return { error: { message: "temporarily offline" } };
        return { data: [{
            revision_id: "rev-retry", file_id: "file-ocr", page_number: 1,
            source_sha256: "a".repeat(64), text_sha256: "b".repeat(64),
            text: "Recovered extracted text", confirmed: false,
        }] };
    });

    const mounted = await mountIntake();
    const retry = findButton(mounted.container, "Try loading again");
    assert.ok(retry, "a transient review failure left no recovery control");
    assert.equal(findButton(mounted.container, "Continue analysis").disabled, true);

    await click(retry);
    assert.equal(api.__calls("getIntakeOcrReview").length, 2);
    assert.ok(mounted.container.querySelector(
        'textarea[aria-label="Extracted text page 1"]'));
    await mounted.unmount();
});

test("one loaded OCR file cannot hide a missing second file", async () => {
    reset();
    seedToken();
    api.__respond("intakeGet", { data: convertedIntake({
        completed: false,
        case_id: null,
        case_status: null,
        ai_structured_case: null,
        ocr_review_required: true,
        evidence_files: ["file-a", "file-b"].map(file_id => ({
            file_id, filename: `${file_id}.pdf`,
            content_type: "application/pdf", ocr_review_required: true,
        })),
    }) });
    api.__respond("getIntakeOcrReview", (_token, fileId) => ({
        data: fileId === "file-a" ? [{
            revision_id: "rev-a", file_id: "file-a", page_number: 1,
            source_sha256: "a".repeat(64), text_sha256: "b".repeat(64),
            text: "Only the first file loaded", confirmed: true,
        }] : [],
    }));

    const mounted = await mountIntake();
    assert.match(
        mounted.container.textContent,
        /one or more extracted files has no current review pages/i,
    );
    assert.equal(findButton(mounted.container, "Continue analysis").disabled, true);
    assert.equal(
        mounted.container.querySelectorAll('[aria-label^="Extracted text page"]').length,
        0,
        "a partial response was rendered as if the review set were complete",
    );
    await mounted.unmount();
});

// ── #2: the category must be saved before matching is triggered ────────────

test("confirmation calls the server exactly once per press", async () => {
    reset();
    seedToken();
    const { container, unmount } = await mountIntake();

    await confirmFinalCategory(container);
    assert.equal(api.__calls("confirmCase").length, 1);
    assert.equal(api.__calls("confirmCase")[0].args[1], "civil",
        "the authoritative category was not part of the opening transition");
    await unmount();
});

// ── the client names the case (2026-11-23) ────────────────────────────────
// Cases were titled with the first 80 characters of the story ("My name is
// Imran Ali and I live in…"). The confirm step now asks for a short name.

test("the case name starts as a suggestion from the category, and is sent on confirm", async () => {
    reset();
    seedToken();
    const { container, unmount } = await mountIntake();
    await click(findButton(container, "Continue to category"));
    const input = container.querySelector("[data-case-name]");
    assert.ok(input, "no Case name field");
    assert.match(input.value, /^Civil matter/, "the suggestion does not follow the category");
    await click(findButton(container, "Confirm & open case"));
    assert.equal(api.__calls("confirmCase")[0].args[2], input.value.trim(), "the name was not sent");
    await unmount();
});

test("a name the client types is the one sent", async () => {
    reset();
    seedToken();
    const { container, unmount } = await mountIntake();
    await click(findButton(container, "Continue to category"));
    const input = container.querySelector("[data-case-name]");
    const setter = Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value").set;
    await act(async () => { setter.call(input, "  Rent deposit dispute  "); input.dispatchEvent(new dom.window.Event("input", { bubbles: true })); });
    await click(findButton(container, "Confirm & open case"));
    assert.equal(api.__calls("confirmCase")[0].args[2], "Rent deposit dispute");
    await unmount();
});

test("a name that is too short cannot be confirmed", async () => {
    reset();
    seedToken();
    const { container, unmount } = await mountIntake();
    await click(findButton(container, "Continue to category"));
    const input = container.querySelector("[data-case-name]");
    const setter = Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value").set;
    await act(async () => { setter.call(input, "ab"); input.dispatchEvent(new dom.window.Event("input", { bubbles: true })); });
    assert.ok(findButton(container, "Confirm & open case").disabled, "a 2-character name could be confirmed");
    assert.match(container.textContent, /Use 3 to 80 characters/);
    assert.equal(api.__calls("confirmCase").length, 0);
    await unmount();
});

test("confirming re-reads the shared case list, so the draft stops showing as one (2026-11-23)", async () => {
    // Without this, Overview kept saying "Confirm your draft case" and the
    // Intake badge stayed until a full reload.
    reset();
    seedToken();
    const { container, unmount } = await mountIntake();
    const before = api.__calls("listCases").length;
    await confirmFinalCategory(container);
    assert.equal(api.__calls("confirmCase").length, 1);
    assert.ok(api.__calls("listCases").length > before, "the case list was not re-read after confirming");
    await unmount();
});

test("a refused confirmation does not re-read the case list", async () => {
    reset();
    seedToken();
    api.__respond("confirmCase", { error: { message: "server said no" } });
    const { container, unmount } = await mountIntake();
    const before = api.__calls("listCases").length;
    await confirmFinalCategory(container);
    assert.equal(api.__calls("listCases").length, before);
    await unmount();
});

test("a restored authoritative category is what confirmation submits", async () => {
    reset();
    seedToken();
    api.__respond("intakeGet", {
        data: convertedIntake({ case_type: "criminal", ai_case_type: "criminal" }),
    });
    const { container, unmount } = await mountIntake();
    await confirmFinalCategory(container);
    assert.equal(api.__calls("confirmCase")[0].args[1], "criminal");
    await unmount();
});

test("a failed confirmation does not advance or clear the token", async () => {
    reset();
    seedToken();
    api.__respond("confirmCase", { error: { message: "server said no" } });
    const { container, unmount } = await mountIntake();

    await confirmFinalCategory(container);

    assert.equal(storedToken(), TOKEN,
        "the token was cleared even though the case is still a draft");
    // Still on the category screen, so the same final action can be retried.
    assert.ok(findButton(container, "Confirm & open case"));
    await unmount();
});

// ── #4: a refresh restores WHERE they were ─────────────────────────────────

test("an unfinished intake resumes past step 1", async () => {
    reset();
    api.__respond("intakeGet", {
        data: convertedIntake({
            completed: false, case_id: null, case_status: null, current_step: 3,
            ai_structured_case: null,
        }),
    });
    seedToken();
    const { container, unmount } = await mountIntake();

    // Step 1 asks for a role. If we resumed correctly we are past it.
    // The role CHOICE, not the word: since 2026-10-10 the steps rail also
    // says "Plaintiff · Punjab" once step 1 is done.
    const onStepOne = !!findButton(container, "I'm taking action");
    assert.equal(onStepOne, false,
        "a mid-intake refresh restored the answers but dropped the client back "
        + "to step 1, with no indication of where they had got to");
    await unmount();
});

test("a restored intake refills the description the client typed", async () => {
    reset();
    api.__respond("intakeGet", {
        data: convertedIntake({
            completed: false, case_id: null, case_status: null, current_step: 2,
            ai_structured_case: null,
        }),
    });
    seedToken();
    const { container, unmount } = await mountIntake();

    // Step 2 opens in VOICE mode, so the description textarea is not rendered
    // until the client switches. Clicking through is what a returning client
    // does to see what they had written.
    const textMode = findButton(container, "Text Input");
    assert.ok(textMode, "step 2 did not render an input-mode switch");
    await click(textMode);

    const restored = [...container.querySelectorAll("textarea")]
        .some(t => (t.value || "").includes("My landlord seized my shop"));
    assert.ok(restored, "the client's own description was not restored");
    await unmount();
});

// ── the logout route to the same orphaning ────────────────────────────────

test("with NO stored token the server is asked before a new intake is started", async () => {
    /* Sign-out clears the token. Keeping it until confirmation closed the
     * REFRESH route to an unconfirmable draft and left this one open: log out
     * between converting and confirming and the draft became unreachable for
     * ever, because nothing but that token could find it. */
    reset();
    // localStorage deliberately empty — this is the post-logout state.
    const { unmount } = await mountIntake();

    assert.ok(api.__calls("getResumableIntake").length >= 1,
        "no token, and the server was never asked whether anything is unfinished");
    await unmount();
});

test("a resumable draft is adopted instead of starting fresh", async () => {
    reset();
    api.__respond("getResumableIntake", { data: convertedIntake() });
    const { container, unmount } = await mountIntake();

    assert.equal(api.__calls("intakeStart").length, 0,
        "a fresh intake was minted while a draft was waiting to be confirmed");
    assert.equal(storedToken(), TOKEN, "the resumed token was not stored");
    assert.ok(findButton(container, "Continue to category"),
        "the resumed draft did not land on the screen that can confirm it");
    await unmount();
});

test("the resumed draft is confirmable — the orphaning is closed", async () => {
    reset();
    api.__respond("getResumableIntake", { data: convertedIntake() });
    const { container, unmount } = await mountIntake();

    await confirmFinalCategory(container);

    const confirmed = api.__calls("confirmCase");
    assert.equal(confirmed.length, 1, "the resumed draft could not be confirmed");
    assert.equal(confirmed[0].args[0], CASE_ID);
    await unmount();
});

test("a fresh intake is started only when the server has nothing", async () => {
    reset();
    api.__respond("getResumableIntake", { data: null });
    const { unmount } = await mountIntake();

    assert.equal(api.__calls("intakeStart").length, 1,
        "a client with nothing unfinished did not get a new intake");
    await unmount();
});

test("a resume failure never creates a duplicate intake", async () => {
    reset();
    api.__respond("getResumableIntake", { error: { message: "offline" } });
    const { container, unmount } = await mountIntake();
    assert.equal(api.__calls("intakeStart").length, 0);
    assert.ok((container.textContent || "").includes("Could not check your saved intake"));
    assert.ok(findButton(container, "Try again"));
    await unmount();
});

test("an unusable stored token falls back to the server rather than dead-ending", async () => {
    /* A token pointing at nothing is exactly when an unfinished intake is most
     * likely to exist — it used to be dropped and replaced with a new session. */
    reset();
    seedToken("tok-STALE");
    api.__respond("intakeGet", { error: { message: "not found" } });
    api.__respond("getResumableIntake", { data: convertedIntake() });

    const { unmount } = await mountIntake();

    assert.ok(api.__calls("getResumableIntake").length >= 1);
    assert.equal(storedToken(), TOKEN, "the stale token was not replaced by the real one");
    await unmount();
});

// ── the call ORDER, which is what both defects were about ─────────────────

test("no lawyer-facing call is made while the case is still a draft", async () => {
    reset();
    seedToken();
    const { unmount } = await mountIntake();

    const lawyerFacing = names().filter(
        n => ["matchLawyers", "requestEngagement", "bookAppointment"].includes(n));
    assert.deepEqual(lawyerFacing, [],
        `an unconfirmed draft reached a lawyer flow: ${lawyerFacing.join(", ")}`);
    await unmount();
});

test("confirmCase is never called without a case id", async () => {
    reset();
    api.__respond("intakeGet", {
        data: convertedIntake({ completed: false, case_id: null, case_status: null }),
    });
    seedToken();
    const { container, unmount } = await mountIntake();

    const confirm = findButton(container, "Continue to category");
    if (confirm) await click(confirm);

    assert.equal(api.__calls("confirmCase").length, 0,
        "confirmation was attempted for a case that does not exist");
    await unmount();
});

// ── the analysis must disclose what it did not read ────────────────────────
//
// The unit tests for `extractionStatus.js` prove the wording. These prove the
// wiring, which is the half that silently does not happen: a perfectly correct
// label helper that no screen renders discloses nothing at all.

test("a partially read file is disclosed on the screen showing the analysis", async () => {
    reset();
    const intake = convertedIntake({
        evidence_files: [{
            file_id: "f-bundle", filename: "court-bundle.pdf",
            content_type: "application/pdf", size: 84000,
            extraction_status: "partially_read",
            completeness: "partial_or_uncertain",
            pages_total: 5, pages_with_text: 2,
        }],
    });
    intake.ai_structured_case.evidence_extraction = [{
        file_id: "f-bundle", status: "partially_read",
        completeness: "partial_or_uncertain",
        pages_total: 5, pages_with_text: 2,
    }];
    api.__respond("intakeGet", { data: intake });
    seedToken();

    const { container, unmount } = await mountIntake();
    const text = container.textContent || "";

    assert.match(text, /did not see all of your evidence/i,
        "the analysis screen did not disclose the gap");
    assert.match(text, /court-bundle\.pdf/,
        "the client is not told WHICH file was short-read");
    assert.match(text, /3 of 5 pages produced no text/,
        "the client is not told how much was missed");
    await unmount();
});

test("a fully read bundle is not given a warning it does not deserve", async () => {
    reset();
    const intake = convertedIntake({
        evidence_files: [{
            file_id: "f-ok", filename: "typed.pdf",
            content_type: "application/pdf", size: 1200,
            extraction_status: "readable", completeness: "complete",
            pages_total: 2, pages_with_text: 2,
        }],
    });
    intake.ai_structured_case.evidence_extraction = [{
        file_id: "f-ok", status: "readable", completeness: "complete",
        pages_total: 2, pages_with_text: 2,
    }];
    api.__respond("intakeGet", { data: intake });
    seedToken();

    const { container, unmount } = await mountIntake();
    const text = container.textContent || "";

    assert.doesNotMatch(text, /did not see all of your evidence/i);
    assert.match(text, /read in full/i);
    await unmount();
});

test("the disclosure never claims a page was a scan", async () => {
    reset();
    const intake = convertedIntake({
        evidence_files: [{
            file_id: "f-x", filename: "bundle.pdf",
            content_type: "application/pdf",
            extraction_status: "partially_read",
            pages_total: 4, pages_with_text: 1,
        }],
    });
    intake.ai_structured_case.evidence_extraction = [{
        file_id: "f-x", status: "partially_read",
        pages_total: 4, pages_with_text: 1,
    }];
    api.__respond("intakeGet", { data: intake });
    seedToken();

    const { container, unmount } = await mountIntake();
    const disclosure = container.querySelector('[data-testid="evidence-gaps"]');

    assert.ok(disclosure, "no disclosure block rendered");
    const text = (disclosure.textContent || "").toLowerCase();
    assert.ok(!text.includes("scan"), "the UI claimed to detect a scan");
    assert.ok(!text.includes("photo"), "the UI claimed to detect a photo");
    await unmount();
});

// ── mounted: the screen must not announce a success it cannot support ──────

test("a truncated file is never announced as read in full and included", async () => {
    reset();
    const intake = convertedIntake({
        evidence_files: [{
            file_id: "f-trunc", filename: "long-contract.pdf",
            content_type: "application/pdf", size: 90000,
            extraction_status: "readable", completeness: "complete",
            pages_total: 8, pages_with_text: 8, prompt_truncated: true,
        }],
    });
    // Every page was read; the ANALYSIS was shown only the beginning. The
    // optimistic reading of that is the one a client would never question.
    intake.ai_structured_case.evidence_extraction = [{
        file_id: "f-trunc", status: "readable", completeness: "complete",
        pages_total: 8, pages_with_text: 8, truncated: true,
    }];
    api.__respond("intakeGet", { data: intake });
    seedToken();

    const { container, unmount } = await mountIntake();
    const text = container.textContent || "";

    assert.doesNotMatch(text, /were read in full and included in this analysis/,
        "a truncated file produced an all-clear");
    assert.match(text, /did not see all of your evidence/i);
    await unmount();
});

test("a storage-only file survives a restore without becoming an error", async () => {
    reset();
    const intake = convertedIntake({
        evidence_files: [{
            file_id: "f-doc", filename: "affidavit.doc",
            content_type: "application/msword", size: 40000,
            analysis_support: "storage_only",
            notice: "Saved, but legacy Word (.doc) files cannot be read for analysis.",
            extraction_status: "storage_only",
        }],
    });
    intake.ai_structured_case.evidence_extraction = [
        { file_id: "f-doc", status: "storage_only" }];
    api.__respond("intakeGet", { data: intake });
    seedToken();

    const { container, unmount } = await mountIntake();
    const text = container.textContent || "";

    assert.match(text, /Stored, not analysed/i);
    assert.doesNotMatch(text, /Could not be read/i,
        "a perfectly fine file was reported as a failure after a reload");
    await unmount();
});

test("an unknown page count is never rendered as a confident zero", async () => {
    reset();
    const intake = convertedIntake({
        evidence_files: [{
            file_id: "f-unk", filename: "bundle.pdf",
            content_type: "application/pdf",
            extraction_status: "partially_read",
            pages_total: 6, pages_with_text: null,
        }],
    });
    intake.ai_structured_case.evidence_extraction = [{
        file_id: "f-unk", status: "partially_read",
        pages_total: 6, pages_with_text: null,
    }];
    api.__respond("intakeGet", { data: intake });
    seedToken();

    const { container, unmount } = await mountIntake();
    const text = container.textContent || "";

    assert.doesNotMatch(text, /6 of 6 pages produced no text/,
        "an unknown counter was rendered as a definite claim");
    assert.doesNotMatch(text, /NaN/);
    await unmount();
});

test("a genuinely complete analysis may still say so", async () => {
    // The guards must not have made every outcome a warning; a real all-clear
    // that can no longer be given is its own kind of dishonesty.
    reset();
    const intake = convertedIntake({
        evidence_files: [{
            file_id: "f-ok", filename: "typed.pdf",
            content_type: "application/pdf",
            extraction_status: "readable", completeness: "complete",
            pages_total: 2, pages_with_text: 2, prompt_truncated: false,
        }],
    });
    intake.ai_structured_case.evidence_extraction = [{
        file_id: "f-ok", status: "readable", completeness: "complete",
        pages_total: 2, pages_with_text: 2, truncated: false,
    }];
    api.__respond("intakeGet", { data: intake });
    seedToken();

    const { container, unmount } = await mountIntake();
    const text = container.textContent || "";

    assert.match(text, /were read in full and included in this analysis/);
    assert.doesNotMatch(text, /did not see all of your evidence/i);
    await unmount();
});

test.after(() => {
    for (const id of liveTimers) { realClearTimeout(id); realClearInterval(id); }
    liveTimers.clear();
    dom.window.close();
});

// ── the legacy-Urdu-encoding status, as the client actually sees it ─────────
//
// The backend can report that a file HAS a text layer which decodes to nothing
// usable. Before the UI knew that status it fell through to the default arm and
// rendered "Read status unknown" — which tells the client nothing, implies we
// never looked, and offers no remedy. A source-reading test cannot catch that:
// the fall-through only happens once the component is mounted with real data.

const LEGACY_FILE = {
    file_id: "f-urdu",
    filename: "PCS_Act_1974.pdf",
    content_type: "application/pdf",
    size: 204800,
    extraction_status: "unextractable_encoding",
    completeness: "none",
    pages_total: 9,
    pages_with_text: 0,
    pages_text_untrusted: 9,
};

function extractionLine(container, fileId) {
    return container.querySelector(`[data-testid="extraction-${fileId}"]`);
}

/* The evidence list lives on the upload screen, behind "do you have evidence".
   A converted intake lands past it, so these tests restore an UNFINISHED one
   sitting on that step with files already uploaded. */
function intakeOnEvidenceStep(files) {
    const data = convertedIntake({ evidence_files: files });
    return {
        ...data,
        completed: false,
        case_id: null,
        case_status: null,
        current_step: 2,
        steps: { ...data.steps, 4: { has_evidence: true } },
    };
}

test("a legacy-encoding file renders its own status, not 'Read status unknown'", async () => {
    reset();
    seedToken();
    api.__respond("intakeGet", {
        data: intakeOnEvidenceStep([LEGACY_FILE]),
    });
    const { container, unmount } = await mountIntake();

    const line = extractionLine(container, "f-urdu");
    assert.ok(line, "the extraction status line was not rendered at all");
    assert.equal(line.getAttribute("data-state"), "legacy_encoding");
    assert.match(line.textContent, /Unsupported legacy Urdu encoding/);
    assert.doesNotMatch(line.textContent, /Read status unknown/);

    await unmount();
});

test("the mounted UI tells the client what would actually help", async () => {
    reset();
    seedToken();
    api.__respond("intakeGet", {
        data: intakeOnEvidenceStep([LEGACY_FILE]),
    });
    const { container, unmount } = await mountIntake();

    const text = extractionLine(container, "f-urdu").textContent;

    assert.match(text, /typed text or an English translation/);
    // Urdu OCR is unavailable, so a scan would be exactly as unreadable.
    assert.doesNotMatch(text, /scan/i);
    assert.doesNotMatch(text, /photo/i);

    await unmount();
});

test("no raw extracted mojibake reaches the mounted UI", async () => {
    reset();
    seedToken();
    api.__respond("intakeGet", {
        data: intakeOnEvidenceStep([LEGACY_FILE]),
    });
    const { container, unmount } = await mountIntake();

    const body = container.textContent;
    for (const fragment of ["Z}5i]w", "!!!!", "%^&*l1", "}[O5i#w"]) {
        assert.ok(!body.includes(fragment),
            `raw extracted mojibake reached the page: ${fragment}`);
    }

    await unmount();
});

test("a readable file is still shown as read in full", async () => {
    reset();
    seedToken();
    api.__respond("intakeGet", {
        data: intakeOnEvidenceStep([{
            file_id: "f-ok", filename: "notice.pdf",
            content_type: "application/pdf", size: 1024,
            extraction_status: "readable", completeness: "complete",
            pages_total: 2, pages_with_text: 2,
        }]),
    });
    const { container, unmount } = await mountIntake();

    const line = extractionLine(container, "f-ok");
    assert.equal(line.getAttribute("data-state"), "complete");
    assert.match(line.textContent, /Read in full/);

    await unmount();
});

// ── a lost /convert response must not strand the intake ────────────────────
//
// The dev proxy gives up on /convert long before the server does, so the
// server completes the case while the browser shows a failure. The retry then
// re-sent the last answer to /clarify, which the finished intake refuses (409),
// and the handler stopped there: the button did nothing, forever, because the
// one call that would have answered — an idempotent /convert — was never made.

function answeredOnStep3() {
    return convertedIntake({
        completed: false, case_id: null, case_status: null,
        ai_structured_case: null, current_step: 3,
        clarification_qa: [1, 2, 3, 4].map(n => ({ q: `Question ${n}?`, a: `Answer ${n}` })),
    });
}

test("a 409 from /clarify on retry goes straight to /convert", async () => {
    reset();
    seedToken();
    api.__respond("intakeGet", { data: answeredOnStep3() });
    api.__respond("intakeClarify", {
        data: null, status: 409,
        error: { message: "This intake changed or started converting. Reload before answering." },
    });
    api.__respond("intakeConvert", { data: {
        case_id: CASE_ID, completed: true, ai_case_type: "civil",
    } });
    const { container, unmount } = await mountIntake();

    const before = api.__calls("intakeSaveStep").length;
    const complete = findButton(container, "Complete & Continue");
    assert.ok(complete, "the step-3 button did not render");
    await click(complete);

    assert.equal(api.__calls("intakeConvert").length, 1,
        "the retry never reached the idempotent /convert");
    assert.equal(api.__calls("intakeSaveStep").length, before,
        "step writes were sent to an intake the server says is converting");
    await unmount();
});

test("any other /clarify failure still stops before analysis", async () => {
    reset();
    seedToken();
    api.__respond("intakeGet", { data: answeredOnStep3() });
    api.__respond("intakeClarify", {
        data: null, status: 0, error: { message: "Network error." },
    });
    const { container, unmount } = await mountIntake();

    await click(findButton(container, "Complete & Continue"));

    assert.equal(api.__calls("intakeConvert").length, 0,
        "analysis ran without the client's final answer");
    await unmount();
});

test("every clarify call carries the app language, so the server can pin it", async () => {
    // The server used to leave the language to the model, which mixed English
    // and Urdu questions within one intake. It now decides — from this value
    // and the description — and needs the value on every call.
    reset();
    seedToken();
    api.__respond("intakeGet", { data: answeredOnStep3() });
    const { container, unmount } = await mountIntake();

    await click(findButton(container, "Complete & Continue"));

    const calls = api.__calls("intakeClarify");
    assert.ok(calls.length >= 1);
    for (const c of calls) assert.equal(c.args[2], "en", "a clarify call omitted the language");
    await unmount();
});

// ── QA fixes (2026-10-12) ──────────────────────────────────────────────────

function onStep2(over = {}) {
    return convertedIntake({
        completed: false, case_id: null, case_status: null, ai_structured_case: null,
        current_step: 2, ...over,
    });
}

const tick = (ms = 40) => act(async () => { await new Promise(r => setTimeout(r, ms)); });
const currentStep = (container) => container.querySelector(".in-rstep[aria-current] .t")?.textContent;

test("before the intake exists, step 1 cannot move on (nothing would be saved)", async () => {
    reset();
    api.__respond("intakeStart", { data: null, error: { message: "down" }, status: 503 });
    const { container, unmount } = await mountIntake();
    await click(container.querySelector(".in-role"));
    await click(container.querySelector(".in-prov"));
    const cont = findButton(container, "Continue");
    assert.ok(cont.disabled, "Continue was usable with no intake to save into");
    await click(container.querySelectorAll(".in-rstep")[1]);
    assert.equal(api.__calls("intakeSaveStep").length, 0);
    assert.equal(currentStep(container), "About you", "the rail moved past step 1 without an intake");
    await unmount();
});

test("going forward on the rail saves what was edited, like Continue does", async () => {
    reset();
    seedToken();
    api.__respond("intakeGet", { data: onStep2() });
    const { container, unmount } = await mountIntake();
    await click(findButton(container, "Back"));
    const provs = [...container.querySelectorAll(".in-prov")];
    await click(provs[1]);
    await click(container.querySelectorAll(".in-rstep")[1]);
    const step1 = api.__calls("intakeSaveStep").filter(c => c.args[1] === 1);
    assert.equal(step1.length, 1, "the rail changed the screen without saving step 1");
    assert.notEqual(step1[0].args[2].province, "punjab", "the edited province was not saved");
    await unmount();
});

test("a failed question fetch is shown as an error with a retry, not as 'no questions needed'", async () => {
    reset();
    seedToken();
    api.__respond("intakeGet", { data: onStep2() });
    api.__respond("intakeClarify", { data: null, error: { message: "Network error." }, status: 0 });
    const { container, unmount } = await mountIntake();
    await click(container.querySelector("[data-step2-continue]"));
    assert.ok(container.querySelector("[data-clarify-error]"), "the failure was not shown");
    assert.doesNotMatch(container.textContent, /no additional questions needed/);
    assert.ok(findButton(container, "Complete & Continue").disabled, "analysis was offered past a failed fetch");
    api.__respond("intakeClarify", { data: { question: "When did it start?", done: false, round: 1 } });
    await click(container.querySelector("[data-clarify-retry]"));
    assert.equal(container.querySelector("[data-clarify-error]"), null);
    assert.match(container.textContent, /When did it start\?/);
    await unmount();
});

test("returning to the questions does not restart them", async () => {
    reset();
    seedToken();
    api.__respond("intakeGet", { data: onStep2() });
    api.__respond("intakeClarify", { data: { question: "When did it start?", done: false, round: 1 } });
    const { container, unmount } = await mountIntake();
    await click(container.querySelector("[data-step2-continue]"));
    await click(findButton(container, "Back"));
    await click(container.querySelector("[data-step2-continue]"));
    assert.equal(api.__calls("intakeClarify").length, 1, "the questions were fetched again from round 0");
    await unmount();
});

test("uploaded files stay visible after a refresh before conversion", async () => {
    reset();
    seedToken();
    const data = onStep2({ evidence_files: [{ file_id: "f1", filename: "fard.pdf", content_type: "application/pdf", size: 2048 }] });
    delete data.steps[4];
    api.__respond("intakeGet", { data });
    const { container, unmount } = await mountIntake();
    assert.match(container.textContent, /fard\.pdf/, "the uploaded file was hidden");
    const yes = [...container.querySelectorAll('[role="radio"]')].find(b => /Yes, I have evidence/.test(b.textContent));
    assert.equal(yes.getAttribute("aria-checked"), "true");
    await unmount();
});

test("the analysis language is only ever en or ur", async () => {
    for (const [story, want] of [["میرے بھائی نے پلاٹ پر قبضہ کر لیا ہے", "ur"], ["My brother took the plot.", "en"]]) {
        reset();
        seedToken();
        const data = answeredOnStep3();
        data.steps[3] = { incident_description: story };
        api.__respond("intakeGet", { data });
        const { container, unmount } = await mountIntake();
        await click(findButton(container, "Complete & Continue"));
        const conv = api.__calls("intakeConvert");
        assert.equal(conv.length, 1);
        assert.equal(conv[0].args[1].language, want);
        await unmount();
    }
});

test("a converted case's earlier steps cannot be reopened with Back", async () => {
    reset();
    seedToken();
    const { container, unmount } = await mountIntake();
    assert.equal(currentStep(container), "Review");
    assert.equal(findButton(container, "Back"), undefined, "Back led into a closed intake");
    await unmount();
});

test("a failed analysis says so, hides the placeholder, and can be retried", async () => {
    reset();
    seedToken();
    const failed = convertedIntake({ ai_structured_case: {
        summary: "AI structuring unavailable — case created successfully.", applicable_laws: [],
        recommended_actions: ["Consult a qualified Pakistani lawyer for advice."], risk_level: null,
        grounded: false, grounding_status: "pipeline_failed" } });
    api.__respond("intakeGet", { data: failed });
    const { container, unmount } = await mountIntake();
    assert.ok(container.querySelector("[data-analysis-failed]"), "the failure was not stated");
    assert.doesNotMatch(container.textContent, /AI structuring unavailable/, "the placeholder was shown as a summary");
    api.__respond("intakeRetryAnalysis", { data: { analysis_status: "done" } });
    api.__respond("intakeGet", { data: convertedIntake() });
    await click(container.querySelector("[data-retry-analysis]"));
    assert.equal(api.__calls("intakeRetryAnalysis").length, 1);
    assert.equal(container.querySelector("[data-analysis-failed]"), null);
    assert.match(container.textContent, /A tenancy arrears claim\./);
    await unmount();
});

test("a conversion the proxy gave up on is picked up when the server finishes", async () => {
    reset();
    seedToken();
    api.__respond("intakeGet", { data: answeredOnStep3() });
    let converts = 0;
    api.__respond("intakeConvert", async () => {
        converts += 1;
        return converts === 1
            ? { data: null, error: { message: "Gateway timeout" }, status: 504 }
            : { data: { case_id: CASE_ID, completed: true, ai_case_type: "civil" }, error: null, status: 200 };
    });
    const { container, unmount } = await mountIntake();
    api.__respond("intakeGet", { data: convertedIntake() });
    await click(findButton(container, "Complete & Continue"));
    await tick(5600);
    assert.equal(converts, 2, "the finished conversion was not replayed");
    assert.equal(currentStep(container), "Review");
    await unmount();
});

test("text fields carry the server's limits", async () => {
    reset();
    seedToken();
    api.__respond("intakeGet", { data: onStep2() });
    const { container, unmount } = await mountIntake();
    assert.equal(container.querySelector("#in-story-text").getAttribute("maxlength"), "20000");
    assert.equal(container.querySelector("#in-outcome").getAttribute("maxlength"), "5000");
    await unmount();
});

test("an AI outage at the questions is said plainly, not as 'no questions needed'", async () => {
    reset();
    seedToken();
    api.__respond("intakeGet", { data: onStep2() });
    api.__respond("intakeClarify", { data: { question: null, done: true, round: 0, ai_unavailable: true } });
    const { container, unmount } = await mountIntake();
    await click(container.querySelector("[data-step2-continue]"));
    assert.ok(container.querySelector("[data-clarify-unavailable]"), "the outage was not stated");
    assert.doesNotMatch(container.textContent, /no additional questions needed|No questions needed/);
    assert.equal(findButton(container, "Complete & Continue").disabled, false, "the client was trapped by the outage");
    api.__respond("intakeClarify", { data: { question: "Who holds the plot now?", done: false, round: 1 } });
    await click(container.querySelector("[data-clarify-unavailable-retry]"));
    assert.equal(container.querySelector("[data-clarify-unavailable]"), null);
    assert.match(container.textContent, /Who holds the plot now\?/);
    await unmount();
});

// ── a pending draft is a choice, not a trap (2026-10-12) ───────────────────

test("a pending draft is offered as a choice, not forced open on its review screen", async () => {
    reset();
    seedToken();
    const { container, unmount } = await mountIntake({ draftChoice: "leave" });
    const card = container.querySelector("[data-draft-choice]");
    assert.ok(card, "the draft was resumed without asking");
    assert.match(card.textContent, /My landlord seized my shop/);
    assert.equal(container.querySelector(".in-shell").style.display, "none");
    await click(container.querySelector("[data-continue-draft]"));
    assert.equal(container.querySelector("[data-draft-choice]"), null);
    assert.equal(container.querySelector(".in-rstep[aria-current] .t").textContent, "Review");
    await unmount();
});

test("starting a new matter leaves the draft alone and opens a fresh intake", async () => {
    reset();
    seedToken();
    api.__respond("intakeStart", { data: { session_token: "tok-new" } });
    const { container, unmount } = await mountIntake({ draftChoice: "leave" });
    await click(container.querySelector("[data-start-new]"));
    assert.equal(api.__calls("intakeStart").length, 1);
    assert.equal(storedToken(), "tok-new", "the new intake's token was not kept");
    assert.equal(container.querySelector(".in-rstep[aria-current] .t").textContent, "About you");
    assert.equal(api.__calls("confirmCase").length, 0, "the draft was touched");
    await unmount();
});

test("the server's resumable draft is offered the same way", async () => {
    reset();
    api.__respond("getResumableIntake", { data: convertedIntake() });
    const { container, unmount } = await mountIntake({ draftChoice: "leave" });
    assert.ok(container.querySelector("[data-draft-choice]"));
    assert.equal(api.__calls("intakeStart").length, 0, "a new intake was started without asking");
    await unmount();
});

test("voice input asks which language will be spoken, Urdu by default", async () => {
    reset();
    seedToken();
    api.__respond("intakeGet", { data: onStep2() });
    const { container, unmount } = await mountIntake();
    await click(findButton(container, "Voice Input"));
    const ur = container.querySelector('[data-speak-lang="ur"]');
    const en = container.querySelector('[data-speak-lang="en"]');
    assert.ok(ur && en, "no language choice before recording");
    assert.equal(ur.getAttribute("aria-checked"), "true");
    await click(en);
    assert.equal(en.getAttribute("aria-checked"), "true");
    await unmount();
});

// ── Urdu rendering of the analysis (2026-10-12) ────────────────────────────

function urduAnalysis(localized) {
    return convertedIntake({ ai_structured_case: {
        summary: "A cheque of Rs. 250,000 was dishonoured.",
        applicable_laws: ["Pakistan Penal Code Section 489-F — Dishonestly issuing a cheque"],
        law_citations: [{ statute: "Pakistan Penal Code", section: "489-F", description: "Dishonestly issuing a cheque", status: "bound" }],
        recommended_actions: ["Preserve the original cheque."],
        risk_level: "high", grounded: false, grounding_status: "ungrounded",
        output_language: "ur",
        localized: { ur: localized },
    } });
}

test("an Urdu analysis is shown in Urdu, right-to-left, with the English original one click away", async () => {
    reset();
    seedToken();
    api.__respond("intakeGet", { data: urduAnalysis({
        language: "ur", status: "ok", summary: "Rs. 250,000 کا چیک باؤنس ہو گیا۔",
        recommended_actions: ["اصل چیک محفوظ رکھیں۔"], citation_notes: ["بددیانتی سے چیک جاری کرنا"],
        cautions: ["partially_unverified"] }) });
    const { container, unmount } = await mountIntake();
    const summary = container.querySelector("[data-analysis-summary]");
    assert.match(summary.textContent, /چیک باؤنس/);
    assert.equal(summary.getAttribute("dir"), "rtl");
    assert.match(container.querySelector("[data-analysis-law]").textContent, /Pakistan Penal Code Section 489-Fوضاحت: بددیانتی/);
    assert.match(container.querySelector("[data-analysis-action]").textContent, /اصل چیک/);
    assert.match(container.querySelector("[data-grounding-note]").textContent, /پوری طرح نہیں مل سکے/, "the warning was not the fixed Urdu text");
    // One warning, not two: the fixed Urdu status note stands for the judge's caution.
    assert.equal(container.querySelectorAll(".in-callout").length, 1, "the same warning was shown twice");
    await click(container.querySelector('[data-view-lang="en"]'));
    assert.match(container.querySelector("[data-analysis-summary]").textContent, /A cheque of Rs\. 250,000 was dishonoured\./);
    await unmount();
});

test("a failed Urdu rendering shows the English original and says so", async () => {
    reset();
    seedToken();
    api.__respond("intakeGet", { data: urduAnalysis({ language: "ur", status: "failed" }) });
    const { container, unmount } = await mountIntake();
    assert.ok(container.querySelector("[data-urdu-unavailable]"));
    assert.match(container.querySelector("[data-analysis-summary]").textContent, /A cheque of Rs\. 250,000/);
    assert.equal(container.querySelector('[data-view-lang="ur"]'), null);
    await unmount();
});

test("a statute shows its fixed Urdu name beside the English one, and evidence notes are in Urdu", async () => {
    reset();
    seedToken();
    const data = urduAnalysis({
        language: "ur", status: "ok", summary: "خلاصہ", recommended_actions: ["قدم"],
        citation_notes: ["وضاحت"], statute_names: ["مجموعہ تعزیرات پاکستان"], cautions: [] });
    data.ai_structured_case.evidence_extraction = [{ file_id: "f1", status: "readable", completeness: "complete", pages_total: 1, pages_with_text: 1 }];
    api.__respond("intakeGet", { data });
    const { container, unmount } = await mountIntake();
    assert.match(container.querySelector("[data-analysis-law]").textContent,
        /^Pakistan Penal Code \(مجموعہ تعزیرات پاکستان\) Section 489-Fوضاحت: وضاحت/);
    assert.match(container.textContent, /فائلیں مکمل پڑھی گئیں/);
    await unmount();
});

// ── a story with no event is not "classified by the AI" (2026-10-12) ───────

test("a vague story is told what to add, and its category is called a starting guess", async () => {
    reset();
    seedToken();
    const vague = convertedIntake({ case_type: "civil" });
    vague.steps[3] = { incident_description: "Can you guide me in my legal matter? I need some information." };
    api.__respond("intakeGet", { data: vague });
    const { container, unmount } = await mountIntake();
    await click(findButton(container, "Continue to category"));
    assert.equal(container.querySelector("[data-category-basis]").getAttribute("data-category-basis"), "guess");
    assert.doesNotMatch(container.textContent, /The AI placed your case under/);
    assert.match(container.textContent, /Starting guess/);
    assert.ok(container.querySelector("[data-next-locked]"), "the locked next steps were not explained");
    await unmount();
});

test("a story with a real event keeps the AI's category wording", async () => {
    reset();
    seedToken();
    const real = convertedIntake({ case_type: "civil" });
    real.steps[3] = { incident_description: "My landlord locked my shop in Lahore last month and refuses to return my security deposit of two lakh rupees despite the rent agreement." };
    api.__respond("intakeGet", { data: real });
    const { container, unmount } = await mountIntake();
    await click(findButton(container, "Continue to category"));
    assert.equal(container.querySelector("[data-category-basis]").getAttribute("data-category-basis"), "ai");
    assert.match(container.textContent, /AI suggested/);
    await unmount();
});

test("a thin story gets a hint on the story step", async () => {
    reset();
    seedToken();
    const data = onStep2();
    data.steps[3] = { incident_description: "Can you help me?" };
    api.__respond("intakeGet", { data });
    const { container, unmount } = await mountIntake();
    assert.ok(container.querySelector("[data-story-thin]"));
    await unmount();
});

test("when the client picks a different category, the AI's suggestion is not presented as their choice", async () => {
    reset();
    seedToken();
    const real = convertedIntake({ case_type: "civil" });
    real.steps[3] = { incident_description: "My landlord locked my shop in Lahore last month and refuses to return my security deposit of two lakh rupees despite the rent agreement." };
    api.__respond("intakeGet", { data: real });
    const { container, unmount } = await mountIntake();
    await click(findButton(container, "Continue to category"));
    await click(container.querySelector('[data-category="family"]'));
    const sub = container.querySelector("[data-category-basis]").textContent;
    assert.match(sub, /The AI suggested Civil( Law)?; you chose Family/);
    assert.doesNotMatch(sub, /The AI placed your case under Family/);
    assert.ok(container.querySelector('[data-category="civil"] .tag'), "the AI tag moved off the AI's suggestion");
    await unmount();
});

test("a vague story's guess and the client's own pick are told apart", async () => {
    reset();
    seedToken();
    const vague = convertedIntake({ case_type: "civil" });
    vague.steps[3] = { incident_description: "cc" };
    api.__respond("intakeGet", { data: vague });
    const { container, unmount } = await mountIntake();
    await click(findButton(container, "Continue to category"));
    await click(container.querySelector('[data-category="family"]'));
    const sub = container.querySelector("[data-category-basis]");
    assert.equal(sub.getAttribute("data-category-basis"), "chosen");
    assert.match(sub.textContent, /Our starting guess was Civil( Law)?; you chose Family/);
    await unmount();
});

// ── review screen layout (2026-10-12) ──────────────────────────────────────

test("the review reads cleanly: caution apart from the summary, one 'Section', a Not-verified badge, a way out", async () => {
    reset();
    seedToken();
    api.__respond("intakeGet", { data: convertedIntake({ ai_structured_case: {
        summary: "The tenant may sue for recovery. Note: one or more statutes cited here could not be matched to the retrieved law sections and must not be relied on without checking.",
        law_citations: [{ statute: "Civil Procedure Code 1908", section: "Section 2", description: "Notice must be served.", status: "unbound" }],
        applicable_laws: ["Civil Procedure Code 1908 Section Section 2 — Notice must be served. [unverified citation]"],
        recommended_actions: ["Send a legal notice."], risk_level: "medium", grounding_status: "citations_unverified",
    } }) });
    const { container, unmount } = await mountIntake();
    const summary = container.querySelector("[data-analysis-summary]").textContent;
    assert.equal(summary, "The tenant may sue for recovery.", "the caution was left inside the summary");
    assert.equal(container.querySelectorAll(".in-callout").length, 1, "the same warning was shown twice");
    assert.match(container.querySelector("[data-grounding-note]").textContent, /could not be matched/);
    const law = container.querySelector("[data-analysis-law]").textContent;
    assert.doesNotMatch(law, /Section Section/);
    assert.doesNotMatch(law, /\[unverified citation\]/);
    assert.ok(container.querySelector("[data-unverified]"), "no Not-verified badge");
    assert.ok(container.querySelector("[data-save-later]"), "no way out once the case exists");
    assert.doesNotMatch(container.textContent, /📋|⚖️|🎯/, "emoji section icons are back");
    await click(container.querySelector("[data-export]"));
    assert.ok(container.querySelector('[role="menu"]'), "the Export menu did not open");
    assert.match(container.querySelector('[role="menu"]').textContent, /Download as PDF.*Email the summary.*Print/s);
    await unmount();
});

test("no language chooser on the story step; the language follows the story and is saved with it", async () => {
    for (const [story, want] of [["My landlord locked my shop and kept my deposit.", "en"], ["میرے مالک مکان نے دکان بند کر دی اور میری رقم رکھ لی", "ur"]]) {
        reset();
        seedToken();
        const data = onStep2();
        data.steps[3] = { incident_description: story };
        api.__respond("intakeGet", { data });
        api.__respond("intakeClarify", { data: { question: "When?", done: false, round: 1 } });
        const { container, unmount } = await mountIntake();
        assert.equal(container.querySelector("[data-answer-lang]"), null, "the confusing chooser is back");
        await click(container.querySelector("[data-step2-continue]"));
        const step2 = api.__calls("intakeSaveStep").filter(c => c.args[1] === 2);
        assert.equal(step2.at(-1).args[2].output_language, want);
        await unmount();
    }
});

test("a language saved with the story survives a refresh", async () => {
    reset();
    seedToken();
    const data = answeredOnStep3();
    data.steps[2] = { case_type: "civil", urgency: "medium", output_language: "ur" };
    api.__respond("intakeGet", { data });
    const { container, unmount } = await mountIntake();
    await click(findButton(container, "Complete & Continue"));
    assert.equal(api.__calls("intakeConvert")[0].args[1].language, "ur");
    await unmount();
});

test("a story with no event in it cannot move on", async () => {
    reset();
    seedToken();
    const data = onStep2();
    data.steps[3] = { incident_description: "no" };
    api.__respond("intakeGet", { data });
    const { container, unmount } = await mountIntake();
    assert.ok(container.querySelector("[data-step2-continue]").disabled, "Continue allowed on 'no'");
    assert.match(container.querySelector("[data-step2-why]").textContent, /Describe what happened/);
    await unmount();
});

// ── evidence-gated analysis (2026-10-12) ───────────────────────────────────

function gated(over) {
    return convertedIntake({ ai_structured_case: {
        summary: "The client says their landlord kept their deposit.",
        law_citations: [], applicable_laws: [],
        recommended_actions: ["Write down what happened and when.", "Consult a lawyer about the deposit."],
        recommended_action_kinds: ["general", "general"],
        risk_level: null, grounded: false, ...over,
    } });
}

test("a retrieval failure offers Retry, in its own words", async () => {
    reset();
    seedToken();
    api.__respond("intakeGet", { data: gated({ grounding_status: "retrieval_error" }) });
    const { container, unmount } = await mountIntake();
    const banner = container.querySelector('[data-analysis-failed="retrieval_error"]');
    assert.ok(banner, "no retry banner for a retrieval failure");
    assert.match(banner.textContent, /could not search the law library/);
    assert.ok(container.querySelector("[data-retry-analysis]"));
    await unmount();
});

test("no admissible law: a facts-only summary, its fixed note, no laws, general steps labelled", async () => {
    reset();
    seedToken();
    api.__respond("intakeGet", { data: gated({ grounding_status: "no_relevant_evidence" }) });
    const { container, unmount } = await mountIntake();
    assert.equal(container.querySelector("[data-analysis-failed]"), null, "not a failure — no retry banner");
    assert.match(container.querySelector("[data-grounding-note]").textContent, /only restates what you told us/);
    assert.equal(container.querySelector("[data-analysis-law]"), null, "law shown although none was admissible");
    assert.equal(container.querySelectorAll("[data-general-step]").length, 2);
    await unmount();
});

test("a fidelity issue is shown beside the summary", async () => {
    reset();
    seedToken();
    api.__respond("intakeGet", { data: gated({ grounding_status: "grounded",
        input_fact_fidelity: { status: "issues", issues: [{ type: "unsupported_number", value: "250000" }] } }) });
    const { container, unmount } = await mountIntake();
    assert.ok(container.querySelector("[data-fidelity-issue]"));
    await unmount();
});

/* The Punjab-only CPC (server, batch 6): a Sindh analysis says why the CPC is not listed. */
test("a non-Punjab analysis shows the CPC jurisdiction notice and lists no CPC law", async () => {
    reset();
    const intake = convertedIntake({
        steps: {
            1: { province: "sindh", party_role: "plaintiff" },
            2: { case_type: "civil", urgency: "medium" },
            3: { incident_description: "My landlord seized my shop." },
        },
    });
    intake.ai_structured_case = {
        ...intake.ai_structured_case,
        summary: "The tenant paid Rs. 50,000 on 3 March. The plaint can be rejected because it discloses no cause of action.",
        applicable_laws: ["Specific Relief Act 1877 Section 42"],
        law_citations: [{ statute: "Specific Relief Act 1877", section: "42", status: "bound" }],
        jurisdiction_notice: {
            scope: "other", province: "sindh",
            en: "Note on the Code of Civil Procedure: our law library holds only the Punjab version of the CPC, so CPC provisions are not shown here as the law that applies in Sindh.",
            ur: "ضابطہ دیوانی کے بارے میں نوٹ: صرف پنجاب کا متن",
        },
    };
    api.__respond("intakeGet", { data: intake });
    seedToken();
    const { container, unmount } = await mountIntake();
    const notice = container.querySelector("[data-jurisdiction-notice]");
    assert.ok(notice, "the jurisdiction notice is not shown");
    assert.equal(notice.getAttribute("data-jurisdiction-notice"), "other");
    assert.match(notice.textContent, /Punjab version of the CPC/);
    assert.match(container.textContent, /Specific Relief Act/);
    assert.doesNotMatch(container.textContent, /Order VII Rule 11|Code of Civil Procedure, 1908/);
    await unmount();
});

test("a Punjab analysis carries no jurisdiction notice", async () => {
    reset();
    api.__respond("intakeGet", { data: convertedIntake() });
    seedToken();
    const { container, unmount } = await mountIntake();
    assert.equal(container.querySelector("[data-jurisdiction-notice]"), null);
    await unmount();
});

/* Batch 7: a risk estimate made with the Punjab-only CPC in view is withheld by the server. */
test("a withheld risk estimate reads 'Not assessed — needs review', never as a rating", async () => {
    reset();
    const intake = convertedIntake({ steps: { 1: { province: "sindh", party_role: "plaintiff" },
                                             2: { case_type: "civil", urgency: "medium" },
                                             3: { incident_description: "My landlord seized my shop." } } });
    intake.ai_structured_case = { ...intake.ai_structured_case, risk_level: null,
                                  risk_level_basis: "not_assessed_cpc_jurisdiction", risk_level_withheld: "high" };
    api.__respond("intakeGet", { data: intake });
    seedToken();
    const { container, unmount } = await mountIntake();
    const tile = container.querySelector("[data-risk-not-assessed]");
    assert.ok(tile, "the withheld estimate is not explained");
    assert.match(tile.textContent, /Not assessed — needs review/);
    assert.equal(container.querySelector("[data-r]"), null, "a rating badge is still shown");
    assert.doesNotMatch(container.textContent, /\bHigh\b/);
    await unmount();
});

test("an ordinary risk estimate is still shown as before", async () => {
    reset();
    api.__respond("intakeGet", { data: convertedIntake() });
    seedToken();
    const { container, unmount } = await mountIntake();
    assert.equal(container.querySelector("[data-r]")?.getAttribute("data-r"), "medium");
    assert.equal(container.querySelector("[data-risk-not-assessed]"), null);
    await unmount();
});

// ── an unfinished intake is OFFERED, not jumped into (2026-10-21) ──────────
//
// Opening Legal Intake used to land on step 2 or 3 of an old, half-done
// matter with no word about it. It is now offered like a draft case.

function unfinishedOnStep3() {
    return convertedIntake({
        completed: false, case_id: null, case_status: null, current_step: 3, ai_structured_case: null,
    });
}

test("an unfinished intake past step 1 is offered, not opened silently", async () => {
    reset();
    api.__respond("intakeGet", { data: unfinishedOnStep3() });
    seedToken();
    const { container, unmount } = await mountIntake({ draftChoice: "leave" });

    assert.ok(container.querySelector("[data-unfinished-choice]"), "no choice was offered");
    assert.ok((container.textContent || "").includes("You stopped at step 3"));
    assert.ok(findButton(container, "Continue where you left off"));
    assert.ok((container.textContent || "").includes("My landlord seized my shop"), "the matter is not named");
    await unmount();
});

test("continuing an unfinished intake puts the client back where they were", async () => {
    reset();
    api.__respond("intakeGet", { data: unfinishedOnStep3() });
    seedToken();
    const { container, unmount } = await mountIntake();          // presses Continue
    assert.equal(!!container.querySelector("[data-unfinished-choice]"), false);
    assert.equal(!!findButton(container, "I'm taking action"), false, "continuing dropped them on step 1");
    await unmount();
});

test("starting a new matter from the offer opens a fresh intake on step 1", async () => {
    reset();
    api.__respond("intakeGet", { data: unfinishedOnStep3() });
    api.__respond("intakeStart", { data: { session_token: "tok-new" } });
    seedToken();
    const { container, unmount } = await mountIntake({ draftChoice: "leave" });
    await click(container.querySelector("[data-start-new]"));
    assert.equal(api.__calls("intakeStart").length, 1);
    assert.ok(findButton(container, "I'm taking action"), "the new matter did not open on step 1");
    await unmount();
});

test("an intake still on step 1 opens directly (nothing to skip past)", async () => {
    reset();
    api.__respond("intakeGet", { data: convertedIntake({
        completed: false, case_id: null, case_status: null, current_step: 1, ai_structured_case: null }) });
    seedToken();
    const { container, unmount } = await mountIntake({ draftChoice: "leave" });
    assert.equal(!!container.querySelector("[data-draft-choice]"), false);
    assert.ok(findButton(container, "I'm taking action"));
    await unmount();
});

test("the server-found unfinished intake is offered too", async () => {
    reset();
    api.__respond("getResumableIntake", { data: unfinishedOnStep3() });
    const { container, unmount } = await mountIntake({ draftChoice: "leave" });
    assert.ok(container.querySelector("[data-unfinished-choice]"));
    assert.equal(api.__calls("intakeStart").length, 0, "a new intake was started over the unfinished one");
    await unmount();
});

test("'New matter' starts a fresh intake without offering the old one", async () => {
    reset();
    api.__respond("intakeGet", { data: unfinishedOnStep3() });
    api.__respond("intakeStart", { data: { session_token: "tok-new" } });
    seedToken();
    const { requestNewMatter } = await import("../src/components/client/newMatter.js");
    requestNewMatter();
    const { container, unmount } = await mountIntake({ draftChoice: "leave" });
    assert.equal(!!container.querySelector("[data-draft-choice]"), false, "New matter offered the old intake");
    assert.equal(api.__calls("intakeStart").length, 1);
    assert.ok(findButton(container, "I'm taking action"));
    assert.equal(dom.window.sessionStorage.getItem("attorney:intake-new"), null, "the request was not consumed");
    await unmount();
});
