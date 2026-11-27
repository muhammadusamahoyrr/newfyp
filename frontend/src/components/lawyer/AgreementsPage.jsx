'use client';
// Lawyer Agreements — contracts awaiting signature, and legacy engagement letters.
// Counterpart of the client's AgreementHub; same backend, lawyer perspective.
import { useState, useEffect, useCallback, useRef } from "react";
import { useTheme } from "./theme.js";
import { Card, Btn, Badge } from "./components.jsx";
import { Icon, I } from "./icons.jsx";
import { DRAFTING_TOKENS_CSS, draftingMode } from "./draftingTheme.js";
import { useAuth } from "@/context/AuthContext.jsx";
import { listAgreements, getAgreement, signAgreement, declineAgreement, downloadExecutedAgreement } from "@/lib/api.js";
import SignaturePad from "./SignaturePad.jsx";
import { DraftComposer } from "./DraftComposer.jsx";
import AgreementBody from "@/components/shared/AgreementBody.jsx";

const PAGE_SIZE = 25;
// For the folder counts: one unfiltered read of this many rows.
const SUMMARY_SIZE = 50;   // the server caps page_size at 50 (agreement_service.MAX_PAGE_SIZE)

/* FOLDERS (2026-11-26, canvas board V5 "Folders like DocuSign"): the lawyer
 * picks what to look at -- what needs their signature first. Two folders share
 * the server's "pending" status and are split here by whose signature is
 * missing; the others map one-to-one to a server status. */
const FOLDERS = [
    { key: "action", label: "Action required", status: "pending", icon: "edit", tone: "gold",
      note: "Agreements waiting for your signature", empty: "Nothing is waiting for your signature." },
    { key: "waiting", label: "Waiting for client", status: "pending", icon: "clock", tone: "teal",
      note: "You signed; the other side has not yet", empty: "Nothing is waiting on a client." },
    { key: "completed", label: "Completed", status: "executed", icon: "checkCircle", tone: "mint",
      note: "Signed by everyone — final, PDF ready", empty: "No agreement is fully signed yet." },
    { key: "declined", label: "Declined & cancelled", status: "cancelled", icon: "x", tone: "red",
      note: "Declined by someone, or withdrawn", empty: "Nothing was declined or cancelled." },
    { key: "drafts", label: "Drafts", status: "draft", icon: "fileText", tone: "grey",
      note: "Your own unsent drafts", empty: "No drafts." },
];
// The tabs over the table (2026-11-27, same as the client's All agreements):
// short labels, the same keys as the folders they replace.
const TAB_LABEL = { all: "All", action: "Needs my signature", waiting: "Pending", completed: "Signed", declined: "Declined", drafts: "Drafts" };
const ALL_FOLDER = { key: "all", label: "All agreements", status: null, icon: "list", tone: "grey",
    note: "Everything you are a party to", empty: "No agreements yet. When a client sends you an agreement to sign, it appears here." };
const inFolder = (a, key) => key === "action" ? a.needsMySig
    : key === "waiting" ? a.status === "Pending" && !a.needsMySig
    : key === "completed" ? a.status === "Executed"
    : key === "declined" ? a.status === "Cancelled"
    : key === "drafts" ? a.isDraft : true;
/** One line on where an agreement stands, from the lawyer's side. */
export function agreementStatusLine(a, myId) {
    if (!a) return "";
    const others = (a.parties || []).filter(p => p.user_id !== myId);
    const names = list => list.map(p => p.full_name || p.email || "Invited signer").join(", ");
    if (a.isDraft) return "Draft — not sent yet";
    if (a.status === "Executed") return "Signed by everyone";
    if (a.status === "Cancelled") return "Declined or cancelled";
    if (a.needsMySig) return `From ${names(others) || "the other party"} — waiting for your signature`;
    const waiting = others.filter(p => !p.signed);
    return waiting.length ? `You signed — waiting for ${names(waiting)}` : "Waiting for the other signatures";
}
const rowTone = a => a.needsMySig ? "gold" : a.status === "Pending" ? "teal" : a.status === "Executed" ? "mint" : a.status === "Cancelled" ? "red" : "grey";
const rowLabel = a => a.needsMySig ? "Your signature needed" : a.status === "Pending" ? "Waiting for client" : a.status;

