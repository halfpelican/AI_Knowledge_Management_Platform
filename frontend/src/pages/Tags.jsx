import { useEffect, useRef, useState } from 'react'
import { ApiError, messageForStatus } from '../api/client.js'
import { CREATE_TAG_DIMENSIONS, createTag, deleteTag, listTags } from '../api/tags.js'
import Button from '../components/Button.jsx'
import Dialog from '../components/Dialog.jsx'
import NotPermitted from '../components/NotPermitted.jsx'
import Notice from '../components/Notice.jsx'
import SelectInput from '../components/SelectInput.jsx'
import TextInput from '../components/TextInput.jsx'
import { TEXT, VALIDATION } from '../constants.js'
import useApiResource from '../hooks/useApiResource.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { extractFieldErrors } from '../utils/fieldErrors.js'
import { whenToRetry } from '../utils/retryAfter.js'
import { spacedTagName, tagNameError } from '../utils/validation.js'
import './Tags.css'

/** A dimension's label, or the dimension as the server sent it for one these do not name. */
const DIMENSION_LABELS = {
  Project: TEXT.documentFieldProject,
  Process: TEXT.documentFieldProcess,
  Topic: TEXT.documentFieldTopic,
}

function labelOf(dimension) {
  return DIMENSION_LABELS[dimension] ?? String(dimension ?? '')
}

function dimensionOf(tag) {
  return labelOf(tag.dimension)
}

/** The fields the add form can place a 400's message beside. Any other key is a form-level failure. */
const CREATE_FIELDS = ['dimension', 'tag_name']

/** The add form's own refusals before any request, worded for a value of any dimension. */
const VALUE_NAME_MESSAGES = { required: VALIDATION.tagValueRequired, tooLong: VALIDATION.tagValueTooLong }

/** "Active" or "Retired" from `active`, or a dash where it did not arrive: never an invented state. */
function stateOf(tag) {
  if (tag.active === true) return TEXT.tagStateActive
  if (tag.active === false) return TEXT.tagStateRetired
  return '—'
}

/** A count as the server sent it, or a dash for one that did not arrive. */
function figure(value) {
  return Number.isFinite(value) ? value : '—'
}

/**
 * `list` with `entry` placed by dimension, then by name, which is where the server's
 * order puts it as near as this screen can tell. Used only when the list could not be
 * read again after a 201, so that the value just added is still shown; the next read
 * is the server's own order.
 */
function withEntry(list, entry) {
  const others = Array.isArray(list) ? list.filter((tag) => tag.tag_id !== entry.tag_id) : []
  const at = others.findIndex(
    (tag) => tag.dimension > entry.dimension || (tag.dimension === entry.dimension && tag.tag_name > entry.tag_name),
  )
  return at === -1 ? [...others, entry] : [...others.slice(0, at), entry, ...others.slice(at)]
}

/**
 * The tags, in the order the server sent them: by dimension, then by name. Nothing
 * here sorts, filters or trims them.
 *
 * `tag_name` is text a person typed or the AI suggested, so it is rendered as text
 * and never as HTML. The action column is left out entirely once the server has
 * refused an action (`showActions` false), rather than left as a column of nothing.
 */
