/**
 * AdminPlansPage — plan management with CRUD + Stripe integration.
 */
import { useEffect, useState } from 'react';

import ConfirmModal from '../../components/admin/ConfirmModal';
import { createPlan, deletePlan, stripeSyncPlan, updatePlan } from '../../services/adminApi';
import type { IPlan, IPlanCreate } from '../../services/adminApi';
import { getErrorMessage } from '../../services/api';
import { useAdminStore } from '../../stores/adminStore';
import { useAuthStore } from '../../stores/authStore';

interface IPlanFormData {
  name: string;
  display_name: string;
  stripe_product_id: string;
  stripe_price_id: string;
  price_cents: number;
  billing_period: string;
  upload_limit_daily: number;
  max_file_size_mb: number;
  max_conversations_daily: number;
  max_tokens_daily: number;
  features_json: string;
  is_active: boolean;
  sort_order: number;
}

const EMPTY_FORM: IPlanFormData = {
  name: '',
  display_name: '',
  stripe_product_id: '',
  stripe_price_id: '',
  price_cents: 0,
  billing_period: 'monthly',
  upload_limit_daily: 10,
  max_file_size_mb: 100,
  max_conversations_daily: 50,
  max_tokens_daily: 100000,
  features_json: '{}',
  is_active: true,
  sort_order: 0,
};

function planToForm(plan: IPlan): IPlanFormData {
  return {
    name: plan.name,
    display_name: plan.display_name,
    stripe_product_id: plan.stripe_product_id || '',
    stripe_price_id: plan.stripe_price_id || '',
    price_cents: plan.price_cents,
    billing_period: plan.billing_period,
    upload_limit_daily: plan.upload_limit_daily,
    max_file_size_mb: plan.max_file_size_mb,
    max_conversations_daily: plan.max_conversations_daily,
    max_tokens_daily: plan.max_tokens_daily,
    features_json: plan.features ? JSON.stringify(plan.features, null, 2) : '{}',
    is_active: plan.is_active,
    sort_order: plan.sort_order,
  };
}

function formToPayload(form: IPlanFormData): IPlanCreate {
  let features: Record<string, boolean> | undefined;
  try {
    const parsed = JSON.parse(form.features_json);
    if (parsed && typeof parsed === 'object' && Object.keys(parsed).length > 0) {
      features = parsed;
    }
  } catch {
    // ignore invalid JSON — backend will use null
  }

  return {
    name: form.name,
    display_name: form.display_name,
    stripe_product_id: form.stripe_product_id || null,
    stripe_price_id: form.stripe_price_id || null,
    price_cents: form.price_cents,
    billing_period: form.billing_period,
    upload_limit_daily: form.upload_limit_daily,
    max_file_size_mb: form.max_file_size_mb,
    max_conversations_daily: form.max_conversations_daily,
    max_tokens_daily: form.max_tokens_daily,
    features,
    is_active: form.is_active,
    sort_order: form.sort_order,
  };
}

function formatPrice(cents: number): string {
  return `R$ ${(cents / 100).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`;
}

