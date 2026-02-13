/**
 * AdminAuditLogPage — paginated audit log with filters.
 */
import { useEffect, useState } from 'react';

import DataTable from '../../components/admin/DataTable';
import type { IAuditLogEntry } from '../../services/adminApi';
import { useAdminStore } from '../../stores/adminStore';

function AdminAuditLogPage() {
  const auditLog = useAdminStore((s) => s.auditLog);
  const pagination = useAdminStore((s) => s.auditPagination);
  const loading = useAdminStore((s) => s.auditLoading);
  const loadAuditLog = useAdminStore((s) => s.loadAuditLog);

  const [actionFilter, setActionFilter] = useState('');
  const [targetFilter, setTargetFilter] = useState('');

  useEffect(() => {
    loadAuditLog({
      page: 1,
      action: actionFilter || undefined,
      target_type: targetFilter || undefined,
    });
  }, [loadAuditLog, actionFilter, targetFilter]);

  function handlePageChange(page: number) {
    loadAuditLog({
      page,
      action: actionFilter || undefined,
      target_type: targetFilter || undefined,
    });
  }

  const columns = [
    {
      key: 'created_at',
      header: 'Data',
      render: (e: IAuditLogEntry) => new Date(e.created_at).toLocaleString('pt-BR'),
      width: '160px',
    },
    {
      key: 'actor_email',
      header: 'Ator',
      render: (e: IAuditLogEntry) => e.actor_email || '-',
    },
    {
      key: 'action',
      header: 'Acao',
      render: (e: IAuditLogEntry) => <code>{e.action}</code>,
    },
    {
      key: 'target',
      header: 'Alvo',
      render: (e: IAuditLogEntry) =>
        e.target_type ? `${e.target_type}:${e.target_id?.slice(0, 8) || ''}` : '-',
    },
    {
      key: 'changes',
      header: 'Mudancas',
      render: (e: IAuditLogEntry) =>
        e.changes ? (
          <code className="audit-changes">{JSON.stringify(e.changes)}</code>
        ) : (
          '-'
        ),
    },
    {
      key: 'ip',
      header: 'IP',
      render: (e: IAuditLogEntry) => e.ip_address || '-',
      width: '120px',
    },
  ];

  return (
    <div className="admin-audit">
      <h2 className="admin-page-title">Audit Log</h2>

      <div className="admin-filters">
        <select value={actionFilter} onChange={(e) => setActionFilter(e.target.value)}>
          <option value="">Todas as acoes</option>
          <option value="user.updated">user.updated</option>
          <option value="plan.created">plan.created</option>
          <option value="plan.updated">plan.updated</option>
          <option value="plan.deactivated">plan.deactivated</option>
        </select>
        <select value={targetFilter} onChange={(e) => setTargetFilter(e.target.value)}>
          <option value="">Todos os alvos</option>
          <option value="user">user</option>
          <option value="plan">plan</option>
        </select>
      </div>

      <DataTable
        columns={columns}
        data={auditLog}
        pagination={pagination}
        loading={loading}
        onPageChange={handlePageChange}
        rowKey={(e) => e.id}
      />
    </div>
  );
}

export default AdminAuditLogPage;
