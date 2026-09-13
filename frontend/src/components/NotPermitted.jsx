import { Link } from 'react-router-dom'
import { TEXT } from '../constants.js'
import Notice from './Notice.jsx'

/**
 * The in-page 403: shown where the *API* answered 403 for material already on
 * screen, for example the user list on the role management screen after the
 * permission was withdrawn mid-session.
 *
 * A refused *navigation* is the other half and does not use this: FR-06 sends
 * that to the /403 Access Denied page (src/auth/RequireRole.jsx).
 *
 * Says only that the user lacks permission. It never describes what the screen
 * would have contained, or whether there was anything to see, so a refusal
 * discloses nothing about material outside the user's scope (CLAUDE.md §6,
 * invariant 1). Neither half is a security control; the server decides
 * (invariant 4).
 */
export default function NotPermitted() {
  return (
    <Notice variant="error" title={TEXT.notPermittedTitle}>
      <p>{TEXT.notPermitted}</p>
      <p>
        <Link to="/">Return to the home page</Link>
      </p>
    </Notice>
  )
}
