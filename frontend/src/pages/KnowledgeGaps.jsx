import { useRef, useState } from 'react'
import { ApiError, messageForStatus } from '../api/client.js'
import {
  KNOWLEDGE_GAP_STATUS,
  listKnowledgeGaps,
  runKnowledgeGapCycle,
  updateKnowledgeGapStatus,
} from '../api/knowledgeGaps.js'
import Button from '../components/Button.jsx'
import NotPermitted from '../components/NotPermitted.jsx'
import Notice from '../components/Notice.jsx'
import { TEXT } from '../constants.js'
import useApiResource from '../hooks/useApiResource.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { formatDate } from '../utils/dates.js'
import './KnowledgeGaps.css'

/**
 * What a row offers for its status: the visible words, the accessible name that
 * adds the entry's subject, and the status the PATCH sends. Null for a status
 * the vocabulary does not name: it is shown as the server sent it and offered
 * nothing, because what a change would mean for it is not known here.
 */
function actionFor(entry) {
  if (entry.status === KNOWLEDGE_GAP_STATUS.open) {
    return {
      label: TEXT.gapMarkAddressed,
      name: TEXT.gapMarkAddressedLabel(entry.subject),
      next: KNOWLEDGE_GAP_STATUS.addressed,
    }
  }
  if (entry.status === KNOWLEDGE_GAP_STATUS.addressed) {
    return { label: TEXT.gapReopen, name: TEXT.gapReopenLabel(entry.subject), next: KNOWLEDGE_GAP_STATUS.open }
  }
  return null
}

/** A count as the server sent it, or a dash for one that did not arrive — never an invented number. */
function figure(value) {
  return Number.isFinite(value) ? value : '—'
}

/**
 * The cycle's 201 in words. Every number in the summary is one of the four
 * counts the reply carries. When any of them is missing, the summary says only
 * that the cycle finished, rather than a sentence holding a number the reply did
 * not send.
 *
 * The two "added" counts are the questions and searches that entered the log,
 * and a row left out on permission grounds is in none of the four (D-108), so
 * the summary says nothing about what was read or what was left out.
 */
function describeCycle(cycle) {
  const {
    queries_considered: questions,
    searches_considered: searches,
    entries_created: created,
    entries_updated: updated,
  } = cycle ?? {}
  if (![questions, searches, created, updated].every(Number.isFinite)) return TEXT.gapsCycleDone
  return [
    TEXT.gapsCycleDone,
    TEXT.gapsCycleAdded(TEXT.gapsCycleQuestions(questions), TEXT.gapsCycleSearches(searches)),
    TEXT.gapsCycleEntries(TEXT.gapsCycleCreated(created), TEXT.gapsCycleUpdated(updated)),
  ].join(' ')
}

/**
 * The entries, in the order the server sent them: Open first by occurrence count
 * then last seen, then Addressed the same way (docs/api-contract.md). Nothing here
 * sorts, filters or trims them.
 *
 * `subject` is a question or a search term a user typed (D-107), so it is
 * rendered as text and never as HTML: it is untrusted input. Each row carries the
 * six fields the entry carries and nothing more; there is no asker, role or reason
 * to show, because none arrives (D-107, D-108).
 *
 * The action column is left out entirely once the server has refused an action
 * (`showActions` false), rather than left as a column of nothing.
 */
