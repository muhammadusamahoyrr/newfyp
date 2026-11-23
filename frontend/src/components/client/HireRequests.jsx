'use client';
/* My hire requests — moved from the Lawyers page to Tracking (2026-11-23, at
 * the user's request), with every action it had: withdraw a request, accept or
 * decline proposed terms, mark complete, end an engagement, and the short
 * history of ended ones. It reads the engagements itself and re-reads them
 * when one changes (its own action, or a live engagement notification).
 *
 * `terms_proposed` is the one a client must not miss — it is the only place
 * they see a price before agreeing to it. Nothing is agreed until they accept.
 */
import React, { useEffect, useState } from "react";
import { onPrimaryInk } from "./clientTheme.js";
import { useT } from "./theme.js";
import { useToast } from "@/components/shared/Toast.jsx";
import Ic from "./Ic.jsx";
import {
    listEngagements, cancelEngagement, acceptEngagementTerms, declineEngagementTerms,
    completeEngagement, terminateEngagement,
} from "@/lib/api.js";
import { onNotification } from "@/lib/notificationTarget.js";

const VISIBLE_ENG = ["requested", "terms_proposed", "accepted"];
// Ended ones stay visible as a short history, so the client can see what
// happened to a request, and why.
const ENDED_ENG = ["declined", "cancelled", "completed", "terminated"];
const FEE_SUFFIX = { hourly: "/hr", per_hearing: "/hearing" };
const ENG_BADGE = {
    requested:      { label: "Pending",        color: "#EF9F27" },
    terms_proposed: { label: "Terms received", color: "#3B82F6" },
    accepted:       { label: "Engaged",        color: "#1D9E75" },
    completed:      { label: "Completed",      color: "#6B7280" },
    terminated:     { label: "Ended",          color: "#9CA3AF" },
    declined:       { label: "Declined",       color: "#9CA3AF" },
    cancelled:      { label: "Withdrawn",      color: "#9CA3AF" },
};

export const feeLabel = (e) =>
    e.fee_amount ? `PKR ${Number(e.fee_amount).toLocaleString()}${FEE_SUFFIX[e.fee_type] || ""}` : "";

export const endedText = (e) => {
    const why = (r) => (r ? ` Reason: ${r}` : "");
    if (e.status === "declined") {
        return e.declined_by === "client"
            ? `You declined the terms.${why(e.decline_reason)}`
            : e.terms_withdrawn
                ? `${e.lawyer_name || "The lawyer"} withdrew the terms they proposed.${why(e.decline_reason)}`
                : `${e.lawyer_name || "The lawyer"} declined this request.${why(e.decline_reason)}`;
    }
    if (e.status === "cancelled") {
        return e.cancelled_by === "system"
            ? "This request closed because the case was taken up elsewhere."
            : "You withdrew this request.";
    }
    if (e.status === "completed") return "The engagement was completed.";
    return `The engagement was ended.${why(e.termination_reason)}`;
};

const engBtn = (t) => ({
    fontSize: 11, fontWeight: 600, color: t.textMuted, background: "none",
    border: `1px solid ${t.border}`, borderRadius: 8, padding: "4px 10px",
    cursor: "pointer", flexShrink: 0,
});

