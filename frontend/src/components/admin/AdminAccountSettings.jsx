'use client';
// Admin account: change the admin's own password.
//
// /admin/account-settings used to render the dashboard and this file was an
// empty stub, so an admin had no screen to change their own password. The
// server endpoint is the same one lawyers and clients use; changing the
// password ends every session, so the admin is signed out afterwards.
import { useState } from 'react';
import { changePassword } from '@/lib/api.js';
import { useAuth } from '@/context/AuthContext.jsx';
import { Btn, Input } from '@/components/admin/AdminComponent.jsx';

export function AccountSettings({ T }) {
  const { logout } = useAuth();
  const [pwd, setPwd] = useState({ current: '', next: '', confirm: '' });
  const [issue, setIssue] = useState(null);
  const [saving, setSaving] = useState(false);

  const set = (k) => (e) => setPwd(p => ({ ...p, [k]: e.target.value }));

  const save = async () => {
    setIssue(null);
    if (!pwd.current || !pwd.next) return setIssue('Enter your current password and a new one.');
    if (pwd.next !== pwd.confirm) return setIssue('The new passwords do not match.');
    if (pwd.next === pwd.current) return setIssue('Choose a password different from the current one.');
    setSaving(true);
    const { error } = await changePassword(pwd.current, pwd.next);
    setSaving(false);
    if (error) return setIssue(error.message || 'Password change failed.');
    // Every session was revoked by the server, this one included.
    try { await logout(); } catch { /* already signed out */ }
    window.location.assign('/login');
  };

  return (
    <div className="admin-page-enter" style={{ maxWidth: 520 }}>
      <h2 style={{ color: T.text, fontSize: 20, fontWeight: 700, margin: '0 0 6px' }}>Account</h2>
      <p style={{ color: T.textMuted, fontSize: 13, margin: '0 0 20px' }}>
        Change your admin password. You will be signed out on every device and asked to sign in again.
      </p>
      <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 14, padding: 22 }}>
        <Input T={T} label="Current password" type="password" value={pwd.current} onChange={set('current')} />
        <Input T={T} label="New password" type="password" value={pwd.next} onChange={set('next')}
          placeholder="8+ characters, a number and an uppercase letter" />
        <Input T={T} label="Confirm new password" type="password" value={pwd.confirm} onChange={set('confirm')} />
        {issue && <div role="alert" style={{ color: T.danger, fontSize: 12.5, margin: '0 0 12px' }}>{issue}</div>}
        <Btn T={T} onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Change password'}</Btn>
      </div>
    </div>
  );
}

export default AccountSettings;
