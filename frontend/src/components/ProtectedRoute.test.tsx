import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';

import ProtectedRoute from './ProtectedRoute';
import { useAuthStore } from '../stores/authStore';

function resetAuthStore(): void {
  localStorage.clear();
  useAuthStore.setState({
    accessToken: null,
    refreshToken: null,
    isAuthenticated: false,
    refreshStatus: 'idle',
    lastRefreshAt: null,
  });
}

function renderAppAt(pathname: string): void {
  render(
    <MemoryRouter
      initialEntries={[pathname]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route path="/login" element={<div>login page</div>} />
        <Route
          path="/me"
          element={
            <ProtectedRoute>
              <div>private profile</div>
            </ProtectedRoute>
          }
        />
      </Routes>
    </MemoryRouter>
  );
}

describe('ProtectedRoute', () => {
  beforeEach(() => {
    resetAuthStore();
  });

  it('redirects to login when user is not authenticated', () => {
    renderAppAt('/me');
    expect(screen.getByText('login page')).toBeInTheDocument();
  });

  it('preserves query/hash path in login redirect state', () => {
    const observedStates: unknown[] = [];

    render(
      <MemoryRouter
        initialEntries={['/me?view=raw#diag']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route
            path="/login"
            element={
              <div>
                login page
                <RouteStateProbe onRead={(state) => observedStates.push(state)} />
              </div>
            }
          />
          <Route
            path="/me"
            element={
              <ProtectedRoute>
                <div>private profile</div>
              </ProtectedRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText('login page')).toBeInTheDocument();
    expect(observedStates).toEqual([{ from: '/me?view=raw#diag' }]);
  });

  it('renders protected content when user is authenticated', () => {
    useAuthStore.setState({
      accessToken: 'access-token',
      refreshToken: 'refresh-token',
      isAuthenticated: true,
      refreshStatus: 'idle',
      lastRefreshAt: null,
    });

    renderAppAt('/me');
    expect(screen.getByText('private profile')).toBeInTheDocument();
  });
});

function RouteStateProbe({ onRead }: { onRead: (state: unknown) => void }) {
  const location = useLocation();
  onRead(location.state);
  return null;
}