export default function HireRequests() {
    const t = useT();
    const toast = useToast();
    const [engagements, setEngagements] = useState([]);
    const [engBusy, setEngBusy] = useState(null);

    const refresh = async () => {
        const res = await listEngagements().catch(() => ({}));
        if (Array.isArray(res?.data)) setEngagements(res.data);
    };
    useEffect(() => { refresh(); }, []);
    // A lawyer proposing terms, or an engagement ending, arrives live.
    useEffect(() => onNotification((n) => {
        const type = String(n.type || "");
        if (type.startsWith("engagement_") || type === "lawyer_assigned") refresh();
    }), []);

    const withdrawRequest = async (engagementId) => {
        const { error } = await cancelEngagement(engagementId);
        if (error) { toast.show(error.message || "Could not withdraw the request.", "error", 3500); return; }
        toast.show("Request withdrawn.", "success", 2500);
        refresh();
    };
    const acceptTerms = async (e) => {
        setEngBusy(e.id);
        const { error } = await acceptEngagementTerms(e.id);
        setEngBusy(null);
        if (error) { toast.show(error.message || "Could not accept the terms.", "error", 4000); return; }
        toast.show(`${e.lawyer_name || "Your lawyer"} is now engaged on your case.`, "success", 5000);
        refresh();
    };
    const declineTerms = async (e) => {
        const reason = window.prompt("Optional: tell the lawyer why these terms don't work (leave blank to skip)");
        if (reason === null) return;
        setEngBusy(e.id);
        const { error } = await declineEngagementTerms(e.id, reason.trim() || null);
        setEngBusy(null);
        if (error) { toast.show(error.message || "Could not decline the terms.", "error", 3500); return; }
        toast.show("Terms declined. Your case is open again — you can approach another lawyer.", "success", 4000);
        refresh();
    };
    const endEngagement = async (e) => {
        const reason = window.prompt(
            "Ending this engagement releases your case so you can engage someone else.\n\n" +
            "Give a reason (required — it is recorded and shown to your lawyer):"
        );
        if (reason === null) return;
        if (!reason.trim()) { toast.show("A reason is required to end an engagement.", "warn", 3500); return; }
        setEngBusy(e.id);
        const { error } = await terminateEngagement(e.id, reason.trim());
        setEngBusy(null);
        if (error) { toast.show(error.message || "Could not end the engagement.", "error", 4000); return; }
        toast.show("Engagement ended. Your case is open again.", "success", 4000);
        refresh();
    };
    const markComplete = async (e) => {
        const note = window.prompt("Optional: add a note about how the matter concluded");
        if (note === null) return;
        setEngBusy(e.id);
        const { data, error } = await completeEngagement(e.id, { note: note.trim() || null });
        setEngBusy(null);
        if (error) { toast.show(error.message || "Could not mark this complete.", "error", 4000); return; }
        toast.show(data?.status === "completed" ? "Engagement completed." : "Completion proposed — your lawyer needs to confirm it.", "success", 4000);
        refresh();
    };

    const visible = engagements.filter(e => VISIBLE_ENG.includes(e.status));
    const ended = engagements
        .filter(e => ENDED_ENG.includes(e.status))
        .sort((a, b) => new Date(b.updated_at || b.responded_at || b.created_at || 0) - new Date(a.updated_at || a.responded_at || a.created_at || 0))
        .slice(0, 5);
    if (!visible.length && !ended.length) return null;

    return (
        <div id="my-hire-requests" data-hire-requests style={{ scrollMarginTop: 16, background: t.card, border: `1.5px solid ${t.border}`, borderRadius: 16, padding: "14px 18px", marginBottom: 20 }}>
            <div style={{ fontSize: 12, fontWeight: 800, color: t.text, textTransform: "uppercase", letterSpacing: "0.8px", marginBottom: 10, display: "flex", alignItems: "center", gap: 8 }}>
                <Ic n="shield" s={14} c={t.primary} /> My Hire Requests
            </div>
            {visible.map(e => {
                const badge = ENG_BADGE[e.status];
                return (
                    <div key={e.id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 0", borderBottom: `1px solid ${t.border}` }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontSize: 13, fontWeight: 700, color: t.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                {e.lawyer_name || "Lawyer"} · {e.case_title || e.case_number}
                            </div>
                            <div style={{ fontSize: 11, color: t.textMuted }}>
                                {e.status === "accepted"
                                    ? `Engaged${feeLabel(e) ? ` — ${feeLabel(e)}` : ""}.`
                                    : e.status === "terms_proposed"
                                        ? `${e.lawyer_name || "The lawyer"} proposed ${feeLabel(e) || "terms"}. Nothing is agreed until you accept.`
                                        : "Waiting for the lawyer to respond…"}
                            </div>
                            {e.status === "terms_proposed" && e.scope_note && (
                                <div style={{ fontSize: 11, color: t.textDim, marginTop: 4, fontStyle: "italic" }}>Scope: {e.scope_note}</div>
                            )}
                            {e.status === "accepted" && e.completion_proposed_by && (
                                <div style={{ fontSize: 11, color: t.primary, marginTop: 4 }}>
                                    {e.completion_proposed_by === "lawyer"
                                        ? "Your lawyer says the work is finished — confirm to close this engagement."
                                        : "You proposed completion; waiting for your lawyer to confirm."}
                                </div>
                            )}
                        </div>
                        <span style={{ fontSize: 11, fontWeight: 700, color: badge.color, background: `${badge.color}18`, borderRadius: 20, padding: "3px 10px", flexShrink: 0 }}>{badge.label}</span>
                        {e.status === "requested" && (
                            <button onClick={() => withdrawRequest(e.id)} disabled={engBusy === e.id} style={engBtn(t)}>Withdraw</button>
                        )}
                        {e.status === "terms_proposed" && (
                            <>
                                <button onClick={() => declineTerms(e)} disabled={engBusy === e.id} style={engBtn(t)}>Decline</button>
                                <button onClick={() => acceptTerms(e)} disabled={engBusy === e.id}
                                    style={{ ...engBtn(t), color: onPrimaryInk(t), background: t.primary, border: `1px solid ${t.primary}` }}>
                                    {engBusy === e.id ? "Accepting…" : "Accept terms"}
                                </button>
                            </>
                        )}
                        {e.status === "accepted" && (
                            <>
                                <button onClick={() => markComplete(e)} disabled={engBusy === e.id} style={engBtn(t)}>
                                    {e.completion_proposed_by === "lawyer" ? "Confirm complete" : "Mark complete"}
                                </button>
                                <button onClick={() => endEngagement(e)} disabled={engBusy === e.id}
                                    style={{ ...engBtn(t), color: "#B91C1C", borderColor: "#FCA5A5" }}>
                                    End engagement
                                </button>
                            </>
                        )}
                    </div>
                );
            })}
            {ended.length > 0 && (
                <div data-ended-engagements style={{ marginTop: visible.length ? 12 : 0 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: t.textMuted, textTransform: "uppercase", letterSpacing: "0.6px", margin: "4px 0 2px" }}>Past requests</div>
                    {ended.map(e => {
                        const badge = ENG_BADGE[e.status];
                        return (
                            <div key={e.id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 0", borderBottom: `1px solid ${t.border}` }}>
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <div style={{ fontSize: 12.5, fontWeight: 600, color: t.textDim, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                        {e.lawyer_name || "Lawyer"} · {e.case_title || e.case_number}
                                    </div>
                                    <div style={{ fontSize: 11, color: t.textMuted, overflowWrap: "anywhere" }}>{endedText(e)}</div>
                                </div>
                                <span style={{ fontSize: 11, fontWeight: 700, color: badge.color, background: `${badge.color}18`, borderRadius: 20, padding: "3px 10px", flexShrink: 0 }}>{badge.label}</span>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
