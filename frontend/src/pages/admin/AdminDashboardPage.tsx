/**
 * AdminDashboardPage — overview statistics.
 */
import { useEffect } from 'react';

import StatCard from '../../components/admin/StatCard';
import { useAdminStore } from '../../stores/adminStore';

function AdminDashboardPage() {
  const stats = useAdminStore((s) => s.stats);
  const loading = useAdminStore((s) => s.statsLoading);
  const loadStats = useAdminStore((s) => s.loadStats);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  if (loading && !stats) {
    return <p className="admin-loading">Carregando dashboard...</p>;
  }

  if (!stats) {
    return <p className="admin-empty">Erro ao carregar estatisticas.</p>;
  }

  return (
    <div className="admin-dashboard">
      <h2 className="admin-page-title">Dashboard</h2>

      <div className="stat-grid">
        <StatCard label="Total Usuarios" value={stats.total_users} />
        <StatCard label="Usuarios Ativos" value={stats.active_users} />
        <StatCard label="Conversas" value={stats.total_conversations} />
        <StatCard label="Mensagens" value={stats.total_messages} />
        <StatCard label="Documentos" value={stats.total_documents} />
        <StatCard label="Novos (7d)" value={stats.recent_signups_7d} />
        <StatCard label="Mensagens Hoje" value={stats.messages_today} />
      </div>

      <div className="admin-section">
        <h3 className="admin-section__title">Usuarios por Plano</h3>
        <div className="stat-grid stat-grid--small">
          {Object.entries(stats.users_by_plan).map(([plan, count]) => (
            <StatCard key={plan} label={plan} value={count} />
          ))}
        </div>
      </div>

      <div className="admin-section">
        <h3 className="admin-section__title">Usuarios por Role</h3>
        <div className="stat-grid stat-grid--small">
          {Object.entries(stats.users_by_role).map(([role, count]) => (
            <StatCard key={role} label={role} value={count} />
          ))}
        </div>
      </div>
    </div>
  );
}

export default AdminDashboardPage;
