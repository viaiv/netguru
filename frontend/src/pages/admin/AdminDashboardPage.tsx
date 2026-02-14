/**
 * AdminDashboardPage — overview statistics + BYO-LLM usage report.
 */
import { useEffect, useState } from 'react';

import { getErrorMessage } from '../../services/api';
import {
  exportByoLlmUsageCsv,
  fetchByoLlmUsageReport,
  type IByoLlmAlert,
  type IByoLlmUsageReport,
} from '../../services/adminApi';
import { useAdminStore } from '../../stores/adminStore';

function isoToday(): string {
  return new Date().toISOString().slice(0, 10);
}

function isoDaysAgo(days: number): string {
  const now = new Date();
  now.setDate(now.getDate() - days);
  return now.toISOString().slice(0, 10);
}

// ---------------------------------------------------------------------------
// Alert badge
// ---------------------------------------------------------------------------

function AlertBadge({ alert }: { alert: IByoLlmAlert }) {
  const cls =
    alert.severity === 'critical'
      ? 'admin-alert-badge--critical'
      : alert.severity === 'warning'
        ? 'admin-alert-badge--warning'
        : 'admin-alert-badge--info';

  return (
    <span className={`admin-alert-badge ${cls}`}>
      {alert.severity.toUpperCase()}: {alert.message}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function AdminDashboardPage() {
  const stats = useAdminStore((s) => s.stats);
  const loading = useAdminStore((s) => s.statsLoading);
  const loadStats = useAdminStore((s) => s.loadStats);
  const [usageReport, setUsageReport] = useState<IByoLlmUsageReport | null>(null);
  const [usageLoading, setUsageLoading] = useState(false);
  const [usageError, setUsageError] = useState<string | null>(null);
  const [startDate, setStartDate] = useState(isoDaysAgo(6));
  const [endDate, setEndDate] = useState(isoToday());
  const [providerFilter, setProviderFilter] = useState('');

  async function loadUsageReport(): Promise<void> {
    setUsageLoading(true);
    setUsageError(null);
    try {
      const report = await fetchByoLlmUsageReport({
        start_date: startDate,
        end_date: endDate,
        provider: providerFilter || undefined,
      });
      setUsageReport(report);
    } catch (error) {
      setUsageError(getErrorMessage(error));
    } finally {
      setUsageLoading(false);
    }
  }

  async function handleExportCsv(): Promise<void> {
    try {
      const blob = await exportByoLlmUsageCsv({
        start_date: startDate,
        end_date: endDate,
        provider: providerFilter || undefined,
      });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `byollm-usage-${startDate}-${endDate}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      setUsageError(getErrorMessage(error));
    }
  }

  function handleExportJson(): void {
    if (!usageReport) return;
    const blob = new Blob([JSON.stringify(usageReport, null, 2)], {
      type: 'application/json',
    });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `byollm-usage-${startDate}-${endDate}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  }

  function handleReload() {
    loadStats();
    void loadUsageReport();
  }

  useEffect(() => {
    loadStats();
    void loadUsageReport();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadStats]);

  if (loading && !stats) {
    return <p className="admin-loading">Carregando dashboard...</p>;
  }

  if (!stats) {
    return <p className="admin-empty">Erro ao carregar estatisticas.</p>;
  }

  return (
    <section className="admin-page">
      {/* Header */}
      <div className="admin-page-header">
        <h2 className="admin-page-title">Dashboard</h2>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={handleReload}
          disabled={loading || usageLoading}
        >
          Recarregar
        </button>
      </div>

      {/* Core metrics — 4 columns */}
      <div className="admin-cards-grid admin-cards-grid--4">
        <div className="admin-stat-card">
          <span className="admin-stat-card__label">Total Usuarios</span>
          <span className="admin-stat-card__value">{stats.total_users}</span>
        </div>
        <div className="admin-stat-card">
          <span className="admin-stat-card__label">Usuarios Ativos</span>
          <span className="admin-stat-card__value">{stats.active_users}</span>
        </div>
        <div className="admin-stat-card">
          <span className="admin-stat-card__label">Conversas</span>
          <span className="admin-stat-card__value">{stats.total_conversations}</span>
        </div>
        <div className="admin-stat-card">
          <span className="admin-stat-card__label">Mensagens</span>
          <span className="admin-stat-card__value">{stats.total_messages}</span>
        </div>
      </div>

      {/* Secondary metrics — 3 columns */}
      <div className="admin-cards-grid" style={{ marginTop: 12 }}>
        <div className="admin-stat-card">
          <span className="admin-stat-card__label">Documentos</span>
          <span className="admin-stat-card__value">{stats.total_documents}</span>
        </div>
        <div className="admin-stat-card">
          <span className="admin-stat-card__label">Novos (7d)</span>
          <span className="admin-stat-card__value">{stats.recent_signups_7d}</span>
        </div>
        <div className="admin-stat-card">
          <span className="admin-stat-card__label">Mensagens Hoje</span>
          <span className="admin-stat-card__value">{stats.messages_today}</span>
        </div>
      </div>

      {/* Users by Plan + Role — side by side */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginTop: 28 }}>
        <div>
          <h3 className="admin-section-title">Usuarios por Plano</h3>
          <div className="admin-cards-grid--auto admin-cards-grid">
            {Object.entries(stats.users_by_plan).map(([plan, count]) => (
              <div key={plan} className="admin-stat-card">
                <span className="admin-stat-card__label">{plan}</span>
                <span className="admin-stat-card__value">{count}</span>
              </div>
            ))}
          </div>
        </div>
        <div>
          <h3 className="admin-section-title">Usuarios por Role</h3>
          <div className="admin-cards-grid--auto admin-cards-grid">
            {Object.entries(stats.users_by_role).map(([role, count]) => (
              <div key={role} className="admin-stat-card">
                <span className="admin-stat-card__label">{role}</span>
                <span className="admin-stat-card__value">{count}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* BYO-LLM Usage */}
      <div style={{ marginTop: 32 }}>
        <h3 className="admin-section-title">Uso BYO-LLM</h3>

        {/* Filter bar */}
        <div className="admin-filter-bar">
          <div className="admin-filter-bar__field">
            <span className="admin-filter-bar__label">Inicio</span>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </div>
          <div className="admin-filter-bar__field">
            <span className="admin-filter-bar__label">Fim</span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </div>
          <div className="admin-filter-bar__field">
            <span className="admin-filter-bar__label">Provider</span>
            <select
              value={providerFilter}
              onChange={(e) => setProviderFilter(e.target.value)}
            >
              <option value="">Todos</option>
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic</option>
              <option value="azure">Azure</option>
              <option value="google">Google</option>
              <option value="groq">Groq</option>
              <option value="deepseek">DeepSeek</option>
              <option value="openrouter">OpenRouter</option>
              <option value="unknown">Unknown</option>
            </select>
          </div>
          <div className="admin-filter-bar__field">
            <span className="admin-filter-bar__label">&nbsp;</span>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => void loadUsageReport()}
            >
              Aplicar
            </button>
          </div>
          <div className="admin-filter-bar__actions">
            <button
              type="button"
              className="btn btn-secondary btn--sm"
              onClick={() => void handleExportCsv()}
              disabled={!usageReport || usageLoading}
            >
              CSV
            </button>
            <button
              type="button"
              className="btn btn-secondary btn--sm"
              onClick={handleExportJson}
              disabled={!usageReport || usageLoading}
            >
              JSON
            </button>
          </div>
        </div>

        {usageError && <div className="admin-error">{usageError}</div>}
        {usageLoading && !usageReport && (
          <p className="admin-loading">Carregando uso BYO-LLM...</p>
        )}

        {usageReport && (
          <>
            {/* Totals — 5 columns */}
            <div className="admin-cards-grid admin-cards-grid--5">
              <div className="admin-stat-card">
                <span className="admin-stat-card__label">Mensagens</span>
                <span className="admin-stat-card__value">{usageReport.totals.messages}</span>
              </div>
              <div className="admin-stat-card">
                <span className="admin-stat-card__label">Tokens</span>
                <span className="admin-stat-card__value">
                  {usageReport.totals.tokens.toLocaleString()}
                </span>
              </div>
              <div className="admin-stat-card">
                <span className="admin-stat-card__label">Latencia p50</span>
                <span className="admin-stat-card__value">
                  {usageReport.totals.latency_p50_ms.toFixed(0)}
                  <span style={{ fontSize: '0.7rem', fontWeight: 400, marginLeft: 2 }}>ms</span>
                </span>
              </div>
              <div className="admin-stat-card">
                <span className="admin-stat-card__label">Latencia p95</span>
                <span className="admin-stat-card__value">
                  {usageReport.totals.latency_p95_ms.toFixed(0)}
                  <span style={{ fontSize: '0.7rem', fontWeight: 400, marginLeft: 2 }}>ms</span>
                </span>
              </div>
              <div className="admin-stat-card">
                <span className="admin-stat-card__label">Taxa de Erro</span>
                <span className="admin-stat-card__value">
                  {usageReport.totals.error_rate_pct.toFixed(1)}%
                </span>
              </div>
            </div>

            {/* Alerts */}
            {usageReport.alerts.length > 0 && (
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 12 }}>
                {usageReport.alerts.map((alert) => (
                  <AlertBadge key={`${alert.code}-${alert.message}`} alert={alert} />
                ))}
              </div>
            )}

            {/* Provider/Model table */}
            <h4 className="admin-section-title" style={{ marginTop: 20 }}>
              Por Provider / Modelo
            </h4>
            <div className="admin-table-wrapper">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Provider</th>
                    <th>Modelo</th>
                    <th>Mensagens</th>
                    <th>Tokens</th>
                    <th>Latencia media</th>
                    <th>Erro</th>
                  </tr>
                </thead>
                <tbody>
                  {usageReport.by_provider_model.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="admin-table__empty">
                        Sem dados no periodo.
                      </td>
                    </tr>
                  ) : (
                    usageReport.by_provider_model.map((row) => (
                      <tr key={`${row.provider}-${row.model}`}>
                        <td>{row.provider}</td>
                        <td>{row.model}</td>
                        <td>{row.messages}</td>
                        <td>{row.tokens.toLocaleString()}</td>
                        <td>{row.avg_latency_ms.toFixed(0)} ms</td>
                        <td>{row.error_rate_pct.toFixed(2)}%</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {/* Tools table */}
            <h4 className="admin-section-title" style={{ marginTop: 20 }}>
              Por Tool
            </h4>
            <div className="admin-table-wrapper">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Tool</th>
                    <th>Chamadas</th>
                    <th>Falhas</th>
                    <th>Duracao media</th>
                    <th>Erro</th>
                  </tr>
                </thead>
                <tbody>
                  {usageReport.by_tool.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="admin-table__empty">
                        Sem chamadas de tool no periodo.
                      </td>
                    </tr>
                  ) : (
                    usageReport.by_tool.map((row) => (
                      <tr key={row.tool}>
                        <td>{row.tool}</td>
                        <td>{row.calls}</td>
                        <td>{row.failed_calls}</td>
                        <td>{row.avg_duration_ms.toFixed(0)} ms</td>
                        <td>{row.error_rate_pct.toFixed(2)}%</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </section>
  );
}

export default AdminDashboardPage;
