import { useId } from 'react'
import { cn } from '../../utils/cn'
import styles from './Switch.module.css'

/** Accessible on/off toggle (role="switch"). */
export function Switch({ id, checked, onChange, label, description, disabled, size = 'md', className, ...props }) {
  const autoId = useId()
  const switchId = id || autoId
  return (
    <div className={cn(styles.row, className)}>
      <button
        id={switchId}
        type="button"
        role="switch"
        aria-checked={Boolean(checked)}
        aria-label={label ? undefined : props['aria-label']}
        aria-labelledby={label ? `${switchId}-label` : undefined}
        aria-describedby={description ? `${switchId}-desc` : undefined}
        disabled={disabled}
        onClick={() => onChange?.(!checked)}
        className={cn(styles.switch, styles[size], checked && styles.on)}
        {...props}
      >
        <span className={styles.thumb} />
      </button>
      {(label || description) && (
        <div className={styles.text}>
          {label && (
            <label id={`${switchId}-label`} htmlFor={switchId} className={styles.label}>
              {label}
            </label>
          )}
          {description && (
            <span id={`${switchId}-desc`} className={styles.description}>
              {description}
            </span>
          )}
        </div>
      )}
    </div>
  )
}
