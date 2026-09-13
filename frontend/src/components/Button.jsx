import './Button.css'

/**
 * Action button in a primary or secondary variant.
 *
 * Native `disabled` disables it. `type` defaults to "button" so a Button placed
 * inside a form does not submit it by accident; pass type="submit" explicitly.
 *
 * `loading` draws the spinner FR-02 asks for ("'Login' button disables and shows
 * a loading indicator") and sets `aria-busy`. The spinner is decorative and
 * `aria-hidden`: the caller changes the label as well, which is the text
 * equivalent a screen reader reads (WCAG 2.1 SC 1.1.1).
 */
export default function Button({
  variant = 'primary',
  type = 'button',
  loading = false,
  className = '',
  children,
  ...rest
}) {
  const classes = ['btn', `btn--${variant}`, className].filter(Boolean).join(' ')
  return (
    <button type={type} className={classes} aria-busy={loading || undefined} {...rest}>
      {loading ? <span className="btn__spinner" aria-hidden="true" /> : null}
      {children}
    </button>
  )
}
