import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ToastViewport } from '../components/ui/Toast'
import { ToastContext } from './ToastContext'

const DURATIONS = { success: 4000, info: 4000, warning: 6000, error: 7000 }
let nextId = 0

export function ToastProvider({ children, max = 4 }) {
  const [toasts, setToasts] = useState([])
  const timers = useRef(new Map())

  const dismiss = useCallback((id) => {
    setToasts((list) => list.filter((t) => t.id !== id))
    clearTimeout(timers.current.get(id))
    timers.current.delete(id)
  }, [])

  const show = useCallback(
    (variant, title, options = {}) => {
      const id = ++nextId
      const duration = options.duration ?? DURATIONS[variant]
      setToasts((list) => [...list.slice(-(max - 1)), { id, variant, title, description: options.description }])
      if (duration > 0) timers.current.set(id, setTimeout(() => dismiss(id), duration))
      return id
    },
    [dismiss, max],
  )

  useEffect(() => {
    const map = timers.current
    return () => map.forEach(clearTimeout)
  }, [])

  const toast = useMemo(
    () => ({
      success: (title, options) => show('success', title, options),
      error: (title, options) => show('error', title, options),
      warning: (title, options) => show('warning', title, options),
      info: (title, options) => show('info', title, options),
    }),
    [show],
  )

  const value = useMemo(() => ({ toast, dismiss }), [toast, dismiss])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <ToastViewport toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  )
}
