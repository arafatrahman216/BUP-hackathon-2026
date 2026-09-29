import { cn } from '../../utils/cn'
import styles from './Button.module.css'
import { Spinner } from './Spinner'

/**
 * @param {'primary'|'secondary'} variant
 * @param {boolean} loading  shows a spinner and disables the button
 */
export function Button({ variant = 'secondary', loading = false, disabled, className, children, type = 'button', ...props }) {
  return (
    <button
      type={type}
      className={cn(styles.button, styles[variant], className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading && <Spinner size={14} label="Loading" />}
      {children}
    </button>
  )
}
