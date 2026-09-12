import { NavLink, Outlet, Route, Routes } from 'react-router-dom'
import ComponentSheet from './components/ComponentSheet.jsx'
import { APP_TITLE } from './constants.js'
import Home from './pages/Home.jsx'
import './App.css'

/**
 * Layout shell: skip link (first focusable element), banner with the app title,
 * primary navigation, and the main landmark that pages render into.
 */
function Shell() {
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="app-header">
        <p className="app-title">{APP_TITLE}</p>
        <nav className="app-nav" aria-label="Primary">
          <NavLink to="/components">Component sheet</NavLink>
        </nav>
      </header>
      <main id="main" className="app-main" tabIndex={-1}>
        <Outlet />
      </main>
    </>
  )
}

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Home />} />
        <Route path="components" element={<ComponentSheet />} />
      </Route>
    </Routes>
  )
}
