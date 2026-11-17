import { useEffect, useId, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { confirmPasswordReset, replyDetail } from '../api/auth.js'
import { ApiError, messageForStatus } from '../api/client.js'
import Button from '../components/Button.jsx'
import Notice from '../components/Notice.jsx'
import PasswordInput from '../components/PasswordInput.jsx'
import PasswordRequirements from '../components/PasswordRequirements.jsx'
import { SIGN_IN_TEXT, VALIDATION } from '../constants.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { extractFieldErrors } from '../utils/fieldErrors.js'
import { passwordMeetsPolicy } from '../utils/password.js'
import { whenToRetry } from '../utils/retryAfter.js'
import './AuthPage.css'

/** The two values the emailed link carries: `/reset-password?uid=<uid>&token=<token>`. */
const LINK_PARAMETERS = ['uid', 'token']

/** The field a 400 can name that leaves the link working. */
const FIELDS = ['new_password']

const EMPTY_VALUES = { newPassword: '', confirmPassword: '' }

/** The link's values from a query string, or null where either is missing or blank. */
function linkFrom(search) {
  const params = new URLSearchParams(search)
  const uid = params.get('uid') ?? ''
  const token = params.get('token') ?? ''
  return uid.trim() && token.trim() ? { uid, token } : null
}

/** A query string without the link's values: `?…`, or '' where nothing else was in it. */
function withoutLink(search) {
  const params = new URLSearchParams(search)
  for (const name of LINK_PARAMETERS) params.delete(name)
  const rest = params.toString()
  return rest ? `?${rest}` : ''
}

/**
 * FR-01's client-side checks on the new password and its confirmation, the ones the
 * registration form makes on its two (src/utils/validation.js validateRegistration).
 * The rules themselves are src/utils/password.js's, the client's one copy of the
 * policy the server enforces.
 */
function validateNewPassword(values) {
  const errors = {}
  if (!values.newPassword) errors.newPassword = VALIDATION.passwordRequired
  else if (!passwordMeetsPolicy(values.newPassword)) errors.newPassword = VALIDATION.passwordRequirements
  if (!values.confirmPassword) errors.confirmPassword = VALIDATION.confirmPasswordRequired
  else if (values.confirmPassword !== values.newPassword) errors.confirmPassword = VALIDATION.passwordMismatch
  return errors
}

/**
 * D-137's reset page, which the emailed link opens: anonymous, as the two routes are.
 *
 * **The link's values leave the address at once.** `uid` and `token` are read from the
 * query string on the first render and kept in state, and an effect then replaces the
 * address with one without them, through React Router, which calls
 * `history.replaceState`. Replaced, not pushed, so no history entry keeps the token,
 * and the address a later request or link sends as its Referer no longer holds it.
 * Until then, index.html's `<meta name="referrer" content="same-origin">` keeps it out
 * of any Referer sent to another origin (REF-1), as the server's `Referrer-Policy`,
 * Django's `same-origin`, does too.
 *
 * **A link without both values** is the dead-link state at once, and nothing is sent.
 *
 * **The form** is a new password, with FR-01's requirements panel, and its
 * confirmation, under the rules registration uses; Reset password stays disabled until
 * every check passes. It posts `{uid, token, new_password}` to
 * POST /api/auth/password-reset/confirm, and then:
 *
 * - 200: the server's sentence, and a link to sign in. A reset signs nobody in.
 * - The 400 for a link that does not work, `{"detail": ...}`, and DRF's 400 for a
 *   `uid` or `token` it could not read: the dead-link state, in the page's own words,
 *   with a link to ask for a new one. Anything a 400 carries other than a
 *   `new_password` message is the link's.
 * - A `new_password` 400: the message under the field. The link still works, so the
 *   form stays, with the same link.
 * - 429: when to try again. Anything else: the API client's fixed text.
 *
 * FR-02's pattern in flight ("Resetting…", disabled, one request per press). When the
 * form gives way to an outcome, focus moves to the heading above it.
 */
export default function ResetPassword() {
  useDocumentTitle('Reset password')
  const location = useLocation()
  const navigate = useNavigate()
  const requirementsId = useId()
  const headingRef = useRef(null)
  // One request at a time: a link works once, so a second confirm would be told it does not.
  const inFlight = useRef(false)
  // Read once, here, and kept: the address loses them in the effect below.
  const [link] = useState(() => linkFrom(location.search))
  // What the last request came to: null while the form is open, then 'done' or 'dead'.
  const [outcome, setOutcome] = useState(null)
  const [doneMessage, setDoneMessage] = useState(null)
  const [values, setValues] = useState(EMPTY_VALUES)
  const [touched, setTouched] = useState({})
  const [serverError, setServerError] = useState(null)
  const [formError, setFormError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  // Out of the address bar at once, and out of history: the entry is replaced.
  useEffect(() => {
    const params = new URLSearchParams(location.search)
    if (!LINK_PARAMETERS.some((name) => params.has(name))) return
    navigate({ pathname: location.pathname, search: withoutLink(location.search), hash: location.hash }, { replace: true })
  }, [location, navigate])

  // An outcome replaces the form, and the button that had focus with it.
  useEffect(() => {
    if (outcome !== null) headingRef.current?.focus()
  }, [outcome])

  const clientErrors = validateNewPassword(values)
  const canSubmit = Object.keys(clientErrors).length === 0

  // What shows under each field: the server's message for the new password, and a
  // client message once its field has been left. The new password's own client feedback
  // is the requirements panel, so it is not repeated under it (as on registration).
  const fieldErrors = {}
  if (serverError) fieldErrors.newPassword = serverError
  for (const [field, message] of Object.entries(clientErrors)) {
    if (field !== 'newPassword' && touched[field]) fieldErrors[field] = message
  }

  function handleChange(event) {
    const { name, value } = event.target
    setValues((current) => ({ ...current, [name]: value }))
    // The server's message is about the password that was sent; editing it clears it.
    if (name === 'newPassword') setServerError(null)
  }

  function handleBlur(event) {
    const { name } = event.target
    setTouched((current) => (current[name] ? current : { ...current, [name]: true }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (inFlight.current || link === null) return
    setFormError(null)
    if (!canSubmit) {
      // Unreachable from the button, which is disabled, but Enter in a field submits too.
      setTouched({ newPassword: true, confirmPassword: true })
      return
    }

    inFlight.current = true
    setSubmitting(true)
    try {
      const reply = await confirmPasswordReset({ uid: link.uid, token: link.token, newPassword: values.newPassword })
      setValues(EMPTY_VALUES)
      setDoneMessage(replyDetail(reply) ?? SIGN_IN_TEXT.resetCompleteFallback)
      setOutcome('done')
    } catch (error) {
      if (error instanceof ApiError && error.status === 400) {
        const extracted = extractFieldErrors(error, FIELDS)
        if (extracted.fieldErrors.new_password) {
          setServerError(extracted.fieldErrors.new_password)
        } else {
          setValues(EMPTY_VALUES)
          setOutcome('dead')
        }
      } else if (error instanceof ApiError && error.status === 429) {
        setFormError(SIGN_IN_TEXT.tooManyAttempts(whenToRetry(error.retryAfter)))
      } else {
        setFormError(error instanceof ApiError ? error.message : messageForStatus())
      }
    } finally {
      inFlight.current = false
      setSubmitting(false)
    }
  }

  let body
  if (link === null || outcome === 'dead') {
    body = (
      <>
        <Notice variant="error" title={SIGN_IN_TEXT.resetLinkDeadTitle}>
          {SIGN_IN_TEXT.resetLinkDead}
        </Notice>
        <p className="auth-page__alt">
          <Link to="/forgot-password">{SIGN_IN_TEXT.resetAskAgain}</Link>
        </p>
      </>
    )
  } else if (outcome === 'done') {
    body = (
      <>
        {/* The server's sentence, rendered as text. */}
        <Notice variant="info" title={SIGN_IN_TEXT.resetDoneTitle}>
          {doneMessage}
        </Notice>
        <p className="auth-page__alt">
          <Link to="/login">Sign in</Link>
        </p>
      </>
    )
  } else {
    body = (
      <>
        <p className="auth-card__intro">{SIGN_IN_TEXT.resetIntro}</p>
        {formError ? (
          <Notice variant="error" title={SIGN_IN_TEXT.resetFailedTitle}>
            {formError}
          </Notice>
        ) : null}
        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          {/* The requirements panel describes the field, as on registration (FR-01). */}
          <PasswordInput
            label="New password"
            name="newPassword"
            toggleLabel="Show new password"
            autoComplete="new-password"
            required
            value={values.newPassword}
            error={fieldErrors.newPassword}
            describedBy={requirementsId}
            onChange={handleChange}
            onBlur={handleBlur}
          />
          <PasswordRequirements id={requirementsId} password={values.newPassword} />
          <PasswordInput
            label="Confirm new password"
            name="confirmPassword"
            toggleLabel="Show confirmed password"
            autoComplete="new-password"
            required
            value={values.confirmPassword}
            error={fieldErrors.confirmPassword}
            onChange={handleChange}
            onBlur={handleBlur}
          />
          <div className="auth-form__actions">
            <Button type="submit" loading={submitting} disabled={submitting || !canSubmit}>
              {submitting ? 'Resetting…' : 'Reset password'}
            </Button>
            {!canSubmit && !submitting ? <p className="auth-form__gate">{SIGN_IN_TEXT.resetGate}</p> : null}
          </div>
        </form>
        <p className="auth-page__alt">
          Remember your password? <Link to="/login">Sign in</Link>
        </p>
      </>
    )
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1 ref={headingRef} tabIndex={-1}>
          Reset password
        </h1>
        {body}
      </div>
    </div>
  )
}
