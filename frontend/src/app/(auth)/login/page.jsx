'use client';
import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { authLogin } from '@/lib/api.js';
import { useAuth } from '@/context/AuthContext';
import { ResendForm } from '@/components/auth/ResendForm.jsx';
import {
  AuthShell, Brand, Icon, LoginVisual, NextCard, Notice, PillInput, PrimaryButton, ShowToggle,
} from '@/components/auth/AuthShell.jsx';

const homeFor = (role) => (role === 'lawyer' ? '/lawyer' : role === 'admin' ? '/admin' : '/dashboard');

export default function LoginPage() {
  const router = useRouter();
  const { login, user, loading: authLoading } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [apiError, setApiError] = useState('');

  const [info, setInfo] = useState('');
  // Right password, email not confirmed yet: offer a new link here.
  const [unconfirmed, setUnconfirmed] = useState(false);
  const [resent, setResent] = useState(false);

  useEffect(() => {
    if (!authLoading && user) router.replace(homeFor(user.role));
  }, [authLoading, user]);

  // Sent here by the register page when the account was created but the
  // automatic sign-in after it failed.
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get('registered') === '1') {
      setInfo('Your account was created. Please sign in to continue.');
      window.history.replaceState(null, '', window.location.pathname);
    }
  }, []);

  async function handleSignIn(e) {
    e?.preventDefault();
    if (!email || !password) { setApiError('Please enter your email and password.'); return; }
    setLoading(true);
    setApiError('');
    setUnconfirmed(false);
    const { data, error } = await authLogin(email, password);
    setLoading(false);
    if (error?.code === 'email_not_verified') {
      setUnconfirmed(true);
      setResent(false);
      return;
    }
    if (error) {
      setApiError(error.message || 'Invalid email or password.');
      return;
    }
    login(data); // sets user in AuthContext immediately
    router.push(homeFor(data.role));
  }

  const busy = loading || authLoading;

  return (
    <AuthShell
      visual={<LoginVisual />}
      next={<NextCard title="New to Attorney.AI?" sub="Create a free account in about a minute."
        cta="Sign up" icons={['book', 'chat', 'shield']} onClick={() => router.push('/register')} />}
    >
      <form onSubmit={handleSignIn} noValidate style={{ display: 'contents' }}>
        <Brand />
        <h1 className="aa-title">Welcome back</h1>
        <p className="aa-sub">Sign in to get legal guidance grounded in Pakistani law, and stay in touch with your lawyer.</p>
        {apiError ? <Notice>{apiError}</Notice> : <Notice tone="info">{info}</Notice>}
        <PillInput icon={Icon.mail()} label="Email" type="email" placeholder="you@example.com" autoComplete="email"
          value={email} onChange={e => setEmail(e.target.value)} error={!!apiError && !email} />
        <PillInput icon={Icon.lock()} label="Password" type={showPw ? 'text' : 'password'} placeholder="Password"
          autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)}
          error={!!apiError && !password} side={<ShowToggle shown={showPw} onToggle={() => setShowPw(p => !p)} />} />
        {/* No "Remember me" box: it was never sent to the server, and every
            sign-in gets the same 7-day session (refresh_token_expire_days), so
            the old "Remember me for 90 days" promised something that did not happen. */}
        <div className="aa-row" style={{ justifyContent: 'flex-end' }}>
          <button type="button" className="aa-link" onClick={() => router.push('/reset-password')}>Forgot password?</button>
        </div>
        <PrimaryButton type="submit" busy={busy} busyLabel={authLoading ? 'Checking session…' : 'Signing in…'}>Sign in</PrimaryButton>
      </form>
      {unconfirmed && (
        <div data-unconfirmed style={{ display: 'contents' }}>
          <Notice tone="info">{resent
            ? 'If this account still needs confirming, a new link is on its way. Earlier links stop working.'
            : 'Please confirm your email first. Open the link we sent when you signed up, or get a new one below.'}</Notice>
          {!resent && <ResendForm initialEmail={email} onSent={() => setResent(true)} />}
        </div>
      )}
    </AuthShell>
  );
}
