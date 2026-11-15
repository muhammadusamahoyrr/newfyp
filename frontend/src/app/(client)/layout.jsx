'use client';
import ProtectedRoute from '@/components/shared/ProtectedRoute';
import ClientApp from '@/components/client/ClientApp';

// The client app is mounted HERE, once, and survives navigation between client
// URLs; the URL only chooses the visible screen (components/client/clientRoutes.js).
// Each page used to render its own <ClientApp>, so every sidebar click tore down
// and rebuilt the shell, reloaded cases/appointments/notifications and reopened
// the notification socket. The pages now render nothing themselves; a page that
// needs to act (e.g. documents/analyzer's redirect) still runs as `children`.
export default function ClientLayout({ children }) {
  return (
    <ProtectedRoute allowedRoles={['client']}>
      <ClientApp />
      {children}
    </ProtectedRoute>
  );
}
