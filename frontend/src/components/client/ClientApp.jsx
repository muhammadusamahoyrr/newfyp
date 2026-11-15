'use client';
import { useState, useEffect, useMemo } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { tabForPath } from './clientRoutes.js';
import { useAuth } from '@/context/AuthContext.jsx';
import Dashboard from './Dashboard.jsx';
import { DARK, LIGHT } from '@/components/admin/themes.js';
import { CLIENT_THEME_REFINED, clientThemeOnTokens } from './clientTheme.js';
import { ToastContainer } from '@/components/shared/Toast.jsx';

// The client's theme choice:
//   'light'  — the light theme (refined);
//   'system' — the app's OWN original theme, exactly as it was (dark);
//   'dark'   — the refined dark theme.
// Kept under its own key; 'aai-theme' still holds the resolved 'dark'/'light'.
// With nothing saved, the app opens in its original theme, as it always did.
const PREF_KEY = 'aai-client-theme-pref';
const PREFS = ['light', 'system', 'dark'];

// Mounted ONCE by app/(client)/layout.jsx and kept alive across client URLs;
// the URL picks the tab (see clientRoutes.js). `initialTab` still wins when
// given (tests mount this directly).
export default function ClientApp({ initialTab }) {
  const router = useRouter();
  const pathname = usePathname();
  const [startTab] = useState(() => initialTab || tabForPath(pathname) || 'overview');
  const { logout } = useAuth();
  const [themePref, setThemePref] = useState('system');

  useEffect(() => {
    try {
      const pref = localStorage.getItem(PREF_KEY);
      const saved = localStorage.getItem('aai-theme');
      if (PREFS.includes(pref)) setThemePref(pref);
      else if (saved === 'light') setThemePref('light');
    } catch {}
  }, []);

  const isDark = themePref !== 'light';
  // The refinements apply to Light and Dark; "System" is the original look.
  const refined = CLIENT_THEME_REFINED && themePref !== 'system';

  useEffect(() => {
    try {
      localStorage.setItem(PREF_KEY, themePref);
      localStorage.setItem('aai-theme', isDark ? 'dark' : 'light');
    } catch {}
  }, [themePref, isDark]);

  const toggleTheme = () => setThemePref(isDark ? 'light' : 'system');
  const toastTheme = useMemo(() => clientThemeOnTokens(isDark ? DARK : LIGHT, { refined }), [isDark, refined]);

  // The ONE toast provider for every live client screen. Without it useToast()
  // fell back to a no-op and every client toast — successes and refusals alike —
  // was silently dropped; the only container lived in the unused legacy App.jsx.
  return (
    <ToastContainer theme={toastTheme}>
      <Dashboard
        initialTab={startTab}
        isDark={isDark}
        toggleTheme={toggleTheme}
        themePref={themePref}
        setThemePref={setThemePref}
        refined={refined}
        go={async (target) => {
          if (target === 'signout') { await logout(); router.push('/'); }
          else if (target === 'landing') router.push('/');
          else if (target === 'login') router.push('/login');
        }}
      />
    </ToastContainer>
  );
}
