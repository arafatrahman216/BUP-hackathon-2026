import { CircleCheck, CircleX, Info, TriangleAlert, X } from 'lucide-react'
import { createPortal } from 'react-dom'
import { cn } from '../../utils/cn'
import styles from './Toast.module.css'

const ICONS = { success: CircleCheck, error: CircleX, warning: TriangleAlert, info: Info }

export function Toast({ variant = 'info', title, description, onDismiss }) {
  const Icon = ICONS[variant] || Info
  return (
    <div className={cn(styles.toast, styles[variant])} role={variant === 'error' ? 'alert' : 'status'}>
      <Icon size={18} className={styles.icon} aria-hidden="true" />
      <div className={styles.text}>
        <p className={styles.title}>{title}</p>
        {description && <p className={styles.description}>{description}</p>}
      </div>
      <button type="button" className={styles.close} onClick={onDismiss} aria-label="Dismiss notification">
        <X size={14} aria-hidden="true" />
      </button>
    </div>
  )
}

/** Rendered once by ToastProvider. */
export function ToastViewport({ toasts, onDismiss }) {
  return createPortal(
    <div className={styles.viewport} aria-live="polite" aria-relevant="additions">
      {toasts.map((t) => (
        <Toast key={t.id} {...t} onDismiss={() => onDismiss(t.id)} />
      ))}
    </div>,
    document.body,
  )
}
