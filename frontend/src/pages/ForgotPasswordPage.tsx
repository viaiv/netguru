/**
 * ForgotPasswordPage — formulario de email para solicitar reset de senha.
 */
import { FormEvent, useState } from 'react';
import { Link } from 'react-router-dom';

import { api, getErrorMessage } from '../services/api';

function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      await api.post('/auth/forgot-password', { email });
      setSubmitted(true);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }

  if (submitted) {
    return (
      <section className="view">
        <div className="view-head">
          <p className="eyebrow">Pronto</p>
          <h2 className="view-title">Verifique seu email</h2>
          <p className="view-subtitle">
            Se o email <strong>{email}</strong> estiver cadastrado, enviaremos um link para
            redefinir sua senha. Verifique sua caixa de entrada e spam.
          </p>
        </div>
        <p className="auth-link" style={{ marginTop: 24 }}>
          <Link to="/login">Voltar para login</Link>
        </p>
      </section>
    );
  }

  return (
    <section className="view">
      <div className="view-head">
        <p className="eyebrow">Recuperar acesso</p>
        <h2 className="view-title">Esqueceu a senha?</h2>
        <p className="view-subtitle">
          Informe seu email e enviaremos um link para redefinir sua senha.
        </p>
      </div>

      <form className="auth-form" onSubmit={handleSubmit}>
        <label className="field">
          <span className="field-label">Email</span>
          <input
            id="forgot_email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>

        <div className="button-row">
          <button type="submit" className="btn btn-primary" disabled={isLoading}>
            {isLoading ? 'Enviando...' : 'Enviar link'}
          </button>
        </div>

        {error && <div className="error-banner">{error}</div>}
      </form>

      <p className="auth-link">
        Lembrou a senha? <Link to="/login">Entrar</Link>
      </p>
    </section>
  );
}

export default ForgotPasswordPage;
