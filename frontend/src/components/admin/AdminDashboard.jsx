'use client';
import { useState, useEffect } from "react";
import { StatCard, IconBox, Ic } from "./components.jsx";
import { IC } from "./icons.js";
import { adminGetAnalytics } from "@/lib/api.js";

export const Dashboard = ({ T, nav }) => {
  const [analytics, setAnalytics] = useState(null);
  const [loadError, setLoadError] = useState(null);

  // Everything on this page comes from GET /admin/analytics/overview. The
  // trend lines, the monthly chart, the donut and "Recent Activity" used to be
  // hard-coded and were shown as if they were live; they are gone.
  const load = () => {
    setLoadError(null);
    adminGetAnalytics().then(({ data, error }) => {
      if (data) setAnalytics(data);
      else setLoadError(error?.message || "Could not load the overview.");
    });
  };
  useEffect(() => { load(); }, []);

  const totalUsers   = analytics ? analytics.total_users.toLocaleString() : "…";
  const totalCases   = analytics ? analytics.total_cases.toLocaleString() : "…";
  const totalDocs    = analytics ? analytics.total_documents.toLocaleString() : "…";
  const lawyerCount  = analytics ? (analytics.users_by_role?.lawyer ?? 0).toLocaleString() : "…";
  const pendingKYC   = analytics?.pending_kyc ?? 0;

  const stats = [
    { label: "Total Users",    value: totalUsers,  sub: `${analytics?.users_by_role?.client ?? 0} clients · ${analytics?.users_by_role?.lawyer ?? 0} lawyers`, icon: <IconBox icon={IC.users} variant="Primary" T={T} size={42} />, onClick: () => nav("users") },
    { label: "Total Cases",    value: totalCases,  sub: `${analytics?.cases_by_status?.open ?? 0} open · ${analytics?.cases_by_status?.in_progress ?? 0} in progress`, icon: <IconBox icon={IC.briefcase} variant="Warn" T={T} size={42} />, onClick: () => nav("cases") },
    // There is no documents screen in the admin panel, so this card does not navigate.
    { label: "Documents",      value: totalDocs,   sub: `${analytics?.total_agreements ?? 0} agreements`, icon: <IconBox icon={IC.file} variant="Info" T={T} size={42} /> },
    { label: "Lawyers",        value: lawyerCount, sub: pendingKYC > 0 ? `${pendingKYC} pending verification` : "None waiting for verification", subColor: pendingKYC > 0 ? T.warn : T.success, icon: <IconBox icon={IC.balance} variant="Success" T={T} size={42} />, onClick: () => nav("kyc") },
  ];
  // The REAL breakdown the backend already sends; statuses with no cases are left out.
  const STATUS_LABEL = { draft: "Draft", open: "Open", pending_lawyer: "Waiting for lawyer", in_progress: "In progress", closed: "Closed", dismissed: "Dismissed" };
  const statusColors = [T.info, T.warn, T.primary, T.success, T.danger, T.textMuted];
  const statusRows = Object.entries(analytics?.cases_by_status || {})
    .filter(([, n]) => n > 0)
    .map(([k, n], i) => ({ key: k, label: STATUS_LABEL[k] || k, value: n, color: statusColors[i % statusColors.length] }));
  const statusMax = Math.max(1, ...statusRows.map(r => r.value));

  return (
    <div>
      {/* Attention band */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 20, flexWrap: "wrap" }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: T.textMuted, display: "flex", alignItems: "center", gap: 5 }}>
          <Ic d={IC.bell} size={13} color={T.warn} /> Needs attention:
        </span>
        {[
          ...(pendingKYC > 0 ? [{ label: `${pendingKYC} KYC pending`, color: T.warn, m: "kyc" }] : []),
          { label: "Review cases",    color: T.danger,    m: "cases" },
          { label: "Manage users",    color: T.textMuted, m: "users" },
        ].map(a => (
          <button key={a.label} onClick={() => nav(a.m)}
            style={{ display: "flex", alignItems: "center", gap: 6, padding: "5px 14px", borderRadius: 20, background: `${a.color}14`, border: `1px solid ${a.color}35`, color: a.color, fontSize: 12.5, fontWeight: 600, cursor: "pointer", transition: "all 0.15s" }}
            onMouseEnter={e => e.currentTarget.style.background = `${a.color}24`}
            onMouseLeave={e => e.currentTarget.style.background = `${a.color}14`}>
            {a.label}
          </button>
        ))}
      </div>

      <div style={{ marginBottom: 22 }}>
        <h1 style={{ margin: 0, fontSize: 28, fontWeight: 700, color: T.text, letterSpacing: -0.5 }}>Dashboard</h1>
        <p style={{ margin: "4px 0 0", color: T.textMuted, fontSize: 14 }}>System overview · click any card to explore</p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 14, marginBottom: 20 }}>
        {stats.map(s => (
          <StatCard key={s.label} label={s.label} value={s.value} sub={s.sub} subColor={s.subColor}
            iconEl={s.icon} sparkData={s.sparkData} sparkColor={s.sparkColor} onClick={s.onClick} T={T} />
        ))}
      </div>

      {loadError && (
        <div role="alert" style={{ display: "flex", alignItems: "center", gap: 12, background: T.card, border: `1px solid ${T.danger}`, borderRadius: 12, padding: "12px 16px", marginBottom: 16, color: T.danger, fontSize: 13 }}>
          <span style={{ flex: 1 }}>{loadError}</span>
          <button onClick={load} style={{ background: "transparent", border: `1px solid ${T.danger}`, color: T.danger, borderRadius: 8, padding: "5px 12px", cursor: "pointer", fontSize: 12, fontWeight: 600 }}>Retry</button>
        </div>
      )}

      <div className="rgrid" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 14, padding: "20px 22px", boxShadow: T.shadowCard }}>
          <div style={{ fontWeight: 600, fontSize: 14, color: T.text, marginBottom: 14 }}>Cases by status</div>
          {!analytics ? <div style={{ color: T.textFaint, fontSize: 12.5 }}>…</div>
            : statusRows.length === 0 ? <div style={{ color: T.textFaint, fontSize: 12.5 }}>No cases yet.</div>
            : statusRows.map(r => (
              <button key={r.key} onClick={() => nav("cases")} style={{ display: "block", width: "100%", background: "transparent", border: "none", padding: "6px 0", cursor: "pointer", textAlign: "left" }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, marginBottom: 4 }}>
                  <span style={{ color: T.textDim }}>{r.label}</span>
                  <span style={{ color: T.text, fontWeight: 700 }}>{r.value}</span>
                </div>
                <div style={{ height: 6, borderRadius: 4, background: `${T.border}60` }}>
                  <div style={{ width: `${(r.value / statusMax) * 100}%`, height: "100%", borderRadius: 4, background: r.color }} />
                </div>
              </button>
            ))}
        </div>
        <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 14, padding: "20px 22px", boxShadow: T.shadowCard }}>
          <div style={{ fontWeight: 600, fontSize: 14, color: T.text, marginBottom: 14 }}>Quick Actions</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            {[
              { l: "User Management",  ic: IC.users,     m: "users"   },
              { l: "KYC Verification", ic: IC.verify,    m: "kyc"     },
              { l: "Case Tracking",    ic: IC.briefcase, m: "cases"   },
              { l: "Lawyer Monitor",   ic: IC.balance,   m: "lawyers" },
            ].map(q => (
              <button key={q.l} onClick={() => nav(q.m)}
                style={{ background: T.mode === "dark" ? T.surface : T.bg, border: `1px solid ${T.border}`, borderRadius: 12, padding: "16px 12px", cursor: "pointer", textAlign: "center", transition: "all 0.18s" }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = T.primary; e.currentTarget.style.background = T.primaryGlow2; }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = T.border; e.currentTarget.style.background = T.mode === "dark" ? T.surface : T.bg; }}>
                <Ic d={q.ic} size={20} color={T.textMuted} />
                <div style={{ color: T.textMuted, fontSize: 12, fontWeight: 600, marginTop: 7 }}>{q.l}</div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
