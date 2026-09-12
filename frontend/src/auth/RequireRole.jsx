import { Outlet } from 'react-router-dom'
import NotPermitted from '../components/NotPermitted.jsx'
import useAuth from './useAuth.js'

/**
 * Renders the not-permitted notice for any signed-in user whose role is not
 * `role`. Place inside RequireAuth.
 *
 * Usability only. The server checks the role on every protected route and
 * answers 403 for a session whose role lacks the permission (CLAUDE.md §6,
 * invariant 2); hiding the screen here just saves the user a dead end.
 */
export default function RequireRole({ role, children }) {
  const { user } = useAuth()

  if (!user || user.role !== role) {
    return <NotPermitted />
  }

  return children ?? <Outlet />
}
