import { cn } from '../../utils/cn'
import styles from './Field.module.css'

/**
 * Label + control + hint/error. Used by Input, Textarea and Select; wrap any
 * custom control with it to get the same layout.
 */
export function Field({ id, label, hint, error, required, className, children, labelAction }) {
  return (
    <div className={cn(styles.field, className)}>
      {(label || labelAction) && (
        <div className={styles.labelRow}>
          {label && (
            <label htmlFor={id} className={styles.label}>
              {label}
              {required && <span className={styles.required} aria-hidden="true">*</span>}
            </label>
          )}
          {labelAction}
        </div>
      )}
      {children}
      {error ? (
        <p id={`${id}-error`} className={styles.error} role="alert">
          {error}
        </p>
      ) : (
        hint && (
          <p id={`${id}-hint`} className={styles.hint}>
            {hint}
          </p>
        )
      )}
    </div>
  )
}
