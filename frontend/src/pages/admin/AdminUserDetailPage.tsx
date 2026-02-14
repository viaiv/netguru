/**
 * AdminUserDetailPage — user detail with actions.
 */
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import ConfirmModal from '../../components/admin/ConfirmModal';
import UserRoleBadge from '../../components/admin/UserRoleBadge';
import PlanTierBadge from '../../components/admin/PlanTierBadge';
import { deleteAdminUser, updateAdminUser } from '../../services/adminApi';
import { getErrorMessage } from '../../services/api';
import { useAdminStore } from '../../stores/adminStore';

function AdminUserDetailPage() {
  const { userId } = useParams<{ userId: string }>();
  const navigate = useNavigate();
  const user = useAdminStore((s) => s.userDetail);
  const loading = useAdminStore((s) => s.userDetailLoading);
  const loadUserDetail = useAdminStore((s) => s.loadUserDetail);

  const [confirmAction, setConfirmAction] = useState<{
    title: string;
    message: string;
    action: () => Promise<void>;
  } | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (userId) loadUserDetail(userId);
  }, [userId, loadUserDetail]);

  async function handleRoleChange(newRole: string) {
    if (!userId) return;
    try {
      await updateAdminUser(userId, { role: newRole });
      loadUserDetail(userId);
      setConfirmAction(null);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  async function handleDelete() {
    if (!userId) return;
    try {
      await deleteAdminUser(userId);
      navigate('/admin/users');
    } catch (err) {
      setError(getErrorMessage(err));
      setConfirmAction(null);
    }
  }

  async function handleToggleActive() {
    if (!userId || !user) return;
    try {
      await updateAdminUser(userId, { is_active: !user.is_active });
      loadUserDetail(userId);
      setConfirmAction(null);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  async function handleTierChange(newTier: string) {
    if (!userId) return;
    try {
      await updateAdminUser(userId, { plan_tier: newTier });
      loadUserDetail(userId);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  if (loading && !user) {
    return <p className="admin-loading">Carregando usuario...</p>;
  }

  if (!user) {
    return <p className="admin-empty">Usuario nao encontrado.</p>;
  }

  return (
    <section className="admin-page">
      <div className="admin-page-header">
        <button type="button" className="btn btn-secondary btn--sm" onClick={() => navigate('/admin/users')}>
          Voltar
        </button>
        <h2 className="admin-page-title">{user.email}</h2>
      </div>

      {error && <div className="admin-error">{error}</div>}

      <div className="admin-detail-grid">
        <div className="kv-card">
          <h3>Informacoes</h3>
          <dl className="kv-list">
            <dt>Nome</dt>
            <dd>{user.full_name || '-'}</dd>
            <dt>Email</dt>
            <dd>{user.email}</dd>
            <dt>Role</dt>
            <dd><UserRoleBadge role={user.role} /></dd>
            <dt>Plano</dt>
            <dd><PlanTierBadge tier={user.plan_tier} /></dd>
            <dt>Status</dt>
            <dd>
              <span className={user.is_active ? 'chip chip--active' : 'chip chip--inactive'}>
                {user.is_active ? 'Ativo' : 'Inativo'}
              </span>
            </dd>
            <dt>LLM Provider</dt>
            <dd>{user.llm_provider || 'Nenhum'}</dd>
            <dt>API Key</dt>
            <dd>{user.has_api_key ? 'Configurada' : 'Nao configurada'}</dd>
            <dt>Criado em</dt>
            <dd>{new Date(user.created_at).toLocaleString('pt-BR')}</dd>
            <dt>Ultimo login</dt>
            <dd>{user.last_login_at ? new Date(user.last_login_at).toLocaleString('pt-BR') : '-'}</dd>
          </dl>
        </div>

        <div className="kv-card">
          <h3>Uso Hoje</h3>
          <dl className="kv-list">
            <dt>Uploads</dt>
            <dd>{user.usage.uploads_today}</dd>
            <dt>Mensagens</dt>
            <dd>{user.usage.messages_today}</dd>
            <dt>Tokens</dt>
            <dd>{user.usage.tokens_today.toLocaleString()}</dd>
          </dl>
        </div>

        <div className="kv-card">
          <h3>Acoes</h3>
          <div className="admin-actions">
            <div className="admin-actions__group">
              <label>Alterar Role</label>
              <select
                value={user.role}
                onChange={(e) => {
                  const newRole = e.target.value;
                  setConfirmAction({
                    title: 'Alterar Role',
                    message: `Alterar role de ${user.email} para "${newRole}"?`,
                    action: () => handleRoleChange(newRole),
                  });
                }}
              >
                <option value="owner">Owner</option>
                <option value="admin">Admin</option>
                <option value="member">Member</option>
                <option value="viewer">Viewer</option>
              </select>
            </div>

            <div className="admin-actions__group">
              <label>Alterar Plano</label>
              <select value={user.plan_tier} onChange={(e) => handleTierChange(e.target.value)}>
                <option value="solo">Solo</option>
                <option value="team">Team</option>
                <option value="enterprise">Enterprise</option>
              </select>
            </div>

            <button
              type="button"
              className={user.is_active ? 'btn btn--danger' : 'btn btn--success'}
              onClick={() =>
                setConfirmAction({
                  title: user.is_active ? 'Desativar Usuario' : 'Ativar Usuario',
                  message: `${user.is_active ? 'Desativar' : 'Ativar'} o usuario ${user.email}?`,
                  action: handleToggleActive,
                })
              }
            >
              {user.is_active ? 'Desativar' : 'Ativar'}
            </button>

            <button
              type="button"
              className="btn btn--danger"
              onClick={() =>
                setConfirmAction({
                  title: 'Deletar Usuario',
                  message: `Tem certeza que deseja deletar permanentemente o usuario ${user.email}? Todas as conversas, documentos e dados serao removidos. Esta acao nao pode ser desfeita.`,
                  action: handleDelete,
                })
              }
            >
              Deletar
            </button>
          </div>
        </div>
      </div>

      <ConfirmModal
        open={!!confirmAction}
        title={confirmAction?.title || ''}
        message={confirmAction?.message || ''}
        variant="danger"
        onConfirm={() => confirmAction?.action()}
        onCancel={() => setConfirmAction(null)}
      />
    </section>
  );
}

export default AdminUserDetailPage;
