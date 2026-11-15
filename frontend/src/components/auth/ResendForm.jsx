'use client';
import React, { useState } from 'react';
import { authResendVerification } from '@/lib/api.js';
import { Icon, Notice, PillInput, PrimaryButton } from '@/components/auth/AuthShell.jsx';

// Ask for a new email-confirmation link. The server answers the same for every
// address, so `onSent` never means "this account exists".
export function ResendForm({ initialEmail = '', onSent }) {
  const [email, setEmail] = useState(initialEmail);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const send = async (e) => {
    e?.preventDefault();
    if (!email.trim()) { setError('Enter the email you signed up with.'); return; }
    setBusy(true); setError('');
    const { error: err } = await authResendVerification(email.trim());
    setBusy(false);
    if (err) { setError(err.message || 'Could not send a new link. Please try again.'); return; }
    onSent(email.trim());
  };
  return (
    <form onSubmit={send} noValidate style={{ display: 'contents' }}>
      <Notice>{error}</Notice>
      <PillInput icon={Icon.mail()} label="Email" type="email" placeholder="you@example.com" autoComplete="email"
        value={email} onChange={e => setEmail(e.target.value)} error={!!error} />
      <PrimaryButton type="submit" busy={busy} busyLabel="Sending…">Send a new link</PrimaryButton>
    </form>
  );
}

export default ResendForm;
