'use client';
import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ONBOARDED_KEY } from '@/components/lawyer/OnboardingPage.jsx';
import { authRegister, authLogin } from '@/lib/api.js';
import { useAuth } from '@/context/AuthContext';
import { toPkPhone } from '@/lib/phone.js';
import { ResendForm } from '@/components/auth/ResendForm.jsx';
import {
  AuthShell, Brand, Checkbox, ConfirmVisual, Icon, NextCard, Notice, PasswordRules, PillInput, PrimaryButton,
  ShowToggle, SignupVisual, passwordProblem,
} from '@/components/auth/AuthShell.jsx';

const homeFor = (role) => (role === 'lawyer' ? '/lawyer' : role === 'admin' ? '/admin' : '/dashboard');


export default function RegisterPage() {
  const router = useRouter();
  const { login, user, loading: authLoading } = useAuth();

  const [role, setRole] = useState('client');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [terms, setTerms] = useState(false);
  const [loading, setLoading] = useState(false);
  const [apiError, setApiError] = useState('');
  // 'form' | 'confirm' (account made, email must be confirmed) | 'resend' | 'resent'
  const [stage, setStage] = useState('form');
  const [sentTo, setSentTo] = useState('');

  // Redirect already-authenticated users (only after auth hydration finishes)
  useEffect(() => {
    if (!authLoading && user) router.replace(homeFor(user.role));
  }, [authLoading, user]);

  async function handleCreate(e) {
    e?.preventDefault();
    if (!name.trim() || !email || !password) { setApiError('Your name, email and password are required.'); return; }
    const weak = passwordProblem(password);
    if (weak) { setApiError(weak); return; }
    if (!terms) { setApiError('Please accept the Terms and Privacy Policy.'); return; }
    setLoading(true);
    setApiError('');
    const { data: regData, error: regError } = await authRegister({
      full_name: name.trim(),
      email,
      password,
      role: role === 'lawyer' ? 'lawyer' : 'client',
      phone: toPkPhone(phone),
      accepted_terms: terms,
    });
    if (regError) {
      setLoading(false);
      setApiError(regError.message || 'Registration failed. Please try again.');
      return;
    }
    if (role === 'lawyer') { try { localStorage.removeItem(ONBOARDED_KEY); } catch { } }
    // The server sent a confirmation link; signing in waits for it.
    if (regData?.message === 'verify_email') {
      setLoading(false);
      setSentTo(email.trim());
      setStage('confirm');
      return;
    }
    // Auto-login after successful registration
    const { data: tokenData, error: loginError } = await authLogin(email, password);
    setLoading(false);
    if (loginError) {
      // Registration succeeded but the automatic sign-in did not (e.g. the
      // login rate limit). Say so on the login page instead of dropping the
      // user there with no explanation.
      router.push('/login?registered=1');
      return;
    }
    login(tokenData);
    router.push(homeFor(tokenData.role));
  }

  const isLawyer = role === 'lawyer';
  const toSignIn = () => router.push('/login');

  if (stage !== 'form') {
    return (
      <AuthShell visual={<ConfirmVisual stage="sent" />}
        next={<NextCard title="Confirmed it already?" sub="Sign in with your email and password." cta="Sign in" onClick={toSignIn} />}>
        <Brand />
        <h1 className="aa-title">Check your inbox</h1>
        {stage === 'resend' ? (
          <>
            <p className="aa-sub">Enter the email you signed up with and we will send a new confirmation link.</p>
            <ResendForm initialEmail={sentTo} onSent={(e) => { setSentTo(e); setStage('resent'); }} />
          </>
        ) : (
          <>
            <p className="aa-sub">
              {stage === 'resent'
                ? <>If <b style={{ color: 'var(--ink)' }}>{sentTo}</b> still needs confirming, a new link is on its way. Earlier links stop working.</>
                : <>Your account was created. We sent a confirmation link to <b style={{ color: 'var(--ink)' }}>{sentTo}</b>. Open it to finish signing up.</>}
            </p>
            <div className="aa-hint" style={{ textAlign: 'left', alignItems: 'flex-start', maxWidth: 400, justifySelf: 'center' }}>
              {Icon.info()}<span>The link works once and expires in 24 hours. Can&apos;t find it? Check your spam folder.</span>
            </div>
            <PrimaryButton type="button" onClick={toSignIn}>I&apos;ve confirmed, sign in</PrimaryButton>
            <button type="button" className="aa-ghost" onClick={() => setStage('resend')}>Send a new link</button>
          </>
        )}
      </AuthShell>
    );
  }

  return (
    <AuthShell
      visual={<SignupVisual role={role} />}
      next={<NextCard title="Already have an account?" sub="Sign in to continue where you left off."
        cta="Sign in" onClick={() => router.push('/login')} />}
    >
      <form onSubmit={handleCreate} noValidate style={{ display: 'contents' }}>
        <Brand />
        <h1 className="aa-title">Create your account</h1>
        <p className="aa-sub">{isLawyer
          ? 'Join as a lawyer. Clients can find you once your profile is complete.'
          : 'Free to start. Takes about a minute.'}</p>
        <div className="aa-role" role="group" aria-label="Account type">
          <button type="button" aria-pressed={!isLawyer} onClick={() => setRole('client')}>I need legal help</button>
          <button type="button" aria-pressed={isLawyer} onClick={() => setRole('lawyer')}>I&apos;m a lawyer</button>
        </div>
        <Notice>{apiError}</Notice>
        <PillInput icon={Icon.user()} label="Full name" placeholder={isLawyer ? 'Adv. Ayesha Khan' : 'Ayesha Khan'}
          autoComplete="name" value={name} onChange={e => setName(e.target.value)} />
        <PillInput icon={Icon.mail()} label="Email" type="email" placeholder="you@example.com" autoComplete="email"
          value={email} onChange={e => setEmail(e.target.value)} />
        <PillInput prefix="+92" label="Phone number (optional)" type="tel" placeholder="300 1234567 · optional"
          autoComplete="tel-national" value={phone} onChange={e => setPhone(e.target.value)} />
        <PillInput icon={Icon.lock()} label="Password" type={showPw ? 'text' : 'password'} placeholder="Create a password"
          autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)}
          side={<ShowToggle shown={showPw} onToggle={() => setShowPw(p => !p)} />} />
        <PasswordRules value={password} />
        <div style={{ display: 'flex', justifyContent: 'center' }}>
          <Checkbox checked={terms} onChange={setTerms}>
            {/* New tab, so following a link does not lose what was typed. */}
            I agree to the <a href="/terms" target="_blank" rel="noopener" className="aa-link" style={{ fontWeight: 700 }}>Terms</a> and{' '}
            <a href="/privacy" target="_blank" rel="noopener" className="aa-link" style={{ fontWeight: 700 }}>Privacy Policy</a>
          </Checkbox>
        </div>
        <PrimaryButton type="submit" busy={loading} busyLabel="Creating your account…">
          {isLawyer ? 'Create account and set up profile' : 'Create account'}
        </PrimaryButton>
      </form>
    </AuthShell>
  );
}
