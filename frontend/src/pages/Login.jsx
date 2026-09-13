import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { ApiError, LOGIN_FAILED_MESSAGE } from '../api/client.js'
import useAuth from '../auth/useAuth.js'
import Button from '../components/Button.jsx'
import Notice from '../components/Notice.jsx'
import PasswordInput from '../components/PasswordInput.jsx'
import TextInput from '../components/TextInput.jsx'
import { dashboardPathForRole, TEXT } from '../constants.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { extractFieldErrors } from '../utils/fieldErrors.js'
import { validateLogin } from '../utils/validation.js'
import './AuthPage.css'

const FIELDS = ['email', 'password']

/** Notices for how the user arrived here, keyed by `location.state.reason`. */
const ARRIVAL_NOTICES = {
  expired: { variant: 'error', title: 'Session expired', text: TEXT.sessionExpired },
  // FR-04 Front-End: "redirected to the Login page with a brief confirmation
  // 'You've been logged out'".
  'signed-out': { variant: 'info', title: 'Logged out', text: TEXT.loggedOut },
  registered: { variant: 'info', title: 'Account created', text: TEXT.registered },
}

/**
 * The login form as a pure view. `arrival` is one of the ARRIVAL_NOTICES keys
 * (or undefined); `formError` is the fixed failure text for the last attempt,
 * either the single 401 message or the distinct locked-account one.
 */
export function LoginForm({ values, fieldErrors, formError, arrival, submitting, onChange, onSubmit }) {
  const arrivalNotice = arrival ? ARRIVAL_NOTICES[arrival] : null
  return (
    <form className="auth-form" onSubmit={onSubmit} noValidate>
      {arrivalNotice ? (
        <Notice variant={arrivalNotice.variant} title={arrivalNotice.title}>
          {arrivalNotice.text}
        </Notice>
      ) : null}
      {formError ? (
        <Notice variant="error" title="Could not sign in">
          {formError}
        </Notice>
      ) : null}
      <TextInput
        label="Email"
        name="email"
        type="email"
        autoComplete="email"
        required
        value={values.email}
        error={fieldErrors.email}
        onChange={onChange}
      />
      <PasswordInput
        label="Password"
        name="password"
        autoComplete="current-password"
        required
        value={values.password}
        error={fieldErrors.password}
        onChange={onChange}
      />
      <div className="auth-form__actions">
        {/* FR-02: "On submit, 'Login' button disables and shows a loading
            indicator, preventing a second submission." */}
        <Button type="submit" loading={submitting} disabled={submitting}>
          {submitting ? 'Signing in…' : 'Sign in'}
        </Button>
      </div>
    </form>
  )
}

/**
 * FR-02 user login.
 *
 * A 401 shows the contract's single message for both an unknown email and a
 * wrong password, so the form never reveals which. A 403 is the locked account
 * and shows its own, distinct message.
 *
 * On success the user goes to the page they were sent here from, else `/`.
 * FR-02's own clause is "On success, user is redirected to a role-specific
 * dashboard (e.g., Administrator → Admin Console; Employee → Knowledge
 * Dashboard)". Those dashboards are FR-14, built in Stage 5, so the branch on
 * role lands with them; the deferral is recorded in docs/decisions.md D-25 and
 * in docs/api-contract.md, not overlooked here.
 */
export default function Login() {
  useDocumentTitle('Sign in')
  const { user, loading, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const arrival = location.state?.reason
  const [values, setValues] = useState({ email: location.state?.email ?? '', password: '' })
  const [fieldErrors, setFieldErrors] = useState({})
  const [formError, setFormError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  if (!loading && user) return <Navigate to="/" replace />

  function handleChange(event) {
    const { name, value } = event.target
    setValues((current) => ({ ...current, [name]: value }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    const clientErrors = validateLogin(values)
    setFieldErrors(clientErrors)
    setFormError(null)
    if (Object.keys(clientErrors).length > 0) return

    setSubmitting(true)
    try {
      const me = await login({ email: values.email.trim(), password: values.password })
      // FR-02: a role-specific dashboard. A guarded route the user was sent away
      // from still wins, so they land where they were going.
      navigate(location.state?.from ?? dashboardPathForRole(me?.role), { replace: true })
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setFormError(LOGIN_FAILED_MESSAGE)
      } else if (error instanceof ApiError && error.status === 403) {
        // FR-02: "Where the account is locked and the submitted password was
        // correct, a distinct message is shown." Login is anonymous, so the lock
        // is the only 403 it can return; the server also sends the machine
        // readable code "account_locked" (apps/api/views.py ACCOUNT_LOCKED_CODE)
        // if a second 403 case is ever added here.
        setFormError(TEXT.accountLocked)
      } else {
        const extracted = extractFieldErrors(error, FIELDS)
        setFieldErrors(extracted.fieldErrors)
        setFormError(extracted.formError)
      }
      setValues((current) => ({ ...current, password: '' }))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="auth-page">
      <h1>Sign in</h1>
      <LoginForm
        values={values}
        fieldErrors={fieldErrors}
        formError={formError}
        arrival={arrival}
        submitting={submitting}
        onChange={handleChange}
        onSubmit={handleSubmit}
      />
      <p className="auth-page__alt">
        No account yet? <Link to="/register">Create one</Link>
      </p>
    </div>
  )
}
