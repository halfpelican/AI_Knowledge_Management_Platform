import { useEffect, useId, useRef, useState } from 'react'
import { ApiError, NETWORK_ERROR_STATUS, messageForStatus } from '../api/client.js'
import {
  classifyDocument,
  confirmClassification,
  confirmProposedTopic,
  confirmTag,
  rejectProposedTopic,
  removeTag,
} from '../api/documents.js'
import { TEXT } from '../constants.js'
import { extractFieldErrors } from '../utils/fieldErrors.js'
import { whenToRetry } from '../utils/retryAfter.js'
import Button from './Button.jsx'
import Notice from './Notice.jsx'
import SelectInput from './SelectInput.jsx'
import TextInput from './TextInput.jsx'
import './Classification.css'

/**
 * FR-10's fixed list of types, mirroring apps/core/constants.py DOCUMENT_TYPES:
 * "the type must be selected from a fixed list rather than generated freely". A
 * vocabulary, not a tuned value. The server validates the choice whatever this
 * list offers, and its 400 lands under the field below.
 */
const DOCUMENT_TYPES = ['Policy', 'Procedure', 'Report', 'Meeting Paper']

/** How the server disposed of one assignment (apps/core/constants.py ASSIGNMENT_OUTCOMES, D-105). */
const OUTCOME = {
  applied: 'applied',
  provisional: 'provisional',
  discarded: 'discarded',
  confirmed: 'confirmed',
}

/** `applied_by` on a tag link (TAG_APPLIED_BY_VALUES, D-74). */
const APPLIED_BY_AI = 'ai'

/** The fields the edit form can place a 400's message under. */
const EDIT_FIELDS = ['doc_type', 'department']

/** The keys of the three one-off requests; a tag's or a topic's key names the button pressed. */
const KEY = { classify: 'classify', confirm: 'confirm', edit: 'edit' }

/**
 * The three tag dimensions in the order the detail shows them, keyed lower-case
 * so the contract's "Project" and the browse route's "project" group alike.
 */
const TAG_DIMENSIONS = [
  ['project', TEXT.documentFieldProject],
  ['process', TEXT.documentFieldProcess],
  ['topic', TEXT.documentFieldTopic],
]

/** A confidence in [0, 1] as a whole percentage, or null where there is none. */
function percentOf(confidence) {
  if (typeof confidence !== 'number' || !Number.isFinite(confidence)) return null
  return Math.round(confidence * 100)
}

/** "Suggested by AI, 92% confidence", or the words alone where no confidence came. */
function withConfidence(words, confidence) {
  const percent = percentOf(confidence)
  return percent === null ? words : `${words}, ${TEXT.classificationConfidence(percent)}`
}

/** A dimension's label, or the dimension itself for one the three do not name. */
function dimensionLabel(dimension) {
  const key = String(dimension ?? '').toLowerCase()
  return TAG_DIMENSIONS.find(([name]) => name === key)?.[1] ?? String(dimension ?? '')
}

/** Whether a tag link is one the AI made and a person has not yet confirmed. */
function isUnconfirmedAi(tag) {
  return tag.applied_by === APPLIED_BY_AI && tag.confirmed !== true
}

/**
 * The provenance of one assignment — the type or the department — in words.
 *
 * @param {string} outcome One of OUTCOME.
 * @param {string|null} machineValue What the AI suggested.
 * @param {number|null} confidence Its confidence.
 * @param {string|null} effectiveValue What the document carries now.
 * @param {boolean} isDepartment Only the department has the `discarded` outcome.
 */
