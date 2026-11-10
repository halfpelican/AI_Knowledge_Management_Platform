import { useRef, useState } from 'react'
import { ApiError, messageForStatus } from '../api/client.js'
import { deleteTag, listTags } from '../api/tags.js'
import Button from '../components/Button.jsx'
import Dialog from '../components/Dialog.jsx'
import NotPermitted from '../components/NotPermitted.jsx'
import Notice from '../components/Notice.jsx'
import { TEXT } from '../constants.js'
import useApiResource from '../hooks/useApiResource.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import './Tags.css'

/** A dimension's label, or the dimension as the server sent it for one these do not name. */
const DIMENSION_LABELS = {
  Project: TEXT.documentFieldProject,
  Process: TEXT.documentFieldProcess,
  Topic: TEXT.documentFieldTopic,
}

function dimensionOf(tag) {
  return DIMENSION_LABELS[tag.dimension] ?? String(tag.dimension ?? '')
}

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
 * FR-10's tag administration (NIT3004; D-119 finding 5): the Administrator's list
 * of every Project, Process and Topic tag, active or retired, with how many
 * documents and meetings carry each, and one action per tag.
 *
 * The action asks for confirmation first, in the existing Dialog, and the dialogue
 * says what will happen: FR-10's "Tags are deactivated rather than deleted where
 * content still references them, preserving historical classification". Which of
 * the two happens is the server's decision, from references this screen cannot see
 * (a held suggestion and a removed link are not in `item_count`), so the sentence
 * gives both, and the row then shows what the reply said:
 *
 * - 200: the tag was deactivated; the row shows the entry the reply carries, now
 *   retired, and a notice says why it was not deleted.
 * - 204: the tag was deleted; the row goes, and a notice says so.
 * - 404: the tag no longer exists; the row goes, and a notice says so.
 * - 403: every action is withdrawn and the not-permitted notice says why, as
 *   src/pages/KnowledgeGaps.jsx does. A 403 on the list renders NotPermitted alone.
 *
 * The route is guarded by RequireRole, which sends anyone but an Administrator to
 * /403 (FR-06), and the navigation offers the link to Administrators only. Both are
 * usability. The server checks `manage_tags` on every request (CLAUDE.md §6,
 * invariant 4).
 *
 * Focus: the Dialog returns it to the row's Delete when that is still there (the
 * 200), and to the page heading when it is not (the 204, the 404, the 403).
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
  // The outcome of the last action, in words: deactivated, deleted, gone, refused or failed.
  const [notice, setNotice] = useState(null)
  // True once the server has refused an action with a 403.
  const [refused, setRefused] = useState(false)

  const actionsWithdrawn = refused || error?.status === 403

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
        setRefused(true)
        setNotice({ variant: 'error', title: TEXT.notPermittedTitle, text: TEXT.tagsNotPermitted })
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
