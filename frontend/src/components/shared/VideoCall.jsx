"use client";
/* The in-app video call (2026-10-20), Google Meet style.
 *
 * Daily carries the audio and video (its "call object"); the screen is ours:
 *   - the other person fills the screen; you are a small tile in the corner
 *     (alone, you fill it, with "Waiting for … to join")
 *   - a shared screen takes the stage, the sharer's camera goes to a tile
 *   - no header bar: a quiet corner label with the name, a timer and
 *     "Private · not recorded"
 *   - one control bar at the bottom: mic, camera, share screen, messages
 *     (when the page offers a chat), more (switch camera / microphone /
 *     speaker-less devices, full screen), and the red hang-up
 * If daily-js cannot load, the room opens in a plain iframe instead. */
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

let loadDaily = () => import("@daily-co/daily-js").then(m => m.default || m);
export function __setCallLoader(fn) { loadDaily = fn; }

const CSS = `[data-video-call]{position:fixed;inset:0;z-index:1000;background:#0e1b1f;color:#eef6f5;font-family:"Hanken Grotesk",system-ui,sans-serif;display:flex;flex-direction:column;overflow:hidden}
[data-video-call] .vc-stage{position:relative;flex:1;min-height:0;padding:14px 14px 0}
[data-video-call] .vc-main{position:relative;width:100%;height:100%;border-radius:18px;overflow:hidden;background:#15262b;display:grid;place-items:center}
[data-video-call] .vc-main video{width:100%;height:100%;object-fit:contain;background:#0b1518}
[data-video-call] .vc-main video.cover{object-fit:cover}
[data-video-call] .vc-self{position:absolute;right:28px;bottom:14px;width:240px;aspect-ratio:16/10;border-radius:14px;overflow:hidden;background:#1d3238;box-shadow:0 10px 30px -10px rgba(0,0,0,.7);border:1px solid rgba(255,255,255,.08)}
[data-video-call] .vc-self video{width:100%;height:100%;object-fit:cover;transform:scaleX(-1)}
[data-video-call] .vc-self video.screen{transform:none;object-fit:contain}
[data-video-call] .vc-name{position:absolute;left:10px;bottom:8px;font-size:12.5px;font-weight:700;padding:3px 8px;border-radius:8px;background:rgba(0,0,0,.45);display:flex;align-items:center;gap:6px}
[data-video-call] .vc-avatar{display:flex;flex-direction:column;align-items:center;gap:12px;color:#cfe3e0;font-size:14px;text-align:center}
[data-video-call] .vc-avatar b{width:96px;height:96px;border-radius:50%;display:grid;place-items:center;font-size:32px;color:#fff;background:linear-gradient(135deg,#12897f,#1c9c66)}
[data-video-call] .vc-self .vc-avatar b{width:52px;height:52px;font-size:18px}
[data-video-call] .vc-corner{position:absolute;left:30px;top:28px;display:flex;align-items:center;gap:10px;font-size:13px;padding:6px 12px;border-radius:999px;background:rgba(0,0,0,.4);backdrop-filter:blur(6px)}
[data-video-call] .vc-corner i{width:8px;height:8px;border-radius:50%;background:#3ec99a}
[data-video-call] .vc-wait{position:absolute;left:50%;top:28px;transform:translateX(-50%);font-size:13.5px;padding:7px 14px;border-radius:999px;background:rgba(0,0,0,.45)}
[data-video-call] .vc-bar{flex:none;display:flex;align-items:center;justify-content:center;gap:12px;padding:14px 16px 18px;position:relative}
[data-video-call] .vc-btn{position:relative;width:52px;height:52px;border-radius:50%;border:none;display:grid;place-items:center;cursor:pointer;background:#2a3d42;color:#fff;transition:background .15s}
[data-video-call] .vc-btn:hover{background:#354c52}
[data-video-call] .vc-btn.off{background:#e5484d}
[data-video-call] .vc-btn.on{background:#40f0dc;color:#0e1b1f}
[data-video-call] .vc-btn.end{width:72px;border-radius:999px;background:#e5484d}
[data-video-call] .vc-btn.end:hover{background:#f05a5f}
[data-video-call] .vc-btn:disabled{opacity:.45;cursor:not-allowed}
[data-video-call] .vc-tip{position:absolute;bottom:calc(100% + 8px);left:50%;transform:translateX(-50%);white-space:nowrap;font-size:12px;padding:4px 8px;border-radius:6px;background:#000c;opacity:0;pointer-events:none;transition:opacity .12s}
[data-video-call] .vc-btn:hover .vc-tip{opacity:1}
[data-video-call] .vc-menu{position:absolute;bottom:84px;left:50%;transform:translateX(40px);width:300px;padding:10px;border-radius:14px;background:#1b2c31;border:1px solid rgba(255,255,255,.1);box-shadow:0 18px 40px -12px #000;display:flex;flex-direction:column;gap:8px}
[data-video-call] .vc-menu label{font-size:12px;color:#9fb9b7}
[data-video-call] .vc-menu select{width:100%;height:36px;border-radius:9px;border:1px solid rgba(255,255,255,.12);background:#122126;color:#eef6f5;font:inherit;font-size:13px;padding:0 8px}
[data-video-call] .vc-menu button{height:36px;border-radius:9px;border:1px solid rgba(255,255,255,.12);background:transparent;color:#eef6f5;font:inherit;font-size:13px;cursor:pointer;text-align:left;padding:0 10px}
[data-video-call] .vc-err{position:absolute;left:50%;top:70px;transform:translateX(-50%);font-size:13px;padding:8px 14px;border-radius:10px;background:#e5484dd9}`;

