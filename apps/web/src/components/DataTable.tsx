import { Fragment, type ReactNode } from 'react';
import { EmptyState, ErrorState, LoadingState } from './States';

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  className?: string;
  numeric?: boolean;
  width?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  caption: string;
  loading?: boolean;
  error?: Error | null;
  emptyTitle?: string;
  emptyDetail?: string;
  /** When present, each row gets an expandable detail area. */
  renderDetail?: (row: T) => ReactNode;
  isExpanded?: (row: T) => boolean;
  onToggle?: (row: T) => void;
  isSelected?: (row: T) => boolean;
  emptyAction?: ReactNode;
}

/**
 * Dense data table with explicit loading, error and empty states.
 * Expandable rows expose a real button so the detail region is keyboard
 * reachable and announced.
 */
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  caption,
  loading = false,
  error = null,
  emptyTitle = 'No records',
  emptyDetail,
  renderDetail,
  isExpanded,
  onToggle,
  isSelected,
  emptyAction,
}: DataTableProps<T>): JSX.Element {
  if (loading) return <LoadingState />;
  if (error) return <ErrorState title="Request failed" detail={error.message} />;
  if (rows.length === 0) return <EmptyState title={emptyTitle} detail={emptyDetail} action={emptyAction} />;

  return (
    <div className="table-wrap">
      <table className="data-table">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={column.className}
                style={column.width ? { width: column.width } : undefined}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const key = rowKey(row);
            const expanded = isExpanded ? isExpanded(row) : false;
            const selected = isSelected ? isSelected(row) : false;
            return (
              <Fragment key={key}>
                <tr
                  className={[expanded ? 'is-expanded' : '', selected ? 'is-selected' : ''].filter(Boolean).join(' ')}
                >
                  {columns.map((column, columnIndex) => (
                    <td key={column.key} className={column.className}>
                      {columnIndex === 0 && renderDetail && onToggle ? (
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          aria-expanded={expanded}
                          aria-label={`${expanded ? 'Collapse' : 'Expand'} details for ${key}`}
                          onClick={() => onToggle(row)}
                          style={{ marginRight: 6 }}
                        >
                          {expanded ? '▾' : '▸'}
                        </button>
                      ) : null}
                      {column.render(row)}
                    </td>
                  ))}
                </tr>
                {expanded && renderDetail ? (
                  <tr className="detail-row">
                    <td colSpan={columns.length}>{renderDetail(row)}</td>
                  </tr>
                ) : null}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
