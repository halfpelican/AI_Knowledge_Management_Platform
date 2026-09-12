import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { ApiError, LOGIN_FAILED_MESSAGE } from '../api/client.js'
import useAuth from '../auth/useAuth.js'
import Button from '../components/Button.jsx'
import Notice from '../components/Notice.jsx'
import TextInput from '../components/TextInput.jsx'
import { TEXT } from '../constants.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { extractFieldErrors } from '../utils/fieldErrors.js'
import { validateLogin } from '../utils/validation.js'
import './AuthPage.css'

const FIELDS = ['email', 'password']

/** Notices for how the user arrived here, keyed by `location.state.reason`. */
const ARRIVAL_NOTICES = {
  expired: { variant: 'error', title: 'Session expired', text: TEXT.sessionExpired },
  'signed-out': { variant: 'info', title: 'Signed out', text: TEXT.signedOut },
  registered: { variant: 'info', title: 'Account created', text: TEXT.registered },
}

/**
 * The login form as a pure view. `arrival` is one of the ARRIVAL_NOTICES keys
 * (or undefined); `formError` is the fixed failure text for the last attempt.
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
      <TextInput
        label="Password"
        name="password"
        type="password"
        autoComplete="current-password"
        required
        value={values.password}
        error={fieldErrors.password}
        onChange={onChange}
      />
      <div className="auth-form__actions">
        <Button type="submit" disabled={submitting}>
          {submitting ? 'Signing in…' : 'Sign in'}
        </Button>
      </div>
    </form>
  )
}

/**
 * FR-02 user login. A 401 shows the contract's single message for both an
 * unknown email and a wrong password, so the form never reveals which.
 * On success the user goes to the page they were sent here from, else `/`.
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
      await login({ email: values.email.trim(), password: values.password })
      navigate(location.state?.from ?? '/', { replace: true })
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setFormError(LOGIN_FAILED_MESSAGE)
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
