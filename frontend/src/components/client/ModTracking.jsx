'use client';
import { useState, useEffect, useRef, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { DARK, LIGHT, useT } from "./theme.js";
import { clientThemeOnTokens } from "./clientTheme.js";
import { useLang, useIsMobile } from "@/lib/i18n.jsx";
import { useCase } from "./CaseContext.jsx";
import VideoJoin, { useVideoConfigured } from "@/components/shared/VideoJoin.jsx";
import { PreJoinModal } from "@/components/shared/PreJoin.jsx";
import ReviewLawyerDialog from "./ReviewLawyerDialog.jsx";
import HireDialog from "./HireDialog.jsx";
import HireRequests, { feeLabel } from "./HireRequests.jsx";
import { caseHero, pickEngagement, stageWindow, journeyStages } from "@/lib/caseHero.js";
import { appointmentTodos, caseTodos } from "@/lib/caseTodos.js";
import { caseUpdates, groupByDay, caseDetails } from "@/lib/caseUpdates.js";
import { getReviewEligibility, errorCode } from "@/lib/api.js";

// The hire steps that open on this page (2026-10-20) instead of the Lawyers page.
const HIRE_HERE = new Set(["none", "requested", "terms_proposed"]);
// The front of the page is a TO-DO list, not a second history: a finished
// consultation is shown there only while the CLIENT has a step to take (hire
// not decided yet, or terms to answer), and only for this long after it.
const NEXT_STEP_DAYS = 30;
// The lawyer side's Meeting colour: a meeting on a case already with a lawyer.
const CASE_MEETING_BLUE = "#5ab3ff";
const NEXT_STEP_STATES = new Set(["none", "terms_proposed"]);
const isRecentCompleted = (a, now = Date.now()) => a.status === "completed"
    && a.scheduled_at && now - new Date(a.scheduled_at).getTime() <= NEXT_STEP_DAYS * 864e5;
import { confirmedCases, caseStatusLabel, isDraftCase } from "@/lib/caseStatus.js";
import { listAgreements, listCases, getCase, getCaseTimeline, listAppointments, cancelAppointment as apiCancelAppointment, getAppointment as apiGetAppointment, rescheduleAppointment as apiRescheduleAppointment, listMessages as apiListMessages, sendMessage as apiSendMessage, listDocuments as apiListDocuments, downloadDocument as apiDownloadDocument, fetchDocumentPreviewUrl, myDocumentsV2, fetchRevisionPreview, downloadDocumentFile, listPayments, startCheckout, mockPay, downloadReceipt, openAppointmentDispute, listAppointmentDisputes, getBookableSlots, listMeetingProposals, acceptMeetingProposal, declineMeetingProposal, listEngagements, listAppointmentFiles as apiListAppointmentFiles, uploadAppointmentFile as apiUploadAppointmentFile, openAppointmentFile as apiOpenAppointmentFile, deleteAppointmentFile as apiDeleteAppointmentFile, acceptAppointmentSuggestion as apiAcceptAppointmentSuggestion, proposeNewTime as apiProposeNewTime, withdrawNewTime as apiWithdrawNewTime, declineNewTime as apiDeclineNewTime, acceptNewTime as apiAcceptNewTime, getSummaryDraft as apiGetSummaryDraft, readSharedSummary as apiReadSharedSummary, shareSummary as apiShareSummary, revokeSummary as apiRevokeSummary } from "@/lib/api.js";
import { formatPkt, pktToday, pktDayKey, pktHourMinute, pktSlotToUtcISO, isPktSlotPast } from "@/lib/bookingTime.js";
import { onNotification, matterHref } from "@/lib/notificationTarget.js";
import { useClientRouter } from "./clientNav.js";
import { useAuth } from "@/context/AuthContext.jsx";
import { requestDocumentsView } from "@/lib/documentsNav.js";
import { AppointmentThread } from "@/components/shared/AppointmentThread.jsx";
import { documentStatusView } from "@/lib/documentStatus.js";
import { useAgreementBuilderOn } from "./useAgreementBuilder.js";
import { shortMatterTitle, fullMatterTitle, matterLabel } from "@/lib/matterTitle.js";

// ─── DATA ─────────────────────────────────────────────────────────────────────
// Nothing is hardcoded here on purpose. This block used to hold five arrays of
// invented data — two lawsuits ("Ahmad vs. Tech Corp Ltd.", Judge M. Tariq),
// a five-step court timeline, documents, a deadline feed and a whole fabricated
// conversation with a lawyer about "Exhibit C pages 8-14". Some were fallbacks
// for an empty API, but the milestones, documents and messages rendered
// unconditionally, so every real case displayed someone else's invented
// litigation. Every screen below now shows what the API actually returned, and
// an honest empty state when that is nothing.

// ─── API MAPPERS ──────────────────────────────────────────────────────────────
/** The hearing to show as "next": the earliest one with no outcome whose
 *  Pakistan day is today or later. Not `hearing_dates[0]`, which is the
 *  OLDEST by insertion and never moved on after an adjournment, a reschedule
 *  or a new date. */
export function nextHearingOf(hearings = []) {
    const today = pktToday();
    return hearings
        .filter(h => h && !h.outcome && h.date && pktDayKey(h.date) >= today)
        .sort((x, y) => new Date(x.date) - new Date(y.date))[0] || null;
}

function hearingLabel(h) {
    if (!h) return "—";
    const day = formatPkt(h.date, { month: "short", day: "numeric", year: "numeric" });
    return h.time ? `${day}, ${h.time}` : day;
}

function mapApiCase(c) {
    const hearings = c.hearing_dates || [];
    const milestones = c.milestones || [];
    const completedCount = milestones.filter(m => m.completed).length;
    // The real number of milestones: no invented "out of 5".
    const total = milestones.length;
    const pct = total > 0 ? Math.round(completedCount / total * 100) : 0;
    const next = nextHearingOf(hearings);
    // The court and judge from the hearing that matters now, else the latest.
    const ref = next || [...hearings].sort((x, y) => new Date(y.date) - new Date(x.date))[0];
    return {
        id: c._id || c.id,
        title: c.title || "Case",
        caseNumber: c.case_number || null,
        status: c.status || "pending",
        type: c.case_type || "civil",
        filed: c.created_at ? formatPkt(c.created_at, { month: "short", day: "numeric", year: "numeric" }) : "—",
        court: ref?.court || "—",
        judge: ref?.judge || "—",
        lawyer: c.lawyer_id ? c.lawyer_id.slice(-6) : "—",
        lawyerAssigned: !!c.lawyer_id,
        progress: completedCount,
        total,
        nextHearing: hearingLabel(next),
        nextHearingRaw: next,
        pct,
    };
}

function mapApiMilestone(m, idx) {
    const date = new Date(m.date);
    return {
        id: idx + 1,
        at: new Date(m.date).getTime() || 0,
        status: m.completed ? "done" : "pending",
        event: m.title,
        date: date.toLocaleDateString("en-US", { month: "short", day: "numeric" }),
        time: date.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" }),
        desc: m.description || "",
        tag: m.completed ? "complete" : "pending",
        milestoneId: `m${idx + 1}`,
    };
}

/** A hearing as a timeline entry, so the Hearings tab has real rows. The
 *  outcome (what the lawyer recorded) is the court's instruction to show. */
export function mapApiHearing(h, idx) {
    // The court moved it: say from when, and why, as the lawyer recorded it.
    // Only the notification said so before, and that scrolls away.
    const moved = Array.isArray(h.reschedules) && h.reschedules.length ? h.reschedules[h.reschedules.length - 1] : null;
    const movedText = moved
        ? `Moved from ${formatPkt(moved.from_date, { month: "short", day: "numeric" })}${moved.reason ? ` — ${moved.reason}` : ""}`
        : null;
    return {
        id: `h-${h._id || idx}`,
        status: h.outcome ? "done" : "pending",
        event: h.purpose || "Hearing",
        date: formatPkt(h.date, { month: "short", day: "numeric" }),
        time: h.time || "",
        sortAt: new Date(h.date).getTime() || 0,
        desc: [h.court, movedText, h.outcome_label, h.outcome_note].filter(Boolean).join(" · "),
        tag: "hearing",
        milestoneId: `h-${h._id || idx}`,
    };
}

// ─── PRIMITIVES ───────────────────────────────────────────────────────────────

const Badge = ({ variant = "primary", children, t, sm }) => {
    const map = { primary: t.badgePrimary, success: t.badgeSuccess, danger: t.badgeDanger, warn: t.badgeWarn, info: t.badgeInfo, gray: t.badgeGray };
    const b = map[variant] || map.primary;
    return (
        <span style={{
            display: "inline-flex", alignItems: "center", gap: 4, fontSize: sm ? 11.5 : 12.5, fontWeight: 700,
            padding: sm ? "3px 9px" : "4px 11px", borderRadius: 20, background: b.bg, color: b.color, border: `1px solid ${b.border}`, whiteSpace: "nowrap"
        }}>
            {children}
        </span>
    );
};

const Card = ({ children, t, style = {}, onClick, ...rest }) => (
    <div {...rest} onClick={onClick} style={{
        background: t.card, borderRadius: 16, border: `1px solid ${t.border}`,
        boxShadow: t.shadowCard, overflow: "hidden", position: "relative", cursor: onClick ? "pointer" : "default", transition: "all 0.2s", ...style
    }}
        onMouseEnter={onClick ? e => { e.currentTarget.style.boxShadow = t.shadowHover; e.currentTarget.style.borderColor = t.borderHi; } : undefined}
        onMouseLeave={onClick ? e => { e.currentTarget.style.boxShadow = t.shadowCard; e.currentTarget.style.borderColor = t.border; } : undefined}>
        <div style={{ position: "relative", zIndex: 1 }}>{children}</div>
    </div>
);

// Says plainly that there is nothing here, rather than filling the space with
// invented content. Same principle as the 2FA and session rows in ModProfile:
// an empty screen a user can trust beats a populated one they cannot.
const Empty = ({ icon = "—", title, desc, t }) => (
    <div style={{
        padding: "26px 20px", textAlign: "center",
        display: "flex", flexDirection: "column", alignItems: "center", gap: 6,
    }}>
        <div style={{ fontSize: 15, fontWeight: 700, color: t.textDim }}>{title}</div>
        {desc && <div style={{ fontSize: 13.5, color: t.textMuted, lineHeight: 1.6, maxWidth: 420 }}>{desc}</div>}
    </div>
);

// Section heading. It used to lead with an emoji in a tinted tile (🕐 📊 📋 📁),
// which read as generated; the title carries the meaning (2026-11-23).
const SH = ({ title, desc, badge, t }) => (
    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "18px 22px", borderBottom: `1px solid ${t.border}` }}>
        <div style={{ flex: 1 }}>
            <div style={{ fontSize: 16.5, fontWeight: 800, color: t.text }}>{title}</div>
            {desc && <div style={{ fontSize: 13.5, color: t.textMuted, marginTop: 2 }}>{desc}</div>}
        </div>
        {badge}
    </div>
);

const Btn = ({ children, variant = "ghost", onClick, style = {}, t, full, disabled }) => {
    const [hov, setHov] = useState(false);
    const vs = {
        ghost: { background: hov ? t.cardHi : "transparent", border: `1px solid ${hov ? t.borderHi : t.border}`, color: t.textDim },
        primary: { background: disabled ? "rgba(64,240,220,0.12)" : hov ? t.primaryDim : t.primary, border: `1px solid ${disabled ? t.border : t.primary}`, color: disabled ? t.textFaint : t.mode === "dark" ? "#1A2E35" : "#fff" },
        danger: { background: "rgba(255,107,122,0.1)", border: "1px solid rgba(255,107,122,0.3)", color: t.danger },
    };
    return (
        <button onClick={disabled ? undefined : onClick} onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)} disabled={disabled}
            style={{
                display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6, padding: "10px 18px",
                borderRadius: 10, cursor: disabled ? "not-allowed" : "pointer", fontSize: 13.5, fontWeight: 700, transition: "all 0.18s",
                width: full ? "100%" : undefined, opacity: disabled ? 0.6 : 1, ...(vs[variant] || vs.ghost), ...style
            }}>
            {children}
        </button>
    );
};

const Inp = ({ placeholder, value, onChange, type = "text", t, style = {} }) => {
    const [f, setF] = useState(false);
    return (
        <input type={type} placeholder={placeholder} value={value} onChange={e => onChange(e.target.value)}
            onFocus={() => setF(true)} onBlur={() => setF(false)}
            style={{
                width: "100%", background: f ? t.inputFocus : t.inputBg, border: `1px solid ${f ? t.primary : t.border}`,
                borderRadius: 10, padding: "9px 14px", color: t.text, fontSize: 13, outline: "none",
                transition: "all 0.2s", boxSizing: "border-box", ...style
            }} />
    );
};

const Tabs = ({ tabs, active, onChange, t }) => (
    <div style={{ display: "flex", gap: 0, borderBottom: `1px solid ${t.border}`, padding: "0 20px" }}>
        {tabs.map(tab => (
            <button key={tab.key} onClick={() => onChange(tab.key)} style={{
                padding: "12px 16px", border: "none",
                background: "transparent", cursor: "pointer", fontSize: 14, fontWeight: 700, transition: "all 0.15s",
                borderBottom: `2px solid ${active === tab.key ? t.primary : "transparent"}`, marginBottom: -1,
                color: active === tab.key ? t.primary : t.textMuted
            }}>
                {tab.label}{tab.count != null ? ` (${tab.count})` : ""}</button>
        ))}
    </div>
);

const TAB_TO_PAGE = { summary: "overview", timeline: "timeline", documents: "documents", messages: "communication", payments: "payments" };
const PAGE_TO_TAB = { overview: "summary", timeline: "timeline", documents: "documents", communication: "messages", payments: "payments" };

const BackToMatters = ({ t, onClick }) => (
    <button type="button" data-to-matters onClick={onClick || undefined}
        style={{ display: "inline-flex", alignItems: "center", gap: 8, background: "none", border: "none", padding: 0, cursor: "pointer",
            color: t.primary, fontSize: 14, fontWeight: 700 }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M19 12H5M12 5l-7 7 7 7" /></svg>
        My matters
    </button>
);

// ─── CASE BAR (2026-11-23, Tracking v2) ──────────────────────────────────────
// One quiet line instead of a second "CaseTrack" sidebar and a top bar (which
// showed the raw case id, a second bell and an avatar the app sidebar already
// has): where you are on the left, the case's sections as tabs on the right.
const CASE_TABS = [
    { key: "overview", label: "Overview" },
    { key: "timeline", label: "Timeline" },
    { key: "documents", label: "Documents" },
    { key: "communication", label: "Messages" },
    { key: "payments", label: "Payments" },
];

// Short title (an old matter's title is the whole intake question) + number.
const caseLabel = c => (c ? matterLabel(c.title, c.caseNumber, 60) : "Case");

function CaseBar({ t, page, onNavigate, activeCase, cases, onCaseSwitch, onMatters = null }) {
    const [open, setOpen] = useState(false);
    const box = useRef(null);
    useEffect(() => {
        if (!open) return undefined;
        const away = e => { if (box.current && !box.current.contains(e.target)) setOpen(false); };
        const esc = e => { if (e.key === "Escape") setOpen(false); };
        document.addEventListener("mousedown", away);
        document.addEventListener("keydown", esc);
        return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); };
    }, [open]);
    const others = cases.filter(c => c.id !== activeCase?.id);
    return (
        <div data-case-bar style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap", minHeight: 40, marginBottom: 18 }}>
            <nav aria-label="Breadcrumb" ref={box} style={{ position: "relative", display: "flex", alignItems: "center", gap: 8, minWidth: 0, fontSize: 13.5, color: t.textMuted }}>
                <BackToMatters t={t} onClick={onMatters} />
                {activeCase && (<>
                    <span aria-hidden="true">/</span>
                    <b data-case-bar-title title={fullMatterTitle(activeCase.title)} style={{ color: t.text, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 420 }}>
                        {shortMatterTitle(activeCase.title, 48)}
                    </b>
                    {activeCase.caseNumber && <span data-case-bar-number style={{ whiteSpace: "nowrap", color: t.textMuted }}>· {activeCase.caseNumber}</span>}
                </>)}
                {others.length > 0 && (
                    <button type="button" aria-haspopup="menu" aria-expanded={open} data-case-switch onClick={() => setOpen(v => !v)}
                        style={{ display: "inline-flex", alignItems: "center", gap: 4, height: 28, padding: "0 10px", borderRadius: 999,
                            ...NEUTRAL_FILL, fontSize: 12.5, fontWeight: 700, cursor: "pointer" }}>
                        Switch
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
                    </button>
                )}
                {open && (
                    <div role="menu" aria-label="Your other cases" style={{ position: "absolute", top: "calc(100% + 6px)", left: 0, minWidth: 300, zIndex: 50,
                        background: t.card, border: `1px solid ${t.border}`, borderRadius: 14, boxShadow: t.shadowHover, padding: 6 }}>
                        {others.map(c => (
                            <button key={c.id} type="button" role="menuitem" data-case-option={c.id} title={fullMatterTitle(c.title)}
                                onClick={() => { setOpen(false); onCaseSwitch(c.id); }}
                                style={{ display: "block", width: "100%", maxWidth: 420, textAlign: "left", padding: "9px 12px", borderRadius: 10, border: 0,
                                    whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                                    background: "transparent", color: t.text, cursor: "pointer", fontSize: 13.5, fontWeight: 600 }}
                                onMouseEnter={e => { e.currentTarget.style.background = t.cardHi; }}
                                onMouseLeave={e => { e.currentTarget.style.background = "transparent"; }}>
                                {caseLabel(c)}
                            </button>
                        ))}
                    </div>
                )}
            </nav>
            <nav aria-label="Case sections" className="case-tabs" style={{ marginLeft: "auto", display: "flex", gap: 2, padding: 4, borderRadius: 999, background: t.cardHi, maxWidth: "100%", overflowX: "auto" }}>
                {CASE_TABS.map(tab => {
                    const on = page === tab.key;
                    return (
                        <button key={tab.key} type="button" data-case-tab={tab.key} aria-current={on ? "page" : undefined}
                            onClick={() => onNavigate(tab.key)}
                            style={{ height: 32, padding: "0 14px", flexShrink: 0, borderRadius: 999, border: 0, cursor: "pointer", fontSize: 13, fontWeight: 700,
                                background: on ? "var(--chip-on-bg, #F3F2F4)" : "transparent", color: on ? "var(--chip-on-ink, #2A282C)" : t.textMuted }}>
                            {tab.label}
                        </button>
                    );
                })}
            </nav>
        </div>
    );
}

// ─── STATUS CARD (Tracking v2, 2026-11-23) ───────────────────────────────────
// The answer first, like an order-tracking page: one sentence for where the
// case is, the next date, the stage line, and who is handling it. It replaced
// a card that showed the same progress three times (a ring, a bar and "2/3
// steps") and named the case by its database id.
/** One read with an honest state (2026-11-23): "loading" until it answers,
 *  "error" when it fails, "ready" only with real data. An empty list is shown
 *  as "nothing" ONLY when its read is ready: a failed read used to look like
 *  "Nothing is waiting on you" and could hide terms or a fee.
 *  `read` returns the data or throws. A failed RE-read keeps what was shown
 *  but is still "error": the old data may be out of date (a fee requested
 *  since), so it can never back a "Nothing is waiting". */
function useSource(read, deps) {
    const [src, setSrc] = useState({ state: "loading", data: [] });
    const tick = useRef(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    const load = useCallback(() => {
        const mine = ++tick.current;
        Promise.resolve().then(read).then(
            data => { if (mine === tick.current) setSrc({ state: "ready", data }); },
            () => { if (mine === tick.current) setSrc(p => ({ state: "error", data: p.data })); });
    }, deps);
    useEffect(() => {
        setSrc({ state: "loading", data: [] });
        load();
        return () => { tick.current++; };
    }, [load]);
    return { ...src, reload: load };
}

const listOf = r => { if (!r || r.error || !Array.isArray(r.data)) throw new Error("read failed"); return r.data; };
const itemsOf = r => { if (!r || r.error || !Array.isArray(r.data?.items)) throw new Error("read failed"); return r.data.items; };

/** The signed-in user's id, or null outside an AuthProvider (a test, a preview). */
function useMyId() {
    let user = null;
    try { user = useAuth()?.user || null; } catch { user = null; }
    return user?._id || user?.id || null;
}

/** Read every pending agreement. A first-page-only read could incorrectly say
 *  nothing needs signing when the client's agreement is on a later page. */
const readPendingAgreements = async (caseId = null) => {
    const out = [];
    let page = 1, pages = 1;
    do {
        const r = await listAgreements({ page, page_size: 50, status: "pending", case_id: caseId });
        const rows = itemsOf(r);
        out.push(...rows);
        pages = Number.isInteger(r.data?.pages) ? r.data.pages : 1;
        page += 1;
    } while (page <= pages);
    return out;
};

/** Read every appointment needed to calculate client actions. Case pages ask
 * the server for one case; My Matters pages through the caller's whole list. */
const readAllAppointments = async (caseId = null) => {
    const out = [];
    let page = 1, pages = 1;
    do {
        const r = await listAppointments({ page, page_size: 50, needs_action: true,
            ...(caseId ? { case_id: caseId } : {}) });
        const rows = itemsOf(r);
        out.push(...rows);
        pages = Number.isInteger(r.data?.pages) ? r.data.pages : 1;
        page += 1;
    } while (page <= pages);
    return out;
};

/** Read the cursor-paginated V2 vault completely for authoritative case and
 *  My Matters action counts. Feature-disabled is a valid empty source. */
const readAllV2Documents = async (caseId = null, { needsAction = false } = {}) => {
    const out = [];
    let cursor = null;
    const seenCursors = new Set();
    let pages = 0;
    do {
        const r = await myDocumentsV2({ caseId, cursor, limit: 100, needsAction });
        if (r?.status === 404 && errorCode(r.error) === "feature_disabled") return [];
        if (!r || r.error || !Array.isArray(r.data?.items)) throw new Error(r?.error?.message || "Could not load drafted documents.");
        out.push(...r.data.items);
        if (!r.data.has_more) break;
        cursor = r.data.next_cursor;
        if (!cursor) throw new Error("The document list was incomplete.");
        if (seenCursors.has(cursor)) throw new Error("The document list repeated a page cursor.");
        seenCursors.add(cursor);
        pages += 1;
        if (pages >= 1000) throw new Error("The document list was too large to verify safely.");
    } while (cursor);
    return out;
};

/** The client's hire requests, read once for the page and re-read when one
 *  changes. `{ data, state, reload }`. */
function useEngagements(caseId = null) {
    // With a case: only that case's requests, filtered by the server (review
    // item 5). Without: every request (My matters).
    const src = useSource(() => Promise.resolve(listEngagements(caseId ? { caseId } : undefined)).then(listOf), [caseId]);
    const { reload } = src;
    useEffect(() => onNotification(n => {
        const type = String(n?.type || "");
        if (type.startsWith("engagement_") || type === "lawyer_assigned") reload();
    }), [reload]);
    return src;
}

/** What could not be checked, in words: ["fees", "documents"] → "fees and documents". */
const andList = xs => (xs.length <= 1 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);

function CheckFailed({ t, what, onRetry, children }) {
    return (
        <span role="alert" data-check-failed style={{ fontSize: 13, color: t.warn }}>
            {children || <>Couldn't check your {what}. Something may be waiting on you.</>}{" "}
            <button type="button" onClick={onRetry} style={{ background: "none", border: 0, padding: 0, cursor: "pointer", color: t.primary, fontWeight: 700, fontSize: 13 }}>Try again</button>
        </span>
    );
}

function CaseStatusHero({ t, activeCase, hearings = [], steps = [], engagements = [], engagementState = "ready", onAction }) {
    const engagement = pickEngagement(engagements, activeCase.id);
    const hero = caseHero({ caseInfo: activeCase, nextHearing: nextHearingOf(hearings), engagement, feeText: engagement ? feeLabel(engagement) : "", engagementState });
    // The lawyer's own milestones when there are any; otherwise the case's
    // journey from real facts (as the approved preview draws it), never blank.
    const fromMilestones = stageWindow(steps);
    const stages = fromMilestones.length ? fromMilestones
        : journeyStages({ caseInfo: activeCase, engagement, nextHearing: nextHearingOf(hearings), hadHearing: hearings.length > 0 });
    const warn = hero.tone === "warn";
    const pill = warn ? { bg: `${t.warn}22`, ink: t.warn } : hero.tone === "muted" ? { bg: t.cardHi, ink: t.textMuted } : { bg: t.primaryGlow2, ink: t.primary };
    const meta = [activeCase.type && activeCase.type.charAt(0).toUpperCase() + activeCase.type.slice(1), activeCase.caseNumber].filter(Boolean).join(" · ");
    const outline = { display: "inline-flex", alignItems: "center", justifyContent: "center", height: 36, padding: "0 16px", borderRadius: 999,
        border: `1px solid ${t.primary}73`, background: "transparent", color: t.primary, fontWeight: 700, fontSize: 13, cursor: "pointer", textDecoration: "none" };
    const solid = { ...outline, border: 0, background: "var(--brand-solid, linear-gradient(135deg,#3EE0A1,#2EC4D6))", color: "var(--on-brand, #04212A)" };
    const act = (a, primary = false) => (
        <button key={a.label} type="button" data-hero-action={a.action} onClick={() => onAction(a.action, engagement)} style={primary ? solid : { ...outline, ...ON_TINT }}>{a.label}</button>
    );
    const p = hero.person;
    return (
        <section aria-label="Case status" data-case-hero={hero.tone}
            style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 250px", borderRadius: 18, background: t.card, border: `1px solid ${t.border}`, overflow: "hidden", marginBottom: 18 }}>
            <div style={{ padding: "18px 22px 16px", display: "flex", flexDirection: "column", gap: 10, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", fontSize: 12.5, fontWeight: 700, color: t.textMuted }}>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, height: 24, padding: "0 10px", borderRadius: 999, background: pill.bg, color: pill.ink }}>
                        <span aria-hidden="true" style={{ width: 7, height: 7, borderRadius: "50%", background: "currentColor" }} />{caseStatusLabel(activeCase.status)}
                    </span>
                    {meta && <span>{meta}</span>}
                </div>
                <div>
                    <h1 data-hero-headline style={{ margin: 0, font: "800 26px/1.15 Nunito, 'Hanken Grotesk', sans-serif", letterSpacing: "-.01em", color: t.text }}>{hero.headline}</h1>
                    {hero.sub && <p style={{ margin: "5px 0 0", fontSize: 14, color: t.textMuted }}>{hero.sub}</p>}
                    {hero.warning && (
                        <div data-hero-warning style={{ marginTop: 8 }}>
                            <CheckFailed t={t} what="" onRetry={() => onAction("retry-engagements", engagement)}>{hero.warning}</CheckFailed>
                        </div>
                    )}
                </div>
                {hero.primary && (
                    <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                        {act(hero.primary, true)}
                        {hero.secondary && act(hero.secondary)}
                    </div>
                )}
                {stages.length > 0 ? (
                    <ol aria-label="Stages" data-hero-stages style={{ listStyle: "none", margin: "4px 0 0", padding: 0, display: "grid", gridTemplateColumns: `repeat(${stages.length}, minmax(0, 1fr))` }}>
                        {stages.map((st, i) => (
                            <li key={i} aria-current={st.state === "now" ? "step" : undefined} data-stage={st.state} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                <div style={{ display: "flex", alignItems: "center" }}>
                                    <span aria-hidden="true" style={{ width: 22, height: 22, flexShrink: 0, borderRadius: "50%", boxSizing: "border-box", display: "grid", placeItems: "center",
                                        fontSize: 11, fontWeight: 800, color: "var(--on-brand, #04212A)",
                                        background: st.state === "done" ? t.primary : st.state === "now" ? t.card : "transparent",
                                        border: `2px solid ${st.state === "next" ? t.border : t.primary}`,
                                        boxShadow: st.state === "now" ? `0 0 0 4px ${t.primaryGlow2}` : "none" }}>{st.state === "done" ? "✓" : ""}</span>
                                    <span aria-hidden="true" style={{ flex: 1, height: 3, borderRadius: 2, background: i === stages.length - 1 ? "transparent" : st.state === "done" ? t.primary : t.border }} />
                                </div>
                                <div style={{ paddingRight: 10, lineHeight: 1.3 }}>
                                    <b style={{ display: "block", fontSize: 13, color: st.state === "next" ? t.textMuted : t.text }}>{st.title}</b>
                                    <span style={{ fontSize: 12, color: t.textMuted }}>{st.when}</span>
                                </div>
                            </li>
                        ))}
                    </ol>
                ) : (
                    <div data-hero-no-stages style={{ fontSize: 13, color: t.textMuted }}>The steps of this case appear here once your lawyer adds them.</div>
                )}
            </div>
            <aside aria-label={p.label} data-hero-person style={{ padding: "18px 18px", borderLeft: `1px solid ${t.border}`,
                // The theme's own soft brand tint over the card: right in Light, System and Dark alike.
                background: "var(--brand-soft, rgba(62,224,161,.13))", display: "flex", flexDirection: "column", justifyContent: "center", gap: 10 }}>
                {p.waiting && (
                    <span data-person-waiting style={{ alignSelf: "flex-start", display: "inline-flex", alignItems: "center", gap: 6, height: 24, padding: "0 10px", borderRadius: 999,
                        fontSize: 12, fontWeight: 800, background: `${t.warn}22`, color: t.warn }}>
                        <span aria-hidden="true" style={{ width: 7, height: 7, borderRadius: "50%", background: "currentColor" }} />Waiting on you</span>
                )}
                <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase", color: t.textMuted }}>{p.label}</div>
                {p.name && (
                    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                        <span aria-hidden="true" style={{ width: 40, height: 40, flexShrink: 0, borderRadius: "50%", display: "grid", placeItems: "center", fontWeight: 800, fontSize: 14,
                            background: "var(--brand-solid, linear-gradient(135deg,#3EE0A1,#2EC4D6))", color: "var(--on-brand, #04212A)" }}>{initialsOf(p.name)}</span>
                        <b style={{ fontSize: 15, color: t.text, lineHeight: 1.3 }}>{p.name}</b>
                    </div>
                )}
                <div style={{ fontSize: 12.5, color: t.textMuted, lineHeight: 1.45 }}>{p.sub}</div>
                {p.note && <div data-person-note style={{ fontSize: 13, color: t.text, lineHeight: 1.45 }}>{p.note}</div>}
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 2 }}>
                    {p.actions.map((a, i) => (
                        // The step waiting on the client is the card's one solid button (2026-11-25).
                        <button key={a.label} type="button" data-person-action={a.action} onClick={() => onAction(a.action, engagement)}
                            style={{ ...(p.waiting && i === 0 ? solid : { ...outline, ...ON_TINT }), flex: "1 1 auto", height: 36, fontSize: 13, padding: "0 12px", whiteSpace: "nowrap" }}>{a.label}</button>
                    ))}
                </div>
            </aside>
        </section>
    );
}

// ─── OVERVIEW DATA (Tracking v2, 2026-11-23) ─────────────────────────────────
// Read once for the Overview and shared by the to-do, the updates feed and the
// details: the client's fees, meeting proposals, this case's documents and
// its messages. Each re-reads when a matching notification arrives.
function useCaseOverviewData(caseId) {
    const payments = useSource(() => (caseId ? Promise.resolve(listPayments({ caseId })).then(listOf) : []), [caseId]);
    const proposals = useSource(() => (caseId ? Promise.resolve(listMeetingProposals({ case_id: caseId, status: "open", all: true })).then(listOf) : []), [caseId]);
    // V2 documents switched off answer 404 feature_disabled: that is "none", not a failure.
    const v2Docs = useSource(() => (caseId ? readAllV2Documents(caseId) : []), [caseId]);
    const legacyDocs = useSource(() => (caseId ? Promise.resolve(apiListDocuments(caseId)).then(listOf) : []), [caseId]);
    const messages = useSource(() => (caseId ? Promise.resolve(apiListMessages(caseId)).then(listOf) : []), [caseId]);
    const agreements = useSource(() => (caseId ? readPendingAgreements(caseId) : []), [caseId]);
    const appointments = useSource(() => (caseId ? readAllAppointments(caseId) : []), [caseId]);
    const reloads = { payments: payments.reload, proposals: proposals.reload, v2: v2Docs.reload, legacy: legacyDocs.reload, messages: messages.reload };
    useEffect(() => onNotification(n => {
        const type = String(n?.type || "");
        if (type.startsWith("payment_")) reloads.payments();
        if (type.startsWith("appointment_propos")) reloads.proposals();
        if (type.startsWith("document_") || type.startsWith("review_request_")) { reloads.v2(); reloads.legacy(); }
        if (type === "case_message" && String(n.payload?.case_id || "") === String(caseId)) reloads.messages();
        if (type.startsWith("agreement_")) agreements.reload();
        if (type.startsWith("appointment_")) appointments.reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }), [caseId, payments.reload, proposals.reload, v2Docs.reload, legacyDocs.reload, messages.reload, agreements.reload, appointments.reload]);
    // One row per document: V2 first, the legacy listing without the V2 ids.
    const v2Rows = (v2Docs.data || []).map(_mapV2Doc);
    const seen = new Set(v2Rows.map(d => d.id));
    const docRows = [...v2Rows, ...(legacyDocs.data || []).map(_mapApiDoc).filter(d => !seen.has(d.id))];
    const casePayments = (payments.data || []).filter(p => String(p.case_id || "") === String(caseId));
    const docsState = v2Docs.state === "error" || legacyDocs.state === "error" ? "error"
        : v2Docs.state === "ready" && legacyDocs.state === "ready" ? "ready" : "loading";
    return { payments, proposals, v2Docs, legacyDocs, messages, agreements, appointments, docRows, casePayments, docsState,
        reloadDocs: () => { v2Docs.reload(); legacyDocs.reload(); } };
}

// ─── YOUR TO-DO (Tracking v2, 2026-11-23) ────────────────────────────────────
// Only what the client can move on this case, each with one button: fees due,
// terms to answer, documents back from the lawyer, meeting times to choose.
function CaseTodos({ t, caseId, sources, userId = null, onAction }) {
    const [showAll, setShowAll] = useState(false);
    // sources: { name: { data, state, reload } } for hire requests, fees, meeting times, documents.
    const get = k => sources[k] || { data: [], state: "ready", reload: () => {} };
    const engagement = pickEngagement(get("hire requests").data, caseId);
    const all = caseTodos({ caseId, engagement, feeText: engagement ? feeLabel(engagement) : "",
        payments: get("fees").data, proposals: get("meeting times").data, appointments: get("appointments").data,
        docs: get("documents").data,
        agreements: get("agreements").data, userId });
    // The hire request's own step (answer the terms, confirm the work is
    // finished) is already the status card's headline, button and lawyer
    // panel: a second card for it was the same action twice (2026-11-25).
    const inHero = all.some(td => td.action === "engagement");
    const items = all.filter(td => td.action !== "engagement").map((td, i) => ({ ...td, primary: i === 0 }));
    const failed = Object.keys(sources).filter(k => sources[k].state === "error");
    const loading = Object.keys(sources).some(k => sources[k].state === "loading");
    const status = failed.length ? "error" : loading ? "loading" : "ready";
    const shown = showAll ? items : items.slice(0, 3);
    const outline = { display: "inline-flex", alignItems: "center", height: 36, padding: "0 16px", borderRadius: 999, cursor: "pointer",
        border: `1px solid ${t.primary}73`, background: "transparent", color: t.primary, fontWeight: 700, fontSize: 13 };
    const solid = { ...outline, border: 0, background: "var(--brand-solid, linear-gradient(135deg,#3EE0A1,#2EC4D6))", color: "var(--on-brand, #04212A)" };
    const second = { ...outline, ...ON_TINT };   // the other to-dos: teal outline (colour roles)
    return (
        <section aria-label="Your to-do" data-case-todos={items.length} data-todos-state={status} style={{ marginBottom: 20 }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 10 }}>
                <h2 style={{ margin: 0, fontSize: 16, fontWeight: 800, color: t.text }}>Your to-do</h2>
                {items.length > 0 && <span style={{ fontSize: 13, color: t.textMuted }}>
                    {status === "loading" ? `${items.length} found so far · Still checking…` : `${items.length} waiting on you`}</span>}
                {status === "error" && <CheckFailed t={t} what={andList(failed)} onRetry={() => failed.forEach(k => sources[k].reload())} />}
                {status === "loading" && !items.length && <span style={{ fontSize: 13, color: t.textMuted }}>Checking what's waiting on you…</span>}
                {status === "ready" && !items.length && <span style={{ fontSize: 13, color: t.textMuted }}>
                    {inHero ? "Nothing else is waiting on you — the lawyer's request is in the card above." : "Nothing is waiting on you right now."}</span>}
                {items.length > 3 && <button type="button" data-toggle-all-todos onClick={() => setShowAll(v => !v)}
                    style={{ border: 0, background: "none", padding: 0, cursor: "pointer", color: t.primary, fontSize: 13, fontWeight: 700 }}>
                    {showAll ? "Show fewer" : `Show all ${items.length}`}
                </button>}
            </div>
            {shown.length > 0 && (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 14 }}>
                    {shown.map(td => (
                        <article key={td.key} data-todo={td.action} style={{ display: "flex", flexDirection: "column", gap: 10, padding: "16px 18px", borderRadius: 16,
                            background: t.card, border: `1px solid ${td.warn ? `${t.warn}66` : t.border}` }}>
                            <span style={{ alignSelf: "flex-start", display: "inline-flex", alignItems: "center", height: 22, padding: "0 9px", borderRadius: 999, fontSize: 11.5, fontWeight: 800,
                                background: td.warn ? `${t.warn}22` : t.cardHi, color: td.warn ? t.warn : t.textMuted }}>{td.chip}</span>
                            <div style={{ lineHeight: 1.35 }}>
                                <b style={{ display: "block", fontSize: 15, color: t.text }}>{td.title}</b>
                                <span style={{ fontSize: 13, color: t.textMuted }}>{td.sub}</span>
                            </div>
                            <button type="button" onClick={() => onAction(td.action, td.action === "engagement" ? engagement : td)}
                                style={{ ...(td.primary ? solid : second), marginTop: "auto", alignSelf: "flex-start" }}>{td.cta}</button>
                        </article>
                    ))}
                </div>
            )}
        </section>
    );
}

