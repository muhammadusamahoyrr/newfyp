'use client';
/* Hiring the lawyer from a finished consultation, on the Appointments page
 * (2026-10-20). "Request to hire", "View request" and "Review terms" used to
 * send the client to the Lawyers page; the same steps now open here, through
 * the same API and the same rules:
 *
 *   request  the consultation is THIS one (fixed); the case is one the client
 *            can still send (a consultation booked for a case allows only
 *            that case), an intake draft (confirmed on send), or a new matter
 *            described in a few fields. POST /engagements.
 *   sent     where the request stands; the client may withdraw it.
 *   terms    the lawyer's fee, fee type and scope; Accept, or Decline with an
 *            optional reason.
 *
 * Errors are said inside the dialog. A failed read of the cases is not shown
 * as "no case". */
import { useCallback, useEffect, useRef, useState } from "react";
import { ModalPortal, BACKDROP } from "@/components/client/documents/ui.jsx";
import {
    listCases, listEngagements, requestEngagement, createCase, confirmCase,
    cancelEngagement, acceptEngagementTerms, declineEngagementTerms,
} from "@/lib/api.js";
import { listAllCases } from "@/lib/allCases.js";
import { hireableCases, isDraftCase } from "@/lib/caseStatus.js";
import { formatPkt } from "@/lib/bookingTime.js";

const NEW_MATTER = "__new__";
const OPEN = new Set(["requested", "terms_proposed"]);
const TYPES = [["civil", "Civil"], ["family", "Family"], ["criminal", "Criminal"], ["constitutional", "Constitutional"]];
const PROVINCES = [["punjab", "Punjab"], ["sindh", "Sindh"], ["kpk", "KPK"], ["balochistan", "Balochistan"], ["federal", "Islamabad (Federal)"]];
const FEE_TYPE = { fixed: "Fixed fee (whole case)", hourly: "Per hour", per_hearing: "Per hearing (peshi)" };

