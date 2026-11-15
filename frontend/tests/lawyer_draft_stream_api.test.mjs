/* aiDraftStream in the REAL api.js, against a mocked fetch (2026-10-14).
 *
 * A draft is complete only when the server's terminal `[DONE]` frame arrives:
 * the legal check runs after the last token, so a stream that stops early is
 * an unchecked draft, not a shorter one. The requirement is the DRAFTER's --
 * the other streams keep resolving on a stream that simply ends.
 */
import test from "node:test";
import assert from "node:assert/strict";

globalThis.BroadcastChannel = class { constructor() { this.onmessage = null; } postMessage() {} close() {} };
globalThis.localStorage = {
    _v: {}, getItem(k) { return this._v[k] ?? null; },
    setItem(k, v) { this._v[k] = String(v); }, removeItem(k) { delete this._v[k]; },
};
const api = await import("../src/lib/api.js");

const frame = (obj) => `data: ${typeof obj === "string" ? obj : JSON.stringify(obj)}\n\n`;

/** fetch answering with these SSE chunks; `breakAfter` errors the body instead of ending it. */
function serve(chunks, { breakAfter = false } = {}) {
    const calls = [];
    globalThis.fetch = async (url, options = {}) => {
        calls.push({ url: String(url), options });
        const enc = new TextEncoder();
        let i = 0;
        const body = new ReadableStream({
            pull(ctrl) {
                if (i < chunks.length) ctrl.enqueue(enc.encode(chunks[i++]));
                else if (breakAfter) ctrl.error(new TypeError("network error"));
                else ctrl.close();
            },
        });
        return new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } });
    };
    return calls;
}

const GUARD = { ran: true, text: "That bail be granted.", withheld: [], checked: 0 };

test("a complete stream resolves, with the guard frame delivered as an event", async () => {
    const calls = serve([frame({ content: "That bail " }), frame({ content: "be granted." }), frame({ guard: GUARD }),
                         frame({ verification: { ran: false } }), frame("[DONE]")]);
    let text = ""; const events = [];
    const out = await api.aiDraftStream({ instruction: "x", province: "sindh" }, t => { text += t; }, e => events.push(e));
    assert.equal(out, true);
    assert.equal(text, "That bail be granted.");
    assert.deepEqual(events[0], { guard: GUARD });
    assert.equal(JSON.parse(calls[0].options.body).province, "sindh");
});

test("[DONE] split across chunks, or without its blank line, still completes", async () => {
    serve([frame({ guard: GUARD }), "data: [DO", "NE]"]);
    assert.equal(await api.aiDraftStream({ instruction: "x" }, () => {}, () => {}), true);
});

test("a stream that ends without [DONE] is an error, even after the guard frame", async () => {
    serve([frame({ content: "That bail be granted." }), frame({ guard: GUARD })]);
    await assert.rejects(api.aiDraftStream({ instruction: "x" }, () => {}, () => {}),
        e => e.code === "stream_incomplete" && /cut off before the legal check finished/.test(e.message));
});

test("a connection that breaks mid-stream is the same error", async () => {
    serve([frame({ content: "That bail" })], { breakAfter: true });
    await assert.rejects(api.aiDraftStream({ instruction: "x" }, () => {}, () => {}),
        e => e.code === "stream_incomplete");
});

test("the server's own error frame keeps its message", async () => {
    serve([frame({ error: "The AI service is busy. Please try again." }), frame("[DONE]")]);
    await assert.rejects(api.aiDraftStream({ instruction: "x" }, () => {}, () => {}),
        e => e.code !== "stream_incomplete" && /AI service is busy/.test(e.message));
});

test("other streams are not held to it: the Urdu pleading stream still resolves without [DONE]", async () => {
    serve([frame({ content: "مسمی" })]);
    let text = "";
    await api.aiPleadingUrduStream({ document: "x" }, t => { text += t; });
    assert.equal(text, "مسمی");
});
