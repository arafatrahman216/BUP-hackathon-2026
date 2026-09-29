import { useState } from 'react'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'
import { Modal } from '../../components/ui/Modal'
import { Switch } from '../../components/ui/Switch'
import { Textarea } from '../../components/ui/Textarea'
import styles from './ItemFormModal.module.css'

const EMPTY = { name: '', description: '', price: '0', is_active: true }

function toForm(item) {
  return item ? { name: item.name, description: item.description ?? '', price: String(item.price ?? 0), is_active: item.is_active } : EMPTY
}

/** Light client-side checks; the backend is the source of truth (its 422s are mapped per field). */
function validate(values) {
  const errors = {}
  if (!values.name.trim()) errors.name = 'Name is required'
  else if (values.name.length > 255) errors.name = 'Keep it under 255 characters'
  const price = Number(values.price)
  if (values.price === '' || Number.isNaN(price)) errors.price = 'Enter a number'
  else if (price < 0) errors.price = 'Price cannot be negative'
  if (values.description.length > 5000) errors.description = 'Keep it under 5000 characters'
  return errors
}

/**
 * Create / edit form. `onSubmit(values)` must resolve to {error} (useMutation's
 * result); API field errors are shown under the matching inputs.
 */
export function ItemFormModal({ open, item, onClose, onSubmit, submitting }) {
  const isEdit = Boolean(item)
  return (
    <Modal
      open={open}
      onClose={onClose}
      dismissible={!submitting}
      title={isEdit ? 'Edit item' : 'New item'}
      description={isEdit ? `Changes are saved with PATCH /items/${item.id}.` : 'Saved with POST /items. Names must be unique.'}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form={FORM_ID} loading={submitting}>
            {isEdit ? 'Save changes' : 'Create item'}
          </Button>
        </>
      }
    >
      {/* Modal only renders children while open, so the form's state starts fresh each time. */}
      <ItemForm item={item} onSubmit={onSubmit} />
    </Modal>
  )
}

const FORM_ID = 'item-form'

function ItemForm({ item, onSubmit }) {
  const [values, setValues] = useState(() => toForm(item))
  const [errors, setErrors] = useState({})
  const [formError, setFormError] = useState(null)

  const set = (field) => (eventOrValue) => {
    const value = eventOrValue?.target ? eventOrValue.target.value : eventOrValue
    setValues((v) => ({ ...v, [field]: value }))
    if (errors[field]) setErrors(({ [field]: _removed, ...rest }) => rest)
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    const clientErrors = validate(values)
    setErrors(clientErrors)
    setFormError(null)
    if (Object.keys(clientErrors).length) return

    const payload = {
      name: values.name.trim(),
      description: values.description.trim() || null,
      price: Number(values.price),
      is_active: values.is_active,
    }
    const { error } = await onSubmit(payload)
    if (!error) return
    const fieldErrors = { ...error.fieldErrors }
    if (error.code === 'CONFLICT' && !Object.keys(fieldErrors).length) fieldErrors.name = 'An item with this name already exists'
    if (Object.keys(fieldErrors).length) setErrors(fieldErrors)
    else if (error.isValidationError || error.code === 'CONFLICT') setFormError(error.message)
  }

  return (
    <form id={FORM_ID} className={styles.form} onSubmit={handleSubmit} noValidate>
      {formError && <p className={styles.formError}>{formError}</p>}
      <Input label="Name" required value={values.name} onChange={set('name')} error={errors.name} placeholder="e.g. Mechanical keyboard" maxLength={255} autoComplete="off" data-autofocus />
      <Input
        label="Price"
        type="number"
        inputMode="decimal"
        min="0"
        step="0.01"
        value={values.price}
        onChange={set('price')}
        error={errors.price}
        hint="In USD. Must be zero or more."
      />
      <Textarea
        label="Description"
        value={values.description}
        onChange={set('description')}
        error={errors.description}
        rows={4}
        placeholder="Optional. You can also generate one with AI from the list."
        hint={`${values.description.length}/5000`}
      />
      <Switch checked={values.is_active} onChange={set('is_active')} label="Active" description="Inactive items are hidden by the “Active” filter." />
    </form>
  )
}
