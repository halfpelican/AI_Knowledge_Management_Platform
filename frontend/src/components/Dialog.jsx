import { useEffect, useId, useRef } from 'react'
import Button from './Button.jsx'
import './Dialog.css'

/* Everything that can take focus inside the dialogue. Disabled controls are
   excluded so the trap never parks focus on one. */
const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

/**
 * Modal confirmation dialogue.
 *
 * FR-05 requires one before a role change is applied. It is a real dialogue, not
 * a panel that looks like one:
 *
 * - `role="dialog"` with `aria-modal="true"`, named by its own heading through
 *   `aria-labelledby` and described by its body through `aria-describedby`.
 * - Focus moves into it when it opens, onto the dialogue itself, so the name and
 *   description are announced before the buttons are reached.
 * - Tab and Shift+Tab cycle within it. The handler is on the document, in the
 *   capture phase, so the trap holds even when focus has slipped out.
 * - Escape cancels, from anywhere.
 * - On close, focus returns to the control that opened it. If that control has
 *   since gone or become disabled — the Save button of a row that has just been
 *   saved, for instance — focus goes to `returnFocusRef` instead, so it is never
 *   dropped on the body.
 *
 * Known limit: the content behind the dialogue is not marked `inert`, so a
 * screen reader's browse mode can still reach it even though focus cannot. The
 * keyboard, pointer and focus paths are all held.
 *
 * While `busy` the confirm button keeps its loading state and ignores further
 * presses, and cancel is disabled; the confirm button is deliberately left
 * enabled, because disabling the focused control would throw focus to the body
 * mid-request.
 */
export default function Dialog({
  title,
  confirmLabel = 'Confirm',
  busyLabel = 'Working…',
  cancelLabel = 'Cancel',
  busy = false,
  onConfirm,
  onCancel,
  returnFocusRef,
  children,
}) {
  const dialogRef = useRef(null)
  const titleId = useId()
  const bodyId = useId()

  // Opening and closing: runs once, so nothing below can steal focus back on a
  // later render. `returnFocusRef` is a ref object and stable, so listing it as
  // a dependency does not make this re-run in practice.
  useEffect(() => {
    const previouslyFocused = document.activeElement
    const fallback = returnFocusRef
    dialogRef.current?.focus()

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    return () => {
      document.body.style.overflow = previousOverflow
      if (previouslyFocused?.isConnected && !previouslyFocused.disabled) previouslyFocused.focus()
      else fallback?.current?.focus()
    }
  }, [returnFocusRef])

  // Escape and the Tab cycle. On the document and in the capture phase, so they
  // hold even if focus has slipped out of the dialogue. Re-subscribing when the
  // handler changes identity is free and moves no focus.
  useEffect(() => {
    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        event.preventDefault()
        onCancel?.()
        return
      }
      if (event.key !== 'Tab') return
      const dialog = dialogRef.current
      if (!dialog) return
      const focusable = Array.from(dialog.querySelectorAll(FOCUSABLE))
      if (focusable.length === 0) {
        event.preventDefault()
        dialog.focus()
        return
      }
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      const active = document.activeElement
      if (!dialog.contains(active)) {
        event.preventDefault()
        ;(event.shiftKey ? last : first).focus()
      } else if (event.shiftKey && active === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && active === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown, true)
    return () => document.removeEventListener('keydown', handleKeyDown, true)
  }, [onCancel])

  function handleOverlayMouseDown(event) {
    // Only a press that starts and ends on the backdrop itself cancels, so a
    // drag that began inside the dialogue does not close it.
    if (event.target === event.currentTarget && !busy) onCancel?.()
  }

  return (
    <div className="dialog-overlay" onMouseDown={handleOverlayMouseDown}>
      <div
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={bodyId}
        tabIndex={-1}
        ref={dialogRef}
      >
        <h2 className="dialog__title" id={titleId}>
          {title}
        </h2>
        <div className="dialog__body" id={bodyId}>
          {children}
        </div>
        <div className="dialog__actions">
          <Button loading={busy} onClick={() => (busy ? undefined : onConfirm?.())}>
            {busy ? busyLabel : confirmLabel}
          </Button>
          <Button variant="secondary" disabled={busy} onClick={() => onCancel?.()}>
            {cancelLabel}
          </Button>
        </div>
      </div>
    </div>
  )
}
