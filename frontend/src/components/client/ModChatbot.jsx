'use client';
import React, { useState, useRef, useEffect, useCallback } from "react";
import VoiceButton, { SendArrow } from "@/components/shared/VoiceButton.jsx";
import RichText from "@/components/shared/RichText.jsx";
import RevealText from "@/components/shared/RevealText.jsx";
import { useClientRouter as useRouter } from "./clientNav.js";
import { useT } from "./theme.js";
import { useToast } from "@/components/shared/Toast.jsx";
import { useCase } from "@/components/shared/CaseContext.jsx";
import {
    getToken, rateAnswer, getWsTicket, websocketUrl, openSourceDocument, cancelClientTurn,
    searchConversations,
    listConversations, createConversation, getConversation,
    renameConversation, deleteConversation,
} from "@/lib/api.js";
/* Rehydration lives in a pure module so it can be tested directly: a
   reloaded answer must be qualified exactly as it was when first given, and
   silently losing a repeal warning on reload is the failure worth guarding. */
import {
    toClientMessages, groupConversations, readActiveSession,
    writeActiveSession, mergeMessages,
} from "@/lib/conversations.js";
import { createGeneration, newAttempt } from "@/lib/attempt.js";
import { createSocketOwner } from "@/lib/socket.js";
import { useAuth } from "@/context/AuthContext.jsx";
import Ic from "./Ic.jsx";
import LawyerMatchPanel from "./LawyerMatchPanel.jsx";
import { Badge } from "@/components/shared/shared.jsx";
import { MessageActions, BUBBLE_CSS } from "@/components/shared/ChatPieces.jsx";
export { MessageActions };
/* Shared with both lawyer AI surfaces so the three cannot describe the same
   backend fields differently — the client used to drop `source` and `url`
   entirely, leaving every chip unclickable. */
import {
    CITATION_GROUPS, REPEALED, normaliseCitations, citationsInGroup,
    citationSummary, copyText, auditNotice,
} from "@/lib/trust.js";

/* Calibrated-confidence bands come from the server (ai/answer_confidence.py).
   The client shows the BAND only — the raw calibrated figure runs far lower than
   the model's old self-report, and a bare "24%" reads as broken to a non-lawyer
   when it is in fact a normal, honest score. The lawyer surface shows both. */
const CONF_LABEL = { high: "High", moderate: "Moderate", low: "Low" };
const CONF_COLOR = { high: "#22c55e", moderate: "#f59e0b", low: "#ef4444" };

/* Per-statement support verdicts from the grounding judge (answer_citations.py).
   Worded for a non-lawyer, and worded carefully: `unassessed` must read as "we
   did not check", never as "it passed". A statement we could not check is not a
   statement we approved. */
const CLAIM_UI = {
    supported:   { icon: "✓", color: "#22c55e", text: "Backed by the source it cites" },
    partial:     { icon: "!", color: "#f59e0b", text: "Goes further than its source says" },
    unsupported: { icon: "✕", color: "#ef4444", text: "Its source does not establish this" },
    unassessed:  { icon: "–", color: "#94a3b8", text: "Not checked against a source" },
};
const CLAIM_ORDER = ["unsupported", "partial", "unassessed", "supported"];

/* Repeal currency (answer_citations.currency_for). Exactly two values reach the
   UI — `repealed` and `unknown` — and `unknown` must never be dressed up as a
   clean bill of health: repeal data covers 4 of 43 statutes, so silence is
   absence of evidence, not evidence of currency. A repealed provision OVERRIDES
   matched/supported: a source can genuinely say what the answer claims and
   still be law that was abolished. REPEALED now comes from lib/trust.js. */
const CURRENCY_TEXT = {
    repealed: "Repealed provision — do not rely on this authority",
    unknown:  "Current status not verified",
};
const repealNote = (c) => {
    const bits = [c.instrument, c.date].filter(Boolean).join(", ");
    return bits ? `Repealed by ${bits}` : "";
};


/* ══════════════════════════════════════════════════════
   MODULE: AI CHATBOT  (WebSocket-backed)
══════════════════════════════════════════════════════ */
// The history list, styled like the lawyer AI Assistant's (2026-10-19), in the
// client theme's own variables so light mode follows.
// The composer, styled like the lawyer AI Assistant's (2026-10-19).

const CHAT_BOX_CSS = `
[data-chat-box]{width:100%;max-width:980px;box-sizing:border-box;padding:10px 12px 8px 16px;border-radius:18px;border:1px solid var(--line-strong);background:var(--surface);box-shadow:0 30px 60px -30px rgba(0,0,0,.8)}
[data-chat-box]:focus-within{border-color:color-mix(in srgb,var(--brand-text) 55%,transparent)}
[data-chat-box] input::placeholder,[data-chat-box] textarea::placeholder{color:var(--faint)}
[data-chat-box] .cb-chip{display:inline-flex;align-items:center;gap:6px;height:32px;padding:0 11px;border-radius:999px;border:1px solid var(--line-strong);background:var(--surface-2);color:var(--muted);font:inherit;font-size:12.5px;font-weight:600;cursor:pointer;white-space:nowrap}
[data-chat-box] .cb-chip:hover{border-color:var(--hover-line);color:var(--hover-ink)}
[data-chat-box] .cb-chip[aria-pressed="true"]{border-color:var(--hover-line);color:var(--brand-text);background:var(--brand-soft)}
[data-chat-box] select.cb-chip{appearance:none;-webkit-appearance:none;padding-right:26px;background-image:linear-gradient(45deg,transparent 50%,currentColor 50%),linear-gradient(135deg,currentColor 50%,transparent 50%);background-position:calc(100% - 13px) 14px,calc(100% - 9px) 14px;background-size:4px 4px;background-repeat:no-repeat}
[data-chat-box] select.cb-chip.on{color:var(--brand-text)}
[data-chat-box] select.cb-chip option{background:var(--surface);color:var(--ink)}
[data-chat-box] .cb-seg{display:inline-flex;height:32px;padding:2px;border-radius:999px;border:1px solid var(--line-strong);background:var(--surface-2)}
[data-chat-box] .cb-seg button{border:0;border-radius:999px;padding:0 11px;background:none;color:var(--muted);font:inherit;font-size:12px;font-weight:700;cursor:pointer}
[data-chat-box] .cb-seg button[aria-pressed="true"]{background:var(--brand-solid);color:var(--on-brand)}
[data-chat-box] .cb-mic{width:42px;height:42px;display:grid;place-items:center;border:1px solid transparent;border-radius:50%;background:none;color:var(--faint);cursor:pointer;transition:color .15s,background .15s}
[data-chat-box] .cb-mic:hover{border-color:var(--line-strong);color:var(--hover-ink)}
[data-chat-box] .cb-mic.on{color:var(--danger);background:var(--danger-soft);border-color:color-mix(in srgb,var(--danger) 45%,transparent)}
[data-chat-box] .cb-send{width:34px;height:34px;display:grid;place-items:center;padding:0;border:1px solid var(--line-strong);border-radius:50%;background:none;color:var(--faint);cursor:default;transition:background .15s,color .15s,transform .15s,box-shadow .15s}
[data-chat-box] .cb-send:focus-visible{outline:2px solid var(--teal);outline-offset:2px}
[data-chat-box] .cb-send.typed{color:var(--teal)}
[data-chat-box] .cb-send.on{cursor:pointer;border-color:transparent;background:var(--brand-solid);color:var(--on-brand,#fff);box-shadow:0 6px 16px -8px rgba(46,196,214,.7)}
[data-chat-box] .cb-send.on:hover{transform:translateY(-1px)}
`;

const CHAT_HIST_CSS = `
[data-chat-hist] .ch-g{font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:var(--faint);font-weight:600;padding:12px 8px 6px}
[data-chat-hist] .ch-cv{display:flex;align-items:center;gap:4px;padding:8px 9px;border-radius:10px;border:1px solid transparent;margin-bottom:2px;font-size:13px;font-weight:600;color:var(--muted);cursor:pointer}
[data-chat-hist] .ch-cv:hover{background:var(--hover-tint);color:var(--ink)}
[data-chat-hist] .ch-cv.on{background:var(--surface-2);border-color:var(--line-strong);color:var(--ink)}
[data-chat-hist] .ch-more{flex:none;width:24px;height:24px;display:grid;place-items:center;border:0;border-radius:7px;background:none;color:var(--faint);cursor:pointer;opacity:0}
[data-chat-hist] .ch-cv:hover .ch-more,[data-chat-hist] .ch-cv.on .ch-more,[data-chat-hist] .ch-more[aria-expanded="true"]{opacity:1}
[data-chat-hist] .ch-more:hover,[data-chat-hist] .ch-more[aria-expanded="true"]{background:var(--surface-2);color:var(--ink)}
[data-chat-hist] .ch-menu{position:absolute;z-index:60;padding:3px;display:flex;flex-direction:column;border-radius:9px;border:1px solid var(--line-strong);background:var(--surface);box-shadow:0 18px 36px -12px rgba(0,0,0,.6)}
[data-chat-hist] .ch-menu button{display:flex;align-items:center;gap:7px;padding:6px 12px 6px 8px;border:0;border-radius:6px;background:none;color:var(--ink);font-size:12.5px;cursor:pointer;text-align:left}
[data-chat-hist] .ch-menu button:hover{background:var(--surface-2)}
[data-chat-hist] .ch-menu button svg{width:13px;height:13px;color:var(--faint)}
[data-chat-hist] .ch-menu button.danger,[data-chat-hist] .ch-menu button.danger svg{color:var(--danger)}
[data-chat-hist] .ch-foot{padding:10px 14px;border-top:1px solid var(--line);font-size:11.5px;color:var(--faint);display:flex;justify-content:space-between;gap:10px;white-space:nowrap}
[data-chat-hist] .ch-foot>span:first-child{min-width:0;overflow:hidden;text-overflow:ellipsis}
[data-chat-hist] .ch-foot>span:last-child{flex-shrink:0}
`;

/* The empty chat (Version C, approved 2026-11-23): the logo mark, a plain
 * greeting, the input right under it, four specific starter questions and
 * one line on what this chat can and cannot do. Theme vars only. */
