/**
 * AdminSystemMemoriesPage — curated system memories shared across users.
 */
import { FormEvent, useEffect, useState } from 'react';

import {
  createSystemMemory,
  deleteSystemMemory,
  fetchSystemMemories,
  type ISystemMemory,
  type ISystemMemoryCreate,
  type ISystemMemoryUpdate,
  updateSystemMemory,
} from '../../services/adminApi';
import { getErrorMessage } from '../../services/api';

interface IFormState {
  memoryKey: string;
  memoryValue: string;
  tags: string;
  ttlSeconds: string;
}

const INITIAL_FORM: IFormState = {
  memoryKey: '',
  memoryValue: '',
  tags: '',
  ttlSeconds: '',
};

function parseTags(raw: string): string[] | undefined {
  const tags = raw
    .split(',')
    .map((part) => part.trim().toLowerCase())
    .filter(Boolean);
  return tags.length > 0 ? tags : undefined;
}

function AdminSystemMemoriesPage() {
  const [items, setItems] = useState<ISystemMemory[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<IFormState>(INITIAL_FORM);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const isEditing = editingId !== null;

  async function loadRows(): Promise<void> {
    setLoading(true);
    setError(null);
    try {
      const rows = await fetchSystemMemories();
      setItems(rows);
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setLoading(false);
    }
  }

  function resetForm(): void {
    setForm(INITIAL_FORM);
    setEditingId(null);
  }

  function beginEdit(row: ISystemMemory): void {
    setEditingId(row.id);
    setForm({
      memoryKey: row.memory_key,
      memoryValue: row.memory_value,
      tags: row.tags?.join(', ') || '',
      ttlSeconds: row.ttl_seconds ? String(row.ttl_seconds) : '',
    });
    setError(null);
    setMessage(null);
  }

  async function handleSubmit(event: FormEvent): Promise<void> {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setMessage(null);

    const ttl = form.ttlSeconds.trim();
    const tags = parseTags(form.tags);
    try {
      if (isEditing && editingId) {
        const payload: ISystemMemoryUpdate = {
          memory_key: form.memoryKey.trim(),
          memory_value: form.memoryValue.trim(),
          tags,
          clear_ttl: ttl === '',
        };
        if (ttl !== '') {
          payload.ttl_seconds = Number(ttl);
          payload.clear_ttl = false;
        }
        await updateSystemMemory(editingId, payload);
        setMessage('Memoria de sistema atualizada.');
      } else {
        const payload: ISystemMemoryCreate = {
          memory_key: form.memoryKey.trim(),
          memory_value: form.memoryValue.trim(),
          tags,
        };
        if (ttl !== '') {
          payload.ttl_seconds = Number(ttl);
        }
        await createSystemMemory(payload);
        setMessage('Memoria de sistema criada.');
      }

      resetForm();
      await loadRows();
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(memoryId: string): Promise<void> {
    setError(null);
    setMessage(null);
    try {
      await deleteSystemMemory(memoryId);
      if (editingId === memoryId) {
        resetForm();
      }
      setMessage('Memoria de sistema removida.');
      await loadRows();
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    }
  }

  useEffect(() => {
    void loadRows();
  }, []);

  return (
    <section className="admin-page">
      <div className="admin-page-header">
        <h2 className="admin-page-title">Memorias de Sistema</h2>
        <button type="button" className="btn btn-secondary" onClick={() => void loadRows()} disabled={loading}>
          Recarregar
        </button>
      </div>

      <p className="text-muted">
        Memorias curatoriais de nivel <code>system</code> compartilhadas com todos os usuarios.
      </p>

      {error ? <div className="admin-error">{error}</div> : null}
      {message ? <p className="state-note">{message}</p> : null}

      <form className="auth-form" onSubmit={(event) => void handleSubmit(event)}>
        <div className="field">
          <label className="field-label" htmlFor="system-memory-key">Chave</label>
          <input
            id="system-memory-key"
            type="text"
            value={form.memoryKey}
            onChange={(event) => setForm((prev) => ({ ...prev, memoryKey: event.target.value }))}
            placeholder="ex: asn"
            required
          />
        </div>

        <div className="field">
          <label className="field-label" htmlFor="system-memory-value">Valor</label>
          <textarea
            id="system-memory-value"
            rows={4}
            value={form.memoryValue}
            onChange={(event) => setForm((prev) => ({ ...prev, memoryValue: event.target.value }))}
            placeholder="ex: ASN padrao para POP principal"
            required
          />
        </div>

        <div className="field">
          <label className="field-label" htmlFor="system-memory-tags">Tags (csv)</label>
          <input
            id="system-memory-tags"
            type="text"
            value={form.tags}
            onChange={(event) => setForm((prev) => ({ ...prev, tags: event.target.value }))}
            placeholder="core, ospf, producao"
          />
        </div>

        <div className="field">
          <label className="field-label" htmlFor="system-memory-ttl">TTL em segundos (opcional)</label>
          <input
            id="system-memory-ttl"
            type="number"
            min={60}
            value={form.ttlSeconds}
            onChange={(event) => setForm((prev) => ({ ...prev, ttlSeconds: event.target.value }))}
            placeholder="3600"
          />
        </div>

        <div className="button-row">
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? 'Salvando...' : isEditing ? 'Atualizar memoria' : 'Criar memoria'}
          </button>
          {isEditing ? (
            <button type="button" className="ghost-btn" onClick={resetForm}>
              Cancelar edicao
            </button>
          ) : null}
        </div>
      </form>

      {loading ? <p className="admin-loading">Carregando memorias...</p> : null}
      {!loading && items.length === 0 ? <p className="admin-empty">Nenhuma memoria de sistema ativa.</p> : null}

      {!loading && items.length > 0 ? (
        <div className="kv-grid">
          {items.map((row) => (
            <article key={row.id} className="kv-card">
              <p className="kv-label">system</p>
              <p className="kv-value">{row.memory_key}</p>
              <p>{row.memory_value}</p>
              <p className="state-note">
                origem sistema | versao {row.version}
                {row.expires_at ? ` | expira em ${new Date(row.expires_at).toLocaleString('pt-BR')}` : ''}
              </p>
              {row.tags && row.tags.length > 0 ? <p className="state-note">tags: {row.tags.join(', ')}</p> : null}
              <div className="button-row">
                <button type="button" className="btn btn-secondary" onClick={() => beginEdit(row)}>
                  Editar
                </button>
                <button type="button" className="btn btn-danger" onClick={() => void handleDelete(row.id)}>
                  Remover
                </button>
              </div>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}

export default AdminSystemMemoriesPage;