function AdminPlansPage() {
  const plans = useAdminStore((s) => s.plans);
  const loading = useAdminStore((s) => s.plansLoading);
  const loadPlans = useAdminStore((s) => s.loadPlans);
  const userRole = useAuthStore((s) => s.user?.role);
  const isOwner = userRole === 'owner';

  const [showForm, setShowForm] = useState(false);
  const [editingPlan, setEditingPlan] = useState<IPlan | null>(null);
  const [formData, setFormData] = useState<IPlanFormData>(EMPTY_FORM);
  const [deleteTarget, setDeleteTarget] = useState<IPlan | null>(null);
  const [syncingId, setSyncingId] = useState<string | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    loadPlans();
  }, [loadPlans]);

  function openCreate() {
    setEditingPlan(null);
    setFormData(EMPTY_FORM);
    setShowForm(true);
    setError('');
  }

  function openEdit(plan: IPlan) {
    setEditingPlan(plan);
    setFormData(planToForm(plan));
    setShowForm(true);
    setError('');
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    try {
      const payload = formToPayload(formData);
      if (editingPlan) {
        await updatePlan(editingPlan.id, payload);
      } else {
        await createPlan(payload);
      }
      setShowForm(false);
      loadPlans();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    try {
      await deletePlan(deleteTarget.id);
      setDeleteTarget(null);
      loadPlans();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  async function handleStripeSync(plan: IPlan) {
    setSyncingId(plan.id);
    setError('');
    try {
      await stripeSyncPlan(plan.id);
      loadPlans();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSyncingId(null);
    }
  }

  function set<K extends keyof IPlanFormData>(key: K, value: IPlanFormData[K]) {
    setFormData((prev) => ({ ...prev, [key]: value }));
  }

  return (
    <div className="admin-plans">
      <div className="admin-page-header">
        <h2 className="admin-page-title">Planos</h2>
        {isOwner && (
          <button type="button" className="btn btn--primary" onClick={openCreate}>
            Novo Plano
          </button>
        )}
      </div>

      {error && <div className="admin-error">{error}</div>}

      {loading && plans.length === 0 ? (
        <p className="admin-loading">Carregando planos...</p>
      ) : (
        <div className="plans-grid">
          {plans.map((plan) => (
            <div key={plan.id} className={`plan-card kv-card ${!plan.is_active ? 'plan-card--inactive' : ''}`}>
              <div className="plan-card__header">
                <h3 className="plan-card__name">{plan.display_name}</h3>
                <span className={`chip chip--tier-${plan.name}`}>{plan.name}</span>
              </div>
              <p className="plan-card__price">
                {plan.price_cents === 0 ? 'Sob consulta' : formatPrice(plan.price_cents)}
                {plan.price_cents > 0 && (
                  <span className="plan-card__period">/{plan.billing_period === 'monthly' ? 'mes' : 'ano'}</span>
                )}
              </p>

              {/* Stripe status */}
              <div style={{ marginBottom: '0.75rem' }}>
                {plan.stripe_price_id ? (
                  <span className="chip chip-live" style={{ fontSize: '0.7rem' }}>
                    Stripe ativo
                  </span>
                ) : (
                  <span className="chip chip-muted" style={{ fontSize: '0.7rem' }}>
                    Stripe nao configurado
                  </span>
                )}
                {!plan.is_active && (
                  <span className="chip chip--inactive" style={{ marginLeft: '0.25rem' }}>Inativo</span>
                )}
              </div>

              <dl className="kv-list kv-list--compact">
                <dt>Uploads/dia</dt>
                <dd>{plan.upload_limit_daily.toLocaleString()}</dd>
                <dt>Tamanho max.</dt>
                <dd>{plan.max_file_size_mb} MB</dd>
                <dt>Mensagens/dia</dt>
                <dd>{plan.max_conversations_daily.toLocaleString()}</dd>
                <dt>Tokens/dia</dt>
                <dd>{plan.max_tokens_daily.toLocaleString()}</dd>
                <dt>Ordem</dt>
                <dd>{plan.sort_order}</dd>
              </dl>

              {plan.features && Object.keys(plan.features).length > 0 && (
                <dl className="kv-list kv-list--compact" style={{ marginTop: '0.5rem', opacity: 0.8 }}>
                  <dt style={{ gridColumn: '1 / -1', fontWeight: 600, fontSize: '0.75rem' }}>Features</dt>
                  {Object.entries(plan.features).map(([key, value]) => (
                    <span key={key} style={{ fontSize: '0.75rem' }}>
                      {key}: {value ? 'sim' : 'nao'}
                      {' '}
                    </span>
                  ))}
                </dl>
              )}

              {isOwner && (
                <div className="plan-card__actions">
                  <button type="button" className="ghost-btn" onClick={() => openEdit(plan)}>
                    Editar
                  </button>
                  {plan.price_cents > 0 && (
                    <button
                      type="button"
                      className="ghost-btn"
                      disabled={syncingId === plan.id}
                      onClick={() => void handleStripeSync(plan)}
                    >
                      {syncingId === plan.id
                        ? 'Sincronizando...'
                        : plan.stripe_price_id
                          ? 'Resincronizar Stripe'
                          : 'Criar no Stripe'}
                    </button>
                  )}
                  {plan.is_active && (
                    <button
                      type="button"
                      className="ghost-btn ghost-btn--danger"
                      onClick={() => setDeleteTarget(plan)}
                    >
                      Desativar
                    </button>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Plan form modal */}
      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal modal--xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="modal__title">{editingPlan ? 'Editar Plano' : 'Novo Plano'}</h3>
            <form onSubmit={(e) => void handleSubmit(e)} className="plan-form">
              {/* Identidade */}
              <fieldset className="plan-form__fieldset">
                <legend>Identidade</legend>
                <div className="plan-form__row">
                  <label>Slug (imutavel)</label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => set('name', e.target.value)}
                    disabled={!!editingPlan}
                    placeholder="ex: solo, team, enterprise"
                    required
                  />
                </div>
                <div className="plan-form__row">
                  <label>Nome de exibicao</label>
                  <input
                    type="text"
                    value={formData.display_name}
                    onChange={(e) => set('display_name', e.target.value)}
                    placeholder="ex: Solo Engineer"
                    required
                  />
                </div>
                <div className="plan-form__row">
                  <label>Ordem de exibicao</label>
                  <input
                    type="number"
                    value={formData.sort_order}
                    onChange={(e) => set('sort_order', Number(e.target.value))}
                    min={0}
                  />
                </div>
                <div className="plan-form__row">
                  <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <input
                      type="checkbox"
                      checked={formData.is_active}
                      onChange={(e) => set('is_active', e.target.checked)}
                    />
                    Ativo (visivel na pagina de pricing)
                  </label>
                </div>
              </fieldset>

              {/* Pricing + Stripe */}
              <fieldset className="plan-form__fieldset">
                <legend>Pricing e Stripe</legend>
                <div className="plan-form__row">
                  <label>Preco (centavos BRL)</label>
                  <input
                    type="number"
                    value={formData.price_cents}
                    onChange={(e) => set('price_cents', Number(e.target.value))}
                    min={0}
                  />
                  {formData.price_cents > 0 && (
                    <span style={{ fontSize: '0.8rem', opacity: 0.7 }}>
                      = {formatPrice(formData.price_cents)}
                    </span>
                  )}
                </div>
                <div className="plan-form__row">
                  <label>Periodo</label>
                  <select
                    value={formData.billing_period}
                    onChange={(e) => set('billing_period', e.target.value)}
                  >
                    <option value="monthly">Mensal</option>
                    <option value="yearly">Anual</option>
                  </select>
                </div>
                <div className="plan-form__row">
                  <label>Stripe Product ID</label>
                  <input
                    type="text"
                    value={formData.stripe_product_id}
                    onChange={(e) => set('stripe_product_id', e.target.value)}
                    placeholder="prod_..."
                  />
                </div>
                <div className="plan-form__row">
                  <label>Stripe Price ID</label>
                  <input
                    type="text"
                    value={formData.stripe_price_id}
                    onChange={(e) => set('stripe_price_id', e.target.value)}
                    placeholder="price_..."
                  />
                  {!formData.stripe_price_id && (
                    <span style={{ fontSize: '0.75rem', color: '#f59e0b' }}>
                      Sem Price ID o checkout Stripe ficara indisponivel
                    </span>
                  )}
                </div>
              </fieldset>

              {/* Limites */}
              <fieldset className="plan-form__fieldset">
                <legend>Limites (enforcement diario)</legend>
                <div className="plan-form__row">
                  <label>Uploads/dia</label>
                  <input
                    type="number"
                    value={formData.upload_limit_daily}
                    onChange={(e) => set('upload_limit_daily', Number(e.target.value))}
                    min={0}
                  />
                </div>
                <div className="plan-form__row">
                  <label>Tamanho max. arquivo (MB)</label>
                  <input
                    type="number"
                    value={formData.max_file_size_mb}
                    onChange={(e) => set('max_file_size_mb', Number(e.target.value))}
                    min={1}
                  />
                </div>
                <div className="plan-form__row">
                  <label>Mensagens/dia</label>
                  <input
                    type="number"
                    value={formData.max_conversations_daily}
                    onChange={(e) => set('max_conversations_daily', Number(e.target.value))}
                    min={0}
                  />
                </div>
                <div className="plan-form__row">
                  <label>Tokens/dia</label>
                  <input
                    type="number"
                    value={formData.max_tokens_daily}
                    onChange={(e) => set('max_tokens_daily', Number(e.target.value))}
                    min={0}
                  />
                </div>
              </fieldset>

              {/* Features */}
              <fieldset className="plan-form__fieldset">
                <legend>Features (JSON)</legend>
                <div className="plan-form__row">
                  <textarea
                    value={formData.features_json}
                    onChange={(e) => set('features_json', e.target.value)}
                    rows={5}
                    style={{ fontFamily: 'monospace', fontSize: '0.8rem' }}
                    placeholder='{"rag_global": true, "rag_local": false, "pcap_analysis": true}'
                  />
                </div>
              </fieldset>

              <div className="modal__actions">
                <button type="button" className="modal__btn modal__btn--cancel" onClick={() => setShowForm(false)}>
                  Cancelar
                </button>
                <button type="submit" className="modal__btn modal__btn--confirm">
                  {editingPlan ? 'Salvar' : 'Criar'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <ConfirmModal
        open={!!deleteTarget}
        title="Desativar Plano"
        message={`Desativar o plano "${deleteTarget?.display_name}"? Usuarios existentes nao serao afetados.`}
        variant="danger"
        confirmLabel="Desativar"
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}

export default AdminPlansPage;
