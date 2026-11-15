import { redirect } from 'next/navigation';

// Agreements are hidden from lawyers for now (2026-10-19, user's request). The
// page component is kept; to bring it back, render
// <App initialPage="agreements" /> here again, restore the nav item in
// components/lawyer/layout.jsx and take it out of HIDDEN_PAGES in App.jsx.
export default function Page() { redirect('/lawyer'); }
