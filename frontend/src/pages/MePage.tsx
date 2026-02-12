import axios from 'axios';
import { useEffect, useState } from 'react';

import {
  api,
  getErrorMessage,
  type IRefreshResponse,
  type IUserResponse,
} from '../services/api';
import { dispatchAuthLogout } from '../services/authEvents';
import { useAuthStore } from '../stores/authStore';

function MePage() {
  const refreshToken = useAuthStore((state) => state.refreshToken);
  const setAccessToken = useAuthStore((state) => state.setAccessToken);
  const [user, setUser] = useState<IUserResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  async function loadProfile(): Promise<void> {
    setError(null);
    setIsLoading(true);

    try {
      const response = await api.get<IUserResponse>('/users/me');
      setUser(response.data);
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setIsLoading(false);
    }
  }

  async function refreshAccessToken(): Promise<void> {
    if (!refreshToken) {
      setError('Refresh token ausente. Faça login novamente.');
      dispatchAuthLogout('missing_refresh_token');
      return;
    }

    try {
      const response = await api.post<IRefreshResponse>('/auth/refresh', {
        refresh_token: refreshToken,
      });
      setAccessToken(response.data.access_token);
      await loadProfile();
    } catch (requestError) {
      setError(getErrorMessage(requestError));
      if (axios.isAxiosError(requestError) && requestError.response?.status === 401) {
        dispatchAuthLogout('invalid_refresh');
      }
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
        <p className="eyebrow">Profile</p>
        <h2 className="view-title">Estado da sessão</h2>
        <p className="view-subtitle">
          Leitura de <code>GET /api/v1/users/me</code> e renovação por <code>/auth/refresh</code>.
        </p>
      </div>

      <div className="button-row">
        <button type="button" className="btn btn-primary" onClick={() => void loadProfile()}>
          Recarregar
        </button>
        <button type="button" className="btn btn-secondary" onClick={() => void refreshAccessToken()}>
          Renovar access token
        </button>
        <button type="button" className="btn btn-danger" onClick={logout}>
          Sair
        </button>
      </div>

      {isLoading ? <p className="state-note">Carregando perfil...</p> : null}
      {error ? <div className="error-banner">{error}</div> : null}

      {user ? (
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
      ) : null}
    </section>
  );
}

export default MePage;
