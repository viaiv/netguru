/**
 * AdminSidebar — navigation links for admin area.
 */
import { NavLink } from 'react-router-dom';

interface AdminSidebarProps {
  isOpen?: boolean;
  onNavigate?: () => void;
}

function AdminSidebar({ isOpen, onNavigate }: AdminSidebarProps) {
  const links = [
    { to: '/admin', label: 'Dashboard', exact: true },
    { to: '/admin/users', label: 'Usuarios' },
    { to: '/admin/plans', label: 'Planos' },
    { to: '/admin/audit-log', label: 'Audit Log' },
    { to: '/admin/health', label: 'System Health' },
    { to: '/admin/email-logs', label: 'Email Logs' },
    { to: '/admin/email-templates', label: 'Email Templates' },
    { to: '/admin/stripe-events', label: 'Stripe Events' },
    { to: '/admin/system-memories', label: 'Memorias Sistema' },
    { to: '/admin/settings', label: 'Configuracoes' },
  ];

  return (
    <aside className={`admin-sidebar ${isOpen ? 'admin-sidebar--open' : ''}`}>
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
            onClick={onNavigate}
          >
            {link.label}
          </NavLink>
        ))}
      </nav>
      <div className="admin-sidebar__footer">
        <NavLink to="/chat" className="admin-sidebar__back" onClick={onNavigate}>
          Voltar ao App
        </NavLink>
      </div>
    </aside>
  );
}

export default AdminSidebar;
