/**
 * AdminSettingsPage — gerencia configuracoes do sistema com abas.
 */
import { FormEvent, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { getErrorMessage } from '../../services/api';
import { testEmail, testFreeLlm, testR2, testStripe, upsertSetting } from '../../services/adminApi';
import { useAdminStore } from '../../stores/adminStore';

// ---------------------------------------------------------------------------
//  Tab definitions
// ---------------------------------------------------------------------------

type SettingDef = {
  key: string;
  label: string;
  description: string;
  type: 'text' | 'password' | 'toggle' | 'select';
  options?: { value: string; label: string }[];
};

const TABS = [
  { id: 'email', label: 'Email' },
  { id: 'cloudflare', label: 'Cloudflare R2' },
  { id: 'stripe', label: 'Stripe' },
  { id: 'llm', label: 'LLM Gratuito' },
] as const;

type TabId = (typeof TABS)[number]['id'];

const EMAIL_SETTINGS_KEYS: SettingDef[] = [
  {
    key: 'email_enabled',
    label: 'Email habilitado',
    description: 'Ativar envio de emails transacionais',
    type: 'toggle',
  },
  {
    key: 'mailtrap_api_key',
    label: 'Mailtrap API Key',
    description: 'Token da API do Mailtrap (Sending)',
    type: 'password',
  },
  {
    key: 'mailtrap_sender_email',
    label: 'Email do remetente',
    description: 'Endereco de email usado como remetente',
    type: 'text',
  },
  {
    key: 'mailtrap_sender_name',
    label: 'Nome do remetente',
    description: 'Nome exibido como remetente dos emails',
    type: 'text',
  },
];

const R2_SETTINGS_KEYS: SettingDef[] = [
  {
    key: 'r2_account_id',
    label: 'Account ID',
    description: 'Account ID da Cloudflare',
    type: 'text',
  },
  {
    key: 'r2_access_key_id',
    label: 'Access Key ID',
    description: 'Chave de acesso R2 (criptografada)',
    type: 'password',
  },
  {
    key: 'r2_secret_access_key',
    label: 'Secret Access Key',
    description: 'Chave secreta R2 (criptografada)',
    type: 'password',
  },
  {
    key: 'r2_bucket_name',
    label: 'Bucket Name',
    description: 'Nome do bucket no Cloudflare R2',
    type: 'text',
  },
];

const STRIPE_SETTINGS_KEYS: SettingDef[] = [
  {
    key: 'stripe_enabled',
    label: 'Stripe habilitado',
    description: 'Ativar integracao com Stripe para pagamentos',
    type: 'toggle',
  },
  {
    key: 'stripe_secret_key',
    label: 'Secret Key',
    description: 'Chave secreta da API Stripe (criptografada)',
    type: 'password',
  },
  {
    key: 'stripe_publishable_key',
    label: 'Publishable Key',
    description: 'Chave publica da API Stripe (visivel no frontend)',
    type: 'text',
  },
  {
    key: 'stripe_webhook_secret',
    label: 'Webhook Secret',
    description: 'Segredo para validacao de webhooks Stripe (criptografado)',
    type: 'password',
  },
];

const FREE_LLM_SETTINGS_KEYS: SettingDef[] = [
  {
    key: 'free_llm_enabled',
    label: 'LLM gratuito habilitado',
    description: 'Ativar fallback gratuito para usuarios sem API key propria',
    type: 'toggle',
  },
  {
    key: 'free_llm_provider',
    label: 'Provider',
    description: 'Provedor LLM usado no fallback gratuito',
    type: 'select',
    options: [
      { value: 'google', label: 'Google (Gemini)' },
      { value: 'openai', label: 'OpenAI' },
      { value: 'anthropic', label: 'Anthropic (Claude)' },
      { value: 'azure', label: 'Azure OpenAI' },
      { value: 'groq', label: 'Groq' },
      { value: 'deepseek', label: 'DeepSeek' },
      { value: 'openrouter', label: 'OpenRouter' },
    ],
  },
  {
    key: 'free_llm_api_key',
    label: 'API Key',
    description: 'Chave de API do provedor gratuito (criptografada)',
    type: 'password',
  },
  {
    key: 'free_llm_model',
    label: 'Modelo',
    description: 'Nome do modelo (ex: gemini-2.0-flash)',
    type: 'text',
  },
];

// ---------------------------------------------------------------------------
//  Component
// ---------------------------------------------------------------------------

function AdminSettingsPage() {
  const { settings, settingsLoading, loadSettings } = useAdminStore();
  const [searchParams, setSearchParams] = useSearchParams();

  const activeTab: TabId =
    (searchParams.get('tab') as TabId) || 'email';

  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testingR2, setTestingR2] = useState(false);
  const [testingStripe, setTestingStripe] = useState(false);
  const [testingFreeLlm, setTestingFreeLlm] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  useEffect(() => {
    const values: Record<string, string> = {};
    for (const s of settings) {
      values[s.key] = s.is_encrypted ? '' : s.value;
    }
    setFormValues(values);
  }, [settings]);

  function switchTab(tab: TabId): void {
    setMessage(null);
    setError(null);
    setSearchParams({ tab });
  }

  function getValue(key: string): string {
    return formValues[key] ?? '';
  }

  function setValue(key: string, value: string): void {
    setFormValues((prev) => ({ ...prev, [key]: value }));
  }

  function isConfigured(key: string): boolean {
    return settings.some((s) => s.key === key && s.value !== '');
  }

  function currentKeys(): SettingDef[] {
    if (activeTab === 'email') return EMAIL_SETTINGS_KEYS;
    if (activeTab === 'stripe') return STRIPE_SETTINGS_KEYS;
    if (activeTab === 'llm') return FREE_LLM_SETTINGS_KEYS;
    return R2_SETTINGS_KEYS;
  }

  async function handleSave(event: FormEvent): Promise<void> {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setMessage(null);

    try {
      for (const def of currentKeys()) {
        const val = formValues[def.key];
        if (def.type === 'password' && !val && isConfigured(def.key)) {
          continue;
        }
        await upsertSetting(def.key, { value: val ?? '', description: def.description });
      }
      setMessage('Configuracoes salvas com sucesso');
      await loadSettings();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleTestEmail(): Promise<void> {
    setTesting(true);
    setError(null);
    setMessage(null);
    try {
      const result = await testEmail();
      setMessage(result.message);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setTesting(false);
    }
  }

  async function handleTestR2(): Promise<void> {
    setTestingR2(true);
    setError(null);
    setMessage(null);
    try {
      const result = await testR2();
      setMessage(result.message);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setTestingR2(false);
    }
  }

  async function handleTestStripe(): Promise<void> {
    setTestingStripe(true);
    setError(null);
    setMessage(null);
    try {
      const result = await testStripe();
      setMessage(result.message);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setTestingStripe(false);
    }
  }

  async function handleTestFreeLlm(): Promise<void> {
    setTestingFreeLlm(true);
    setError(null);
    setMessage(null);
    try {
      const result = await testFreeLlm();
      setMessage(result.message);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setTestingFreeLlm(false);
    }
  }

  // ---------------------------------------------------------------------------
  //  Field renderer
  // ---------------------------------------------------------------------------

  function renderField(def: SettingDef) {
    return (
      <div className="field" key={def.key} style={{ marginBottom: 16 }}>
        <label className="field-label" htmlFor={def.key}>
          {def.label}
        </label>

        {def.type === 'toggle' ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <input
              id={def.key}
              type="checkbox"
              checked={getValue(def.key) === 'true'}
              onChange={(e) => setValue(def.key, e.target.checked ? 'true' : 'false')}
            />
            <span className="text-muted" style={{ fontSize: 13 }}>
              {getValue(def.key) === 'true' ? 'Ativado' : 'Desativado'}
            </span>
          </div>
        ) : def.type === 'select' && def.options ? (
          <select
            id={def.key}
            value={getValue(def.key)}
            onChange={(e) => setValue(def.key, e.target.value)}
          >
            <option value="">Selecione...</option>
            {def.options.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        ) : (
          <input
            id={def.key}
            type={def.type === 'password' ? 'password' : 'text'}
            value={getValue(def.key)}
            onChange={(e) => setValue(def.key, e.target.value)}
            placeholder={
              def.type === 'password' && isConfigured(def.key)
                ? '(configurado — deixe vazio para manter)'
                : ''
            }
            autoComplete="off"
          />
        )}

        <p className="text-muted" style={{ fontSize: 12, marginTop: 4 }}>
          {def.description}
        </p>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  //  Render
  // ---------------------------------------------------------------------------

  if (settingsLoading && settings.length === 0) {
    return (
      <section className="admin-page">
        <p className="text-muted">Carregando configuracoes...</p>
      </section>
    );
  }

  return (
    <section className="admin-page">
      <div className="admin-page__header">
        <h2 className="admin-page__title">Configuracoes</h2>
        <p className="text-muted">Gerencie as configuracoes do sistema.</p>
      </div>

      {/* Tabs */}
      <div className="settings-tabs">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={`settings-tabs__item${activeTab === tab.id ? ' settings-tabs__item--active' : ''}`}
            onClick={() => switchTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <form className="admin-settings-form" onSubmit={handleSave}>
        {/* Email tab */}
        {activeTab === 'email' && (
          <div className="admin-card">
            <h3 className="admin-card__title">Email (Mailtrap)</h3>
            {EMAIL_SETTINGS_KEYS.map(renderField)}
            <div className="button-row" style={{ gap: 12 }}>
              <button type="submit" className="btn btn-primary" disabled={saving}>
                {saving ? 'Salvando...' : 'Salvar'}
              </button>
              <button
                type="button"
                className="btn btn-outline"
                disabled={testing}
                onClick={handleTestEmail}
              >
                {testing ? 'Enviando...' : 'Enviar Email de Teste'}
              </button>
            </div>
          </div>
        )}

        {/* Cloudflare R2 tab */}
        {activeTab === 'cloudflare' && (
          <div className="admin-card">
            <h3 className="admin-card__title">Armazenamento (Cloudflare R2)</h3>
            {R2_SETTINGS_KEYS.map(renderField)}
            <div className="button-row" style={{ gap: 12 }}>
              <button type="submit" className="btn btn-primary" disabled={saving}>
                {saving ? 'Salvando...' : 'Salvar'}
              </button>
              <button
                type="button"
                className="btn btn-outline"
                disabled={testingR2}
                onClick={handleTestR2}
              >
                {testingR2 ? 'Testando...' : 'Testar Conexao'}
              </button>
            </div>
          </div>
        )}

        {/* Stripe tab */}
        {activeTab === 'stripe' && (
          <div className="admin-card">
            <h3 className="admin-card__title">Pagamentos (Stripe)</h3>
            {STRIPE_SETTINGS_KEYS.map(renderField)}
            <div className="button-row" style={{ gap: 12 }}>
              <button type="submit" className="btn btn-primary" disabled={saving}>
                {saving ? 'Salvando...' : 'Salvar'}
              </button>
              <button
                type="button"
                className="btn btn-outline"
                disabled={testingStripe}
                onClick={handleTestStripe}
              >
                {testingStripe ? 'Testando...' : 'Testar Conexao'}
              </button>
            </div>
          </div>
        )}

        {/* LLM Gratuito tab */}
        {activeTab === 'llm' && (
          <div className="admin-card">
            <h3 className="admin-card__title">LLM Gratuito (Fallback)</h3>
            {FREE_LLM_SETTINGS_KEYS.map(renderField)}
            <div className="button-row" style={{ gap: 12 }}>
              <button type="submit" className="btn btn-primary" disabled={saving}>
                {saving ? 'Salvando...' : 'Salvar'}
              </button>
              <button
                type="button"
                className="btn btn-outline"
                disabled={testingFreeLlm}
                onClick={handleTestFreeLlm}
              >
                {testingFreeLlm ? 'Testando...' : 'Testar Conexao'}
              </button>
            </div>
          </div>
        )}

        {message && <div className="success-banner">{message}</div>}
        {error && <div className="error-banner">{error}</div>}
      </form>
    </section>
  );
}

export default AdminSettingsPage;
