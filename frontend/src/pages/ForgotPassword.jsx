import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Button from '../components/Button.jsx'
import Notice from '../components/Notice.jsx'
import TextInput from '../components/TextInput.jsx'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { TEXT } from '../constants.js'
import './AuthPage.css'

export default function ForgotPassword() {
  useDocumentTitle('Forgot password')
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState(null)

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    if (!email.trim()) {
      setError('Enter your email address.')
      return
    }

    setSubmitting(true)
    try {
      // No backend reset endpoint exists yet, so we simulate a safe response.
      // A real implementation would call POST /auth/forgot-password here.
      setSent(true)
    } catch (caught) {
      setError('Could not send reset instructions. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  if (sent) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1>Forgot password</h1>
          <Notice variant="info" title="Check your email">
            If an account exists with {email}, you will receive instructions to reset your password.
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
        {error ? (
          <Notice variant="error" title="Could not send reset instructions">
            {error}
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