/**
 * AdminSettingsPage — gerencia configuracoes do sistema com abas.
 */
import { FormEvent, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { getErrorMessage } from '../../services/api';
import {
  createLlmModel,
  deleteLlmModel,
  testEmail,
  testFreeLlm,
  testR2,
  testStripe,
  updateLlmModel,
  upsertSetting,
} from '../../services/adminApi';
import type { ILlmModel, ILlmModelCreate } from '../../services/adminApi';
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

const LLM_PROVIDER_OPTIONS = [
  { value: 'google', label: 'Google (Gemini)' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic (Claude)' },
  { value: 'azure', label: 'Azure OpenAI' },
  { value: 'groq', label: 'Groq' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'openrouter', label: 'OpenRouter' },
] as const;

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
    options: [...LLM_PROVIDER_OPTIONS],
  },
  {
    key: 'free_llm_api_key',
    label: 'API Key',
    description: 'Chave de API do provedor gratuito (criptografada)',
    type: 'password',
  },
];

const PER_PROVIDER_API_KEY_SETTINGS: SettingDef[] = [
  {
    key: 'free_llm_api_key_openai',
    label: 'API Key OpenAI',
    description: 'Chave da API OpenAI para planos com default OpenAI (criptografada)',
    type: 'password',
  },
  {
    key: 'free_llm_api_key_anthropic',
    label: 'API Key Anthropic',
    description: 'Chave da API Anthropic para planos com default Anthropic (criptografada)',
    type: 'password',
  },
  {
    key: 'free_llm_api_key_google',
    label: 'API Key Google',
    description: 'Chave da API Google para planos com default Google (criptografada)',
    type: 'password',
  },
  {
    key: 'free_llm_api_key_azure',
    label: 'API Key Azure',
    description: 'Chave da API Azure para planos com default Azure (criptografada)',
    type: 'password',
  },
  {
    key: 'free_llm_api_key_groq',
    label: 'API Key Groq',
    description: 'Chave da API Groq para planos com default Groq (criptografada)',
    type: 'password',
  },
  {
    key: 'free_llm_api_key_deepseek',
    label: 'API Key DeepSeek',
    description: 'Chave da API DeepSeek para planos com default DeepSeek (criptografada)',
    type: 'password',
  },
  {
    key: 'free_llm_api_key_openrouter',
    label: 'API Key OpenRouter',
    description: 'Chave da API OpenRouter para planos com default OpenRouter (criptografada)',
    type: 'password',
  },
];

const LLM_PROVIDER_MODEL_SETTINGS_KEYS: SettingDef[] = [
  {
    key: 'llm_default_model_openai',
    label: 'Modelo default OpenAI',
    description: 'Modelo padrao para OpenAI (fallback e BYO quando nao houver override)',
    type: 'text',
  },
  {
    key: 'llm_default_model_anthropic',
    label: 'Modelo default Anthropic',
    description: 'Modelo padrao para Anthropic (fallback e BYO quando nao houver override)',
    type: 'text',
  },
  {
    key: 'llm_default_model_azure',
    label: 'Modelo default Azure OpenAI',
    description: 'Modelo padrao para Azure (fallback e BYO quando nao houver override)',
    type: 'text',
  },
  {
    key: 'llm_default_model_google',
    label: 'Modelo default Google',
    description: 'Modelo padrao para Google (fallback e BYO quando nao houver override)',
    type: 'text',
  },
  {
    key: 'llm_default_model_groq',
    label: 'Modelo default Groq',
    description: 'Modelo padrao para Groq (fallback e BYO quando nao houver override)',
    type: 'text',
  },
  {
    key: 'llm_default_model_deepseek',
    label: 'Modelo default DeepSeek',
    description: 'Modelo padrao para DeepSeek (fallback e BYO quando nao houver override)',
    type: 'text',
  },
  {
    key: 'llm_default_model_openrouter',
    label: 'Modelo default OpenRouter',
    description: 'Modelo padrao para OpenRouter (fallback e BYO quando nao houver override)',
    type: 'text',
  },
];

const LEGACY_FREE_LLM_SETTINGS_KEYS: SettingDef[] = [
  {
    key: 'free_llm_model',
    label: 'Modelo fallback legado',
    description: 'Compatibilidade com configuracao antiga (usado se o modelo por provider nao existir)',
    type: 'text',
  },
];

