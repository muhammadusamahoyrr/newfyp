'use client';
/* AN APPOINTMENT'S OWN MESSAGE THREAD (2026-10-12), shared by the client's
 * Appointments page, the client's Tracking cards and the lawyer's appointment
 * details -- one hook, one component, so the three cannot drift.
 *
 * The SERVER decides whether the thread is open (`can_send`, `send_state`);
 * nothing here re-derives it from the appointment's status. Loading never
 * looks like an empty thread, a failed read offers Retry, a failed send never
 * shows a message as sent, and a lost reply is reconciled with the SAME
 * idempotency key (the server stores one message per key) before inviting
 * another send. Text is rendered by React, never as HTML. */
import { useCallback, useEffect, useRef, useState } from "react";
import { listAppointmentMessages, sendAppointmentMessage } from "@/lib/api.js";
import { formatPkt } from "@/lib/bookingTime.js";
import { onNotification } from "@/lib/notificationTarget.js";

export const MESSAGE_MAX = 2000;

const byTime = (a, b) => (a.created_at === b.created_at ? (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)
    : new Date(a.created_at) - new Date(b.created_at));
const merge = (prev, next) => {
    const map = new Map(prev.map(m => [m.id, m]));
    for (const m of next) map.set(m.id, m);
    return [...map.values()].sort(byTime);
};
const newKey = () => {
    try { if (globalThis.crypto?.randomUUID) return `msg-${globalThis.crypto.randomUUID()}`; } catch { /* no crypto */ }
    return `msg-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
};

export function useAppointmentThread(appointmentId, { enabled = true } = {}) {
    const [st, setSt] = useState({ status: "loading", items: [], nextCursor: null, olderLoaded: false,
        canSend: false, sendState: null, stale: false });
    const [sending, setSending] = useState(false);
    const [sendError, setSendError] = useState(null);
    const [olderBusy, setOlderBusy] = useState(false);
    const gen = useRef(0);
    const pending = useRef(null);     // { text, key }: the send a retry must repeat

    const load = useCallback(async () => {
        if (!appointmentId) return null;
        const mine = ++gen.current;
        let res;
        try { res = await listAppointmentMessages(appointmentId); } catch { res = null; }
        if (mine !== gen.current) return null;
        const data = res && !res.error ? res.data : null;
        if (!data || !Array.isArray(data.items)) {
            // Keep what was read; say it may be out of date. With nothing read, an error.
            setSt(s => (s.status === "ready" ? { ...s, stale: true } : { ...s, status: "error" }));
            return null;
        }
        setSt(s => ({
            status: "ready",
            items: merge(s.status === "ready" ? s.items : [], data.items),
            nextCursor: s.olderLoaded ? s.nextCursor : (data.next_cursor || null),
            olderLoaded: s.olderLoaded,
            canSend: Boolean(data.can_send),
            sendState: data.send_state || null,
            stale: false,
        }));
        return data;
    }, [appointmentId]);

    useEffect(() => {
        if (!enabled || !appointmentId) return undefined;
        setSt({ status: "loading", items: [], nextCursor: null, olderLoaded: false, canSend: false, sendState: null, stale: false });
        setSendError(null);
        pending.current = null;
        load();
        return () => { gen.current += 1; };
    }, [appointmentId, enabled, load]);

    // A message, or any change to THIS appointment, arriving live: read again.
    useEffect(() => {
        if (!enabled || !appointmentId) return undefined;
        return onNotification((n) => {
            const t = String(n.type || "");
            if (t.startsWith("appointment_") && n.payload?.appointment_id === appointmentId) load();
        });
    }, [appointmentId, enabled, load]);

    const loadOlder = useCallback(async () => {
        const cur = st.nextCursor;
        if (!cur || olderBusy) return;
        setOlderBusy(true);
        let res;
        try { res = await listAppointmentMessages(appointmentId, cur); } catch { res = null; }
        setOlderBusy(false);
        const data = res && !res.error ? res.data : null;
        if (!data || !Array.isArray(data.items)) { setSt(s => ({ ...s, stale: true })); return; }
        setSt(s => ({ ...s, items: merge(s.items, data.items), nextCursor: data.next_cursor || null, olderLoaded: true }));
    }, [appointmentId, st.nextCursor, olderBusy]);

    /** Resolves true once the server has the message (sent, or found stored). */
    const send = useCallback(async (raw) => {
        const text = String(raw || "").trim();
        if (!text) { setSendError("Write a message first."); return false; }
        if (text.length > MESSAGE_MAX) { setSendError(`A message can be at most ${MESSAGE_MAX} characters.`); return false; }
        if (sending) return false;
        // The same words after a lost reply keep their key: the server returns
        // the stored message instead of storing a second one.
        const key = pending.current && pending.current.text === text ? pending.current.key : newKey();
        pending.current = { text, key };
        setSending(true);
        setSendError(null);
        let res;
        try { res = await sendAppointmentMessage(appointmentId, { text, idempotency_key: key }); } catch { res = { error: { message: "" }, status: 0 }; }
        if (res && !res.error && res.data?.id) {
            pending.current = null;
            setSt(s => ({ ...s, items: merge(s.items, [res.data]) }));
            setSending(false);
            return true;
        }
        if (!res || res.status === 0) {
            // LOST REPLY: the server may have stored it. Read back and look for this key.
            const data = await load();
            setSending(false);
            if (data?.items?.some(m => m.from_me && m.client_key === key)) { pending.current = null; return true; }
            setSendError("We could not confirm your message was sent. Send again — it will not be sent twice.");
            return false;
        }
        // Refused: nothing was stored. A closed thread is re-read so the composer goes.
        pending.current = null;
        if (res.status === 409) await load();
        setSending(false);
        setSendError(res.error?.message || "Could not send your message. Please try again.");
        return false;
    }, [appointmentId, sending, load]);

    return { ...st, sending, sendError, olderBusy, load, loadOlder, send, clearSendError: () => setSendError(null) };
}

const when = (iso) => formatPkt(iso, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });

/**
 * `palette`: { text, muted, faint, border, surface, input, primary, onPrimary, danger, mine }.
 * `counterpart`: who the messages go to ("lawyer" / "client" or a name).
 */
/* `compact` (2026-10-19, the lawyer's floating chat window): the window shows
 * who it is with, so the heading is kept only for screen readers, and the
 * thread fills the window with the composer at the bottom. Off by default. */
export function AppointmentThread({ appointmentId, palette: p, counterpart = "them", title, onClose, autoFocus = true, compact = false, suggestions = null }) {
    const th = useAppointmentThread(appointmentId);
    const [draft, setDraft] = useState("");
    const box = useRef(null);
    const input = useRef(null);
    const heading = useRef(null);
    const listEnd = useRef(null);
    const focused = useRef(false);

    // Focus once, when the thread first shows: the composer if open, else the heading.
    useEffect(() => {
        if (!autoFocus || focused.current || th.status !== "ready") return;
        focused.current = true;
        try { (th.canSend ? input.current : heading.current)?.focus({ preventScroll: false }); } catch { /* not in a browser */ }
    }, [autoFocus, th.status, th.canSend]);
    // Keep the newest message in view without moving focus.
    useEffect(() => {
        try { listEnd.current?.scrollIntoView?.({ block: "nearest" }); } catch { /* not in a browser */ }
    }, [th.items.length]);

    const submit = async () => {
        if (await th.send(draft)) setDraft("");
    };
    // Compact: the one-line composer grows with the text, up to four lines.
    useEffect(() => {
        if (!compact || !input.current) return;
        const el = input.current;
        el.style.height = "auto";
        el.style.height = `${Math.min(el.scrollHeight, 104)}px`;
    }, [compact, draft]);
    const btn = (primary) => ({
        height: 38, padding: "0 16px", borderRadius: 999, fontFamily: "inherit", fontSize: 13.5, fontWeight: 700,
        cursor: "pointer", border: primary ? "none" : `1px solid ${p.border}`,
        background: primary ? p.primary : "transparent", color: primary ? (p.onPrimary || "#fff") : p.text,
    });

    return (
        <section ref={box} aria-label={title || "Messages"} data-appointment-thread={appointmentId}
            data-thread-state={th.status === "ready" ? (th.canSend ? "open" : th.sendState || "read_only") : th.status}
            style={{ display: "flex", flexDirection: "column", gap: 10, minWidth: 0, maxWidth: "100%", ...(compact ? { height: "100%" } : null) }}>
            <div style={compact ? { position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" } : { display: "flex", alignItems: "center", gap: 10 }}>
                <h3 ref={heading} tabIndex={-1} style={{ margin: 0, flex: 1, fontSize: 15.5, fontWeight: 800, color: p.text, outline: "none" }}>{title || "Messages"}</h3>
                {onClose && <button type="button" onClick={onClose} aria-label="Close messages" style={{ ...btn(false), height: 32, padding: "0 12px" }}>Close</button>}
            </div>

            {th.status === "loading" && <div role="status" style={{ fontSize: 13, color: p.muted, padding: "18px 0" }}>Loading messages…</div>}
            {th.status === "error" && (
                <div role="alert" style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13, color: p.danger }}>
                    <span style={{ flex: 1 }}>Could not load the messages.</span>
                    <button type="button" onClick={() => th.load()} style={btn(false)}>Retry</button>
                </div>
            )}

            {th.status === "ready" && (<>
                {th.stale && (
                    <div role="status" style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12.5, color: p.muted }}>
                        <span style={{ flex: 1 }}>Could not refresh — these messages may be out of date.</span>
                        <button type="button" onClick={() => th.load()} style={{ ...btn(false), height: 30 }}>Retry</button>
                    </div>
                )}
                {th.nextCursor && (
                    <button type="button" data-thread-older onClick={th.loadOlder} disabled={th.olderBusy} style={{ ...btn(false), alignSelf: "center", height: 32 }}>
                        {th.olderBusy ? "Loading…" : "Load older messages"}
                    </button>
                )}
                <ol aria-live="polite" aria-relevant="additions" data-thread-list
                    style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 8, overflowY: "auto",
                        ...(compact ? { flex: 1, minHeight: 0 } : { maxHeight: 360 }) }}>
                    {th.items.length === 0 && !compact && <li style={{ fontSize: 13, color: p.muted }}>No messages yet.</li>}
                    {th.items.length === 0 && compact && (
                        <li data-thread-empty style={{ margin: "auto 0", textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center", gap: 10, padding: "8px 4px" }}>
                            <span aria-hidden="true" style={{ fontSize: 26 }}>💬</span>
                            <span style={{ fontSize: 13.5, fontWeight: 700, color: p.text }}>Start the conversation with {counterpart}</span>
                            <span style={{ fontSize: 12.5, color: p.muted, lineHeight: 1.45 }}>Confirm details, ask for documents, or let them know if plans change.</span>
                            {th.canSend && suggestions?.length > 0 && (
                                <span style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: 6, marginTop: 4 }}>
                                    {suggestions.map(sug => (
                                        <button key={sug} type="button" data-thread-suggestion onClick={() => { setDraft(sug); input.current?.focus(); }}
                                            style={{ border: `1px solid ${p.border}`, background: "transparent", color: p.text, borderRadius: 999, padding: "6px 11px", fontFamily: "inherit", fontSize: 12.5, cursor: "pointer", textAlign: "left" }}>
                                            {sug}
                                        </button>
                                    ))}
                                </span>
                            )}
                        </li>
                    )}
                    {th.items.map(m => (
                        <li key={m.id} data-message={m.id} data-mine={m.from_me ? "" : undefined}
                            style={{ alignSelf: m.from_me ? "flex-end" : "flex-start", maxWidth: "min(88%, 520px)", minWidth: 0,
                                padding: "8px 12px", borderRadius: 12, background: m.from_me ? (p.mine || p.input) : p.input,
                                border: `1px solid ${p.border}` }}>
                            <div style={{ fontSize: 11.5, color: p.muted, marginBottom: 2 }}>
                                <b style={{ color: p.text }}>{m.from_me ? "You" : (m.sender_name || (m.sender_role === "lawyer" ? "Lawyer" : "Client"))}</b>
                                {" · "}<time dateTime={m.created_at}>{when(m.created_at)} PKT</time>
                            </div>
                            <div style={{ fontSize: 13.5, color: p.text, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{m.text}</div>
                        </li>
                    ))}
                    <li ref={listEnd} aria-hidden="true" style={{ height: 0 }} />
                </ol>

                {th.canSend && compact ? (
                    <div data-thread-compose style={{ display: "flex", alignItems: "flex-end", gap: 8, padding: 6, borderRadius: 16, border: `1px solid ${p.border}`, background: p.input }}>
                        <label htmlFor={`thread-input-${appointmentId}`} style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }}>
                            Message to {counterpart} (Enter to send, Shift+Enter for a new line)
                        </label>
                        <textarea id={`thread-input-${appointmentId}`} ref={input} rows={1} maxLength={MESSAGE_MAX} value={draft}
                            disabled={th.sending}
                            onChange={e => { setDraft(e.target.value); if (th.sendError) th.clearSendError(); }}
                            onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } }}
                            placeholder={`Message ${counterpart}…`}
                            style={{ flex: 1, minWidth: 0, boxSizing: "border-box", resize: "none", height: 36, maxHeight: 104, padding: "8px 8px", border: "none",
                                background: "transparent", color: p.text, fontFamily: "inherit", fontSize: 13.5, lineHeight: 1.45, outline: "none" }} />
                        <button type="button" data-thread-send onClick={submit} disabled={th.sending || !draft.trim()} aria-label="Send" title="Send (Enter)"
                            style={{ width: 36, height: 36, flex: "none", borderRadius: "50%", border: "none", display: "grid", placeItems: "center", cursor: "pointer",
                                background: p.primary, color: p.onPrimary || "#fff", opacity: th.sending || !draft.trim() ? 0.6 : 1,
                                boxShadow: draft.trim() ? "0 4px 14px rgba(47,111,237,.45)" : "none", transition: "opacity .15s, box-shadow .15s" }}>
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7" /></svg>
                        </button>
                    </div>
                ) : th.canSend ? (
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                        <label htmlFor={`thread-input-${appointmentId}`} style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }}>
                            Message to {counterpart}
                        </label>
                        <textarea id={`thread-input-${appointmentId}`} ref={input} rows={2} maxLength={MESSAGE_MAX} value={draft}
                            disabled={th.sending}
                            onChange={e => { setDraft(e.target.value); if (th.sendError) th.clearSendError(); }}
                            onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } }}
                            placeholder={`Write to ${counterpart}…`}
                            style={{ width: "100%", boxSizing: "border-box", resize: "vertical", minHeight: 56, padding: "10px 12px", borderRadius: 12,
                                border: `1px solid ${p.border}`, background: p.input, color: p.text, fontFamily: "inherit", fontSize: 13.5, outline: "none" }} />
                        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                            <span style={{ flex: 1, minWidth: 160, fontSize: 11.5, color: p.faint || p.muted }}>Enter to send · Shift+Enter for a new line</span>
                            <button type="button" data-thread-send onClick={submit} disabled={th.sending || !draft.trim()} style={{ ...btn(true), opacity: th.sending || !draft.trim() ? 0.6 : 1 }}>
                                {th.sending ? "Sending…" : "Send"}
                            </button>
                        </div>
                    </div>
                ) : (
                    <div data-thread-closed style={{ fontSize: 12.5, color: p.muted }}>
                        {th.sendState === "awaiting_confirmation"
                            ? "Messages open once this appointment is confirmed."
                            : "This conversation is read-only: the appointment has ended."}
                    </div>
                )}
                {th.sendError && <div role="alert" data-thread-error style={{ fontSize: 12.5, fontWeight: 600, color: p.danger }}>{th.sendError}</div>}
            </>)}
        </section>
    );
}
