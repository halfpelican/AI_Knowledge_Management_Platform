import { useState } from 'react'
import { NavLink, Outlet, Route, Routes, useNavigate } from 'react-router-dom'
import AuthProvider from './auth/AuthProvider.jsx'
import RequireAuth from './auth/RequireAuth.jsx'
import RequireRole from './auth/RequireRole.jsx'
import useAuth from './auth/useAuth.js'
import Button from './components/Button.jsx'
import ComponentSheet from './components/ComponentSheet.jsx'
import Notice from './components/Notice.jsx'
import SearchField from './components/SearchField.jsx'
import { APP_TITLE, ROLES, TEXT } from './constants.js'
import AccessDenied from './pages/AccessDenied.jsx'
import Ask from './pages/Ask.jsx'
import DocumentRepository from './pages/DocumentRepository.jsx'
import Home from './pages/Home.jsx'
import Login from './pages/Login.jsx'
import MeetingDetail from './pages/MeetingDetail.jsx'
import Meetings from './pages/Meetings.jsx'
import Register from './pages/Register.jsx'
import RoleManagement from './pages/RoleManagement.jsx'
import Search from './pages/Search.jsx'
import Upload from './pages/Upload.jsx'
import './App.css'

/**
 * Primary navigation. What it shows depends on who is signed in, but that is
 * usability only: every protected route is authorised on the server
 * (CLAUDE.md §6, invariant 4).
 */
function PrimaryNav({ onLogoutError }) {
  const { user, loading, logout } = useAuth()
  const navigate = useNavigate()
  const [signingOut, setSigningOut] = useState(false)

  async function handleLogout() {
    setSigningOut(true)
    onLogoutError(null)
    try {
      await logout()
      navigate('/login', { replace: true, state: { reason: 'signed-out' } })
    } catch (error) {
      onLogoutError(error.message)
    } finally {
      setSigningOut(false)
    }
  }

  return (
    <nav className="app-nav" aria-label="Primary">
      <NavLink to="/" end>
        Home
      </NavLink>
      {/* FR-08, FR-09 and FR-15: every signed-in user may reach all three, so
          there is no role test here. They are shown only while signed in
          because an anonymous visitor would be sent straight to /login by
          RequireAuth; that is usability, and the server authorises each request
          regardless (CLAUDE.md §6, invariant 4). */}
      {user ? (
        <>
          <NavLink to="/documents">Documents</NavLink>
          <NavLink to="/upload">Upload</NavLink>
          <NavLink to="/meetings">Meetings</NavLink>
          {/* FR-12's answer path and FR-13's assistant are one screen, because they
              are one endpoint. FR-13 asks for it to be "reachable from any page",
              which is what this link is. */}
          <NavLink to="/ask">{TEXT.askNavLabel}</NavLink>
        </>
      ) : null}
      {/* FR-05: the role management screen "is entirely hidden and inaccessible
          to non-admin roles (button and route do not render)". This is the button
          half; RequireRole is the route half. Both are usability — the server
          refuses the call either way (CLAUDE.md §6, invariant 4). */}
      {user?.role === ROLES.administrator ? <NavLink to="/admin/roles">Role management</NavLink> : null}
      <NavLink to="/components">Component sheet</NavLink>
      {/* FR-04: "A 'Logout' control visible in navigation for all authenticated
          roles." One branch, no role test, so every signed-in user has it. */}
      {loading ? null : user ? (
        <>
          <span className="app-nav__user">{`Signed in as ${user.name}`}</span>
          <Button
            variant="secondary"
            className="app-nav__logout"
            loading={signingOut}
            disabled={signingOut}
            onClick={handleLogout}
          >
            {signingOut ? 'Signing out…' : 'Log out'}
          </Button>
        </>
      ) : (
        <>
          <NavLink to="/login">Sign in</NavLink>
          <NavLink to="/register">Register</NavLink>
        </>
      )}
    </nav>
  )
}

/**
 * FR-12: "a search field available from every page".
 *
 * It lives in the shell's header, so it is on every screen a signed-in user can
 * reach, and it is a `role="search"` landmark of its own rather than part of the
 * navigation. It is rendered only while signed in, for the same reason the
 * navigation's own links are: an anonymous visitor is sent to /login by
 * RequireAuth before any screen with results could render, and the server
 * authorises the call regardless (CLAUDE.md §6, invariant 4).
 */
function HeaderSearch() {
  const { user } = useAuth()
  if (!user) return null
  return <SearchField id="header-search" className="search-field--header" />
}

/**
 * Layout shell: skip link (first focusable element), banner with the app title,
 * the search field FR-12 wants on every page, primary navigation, and the main
 * landmark that pages render into.
 */
export function Shell() {
  const [logoutError, setLogoutError] = useState(null)

  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="app-header">
        <p className="app-title">{APP_TITLE}</p>
        <HeaderSearch />
        <PrimaryNav onLogoutError={setLogoutError} />
      </header>
      <main id="main" className="app-main" tabIndex={-1}>
        {logoutError ? (
          <Notice variant="error" title="Could not sign out">
            {logoutError}
          </Notice>
        ) : null}
        <Outlet />
      </main>
    </>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<Home />} />
          <Route path="login" element={<Login />} />
          <Route path="register" element={<Register />} />
          <Route path="components" element={<ComponentSheet />} />
          {/* FR-02 redirects to a role-specific dashboard. FR-14 replaces what
              these render in Stage 5; they exist now so the redirect is real. */}
          <Route element={<RequireAuth />}>
            <Route path="dashboard" element={<Home />} />
            <Route path="admin" element={<Home />} />
            {/* Stage 3: FR-08 upload and the repository list, FR-09 transcript
                ingestion and the full stored transcript. */}
            <Route path="upload" element={<Upload />} />
            <Route path="documents" element={<DocumentRepository />} />
            <Route path="meetings" element={<Meetings />} />
            <Route path="meetings/:meetingId" element={<MeetingDetail />} />
            {/* Stage 4: FR-12's grouped keyword search, and FR-12's answer path,
                which is also FR-13's conversational turn. */}
            <Route path="search" element={<Search />} />
            <Route path="ask" element={<Ask />} />
          </Route>
          {/* FR-06: where a guarded route sends an unauthorised navigation attempt. */}
          <Route path="403" element={<AccessDenied />} />
          <Route element={<RequireAuth />}>
            <Route element={<RequireRole role={ROLES.administrator} />}>
              <Route path="admin/roles" element={<RoleManagement />} />
            </Route>
          </Route>
        </Route>
      </Routes>
    </AuthProvider>
  )
}
