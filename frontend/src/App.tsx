import { useEffect, useState } from 'react';
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';

import ChatPage from './pages/ChatPage';
import FilesPage from './pages/FilesPage';
import ForgotPasswordPage from './pages/ForgotPasswordPage';
import HomePage from './pages/HomePage';
import LoginPage from './pages/LoginPage';
import MePage from './pages/MePage';
import MemoriesPage from './pages/MemoriesPage';
import PcapDashboardPage from './pages/PcapDashboardPage';
import PricingPage from './pages/PricingPage';
import RegisterPage from './pages/RegisterPage';
import ResetPasswordPage from './pages/ResetPasswordPage';
import VerifyEmailPage from './pages/VerifyEmailPage';
import ProtectedRoute from './components/ProtectedRoute';
import AdminRoute from './components/admin/AdminRoute';
import AdminLayout from './components/admin/AdminLayout';
import { useMobile } from './hooks/useMediaQuery';
import { AUTH_LOGOUT_EVENT, dispatchAuthLogout, type IAuthLogoutEventDetail } from './services/authEvents';
import { useAuthStore } from './stores/authStore';

function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const user = useAuthStore((state) => state.user);
  const isAdmin = user?.role === 'owner' || user?.role === 'admin';
  const clearAuth = useAuthStore((state) => state.clearAuth);

  const isAdminRoute = location.pathname.startsWith('/admin');
  const isMobile = useMobile();

  const [railCollapsed, setRailCollapsed] = useState(false);

  const hideRail = !isAuthenticated;

  function handleLogout(): void {
    dispatchAuthLogout('manual');
  }

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

  const isHomePage = location.pathname === '/home';
  const isPricingPage = location.pathname === '/pricing';
  const isPcapRoute = location.pathname.startsWith('/pcap/');

  // PCAP dashboard — layout fullscreen, sem chrome/rail/panel
  if (isPcapRoute) {
    return (
      <Routes>
        <Route
          path="/pcap/:messageId"
          element={
            <ProtectedRoute>
              <PcapDashboardPage />
            </ProtectedRoute>
          }
        />
      </Routes>
    );
  }

  // Landing page — layout proprio, sem chrome/rail/panel
  if (isHomePage) {
    return <HomePage />;
  }

  // Pricing page — layout publico com chrome minimo
  if (isPricingPage) {
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
        </header>
        <main className="panel" style={{ marginLeft: 0 }}>
          <div className="panel-inner">
            <PricingPage />
          </div>
        </main>
      </div>
    );
  }

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
          <span>{isAuthenticated ? 'Conectado' : 'Desconectado'}</span>
          {isAuthenticated && user && (
            <span className="chip chip-live">{user.full_name || user.email}</span>
          )}
        </div>
      </header>

      <div className={`layout ${railCollapsed ? 'layout--collapsed' : ''} ${hideRail ? 'layout--no-rail' : ''}`}>
        {!hideRail && (
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
                to="/chat"
                className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
                title="Chat"
              >
                {railCollapsed ? '\uD83D\uDCAC' : 'Chat'}
              </NavLink>
              <NavLink
                to="/files"
                className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
                title="Arquivos"
              >
                {railCollapsed ? '\uD83D\uDCC1' : 'Arquivos'}
              </NavLink>
              <NavLink
                to="/memories"
                className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
                title="Memorias"
              >
                {railCollapsed ? '\uD83E\uDDE0' : 'Memorias'}
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

            {!railCollapsed && isAuthenticated && (
              <div className="rail-card">
                <button type="button" className="ghost-btn" onClick={handleLogout}>
                  Encerrar sessão
                </button>
              </div>
            )}
          </aside>
        )}

        <main className="panel">
          <div className="panel-inner">
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
              <Route path="/verify-email" element={<VerifyEmailPage />} />
              <Route path="/forgot-password" element={<ForgotPasswordPage />} />
              <Route path="/reset-password" element={<ResetPasswordPage />} />
              <Route
                path="/chat"
                element={
                  <ProtectedRoute>
                    <ChatPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/files"
                element={
                  <ProtectedRoute>
                    <FilesPage />
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
                path="/memories"
                element={
                  <ProtectedRoute>
                    <MemoriesPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/billing/success"
                element={
                  <ProtectedRoute>
                    <section className="view">
                      <div className="view-head" style={{ textAlign: 'center' }}>
                        <p className="eyebrow">Billing</p>
                        <h2 className="view-title">Assinatura confirmada!</h2>
                        <p className="view-subtitle">
                          Seu pagamento foi processado com sucesso. Sua assinatura esta ativa.
                        </p>
                      </div>
                      <div className="button-row" style={{ justifyContent: 'center' }}>
                        <button
                          type="button"
                          className="btn btn-primary"
                          onClick={() => navigate('/me')}
                        >
                          Ver meu perfil
                        </button>
                        <button
                          type="button"
                          className="btn btn-outline"
                          onClick={() => navigate('/chat')}
                        >
                          Ir para o chat
                        </button>
                      </div>
                    </section>
                  </ProtectedRoute>
                }
              />
              <Route
                path="*"
                element={<Navigate to="/home" replace />}
              />
            </Routes>
          </div>
        </main>
      </div>
    </div>
  );
}

export default App;
