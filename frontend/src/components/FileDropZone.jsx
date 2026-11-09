import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { TEXT } from '../constants.js'
import './Button.css'
import './TextInput.css'
import './FileDropZone.css'

/** True when a drag carries files rather than text or a link. */
function carriesFiles(event) {
  return Array.from(event.dataTransfer?.types ?? []).includes('Files')
}

/**
 * Drag-and-drop area with a file picker inside it.
 *
 * FR-08 asks for "a drag-and-drop or file-picker upload area"; this is both,
 * because dragging is a pointer gesture and nothing else. The picker is a real
 * `<input type="file">` with a real `<label>`, so every file the drop area can
 * take can also be chosen from the keyboard (WCAG 2.1 SC 2.1.1). The drop target
 * text is a visual affordance for the same action and is `aria-hidden`, since
 * announcing "drop files here" to a screen reader offers something it cannot do.
 *
 * `onFiles` receives an array of File objects from either route. The caller
 * screens them — format and size (src/utils/uploads.js) — because neither the
 * `accept` attribute nor this component decides anything: `accept` only filters
 * what the picker shows by default, and a dropped file bypasses it entirely.
 *
 * **What the zone says is the component's own, not the browser's** (usability
 * findings 1 and 2). The input's value is cleared after each change so choosing
 * the same file twice in a row still fires, which snaps the browser's own label
 * back to "No file chosen" the moment a file is chosen. So the native input is
 * visually hidden, its `<label>` is drawn as the button, and `status` — the
 * caller's sentence for what the last pick or drop did — is shown inside the zone,
 * where the pointer was released, in a polite live region. Sighted and screen
 * reader users are told the same words. The input keeps the keyboard focus, and
 * FileDropZone.css draws the focus ring on the label beside it.
 *
 * **A disabled zone says why** (finding 4). `disabledReason` replaces the status
 * while `disabled`, and a drop made meanwhile is answered with
 * `TEXT.dropZoneRefused` rather than vanishing.
 *
 * **`pageDrop` widens the target to the whole page** (finding 3). A file dropped
 * a little outside the zone used to be taken by the browser, which navigated to
 * it and lost the screen. With `pageDrop`, a file dragged anywhere over the page
 * lights the zone up, and a drop anywhere is the zone's drop. Only drags carrying
 * files are taken; text dragged into a field elsewhere behaves as it always did.
 */
export default function FileDropZone({
  id,
  label,
  hint,
  accept,
  multiple = false,
  disabled = false,
  disabledReason,
  error,
  status,
  pageDrop = false,
  onFiles,
}) {
  const generatedId = useId()
  const inputId = id ?? generatedId
  const hintId = `${inputId}-hint`
  const errorId = `${inputId}-error`
  const [dragging, setDragging] = useState(false)
  // Set when a drop lands while the zone is disabled, and cleared once it is not.
  const [refused, setRefused] = useState(false)
  const zoneRef = useRef(null)
  const describedBy =
    [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(' ') || undefined

  // The page-wide listeners read the current props through this, so they are
  // added once per mount rather than on every render of the page. receive()
  // reads it too, for the input's change and the zone's own drop.
  //
  // A layout effect, not a passive one: it runs inside the commit, so the ref
  // matches the committed props before the browser can deliver another event.
  // A passive effect left a gap after an upload finished in which the zone was
  // enabled on screen but receive() still read disabled, so a file chosen or
  // dropped at once was refused and, the refusal clearing on the next render,
  // silently lost. Two CI flakes showed it on 10 November (ingestionLimits'
  // D-85 queue test and dropZone's finding 4).
  const latest = useRef({ disabled, multiple, onFiles })
  useLayoutEffect(() => {
    latest.current = { disabled, multiple, onFiles }
  })

  // A refusal is about the upload that was running. Once the zone is enabled
  // again it goes, and the ordinary status returns.
  if (!disabled && refused) setRefused(false)

  function receive(fileList) {
    const { disabled: off, multiple: many, onFiles: emit } = latest.current
    if (off) {
      setRefused(true)
      return
    }
    const files = Array.from(fileList ?? [])
    if (files.length > 0) emit(many ? files : files.slice(0, 1))
  }

  function handleDrop(event) {
    event.preventDefault()
    setDragging(false)
    receive(event.dataTransfer?.files)
  }

  function handleDragOver(event) {
    // Without preventDefault the browser navigates to the dropped file instead.
    event.preventDefault()
    if (event.dataTransfer) event.dataTransfer.dropEffect = disabled ? 'none' : 'copy'
    if (!disabled) setDragging(true)
  }

  function handleDragLeave(event) {
    // With the whole page as the target, leaving the zone is not leaving the
    // target: only leaving the window is.
    if (!pageDrop || event.relatedTarget === null) setDragging(false)
  }

  useEffect(() => {
    if (!pageDrop) return undefined
    function over(event) {
      if (!carriesFiles(event)) return
      event.preventDefault()
      const off = latest.current.disabled
      if (event.dataTransfer) event.dataTransfer.dropEffect = off ? 'none' : 'copy'
      if (!off) setDragging(true)
    }
    function leave(event) {
      // relatedTarget is null only when the drag has left the window.
      if (event.relatedTarget === null) setDragging(false)
    }
    function drop(event) {
      if (!carriesFiles(event)) return
      event.preventDefault()
      setDragging(false)
      // A drop on the zone itself has been taken by the zone's own handler.
      if (zoneRef.current?.contains(event.target)) return
      receive(event.dataTransfer?.files)
    }
    window.addEventListener('dragover', over)
    window.addEventListener('dragleave', leave)
    window.addEventListener('drop', drop)
    return () => {
      window.removeEventListener('dragover', over)
      window.removeEventListener('dragleave', leave)
      window.removeEventListener('drop', drop)
    }
  }, [pageDrop])

  let shownStatus = status
  if (disabled) shownStatus = refused ? TEXT.dropZoneRefused : disabledReason

  return (
    <div
      ref={zoneRef}
      className={['dropzone', dragging ? 'dropzone--active' : ''].filter(Boolean).join(' ')}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <div className="field dropzone__field">
        {/* The input comes before its label, so FileDropZone.css can draw the
            input's focus ring on the label with a sibling selector. */}
        <input
          id={inputId}
          className="visually-hidden dropzone__input"
          type="file"
          accept={accept}
          multiple={multiple}
          disabled={disabled}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          onChange={(event) => {
            receive(event.target.files)
            event.target.value = ''
          }}
        />
        <label className="btn btn--secondary dropzone__choose" htmlFor={inputId}>
          {label}
        </label>
        <p className="dropzone__target" aria-hidden="true">
          {TEXT.uploadDropTarget}
        </p>
        {hint ? (
          <p id={hintId} className="field__hint">
            {hint}
          </p>
        ) : null}
        {/* Always mounted, so a change is announced as well as shown. */}
        <p className="dropzone__status" role="status" aria-live="polite">
          {shownStatus}
        </p>
        {error ? (
          <p id={errorId} className="field__error">
            <span className="visually-hidden">Error: </span>
            {error}
          </p>
        ) : null}
      </div>
    </div>
  )
}