// ---------------------------------------------------------------------------
//  Component
// ---------------------------------------------------------------------------

const LLM_PROVIDER_LABELS: Record<string, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  google: 'Google',
  azure: 'Azure',
  groq: 'Groq',
  deepseek: 'DeepSeek',
  openrouter: 'OpenRouter',
};

function AdminSettingsPage() {
  const { settings, settingsLoading, loadSettings, llmModels, loadLlmModels } = useAdminStore();
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

  // LLM Catalog state
  const [showModelForm, setShowModelForm] = useState(false);
  const [editingModel, setEditingModel] = useState<ILlmModel | null>(null);
  const [modelForm, setModelForm] = useState<ILlmModelCreate>({
    provider: 'openai',
    model_id: '',
    display_name: '',
    is_active: true,
    sort_order: 0,
  });

  useEffect(() => {
    loadSettings();
    loadLlmModels();
  }, [loadSettings, loadLlmModels]);

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
    if (activeTab === 'llm') {
      return [
        ...FREE_LLM_SETTINGS_KEYS,
        ...PER_PROVIDER_API_KEY_SETTINGS,
        ...LLM_PROVIDER_MODEL_SETTINGS_KEYS,
        ...LEGACY_FREE_LLM_SETTINGS_KEYS,
      ];
    }
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

  function openModelCreate(): void {
    setEditingModel(null);
    setModelForm({ provider: 'openai', model_id: '', display_name: '', is_active: true, sort_order: 0 });
    setShowModelForm(true);
  }

  function openModelEdit(m: ILlmModel): void {
    setEditingModel(m);
    setModelForm({
      provider: m.provider,
      model_id: m.model_id,
      display_name: m.display_name,
      is_active: m.is_active,
      sort_order: m.sort_order,
    });
    setShowModelForm(true);
  }

  async function handleModelSave(): Promise<void> {
    setError(null);
    setMessage(null);
    try {
      if (editingModel) {
        await updateLlmModel(editingModel.id, {
          display_name: modelForm.display_name,
          is_active: modelForm.is_active,
          sort_order: modelForm.sort_order,
        });
      } else {
        await createLlmModel(modelForm);
      }
      setShowModelForm(false);
      setMessage(editingModel ? 'Modelo atualizado' : 'Modelo criado');
      await loadLlmModels();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  async function handleModelDelete(id: string): Promise<void> {
    setError(null);
    setMessage(null);
    try {
      await deleteLlmModel(id);
      setMessage('Modelo removido');
      await loadLlmModels();
    } catch (err) {
      setError(getErrorMessage(err));
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
      <div className="admin-page-header">
        <h2 className="admin-page-title">Configuracoes</h2>
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
          <>
            {/* Catalogo de Modelos */}
            <div className="admin-card" style={{ marginBottom: 24 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <h3 className="admin-card__title" style={{ margin: 0 }}>Catalogo de Modelos</h3>
                <button type="button" className="btn btn-primary" onClick={openModelCreate}>
                  Novo Modelo
                </button>
              </div>
              <p className="text-muted" style={{ marginBottom: 12 }}>
                Modelos disponiveis para uso como default por plano ou override por conversa.
              </p>
              <table style={{ width: '100%', fontSize: '0.85rem', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-color, #e2e8f0)', textAlign: 'left' }}>
                    <th style={{ padding: '8px 6px' }}>Provider</th>
                    <th style={{ padding: '8px 6px' }}>Model ID</th>
                    <th style={{ padding: '8px 6px' }}>Display Name</th>
                    <th style={{ padding: '8px 6px' }}>Ativo</th>
                    <th style={{ padding: '8px 6px' }}>Acoes</th>
                  </tr>
                </thead>
                <tbody>
                  {llmModels.map((m) => (
                    <tr key={m.id} style={{ borderBottom: '1px solid var(--border-color, #e2e8f0)', opacity: m.is_active ? 1 : 0.5 }}>
                      <td style={{ padding: '6px' }}>{LLM_PROVIDER_LABELS[m.provider] ?? m.provider}</td>
                      <td style={{ padding: '6px', fontFamily: 'monospace', fontSize: '0.8rem' }}>{m.model_id}</td>
                      <td style={{ padding: '6px' }}>{m.display_name}</td>
                      <td style={{ padding: '6px' }}>{m.is_active ? 'Sim' : 'Nao'}</td>
                      <td style={{ padding: '6px', display: 'flex', gap: 6 }}>
                        <button type="button" className="ghost-btn" onClick={() => openModelEdit(m)}>Editar</button>
                        <button type="button" className="ghost-btn ghost-btn--danger" onClick={() => void handleModelDelete(m.id)}>Remover</button>
                      </td>
                    </tr>
                  ))}
                  {llmModels.length === 0 && (
                    <tr><td colSpan={5} style={{ padding: 12, textAlign: 'center', opacity: 0.6 }}>Nenhum modelo cadastrado</td></tr>
                  )}
                </tbody>
              </table>

              {/* Inline model form */}
              {showModelForm && (
                <div style={{ marginTop: 16, padding: 16, border: '1px solid var(--border-color, #e2e8f0)', borderRadius: 8 }}>
                  <h4 style={{ marginBottom: 12 }}>{editingModel ? 'Editar Modelo' : 'Novo Modelo'}</h4>
                  <div style={{ display: 'grid', gap: 12, gridTemplateColumns: '1fr 1fr' }}>
                    <div>
                      <label className="field-label">Provider</label>
                      <select
                        value={modelForm.provider}
                        onChange={(e) => setModelForm((p) => ({ ...p, provider: e.target.value }))}
                        disabled={!!editingModel}
                      >
                        {LLM_PROVIDER_OPTIONS.map((opt) => (
                          <option key={opt.value} value={opt.value}>{opt.label}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="field-label">Model ID</label>
                      <input
                        type="text"
                        value={modelForm.model_id}
                        onChange={(e) => setModelForm((p) => ({ ...p, model_id: e.target.value }))}
                        disabled={!!editingModel}
                        placeholder="ex: gpt-4o, claude-opus-4-20250514"
                      />
                    </div>
                    <div>
                      <label className="field-label">Display Name</label>
                      <input
                        type="text"
                        value={modelForm.display_name}
                        onChange={(e) => setModelForm((p) => ({ ...p, display_name: e.target.value }))}
                        placeholder="ex: GPT-4o, Claude Opus 4"
                      />
                    </div>
                    <div>
                      <label className="field-label">Ordem</label>
                      <input
                        type="number"
                        value={modelForm.sort_order ?? 0}
                        onChange={(e) => setModelForm((p) => ({ ...p, sort_order: Number(e.target.value) }))}
                        min={0}
                      />
                    </div>
                    <div>
                      <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <input
                          type="checkbox"
                          checked={modelForm.is_active ?? true}
                          onChange={(e) => setModelForm((p) => ({ ...p, is_active: e.target.checked }))}
                        />
                        Ativo
                      </label>
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                    <button type="button" className="btn btn-primary" onClick={() => void handleModelSave()}>
                      {editingModel ? 'Salvar' : 'Criar'}
                    </button>
                    <button type="button" className="btn btn-outline" onClick={() => setShowModelForm(false)}>
                      Cancelar
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Settings */}
            <div className="admin-card">
              <h3 className="admin-card__title">Fallback Global</h3>
              <p className="text-muted" style={{ marginBottom: 12 }}>
                Configuracao global do LLM gratuito (usado quando o plano nao define um modelo default ou a chave por provider nao existe).
              </p>
              {FREE_LLM_SETTINGS_KEYS.map(renderField)}

              <h4 style={{ marginTop: 20, marginBottom: 8 }}>API Keys por Provider</h4>
              <p className="text-muted" style={{ marginBottom: 12, fontSize: 12 }}>
                Para que cada plano use o provider do seu modelo default, configure a API key correspondente abaixo.
              </p>
              {PER_PROVIDER_API_KEY_SETTINGS.map(renderField)}

              <h4 style={{ marginTop: 20, marginBottom: 8 }}>Modelos Default por Provider</h4>
              <p className="text-muted" style={{ marginBottom: 12, fontSize: 12 }}>
                Modelos usados como fallback quando nao ha override por plano ou conversa.
              </p>
              {LLM_PROVIDER_MODEL_SETTINGS_KEYS.map(renderField)}
              {LEGACY_FREE_LLM_SETTINGS_KEYS.map(renderField)}

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
          </>
        )}

        {message && <div className="success-banner">{message}</div>}
        {error && <div className="error-banner">{error}</div>}
      </form>
    </section>
  );
}

export default AdminSettingsPage;
