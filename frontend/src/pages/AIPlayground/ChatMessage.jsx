import { Bot, RefreshCw, TriangleAlert, User } from 'lucide-react'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { cn } from '../../utils/cn'
import { getErrorMessage, getErrorTitle } from '../../utils/errors'
import { formatNumber } from '../../utils/format'
import { AttemptsTrail } from './AttemptsTrail'
import styles from './ChatMessage.module.css'

function prettyJson(text) {
  try {
    return JSON.stringify(JSON.parse(text), null, 2)
  } catch {
    return null
  }
}

export function ChatMessage({ message, onRetry }) {
  const { role } = message

  if (role === 'user') {
    return (
      <div className={cn(styles.row, styles.userRow)}>
        <div className={cn(styles.bubble, styles.user)}>{message.content}</div>
        <span className={cn(styles.avatar, styles.userAvatar)} aria-hidden="true">
          <User size={14} />
        </span>
      </div>
    )
  }

  if (message.pending) {
    return (
      <div className={styles.row}>
        <span className={styles.avatar} aria-hidden="true">
          <Bot size={14} />
        </span>
        <div className={cn(styles.bubble, styles.assistant)} aria-label="Assistant is thinking">
          <span className={styles.typing}>
            <span />
            <span />
            <span />
          </span>
        </div>
      </div>
    )
  }

  if (role === 'error') {
    const { error } = message
    const attempts = error.code === 'AI_PROVIDERS_FAILED' && Array.isArray(error.details) ? error.details : null
    return (
      <div className={styles.row}>
        <span className={cn(styles.avatar, styles.errorAvatar)} aria-hidden="true">
          <TriangleAlert size={14} />
        </span>
        <div className={cn(styles.bubble, styles.error)} role="alert">
          <p className={styles.errorTitle}>{getErrorTitle(error)}</p>
          <p>{getErrorMessage(error)}</p>
          {error.code === 'AI_PROVIDERS_FAILED' && error.message && <p className={styles.errorRaw}>{error.message}</p>}
          <div className={styles.meta}>
            <Badge variant="danger">{error.code}</Badge>
            {error.requestId && <span className={styles.metaText}>Request {error.requestId}</span>}
          </div>
          {attempts && <AttemptsTrail attempts={attempts} defaultOpen />}
          {onRetry && (
            <Button size="sm" variant="secondary" leftIcon={RefreshCw} onClick={onRetry} className={styles.retry}>
              Retry
            </Button>
          )}
        </div>
      </div>
    )
  }

  const { response } = message
  const json = message.jsonMode ? prettyJson(message.content) : null

  return (
    <div className={styles.row}>
      <span className={styles.avatar} aria-hidden="true">
        <Bot size={14} />
      </span>
      <div className={cn(styles.bubble, styles.assistant)}>
        {json ? <pre className={styles.code}>{json}</pre> : <div className={styles.text}>{message.content}</div>}
        {response && (
          <>
            <div className={styles.meta}>
              <Badge variant="accent">{response.provider}</Badge>
              <span className={cn(styles.metaText, 'mono')}>{response.model}</span>
              {response.usage && (
                <span className={styles.metaText} title={`prompt ${response.usage.prompt_tokens ?? '?'} · completion ${response.usage.completion_tokens ?? '?'}`}>
                  {formatNumber(response.usage.total_tokens)} tokens ({formatNumber(response.usage.prompt_tokens)} in / {formatNumber(response.usage.completion_tokens)} out)
                </span>
              )}
            </div>
            {response.attempts?.length > 0 && <AttemptsTrail attempts={response.attempts} defaultOpen={response.attempts.length > 1} />}
          </>
        )}
      </div>
    </div>
  )
}
