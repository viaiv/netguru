/**
 * AdminUsersPage — paginated user list with search/filters.
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import DataTable from '../../components/admin/DataTable';
import UserRoleBadge from '../../components/admin/UserRoleBadge';
import PlanTierBadge from '../../components/admin/PlanTierBadge';
import type { IAdminUser } from '../../services/adminApi';
import { useAdminStore } from '../../stores/adminStore';

function AdminUsersPage() {
  const navigate = useNavigate();
  const users = useAdminStore((s) => s.users);
  const pagination = useAdminStore((s) => s.usersPagination);
  const loading = useAdminStore((s) => s.usersLoading);
  const loadUsers = useAdminStore((s) => s.loadUsers);

  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [tierFilter, setTierFilter] = useState('');

  useEffect(() => {
    loadUsers({ page: 1, search, role: roleFilter || undefined, plan_tier: tierFilter || undefined });
  }, [loadUsers, search, roleFilter, tierFilter]);

  function handlePageChange(page: number) {
    loadUsers({ page, search, role: roleFilter || undefined, plan_tier: tierFilter || undefined });
  }

  const columns = [
    {
      key: 'email',
      header: 'Email',
      render: (u: IAdminUser) => u.email,
    },
    {
      key: 'full_name',
      header: 'Nome',
      render: (u: IAdminUser) => u.full_name || '-',
    },
    {
      key: 'role',
      header: 'Role',
      render: (u: IAdminUser) => <UserRoleBadge role={u.role} />,
      width: '100px',
    },
    {
      key: 'plan_tier',
      header: 'Plano',
      render: (u: IAdminUser) => <PlanTierBadge tier={u.plan_tier} />,
      width: '100px',
    },
    {
      key: 'status',
      header: 'Status',
      render: (u: IAdminUser) => (
        <span className={u.is_active ? 'chip chip--active' : 'chip chip--inactive'}>
          {u.is_active ? 'Ativo' : 'Inativo'}
        </span>
      ),
      width: '80px',
    },
    {
      key: 'created_at',
      header: 'Criado em',
      render: (u: IAdminUser) => new Date(u.created_at).toLocaleDateString('pt-BR'),
      width: '110px',
    },
  ];

  return (
    <section className="admin-page">
      <div className="admin-page-header">
        <h2 className="admin-page-title">Usuarios</h2>
      </div>

      <div className="admin-filter-bar">
        <div className="admin-filter-bar__field">
          <span className="admin-filter-bar__label">Role</span>
          <select value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)}>
            <option value="">Todas</option>
            <option value="owner">Owner</option>
            <option value="admin">Admin</option>
            <option value="member">Member</option>
            <option value="viewer">Viewer</option>
          </select>
        </div>
        <div className="admin-filter-bar__field">
          <span className="admin-filter-bar__label">Plano</span>
          <select value={tierFilter} onChange={(e) => setTierFilter(e.target.value)}>
            <option value="">Todos</option>
            <option value="solo">Solo</option>
            <option value="team">Team</option>
            <option value="enterprise">Enterprise</option>
          </select>
        </div>
      </div>

      <DataTable
        columns={columns}
        data={users}
        pagination={pagination}
        loading={loading}
        searchPlaceholder="Buscar por email ou nome..."
        onSearch={(q) => setSearch(q)}
        onPageChange={handlePageChange}
        onRowClick={(u) => navigate(`/admin/users/${u.id}`)}
        rowKey={(u) => u.id}
      />
    </section>
  );
}

export default AdminUsersPage;
