import { ChevronLeft, ChevronRight } from 'lucide-react'
import { cn } from '../../utils/cn'
import { Button } from './Button'
import styles from './Pagination.module.css'

/** Compact page numbers with ellipses: 1 … 4 5 [6] 7 8 … 20 */
function pageList(page, pages) {
  if (pages <= 7) return Array.from({ length: pages }, (_, i) => i + 1)
  const list = [1]
  const start = Math.max(2, page - 1)
  const end = Math.min(pages - 1, page + 1)
  if (start > 2) list.push('…start')
  for (let p = start; p <= end; p += 1) list.push(p)
  if (end < pages - 1) list.push('…end')
  list.push(pages)
  return list
}

export function Pagination({ page, pages, total, pageSize, onPageChange, className }) {
  if (!pages || pages < 1) return null
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1
  const to = Math.min(page * pageSize, total)

  return (
    <nav className={cn(styles.pagination, className)} aria-label="Pagination">
      {total !== undefined && (
        <p className={styles.summary}>
          Showing <strong>{from}</strong>–<strong>{to}</strong> of <strong>{total}</strong>
        </p>
      )}
      <div className={styles.controls}>
        <Button size="sm" variant="ghost" iconOnly leftIcon={ChevronLeft} aria-label="Previous page" disabled={page <= 1} onClick={() => onPageChange(page - 1)} />
        {pageList(page, pages).map((p) =>
          typeof p === 'string' ? (
            <span key={p} className={styles.ellipsis} aria-hidden="true">
              …
            </span>
          ) : (
            <button
              key={p}
              type="button"
              className={cn(styles.page, p === page && styles.active)}
              aria-current={p === page ? 'page' : undefined}
              aria-label={`Page ${p}`}
              onClick={() => onPageChange(p)}
            >
              {p}
            </button>
          ),
        )}
        <Button size="sm" variant="ghost" iconOnly leftIcon={ChevronRight} aria-label="Next page" disabled={page >= pages} onClick={() => onPageChange(page + 1)} />
      </div>
    </nav>
  )
}