const STARTER_QUESTIONS = [
    { area: "Criminal", text: "How do I get bail after an FIR is registered?" },
    { area: "Property", text: "My landlord wants me out without notice. What are my rights?" },
    { area: "Family", text: "What is the process for khula in Punjab?" },
    { area: "Money", text: "A cheque given to me bounced. What can I do?" },
];

/* About eight lines of 15px text; longer questions scroll inside the box. */
const MAX_INPUT_HEIGHT = 200;

const CHAT_WELCOME_CSS = `
[data-chat-welcome]{width:100%;max-width:760px;display:flex;flex-direction:column;gap:22px}
[data-chat-welcome] [data-chat-box]{max-width:none}
[data-chat-welcome] .cw-q{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));grid-auto-rows:1fr;gap:8px}
[data-chat-welcome] .cw-q button{display:flex;flex-direction:column;justify-content:flex-start;min-height:72px;box-sizing:border-box;text-align:left;padding:11px 14px;border-radius:12px;border:1px solid var(--line-strong);background:transparent;color:var(--ink);font:inherit;font-size:13.5px;line-height:1.4;cursor:pointer;transition:border-color .15s,background .15s}
[data-chat-welcome] .cw-q button:hover{border-color:var(--hover-line);background:var(--hover-tint)}
[data-chat-welcome] .cw-q button:focus-visible{outline:2px solid var(--teal);outline-offset:2px}
[data-chat-welcome] .cw-q b{display:block;font-size:11.5px;font-weight:600;color:var(--faint);margin-bottom:2px}
[data-chat-welcome] .cw-links a{color:var(--brand-text);font-weight:600;text-decoration:none}
[data-chat-welcome] .cw-links a:hover{text-decoration:underline}
`;

