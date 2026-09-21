import { useId, useState } from 'react'
import { TEXT } from '../constants.js'
import './TextInput.css'
import './FileDropZone.css'

/**
 * Drag-and-drop area with a file picker inside it.
 *
 * FR-08 asks for "a drag-and-drop or file-picker upload area"; this is both,
 * because dragging is a pointer gesture and nothing else. The picker is a real
 * `<input type="file">` with a real `<label>`, so every file the drop area can
 * take can also be chosen from the keyboard (WCAG 2.1 SC 2.1.1). The drop target
 * is a visual affordance for the same action and is `aria-hidden`, since
 * announcing "drop files here" to a screen reader offers something it cannot do.
 *
 * `onFiles` receives an array of File objects from either route. The caller
 * screens them — format and size (src/utils/uploads.js) — because neither the
 * `accept` attribute nor this component decides anything: `accept` only filters
 * what the picker shows by default, and a dropped file bypasses it entirely.
 *
 * The input's value is cleared after each change so choosing the same file twice
 * in a row still fires.
 */
export default function FileDropZone({
  id,
  label,
  hint,
  accept,
  multiple = false,
  disabled = false,
  error,
  onFiles,
}) {
  const generatedId = useId()
  const inputId = id ?? generatedId
  const hintId = `${inputId}-hint`
  const errorId = `${inputId}-error`
  const [dragging, setDragging] = useState(false)
  const describedBy =
    [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(' ') || undefined

  function emit(fileList) {
    const files = Array.from(fileList ?? [])
    if (files.length > 0) onFiles(multiple ? files : files.slice(0, 1))
  }

  function handleDrop(event) {
    event.preventDefault()
    setDragging(false)
    if (disabled) return
    emit(event.dataTransfer?.files)
  }

  function handleDragOver(event) {
    // Without preventDefault the browser navigates to the dropped file instead.
    event.preventDefault()
    if (!disabled) setDragging(true)
  }

  return (
    <div
      className={['dropzone', dragging ? 'dropzone--active' : ''].filter(Boolean).join(' ')}
      onDragOver={handleDragOver}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
    >
      <div className="field">
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
          className="dropzone__input"
          type="file"
          accept={accept}
          multiple={multiple}
          disabled={disabled}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          onChange={(event) => {
            emit(event.target.files)
            event.target.value = ''
          }}
        />
        {error ? (
          <p id={errorId} className="field__error">
            <span className="visually-hidden">Error: </span>
            {error}
          </p>
        ) : null}
      </div>
      <p className="dropzone__target" aria-hidden="true">
        {TEXT.uploadDropTarget}
      </p>
    </div>
  )
}