export const LAWYER_AGREEMENTS_CSS = `[data-lawyer-agreements].la-page{flex:1;min-height:0;overflow-y:auto;background:radial-gradient(900px 360px at 25% -80px,var(--glow),transparent 70%) no-repeat,var(--bg);padding:26px clamp(16px,3.2vw,40px) 64px;box-sizing:border-box}
[data-lawyer-agreements].la-page>*{flex-shrink:0}
[data-lawyer-agreements] .al-head{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;flex-wrap:wrap}
[data-lawyer-agreements] .al-head h1{margin:0;font-size:28px;font-weight:800;color:var(--ink)}
[data-lawyer-agreements] .al-head p{margin:5px 0 0;font-size:14px;color:var(--muted)}
[data-lawyer-agreements] .al-search{display:flex;align-items:center;gap:8px;width:300px;height:42px;padding:0 16px;box-sizing:border-box;border-radius:999px;background:var(--surface);border:1px solid var(--line);color:var(--faint)}
[data-lawyer-agreements] .al-search:focus-within{border-color:var(--focus);box-shadow:0 0 0 3px var(--brand-soft)}
[data-lawyer-agreements] .al-search input{flex:1;min-width:0;border:0;outline:none;background:transparent;color:var(--ink);font:inherit;font-size:13.5px}
[data-lawyer-agreements] .al-search input::placeholder{color:var(--faint)}
[data-lawyer-agreements] .al-seg{display:flex;gap:4px;padding:4px;border-radius:999px;background:var(--surface);border:1px solid var(--line);width:max-content}
[data-lawyer-agreements] .al-seg button{height:34px;padding:0 16px;border:0;border-radius:999px;background:transparent;color:var(--muted);font:inherit;font-size:13.5px;font-weight:600;cursor:pointer;transition:background .15s,color .15s;display:inline-flex;align-items:center;gap:7px}
[data-lawyer-agreements] .al-seg button:hover{color:var(--ink);background:var(--hover)}
[data-lawyer-agreements] .al-seg button[aria-pressed="true"]{background:var(--ink);color:var(--bg)}
[data-lawyer-agreements] .al-seg .n{min-width:20px;height:20px;padding:0 6px;border-radius:999px;display:inline-grid;place-items:center;font-size:11px;font-weight:800;background:color-mix(in srgb,var(--gold) 22%,transparent);color:var(--gold)}
[data-lawyer-agreements] .al-table{border-radius:18px;border:1px solid color-mix(in srgb,var(--brand-text) 14%,var(--line));background:linear-gradient(180deg,color-mix(in srgb,var(--surface) 88%,#fff 12%),var(--surface));box-shadow:inset 0 1px 0 rgba(255,255,255,.1),0 14px 28px -16px rgba(0,0,0,.7);overflow:hidden}
[data-lawyer-agreements] .al-grid{display:grid;grid-template-columns:minmax(0,2.3fr) minmax(0,1.5fr) 170px 150px 170px;gap:16px;align-items:center}
[data-lawyer-agreements] .al-th{padding:11px 22px;font-size:11px;font-weight:700;letter-spacing:.1em;color:var(--faint);background:color-mix(in srgb,var(--surface-2) 70%,transparent);border-bottom:1px solid var(--line)}
[data-lawyer-agreements] .al-tr{padding:14px 22px;border-bottom:1px solid var(--line);cursor:pointer;transition:background .15s}
[data-lawyer-agreements] .al-tr:hover{background:color-mix(in srgb,var(--c) 7%,transparent)}
[data-lawyer-agreements] .al-ic{width:40px;height:40px;flex:none;border-radius:11px;display:grid;place-items:center;color:var(--c);background:color-mix(in srgb,var(--c) 17%,transparent)}
[data-lawyer-agreements] .al-title{font-size:14.5px;font-weight:600;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
[data-lawyer-agreements] .al-sub{margin-top:2px;font-size:12.5px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
[data-lawyer-agreements] .al-avs{display:flex;align-items:center}
[data-lawyer-agreements] .al-av{width:30px;height:30px;flex:none;border-radius:50%;display:grid;place-items:center;font-size:10.5px;font-weight:800;color:var(--c);background:color-mix(in srgb,var(--c) 20%,var(--surface));border:2px solid var(--surface);box-sizing:border-box}
[data-lawyer-agreements] .al-av+.al-av{margin-left:-8px}
[data-lawyer-agreements] .al-chip{display:inline-flex;align-items:center;gap:6px;height:26px;padding:0 11px;border-radius:999px;font-size:12px;font-weight:700;color:var(--c);background:color-mix(in srgb,var(--c) 15%,transparent);white-space:nowrap;width:max-content}
[data-lawyer-agreements] .al-chip i{width:6px;height:6px;border-radius:50%;background:currentColor}
[data-lawyer-agreements] .al-pbar{height:6px;border-radius:6px;background:var(--line);overflow:hidden}
[data-lawyer-agreements] .al-pbar i{display:block;height:100%;border-radius:6px;background:var(--c)}
[data-lawyer-agreements] .al-acts{display:flex;align-items:center;justify-content:flex-end;gap:4px}
[data-lawyer-agreements] .al-btn{--a:var(--brand-text);display:inline-flex;align-items:center;justify-content:center;gap:6px;height:34px;padding:0 14px;border-radius:999px;border:1px solid color-mix(in srgb,var(--a) 38%,transparent);background:color-mix(in srgb,var(--a) 13%,var(--surface));color:var(--a);font:inherit;font-size:12.5px;font-weight:700;cursor:pointer;white-space:nowrap;transition:background .2s,color .2s,border-color .2s,transform .12s}
[data-lawyer-agreements] .al-btn:hover{background:var(--a);border-color:transparent;color:#04262c}
[data-lawyer-agreements] .al-btn.solid{background:linear-gradient(135deg,#3EE0A1,#2EC4D6);border-color:transparent;color:#04212A}
[data-lawyer-agreements] .al-foot{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 22px;flex-wrap:wrap;font-size:12.5px;color:var(--muted)}
[data-lawyer-agreements] .al-empty{padding:44px 20px;text-align:center;color:var(--muted);font-size:13.5px;line-height:1.6}
[data-lawyer-agreements]{--tone-gold:var(--gold);--tone-teal:var(--teal-ink);--tone-mint:var(--brand-text);--tone-red:var(--danger);--tone-grey:var(--muted);display:flex;flex-direction:column;gap:18px;color:var(--ink);font:15px/1.5 "Hanken Grotesk",system-ui,sans-serif}
[data-lawyer-agreements] .la-crumbs{font-size:14px;color:var(--muted)}
[data-lawyer-agreements] .la-crumbs b{color:var(--ink)}
[data-lawyer-agreements] .la-head{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;column-gap:20px}
[data-lawyer-agreements] .la-head h1{margin:0;font:600 clamp(28px,3.4vw,38px)/1.1 "Literata",Georgia,serif;letter-spacing:-.01em}
[data-lawyer-agreements] .la-accent{background:linear-gradient(90deg,var(--brand-text),var(--teal-ink));-webkit-background-clip:text;background-clip:text;color:transparent}
[data-lawyer-agreements] .la-head p{grid-column:1/-1;margin:8px 0 0;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
[data-lawyer-agreements] .la-search{display:flex;align-items:center;gap:10px;height:42px;width:320px;padding:0 14px;border-radius:12px;background:var(--surface);border:1px solid var(--line-strong);color:var(--faint)}
[data-lawyer-agreements] .la-search input{flex:1;min-width:0;border:0;outline:none;background:transparent;color:var(--ink);font:inherit;font-size:14px}
[data-lawyer-agreements] .la-search:focus-within{border-color:var(--brand-text);box-shadow:0 0 0 3px color-mix(in srgb,var(--brand-text) 16%,transparent)}
[data-lawyer-agreements] .la-body{display:grid;grid-template-columns:260px minmax(0,1fr);gap:18px;align-items:start}
[data-lawyer-agreements] .la-card{border-radius:20px;background:var(--surface);border:1px solid var(--line)}
[data-lawyer-agreements] .la-folders{padding:10px;display:flex;flex-direction:column;gap:4px}
[data-lawyer-agreements] .la-folder{--c:var(--tone-grey);display:flex;align-items:center;gap:12px;width:100%;height:46px;padding:0 12px;border:0;border-radius:12px;background:transparent;color:var(--muted);font:inherit;font-size:14.5px;font-weight:700;text-align:left;cursor:pointer;transition:background .15s,color .15s}
[data-lawyer-agreements] .la-folder:hover{background:color-mix(in srgb,var(--c) 9%,transparent);color:var(--ink)}
[data-lawyer-agreements] .la-folder[aria-current="true"]{background:color-mix(in srgb,var(--c) 15%,transparent);box-shadow:inset 3px 0 0 var(--c);color:var(--ink)}
[data-lawyer-agreements] .la-folder .ic{color:var(--c);display:inline-flex}
[data-lawyer-agreements] .la-folder .t{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
[data-lawyer-agreements] .la-n{min-width:24px;height:24px;padding:0 7px;border-radius:999px;display:grid;place-items:center;font-size:12px;font-weight:800;background:color-mix(in srgb,var(--c) 18%,transparent);color:var(--c)}
[data-lawyer-agreements] .la-sep{height:1px;background:var(--line);margin:6px 4px}
[data-lawyer-agreements] .la-list{overflow:hidden}
[data-lawyer-agreements] .la-list-head{--c:var(--tone-grey);display:flex;align-items:center;gap:10px;padding:16px 20px;border-bottom:1px solid var(--line)}
[data-lawyer-agreements] .la-list-head .ic{color:var(--c);display:inline-flex}
[data-lawyer-agreements] .la-list-head b{font-size:17px}
[data-lawyer-agreements] .la-list-head span{color:var(--faint);font-size:14px}
[data-lawyer-agreements] .la-row{--c:var(--tone-grey);display:grid;grid-template-columns:42px minmax(0,1fr) 150px auto auto;gap:14px;align-items:center;padding:14px 20px;border-top:1px solid var(--line);cursor:pointer;transition:background .12s}
[data-lawyer-agreements] .la-row:first-child{border-top:0}
[data-lawyer-agreements] .la-row:hover{background:var(--hover-tint)}
[data-lawyer-agreements] .la-row[data-needs-me]{background:linear-gradient(90deg,color-mix(in srgb,var(--gold) 9%,transparent),transparent 60%);box-shadow:inset 3px 0 0 var(--gold)}
[data-lawyer-agreements] .la-ic{width:42px;height:42px;border-radius:12px;display:grid;place-items:center;background:color-mix(in srgb,var(--c) 15%,transparent);color:var(--c)}
[data-lawyer-agreements] .la-title{display:block;font-size:15px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
[data-lawyer-agreements] .la-sub{font-size:12.5px;color:var(--faint)}
[data-lawyer-agreements] .la-prog{display:flex;flex-direction:column;gap:5px;font-size:12px;color:var(--faint)}
[data-lawyer-agreements] .la-prog span{display:flex;gap:3px}
[data-lawyer-agreements] .la-prog i{display:block;flex:1;max-width:22px;height:5px;border-radius:3px;background:color-mix(in srgb,var(--ink) 14%,transparent)}
[data-lawyer-agreements] .la-prog i[data-on]{background:var(--brand-text)}
[data-lawyer-agreements] .la-chip{display:inline-flex;align-items:center;gap:6px;height:28px;padding:0 11px;border-radius:999px;font-size:12.5px;font-weight:700;white-space:nowrap;background:color-mix(in srgb,var(--c) 15%,transparent);color:var(--c)}
[data-lawyer-agreements] .la-btn{display:inline-flex;align-items:center;justify-content:center;gap:7px;height:38px;min-width:120px;padding:0 15px;border:0;border-radius:12px;font:inherit;font-size:13.5px;font-weight:700;white-space:nowrap;cursor:pointer;background:color-mix(in srgb,var(--teal-ink) 16%,transparent);color:var(--teal-ink);transition:filter .15s,transform .12s,background .15s}
[data-lawyer-agreements] .la-btn:hover{background:color-mix(in srgb,var(--teal-ink) 24%,transparent);transform:translateY(-1px)}
[data-lawyer-agreements] .la-btn.go{background:var(--brand-solid);color:var(--on-brand);box-shadow:0 8px 18px -10px rgba(46,196,214,.8)}
[data-lawyer-agreements] .la-btn.go:hover{filter:brightness(1.06);background:var(--brand-solid)}
[data-lawyer-agreements] .la-empty{padding:40px 20px;text-align:center;color:var(--faint);font-size:14px}
[data-lawyer-agreements] .la-empty .ic{width:48px;height:48px;margin:0 auto 10px;border-radius:14px;display:grid;place-items:center;background:color-mix(in srgb,var(--c,var(--muted)) 14%,transparent);color:var(--c,var(--muted))}
[data-lawyer-agreements] .la-foot{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 20px;border-top:1px solid var(--line);font-size:12.5px;color:var(--faint)}
[data-lawyer-agreements] [data-tone="gold"]{--c:var(--tone-gold)}
[data-lawyer-agreements] [data-tone="teal"]{--c:var(--tone-teal)}
[data-lawyer-agreements] [data-tone="mint"]{--c:var(--tone-mint)}
[data-lawyer-agreements] [data-tone="red"]{--c:var(--tone-red)}
[data-lawyer-agreements] [data-tone="grey"]{--c:var(--tone-grey)}
@media (max-width:1100px){[data-lawyer-agreements] .la-body{grid-template-columns:minmax(0,1fr)}[data-lawyer-agreements] .la-row{grid-template-columns:42px minmax(0,1fr) auto}[data-lawyer-agreements] .la-prog{display:none}}`;

