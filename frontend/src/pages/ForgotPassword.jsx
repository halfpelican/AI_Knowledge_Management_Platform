import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { replyDetail, requestPasswordReset } from '../api/auth.js'
import { ApiError } from '../api/client.js'
import Button from '../components/Button.jsx'
import Notice from '../components/Notice.jsx'
import TextInput from '../components/TextInput.jsx'
import { SIGN_IN_TEXT, VALIDATION } from '../constants.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { extractFieldErrors } from '../utils/fieldErrors.js'
import { whenToRetry } from '../utils/retryAfter.js'
import './AuthPage.css'

/** The field the server may return a validation message for. */
const FIELDS = ['email']

/**
 * D-137's forgotten-password request: PR #119's page, wired to POST
 * /api/auth/password-reset.
 *
 * The server answers every well-formed address with the same 200 and the same
 * sentence, whether or not an account uses it, and emails a link only to an account
 * (D-25). The page shows that sentence as it was sent and nothing else about the
 * address, so it never says or implies whether an account exists. It says nothing of a
 * link until that 200 has arrived: no success is simulated.
 *
 * An empty address is refused here before anything is sent. Whether an address is
 * well formed is the server's to say: its 400 puts DRF's message under the field, as
 * FR-01's page does. The 429, past the `auth` rate the reset shares with sign-in and
 * registration, says when to try again; any other failure shows the API client's fixed
 * text and never the server's (src/api/client.js). The address stays in the field
 * after a refusal.
 *
 * FR-02's pattern while the request is in flight: the button disables, says
 * "Sending…" and shows the loading indicator, and a second press sends nothing.
 */
export default function ForgotPassword() {
  useDocumentTitle('Forgot password')
  const headingRef = useRef(null)
  // One request at a time, whatever the button's state has caught up with.
  const inFlight = useRef(false)
  const [email, setEmail] = useState('')
  const [fieldError, setFieldError] = useState(null)
  const [formError, setFormError] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  // The server's 200 sentence, once it has answered; null until then.
  const [sent, setSent] = useState(null)

  // Once the form gives way to the message, the button that had focus is gone, so
  // focus starts again at the heading, with the message under it.
  useEffect(() => {
    if (sent !== null) headingRef.current?.focus()
  }, [sent])

  async function handleSubmit(event) {
    event.preventDefault()
    if (inFlight.current) return
    setFormError(null)
    const address = email.trim()
    if (!address) {
      setFieldError(VALIDATION.emailRequired)
      return
    }
    setFieldError(null)

    inFlight.current = true
    setSubmitting(true)
    try {
      const reply = await requestPasswordReset({ email: address })
      setSent(replyDetail(reply) ?? SIGN_IN_TEXT.resetRequestedFallback)
    } catch (error) {
      if (error instanceof ApiError && error.status === 429) {
        setFormError(SIGN_IN_TEXT.tooManyAttempts(whenToRetry(error.retryAfter)))
      } else {
        const extracted = extractFieldErrors(error, FIELDS)
        setFieldError(extracted.fieldErrors.email ?? null)
        setFormError(extracted.formError)
      }
    } finally {
      inFlight.current = false
      setSubmitting(false)
    }
  }

  if (sent !== null) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1 ref={headingRef} tabIndex={-1}>
            Forgot password
          </h1>
          {/* The server's one sentence for every address (D-25), rendered as text. */}
          <Notice variant="info" title="Check your email">
            {sent}
          </Notice>
          <p className="auth-page__alt">
            Remember your password? <Link to="/login">Sign in</Link>
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>Forgot password</h1>
        <p className="auth-card__intro">
          Enter the email address you signed up with and we will send reset instructions.
        </p>
        {formError ? (
          <Notice variant="error" title="Could not send reset instructions">
            {formError}
          </Notice>
        ) : null}
        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          <TextInput
            label="Email address"
            name="email"
            type="email"
            autoComplete="email"
            hint="The address you used to register."
            required
            value={email}
            error={fieldError}
            onChange={(event) => setEmail(event.target.value)}
          />
          <div className="auth-form__actions">
            <Button type="submit" loading={submitting} disabled={submitting}>
              {submitting ? 'Sending…' : 'Send reset instructions'}
            </Button>
          </div>
        </form>
        <p className="auth-page__alt">
          Remember your password? <Link to="/login">Sign in</Link>
        </p>
      </div>
    </div>
  )
}
