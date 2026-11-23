/* The refined client theme and the Light / System / Dark choice (2026-10-16).
 *
 * The refinement is one switch in clientTheme.js (CLIENT_THEME_REFINED): when
 * on, Light and Dark carry [data-refined] and the refined tokens; "System" is
 * the app's own original theme, untouched; a saved choice from before keeps
 * working.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><head></head><body></body></html>", { url: "http://localhost/dashboard" });
function define(name, value) {
    Object.defineProperty(globalThis, name, { value, writable: true, configurable: true });
}
for (const name of ["window", "document", "navigator", "HTMLElement", "HTMLInputElement", "Element",
                    "Node", "Event", "CustomEvent", "MouseEvent", "KeyboardEvent", "MutationObserver",
                    "getComputedStyle", "localStorage", "sessionStorage", "FileReader",
                    "requestAnimationFrame", "cancelAnimationFrame"]) {
    if (dom.window[name] !== undefined) define(name, dom.window[name]);
}
dom.window.matchMedia = (q) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {},
                                   addListener() {}, removeListener() {} });
define("matchMedia", dom.window.matchMedia);
if (!globalThis.ResizeObserver) define("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
if (!globalThis.IntersectionObserver) define("IntersectionObserver", class { observe() {} unobserve() {} disconnect() {} });
if (!dom.window.HTMLElement.prototype.scrollIntoView) dom.window.HTMLElement.prototype.scrollIntoView = () => {};
define("IS_REACT_ACT_ENVIRONMENT", true);

const React = (await import("react")).default;
const { act } = await import("react");
const { createRoot } = await import("react-dom/client");
const api = await import("./support/api-stub.mjs");
const { AuthProvider } = await import("../src/context/AuthContext.jsx");
const { DARK, LIGHT } = await import("../src/components/admin/themes.js");
const theme = await import("../src/components/client/clientTheme.js");
const { default: ClientApp } = await import("../src/components/client/ClientApp.jsx");
const h = React.createElement;
const settle = (ms = 60) => act(async () => { await new Promise(r => setTimeout(r, ms)); });
const click = (el) => act(async () => { el.dispatchEvent(new MouseEvent("click", { bubbles: true })); });

test("the refinement is on, scoped, and readable", () => {
    assert.equal(theme.CLIENT_THEME_REFINED, true);
    // Dark = the approved chat preview's colours (2026-11-23); System is untouched.
    assert.match(theme.CLIENT_REFINED_CSS, /\[data-client-theme\]\[data-refined\]:not\(\[data-mode="light"\]\)\{--bg:#0E2024;--bg-a:#0E2024F5;--surface:#16343A;--input:#17353B/);
    assert.match(theme.CLIENT_REFINED_CSS, /\[data-client-theme\]\[data-refined\]\[data-mode="light"\]\{--bg:#EEF3F1/);
    // the old palette is still there, untouched, for the off-switch
    assert.match(theme.CLIENT_TOKENS_CSS, /--bg:#403E42/);
    assert.equal(theme.clientThemeOnTokens(LIGHT).primary, "#0E7A55");
    assert.equal(theme.clientThemeOnTokens(DARK).primary, "#3EE0A1");
    // a label on a primary fill uses the theme's own colour, never white on mint
    assert.equal(theme.onPrimaryInk(theme.clientThemeOnTokens(DARK)), "var(--on-brand)");
    assert.equal(theme.onPrimaryInk({}), "#fff");
});

test("Light, System (the app's original theme) and Dark: chosen in the account menu, each a different look", async () => {
    api.__reset();
    api.__respond("bootstrapAuth", true);
    api.__respond("getMe", { data: { _id: "c1", role: "client", full_name: "Ayesha Khan", email: "a@x.pk" }, error: null });
    localStorage.removeItem("aai-client-theme-pref");
    localStorage.setItem("aai-theme", "light");          // a choice saved before this change

    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => { root.render(h(AuthProvider, null, h(ClientApp, { initialTab: "profile" }))); });
    await settle(250);

    const body = document.body;
    assert.equal(body.getAttribute("data-mode"), "light", "the old saved choice was not kept");
    assert.ok(body.hasAttribute("data-refined"), "Light is not the refined theme");

    const me = container.querySelector("[data-client-account] .cs-me");
    assert.ok(me, "the account button did not render");
    await click(me);
    const pick = (v) => container.querySelector(`[data-theme-pref="${v}"]`);
    const note = () => container.querySelector("[data-theme-note]").textContent;
    const pos = () => container.querySelector(".cs-theme-seg").getAttribute("data-pos");
    assert.ok(pick("light") && pick("system") && pick("dark"), "the three choices are not offered");
    assert.equal(pick("light").getAttribute("aria-checked"), "true");
    assert.equal(note(), "Light theme");

    // System = the app's own original theme: dark, WITHOUT the refinements
    await click(pick("system"));
    assert.equal(body.getAttribute("data-mode"), "dark");
    assert.ok(!body.hasAttribute("data-refined"), "System must be the original theme");
    assert.ok(!container.querySelector("[data-client-theme][data-refined]"));
    assert.equal(localStorage.getItem("aai-client-theme-pref"), "system");
    assert.equal(note(), "The app’s original theme");
    assert.equal(pos(), "1");
    assert.ok(body.classList.contains("aai-theme-anim"), "the switch had no visible transition");

    // Dark = the refined dark: a different look from System
    await click(pick("dark"));
    assert.equal(body.getAttribute("data-mode"), "dark");
    assert.ok(body.hasAttribute("data-refined"), "Dark is not the refined theme");
    assert.equal(localStorage.getItem("aai-client-theme-pref"), "dark");
    assert.equal(pick("dark").getAttribute("aria-checked"), "true");
    assert.equal(note(), "New dark theme, easier to read");
    assert.equal(pos(), "2");

    await act(async () => root.unmount());
    container.remove();
    assert.ok(!body.hasAttribute("data-refined"), "the attribute outlived the dashboard");
    localStorage.removeItem("aai-theme");
    localStorage.removeItem("aai-client-theme-pref");
});

test("with nothing saved, the app opens in its original theme, as before", async () => {
    api.__reset();
    api.__respond("bootstrapAuth", true);
    api.__respond("getMe", { data: { _id: "c1", role: "client", full_name: "Ayesha Khan", email: "a@x.pk" }, error: null });
    localStorage.removeItem("aai-client-theme-pref");
    localStorage.removeItem("aai-theme");
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => { root.render(h(AuthProvider, null, h(ClientApp, { initialTab: "profile" }))); });
    await settle(250);
    assert.equal(document.body.getAttribute("data-mode"), "dark");
    assert.ok(!document.body.hasAttribute("data-refined"));
    await act(async () => root.unmount());
    container.remove();
    localStorage.removeItem("aai-theme");
    localStorage.removeItem("aai-client-theme-pref");
});
