import { useEffect, useRef, useState } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'
import { ACCOUNT_LOCKED_CODE, getLockoutPolicy } from '../api/auth.js'
import { ApiError, LOGIN_FAILED_MESSAGE } from '../api/client.js'
import useAuth from '../auth/useAuth.js'
import Button from '../components/Button.jsx'
import Notice from '../components/Notice.jsx'
import PasswordInput from '../components/PasswordInput.jsx'
import TextInput from '../components/TextInput.jsx'
import { dashboardPathForRole, LOCKOUT_WARNING_REMAINING, TEXT } from '../constants.js'
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

/** The 403's `retry_after`, in whole seconds, or null where it is absent or not a positive number. */
function retryAfterFrom(details) {
  const retryAfter = details && typeof details === 'object' ? details.retry_after : undefined
  return typeof retryAfter === 'number' && Number.isFinite(retryAfter) && retryAfter > 0 ? Math.ceil(retryAfter) : null
}

/**
 * The running lockout policy from GET /api/auth/lockout-policy (D-130 decision 7):
 * `{threshold, durationSeconds}`, or null where the reply is not one.
 */
function policyFrom(body) {
  const threshold = body && typeof body === 'object' ? body.lockout_threshold : undefined
  const durationSeconds = body && typeof body === 'object' ? body.lockout_duration_seconds : undefined
  return Number.isInteger(threshold) && threshold > 0 && Number.isFinite(durationSeconds) && durationSeconds > 0
    ? { threshold, durationSeconds }
    : null
}

/*
 * FR-03's record of each address this page has been given (D-130 decision 1):
 * address -> { failures, lastFailureAt, serverLockAt, serverLockSeconds }, times in
 * milliseconds or null. It lives in component state for the screen's life and in no
 * storage of any kind. Nothing in it comes from the server except the right-password
 * 403 and its `retry_after`. The policy it is read against comes from the server too,
 * the same two numbers for every caller (D-130 decision 7).
 */

/**
 * When the server's lock on `record` ends: the 403's time plus its `retry_after`, or
 * the policy's duration where the 403 gave none. Null where there is no server lock,
 * or where its length is not known yet.
 */
function serverLockEnd(record, policy) {
  if (!record || record.serverLockAt === null) return null
  const seconds = record.serverLockSeconds ?? policy?.durationSeconds ?? null
  return seconds === null ? null : record.serverLockAt + seconds * 1000
}

/**
 * When the page's own lock on `record` ends: its last failure plus the policy's
 * duration, once its count has reached the policy's threshold. Null otherwise, and
 * before the policy is known.
 */
function pageLockEnd(record, policy) {
  if (!record || !policy || record.lastFailureAt === null || record.failures < policy.threshold) return null
  return record.lastFailureAt + policy.durationSeconds * 1000
}

/** The later of `record`'s two locks' ends, or null where it has neither. */
function lockEnd(record, policy) {
  const ends = [serverLockEnd(record, policy), pageLockEnd(record, policy)].filter((end) => end !== null)
  return ends.length === 0 ? null : Math.max(...ends)
}

/** After a 401: one more consecutive failure. A locked address never gets here, because Sign in is disabled for it. */
function afterFailure(records, address, at) {
  const failures = (records[address]?.failures ?? 0) + 1
  return { ...records, [address]: { failures, lastFailureAt: at, serverLockAt: null, serverLockSeconds: null } }
}

/** After the server's 403: its lock, and the count cleared. */
function afterServerLock(records, address, at, seconds) {
  return {
    ...records,
    [address]: { failures: 0, lastFailureAt: null, serverLockAt: at, serverLockSeconds: seconds },
  }
}

/** After a success: the address's record cleared. */
function withoutAddress(records, address) {
  if (!(address in records)) return records
  const next = { ...records }
  delete next[address]
  return next
}

