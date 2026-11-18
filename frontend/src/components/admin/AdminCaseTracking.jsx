'use client';
import { useState, useEffect, useCallback } from "react";
import { Badge, Btn, Modal, Ic, EmptyState, Paginator } from "./components.jsx";
import { IC } from "./icons.js";
import { adminListCases, adminEndCase } from "@/lib/api.js";

// Case Tracking is an OVERSIGHT view (2026-11-18).
//
// It used to offer one-click buttons for every status, so an admin could move a
// live case back to "draft" with no rule, no confirmation and no word to the
// client or lawyer. A case's lifecycle belongs to its parties. The admin can
// now only END a case that cannot end normally (close or dismiss), with a
// reason that both parties are sent. The list also no longer carries the
// client's description: a lawyer-client matter is confidential, and the server
// sends this screen metadata only.

// Backend status → display label + badge type
const STATUS_META = {
  draft:          { label: "Draft",          type: "gray"    },
  open:           { label: "Open",           type: "info"    },
  pending_lawyer: { label: "Pending Lawyer", type: "primary" },
  in_progress:    { label: "In Progress",    type: "warn"    },
  closed:         { label: "Closed",         type: "gray"    },
  dismissed:      { label: "Dismissed",      type: "danger"  },
};
const ALL_STATUSES = Object.keys(STATUS_META);
const ENDED = new Set(["closed", "dismissed"]);

function fmtDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export const CaseTracking = ({ T }) => {
  const [sf, setSf]           = useState("all");
  const [search, setSearch]   = useState("");
  const [modal, setModal]     = useState(null);
  const [cases, setCases]     = useState([]);
  const [total, setTotal]     = useState(0);
  const [page, setPage]       = useState(1);
  const [perPage, setPerPage] = useState(10);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [toast, setToast]     = useState(null);      // { text, ok }
  // The "end this case" form inside the details window.
  const [ending, setEnding]   = useState(null);      // { status, reason } | null
  const [saving, setSaving]   = useState(false);
  const [endError, setEndError] = useState(null);

  const showToast = (text, ok = true) => { setToast({ text, ok }); setTimeout(() => setToast(null), 3200); };

  const fetchCases = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    const { data, error } = await adminListCases({
      page,
      pageSize: perPage,
      status: sf !== "all" ? sf : undefined,
      search: search || undefined,
    });
    if (!error && data) {
      setCases(data.items || []);
      setTotal(data.total || 0);
    } else {
      // A failed load is not "no cases": say so and offer a retry.
      setLoadError(error?.message || "Could not load cases.");
    }
    setLoading(false);
  }, [page, perPage, sf, search]);

  useEffect(() => { fetchCases(); }, [fetchCases]);
  useEffect(() => { setPage(1); }, [sf, search]);

  const openDetails = (c) => { setModal(c); setEnding(null); setEndError(null); };

  const submitEnd = async () => {
    if (!modal || !ending) return;
    const reason = ending.reason.trim();
    if (reason.length < 10) { setEndError("Give a reason of at least 10 characters. Both parties will see it."); return; }
    setSaving(true);
    setEndError(null);
    const { error } = await adminEndCase(modal._id, ending.status, reason);
    setSaving(false);
    if (error) { setEndError(error.message || "The case could not be ended."); return; }
    showToast(`Case ${modal.case_number || ""} ${ending.status}. Both parties were notified.`);
    setModal(null);
    setEnding(null);
    fetchCases();
  };

  const sm = (s) => STATUS_META[s] || { label: s || "—", type: "gray" };

  return (
    <div>
      {toast && (
        <div role={toast.ok ? "status" : "alert"} style={{ position: "fixed", bottom: 24, right: 24, zIndex: 999, background: toast.ok ? T.success : T.danger, color: "#fff", padding: "10px 18px", borderRadius: 10, fontSize: 13, fontWeight: 600, boxShadow: "0 4px 18px rgba(0,0,0,0.18)" }}>
          {toast.text}
        </div>
      )}

      <div style={{ marginBottom: 26 }}>
        <h1 style={{ margin: 0, fontSize: 28, fontWeight: 700, color: T.text, letterSpacing: -0.5 }}>Case Tracking</h1>
        <p style={{ margin: "4px 0 0", color: T.textMuted, fontSize: 14 }}>An overview of every case: who, what kind and where it stands. Case contents stay private to the client and lawyer.</p>
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap", alignItems: "center" }}>
        <button onClick={() => setSf("all")}
          style={{ padding: "7px 14px", borderRadius: 9, border: `1px solid ${sf==="all" ? T.primary : T.border}`, background: sf==="all" ? T.primaryGlow2 : "transparent", color: sf==="all" ? T.primary : T.textMuted, fontSize: 12.5, fontWeight: 600, cursor: "pointer" }}>
          All
        </button>
        {ALL_STATUSES.map(s => (
          <button key={s} onClick={() => setSf(s)}
            style={{ padding: "7px 14px", borderRadius: 9, border: `1px solid ${sf===s ? T.primary : T.border}`, background: sf===s ? T.primaryGlow2 : "transparent", color: sf===s ? T.primary : T.textMuted, fontSize: 12.5, fontWeight: 600, cursor: "pointer" }}>
            {STATUS_META[s].label}
          </button>
        ))}
        <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center", background: T.inputBg, border: `1px solid ${T.border}`, borderRadius: 9, padding: "7px 12px" }}>
          <Ic d={IC.search} size={14} color={T.textFaint} />
          <input value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} placeholder="Search by case # or title..."
            style={{ background: "none", border: "none", outline: "none", color: T.text, fontSize: 13, width: 190 }} />
          {search && <button onClick={() => { setSearch(""); setPage(1); }} style={{ background: "none", border: "none", cursor: "pointer", padding: 0, display: "flex" }}><Ic d={IC.x} size={13} color={T.textFaint} /></button>}
        </div>
      </div>

      {loading ? (
        <div style={{ padding: 40, textAlign: "center", color: T.textMuted, fontSize: 14 }}>Loading cases…</div>
      ) : loadError ? (
        <div role="alert" style={{ padding: 28, textAlign: "center", background: T.card, border: `1px solid ${T.danger}`, borderRadius: 14 }}>
          <div style={{ color: T.danger, fontSize: 14, fontWeight: 600, marginBottom: 10 }}>{loadError}</div>
          <Btn T={T} variant="outline" onClick={fetchCases}>Retry</Btn>
        </div>
      ) : cases.length === 0 ? (
        <EmptyState T={T} icon={IC.briefcase} title="No cases found" sub="Try a different filter or search term."
          actionLabel="Clear" onAction={() => { setSf("all"); setSearch(""); setPage(1); }} />
      ) : (
        <>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {cases.map(c => (
              <div key={c._id} style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 14, padding: 20, boxShadow: T.shadowCard }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4, flexWrap: "wrap" }}>
                      <span style={{ color: T.primary, fontWeight: 600, fontSize: 14 }}>{c.case_number || "—"}</span>
                      <Badge label={sm(c.status).label} type={sm(c.status).type} T={T} />
                      <Badge label={c.case_type || "—"} type="gray" T={T} />
                    </div>
                    <div style={{ color: T.textMuted, fontSize: 13 }}>
                      {c.title && <span style={{ color: T.textDim, marginRight: 8 }}>{c.title}</span>}
                      {c.client_name && <span>Client: <span style={{ color: T.textDim }}>{c.client_name}</span></span>}
                      <span style={{ marginLeft: 12 }}>Lawyer: <span style={{ color: T.textDim }}>{c.lawyer_name || "Unassigned"}</span></span>
                    </div>
                  </div>
                  <div style={{ textAlign: "right", flexShrink: 0, display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 8 }}>
                    <div style={{ color: T.textFaint, fontSize: 12 }}>Filed: {fmtDate(c.created_at)}</div>
                    <button onClick={() => openDetails(c)} style={{ display: "flex", gap: 6, alignItems: "center", padding: "7px 14px", border: `1px solid ${T.border}`, borderRadius: 9, background: "transparent", color: T.textMuted, fontSize: 12.5, fontWeight: 600, cursor: "pointer" }}>
                      <Ic d={IC.eye} size={13} color={T.textMuted} /> View Details
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 14 }}>
            <Paginator T={T} total={total} page={page} perPage={perPage} onPage={setPage} onPerPage={n => { setPerPage(n); setPage(1); }} />
          </div>
        </>
      )}

      <Modal open={!!modal} onClose={() => { if (!saving) setModal(null); }} title="Case Details" T={T}>
        {modal && (
          <>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 14 }}>
              <span style={{ color: T.primary, fontWeight: 700, fontSize: 15 }}>{modal.case_number || "—"}</span>
              <Badge label={sm(modal.status).label} type={sm(modal.status).type} T={T} />
            </div>
            {[
              ["Title",       modal.title || "—"],
              ["Type",        modal.case_type || "—"],
              ["Client",      modal.client_name || "—"],
              ["Lawyer",      modal.lawyer_name || "Unassigned"],
              ["Province",    modal.province || "—"],
              ["Filed",       fmtDate(modal.created_at)],
              ["Last Update", fmtDate(modal.updated_at)],
              ...(modal.closed_at ? [["Ended", fmtDate(modal.closed_at)]] : []),
            ].map(([k, v]) => (
              <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "9px 0", borderBottom: `1px solid ${T.border}40` }}>
                <span style={{ color: T.textMuted, fontSize: 13 }}>{k}</span>
                <span style={{ color: T.text, fontWeight: 600, fontSize: 13 }}>{v}</span>
              </div>
            ))}
            <p style={{ margin: "12px 0 0", fontSize: 11.5, color: T.textFaint }}>
              The case's story, documents and messages are private to the client and lawyer and are not shown here.
            </p>

            {!ENDED.has(modal.status) && !ending && (
              <div style={{ marginTop: 16, display: "flex", gap: 8, flexWrap: "wrap" }}>
                <Btn T={T} variant="ghost" onClick={() => setEnding({ status: "closed", reason: "" })}>Close case…</Btn>
                <Btn T={T} variant="ghost" onClick={() => setEnding({ status: "dismissed", reason: "" })}>Dismiss case…</Btn>
              </div>
            )}

            {ending && (
              <div style={{ marginTop: 16, padding: 14, border: `1px solid ${T.warn}`, borderRadius: 10, background: `${T.warn}10` }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: T.text, marginBottom: 6 }}>
                  {ending.status === "closed" ? "Close this case" : "Dismiss this case"}
                </div>
                <div style={{ fontSize: 12, color: T.textMuted, marginBottom: 10 }}>
                  Use this only when the client and lawyer cannot end the case themselves. It cannot be undone here.
                  The client and the lawyer will both be sent your reason.
                </div>
                <label htmlFor="admin-end-reason" style={{ display: "block", fontSize: 11.5, fontWeight: 700, color: T.textMuted, marginBottom: 5, textTransform: "uppercase", letterSpacing: 0.6 }}>Reason</label>
                <textarea id="admin-end-reason" value={ending.reason} maxLength={500} rows={3}
                  onChange={e => setEnding(p => ({ ...p, reason: e.target.value }))}
                  style={{ width: "100%", boxSizing: "border-box", background: T.inputBg, border: `1px solid ${T.border}`, borderRadius: 9, padding: "9px 12px", color: T.text, fontSize: 13, resize: "vertical", fontFamily: "inherit" }} />
                {endError && <div role="alert" style={{ color: T.danger, fontSize: 12.5, marginTop: 8 }}>{endError}</div>}
                <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 10 }}>
                  <Btn T={T} variant="ghost" onClick={() => { setEnding(null); setEndError(null); }} disabled={saving}>Cancel</Btn>
                  <Btn T={T} variant="danger" onClick={submitEnd} disabled={saving}>{saving ? "Saving…" : (ending.status === "closed" ? "Close case" : "Dismiss case")}</Btn>
                </div>
              </div>
            )}

            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 18 }}>
              <Btn T={T} variant="ghost" onClick={() => setModal(null)} disabled={saving}>Close</Btn>
            </div>
          </>
        )}
      </Modal>
    </div>
  );
};
