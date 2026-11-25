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
import React, { useEffect, useRef, useState } from "react";
import { onPrimaryInk } from "./clientTheme.js";
import { useT } from "./theme.js";
import { useToast } from "@/components/shared/Toast.jsx";
import Ic from "./Ic.jsx";
import {
    listEngagements, cancelEngagement, acceptEngagementTerms, declineEngagementTerms,
    completeEngagement, terminateEngagement,
} from "@/lib/api.js";
import { onNotification } from "@/lib/notificationTarget.js";
import { ModalPortal, BACKDROP } from "@/components/client/documents/ui.jsx";

const VISIBLE_ENG = ["requested", "terms_proposed", "accepted"];
// Ended ones stay visible as a short history, so the client can see what
// happened to a request, and why.
const ENDED_ENG = ["declined", "cancelled", "completed", "terminated"];
const FEE_SUFFIX = { hourly: "/hr", per_hearing: "/hearing" };
const ENG_BADGE = {
    requested:      { label: "Pending",        color: "#EF9F27" },
    terms_proposed: { label: "Terms received", color: "var(--gold, #F2C35E)" },
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

// Readable, finger-sized actions (2026-11-23: they were 11px chips).
// One size for every action and the status chip beside them (2026-11-25),
// and a colour that says what the button does: go ahead = brand gradient,
// say no / end = danger, everything else = a quiet outline.
const engBtn = (t) => ({
    fontSize: 13, fontWeight: 700, color: t.textMuted, background: "none",
    border: `1px solid ${t.border}`, borderRadius: 999, height: 36, minWidth: 128, padding: "0 16px",
    display: "inline-flex", alignItems: "center", justifyContent: "center", boxSizing: "border-box",
    cursor: "pointer", flexShrink: 0, whiteSpace: "nowrap",
});
const engGo = (t) => ({ ...engBtn(t), border: 0, color: "var(--on-brand, #04212A)",
    background: "var(--brand-solid, linear-gradient(135deg,#3EE0A1,#2EC4D6))" });
const engStop = (t) => ({ ...engBtn(t), color: "var(--danger, #FF8A80)", background: "var(--danger-soft, rgba(255,138,128,.14))",
    border: "1px solid color-mix(in srgb, var(--danger, #FF8A80) 45%, transparent)" });
const engChip = (color) => ({ display: "inline-flex", alignItems: "center", justifyContent: "center", boxSizing: "border-box",
    height: 36, minWidth: 128, padding: "0 14px", borderRadius: 999, flexShrink: 0, whiteSpace: "nowrap",
    fontSize: 13, fontWeight: 700, color, background: `color-mix(in srgb, ${color} 14%, transparent)` });

/* The note asked for before declining terms, ending or completing an
 * engagement (2026-11-23). These used to be browser prompts: unstyled, easy
 * to dismiss by accident, and an empty "required" reason only failed AFTER
 * the prompt had closed. */
const NOTE_DIALOG = {
    decline: {
        title: "Decline these terms?",
        body: e => `${e.lawyer_name || "The lawyer"} will be told you declined. Your case opens again, so you can approach another lawyer.`,
        label: "Reason for the lawyer", hint: "optional",
        placeholder: "e.g. The fee is more than I can pay right now",
        confirm: "Decline terms", danger: true, required: false,
    },
    end: {
        title: "End this engagement?",
        body: e => `${e.lawyer_name || "Your lawyer"} will no longer act on ${e.case_title || "this case"}. The case is released so you can engage someone else. The reason is recorded and shown to your lawyer.`,
        label: "Reason", hint: "required",
        placeholder: "Why are you ending this engagement?",
        confirm: "End engagement", danger: true, required: true,
    },
    complete: {
        title: "Mark this matter complete?",
        body: () => "Your lawyer has to confirm before the engagement closes.",
        label: "How did the matter conclude?", hint: "optional",
        placeholder: "e.g. Settled out of court",
        confirm: "Mark complete", danger: false, required: false,
    },
    confirmComplete: {
        title: "Confirm the work is finished?",
        body: e => `${e.lawyer_name || "Your lawyer"} says the work is finished. Confirming closes this engagement.`,
        label: "Note", hint: "optional",
        placeholder: "Anything you want on record",
        confirm: "Confirm complete", danger: false, required: false,
    },
};

function NoteDialog({ t, kind, engagement, busy, onCancel, onConfirm }) {
    const cfg = NOTE_DIALOG[kind];
    const [text, setText] = useState("");
    const box = useRef(null);
    useEffect(() => {
        box.current?.focus();
        const esc = (ev) => { if (ev.key === "Escape" && !busy) onCancel(); };
        window.addEventListener("keydown", esc);
        return () => window.removeEventListener("keydown", esc);
    }, [busy, onCancel]);
    const missing = cfg.required && !text.trim();
    const danger = t.danger || "#B42318";
    const btn = (look) => {
        const off = busy || (look !== "ghost" && missing);
        return {
            height: 40, padding: "0 18px", borderRadius: 10, fontFamily: "inherit", fontSize: 13.5, fontWeight: 700,
            cursor: off ? "default" : "pointer", opacity: off ? .55 : 1,
            border: look === "prim" ? `1px solid ${t.primary}` : `1px solid ${look === "danger" ? danger : t.border}`,
            background: look === "prim" ? t.primary : "transparent",
            color: look === "prim" ? onPrimaryInk(t) : look === "danger" ? danger : t.text,
        };
    };
    const submit = () => { if (!busy && !missing) onConfirm(text.trim() || null); };
    return (
        <ModalPortal>
            <div data-lenis-prevent style={{ ...BACKDROP, display: "grid", placeItems: "center", padding: 20 }}
                onClick={() => { if (!busy) onCancel(); }}>
                <div role="dialog" aria-modal="true" aria-label={cfg.title} data-note-dialog={kind}
                    onClick={ev => ev.stopPropagation()}
                    style={{ width: "min(460px, 100%)", borderRadius: 16, background: t.card, border: `1px solid ${t.border}`,
                        boxShadow: "0 30px 80px rgba(0,0,0,.45)", padding: "22px 24px", display: "flex", flexDirection: "column", gap: 14, color: t.text }}>
                    <div>
                        <div style={{ fontSize: 17, fontWeight: 800 }}>{cfg.title}</div>
                        <div style={{ fontSize: 13, color: t.textMuted, marginTop: 6, lineHeight: 1.55 }}>{cfg.body(engagement)}</div>
                    </div>
                    <label style={{ display: "block" }}>
                        <div style={{ fontSize: 12, fontWeight: 700, color: t.textMuted, marginBottom: 6 }}>
                            {cfg.label} <span style={{ fontWeight: 500 }}>({cfg.hint})</span>
                        </div>
                        <textarea ref={box} value={text} onChange={ev => setText(ev.target.value)} rows={3} maxLength={1000}
                            placeholder={cfg.placeholder} disabled={busy} aria-required={cfg.required || undefined}
                            onKeyDown={ev => { if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) submit(); }}
                            style={{ width: "100%", boxSizing: "border-box", resize: "vertical", minHeight: 76, borderRadius: 10,
                                border: `1px solid ${t.border}`, background: t.inputBg, color: t.text, fontSize: 13.5,
                                fontFamily: "inherit", lineHeight: 1.5, outline: "none", padding: "9px 11px" }} />
                    </label>
                    <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
                        <button type="button" data-note-cancel onClick={onCancel} disabled={busy} style={btn("ghost")}>Cancel</button>
                        <button type="button" data-note-confirm onClick={submit} disabled={busy || missing}
                            style={btn(cfg.danger ? "danger" : "prim")}>{busy ? "Working…" : cfg.confirm}</button>
                    </div>
                </div>
            </div>
        </ModalPortal>
    );
}

