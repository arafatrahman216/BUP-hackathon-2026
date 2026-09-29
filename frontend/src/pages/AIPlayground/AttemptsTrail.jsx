import { ChevronRight, CircleCheck, CircleMinus, CircleX } from 'lucide-react'
import { cn } from '../../utils/cn'
import { formatDuration } from '../../utils/format'
import styles from './AttemptsTrail.module.css'

const STATUS = {
  success: { icon: CircleCheck, className: styles.success, label: 'Succeeded' },
  failed: { icon: CircleX, className: styles.failed, label: 'Failed' },
  skipped: { icon: CircleMinus, className: styles.skipped, label: 'Skipped' },
}

/** The backend's fallback trail: one row per provider it tried, in order. */
export function AttemptsTrail({ attempts, defaultOpen = false }) {
  const failed = attempts.filter((a) => a.status !== 'success').length
  return (
    <details className={styles.trail} open={defaultOpen}>
      <summary className={styles.summary}>
        <ChevronRight size={14} className={styles.chevron} aria-hidden="true" />
        {attempts.length} attempt{attempts.length === 1 ? '' : 's'}
        {failed > 0 && <span className={styles.summaryMuted}>· {failed} fell through</span>}
      </summary>
      <ol className={styles.list}>
        {attempts.map((a, i) => {
          const status = STATUS[a.status] || STATUS.skipped
          const Icon = status.icon
          return (
            <li key={`${a.provider}-${i}`} className={styles.attempt}>
              <Icon size={15} className={cn(styles.icon, status.className)} aria-label={status.label} />
              <div className={styles.body}>
                <div className={styles.line}>
                  <span className={styles.provider}>{a.provider}</span>
                  {a.model && <span className={cn(styles.model, 'mono')}>{a.model}</span>}
                  {a.latency_ms !== null && a.latency_ms !== undefined && <span className={styles.latency}>{formatDuration(a.latency_ms)}</span>}
                </div>
                {a.error && <p className={styles.error}>{a.error}</p>}
              </div>
            </li>
          )
        })}
      </ol>
    </details>
  )
}
