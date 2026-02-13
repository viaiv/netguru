/**
 * AdminStripeEventsPage — tabela paginada de eventos Stripe recebidos via webhook.
 */
import { useEffect, useState } from 'react';

import DataTable from '../../components/admin/DataTable';
import type { IStripeEvent } from '../../services/adminApi';
import { useAdminStore } from '../../stores/adminStore';

const STATUS_COLORS: Record<string, string> = {
  processed: '#22c55e',
  failed: '#ef4444',
  ignored: '#a3a3a3',
};

const TYPE_LABELS: Record<string, string> = {
  'checkout.session.completed': 'Checkout',
  'customer.subscription.updated': 'Sub. Atualizada',
  'customer.subscription.deleted': 'Sub. Cancelada',
  'invoice.payment_failed': 'Pgto. Falhou',
  signature_verification_error: 'Erro Assinatura',
};

function AdminStripeEventsPage() {
  const stripeEvents = useAdminStore((s) => s.stripeEvents);
  const pagination = useAdminStore((s) => s.stripeEventsPagination);
  const loading = useAdminStore((s) => s.stripeEventsLoading);
  const loadStripeEvents = useAdminStore((s) => s.loadStripeEvents);

  const [typeFilter, setTypeFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  useEffect(() => {
    loadStripeEvents({
      page: 1,
      event_type: typeFilter || undefined,
      status: statusFilter || undefined,
    });
  }, [loadStripeEvents, typeFilter, statusFilter]);

  function handlePageChange(page: number) {
    loadStripeEvents({
      page,
      event_type: typeFilter || undefined,
      status: statusFilter || undefined,
    });
  }

  const columns = [
    {
      key: 'created_at',
      header: 'Data',
      render: (e: IStripeEvent) => new Date(e.created_at).toLocaleString('pt-BR'),
      width: '160px',
    },
    {
      key: 'event_id',
      header: 'Event ID',
      render: (e: IStripeEvent) => (
        <span
          title={e.event_id}
          style={{ fontFamily: 'monospace', fontSize: 12 }}
        >
          {e.event_id.length > 16 ? e.event_id.slice(0, 16) + '...' : e.event_id}
        </span>
      ),
      width: '160px',
    },
    {
      key: 'event_type',
      header: 'Tipo',
      render: (e: IStripeEvent) => (
        <span className="chip">
          {TYPE_LABELS[e.event_type] ?? e.event_type}
        </span>
      ),
      width: '140px',
    },
    {
      key: 'status',
      header: 'Status',
      render: (e: IStripeEvent) => (
        <span style={{ color: STATUS_COLORS[e.status] ?? '#fff', fontWeight: 600 }}>
          {e.status}
        </span>
      ),
      width: '100px',
    },
    {
      key: 'customer_id',
      header: 'Customer',
      render: (e: IStripeEvent) =>
        e.customer_id ? (
          <span style={{ fontFamily: 'monospace', fontSize: 12 }} title={e.customer_id}>
            {e.customer_id.length > 16
              ? e.customer_id.slice(0, 16) + '...'
              : e.customer_id}
          </span>
        ) : (
          '-'
        ),
    },
    {
      key: 'error',
      header: 'Erro',
      render: (e: IStripeEvent) =>
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
    <div className="admin-stripe-events">
      <h2 className="admin-page-title">Stripe Events</h2>

      <div className="admin-filters">
        <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
          <option value="">Todos os tipos</option>
          <option value="checkout.session.completed">Checkout</option>
          <option value="customer.subscription.updated">Sub. Atualizada</option>
          <option value="customer.subscription.deleted">Sub. Cancelada</option>
          <option value="invoice.payment_failed">Pgto. Falhou</option>
        </select>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Todos os status</option>
          <option value="processed">Processado</option>
          <option value="failed">Falhou</option>
          <option value="ignored">Ignorado</option>
        </select>
      </div>

      <DataTable
        columns={columns}
        data={stripeEvents}
        pagination={pagination}
        loading={loading}
        onPageChange={handlePageChange}
        rowKey={(e) => e.id}
      />
    </div>
  );
}

export default AdminStripeEventsPage;
