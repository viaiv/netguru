/**
 * AdminHealthPage — system health status + Celery task event log.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';

import HealthStatusCard from '../../components/admin/HealthStatusCard';
import {
  fetchCeleryTasks,
  type ICeleryTaskEvent,
  type IPaginationMeta,
} from '../../services/adminApi';
import { useAdminStore } from '../../stores/adminStore';

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

/** Extract short task name from full dotted path. */
function shortTaskName(fullName: string): string {
  const parts = fullName.split('.');
  return parts[parts.length - 1];
}

/** Format duration in ms to human-readable string. */
function formatDuration(ms: number | null): string {
  if (ms == null) return '-';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/** Map task status to CSS badge modifier class. */
function statusBadgeClass(status: string): string {
  switch (status) {
    case 'SUCCESS':
      return 'celery-badge--success';
    case 'FAILURE':
      return 'celery-badge--failure';
    case 'STARTED':
      return 'celery-badge--started';
    case 'RETRY':
      return 'celery-badge--started';
    default:
      return '';
  }
}

/** Format a UTC datetime string for display. */
function formatDatetime(iso: string | null): string {
  if (!iso) return '-';
  return new Date(iso).toLocaleString();
}

const AUTO_REFRESH_MS = 10_000;

function CeleryTaskDetail({ event }: { event: ICeleryTaskEvent }) {
  return (
    <tr className="celery-detail-row">
      <td colSpan={5}>
        <div className="celery-detail">
          <dl className="celery-detail__grid">
            <dt>Task ID</dt>
            <dd className="celery-detail__mono">{event.task_id}</dd>

            <dt>Nome completo</dt>
            <dd className="celery-detail__mono">{event.task_name}</dd>

            <dt>Worker</dt>
            <dd>{event.worker ?? '-'}</dd>

            <dt>Inicio</dt>
            <dd>{formatDatetime(event.started_at)}</dd>

            <dt>Fim</dt>
            <dd>{formatDatetime(event.finished_at)}</dd>

            <dt>Duracao</dt>
            <dd>{formatDuration(event.duration_ms)}</dd>

            <dt>Argumentos</dt>
            <dd className="celery-detail__pre">{event.args_summary ?? '-'}</dd>

            <dt>Resultado</dt>
            <dd className="celery-detail__pre">{event.result_summary ?? '-'}</dd>

            {event.error && (
              <>
                <dt>Erro</dt>
                <dd className="celery-detail__pre celery-detail__error">{event.error}</dd>
              </>
            )}
          </dl>
        </div>
      </td>
    </tr>
  );
}

function CeleryTaskLog() {
  const [events, setEvents] = useState<ICeleryTaskEvent[]>([]);
  const [pagination, setPagination] = useState<IPaginationMeta | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async (p: number) => {
    setLoading(true);
    try {
      const data = await fetchCeleryTasks({ page: p, limit: 15 });
      setEvents(data.items);
      setPagination(data.pagination);
    } catch {
      // silently ignore — health page is best-effort
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(page);
  }, [load, page]);

  // Auto-refresh every 10s
  useEffect(() => {
    intervalRef.current = setInterval(() => {
      load(page);
    }, AUTO_REFRESH_MS);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [load, page]);

  return (
    <div className="celery-task-log">
      <h3 className="admin-section-title">
        Celery Task Log
        {loading && <span className="celery-task-log__spinner" />}
      </h3>

      <div className="admin-table-wrapper">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Task</th>
              <th>Status</th>
              <th>Inicio</th>
              <th>Duracao</th>
              <th>Resultado</th>
            </tr>
          </thead>
          <tbody>
            {events.length === 0 && (
              <tr>
                <td colSpan={5} className="admin-table__empty">
                  Nenhum evento registrado.
                </td>
              </tr>
            )}
            {events.map((ev) => (
              <React.Fragment key={ev.id}>
                <tr
                  className={`celery-task-row${expandedId === ev.id ? ' celery-task-row--active' : ''}`}
                  onClick={() => setExpandedId(expandedId === ev.id ? null : ev.id)}
                >
                  <td title={ev.task_name}>{shortTaskName(ev.task_name)}</td>
                  <td>
                    <span className={`celery-badge ${statusBadgeClass(ev.status)}`}>
                      {ev.status}
                    </span>
                  </td>
                  <td>{new Date(ev.started_at).toLocaleString()}</td>
                  <td>{formatDuration(ev.duration_ms)}</td>
                  <td className="celery-task-log__result">
                    {ev.status === 'FAILURE'
                      ? (ev.error ?? 'Erro desconhecido').slice(0, 120)
                      : (ev.result_summary ?? '-').slice(0, 120)}
                  </td>
                </tr>
                {expandedId === ev.id && <CeleryTaskDetail event={ev} />}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {pagination && pagination.pages > 1 && (
        <div className="celery-task-log__pagination">
          <button
            type="button"
            className="btn btn--secondary btn--sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            Anterior
          </button>
          <span className="celery-task-log__page-info">
            Pagina {pagination.page} de {pagination.pages}
          </span>
          <button
            type="button"
            className="btn btn--secondary btn--sm"
            disabled={page >= pagination.pages}
            onClick={() => setPage((p) => p + 1)}
          >
            Proxima
          </button>
        </div>
      )}
    </div>
  );
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

      <CeleryTaskLog />
    </div>
  );
}

export default AdminHealthPage;