const ModChatbot = () => {
    const t = useT();
    const toast = useToast();
    const router = useRouter();
    const { caseType } = useCase();
    const { user } = useAuth();

    /* ── UI state ─────────────────────────────────────────────────────── */
    const [msgs, setMsgs] = useState([]);
    const [inp, setInp] = useState("");
    const inpRef = useRef(null);
    // The box fits its text on every change — typing, a starter question,
    // voice, or the clear after sending — up to MAX_INPUT_HEIGHT, then scrolls.
    useEffect(() => {
        const el = inpRef.current;
        if (!el) return;
        el.style.height = "auto";
        const full = el.scrollHeight;
        el.style.height = `${Math.min(full, MAX_INPUT_HEIGHT)}px`;
        el.style.overflowY = full > MAX_INPUT_HEIGHT ? "auto" : "hidden";
        if (full > MAX_INPUT_HEIGHT && document.activeElement === el
            && el.selectionStart === el.value.length) el.scrollTop = el.scrollHeight;
    }, [inp]);
    const [typing, setTyping] = useState(false);
    // No EN/UR switch on the composer (2026-10-19). Voice (2026-10-20) writes
    // Urdu speech in Urdu script; the backend answers in the question's language.
    const [sideOpen, setSideOpen] = useState(true);
    // Web search is not offered on the client chat (2026-10-19).
    const webSearch = false;
    // Jurisdiction. The client used to send province: null on every message,
    // which the backend resolved to "unknown" — and the province filter turned
    // that into federal-only, hiding ~1,600 provincial sections. Retrieval no
    // longer narrows on unknown, but stating the province still gives a much
    // better answer, so it is asked for explicitly and remembered.
    const [province, setProvince] = useState(() => {
        if (typeof window === "undefined") return "";
        return localStorage.getItem("aai-province") || "";
    });
    useEffect(() => {
        if (typeof window === "undefined") return;
        if (province) localStorage.setItem("aai-province", province);
        else localStorage.removeItem("aai-province");
    }, [province]);
    // Default from the user's own profile when they have not chosen one.
    useEffect(() => {
        if (!province && user?.province) setProvince(String(user.province).toLowerCase());
    }, [user, province]);
    const [listening, setListening] = useState(false);
    // Real conversations, loaded from the server. "Last Week" previously listed
    // two hardcoded strings that were never real chats and could not be opened.
    const [history, setHistory] = useState([]);
    // The rows themselves, ungrouped. `groupConversations` buckets by date for
    // display, and appending a page has to happen on the flat list — merging
    // into the grouped shape would need the grouping undone first.
    const [rows, setRows] = useState([]);
    const [listCursor, setListCursor] = useState(null);
    const [listMore, setListMore] = useState(false);
    const [listLoading, setListLoading] = useState(false);
    const [search, setSearch] = useState("");
    // The "⋯" menu of one history row: { item, x, y } inside the sidebar.
    const [rowMenu, setRowMenu] = useState(null);
    useEffect(() => {
        if (!rowMenu) return undefined;
        const close = (e) => { if (!e.target.closest?.("[data-row-menu], .ch-more")) setRowMenu(null); };
        document.addEventListener("mousedown", close);
        return () => document.removeEventListener("mousedown", close);
    }, [rowMenu]);
    // Conversations matched by what was SAID in them, as opposed to by title.
    // Kept separate from `rows` because they are a different question with a
    // different answer shape — a title match is a row, a message match is a row
    // plus the sentence that matched — and merging them would lose the snippet
    // that makes the second kind worth showing.
    // Below this, a message search matches most of a corpus and ranks
    // none of it usefully — and costs a text query per keystroke.
    const MIN_SEARCH_CHARS = 2;
    const [messageHits, setMessageHits] = useState([]);
    const [unsearchable, setUnsearchable] = useState(false);

    // "Is this list response still wanted?" A search typed quickly issues
    // several requests, and the slowest must not paint over the newest.
    const listGeneration = useRef(createGeneration()).current;

    /* One page of conversations. `after` continues from a cursor; without it
       the list starts again from the top.

       The sidebar used to ask for fifty and stop. A user with a fifty-first
       conversation could not reach it by any route — no cursor, no search, no
       "load more". It was not slow, it was unreachable. */
    const loadHistory = useCallback(async ({ after = null, term = null } = {}) => {
        const ticket = listGeneration.next();
        setListLoading(true);
        const { data } = await listConversations({
            limit: 30, after, search: term ?? null,
        });
        if (!listGeneration.isCurrent(ticket)) return;   // a newer request won
        setListLoading(false);
        if (!data) return;

        const incoming = data.conversations || [];
        setRows(prev => {
            // Appending a page de-duplicates on session id: a conversation
            // that moved while the user was scrolling can legitimately appear
            // in a later read, and rendering it twice looks like data
            // corruption.
            const merged = after ? [...prev, ...incoming] : incoming;
            const seen = new Set();
            const unique = merged.filter(r => {
                if (seen.has(r.session_id)) return false;
                seen.add(r.session_id);
                return true;
            });
            // A chat with no message yet is not history: listing it showed a
            // row of "New conversation" copies. The open one stays (2026-11-23).
            setHistory(groupConversations(unique.filter(r =>
                (r.message_count ?? 1) > 0 || r.session_id === sessionIdRef.current)));
            return unique;
        });

        // Message-body search, alongside the title search above.
        //
        // Two searches rather than one because they answer different questions:
        // the list is "conversations called this", these are "conversations
        // where I said this". Run under the SAME generation ticket, so a stale
        // response cannot paint results for a term the user has moved on from.
        // `term` is the phrase the caller searched for — the same one the
        // list above was filtered by. Reading component state here instead
        // would let the two searches disagree about what was asked.
        const phrase = (term || "").trim();
        if (phrase.length >= MIN_SEARCH_CHARS) {
            const { data: found } = await searchConversations(phrase);
            if (!listGeneration.isCurrent(ticket)) return;
            setMessageHits(found?.results || []);
            setUnsearchable(!!found?.has_unsearchable_history);
        } else {
            setMessageHits([]);
            setUnsearchable(false);
        }
        setListCursor(data.next_cursor || null);
        setListMore(!!data.has_more);
    }, [listGeneration]);

    const refreshHistory = useCallback(
        () => loadHistory({ term: search || null }), [loadHistory, search]);

    const loadMoreHistory = useCallback(
        () => loadHistory({ after: listCursor, term: search || null }),
        [loadHistory, listCursor, search]);

    /* Search re-runs the list from the top, debounced: a request per keystroke
       would have the same slow-response-wins problem the generation ticket
       guards against, at several times the cost. */
    useEffect(() => {
        const timer = setTimeout(
            () => { loadHistory({ term: search || null }); }, 250);
        return () => clearTimeout(timer);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [search]);

    /* ── WebSocket state ──────────────────────────────────────────────── */
    // Who owns the live socket. Not a bare ref: the claim is held across the
    // ticket fetch, which is the window two sockets used to open in. See
    // lib/socket.
    const socket = useRef(createSocketOwner()).current;
    const sessionIdRef = useRef(null);
    const bottomRef = useRef(null);
    const retryRef = useRef(null);
    const stableRef = useRef(null); // timer to reset retry count after stable connection
    const retryCount = useRef(0);
    const listeningRef = useRef(false); // mirror of `listening` state for WS closures
    const [wsStatus, setWsStatus] = useState("disconnected");

    /* The active conversation.
       Previously a fresh id was minted on every mount, so a refresh started a
       new conversation and the previous one became unreachable — still in the
       database, with no id anywhere pointing at it. The id is now created by
       the server and remembered here, so a reload reopens the same thread. */
    const [sessionReady, setSessionReady] = useState(false);
    const [loadingHistory, setLoadingHistory] = useState(false);
    // "Is this response still wanted?" Selecting A then B used to let A's
    // slower page loop call setMsgs last, so B's socket was live while A's
    // history was on screen — and the next message went into B under A's
    // visible conversation.
    const openGeneration = useRef(createGeneration()).current;
    // The attempt in flight, so a retry can reuse its id. Null once the answer
    // (or a refusal, or a cancellation) has arrived.
    const attemptRef = useRef(null);
    // What the pipeline is doing, in words a user can act on. "Thinking" for
    // thirty seconds is indistinguishable from broken.
    const [stage, setStage] = useState(null);
    // Fires if no answer arrives at all. Deliberately longer than the server's
    // own turn timeout, so the server's honest message wins when it can.
    const deadlineRef = useRef(null);
    // Re-asks "is my answer ready?" while a recovered turn is still running.
    // The server replies to `resume` once and never pushes the answer to the
    // new socket by itself, so without asking again the answer is never seen.
    const resumePollRef = useRef(null);
    // Walking BACKWARDS through history. `olderCursor` is the sequence of the
    // oldest message on screen; the next request asks for what precedes it.
    const [olderCursor, setOlderCursor] = useState(null);
    const [hasOlder, setHasOlder] = useState(false);
    const [loadingOlder, setLoadingOlder] = useState(false);

    /* ── WebSocket connect ────────────────────────────────────────────── */
    const connect = useCallback(async () => {
        const token = getToken();
        if (!token) return;                              // not logged in

        // Claim BEFORE the first await.
        //
        // The old guard was a readyState check, which is blind during the
        // ticket fetch below: nothing is CONNECTING because no socket exists
        // yet, so a reconnect timer and a conversation switch both passed it
        // and both opened a socket. The claim is held across the await, and a
        // claim superseded meanwhile closes its socket instead of installing
        // it.
        const claim = socket.claim();
        if (claim === null) return;

        const sid = sessionIdRef.current;
        // No conversation yet — the bootstrap effect below creates or restores
        // one and calls connect() again.
        if (!sid) { socket.abandon(claim); return; }

        // Exchange access token for a one-time 60-second WS ticket.
        // Never put the JWT itself in the URL — it ends up in server logs.
        // getWsTicket goes through apiFetch, so an expired access token is
        // refreshed and retried instead of silently failing the connect.
        let ticket;
        try {
            ticket = await getWsTicket();
        } catch {
            ticket = null;
        }
        if (!ticket) { socket.abandon(claim); return; }

        const url = `${websocketUrl(`/ws/chat/${encodeURIComponent(sid)}`)}?ticket=${encodeURIComponent(ticket)}`;

        setWsStatus("connecting");
        const ws = new WebSocket(url);
        // Stale claim: something newer took over while we fetched the ticket.
        // adopt() closes this socket for us; wiring handlers to it would be
        // wiring them to a socket nobody owns.
        if (!socket.adopt(claim, ws)) return;

        ws.onopen = () => {
            setWsStatus("connected");
            // A turn we never heard the end of.
            //
            // The worker that was running it filed its answer against a socket
            // that no longer exists. Asking about the id is the ONLY safe way
            // to recover it: the server reads its ledger and replays, and can
            // never start a second run from this. Resending the question could.
            const waiting = attemptRef.current;
            if (waiting) {
                try {
                    ws.send(JSON.stringify({
                        action: "resume", client_message_id: waiting.id,
                    }));
                } catch { /* the socket died between open and here */ }
            }
            // Reset retry count only after the connection has been stable for 10 s
            // (not immediately on open — that caused an infinite retry loop)
            clearTimeout(stableRef.current);
            stableRef.current = setTimeout(() => { retryCount.current = 0; }, 10000);
        };
        ws.onclose = () => {
            // A socket we have already replaced must not speak for the UI, and
            // above all must not schedule a reconnect — that is how one dropped
            // connection used to become a growing pile of them.
            if (!socket.isCurrent(ws)) return;
            clearTimeout(stableRef.current);
            setWsStatus("disconnected");
            // Don't retry while mic is active — Chrome drops WS when SpeechRecognition
            // grabs the audio device; reconnect happens in rec.onend instead
            if (listeningRef.current) return;
            if (retryCount.current < 5) {
                const delay = Math.min(1000 * 2 ** retryCount.current, 30000);
                retryCount.current += 1;
                retryRef.current = setTimeout(connect, delay);
            }
        };
        ws.onerror = () => { ws.close(); };

        ws.onmessage = (event) => {
            let msg;
            try { msg = JSON.parse(event.data); } catch { return; }

            const now = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

            if (msg.type === "thinking") {
                setTyping(true);
                setStage(null);

            } else if (msg.type === "stage") {
                // Progress, not an answer. Never appended to the transcript.
                setStage(msg.label || null);

            } else if (msg.type === "pending") {
                // The turn we asked about is still running. Keep waiting; do
                // NOT re-send the question, or the wait becomes a second one.
                // Ask about the SAME id again shortly: `resume` only reads the
                // ledger, so it can never start a second run, and it is the
                // only way the finished answer reaches this socket.
                setTyping(true);
                const pendingId = msg.client_message_id;
                clearTimeout(resumePollRef.current);
                resumePollRef.current = setTimeout(() => {
                    if (!pendingId || attemptRef.current?.id !== pendingId) return;   // it landed or was abandoned
                    if (!socket.isCurrent(ws) || ws.readyState !== WebSocket.OPEN) return;   // a reconnect will ask again
                    try {
                        ws.send(JSON.stringify({ action: "resume", client_message_id: pendingId }));
                    } catch { /* socket died; onopen of the next one resumes */ }
                }, 4000);

            } else if (msg.type === "resume_unknown"
                       || msg.type === "resume_dead") {
                // No answer is coming for the turn we were waiting on. Say so
                // rather than spinning forever on a turn that already ended.
                clearTimeout(deadlineRef.current);
                attemptRef.current = null;
                setTyping(false);
                setStage(null);
                setMsgs(m => [...m, {
                    role: "ai", time: now, refs: [], isError: true,
                    text: "That question didn't finish. Please ask it again.",
                }]);

            } else if (msg.type === "cancelled") {
                clearTimeout(deadlineRef.current);
                attemptRef.current = null;
                setTyping(false);
                setStage(null);
                // The server says what actually happened — stopped, already
                // answered, already ended. Reporting "Stopped." for a turn that
                // had finished a moment earlier is a claim the next reload
                // contradicts.
                setMsgs(m => [...m, {
                    role: "ai", time: now, refs: [], isNotice: true,
                    text: msg.content || "Stopped.",
                }]);

            } else if (msg.type === "control_rejected") {
                // A malformed control frame. Nothing was stopped or recovered,
                // so the wait must not be left running as though it had been.
                clearTimeout(deadlineRef.current);
                attemptRef.current = null;
                setTyping(false);
                setStage(null);
                toast.show(msg.content || "That request could not be processed.",
                           "error", 3000);

            } else if (msg.type === "final") {
                clearTimeout(deadlineRef.current);
                clearTimeout(resumePollRef.current);
                attemptRef.current = null;
                setTyping(false);
                setStage(null);
                // A resume asked while the turn was finishing replays the SAME
                // stored answer the live socket just delivered. Same audit id
                // means same answer: show it once.

                // Keep the objects: `status` says whether the answer actually
                // cited a source or whether it was merely consulted, and the two
                // must not be presented as the same thing.
                const citations = normaliseCitations(msg.citations);
                // Checked INSIDE the update, against the latest list: two frames
                // landing in one tick both saw a stale ref when this was a
                // separate read.
                setMsgs(m => (msg.request_id && m.some(x => x.role === "ai" && x.requestId === msg.request_id)) ? m : [...m, {
                    role: "ai",
                    text: msg.content || "",
                    // Typed out on screen (RevealText). Only a LIVE answer: one
                    // restored from history is shown at once. The text is the
                    // final, already-checked answer; nothing unchecked is shown.
                    fresh: true,
                    time: now,
                    refs: citations,
                    claims: msg.claims || [],
                    confidence: msg.confidence,
                    confidenceBand: msg.confidence_band,
                    status: msg.convergence_status,
                    jurisdiction: msg.jurisdiction,
                    jurisdictionBasis: msg.jurisdiction_basis,
                    // The turn ran and this answer is real, but it was not
                    // filed. Shown, because a refresh will lose it and the
                    // user is entitled to know that before they rely on it.
                    historySaved: msg.history_saved !== false,
                    // Whether this turn reached the audit trail. Identical
                    // wording to the restored path, so a live answer and the
                    // same answer after a reload cannot report different
                    // things about their own auditability.
                    auditSaved: msg.audit_saved !== false,
                    auditPending: msg.audit_pending === true,
                    // Names this turn's audit record. A client cannot open the
                    // audit trail — that view is the machinery behind the
                    // findings and is lawyer-only — but they can quote the id
                    // when reporting an answer that looked wrong, which is
                    // otherwise impossible on this surface.
                    requestId: msg.request_id || "",
                    matchedLawyers: msg.suggest_lawyer ? (msg.matched_lawyers || []) : [],
                    // The service's verdict travels with the list: ranked
                    // candidates and a browsing listing look identical once the
                    // kind is dropped, and the UI then has to guess.
                    matchResultKind: msg.match_result_kind || "",
                    matchNotice: msg.match_notice || "",
                    suggestLawyer: !!msg.suggest_lawyer,
                }]);

            } else if (msg.type === "clarification") {
                clearTimeout(deadlineRef.current);
                attemptRef.current = null;
                setTyping(false);
                setStage(null);
                setMsgs(m => [...m, {
                    role: "ai",
                    text: msg.question || "",
                    time: now,
                    refs: [],
                    isClarification: true,
                    // No matching status under a clarifying question: the
                    // conversation is still working out what the matter is.
                    // (The server no longer sends any; an older one did, and
                    // its "unavailable" line sat under every question.)
                    matchedLawyers: [],
                    matchResultKind: "",
                    matchNotice: "",
                }]);

            } else if (msg.type === "error") {
                clearTimeout(deadlineRef.current);
                attemptRef.current = null;
                setTyping(false);
                setStage(null);
                toast.show("AI pipeline error — please try again.", "error", 3000);
                setMsgs(m => [...m, {
                    role: "ai",
                    text: msg.content || "AI assistant temporarily unavailable.",
                    time: now,
                    refs: [],
                    isError: true,
                }]);
            }
        };

    }, [socket]);   // sessionIdRef is a ref — no dep needed


    /* Auto-scroll to latest message */
    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [msgs, typing]);

    /* How long the browser waits before admitting nothing is coming.
       Deliberately longer than the server's own turn timeout, so that when the
       server can explain the failure its message wins and this never fires. */
    const CLIENT_TURN_TIMEOUT_MS = 150000;

    /* Start waiting for an answer to `attempt`, with a deadline on the wait.

       Every path that begins a wait goes through here — a fresh send AND a turn
       recovered after a refresh. Recovery used to set the attempt and the
       typing indicator without arming a deadline, so a turn whose worker had
       died left the dots spinning and the composer locked with nothing to end
       it: the one failure a user cannot get out of, reachable only by the
       recovery path that exists to rescue them. */
    const awaitTurn = useCallback((attempt) => {
        attemptRef.current = attempt;
        setTyping(true);
        clearTimeout(deadlineRef.current);
        deadlineRef.current = setTimeout(() => {
            if (attemptRef.current?.id !== attempt.id) return;   // it landed
            attemptRef.current = null;
            setTyping(false);
            setStage(null);
            setMsgs(m => [...m, {
                role: "ai", refs: [], isError: true,
                time: new Date().toLocaleTimeString(
                    [], { hour: "2-digit", minute: "2-digit" }),
                text: "This is taking longer than expected and I've stopped "
                    + "waiting. Please try again.",
            }]);
        }, CLIENT_TURN_TIMEOUT_MS);
    }, []);

    /* How many messages one page holds, in both directions. */
    const PAGE_SIZE = 50;

    /* Older messages, on demand.

       Guarded by the SAME generation ticket the open uses, and the check is not
       decoration: this is an await, and a user who switches conversation while
       it is in flight would otherwise have another thread's history prepended
       to the one they are now looking at. The ticket is taken at call time and
       compared after the await, so a stale response is dropped rather than
       raced onto the screen.

       Prepended, and the merge de-duplicates: a message can legitimately arrive
       twice — once in a live frame, once in an older page — and rendering it
       twice looks like data corruption. */
    const loadOlder = useCallback(async () => {
        const sessionId = sessionIdRef.current;
        if (!sessionId || !olderCursor || loadingOlder) return;
        // `current()`, NOT `next()`. Claiming a new generation here would
        // invalidate the open this fetch belongs to — the guard is meant to
        // notice the user switching away, not to cause it.
        const ticket = openGeneration.current();
        setLoadingOlder(true);
        const { data, error } = await getConversation(
            sessionId, { beforeSeq: olderCursor, pageSize: PAGE_SIZE });
        if (!openGeneration.isCurrent(ticket)) return;   // the user moved on
        setLoadingOlder(false);
        if (error || !data) {
            toast.show(error?.message || "Could not load earlier messages. Please try again.",
                       "error", 3500);
            return;
        }

        // `mergeMessages` sorts by the server-allocated `seq`, so which side
        // the older page is passed on does not decide the order — the sequence
        // does. De-duplicated because a message can legitimately arrive twice,
        // once live and once in a page.
        setMsgs(current => mergeMessages(current, toClientMessages(data.messages)));
        setOlderCursor(data.older_cursor ?? null);
        setHasOlder(!!data.has_older);
    }, [olderCursor, loadingOlder, openGeneration, toast]);

    /* ── Opening a conversation ───────────────────────────────────────── */
    const openConversation = useCallback(async (sessionId) => {
        if (!sessionId) return;
        const ticket = openGeneration.next();
        clearTimeout(retryRef.current);
        clearTimeout(deadlineRef.current);
        retryCount.current = 0;
        socket.close();
        // The turn we were waiting on belongs to the conversation we are
        // leaving, not to the one we are opening.
        attemptRef.current = null;
        setStage(null);

        sessionIdRef.current = sessionId;
        writeActiveSession("client", user?._id, sessionId);
        setTyping(false);
        setLoadingHistory(true);

        // ONE page, the newest.
        //
        // This used to walk forward from the very first message until
        // `has_more` went false — every page of a two-year conversation, before
        // anything appeared. The reader opens at the bottom, so that is where
        // the fetch starts; older pages arrive when they are asked for.
        setOlderCursor(null);
        setHasOlder(false);
        const { data, error } = await getConversation(
            sessionId, { pageSize: PAGE_SIZE });
        if (!openGeneration.isCurrent(ticket)) return;   // the user moved on
        if (error || !data) {
            setLoadingHistory(false);
            // Gone, or never ours. Say so and start clean rather than leaving
            // the UI pointed at nothing.
            writeActiveSession("client", user?._id, null);
            setMsgs([]);
            toast.show(error?.message || "That conversation is no longer available",
                       "warn", 3000);
            return;
        }

        const header = data;
        setLoadingHistory(false);
        setMsgs(toClientMessages(data.messages));
        setOlderCursor(data.older_cursor ?? null);
        setHasOlder(!!data.has_older);
        setSessionReady(true);
        // An answer this conversation is still waiting for.
        //
        // A refresh mid-turn loses the socket, not the turn: the worker files
        // the answer regardless. Remembering the id here is what lets the
        // reconnect ASK for it, instead of the user re-asking and paying twice.
        const pending = header?.pending_turn;
        if (pending?.client_message_id) {
            // Through `awaitTurn`, so the recovered wait is bounded exactly
            // like a fresh one. Setting the attempt directly here is what left
            // a dead turn spinning forever.
            awaitTurn(newAttempt(pending.client_message_id));
        }
        connect();
        // Reads and writes the remembered-session key, which is scoped by user
        // id — so it has to depend on the user. With `[connect, toast]` it
        // captured the first render's null user and remembered nothing.
    }, [awaitTurn, connect, toast, user?._id]);

    /* ── New chat ─────────────────────────────────────────────────────────
       A real, persisted conversation from the moment it is asked for. It used
       to be a client-side array reset with a browser-minted id, so a chat
       abandoned before its first reply left no trace at all. */
    const newChat = useCallback(async () => {
        // Already on an empty chat: use it. Each click used to make another
        // empty conversation, and the history filled with "New conversation"
        // copies (2026-11-23).
        if (sessionReady && sessionIdRef.current && msgs.length === 0 && !typing) {
            inpRef.current?.focus();
            return;
        }
        clearTimeout(retryRef.current);
        clearTimeout(deadlineRef.current);
        retryCount.current = 0;
        socket.close();
        attemptRef.current = null;
        setStage(null);

        const { data, error } = await createConversation();
        if (error || !data?.session_id) {
            toast.show(error?.message || "Could not start a new chat", "error", 3000);
            return;
        }
        sessionIdRef.current = data.session_id;
        writeActiveSession("client", user?._id, data.session_id);
        setMsgs([]);
        setTyping(false);
        setSessionReady(true);
        connect();
        refreshHistory();
    }, [connect, refreshHistory, toast, user?._id, sessionReady, msgs.length, typing]);

    /* Rename / delete, on the user's own conversations only — the server scopes
       every one of these to the caller. */
    const renameActive = useCallback(async (sessionId, title) => {
        const { error } = await renameConversation(sessionId, title);
        if (error) toast.show(error.message || "Could not rename", "error", 3000);
        else refreshHistory();
    }, [refreshHistory, toast]);

    const removeConversation = useCallback(async (sessionId) => {
        const { error } = await deleteConversation(sessionId);
        if (error) { toast.show(error.message || "Could not delete", "error", 3000); return; }
        if (sessionIdRef.current === sessionId) {
            writeActiveSession("client", user?._id, null);
            setMsgs([]);
            setSessionReady(false);
            await newChat();
        }
        refreshHistory();
    }, [newChat, refreshHistory, toast, user?._id]);

    /* Restore the conversation, then connect.
       The socket is NOT opened until a session exists, because the id is the
       WebSocket path segment and the server keys the stored conversation and
       the LangGraph thread on it. Opening first would have meant connecting to
       an id nothing had agreed to yet. */
    useEffect(() => {
        let live = true;
        (async () => {
            // No user yet: the bootstrap re-runs when the account resolves.
            if (!user?._id) return;
            refreshHistory();
            // Scoped to the signed-in user, so a different account cannot
            // land on the previous one's conversation.
            const remembered = readActiveSession("client", user._id);
            if (remembered) {
                // A refresh: reopen exactly the conversation this tab was in.
                await openConversation(remembered);
                return;
            }
            const { data } = await createConversation();
            if (!live) return;
            if (data?.session_id) {
                sessionIdRef.current = data.session_id;
                writeActiveSession("client", user?._id, data.session_id);
                setSessionReady(true);
                connect();
                refreshHistory();
            }
        })();
        return () => {
            live = false;
            clearTimeout(retryRef.current);
            clearTimeout(stableRef.current);
            clearTimeout(deadlineRef.current);
            clearTimeout(resumePollRef.current);
            retryCount.current = 99;
            listeningRef.current = false;
            socket.close();
        };
        // Re-runs on an ACCOUNT CHANGE, not on every render: a new user must
        // not inherit the previous one's open conversation.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [user?._id]);



    /* ── Stop ──────────────────────────────────────────────────────────────
       Cancelling does not stop the provider call — that is in flight and cannot
       be recalled. It discards the ANSWER: the server clears the turn's lease,
       so the running worker's fenced completion matches nothing and stores no
       message. The user is not handed an answer they said they no longer
       wanted, and the conversation is usable again immediately. */
    const stop = async () => {
        const waiting = attemptRef.current;
        const sid = sessionIdRef.current;
        if (!waiting) return;

        // ALWAYS over HTTP, never over the socket — even when the socket is
        // open and healthy.
        //
        // The server reads one frame at a time from this connection and is
        // parked inside `chat_graph.ainvoke` for the whole turn. A cancel frame
        // sent down the same socket sits in the transport buffer and is not
        // read until generation FINISHES, at which point the turn has already
        // completed and there is nothing left to cancel. So Stop appeared to
        // work, reported "Stopped", and stopped nothing — the answer was
        // produced, paid for and filed exactly as if the button did not exist.
        //
        // An HTTP request arrives on a different connection and a different
        // task. It clears the turn's lease immediately, so the worker still
        // running inside the graph loses its fenced completion and files
        // nothing. That is the only route that can reach a turn in flight.
        if (!sid) return;
        const { data, error } = await cancelClientTurn(sid, waiting.id);
        clearTimeout(deadlineRef.current);
        attemptRef.current = null;
        setTyping(false);
        setStage(null);
        setMsgs(m => [...m, {
            role: "ai", refs: [], isNotice: true,
            time: new Date().toLocaleTimeString(
                [], { hour: "2-digit", minute: "2-digit" }),
            text: error ? "Could not stop that question."
                        : (data?.message || "Stopped."),
        }]);
    };

    /* ── Send message ─────────────────────────────────────────────────── */
    // `override`: the text to send instead of the box's (Regenerate). A click
    // hands an event, which is not text, so the box is used then.
    const send = (override, regenerate = false) => {
        const fromBox = typeof override !== "string";
        const txt = (fromBox ? inp : override).trim();
        if (!txt) return;
        // One question at a time. The server refuses a second concurrent turn
        // anyway; refusing it here means the user sees why instead of watching
        // their message vanish into a refusal frame.
        if (attemptRef.current) {
            toast.show("Still answering your last question.", "info", 2000);
            return;
        }

        /* Reconnect if socket dropped */
        if (!socket.isOpen()) {
            toast.show("Reconnecting...", "info", 1500);
            connect();
            return;
        }

        const now = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

        setMsgs(m => [...m, { role: "user", text: txt, time: now }]);
        if (fromBox) setInp("");

        // The sidebar reflects the server's list, so it is refreshed rather
        // than guessed at locally. The first question becomes the conversation's
        // title, which is why a send changes what the list shows.
        setTimeout(refreshHistory, 400);

        // One id per ATTEMPT, not per transmission. The server deduplicates on
        // it, so resending the same attempt replays the first answer instead of
        // running the graph and paying a provider again. Minting a fresh id per
        // send made the whole idempotency mechanism unreachable from here.
        const attempt = newAttempt();
        awaitTurn(attempt);
        socket.current().send(JSON.stringify({
            content: txt,
            client_message_id: attempt.id,
            // `case_id` is deliberately not sent. It used to be read off this
            // frame and written to the session with no check at all, so the
            // browser could bind a conversation to any case id it could name.
            // The client chat surface has no case binding.
            case_type: caseType || null,
            // "" (not null) when unset: the backend treats unknown as "search
            // every jurisdiction and say so", never as federal.
            province: province || null,
            language: "en",
            web_search: webSearch,
            ...(regenerate && { regenerate: true }),
        }));
    };

    /* Regenerate (2026-10-19): offered on the LAST answer only, and asks the
     * question that led to it again as a new turn -- the server keeps both. */
    const lastAiIndex = msgs.map(x => x.role).lastIndexOf("ai");
    const questionFor = i => {
        for (let j = i - 1; j >= 0; j--) if (msgs[j].role === "user") return msgs[j].text;
        return null;
    };

    /* ── Voice input (2026-10-20): the shared VoiceButton. While it listens
     * the socket is left alone (Chrome can drop it); when it stops, a dropped
     * socket is reconnected. ── */
    const wasListening = useRef(false);
    const onListening = (v) => {
        setListening(v);
        listeningRef.current = v;
        if (wasListening.current && !v && !socket.isOpen()) {
            retryCount.current = 0;
            connect();
        }
        wasListening.current = v;
    };

    const hasMessages = msgs.length > 0;

    /* ── Shared icon-button style ─────────────────────────────────────── */
    const iconBtn = (extra = {}) => ({
        background: "none", border: "none", cursor: "pointer", padding: 6,
        borderRadius: 8, color: t.textMuted, display: "flex",
        alignItems: "center", justifyContent: "center",
        transition: "background 0.15s, color 0.15s", ...extra,
    });

    /* ── Greeting (Version C, approved 2026-11-23) ────────────────────────
       Plain words in the app's own font. The old emoji and the "Dark mode is
       on" joke read wrong in light mode and looked template-made. */
    const h = new Date().getHours();
    const greetingText = h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
    const firstName = user?.full_name?.split(" ")[0];

    /* Starter questions: real, specific uses. A click only FILLS the box —
       the client still reads it, can change it, and presses send. */
    const fillQuestion = q => { setInp(q); setTimeout(() => inpRef.current?.focus(), 0); };

    /* The input box, built once: under the greeting on an empty chat, at the
       bottom once the chat has messages (2026-11-23). */
    const composer = (
        <>
            <style>{CHAT_BOX_CSS}</style>
                    <div data-chat-box>
                        {/* Grows with the question, like ChatGPT (2026-11-23): Enter
                            sends, Shift+Enter makes a new line; past MAX_INPUT_HEIGHT
                            it scrolls inside, so earlier lines move up out of view.
                            Enter during an Urdu IME composition does not send. */}
                        <textarea
                            ref={inpRef}
                            value={inp}
                            dir="auto"
                            rows={1}
                            aria-label="Ask Attorney AI"
                            onChange={e => setInp(e.target.value)}
                            onKeyDown={e => {
                                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                                    e.preventDefault();
                                    send();
                                }
                            }}
                            placeholder={wsStatus === "connected" ? "Ask Attorney AI..." : wsStatus === "connecting" ? "Connecting..." : "Offline — reconnecting..."}
                            className="thin-scrollbar"
                            style={{
                                display: "block", width: "100%", boxSizing: "border-box", resize: "none",
                                background: "transparent", border: "none", outline: "none",
                                color: t.text, fontSize: 15, padding: "2px 2px 8px", lineHeight: 1.5,
                                fontFamily: "inherit", overflowY: "hidden", maxHeight: MAX_INPUT_HEIGHT,
                            }}
                        />

                        {/* Toolbar: the options on the left, voice and send on the right. */}
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap", minWidth: 0 }}>
                                {/* History and Web chips removed (2026-10-19): the
                                    sidebar has its own collapse / open control. */}
                                {/* Jurisdiction selector.
                                    Province materially changes the governing
                                    law — a shop-eviction question is answered
                                    by the Punjab Rented Premises Act 2009 in
                                    Punjab and by nothing equivalent federally.
                                    "All Pakistan" is honest about searching
                                    every jurisdiction; it is NOT "federal". */}
                                <select
                                    className={`cb-chip${province ? " on" : ""}`}
                                    value={province}
                                    onChange={e => setProvince(e.target.value)}
                                    title="Jurisdiction — which province's law applies to your question"
                                    aria-label="Jurisdiction">
                                    <option value="">No jurisdiction filter</option>
                                    <option value="punjab">Punjab</option>
                                    <option value="sindh">Sindh</option>
                                    <option value="kpk">KPK</option>
                                    <option value="balochistan">Balochistan</option>
                                    <option value="federal">Federal only</option>
                                </select>

                            </div>

                            <div style={{ display: "flex", alignItems: "center", gap: 8, flex: "none" }}>
                                {/* Speak Urdu or English (2026-10-20): our server tells them
                                    apart and writes Urdu in Urdu script; the answer follows the
                                    language of the question. Click to start, click to finish. */}
                                <VoiceButton value={inp} onText={setInp} className="cb-mic" onListening={onListening}
                                    mode="server" serverLanguage="auto"
                                    onError={msg => toast.show(msg, "warn", 4000)}
                                    onNotice={msg => toast.show(msg, "info", 6000)} />

                                <button type="button" onClick={send} aria-label="Send"
                                    disabled={!(inp.trim() && wsStatus === "connected")}
                                    className={`cb-send${inp.trim() ? " typed" : ""}${inp.trim() && wsStatus === "connected" ? " on" : ""}`}>
                                    {/* An upward arrow (2026-10-20), in place of the turned logo mark. */}
                                    <SendArrow />
                                </button>
                            </div>
                        </div>
                    </div>
        </>
    );
    const disclaimer = (
        <div style={{ marginTop: 8, fontSize: 11, color: t.textFaint, textAlign: "center" }}>
            Informational only — not legal advice. Verify with a qualified Pakistani lawyer.
        </div>
    );


    return (
        <div style={{
            position: "relative", inset: 0, width: "100%", height: "100%",
            display: "flex", overflow: "hidden",
            background: t.bg, fontFamily: "'Inter',sans-serif",
        }}>

            {/* ══ SIDEBAR ══ */}
            <div style={{
                width: sideOpen ? 200 : 0, minWidth: sideOpen ? 200 : 0,
                flexShrink: 0, overflow: "hidden",
                transition: "width 0.3s cubic-bezier(0.4,0,0.2,1), min-width 0.3s cubic-bezier(0.4,0,0.2,1)",
                background: t.surface, borderRight: `1px solid ${t.border}`,
                display: "flex", flexDirection: "column", position: "relative",
            }} data-chat-hist>
                <style>{CHAT_HIST_CSS}</style>
                {/* New Chat */}
                <div style={{ padding: "14px 14px 10px" }}>
                    <button onClick={newChat} style={{
                        width: "100%", padding: "10px 18px", borderRadius: 50,
                        // The client theme's brand gradient (2026-10-19), as on the
                        // lawyer AI Assistant; light mode gets its own from the theme.
                        background: "var(--brand-solid)", color: "var(--on-brand)",
                        border: "none", fontSize: 13, fontWeight: 700, cursor: "pointer",
                        display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                        fontFamily: "'Inter',sans-serif", transition: "opacity 0.2s",
                        boxShadow: `0 4px 16px ${t.primaryGlow}`, whiteSpace: "nowrap",
                    }}
                        onMouseEnter={e => e.currentTarget.style.opacity = "0.88"}
                        onMouseLeave={e => e.currentTarget.style.opacity = "1"}
                    >
                        <svg width={15} height={15} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                            <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="16" /><line x1="8" y1="12" x2="16" y2="12" />
                        </svg>
                        New Chat
                    </button>
                </div>

                {/* History header */}
                <div style={{
                    display: "flex", alignItems: "center", justifyContent: "space-between",
                    padding: "6px 16px 4px",
                }}>
                    <span style={{ fontSize: 13, fontWeight: 700, color: t.text }}>History</span>
                </div>

                {/* Search. Matches the conversation title and the question
                    that named it — not message bodies, which live in another
                    collection. A search covering some of a conversation's text
                    but not the rest would be worse than one whose scope is
                    obvious. */}
                <div style={{ padding: "0 16px 6px" }}>
                    <input
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                        placeholder="Search conversations"
                        aria-label="Search conversations"
                        style={{
                            width: "100%", padding: "6px 10px", fontSize: 12,
                            borderRadius: 8, background: t.surface,
                            border: `1px solid ${t.border}`, color: t.text,
                            outline: "none",
                        }} />
                </div>

                {/* Found in what was SAID.
                    A separate section from the list above, not merged into it,
                    because it answers a different question and carries a
                    different thing: the sentence that matched. Merging would
                    drop the snippet, which is the only part that tells the user
                    WHY this conversation came back. */}
                {messageHits.length > 0 && (
                    <div style={{ padding: "0 10px 8px" }}>
                        <div style={{
                            fontSize: 11, fontWeight: 600, color: t.textMuted,
                            padding: "6px 6px 4px", textTransform: "uppercase",
                            letterSpacing: "0.6px",
                        }}>
                            Found in messages
                        </div>
                        {messageHits.map(hit => (
                            <div key={`hit-${hit.session_id}`}
                                 onClick={() => openConversation(hit.session_id)}
                                 style={{
                                     padding: "7px 8px", borderRadius: 8,
                                     cursor: "pointer", marginBottom: 2,
                                 }}>
                                <div style={{
                                    fontSize: 12.5, color: t.text,
                                    whiteSpace: "nowrap", overflow: "hidden",
                                    textOverflow: "ellipsis",
                                }}>
                                    {hit.title}
                                </div>
                                <div style={{
                                    fontSize: 11, color: t.textMuted,
                                    marginTop: 2, lineHeight: 1.45,
                                }}>
                                    {hit.snippet}
                                </div>
                            </div>
                        ))}
                    </div>
                )}

                {/* Older conversations that cannot be searched by content.
                    Said out loud rather than left to be discovered by not
                    finding something you remember saying — the thread is still
                    there and still findable by name. */}
                {unsearchable && (
                    <div style={{
                        margin: "0 16px 8px", padding: "6px 9px",
                        borderRadius: 8, fontSize: 11,
                        color: t.textMuted, background: t.surface,
                        border: `1px solid ${t.border}`,
                    }}>
                        Some older conversations can only be found by their
                        title, not by what was said in them.
                    </div>
                )}

                {/* History list. Scrolls without a visible bar, as on the lawyer page. */}
                <div className="hide-scrollbar" style={{ flex: 1, overflowY: "auto", padding: "4px 10px 8px" }}>
                    {history.map((g, gi) => (
                        <div key={gi} style={{ marginBottom: 14 }}>
                            <div className="ch-g">{g.group}</div>
                            {/* Real conversations. Clicking one reopens it with its
                                full history; the previous list put the raw text of
                                a past question into the input box, which was the
                                only thing it could do because nothing was stored. */}
                            {g.items.map((item) => {
                                const active = item.session_id === sessionIdRef.current;
                                return (
                                    <div key={item.session_id}
                                        onClick={() => openConversation(item.session_id)}
                                        title={item.title}
                                        className={`ch-cv${active ? " on" : ""}`}>
                                        <span style={{ flex: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{item.title}</span>
                                        <button type="button" className="ch-more" title="More actions"
                                            aria-label={`Actions for ${item.title}`} aria-haspopup="menu"
                                            aria-expanded={rowMenu?.item.session_id === item.session_id}
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                // Inside the sidebar, under the button (above it near the bottom).
                                                const r = e.currentTarget.getBoundingClientRect();
                                                const box = e.currentTarget.closest("[data-chat-hist]").getBoundingClientRect();
                                                const below = r.bottom - box.top + 4;
                                                const y = below + 70 > box.height ? r.top - box.top - 70 : below;
                                                setRowMenu(m => m?.item.session_id === item.session_id ? null
                                                    : { item, x: Math.min(r.left - box.left, box.width - 130), y });
                                            }}>
                                            <svg width={15} height={15} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="5" cy="12" r="1.8" /><circle cx="12" cy="12" r="1.8" /><circle cx="19" cy="12" r="1.8" /></svg>
                                        </button>
                                    </div>
                                );
                            })}
                        </div>
                    ))}
                    {/* Follows `has_more`, NOT "did this page return rows".
                        The research list filters out threads on revoked cases
                        after reading them, so a page can legitimately come back
                        empty while more accessible threads wait behind it. */}
                    {listMore && (
                        <button
                            onClick={loadMoreHistory}
                            disabled={listLoading}
                            style={{
                                width: "100%", marginTop: 4, padding: "7px 10px",
                                fontSize: 12, borderRadius: 8, cursor: "pointer",
                                background: "none", color: t.textMuted,
                                border: `1px dashed ${t.border}`,
                            }}>
                            {listLoading ? "Loading…" : "Load older conversations"}
                        </button>
                    )}
                    {!listMore && !listLoading && history.every(g => g.items.length === 0) && (
                        <div style={{
                            padding: "10px 6px", fontSize: 12, color: t.textFaint,
                        }}>
                            {search ? "No conversations match that search."
                                    : "No conversations yet."}
                        </div>
                    )}
                </div>

                {rowMenu && (
                    <div role="menu" data-row-menu className="ch-menu" style={{ left: Math.max(8, rowMenu.x), top: Math.max(8, rowMenu.y) }}>
                        <button type="button" role="menuitem" onClick={() => {
                            const item = rowMenu.item; setRowMenu(null);
                            const next = window.prompt("Rename this conversation", item.title);
                            if (next && next.trim()) renameActive(item.session_id, next.trim());
                        }}>
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" /></svg>
                            Rename
                        </button>
                        <button type="button" role="menuitem" className="danger" onClick={() => {
                            const item = rowMenu.item; setRowMenu(null);
                            if (window.confirm("Delete this conversation and its messages?")) removeConversation(item.session_id);
                        }}>
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6" /></svg>
                            Delete
                        </button>
                    </div>
                )}
                {(() => {
                    const shown = history.reduce((n, g) => n + g.items.length, 0);
                    return <div className="ch-foot"><span>Private to you</span><span>{shown}{listMore ? "+" : ""} chat{shown === 1 ? "" : "s"}</span></div>;
                })()}

                {/* Sidebar footer */}
                <div style={{ padding: "10px 14px 14px", borderTop: `1px solid ${t.border}` }}>
                    <button onClick={() => setSideOpen(false)} style={{
                        width: "100%", padding: "9px", borderRadius: 10, fontSize: 12,
                        background: "transparent", border: `1px solid ${t.border}`,
                        color: t.textMuted, cursor: "pointer", fontFamily: "'Inter',sans-serif",
                        display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
                        transition: "all 0.2s",
                    }}
                        onMouseEnter={e => { e.currentTarget.style.borderColor = t.primary; e.currentTarget.style.color = t.primary; }}
                        onMouseLeave={e => { e.currentTarget.style.borderColor = t.border; e.currentTarget.style.color = t.textMuted; }}
                    >
                        <svg width={13} height={13} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M15 18l-6-6 6-6" />
                        </svg>
                        Collapse
                    </button>
                </div>
            </div>

            {/* ══ MAIN AREA ══ */}
            <div style={{
                flex: 1, display: "flex", flexDirection: "column",
                overflow: "hidden", position: "relative",
            }}>

                {/* Top-left label + expand button */}
                <div style={{
                    position: "absolute", top: 18, left: 22, zIndex: 10,
                    display: "flex", alignItems: "center", gap: 10, pointerEvents: "none",
                }}>
                    {!sideOpen && (
                        // Theme colours, not a fixed mint disc (2026-10-19).
                        <button onClick={() => setSideOpen(true)} aria-label="Show history" title="Show history" style={{
                            width: 34, height: 34, borderRadius: "50%",
                            background: "var(--surface)", border: "1px solid var(--line-strong)",
                            color: "var(--teal)",
                            display: "flex", alignItems: "center", justifyContent: "center",
                            cursor: "pointer", pointerEvents: "auto",
                            transition: "border-color 0.15s, background 0.15s",
                        }}
                            onMouseEnter={e => { e.currentTarget.style.borderColor = "var(--teal)"; }}
                            onMouseLeave={e => { e.currentTarget.style.borderColor = "var(--line-strong)"; }}
                        >
                            <svg width={15} height={15} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                <path d="M9 18l6-6-6-6" />
                            </svg>
                        </button>
                    )}
                    {/* Plain title in the app's font (2026-11-23). The status dot and
                        the upgrade button (which had no action) are gone; the
                        connection state still shows in the input's placeholder. */}
                    <span style={{ fontSize: 16, fontWeight: 600, color: t.text }}>Chat</span>
                </div>

                {/* ── Messages / Welcome ── */}
                <div style={{
                    flex: 1, overflowY: "auto",
                    display: "flex", flexDirection: "column",
                    alignItems: "center",
                    // Empty chat: centred with auto margins on the welcome block,
                    // not justify-content, so on a short or zoomed screen it
                    // scrolls from the top instead of cutting the logo off; the
                    // top padding clears the "Chat" title (2026-11-23).
                    justifyContent: "flex-start",
                    padding: hasMessages ? "68px 28px 16px" : "64px 28px 24px",
                }}>
                    {!hasMessages ? (
                        <div data-chat-welcome style={{ margin: "auto 0", padding: "0 0 40px" }}>
                            <style>{CHAT_WELCOME_CSS}</style>
                            {/* Logo mark, greeting, then the input right under it. No
                                mascot, glow or emoji (Version C, 2026-11-23). */}
                            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6, textAlign: "center" }}>
                                <img src="/logo-mark.png" alt="" aria-hidden="true" width={52} height={52}
                                    style={{ objectFit: "contain", display: "block", marginBottom: 10 }} />
                                <h2 style={{ margin: 0, fontSize: 28, fontWeight: 600, color: t.text, letterSpacing: "-0.01em" }}>
                                    {greetingText}{firstName ? `, ${firstName}` : ""}
                                </h2>
                                <p style={{ margin: 0, fontSize: 15, color: t.textMuted }}>What legal question can I help with?</p>
                                {wsStatus === "disconnected" && (
                                    <p style={{ margin: "4px 0 0", fontSize: 13, color: t.textMuted }}>
                                        AI chat unavailable — please sign in again.
                                    </p>
                                )}
                            </div>
                            <div>
                                {composer}
                                {disclaimer}
                            </div>
                            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                                <div style={{ fontSize: 12, fontWeight: 600, color: t.textFaint }}>
                                    Try one of these, or type your own — English, Urdu or Roman Urdu
                                </div>
                                <div className="cw-q" role="group" aria-label="Example questions">
                                    {STARTER_QUESTIONS.map(q => (
                                        <button key={q.text} type="button" onClick={() => fillQuestion(q.text)}>
                                            <b>{q.area}</b>{q.text}
                                        </button>
                                    ))}
                                </div>
                                <div className="cw-links" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "center", gap: "6px 14px", marginTop: 6, fontSize: 12.5, color: t.textMuted }}>
                                    <span>I explain Pakistani law and show the sources. I can't act for you in court.</span>
                                    <a href="/lawyers" onClick={e => { e.preventDefault(); router.push("/lawyers"); }}>Find a lawyer</a>
                                    <a href="/intake" onClick={e => { e.preventDefault(); router.push("/intake"); }}>Describe your case</a>
                                </div>
                            </div>
                        </div>
                    ) : (
                        <div style={{ width: "100%", maxWidth: 980, display: "flex", flexDirection: "column", gap: 18 }}>
                            <style>{BUBBLE_CSS}</style>
                            {/* Older messages, on demand.
                                A conversation opens at its END, so this is the
                                only way back — and it is at the TOP of the
                                transcript because that is where the history it
                                loads belongs. */}
                            {hasOlder && (
                                <div style={{ display: "flex", justifyContent: "center",
                                              padding: "2px 0 10px" }}>
                                    <button
                                        onClick={loadOlder}
                                        disabled={loadingOlder}
                                        style={{
                                            padding: "5px 14px", fontSize: 11.5,
                                            borderRadius: 999, cursor: "pointer",
                                            background: "none", color: t.textMuted,
                                            border: `1px solid ${t.border}`,
                                        }}>
                                        {loadingOlder ? "Loading\u2026" : "Load earlier messages"}
                                    </button>
                                </div>
                            )}
                            {msgs.map((m, i) => (
                                <div key={i} data-msg-role={m.role} style={{
                                    display: "flex",
                                    flexDirection: m.role === "user" ? "row-reverse" : "row",
                                    gap: 10, alignItems: "flex-start",
                                }}>
                                    {m.role === "ai" && (
                                        // The icon alone, no box round it (2026-10-19).
                                        <div style={{
                                            width: 36, height: 36,
                                            flexShrink: 0,
                                            display: "flex", alignItems: "center", justifyContent: "center",
                                            overflow: "hidden",
                                        }}>
                                            {m.isError
                                                ? <Ic n="scale" s={16} c="#ef4444" />
                                                : <span data-ai-avatar role="img" aria-label="Attorney.AI"><span /></span>
                                            }
                                        </div>
                                    )}
                                    <div data-revealing={m.fresh ? "" : undefined} style={{ maxWidth: m.role === "user" ? "75%" : "calc(100% - 44px)", minWidth: 0 }}>
                                        <div data-bubble={m.role === "user" ? "user" : "ai"} dir="auto" style={{
                                            // Solid, so the tail is the same colour as the bubble (2026-10-19;
                                            // a gradient left a seam where they meet). The theme is set later.
                                            "--bub": m.role === "user" ? (t.mode === "light" ? "#0B7A8C" : "#2EC4D6") : t.surface,
                                            padding: m.role === "user" ? "8px 16px" : "12px 20px", fontSize: 15, lineHeight: 1.7,
                                            color: m.role === "user" ? (t.mode === "dark" ? "#1A2E35" : "#fff") : t.text,
                                            // An answer is markdown (2026-10-20): bold, headings, lists.
                                            whiteSpace: m.role === "user" ? "pre-wrap" : "normal",
                                        }}>
                                            {m.isClarification && (
                                                <div style={{ fontSize: 11, color: t.primary, fontWeight: 700, marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.5px" }}>
                                                    Clarification needed
                                                </div>
                                            )}
                                            {m.role === "user" ? m.text : (
                                                <RevealText text={m.text} animate={!!m.fresh}
                                                    render={txt => <RichText text={txt} />}
                                                    onProgress={() => bottomRef.current?.scrollIntoView({ block: "end" })}
                                                    onDone={() => m.fresh && setMsgs(ms => ms.map(x => (x === m ? { ...x, fresh: false } : x)))} />
                                            )}
                                        </div>
                                        {/* Statement checks. Surfaced ABOVE the sources panel and
                                            with a always-visible warning line, because the finding
                                            that matters most — "this sentence is not backed by the
                                            law it cites" — is worthless hidden behind a click. */}
                                        {m.claims?.length > 0 && (() => {
                                            const repealed = m.claims.filter(c => c.currency === REPEALED);
                                            const flagged = m.claims.filter(
                                                c => c.support === "unsupported" || c.support === "partial");
                                            const sorted = [...m.claims].sort(
                                                (a, b) => CLAIM_ORDER.indexOf(a.support) - CLAIM_ORDER.indexOf(b.support));
                                            return (
                                                <div style={{ marginTop: 8 }}>
                                                    {repealed.length > 0 && (
                                                        <div style={{
                                                            fontSize: 12, color: "#ef4444", fontWeight: 700,
                                                            marginBottom: 6, padding: "7px 10px", borderRadius: 8,
                                                            background: "#ef444414", border: "1px solid #ef444455",
                                                        }}>
                                                            {"\u26D4"} {CURRENCY_TEXT.repealed}
                                                            <div style={{ fontWeight: 400, fontSize: 11, marginTop: 3 }}>
                                                                {repealed.length === 1 ? "1 statement relies" : `${repealed.length} statements rely`}
                                                                {" "}on law that has been repealed. Speak to a lawyer before acting on this answer.
                                                            </div>
                                                        </div>
                                                    )}
                                                    {flagged.length > 0 && (
                                                        <div style={{
                                                            fontSize: 11.5, color: "#f59e0b", fontWeight: 600,
                                                            marginBottom: 6, display: "flex", gap: 6, alignItems: "center",
                                                        }}>
                                                            ⚠ {flagged.length === 1
                                                                ? "1 statement isn't fully backed by the law it cites"
                                                                : `${flagged.length} statements aren't fully backed by the law they cite`}
                                                        </div>
                                                    )}
                                                    <button
                                                        onClick={() => setMsgs(prev => prev.map((x, xi) => xi === i ? { ...x, claimsOpen: !x.claimsOpen } : x))}
                                                        style={{
                                                            display: "inline-flex", alignItems: "center", gap: 6,
                                                            padding: "5px 12px", borderRadius: 8, fontSize: 11.5, fontWeight: 700,
                                                            border: `1px solid ${t.border}`, background: m.claimsOpen ? t.primaryGlow : "transparent",
                                                            color: t.primary, cursor: "pointer", fontFamily: "inherit",
                                                        }}>
                                                        🔍 Statement checks ({m.claims.length}) {m.claimsOpen ? "▴" : "▾"}
                                                    </button>
                                                    {m.claimsOpen && (
                                                        <div style={{
                                                            marginTop: 6, padding: "10px 12px", borderRadius: 10,
                                                            background: t.surface, border: `1px solid ${t.border}`,
                                                            display: "flex", flexDirection: "column", gap: 9,
                                                        }}>
                                                            {sorted.map((c, ci) => {
                                                                // A repealed source OVERRIDES the support verdict. The source
                                                                // may genuinely say what the claim says and still be law that
                                                                // no longer exists — the more important fact, and the one a
                                                                // reader cannot spot unaided.
                                                                const dead = c.currency === REPEALED;
                                                                const ui = dead
                                                                    ? { icon: "\u26D4", color: "#ef4444", text: CURRENCY_TEXT.repealed }
                                                                    : (CLAIM_UI[c.support] || CLAIM_UI.unassessed);
                                                                return (
                                                                    <div key={ci} style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                                                                        <span style={{
                                                                            color: ui.color, fontWeight: 700, fontSize: 12,
                                                                            lineHeight: "1.5", flexShrink: 0, width: 12, textAlign: "center",
                                                                        }}>{ui.icon}</span>
                                                                        <div style={{ minWidth: 0 }}>
                                                                            <div style={{ fontSize: 12, color: t.textDim, lineHeight: 1.5 }}>
                                                                                “{c.text}”
                                                                            </div>
                                                                            <div style={{ fontSize: 10.5, color: ui.color, marginTop: 2 }}>
                                                                                {ui.text}
                                                                                {dead && (c.sources || []).map(repealNote).filter(Boolean).length > 0 && (
                                                                                    <span style={{ color: t.textFaint }}>
                                                                                        {" \u2014 "}{(c.sources || []).map(repealNote).filter(Boolean).join("; ")}
                                                                                    </span>
                                                                                )}
                                                                                {c.sources?.length > 0 && (
                                                                                    <span style={{ color: t.textFaint }}>
                                                                                        {" — "}{c.sources.map(sc => [sc.statute, sc.section ? `§${sc.section}` : ""].filter(Boolean).join(" ")).join("; ")}
                                                                                    </span>
                                                                                )}
                                                                            </div>
                                                                        </div>
                                                                    </div>
                                                                );
                                                            })}
                                                            <div style={{ fontSize: 10, color: t.textFaint, borderTop: `1px solid ${t.border}`, paddingTop: 7 }}>
                                                                These checks compare each statement against the law sections we
                                                                retrieved. Where a provision is not marked repealed its current
                                                                status is simply not verified — that is not a confirmation it is
                                                                still in force. Not a substitute for a lawyer.
                                                            </div>
                                                        </div>
                                                    )}
                                                </div>
                                            );
                                        })()}
                                        {/* Which jurisdiction this answer assumed.
                                            Shown for every answer, because an
                                            assumption the user cannot see is an
                                            assumption they cannot correct — and
                                            province decides which statute even
                                            applies. "All Pakistan" is stated
                                            plainly rather than quietly meaning
                                            federal. */}
                                        {m.role === "ai" && !m.isError && m.jurisdictionBasis
                                            && m.jurisdictionBasis !== "not_applicable"
                                            // "No jurisdiction filter …" was noise under every answer (2026-10-19).
                                            && m.jurisdictionBasis !== "unspecified" && (
                                            <div style={{
                                                marginTop: 8, fontSize: 11, color: t.textMuted,
                                                display: "flex", alignItems: "center", gap: 6,
                                            }}>
                                                {m.jurisdictionBasis === "unspecified" ? (
                                                    <span>
                                                        No jurisdiction filter — all jurisdictions in the
                                                        corpus were searched. Provincial coverage is
                                                        currently <strong>Punjab only</strong>; other provinces
                                                        return federal law. Set a jurisdiction above for
                                                        province-specific law.
                                                    </span>
                                                ) : (
                                                    <span>
                                                        Jurisdiction: <strong style={{ color: t.text, textTransform: "capitalize" }}>
                                                            {m.jurisdiction}
                                                        </strong>
                                                        {m.jurisdictionBasis === "inferred_from_query"
                                                            ? " (inferred from your question)"
                                                            : " (your selection)"}
                                                    </span>
                                                )}
                                            </div>
                                        )}
                                        {m.refs?.length > 0 && (
                                            <div style={{ marginTop: 8 }}>
                                                <button
                                                    onClick={() => setMsgs(prev => prev.map((x, xi) => xi === i ? { ...x, refsOpen: !x.refsOpen } : x))}
                                                    style={{
                                                        display: "inline-flex", alignItems: "center", gap: 6,
                                                        padding: "5px 12px", borderRadius: 8, fontSize: 11.5, fontWeight: 700,
                                                        border: `1px solid ${t.border}`, background: m.refsOpen ? t.primaryGlow : "transparent",
                                                        color: t.primary, cursor: "pointer", fontFamily: "inherit",
                                                    }}>
                                                    {/* "Cited in this answer (n)" counts only what
                                                        the answer actually cited. Counting
                                                        everything retrieved under that label is
                                                        the original bug this area exists to fix. */}
                                                    📖 {citationSummary(m.refs).label} {m.refsOpen ? "▴" : "▾"}
                                                </button>
                                                {m.refsOpen && (
                                                    <div style={{
                                                        marginTop: 6, padding: "10px 12px", borderRadius: 10,
                                                        background: t.surface, border: `1px solid ${t.border}`,
                                                    }}>
                                                        <div style={{ fontSize: 10, fontWeight: 700, color: t.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>
                                                            Verify before relying on them
                                                        </div>
                                                        {CITATION_GROUPS.map(({ key, client: caption }) => {
                                                            const group = citationsInGroup(m.refs, key);
                                                            if (!group.length) return null;
                                                            return (
                                                                <div key={key} style={{ marginBottom: 8 }}>
                                                                    <div style={{ fontSize: 10, color: key === "unresolved" ? "#f59e0b" : t.textFaint, marginBottom: 4 }}>
                                                                        {caption}
                                                                    </div>
                                                                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                                                                        {group.map((r, ri) => {
                                                                            // A repealed chip is red whatever its match status:
                                                                            // being cited AND retrieved says nothing about
                                                                            // whether the provision still exists.
                                                                            const badge = (
                                                                                <Badge type={r.currency === REPEALED ? "danger" : key === "unresolved" ? "warn" : "info"}>
                                                                                    {r.currency === REPEALED ? "⛔ " : key === "matched" ? "✓ " : key === "unresolved" ? "? " : ""}{r.label}
                                                                                    {r.currency === REPEALED ? " — repealed" : ""}
                                                                                    {(r.href || r.sourceUrl) ? " ↗" : ""}
                                                                                </Badge>
                                                                            );
                                                                            // Openable only where the source document is
                                                                            // actually held, so a chip opens something exactly
                                                                            // when there is something to open. "Verify before
                                                                            // relying on them" was an instruction with no way
                                                                            // to follow it; this is the way. A judgment is an
                                                                            // external anchor; a corpus document needs the
                                                                            // authenticated fetch, because our API route wants
                                                                            // a header a new tab cannot send.
                                                                            if (r.href) {
                                                                                return (
                                                                                    <a key={ri} href={r.href} target="_blank" rel="noopener noreferrer"
                                                                                       title="Open the judgment" style={{ textDecoration: "none" }}>
                                                                                        {badge}
                                                                                    </a>
                                                                                );
                                                                            }
                                                                            if (r.sourceUrl) {
                                                                                return (
                                                                                    <button key={ri} title="Open the source document"
                                                                                        onClick={async () => {
                                                                                            const res = await openSourceDocument(r.sourceUrl, r.label);
                                                                                            // useToast returns { show }, not a callable.
                                                                                            if (res.error) toast.show(res.error, "error");
                                                                                        }}
                                                                                        style={{ border: "none", background: "transparent", padding: 0, cursor: "pointer" }}>
                                                                                        {badge}
                                                                                    </button>
                                                                                );
                                                                            }
                                                                            return <span key={ri}>{badge}</span>;
                                                                        })}
                                                                    </div>
                                                                </div>
                                                            );
                                                        })}
                                                    </div>
                                                )}
                                            </div>
                                        )}
                                        {/* The answer was produced but not saved.
                                            Silence here meant a user read an
                                            answer, refreshed, and found it gone
                                            with no explanation. */}
                                        {m.role === "ai" && m.historySaved === false && (
                                            <div style={{
                                                marginTop: 6, padding: "6px 10px",
                                                borderRadius: 8, fontSize: 11.5,
                                                background: "#f59e0b14",
                                                border: "1px solid #f59e0b55",
                                                color: t.text,
                                            }}>
                                                ⚠ This answer could not be saved to your
                                                history. Copy anything you need — it will
                                                not be here after a refresh.
                                            </div>
                                        )}
                                        {(() => {
                                            if (m.role !== "ai") return null;
                                            // Nothing at all when the record is
                                            // safely written — which is almost
                                            // always. A badge on every answer
                                            // confirming the system worked is
                                            // noise, and noise is what stops
                                            // people reading the one that
                                            // matters.
                                            const notice = auditNotice(m);
                                            if (!notice) return null;
                                            const warn = notice.tone === "warn";
                                            return (
                                                <div title={notice.detail} style={{
                                                    marginTop: 6, padding: "6px 10px",
                                                    borderRadius: 8, fontSize: 11.5,
                                                    background: warn ? "#f59e0b14" : "#64748b14",
                                                    border: `1px solid ${warn ? "#f59e0b55" : "#64748b44"}`,
                                                    color: warn ? t.text : t.textMuted,
                                                }}>
                                                    {warn ? "\u26a0 " : ""}{notice.label}
                                                </div>
                                            );
                                        })()}
                                        {/* Copy, and the rating on every substantive answer. The
                                            rating carries the answer's request id, so a reported
                                            answer can still be found (the visible id was removed). */}
                                        {m.role === "ai" && !m.isError && !m.isNotice && m.text && (
                                            <MessageActions t={t} text={m.text} rated={m.rated}
                                                onRegenerate={i === lastAiIndex && questionFor(i) ? () => send(questionFor(i), true) : null}
                                                canRate={!m.isClarification && Boolean(m.requestId) && m.auditSaved !== false && !m.auditPending}
                                                onRate={r => {
                                                    rateAnswer({
                                                        request_id: m.requestId,
                                                        session_id: sessionIdRef.current || "unknown",
                                                        rating: r,
                                                        source: "chat",
                                                    }).then(({ error }) => {
                                                        if (!error) setMsgs(prev => prev.map((x, xi) => xi === i ? { ...x, rated: r } : x));
                                                        else toast.show("Feedback could not be saved.", "error", 2500);
                                                    });
                                                }} />
                                        )}
                                        {/* Lawyer connect card — shown on HITL or max_attempts.
                                            Extracted so it can be mounted and asserted on without a
                                            WebSocket harness; see LawyerMatchPanel.jsx. */}
                                        <LawyerMatchPanel
                                            message={m}
                                            theme={t}
                                            onBook={() => router.push("/lawyers")}
                                        />
                                        <div style={{ fontSize: 10, color: t.textFaint, marginTop: 5, textAlign: m.role === "user" ? "right" : "left" }}>
                                            {m.time}
                                            {/* A confidence band only when there is one; no
                                                "not calibrated" jargon for clients (2026-10-19). */}
                                            {m.role === "ai" && !m.isError && !m.isClarification && m.text && m.confidenceBand && (
                                                <span style={{ marginLeft: 8, color: CONF_COLOR[m.confidenceBand] || t.textMuted }}>
                                                    ⬤ {CONF_LABEL[m.confidenceBand]} confidence
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            ))}

                            {/* Typing indicator */}
                            {typing && (
                                // Same avatar and bubble as an answer (2026-10-19).
                                <div data-typing style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                                    <div style={{ width: 36, height: 36, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
                                        <span data-ai-avatar role="img" aria-label="Attorney.AI"><span /></span>
                                    </div>
                                    <div data-bubble="ai" style={{
                                        "--bub": t.surface,
                                        padding: "13px 18px", display: "flex", gap: 5, alignItems: "center",
                                    }}>
                                        {[0, 1, 2].map(d => (
                                            <div key={d} style={{
                                                width: 7, height: 7, borderRadius: "50%", background: "var(--teal)",
                                                animation: `pulse 1.2s ease ${d * 0.2}s infinite`,
                                            }} />
                                        ))}
                                    </div>
                                    {/* What it is actually doing, and a way out.
                                        Three dots for two minutes is
                                        indistinguishable from broken, and a
                                        user who has changed their mind had no
                                        way to say so. */}
                                    <div style={{
                                        display: "flex", alignItems: "center", gap: 10,
                                        alignSelf: "center",
                                    }}>
                                        {stage && (
                                            <span style={{ fontSize: 12, color: t.textMuted }}>
                                                {stage}
                                            </span>
                                        )}
                                        <button
                                            onClick={stop}
                                            title="Stop generating" className="stop-gen">
                                            <span aria-hidden="true" style={{ width: 8, height: 8, borderRadius: 2, background: "currentColor" }} />
                                            Stop
                                        </button>
                                    </div>
                                </div>
                            )}
                            <div ref={bottomRef} />
                        </div>
                    )}
                </div>

                {/* ── Input box: at the bottom once a chat has messages; on an
                    empty chat it sits under the greeting instead. ── */}
                {hasMessages && (
                <div style={{
                    padding: "0 28px 20px",
                    display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0,
                }}>
                    {composer}
                    {disclaimer}
                </div>
                )}

            </div>
        </div>
    );
};

export default ModChatbot;
