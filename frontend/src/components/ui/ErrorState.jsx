import { CircleX, RefreshCw } from 'lucide-react'
import { cn } from '../../utils/cn'
import { getErrorMessage, getErrorTitle } from '../../utils/errors'
import { Button } from './Button'
import styles from './ErrorState.module.css'

/** Inline error panel for failed loads. Shows the backend code + request id for debugging. */
export function ErrorState({ error, title, onRetry, retrying = false, compact = false, className }) {
  if (!error) return null
  return (
    <div className={cn(styles.error, compact && styles.compact, className)} role="alert">
      <span className={styles.icon}>
        <CircleX size={18} aria-hidden="true" />
      </span>
      <div className={styles.text}>
        <h3 className={styles.title}>{title || getErrorTitle(error)}</h3>
        <p className={styles.message}>{getErrorMessage(error)}</p>
        {(error.code || error.requestId) && (
          <p className={styles.meta}>
            {error.code && <code>{error.code}</code>}
            {error.status > 0 && <span>HTTP {error.status}</span>}
            {error.requestId && <span>Request ID {error.requestId}</span>}
          </p>
        )}
      </div>
      {onRetry && (
        <Button size="sm" variant="secondary" leftIcon={RefreshCw} onClick={onRetry} loading={retrying} className={styles.retry}>
          Retry
        </Button>
      )}
    </div>
  )
}
