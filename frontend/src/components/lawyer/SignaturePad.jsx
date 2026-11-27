'use client';
/* LAWYER-OWNED COPY (2026-10-08). Forked from components/shared/SignaturePad.jsx so that
 * lawyer screens can change freely without touching the finalized client
 * screens, which keep the shared original. Change THIS file for the lawyer
 * side; a fix both sides need must be made in both (tests/docs_isolation). */
/* The three ways to sign: draw, type, upload.
 *
 * EXTRACTED so every signing surface offers the same three. The agreement
 * BUILDER had all three from the start, while everyone asked to counter-sign --
 * the client in the detail modal, the lawyer on their own page, and an invited
 * signer on /sign -- was given a single "type your name" box. The backend
 * accepted `canvas`, `typed` and `image_upload` on both signing paths the whole
 * time; only the UI was narrower, and only for the people receiving an
 * agreement rather than sending one.
 *
 * It reports `{ method, data }` using the server's own method names, so a caller
 * passes them straight through and there is no mapping table to drift.
 */
import React, { useCallback, useEffect, useRef, useState } from "react";
// The lawyer theme (its own palette, light/dark toggle): lawyer/theme.js.
import { useTheme } from "./theme.js";
import { Icon, I } from "./icons.jsx";

/* V1, "draw on paper" (2026-11-26): the pad is the agreement's own cream paper
 * and the ink its dark blue, so what you draw is what lands on the document.
 * It used to be a dark box with cyan ink that looked nothing like the paper. */
const INK = "#1A3E8C";             // what lands on the agreement
const INK_RGB = [26, 62, 140];

/* WHAT THE SERVER WILL ACTUALLY TAKE.
 *
 * `signature_data` is capped at 200,000 characters (schemas/agreement.py
 * `_MAX_SIGNATURE`). Base64 costs 4 bytes per 3, plus the data-URL prefix, so
 * the real ceiling on an uploaded image is about 146 KB.
 *
 * The old drop zone said "Max 2MB". Anything near that was rejected by the
 * server with a 422 the user had no way to interpret, after they had already
 * chosen the file. Checking here means the limit is enforced where it can be
 * explained. */
const MAX_SIGNATURE_CHARS = 200_000;
const MAX_IMAGE_BYTES = Math.floor((MAX_SIGNATURE_CHARS - 64) * 3 / 4);
const MAX_IMAGE_LABEL = `${Math.floor(MAX_IMAGE_BYTES / 1024)} KB`;

const MODES = [
    ["draw", "edit", "Draw"],
    ["type", null, "Type"],
    ["upload", "upload", "Upload"],
];

/* The drawn image, cut down to the ink plus a small margin. Falls back to the
 * whole canvas when pixels cannot be read (e.g. no 2D context). */
function trimToInk(canvas, margin = 10) {
    // Cropped to the ink AND recoloured to the paper's ink: the pad is drawn in
    // a light colour that reads on the dark theme.
    try {
        const ctx = canvas.getContext("2d");
        const { width: w, height: h } = canvas;
        const px = ctx.getImageData(0, 0, w, h).data;
        let top = h, left = w, right = -1, bottom = -1;
        for (let y = 0; y < h; y++) {
            for (let x = 0; x < w; x++) {
                if (px[(y * w + x) * 4 + 3] > 8) {
                    if (x < left) left = x;
                    if (x > right) right = x;
                    if (y < top) top = y;
                    if (y > bottom) bottom = y;
                }
            }
        }
        if (right < 0) return canvas.toDataURL();
        const x0 = Math.max(0, left - margin), y0 = Math.max(0, top - margin);
        const cw = Math.min(w, right + margin + 1) - x0, ch = Math.min(h, bottom + margin + 1) - y0;
        const out = document.createElement("canvas");
        out.width = cw; out.height = ch;
        const octx = out.getContext("2d");
        octx.drawImage(canvas, x0, y0, cw, ch, 0, 0, cw, ch);
        const img = octx.getImageData(0, 0, cw, ch);
        for (let i = 0; i < img.data.length; i += 4) {
            if (img.data[i + 3] > 0) { img.data[i] = INK_RGB[0]; img.data[i + 1] = INK_RGB[1]; img.data[i + 2] = INK_RGB[2]; }
        }
        octx.putImageData(img, 0, 0);
        return out.toDataURL();
    } catch {
        return canvas.toDataURL();
    }
}

/* The server's vocabulary, not ours. */
const METHOD = { draw: "canvas", type: "typed", upload: "image_upload" };

