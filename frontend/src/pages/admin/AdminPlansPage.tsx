/**
 * AdminPlansPage — plan management with CRUD.
 */
import { useEffect, useState } from 'react';

import ConfirmModal from '../../components/admin/ConfirmModal';
import { createPlan, deletePlan, updatePlan } from '../../services/adminApi';
import type { IPlan, IPlanCreate } from '../../services/adminApi';
import { getErrorMessage } from '../../services/api';
import { useAdminStore } from '../../stores/adminStore';
import { useAuthStore } from '../../stores/authStore';

const EMPTY_PLAN: IPlanCreate = {
  name: '',
  display_name: '',
  price_cents: 0,
  billing_period: 'monthly',
  upload_limit_daily: 10,
  max_file_size_mb: 100,
  max_conversations_daily: 50,
  max_tokens_daily: 100000,
};

function AdminPlansPage() {
  const plans = useAdminStore((s) => s.plans);
  const loading = useAdminStore((s) => s.plansLoading);
  const loadPlans = useAdminStore((s) => s.loadPlans);
  const userRole = useAuthStore((s) => s.user?.role);
  const isOwner = userRole === 'owner';

  const [showForm, setShowForm] = useState(false);
  const [editingPlan, setEditingPlan] = useState<IPlan | null>(null);
  const [formData, setFormData] = useState<IPlanCreate>(EMPTY_PLAN);
  const [deleteTarget, setDeleteTarget] = useState<IPlan | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    loadPlans();
  }, [loadPlans]);

  function openCreate() {
    setEditingPlan(null);
    setFormData(EMPTY_PLAN);
    setShowForm(true);
    setError('');
  }

  function openEdit(plan: IPlan) {
    setEditingPlan(plan);
    setFormData({
      name: plan.name,
      display_name: plan.display_name,
      price_cents: plan.price_cents,
      billing_period: plan.billing_period,
      upload_limit_daily: plan.upload_limit_daily,
      max_file_size_mb: plan.max_file_size_mb,
      max_conversations_daily: plan.max_conversations_daily,
      max_tokens_daily: plan.max_tokens_daily,
    });
    setShowForm(true);
    setError('');
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    try {
      if (editingPlan) {
        await updatePlan(editingPlan.id, formData);
      } else {
        await createPlan(formData);
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

  function formatPrice(cents: number): string {
    return `$${(cents / 100).toFixed(2)}`;
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
                {plan.price_cents === 0 ? 'Custom' : formatPrice(plan.price_cents)}
                <span className="plan-card__period">/{plan.billing_period === 'monthly' ? 'mes' : 'ano'}</span>
              </p>
              {!plan.is_active && <span className="chip chip--inactive">Inativo</span>}
              <dl className="kv-list kv-list--compact">
                <dt>Uploads/dia</dt>
                <dd>{plan.upload_limit_daily}</dd>
                <dt>Tamanho max.</dt>
                <dd>{plan.max_file_size_mb} MB</dd>
                <dt>Conversas/dia</dt>
                <dd>{plan.max_conversations_daily}</dd>
                <dt>Tokens/dia</dt>
                <dd>{plan.max_tokens_daily.toLocaleString()}</dd>
              </dl>
              {isOwner && (
                <div className="plan-card__actions">
                  <button type="button" className="ghost-btn" onClick={() => openEdit(plan)}>
                    Editar
                  </button>
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
          <div className="modal modal--wide" onClick={(e) => e.stopPropagation()}>
            <h3 className="modal__title">{editingPlan ? 'Editar Plano' : 'Novo Plano'}</h3>
            <form onSubmit={handleSubmit} className="plan-form">
              <div className="plan-form__row">
                <label>Slug</label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  disabled={!!editingPlan}
                  required
                />
              </div>
              <div className="plan-form__row">
                <label>Nome de exibicao</label>
                <input
                  type="text"
                  value={formData.display_name}
                  onChange={(e) => setFormData({ ...formData, display_name: e.target.value })}
                  required
                />
              </div>
              <div className="plan-form__row">
                <label>Preco (centavos USD)</label>
                <input
                  type="number"
                  value={formData.price_cents}
                  onChange={(e) => setFormData({ ...formData, price_cents: Number(e.target.value) })}
                  min={0}
                />
              </div>
              <div className="plan-form__row">
                <label>Periodo</label>
                <select
                  value={formData.billing_period}
                  onChange={(e) => setFormData({ ...formData, billing_period: e.target.value })}
                >
                  <option value="monthly">Mensal</option>
                  <option value="yearly">Anual</option>
                </select>
              </div>
              <div className="plan-form__row">
                <label>Uploads/dia</label>
                <input
                  type="number"
                  value={formData.upload_limit_daily}
                  onChange={(e) => setFormData({ ...formData, upload_limit_daily: Number(e.target.value) })}
                  min={0}
                />
              </div>
              <div className="plan-form__row">
                <label>Tamanho max. (MB)</label>
                <input
                  type="number"
                  value={formData.max_file_size_mb}
                  onChange={(e) => setFormData({ ...formData, max_file_size_mb: Number(e.target.value) })}
                  min={1}
                />
              </div>
              <div className="plan-form__row">
                <label>Conversas/dia</label>
                <input
                  type="number"
                  value={formData.max_conversations_daily}
                  onChange={(e) => setFormData({ ...formData, max_conversations_daily: Number(e.target.value) })}
                  min={0}
                />
              </div>
              <div className="plan-form__row">
                <label>Tokens/dia</label>
                <input
                  type="number"
                  value={formData.max_tokens_daily}
                  onChange={(e) => setFormData({ ...formData, max_tokens_daily: Number(e.target.value) })}
                  min={0}
                />
              </div>
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
