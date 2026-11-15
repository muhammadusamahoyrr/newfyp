'use client';
import React, { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { authVerifyEmail } from '@/lib/api.js';
import { ResendForm } from '@/components/auth/ResendForm.jsx';
import {
  AuthShell, Brand, ConfirmVisual, Icon, NextCard, PrimaryButton,
} from '@/components/auth/AuthShell.jsx';

// The emailed link is /verify-email#token=… (fragment: never sent to a server).
// The token is read once, removed from the address bar, and confirmed once;
// the server deletes it on use, so a second visit says the link is used up.
export default function VerifyEmailPage() {
  const router = useRouter();
  const [stage, setStage] = useState('loading');
  const [sentTo, setSentTo] = useState('');
  const started = useRef(false);   // dev StrictMode runs effects twice; the token works once

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const token = new URLSearchParams(window.location.hash.slice(1)).get('token') || '';
    if (window.location.hash) window.history.replaceState(null, '', window.location.pathname);
    if (!token) { setStage('request'); return; }
    setStage('checking');
    authVerifyEmail(token).then(({ error }) => setStage(error ? 'expired' : 'done'));
  }, []);

  const toSignIn = () => router.push('/login');
  if (stage === 'loading') return null;

  let body;
  if (stage === 'checking') body = (
    <>
      <Brand />
      <h1 className="aa-title">Confirming your email…</h1>
      <p className="aa-sub">This takes a moment.</p>
    </>
  );
  else if (stage === 'done') body = (
    <>
      {/* Only reachable after /auth/verify-email returned success. */}
      <Brand />
      <h1 className="aa-title">Email confirmed</h1>
      <p className="aa-sub">Your account is ready. Sign in to continue.</p>
      <PrimaryButton type="button" onClick={toSignIn}>Sign in</PrimaryButton>
    </>
  );
  else if (stage === 'sent') body = (
    <>
      <Brand />
      <h1 className="aa-title">Check your inbox</h1>
      {/* Same answer for every address: does not say whether it is registered. */}
      <p className="aa-sub">If <b style={{ color: 'var(--ink)' }}>{sentTo}</b> still needs confirming, a new link is on its way. Earlier links stop working.</p>
      <div className="aa-hint" style={{ textAlign: 'left', alignItems: 'flex-start', maxWidth: 400, justifySelf: 'center' }}>
        {Icon.info()}<span>Can&apos;t find it? Check your spam folder.</span>
      </div>
      <button type="button" className="aa-ghost" onClick={() => setStage('request')}>Use a different email</button>
    </>
  );
  else body = (
    <>
      <Brand />
      <h1 className="aa-title">{stage === 'expired' ? 'This link has expired' : 'Confirm your email'}</h1>
      <p className="aa-sub">{stage === 'expired'
        ? 'Confirmation links work once and expire after 24 hours. Enter your email and we will send a new one.'
        : 'Enter the email you signed up with and we will send you a new confirmation link.'}</p>
      <ResendForm onSent={(e) => { setSentTo(e); setStage('sent'); }} />
    </>
  );

  return (
    <AuthShell visual={<ConfirmVisual stage={stage} />}
      next={<NextCard title="Already confirmed?" sub="Sign in with your email and password." cta="Sign in" onClick={toSignIn} />}>
      {body}
    </AuthShell>
  );
}
