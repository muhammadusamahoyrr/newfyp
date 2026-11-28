'use client';
/* Clients (2026-10-19, APPOINTMENT_FLOW_PLAN.md, Marhala 4; Batch C 2026-10-20).
 *
 * An INDEX, not a record of its own: everything comes from the server
 * (/lawyer-clients), which groups the SAME predicates the Dashboard and the
 * Appointments tabs count with (lawyer_actions). Nothing is guessed here.
 *
 * Each card shows the relationship (`stage`) and, apart from it, the ONE next
 * step (`next_action`, with its exact target) as its main button:
 *   Send terms > Record outcome > Answer request > View next appointment > Open case
 * Every other piece of waiting work stays visible as a chip (and opens it).
 * Terms already sent read "Waiting for client" -- the client owes that answer.
 * Message opens an engaged client's case on Messages, a prospective client's
 * appointment chat.
 *
 * "Suggest a meeting" only PROPOSES times on the client's case; the client
 * chooses, and only then is anything booked. A prospective client has no
 * case, so they have no such button: their meeting is the request itself. */
import { useState, useEffect, useCallback } from "react";
import { useTheme } from "./theme.js";
import { useCase } from "./theme.js";
import { Icon, I } from "./icons.jsx";
import { DRAFTING_TOKENS_CSS, draftingMode } from "./draftingTheme.js";
import { avatarBg } from "./utils.js";
import { listMyClients, listEngagements } from "@/lib/api.js";
import { formatPkt } from "@/lib/bookingTime.js";
import { ProposeMeetingModal, useEngagementActions } from "./CasesPage.jsx";

const STAGES = ["Engaged", "Hire request", "Consultation scheduled", "Appointment requested", "Closed", "Consultation completed"];
// Each stage's colour, from the drafting/Cases tokens (2026-10-20).
const STAGE_TONE = {
    "Engaged": "var(--brand-text)",
    "Hire request": "var(--gold)",
    "Consultation scheduled": "var(--teal-ink)",
    "Appointment requested": "var(--gold)",
    "Closed": "var(--muted)",
    "Consultation completed": "var(--c-petition, var(--teal-ink))",
};

/* The Cases page's look (CASES_HOME_CSS), for this page: the same tokens,
 * serif title, segmented filter, search box, cards and buttons. Scoped by
 * [data-clients-home] so it reaches nothing else. */
