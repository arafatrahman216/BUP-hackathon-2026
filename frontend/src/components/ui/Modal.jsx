import { X } from 'lucide-react'
import { useEffect, useId, useRef } from 'react'
import { createPortal } from 'react-dom'
import { cn } from '../../utils/cn'
import { Button } from './Button'
import styles from './Modal.module.css'

const FOCUSABLE = 'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'

/**
 * Accessible dialog: portal, Esc / backdrop to close, focus trap, focus restore,
 * body scroll lock. Put the first field's `autoFocus` or `data-autofocus` to
 * choose what gets focus; otherwise the first focusable element does.
 *
 * @param {'sm'|'md'|'lg'} size
 * @param {boolean} dismissible  false while a request is running, to block closing
 */
export function Modal({ open, onClose, title, description, footer, size = 'md', dismissible = true, className, children }) {
  const titleId = useId()
  const descId = useId()
  const panelRef = useRef(null)
  const onCloseRef = useRef(onClose)
  const dismissibleRef = useRef(dismissible)

  useEffect(() => {
    onCloseRef.current = onClose
    dismissibleRef.current = dismissible
  })

  useEffect(() => {
    if (!open) return undefined
    const previouslyFocused = document.activeElement
    const panel = panelRef.current

    // Respect a child's autoFocus; else [data-autofocus]; else the first control in
    // the body (not the header's close button); else the panel itself.
    if (panel && !panel.contains(document.activeElement)) {
      const body = panel.querySelector('[data-modal-body]')
      const target = panel.querySelector('[data-autofocus]') || body?.querySelector(FOCUSABLE) || panel
      target.focus()
    }

    const { overflow } = document.body.style
    document.body.style.overflow = 'hidden'

    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        if (dismissibleRef.current) onCloseRef.current?.()
        return
      }
      if (event.key !== 'Tab' || !panel) return
      const nodes = [...panel.querySelectorAll(FOCUSABLE)].filter((el) => !el.closest('[hidden], [inert], [aria-hidden="true"]'))
      if (!nodes.length) {
        event.preventDefault()
        return
      }
      const first = nodes[0]
      const last = nodes[nodes.length - 1]
      if (event.shiftKey && (document.activeElement === first || document.activeElement === panel)) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = overflow
      if (previouslyFocused instanceof HTMLElement) previouslyFocused.focus()
    }
  }, [open])

  if (!open) return null

  return createPortal(
    <div className={styles.root}>
      <div className={styles.backdrop} onMouseDown={() => dismissible && onClose?.()} aria-hidden="true" />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        aria-describedby={description ? descId : undefined}
        tabIndex={-1}
        className={cn(styles.panel, styles[size], className)}
      >
        {title && (
          <header className={styles.header}>
            <div>
              <h2 id={titleId} className={styles.title}>
                {title}
              </h2>
              {description && (
                <p id={descId} className={styles.description}>
                  {description}
                </p>
              )}
            </div>
            <Button variant="ghost" size="sm" iconOnly leftIcon={X} aria-label="Close dialog" onClick={onClose} disabled={!dismissible} />
          </header>
        )}
        <div className={styles.body} data-modal-body>
          {children}
        </div>
        {footer && <footer className={styles.footer}>{footer}</footer>}
      </div>
    </div>,
    document.body,
  )
}
