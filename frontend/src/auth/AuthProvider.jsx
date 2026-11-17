import { startTransition, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import * as authApi from '../api/auth.js'
import { ApiError, onUnauthorized } from '../api/client.js'
import { LOGOUT_WAIT_LIMIT_MS } from '../constants.js'
import { AuthContext } from './context.js'

/**
 * Settles once `change` has answered, or once LOGOUT_WAIT_LIMIT_MS has passed, whichever
 * comes first, and never rejects (FEA-11). If the limit comes first, the change is marked
 * abandoned, so that its success, should it come later, ends its session too.
 */
function waitForChange(change) {
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      change.abandoned = true
      resolve()
    }, LOGOUT_WAIT_LIMIT_MS)
    change.answered.then(() => {
      clearTimeout(timer)
      resolve()
    })
  })
}

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
 *
 * The wait has an upper limit, LOGOUT_WAIT_LIMIT_MS, 15 seconds (FEA-11), so a change
 * that has stalled cannot hold FR-04's redirect. Past it, the logout goes ahead with the
 * cookie the browser holds. A change that then succeeds has set its new key's cookie
 * after the logout, which is LOG-1 again, so the provider sends one more logout for it,
 * and the session that 200 left ends too. A change refused after the limit changed
 * nothing, and nothing more is sent.
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
  // LOG-1: the password change in flight, or null when there is none. `answered` is a
  // promise that settles once the change has answered, whatever the answer, and never
  // rejects; `abandoned` is set when a logout stopped waiting for it (FEA-11).
  const accountChange = useRef(null)

  // Reads the session again. `quiet` is for a 401 that is expected because the session
  // was ended on purpose: a completed password reset ends every session of its account,
  // this browser's included (RST-UI-3). The user is then cleared where they are, without
  // the "expired" notice or a move to /login, because nothing expired. A quiet read that
  // finds the session alive keeps the user, as any read does.
  const refresh = useCallback(async ({ quiet = false } = {}) => {
    // The 401 listener below acts only while a user is held; quiet, none is held for it.
    if (quiet) userRef.current = null
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
    const entry = { answered: null, abandoned: false }
    entry.answered = Promise.resolve(change).then(
      () => {
        // FEA-11: a logout stopped waiting for this change, and it has since succeeded,
        // setting its new key's cookie after the logout. That session is ended too. A
        // failure here is the session being gone already, which is the aim.
        if (entry.abandoned) authApi.logout().catch(() => undefined)
      },
      () => undefined,
    )
    accountChange.current = entry
    entry.answered.then(() => {
      if (accountChange.current === entry) accountChange.current = null
    })
    return change
  }, [])

  // FR-04: on success, /login with "You've been logged out". Any other failure still
  // clears the user, and is thrown for the navigation to report.
  const logout = useCallback(async () => {
    // LOG-1: nothing is sent until a password change in flight has answered. Sent now,
    // the logout would end the key the change is replacing, and leave the new one live.
    // FEA-11: for at most LOGOUT_WAIT_LIMIT_MS; a change that succeeds after that is
    // logged out when it answers (trackAccountChange above).
    const change = accountChange.current
    if (change) await waitForChange(change)
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
