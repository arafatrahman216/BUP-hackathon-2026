import { cn } from '../../utils/cn'
import styles from './Badge.module.css'

/** @param {'neutral'|'accent'|'success'|'warning'|'danger'|'info'} variant */
export function Badge({ variant = 'neutral', dot = false, icon: Icon, className, children, ...props }) {
  return (
    <span className={cn(styles.badge, styles[variant], className)} {...props}>
      {dot && <span className={styles.dot} aria-hidden="true" />}
      {Icon && <Icon size={12} aria-hidden="true" />}
      {children}
    </span>
  )
}
