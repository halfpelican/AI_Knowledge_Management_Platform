import { useId } from 'react'
import './TextInput.css'
import './TextAreaInput.css'

/**
 * Labelled multi-line input, for FR-09's "paste transcript text directly into a
 * form".
 *
 * Same wiring as TextInput, which is deliberate: label via htmlFor/id, hint and
 * error through aria-describedby, aria-invalid on error, and the hidden "Error:"
 * prefix so the message is not distinguished by colour alone. A native textarea
 * is resizable and keyboard-operable without any extra script.
 */
export default function TextAreaInput({ id, label, hint, error, describedBy, className = '', ...rest }) {
  const generatedId = useId()
  const areaId = id ?? generatedId
  const hintId = `${areaId}-hint`
  const errorId = `${areaId}-error`
  const describedByValue =
    [hint ? hintId : null, error ? errorId : null, describedBy || null].filter(Boolean).join(' ') ||
    undefined

  return (
    <div className={['field', className].filter(Boolean).join(' ')}>
      <label className="field__label" htmlFor={areaId}>
        {label}
      </label>
      {hint ? (
        <p id={hintId} className="field__hint">
          {hint}
        </p>
      ) : null}
      <textarea
        id={areaId}
        className="field__input textarea-field__control"
        aria-invalid={error ? true : undefined}
        aria-describedby={describedByValue}
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
