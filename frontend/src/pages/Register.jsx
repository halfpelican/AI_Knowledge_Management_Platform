import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import useAuth from '../auth/useAuth.js'
import Button from '../components/Button.jsx'
import Notice from '../components/Notice.jsx'
import TextInput from '../components/TextInput.jsx'
import { PASSWORD_MIN_LENGTH } from '../constants.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { extractFieldErrors } from '../utils/fieldErrors.js'
import { validateRegistration } from '../utils/validation.js'
import './AuthPage.css'

const FIELDS = ['name', 'email', 'password']

/**
 * The registration form as a pure view. All state comes in as props so every
 * state (field error, 409 notice, submitting) can be rendered directly.
 */
export function RegisterForm({ values, fieldErrors, formError, submitting, onChange, onSubmit }) {
  return (
    <form className="auth-form" onSubmit={onSubmit} noValidate>
      {formError ? (
        <Notice variant="error" title="Could not create your account">
          {formError}
        </Notice>
      ) : null}
      <TextInput
        label="Name"
        name="name"
        autoComplete="name"
        required
        value={values.name}
        error={fieldErrors.name}
        onChange={onChange}
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
      />
      <TextInput
        label="Password"
        name="password"
        type="password"
        autoComplete="new-password"
        hint={`At least ${PASSWORD_MIN_LENGTH} characters and not entirely numeric.`}
        required
        value={values.password}
        error={fieldErrors.password}
        onChange={onChange}
      />
      <div className="auth-form__actions">
        <Button type="submit" disabled={submitting}>
          {submitting ? 'Creating account…' : 'Create account'}
        </Button>
      </div>
    </form>
  )
}

/**
 * FR-01 user registration.
 *
 * On success the user is sent to /login with a confirmation notice and the
 * email prefilled, rather than being signed in directly: the contract's
 * register response is a user object and says nothing about a session cookie,
 * so the client cannot assume one exists. Login (FR-02) is the only path that
 * establishes a session.
 */
export default function Register() {
  useDocumentTitle('Register')
  const { user, loading, register } = useAuth()
  const navigate = useNavigate()
  const [values, setValues] = useState({ name: '', email: '', password: '' })
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
    const clientErrors = validateRegistration(values)
    setFieldErrors(clientErrors)
    setFormError(null)
    if (Object.keys(clientErrors).length > 0) return

    setSubmitting(true)
    try {
      await register({ name: values.name.trim(), email: values.email.trim(), password: values.password })
      navigate('/login', { replace: true, state: { reason: 'registered', email: values.email.trim() } })
    } catch (error) {
      const extracted = extractFieldErrors(error, FIELDS)
      setFieldErrors(extracted.fieldErrors)
      setFormError(extracted.formError)
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
        submitting={submitting}
        onChange={handleChange}
        onSubmit={handleSubmit}
      />
      <p className="auth-page__alt">
        Already have an account? <Link to="/login">Sign in</Link>
      </p>
    </div>
  )
}
