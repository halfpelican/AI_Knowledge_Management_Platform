import { useId } from 'react'
import './TextInput.css'

/**
 * Labelled single-line input.
 *
 * The label is wired to the input with htmlFor/id. Hint and error text are
 * linked through aria-describedby; an error also sets aria-invalid so assistive
 * technology announces the state, and carries a hidden "Error:" prefix so the
 * message is not distinguished by colour alone.
 */
export default function TextInput({ id, label, hint, error, type = 'text', className = '', ...rest }) {
  const generatedId = useId()
  const inputId = id ?? generatedId
  const hintId = `${inputId}-hint`
  const errorId = `${inputId}-error`
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(' ') || undefined

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
      <input
        id={inputId}
        type={type}
        className="field__input"
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        {...rest}
      />
      {error ? (
        <p id={errorId} className="field__error">
          <span className="visually-hidden">Error: </span>
          {error}
        </p>
      ) : null}
    </div>
  )
}
