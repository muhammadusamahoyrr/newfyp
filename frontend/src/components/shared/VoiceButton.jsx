'use client';
/* Dictation into a chat box, for the client AND the lawyer (2026-10-20).
 *
 * Both chats had their own: the lawyer's heard Pakistani English reasonably
 * (en-PK, words shown while speaking); the client's was set to en-US, showed
 * nothing until the very end, could not be stopped, and called every error
 * "failed" -- including simply not speaking yet. This is the one they share.
 *
 * TWO WAYS TO LISTEN.
 *   browser  the browser's own speech recognition (Chrome / Edge): words
 *            appear while speaking; en-PK; keeps listening across short
 *            pauses and stops itself after SILENCE_MS without new words (or
 *            MAX_MS), or on a second click. It needs the browser vendor's
 *            speech service -- which many browsers (Brave, Opera, some Edge
 *            setups) do not have, and which then fails with "network".
 *   server   a recording, turned into text by OUR server
 *            (POST /voice/transcribe: Whisper on Groq, else the local
 *            model). Works in any browser with a microphone. Click to start,
 *            click again to finish; the text arrives after.
 * The browser way is tried first; when it is missing, or its service cannot
 * be reached, the button switches to the server way by itself (and starts
 * recording at once, since the person was about to speak), and remembers that
 * for this tab.
 *
 * Whatever was already typed is kept: the speech is added after it. Each
 * failure is named; a stop is not a failure. */
import { useEffect, useRef, useState } from "react";
import { transcribeAudio } from "@/lib/api.js";

const SILENCE_MS = 3500;
const MAX_MS = 60000;
const PREFER_SERVER_KEY = "attorney:voice-server";
const SWITCH_TO_SERVER = new Set(["network", "language-not-supported", "service-not-allowed-by-vendor"]);
const ERRORS = {
    "not-allowed": "Microphone permission was refused — allow it in the browser's address bar.",
    "service-not-allowed": "Microphone permission was refused — allow it in the browser's address bar.",
    "audio-capture": "No microphone was found.",
    "no-speech": "Didn't hear anything — click the mic and speak.",
};

export function joinDictation(base, spoken) {
    const a = String(base || "").replace(/\s+$/, "");
    const b = String(spoken || "").trim();
    if (!b) return a;
    return a ? `${a} ${b}` : b;
}

// 16-bit mono WAV from Float32 PCM: the server needs no ffmpeg to read it.
export function pcmToWav(samples, sampleRate) {
    const buf = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buf);
    const write4 = (off, str) => [...str].forEach((c, i) => view.setUint8(off + i, c.charCodeAt(0)));
    write4(0, "RIFF"); view.setUint32(4, 36 + samples.length * 2, true);
    write4(8, "WAVE"); write4(12, "fmt ");
    view.setUint32(16, 16, true); view.setUint16(20, 1, true);
    view.setUint16(22, 1, true); view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true); view.setUint16(32, 2, true);
    view.setUint16(34, 16, true); write4(36, "data");
    view.setUint32(40, samples.length * 2, true);
    for (let i = 0; i < samples.length; i++)
        view.setInt16(44 + i * 2, Math.max(-32768, Math.min(32767, samples[i] * 32768)), true);
    return new Blob([buf], { type: "audio/wav" });
}

/* The live sound bars beside the mic (2026-10-20), as in ChatGPT: they move
 * with the voice, so the person can see they are being heard. Drawn from the
 * microphone through an AnalyserNode; heights are written straight to the
 * bars (no re-render per frame). With no Web Audio, the bars breathe gently
 * so "listening" is still visible. A running timer sits beside them. */
const BARS = 22;
export function VoiceWave({ stream, color = "#2EC4B6" }) {
    const bars = useRef([]);
    const [secs, setSecs] = useState(0);
    useEffect(() => {
        const t0 = Date.now();
        const tick = setInterval(() => setSecs(Math.floor((Date.now() - t0) / 1000)), 500);
        return () => clearInterval(tick);
    }, []);
    useEffect(() => {
        let raf = 0, ctx = null, analyser = null, buf = null, frame = 0;
        const levels = new Array(BARS).fill(0.08);
        const Ctx = typeof window !== "undefined" ? (window.AudioContext || window.webkitAudioContext) : null;
        try {
            if (Ctx && stream) {
                ctx = new Ctx();
                analyser = ctx.createAnalyser();
                analyser.fftSize = 512;
                ctx.createMediaStreamSource(stream).connect(analyser);
                buf = new Uint8Array(analyser.fftSize);
            }
        } catch { analyser = null; }
        // A plain 50 ms timer (20 updates a second), not animation frames:
        // those stall when the window is in the background.
        const draw = () => {
            frame += 3;
            {
                let level;
                if (analyser) {
                    analyser.getByteTimeDomainData(buf);
                    let sum = 0;
                    for (let i = 0; i < buf.length; i++) { const v = (buf[i] - 128) / 128; sum += v * v; }
                    level = Math.min(1, Math.sqrt(sum / buf.length) * 4.5);
                } else {
                    level = 0.18 + 0.12 * Math.sin(frame / 9);
                }
                levels.shift();
                levels.push(Math.max(0.08, level));
                bars.current.forEach((el, i) => { if (el) el.style.transform = `scaleY(${levels[i]})`; });
            }
        };
        raf = setInterval(draw, 50);
        return () => {
            clearInterval(raf);
            try { ctx?.close(); } catch { /* closed */ }
        };
    }, [stream]);
    const mm = `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}`;
    return (
        <span data-voice-wave role="status" aria-label="Listening" style={{ display: "inline-flex", alignItems: "center", gap: 8, color, flex: "none" }}>
            <span aria-hidden="true" style={{ display: "inline-flex", alignItems: "center", gap: 2, height: 24 }}>
                {Array.from({ length: BARS }, (_, i) => (
                    <span key={i} ref={el => { bars.current[i] = el; }}
                        style={{ width: 3, height: 24, borderRadius: 2, background: "currentColor", transform: "scaleY(0.08)", transformOrigin: "center", transition: "transform .08s linear" }} />
                ))}
            </span>
            <span style={{ fontSize: 12.5, fontWeight: 700, fontVariantNumeric: "tabular-nums", opacity: .85 }}>{mm}</span>
        </span>
    );
}

