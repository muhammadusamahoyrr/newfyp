'use client';
/* Types out an answer that has ALREADY been checked (2026-11-22).
 *
 * Chat and research answers are not streamed from the model on purpose: they
 * pass the statement check (generation -> hallucination -> finalizer) first,
 * and that check can add cautions or withdraw a citation. Streaming the raw
 * model text would show a client words that are later corrected. This only
 * reveals the final, checked text quickly, so the screen feels like a live
 * reply without ever showing anything unchecked.
 *
 *   - At most MAX_MS however long the answer is; short ones are quicker.
 *   - Word by word, and an unclosed `**` is closed while typing, so bold text
 *     renders as bold instead of flashing asterisks.
 *   - A click on the text, or "reduce motion" in the OS, shows it all at once.
 *   - `onDone` fires once, when the whole text is shown (also after a skip).
 */
import React, { useEffect, useRef, useState } from "react";

const MAX_MS = 2000;         // never make anyone wait longer than this
const MS_PER_WORD = 36;      // about 28 words a second; long answers hit MAX_MS

/* True when the text should simply appear: the OS asks for reduced motion, or
   there is no animation frame to type with (server render, tests, very old
   browsers). Never a reason to hide or delay the answer. */
function reducedMotion() {
    try {
        if (typeof window === "undefined" || typeof window.requestAnimationFrame !== "function") return true;
        return !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    } catch { return true; }
}

/* Word boundaries of `text`: the index just after each word (and its spaces). */
function wordEnds(text) {
    const ends = [];
    const re = /\S+\s*/g;
    let m;
    while ((m = re.exec(text))) ends.push(m.index + m[0].length);
    if (!ends.length || ends[ends.length - 1] !== text.length) ends.push(text.length);
    return ends;
}

/* A prefix that renders cleanly: an odd number of `**` gets its closer. */
function tidy(prefix) {
    const pairs = (prefix.match(/\*\*/g) || []).length;
    return pairs % 2 ? `${prefix.replace(/\s+$/, "")}**` : prefix;
}

export default function RevealText({ text = "", animate = false, onDone, onProgress, render }) {
    const full = String(text);
    const [shown, setShown] = useState(animate && !reducedMotion() ? 0 : full.length);
    const doneRef = useRef(false);
    const skipRef = useRef(false);

    useEffect(() => {
        doneRef.current = false;
        skipRef.current = false;
        if (!animate || reducedMotion() || !full) {
            setShown(full.length);
            return undefined;
        }
        const ends = wordEnds(full);
        const total = Math.min(MAX_MS, ends.length * MS_PER_WORD);
        const started = performance.now();
        let raf = 0;
        const step = (now) => {
            if (skipRef.current) { setShown(full.length); return; }
            const k = Math.min(1, (now - started) / Math.max(total, 1));
            const idx = Math.min(ends.length - 1, Math.floor(k * ends.length));
            setShown(k >= 1 ? full.length : ends[idx]);
            onProgress?.();
            if (k < 1) raf = window.requestAnimationFrame(step);
        };
        raf = window.requestAnimationFrame(step);
        return () => window.cancelAnimationFrame?.(raf);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [full, animate]);

    const complete = shown >= full.length;
    useEffect(() => {
        if (complete && !doneRef.current) {
            doneRef.current = true;
            onDone?.();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [complete]);

    const visible = complete ? full : tidy(full.slice(0, shown));
    const body = render ? render(visible) : visible;
    if (complete) return <>{body}</>;
    return (
        <span data-revealing-text title="Click to show the whole answer"
              onClick={() => { skipRef.current = true; setShown(full.length); }}
              style={{ cursor: "pointer", display: "block" }}>
            {body}
            <span aria-hidden="true" style={{ display: "inline-block", width: 2, height: "1em", marginLeft: 2,
                verticalAlign: "text-bottom", background: "currentColor", opacity: 0.6,
                animation: "aiBlink 1s step-end infinite" }} />
        </span>
    );
}
