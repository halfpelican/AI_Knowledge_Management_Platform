import { Link } from 'react-router-dom'
import { TEXT } from '../constants.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'

/**
 * FR-06 Front-End: "Unauthorised navigation attempts (e.g., manually typing an
 * admin URL) redirect to a '403 – Access Denied' page."
 *
 * A route of its own at /403, so the redirect has somewhere to go and the
 * address bar shows that the attempt was refused.
 *
 * It says only that permission is lacking. It does not name the screen that was
 * asked for, or say whether that screen exists, so a refusal discloses nothing
 * about material outside the user's scope (CLAUDE.md §6, invariant 1).
 *
 * This is usability, not security. The screen behind it is authorised on the
 * server, which answers 403 for a role lacking the permission whatever the
 * interface does (invariant 4).
 */
export default function AccessDenied() {
  useDocumentTitle(TEXT.accessDeniedTitle)

  return (
    <div className="access-denied">
      <h1>{TEXT.accessDeniedTitle}</h1>
      <p>{TEXT.accessDenied}</p>
      <p>
        <Link to="/">Return to the home page</Link>
      </p>
    </div>
  )
}
