/* The shared dictation button (2026-10-20), used by the client and the
 * lawyer chat. The browser's SpeechRecognition is faked. */
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/" });
for (const n of ["window", "document", "HTMLElement", "Node", "MouseEvent", "sessionStorage", "navigator", "Blob"]) Object.defineProperty(globalThis, n, { value: dom.window[n], configurable: true, writable: true });
Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { value: true, configurable: true, writable: true });
const React = (await import("react")).default;
const { act } = await import("react");
const { createRoot } = await import("react-dom/client");
const api = await import("./support/api-stub.mjs");
const { default: VoiceButton, joinDictation } = await import("../src/components/shared/VoiceButton.jsx");
const h = React.createElement;

let last = null;
class FakeRec {
    constructor() { last = this; this.started = false; this.stopped = false; }
    start() { this.started = true; }
    stop() { this.stopped = true; this.onend?.(); }
    abort() { this.stopped = true; }
    say(...chunks) { this.onresult?.({ results: chunks.map(c => [{ transcript: c }]) }); }
    fail(error) { this.onerror?.({ error }); }
}

// A microphone the server way can record from (nothing real is opened).
let recorder = null;
class FakeMediaRecorder {
    static isTypeSupported() { return true; }
    constructor(stream, opts) { recorder = this; this.stream = stream; this.mimeType = opts?.mimeType || "audio/webm"; this.state = "inactive"; }
    start() { this.state = "recording"; }
    stop() { this.state = "inactive"; this.ondataavailable?.({ data: new Blob(["sound"], { type: "audio/webm" }) }); this.onstop?.(); }
}
function withMic() {
    dom.window.MediaRecorder = FakeMediaRecorder;
    Object.defineProperty(dom.window.navigator, "mediaDevices", { configurable: true,
        value: { getUserMedia: async () => ({ getTracks: () => [{ stop() {} }] }) } });
}
function withoutMic() {
    delete dom.window.MediaRecorder;
    Object.defineProperty(dom.window.navigator, "mediaDevices", { configurable: true, value: undefined });
}
const settle = () => act(async () => { await new Promise(r => setTimeout(r, 20)); });

async function mount(props, { speech = true } = {}) {
    if (speech) dom.window.webkitSpeechRecognition = FakeRec; else delete dom.window.webkitSpeechRecognition;
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => { root.render(h(VoiceButton, props)); });
    await act(async () => { await new Promise(r => setTimeout(r, 10)); });
    const btn = () => container.querySelector("[data-voice-button]");
    const click = async () => { await act(async () => { btn().dispatchEvent(new MouseEvent("click", { bubbles: true })); }); };
    return { btn, click, unmount: async () => { await act(async () => root.unmount()); container.remove(); } };
}

test("joinDictation keeps the typed text and adds the speech after it", () => {
    assert.equal(joinDictation("Bail under", " section 497 "), "Bail under section 497");
    assert.equal(joinDictation("", "hello"), "hello");
    assert.equal(joinDictation("typed ", ""), "typed");
});

test("listens in Pakistani English, shows words while speaking, and keeps what was typed", async () => {
    const texts = [];
    const ui = await mount({ value: "My question:", onText: t => texts.push(t) });
    await ui.click();
    assert.equal(last.lang, "en-PK");
    assert.equal(last.interimResults, true, "words are not shown while speaking");
    assert.equal(last.continuous, true, "a short pause ends the dictation");
    await act(async () => { last.say("what is"); });
    await act(async () => { last.say("what is", " bail"); });
    assert.deepEqual(texts, ["My question: what is", "My question: what is bail"]);
    assert.equal(ui.btn().getAttribute("aria-pressed"), "true");
    await ui.unmount();
});

test("a second click stops it", async () => {
    const ui = await mount({ value: "", onText: () => {} });
    await ui.click();
    await ui.click();
    assert.equal(last.stopped, true);
    assert.equal(ui.btn().getAttribute("aria-pressed"), "false");
    await ui.unmount();
});

test("each failure is named; our own stop is not an error", async () => {
    withoutMic();
    const errors = [];
    const ui = await mount({ value: "", onText: () => {}, onError: m => errors.push(m) });
    await ui.click();
    await act(async () => { last.fail("aborted"); });
    await act(async () => { last.fail("no-speech"); });
    await act(async () => { last.fail("not-allowed"); });
    assert.deepEqual(errors, ["Didn't hear anything — click the mic and speak.",
        "Microphone permission was refused — allow it in the browser's address bar."]);
    await ui.unmount();
});

