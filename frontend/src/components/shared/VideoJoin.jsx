"use client";
/* In-app video for a confirmed video consultation (2026-10-19, Marhala 3).
 *
 * Shared by the client and the lawyer, so it takes its colours as props and
 * touches neither theme. It renders NOTHING unless the backend says in-app
 * video is set up (a Daily key exists) and this appointment qualifies, so the
 * paste-a-link path is untouched when video is off.
 *
 * The browser never sees the Daily key: Join asks the backend for a short-lived
 * token for this one room. The call runs in Daily Prebuilt through daily-js,
 * themed in the app's own colours (dark or light, as the app is); if daily-js
 * cannot load, the same room opens in a plain iframe instead. */
import { useEffect, useRef, useState } from "react";
import { checkVideoAttendance, getVideoConfig, getVideoStatus, joinVideo } from "@/lib/api.js";
import VideoCall, { __setCallLoader } from "./VideoCall.jsx";

/* Is in-app video set up? Asked once per page load and shared, so a list of
 * cards can word "Join video" vs "Add joining link" without a call per card. */
let configPromise = null;
export function useVideoConfigured() {
    const [on, setOn] = useState(false);
    useEffect(() => {
        let alive = true;
        if (!configPromise) {
            configPromise = getVideoConfig().then(({ data }) => Boolean(data?.configured)).catch(() => false);
        }
        configPromise.then(v => { if (alive) setOn(v); });
        return () => { alive = false; };
    }, []);
    return on;
}
export function __resetVideoConfig() { configPromise = null; }

/* The call itself is VideoCall (our own Meet-style screen on Daily's call
 * object). `__setDailyLoader` stays for tests: it swaps how daily-js loads. */
export function __setDailyLoader(fn) { __setCallLoader(fn); }

/* The app's palette in Daily's terms -- kept for anything that still themes
 * Daily Prebuilt (the iframe fallback cannot be themed). */
export function dailyTheme(dark) {
    return { colors: dark
        ? { accent: "#40F0DC", accentText: "#1A2E35", background: "#223A42", backgroundAccent: "#2A4750", baseText: "#F2F2EC", border: "#2C606E", mainAreaBg: "#1A2E35", mainAreaBgAccent: "#2A4750", mainAreaText: "#F2F2EC", supportiveText: "#9A9A94" }
        : { accent: "#1A3A42", accentText: "#FFFFFF", background: "#FFFFFF", backgroundAccent: "#EDF1F0", baseText: "#1A2E35", border: "#E3ECEA", mainAreaBg: "#F2F5F4", mainAreaBgAccent: "#EDF1F0", mainAreaText: "#1A2E35", supportiveText: "#6B7E84" } };
}

/* After the other person joins, and when the call closes, ask the server
 * whether Daily shows that both met (2026-10-21). Daily's report can trail a
 * few seconds behind, so one quiet retry. When it says yes, pages that offer
 * early completion ("It took place") re-read their list. */
export const VIDEO_MET_EVENT = "attorney:video-met";
function askAttendance(apptId, retry = true) {
    if (!apptId) return;
    checkVideoAttendance(apptId).then(({ data }) => {
        if (data?.video_met) {
            if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent(VIDEO_MET_EVENT, { detail: { appointment_id: apptId } }));
        } else if (retry) {
            setTimeout(() => askAttendance(apptId, false), 8000);
        }
    }).catch(() => { /* best effort: the server re-checks on completion */ });
}

