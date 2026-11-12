import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { ApiError, NETWORK_ERROR_STATUS, messageForStatus } from '../api/client.js'
import { addActionItem, deleteActionItem, updateActionItem } from '../api/meetings.js'
import { listUserDirectory } from '../api/users.js'
import { ACTION_ITEM_ORIGIN, TEXT, VALIDATION } from '../constants.js'
import useApiResource from '../hooks/useApiResource.js'
import usePassagePanels from '../hooks/usePassagePanels.js'
import { formatDate } from '../utils/dates.js'
import { extractFieldErrors } from '../utils/fieldErrors.js'
import { passageNumbers, passageText } from '../utils/passages.js'
import AiMark, { PersonMark } from './AiMark.jsx'
import Button from './Button.jsx'
import Dialog from './Dialog.jsx'
import Notice from './Notice.jsx'
import { PassageMarkers, PassagePanels } from './PassageReferences.jsx'
import SelectInput from './SelectInput.jsx'
import TextAreaInput from './TextAreaInput.jsx'
import TextInput from './TextInput.jsx'
import './ActionItems.css'

/** The API's own field names, so a 400's message lands beside the control it concerns. */
const FIELDS = ['description', 'owner_id', 'due_date']

/** An empty form, for an item added by hand. */
const BLANK = { description: '', ownerId: '', dueDate: '' }

/** Text the transcript gave, or "" where it gave none (and on an item a person added). */
function said(value) {
  return typeof value === 'string' ? value.trim() : ''
}

/** A hint built of whichever of its sentences apply, or none at all. */
function hintOf(...sentences) {
  return sentences.filter(Boolean).join(' ') || undefined
}

/**
 * The owner choices: "Unassigned", then the directory as the server ordered it. An
 * item's current owner is listed even where the directory did not arrive or no
 * longer names them, so the form shows who the owner is and saving it untouched
 * changes nothing.
 */
function ownerOptions(people, currentOwner) {
  const options = [{ value: '', label: TEXT.actionItemUnassigned }]
  for (const person of people) {
    options.push({ value: person.id, label: `${person.name} (${person.email})` })
  }
  if (currentOwner && !people.some((person) => person.id === currentOwner.id)) {
    options.push({ value: currentOwner.id, label: currentOwner.name })
  }
  return options
}

/**
 * The form an action item is edited in, and a new one is added in: FR-16's
 * "description, suggested owner and due date, all editable".
 *
 * The description is required, and a blank one is refused here before anything is
 * sent. The owner is a native select of the directory's people and "Unassigned";
 * the due date a native date input, which is cleared to record no date. A 400's
 * messages are DRF's, written for the person typing, and each is shown beside the
 * field it names, with focus on the first.
 *
 * It opens on its first field. `onSubmit` is given the values as they would be
 * stored (the description trimmed, `null` for no owner and for no date) and
 * resolves to the field messages of a 400, or to null for anything else: saved,
 * or a failure the panel has already said.
 */
