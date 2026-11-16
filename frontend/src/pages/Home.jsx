import { Link, Navigate } from 'react-router-dom'
import useAuth from '../auth/useAuth.js'
import { dashboardPathForRole, TEXT } from '../constants.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import './Home.css'

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
    <div className="home-page">
      <div className="home-hero">
        {/* Left side: content */}
        <div className="home-content">
          <div className="home-badge">Organisational Knowledge Platform</div>
          <h1>Welcome back</h1>
          <p className="home-lead">
            Search and ask questions of your organisation's documents and meeting
            transcripts. Every answer cites the material it came from.
          </p>

          <div className="home-actions">
            <Link to="/login" className="btn btn--primary btn--large">
              Sign in
            </Link>
            <Link to="/register" className="btn btn--outline btn--large">
              Create an account
            </Link>
          </div>

          <div className="home-features">
            <div className="home-feature">
              <span className="home-feature__icon">🔍</span>
              <div>
                <strong>Knowledge search</strong>
                <p>Find answers across documents and meeting transcripts.</p>
              </div>
            </div>
            <div className="home-feature">
              <span className="home-feature__icon">📄</span>
              <div>
                <strong>Verified citations</strong>
                <p>Every answer links back to its source passage.</p>
              </div>
            </div>
            <div className="home-feature">
              <span className="home-feature__icon">🔐</span>
              <div>
                <strong>Role-based access</strong>
                <p>See only what your role permits.</p>
              </div>
            </div>
          </div>
        </div>

        {/* Right side: illustration / visual */}
        <div className="home-visual">
          <div className="home-visual__shape home-visual__shape--1"></div>
          <div className="home-visual__shape home-visual__shape--2"></div>
          <div className="home-visual__shape home-visual__shape--3"></div>
          <div className="home-visual__scene">
            <div className="home-visual__device">
              <div className="home-visual__screen">
                <div className="home-visual__chat">
                  <div className="home-visual__bubble home-visual__bubble--left">Hello!</div>
                  <div className="home-visual__bubble home-visual__bubble--right">How can I help?</div>
                  <div className="home-visual__bubble home-visual__bubble--left">Search our knowledge base.</div>
                </div>
                <div className="home-visual__cursor"></div>
              </div>
              <div className="home-visual__keyboard"></div>
            </div>
            <div className="home-visual__person"></div>
            <div className="home-visual__details">
              <div className="home-visual__icon home-visual__icon--globe">🌐</div>
              <div className="home-visual__icon home-visual__icon--doc">📄</div>
              <div className="home-visual__icon home-visual__icon--chat">💬</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}