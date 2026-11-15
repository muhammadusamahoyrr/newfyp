'use client';
/* The lawyer's chat with clients (2026-10-19 / 20).
 *
 * "Message client" opens the conversation WITHOUT moving the page. Two ways to
 * show it, the lawyer's choice (remembered on this device):
 *
 *   DOCKED (default)  a full-height panel on the right, OVER the page: the
 *                     page stays as it is, softly dimmed behind it (the dim
 *                     does not block clicks). Several open chats are tabs.
 *   FLOATING          small windows in the corner, as on WhatsApp Web, for a
 *                     lawyer who wants the page at full width.
 *
 * It lives in the lawyer LAYOUT, so it stays open across lawyer pages.
 *   - at most three chats; opening a fourth closes the oldest
 *   - "–" tucks the chat(s) into bubbles that show how many messages are new
 *   - the chat on screen marks its thread read (server-side receipts, right
 *     on every device) and keeps doing so as messages arrive
 * The thread is the shared AppointmentThread: the server still decides who may
 * read and whether it is open for sending. */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { AppointmentThread } from "@/components/shared/AppointmentThread.jsx";
import { getThreadSummary, markThreadRead } from "@/lib/api.js";
import { onNotification } from "@/lib/notificationTarget.js";
import { formatPkt } from "@/lib/bookingTime.js";
import { DRAFTING_TOKENS_CSS } from "./draftingTheme.js";

const DockCtx = createContext(null);
/** null outside the lawyer layout (tests, other roles): callers fall back. */
export const useChatDock = () => useContext(DockCtx);

const MAX_WINDOWS = 3;
const DOCK_WIDTH = 400;
const MODE_KEY = "attorney:lawyer-chat-docked";
// One click fills the composer; the lawyer can still edit before sending.
const QUICK_REPLIES = [
    "Please bring your documents to the meeting.",
    "I'm running 10 minutes late.",
    "See you at the scheduled time.",
    "Could you share a short summary of your matter?",
];

export const LAWYER_CHAT_PALETTE = {
    text: "var(--ink)", muted: "var(--muted)", faint: "var(--faint)", border: "var(--line)", surface: "var(--surface)",
    // Send is blue: it stands apart from the green "Join video" and reads as
    // the one action in the composer.
    input: "var(--input)", primary: "#2f6fed", onPrimary: "#fff", danger: "var(--danger)",
    mine: "color-mix(in srgb, #1c9c66 18%, var(--input))",
};

const DOCK_CSS = `body:has([data-video-call]) [data-chat-scrim]{display:none}
[data-chat-scrim]{position:fixed;inset:0;z-index:1099;pointer-events:none;background:rgba(4,12,14,.32);animation:cdFade .18s ease}
@keyframes cdFade{from{opacity:0}to{opacity:1}}
@keyframes cdSlide{from{transform:translateX(24px);opacity:.4}to{transform:none;opacity:1}}
[data-chat-dock]{position:fixed;right:16px;bottom:16px;z-index:1100;display:flex;align-items:flex-end;gap:12px;pointer-events:none;font-family:"Hanken Grotesk",system-ui,sans-serif}
[data-chat-dock]>*{pointer-events:auto}
[data-chat-panel]{position:fixed;top:0;right:0;bottom:0;width:${DOCK_WIDTH}px;z-index:1100;animation:cdSlide .2s ease;display:flex;flex-direction:column;background:var(--surface);color:var(--ink);border-left:1px solid var(--line-strong);box-shadow:-14px 0 40px -24px rgba(0,0,0,.55);font-family:"Hanken Grotesk",system-ui,sans-serif}
.cd-win{width:360px;height:min(480px,62vh);min-height:300px;display:flex;flex-direction:column;background:var(--surface);color:var(--ink);border:1px solid var(--line-strong);border-radius:18px;box-shadow:0 18px 50px -14px rgba(0,0,0,.6),0 0 0 1px rgba(0,0,0,.08);overflow:hidden}
.cd-head{display:flex;align-items:center;gap:10px;padding:10px 12px;border-bottom:1px solid var(--line);background:var(--surface-2)}
[data-chat-panel] .cd-head{padding:14px 14px 12px}
.cd-av{width:34px;height:34px;border-radius:50%;display:grid;place-items:center;font-size:12.5px;font-weight:800;color:#fff;background:linear-gradient(135deg,#12897f,#1c9c66);flex:none}
.cd-who{flex:1;min-width:0}
.cd-who b{display:block;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cd-who small{display:block;font-size:11.5px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cd-ic{width:30px;height:30px;border-radius:8px;border:none;background:transparent;color:var(--muted);cursor:pointer;display:grid;place-items:center;font:inherit;font-size:16px;flex:none}
.cd-ic:hover{background:var(--chip-n);color:var(--ink)}
.cd-tabs{display:flex;gap:6px;padding:8px 12px;border-bottom:1px solid var(--line);overflow-x:auto;scrollbar-width:none}
.cd-tab{display:flex;align-items:center;gap:6px;height:30px;padding:0 6px 0 10px;border-radius:999px;border:1px solid var(--line);background:transparent;color:var(--muted);font:inherit;font-size:12.5px;font-weight:700;cursor:pointer;white-space:nowrap}
.cd-tab[aria-selected=true]{background:var(--chip-n);color:var(--ink);border-color:var(--line-strong)}
.cd-tab .x{width:18px;height:18px;border-radius:50%;display:grid;place-items:center;font-size:11px;color:var(--faint)}
.cd-tab .x:hover{background:var(--chip-n);color:var(--ink)}
.cd-body{flex:1;min-height:0;overflow:hidden;padding:12px 12px 10px;display:flex;flex-direction:column}
[data-chat-panel] .cd-body{padding:14px 14px 14px}
.cd-body>section{flex:1;min-height:0}
.cd-pill{display:flex;align-items:center;gap:8px;height:44px;padding:0 14px 0 6px;border-radius:999px;border:1px solid var(--line-strong);background:var(--surface);color:var(--ink);box-shadow:0 8px 24px -10px rgba(0,0,0,.6);cursor:pointer;font:inherit;font-size:13px;font-weight:700}
.cd-pill .cd-av{width:32px;height:32px}
.cd-badge{min-width:20px;height:20px;padding:0 6px;border-radius:999px;background:#e5484d;color:#fff;font-size:11.5px;font-weight:800;display:grid;place-items:center}`;

