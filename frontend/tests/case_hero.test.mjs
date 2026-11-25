/* The status card's sentence (Tracking v2, 2026-11-23): one line that says
 * where the case is and what happens next, from real records only. */
import test from "node:test";
import assert from "node:assert/strict";
import { caseHero, daysUntil, pickEngagement, stageWindow, journeyStages } from "../src/lib/caseHero.js";

const TODAY = "2026-11-23";
const caseInfo = (over = {}) => ({ id: "C1", status: "in_progress", lawyerAssigned: true, ...over });

test("days are counted on Pakistan days", () => {
    assert.equal(daysUntil("2026-11-23T05:00:00Z", TODAY), 0);
    assert.equal(daysUntil("2026-11-24T05:00:00Z", TODAY), 1);
    assert.equal(daysUntil("2026-12-02T05:00:00Z", TODAY), 9);
    assert.equal(daysUntil(null, TODAY), null);
});

test("a next hearing leads, with the day, time and court", () => {
    const h = caseHero({ caseInfo: caseInfo(), today: TODAY,
        nextHearing: { date: "2026-12-02T05:00:00Z", time: "10:00", court: "Civil Court, Lahore" },
        engagement: { status: "accepted", lawyer_name: "Adv. Ayesha Khan", accepted_at: "2026-11-10T09:00:00Z" } });
    assert.equal(h.headline, "Your next hearing is in 9 days");
    assert.match(h.sub, /Tue, 2 Dec, 10:00 · Civil Court, Lahore|2 Dec.*10:00 · Civil Court, Lahore/);
    assert.equal(h.primary.action, "timeline");
    assert.equal(h.secondary.label, "Message Ayesha");
    assert.equal(h.person.name, "Adv. Ayesha Khan");
    assert.match(h.person.sub, /Engaged since 10 Nov/);
});

test("today and tomorrow are said in words", () => {
    const at = d => caseHero({ caseInfo: caseInfo(), today: TODAY, nextHearing: { date: d } }).headline;
    assert.equal(at("2026-11-23T05:00:00Z"), "Your next hearing is today");
    assert.equal(at("2026-11-24T05:00:00Z"), "Your next hearing is tomorrow");
});

test("terms waiting on the client come before any date", () => {
    const h = caseHero({ caseInfo: caseInfo({ lawyerAssigned: false }), today: TODAY, feeText: "PKR 60,000",
        nextHearing: { date: "2026-12-02T05:00:00Z" },
        engagement: { status: "terms_proposed", lawyer_name: "Adv. Bilal Ahmed" } });
    assert.equal(h.headline, "Adv. Bilal Ahmed sent you terms");
    assert.match(h.sub, /PKR 60,000\. Nothing is agreed until you accept\./);
    // Review terms is the lawyer panel's one button, not repeated on the left.
    assert.equal(h.primary, null);
    assert.equal(h.person.waiting, true);
    assert.deepEqual(h.person.actions.map(x => x.action), ["engagement"]);
    assert.equal(h.tone, "warn");
    assert.equal(h.person.label, "Offering to take your case");
});

test("no lawyer and no request says so, and points to the lawyers", () => {
    const h = caseHero({ caseInfo: caseInfo({ lawyerAssigned: false }), today: TODAY });
    assert.equal(h.headline, "No lawyer on this case yet");
    assert.equal(h.primary.action, "find-lawyer");
    assert.equal(h.person.name, null);
});

test("a request still waiting names the lawyer", () => {
    const h = caseHero({ caseInfo: caseInfo({ lawyerAssigned: false }), today: TODAY,
        engagement: { status: "requested", lawyer_name: "Adv. Sana", created_at: "2026-11-20T09:00:00Z" } });
    assert.equal(h.headline, "Waiting for Adv. Sana to reply");
    assert.match(h.person.sub, /Request sent 20 Nov/);
});

test("a lawyer at work with no hearing date does not invent one", () => {
    const h = caseHero({ caseInfo: caseInfo(), today: TODAY,
        engagement: { status: "accepted", lawyer_name: "Adv. Ayesha Khan" } });
    assert.equal(h.headline, "Ayesha Khan is working on your case");
    assert.match(h.sub, /No hearing date yet/);
});

test("the lawyer saying the work is finished asks the client to confirm", () => {
    const h = caseHero({ caseInfo: caseInfo(), today: TODAY, nextHearing: { date: "2026-12-02T05:00:00Z" },
        engagement: { status: "accepted", lawyer_name: "Adv. Ayesha Khan", completion_proposed_by: "lawyer" } });
    assert.equal(h.headline, "Adv. Ayesha Khan says the work is finished");
    assert.equal(h.primary.action, "engagement");
});

