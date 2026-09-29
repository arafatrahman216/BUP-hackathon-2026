import { forwardRef, useId } from 'react'
import { cn } from '../../utils/cn'
import { Field } from './Field'
import { fieldAria } from './fieldAria'
import fieldStyles from './Field.module.css'
import styles from './Textarea.module.css'

export const Textarea = forwardRef(function Textarea({ id, label, hint, error, required, className, textareaClassName, rows = 4, labelAction, ...props }, ref) {
  const autoId = useId()
  const inputId = id || autoId
  return (
    <Field id={inputId} label={label} hint={hint} error={error} required={required} className={className} labelAction={labelAction}>
      <textarea
        ref={ref}
        id={inputId}
        rows={rows}
        required={required}
        className={cn(fieldStyles.control, styles.textarea, textareaClassName)}
        {...fieldAria(inputId, { error, hint })}
        {...props}
      />
    </Field>
  )
})
