import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from './AuthProvider'

/** Every app-wide provider, in dependency order. Add new ones here. */
export function AppProviders({ children }) {
  return (
    <BrowserRouter>
      <AuthProvider>{children}</AuthProvider>
    </BrowserRouter>
  )
}
