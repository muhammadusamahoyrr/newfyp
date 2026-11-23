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
import HireRequests from "./HireRequests.jsx";
import { getReviewEligibility } from "@/lib/api.js";

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
import { confirmedCases, caseStatusLabel } from "@/lib/caseStatus.js";
import { listCases, getCaseTimeline, listAppointments, cancelAppointment as apiCancelAppointment, getAppointment as apiGetAppointment, rescheduleAppointment as apiRescheduleAppointment, listMessages as apiListMessages, sendMessage as apiSendMessage, listDocuments as apiListDocuments, downloadDocument as apiDownloadDocument, fetchDocumentPreviewUrl, myDocumentsV2, fetchRevisionPreview, downloadDocumentFile, listPayments, startCheckout, mockPay, downloadReceipt, openAppointmentDispute, listAppointmentDisputes, getBookableSlots, listMeetingProposals, acceptMeetingProposal, declineMeetingProposal, listEngagements, listAppointmentFiles as apiListAppointmentFiles, uploadAppointmentFile as apiUploadAppointmentFile, openAppointmentFile as apiOpenAppointmentFile, deleteAppointmentFile as apiDeleteAppointmentFile, acceptAppointmentSuggestion as apiAcceptAppointmentSuggestion, proposeNewTime as apiProposeNewTime, withdrawNewTime as apiWithdrawNewTime, declineNewTime as apiDeclineNewTime, acceptNewTime as apiAcceptNewTime, getSummaryDraft as apiGetSummaryDraft, readSharedSummary as apiReadSharedSummary, shareSummary as apiShareSummary, revokeSummary as apiRevokeSummary } from "@/lib/api.js";
import { formatPkt, pktToday, pktDayKey, pktHourMinute, pktSlotToUtcISO, isPktSlotPast } from "@/lib/bookingTime.js";
import { onNotification } from "@/lib/notificationTarget.js";
import { AppointmentThread } from "@/components/shared/AppointmentThread.jsx";
import { useAuth } from "@/context/AuthContext.jsx";
import { documentStatusView } from "@/lib/documentStatus.js";

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
        pct,
    };
}

function mapApiMilestone(m, idx) {
    const date = new Date(m.date);
    return {
        id: idx + 1,
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
const DotGrid = ({ t }) => (
    <div style={{
        position: "absolute", inset: 0, pointerEvents: "none", zIndex: 0,
        backgroundImage: `radial-gradient(circle,${t.mode === "dark" ? "rgba(64,240,220,0.06)" : "rgba(44,96,110,0.05)"} 1px,transparent 1px)`,
        backgroundSize: "22px 22px"
    }} />
);

const Badge = ({ variant = "primary", children, t, sm }) => {
    const map = { primary: t.badgePrimary, success: t.badgeSuccess, danger: t.badgeDanger, warn: t.badgeWarn, info: t.badgeInfo, gray: t.badgeGray };
    const b = map[variant] || map.primary;
    return (
        <span style={{
            display: "inline-flex", alignItems: "center", gap: 4, fontSize: sm ? 10 : 11, fontWeight: 700,
            padding: sm ? "2px 7px" : "3px 10px", borderRadius: 20, background: b.bg, color: b.color, border: `1px solid ${b.border}`, whiteSpace: "nowrap"
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
        <DotGrid t={t} />
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
        <div style={{ fontSize: 22, opacity: 0.5 }}>{icon}</div>
        <div style={{ fontSize: 13, fontWeight: 700, color: t.textDim }}>{title}</div>
        {desc && <div style={{ fontSize: 11.5, color: t.textMuted, lineHeight: 1.6, maxWidth: 320 }}>{desc}</div>}
    </div>
);

const SH = ({ icon, title, desc, badge, t }) => (
    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "16px 20px", borderBottom: `1px solid ${t.border}` }}>
        <div style={{
            width: 36, height: 36, borderRadius: 10, background: t.primaryGlow2, border: `1px solid ${t.border}`,
            display: "flex", alignItems: "center", justifyContent: "center", fontSize: 15, flexShrink: 0
        }}>{icon}</div>
        <div style={{ flex: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: t.text }}>{title}</div>
            {desc && <div style={{ fontSize: 11, color: t.textMuted, marginTop: 1 }}>{desc}</div>}
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
                display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6, padding: "8px 16px",
                borderRadius: 10, cursor: disabled ? "not-allowed" : "pointer", fontSize: 12, fontWeight: 700, transition: "all 0.18s",
                width: full ? "100%" : undefined, opacity: disabled ? 0.6 : 1, ...(vs[variant] || vs.ghost), ...style
            }}>
            {children}
        </button>
    );
};

const Toggle = ({ value, onChange, t }) => (
    <div onClick={() => onChange(!value)} style={{
        width: 42, height: 24, borderRadius: 12, cursor: "pointer",
        background: value ? t.primary : t.accent, position: "relative", transition: "background 0.2s",
        border: `1px solid ${value ? t.primary : t.border}`, flexShrink: 0
    }}>
        <div style={{
            position: "absolute", width: 18, height: 18, background: "#fff", borderRadius: "50%",
            top: 2, left: value ? 20 : 2, transition: "left 0.2s", boxShadow: "0 1px 4px rgba(0,0,0,0.3)"
        }} />
    </div>
);

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
                padding: "10px 14px", border: "none",
                background: "transparent", cursor: "pointer", fontSize: 12, fontWeight: 700, transition: "all 0.15s",
                borderBottom: `2px solid ${active === tab.key ? t.primary : "transparent"}`, marginBottom: -1,
                color: active === tab.key ? t.primary : t.textMuted
            }}>
                {tab.label}{tab.count != null ? ` (${tab.count})` : ""}</button>
        ))}
    </div>
);

const Ring = ({ pct, t, size = 88 }) => {
    const r = 32, c = 2 * Math.PI * r, fill = c - (pct / 100) * c;
    return (
        <div style={{ position: "relative", width: size, height: size, flexShrink: 0 }}>
            <svg width={size} height={size} viewBox="0 0 80 80" style={{ transform: "rotate(-90deg)" }}>
                <circle cx="40" cy="40" r={r} fill="none" stroke={t.accent} strokeWidth="5" />
                <circle cx="40" cy="40" r={r} fill="none" stroke={t.primary} strokeWidth="5"
                    strokeDasharray={c} strokeDashoffset={fill} strokeLinecap="round" style={{ transition: "stroke-dashoffset 1.2s ease" }} />
            </svg>
            <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
                <span style={{ fontSize: 18, fontWeight: 800, color: t.text }}>{pct}%</span>
                <span style={{ fontSize: 9, color: t.textMuted, fontWeight: 600 }}>done</span>
            </div>
        </div>
    );
};

// ─── NAV ICONS ────────────────────────────────────────────────────────────────
const TrackIc = ({ name, s = 18, c = "currentColor" }) => {
    const icons = {
        overview: <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="2"><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></svg>,
        timeline: <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="2"><circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" /></svg>,
        documents: <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" /><polyline points="14,2 14,8 20,8" /><line x1="8" y1="13" x2="16" y2="13" /><line x1="8" y1="17" x2="13" y2="17" /></svg>,
        notifications: <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="2"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 01-3.46 0" /></svg>,
        communication: <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" /></svg>,
        reminders: <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="2"><rect x="3" y="4" width="18" height="18" rx="2" /><line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" /></svg>,
        appointments: <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="2"><rect x="3" y="4" width="18" height="18" rx="2" /><line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" /><circle cx="12" cy="16" r="2" /></svg>,
    };
    return icons[name] || null;
};

// ─── URGENCY CONFIG ───────────────────────────────────────────────────────────
const urgencyConfig = (t) => ({
    critical: { color: t.danger, bg: "rgba(255,107,122,0.10)", border: "rgba(255,107,122,0.30)", label: "Critical", dot: t.danger },
    overdue: { color: t.danger, bg: "rgba(255,107,122,0.08)", border: "rgba(255,107,122,0.20)", label: "Overdue", dot: t.danger },
    urgent: { color: t.warn, bg: `${t.warn}18`, border: `${t.warn}33`, label: "Soon", dot: t.warn },
    upcoming: { color: t.info, bg: `${t.info}14`, border: `${t.info}28`, label: "Upcoming", dot: t.info },
    normal: { color: t.primary, bg: t.primaryGlow2, border: `${t.primary}33`, label: "Reminder", dot: t.primary },
    info: { color: t.textMuted, bg: t.cardHi, border: t.border, label: "Info", dot: t.textFaint },
});

const typeIcon = { hearing: "⚖️", deadline: "📅", reminder: "⏰", document: "📄", status: "🔄", response: "💬" };
const priorityOrder = { critical: 0, overdue: 1, urgent: 2, upcoming: 3, normal: 4, info: 5 };

// ─── SIDEBAR ──────────────────────────────────────────────────────────────────
const TRACKING_PAGES = [
    { key: "overview", label: "Overview", ur: "جائزہ", ico: "overview", badge: null },
    { key: "appointments", label: "Appointments", ur: "ملاقاتیں", ico: "appointments", badge: null },
    { key: "timeline", label: "Case Timeline", ur: "کیس ٹائم لائن", ico: "timeline", badge: null },
    { key: "documents", label: "Documents", ur: "دستاویزات", ico: "documents", badge: null },
    { key: "payments", label: "Payments", ur: "ادائیگیاں", ico: "documents", badge: null },
    { key: "notifications", label: "Notifications", ur: "اطلاعات", ico: "notifications", badge: null },
    { key: "communication", label: "Communication", ur: "رابطہ", ico: "communication", badge: null },
    { key: "reminders", label: "Reminders", ur: "یاد دہانیاں", ico: "reminders", badge: null },
];

