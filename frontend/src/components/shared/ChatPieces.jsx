/* Chat pieces shared by the client chat and the lawyer AI Assistant
 * (2026-10-19): the answer's action row (Copy, Helpful, Not helpful,
 * Regenerate) and the message bubbles, avatar and Stop pill. Moved here from
 * client/ModChatbot.jsx unchanged so both sides look and behave the same. Each
 * page sets its own colours through CSS variables. */
import { useState } from "react";
import { copyText } from "@/lib/trust.js";

/* Under an answer: Copy, Helpful, Not helpful -- plain line icons, as other
 * chat apps show them (2026-10-19). No emoji, no reference chip: the answer's
 * id still goes with every rating, which is how a reported answer is found. */
const ACTION_ICON = {
    copy: ["M8 8h12v12H8z", "M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"],
    check: ["M20 6 9 17l-5-5"],
    up: ["M7 10v11", "M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z"],
    regenerate: ["M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8", "M21 3v5h-5"],
    down: ["M17 14V3", "M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22a3.13 3.13 0 0 1-3-3.88Z"],
};
const MSG_ACTIONS_CSS = `[data-msg-actions]{display:flex;align-items:center;gap:2px;margin-top:6px}
[data-msg-actions] button{width:26px;height:26px;display:grid;place-items:center;border:0;border-radius:7px;background:transparent;color:var(--ma-ink);cursor:pointer;transition:background .15s,color .15s}
[data-msg-actions] button:hover{background:var(--ma-hover);color:var(--ma-strong)}
[data-msg-actions] button:focus-visible{outline:2px solid var(--ma-strong);outline-offset:1px}
[data-msg-actions] button[aria-pressed="true"]{color:var(--ma-strong)}`;

function ActionIcon({ name, filled = false }) {
    return (
        <svg width="15" height="15" viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"} stroke="currentColor"
            strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            {ACTION_ICON[name].map(d => <path key={d} d={d} />)}
        </svg>
    );
}

export function MessageActions({ text, canRate, rated, onRate, onRegenerate = null, t }) {
    const [copied, setCopied] = useState(false);
    return (
        <div data-msg-actions style={{ "--ma-ink": t.textMuted, "--ma-strong": t.text, "--ma-hover": t.border }}>
            <style>{MSG_ACTIONS_CSS}</style>
            <button type="button" aria-label={copied ? "Copied" : "Copy"} title={copied ? "Copied" : "Copy"}
                onClick={async () => { const ok = await copyText(text); setCopied(ok); if (ok) setTimeout(() => setCopied(false), 1600); }}>
                <ActionIcon name={copied ? "check" : "copy"} />
            </button>
            {canRate && ["up", "down"].filter(r => !rated || rated === r).map(r => (
                <button key={r} type="button" aria-pressed={rated === r} disabled={Boolean(rated)}
                    aria-label={r === "up" ? "Helpful" : "Not helpful"}
                    title={rated ? "Thanks for the feedback" : r === "up" ? "Helpful" : "Not helpful"}
                    onClick={() => onRate(r)} style={rated ? { cursor: "default" } : undefined}>
                    <ActionIcon name={r} filled={rated === r} />
                </button>
            ))}
            {onRegenerate && (
                <button type="button" aria-label="Regenerate" title="Regenerate" onClick={onRegenerate}>
                    <ActionIcon name="regenerate" />
                </button>
            )}
        </div>
    );
}

/* Message bubbles (2026-10-19): round, solid, with a small tail at the
 * bottom corner nearest the speaker -- the user's on the right, the AI's on
 * the left. Two pieces make the soft S-bend (2026-10-19): one in the bubble's
 * colour with a rounded foot, and one in the page colour (--bub-page) that
 * rounds the outer side back in. Colours follow the theme. */
export const BUBBLE_CSS = `[data-bubble]{position:relative;background:var(--bub);border-radius:20px}
/* While a checked answer is typing out (RevealText), what sits under the bubble -- statement checks,
   sources, lawyer suggestions, copy/rate -- waits until the text is complete, as in a live reply. */
[data-revealing]>:not([data-bubble]){display:none!important}
/* ...and inside the bubble too: the lawyer page renders its evidence check and citations there. */
[data-revealing-text]~*{display:none!important}
@keyframes aiBlink{50%{opacity:0}}
[data-bubble]::before,[data-bubble]::after{content:"";position:absolute;bottom:0;height:20px;pointer-events:none}
[data-bubble]::before{z-index:0;width:20px;background:var(--bub-tail,var(--bub))}
[data-bubble]::after{z-index:1;width:10px;background:var(--bub-page,var(--bg,#403E42))}
[data-bubble="user"]::before{right:-8px;border-bottom-left-radius:16px 14px}
[data-bubble="user"]::after{right:-10px;border-bottom-left-radius:10px}
[data-bubble="ai"]::before{left:-8px;border-bottom-right-radius:16px 14px}
[data-bubble="ai"]::after{left:-10px;border-bottom-right-radius:10px}
[data-typing] .stop-gen{display:inline-flex;align-items:center;gap:7px;height:28px;padding:0 13px;border-radius:999px;border:1px solid var(--line-strong);background:var(--surface);color:var(--muted);font:inherit;font-size:12px;font-weight:600;cursor:pointer;transition:border-color .15s,color .15s}
[data-typing] .stop-gen:hover{border-color:var(--chat-accent,var(--teal));color:var(--chat-accent,var(--teal))}
[data-ai-avatar]{width:32px;height:32px;display:grid;place-items:center}
[data-ai-avatar]>span{width:30px;height:30px;background:var(--chat-mark,var(--brand-solid));-webkit-mask:url(/logo-mark.png) center/contain no-repeat;mask:url(/logo-mark.png) center/contain no-repeat}`;
