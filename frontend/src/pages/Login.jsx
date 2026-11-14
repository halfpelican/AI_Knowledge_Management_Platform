import { useEffect, useState } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'
import { ACCOUNT_LOCKED_CODE } from '../api/auth.js'
import { ApiError, LOGIN_FAILED_MESSAGE } from '../api/client.js'
import useAuth from '../auth/useAuth.js'
import Button from '../components/Button.jsx'
import Notice from '../components/Notice.jsx'
import PasswordInput from '../components/PasswordInput.jsx'
import TextInput from '../components/TextInput.jsx'
import {
  dashboardPathForRole,
  LOCKOUT_DURATION_SECONDS,
  LOCKOUT_THRESHOLD,
  LOCKOUT_WARNING_REMAINING,
  TEXT,
} from '../constants.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { extractFieldErrors } from '../utils/fieldErrors.js'
import { validateLogin } from '../utils/validation.js'
import './AuthPage.css'

const FIELDS = ['email', 'password']

/**
 * How often the countdown is redrawn, in milliseconds. It shows whole seconds, so
 * once a second. Each redraw reads the clock rather than counting ticks, so a late
 * tick never makes the countdown drift.
 */
const COUNTDOWN_TICK_MS = 1000

/** Who put an address into the locked state: the server's 403, or the page's own count. */
const LOCKED_BY = { server: 'server', page: 'page' }

/** Notices for how the user arrived here, keyed by `location.state.reason`. */
const ARRIVAL_NOTICES = {
  expired: { variant: 'error', title: 'Session expired', text: TEXT.sessionExpired },
  // FR-04 Front-End: "redirected to the Login page with a brief confirmation
  // 'You've been logged out'".
  'signed-out': { variant: 'info', title: 'Logged out', text: TEXT.loggedOut },
  registered: { variant: 'info', title: 'Account created', text: TEXT.registered },
}

/**
 * The address as FR-03's count keys it: trimmed and lower-cased, so
 * "Jane@Example.com " and "jane@example.com" share one count.
 */
function normalisedAddress(email) {
  return String(email ?? '')
    .trim()
    .toLowerCase()
}

/** Whole seconds from `now` until `lockedUntil` (both in milliseconds), or 0 once it has passed. */
function secondsUntil(lockedUntil, now) {
  if (lockedUntil === null || lockedUntil === undefined) return 0
  return Math.max(0, Math.ceil((lockedUntil - now) / 1000))
}

/**
 * How long the server's 403 says the lock has left: its `retry_after`, in whole
 * seconds. Where that is absent or not a positive number, the full
 * LOCKOUT_DURATION_SECONDS, which no lock outlasts, so Sign in never comes back
 * before the lock could have ended.
 */
function lockSecondsFrom(details) {
  const retryAfter = details && typeof details === 'object' ? details.retry_after : undefined
  return typeof retryAfter === 'number' && Number.isFinite(retryAfter) && retryAfter > 0
    ? Math.ceil(retryAfter)
    : LOCKOUT_DURATION_SECONDS
}

/*
 * FR-03's record of each address this page has been given (D-130 decision 1):
 * address -> { failures, lockedUntil, lockedBy }, with `lockedUntil` in
 * milliseconds or null. It lives in component state for the screen's life and in
 * no storage of any kind, and nothing in it comes from the server except the
 * right-password 403's `retry_after`. A locked address never reaches
 * `afterFailure`, because Sign in is disabled for it.
 */

/** After a 401: one more consecutive failure, and the page's own lock at LOCKOUT_THRESHOLD. */
function afterFailure(records, address, at) {
  const failures = (records[address]?.failures ?? 0) + 1
  const locks = failures >= LOCKOUT_THRESHOLD
  return {
    ...records,
    [address]: {
      failures,
      lockedUntil: locks ? at + LOCKOUT_DURATION_SECONDS * 1000 : null,
      lockedBy: locks ? LOCKED_BY.page : null,
    },
  }
}

/** After the server's 403: its lock, and the count cleared. */
function afterServerLock(records, address, at, seconds) {
  return { ...records, [address]: { failures: 0, lockedUntil: at + seconds * 1000, lockedBy: LOCKED_BY.server } }
}

