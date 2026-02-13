/**
 * AdminHealthPage — system health status.
 */
import { useEffect } from 'react';

import HealthStatusCard from '../../components/admin/HealthStatusCard';
import { useAdminStore } from '../../stores/adminStore';

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

function AdminHealthPage() {
  const health = useAdminStore((s) => s.health);
  const loading = useAdminStore((s) => s.healthLoading);
  const loadHealth = useAdminStore((s) => s.loadHealth);

  useEffect(() => {
    loadHealth();
  }, [loadHealth]);

  if (loading && !health) {
    return <p className="admin-loading">Verificando saude do sistema...</p>;
  }

  if (!health) {
    return <p className="admin-empty">Erro ao verificar saude do sistema.</p>;
  }

  return (
    <div className="admin-health">
      <h2 className="admin-page-title">System Health</h2>

      <div className="health-overview kv-card">
        <div className="health-overview__status">
          <span className={`health-card__dot health-card__dot--${health.overall}`} />
          <span className="health-overview__label">
            Status geral: <strong>{health.overall}</strong>
          </span>
        </div>
        {health.uptime_seconds != null && (
          <p className="health-overview__uptime">
            Uptime: {formatUptime(health.uptime_seconds)}
          </p>
        )}
      </div>

      <div className="health-grid">
        {health.services.map((svc) => (
          <HealthStatusCard key={svc.name} service={svc} />
        ))}
      </div>

      <button type="button" className="btn btn--secondary" onClick={loadHealth}>
        Verificar novamente
      </button>
    </div>
  );
}

export default AdminHealthPage;
