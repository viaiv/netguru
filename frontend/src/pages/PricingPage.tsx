import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useAuthStore } from '../stores/authStore';
import { getErrorMessage } from '../services/api';
import { createCheckout, fetchPublicPlans, type IPublicPlan } from '../services/billingApi';

function formatPrice(cents: number): string {
  return `R$ ${(cents / 100).toFixed(2).replace('.', ',')}`;
}

function isUnlimited(value: number): boolean {
  return value >= 999_999;
}

function formatLimit(value: number, suffix = ''): string {
  if (isUnlimited(value)) return 'Ilimitado';
  return `${value.toLocaleString('pt-BR')}${suffix}`;
}

const FEATURE_LABELS: Record<string, string> = {
  rag_global: 'RAG Global',
  rag_local: 'RAG Local',
  pcap_analysis: 'Analise PCAP',
  topology_generation: 'Topologia',
  custom_tools: 'Custom tools',
};

function PricingPage() {
  const [plans, setPlans] = useState<IPublicPlan[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null);

  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const navigate = useNavigate();

  useEffect(() => {
    async function load(): Promise<void> {
      try {
        const data = await fetchPublicPlans();
        setPlans(data);
      } catch (err) {
        setError(getErrorMessage(err));
      } finally {
        setIsLoading(false);
      }
    }
    void load();
  }, []);

  async function handleSubscribe(plan: IPublicPlan): Promise<void> {
    if (!isAuthenticated) {
      navigate(`/login?redirect=/pricing`);
      return;
    }

    setCheckoutLoading(plan.id);
    setError(null);
    try {
      const result = await createCheckout(plan.id);
      window.location.href = result.checkout_url;
    } catch (err) {
      setError(getErrorMessage(err));
      setCheckoutLoading(null);
    }
  }

  const highlightPlan = 'team';

  return (
    <section className="view">
      <div className="view-head" style={{ textAlign: 'center' }}>
        <p className="eyebrow">Planos</p>
        <h2 className="view-title">Escolha o plano ideal</h2>
        <p className="view-subtitle">
          Todos os planos incluem acesso ao Agent AI, RAG e ferramentas de rede.
        </p>
      </div>

      {isLoading && <p className="state-note">Carregando planos...</p>}
      {error && <div className="error-banner">{error}</div>}

      {!isLoading && plans.length > 0 && (
        <>
          {/* Plan cards */}
          <div
            className="kv-grid"
            style={{
              display: 'grid',
              gridTemplateColumns: `repeat(${Math.min(plans.length, 4)}, 1fr)`,
              gap: '1.5rem',
              marginBottom: '2rem',
            }}
          >
            {plans.map((plan) => {
              const isHighlight = plan.name === highlightPlan;
              return (
                <article
                  key={plan.id}
                  className="kv-card"
                  style={{
                    border: isHighlight ? '2px solid var(--accent, #6366f1)' : undefined,
                    position: 'relative',
                    display: 'flex',
                    flexDirection: 'column',
                    padding: '1.5rem',
                  }}
                >
                  {isHighlight && (
                    <span
                      className="chip chip-live"
                      style={{
                        position: 'absolute',
                        top: '-0.75rem',
                        right: '1rem',
                        fontSize: '0.7rem',
                      }}
                    >
                      Mais popular
                    </span>
                  )}

                  <h3 style={{ margin: '0 0 0.25rem' }}>{plan.display_name}</h3>

                  <p style={{ fontSize: '1.75rem', fontWeight: 700, margin: '0.5rem 0' }}>
                    {plan.price_cents === 0 && plan.name === 'enterprise'
                      ? 'Sob consulta'
                      : plan.price_cents === 0
                        ? 'Gratis'
                        : plan.promo_price_cents
                          ? formatPrice(plan.promo_price_cents)
                          : formatPrice(plan.price_cents)}
                    {plan.price_cents > 0 && (
                      <span style={{ fontSize: '0.875rem', fontWeight: 400, opacity: 0.7 }}>
                        /{plan.billing_period === 'monthly' ? 'mes' : 'ano'}
                      </span>
                    )}
                  </p>
                  {plan.promo_price_cents && plan.promo_months && (
                    <p style={{ fontSize: '0.78rem', color: 'var(--ink-soft)', margin: '-0.25rem 0 0.5rem' }}>
                      por {plan.promo_months} meses, depois {formatPrice(plan.price_cents)}/mes
                    </p>
                  )}

                  <ul style={{ listStyle: 'none', padding: 0, margin: '1rem 0', flex: 1 }}>
                    <li style={{ marginBottom: '0.5rem' }}>
                      {formatLimit(plan.upload_limit_daily)} uploads/dia
                    </li>
                    <li style={{ marginBottom: '0.5rem' }}>
                      Arquivos ate {formatLimit(plan.max_file_size_mb, ' MB')}
                    </li>
                    <li style={{ marginBottom: '0.5rem' }}>
                      {formatLimit(plan.max_conversations_daily)} mensagens/dia
                    </li>
                    <li style={{ marginBottom: '0.5rem' }}>
                      {formatLimit(plan.max_tokens_daily)} tokens/dia
                    </li>
                  </ul>

                  {plan.features && Object.keys(plan.features).length > 0 && (
                    <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 1rem', fontSize: '0.85rem', opacity: 0.8 }}>
                      {Object.entries(plan.features).map(([key, value]) => {
                        const label = FEATURE_LABELS[key] || key;
                        return (
                          <li key={key} style={{ marginBottom: '0.25rem' }}>
                            {value === true ? `✓ ${label}` : value === false ? `— ${label}` : `${label}: ${String(value)}`}
                          </li>
                        );
                      })}
                    </ul>
                  )}

                  {plan.name === 'enterprise' ? (
                    <a
                      href="mailto:contato@netguru.com.br?subject=Enterprise"
                      className="btn btn-outline"
                      style={{ width: '100%', textAlign: 'center' }}
                    >
                      Falar com vendas
                    </a>
                  ) : plan.name === 'free' ? (
                    <button
                      type="button"
                      className="btn btn-outline"
                      onClick={() => navigate(isAuthenticated ? '/chat' : '/register')}
                      style={{ width: '100%' }}
                    >
                      {isAuthenticated ? 'Ir para o chat' : 'Comecar gratis'}
                    </button>
                  ) : !plan.is_purchasable ? (
                    <button
                      type="button"
                      className="btn btn-outline"
                      disabled
                      style={{ width: '100%', opacity: 0.5 }}
                      title="Stripe nao configurado para este plano"
                    >
                      Indisponivel
                    </button>
                  ) : (
                    <button
                      type="button"
                      className={isHighlight ? 'btn btn-primary' : 'btn btn-outline'}
                      disabled={checkoutLoading === plan.id}
                      onClick={() => void handleSubscribe(plan)}
                      style={{ width: '100%' }}
                    >
                      {checkoutLoading === plan.id
                        ? 'Redirecionando...'
                        : 'Assinar'}
                    </button>
                  )}
                </article>
              );
            })}
          </div>

          {/* Comparison table */}
          <div className="view-head" style={{ textAlign: 'center' }}>
            <p className="eyebrow">Comparacao</p>
            <h2 className="view-title">Recursos por plano</h2>
          </div>

          <div className="data-table__wrapper">
            <table className="data-table__table">
              <thead>
                <tr>
                  <th>Recurso</th>
                  {plans.map((p) => (
                    <th key={p.id}>{p.display_name}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Uploads diarios</td>
                  {plans.map((p) => (
                    <td key={p.id}>{formatLimit(p.upload_limit_daily)}</td>
                  ))}
                </tr>
                <tr>
                  <td>Tamanho max. arquivo</td>
                  {plans.map((p) => (
                    <td key={p.id}>{formatLimit(p.max_file_size_mb, ' MB')}</td>
                  ))}
                </tr>
                <tr>
                  <td>Mensagens diarias</td>
                  {plans.map((p) => (
                    <td key={p.id}>{formatLimit(p.max_conversations_daily)}</td>
                  ))}
                </tr>
                <tr>
                  <td>Tokens diarios</td>
                  {plans.map((p) => (
                    <td key={p.id}>{formatLimit(p.max_tokens_daily)}</td>
                  ))}
                </tr>
                <tr>
                  <td>Preco</td>
                  {plans.map((p) => (
                    <td key={p.id}>
                      {p.price_cents === 0 && p.name === 'enterprise'
                        ? 'Sob consulta'
                        : p.price_cents === 0
                          ? 'Gratis'
                          : formatPrice(p.price_cents)}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td>RAG Global</td>
                  {plans.map((p) => (
                    <td key={p.id}>{p.features?.rag_global ? '✓' : '—'}</td>
                  ))}
                </tr>
                <tr>
                  <td>RAG Local</td>
                  {plans.map((p) => (
                    <td key={p.id}>{p.features?.rag_local ? '✓' : '—'}</td>
                  ))}
                </tr>
                <tr>
                  <td>Analise PCAP</td>
                  {plans.map((p) => (
                    <td key={p.id}>{p.features?.pcap_analysis ? '✓' : '—'}</td>
                  ))}
                </tr>
                <tr>
                  <td>Topologia</td>
                  {plans.map((p) => (
                    <td key={p.id}>{p.features?.topology_generation ? '✓' : '—'}</td>
                  ))}
                </tr>
                <tr>
                  <td>Custom tools</td>
                  {plans.map((p) => (
                    <td key={p.id}>{p.features?.custom_tools ? '✓' : '—'}</td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}

export default PricingPage;
