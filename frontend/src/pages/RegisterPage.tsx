import { FormEvent, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { api, getErrorMessage } from '../services/api';

function RegisterPage() {
  const navigate = useNavigate();
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      await api.post('/auth/register', {
        email,
        password,
        full_name: fullName || null,
        plan_tier: 'solo',
      });

      navigate('/login');
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <section className="view">
      <div className="view-head">
        <p className="eyebrow">Criar conta</p>
        <h2 className="view-title">Criar sua conta</h2>
        <p className="view-subtitle">
          Preencha os dados abaixo para comecar a usar o NetGuru.
        </p>
      </div>

      <form className="auth-form" onSubmit={handleSubmit}>
        <label className="field">
          <span className="field-label">Nome completo</span>
          <input
            id="full_name"
            type="text"
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
          />
        </label>

        <label className="field">
          <span className="field-label">Email</span>
          <input
            id="register_email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
        </label>

        <label className="field">
          <span className="field-label">Senha</span>
          <input
            id="register_password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            minLength={8}
            required
          />
        </label>

        <div className="button-row">
          <button type="submit" className="btn btn-primary" disabled={isLoading}>
            {isLoading ? 'Criando usuário...' : 'Criar conta'}
          </button>
        </div>

        {error ? <div className="error-banner">{error}</div> : null}
      </form>

      <p className="auth-link">
        Ja tem conta? <Link to="/login">Entrar</Link>
      </p>
    </section>
  );
}

export default RegisterPage;
