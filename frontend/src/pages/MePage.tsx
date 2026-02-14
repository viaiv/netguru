import { useEffect, useState } from 'react';

import {
  api,
  getErrorMessage,
  type IUserResponse,
} from '../services/api';
import { dispatchAuthLogout } from '../services/authEvents';

const LLM_PROVIDERS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'azure', label: 'Azure OpenAI' },
  { value: 'google', label: 'Google Gemini' },
  { value: 'groq', label: 'Groq' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'openrouter', label: 'OpenRouter' },
] as const;

function MePage() {
  const [user, setUser] = useState<IUserResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // LLM config form
  const [llmProvider, setLlmProvider] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [llmSaving, setLlmSaving] = useState(false);
  const [llmSuccess, setLlmSuccess] = useState(false);

  async function loadProfile(): Promise<void> {
    setError(null);
    setIsLoading(true);

    try {
      const response = await api.get<IUserResponse>('/users/me');
      setUser(response.data);
      setLlmProvider(response.data.llm_provider || '');
      setApiKey('');
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setIsLoading(false);
    }
  }

  async function saveLlmConfig(): Promise<void> {
    setLlmSaving(true);
    setLlmSuccess(false);
    setError(null);

    try {
      const payload: Record<string, string> = {};
      if (llmProvider) payload.llm_provider = llmProvider;
      if (apiKey) payload.api_key = apiKey;

      if (Object.keys(payload).length === 0) {
        setError('Selecione um provedor e informe sua API key.');
        setLlmSaving(false);
        return;
      }

      const response = await api.patch<IUserResponse>('/users/me', payload);
      setUser(response.data);
      setApiKey('');
      setLlmSuccess(true);
      setTimeout(() => setLlmSuccess(false), 3000);
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setLlmSaving(false);
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
        <p className="eyebrow">Minha conta</p>
        <h2 className="view-title">Meu perfil</h2>
        <p className="view-subtitle">
          Gerencie suas informacoes e configuracoes de conta.
        </p>
      </div>

      <div className="button-row">
        <button type="button" className="btn btn-primary" onClick={() => void loadProfile()}>
          Recarregar
        </button>
        <button type="button" className="btn btn-danger" onClick={logout}>
          Sair
        </button>
      </div>

      {isLoading ? <p className="state-note">Carregando perfil...</p> : null}
      {error ? <div className="error-banner">{error}</div> : null}

      {user ? (
        <>
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

          {/* LLM Configuration */}
          <div className="view-head">
            <p className="eyebrow">BYO-LLM</p>
            <h2 className="view-title">Configurar provedor LLM</h2>
            <p className="view-subtitle">
              Informe seu provedor e API key para usar o chat.
            </p>
          </div>

          <form
            className="auth-form"
            onSubmit={(e) => {
              e.preventDefault();
              void saveLlmConfig();
            }}
          >
            <div className="field">
              <label className="field-label" htmlFor="llm-provider">
                Provedor
              </label>
              <select
                id="llm-provider"
                value={llmProvider}
                onChange={(e) => setLlmProvider(e.target.value)}
              >
                <option value="">Selecione...</option>
                {LLM_PROVIDERS.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="field">
              <label className="field-label" htmlFor="api-key">
                API Key {user.has_api_key ? '(ja configurada — preencha para alterar)' : ''}
              </label>
              <input
                id="api-key"
                type="password"
                placeholder={user.has_api_key ? '***' : 'sk-...'}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                autoComplete="off"
              />
            </div>

            <div className="button-row">
              <button
                type="submit"
                className="btn btn-primary"
                disabled={llmSaving || (!llmProvider && !apiKey)}
              >
                {llmSaving ? 'Salvando...' : 'Salvar configuracao'}
              </button>
              {llmSuccess ? (
                <span className="chip chip-live">Salvo com sucesso</span>
              ) : null}
            </div>
          </form>
        </>
      ) : null}
    </section>
  );
}

export default MePage;