export default function SignaturePad({ onChange, height = 200 }) {
    const { t } = useTheme();
    const [mode, setMode] = useState("draw");

    // THE DRAWING LIVES IN STATE, NOT ON THE CANVAS. A canvas unmounts with the
    // view that holds it, and reading `canvasRef.current.toDataURL()` at submit
    // time then yields nothing -- which is exactly how the builder's Sign & Send
    // came to look like a dead button. Captured at the end of each stroke.
    const [drawn, setDrawn] = useState(null);
    const [typed, setTyped] = useState("");
    const [uploaded, setUploaded] = useState(null);
    const [uploadError, setUploadError] = useState(null);

    const canvasRef = useRef(null);
    const drawing = useRef(false);
    const lastPos = useRef({ x: 0, y: 0 });

    const current = mode === "draw" ? drawn : mode === "type" ? typed.trim() : uploaded;

    useEffect(() => {
        onChange?.({ method: METHOD[mode], data: current || "" });
        // `onChange` is intentionally not a dependency: callers pass an inline
        // arrow, so including it would fire this on every render of the parent.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [mode, current]);

    const pos = (e) => {
        const r = canvasRef.current.getBoundingClientRect();
        const src = e.touches ? e.touches[0] : e;
        // The canvas is drawn at its intrinsic size but displayed stretched, so
        // a click at the right edge is further right in canvas coordinates than
        // in CSS pixels. Without this the ink lags behind the cursor.
        return {
            x: (src.clientX - r.left) * (canvasRef.current.width / r.width),
            y: (src.clientY - r.top) * (canvasRef.current.height / r.height),
        };
    };

    const startDraw = useCallback((e) => {
        if (!canvasRef.current) return;
        e.preventDefault();
        drawing.current = true;
        lastPos.current = pos(e);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const draw = useCallback((e) => {
        if (!drawing.current || !canvasRef.current) return;
        e.preventDefault();
        const p = pos(e);
        const ctx = canvasRef.current.getContext("2d");
        ctx.beginPath();
        ctx.moveTo(lastPos.current.x, lastPos.current.y);
        ctx.lineTo(p.x, p.y);
        ctx.strokeStyle = t.mode === "dark" ? "#E6F4F1" : INK;
        ctx.lineWidth = 2.6;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        ctx.stroke();
        lastPos.current = p;
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [t.mode]);

    const stopDraw = useCallback(() => {
        if (drawing.current && canvasRef.current) {
            // At the end of a stroke, not on every movement: toDataURL
            // serialises the whole bitmap and is far too costly per pixel.
            // Cropped to the ink (2026-11-26), so the signature fills its line
            // on the agreement instead of shrinking inside an empty canvas.
            setDrawn(trimToInk(canvasRef.current));
        }
        drawing.current = false;
    }, []);

    const clear = () => {
        const c = canvasRef.current;
        if (c) c.getContext("2d").clearRect(0, 0, c.width, c.height);
        setDrawn(null);
        setTyped("");
        setUploaded(null);
        setUploadError(null);
    };

    const onFile = (e) => {
        const file = e.target.files?.[0];
        e.target.value = "";           // so re-picking the same file still fires
        if (!file) return;
        setUploadError(null);

        if (!file.type.startsWith("image/")) {
            setUploadError("That is not an image file.");
            return;
        }
        if (file.size > MAX_IMAGE_BYTES) {
            setUploadError(
                `That image is ${Math.round(file.size / 1024)} KB. The limit is `
                + `${MAX_IMAGE_LABEL} — try a smaller or more compressed one.`);
            return;
        }
        const reader = new FileReader();
        reader.onerror = () => setUploadError("That file could not be read.");
        reader.onload = (ev) => {
            const data = String(ev.target.result || "");
            // The byte check above is the useful one; this catches the edge
            // where encoding pushes a borderline file over the server's cap.
            if (data.length > MAX_SIGNATURE_CHARS) {
                setUploadError(
                    `That image encodes to more than the server accepts. Try one `
                    + `under ${MAX_IMAGE_LABEL}.`);
                return;
            }
            setUploaded(data);
        };
        reader.readAsDataURL(file);
    };

    const pane = {
        position: "relative", background: t.inputBg, borderRadius: 14,
        border: `1px solid ${t.border}`, overflow: "hidden",
    };
    // The sign-here line, with an "×" at its start, like a paper form.
    const baseline = (
        <>
            <div aria-hidden="true" style={{
                position: "absolute", left: 24, right: 24, bottom: 44, height: 0,
                borderTop: `1.5px dashed ${t.textMuted}66`, pointerEvents: "none", zIndex: 0,
            }} />
            <span aria-hidden="true" style={{
                position: "absolute", left: 24, bottom: 48, color: t.textMuted, fontSize: 18,
                fontWeight: 700, fontFamily: "Georgia, serif", pointerEvents: "none", zIndex: 0,
            }}>×</span>
        </>
    );
    const hint = (text) => (
        <span style={{ position: "absolute", left: 24, bottom: 14, fontSize: 12, color: t.textMuted, pointerEvents: "none", zIndex: 2 }}>{text}</span>
    );
    const hasSomething = mode === "draw" ? !!drawn : mode === "type" ? !!typed : !!uploaded;
    const clearBtn = hasSomething && (
        <button type="button" onClick={clear} style={{
            position: "absolute", right: 12, top: 12, zIndex: 3,
            display: "inline-flex", alignItems: "center", gap: 6, height: 30, padding: "0 12px",
            borderRadius: 8, border: `1px solid ${t.border}`, background: `${t.text}14`, color: t.text,
            fontSize: 12.5, fontWeight: 700, cursor: "pointer", fontFamily: "inherit",
        }}>↺ Clear</button>
    );

    return (
        <div>
            {/* Three equal tabs, each with its icon. */}
            <div role="tablist" aria-label="How to sign" style={{
                display: "flex", gap: 4, padding: 4, marginBottom: 10,
                background: t.inputBg, border: `1px solid ${t.border}`, borderRadius: 13,
            }}>
                {MODES.map(([m, ico, lbl]) => (
                    <button key={m} type="button" role="tab" aria-selected={mode === m}
                        onClick={() => { setMode(m); setUploadError(null); }}
                        style={{
                            flex: 1, display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 7,
                            height: 40, borderRadius: 10, fontSize: 14, fontFamily: "inherit",
                            fontWeight: 700, border: "none",
                            background: mode === m ? `${t.primary}29` : "transparent",
                            color: mode === m ? t.primary : t.textMuted,
                            boxShadow: mode === m ? `inset 0 0 0 1px ${t.primary}66` : "none",
                            cursor: "pointer", transition: "background .15s, color .15s",
                        }}>
                        {ico ? <Icon d={I[ico]} size={15} /> : <span style={{ fontSize: 13, fontWeight: 800 }}>Aa</span>}{lbl}
                    </button>
                ))}
            </div>

            {mode === "draw" && (
                <div style={pane}>
                    {baseline}
                    <canvas
                        ref={canvasRef} width={760} height={height}
                        onMouseDown={startDraw} onMouseMove={draw}
                        onMouseUp={stopDraw} onMouseLeave={stopDraw}
                        onTouchStart={startDraw} onTouchMove={draw} onTouchEnd={stopDraw}
                        style={{
                            display: "block", width: "100%", height,
                            cursor: "crosshair", touchAction: "none",
                            position: "relative", zIndex: 1,
                        }}
                    />
                    {clearBtn}
                    {hint(drawn ? "Looks good — click “Use this signature”" : "Sign above the line with your mouse or finger")}
                </div>
            )}

            {mode === "type" && (
                <div style={pane}>
                    {baseline}
                    <input
                        value={typed}
                        onChange={e => setTyped(e.target.value)}
                        placeholder="Type your name…"
                        aria-label="Type your name"
                        style={{
                            position: "relative", zIndex: 1,
                            display: "block", width: "100%", height,
                            background: "transparent", border: "none", outline: "none",
                            color: t.mode === "dark" ? "#E6F4F1" : INK, fontSize: Math.round(height * 0.22),
                            textAlign: "center", boxSizing: "border-box",
                            fontFamily: "'Brush Script MT','Segoe Script',cursive", fontStyle: "italic",
                            padding: "0 24px 26px",
                        }}
                    />
                    {clearBtn}
                    {hint(typed ? "Looks good — click “Use this signature”" : "Type your full name")}
                </div>
            )}

            {mode === "upload" && (
                <div style={{ ...pane, minHeight: height, display: "flex", alignItems: "center", justifyContent: "center" }}>
                    {uploaded ? (
                        <div style={{ width: "100%", padding: "14px 20px 34px", textAlign: "center" }}>
                            <img src={uploaded} alt="Your signature" style={{ maxHeight: height - 70, maxWidth: "100%", objectFit: "contain",
                                filter: t.mode === "dark" ? "invert(1) brightness(1.5)" : "none" }} />
                            {clearBtn}
                            {hint("✓ Signature image ready")}
                        </div>
                    ) : (
                        <label style={{
                            display: "flex", flexDirection: "column", alignItems: "center",
                            justifyContent: "center", gap: 10, width: "100%",
                            minHeight: height, cursor: "pointer", padding: "14px 20px",
                            boxSizing: "border-box", color: t.text,
                        }}>
                            <input type="file" accept="image/*" style={{ display: "none" }} onChange={onFile} />
                            <div style={{
                                width: 48, height: 48, borderRadius: 14, color: t.primary,
                                background: `${t.primary}1A`, border: `1.5px dashed ${t.primary}`,
                                display: "flex", alignItems: "center", justifyContent: "center",
                            }}><Icon d={I.upload} size={20} /></div>
                            <div style={{ textAlign: "center" }}>
                                <div style={{ fontSize: 14, fontWeight: 700 }}>Upload a signature image</div>
                                {/* The REAL limit. The old drop zone said 2MB, which the
                                    server rejects with a 422 nobody could interpret. */}
                                <div style={{ fontSize: 12, color: t.textMuted, marginTop: 3 }}>
                                    PNG or JPG · up to {MAX_IMAGE_LABEL}
                                </div>
                            </div>
                        </label>
                    )}
                </div>
            )}

            {uploadError && (
                <div style={{
                    marginTop: 8, padding: "9px 12px", borderRadius: 9,
                    background: `${t.danger}14`, border: `1px solid ${t.danger}45`,
                    fontSize: 12, color: t.danger, lineHeight: 1.5,
                }}>{uploadError}</div>
            )}
        </div>
    );
}

export { MAX_IMAGE_BYTES, MAX_SIGNATURE_CHARS };
