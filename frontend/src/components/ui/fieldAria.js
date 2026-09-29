/** aria-invalid / aria-describedby for a control rendered inside <Field>. */
export function fieldAria(id, { error, hint }) {
  return {
    'aria-invalid': error ? true : undefined,
    'aria-describedby': error ? `${id}-error` : hint ? `${id}-hint` : undefined,
  }
}