const CLIENTS_CSS = `[data-clients-home]{color:var(--ink);font:15px/1.5 "Hanken Grotesk",system-ui,sans-serif;-webkit-font-smoothing:antialiased;background:radial-gradient(900px 360px at 25% -80px,var(--glow),transparent 70%) no-repeat,var(--bg)}
[data-clients-home] *{box-sizing:border-box}
[data-clients-home] :focus-visible{outline:2px solid var(--focus);outline-offset:2px}
[data-clients-home] .cl-wrap{max-width:1320px;margin:0 auto;padding:22px clamp(16px,3vw,36px) 56px;display:grid;gap:18px}
[data-clients-home] .cl-crumbs{font-size:13px;color:var(--muted)}
[data-clients-home] .cl-crumbs b{color:var(--ink);font-weight:600}
[data-clients-home] .cl-head{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;flex-wrap:wrap}
[data-clients-home] .cl-head h1{margin:2px 0 0;font:600 30px/1.1 "Literata",Georgia,serif;letter-spacing:-.01em}
[data-clients-home] .cl-sum{margin-top:6px;font-size:13.5px;color:var(--muted)}
[data-clients-home] .cl-sum b{color:var(--ink);font-weight:700}
[data-clients-home] .cl-sum .warn,[data-clients-home] .cl-sum .warn b{color:var(--gold)}
[data-clients-home] .cl-search{display:flex;align-items:center;gap:8px;width:300px;height:38px;padding:0 12px;border-radius:10px;background:var(--surface);border:1px solid var(--line)}
[data-clients-home] .cl-search:focus-within{border-color:var(--focus);box-shadow:0 0 0 3px var(--brand-soft)}
[data-clients-home] .cl-search svg{color:var(--faint);flex:none}
[data-clients-home] .cl-search input{flex:1;min-width:0;border:0;outline:none;background:transparent;color:var(--ink);font:inherit;font-size:14.5px}
[data-clients-home] .cl-search input::placeholder{color:var(--faint)}
[data-clients-home] .cl-tabs{display:flex;flex-wrap:wrap;gap:2px;padding:3px;border-radius:999px;background:var(--surface);border:1px solid var(--line);width:fit-content;max-width:100%}
[data-clients-home] .cl-tab{display:inline-flex;align-items:center;gap:6px;height:30px;padding:0 13px;border-radius:999px;border:0;background:transparent;color:var(--muted);font:inherit;font-size:13px;font-weight:700;cursor:pointer;white-space:nowrap}
[data-clients-home] .cl-tab:hover{color:var(--hover-ink)}
[data-clients-home] .cl-tab[aria-pressed="true"]{background:var(--ink);color:var(--surface)}
[data-clients-home] .cl-tab .n{font-size:13px;font-weight:700;opacity:.85}
[data-clients-home] .cl-av{width:36px;height:36px;border-radius:50%;flex:none;display:inline-flex;align-items:center;justify-content:center;font-size:12.5px;font-weight:800;color:#e9fffb;box-shadow:inset 0 0 0 1px var(--line-strong)}
[data-clients-home] .cl-av.sm{width:30px;height:30px;font-size:11px}
[data-clients-home] .cl-name{display:block;font-size:14.5px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
[data-clients-home] .cl-muted{font-size:13px;color:var(--muted);min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
[data-clients-home] .cl-tags{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
[data-clients-home] .cl-stage{display:inline-flex;align-items:center;gap:6px;height:24px;padding:0 10px;border-radius:999px;font-size:12px;font-weight:700;color:var(--c);background:color-mix(in srgb,var(--c) 14%,transparent);white-space:nowrap}
[data-clients-home] .cl-wait{display:inline-flex;align-items:center;height:24px;padding:0 10px;border-radius:999px;font-size:12px;font-weight:700;color:var(--muted);background:var(--chip-n);white-space:nowrap}
[data-clients-home] .cl-b{display:inline-flex;align-items:center;justify-content:center;height:34px;padding:0 15px;border-radius:999px;border:1px solid transparent;font:inherit;font-size:13px;font-weight:700;cursor:pointer;white-space:nowrap}
[data-clients-home] .cl-b.gold{background:var(--gold);color:#241a05}
[data-clients-home] .cl-b.gold:hover{filter:brightness(1.06)}
[data-clients-home][data-mode="light"] .cl-b.gold{color:#fff}
[data-clients-home] .cl-b.teal{background:color-mix(in srgb,var(--teal-ink) 16%,transparent);border-color:color-mix(in srgb,var(--teal-ink) 38%,transparent);color:var(--teal-ink)}
[data-clients-home] .cl-b.teal:hover{background:color-mix(in srgb,var(--teal-ink) 24%,transparent)}
[data-clients-home] .cl-b.fill{background:var(--chip-n);border-color:var(--line);color:var(--ink)}
[data-clients-home] .cl-b.fill:hover{border-color:var(--hover-line);color:var(--hover-ink)}
[data-clients-home] .cl-acts{display:flex;gap:8px;justify-content:flex-end;align-items:center}
[data-clients-home] .cl-attn{border-radius:16px;border:1px solid color-mix(in srgb,var(--gold) 32%,transparent);background:linear-gradient(color-mix(in srgb,var(--gold) 6%,transparent),color-mix(in srgb,var(--gold) 6%,transparent)),var(--surface);box-shadow:var(--shadow-rest);padding:4px 0}
[data-clients-home] .cl-attn-h{display:flex;align-items:center;gap:8px;padding:9px 18px;font-size:14px}
[data-clients-home] .cl-attn-h .dot{width:8px;height:8px;border-radius:50%;background:var(--gold)}
[data-clients-home] .cl-attn-h .n{font-size:12px;font-weight:800;padding:1px 8px;border-radius:999px;background:color-mix(in srgb,var(--gold) 18%,transparent);color:var(--gold)}
[data-clients-home] .cl-arow{display:grid;grid-template-columns:36px minmax(0,1fr) auto;gap:12px;align-items:center;padding:10px 18px;border-top:1px solid color-mix(in srgb,var(--gold) 14%,transparent)}
[data-clients-home] .cl-who{min-width:0;display:flex;flex-direction:column;gap:2px}
[data-clients-home] .cl-who small{font-size:13px;color:var(--muted)}
[data-clients-home] .cl-table{border-radius:16px;border:1px solid var(--line);background:var(--surface);box-shadow:var(--shadow-rest)}
[data-clients-home] .cl-trow:last-child{border-radius:0 0 15px 15px}
[data-clients-home] .cl-cols{display:grid;gap:14px;padding:10px 18px;border-bottom:1px solid var(--line);font-size:12px;font-weight:700;color:var(--muted)}
[data-clients-home] .cl-trow{display:grid;gap:14px;align-items:center;padding:11px 18px;border-bottom:1px solid var(--line)}
[data-clients-home] .cl-trow:last-child{border-bottom:0}
[data-clients-home] .cl-trow:hover{background:var(--hover-tint)}
[data-clients-home] .cl-cell-client{display:flex;align-items:center;gap:11px;min-width:0}
[data-clients-home] .cl-cell-client small{display:block;font-size:12.5px;color:var(--muted)}
[data-clients-home] .cl-arow[data-focused],[data-clients-home] .cl-trow[data-focused]{box-shadow:inset 3px 0 0 var(--brand-text);background:var(--hover-tint)}
[data-clients-home] .cl-cases{display:flex;align-items:center;gap:8px;flex-wrap:wrap;min-width:0}
[data-clients-home] .cl-case{max-width:100%;text-align:left;background:none;border:0;padding:0;color:var(--teal-ink);font:inherit;font-size:13.5px;font-weight:600;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
[data-clients-home] .cl-case:hover{color:var(--hover-ink);text-decoration:underline;text-underline-offset:3px}
[data-clients-home] .cl-more{font-size:12.5px;color:var(--muted)}
[data-clients-home] .cl-chips{display:flex;gap:6px;flex-wrap:wrap;margin-top:4px}
[data-clients-home] .cl-chip{display:inline-flex;align-items:center;gap:6px;height:24px;padding:0 10px;border-radius:999px;border:0;background:var(--chip-n);color:var(--ink);font:inherit;font-size:12px;font-weight:700;cursor:pointer}
[data-clients-home] .cl-chip::before{content:"";width:6px;height:6px;border-radius:50%;background:var(--c,var(--brand-text))}
[data-clients-home] .cl-chip:hover{color:var(--hover-ink)}
[data-clients-home] .cl-trow .cl-b{height:30px;padding:0 14px;font-size:12.5px}
[data-clients-home] .cl-menu{position:relative}
[data-clients-home] .cl-menu summary{list-style:none;width:30px;height:30px;border-radius:999px;display:inline-flex;align-items:center;justify-content:center;background:var(--chip-n);border:1px solid var(--line);color:var(--ink);font-weight:800;cursor:pointer}
[data-clients-home] .cl-menu summary::-webkit-details-marker{display:none}
[data-clients-home] .cl-menu[open] summary{border-color:var(--hover-line)}
[data-clients-home] .cl-menu-list{position:absolute;right:0;top:36px;z-index:5;min-width:180px;padding:5px;border-radius:12px;background:var(--surface);border:1px solid var(--line-strong);box-shadow:0 12px 32px rgba(0,0,0,.28);display:grid;gap:2px}
[data-clients-home] .cl-menu-list button{height:34px;padding:0 12px;border:0;border-radius:8px;background:transparent;color:var(--ink);font:inherit;font-size:13px;font-weight:600;text-align:left;cursor:pointer}
[data-clients-home] .cl-menu-list button:hover{background:var(--hover-tint);color:var(--hover-ink)}
[data-clients-home] .cl-note{padding:40px 18px;border-radius:18px;border:1px solid var(--line);background:var(--surface);text-align:center;font-size:14px;color:var(--muted)}
[data-clients-home] .cl-sent{font-size:13.5px;color:var(--brand-text);font-weight:600}`;
const OPEN_APPT_KEY = "attorney:lawyer-open-appointment";
const FOCUS_KEY = "attorney:lawyer-focus-client";
// The primary step's words, and the chips for the rest of the waiting work.
const ACTION_LABEL = {
    send_terms: "Send terms", record_outcome: "Record outcome", answer_request: "Answer appointment request",
    view_appointment: "View next appointment", open_case: "Open case",
};
const CHIPS = [
    ["send_terms", "hire_requests", "hire request"],
    ["record_outcome", "outcomes", "outcome to record"],
    ["answer_request", "appointment_requests", "appointment request"],
];
const CLOSED_CASE = new Set(["closed", "dismissed"]);
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

