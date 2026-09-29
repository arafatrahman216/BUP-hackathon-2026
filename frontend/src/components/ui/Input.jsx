import { forwardRef, useId } from 'react'
import { cn } from '../../utils/cn'
import { Field } from './Field'
import { fieldAria } from './fieldAria'
import fieldStyles from './Field.module.css'
import styles from './Input.module.css'

/** Text input with optional label, hint, error and leading icon. */
export const Input = forwardRef(function Input({ id, label, hint, error, required, leftIcon: LeftIcon, className, inputClassName, ...props }, ref) {
  const autoId = useId()
  const inputId = id || autoId
  return (
    <Field id={inputId} label={label} hint={hint} error={error} required={required} className={className}>
      <div className={styles.wrapper}>
        {LeftIcon && <LeftIcon size={16} className={styles.icon} aria-hidden="true" />}
        <input
          ref={ref}
          id={inputId}
          required={required}
          className={cn(fieldStyles.control, LeftIcon && styles.withIcon, inputClassName)}
          {...fieldAria(inputId, { error, hint })}
          {...props}
        />
      </div>
    </Field>
  )
})