/** At zero: every record whose lock has ended by `at` is cleared, count and all. */
function withoutEndedLocks(records, at, policy) {
  const ended = Object.keys(records).filter((address) => {
    const end = lockEnd(records[address], policy)
    return end !== null && end <= at
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
 * 403 or a success clears the count. The threshold and the duration it reads the
 * count against are the server's running policy (decision 7), asked for once, after
 * the first failed attempt, from GET /api/auth/lockout-policy. Until it arrives the
 * page counts but shows no warning and no lock of its own, and if it never arrives
 * the page shows neither. Once LOCKOUT_WARNING_REMAINING or fewer attempts remain,
 * the warning shows; at the threshold the address enters the page's locked state,
 * with a message true of any address and a countdown from the policy's duration. A
 * 403 enters the server's locked state, counted down from its `retry_after`, or from
 * the policy's duration where it gave none. While a countdown runs for the address
 * typed, Sign in is disabled; typing another address shows that address's own
 * state. At zero the record is cleared. None of this is security: the server
 * enforces the lock whatever the page shows (CLAUDE.md §6, invariant 4), and nothing
 * the page shows depends on what the server says of an account, except the
 * right-password 403, so it is the same for an address with no account.
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
  // FR-03: the page's own record of each address (the note above `serverLockEnd`).
  const [records, setRecords] = useState({})
  // FR-03's running policy, or null until it has arrived (decision 7).
  const [policy, setPolicy] = useState(null)
  // Whether the policy has been asked for and not refused, so it is asked for once.
  const policyAsked = useRef(false)
  // The clock the countdown is read from. It is set whenever a lock begins and
  // moved on once a second while any lock runs.
  const [now, setNow] = useState(() => Date.now())

  const anyLock = Object.values(records).some((record) => {
    const end = lockEnd(record, policy)
    return end !== null && end > now
  })
  useEffect(() => {
    if (!anyLock) return undefined
    const timer = setInterval(() => {
      const at = Date.now()
      setNow(at)
      setRecords((current) => withoutEndedLocks(current, at, policy))
    }, COUNTDOWN_TICK_MS)
    return () => clearInterval(timer)
  }, [anyLock, policy])

  // Signed in, by this form or before arriving. FR-02: a role-specific dashboard, but a
  // guarded route the user was sent away from still wins, so they land where they were
  // going. This is the only navigation after sign-in, so nothing can replace it.
  if (!loading && user) {
    return <Navigate to={location.state?.from ?? dashboardPathForRole(user.role)} replace />
  }

  // FR-03's state for the address typed now.
  const record = records[normalisedAddress(values.email)]
  const lockSeconds = secondsUntil(lockEnd(record, policy), now)
  const locked = lockSeconds > 0
  // The server's lock is told, by its own message, from its 403 until it ends, even
  // while its length is not known yet.
  const serverEnd = serverLockEnd(record, policy)
  const lockedByServer = record !== undefined && record.serverLockAt !== null && (serverEnd === null || serverEnd > now)
  const remaining = policy && record ? policy.threshold - record.failures : null
  const warning =
    !locked && !lockedByServer && remaining !== null && remaining >= 1 && remaining <= LOCKOUT_WARNING_REMAINING
      ? TEXT.attemptsRemaining(remaining)
      : null
  let lockMessage = null
  if (lockedByServer) lockMessage = TEXT.accountLocked
  else if (locked) lockMessage = TEXT.accountMayBeLocked(policy.durationSeconds)

  /** Asks for the running policy once (decision 7). A refusal lets the next failure ask again. */
  function requestPolicy() {
    if (policy !== null || policyAsked.current) return
    policyAsked.current = true
    getLockoutPolicy()
      .then((body) => {
        const loaded = policyFrom(body)
        if (loaded === null) {
          policyAsked.current = false
          return
        }
        setNow(Date.now())
        setPolicy(loaded)
      })
      .catch(() => {
        policyAsked.current = false
      })
  }

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
        requestPolicy()
      } else if (error instanceof ApiError && error.status === 403 && error.code === ACCOUNT_LOCKED_CODE) {
        // FR-02: "Where the account is locked and the submitted password was
        // correct, a distinct message is shown." The server sends that 403 only to
        // the right password (FR-03's messaging rule), so it discloses the lock to
        // nobody else. Its message replaces the attempt's banner and goes with the
        // countdown, so nothing is left in the banner when the lock ends.
        const at = Date.now()
        setNow(at)
        setRecords((current) => afterServerLock(current, attempted, at, retryAfterFrom(error.details)))
        requestPolicy()
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
