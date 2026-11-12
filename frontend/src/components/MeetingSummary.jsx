import { useEffect, useId, useRef, useState } from 'react'
import { ApiError, NETWORK_ERROR_STATUS, messageForStatus } from '../api/client.js'
import { requestMeetingSummary } from '../api/meetings.js'
import { SUMMARY_STATUS, TEXT } from '../constants.js'
import useMeetingSummary from '../hooks/useMeetingSummary.js'
import usePassagePanels from '../hooks/usePassagePanels.js'
import { formatDate } from '../utils/dates.js'
import { referencedElements } from '../utils/passages.js'
import { whenToRetry } from '../utils/retryAfter.js'
import ActionItems from './ActionItems.jsx'
import AiMark from './AiMark.jsx'
import Button from './Button.jsx'
import Notice from './Notice.jsx'
import { PassageMarkers, PassagePanels } from './PassageReferences.jsx'
import './MeetingSummary.css'

/**
 * The decisions or the highlights: a list, each entry with its passage
 * references, and nothing at all where the summary has none (FR-16's panel shows
 * what the run found; an empty heading would claim a section that is not there).
 */
function ReferencedList({ idPrefix, heading, elements, passages, open, onToggle }) {
  if (elements.length === 0) return null
  return (
    <>
      <h3 className="meeting-summary__subheading">{heading}</h3>
      <ul className="meeting-summary__list">
        {elements.map((element, index) => {
          const prefix = `${idPrefix}-${index}`
          return (
            // The index is the key: the list is one summary's and never reorders.
            <li key={index}>
              <p className="meeting-summary__element">
                {element.text}
                <PassageMarkers
                  idPrefix={prefix}
                  numbers={element.passages}
                  passages={passages}
                  open={open}
                  onToggle={onToggle}
                />
              </p>
              <PassagePanels idPrefix={prefix} numbers={element.passages} passages={passages} open={open} />
            </li>
          )
        })}
      </ul>
    </>
  )
}

/**
 * One Ready summary, as FR-16's panel shows it: the narrative as one paragraph,
 * then the decisions and the highlights (UC-04: "a narrative account of the
 * meeting, the decisions reached ... and the highlights of discussion").
 *
 * **Every sentence, decision and highlight shows its passage references**, and a
 * reference opens the transcript passage it names (UC-04: "Every element of the
 * summary carries a reference to the passage of the transcript it was drawn
 * from"). An element with no reference is not shown: the server sends none, and
 * `referencedElements` keeps it so whatever arrives. For the same reason the
 * narrative is built from `narrative` and never from `summary_text`, which is the
 * same sentences without their references.
 *
 * **It is AI content and says so first** (NFR-15): the mark, then UC-04's "record
 * of the model that produced it and the date of production", inside the dashed
 * boundary the convention gives AI content. A summary cut short says how much of
 * the transcript it covers (D-125), rather than reading as the whole meeting.
 *
 * The text is the model's, from a transcript anyone may have supplied: rendered as
 * text children only, never as HTML.
 *
 * @param {object} props
 * @param {object} props.summary The summary state's `summary`: a Ready one, always.
 */