function provenanceFor(outcome, machineValue, confidence, effectiveValue, isDepartment) {
  switch (outcome) {
    case OUTCOME.applied:
      return withConfidence(TEXT.classificationSuggestedByAI, confidence)
    case OUTCOME.provisional: {
      if (!machineValue) return `${TEXT.classificationAwaiting}.`
      const held = `${TEXT.classificationAwaiting}. ${withConfidence(TEXT.classificationSuggestion(machineValue), confidence)}.`
      // Since 10 November a department already on the document stays, and a
      // different suggestion waits here (D-105's note). Confirming writes the
      // suggestion over the department shown, so the sentence says so rather than
      // leaving "Confirm" to be read as confirming the value on screen.
      return isDepartment && effectiveValue && effectiveValue !== machineValue
        ? `${held} ${TEXT.classificationConfirmReplaces(effectiveValue, machineValue)}`
        : held
    }
    case OUTCOME.confirmed:
      // The machine's value is kept beside the person's (FR-10); it is named only
      // where it differs, so a confirmation of the suggestion reads as one line.
      return machineValue && machineValue !== effectiveValue
        ? `${TEXT.classificationConfirmed}. ${withConfidence(TEXT.classificationSuggestion(machineValue), confidence)}.`
        : TEXT.classificationConfirmed
    case OUTCOME.discarded:
      if (!isDepartment) return null
      return machineValue
        ? TEXT.classificationDiscardedDepartment(machineValue)
        : TEXT.classificationDiscardedDepartmentUnnamed
    default:
      return null
  }
}

/**
 * The document's department after a confirm or an edit: the reply's
 * `department`, the column the server stored (docs/api-contract.md, FR-10;
 * D-105's note of 10 November). It is taken as it is; nothing is worked out from
 * the outcome or from what was sent.
 *
 * `inferForOlderServer` runs only when a reply carries no `department`, which
 * is a server from before 10 November, whose reply was `{classification}` alone.
 * Remove it once no such server is run against this front end.
 */
function departmentFromReply(reply, inferForOlderServer) {
  if (typeof reply?.department === 'string') return reply.department
  return inferForOlderServer()
}

/**
 * For an older server only (see `departmentFromReply`): the department this
 * section inferred before the reply carried one. An edit stored the department
 * it sent, and an empty-body confirm stored a held (provisional) suggestion.
 */
function departmentInferredForOlderServer(current, previous, next, sent) {
  if (sent.department !== undefined) return sent.department
  if (previous?.department_outcome === OUTCOME.provisional && next?.department_outcome === OUTCOME.confirmed) {
    return next.machine_department ?? current
  }
  return current
}

/**
 * One tag link, with its provenance in words and its one-action controls.
 *
 * A machine's tag and a person's tag are told apart by a word as well as by the
 * border (FR-10: "visually distinguished"; WCAG 2.1 SC 1.4.1), and a confirmed AI
 * tag says so. An unconfirmed AI tag offers Confirm and Remove; a person's tag,
 * or a confirmed one, Remove; a held suggestion, Confirm and Reject. Each
 * button's accessible name names its tag, starting with the visible word.
 */
function TagRow({ tag, held, controls, pending, onConfirm, onRemove }) {
  const ai = tag.applied_by === APPLIED_BY_AI
  const provenance = ai
    ? withConfidence(tag.confirmed === true ? TEXT.tagConfirmedAI : TEXT.tagSuggestedByAI, tag.confidence)
    : TEXT.tagAddedByPerson
  const confirmKey = `tag-confirm:${tag.content_tag_id}`
  const removeKey = `tag-remove:${tag.content_tag_id}`
  const mine = pending === confirmKey || pending === removeKey
  const otherBusy = pending !== null && !mine
  return (
    <li className={`tag ${ai ? 'tag--ai' : 'tag--user'}`}>
      {held ? <span className="tag__dimension">{dimensionLabel(tag.dimension)}</span> : null}
      <span className="tag__name">{tag.name}</span>
      <span className="tag__provenance">{provenance}</span>
      {controls ? (
        <span className="tag__actions">
          {isUnconfirmedAi(tag) ? (
            <Button
              variant="secondary"
              aria-label={TEXT.tagConfirmLabel(tag.name)}
              loading={pending === confirmKey}
              disabled={otherBusy || pending === removeKey}
              onClick={() => onConfirm(confirmKey)}
            >
              {TEXT.tagConfirm}
            </Button>
          ) : null}
          <Button
            variant="secondary"
            aria-label={held ? TEXT.tagRejectLabel(tag.name) : TEXT.tagRemoveLabel(tag.name)}
            loading={pending === removeKey}
            disabled={otherBusy || pending === confirmKey}
            onClick={() => onRemove(removeKey)}
          >
            {held ? TEXT.tagReject : TEXT.tagRemove}
          </Button>
        </span>
      ) : null}
    </li>
  )
}

