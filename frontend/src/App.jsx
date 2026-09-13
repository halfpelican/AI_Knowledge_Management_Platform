import { useState } from 'react'
import { NavLink, Outlet, Route, Routes, useNavigate } from 'react-router-dom'
import AuthProvider from './auth/AuthProvider.jsx'
import RequireAuth from './auth/RequireAuth.jsx'
import RequireRole from './auth/RequireRole.jsx'
import useAuth from './auth/useAuth.js'
import Button from './components/Button.jsx'
import ComponentSheet from './components/ComponentSheet.jsx'
import Notice from './components/Notice.jsx'
import { APP_TITLE, ROLES } from './constants.js'
import AccessDenied from './pages/AccessDenied.jsx'
import Home from './pages/Home.jsx'
import Login from './pages/Login.jsx'
import Register from './pages/Register.jsx'
import RoleManagement from './pages/RoleManagement.jsx'
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
 * Layout shell: skip link (first focusable element), banner with the app title,
 * primary navigation, and the main landmark that pages render into.
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
