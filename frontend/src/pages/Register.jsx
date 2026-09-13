import { useId, useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import useAuth from '../auth/useAuth.js'
import Button from '../components/Button.jsx'
import Notice from '../components/Notice.jsx'
import PasswordInput from '../components/PasswordInput.jsx'
import PasswordRequirements from '../components/PasswordRequirements.jsx'
import TextInput from '../components/TextInput.jsx'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { extractFieldErrors } from '../utils/fieldErrors.js'
import { validateRegistration } from '../utils/validation.js'
import './AuthPage.css'

/* Fields the server may return validation messages for. `confirmPassword` is
   not among them: it is a client-side check and never leaves the browser. */
const FIELDS = ['name', 'email', 'password']

const EMPTY_VALUES = { name: '', email: '', password: '', confirmPassword: '' }

/**
 * The registration form as a pure view. All state comes in as props so every
 * state — field error, mismatch, each rule unmet then met, submit disabled then
 * enabled, submitting — can be rendered directly.
 *
 * FR-01 Front-End: "the submit button remains disabled until all client-side
 * checks pass", so `canSubmit` is computed by the caller from
 * validateRegistration and passed in.
 */
export function RegisterForm({
  values,
  fieldErrors,
  formError,
  canSubmit,
  submitting,
  onChange,
  onBlur,
  onSubmit,
}) {
  const requirementsId = useId()

  return (
    <form className="auth-form" onSubmit={onSubmit} noValidate>
      {formError ? (
        <Notice variant="error" title="Could not create your account">
          {formError}
        </Notice>
      ) : null}
      <TextInput
        label="Full name"
        name="name"
        autoComplete="name"
        required
        value={values.name}
        error={fieldErrors.name}
        onChange={onChange}
        onBlur={onBlur}
      />
      <TextInput
        label="Email"
        name="email"
        type="email"
        autoComplete="email"
        required
        value={values.email}
        error={fieldErrors.email}
        onChange={onChange}
        onBlur={onBlur}
      />
      {/* The requirements panel describes the password field, so the field points
          at it with aria-describedby rather than repeating the rules in a hint. */}
      <PasswordInput
        label="Password"
        name="password"
        autoComplete="new-password"
        required
        value={values.password}
        error={fieldErrors.password}
        describedBy={requirementsId}
        onChange={onChange}
        onBlur={onBlur}
      />
      <PasswordRequirements id={requirementsId} password={values.password} />
      <PasswordInput
        label="Confirm password"
        name="confirmPassword"
        toggleLabel="Show confirmed password"
        autoComplete="new-password"
        required
        value={values.confirmPassword}
        error={fieldErrors.confirmPassword}
        onChange={onChange}
        onBlur={onBlur}
      />
      <div className="auth-form__actions">
        <Button type="submit" loading={submitting} disabled={submitting || !canSubmit}>
          {submitting ? 'Creating account…' : 'Create account'}
        </Button>
        {/* A disabled button cannot be focused, so the reason sits beside it in
            ordinary text rather than in a description only it would carry. */}
        {!canSubmit && !submitting ? (
          <p className="auth-form__gate">Complete every field and password requirement to continue.</p>
        ) : null}
      </div>
    </form>
  )
}

/**
 * FR-01 user registration.
 *
 * On success the user is sent to /login with a confirmation notice and the email
 * prefilled — "On success, the user is directed to the login page with a
 * confirmation message" — rather than being signed in directly: registration
 * starts no session (D-23), so login is the only path that establishes one.
 */
export default function Register() {
  useDocumentTitle('Register')
  const { user, loading, register } = useAuth()
  const navigate = useNavigate()
  const [values, setValues] = useState(EMPTY_VALUES)
  const [serverErrors, setServerErrors] = useState({})
  const [touched, setTouched] = useState({})
  const [formError, setFormError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  if (!loading && user) return <Navigate to="/" replace />

  const clientErrors = validateRegistration(values)
  const canSubmit = Object.keys(clientErrors).length === 0

  // What the user actually sees under each field. A client-side message appears
  // only once the field has been left, so a form nobody has touched is not
  // covered in red; the password's own feedback is the requirements panel, which
  // is always visible, so its client message is not repeated underneath.
  const fieldErrors = { ...serverErrors }
  for (const [field, message] of Object.entries(clientErrors)) {
    if (field !== 'password' && touched[field]) fieldErrors[field] = message
  }

  function handleChange(event) {
    const { name, value } = event.target
    setValues((current) => ({ ...current, [name]: value }))
    // A server message is about the value that was submitted; editing it clears it.
    setServerErrors((current) => {
      if (!(name in current)) return current
      const next = { ...current }
      delete next[name]
      return next
    })
  }

  function handleBlur(event) {
    const { name } = event.target
    setTouched((current) => (current[name] ? current : { ...current, [name]: true }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setFormError(null)
    if (!canSubmit) {
      // Unreachable from the button, which is disabled, but a form can also be
      // submitted with Enter from a field.
      setTouched({ name: true, email: true, password: true, confirmPassword: true })
      return
    }

    setSubmitting(true)
    try {
      await register({
        name: values.name.trim(),
        email: values.email.trim(),
        password: values.password,
      })
      navigate('/login', { replace: true, state: { reason: 'registered', email: values.email.trim() } })
    } catch (error) {
      // FR-01: "an inline error message appears under the relevant field". A 409
      // is by definition the duplicate address, so it goes under the email field
      // instead of into the banner above the form.
      const extracted = extractFieldErrors(error, FIELDS, { conflictField: 'email' })
      setServerErrors(extracted.fieldErrors)
      setFormError(extracted.formError)
      if (extracted.fieldErrors.email) setTouched((current) => ({ ...current, email: true }))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="auth-page">
      <h1>Create an account</h1>
      <p>New accounts start with the Employee role. An Administrator can change it later.</p>
      <RegisterForm
        values={values}
        fieldErrors={fieldErrors}
        formError={formError}
        canSubmit={canSubmit}
        submitting={submitting}
        onChange={handleChange}
        onBlur={handleBlur}
        onSubmit={handleSubmit}
      />
      <p className="auth-page__alt">
        Already have an account? <Link to="/login">Sign in</Link>
      </p>
    </div>
  )
}