function TagTable({ tags, showActions, onDelete }) {
  return (
    <div className="table-scroll" role="region" aria-labelledby="tags-list-heading" tabIndex={0}>
      <table className="tags-table">
        <caption className="visually-hidden">{TEXT.tagsTableCaption}</caption>
        <thead>
          <tr>
            <th scope="col">{TEXT.tagsColumnName}</th>
            <th scope="col">{TEXT.tagsColumnDimension}</th>
            <th scope="col">{TEXT.tagsColumnState}</th>
            <th scope="col">{TEXT.tagsColumnItems}</th>
            {showActions ? (
              <th scope="col">
                <span className="visually-hidden">{TEXT.tagsColumnAction}</span>
              </th>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {tags.map((tag) => (
            <tr key={tag.tag_id}>
              <th scope="row" className="tags-table__name">
                {tag.tag_name}
              </th>
              <td>{dimensionOf(tag)}</td>
              {/* The state is a word; the muted colour of "Retired" is a second cue, never the only one. */}
              <td className={tag.active === false ? 'tags-table__retired' : undefined}>{stateOf(tag)}</td>
              <td className="tags-table__count">{figure(tag.item_count)}</td>
              {showActions ? (
                <td className="tags-table__action">
                  <Button
                    variant="secondary"
                    aria-label={TEXT.tagDeleteLabel(dimensionOf(tag), tag.tag_name)}
                    onClick={() => onDelete(tag)}
                  >
                    {TEXT.tagDelete}
                  </Button>
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/**
 * FR-10's tag administration (NIT3004; D-119 finding 5; D-128): the Administrator's
 * list of every Project, Process and Topic tag, active or retired, with how many
 * documents and meetings carry each, one action per tag, and a form that adds a
 * value.
 *
 * **Deleting.** The action asks for confirmation first, in the existing Dialog, and
 * the dialogue says what will happen: FR-10's "Tags are deactivated rather than
 * deleted where content still references them, preserving historical
 * classification". Which of the two happens is the server's decision, from references
 * this screen cannot see (a held suggestion and a removed link are not in
 * `item_count`), so the sentence gives both, and the row then shows what the reply
 * said:
 *
 * - 200: the tag was deactivated; the row shows the entry the reply carries, now
 *   retired, and a notice says why it was not deleted.
 * - 204: the tag was deleted; the row goes, and a notice says so.
 * - 404: the tag no longer exists; the row goes, and a notice says so.
 * - 403: every action is withdrawn and the not-permitted notice says why, as
 *   src/pages/KnowledgeGaps.jsx does. A 403 on the list renders NotPermitted alone.
 *
 * **Adding a value** (D-128; FR-10's CRUD line gives Tags "Create"). A dimension, a
 * name and Add, offered once the list has been read. The two sentences above the form
 * say what an Administrator needs to know before adding: the value is offered for
 * every document whatever its audience, and the AI adds values itself, so a retired
 * one can come back. The name is checked here first, empty or too long, and sent
 * trimmed and single-spaced. Then, from the reply:
 *
 * - 201: the list is read again, so the new entry is shown where the server orders
 *   it, beside anything the AI added meanwhile; where that read fails, the entry is
 *   placed by dimension and name. The name field clears and a polite notice names
 *   the value as stored.
 * - 409: a tag of that name is already in the dimension. The list is read again and
 *   the tag the reply's `tag_id` names is found in it, so the notice names its
 *   dimension and name and, for a retired one, says it is retired and is not added
 *   again here. The name stays in the field. The reply's `detail` is never shown.
 * - 400: DRF's message beside the field it names, with focus there.
 * - 429: the `tagging` limit, worded as the document detail words it, with when to
 *   try again from Retry-After.
 * - 403: the delete's not-permitted handling: every action, the form included, is
 *   withdrawn, and focus goes to the page heading.
 *
 * The route is guarded by RequireRole, which sends anyone but an Administrator to
 * /403 (FR-06), and the navigation offers the link to Administrators only. Both are
 * usability. The server checks `manage_tags` on every request (CLAUDE.md §6,
 * invariant 4).
 *
 * Focus: the Dialog returns it to the row's Delete when that is still there (the
 * 200), and to the page heading when it is not (the 204, the 404, the 403). An add
 * leaves it where it was, on the form, except a 400 (the field) and a 403 (the
 * heading, since the form is gone).
 */
export default function Tags() {
  useDocumentTitle(TEXT.tagsHeading)
  const { data, loading, error, reload, setData } = useApiResource(listTags)
  const tags = Array.isArray(data) ? data : []
  const headingRef = useRef(null)

  // The tag whose confirmation is open, and whether its DELETE is in flight. The ref
  // is the guard: one DELETE per confirmation, even when confirm is pressed again
  // before the busy state has rendered.
  const [confirming, setConfirming] = useState(null)
  const [deleting, setDeleting] = useState(false)
  const deleteInFlight = useRef(false)
  // The outcome of the last action, in words: added, already there, deactivated,
  // deleted, gone, refused or failed.
  const [notice, setNotice] = useState(null)
  // True once the server has refused an action with a 403.
  const [refused, setRefused] = useState(false)

  // Adding a value: the dimension and the name as typed, the message beside either
  // field (a check's here or a 400's), and whether the POST is in flight. The ref is
  // the guard: one POST per press, even a second press before the busy state renders.
  const [draft, setDraft] = useState({ dimension: CREATE_TAG_DIMENSIONS[0], name: '' })
  const [createErrors, setCreateErrors] = useState({})
  const [creating, setCreating] = useState(false)
  const createInFlight = useRef(false)
  const dimensionRef = useRef(null)
  const nameRef = useRef(null)
  // Where focus goes once the render that shows the reason has committed: a field
  // with its message, or the heading once the form has gone. A new object each time,
  // so the same target twice running still moves focus.
  const [focusRequest, setFocusRequest] = useState(null)

  useEffect(() => {
    if (!focusRequest) return
    const target = { dimension: dimensionRef, tag_name: nameRef, heading: headingRef }[focusRequest.target]
    target?.current?.focus()
  }, [focusRequest])

  const actionsWithdrawn = refused || error?.status === 403
  // The form waits for the list: a 409 is told apart, retired or active, by the list.
  const offerCreate = !loading && !error && !refused

  function openConfirmation(tag) {
    setNotice(null)
    setConfirming(tag)
  }

  function cancel() {
    if (!deleting) setConfirming(null)
  }

  /** The row for `tag` leaves the list on screen. */
  function removeRow(tag) {
    setData((current) => (Array.isArray(current) ? current.filter((item) => item.tag_id !== tag.tag_id) : current))
  }

  /** The not-permitted handling every action shares: everything is withdrawn, and the notice says why. */
  function withdrawActions() {
    setRefused(true)
    setNotice({ variant: 'error', title: TEXT.notPermittedTitle, text: TEXT.tagsNotPermitted })
  }

  async function confirmDelete() {
    const tag = confirming
    if (!tag || deleteInFlight.current) return
    deleteInFlight.current = true
    setDeleting(true)
    try {
      const outcome = await deleteTag(tag.tag_id)
      if (outcome.deleted) {
        removeRow(tag)
        setNotice({ variant: 'info', text: TEXT.tagDeleted(tag.tag_name) })
      } else {
        // The row becomes the entry the server returned, now retired. It stays where
        // it is: the order is the server's.
        const entry = outcome.tag && typeof outcome.tag === 'object' ? outcome.tag : { ...tag, active: false }
        setData((current) =>
          Array.isArray(current) ? current.map((item) => (item.tag_id === tag.tag_id ? entry : item)) : current,
        )
        setNotice({ variant: 'info', text: TEXT.tagDeactivated(tag.tag_name) })
      }
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 403) {
        // The role lacks manage_tags now, whatever it held when the list was read.
        withdrawActions()
      } else if (caught instanceof ApiError && caught.status === 404) {
        removeRow(tag)
        setNotice({ variant: 'info', text: TEXT.tagGone(tag.tag_name) })
      } else {
        // Fixed, user-facing text from the API client; never the server's.
        setNotice({
          variant: 'error',
          title: TEXT.tagDeleteFailed,
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
      const list = await listTags()
      return Array.isArray(list) ? list : null
    } catch {
      return null
    }
  }

  /**
   * FR-10's 409: a tag of that name is already in the dimension. The list is read
   * again first, so the tag the reply names is found as it is now, a value the AI
   * added or brought back since the page was read included; where the read fails, the
   * list held is searched. Named by its own dimension and name where it is found, and
   * by what was sent where it is not.
   */
  async function sayAlreadyThere(caught, held, sent) {
    const tagId = typeof caught.details?.tag_id === 'string' ? caught.details.tag_id : null
    const reread = await readList()
    if (reread) setData(reread)
    const existing = tagId ? ((reread ?? held).find((tag) => tag.tag_id === tagId) ?? null) : null
    const dimension = labelOf(existing?.dimension ?? sent.dimension)
    const name = existing?.tag_name ?? sent.name
    setNotice({
      variant: 'info',
      text:
        existing?.active === false
          ? TEXT.tagCreateExistsRetired(dimension, name)
          : TEXT.tagCreateExists(dimension, name),
    })
  }

  async function addValue(event) {
    event.preventDefault()
    if (createInFlight.current) return
    // Trimmed and single-spaced, and sent that way, so the server measures what was
    // measured here (src/utils/validation.js).
    const sent = { dimension: draft.dimension, name: spacedTagName(draft.name) }
    const problem = tagNameError(sent.name, VALUE_NAME_MESSAGES)
    setNotice(null)
    if (problem) {
      setCreateErrors({ tag_name: problem })
      setFocusRequest({ target: 'tag_name' })
      return
    }
    setCreateErrors({})
    const held = tags
    createInFlight.current = true
    setCreating(true)
    try {
      const reply = await createTag({ dimension: sent.dimension, tagName: sent.name })
      const entry = reply && typeof reply === 'object' ? reply : null
      const reread = await readList()
      setData((current) => reread ?? (entry ? withEntry(current, entry) : current))
      setDraft((current) => ({ ...current, name: '' }))
      setNotice({
        variant: 'info',
        text: TEXT.tagCreated(labelOf(entry?.dimension ?? sent.dimension), entry?.tag_name ?? sent.name),
      })
    } catch (caught) {
      const status = caught instanceof ApiError ? caught.status : null
      if (status === 409) {
        await sayAlreadyThere(caught, held, sent)
      } else if (status === 403) {
        // The role lacks manage_tags now. The form goes with every other action, so
        // focus goes to the heading rather than being left on nothing.
        withdrawActions()
        setFocusRequest({ target: 'heading' })
      } else if (status === 400) {
        // DRF's validation message, beside the field it names; the notice points at it.
        const { fieldErrors, formError } = extractFieldErrors(caught, CREATE_FIELDS)
        setCreateErrors(fieldErrors)
        const first = CREATE_FIELDS.find((field) => fieldErrors[field])
        if (first) setFocusRequest({ target: first })
        setNotice({ variant: 'error', title: TEXT.tagCreateFailed, text: formError ?? TEXT.classificationCheckFields })
      } else if (status === 429) {
        // The `tagging` limit, which adding a tag to a document counts against too, so
        // it is worded as that one is; when to try again comes from Retry-After.
        setNotice({
          variant: 'error',
          title: TEXT.tagCreateFailed,
          text: TEXT.tagLimitReached(whenToRetry(caught.retryAfter)),
        })
      } else {
        // Fixed, user-facing text from the API client; never the server's.
        setNotice({
          variant: 'error',
          title: TEXT.tagCreateFailed,
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
    listBody = <p role="status">{TEXT.loadingTags}</p>
  } else if (error?.status === 403) {
    listBody = <NotPermitted />
  } else if (error) {
    listBody = (
      <>
        <Notice variant="error" title={TEXT.tagsLoadFailed}>
          {error.message}
        </Notice>
        <div className="tags-page__actions">
          <Button variant="secondary" onClick={reload}>
            {TEXT.uploadRetry}
          </Button>
        </div>
      </>
    )
  } else if (tags.length === 0) {
    listBody = <Notice variant="info">{TEXT.noTags}</Notice>
  } else {
    listBody = <TagTable tags={tags} showActions={!actionsWithdrawn} onDelete={openConfirmation} />
  }

  return (
    <div className="tags-page">
      <h1 id="tags-heading" ref={headingRef} tabIndex={-1}>
        {TEXT.tagsHeading}
      </h1>
      <p className="tags-page__intro">{TEXT.tagsIntro}</p>
      <p className="tags-page__intro">{TEXT.tagsCountNote}</p>
      {notice ? (
        <Notice variant={notice.variant} title={notice.title}>
          {notice.text}
        </Notice>
      ) : null}

      {offerCreate ? (
        <section className="tags-create" aria-labelledby="tags-create-heading">
          <h2 id="tags-create-heading">{TEXT.tagCreateHeading}</h2>
          <p id="tags-create-scope" className="tags-page__intro">
            {TEXT.tagCreateScope}
          </p>
          <p className="tags-page__intro">{TEXT.tagCreateAiNote}</p>
          <form className="tags-create__form" onSubmit={addValue} noValidate>
            <SelectInput
              ref={dimensionRef}
              label={TEXT.tagDimensionLabel}
              name="dimension"
              options={CREATE_TAG_DIMENSIONS.map((dimension) => ({ value: dimension, label: labelOf(dimension) }))}
              value={draft.dimension}
              error={createErrors.dimension}
              onChange={(event) => {
                const { value } = event.target
                setDraft((current) => ({ ...current, dimension: value }))
                setCreateErrors((current) => ({ ...current, dimension: undefined }))
              }}
            />
            {/* The scope sentence describes the field too, so it is heard by someone who
                tabs straight to the field past the paragraphs above. */}
            <TextInput
              ref={nameRef}
              label={TEXT.tagCreateNameLabel}
              name="tag_name"
              hint={TEXT.tagCreateNameHint}
              describedBy="tags-create-scope"
              value={draft.name}
              error={createErrors.tag_name}
              autoComplete="off"
              onChange={(event) => {
                const { value } = event.target
                setDraft((current) => ({ ...current, name: value }))
                setCreateErrors((current) => ({ ...current, tag_name: undefined }))
              }}
            />
            <Button type="submit" loading={creating}>
              {creating ? TEXT.tagAdding : TEXT.tagCreateAdd}
            </Button>
          </form>
        </section>
      ) : null}

      <section className="tags-list" aria-labelledby="tags-list-heading">
        <h2 id="tags-list-heading">{TEXT.tagsListHeading}</h2>
        {listBody}
      </section>

      {confirming ? (
        <Dialog
          title={TEXT.tagDeleteConfirm(dimensionOf(confirming), confirming.tag_name)}
          confirmLabel={TEXT.tagDeleteConfirmLabel}
          busyLabel={TEXT.tagDeleting}
          cancelLabel={TEXT.tagDeleteCancel}
          busy={deleting}
          returnFocusRef={headingRef}
          onConfirm={confirmDelete}
          onCancel={cancel}
        >
          <p>{TEXT.tagDeleteBody}</p>
        </Dialog>
      ) : null}
    </div>
  )
}
