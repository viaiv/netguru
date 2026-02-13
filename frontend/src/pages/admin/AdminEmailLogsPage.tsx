/**
 * AdminEmailLogsPage — tabela paginada de logs de envio de email.
 */
import { useEffect, useState } from 'react';

import DataTable from '../../components/admin/DataTable';
import type { IEmailLog } from '../../services/adminApi';
import { useAdminStore } from '../../stores/adminStore';

const STATUS_COLORS: Record<string, string> = {
  sent: '#22c55e',
  failed: '#ef4444',
  skipped: '#a3a3a3',
};

const TYPE_LABELS: Record<string, string> = {
  verification: 'Verificacao',
  password_reset: 'Reset senha',
  welcome: 'Boas-vindas',
  test: 'Teste',
};

function AdminEmailLogsPage() {
  const emailLogs = useAdminStore((s) => s.emailLogs);
  const pagination = useAdminStore((s) => s.emailLogsPagination);
  const loading = useAdminStore((s) => s.emailLogsLoading);
  const loadEmailLogs = useAdminStore((s) => s.loadEmailLogs);

  const [typeFilter, setTypeFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  useEffect(() => {
    loadEmailLogs({
      page: 1,
      email_type: typeFilter || undefined,
      status: statusFilter || undefined,
    });
  }, [loadEmailLogs, typeFilter, statusFilter]);

  function handlePageChange(page: number) {
    loadEmailLogs({
      page,
      email_type: typeFilter || undefined,
      status: statusFilter || undefined,
    });
  }

  function handleSearch(query: string) {
    loadEmailLogs({
      page: 1,
      search: query || undefined,
      email_type: typeFilter || undefined,
      status: statusFilter || undefined,
    });
  }

  const columns = [
    {
      key: 'created_at',
      header: 'Data',
      render: (e: IEmailLog) => new Date(e.created_at).toLocaleString('pt-BR'),
      width: '160px',
    },
    {
      key: 'recipient_email',
      header: 'Destinatario',
      render: (e: IEmailLog) => e.recipient_email,
    },
    {
      key: 'email_type',
      header: 'Tipo',
      render: (e: IEmailLog) => (
        <span className="chip">{TYPE_LABELS[e.email_type] ?? e.email_type}</span>
      ),
      width: '130px',
    },
    {
      key: 'subject',
      header: 'Assunto',
      render: (e: IEmailLog) => e.subject,
    },
    {
      key: 'status',
      header: 'Status',
      render: (e: IEmailLog) => (
        <span style={{ color: STATUS_COLORS[e.status] ?? '#fff', fontWeight: 600 }}>
          {e.status}
        </span>
      ),
      width: '90px',
    },
    {
      key: 'error',
      header: 'Erro',
      render: (e: IEmailLog) =>
        e.error_message ? (
          <span title={e.error_message} style={{ color: '#ef4444', fontSize: 12 }}>
            {e.error_message.length > 60
              ? e.error_message.slice(0, 60) + '...'
              : e.error_message}
          </span>
        ) : (
          '-'
        ),
    },
  ];

  return (
    <div className="admin-email-logs">
      <h2 className="admin-page-title">Email Logs</h2>

      <div className="admin-filters">
        <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
          <option value="">Todos os tipos</option>
          <option value="verification">Verificacao</option>
          <option value="password_reset">Reset senha</option>
          <option value="welcome">Boas-vindas</option>
          <option value="test">Teste</option>
        </select>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Todos os status</option>
          <option value="sent">Enviado</option>
          <option value="failed">Falhou</option>
          <option value="skipped">Pulado</option>
        </select>
      </div>

      <DataTable
        columns={columns}
        data={emailLogs}
        pagination={pagination}
        loading={loading}
        onPageChange={handlePageChange}
        onSearch={handleSearch}
        searchPlaceholder="Buscar por email..."
        rowKey={(e) => e.id}
      />
    </div>
  );
}

export default AdminEmailLogsPage;