/** After a success: the address's count cleared. */
function withoutAddress(records, address) {
  if (!(address in records)) return records
  const next = { ...records }
  delete next[address]
  return next
}

/** At zero: every lock that has ended by `at` is cleared, with its count. */
function withoutEndedLocks(records, at) {
  const ended = Object.keys(records).filter((address) => {
    const { lockedUntil } = records[address]
    return lockedUntil !== null && lockedUntil <= at
  })
  if (ended.length === 0) return records
  const next = { ...records }
  for (const address of ended) delete next[address]
  return next
}

/**
 * The login form as a pure view. `arrival` is one of the ARRIVAL_NOTICES keys
 * (or undefined); `formError` is the fixed failure text for the last attempt.
 *
 * FR-03's three, all for the address typed: `warning` is the remaining-attempts
 * text or null; `lockMessage` is the locked state's text or null; `lockSeconds`
 * is the time its lock has left, and while it is above zero Sign in is disabled
 * and the countdown is shown.
 */
export function LoginForm({
  values,
  fieldErrors,
  formError,
  arrival,
  submitting,
  warning = null,
  lockMessage = null,
  lockSeconds = 0,
  onChange,
  onSubmit,
}) {
  const arrivalNotice = arrival ? ARRIVAL_NOTICES[arrival] : null
  const locked = lockSeconds > 0
  return (
    <form className="auth-form" onSubmit={onSubmit} noValidate>
      {arrivalNotice ? (
        <Notice variant={arrivalNotice.variant} title={arrivalNotice.title}>
          {arrivalNotice.text}
        </Notice>
      ) : null}
      {/* The lock's message is in the same alert as the attempt's failure, so it is
          announced once, when it appears, and not again while the countdown runs. */}
      {formError || lockMessage ? (
        <Notice variant="error" title="Could not sign in">
          {formError ? <p>{formError}</p> : null}
          {lockMessage ? <p>{lockMessage}</p> : null}
          {lockMessage ? <p>{TEXT.lockedReloadHint}</p> : null}
        </Notice>
      ) : null}
      {/* FR-03's warning: subtle text beside the banner, not a second banner. Always
          in the page, so that a change to it is announced politely; it takes no room
          while it has nothing to say. */}
      <p className="auth-form__warning" role="status">
        {warning ?? ''}
      </p>
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
            indicator, preventing a second submission." FR-03 disables it as well
            while the typed address's lock runs, with the countdown shown. */}
        <Button type="submit" loading={submitting} disabled={submitting || locked}>
          {submitting ? 'Signing in…' : 'Sign in'}
        </Button>
        {/* A timer, which assistive technology does not announce on every tick. A
            disabled button cannot be focused, so the reason sits beside it in
            ordinary text, as on the registration form. */}
        {locked ? (
          <p className="auth-form__gate auth-form__countdown" role="timer">
            {TEXT.lockoutCountdown(lockSeconds)}
          </p>
        ) : null}
      </div>
    </form>
  )
}

/**
 * FR-02 user login, with FR-03's warning and countdown.
 *
 * A 401 shows the contract's single message for both an unknown email and a
 * wrong password, so the form never reveals which. A 403 `account_locked` is the
 * locked account, given only to the right password, and shows its own, distinct
 * message.
 *
 * FR-03 (D-130). The page counts consecutive 401s for each address, as typed and
 * normalised, in memory only. A 400, a 429 or a network failure does not count; a
 * 403 or a success clears the count. Once LOCKOUT_WARNING_REMAINING or fewer
 * attempts remain, the warning shows; at LOCKOUT_THRESHOLD the address enters the
 * page's locked state, with a message true of any address and a countdown from
 * LOCKOUT_DURATION_SECONDS. A 403 enters the same state from its `retry_after`.
 * While the countdown runs for the address typed, Sign in is disabled; typing
 * another address shows that address's own state. At zero the lock and the count
 * are cleared. None of this is security: the server enforces the lock whatever the
 * page shows (CLAUDE.md §6, invariant 4), and nothing the page shows depends on
 * what the server says of an account, except the right-password 403, so it is the
 * same for an address with no account.
 *
 * On success the user goes to the page they were sent here from, else to their
 * role's dashboard.
 * FR-02's own clause is "On success, user is redirected to a role-specific
 * dashboard (e.g., Administrator → Admin Console; Employee → Knowledge
 * Dashboard)". Those dashboards are FR-14, built in Stage 5, so the branch on
 * role lands with them; the deferral is recorded in docs/decisions.md D-25 and
 * in docs/api-contract.md, not overlooked here.
 */
