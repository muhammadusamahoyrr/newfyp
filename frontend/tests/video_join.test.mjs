/* In-app video Join (2026-10-19, Marhala 3). Hidden unless the backend says
 * video is set up; opens only in its window; the call runs in an iframe with a
 * token, and Leave ends it. */
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/" });
function define(name, value) {
    Object.defineProperty(globalThis, name, { value, writable: true, configurable: true });
}
for (const name of ["window", "document", "navigator", "HTMLElement", "Element", "Node", "Event", "MouseEvent"]) {
    define(name, dom.window[name]);
}
define("IS_REACT_ACT_ENVIRONMENT", true);

const React = (await import("react")).default;
const { act } = await import("react");
const { createRoot } = await import("react-dom/client");
const api = await import("./support/api-stub.mjs");
const vj = await import("../src/components/shared/VideoJoin.jsx");
const VideoJoin = vj.default;
// The tests below use the plain-iframe fallback; the daily-js path has its own test.
vj.__setDailyLoader(() => Promise.reject(new Error("no daily-js in tests")));
const h = React.createElement;

const iso = ms => new Date(Date.now() + ms).toISOString();
const flush = () => act(() => new Promise(r => setTimeout(r, 0)));

async function mount(props, status) {
    api.__reset();
    api.__respond("getVideoStatus", { data: status });
    api.__respond("joinVideo", { data: { room_url: "https://x.daily.co/aai-1-v0", token: "tok 1", expires_at: iso(36e5) } });
    const box = document.createElement("div");
    document.body.appendChild(box);
    const root = createRoot(box);
    await act(async () => root.render(h(VideoJoin, { apptId: "a1", status: "confirmed", mode: "video", ...props })));
    await flush();
    return { box, root };
}

test("nothing shows when in-app video is not set up", async () => {
    const { box, root } = await mount({}, { configured: false, eligible: true, opens_at: iso(-1), closes_at: iso(36e5) });
    assert.equal(box.querySelector("[data-video-join]"), null);
    act(() => root.unmount());
});

test("not a confirmed video appointment: no call to the backend at all", async () => {
    const { box, root } = await mount({ mode: "in_person" }, { configured: true, eligible: true, opens_at: iso(-1), closes_at: iso(36e5) });
    assert.equal(box.querySelector("[data-video-join]"), null);
    assert.equal(api.__calls("getVideoStatus").length, 0);
    act(() => root.unmount());
});

test("before the window the button is disabled and says when it opens", async () => {
    const { box, root } = await mount({}, { configured: true, eligible: true, opens_at: iso(36e5), closes_at: iso(2 * 36e5) });
    const btn = box.querySelector("[data-video-join-btn]");
    assert.ok(btn.disabled);
    assert.match(box.textContent, /Opens .* — a day before the start/);
    act(() => root.unmount());
});

test("in the window Join opens the call with the token, and Leave ends it", async () => {
    const { box, root } = await mount({}, { configured: true, eligible: true, opens_at: iso(-60e3), closes_at: iso(36e5) });
    const btn = box.querySelector("[data-video-join-btn]");
    assert.equal(btn.disabled, false);
    assert.match(box.textContent, /not recorded/);
    await act(async () => btn.click());
    await flush();
    assert.deepEqual(api.__calls("joinVideo")[0].args, ["a1"]);
    await flush();
    const frame = document.querySelector("[data-video-call] iframe");
    assert.equal(frame.getAttribute("src"), "https://x.daily.co/aai-1-v0?t=tok%201");
    assert.match(frame.getAttribute("allow"), /camera; microphone/);
    await act(async () => document.querySelector("[data-video-leave]").click());
    assert.equal(document.querySelector("[data-video-call]"), null);
    act(() => root.unmount());
});

test("a refused join is shown, not swallowed", async () => {
    const { box, root } = await mount({}, { configured: true, eligible: true, opens_at: iso(-60e3), closes_at: iso(36e5) });
    api.__respond("joinVideo", { error: { message: "This month's in-app video minutes are used up. Use the meeting link instead." } });
    await act(async () => box.querySelector("[data-video-join-btn]").click());
    await flush();
    assert.match(box.querySelector("[role=alert]").textContent, /used up/);
    assert.equal(document.querySelector("[data-video-call]"), null);
    act(() => root.unmount());
});


test("with daily-js: our own Meet-style screen — joins with the token, real mic / camera controls, Leave ends it", async () => {
    const seen = { audio: true, video: true, calls: [] };
    const handlers = {};
    const local = { local: true, session_id: "me", user_name: "Test Lawyer", tracks: {} };
    vj.__setDailyLoader(() => Promise.resolve({
        createCallObject() {
            return {
                on(ev, fn) { handlers[ev] = fn; },
                join(args) { seen.join = args; return Promise.resolve(); },
                leave() { seen.left = true; return Promise.resolve(); },
                destroy() { seen.destroyed = true; },
                participants() { return { local }; },
                localAudio() { return seen.audio; },
                localVideo() { return seen.video; },
                setLocalAudio(v) { seen.audio = v; handlers["participant-updated"]?.(); },
                setLocalVideo(v) { seen.video = v; handlers["participant-updated"]?.(); },
                startScreenShare() { seen.calls.push("share"); },
                stopScreenShare() {},
                enumerateDevices: async () => ({ devices: [] }),
            };
        },
    }));
    const { box, root } = await mount({ otherName: "Ayesha" }, { configured: true, eligible: true, opens_at: iso(-60e3), closes_at: iso(36e5) });
    await act(async () => box.querySelector("[data-video-join-btn]").click());
    await flush(); await flush();
    const screen = document.querySelector("[data-video-call]");
    assert.ok(screen && screen.parentElement === document.body, "the call is not full screen");
    assert.deepEqual(seen.join, { url: "https://x.daily.co/aai-1-v0", token: "tok 1" });
    assert.match(screen.querySelector("[data-vc-waiting]").textContent, /Waiting for Ayesha to join/);
    assert.equal(screen.querySelector("iframe"), null, "Daily's own screen (and its 'ready to join?') must not appear");
    await act(async () => screen.querySelector("[data-vc-mic]").click());
    assert.equal(seen.audio, false, "Mute did not mute");
    assert.equal(screen.querySelector("[data-vc-mic]").getAttribute("aria-label"), "Unmute microphone");
    await act(async () => screen.querySelector("[data-vc-cam]").click());
    assert.equal(seen.video, false);
    await act(async () => screen.querySelector("[data-vc-share]").click());
    assert.deepEqual(seen.calls, ["share"]);
    await act(async () => screen.querySelector("[data-video-leave]").click());
    await flush();
    assert.ok(seen.left && seen.destroyed);
    assert.equal(document.querySelector("[data-video-call]"), null);
    assert.equal(vj.dailyTheme(true).colors.accent, "#40F0DC");
    act(() => root.unmount());
});
