/* Where a CLIENT notification opens (2026-10-12). Clicking one used to only
 * mark it read: appointment, proposal and hiring notices led nowhere. */
import test from "node:test";
import assert from "node:assert/strict";
import { clientNotificationTarget as to } from "../src/lib/notificationTarget.js";

test("an appointment notice opens that appointment", () => {
    assert.equal(to("appointment_confirmed", { appointment_id: "a 1" }), "/appointments?appointment=a%201");
    assert.equal(to("appointment_cancelled", { appointment_id: "a2" }), "/appointments?appointment=a2");
    assert.equal(to("appointment_booked", {}), "/appointments");
});

test("a meeting proposal opens Appointments, and once accepted its appointment", () => {
    assert.equal(to("appointment_proposed", { proposal_id: "P1", case_id: "C1" }), "/appointments?section=proposals&proposal=P1");
    assert.equal(to("appointment_proposal_withdrawn", { proposal_id: "P1" }), "/appointments");
    assert.equal(to("appointment_proposal_accepted", { appointment_id: "a9" }), "/appointments?appointment=a9");
});

test("hiring opens the exact request on its case in My Matters (2026-11-23)", () => {
    // Proposed terms are the only place a client sees a price before agreeing:
    // the link carries the case AND the request, never just /lawyers.
    assert.equal(to("engagement_terms_proposed", { engagement_id: "E1", case_id: "C1" }),
        "/tracking?case=C1&tab=summary&engagement=E1");
    assert.equal(to("engagement_declined", { engagement_id: "E2", case_id: "C 2" }),
        "/tracking?case=C+2&tab=summary&engagement=E2");
    assert.equal(to("engagement_accepted", { engagement_id: "E3", case_id: "C3" }),
        "/tracking?case=C3&tab=summary&engagement=E3");
    assert.equal(to("lawyer_assigned", { case_id: "C4" }), "/tracking?case=C4&tab=summary");
    // No case id in an old notification: My Matters, never a wrong case.
    assert.equal(to("engagement_declined", {}), "/tracking");
    for (const t of ["engagement_terms_proposed", "engagement_declined", "engagement_accepted"]) {
        assert.doesNotMatch(to(t, { engagement_id: "E", case_id: "C" }), /^\/lawyers/);
    }
});

test("an agreement notice opens the exact agreement", () => {
    assert.equal(to("agreement_created", { agreement_id: "A 1" }), "/agreements?agreement=A%201");
    assert.equal(to("agreement_executed", {}), "/agreements");
});

test("case notices open their tab on the exact case", () => {
    assert.equal(to("hearing_scheduled", { case_id: "C1" }), "/tracking?case=C1&tab=timeline");
    assert.equal(to("case_message", { case_id: "C1" }), "/tracking?case=C1&tab=messages");
    assert.equal(to("case_update", { case_id: "C1" }), "/tracking?case=C1&tab=summary");
});

test("anything else opens nothing", () => {
    assert.equal(to("something_new", {}), null);
    assert.equal(to(undefined), null);
});
test("a message opens the appointment ON its thread; no id falls back to the page (2026-10-12)", () => {
    assert.equal(to("appointment_message", { appointment_id: "a1" }), "/appointments?appointment=a1&thread=open");
    assert.equal(to("appointment_message", {}), "/appointments");
});

test("a fee notice opens that payment on its case (2026-11-23)", () => {
    assert.equal(to("payment_requested", { payment_id: "P1", case_id: "C1", amount: 5000 }),
        "/tracking?case=C1&tab=payments&payment=P1");
    assert.equal(to("payment_received", { payment_id: "P2", case_id: "C1" }),
        "/tracking?case=C1&tab=payments&payment=P2");
    // "Failed" now names its case too; an older notice without one opens
    // All my payments, never a case page (no case header over another case's fee).
    assert.equal(to("payment_failed", { payment_id: "P3", case_id: "C2" }), "/tracking?case=C2&tab=payments&payment=P3");
    assert.equal(to("payment_failed", { payment_id: "P3" }), "/tracking?view=payments&payment=P3");
    assert.equal(to("payment_failed", {}), "/tracking?view=payments");
});

test("the notification drawer has no 'View all in Tracking' button (2026-11-23)", async () => {
    // Tracking has no notifications page any more, so the button only opened
    // My matters under a label that promised a list. The drawer is the list.
    const { readFileSync } = await import("node:fs");
    const src = readFileSync(new URL("../src/components/client/Dashboard.jsx", import.meta.url), "utf8");
    assert.doesNotMatch(src, />\s*View all in Tracking|onGoTracking=/);
});
