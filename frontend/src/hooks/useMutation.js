import { useCallback, useEffect, useRef, useState } from 'react'
import { getErrorMessage } from '../utils/errors'
import { useToast } from './useToast'

/**
 * Wrap a write call (POST/PATCH/DELETE) with loading/error state and toasts.
 *
 *   const createItem = useMutation(itemsApi.create, { successMessage: 'Item created' })
 *   const { data, error } = await createItem.mutate(payload)
 *
 * `mutate` never throws: it resolves to {data, error}, so a form can map
 * `error.fieldErrors` without try/catch. Errors are toasted unless
 * `errorToast: false` (handy when the form shows them inline).
 *
 * @param {(...args) => Promise<any>} fn
 * @param {{
 *   onSuccess?: (data, ...args) => void,
 *   onError?: (error, ...args) => void,
 *   successMessage?: string | ((data, ...args) => string),
 *   errorToast?: boolean | ((error) => boolean),
 * }} options
 */
export function useMutation(fn, options = {}) {
  const [state, setState] = useState({ loading: false, error: null, data: null })
  const { toast } = useToast()
  const optionsRef = useRef(options)
  const fnRef = useRef(fn)

  // Always call the latest fn/options without re-creating `mutate`.
  useEffect(() => {
    optionsRef.current = options
    fnRef.current = fn
  })

  const mutate = useCallback(
    async (...args) => {
      const { onSuccess, onError, successMessage, errorToast = true } = optionsRef.current
      setState((s) => ({ ...s, loading: true, error: null }))
      try {
        const data = await fnRef.current(...args)
        setState({ loading: false, error: null, data })
        const message = typeof successMessage === 'function' ? successMessage(data, ...args) : successMessage
        if (message) toast.success(message)
        onSuccess?.(data, ...args)
        return { data, error: null }
      } catch (error) {
        setState((s) => ({ ...s, loading: false, error }))
        const shouldToast = typeof errorToast === 'function' ? errorToast(error) : errorToast
        if (shouldToast) toast.error(getErrorMessage(error), { description: error?.requestId ? `Request ID ${error.requestId}` : undefined })
        onError?.(error, ...args)
        return { data: null, error }
      }
    },
    [toast],
  )

  const reset = useCallback(() => setState({ loading: false, error: null, data: null }), [])

  return { ...state, mutate, reset }
}
