import { useRef, useState } from 'react'
import { TEXT } from '../constants.js'
import Button from './Button.jsx'
import SelectInput from './SelectInput.jsx'
import './AttendeePicker.css'

/**
 * FR-09's attendee association: choose people one at a time and see who is
 * chosen.
 *
 * This replaces a native multi-select listbox, where selecting a second person
 * needed Ctrl+click, nothing said so, and the natural gesture silently undid the
 * first choice — a meeting was ingested with zero attendees before anyone
 * noticed (usability finding 5). The finding offers checkboxes for a handful of
 * people or a combobox-with-Add once it is a real organisation; this is the
 * second shape in its plainest form. A native single select needs no modifier
 * keys, is keyboard- and switch-operable everywhere, finds a name by typing,
 * and does not stop working at 500 staff. Each Add appends to a visible list,
 * so the state is on the screen rather than in a selection pattern, and each
 * entry has its own Remove button named for the person it removes.
 *
 * Adding and removing are announced through a polite live region in the same
 * words the list shows. After either, focus returns to the select, because the
 * control that was pressed may no longer exist (Remove) or be about to lose its
 * use (the last person added).
 *
 * Attendance is a participation record and never an access control (D-16,
 * CLAUDE.md §6, invariant 3); the hint the caller passes says so.
 *
 * @param {object} props
 * @param {string} props.legend
 * @param {string} [props.hint]
 * @param {{id: string, name: string, email: string}[]} props.options The directory (D-34).
 * @param {string[]} props.value Ids already chosen, in the order they were added.
 * @param {(ids: string[]) => void} props.onChange
 * @param {boolean} [props.disabled]
 * @param {string} [props.error] The server's `attendees` message, when it refused them.
 */
export default function AttendeePicker({ legend, hint, options, value, onChange, disabled = false, error }) {
  const [choice, setChoice] = useState('')
  const [announcement, setAnnouncement] = useState('')
  const selectRef = useRef(null)

  const byId = new Map(options.map((person) => [person.id, person]))
  const chosen = value.map((id) => byId.get(id)).filter(Boolean)
  const remaining = options.filter((person) => !value.includes(person.id))
  const label = (person) => `${person.name} (${person.email})`

  function handleAdd() {
    const person = byId.get(choice)
    if (!person || value.includes(person.id)) return
    onChange([...value, person.id])
    setChoice('')
    setAnnouncement(TEXT.attendeeAdded(label(person)))
    selectRef.current?.focus()
  }

  function handleRemove(person) {
    onChange(value.filter((id) => id !== person.id))
    setAnnouncement(TEXT.attendeeRemoved(label(person)))
    // The button just pressed is gone with its row, so focus is moved somewhere
    // deliberate rather than dropped on the page.
    selectRef.current?.focus()
  }

  return (
    <fieldset className="attendee-picker" disabled={disabled}>
      <legend>{legend}</legend>
      {hint ? <p className="field__hint attendee-picker__hint">{hint}</p> : null}

      <div className="attendee-picker__row">
        <SelectInput
          className="select-field--inline attendee-picker__select"
          label={TEXT.attendeeAddLabel}
          ref={selectRef}
          value={choice}
          error={error}
          options={
            remaining.length > 0
              ? [{ value: '', label: TEXT.attendeeChoosePrompt }, ...remaining.map((person) => ({ value: person.id, label: label(person) }))]
              : [{ value: '', label: TEXT.attendeeAllAdded }]
          }
          onChange={(event) => setChoice(event.target.value)}
        />
        <Button variant="secondary" className="attendee-picker__add" disabled={disabled || !choice} onClick={handleAdd}>
          {TEXT.attendeeAddButton}
        </Button>
      </div>

      {chosen.length > 0 ? (
        <ul className="attendee-picker__list" aria-label={TEXT.attendeeListLabel}>
          {chosen.map((person) => (
            <li key={person.id} className="attendee-picker__person">
              <span className="attendee-picker__name">{label(person)}</span>
              <Button
                variant="secondary"
                className="attendee-picker__remove"
                aria-label={TEXT.attendeeRemoveLabel(label(person))}
                onClick={() => handleRemove(person)}
              >
                {TEXT.attendeeRemove}
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="attendee-picker__empty">{TEXT.attendeeNoneYet}</p>
      )}

      {/* The list above is the visible record; this tells assistive technology
          about the change just made, in the same words. */}
      <p className="visually-hidden" role="status" aria-live="polite">
        {announcement}
      </p>
    </fieldset>
  )
}
