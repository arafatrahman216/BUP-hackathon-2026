import { createContext } from 'react'

/** Value: {token, isAuthenticated, login(token), logout()} - see AuthProvider. */
export const AuthContext = createContext(null)
