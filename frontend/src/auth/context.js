import { createContext } from 'react'

/**
 * Shape: { user, loading, login, register, logout, refresh, trackAccountChange }.
 * `user` is the contract's user object or null; `loading` is true only until
 * the first GET /api/auth/me on page load has settled. `trackAccountChange(promise)`
 * takes the promise of a password change in flight and returns it; `logout` waits
 * for it to answer before sending anything, for at most LOGOUT_WAIT_LIMIT_MS (LOG-1,
 * FEA-11, src/auth/AuthProvider.jsx).
 */
export const AuthContext = createContext(null)
