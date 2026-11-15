/* The browser's first guess at a case type (2026-10-19).
 *
 * A Punjab pre-emption story ("my right of pre-emption" over a neighbour's
 * land sale) was guessed "constitutional" because of the word "right", and the
 * client was then asked which fundamental right had been violated. Land and
 * sale words now count as civil, and a bare "right" no longer means
 * constitutional. */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const { quickClassify } = await import("../src/components/client/ModIntake.jsx");

const PRE_EMPTION = "I own 4 kanal of agricultural land and my neighbour sold his 2 kanal next to mine " +
    "to an outsider. The mutation was attested on 12 August. I sent a notice claiming my right of pre-emption.";

test("a land sale with 'right of pre-emption' is civil", () => {
    assert.equal(quickClassify(PRE_EMPTION), "civil");
});

test("Urdu land words count as civil", () => {
    assert.equal(quickClassify("میرے ہمسائے نے اپنی زمین بیچ دی، میں حق شفعہ چاہتا ہوں"), "civil");
});

test("a bare 'right' does not make a case constitutional", () => {
    assert.notEqual(quickClassify("I have the right of way through my neighbour's lane and he blocked it"), "constitutional");
});

test("a real constitutional matter is still recognised", () => {
    assert.equal(quickClassify("The government violated my fundamental rights; I want to file a writ in the High Court"), "constitutional");
});

test("other types are unchanged", () => {
    assert.equal(quickClassify("My husband gave me talaq and keeps the children"), "family");
    assert.equal(quickClassify("Police registered an FIR against my brother for theft"), "criminal");
});

test("the general caution says information only and to contact a lawyer", () => {
    const src = readFileSync(new URL("../src/components/client/ModIntake.jsx", import.meta.url), "utf8");
    assert.match(src, /unverified: "This is general information for education only, not legal advice\. Please contact a qualified lawyer/);
    assert.doesNotMatch(src, /These steps have not been verified against Pakistani law/);
});