/** `caseId` scopes the list to ONE case (2026-11-23): the Tracking page shows
 *  a selected case, and a request for another case under it read as if it
 *  belonged to this one. One case means one case (review item 4): requests
 *  on OTHER cases are not named here at all; My matters shows what waits on
 *  the client across every case. `focusEngagementId` highlights the request
 *  a link pointed at. */
export default function HireRequests({ caseId = null, focusEngagementId = null } = {}) {
    const t = useT();
    const toast = useToast();
    const [engagements, setEngagements] = useState([]);
    // loading | ready | error -- a failed read is never shown as "no requests"
    // (it could hide terms that are waiting on the client).
    const [loadState, setLoadState] = useState("loading");
    const [engBusy, setEngBusy] = useState(null);
    const focusedOnce = useRef(null);
    const [note, setNote] = useState(null);   // { kind, engagement } while a dialog is open

    // The case on screen now, for reads started by a notification listener that
    // was created earlier; and a number per read, so only the newest answer
    // lands (a slow read for the previous case must not overwrite this one).
    const caseRef = useRef(caseId);
    caseRef.current = caseId;
    const readSeq = useRef(0);
    const refresh = async () => {
        const mine = ++readSeq.current;
        const forCase = caseRef.current;
        // One case: the server returns only that case's requests (review item 5).
        const res = await listEngagements(forCase ? { caseId: forCase } : undefined).catch(e => ({ error: e }));
        if (mine !== readSeq.current) return;
        if (Array.isArray(res?.data)) { setEngagements(res.data); setLoadState("ready"); }
        // A failed RE-read keeps the list but says it may be out of date.
        else setLoadState(s => (s === "ready" || s === "stale" ? "stale" : "error"));
    };
    // A different case is a fresh read, never the previous case's list.
    useEffect(() => { setEngagements([]); setLoadState("loading"); refresh(); }, [caseId]);
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
    // Decline / end / complete ask for a note first (NoteDialog). The dialog
    // stays open and busy until the server answers, and closes only on success.
    const runNote = async (text) => {
        const { kind, engagement: e } = note;
        setEngBusy(e.id);
        let res;
        if (kind === "decline") res = await declineEngagementTerms(e.id, text);
        else if (kind === "end") res = await terminateEngagement(e.id, text);
        else res = await completeEngagement(e.id, { note: text });
        setEngBusy(null);
        const { data, error } = res || {};
        if (error) {
            const what = kind === "decline" ? "decline the terms" : kind === "end" ? "end the engagement" : "mark this complete";
            toast.show(error.message || `Could not ${what}.`, "error", 4000);
            return;
        }
        setNote(null);
        toast.show(kind === "decline" ? "Terms declined. Your case is open again — you can approach another lawyer."
            : kind === "end" ? "Engagement ended. Your case is open again."
            : data?.status === "completed" ? "Engagement completed." : "Completion proposed — your lawyer needs to confirm it.",
            "success", 4000);
        refresh();
    };
    const declineTerms = e => setNote({ kind: "decline", engagement: e });
    const endEngagement = e => setNote({ kind: "end", engagement: e });
    const markComplete = e => setNote({ kind: e.completion_proposed_by === "lawyer" ? "confirmComplete" : "complete", engagement: e });

    const inScope = caseId ? engagements.filter(e => String(e.case_id || "") === String(caseId)) : engagements;
    const visible = inScope.filter(e => VISIBLE_ENG.includes(e.status));
    const ended = inScope
        .filter(e => ENDED_ENG.includes(e.status))
        .sort((a, b) => new Date(b.updated_at || b.responded_at || b.created_at || 0) - new Date(a.updated_at || a.responded_at || a.created_at || 0))
        .slice(0, 5);

    // The request a link pointed at: scrolled to once it is on screen.
    useEffect(() => {
        if (!focusEngagementId || focusedOnce.current === focusEngagementId) return;
        const el = typeof document !== "undefined"
            && [...document.querySelectorAll("[data-engagement]")].find(n => n.getAttribute("data-engagement") === String(focusEngagementId));
        if (el) { focusedOnce.current = focusEngagementId; el.scrollIntoView?.({ behavior: "smooth", block: "center" }); }
    });

    if (loadState === "loading") return null;
    if (loadState === "error") {
        return (
            <div role="alert" data-hire-requests-error style={{ background: t.card, border: `1.5px solid ${t.border}`, borderRadius: 16, padding: "14px 18px", marginBottom: 20, display: "flex", alignItems: "center", gap: 12 }}>
                <span style={{ flex: 1, fontSize: 14.5, color: t.text }}>Couldn't load your hire requests. Proposed terms may be waiting for you.</span>
                <button type="button" onClick={() => { setLoadState("loading"); refresh(); }} style={engBtn(t)}>Try again</button>
            </div>
        );
    }
    if (!visible.length && !ended.length && loadState !== "stale") return null;

    return (
        <div id="my-hire-requests" data-hire-requests style={{ scrollMarginTop: 16, background: t.card, border: `1.5px solid ${t.border}`, borderRadius: 16, padding: "14px 18px", marginBottom: 20 }}>
            {loadState === "stale" && (
                <div role="alert" data-hire-requests-stale style={{ fontSize: 13.5, color: t.warn, marginBottom: 8 }}>
                    Couldn't refresh your hire requests; this list may be out of date.{" "}
                    <button type="button" onClick={refresh} style={{ background: "none", border: 0, padding: 0, cursor: "pointer", color: t.primary, fontWeight: 700, fontSize: 13.5 }}>Try again</button>
                </div>
            )}
            <div style={{ fontSize: 12.5, fontWeight: 800, color: t.text, textTransform: "uppercase", letterSpacing: "0.8px", marginBottom: 10, display: "flex", alignItems: "center", gap: 8 }}>
                <Ic n="shield" s={14} c={t.primary} /> {caseId ? "Hire requests for this case" : "My Hire Requests"}
            </div>
            {visible.map(e => {
                const badge = ENG_BADGE[e.status];
                const focused = focusEngagementId && String(e.id) === String(focusEngagementId);
                return (
                    <div key={e.id} data-engagement={e.id} data-focused={focused ? "" : undefined}
                        style={{ display: "flex", alignItems: "center", gap: 12, padding: focused ? "8px 10px" : "8px 0", borderBottom: `1px solid ${t.border}`,
                            ...(focused ? { borderRadius: 10, outline: `2px solid ${t.primary}`, outlineOffset: -2, background: `${t.primary}12` } : null) }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontSize: 14.5, fontWeight: 700, color: t.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                {e.lawyer_name || "Lawyer"} · {e.case_title || e.case_number}
                            </div>
                            <div style={{ fontSize: 13.5, color: t.textMuted }}>
                                {e.status === "accepted"
                                    ? `Engaged${feeLabel(e) ? ` — ${feeLabel(e)}` : ""}.`
                                    : e.status === "terms_proposed"
                                        ? `${e.lawyer_name || "The lawyer"} proposed ${feeLabel(e) || "terms"}. Nothing is agreed until you accept.`
                                        : "Waiting for the lawyer to respond…"}
                            </div>
                            {e.status === "terms_proposed" && e.scope_note && (
                                <div style={{ fontSize: 13.5, color: t.textDim, marginTop: 4, fontStyle: "italic" }}>Scope: {e.scope_note}</div>
                            )}
                            {e.status === "accepted" && e.completion_proposed_by && (
                                <div style={{ fontSize: 13.5, color: t.primary, marginTop: 4 }}>
                                    {e.completion_proposed_by === "lawyer"
                                        ? "Your lawyer says the work is finished — confirm to close this engagement."
                                        : "You proposed completion; waiting for your lawyer to confirm."}
                                </div>
                            )}
                        </div>
                        <span data-eng-badge style={engChip(badge.color)}>{badge.label}</span>
                        {e.status === "requested" && (
                            <button onClick={() => withdrawRequest(e.id)} disabled={engBusy === e.id} style={engStop(t)}>Withdraw</button>
                        )}
                        {e.status === "terms_proposed" && (
                            <>
                                <button data-eng-decline onClick={() => declineTerms(e)} disabled={engBusy === e.id} style={engStop(t)}>Decline</button>
                                <button data-eng-accept onClick={() => acceptTerms(e)} disabled={engBusy === e.id} style={engGo(t)}>
                                    {engBusy === e.id ? "Accepting…" : "Accept terms"}
                                </button>
                            </>
                        )}
                        {e.status === "accepted" && (
                            <>
                                <button onClick={() => markComplete(e)} disabled={engBusy === e.id} style={engBtn(t)}>
                                    {e.completion_proposed_by === "lawyer" ? "Confirm complete" : "Mark complete"}
                                </button>
                                <button onClick={() => endEngagement(e)} disabled={engBusy === e.id} style={engStop(t)}>
                                    End engagement
                                </button>
                            </>
                        )}
                    </div>
                );
            })}
            {ended.length > 0 && (
                <div data-ended-engagements style={{ marginTop: visible.length ? 12 : 0 }}>
                    <div style={{ fontSize: 12.5, fontWeight: 700, color: t.textMuted, textTransform: "uppercase", letterSpacing: "0.6px", margin: "4px 0 2px" }}>Past requests</div>
                    {ended.map(e => {
                        const badge = ENG_BADGE[e.status];
                        return (
                            <div key={e.id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 0", borderBottom: `1px solid ${t.border}` }}>
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <div style={{ fontSize: 13.5, fontWeight: 600, color: t.textDim, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                        {e.lawyer_name || "Lawyer"} · {e.case_title || e.case_number}
                                    </div>
                                    <div style={{ fontSize: 13.5, color: t.textMuted, overflowWrap: "anywhere" }}>{endedText(e)}</div>
                                </div>
                                <span style={{ fontSize: 13.5, fontWeight: 700, color: badge.color, background: `${badge.color}18`, borderRadius: 20, padding: "4px 12px", flexShrink: 0 }}>{badge.label}</span>
                            </div>
                        );
                    })}
                </div>
            )}
            {note && (
                <NoteDialog t={t} kind={note.kind} engagement={note.engagement} busy={engBusy === note.engagement.id}
                    onCancel={() => setNote(null)} onConfirm={runNote} />
            )}
        </div>
    );
}