test("the browser's speech service unreachable: it switches to recording and our server writes the text", async () => {
    withMic();
    dom.window.sessionStorage.clear();
    api.__respond("transcribeAudio", { data: { transcript: "bail under section 497", language: "en" }, error: null });
    const texts = [], notices = [];
    const ui = await mount({ value: "Question:", onText: t => texts.push(t), onNotice: m => notices.push(m) });
    await ui.click();
    await act(async () => { last.fail("network"); last.onend?.(); });
    await settle();
    assert.match(notices[0] || "", /records instead/);
    assert.equal(ui.btn().getAttribute("data-voice-state"), "recording", "it did not start recording");
    await ui.click();                                   // finish
    await settle();
    assert.equal(api.__calls("transcribeAudio").length, 1);
    assert.equal(api.__calls("transcribeAudio")[0].args[1].language, "en");
    assert.deepEqual(texts, ["Question: bail under section 497"]);
    assert.equal(dom.window.sessionStorage.getItem("attorney:voice-server"), "1", "the switch is not remembered");
    // The next click records straight away.
    last = null;
    await ui.click();
    await settle();
    assert.equal(last, null, "it tried the broken browser service again");
    assert.equal(ui.btn().getAttribute("data-voice-state"), "recording");
    await ui.unmount();
    dom.window.sessionStorage.clear();
});

test("a failed transcription is said, and nothing is typed", async () => {
    withMic();
    dom.window.sessionStorage.setItem("attorney:voice-server", "1");
    api.__respond("transcribeAudio", { data: null, error: { message: "Transcription failed. Please try again." }, status: 500 });
    const texts = [], errors = [];
    const ui = await mount({ value: "", onText: t => texts.push(t), onError: m => errors.push(m) });
    await ui.click(); await settle();
    await ui.click(); await settle();
    assert.deepEqual(texts, []);
    assert.deepEqual(errors, ["Transcription failed. Please try again."]);
    await ui.unmount();
    dom.window.sessionStorage.clear();
});

test("no speech recognition but a microphone: the button records", async () => {
    withMic();
    const ui = await mount({ value: "", onText: () => {} }, { speech: false });
    assert.ok(ui.btn(), "no mic shown where recording works");
    await ui.unmount();
});

test("no speech recognition and no microphone: no button", async () => {
    withoutMic();
    delete dom.window.webkitSpeechRecognition;
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => { root.render(h(VoiceButton, { value: "", onText: () => {} })); });
    assert.equal(container.querySelector("[data-voice-button]"), null);
    await act(async () => root.unmount());
});

test("silence that comes back as '.' is 'didn't hear anything', not typed", async () => {
    withMic();
    dom.window.sessionStorage.setItem("attorney:voice-server", "1");
    api.__respond("transcribeAudio", { data: { transcript: ".", language: "en" }, error: null });
    const texts = [], errors = [];
    const ui = await mount({ value: "", onText: t => texts.push(t), onError: m => errors.push(m) });
    await ui.click(); await settle();
    await ui.click(); await settle();
    assert.deepEqual(texts, []);
    assert.match(errors[0] || "", /Didn't hear anything/);
    await ui.unmount();
    dom.window.sessionStorage.clear();
});

test("mode='server' (the client chat) records for our server, which writes Urdu speech in Urdu", async () => {
    withMic();
    dom.window.sessionStorage.clear();
    api.__respond("transcribeAudio", { data: { transcript: "میرا مقدمہ", language: "ur" }, error: null });
    const texts = [];
    last = null;
    const ui = await mount({ value: "", onText: t => texts.push(t), mode: "server", serverLanguage: "auto" });
    await ui.click(); await settle();
    assert.equal(last, null, "the browser's English-only recognition was used");
    assert.equal(ui.btn().getAttribute("data-voice-state"), "recording");
    await ui.click(); await settle();
    assert.equal(api.__calls("transcribeAudio").at(-1).args[1].language, "auto", "Urdu would be translated to English");
    assert.deepEqual(texts, ["میرا مقدمہ"]);
    await ui.unmount();
});

test("while listening, live sound bars and a timer show; they go when it stops", async () => {
    withMic();
    dom.window.sessionStorage.setItem("attorney:voice-server", "1");
    api.__respond("transcribeAudio", { data: { transcript: "hello", language: "en" }, error: null });
    const ui = await mount({ value: "", onText: () => {} });
    assert.equal(document.querySelector("[data-voice-wave]"), null, "bars before listening");
    await ui.click(); await settle();
    const wave = document.querySelector("[data-voice-wave]");
    assert.ok(wave, "no sound bars while listening");
    assert.equal(wave.querySelectorAll("span[aria-hidden] > span").length, 22);
    assert.match(wave.textContent, /0:0\d/);
    await ui.click(); await settle();
    assert.equal(document.querySelector("[data-voice-wave]"), null, "the bars stayed after stopping");
    await ui.unmount();
    dom.window.sessionStorage.clear();
});