// ─── UPDATES + DETAILS (Tracking v2, 2026-11-23) ─────────────────────────────
// What happened on the case, newest first, with a reply box to the lawyer;
// beside it the case's facts, money and files. Replaces four equal cards
// (Action Required, a timeline preview, Notifications, Documents) and a
// "Communication" card that only linked away.
function CaseUpdates({ t, caseId, groups, messagesState, missing = [], loadingAny = false, canReply, lawyerName, onSent, onRetry, onOpenMessages }) {
    const [text, setText] = useState("");
    const [sending, setSending] = useState(false);
    const [sendError, setSendError] = useState(null);
    const [showAll, setShowAll] = useState(false);
    const LIMIT = 6;
    let left = showAll ? Infinity : LIMIT;
    const shown = groups.map(g => { const items = g.items.slice(0, Math.max(0, left)); left -= items.length; return { ...g, items }; }).filter(g => g.items.length);
    const total = groups.reduce((n, g) => n + g.items.length, 0);
    const send = async () => {
        const body = text.trim();
        if (!body || sending || !caseId) return;
        setSending(true); setSendError(null);
        const { data, error } = await apiSendMessage(caseId, body);
        setSending(false);
        // Nothing was delivered: keep the text and say why.
        if (error || !data) { setSendError(error?.message || "Your message was not sent. Try again."); return; }
        setText("");
        onSent?.(data);
    };
    return (
        <section aria-label="Updates" data-case-updates={total} style={{ borderRadius: 18, background: t.card, border: `1px solid ${t.border}`, padding: "16px 20px", display: "flex", flexDirection: "column" }}>
            <div style={{ display: "flex", alignItems: "baseline", marginBottom: 4 }}>
                <h2 style={{ margin: 0, fontSize: 16, fontWeight: 800, color: t.text }}>Updates</h2>
                <button type="button" onClick={onOpenMessages} style={{ marginLeft: "auto", background: "none", border: 0, padding: 0, cursor: "pointer", fontSize: 13, fontWeight: 700, color: t.primary }}>All messages</button>
            </div>
            {missing.length > 0 && (
                <div style={{ margin: "8px 0" }}>
                    <CheckFailed t={t} what="" onRetry={onRetry}>Couldn't load the {andList(missing)} on this case, so some updates may be missing.</CheckFailed>
                </div>
            )}
            {total === 0 && !missing.length && (
                <div data-updates-empty style={{ fontSize: 13.5, color: t.textMuted, padding: "10px 0 14px" }}>
                    {loadingAny || messagesState === "loading" ? "Loading updates…" : "Nothing has happened on this case yet. Messages, documents and steps your lawyer marks will show here."}
                </div>
            )}
            {shown.map(g => (
                <div key={g.key}>
                    <div style={{ fontSize: 11.5, fontWeight: 800, letterSpacing: ".08em", textTransform: "uppercase", color: t.textMuted, margin: "10px 0 2px" }}>{g.label}</div>
                    {g.items.map(u => (
                        <div key={u.key} data-update={u.tag} style={{ display: "flex", gap: 12, padding: "9px 0" }}>
                            <span aria-hidden="true" style={{ width: 32, height: 32, flexShrink: 0, borderRadius: "50%", display: "grid", placeItems: "center", fontSize: 10.5, fontWeight: 800,
                                background: u.mine ? t.cardHi : t.primaryGlow2, color: u.mine ? t.textMuted : t.primary }}>
                                {u.tag === "msg" ? (u.mine ? "You" : initialsOf(u.who)) : u.tag === "doc" ? "DOC" : u.tag === "fee" ? "FEE" : "✓"}
                            </span>
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontSize: 13.5, color: t.text }}><b>{u.who}</b> <span style={{ color: t.textMuted }}>{u.what} · {u.time}</span></div>
                                {u.body && <div style={{ marginTop: 4, padding: "9px 12px", borderRadius: 12, background: t.cardHi, fontSize: 13.5, color: t.text, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{u.body}</div>}
                            </div>
                        </div>
                    ))}
                </div>
            ))}
            {total > LIMIT && (
                <button type="button" onClick={() => setShowAll(v => !v)} style={{ alignSelf: "flex-start", margin: "2px 0 8px 44px", padding: 0, border: 0, background: "none", cursor: "pointer", fontSize: 13, fontWeight: 700, color: t.textMuted }}>
                    {showAll ? "Show fewer" : `Show ${total - LIMIT} older update${total - LIMIT === 1 ? "" : "s"}`}
                </button>
            )}
            {canReply ? (
                <form onSubmit={e => { e.preventDefault(); send(); }} style={{ display: "flex", gap: 8, alignItems: "center", paddingTop: 12, marginTop: 6, borderTop: `1px solid ${t.border}` }}>
                    <label htmlFor="case-reply" style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }}>Write to your lawyer</label>
                    <input id="case-reply" data-case-reply value={text} onChange={e => { setText(e.target.value); setSendError(null); }} disabled={sending}
                        placeholder={`Write to ${lawyerName ? String(lawyerName).replace(/^(adv\.?|advocate)\s+/i, "").split(" ")[0] : "your lawyer"}…`}
                        style={{ flex: 1, height: 42, boxSizing: "border-box", padding: "0 16px", borderRadius: 999, border: `1px solid ${t.border}`, background: t.inputBg, color: t.text, fontSize: 14, outline: "none" }} />
                    <button type="submit" data-case-send disabled={sending || !text.trim()}
                        style={{ height: 42, padding: "0 20px", borderRadius: 999, border: 0, cursor: sending || !text.trim() ? "default" : "pointer", opacity: sending || !text.trim() ? .6 : 1,
                            background: "var(--brand-solid, linear-gradient(135deg,#3EE0A1,#2EC4D6))", color: "var(--on-brand, #04212A)", fontWeight: 700 }}>{sending ? "Sending…" : "Send"}</button>
                </form>
            ) : (
                <div style={{ paddingTop: 12, marginTop: 6, borderTop: `1px solid ${t.border}`, fontSize: 13, color: t.textMuted }}>You can message here once a lawyer takes your case.</div>
            )}
            {sendError && <div role="alert" style={{ marginTop: 8, fontSize: 12.5, color: t.danger }}>{sendError}</div>}
        </section>
    );
}

function CaseDetails({ t, groups, onTab }) {
    return (
        <aside aria-label="Case details" data-case-details style={{ borderRadius: 18, background: t.card, border: `1px solid ${t.border}`, padding: "4px 20px" }}>
            {groups.map((g, i) => (
                <section key={g.key} data-details={g.key} style={{ padding: "14px 0", borderBottom: i === groups.length - 1 ? 0 : `1px solid ${t.border}` }}>
                    <div style={{ display: "flex", alignItems: "baseline", marginBottom: 8 }}>
                        <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase", color: t.textMuted }}>{g.title}</div>
                        <button type="button" onClick={() => onTab(g.tab)} style={{ marginLeft: "auto", background: "none", border: 0, padding: 0, cursor: "pointer", fontSize: 12.5, fontWeight: 700, color: t.primary }}>{g.link}</button>
                    </div>
                    {g.error ? <CheckFailed t={t} what="" onRetry={g.onRetry}>{g.error}</CheckFailed>
                        : g.loading ? <div style={{ fontSize: 13, color: t.textMuted }}>Loading…</div>
                        : g.rows.length === 0 ? <div style={{ fontSize: 13, color: t.textMuted }}>Nothing recorded yet.</div> : null}
                    {!g.error && !g.loading && g.rows.map(r => (
                        <div key={r.k} style={{ display: "flex", justifyContent: "space-between", gap: 12, padding: "3px 0", fontSize: 13.5 }}>
                            <span style={{ color: t.textMuted }}>{r.k}</span>
                            <b style={{ textAlign: "right", color: r.warn ? t.warn : t.text, overflowWrap: "anywhere" }}>{r.v}</b>
                        </div>
                    ))}
                </section>
            ))}
        </aside>
    );
}

// ─── MY MATTERS (Tracking v2, 2026-11-23) ─────────────────────────────────────
// Every case the client has, each saying where it stands in one sentence (the
// same sentence as its status card), its steps, its lawyer, and what is
// waiting on the client. Replaces the case dropdown that named cases by their
// database id, and the silent "open the newest case" on /tracking.
const MATTER_CLOSED = new Set(["closed", "dismissed", "completed", "withdrawn"]);

/* My matters text colours, option A (canvas board InkA, 2026-11-25): only the
 * headline is full white; the title, details and stage step down in calm greys,
 * and the side label takes the brand tint. Theme variables, so Light works. */
const INK = {
    title: "color-mix(in srgb, var(--ink, #F1F5F6) 82%, var(--muted, #BFCACC))",
    meta: "var(--faint, #93A4A8)",
    stage: "var(--muted, #BFCACC)",
    label: "var(--brand-text, #5EE6B0)",
};

/* An outlined button that sits ON a brand-tinted panel (My matters' side
 * panel, the case card's lawyer panel). Transparent, it took the panel's own
 * tint and vanished into it (2026-11-25): it gets the deeper surface behind
 * it, so it reads as a button in Light and Dark alike. */
const ON_TINT = {
    background: "var(--surface-2, #0F2429)",
    border: "1px solid color-mix(in srgb, var(--teal-ink, #6ADDEB) 55%, transparent)",
    color: "var(--teal-ink, #6ADDEB)",
};
/* Colour roles (2026-11-25, canvas board TealMatters): mint gradient = the one
 * main action; teal outline (ON_TINT) = open / go somewhere / a second action;
 * gold = waiting on you; red = decline / remove. */
const TEAL_INK = "var(--teal-ink, #6ADDEB)";
/* Teal filled (My matters' Open case, 2026-11-25) and the soft "tonal" fills
 * for a row's main action (canvas DocButtons option 1). */
// Option 6 of the gradient board (user's pick, 2026-11-25): cyan with a soft
// top shine. Dark text on it reads in Dark and Light alike.
const TEAL_SOLID = { background: "linear-gradient(180deg, #8AE7F2 0%, #5BCFE2 55%, #3FBFD6 100%)", border: 0, color: "#04212A",
    boxShadow: "0 8px 18px -12px rgba(0,0,0,.7)" };
const TEAL_TONAL = { background: "color-mix(in srgb, var(--teal-ink, #6ADDEB) 16%, transparent)", border: 0, color: TEAL_INK };
const MINT_TONAL = { background: "color-mix(in srgb, var(--brand-text, #5EE6B0) 16%, transparent)", border: 0, color: "var(--brand-text, #5EE6B0)" };
/* No transparent buttons in the matter flow (user, 2026-11-25): on the dark
 * theme a border-only button has the page's own colour and does not read as a
 * button. Anything that is not the main action or a teal one is NEUTRAL: a
 * light fill of the text colour over the card, visible in Dark and Light. */
const NEUTRAL_FILL = { background: "color-mix(in srgb, var(--ink, #F1F5F6) 11%, var(--surface, #183840))",
    border: "1px solid color-mix(in srgb, var(--ink, #F1F5F6) 16%, transparent)", color: "var(--ink, #F1F5F6)" };
const SR_ONLY = { position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)", whiteSpace: "nowrap" };