// WRITING AGREEMENTS IS OFF (2026-11-25). The page came back so a lawyer can
// SIGN and DECLINE what a client sends them. Authoring is a separate product
// decision, so "New agreement" stays hidden until it is made. A draft the
// lawyer already has still opens in the composer.
export const LAWYER_CAN_CREATE_AGREEMENTS = false;

const OPEN_AGREEMENT_KEY = "attorney:lawyer-open-agreement";

/* THE ADDRESS IS THE SOURCE OF TRUTH (2026-11-25), as on the client's
 * Tracking page: an open agreement is /lawyer/agreements?agreement=<id>, so a
 * refresh, a copied link and Back/Forward all reopen the same one.
 * sessionStorage is only the hand-over for an in-app jump. */
export function agreementParam() {
    try { return new URLSearchParams(window.location.search).get("agreement"); } catch { return null; }
}
function writeAgreementParam(id, { replace = false } = {}) {
    if (typeof window === "undefined" || agreementParam() === (id || null)) return;
    const url = new URL(window.location.href);
    if (id) url.searchParams.set("agreement", id); else url.searchParams.delete("agreement");
    const next = url.pathname + url.search + url.hash;
    try {
        if (replace) window.history.replaceState(window.history.state, "", next);
        else window.history.pushState(window.history.state, "", next);
    } catch { /* history unavailable */ }
}

const STATUS_LABEL = { pending: "Pending", executed: "Executed", cancelled: "Cancelled", draft: "Draft" };
const STATUS_BADGE = { Pending: "warn", Executed: "success", Cancelled: "danger", Draft: "gray" };