const Sidebar = ({ page, onNavigate, collapsed, onToggle }) => {
    const t = useT();
    const { T } = useLang();
    return (
        <div style={{
            width: collapsed ? 56 : 200, flexShrink: 0, background: t.surface, borderRight: `1px solid ${t.border}`,
            display: "flex", flexDirection: "column", transition: "width 0.25s cubic-bezier(0.4,0,0.2,1)", overflow: "hidden", height: "100%"
        }}>
            <div style={{
                height: 67, padding: collapsed ? "0 14px" : "0 16px", borderBottom: `1px solid ${t.border}`,
                display: "flex", alignItems: "center", justifyContent: collapsed ? "center" : "space-between", gap: 10, flexShrink: 0
            }}>
                {!collapsed && (
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <div style={{
                            width: 32, height: 32, borderRadius: 10, background: `linear-gradient(135deg,${t.primary},${t.secondary})`,
                            display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, boxShadow: `0 4px 12px ${t.primaryGlow}`
                        }}>
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={t.mode === "dark" ? "#1A2E35" : "#fff"} strokeWidth="2.5">
                                <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
                            </svg>
                        </div>
                        <span style={{ fontSize: 15, fontWeight: 800, color: t.text, fontFamily: "'Sora','Inter',sans-serif", letterSpacing: "-0.3px", whiteSpace: "nowrap" }}>
                            Case<span style={{ color: t.primary }}>Track</span>
                        </span>
                    </div>
                )}
                <button onClick={onToggle} style={{
                    width: 32, height: 32, borderRadius: 8, background: "transparent",
                    border: `1px solid ${t.border}`, display: "flex", flexDirection: "column", alignItems: "center",
                    justifyContent: "center", gap: 4, cursor: "pointer", flexShrink: 0, transition: "all 0.15s"
                }}
                    onMouseEnter={e => { e.currentTarget.style.background = t.cardHi; e.currentTarget.style.borderColor = t.borderHi; }}
                    onMouseLeave={e => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.borderColor = t.border; }}>
                    <span style={{ display: "block", width: 14, height: 1.5, background: t.textMuted, borderRadius: 1 }} />
                    <span style={{ display: "block", width: 14, height: 1.5, background: t.textMuted, borderRadius: 1 }} />
                    <span style={{ display: "block", width: 14, height: 1.5, background: t.textMuted, borderRadius: 1 }} />
                </button>
            </div>
            <div style={{ padding: "10px 8px", flex: 1, overflow: "auto" }}>
                {TRACKING_PAGES.map(l => {
                    const active = page === l.key;
                    return (
                        <div key={l.key} onClick={() => onNavigate(l.key)} style={{
                            display: "flex", alignItems: "center",
                            gap: collapsed ? 0 : 12, justifyContent: collapsed ? "center" : "flex-start",
                            padding: collapsed ? "12px 0" : "9px 12px", borderRadius: 10, marginBottom: 2, cursor: "pointer",
                            transition: "all 0.2s cubic-bezier(0.4,0,0.2,1)", background: active ? t.primaryGlow : "transparent",
                            color: active ? t.primary : t.textMuted, position: "relative"
                        }}
                            onMouseEnter={e => { if (!active) { e.currentTarget.style.background = t.inputBg; e.currentTarget.style.color = t.text; } }}
                            onMouseLeave={e => { if (!active) { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = t.textMuted; } }}>
                            <div style={{ position: "relative", flexShrink: 0 }}>
                                <TrackIc name={l.ico} s={18} c={active ? t.primary : "currentColor"} />
                                {collapsed && l.badge != null && (
                                    <span style={{
                                        position: "absolute", top: -4, right: -4, minWidth: 14, height: 14, borderRadius: 7,
                                        background: t[l.bv || "primary"] || t.primary, color: t.mode === "dark" ? "#1A2E35" : "#fff",
                                        fontSize: 8, fontWeight: 800, display: "flex", alignItems: "center", justifyContent: "center",
                                        padding: "0 3px", lineHeight: 1, border: `2px solid ${t.surface}`
                                    }}>{l.badge}</span>
                                )}
                            </div>
                            {!collapsed && (
                                <>
                                    <span style={{ fontSize: 13, fontWeight: active ? 700 : 500, whiteSpace: "nowrap", flex: 1, color: "inherit" }}>{T(l.label, l.ur)}</span>
                                    {l.badge != null && (
                                        <span style={{
                                            minWidth: 18, padding: "2px 6px", borderRadius: 999, fontSize: 10, fontWeight: 700, textAlign: "center",
                                            background: active ? t.primary : t.cardHi, color: active ? (t.mode === "dark" ? "#1A2E35" : "#fff") : t.textDim,
                                            border: `1px solid ${active ? t.primary : t.border}`
                                        }}>{l.badge}</span>
                                    )}
                                </>
                            )}
                            {active && !collapsed && (
                                <div style={{ width: 6, height: 6, borderRadius: "50%", background: t.primary, boxShadow: `0 0 8px ${t.primaryGlow}`, flexShrink: 0 }} />
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
};

// ─── TOP HEADER ───────────────────────────────────────────────────────────────
const TopHeader = ({ t, onBack, activeCaseId, cases, onCaseSwitch, unreadCount, onBell = null }) => {
    // The signed-in client, not a hardcoded "MU" (2026-10-19).
    // Outside an AuthProvider (a test, a preview) there is no user: fall back.
    let user = null;
    try { user = useAuth()?.user || null; } catch { user = null; }
    const { T } = useLang();
    const [caseOpen, setCaseOpen] = useState(false);
    const activeCase = cases.find(c => c.id === activeCaseId) || cases[0];
    return (
        <div style={{
            height: 67, background: t.surface, borderBottom: `1px solid ${t.border}`,
            display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "0 20px", flexShrink: 0, gap: 12, position: "relative", zIndex: 20
        }}>
            <button onClick={onBack} style={{
                display: "flex", alignItems: "center", gap: 8, background: "transparent",
                border: `1px solid ${t.border}`, borderRadius: 8, padding: "6px 12px", cursor: "pointer",
                color: t.textMuted, fontSize: 12, fontWeight: 600, transition: "all 0.15s"
            }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = t.borderHi; e.currentTarget.style.color = t.text; }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = t.border; e.currentTarget.style.color = t.textMuted; }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="15 18 9 12 15 6" />
                </svg>
                Overview
            </button>

            {/* Multi-case switcher */}
            <div style={{ position: "relative" }}>
                <button onClick={() => setCaseOpen(p => !p)} style={{
                    display: "flex", alignItems: "center", gap: 8,
                    background: t.cardHi, border: `1px solid ${t.border}`, borderRadius: 8, padding: "6px 14px",
                    cursor: "pointer", color: t.text, fontSize: 12, fontWeight: 700, transition: "all 0.15s"
                }}
                    onMouseEnter={e => { e.currentTarget.style.borderColor = t.borderHi; }}
                    onMouseLeave={e => { e.currentTarget.style.borderColor = t.border; }}>
                    <span style={{ width: 8, height: 8, borderRadius: "50%", background: activeCase ? t.success : t.textFaint, flexShrink: 0 }} />
                    {activeCase
                        ? `${activeCase.id} — ${activeCase.title.length > 22 ? activeCase.title.slice(0, 22) + "…" : activeCase.title}`
                        : T("No case selected", "کوئی کیس منتخب نہیں")}
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                        <polyline points="6 9 12 15 18 9" />
                    </svg>
                </button>
                {caseOpen && (
                    <div style={{
                        position: "absolute", top: "calc(100% + 6px)", left: 0, minWidth: 260,
                        background: t.card, border: `1px solid ${t.border}`, borderRadius: 12,
                        boxShadow: t.shadowHover, zIndex: 100, overflow: "hidden"
                    }}>
                        <div style={{
                            padding: "8px 14px", fontSize: 10, fontWeight: 700, color: t.textMuted,
                            letterSpacing: "0.1em", textTransform: "uppercase", borderBottom: `1px solid ${t.border}`
                        }}>{T("Switch Case", "کیس تبدیل کریں")}</div>
                        {cases.map(cs => (
                            <div key={cs.id} onClick={() => { onCaseSwitch(cs.id); setCaseOpen(false); }}
                                style={{
                                    padding: "10px 14px", cursor: "pointer", display: "flex", alignItems: "center", gap: 10,
                                    background: cs.id === activeCaseId ? t.primaryGlow : "transparent", transition: "background 0.15s"
                                }}
                                onMouseEnter={e => { if (cs.id !== activeCaseId) e.currentTarget.style.background = t.cardHi; }}
                                onMouseLeave={e => { if (cs.id !== activeCaseId) e.currentTarget.style.background = "transparent"; }}>
                                <span style={{ width: 7, height: 7, borderRadius: "50%", background: cs.id === activeCaseId ? t.primary : t.textFaint, flexShrink: 0 }} />
                                <div style={{ flex: 1 }}>
                                    <div style={{ fontSize: 12, fontWeight: 700, color: cs.id === activeCaseId ? t.primary : t.text }}>{cs.id} — {cs.title}</div>
                                    <div style={{ fontSize: 10, color: t.textMuted }}>{cs.type} · {cs.court}</div>
                                </div>
                                {cs.id === activeCaseId && <span style={{ fontSize: 10, color: t.primary, fontWeight: 700 }}>{T("Active", "فعال")}</span>}
                            </div>
                        ))}
                    </div>
                )}
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{ position: "relative" }}>
                    <button type="button" aria-label="Notifications" title="Notifications" onClick={onBell || undefined} style={{
                        width: 34, height: 34, borderRadius: 8, background: "transparent", border: `1px solid ${t.border}`,
                        display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", color: t.textMuted, transition: "all 0.15s"
                    }}
                        onMouseEnter={e => { e.currentTarget.style.borderColor = t.borderHi; e.currentTarget.style.color = t.text; }}
                        onMouseLeave={e => { e.currentTarget.style.borderColor = t.border; e.currentTarget.style.color = t.textMuted; }}>
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 01-3.46 0" />
                        </svg>
                    </button>
                    {unreadCount > 0 && (
                        <span style={{
                            position: "absolute", top: -4, right: -4, width: 16, height: 16, borderRadius: "50%",
                            background: t.danger || "#ff6b7a", color: "#fff", fontSize: 9, fontWeight: 800,
                            display: "flex", alignItems: "center", justifyContent: "center", border: `2px solid ${t.surface}`
                        }}>{unreadCount}</span>
                    )}
                </div>
                <div style={{
                    width: 34, height: 34, borderRadius: "50%", background: `linear-gradient(135deg,${t.primary},${t.secondary})`,
                    display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 800,
                    color: t.mode === "dark" ? "#1A2E35" : "#fff", cursor: "pointer", flexShrink: 0, boxShadow: `0 2px 8px ${t.primaryGlow}`
                }} title={user?.full_name || undefined}>{initialsOf(user?.full_name || "You")}</div>
            </div>
        </div>
    );
};

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
            <SH icon="🏛" title="Hearing Updates" desc="What happened at each court date — explained simply" t={t}
                badge={
                    <button onClick={(e) => { e.stopPropagation(); setShowUrdu(u => !u); }} style={{
                        padding: "4px 12px", borderRadius: 8, fontSize: 11, fontWeight: 700, cursor: "pointer",
                        border: `1px solid ${t.border}`, background: showUrdu ? t.primaryGlow2 : "transparent", color: showUrdu ? t.primary : t.textMuted,
                    }}>{showUrdu ? "اردو ✓" : "اردو"}</button>
                } />
            <div style={{ padding: 16 }}>
                {nextUp && (
                    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", borderRadius: 10, background: t.primaryGlow2, border: `1px solid ${t.primary}40`, marginBottom: 12 }}>
                        <span style={{ fontSize: 16 }}>📅</span>
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
                            <div style={{ fontSize: 11.5, color: t.textMuted, marginTop: 3 }}>💬 Lawyer's note: {h.outcome_note}</div>
                        )}
                    </div>
                ))}
            </div>
        </Card>
    );
}

