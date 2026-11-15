'use client';
import React, { useEffect, useState, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { authForgotPassword, authResetPassword } from '@/lib/api.js';
import {
  AuthShell, Brand, Icon, NextCard, Notice, PasswordRules, PillInput, PrimaryButton, RecoveryVisual, ShowToggle,
  passwordProblem,
} from '@/components/auth/AuthShell.jsx';

// The real flow has two halves that happen in different sessions: request a
// link by email, then follow that link back here with ?token=... . Each stage
// is only reached after the matching API call succeeds.

// /auth/reset-password answers "Invalid or expired reset token" for a stale or
// already-used link; that needs a fresh link, not another attempt here.
const isDeadLink = (msg = '') => /expired|invalid.*token|reset token/i.test(msg);

function ForgotPw({ goBack }) {
  const params = useSearchParams();
  // The emailed link carries the secret in the fragment (#token=…), which never
  // reaches a server. Links sent before that change used ?token=…; those still
  // work for their one-hour life. Either way the token is read once and then
  // removed from the address bar, so it does not stay in history.
  const [token, setToken] = useState('');
  const [stage, setStage] = useState('loading');

  useEffect(() => {
    const fromHash = new URLSearchParams(window.location.hash.slice(1)).get('token') || '';
    const fromQuery = params?.get('token') || '';
    const found = fromHash || fromQuery;
    if (window.location.hash || fromQuery) {
      window.history.replaceState(null, '', window.location.pathname);
    }
    setToken(found);
    setStage(found ? 'reset' : 'request');
  }, []);

  const [email, setEmail] = useState('');
  const [pw, setPw] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const sendLink = async (e) => {
    e?.preventDefault();
    setError(null);
    if (!email.trim()) { setError('Enter the email you signed up with.'); return; }
    setBusy(true);
    const { error: err } = await authForgotPassword(email.trim());
    setBusy(false);
    if (err) { setError(err.message || 'Could not send the reset link. Please try again.'); return; }
    setStage('sent');
  };

  const submitNewPassword = async (e) => {
    e?.preventDefault();
    setError(null);
    const problem = passwordProblem(pw);
    if (problem) { setError(problem); return; }
    if (pw !== confirm) { setError('The two passwords do not match.'); return; }
    setBusy(true);
    const { error: err } = await authResetPassword(token, pw);
    setBusy(false);
    if (err) {
      if (isDeadLink(err.message)) { setStage('expired'); return; }
      setError(err.message || 'Could not reset the password. Please try again.');
      return;
    }
    setStage('done');
  };

  const startOver = () => { setError(null); setStage('request'); };
  const backToSignIn = <NextCard title="Remembered your password?" sub="Go back and sign in." cta="Sign in" onClick={goBack} />;

  // Until the token has been read from the URL, render nothing rather than a
  // stage that may be wrong (the final `else` below is the success screen).
  if (stage === 'loading') return null;

  let body;
  if (stage === 'request') body = (
    <form onSubmit={sendLink} noValidate style={{ display: 'contents' }}>
      <button type="button" className="aa-link aa-back" onClick={goBack}>{Icon.back()}Back to sign in</button>
      <Brand />
      <h1 className="aa-title">Forgot your password?</h1>
      <p className="aa-sub">Enter the email you signed up with and we&apos;ll send you a secure link to set a new one.</p>
      <Notice>{error}</Notice>
      <PillInput icon={Icon.mail()} label="Email" type="email" placeholder="you@example.com" autoComplete="email"
        value={email} onChange={e => setEmail(e.target.value)} error={!!error} />
      <PrimaryButton type="submit" busy={busy} busyLabel="Sending…">Send reset link</PrimaryButton>
    </form>
  );
  else if (stage === 'sent') body = (
    <>
      <Brand />
      <h1 className="aa-title">Check your inbox</h1>
      {/* Deliberately does not confirm whether the address is registered —
          the endpoint answers the same either way. */}
      <p className="aa-sub">If an account exists for <b style={{ color: 'var(--ink)' }}>{email}</b>, a reset link is on its way. It works once and expires in 1 hour.</p>
      {/* No "Resend" button: the server keeps ONE active link per account and
          silently ignores a second request while it is valid (auth_service.
          forgot_password, DuplicateKeyError), so a resend would not send. */}
      <div className="aa-hint" style={{ textAlign: 'left', alignItems: 'flex-start', maxWidth: 400, justifySelf: 'center' }}>
        {Icon.info()}<span>Can&apos;t find it? Check your spam folder. Only one link is active at a time; you can ask for a new one after this one expires.</span>
      </div>
      <button type="button" className="aa-ghost" onClick={startOver}>Use a different email</button>
    </>
  );
  else if (stage === 'reset') body = (
    <form onSubmit={submitNewPassword} noValidate style={{ display: 'contents' }}>
      <Brand />
      <h1 className="aa-title">Set a new password</h1>
      <p className="aa-sub">Pick a strong password you don&apos;t use on other sites.</p>
      <Notice>{error}</Notice>
      <PillInput icon={Icon.lock()} label="New password" type={showPw ? 'text' : 'password'} placeholder="New password"
        autoComplete="new-password" value={pw} onChange={e => setPw(e.target.value)}
        side={<ShowToggle shown={showPw} onToggle={() => setShowPw(p => !p)} />} />
      <PasswordRules value={pw} />
      <PillInput icon={Icon.lock()} label="Confirm new password" type={showPw ? 'text' : 'password'} placeholder="Type it again"
        autoComplete="new-password" value={confirm} onChange={e => setConfirm(e.target.value)}
        error={!!confirm && confirm !== pw && confirm.length >= pw.length} />
      {confirm && confirm === pw && <div className="aa-hint ok">{Icon.check()}Passwords match</div>}
      <PrimaryButton type="submit" busy={busy} busyLabel="Updating…">Update password</PrimaryButton>
    </form>
  );
  else if (stage === 'expired') body = (
    <>
      <Brand />
      <h1 className="aa-title">This link has expired</h1>
      <p className="aa-sub">Reset links work once and expire after an hour. Request a new one and use the latest email we send.</p>
      <PrimaryButton type="button" onClick={startOver}>Send a new link</PrimaryButton>
      <button type="button" className="aa-ghost" onClick={goBack}>Back to sign in</button>
    </>
  );
  else body = (
    <>
      {/* Only reachable after /auth/reset-password returned success. */}
      <Brand />
      <h1 className="aa-title">Password updated</h1>
      <p className="aa-sub">Your password has been changed and you&apos;ve been signed out on every device. Sign in with your new password.</p>
      <PrimaryButton type="button" onClick={goBack}>Sign in</PrimaryButton>
    </>
  );

  return (
    <AuthShell visual={<RecoveryVisual stage={stage} />}
      next={stage === 'done'
        ? <NextCard title="Keep your account safe" sub="Use a password you don't use anywhere else." cta="Sign in" onClick={goBack} />
        : backToSignIn}>
      {body}
    </AuthShell>
  );
}

export default function ResetPasswordPage() {
  const router = useRouter();
  // useSearchParams needs a Suspense boundary during static prerender.
  return (
    <Suspense fallback={null}>
      <ForgotPw goBack={() => router.push('/login')} />
    </Suspense>
  );
}
