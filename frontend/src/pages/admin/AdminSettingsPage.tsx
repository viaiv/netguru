/**
 * AdminSettingsPage — gerencia configuracoes do sistema (Mailtrap email).
 */
import { FormEvent, useEffect, useState } from 'react';

import { getErrorMessage } from '../../services/api';
import { testEmail, upsertSetting } from '../../services/adminApi';
import { useAdminStore } from '../../stores/adminStore';

/** As 4 settings de email que gerenciamos. */
const EMAIL_SETTINGS_KEYS = [
  {
    key: 'email_enabled',
    label: 'Email habilitado',
    description: 'Ativar envio de emails transacionais',
    type: 'toggle' as const,
  },
  {
    key: 'mailtrap_api_key',
    label: 'Mailtrap API Key',
    description: 'Token da API do Mailtrap (Sending)',
    type: 'password' as const,
  },
  {
    key: 'mailtrap_sender_email',
    label: 'Email do remetente',
    description: 'Endereco de email usado como remetente',
    type: 'text' as const,
  },
  {
    key: 'mailtrap_sender_name',
    label: 'Nome do remetente',
    description: 'Nome exibido como remetente dos emails',
    type: 'text' as const,
  },
];

function AdminSettingsPage() {
  const { settings, settingsLoading, loadSettings } = useAdminStore();

  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  // Sync form values from loaded settings
  useEffect(() => {
    const values: Record<string, string> = {};
    for (const s of settings) {
      values[s.key] = s.is_encrypted ? '' : s.value;
    }
    setFormValues(values);
  }, [settings]);

  function getValue(key: string): string {
    return formValues[key] ?? '';
  }

  function setValue(key: string, value: string): void {
    setFormValues((prev) => ({ ...prev, [key]: value }));
  }

  function isConfigured(key: string): boolean {
    return settings.some((s) => s.key === key && s.value !== '');
  }

  async function handleSave(event: FormEvent): Promise<void> {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setMessage(null);

    try {
      for (const def of EMAIL_SETTINGS_KEYS) {
        const val = formValues[def.key];
        // Skip empty password fields (dont overwrite existing encrypted value)
        if (def.type === 'password' && !val && isConfigured(def.key)) {
          continue;
        }
        const desc = def.description;
        await upsertSetting(def.key, { value: val ?? '', description: desc });
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
        <p className="text-muted">Gerencie as configuracoes de email do sistema.</p>
      </div>

      <form className="admin-settings-form" onSubmit={handleSave}>
        <div className="admin-card">
          <h3 className="admin-card__title">Email (Mailtrap)</h3>

          {EMAIL_SETTINGS_KEYS.map((def) => (
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
          ))}

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

        {message && <div className="success-banner">{message}</div>}
        {error && <div className="error-banner">{error}</div>}
      </form>
    </section>
  );
}

export default AdminSettingsPage;
