import { useId } from 'react'
import './TextInput.css'

/**
 * Labelled single-line input.
 *
 * The label is wired to the input with htmlFor/id. Hint and error text are
 * linked through aria-describedby; an error also sets aria-invalid so assistive
 * technology announces the state, and carries a hidden "Error:" prefix so the
 * message is not distinguished by colour alone.
 *
 * `describedBy` appends further ids to aria-describedby, for a panel rendered
 * outside this component that still describes the field — the registration
 * form's password requirements, for one (FR-01).
 *
 * `action` renders a control beside the input, inside the same row, for the
 * "Show password" toggle FR-02 asks for. It sits after the input in the DOM, so
 * the tab order is label, input, action.
 */
export default function TextInput({
  id,
  label,
  hint,
  error,
  describedBy,
  action,
  type = 'text',
  className = '',
  ...rest
}) {
  const generatedId = useId()
  const inputId = id ?? generatedId
  const hintId = `${inputId}-hint`
  const errorId = `${inputId}-error`
  const describedByValue =
    [hint ? hintId : null, error ? errorId : null, describedBy || null].filter(Boolean).join(' ') ||
    undefined

  return (
    <div className={['field', className].filter(Boolean).join(' ')}>
      <label className="field__label" htmlFor={inputId}>
        {label}
      </label>
      {hint ? (
        <p id={hintId} className="field__hint">
          {hint}
        </p>
      ) : null}
      <div className="field__control">
        <input
          id={inputId}
          type={type}
          className="field__input"
          aria-invalid={error ? true : undefined}
          aria-describedby={describedByValue}
          {...rest}
        />
        {action}
      </div>
      {error ? (
        <p id={errorId} className="field__error">
          <span className="visually-hidden">Error: </span>
          {error}
        </p>
      ) : null}
    </div>
  )
}
