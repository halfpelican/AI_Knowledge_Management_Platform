import { Link } from 'react-router-dom'
import { TEXT } from '../constants.js'
import Notice from './Notice.jsx'

/**
 * Shown when the signed-in user's role does not allow a screen or the server
 * answered 403. Says only that the user lacks permission; it never describes
 * what the screen would have contained.
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