function ActionItemForm({
  legend,
  submitLabel,
  busyLabel,
  initial,
  currentOwner = null,
  ownerSaid = '',
  dueSaid = '',
  directory,
  onSubmit,
  onCancel,
}) {
  const legendId = useId()
  const descriptionRef = useRef(null)
  const ownerRef = useRef(null)
  const dueRef = useRef(null)
  // One request per press, even if Save is pressed again before the busy state
  // has rendered.
  const inFlight = useRef(false)
  const [values, setValues] = useState(initial)
  const [errors, setErrors] = useState({})
  const [saving, setSaving] = useState(false)
  // The field a refusal was placed beside. A new object each time, so the same
  // field twice running still takes focus.
  const [focusRequest, setFocusRequest] = useState(null)

  useEffect(() => {
    descriptionRef.current?.focus()
  }, [])

  useEffect(() => {
    if (!focusRequest) return
    const target = { description: descriptionRef, owner_id: ownerRef, due_date: dueRef }[focusRequest.field]
    target?.current?.focus()
  }, [focusRequest])

  function change(name, value, field) {
    setValues((current) => ({ ...current, [name]: value }))
    setErrors((current) => ({ ...current, [field]: undefined }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (inFlight.current) return
    const description = values.description.trim()
    if (!description) {
      setErrors({ description: VALIDATION.actionItemDescriptionRequired })
      setFocusRequest({ field: 'description' })
      return
    }
    inFlight.current = true
    setSaving(true)
    setErrors({})
    const refused = await onSubmit({
      description,
      ownerId: values.ownerId || null,
      dueDate: values.dueDate || null,
    })
    inFlight.current = false
    setSaving(false)
    if (refused) {
      setErrors(refused)
      const first = FIELDS.find((field) => refused[field])
      if (first) setFocusRequest({ field: first })
    }
  }

  return (
    <form className="action-item__form" aria-labelledby={legendId} onSubmit={handleSubmit} noValidate>
      <fieldset className="action-item__fieldset">
        <legend id={legendId} className="action-item__legend">
          {legend}
        </legend>
        <TextAreaInput
          ref={descriptionRef}
          className="action-item__description-field"
          label={TEXT.actionItemDescription}
          name="description"
          rows={3}
          value={values.description}
          error={errors.description}
          required
          onChange={(event) => change('description', event.target.value, 'description')}
        />
        <SelectInput
          ref={ownerRef}
          label={TEXT.actionItemOwner}
          name="owner_id"
          // What the meeting called the owner, beside the choice of who it is.
          hint={hintOf(
            ownerSaid ? `${TEXT.actionItemOwnerSaid(ownerSaid)}.` : null,
            directory.loading ? TEXT.loadingAttendees : null,
            directory.failed ? TEXT.actionItemOwnerUnavailable : null,
          )}
          options={ownerOptions(directory.people, currentOwner)}
          value={values.ownerId}
          error={errors.owner_id}
          onChange={(event) => change('ownerId', event.target.value, 'owner_id')}
        />
        <TextInput
          ref={dueRef}
          label={TEXT.actionItemDue}
          name="due_date"
          type="date"
          hint={hintOf(dueSaid ? `${TEXT.actionItemDueSaid(dueSaid)}.` : null, TEXT.actionItemDueHint)}
          value={values.dueDate}
          error={errors.due_date}
          onChange={(event) => change('dueDate', event.target.value, 'due_date')}
        />
      </fieldset>
      <div className="action-item__actions">
        <Button type="submit" loading={saving}>
          {saving ? busyLabel : submitLabel}
        </Button>
        <Button variant="secondary" disabled={saving} onClick={onCancel}>
          {TEXT.actionItemCancel}
        </Button>
      </div>
    </form>
  )
}

/**
 * One action item: its description, its owner and its due date, with what the
 * meeting itself said of each, the passages it came from, and whose it is.
 *
 * **The owner is a person or the word "Unassigned"** (FR-16: "where no confident
 * match exists the item is stored as unassigned rather than attributed to the
 * wrong person"), and the transcript's own name for them is kept beside it, so
 * "the facilities team" stays readable where nobody was matched. The due date is
 * shown the same way: the date the server worked out, or that none is set, and
 * the phrase that was said.
 *
 * **Whose it is, in words** (NFR-15): an extracted item is "Suggested by AI",
 * "Suggested by AI, edited by a person" once a person has changed it, inside the
 * dashed boundary AI content has. An item a person added carries no AI mark: it
 * reads "Added by a person" inside a solid one, as FR-10's tags do.
 *
 * Each row keeps its own edit form, so opening one never discards another's
 * unsaved changes. The controls are there only while `canEdit`.
 */
function ActionItem({ item, passages, canEdit, directory, onWantDirectory, onSave, onAskDelete }) {
  const idPrefix = useId()
  const [open, toggle] = usePassagePanels()
  const [editing, setEditing] = useState(false)
  const editButtonRef = useRef(null)
  // Set when the form closes, so focus follows the Edit button back onto the page.
  const returnFocus = useRef(false)

  const numbers = passageNumbers(item)
  const ai = item.origin === ACTION_ITEM_ORIGIN.ai
  const ownerSaid = said(item.owner_name)
  const dueSaid = said(item.due_text)
  const showForm = editing && canEdit

  useEffect(() => {
    if (showForm || !returnFocus.current) return
    returnFocus.current = false
    editButtonRef.current?.focus()
  }, [showForm])

  function openEdit() {
    onWantDirectory()
    setEditing(true)
  }

  function closeEdit() {
    returnFocus.current = true
    setEditing(false)
  }

  async function save(values) {
    const outcome = await onSave(item, values)
    if (outcome.done) closeEdit()
    return outcome.fieldErrors ?? null
  }

  return (
    <li className={`action-item ${ai ? 'ai-content' : 'person-content'}`}>
      {showForm ? (
        <ActionItemForm
          legend={TEXT.actionItemEditLegend}
          submitLabel={TEXT.actionItemSave}
          busyLabel={TEXT.actionItemSaving}
          initial={{
            description: item.description ?? '',
            ownerId: item.owner?.id ?? '',
            dueDate: item.due_date ?? '',
          }}
          currentOwner={item.owner ?? null}
          ownerSaid={ownerSaid}
          dueSaid={dueSaid}
          directory={directory}
          onSubmit={save}
          onCancel={closeEdit}
        />
      ) : (
        <>
          <p className="action-item__description">
            {item.description}
            <PassageMarkers
              idPrefix={idPrefix}
              numbers={numbers}
              passages={passages}
              open={open}
              onToggle={toggle}
            />
          </p>
          <dl className="action-item__facts">
            <div className="action-item__fact">
              <dt>{TEXT.actionItemOwner}</dt>
              <dd>
                <span className="action-item__value">{item.owner ? item.owner.name : TEXT.actionItemUnassigned}</span>
                {ownerSaid ? <span className="action-item__said">{TEXT.actionItemOwnerSaid(ownerSaid)}</span> : null}
              </dd>
            </div>
            <div className="action-item__fact">
              <dt>{TEXT.actionItemDue}</dt>
              <dd>
                <span className="action-item__value">
                  {item.due_date ? (
                    <time dateTime={item.due_date}>{formatDate(item.due_date) || item.due_date}</time>
                  ) : (
                    TEXT.actionItemNoDate
                  )}
                </span>
                {dueSaid ? <span className="action-item__said">{TEXT.actionItemDueSaid(dueSaid)}</span> : null}
              </dd>
            </div>
          </dl>
          <PassagePanels idPrefix={idPrefix} numbers={numbers} passages={passages} open={open} />
          <div className="action-item__footer">
            {ai ? <AiMark edited={item.edited === true} /> : <PersonMark />}
            {canEdit ? (
              <span className="action-item__actions">
                <Button
                  ref={editButtonRef}
                  variant="secondary"
                  aria-label={TEXT.actionItemEditLabel(item.description)}
                  onClick={openEdit}
                >
                  {TEXT.actionItemEdit}
                </Button>
                <Button
                  variant="secondary"
                  aria-label={TEXT.actionItemDeleteLabel(item.description)}
                  onClick={() => onAskDelete(item)}
                >
                  {TEXT.actionItemDelete}
                </Button>
              </span>
            ) : null}
          </div>
        </>
      )}
    </li>
  )
}

/**
 * FR-16's "Action Items" panel: "lists each extracted item with description,
 * suggested owner and due date, all editable. Users can edit, delete or manually
 * add items the extraction missed; deletion requires confirmation."
 *
 * **The list is the server's, in the server's order**: extracted items in the
 * model's order, then the ones people added. A write changes it from its reply and
 * nothing else: an edit replaces the row with the item the PATCH returned, an add
 * appends the POST's, and a delete removes the row on its 204. An edit sends only
 * the fields that changed, `null` for an owner or a date cleared, and nothing at
 * all when nothing changed.
 *
 * **An empty list says which kind of empty it is.** Under a Ready summary whose
 * run extracted none, that no action items were raised (UC-04 A1: "records the
 * action item section as empty rather than omitting it"); otherwise, that there
 * are none yet.
 *
 * **Deletion asks first**, in the shared Dialog, quoting the item, and sends
 * nothing until it is confirmed.
 *
 * **Authorisation is the server's.** The controls are offered when the summary
 * state says `can_edit`, which is a hint; every write checks `contribute_content`
 * (CLAUDE.md §6, invariant 4). A 403 withdraws them and says why in words. A 404
 * means the item or the meeting has gone, or is now out of scope: one message for
 * all of them (invariant 1), and the panel is read again.
 *
 * Descriptions and names are the model's or a person's text: rendered as text
 * children only, never as HTML.
 *
 * @param {object} props
 * @param {string} props.meetingId
 * @param {boolean} [props.loading] The summary state has not arrived yet.
 * @param {boolean} [props.unavailable] Its read failed; the Summary panel says how.
 * @param {object[]} props.items The state's `action_items`.
 * @param {Record<string, string>|null} [props.passages] The current summary's `passages`.
 * @param {boolean} [props.noneRaised] A Ready summary whose `action_items_extracted` is 0.
 * @param {boolean} props.canEdit `can_edit`, and no write has been refused.
 * @param {(updater: (items: object[]) => object[]) => void} [props.onItemsChange]
 * @param {() => void} [props.onRefused] A write answered 403.
 * @param {() => void} [props.onStale] A write answered 404: read the panel again.
 */
export default function ActionItems({
  meetingId,
  loading = false,
  unavailable = false,
  items,
  passages = null,
  noneRaised = false,
  canEdit,
  onItemsChange = () => {},
  onRefused = () => {},
  onStale = () => {},
}) {
  const headingId = useId()
  const headingRef = useRef(null)
  const addButtonRef = useRef(null)
  const returnFocusToAdd = useRef(false)
  const [adding, setAdding] = useState(false)
  // The item whose confirmation is open, and whether its DELETE is in flight. The
  // ref is the guard: one DELETE per confirmation.
  const [confirming, setConfirming] = useState(null)
  const [deleting, setDeleting] = useState(false)
  const deleteInFlight = useRef(false)
  // The outcome of the last action: what was done, announced in a live region, or
  // why it was not, in an alert. A new object each time, for the focus effect.
  const [outcome, setOutcome] = useState(null)

  // The people an owner is chosen from (D-34), read when a form first opens and
  // not before: most visits to a meeting change nothing.
  const [directoryWanted, setDirectoryWanted] = useState(false)
  const loadDirectory = useCallback(
    ({ signal }) => (directoryWanted ? listUserDirectory({ signal }) : Promise.resolve(null)),
    [directoryWanted],
  )
  const directoryResource = useApiResource(loadDirectory)
  const people = Array.isArray(directoryResource.data)
    ? directoryResource.data.filter((person) => typeof person?.id === 'string')
    : null
  const directory = {
    people: people ?? [],
    loading: directoryWanted && people === null && !directoryResource.error,
    failed: directoryWanted && Boolean(directoryResource.error),
  }

  const showAddForm = adding && canEdit

  // After an action the control that was pressed may have left the page: a
  // deleted row's button, a form that closed, every control on a 403. Focus then
  // goes to the heading, under which the outcome is said.
  useEffect(() => {
    if (!outcome) return
    const active = document.activeElement
    if (active && active !== document.body && active.isConnected) return
    headingRef.current?.focus()
  }, [outcome])

  useEffect(() => {
    if (showAddForm || !returnFocusToAdd.current) return
    returnFocusToAdd.current = false
    addButtonRef.current?.focus()
  }, [showAddForm])

  function done(text) {
    setOutcome({ failed: false, text })
  }

  /** Says why a write failed. Resolves to a 400's field messages, or to null. */
  function fail(caught) {
    const refusal =
      caught instanceof ApiError ? caught : new ApiError(NETWORK_ERROR_STATUS, messageForStatus(NETWORK_ERROR_STATUS))
    switch (refusal.status) {
      case 403:
        // The role may not change action items, whatever `can_edit` said. The
        // controls go, here and on the Summary panel, and the sentence says why.
        onRefused()
        setOutcome({ failed: true, text: TEXT.meetingContributionNotPermitted })
        return null
      case 404:
        setOutcome({ failed: true, text: TEXT.actionItemNotFound })
        onStale()
        return null
      case 400: {
        // DRF's validation message, beside the field it names; the notice points at it.
        const { fieldErrors, formError } = extractFieldErrors(refusal, FIELDS)
        setOutcome({ failed: true, text: formError ?? TEXT.actionItemCheckFields })
        return fieldErrors
      }
      default:
        // Fixed, user-facing text from the API client. Never a backend string.
        setOutcome({ failed: true, text: refusal.message })
        return null
    }
  }

  function wantDirectory() {
    setDirectoryWanted(true)
  }

  async function saveItem(item, values) {
    // Only what changed is sent; `null` clears an owner or a date.
    const changes = {}
    if (values.description !== item.description) changes.description = values.description
    if (values.ownerId !== (item.owner?.id ?? null)) changes.ownerId = values.ownerId
    if (values.dueDate !== (item.due_date ?? null)) changes.dueDate = values.dueDate
    if (Object.keys(changes).length === 0) {
      done(TEXT.actionItemUnchanged)
      return { done: true }
    }
    try {
      const updated = await updateActionItem(meetingId, item.action_item_id, changes)
      if (updated && typeof updated === 'object') {
        onItemsChange((current) =>
          current.map((existing) => (existing.action_item_id === item.action_item_id ? updated : existing)),
        )
      } else {
        // A 200 with no item is not something the contract allows; read it again.
        onStale()
      }
      done(TEXT.actionItemSaved)
      return { done: true }
    } catch (caught) {
      return { done: false, fieldErrors: fail(caught) }
    }
  }

  async function addItem(values) {
    try {
      const created = await addActionItem(meetingId, values)
      if (created && typeof created === 'object') onItemsChange((current) => [...current, created])
      else onStale()
      returnFocusToAdd.current = true
      setAdding(false)
      done(TEXT.actionItemAdded)
      return null
    } catch (caught) {
      return fail(caught)
    }
  }

  function cancelAdd() {
    returnFocusToAdd.current = true
    setAdding(false)
  }

  async function confirmDelete() {
    const item = confirming
    if (!item || deleteInFlight.current) return
    deleteInFlight.current = true
    setDeleting(true)
    try {
      await deleteActionItem(meetingId, item.action_item_id)
      onItemsChange((current) => current.filter((existing) => existing.action_item_id !== item.action_item_id))
      done(TEXT.actionItemDeleted)
    } catch (caught) {
      fail(caught)
    } finally {
      deleteInFlight.current = false
      setDeleting(false)
      setConfirming(null)
    }
  }

  let body
  if (loading) {
    // Plain text: the one read both panels wait on is announced once, by Summary.
    body = <p className="action-items__state">{TEXT.loadingActionItems}</p>
  } else if (unavailable) {
    body = <p className="action-items__state">{TEXT.actionItemsUnavailable}</p>
  } else {
    // A kept item can name a passage the current summary does not quote.
    const numberOnly = items.some((item) =>
      passageNumbers(item).some((number) => passageText(passages, number) === null),
    )
    body = (
      <>
        {outcome?.failed ? (
          <Notice variant="error" title={TEXT.actionItemsFailed}>
            {outcome.text}
          </Notice>
        ) : null}
        <p className="action-items__announcement" role="status">
          {outcome && !outcome.failed ? outcome.text : ''}
        </p>

        {items.length === 0 ? (
          <p className="action-items__state">{noneRaised ? TEXT.actionItemsNoneRaised : TEXT.actionItemsNone}</p>
        ) : (
          <ul className="action-items__list">
            {items.map((item) => (
              <ActionItem
                key={item.action_item_id}
                item={item}
                passages={passages}
                canEdit={canEdit}
                directory={directory}
                onWantDirectory={wantDirectory}
                onSave={saveItem}
                onAskDelete={setConfirming}
              />
            ))}
          </ul>
        )}
        {numberOnly ? <p className="action-items__note">{TEXT.passageNumberOnly}</p> : null}

        {showAddForm ? (
          <div className="action-item action-items__add person-content">
            <ActionItemForm
              legend={TEXT.actionItemAddLegend}
              submitLabel={TEXT.actionItemAdd}
              busyLabel={TEXT.actionItemAdding}
              initial={BLANK}
              directory={directory}
              onSubmit={addItem}
              onCancel={cancelAdd}
            />
          </div>
        ) : null}
        {canEdit && !showAddForm ? (
          <div className="action-items__actions">
            <Button
              ref={addButtonRef}
              variant="secondary"
              onClick={() => {
                wantDirectory()
                setAdding(true)
              }}
            >
              {TEXT.actionItemAdd}
            </Button>
          </div>
        ) : null}
      </>
    )
  }

  return (
    <section className="action-items" aria-labelledby={headingId}>
      <h2 id={headingId} ref={headingRef} tabIndex={-1}>
        {TEXT.actionItemsHeading}
      </h2>
      {body}

      {confirming ? (
        <Dialog
          title={TEXT.actionItemDeleteConfirm}
          confirmLabel={TEXT.actionItemDeleteConfirmLabel}
          busyLabel={TEXT.actionItemDeleting}
          cancelLabel={TEXT.actionItemDeleteCancel}
          busy={deleting}
          returnFocusRef={headingRef}
          onConfirm={confirmDelete}
          onCancel={() => {
            if (!deleting) setConfirming(null)
          }}
        >
          <p className="action-items__quoted">“{confirming.description}”</p>
          <p>
            {TEXT.actionItemDeleteBody}
            {confirming.origin === ACTION_ITEM_ORIGIN.ai ? ` ${TEXT.actionItemDeleteAiNote}` : ''}
          </p>
        </Dialog>
      ) : null}
    </section>
  )
}