/**
 * A Topic value the AI proposed that is not in the list of topics. No tag exists
 * for it until a person confirms it (FR-10's controlled taxonomy growth), so it
 * has no `content_tag_id` and is acted on by value.
 */
function ProposedTopicRow({ topic, controls, pending, onConfirm, onReject }) {
  const confirmKey = `topic-confirm:${topic.value}`
  const rejectKey = `topic-reject:${topic.value}`
  const mine = pending === confirmKey || pending === rejectKey
  const otherBusy = pending !== null && !mine
  return (
    <li className="tag tag--ai">
      <span className="tag__dimension">{TEXT.documentFieldTopic}</span>
      <span className="tag__name">{topic.value}</span>
      <span className="tag__provenance">{withConfidence(TEXT.proposedTopicLabel, topic.confidence)}</span>
      {controls ? (
        <span className="tag__actions">
          <Button
            variant="secondary"
            aria-label={TEXT.proposedTopicConfirmLabel(topic.value)}
            loading={pending === confirmKey}
            disabled={otherBusy || pending === rejectKey}
            onClick={() => onConfirm(confirmKey)}
          >
            {TEXT.tagConfirm}
          </Button>
          <Button
            variant="secondary"
            aria-label={TEXT.proposedTopicRejectLabel(topic.value)}
            loading={pending === rejectKey}
            disabled={otherBusy || pending === confirmKey}
            onClick={() => onReject(rejectKey)}
          >
            {TEXT.tagReject}
          </Button>
        </span>
      ) : null}
    </li>
  )
}

/**
 * FR-10's classification section of the document detail view (D-104, D-105).
 *
 * **Every AI value is marked as one in words.** FR-10 asks that the type and the
 * department be "each marked as AI-generated and editable", that provisional
 * assignments be "presented for confirmation rather than applied silently", and
 * that machine tags be "visually distinguished from those applied by a person".
 * Each is a sentence beside the value, never a colour or a border alone.
 *
 * **A held suggestion is never shown as the document's.** A provisional type
 * leaves `doc_type` null, and the type reads "Not yet assigned" with the
 * suggestion named beside it. A provisional tag is listed under "Suggested tags
 * awaiting confirmation" and nowhere else; a proposed Topic value likewise. A
 * discarded department is named in a sentence saying it was not applied, and the
 * department shown is the document's own.
 *
 * **One click is one request, and the section re-reads from the reply.** The
 * routes return what changed — the classification, the tag links, the one link,
 * or the department a confirm or an edit stored — and `onChange` hands it to the
 * page, which holds the record. Nothing is assumed about the result beyond what
 * the reply says (`departmentFromReply` keeps one inference, for an older server
 * only).
 *
 * **A department already on the document is the current one** while a different
 * suggestion waits (D-105's note of 10 November): the value shown is the
 * document's, the suggestion is named as awaiting confirmation, and the sentence
 * says that confirming replaces the one with the other.
 *
 * **Authorisation is the server's.** The controls are offered to everyone who can
 * read the document, because both roles hold `contribute_content` (D-105); a 403
 * on any action withdraws them and says why in words. A 404 reads as the delete
 * path's: the record could not be found, whether it is gone or now out of scope
 * (CLAUDE.md §6, invariant 1).
 *
 * Tag names and suggested values are text from the AI or from an uploader:
 * rendered as text children only, never as HTML.
 *
 * @param {object} props
 * @param {string} props.docId
 * @param {object|null|undefined} props.classification The detail's `classification`.
 * @param {object[]|undefined} props.tagDetails The detail's `tag_details`.
 * @param {string} props.department The document's own `department`, the effective one.
 * @param {(patch: {classification?: object, tag_details?: object[], department?: string}) => void} props.onChange
 */
