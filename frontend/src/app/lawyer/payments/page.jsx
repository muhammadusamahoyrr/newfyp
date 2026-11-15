import { redirect } from 'next/navigation';

// Payments are hidden from lawyers for now (2026-10-19, user's request). The
// page component is kept; to bring it back, render
// <App initialPage="payments" /> here again and restore the nav item in
// components/lawyer/layout.jsx.
export default function Page() { redirect('/lawyer'); }
