import { Link } from 'react-router-dom'
import useAuth from '../auth/useAuth.js'
import { APP_TITLE } from '../constants.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'

export default function Home() {
  useDocumentTitle('Alpha build')
  const { user, loading } = useAuth()

  return (
    <>
      <h1>Alpha build under construction</h1>
      <p>
        The {APP_TITLE} alpha build is under construction. Feature screens will appear here as each requirement
        is completed for the M6 gate.
      </p>
      {loading ? null : user ? (
        <p>
          You are signed in as {user.name} ({user.role}).
        </p>
      ) : (
        <p>
          <Link to="/login">Sign in</Link> or <Link to="/register">create an account</Link> to get started.
        </p>
      )}
    </>
  )
}
