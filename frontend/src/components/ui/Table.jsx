import { cn } from '../../utils/cn'
import { Skeleton } from './Skeleton'
import styles from './Table.module.css'

/**
 * Data table driven by a column config.
 *
 *   <Table
 *     columns={[{ key: 'name', header: 'Name', render: (row) => row.name, width: '40%', align: 'right', hideOnMobile: true }]}
 *     rows={items} rowKey="id" loading={loading} empty={<EmptyState ... />}
 *   />
 */
export function Table({ columns, rows, rowKey = 'id', loading = false, skeletonRows = 5, empty, caption, dimmed = false, className }) {
  const showSkeleton = loading && rows.length === 0
  return (
    <div className={cn(styles.wrapper, className)}>
      <table className={cn(styles.table, dimmed && styles.dimmed)}>
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col.key} scope="col" style={{ width: col.width, textAlign: col.align }} className={cn(col.hideOnMobile && styles.hideOnMobile)}>
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {showSkeleton &&
            Array.from({ length: skeletonRows }, (_, i) => (
              <tr key={`skeleton-${i}`}>
                {columns.map((col) => (
                  <td key={col.key} className={cn(col.hideOnMobile && styles.hideOnMobile)}>
                    <Skeleton width={i % 2 ? '60%' : '80%'} />
                  </td>
                ))}
              </tr>
            ))}
          {!showSkeleton &&
            rows.map((row) => (
              <tr key={typeof rowKey === 'function' ? rowKey(row) : row[rowKey]}>
                {columns.map((col) => (
                  <td key={col.key} style={{ textAlign: col.align }} className={cn(col.hideOnMobile && styles.hideOnMobile, col.className)}>
                    {col.render ? col.render(row) : row[col.key]}
                  </td>
                ))}
              </tr>
            ))}
        </tbody>
      </table>
      {!loading && rows.length === 0 && empty}
    </div>
  )
}
