/* The Overview's updates feed and details (Tracking v2, 2026-11-23). */
import test from "node:test";
import assert from "node:assert/strict";
import { caseUpdates, groupByDay, caseDetails } from "../src/lib/caseUpdates.js";

test("updates come from real records, newest first", () => {
    const u = caseUpdates({
        messages: [{ _id: "m1", sender_role: "lawyer", sender_name: "Adv. A", text: "Hi", created_at: "2026-11-22T06:00:00Z" }],
        docs: [{ id: "d1", name: "Plaint", at: Date.parse("2026-11-21T06:00:00Z") }],
        steps: [{ id: 1, event: "Notice sent", status: "done", at: Date.parse("2026-11-20T06:00:00Z") }, { id: 2, event: "Hearing", status: "pending", at: 1 }],
        payments: [{ id: "p1", amount: 5000, status: "created", purpose: "peshi_fee", created_at: "2026-11-23T06:00:00Z" }],
        lawyerName: "Adv. A",
    });
    assert.deepEqual(u.map(x => x.tag), ["fee", "msg", "doc", "step"]);
    assert.equal(u[0].what, "requested the appearance (peshi) fee of PKR 5,000");
    assert.ok(!u.some(x => x.who === "Hearing"), "a step not done was shown as an update");
    assert.deepEqual(caseUpdates(), []);
});

test("updates are grouped by Pakistan day", () => {
    const g = groupByDay([
        { key: "a", at: Date.parse("2026-11-23T10:00:00Z") },
        { key: "b", at: Date.parse("2026-11-22T10:00:00Z") },
        { key: "c", at: Date.parse("2026-11-20T10:00:00Z") },
    ], "2026-11-23");
    assert.deepEqual(g.map(x => x.label), ["Today", "Yesterday", "20 Nov"]);
});

test("details leave out what is not known instead of showing dashes", () => {
    const d = caseDetails({ caseInfo: { type: "civil", caseNumber: null, court: "—", filed: "9 Nov 2026" }, payments: [], docs: [] });
    const c = d.find(x => x.key === "case");
    assert.deepEqual(c.rows.map(r => r.k), ["Type", "Opened"]);
    const m = d.find(x => x.key === "money");
    assert.deepEqual(m.rows.map(r => r.k), ["Paid"], "a due row was shown with nothing due");
});
