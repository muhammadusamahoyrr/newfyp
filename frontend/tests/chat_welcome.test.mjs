/* The client chat's empty screen (Version C, approved 2026-11-23).
 *
 * Source checks, as in surfaces.test.mjs: the screen needs a live socket to
 * mount, and what matters here is what is (and is no longer) on it.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const code = readFileSync(
    new URL("../src/components/client/ModChatbot.jsx", import.meta.url), "utf8");

test("the empty chat has no mascot, emoji greeting or dead upgrade button", () => {
    assert.doesNotMatch(code, /chatbot\.gif/, "the robot mascot is back");
    assert.doesNotMatch(code, /Dark mode is on/, "the after-8pm joke is back");
    assert.doesNotMatch(code, /Upgrade Plan/, "the Upgrade Plan button (no action) is back");
    assert.doesNotMatch(code, /Playfair Display/, "the serif that fell back to Times is back");
});

test("starter questions fill the box and never send on their own", () => {
    assert.match(code, /const STARTER_QUESTIONS = \[/);
    const fill = code.match(/const fillQuestion = q => \{([^}]*)\}/);
    assert.ok(fill, "fillQuestion is missing");
    assert.match(fill[1], /setInp\(q\)/);
    assert.doesNotMatch(fill[1], /send\(/, "a starter question sends without the client pressing send");
    assert.match(code, /onClick=\{\(\) => fillQuestion\(q\.text\)\}/);
});

test("the input sits under the greeting on an empty chat, at the bottom otherwise", () => {
    assert.match(code, /const composer = \(/);
    assert.match(code, /<div data-chat-welcome[\s\S]*?\{composer\}/, "the empty chat does not show the input");
    assert.match(code, /\{hasMessages && \([\s\S]*?\{composer\}/, "a chat with messages lost its bottom input");
});

test("the question box grows: Enter sends, Shift+Enter is a new line", () => {
    assert.match(code, /<textarea\s+ref=\{inpRef\}/, "the question box is a single-line input again");
    assert.match(code, /e\.key === "Enter" && !e\.shiftKey && !e\.nativeEvent\.isComposing/,
        "Enter must send, Shift+Enter must not, and an Urdu IME composition must not");
    assert.match(code, /e\.preventDefault\(\);\s*send\(\);/, "Enter adds a stray new line before sending");
    assert.match(code, /el\.style\.height = `\$\{Math\.min\(full, MAX_INPUT_HEIGHT\)\}px`/,
        "the box no longer fits its text up to a limit");
});

test("the lawyer research box grows the same way", () => {
    const lawyer = readFileSync(
        new URL("../src/components/lawyer/AILegalPage.jsx", import.meta.url), "utf8");
    assert.match(lawyer, /<textarea ref=\{queryRef\}/, "the research box is a single-line input again");
    assert.match(lawyer, /e\.key === "Enter" && !e\.shiftKey && !e\.nativeEvent\.isComposing/);
    assert.match(lawyer, /el\.style\.height = `\$\{Math\.min\(full, MAX_QUERY_HEIGHT\)\}px`/);
});

test("the lawyer research box sits under the heading on an empty thread, like the client chat", () => {
    const lawyer = readFileSync(
        new URL("../src/components/lawyer/AILegalPage.jsx", import.meta.url), "utf8");
    assert.match(lawyer, /const composer = \(/);
    assert.match(lawyer, /className="ai-welcome"[\s\S]*?<div className="ai-compose">\{composer\}<\/div>[\s\S]*?className="ai-below"/,
        "the empty thread does not show the box under the heading");
    assert.match(lawyer, /\{hasMessages && \([\s\S]*?\{composer\}/, "a thread with messages lost its bottom box");
});

test("the lawyer research history does not fill with empty threads either", () => {
    const lawyer = readFileSync(
        new URL("../src/components/lawyer/AILegalPage.jsx", import.meta.url), "utf8");
    // New Chat on an empty thread for the same case reuses it…
    assert.match(lawyer, /sessionIdRef\.current && msgs\.length === 0 && !loading\s*&& boundCaseRef\.current === caseId/);
    // …and a thread with no message is not listed, except the open one.
    assert.match(lawyer, /\(r\.message_count \?\? 1\) > 0 \|\| r\.session_id === sessionIdRef\.current/);
});

test("empty conversations do not fill the history with 'New conversation' copies", () => {
    // New Chat on an already-empty chat reuses it…
    assert.match(code, /sessionReady && sessionIdRef\.current && msgs\.length === 0 && !typing/);
    // …and a chat with no message is not listed, except the open one.
    assert.match(code, /\(r\.message_count \?\? 1\) > 0 \|\| r\.session_id === sessionIdRef\.current/);
});
