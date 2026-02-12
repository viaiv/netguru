import type { ReactElement } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

import { useAuthStore } from '../stores/authStore';

interface IProtectedRouteProps {
  children: ReactElement;
}

function ProtectedRoute({ children }: IProtectedRouteProps) {
  const location = useLocation();
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const from = `${location.pathname}${location.search}${location.hash}`;

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from }} />;
  }

  return children;
}

export default ProtectedRoute;