export default function HireDialog({ appt, engagement = null, t, onClose, onChanged = null }) {
    const lawyer = appt.lawyer_name || "your lawyer";
    const first = String(lawyer).split(" ")[0];
    const mode = !engagement ? "request" : engagement.status === "terms_proposed" ? "terms" : engagement.status === "requested" ? "sent" : "closed";
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);
    const [done, setDone] = useState(null);           // the success sentence
    const panel = useRef(null);

    // ── request: the client's cases ──
    const [cases, setCases] = useState({ state: mode === "request" ? "loading" : "idle", options: [], drafts: [] });
    const [caseId, setCaseId] = useState("");
    const [message, setMessage] = useState("");
    const [matter, setMatter] = useState({ title: "", case_type: "", province: "", description: "" });
    const loadCases = useCallback(async () => {
        setCases(c => ({ ...c, state: "loading" }));
        const [cs, es] = await Promise.all([listAllCases(listCases), listEngagements()]);
        if (cs?.error || !Array.isArray(cs?.data?.items) || es?.error || !Array.isArray(es?.data)) { setCases({ state: "error", options: [], drafts: [] }); return; }
        const all = cs.data.items;
        const open = {};
        es.data.filter(e => OPEN.has(e.status)).forEach(e => { open[e.case_id] = e; });
        let options = hireableCases(all, open);
        if (appt.case_id) options = options.filter(c => (c._id || c.id) === appt.case_id);
        const drafts = appt.case_id ? [] : all.filter(c => (c._id || c.id) && isDraftCase(c) && !c.lawyer_id);
        setCases({ state: "ready", options, drafts });
        setCaseId(options[0] ? (options[0]._id || options[0].id) : drafts[0] ? `draft:${drafts[0]._id || drafts[0].id}` : appt.case_id ? "" : NEW_MATTER);
    }, [appt.case_id]);
    useEffect(() => { if (mode === "request") loadCases(); }, [mode, loadCases]);

    // ── decline / withdraw ──
    const [confirming, setConfirming] = useState(null);   // "withdraw" | "decline"
    const [reason, setReason] = useState("");

    useEffect(() => {
        panel.current?.focus();
        const esc = (e) => { if (e.key === "Escape" && !busy) onClose(); };
        window.addEventListener("keydown", esc);
        return () => window.removeEventListener("keydown", esc);
    }, [busy, onClose]);

    const finish = (sentence) => { setDone(sentence); onChanged?.(); };

    const sendRequest = async () => {
        if (busy) return;
        setError(null);
        if (!caseId) { setError("Choose the case you want " + first + " to handle."); return; }
        let id = caseId;
        setBusy(true);
        if (id === NEW_MATTER) {
            const m = { title: matter.title.trim(), description: matter.description.trim(), case_type: matter.case_type, province: matter.province };
            const bad = m.title.length < 3 ? "Give the matter a short title."
                : !m.case_type ? "Choose the area of law."
                : !m.province ? "Choose the province."
                : m.description.length < 10 ? "Describe the matter in a sentence or two." : null;
            if (bad) { setBusy(false); setError(bad); return; }
            const { data, error: e } = await createCase(m);
            if (e || !(data?._id || data?.id)) { setBusy(false); setError(e?.message || "Could not create the matter. Try again."); return; }
            id = data._id || data.id;
            setCaseId(id);          // a retry reuses this matter instead of making another
        } else if (id.startsWith("draft:")) {
            id = id.slice(6);
            const { error: e } = await confirmCase(id);
            if (e) { setBusy(false); setError(e.message || "Could not confirm the case. Try again."); return; }
            setCaseId(id);
        }
        const { error: e } = await requestEngagement({ case_id: id, lawyer_id: appt.lawyer_id, appointment_id: appt.id, message: message.trim() || null });
        setBusy(false);
        if (e) { setError(e.message || "Could not send the request. Try again."); return; }
        finish(`Request sent to ${lawyer}. They will send their fee and scope; you'll be notified.`);
    };

    const withdraw = async () => {
        setBusy(true); setError(null);
        const { error: e } = await cancelEngagement(engagement.id);
        setBusy(false);
        if (e) { setError(e.message || "Could not withdraw the request."); return; }
        finish("Request withdrawn. This consultation was used for it; book a follow-up to ask again.");
    };
    const accept = async () => {
        setBusy(true); setError(null);
        const { error: e } = await acceptEngagementTerms(engagement.id);
        setBusy(false);
        if (e) { setError(e.message || "Could not accept the terms."); return; }
        finish(`${lawyer} is now engaged on your case. You'll find it under Tracking.`);
    };
    const decline = async () => {
        setBusy(true); setError(null);
        const { error: e } = await declineEngagementTerms(engagement.id, reason.trim() || null);
        setBusy(false);
        if (e) { setError(e.message || "Could not decline the terms."); return; }
        finish("Terms declined. Your case is open again — you can approach another lawyer.");
    };

    // ── look ──
    const btn = (kind = "ghost") => ({
        height: 44, padding: "0 20px", borderRadius: 12, fontFamily: "inherit", fontSize: 14, fontWeight: 700, cursor: busy ? "default" : "pointer",
        opacity: busy ? .7 : 1,
        border: kind === "prim" ? "none" : `1px solid ${kind === "danger" ? (t.danger || "#e8526a") : t.border}`,
        background: kind === "prim" ? t.primary : "transparent",
        color: kind === "prim" ? "#06211a" : kind === "danger" ? (t.danger || "#e8526a") : t.text,
    });
    const field = { width: "100%", boxSizing: "border-box", borderRadius: 12, border: `1px solid ${t.border}`, background: t.inputBg, color: t.text, fontSize: 14, fontFamily: "inherit", outline: "none", padding: "10px 12px" };
    const lbl = (text, extra = null) => (
        <div style={{ fontSize: 12, fontWeight: 800, letterSpacing: ".06em", textTransform: "uppercase", color: t.textMuted, marginBottom: 7 }}>
            {text}{extra && <span style={{ textTransform: "none", letterSpacing: 0, fontWeight: 500 }}> {extra}</span>}
        </div>
    );
    const row = (k, v) => (
        <div style={{ display: "flex", justifyContent: "space-between", gap: 14, padding: "9px 0", borderTop: `1px solid ${t.border}`, fontSize: 14 }}>
            <span style={{ color: t.textMuted }}>{k}</span><b style={{ color: t.text, textAlign: "right" }}>{v}</b>
        </div>
    );
    const when = formatPkt(appt.scheduled_at, { weekday: "short", day: "numeric", month: "short" });

    let title, sub, body;
    if (done) {
        title = mode === "request" ? "Request sent" : mode === "terms" ? (done.startsWith("Terms declined") ? "Terms declined" : "You're engaged") : "Request withdrawn";
        sub = null;
        body = (<>
            <div data-hire-done style={{ fontSize: 14.5, color: t.text, lineHeight: 1.55 }}>{done}</div>
            <div style={{ display: "flex", justifyContent: "flex-end" }}><button type="button" style={btn("prim")} onClick={onClose}>Done</button></div>
        </>);
    } else if (mode === "request") {
        title = `Request to hire ${lawyer}`;
        sub = `After your consultation on ${when}. ${first} reviews your case and sends a fee and scope — nothing is agreed until you accept.`;
        body = cases.state === "loading" ? <div style={{ fontSize: 14, color: t.textMuted }}>Loading your cases…</div>
            : cases.state === "error" ? (
                <div role="alert" style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 14, color: t.textMuted }}>
                    <span style={{ flex: 1 }}>Could not load your cases. This is not the same as having none.</span>
                    <button type="button" style={{ ...btn(), flex: "none" }} onClick={loadCases}>Retry</button>
                </div>
            ) : (<>
                <div>
                    {lbl("Case")}
                    {!cases.options.length && !cases.drafts.length && appt.case_id ? (
                        <div style={{ fontSize: 14, color: t.textMuted }}>The case this consultation was booked for can't be sent to a lawyer now (it may already have one, or a request is open).</div>
                    ) : (
                        <select value={caseId} onChange={e => { setCaseId(e.target.value); setError(null); }} data-hire-case style={{ ...field, height: 46 }}>
                            {cases.options.map(c => <option key={c._id || c.id} value={c._id || c.id}>{c.title || "Untitled case"}{c.case_number ? ` · ${c.case_number}` : ""}</option>)}
                            {cases.drafts.map(c => <option key={c._id || c.id} value={`draft:${c._id || c.id}`}>{c.title || "Draft"} — draft, confirmed when sent</option>)}
                            {!appt.case_id && <option value={NEW_MATTER}>＋ Describe a new matter</option>}
                        </select>
                    )}
                </div>
                {caseId === NEW_MATTER && (
                    <div data-hire-new-matter style={{ display: "grid", gap: 10 }}>
                        <input placeholder="Short title, e.g. Land sold without consent" value={matter.title} maxLength={160}
                            onChange={e => setMatter(m => ({ ...m, title: e.target.value }))} style={{ ...field, height: 44 }} />
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                            <select value={matter.case_type} onChange={e => setMatter(m => ({ ...m, case_type: e.target.value }))} style={{ ...field, height: 44 }}>
                                <option value="">Area of law…</option>{TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                            </select>
                            <select value={matter.province} onChange={e => setMatter(m => ({ ...m, province: e.target.value }))} style={{ ...field, height: 44 }}>
                                <option value="">Province…</option>{PROVINCES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                            </select>
                        </div>
                        <textarea rows={3} placeholder="Describe the matter in a sentence or two." value={matter.description} maxLength={2000}
                            onChange={e => setMatter(m => ({ ...m, description: e.target.value }))} style={{ ...field, resize: "vertical" }} />
                    </div>
                )}
                <div>
                    {lbl("Message to " + first, "(optional)")}
                    <textarea rows={3} maxLength={1000} value={message} onChange={e => setMessage(e.target.value)}
                        placeholder="What you need help with, how urgent it is, anything they should know…" style={{ ...field, resize: "vertical" }} />
                </div>
                {error && <div role="alert" data-hire-error style={{ fontSize: 13, fontWeight: 600, color: t.danger || "#e8526a" }}>{error}</div>}
                <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
                    <button type="button" style={btn()} onClick={onClose} disabled={busy}>Cancel</button>
                    <button type="button" data-hire-send style={btn("prim")} onClick={sendRequest} disabled={busy || (appt.case_id && !caseId)}>
                        {busy ? "Sending…" : "Send hire request"}
                    </button>
                </div>
            </>);
    } else if (mode === "sent") {
        title = "Hire request sent";
        sub = `Waiting for ${first} to send their fee and scope. You'll be notified.`;
        body = (<>
            <div>
                {row("Lawyer", lawyer)}
                {row("Case", engagement.case_title || "Your case")}
                {row("After consultation on", when)}
                {engagement.created_at && row("Sent", formatPkt(engagement.created_at, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }))}
            </div>
            {engagement.message && <div style={{ fontSize: 13.5, color: t.textMuted, fontStyle: "italic" }}>“{engagement.message}”</div>}
            {error && <div role="alert" data-hire-error style={{ fontSize: 13, fontWeight: 600, color: t.danger || "#e8526a" }}>{error}</div>}
            {confirming === "withdraw" ? (
                <div style={{ display: "flex", alignItems: "center", gap: 10, justifyContent: "flex-end", flexWrap: "wrap" }}>
                    <span style={{ fontSize: 13.5, color: t.text, marginRight: "auto" }}>Withdraw this request? This consultation can't be used again for a new one.</span>
                    <button type="button" style={btn()} onClick={() => setConfirming(null)} disabled={busy}>Keep it</button>
                    <button type="button" data-hire-withdraw-confirm style={btn("danger")} onClick={withdraw} disabled={busy}>{busy ? "Withdrawing…" : "Withdraw"}</button>
                </div>
            ) : (
                <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
                    <button type="button" data-hire-withdraw style={btn("danger")} onClick={() => setConfirming("withdraw")}>Withdraw request</button>
                    <button type="button" style={btn("prim")} onClick={onClose}>Close</button>
                </div>
            )}
        </>);
    } else if (mode === "terms") {
        const fee = engagement.fee_amount != null ? `Rs ${Number(engagement.fee_amount).toLocaleString("en-PK")}` : "—";
        title = `${first} sent you terms`;
        sub = "Accept to engage them on your case, or decline. Nothing is agreed until you accept.";
        body = (<>
            <div style={{ padding: "16px 18px", borderRadius: 14, background: t.inputBg, border: `1px solid ${t.border}` }}>
                <div style={{ fontSize: 12, fontWeight: 800, letterSpacing: ".06em", textTransform: "uppercase", color: t.textMuted }}>Proposed fee</div>
                <div data-hire-fee style={{ fontSize: 28, fontWeight: 800, color: t.text, marginTop: 2 }}>{fee}</div>
                <div style={{ fontSize: 13.5, color: t.textMuted }}>{FEE_TYPE[engagement.fee_type] || engagement.fee_type || ""}</div>
            </div>
            <div>
                {row("Case", engagement.case_title || "Your case")}
                {row("Lawyer", lawyer)}
            </div>
            {engagement.scope_note && (
                <div>
                    {lbl("What it covers")}
                    <div style={{ fontSize: 14, color: t.text, lineHeight: 1.55, whiteSpace: "pre-wrap" }}>{engagement.scope_note}</div>
                </div>
            )}
            {error && <div role="alert" data-hire-error style={{ fontSize: 13, fontWeight: 600, color: t.danger || "#e8526a" }}>{error}</div>}
            {confirming === "decline" ? (
                <div style={{ display: "grid", gap: 10 }}>
                    {lbl("Why don't these terms work?", "(optional — shown to " + first + ")")}
                    <textarea rows={3} maxLength={1000} value={reason} onChange={e => setReason(e.target.value)} style={{ ...field, resize: "vertical" }} />
                    <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
                        <button type="button" style={btn()} onClick={() => setConfirming(null)} disabled={busy}>Back</button>
                        <button type="button" data-hire-decline-confirm style={btn("danger")} onClick={decline} disabled={busy}>{busy ? "Declining…" : "Decline terms"}</button>
                    </div>
                </div>
            ) : (
                <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
                    <button type="button" data-hire-decline style={btn("danger")} onClick={() => setConfirming("decline")} disabled={busy}>Decline</button>
                    <button type="button" data-hire-accept style={btn("prim")} onClick={accept} disabled={busy}>{busy ? "Accepting…" : `Accept and engage ${first}`}</button>
                </div>
            )}
        </>);
    } else {
        title = "Hire request closed";
        sub = null;
        body = (<>
            <div style={{ fontSize: 14, color: t.textMuted }}>It was {String(engagement.status).replace(/_/g, " ")}. Book a follow-up with {first} to ask again.</div>
            <div style={{ display: "flex", justifyContent: "flex-end" }}><button type="button" style={btn("prim")} onClick={onClose}>Close</button></div>
        </>);
    }

    return (
        <ModalPortal>
            <div data-lenis-prevent style={{ ...BACKDROP, display: "grid", placeItems: "center", padding: 20 }}
                onClick={() => { if (!busy) onClose(); }}>
                <div ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title} data-hire-dialog={done ? "done" : mode}
                    onClick={e => e.stopPropagation()}
                    style={{ width: "min(560px, 100%)", maxHeight: "92vh", overflowY: "auto", overscrollBehavior: "contain", borderRadius: 20, background: t.card,
                        border: `1px solid ${t.border}`, boxShadow: "0 30px 80px rgba(0,0,0,.45)", padding: "24px 26px",
                        display: "flex", flexDirection: "column", gap: 16, outline: "none", color: t.text }}>
                    <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontSize: 22, fontWeight: 800, color: t.text }}>{title}</div>
                            {sub && <div style={{ fontSize: 13, color: t.textMuted, marginTop: 4, lineHeight: 1.5 }}>{sub}</div>}
                        </div>
                        <button type="button" aria-label="Close" onClick={onClose} disabled={busy}
                            style={{ background: "none", border: "none", color: t.textMuted, fontSize: 18, cursor: "pointer", padding: 4 }}>✕</button>
                    </div>
                    {body}
                </div>
            </div>
        </ModalPortal>
    );
}
