/**
 * ResetPasswordPage — le ?token= da URL, formulario para nova senha.
 */
import { FormEvent, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { api, getErrorMessage } from '../services/api';

function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');

  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  if (!token) {
    return (
      <section className="view">
        <div className="view-head">
          <h2 className="view-title">Redefinir Senha</h2>
        </div>
        <div className="error-banner">
          <p>Token de redefinicao nao encontrado na URL.</p>
        </div>
        <p className="auth-link" style={{ marginTop: 24 }}>
          <Link to="/forgot-password">Solicitar novo link</Link>
        </p>
      </section>
    );
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError('As senhas nao coincidem');
      return;
    }

    setIsLoading(true);
    try {
      await api.post('/auth/reset-password', { token, new_password: password });
      setSuccess(true);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }

  if (success) {
    return (
      <section className="view">
        <div className="view-head">
          <p className="eyebrow">Pronto</p>
          <h2 className="view-title">Senha redefinida</h2>
          <p className="view-subtitle">
            Sua senha foi alterada com sucesso. Voce ja pode fazer login.
          </p>
        </div>
        <p className="auth-link" style={{ marginTop: 24 }}>
          <Link to="/login" className="btn btn-primary" style={{ display: 'inline-block' }}>
            Fazer login
          </Link>
        </p>
      </section>
    );
  }

  return (
    <section className="view">
      <div className="view-head">
        <p className="eyebrow">Nova senha</p>
        <h2 className="view-title">Redefinir Senha</h2>
        <p className="view-subtitle">Escolha uma nova senha para sua conta.</p>
      </div>

      <form className="auth-form" onSubmit={handleSubmit}>
        <label className="field">
          <span className="field-label">Nova senha</span>
          <input
            id="new_password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={8}
            required
          />
        </label>

        <label className="field">
          <span className="field-label">Confirmar senha</span>
          <input
            id="confirm_password"
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            minLength={8}
            required
          />
        </label>

        <div className="button-row">
          <button type="submit" className="btn btn-primary" disabled={isLoading}>
            {isLoading ? 'Redefinindo...' : 'Redefinir senha'}
          </button>
        </div>

        {error && <div className="error-banner">{error}</div>}
      </form>

      <p className="auth-link">
        <Link to="/login">Voltar para login</Link>
      </p>
    </section>
  );
}

export default ResetPasswordPage;