const preferServer = () => { try { return sessionStorage.getItem(PREFER_SERVER_KEY) === "1"; } catch { return false; } };
const rememberServer = () => { try { sessionStorage.setItem(PREFER_SERVER_KEY, "1"); } catch { /* storage off */ } };

/* `mode`: "auto" tries the browser first (above); "server" always records
 * for our server -- the only way that tells Urdu from English by itself
 * (`serverLanguage="auto"`: Urdu speech is written in Urdu script, English in
 * English). The client chat uses that (2026-10-20). */
export default function VoiceButton({ value = "", onText, onError = null, onNotice = null, onListening = null,
                                      className = "", size = 22, lang = "en-PK", serverLanguage = "en", mode = "auto" }) {
    // Looked up after mount, so the server render and the first client render agree.
    const [caps, setCaps] = useState(null);       // { Rec, canRecord }
    useEffect(() => {
        const Rec = typeof window !== "undefined" ? (window.SpeechRecognition || window.webkitSpeechRecognition || null) : null;
        const canRecord = typeof navigator !== "undefined" && Boolean(navigator.mediaDevices?.getUserMedia) && typeof window.MediaRecorder !== "undefined";
        setCaps({ Rec, canRecord });
    }, []);
    const recRef = useRef(null);
    const mediaRef = useRef(null);
    const chunks = useRef([]);
    const timers = useRef({ silence: 0, max: 0 });
    const valueRef = useRef(value);
    valueRef.current = value;
    const [state, setState] = useState("idle");   // idle | listening | recording | transcribing
    const [err, setErr] = useState("");
    // The microphone the sound bars read: the recording's own stream, or (for
    // the browser's recognition, which exposes none) a second one, opened only
    // to draw the bars and closed with it.
    const [waveStream, setWaveStream] = useState(null);
    const vizRef = useRef(null);
    const closeViz = () => { try { vizRef.current?.getTracks().forEach(tr => tr.stop()); } catch { /* gone */ } vizRef.current = null; };

    const clear = () => { clearTimeout(timers.current.silence); clearTimeout(timers.current.max); };
    const releaseMic = () => { try { mediaRef.current?.stream?.getTracks().forEach(tr => tr.stop()); } catch { /* gone */ } setWaveStream(null); };
    useEffect(() => () => {
        clear();
        try { recRef.current?.abort(); } catch { /* already stopped */ }
        try { if (mediaRef.current?.state === "recording") mediaRef.current.stop(); } catch { /* already stopped */ }
        try { mediaRef.current?.stream?.getTracks().forEach(tr => tr.stop()); } catch { /* gone */ }
        closeViz();
    }, []);
    useEffect(() => { onListening?.(state === "listening" || state === "recording"); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [state]);
    if (!caps || (!caps.Rec && !caps.canRecord) || (mode === "server" && !caps.canRecord)) return null;

    const fail = (msg) => { setErr(msg); onError?.(msg); };

    // ── server: record, then our transcription ──
    const startRecording = async () => {
        let stream;
        try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
        catch { fail(ERRORS["not-allowed"]); setState("idle"); return; }
        chunks.current = [];
        const type = window.MediaRecorder.isTypeSupported?.("audio/webm") ? "audio/webm" : "";
        const mr = new window.MediaRecorder(stream, type ? { mimeType: type } : {});
        mr.ondataavailable = e => { if (e.data?.size) chunks.current.push(e.data); };
        mr.onstop = () => { releaseMic(); finishRecording(); };
        mediaRef.current = mr;
        mr.start(250);
        setWaveStream(stream);
        setState("recording");
        timers.current.max = setTimeout(() => { try { mr.stop(); } catch { /* stopped */ } }, MAX_MS);
    };
    const finishRecording = async () => {
        clear();
        if (!chunks.current.length) { setState("idle"); fail(ERRORS["no-speech"]); return; }
        setState("transcribing");
        const raw = new Blob(chunks.current, { type: mediaRef.current?.mimeType || "audio/webm" });
        let blob = raw;
        try {
            const Ctx = window.AudioContext || window.webkitAudioContext;
            const ctx = new Ctx({ sampleRate: 16000 });
            const decoded = await ctx.decodeAudioData(await raw.arrayBuffer());
            blob = pcmToWav(decoded.getChannelData(0), 16000);
            ctx.close?.();
        } catch { /* send the recording as it is */ }
        const { data, error } = await transcribeAudio(blob, { language: serverLanguage });
        setState("idle");
        if (error) { fail(error.message || "Couldn't turn the recording into text — try again."); return; }
        const text = String(data?.transcript || "").trim();
        // Silence or noise comes back as punctuation alone (".").
        if (!/[\p{L}\p{N}]/u.test(text)) { fail(ERRORS["no-speech"]); return; }
        onText(joinDictation(valueRef.current, text));
    };
    const switchToServer = () => {
        rememberServer();
        onNotice?.("Your browser's speech service isn't available, so the mic now records instead. Speak, then click the mic again to finish.");
        startRecording();
    };

    // ── browser: live recognition ──
    const startBrowser = () => {
        const base = valueRef.current;          // what was typed before speaking: kept
        const rec = new caps.Rec();
        rec.lang = lang;
        rec.interimResults = true;
        rec.continuous = true;
        rec.maxAlternatives = 1;
        let switched = false;
        const stopLater = () => { clearTimeout(timers.current.silence); timers.current.silence = setTimeout(() => { try { rec.stop(); } catch { /* stopped */ } }, SILENCE_MS); };
        rec.onresult = (e) => {
            const spoken = Array.from(e.results).map(r => r[0].transcript).join(" ").replace(/\s+/g, " ");
            onText(joinDictation(base, spoken));
            stopLater();
        };
        rec.onerror = (e) => {
            if (e.error === "aborted") return;              // our own stop
            if (SWITCH_TO_SERVER.has(e.error) && caps.canRecord) { switched = true; return; }
            fail(ERRORS[e.error] || (e.error === "network"
                ? "Couldn't reach the speech service — check the internet connection."
                : "Couldn't hear that — try again."));
        };
        rec.onend = () => {
            clear();
            closeViz();
            setWaveStream(null);
            setState("idle");
            if (switched) switchToServer();
        };
        recRef.current = rec;
        try {
            rec.start();
            setState("listening");
            stopLater();
            // A stream only to draw the bars; recognition has its own.
            navigator.mediaDevices?.getUserMedia?.({ audio: true }).then(s => {
                if (recRef.current !== rec) { s.getTracks().forEach(tr => tr.stop()); return; }
                vizRef.current = s; setWaveStream(s);
            }).catch(() => { /* bars breathe without a level */ });
            timers.current.max = setTimeout(() => { try { rec.stop(); } catch { /* stopped */ } }, MAX_MS);
        } catch {
            setState("idle");
            if (caps.canRecord) switchToServer();
        }
    };

    const toggle = () => {
        if (state === "transcribing") return;
        if (state === "listening") { clear(); try { recRef.current?.stop(); } catch { /* stopped */ } return; }
        if (state === "recording") { clear(); try { mediaRef.current?.stop(); } catch { /* stopped */ } return; }
        setErr("");
        if (mode !== "server" && caps.Rec && !preferServer()) startBrowser();
        else startRecording();
    };

    const busy = state === "transcribing";
    const live = state === "listening" || state === "recording";
    return (<>
        {live && <VoiceWave stream={waveStream} />}
        <button type="button" className={`${className}${live ? " on" : ""}`} onClick={toggle} data-voice-button data-voice-state={state}
            disabled={busy} aria-pressed={live} aria-busy={busy || undefined}
            aria-label={busy ? "Turning your recording into text" : live ? "Stop" : "Speak your question"}
            title={err || (busy ? "Turning your recording into text…" : state === "recording" ? "Recording… click to finish" : live ? "Listening… click to stop" : "Speak your question")}>
            {busy ? (
                <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true">
                    <path d="M12 3a9 9 0 1 0 9 9">
                        <animateTransform attributeName="transform" type="rotate" from="0 12 12" to="360 12 12" dur=".9s" repeatCount="indefinite" />
                    </path>
                </svg>
            ) : (
                <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <rect x="9" y="2.5" width="6" height="11.5" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3.5M8.5 21.5h7" />
                </svg>
            )}
        </button>
    </>);
}

/* The send arrow (2026-10-20): an upward arrow, for both chats. */
export function SendArrow({ size = 15 }) {
    return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M12 19V5M5.5 11.5 12 5l6.5 6.5" />
        </svg>
    );
}
