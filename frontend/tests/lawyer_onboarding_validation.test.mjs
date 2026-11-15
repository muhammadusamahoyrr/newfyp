/* LD-04: lawyer onboarding, mounted for real.
 *
 * WHAT WAS WRONG.
 *   * The submit error path rendered `err.detail`. On a 422 that is the raw
 *     Pydantic array of objects, and React throws on objects as children.
 *   * Step 1 let "Continue" through with no bar number and no specialization.
 *     The server drops nulls, the save "succeeds", and isLawyerOnboarded then
 *     rejects the profile: the lawyer is sent back into onboarding.
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
                    "getComputedStyle", "localStorage", "sessionStorage"]) {
    define(name, dom.window[name]);
}
define("IS_REACT_ACT_ENVIRONMENT", true);

const React = (await import("react")).default;
const { act } = await import("react");
const { createRoot } = await import("react-dom/client");
const api = await import("./support/api-stub.mjs");
const { OnboardingPage, stepOneProblem } = await import("../src/components/lawyer/OnboardingPage.jsx");
const h = React.createElement;

const settle = (ms = 30) => act(async () => { await new Promise(r => setTimeout(r, ms)); });

async function mount() {
    const errors = [];
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container, {
        onUncaughtError: e => errors.push(e),
        onCaughtError: e => errors.push(e),
    });
    await act(async () => { root.render(h(OnboardingPage, { onComplete: () => {} })); });
    await settle();
    return { container, errors,
             unmount: async () => { await act(async () => root.unmount()); container.remove(); } };
}

const buttonWith = (root, text) => [...root.querySelectorAll("button")]
    .find(b => b.textContent.includes(text));
const byText = (root, text) => [...root.querySelectorAll("span, div")]
    .find(el => el.children.length === 0 && el.textContent.trim() === text);

async function click(el) {
    assert.ok(el, "element to click was not found");
    await act(async () => { el.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    await settle();
}

async function type(input, value) {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
    await act(async () => {
        setter.call(input, value);
        input.dispatchEvent(new Event("input", { bubbles: true }));
    });
}

const licenseInput = (root) => root.querySelector('input[placeholder="e.g. PBC/12345/2019"]');

test.beforeEach(() => {
    api.__reset();
    api.__respond("getMe", { data: { _id: "l1", role: "lawyer" }, error: null });
});

test("the Step 1 rule matches the server's bar-number shape and needs a specialization", () => {
    assert.match(stepOneProblem({ license: "", specs: ["civil"] }), /bar license/);
    assert.match(stepOneProblem({ license: "ab", specs: ["civil"] }), /bar license/);
    assert.match(stepOneProblem({ license: "x!yz", specs: ["civil"] }), /bar license/);
    assert.match(stepOneProblem({ license: "PBC/12345/2019", specs: [] }), /specialization/);
    assert.equal(stepOneProblem({ license: " PBC/12345/2019 ", specs: ["civil"] }), null);
});

test("Continue on an empty Step 1 is blocked with a visible reason", async () => {
    const view = await mount();
    await click(buttonWith(view.container, "Continue"));
    assert.ok(view.container.querySelector('[role="alert"]'), "no validation message was shown");
    assert.ok(licenseInput(view.container), "the wizard left Step 1 with no bar number");
    await view.unmount();
});

test("a 422 with an array detail shows a readable message and does not crash", async () => {
    const detail = [{ loc: ["body", "bar_number"], msg: "String should match pattern", type: "string_pattern_mismatch" }];
    api.__respond("updateMe", { data: {}, error: null, status: 200 });
    api.__respond("updateLawyerProfile", {
        data: null, status: 422,
        error: { detail, message: "Bar_number: String should match pattern" },
    });

    const view = await mount();
    await type(licenseInput(view.container), "PBC/12345/2019");
    await click(byText(view.container, "Civil Litigation"));
    await click(buttonWith(view.container, "Continue"));       // Step 1 -> 2
    await click(buttonWith(view.container, "Continue"));       // Step 2 -> 3
    await click(buttonWith(view.container, "Finish profile"));

    assert.equal(api.__calls("updateLawyerProfile").length, 1, "the profile was never submitted");
    assert.deepEqual(view.errors, [], `onboarding crashed: ${view.errors[0]}`);
    assert.match(view.container.textContent, /Bar_number: String should match pattern/);
    await view.unmount();
});

/* LAWYER_AUTO_APPROVE (2026-10-18). Nobody checks the Bar license, so the
 * final screen reports what the server saved and never says "verified". */
async function finishOnboarding(kycVerified) {
    api.__respond("updateMe", { data: {}, error: null, status: 200 });
    api.__respond("updateLawyerProfile", {
        data: { _id: "l1", lawyer_profile: { kyc_verified: kycVerified } }, error: null, status: 200,
    });
    const view = await mount();
    await type(licenseInput(view.container), "PBC/12345/2019");
    await click(byText(view.container, "Civil Litigation"));
    await click(buttonWith(view.container, "Continue"));
    await click(buttonWith(view.container, "Continue"));
    await click(buttonWith(view.container, "Finish profile"));
    return view;
}

test("an approved account is told it is live, and nothing claims verification", async () => {
    const view = await finishOnboarding(true);
    const text = view.container.textContent;
    assert.match(text, /Your profile is live/);
    assert.match(text, /Registered lawyer/);
    assert.doesNotMatch(text, /verif|in review/i);
    await view.unmount();
});

test("an account still waiting for an admin is not told it is live", async () => {
    const view = await finishOnboarding(false);
    const text = view.container.textContent;
    assert.match(text, /Profile saved/);
    assert.match(text, /Admin approval/);
    assert.doesNotMatch(text, /profile is live|Registered lawyer|verif/i);
    await view.unmount();
});
