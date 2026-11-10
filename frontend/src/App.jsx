import { useState } from 'react'
import { NavLink, Outlet, Route, Routes } from 'react-router-dom'
import AuthProvider from './auth/AuthProvider.jsx'
import RequireAuth from './auth/RequireAuth.jsx'
import RequireRole from './auth/RequireRole.jsx'
import useAuth from './auth/useAuth.js'
import Button from './components/Button.jsx'
import ComponentSheet from './components/ComponentSheet.jsx'
import Notice from './components/Notice.jsx'
import SearchField from './components/SearchField.jsx'
import { APP_TITLE, dashboardPathForRole, ROLES, TEXT } from './constants.js'
import AccessDenied from './pages/AccessDenied.jsx'
import Ask from './pages/Ask.jsx'
import Dashboard from './pages/Dashboard.jsx'
import DocumentDetail from './pages/DocumentDetail.jsx'
import DocumentRepository from './pages/DocumentRepository.jsx'
import Home from './pages/Home.jsx'
import KnowledgeGaps from './pages/KnowledgeGaps.jsx'
import Login from './pages/Login.jsx'
import MeetingDetail from './pages/MeetingDetail.jsx'
import Meetings from './pages/Meetings.jsx'
import Register from './pages/Register.jsx'
import RoleManagement from './pages/RoleManagement.jsx'
import Search from './pages/Search.jsx'
import Tags from './pages/Tags.jsx'
import Upload from './pages/Upload.jsx'
import './App.css'

/**
 * Primary navigation. What it shows depends on who is signed in, but that is
 * usability only: every protected route is authorised on the server
 * (CLAUDE.md §6, invariant 4).
 */
function PrimaryNav({ onLogoutError }) {
  const { user, loading, logout } = useAuth()
  const [signingOut, setSigningOut] = useState(false)

  async function handleLogout() {
    setSigningOut(true)
    onLogoutError(null)
    try {
      // On success the auth provider sends the user to /login with the confirmation.
      await logout()
    } catch (error) {
      onLogoutError(error.message)
    } finally {
      setSigningOut(false)
    }
  }

  return (
    <nav className="app-nav" aria-label="Primary">
      {/* FR-14: a signed-in user's home is their dashboard, so the first link goes
          there and says so. `end`, so an Administrator's /admin link is not also
          marked current on /admin/roles. */}
      <NavLink to={user ? dashboardPathForRole(user.role) : '/'} end>
        {user ? TEXT.dashboardHeading : 'Home'}
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
      {/* FR-19: the knowledge-gap log is "visible to Administrators", so its link
          sits beside role management under the same test, and RequireRole guards
          its route the same way. Usability again: every knowledge-gap route checks
          `review_knowledge_gaps` on the server (D-107, invariant 4). */}
      {/* FR-10's tag administration (D-119 finding 5) is the Administrator's too:
          its link sits beside the other two under the same test, and RequireRole
          guards its route the same way. Usability once more: both tag routes check
          `manage_tags` on the server, which only the Administrator holds
          (accounts 0008, invariant 4). */}
      {user?.role === ROLES.administrator ? (
        <>
          <NavLink to="/admin/roles">Role management</NavLink>
          <NavLink to="/admin/knowledge-gaps">{TEXT.gapsHeading}</NavLink>
          <NavLink to="/admin/tags">{TEXT.tagsHeading}</NavLink>
        </>
      ) : null}
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
          {/* FR-02 redirects to a role-specific dashboard, and both destinations
              render FR-14's (D-70): whichever role signs in first lands on it. */}
          <Route element={<RequireAuth />}>
            <Route path="dashboard" element={<Dashboard />} />
            <Route path="admin" element={<Dashboard />} />
            {/* FR-08 upload; FR-15's repository, with its filters and sort in
                the query string; FR-09 transcript ingestion and the full stored
                transcript. */}
            <Route path="upload" element={<Upload />} />
            <Route path="documents" element={<DocumentRepository />} />
            {/* FR-15's detail view — metadata, extracted content, and deletion
                for a role that may delete — and where a document citation lands
                (FR-12, D-46). */}
            <Route path="documents/:docId" element={<DocumentDetail />} />
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
              {/* FR-19's knowledge-gap log (NIT3004, Objective 06). */}
              <Route path="admin/knowledge-gaps" element={<KnowledgeGaps />} />
              {/* FR-10's tag administration (NIT3004, D-119 finding 5). */}
              <Route path="admin/tags" element={<Tags />} />
            </Route>
          </Route>
        </Route>
      </Routes>
    </AuthProvider>
  )
}
