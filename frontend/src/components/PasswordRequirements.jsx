import { evaluatePassword } from '../utils/password.js'
import './PasswordRequirements.css'

/**
 * FR-01's real-time password strength validation: "password strength meter shown
 * as user types (e.g., 'must contain 1 uppercase letter, 1 number, 1 special
 * character, minimum 8 characters')".
 *
 * Every rule is listed with its own met/unmet state rather than only a score, so
 * the user can see which one is outstanding. The rules and the tests come from
 * src/utils/password.js, the one copy of the policy the server enforces.
 *
 * Accessibility:
 *
 * - The meter bar is decorative and `aria-hidden`. The sentence beside it
 *   ("Password strength: Fair. 3 of 4 requirements met.") is its text equivalent
 *   (WCAG 2.1 SC 1.1.1), and that sentence is visible, not hidden.
 * - Each rule carries a visually hidden "Met:" or "Not met:" prefix, so the
 *   state reaches a screen reader and is never colour alone (SC 1.4.1). The tick
 *   and dash glyphs are `aria-hidden` decoration for the same reason.
 * - The live region is a separate, visually hidden `role="status"` sibling — not
 *   inside the element the field's `aria-describedby` points at, or its text
 *   would be read twice. It holds only the summary sentence, so it announces
 *   once per change of state rather than on every keystroke.
 *
 * @param {object} props
 * @param {string} props.password Current value of the password field.
 * @param {string} props.id Id the password field's aria-describedby points at.
 */
export default function PasswordRequirements({ password, id }) {
  const { results, metCount, total, strength, strengthLabel, summary } = evaluatePassword(password)
  const percentage = Math.round((metCount / total) * 100)

  return (
    <div className="password-req">
      <div id={id} className="password-req__panel">
        <p className="password-req__summary">
          Password strength: <strong>{strengthLabel}</strong>. {metCount} of {total} requirements
          met.
        </p>
        <div className="password-req__meter" aria-hidden="true">
          <span
            className="password-req__meter-fill"
            data-strength={strength}
            style={{ width: `${percentage}%` }}
          />
        </div>
        <ul className="password-req__list">
          {results.map((rule) => (
            <li
              key={rule.id}
              className={`password-req__item${rule.met ? ' password-req__item--met' : ''}`}
            >
              <span className="password-req__glyph" aria-hidden="true">
                {rule.met ? '✓' : '–'}
              </span>
              <span className="visually-hidden">{rule.met ? 'Met: ' : 'Not met: '}</span>
              {rule.label}
            </li>
          ))}
        </ul>
      </div>
      <p className="visually-hidden" role="status">
        {summary}
      </p>
    </div>
  )
}
