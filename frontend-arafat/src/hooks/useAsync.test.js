import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useAsync } from './useAsync'

describe('useAsync', () => {
  it('tracks loading -> data and supports refetch', async () => {
    let n = 0
    const fn = vi.fn(async () => ++n)
    const { result } = renderHook(() => useAsync(fn, []))

    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.data).toBe(1))
    expect(result.current.loading).toBe(false)
    expect(result.current.error).toBeNull()

    await act(() => result.current.refetch())
    expect(result.current.data).toBe(2)
    expect(fn).toHaveBeenCalledTimes(2)
    expect(fn.mock.calls[0][0].signal).toBeInstanceOf(AbortSignal)
  })

  it('exposes errors and keeps previous data', async () => {
    const fn = vi.fn().mockResolvedValueOnce('first').mockRejectedValueOnce(new Error('boom'))
    const { result } = renderHook(() => useAsync(fn, []))
    await waitFor(() => expect(result.current.data).toBe('first'))

    await act(() => result.current.refetch())
    expect(result.current.error?.message).toBe('boom')
    expect(result.current.data).toBe('first')
    expect(result.current.loading).toBe(false)
  })

  it('re-runs when deps change and ignores the stale response', async () => {
    const resolvers = {}
    const fn = vi.fn(() => new Promise((resolve) => (resolvers[fn.mock.calls.length] = resolve)))
    const { result, rerender } = renderHook(({ q }) => useAsync((ctx) => fn(ctx, q), [q]), { initialProps: { q: 'a' } })

    rerender({ q: 'b' })
    expect(fn).toHaveBeenCalledTimes(2)
    expect(fn.mock.calls[0][0].signal.aborted).toBe(true) // first request cancelled

    await act(async () => {
      resolvers[1]('stale')
      resolvers[2]('fresh')
    })
    expect(result.current.data).toBe('fresh')
  })

  it('does not run until run() when immediate is false', async () => {
    const fn = vi.fn(async () => 'ok')
    const { result } = renderHook(() => useAsync(fn, [], { immediate: false }))
    expect(fn).not.toHaveBeenCalled()
    expect(result.current.loading).toBe(false)
    await act(() => result.current.run())
    expect(result.current.data).toBe('ok')
  })
})
