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
    assert.equal(to("appointment_proposed", { proposal_id: "P1", case_id: "C1" }), "/appointments");
    assert.equal(to("appointment_proposal_withdrawn", { proposal_id: "P1" }), "/appointments");
    assert.equal(to("appointment_proposal_accepted", { appointment_id: "a9" }), "/appointments?appointment=a9");
});

test("hiring opens where it is answered, then the case", () => {
    assert.equal(to("engagement_terms_proposed", { engagement_id: "E1" }), "/lawyers");
    assert.equal(to("engagement_declined", {}), "/lawyers");
    assert.equal(to("engagement_accepted", {}), "/tracking");
    assert.equal(to("lawyer_assigned", {}), "/tracking");
    assert.equal(to("hearing_scheduled", {}), "/tracking");
});

test("anything else opens nothing", () => {
    assert.equal(to("something_new", {}), null);
    assert.equal(to(undefined), null);
});
test("a message opens the appointment ON its thread; no id falls back to the page (2026-10-12)", () => {
    assert.equal(to("appointment_message", { appointment_id: "a1" }), "/appointments?appointment=a1&thread=open");
    assert.equal(to("appointment_message", {}), "/appointments");
});
