/**
 * AdminSidebar — navigation links for admin area.
 */
import { NavLink } from 'react-router-dom';

function AdminSidebar() {
  const links = [
    { to: '/admin', label: 'Dashboard', exact: true },
    { to: '/admin/users', label: 'Usuarios' },
    { to: '/admin/plans', label: 'Planos' },
    { to: '/admin/audit-log', label: 'Audit Log' },
    { to: '/admin/health', label: 'System Health' },
  ];

  return (
    <aside className="admin-sidebar">
      <div className="admin-sidebar__header">
        <h2 className="admin-sidebar__title">Admin</h2>
      </div>
      <nav className="admin-sidebar__nav">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.exact}
            className={({ isActive }) =>
              `admin-sidebar__link ${isActive ? 'admin-sidebar__link--active' : ''}`
            }
          >
            {link.label}
          </NavLink>
        ))}
      </nav>
      <div className="admin-sidebar__footer">
        <NavLink to="/chat" className="admin-sidebar__back">
          Voltar ao App
        </NavLink>
      </div>
    </aside>
  );
}

export default AdminSidebar;
