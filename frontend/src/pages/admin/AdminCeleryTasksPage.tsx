/**
 * AdminCeleryTasksPage — trigger scheduled Celery tasks + view execution history.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';

import {
  fetchCeleryTasks,
  triggerCeleryTask,
  type ICeleryTaskEvent,
  type IPaginationMeta,
} from '../../services/adminApi';

// ---------------------------------------------------------------------------
// Scheduled tasks definition
// ---------------------------------------------------------------------------

interface ScheduledTask {
  name: string;
  label: string;
  description: string;
  schedule: string;
}

const SCHEDULED_TASKS: ScheduledTask[] = [
  { name: 'cleanup_orphan_uploads', label: 'Limpeza de Uploads Orfaos', description: 'Remove documentos e uploads pendentes abandonados', schedule: '24h' },
  { name: 'cleanup_expired_tokens', label: 'Limpeza de Tokens Expirados', description: 'Remove refresh tokens expirados do Redis', schedule: '6h' },
  { name: 'service_health_check', label: 'Health Check', description: 'Verifica saude do Redis e banco de dados', schedule: '5min' },
  { name: 'recalculate_stale_embeddings', label: 'Recalcular Embeddings', description: 'Regenera embeddings com modelo desatualizado', schedule: '12h' },
  { name: 'mark_stale_tasks_timeout', label: 'Timeout de Tasks Travadas', description: 'Marca tasks STARTED ha mais de 5 min como TIMEOUT', schedule: '5min' },
  { name: 'downgrade_expired_trials', label: 'Downgrade Trials Expirados', description: 'Rebaixa usuarios com trial expirado para plano free', schedule: '1h' },
  { name: 'reconcile_seat_quantities', label: 'Reconciliar Seats', description: 'Sincroniza quantidade de seats com Stripe', schedule: '6h' },
  { name: 'check_byollm_discount_eligibility', label: 'Verificar Desconto BYO-LLM', description: 'Verifica e revoga descontos BYO-LLM apos grace period', schedule: '6h' },
  { name: 'crawl_brainwork_blog', label: 'Crawler Brainwork', description: 'Ingere posts do brainwork.com.br no RAG Global', schedule: '24h' },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function shortTaskName(fullName: string): string {
  const parts = fullName.split('.');
  return parts[parts.length - 1];
}

function formatDuration(ms: number | null): string {
  if (ms == null) return '-';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function statusBadgeClass(status: string): string {
  switch (status) {
    case 'SUCCESS':
      return 'celery-badge--success';
    case 'FAILURE':
      return 'celery-badge--failure';
    case 'STARTED':
    case 'RETRY':
      return 'celery-badge--started';
    case 'TIMEOUT':
      return 'celery-badge--timeout';
    default:
      return '';
  }
}

function formatDatetime(iso: string | null): string {
  if (!iso) return '-';
  return new Date(iso).toLocaleString();
}

// ---------------------------------------------------------------------------
// TaskCard
// ---------------------------------------------------------------------------

function TaskCard({ task }: { task: ScheduledTask }) {
  const [loading, setLoading] = useState(false);
  const [feedback, setFeedback] = useState<{ ok: boolean; text: string } | null>(null);

  async function handleTrigger() {
    setLoading(true);
    setFeedback(null);
    try {
      const res = await triggerCeleryTask(task.name);
      setFeedback({ ok: true, text: `Disparada! ID: ${res.task_id.slice(0, 8)}...` });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Erro ao disparar task';
      setFeedback({ ok: false, text: msg });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="celery-task-card kv-card">
      <div className="celery-task-card__header">
        <h4 className="celery-task-card__title">{task.label}</h4>
        <span className="celery-task-card__schedule">{task.schedule}</span>
      </div>
      <p className="celery-task-card__desc">{task.description}</p>
      <div className="celery-task-card__actions">
        <button
          type="button"
          className="btn btn--primary btn--sm"
          disabled={loading}
          onClick={handleTrigger}
        >
          {loading ? 'Disparando...' : 'Executar'}
        </button>
        {feedback && (
          <span className={`celery-task-card__feedback ${feedback.ok ? 'celery-task-card__feedback--ok' : 'celery-task-card__feedback--err'}`}>
            {feedback.text}
          </span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// History detail row
// ---------------------------------------------------------------------------

function CeleryTaskDetail({ event }: { event: ICeleryTaskEvent }) {
  return (
    <tr className="celery-detail-row">
      <td colSpan={6}>
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

// ---------------------------------------------------------------------------
// History table
// ---------------------------------------------------------------------------

const AUTO_REFRESH_MS = 10_000;

function CeleryHistory() {
  const [events, setEvents] = useState<ICeleryTaskEvent[]>([]);
  const [pagination, setPagination] = useState<IPaginationMeta | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [nameFilter, setNameFilter] = useState('');
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async (p: number, st: string, name: string) => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { page: p, limit: 20 };
      if (st) params.status = st;
      if (name) params.task_name = name;
      const data = await fetchCeleryTasks(params as Parameters<typeof fetchCeleryTasks>[0]);
      setEvents(data.items);
      setPagination(data.pagination);
    } catch {
      // best-effort
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(page, statusFilter, nameFilter);
  }, [load, page, statusFilter, nameFilter]);

  useEffect(() => {
    intervalRef.current = setInterval(() => {
      load(page, statusFilter, nameFilter);
    }, AUTO_REFRESH_MS);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [load, page, statusFilter, nameFilter]);

  return (
    <div className="celery-task-log">
      <h3 className="admin-section-title">
        Historico de Execucoes
        {loading && <span className="celery-task-log__spinner" />}
      </h3>

      <div className="celery-history-filters">
        <select
          className="form-select form-select--sm"
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
        >
          <option value="">Todos os status</option>
          <option value="SUCCESS">SUCCESS</option>
          <option value="FAILURE">FAILURE</option>
          <option value="STARTED">STARTED</option>
          <option value="TIMEOUT">TIMEOUT</option>
          <option value="RETRY">RETRY</option>
        </select>
        <input
          type="text"
          className="form-input form-input--sm"
          placeholder="Filtrar por nome..."
          value={nameFilter}
          onChange={(e) => { setNameFilter(e.target.value); setPage(1); }}
        />
      </div>

      <div className="admin-table-wrapper">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Task</th>
              <th>Status</th>
              <th>Inicio</th>
              <th>Duracao</th>
              <th>Worker</th>
              <th>Resultado / Erro</th>
            </tr>
          </thead>
          <tbody>
            {events.length === 0 && (
              <tr>
                <td colSpan={6} className="admin-table__empty">
                  Nenhum evento encontrado.
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
                  <td>{formatDatetime(ev.started_at)}</td>
                  <td>{formatDuration(ev.duration_ms)}</td>
                  <td>{ev.worker ?? '-'}</td>
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

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

function AdminCeleryTasksPage() {
  return (
    <section className="admin-page">
      <div className="admin-page-header">
        <h2 className="admin-page-title">Celery Tasks</h2>
      </div>

      <h3 className="admin-section-title">Tasks Agendadas</h3>
      <div className="celery-tasks-grid">
        {SCHEDULED_TASKS.map((t) => (
          <TaskCard key={t.name} task={t} />
        ))}
      </div>

      <CeleryHistory />
    </section>
  );
}

export default AdminCeleryTasksPage;
