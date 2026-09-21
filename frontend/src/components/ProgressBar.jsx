import './ProgressBar.css'

/**
 * Progress bar, determinate or indeterminate.
 *
 * FR-08: "Each file shows a progress indicator and an individual progress bar
 * during upload", so one of these belongs to each queued file rather than one
 * belonging to the page.
 *
 * `value` is a percentage. Pass a number for a transfer whose size is known and
 * `null` for work whose duration is not — the wait while the server extracts,
 * chunks and embeds, which is synchronous and reports nothing until it answers.
 * An indeterminate bar deliberately carries no `aria-valuenow`: a value of zero
 * would be read as "no progress" rather than "unknown".
 *
 * The bar is a non-text representation, so the same information is present as
 * text beside it and as `aria-valuetext` (WCAG 2.1 SC 1.1.1). The filled portion
 * is decorative and `aria-hidden`; the `progressbar` element above it is what
 * assistive technology reads.
 */
export default function ProgressBar({ label, value = null, valueText, className = '' }) {
  const determinate = typeof value === 'number' && Number.isFinite(value)
  const percent = determinate ? Math.max(0, Math.min(100, Math.round(value))) : 0
  const text = valueText ?? (determinate ? `${percent}%` : '')
  const classes = ['progress', determinate ? '' : 'progress--indeterminate', className]
    .filter(Boolean)
    .join(' ')

  return (
    <div className={classes}>
      <div
        className="progress__track"
        role="progressbar"
        aria-label={label}
        aria-valuemin={determinate ? 0 : undefined}
        aria-valuemax={determinate ? 100 : undefined}
        aria-valuenow={determinate ? percent : undefined}
        aria-valuetext={text || undefined}
      >
        {/* Width comes from the stylesheet while the duration is unknown, so the
            travelling band is not fixed at 0% by an inline style. */}
        <span
          className="progress__fill"
          style={determinate ? { width: `${percent}%` } : undefined}
          aria-hidden="true"
        />
      </div>
      {text ? (
        <span className="progress__value" aria-hidden="true">
          {text}
        </span>
      ) : null}
    </div>
  )
}
