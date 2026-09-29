import { TriangleAlert } from 'lucide-react'
import { Button } from './Button'
import styles from './ConfirmDialog.module.css'
import { Modal } from './Modal'

/** "Are you sure?" dialog. Keeps itself open (and undismissible) while `loading`. */
export function ConfirmDialog({ open, onClose, onConfirm, title = 'Are you sure?', message, confirmLabel = 'Confirm', cancelLabel = 'Cancel', variant = 'danger', loading = false }) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      size="sm"
      dismissible={!loading}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={loading} data-autofocus>
            {cancelLabel}
          </Button>
          <Button variant={variant} onClick={onConfirm} loading={loading}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className={styles.content}>
        <span className={styles[variant] || styles.icon}>
          <TriangleAlert size={18} aria-hidden="true" />
        </span>
        <div>
          <h2 className={styles.title}>{title}</h2>
          {message && <div className={styles.message}>{message}</div>}
        </div>
      </div>
    </Modal>
  )
}
