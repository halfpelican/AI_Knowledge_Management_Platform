import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import * as authApi from '../api/auth.js'
import { ApiError, onUnauthorized } from '../api/client.js'
import { AuthContext } from './context.js'

/**
 * Holds the signed-in user for the whole app.
 *
 * On load it asks GET /api/auth/me whether the session cookie is still valid.
 * Nothing is stored on the client: the cookie is HttpOnly and the server is the
 * only source of truth for who is signed in (D-21). Whether a user *may* do
 * something is decided server-side on every route (CLAUDE.md §6, invariant 2);
 * the `user.role` held here only shapes what the interface offers.
 *
 * Session expiry (FR-04): if any request answers 401 while the app believes a
 * user is signed in, the user is cleared and sent to /login with a notice.
 */
export default function AuthProvider({ children }) {
  const navigate = useNavigate()
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  // Mirror of `user` for the 401 listener, which must not re-subscribe on every change.
  const userRef = useRef(null)
  useEffect(() => {
    userRef.current = user
  }, [user])

  const refresh = useCallback(async () => {
    try {
      const me = await authApi.fetchCurrentUser()
      setUser(me)
      return me
    } catch {
      setUser(null)
      return null
    }
  }, [])

  // Initial session check against the server; nothing is read from local storage.
  useEffect(() => {
    const controller = new AbortController()
    async function check() {
      let me = null
      try {
        me = await authApi.fetchCurrentUser({ signal: controller.signal })
      } catch (error) {
        if (error?.name === 'AbortError') return
      }
      if (controller.signal.aborted) return
      setUser(me)
      setLoading(false)
    }
    check()
    return () => controller.abort()
  }, [])

  useEffect(
    () =>
      onUnauthorized(() => {
        // A 401 on the login form or the initial /me check is not an expiry.
        if (!userRef.current) return
        setUser(null)
        navigate('/login', { replace: true, state: { reason: 'expired' } })
      }),
    [navigate],
  )

  const login = useCallback(
    async (credentials) => {
      await authApi.login(credentials)
      // Reload rather than trust the login body: /me also refreshes the CSRF cookie.
      return refresh()
    },
    [refresh],
  )

  const register = useCallback((details) => authApi.register(details), [])

  const logout = useCallback(async () => {
    try {
      await authApi.logout()
    } catch (error) {
      // 401 means the session was already gone; that is still signed out.
      if (!(error instanceof ApiError && error.status === 401)) throw error
    } finally {
      setUser(null)
    }
  }, [])

  const value = useMemo(
    () => ({ user, loading, login, register, logout, refresh }),
    [user, loading, login, register, logout, refresh],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
