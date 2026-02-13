/**
 * AdminEmailTemplatesPage — gerencia templates de email transacionais.
 */
import { useEffect, useRef, useState } from 'react';

import { getErrorMessage } from '../../services/api';
import type { IEmailTemplate, IEmailTemplateUpdate } from '../../services/adminApi';
import { previewEmailTemplate, updateEmailTemplate } from '../../services/adminApi';
import { useAdminStore } from '../../stores/adminStore';

/** Labels amigaveis por tipo de email */
const TYPE_LABELS: Record<string, string> = {
  verification: 'Verificacao de Email',
  password_reset: 'Redefinir Senha',
  welcome: 'Boas-vindas',
  test: 'Email de Teste',
};

function AdminEmailTemplatesPage() {
  const { emailTemplates, emailTemplatesLoading, loadEmailTemplates } = useAdminStore();

  const [editing, setEditing] = useState<IEmailTemplate | null>(null);
  const [formSubject, setFormSubject] = useState('');
  const [formBody, setFormBody] = useState('');
  const [formActive, setFormActive] = useState(true);
  const [saving, setSaving] = useState(false);
  const [previewHtml, setPreviewHtml] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const iframeRef = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    loadEmailTemplates();
  }, [loadEmailTemplates]);

  function openEdit(template: IEmailTemplate): void {
    setEditing(template);
    setFormSubject(template.subject);
    setFormBody(template.body_html);
    setFormActive(template.is_active);
    setPreviewHtml(null);
    setMessage(null);
    setError(null);
  }

  function closeEdit(): void {
    setEditing(null);
    setPreviewHtml(null);
    setMessage(null);
    setError(null);
  }

  async function handleSave(): Promise<void> {
    if (!editing) return;
    setSaving(true);
    setError(null);
    setMessage(null);

    try {
      const data: IEmailTemplateUpdate = {};
      if (formSubject !== editing.subject) data.subject = formSubject;
      if (formBody !== editing.body_html) data.body_html = formBody;
      if (formActive !== editing.is_active) data.is_active = formActive;

      await updateEmailTemplate(editing.email_type, data);
      setMessage('Template salvo com sucesso');
      await loadEmailTemplates();
      // Atualiza o editing com os novos valores
      setEditing((prev) =>
        prev
          ? {
              ...prev,
              subject: formSubject,
              body_html: formBody,
              is_active: formActive,
            }
          : null,
      );
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function handlePreview(): Promise<void> {
    if (!editing) return;
    setPreviewLoading(true);
    setError(null);

    try {
      // Salva antes do preview para que o backend use o body mais recente
      const data: IEmailTemplateUpdate = {
        subject: formSubject,
        body_html: formBody,
        is_active: formActive,
      };
      await updateEmailTemplate(editing.email_type, data);
      await loadEmailTemplates();

      const result = await previewEmailTemplate(editing.email_type);
      setPreviewHtml(result.html);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setPreviewLoading(false);
    }
  }

  function copyVariable(name: string): void {
    navigator.clipboard.writeText(`{{${name}}}`);
  }

  if (emailTemplatesLoading && emailTemplates.length === 0) {
    return (
      <section className="admin-page">
        <p className="text-muted">Carregando templates...</p>
      </section>
    );
  }

  return (
    <section className="admin-page">
      <div className="admin-page__header">
        <h2 className="admin-page__title">Email Templates</h2>
        <p className="text-muted">
          Gerencie os templates dos emails transacionais do sistema.
        </p>
      </div>

      {/* Cards grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
          gap: 16,
        }}
      >
        {emailTemplates.map((t) => (
          <div className="admin-card" key={t.id} style={{ position: 'relative' }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 8,
              }}
            >
              <span
                style={{
                  background: 'var(--accent-soft)',
                  color: 'var(--accent-deep)',
                  padding: '2px 10px',
                  borderRadius: 999,
                  fontSize: 12,
                  fontWeight: 600,
                }}
              >
                {t.email_type}
              </span>
              <span
                style={{
                  fontSize: 11,
                  padding: '2px 8px',
                  borderRadius: 999,
                  background: t.is_active
                    ? 'var(--accent-soft)'
                    : 'rgba(var(--danger-rgb), 0.12)',
                  color: t.is_active ? 'var(--accent-deep)' : 'var(--danger)',
                  fontWeight: 600,
                }}
              >
                {t.is_active ? 'Ativo' : 'Inativo'}
              </span>
            </div>

            <h3
              className="admin-card__title"
              style={{ fontSize: 15, margin: '8px 0 4px' }}
            >
              {TYPE_LABELS[t.email_type] ?? t.email_type}
            </h3>

            <p className="text-muted" style={{ fontSize: 13, margin: '4px 0 8px' }}>
              {t.subject}
            </p>

            <p className="text-muted" style={{ fontSize: 11 }}>
              Atualizado em: {new Date(t.updated_at).toLocaleString('pt-BR')}
            </p>

            <button
              type="button"
              className="btn btn-outline"
              style={{ marginTop: 12, width: '100%' }}
              onClick={() => openEdit(t)}
            >
              Editar
            </button>
          </div>
        ))}
      </div>

      {/* Edit modal */}
      {editing && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.35)',
            zIndex: 1000,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 16,
          }}
          onClick={(e) => {
            if (e.target === e.currentTarget) closeEdit();
          }}
        >
          <div
            style={{
              background: 'var(--panel-strong)',
              borderRadius: 'var(--radius)',
              border: '1px solid var(--edge)',
              width: '100%',
              maxWidth: 800,
              maxHeight: '90vh',
              overflow: 'auto',
              padding: 24,
              boxShadow: 'var(--shadow)',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 16,
              }}
            >
              <h3 style={{ margin: 0, color: 'var(--ink)' }}>
                Editar: {TYPE_LABELS[editing.email_type] ?? editing.email_type}
              </h3>
              <button
                type="button"
                onClick={closeEdit}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--ink-soft)',
                  fontSize: 20,
                  cursor: 'pointer',
                }}
              >
                X
              </button>
            </div>

            {/* Subject */}
            <div className="field" style={{ marginBottom: 16 }}>
              <label className="field-label" htmlFor="tpl-subject">
                Assunto
              </label>
              <input
                id="tpl-subject"
                type="text"
                value={formSubject}
                onChange={(e) => setFormSubject(e.target.value)}
                style={{ width: '100%' }}
              />
            </div>

            {/* Body HTML */}
            <div className="field" style={{ marginBottom: 16 }}>
              <label className="field-label" htmlFor="tpl-body">
                Body HTML
              </label>
              <textarea
                id="tpl-body"
                value={formBody}
                onChange={(e) => setFormBody(e.target.value)}
                rows={14}
                style={{
                  width: '100%',
                  fontFamily: 'monospace',
                  fontSize: 13,
                  resize: 'vertical',
                }}
              />
            </div>

            {/* Variables */}
            {editing.variables.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <label className="field-label">Variaveis disponiveis</label>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 6 }}>
                  {editing.variables.map((v) => (
                    <button
                      key={v.name}
                      type="button"
                      title={`${v.description} — clique para copiar`}
                      onClick={() => copyVariable(v.name)}
                      style={{
                        background: 'var(--accent-soft)',
                        border: '1px solid rgba(var(--accent-rgb), 0.4)',
                        color: 'var(--accent-deep)',
                        borderRadius: 999,
                        padding: '4px 12px',
                        fontSize: 12,
                        cursor: 'pointer',
                        fontFamily: 'monospace',
                      }}
                    >
                      {'{{' + v.name + '}}'}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Active toggle */}
            <div
              className="field"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                marginBottom: 16,
              }}
            >
              <input
                id="tpl-active"
                type="checkbox"
                checked={formActive}
                onChange={(e) => setFormActive(e.target.checked)}
              />
              <label htmlFor="tpl-active" className="field-label" style={{ margin: 0 }}>
                Template ativo
              </label>
              <span className="text-muted" style={{ fontSize: 12 }}>
                (se inativo, o email usa o template padrao hardcoded)
              </span>
            </div>

            {/* Buttons */}
            <div className="button-row" style={{ gap: 12, marginBottom: 16 }}>
              <button
                type="button"
                className="btn btn-primary"
                disabled={saving}
                onClick={handleSave}
              >
                {saving ? 'Salvando...' : 'Salvar'}
              </button>
              <button
                type="button"
                className="btn btn-outline"
                disabled={previewLoading}
                onClick={handlePreview}
              >
                {previewLoading ? 'Gerando...' : 'Preview'}
              </button>
            </div>

            {message && <div className="success-banner">{message}</div>}
            {error && <div className="error-banner">{error}</div>}

            {/* Preview iframe */}
            {previewHtml && (
              <div style={{ marginTop: 16 }}>
                <label className="field-label">Preview</label>
                <iframe
                  ref={iframeRef}
                  sandbox=""
                  srcDoc={previewHtml}
                  title="Email Preview"
                  style={{
                    width: '100%',
                    height: 500,
                    border: '1px solid var(--edge)',
                    borderRadius: 12,
                    background: '#fff',
                    marginTop: 8,
                  }}
                />
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

export default AdminEmailTemplatesPage;
