import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Run an async function and track {data, error, loading}.
 *
 *   const { data, loading, error, refetch } = useAsync(
 *     ({ signal }) => healthApi.check({ signal }),
 *     [],
 *   )
 *
 * - Re-runs whenever `deps` change (like useEffect).
 * - Cancels the in-flight request on re-run/unmount via the provided `signal`,
 *   and ignores stale responses, so fast-changing inputs never race.
 * - Keeps the previous `data` while reloading (no flicker between pages).
 *
 * @param {(ctx: {signal: AbortSignal}) => Promise<any>} fn
 * @param {any[]} deps
 * @param {{immediate?: boolean, initialData?: any}} options  immediate=false -> call `run()` yourself
 */
export function useAsync(fn, deps = [], { immediate = true, initialData = null } = {}) {
  const [state, setState] = useState({ data: initialData, error: null, loading: immediate })
  const fnRef = useRef(fn)
  const controllerRef = useRef(null)

  useEffect(() => {
    fnRef.current = fn
  })

  const run = useCallback(async () => {
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    setState((s) => ({ ...s, loading: true, error: null }))
    try {
      const data = await fnRef.current({ signal: controller.signal })
      if (!controller.signal.aborted) setState({ data, error: null, loading: false })
      return data
    } catch (error) {
      if (controller.signal.aborted || error?.name === 'AbortError') return undefined
      setState((s) => ({ ...s, error, loading: false }))
      return undefined
    }
  }, [])

  useEffect(() => {
    if (immediate) run()
    return () => controllerRef.current?.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- deps are the caller's
  }, [immediate, run, ...deps])

  const setData = useCallback((updater) => {
    setState((s) => ({ ...s, data: typeof updater === 'function' ? updater(s.data) : updater }))
  }, [])

  return { ...state, refetch: run, run, setData }
}