test("a closed case says it is closed", () => {
    const h = caseHero({ caseInfo: caseInfo({ status: "closed" }), today: TODAY, nextHearing: { date: "2026-12-02T05:00:00Z" } });
    assert.equal(h.headline, "This case is closed");
    assert.equal(h.tone, "muted");
});

test("the request that matters: terms first, ended ones never, other cases never", () => {
    const list = [
        { id: "a", case_id: "C1", status: "declined" },
        { id: "b", case_id: "C1", status: "requested" },
        { id: "c", case_id: "C2", status: "terms_proposed" },
        { id: "d", case_id: "C1", status: "terms_proposed" },
    ];
    assert.equal(pickEngagement(list, "C1").id, "d");
    assert.equal(pickEngagement([{ id: "x", case_id: "C1", status: "cancelled" }], "C1"), null);
    assert.equal(pickEngagement(list, null), null);
});

test("the stage line shows the steps around the current one, at most five", () => {
    const steps = ["A", "B", "C", "D", "E", "F", "G"].map((e, i) => ({ event: e, date: `D${i}`, status: i < 4 ? "done" : "pending" }));
    const w = stageWindow(steps);
    assert.deepEqual(w.map(s => s.title), ["C", "D", "E", "F", "G"]);
    assert.deepEqual(w.map(s => s.state), ["done", "done", "now", "next", "next"]);
    assert.equal(w[2].when, "You are here");
    assert.deepEqual(stageWindow([]), []);
    const allDone = stageWindow([{ event: "A", status: "done" }, { event: "B", status: "done" }]);
    assert.deepEqual(allDone.map(s => s.state), ["done", "done"]);
});

test("an unread hire request is never 'your lawyer is working', even with a lawyer assigned", () => {
    const h = caseHero({ caseInfo: caseInfo(), today: TODAY, engagementState: "error" });
    assert.equal(h.headline, "Couldn't check this case's latest status");
    assert.equal(h.primary.action, "retry-engagements");
    assert.equal(h.warning, null, "the headline already is the warning");
    const loading = caseHero({ caseInfo: caseInfo(), today: TODAY, engagementState: "loading" });
    assert.equal(loading.headline, "Checking your case…");
});

test("a sentence that stands on other facts carries a warning when the request could not be read", () => {
    const h = caseHero({ caseInfo: caseInfo(), today: TODAY, engagementState: "error",
        nextHearing: { date: "2026-12-02T05:00:00Z" } });
    assert.equal(h.headline, "Your next hearing is in 9 days");
    assert.match(h.warning, /may be out of date/);
    const stale = caseHero({ caseInfo: caseInfo(), today: TODAY, engagementState: "error",
        engagement: { status: "accepted", lawyer_name: "Adv. Ayesha Khan" } });
    assert.match(stale.warning, /Couldn't check the latest/, "stale data was shown as current");
});

/* The journey line for a case without milestones (2026-11-25): each stage is
 * done only on a real fact, and the first stage not done is "You are here". */
const states = l => l.map(s => `${s.state}:${s.title}`);
test("journey: a new case with no lawyer is at 'Choosing a lawyer'", () => {
    const l = journeyStages({ caseInfo: { status: "open", filed: "Nov 17, 2026" } });
    assert.deepEqual(states(l), ["done:Problem described", "now:Choosing a lawyer", "next:Case filed", "next:Hearings", "next:Decision"]);
    assert.equal(l[0].when, "Nov 17, 2026");
    assert.equal(l[1].when, "You are here");
});
test("journey: an accepted lawyer moves it to 'Case filed', dated by the acceptance", () => {
    const l = journeyStages({ caseInfo: { status: "in_progress" }, engagement: { status: "accepted", accepted_at: "2026-11-18T09:00:00Z" } });
    assert.deepEqual(states(l).slice(0, 3), ["done:Problem described", "done:Lawyer hired", "now:Case filed"]);
    assert.match(l[1].when, /18 Nov|Nov 18/);
});
test("journey: a hearing means the case is filed; closed means decided", () => {
    const h = journeyStages({ caseInfo: { status: "in_progress", lawyerAssigned: true }, nextHearing: { date: "2026-12-02T05:00:00Z" } });
    assert.deepEqual(states(h).slice(2, 4), ["done:Case filed", "now:Hearings"]);
    const c = journeyStages({ caseInfo: { status: "closed", lawyerAssigned: true } });
    assert.ok(c.every(s => s.state === "done"), "a closed case is not fully done");
});
test("journey: a request that is only sent does not count as a lawyer hired", () => {
    const l = journeyStages({ caseInfo: { status: "open" }, engagement: { status: "requested" } });
    assert.equal(l[1].state, "now");
    assert.equal(l[1].title, "Choosing a lawyer");
});
