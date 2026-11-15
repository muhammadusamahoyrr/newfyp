'use client';
/* The join screen for an in-app video consultation (2026-10-20), shared by the
 * lawyer and the client (each side passes what it can do: message, links).
 *
 * Opened from "Join video". The page behind is blurred; the screen has two
 * halves:
 *   LEFT   a camera & microphone check. Nothing is switched on until the
 *          lawyer asks ("Check camera & mic"): a laptop camera that lights up
 *          by itself is a surprise nobody wants. The preview is stopped the
 *          moment the lawyer joins (a camera can be held by one user only) or
 *          leaves this screen.
 *   RIGHT  who and when, the big Join button, and the other things a lawyer
 *          does just before a call: message the client, copy the details, or
 *          use their own meeting link instead.
 * Join itself is VideoJoin: the server still decides whether the room opens. */
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { PREJOIN_TOKENS_CSS } from "./prejoinTheme.js";
import VideoJoin from "@/components/shared/VideoJoin.jsx";

const CSS = `[data-prejoin-backdrop]{position:fixed;inset:0;z-index:1000;display:grid;place-items:center;padding:20px;font-family:"Hanken Grotesk",system-ui,sans-serif;background:rgba(6,14,16,.55);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);animation:pjFade .18s ease}
@keyframes pjFade{from{opacity:0}to{opacity:1}}
@keyframes pjRise{from{transform:translateY(10px);opacity:.6}to{transform:none;opacity:1}}
[data-prejoin]{width:min(980px,100%);max-height:calc(100vh - 40px);overflow:auto;display:grid;grid-template-columns:1fr 1fr;border-radius:22px;background:var(--surface);color:var(--ink);border:1px solid var(--line-strong);box-shadow:0 30px 80px -24px rgba(0,0,0,.7);animation:pjRise .2s ease}
[data-prejoin] .pj-left{padding:24px;background:var(--surface-2);border-right:1px solid var(--line);display:flex;flex-direction:column;gap:14px}
[data-prejoin] .pj-right{padding:24px 26px;display:flex;flex-direction:column;gap:14px}
[data-prejoin] .pj-stage{position:relative;aspect-ratio:16/9;border-radius:16px;overflow:hidden;background:radial-gradient(120% 120% at 50% 0%,#1d3a40 0%,#0c1a1d 70%);display:grid;place-items:center}
[data-prejoin] .pj-stage video{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;transform:scaleX(-1)}
[data-prejoin] .pj-off{display:flex;flex-direction:column;align-items:center;gap:10px;color:#cfe3e0;text-align:center;padding:16px;font-size:13px}
[data-prejoin] .pj-off .av{width:64px;height:64px;border-radius:50%;display:grid;place-items:center;font-weight:800;font-size:20px;color:#fff;background:linear-gradient(135deg,#12897f,#1c9c66)}
[data-prejoin] .pj-ctl{display:flex;gap:10px;justify-content:center}
[data-prejoin] .pj-round{width:44px;height:44px;border-radius:50%;display:grid;place-items:center;border:1px solid var(--line-strong);background:var(--surface);color:var(--ink);cursor:pointer}
[data-prejoin] .pj-round.off{background:#e5484d;border-color:#e5484d;color:#fff}
[data-prejoin] .pj-round:disabled{opacity:.45;cursor:not-allowed}
[data-prejoin] .pj-meter{height:6px;border-radius:999px;background:var(--line);overflow:hidden}
[data-prejoin] .pj-meter i{display:block;height:100%;background:linear-gradient(90deg,#1c9c66,#40f0dc);transition:width .08s linear}
[data-prejoin] .pj-btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;height:40px;padding:0 14px;border-radius:12px;border:1px solid var(--line-strong);background:transparent;color:var(--ink);font:inherit;font-size:13px;font-weight:700;cursor:pointer}
[data-prejoin] .pj-btn:hover{border-color:var(--hover-line)}
[data-prejoin] .pj-opts{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
[data-prejoin] .pj-opt{display:flex;flex-direction:column;align-items:center;gap:5px;padding:10px 6px;border-radius:14px;border:1px solid var(--line);background:var(--surface-2);color:var(--ink);font:inherit;font-size:12.5px;font-weight:700;cursor:pointer;text-align:center}
[data-prejoin] .pj-opt:hover{border-color:var(--hover-line)}
[data-prejoin] .pj-opt svg{color:#40f0dc}
[data-prejoin] .pj-x{width:36px;height:36px;border-radius:10px;border:1px solid var(--line);background:transparent;color:var(--muted);cursor:pointer;display:grid;place-items:center;font-size:15px}
[data-prejoin] .pj-when{display:inline-flex;align-items:center;gap:7px;height:30px;padding:0 12px;border-radius:999px;font-size:12.5px;font-weight:700;color:#3ec99a;background:rgba(62,201,154,.12);border:1px solid rgba(62,201,154,.35)}
[data-prejoin] .pj-when i{width:7px;height:7px;border-radius:50%;background:currentColor}
[data-prejoin] .pj-facts{display:grid;grid-template-columns:auto 1fr;gap:8px 14px;font-size:13.5px;margin:0}
[data-prejoin] .pj-facts dt{color:var(--muted)}
[data-prejoin] .pj-facts dd{margin:0;font-weight:700}
[data-prejoin] .pj-link input{flex:1;min-width:0;box-sizing:border-box;height:40px;padding:0 12px;border-radius:12px;border:1px solid var(--line-strong);background:var(--input);color:var(--ink);font:inherit;font-size:13.5px}
@media (max-width:760px){[data-prejoin]{grid-template-columns:1fr}[data-prejoin] .pj-left{border-right:none;border-bottom:1px solid var(--line)}}`;