function GapTable({ entries, showActions, changing, onChangeStatus }) {
  return (
    <div className="table-scroll" role="region" aria-labelledby="gaps-list-heading" tabIndex={0}>
      <table className="gaps-table">
        <caption className="visually-hidden">{TEXT.gapsTableCaption}</caption>
        <thead>
          <tr>
            <th scope="col">{TEXT.gapsColumnSubject}</th>
            <th scope="col">{TEXT.gapsColumnOccurrences}</th>
            <th scope="col">{TEXT.gapsColumnStatus}</th>
            <th scope="col">{TEXT.gapsColumnFirstSeen}</th>
            <th scope="col">{TEXT.gapsColumnLastSeen}</th>
            {showActions ? (
              <th scope="col">
                <span className="visually-hidden">{TEXT.gapsColumnAction}</span>
              </th>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => {
            const action = actionFor(entry)
            const busy = changing.has(entry.gap_id)
            return (
              <tr key={entry.gap_id}>
                <th scope="row" className="gaps-table__subject">
                  {entry.subject}
                </th>
                <td className="gaps-table__count">{figure(entry.occurrence_count)}</td>
                <td>{entry.status}</td>
                <td className="gaps-table__date">
                  <time dateTime={entry.first_seen_at}>{formatDate(entry.first_seen_at)}</time>
                </td>
                <td className="gaps-table__date">
                  <time dateTime={entry.last_seen_at}>{formatDate(entry.last_seen_at)}</time>
                </td>
                {showActions ? (
                  <td className="gaps-table__action">
                    {/* `aria-disabled`, not `disabled`, while the change is in flight:
                        the button keeps focus, says it is unavailable, and the click
                        handler refuses a second press itself. */}
                    {action ? (
                      <Button
                        variant="secondary"
                        loading={busy}
                        aria-disabled={busy || undefined}
                        aria-label={action.name}
                        onClick={() => onChangeStatus(entry, action.next)}
                      >
                        {action.label}
                      </Button>
                    ) : null}
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
 * FR-19 knowledge-gap log (NIT3004, Objective 06): "A list, visible to
 * Administrators, of questions the system could not answer and searches
 * returning no results, grouped by subject with an occurrence count and the
 * ability to mark an entry as addressed."
 *
 * Reads `GET /api/knowledge-gaps` and shows the entries as the server ordered
 * them. Each entry has one action, "Mark addressed" on an Open entry and
 * "Reopen" on an Addressed one, which sends one `PATCH` per press and updates its
 * row from the reply, so the row shows what the server stored. "Run aggregation
 * now" runs one cycle (`POST /api/knowledge-gaps/cycles`), says what it added in
 * words, and reads the list again.
 *
 * The route is guarded by RequireRole, which sends anyone but an Administrator to
 * /403 (FR-06), and the navigation offers the link to Administrators only. Both
 * are usability. The server checks `review_knowledge_gaps` on every request
 * (CLAUDE.md §6, invariant 4): a 403 on the list renders the not-permitted notice
 * and nothing else, and a 403 on an action withdraws every action and says why.
 */
export default function KnowledgeGaps() {
  useDocumentTitle(TEXT.gapsHeading)
  const { data, loading, error, reload, setData } = useApiResource(listKnowledgeGaps)
  const entries = Array.isArray(data) ? data : []
  // Where focus goes when the control that was pressed is about to disappear.
  const headingRef = useRef(null)

  // The entries whose change is in flight. The ref is the guard: it is read and
  // written inside the click itself, so a second press before React has rendered
  // the first is refused as surely as one after. The state is what the rows render.
  const changingRef = useRef(new Set())
  const [changing, setChanging] = useState(() => new Set())
  const runningRef = useRef(false)
  const [running, setRunning] = useState(false)
  // The outcome of the last change: a 404, a refusal or a failure.
  const [notice, setNotice] = useState(null)
  // The outcome of the last cycle: `finished` with its summary, `unavailable` (503) or `failed`.
  const [cycleOutcome, setCycleOutcome] = useState(null)
  // True once the server has refused an action with a 403.
  const [refused, setRefused] = useState(false)
  // A row's new status, announced in the words the row now shows.
  const [announcement, setAnnouncement] = useState('')

  const actionsWithdrawn = refused || error?.status === 403

  /** A 403 on a change or a cycle: the role lacks the code now, whatever it held when the list was read. */
  function withdrawActions() {
    setRefused(true)
    setNotice({ variant: 'error', title: TEXT.notPermittedTitle, text: TEXT.gapsNotPermitted })
    headingRef.current?.focus()
  }

  async function handleChangeStatus(entry, next) {
    const id = entry.gap_id
    if (changingRef.current.has(id)) return
    changingRef.current.add(id)
    setChanging(new Set(changingRef.current))
    setNotice(null)
    try {
      const updated = await updateKnowledgeGapStatus(id, next)
      if (updated && typeof updated === 'object') {
        // The row becomes what the server stored. It stays where it is: the order
        // is the server's, and the next read of the list applies it.
        setData((current) =>
          Array.isArray(current) ? current.map((item) => (item.gap_id === id ? updated : item)) : current,
        )
        setAnnouncement(TEXT.statusAnnouncement(entry.subject, updated.status))
      }
    } catch (caught) {
      handleChangeError(caught)
    } finally {
      changingRef.current.delete(id)
      setChanging(new Set(changingRef.current))
    }
  }

  function handleChangeError(caught) {
    if (!(caught instanceof ApiError)) {
      setNotice({ variant: 'error', title: TEXT.gapUpdateFailed, text: messageForStatus() })
      return
    }
    if (caught.status === 403) {
      withdrawActions()
      return
    }
    if (caught.status === 404) {
      // The entry is gone, so the list on screen is out of date. The row's button
      // goes with the table while it is read again.
      setNotice({ variant: 'error', title: TEXT.gapUpdateFailed, text: TEXT.gapNotFound })
      reload()
      headingRef.current?.focus()
      return
    }
    // Fixed, user-facing text from the API client; never the server's.
    setNotice({ variant: 'error', title: TEXT.gapUpdateFailed, text: caught.message })
  }

  async function handleRun() {
    if (runningRef.current) return
    runningRef.current = true
    setRunning(true)
    setNotice(null)
    setCycleOutcome(null)
    try {
      const cycle = await runKnowledgeGapCycle()
      setCycleOutcome({ kind: 'finished', text: describeCycle(cycle) })
      // The cycle changed the log, so the list on screen is out of date.
      reload()
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 403) {
        withdrawActions()
      } else if (caught instanceof ApiError && caught.status === 503) {
        // NFR-19: the client's own 503 sentence, then what the contract makes true:
        // the cycle rolled back. The server's detail is never shown.
        setCycleOutcome({ kind: 'unavailable', text: `${caught.message} ${TEXT.gapsCycleNotRun}` })
      } else {
        setCycleOutcome({
          kind: 'failed',
          text: caught instanceof ApiError ? caught.message : messageForStatus(),
        })
      }
    } finally {
      runningRef.current = false
      setRunning(false)
    }
  }

  let listBody
  if (loading) {
    listBody = <p role="status">{TEXT.loadingGaps}</p>
  } else if (error?.status === 403) {
    listBody = <NotPermitted />
  } else if (error) {
    listBody = (
      <>
        <Notice variant="error" title={TEXT.gapsLoadFailed}>
          {error.message}
        </Notice>
        <div className="gaps-page__actions">
          <Button variant="secondary" onClick={reload}>
            {TEXT.uploadRetry}
          </Button>
        </div>
      </>
    )
  } else if (entries.length === 0) {
    listBody = <Notice variant="info">{TEXT.noGaps}</Notice>
  } else {
    listBody = (
      <GapTable
        entries={entries}
        showActions={!actionsWithdrawn}
        changing={changing}
        onChangeStatus={handleChangeStatus}
      />
    )
  }

  // Visible and live at once (usability finding 1): the words announced are the
  // words on the screen.
  let cycleStatus = ''
  if (running) cycleStatus = TEXT.gapsCycleWait
  else if (cycleOutcome?.kind === 'finished') cycleStatus = cycleOutcome.text

  return (
    <div className="gaps-page">
      <h1 id="gaps-heading" ref={headingRef} tabIndex={-1}>
        {TEXT.gapsHeading}
      </h1>
      <p className="gaps-page__intro">{TEXT.gapsIntro}</p>
      {notice ? (
        <Notice variant={notice.variant} title={notice.title}>
          {notice.text}
        </Notice>
      ) : null}

      {actionsWithdrawn ? null : (
        <section className="gaps-cycle" aria-labelledby="gaps-cycle-heading">
          <h2 id="gaps-cycle-heading" className="gaps-cycle__heading">
            {TEXT.gapsCycleHeading}
          </h2>
          <p className="gaps-cycle__hint">{TEXT.gapsCycleHint}</p>
          <Button loading={running} aria-disabled={running || undefined} onClick={handleRun}>
            {running ? TEXT.gapsCycleRunning : TEXT.gapsCycleRun}
          </Button>
          <p className="gaps-cycle__status" role="status" aria-live="polite">
            {cycleStatus}
          </p>
          {cycleOutcome?.kind === 'unavailable' ? (
            <Notice variant="unavailable">{cycleOutcome.text}</Notice>
          ) : null}
          {cycleOutcome?.kind === 'failed' ? (
            <Notice variant="error" title={TEXT.gapsCycleFailed}>
              {cycleOutcome.text}
            </Notice>
          ) : null}
        </section>
      )}

      <section className="gaps-list" aria-labelledby="gaps-list-heading">
        <h2 id="gaps-list-heading">{TEXT.gapsListHeading}</h2>
        {listBody}
      </section>

      {/* A row's new status, in the words the row shows, announced once. */}
      <p className="visually-hidden" role="status" aria-live="polite">
        {announcement}
      </p>
    </div>
  )
}
