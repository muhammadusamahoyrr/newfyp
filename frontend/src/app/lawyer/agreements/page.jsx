import App from '@/components/lawyer/App';

// Restored 2026-11-25. It had been hidden (2026-10-19), which left every
// agreement sent to a lawyer unsignable: no page, no case-page view, and the
// notification opened a case that does not show agreements.
export default function Page() { return <App initialPage="agreements" />; }
