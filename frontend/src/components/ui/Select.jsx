import { ChevronDown } from 'lucide-react'
import { forwardRef, useId } from 'react'
import { cn } from '../../utils/cn'
import { Field } from './Field'
import { fieldAria } from './fieldAria'
import fieldStyles from './Field.module.css'
import styles from './Select.module.css'

/**
 * Native <select> (accessible and mobile friendly) with the app's styling.
 * @param {{value: string, label: string, disabled?: boolean}[]} options
 */
export const Select = forwardRef(function Select({ id, label, hint, error, required, options = [], className, selectClassName, children, ...props }, ref) {
  const autoId = useId()
  const selectId = id || autoId
  return (
    <Field id={selectId} label={label} hint={hint} error={error} required={required} className={className}>
      <div className={styles.wrapper}>
        <select
          ref={ref}
          id={selectId}
          required={required}
          className={cn(fieldStyles.control, styles.select, selectClassName)}
          {...fieldAria(selectId, { error, hint })}
          {...props}
        >
          {options.map((o) => (
            <option key={o.value} value={o.value} disabled={o.disabled}>
              {o.label}
            </option>
          ))}
          {children}
        </select>
        <ChevronDown size={16} className={styles.chevron} aria-hidden="true" />
      </div>
    </Field>
  )
})
