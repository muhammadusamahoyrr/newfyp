/* Where a LAWYER's meeting-proposal notice opens (2026-10-12): a declined,
 * withdrawn or lapsed proposal opens its case (propose again there); an
 * accepted one opens the appointment it became. Bad ids fall back to the page. */
import test from "node:test";
import assert from "node:assert/strict";
import { lawyerNotificationTarget as to } from "../src/lib/notificationTarget.js";

test("a declined or lapsed proposal opens its case", () => {
    assert.deepEqual(to("appointment_proposal_declined", { proposal_id: "P1", case_id: "C1" }), { page: "cases", caseId: "C1" });
    assert.deepEqual(to("appointment_proposal_expired", { case_id: "C1" }), { page: "cases", caseId: "C1" });
    assert.deepEqual(to("appointment_proposal_withdrawn", { case_id: "C1" }), { page: "cases", caseId: "C1" });
});

test("an accepted proposal opens the appointment it became", () => {
    assert.deepEqual(to("appointment_proposal_accepted", { appointment_id: "A1", case_id: "C1" }),
                     { page: "appointments", caseId: null, appointmentId: "A1" });
});

test("missing or malformed ids fall back to the page itself", () => {
    assert.deepEqual(to("appointment_proposal_declined", {}), { page: "cases", caseId: null });
    assert.deepEqual(to("appointment_proposal_declined", { case_id: 42 }), { page: "cases", caseId: null });
    assert.deepEqual(to("appointment_proposal_accepted", { appointment_id: "  " }), { page: "appointments", caseId: null });
    assert.deepEqual(to("appointment_proposal_accepted"), { page: "appointments", caseId: null });
});
test("a message opens the appointment on its thread; the generic rule does not override it", () => {
    assert.deepEqual(to("appointment_message", { appointment_id: "A1" }), { page: "appointments", caseId: null, appointmentId: "A1", thread: true });
    assert.deepEqual(to("appointment_message", {}), { page: "appointments", caseId: null });
    assert.deepEqual(to("appointment_confirmed", { appointment_id: "A1" }), { page: "appointments", caseId: null, appointmentId: "A1" });
});
