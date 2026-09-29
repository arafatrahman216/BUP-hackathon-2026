import { useCallback } from 'react'
import { BrowserRouter } from 'react-router-dom'
import { useToast } from '../hooks/useToast'
import { AuthProvider } from './AuthProvider'
import { ToastProvider } from './ToastProvider'

/** Every app-wide provider, in dependency order. Add new ones here. */
export function AppProviders({ children }) {
  return (
    <BrowserRouter>
      <ToastProvider>
        <AuthWithToasts>{children}</AuthWithToasts>
      </ToastProvider>
    </BrowserRouter>
  )
}

function AuthWithToasts({ children }) {
  const { toast } = useToast()
  const onUnauthorized = useCallback(() => toast.warning('Your session expired. Please sign in again.'), [toast])
  return <AuthProvider onUnauthorized={onUnauthorized}>{children}</AuthProvider>
}
