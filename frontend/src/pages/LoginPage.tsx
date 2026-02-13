import { FormEvent, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';

import { api, getErrorMessage, type ITokenResponse } from '../services/api';
import { useAuthStore } from '../stores/authStore';

interface ILoginLocationState {
  from?: string;
}

export function resolvePostLoginRedirect(state: unknown): string {
  if (state && typeof state === 'object') {
    const candidate = (state as ILoginLocationState).from;
    if (typeof candidate === 'string' && candidate.startsWith('/')) {
      return candidate;
    }
  }

  return '/me';
}

function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const setTokens = useAuthStore((state) => state.setTokens);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      const response = await api.post<ITokenResponse>('/auth/login', {
        email,
        password,
      });

      setTokens(response.data);
      navigate(resolvePostLoginRedirect(location.state), { replace: true });
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <section className="view">
      <div className="view-head">
        <p className="eyebrow">Bem-vindo</p>
        <h2 className="view-title">Entrar na plataforma</h2>
        <p className="view-subtitle">
          Informe suas credenciais para acessar o NetGuru.
        </p>
      </div>

      <form className="auth-form" onSubmit={handleSubmit}>
        <label className="field">
          <span className="field-label">Email</span>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
        </label>

        <label className="field">
          <span className="field-label">Senha</span>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            minLength={8}
            required
          />
        </label>

        <div className="button-row">
          <button type="submit" className="btn btn-primary" disabled={isLoading}>
            {isLoading ? 'Autenticando...' : 'Entrar'}
          </button>
        </div>

        {error ? <div className="error-banner">{error}</div> : null}
      </form>

      <p className="auth-link">
        <Link to="/forgot-password">Esqueceu a senha?</Link>
      </p>
      <p className="auth-link">
        Nao tem conta? <Link to="/register">Criar conta</Link>
      </p>
    </section>
  );
}

export default LoginPage;
