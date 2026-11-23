/* "Your to-do" on a case (Tracking v2, 2026-11-23): only real items the
 * client can move, on THIS case, each with one button. */
import test from "node:test";
import assert from "node:assert/strict";
import { caseTodos } from "../src/lib/caseTodos.js";

test("nothing on the case gives an empty list, never padding", () => {
    assert.deepEqual(caseTodos({ caseId: "C1" }), []);
    assert.deepEqual(caseTodos({ caseId: null, payments: [{ id: "P", case_id: null, status: "created" }] }), []);
});

test("a fee due on this case is a to-do; paid fees and other cases' fees are not", () => {
    const items = caseTodos({ caseId: "C1", payments: [
        { id: "P1", case_id: "C1", status: "created", amount: 5000, purpose: "peshi_fee", expires_at: "2026-11-28T10:00:00Z", created_at: "2026-11-21T10:00:00Z" },
        { id: "P2", case_id: "C1", status: "paid", amount: 3000 },
        { id: "P3", case_id: "C2", status: "created", amount: 9000 },
    ] });
    assert.equal(items.length, 1);
    assert.equal(items[0].title, "Pay the appearance (peshi) fee");
    assert.match(items[0].sub, /PKR 5,000 · requested 21 Nov/);
    assert.equal(items[0].chip, "Pay by 28 Nov");
    assert.equal(items[0].action, "pay");
    assert.equal(items[0].id, "P1");
    assert.equal(items[0].primary, true);
});

test("terms to answer come first, then fees, documents and meeting times", () => {
    const items = caseTodos({
        caseId: "C1", feeText: "PKR 60,000",
        engagement: { id: "E1", status: "terms_proposed", lawyer_name: "Adv. Bilal" },
        payments: [{ id: "P1", case_id: "C1", status: "pending", amount: 100 }],
        docs: [{ id: "D1", title: "Written statement", review_status: "returned" }, { id: "D2", title: "Old", review_status: "approved" }],
        proposals: [{ id: "M1", case_id: "C1", status: "open", lawyer_name: "Adv. Bilal", options: ["a", "b"] }, { id: "M2", case_id: "C2", status: "open" }],
    });
    assert.deepEqual(items.map(i => i.action), ["engagement", "pay", "documents", "proposals"]);
    assert.equal(items[0].title, "Answer Adv. Bilal's terms");
    assert.equal(items[2].title, 'Read "Written statement"');
    assert.match(items[3].sub, /proposed 2 times/);
    assert.deepEqual(items.map(i => i.primary), [true, false, false, false], "more than one card leads");
});

test("a document that must be sent again says so in the API's own words", () => {
    const items = caseTodos({ caseId: "C1", docs: [{ id: "D9", title: "Plaint", review_status: "needs_reapproval",
        recovery: { headline: "Needs approval again", explanation: "x" } }] });
    assert.equal(items.length, 1);
    assert.equal(items[0].title, "Needs approval again");
    assert.equal(items[0].warn, true);
});

test("the lawyer's 'work is finished' waits on the client", () => {
    const items = caseTodos({ caseId: "C1", engagement: { id: "E2", status: "accepted", completion_proposed_by: "lawyer", lawyer_name: "Adv. Ayesha" } });
    assert.equal(items[0].title, "Confirm the work is finished");
    assert.equal(items[0].action, "engagement");
});