const svg = (d, size = 22) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{d}</svg>;
const I = {
    mic: svg(<><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0014 0M12 18v3" /></>),
    micOff: svg(<><path d="M2 2l20 20" /><path d="M9 9v2a3 3 0 005 2.2M15 9.3V6a3 3 0 00-5.7-1.3M5 11a7 7 0 0011.4 5.4M19 11a7 7 0 01-.4 2.3M12 18v3" /></>),
    cam: svg(<><rect x="2.5" y="6" width="13" height="12" rx="2.5" /><path d="M15.5 10.5l6-3.5v10l-6-3.5z" /></>),
    camOff: svg(<><path d="M2 2l20 20" /><path d="M15.5 10.5l6-3.5v10l-3-1.75M10 6h3a2.5 2.5 0 012.5 2.5v3M15.5 16v-.5a2.5 2.5 0 01-2.5 2.5H5a2.5 2.5 0 01-2.5-2.5v-7A2.5 2.5 0 015 6" /></>),
    share: svg(<><rect x="2.5" y="4" width="19" height="13" rx="2" /><path d="M8 21h8M12 13V8M9.5 10.5L12 8l2.5 2.5" /></>),
    chat: svg(<path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />),
    more: svg(<><circle cx="12" cy="5" r="1.4" /><circle cx="12" cy="12" r="1.4" /><circle cx="12" cy="19" r="1.4" /></>),
    end: svg(<path d="M3.5 14.5c4.8-4.6 12.2-4.6 17 0l-2.3 2.3-3.4-1.6v-2.6a10.6 10.6 0 00-5.6 0v2.6l-3.4 1.6z" fill="currentColor" stroke="none" />, 26),
};
const initials = n => String(n || "?").split(" ").filter(Boolean).map(w => w[0]).join("").toUpperCase().slice(0, 2) || "?";

/** Plays one MediaStreamTrack (video or audio). */
function Track({ track, kind = "video", className, muted = true }) {
    const ref = useRef(null);
    useEffect(() => {
        const el = ref.current;
        if (!el) return;
        el.srcObject = track ? new MediaStream([track]) : null;
    }, [track]);
    if (kind === "audio") return <audio ref={ref} autoPlay />;
    return <video ref={ref} className={className} autoPlay playsInline muted={muted} />;
}

const track = (p, key) => {
    const t = p?.tracks?.[key];
    return t && (t.state === "playable" || t.state === "sendable") ? t.persistentTrack || t.track || null : null;
};

export default function VideoCall({ call, otherName = "your client", onClose, onOpenChat = null, onPeerJoined = null }) {
    // Latest callback without restarting the call (the effect below runs once per call).
    const peerJoined = useRef(onPeerJoined);
    peerJoined.current = onPeerJoined;
    const [frame, setFrame] = useState(null);
    const [fallback, setFallback] = useState(false);
    const [people, setPeople] = useState({});
    const [error, setError] = useState(null);
    const [menu, setMenu] = useState(false);
    const [devices, setDevices] = useState({ cams: [], mics: [] });
    const [seconds, setSeconds] = useState(0);
    const root = useRef(null);
    const closing = useRef(false);

    useEffect(() => {
        let gone = false, co = null;
        const sync = () => { if (co && !gone) setPeople({ ...co.participants() }); };
        loadDaily().then(async (Daily) => {
            if (gone) return;
            co = Daily.createCallObject({ subscribeToTracksAutomatically: true });
            setFrame(co);
            for (const ev of ["joined-meeting", "participant-joined", "participant-updated", "participant-left", "track-started", "track-stopped"]) co.on(ev, sync);
            // The other person is in the call: a moment for the server to ask
            // Daily whether both have met (it decides, not this browser).
            co.on("participant-joined", () => { if (!gone) peerJoined.current?.(); });
            co.on("left-meeting", () => { if (!gone && !closing.current) onClose(); });
            co.on("camera-error", () => setError("Your camera or microphone could not start. Check the browser's permission."));
            co.on("error", (e) => setError(e?.errorMsg || "The call ran into a problem."));
            await co.join({ url: call.room_url, token: call.token });
            sync();
        }).catch(() => { if (!gone) setFallback(true); });
        return () => {
            gone = true;
            if (co) Promise.resolve(co.leave()).catch(() => {}).finally(() => { try { co.destroy(); } catch { /* gone */ } });
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [call]);

    useEffect(() => {
        const id = setInterval(() => setSeconds(s => s + 1), 1000);
        return () => clearInterval(id);
    }, []);

    const leave = useCallback(() => {
        closing.current = true;
        if (frame) Promise.resolve(frame.leave()).catch(() => {}).finally(onClose);
        else onClose();
    }, [frame, onClose]);
    useEffect(() => {
        const esc = (e) => { if (e.key === "Escape") setMenu(false); };
        window.addEventListener("keydown", esc);
        return () => window.removeEventListener("keydown", esc);
    }, []);

    const local = people.local;
    const others = Object.values(people).filter(p => !p.local);
    const other = others[0] || null;
    // Daily's own answer; re-read on every participant update (which re-renders).
    const micOn = frame?.localAudio ? Boolean(frame.localAudio()) : Boolean(local?.tracks?.audio?.state === "playable");
    const camOn = frame?.localVideo ? Boolean(frame.localVideo()) : Boolean(local?.tracks?.video?.state === "playable");
    const sharing = Boolean(local?.screen || track(local, "screenVideo"));
    const otherScreen = track(other, "screenVideo");
    const myScreen = track(local, "screenVideo");

    const openMenu = async () => {
        if (!menu && frame?.enumerateDevices) {
            try {
                const { devices: list = [] } = await frame.enumerateDevices();
                setDevices({ cams: list.filter(d => d.kind === "videoinput"), mics: list.filter(d => d.kind === "audioinput") });
            } catch { /* keep the old list */ }
        }
        setMenu(m => !m);
    };
    const fullScreen = () => {
        const el = root.current;
        try { if (document.fullscreenElement) document.exitFullscreen(); else el?.requestFullscreen?.(); } catch { /* not allowed */ }
        setMenu(false);
    };

    if (fallback) {
        return createPortal(
            <div data-video-call data-video-call-fallback>
                <style>{CSS}</style>
                <iframe title="Video consultation" src={`${call.room_url}?t=${encodeURIComponent(call.token)}`}
                    allow="camera; microphone; fullscreen; display-capture; autoplay; clipboard-write" style={{ flex: 1, border: 0 }} />
                <div className="vc-bar"><button type="button" className="vc-btn end" data-video-leave aria-label="Leave the call" onClick={onClose}>{I.end}</button></div>
            </div>, document.body);
    }

    // The stage: a shared screen, else the other person, else you.
    const stage = otherScreen ? { t: otherScreen, label: `${otherName} is presenting`, screen: true }
        : myScreen ? { t: myScreen, label: "You are presenting", screen: true }
        : other ? { t: track(other, "video"), label: other.user_name || otherName, cover: false, person: other }
        : { t: camOn ? track(local, "video") : null, label: "You", mirror: true, person: local };
    const mm = String(Math.floor(seconds / 60)).padStart(2, "0"), ss = String(seconds % 60).padStart(2, "0");

    return createPortal(
        <div ref={root} data-video-call role="dialog" aria-modal="true" aria-label="Video consultation" data-lenis-prevent>
            <style>{CSS}</style>
            <div className="vc-stage">
                <div className="vc-main" data-vc-stage>
                    {stage.t
                        ? <Track track={stage.t} className={stage.mirror ? "cover" : undefined} />
                        : <div className="vc-avatar"><b>{initials(stage.person?.user_name || stage.label)}</b>{stage.person && !stage.person.local ? `${stage.label} · camera off` : "Your camera is off"}</div>}
                    <span className="vc-name">{stage.label}</span>
                    <span className="vc-corner"><i />{otherName} · {mm}:{ss} · Private · not recorded</span>
                    {!other && <span className="vc-wait" data-vc-waiting>Waiting for {otherName} to join…</span>}
                </div>
                {/* You, small, once someone else (or a screen) has the stage. */}
                {(other || myScreen) && (
                    <div className="vc-self" data-vc-self>
                        {myScreen && other
                            ? (track(other, "video") ? <Track track={track(other, "video")} /> : <div className="vc-avatar"><b>{initials(otherName)}</b></div>)
                            : camOn && track(local, "video") ? <Track track={track(local, "video")} /> : <div className="vc-avatar" style={{ height: "100%", justifyContent: "center" }}><b>{initials(local?.user_name || "You")}</b></div>}
                        <span className="vc-name">{myScreen && other ? (other.user_name || otherName) : "You"}{!micOn && !(myScreen && other) ? " · muted" : ""}</span>
                    </div>
                )}
                {/* The other person's voice. */}
                {others.map(p => track(p, "audio") && <Track key={p.session_id} kind="audio" track={track(p, "audio")} />)}
                {error && <div className="vc-err" role="alert">{error}</div>}
            </div>

            <div className="vc-bar" role="toolbar" aria-label="Call controls">
                <button type="button" className={`vc-btn${micOn ? "" : " off"}`} data-vc-mic aria-pressed={!micOn} disabled={!frame}
                    aria-label={micOn ? "Mute microphone" : "Unmute microphone"} onClick={() => frame?.setLocalAudio(!micOn)}>
                    {micOn ? I.mic : I.micOff}<span className="vc-tip">{micOn ? "Mute" : "Unmute"}</span>
                </button>
                <button type="button" className={`vc-btn${camOn ? "" : " off"}`} data-vc-cam aria-pressed={!camOn} disabled={!frame}
                    aria-label={camOn ? "Turn camera off" : "Turn camera on"} onClick={() => frame?.setLocalVideo(!camOn)}>
                    {camOn ? I.cam : I.camOff}<span className="vc-tip">{camOn ? "Camera off" : "Camera on"}</span>
                </button>
                <button type="button" className={`vc-btn${sharing ? " on" : ""}`} data-vc-share disabled={!frame}
                    aria-label={sharing ? "Stop presenting" : "Present your screen"} onClick={() => (sharing ? frame?.stopScreenShare() : frame?.startScreenShare())}>
                    {I.share}<span className="vc-tip">{sharing ? "Stop presenting" : "Present screen"}</span>
                </button>
                {onOpenChat && (
                    <button type="button" className="vc-btn" data-vc-chat aria-label="Messages" onClick={onOpenChat}>
                        {I.chat}<span className="vc-tip">Messages</span>
                    </button>
                )}
                <button type="button" className={`vc-btn${menu ? " on" : ""}`} data-vc-more aria-label="More options" aria-expanded={menu} onClick={openMenu}>
                    {I.more}<span className="vc-tip">More</span>
                </button>
                <button type="button" className="vc-btn end" data-video-leave aria-label="Leave the call" onClick={leave}>
                    {I.end}<span className="vc-tip">Leave call</span>
                </button>
                {menu && (
                    <div className="vc-menu" role="menu" data-vc-menu>
                        {devices.cams.length > 0 && (<>
                            <label htmlFor="vc-cam">Camera</label>
                            <select id="vc-cam" onChange={e => frame?.setInputDevicesAsync({ videoDeviceId: e.target.value })}>
                                {devices.cams.map(d => <option key={d.deviceId} value={d.deviceId}>{d.label || "Camera"}</option>)}
                            </select>
                        </>)}
                        {devices.mics.length > 0 && (<>
                            <label htmlFor="vc-mic">Microphone</label>
                            <select id="vc-mic" onChange={e => frame?.setInputDevicesAsync({ audioDeviceId: e.target.value })}>
                                {devices.mics.map(d => <option key={d.deviceId} value={d.deviceId}>{d.label || "Microphone"}</option>)}
                            </select>
                        </>)}
                        <button type="button" onClick={fullScreen}>⛶  Full screen</button>
                    </div>
                )}
            </div>
        </div>,
        document.body,
    );
}
