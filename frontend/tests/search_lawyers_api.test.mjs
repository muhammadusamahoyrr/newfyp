/* searchLawyers in the REAL api.js, against a mocked fetch: the Lawyers page's
 * search box (q / bar_number) and sort menu reach the server (2026-10-12).
 * They used to be dropped by the helper, so neither did anything. */
import test from "node:test";
import assert from "node:assert/strict";

async function loadApi(calls) {
    globalThis.BroadcastChannel = class { constructor() { this.onmessage = null; } postMessage() {} close() {} };
    globalThis.localStorage = {
        _v: {}, getItem(k) { return this._v[k] ?? null; },
        setItem(k, v) { this._v[k] = String(v); }, removeItem(k) { delete this._v[k]; },
    };
    globalThis.fetch = async (url, options = {}) => {
        calls.push({ url: String(url), options });
        return new Response(JSON.stringify({ items: [], total: 0 }),
                            { status: 200, headers: { "content-type": "application/json" } });
    };
    return import("../src/lib/api.js");
}

const query = (call) => new URL(call.url, "http://x").searchParams;

test("the search text and the sort key are sent", async () => {
    const calls = [];
    const api = await loadApi(calls);
    await api.searchLawyers({ q: "  Bilal ", sort: "fee_asc", page: 2, page_size: 12 });
    const p = query(calls[0]);
    assert.equal(p.get("q"), "Bilal");
    assert.equal(p.get("sort"), "fee_asc");
    assert.equal(p.get("page"), "2");
    assert.equal(p.get("page_size"), "12");
});

test("a bar number search is sent as bar_number", async () => {
    const calls = [];
    const api = await loadApi(calls);
    await api.searchLawyers({ bar_number: "LHC-1234" });
    assert.equal(query(calls[0]).get("bar_number"), "LHC-1234");
    assert.equal(query(calls[0]).get("q"), null);
});

test("empty search text and no sort add nothing", async () => {
    const calls = [];
    const api = await loadApi(calls);
    await api.searchLawyers({ q: "   ", bar_number: "", sort: undefined, province: "punjab" });
    const p = query(calls[0]);
    assert.equal(p.get("q"), null);
    assert.equal(p.get("bar_number"), null);
    assert.equal(p.get("sort"), null);
    assert.equal(p.get("province"), "punjab");
});