function PageOverview({ setPage, activeCase, feed, hearings, milestones = [], casesState = "ready", onRetryCases = null }) {
    const t = useT();
    const { T } = useLang();
    const uc = urgencyConfig(t);
    const critical = feed.filter(f => !f.done && (f.urgency === "critical" || f.urgency === "overdue"));
    const upcoming = feed.filter(f => !f.done && (f.urgency === "urgent" || f.urgency === "upcoming")).slice(0, 2);
    const activeM = milestones.find(m => m.status === "active");

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
            {/* Hero card */}
            <Card t={t} style={{ marginBottom: 20 }}>
                <div style={{ padding: "20px 24px 14px" }}>
                    <div style={{ display: "flex", alignItems: "flex-start", gap: 16 }}>
                        <div style={{ flex: 1 }}>
                            <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
                                <Badge variant={["closed", "dismissed"].includes(activeCase.status) ? "gray" : "success"} t={t}>● {caseStatusLabel(activeCase.status)}</Badge>
                                <Badge variant="warn" t={t}>{activeCase.type}</Badge>
                            </div>
                            <div style={{ fontSize: 26, fontWeight: 800, color: t.text, letterSpacing: "-0.4px", marginBottom: 4 }}>{activeCase.title}</div>
                            <div style={{ fontSize: 12, color: t.textMuted, marginBottom: 14 }}>Filed {activeCase.filed} · {activeCase.court} · {activeCase.judge}</div>
                            <div style={{ marginBottom: 6 }}>
                                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                                    <span style={{ fontSize: 11, color: t.textMuted }}>Case progress ({activeCase.progress}/{activeCase.total} milestones)</span>
                                    <span style={{ fontSize: 11, color: t.primary, fontWeight: 700 }}>{activeCase.pct}%</span>
                                </div>
                                <div style={{ height: 6, background: t.accent, borderRadius: 3, overflow: "hidden" }}>
                                    <div style={{ height: "100%", width: `${activeCase.pct}%`, background: `linear-gradient(90deg,${t.primary},${t.secondary})`, borderRadius: 3 }} />
                                </div>
                            </div>
                            <div style={{ fontSize: 12, color: t.textDim }}>
                                Next hearing: <span style={{ color: t.primary, fontWeight: 700 }}>{activeCase.nextHearing}</span>
                            </div>
                        </div>
                        <Ring pct={activeCase.pct} t={t} />
                    </div>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", borderTop: `1px solid ${t.border}` }}>
                    {[
                        { icon: "🗂", label: "CASE ID", val: activeCase.id, color: t.primary },
                        { icon: "✅", label: "PROGRESS", val: `${activeCase.progress}/${activeCase.total} Steps`, color: t.success },
                        { icon: "📅", label: "NEXT HEARING", val: activeCase.nextHearing, color: t.danger },
                        { icon: "👤", label: "LAWYER", val: activeCase.lawyerAssigned ? "Assigned" : "Not yet", color: t.info },
                    ].map((s, i) => (
                        <div key={s.label} style={{ padding: "14px 18px", display: "flex", alignItems: "center", gap: 10, borderRight: i < 3 ? `1px solid ${t.border}` : "none" }}>
                            <div style={{
                                width: 30, height: 30, borderRadius: 8, background: t.primaryGlow2, border: `1px solid ${t.border}`,
                                display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13
                            }}>{s.icon}</div>
                            <div>
                                <div style={{ fontSize: 9, fontWeight: 700, color: t.textMuted, letterSpacing: "0.1em", textTransform: "uppercase" }}>{s.label}</div>
                                <div style={{ fontSize: 12, fontWeight: 700, color: s.color, marginTop: 1 }}>{s.val}</div>
                            </div>
                        </div>
                    ))}
                </div>
            </Card>

            {/* Peshi tracker — hearing updates in plain language */}
            <HearingUpdates hearings={hearings} caseTitle={activeCase?.title} court={activeCase?.court} />

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 16, marginBottom: 16 }}>
                {/* Action Required — unified feed preview */}
                <Card t={t} onClick={() => setPage("reminders")}>
                    <SH icon="🚨" title="Action Required" desc="Deadlines, hearings & reminders"
                        badge={<Badge variant="danger" t={t}>● {critical.length} Critical</Badge>} t={t} />
                    <div style={{ padding: 16 }}>
                        {critical.length > 0 && (
                            <>
                                <div style={{ fontSize: 10, fontWeight: 700, color: t.danger, letterSpacing: "0.1em", marginBottom: 8 }}>⚠ NEEDS ATTENTION</div>
                                {critical.map(f => {
                                    const u = uc[f.urgency];
                                    return (
                                        <div key={f.id} style={{
                                            display: "flex", alignItems: "center", gap: 10, padding: "10px 12px", borderRadius: 10,
                                            background: u.bg, border: `1px solid ${u.border}`, marginBottom: 8
                                        }}>
                                            <span style={{ fontSize: 16, flexShrink: 0 }}>{typeIcon[f.type]}</span>
                                            <div style={{ flex: 1 }}>
                                                <div style={{ fontSize: 13, fontWeight: 700, color: u.color }}>{f.title}</div>
                                                <div style={{ fontSize: 11, color: t.textMuted }}>{f.date} · {f.time}</div>
                                            </div>
                                            <Badge variant="danger" t={t} sm>{u.label}</Badge>
                                        </div>
                                    );
                                })}
                            </>
                        )}
                        {upcoming.length > 0 && (
                            <>
                                <div style={{ fontSize: 10, fontWeight: 700, color: t.textMuted, letterSpacing: "0.1em", marginBottom: 8, marginTop: 4 }}>{T("UPCOMING", "آئندہ")}</div>
                                {upcoming.map(f => {
                                    const u = uc[f.urgency];
                                    return (
                                        <div key={f.id} style={{
                                            display: "flex", alignItems: "center", gap: 10, padding: "10px 12px", borderRadius: 10,
                                            background: t.cardHi, border: `1px solid ${t.border}`, marginBottom: 8
                                        }}>
                                            <span style={{ fontSize: 16, flexShrink: 0 }}>{typeIcon[f.type]}</span>
                                            <div style={{ flex: 1 }}>
                                                <div style={{ fontSize: 13, fontWeight: 600, color: t.text }}>{f.title}</div>
                                                <div style={{ fontSize: 11, color: t.textMuted }}>{f.date}</div>
                                            </div>
                                            <Badge variant={f.urgency === "urgent" ? "warn" : "info"} t={t} sm>{u.label}</Badge>
                                        </div>
                                    );
                                })}
                            </>
                        )}
                    </div>
                </Card>

                {/* Timeline with "you are here" */}
                <Card t={t} onClick={() => setPage("timeline")}>
                    <SH icon="🕐" title="Case Timeline" desc="Milestones, hearings & court instructions"
                        badge={activeCase.total ? <Badge variant="success" t={t}>{activeCase.progress}/{activeCase.total} done</Badge> : null} t={t} />
                    <div style={{ padding: "16px 20px" }}>
                        {activeM && (
                            <div style={{
                                padding: "8px 12px", borderRadius: 10, background: t.primaryGlow2,
                                border: `1px solid ${t.primary}44`, marginBottom: 14
                            }}>
                                <div style={{ fontSize: 10, fontWeight: 700, color: t.primary, letterSpacing: "0.08em", marginBottom: 2 }}>▶ YOU ARE HERE</div>
                                <div style={{ fontSize: 13, fontWeight: 700, color: t.text }}>{activeM.event}</div>
                                <div style={{ fontSize: 11, color: t.textMuted }}>{activeM.date} · {activeM.time}</div>
                            </div>
                        )}
                        {milestones.length === 0 && (
                            <Empty t={t} icon="🗓" title="No milestones recorded yet"
                                desc="The case timeline fills in as your lawyer records progress." />
                        )}
                        {milestones.slice(0, 4).map((m, i) => {
                            const isDone = m.status === "done", isActive = m.status === "active";
                            return (
                                <div key={m.id} style={{ display: "flex", gap: 12, paddingBottom: i < 3 ? 14 : 0, position: "relative" }}>
                                    {i < 3 && <div style={{ position: "absolute", left: 13, top: 28, width: 2, bottom: 0, background: t.border }} />}
                                    <div style={{
                                        width: 26, height: 26, borderRadius: "50%", border: `2px solid ${isActive ? t.primary : isDone ? t.success : t.border}`,
                                        background: isActive ? t.primaryGlow2 : isDone ? `${t.success}22` : "transparent",
                                        display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11,
                                        color: isActive ? t.primary : isDone ? t.success : t.textFaint,
                                        boxShadow: isActive ? `0 0 10px ${t.primaryGlow}` : "none", zIndex: 1, flexShrink: 0
                                    }}>
                                        {isDone ? "✓" : isActive ? "▶" : "○"}
                                    </div>
                                    <div style={{ flex: 1 }}>
                                        <div style={{ fontSize: 12, fontWeight: 700, color: isActive ? t.text : isDone ? t.textDim : t.textFaint }}>{m.event}</div>
                                        <div style={{ fontSize: 10, color: t.textFaint }}>{m.date}</div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </Card>

                {/* Notifications with urgency tiers */}
                <Card t={t} onClick={() => setPage("notifications")}>
                    <SH icon="🔔" title="Notifications" desc="Sorted by urgency"
                        badge={<Badge variant="warn" t={t}>{feed.filter(f => !f.done).length} Unread</Badge>} t={t} />
                    <div style={{ padding: "12px 20px" }}>
                        {[...feed].sort((a, b) => priorityOrder[a.urgency] - priorityOrder[b.urgency]).slice(0, 4).map((n, i) => {
                            const u = uc[n.urgency];
                            return (
                                <div key={n.id} style={{ display: "flex", gap: 10, padding: "9px 0", borderBottom: `1px solid ${t.border}`, opacity: n.done ? 0.5 : 1 }}>
                                    <div style={{
                                        width: 32, height: 32, borderRadius: 8, flexShrink: 0, background: u.bg, border: `1px solid ${u.border}`,
                                        display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14
                                    }}>{typeIcon[n.type] || "🔔"}</div>
                                    <div style={{ flex: 1 }}>
                                        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                                            <span style={{ fontSize: 12, fontWeight: 700, color: t.text }}>{n.title}</span>
                                            {!n.done && <span style={{ width: 6, height: 6, borderRadius: "50%", background: u.dot, display: "inline-block" }} />}
                                        </div>
                                        <div style={{ fontSize: 11, color: t.textMuted, lineHeight: 1.4 }}>{n.desc}</div>
                                        <div style={{ fontSize: 10, color: t.textFaint, marginTop: 2 }}>{n.date}</div>
                                    </div>
                                </div>
                            );
                        })}
                        <div style={{ padding: "10px 0", textAlign: "center" }}>
                            <span onClick={e => { e.stopPropagation(); setPage("notifications"); }}
                                style={{ fontSize: 12, color: t.primary, fontWeight: 700, cursor: "pointer" }}>View all →</span>
                        </div>
                    </div>
                </Card>
            </div>

            {/* Bottom row */}
            <div className="rgrid-2" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                <Card t={t} onClick={() => setPage("documents")}>
                    <SH icon="📁" title="Documents" desc="Case files & uploads" t={t} />
                    {/* The preview list here used to render a fixed array of
                        invented filenames. Documents are loaded per case in
                        PageDocuments; rather than duplicate that fetch, this
                        card points at it instead of inventing a preview. */}
                    <Empty t={t} icon="📁" title="Open documents"
                        desc="Case files and uploads for the selected case." />
                    <div style={{ padding: "0 0 14px", textAlign: "center" }}>
                        <span style={{ fontSize: 12, color: t.primary, fontWeight: 700, cursor: "pointer" }}>View all documents →</span>
                    </div>
                </Card>

                <Card t={t} onClick={() => setPage("communication")}>
                    <SH icon="💬" title="Communication" desc="Messages & notes with your lawyer" t={t} />
                    {/* Previously two hardcoded messages, including a lawyer
                        reply about "Exhibit C pages 8-14" that no user ever
                        sent. Real messages load in PageCommunication. */}
                    <Empty t={t} icon="💬" title="Open conversation"
                        desc="Messages and notes exchanged with your lawyer on this case." />
                    <div style={{ padding: "0 0 14px", textAlign: "center" }}>
                        <span style={{ fontSize: 12, color: t.primary, fontWeight: 700, cursor: "pointer" }}>Open conversation →</span>
                    </div>
                </Card>
            </div>
        </div>
    );
}

// ─── PAGE: TIMELINE ───────────────────────────────────────────────────────────
// Accepts the milestones prop: the case timeline from the API plus any
// appointment milestones written by ModLawyers via CaseContext.
function PageTimeline({ milestones: propMilestones, hearings = [] }) {
    const t = useT();
    const milestoneRows = propMilestones || [];
    const hearingRows = hearings.map(mapApiHearing);
    const allMilestones = [...milestoneRows, ...hearingRows];
    // Real counts, from the milestones the lawyer marks (no invented "/5").
    const doneCount = milestoneRows.filter(m => m.status === "done").length;
    const pendingCount = milestoneRows.length - doneCount;
    const outcomes = hearings.filter(h => h.outcome).sort((x, y) => new Date(y.date) - new Date(x.date));
    const [tab, setTab] = useState("all");
    const [addNote, setAddNote] = useState(null);
    const [noteText, setNoteText] = useState("");
    const [tagLawyer, setTagLawyer] = useState(false);
    const [notes, setNotes] = useState({});
    const activeRef = useRef(null);

    useEffect(() => {
        setTimeout(() => activeRef.current?.scrollIntoView({ behavior: "smooth", block: "center" }), 200);
    }, [tab]);

    const list = tab === "hearings" ? allMilestones.filter(m => m.tag === "hearing" || m.tag === "appointment")
        : tab === "done" ? allMilestones.filter(m => m.status === "done")
            : allMilestones;
    const tagStyle = { complete: { v: "success", l: "Complete" }, hearing: { v: "warn", l: "⚖ Hearing" }, pending: { v: "gray", l: "Pending" } };

    return (
        <div>
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
                                        display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, flexShrink: 0, zIndex: 1,
                                        color: isActive ? t.primary : isDone ? t.success : t.textFaint,
                                        boxShadow: isActive ? `0 0 14px ${t.primaryGlow}` : "none"
                                    }}>
                                        {isDone ? "✓" : isActive ? "▶" : "○"}
                                    </div>
                                    <div style={{ flex: 1, paddingTop: 4 }}>
                                        {isActive && <div style={{ fontSize: 10, fontWeight: 700, color: t.primary, letterSpacing: "0.08em", marginBottom: 4 }}>▶ YOU ARE HERE</div>}
                                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                                            <div style={{ fontSize: 14, fontWeight: 700, color: isActive ? t.text : isDone ? t.textDim : t.textFaint }}>{m.event}</div>
                                            <div style={{ fontSize: 10, color: t.textFaint, textAlign: "right", flexShrink: 0, marginLeft: 12 }}>{m.date}<br />{m.time}</div>
                                        </div>
                                        <div style={{ fontSize: 12, color: t.textMuted, marginBottom: 6 }}>{m.desc}</div>
                                        <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                                            <Badge variant={tc.v} t={t} sm>{tc.l}</Badge>
                                            {notes[m.id] && <Badge variant="info" t={t} sm>📝 Note added</Badge>}
                                        </div>
                                        {addNote === m.id ? (
                                            <div style={{ marginTop: 10, background: t.cardHi, border: `1px solid ${t.border}`, borderRadius: 12, padding: 12 }}>
                                                <textarea value={noteText} onChange={e => setNoteText(e.target.value)} placeholder="Write note…"
                                                    style={{
                                                        width: "100%", minHeight: 60, background: t.inputBg, border: `1px solid ${t.border}`, borderRadius: 8,
                                                        padding: "8px 12px", color: t.text, fontSize: 12, outline: "none", resize: "vertical", boxSizing: "border-box", marginBottom: 8
                                                    }} />
                                                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                                                    <Toggle value={tagLawyer} onChange={setTagLawyer} t={t} />
                                                    <span style={{ fontSize: 11, color: t.textDim }}>Tag lawyer for review</span>
                                                </div>
                                                <div style={{ display: "flex", gap: 6 }}>
                                                    <Btn t={t} variant="primary" style={{ fontSize: 11 }} onClick={() => { setNotes(p => ({ ...p, [m.id]: noteText })); setAddNote(null); setNoteText(""); }}>Save Note</Btn>
                                                    <Btn t={t} variant="ghost" style={{ fontSize: 11 }} onClick={() => { setAddNote(null); setNoteText(""); }}>Cancel</Btn>
                                                </div>
                                            </div>
                                        ) : (
                                            <div style={{ marginTop: 6 }}>
                                                <span onClick={() => setAddNote(m.id)} style={{ fontSize: 11, color: t.primary, cursor: "pointer", fontWeight: 700 }}>+ Add Note / Tag Lawyer</span>
                                            </div>
                                        )}
                                        {notes[m.id] && addNote !== m.id && (
                                            <div style={{ marginTop: 6, background: t.inputBg, borderRadius: 8, padding: "8px 12px", borderLeft: `3px solid ${t.primary}`, fontSize: 12, color: t.textDim }}>{notes[m.id]}</div>
                                        )}
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
                            {milestoneRows.length === 0 && <div style={{ fontSize: 12, color: t.textMuted, marginBottom: 10 }}>Your lawyer has not added milestones yet.</div>}
                            {milestoneRows.length > 0 && [{ l: "Completed", c: doneCount, col: t.success }, { l: "Pending", c: pendingCount, col: t.textFaint }].map(item => (
                                <div key={item.l} style={{ marginBottom: 14 }}>
                                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
                                        <span style={{ fontSize: 12, color: t.textDim, fontWeight: 500 }}>{item.l}</span>
                                        <span style={{ fontSize: 11, color: item.col, fontWeight: 700 }}>{item.c}/{milestoneRows.length}</span>
                                    </div>
                                    <div style={{ height: 5, background: t.accent, borderRadius: 3, overflow: "hidden" }}>
                                        <div style={{ height: "100%", width: `${(item.c / milestoneRows.length) * 100}%`, background: item.col, borderRadius: 3 }} />
                                    </div>
                                </div>
                            ))}
                            <div style={{ fontSize: 11, color: t.textFaint, marginTop: 4, padding: "8px 10px", background: t.cardHi, borderRadius: 8 }}>
                                % = milestones marked complete by your lawyer
                            </div>
                        </div>
                    </Card>
                    <Card t={t}>
                        <SH icon="📋" title="What the court decided" t={t} />
                        <div style={{ padding: 14 }}>
                            {outcomes.length === 0 && <div style={{ fontSize: 12, color: t.textMuted }}>No hearing outcomes recorded yet.</div>}
                            {outcomes.map((h, i) => (
                                <div key={h._id || i} style={{ background: t.cardHi, border: `1px solid ${t.border}`, borderRadius: 10, padding: 12, marginBottom: i < outcomes.length - 1 ? 10 : 0 }}>
                                    <div style={{ fontSize: 10, color: t.warn, fontWeight: 700, marginBottom: 4 }}>⚖ {formatPkt(h.date, { month: "short", day: "numeric", year: "numeric" })} · {h.outcome_label || h.outcome}</div>
                                    {h.outcome_note && <div style={{ fontSize: 12, color: t.textDim, lineHeight: 1.5 }}>{h.outcome_note}</div>}
                                    {h.outcome_meaning && <div style={{ fontSize: 11.5, color: t.textMuted, lineHeight: 1.5, marginTop: 4 }}>{h.outcome_meaning}</div>}
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
// The case's documents, from the server. What was here and did nothing has
// been made to work or removed: Open and Download had no handler, Sort was
// ignored, a "Seen by lawyer" label was always "Not yet seen" (nothing records
// it), a version history always showed one version with a dead ↓, and a
// failed read showed "0 Files".
function PageDocuments({ activeCaseId }) {
    const t = useT();
    const [filter, setFilter] = useState("All");
    const [search, setSearch] = useState("");
    const [sort, setSort] = useState("date");
    const [apiDocs, setApiDocs] = useState(null);   // null = loading
    const [loadError, setLoadError] = useState(null);
    const [busy, setBusy] = useState(null);         // `${id}:open|download`
    const [docError, setDocError] = useState({});   // id -> message

    const load = useCallback(() => {
        if (!activeCaseId) { setApiDocs([]); setLoadError(null); return () => {}; }
        let off = false;
        setApiDocs(null);
        setLoadError(null);
        Promise.all([
            apiListDocuments(activeCaseId),
            // Off (feature_disabled) or failing, V2 adds nothing: the legacy
            // list still stands on its own.
            myDocumentsV2({ caseId: activeCaseId, limit: 100 }).catch(() => ({ data: null })),
        ]).then(([legacy, v2]) => {
            if (off) return;
            const v2Rows = Array.isArray(v2?.data?.items) ? v2.data.items.map(_mapV2Doc) : [];
            const legacyRows = !legacy.error && Array.isArray(legacy.data) ? legacy.data.map(_mapApiDoc) : null;
            if (!legacyRows && !v2Rows.length) {
                setLoadError(legacy.error?.message || "Could not load this case's documents.");
                setApiDocs([]);
                return;
            }
            const seen = new Set(v2Rows.map(d => d.id));
            setApiDocs([...v2Rows, ...(legacyRows || []).filter(d => !seen.has(d.id))]);
        });
        return () => { off = true; };
    }, [activeCaseId]);
    useEffect(() => load(), [load]);

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
    const cats = ["All", ...Array.from(new Set(docSource.map(d => d.category)))];
    const filtered = docSource
        .filter(d => (filter === "All" || d.category === filter)
            && (!search || d.name.toLowerCase().includes(search.toLowerCase())))
        .sort(DOC_SORTS[sort] || DOC_SORTS.date);
    const btn = (on) => ({
        padding: "5px 12px", borderRadius: 8, border: `1px solid ${t.border}`, background: "transparent",
        color: t.textMuted, fontSize: 11, fontWeight: 600, cursor: on ? "wait" : "pointer", fontFamily: "inherit",
    });

    return (
        <div>
            <Card t={t}>
                <SH icon="📁" title="Case documents" desc="Open or download the documents on this case"
                    badge={<Badge variant="primary" t={t}>{apiDocs === null ? "…" : `${filtered.length} file${filtered.length === 1 ? "" : "s"}`}</Badge>} t={t} />
                <div style={{ padding: "14px 20px", borderBottom: `1px solid ${t.border}` }}>
                    <div style={{ display: "flex", gap: 10, marginBottom: 10 }}>
                        <div style={{ flex: 1, position: "relative" }}>
                            <span style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: t.textMuted }}>🔍</span>
                            <Inp placeholder="Search documents…" value={search} onChange={setSearch} t={t} style={{ paddingLeft: 36 }} />
                        </div>
                        <select aria-label="Sort documents" value={sort} onChange={e => setSort(e.target.value)}
                            style={{ background: t.inputBg, border: `1px solid ${t.border}`, borderRadius: 10, padding: "0 14px", color: t.textDim, fontSize: 12, fontWeight: 600, outline: "none", cursor: "pointer" }}>
                            <option value="date">Sort: Newest</option>
                            <option value="name">Sort: Name</option>
                            <option value="type">Sort: Type</option>
                        </select>
                    </div>
                    {cats.length > 2 && (
                        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                            {cats.map(c => (
                                <button key={c} type="button" onClick={() => setFilter(c)} aria-pressed={filter === c}
                                    style={{
                                        padding: "5px 12px", borderRadius: 20, border: `1px solid ${filter === c ? t.primary : t.border}`,
                                        background: filter === c ? t.primaryGlow2 : "transparent", color: filter === c ? t.primary : t.textMuted,
                                        fontSize: 11, fontWeight: 700, cursor: "pointer", fontFamily: "inherit",
                                    }}>{c}</button>
                            ))}
                        </div>
                    )}
                </div>
                <div style={{ padding: 20 }}>
                    {apiDocs === null && <div style={{ fontSize: 13, color: t.textMuted }}>Loading documents…</div>}
                    {loadError && (
                        <div role="alert" style={{ fontSize: 13, color: t.danger }}>
                            {loadError}{" "}
                            <button type="button" onClick={load} style={{ background: "none", border: "none", color: t.primary, cursor: "pointer", fontWeight: 700, fontFamily: "inherit" }}>Retry</button>
                        </div>
                    )}
                    {apiDocs !== null && !loadError && filtered.length === 0 && (
                        <div style={{ fontSize: 13, color: t.textMuted }}>
                            {docSource.length ? "No documents match." : "No documents on this case yet."}
                        </div>
                    )}
                    {filtered.map(doc => (
                        <div key={doc.id} data-doc={doc.id} style={{ borderRadius: 12, border: `1px solid ${t.border}`, marginBottom: 8, background: t.cardHi, padding: "12px 14px" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                                <div style={{
                                    width: 38, height: 44, borderRadius: 8, background: `${t.danger}18`, border: `1px solid ${t.danger}33`,
                                    display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18, flexShrink: 0,
                                }}>📄</div>
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <div style={{ fontSize: 13, fontWeight: 700, color: t.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", marginBottom: 3 }}>{doc.name}</div>
                                    <div style={{ display: "flex", gap: 10, fontSize: 11, color: t.textMuted, flexWrap: "wrap" }}>
                                        <span style={{ color: t.danger, fontWeight: 700 }}>{doc.type}</span>
                                        <span>{doc.date}</span><span>{doc.category}</span>
                                        {doc.status && <span data-doc-status style={{ fontWeight: 700, color: t.text }}>{doc.status}</span>}
                                    </div>
                                </div>
                                <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                                    <button type="button" onClick={() => openDoc(doc)} disabled={!!busy || doc.downloadable === false} title={doc.downloadable === false ? "This version has no PDF yet" : undefined} style={btn(busy === `${doc.id}:open`)}>
                                        {busy === `${doc.id}:open` ? "Opening…" : "↗ Open"}
                                    </button>
                                    <button type="button" onClick={() => download(doc)} disabled={!!busy || doc.downloadable === false} style={btn(busy === `${doc.id}:download`)}>
                                        {busy === `${doc.id}:download` ? "Downloading…" : "↓ Download"}
                                    </button>
                                </div>
                            </div>
                            {docError[doc.id] && <div role="alert" style={{ fontSize: 12, color: t.danger, marginTop: 8 }}>{docError[doc.id]}</div>}
                        </div>
                    ))}
                </div>
            </Card>
        </div>
    );
}

// ─── PAGE: NOTIFICATIONS ──────────────────────────────────────────────────────
// Fix #4: reads from CaseContext feed; mutations go through context helpers.
function PagePayments({ t }) {
    const { T } = useLang();
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [payingId, setPayingId] = useState(null);
    const [payError, setPayError] = useState({});   // payment id -> message

    const load = async () => {
        const { data } = await listPayments();
        if (Array.isArray(data)) setItems(data);
        setLoading(false);
    };
    useEffect(() => { load(); }, []);

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

    const badge = (status) => {
        const map = {
            paid: t.badgeSuccess, pending: t.badgeWarn, created: t.badgeInfo,
            expired: t.badgeGray, failed: t.badgeDanger, cancelled: t.badgeGray,
        };
        const b = map[status] || t.badgeInfo;
        const label = {
            paid: T("Paid", "ادا شدہ"), pending: T("Processing", "زیرِ عمل"),
            created: T("Due", "واجب"), expired: T("Expired", "میعاد ختم"),
            failed: T("Failed", "ناکام"), cancelled: T("Cancelled", "منسوخ")
        }[status] || status;
        return <span style={{ fontSize: 11, fontWeight: 700, padding: "3px 10px", borderRadius: 20, background: b.bg, color: b.color, border: `1px solid ${b.border}` }}>{label}</span>;
    };

    return (
        <div style={{ maxWidth: 720 }}>
            <div style={{ fontSize: 20, fontWeight: 800, color: t.text, marginBottom: 4 }}>{T("Payments", "ادائیگیاں")}</div>
            <div style={{ fontSize: 13, color: t.textMuted, marginBottom: 18 }}>
                {T("Fees requested by your lawyer. Pay securely from here.", "آپ کے وکیل کی طرف سے مانگی گئی فیس۔ یہاں سے محفوظ ادائیگی کریں۔")}
            </div>

            {loading && <div style={{ fontSize: 13, color: t.textMuted }}>{T("Loading…", "لوڈ ہو رہا ہے…")}</div>}
            {!loading && items.length === 0 && (
                <div style={{ background: t.card, border: `1px solid ${t.border}`, borderRadius: 14, padding: 28, textAlign: "center", fontSize: 13.5, color: t.textMuted }}>
                    {T("No fee requests yet.", "ابھی تک کوئی فیس کی درخواست نہیں۔")}
                </div>
            )}

            {items.map(p => (
                <div key={p.id} style={{ background: t.card, border: `1px solid ${t.border}`, borderRadius: 14, padding: 16, marginBottom: 12, display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                    <div style={{ flex: 1, minWidth: 200 }}>
                        <div style={{ fontSize: 17, fontWeight: 800, color: t.text }}>PKR {Number(p.amount).toLocaleString()}</div>
                        <div style={{ fontSize: 12, color: t.textMuted, marginTop: 3 }}>
                            {p.purpose === "peshi_fee" ? T("Appearance (peshi) fee", "پیشی فیس") : T("Professional fee", "پروفیشنل فیس")}
                            {p.payee_snapshot?.name ? ` · ${p.payee_snapshot.name}` : ""}
                        </div>
                        {p.case_snapshot?.title && <div style={{ fontSize: 11.5, color: t.textFaint, marginTop: 2 }}>{p.case_snapshot.title}</div>}
                        {p.note && <div style={{ fontSize: 11.5, color: t.textFaint, marginTop: 2, fontStyle: "italic" }}>“{p.note}”</div>}
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 8 }}>
                        {badge(p.status)}
                        {/* failed is payable again: the payer was told to try again */}
                        {(p.status === "created" || p.status === "pending" || p.status === "failed") && (
                            <button onClick={() => pay(p)} disabled={payingId === p.id} style={{ padding: "0 20px", height: 40, borderRadius: 10, border: "none", background: t.primary, color: t.mode === "dark" ? "#0F2A30" : "#fff", fontSize: 13.5, fontWeight: 800, cursor: payingId === p.id ? "default" : "pointer", fontFamily: "inherit" }}>
                                {payingId === p.id ? T("Processing…", "زیرِ عمل…") : `${p.status === "failed" ? T("Try again", "دوبارہ کوشش") + " · " : ""}${T("Pay", "ادا کریں")} PKR ${Number(p.amount).toLocaleString()}`}
                            </button>
                        )}
                        {payError[p.id] && (
                            <div role="alert" style={{ fontSize: 11.5, color: t.danger || "#B42318", maxWidth: 220, textAlign: "right" }}>{payError[p.id]}</div>
                        )}
                        {p.status === "paid" && (
                            <button onClick={() => downloadReceipt(p.id, `receipt-${p.id}.pdf`)} style={{ padding: "6px 12px", borderRadius: 8, border: `1px solid ${t.border}`, background: "transparent", color: t.primary, fontSize: 12, fontWeight: 700, cursor: "pointer", fontFamily: "inherit" }}>
                                {T("Receipt", "رسید")} ↓
                            </button>
                        )}
                    </div>
                </div>
            ))}
        </div>
    );
}

function PageNotifications({ feed, onMarkDone, onMarkAllDone, milestones = [] }) {
    const t = useT();
    const [tab, setTab] = useState("all");
    const [settings, setSettings] = useState({
        pushHearing: true, pushStatus: true, pushDocs: true, pushReply: false,
        emailAll: true, emailDigest: true, emailWeekly: false, emailDeadline: true,
    });
    const uc = urgencyConfig(t);
    const unread = feed.filter(f => !f.done).length;
    const displayed = (
        tab === "unread" ? feed.filter(f => !f.done) :
            tab === "critical" ? feed.filter(f => f.urgency === "critical" || f.urgency === "overdue") :
                [...feed]
    ).sort((a, b) => priorityOrder[a.urgency] - priorityOrder[b.urgency]);

    const settingSections = [
        {
            title: "Push Notifications", icon: "📲", items: [
                { k: "pushHearing", l: "Hearing Reminders", d: "Reminders before scheduled hearings" },
                { k: "pushStatus", l: "Status Updates", d: "Case phase change alerts" },
                { k: "pushDocs", l: "Document Alerts", d: "When lawyer uploads documents" },
                { k: "pushReply", l: "Lawyer Replies", d: "Responses to your questions" },
            ]
        },
        {
            title: "Email Notifications", icon: "✉️", items: [
                { k: "emailAll", l: "Enable Email Notifications", d: "Global email toggle" },
                { k: "emailDigest", l: "Daily Digest", d: "End-of-day case summary" },
                { k: "emailWeekly", l: "Weekly Report", d: "Weekly progress summary" },
                { k: "emailDeadline", l: "Deadline Reminders", d: "48hrs before overdue items" },
            ]
        },
    ];

    return (
        <div>
            <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
                <Btn t={t} variant="ghost" onClick={onMarkAllDone}>✓ Mark All Read</Btn>
            </div>
            <div className="rgrid" style={{ display: "grid", gridTemplateColumns: "1fr 308px", gap: 16 }}>
                <Card t={t}>
                    <SH icon="🔔" title="Notifications" desc="Sorted by urgency — critical items first"
                        badge={unread > 0 ? <Badge variant="danger" t={t}>{unread} Unread</Badge> : null} t={t} />
                    <Tabs tabs={[
                        { key: "all", label: "All", count: feed.length },
                        { key: "unread", label: "Unread", count: unread },
                        { key: "critical", label: "⚠ Critical", count: feed.filter(f => f.urgency === "critical" || f.urgency === "overdue").length },
                    ]} active={tab} onChange={setTab} t={t} />
                    <div style={{ padding: "4px 20px 20px" }}>
                        {displayed.map(n => {
                            const u = uc[n.urgency];
                            const ms = n.milestoneId ? milestones.find(m => m.milestoneId === n.milestoneId) : null;
                            return (
                                <div key={n.id} onClick={() => !n.done && onMarkDone(n.id)}
                                    style={{
                                        display: "flex", gap: 12, padding: "14px 0", borderBottom: `1px solid ${t.border}`,
                                        opacity: n.done ? 0.45 : 1, cursor: "pointer", transition: "opacity 0.2s"
                                    }}>
                                    <div style={{
                                        width: 38, height: 38, borderRadius: 10, flexShrink: 0, background: u.bg, border: `1px solid ${u.border}`,
                                        display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16
                                    }}>{typeIcon[n.type] || "🔔"}</div>
                                    <div style={{ flex: 1 }}>
                                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3, flexWrap: "wrap" }}>
                                            <span style={{ fontSize: 13, fontWeight: 700, color: t.text }}>{n.title}</span>
                                            {!n.done && <span style={{ width: 7, height: 7, borderRadius: "50%", background: u.dot, display: "inline-block" }} />}
                                            <Badge variant={
                                                n.urgency === "critical" || n.urgency === "overdue" ? "danger" :
                                                    n.urgency === "urgent" ? "warn" :
                                                        n.urgency === "upcoming" ? "info" : "gray"
                                            } t={t} sm>{u.label}</Badge>
                                        </div>
                                        <div style={{ fontSize: 12, color: t.textDim, lineHeight: 1.5, marginBottom: 3 }}>{n.desc}</div>
                                        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                                            <span style={{ fontSize: 10, color: t.textFaint }}>{n.date} · {n.time}</span>
                                            {ms && <span style={{ fontSize: 10, color: t.primary, fontWeight: 600 }}>● {ms.event}</span>}
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </Card>
                <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                    {settingSections.map(section => (
                        <Card key={section.title} t={t}>
                            <SH icon={section.icon} title={section.title} t={t} />
                            <div style={{ padding: "4px 20px 16px" }}>
                                {section.items.map((s, i) => (
                                    <div key={s.k} style={{
                                        display: "flex", alignItems: "center", gap: 12, padding: "10px 0",
                                        borderBottom: i < section.items.length - 1 ? `1px solid ${t.border}` : "none"
                                    }}>
                                        <div style={{ flex: 1 }}>
                                            <div style={{ fontSize: 13, color: t.text, fontWeight: 600 }}>{s.l}</div>
                                            <div style={{ fontSize: 11, color: t.textFaint }}>{s.d}</div>
                                        </div>
                                        <Toggle value={settings[s.k]} onChange={v => setSettings(p => ({ ...p, [s.k]: v }))} t={t} />
                                    </div>
                                ))}
                            </div>
                        </Card>
                    ))}
                </div>
            </div>
        </div>
    );
}

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
                                <Btn t={t} variant="primary" onClick={send} disabled={!input.trim() || sending}>{sending ? "Sending…" : "Send ↗"}</Btn>
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

// ─── PAGE: REMINDERS — unified feed ──────────────────────────────────────────
function PageReminders({ feed, setFeed, milestones = [], documents = [] }) {
    const t = useT();
    const [tab, setTab] = useState("all");
    const [form, setForm] = useState({ desc: "", date: "", time: "", milestoneId: "" });
    const [editId, setEditId] = useState(null);
    const [editForm, setEditForm] = useState({});
    const uc = urgencyConfig(t);

    const displayed = (
        tab === "overdue" ? feed.filter(f => !f.done && (f.urgency === "overdue" || f.urgency === "critical")) :
            tab === "upcoming" ? feed.filter(f => !f.done && (f.urgency === "upcoming" || f.urgency === "urgent")) :
                tab === "done" ? feed.filter(f => f.done) :
                    [...feed]
    ).sort((a, b) => priorityOrder[a.urgency] - priorityOrder[b.urgency]);

    const conflictOn = (date) => date ? feed.find(f => f.dateRaw === date && !f.done) : null;

    const addReminder = () => {
        if (!form.desc || !form.date) return;
        const conflict = conflictOn(form.date);
        const ms = milestones.find(m => m.milestoneId === form.milestoneId);
        setFeed(p => [...p, {
            id: "r" + Date.now(), type: "reminder", urgency: "normal",
            title: form.desc, date: form.date, dateRaw: form.date, time: form.time || "Any time",
            desc: ms ? `Linked to: ${ms.event}` : "Personal reminder",
            milestoneId: form.milestoneId || undefined, done: false,
            conflict: conflict ? conflict.title : null,
        }]);
        setForm({ desc: "", date: "", time: "", milestoneId: "" });
    };

    return (
        <div>
            <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
                <Btn t={t} variant="primary" onClick={() => document.getElementById("reminder-form")?.scrollIntoView({ behavior: "smooth" })}>+ New Reminder</Btn>
            </div>
            <div className="rgrid-2" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                <Card t={t}>
                    <SH icon="📋" title="All Events & Deadlines" desc="Hearings, deadlines & reminders — one view"
                        badge={<Badge variant="danger" t={t}>{feed.filter(f => !f.done && (f.urgency === "overdue" || f.urgency === "critical")).length} Overdue</Badge>} t={t} />
                    <Tabs tabs={[
                        { key: "all", label: "All", count: feed.length },
                        { key: "overdue", label: "Overdue", count: feed.filter(f => !f.done && (f.urgency === "overdue" || f.urgency === "critical")).length },
                        { key: "upcoming", label: "Upcoming", count: feed.filter(f => !f.done && (f.urgency === "upcoming" || f.urgency === "urgent")).length },
                        { key: "done", label: "Done", count: feed.filter(f => f.done).length },
                    ]} active={tab} onChange={setTab} t={t} />
                    <div style={{ padding: "12px 20px" }}>
                        {displayed.map(f => {
                            const u = uc[f.urgency];
                            const ms = f.milestoneId ? milestones.find(m => m.milestoneId === f.milestoneId) : null;
                            const isEditing = editId === f.id;
                            return (
                                <div key={f.id} style={{
                                    borderRadius: 12, border: `1px solid ${f.done ? t.border : u.border}`,
                                    marginBottom: 10, overflow: "hidden", opacity: f.done ? 0.5 : 1, transition: "opacity 0.2s"
                                }}>
                                    <div style={{ display: "flex", alignItems: "flex-start", gap: 12, padding: "12px 14px", background: f.done ? t.cardHi : u.bg }}>
                                        <div onClick={() => setFeed(p => p.map(x => x.id === f.id ? { ...x, done: !x.done } : x))}
                                            style={{
                                                width: 22, height: 22, borderRadius: 6, border: `2px solid ${f.done ? t.success : u.color}`,
                                                background: f.done ? t.success : "transparent", cursor: "pointer", flexShrink: 0, marginTop: 2,
                                                display: "flex", alignItems: "center", justifyContent: "center",
                                                color: "#fff", fontSize: 11, fontWeight: 800, transition: "all 0.15s"
                                            }}>{f.done ? "✓" : ""}</div>
                                        <div style={{ flex: 1, minWidth: 0 }}>
                                            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4, flexWrap: "wrap" }}>
                                                <span style={{ fontSize: 16 }}>{typeIcon[f.type]}</span>
                                                <span style={{ fontSize: 13, fontWeight: 700, color: f.done ? t.textMuted : t.text, textDecoration: f.done ? "line-through" : "none" }}>{f.title}</span>
                                                <Badge variant={
                                                    f.urgency === "critical" || f.urgency === "overdue" ? "danger" :
                                                        f.urgency === "urgent" ? "warn" :
                                                            f.urgency === "upcoming" ? "info" :
                                                                f.urgency === "normal" ? "primary" : "gray"
                                                } t={t} sm>{u.label}</Badge>
                                                {f.conflict && <Badge variant="danger" t={t} sm>⚡ Conflicts with {f.conflict}</Badge>}
                                            </div>
                                            <div style={{ fontSize: 12, color: t.textMuted, marginBottom: 4 }}>{f.desc}</div>
                                            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                                                <span style={{ fontSize: 11, color: u.color, fontWeight: 600 }}>{f.date} · {f.time}</span>
                                                {ms && <span style={{ fontSize: 11, color: t.primary, fontWeight: 600 }}>● {ms.event}</span>}
                                            </div>
                                        </div>
                                        <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
                                            {f.type === "reminder" && !f.done && (
                                                <button onClick={() => { setEditId(f.id); setEditForm({ desc: f.title, date: f.dateRaw, time: f.time }); }}
                                                    style={{ background: "transparent", border: "none", color: t.textFaint, cursor: "pointer", fontSize: 13 }}>✏</button>
                                            )}
                                            {f.type === "reminder" && (
                                                <button onClick={() => setFeed(p => p.filter(x => x.id !== f.id))}
                                                    style={{ background: "transparent", border: "none", color: t.textFaint, cursor: "pointer", fontSize: 16, padding: "0 2px" }}>×</button>
                                            )}
                                        </div>
                                    </div>
                                    {isEditing && (
                                        <div style={{ padding: "10px 14px", borderTop: `1px solid ${t.border}`, background: t.cardHi }}>
                                            <div className="rgrid-2" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 8 }}>
                                                <Inp placeholder="Description" value={editForm.desc} onChange={v => setEditForm(p => ({ ...p, desc: v }))} t={t} />
                                                <Inp type="date" value={editForm.date} onChange={v => setEditForm(p => ({ ...p, date: v }))} t={t} />
                                            </div>
                                            <div style={{ display: "flex", gap: 6 }}>
                                                <Btn t={t} variant="primary" style={{ fontSize: 11 }} onClick={() => { setFeed(p => p.map(x => x.id === f.id ? { ...x, title: editForm.desc, dateRaw: editForm.date, date: editForm.date } : x)); setEditId(null); }}>Save</Btn>
                                                <Btn t={t} variant="ghost" style={{ fontSize: 11 }} onClick={() => setEditId(null)}>Cancel</Btn>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </Card>

                <div id="reminder-form" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                    <Card t={t}>
                        <SH icon="⏰" title="Set Custom Reminder" desc="Link to a milestone for context" t={t} />
                        <div style={{ padding: 16 }}>
                            <div style={{ marginBottom: 10 }}>
                                <div style={{ fontSize: 10, fontWeight: 700, color: t.textMuted, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 6 }}>Description</div>
                                <Inp placeholder="e.g. Review witness statement before hearing…" value={form.desc} onChange={v => setForm(p => ({ ...p, desc: v }))} t={t} />
                            </div>
                            <div style={{ marginBottom: 10 }}>
                                <div style={{ fontSize: 10, fontWeight: 700, color: t.textMuted, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 6 }}>Link to Milestone</div>
                                <select value={form.milestoneId} onChange={e => setForm(p => ({ ...p, milestoneId: e.target.value }))}
                                    style={{
                                        width: "100%", background: t.inputBg, border: `1px solid ${form.milestoneId ? t.primary : t.border}`, borderRadius: 10,
                                        padding: "9px 12px", color: t.text, fontSize: 12, outline: "none", boxSizing: "border-box"
                                    }}>
                                    <option value="">— No milestone —</option>
                                    {milestones.map(m => <option key={m.id} value={m.milestoneId}>{m.event}</option>)}
                                </select>
                            </div>
                            <div className="rgrid-2" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 14 }}>
                                <div>
                                    <div style={{ fontSize: 10, fontWeight: 700, color: t.textMuted, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 6 }}>Date</div>
                                    <Inp type="date" value={form.date} onChange={v => setForm(p => ({ ...p, date: v }))} t={t} />
                                </div>
                                <div>
                                    <div style={{ fontSize: 10, fontWeight: 700, color: t.textMuted, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 6 }}>Time</div>
                                    <Inp type="time" value={form.time} onChange={v => setForm(p => ({ ...p, time: v }))} t={t} />
                                </div>
                            </div>
                            {form.date && conflictOn(form.date) && (
                                <div style={{
                                    padding: "8px 12px", borderRadius: 8, background: "rgba(255,107,122,0.08)",
                                    border: "1px solid rgba(255,107,122,0.2)", marginBottom: 10, fontSize: 11, color: t.danger
                                }}>
                                    ⚡ Another event on this date: <strong>{conflictOn(form.date)?.title}</strong>
                                </div>
                            )}
                            <Btn t={t} variant="primary" full onClick={addReminder} disabled={!form.desc || !form.date}>+ Create Reminder</Btn>
                        </div>
                    </Card>

                    <Card t={t}>
                        <SH icon="📊" title="Event Summary" t={t} />
                        <div style={{ padding: "8px 20px 16px" }}>
                            {[
                                { label: "Overdue", count: feed.filter(f => !f.done && (f.urgency === "overdue" || f.urgency === "critical")).length, color: t.danger },
                                { label: "Due soon", count: feed.filter(f => !f.done && f.urgency === "urgent").length, color: t.warn },
                                { label: "Upcoming", count: feed.filter(f => !f.done && f.urgency === "upcoming").length, color: t.info },
                                { label: "Completed", count: feed.filter(f => f.done).length, color: t.success },
                            ].map((s, i) => (
                                <div key={s.label} style={{
                                    display: "flex", justifyContent: "space-between", alignItems: "center",
                                    padding: "8px 0", borderBottom: i < 3 ? `1px solid ${t.border}` : "none"
                                }}>
                                    <span style={{ fontSize: 13, color: t.textDim }}>{s.label}</span>
                                    <span style={{ fontSize: 16, fontWeight: 800, color: s.color }}>{s.count}</span>
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
    if (e.status === "requested") return ["Hire request sent", `Waiting for ${first} to send their fee and scope. You'll be notified.`, "/lawyers", "View request", "ghost"];
    if (e.status === "terms_proposed") return [`${first} sent you terms`, `${e.fee_amount != null ? `Fee Rs ${Number(e.fee_amount).toLocaleString()}` : "Their fee and scope"} — accept or decline them.`, "/lawyers", "Review terms", "prim"];
    if (e.status === "accepted" || e.status === "completed") return [`${first} is your lawyer`, `${e.case_title || "Your case"} — follow it on Tracking.`, "/tracking", "Open case", "prim"];
    return ["Hire request closed", `It was ${String(e.status).replace(/_/g, " ")}. This consultation was used for it; book a follow-up to ask again.`, lawyerHref(appt, "book"), "Book a follow-up", "ghost"];
}

function HireAfterConsultation({ appt, t, engagement = null }) {
    if (appt.status !== "completed" || !appt.lawyer_id) return null;
    const [title, sub, href, cta] = hireAction(appt, engagement);
    // The first offer keeps its familiar words; every later state says where it stands.
    const label = engagement ? `${cta} →` : "Hire this lawyer →";

    return (
        <div style={{ marginTop: 10 }} data-hire-state={engagement?.status || "none"}>
            <a href={href} style={{
                display: "inline-block", minHeight: 44, lineHeight: "28px",
                padding: "8px 16px", borderRadius: 9, textDecoration: "none",
                border: "1px solid " + t.primary + "55", background: t.primary + "12",
                color: t.primary, fontSize: 12.5, fontWeight: 700,
            }}>
                {label}
            </a>
            <div style={{ fontSize: 11.5, color: t.textMuted, marginTop: 6 }}>
                {engagement ? `${title}. ${sub}` : <>Ask {appt.lawyer_name || "this lawyer"} to take one of your cases.
                You will agree the fee before anything is assigned.</>}
            </div>
        </div>
    );
}



/* ── APPOINTMENTS, REDESIGNED (2026-10-12) ─────────────────────────────────
 * One card is the whole appointment: where it stands (a progress strip), what
 * to do now (join, wait, next step), and the actions that already existed
 * below it. The same component serves Tracking's tab and the Appointments
 * page, so there is one list and one set of rules. */
const APPT_STEPS = ["Requested", "Confirmed", "Meeting", "Next step"];

function apptEnded(appt, now = Date.now()) {
    return Boolean(appt.end_at && new Date(appt.end_at).getTime() <= now);
}

/** Which step is current: 1 = waiting for the lawyer, 2 = meeting ahead,
 * 3 = after the meeting. -1 for an appointment that ended without one. */
function apptStep(appt) {
    if (appt.status === "pending") return 1;
    if (appt.status === "confirmed") return 2;
    if (appt.status === "completed") return 3;
    return -1;
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

function ApptProgress({ appt, t }) {
    const step = apptStep(appt);
    if (step < 0) return null;
    return (
        <ol aria-label="Progress" data-appt-progress style={{ listStyle: "none", margin: "14px 0 0", padding: 0, display: "grid", gridTemplateColumns: "repeat(4, minmax(0,1fr))", gap: 8 }}>
            {APPT_STEPS.map((label, i) => {
                const done = i < step, now = i === step;
                return (
                    <li key={label} aria-current={now ? "step" : undefined} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                        <span style={{ height: 4, borderRadius: 3, background: done ? t.primary : now ? t.warn : t.border }} />
                        <span style={{ fontSize: 11.5, fontWeight: 700, color: done ? t.text : now ? t.warn : t.textFaint }}>{done ? "✓ " : ""}{label}</span>
                    </li>
                );
            })}
        </ol>
    );
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

/** What the client does now: the meeting's how and when, or the next step. */
function ApptNow({ appt, t }) {
    const video = useVideoConfigured();
    const box = { marginTop: 12, padding: "12px 14px", borderRadius: 12, background: t.inputBg, border: `1px solid ${t.border}` };
    const btn = { display: "inline-flex", alignItems: "center", justifyContent: "center", height: 38, padding: "0 14px", borderRadius: 10, fontSize: 13, fontWeight: 700, textDecoration: "none", cursor: "pointer", fontFamily: "inherit" };
    if (appt.status === "pending") {
        return (
            <div style={box} data-appt-now="waiting">
                <div style={{ fontSize: 13, color: t.text, fontWeight: 700 }}>Waiting for {appt.lawyer_name || "the lawyer"} to confirm</div>
                <div style={{ fontSize: 12, color: t.textMuted, marginTop: 3 }}>You'll be notified when they answer. You can change the time or cancel below until then.</div>
            </div>
        );
    }
    if (appt.status === "confirmed" && !apptEnded(appt)) {
        const live = appt.meeting_link;
        return (
            <div style={{ ...box, borderColor: `${t.primary}55` }} data-appt-now="meeting">
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    <div style={{ flex: "1 1 200px" }}>
                        <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: ".06em", textTransform: "uppercase", color: t.textMuted }}>Starts</div>
                        <div style={{ fontSize: 18, fontWeight: 800, color: t.text }}>{untilWords(appt.scheduled_at)}</div>
                    </div>
                    {live && (
                        <a href={appt.meeting_link} target="_blank" rel="noreferrer"
                            style={{ ...btn, border: "none", color: "#fff", background: "linear-gradient(135deg,#12897f,#1c9c66)" }}>
                            🔗 Join Meeting →
                        </a>
                    )}
                    <button type="button" onClick={() => downloadIcs(appt)} style={{ ...btn, border: `1px solid ${t.border}`, background: "transparent", color: t.text }}>Add to calendar</button>
                </div>
                {!live && appt.mode === "video" && (video ? (
                    <div style={{ marginTop: 10 }}><ClientJoinVideo appt={appt} t={t} /></div>
                ) : (
                    <div style={{ marginTop: 8, fontSize: 12, color: t.textMuted }}>Joining link not shared yet — your lawyer will add it.</div>
                ))}
                {appt.mode === "phone" && (
                    <div style={{ marginTop: 8, fontSize: 12, color: t.textMuted }}>Phone consultation — confirm the number with your lawyer before the time.</div>
                )}
                {appt.mode === "in_person" && (
                    <div style={{ marginTop: 8, fontSize: 12, color: t.textMuted }}>In person — the office address is on your lawyer's profile.</div>
                )}
            </div>
        );
    }
    if (appt.status === "confirmed") {
        return (
            <div style={box} data-appt-now="ended">
                <div style={{ fontSize: 13, color: t.text, fontWeight: 700 }}>This consultation has ended</div>
                <div style={{ fontSize: 12, color: t.textMuted, marginTop: 3 }}>Your lawyer marks it complete; then you can hire them, book a follow-up or leave a review.</div>
            </div>
        );
    }
    if (appt.status === "completed") {
        return (
            <div style={box} data-appt-now="next">
                <div style={{ fontSize: 13, color: t.text, fontWeight: 700 }}>What would you like to do next?</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 4 }}>
                    <a href="/documents" style={{ ...btn, border: `1px solid ${t.border}`, color: t.text }}>Get a document reviewed</a>
                    <a href={lawyerHref(appt, "book")} style={{ ...btn, border: `1px solid ${t.border}`, color: t.text }}>Book a follow-up</a>
                </div>
            </div>
        );
    }
    if (appt.status === "cancelled" || appt.status === "expired") {
        return (
            <div style={{ marginTop: 10 }}>
                <a href={lawyerHref(appt, "book")} style={{ fontSize: 12.5, color: t.primary, fontWeight: 700, textDecoration: "none" }}>Book a new time →</a>
            </div>
        );
    }
    return null;
}

/* ── THE APPOINTMENTS PAGE (2026-10-12) ─────────────────────────────────────
 * The sidebar's Appointments page, as designed: a hub of compact rows (one
 * action each) and, on opening one, its own page. The actions themselves are
 * the components above -- Reschedule, Cancel, Report, Hire -- so the rules
 * live in one place. Tracking's tab keeps its expanded cards. */
// Headings in the Documents module typeface too (2026-10-12), at a heavier weight.
const HUB_SERIF = "'Nunito Sans', 'Avenir Next', Avenir, system-ui, sans-serif";
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
    const [busy, setBusy] = useState(null);
    const [error, setError] = useState({});
    const [declining, setDeclining] = useState(null);
    const [reason, setReason] = useState("");
    const load = useCallback(() => Promise.resolve().then(() => listMeetingProposals({ status: "open" }))
        .then(res => { if (res && !res.error && Array.isArray(res.data)) setItems(res.data.filter(p => p.status === "open")); })
        .catch(() => {}), []);
    useEffect(() => { load(); }, [load]);
    useEffect(() => onNotification((n) => {
        if (String(n.type || "").startsWith("appointment_propos")) load();
    }), [load]);
    // Arriving from "Choose a time" (?section=proposals): bring them into view.
    useEffect(() => {
        if (!items.length) return;
        try {
            if (new URLSearchParams(window.location.search).get("section") !== "proposals") return;
            document.querySelector("[data-proposals]")?.scrollIntoView?.({ block: "start", behavior: "smooth" });
        } catch { /* not in a browser */ }
    }, [items.length]);
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
            {items.map(p => {
                const word = MODE_WORDS[p.mode] || p.mode;
                const mins = p.duration_minutes || 60;
                return (
                    <article key={p.id} data-proposal={p.id} style={{ padding: "18px 20px", borderRadius: 18, border: `1px solid ${t.primary}66`,
                        background: `linear-gradient(120deg, color-mix(in srgb, ${t.primary} 12%, ${t.card}) 0%, ${t.card} 60%)` }}>
                        <div style={{ fontSize: 11.5, fontWeight: 800, letterSpacing: ".08em", textTransform: "uppercase", color: t.primary }}>Meeting proposed</div>
                        <div style={{ font: `800 18px/1.3 ${HUB_SERIF}`, color: t.text, marginTop: 4 }}>
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
                    <h1 style={{ margin: 0, font: `800 30px/1.15 ${HUB_SERIF}`, color: t.text }}>Appointments</h1>
                    <div style={{ fontSize: 14, color: t.textMuted, marginTop: 4 }}>Manage your consultations, view details and join your meetings.</div>
                </div>
                <a href="/lawyers" style={hubBtn("prim", t)}>+ Book a consultation</a>
            </header>

            {refreshError && (
                <div role="alert" style={{ padding: "10px 14px", borderRadius: 12, border: `1px solid ${t.warn}55`, background: `${t.warn}12`, fontSize: 13, color: t.text, display: "flex", gap: 10, alignItems: "center" }}>
                    <span style={{ flex: 1 }}>{refreshError} {appointments.length ? "These may be out of date." : ""}</span>
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
                                            const st = engByAppt[appt.id].status;
                                            const [label, href, kind] = st === "terms_proposed" ? ["Review terms", "/lawyers", "prim"]
                                                : st === "requested" ? ["Hire requested", "/lawyers", "ghost"]
                                                : (st === "accepted" || st === "completed") ? ["Open case", "/tracking", "ghost"] : [null];
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
            <h2 style={{ margin: 0, flex: 1, font: `800 17px/1.3 ${HUB_SERIF}`, color: t.text }}>{text}</h2>{extra}
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
                <div style={{ font: `800 16.5px/1.3 ${HUB_SERIF}`, color: t.text }}>{title}</div>
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
                        <h1 style={{ margin: 0, font: `800 25px/1.2 ${HUB_SERIF}`, color: t.text }}>{appt.lawyer_name || "Your lawyer"}</h1>
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
                            <div style={{ font: `800 15px/1.3 ${HUB_SERIF}`, color: t.text, marginTop: 16 }}>What you can do now</div>
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

function PageAppointments({ appointments, loading, t, onReload, cancelErrors, setCancelError, refreshError,
                            onLoadMore, loadingMore, moreError, total, complete, caseTitles = {}, standalone = false, focusId = null }) {
    const { T } = useLang();
    // Hire requests by consultation, so a completed card shows where its request stands.
    const hireRequests = useHireRequests(appointments.length);
    // The one card whose message thread is open.
    const [threadFor, setThreadFor] = useState(null);
    const statusStyle = {
        pending: { bg: `${t.warn}18`, color: t.warn, label: "Pending Confirmation" },
        confirmed: { bg: `${t.primary}18`, color: t.primary, label: "Confirmed" },
        cancelled: { bg: "rgba(255,107,122,0.12)", color: t.danger, label: "Cancelled" },
        completed: { bg: `${t.info}14`, color: t.info, label: "Completed" },
        no_show: { bg: t.cardHi, color: t.textMuted, label: "No Show" },
        // A request that was never answered and has stopped holding its slot.
        // Its own entry because it is its own outcome — and because without
        // one the fallback below would have shown it as still pending, which
        // is the one thing it definitely is not.
        expired: { bg: t.cardHi, color: t.textMuted, label: "Expired" },
    };
    const modeWords = { video: "Video call", in_person: "In person", phone: "Phone" };
    // Upcoming first, then everything that is over -- each in the server's order.
    const isUpcoming = a => (a.status === "pending" || a.status === "confirmed") && !apptEnded(a);
    const upcoming = appointments.filter(isUpcoming);
    const past = appointments.filter(a => !isUpcoming(a));
    // Opened from a link to one appointment (after booking): bring it into view.
    useEffect(() => {
        if (!focusId) return;
        const el = typeof document !== "undefined" && document.querySelector(`[data-appt="${CSS.escape(focusId)}"]`);
        if (el && el.scrollIntoView) el.scrollIntoView({ block: "center", behavior: "smooth" });
    }, [focusId, appointments.length]);

    // The spinner is for the FIRST read only. Re-reads (after a cancel, a
    // reschedule, a live notification) used to swap the whole list for it,
    // unmounting every card and wiping any dispute or reschedule form the
    // client was typing into.
    if (loading && !appointments.length) return (
        <div style={{ display: "flex", justifyContent: "center", padding: 60 }}>
            <div style={{ width: 32, height: 32, border: `3px solid ${t.primary}`, borderTopColor: "transparent", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
        </div>
    );

    // A FAILED READ IS NOT AN EMPTY DIARY.
    //
    // This used to be `if (!appointments.length)` alone, and the loader turned
    // every failed read into `[]` — so a dropped connection or a 500 told the
    // client, in plain words, that they had no appointments. That is a lie
    // about their own legal engagements, and it is indistinguishable from the
    // truth. When a read has failed and nothing is held, the page says the read
    // failed and offers to try again.
    if (!appointments.length && refreshError) return (
        <div style={{ textAlign: "center", padding: "60px 24px" }} role="alert">
            <div style={{ fontSize: 48, marginBottom: 16 }}>⚠️</div>
            <div style={{ fontSize: 16, fontWeight: 700, color: t.text, marginBottom: 8 }}>
                {T("Could not load your appointments", "ملاقاتیں لوڈ نہیں ہو سکیں")}
            </div>
            <div style={{ fontSize: 13, color: t.textMuted, marginBottom: 16 }}>{refreshError}</div>
            <button type="button" onClick={() => onReload && onReload()} style={{
                minHeight: 44, padding: "10px 20px", borderRadius: 10, cursor: "pointer",
                border: "1px solid " + t.border, background: "transparent",
                color: t.text, fontSize: 13, fontWeight: 700, fontFamily: "inherit",
            }}>
                Try again
            </button>
        </div>
    );

    if (!appointments.length) return (
        <div style={{ textAlign: "center", padding: "60px 24px" }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>📅</div>
            <div style={{ fontSize: 16, fontWeight: 700, color: t.text, marginBottom: 8 }}>{T("No appointments yet", "ابھی کوئی ملاقات نہیں")}</div>
            <div style={{ fontSize: 13, color: t.textMuted }}>Book a consultation with a lawyer to get started.</div>
            <a href="/lawyers" style={{ display: "inline-flex", marginTop: 16, height: 42, alignItems: "center", padding: "0 18px", borderRadius: 12, color: "#fff", fontSize: 14, fontWeight: 700, textDecoration: "none", background: "linear-gradient(135deg,#12897f,#1c9c66)" }}>Find a lawyer</a>
        </div>
    );

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ display: "flex", alignItems: "flex-end", gap: 12, flexWrap: "wrap", marginBottom: 4 }}>
                <div style={{ flex: "1 1 240px" }}>
                    <div style={{ fontSize: standalone ? 26 : 20, fontWeight: 800, color: t.text }}>{T("Your Appointments", "آپ کی ملاقاتیں")}</div>
                    <div style={{ fontSize: 13, color: t.textMuted, marginTop: 2 }}>Every consultation, what it needs from you, and what comes next.</div>
                </div>
                <a href="/lawyers" style={{ display: "inline-flex", height: 40, alignItems: "center", padding: "0 16px", borderRadius: 12, color: "#fff", fontSize: 13.5, fontWeight: 700, textDecoration: "none", background: "linear-gradient(135deg,#12897f,#1c9c66)" }}>+ Book a consultation</a>
            </div>
            {refreshError && (
                // Rows are still shown — they are the last thing the server
                // actually said — but they are labelled as possibly out of
                // date rather than presented as current.
                <div role="alert" style={{
                    padding: "10px 14px", borderRadius: 10,
                    border: "1px solid " + t.warn + "55", background: t.warn + "12",
                    fontSize: 12, color: t.text, display: "flex",
                    alignItems: "center", gap: 10, flexWrap: "wrap",
                }}>
                    <span style={{ flex: "1 1 220px" }}>
                        {refreshError} These may be out of date.
                    </span>
                    <button type="button" onClick={() => onReload && onReload()} style={{
                        minHeight: 44, padding: "8px 16px", borderRadius: 9, cursor: "pointer",
                        border: "1px solid " + t.border, background: "transparent",
                        color: t.text, fontSize: 12, fontWeight: 700, fontFamily: "inherit",
                    }}>
                        Refresh
                    </button>
                </div>
            )}
            {loading && (
                <div aria-live="polite" style={{ fontSize: 12, color: t.textMuted }}>Refreshing…</div>
            )}
            {[["Upcoming", upcoming], ["Past & closed", past]].filter(([, list]) => list.length).map(([heading, list]) => (
            <section key={heading} aria-label={heading} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ fontSize: 11.5, fontWeight: 800, letterSpacing: ".08em", textTransform: "uppercase", color: t.textMuted, marginTop: 6 }}>{heading}</div>
            {list.map(appt => {
                // NOT `|| statusStyle.pending`. Defaulting an unrecognised
                // status to "Pending Confirmation" told the client their
                // request was still live when it was not — including, before
                // this entry existed, every expired one.
                const s = statusStyle[appt.status] || {
                    bg: t.cardHi, color: t.textMuted,
                    label: statusWord(appt.status),
                };
                // PKT explicitly — `toLocale*` without a timeZone renders in
                // whatever zone the browser is in, which is not the zone this
                // appointment was booked in.
                const dateStr = formatPkt(appt.scheduled_at, { weekday: "short", day: "numeric", month: "short", year: "numeric" });
                const timeStr = formatPkt(appt.scheduled_at, { hour: "2-digit", minute: "2-digit" });
                return (
                    <Card key={appt.id} t={t} style={{ padding: 0, ...(focusId === appt.id ? { boxShadow: `0 0 0 2px ${t.primary}` } : {}) }} data-appt={appt.id}>
                        {/* Status strip */}
                        <div style={{ height: 4, borderRadius: "16px 16px 0 0", background: s.color, opacity: 0.7 }} />
                        <div style={{ padding: "16px 20px" }}>
                            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 14 }}>
                                <div aria-hidden="true" style={{ width: 64, height: 64, flexShrink: 0, borderRadius: 14, background: t.inputBg, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
                                    <span style={{ fontSize: 10.5, fontWeight: 800, color: t.textMuted, textTransform: "uppercase" }}>{formatPkt(appt.scheduled_at, { weekday: "short", day: "numeric" })}</span>
                                    <b style={{ fontSize: 17, color: t.text }}>{formatPkt(appt.scheduled_at, { hour: "2-digit", minute: "2-digit", hourCycle: "h23" })}</b>
                                </div>
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <div style={{ fontSize: 15.5, fontWeight: 800, color: t.text }}>
                                        Consultation{appt.lawyer_name ? ` — ${appt.lawyer_name}` : ""}
                                    </div>
                                    <div style={{ fontSize: 12.5, color: t.textMuted, marginTop: 3 }}>{dateStr} · {timeStr} PKT</div>
                                    <div style={{ fontSize: 12.5, color: t.textMuted, marginTop: 2 }}>
                                        {[modeWords[appt.mode] || appt.mode, appt.duration_minutes ? `${appt.duration_minutes} min` : null,
                                          appt.case_id ? (caseTitles[appt.case_id] || `Case ${appt.case_id.slice(-8)}`) : "General consultation"].filter(Boolean).join(" · ")}
                                    </div>
                                </div>
                                <span style={{ fontSize: 11, fontWeight: 700, padding: "4px 10px", borderRadius: 20, background: s.bg, color: s.color, whiteSpace: "nowrap", flexShrink: 0 }}>
                                    {s.label}
                                </span>
                            </div>
                            <ApptProgress appt={appt} t={t} />
                            <ApptNow appt={appt} t={t} />
                            {appt.notes && (
                                <div style={{ marginTop: 10, padding: "8px 12px", borderRadius: 8, background: t.inputBg, border: `1px solid ${t.border}`, fontSize: 12, color: t.textMuted, fontStyle: "italic" }}>
                                    "{appt.notes}"
                                </div>
                            )}
                            <HireAfterConsultation appt={appt} t={t} engagement={hireRequests[appt.id] || null} />
                            <CancellationDetail appt={appt} t={t} />
                            <ExpiryDetail appt={appt} t={t} />
                            <ReportIssue appt={appt} t={t} />
                            <RescheduleAppointment appt={appt} t={t} onReload={onReload}
                                error={(cancelErrors || {})[appt.id] || null}
                                setError={setCancelError} />
                            <CancelAppointment appt={appt} t={t} onReload={onReload}
                                error={(cancelErrors || {})[appt.id] || null}
                                setError={setCancelError} onMessage={() => setThreadFor(appt.id)} />
                            <div data-card-messages style={{ marginTop: 12, display: "flex", flexDirection: "column" }}>
                                <ApptMessages appt={appt} t={t} open={threadFor === appt.id}
                                    onOpenChange={o => setThreadFor(o ? appt.id : null)} />
                            </div>
                        </div>
                    </Card>
                );
            })}
            </section>
            ))}

            {/* LATER-PAGE FAILURE. The appointments above were read
                successfully and stay exactly where they are — a client
                watching their own appointments vanish to report a partial
                failure would reasonably conclude something had been
                cancelled. */}
            {moreError && (
                <div role="alert" style={{
                    padding: "10px 12px", borderRadius: 8,
                    background: `${t.danger}0e`, border: `1px solid ${t.danger}33`,
                    fontSize: 12, color: t.danger,
                }}>
                    {moreError} The appointments already shown are unaffected.
                </div>
            )}

            {/* END OF LIST, only when the SERVER says so. A short page is not
                the signal: rows can be removed between requests, and "that is
                everything" would be a claim the server never made. */}
            <div style={{ textAlign: "center", paddingTop: 4 }}>
                {!complete && (
                    <button type="button" onClick={onLoadMore} disabled={loadingMore}
                        aria-busy={loadingMore || undefined}
                        style={{
                            minHeight: 44, padding: "10px 18px", borderRadius: 9,
                            border: `1px solid ${t.border}`, background: "transparent",
                            color: t.text, fontSize: 12, fontWeight: 700,
                            cursor: loadingMore ? "wait" : "pointer",
                            opacity: loadingMore ? 0.6 : 1, fontFamily: "inherit",
                        }}>
                        {loadingMore ? "Loading…" : "Load more appointments"}
                    </button>
                )}
                <div style={{ fontSize: 11, color: t.textFaint, marginTop: 8 }}>
                    {Number.isInteger(total)
                        ? `Showing ${appointments.length} of ${total}`
                        : `Showing ${appointments.length}`}
                    {complete ? " — that is all of them." : ""}
                </div>
            </div>
        </div>
    );
}

// The sidebar page gets the hub; Tracking's tab keeps its cards.
const AppointmentsPage = ({ standalone, ...props }) => standalone ? <AppointmentsHub {...props} /> : <PageAppointments {...props} />;

// ─── ROOT ─────────────────────────────────────────────────────────────────────
// Fix #2: accepts isDark from Dashboard — no longer owns its own theme state.
// Fix #5: reads appointmentMilestones from CaseContext so booked appointments
//         appear on the timeline immediately.
export default function Module7({ isDark, standalone = null }) {
    const t = clientThemeOnTokens(isDark ? DARK : LIGHT);
    const isMobile = useIsMobile();
    const { notifications, markNotificationDone, markAllNotificationsDone, appointmentMilestones } = useCase();
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
    const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
    // Icon-only inner nav on phones
    useEffect(() => { if (isMobile) setSidebarCollapsed(true); }, [isMobile]);
    const [activeCaseId, setActiveCaseId] = useState(null);
    const [apiCases, setApiCases] = useState([]);
    const [casesState, setCasesState] = useState("loading");   // loading | ready | error
    const [apiMilestones, setApiMilestones] = useState([]);
    const [apiHearings, setApiHearings] = useState([]);
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
    const setCancelError = useCallback((id, message) => {
        setCancelErrors(prev => ({ ...prev, [id]: message }));
    }, []);

    // Load cases from API on mount (and again from "Try again").
    const loadCases = useCallback(() => {
        setCasesState("loading");
        return listCases({ page_size: 20 }).then(({ data, error }) => {
            if (error) { setCasesState("error"); return; }
            setCasesState("ready");
            // Drafts are filtered out BEFORE mapping. `mapApiCase` stamps a
            // "Filed" date from `created_at`, and a draft has not been filed
            // anywhere — it has not even been confirmed. Worse, cases arrive
            // newest-first and the first one becomes the active case, so a
            // fresh draft became the client's headline matter and displaced a
            // real one.
            const real = confirmedCases(data?.items);
            if (real.length) {
                const mapped = real.map(mapApiCase);
                setApiCases(mapped);
                setActiveCaseId(mapped[0].id);
            }
        });
    }, []);
    useEffect(() => { loadCases(); }, [loadCases]);

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
        getCaseTimeline(activeCaseId).then(({ data }) => {
            if (off) return;
            if (data?.milestones?.length) {
                setApiMilestones(data.milestones.map(mapApiMilestone));
            } else {
                setApiMilestones([]);
            }
            setApiHearings(data?.hearing_dates || []);
        });
        return () => { off = true; };
    }, [activeCaseId]);

    // No fallbacks. An empty list renders an empty state, not invented cases.
    const displayCases = apiCases;
    const displayMilestones = apiMilestones;

    // Local reminders created inside PageReminders (notifications come from CaseContext)
    const [localReminders, setLocalReminders] = useState([]);
    const feed = [...notifications, ...localReminders];
    const setFeed = (updater) => {
        const notifIds = new Set(notifications.map(n => n.id));
        const fullFeed = [...notifications, ...localReminders];
        const updated = typeof updater === 'function' ? updater(fullFeed) : updater;
        // Route notification done-toggles through CaseContext
        updated
            .filter(x => notifIds.has(x.id) && x.done && !notifications.find(n => n.id === x.id)?.done)
            .forEach(n => markNotificationDone(n.id));
        // Persist only local (non-notification) entries in local state
        setLocalReminders(updated.filter(x => !notifIds.has(x.id)));
    };

    // Merge milestones with any appointment milestones from Module 4
    const allMilestones = [...displayMilestones, ...appointmentMilestones];

    const activeCase = displayCases.find(c => c.id === activeCaseId) || displayCases[0];
    const unreadCount = feed.filter(f => !f.done).length;

    const pages = {
        // My hire requests sit on top of the overview (moved here from the
        // Lawyers page, 2026-11-23): with or without a case selected.
        overview: (props) => <><HireRequests /><PageOverview      {...props} activeCase={activeCase} feed={feed} hearings={apiHearings} milestones={allMilestones} casesState={casesState} onRetryCases={loadCases} /></>,
        appointments: (props) => <AppointmentsPage standalone={Boolean(standalone)} {...props} appointments={apiAppointments} loading={apptLoading} onReload={reloadAppointments} cancelErrors={cancelErrors} setCancelError={setCancelError}
            refreshError={apptRefreshError}
            onLoadMore={loadMoreAppointments} loadingMore={apptLoadingMore}
            moreError={apptMoreError} total={apptTotal}
            complete={apptPages !== null && apptPage >= apptPages}
            caseTitles={Object.fromEntries(displayCases.map(c => [c.id, c.title]))}
            standalone={Boolean(standalone)} focusId={focusAppt} openThreadId={openThreadId} />,
        timeline: (props) => <PageTimeline      {...props} milestones={allMilestones} hearings={apiHearings} />,
        documents: (props) => <PageDocuments     {...props} activeCaseId={activeCaseId} />,
        payments: (props) => <PagePayments      {...props} />,
        notifications: (props) => <PageNotifications {...props} feed={feed} milestones={allMilestones}
            onMarkDone={markNotificationDone}
            onMarkAllDone={markAllNotificationsDone} />,
        communication: (props) => <PageCommunication {...props} caseId={activeCaseId} activeCase={activeCase} />,
        reminders: (props) => <PageReminders     {...props} feed={feed} setFeed={setFeed} milestones={allMilestones} />,
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
    const renderPage = pages[page] || pages.overview;

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
        }
        select option{background:${t.card};}
      `}</style>
            {standalone ? (
            <div className="tracking-root" data-appointments-page data-lenis-prevent style={{ position: "absolute", inset: 0, background: t.bg, fontFamily: "'Nunito Sans', 'Avenir Next', Avenir, system-ui, sans-serif", color: t.text, overflowY: "auto", scrollbarWidth: "none" }}>
                <style>{`[data-appointments-page]::-webkit-scrollbar{display:none}[data-appointments-page] .hub-stat:hover{transform:translateY(-2px)}`}</style>
                <div style={{ maxWidth: 1240, margin: "0 auto", padding: isMobile ? 12 : "28px 32px" }}>
                    {renderPage({ setPage, t })}
                </div>
            </div>
            ) : (
            <div className="tracking-root" style={{ display: "flex", position: "absolute", inset: 0, background: t.bg, fontFamily: "'Inter',sans-serif", color: t.text, overflow: "hidden" }}>
                <Sidebar page={page} onNavigate={setPage} collapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed(p => !p)} t={t} />
                <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
                    <TopHeader t={t} onBack={() => setPage("overview")}
                        activeCaseId={activeCaseId} cases={displayCases} onCaseSwitch={setActiveCaseId} unreadCount={unreadCount}
                        onBell={() => setPage("notifications")} />
                    <div style={{ flex: 1, overflowY: "auto", padding: isMobile ? 12 : 24 }}>
                        {renderPage({ setPage, t })}
                    </div>
                </div>
            </div>
            )}
        </>
    );
}