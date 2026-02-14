/**
 * AdminRagPage — RAG management with Stats, Global and Local tabs.
 */
import { FormEvent, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import {
  deleteRagDocument,
  fetchRagDocuments,
  fetchRagGaps,
  fetchRagGapStats,
  fetchRagStats,
  ingestRagUrl,
  reprocessRagDocument,
  uploadRagDocument,
  type IPaginationMeta,
  type IRagDocument,
  type IRagGapItem,
  type IRagGapStats,
  type IRagStats,
} from '../../services/adminApi';
import { getErrorMessage } from '../../services/api';

type TabKey = 'global' | 'local' | 'stats' | 'gaps';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'global', label: 'RAG Global' },
  { key: 'local', label: 'RAG Local' },
  { key: 'stats', label: 'Estatisticas' },
  { key: 'gaps', label: 'Lacunas' },
];

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

function formatDate(iso: string): string {
  const normalized = iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z';
  return new Date(normalized).toLocaleString('pt-BR');
}

// ---------------------------------------------------------------------------
// Stats Tab
// ---------------------------------------------------------------------------

function StatsTab({ stats, loading }: { stats: IRagStats | null; loading: boolean }) {
  if (loading) return <p className="admin-loading">Carregando estatisticas...</p>;
  if (!stats) return <p className="admin-empty">Sem dados.</p>;

  return (
    <div>
      <div className="admin-cards-grid">
        <div className="admin-stat-card">
          <span className="admin-stat-card__label">Docs Total</span>
          <span className="admin-stat-card__value">{stats.total_documents}</span>
        </div>
        <div className="admin-stat-card">
          <span className="admin-stat-card__label">Docs Global</span>
          <span className="admin-stat-card__value">{stats.global_documents}</span>
        </div>
        <div className="admin-stat-card">
          <span className="admin-stat-card__label">Docs Local</span>
          <span className="admin-stat-card__value">{stats.local_documents}</span>
        </div>
        <div className="admin-stat-card">
          <span className="admin-stat-card__label">Chunks Total</span>
          <span className="admin-stat-card__value">{stats.total_chunks}</span>
        </div>
        <div className="admin-stat-card">
          <span className="admin-stat-card__label">Chunks Global</span>
          <span className="admin-stat-card__value">{stats.global_chunks}</span>
        </div>
        <div className="admin-stat-card">
          <span className="admin-stat-card__label">Chunks Local</span>
          <span className="admin-stat-card__value">{stats.local_chunks}</span>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginTop: 24 }}>
        <div>
          <h4 style={{ marginBottom: 8 }}>Por tipo de arquivo</h4>
          {stats.by_file_type.length === 0 ? (
            <p className="text-muted">Nenhum documento.</p>
          ) : (
            <table className="admin-table">
              <thead>
                <tr><th>Tipo</th><th>Quantidade</th></tr>
              </thead>
              <tbody>
                {stats.by_file_type.map((row) => (
                  <tr key={row.file_type}>
                    <td>{row.file_type}</td>
                    <td>{row.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <div>
          <h4 style={{ marginBottom: 8 }}>Por status</h4>
          {stats.by_status.length === 0 ? (
            <p className="text-muted">Nenhum documento.</p>
          ) : (
            <table className="admin-table">
              <thead>
                <tr><th>Status</th><th>Quantidade</th></tr>
              </thead>
              <tbody>
                {stats.by_status.map((row) => (
                  <tr key={row.status}>
                    <td>{row.status}</td>
                    <td>{row.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Document Table
// ---------------------------------------------------------------------------

function DocumentTable({
  items,
  showUser,
  pagination,
  onPageChange,
  onReprocess,
  onDelete,
  actionLoading,
}: {
  items: IRagDocument[];
  showUser: boolean;
  pagination: IPaginationMeta | null;
  onPageChange: (page: number) => void;
  onReprocess: (id: string) => void;
  onDelete: (id: string) => void;
  actionLoading: string | null;
}) {
  if (items.length === 0) {
    return <p className="admin-empty">Nenhum documento encontrado.</p>;
  }

  return (
    <>
      <table className="admin-table">
        <thead>
          <tr>
            <th>Arquivo</th>
            {showUser && <th>Usuario</th>}
            <th>Tipo</th>
            <th>Tamanho</th>
            <th>Status</th>
            <th>Chunks</th>
            <th>Criado em</th>
            <th>Acoes</th>
          </tr>
        </thead>
        <tbody>
          {items.map((doc) => (
            <tr key={doc.id}>
              <td title={doc.original_filename}>
                {doc.original_filename.length > 40
                  ? doc.original_filename.slice(0, 37) + '...'
                  : doc.original_filename}
              </td>
              {showUser && <td>{doc.user_email || '-'}</td>}
              <td>{doc.file_type}</td>
              <td>{formatBytes(doc.file_size_bytes)}</td>
              <td>
                <span className={`status-badge status-badge--${doc.status}`}>
                  {doc.status}
                </span>
              </td>
              <td>{doc.chunk_count}</td>
              <td>{formatDate(doc.created_at)}</td>
              <td>
                <div className="button-row" style={{ gap: 4 }}>
                  <button
                    type="button"
                    className="btn btn-secondary btn--sm"
                    disabled={actionLoading === doc.id}
                    onClick={() => onReprocess(doc.id)}
                  >
                    Reprocessar
                  </button>
                  <button
                    type="button"
                    className="btn btn-danger btn--sm"
                    disabled={actionLoading === doc.id}
                    onClick={() => onDelete(doc.id)}
                  >
                    Deletar
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {pagination && pagination.pages > 1 && (
        <div className="admin-pagination">
          <button
            type="button"
            className="btn btn-secondary btn--sm"
            disabled={pagination.page <= 1}
            onClick={() => onPageChange(pagination.page - 1)}
          >
            Anterior
          </button>
          <span className="text-muted">
            Pagina {pagination.page} de {pagination.pages} ({pagination.total} total)
          </span>
          <button
            type="button"
            className="btn btn-secondary btn--sm"
            disabled={pagination.page >= pagination.pages}
            onClick={() => onPageChange(pagination.page + 1)}
          >
            Proxima
          </button>
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Gaps Tab
// ---------------------------------------------------------------------------

function GapsTab() {
  const [gapStats, setGapStats] = useState<IRagGapStats | null>(null);
  const [gapItems, setGapItems] = useState<IRagGapItem[]>([]);
  const [gapPagination, setGapPagination] = useState<IPaginationMeta | null>(null);
  const [gapPage, setGapPage] = useState(1);
  const [gapLoading, setGapLoading] = useState(false);
  const [statsLoading, setStatsLoading] = useState(false);
  const [toolFilter, setToolFilter] = useState<string>('');
  const [searchFilter, setSearchFilter] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  async function loadGapStats() {
    setStatsLoading(true);
    try {
      const data = await fetchRagGapStats();
      setGapStats(data);
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setStatsLoading(false);
    }
  }

  async function loadGaps(p: number = gapPage) {
    setGapLoading(true);
    setError(null);
    try {
      const params: Record<string, unknown> = { page: p, limit: 20 };
      if (toolFilter) params.tool_name = toolFilter;
      if (searchFilter.trim()) params.search = searchFilter.trim();
      const data = await fetchRagGaps(params as Parameters<typeof fetchRagGaps>[0]);
      setGapItems(data.items);
      setGapPagination(data.pagination);
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setGapLoading(false);
    }
  }

  function handleGapPageChange(newPage: number) {
    setGapPage(newPage);
    void loadGaps(newPage);
  }

  function handleFilterApply() {
    setGapPage(1);
    void loadGaps(1);
  }

  useEffect(() => {
    void loadGapStats();
    void loadGaps(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toolLabel = (name: string) =>
    name === 'search_rag_global' ? 'Global' : name === 'search_rag_local' ? 'Local' : name;

  return (
    <div>
      {error && <div className="admin-error">{error}</div>}

      {/* Stats cards */}
      {statsLoading ? (
        <p className="admin-loading">Carregando estatisticas de lacunas...</p>
      ) : gapStats ? (
        <div className="admin-cards-grid" style={{ marginBottom: 24 }}>
          <div className="admin-stat-card">
            <span className="admin-stat-card__label">Total Gaps</span>
            <span className="admin-stat-card__value">{gapStats.total_gaps}</span>
          </div>
          <div className="admin-stat-card">
            <span className="admin-stat-card__label">Global Gaps</span>
            <span className="admin-stat-card__value">{gapStats.global_gaps}</span>
          </div>
          <div className="admin-stat-card">
            <span className="admin-stat-card__label">Local Gaps</span>
            <span className="admin-stat-card__value">{gapStats.local_gaps}</span>
          </div>
        </div>
      ) : null}

      {/* Top queries table */}
      {gapStats && gapStats.top_queries.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <h4 style={{ marginBottom: 8 }}>Top Queries sem Resposta</h4>
          <table className="admin-table">
            <thead>
              <tr>
                <th>Query</th>
                <th>Ocorrencias</th>
                <th>Ultima vez</th>
              </tr>
            </thead>
            <tbody>
              {gapStats.top_queries.map((tq, idx) => (
                <tr key={idx}>
                  <td title={tq.query}>
                    {tq.query.length > 80 ? tq.query.slice(0, 77) + '...' : tq.query}
                  </td>
                  <td>{tq.count}</td>
                  <td>{formatDate(tq.last_seen)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Filters */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 16, alignItems: 'center' }}>
        <select
          value={toolFilter}
          onChange={(e) => setToolFilter(e.target.value)}
          style={{ padding: '6px 10px' }}
        >
          <option value="">Todos os tools</option>
          <option value="search_rag_global">Global</option>
          <option value="search_rag_local">Local</option>
        </select>
        <input
          type="text"
          placeholder="Buscar por query..."
          value={searchFilter}
          onChange={(e) => setSearchFilter(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleFilterApply()}
          style={{ padding: '6px 10px', minWidth: 220 }}
        />
        <button
          type="button"
          className="btn btn-secondary btn--sm"
          onClick={handleFilterApply}
        >
          Filtrar
        </button>
      </div>

      {/* Gap events table */}
      {gapLoading ? (
        <p className="admin-loading">Carregando eventos...</p>
      ) : gapItems.length === 0 ? (
        <p className="admin-empty">Nenhum gap registrado.</p>
      ) : (
        <>
          <table className="admin-table">
            <thead>
              <tr>
                <th>Query</th>
                <th>Tool</th>
                <th>Usuario</th>
                <th>Data</th>
              </tr>
            </thead>
            <tbody>
              {gapItems.map((gap) => (
                <tr key={gap.id}>
                  <td title={gap.query}>
                    {gap.query.length > 60 ? gap.query.slice(0, 57) + '...' : gap.query}
                  </td>
                  <td>{toolLabel(gap.tool_name)}</td>
                  <td>{gap.user_email || '-'}</td>
                  <td>{formatDate(gap.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {gapPagination && gapPagination.pages > 1 && (
            <div className="admin-pagination">
              <button
                type="button"
                className="btn btn-secondary btn--sm"
                disabled={gapPagination.page <= 1}
                onClick={() => handleGapPageChange(gapPagination.page - 1)}
              >
                Anterior
              </button>
              <span className="text-muted">
                Pagina {gapPagination.page} de {gapPagination.pages} ({gapPagination.total} total)
              </span>
              <button
                type="button"
                className="btn btn-secondary btn--sm"
                disabled={gapPagination.page >= gapPagination.pages}
                onClick={() => handleGapPageChange(gapPagination.page + 1)}
              >
                Proxima
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

function AdminRagPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = (searchParams.get('tab') as TabKey) || 'global';

  // Stats
  const [stats, setStats] = useState<IRagStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);

  // Document list
  const [items, setItems] = useState<IRagDocument[]>([]);
  const [pagination, setPagination] = useState<IPaginationMeta | null>(null);
  const [listLoading, setListLoading] = useState(false);
  const [page, setPage] = useState(1);

  // Forms
  const [uploading, setUploading] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [urlInput, setUrlInput] = useState('');
  const [titleInput, setTitleInput] = useState('');
  const [selectedFileName, setSelectedFileName] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // General
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  function switchTab(tab: TabKey) {
    setSearchParams({ tab });
    setError(null);
    setMessage(null);
    setPage(1);
  }

  // -- Load stats --
  async function loadStats() {
    setStatsLoading(true);
    setError(null);
    try {
      const data = await fetchRagStats();
      setStats(data);
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setStatsLoading(false);
    }
  }

  // -- Load documents --
  async function loadDocuments(p: number = page) {
    setListLoading(true);
    setError(null);
    try {
      const scope = activeTab === 'global' ? 'global' : activeTab === 'local' ? 'local' : 'all';
      const data = await fetchRagDocuments({ page: p, limit: 20, scope });
      setItems(data.items);
      setPagination(data.pagination);
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setListLoading(false);
    }
  }

  function handlePageChange(newPage: number) {
    setPage(newPage);
    void loadDocuments(newPage);
  }

  // -- Upload --
  async function handleUpload(event: FormEvent) {
    event.preventDefault();
    const files = fileRef.current?.files;
    if (!files || files.length === 0) return;

    setUploading(true);
    setError(null);
    setMessage(null);
    try {
      const result = await uploadRagDocument(files[0]);
      setMessage(`Documento "${result.filename}" enviado para processamento.`);
      if (fileRef.current) fileRef.current.value = '';
      setSelectedFileName(null);
      void loadDocuments(1);
      setPage(1);
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setUploading(false);
    }
  }

  // -- Ingest URL --
  async function handleIngestUrl(event: FormEvent) {
    event.preventDefault();
    if (!urlInput.trim()) return;

    setIngesting(true);
    setError(null);
    setMessage(null);
    try {
      const result = await ingestRagUrl({
        url: urlInput.trim(),
        title: titleInput.trim() || undefined,
      });
      setMessage(`URL ingerida: "${result.original_filename}" (${formatBytes(result.file_size_bytes)})`);
      setUrlInput('');
      setTitleInput('');
      void loadDocuments(1);
      setPage(1);
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setIngesting(false);
    }
  }

  // -- Reprocess --
  async function handleReprocess(id: string) {
    setActionLoading(id);
    setError(null);
    setMessage(null);
    try {
      const result = await reprocessRagDocument(id);
      setMessage(result.message);
      void loadDocuments();
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setActionLoading(null);
    }
  }

  // -- Delete --
  async function handleDelete(id: string) {
    if (!window.confirm('Tem certeza que deseja deletar este documento? Os embeddings serao removidos.')) {
      return;
    }
    setActionLoading(id);
    setError(null);
    setMessage(null);
    try {
      await deleteRagDocument(id);
      setMessage('Documento deletado.');
      void loadDocuments();
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setActionLoading(null);
    }
  }

  // -- Effects --
  useEffect(() => {
    if (activeTab === 'stats') {
      void loadStats();
    } else if (activeTab === 'gaps') {
      // GapsTab manages its own data loading
    } else {
      setPage(1);
      void loadDocuments(1);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  return (
    <section className="admin-page">
      <div className="admin-page-header">
        <h2 className="admin-page-title">Gestao RAG</h2>
        {(activeTab === 'global' || activeTab === 'local') && (
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => void loadDocuments()}
            disabled={listLoading}
          >
            Recarregar
          </button>
        )}
        {activeTab === 'stats' && (
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => void loadStats()}
            disabled={statsLoading}
          >
            Recarregar
          </button>
        )}
      </div>

      {/* Tabs */}
      <div className="admin-tabs" style={{ display: 'flex', gap: 0, marginBottom: 20 }}>
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            className={`admin-tab-btn ${activeTab === tab.key ? 'admin-tab-btn--active' : ''}`}
            onClick={() => switchTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {error && <div className="admin-error">{error}</div>}
      {message && <p className="state-note">{message}</p>}

      {/* Stats Tab */}
      {activeTab === 'stats' && <StatsTab stats={stats} loading={statsLoading} />}

      {/* Global Tab */}
      {activeTab === 'global' && (
        <div>
          {/* Upload form */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginBottom: 24 }}>
            <form className="auth-form" onSubmit={(e) => void handleUpload(e)}>
              <h4>Upload de arquivo</h4>
              <div className="field">
                <input
                  ref={fileRef}
                  type="file"
                  className="file-input-hidden"
                  id="rag-file-input"
                  required
                  onChange={(e) => setSelectedFileName(e.target.files?.[0]?.name ?? null)}
                />
                <div className="file-input-row">
                  <label htmlFor="rag-file-input" className="btn btn-secondary">
                    Escolher arquivo
                  </label>
                  <span className="file-input-name">
                    {selectedFileName || 'Nenhum arquivo selecionado'}
                  </span>
                </div>
              </div>
              <button type="submit" className="btn btn-primary" disabled={uploading || !selectedFileName}>
                {uploading ? 'Enviando...' : 'Upload'}
              </button>
            </form>

            <form className="auth-form" onSubmit={(e) => void handleIngestUrl(e)}>
              <h4>Ingerir URL</h4>
              <div className="field">
                <input
                  type="url"
                  placeholder="https://docs.vendor.com/..."
                  value={urlInput}
                  onChange={(e) => setUrlInput(e.target.value)}
                  required
                />
              </div>
              <div className="field">
                <input
                  type="text"
                  placeholder="Titulo (opcional)"
                  value={titleInput}
                  onChange={(e) => setTitleInput(e.target.value)}
                />
              </div>
              <button type="submit" className="btn btn-primary" disabled={ingesting}>
                {ingesting ? 'Ingerindo...' : 'Ingerir URL'}
              </button>
            </form>
          </div>

          {listLoading ? (
            <p className="admin-loading">Carregando documentos...</p>
          ) : (
            <DocumentTable
              items={items}
              showUser={false}
              pagination={pagination}
              onPageChange={handlePageChange}
              onReprocess={(id) => void handleReprocess(id)}
              onDelete={(id) => void handleDelete(id)}
              actionLoading={actionLoading}
            />
          )}
        </div>
      )}

      {/* Local Tab */}
      {activeTab === 'local' && (
        <div>
          <p className="text-muted" style={{ marginBottom: 16 }}>
            Documentos enviados por usuarios. Acoes de reprocessamento e exclusao disponiveis.
          </p>
          {listLoading ? (
            <p className="admin-loading">Carregando documentos...</p>
          ) : (
            <DocumentTable
              items={items}
              showUser={true}
              pagination={pagination}
              onPageChange={handlePageChange}
              onReprocess={(id) => void handleReprocess(id)}
              onDelete={(id) => void handleDelete(id)}
              actionLoading={actionLoading}
            />
          )}
        </div>
      )}

      {/* Gaps Tab */}
      {activeTab === 'gaps' && <GapsTab />}
    </section>
  );
}

export default AdminRagPage;
