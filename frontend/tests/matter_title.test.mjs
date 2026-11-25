/* lib/matterTitle.js: an old matter's title is the client's whole intake
 * question; cards, menus and dialogs show it shortened, the tooltip keeps it. */
import test from "node:test";
import assert from "node:assert/strict";
import { shortMatterTitle, fullMatterTitle, matterLabel } from "../src/lib/matterTitle.js";

const INTAKE = "My name is Imran Ali and I live in Village Chak 45, Tehsil Kasur, District Kasur, مرا دوست مجھے پاسے وہاں پیس, no";

test("a short title is left alone, whitespace tidied", () => {
    assert.equal(shortMatterTitle("  Rent   dispute \n with landlord "), "Rent dispute with landlord");
});

test("a long intake title is cut at a word and ends in an ellipsis", () => {
    const s = shortMatterTitle(INTAKE, 60);
    assert.ok(s.length <= 60, `too long: ${s.length}`);
    assert.ok(s.endsWith("…"));
    assert.ok(INTAKE.startsWith(s.slice(0, -1).trimEnd()), "not a prefix of the real title");
    assert.doesNotMatch(s, /[,\s]…$/, "ends on punctuation before the ellipsis");
});

test("the full title survives for tooltips, and nothing is ever empty", () => {
    assert.equal(fullMatterTitle(INTAKE), INTAKE.replace(/\s+/g, " ").trim());
    assert.equal(shortMatterTitle(""), "Untitled matter");
    assert.equal(fullMatterTitle(null), "Untitled matter");
});

test("the case number is never cut", () => {
    const l = matterLabel(INTAKE, "ATT-DEMO-0142", 40);
    assert.ok(l.endsWith(" · ATT-DEMO-0142"));
    assert.ok(l.split(" · ")[0].length <= 40);
});
