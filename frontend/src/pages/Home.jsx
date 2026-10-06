import { Link, Navigate } from 'react-router-dom'
import useAuth from '../auth/useAuth.js'
import { dashboardPathForRole, TEXT } from '../constants.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'

/**
 * The home route, `/`.
 *
 * A signed-in user is sent to their dashboard (FR-14: "the platform's entry point
 * after login"), so nobody who has signed in lands on a page that is not one.
 * Login already sends them there by role (FR-02); this covers everything else
 * that leads to `/` — the 403 page's "Return to the home page", a bookmark, the
 * address typed by hand. A visitor who is not signed in is offered sign-in and
 * registration.
 */
export default function Home() {
  useDocumentTitle(TEXT.homeHeading)
  const { user, loading } = useAuth()

  if (loading) {
    return <p role="status">{TEXT.checkingSession}</p>
  }

  if (user) {
    return <Navigate to={dashboardPathForRole(user.role)} replace />
  }

  return (
    <>
      <h1>{TEXT.homeHeading}</h1>
      <p>{TEXT.homeIntro}</p>
      <p>
        <Link to="/login">Sign in</Link> or <Link to="/register">create an account</Link> to get started.
      </p>
    </>
  )
}
