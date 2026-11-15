'use client';
/* Review a lawyer, right where the client is (2026-10-20).
 *
 * The Appointments page's "Review" used to send the client to the Lawyers
 * page to find the form. This is the same review -- the same server rule
 * (GET /lawyers/{id}/review-eligibility) and the same submit
 * (POST /lawyers/{id}/review) -- in a dialog over the page they are on.
 *
 * States are kept apart: checking, could-not-check (with Retry), already
 * reviewed, not yet allowed (and why), the form, and done. A failed check is
 * never shown as "you can't review". */
import { useCallback, useEffect, useRef, useState } from "react";
import { ModalPortal, BACKDROP } from "@/components/shared/ui/primitives.jsx";
import { getReviewEligibility, submitReview } from "@/lib/api.js";

const WORDS = ["", "Poor", "Fair", "Good", "Very good", "Excellent"];
const COMMENT_MAX = 1000;
const STAR = "12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2";

export default function ReviewLawyerDialog({ lawyerId, lawyerName, t, onClose, onDone = null }) {
    const first = String(lawyerName || "this lawyer").split(" ")[0];
    const [elig, setElig] = useState({ state: "loading" });
    const [stars, setStars] = useState(0);
    const [hover, setHover] = useState(0);
    const [comment, setComment] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);
    const [done, setDone] = useState(false);
    const panel = useRef(null);

    const check = useCallback(() => {
        setElig({ state: "loading" });
        getReviewEligibility(lawyerId).then(({ data, error: e }) => {
            setElig(e || !data ? { state: "error" } : { state: "ready", data });
        }).catch(() => setElig({ state: "error" }));
    }, [lawyerId]);
    useEffect(() => { check(); }, [check]);
    useEffect(() => {
        panel.current?.focus();
        const esc = (e) => { if (e.key === "Escape" && !busy) onClose(); };
        window.addEventListener("keydown", esc);
        return () => window.removeEventListener("keydown", esc);
    }, [busy, onClose]);

    const send = async () => {
        if (!stars) { setError("Choose a rating from 1 to 5 stars."); return; }
        setBusy(true); setError(null);
        const { error: e } = await submitReview(lawyerId, stars, comment.trim() || null);
        setBusy(false);
        if (e) { setError(e.message || "Could not submit your review. Try again."); return; }
        setDone(true);
        onDone?.();
    };

    const shown = hover || stars;
    const btn = (primary) => ({
        height: 44, padding: "0 20px", borderRadius: 12, fontFamily: "inherit", fontSize: 14, fontWeight: 700, cursor: "pointer",
        border: primary ? "none" : `1px solid ${t.border}`, background: primary ? t.primary : "transparent",
        color: primary ? "#06211a" : t.text,
    });
    const note = (text, tone = t.textMuted) => <div style={{ fontSize: 14, color: tone, lineHeight: 1.55 }}>{text}</div>;

    let body;
    if (done) {
        body = (<>
            {note(<><b style={{ color: t.text }}>Thank you.</b> Your review of {first} is posted and helps other clients choose.</>)}
            <div style={{ display: "flex", justifyContent: "flex-end" }}><button type="button" style={btn(true)} onClick={onClose}>Done</button></div>
        </>);
    } else if (elig.state === "loading") {
        body = note("Checking whether you can review…");
    } else if (elig.state === "error") {
        body = (<div role="alert" style={{ display: "flex", alignItems: "center", gap: 12 }}>
            {note(`Could not check whether you can review ${first}. This is not the same as "not allowed".`)}
            <button type="button" style={{ ...btn(false), flex: "none" }} onClick={check}>Retry</button>
        </div>);
    } else if (elig.data.already_reviewed) {
        body = (<>
            {note(<><b style={{ color: t.text }}>✓ You have already reviewed {first}.</b> Thank you.</>)}
            <div style={{ display: "flex", justifyContent: "flex-end" }}><button type="button" style={btn(false)} onClick={onClose}>Close</button></div>
        </>);
    } else if (!elig.data.can_review) {
        body = (<>
            {note(`You can review ${first} after a completed consultation with them, or once they have taken your case.`)}
            <div style={{ display: "flex", justifyContent: "flex-end" }}><button type="button" style={btn(false)} onClick={onClose}>Close</button></div>
        </>);
    } else {
        body = (<>
            <div>
                <div style={{ fontSize: 12, fontWeight: 800, letterSpacing: ".06em", textTransform: "uppercase", color: t.textMuted, marginBottom: 8 }}>Your rating</div>
                <div role="radiogroup" aria-label="Rating" style={{ display: "flex", alignItems: "center", gap: 6 }} onMouseLeave={() => setHover(0)}>
                    {[1, 2, 3, 4, 5].map(s => (
                        <button key={s} type="button" role="radio" aria-checked={stars === s} aria-label={`${s} star${s === 1 ? "" : "s"} — ${WORDS[s]}`}
                            data-review-star={s} onMouseEnter={() => setHover(s)} onClick={() => { setStars(s); setError(null); }}
                            style={{ background: "none", border: "none", cursor: "pointer", padding: 2, lineHeight: 0 }}>
                            <svg width={34} height={34} viewBox="0 0 24 24" aria-hidden="true">
                                <polygon points={STAR} fill={s <= shown ? "#F2C35E" : "transparent"} stroke={s <= shown ? "#F2C35E" : t.border} strokeWidth="1.5" strokeLinejoin="round" />
                            </svg>
                        </button>
                    ))}
                    <span style={{ marginLeft: 8, fontSize: 14, fontWeight: 700, color: shown ? t.text : t.textMuted }}>{shown ? WORDS[shown] : "Tap a star"}</span>
                </div>
            </div>
            <div>
                <label htmlFor="rv-comment" style={{ display: "block", fontSize: 12, fontWeight: 800, letterSpacing: ".06em", textTransform: "uppercase", color: t.textMuted, marginBottom: 8 }}>
                    Your experience <span style={{ textTransform: "none", letterSpacing: 0, fontWeight: 500 }}>(optional)</span>
                </label>
                <textarea id="rv-comment" rows={4} maxLength={COMMENT_MAX} value={comment} onChange={e => setComment(e.target.value)}
                    placeholder={`How was your consultation with ${first}? Was the advice clear and useful?`}
                    style={{ width: "100%", minHeight: 96, padding: "10px 12px", borderRadius: 12, border: `1px solid ${t.border}`, background: t.inputBg, color: t.text, fontSize: 14, fontFamily: "inherit", outline: "none", resize: "vertical", boxSizing: "border-box" }} />
                <div style={{ textAlign: "right", fontSize: 11.5, color: t.textFaint || t.textMuted, marginTop: 4 }}>{comment.length} / {COMMENT_MAX}</div>
            </div>
            {note("Your name and rating are shown with the review. Keep it about the service — no case details.", t.textMuted)}
            {error && <div role="alert" data-review-error style={{ fontSize: 13, fontWeight: 600, color: t.danger || "#e8526a" }}>{error}</div>}
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
                <button type="button" style={btn(false)} onClick={onClose} disabled={busy}>Cancel</button>
                <button type="button" data-review-submit style={{ ...btn(true), opacity: busy ? .7 : 1 }} onClick={send} disabled={busy}>
                    {busy ? "Submitting…" : "Submit review"}
                </button>
            </div>
        </>);
    }

    return (
        <ModalPortal>
            <div data-lenis-prevent style={{ ...BACKDROP, display: "grid", placeItems: "center", padding: 20 }}
                onClick={() => { if (!busy) onClose(); }}>
                <div ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-label={`Review ${lawyerName || "lawyer"}`}
                    data-review-dialog={elig.state === "ready" ? (elig.data.already_reviewed ? "done" : elig.data.can_review ? "can" : "not-eligible") : elig.state}
                    onClick={e => e.stopPropagation()}
                    style={{ width: "min(520px, 100%)", borderRadius: 20, background: t.card, border: `1px solid ${t.border}`, boxShadow: "0 30px 80px rgba(0,0,0,.45)",
                        padding: "24px 26px", display: "flex", flexDirection: "column", gap: 18, outline: "none", color: t.text }}>
                    <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontSize: 22, fontWeight: 800, color: t.text }}>Review {lawyerName || "your lawyer"}</div>
                            <div style={{ fontSize: 13, color: t.textMuted, marginTop: 3 }}>Rate your consultation — it helps other clients choose.</div>
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