export default function VideoJoin({ apptId, status, mode, accent = "#13806b", muted = "#6b7280", danger = "#b42318", dark = true,
                                    big = false, onBeforeJoin = null, otherName = "your client", onOpenChat = null,
                                    onPreJoin = null }) {
    const eligible = status === "confirmed" && mode === "video" && Boolean(apptId);
    const [info, setInfo] = useState(null);
    const [now, setNow] = useState(() => Date.now());
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);
    const [call, setCall] = useState(null);

    useEffect(() => {
        if (!eligible) return undefined;
        let alive = true;
        getVideoStatus(apptId).then(({ data }) => { if (alive) setInfo(data || null); });
        return () => { alive = false; };
    }, [apptId, eligible]);
    useEffect(() => {
        if (!info?.configured) return undefined;
        const id = setInterval(() => setNow(Date.now()), 30000);
        return () => clearInterval(id);
    }, [info?.configured]);
    useEffect(() => {
        if (!call) return undefined;
        const esc = (e) => { if (e.key === "Escape") setCall(null); };
        window.addEventListener("keydown", esc);
        return () => window.removeEventListener("keydown", esc);
    }, [call]);

    if (!eligible || !info?.configured || !info.eligible) return null;
    const opens = Date.parse(info.opens_at);
    const closes = Date.parse(info.closes_at);
    const open = now >= opens && now <= closes;
    if (now > closes) return null;

    const join = async () => {
        // A join screen first (camera check, options), when the page has one.
        if (onPreJoin) { onPreJoin(); return; }
        try { onBeforeJoin?.(); } catch { /* the preview's own cleanup */ }
        setBusy(true); setError(null);
        const { data, error: err } = await joinVideo(apptId);
        setBusy(false);
        if (err || !data?.token) { setError(err?.message || "Could not open the video. Use the meeting link instead."); return; }
        setCall(data);
    };

    return (
        <div data-video-join style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {big ? (
                <>
                    <button type="button" data-video-join-btn onClick={join} disabled={!open || busy}
                        title={open ? "Join the video call in the app" : "Opens a day before the start"}
                        style={{ width: "100%", height: 46, borderRadius: 12, border: "none", cursor: open && !busy ? "pointer" : "not-allowed",
                            display: "flex", alignItems: "center", justifyContent: "center", gap: 9, fontFamily: "inherit", fontSize: 15, fontWeight: 800,
                            color: open ? "#fff" : muted, opacity: busy ? .75 : 1,
                            background: open ? `linear-gradient(135deg, ${accent} 0%, #1c9c66 100%)` : "rgba(127,127,127,.12)",
                            boxShadow: open ? "0 10px 26px -10px rgba(28,156,102,.65)" : "inset 0 0 0 1px rgba(127,127,127,.4)" }}>
                        <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="2.5" y="6" width="13" height="12" rx="2.5" /><path d="M15.5 10.5l6-3.5v10l-6-3.5z" /></svg>
                        {busy ? "Opening…" : "Join in-app video"}
                    </button>
                    <span style={{ fontSize: 12.5, color: muted, textAlign: "center" }}>
                        {open ? `Private room · not recorded · only you and ${otherName}` : `Opens ${new Date(opens).toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" })} — a day before the start`}
                    </span>
                </>
            ) : (
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                <button type="button" data-video-join-btn onClick={join} disabled={!open || busy}
                    title={open ? "Join the video call in the app" : "Opens a day before the start"}
                    style={{ height: 40, padding: "0 18px", borderRadius: 999, border: "none", cursor: open && !busy ? "pointer" : "not-allowed",
                        // Disabled still reads as a button: a grey pill with an outline
                        // (works with hex and CSS-variable colours alike).
                        background: open ? accent : "rgba(127,127,127,.12)", color: open ? "#fff" : muted, fontWeight: 700, fontSize: 13.5,
                        boxShadow: open ? "none" : "inset 0 0 0 1px rgba(127,127,127,.4)", opacity: busy ? .7 : 1, fontFamily: "inherit" }}>
                    {busy ? "Opening…" : "Join in-app video"}
                </button>
                <span style={{ fontSize: 12.5, color: muted }}>
                    {open ? "Private room · not recorded" : `Opens ${new Date(opens).toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" })} — a day before the start`}
                </span>
            </div>
            )}
            {error && <div role="alert" style={{ fontSize: 12.5, color: danger }}>{error}</div>}
            {/* On <body>: inside a dialog (transformed) a fixed overlay would
                be pinned to the dialog, not cover the whole page. */}
            {call && <VideoCall call={call} otherName={otherName} onOpenChat={onOpenChat}
                onPeerJoined={() => askAttendance(apptId)}
                onClose={() => { setCall(null); askAttendance(apptId); }} />}
        </div>
    );
}
