import { FormEvent, useEffect, useState } from 'react';

import { getErrorMessage } from '../services/api';
import {
  createMemory,
  deleteMemory,
  fetchMemories,
  type ICreateMemoryPayload,
  type IMemory,
  type IUpdateMemoryPayload,
  type MemoryScope,
  updateMemory,
} from '../services/memoryApi';

interface IFormState {
  scope: MemoryScope;
  scopeName: string;
  memoryKey: string;
  memoryValue: string;
  tags: string;
  ttlSeconds: string;
}

const INITIAL_FORM: IFormState = {
  scope: 'global',
  scopeName: '',
  memoryKey: '',
  memoryValue: '',
  tags: '',
  ttlSeconds: '',
};

function formatScope(memory: IMemory): string {
  if (memory.scope === 'global') return 'global';
  return `${memory.scope}:${memory.scope_name || '-'}`;
}

function buildTags(tagsText: string): string[] | undefined {
  const tags = tagsText
    .split(',')
    .map((tag) => tag.trim().toLowerCase())
    .filter(Boolean);
  return tags.length > 0 ? tags : undefined;
}

function MemoriesPage() {
  const [memories, setMemories] = useState<IMemory[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<IFormState>(INITIAL_FORM);

  const isEditing = editingId !== null;
  const requiresScopeName = form.scope !== 'global';

  async function loadMemories(): Promise<void> {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchMemories();
      setMemories(data);
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

  function editMemory(memory: IMemory): void {
    setEditingId(memory.id);
    setForm({
      scope: memory.scope,
      scopeName: memory.scope_name || '',
      memoryKey: memory.memory_key,
      memoryValue: memory.memory_value,
      tags: memory.tags?.join(', ') || '',
      ttlSeconds: memory.ttl_seconds ? String(memory.ttl_seconds) : '',
    });
    setSuccess(null);
    setError(null);
  }

  async function submitForm(event: FormEvent): Promise<void> {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setSuccess(null);

    const ttl = form.ttlSeconds.trim();
    const tags = buildTags(form.tags);

    try {
      if (isEditing && editingId) {
        const payload: IUpdateMemoryPayload = {
          scope: form.scope,
          scope_name: form.scope === 'global' ? null : form.scopeName.trim(),
          memory_key: form.memoryKey.trim(),
          memory_value: form.memoryValue.trim(),
          tags,
          clear_ttl: ttl === '',
        };
        if (ttl !== '') {
          payload.ttl_seconds = Number(ttl);
          payload.clear_ttl = false;
        }
        await updateMemory(editingId, payload);
        setSuccess('Memoria atualizada com sucesso.');
      } else {
        const payload: ICreateMemoryPayload = {
          scope: form.scope,
          scope_name: form.scope === 'global' ? null : form.scopeName.trim(),
          memory_key: form.memoryKey.trim(),
          memory_value: form.memoryValue.trim(),
          tags,
        };
        if (ttl !== '') {
          payload.ttl_seconds = Number(ttl);
        }
        await createMemory(payload);
        setSuccess('Memoria criada com sucesso.');
      }

      resetForm();
      await loadMemories();
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setSaving(false);
    }
  }

  async function removeMemory(memoryId: string): Promise<void> {
    setError(null);
    setSuccess(null);
    try {
      await deleteMemory(memoryId);
      setSuccess('Memoria removida com sucesso.');
      if (editingId === memoryId) {
        resetForm();
      }
      await loadMemories();
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    }
  }

  useEffect(() => {
    void loadMemories();
  }, []);

  return (
    <section className="view">
      <div className="view-head">
        <p className="eyebrow">Contexto persistente</p>
        <h2 className="view-title">Memorias de rede</h2>
        <p className="view-subtitle">
          Registre fatos fixos por escopo para o agent usar automaticamente no chat.
        </p>
      </div>

      <form className="auth-form" onSubmit={(event) => void submitForm(event)}>
        <div className="field">
          <label className="field-label" htmlFor="memory-scope">Escopo</label>
          <select
            id="memory-scope"
            value={form.scope}
            onChange={(event) =>
              setForm((prev) => ({
                ...prev,
                scope: event.target.value as MemoryScope,
                scopeName: event.target.value === 'global' ? '' : prev.scopeName,
              }))
            }
          >
            <option value="global">Global</option>
            <option value="site">Site</option>
            <option value="device">Device</option>
          </select>
        </div>

        {requiresScopeName ? (
          <div className="field">
            <label className="field-label" htmlFor="memory-scope-name">
              Nome do escopo
            </label>
            <input
              id="memory-scope-name"
              type="text"
              value={form.scopeName}
              placeholder={form.scope === 'site' ? 'ex: dc-sp' : 'ex: edge-rtr-01'}
              onChange={(event) => setForm((prev) => ({ ...prev, scopeName: event.target.value }))}
              required={requiresScopeName}
            />
          </div>
        ) : null}

        <div className="field">
          <label className="field-label" htmlFor="memory-key">Chave</label>
          <input
            id="memory-key"
            type="text"
            value={form.memoryKey}
            placeholder="ex: asn"
            onChange={(event) => setForm((prev) => ({ ...prev, memoryKey: event.target.value }))}
            required
          />
        </div>

        <div className="field">
          <label className="field-label" htmlFor="memory-value">Valor</label>
          <textarea
            id="memory-value"
            rows={4}
            value={form.memoryValue}
            placeholder="ex: AS 65001 para todo edge site SP."
            onChange={(event) => setForm((prev) => ({ ...prev, memoryValue: event.target.value }))}
            required
          />
        </div>

        <div className="field">
          <label className="field-label" htmlFor="memory-tags">Tags (csv)</label>
          <input
            id="memory-tags"
            type="text"
            value={form.tags}
            placeholder="ospf, edge, producao"
            onChange={(event) => setForm((prev) => ({ ...prev, tags: event.target.value }))}
          />
        </div>

        <div className="field">
          <label className="field-label" htmlFor="memory-ttl">TTL em segundos (opcional)</label>
          <input
            id="memory-ttl"
            type="number"
            min={60}
            value={form.ttlSeconds}
            placeholder="3600"
            onChange={(event) => setForm((prev) => ({ ...prev, ttlSeconds: event.target.value }))}
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
          <button type="button" className="btn btn-secondary" onClick={() => void loadMemories()} disabled={loading}>
            Recarregar lista
          </button>
        </div>
      </form>

      {error ? <div className="error-banner">{error}</div> : null}
      {success ? <p className="state-note">{success}</p> : null}
      {loading ? <p className="state-note">Carregando memorias...</p> : null}

      {!loading && memories.length === 0 ? (
        <p className="state-note">Nenhuma memoria ativa cadastrada.</p>
      ) : null}

      {!loading && memories.length > 0 ? (
        <div className="kv-grid">
          {memories.map((memory) => (
            <article key={memory.id} className="kv-card">
              <p className="kv-label">{formatScope(memory)}</p>
              <p className="kv-value">{memory.memory_key}</p>
              <p>{memory.memory_value}</p>
              <p className="state-note">
                versao {memory.version}
                {memory.expires_at ? ` | expira em ${new Date(memory.expires_at).toLocaleString('pt-BR')}` : ''}
              </p>
              {memory.tags && memory.tags.length > 0 ? (
                <p className="state-note">tags: {memory.tags.join(', ')}</p>
              ) : null}
              <div className="button-row">
                <button type="button" className="btn btn-secondary" onClick={() => editMemory(memory)}>
                  Editar
                </button>
                <button type="button" className="btn btn-danger" onClick={() => void removeMemory(memory.id)}>
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

export default MemoriesPage;
