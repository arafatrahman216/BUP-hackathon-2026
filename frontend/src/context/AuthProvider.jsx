import { useCallback, useEffect, useMemo, useState } from 'react'
import { AUTH_UNAUTHORIZED_EVENT, clearToken, getToken, setToken } from '../api/api'
import { AuthContext } from './AuthContext'

/**
 * Keeps the auth token in React state, backed by api.js's token helpers so
 * every request picks it up automatically. The backend has no auth yet: wire a
 * real login page to `login(token)` when it does.
 */
export function AuthProvider({ children, onUnauthorized }) {
  const [token, setTokenState] = useState(() => getToken())

  const login = useCallback((newToken) => {
    setToken(newToken)
    setTokenState(newToken)
  }, [])

  const logout = useCallback(() => {
    clearToken()
    setTokenState(null)
  }, [])

  useEffect(() => {
    // api.js already cleared storage; sync React state.
    const handleUnauthorized = (event) => {
      setTokenState(null)
      onUnauthorized?.(event.detail?.error)
    }
    // Keep tabs in sync.
    const handleStorage = () => setTokenState(getToken())
    window.addEventListener(AUTH_UNAUTHORIZED_EVENT, handleUnauthorized)
    window.addEventListener('storage', handleStorage)
    return () => {
      window.removeEventListener(AUTH_UNAUTHORIZED_EVENT, handleUnauthorized)
      window.removeEventListener('storage', handleStorage)
    }
  }, [onUnauthorized])

  const value = useMemo(() => ({ token, isAuthenticated: Boolean(token), login, logout }), [token, login, logout])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
