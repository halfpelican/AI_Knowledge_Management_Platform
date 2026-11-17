import { startTransition, useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
 * something is decided server-side on every route (CLAUDE.md §6, invariant 4);
 * the `user.role` held here only shapes what the interface offers.
 *
 * Session expiry (FR-04): if any request answers 401 while the app believes a
 * user is signed in, the user is cleared and sent to /login with a notice. Logout
 * does the same with its own notice.
 *
 * A logout waits for a password change in flight (LOG-1, the security review of PR
 * #119). The change gives this session a new key once its password hashes are done,
 * and the server makes it even if a logout has ended the old key meanwhile; the
 * change's 200 then sets the new key's cookie. A logout sent during the change would
 * end only the old key, leaving the browser signed in after "You've been logged out".
 * So the Profile page hands its change to `trackAccountChange`, and `logout` waits for
 * the change to answer, whatever the answer, before it sends anything. The logout then
 * carries the cookie that answer left, the new key's after a 200, and destroys that
 * session. A Log out pressed in another tab is not covered: tabs share the cookie, not
 * this state.
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
  // LOG-1: a promise that settles once the password change in flight has answered,
  // whatever the answer, and never rejects; null when no change is in flight.
  const accountChange = useRef(null)

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

  // Clears the user and goes to /login, where `reason` picks the notice. D-97: React
  // Router applies a navigation inside startTransition, so the user is cleared inside
  // one too, and the two render together. Cleared as an ordinary update, the user would
  // render first, at the old address, and RequireAuth's redirect from there would
  // replace this navigation and its notice.
  const signOut = useCallback(
    (reason) => {
      // A 401 from here on is not a second expiry to redirect for.
      userRef.current = null
      startTransition(() => {
        setUser(null)
        navigate('/login', { replace: true, state: { reason } })
      })
    },
    [navigate],
  )

  useEffect(
    () =>
      onUnauthorized(() => {
        // A 401 on the login form or the initial /me check is not an expiry.
        if (!userRef.current) return
        signOut('expired')
      }),
    [signOut],
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

  // LOG-1: holds `change`, the promise of a password change this browser has sent,
  // until it has answered, so that `logout` waits for it. Returns `change` itself, for
  // the caller to await as before.
  const trackAccountChange = useCallback((change) => {
    const answered = Promise.resolve(change).then(
      () => undefined,
      () => undefined,
    )
    accountChange.current = answered
    answered.then(() => {
      if (accountChange.current === answered) accountChange.current = null
    })
    return change
  }, [])

  // FR-04: on success, /login with "You've been logged out". Any other failure still
  // clears the user, and is thrown for the navigation to report.
  const logout = useCallback(async () => {
    // LOG-1: nothing is sent until a password change in flight has answered. Sent now,
    // the logout would end the key the change is replacing, and leave the new one live.
    const change = accountChange.current
    if (change) await change
    try {
      await authApi.logout()
    } catch (error) {
      // 401 means the session was already gone; that is still signed out.
      if (!(error instanceof ApiError && error.status === 401)) {
        setUser(null)
        throw error
      }
    }
    signOut('signed-out')
  }, [signOut])

  const value = useMemo(
    () => ({ user, loading, login, register, logout, refresh, trackAccountChange }),
    [user, loading, login, register, logout, refresh, trackAccountChange],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
