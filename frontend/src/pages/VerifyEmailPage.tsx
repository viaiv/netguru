/**
 * VerifyEmailPage — le ?token= da URL e chama POST /auth/verify-email.
 */
import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { api, getErrorMessage } from '../services/api';

type Status = 'loading' | 'success' | 'error' | 'no_token';

function VerifyEmailPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');

  const [status, setStatus] = useState<Status>(token ? 'loading' : 'no_token');
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (!token) return;

    api
      .post('/auth/verify-email', { token })
      .then((res) => {
        setStatus('success');
        setMessage(res.data.message);
      })
      .catch((err) => {
        setStatus('error');
        setMessage(getErrorMessage(err));
      });
  }, [token]);

  return (
    <section className="view">
      <div className="view-head">
        <p className="eyebrow">Verificacao</p>
        <h2 className="view-title">Verificar Email</h2>
      </div>

      {status === 'loading' && <p>Verificando seu email...</p>}

      {status === 'success' && (
        <div className="success-banner">
          <p>{message}</p>
          <p style={{ marginTop: 12 }}>
            <Link to="/login" className="btn btn-primary" style={{ display: 'inline-block' }}>
              Fazer login
            </Link>
          </p>
        </div>
      )}

      {status === 'error' && (
        <div className="error-banner">
          <p>{message}</p>
          <p style={{ marginTop: 8 }}>O link pode ter expirado ou ja foi utilizado.</p>
        </div>
      )}

      {status === 'no_token' && (
        <div className="error-banner">
          <p>Token de verificacao nao encontrado na URL.</p>
        </div>
      )}

      <p className="auth-link" style={{ marginTop: 24 }}>
        <Link to="/login">Voltar para login</Link>
      </p>
    </section>
  );
}

export default VerifyEmailPage;
