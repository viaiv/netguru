/**
 * AdminLayout — sidebar + content area for admin routes.
 */
import { Route, Routes } from 'react-router-dom';

import AdminSidebar from './AdminSidebar';
import Breadcrumb from './Breadcrumb';
import AdminDashboardPage from '../../pages/admin/AdminDashboardPage';
import AdminUsersPage from '../../pages/admin/AdminUsersPage';
import AdminUserDetailPage from '../../pages/admin/AdminUserDetailPage';
import AdminPlansPage from '../../pages/admin/AdminPlansPage';
import AdminAuditLogPage from '../../pages/admin/AdminAuditLogPage';
import AdminHealthPage from '../../pages/admin/AdminHealthPage';

function AdminLayout() {
  return (
    <div className="admin-layout">
      <AdminSidebar />
      <div className="admin-content">
        <Breadcrumb />
        <div className="admin-content__body">
          <Routes>
            <Route index element={<AdminDashboardPage />} />
            <Route path="users" element={<AdminUsersPage />} />
            <Route path="users/:userId" element={<AdminUserDetailPage />} />
            <Route path="plans" element={<AdminPlansPage />} />
            <Route path="audit-log" element={<AdminAuditLogPage />} />
            <Route path="health" element={<AdminHealthPage />} />
          </Routes>
        </div>
      </div>
    </div>
  );
}

export default AdminLayout;
