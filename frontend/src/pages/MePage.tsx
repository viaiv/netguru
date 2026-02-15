import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import {
  api,
  getErrorMessage,
  type IUserResponse,
} from '../services/api';
import { dispatchAuthLogout } from '../services/authEvents';
import {
  createPortalSession,
  fetchMySubscription,
  type ISeatInfo,
  type IUserSubscription,
} from '../services/billingApi';

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

function isUnlimited(value: number): boolean {
  return value >= 999_999;
}

function formatLimit(value: number): string {
  if (isUnlimited(value)) return 'Ilimitado';
  return value.toLocaleString('pt-BR');
}

function usagePercent(current: number, max: number): number {
  if (isUnlimited(max) || max === 0) return 0;
  return Math.min(100, Math.round((current / max) * 100));
}

function MePage() {
  const navigate = useNavigate();
  const [user, setUser] = useState<IUserResponse | null>(null);
  const [usageSummary, setUsageSummary] = useState<IUserByoLlmUsageSummary | null>(null);
  const [subscription, setSubscription] = useState<IUserSubscription | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [portalLoading, setPortalLoading] = useState(false);

  // LLM config form
  const [llmProvider, setLlmProvider] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [llmSaving, setLlmSaving] = useState(false);
  const [llmSuccess, setLlmSuccess] = useState(false);

  async function loadProfile(): Promise<void> {
    setError(null);
    setIsLoading(true);

    try {
      const [profileResponse, usageResponse, subResponse] = await Promise.all([
        api.get<IUserResponse>('/users/me'),
        api.get<IUserByoLlmUsageSummary>('/users/me/usage-summary', {
          params: { days: 7 },
        }),
        fetchMySubscription().catch(() => null),
      ]);
      setUser(profileResponse.data);
      setUsageSummary(usageResponse.data);
      setSubscription(subResponse);
      setLlmProvider(profileResponse.data.llm_provider || '');
      setApiKey('');
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setIsLoading(false);
    }
  }

  async function handleManagePayment(): Promise<void> {
    setPortalLoading(true);
    try {
      const result = await createPortalSession();
      window.location.href = result.portal_url;
    } catch (err) {
      setError(getErrorMessage(err));
      setPortalLoading(false);
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
              <p className="kv-value">
                {user.active_workspace?.plan_tier ?? user.plan_tier}
              </p>
            </article>
            {user.active_workspace && (
              <article className="kv-card">
                <p className="kv-label">Workspace</p>
                <p className="kv-value">{user.active_workspace.name}</p>
              </article>
            )}
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
              <p className="kv-label">Modo LLM</p>
              <p className="kv-value">
                {user.has_api_key
                  ? `BYO (${user.llm_provider || 'sem provedor'})`
                  : ['team', 'enterprise'].includes(user.active_workspace?.plan_tier ?? user.plan_tier)
                    ? 'BYO obrigatorio — configure sua API key'
                    : 'Fallback gratuito'}
              </p>
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

          {/* Subscription & Daily Usage */}
          {subscription && (
            <>
              <div className="view-head">
                <p className="eyebrow">Assinatura</p>
                <h2 className="view-title">Plano e uso diario</h2>
                <p className="view-subtitle">
                  Gerencie sua assinatura e acompanhe o uso do dia.
                </p>
              </div>

              <div className="kv-grid">
                <article className="kv-card">
                  <p className="kv-label">Plano atual</p>
                  <p className="kv-value">{subscription.plan.display_name}</p>
                </article>
                <article className="kv-card">
                  <p className="kv-label">Status</p>
                  <p className="kv-value">
                    {subscription.has_subscription
                      ? subscription.subscription?.status === 'active'
                        ? 'Ativo'
                        : subscription.subscription?.status ?? 'Sem assinatura'
                      : 'Sem assinatura Stripe'}
                  </p>
                </article>
                {subscription.subscription?.current_period_end && (
                  <article className="kv-card">
                    <p className="kv-label">Proximo vencimento</p>
                    <p className="kv-value">
                      {new Date(subscription.subscription.current_period_end).toLocaleDateString('pt-BR')}
                    </p>
                  </article>
                )}
              </div>

              {/* Daily usage bars */}
              <div className="kv-grid" style={{ marginTop: '1rem' }}>
                {([
                  {
                    label: 'Uploads hoje',
                    current: subscription.usage_today.uploads_today,
                    max: subscription.plan.upload_limit_daily,
                  },
                  {
                    label: 'Mensagens hoje',
                    current: subscription.usage_today.messages_today,
                    max: subscription.plan.max_conversations_daily,
                  },
                  {
                    label: 'Tokens hoje',
                    current: subscription.usage_today.tokens_today,
                    max: subscription.plan.max_tokens_daily,
                  },
                ] as const).map((item) => {
                  const pct = usagePercent(item.current, item.max);
                  const barColor = pct >= 90 ? '#ef4444' : pct >= 70 ? '#f59e0b' : '#22c55e';
                  return (
                    <article key={item.label} className="kv-card">
                      <p className="kv-label">{item.label}</p>
                      <p className="kv-value">
                        {item.current.toLocaleString('pt-BR')} / {formatLimit(item.max)}
                      </p>
                      {!isUnlimited(item.max) && (
                        <div
                          style={{
                            marginTop: '0.5rem',
                            height: '6px',
                            background: 'rgba(255,255,255,0.1)',
                            borderRadius: '3px',
                            overflow: 'hidden',
                          }}
                        >
                          <div
                            style={{
                              width: `${pct}%`,
                              height: '100%',
                              background: barColor,
                              borderRadius: '3px',
                              transition: 'width 0.3s ease',
                            }}
                          />
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>

              {/* Seat info for Team/Enterprise */}
              {subscription.seat_info && (
                <>
                  <div className="view-head" style={{ marginTop: '1.5rem' }}>
                    <p className="eyebrow">Assentos</p>
                    <h2 className="view-title">Gerenciamento de assentos</h2>
                  </div>
                  <div className="kv-grid">
                    <article className="kv-card">
                      <p className="kv-label">Inclusos no plano</p>
                      <p className="kv-value">{subscription.seat_info.max_members_included}</p>
                    </article>
                    <article className="kv-card">
                      <p className="kv-label">Membros ativos</p>
                      <p className="kv-value">{subscription.seat_info.current_members}</p>
                    </article>
                    <article className="kv-card">
                      <p className="kv-label">Assentos cobrados</p>
                      <p className="kv-value">{subscription.seat_info.seats_billed}</p>
                    </article>
                    <article className="kv-card">
                      <p className="kv-label">Extras</p>
                      <p className="kv-value">
                        {subscription.seat_info.extra_seats > 0
                          ? `${subscription.seat_info.extra_seats} (R$ ${(subscription.seat_info.extra_seat_price_cents / 100).toFixed(2).replace('.', ',')}/cada)`
                          : 'Nenhum'}
                      </p>
                    </article>
                  </div>
                </>
              )}

              <div className="button-row" style={{ marginTop: '1rem' }}>
                <button
                  type="button"
                  className="btn btn-outline"
                  onClick={() => navigate('/pricing')}
                >
                  Upgrade
                </button>
                {subscription.has_subscription && (
                  <button
                    type="button"
                    className="btn btn-outline"
                    disabled={portalLoading}
                    onClick={() => void handleManagePayment()}
                  >
                    {portalLoading ? 'Abrindo...' : 'Gerenciar pagamento'}
                  </button>
                )}
              </div>
            </>
          )}

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
