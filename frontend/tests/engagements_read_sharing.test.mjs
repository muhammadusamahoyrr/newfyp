/* listEngagements in the REAL api.js, against a mocked fetch (2026-10-18).
 *
 * The client shell, Overview, Lawyers and Tracking all read the engagement list,
 * often in the same moment (opening Overview fetched it twice). Reads within a
 * short window now share one request. The window must stay short and every
 * engagement change must drop it, because the lawyer can change an engagement
 * too; and callers must not share one mutable array. */
import test from "node:test";
import assert from "node:assert/strict";

const calls = [];
globalThis.BroadcastChannel = class { constructor() { this.onmessage = null; } postMessage() {} close() {} };
globalThis.localStorage = {
    _v: {}, getItem(k) { return this._v[k] ?? null; },
    setItem(k, v) { this._v[k] = String(v); }, removeItem(k) { delete this._v[k]; },
};
globalThis.fetch = async (url, options = {}) => {
    calls.push({ url: String(url), method: options.method || "GET" });
    return new Response(JSON.stringify({ items: [{ _id: "e2" }, { _id: "e1" }] }),
                        { status: 200, headers: { "content-type": "application/json" } });
};
const api = await import("../src/lib/api.js");
const reads = () => calls.filter(c => c.method === "GET" && /\/engagements(\?|$)/.test(new URL(c.url, "http://x").pathname + new URL(c.url, "http://x").search));

test("two reads in the same moment share one request", async () => {
    api.invalidateEngagements(); calls.length = 0;
    const [a, b] = await Promise.all([api.listEngagements(), api.listEngagements()]);
    assert.equal(reads().length, 1);
    assert.deepEqual(a.data, b.data);
});

test("each caller gets its own copy of the list", async () => {
    api.invalidateEngagements(); calls.length = 0;
    const a = await api.listEngagements();
    a.data.items.reverse();
    const b = await api.listEngagements();
    assert.equal(b.data.items[0]._id, "e2", "one caller reordered another's list");
});

test("a different status filter is a different read", async () => {
    api.invalidateEngagements(); calls.length = 0;
    await api.listEngagements();
    await api.listEngagements({ status: "accepted" });
    assert.equal(reads().length, 2);
});

test("changing an engagement makes the next read fresh", async () => {
    api.invalidateEngagements(); calls.length = 0;
    await api.listEngagements();
    await api.acceptEngagementTerms("e1");
    await api.listEngagements();
    assert.equal(reads().length, 2, "the read after accepting terms reused the old list");
});

test("reads are not shared beyond the short window", async () => {
    api.invalidateEngagements(); calls.length = 0;
    await api.listEngagements();
    const realNow = Date.now;
    Date.now = () => realNow() + 5000;
    try { await api.listEngagements(); } finally { Date.now = realNow; }
    assert.equal(reads().length, 2);
});