const svg = (d, size = 20) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{d}</svg>
);
const ICON = {
    cam: svg(<><rect x="2.5" y="6" width="13" height="12" rx="2.5" /><path d="M15.5 10.5l6-3.5v10l-6-3.5z" /></>),
    camOff: svg(<><path d="M2 2l20 20" /><path d="M15.5 10.5l6-3.5v10l-3-1.75M10 6h3a2.5 2.5 0 012.5 2.5v3M15.5 16v-.5a2.5 2.5 0 01-2.5 2.5H5a2.5 2.5 0 01-2.5-2.5v-7A2.5 2.5 0 015 6" /></>),
    mic: svg(<><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0014 0M12 18v3" /></>),
    micOff: svg(<><path d="M2 2l20 20" /><path d="M9 9v2a3 3 0 005 2.2M15 9.3V6a3 3 0 00-5.7-1.3M5 11a7 7 0 0011.4 5.4M19 11a7 7 0 01-.4 2.3M12 18v3" /></>),
    chat: svg(<path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />),
    copy: svg(<><rect x="9" y="9" width="12" height="12" rx="2" /><path d="M5 15V5a2 2 0 012-2h10" /></>),
    link: svg(<><path d="M10 13a5 5 0 007.5.5l3-3a5 5 0 00-7-7l-1.5 1.5" /><path d="M14 11a5 5 0 00-7.5-.5l-3 3a5 5 0 007 7l1.5-1.5" /></>),
};

/** A local camera + mic preview, off until asked for. */
function useDevicePreview() {
    const [state, setState] = useState("idle");      // idle | starting | on | blocked | none
    const [cam, setCam] = useState(true);
    const [mic, setMic] = useState(true);
    const [level, setLevel] = useState(0);
    const stream = useRef(null);
    const audio = useRef(null);
    const raf = useRef(0);
    const videoRef = useRef(null);

    const stop = useCallback(() => {
        cancelAnimationFrame(raf.current);
        stream.current?.getTracks().forEach(t => t.stop());
        stream.current = null;
        try { audio.current?.close(); } catch { /* already closed */ }
        audio.current = null;
        setLevel(0);
        setState(s => (s === "on" || s === "starting" ? "idle" : s));
    }, []);

    const start = useCallback(async () => {
        if (!navigator.mediaDevices?.getUserMedia) { setState("none"); return; }
        setState("starting");
        try {
            const s = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
            stream.current = s;
            if (videoRef.current) videoRef.current.srcObject = s;
            setCam(true); setMic(true);
            setState("on");
            const Ctx = window.AudioContext || window.webkitAudioContext;
            if (Ctx && s.getAudioTracks().length) {
                const ctx = new Ctx();
                audio.current = ctx;
                const an = ctx.createAnalyser();
                an.fftSize = 256;
                ctx.createMediaStreamSource(s).connect(an);
                const buf = new Uint8Array(an.frequencyBinCount);
                const tick = () => {
                    an.getByteTimeDomainData(buf);
                    let peak = 0;
                    for (const v of buf) peak = Math.max(peak, Math.abs(v - 128));
                    setLevel(Math.min(1, peak / 64));
                    raf.current = requestAnimationFrame(tick);
                };
                tick();
            }
        } catch (e) {
            setState(e?.name === "NotFoundError" ? "none" : "blocked");
        }
    }, []);

    const toggle = (kind) => {
        const tracks = kind === "cam" ? stream.current?.getVideoTracks() : stream.current?.getAudioTracks();
        const next = !(kind === "cam" ? cam : mic);
        tracks?.forEach(t => { t.enabled = next; });
        (kind === "cam" ? setCam : setMic)(next);
    };

    useEffect(() => () => stop(), [stop]);
    useEffect(() => { if (state === "on" && videoRef.current && stream.current) videoRef.current.srcObject = stream.current; }, [state]);
    return { state, cam, mic, level, start, stop, toggle, videoRef };
}

/* onMessage: open the conversation (null = no button). onOpenChatInCall: the
 * call's Messages button. onSaveLink: the lawyer may set their own link (null =
 * the client, who can only open a link the lawyer gave). */
export function PreJoinModal({ apt, day, span, when, live, dark, onClose, onSaveLink = null, onMessage = null, onOpenChatInCall = null }) {
    const dev = useDevicePreview();
    const [copied, setCopied] = useState(false);
    const [linkOpen, setLinkOpen] = useState(false);
    const [link, setLink] = useState(apt.meetingLink || "");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);
    const panel = useRef(null);
    const first = String(apt.client || "the client").split(" ")[0];

    const stopPreview = dev.stop;
    const close = useCallback(() => { stopPreview(); onClose(); }, [stopPreview, onClose]);
    useEffect(() => {
        panel.current?.focus();
        const esc = (e) => { if (e.key === "Escape" && !busy) close(); };
        window.addEventListener("keydown", esc);
        return () => window.removeEventListener("keydown", esc);
    }, [busy, close]);

    const copyDetails = async () => {
        const text = `Video consultation with ${apt.client}\n${day} · ${span} PKT (${apt.duration})\nJoin from the appointment in AttorneyAI — no separate link needed.`;
        try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000); }
        catch { setError("Could not copy — your browser blocked the clipboard."); }
    };
    const message = () => { onMessage?.(); close(); };
    const saveLink = async () => {
        const value = link.trim();
        if (!/^https:\/\/.+\..+/i.test(value)) { setError("The link must start with https:// and include a host."); return; }
        setBusy(true); setError(null);
        const { error: err } = await onSaveLink(apt.id, value);
        setBusy(false);
        if (err) { setError(err.message || "Could not save the link."); return; }
        setLinkOpen(false);
    };

    // On <body>, so the blur covers the whole screen -- the sidebar too -- and
    // with the lawyer's colour tokens, which the page no longer provides there.
    return createPortal(
        <div data-prejoin-backdrop data-drafting-theme data-mode={dark ? "dark" : "light"} onClick={() => { if (!busy) close(); }}>
            <style>{PREJOIN_TOKENS_CSS}{CSS}</style>
            <div ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-label={`Join the video consultation with ${apt.client}`}
                data-prejoin onClick={e => e.stopPropagation()}>
                <section className="pj-left" aria-label="Camera and microphone check">
                    <div style={{ fontSize: 13, fontWeight: 800, letterSpacing: ".04em", textTransform: "uppercase", color: "var(--muted)" }}>Before you join</div>
                    <div className="pj-stage">
                        {dev.state === "on" && <video ref={dev.videoRef} autoPlay playsInline muted data-prejoin-video style={{ opacity: dev.cam ? 1 : 0 }} />}
                        {(dev.state !== "on" || !dev.cam) && (
                            <div className="pj-off">
                                <span className="av">You</span>
                                {dev.state === "idle" && <span>Your camera is off. Check it before the call, if you like.</span>}
                                {dev.state === "starting" && <span>Asking your browser for the camera…</span>}
                                {dev.state === "blocked" && <span role="alert">Camera or microphone is blocked. Allow them from the lock icon in the address bar, then try again.</span>}
                                {dev.state === "none" && <span role="alert">No camera or microphone was found on this device.</span>}
                                {dev.state === "on" && !dev.cam && <span>Camera paused</span>}
                            </div>
                        )}
                    </div>
                    {dev.state === "on" ? (<>
                        <div className="pj-ctl">
                            <button type="button" className={`pj-round${dev.cam ? "" : " off"}`} data-prejoin-cam aria-pressed={!dev.cam}
                                aria-label={dev.cam ? "Turn camera off" : "Turn camera on"} onClick={() => dev.toggle("cam")}>{dev.cam ? ICON.cam : ICON.camOff}</button>
                            <button type="button" className={`pj-round${dev.mic ? "" : " off"}`} data-prejoin-mic aria-pressed={!dev.mic}
                                aria-label={dev.mic ? "Mute microphone" : "Unmute microphone"} onClick={() => dev.toggle("mic")}>{dev.mic ? ICON.mic : ICON.micOff}</button>
                            <button type="button" className="pj-btn" onClick={dev.stop}>Stop check</button>
                        </div>
                        <div>
                            <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 6 }}>{dev.mic ? "Say something — the bar should move" : "Microphone muted"}</div>
                            <div className="pj-meter" aria-hidden="true"><i style={{ width: `${Math.round((dev.mic ? dev.level : 0) * 100)}%` }} /></div>
                        </div>
                    </>) : (
                        <button type="button" className="pj-btn" data-prejoin-check onClick={dev.start} disabled={dev.state === "starting"}>
                            {ICON.cam} {dev.state === "blocked" ? "Try again" : "Check camera & mic"}
                        </button>
                    )}
                    <div style={{ fontSize: 12, color: "var(--faint)", lineHeight: 1.5 }}>
                        This check stays on your device. The call asks for the camera again when you join, and you can switch it off there too.
                    </div>
                </section>

                <section className="pj-right" aria-label="Join">
                    <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontSize: 21, fontWeight: 800, lineHeight: 1.2 }}>Video consultation</div>
                            <div style={{ fontSize: 13.5, color: "var(--muted)", marginTop: 3 }}>with <b style={{ color: "var(--ink)" }}>{apt.client}</b></div>
                        </div>
                        <button type="button" className="pj-x" aria-label="Close" onClick={close}>✕</button>
                    </div>
                    {when && <span className="pj-when" style={live ? undefined : { color: "var(--ink)", background: "var(--chip-n, rgba(255,255,255,.06))", borderColor: "var(--line)" }}><i />{when}</span>}
                    <dl className="pj-facts">
                        <dt>When</dt><dd>{day} · {span} PKT</dd>
                        <dt>Length</dt><dd>{apt.duration}</dd>
                        {apt.note && (<><dt>Note</dt><dd style={{ fontWeight: 500, fontStyle: "italic" }}>“{apt.note}”</dd></>)}
                    </dl>

                    <VideoJoin apptId={apt.id} status="confirmed" mode="video" accent="#12897f" muted="var(--muted)" danger="var(--danger)"
                        dark={dark} big onBeforeJoin={dev.stop} otherName={first}
                        onOpenChat={onOpenChatInCall} />

                    <div className="pj-opts">
                        {onMessage && <button type="button" className="pj-opt" data-prejoin-message onClick={message}>{ICON.chat}Message {first}</button>}
                        <button type="button" className="pj-opt" data-prejoin-copy onClick={copyDetails}>{ICON.copy}{copied ? "Copied" : "Copy details"}</button>
                        {onSaveLink
                            ? <button type="button" className="pj-opt" data-prejoin-link aria-expanded={linkOpen} onClick={() => setLinkOpen(o => !o)}>{ICON.link}{apt.meetingLink ? "Your link" : "Use own link"}</button>
                            : apt.meetingLink && <a className="pj-opt" data-join-call href={apt.meetingLink} target="_blank" rel="noreferrer" style={{ textDecoration: "none" }}>{ICON.link}Open meeting link</a>}
                    </div>

                    {onSaveLink && linkOpen && (
                        <div className="pj-link" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                            <label htmlFor="pj-link" style={{ fontSize: 12.5, color: "var(--muted)" }}>
                                Optional: a Meet, Zoom or Teams link. {first} sees it on their appointment too.
                            </label>
                            <div style={{ display: "flex", gap: 8 }}>
                                <input id="pj-link" type="url" value={link} onChange={e => setLink(e.target.value)}
                                    placeholder="https://meet.google.com/…" disabled={busy} />
                                <button type="button" className="pj-btn" onClick={saveLink} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
                                {apt.meetingLink && <a className="pj-btn" href={apt.meetingLink} target="_blank" rel="noreferrer" data-join-call>Open</a>}
                            </div>
                        </div>
                    )}
                    {error && <div role="alert" style={{ fontSize: 12.5, color: "var(--danger)" }}>{error}</div>}
                </section>
            </div>
        </div>,
        document.body,
    );
}