export default function Classification({ docId, classification, tagDetails, department, onChange }) {
  const headingId = useId()
  const heldHeadingId = useId()
  const legendId = useId()
  const headingRef = useRef(null)
  const editButtonRef = useRef(null)
  const typeSelectRef = useRef(null)
  // One request at a time, whichever control was pressed, even if a second press
  // lands before the busy state has rendered.
  const inFlight = useRef(false)
  const [pending, setPending] = useState(null)
  const [failure, setFailure] = useState(null)
  // The latest outcome, announced in a live region. A new object on every call,
  // so the same sentence twice running still re-runs the focus effect below.
  const [announcement, setAnnouncement] = useState(null)
  // A 403 was answered: the role may not change classifications. The controls go.
  const [refused, setRefused] = useState(false)
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({ docType: DOCUMENT_TYPES[0], department: '' })
  const [fieldErrors, setFieldErrors] = useState({})
  // Where focus should go once the control that had it has left the page: the
  // Edit button after a save, else the section heading.
  const focusAfter = useRef(null)

  const tags = Array.isArray(tagDetails) ? tagDetails : []
  const applied = tags.filter((tag) => tag.provisional !== true)
  const held = tags.filter((tag) => tag.provisional === true)
  const proposedTopics = Array.isArray(classification?.proposed_topics) ? classification.proposed_topics : []
  const controls = !refused
  const classified = classification !== null && classification !== undefined

  // After an action the pressed button may be gone — a removed tag, a Confirm that
  // became a Remove — leaving focus on the body. It goes somewhere deliberate.
  useEffect(() => {
    if (!announcement) return
    const active = document.activeElement
    if (active && active !== document.body && active.isConnected) return
    const target = focusAfter.current?.() ?? headingRef.current
    focusAfter.current = null
    target?.focus()
  }, [announcement])

  // The edit form opens on its first field.
  useEffect(() => {
    if (editing) typeSelectRef.current?.focus()
  }, [editing])

  function announce(text) {
    setAnnouncement({ text })
  }

  function fail(caught, { onFieldErrors } = {}) {
    const error =
      caught instanceof ApiError ? caught : new ApiError(NETWORK_ERROR_STATUS, messageForStatus(NETWORK_ERROR_STATUS))
    switch (error.status) {
      case 403:
        // The role may not change classifications, whatever it was offered. The
        // controls go and the sentence says why; the record stays.
        setRefused(true)
        setEditing(false)
        setFailure({ variant: 'error', title: TEXT.classificationFailed, text: TEXT.classificationNotPermitted })
        return
      case 404:
        // Gone, or now outside the caller's scope: one message for both, the
        // delete path's (invariant 1).
        setFailure({ variant: 'error', title: TEXT.classificationFailed, text: TEXT.documentRecordNotFound })
        return
      case 503:
        // NFR-19: shown the moment the reply lands. The client's fixed text, then
        // what became of the record. The notice's own title names the service.
        setFailure({ variant: 'unavailable', title: undefined, text: `${error.message} ${TEXT.classifyNotDone}` })
        return
      case 422:
        setFailure({ variant: 'error', title: TEXT.classifyFailedTitle, text: TEXT.classifyNoText })
        return
      case 429:
        setFailure({
          variant: 'error',
          title: TEXT.classifyFailedTitle,
          text: TEXT.classifyLimitReached(whenToRetry(error.retryAfter)),
        })
        return
      case 400:
        if (onFieldErrors) {
          // DRF's validation message, under the field it names; the notice points at it.
          const { fieldErrors: perField, formError } = extractFieldErrors(error, EDIT_FIELDS)
          onFieldErrors(perField)
          setFailure({
            variant: 'error',
            title: TEXT.classificationFailed,
            text: formError ?? TEXT.classificationCheckFields,
          })
          return
        }
        setFailure({ variant: 'error', title: TEXT.classificationFailed, text: error.message })
        return
      default:
        // Fixed, user-facing text from the API client. Never a backend string.
        setFailure({ variant: 'error', title: TEXT.classificationFailed, text: error.message })
    }
  }

  /** Sends one request for one control and hands its reply on; one at a time. */
  async function run(key, request, onSuccess, options = {}) {
    if (inFlight.current) return
    inFlight.current = true
    setPending(key)
    setFailure(null)
    try {
      const body = await request()
      onSuccess(body)
    } catch (caught) {
      fail(caught, options)
    } finally {
      inFlight.current = false
      setPending(null)
    }
  }

  function classifyNow() {
    run(
      KEY.classify,
      () => classifyDocument(docId),
      (body) => {
        // Known gap: the classify reply carries no `department` (docs/api-contract.md),
        // and a run fills a blank department with an applied suggestion (D-105), so
        // the department shown stays blank until the page is read again. Raised with
        // the lead for the reply to carry it, as the confirm reply does; nothing is
        // inferred here meanwhile.
        onChange({ classification: body?.classification ?? null, tag_details: body?.tag_details ?? [] })
        announce(TEXT.classifyDone)
      },
    )
  }

  function confirmAll() {
    const previous = classification
    run(
      KEY.confirm,
      () => confirmClassification(docId, {}),
      (body) => {
        const next = body?.classification ?? previous
        onChange({
          classification: next,
          department: departmentFromReply(body, () => departmentInferredForOlderServer(department, previous, next, {})),
        })
        announce(TEXT.classificationConfirmedAll)
      },
    )
  }

  function openEdit() {
    // The type starts from the document's, or, while that is held, from the
    // suggestion, because the list has no empty choice. The department starts
    // from the document's own whenever it has one, so saving a changed type never
    // also writes a held suggestion over it that the person did not choose. Only a
    // blank department starts from the suggestion, as the server itself fills only
    // a blank department (D-105's note of 10 November).
    const docType =
      classification?.doc_type ??
      (DOCUMENT_TYPES.includes(classification?.machine_doc_type) ? classification.machine_doc_type : DOCUMENT_TYPES[0])
    const startDepartment =
      !department && classification?.department_outcome === OUTCOME.provisional && classification?.machine_department
        ? classification.machine_department
        : (department ?? '')
    setForm({ docType, department: startDepartment })
    setFieldErrors({})
    setEditing(true)
  }

  function cancelEdit() {
    if (pending === KEY.edit) return
    setEditing(false)
    setFieldErrors({})
    // The Edit button is back on the next commit; focus follows it then.
    focusAfter.current = () => editButtonRef.current
    announce('')
  }

  function saveEdit(event) {
    event.preventDefault()
    const sent = { docType: form.docType, department: form.department.trim() }
    const previous = classification
    setFieldErrors({})
    run(
      KEY.edit,
      () => confirmClassification(docId, sent),
      (body) => {
        const next = body?.classification ?? previous
        onChange({
          classification: next,
          department: departmentFromReply(body, () =>
            departmentInferredForOlderServer(department, previous, next, { department: sent.department }),
          ),
        })
        setEditing(false)
        focusAfter.current = () => editButtonRef.current
        announce(TEXT.classificationSaved)
      },
      { onFieldErrors: setFieldErrors },
    )
  }

  function confirmOneTag(tag, key) {
    run(
      key,
      () => confirmTag(docId, tag.content_tag_id),
      (entry) => {
        const updated = entry && typeof entry === 'object' ? entry : { ...tag, confirmed: true, provisional: false }
        onChange({ tag_details: tags.map((item) => (item.content_tag_id === tag.content_tag_id ? updated : item)) })
        announce(TEXT.tagConfirmed(tag.name))
      },
    )
  }

  function removeOneTag(tag, key) {
    run(
      key,
      () => removeTag(docId, tag.content_tag_id),
      () => {
        onChange({ tag_details: tags.filter((item) => item.content_tag_id !== tag.content_tag_id) })
        announce(tag.provisional === true ? TEXT.tagRejected(tag.name) : TEXT.tagRemoved(tag.name))
      },
    )
  }

  function decideTopic(topic, confirm, key) {
    run(
      key,
      () => (confirm ? confirmProposedTopic(docId, topic.value) : rejectProposedTopic(docId, topic.value)),
      (body) => {
        onChange({
          classification: body?.classification ?? classification,
          tag_details: Array.isArray(body?.tag_details) ? body.tag_details : tags,
        })
        announce(confirm ? TEXT.proposedTopicConfirmed(topic.value) : TEXT.proposedTopicRejected(topic.value))
      },
    )
  }

  const typeProvenance = classified
    ? provenanceFor(
        classification.doc_type_outcome,
        classification.machine_doc_type,
        classification.machine_doc_type_confidence,
        classification.doc_type,
        false,
      )
    : null
  const departmentProvenance = classified
    ? provenanceFor(
        classification.department_outcome,
        classification.machine_department,
        classification.machine_department_confidence,
        department,
        true,
      )
    : null
  const confirmable =
    classified &&
    [classification.doc_type_outcome, classification.department_outcome].some(
      (outcome) => outcome === OUTCOME.applied || outcome === OUTCOME.provisional,
    )
  const anythingHeld = held.length > 0 || proposedTopics.length > 0
  const classifying = pending === KEY.classify

  return (
    <section className="classification" aria-labelledby={headingId}>
      <h2 id={headingId} ref={headingRef} tabIndex={-1}>
        {TEXT.classificationHeading}
      </h2>
      <p className="classification__intro">{TEXT.classificationIntro}</p>

      {failure ? (
        <Notice variant={failure.variant} title={failure.title}>
          {failure.text}
        </Notice>
      ) : null}
      {/* The wait while the AI classifies, then the latest outcome: one live region.
          The wait is read off `pending`, not announced, so it moves no focus. */}
      <p className="classification__announcement" role="status">
        {classifying ? TEXT.classifyingStatus : (announcement?.text ?? '')}
      </p>

      {!classified ? (
        <>
          <p className="classification__state">
            <strong>{TEXT.classificationNone}</strong> {TEXT.classificationNoneHint}
          </p>
          {controls ? (
            <div className="classification__actions">
              <Button loading={classifying} disabled={pending !== null && !classifying} onClick={classifyNow}>
                {classifying ? TEXT.classifying : TEXT.classifyNow}
              </Button>
            </div>
          ) : null}
        </>
      ) : (
        <>
          <dl className="classification__assignments">
            <dt>{TEXT.classificationFieldType}</dt>
            <dd>
              <span className="classification__value">
                {classification.doc_type || TEXT.classificationNotAssigned}
              </span>
              {typeProvenance ? <span className="classification__provenance">{typeProvenance}</span> : null}
            </dd>
            <dt>{TEXT.classificationFieldDepartment}</dt>
            <dd>
              <span className="classification__value">{department || TEXT.documentNotRecorded}</span>
              {departmentProvenance ? (
                <span className="classification__provenance">{departmentProvenance}</span>
              ) : null}
            </dd>
          </dl>
          {classification.input_truncated === true ? (
            <p className="classification__note">{TEXT.classificationTruncated}</p>
          ) : null}

          {controls && !editing ? (
            <div className="classification__actions">
              {confirmable ? (
                <Button
                  loading={pending === KEY.confirm}
                  disabled={pending !== null && pending !== KEY.confirm}
                  onClick={confirmAll}
                >
                  {pending === KEY.confirm ? TEXT.classificationConfirming : TEXT.classificationConfirmAll}
                </Button>
              ) : null}
              <Button ref={editButtonRef} variant="secondary" disabled={pending !== null} onClick={openEdit}>
                {TEXT.classificationEdit}
              </Button>
            </div>
          ) : null}

          {controls && editing ? (
            <form className="classification__form" aria-labelledby={legendId} onSubmit={saveEdit} noValidate>
              <fieldset className="classification__fieldset">
                <legend id={legendId} className="classification__legend">
                  {TEXT.classificationEditLegend}
                </legend>
                <SelectInput
                  ref={typeSelectRef}
                  label={TEXT.classificationFieldType}
                  name="doc_type"
                  options={DOCUMENT_TYPES.map((value) => ({ value, label: value }))}
                  value={form.docType}
                  error={fieldErrors.doc_type}
                  onChange={(event) => setForm((current) => ({ ...current, docType: event.target.value }))}
                />
                <TextInput
                  label={TEXT.classificationFieldDepartment}
                  name="department"
                  hint={TEXT.classificationDepartmentHint}
                  value={form.department}
                  error={fieldErrors.department}
                  maxLength={255}
                  onChange={(event) => setForm((current) => ({ ...current, department: event.target.value }))}
                />
              </fieldset>
              <div className="classification__actions">
                <Button type="submit" loading={pending === KEY.edit}>
                  {pending === KEY.edit ? TEXT.classificationSaving : TEXT.classificationSave}
                </Button>
                <Button variant="secondary" disabled={pending === KEY.edit} onClick={cancelEdit}>
                  {TEXT.classificationCancel}
                </Button>
              </div>
            </form>
          ) : null}
        </>
      )}

      {/* The document's tags, by dimension, each with its provenance. A held
          suggestion is not among them. */}
      <h3 className="classification__subheading">{TEXT.classificationTagsHeading}</h3>
      {TAG_DIMENSIONS.map(([dimension, label]) => {
        const inDimension = applied.filter((tag) => String(tag.dimension ?? '').toLowerCase() === dimension)
        return (
          <section key={dimension} className="tag-group" aria-label={label}>
            <h4 className="tag-group__heading">{label}</h4>
            {inDimension.length === 0 ? (
              <p className="tag-group__empty">{TEXT.documentNoTags}</p>
            ) : (
              <ul className="tag-list">
                {inDimension.map((tag) => (
                  <TagRow
                    key={tag.content_tag_id}
                    tag={tag}
                    held={false}
                    controls={controls}
                    pending={pending}
                    onConfirm={(key) => confirmOneTag(tag, key)}
                    onRemove={(key) => removeOneTag(tag, key)}
                  />
                ))}
              </ul>
            )}
          </section>
        )
      })}

      {anythingHeld ? (
        <section className="tag-group tag-group--held" aria-labelledby={heldHeadingId}>
          <h3 id={heldHeadingId} className="classification__subheading">
            {TEXT.suggestedTagsHeading}
          </h3>
          <p className="tag-group__intro">{TEXT.suggestedTagsIntro}</p>
          <ul className="tag-list">
            {held.map((tag) => (
              <TagRow
                key={tag.content_tag_id}
                tag={tag}
                held
                controls={controls}
                pending={pending}
                onConfirm={(key) => confirmOneTag(tag, key)}
                onRemove={(key) => removeOneTag(tag, key)}
              />
            ))}
            {proposedTopics.map((topic) => (
              <ProposedTopicRow
                key={`proposed:${topic.value}`}
                topic={topic}
                controls={controls}
                pending={pending}
                onConfirm={(key) => decideTopic(topic, true, key)}
                onReject={(key) => decideTopic(topic, false, key)}
              />
            ))}
          </ul>
        </section>
      ) : null}
    </section>
  )
}
