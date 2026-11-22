/* The admin Avatar must not crash on a user with no name (audit 2026-11-22,
 * low #6): name.split on undefined took the whole admin table down. */
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/" });
for (const n of ["window", "document", "navigator", "HTMLElement", "Node"]) {
    Object.defineProperty(globalThis, n, { value: dom.window[n], writable: true, configurable: true });
}
const React = (await import("react")).default;
const { renderToStaticMarkup } = await import("react-dom/server");
const h = React.createElement;

for (const file of ["AdminComponent", "AdminCharts"]) {
    const { Avatar } = await import(`../src/components/admin/${file}.jsx`);
    test(`${file} Avatar: missing, empty and normal names`, () => {
        for (const name of [undefined, null, "", "   "]) {
            const html = renderToStaticMarkup(h(Avatar, { name }));
            assert.match(html, /\?/, `no fallback for ${JSON.stringify(name)}`);
        }
        assert.match(renderToStaticMarkup(h(Avatar, { name: "Sara  Khan" })), />SK</);
        assert.match(renderToStaticMarkup(h(Avatar, { name: "Usama" })), />U</);
    });
}
