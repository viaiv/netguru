/**
 * AdminDashboardPage — overview statistics.
 */
import { useEffect, useState } from 'react';

import StatCard from '../../components/admin/StatCard';
import { getErrorMessage } from '../../services/api';
import {
  exportByoLlmUsageCsv,
  fetchByoLlmUsageReport,
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

      <div className="admin-section">
        <h3 className="admin-section__title">Uso BYO-LLM</h3>

        <div className="admin-filters">
          <label>
            Inicio
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </label>
          <label>
            Fim
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </label>
          <label>
            Provider
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
          </label>
          <button type="button" className="btn btn-primary" onClick={() => void loadUsageReport()}>
            Aplicar
          </button>
          <button
            type="button"
            className="ghost-btn"
            onClick={() => void handleExportCsv()}
            disabled={!usageReport || usageLoading}
          >
            Exportar CSV
          </button>
          <button
            type="button"
            className="ghost-btn"
            onClick={handleExportJson}
            disabled={!usageReport || usageLoading}
          >
            Exportar JSON
          </button>
        </div>

        {usageError ? <p className="admin-empty">{usageError}</p> : null}
        {usageLoading && !usageReport ? <p className="admin-loading">Carregando uso BYO-LLM...</p> : null}

        {usageReport && (
          <>
            <div className="stat-grid stat-grid--small">
              <StatCard label="Mensagens" value={usageReport.totals.messages} />
              <StatCard label="Tokens" value={usageReport.totals.tokens.toLocaleString()} />
              <StatCard label="Latencia p50 (ms)" value={usageReport.totals.latency_p50_ms.toFixed(1)} />
              <StatCard label="Latencia p95 (ms)" value={usageReport.totals.latency_p95_ms.toFixed(1)} />
              <StatCard label="Erro (%)" value={`${usageReport.totals.error_rate_pct.toFixed(2)}%`} />
            </div>

            {usageReport.alerts.length > 0 && (
              <div className="button-row">
                {usageReport.alerts.map((alert) => (
                  <span key={`${alert.code}-${alert.message}`} className="chip chip-muted">
                    {alert.severity.toUpperCase()}: {alert.message}
                  </span>
                ))}
              </div>
            )}

            <div className="data-table__wrapper">
              <table className="data-table__table">
                <thead>
                  <tr>
                    <th>Provider</th>
                    <th>Modelo</th>
                    <th>Mensagens</th>
                    <th>Tokens</th>
                    <th>Latencia media (ms)</th>
                    <th>Erro (%)</th>
                  </tr>
                </thead>
                <tbody>
                  {usageReport.by_provider_model.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="data-table__empty">Sem dados no periodo.</td>
                    </tr>
                  ) : (
                    usageReport.by_provider_model.map((row) => (
                      <tr key={`${row.provider}-${row.model}`}>
                        <td>{row.provider}</td>
                        <td>{row.model}</td>
                        <td>{row.messages}</td>
                        <td>{row.tokens.toLocaleString()}</td>
                        <td>{row.avg_latency_ms.toFixed(1)}</td>
                        <td>{row.error_rate_pct.toFixed(2)}%</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <div className="data-table__wrapper">
              <table className="data-table__table">
                <thead>
                  <tr>
                    <th>Tool</th>
                    <th>Chamadas</th>
                    <th>Falhas</th>
                    <th>Duracao media (ms)</th>
                    <th>Erro (%)</th>
                  </tr>
                </thead>
                <tbody>
                  {usageReport.by_tool.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="data-table__empty">Sem chamadas de tool no periodo.</td>
                    </tr>
                  ) : (
                    usageReport.by_tool.map((row) => (
                      <tr key={row.tool}>
                        <td>{row.tool}</td>
                        <td>{row.calls}</td>
                        <td>{row.failed_calls}</td>
                        <td>{row.avg_duration_ms.toFixed(1)}</td>
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
    </div>
  );
}

export default AdminDashboardPage;
