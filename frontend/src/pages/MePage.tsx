import { useEffect, useState } from 'react';

import {
  api,
  getErrorMessage,
  type IUserResponse,
} from '../services/api';
import { dispatchAuthLogout } from '../services/authEvents';

const LLM_PROVIDERS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'azure', label: 'Azure OpenAI' },
  { value: 'google', label: 'Google Gemini' },
  { value: 'groq', label: 'Groq' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'openrouter', label: 'OpenRouter' },
] as const;

interface IUserByoLlmTotals {
  messages: number;
  tokens: number;
  latency_p50_ms: number;
  latency_p95_ms: number;
  error_rate_pct: number;
}

interface IUserByoLlmProviderItem {
  provider: string;
  model: string;
  messages: number;
  tokens: number;
  avg_latency_ms: number;
  error_rate_pct: number;
}

interface IUserByoLlmAlert {
  code: string;
  severity: string;
  message: string;
}

interface IUserByoLlmUsageSummary {
  period_days: number;
  provider_filter: string | null;
  totals: IUserByoLlmTotals;
  by_provider_model: IUserByoLlmProviderItem[];
  alerts: IUserByoLlmAlert[];
}

function MePage() {
  const [user, setUser] = useState<IUserResponse | null>(null);
  const [usageSummary, setUsageSummary] = useState<IUserByoLlmUsageSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // LLM config form
  const [llmProvider, setLlmProvider] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [llmSaving, setLlmSaving] = useState(false);
  const [llmSuccess, setLlmSuccess] = useState(false);

  async function loadProfile(): Promise<void> {
    setError(null);
    setIsLoading(true);

    try {
      const [profileResponse, usageResponse] = await Promise.all([
        api.get<IUserResponse>('/users/me'),
        api.get<IUserByoLlmUsageSummary>('/users/me/usage-summary', {
          params: { days: 7 },
        }),
      ]);
      setUser(profileResponse.data);
      setUsageSummary(usageResponse.data);
      setLlmProvider(profileResponse.data.llm_provider || '');
      setApiKey('');
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setIsLoading(false);
    }
  }

  async function saveLlmConfig(): Promise<void> {
    setLlmSaving(true);
    setLlmSuccess(false);
    setError(null);

    try {
      const payload: Record<string, string> = {};
      if (llmProvider) payload.llm_provider = llmProvider;
      if (apiKey) payload.api_key = apiKey;

      if (Object.keys(payload).length === 0) {
        setError('Selecione um provedor e informe sua API key.');
        setLlmSaving(false);
        return;
      }

      const response = await api.patch<IUserResponse>('/users/me', payload);
      setUser(response.data);
      setApiKey('');
      setLlmSuccess(true);
      setTimeout(() => setLlmSuccess(false), 3000);
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setLlmSaving(false);
    }
  }

  function logout(): void {
    dispatchAuthLogout('manual');
  }

  useEffect(() => {
    void loadProfile();
  }, []);

  return (
    <section className="view">
      <div className="view-head">
        <p className="eyebrow">Minha conta</p>
        <h2 className="view-title">Meu perfil</h2>
        <p className="view-subtitle">
          Gerencie suas informacoes e configuracoes de conta.
        </p>
      </div>

      <div className="button-row">
        <button type="button" className="btn btn-primary" onClick={() => void loadProfile()}>
          Recarregar
        </button>
        <button type="button" className="btn btn-danger" onClick={logout}>
          Sair
        </button>
      </div>

      {isLoading ? <p className="state-note">Carregando perfil...</p> : null}
      {error ? <div className="error-banner">{error}</div> : null}

      {user ? (
        <>
          <div className="kv-grid">
            <article className="kv-card">
              <p className="kv-label">ID</p>
              <p className="kv-value">{user.id}</p>
            </article>
            <article className="kv-card">
              <p className="kv-label">Email</p>
              <p className="kv-value">{user.email}</p>
            </article>
            <article className="kv-card">
              <p className="kv-label">Nome</p>
              <p className="kv-value">{user.full_name || '-'}</p>
            </article>
            <article className="kv-card">
              <p className="kv-label">Plano</p>
              <p className="kv-value">{user.plan_tier}</p>
            </article>
            <article className="kv-card">
              <p className="kv-label">Role</p>
              <p className="kv-value">{user.role}</p>
            </article>
            <article className="kv-card">
              <p className="kv-label">Provider</p>
              <p className="kv-value">{user.llm_provider || '-'}</p>
            </article>
            <article className="kv-card">
              <p className="kv-label">API key</p>
              <p className="kv-value">{user.has_api_key ? 'Configurada' : 'Ausente'}</p>
            </article>
            <article className="kv-card">
              <p className="kv-label">Ativo</p>
              <p className="kv-value">{user.is_active ? 'Sim' : 'Não'}</p>
            </article>
            <article className="kv-card">
              <p className="kv-label">Verificado</p>
              <p className="kv-value">{user.is_verified ? 'Sim' : 'Não'}</p>
            </article>
          </div>

          {usageSummary && (
            <>
              <div className="view-head">
                <p className="eyebrow">Uso BYO-LLM</p>
                <h2 className="view-title">Ultimos {usageSummary.period_days} dias</h2>
                <p className="view-subtitle">
                  Visao resumida de mensagens, tokens, latencia e taxa de erro.
                </p>
              </div>

              <div className="kv-grid">
                <article className="kv-card">
                  <p className="kv-label">Mensagens</p>
                  <p className="kv-value">{usageSummary.totals.messages}</p>
                </article>
                <article className="kv-card">
                  <p className="kv-label">Tokens</p>
                  <p className="kv-value">{usageSummary.totals.tokens.toLocaleString()}</p>
                </article>
                <article className="kv-card">
                  <p className="kv-label">Latencia p50</p>
                  <p className="kv-value">{usageSummary.totals.latency_p50_ms.toFixed(1)} ms</p>
                </article>
                <article className="kv-card">
                  <p className="kv-label">Latencia p95</p>
                  <p className="kv-value">{usageSummary.totals.latency_p95_ms.toFixed(1)} ms</p>
                </article>
                <article className="kv-card">
                  <p className="kv-label">Taxa de erro</p>
                  <p className="kv-value">{usageSummary.totals.error_rate_pct.toFixed(2)}%</p>
                </article>
              </div>

              {usageSummary.alerts.length > 0 && (
                <div className="button-row">
                  {usageSummary.alerts.map((alert) => (
                    <span key={`${alert.code}-${alert.message}`} className="chip chip-muted">
                      {alert.severity.toUpperCase()}: {alert.message}
                    </span>
                  ))}
                </div>
              )}

              {usageSummary.by_provider_model.length > 0 && (
                <div className="data-table__wrapper">
                  <table className="data-table__table">
                    <thead>
                      <tr>
                        <th>Provider</th>
                        <th>Modelo</th>
                        <th>Mensagens</th>
                        <th>Tokens</th>
                        <th>Lat. media (ms)</th>
                        <th>Erro (%)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {usageSummary.by_provider_model.map((row) => (
                        <tr key={`${row.provider}-${row.model}`}>
                          <td>{row.provider}</td>
                          <td>{row.model}</td>
                          <td>{row.messages}</td>
                          <td>{row.tokens.toLocaleString()}</td>
                          <td>{row.avg_latency_ms.toFixed(1)}</td>
                          <td>{row.error_rate_pct.toFixed(2)}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}

          {/* LLM Configuration */}
          <div className="view-head">
            <p className="eyebrow">BYO-LLM</p>
            <h2 className="view-title">Configurar provedor LLM</h2>
            <p className="view-subtitle">
              Informe seu provedor e API key para usar o chat.
            </p>
          </div>

          <form
            className="auth-form"
            onSubmit={(e) => {
              e.preventDefault();
              void saveLlmConfig();
            }}
          >
            <div className="field">
              <label className="field-label" htmlFor="llm-provider">
                Provedor
              </label>
              <select
                id="llm-provider"
                value={llmProvider}
                onChange={(e) => setLlmProvider(e.target.value)}
              >
                <option value="">Selecione...</option>
                {LLM_PROVIDERS.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="field">
              <label className="field-label" htmlFor="api-key">
                API Key {user.has_api_key ? '(ja configurada — preencha para alterar)' : ''}
              </label>
              <input
                id="api-key"
                type="password"
                placeholder={user.has_api_key ? '***' : 'sk-...'}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                autoComplete="off"
              />
            </div>

            <div className="button-row">
              <button
                type="submit"
                className="btn btn-primary"
                disabled={llmSaving || (!llmProvider && !apiKey)}
              >
                {llmSaving ? 'Salvando...' : 'Salvar configuracao'}
              </button>
              {llmSuccess ? (
                <span className="chip chip-live">Salvo com sucesso</span>
              ) : null}
            </div>
          </form>
        </>
      ) : null}
    </section>
  );
}

export default MePage;
