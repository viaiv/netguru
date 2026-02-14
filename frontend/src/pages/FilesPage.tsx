import { useEffect, useState } from 'react';

import ConfirmModal from '../components/admin/ConfirmModal';
import { getErrorMessage } from '../services/api';
import {
  deleteFile,
  downloadFile,
  fetchFiles,
  fetchStorageUsage,
  formatFileSize,
  type IFileItem,
  type IFilePagination,
  type IStorageUsage,
} from '../services/fileApi';

const FILE_TYPE_OPTIONS = [
  { value: '', label: 'Todos' },
  { value: 'pcap', label: 'PCAP' },
  { value: 'config', label: 'Config' },
  { value: 'log', label: 'Log' },
  { value: 'pdf', label: 'PDF' },
  { value: 'md', label: 'Markdown' },
];

const STATUS_CLASSES: Record<string, string> = {
  completed: 'chip chip-live',
  processing: 'chip chip-warn',
  uploaded: 'chip',
  pending_upload: 'chip',
  failed: 'chip chip-danger',
};

const STATUS_LABELS: Record<string, string> = {
  completed: 'Processado',
  processing: 'Processando',
  uploaded: 'Enviado',
  pending_upload: 'Pendente',
  failed: 'Falhou',
};

function FilesPage() {
  const [files, setFiles] = useState<IFileItem[]>([]);
  const [pagination, setPagination] = useState<IFilePagination | null>(null);
  const [storage, setStorage] = useState<IStorageUsage | null>(null);
  const [fileType, setFileType] = useState('');
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirmAction, setConfirmAction] = useState<{
    title: string;
    message: string;
    action: () => void;
  } | null>(null);

  async function loadData(): Promise<void> {
    setError(null);
    setIsLoading(true);
    try {
      const params: Record<string, string | number> = { page, limit: 20 };
      if (fileType) params.file_type = fileType;

      const [fileList, usage] = await Promise.all([
        fetchFiles(params),
        fetchStorageUsage(),
      ]);
      setFiles(fileList.files);
      setPagination(fileList.pagination);
      setStorage(usage);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, [page, fileType]);

  function handleDelete(fileId: string, filename: string): void {
    setConfirmAction({
      title: 'Excluir arquivo',
      message: `Excluir "${filename}"? Esta acao nao pode ser desfeita.`,
      action: async () => {
        setConfirmAction(null);
        try {
          await deleteFile(fileId);
          void loadData();
        } catch (err) {
          setError(getErrorMessage(err));
        }
      },
    });
  }

  async function handleDownload(fileId: string, filename: string): Promise<void> {
    try {
      const { download_url } = await downloadFile(fileId);
      const link = document.createElement('a');
      link.href = download_url;
      link.download = filename;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  function handleFilterChange(value: string): void {
    setFileType(value);
    setPage(1);
  }

  return (
    <section className="view">
      <div className="view-head">
        <p className="eyebrow">Storage</p>
        <h2 className="view-title">Meus arquivos</h2>
        <p className="view-subtitle">
          Gerencie arquivos enviados via chat. Baixe ou exclua conforme necessario.
        </p>
      </div>

      {/* Storage summary cards */}
      {storage && (
        <div className="kv-grid">
          <article className="kv-card">
            <p className="kv-label">Total de arquivos</p>
            <p className="kv-value">{storage.total_files}</p>
          </article>
          <article className="kv-card">
            <p className="kv-label">Espaco utilizado</p>
            <p className="kv-value">{formatFileSize(storage.total_bytes)}</p>
          </article>
        </div>
      )}

      {/* Filter + reload */}
      <div className="button-row">
        <select
          value={fileType}
          onChange={(e) => handleFilterChange(e.target.value)}
          style={{ maxWidth: 180 }}
        >
          {FILE_TYPE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <button type="button" className="btn btn-primary" onClick={() => void loadData()}>
          Recarregar
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}
      {isLoading && <p className="state-note">Carregando arquivos...</p>}

      {/* Files table */}
      {!isLoading && files.length === 0 && (
        <p className="state-note">Nenhum arquivo encontrado.</p>
      )}

      {!isLoading && files.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left', padding: '8px 12px' }}>Nome</th>
                <th style={{ textAlign: 'left', padding: '8px 12px' }}>Tipo</th>
                <th style={{ textAlign: 'right', padding: '8px 12px' }}>Tamanho</th>
                <th style={{ textAlign: 'center', padding: '8px 12px' }}>Status</th>
                <th style={{ textAlign: 'left', padding: '8px 12px' }}>Data</th>
                <th style={{ textAlign: 'center', padding: '8px 12px' }}>Acoes</th>
              </tr>
            </thead>
            <tbody>
              {files.map((file) => (
                <tr key={file.id}>
                  <td style={{ padding: '8px 12px', wordBreak: 'break-all' }}>
                    {file.original_filename}
                  </td>
                  <td style={{ padding: '8px 12px' }}>{file.file_type}</td>
                  <td style={{ padding: '8px 12px', textAlign: 'right' }}>
                    {formatFileSize(file.file_size_bytes)}
                  </td>
                  <td style={{ padding: '8px 12px', textAlign: 'center' }}>
                    <span className={STATUS_CLASSES[file.status] || 'chip'}>
                      {STATUS_LABELS[file.status] || file.status}
                    </span>
                  </td>
                  <td style={{ padding: '8px 12px', whiteSpace: 'nowrap' }}>
                    {new Date(file.created_at).toLocaleDateString('pt-BR')}
                  </td>
                  <td style={{ padding: '8px 12px', textAlign: 'center', whiteSpace: 'nowrap' }}>
                    <button
                      type="button"
                      className="ghost-btn"
                      title="Baixar"
                      onClick={() => void handleDownload(file.id, file.original_filename)}
                    >
                      Baixar
                    </button>
                    <button
                      type="button"
                      className="ghost-btn"
                      style={{ color: 'var(--clr-danger, #e74c3c)' }}
                      title="Excluir"
                      onClick={() => handleDelete(file.id, file.original_filename)}
                    >
                      Excluir
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {pagination && pagination.pages > 1 && (
        <div className="button-row" style={{ justifyContent: 'center', marginTop: 16 }}>
          <button
            type="button"
            className="btn"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            Anterior
          </button>
          <span className="state-note" style={{ margin: '0 12px' }}>
            Pagina {pagination.page} de {pagination.pages}
          </span>
          <button
            type="button"
            className="btn"
            disabled={page >= pagination.pages}
            onClick={() => setPage((p) => p + 1)}
          >
            Proximo
          </button>
        </div>
      )}
      <ConfirmModal
        open={!!confirmAction}
        title={confirmAction?.title || ''}
        message={confirmAction?.message || ''}
        variant="danger"
        confirmLabel="Excluir"
        onConfirm={() => confirmAction?.action()}
        onCancel={() => setConfirmAction(null)}
      />
    </section>
  );
}

export default FilesPage;
