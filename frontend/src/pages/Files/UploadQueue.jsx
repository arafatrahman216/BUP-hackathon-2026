import { CircleCheck, CircleX, Clock } from 'lucide-react'
import { Spinner } from '../../components/ui/Spinner'
import { getErrorMessage } from '../../utils/errors'
import { formatBytes } from '../../utils/format'
import styles from './UploadQueue.module.css'

const ICON = {
  queued: <Clock size={15} className={styles.muted} aria-label="Queued" />,
  uploading: <Spinner size={14} label="Uploading" />,
  done: <CircleCheck size={15} className={styles.ok} aria-label="Uploaded" />,
  error: <CircleX size={15} className={styles.fail} aria-label="Failed" />,
}

export function UploadQueue({ uploads, onClear }) {
  if (!uploads.length) return null
  const finished = uploads.some((u) => u.status === 'done' || u.status === 'error')
  return (
    <div className={styles.queue}>
      <div className={styles.head}>
        <span>Recent uploads</span>
        {finished && (
          <button type="button" className={styles.clear} onClick={onClear}>
            Clear
          </button>
        )}
      </div>
      <ul className={styles.list}>
        {uploads.map((u) => (
          <li key={u.id} className={styles.row}>
            <span className={styles.icon}>{ICON[u.status]}</span>
            <div className={styles.text}>
              <span className={styles.name} title={u.name}>
                {u.name}
              </span>
              {u.error ? <span className={styles.error}>{getErrorMessage(u.error)}</span> : <span className={styles.size}>{formatBytes(u.size)}</span>}
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