export function SummaryContent({ summary }) {
  const idPrefix = useId()
  const [open, toggle] = usePassagePanels()
  const narrative = referencedElements(summary.narrative)
  const decisions = referencedElements(summary.decisions)
  const highlights = referencedElements(summary.highlights)
  const passages = summary.passages
  const sent = summary.passages_sent
  const total = summary.passages_total

  return (
    <div className="meeting-summary__content ai-content">
      <p className="meeting-summary__provenance">
        <AiMark />
        {summary.model ? <span>{TEXT.summaryModel(summary.model)}</span> : null}
        {summary.generated_at ? (
          <span>
            {TEXT.summaryGenerated}{' '}
            <time dateTime={summary.generated_at}>{formatDate(summary.generated_at)}</time>
          </span>
        ) : null}
      </p>
      {summary.input_truncated === true ? (
        <p className="meeting-summary__note">
          {Number.isFinite(sent) && Number.isFinite(total)
            ? TEXT.summaryTruncated(sent, total)
            : TEXT.summaryTruncatedOpening}
        </p>
      ) : null}

      {narrative.length > 0 ? (
        <>
          <p className="meeting-summary__narrative">
            {narrative.map((sentence, index) => (
              <span key={index}>
                {index > 0 ? ' ' : null}
                {sentence.text}
                <PassageMarkers
                  idPrefix={`${idPrefix}-narrative-${index}`}
                  numbers={sentence.passages}
                  passages={passages}
                  open={open}
                  onToggle={toggle}
                />
              </span>
            ))}
          </p>
          {/* After the paragraph and in its order: a passage is a block, and a
              paragraph cannot hold one. */}
          {narrative.map((sentence, index) => (
            <PassagePanels
              key={index}
              idPrefix={`${idPrefix}-narrative-${index}`}
              numbers={sentence.passages}
              passages={passages}
              open={open}
            />
          ))}
        </>
      ) : null}

      <ReferencedList
        idPrefix={`${idPrefix}-decision`}
        heading={TEXT.summaryDecisionsHeading}
        elements={decisions}
        passages={passages}
        open={open}
        onToggle={toggle}
      />
      <ReferencedList
        idPrefix={`${idPrefix}-highlight`}
        heading={TEXT.summaryHighlightsHeading}
        elements={highlights}
        passages={passages}
        open={open}
        onToggle={toggle}
      />
    </div>
  )
}

/**
 * What the panel says about where the summary stands, in one sentence, from the
 * summary state alone. "" where a Ready summary speaks for itself.
 *
 * `status` is the latest run's and `summary` the latest Ready one, so they can
 * differ: while a Regenerate runs, and after one fails, the previous summary is
 * still shown, and each sentence then says so rather than reading as though
 * nothing were on screen.
 */
function standing({ tooShort, status, queued, hasSummary, justFinished }) {
  // FR-16's 422. Nothing was sent to the model, and nothing will be.
  if (tooShort) return TEXT.summaryTooShort
  if (status === SUMMARY_STATUS.processing) return hasSummary ? TEXT.summaryRegenerating : TEXT.summaryProcessing
  if (status === SUMMARY_STATUS.unavailable) {
    // UC-04 E1 and NFR-20: queued, it will be tried again without anyone asking.
    if (queued) return hasSummary ? TEXT.summaryRegeneratePendingRetry : TEXT.summaryPendingRetry
    return hasSummary ? TEXT.summaryRegenerateUnavailable : TEXT.summaryUnavailable
  }
  if (!hasSummary) return TEXT.summaryNone
  return justFinished ? TEXT.summaryReady : ''
}

/**
 * FR-16's "Summary" panel: "shows a concise paragraph-length summary once
 * processing completes", with the button that starts a run.
 *
 * **Only `summary` is ever rendered as a summary.** It is the latest Ready one or
 * null, and a failed run has no text in the reply at all (UC-04: "in the failed
 * state it is never presented to a user"). So there is no state here that shows a
 * failed or partial summary, greyed out or otherwise: an "Unavailable" run is a
 * sentence, and whatever stands under it is the previous Ready summary or nothing.
 *
 * **The button** reads "Regenerate Summary" (FR-16) when a Ready summary exists
 * and "Generate Summary" (NFR-14's label) when none does. It is offered only when
 * the state says `can_edit`, never for a transcript too short to summarise, and it
 * is disabled while a run is in flight. Pressing it sends the POST, whose 202
 * carries the state with `status` "Processing", and the page then asks again until
 * the run settles (src/hooks/useMeetingSummary.js). Showing it is usability; the
 * server checks `contribute_content` on every POST (CLAUDE.md §6, invariant 4), and
 * a 403 withdraws it and says why.
 *
 * **The wait is said, not only spun**: the standing sentence is in a polite live
 * region, so "being generated", "ready" and "could not be generated" are each
 * announced as they become true. A check that fails stops the asking and says so
 * (NFR-19's rule against a wait that never resolves).
 *
 * @param {object} props
 * @param {string} props.meetingId
 * @param {ReturnType<typeof useMeetingSummary>} props.resource
 * @param {boolean} props.canEdit `can_edit`, and no write has been refused.
 * @param {() => void} props.onRefused A write answered 403.
 */
