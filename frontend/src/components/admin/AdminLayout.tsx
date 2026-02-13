/**
 * AdminLayout — sidebar + content area for admin routes.
 */
import { useState } from 'react';
import { Route, Routes } from 'react-router-dom';

import { useMobile } from '../../hooks/useMediaQuery';
import AdminSidebar from './AdminSidebar';
import Breadcrumb from './Breadcrumb';
import AdminDashboardPage from '../../pages/admin/AdminDashboardPage';
import AdminUsersPage from '../../pages/admin/AdminUsersPage';
import AdminUserDetailPage from '../../pages/admin/AdminUserDetailPage';
import AdminPlansPage from '../../pages/admin/AdminPlansPage';
import AdminAuditLogPage from '../../pages/admin/AdminAuditLogPage';
import AdminHealthPage from '../../pages/admin/AdminHealthPage';
import AdminEmailLogsPage from '../../pages/admin/AdminEmailLogsPage';
import AdminSettingsPage from '../../pages/admin/AdminSettingsPage';

function AdminLayout() {
  const isMobile = useMobile();
  const [showSidebar, setShowSidebar] = useState(false);

  function handleNavigate(): void {
    if (isMobile) setShowSidebar(false);
  }

  return (
    <div className="admin-layout">
      {/* Mobile drawer overlay */}
      {isMobile && showSidebar && (
        <div className="admin-drawer-overlay" onClick={() => setShowSidebar(false)} />
      )}

      <AdminSidebar isOpen={!isMobile || showSidebar} onNavigate={handleNavigate} />

      <div className="admin-content">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button
            type="button"
            className="admin-drawer-toggle"
            onClick={() => setShowSidebar((v) => !v)}
            aria-label="Menu"
          >
            &#9776;
          </button>
          <Breadcrumb />
        </div>
        <div className="admin-content__body">
          <Routes>
            <Route index element={<AdminDashboardPage />} />
            <Route path="users" element={<AdminUsersPage />} />
            <Route path="users/:userId" element={<AdminUserDetailPage />} />
            <Route path="plans" element={<AdminPlansPage />} />
            <Route path="audit-log" element={<AdminAuditLogPage />} />
            <Route path="health" element={<AdminHealthPage />} />
            <Route path="email-logs" element={<AdminEmailLogsPage />} />
            <Route path="settings" element={<AdminSettingsPage />} />
          </Routes>
        </div>
      </div>
    </div>
  );
}

export default AdminLayout;
