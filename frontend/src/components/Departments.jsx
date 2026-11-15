import { useEffect, useRef, useState } from 'react'
import { ApiError, messageForStatus } from '../api/client.js'
import { createDepartment, deleteDepartment, listDepartments } from '../api/departments.js'
import { TEXT } from '../constants.js'
import { extractFieldErrors } from '../utils/fieldErrors.js'
import { whenToRetry } from '../utils/retryAfter.js'
import { departmentNameError, spacedTagName } from '../utils/validation.js'
import Button from './Button.jsx'
import Dialog from './Dialog.jsx'
import NotPermitted from './NotPermitted.jsx'
import Notice from './Notice.jsx'
import TextInput from './TextInput.jsx'
import './Departments.css'

/** The one field the add form can place a 400's message beside. Any other key is a form-level failure. */
const CREATE_FIELDS = ['name']

/**
 * The words of each action, keyed on what `actionOf` says a press asks for. Kept apart so
 * a row, its confirmation and its failure always speak of the same action.
 */
const ACTION_WORDS = {
  retire: {
    button: TEXT.departmentRetire,
    label: TEXT.departmentRetireLabel,
    confirm: TEXT.departmentRetireConfirm,
    body: TEXT.departmentRetireBody,
    confirmLabel: TEXT.departmentRetireConfirmLabel,
    busyLabel: TEXT.departmentRetiring,
    failed: TEXT.departmentRetireFailed,
  },
  delete: {
    button: TEXT.departmentDelete,
    label: TEXT.departmentDeleteLabel,
    confirm: TEXT.departmentDeleteConfirm,
    body: TEXT.departmentDeleteBody,
    confirmLabel: TEXT.departmentDeleteConfirmLabel,
    busyLabel: TEXT.departmentDeleting,
    failed: TEXT.departmentDeleteFailed,
  },
}

/**
 * What a press on a row's action asks the server for, as far as the list can tell.
 *
 * The server retires a department any document has (200) and deletes one none has (204),
 * and `item_count` is that number of documents. So an active department with documents is
 * offered "Retire", and one with none "Delete". A retired department is offered "Delete",
 * because deleting is the only change left for it: the server keeps it retired while
 * documents have it. A count that did not arrive is read as in use, the outcome that
 * keeps the department on documents. The server decides from the documents as they are
 * when it is asked, so each confirmation gives the other outcome too, and the row then
 * shows what the reply said.
 */
function actionOf(department) {
  if (department.active === false || department.item_count === 0) return 'delete'
  return 'retire'
}

/** "Active" or "Retired" from `active`, or a dash where it did not arrive: never an invented state. */
function stateOf(department) {
  if (department.active === true) return TEXT.departmentStateActive
  if (department.active === false) return TEXT.departmentStateRetired
  return '—'
}

/** A count as the server sent it, or a dash for one that did not arrive. */
function figure(value) {
  return Number.isFinite(value) ? value : '—'
}

/**
 * `list` with `entry` in place of the row with its id, or, where there is none, placed by
 * name without regard to case, which is where the server's order puts it as near as this
 * screen can tell. Used only when the list could not be read again after an add, so that
 * the department just added or brought back is still shown; the next read is the server's
 * own order.
 */
function withEntry(list, entry) {
  const held = Array.isArray(list) ? list : []
  if (held.some((item) => item.department_id === entry.department_id)) {
    return held.map((item) => (item.department_id === entry.department_id ? entry : item))
  }
  const key = String(entry.name ?? '').toLowerCase()
  const at = held.findIndex((item) => String(item.name ?? '').toLowerCase() > key)
  return at === -1 ? [...held, entry] : [...held.slice(0, at), entry, ...held.slice(at)]
}

/**
 * The departments, in the order the server sent them: by name, without regard to case.
 * Nothing here sorts, filters or trims them.
 *
 * `name` is text a person typed, on the upload form or here, so it is rendered as text
 * and never as HTML. The action column is left out entirely once the server has refused
 * an action (`showActions` false), rather than left as a column of nothing.
 */
