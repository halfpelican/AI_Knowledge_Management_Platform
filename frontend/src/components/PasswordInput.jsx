import { useId, useState } from 'react'
import Button from './Button.jsx'
import TextInput from './TextInput.jsx'
import './PasswordInput.css'

/**
 * Password field with the "Show password" toggle FR-02 asks for.
 *
 * The toggle is a real `<button>`, not an icon with a click handler, so it is in
 * the tab order and works from the keyboard. It is a toggle button: the
 * accessible name stays "Show password" and `aria-pressed` carries the state,
 * which is what a screen reader announces. Only the input's `type` attribute
 * changes, so the input is not re-mounted and neither the caret position nor the
 * focus ring on the toggle is lost.
 *
 * Name and visible text are both constant — "Show password" and the short
 * "Show", which the name contains (WCAG 2.1 SC 2.5.3) and which still fits
 * beside the input at 400px. The state is carried by `aria-pressed` and, for a
 * sighted user, by the pressed styling and by the password now being legible.
 * A label that flipped to "Hide" would contradict `aria-pressed` and would stop
 * being contained in the accessible name.
 *
 * `visible` starts false on every mount and is never lifted out of the
 * component: nothing else in the app can leave a password on screen.
 */
export default function PasswordInput({ id, toggleLabel = 'Show password', ...rest }) {
  const generatedId = useId()
  const inputId = id ?? generatedId
  const [visible, setVisible] = useState(false)

  const toggle = (
    <Button
      variant="secondary"
      className="password-toggle"
      aria-pressed={visible}
      aria-controls={inputId}
      aria-label={toggleLabel}
      onClick={() => setVisible((current) => !current)}
    >
      <span aria-hidden="true">Show</span>
    </Button>
  )

  return <TextInput {...rest} id={inputId} type={visible ? 'text' : 'password'} action={toggle} />
}
