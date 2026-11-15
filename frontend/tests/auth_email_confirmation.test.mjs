/* Sign-up consent and email confirmation, mounted for real (2026-10-18).
 *
 * The pages use the REAL api.js against a mocked fetch, so these pin the wire
 * contract too: `accepted_terms` is sent, a "verify_email" registration does
 * not try to sign in, a 403 `email_not_verified` login offers a new link, and
 * the emailed #token is confirmed once. ResendForm lives in src/components, so
 * the loader gives it the api STUB: its requests are read from api.__calls. */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/register" });
function define(name, value) {
    Object.defineProperty(globalThis, name, { value, writable: true, configurable: true });
}
for (const name of ["window", "document", "navigator", "HTMLElement", "HTMLInputElement", "Element",
                    "Node", "Event", "CustomEvent", "MouseEvent", "KeyboardEvent", "MutationObserver",
                    "getComputedStyle", "localStorage", "sessionStorage", "location", "history"]) {
    define(name, dom.window[name]);
}
define("IS_REACT_ACT_ENVIRONMENT", true);
globalThis.BroadcastChannel = class { constructor() { this.onmessage = null; } postMessage() {} close() {} };
window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });

// path -> [status, body]; every request is recorded.
const calls = [];
let replies = {};
globalThis.fetch = async (url, options = {}) => {
    const path = new URL(String(url), "http://localhost").pathname.replace(/^\/api\/v1/, "");
    calls.push({ path, body: options.body ? JSON.parse(options.body) : null });
    const [status, body] = replies[path] || [404, { error: "not stubbed" }];
    return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
};

const React = (await import("react")).default;
const { act } = await import("react");
const { createRoot } = await import("react-dom/client");
const api = await import("./support/api-stub.mjs");
const { AuthProvider } = await import("../src/context/AuthContext.jsx");
const RegisterPage = (await import("../src/app/(auth)/register/page.jsx")).default;
const LoginPage = (await import("../src/app/(auth)/login/page.jsx")).default;
const VerifyEmailPage = (await import("../src/app/(auth)/verify-email/page.jsx")).default;
const h = React.createElement;

const settle = (ms = 30) => act(async () => { await new Promise(r => setTimeout(r, ms)); });

async function mount(Page) {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => { root.render(h(AuthProvider, null, h(Page))); });
    await settle();
    return { container, text: () => container.textContent,
             unmount: async () => { await act(async () => root.unmount()); container.remove(); } };
}

async function type(root, label, value) {
    const input = root.querySelector(`input[aria-label="${label}"]`);
    assert.ok(input, `no input labelled ${label}`);
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
    await act(async () => { setter.call(input, value); input.dispatchEvent(new Event("input", { bubbles: true })); });
}
async function click(el) {
    assert.ok(el, "nothing to click");
    await act(async () => { el.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    await settle();
}
const button = (root, text) => [...root.querySelectorAll("button")].find(b => b.textContent.includes(text));

async function fillSignUp(view) {
    await type(view.container, "Full name", "Ayesha Khan");
    await type(view.container, "Email", "ayesha@example.com");
    await type(view.container, "Password", "Str0ngPass");
}

test.beforeEach(() => { calls.length = 0; replies = {}; api.__reset(); });

test("sign-up without ticking the box sends nothing", async () => {
    const view = await mount(RegisterPage);
    await fillSignUp(view);
    await click(button(view.container, "Create account"));
    assert.match(view.text(), /Please accept the Terms and Privacy Policy/);
    assert.equal(calls.filter(c => c.path === "/auth/register").length, 0);
    await view.unmount();
});

test("the checkbox links to the real Terms and Privacy pages", async () => {
    const view = await mount(RegisterPage);
    const hrefs = [...view.container.querySelectorAll(".aa-check a")].map(a => a.getAttribute("href"));
    assert.deepEqual(hrefs, ["/terms", "/privacy"]);
    await view.unmount();
});

test("a sign-up that needs confirming sends consent and does not sign in", async () => {
    replies["/auth/register"] = [200, { success: true, message: "verify_email" }];
    const view = await mount(RegisterPage);
    await fillSignUp(view);
    await click(view.container.querySelector(".aa-check input"));
    await click(button(view.container, "Create account"));

    const reg = calls.find(c => c.path === "/auth/register");
    assert.equal(reg.body.accepted_terms, true);
    assert.equal(calls.filter(c => c.path === "/auth/login").length, 0, "it tried to sign in before confirming");
    assert.match(view.text(), /Check your inbox/);
    assert.match(view.text(), /ayesha@example\.com/);

    api.__respond("authResendVerification", { data: { success: true }, error: null, status: 200 });
    await click(button(view.container, "Send a new link"));
    await click(button(view.container, "Send a new link"));      // the form's own submit
    assert.deepEqual(api.__calls("authResendVerification").map(c => c.args[0]), ["ayesha@example.com"]);
    assert.match(view.text(), /a new link is on its way/);
    await view.unmount();
});

test("an unconfirmed sign-in offers a new link instead of an error", async () => {
    replies["/auth/login"] = [403, { error: { code: "email_not_verified",
        message: "Please confirm your email first. We sent a link to your inbox." }, status_code: 403 }];
    api.__respond("authResendVerification", { data: { success: true }, error: null, status: 200 });
    const view = await mount(LoginPage);
    await type(view.container, "Email", "ayesha@example.com");
    await type(view.container, "Password", "Str0ngPass");
    await click(button(view.container, "Sign in"));

    assert.match(view.text(), /Please confirm your email first/);
    await click(button(view.container, "Send a new link"));
    assert.deepEqual(api.__calls("authResendVerification").map(c => c.args[0]), ["ayesha@example.com"]);
    assert.match(view.text(), /a new link is on its way/);
    await view.unmount();
});

test("the emailed link confirms once and leaves the address bar clean", async () => {
    replies["/auth/verify-email"] = [200, { success: true, message: "Email confirmed" }];
    window.history.replaceState(null, "", "/verify-email#token=abc123");
    const view = await mount(VerifyEmailPage);
    await settle();
    const sent = calls.filter(c => c.path === "/auth/verify-email");
    assert.equal(sent.length, 1);
    assert.equal(sent[0].body.token, "abc123");
    assert.equal(window.location.hash, "", "the token stayed in the address bar");
    assert.match(view.text(), /Email confirmed/);
    await view.unmount();
});

test("a used or expired link asks for a new one", async () => {
    replies["/auth/verify-email"] = [422, { error: "This confirmation link is invalid or has expired.", status_code: 422 }];
    window.history.replaceState(null, "", "/verify-email#token=used");
    const view = await mount(VerifyEmailPage);
    await settle();
    assert.match(view.text(), /This link has expired/);
    assert.ok(button(view.container, "Send a new link"));
    await view.unmount();
});

test("the pages' versions match what the server records", () => {
    const backend = readFileSync(new URL("../../backend/app/core/constants.py", import.meta.url), "utf8");
    const front = readFileSync(new URL("../src/components/shared/LegalDocument.jsx", import.meta.url), "utf8");
    for (const name of ["TERMS_VERSION", "PRIVACY_VERSION"]) {
        const be = backend.match(new RegExp(`${name} = "([^"]+)"`))[1];
        const fe = front.match(new RegExp(`${name} = '([^']+)'`))[1];
        assert.equal(fe, be, `${name} differs between the page and the server`);
    }
});