export default function Login() {
  useDocumentTitle('Sign in')
  const { user, loading, login } = useAuth()
  const location = useLocation()
  const arrival = location.state?.reason
  const [values, setValues] = useState({ email: location.state?.email ?? '', password: '' })
  const [fieldErrors, setFieldErrors] = useState({})
  const [formError, setFormError] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  // FR-03: the page's own record of each address (the note above `afterFailure`).
  const [records, setRecords] = useState({})
  // The clock the countdown is read from. It is set whenever a lock begins and
  // moved on once a second while any lock runs.
  const [now, setNow] = useState(() => Date.now())

  const anyLock = Object.values(records).some((record) => record.lockedUntil !== null)
  useEffect(() => {
    if (!anyLock) return undefined
    const timer = setInterval(() => {
      const at = Date.now()
      setNow(at)
      setRecords((current) => withoutEndedLocks(current, at))
    }, COUNTDOWN_TICK_MS)
    return () => clearInterval(timer)
  }, [anyLock])

  // Signed in, by this form or before arriving. FR-02: a role-specific dashboard, but a
  // guarded route the user was sent away from still wins, so they land where they were
  // going. This is the only navigation after sign-in, so nothing can replace it.
  if (!loading && user) {
    return <Navigate to={location.state?.from ?? dashboardPathForRole(user.role)} replace />
  }

  // FR-03's state for the address typed now.
  const record = records[normalisedAddress(values.email)]
  const lockSeconds = secondsUntil(record?.lockedUntil, now)
  const locked = lockSeconds > 0
  const remaining = LOCKOUT_THRESHOLD - (record?.failures ?? 0)
  const warning =
    !locked && remaining >= 1 && remaining <= LOCKOUT_WARNING_REMAINING ? TEXT.attemptsRemaining(remaining) : null
  let lockMessage = null
  if (locked) lockMessage = record.lockedBy === LOCKED_BY.server ? TEXT.accountLocked : TEXT.accountMayBeLocked

  function handleChange(event) {
    const { name, value } = event.target
    setValues((current) => ({ ...current, [name]: value }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    // Sign in is disabled while the typed address's lock runs. This holds for a
    // submission that does not come from the button as well.
    if (locked) return
    const clientErrors = validateLogin(values)
    setFieldErrors(clientErrors)
    setFormError(null)
    if (Object.keys(clientErrors).length > 0) return

    // The address this attempt is for, fixed now: the field can be edited while the
    // request is in flight, and the answer belongs to the address that was sent.
    const attempted = normalisedAddress(values.email)
    setSubmitting(true)
    try {
      // Sets the user, and the redirect above sends them on.
      await login({ email: values.email.trim(), password: values.password })
      setRecords((current) => withoutAddress(current, attempted))
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setFormError(LOGIN_FAILED_MESSAGE)
        const at = Date.now()
        setNow(at)
        setRecords((current) => afterFailure(current, attempted, at))
      } else if (error instanceof ApiError && error.status === 403 && error.code === ACCOUNT_LOCKED_CODE) {
        // FR-02: "Where the account is locked and the submitted password was
        // correct, a distinct message is shown." The server sends that 403 only to
        // the right password (FR-03's messaging rule), so it discloses the lock to
        // nobody else. Its message replaces the attempt's banner and goes with the
        // countdown, so nothing is left in the banner when the lock ends.
        const at = Date.now()
        setNow(at)
        setRecords((current) => afterServerLock(current, attempted, at, lockSecondsFrom(error.details)))
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
        warning={warning}
        lockMessage={lockMessage}
        lockSeconds={lockSeconds}
        onChange={handleChange}
        onSubmit={handleSubmit}
      />
      <p className="auth-page__alt">
        No account yet? <Link to="/register">Create one</Link>
      </p>
    </div>
  )
}
