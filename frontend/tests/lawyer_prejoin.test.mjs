/* The lawyer's join screen for in-app video (2026-10-20).
 *
 * The camera is never switched on by itself; the check starts only when the
 * lawyer asks, its controls really pause the tracks, and joining (or closing)
 * stops the preview so the call can have the camera. */
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/" });
function define(name, value) {
    Object.defineProperty(globalThis, name, { value, writable: true, configurable: true });
}
for (const name of ["window", "document", "HTMLElement", "Element", "Node", "Event", "CustomEvent", "MouseEvent",
                    "KeyboardEvent", "MutationObserver", "getComputedStyle", "localStorage", "sessionStorage"]) {
    define(name, dom.window[name]);
}
define("IS_REACT_ACT_ENVIRONMENT", true);
define("requestAnimationFrame", () => 0);
define("cancelAnimationFrame", () => {});

// A fake camera: records what was asked for and what was stopped.
const media = { asked: 0, stopped: 0, tracks: [] };
function track(kind) {
    const t = { kind, enabled: true, stop() { media.stopped += 1; } };
    media.tracks.push(t);
    return t;
}
define("navigator", {
    userAgent: "node",
    clipboard: { writeText: async (txt) => { media.copied = txt; } },
    mediaDevices: {
        getUserMedia: async () => {
            media.asked += 1;
            const v = track("video"), a = track("audio");
            return { getTracks: () => [v, a], getVideoTracks: () => [v], getAudioTracks: () => [a] };
        },
    },
});

const React = (await import("react")).default;
const { act } = await import("react");
const { createRoot } = await import("react-dom/client");
const api = await import("./support/api-stub.mjs");
const { PreJoinModal } = await import("../src/components/lawyer/PreJoin.jsx");
const { ChatDockProvider, useChatDock } = await import("../src/components/lawyer/ChatDock.jsx");
const h = React.createElement;
const settle = () => act(async () => { await new Promise(r => setTimeout(r, 20)); });
const click = async (el) => {
    assert.ok(el, "control missing");
    await act(async () => { el.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true, cancelable: true })); });
    await settle();
};

const APT = { id: "a1", client: "Ayesha Bibi", initials: "AB", duration: "60 min", at: new Date(), meetingLink: null };
const iso = ms => new Date(Date.now() + ms).toISOString();

async function mount() {
    api.__reset();
    api.__respond("getVideoStatus", { data: { configured: true, eligible: true, opens_at: iso(-60e3), closes_at: iso(36e5) } });
    api.__respond("joinVideo", { data: { room_url: "https://x.daily.co/r", token: "t", expires_at: iso(36e5) } });
    media.asked = 0; media.stopped = 0; media.tracks = [];
    let closed = 0, dock;
    function Grab() { dock = useChatDock(); return null; }
    const box = document.createElement("div");
    document.body.appendChild(box);
    const root = createRoot(box);
    await act(async () => root.render(h(ChatDockProvider, null, h(Grab),
        h(PreJoinModal, { apt: APT, day: "Thu 22 Oct", span: "10:00–11:00", when: "Starts in 2 days", live: false, dark: true,
            onClose: () => { closed += 1; }, onSaveLink: async () => ({}) }))));
    await settle();
    return { box, closed: () => closed, dock: () => dock, unmount: () => act(async () => root.unmount()) };
}

test("the page behind is blurred, and the camera is NOT switched on by itself", async () => {
    const ui = await mount();
    assert.ok(document.querySelector("[data-prejoin-backdrop]"));
    assert.match([...document.querySelectorAll("style")].map(s => s.textContent).join(""), /backdrop-filter:blur/);
    assert.equal(document.querySelector("[data-prejoin-backdrop]").parentElement, document.body, "the blur must cover the whole screen, sidebar too");
    assert.equal(media.asked, 0, "the camera was asked for without the lawyer asking");
    assert.ok(document.querySelector("[data-prejoin-check]"));
    assert.ok(document.querySelector("[data-video-join-btn]"), "no Join button");
    await ui.unmount();
});

test("the check starts on request; camera and mic buttons really pause the tracks", async () => {
    const ui = await mount();
    await click(document.querySelector("[data-prejoin-check]"));
    assert.equal(media.asked, 1);
    await click(document.querySelector("[data-prejoin-cam]"));
    assert.equal(media.tracks.find(t => t.kind === "video").enabled, false);
    await click(document.querySelector("[data-prejoin-mic]"));
    assert.equal(media.tracks.find(t => t.kind === "audio").enabled, false);
    await ui.unmount();
    assert.equal(media.stopped, 2, "leaving the screen did not release the camera and mic");
});

test("Join stops the preview first, so the call can take the camera", async () => {
    const ui = await mount();
    await click(document.querySelector("[data-prejoin-check]"));
    await click(document.querySelector("[data-video-join-btn]"));
    assert.equal(media.stopped, 2, "the preview still held the camera when joining");
    assert.equal(api.__calls("joinVideo").length, 1);
    await ui.unmount();
});

test("Message opens the chat and closes this screen; Copy copies the details", async () => {
    const ui = await mount();
    await click(document.querySelector("[data-prejoin-copy]"));
    assert.match(media.copied, /Video consultation with Ayesha Bibi/);
    await click(document.querySelector("[data-prejoin-message]"));
    assert.equal(ui.closed(), 1);
    assert.ok(document.querySelector('[data-chat-window="a1"]'), "the chat did not open");
    await ui.unmount();
});

test("the client's join screen (shared): no own-link field, only the lawyer's link to open; Message opens their thread", async () => {
    const { PreJoinModal: Shared } = await import("../src/components/shared/PreJoin.jsx");
    api.__reset();
    api.__respond("getVideoStatus", { data: { configured: true, eligible: true, opens_at: iso(-60e3), closes_at: iso(36e5) } });
    let messaged = 0;
    const box = document.createElement("div");
    document.body.appendChild(box);
    const root = createRoot(box);
    await act(async () => root.render(h(Shared, {
        apt: { ...APT, client: "Kamran Aziz", meetingLink: "https://meet.example.com/x" }, day: "Thu 22 Oct", span: "10:00–11:00",
        when: "Starts in 2 days", live: false, dark: true, onClose: () => {}, onMessage: () => { messaged += 1; } })));
    await settle();
    assert.equal(document.querySelector("[data-prejoin-link]"), null, "a client cannot set the link");
    assert.equal(document.querySelector("[data-prejoin] [data-join-call]").getAttribute("href"), "https://meet.example.com/x");
    assert.match(document.querySelector("[data-prejoin-message]").textContent, /Message Kamran/);
    await click(document.querySelector("[data-prejoin-message]"));
    assert.equal(messaged, 1);
    await act(async () => root.unmount());
});
