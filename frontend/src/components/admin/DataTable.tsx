/**
 * DataTable — generic paginated table with search.
 */
import { useState } from 'react';

import type { IPaginationMeta } from '../../services/adminApi';

interface IColumn<T> {
  key: string;
  header: string;
  render: (row: T) => React.ReactNode;
  width?: string;
}

interface IDataTableProps<T> {
  columns: IColumn<T>[];
  data: T[];
  pagination?: IPaginationMeta | null;
  loading?: boolean;
  searchPlaceholder?: string;
  onSearch?: (query: string) => void;
  onPageChange?: (page: number) => void;
  onRowClick?: (row: T) => void;
  rowKey: (row: T) => string;
}

function DataTable<T>({
  columns,
  data,
  pagination,
  loading,
  searchPlaceholder = 'Buscar...',
  onSearch,
  onPageChange,
  onRowClick,
  rowKey,
}: IDataTableProps<T>) {
  const [searchTerm, setSearchTerm] = useState('');

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    onSearch?.(searchTerm);
  }

  return (
    <div className="data-table">
      {onSearch && (
        <form className="data-table__search" onSubmit={handleSearch}>
          <input
            type="text"
            className="data-table__input"
            placeholder={searchPlaceholder}
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
          <button type="submit" className="data-table__search-btn">
            Buscar
          </button>
        </form>
      )}

      <div className="data-table__wrapper">
        <table className="data-table__table">
          <thead>
            <tr>
              {columns.map((col) => (
                <th key={col.key} style={col.width ? { width: col.width } : undefined}>
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={columns.length} className="data-table__loading">
                  Carregando...
                </td>
              </tr>
            ) : data.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="data-table__empty">
                  Nenhum resultado encontrado.
                </td>
              </tr>
            ) : (
              data.map((row) => (
                <tr
                  key={rowKey(row)}
                  className={onRowClick ? 'data-table__row--clickable' : ''}
                  onClick={() => onRowClick?.(row)}
                >
                  {columns.map((col) => (
                    <td key={col.key}>{col.render(row)}</td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {pagination && pagination.pages > 1 && (
        <div className="data-table__pagination">
          <button
            disabled={pagination.page <= 1}
            onClick={() => onPageChange?.(pagination.page - 1)}
          >
            Anterior
          </button>
          <span className="data-table__page-info">
            Pagina {pagination.page} de {pagination.pages} ({pagination.total} total)
          </span>
          <button
            disabled={pagination.page >= pagination.pages}
            onClick={() => onPageChange?.(pagination.page + 1)}
          >
            Proxima
          </button>
        </div>
      )}
    </div>
  );
}

export default DataTable;
