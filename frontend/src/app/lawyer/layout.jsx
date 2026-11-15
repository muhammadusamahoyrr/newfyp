'use client';
import ProtectedRoute from '@/components/shared/ProtectedRoute';
import { ChatDockProvider } from '@/components/lawyer/ChatDock.jsx';

// The chat windows live here, above the pages, so they stay open while the
// lawyer moves between them (2026-10-19).
export default function LawyerLayout({ children }) {
  return <ProtectedRoute allowedRoles={['lawyer']}><ChatDockProvider>{children}</ChatDockProvider></ProtectedRoute>;
}
