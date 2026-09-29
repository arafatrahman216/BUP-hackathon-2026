import { Inbox } from 'lucide-react'
import { cn } from '../../utils/cn'
import styles from './EmptyState.module.css'

export function EmptyState({ icon: Icon = Inbox, title, description, action, compact = false, className }) {
  return (
    <div className={cn(styles.empty, compact && styles.compact, className)}>
      <span className={styles.icon}>
        <Icon size={compact ? 18 : 22} aria-hidden="true" />
      </span>
      <h3 className={styles.title}>{title}</h3>
      {description && <p className={styles.description}>{description}</p>}
      {action && <div className={styles.action}>{action}</div>}
    </div>
  )
}
