import { useCallback, useEffect, useRef, useState } from 'react'
import { dashboardApi } from '../api/api'

const POLL_MS = 2000
const SSE_RETRY_MS = 5000

/**
 * Live dashboard state.
 * - Primary: the backend's SSE stream (`state` events).
 * - Fallback: polls GET /dashboard every 2 s while the stream is down, and retries
 *   the stream every 5 s.
 *
 * @returns {{state: object|null, link: 'connecting'|'live'|'polling'|'offline', error: Error|null, refresh: () => Promise}}
 */
export function useDashboard() {
  const [state, setState] = useState(null)
  const [link, setLink] = useState('connecting')
  const [error, setError] = useState(null)
  const pollRef = useRef(null)

  const refresh = useCallback(async () => {
    try {
      const data = await dashboardApi.get()
      setState(data)
      setError(null)
      return data
    } catch (err) {
      setError(err)
      return null
    }
  }, [])

  useEffect(() => {
    let source = null
    let retryTimer = null
    let closed = false

    const stopPolling = () => {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
    const startPolling = () => {
      if (pollRef.current) return
      pollRef.current = setInterval(async () => {
        const data = await refresh()
        setLink(data ? 'polling' : 'offline')
      }, POLL_MS)
    }

    const connect = () => {
      if (closed) return
      if (typeof EventSource === 'undefined') {
        refresh()
        startPolling()
        return
      }
      source = new EventSource(dashboardApi.streamUrl())
      source.addEventListener('state', (event) => {
        try {
          setState(JSON.parse(event.data))
          setError(null)
          setLink('live')
          stopPolling()
        } catch {
          /* ignore a malformed message; the next one replaces it */
        }
      })
      source.onerror = () => {
        source?.close()
        setLink((current) => (current === 'live' || current === 'connecting' ? 'polling' : current))
        startPolling()
        retryTimer = setTimeout(connect, SSE_RETRY_MS)
      }
    }

    connect() // the stream sends the current state as its first event
    return () => {
      closed = true
      source?.close()
      clearTimeout(retryTimer)
      stopPolling()
    }
  }, [refresh])

  return { state, link, error, refresh }
}
