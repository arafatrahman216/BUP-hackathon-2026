import { forwardRef } from 'react'
import { cn } from '../../utils/cn'
import styles from './Button.module.css'
import { Spinner } from './Spinner'

/**
 * @param {'primary'|'secondary'|'ghost'|'danger'|'outline'} variant
 * @param {'sm'|'md'|'lg'} size
 * @param {boolean} loading   shows a spinner, disables the button, keeps its width
 * @param {React.ElementType} leftIcon / rightIcon  lucide icon components
 * @param {boolean} iconOnly  square button; pass `aria-label`
 */
export const Button = forwardRef(function Button(
  { variant = 'secondary', size = 'md', loading = false, disabled, leftIcon: LeftIcon, rightIcon: RightIcon, iconOnly = false, fullWidth = false, className, children, type = 'button', ...props },
  ref,
) {
  const iconSize = size === 'sm' ? 14 : size === 'lg' ? 18 : 16
  return (
    <button
      ref={ref}
      type={type}
      className={cn(styles.button, styles[variant], styles[size], iconOnly && styles.iconOnly, fullWidth && styles.fullWidth, loading && styles.loading, className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading ? <Spinner size={iconSize} label="Loading" /> : LeftIcon && <LeftIcon size={iconSize} aria-hidden="true" />}
      {children && <span className={styles.label}>{children}</span>}
      {!loading && RightIcon && <RightIcon size={iconSize} aria-hidden="true" />}
    </button>
  )
})
