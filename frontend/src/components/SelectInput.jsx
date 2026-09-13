import { useId } from 'react'
import './TextInput.css'
import './SelectInput.css'

/**
 * Labelled native select. Same wiring as TextInput: label via htmlFor/id,
 * hint and error via aria-describedby, aria-invalid on error. A native select
 * is keyboard-operable everywhere without any extra script.
 *
 * `options` is [{ value, label }]. The label may be visually hidden (for a
 * table cell whose column header already names it) with `labelHidden`.
 */
export default function SelectInput({
  id,
  label,
  labelHidden = false,
  hint,
  error,
  options,
  className = '',
  ...rest
}) {
  const generatedId = useId()
  const selectId = id ?? generatedId
  const hintId = `${selectId}-hint`
  const errorId = `${selectId}-error`
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(' ') || undefined

  return (
    <div className={['field', 'select-field', className].filter(Boolean).join(' ')}>
      <label className={labelHidden ? 'visually-hidden' : 'field__label'} htmlFor={selectId}>
        {label}
      </label>
      {hint ? (
        <p id={hintId} className="field__hint">
          {hint}
        </p>
      ) : null}
      <select
        id={selectId}
        className="field__input select-field__control"
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        {...rest}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {error ? (
        <p id={errorId} className="field__error">
          <span className="visually-hidden">Error: </span>
          {error}
        </p>
      ) : null}
    </div>
  )
}
