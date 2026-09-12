import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { TEXT } from '../constants.js'
import useAuth from './useAuth.js'

/**
 * Sends anonymous users to /login, remembering where they were going.
 *
 * Usability only. Every protected route is authorised on the server, which
 * answers 401 without a valid session regardless of what the interface shows
 * (CLAUDE.md §6, invariant 2).
 */
export default function RequireAuth({ children }) {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) {
    return <p role="status">{TEXT.checkingSession}</p>
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  return children ?? <Outlet />
}
