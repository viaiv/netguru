import { useEffect, useRef, useState } from 'react';
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
import ChatSidebar from './components/sidebar/ChatSidebar';
import FilesSidebar from './components/sidebar/FilesSidebar';
import MemoriesSidebar from './components/sidebar/MemoriesSidebar';
import ProfileSidebar from './components/sidebar/ProfileSidebar';
import GenericSidebar from './components/sidebar/GenericSidebar';
import { useSidebarCollapsed } from './hooks/useMediaQuery';
import { AUTH_LOGOUT_EVENT, dispatchAuthLogout, type IAuthLogoutEventDetail } from './services/authEvents';
import { useAuthStore } from './stores/authStore';
import { useChatStore } from './stores/chatStore';

/* ------------------------------------------------------------------ */
/*  Auth route paths — rendered inside layout > panel > panel-inner   */
/* ------------------------------------------------------------------ */
const AUTH_PATHS = ['/login', '/register', '/verify-email', '/forgot-password', '/reset-password'];

function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const user = useAuthStore((state) => state.user);
  const isAdmin = user?.role === 'owner' || user?.role === 'admin';
  const clearAuth = useAuthStore((state) => state.clearAuth);

  const isAdminRoute = location.pathname.startsWith('/admin');
  const isMobile = useSidebarCollapsed();
  const isChatRoute = location.pathname === '/chat';

  const createConversation = useChatStore((state) => state.createConversation);
  const selectConversation = useChatStore((state) => state.selectConversation);

  // ---- Sidebar drawer (mobile) ----
  const [showSidebar, setShowSidebar] = useState(false);

  // ---- Nav menu (dropdown) ----
  const [navMenuOpen, setNavMenuOpen] = useState(false);
  const navMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!navMenuOpen) return;
    function handleClick(e: MouseEvent): void {
      if (navMenuRef.current && !navMenuRef.current.contains(e.target as Node)) {
        setNavMenuOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [navMenuOpen]);

  // ---- Close drawer on route change ----
  useEffect(() => {
    setShowSidebar(false);
    setNavMenuOpen(false);
  }, [location.pathname]);

  // ---- Auth logout event ----
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
  const isAuthRoute = AUTH_PATHS.includes(location.pathname);

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

  // Auth pages (login, register, etc.) — layout antigo sem aside
  if (isAuthRoute && !isAuthenticated) {
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

          <div className="chrome-right">
            <div className="status-strip">
              <span className="status-dot offline" />
              <span>Desconectado</span>
            </div>
          </div>
        </header>

        <div className="layout layout--no-rail">
          <main className="panel">
            <div className="panel-inner">
              <Routes>
                <Route path="/login" element={<LoginPage />} />
                <Route path="/register" element={<RegisterPage />} />
                <Route path="/verify-email" element={<VerifyEmailPage />} />
                <Route path="/forgot-password" element={<ForgotPasswordPage />} />
                <Route path="/reset-password" element={<ResetPasswordPage />} />
                <Route path="*" element={<Navigate to="/home" replace />} />
              </Routes>
            </div>
          </main>
        </div>
      </div>
    );
  }

  // ---- Authenticated pages — universal aside + main layout ----
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

        <div className="chrome-right">
          <div className="status-strip">
            <span className={isAuthenticated ? 'status-dot online' : 'status-dot offline'} />
            <span>{isAuthenticated ? 'Conectado' : 'Desconectado'}</span>
            {isAuthenticated && user && (
              <span className="chip chip-live">{user.full_name || user.email}</span>
            )}
          </div>
        </div>
      </header>

      <div className="app-body">
        {/* Mobile drawer overlay */}
        {isMobile && showSidebar && (
          <div className="chat-drawer-overlay" onClick={() => setShowSidebar(false)} />
        )}

        <aside className={`chat-panel ${isMobile && showSidebar ? 'chat-panel--open' : ''}`}>
          {/* Conteudo contextual baseado na rota */}
          <Routes>
            <Route path="/chat" element={<ChatSidebar onSelectConversation={() => { if (isMobile) setShowSidebar(false); }} />} />
            <Route path="/files" element={<FilesSidebar />} />
            <Route path="/memories" element={<MemoriesSidebar />} />
            <Route path="/me" element={<ProfileSidebar />} />
            <Route path="/billing/success" element={<GenericSidebar title="Billing" subtitle="Assinatura confirmada" />} />
            <Route path="*" element={<GenericSidebar title="NetGuru" subtitle="Agentic Network Console" />} />
          </Routes>

          {/* Bottom nav compartilhado */}
          <div className="panel-bottom-nav">
            {isChatRoute && (
              <button
                type="button"
                className="panel-nav-icon"
                title="Nova conversa"
                onClick={async () => {
                  const conv = await createConversation();
                  if (conv) selectConversation(conv.id);
                }}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              </button>
            )}
            <div className="panel-nav-menu" ref={navMenuRef}>
              <button type="button" className="panel-nav-icon" title="Menu" onClick={() => setNavMenuOpen((v) => !v)}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
              </button>
              {navMenuOpen && (
                <nav className="panel-dropdown">
                  <NavLink to="/chat" className={({ isActive }) => `panel-dropdown-link ${isActive ? 'panel-dropdown-link--active' : ''}`} onClick={() => setNavMenuOpen(false)}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                    Chat
                  </NavLink>
                  <NavLink to="/files" className={({ isActive }) => `panel-dropdown-link ${isActive ? 'panel-dropdown-link--active' : ''}`} onClick={() => setNavMenuOpen(false)}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
                    Arquivos
                  </NavLink>
                  <NavLink to="/memories" className={({ isActive }) => `panel-dropdown-link ${isActive ? 'panel-dropdown-link--active' : ''}`} onClick={() => setNavMenuOpen(false)}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
                    Memorias
                  </NavLink>
                  <NavLink to="/me" className={({ isActive }) => `panel-dropdown-link ${isActive ? 'panel-dropdown-link--active' : ''}`} onClick={() => setNavMenuOpen(false)}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                    Perfil
                  </NavLink>
                  {isAdmin && (
                    <NavLink to="/admin" className={({ isActive }) => `panel-dropdown-link ${isActive ? 'panel-dropdown-link--active' : ''}`} onClick={() => setNavMenuOpen(false)}>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
                      Admin
                    </NavLink>
                  )}
                  <div className="panel-dropdown-sep" />
                  <button type="button" className="panel-dropdown-link panel-dropdown-link--danger" onClick={() => { setNavMenuOpen(false); dispatchAuthLogout('manual'); }}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
                    Encerrar sessao
                  </button>
                </nav>
              )}
            </div>
          </div>
        </aside>

        <section className="chat-main">
          {/* Mobile topbar with hamburger */}
          {isMobile && (
            <div className="mobile-topbar">
              <button
                type="button"
                className="chat-drawer-toggle"
                onClick={() => setShowSidebar((v) => !v)}
                aria-label="Menu"
              >
                &#9776;
              </button>
            </div>
          )}

          <Routes>
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
        </section>
      </div>
    </div>
  );
}

export default App;
