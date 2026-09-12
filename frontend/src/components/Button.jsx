import './Button.css'

/**
 * Action button in a primary or secondary variant.
 *
 * Native `disabled` disables it. `type` defaults to "button" so a Button placed
 * inside a form does not submit it by accident; pass type="submit" explicitly.
 */
export default function Button({ variant = 'primary', type = 'button', className = '', children, ...rest }) {
  const classes = ['btn', `btn--${variant}`, className].filter(Boolean).join(' ')
  return (
    <button type={type} className={classes} {...rest}>
      {children}
    </button>
  )
}
