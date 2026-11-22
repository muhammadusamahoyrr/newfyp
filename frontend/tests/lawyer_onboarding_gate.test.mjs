/* The onboarding gate fails OPEN (audit 2026-11-22, low #5).
 *
 * With no cached answer (a new browser, cleared site data) the wizard is shown
 * optimistically while /users/me is read. If that read failed, the code only
 * returned, so a registered lawyer was left on the wizard. Now the wizard stays
 * only when the cache says "not onboarded" or the server says so.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/lawyer" });
function define(name, value) {
    Object.defineProperty(globalThis, name, { value, writable: true, configurable: true });
}
for (const name of ["window", "document", "navigator", "HTMLElement", "HTMLInputElement", "Element",
                    "Node", "Event", "CustomEvent", "MouseEvent", "KeyboardEvent", "MutationObserver",
                    "getComputedStyle", "localStorage", "sessionStorage", "requestAnimationFrame",
                    "cancelAnimationFrame", "matchMedia", "ResizeObserver", "IntersectionObserver"]) {
    if (dom.window[name] !== undefined) define(name, dom.window[name]);
}
if (!dom.window.matchMedia) define("matchMedia", () => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }));
if (!dom.window.HTMLElement.prototype.scrollIntoView) dom.window.HTMLElement.prototype.scrollIntoView = () => {};
define("IS_REACT_ACT_ENVIRONMENT", true);

const React = (await import("react")).default;
const { act } = await import("react");
const { createRoot } = await import("react-dom/client");
const api = await import("./support/api-stub.mjs");
const { AuthProvider } = await import("../src/context/AuthContext.jsx");
const { ONBOARDED_KEY } = await import("../src/components/lawyer/OnboardingPage.jsx");
const App = (await import("../src/components/lawyer/App.jsx")).default;
const h = React.createElement;
const settle = (ms = 60) => act(async () => { await new Promise(r => setTimeout(r, ms)); });

async function mountApp() {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => { root.render(h(AuthProvider, null, h(App, { initialPage: "dashboard" }))); });
    await settle(250);
    return { container, unmount: async () => { await act(async () => root.unmount()); container.remove(); } };
}
const wizardShown = (c) => !!c.querySelector(".ob-brand");

function serve(me) {
    api.__reset();
    api.__respond("bootstrapAuth", true);
    api.__respond("getMe", me);
}

test("no cache and a failed profile read: the lawyer is NOT left on the wizard", async () => {
    localStorage.removeItem(ONBOARDED_KEY);
    serve({ data: null, error: { message: "Network error" }, status: 0 });
    const ui = await mountApp();
    assert.equal(wizardShown(ui.container), false, "a registered lawyer was stuck on the onboarding wizard");
    await ui.unmount();
});

test("a cached 'not onboarded' keeps the wizard when the read fails", async () => {
    localStorage.setItem(ONBOARDED_KEY, "0");
    serve({ data: null, error: { message: "Network error" }, status: 0 });
    const ui = await mountApp();
    assert.equal(wizardShown(ui.container), true);
    await ui.unmount();
});

test("the server saying 'not onboarded' shows the wizard", async () => {
    localStorage.removeItem(ONBOARDED_KEY);
    serve({ data: { _id: "l1", role: "lawyer", full_name: "New Lawyer", lawyer_profile: {} }, error: null });
    const ui = await mountApp();
    assert.equal(wizardShown(ui.container), true);
    await ui.unmount();
});