function SummaryPanel({ meetingId, resource, canEdit, onRefused }) {
  const headingId = useId()
  const headingRef = useRef(null)
  // One POST at a time, even if the button is pressed again before the busy
  // state has rendered.
  const inFlight = useRef(false)
  const [starting, setStarting] = useState(false)
  // The last press's refusal. A new object each time, so the same refusal twice
  // running still re-runs the focus effect below.
  const [failure, setFailure] = useState(null)
  // Bumped when a press started a run, for the same effect.
  const [started, setStarted] = useState(0)

  const { loading, error, checkError, tooShort, state } = resource
  const status = state?.status ?? null
  const summary = state?.summary && typeof state.summary === 'object' ? state.summary : null
  const processing = status === SUMMARY_STATUS.processing

  // Whether the run this page was waiting on has just finished, so its arrival is
  // announced. Adjusted while rendering, from the status as it was last rendered.
  const [watched, setWatched] = useState({ status, justFinished: false })
  if (watched.status !== status) {
    setWatched({
      status,
      justFinished: watched.status === SUMMARY_STATUS.processing && status === SUMMARY_STATUS.ready,
    })
  }

  // After a press, the button may be gone (a 403) or disabled (a run began),
  // leaving focus on nothing. It goes to the panel's heading, under which the
  // outcome is said.
  useEffect(() => {
    if (!failure && started === 0) return
    const active = document.activeElement
    if (active && active !== document.body && active.isConnected && !active.disabled) return
    headingRef.current?.focus()
  }, [failure, started])

  async function generate() {
    if (inFlight.current) return
    inFlight.current = true
    setStarting(true)
    setFailure(null)
    try {
      resource.apply(await requestMeetingSummary(meetingId))
      setStarted((count) => count + 1)
    } catch (caught) {
      const refusal =
        caught instanceof ApiError
          ? caught
          : new ApiError(NETWORK_ERROR_STATUS, messageForStatus(NETWORK_ERROR_STATUS))
      switch (refusal.status) {
        case 403:
          // The role may not start a run, whatever `can_edit` said. Every control
          // behind the same permission goes, in both panels.
          onRefused()
          setFailure({ text: TEXT.meetingContributionNotPermitted })
          break
        case 404:
          // Gone, or now outside the caller's scope: one message for both, the
          // page's own (invariant 1). The panel is read again and will say the same.
          setFailure({ text: TEXT.meetingNotFound })
          resource.reload()
          break
        case 429:
          // The ingestion limit (D-79), with when to try again from Retry-After.
          setFailure({ text: TEXT.summaryLimitReached(whenToRetry(refusal.retryAfter)) })
          break
        default:
          // Fixed, user-facing text from the API client. Never a backend string.
          setFailure({ text: refusal.message })
      }
    } finally {
      inFlight.current = false
      setStarting(false)
    }
  }

  let body
  if (loading) {
    body = <p role="status">{TEXT.loadingSummary}</p>
  } else if (error || !state) {
    // A 404 is the meeting gone or out of scope since the page loaded, said in the
    // words the page itself uses for one, and trying again cannot change it.
    const notFound = error?.status === 404
    body = (
      <>
        <Notice variant="error" title={notFound ? TEXT.documentNotFoundTitle : TEXT.summaryLoadFailed}>
          {notFound ? TEXT.meetingNotFound : (error?.message ?? messageForStatus())}
        </Notice>
        {notFound ? null : (
          <div className="meeting-summary__actions">
            <Button variant="secondary" onClick={resource.reload}>
              {TEXT.uploadRetry}
            </Button>
          </div>
        )}
      </>
    )
  } else {
    const offered = canEdit && !tooShort
    body = (
      <>
        {failure ? (
          <Notice variant="error" title={TEXT.summaryRequestFailed}>
            {failure.text}
          </Notice>
        ) : null}
        {/* One live region for where the summary stands. While a check has failed
            it says nothing, because the notice under it says what is known. */}
        <p className="meeting-summary__standing" role="status">
          {checkError
            ? ''
            : standing({
                tooShort,
                status,
                queued: state.queued_for_retry === true,
                hasSummary: summary !== null,
                justFinished: watched.justFinished,
              })}
        </p>
        {checkError ? (
          <>
            <Notice variant="error" title={TEXT.summaryCheckFailed}>
              {checkError.message}
            </Notice>
            <div className="meeting-summary__actions">
              <Button variant="secondary" onClick={resource.reload}>
                {TEXT.uploadRetry}
              </Button>
            </div>
          </>
        ) : null}

        {/* Keyed on the summary, so a regenerated one starts with its passages closed. */}
        {summary ? <SummaryContent key={summary.summary_id ?? 'summary'} summary={summary} /> : null}

        {offered ? (
          <>
            <div className="meeting-summary__actions">
              {/* Disabled while a run is in flight. While its own POST is, it stays
                  enabled and ignores a second press, so focus is not thrown off it
                  mid-request. */}
              <Button loading={starting} disabled={processing && !starting} onClick={generate}>
                {starting ? TEXT.summaryStarting : summary ? TEXT.summaryRegenerate : TEXT.summaryGenerate}
              </Button>
            </div>
            {summary ? <p className="meeting-summary__hint">{TEXT.summaryRegenerateHint}</p> : null}
          </>
        ) : null}
      </>
    )
  }

  return (
    <section className="meeting-summary" aria-labelledby={headingId}>
      <h2 id={headingId} ref={headingRef} tabIndex={-1}>
        {TEXT.summaryHeading}
      </h2>
      {body}
    </section>
  )
}

