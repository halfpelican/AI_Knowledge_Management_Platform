import { Link, Navigate } from 'react-router-dom'
import useAuth from '../auth/useAuth.js'
import { APP_TITLE, dashboardPathForRole, TEXT } from '../constants.js'
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
 * registration (FR-02, FR-01).
 *
 * The page is PR #119's design (Sagarika Dey): the offer and three features on
 * the left, an illustration on the right. Every word comes from TEXT. The emoji
 * beside each feature and the whole illustration are decoration, so both are
 * aria-hidden (WCAG 2.1 SC 1.1.1): each feature's words say what its glyph shows,
 * and the lead says what the illustration does. Nothing in the illustration is
 * focusable.
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
          <div className="home-badge">{APP_TITLE}</div>
          <h1>{TEXT.homeHeading}</h1>
          <p className="home-lead">{TEXT.homeIntro}</p>

          <div className="home-actions">
            <Link to="/login" className="btn btn--primary btn--large">
              {TEXT.homeSignIn}
            </Link>
            <Link to="/register" className="btn btn--outline btn--large">
              {TEXT.homeRegister}
            </Link>
          </div>

          <div className="home-features">
            <div className="home-feature">
              <span className="home-feature__icon" aria-hidden="true">🔍</span>
              <div>
                <strong>{TEXT.homeFeatureSearchTitle}</strong>
                <p>{TEXT.homeFeatureSearchText}</p>
              </div>
            </div>
            <div className="home-feature">
              <span className="home-feature__icon" aria-hidden="true">📄</span>
              <div>
                <strong>{TEXT.homeFeatureCitationsTitle}</strong>
                <p>{TEXT.homeFeatureCitationsText}</p>
              </div>
            </div>
            <div className="home-feature">
              <span className="home-feature__icon" aria-hidden="true">🔐</span>
              <div>
                <strong>{TEXT.homeFeatureAccessTitle}</strong>
                <p>{TEXT.homeFeatureAccessText}</p>
              </div>
            </div>
          </div>
        </div>

        {/* Right side: illustration / visual. Decoration only: aria-hidden as a
            whole, with nothing focusable inside it. */}
        <div className="home-visual" aria-hidden="true">
          <div className="home-visual__shape home-visual__shape--1"></div>
          <div className="home-visual__shape home-visual__shape--2"></div>
          <div className="home-visual__shape home-visual__shape--3"></div>
          <div className="home-visual__scene">
            <div className="home-visual__device">
              <div className="home-visual__screen">
                <div className="home-visual__chat">
                  <div className="home-visual__bubble home-visual__bubble--left">{TEXT.homeIllustrationGreeting}</div>
                  <div className="home-visual__bubble home-visual__bubble--right">{TEXT.homeIllustrationReply}</div>
                  <div className="home-visual__bubble home-visual__bubble--left">{TEXT.homeIllustrationRequest}</div>
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
