/**
 * AdminRoute — ProtectedRoute + role check for owner/admin.
 */
import type { ReactElement } from 'react';
import { Navigate } from 'react-router-dom';

import { useAuthStore } from '../../stores/authStore';

interface IAdminRouteProps {
  children: ReactElement;
}

function AdminRoute({ children }: IAdminRouteProps) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const user = useAuthStore((s) => s.user);

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  // While user data is loading, show nothing
  if (!user) {
    return null;
  }

  if (user.role !== 'owner' && user.role !== 'admin') {
    return <Navigate to="/chat" replace />;
  }

  return children;
}

export default AdminRoute;
