/**
 * Breadcrumb — auto-generates breadcrumb from pathname.
 */
import { Link, useLocation } from 'react-router-dom';

const SEGMENT_LABELS: Record<string, string> = {
  admin: 'Admin',
  users: 'Usuarios',
  plans: 'Planos',
  'audit-log': 'Audit Log',
  health: 'System Health',
  'system-memories': 'Memorias Sistema',
};

function Breadcrumb() {
  const { pathname } = useLocation();
  const segments = pathname.split('/').filter(Boolean);

  const crumbs = segments.map((seg, i) => {
    const path = '/' + segments.slice(0, i + 1).join('/');
    const label = SEGMENT_LABELS[seg] || seg;
    const isLast = i === segments.length - 1;
    return { path, label, isLast };
  });

  return (
    <nav className="breadcrumb">
      {crumbs.map((c, i) => (
        <span key={c.path} className="breadcrumb__item">
          {i > 0 && <span className="breadcrumb__sep">/</span>}
          {c.isLast ? (
            <span className="breadcrumb__current">{c.label}</span>
          ) : (
            <Link to={c.path} className="breadcrumb__link">
              {c.label}
            </Link>
          )}
        </span>
      ))}
    </nav>
  );
}

export default Breadcrumb;