/**
 * FR-16 on the meeting page: the "Summary" panel and the "Action Items" panel,
 * both fed by one read of `GET /api/meetings/{id}/summary` (D-125).
 *
 * The read is this component's own, apart from the meeting's, so the transcript is
 * on the page whatever the summary does: slow, failed, too short or never
 * requested (NFR-20, "summary failure never blocks the transcript from being
 * stored or searched"). While it fails, both panels say so and nothing else on the
 * page changes.
 *
 * **One refusal withdraws every control.** Generating a summary and adding,
 * editing or deleting an action item all need `contribute_content`, so a 403 on
 * any of them means the role does not hold it now, whatever `can_edit` said when
 * the panels loaded: the button and every Edit, Delete and Add go together, and
 * the panel where it happened says why.
 *
 * Give it a `key` of the meeting's id, so another meeting starts from nothing.
 *
 * @param {object} props
 * @param {string} props.meetingId
 */
export default function MeetingSummary({ meetingId }) {
  const resource = useMeetingSummary(meetingId)
  const [refused, setRefused] = useState(false)
  const state = resource.state
  const summary = state?.summary && typeof state.summary === 'object' ? state.summary : null
  const canEdit = state?.can_edit === true && !refused

  return (
    <>
      <SummaryPanel
        meetingId={meetingId}
        resource={resource}
        canEdit={canEdit}
        onRefused={() => setRefused(true)}
      />
      <ActionItems
        meetingId={meetingId}
        loading={resource.loading}
        unavailable={!resource.loading && (resource.error !== null || !state)}
        items={Array.isArray(state?.action_items) ? state.action_items : []}
        passages={summary?.passages ?? null}
        // UC-04 A1: a Ready summary whose run extracted none.
        noneRaised={summary !== null && summary.action_items_extracted === 0}
        canEdit={canEdit}
        onItemsChange={resource.updateItems}
        onRefused={() => setRefused(true)}
        onStale={resource.reload}
      />
    </>
  )
}
