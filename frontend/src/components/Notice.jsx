import './Notice.css'

const ROLE_BY_VARIANT = {
  info: 'status', // polite: read at the next pause, does not interrupt
  error: 'alert', // assertive: announced immediately
  unavailable: 'alert', // the AI service is down (NFR-19): announced immediately
}

const DEFAULT_TITLE_BY_VARIANT = {
  unavailable: 'AI service unavailable',
}

/**
 * Inline message panel.
 *
 * `info` is a polite status; `error` and `unavailable` are alerts. The
 * `unavailable` variant is the NFR-19 notice shown the moment the API answers
 * 503, in place of a spinner that never resolves.
 */
export default function Notice({ variant = 'info', title, className = '', children }) {
  const role = ROLE_BY_VARIANT[variant] ?? 'status'
  const heading = title ?? DEFAULT_TITLE_BY_VARIANT[variant]
  const classes = ['notice', `notice--${variant}`, className].filter(Boolean).join(' ')

  return (
    <div className={classes} role={role}>
      {heading ? <p className="notice__title">{heading}</p> : null}
      <div className="notice__body">{children}</div>
    </div>
  )
}