const initials = name => String(name || "C").split(" ").filter(Boolean).map(w => w[0]).join("").toUpperCase().slice(0, 2) || "C";
const first = name => String(name || "Client").split(" ")[0];
const whenOf = at => formatPkt(at, { weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });

function readMode() {
    try { return localStorage.getItem(MODE_KEY) !== "0"; } catch { return true; }
}

export function ChatDockProvider({ children }) {
    const [chats, setChats] = useState([]);          // [{ id, client, at, min }]
    const [active, setActive] = useState(null);      // the docked panel's tab
    const [docked, setDocked] = useState(true);
    const [dark, setDark] = useState(true);
    const [unread, setUnread] = useState({});        // id -> count, for chats not on screen
    const [readTick, setReadTick] = useState(0);     // bumps when a thread is marked read
    const chatsRef = useRef(chats);
    chatsRef.current = chats;
    useEffect(() => { setDocked(readMode()); }, []);

    const openChat = useCallback((c) => {
        if (!c?.id) return;
        setChats(list => {
            const next = [...list.filter(x => x.id !== c.id), { id: c.id, client: c.client, at: c.at || null, min: false }].slice(-MAX_WINDOWS);
            // Docked: the panel is one surface, so opening any chat shows it.
            return next.map(x => ({ ...x, min: x.id === c.id ? false : x.min }));
        });
        setActive(c.id);
    }, []);
    const closeChat = useCallback(id => {
        setChats(list => list.filter(x => x.id !== id));
        setActive(a => (a === id ? null : a));
    }, []);
    const toggleChat = useCallback(id => setChats(list => list.map(x => (x.id === id ? { ...x, min: !x.min } : x))), []);
    const tuckAll = useCallback(() => setChats(list => list.map(x => ({ ...x, min: true }))), []);
    const showFromBubble = useCallback((id) => {
        if (docked) { setChats(list => list.map(x => ({ ...x, min: false }))); setActive(id); }
        else toggleChat(id);
    }, [docked, toggleChat]);
    const switchMode = useCallback(() => {
        setDocked(d => {
            try { localStorage.setItem(MODE_KEY, d ? "0" : "1"); } catch { /* storage off */ }
            return !d;
        });
    }, []);

    const open = chats.filter(c => !c.min);
    const shownActive = docked ? (open.find(c => c.id === active) || open[open.length - 1] || null) : null;
    // What is on screen has been read.
    const onScreen = docked ? (shownActive ? [shownActive.id] : []) : open.map(c => c.id);
    const onScreenKey = onScreen.join(",");
    const onScreenRef = useRef(onScreen);
    onScreenRef.current = onScreen;

    const markRead = useCallback(async (id) => {
        const { error } = await markThreadRead(id);
        if (!error) {
            setUnread(u => ({ ...u, [id]: 0 }));
            setReadTick(n => n + 1);
        }
    }, []);
    useEffect(() => { onScreenKey.split(",").filter(Boolean).forEach(markRead); }, [onScreenKey, markRead]);

    // A new message: the chat on screen reads it; any other counts it.
    useEffect(() => onNotification((n) => {
        if (String(n.type || "") !== "appointment_message") return;
        const id = n.payload?.appointment_id;
        if (!chatsRef.current.some(x => x.id === id)) return;
        if (onScreenRef.current.includes(id)) markRead(id);
        else setUnread(u => ({ ...u, [id]: (u[id] || 0) + 1 }));
    }), [markRead]);
    // Chats not on screen show the server's count (right after a reload too).
    const offKey = chats.filter(c => !onScreen.includes(c.id)).map(c => c.id).join(",");
    useEffect(() => {
        if (!offKey) return;
        let alive = true;
        getThreadSummary(offKey.split(",")).then(({ data }) => {
            if (!alive || !data?.items) return;
            setUnread(u => ({ ...u, ...Object.fromEntries(Object.entries(data.items).map(([k, v]) => [k, v.unread || 0])) }));
        });
        return () => { alive = false; };
    }, [offKey]);

    const panelShown = docked && Boolean(shownActive);

    const value = useMemo(() => ({ openChat, closeChat, setDark, readTick }), [openChat, closeChat, readTick]);
    const mode = dark ? "dark" : "light";

    const thread = (c) => (
        <div className="cd-body" data-lenis-prevent>
            <AppointmentThread key={c.id} appointmentId={c.id} palette={LAWYER_CHAT_PALETTE}
                counterpart={first(c.client)} title={`Messages with ${c.client || "the client"}`}
                compact suggestions={QUICK_REPLIES} />
        </div>
    );
    const headerButtons = (c, onMin) => (<>
        <button type="button" className="cd-ic" data-chat-mode onClick={e => { e.stopPropagation(); switchMode(); }}
            aria-label={docked ? "Pop out into a small window" : "Dock to the side, full height"}
            title={docked ? "Pop out (small window)" : "Dock to the side"}>{docked ? "⧉" : "⤢"}</button>
        <button type="button" className="cd-ic" aria-label="Minimise" title="Minimise (Esc)" data-chat-min
            onClick={e => { e.stopPropagation(); onMin(); }}>–</button>
        <button type="button" className="cd-ic" aria-label="Close" title="Close" data-chat-close
            onClick={e => { e.stopPropagation(); closeChat(c.id); }}>✕</button>
    </>);
    const bubbles = chats.filter(c => !onScreen.includes(c.id) && (!docked || !panelShown || c.min));

    return (
        <DockCtx.Provider value={value}>
            {children}
            {chats.length > 0 && (<>
                <style>{DRAFTING_TOKENS_CSS}{DOCK_CSS}</style>
                {panelShown && <div data-chat-scrim aria-hidden="true" />}
                {panelShown && (
                    <aside data-chat-panel data-drafting-theme data-mode={mode} data-chat-window={shownActive.id}
                        aria-label={`Messages with ${shownActive.client}`}
                        onKeyDown={e => { if (e.key === "Escape") tuckAll(); }}>
                        <div className="cd-head">
                            <span className="cd-av">{initials(shownActive.client)}</span>
                            <span className="cd-who">
                                <b>{shownActive.client || "Client"}</b>
                                {shownActive.at && <small>Appointment · {whenOf(shownActive.at)}</small>}
                            </span>
                            {headerButtons(shownActive, tuckAll)}
                        </div>
                        {open.length > 1 && (
                            <div className="cd-tabs" role="tablist" aria-label="Open conversations">
                                {open.map(c => (
                                    <button key={c.id} type="button" role="tab" className="cd-tab" data-chat-tab={c.id}
                                        aria-selected={c.id === shownActive.id} onClick={() => setActive(c.id)}>
                                        {first(c.client)}
                                        {unread[c.id] > 0 && c.id !== shownActive.id && <span className="cd-badge">{unread[c.id]}</span>}
                                        <span className="x" role="button" aria-label={`Close ${first(c.client)}`}
                                            onClick={e => { e.stopPropagation(); closeChat(c.id); }}>✕</span>
                                    </button>
                                ))}
                            </div>
                        )}
                        {thread(shownActive)}
                    </aside>
                )}
                <div data-chat-dock data-drafting-theme data-mode={mode} aria-label="Conversations"
                    style={panelShown ? { right: DOCK_WIDTH + 16 } : undefined}>
                    {bubbles.map(c => (
                        <button key={c.id} type="button" className="cd-pill" data-chat-pill={c.id} onClick={() => showFromBubble(c.id)}
                            aria-label={`Open messages with ${c.client}${unread[c.id] ? `, ${unread[c.id]} new` : ""}`}>
                            <span className="cd-av">{initials(c.client)}</span>
                            {first(c.client)}
                            {unread[c.id] > 0 && <span className="cd-badge" data-chat-unread>{unread[c.id]}</span>}
                        </button>
                    ))}
                    {!docked && open.map(c => (
                        <section key={c.id} className="cd-win" data-chat-window={c.id} aria-label={`Messages with ${c.client}`}
                            onKeyDown={e => { if (e.key === "Escape") toggleChat(c.id); }}>
                            <div className="cd-head" style={{ cursor: "pointer" }} onClick={() => toggleChat(c.id)}>
                                <span className="cd-av">{initials(c.client)}</span>
                                <span className="cd-who">
                                    <b>{c.client || "Client"}</b>
                                    {c.at && <small>Appointment · {whenOf(c.at)}</small>}
                                </span>
                                {headerButtons(c, () => toggleChat(c.id))}
                            </div>
                            {thread(c)}
                        </section>
                    ))}
                </div>
            </>)}
        </DockCtx.Provider>
    );
}
