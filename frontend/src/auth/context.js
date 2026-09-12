import { createContext } from 'react'

/**
 * Shape: { user, loading, login, register, logout, refresh }.
 * `user` is the contract's user object or null; `loading` is true only until
 * the first GET /api/auth/me on page load has settled.
 */
export const AuthContext = createContext(null)
