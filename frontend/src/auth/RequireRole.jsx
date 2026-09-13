import { Navigate, Outlet } from 'react-router-dom'
import useAuth from './useAuth.js'

/**
 * Guards a route on the signed-in user's role. Place inside RequireAuth.
 *
 * FR-06 Front-End: "Unauthorised navigation attempts (e.g., manually typing an
 * admin URL) redirect to a '403 – Access Denied' page." So this redirects to
 * /403 rather than rendering a notice in place: typing /admin/roles as an
 * Employee must not leave the admin URL in the address bar as though the screen
 * were merely empty.
 *
 * `replace` keeps the refused URL out of the history, so Back returns to where
 * the user actually was rather than bouncing through the guard again.
 *
 * Usability only. The server checks the role on every protected route and
 * answers 403 for a session whose role lacks the permission (CLAUDE.md §6,
 * invariant 4); redirecting here just saves the user a dead end. The in-page
 * NotPermitted notice is still what a 403 *from the API* renders.
 */
export default function RequireRole({ role, children }) {
  const { user } = useAuth()

  if (!user || user.role !== role) {
    return <Navigate to="/403" replace />
  }

  return children ?? <Outlet />
}