function DepartmentTable({ departments, showActions, onAction }) {
  return (
    <div className="table-scroll" role="region" aria-labelledby="departments-list-heading" tabIndex={0}>
      <table className="departments-table">
        <caption className="visually-hidden">{TEXT.departmentsTableCaption}</caption>
        <thead>
          <tr>
            <th scope="col">{TEXT.departmentsColumnName}</th>
            <th scope="col">{TEXT.departmentsColumnState}</th>
            <th scope="col">{TEXT.departmentsColumnItems}</th>
            {showActions ? (
              <th scope="col">
                <span className="visually-hidden">{TEXT.departmentsColumnAction}</span>
              </th>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {departments.map((department) => {
            const words = ACTION_WORDS[actionOf(department)]
            return (
              <tr key={department.department_id}>
                <th scope="row" className="departments-table__name">
                  {department.name}
                </th>
                {/* The state is a word; the muted colour of "Retired" is a second cue, never the only one. */}
                <td className={department.active === false ? 'departments-table__retired' : undefined}>
                  {stateOf(department)}
                </td>
                <td className="departments-table__count">{figure(department.item_count)}</td>
                {showActions ? (
                  <td className="departments-table__action">
                    <Button
                      variant="secondary"
                      aria-label={words.label(department.name)}
                      onClick={() => onAction(department)}
                    >
                      {words.button}
                    </Button>
                  </td>
                ) : null}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

/**
 * FR-10's department list on the Tags page (D-129, the user's decision of 13 November
 * 2026): the departments the AI may assign, active or retired, with how many documents
 * use each, one action per department, and a form that adds one.
 *
 * **What the list is for,** said above it in three sentences, as the user decided it: the
 * AI assigns a department only from this list; the upload form still accepts any
 * department (FR-08's form is unchanged); and a retired department stays on the documents
 * that have it, while the AI no longer assigns it.
 *
 * **Retiring and deleting.** The action asks for confirmation first, in the existing
 * Dialog, and is named for what the list says will happen (`actionOf`). The dialogue gives
 * the other outcome too, because the server decides from the documents as they are, and
 * the row then shows what the reply said:
 *
 * - 200: the department was retired, or stays retired; the row shows the entry the reply
 *   carries, and a notice says it stays on its documents and is no longer assigned.
 * - 204: it was deleted; the row goes, and a notice says so.
 * - 404: it no longer exists; the row goes, and a notice says so.
 * - 403: every action on the page is withdrawn (`onRefused`), the tags' with this
 *   section's, since both ask for `manage_tags`, and the not-permitted notice says why.
 *
 * **Adding a department.** A name and Add, offered once the list has been read. The
 * name is checked here first, empty or too long, and sent trimmed and single-spaced, its
 * case kept. Then, from the reply:
 *
 * - 201: the list is read again, so the new entry is shown where the server orders it;
 *   where that read fails, it is placed by name. The field clears and a polite notice
 *   names the department as stored.
 * - 200: the name was a retired department's, and it is active again. Handled as the
 *   201, and announced as brought back.
 * - 409: an active department of that name is in the list. The list is read again and
 *   the department the reply's `department_id` names is found in it, so the notice names
 *   it as the list spells it. The name stays in the field. The reply's `detail` is never
 *   shown.
 * - 400: DRF's message beside the field, with focus there.
 * - 429: the `tagging` limit, shared with adding tags, with when to try again from
 *   Retry-After.
 * - 403: as for an action: everything is withdrawn, the form included, and focus goes to
 *   this section's heading.
 *
 * The list is read by the page (src/pages/Tags.jsx), which passes it in as `list`, so
 * that a 403 on it withdraws the tags' actions too; `withdrawn` is true once anything on
 * the page has been refused.
 *
 * Focus: the Dialog returns it to the row's action when that is still there (the 200),
 * and to this section's heading when it is not (the 204, the 404, the 403). An add leaves
 * it where it was, on the form, except a 400 (the field) and a 403 (the heading, since the
 * form is gone).
 *
 * @param {object} props
 * @param {{data: unknown, loading: boolean, error: ApiError|null, reload: () => void, setData: Function}} props.list
 *   The page's read of `GET /api/departments` (src/hooks/useApiResource.js).
 * @param {boolean} props.withdrawn True once the server has refused anything on the page.
 * @param {() => void} props.onRefused Called when an action here is refused with a 403.
 */
export default function Departments({ list, withdrawn, onRefused }) {
  const { data, loading, error, reload, setData } = list
  const departments = Array.isArray(data) ? data : []
  const headingRef = useRef(null)

  // The department whose confirmation is open, with the action it was opened for, and
  // whether its DELETE is in flight. The ref is the guard: one DELETE per confirmation,
  // even when confirm is pressed again before the busy state has rendered.
  const [confirming, setConfirming] = useState(null)
  const [deleting, setDeleting] = useState(false)
  const deleteInFlight = useRef(false)
  // The outcome of this section's last action, in words.
  const [notice, setNotice] = useState(null)

  // Adding a department: the name as typed, the message beside the field (a check's here
  // or a 400's), and whether the POST is in flight. The ref is the guard: one POST per
  // press, even a second press before the busy state renders.
  const [draft, setDraft] = useState('')
  const [nameError, setNameError] = useState(null)
  const [creating, setCreating] = useState(false)
  const createInFlight = useRef(false)
  const nameRef = useRef(null)
  // Where focus goes once the render that shows the reason has committed: the field with
  // its message, or the heading once the form has gone. A new object each time, so the
  // same target twice running still moves focus.
  const [focusRequest, setFocusRequest] = useState(null)

  useEffect(() => {
    if (!focusRequest) return
    const target = { name: nameRef, heading: headingRef }[focusRequest.target]
    target?.current?.focus()
  }, [focusRequest])

  // The form waits for the list: a 409 names the department as the list spells it.
  const offerCreate = !loading && !error && !withdrawn

  function openConfirmation(department) {
    setNotice(null)
    setConfirming({ department, action: actionOf(department) })
  }

  function cancel() {
    if (!deleting) setConfirming(null)
  }

  /** The row for `department` leaves the list on screen. */
  function removeRow(department) {
    setData((current) =>
      Array.isArray(current) ? current.filter((item) => item.department_id !== department.department_id) : current,
    )
  }

  /** The not-permitted handling every action here shares: everything on the page is withdrawn, and the notice says why. */
  function withdrawActions() {
    onRefused()
    setNotice({ variant: 'error', title: TEXT.notPermittedTitle, text: TEXT.departmentsNotPermitted })
  }

  async function confirmAction() {
    const pending = confirming
    if (!pending || deleteInFlight.current) return
    const { department } = pending
    deleteInFlight.current = true
    setDeleting(true)
    try {
      const outcome = await deleteDepartment(department.department_id)
      if (outcome.deleted) {
        removeRow(department)
        setNotice({ variant: 'info', text: TEXT.departmentDeleted(department.name) })
      } else {
        // The row becomes the entry the server returned, retired. It stays where it is:
        // the order is the server's.
        const entry =
          outcome.department && typeof outcome.department === 'object'
            ? outcome.department
            : { ...department, active: false }
        setData((current) =>
          Array.isArray(current)
            ? current.map((item) => (item.department_id === department.department_id ? entry : item))
            : current,
        )
        setNotice({ variant: 'info', text: TEXT.departmentRetired(department.name) })
      }
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 403) {
        // The role lacks manage_tags now, whatever it held when the list was read.
        withdrawActions()
      } else if (caught instanceof ApiError && caught.status === 404) {
        removeRow(department)
        setNotice({ variant: 'info', text: TEXT.departmentGone(department.name) })
      } else {
        // Fixed, user-facing text from the API client; never the server's.
        setNotice({
          variant: 'error',
          title: ACTION_WORDS[pending.action].failed,
          text: caught instanceof ApiError ? caught.message : messageForStatus(),
        })
      }
    } finally {
      deleteInFlight.current = false
      setDeleting(false)
      setConfirming(null)
    }
  }

  /**
   * The list read again, or null when the read failed. A failed read is not the add's
   * failure: the add's own reply has already said what happened.
   */
  async function readList() {
    try {
      const reread = await listDepartments()
      return Array.isArray(reread) ? reread : null
    } catch {
      return null
    }
  }

  /**
   * The 409: an active department of that name is in the list. The list is read again
   * first, so the department the reply names is found as it is now, one another
   * Administrator added since the page was read included; where the read fails, the list
   * held is searched. Named as the list spells it where it is found, and by what was sent
   * where it is not.
   */
  async function sayAlreadyThere(caught, held, sent) {
    const departmentId = typeof caught.details?.department_id === 'string' ? caught.details.department_id : null
    const reread = await readList()
    if (reread) setData(reread)
    const existing = departmentId
      ? ((reread ?? held).find((department) => department.department_id === departmentId) ?? null)
      : null
    setNotice({ variant: 'info', text: TEXT.departmentCreateExists(existing?.name ?? sent) })
  }

  async function addDepartment(event) {
    event.preventDefault()
    if (createInFlight.current) return
    // Trimmed and single-spaced, and sent that way, so the server measures what was
    // measured here (src/utils/validation.js). The case is the person's.
    const sent = spacedTagName(draft)
    const problem = departmentNameError(sent)
    setNotice(null)
    if (problem) {
      setNameError(problem)
      setFocusRequest({ target: 'name' })
      return
    }
    setNameError(null)
    const held = departments
    createInFlight.current = true
    setCreating(true)
    try {
      const { reactivated, department } = await createDepartment({ name: sent })
      const reread = await readList()
      setData((current) => reread ?? (department ? withEntry(current, department) : current))
      setDraft('')
      const name = department?.name ?? sent
      setNotice({
        variant: 'info',
        text: reactivated ? TEXT.departmentReactivated(name) : TEXT.departmentCreated(name),
      })
    } catch (caught) {
      const status = caught instanceof ApiError ? caught.status : null
      if (status === 409) {
        await sayAlreadyThere(caught, held, sent)
      } else if (status === 403) {
        // The role lacks manage_tags now. The form goes with every other action, so focus
        // goes to this section's heading rather than being left on nothing.
        withdrawActions()
        setFocusRequest({ target: 'heading' })
      } else if (status === 400) {
        // DRF's validation message, beside the field; the notice points at it.
        const { fieldErrors, formError } = extractFieldErrors(caught, CREATE_FIELDS)
        setNameError(fieldErrors.name ?? null)
        if (fieldErrors.name) setFocusRequest({ target: 'name' })
        setNotice({
          variant: 'error',
          title: TEXT.departmentCreateFailed,
          text: formError ?? TEXT.classificationCheckFields,
        })
      } else if (status === 429) {
        // The `tagging` limit, which adding a tag counts against too; when to try again
        // comes from Retry-After.
        setNotice({
          variant: 'error',
          title: TEXT.departmentCreateFailed,
          text: TEXT.departmentLimitReached(whenToRetry(caught.retryAfter)),
        })
      } else {
        // Fixed, user-facing text from the API client; never the server's.
        setNotice({
          variant: 'error',
          title: TEXT.departmentCreateFailed,
          text: caught instanceof ApiError ? caught.message : messageForStatus(),
        })
      }
    } finally {
      createInFlight.current = false
      setCreating(false)
    }
  }

  let listBody
  if (loading) {
    listBody = <p role="status">{TEXT.loadingDepartments}</p>
  } else if (error?.status === 403) {
    listBody = <NotPermitted />
  } else if (error) {
    listBody = (
      <>
        <Notice variant="error" title={TEXT.departmentsLoadFailed}>
          {error.message}
        </Notice>
        <div className="departments__actions">
          <Button variant="secondary" aria-label={TEXT.departmentsRetryLabel} onClick={reload}>
            {TEXT.uploadRetry}
          </Button>
        </div>
      </>
    )
  } else if (departments.length === 0) {
    listBody = <Notice variant="info">{TEXT.noDepartments}</Notice>
  } else {
    listBody = <DepartmentTable departments={departments} showActions={!withdrawn} onAction={openConfirmation} />
  }

  const words = confirming ? ACTION_WORDS[confirming.action] : null

  return (
    <section className="departments" aria-labelledby="departments-heading">
      <h2 id="departments-heading" ref={headingRef} tabIndex={-1}>
        {TEXT.departmentsHeading}
      </h2>
      <p className="departments__intro">{TEXT.departmentsSuggestNote}</p>
      <p className="departments__intro">{TEXT.departmentsUploadNote}</p>
      <p className="departments__intro">{TEXT.departmentsRetiredNote}</p>
      {notice ? (
        <Notice variant={notice.variant} title={notice.title}>
          {notice.text}
        </Notice>
      ) : null}

      {offerCreate ? (
        <section className="departments-create" aria-labelledby="departments-create-heading">
          <h3 id="departments-create-heading">{TEXT.departmentCreateHeading}</h3>
          <p id="departments-create-scope" className="departments__intro">
            {TEXT.departmentCreateScope}
          </p>
          <form className="departments-create__form" onSubmit={addDepartment} noValidate>
            {/* The scope sentence describes the field too, so it is heard by someone who
                tabs straight to the field past the paragraph above. */}
            <TextInput
              ref={nameRef}
              label={TEXT.departmentCreateNameLabel}
              name="name"
              hint={TEXT.departmentCreateNameHint}
              describedBy="departments-create-scope"
              value={draft}
              error={nameError}
              autoComplete="off"
              onChange={(event) => {
                setDraft(event.target.value)
                setNameError(null)
              }}
            />
            <Button type="submit" loading={creating}>
              {creating ? TEXT.departmentAdding : TEXT.departmentCreateAdd}
            </Button>
          </form>
        </section>
      ) : null}

      <section className="departments-list" aria-labelledby="departments-list-heading">
        <h3 id="departments-list-heading">{TEXT.departmentsListHeading}</h3>
        {listBody}
      </section>

      {confirming ? (
        <Dialog
          title={words.confirm(confirming.department.name)}
          confirmLabel={words.confirmLabel}
          busyLabel={words.busyLabel}
          cancelLabel={TEXT.departmentActionCancel}
          busy={deleting}
          returnFocusRef={headingRef}
          onConfirm={confirmAction}
          onCancel={cancel}
        >
          <p>{words.body}</p>
        </Dialog>
      ) : null}
    </section>
  )
}