function ClientsPage() {
    const { t } = useTheme();
    const { setPage, setOpenCaseId } = useCase();
    const [search, setSearch] = useState("");
    const [stage, setStage] = useState("All");
    const [state, setState] = useState({ status: "loading", items: [], totals: {} });
    const [propose, setPropose] = useState(null);       // { client, caseId }
    const [sent, setSent] = useState(null);

    const load = useCallback(() => {
        setState(s => ({ ...s, status: "loading" }));
        listMyClients().then(({ data, error }) => {
            if (error || !data) { setState({ status: "error", items: [], totals: {} }); return; }
            setState({ status: "ready", items: data.items || [], totals: data.totals || {} });
        }).catch(() => setState({ status: "error", items: [], totals: {} }));
    }, []);
    useEffect(() => { load(); }, [load]);

    // Send terms opens the terms dialog HERE (2026-10-20), the same one Cases
    // uses; it used to take the lawyer away to Cases. After sending, this
    // page re-reads so the card shows "Waiting for client".
    const eng = useEngagementActions(() => load(), (msg) => setSent(String(msg).replace(/^\W+\s*/u, "")));
    const [termsLoading, setTermsLoading] = useState(false);
    const openTermsHere = async (id) => {
        if (!id || termsLoading) return;
        setTermsLoading(true);
        const { data, error } = await listEngagements({ status: "requested" });
        setTermsLoading(false);
        const e = !error && Array.isArray(data) ? data.find(x => x.id === id) : null;
        if (e) { eng.openAccept(e); return; }
        // Not open any more (answered elsewhere, withdrawn): say so and re-read.
        setSent("That hire request is no longer waiting for your terms. The list has been refreshed.");
        load();
    };

    // The case workspace finds a case by `case_number || _id`.
    const openCase = (c, tab = null) => {
        try { if (tab) sessionStorage.setItem("attorney:lawyer-case-tab", tab); } catch { /* storage off */ }
        setOpenCaseId(c.case_number || c.id); setPage("cases");
    };
    const openAppointment = (id, thread = false) => {
        try {
            if (id) sessionStorage.setItem(OPEN_APPT_KEY, id);
            if (id && thread) sessionStorage.setItem("attorney:lawyer-open-appointment-thread", id);
        } catch { /* storage off */ }
        setPage("appointments");
    };
    // The same deep links the Dashboard uses, to the exact item.
    const go = {
        send_terms: (id) => openTermsHere(id),
        record_outcome: (id) => {
            try { if (id) sessionStorage.setItem("attorney:lawyer-record-outcome", id); } catch { /* storage off */ }
            setPage("appointments");
            if (id) window.dispatchEvent(new CustomEvent("attorney:record-outcome", { detail: id }));
        },
        answer_request: (id) => openAppointment(id),
        view_appointment: (id) => openAppointment(id),
        open_case: (id, c) => {
            const k = c.cases.find(x => x.id === id) || { id, case_number: c.targets?.case_number };
            openCase(k);
        },
    };
    const targetFor = (kind, c) => ({
        send_terms: c.targets?.engagement_id, record_outcome: c.targets?.outcome_appointment_id,
        answer_request: c.targets?.pending_appointment_id,
    })[kind];

    // Arriving from a case's "Profile": that client's card, in view and marked.
    const [focusId] = useState(() => {
        try { const v = sessionStorage.getItem(FOCUS_KEY); if (v) sessionStorage.removeItem(FOCUS_KEY); return v || null; } catch { return null; }
    });
    useEffect(() => {
        if (!focusId || state.status !== "ready") return;
        const safe = typeof CSS !== "undefined" && CSS.escape ? CSS.escape(focusId) : String(focusId).replace(/["\\]/g, "\\$&");
        const el = document.querySelector(`[data-client-card="${safe}"]`);
        el?.scrollIntoView?.({ behavior: "smooth", block: "center" });
    }, [focusId, state.status]);

    // A row's ⋯ menu closes on a click anywhere else, and only one is open.
    useEffect(() => {
        const close = (e) => {
            document.querySelectorAll("[data-clients-home] details[data-client-more][open]").forEach(d => {
                if (!d.contains(e.target)) d.removeAttribute("open");
            });
        };
        document.addEventListener("mousedown", close);
        return () => document.removeEventListener("mousedown", close);
    }, []);

    const q = search.trim().toLowerCase();
    const shown = state.items.filter(c => (stage === "All" || c.stage === stage) && (!q || c.name.toLowerCase().includes(q)));
    const total = state.items.length;

    // The main button: the server's next step, to its exact target. Then
    // Message (case Messages / appointment chat) and, for an engaged client,
    // Suggest a meeting. A client with nothing to do gets the history view.
    const actionsFor = (c) => {
        const out = [];
        const na = c.next_action;
        if (na && ACTION_LABEL[na.kind]) {
            out.push({ key: "primary", label: ACTION_LABEL[na.kind], icon: na.kind === "open_case" ? I.cases : I.calendar,
                variant: "accent", primary: true, run: () => go[na.kind](na.target_id, c) });
        } else if (c.latest_appointment_id) {
            out.push({ key: "history", label: "View consultation", icon: I.calendar, variant: "secondary", run: () => openAppointment(c.latest_appointment_id) });
        }
        const m = c.message;
        if (m?.kind === "case") {
            const k = c.cases.find(x => x.id === m.target_id) || { id: m.target_id, case_number: m.case_number };
            out.push({ key: "message", label: "Message", icon: I.chat, variant: "secondary", run: () => openCase(k, "messages") });
        } else if (m?.kind === "appointment") {
            out.push({ key: "message", label: "Message", icon: I.chat, variant: "secondary", run: () => openAppointment(m.target_id, true) });
        }
        if (c.stage === "Engaged" && c.targets?.case_id) {
            out.push({ key: "suggest", label: "Suggest a meeting", icon: I.calendar, variant: "secondary", run: () => setPropose({ client: c.name, caseId: c.targets.case_id }) });
        }
        return out;
    };

    const chip = (label, count) => {
        const on = stage === label;
        return (
            <button key={label} type="button" className="cl-tab" data-stage-filter={label} aria-pressed={on} onClick={() => setStage(label)}>
                {label} <span className="n">{count}</span>
            </button>
        );
    };
    // The page's one-line summary: how many, and how many need the lawyer.
    const needYou = state.items.filter(c => c.next_action && ["send_terms", "record_outcome", "answer_request"].includes(c.next_action.kind)).length;
    const waiting = state.items.filter(c => c.waiting_for_client > 0).length;
    // Layout D (2026-11-28, as previewed): the clients whose next step is the
    // lawyer's sit on top under "Needs you", each with the reason in words and
    // that one step; under them the stage tabs and a quiet table of EVERY
    // client, each row opening the client's case or appointment. Message and
    // Suggest a meeting sit in the row's ⋯ menu. Data and handlers unchanged.
    const NEEDS = new Set(["send_terms", "record_outcome", "answer_request"]);
    const REASON = {
        send_terms: "Asked to hire you — your terms haven't been sent",
        record_outcome: "A consultation is over — its outcome isn't recorded",
        answer_request: "Asked for an appointment — accept it or suggest other times",
    };
    const attn = shown.filter(c => NEEDS.has(c.next_action?.kind));
    const initials = (name) => name.split(" ").filter(Boolean).map(n => n[0]).join("").toUpperCase().slice(0, 2) || "C";
    const COLS = "minmax(0,1.4fr) 190px minmax(0,1.6fr) 160px 116px";
    const avatar = (c, size) => {
        const ini = initials(c.name);
        return <span className={`cl-av${size ? ` ${size}` : ""}`} style={{ background: avatarBg(ini) }} aria-hidden="true">{ini}</span>;
    };
    const chipsFor = (c) => {
        const chips = CHIPS.filter(([kind, key]) => (c.pending?.[key] || 0) > 0 && kind !== c.next_action?.kind);
        if (!chips.length) return null;
        return (
            <span className="cl-chips" data-client-chips>
                {chips.map(([kind, key, word]) => (
                    <button key={kind} type="button" className="cl-chip" data-client-chip={kind}
                        style={{ "--c": kind === "answer_request" ? "var(--teal-ink)" : "var(--gold)" }}
                        onClick={() => go[kind](targetFor(kind, c), c)}>
                        {plural(c.pending[key], word)}
                    </button>
                ))}
            </span>
        );
    };
    // A row's "Open": its next step when that is just a place to go, else the
    // client's first case, else their latest or pending appointment.
    const openFor = (c) => {
        const na = c.next_action;
        if (na && (na.kind === "open_case" || na.kind === "view_appointment")) return () => go[na.kind](na.target_id, c);
        if (c.cases[0]) return () => openCase(c.cases[0]);
        const appt = c.latest_appointment_id || c.targets?.pending_appointment_id;
        return appt ? () => openAppointment(appt) : null;
    };
    const lastSeen = (c) => {
        if (c.next_appointment?.at) return `Next: ${formatPkt(c.next_appointment.at, { weekday: "short", day: "numeric", month: "short" })}`;
        return c.last_activity ? formatPkt(c.last_activity, { day: "numeric", month: "short", year: "numeric" }) : "—";
    };

    return (
        <div data-clients-home data-drafting-theme data-mode={draftingMode(t)} data-lenis-prevent style={{ height: "100%", overflowY: "auto" }}>
            <style>{`${DRAFTING_TOKENS_CSS}\n${CLIENTS_CSS}`}</style>
            <div className="cl-wrap">
                <div>
                    <nav className="cl-crumbs" aria-label="Breadcrumb">Practice / <b>Clients</b></nav>
                    <div className="cl-head">
                        <div>
                            <h1>Clients</h1>
                            <div className="cl-sum">
                                {state.status === "loading" ? <span>Loading…</span> : state.status === "error" ? <span>&nbsp;</span> : (<>
                                    <span><b>{plural(total, "client")}</b> · from your appointments and cases</span>
                                    {" · "}<span className={needYou > 0 ? "warn" : undefined}><b>{needYou}</b> need{needYou === 1 ? "s" : ""} you</span>
                                    {" · "}<span><b>{waiting}</b> waiting for the client</span>
                                </>)}
                            </div>
                        </div>
                        {state.status === "ready" && total > 0 && (
                            <label className="cl-search">
                                <Icon d={I.search} size={15} />
                                <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search clients…" aria-label="Search clients" />
                            </label>
                        )}
                    </div>
                </div>

                {sent && <div role="status" className="cl-sent">{sent}</div>}

                {state.status === "loading" ? (
                    <div className="cl-note">Loading clients…</div>
                ) : state.status === "error" ? (
                    <div role="alert" data-clients-error className="cl-note">
                        Could not load your clients. This is not the same as having none.
                        <div style={{ marginTop: 12 }}><button type="button" className="cl-b fill" onClick={load}>Try again</button></div>
                    </div>
                ) : total === 0 ? (
                    <div className="cl-note">No clients yet. People who request a consultation or hire you appear here.</div>
                ) : (<>
                    {/* 1. Needs you: the reason and the one step, per client */}
                    {attn.length > 0 && (
                        <section className="cl-attn" aria-label="Clients who need you" data-clients-attn>
                            <div className="cl-attn-h"><span className="dot" aria-hidden="true" /><b>Needs you</b><span className="n">{attn.length}</span></div>
                            {attn.map(c => {
                                const acts = actionsFor(c).filter(x => x.primary || x.key === "message");
                                return (
                                    <div key={c.client_id} className="cl-arow" data-client-attn={c.client_id}>
                                        {avatar(c)}
                                        <span className="cl-who">
                                            <b className="cl-name">{c.name}</b>
                                            <small>{REASON[c.next_action.kind]}</small>
                                            {chipsFor(c)}
                                        </span>
                                        <span className="cl-acts">
                                            {acts.map(x => (
                                                <button key={x.key} type="button" className={x.primary ? "cl-b gold" : "cl-b teal"}
                                                    {...(x.primary ? { "data-client-primary": c.next_action.kind } : { "data-client-action": x.key })} onClick={x.run}>
                                                    {x.label}
                                                </button>
                                            ))}
                                        </span>
                                    </div>
                                );
                            })}
                        </section>
                    )}

                    {/* 2. The stage tabs, then every client as one quiet row */}
                    <div className="cl-tabs" role="group" aria-label="Filter by stage">
                        {chip("All", total)}
                        {STAGES.filter(s => state.totals[s]).map(s => chip(s, state.totals[s]))}
                    </div>

                    {shown.length === 0 ? (
                        <div className="cl-note">No clients match.</div>
                    ) : (
                        <section className="cl-table" aria-label="Clients" data-clients-table>
                            <div className="cl-cols" style={{ gridTemplateColumns: COLS }}>
                                <span>Client</span><span>Stage</span><span>Cases</span><span>Last activity</span><span />
                            </div>
                            {shown.map(c => {
                                const first = c.cases[0];
                                const open = openFor(c);
                                const more = actionsFor(c).filter(x => x.key === "message" || x.key === "suggest");
                                return (
                                    <div key={c.client_id} className="cl-trow" style={{ gridTemplateColumns: COLS }}
                                        data-client-card={c.client_id} data-stage={c.stage} data-focused={focusId === c.client_id || undefined}>
                                        <span className="cl-cell-client">{avatar(c, "sm")}<b className="cl-name">{c.name}</b></span>
                                        <span className="cl-tags">
                                            <span className="cl-stage" style={{ "--c": STAGE_TONE[c.stage] || "var(--muted)" }}>{c.stage}</span>
                                            {c.waiting_for_client > 0 && <span className="cl-wait" data-client-waiting>Waiting for client</span>}
                                        </span>
                                        <span className="cl-cases">
                                            {first ? (<>
                                                <button type="button" className="cl-case" data-client-case={first.id} onClick={() => openCase(first)} title={first.title}>
                                                    {first.title}{CLOSED_CASE.has(first.status) ? " (closed)" : ""}
                                                </button>
                                                {c.cases.length > 1 && <span className="cl-more">+{c.cases.length - 1}</span>}
                                            </>) : <span className="cl-muted">No case yet</span>}
                                        </span>
                                        <span className="cl-muted">{lastSeen(c)}</span>
                                        <span className="cl-acts">
                                            {open && <button type="button" className="cl-b fill" data-client-open onClick={open}>Open</button>}
                                            {more.length > 0 && (
                                                <details className="cl-menu" data-client-more>
                                                    <summary aria-label={`More for ${c.name}`}>⋯</summary>
                                                    <div className="cl-menu-list" role="menu">
                                                        {more.map(x => (
                                                            <button key={x.key} type="button" role="menuitem" data-client-action={x.key}
                                                                onClick={(e) => { e.currentTarget.closest("details")?.removeAttribute("open"); x.run(); }}>
                                                                {x.label}
                                                            </button>
                                                        ))}
                                                    </div>
                                                </details>
                                            )}
                                        </span>
                                    </div>
                                );
                            })}
                        </section>
                    )}
                </>)}
            </div>
            {eng.termsModal}
            {propose && (
                <ProposeMeetingModal client={propose.client} caseId={propose.caseId} onClose={() => setPropose(null)}
                    onSent={() => { setSent(`Proposal sent — ${propose.client} will choose a time.`); setPropose(null); }} />
            )}
        </div>
    );
}
export { ClientsPage };
