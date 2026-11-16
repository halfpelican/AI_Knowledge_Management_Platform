import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, NETWORK_ERROR_STATUS, messageForStatus } from '../api/client.js'
import { SUMMARY_TOO_SHORT_STATUS, fetchMeetingSummary } from '../api/meetings.js'
import { MEETING_SUMMARY_POLL_MS, SUMMARY_STATUS } from '../constants.js'

/** Any failure as an `ApiError`, so a screen can branch on its status and show its fixed message. */
function failureOf(caught) {
  return caught instanceof ApiError
    ? caught
    : new ApiError(NETWORK_ERROR_STATUS, messageForStatus(NETWORK_ERROR_STATUS))
}

/** Nothing read yet for this meeting. */
function unread(meetingId) {
  return { meetingId, loading: true, error: null, checkError: null, httpStatus: null, state: null }
}

/** A summary route's answer as the resource holds it, or the failure a body-less answer is. */
function settled(meetingId, answer) {
  if (!answer.state || typeof answer.state !== 'object') {
    // A 2xx with no body is not something the contract allows. Handled as a
    // failure, so the panels never read fields off nothing.
    return { ...unread(meetingId), loading: false, error: new ApiError(answer.status, messageForStatus()) }
  }
  return { meetingId, loading: false, error: null, checkError: null, httpStatus: answer.status, state: answer.state }
}

/**
 * FR-16's summary state for one meeting: `GET /api/meetings/{id}/summary`, read
 * once, and read again every MEETING_SUMMARY_POLL_MS while the latest run is
 * "Processing" (FR-16: "202 Accepted while processing, 200 OK with the summary and
 * item list once ready").
 *
 * It is a read of its own, apart from the meeting's: the page shows the transcript
 * whatever this does, so a slow or failed summary never hides it (NFR-20, CLAUDE.md
 * §6, invariant 8).
 *
 * **When it asks again.** Only while `status` is "Processing". A summary that is
 * "Unavailable" and queued for its retry also answers 202, and is not polled: that
 * retry is hourly. The timer is set after each answer and cleared when the
 * component unmounts or the meeting changes, and a read in flight then is
 * aborted, so nothing asks for a meeting the page has left.
 *
 * **When a check fails.** The page stops asking and holds the failure in
 * `checkError`, with the state it last had, so the panel can say that it could not
 * check rather than leave "being generated" on screen with nothing behind it.
 * `reload()` reads again and, if the run is still in flight, resumes. A 404 on a
 * check is the first read's 404: the meeting is gone or now out of scope, and the
 * state goes with it.
 *
 * **A check never overwrites a write it did not see.** `apply` and `updateItems`
 * are how a POST's answer and an action-item write reach the state; each is
 * counted, and a check that was in flight across one is discarded and asked again,
 * because its list may be older than the one on screen.
 *
 * @param {string} meetingId
 * @returns {{
 *   loading: boolean,
 *   error: ApiError|null,
 *   checkError: ApiError|null,
 *   tooShort: boolean,
 *   state: object|null,
 *   reload: () => void,
 *   apply: (answer: {status: number, state: object|null}) => void,
 *   updateItems: (updater: (items: object[]) => object[]) => void,
 * }}
 */
export default function useMeetingSummary(meetingId) {
  const [resource, setResource] = useState(() => unread(meetingId))
  // Bumped by reload(): a retry, or a panel a write has shown to be out of date.
  const [reloadKey, setReloadKey] = useState(0)
  // Bumped by each check that answered, so the next one is scheduled.
  const [checks, setChecks] = useState(0)
  // How many writes this page has applied; see "A check never overwrites" above.
  const writes = useRef(0)

  // Another meeting: what was read is not its state. Reset while rendering, so no
  // commit shows one meeting's summary under another's title.
  if (resource.meetingId !== meetingId) setResource(unread(meetingId))

  useEffect(() => {
    const controller = new AbortController()
    const { signal } = controller

    async function read() {
      let next
      try {
        next = settled(meetingId, await fetchMeetingSummary(meetingId, { signal }))
      } catch (caught) {
        if (caught?.name === 'AbortError') return
        next = { ...unread(meetingId), loading: false, error: failureOf(caught) }
      }
      if (signal.aborted) return
      setResource(next)
    }

    read()
    return () => controller.abort()
  }, [meetingId, reloadKey])

  const processing =
    resource.meetingId === meetingId &&
    resource.state?.status === SUMMARY_STATUS.processing &&
    resource.checkError === null

  useEffect(() => {
    if (!processing) return undefined
    const controller = new AbortController()
    const { signal } = controller

    async function check() {
      const writesBefore = writes.current
      let answer
      try {
        answer = await fetchMeetingSummary(meetingId, { signal })
      } catch (caught) {
        if (caught?.name === 'AbortError' || signal.aborted) return
        const failure = failureOf(caught)
        setResource((current) => {
          if (current.meetingId !== meetingId) return current
          // Gone, or now outside the caller's scope: the first read's answer.
          if (failure.status === 404) return { ...unread(meetingId), loading: false, error: failure }
          return { ...current, checkError: failure }
        })
        return
      }
      if (signal.aborted) return
      if (writes.current === writesBefore) {
        setResource((current) => (current.meetingId === meetingId ? settled(meetingId, answer) : current))
      }
      setChecks((count) => count + 1)
    }

    const timer = setTimeout(check, MEETING_SUMMARY_POLL_MS)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [meetingId, processing, checks])

  const reload = useCallback(() => {
    // What is on screen stays there while it is read again; "loading" is for
    // having nothing to show.
    setResource((current) => ({ ...current, loading: current.state === null, error: null, checkError: null }))
    setReloadKey((key) => key + 1)
  }, [])

  const apply = useCallback(
    (answer) => {
      writes.current += 1
      setResource(settled(meetingId, answer))
    },
    [meetingId],
  )

  const updateItems = useCallback((updater) => {
    writes.current += 1
    setResource((current) => {
      if (!current.state) return current
      const items = Array.isArray(current.state.action_items) ? current.state.action_items : []
      return { ...current, state: { ...current.state, action_items: updater(items) } }
    })
  }, [])

  return {
    loading: resource.loading,
    error: resource.error,
    checkError: resource.checkError,
    tooShort: resource.httpStatus === SUMMARY_TOO_SHORT_STATUS,
    state: resource.state,
    reload,
    apply,
    updateItems,
  }
}
