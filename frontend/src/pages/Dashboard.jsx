import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ApiError, NETWORK_ERROR_STATUS, messageForStatus } from '../api/client.js'
import { DASHBOARD_FILTER_KEYS, fetchDashboard } from '../api/dashboard.js'
import Button from '../components/Button.jsx'
import DashboardPanel from '../components/DashboardPanel.jsx'
import Notice from '../components/Notice.jsx'
import SelectInput from '../components/SelectInput.jsx'
import TextInput from '../components/TextInput.jsx'
import { TEXT } from '../constants.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { formatDate } from '../utils/dates.js'
import { extractFieldErrors } from '../utils/fieldErrors.js'
import './Dashboard.css'

/* ---- Filters and the URL ------------------------------------------------- */

/** The filters the address holds, each `''` where it holds none. */
function filtersFromParams(params) {
  return Object.fromEntries(DASHBOARD_FILTER_KEYS.map((key) => [key, params.get(key) ?? '']))
}

/**
 * The address for a set of filters: only the ones carrying a value, in the
 * contract's order. An empty value and an absent one are the same request (the
 * contract), so they are made the same address too, and the string doubles as
 * the identity of the request the screen is showing.
 */
function paramsFromFilters(filters) {
  const params = new URLSearchParams()
  for (const key of DASHBOARD_FILTER_KEYS) {
    if (filters[key]) params.set(key, filters[key])
  }
  return params
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

/**
 * The one check made before sending: a start date after the end date. Both are
 * `YYYY-MM-DD`, so the strings compare in date order. The server refuses the same
 * range with a 400 (D-65); this only spares the round trip. A date that is not
 * `YYYY-MM-DD` at all can only arrive by editing the address, and is left to the
 * server, whose 400 names it under the control it concerns.
 */
function rangeIsInverted({ date_from: from, date_to: to }) {
  return ISO_DATE.test(from) && ISO_DATE.test(to) && from > to
}

/* ---- The one request ---------------------------------------------------- */

/**
 * The dashboard's single request, re-sent whenever the filters in the address
 * change. FR-14's Server-End clause is one endpoint "rather than issuing separate
 * calls per panel", so every panel reads from this and none fetches for itself.
 *
 * **Not `useApiResource`, deliberately.** That hook re-reads when its loader
 * changes but leaves `loading` false and the previous reply on screen while it
 * does. FR-14 asks that panels "display a loading state while data is retrieved",
 * which has to hold after a filter is applied as much as on arrival — a stale
 * reply under a new filter is the panel claiming to show something it does not.
 * So each reply is kept with the request it answers (`key`), and one that answers
 * an earlier request is never shown as the answer to the current one.
 *
 * `departments` is the last offered list seen, and survives a reload: the server
 * does not narrow it by the active filters (D-70) precisely so that the control
 * does not change under the user, and blanking it while the next reply is in
 * flight would do exactly that.
 *
 * @param {string} query The canonical query string; '' for no filters.
 * @param {boolean} blocked True where the filters were refused client-side and
 *   nothing is to be sent.
 */
function useDashboardSummary(query, blocked) {
  const [attempt, setAttempt] = useState(0)
  const [settled, setSettled] = useState({ key: null, payload: null, error: null })
  const [departments, setDepartments] = useState([])
  const key = `${attempt}?${query}`

  useEffect(() => {
    if (blocked) return undefined
    const controller = new AbortController()
    const filters = filtersFromParams(new URLSearchParams(query))
    fetchDashboard(filters, { signal: controller.signal }).then(
      (payload) => {
        if (controller.signal.aborted) return
        setSettled({ key, payload, error: null })
        if (Array.isArray(payload?.departments)) setDepartments(payload.departments)
      },
      (caught) => {
        // This screen cancelling its own request, because the filters moved on.
        if (caught?.name === 'AbortError' || controller.signal.aborted) return
        const error =
          caught instanceof ApiError
            ? caught
            : new ApiError(NETWORK_ERROR_STATUS, messageForStatus(NETWORK_ERROR_STATUS))
        setSettled({ key, payload: null, error })
      },
    )
    return () => controller.abort()
  }, [key, query, blocked])

  const retry = useCallback(() => setAttempt((current) => current + 1), [])
  const current = settled.key === key

  return {
    payload: current ? settled.payload : null,
    error: current ? settled.error : null,
    loading: !blocked && !current,
    departments,
    retry,
  }
}

/* ---- Filter form --------------------------------------------------------- */

/**
 * The department options: "All departments", then the departments the server
 * offered — those on documents in the caller's scope, never those on documents
 * they cannot see (D-70, invariant 1). The screen adds nothing from anywhere
 * else, with one exception: the department already in the address is offered
 * back even when the list does not hold it, so the control shows the filter that
 * is actually applied rather than reading "All departments" over a narrowed list.
 * That value is the user's own, so offering it discloses nothing.
 */
function departmentOptions(departments, applied) {
  const values = [...departments]
  if (applied && !values.includes(applied)) values.push(applied)
  return [
    { value: '', label: TEXT.dashboardAllDepartments },
    ...values.map((department) => ({ value: department, label: department })),
  ]
}

/**
 * The date range and department controls.
 *
 * A draft until "Apply filters" is pressed, then written to the address — the
 * filters live in the URL, not in this component (D-61's gap 3: follow a link,
 * press Back, and state held only in a component is gone). The page keys this
 * form on the applied query, so whenever the address changes — Back, a cleared
 * filter, the navigation's Dashboard link — the form is rebuilt from it and can
 * never show one filter while the panels show another.
 */
function DashboardFilters({ applied, departments, errors, onApply, onClear }) {
  const [draft, setDraft] = useState(applied)
  const [ownErrors, setOwnErrors] = useState({})
  const dateToRef = useRef(null)
  const rangeHintId = useId()

  const shown = { ...errors, ...ownErrors }
  const anyApplied = DASHBOARD_FILTER_KEYS.some((key) => applied[key])

  function handleChange(event) {
    const { name, value } = event.target
    setDraft((current) => ({ ...current, [name]: value }))
  }

  function handleSubmit(event) {
    event.preventDefault()
    if (rangeIsInverted(draft)) {
      // Refused before sending. The address does not change, so no request is
      // made, and focus goes to the control the message is under.
      setOwnErrors({ date_to: TEXT.dashboardRangeInverted })
      dateToRef.current?.focus()
      return
    }
    setOwnErrors({})
    onApply(draft)
  }

  return (
    <form className="dashboard-filters" aria-label={TEXT.dashboardFiltersLabel} noValidate onSubmit={handleSubmit}>
      <fieldset className="dashboard-filters__range">
        <legend className="dashboard-filters__legend">{TEXT.dashboardDateRange}</legend>
        <p id={rangeHintId} className="field__hint dashboard-filters__hint">
          {TEXT.dashboardDateRangeHint}
        </p>
        <div className="dashboard-filters__dates">
          <TextInput
            type="date"
            label={TEXT.dashboardDateFrom}
            name="date_from"
            value={draft.date_from}
            error={shown.date_from}
            describedBy={rangeHintId}
            onChange={handleChange}
          />
          <TextInput
            ref={dateToRef}
            type="date"
            label={TEXT.dashboardDateTo}
            name="date_to"
            value={draft.date_to}
            error={shown.date_to}
            describedBy={rangeHintId}
            onChange={handleChange}
          />
        </div>
      </fieldset>
      {/* D-70: the note that the department narrows documents only sits next to
          the control, as its hint, so it is read with it. */}
      <SelectInput
        className="dashboard-filters__department"
        label={TEXT.dashboardDepartment}
        name="department"
        hint={TEXT.dashboardDepartmentHint}
        options={departmentOptions(departments, applied.department)}
        value={draft.department}
        error={shown.department}
        onChange={handleChange}
      />
      <div className="dashboard-filters__actions">
        <Button type="submit">{TEXT.dashboardApplyFilters}</Button>
        {anyApplied ? (
          <Button variant="secondary" onClick={onClear}>
            {TEXT.dashboardClearFilters}
          </Button>
        ) : null}
      </div>
    </form>
  )
}

/**
 * The active filters, read from the reply's `filters` — what the server applied
 * after validation — and not from the form, which may hold an unapplied draft
 * (D-70: "the screen shows the active range").
 *
 * Always mounted and a polite live region, so the line that changes when a
 * filtered reply lands is also the announcement that it has (usability finding
 * 1: an acknowledgement on the screen, not only to assistive technology).
 */
function ActiveFilters({ filters }) {
  if (!filters) {
    return <p className="dashboard__active" role="status" />
  }
  return (
    <p className="dashboard__active" role="status">
      <span>
        {TEXT.dashboardActiveDates} <strong>{describeRange(filters)}</strong>
      </span>
      <span>
        {TEXT.dashboardActiveDepartment}{' '}
        <strong>
          {filters.department
            ? TEXT.dashboardDepartmentApplied(filters.department)
            : TEXT.dashboardAllDepartments}
        </strong>
      </span>
    </p>
  )
}

function describeRange({ date_from: from, date_to: to }) {
  if (from && to) return TEXT.dashboardRangeBetween(formatDate(from), formatDate(to))
  if (from) return TEXT.dashboardRangeFrom(formatDate(from))
  if (to) return TEXT.dashboardRangeUntil(formatDate(to))
  return TEXT.dashboardAllDates
}

/* ---- Panel contents ------------------------------------------------------ */

/*
 * Every title and question below is text from a document, a transcript or a
 * user, rendered as text and never as HTML. The lists are rendered exactly as
 * they arrived: the server scoped them before counting or ranking anything
 * (CLAUDE.md §6, invariant 1), and the screen neither filters nor trims them.
 */

function RecentDocuments({ documents }) {
  return (
    <ul className="dashboard-list">
      {documents.map((record) => (
        <li key={record.doc_id}>
          <Link className="dashboard-list__title" to={`/documents/${encodeURIComponent(record.doc_id)}`}>
            {record.title}
          </Link>
          <p className="dashboard-list__meta">
            <span>
              <span className="visually-hidden">Status: </span>
              {record.status}
            </span>
            {record.department ? (
              <span>
                <span className="visually-hidden">Department: </span>
                {record.department}
              </span>
            ) : null}
            <span>
              {TEXT.dashboardUploaded} <time dateTime={record.uploaded_at}>{formatDate(record.uploaded_at)}</time>
            </span>
          </p>
        </li>
      ))}
    </ul>
  )
}

function RecentMeetings({ meetings }) {
  return (
    <ul className="dashboard-list">
      {meetings.map((meeting) => (
        <li key={meeting.meeting_id}>
          <Link className="dashboard-list__title" to={`/meetings/${encodeURIComponent(meeting.meeting_id)}`}>
            {meeting.title}
          </Link>
          <p className="dashboard-list__meta">
            <span>
              <span className="visually-hidden">Status: </span>
              {meeting.status}
            </span>
            <span>
              {TEXT.dashboardHeld} <time dateTime={meeting.meeting_date}>{formatDate(meeting.meeting_date)}</time>
            </span>
          </p>
        </li>
      ))}
    </ul>
  )
}

/** A count as the server sent it, or a dash for one that did not arrive — never an invented 0. */
function figure(value) {
  return Number.isFinite(value) ? value : '—'
}

/**
 * D-70: the indexed total split by type — documents, meetings, and their sum —
 * so that the department filter visibly narrows only the documents figure. Each
 * figure links to its module's own view. The sum is the server's `total`, not
 * one added up here: every number on this panel is the server's post-scope count.
 */
function IndexedTotals({ totals }) {
  return (
    <>
      <dl className="dashboard-totals">
        <div className="dashboard-totals__item">
          <dt>
            <Link to="/documents">{TEXT.dashboardTotalsDocuments}</Link>
          </dt>
          <dd>{figure(totals?.documents)}</dd>
        </div>
        <div className="dashboard-totals__item">
          <dt>
            <Link to="/meetings">{TEXT.dashboardTotalsMeetings}</Link>
          </dt>
          <dd>{figure(totals?.meetings)}</dd>
        </div>
        <div className="dashboard-totals__item">
          <dt>{TEXT.dashboardTotalsSum}</dt>
          <dd>{figure(totals?.total)}</dd>
        </div>
      </dl>
      <p className="dashboard-panel__note">{TEXT.dashboardTotalsHint}</p>
    </>
  )
}

/**
 * D-68: the caller's own questions, and for each only the question as asked and
 * when. Nothing that looks like an answer: no answer text, no answered or
 * unanswered marker, no reason. A question links nowhere of its own, so the
 * panel's heading is the route to `/ask`. Ask now reads `/ask?c=<id>` (D-77) and
 * each question already carries its `conversation_id`, null for a one-off (D-68),
 * so a link from a question to its thread is front-end work only: a follow-up to
 * D-70 that no Stage 5 item names yet.
 */
function RecentQuestions({ questions }) {
  return (
    <ul className="dashboard-list">
      {questions.map((item, index) => (
        <li key={`${index}-${item.asked_at}`}>
          <p className="dashboard-list__question">{item.question}</p>
          <p className="dashboard-list__meta">
            <span>
              {TEXT.dashboardAsked} <time dateTime={item.asked_at}>{formatDate(item.asked_at)}</time>
            </span>
          </p>
        </li>
      ))}
    </ul>
  )
}

/* ---- The page ------------------------------------------------------------ */

/**
 * FR-14 dashboard overview: "the platform's entry point after login, presenting
 * a summary of recent documents, meetings, indexed content, and recent questions
 * in a single view". FR-02's login sends an Employee to `/dashboard` and an
 * Administrator to `/admin`, and both render this (D-70); the content differs
 * only because the server scopes it to the caller's role.
 *
 * The filters live in the address: `?date_from=&date_to=&department=`, the
 * contract's own parameter names. Following a panel's link and pressing Back
 * returns to the same filters and re-sends the same request.
 *
 * What the screen does not do is filter. Every list and every count arrives
 * already scoped to the caller's role by the server (FR-14: "counts are computed
 * after permission filtering, consistent with FR-11"), and nothing here hides,
 * trims or recounts what arrived, because a screen that filtered would be a
 * second scoping mechanism that could disagree with the first (CLAUDE.md §6,
 * invariants 1 and 4).
 */
export default function Dashboard() {
  useDocumentTitle(TEXT.dashboardHeading)
  const [params, setParams] = useSearchParams()
  const applied = filtersFromParams(params)
  const query = paramsFromFilters(applied).toString()
  // The form refuses an inverted range before it reaches the address, so one here
  // was typed or pasted. It is refused the same way: nothing is sent.
  const inverted = rangeIsInverted(applied)
  const { payload, error, loading, departments, retry } = useDashboardSummary(query, inverted)

  // A 400 names the parameter it refused. Its message, DRF's validation text for
  // that parameter, goes under the control it concerns (src/utils/fieldErrors.js);
  // nothing else from the server body is shown.
  const refusal = error?.status === 400 ? extractFieldErrors(error, DASHBOARD_FILTER_KEYS) : null
  const fieldErrors = inverted ? { date_to: TEXT.dashboardRangeInverted } : (refusal?.fieldErrors ?? {})
  const failed = inverted || error !== null

  function applyFilters(next) {
    setParams(paramsFromFilters(next))
  }

  function clearFilters() {
    setParams(new URLSearchParams())
  }

  let failure = null
  if (inverted) {
    failure = (
      <Notice variant="error" title={TEXT.dashboardLoadFailed}>
        {TEXT.dashboardRangeInverted}
      </Notice>
    )
  } else if (refusal) {
    // Retrying the same filters would be refused the same way, so there is no
    // retry here: the filter is what has to change.
    failure = (
      <Notice variant="error" title={TEXT.dashboardLoadFailed}>
        {refusal.formError ?? TEXT.dashboardCheckFilters}
      </Notice>
    )
  } else if (error) {
    // Fixed, user-facing text from the API client; never a backend string.
    failure = (
      <>
        <Notice variant="error" title={TEXT.dashboardLoadFailed}>
          {error.message}
        </Notice>
        <div className="dashboard__actions">
          <Button variant="secondary" onClick={retry}>
            {TEXT.uploadRetry}
          </Button>
        </div>
      </>
    )
  }

  const documents = payload?.recent_documents ?? []
  const meetings = payload?.recent_meetings ?? []
  const questions = payload?.recent_questions ?? []
  const panelState = { loading, failed }

  return (
    <div className="dashboard">
      <h1>{TEXT.dashboardHeading}</h1>
      <p className="dashboard__intro">{TEXT.dashboardIntro}</p>
      <DashboardFilters
        key={query}
        applied={applied}
        departments={departments}
        errors={fieldErrors}
        onApply={applyFilters}
        onClear={clearFilters}
      />
      {failure}
      <ActiveFilters filters={payload ? (payload.filters ?? {}) : null} />
      {/* In the proposal's order: recent documents, recent meetings, total indexed
          items, recent questions. The DOM order is the tab order. */}
      <div className="dashboard__panels">
        <DashboardPanel
          headingId="dashboard-documents-heading"
          heading={TEXT.dashboardDocumentsHeading}
          to="/documents"
          loadingText={TEXT.dashboardLoadingDocuments}
          empty={documents.length === 0}
          emptyText={TEXT.dashboardNoDocuments}
          {...panelState}
        >
          <RecentDocuments documents={documents} />
        </DashboardPanel>
        <DashboardPanel
          headingId="dashboard-meetings-heading"
          heading={TEXT.dashboardMeetingsHeading}
          to="/meetings"
          loadingText={TEXT.dashboardLoadingMeetings}
          empty={meetings.length === 0}
          emptyText={TEXT.dashboardNoMeetings}
          {...panelState}
        >
          <RecentMeetings meetings={meetings} />
        </DashboardPanel>
        <DashboardPanel
          headingId="dashboard-totals-heading"
          heading={TEXT.dashboardTotalsHeading}
          loadingText={TEXT.dashboardLoadingTotals}
          {...panelState}
        >
          <IndexedTotals totals={payload?.indexed_totals} />
        </DashboardPanel>
        <DashboardPanel
          headingId="dashboard-questions-heading"
          heading={TEXT.dashboardQuestionsHeading}
          to="/ask"
          loadingText={TEXT.dashboardLoadingQuestions}
          empty={questions.length === 0}
          emptyText={TEXT.dashboardNoQuestions}
          {...panelState}
        >
          <RecentQuestions questions={questions} />
        </DashboardPanel>
      </div>
    </div>
  )
}