function mapAgreement(a, myId) {
    const parties = a.parties || [];
    const me = parties.find(p => p.user_id === myId);
    return {
        id: a.id || a._id,
        title: a.title || "Agreement",
        // NO `body` HERE. Gate 3F made the list light, and deriving the
        // displayed text from a list row is what made every agreement open
        // as "No content." beside a working Sign button. The body is fetched
        // by id when the document is opened -- see `openAgreement`.
        status: STATUS_LABEL[a.status] || "Pending",
        parties,
        // THE SERVER'S COUNTS FIRST. It derives them from the parties on every
        // read, and it is the side that knows about an external signer whose
        // row carries no user_id. Counting here is only the fallback.
        signedCount: a.signed_count ?? parties.filter(p => p.signed).length,
        totalParties: a.total_parties ?? parties.length,
        needsMySig: a.status === "pending" && !!me && !me.signed,
        date: a.created_at ? new Date(a.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "",
        // An invited signer has NO user_id, so the filter keeps them -- which
        // is right -- but `full_name` may be absent, and a blank in a
        // dot-separated list reads as a missing party rather than an invited
        // one.
        counterparts: parties
            .filter(p => p.user_id !== myId)
            .map(p => p.full_name || p.email || "Invited signer")
            .join(" · "),
        // NO `eto` HERE either. Like the body, it is a property of the
        // DOCUMENT and the list does not carry it -- reading it off a row
        // yielded undefined, so the subtitle silently said "Awaiting first
        // signature" for agreements that were already executed. It now comes
        // from the fetched document.
        isEngagementLetter: !!a.engagement_id,
        // Kept for the editor: `version` drives optimistic concurrency and
        // `raw` is the untouched server copy, which is what the digest is
        // taken over at send time. The mapped view is for DISPLAY; signing
        // reads from the server's own object.
        isDraft: a.status === "draft",
        version: a.version,
        raw: a,
    };
}

export function AgreementsPage() {
    const { t: T } = useTheme();
    const { user } = useAuth();
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [active, setActive] = useState(null);
    // {method, data} from SignaturePad. A lawyer counter-signing had a
    // name box only, while the same person composing an agreement could
    // draw or upload.
    const [signSig, setSignSig] = useState({ method: "canvas", data: "" });
    const [signConsent, setSignConsent] = useState(false);
    const [busy, setBusy] = useState(false);
    // Same two-step guard as the client screen. The backend authorises decline
    // by PARTY, not by role -- a lawyer is a party and may refuse -- so the
    // destructive path needs the same protection here.
    const [declineOpen, setDeclineOpen] = useState(false);
    const [declineReason, setDeclineReason] = useState("");
    const [toast, setToast] = useState(null);
    const showToast = (msg) => { setToast(msg); setTimeout(() => setToast(null), 3200); };
    // `composing` is either "new" or the draft being edited. A draft never
    // opens the signing modal: it has nothing to sign yet, and the only way to
    // sign it is to send it.
    const [composing, setComposing] = useState(null);

    // The DOCUMENT behind the open row: { loading, body, error }. Kept apart
    // from `active` (the list row) so it is impossible to render one while
    // believing it is the other.
    const [doc, setDoc] = useState(null);
    // Step 1 of signing (S2, 2026-11-26): the end of the document was reached.
    // It guides; it does not gate -- the consent box is the legal act.
    const docPaneRef = useRef(null);
    const [readToEnd, setReadToEnd] = useState(false);
    // Signing sheet (layout A, 2026-11-26): the document takes the window; a bar
    // at the bottom opens a sheet to sign, or to decline.
    const [signOpen, setSignOpen] = useState(false);
    // The signing flow (2026-11-26, canvas "one flow in 4 steps", after Adobe /
    // Dropbox / Box): 1 start screen, 2 read with "fields left" + Next and
    // Finish on top, 3 click "Sign here" for the signature popup, 4 Finish and
    // "You're all set". The signature is ADOPTED first and only sent on Finish.
    const [gateDone, setGateDone] = useState(false);
    const [adopted, setAdopted] = useState(null);
    const [menuOpen, setMenuOpen] = useState(false);
    const [doneInfo, setDoneInfo] = useState(null);
    const checkRead = useCallback(() => {
        const el = docPaneRef.current;
        if (el && el.scrollTop + el.clientHeight >= el.scrollHeight - 24) setReadToEnd(true);
    }, []);
    // Monotonic counter identifying the most recent open. See `openAgreement`.
    const openSeq = useRef(0);

    // Paging. `total` is what stops a truncated list looking complete.
    const [total, setTotal] = useState(0);
    const [pages, setPages] = useState(1);
    const [page, setPage] = useState(1);
    const [statusFilter, setStatusFilter] = useState(null);
    const [folder, setFolder] = useState("all");
    const [query, setQuery] = useState("");
    // One unfiltered read for the folder counts. Re-read after a sign or a
    // decline, never on a folder change (the list read is the one that moves).
    const [summary, setSummary] = useState({ rows: [], total: 0, ready: false });
    const [summarySeq, setSummarySeq] = useState(0);

    const reload = useCallback(() => {
        // 3F: the response is a page, not a bare array. Reading `data.items`
        // rather than `data` -- an `Array.isArray(data)` check would now be
        // false for every successful response and the screen would render
        // "no agreements" to someone who has forty.
        listAgreements({ page, page_size: PAGE_SIZE, status: statusFilter })
            .then(({ data }) => {
                const rows = data?.items;
                if (Array.isArray(rows)) {
                    const mapped = rows.map(a => mapAgreement(a, user?._id));
                    // Page 1 REPLACES, later pages APPEND. A filter change
                    // resets to page 1, so this is also what clears the old
                    // results rather than stacking them underneath.
                    setItems(prev => (page === 1 ? mapped : [...prev, ...mapped]));
                    setTotal(data.total ?? mapped.length);
                    setPages(data.pages ?? 1);
                }
                setLoading(false);
            }).catch(() => setLoading(false));
    }, [user?._id, page, statusFilter]);
    useEffect(() => { reload(); }, [reload]);
    useEffect(() => { setReadToEnd(false); setSignOpen(false); setGateDone(false); setAdopted(null); setMenuOpen(false); setDoneInfo(null); }, [active?.id]);
    useEffect(() => { if (!doc || doc.loading) return undefined; const id = setTimeout(checkRead, 0); return () => clearTimeout(id); }, [doc, checkRead]);
    useEffect(() => {
        let live = true;
        listAgreements({ page: 1, page_size: SUMMARY_SIZE }).then(({ data }) => {
            if (!live || !Array.isArray(data?.items)) return;
            const rows = data.items.map(a => mapAgreement(a, user?._id));
            setSummary({ rows, total: data.total ?? rows.length, ready: true });
        }).catch(() => {});
        return () => { live = false; };
    }, [user?._id, summarySeq]);

    /* Open a row: fetch the DOCUMENT, never trust the row.
     *
     * The sign and decline panels are gated on `doc.body != null`, so a failed
     * fetch cannot leave somebody able to sign text they were never shown. */
    const openAgreement = useCallback(async (row) => {
        writeAgreementParam(row.id);
        setActive(row);
        setSignSig({ method: "canvas", data: "" });
        setSignConsent(false);
        setDoc({ loading: true, body: null, error: null });

        // THE LAST QUESTION ASKED IS THE ONLY ONE WHOSE ANSWER COUNTS.
        // Open A, open B before A replies, and A's late reply would land in
        // `doc` while `active` is B -- putting one agreement's wording under
        // another's heading, on a screen whose next button is Sign.
        const token = ++openSeq.current;
        const { data, error } = await getAgreement(row.id);
        if (token !== openSeq.current) return;

        if (error || !data) {
            setDoc({ loading: false, body: null,
                     error: error?.message || "This agreement could not be loaded." });
            return;
        }
        setDoc({ loading: false, body: data.body_html ?? "", format: data.body_format,
                 eto: data.eto_classification, error: null });
    }, [user?.full_name]);

    /* OPEN ONE AGREEMENT BY ID (2026-11-25): from a notification, or a link
     * with ?agreement=. The list may not hold it (another page or filter), so
     * it is fetched by id. The server decides whether this lawyer may see it;
     * a refusal is said plainly, never shown as an empty screen. */
    const [focusMissing, setFocusMissing] = useState(false);
    // THE LAST AGREEMENT ASKED FOR IS THE ONLY ONE THAT MAY OPEN. Open A, then
    // B before A answers: A's late answer must not open A under ?agreement=B,
    // and a refused B must not leave A on screen behind "couldn't open".
    const focusSeq = useRef(0);
    const openById = useCallback(async (id) => {
        if (!id) return;
        const token = ++focusSeq.current;
        setFocusMissing(false);
        // Whatever was open goes NOW, before the new answer arrives.
        openSeq.current += 1;
        setActive(null); setDoc(null); setSignConsent(false); setDeclineOpen(false); setDeclineReason("");
        // Written FIRST, so even an agreement that cannot be opened keeps its
        // address (a refresh shows the same honest "couldn't open").
        writeAgreementParam(id);
        const { data, error } = await getAgreement(id);
        if (token !== focusSeq.current) return;
        if (error || !data) { setFocusMissing(true); return; }
        const row = mapAgreement(data, user?._id);
        // A draft opens in the composer, which has no address of its own.
        if (row.isDraft) { writeAgreementParam(null, { replace: true }); setComposing(data); return; }
        openAgreement(row);
    }, [user?._id, openAgreement]);

    // Closing without touching the address (Back already changed it).
    const dropOpen = () => { focusSeq.current += 1; openSeq.current += 1; setActive(null); setDoc(null); setSignConsent(false); setDeclineOpen(false); setDeclineReason(""); setSignOpen(false); setGateDone(false); setAdopted(null); setMenuOpen(false); setDoneInfo(null); };
    const activeRef = useRef(null);
    activeRef.current = active;

    const myId = user?._id;
    useEffect(() => {
        if (!myId) return undefined;
        // The address first; the hand-over only when the address has none,
        // and then the address is written so a refresh keeps it.
        let pending = agreementParam();
        try {
            const handed = sessionStorage.getItem(OPEN_AGREEMENT_KEY);
            sessionStorage.removeItem(OPEN_AGREEMENT_KEY);
            if (!pending && handed) { pending = handed; writeAgreementParam(handed, { replace: true }); }
        } catch { /* storage off */ }
        if (pending) openById(pending);
        const onOpen = (ev) => {
            try { sessionStorage.removeItem(OPEN_AGREEMENT_KEY); } catch { /* storage off */ }
            openById(ev.detail);
        };
        // Back / Forward: open what the address names, or close.
        const onPop = () => {
            const id = agreementParam();
            if (id) { if (activeRef.current?.id !== id) openById(id); }
            else { setFocusMissing(false); if (activeRef.current) dropOpen(); }
        };
        window.addEventListener("attorney:open-agreement", onOpen);
        window.addEventListener("popstate", onPop);
        return () => {
            window.removeEventListener("attorney:open-agreement", onOpen);
            window.removeEventListener("popstate", onPop);
        };
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [myId]);

    const doSign = async () => {
        if (!signSig.data) {
            showToast("⚠️ Add your signature first — draw, type or upload");
            return;
        }
        if (!signConsent) {
            showToast("⚠️ Confirm that you intend to sign this agreement");
            return;
        }
        setBusy(true);
        const { data, error } = await signAgreement(
            active.id, signSig.method, signSig.data, true);
        setBusy(false);
        if (error) { showToast("❌ " + (error.message || "Failed to sign")); return; }
        // Step 4: the window stays open on "You're all set" (or, when someone
        // else still has to sign, on who that is). The list re-reads behind it.
        setDoneInfo({ executed: data?.status === "executed" });
        // The header behind "You're all set" must not still say Pending: take
        // the server's answer for the open agreement (2026-11-26).
        if (data && Array.isArray(data.parties)) setActive(mapAgreement(data, user?._id));
        // The signing-method line too: it was read when the window opened, before
        // this signature existed, so it kept the old method (2026-11-26).
        if (data && "eto_classification" in data) setDoc(d => (d ? { ...d, eto: data.eto_classification } : d));
        else setActive(a => (a ? { ...a, needsMySig: false, status: data?.status === "executed" ? "Executed" : a.status } : a));
        reload(); setSummarySeq(n => n + 1);
    };

    const doDecline = async () => {
        setBusy(true);
        const { error } = await declineAgreement(active.id, declineReason);
        setBusy(false);
        if (error) { showToast("❌ " + (error.message || "Failed to decline")); return; }
        showToast("Agreement declined — the other party has been notified");
        writeAgreementParam(null, { replace: true });
        setActive(null);
        setDeclineOpen(false);
        setDeclineReason("");
        reload(); setSummarySeq(n => n + 1);
    };

    const doDownload = async () => {
        setBusy(true);
        const { error } = await downloadExecutedAgreement(active.id, `${active.title || "agreement"}.pdf`);
        setBusy(false);
        if (error) { showToast("❌ " + error); return; }
        showToast("⬇ Downloaded");
    };

    const closeModal = () => { writeAgreementParam(null); focusSeq.current += 1; openSeq.current += 1; setActive(null); setDoc(null); setSignConsent(false); setDeclineOpen(false); setDeclineReason(""); setSignOpen(false); setGateDone(false); setAdopted(null); setMenuOpen(false); setDoneInfo(null); };

    const changeFilter = (next) => {
        // ONE place, because resetting the page is not optional: keeping page
        // 3 across a filter change shows the user page 3 of a list they just
        // narrowed, which usually looks empty.
        setPage(1);
        setStatusFilter(next);
    };

    // Signing is offered only once the document is on screen.
    const signing = !!(active?.needsMySig && doc && !doc.loading && !doc.error);
    const leftToSign = active ? Math.max(0, (active.totalParties || 0) - (active.signedCount || 0)) : 0;
    const signedOn = iso => iso ? new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : "";
    const stepHead = (n, title, sub, state) => (
        <div data-sign-step={n} data-step-state={state} style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
            <span aria-hidden="true" style={{ width: 28, height: 28, flexShrink: 0, borderRadius: "50%", display: "grid", placeItems: "center", fontWeight: 800, fontSize: 13,
                ...(state === "done" ? { background: T.success, color: "#04212A" } : { border: `2px solid ${state === "now" ? T.warn : T.textMuted}`, color: state === "now" ? T.warn : T.textMuted }) }}>
                {state === "done" ? <Icon d={I.check} size={14} /> : n}
            </span>
            <div>
                <div style={{ fontSize: 14.5, fontWeight: 700, color: state === "next" ? T.textMuted : T.text }}>{title}</div>
                <div style={{ fontSize: 12.5, color: T.textMuted }}>{sub}</div>
            </div>
        </div>
    );
    const folders = [...FOLDERS.filter(f => f.key !== "drafts" || LAWYER_CAN_CREATE_AGREEMENTS || summary.rows.some(a => a.isDraft)), null, ALL_FOLDER];
    const current = FOLDERS.find(f => f.key === folder) || ALL_FOLDER;
    const partial = summary.total > summary.rows.length;   // counts read from the first SUMMARY_SIZE rows
    const countOf = key => key === "all" ? summary.total : `${summary.rows.filter(a => inFolder(a, key)).length}${partial ? "+" : ""}`;
    const chooseFolder = (key) => {
        const next = FOLDERS.find(f => f.key === key) || ALL_FOLDER;
        setFolder(next.key);
        changeFilter(next.status);
    };
    const q = query.trim().toLowerCase();
    const shown = items.filter(a => inFolder(a, current.key))
        .filter(a => !q || a.title.toLowerCase().includes(q) || a.counterparts.toLowerCase().includes(q));
    const openRow = (a) => {
        focusSeq.current += 1; setFocusMissing(false);
        if (a.isDraft) { setComposing(a.raw); return; }
        openAgreement(a);
    };

    const needCount = summary.rows.filter(a => a.needsMySig).length;
    const tabs = folders.filter(Boolean).map(f => f.key).sort((x, y) => ["all", "action", "waiting", "completed", "declined", "drafts"].indexOf(x) - ["all", "action", "waiting", "completed", "declined", "drafts"].indexOf(y));
    const look = a => a.needsMySig ? { c: "var(--gold)", icon: I.edit, chip: "Needs you" }
        : a.status === "Executed" ? { c: "var(--brand-text)", icon: I.check, chip: "Signed" }
        : a.status === "Cancelled" ? { c: "var(--danger)", icon: I.x, chip: "Declined" }
        : a.isDraft ? { c: "var(--muted)", icon: I.fileText, chip: "Draft" }
        : { c: "var(--teal-ink)", icon: I.fileText, chip: "Pending" };
    const ini = n => (n || "?").trim().split(/\s+/).slice(0, 2).map(w => w[0]).join("").toUpperCase() || "?";

    return (
        <div data-lawyer-agreements data-drafting-theme data-mode={draftingMode(T)} className="la-page" data-lenis-prevent>
            <style>{`${DRAFTING_TOKENS_CSS}\n${LAWYER_AGREEMENTS_CSS}`}</style>
            {/* The client's "All agreements" layout (user, 2026-11-27): title and
                count, search on the right, status tabs, one table. */}
            <header className="al-head">
                <div>
                    <h1>All agreements</h1>
                    <p data-agreements-count>
                        {!summary.ready ? "Loading…"
                            : `${summary.total} agreement${summary.total === 1 ? "" : "s"}`
                              + (needCount ? ` · ${needCount} need${needCount === 1 ? "s" : ""} your signature` : "")}
                    </p>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    <label className="al-search">
                        <Icon d={I.search} size={16} />
                        <input data-agreement-search aria-label="Search agreements" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search by title or client" />
                    </label>
                    {LAWYER_CAN_CREATE_AGREEMENTS && (
                        <Btn variant="primary" onClick={() => setComposing("new")}>+ New agreement</Btn>
                    )}
                </div>
            </header>

            {focusMissing && (
                <div role="alert" data-agreement-missing style={{
                    display: "flex", alignItems: "center", gap: 12, padding: "12px 16px", borderRadius: 12,
                    background: `${T.warn}14`, border: `1px solid ${T.warn}55`, color: T.text, fontSize: 13,
                }}>
                    <span style={{ flex: 1 }}>
                        We couldn&rsquo;t open that agreement. It may have been removed, or you may no longer have access to it.
                    </span>
                    <Btn variant="secondary" size="sm" onClick={() => { setFocusMissing(false); writeAgreementParam(null, { replace: true }); }}>Dismiss</Btn>
                </div>
            )}

            <div className="al-seg" role="group" aria-label="Filter by status">
                {tabs.map(k => (
                    <button key={k} type="button" data-folder={k} aria-pressed={folder === k} onClick={() => chooseFolder(k)}>
                        {TAB_LABEL[k]}
                        {k === "action" && summary.ready && needCount > 0 && <span className="n" data-folder-count="action">{countOf("action")}</span>}
                    </button>
                ))}
            </div>

            <div className="al-table" aria-label={current.label}>
                <div className="al-grid al-th">
                    {["DOCUMENT", "PARTIES", "STATUS", "PROGRESS", "ACTIONS"].map(h => (
                        <div key={h} style={h === "ACTIONS" ? { textAlign: "right" } : undefined}>{h}</div>
                    ))}
                </div>
                {loading ? (
                    <div className="al-empty">Loading agreements…</div>
                ) : shown.length === 0 ? (
                    <div className="al-empty">{q ? <>Nothing matches &ldquo;{query.trim()}&rdquo; here.</> : current.empty}</div>
                ) : shown.map(a => {
                    const lk = look(a);
                    const sender = (a.parties || []).find(p => p.user_id === a.raw?.created_by) || (a.parties || []).find(p => p.user_id !== myId);
                    const senderName = sender?.full_name || sender?.email || "—";
                    const others = (a.parties || []).filter(p => p !== sender);
                    const pct = a.totalParties ? Math.round((a.signedCount / a.totalParties) * 100) : 0;
                    return (
                        <div key={a.id} className="al-grid al-tr" data-agreement-row={a.id} data-needs-me={a.needsMySig ? "" : undefined}
                            style={{ "--c": lk.c }} onClick={() => openRow(a)}>
                            <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
                                <span className="al-ic"><Icon d={lk.icon} size={18} /></span>
                                <div style={{ minWidth: 0 }}>
                                    <div className="al-title">{a.title}</div>
                                    <div className="al-sub">{a.isEngagementLetter ? "Engagement letter" : "Agreement"}{a.date ? ` · ${a.date}` : ""}</div>
                                </div>
                            </div>
                            <div style={{ minWidth: 0 }}>
                                <div className="al-avs">
                                    <span className="al-av" style={{ "--c": sender?.signed ? "var(--brand-text)" : "var(--gold)" }} title={`Sender — ${senderName}`}>{ini(senderName)}</span>
                                    {others.slice(0, 3).map((p, n) => (
                                        <span key={n} className="al-av" style={{ "--c": p.signed ? "var(--brand-text)" : "var(--gold)" }}
                                            title={`${p.full_name || p.email || "Invited signer"} — ${p.signed ? "signed" : "not signed yet"}`}>{ini(p.full_name || p.email)}</span>
                                    ))}
                                </div>
                                <div className="al-sub" style={{ marginTop: 5 }}>
                                    Sender {senderName} · {others.length > 1 ? `Recipients (${others.length})` : `Recipient ${others[0]?.full_name || others[0]?.email || "—"}`}
                                </div>
                            </div>
                            <span className="al-chip" data-status-chip><i />{lk.chip}</span>
                            <div>
                                <div className="al-pbar"><i style={{ width: `${pct}%` }} /></div>
                                <div className="al-sub" style={{ marginTop: 5 }}>{a.signedCount}/{a.totalParties} signed</div>
                            </div>
                            <div className="al-acts" onClick={e => e.stopPropagation()}>
                                {a.needsMySig ? (
                                    <button type="button" className="al-btn solid" onClick={() => openRow(a)}>Review &amp; sign</button>
                                ) : a.status === "Executed" ? (
                                    <button type="button" className="al-btn" style={{ "--a": "#b9a6f2" }} onClick={() => openRow(a)}>Open</button>
                                ) : (
                                    <button type="button" className="al-btn" style={{ "--a": "var(--teal-ink)" }} onClick={() => openRow(a)}>{a.isDraft ? "Edit draft" : "Open"}</button>
                                )}
                            </div>
                        </div>
                    );
                })}

                {/* HOW MANY THERE ARE, and a way to reach them. A truncated
                    list must never look complete. */}
                {!loading && items.length > 0 && (
                    <div className="al-foot">
                        <span>{current.key === "action" || current.key === "waiting" || q
                            ? `Showing ${shown.length}` : `Showing ${items.length} of ${total}`}</span>
                        {items.length < total && (
                            <Btn variant="secondary" size="sm" disabled={loading}
                                onClick={() => { setLoading(true); setPage(p => p + 1); }}>
                                Load more
                            </Btn>
                        )}
                    </div>
                )}
            </div>

            {/* Detail / sign modal */}
            {active && (() => {
                const sender = (active.parties || []).find(p => p.user_id !== myId);
                const senderName = sender?.full_name || sender?.email || "The other party";
                const waitingFor = (active.parties || []).filter(p => p.user_id !== myId && !p.signed).map(p => p.full_name || p.email || "Invited signer");
                const reading = signing && !doneInfo;
                const goToField = () => document.querySelector("[data-sign-here]")?.scrollIntoView?.({ behavior: "smooth", block: "center" });
                const chipBtn = { height: 40, padding: "0 16px", borderRadius: 10, border: 0, cursor: "pointer", fontFamily: "inherit", fontSize: 14, fontWeight: 700,
                    display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 7, whiteSpace: "nowrap" };
                const mint = { ...chipBtn, background: "linear-gradient(135deg,#3EE0A1,#2EC4D6)", color: "#04212A" };
                const neutral = { ...chipBtn, background: `${T.text}1A`, color: T.text, border: `1px solid ${T.text}24` };
                const overlay = { position: "fixed", inset: 0, zIndex: 10001, background: "rgba(5,15,18,.55)", display: "flex", alignItems: "flex-start", justifyContent: "center", padding: "56px 20px 20px", overflowY: "auto" };
                const dialog = { width: "min(740px, 100%)", borderRadius: 20, background: T.surface, border: `1px solid ${T.border}`, padding: "22px 24px", boxShadow: "0 30px 60px -20px rgba(0,0,0,.85)" };
                const sigMark = sig => sig?.method === "typed"
                    ? <span style={{ fontFamily: "'Brush Script MT', 'Segoe Script', cursive", fontStyle: "italic", fontSize: 30, color: "#1A3E8C" }}>{sig.data}</span>
                    : <img src={sig?.data} alt="Your signature" style={{ height: 50, maxWidth: 280, objectFit: "contain", objectPosition: "left bottom" }} />;

                const paper = (interactive) => (
                    <article data-agreement-paper data-keep-font style={{ maxWidth: 1120, margin: "0 auto", padding: "56px 72px", borderRadius: 4,
                        background: "#FBFAF6", color: "#1E1C21", fontFamily: "Literata, Georgia, serif", boxShadow: "0 1px 3px rgba(0,0,0,.4), 0 24px 50px -24px rgba(0,0,0,.7)" }}>
                        <div style={{ textAlign: "center", fontFamily: "'Hanken Grotesk', system-ui, sans-serif", fontSize: 11.5, fontWeight: 700, letterSpacing: ".18em", color: "#7F7B85" }}>AGREEMENT</div>
                        <h2 style={{ margin: "8px 0 18px", textAlign: "center", fontSize: 22, fontWeight: 600, lineHeight: 1.3 }}>{active.title}</h2>
                        {active.parties.length > 0 && (
                            <p style={{ margin: "0 0 16px", fontSize: 14.5, color: "#5A5660" }}>
                                Between {active.parties.map((p, i) => (
                                    <span key={p.user_id || p.party_id || p.email || i}>{i > 0 && (i === active.parties.length - 1 ? " and " : ", ")}<b style={{ color: "#1E1C21" }}>{p.full_name || p.email || "Invited signer"}</b></span>
                                ))}.
                            </p>
                        )}
                        <AgreementBody body={doc?.body} format={doc?.format}
                            style={{ background: "transparent", border: 0, padding: 0, fontSize: 17, lineHeight: 1.85, color: "#1E1C21", fontFamily: "Literata, Georgia, serif" }} />
                        {/* The signature lines. KEYED BY WHATEVER IDENTIFIES THE
                            PARTY: an external signer has no user_id. */}
                        <div data-signature-lines style={{ display: "grid", gridTemplateColumns: `repeat(${Math.min(3, Math.max(1, active.parties.length))}, minmax(0, 1fr))`, gap: 28, marginTop: 30 }}>
                            {active.parties.map((p, i) => {
                                const mine = !!myId && p.user_id === myId;
                                return (
                                    <div key={p.user_id || p.party_id || p.email || i} data-party-line={p.signed ? "signed" : mine ? "you" : "waiting"}
                                        style={{ display: "flex", flexDirection: "column", gap: 6, fontFamily: "'Hanken Grotesk', system-ui, sans-serif" }}>
                                        <div style={{ height: 50, display: "flex", alignItems: "flex-end" }}>
                                            {p.signed ? (
                                                <span style={{ fontFamily: "'Brush Script MT', 'Segoe Script', cursive", fontStyle: "italic", fontSize: 26, color: "#1A3E8C" }}>{p.full_name || "Signed"}</span>
                                            ) : mine && signing && adopted ? (
                                                <button type="button" data-adopted-signature onClick={() => interactive && setSignOpen(true)} title="Change your signature"
                                                    style={{ background: "none", border: 0, padding: 0, cursor: interactive ? "pointer" : "default" }}>{sigMark(adopted)}</button>
                                            ) : mine && signing ? (
                                                <button type="button" data-sign-here disabled={!interactive} onClick={() => setSignOpen(true)}
                                                    style={{ position: "relative", display: "inline-flex", alignItems: "center", gap: 8, height: 44, padding: "0 18px", borderRadius: 6,
                                                        background: "#FFF3B8", border: "2px solid #E0B400", color: "#3A2A00", fontSize: 14, fontWeight: 700, fontFamily: "inherit",
                                                        cursor: interactive ? "pointer" : "default", boxShadow: "0 6px 14px -6px rgba(180,130,0,.6)" }}>
                                                    <Icon d={I.edit} size={15} /> Sign here<span aria-hidden="true" style={{ position: "absolute", top: -10, right: -7, color: "#D92D20", fontSize: 18 }}>*</span>
                                                </button>
                                            ) : null}
                                        </div>
                                        <div style={{ borderTop: "1px solid #C9C5CE", paddingTop: 6, fontSize: 13, color: "#1E1C21" }}>
                                            <b>{p.full_name || p.email || "Invited signer"}</b>{mine ? " (you)" : ""}
                                            {p.external && (
                                                /* Said on the party itself: this is where someone
                                                   decides how much to trust the signature. */
                                                <span title="Invited by email — identity not verified by us" style={{ marginLeft: 6, fontSize: 10, fontWeight: 700, color: "#92650B", background: "#F6E7C1", borderRadius: 5, padding: "1px 5px" }}>
                                                    EMAIL{p.invitation_status === "revoked" ? " · REVOKED" : p.invitation_status === "expired" ? " · EXPIRED" : ""}</span>
                                            )}
                                        </div>
                                        <span style={{ fontSize: 12, fontWeight: 700, color: p.signed || (mine && adopted) ? "#0E7A55" : mine ? "#92650B" : "#7F7B85" }}>
                                            {p.signed ? `✓ Signed${p.signed_at ? ` ${signedOn(p.signed_at)}` : ""}`
                                                : mine && adopted ? "✓ Your signature — click Finish to complete"
                                                : mine ? "Waiting for you" : "Waiting"}
                                        </span>
                                    </div>
                                );
                            })}
                        </div>
                    </article>
                );

                return (
                <div onClick={closeModal} style={{
                    position: "fixed", inset: 0, zIndex: 9999, background: "rgba(0,0,0,0.6)",
                    display: "flex", alignItems: "stretch", justifyContent: "center", padding: 0,
                }}>
                    <div onClick={e => { e.stopPropagation(); if (menuOpen) setMenuOpen(false); }} style={{
                        background: T.card, border: 0, borderRadius: 0,
                        width: "100%", height: "100%", maxWidth: "none", maxHeight: "none",
                        display: "flex", flexDirection: "column", overflowY: "auto", position: "relative",
                        boxShadow: T.shadowCard,
                    }} ref={docPaneRef} onScroll={checkRead}>
                        {/* ONE TOP BAR holds everything (Adobe, Dropbox, Box):
                            fields left + Next on the left, Finish + ⋯ on the right. */}
                        <div data-agreement-topbar style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 18px", borderBottom: `1px solid ${T.border}`, background: T.surface }}>
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontSize: 16, fontWeight: 700, color: T.text, fontFamily: "Literata, Georgia, serif", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{active.title}</div>
                                {/* WHERE IT STANDS, in words (2026-11-26). The server's
                                    signing-method label is kept, labelled, after it. */}
                                <div data-agreement-subtitle style={{ fontSize: 12.5, color: T.textMuted }}>
                                    {[agreementStatusLine(active, myId), doc?.eto ? `Signing method: ${doc.eto}` : null].filter(Boolean).join(" · ")}
                                </div>
                            </div>
                            <div data-topbar-actions style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            {reading ? (<>
                                <button type="button" data-finish disabled={!adopted || busy} onClick={doSign}
                                    title={adopted ? "Sign the agreement" : "Add your signature on the agreement first"}
                                    style={{ ...mint, height: 32, minWidth: 84, padding: "0 16px", fontSize: 13, opacity: !adopted || busy ? 0.5 : 1, cursor: !adopted || busy ? "not-allowed" : "pointer",
                                        boxShadow: adopted ? "0 0 0 3px rgba(94,230,176,.25)" : "none" }}>{busy ? "Signing…" : "Finish"}</button>
                                <div style={{ position: "relative" }}>
                                    <button type="button" data-more-actions aria-label="More actions" aria-expanded={menuOpen}
                                        onClick={e => { e.stopPropagation(); setMenuOpen(v => !v); }} style={{ ...neutral, height: 32, width: 32, padding: 0, fontSize: 16, lineHeight: 1 }}>⋯</button>
                                    {menuOpen && (
                                        <div role="menu" onClick={e => e.stopPropagation()} style={{ position: "absolute", right: 0, top: 38, zIndex: 4, width: 230, padding: 6, borderRadius: 12,
                                            background: T.surface, border: `1px solid ${T.border}`, boxShadow: "0 20px 40px -16px rgba(0,0,0,.8)" }}>
                                            <button type="button" role="menuitem" onClick={() => { setMenuOpen(false); setDeclineOpen(true); }}
                                                style={{ width: "100%", height: 40, padding: "0 12px", borderRadius: 8, border: 0, background: "none", textAlign: "left", cursor: "pointer", fontFamily: "inherit", fontSize: 14, fontWeight: 600, color: T.danger }}>
                                                Decline to sign…
                                            </button>
                                            <button type="button" role="menuitem" onClick={closeModal}
                                                style={{ width: "100%", height: 40, padding: "0 12px", borderRadius: 8, border: 0, background: "none", textAlign: "left", cursor: "pointer", fontFamily: "inherit", fontSize: 14, fontWeight: 600, color: T.text }}>
                                                Finish later
                                            </button>
                                        </div>
                                    )}
                                </div>
                            </>) : (
                                <Badge type={STATUS_BADGE[active.status] || "gray"}>{active.status}</Badge>
                            )}
                            <span aria-hidden="true" style={{ width: 1, height: 20, background: T.border, margin: "0 2px" }} />
                            <button onClick={closeModal} aria-label="Close" style={{ background: `${T.text}12`, border: `1px solid ${T.border}`, borderRadius: 7, width: 26, height: 26, padding: 0, cursor: "pointer", color: T.textMuted, fontSize: 11, lineHeight: 1 }}>✕</button>
                            </div>
                        </div>

                            <div data-agreement-doc
                                style={{ flex: "1 0 auto", padding: "24px 24px", background: "rgba(0,0,0,.16)" }}>
                                {/* THE DOCUMENT, fetched by id. Three distinct states,
                                    and "No content." is only ever the third. */}
                                {doc?.loading ? (
                                    <div style={{ background: T.cardHi, border: `1px solid ${T.border}`, borderRadius: 10, padding: "20px 18px", fontSize: 13, color: T.textMuted, textAlign: "center" }}>
                                        Loading the agreement…
                                    </div>
                                ) : doc?.error ? (
                                    <div style={{ background: `${T.danger}12`, border: `1px solid ${T.danger}40`, borderRadius: 10, padding: "16px 18px", fontSize: 13, lineHeight: 1.7, color: T.danger }}>
                                        {doc.error}
                                        <div style={{ color: T.textMuted, marginTop: 6, fontSize: 12 }}>
                                            Nothing can be signed until the wording is on screen.
                                        </div>
                                    </div>
                                ) : paper(true)}

                                {/* Only once EXECUTED: the server refuses a PDF before. */}
                                {active.status === "Executed" && doc && !doc.loading && !doc.error && (
                                    <div style={{ maxWidth: 1120, margin: "16px auto 0" }}>
                                        <Btn variant="secondary" disabled={busy} onClick={doDownload}>
                                            <Icon d={I.download} size={15} /> Download signed copy
                                        </Btn>
                                        <div style={{ fontSize: 10.5, color: T.textFaint, marginTop: 6, lineHeight: 1.5 }}>
                                            Includes the signature record: who signed, how, when the
                                            server recorded it, and the digest of the signed text.
                                        </div>
                                    </div>
                                )}
                            </div>

                        {/* STEP 3 — the signature popup, from "Sign here". GATED ON
                            THE BODY: signing exists only once the text is shown. */}
                        {reading && signOpen && (
                            <div style={overlay} onClick={() => setSignOpen(false)}>
                                <div data-agreement-sign onClick={e => e.stopPropagation()} style={dialog}>
                                    <div style={{ display: "flex", alignItems: "center", marginBottom: 12 }}>
                                        <div>
                                            <div style={{ fontSize: 20, fontWeight: 800, color: T.text, lineHeight: 1.25 }}>Add your signature</div>
                                            <div style={{ fontSize: 13.5, color: T.textMuted, marginTop: 2, lineHeight: 1.4 }}>It goes on the agreement in dark ink</div>
                                        </div>
                                        <button type="button" aria-label="Cancel" onClick={() => setSignOpen(false)}
                                            style={{ marginLeft: "auto", width: 34, height: 34, borderRadius: 10, border: `1px solid ${T.border}`, background: "none", color: T.textMuted, cursor: "pointer", display: "grid", placeItems: "center" }}>
                                            <Icon d={I.x} size={16} />
                                        </button>
                                    </div>
                                    <SignaturePad height={200} onChange={setSignSig} />
                                    {/* The consent, as a box you cannot miss. */}
                                    <label data-sign-consent style={{ display: "flex", gap: 12, alignItems: "flex-start", marginTop: 14, padding: "12px 14px", borderRadius: 12,
                                        background: signConsent ? `${T.success}14` : `${T.text}0D`, border: `1px solid ${signConsent ? `${T.success}66` : T.border}`,
                                        fontSize: 14, color: T.text, lineHeight: 1.5, cursor: "pointer" }}>
                                        <input type="checkbox" checked={signConsent} onChange={e => setSignConsent(e.target.checked)}
                                            style={{ width: 18, height: 18, marginTop: 2, accentColor: "#3EE0A1", flexShrink: 0 }} />
                                        <span>I have read this agreement and intend the signature above to be my signature on it.</span>
                                    </label>
                                    <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 16 }}>
                                        {/* WHAT IS RECORDED, not what it amounts to in law
                                            (no ETO claim without counsel-approved wording). */}
                                        <span title="Recorded in the audit log with the time, your IP address where it can be determined, and a digest of the text you signed."
                                            style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, color: T.textMuted, maxWidth: 300, lineHeight: 1.4 }}>
                                            <Icon d={I.shield} size={14} /> Time, method and a digest of the text are recorded
                                        </span>
                                        <span style={{ flex: 1 }} />
                                        <button type="button" onClick={() => setSignOpen(false)} style={neutral}>Cancel</button>
                                        <button type="button" data-use-signature disabled={!signSig.data || !signConsent}
                                            onClick={() => { setAdopted({ ...signSig }); setSignOpen(false); }}
                                            style={{ ...mint, opacity: !signSig.data || !signConsent ? 0.45 : 1, cursor: !signSig.data || !signConsent ? "not-allowed" : "pointer" }}>
                                            Use this signature
                                        </button>
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* Decline, from the ⋯ menu: the same two-step guard. */}
                        {reading && declineOpen && (
                            <div style={overlay} onClick={() => { setDeclineOpen(false); setDeclineReason(""); }}>
                                <div data-decline-dialog onClick={e => e.stopPropagation()} style={dialog}>
                                    <div style={{ fontSize: 12, fontWeight: 700, color: T.danger, textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 10 }}>
                                        Decline — this ends the agreement and cannot be undone
                                    </div>
                                    <input value={declineReason} maxLength={2000}
                                        onChange={e => setDeclineReason(e.target.value)}
                                        placeholder="Reason (optional — the other party will see this)"
                                        style={{ width: "100%", height: 44, boxSizing: "border-box", border: `1px solid ${T.border}`, borderRadius: 12, background: T.inputBg, color: T.text, fontSize: 14, padding: "0 14px", outline: "none", fontFamily: "inherit" }} />
                                    <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 14 }}>
                                        <button type="button" disabled={busy} onClick={() => { setDeclineOpen(false); setDeclineReason(""); }} style={neutral}>Keep reviewing</button>
                                        <button type="button" disabled={busy} onClick={doDecline}
                                            style={{ ...chipBtn, background: T.danger, color: "#fff" }}>{busy ? "Declining…" : "Confirm decline"}</button>
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* STEP 4 — done. */}
                        {doneInfo && (
                            <div style={overlay}>
                                <div data-sign-done style={{ ...dialog, width: "min(520px, 100%)", display: "flex", flexDirection: "column", alignItems: "center", gap: 12, textAlign: "center", padding: 30 }}>
                                    <span aria-hidden="true" style={{ width: 64, height: 64, borderRadius: "50%", display: "grid", placeItems: "center", background: "linear-gradient(135deg,#3EE0A1,#2EC4D6)", color: "#04212A" }}>
                                        <Icon d={I.check} size={30} />
                                    </span>
                                    <div style={{ fontFamily: "Literata, Georgia, serif", fontSize: 24, fontWeight: 600, color: T.text }}>
                                        {doneInfo.executed ? "You’re all set" : "Signed"}
                                    </div>
                                    <div style={{ fontSize: 14.5, color: T.textMuted }}>
                                        {doneInfo.executed
                                            ? `Everyone has signed. The agreement is final and ${senderName} has been told.`
                                            : `Your signature is recorded. Waiting for ${waitingFor.join(", ") || "the other signatures"}.`}
                                    </div>
                                    <div style={{ display: "flex", gap: 10, marginTop: 8 }}>
                                        {doneInfo.executed && <button type="button" disabled={busy} onClick={doDownload} style={mint}><Icon d={I.download} size={15} /> Download signed copy</button>}
                                        <button type="button" onClick={closeModal} style={neutral}>Back to agreements</button>
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
                );
            })()}

            {composing && (
                <DraftComposer
                    draft={composing === "new" ? null : composing}
                    onSaved={reload}
                    onClose={(msg) => { setComposing(null); if (msg) showToast(msg); }}
                />
            )}

            {toast && (
                <div style={{
                    position: "fixed", bottom: 28, left: "50%", transform: "translateX(-50%)", zIndex: 10000,
                    background: T.card, border: `1px solid ${T.border}`, borderRadius: 10,
                    padding: "10px 20px", fontSize: 13, color: T.text, boxShadow: T.shadowCard,
                }}>{toast}</div>
            )}
        </div>
    );
}
