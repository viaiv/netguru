import { useEffect, useState } from 'react';
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';

import ChatPage from './pages/ChatPage';
import LoginPage from './pages/LoginPage';
import MePage from './pages/MePage';
import RegisterPage from './pages/RegisterPage';
import ProtectedRoute from './components/ProtectedRoute';
import AdminRoute from './components/admin/AdminRoute';
import AdminLayout from './components/admin/AdminLayout';
import { AUTH_LOGOUT_EVENT, dispatchAuthLogout, type IAuthLogoutEventDetail } from './services/authEvents';
import { useAuthStore } from './stores/authStore';

function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const user = useAuthStore((state) => state.user);
  const isAdmin = user?.role === 'owner' || user?.role === 'admin';
  const hasRefreshToken = Boolean(useAuthStore((state) => state.refreshToken));
  const refreshStatus = useAuthStore((state) => state.refreshStatus);
  const lastRefreshAt = useAuthStore((state) => state.lastRefreshAt);
  const clearAuth = useAuthStore((state) => state.clearAuth);
  const resetRefreshStatus = useAuthStore((state) => state.resetRefreshStatus);

  const isAdminRoute = location.pathname.startsWith('/admin');

  const [railCollapsed, setRailCollapsed] = useState(false);

  const refreshStatusLabel = {
    idle: 'refresh idle',
    refreshing: 'renovando',
    refreshed: 'renovado',
    expired: 'expirado',
  }[refreshStatus];

  const lastRefreshLabel = lastRefreshAt
    ? new Date(lastRefreshAt).toLocaleTimeString('pt-BR', {
        hour: '2-digit',
        minute: '2-digit',
      })
    : '--:--';

  function handleLogout(): void {
    dispatchAuthLogout('manual');
  }

  useEffect(() => {
    if (refreshStatus !== 'refreshed') {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      resetRefreshStatus();
    }, 3000);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [refreshStatus, resetRefreshStatus]);

  useEffect(() => {
    function handleAuthLogout(event: Event): void {
      const logoutEvent = event as CustomEvent<IAuthLogoutEventDetail>;
      clearAuth();
      navigate('/login', {
        replace: true,
        state: {
          logoutReason: logoutEvent.detail?.reason ?? 'session_expired',
        },
      });
    }

    window.addEventListener(AUTH_LOGOUT_EVENT, handleAuthLogout);
    return () => {
      window.removeEventListener(AUTH_LOGOUT_EVENT, handleAuthLogout);
    };
  }, [clearAuth, navigate]);

  // Admin area — layout proprio, sem header/sidebar do app
  if (isAdminRoute) {
    return (
      <div className="app-shell app-shell--admin">
        <div className="bg-grid" />
        <div className="bg-glow bg-glow-a" />
        <div className="bg-glow bg-glow-b" />
        <Routes>
          <Route
            path="/admin/*"
            element={
              <AdminRoute>
                <AdminLayout />
              </AdminRoute>
            }
          />
        </Routes>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <div className="bg-grid" />
      <div className="bg-glow bg-glow-a" />
      <div className="bg-glow bg-glow-b" />

      <header className="chrome">
        <div className="brand-block">
          <p className="kicker">NetGuru</p>
          <h1 className="brand-title">Agentic Network Console</h1>
        </div>

        <div className="status-strip">
          <span className={isAuthenticated ? 'status-dot online' : 'status-dot offline'} />
          <span>{isAuthenticated ? 'Session Active' : 'Session Locked'}</span>
          <span className={hasRefreshToken ? 'chip chip-live' : 'chip'}>refresh</span>
          <span className={`chip chip-refresh-${refreshStatus}`}>{refreshStatusLabel}</span>
          <span className="chip chip-muted">{lastRefreshLabel}</span>
          <span className="chip">phase 1</span>
        </div>
      </header>

      <div className={`layout ${railCollapsed ? 'layout--collapsed' : ''}`}>
        <aside className={`rail ${railCollapsed ? 'rail--collapsed' : ''}`}>
          <button
            type="button"
            className="rail-toggle"
            onClick={() => setRailCollapsed((prev) => !prev)}
            title={railCollapsed ? 'Expandir menu' : 'Recolher menu'}
          >
            {railCollapsed ? '\u25B6' : '\u25C0'}
          </button>

          <nav className="nav">
            <NavLink
              to="/login"
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
              title="Login"
            >
              {railCollapsed ? '\uD83D\uDD12' : 'Login'}
            </NavLink>
            <NavLink
              to="/register"
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
              title="Cadastro"
            >
              {railCollapsed ? '\uD83D\uDCDD' : 'Cadastro'}
            </NavLink>
            <NavLink
              to="/chat"
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
              title="Chat"
            >
              {railCollapsed ? '\uD83D\uDCAC' : 'Chat'}
            </NavLink>
            <NavLink
              to="/me"
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
              title="Perfil"
            >
              {railCollapsed ? '\uD83D\uDC64' : 'Perfil'}
            </NavLink>
            {isAdmin && (
              <NavLink
                to="/admin"
                className={({ isActive }) => `nav-link nav-link--admin ${isActive ? 'active' : ''}`}
                title="Admin"
              >
                {railCollapsed ? '\u2699' : 'Admin'}
              </NavLink>
            )}
          </nav>

          {!railCollapsed && (
            <div className="rail-card">
              <p className="rail-label">current route</p>
              <p className="rail-value">{location.pathname}</p>
              <p className="rail-help">
                Fluxo: <code>/register</code> → <code>/login</code> → <code>/chat</code>.
              </p>
              {isAuthenticated ? (
                <button type="button" className="ghost-btn" onClick={handleLogout}>
                  Encerrar sessão
                </button>
              ) : null}
            </div>
          )}
        </aside>

        <main className="panel">
          <div className="panel-inner">
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
              <Route
                path="/chat"
                element={
                  <ProtectedRoute>
                    <ChatPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/me"
                element={
                  <ProtectedRoute>
                    <MePage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="*"
                element={<Navigate to={isAuthenticated ? '/chat' : '/login'} replace />}
              />
            </Routes>
          </div>
        </main>
      </div>
    </div>
  );
}

export default App;