function MyMatters({ t, cases, drafts = [], casesState, onRetry, onOpen, onOpenAppointment, onAllPayments = null }) {
    const engagements = useEngagements();
    const [showClosed, setShowClosed] = useState(false);
    const payments = useSource(() => Promise.resolve(listPayments()).then(listOf), []);
    const proposals = useSource(() => Promise.resolve(listMeetingProposals({ status: "open", all: true })).then(listOf), []);
    // The client's actionable documents across cases, so one sent back or
    // needing approval again counts on its case too (review item 6, 2026-11-23).
    const docs = useSource(() => readAllV2Documents(null, { needsAction: true }), []);
    const agreements = useSource(() => readPendingAgreements(), []);
    const appointments = useSource(() => readAllAppointments(), []);
    useEffect(() => onNotification(n => {
        const type = String(n?.type || "");
        if (type.startsWith("payment_")) payments.reload();
        if (type.startsWith("appointment_propos")) proposals.reload();
        if (type.startsWith("document_") || type.startsWith("review_request_")) docs.reload();
        if (type.startsWith("agreement_")) agreements.reload();
        if (type.startsWith("appointment_")) appointments.reload();
    }), [payments.reload, proposals.reload, docs.reload, agreements.reload, appointments.reload]);
    const myId = useMyId();
    const sources = { "hire requests": engagements, fees: payments, "meeting times": proposals, appointments, documents: docs,
        ...(myId ? { agreements } : {}) };
    const failed = Object.keys(sources).filter(k => sources[k].state === "error");
    const checking = Object.keys(sources).some(k => sources[k].state === "loading");
    const rows = cases.map(c => {
        const engagement = pickEngagement(engagements.data, c.id);
        const feeText = engagement ? feeLabel(engagement) : "";
        const hero = caseHero({ caseInfo: c, nextHearing: c.nextHearingRaw || null, engagement, feeText, engagementState: engagements.state });
        const todos = caseTodos({ caseId: c.id, engagement, feeText, payments: payments.data, proposals: proposals.data,
            appointments: appointments.data,
            docs: (docs.data || []).filter(d => String(d.case_id || "") === String(c.id)), agreements: agreements.data, userId: myId });
        return { c, engagement, hero, todos };
    });
    // What waits on the client comes first; otherwise the server's order (newest).
    // Closed matters fold away under "Closed matters (n)" (2026-11-25, as the preview).
    const isClosed = r => MATTER_CLOSED.has(String(r.c.status || ""));
    const live = rows.filter(r => !isClosed(r));
    const closedRows = rows.filter(isClosed);
    const ordered = [...live.filter(r => r.todos.length), ...live.filter(r => !r.todos.length)];
    // Initial consultations may intentionally have no case. They still need a
    // visible home here or the cross-matter summary can claim there is nothing
    // waiting while Appointments is asking the client to choose a time.
    const otherActions = appointmentTodos({ appointments: appointments.data, caseId: null });
    const waiting = rows.reduce((n, r) => n + r.todos.length, 0) + otherActions.length;
    const solid = { display: "inline-flex", alignItems: "center", justifyContent: "center", height: 38, padding: "0 18px", borderRadius: 999, border: 0, cursor: "pointer",
        fontWeight: 700, fontSize: 13.5, background: "var(--brand-solid, linear-gradient(135deg,#3EE0A1,#2EC4D6))", color: "var(--on-brand, #04212A)", textDecoration: "none" };
    const outline = { ...solid, ...TEAL_TONAL };
    return (
        <div data-my-matters>
            <header style={{ display: "flex", alignItems: "flex-end", gap: 16, flexWrap: "wrap", marginBottom: 20 }}>
                <div style={{ flex: "1 1 360px" }}>
                    <h1 style={{ margin: 0, font: "800 32px/1.15 Nunito, 'Hanken Grotesk', sans-serif", letterSpacing: "-.01em", color: t.text }}>My matters</h1>
                    <div data-matters-summary style={{ marginTop: 4, fontSize: 14.5, color: t.textMuted }}>
                        {casesState !== "ready" || !cases.length ? "Your matters, newest first."
                            : failed.length ? <CheckFailed t={t} what={andList(failed)} onRetry={() => failed.forEach(k => sources[k].reload())} />
                            : waiting && checking ? <><b style={{ color: t.warn }}>{waiting} thing{waiting === 1 ? "" : "s"} found so far</b> · Still checking…</>
                            : waiting ? <><b style={{ color: t.warn }}>{waiting} thing{waiting === 1 ? "" : "s"}</b> {waiting === 1 ? "is" : "are"} waiting on you across your matters.</>
                            : checking ? "Checking what's waiting on you…"
                            : "Nothing is waiting on you right now."}
                    </div>
                </div>
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                    {onAllPayments && <button type="button" data-open-all-payments onClick={onAllPayments} style={{ ...outline, ...ON_TINT }}>All my payments</button>}
                    <a href="/intake" style={solid}>+ Start a new matter</a>
                </div>
            </header>

            {casesState === "loading" && <div style={{ fontSize: 13.5, color: t.textMuted }}>Loading your matters…</div>}
            {casesState === "error" && (
                <div role="alert" data-matters-error style={{ padding: "16px 18px", borderRadius: 16, background: t.card, border: `1px solid ${t.border}`, display: "flex", alignItems: "center", gap: 12 }}>
                    <span style={{ flex: 1, fontSize: 13.5, color: t.text }}>Couldn't load your matters. Check your connection and try again.</span>
                    <button type="button" onClick={onRetry} style={outline}>Try again</button>
                </div>
            )}
            {casesState === "ready" && !cases.length && !drafts.length && (
                <div data-matters-empty style={{ padding: "36px 24px", borderRadius: 18, background: t.card, border: `1px solid ${t.border}`, textAlign: "center" }}>
                    <b style={{ display: "block", fontSize: 17, color: t.text }}>No matters yet</b>
                    <div style={{ fontSize: 13.5, color: t.textMuted, margin: "6px 0 14px" }}>Describe your problem in Legal Intake. Once you confirm it, it opens here as a case.</div>
                    <a href="/intake" style={solid}>Start a new matter</a>
                </div>
            )}

            {otherActions.length > 0 && (
                <section aria-label="Other actions" data-other-actions style={{ marginBottom: 16 }}>
                    <h2 style={{ margin: "0 0 9px", fontSize: 16, fontWeight: 800, color: t.text }}>Other actions</h2>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 12 }}>
                        {otherActions.map(action => (
                            <article key={action.key} data-other-action={action.id} style={{ padding: "15px 17px", borderRadius: 16,
                                background: t.card, border: `1px solid ${t.warn}55`, display: "flex", alignItems: "center", gap: 14 }}>
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <div style={{ fontSize: 11.5, fontWeight: 800, color: t.warn, textTransform: "uppercase", letterSpacing: ".06em" }}>Appointment · Waiting on you</div>
                                    <b style={{ display: "block", marginTop: 3, fontSize: 14.5, color: t.text }}>{action.title}</b>
                                    <span style={{ display: "block", marginTop: 2, fontSize: 12.5, color: t.textMuted }}>{action.sub}</span>
                                </div>
                                <button type="button" onClick={() => onOpenAppointment?.(action.id)} style={solid}>{action.cta}</button>
                            </article>
                        ))}
                    </div>
                </section>
            )}

            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                {[...ordered, ...(showClosed ? closedRows : [])].map(({ c, engagement, hero, todos }, idx) => {
                    const first = todos[0] || null;
                    const lawyer = engagement?.status === "accepted" ? engagement.lawyer_name : null;
                    return (
                        <article key={c.id} data-matter={c.id} data-waiting={todos.length}
                            style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 240px", borderRadius: 20, background: t.card, overflow: "hidden",
                                border: `1px solid ${todos.length ? `${t.warn}55` : t.border}` }}>
                            <div style={{ padding: "18px 22px", display: "flex", flexDirection: "column", gap: 9, minWidth: 0 }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", fontSize: 13, color: INK.meta }}>
                                    <b data-matter-title title={fullMatterTitle(c.title)} style={{ color: INK.title, fontSize: 14, minWidth: 0, maxWidth: "100%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{shortMatterTitle(c.title, 60)}</b>
                                    {c.type && <><span aria-hidden="true">·</span><span>{c.type.charAt(0).toUpperCase() + c.type.slice(1)}</span></>}
                                    {c.caseNumber && <><span aria-hidden="true">·</span><span data-matter-number style={{ color: TEAL_INK }}>{c.caseNumber}</span></>}
                                </div>
                                <h2 data-matter-headline style={{ margin: 0, font: "800 22px/1.2 Nunito, 'Hanken Grotesk', sans-serif", color: hero.tone === "muted" ? t.textMuted : t.text }}>{hero.headline}</h2>
                                <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap", fontSize: 12.5, color: INK.stage }}>
                                    {(() => {
                                        // Every card reads the same way: the case's five-stage
                                        // journey from real facts (2026-11-25). A lawyer's
                                        // milestones ("1 of 1 steps done") counted something
                                        // else on some cards only; they stay on the Timeline.
                                        const j = journeyStages({ caseInfo: c, engagement, nextHearing: c.nextHearingRaw ? { date: c.nextHearingRaw } : null, hadHearing: !!c.nextHearingRaw });
                                        const now = j.findIndex(st => st.state === "now");
                                        return (<>
                                            <span aria-hidden="true" data-matter-journey style={{ display: "grid", gridTemplateColumns: `repeat(${j.length}, minmax(0, 1fr))`, gap: 4, width: 280 }}>
                                                {j.map((st, i) => (
                                                    <span key={i} data-seg={st.state} style={{ height: 6, borderRadius: 3, background: st.state === "now" ? TEAL_INK : st.state === "done" ? t.primary : t.border }} />
                                                ))}
                                            </span>
                                            <span data-matter-stage>{now === -1 ? `All ${j.length} stages done` : `Stage ${now + 1} of ${j.length} · ${j[now].title}`}</span>
                                        </>);
                                    })()}
                                    <span data-matter-lawyer style={{ marginLeft: "auto", color: lawyer || c.lawyerAssigned ? INK.title : INK.meta }}>{lawyer || (c.lawyerAssigned ? "Lawyer assigned" : "No lawyer yet")}</span>
                                </div>
                            </div>
                            {/* The same theme tint as the case page's status panel
                                (decided 2026-11-23: cardHi clashed across themes). */}
                            <div data-matter-side style={{ padding: 18, borderLeft: `1px solid ${t.border}`, background: "var(--brand-soft, rgba(62,224,161,.13))", display: "flex", flexDirection: "column", justifyContent: "center", gap: 8 }}>
                                <div data-matter-side-label style={{ fontSize: 11.5, fontWeight: 800, letterSpacing: ".08em", textTransform: "uppercase", color: first ? t.warn : failed.length ? INK.meta : INK.label }}>
                                    {first ? `Waiting on you${todos.length > 1 ? ` · ${todos.length}` : ""}`
                                        : failed.length ? "Couldn't check" : checking ? "Checking…" : "Nothing waiting on you"}
                                </div>
                                {first && <b style={{ fontSize: 14.5, color: t.text, lineHeight: 1.3 }}>{first.title}</b>}
                                {first && (first.sub || first.chip) && (
                                    <span data-matter-next-sub style={{ fontSize: 12.5, color: t.textMuted, lineHeight: 1.35, marginTop: -4 }}>
                                        {[first.sub, first.chip && first.chip !== "Waiting on you" ? first.chip : null].filter(Boolean).join(" · ")}
                                    </span>
                                )}
                                <button type="button" data-open-matter={c.id}
                                    onClick={() => (first?.action === "engagement" ? onOpen(c.id, { engagement: first.id }) : onOpen(c.id))}
                                    /* ONE solid button on the page (as the preview): the top
                                       card, and only when something waits on it. The rest
                                       are outlined, so the eye lands on the most urgent. */
                                    style={first && idx === 0 ? solid : { ...outline, ...TEAL_SOLID }}>{first?.action === "engagement" ? first.cta : "Open case"}</button>
                            </div>
                        </article>
                    );
                })}
            </div>
            {casesState === "ready" && drafts.length > 0 && (
                <div style={{ display: "flex", flexDirection: "column", gap: 14, marginTop: 14 }}>
                    {drafts.map(d => (
                        <article key={d.id} data-draft-matter={d.id}
                            style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 240px", borderRadius: 20, background: t.card, overflow: "hidden", border: `1px solid ${t.border}` }}>
                            <div style={{ padding: "18px 22px", display: "flex", flexDirection: "column", gap: 9, minWidth: 0 }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", fontSize: 13, color: t.textMuted }}>
                                    <b title={fullMatterTitle(d.title)} style={{ color: t.text, fontSize: 14, minWidth: 0, maxWidth: "100%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{shortMatterTitle(d.title, 60)}</b>
                                    <span aria-hidden="true">·</span><span>{[d.type && d.type.charAt(0).toUpperCase() + d.type.slice(1), "draft"].filter(Boolean).join(" · ")}</span>
                                </div>
                                <h2 style={{ margin: 0, font: "800 22px/1.2 Nunito, 'Hanken Grotesk', sans-serif", color: t.textMuted }}>Not submitted yet</h2>
                                <div style={{ display: "flex", alignItems: "center", gap: 14, fontSize: 12.5, color: t.textMuted }}>
                                    <span aria-hidden="true" style={{ display: "grid", gridTemplateColumns: "repeat(5, minmax(0, 1fr))", gap: 4, width: 280 }}>
                                        {[0, 1, 2, 3, 4].map(i => <span key={i} style={{ height: 6, borderRadius: 3, background: t.border }} />)}
                                    </span>
                                    <span>Confirm it in Legal Intake to open it as a case</span>
                                </div>
                            </div>
                            <div data-matter-side style={{ padding: 18, borderLeft: `1px solid ${t.border}`, background: "var(--brand-soft, rgba(62,224,161,.13))", display: "flex", flexDirection: "column", justifyContent: "center", gap: 8 }}>
                                <div style={{ fontSize: 11.5, fontWeight: 800, letterSpacing: ".08em", textTransform: "uppercase", color: t.textMuted }}>Next step</div>
                                <b style={{ fontSize: 14.5, color: t.text, lineHeight: 1.3 }}>Finish describing your problem</b>
                                <a href="/intake" data-continue-intake style={{ ...outline, ...ON_TINT }}>Continue intake</a>
                            </div>
                        </article>
                    ))}
                </div>
            )}
            {casesState === "ready" && (cases.length > 0 || drafts.length > 0) && (
                <button type="button" data-closed-matters aria-expanded={showClosed} disabled={!closedRows.length}
                    onClick={() => setShowClosed(v => !v)}
                    style={{ marginTop: 16, border: 0, background: "none", padding: 0, cursor: closedRows.length ? "pointer" : "default",
                        fontSize: 13.5, fontWeight: 700, color: t.textMuted, fontFamily: "inherit", opacity: closedRows.length ? 1 : 0.7 }}>
                    {showClosed ? "Hide closed matters" : `${closedRows.length ? "\u25B8 " : ""}Closed matters (${closedRows.length})`}
                </button>
            )}
        </div>
    );
}

// ─── PAGE: OVERVIEW ───────────────────────────────────────────────────────────
const _fmtHearingDate = (d) => d ? new Date(d).toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" }) : "—";

// WhatsApp-shareable peshi card: the family group chat is where hearing news
// actually travels — build the update as plain text and hand it to wa.me.
const _fmtShareDate = (d, urdu) => d
    ? new Date(d).toLocaleDateString(urdu ? "ur-PK" : "en-PK", { day: "numeric", month: "long", year: "numeric" })
    : "";

function _buildPeshiMessage(h, { caseTitle, court, nextUp, urdu }) {
    const meaning = urdu ? (h.outcome_meaning_ur || h.outcome_meaning || "") : (h.outcome_meaning || "");
    const lines = urdu
        ? [
            "⚖️ پیشی کی تازہ کاری",
            "",
            caseTitle ? `مقدمہ: ${caseTitle}` : null,
            court ? `عدالت: ${court}` : null,
            `تاریخِ پیشی: ${_fmtShareDate(h.date, true)}`,
            h.outcome_label || h.outcome ? `نتیجہ: ${h.outcome_label || h.outcome}` : null,
            "",
            meaning || null,
            h.outcome_note ? `\n💬 وکیل کا نوٹ: ${h.outcome_note}` : null,
            nextUp ? `\n📅 اگلی پیشی: ${_fmtShareDate(nextUp.date, true)}${nextUp.time ? ` · ${nextUp.time}` : ""}` : null,
            "",
            "— Attorney.AI کے ذریعے بھیجا گیا",
        ]
        : [
            "⚖️ Hearing Update (Peshi)",
            "",
            caseTitle ? `Case: ${caseTitle}` : null,
            court ? `Court: ${court}` : null,
            `Hearing date: ${_fmtShareDate(h.date, false)}`,
            h.outcome_label || h.outcome ? `Outcome: ${h.outcome_label || h.outcome}` : null,
            "",
            meaning || null,
            h.outcome_note ? `\n💬 Lawyer's note: ${h.outcome_note}` : null,
            nextUp ? `\n📅 Next hearing: ${_fmtShareDate(nextUp.date, false)}${nextUp.time ? ` · ${nextUp.time}` : ""}` : null,
            "",
            "— Sent via Attorney.AI",
        ];
    return lines.filter(l => l !== null).join("\n");
}

function _shareOnWhatsApp(text) {
    window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, "_blank", "noopener,noreferrer");
}

// Peshi tracker — what the lawyer recorded, in the client's language
function HearingUpdates({ hearings, caseTitle, court }) {
    const t = useT();
    const [showUrdu, setShowUrdu] = useState(false);
    const recorded = (hearings || []).filter(h => h.outcome).sort((a, b) => new Date(b.date) - new Date(a.date));
    const nextUp = (hearings || []).filter(h => !h.outcome).sort((a, b) => new Date(a.date) - new Date(b.date))[0];

    if (!hearings?.length) return null;

    return (
        <Card t={t} style={{ marginBottom: 16 }}>
            <SH title="Hearing Updates" desc="What happened at each court date — explained simply" t={t}
                badge={
                    <button onClick={(e) => { e.stopPropagation(); setShowUrdu(u => !u); }} style={{
                        padding: "4px 12px", borderRadius: 8, fontSize: 11, fontWeight: 700, cursor: "pointer",
                        border: `1px solid ${t.border}`, background: showUrdu ? t.primaryGlow2 : "transparent", color: showUrdu ? t.primary : t.textMuted,
                    }}>{showUrdu ? "اردو ✓" : "اردو"}</button>
                } />
            <div style={{ padding: 16 }}>
                {nextUp && (
                    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", borderRadius: 10, background: t.primaryGlow2, border: `1px solid ${t.primary}40`, marginBottom: 12 }}>
                        <span aria-hidden="true" style={{ display: "flex", color: t.primary }}>
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 10h18" /></svg>
                        </span>
                        <div>
                            <div style={{ fontSize: 12.5, fontWeight: 700, color: t.primary }}>Next hearing: {_fmtHearingDate(nextUp.date)}{nextUp.time ? ` · ${nextUp.time}` : ""}</div>
                            <div style={{ fontSize: 11, color: t.textMuted }}>{[nextUp.purpose, nextUp.court].filter(Boolean).join(" — ")}</div>
                        </div>
                    </div>
                )}
                {recorded.length === 0 ? (
                    <div style={{ fontSize: 12, color: t.textMuted, padding: "6px 2px" }}>No hearing outcomes recorded yet — updates from your lawyer will appear here after each court date.</div>
                ) : recorded.slice(0, 4).map((h, i) => (
                    <div key={h._id || i} style={{ padding: "10px 2px", borderTop: i > 0 ? `1px solid ${t.border}` : "none" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
                            <span style={{ fontSize: 12, fontWeight: 700, color: t.text }}>{_fmtHearingDate(h.date)}</span>
                            <Badge variant={h.outcome === "decided" ? "success" : h.outcome === "adjourned" || h.outcome === "judge_on_leave" ? "warn" : "info"} t={t} sm>
                                {h.outcome_label || h.outcome}
                            </Badge>
                            <button
                                onClick={(e) => { e.stopPropagation(); _shareOnWhatsApp(_buildPeshiMessage(h, { caseTitle, court, nextUp, urdu: showUrdu })); }}
                                title={showUrdu ? "واٹس ایپ پر شیئر کریں" : "Share update on WhatsApp"}
                                style={{
                                    marginLeft: "auto", display: "flex", alignItems: "center", gap: 5,
                                    padding: "3px 10px", borderRadius: 8, cursor: "pointer",
                                    border: "1px solid #25D36650", background: "#25D36615",
                                    color: "#25D366", fontSize: 10.5, fontWeight: 700,
                                    fontFamily: "inherit", transition: "all .15s", flexShrink: 0,
                                }}
                                onMouseEnter={e => { e.currentTarget.style.background = "#25D36630"; e.currentTarget.style.borderColor = "#25D366"; }}
                                onMouseLeave={e => { e.currentTarget.style.background = "#25D36615"; e.currentTarget.style.borderColor = "#25D36650"; }}
                            >
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.297-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z" /></svg>
                                {showUrdu ? "شیئر" : "Share"}
                            </button>
                        </div>
                        <div style={{ fontSize: 12, color: t.textDim, lineHeight: 1.6, direction: showUrdu ? "rtl" : "ltr", textAlign: showUrdu ? "right" : "left" }}>
                            {showUrdu ? (h.outcome_meaning_ur || h.outcome_meaning || "") : (h.outcome_meaning || "")}
                        </div>
                        {h.outcome_note && (
                            <div style={{ display: "flex", alignItems: "flex-start", gap: 6, fontSize: 12.5, color: t.textMuted, marginTop: 4 }}>
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ flexShrink: 0, marginTop: 2 }}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>
                                <span>Lawyer&rsquo;s note: {h.outcome_note}</span>
                            </div>
                        )}
                    </div>
                ))}
            </div>
        </Card>
    );
}

function PageOverview({ setPage, activeCase, hearings, steps = [], onHeroAction = null, afterHero = null, casesState = "ready", onRetryCases = null }) {
    const t = useT();
    const { T } = useLang();
    const engagements = useEngagements(activeCase?.id || null);
    const data = useCaseOverviewData(activeCase?.id || null);
    const myId = useMyId();
    const overviewEngagement = activeCase ? pickEngagement(engagements.data, activeCase.id) : null;

    // Every field below reads off activeCase. Before the mock CASES array was
    // removed this was never undefined; on a real account with no cases it is,
    // and dereferencing it threw.
    if (!activeCase) {
        // A failed or unfinished read is not "you have no cases" (2026-10-19):
        // it said so on any network hiccup, and a client believed their case
        // had gone.
        if (casesState === "loading") return <Card t={t}><div style={{ padding: 24, color: t.textMuted, fontSize: 13.5 }}>Loading your cases…</div></Card>;
        if (casesState === "error") return (
            <Card t={t}>
                <div role="alert" data-cases-error style={{ padding: 24, display: "flex", flexDirection: "column", alignItems: "center", gap: 10, textAlign: "center" }}>
                    <b style={{ color: t.text }}>Could not load your cases</b>
                    <span style={{ fontSize: 13, color: t.textMuted }}>Check your connection and try again.</span>
                    {onRetryCases && <button type="button" onClick={onRetryCases} style={{ ...hubBtn("ghost", t), height: 36 }}>Try again</button>}
                </div>
            </Card>
        );
        return (
            <Card t={t}>
                <Empty t={t} icon="🗂" title="No cases yet"
                    desc="Complete an intake and convert it to a case. Its timeline, documents, hearings and messages all appear here once it exists." />
            </Card>
        );
    }

    return (
        <div>
            <CaseStatusHero t={t} activeCase={activeCase} hearings={hearings} steps={steps} engagements={engagements.data} engagementState={engagements.state}
                onAction={(a, e) => (a === "retry-engagements" ? engagements.reload() : (onHeroAction || (() => {}))(a, e))} />
            <CaseTodos t={t} caseId={activeCase.id} onAction={onHeroAction || (() => {})}
                userId={myId}
                sources={{ "hire requests": engagements, fees: data.payments, "meeting times": data.proposals,
                    appointments: data.appointments, documents: data.v2Docs,
                    // Whose signature is missing needs the client's id: checked only when it is known.
                    ...(myId ? { agreements: data.agreements } : {}) }} />
            {afterHero}

            <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 320px", gap: 18, alignItems: "start" }}>
                <CaseUpdates t={t} caseId={activeCase.id} messagesState={data.messages.state}
                    missing={[data.messages.state === "error" && "messages", data.payments.state === "error" && "fees", data.docsState === "error" && "documents"].filter(Boolean)}
                    loadingAny={[data.payments.state, data.docsState].includes("loading")}
                    onRetry={() => { if (data.messages.state === "error") data.messages.reload(); if (data.payments.state === "error") data.payments.reload(); if (data.docsState === "error") data.reloadDocs(); }}
                    groups={groupByDay(caseUpdates({ messages: data.messages.data, docs: data.docRows, steps, payments: data.casePayments, lawyerName: overviewEngagement?.lawyer_name || null }))}
                    canReply={!["closed", "dismissed"].includes(activeCase.status) && (overviewEngagement?.status === "accepted" || activeCase.lawyerAssigned)}
                    lawyerName={overviewEngagement?.status === "accepted" ? overviewEngagement.lawyer_name : null}
                    onSent={() => data.messages.reload()} onOpenMessages={() => setPage("communication")} />
                <CaseDetails t={t} onTab={setPage}
                    groups={caseDetails({ caseInfo: activeCase, engagement: overviewEngagement, feeText: overviewEngagement ? feeLabel(overviewEngagement) : "", payments: data.casePayments, docs: data.docRows })
                        .map(g => g.key === "money" ? { ...g, loading: data.payments.state === "loading", error: data.payments.state === "error" ? "Couldn't load the fees on this case." : null, onRetry: data.payments.reload }
                            : g.key === "files" ? { ...g, loading: data.docsState === "loading", error: data.docsState === "error" ? "Couldn't load this case's documents." : null, onRetry: data.reloadDocs }
                            : g)} />
            </div>
        </div>
    );
}

// ─── PAGE: TIMELINE ───────────────────────────────────────────────────────────
// Accepts the milestones prop: the case timeline from the API plus any
// appointment milestones written by ModLawyers via CaseContext.
function PageTimeline({ milestones: propMilestones, hearings = [], loadState = "ready", onRetry = null, activeCase = null }) {
    const t = useT();
    const milestoneRows = propMilestones || [];
    const hearingRows = hearings.map(mapApiHearing);
    const allMilestones = [...milestoneRows, ...hearingRows];
    // Real counts, from the milestones the lawyer marks (no invented "/5").
    const doneCount = milestoneRows.filter(m => m.status === "done").length;
    const pendingCount = milestoneRows.length - doneCount;
    const outcomes = hearings.filter(h => h.outcome).sort((x, y) => new Date(y.date) - new Date(x.date));
    const [tab, setTab] = useState("all");
    // "Add Note / Tag Lawyer" was removed (2026-11-23): the note lived only in
    // this browser and the lawyer was never told. Questions go to Messages.
    const activeRef = useRef(null);

    useEffect(() => {
        setTimeout(() => activeRef.current?.scrollIntoView({ behavior: "smooth", block: "center" }), 200);
    }, [tab]);

    const list = tab === "hearings" ? allMilestones.filter(m => m.tag === "hearing" || m.tag === "appointment")
        : tab === "done" ? allMilestones.filter(m => m.status === "done")
            : allMilestones;
    const tagStyle = { complete: { v: "success", l: "Complete" }, hearing: { v: "warn", l: "Hearing" }, pending: { v: "gray", l: "Pending" } };

    // A read still in flight, or one that failed, is not "no hearings".
    if (loadState === "loading") {
        return <Card t={t}><div data-timeline-state="loading" style={{ padding: 24, fontSize: 13.5, color: t.textMuted }}>Loading the timeline…</div></Card>;
    }
    if (loadState === "error") {
        return (
            <Card t={t}>
                <div role="alert" data-timeline-state="error" style={{ padding: 24, display: "flex", flexDirection: "column", alignItems: "center", gap: 10, textAlign: "center" }}>
                    <b style={{ color: t.text }}>Couldn't load this case's timeline</b>
                    <span style={{ fontSize: 14, color: t.textMuted }}>Hearings and milestones may be missing from this view. Check your connection and try again.</span>
                    {onRetry && <button type="button" onClick={onRetry} style={{ ...hubBtn("ghost", t), height: 36 }}>Try again</button>}
                </div>
            </Card>
        );
    }

    return (
        <div>
            {/* Share a hearing on WhatsApp (moved here from the Overview, 2026-11-23). */}
            <HearingUpdates hearings={hearings} caseTitle={activeCase?.title} court={activeCase?.court} />
            <div className="rgrid" style={{ display: "grid", gridTemplateColumns: "1fr 288px", gap: 16 }}>
                <Card t={t}>
                    <SH icon="🕐" title="Case Timeline" desc="Milestones, hearings & court instructions"
                        badge={<Badge variant="success" t={t}>{allMilestones.filter(m => m.status === "done").length}/{allMilestones.length} Done</Badge>} t={t} />
                    <Tabs tabs={[
                        { key: "all", label: "All", count: allMilestones.length },
                        { key: "hearings", label: "Hearings" },
                        { key: "done", label: "Completed" },
                    ]} active={tab} onChange={setTab} t={t} />
                    <div style={{ padding: "20px 24px" }}>
                        {list.length === 0 && (
                            <Empty t={t} icon="🗓"
                                title="No timeline entries for this case yet"
                                desc="Milestones appear here once your lawyer records a filing, hearing or court order against the case." />
                        )}
                        {list.map((m, i) => {
                            const isDone = m.status === "done", isActive = m.status === "active";
                            const tc = tagStyle[m.tag] || tagStyle.pending;
                            return (
                                <div key={m.id} ref={isActive ? activeRef : null}
                                    style={{ display: "flex", gap: 16, paddingBottom: i < list.length - 1 ? 28 : 0, position: "relative" }}>
                                    {i < list.length - 1 && <div style={{ position: "absolute", left: 15, top: 32, width: 2, bottom: 0, background: t.border }} />}
                                    <div style={{
                                        width: 32, height: 32, borderRadius: "50%",
                                        border: `2px solid ${isActive ? t.primary : isDone ? t.success : t.border}`,
                                        background: isActive ? t.primaryGlow2 : isDone ? `${t.success}22` : "transparent",
                                        display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13.5, flexShrink: 0, zIndex: 1,
                                        color: isActive ? t.primary : isDone ? t.success : t.textFaint,
                                        boxShadow: isActive ? `0 0 14px ${t.primaryGlow}` : "none"
                                    }}>
                                        {isDone ? "✓" : isActive ? "▶" : "○"}
                                    </div>
                                    <div style={{ flex: 1, paddingTop: 4 }}>
                                        {isActive && <div style={{ fontSize: 12, fontWeight: 700, color: t.primary, letterSpacing: "0.08em", marginBottom: 4 }}>▶ YOU ARE HERE</div>}
                                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                                            <div style={{ fontSize: 14, fontWeight: 700, color: isActive ? t.text : isDone ? t.textDim : t.textFaint }}>{m.event}</div>
                                            <div style={{ fontSize: 13.5, color: t.textFaint, textAlign: "right", flexShrink: 0, marginLeft: 12 }}>{m.date}<br />{m.time}</div>
                                        </div>
                                        <div style={{ fontSize: 13.5, color: t.textMuted, marginBottom: 6 }}>{m.desc}</div>
                                        <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                                            <Badge variant={tc.v} t={t} sm>{tc.l}</Badge>
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </Card>

                <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                    <Card t={t}>
                        <SH icon="📊" title="Progress" desc="Milestone completion" t={t} />
                        <div style={{ padding: 16 }}>
                            {milestoneRows.length === 0 && <div style={{ fontSize: 13.5, color: t.textMuted, marginBottom: 10 }}>Your lawyer has not added milestones yet.</div>}
                            {milestoneRows.length > 0 && [{ l: "Completed", c: doneCount, col: t.success }, { l: "Pending", c: pendingCount, col: t.textFaint }].map(item => (
                                <div key={item.l} style={{ marginBottom: 14 }}>
                                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
                                        <span style={{ fontSize: 13.5, color: t.textDim, fontWeight: 500 }}>{item.l}</span>
                                        <span style={{ fontSize: 12.5, color: item.col, fontWeight: 700 }}>{item.c}/{milestoneRows.length}</span>
                                    </div>
                                    <div style={{ height: 5, background: t.accent, borderRadius: 3, overflow: "hidden" }}>
                                        <div style={{ height: "100%", width: `${(item.c / milestoneRows.length) * 100}%`, background: item.col, borderRadius: 3 }} />
                                    </div>
                                </div>
                            ))}
                            <div style={{ fontSize: 12.5, color: t.textFaint, marginTop: 4, padding: "8px 10px", background: t.cardHi, borderRadius: 8 }}>
                                % = milestones marked complete by your lawyer
                            </div>
                        </div>
                    </Card>
                    <Card t={t}>
                        <SH icon="📋" title="What the court decided" t={t} />
                        <div style={{ padding: 14 }}>
                            {outcomes.length === 0 && <div style={{ fontSize: 13.5, color: t.textMuted }}>No hearing outcomes recorded yet.</div>}
                            {outcomes.map((h, i) => (
                                <div key={h._id || i} style={{ background: t.cardHi, border: `1px solid ${t.border}`, borderRadius: 10, padding: 12, marginBottom: i < outcomes.length - 1 ? 10 : 0 }}>
                                    <div style={{ fontSize: 13.5, color: t.warn, fontWeight: 700, marginBottom: 4 }}>{formatPkt(h.date, { month: "short", day: "numeric", year: "numeric" })} · {h.outcome_label || h.outcome}</div>
                                    {h.outcome_note && <div style={{ fontSize: 13.5, color: t.textDim, lineHeight: 1.5 }}>{h.outcome_note}</div>}
                                    {h.outcome_meaning && <div style={{ fontSize: 14, color: t.textMuted, lineHeight: 1.5, marginTop: 4 }}>{h.outcome_meaning}</div>}
                                </div>
                            ))}
                        </div>
                    </Card>
                </div>
            </div>
        </div>
    );
}

const DOC_TYPE_LABELS = {
    plaint_civil: "Plaint", written_statement: "Written Statement",
    legal_notice: "Legal Notice", stay_application: "Stay Application",
    settlement_draft: "Settlement Draft", nda: "NDA / Contract",
};

function _mapApiDoc(d) {
    return {
        id: d._id || d.id,
        name: d.title || DOC_TYPE_LABELS[d.template_type] || (d.template_type || "Document"),
        type: "PDF",
        date: d.created_at ? formatPkt(d.created_at, { month: "short", day: "numeric", year: "numeric" }) : "—",
        at: d.created_at ? new Date(d.created_at).getTime() || 0 : 0,
        category: DOC_TYPE_LABELS[d.template_type] || "Document",
        _raw: d,
    };
}

/* A V2 document on this case (2026-10-09). The legacy case listing drops V2
 * rows by design ("V2 rows are listed by the V2 routes"), and nothing here
 * asked the V2 routes, so a client's drafted -- even approved -- documents
 * never appeared on their case. These carry the exact revision and hash, so
 * Open and Download serve the bytes the row names. */
function _mapV2Doc(d) {
    const row = _mapApiDoc(d);
    return {
        ...row, v2: true,
        status: documentStatusView(d).label,
        revisionId: d.revision_id || null,
        pdfSha256: d.pdf_sha256 || null,
        downloadable: d.downloadable !== false,
    };
}

const DOC_SORTS = {
    date: (x, y) => y.at - x.at,
    name: (x, y) => x.name.localeCompare(y.name),
    type: (x, y) => x.category.localeCompare(y.category) || y.at - x.at,
};

// ─── PAGE: DOCUMENTS ──────────────────────────────────────────────────────────
// The case's documents, from the server (redesigned 2026-11-23, approved v2
// preview). What needs the client comes first ("Needs you": a document the
// lawyer sent back, or one the system says must be approved again); then one
// plain list. A row's status sits in its text line as the app's own word, and
// every row has the same two buttons. Search shows only above 5 documents and
// sort from 2: a toolbar over nothing was most of the old screen.
const DOC_TONE = t => ({ ok: t.primary, info: t.info || t.primary, warn: t.warn, danger: t.danger, muted: t.textMuted });

/* "Agreements on this matter" (board 1, 2026-11-25). A SHORTCUT, not a second
 * agreement system: it lists this matter's agreements (the server filters by
 * case_id) and every Open goes to the one Agreements page. No viewer, signing
 * or decline logic lives here.
 *
 * "New agreement" opens the builder FOR this matter (/agreements?case=…,
 * board 2): its lawyer already a required signer. Shown only while the
 * server's builder switch is on (GET /agreements/capabilities). */
export const AGREEMENT_FROM_MATTER = true;

const readCaseAgreements = async (caseId) => {
    const out = [];
    let page = 1, pages = 1;
    do {
        const r = await listAgreements({ page, page_size: 50, case_id: caseId });
        out.push(...itemsOf(r));
        pages = Number.isInteger(r.data?.pages) ? r.data.pages : 1;
        page += 1;
    } while (page <= pages);
    return out;
};

/** How one agreement on the matter reads, in the app's own words. */
export function matterAgreementView(a, myId = null) {
    const parties = Array.isArray(a?.parties) ? a.parties : [];
    const day = iso => (iso ? new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : null);
    if (a?.status === "executed") return { tone: "ok", status: "Signed by everyone", sub: day(a.updated_at) ? `completed ${day(a.updated_at)}` : "" };
    if (a?.status === "cancelled") {
        const d = a.declined;
        if (!d) return { tone: "bad", status: "Cancelled", sub: day(a.updated_at) || "" };
        const mine = myId && d.by_user_id && String(d.by_user_id) === String(myId);
        return { tone: "bad", status: mine ? "You declined it" : `Declined by ${d.by_name || "a party"}`, sub: day(d.at) || "", reason: d.reason || null };
    }
    const waiting = parties.filter(p => p && !p.signed);
    const meWaiting = myId && waiting.some(p => String(p.user_id) === String(myId));
    const total = a?.total_parties ?? parties.length;
    const signed = a?.signed_count ?? parties.filter(p => p?.signed).length;
    if (meWaiting) return { tone: "warn", status: "Waiting for your signature", sub: `${signed} of ${total} signed`, mine: true };
    const names = waiting.map(p => p.full_name || p.email || "an invited signer");
    return { tone: "warn", status: names.length ? `Waiting for ${andList(names)}` : "Waiting for signatures", sub: `${signed} of ${total} signed` };
}

function MatterAgreements({ caseId, focusAgreementId = null }) {
    const t = useT();
    const router = useClientRouter();
    const myId = useMyId();
    const src = useSource(() => (caseId ? readCaseAgreements(caseId) : []), [caseId]);
    const engagements = useEngagements(caseId);
    const builderOn = useAgreementBuilderOn();   // the server's switch
    const { reload } = src;
    // Live: a lawyer signing or declining shows here without a reload.
    useEffect(() => onNotification(n => {
        const type = String(n?.type || "");
        const noticeCase = n?.payload?.case_id;
        if (type.startsWith("agreement_") && (!noticeCase || String(noticeCase) === String(caseId))) reload();
    }), [caseId, reload]);
    // ?agreement=… (e.g. "Back to matter" after sending): bring THAT row into
    // view once the list has it, the way ?document= does for files.
    const focusRows = Array.isArray(src.data) ? src.data : [];
    const focusFound = !!focusAgreementId && focusRows.some(a => String(a.id || a._id) === String(focusAgreementId));
    useEffect(() => {
        if (!focusFound) return;
        const el = [...document.querySelectorAll("[data-matter-agreement]")]
            .find(node => node.getAttribute("data-matter-agreement") === String(focusAgreementId));
        el?.scrollIntoView?.({ behavior: "smooth", block: "center" });
    }, [focusFound, focusAgreementId]);
    if (!caseId) return null;

    const hired = (engagements.data || []).find(e => e && e.status === "accepted" && (!e.case_id || String(e.case_id) === String(caseId)));
    const noLawyer = engagements.state === "ready" && !hired;
    const rows = Array.isArray(src.data) ? src.data : [];
    const toneInk = { ok: t.success, warn: t.warn, bad: t.danger };
    const pill = { display: "inline-flex", alignItems: "center", justifyContent: "center", width: 104, height: 36, borderRadius: 999,
        cursor: "pointer", fontSize: 13, fontWeight: 700, fontFamily: "inherit", ...TEAL_TONAL };
    const open = id => router.push(`/agreements?agreement=${encodeURIComponent(id)}`);

    // Rows inside the card: a line between them, none above the first.
    const line = first => (first ? 0 : `1px solid ${t.border}`);
    const hasNote = (src.state === "loading" && !rows.length) || src.state === "error"
        || (src.state === "ready" && !rows.length) || (src.state === "ready" && focusAgreementId && !focusFound);
    return (
        <section aria-label="Agreements on this matter" data-matter-agreements={src.state} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, minHeight: 38 }}>
                <h2 style={{ margin: 0, fontSize: 12.5, fontWeight: 800, letterSpacing: ".08em", textTransform: "uppercase", color: t.textMuted }}>
                    Agreements{src.state === "ready" ? ` \u00b7 ${rows.length}` : ""}</h2>
                {hired?.lawyer_name && <span style={{ marginLeft: "auto", fontSize: 13, color: t.textMuted }}>With {hired.lawyer_name}, your lawyer on this matter</span>}
                {AGREEMENT_FROM_MATTER && builderOn === true && hired && (
                    <button type="button" data-new-matter-agreement onClick={() => router.push(`/agreements?case=${encodeURIComponent(caseId)}`)}
                        style={{ ...pill, ...MINT_TONAL, width: "auto", padding: "0 16px", marginLeft: hired?.lawyer_name ? 0 : "auto" }}>
                        + New agreement</button>
                )}
            </div>
            <div style={{ borderRadius: 18, background: t.card, border: `1px solid ${t.border}`, overflow: "hidden" }}>
            {src.state === "loading" && !rows.length && (
                <div style={{ padding: "14px 20px", fontSize: 13.5, color: t.textMuted }}>Checking agreements…</div>
            )}
            {src.state === "error" && (
                <div role="alert" data-matter-agreements-error style={{ display: "flex", alignItems: "center", gap: 12, padding: "14px 20px", fontSize: 13.5, color: t.text }}>
                    <span style={{ flex: 1 }}>Couldn&rsquo;t check this matter&rsquo;s agreements{rows.length ? " — this list may be out of date" : ""}.</span>
                    <button type="button" onClick={reload} style={pill}>Try again</button>
                </div>
            )}
            {src.state === "ready" && !rows.length && (
                <div data-matter-agreements-empty style={{ display: "flex", alignItems: "center", gap: 14, padding: "16px 20px", fontSize: 14, color: t.textMuted }}>
                    <span aria-hidden="true" style={{ width: 40, height: 40, flexShrink: 0, borderRadius: 12, display: "grid", placeItems: "center",
                        background: "var(--brand-soft, rgba(62,224,161,.13))", color: t.primary }}>
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M4 20h4L19 9l-4-4L4 16z" /><path d="M13 7l4 4" /></svg>
                    </span>
                    <span>
                    {noLawyer
                        ? <>Agreements on a matter need a lawyer on it. <button type="button" onClick={() => router.push("/lawyers")}
                            style={{ border: 0, background: "none", padding: 0, cursor: "pointer", color: t.primary, fontWeight: 700, fontSize: 13.5, fontFamily: "inherit" }}>Find a lawyer →</button></>
                        : `No agreements on this matter yet.${hired?.lawyer_name ? ` An agreement you send ${hired.lawyer_name} to sign shows here.` : ""}`}</span>
                </div>
            )}
            {src.state === "ready" && focusAgreementId && !focusFound && (
                <div role="status" data-matter-agreement-missing style={{ padding: "12px 20px", fontSize: 13.5, color: t.text, background: `${t.warn}14` }}>
                    The agreement this link points to is not on this matter.
                </div>
            )}
            {rows.map((a, i) => {
                const id = a.id || a._id;
                const v = matterAgreementView(a, myId);
                const focused = !!focusAgreementId && String(id) === String(focusAgreementId);
                return (
                    <article key={id} data-matter-agreement={id} data-focused={focused ? "" : undefined}
                        style={{ display: "flex", alignItems: "center", gap: 14, padding: "14px 20px", borderTop: line(i === 0 && !hasNote),
                            background: focused ? "var(--brand-soft, rgba(62,224,161,.10))" : "transparent",
                            boxShadow: focused ? `inset 3px 0 0 ${t.primary}` : "none" }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                            <b style={{ display: "block", fontSize: 15, color: t.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.title || "Agreement"}</b>
                            <span style={{ display: "inline-flex", alignItems: "center", gap: 8, flexWrap: "wrap", fontSize: 13, color: t.textMuted }}>
                                <span data-agreement-status style={{ display: "inline-flex", alignItems: "center", gap: 6, fontWeight: 700, color: toneInk[v.tone] || t.textMuted }}>
                                    <span aria-hidden="true" style={{ width: 7, height: 7, borderRadius: "50%", background: "currentColor" }} />{v.status}</span>
                                {v.sub && <><span aria-hidden="true">·</span><span>{v.sub}</span></>}
                            </span>
                            {v.reason && <span data-agreement-reason style={{ display: "block", marginTop: 4, fontSize: 13, color: t.text, whiteSpace: "pre-wrap" }}>&ldquo;{v.reason}&rdquo;</span>}
                        </div>
                        <button type="button" onClick={() => open(id)} style={{ ...pill, ...TEAL_TONAL, ...(v.mine ? { width: "auto", padding: "0 16px" } : null) }}>{v.mine ? "Review & sign" : "Open"}</button>
                    </article>
                );
            })}
            </div>
        </section>
    );
}

function PageDocuments({ activeCaseId, focusDocumentId = null, focusAgreementId = null }) {
    const t = useT();
    const router = useClientRouter();
    const [search, setSearch] = useState("");
    const [sort, setSort] = useState("date");
    const [apiDocs, setApiDocs] = useState(null);   // null = loading
    const [loadError, setLoadError] = useState(null);
    const [loadWarning, setLoadWarning] = useState(null);
    const [busy, setBusy] = useState(null);         // `${id}:open|download`
    const [docError, setDocError] = useState({});   // id -> message

    const load = useCallback(() => {
        if (!activeCaseId) { setApiDocs([]); setLoadError(null); setLoadWarning(null); return () => {}; }
        let off = false;
        setApiDocs(null);
        setLoadError(null);
        setLoadWarning(null);
        Promise.all([
            apiListDocuments(activeCaseId),
            readAllV2Documents(activeCaseId)
                .then(items => ({ data: { items } }))
                .catch(error => ({ data: null, error })),
        ]).then(([legacy, v2]) => {
            if (off) return;
            const v2Disabled = v2?.status === 404 && errorCode(v2.error) === "feature_disabled";
            const v2Rows = Array.isArray(v2?.data?.items) ? v2.data.items.map(_mapV2Doc) : [];
            const legacyRows = !legacy.error && Array.isArray(legacy.data) ? legacy.data.map(_mapApiDoc) : null;
            const failed = [
                legacyRows === null ? "uploaded documents" : null,
                !v2Disabled && (v2?.error || !Array.isArray(v2?.data?.items)) ? "drafted documents" : null,
            ].filter(Boolean);
            if (failed.length && !v2Rows.length && !(legacyRows || []).length) {
                const cause = legacy.error?.message || v2?.error?.message;
                setLoadError(`${cause ? `${cause}. ` : ""}Could not load this case's ${andList(failed)}. Documents may still exist.`);
                setApiDocs([]);
                return;
            }
            const seen = new Set(v2Rows.map(d => d.id));
            setApiDocs([...v2Rows, ...(legacyRows || []).filter(d => !seen.has(d.id))]);
            if (failed.length) setLoadWarning(`Could not refresh the ${andList(failed)}. This list may be incomplete.`);
        });
        return () => { off = true; };
    }, [activeCaseId]);
    useEffect(() => load(), [load]);
    useEffect(() => {
        if (!focusDocumentId || apiDocs === null) return;
        const el = [...document.querySelectorAll("[data-doc]")]
            .find(node => node.getAttribute("data-doc") === String(focusDocumentId));
        el?.scrollIntoView?.({ behavior: "smooth", block: "center" });
    }, [focusDocumentId, apiDocs]);
    useEffect(() => onNotification(n => {
        const type = String(n?.type || "");
        const noticeCase = n?.payload?.case_id;
        if ((type.startsWith("document_") || type.startsWith("review_request_"))
            && (!noticeCase || String(noticeCase) === String(activeCaseId))) load();
    }), [activeCaseId, load]);

    const openDoc = async (doc) => {
        setBusy(`${doc.id}:open`);
        setDocError(p => ({ ...p, [doc.id]: null }));
        let url = null, error = null;
        if (doc.v2) {
            const res = await fetchRevisionPreview(doc.id, { revisionId: doc.revisionId, expectedPdfSha256: doc.pdfSha256 });
            url = res.data?.url || null;
            error = res.error?.message || res.error || null;
        } else {
            ({ data: url, error } = await fetchDocumentPreviewUrl(doc.id));
        }
        setBusy(null);
        if (error || !url) { setDocError(p => ({ ...p, [doc.id]: error || "Could not open this document." })); return; }
        // Not the "noopener" feature: with it window.open always returns null,
        // and a blocked tab could not be told apart from an opened one.
        const win = window.open(url, "_blank");
        if (win) win.opener = null;
        else setDocError(p => ({ ...p, [doc.id]: "Your browser blocked the new tab. Use Download instead." }));
        // The tab has loaded the bytes by then; the object URL is not needed after.
        setTimeout(() => URL.revokeObjectURL?.(url), 60000);
    };
    const download = async (doc) => {
        setBusy(`${doc.id}:download`);
        setDocError(p => ({ ...p, [doc.id]: null }));
        const safe = doc.name.replace(/[\\/:*?"<>|]+/g, " ").trim() || "document";
        const res = doc.v2
            ? await downloadDocumentFile(doc.id, `${safe}.pdf`, { revisionId: doc.revisionId, expectedPdfSha256: doc.pdfSha256 })
            : await apiDownloadDocument(doc.id, `${safe}.pdf`);
        setBusy(null);
        if (res?.error) setDocError(p => ({ ...p, [doc.id]: res.error }));
    };

    const docSource = apiDocs ?? [];
    const focusDocumentMissing = !!focusDocumentId && apiDocs !== null
        && !docSource.some(doc => String(doc.id) === String(focusDocumentId));
    const viewOf = d => (d.v2 ? documentStatusView(d._raw) : null);
    // Needs you: sent back by the lawyer, or needing approval again. Nothing else.
    const needsYou = docSource.filter(d => { const v = viewOf(d); return v && (v.isRecovery || d._raw?.review_status === "returned"); });
    const needIds = new Set(needsYou.map(d => d.id));
    const rest = docSource.filter(d => !needIds.has(d.id));
    const listed = rest
        .filter(d => !search || d.name.toLowerCase().includes(search.toLowerCase()))
        .sort(DOC_SORTS[sort] || DOC_SORTS.date);
    const tone = DOC_TONE(t);
    const pill = (kind, on) => ({
        display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6, minWidth: 112, padding: "0 14px", boxSizing: "border-box", height: 36, borderRadius: 999,
        cursor: on ? "wait" : "pointer", fontSize: 13, fontWeight: 700, fontFamily: "inherit",
        ...(kind === "brand" ? TEAL_TONAL : NEUTRAL_FILL),
    });
    const iconBtn = on => ({ position: "relative", display: "inline-grid", placeItems: "center", width: 36, height: 36, padding: 0, borderRadius: "50%", boxSizing: "border-box",
        cursor: on ? "wait" : "pointer", fontFamily: "inherit", ...NEUTRAL_FILL });
    const ico = d => <svg aria-hidden="true" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">{d}</svg>;
    const EYE = ico(<><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></>);
    const DOWN = ico(<><path d="M12 4v11" /><path d="M7 10l5 5 5-5" /><path d="M5 20h14" /></>);
    const solid = { display: "inline-flex", alignItems: "center", justifyContent: "center", minWidth: 104, height: 40, padding: "0 20px", borderRadius: 999, border: 0,
        cursor: "pointer", fontSize: 14, fontWeight: 700, fontFamily: "inherit", background: "var(--brand-solid, linear-gradient(135deg,#3EE0A1,#2EC4D6))", color: "var(--on-brand, #04212A)" };
    const fileIcon = (col, bg) => (
        <span aria-hidden="true" style={{ width: 40, height: 40, flexShrink: 0, borderRadius: 12, display: "grid", placeItems: "center", background: bg, color: col }}>
            <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></svg>
        </span>
    );
    const label = { fontSize: 12.5, fontWeight: 800, letterSpacing: ".08em", textTransform: "uppercase", margin: 0 };
    // Every document the client keeps, beyond this case: the Vault (Documents).
    const openVault = () => { requestDocumentsView("vault"); router.push("/documents"); };

    if (apiDocs === null) return <div style={{ fontSize: 14, color: t.textMuted }}>Loading documents…</div>;
    if (loadError) return (
        <div role="alert" style={{ borderRadius: 16, background: t.card, border: `1px solid ${t.border}`, padding: "16px 18px", fontSize: 14, color: t.text, display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{ flex: 1 }}>{loadError}</span>
            <button type="button" onClick={load} style={pill("brand", false)}>Retry</button>
        </div>
    );
    if (!docSource.length) return (<>
        {focusDocumentMissing && <div role="status" data-document-missing style={{ marginBottom: 14, borderRadius: 14, background: t.card, border: `1px solid ${t.warn}66`, padding: "12px 16px", color: t.text, fontSize: 13.5 }}>
            The document this link points to is no longer available on this matter.
        </div>}
        <div style={{ marginBottom: 20 }}><MatterAgreements caseId={activeCaseId} focusAgreementId={focusAgreementId} /></div>
        <section aria-label="Documents on this case" data-docs-empty
            style={{ borderRadius: 20, background: t.card, border: `1px solid ${t.border}`, padding: "40px 40px", display: "grid", gridTemplateColumns: "minmax(0, 1fr) 360px", gap: 40, alignItems: "center" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {fileIcon(t.primary, "var(--brand-soft, rgba(62,224,161,.13))")}
                <h2 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: t.text }}>No documents on this case yet</h2>
                <p style={{ margin: 0, fontSize: 14.5, color: t.textMuted, maxWidth: 520 }}>Documents you draft and link to this case, and the copies your lawyer sends back, are listed here to open or download.</p>
                <button type="button" data-draft-document onClick={() => router.push("/documents")} style={{ ...solid, alignSelf: "flex-start", marginTop: 4 }}>Draft a document</button>
            </div>
            <ol style={{ listStyle: "none", margin: 0, padding: "20px 22px", borderRadius: 16, background: "var(--brand-soft, rgba(62,224,161,.10))", border: `1px solid ${t.primary}4D`, display: "flex", flexDirection: "column", gap: 14 }}>
                {["Draft from a template in Documents", "Send it to your lawyer for review", "Drafts linked to this case appear here"].map((s, i) => (
                    <li key={s} style={{ display: "flex", alignItems: "center", gap: 12 }}>
                        <b aria-hidden="true" style={{ width: 24, height: 24, flexShrink: 0, borderRadius: "50%", display: "grid", placeItems: "center", fontSize: 12.5,
                            background: "var(--brand-solid, linear-gradient(135deg,#3EE0A1,#2EC4D6))", color: "var(--on-brand, #04212A)" }}>{i + 1}</b>
                        <span style={{ fontSize: 13.5, color: t.text }}>{s}</span>
                    </li>
                ))}
            </ol>
        </section>
    </>);

    return (
        // One column (board DocsTabA, 2026-11-25): the rail beside it started
        // lower than the list and left a dead column; its two actions now sit
        // in the Documents header and the agreements follow the files.
        <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
            {loadWarning && <div role="alert" data-documents-warning style={{ borderRadius: 14, background: t.card, border: `1px solid ${t.warn}66`, padding: "12px 16px", color: t.text, fontSize: 13.5 }}>
                {loadWarning} <button type="button" onClick={load} style={{ border: 0, background: "none", padding: 0, color: t.primary, fontWeight: 700, cursor: "pointer" }}>Try again</button>
            </div>}
            {focusDocumentMissing && <div role="status" data-document-missing style={{ borderRadius: 14, background: t.card, border: `1px solid ${t.warn}66`, padding: "12px 16px", color: t.text, fontSize: 13.5 }}>
                The document this link points to is no longer available on this matter.
            </div>}
            <div style={{ display: "flex", flexDirection: "column", gap: 22, minWidth: 0 }}>
                {needsYou.length > 0 && (
                    <section aria-label="Needs you" data-docs-needs-you style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                        <h2 style={{ ...label, color: t.warn }}>Needs you · {needsYou.length}</h2>
                        {needsYou.map(doc => {
                            const v = viewOf(doc);
                            const recovery = v.isRecovery;
                            return (
                                <article key={doc.id} data-doc={doc.id} style={{ display: "flex", flexDirection: "column", gap: 8, padding: "18px 22px", borderRadius: 18, background: t.card, border: `1px solid ${t.warn}73` }}>
                                    <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                                        {fileIcon(t.warn, `${t.warn}22`)}
                                        <div style={{ flex: 1, minWidth: 0 }}>
                                            <b style={{ display: "block", fontSize: 16, color: t.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{doc.name}</b>
                                            <span data-doc-status style={{ fontSize: 13.5, color: t.textMuted }}>
                                                {recovery ? (v.explanation || v.headline) : "Your lawyer sent it back. Open it to see their changes."}
                                            </span>
                                        </div>
                                        {recovery
                                            ? <button type="button" onClick={() => router.push("/documents")} style={solid}>Open in Documents</button>
                                            : <button type="button" onClick={() => openDoc(doc)} disabled={!!busy || doc.downloadable === false} style={solid}>
                                                {busy === `${doc.id}:open` ? "Opening…" : "Open"}</button>}
                                    </div>
                                    {docError[doc.id] && <div role="alert" style={{ fontSize: 13.5, color: t.danger }}>{docError[doc.id]}</div>}
                                </article>
                            );
                        })}
                    </section>
                )}

                <section aria-label="All documents" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 12, minHeight: 38 }}>
                        <h2 style={{ ...label, color: t.textMuted }}>{needsYou.length ? "All documents" : "Documents"} · {rest.length}</h2>
                        {rest.length <= 1 && <span style={{ marginLeft: "auto", fontSize: 13, color: t.textMuted }}>Drafts linked to this case and copies your lawyer sends back</span>}
                        {rest.length > 5 && (
                            <label style={{ marginLeft: "auto", position: "relative", display: "flex", alignItems: "center" }}>
                                <span style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }}>Search documents</span>
                                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke={t.textMuted} strokeWidth="2" strokeLinecap="round" aria-hidden="true" style={{ position: "absolute", left: 12 }}><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
                                <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search"
                                    style={{ width: 200, height: 36, boxSizing: "border-box", padding: "0 12px 0 34px", borderRadius: 999, border: `1px solid ${t.border}`, background: t.inputBg, color: t.text, fontSize: 13.5, outline: "none" }} />
                            </label>
                        )}
                        {rest.length > 1 && (
                            <select aria-label="Sort documents" value={sort} onChange={e => setSort(e.target.value)}
                                style={{ marginLeft: rest.length > 5 ? 0 : "auto", height: 36, padding: "0 12px", borderRadius: 999, border: `1px solid ${t.border}`, background: t.inputBg, color: t.text, fontSize: 13.5, fontWeight: 600, outline: "none", cursor: "pointer" }}>
                                {/* Options in the theme's colours: the native list was white with light text. */}
                                {[["date", "Newest first"], ["name", "Name"], ["type", "Type"]].map(([v, l]) => (
                                    <option key={v} value={v} style={{ background: t.card, color: t.text }}>{l}</option>
                                ))}
                            </select>
                        )}
                        <button type="button" data-open-vault onClick={openVault} style={{ ...pill("brand", false), ...TEAL_SOLID, minWidth: 0, height: 38 }}>Open Vault</button>
                        <button type="button" data-draft-document onClick={() => router.push("/documents")} style={{ ...solid, height: 38, fontSize: 13.5 }}>+ Draft a document</button>
                    </div>
                    {rest.length > 0 && (
                        <div style={{ borderRadius: 18, background: t.card, border: `1px solid ${t.border}`, overflow: "hidden" }}>
                            {listed.length === 0 && <div style={{ padding: "16px 20px", fontSize: 14, color: t.textMuted }}>No documents match.</div>}
                            {listed.map((doc, i) => {
                                const v = viewOf(doc);
                                const ready = doc.downloadable !== false;
                                return (
                                    <article key={doc.id} data-doc={doc.id} style={{ padding: "15px 20px", borderTop: i ? `1px solid ${t.border}` : 0 }}>
                                        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                                            {fileIcon(t.textMuted, t.cardHi)}
                                            <div style={{ flex: 1, minWidth: 0 }}>
                                                <b style={{ display: "block", fontSize: 15, color: t.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{doc.name}</b>
                                                <span style={{ display: "inline-flex", alignItems: "center", gap: 8, flexWrap: "wrap", fontSize: 13, color: t.textMuted }}>
                                                    {v && <span data-doc-status style={{ display: "inline-flex", alignItems: "center", gap: 6, fontWeight: 700, color: tone[v.tone] || t.textMuted }}>
                                                        <span aria-hidden="true" style={{ width: 7, height: 7, borderRadius: "50%", background: "currentColor" }} />{v.label}</span>}
                                                    {v && <span aria-hidden="true">·</span>}
                                                    <span>{doc.type} · {doc.date}</span>
                                                </span>
                                            </div>
                                            {ready ? (<>
                                                <button type="button" onClick={() => openDoc(doc)} disabled={!!busy} style={pill("brand", busy === `${doc.id}:open`)}>
                                                    {EYE}{busy === `${doc.id}:open` ? "Opening…" : "Open"}</button>
                                                <button type="button" data-doc-download onClick={() => download(doc)} disabled={!!busy} className="doc-icon-btn"
                                                    title={busy === `${doc.id}:download` ? "Downloading…" : "Download"} style={iconBtn(busy === `${doc.id}:download`)}>
                                                    {DOWN}<span style={SR_ONLY}>{busy === `${doc.id}:download` ? "Downloading…" : "Download"}</span></button>
                                            </>) : (
                                                // No PDF for this version yet: say so, in the buttons' space.
                                                <span style={{ width: 216, textAlign: "center", fontSize: 13, color: t.textMuted }}>PDF not ready yet</span>
                                            )}
                                        </div>
                                        {docError[doc.id] && <div role="alert" style={{ fontSize: 13.5, color: t.danger, marginTop: 8 }}>{docError[doc.id]}</div>}
                                    </article>
                                );
                            })}
                        </div>
                    )}
                </section>

                <MatterAgreements caseId={activeCaseId} focusAgreementId={focusAgreementId} />
            </div>
        </div>
    );
}

// ─── PAGE: PAYMENTS ───────────────────────────────────────────────────────────
// Redesigned 2026-11-23 (approved v2 preview): the amount due first and
// biggest, with one Pay; the agreed fee as one quiet line; then a history
// table of what has finished. A due fee is shown once: in the top card, never
// again in the history.
//   due      = created, pending (checkout started, not settled: payable again),
//              failed (the payer was told to try again)
//   finished = paid, expired, cancelled
// The agreed-fee line needs an ACCEPTED engagement with a FIXED fee and counts
// professional fees only: a peshi fee is not part of the agreed fee, and an
// hourly or per-hearing rate has no "left".
const PAY_DUE = new Set(["created", "pending", "failed"]);

function PagePayments({ t, caseId = null, focusPaymentId = null, onAllPayments = null }) {
    const { T } = useLang();
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    // A failed read is said, never shown as "no fee requests": it could hide a
    // fee that is due (2026-11-23).
    const [loadError, setLoadError] = useState(null);
    // The engagement on this case, for the agreed-fee line (case view only).
    const engagements = useEngagements(caseId);
    const engagement = caseId ? (engagements.data || []).find(e => String(e.case_id || "") === String(caseId) && e.status === "accepted") || null : null;
    // A link to one payment (a fee notification): scroll to it once it is on screen.
    const focusDone = useRef(null);
    useEffect(() => {
        if (!focusPaymentId || loading || focusDone.current === focusPaymentId) return;
        const hit = items.find(p => String(p.id) === String(focusPaymentId));
        if (!hit) return;
        focusDone.current = focusPaymentId;
        setTimeout(() => {
            const el = [...document.querySelectorAll("[data-payment]")].find(n => n.getAttribute("data-payment") === String(focusPaymentId));
            el?.scrollIntoView?.({ behavior: "smooth", block: "center" });
        }, 0);
    }, [focusPaymentId, loading, items, caseId]);
    const [payingId, setPayingId] = useState(null);
    const [payError, setPayError] = useState({});   // payment id -> message

    // As in HireRequests: the case on screen now, and only the newest read lands.
    const caseRef = useRef(caseId);
    caseRef.current = caseId;
    const readSeq = useRef(0);
    const load = useCallback(async () => {
        const mine = ++readSeq.current;
        const forCase = caseRef.current;
        const { data, error } = await listPayments(forCase ? { caseId: forCase } : undefined);
        if (mine !== readSeq.current) return;
        if (Array.isArray(data)) { setItems(data); setLoadError(null); }
        else setLoadError(error?.message || "Couldn't load your payments.");
        setLoading(false);
    }, []);
    // A different case is a fresh read, never the previous case's fees.
    useEffect(() => { setItems([]); setLoadError(null); setLoading(true); load(); }, [caseId, load]);
    // Checkout finishes in another tab. Webhook notifications are the primary
    // refresh; focus is a fallback when the socket was briefly disconnected.
    useEffect(() => onNotification(n => {
        const type = String(n?.type || "");
        const noticeCase = n?.payload?.case_id;
        if (type.startsWith("payment_") && (!caseId || !noticeCase || String(noticeCase) === String(caseId))) load();
    }), [caseId, load]);
    useEffect(() => {
        const refresh = () => load();
        window.addEventListener("focus", refresh);
        return () => window.removeEventListener("focus", refresh);
    }, [load]);

    const pay = async (p) => {
        setPayingId(p.id);
        setPayError(m => ({ ...m, [p.id]: null }));
        const { data, error } = await startCheckout(p.id);
        if (error) {
            setPayError(m => ({ ...m, [p.id]: error.message || T("Payment could not be started. Try again.", "ادائیگی شروع نہیں ہو سکی۔ دوبارہ کوشش کریں۔") }));
            setPayingId(null);
            await load();             // e.g. it expired meanwhile: show its real status
            return;
        }
        if (data?.dry_run) {
            const res = await mockPay(p.id);          // dev/test: settle immediately
            if (res?.error) setPayError(m => ({ ...m, [p.id]: res.error.message || T("Payment did not go through.", "ادائیگی مکمل نہیں ہوئی۔") }));
        } else if (data?.checkout_url) {
            window.open(data.checkout_url, "_blank", "noopener");
        }
        await load();
        setPayingId(null);
    };

    const money = n => `PKR ${Number(n || 0).toLocaleString()}`;
    const day = iso => (iso ? formatPkt(iso, { day: "numeric", month: "short" }) : null);
    const feeName = p => (p.purpose === "peshi_fee" ? T("Appearance (peshi) fee", "پیشی فیس") : T("Professional fee", "پروفیشنل فیس"));
    const isFocus = p => !!focusPaymentId && String(p.id) === String(focusPaymentId);
    const focusRing = p => (isFocus(p) ? { outline: `2px solid ${t.primary}`, outlineOffset: -2, borderRadius: 12 } : null);
    const ts = p => new Date(p.paid_at || p.updated_at || p.created_at || 0).getTime();

    const shown = caseId ? items.filter(p => String(p.case_id || "") === String(caseId)) : items;
    const due = shown.filter(p => PAY_DUE.has(p.status))
        .sort((a, b) => new Date(a.expires_at || a.created_at || 0) - new Date(b.expires_at || b.created_at || 0));
    const finished = shown.filter(p => !PAY_DUE.has(p.status)).sort((a, b) => ts(b) - ts(a));
    const dueTotal = due.reduce((s, p) => s + Number(p.amount || 0), 0);

    // The agreed fee, only where it means something.
    const fixedFee = engagement && engagement.fee_amount && !["hourly", "per_hearing"].includes(engagement.fee_type);
    const proPaid = shown.filter(p => p.status === "paid" && p.purpose !== "peshi_fee").reduce((s, p) => s + Number(p.amount || 0), 0);

    const dueNote = p => (p.status === "failed" ? T("Last attempt did not go through — try again", "پچھلی کوشش مکمل نہیں ہوئی — دوبارہ کوشش کریں")
        : p.status === "pending" ? T("Payment started, not finished", "ادائیگی شروع ہوئی، مکمل نہیں")
        : p.expires_at ? `${T("Pay by", "ادائیگی کی آخری تاریخ")} ${day(p.expires_at)}` : T("Due now", "ابھی واجب"));
    const byLine = p => [feeName(p), p.payee_snapshot?.name ? `${T("requested by", "مانگی")} ${p.payee_snapshot.name}${p.created_at ? ` ${T("on", "")} ${day(p.created_at)}` : ""}` : null,
        !caseId && p.case_snapshot?.title ? p.case_snapshot.title : null].filter(Boolean).join(" · ");
    const payLabel = p => (payingId === p.id ? T("Processing…", "زیرِ عمل…") : `${p.status === "failed" ? T("Try again", "دوبارہ کوشش") + " · " : ""}${T("Pay", "ادا کریں")} ${money(p.amount)}`);
    const payBtn = (p, big) => (
        <button type="button" onClick={() => pay(p)} disabled={payingId === p.id}
            style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", minWidth: big ? 220 : 170, height: big ? 48 : 40, padding: "0 20px", borderRadius: 999, border: "none",
                background: "var(--brand-solid, linear-gradient(135deg,#3EE0A1,#2EC4D6))", color: "var(--on-brand, #04212A)", fontSize: big ? 15 : 13.5, fontWeight: 800,
                cursor: payingId === p.id ? "default" : "pointer", fontFamily: "inherit", opacity: payingId === p.id ? .7 : 1 }}>{payLabel(p)}</button>
    );
    const payErr = p => payError[p.id] && <div role="alert" style={{ fontSize: 12.5, color: t.danger || "#B42318", marginTop: 6 }}>{payError[p.id]}</div>;
    const finishedStatus = p => (p.status === "paid" ? [`${T("Paid", "ادا شدہ")}${day(p.paid_at || p.updated_at) ? ` ${day(p.paid_at || p.updated_at)}` : ""}`, t.primary]
        : p.status === "expired" ? [T("Expired", "میعاد ختم"), t.textMuted]
        : p.status === "cancelled" ? [T("Cancelled", "منسوخ"), t.textMuted] : [p.status, t.textMuted]);
    const th = { padding: "10px 12px", fontWeight: 700, fontSize: 12, letterSpacing: ".08em", textTransform: "uppercase", color: t.textMuted, borderTop: `1px solid ${t.border}`, textAlign: "left" };
    const td = { padding: "14px 12px", borderTop: `1px solid ${t.border}`, verticalAlign: "middle" };

    return (
        <div data-payments-page style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
                <h1 style={{ margin: 0, fontSize: 20, fontWeight: 800, color: t.text }}>{T("Payments", "ادائیگیاں")}</h1>
                <span style={{ fontSize: 13.5, color: t.textMuted }}>
                    {caseId ? T("Fees your lawyer requested on this case", "اس کیس پر آپ کے وکیل کی مانگی گئی فیس") : T("Fees requiring action and recent payment history", "واجب فیس اور حالیہ ادائیگیوں کی تاریخ")}
                </span>
            </div>

            {loading && <div style={{ fontSize: 13.5, color: t.textMuted }}>{T("Loading…", "لوڈ ہو رہا ہے…")}</div>}
            {!loading && loadError && (
                <div role="alert" data-payments-error style={{ background: t.card, border: `1px solid ${t.border}`, borderRadius: 14, padding: 16, display: "flex", alignItems: "center", gap: 12 }}>
                    <span style={{ flex: 1, fontSize: 13.5, color: t.text }}>
                        {items.length ? T("Couldn't refresh your payments — this list may be out of date.", "ادائیگیاں تازہ نہیں ہو سکیں — یہ فہرست پرانی ہو سکتی ہے۔")
                            : T("Couldn't load your payments. A fee may be due.", "ادائیگیاں لوڈ نہیں ہو سکیں۔ کوئی فیس واجب ہو سکتی ہے۔")}
                    </span>
                    <button type="button" onClick={() => { setLoading(true); load(); }} style={{ ...hubBtn("ghost", t), height: 34 }}>{T("Try again", "دوبارہ کوشش کریں")}</button>
                </div>
            )}
            {focusPaymentId && !loading && !loadError && !items.some(p => String(p.id) === String(focusPaymentId)) && (
                <div role="status" data-payment-missing style={{ fontSize: 12.5, color: t.textMuted }}>
                    {T("The payment this link points to is not in your list.", "اس لنک والی ادائیگی آپ کی فہرست میں نہیں ہے۔")}
                </div>
            )}
            {!loading && !loadError && shown.length === 0 && (
                <div data-payments-empty style={{ background: t.card, border: `1px solid ${t.border}`, borderRadius: 16, padding: 28, textAlign: "center", fontSize: 14, color: t.textMuted }}>
                    {caseId ? T("No fee requests on this case yet.", "اس کیس پر ابھی کوئی فیس کی درخواست نہیں۔") : T("No fee requests yet.", "ابھی تک کوئی فیس کی درخواست نہیں۔")}
                    {caseId && onAllPayments && <div style={{ marginTop: 10 }}><button type="button" data-open-all-payments onClick={onAllPayments} style={{ border: 0, background: "none", padding: 0, cursor: "pointer", color: t.primary, fontSize: 13.5, fontWeight: 700 }}>{T("All my payments →", "تمام ادائیگیاں ←")}</button></div>}
                </div>
            )}

            {/* 1. THE AMOUNT DUE: the one thing to act on */}
            {!loading && due.length === 1 && (() => {
                const p = due[0];
                return (
                    <section aria-label="Amount due" data-amount-due data-payment={p.id} data-focused={isFocus(p) ? "" : undefined}
                        style={{ display: "flex", alignItems: "center", gap: 28, padding: "24px 28px", borderRadius: 20, background: t.card, border: `1px solid ${p.status === "failed" ? (t.danger || "#B42318") : t.warn}66`, ...focusRing(p) }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontSize: 12.5, fontWeight: 800, letterSpacing: ".1em", textTransform: "uppercase", color: p.status === "failed" ? (t.danger || "#B42318") : t.warn }}>
                                {T("Amount due", "واجب رقم")} · {dueNote(p)}</div>
                            <div style={{ font: "800 40px/1.1 Nunito, 'Hanken Grotesk', sans-serif", marginTop: 6, color: t.text }}>{money(p.amount)}</div>
                            <div style={{ fontSize: 14.5, color: t.textMuted, marginTop: 6 }}>{byLine(p)}</div>
                            {p.note && <div style={{ fontSize: 13.5, color: t.textMuted, marginTop: 4, fontStyle: "italic" }}>“{p.note}”</div>}
                            {payErr(p)}
                        </div>
                        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
                            {payBtn(p, true)}
                            <span style={{ fontSize: 12.5, color: t.textMuted }}>{T("Secure payment · receipt after it is paid", "محفوظ ادائیگی · ادائیگی کے بعد رسید")}</span>
                        </div>
                    </section>
                );
            })()}
            {!loading && due.length > 1 && (
                <section aria-label="Amount due" data-amount-due style={{ borderRadius: 20, background: t.card, border: `1px solid ${t.warn}66`, overflow: "hidden" }}>
                    <div style={{ padding: "20px 28px 14px" }}>
                        <div style={{ fontSize: 12.5, fontWeight: 800, letterSpacing: ".1em", textTransform: "uppercase", color: t.warn }}>{due.length} {T("fees due", "فیس واجب")}</div>
                        <div style={{ font: "800 36px/1.1 Nunito, 'Hanken Grotesk', sans-serif", marginTop: 6, color: t.text }}>{money(dueTotal)}</div>
                    </div>
                    {due.map(p => (
                        <div key={p.id} data-payment={p.id} data-focused={isFocus(p) ? "" : undefined}
                            style={{ display: "flex", alignItems: "center", gap: 16, padding: "14px 28px", borderTop: `1px solid ${t.border}`, ...focusRing(p) }}>
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <b style={{ fontSize: 16, color: t.text }}>{money(p.amount)}</b>
                                <div style={{ fontSize: 13.5, color: t.textMuted }}>
                                    <span style={{ fontWeight: 700, color: p.status === "failed" ? (t.danger || "#B42318") : t.warn }}>{dueNote(p)}</span> · {byLine(p)}
                                </div>
                                {payErr(p)}
                            </div>
                            {payBtn(p, false)}
                        </div>
                    ))}
                </section>
            )}
            {!loading && !loadError && shown.length > 0 && due.length === 0 && (
                <div data-nothing-due style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 14.5, fontWeight: 700, color: t.primary }}>
                    <span aria-hidden="true" style={{ width: 8, height: 8, borderRadius: "50%", background: "currentColor" }} />
                    {caseId ? T("Nothing due on this case right now.", "اس کیس پر ابھی کچھ واجب نہیں۔") : T("Nothing due right now.", "ابھی کچھ واجب نہیں۔")}
                </div>
            )}

            {/* 2. THE AGREED FEE: one quiet line */}
            {!loading && engagement && engagement.fee_amount ? (
                fixedFee ? (
                    <section aria-label="Agreed fee" data-agreed-fee style={{ display: "flex", alignItems: "center", gap: 18, padding: "0 4px", flexWrap: "wrap" }}>
                        <span style={{ fontSize: 14, color: t.textMuted, whiteSpace: "nowrap" }}>
                            {T("Professional fee:", "پروفیشنل فیس:")} <b style={{ color: t.text }}>{money(proPaid)}</b> {T("paid of", "ادا از")} <b style={{ color: t.text }}>{money(engagement.fee_amount)}</b> {T("agreed", "طے شدہ")}
                        </span>
                        <span aria-hidden="true" style={{ flex: "1 1 160px", height: 8, borderRadius: 4, background: t.cardHi, overflow: "hidden" }}>
                            <span style={{ display: "block", height: "100%", width: `${Math.min(100, (proPaid / Number(engagement.fee_amount)) * 100)}%`, background: t.primary }} />
                        </span>
                        <span style={{ fontSize: 14, color: t.textMuted, whiteSpace: "nowrap" }}>{money(Math.max(0, Number(engagement.fee_amount) - proPaid))} {T("left", "باقی")}</span>
                    </section>
                ) : (
                    <div data-agreed-fee style={{ fontSize: 14, color: t.textMuted, padding: "0 4px" }}>
                        {T("Agreed rate:", "طے شدہ ریٹ:")} <b style={{ color: t.text }}>{feeLabel(engagement)}</b>
                    </div>
                )
            ) : null}

            {/* 3. HISTORY: what has finished */}
            {!loading && (finished.length > 0 || (caseId && onAllPayments && shown.length > 0)) && (
                <section aria-label="Payment history" data-payment-history style={{ borderRadius: 18, background: t.card, border: `1px solid ${t.border}`, overflow: "hidden" }}>
                    <div style={{ display: "flex", alignItems: "center", padding: "16px 22px" }}>
                        <h2 style={{ margin: 0, fontSize: 16, fontWeight: 800, color: t.text }}>{T("Payment history", "ادائیگیوں کی تاریخ")}</h2>
                        {caseId && onAllPayments && (
                            <button type="button" data-open-all-payments onClick={onAllPayments}
                                style={{ marginLeft: "auto", border: 0, background: "none", padding: 0, cursor: "pointer", color: t.primary, fontSize: 13.5, fontWeight: 700 }}>
                                {T("All my payments →", "تمام ادائیگیاں ←")}
                            </button>
                        )}
                    </div>
                    {finished.length === 0 ? (
                        <div style={{ padding: "0 22px 16px", fontSize: 13.5, color: t.textMuted }}>{T("No finished payments yet.", "ابھی کوئی ادائیگی مکمل نہیں۔")}</div>
                    ) : (
                        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
                            <thead>
                                <tr>
                                    <th scope="col" style={{ ...th, paddingLeft: 22 }}>{T("Date", "تاریخ")}</th>
                                    <th scope="col" style={th}>{T("Fee", "فیس")}</th>
                                    <th scope="col" style={{ ...th, textAlign: "right" }}>{T("Amount", "رقم")}</th>
                                    <th scope="col" style={th}>{T("Status", "حیثیت")}</th>
                                    <th scope="col" style={{ ...th, textAlign: "right", paddingRight: 22 }}>{T("Receipt", "رسید")}</th>
                                </tr>
                            </thead>
                            <tbody>
                                {finished.map(p => {
                                    const [word, ink] = finishedStatus(p);
                                    return (
                                        <tr key={p.id} data-payment={p.id} data-focused={isFocus(p) ? "" : undefined} style={isFocus(p) ? { outline: `2px solid ${t.primary}`, outlineOffset: -2 } : undefined}>
                                            <td style={{ ...td, paddingLeft: 22, color: t.textMuted, whiteSpace: "nowrap" }}>{day(p.created_at) || "—"}</td>
                                            <td style={td}>
                                                <b style={{ color: t.text }}>{feeName(p)}</b>
                                                <div style={{ fontSize: 12.5, color: t.textMuted }}>{[p.payee_snapshot?.name, !caseId ? p.case_snapshot?.title : null].filter(Boolean).join(" · ")}</div>
                                            </td>
                                            <td style={{ ...td, textAlign: "right", fontWeight: 700, color: t.text, whiteSpace: "nowrap" }}>{money(p.amount)}</td>
                                            <td style={{ ...td, whiteSpace: "nowrap" }}>
                                                <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontWeight: 700, color: ink }}>
                                                    <span aria-hidden="true" style={{ width: 7, height: 7, borderRadius: "50%", background: "currentColor" }} />{word}</span>
                                            </td>
                                            <td style={{ ...td, textAlign: "right", paddingRight: 22, whiteSpace: "nowrap" }}>
                                                {p.status === "paid"
                                                    ? <button type="button" onClick={() => downloadReceipt(p.id, `receipt-${p.id}.pdf`)}
                                                        style={{ border: 0, background: "none", padding: 0, cursor: "pointer", color: t.primary, fontSize: 13.5, fontWeight: 700, fontFamily: "inherit" }}>{T("Receipt", "رسید")} ↓</button>
                                                    : <span style={{ color: t.textMuted }}>—</span>}
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    )}
                </section>
            )}
        </div>
    );
}

// The Notifications page that was here was removed (2026-11-23). It repeated
// the app's notification drawer (the bell in the app sidebar), but clicking a
// row only marked it read; the drawer opens the exact case, payment or
// appointment.

// ─── PAGE: COMMUNICATION ──────────────────────────────────────────────────────
// The case conversation with the lawyer, from the server and nothing else.
// What used to be here and was not real has been removed: a hardcoded
// "Atty. Ahmad Raza — Online" badge and sender name, a fixed "1 Awaiting"
// count, two invented questions, milestone notes and "tag lawyer" that lived
// only in this browser (the lawyer never saw them), and a document picker that
// read a variable that did not exist and crashed the page.
function PageCommunication({ caseId, activeCase }) {
    const t = useT();
    const [msgs, setMsgs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState(null);
    const [sending, setSending] = useState(false);
    const [sendError, setSendError] = useState(null);
    const [input, setInput] = useState("");
    const endRef = useRef(null);
    useEffect(() => { endRef.current?.scrollIntoView?.({ behavior: "smooth" }); }, [msgs]);

    const toMsg = (m) => ({
        id: m._id,
        from: m.sender_role === "lawyer" ? "lawyer" : "client",
        name: m.sender_name || "",
        text: m.text,
        date: m.created_at ? new Date(m.created_at).toLocaleString("en-US", { timeZone: "Asia/Karachi", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—",
    });

    const load = useCallback(() => {
        if (!caseId) { setLoading(false); setMsgs([]); return () => {}; }
        let off = false;
        setLoading(true);
        apiListMessages(caseId).then(({ data, error }) => {
            if (off) return;
            if (error || !Array.isArray(data)) {
                // Not "no messages": the read failed, and saying so matters.
                setLoadError(error?.message || "Could not load messages.");
                setMsgs([]);
            } else {
                setLoadError(null);
                setMsgs(data.map(toMsg));
            }
            setLoading(false);
        });
        return () => { off = true; };
    }, [caseId]);
    useEffect(() => load(), [load]);

    // The lawyer replies while this page is open: show it.
    useEffect(() => onNotification((n) => {
        if (n.type === "case_message" && n.payload?.case_id === caseId) load();
    }), [caseId, load]);

    const send = async () => {
        const text = input.trim();
        if (!text || sending || !caseId) return;
        setSending(true);
        setSendError(null);
        const { data, error } = await apiSendMessage(caseId, text);
        setSending(false);
        if (error || !data) {
            // Nothing was delivered: keep the text and say why.
            setSendError(error?.message || "Your message was not sent. Try again.");
            return;
        }
        setMsgs(p => [...p, toMsg(data)]);
        setInput("");
    };

    const lawyerName = [...msgs].reverse().find(m => m.from === "lawyer" && m.name)?.name;
    const hasLawyer = !!activeCase?.lawyerAssigned;
    const closed = ["closed", "dismissed"].includes(activeCase?.status);
    // Client messages after the lawyer's last reply: what is still waiting.
    const lastLawyer = msgs.map(m => m.from).lastIndexOf("lawyer");
    const waiting = msgs.slice(lastLawyer + 1).filter(m => m.from === "client");

    return (
        <div>
            <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
                <Badge variant={hasLawyer ? "success" : "warn"} t={t}>
                    {hasLawyer ? `● ${lawyerName || "Your lawyer"}` : "No lawyer assigned yet"}
                </Badge>
            </div>
            <div className="rgrid" style={{ display: "grid", gridTemplateColumns: "1fr 290px", gap: 16 }}>
                <Card t={t} style={{ display: "flex", flexDirection: "column" }}>
                    <SH icon="💬" title="Messages with your lawyer" desc="Every message stays inside this case"
                        badge={waiting.length ? <Badge variant="warn" t={t}>{waiting.length} awaiting reply</Badge> : null} t={t} />
                    <div style={{ flex: 1, padding: "16px 20px", overflowY: "auto", maxHeight: 380 }}>
                        {loading && <div style={{ fontSize: 13, color: t.textMuted }}>Loading messages…</div>}
                        {!loading && loadError && (
                            <div role="alert" style={{ fontSize: 13, color: t.danger || "#e8526a" }}>
                                {loadError} <button type="button" onClick={load} style={{ marginLeft: 8, background: "none", border: "none", color: t.primary, cursor: "pointer", fontWeight: 700 }}>Retry</button>
                            </div>
                        )}
                        {!loading && !loadError && msgs.length === 0 && (
                            <div style={{ fontSize: 13, color: t.textMuted }}>No messages yet.{hasLawyer ? " Ask your lawyer anything about this case." : ""}</div>
                        )}
                        {msgs.map(m => (
                            <div key={m.id} style={{ display: "flex", flexDirection: "column", alignItems: m.from === "client" ? "flex-end" : "flex-start", marginBottom: 16 }}>
                                <div style={{ fontSize: 10, color: t.textFaint, marginBottom: 4, fontWeight: 600 }}>
                                    {m.from === "lawyer" ? (m.name || "Your lawyer") : "You"} · {m.date}
                                </div>
                                <div style={{
                                    maxWidth: "82%", padding: "10px 14px", borderRadius: 12,
                                    background: m.from === "client" ? t.primaryGlow2 : t.cardHi,
                                    border: `1px solid ${m.from === "client" ? t.primary + "44" : t.border}`,
                                    color: t.text, fontSize: 13, lineHeight: 1.6, whiteSpace: "pre-wrap", overflowWrap: "anywhere",
                                }}>{m.text}</div>
                            </div>
                        ))}
                        <div ref={endRef} />
                    </div>
                    <div style={{ padding: "12px 20px", borderTop: `1px solid ${t.border}` }}>
                        {closed ? (
                            <div style={{ fontSize: 12.5, color: t.textMuted }}>This case is closed, so no new messages can be sent.</div>
                        ) : !hasLawyer ? (
                            <div style={{ fontSize: 12.5, color: t.textMuted }}>You can message once a lawyer has taken your case.</div>
                        ) : (<>
                            <div style={{ display: "flex", gap: 8 }}>
                                <div style={{ flex: 1 }}>
                                    <Inp placeholder="Ask your lawyer a question…" value={input} onChange={v => { setInput(v); setSendError(null); }} t={t} />
                                </div>
                                {/* The theme's brand button (2026-11-25), as on the Overview's reply box: the flat mint one stood apart. */}
                                <Btn t={t} variant="primary" onClick={send} disabled={!input.trim() || sending}
                                    style={!input.trim() || sending ? { minWidth: 110 } : { minWidth: 110, border: 0, background: "var(--brand-solid, linear-gradient(135deg,#3EE0A1,#2EC4D6))", color: "var(--on-brand, #04212A)" }}>
                                    <span data-send-message>{sending ? "Sending…" : "Send ↗"}</span></Btn>
                            </div>
                            {sendError && <div role="alert" style={{ fontSize: 12, color: t.danger || "#e8526a", marginTop: 6 }}>{sendError}</div>}
                        </>)}
                    </div>
                </Card>

                <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                    <Card t={t}>
                        <SH icon="❓" title="Waiting for a reply" t={t} />
                        <div style={{ padding: "0 16px 16px" }}>
                            {waiting.length === 0 && <div style={{ fontSize: 12.5, color: t.textMuted }}>Nothing is waiting. Your lawyer has replied to everything.</div>}
                            {waiting.map((m, i) => (
                                <div key={m.id} style={{ padding: "10px 0", borderBottom: i < waiting.length - 1 ? `1px solid ${t.border}` : "none" }}>
                                    <div style={{ fontSize: 12, fontWeight: 600, color: t.text, marginBottom: 4, overflowWrap: "anywhere" }}>{m.text.length > 120 ? m.text.slice(0, 119) + "…" : m.text}</div>
                                    <div style={{ fontSize: 10.5, color: t.textFaint }}>Sent {m.date}</div>
                                </div>
                            ))}
                        </div>
                    </Card>
                </div>
            </div>
        </div>
    );
}

// ─── PAGE: APPOINTMENTS ───────────────────────────────────────────────────────
// Statuses a client may still call off. The server's transition table allows
// cancellation from pending and confirmed only; everything else is terminal, so
// offering the action there would be a button that always fails.
// One page of appointments. The list pages now, so a first screen arrives
// quickly and the rest is a click away rather than a silent truncation at 50.
const APPT_PAGE_SIZE = 25;

const CLIENT_CANCELLABLE = new Set(["pending", "confirmed"]);

// The server refuses a client cancellation inside this window. Stated up front
// rather than discovered through a 422: a client who reads it can ring the
// lawyer instead, and one who does not just meets a refusal they cannot act on.
const CANCEL_CUTOFF_HOURS = 2;
// Times a client may ASK for when the lawyer has published no hours and the
// server does not enforce hours -- the same grid the booking dialog offers.
const REQUEST_DAY_TIMES = Array.from({ length: 24 }, (_, i) => {
    const m = 9 * 60 + i * 30;
    return `${String(Math.floor(m / 60)).padStart(2, "0")}:${m % 60 ? "30" : "00"}`;
});


// Stored statuses in words. `no_show` in particular must not reach a client as
// "no_show", and "completed" versus "cancelled" is the difference between a
// consultation they may owe a fee for and one they do not.
const STATUS_WORDS = {
    pending: "pending", confirmed: "confirmed", cancelled: "cancelled",
    completed: "completed", no_show: "a no-show",
    // Not "cancelled". Nobody called this off; it lapsed unanswered, and a
    // client told their request was cancelled would reasonably ask who by.
    expired: "expired",
};
const statusWord = (status) => STATUS_WORDS[status] || String(status || "unknown");

// Only a PENDING request may be moved. A confirmed appointment is an agreement
// between two people, and letting one of them move it is not rescheduling — it
// is telling the other party where to be. The server refuses it too; this keeps
// the control off a card where it would always fail.
const CLIENT_RESCHEDULABLE = new Set(["pending"]);

/** Move a pending request to a different time.
 *
 * Pakistan time throughout, in both directions: the pickers are filled from the
 * stored instant rendered in PKT, and the chosen wall-clock time is converted
 * back to a UTC instant before it is sent. A date input reads and writes the
 * BROWSER's zone, so a client outside PKT would otherwise compose a time five
 * hours from the one on screen.
 *
 * The card never moves optimistically. The server owns the outcome — the slot
 * may be taken, the cutoff may have passed, the lawyer may have confirmed — so
 * the new time appears only after a successful reload.
 */
/* The lawyer offered other times for this pending request (2026-10-19). Picking
 * one moves the request there AND confirms it -- the lawyer already agreed to
 * every time they offered (services/appointment_suggestions.py). */
function ApptSuggestion({ appt, t, onReload, first }) {
    const tint = (col, pct) => `color-mix(in srgb, ${col} ${pct}%, transparent)`;
    const s = appt.time_suggestion;
    const [busy, setBusy] = useState(null);
    const [error, setError] = useState(null);
    if (appt.status !== "pending" || !s?.options?.length) return null;
    const pick = async (when) => {
        if (busy) return;
        setBusy(when); setError(null);
        const { data, error: err, status } = await apiAcceptAppointmentSuggestion(appt._id || appt.id, {
            scheduledAt: when, scheduleVersion: appt.schedule_version ?? 0,
        });
        setBusy(null);
        if (err) {
            setError(err.message || "Could not book that time.");
            if ((status === 409 || status === 422) && onReload) await onReload();
            return;
        }
        if (data && data.suggestion_confirmed === false) setError("Moved to that time — it is waiting for your lawyer to confirm.");
        if (onReload) await onReload();
    };
    return (
        <section aria-label="Suggested times" data-appt-suggestion style={{ padding: "16px 18px", borderRadius: 16, background: tint(t.primary, 8), border: `1px solid ${tint(t.primary, 40)}`, display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                <span aria-hidden="true" style={{ width: 40, height: 40, flexShrink: 0, borderRadius: 12, display: "grid", placeItems: "center", background: tint(t.primary, 16), color: t.primary }}><DtIcon name="repeat" size={20} /></span>
                <div>
                    <b style={{ fontSize: 14.5, color: t.text }}>{first} suggested other times</b>
                    <div style={{ fontSize: 13, color: t.textMuted, marginTop: 2 }}>Pick one and your appointment is confirmed at that time.</div>
                </div>
            </div>
            {s.note && <div style={{ fontSize: 13, color: t.text, fontStyle: "italic", padding: "8px 12px", borderRadius: 10, background: t.inputBg }}>“{s.note}”</div>}
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {s.options.map(o => (
                    <button key={o} type="button" data-suggested-time={o} disabled={Boolean(busy)} onClick={() => pick(o)}
                        style={{ ...hubBtn("ghost", t), borderColor: tint(t.primary, 55), opacity: busy && busy !== o ? 0.5 : 1 }}>
                        {busy === o ? "Booking…" : formatPkt(o, { weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" })}
                    </button>
                ))}
            </div>
            <div style={{ fontSize: 12, color: t.textMuted }}>None of these work? Keep your time and wait, change it below, or cancel the request.</div>
            {error && <div role="alert" style={{ fontSize: 12.5, color: t.danger }}>{error}</div>}
        </section>
    );
}

/* Moving a CONFIRMED appointment by agreement (2026-10-19,
 * APPOINTMENT_FLOW_PLAN.md). Either side proposes one new time; the other
 * accepts or declines; the current time stands until it is accepted. */
function ApptMoveProposal({ appt, t, onReload, first }) {
    const id = appt._id || appt.id;
    const p = appt.reschedule_proposal && (!appt.reschedule_proposal.expires_at || new Date(appt.reschedule_proposal.expires_at) > new Date())
        ? appt.reschedule_proposal : null;
    const [open, setOpen] = useState(false);
    const [date, setDate] = useState("");
    const [time, setTime] = useState("10:00");
    const [note, setNote] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);
    const started = new Date(appt.scheduled_at) <= new Date();
    if (appt.status !== "confirmed" || started) return null;
    const when = v => formatPkt(v, { weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
    const run = async (fn, okMsg) => {
        if (busy) return;
        setBusy(true); setError(null);
        const { error: err } = await fn();
        setBusy(false);
        if (err) { setError(err.message || "That didn't go through."); if (onReload) await onReload(); return; }
        setOpen(false); setDate(""); setNote("");
        if (onReload) await onReload();
    };
    const slots = Array.from({ length: 28 }, (_, i) => `${String(8 + Math.floor(i / 2)).padStart(2, "0")}:${i % 2 ? "30" : "00"}`);
    const field = { height: 40, width: "100%", boxSizing: "border-box", padding: "0 10px", borderRadius: 9, border: "1px solid " + t.border, background: t.inputBg, color: t.text, fontSize: 13, fontFamily: "inherit" };
    if (p) return (
        <div data-move-proposal={p.by} style={{ marginTop: 10, padding: "12px 14px", borderRadius: 12, border: `1px solid ${t.primary}55`, background: `${t.primary}12`, display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ fontSize: 13, color: t.text, lineHeight: 1.5 }}>
                <b>{p.by === "client" ? "You proposed" : `${first} proposed`}</b> moving it to <b>{when(p.scheduled_at)}</b>{p.note ? ` — “${p.note}”` : ""}.
                <div style={{ fontSize: 12, color: t.textMuted }}>The current time stands until it is accepted.</div>
            </div>
            {/* Wraps in the narrow side column instead of running past its edge. */}
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {p.by === "client"
                    ? <button type="button" data-withdraw-move disabled={busy} onClick={() => run(() => apiWithdrawNewTime(id))} style={{ ...hubBtn("ghost", t), height: 38, flex: "1 1 140px", minWidth: 0, padding: "0 12px" }}>Withdraw</button>
                    : <>
                        <button type="button" data-accept-move disabled={busy} onClick={() => run(() => apiAcceptNewTime(id, p.id))} style={{ ...hubBtn("prim", t), height: 38, flex: "1 1 140px", minWidth: 0, padding: "0 12px", background: "var(--brand-solid)", color: "var(--on-brand)" }}>{busy ? "Saving…" : "Accept new time"}</button>
                        <button type="button" data-decline-move disabled={busy} onClick={() => run(() => apiDeclineNewTime(id))} style={{ ...hubBtn("ghost", t), height: 38, flex: "1 1 140px", minWidth: 0, padding: "0 12px" }}>Keep current time</button>
                    </>}
            </div>
            {error && <div role="alert" style={{ fontSize: 12, color: t.danger }}>{error}</div>}
        </div>
    );
    if (!open) return (
        <button type="button" data-propose-move onClick={() => setOpen(true)} style={{ ...hubBtn("ghost", t), marginTop: 10, height: 42, width: "100%" }}>Propose a new time</button>
    );
    return (
        <div data-propose-move-form style={{ marginTop: 10, padding: "12px 14px", borderRadius: 10, border: "1px solid " + t.border, background: t.inputBg, display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: t.text }}>Propose a new time</div>
            <div style={{ fontSize: 12, color: t.textMuted, lineHeight: 1.5 }}>{first} accepts or declines. Until then your appointment stays at its current time.</div>
            <div style={{ display: "flex", gap: 8 }}>
                <input type="date" aria-label="New date (PKT)" value={date} min={pktToday()} onChange={e => setDate(e.target.value)} style={field} />
                <select aria-label="New time (PKT)" value={time} onChange={e => setTime(e.target.value)} style={{ ...field, width: 110 }}>
                    {slots.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
            </div>
            <input aria-label="Reason (optional)" value={note} maxLength={300} onChange={e => setNote(e.target.value)} placeholder="Why (optional)" style={field} />
            {error && <div role="alert" style={{ fontSize: 12, color: t.danger }}>{error}</div>}
            <div style={{ display: "flex", gap: 8 }}>
                <button type="button" onClick={() => { setOpen(false); setError(null); }} style={{ ...hubBtn("ghost", t), height: 38, flex: 1 }}>Cancel</button>
                <button type="button" data-send-move disabled={busy || !date || isPktSlotPast(date, time)}
                    onClick={() => run(() => apiProposeNewTime(id, { scheduledAt: pktSlotToUtcISO(date, time), note: note.trim() }))}
                    style={{ ...hubBtn("prim", t), height: 38, flex: 1, background: "var(--brand-solid)", color: "var(--on-brand)", opacity: !date ? 0.6 : 1 }}>{busy ? "Sending…" : "Send proposal"}</button>
            </div>
        </div>
    );
}

function RescheduleAppointment({ appt, t, onReload, error, setError }) {
    const [open, setOpen] = useState(false);
    const [busy, setBusy] = useState(false);
    const [date, setDate] = useState("");
    const [time, setTime] = useState("");
    // The lawyer's FREE times on the chosen day, from the server: their
    // working hours minus other bookings, court hearings and diary entries.
    // This offered all 48 half-hours of the day, including 03:00 and times the
    // lawyer was already booked, which the client could only learn by failing.
    const [slots, setSlots] = useState({ state: "idle", times: [] });
    const currentDay = pktDayKey(appt.scheduled_at);
    const currentTime = pktHourMinute(appt.scheduled_at);

    useEffect(() => {
        if (!open || !date) { setSlots({ state: "idle", times: [] }); return undefined; }
        let off = false;
        setSlots({ state: "loading", times: [] });
        getBookableSlots(appt.lawyer_id, { from: date, duration_minutes: appt.duration_minutes })
            .then(({ data, error: err }) => {
                if (off) return;
                if (err || !data || !Array.isArray(data.days)) { setSlots({ state: "error", times: [] }); return; }
                if (!data.configured) {
                    // Only while hours are NOT enforced (`enforced === false`):
                    // then the lawyer can be asked for any time and confirms or
                    // declines, exactly as when booking. Enforced, or not said,
                    // there is no time to offer.
                    if (data.enforced === false) {
                        setSlots({ state: "ready", requestable: true, times: REQUEST_DAY_TIMES.filter(x => !isPktSlotPast(date, x)) });
                    } else {
                        setSlots({ state: "unconfigured", times: [] });
                    }
                    return;
                }
                const day = data.days.find(d => d.date === date) || data.days[0];
                setSlots({ state: "ready", times: (day?.slots || []).map(x => x.local_time).filter(Boolean) });
            })
            .catch(() => { if (!off) setSlots({ state: "error", times: [] }); });
        return () => { off = true; };
    }, [open, date, appt.lawyer_id, appt.duration_minutes]);

    // The request's own time stays listed on its own day (it is what the form
    // opens with), marked as the current one; it is not "free" because this
    // request is holding it.
    const keepsCurrent = date === currentDay && !!currentTime;
    const offered = slots.state === "ready" ? slots.times.filter(x => x !== currentTime || !keepsCurrent) : [];

    // A time that is not offered on the new day is cleared, not carried over.
    useEffect(() => {
        if (slots.state !== "ready" || !time) return;
        if (!offered.includes(time) && !(keepsCurrent && time === currentTime)) setTime("");
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [slots]);

    if (!CLIENT_RESCHEDULABLE.has(appt.status)) return null;

    const begin = () => {
        setError(appt.id, null);
        // Pre-filled from the appointment's own PKT clock face, so the client
        // edits the time they were shown rather than starting from blank.
        setDate(pktDayKey(appt.scheduled_at));
        setTime(pktHourMinute(appt.scheduled_at));
        setOpen(true);
    };

    const close = () => { setOpen(false); setError(appt.id, null); };

    const submit = async () => {
        // The handler is guarded as well as the button: a keyboard repeat or a
        // dispatched event does not go through `disabled`, and a double submit
        // is a second PATCH against a row the first one is already moving.
        if (busy) return;
        if (!date || !time) {
            setError(appt.id, "Choose both a date and a time.");
            return;
        }
        if (date === currentDay && time === currentTime) {
            setError(appt.id, "That is already the time of this request. Choose a different one.");
            return;
        }
        if (!offered.includes(time)) {
            setError(appt.id, "Choose one of the times your lawyer has free.");
            return;
        }
        if (isPktSlotPast(date, time)) {
            setError(appt.id, "That time has already passed. Choose a later one.");
            return;
        }
        const iso = pktSlotToUtcISO(date, time);
        if (!iso) {
            setError(appt.id, "That is not a valid date and time.");
            return;
        }

        setBusy(true);
        setError(appt.id, null);
        try {
            const { error: err, status } = await apiRescheduleAppointment(appt.id, {
                scheduled_at: iso,
                schedule_version: appt.schedule_version,
            });

            // A LOST REPLY LEAVES THE OUTCOME UNKNOWN.
            //
            // `apiFetch` resolves with status 0 when the request never
            // completed, which is the BROWSER's view — the server may have
            // moved the appointment and lost the connection while replying.
            // The card is never moved on this path; the appointment is read
            // back, and only a confirmed new time closes the form.
            if (status === 0) {
                const { data: verified, error: readErr } =
                    await apiGetAppointment(appt.id);
                const refreshed = onReload ? await onReload() : true;

                if (readErr || !verified || !verified.scheduled_at) {
                    setError(appt.id,
                        "The connection dropped and we could not confirm whether "
                        + "the time changed. Refresh to check before relying on it.");
                    return;
                }
                if (new Date(verified.scheduled_at).toISOString() === new Date(iso).toISOString()) {
                    setOpen(false);
                    if (!refreshed) {
                        setError(appt.id,
                            "Moved, but the list could not be refreshed. "
                            + "What you see may be out of date.");
                    }
                    return;
                }
                // The read shows the old time — which does NOT prove the move
                // failed, because the read races the original request. Left
                // open so the client can see and retry, described as unknown.
                setError(appt.id,
                    "The connection dropped, so we could not confirm this. It may "
                    + "still be completing — refresh in a moment, and try again "
                    + "only if it still shows the old time.");
                return;
            }

            if (err) {
                setError(appt.id, err.message || "Could not change this time.");
                // A 409 means the appointment moved underneath us — confirmed,
                // cancelled, or rescheduled in another tab. A 422 does not
                // prove the status either: the cutoff is checked before
                // anything else, so re-read on both.
                if ((status === 409 || status === 422) && onReload) await onReload();
                return;
            }

            setOpen(false);
            const refreshed = onReload ? await onReload() : true;
            if (!refreshed) {
                setError(appt.id,
                    "Moved, but the list could not be refreshed. "
                    + "What you see may be out of date.");
            }
        } catch {
            setError(appt.id,
                "Something went wrong and we could not confirm whether the time "
                + "changed. Refresh to check before relying on it.");
        } finally {
            setBusy(false);
        }
    };

    if (!open) {
        return (
            <div style={{ marginTop: 10 }}>
                <button
                    type="button"
                    data-reschedule-start
                    onClick={begin}
                    style={{
                        minHeight: 44, padding: "10px 16px", width: "100%", maxWidth: 280,
                        borderRadius: 10, cursor: "pointer",
                        border: "1px solid " + t.border, background: "transparent",
                        color: t.text, fontSize: 13, fontWeight: 700, fontFamily: "inherit",
                    }}>
                    Change time
                </button>
                {error && (
                    <div role="alert" style={{ marginTop: 8, fontSize: 12, color: t.danger }}>
                        {error}
                    </div>
                )}
            </div>
        );
    }

    // No `flex` here: the field sits in a COLUMN label, where a 150px flex
    // basis became its HEIGHT -- the date and time boxes stood ~200px tall
    // (2026-10-19). The label carries the row sizing instead.
    const field = {
        height: 42, width: "100%", boxSizing: "border-box", padding: "0 12px", borderRadius: 9,
        border: "1px solid " + t.border, background: t.inputBg,
        color: t.text, fontSize: 13, fontFamily: "inherit",
    };

    return (
        <div style={{
            marginTop: 10, padding: "12px 14px", borderRadius: 10,
            border: "1px solid " + t.border, background: t.inputBg,
        }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: t.text, marginBottom: 6 }}>
                Choose a new time
            </div>
            <div style={{ fontSize: 12, color: t.textMuted, lineHeight: 1.5, marginBottom: 10 }}>
                Times are Pakistan Standard Time, on the hour or half hour. Your
                lawyer has not accepted this request yet, so moving it does not
                need their approval — but it can only be changed up to{" "}
                {CANCEL_CUTOFF_HOURS} hours before the current time.
            </div>
            {error && (
                <div role="alert" style={{ marginBottom: 10, fontSize: 12, color: t.danger, fontWeight: 600 }}>
                    {error}
                </div>
            )}
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
                <label style={{ flex: "1 1 150px", display: "flex", flexDirection: "column", gap: 4 }}>
                    <span style={{ fontSize: 11, color: t.textMuted, fontWeight: 600 }}>Date (PKT)</span>
                    <input type="date" value={date} min={pktToday()}
                        onChange={e => setDate(e.target.value)}
                        disabled={busy} style={field} />
                </label>
                <label style={{ flex: "1 1 150px", display: "flex", flexDirection: "column", gap: 4 }}>
                    <span style={{ fontSize: 11, color: t.textMuted, fontWeight: 600 }}>Time (PKT)</span>
                    <select value={time} onChange={e => setTime(e.target.value)}
                        disabled={busy || slots.state === "loading"} style={field}>
                        <option value="">{slots.state === "loading" ? "Loading…" : "Select…"}</option>
                        {keepsCurrent && <option value={currentTime}>{currentTime} (current)</option>}
                        {offered.map(slot => (
                            <option key={slot} value={slot}>{slot}</option>
                        ))}
                    </select>
                </label>
            </div>
            {slots.state === "ready" && slots.requestable && (
                <div style={{ marginBottom: 10, fontSize: 12, color: t.textMuted }}>This lawyer has not set their working hours — pick a time that suits you and they will confirm or decline.</div>
            )}
            {slots.state === "ready" && offered.length === 0 && (
                <div style={{ marginBottom: 10, fontSize: 12, color: t.textMuted }}>No free times on this day. Try another date.</div>
            )}
            {slots.state === "unconfigured" && (
                <div style={{ marginBottom: 10, fontSize: 12, color: t.textMuted }}>This lawyer has not set their working hours, so a new time cannot be chosen here. You can cancel this request and book again.</div>
            )}
            {slots.state === "error" && (
                <div role="alert" style={{ marginBottom: 10, fontSize: 12, color: t.danger }}>Could not load this lawyer's free times. Change the date to try again.</div>
            )}
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button
                    type="button"
                    onClick={submit}
                    disabled={busy}
                    aria-busy={busy}
                    style={{
                        minHeight: 44, padding: "10px 16px", flex: "1 1 160px",
                        // The client theme's brand gradient, not a fixed mint (2026-10-19).
                        borderRadius: 10, border: "none", background: "var(--brand-solid)",
                        color: "var(--on-brand)", fontSize: 13, fontWeight: 700, fontFamily: "inherit",
                        cursor: busy ? "not-allowed" : "pointer", opacity: busy ? 0.6 : 1,
                    }}>
                    {busy ? "Changing…" : "Confirm new time"}
                </button>
                <button
                    type="button"
                    onClick={close}
                    disabled={busy}
                    style={{
                        minHeight: 44, padding: "10px 16px", flex: "1 1 160px",
                        borderRadius: 10, border: "1px solid " + t.border,
                        background: "transparent", color: t.text,
                        fontSize: 13, fontWeight: 700, fontFamily: "inherit",
                        cursor: busy ? "not-allowed" : "pointer", opacity: busy ? 0.6 : 1,
                    }}>
                    Keep current time
                </button>
            </div>
        </div>
    );
}

// Who cancelled, in words the client reads rather than the value we store.
//
// `cancelled_by` holds a ROLE — "client", "lawyer", "admin". Rendering it raw
// would show a client the word "client" as though it named someone else, and
// legacy rows are worse: an older seeder wrote the client's `_id` into this
// field, so an unrecognised value is not merely unknown, it is actively
// misleading if echoed.
//
// Anything not in this map is treated as UNKNOWN and the actor is simply not
// named. Inventing one — "cancelled by your lawyer" when the row does not say
// so — would be a claim about a person, in a record of a legal engagement.
const CANCELLED_BY_LABEL = {
    client: "You cancelled this appointment.",
    lawyer: "Your lawyer cancelled this appointment.",
    admin: "This appointment was cancelled by Attorney.AI support.",
};

// A REQUEST turned down or withdrawn before it was confirmed is not a
// cancelled appointment. The server records the status a cancellation ended
// (`cancelled_from`, 2026-10-12); older rows lack it and keep the words above.
const isDeclinedRequest = a => a.status === "cancelled" && a.cancelled_from === "pending" && a.cancelled_by === "lawyer";
function cancelledWho(appt) {
    if (appt.cancelled_from === "pending") {
        if (appt.cancelled_by === "lawyer") return "Your lawyer declined this request.";
        if (appt.cancelled_by === "client") return "You withdrew this request.";
    }
    return CANCELLED_BY_LABEL[appt.cancelled_by] || null;
}

// Which appointments a client may report, and which report each one supports.
//
// Mirrors the server's rule rather than inventing a looser one: the category
// is a claim about what went wrong, and "the lawyer wrongly marked me absent"
// cannot be said about an appointment nobody has recorded an outcome for. A
// control offered where the server would refuse is a button that always fails.
const OUTCOME_GRACE_HOURS = 2;

function reportableCategory(appt) {
    if (appt.status === "no_show") return "incorrect_no_show";
    if (appt.status === "confirmed" && appt.end_at) {
        const ended = new Date(appt.end_at);
        if (Number.isFinite(ended.getTime())
            && ended.getTime() < Date.now() - OUTCOME_GRACE_HOURS * 3600e3) {
            return "outcome_not_recorded";
        }
    }
    return null;
}

const CATEGORY_PROMPT = {
    incorrect_no_show:
        "Tell us what happened. Your lawyer recorded that you did not attend.",
    outcome_not_recorded:
        "Tell us what happened. This consultation has finished and no outcome "
        + "has been recorded.",
};

const MAX_STATEMENT = 2000;

/** Report that an appointment's record is wrong.
 *
 * WHAT THIS DOES NOT DO, said plainly to the client before they write
 * anything: filing a report does not change the appointment. Letting someone
 * believe their record had been corrected — when in fact a support officer has
 * yet to look at it — would be worse than offering nothing, because they would
 * stop pursuing it.
 *
 * FIVE OUTCOMES ARE KEPT APART. Submitting, submitted, an identical retry
 * (which returns the report already filed), a conflicting retry, and a failed
 * request. `apiFetch` RESOLVES on failure, so an unchecked result would turn a
 * network error into a silent success — the client would believe a complaint
 * had been filed that nobody ever received.
 */
/* A short case summary the client CHOOSES to share (2026-10-19,
 * APPOINTMENT_FLOW_PLAN.md). Nothing is shared until they press Share; they
 * see and edit the exact text first, identifiers come pre-hidden, and what the
 * lawyer gets is that snapshot. Separate from the documents below. */
function ApptSummaryShare({ appt, t, first }) {
    const id = appt._id || appt.id;
    const [state, setState] = useState(null);         // { shared, text, shared_at }
    const [editing, setEditing] = useState(null);     // text being prepared
    const [hidden, setHidden] = useState(0);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);
    const [confirmStop, setConfirmStop] = useState(false);
    useEffect(() => {
        let alive = true;
        apiReadSharedSummary(id).then(({ data }) => { if (alive) setState(data || { shared: false }); });
        return () => { alive = false; };
    }, [id]);
    const prepare = async () => {
        setBusy(true); setError(null);
        const { data, error: err } = await apiGetSummaryDraft(id);
        setBusy(false);
        if (err) { setError(err.message || "Could not prepare a summary."); return; }
        setEditing(state?.shared ? state.text : (data?.text || "")); setHidden(state?.shared ? 0 : (data?.hidden || 0));
    };
    const share = async () => {
        if (!editing?.trim()) return;
        setBusy(true); setError(null);
        const { data, error: err } = await apiShareSummary(id, editing.trim());
        setBusy(false);
        if (err) { setError(err.message || "Could not share the summary."); return; }
        setState(data); setEditing(null);
    };
    const stop = async () => {
        setBusy(true); setError(null);
        const { error: err } = await apiRevokeSummary(id);
        setBusy(false);
        if (err) { setError(err.message || "Could not stop sharing."); return; }
        setState({ shared: false }); setConfirmStop(false);
    };
    const box = { marginTop: 14, paddingTop: 14, borderTop: `1px solid ${t.border}` };
    const small = { ...hubBtn("ghost", t), height: 34, padding: "0 12px", fontSize: 12.5 };
    if (state === null) return null;
    return (
        <div data-summary-share style={box}>
            <div style={{ fontSize: 14, fontWeight: 700, color: t.text }}>Case summary for {first}</div>
            {editing !== null ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
                    <div style={{ fontSize: 12.5, color: t.textMuted, lineHeight: 1.5 }}>
                        This is exactly what {first} will see. Edit it as you like.{hidden ? ` We hid ${hidden} identifier${hidden === 1 ? "" : "s"} (CNIC, phone or email).` : ""} Check that your home address isn't in it.
                    </div>
                    <textarea aria-label="Summary to share" data-summary-text rows={6} maxLength={3000} value={editing} onChange={e => setEditing(e.target.value)}
                        style={{ padding: 10, borderRadius: 10, border: `1px solid ${t.border}`, background: t.inputBg, color: t.text, fontSize: 13, fontFamily: "inherit", lineHeight: 1.5, resize: "vertical" }} />
                    <div style={{ display: "flex", gap: 8 }}>
                        <button type="button" onClick={() => setEditing(null)} disabled={busy} style={small}>Cancel</button>
                        <button type="button" data-summary-send onClick={share} disabled={busy || !editing.trim()} style={{ ...small, borderColor: t.primary, color: t.primary }}>{busy ? "Sharing…" : `Share with ${first}`}</button>
                    </div>
                </div>
            ) : state.shared ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
                    <div style={{ fontSize: 12.5, color: t.primary }}>Shared {state.shared_at ? formatPkt(state.shared_at, { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }) : ""} — {first} can read it.</div>
                    <div data-summary-shared style={{ fontSize: 13, color: t.text, whiteSpace: "pre-wrap", padding: "10px 12px", borderRadius: 10, background: t.inputBg, border: `1px solid ${t.border}`, maxHeight: 180, overflowY: "auto" }}>{state.text}</div>
                    {confirmStop ? (
                        <div role="alert" style={{ fontSize: 12.5, color: t.text, lineHeight: 1.5 }}>
                            {first} loses access in the app right away. If they have already read it, that copy can't be taken back.
                            <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
                                <button type="button" onClick={() => setConfirmStop(false)} style={small}>Keep sharing</button>
                                <button type="button" data-summary-stop-confirm onClick={stop} disabled={busy} style={{ ...small, color: t.danger }}>{busy ? "Stopping…" : "Stop sharing"}</button>
                            </div>
                        </div>
                    ) : (
                        <div style={{ display: "flex", gap: 8 }}>
                            <button type="button" onClick={prepare} disabled={busy} style={small}>Edit</button>
                            <button type="button" data-summary-stop onClick={() => setConfirmStop(true)} style={{ ...small, color: t.danger }}>Stop sharing</button>
                        </div>
                    )}
                </div>
            ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 4 }}>
                    <div style={{ fontSize: 12.5, color: t.textMuted, lineHeight: 1.5 }}>Help {first} prepare: share a short summary of your matter. Nothing is shared until you press Share, and you can stop sharing any time.</div>
                    <button type="button" data-summary-prepare onClick={prepare} disabled={busy} style={{ ...hubBtn("ghost", t), alignSelf: "flex-start" }}>{busy ? "Preparing…" : "Prepare a summary"}</button>
                </div>
            )}
            {error && <div role="alert" style={{ marginTop: 6, fontSize: 12.5, color: t.danger }}>{error}</div>}
        </div>
    );
}

/* Documents for this appointment (2026-10-19), in place of a "Share a document"
 * link that only went to /documents. The server decides who sees what: while
 * the request is pending the lawyer sees only the name and note (a file opens
 * for them only if the client chose to show it early); once accepted, all of
 * them; after a decline, cancel or expiry, nothing. */
function ApptFiles({ appt, t }) {
    const id = appt._id || appt.id;
    const editable = appt.status === "pending" || appt.status === "confirmed";
    const [rows, setRows] = useState(null);
    const [note, setNote] = useState("");
    const [early, setEarly] = useState(false);
    const [busy, setBusy] = useState(false);
    const [msg, setMsg] = useState(null);          // { kind: "ok" | "err", text }
    const input = useRef(null);

    const load = useCallback(async () => {
        const { data, error } = await apiListAppointmentFiles(id);
        setRows(error ? [] : (data?.items || []));
    }, [id]);
    useEffect(() => { load(); }, [load]);

    const pick = async (file) => {
        if (!file || busy) return;
        if (file.size > 10 * 1024 * 1024) { setMsg({ kind: "err", text: "The file is larger than 10 MB." }); return; }
        setBusy(true); setMsg(null);
        const { error } = await apiUploadAppointmentFile(id, file, { note: note.trim(), shareBeforeAccept: early });
        setBusy(false);
        if (error) { setMsg({ kind: "err", text: error.message || "Could not upload the file." }); return; }
        setNote(""); setEarly(false);
        setMsg({ kind: "ok", text: appt.status === "pending" && !early
            ? "File uploaded privately. Lawyer can view it after accepting."
            : "File uploaded. Your lawyer can view it." });
        load();
    };
    const open = async (row) => {
        const { data, error } = await apiOpenAppointmentFile(id, row.id);
        if (error) { setMsg({ kind: "err", text: error }); return; }
        window.open(data, "_blank", "noopener");
        setTimeout(() => URL.revokeObjectURL(data), 60000);
    };
    const remove = async (row) => {
        const { error } = await apiDeleteAppointmentFile(id, row.id);
        if (error) { setMsg({ kind: "err", text: error.message || "Could not remove the file." }); return; }
        load();
    };

    const full = (rows?.length || 0) >= 5;
    const kb = n => (n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);
    return (
        <div data-appt-files style={{ marginTop: 14, paddingTop: 14, borderTop: `1px solid ${t.border}` }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: t.text }}>Documents for this appointment</div>
            <div style={{ fontSize: 12.5, color: t.textMuted, marginTop: 2, lineHeight: 1.5 }}>
                PDF, PNG or JPEG, up to 10 MB, at most 5 files. Private: your lawyer sees them only after accepting — unless you choose to show one earlier.
            </div>
            {rows?.length > 0 && (
                <ul style={{ listStyle: "none", margin: "10px 0 0", padding: 0, display: "flex", flexDirection: "column", gap: 8 }}>
                    {rows.map(r => (
                        <li key={r.id} data-appt-file={r.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 12px", borderRadius: 12, background: t.inputBg, border: `1px solid ${t.border}` }}>
                            <span style={{ color: t.textMuted, display: "flex" }}><DtIcon name="file" size={17} /></span>
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontSize: 13.5, fontWeight: 600, color: t.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.name}</div>
                                <div style={{ fontSize: 11.5, color: t.textMuted }}>
                                    {kb(r.size)} · {r.lawyer_can_open ? "Your lawyer can view it" : "Private until your lawyer accepts"}
                                    {r.note ? ` · “${r.note}”` : ""}
                                </div>
                            </div>
                            <button type="button" className="dt-ghost" onClick={() => open(r)} style={{ ...hubBtn("ghost", t), height: 32, padding: "0 12px", fontSize: 12.5 }}>Open</button>
                            {editable && <button type="button" className="dt-ghost" aria-label={`Remove ${r.name}`} onClick={() => remove(r)} style={{ ...hubBtn("ghost", t), height: 32, padding: "0 12px", fontSize: 12.5, color: t.danger }}>Remove</button>}
                        </li>
                    ))}
                </ul>
            )}
            {editable && !full && (
                <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 12 }}>
                    <input aria-label="Note for your lawyer (optional)" value={note} maxLength={300} onChange={e => setNote(e.target.value)}
                        placeholder="Optional note, e.g. the rent agreement we discussed"
                        style={{ height: 40, padding: "0 12px", borderRadius: 10, border: `1px solid ${t.border}`, background: t.inputBg, color: t.text, fontSize: 13, fontFamily: "inherit", outline: "none" }} />
                    {appt.status === "pending" && (
                        <label style={{ display: "flex", gap: 8, alignItems: "flex-start", fontSize: 12.5, color: t.textMuted, cursor: "pointer", lineHeight: 1.45 }}>
                            <input type="checkbox" checked={early} onChange={e => setEarly(e.target.checked)} style={{ marginTop: 2 }} />
                            <span>Show this file to the lawyer before they accept
                                {early && <span style={{ display: "block", color: t.warn || "#E8B04A" }}>They can open it even if they later decline.</span>}
                            </span>
                        </label>
                    )}
                    <input ref={input} type="file" accept="application/pdf,image/png,image/jpeg" hidden
                        onChange={e => { const f = e.target.files?.[0]; e.target.value = ""; pick(f); }} />
                    <button type="button" className="dt-ghost" data-appt-upload disabled={busy} onClick={() => input.current?.click()}
                        style={{ ...hubBtn("ghost", t), alignSelf: "flex-start", opacity: busy ? 0.6 : 1 }}>
                        <DtIcon name="file" size={17} /> {busy ? "Uploading…" : "Upload a document"}
                    </button>
                </div>
            )}
            {msg && <div role={msg.kind === "err" ? "alert" : "status"} style={{ marginTop: 8, fontSize: 12.5, color: msg.kind === "err" ? t.danger : t.primary }}>{msg.text}</div>}
        </div>
    );
}

function ReportIssue({ appt, t }) {
    const category = reportableCategory(appt);
    const [open, setOpen] = useState(false);
    const [statement, setStatement] = useState("");
    const [state, setState] = useState("idle");   // idle|sending|done|conflict|error
    const [message, setMessage] = useState("");
    const [filed, setFiled] = useState(null);

    // Reports already filed about this appointment, so a client who returns
    // sees the outcome rather than an invitation to complain again.
    useEffect(() => {
        let cancelled = false;
        listAppointmentDisputes(appt.id).then(({ data, error }) => {
            if (cancelled || error || !Array.isArray(data)) return;
            setFiled(data[data.length - 1] || null);
        });
        return () => { cancelled = true; };
    }, [appt.id]);

    const submit = async () => {
        const text = statement.trim();
        if (!text) {
            setState("error");
            setMessage("Please describe what happened before sending.");
            return;
        }
        setState("sending");
        setMessage("");
        const { data, error, status } = await openAppointmentDispute(appt.id, {
            category, statement: text,
        });
        if (error || !data) {
            if (status === 409) {
                // A report already exists and says something different. Not an
                // error to retry — support has the earlier one.
                setState("conflict");
                setMessage(error?.message
                    || "You already have an open report for this appointment.");
                return;
            }
            // A HUMAN SENTENCE, not the transport's. "network down" or a
            // driver string tells a client nothing they can act on, and this
            // is the surface where somebody is trying to report that their
            // record is wrong.
            setState("error");
            setMessage("Your report could not be sent. Please try again.");
            return;
        }
        setFiled(data);
        setState("done");
        setOpen(false);
    };

    // An existing report is shown instead of the form — including its outcome
    // once support has decided. The PUBLIC explanation only; the private note
    // never leaves the server.
    if (filed) {
        const decided = filed.status !== "open";
        return (
            <div style={{
                marginTop: 10, padding: "10px 12px", borderRadius: 8,
                background: t.cardHi, border: `1px solid ${t.border}`,
            }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: t.text }}>
                    {decided ? "Your report has been reviewed."
                             : "Your report is with support."}
                </div>
                <div style={{ fontSize: 12, color: t.textMuted, marginTop: 4 }}>
                    {decided
                        ? (filed.resolution_explanation || "Support has decided this report.")
                        : "Support will review it. The appointment is unchanged until then."}
                </div>
            </div>
        );
    }

    if (!category) return null;

    if (!open) {
        return (
            <div style={{ marginTop: 10 }}>
                <button type="button" onClick={() => setOpen(true)} style={{
                    minHeight: 40, padding: "9px 14px", borderRadius: 8,
                    border: `1px solid ${t.border}`, background: "transparent",
                    color: t.textMuted, fontSize: 12, fontWeight: 700,
                    cursor: "pointer", fontFamily: "inherit",
                }}>Report an issue</button>
                {state === "done" && (
                    <span role="status" style={{ fontSize: 12, color: t.success, marginLeft: 10 }}>
                        Report sent.
                    </span>
                )}
            </div>
        );
    }

    const tooLong = statement.length > MAX_STATEMENT;

    return (
        <div style={{
            marginTop: 10, padding: "12px 14px", borderRadius: 10,
            background: t.cardHi, border: `1px solid ${t.border}`,
        }}>
            <label htmlFor={`report-${appt.id}`}
                style={{ display: "block", fontSize: 12, fontWeight: 700, color: t.text }}>
                {CATEGORY_PROMPT[category]}
            </label>

            {/* SAID BEFORE THEY WRITE ANYTHING. A client who believed the
                record had been corrected would stop pursuing it. */}
            <div style={{ fontSize: 11, color: t.textMuted, margin: "6px 0 8px" }}>
                Sending this does not change the appointment. A member of the
                Attorney.AI support team will review it and decide.
            </div>

            <textarea
                id={`report-${appt.id}`}
                value={statement}
                maxLength={MAX_STATEMENT + 100}
                onChange={e => setStatement(e.target.value)}
                aria-invalid={tooLong || undefined}
                aria-describedby={`report-help-${appt.id}`}
                rows={4}
                style={{
                    width: "100%", boxSizing: "border-box", padding: "8px 10px",
                    borderRadius: 8, border: `1px solid ${tooLong ? t.danger : t.border}`,
                    background: t.inputBg, color: t.text, fontSize: 12,
                    fontFamily: "inherit", resize: "vertical",
                }} />

            <div id={`report-help-${appt.id}`}
                style={{ fontSize: 11, color: tooLong ? t.danger : t.textFaint, marginTop: 4 }}>
                {statement.length} of {MAX_STATEMENT} characters
                {tooLong ? " — too long to send." : ""}
            </div>

            {(state === "error" || state === "conflict") && (
                <div role="alert" style={{ fontSize: 12, color: t.danger, marginTop: 8 }}>
                    {message}
                </div>
            )}

            <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                <button type="button" onClick={submit}
                    disabled={state === "sending" || tooLong}
                    aria-busy={state === "sending" || undefined}
                    style={{
                        minHeight: 40, padding: "9px 16px", borderRadius: 8,
                        border: `1px solid ${t.primary}`, background: t.primaryGlow,
                        color: t.primary, fontSize: 12, fontWeight: 700,
                        cursor: state === "sending" ? "wait" : "pointer",
                        opacity: state === "sending" || tooLong ? 0.6 : 1,
                        fontFamily: "inherit",
                    }}>
                    {state === "sending" ? "Sending…" : "Send report"}
                </button>
                <button type="button" onClick={() => { setOpen(false); setState("idle"); }}
                    style={{
                        minHeight: 40, padding: "9px 16px", borderRadius: 8,
                        border: `1px solid ${t.border}`, background: "transparent",
                        color: t.textMuted, fontSize: 12, fontWeight: 700,
                        cursor: "pointer", fontFamily: "inherit",
                    }}>Cancel</button>
            </div>
        </div>
    );
}

/** Why an expired request ended, for the client whose request it was.
 *
 * A badge reading "Expired" on its own invites the wrong inference — that the
 * client missed something, or that the lawyer refused. Neither happened: the
 * request was never answered and stopped holding its slot.
 *
 * It does NOT say the original time is free again. A request can lapse at its
 * own start time, so for some of these the slot is already in the past, and
 * "book it again" would be pointing at an hour that no longer exists. What is
 * true for all of them is that a new request can be made.
 */
function ExpiryDetail({ appt, t }) {
    if (appt.status !== "expired") return null;

    return (
        <div style={{
            marginTop: 10, padding: "10px 12px", borderRadius: 8,
            background: t.cardHi, border: `1px solid ${t.border}`,
        }}>
            <div style={{ fontSize: 12, color: t.text, fontWeight: 600 }}>
                This request expired before it was confirmed.
            </div>
            <div style={{ fontSize: 12, color: t.textMuted, marginTop: 4 }}>
                Your lawyer did not respond in time, so the request was closed.
                Nothing was charged. You can book a new time.
            </div>
        </div>
    );
}

/** The cancellation details, where the row actually has them.
 *
 * Renders nothing at all when both fields are missing — which is what a legacy
 * cancellation looks like, and the honest thing to show for one. A heading with
 * an empty body tells the client their record is incomplete without telling
 * them anything.
 */
function CancellationDetail({ appt, t }) {
    if (appt.status !== "cancelled") return null;

    const who = cancelledWho(appt);
    const reason = (appt.cancel_reason || "").trim();
    if (!who && !reason) return null;

    return (
        <div style={{
            marginTop: 10, padding: "10px 12px", borderRadius: 8,
            background: `${t.danger}0e`, border: `1px solid ${t.danger}33`,
        }}>
            {who && (
                <div style={{ fontSize: 12, color: t.text, fontWeight: 600 }}>
                    {who}
                </div>
            )}
            {reason && (
                <div style={{ fontSize: 12, color: t.textMuted, marginTop: who ? 4 : 0 }}>
                    <span style={{ fontWeight: 600, color: t.textDim }}>Reason</span>
                    {" · "}{reason}
                </div>
            )}
        </div>
    );
}

/** Client-side cancellation for one appointment.
 *
 * `PageAppointments` was read-only, so `cancelled_by: "client"` could never
 * occur — the backend path existed and nothing could reach it.
 *
 * Deliberately NOT optimistic. On success it re-reads the list from the server
 * rather than writing "cancelled" into local state: the server owns the
 * outcome, and a local status would show a state the database may not hold —
 * most obviously when the request is refused, but also when the lawyer
 * cancelled first and the real row says `cancelled_by: "lawyer"`.
 */
/* AN APPOINTMENT'S MESSAGES (2026-10-12), one entry for both renderers -- the
 * Appointments page and Tracking's cards -- so they cannot drift. Whether the
 * thread can be written is the SERVER's answer, shown by AppointmentThread;
 * here only: a pending request has no thread yet, anything else opens it. */
const clientThreadPalette = (t) => ({
    text: t.text, muted: t.textMuted, faint: t.textFaint, border: t.border, surface: t.card,
    input: t.inputBg, primary: t.primary, onPrimary: "#06211a", danger: t.danger, mine: `${t.primary}22`,
});
function ApptMessages({ appt, t, open, onOpenChange }) {
    const name = appt.lawyer_name || "your lawyer";
    const first = String(name).split(" ")[0];
    if (appt.status === "pending") {
        return (
            <div data-thread-pending style={{ fontSize: 12.5, color: t.textMuted, lineHeight: 1.5 }}>
                Messages with {first} open once they confirm this request.
            </div>
        );
    }
    if (!open) {
        return (
            <button type="button" data-open-thread onClick={() => onOpenChange(true)}
                style={{ alignSelf: "flex-start", minHeight: 40, padding: "0 16px", borderRadius: 10, cursor: "pointer",
                    border: `1px solid ${t.border}`, background: "transparent", color: t.text,
                    fontSize: 13, fontWeight: 700, fontFamily: "inherit" }}>
                {appt.status === "confirmed" ? `Message ${first}` : "View messages"}
            </button>
        );
    }
    return (
        <AppointmentThread appointmentId={appt.id} palette={clientThreadPalette(t)} counterpart={first}
            title={`Messages with ${name}`} onClose={() => onOpenChange(false)} />
    );
}

function CancelAppointment({ appt, t, onReload, error, setError, onMessage = null }) {
    const [confirming, setConfirming] = useState(false);
    const [busy, setBusy] = useState(false);
    // `error` is NOT local state. A reload re-creates the page component, which
    // unmounts this subtree and destroys anything it owned — so an error raised
    // just before a reload would vanish exactly when it is most needed, which
    // is how a 409 came to change the card from Pending to Completed with no
    // explanation at all. It is held by the page, which survives.

    if (!CLIENT_CANCELLABLE.has(appt.status)) {
        // The action is gone, but an explanation of why may still be owed.
        //
        // A 409 reloads the list, and the reloaded appointment is terminal — so
        // returning null here removed the message along with the button, and
        // the client watched the card silently change from Pending to Completed
        // with nothing saying their cancellation had been refused or why.
        return error ? (
            <div role="alert" style={{ marginTop: 12, fontSize: 12, color: t.danger, fontWeight: 600 }}>
                {error}
            </div>
        ) : null;
    }

    const run = async () => {
        // Guard the handler as well as the button. `disabled` stops a second
        // click, but a keyboard repeat or an event dispatched directly does not
        // go through the same path, and a double submit here is a second PATCH
        // against an appointment the first one is already cancelling.
        if (busy) return;
        setBusy(true);
        setError(appt.id, null);
        try {
            const { error: err, status } = await apiCancelAppointment(appt.id, null);

            // STATUS 0 MEANS THE OUTCOME IS UNKNOWN, NOT THAT NOTHING HAPPENED.
            //
            // `apiFetch` returns this when the request never completed — but
            // "never completed" is from the BROWSER's side. The server may have
            // received the PATCH, committed the cancellation and then lost the
            // connection while replying. Saying "the appointment was not
            // changed", as this used to, asserts the one thing nobody here
            // knows, and a client who believes it turns up to a consultation
            // that was cancelled.
            //
            // So the client asks. A read is safe to retry in a way the PATCH is
            // not.
            if (status === 0) {
                const { data: verified, error: readErr } =
                    await apiGetAppointment(appt.id);

                if (readErr || !verified || !verified.status) {
                    // Still blind. The honest answer is that we do not know,
                    // and the refresh control is how the client finds out.
                    setError(appt.id,
                        "The connection dropped and we could not confirm whether "
                        + "this was cancelled. Refresh to check before relying on it.");
                    return;
                }

                // The read narrows the answer. It does not always settle it.
                const refreshed = onReload ? await onReload() : true;

                if (verified.status === "cancelled") {
                    // THE ONLY CONFIRMED SUCCESS. Not "any terminal status":
                    // this branch used to accept completed and no_show as
                    // proof of cancellation, so an appointment the lawyer had
                    // marked completed was reported to the client as
                    // "Cancelled, but the list could not be refreshed" — a
                    // cancellation that never happened, described as done.
                    setConfirming(false);
                    if (!refreshed) {
                        setError(appt.id,
                            "Cancelled, but the list could not be refreshed. "
                            + "What you see may be out of date.");
                    }
                    return;
                }

                if (!CLIENT_CANCELLABLE.has(verified.status)) {
                    // Terminal, but not by cancellation. The appointment ended
                    // some other way — completed, or recorded as a no-show —
                    // and the client's request is not what did it. Naming the
                    // real status matters: "cancelled" and "completed" have
                    // opposite consequences for whether they owe a fee.
                    setError(appt.id,
                        "This was NOT cancelled — it is now "
                        + statusWord(verified.status) + "."
                        + (refreshed ? "" : " The list could not be refreshed, so"
                           + " what you see may be out of date."));
                    return;
                }

                // STILL PENDING OR CONFIRMED ON THIS READ, WHICH IS NOT PROOF
                // THAT THE CANCELLATION FAILED.
                //
                // The lost reply means the PATCH's fate is unknown, and an
                // immediate read races it: the server may be committing the
                // cancellation at the moment this read returns the old row.
                // Saying "it is still pending, please try again" — as this did
                // — turns one unknown into a false certainty and invites a
                // second cancellation of something already cancelling.
                //
                // The wording is deliberately true under both outcomes, so it
                // does not contradict the card if the refresh above has already
                // pulled in a cancelled row.
                setError(appt.id,
                    "The connection dropped, so we could not confirm this. It may "
                    + "still be completing — refresh in a moment, and try again "
                    + "only if it still shows as "
                    + statusWord(verified.status) + ".");
                return;
            }

            if (err) {
                setError(appt.id, err.message || "Could not cancel this appointment.");
                // REFRESH ON 422 AS WELL AS 409.
                //
                // The two-hour cutoff is checked BEFORE the status transition,
                // so a 422 says only that this request was refused — not that
                // the appointment is still pending or confirmed. The lawyer may
                // have cancelled it seconds earlier. Re-reading costs one
                // request and is the difference between showing the client
                // their appointment and showing them a guess.
                //
                // The refusal message survives because it is held by the page,
                // not by this component, which the reload re-creates.
                if ((status === 409 || status === 422) && onReload) await onReload();
                return;
            }

            setConfirming(false);
            // A cancellation that committed but could not be re-read leaves a
            // PENDING card on screen. It must not be presented as current.
            const refreshed = onReload ? await onReload() : true;
            if (!refreshed) {
                setError(appt.id,
                    "Cancelled, but the list could not be refreshed. "
                    + "What you see may be out of date.");
            }
        } catch {
            // The client resolves rather than throws for network failures, so
            // this is only reached if the client itself breaks. The outcome is
            // just as unknown, and it is described that way.
            setError(appt.id,
                "Something went wrong and we could not confirm whether this was "
                + "cancelled. Refresh to check before relying on it.");
        } finally {
            setBusy(false);
        }
    };

    // A CONFIRMED appointment can be cancelled only up to the cutoff before it
    // starts; the server refuses later. A pending request may be withdrawn at
    // any time, so it is never blocked here.
    const tooLate = appt.status === "confirmed" && appt.scheduled_at
        && Date.now() >= new Date(appt.scheduled_at).getTime() - CANCEL_CUTOFF_HOURS * 3600e3;
    if (!confirming && tooLate) {
        return (
            <div style={{ marginTop: 12 }} data-cancel-closed>
                <button type="button" disabled
                    style={{
                        minHeight: 44, padding: "10px 16px", width: "100%", maxWidth: 280,
                        borderRadius: 10, cursor: "not-allowed", opacity: 0.55,
                        border: "1px solid " + t.border, background: "transparent",
                        color: t.textMuted, fontSize: 13, fontWeight: 700, fontFamily: "inherit",
                    }}>
                    Cancel appointment
                </button>
                <div style={{ marginTop: 8, fontSize: 12, color: t.textMuted, lineHeight: 1.5 }}>
                    It can no longer be cancelled: confirmed appointments close for
                    changes {CANCEL_CUTOFF_HOURS} hours before they start.
                    {onMessage ? " If you cannot make it, tell your lawyer." : ""}
                </div>
                {onMessage && (
                    <button type="button" data-cutoff-message onClick={onMessage}
                        style={{ marginTop: 8, minHeight: 40, padding: "0 16px", borderRadius: 10, cursor: "pointer",
                            border: `1px solid ${t.primary}66`, background: "transparent", color: t.primary,
                            fontSize: 13, fontWeight: 700, fontFamily: "inherit" }}>
                        Message lawyer
                    </button>
                )}
                {error && (
                    <div role="alert" style={{ marginTop: 8, fontSize: 12, color: t.danger }}>
                        {error}
                    </div>
                )}
            </div>
        );
    }

    if (!confirming) {
        return (
            <div style={{ marginTop: 12 }}>
                <button
                    type="button"
                    data-cancel-start
                    onClick={() => { setError(appt.id, null); setConfirming(true); }}
                    style={{
                        // 44px min target, full width up to a cap: this is a
                        // destructive action reached with a thumb.
                        minHeight: 44, padding: "10px 16px", width: "100%", maxWidth: 280,
                        borderRadius: 10, cursor: "pointer",
                        border: "1px solid " + t.danger + "55", background: "transparent",
                        color: t.danger, fontSize: 13, fontWeight: 700, fontFamily: "inherit",
                    }}>
                    Cancel appointment
                </button>
                {error && (
                    <div role="alert" style={{ marginTop: 8, fontSize: 12, color: t.danger }}>
                        {error}
                    </div>
                )}
            </div>
        );
    }

    return (
        <div style={{
            marginTop: 12, padding: "12px 14px", borderRadius: 10,
            border: "1px solid " + t.danger + "44", background: t.danger + "0e",
        }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: t.text, marginBottom: 6 }}>
                Cancel this appointment?
            </div>
            <div style={{ fontSize: 12, color: t.textMuted, lineHeight: 1.5, marginBottom: 10 }}>
                This cannot be undone — rebooking means choosing a new slot.
                {" "}Appointments can only be cancelled at least {CANCEL_CUTOFF_HOURS} hours
                before the scheduled time; after that, contact your lawyer directly.
            </div>
            {error && (
                <div role="alert" style={{ marginBottom: 10, fontSize: 12, color: t.danger, fontWeight: 600 }}>
                    {error}
                </div>
            )}
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button
                    type="button"
                    data-cancel-yes
                    onClick={run}
                    disabled={busy}
                    aria-busy={busy}
                    style={{
                        minHeight: 44, padding: "10px 16px", flex: "1 1 160px",
                        borderRadius: 10, border: "none", background: t.danger, color: "#fff",
                        fontSize: 13, fontWeight: 700, fontFamily: "inherit",
                        cursor: busy ? "not-allowed" : "pointer", opacity: busy ? 0.6 : 1,
                    }}>
                    {busy ? "Cancelling…" : "Yes, cancel it"}
                </button>
                <button
                    type="button"
                    data-cancel-keep
                    onClick={() => { setConfirming(false); setError(appt.id, null); }}
                    disabled={busy}
                    style={{
                        minHeight: 44, padding: "10px 16px", flex: "1 1 160px",
                        borderRadius: 10, border: "1px solid " + t.border,
                        background: "transparent", color: t.text,
                        fontSize: 13, fontWeight: 700, fontFamily: "inherit",
                        cursor: busy ? "not-allowed" : "pointer", opacity: busy ? 0.6 : 1,
                    }}>
                    Keep appointment
                </button>
            </div>
        </div>
    );
}

/* "Hire this lawyer", offered only where it can actually work.
 *
 * A new engagement must follow a COMPLETED consultation with that lawyer
 * (AGREEMENTS_PRODUCT_PLAN.md §17 R5-1), and only the lawyer can mark one
 * completed -- so this is the first moment the client is allowed to ask.
 *
 * It hands off to the lawyers page rather than duplicating the hire form: the
 * link carries the lawyer, their name and THIS consultation, so the form opens
 * with the right consultation already chosen. The server re-checks all three.
 */
/* ONE HIRE RULE (2026-10-12) for every place a completed consultation is
 * shown: the Appointments page (hub row and detail) and Tracking's cards.
 * They were two renderers, and Tracking kept offering "Hire" after a request
 * had been sent, which the server refuses (one attempt per consultation). */
function useHireRequests(dep) {
    const [byAppt, setByAppt] = useState({});
    useEffect(() => {
        let off = false;
        const load = () => Promise.resolve().then(() => listEngagements()).then(res => {
            if (off || !res || res.error || !Array.isArray(res.data)) return;
            const map = {};
            for (const e of res.data) if (e.appointment_id) map[e.appointment_id] = e;
            setByAppt(map);
        }).catch(() => {});
        load();
        const stop = onNotification((n) => {
            const ty = String(n.type || "");
            if (ty.startsWith("engagement_") || ty === "lawyer_assigned") load();
        });
        return () => { off = true; stop(); };
    }, [dep]);
    return byAppt;
}

/** [title, sub, href, cta, kind] for the hire step of a completed consultation. */
function hireAction(appt, e) {
    const first = String(appt.lawyer_name || "your lawyer").split(" ")[0];
    if (!e) return ["Hire " + first + " for a case", "They send their fee and scope; nothing is agreed until you accept.", hireHref(appt), "Request to hire", "prim"];
    if (e.status === "requested") return ["Hire request sent", `Waiting for ${first} to send their fee and scope. You'll be notified.`, matterHref(e.case_id, { engagement: e.id }), "View request", "ghost"];
    if (e.status === "terms_proposed") return [`${first} sent you terms`, `${e.fee_amount != null ? `Fee Rs ${Number(e.fee_amount).toLocaleString()}` : "Their fee and scope"} — accept or decline them.`, matterHref(e.case_id, { engagement: e.id }), "Review terms", "prim"];
    if (e.status === "accepted" || e.status === "completed") return [`${first} is your lawyer`, `${e.case_title || "Your case"} — follow it on Tracking.`, matterHref(e.case_id, { engagement: e.id }), "Open case", "prim"];
    return ["Hire request closed", `It was ${String(e.status).replace(/_/g, " ")}. This consultation was used for it; book a follow-up to ask again.`, lawyerHref(appt, "book"), "Book a follow-up", "ghost"];
}

/* ── APPOINTMENTS, REDESIGNED (2026-10-12) ─────────────────────────────────
 * One card is the whole appointment: where it stands (a progress strip), what
 * to do now (join, wait, next step), and the actions that already existed
 * below it. The same component serves Tracking's tab and the Appointments
 * page, so there is one list and one set of rules. */
function apptEnded(appt, now = Date.now()) {
    return Boolean(appt.end_at && new Date(appt.end_at).getTime() <= now);
}

function untilWords(iso, now = Date.now()) {
    const mins = Math.round((new Date(iso).getTime() - now) / 60000);
    if (!Number.isFinite(mins)) return "";
    if (mins <= 0) return "now";
    if (mins < 60) return `in ${mins} min`;
    if (mins < 1440) return `in ${Math.floor(mins / 60)} h ${mins % 60} min`;
    const d = Math.floor(mins / 1440);
    return `in ${d} day${d === 1 ? "" : "s"}`;
}

/** A calendar file for a confirmed appointment, made in the browser. */
function downloadIcs(appt) {
    const stamp = iso => new Date(iso).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
    const end = appt.end_at || new Date(new Date(appt.scheduled_at).getTime() + (appt.duration_minutes || 60) * 60000).toISOString();
    const esc = v => String(v || "").replace(/[\\,;]/g, m => "\\" + m).replace(/\n/g, "\\n");
    const lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//AttorneyAI//Appointments//EN", "BEGIN:VEVENT",
        `UID:${appt.id}@attorney.ai`, `DTSTAMP:${stamp(new Date().toISOString())}`,
        `DTSTART:${stamp(appt.scheduled_at)}`, `DTEND:${stamp(end)}`,
        `SUMMARY:${esc(`Consultation${appt.lawyer_name ? " with " + appt.lawyer_name : ""}`)}`,
        appt.meeting_link ? `URL:${appt.meeting_link}` : null,
        `DESCRIPTION:${esc(appt.meeting_link ? `Join: ${appt.meeting_link}` : "AttorneyAI consultation")}`,
        "END:VEVENT", "END:VCALENDAR",
    ].filter(Boolean);
    const url = URL.createObjectURL(new Blob([lines.join("\r\n")], { type: "text/calendar" }));
    const a = document.createElement("a");
    a.href = url; a.download = "consultation.ics";
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function googleCalendarHref(appt) {
    const stamp = iso => new Date(iso).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
    const end = appt.end_at || new Date(new Date(appt.scheduled_at).getTime() + (appt.duration_minutes || 60) * 60000).toISOString();
    const where = appt.meeting_link || appt.lawyer_card?.office_address || "";
    const q = new URLSearchParams({
        action: "TEMPLATE",
        text: `Consultation${appt.lawyer_name ? " with " + appt.lawyer_name : ""}`,
        dates: `${stamp(appt.scheduled_at)}/${stamp(end)}`,
        details: appt.meeting_link ? `Join: ${appt.meeting_link}` : "AttorneyAI consultation",
        ...(where ? { location: where } : {}),
    });
    return "https://calendar.google.com/calendar/render?" + q.toString();
}

/* Join in-app video (2026-10-20): the client gets the same join screen as the
 * lawyer -- blurred page, camera check, a big Join -- before the call itself.
 * "Message" opens this appointment's thread when the page has one. */
function ClientJoinVideo({ appt, t, onMessage = null }) {
    const [open, setOpen] = useState(false);
    const lawyer = appt.lawyer_name || "your lawyer";
    const first = String(lawyer).split(" ")[0];
    const start = new Date(appt.scheduled_at);
    const end = appt.end_at ? new Date(appt.end_at) : new Date(+start + (appt.duration_minutes || 60) * 60000);
    const now = Date.now();
    const live = +start <= now && now < +end;
    return (<>
        <VideoJoin apptId={appt._id || appt.id} status={appt.status} mode={appt.mode} accent="#13806b" muted={t.textMuted} danger={t.danger}
            dark={t.mode !== "light"} otherName={first} onPreJoin={() => setOpen(true)} />
        {open && (
            <PreJoinModal
                apt={{ id: appt._id || appt.id, client: lawyer, duration: `${appt.duration_minutes || 60} min`, at: start,
                       note: appt.notes || null, meetingLink: appt.meeting_link || null,
                       initials: String(lawyer).split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase() }}
                day={formatPkt(start, { weekday: "short", day: "numeric", month: "short" })}
                span={`${hhmm(start)}–${hhmm(end)}`}
                when={live ? "Happening now" : `Starts ${untilWords(appt.scheduled_at)}`} live={live}
                dark={t.mode !== "light"} onClose={() => setOpen(false)}
                onMessage={onMessage} />
        )}
    </>);
}

/* ── THE APPOINTMENTS PAGE (2026-10-12) ─────────────────────────────────────
 * The sidebar's Appointments page, as designed: a hub of compact rows (one
 * action each) and, on opening one, its own page. The actions themselves are
 * the components above -- Reschedule, Cancel, Report, Hire -- so the rules
 * live in one place. Tracking's tab keeps its expanded cards. */
// Headings in the Documents module typeface too (2026-10-12), at a heavier weight.
// Same type as Overview (2026-11-23): Hanken Grotesk for the page and its
// headings, Nunito Sans only for the page title (as Overview's greeting).
const HUB_SERIF = "'Hanken Grotesk', system-ui, sans-serif";
const HUB_TITLE = "'Nunito Sans', 'Avenir Next', Avenir, system-ui, sans-serif";
const GRAD = "linear-gradient(135deg,#12897f,#1c9c66)";

function hubChip(appt, t) {
    const ended = apptEnded(appt);
    switch (appt.status) {
        case "pending": return { text: "Waiting for lawyer", bg: `${t.warn}24`, color: t.warn };
        case "confirmed": return ended
            ? { text: "Ended · to be closed", bg: t.inputBg, color: t.textMuted }
            : { text: `✓ Confirmed · ${untilWords(appt.scheduled_at)}`, bg: `${t.primary}24`, color: t.primary };
        case "completed": return { text: "Completed", bg: t.inputBg, color: t.text };
        case "cancelled": return { text: isDeclinedRequest(appt) ? "Declined" : "Cancelled", bg: `${t.danger}1f`, color: t.danger };
        case "expired": return { text: "Expired", bg: t.inputBg, color: t.textMuted };
        case "no_show": return { text: "No show", bg: t.inputBg, color: t.textMuted };
        default: return { text: statusWord(appt.status), bg: t.inputBg, color: t.textMuted };
    }
}

function dayTag(iso) {
    const key = pktDayKey(iso);
    if (key === pktToday()) return "TODAY";
    if (key === pktDayKey(new Date(Date.now() + 86400000).toISOString())) return "TOMORROW";
    return String(formatPkt(iso, { weekday: "short", day: "numeric" })).toUpperCase();
}
const hhmm = iso => formatPkt(iso, { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const MODE_WORDS = { video: "Video call", in_person: "In person", phone: "Phone" };
const aboutOf = (appt, caseTitles) => appt.case_id ? (caseTitles[appt.case_id] || `Case ${appt.case_id.slice(-8)}`) : "General consultation";
const needsAction = a => (a.status === "confirmed" && !apptEnded(a)
    && new Date(a.scheduled_at).getTime() - Date.now() < 24 * 3600000) || a.status === "completed";
const isUpcomingAppt = a => (a.status === "pending" || a.status === "confirmed") && !apptEnded(a);

function hubBtn(kind, t) {
    return {
        height: 40, padding: "0 16px", borderRadius: 12, fontSize: 14, fontWeight: 700, fontFamily: "inherit",
        display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 8, whiteSpace: "nowrap",
        cursor: "pointer", textDecoration: "none", boxSizing: "border-box",
        ...(kind === "prim" ? { border: "none", color: "#fff", background: GRAD }
            : { border: `1px solid ${t.border}`, background: "transparent", color: t.text }),
    };
}

/** That lawyer's page with one action open: "book" or "review". */
function lawyerHref(appt, action) {
    return "/lawyers?lawyer=" + encodeURIComponent(appt.lawyer_id || "")
        + "&lawyer_name=" + encodeURIComponent(appt.lawyer_name || "")
        + "&action=" + action;
}

function hireHref(appt) {
    return "/lawyers?hire=" + encodeURIComponent(appt.lawyer_id || "")
        + "&hire_name=" + encodeURIComponent(appt.lawyer_name || "")
        + "&appointment=" + encodeURIComponent(appt.id);
}

const cardOf = appt => appt.lawyer_card || {};
const titleCase = x => String(x || "").replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
function lawyerLine(appt) {
    const c = cardOf(appt);
    const specs = (c.specializations || []).map(titleCase).slice(0, 2).join(", ");
    const place = c.office_address || (c.province ? (c.province === "kpk" ? "KPK" : titleCase(c.province)) : "");
    return [specs, place].filter(Boolean).join(" · ");
}
function initialsOf(name) {
    return String(name || "L").split(" ").filter(Boolean).map(w => w[0]).join("").slice(0, 2).toUpperCase();
}
const MODE_LONG = { video: "Video consultation", in_person: "In-person consultation", phone: "Phone consultation" };
const MODE_GLYPH = { video: "▣", in_person: "⌖", phone: "☎" };
function mapsHref(appt, directions) {
    const c = cardOf(appt);
    const q = (c.lat != null && c.lng != null) ? `${c.lat},${c.lng}` : c.office_address;
    if (!q) return null;
    return directions
        ? `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(q)}`
        : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(q)}`;
}
async function copyText(text) {
    try { await navigator.clipboard.writeText(text); return true; } catch { return false; }
}

/* A small month calendar: days with appointments are ringed (green when
 * confirmed, gold while waiting); picking one narrows the list to that day. */
function MiniCalendar({ t, appointments, picked, onPick, bare = false }) {
    const [month, setMonth] = useState(() => pktToday().slice(0, 7));
    const [y, m] = month.split("-").map(Number);
    const first = new Date(Date.UTC(y, m - 1, 1));
    const days = new Date(Date.UTC(y, m, 0)).getUTCDate();
    const lead = (first.getUTCDay() + 6) % 7;
    const byDay = {};
    for (const a of appointments) {
        const k = pktDayKey(a.scheduled_at);
        if (a.status === "confirmed") byDay[k] = "confirmed";
        else if (a.status === "pending" && byDay[k] !== "confirmed") byDay[k] = "pending";
        else if (!byDay[k]) byDay[k] = "other";
    }
    const today = pktToday();
    const step = d => { const n = new Date(Date.UTC(y, m - 1 + d, 1)); setMonth(n.toISOString().slice(0, 7)); };
    const label = first.toLocaleDateString("en-GB", { month: "long", year: "numeric", timeZone: "UTC" });
    const navBtn = { width: 28, height: 28, borderRadius: 8, border: `1px solid ${t.border}`, background: "transparent", color: t.text, cursor: "pointer", fontFamily: "inherit" };
    return (
        <div data-mini-calendar style={bare ? {} : { padding: 16, borderRadius: 16, background: t.card, border: `1px solid ${t.border}` }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 10 }}>
                <b style={{ flex: 1, color: t.text }}>{label}</b>
                <button type="button" aria-label="Previous month" onClick={() => step(-1)} style={navBtn}>‹</button>
                <button type="button" aria-label="Next month" onClick={() => step(1)} style={navBtn}>›</button>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(7,minmax(0,1fr))", gap: 4, textAlign: "center", fontSize: 11, fontWeight: 800, color: t.textMuted }}>
                {["M", "T", "W", "T", "F", "S", "S"].map((d, i) => <span key={i}>{d}</span>)}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(7,minmax(0,1fr))", gap: 4, marginTop: 4 }}>
                {Array.from({ length: lead }, (_, i) => <span key={`b${i}`} />)}
                {Array.from({ length: days }, (_, i) => {
                    const key = `${month}-${String(i + 1).padStart(2, "0")}`;
                    const kind = byDay[key];
                    const isToday = key === today, on = picked === key;
                    const ring = kind === "confirmed" ? t.primary : kind === "pending" ? t.warn : kind ? t.textMuted : null;
                    return (
                        <button key={key} type="button" data-cal-day={key} disabled={!kind}
                            aria-pressed={on} aria-label={`${key}${kind ? " — has appointments" : ""}`}
                            onClick={() => onPick(on ? null : key)}
                            style={{ height: 30, borderRadius: "50%", border: "none", fontFamily: "inherit", fontSize: 12.5, fontWeight: isToday || on ? 800 : 600,
                                cursor: kind ? "pointer" : "default",
                                background: on ? t.primary : isToday ? `${t.primary}26` : "transparent",
                                color: on ? "#06211a" : kind ? t.text : t.textMuted,
                                boxShadow: ring && !on ? `inset 0 0 0 1.5px ${ring}` : "none" }}>{i + 1}</button>
                    );
                })}
            </div>
            <div style={{ display: "flex", gap: 12, fontSize: 11.5, color: t.textMuted, marginTop: 10 }}>
                <span><i style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: t.primary, marginRight: 5 }} />Confirmed</span>
                <span><i style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: t.warn, marginRight: 5 }} />Waiting</span>
            </div>
        </div>
    );
}

/* MEETINGS YOUR LAWYER PROPOSED (2026-10-12). After hiring, the lawyer can
 * ask to meet: they propose up to three times on the case, and choosing one
 * here makes it a confirmed appointment. Nothing is booked before that. */
function MeetingProposals({ t, onChosen }) {
    const [items, setItems] = useState([]);
    const [loadState, setLoadState] = useState("loading");
    const [loadError, setLoadError] = useState(null);
    const [busy, setBusy] = useState(null);
    const [error, setError] = useState({});
    const [declining, setDeclining] = useState(null);
    const [reason, setReason] = useState("");
    let focusProposalId = null;
    try { focusProposalId = new URLSearchParams(window.location.search).get("proposal"); } catch { focusProposalId = null; }
    const load = useCallback(() => Promise.resolve().then(() => listMeetingProposals({ status: "open", all: true }))
        .then(res => {
            if (!res || res.error || !Array.isArray(res.data)) {
                setLoadState("error"); setLoadError(res?.error?.message || "Could not load proposed meeting times."); return;
            }
            setItems(res.data.filter(p => p.status === "open"));
            setLoadState("ready"); setLoadError(null);
        })
        .catch(() => { setLoadState("error"); setLoadError("Could not load proposed meeting times."); }), []);
    useEffect(() => { load(); }, [load]);
    useEffect(() => onNotification((n) => {
        if (String(n.type || "").startsWith("appointment_propos")) load();
    }), [load]);
    // Arriving from "Choose a time" (?section=proposals): bring them into view.
    useEffect(() => {
        if (!items.length) return;
        try {
            if (new URLSearchParams(window.location.search).get("section") !== "proposals") return;
            const exact = focusProposalId ? [...document.querySelectorAll("[data-proposal]")]
                .find(node => node.getAttribute("data-proposal") === String(focusProposalId)) : null;
            (exact || document.querySelector("[data-proposals]"))?.scrollIntoView?.({ block: "center", behavior: "smooth" });
        } catch { /* not in a browser */ }
    }, [items.length, focusProposalId]);
    const focusMissing = !!focusProposalId && loadState === "ready"
        && !items.some(p => String(p.id) === String(focusProposalId));
    if (!items.length && loadState === "loading") return null;
    if (!items.length && loadState === "error") return (
        <div role="alert" data-proposals-error style={{ marginTop: 6, padding: "14px 16px", borderRadius: 14, background: t.card, border: `1px solid ${t.warn}66`, color: t.text, fontSize: 13.5 }}>
            {loadError} A meeting time may still be waiting for you.{" "}
            <button type="button" onClick={load} style={{ border: 0, background: "none", padding: 0, color: t.primary, fontWeight: 700, cursor: "pointer" }}>Try again</button>
        </div>
    );
    if (!items.length && focusMissing) return (
        <div role="status" data-proposal-missing style={{ marginTop: 6, padding: "14px 16px", borderRadius: 14, background: t.card, border: `1px solid ${t.border}`, color: t.textMuted, fontSize: 13.5 }}>
            The proposed meeting this link points to is no longer waiting for a response.
        </div>
    );
    if (!items.length) return null;

    const choose = async (p, i) => {
        if (busy) return;
        setBusy(`${p.id}:${i}`);
        setError(e => ({ ...e, [p.id]: null }));
        const { data, error: err } = await acceptMeetingProposal(p.id, i);
        setBusy(null);
        if (err) {
            setError(e => ({ ...e, [p.id]: err.message || "Could not confirm that time. Please choose another." }));
            load();
            return;
        }
        setItems(list => list.filter(x => x.id !== p.id));
        onChosen && onChosen(data?.appointment?.id || null);
    };
    const decline = async (p) => {
        if (busy) return;
        setBusy(`${p.id}:decline`);
        const { error: err } = await declineMeetingProposal(p.id, reason.trim() || null);
        setBusy(null);
        if (err) { setError(e => ({ ...e, [p.id]: err.message || "Could not send that. Please try again." })); return; }
        setDeclining(null);
        setReason("");
        setItems(list => list.filter(x => x.id !== p.id));
    };

    return (
        <section aria-label="Meetings your lawyer proposed" data-proposals style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 6 }}>
            {loadState === "error" && <div role="alert" data-proposals-error style={{ padding: "12px 14px", borderRadius: 12, border: `1px solid ${t.warn}66`, color: t.text, fontSize: 13 }}>
                {loadError} This list may be out of date.{" "}<button type="button" onClick={load} style={{ border: 0, background: "none", padding: 0, color: t.primary, fontWeight: 700, cursor: "pointer" }}>Try again</button>
            </div>}
            {focusMissing && <div role="status" data-proposal-missing style={{ padding: "12px 14px", borderRadius: 12, border: `1px solid ${t.border}`, color: t.textMuted, fontSize: 13 }}>
                The proposed meeting this link points to is no longer waiting for a response.
            </div>}
            {items.map(p => {
                const word = MODE_WORDS[p.mode] || p.mode;
                const mins = p.duration_minutes || 60;
                return (
                    <article key={p.id} data-proposal={p.id} data-focused={String(p.id) === String(focusProposalId) ? "" : undefined} style={{ padding: "18px 20px", borderRadius: 18, border: `1px solid ${t.primary}66`,
                        outline: String(p.id) === String(focusProposalId) ? `2px solid ${t.primary}` : "none", outlineOffset: 2,
                        background: `linear-gradient(120deg, color-mix(in srgb, ${t.primary} 12%, ${t.card}) 0%, ${t.card} 60%)` }}>
                        <div style={{ fontSize: 11.5, fontWeight: 800, letterSpacing: ".08em", textTransform: "uppercase", color: t.primary }}>Meeting proposed</div>
                        <div style={{ font: `700 18px/1.3 ${HUB_SERIF}`, color: t.text, marginTop: 4 }}>
                            {p.lawyer_name || "Your lawyer"} would like to meet about “{p.case_title || "your case"}”
                        </div>
                        <div style={{ fontSize: 13.5, color: t.textMuted, marginTop: 4 }}>{p.agenda} · {word} · {mins} minutes</div>
                        <div style={{ fontSize: 12.5, fontWeight: 700, color: t.text, marginTop: 14 }}>Choose a time</div>
                        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 8 }}>
                            {p.options.map((iso, i) => {
                                const passed = p.option_passed?.[i];
                                return (
                                    <button key={iso} type="button" data-proposal-option={i} disabled={passed || !!busy}
                                        onClick={() => choose(p, i)}
                                        title={passed ? "This time has passed" : undefined}
                                        style={{ ...hubBtn(passed ? "ghost" : "prim", t), height: 42, padding: "0 16px", opacity: passed ? 0.5 : 1,
                                            textDecoration: passed ? "line-through" : "none", cursor: passed ? "not-allowed" : busy ? "wait" : "pointer" }}>
                                        {busy === `${p.id}:${i}` ? "Confirming…"
                                            : `${formatPkt(iso, { weekday: "short", day: "numeric", month: "short" })} · ${hhmm(iso)}`}
                                    </button>
                                );
                            })}
                        </div>
                        {error[p.id] && <div role="alert" style={{ marginTop: 10, fontSize: 13, fontWeight: 600, color: t.danger }}>{error[p.id]}</div>}
                        {declining === p.id ? (
                            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginTop: 12 }}>
                                <input aria-label="Message to your lawyer (optional)" value={reason} maxLength={500} onChange={e => setReason(e.target.value)}
                                    placeholder="Optional: when would suit you instead?"
                                    style={{ flex: "1 1 260px", height: 40, padding: "0 12px", borderRadius: 10, border: `1px solid ${t.border}`, background: t.inputBg, color: t.text, fontSize: 13.5, fontFamily: "inherit", outline: "none" }} />
                                <button type="button" onClick={() => { setDeclining(null); setReason(""); }} style={hubBtn("ghost", t)}>Back</button>
                                <button type="button" data-proposal-decline onClick={() => decline(p)} disabled={!!busy} style={{ ...hubBtn("ghost", t), color: t.danger, borderColor: `${t.danger}66` }}>Send</button>
                            </div>
                        ) : (
                            <button type="button" onClick={() => setDeclining(p.id)}
                                style={{ marginTop: 12, border: 0, background: "none", padding: 0, color: t.textMuted, fontSize: 13, fontWeight: 700, cursor: "pointer", fontFamily: "inherit" }}>
                                None of these work for me
                            </button>
                        )}
                    </article>
                );
            })}
        </section>
    );
}

function AppointmentsHub(props) {
    const { appointments, loading, t, refreshError, onReload, onLoadMore, loadingMore, moreError, total, complete,
        caseTitles = {}, focusId = null } = props;
    const video = useVideoConfigured();
    const [openId, setOpenId] = useState(focusId);
    // A new ?appointment= (another booking, a notification) opens that one.
    useEffect(() => { if (focusId) setOpenId(focusId); }, [focusId]);
    const [tab, setTab] = useState("upcoming");
    const [day, setDay] = useState(null);
    // "Review" opens the review dialog on this page (2026-10-20); it used to
    // send the client to the Lawyers page to find the form.
    const [reviewFor, setReviewFor] = useState(null);
    // Request to hire / View request / Review terms open HERE (2026-10-20).
    const [hireFor, setHireFor] = useState(null);
    const [hireVersion, setHireVersion] = useState(0);
    // Hire requests by the consultation they follow (2026-10-12): a completed
    // consultation shows where its request stands instead of offering "Hire"
    // again, which the server would refuse (one attempt per consultation).
    const engByAppt = useHireRequests(`${appointments.length}:${hireVersion}`);
    // Lawyers this client has already reviewed: their front card drops the
    // Review button. Unknown (not asked yet, or the check failed) keeps it --
    // the dialog itself then says "already reviewed".
    const [reviewed, setReviewed] = useState({});
    const reviewIds = [...new Set(appointments.filter(a => isRecentCompleted(a)).map(a => a.lawyer_id).filter(Boolean))].slice(0, 6);
    const reviewKey = reviewIds.join(",");
    useEffect(() => {
        let off = false;
        reviewIds.filter(id => !(id in reviewed)).forEach(id => {
            Promise.resolve().then(() => getReviewEligibility(id)).then(res => {
                if (off || !res || res.error || !res.data) return;
                setReviewed(r => ({ ...r, [id]: res.data.already_reviewed === true }));
            }).catch(() => {});
        });
        return () => { off = true; };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [reviewKey]);
    const hireDialog = hireFor && (
        <HireDialog appt={hireFor} engagement={engByAppt[hireFor.id] || null} t={t}
            onClose={() => setHireFor(null)} onChanged={() => setHireVersion(v => v + 1)} />
    );
    const opened = openId ? appointments.find(a => a.id === openId) : null;
    if (opened) return (<>
        <AppointmentDetail {...props} appt={opened} engagement={engByAppt[opened.id] || null}
            openThread={props.openThreadId === opened.id} onBack={() => setOpenId(null)} onHire={a => setHireFor(a)} />
        {hireDialog}
    </>);

    const at = a => new Date(a.scheduled_at).getTime();
    const upcoming = appointments.filter(isUpcomingAppt).sort((a, b) => at(a) - at(b));
    const cancelled = appointments.filter(a => a.status === "cancelled").sort((a, b) => at(b) - at(a));
    const past = appointments.filter(a => !isUpcomingAppt(a) && a.status !== "cancelled").sort((a, b) => at(b) - at(a));
    const lists = { upcoming, past, cancelled };
    const shown = (lists[tab] || upcoming).filter(a => !day || pktDayKey(a.scheduled_at) === day);
    const next = upcoming[0] || null;
    const pendingCount = upcoming.filter(a => a.status === "pending").length;
    // A finished consultation's next step, on the page's FRONT (2026-10-20):
    // it lived only under "Past", so a client never saw "Hire" or "Review"
    // after the meeting. Shown while the hire is not settled either way.
    // Only what the client must act on (2026-10-20): hire not yet asked, or
    // terms to answer. "Hire request sent" waits on the lawyer, so it stays in
    // Past (its row button opens the request), not here.
    const nextSteps = past.filter(a => isRecentCompleted(a)
        && NEXT_STEP_STATES.has(engByAppt[a.id]?.status || "none")).slice(0, 2);
    const tabBtn = on => ({ height: 36, padding: "0 14px", borderRadius: 999, fontFamily: "inherit", fontSize: 13.5, fontWeight: 700, cursor: "pointer",
        display: "inline-flex", alignItems: "center", gap: 8,
        border: `1px solid ${on ? t.primary : t.border}`, background: on ? t.primary : "transparent", color: on ? "#06211a" : t.text });

    return (
        <div data-appointments-hub style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <header style={{ display: "flex", alignItems: "flex-end", gap: 14, flexWrap: "wrap" }}>
                <div style={{ flex: "1 1 260px" }}>
                    <h1 style={{ margin: 0, font: `600 34px/1.15 ${HUB_TITLE}`, color: t.text }}>Appointments</h1>
                    <div style={{ fontSize: 14, color: t.textMuted, marginTop: 4 }}>Manage your consultations, view details and join your meetings.</div>
                </div>
                <a href="/lawyers" style={hubBtn("prim", t)}>+ Book a consultation</a>
            </header>

            {refreshError && (
                <div role="alert" style={{ padding: "10px 14px", borderRadius: 12, border: `1px solid ${t.warn}55`, background: `${t.warn}12`, fontSize: 13, color: t.text, display: "flex", gap: 10, alignItems: "center" }}>
                    <span style={{ flex: 1 }}>
                        {!appointments.length && <b style={{ display: "block" }}>Could not load your appointments</b>}
                        {refreshError} {appointments.length ? "These may be out of date." : ""}
                    </span>
                    <button type="button" onClick={() => onReload && onReload()} style={hubBtn("ghost", t)}>Try again</button>
                </div>
            )}

            <MeetingProposals t={t} onChosen={async (id) => { if (onReload) await onReload(); if (id) setOpenId(id); }} />

            {hireDialog}
            {reviewFor && <ReviewLawyerDialog lawyerId={reviewFor.lawyer_id} lawyerName={reviewFor.lawyer_name} t={t} onClose={() => setReviewFor(null)}
                onDone={() => setReviewed(r => ({ ...r, [reviewFor.lawyer_id]: true }))} />}

            {nextSteps.length > 0 && (
                <section aria-label="After your consultation" data-next-steps style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {nextSteps.map(appt => {
                        const e = engByAppt[appt.id] || null;
                        const [title, sub, href, cta, kind] = hireAction(appt, e);
                        const first = String(appt.lawyer_name || "your lawyer").split(" ")[0];
                        return (
                            <article key={appt.id} data-next-step={appt.id} data-hire-state={e?.status || "none"}
                                style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap", padding: "16px 18px", borderRadius: 16,
                                    background: t.card, border: `1px solid ${kind === "prim" ? `${t.primary}80` : t.border}` }}>
                                <span aria-hidden="true" style={{ width: 46, height: 46, borderRadius: "50%", display: "grid", placeItems: "center", fontWeight: 800, color: "#fff", background: GRAD, flex: "none" }}>{initialsOf(appt.lawyer_name)}</span>
                                <div style={{ flex: "1 1 260px", minWidth: 0 }}>
                                    <div style={{ fontSize: 12, fontWeight: 800, letterSpacing: ".04em", textTransform: "uppercase", color: t.primary }}>
                                        Consultation completed · {formatPkt(appt.scheduled_at, { weekday: "short", day: "numeric", month: "short" })}
                                    </div>
                                    <b style={{ display: "block", fontSize: 16, color: t.text, marginTop: 2 }}>{title}</b>
                                    <div style={{ fontSize: 13, color: t.textMuted, marginTop: 2 }}>{sub}</div>
                                </div>
                                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                                    {HIRE_HERE.has(e?.status || "none")
                                        ? <button type="button" data-next-hire onClick={() => setHireFor(appt)} style={{ ...hubBtn(kind, t), fontFamily: "inherit" }}>{cta}</button>
                                        : <a href={href} data-next-hire style={hubBtn(kind, t)}>{cta}</a>}
                                    {!reviewed[appt.lawyer_id] && <button type="button" data-next-review onClick={() => setReviewFor(appt)} style={{ ...hubBtn("ghost", t), fontFamily: "inherit" }}>Review {first}</button>}
                                </div>
                            </article>
                        );
                    })}
                </section>
            )}

            <nav aria-label="Filter appointments" data-hub-stats style={{ display: "grid", gridTemplateColumns: "repeat(3,minmax(0,1fr))", gap: 14, margin: "14px 0 10px" }}>
                {[["upcoming", "Upcoming", t.primary, <><rect x="3.5" y="5" width="17" height="15" rx="2.5" /><path d="M8 3v4M16 3v4M3.5 10h17" /></>],
                  ["past", "Past", "#6ADDEB", <><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></>],
                  ["cancelled", "Cancelled", t.danger, <><circle cx="12" cy="12" r="8.5" /><path d="m9.2 9.2 5.6 5.6M14.8 9.2l-5.6 5.6" /></>]].map(([k, label, tone, icon]) => {
                    const on = tab === k;
                    return (
                        <button key={k} type="button" aria-pressed={on} data-hub-tab={k} onClick={() => setTab(k)} className="hub-stat"
                            style={{ display: "flex", alignItems: "center", gap: 14, padding: "16px 18px", borderRadius: 16, textAlign: "left", cursor: "pointer", fontFamily: "inherit",
                                border: `1px solid ${on ? `color-mix(in srgb, ${tone} 65%, transparent)` : t.border}`, background: on ? `color-mix(in srgb, ${tone} 11%, ${t.card})` : t.card, color: t.text,
                                boxShadow: on ? `0 0 0 3px color-mix(in srgb, ${tone} 9%, transparent)` : "none", transition: "border-color .15s, background .15s, transform .15s" }}>
                            <span aria-hidden="true" style={{ width: 42, height: 42, flexShrink: 0, borderRadius: 12, display: "grid", placeItems: "center", color: tone, background: `color-mix(in srgb, ${tone} ${on ? 30 : 16}%, transparent)` }}>
                                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">{icon}</svg>
                            </span>
                            <span style={{ flex: 1 }}>
                                <span style={{ display: "block", fontSize: 13, color: t.textMuted, fontWeight: 700 }}>{label}</span>
                                <span style={{ display: "block", fontSize: 26, fontWeight: 800, lineHeight: 1.1 }}>{lists[k].length}</span>
                            </span>
                            <span aria-hidden="true" style={{ color: on ? tone : t.textMuted, fontSize: 18 }}>→</span>
                        </button>
                    );
                })}
            </nav>
            {day && <button type="button" onClick={() => setDay(null)} style={{ ...hubBtn("ghost", t), height: 32, alignSelf: "flex-end" }}>Showing {formatPkt(`${day}T12:00:00+05:00`, { weekday: "short", day: "numeric", month: "short" })} · Show all</button>}

            <div style={{ display: "grid", gridTemplateColumns: "290px minmax(0,1fr)", gap: 18, alignItems: "start" }}>
                <aside data-hub-panel style={{ display: "flex", flexDirection: "column", gap: 12, padding: 14, borderRadius: 22,
                    border: `1px solid ${t.primary}55`, background: `linear-gradient(180deg, color-mix(in srgb, ${t.primary} 18%, ${t.card}) 0%, ${t.card} 70%)` }}>
                    <div style={{ padding: 14, borderRadius: 16, background: t.inputBg }}>
                        <MiniCalendar bare t={t} appointments={appointments} picked={day} onPick={setDay} />
                    </div>
                    {[next ? {
                        key: "next", dot: t.primary, title: "Next appointment",
                        sub: `${dayTag(next.scheduled_at) === "TODAY" ? "Today" : dayTag(next.scheduled_at) === "TOMORROW" ? "Tomorrow" : formatPkt(next.scheduled_at, { weekday: "short", day: "numeric", month: "short" })} · ${hhmm(next.scheduled_at)} PKT`,
                        sub2: `${next.lawyer_name || "Your lawyer"} · ${MODE_WORDS[next.mode] || next.mode}`, open: () => setOpenId(next.id), attr: { "data-next-appointment": "" },
                    } : null,
                    pendingCount ? {
                        key: "waiting", dot: t.warn, title: "Waiting for a lawyer",
                        sub: `${pendingCount} request${pendingCount === 1 ? "" : "s"} not confirmed yet`,
                        open: () => setOpenId(upcoming.find(a => a.status === "pending").id), attr: {},
                    } : null].filter(Boolean).map(item => (
                        <button key={item.key} type="button" onClick={item.open} {...item.attr}
                            style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 14px", borderRadius: 14, border: `1px solid ${t.border}`, background: t.card, color: t.text, textAlign: "left", cursor: "pointer", fontFamily: "inherit" }}>
                            <span aria-hidden="true" style={{ width: 10, height: 10, flexShrink: 0, borderRadius: "50%", background: item.dot }} />
                            <span style={{ flex: 1, minWidth: 0 }}>
                                <b style={{ display: "block", fontSize: 14 }}>{item.title}</b>
                                <span style={{ display: "block", fontSize: 12.5, color: t.textMuted }}>{item.sub}</span>
                                {item.sub2 && <span style={{ display: "block", fontSize: 12.5, color: t.textMuted }}>{item.sub2}</span>}
                            </span>
                            <span aria-hidden="true" style={{ color: t.textMuted }}>›</span>
                        </button>
                    ))}
                    {!next && <div style={{ padding: "12px 14px", borderRadius: 14, background: t.card, fontSize: 13, color: t.textMuted }}>Nothing booked yet. <a href="/lawyers" style={{ color: t.primary, fontWeight: 700 }}>Find a lawyer</a></div>}
                    <div data-prepare-ai style={{ marginTop: 6, padding: "16px 14px 14px", borderRadius: 16, background: `color-mix(in srgb, ${t.primary} 12%, transparent)` }}>
                        <span aria-hidden="true" style={{ width: 38, height: 38, borderRadius: 12, display: "grid", placeItems: "center", background: GRAD, color: "#fff" }}>
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3l1.8 4.6L18.5 9l-4.7 1.6L12 15l-1.8-4.4L5.5 9l4.7-1.4z" /><path d="M18 15l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z" /></svg>
                        </span>
                        <div style={{ fontSize: 17, fontWeight: 800, color: t.text, marginTop: 10, lineHeight: 1.3 }}>Not sure what to ask?</div>
                        <div style={{ fontSize: 13, color: t.textMuted, marginTop: 4, lineHeight: 1.5 }}>Prepare with AI Chat before you meet: the questions to ask and the documents to bring.</div>
                        <a href="/chat" style={{ ...hubBtn("prim", t), marginTop: 12, height: 38 }}>Prepare with AI</a>
                    </div>
                </aside>

                <section aria-label={tab} data-hub-list style={{ display: "flex", flexDirection: "column", gap: 12, minWidth: 0, padding: 14, borderRadius: 22,
                    border: `1px solid ${t.border}`, background: `color-mix(in srgb, ${t.card} 55%, ${t.bg})` }}>
                    <div style={{ display: "flex", alignItems: "baseline", gap: 10, padding: "4px 6px 2px" }}>
                        <b style={{ fontSize: 16, color: t.text }}>{{ upcoming: "Upcoming appointments", past: "Past appointments", cancelled: "Cancelled appointments" }[tab]}</b>
                        <span style={{ fontSize: 12.5, color: t.textMuted }}>{shown.length} · {tab === "upcoming" ? "soonest first" : "most recent first"}</span>
                    </div>
                    {loading && !appointments.length && <div style={{ fontSize: 13, color: t.textMuted }}>Loading your appointments…</div>}
                    {!loading && !shown.length && !refreshError && (
                        <div style={{ padding: "40px 20px", textAlign: "center", borderRadius: 16, background: t.card, border: `1px solid ${t.border}` }}>
                            <div style={{ fontSize: 16, fontWeight: 800, color: t.text }}>
                                {day ? "Nothing on this day in this list" : tab === "upcoming" ? "Nothing coming up" : tab === "past" ? "No past appointments yet" : "Nothing cancelled"}
                            </div>
                            {tab === "upcoming" && !day && <a href="/lawyers" style={{ ...hubBtn("prim", t), marginTop: 14 }}>Find a lawyer</a>}
                        </div>
                    )}
                    {shown.map(appt => {
                        const chip = hubChip(appt, t);
                        const isToday = dayTag(appt.scheduled_at) === "TODAY";
                        const joinable = appt.status === "confirmed" && !apptEnded(appt) && appt.meeting_link;
                        // No pasted link, but in-app video is on: Join opens the appointment, where the call starts.
                        const videoJoinable = !joinable && video && appt.status === "confirmed" && appt.mode === "video" && !apptEnded(appt);
                        const end = appt.end_at || new Date(at(appt) + (appt.duration_minutes || 60) * 60000).toISOString();
                        const line = lawyerLine(appt);
                        return (
                            <article key={appt.id} data-hub-row={appt.id} data-case-meeting={appt.case_meeting || undefined}
                                style={{ display: "grid", gridTemplateColumns: "104px 52px minmax(0,1fr) auto", gap: 16, alignItems: "center", padding: "16px 18px", borderRadius: 16,
                                    background: t.card, border: `1px solid ${isToday && appt.status === "confirmed" ? `${t.primary}80` : t.border}`,
                                    // A meeting on a case your lawyer is handling (2026-10-20), marked apart from a consultation.
                                    ...(appt.case_meeting ? { borderLeft: `4px solid ${CASE_MEETING_BLUE}`, paddingLeft: 15 } : {}) }}>
                                <div>
                                    {isToday && <span style={{ display: "inline-flex", height: 22, alignItems: "center", padding: "0 8px", borderRadius: 999, background: `${t.primary}24`, color: t.primary, fontSize: 11, fontWeight: 800, marginBottom: 6 }}>Today</span>}
                                    <div style={{ fontSize: 11, fontWeight: 800, color: t.textMuted }}>{String(formatPkt(appt.scheduled_at, { weekday: "short" })).toUpperCase()}</div>
                                    <b style={{ fontSize: 19, color: t.text }}>{formatPkt(appt.scheduled_at, { day: "numeric", month: "short" })}</b>
                                    <div style={{ fontSize: 12.5, color: t.textMuted }}>{hhmm(appt.scheduled_at)} – {hhmm(end)}</div>
                                </div>
                                <span aria-hidden="true" style={{ width: 52, height: 52, borderRadius: "50%", display: "grid", placeItems: "center", fontWeight: 800, color: "#fff", background: GRAD }}>{initialsOf(appt.lawyer_name)}</span>
                                <div style={{ minWidth: 0 }}>
                                    <b style={{ fontSize: 16, color: t.text }}>{appt.lawyer_name || "Your lawyer"}</b>
                                    {appt.case_meeting && <span data-case-meeting-chip style={{ display: "inline-flex", alignItems: "center", height: 22, padding: "0 9px", marginLeft: 8, borderRadius: 999, fontSize: 11.5, fontWeight: 800, color: CASE_MEETING_BLUE, background: `${CASE_MEETING_BLUE}1f`, border: `1px solid ${CASE_MEETING_BLUE}66`, verticalAlign: "middle" }}>Case meeting{appt.case_number ? ` · ${appt.case_number}` : ""}</span>}
                                    <div style={{ fontSize: 12.5, color: t.textMuted, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{line || "Lawyer"} · {aboutOf(appt, caseTitles)}</div>
                                    <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12.5, color: t.textMuted, marginTop: 6 }}><span style={{ color: t.primary }}>{MODE_GLYPH[appt.mode]}</span>{MODE_LONG[appt.mode] || appt.mode}</div>
                                </div>
                                <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 8 }}>
                                    <span style={{ display: "inline-flex", alignItems: "center", height: 26, padding: "0 10px", borderRadius: 999, fontSize: 12, fontWeight: 800, background: chip.bg, color: chip.color, whiteSpace: "nowrap" }}>{chip.text}</span>
                                    <div style={{ display: "flex", gap: 6 }}>
                                        <button type="button" data-open-appt onClick={() => setOpenId(appt.id)} style={hubBtn(joinable || videoJoinable ? "ghost" : appt.status === "completed" ? "ghost" : "prim", t)}>View details</button>
                                        {joinable && <a href={appt.meeting_link} target="_blank" rel="noreferrer" style={hubBtn("prim", t)}>Join meeting</a>}
                                        {videoJoinable && <button type="button" data-join-video-card onClick={() => setOpenId(appt.id)} style={hubBtn("prim", t)}>Join video</button>}
                                        {appt.status === "completed" && !engByAppt[appt.id] && <button type="button" data-row-hire onClick={() => setHireFor(appt)} style={{ ...hubBtn("prim", t), fontFamily: "inherit" }}>Hire</button>}
                                        {appt.status === "completed" && <button type="button" data-row-review onClick={() => setReviewFor(appt)} style={{ ...hubBtn("ghost", t), fontFamily: "inherit" }}>Review</button>}
                                        {appt.status === "completed" && engByAppt[appt.id] && (() => {
                                            const eng = engByAppt[appt.id];
                                            const st = eng.status;
                                            // "Open case" opens THAT case (2026-11-23), not whichever Tracking picks first.
                                            const [label, href, kind] = st === "terms_proposed" ? ["Review terms", "/lawyers", "prim"]
                                                : st === "requested" ? ["Hire requested", "/lawyers", "ghost"]
                                                : (st === "accepted" || st === "completed") ? ["Open case", matterHref(eng.case_id, { engagement: eng.id }), "ghost"] : [null];
                                            if (!label) return null;
                                            return HIRE_HERE.has(st)
                                                ? <button type="button" data-hire-state={st} onClick={() => setHireFor(appt)} style={{ ...hubBtn(kind, t), fontFamily: "inherit" }}>{label}</button>
                                                : <a href={href} data-hire-state={st} style={hubBtn(kind, t)}>{label}</a>;
                                        })()}
                                    </div>
                                </div>
                            </article>
                        );
                    })}
                    {moreError && <div role="alert" style={{ fontSize: 12.5, color: t.danger }}>{moreError} The appointments already shown are unaffected.</div>}
                    <div style={{ textAlign: "center" }}>
                        {!complete && appointments.length > 0 && (
                            <button type="button" onClick={onLoadMore} disabled={loadingMore} style={hubBtn("ghost", t)}>{loadingMore ? "Loading…" : "Load more appointments"}</button>
                        )}
                        {appointments.length > 0 && (
                            <div style={{ fontSize: 11.5, color: t.textFaint, marginTop: 8 }}>
                                {Number.isInteger(total) ? `Showing ${appointments.length} of ${total}` : `Showing ${appointments.length}`}{complete ? " — that is all of them." : ""}
                            </div>
                        )}
                    </div>
                </section>
            </div>
        </div>
    );
}

/* Line icons for the appointment page (24-unit grid, stroked). */
const DT_ICON = {
    cal: <><rect x="3.5" y="5" width="17" height="15" rx="2.5" /><path d="M8 3v4M16 3v4M3.5 10h17" /></>,
    clock: <><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></>,
    video: <><rect x="3" y="6.5" width="12.5" height="11" rx="2.5" /><path d="m15.5 10.5 5-3v9l-5-3z" /></>,
    phone: <path d="M6.5 3.5h3l1.6 4.4-2 1.3a11 11 0 0 0 5.7 5.7l1.3-2 4.4 1.6v3a2 2 0 0 1-2.2 2A16.5 16.5 0 0 1 4.5 5.7a2 2 0 0 1 2-2.2z" />,
    in_person: <><path d="M12 21s-6.5-5.8-6.5-11a6.5 6.5 0 0 1 13 0c0 5.2-6.5 11-6.5 11z" /><circle cx="12" cy="10" r="2.4" /></>,
    file: <><path d="M7 3h7l5 5v13H7z" /><path d="M14 3v5h5M10 13h6M10 17h4" /></>,
    link: <><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1" /><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" /></>,
    hourglass: <path d="M7 3.5h10M7 20.5h10M8 3.5c0 4.5 8 5 8 8.5s-8 4-8 8.5M16 3.5c0 4.5-8 5-8 8.5s8 4 8 8.5" />,
    check: <><circle cx="12" cy="12" r="8.5" /><path d="m8.3 12.2 2.5 2.5 4.9-5" /></>,
    x: <><circle cx="12" cy="12" r="8.5" /><path d="m9.2 9.2 5.6 5.6M14.8 9.2l-5.6 5.6" /></>,
    calPlus: <><rect x="3.5" y="5" width="17" height="15" rx="2.5" /><path d="M8 3v4M16 3v4M3.5 10h17M12 13v5M9.5 15.5h5" /></>,
    info: <><circle cx="12" cy="12" r="8.5" /><path d="M12 11v5M12 8h.01" /></>,
    hire: <><rect x="3.5" y="7.5" width="17" height="12" rx="2.5" /><path d="M9 7.5V6a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v1.5M3.5 13h17" /></>,
    star: <path d="m12 4 2.4 5 5.4.6-4 3.7 1.1 5.4L12 16l-4.9 2.7 1.1-5.4-4-3.7 5.4-.6z" />,
    search: <><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4.5 4.5" /></>,
    download: <><path d="M12 4v11M7.5 10.5 12 15l4.5-4.5" /><path d="M5 19.5h14" /></>,
    copy: <><rect x="8.5" y="8.5" width="11" height="11" rx="2.5" /><path d="M15.5 8.5V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7.5a2 2 0 0 0 2 2h2.5" /></>,
    spark: <><path d="M12 3l1.8 4.6L18.5 9l-4.7 1.6L12 15l-1.8-4.4L5.5 9l4.7-1.4z" /><path d="M18 15l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z" /></>,
    repeat: <><path d="M4 12a8 8 0 0 1 13.7-5.6L20 8.5" /><path d="M20 4v4.5h-4.5M20 12a8 8 0 0 1-13.7 5.6L4 15.5" /><path d="M4 20v-4.5h4.5" /></>,
};
function DtIcon({ name, size = 20 }) {
    return (
        <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
            {DT_ICON[name]}
        </svg>
    );
}
const DT_CSS = `
[data-appointment-detail] .dt-check{transition:background .15s, border-color .15s}
[data-appointment-detail] .dt-check-input:focus-visible + .dt-check{outline:2px solid var(--dt-accent);outline-offset:2px}
[data-appointment-detail] .dt-opt{transition:border-color .15s, transform .15s}
[data-appointment-detail] .dt-opt:hover{border-color:var(--dt-accent);transform:translateY(-2px)}
[data-appointment-detail] [data-detail-actions] button{max-width:none!important;border-radius:12px!important;transition:background .15s, border-color .15s, filter .15s}
[data-appointment-detail] [data-cancel-start]{background:color-mix(in srgb, var(--dt-danger) 10%, transparent)!important;border-color:color-mix(in srgb, var(--dt-danger) 35%, transparent)!important}
[data-appointment-detail] [data-cancel-start]:hover{background:color-mix(in srgb, var(--dt-danger) 18%, transparent)!important;border-color:color-mix(in srgb, var(--dt-danger) 65%, transparent)!important}
[data-appointment-detail] [data-cancel-yes]:hover:not(:disabled){filter:brightness(.9)}
[data-appointment-detail] [data-cancel-keep]:hover:not(:disabled){border-color:var(--dt-accent)!important;color:var(--dt-accent)!important}
[data-appointment-detail] [data-reschedule-start]:hover{border-color:var(--dt-accent)!important;color:var(--dt-accent)!important}
[data-appointment-detail] .dt-join{transition:background .15s}
[data-appointment-detail] .dt-join:hover{background:#0f6b5b!important}
[data-appointment-detail] .dt-gcal{transition:background .15s, border-color .15s}
[data-appointment-detail] .dt-gcal.solid:hover{background:#1765cc!important}
[data-appointment-detail] .dt-gcal.line:hover{background:rgba(138,180,248,.10)!important;border-color:#8ab4f8!important}
[data-appointment-detail] .dt-ghost:hover{border-color:var(--dt-accent)!important;color:var(--dt-accent)!important}
`;

function AppointmentDetail({ appt, t, onBack, onReload, cancelErrors, setCancelError, caseTitles = {}, engagement = null, openThread = false, onHire = null }) {
    const [reviewOpen, setReviewOpen] = useState(false);
    const video = useVideoConfigured();
    // The thread opens from "Message lawyer", the cutoff note or a message notification.
    const [threadOpen, setThreadOpen] = useState(Boolean(openThread));
    useEffect(() => { if (openThread) setThreadOpen(true); }, [openThread]);
    const openMessages = () => {
        setThreadOpen(true);
        setTimeout(() => {
            try { document.querySelector("[data-detail-messages]")?.scrollIntoView?.({ block: "center", behavior: "smooth" }); } catch { /* not in a browser */ }
        }, 50);
    };
    const [ready, setReady] = useState({});
    const [copied, setCopied] = useState(null);
    const chip = hubChip(appt, t);
    const c = cardOf(appt);
    const name = appt.lawyer_name || "your lawyer";
    const first = String(name).split(" ")[0];
    const live = appt.status === "pending" || (appt.status === "confirmed" && !apptEnded(appt));
    const upcomingConfirmed = appt.status === "confirmed" && !apptEnded(appt);
    const box = { borderRadius: 18, background: t.card, border: `1px solid ${t.border}` };
    const endIso = appt.end_at || new Date(new Date(appt.scheduled_at).getTime() + (appt.duration_minutes || 60) * 60000).toISOString();
    const err = (cancelErrors || {})[appt.id] || null;
    const specs = (c.specializations || []).map(titleCase).slice(0, 2).join(", ");
    const lastItem = { video: "Test your camera and microphone", phone: "Be somewhere quiet with your documents in hand", in_person: "Bring the related documents and your CNIC" }[appt.mode] || "Keep the related documents ready";
    const checks = [["dates", "Write down the key dates (notices, hearings)"], ["questions", "List the questions you want answered"], ["last", lastItem]];
    const doneCount = Object.values(ready).filter(Boolean).length + (appt.notes ? 1 : 0);
    const totalChecks = checks.length + (appt.notes ? 1 : 0);
    const copy = async (what, text) => { if (await copyText(text)) { setCopied(what); setTimeout(() => setCopied(null), 1600); } };
    // One colour per state, carried by the header, the panels and the timeline.
    const tone = appt.status === "pending" ? t.warn
        : appt.status === "cancelled" ? t.danger
        : upcomingConfirmed || appt.status === "completed" ? t.primary : t.textMuted;
    const tint = (col, pct) => `color-mix(in srgb, ${col} ${pct}%, transparent)`;
    // A plain line icon, no tile behind it: the tinted box read as decoration.
    const iconTile = (icon, col, size = 44) => (
        <span aria-hidden="true" style={{ display: "flex", flexShrink: 0, color: col }}>
            <DtIcon name={icon} size={Math.round(size * 0.55)} />
        </span>
    );
    const sectionTitle = (text, extra) => (
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <h2 style={{ margin: 0, flex: 1, font: `700 16px/1.3 ${HUB_SERIF}`, color: t.text }}>{text}</h2>{extra}
        </div>
    );
    const rel = dayTag(appt.scheduled_at);
    const hiddenInput = { position: "absolute", left: 0, top: "50%", width: 1, height: 1, margin: 0, opacity: 0 };
    const tick = on => (
        <span aria-hidden="true" className="dt-check" style={{ width: 22, height: 22, flexShrink: 0, borderRadius: "50%", display: "grid", placeItems: "center", boxSizing: "border-box",
            border: on ? "none" : `1.8px solid ${t.textFaint}`, background: on ? t.primary : "transparent", color: "#06211a" }}>
            {on && <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.4" strokeLinecap="round" strokeLinejoin="round"><path d="m5 12.5 4.5 4.5L19 7.5" /></svg>}
        </span>
    );
    const timeline = [
        ["Request sent", appt.created_at ? formatPkt(appt.created_at, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }) : null, "done"],
        ...(appt.status === "cancelled" ? [[isDeclinedRequest(appt) ? "Declined" : "Cancelled", cancelledWho(appt), "end"]]
            : appt.status === "expired" ? [["Expired — not answered in time", null, "end"]]
            : [
                [appt.status === "pending" ? "Pending confirmation" : `Confirmed by ${first}`, appt.status === "pending" ? `${first} answers soon` : null, appt.status === "pending" ? "now" : "done"],
                // Each accepted move, and an open proposal (2026-10-19).
                ...(appt.reschedule_history || []).map((h, i) => [
                    i === 0 ? "Time changed" : `Time changed (${i + 1})`,
                    `${formatPkt(h.from, { day: "numeric", month: "short" })} ${hhmm(h.from)} → ${formatPkt(h.to, { day: "numeric", month: "short" })} ${hhmm(h.to)} · proposed by ${h.proposed_by === "client" ? "you" : first}`,
                    "done"]),
                ...(appt.status === "confirmed" && appt.reschedule_proposal && (!appt.reschedule_proposal.expires_at || new Date(appt.reschedule_proposal.expires_at) > new Date())
                    ? [["New time proposed", `${formatPkt(appt.reschedule_proposal.scheduled_at, { weekday: "short", day: "numeric", month: "short" })} · ${hhmm(appt.reschedule_proposal.scheduled_at)} — ${appt.reschedule_proposal.by === "client" ? `waiting for ${first}` : "waiting for you"}`, "now"]]
                    : []),
                ["Meeting", formatPkt(appt.scheduled_at, { weekday: "short", day: "numeric", month: "short" }) + " · " + hhmm(appt.scheduled_at),
                    appt.status === "completed" || appt.status === "no_show" ? "done" : appt.status === "confirmed" ? "now" : "next"],
                [appt.status === "no_show" ? "Recorded as a no-show" : "Summary & next step", null, appt.status === "completed" ? "now" : appt.status === "no_show" ? "end" : "next"],
            ]),
    ];
    const dot = state => state === "done" ? { background: t.primary } : state === "now" ? { border: `2.5px solid ${t.warn}`, background: t.card }
        : state === "end" ? { background: t.danger } : { border: `1.5px solid ${t.border}`, background: t.card };
    const panelHead = (icon, title, sub, col, right) => (
        <div style={{ display: "flex", gap: 14, alignItems: "center", flexWrap: "wrap" }}>
            {iconTile(icon, col)}
            <div style={{ flex: "1 1 240px", minWidth: 0 }}>
                <div style={{ font: `700 16px/1.3 ${HUB_SERIF}`, color: t.text }}>{title}</div>
                <div style={{ fontSize: 13.5, color: t.textMuted, marginTop: 2 }}>{sub}</div>
            </div>
            {right}
        </div>
    );
    // A value the client may need to copy (the link, the number), shown as a field.
    const field = (icon, label, value, copyKey, extra) => (
        <div style={{ display: "flex", gap: 12, alignItems: "center", padding: "10px 10px 10px 14px", borderRadius: 14, background: t.inputBg, border: `1px solid ${t.border}` }}>
            <span style={{ color: t.textMuted, display: "flex" }}><DtIcon name={icon} size={18} /></span>
            <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 11.5, fontWeight: 800, letterSpacing: ".04em", textTransform: "uppercase", color: t.textFaint }}>{label}</div>
                <div style={{ fontSize: 15, fontWeight: 700, color: t.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{value}</div>
            </div>
            {extra}
            <button type="button" className="dt-ghost" onClick={() => copy(copyKey, value)} style={{ ...hubBtn("ghost", t), height: 36 }}><DtIcon name="copy" size={16} />{copied === copyKey ? "Copied" : "Copy"}</button>
        </div>
    );
    const meta = [
        ["cal", "Date", formatPkt(appt.scheduled_at, { weekday: "short", day: "numeric", month: "short", year: "numeric" }),
            rel === "TODAY" ? "Today" : rel === "TOMORROW" ? "Tomorrow" : null],
        ["clock", "Time", `${hhmm(appt.scheduled_at)} – ${hhmm(endIso)} PKT`, `${appt.duration_minutes || 60} minutes`],
        [appt.mode in DT_ICON ? appt.mode : "video", "How", MODE_LONG[appt.mode] || appt.mode,
            { video: video && !appt.meeting_link ? "Online, in the app" : "Online, by a video link", phone: `${first} calls you`, in_person: "At the lawyer's office" }[appt.mode] || null],
        ["file", "About", aboutOf(appt, caseTitles), appt.case_id ? "Linked case" : "Not tied to a case"],
    ];

    return (
        <div data-appointment-detail={appt.id} style={{ display: "flex", flexDirection: "column", gap: 16, "--dt-hover": tint(t.text, 4), "--dt-accent": t.primary, "--dt-danger": t.danger }}>
            <style>{DT_CSS}</style>
            <button type="button" data-back-to-hub onClick={onBack} style={{ alignSelf: "flex-start", border: "none", background: "transparent", padding: 0, color: t.primary, fontSize: 13.5, fontWeight: 700, cursor: "pointer", fontFamily: "inherit" }}>← Back to appointments</button>

            {/* Who, and when: the state's colour washes the header. */}
            <section data-detail-head style={{ ...box, overflow: "hidden", borderColor: `color-mix(in srgb, ${tone} 35%, ${t.border})`,
                background: `linear-gradient(120deg, color-mix(in srgb, ${tone} 14%, ${t.card}) 0%, ${t.card} 55%)` }}>
                <div style={{ display: "flex", gap: 18, alignItems: "center", padding: "22px 24px" }}>
                    <span aria-hidden="true" style={{ width: 68, height: 68, flexShrink: 0, borderRadius: "50%", display: "grid", placeItems: "center", fontWeight: 800, fontSize: 21, color: "#fff", background: GRAD,
                        boxShadow: `0 0 0 4px ${t.card}, 0 0 0 6px ${tint(tone, 45)}` }}>{initialsOf(appt.lawyer_name)}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                        <h1 style={{ margin: 0, font: `600 26px/1.2 ${HUB_TITLE}`, color: t.text }}>{appt.lawyer_name || "Your lawyer"}</h1>
                        <div style={{ fontSize: 13.5, color: t.textMuted, marginTop: 3 }}>{["Lawyer", specs, c.experience_years ? `${c.experience_years} years experience` : null].filter(Boolean).join(" · ")}</div>
                        {c.total_reviews > 0 && <div style={{ fontSize: 13, marginTop: 4, color: t.text, display: "flex", alignItems: "center", gap: 5 }}><span style={{ color: "#F2C35E" }}>★</span> <b>{Number(c.rating).toFixed(1)}</b> <span style={{ color: t.textMuted }}>({c.total_reviews} reviews)</span></div>}
                    </div>
                    <span style={{ height: 34, display: "inline-flex", alignItems: "center", padding: "0 15px", borderRadius: 999, background: chip.bg, color: chip.color, fontSize: 13, fontWeight: 800, whiteSpace: "nowrap", border: `1px solid ${tint(chip.color, 30)}` }}>{chip.text}</span>
                </div>
                <div data-detail-meta style={{ display: "grid", gridTemplateColumns: "repeat(4,minmax(0,1fr))", borderTop: `1px solid ${t.border}`, background: tint(t.bg, 35) }}>
                    {meta.map(([icon, label, value, sub], i) => (
                        <div key={label} style={{ display: "flex", gap: 12, alignItems: "center", padding: "14px 20px", minWidth: 0, borderLeft: i ? `1px solid ${t.border}` : "none" }}>
                            {iconTile(icon, i === 2 ? tone : t.textMuted, 36)}
                            <div style={{ minWidth: 0 }}>
                                <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: ".06em", textTransform: "uppercase", color: t.textFaint }}>{label}</div>
                                <div style={{ fontSize: 14, fontWeight: 700, color: t.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{value}</div>
                                {sub && <div style={{ fontSize: 12, color: t.textMuted }}>{sub}</div>}
                            </div>
                        </div>
                    ))}
                </div>
            </section>

            <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 340px", gap: 16, alignItems: "start" }}>
                <div style={{ display: "flex", flexDirection: "column", gap: 16, minWidth: 0 }}>
                    {appt.status === "pending" && !appt.time_suggestion?.options?.length && (
                        <div role="note" data-waiting-note style={{ display: "flex", gap: 14, alignItems: "center", padding: "14px 18px", borderRadius: 16, background: tint(t.warn, 9), border: `1px solid ${tint(t.warn, 38)}` }}>
                            {iconTile("hourglass", t.warn, 40)}
                            <div>
                                <b style={{ fontSize: 14.5, color: t.text }}>Waiting for {first} to confirm</b>
                                <div style={{ fontSize: 13, color: t.textMuted, marginTop: 2 }}>You'll be notified once they answer{appt.mode === "in_person" ? " — please don't travel until it's confirmed" : ""}.</div>
                            </div>
                        </div>
                    )}

                    <ApptSuggestion appt={appt} t={t} onReload={onReload} first={first} />

                    {/* How the meeting happens, by mode */}
                    {live && appt.mode === "video" && (
                        <section aria-label="Join" data-mode-panel="video" style={{ ...box, padding: "20px 22px", display: "flex", flexDirection: "column", gap: 16, borderColor: upcomingConfirmed ? tint(t.primary, 45) : t.border }}>
                            {panelHead("video", upcomingConfirmed ? `Video consultation · starts ${untilWords(appt.scheduled_at)}` : "Video consultation",
                                upcomingConfirmed ? (appt.meeting_link ? "Your meeting link is ready. Join at the scheduled time." : video ? "Join the video call right here in the app — it opens a day before the start." : "Joining link not shared yet — your lawyer will add it.")
                                    : "The joining link appears here once the lawyer confirms.", t.primary,
                                upcomingConfirmed && appt.meeting_link ? <a href={appt.meeting_link} target="_blank" rel="noreferrer" className="dt-join" style={{ ...hubBtn("prim", t), height: 44, minWidth: 180, padding: "0 22px", borderRadius: 999, background: "#13806b" }}><DtIcon name="video" size={19} />Join meeting</a> : null)}
                            {upcomingConfirmed && appt.meeting_link && (<>
                                {field("link", "Meeting link", appt.meeting_link.replace(/^https:\/\//, ""), "link")}
                                <div style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12.5, color: t.textFaint }}><DtIcon name="info" size={15} /> You can join a few minutes before the meeting time.</div>
                            </>)}
                            {/* In-app video; renders nothing unless it is set up. */}
                            {upcomingConfirmed && <ClientJoinVideo appt={appt} t={t} onMessage={openMessages} />}
                        </section>
                    )}
                    {live && appt.mode === "phone" && (
                        <section aria-label="Phone" data-mode-panel="phone" style={{ ...box, padding: "20px 22px", display: "flex", flexDirection: "column", gap: 16, borderColor: upcomingConfirmed ? tint("#6ADDEB", 40) : t.border }}>
                            {panelHead("phone", upcomingConfirmed ? `Phone consultation · starts ${untilWords(appt.scheduled_at)}` : "Phone consultation",
                                upcomingConfirmed ? `${first} will call you at the scheduled time. Keep your phone free.` : "The lawyer's number appears here once they confirm.", "#6ADDEB")}
                            {upcomingConfirmed && (c.phone ? (<>
                                {field("phone", "Lawyer's number", c.phone, "phone",
                                    <a href={`tel:${c.phone.replace(/[^\d+]/g, "")}`} style={{ ...hubBtn("prim", t), height: 36 }}>Call</a>)}
                                <div style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12.5, color: t.textFaint }}><DtIcon name="info" size={15} /> Shown only for a confirmed phone consultation.</div>
                            </>) : <div style={{ fontSize: 13, color: t.textMuted }}>Confirm the number with your lawyer before the time.</div>)}
                        </section>
                    )}
                    {live && appt.mode === "in_person" && (
                        <section aria-label="Meeting location" data-mode-panel="in_person" style={{ ...box, padding: "20px 22px", display: "flex", flexDirection: "column", gap: 16, borderColor: upcomingConfirmed ? tint(t.primary, 45) : t.border }}>
                            {panelHead("in_person", "Meeting location", c.office_address ? "Lawyer's office" : "Ask your lawyer for the office address.", t.primary,
                                <div style={{ display: "flex", gap: 8 }}>
                                    {mapsHref(appt, false) && <a href={mapsHref(appt, false)} target="_blank" rel="noreferrer" className="dt-ghost" style={hubBtn("ghost", t)}>View on map</a>}
                                    {mapsHref(appt, true) && <a href={mapsHref(appt, true)} target="_blank" rel="noreferrer" style={hubBtn("prim", t)}>Directions</a>}
                                </div>)}
                            {c.office_address && (
                                <div style={{ display: "flex", gap: 12, alignItems: "center", padding: "12px 14px", borderRadius: 14, background: t.inputBg, border: `1px solid ${t.border}` }}>
                                    <span style={{ color: t.primary, display: "flex" }}><DtIcon name="in_person" size={18} /></span>
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                        <div style={{ fontSize: 11.5, fontWeight: 800, letterSpacing: ".04em", textTransform: "uppercase", color: t.textFaint }}>Address</div>
                                        <div style={{ fontSize: 15, fontWeight: 700, color: t.text }}>{c.office_address}</div>
                                    </div>
                                </div>
                            )}
                        </section>
                    )}
                    <section aria-label="Messages" data-detail-messages style={{ ...box, padding: "18px 20px", display: "flex", flexDirection: "column" }}>
                        <ApptMessages appt={appt} t={t} open={threadOpen} onOpenChange={setThreadOpen} />
                    </section>
                    {appt.status === "confirmed" && apptEnded(appt) && (
                        <section aria-label="Ended" style={{ ...box, padding: "20px 22px" }}>
                            {panelHead("clock", "This consultation has ended", `${first} marks it complete; then you can hire them, book a follow-up or leave a review.`, t.textMuted)}
                        </section>
                    )}
                    {appt.status === "completed" && (
                        <section aria-label="Next step" style={{ ...box, padding: "20px 22px", display: "flex", flexDirection: "column", gap: 16 }}>
                            {panelHead("check", "Consultation completed", `You met ${first} on ${formatPkt(appt.scheduled_at, { weekday: "short", day: "numeric", month: "short" })}. Here is what you can do next.`, t.primary)}
                            <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: 12 }}>
                                {[(() => {
                                    // Where the hire request from THIS consultation stands (one rule: hireAction).
                                    const [title, sub, href, cta, kind] = hireAction(appt, engagement);
                                    return ["hire", title, sub, href, kind, cta];
                                })(),
                                  ["file", "Get a document reviewed", "Send one draft for a quick review.", "/documents", "ghost", "Choose a document"],
                                  ["repeat", "Book a follow-up", "Same lawyer — pick a new time.", lawyerHref(appt, "book"), "ghost", "Pick a time"],
                                  ["star", "Rate this consultation", "Helps other clients choose.", lawyerHref(appt, "review"), "ghost", "Write a review"]].map(([icon, title, sub, href, kind, cta]) => (
                                    <div key={title} className="dt-opt" style={{ padding: 16, borderRadius: 16, background: t.inputBg, border: `1px solid ${kind === "prim" ? tint(t.primary, 50) : t.border}`, display: "flex", flexDirection: "column", gap: 10 }}>
                                        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                                            {iconTile(icon, kind === "prim" ? t.primary : t.textMuted, 38)}
                                            <b style={{ fontSize: 15, color: t.text }}>{title}</b>
                                        </div>
                                        <div style={{ fontSize: 12.5, color: t.textMuted, flex: 1, lineHeight: 1.5 }}>{sub}</div>
                                        {icon === "star"
                                            ? <button type="button" data-detail-review className="dt-ghost" onClick={() => setReviewOpen(true)} style={{ ...hubBtn(kind, t), fontFamily: "inherit" }}>{cta}</button>
                                            : icon === "hire" && onHire && HIRE_HERE.has(engagement?.status || "none")
                                            ? <button type="button" data-detail-hire className={kind === "prim" ? undefined : "dt-ghost"} onClick={() => onHire(appt)} style={{ ...hubBtn(kind, t), fontFamily: "inherit" }}>{cta}</button>
                                            : <a href={href} className={kind === "prim" ? undefined : "dt-ghost"} style={hubBtn(kind, t)}>{cta}</a>}
                                    </div>
                                ))}
                                {reviewOpen && <ReviewLawyerDialog lawyerId={appt.lawyer_id} lawyerName={appt.lawyer_name} t={t} onClose={() => setReviewOpen(false)} />}
                            </div>
                        </section>
                    )}
                    {(appt.status === "cancelled" || appt.status === "expired" || appt.status === "no_show") && (
                        <section aria-label="Closed" style={{ ...box, padding: "20px 22px", display: "flex", flexDirection: "column", gap: 4 }}>
                            {panelHead(appt.status === "expired" ? "hourglass" : "x",
                                appt.status === "cancelled" ? (appt.outcome_code === "lawyer_no_show" ? "Your lawyer couldn't attend" : appt.outcome_code === "did_not_take_place" ? "This appointment didn't take place" : isDeclinedRequest(appt) ? "Your request was declined" : "This appointment was cancelled") : appt.status === "expired" ? "This request expired" : "Recorded as a no-show",
                                appt.status === "no_show" ? "The meeting did not take place." : (appt.status === "expired" ? "The lawyer did not answer before the time." : "It will not take place at this time."), tone)}
                            <CancellationDetail appt={appt} t={t} />
                            <ExpiryDetail appt={appt} t={t} />
                            <div style={{ font: `700 15px/1.3 ${HUB_SERIF}`, color: t.text, marginTop: 16 }}>What you can do now</div>
                            <div style={{ display: "grid", gridTemplateColumns: "repeat(3,minmax(0,1fr))", gap: 12, marginTop: 8 }}>
                                {[["repeat", "Book a new time", `Pick another time with ${first}.`, lawyerHref(appt, "book"), "prim", "Book a new time"],
                                  ["search", "Try another lawyer", "Compare lawyers by practice area, city and fee.", "/lawyers", "ghost", "Browse lawyers"],
                                  ["spark", "Ask AI meanwhile", "Get a first view of your issue while you rebook.", "/chat", "ghost", "Open AI Chat"]].map(([icon, title, sub, href, kind, cta]) => (
                                    <div key={title} className="dt-opt" style={{ padding: 16, borderRadius: 16, background: t.inputBg, border: `1px solid ${kind === "prim" ? tint(t.primary, 50) : t.border}`, display: "flex", flexDirection: "column", gap: 10 }}>
                                        {iconTile(icon, kind === "prim" ? t.primary : t.textMuted, 38)}
                                        <b style={{ fontSize: 14.5, color: t.text }}>{title}</b>
                                        <div style={{ fontSize: 12.5, color: t.textMuted, flex: 1, lineHeight: 1.5 }}>{sub}</div>
                                        {icon === "star"
                                            ? <button type="button" data-detail-review className="dt-ghost" onClick={() => setReviewOpen(true)} style={{ ...hubBtn(kind, t), fontFamily: "inherit" }}>{cta}</button>
                                            : icon === "hire" && onHire && HIRE_HERE.has(engagement?.status || "none")
                                            ? <button type="button" data-detail-hire className={kind === "prim" ? undefined : "dt-ghost"} onClick={() => onHire(appt)} style={{ ...hubBtn(kind, t), fontFamily: "inherit" }}>{cta}</button>
                                            : <a href={href} className={kind === "prim" ? undefined : "dt-ghost"} style={hubBtn(kind, t)}>{cta}</a>}
                                    </div>
                                ))}
                                {reviewOpen && <ReviewLawyerDialog lawyerId={appt.lawyer_id} lawyerName={appt.lawyer_name} t={t} onClose={() => setReviewOpen(false)} />}
                            </div>
                        </section>
                    )}

                    {live && (
                        <section aria-label="Preparation checklist" style={{ ...box, padding: "20px 22px" }}>
                            {sectionTitle("Preparation checklist",
                                <span style={{ fontSize: 12.5, fontWeight: 700, color: doneCount === totalChecks ? t.primary : t.textMuted }}>{doneCount} of {totalChecks} completed</span>)}
                            <div style={{ height: 6, borderRadius: 99, background: tint(t.text, 10), margin: "12px 0 8px", overflow: "hidden" }}>
                                <div style={{ width: `${Math.round(doneCount / totalChecks * 100)}%`, height: "100%", borderRadius: 99, background: GRAD, transition: "width .2s" }} />
                            </div>
                            {appt.notes && <label style={{ position: "relative", display: "flex", gap: 12, alignItems: "center", padding: "11px 0", fontSize: 14, color: t.text }}><input type="checkbox" checked readOnly className="dt-check-input" style={hiddenInput} />{tick(true)} {appt.from_proposal ? `Agenda from ${first}` : "Your note"}: “{appt.notes}”</label>}
                            {checks.map(([k, text]) => (
                                <label key={k} style={{ position: "relative", display: "flex", gap: 12, alignItems: "center", padding: "11px 0", fontSize: 14, color: ready[k] ? t.textMuted : t.text, cursor: "pointer" }}>
                                    <input type="checkbox" checked={!!ready[k]} onChange={e => setReady(r => ({ ...r, [k]: e.target.checked }))} className="dt-check-input" style={hiddenInput} />{tick(!!ready[k])} {text}
                                </label>
                            ))}
                            <ApptSummaryShare appt={appt} t={t} first={first} />
                            <ApptFiles appt={appt} t={t} />
                        </section>
                    )}
                    <ReportIssue appt={appt} t={t} />
                </div>

                <aside style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                    {/* A refused cancel or move (422 cutoff, 409 conflict) reloads the
                        appointment, and a finished one has no Manage panel; the reason
                        is still owed, so it stays here (2026-11-23). */}
                    {!live && err && (
                        <div role="alert" data-detail-error style={{ ...box, padding: "12px 16px", fontSize: 13, fontWeight: 600, color: t.danger }}>{err}</div>
                    )}
                    {live && (
                        <section aria-label="Manage appointment" data-detail-manage style={{ ...box, padding: "18px 20px", display: "flex", flexDirection: "column", gap: 4 }}>
                            {sectionTitle("Manage appointment")}
                            {upcomingConfirmed && (
                                <div data-add-calendar style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 12 }}>
                                    <div style={{ fontSize: 12, fontWeight: 700, color: t.textMuted }}>Add to calendar <span style={{ fontWeight: 600, color: t.textFaint }}>(optional)</span></div>
                                    <a href={googleCalendarHref(appt)} target="_blank" rel="noreferrer" data-google-calendar className="dt-gcal solid"
                                        style={{ ...hubBtn("prim", t), width: "100%", height: 44, background: "#1a73e8" }}>
                                        <DtIcon name="calPlus" size={18} /> Google Calendar
                                    </a>
                                    {/* Outlook / Apple Calendar users still need the file, but it
                                        does not need a second big button. */}
                                    <button type="button" data-ics onClick={() => downloadIcs(appt)}
                                        style={{ alignSelf: "center", background: "none", border: "none", padding: "2px 4px", cursor: "pointer", fontFamily: "inherit", fontSize: 12.5, fontWeight: 600, color: t.textMuted, display: "inline-flex", alignItems: "center", gap: 6 }}>
                                        <DtIcon name="download" size={14} /> Outlook / Apple Calendar (.ics)
                                    </button>
                                </div>
                            )}
                            <div data-detail-actions style={{ display: "flex", flexDirection: "column" }}>
                                <RescheduleAppointment appt={appt} t={t} onReload={onReload} error={err} setError={setCancelError} />
                                <ApptMoveProposal appt={appt} t={t} onReload={onReload} first={first} />
                                <CancelAppointment appt={appt} t={t} onReload={onReload} error={err} setError={setCancelError} onMessage={openMessages} />
                            </div>
                            <div style={{ display: "flex", gap: 10, marginTop: 14, paddingTop: 14, borderTop: `1px solid ${t.border}`, fontSize: 12.5, color: t.textMuted, lineHeight: 1.5 }}>
                                <span style={{ color: t.primary, display: "flex", marginTop: 1 }}><DtIcon name="info" size={16} /></span>
                                <div><b style={{ color: t.text }}>Need to make a change?</b><br />{appt.status === "pending"
                                    ? "You can change the time or cancel while it's waiting."
                                    : `Propose a new time and your lawyer accepts or declines — or cancel up to ${CANCEL_CUTOFF_HOURS} hours before.`}</div>
                            </div>
                        </section>
                    )}
                    <section aria-label="Appointment timeline" style={{ ...box, padding: "18px 20px", display: "flex", flexDirection: "column", gap: 14 }}>
                        {sectionTitle("Appointment timeline")}
                        <div>
                            {timeline.map(([title, sub, state], i) => (
                                <div key={title} style={{ display: "flex", gap: 14, fontSize: 13.5 }}>
                                    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0 }}>
                                        <i aria-hidden="true" style={{ width: 14, height: 14, borderRadius: "50%", marginTop: 3, boxSizing: "border-box", ...dot(state) }} />
                                        {i < timeline.length - 1 && <span aria-hidden="true" style={{ flex: 1, width: 2, minHeight: 18, margin: "4px 0", borderRadius: 2, background: state === "done" ? tint(t.primary, 55) : t.border }} />}
                                    </div>
                                    <div style={{ paddingBottom: i < timeline.length - 1 ? 16 : 0 }}>
                                        <b style={{ color: state === "now" ? t.warn : state === "next" ? t.textMuted : state === "end" ? t.danger : t.text }}>{title}</b>
                                        {sub && <div style={{ color: t.textMuted, fontSize: 12.5, marginTop: 2 }}>{sub}</div>}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </section>
                </aside>
            </div>
        </div>
    );
}

// Appointments have one page, /appointments (2026-11-23). Tracking's own
// Appointments tab showed the same list a second time, in older cards; it was
// removed once every test of it had moved to this page.
const AppointmentsPage = ({ standalone, ...props }) => <AppointmentsHub {...props} />;

// ─── ROOT ─────────────────────────────────────────────────────────────────────
// Fix #2: accepts isDark from Dashboard — no longer owns its own theme state.
// Fix #5: reads appointmentMilestones from CaseContext so booked appointments
//         appear on the timeline immediately.
export default function Module7({ isDark, standalone = null }) {
    const t = clientThemeOnTokens(isDark ? DARK : LIGHT);
    const isMobile = useIsMobile();
    const { appointmentMilestones } = useCase();
    const [page, setPage] = useState(standalone || "overview");
    // Opened on one appointment (?appointment=<id>, after booking). Read
    // through the router: after router.push from the booking dialog,
    // window.location still holds the previous URL during the first render,
    // so reading only that missed the id and left the client on the hub.
    // window.location stays as the fallback for a direct page load.
    const searchParams = useSearchParams();
    const focusAppt = searchParams?.get("appointment") || (() => {
        try { return new URLSearchParams(window.location.search).get("appointment"); } catch { return null; }
    })();
    const threadParam = searchParams?.get("thread") || (() => {
        try { return new URLSearchParams(window.location.search).get("thread"); } catch { return null; }
    })();
    const openThreadId = threadParam === "open" ? focusAppt : null;
    // My Matters links (2026-11-23): ?case=<id>&tab=<summary|timeline|documents|messages|payments>
    // [&engagement=<id>]. The case and tab survive refresh, Back and a
    // notification click; a case that cannot be opened is said so, never
    // silently swapped for the newest one.
    const caseParam = standalone ? null : (searchParams?.get("case") || null);
    const tabParam = standalone ? null : (searchParams?.get("tab") || null);
    const engagementParam = standalone ? null : (searchParams?.get("engagement") || null);
    const paymentParam = standalone ? null : (searchParams?.get("payment") || null);
    const documentParam = standalone ? null : (searchParams?.get("document") || null);
    const agreementParam = standalone ? null : (searchParams?.get("agreement") || null);
    // The status card's "Review terms" opens the request below it (v2).
    const [focusEngagement, setFocusEngagement] = useState(null);
    const [focusPayment, setFocusPayment] = useState(null);
    const clientRouter = useClientRouter();
    const [caseLinkError, setCaseLinkError] = useState(null);   // null | "missing" | "draft"
    const [caseLinkLoading, setCaseLinkLoading] = useState(() => !!caseParam);
    const [caseLinkTry, setCaseLinkTry] = useState(0);
    // My matters (v2): shown when /tracking names no case and no tab; a link
    // that names either opens the case as before.
    // All my payments (2026-11-23): every fee across cases, with NO case
    // header. /tracking?view=payments, and an old fee link that names a
    // payment but no case (it used to open under whichever case came first).
    const viewParam = standalone ? null : (searchParams?.get("view") || null);
    const globalPayments = !standalone && !caseParam && (viewParam === "payments" || (tabParam === "payments" && !!paymentParam));
    const [showAllPayments, setShowAllPayments] = useState(() => globalPayments);
    const [showMatters, setShowMatters] = useState(() => !standalone && !caseParam && !globalPayments);
    useEffect(() => {
        if (globalPayments) { setShowAllPayments(true); setShowMatters(false); }
        else if (caseParam) { setShowAllPayments(false); setShowMatters(false); }
        else if (!standalone) { setShowAllPayments(false); setShowMatters(true); }
    }, [standalone, globalPayments, caseParam]);
    useEffect(() => {
        if (tabParam && TAB_TO_PAGE[tabParam]) setPage(TAB_TO_PAGE[tabParam]);
    }, [tabParam]);
    const [activeCaseId, setActiveCaseId] = useState(null);
    const [apiCases, setApiCases] = useState([]);
    const [casesState, setCasesState] = useState("loading");   // loading | ready | error
    const [apiMilestones, setApiMilestones] = useState([]);
    const [apiHearings, setApiHearings] = useState([]);
    // loading | ready | error for the open case's timeline: a failed read is
    // never shown as "no hearings" (2026-11-23).
    const [timelineState, setTimelineState] = useState("loading");
    const [timelineTry, setTimelineTry] = useState(0);
    const [apiAppointments, setApiAppointments] = useState([]);
    const [apptLoading, setApptLoading] = useState(false);
    // Cancellation failures, keyed by appointment id. Held here because a
    // reload re-creates the page subtree below and would take any state it
    // owned with it — see CancelAppointment.
    const [cancelErrors, setCancelErrors] = useState({});
    // Set when a READ fails. Distinct from a cancellation error: this one says
    // the list on screen may be out of date, not that an action was refused.
    const [apptRefreshError, setApptRefreshError] = useState(null);
    // PAGING. Every caller used to ask for fifty and stop — which is the first
    // fifty by the server's sort, not "all", so a client with a longer history
    // saw a truncated diary with nothing saying so.
    //
    // `apptPages === null` means the server has not said yet, which is NOT the
    // same as "one page": the list must never claim to be complete on that.
    const [apptPage, setApptPage] = useState(1);
    const [apptPages, setApptPages] = useState(null);
    const [apptTotal, setApptTotal] = useState(null);
    const [apptLoadingMore, setApptLoadingMore] = useState(false);
    const [apptMoreError, setApptMoreError] = useState(null);
    const apptMoreInFlight = useRef(false);
    const casesReadSeq = useRef(0);
    const setCancelError = useCallback((id, message) => {
        setCancelErrors(prev => ({ ...prev, [id]: message }));
    }, []);

    // Load cases from API on mount (and again from "Try again").
    const [draftMatters, setDraftMatters] = useState([]);
    const loadCases = useCallback(async () => {
        const mine = ++casesReadSeq.current;
        setCasesState("loading");
        const all = [];
        let pageNumber = 1;
        let pages = 1;
        do {
            const { data, error } = await listCases({ page: pageNumber, page_size: 50 });
            if (mine !== casesReadSeq.current) return false;
            if (error || !Array.isArray(data?.items)) { setCasesState("error"); return false; }
            all.push(...data.items);
            pages = Number.isInteger(data.pages) ? data.pages : 1;
            pageNumber += 1;
        } while (pageNumber <= pages);
        // A successful empty read must clear stale rows from a prior refresh.
        if (mine !== casesReadSeq.current) return false;
        const unique = [...new Map(confirmedCases(all).map(row => [String(row?._id || row?.id || ""), row])).values()];
        setApiCases(unique.map(mapApiCase));
        // Drafts are not cases yet, but My matters shows them as "Not submitted
        // yet · Continue intake" (2026-11-25, as the approved preview).
        setDraftMatters([...new Map(all.filter(isDraftCase).map(row => [String(row?._id || row?.id || ""), row])).values()].map(mapApiCase));
        setCasesState("ready");
        return true;
    }, []);
    useEffect(() => { loadCases(); }, [loadCases]);
    useEffect(() => onNotification(n => {
        const type = String(n?.type || "");
        if (type === "case_update" || type === "lawyer_assigned" || type.startsWith("engagement_") || type.startsWith("hearing_")) loadCases();
        if ((type === "case_update" || type.startsWith("hearing_"))
            && (!n?.payload?.case_id || String(n.payload.case_id) === String(activeCaseId))) setTimelineTry(v => v + 1);
    }), [activeCaseId, loadCases]);

    // Which case is open. With ?case= it is THAT case: from the loaded page
    // when it is there, else read directly (the list holds the newest 20 only).
    // Without it, the newest confirmed case, as before.
    useEffect(() => {
        if (casesState === "loading") return undefined;
        // (The standalone Appointments page has no ?case=, so it takes the
        // newest case as before.)
        if (!caseParam) {
            setCaseLinkLoading(false);
            setCaseLinkError(null);
            setActiveCaseId(cur => (cur && apiCases.some(c => c.id === cur)) ? cur : (apiCases[0]?.id ?? null));
            return undefined;
        }
        if (apiCases.some(c => c.id === caseParam)) { setCaseLinkLoading(false); setCaseLinkError(null); setActiveCaseId(caseParam); return undefined; }
        let off = false;
        setCaseLinkLoading(true);
        getCase(caseParam).then(({ data, error, status }) => {
            if (off) return;
            setCaseLinkLoading(false);
            if (error || !data) {
                setActiveCaseId(null);
                setCaseLinkError(status === 404 ? "missing" : "load");
                return;
            }
            if (isDraftCase(data)) { setActiveCaseId(null); setCaseLinkError("draft"); return; }
            const one = mapApiCase(data);
            setApiCases(list => (list.some(c => c.id === one.id) ? list : [...list, one]));
            setActiveCaseId(one.id);
            setCaseLinkError(null);
        });
        return () => { off = true; };
    }, [standalone, casesState, caseParam, apiCases, caseLinkTry]);

    // Keep the address on what is on screen (refresh, share). This only
    // TIDIES the current entry (replace); a move the client makes is a new
    // history entry, pushed by goPage/goCase/goMatters/goAllPayments.
    useEffect(() => {
        if (standalone || typeof window === "undefined") return;
        // Only while the page really is /tracking: never rewrite another route.
        if (!["/tracking", "/cases"].includes(window.location.pathname)) return;
        if (showAllPayments) {
            const want = paymentParam && globalPayments ? `/tracking?view=payments&payment=${encodeURIComponent(paymentParam)}` : "/tracking?view=payments";
            if (window.location.pathname + window.location.search !== want) window.history.replaceState(null, "", want);
            return;
        }
        if (showMatters) {
            if (window.location.pathname + window.location.search !== "/tracking") window.history.replaceState(null, "", "/tracking");
            return;
        }
        if (caseLinkError || !activeCaseId) return;
        const tab = PAGE_TO_TAB[page];
        if (!tab) return;
        const href = matterHref(activeCaseId, {
            tab,
            // The request in focus stays in the address (pressed "Review terms" /
            // "View request", or arrived from a link naming it).
            engagement: focusEngagement || (activeCaseId === caseParam ? engagementParam : null),
            // The payment a link named stays in the address while its tab is open.
            payment: page === "payments" ? paymentParam : null,
            document: page === "documents" ? documentParam : null,
            agreement: page === "documents" ? agreementParam : null,
        });
        if (window.location.pathname + window.location.search !== href) window.history.replaceState(null, "", href);
    }, [standalone, showAllPayments, globalPayments, showMatters, caseLinkError, activeCaseId, page, caseParam, engagementParam, paymentParam, documentParam, agreementParam, focusEngagement]);

    // One loader, reused.
    //
    // A cancellation must re-read the server rather than patch the row locally:
    // the server decides the outcome (it can refuse inside the two-hour cutoff,
    // or the lawyer may have moved the appointment first), and a local
    // "cancelled" would show the client a state the database does not hold.
    const reloadAppointments = useCallback(async () => {
        setApptLoading(true);
        try {
            const { data, error } = await listAppointments({
                page: 1, page_size: APPT_PAGE_SIZE,
            });

            // THE CLIENT RESOLVES ON FAILURE; IT DOES NOT THROW.
            //
            // `apiFetch` returns `{data: null, error, status}` for an HTTP
            // error and `{status: 0}` when the request never left — so the
            // previous `data?.items || data || []` turned every failed read
            // into an empty array, and the page then said "No appointments
            // yet". That is a read failure rendered as a fact about the
            // client's diary, and it is indistinguishable from the truth.
            if (error) {
                setApptRefreshError(
                    error.message || "Could not refresh your appointments.");
                return false;
            }
            const items = Array.isArray(data?.items) ? data.items
                : Array.isArray(data) ? data
                : null;
            if (items === null) {
                // A 200 whose body is not a list is a read we cannot use.
                // Treating it as zero appointments would be the same lie.
                setApptRefreshError(
                    "Your appointments could not be read. Please refresh.");
                return false;
            }

            setApiAppointments(items);
            // PAGING METADATA, recorded from the response rather than guessed.
            // `pages` is the server's own count; a short page is NOT treated as
            // the end, because rows can be removed between requests and "that
            // is everything" would then be a claim the server never made.
            setApptPage(1);
            setApptPages(Number.isInteger(data?.pages) ? data.pages : null);
            setApptTotal(Number.isInteger(data?.total) ? data.total : null);
            setApptRefreshError(null);
            setApptMoreError(null);
            return true;
        } catch {
            // Reached only if the client itself throws. Same rule: keep what is
            // on screen and say the refresh failed.
            setApptRefreshError("Could not refresh your appointments.");
            return false;
        } finally {
            setApptLoading(false);
        }
    }, []);

    // The lawyer confirms, declines or completes while this page is open:
    // re-read, so the card shows it without a manual refresh.
    useEffect(() => onNotification((n) => {
        if (String(n.type || "").startsWith("appointment_")) reloadAppointments();
    }), [reloadAppointments]);

    /** Append the next page of appointments.
     *
     * A FAILED LATER PAGE CHANGES NOTHING ALREADY ON SCREEN. Those rows were
     * read successfully; discarding them to report a partial failure would
     * destroy good data — and would look to the client like appointments
     * disappearing.
     */
    const loadMoreAppointments = useCallback(async () => {
        // The guard, not a nicety: a second click would request the same page
        // again and append it, duplicating every row on it.
        // A REF, NOT THE STATE. Two clicks in the same tick both read the
        // state before React re-renders, so both pass the guard and both
        // request the same page — appending it twice.
        if (apptMoreInFlight.current) return false;
        if (apptPages === null || apptPage >= apptPages) return false;

        apptMoreInFlight.current = true;
        setApptLoadingMore(true);
        setApptMoreError(null);
        const next = apptPage + 1;
        const { data, error } = await listAppointments({
            page: next, page_size: APPT_PAGE_SIZE,
        });
        apptMoreInFlight.current = false;
        setApptLoadingMore(false);

        const rows = Array.isArray(data?.items) ? data.items : null;
        if (error || rows === null) {
            setApptMoreError("Could not load more appointments.");
            return false;
        }
        setApiAppointments(prev => {
            // The backend pages with skip/limit, so a row inserted or removed
            // between requests can shift the window and return one already
            // shown. Appending blindly would display it twice.
            const seen = new Set(prev.map(a => a?.id));
            return [...prev, ...rows.filter(a => a?.id === undefined || !seen.has(a.id))];
        });
        setApptPage(next);
        setApptPages(Number.isInteger(data.pages) ? data.pages : apptPages);
        setApptTotal(Number.isInteger(data.total) ? data.total : apptTotal);
        return true;
    }, [apptLoadingMore, apptPage, apptPages, apptTotal]);

    // Load on mount and whenever the page switches to "appointments"
    useEffect(() => {
        if (page !== "appointments") return;
        reloadAppointments();
    }, [page, reloadAppointments]);

    // Load timeline when the active case changes
    //
    // Only the answer for the case still selected may land: switching cases
    // while a slow read was in flight used to let the PREVIOUS case's hearings
    // and milestones arrive last and show under the new case. Cleared on the
    // switch too, so the old case's dates are not shown meanwhile.
    useEffect(() => {
        if (!activeCaseId) return undefined;
        let off = false;
        setApiMilestones([]);
        setApiHearings([]);
        setTimelineState("loading");
        getCaseTimeline(activeCaseId).then(({ data, error }) => {
            if (off) return;
            if (error || !data) { setTimelineState("error"); return; }
            setTimelineState("ready");
            if (data?.milestones?.length) {
                setApiMilestones(data.milestones.map(mapApiMilestone));
            } else {
                setApiMilestones([]);
            }
            setApiHearings(data?.hearing_dates || []);
        });
        return () => { off = true; };
    }, [activeCaseId, timelineTry]);

    // No fallbacks. An empty list renders an empty state, not invented cases.
    const displayCases = apiCases;
    const displayMilestones = apiMilestones;

    // Merge milestones with any appointment milestones from Module 4
    const allMilestones = [...displayMilestones, ...appointmentMilestones];

    // No silent fallback when a link named a case: an unknown id shows the
    // "cannot be opened" state instead of the newest case.
    const activeCase = displayCases.find(c => c.id === activeCaseId) || (caseParam ? null : displayCases[0]);
    let addressCaseParam = caseParam;
    try {
        if (["/tracking", "/cases"].includes(window.location.pathname)) addressCaseParam = new URLSearchParams(window.location.search).get("case");
    } catch { /* server render */ }
    const caseIsOpening = !!addressCaseParam && !caseLinkError
        && (caseLinkLoading || String(activeCaseId || "") !== String(addressCaseParam));

    // BACK / FORWARD (review item 3, 2026-11-23). Every move between views
    // (a tab, a case, My matters, All my payments) is a browser history entry,
    // and Back/Forward put the view back from the address. The address used
    // to be rewritten in place, so Back left Tracking altogether.
    const pushHref = (href) => {
        if (standalone || typeof window === "undefined" || !["/tracking", "/cases"].includes(window.location.pathname)) return;
        if (window.location.pathname + window.location.search !== href) window.history.pushState(null, "", href);
    };
    const goPage = (key) => {
        setFocusEngagement(null); setFocusPayment(null);
        setPage(key);
        if (activeCaseId && PAGE_TO_TAB[key]) pushHref(matterHref(activeCaseId, { tab: PAGE_TO_TAB[key] }));
    };
    // `engagement`: open the case ON that hire request (its box opens,
    // highlighted) -- My matters' "Review terms" (2026-11-25).
    const goCase = (id, { engagement = null } = {}) => {
        setFocusEngagement(engagement); setFocusPayment(null);
        setCaseLinkError(null); setActiveCaseId(id); setPage("overview");
        setShowMatters(false); setShowAllPayments(false);
        pushHref(matterHref(id, { tab: "summary", engagement }));
    };
    const goMatters = () => { setFocusEngagement(null); setFocusPayment(null); setShowAllPayments(false); setShowMatters(true); pushHref("/tracking"); };
    const goAllPayments = () => { setFocusEngagement(null); setFocusPayment(null); setShowMatters(false); setShowAllPayments(true); pushHref("/tracking?view=payments"); };
    useEffect(() => {
        if (standalone || typeof window === "undefined") return undefined;
        const onPop = () => {
            if (!["/tracking", "/cases"].includes(window.location.pathname)) return;
            const q = new URLSearchParams(window.location.search);
            const c = q.get("case"), tab = q.get("tab"), view = q.get("view"), pay = q.get("payment");
            setFocusEngagement(q.get("engagement")); setFocusPayment(pay);
            if (!c && (view === "payments" || (tab === "payments" && pay))) { setShowMatters(false); setShowAllPayments(true); return; }
            if (!c) { setShowAllPayments(false); setShowMatters(true); return; }
            setShowAllPayments(false); setShowMatters(false);
            if (c) {
                const known = apiCases.some(item => String(item.id) === String(c));
                setCaseLinkError(null);
                setCaseLinkLoading(!known);
                setActiveCaseId(known ? c : null);
            }
            setPage(TAB_TO_PAGE[tab] || "overview");
        };
        window.addEventListener("popstate", onPop);
        return () => window.removeEventListener("popstate", onPop);
    }, [standalone, apiCases]);

    // What the status card's buttons do (v2). "Review terms" opens and
    // highlights the request in the list just below the card.
    const heroAction = (action, eng) => {
        if (action === "timeline") goPage("timeline");
        else if (action === "messages") goPage("communication");
        else if (action === "engagement" && eng) {
            setFocusEngagement(eng.id);
            if (activeCaseId) pushHref(matterHref(activeCaseId, { tab: "summary", engagement: eng.id }));
        }
        else if (action === "pay" && eng) {
            setFocusPayment(eng.id); setPage("payments");
            if (activeCaseId) pushHref(matterHref(activeCaseId, { tab: "payments", payment: eng.id }));
        }
        else if (action === "documents") {
            const documentId = eng?.action === "documents" ? eng.id : null;
            setPage("documents");
            if (activeCaseId) pushHref(matterHref(activeCaseId, { tab: "documents", document: documentId }));
        }
        else if (action === "proposals") clientRouter.push(`/appointments?section=proposals${eng?.action === "proposals" && eng.id ? `&proposal=${encodeURIComponent(eng.id)}` : ""}`);
        else if (action === "agreements") clientRouter.push(`/agreements${eng?.action === "agreements" && eng.id ? `?agreement=${encodeURIComponent(eng.id)}` : ""}`);
        else if (action === "appointment" && eng?.id) clientRouter.push(`/appointments?appointment=${encodeURIComponent(eng.id)}`);
        else if (action === "find-lawyer") clientRouter.push("/lawyers");
        else if (action === "book" && eng) clientRouter.push(lawyerHref({ lawyer_id: eng.lawyer_id, lawyer_name: eng.lawyer_name }, "book"));
    };

    const pages = {
        // My hire requests sit on top of the overview (moved here from the
        // Lawyers page, 2026-11-23): with or without a case selected.
        // The hire-request box ON DEMAND (2026-11-25, as the approved preview):
        // it opens -- scrolled to and highlighted -- when the client presses
        // "View request" / "Review terms" (status card or to-do) or arrives
        // from a link naming the request. Its actions are unchanged.
        overview: (props) => <><PageOverview      {...props} steps={displayMilestones} onHeroAction={heroAction}
            afterHero={(focusEngagement || engagementParam) ? <HireRequests caseId={activeCase?.id || null} focusEngagementId={focusEngagement || engagementParam} /> : null}
            activeCase={activeCase} hearings={apiHearings} casesState={caseIsOpening ? "loading" : casesState} onRetryCases={loadCases} /></>,
        appointments: (props) => <AppointmentsPage standalone={Boolean(standalone)} {...props} appointments={apiAppointments} loading={apptLoading} onReload={reloadAppointments} cancelErrors={cancelErrors} setCancelError={setCancelError}
            refreshError={apptRefreshError}
            onLoadMore={loadMoreAppointments} loadingMore={apptLoadingMore}
            moreError={apptMoreError} total={apptTotal}
            complete={apptPages !== null && apptPage >= apptPages}
            caseTitles={Object.fromEntries(displayCases.map(c => [c.id, c.title]))}
            standalone={Boolean(standalone)} focusId={focusAppt} openThreadId={openThreadId} />,
        timeline: (props) => <PageTimeline      {...props} activeCase={activeCase} milestones={allMilestones} hearings={apiHearings}
            loadState={activeCaseId ? timelineState : "ready"} onRetry={() => setTimelineTry(n => n + 1)} />,
        documents: (props) => <PageDocuments     {...props} activeCaseId={activeCaseId} focusDocumentId={documentParam} focusAgreementId={agreementParam} />,
        payments: (props) => <PagePayments      {...props} caseId={activeCase?.id || null} focusPaymentId={focusPayment || paymentParam} onAllPayments={goAllPayments} />,
        communication: (props) => <PageCommunication {...props} caseId={activeCaseId} activeCase={activeCase} />,
    };
    // CALLED, not rendered as a component.
    //
    // `pages` is rebuilt on every render, so each entry is a NEW function
    // identity — and rendering one as `<PageComp />` makes React see a
    // different component type every time and remount the entire page subtree.
    // Any state inside it is then destroyed by any state change out here: the
    // cancel confirmation closed itself the moment it recorded an error, and
    // every page in this module silently lost its local state on each keypress
    // elsewhere.
    //
    // Calling the arrow returns the element directly, so the child type is the
    // real page component and stays stable across renders.
    const pageFn = pages[page] || pages.overview;
    // A link named a case that cannot be opened: say so on every tab, with a
    // way back to all matters, instead of showing another case's data.
    const renderPage = (props) => caseIsOpening ? (
        <div role="status" data-case-link-loading style={{ maxWidth: 640, margin: "40px auto", padding: "22px 24px", borderRadius: 16, background: t.card, border: `1px solid ${t.border}`, color: t.textMuted }}>
            Opening this matter…
        </div>
    ) : caseLinkError ? (
        <div role="alert" data-case-link-error={caseLinkError} style={{ maxWidth: 640, margin: "40px auto", padding: "22px 24px", borderRadius: 16, background: t.card, border: `1px solid ${t.border}`, color: t.text }}>
            <div style={{ fontSize: 17, fontWeight: 700, marginBottom: 6 }}>
                {caseLinkError === "draft" ? "This case is still a draft"
                    : caseLinkError === "load" ? "This matter could not be loaded"
                    : "This case could not be opened"}
            </div>
            <div style={{ fontSize: 13.5, color: t.textMuted, marginBottom: 14 }}>
                {caseLinkError === "draft"
                    ? "Confirm it at the end of your Legal Intake first; it opens here after that."
                    : caseLinkError === "load"
                        ? "The connection failed, so the matter may still exist. Try again before assuming it is unavailable."
                    : "It may have been removed, or it is not on your account. Nothing from another case is shown instead."}
            </div>
            <div style={{ display: "flex", gap: 10 }}>
                {caseLinkError === "draft" && <a href="/intake" style={{ ...hubBtn("prim", t), textDecoration: "none" }}>Go to Legal Intake</a>}
                {caseLinkError === "load" && <button type="button" data-retry-case-link onClick={() => {
                    setCaseLinkError(null); setCaseLinkLoading(true); setCaseLinkTry(v => v + 1); loadCases();
                }} style={hubBtn("prim", t)}>Try again</button>}
                <a href="/tracking" style={{ ...hubBtn("ghost", t), textDecoration: "none" }}>Show all my matters</a>
            </div>
        </div>
    ) : pageFn(props);

    return (
        <>
            <style>{`
        ::-webkit-scrollbar{width:4px;height:4px;}
        ::-webkit-scrollbar-track{background:transparent;}
        ::-webkit-scrollbar-thumb{background:${t.accent};border-radius:2px;}
        input[type=date],input[type=time]{color-scheme:${t.mode};}
        textarea::placeholder,input::placeholder{color:${t.textFaint};}
        @media (max-width:768px){
          .tracking-root [style*="grid-template-columns"]{grid-template-columns:1fr !important;}
          .tracking-root .case-tabs{width:100%;margin-left:0 !important;justify-content:flex-start;scrollbar-width:none;}
          .tracking-root .case-tabs::-webkit-scrollbar{display:none;}
        }
        select option{background:${t.card};}
        .tracking-root button,.tracking-root input,.tracking-root select,.tracking-root textarea{font-family:inherit}
      `}</style>
            {standalone ? (
            <div className="tracking-root" data-appointments-page data-lenis-prevent style={{ position: "absolute", inset: 0, background: t.bg, fontFamily: "'Hanken Grotesk', system-ui, sans-serif", color: t.text, overflowY: "auto", scrollbarWidth: "none" }}>
                <style>{`[data-appointments-page]::-webkit-scrollbar{display:none}[data-appointments-page] .hub-stat:hover{transform:translateY(-2px)}`}</style>
                <div style={{ maxWidth: 1240, margin: "0 auto", padding: isMobile ? 12 : "28px 32px" }}>
                    {renderPage({ setPage, t })}
                </div>
            </div>
            ) : (
            <div className="tracking-root" data-lenis-prevent style={{ position: "absolute", inset: 0, background: t.bg, fontFamily: "'Hanken Grotesk', system-ui, sans-serif", color: t.text, overflowY: "auto" }}>
                <div style={{ maxWidth: 1240, margin: "0 auto", padding: isMobile ? 12 : "22px 32px 32px" }}>
                    {showAllPayments ? (<>
                        <nav aria-label="Breadcrumb" data-all-payments style={{ display: "flex", alignItems: "center", gap: 8, minHeight: 40, marginBottom: 18, fontSize: 13.5, color: t.textMuted }}>
                            <BackToMatters t={t} onClick={goMatters} />
                            <span aria-hidden="true">/</span>
                            <b style={{ color: t.text }}>All my payments</b>
                        </nav>
                        <PagePayments t={t} caseId={null} focusPaymentId={globalPayments ? paymentParam : null} />
                    </>) : showMatters ? (
                        <MyMatters t={t} cases={displayCases} drafts={draftMatters} casesState={casesState} onRetry={loadCases}
                            onAllPayments={goAllPayments} onOpen={goCase}
                            onOpenAppointment={id => clientRouter.push(`/appointments?appointment=${encodeURIComponent(id)}`)} />
                    ) : (<>
                        <CaseBar t={t} page={page} onNavigate={goPage} activeCase={caseLinkError || caseIsOpening ? null : activeCase}
                            cases={displayCases} onCaseSwitch={goCase} onMatters={goMatters} />
                        {renderPage({ setPage: goPage, t })}
                    </>)}
                </div>
            </div>
            )}
        </>
    );
}
