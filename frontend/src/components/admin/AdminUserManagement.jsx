'use client';
import { useState, useMemo, useEffect, useCallback } from "react";
import { Avatar, Badge, Btn, Modal, Input, EmptyState, Paginator, ActionMenu, SortTh, Ic } from "./components.jsx";
import { IC } from "./icons.js";
import { adminListUsers, adminCreateUser, adminUpdateUser, adminResetPassword, adminDeleteUser } from "@/lib/api.js";

function fmtDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export const UserManagement = ({ T }) => {
  const [tab, setTab]       = useState("all");
  const [search, setSearch] = useState("");
  const [modal, setModal]   = useState(null);
  const [sel, setSel]       = useState(null);
  const [confirmDel, setConfirmDel] = useState(null);
  const [toast, setToast]           = useState(null);   // { text, ok }
  const [loading, setLoading]       = useState(true);
  const [loadError, setLoadError]   = useState(null);

  // Server-side data
  const [users, setUsers]   = useState([]);
  const [total, setTotal]   = useState(0);
  const [page, setPage]     = useState(1);
  const [perPage, setPerPage] = useState(10);

  // Form state
  const [formName, setFormName]     = useState("");
  const [formEmail, setFormEmail]   = useState("");
  const [formRole, setFormRole]     = useState("client");
  const [formSaving, setFormSaving] = useState(false);

  // Sort is client-side on the current page only
  const [sort, setSort] = useState({ field: "full_name", dir: "asc" });
  const handleSort = (field) => setSort(p => ({ field, dir: p.field === field && p.dir === "asc" ? "desc" : "asc" }));

  // Failures show in red, successes in green (errors used the success style).
  const showToast = (text, ok = true) => { setToast({ text, ok }); setTimeout(() => setToast(null), ok ? 2800 : 5000); };

  const roleForTab = { all: null, clients: "client", lawyers: "lawyer", admins: "admin" };

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    const { data, error } = await adminListUsers({
      page,
      pageSize: perPage,
      role: roleForTab[tab],
      search: search || undefined,
    });
    if (!error && data) {
      setUsers(data.items || []);
      setTotal(data.total || 0);
    } else {
      // A failed load is not "no users found".
      setLoadError(error?.message || "Could not load users.");
    }
    setLoading(false);
  }, [page, perPage, tab, search]);

  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  // Reset to page 1 when filter changes
  useEffect(() => { setPage(1); }, [tab, search]);

  const sortedUsers = useMemo(() => {
    return [...users].sort((a, b) => {
      const av = a[sort.field] || "", bv = b[sort.field] || "";
      return sort.dir === "asc" ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
    });
  }, [users, sort]);

  const toggleStatus = async (u) => {
    const next = !u.is_active;
    setUsers(p => p.map(x => x._id === u._id ? { ...x, is_active: next } : x));
    const { error } = await adminUpdateUser(u._id, { is_active: next });
    if (error) {
      setUsers(p => p.map(x => x._id === u._id ? { ...x, is_active: u.is_active } : x));
      showToast(error.message || "Failed to update status", false);
    } else {
      showToast(`${u.full_name} account ${next ? "activated" : "deactivated"}`);
    }
  };

  const deleteUser = async (u) => {
    setConfirmDel(null);
    setUsers(p => p.filter(x => x._id !== u._id));
    setTotal(p => p - 1);
    const { error } = await adminDeleteUser(u._id);
    if (error) {
      showToast(error.message || "Failed to delete user", false);
      fetchUsers();
    } else {
      showToast(`${u.full_name} deleted`);
    }
  };

  const openAdd = () => { setSel(null); setFormName(""); setFormEmail(""); setFormRole("client"); setModal("add"); };
  const openEdit = (u) => { setSel(u); setFormName(u.full_name); setFormEmail(u.email); setFormRole(u.role); setModal("edit"); };
  const openPw = (u) => { setSel(u); setModal("pw"); };

  // No password field: the new user is emailed a link to set their own, so
  // no admin ever knows another person's password.
  const saveAdd = async () => {
    if (!formName.trim() || !formEmail.trim()) return;
    setFormSaving(true);
    const { data, error } = await adminCreateUser({ full_name: formName.trim(), email: formEmail.trim(), role: formRole });
    setFormSaving(false);
    if (error) { showToast(`Failed: ${error?.message || "server error"}`, false); return; }
    showToast(data?.setup_link_sent
      ? `${formName} created. A link to set their password was emailed.`
      : `${formName} created, but the email could not be sent. Ask them to use "Forgot password".`,
      !!data?.setup_link_sent);
    setModal(null);
    fetchUsers();
  };

  const saveEdit = async () => {
    if (!sel) return;
    setFormSaving(true);
    const { error } = await adminUpdateUser(sel._id, { full_name: formName, role: formRole });
    setFormSaving(false);
    if (error) { showToast(`Failed: ${error?.message || "server error"}`, false); return; }
    setUsers(p => p.map(u => u._id === sel._id ? { ...u, full_name: formName, role: formRole } : u));
    showToast("Changes saved");
    setModal(null);
  };

  // The admin no longer types a new password: the user is signed out
  // everywhere and emailed a link to set one themselves.
  const savePw = async () => {
    if (!sel) return;
    setFormSaving(true);
    const { data, error } = await adminResetPassword(sel._id);
    setFormSaving(false);
    if (error) { showToast(`Failed: ${error?.message || "server error"}`, false); return; }
    showToast(data?.message || `Reset link sent to ${sel.full_name}`, data?.success !== false);
    setModal(null);
  };

  const Toggle = ({ on, onChange }) => (
    <button onClick={onChange} role="switch" aria-checked={on} title={on ? "Deactivate" : "Activate"}
      style={{ width: 42, height: 24, borderRadius: 12, border: "none", padding: 2, cursor: "pointer", transition: "background 0.22s", background: on ? T.success : (T.mode==="dark"?"rgba(255,255,255,0.12)":"rgba(26,46,53,0.12)"), display: "flex", alignItems: "center", justifyContent: on ? "flex-end" : "flex-start" }}>
      <div style={{ width: 18, height: 18, borderRadius: "50%", background: "#fff", boxShadow: "0 1px 3px rgba(0,0,0,0.2)", transition: "all 0.22s cubic-bezier(0.34,1.56,0.64,1)" }} />
    </button>
  );

  return (
    <div style={{ position: "relative" }}>
      {toast && (
        <div role={toast.ok ? "status" : "alert"} style={{ position: "fixed", bottom: 24, right: 24, zIndex: 999, maxWidth: 420, background: toast.ok ? T.success : T.danger, color: toast.ok && T.mode==="dark" ? "#0a1f1a" : "#fff", padding: "10px 18px", borderRadius: 10, fontSize: 13, fontWeight: 600, boxShadow: "0 4px 18px rgba(0,0,0,0.18)", display: "flex", alignItems: "center", gap: 8 }}>
          <Ic d={toast.ok ? IC.check : "M12 9v4M12 17h.01"} size={15} color={toast.ok && T.mode==="dark" ? "#0a1f1a" : "#fff"} sw={2.5} /> {toast.text}
        </div>
      )}

      {confirmDel && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 998, display: "flex", alignItems: "center", justifyContent: "center" }} onClick={() => setConfirmDel(null)}>
          <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 16, padding: 28, maxWidth: 400, width: "90%", boxShadow: "0 20px 60px rgba(0,0,0,0.28)" }} onClick={e => e.stopPropagation()}>
            <div style={{ width: 48, height: 48, borderRadius: "50%", background: `${T.danger}15`, display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 16 }}>
              <Ic d={IC.trash} size={22} color={T.danger} />
            </div>
            <div style={{ fontSize: 15, fontWeight: 700, color: T.text, marginBottom: 6 }}>Delete account?</div>
            <div style={{ fontSize: 13, color: T.textMuted, marginBottom: 20, lineHeight: 1.65 }}>
              This closes <strong style={{ color: T.text }}>{confirmDel.full_name}</strong>'s account and erases their personal details. It is refused while they have open engagements or payments. This cannot be undone.
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              <Btn T={T} variant="ghost" onClick={() => setConfirmDel(null)} style={{ flex: 1, justifyContent: "center" }}>Cancel</Btn>
              <Btn T={T} variant="danger" onClick={() => deleteUser(confirmDel)} style={{ flex: 1, justifyContent: "center" }}>Delete permanently</Btn>
            </div>
          </div>
        </div>
      )}

      <div style={{ marginBottom: 22 }}>
        <h1 style={{ margin: 0, fontSize: 28, fontWeight: 700, color: T.text, letterSpacing: -0.5 }}>User Management</h1>
        <p style={{ margin: "4px 0 0", color: T.textMuted, fontSize: 14 }}>Manage all users, roles, and account access</p>
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 14, alignItems: "center", flexWrap: "wrap" }}>
        {["all","clients","lawyers","admins"].map(t => (
          <button key={t} onClick={() => { setTab(t); setPage(1); }}
            style={{ padding: "7px 16px", borderRadius: 9, border: `1px solid ${tab===t ? T.primary : T.border}`, background: tab===t ? T.primaryGlow2 : "transparent", color: tab===t ? T.primary : T.textMuted, fontSize: 13, fontWeight: 600, cursor: "pointer", textTransform: "capitalize" }}>
            {t}
          </button>
        ))}
        <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center", background: T.inputBg, border: `1px solid ${T.border}`, borderRadius: 9, padding: "7px 12px" }}>
          <Ic d={IC.search} size={14} color={T.textFaint} />
          <input value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} placeholder="Search users..."
            style={{ background: "none", border: "none", outline: "none", color: T.text, fontSize: 13, width: 160 }} />
          {search && <button onClick={() => { setSearch(""); setPage(1); }} style={{ background: "none", border: "none", cursor: "pointer", padding: 0, display: "flex" }}><Ic d={IC.x} size={13} color={T.textFaint} /></button>}
        </div>
        <Btn T={T} icon={IC.plus} onClick={openAdd}>Add User</Btn>
      </div>

      <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 14, overflow: "hidden", boxShadow: T.shadowCard }}>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 640 }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${T.border}`, background: T.mode === "dark" ? "rgba(255,255,255,0.025)" : "rgba(26,46,53,0.025)" }}>
                <SortTh label="User"   field="full_name"   sort={sort} onSort={handleSort} T={T} />
                <SortTh label="Email"  field="email"       sort={sort} onSort={handleSort} T={T} />
                <SortTh label="Role"   field="role"        sort={sort} onSort={handleSort} T={T} />
                <th style={{ padding: "12px 18px", textAlign: "left", color: T.textMuted, fontSize: 12, fontWeight: 600 }}>Active</th>
                <SortTh label="Joined" field="created_at"  sort={sort} onSort={handleSort} T={T} />
                <th style={{ padding: "12px 14px", width: 44 }} />
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={6} style={{ padding: 32, textAlign: "center", color: T.textMuted, fontSize: 13 }}>Loading users…</td></tr>
              ) : loadError ? (
                <tr><td colSpan={6} role="alert" style={{ padding: 28, textAlign: "center" }}>
                  <div style={{ color: T.danger, fontSize: 13.5, fontWeight: 600, marginBottom: 10 }}>{loadError}</div>
                  <Btn T={T} variant="outline" onClick={fetchUsers}>Retry</Btn>
                </td></tr>
              ) : sortedUsers.length === 0 ? (
                <tr><td colSpan={6}>
                  <EmptyState T={T} icon={IC.users} title="No users found" sub="Try adjusting the filter or search term." actionLabel="Clear filters" onAction={() => { setSearch(""); setTab("all"); setPage(1); }} />
                </td></tr>
              ) : sortedUsers.map((u, i) => (
                <tr key={u._id} style={{ borderBottom: i < sortedUsers.length - 1 ? `1px solid ${T.border}40` : "none", transition: "background 0.13s" }}
                  onMouseEnter={e => e.currentTarget.style.background = T.cardHi}
                  onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                  <td style={{ padding: "12px 18px" }}>
                    <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                      <Avatar name={u.full_name} size={34} />
                      <span style={{ color: T.text, fontWeight: 600, fontSize: 13.5 }}>{u.full_name}</span>
                    </div>
                  </td>
                  <td style={{ padding: "12px 18px", color: T.textMuted, fontSize: 13 }}>{u.email}</td>
                  <td style={{ padding: "12px 18px" }}><Badge label={u.role.charAt(0).toUpperCase()+u.role.slice(1)} type={u.role==="admin"?"primary":u.role==="lawyer"?"info":"gray"} T={T} /></td>
                  <td style={{ padding: "12px 18px" }}>
                    {u.is_closed ? (
                      // Deleted accounts are anonymised and cannot be reactivated.
                      <Badge label="Deleted" type="danger" T={T} />
                    ) : (
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <Toggle on={u.is_active} onChange={() => toggleStatus(u)} />
                        <span style={{ fontSize: 12, color: u.is_active ? T.success : T.textFaint, fontWeight: 500 }}>{u.is_active ? "Active" : "Inactive"}</span>
                      </div>
                    )}
                  </td>
                  <td style={{ padding: "12px 18px", color: T.textMuted, fontSize: 13 }}>{fmtDate(u.created_at)}</td>
                  <td style={{ padding: "12px 14px" }}>
                    {!u.is_closed && <ActionMenu T={T} actions={[
                      { label: "Edit user",      icon: IC.edit,  fn: () => openEdit(u) },
                      { label: "Send password reset", icon: IC.key, fn: () => openPw(u) },
                      { label: u.is_active ? "Deactivate" : "Activate", icon: IC.lock, fn: () => toggleStatus(u) },
                      { label: "Delete user",    icon: IC.trash, fn: () => setConfirmDel(u), danger: true },
                    ]} />}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Paginator T={T} total={total} page={page} perPage={perPage} onPage={setPage} onPerPage={n => { setPerPage(n); setPage(1); }} />
      </div>

      {/* Add / Edit User Modal */}
      <Modal open={modal==="add"||modal==="edit"} onClose={() => setModal(null)} title={modal==="add" ? "Add User" : "Edit User"} T={T}>
        <Input label="Full Name" value={formName} onChange={e => setFormName(e.target.value)} T={T} placeholder="Full name" />
        {modal === "add" ? (
          <Input label="Email" type="email" value={formEmail} onChange={e => setFormEmail(e.target.value)} T={T} placeholder="Email address" />
        ) : (
          // Read-only. The email is the sign-in and password-reset address, so
          // an admin who could change it could take over the account. Users
          // change their own email, confirmed by email.
          <div style={{ marginBottom: 14 }}>
            <label style={{ display: "block", color: T.textMuted, fontSize: 11.5, fontWeight: 700, marginBottom: 5, textTransform: "uppercase", letterSpacing: 0.6 }}>Email</label>
            <div style={{ padding: "9px 13px", borderRadius: 9, border: `1px solid ${T.border}`, color: T.textMuted, fontSize: 13.5 }}>{formEmail}</div>
            <div style={{ marginTop: 5, fontSize: 11.5, color: T.textFaint }}>Only the user can change their email.</div>
          </div>
        )}
        <div style={{ marginBottom: 14 }}>
          <label style={{ display: "block", color: T.textMuted, fontSize: 11.5, fontWeight: 700, marginBottom: 5, textTransform: "uppercase", letterSpacing: 0.6 }}>Role</label>
          <select value={formRole} onChange={e => setFormRole(e.target.value)}
            style={{ width: "100%", background: T.inputBg, border: `1px solid ${T.border}`, borderRadius: 9, padding: "9px 13px", color: T.text, fontSize: 13.5, outline: "none" }}>
            <option value="client">Client</option>
            <option value="lawyer">Lawyer</option>
            <option value="admin">Admin</option>
          </select>
          {modal==="edit" && sel && formRole !== sel.role && (
            <div style={{ marginTop: 6, fontSize: 12, color: T.warn, display: "flex", alignItems: "center", gap: 5 }}>
              <Ic d="M12 9v4M12 17h.01" size={13} color={T.warn} /> Role will change from <strong>{sel.role}</strong> → <strong>{formRole}</strong>
            </div>
          )}
        </div>
        {modal === "add" && (
          <div style={{ marginBottom: 14, fontSize: 12, color: T.textMuted }}>
            The new user will be emailed a link to set their own password.
          </div>
        )}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <Btn T={T} variant="ghost" onClick={() => setModal(null)}>Cancel</Btn>
          <Btn T={T} onClick={modal==="add" ? saveAdd : saveEdit} disabled={formSaving}>
            {formSaving ? "Saving…" : "Save changes"}
          </Btn>
        </div>
      </Modal>

      {/* Reset Password Modal */}
      <Modal open={modal==="pw"} onClose={() => setModal(null)} title="Send password reset" T={T}>
        <div style={{ fontSize: 13, color: T.textDim, lineHeight: 1.6, marginBottom: 18 }}>
          <strong style={{ color: T.text }}>{sel?.full_name}</strong> will be signed out on every device, their current
          password will stop working, and they will be emailed a link to set a new one. You will not see or choose the password.
        </div>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <Btn T={T} variant="ghost" onClick={() => setModal(null)}>Cancel</Btn>
          <Btn T={T} icon={IC.key} onClick={savePw} disabled={formSaving}>
            {formSaving ? "Sending…" : "Sign out and send link"}
          </Btn>
        </div>
      </Modal>
    </div>
  );
};
