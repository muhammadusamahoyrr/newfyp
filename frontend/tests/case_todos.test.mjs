/* "Your to-do" on a case (Tracking v2, 2026-11-23): only real items the
 * client can move, on THIS case, each with one button. */
import test from "node:test";
import assert from "node:assert/strict";
import { appointmentTodos, caseTodos } from "../src/lib/caseTodos.js";

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

test("a failed payment remains actionable and tells the client to retry", () => {
    const items = caseTodos({ caseId: "C1", payments: [
        { id: "P4", case_id: "C1", status: "failed", amount: 2500, purpose: "professional_fee" },
    ] });
    assert.equal(items.length, 1);
    assert.equal(items[0].chip, "Payment failed");
    assert.equal(items[0].cta, "Try payment again");
    assert.equal(items[0].id, "P4");
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

test("an agreement is on the to-do only when it waits for THIS client's signature, on this case", () => {
    const mine = { id: "A1", case_id: "C1", status: "pending", title: "Engagement letter", signed_count: 1, total_parties: 2,
        parties: [{ user_id: "L1", signed: true }, { user_id: "U1", signed: false }] };
    const items = caseTodos({ caseId: "C1", userId: "U1", agreements: [mine] });
    assert.equal(items.length, 1);
    assert.equal(items[0].action, "agreements");
    assert.equal(items[0].title, "Sign \u201cEngagement letter\u201d");
    assert.equal(items[0].sub, "1 of 2 have signed");
    // already signed by the client, another case, not pending, someone else's signature, or no known user: nothing
    assert.equal(caseTodos({ caseId: "C1", userId: "U1", agreements: [{ ...mine, parties: [{ user_id: "U1", signed: true }] }] }).length, 0);
    assert.equal(caseTodos({ caseId: "C2", userId: "U1", agreements: [mine] }).length, 0);
    assert.equal(caseTodos({ caseId: "C1", userId: "U1", agreements: [{ ...mine, status: "executed" }] }).length, 0);
    assert.equal(caseTodos({ caseId: "C1", userId: "U9", agreements: [mine] }).length, 0);
    assert.equal(caseTodos({ caseId: "C1", userId: null, agreements: [mine] }).length, 0);
});

test("appointment time choices waiting on the client are real case to-dos", () => {
    const items = caseTodos({ caseId: "C1", appointments: [
        { id: "S1", case_id: "C1", status: "pending", lawyer_name: "Adv. Sana",
            time_suggestion: { options: ["2026-12-01T10:00:00Z", "2026-12-02T10:00:00Z"] } },
        { id: "R1", case_id: "C1", status: "confirmed", lawyer_name: "Adv. Sana",
            reschedule_proposal: { by: "lawyer", scheduled_at: "2026-12-03T10:00:00Z", expires_at: "2099-12-01T00:00:00Z" } },
        { id: "R2", case_id: "C1", status: "confirmed",
            reschedule_proposal: { by: "client", scheduled_at: "2026-12-04T10:00:00Z" } },
        { id: "OTHER", case_id: "C2", status: "pending", time_suggestion: { options: ["x"] } },
    ] });
    assert.deepEqual(items.map(i => i.id), ["S1", "R1"]);
    assert.deepEqual(items.map(i => i.action), ["appointment", "appointment"]);
    assert.match(items[0].title, /Choose a consultation time/);
    assert.match(items[1].title, /proposed new time/);
});

test("case-less appointment actions remain visible outside matter cards", () => {
    const items = appointmentTodos({ appointments: [
        { id: "FREE", case_id: null, status: "pending", lawyer_name: "Adv. Noor",
            time_suggestion: { options: ["2026-12-01T10:00:00Z"] } },
        { id: "CASED", case_id: "C1", status: "pending", time_suggestion: { options: ["x"] } },
    ], caseId: null });
    assert.deepEqual(items.map(i => i.id), ["FREE"]);
});
