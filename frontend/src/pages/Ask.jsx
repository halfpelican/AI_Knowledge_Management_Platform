import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { ASK_IN_FLIGHT_CODE, askQuestion } from '../api/ask.js'
import { ApiError, NETWORK_ERROR_STATUS, messageForStatus } from '../api/client.js'
import { createConversation, fetchConversation, listConversations } from '../api/conversations.js'
import { TurnBody } from '../components/Answer.jsx'
import Button from '../components/Button.jsx'
import Notice from '../components/Notice.jsx'
import TextAreaInput from '../components/TextAreaInput.jsx'
import { QUESTION_MAXIMUM_LENGTH, TEXT } from '../constants.js'
import useApiResource from '../hooks/useApiResource.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { formatDate } from '../utils/dates.js'
import { extractFieldErrors } from '../utils/fieldErrors.js'
import { whenToRetry } from '../utils/retryAfter.js'
import { addressForThread, questionInSearch, searchForThread, threadInSearch } from '../utils/threadAddress.js'
import {
  threadAfterNewTopic,
  threadForNextQuestion,
  unusedThreadAfterFailure,
  unusedThreadAfterTurn,
} from '../utils/threads.js'
import { liveTurnFrom, savedTurnFrom } from '../utils/turns.js'
import { questionError } from '../utils/validation.js'
import './Repository.css'
import './Ask.css'

/** The API's own field names, so a 400's `details` lands under the right control. */
const FIELDS = ['question', 'conversation_id']

/**
 * FR-12's question-and-answer path and FR-13's conversational assistant, on one
 * screen because they are one endpoint: `POST /api/ask` is the answer and, when
 * the body names a thread, the turn of it.
 *
 * What each requirement contributes:
 *
 * - FR-12: the question field, the answer with numbered inline citations, each
 *   citation expanding to its source passage, the Sources panel listing every item
 *   consulted with its date, the no-answer state, and the partial matches beside
 *   it — which are a field of the reply (`partial_matches`), not something this
 *   screen derives: one request per question, and no second one. The rendering of
 *   all of that lives in src/components/Answer.jsx.
 * - FR-13: the thread that retains its turns so a follow-up need not restate the
 *   subject, the list of previous conversations with a way to reopen one, and the
 *   control that clears the active thread to begin a new topic.
 *
 * **Clearing the thread starts a new conversation; it deletes nothing.** There is
 * no delete route and no rename route in the contract, and no control for either
 * here. The old thread stays in the list and its `QueryLog` rows stay as FR-19
 * evidence (D-12).
 *
 * **The active thread lives in the address, and only there** (D-77, which closes
 * D-61's gap 3). `/ask?c=<id>` names it and `/ask` names none, so following a
 * citation's source link in the same tab and pressing Back returns to the
 * conversation that was left. The thread the address names is read from the
 * server on mount and whenever the address changes, never restored from anything
 * the browser kept, and only when it is not already the thread on screen, so the
 * screen's own writes never re-read over a live turn. Opening a thread from the
 * list and "Start a new topic" add a history entry; the thread a first question
 * creates replaces the entry it was asked from, before the answer arrives; an
 * address that answers 404 is replaced with `/ask`; and a reply for a thread the
 * address no longer names is not shown, because the server has it and the next
 * read of that thread shows it. The tab title stays "Ask", never a thread's title.
 * What D-77 left to the implementation — where focus goes, what is disabled while a
 * thread is read, what a dropped reply still does — is a dated note on D-77.
 *
 * **A thread is created lazily, on the first question, and reused until a question
 * has actually landed in it.** FR-13's interface never asks the user to name a
 * topic before typing, so `POST /api/conversations` is sent with no title: the
 * thread is created as "New conversation" and the first turn replaces that with
 * the question itself (D-43).
 *
 * **The claim this docstring used to make was false, and is not repeated.** It said
 * that creating the thread on the first ask rather than on the button press "keeps
 * the list free of empty threads nobody asked anything in". Creating it there is
 * *necessary* — `POST /api/ask` attaches a turn to a thread that already exists and
 * creates none of its own, so the id must exist before the question is sent or the
 * first turn is a one-off with `QueryLog.conversation` NULL that no thread can ever
 * hold, and the thread would reopen without its own first question. It is not
 * *sufficient*: the create succeeds and the ask can still fail — a 503, NFR-19's
 * own demonstration path, reachable whenever FLM drops; a 400 the client pre-check
 * missed; or one of D-79's 429s. Until D-80 that left a "New conversation" at the
 * top of the list, because `last_updated_at` is `auto_now` on create, and FR-13
 * specifies no Delete.
 *
 * What is true now:
 *
 * - **The list leaves an empty thread out (D-80, which closes D-58).** The server
 *   lists only threads with at least one turn, answered or not, so a thread created
 *   for a first question that failed is not in the list, even while the address
 *   names it and it is on screen. Once its first turn lands, the list is re-read and
 *   shows it, marked as current. This screen filters nothing itself: the list is
 *   exactly what the server sent.
 * - A thread that has had no successful turn is **reused, not abandoned**. The
 *   question stays in the field after a 503 or a 429, so the retry lands in the same
 *   thread and names it. "Start a new topic" keeps it too: nothing has been asked in
 *   it, so it already *is* a new topic and clearing it would only mean a second
 *   empty row on the next ask. One failed first question therefore costs at most one
 *   thread, however many times it is retried or the topic is cleared. That still
 *   matters under D-80: the row exists, and each create spends the per-user create
 *   budget (D-79).
 * - The list is **not** re-read after a failed ask. Nothing the user asked for
 *   happened, so there is nothing new for it to show.
 * - **The residue, stated rather than implied.** One created thread can still
 *   outlive the session that made it: its first ask failed and the user left
 *   without asking again. It is no longer seen in the list (D-80); it stays a row,
 *   which nothing deletes (D-80 rule 3), and its address goes back into it (D-77).
 *
 * **Six states that are not each other**, and the screen keeps them apart because
 * a user who confuses them retries the wrong thing. The second was added at Stage 4
 * item 1c, by separating it from the first, and the last two by D-79:
 *
 * - *No answer* (200, `answered: false`) — the corpus has nothing to answer from.
 *   A designed outcome, stated plainly, with no speculative answer and no empty
 *   answer frame pretending to be one. A turn the reader's current role may no
 *   longer see renders as this state too, and deliberately cannot be told from it:
 *   see `src/utils/turns.js`, which holds that argument and the one below.
 * - *Sources no longer on record* (a stored turn carrying `provenance_removed`) —
 *   the turn was answered and none of its citations still points at a chunk: a
 *   reprocess, a re-index or FR-15's deletion removed them, and since D-67 each
 *   survives only as a record whose chunk is NULL. No statements, and not the no-answer
 *   copy either, because "this cannot be answered from the knowledge base" is a
 *   claim about the corpus, and this state makes none: a re-index or a successful
 *   reprocess leaves the material indexed, while a failed reprocess and FR-15's
 *   deletion leave none of it. See the paths enumerated at
 *   `apps/core/constants.py`'s PROVENANCE_REMOVED_MESSAGE. The earlier wording here
 *   asserted the material was "still indexed", which is the claim
 *   `docs/api-contract.md` retired on 27 September and this file kept.
 * - *AI unavailable* (503) — the question could not be asked at all. NFR-19's
 *   notice, shown the moment the API answers, and the question is kept in the
 *   field because no `QueryLog` row was written and it can be asked again.
 * - *Rejected* (400) — the question itself was not acceptable, shown under the
 *   field.
 * - *Still answering the previous question* (429, `code` "ask_in_flight") — the
 *   server answers one question per user at a time. This screen sends one at a
 *   time and keeps Ask disabled while it waits, so this is reached from another
 *   tab, or in this one after the screen was left and come back to while an ask
 *   was pending — a citation followed, then Back (D-77) — or reloaded. An
 *   information notice and not NFR-19's: nothing is unavailable. It names no time,
 *   because the reply carries none.
 * - *Too many questions* (429, any other body) — past the per-user ask rate, or the
 *   create rate on a first question (D-79, D-80). It says when the user can ask
 *   again, from `Retry-After`.
 *
 *   The two 429s are told apart by `code` alone, never by `detail`. In both the
 *   question stays in the field, nothing was recorded, and no turn is added.
 *
 * **Invariant 6 holds by construction.** No reply carries a rejected statement, a
 * rejection count or a no-answer reason, so there is nothing on this screen to
 * render greyed out, behind a disclosure or in a withheld panel, and nothing here
 * invents an affordance for one.
 */
export default function Ask() {
  // Static, and never the thread's title (D-77): every thread visited stays in the
  // Back button's history list, where anyone at the machine can read it.
  useDocumentTitle('Ask')
  const location = useLocation()
  const navigate = useNavigate()
  // The active thread as the address names it, and the only record of it (D-77).
  // Null when the address names none.
  const addressThread = threadInSearch(location.search)
  // Arriving from the search screen's "Ask this as a question" link. Prefilled
  // and never submitted for the user: the question is theirs to send.
  const [question, setQuestion] = useState(() => questionInSearch(location.search))
  const [touched, setTouched] = useState(false)
  const [fieldError, setFieldError] = useState(null)
  const [failure, setFailure] = useState(null)
  const [asking, setAsking] = useState(false)
  const [acknowledgement, setAcknowledgement] = useState('')

  // The thread on screen: the one whose turns are shown and the one the next
  // question is a turn of. It follows the address, one read behind it. Null means
  // the next question starts a new conversation.
  const [shownThreadId, setShownThreadId] = useState(null)
  const [turns, setTurns] = useState([])
  // The thread the address names is being read. True from the first render when
  // the address names one, so nothing is offered for a thread not yet on screen.
  const [opening, setOpening] = useState(() => addressThread !== null)
  // Bumped to read the thread the address names again, after its read failed.
  const [readAttempt, setReadAttempt] = useState(0)

  const conversations = useApiResource(listConversations)
  const reloadConversations = conversations.reload
  const turnCounter = useRef(0)
  const lastTurnRef = useRef(null)
  const questionRef = useRef(null)
  /**
   * A one-shot instruction to the focus effect below, as `{thread}`, or null. A ref
   * rather than state: nothing renders from it, so it must not cause a render of
   * its own.
   *
   * It carries the thread it was set for and is spent only on that thread's turns
   * (D-77, rule a), the pattern src/pages/DocumentRepository.jsx uses for the same
   * reason: a read for another thread that lands first must not take it, and an
   * address naming another thread drops it, so a later Back or Forward to the
   * thread it named cannot move focus. Only a click in the list and an arriving
   * answer set it. A read the address asks for on its own — mount, Back, Forward,
   * a link — moves no focus, as no page load does.
   */
  const pendingTurnFocus = useRef(null)
  /**
   * The id of a thread this screen created that no turn has landed in yet, or
   * null. Also a ref rather than state: nothing renders from it, and it has to be
   * readable inside the async submit that set it a few lines earlier, which a
   * state value batched for the next render would not be.
   *
   * It exists because `POST /api/conversations` is not undoable — FR-13 has no
   * Delete and no delete route was built — so the only way not to leave a second
   * empty thread behind is to go back into the first one.
   */
  const unusedThreadRef = useRef(null)
  /**
   * The thread on screen, the thread the address names, and whether the screen is
   * still mounted, as refs: a submit reads them after an await, where state would
   * be the value its own render closed over (D-77, rules 4 and d).
   *
   * The address is the one last committed, except that the screen's own writes
   * are recorded the moment they are made (`writeAddress`). The router commits a
   * navigation as a transition, and a reply can land before it does. A Back or
   * Forward is learned only when it commits, which leaves a window of one render
   * in which a reply is judged against the address before it.
   */
  const shownThreadRef = useRef(null)
  const addressRef = useRef({ thread: addressThread, search: location.search })
  const mountedRef = useRef(false)

  useLayoutEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  // Keyed on the location object, so a render that does not navigate leaves a
  // write recorded by `writeAddress` in place until that navigation commits.
  useLayoutEffect(() => {
    addressRef.current = { thread: threadInSearch(location.search), search: location.search }
  }, [location])

  /** Puts `threadId` on screen, in the ref that async work compares against as well. */
  const showThread = useCallback((threadId) => {
    shownThreadRef.current = threadId
    setShownThreadId(threadId)
  }, [])

  /** Writes `threadId` to the address: a new history entry unless `replace` is asked for. */
  const writeAddress = useCallback(
    (threadId, { replace = false } = {}) => {
      navigate(addressForThread(threadId), { replace })
      addressRef.current = { thread: threadId, search: searchForThread(threadId) }
    },
    [navigate],
  )

  /**
   * A 404 for the thread on screen or the one the address names. It is the answer
   * both for a thread that is not there and for one that is not this caller's, and
   * the screen distinguishes neither (CLAUDE.md §6, invariant 1). The thread is
   * cleared so the next question starts a new one, the list is re-read, and the
   * address is replaced with `/ask` so Back never returns to it (D-77, rule 5).
   *
   * The thread on screen is cleared before the address is, so the read effect finds
   * nothing left to clear when the address names none, and the notice stays.
   */
  const forgetMissingThread = useCallback(() => {
    showThread(null)
    setTurns([])
    reloadConversations()
    setFailure({ variant: 'error', title: TEXT.conversationLoadFailed, text: TEXT.conversationNotFound })
    if (addressRef.current.search !== searchForThread(null)) writeAddress(null, { replace: true })
  }, [showThread, reloadConversations, writeAddress])

  /**
   * Where the visible acknowledgement is completed for a keyboard and screen
   * reader user: the reply is scrolled to and focused, so the next tab stop is the
   * answer's own citations rather than something above the fold. A thread opened
   * from the list is focused the same way, at its last turn.
   *
   * It runs after the turn it focuses has rendered, which is why `turns` is the
   * dependency, and only for the thread the focus was asked for.
   */
  useEffect(() => {
    const pending = pendingTurnFocus.current
    if (!pending || pending.thread !== shownThreadRef.current) return
    pendingTurnFocus.current = null
    const node = lastTurnRef.current
    if (!node) return
    node.focus()
    // No smooth scrolling: an instant jump respects a reduced-motion preference
    // without needing to ask about one.
    node.scrollIntoView({ block: 'nearest' })
  }, [turns])

  /**
   * FR-13's "retaining the thread" (D-77, rule 1): the thread the address names is
   * read from the server on mount and whenever the address changes — Back,
   * Forward, a link, the list — and its turns always come from that read, never
   * from anything the browser kept. The read is re-scoped on the server (D-48), so
   * a source deleted since is not shown again.
   */
  useEffect(() => {
    // A focus asked for by a click belongs to the thread it was asked for.
    if (pendingTurnFocus.current && pendingTurnFocus.current.thread !== addressThread) {
      pendingTurnFocus.current = null
    }

    // Only a thread that is not already on screen is read. The screen puts a thread
    // on screen before it writes it to the address, so its own writes — a created
    // thread, a new topic — never re-read over a live turn. This is also Back to
    // the thread a read still in flight was leaving: that read is cancelled below.
    if (addressThread === shownThreadRef.current) {
      setOpening(false)
      return undefined
    }

    // The address names no thread, through the navigation's Ask link or Back to
    // `/ask`: the screen shows an empty one. The draft in the field is kept.
    if (addressThread === null) {
      // The address is the external system this effect keeps the screen in step
      // with (D-77), so clearing the screen when it names no thread is that
      // synchronisation rather than state that could be derived in render.
      // oxlint-disable-next-line react/set-state-in-effect
      showThread(null)
      setTurns([])
      setFailure(null)
      setFieldError(null)
      setTouched(false)
      setAcknowledgement('')
      setOpening(false)
      return undefined
    }

    // Cancelled when the address moves on or the screen unmounts, so a slow read for
    // one thread cannot land over the thread the address has gone back to.
    let cancelled = false
    const controller = new AbortController()
    setOpening(true)
    setFailure(null)
    setAcknowledgement('')
    fetchConversation(addressThread, { signal: controller.signal }).then(
      (thread) => {
        if (cancelled) return
        // src/utils/turns.js holds the mapping and the three states a stored turn
        // can be in, including the one where the answer's citations no longer
        // point at anything. A stored turn carries its consulted sources (D-78),
        // so it renders by the same branch as a live one.
        const saved = (thread?.turns ?? []).map((turn, index) =>
          savedTurnFrom(turn, { key: `saved-${addressThread}-${index}` }),
        )
        // The id the address names rather than the one the body carries, so the
        // address and the screen agree character for character.
        showThread(addressThread)
        setTurns(saved)
        turnCounter.current = 0
        setOpening(false)
      },
      (error) => {
        if (cancelled) return
        setOpening(false)
        if (error instanceof ApiError && error.status === 404) {
          forgetMissingThread()
          return
        }
        // The screen keeps what it was showing, under a notice. Choosing the
        // thread again from the list reads it again.
        setFailure({
          variant: 'error',
          title: TEXT.conversationLoadFailed,
          text: error instanceof ApiError ? error.message : messageForStatus(NETWORK_ERROR_STATUS),
        })
      },
    )
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [addressThread, readAttempt, showThread, forgetMissingThread])

  const refusal = questionError(question)
  const shownFieldError = fieldError ?? (touched && refusal ? refusal : null)

  function appendTurn(turn) {
    turnCounter.current += 1
    const key = `turn-${turnCounter.current}`
    setTurns((current) => [...current, { ...turn, key }])
  }

  function handleFailure(error) {
    if (!(error instanceof ApiError)) {
      setFailure({ variant: 'error', title: TEXT.askRejected, text: TEXT.askRejected })
      return
    }
    if (error.status === 503) {
      // NFR-19. The 503 message is the client's fixed text; the second sentence is
      // the one the contract makes true — no QueryLog row was written, so asking
      // again is safe. The question stays in the field for exactly that reason.
      setFailure({ variant: 'unavailable', title: TEXT.askUnavailableTitle, text: `${error.message} ${TEXT.askNotRecorded}` })
      return
    }
    if (error.status === 429) {
      // D-79's two 429s, told apart by `code` alone; `detail` is never read. Neither
      // wrote a `QueryLog` row, so the question stays in the field and no turn is
      // added. The in-flight one is an information notice, not NFR-19's: nothing is
      // unavailable, and it names no time because the reply carries none. Every
      // other 429 here is a rate limit — the ask's, or the create's before a first
      // question (D-80) — and says when, from `Retry-After`.
      setFailure(
        error.code === ASK_IN_FLIGHT_CODE
          ? { variant: 'info', title: TEXT.askInFlightTitle, text: TEXT.askInFlight }
          : {
              variant: 'error',
              title: TEXT.askRateLimitedTitle,
              text: TEXT.askRateLimited(whenToRetry(error.retryAfter)),
            },
      )
      return
    }
    if (error.status === 404) {
      // The thread asked in is not there, or is not this caller's: handled as a read
      // of it would be, address included.
      forgetMissingThread()
      return
    }
    const extracted = extractFieldErrors(error, FIELDS)
    if (extracted.fieldErrors.question) {
      setFieldError(extracted.fieldErrors.question)
      return
    }
    setFailure({
      variant: 'error',
      title: TEXT.askRejected,
      text: extracted.formError ?? extracted.fieldErrors.conversation_id ?? error.message,
    })
  }

  /**
   * True while the screen is mounted, the address names `address` and the screen
   * shows `shown`. Everything a submit does after an await is conditional on it
   * (D-77, rules 4 and d): react-router's navigate still works after the screen has
   * unmounted, so without the first condition a citation followed while a question
   * was in flight could be undone by a navigation back when the reply landed.
   */
  function isStill(address, shown) {
    return mountedRef.current && addressRef.current.thread === address && shownThreadRef.current === shown
  }

  async function handleSubmit(event) {
    event.preventDefault()
    // One question at a time, and none into a thread not yet on screen. The submit
    // button is disabled for both; this is the same rule for a submit that gets
    // here anyway.
    if (asking || opening) return
    setTouched(true)
    if (refusal) {
      setFieldError(refusal)
      questionRef.current?.focus()
      return
    }
    setFieldError(null)
    setFailure(null)
    setAcknowledgement('')
    setAsking(true)

    const asked = question
    // Where the question was asked from, for the check after the first await.
    const askedFromAddress = addressRef.current.thread
    const askedFromThread = shownThreadRef.current
    // The thread the question is a turn of, once it is known.
    let threadId = null
    let threadKnown = false
    try {
      // Lazily create the thread, and before the ask rather than after it: `POST
      // /api/ask` attaches a turn to a thread and creates none, so a question sent
      // without an id is a one-off that no thread can later adopt (D-43). A thread
      // already created for a question that failed is reused, so a retry after a
      // 503 goes back into it instead of leaving a second empty one beside it.
      // The rules themselves are in src/utils/threads.js, with the argument for
      // each one and nothing React in any of them, so they can be run.
      threadId = threadForNextQuestion(askedFromThread, unusedThreadRef.current)
      if (!threadId) {
        const created = await createConversation()
        threadId = created?.conversation_id ?? null
        // Recorded before the ask, so it is still known if the ask throws.
        unusedThreadRef.current = threadId
      }
      threadKnown = true

      // The address names the thread the question is asked in before the answer
      // arrives (D-77, rule 3): a created thread, or an empty one reused. Replaced
      // rather than pushed, so Back from it never lands on an empty `/ask`, and
      // written as `?c=` alone, which drops a `q` the search screen's link brought.
      // Only while nothing has moved since the submit began: if the address has, the
      // question is still sent and its reply is dropped below.
      if (isStill(askedFromAddress, askedFromThread)) {
        if (threadId !== shownThreadRef.current) showThread(threadId)
        if (threadId && addressRef.current.search !== searchForThread(threadId)) {
          writeAddress(threadId, { replace: true })
        }
      }

      const reply = await askQuestion({ question: asked, conversationId: threadId ?? undefined })
      // The turn landed — answered or not, a `QueryLog` row exists and the thread
      // has been named from the question — so it is no longer an empty one to
      // return to.
      unusedThreadRef.current = unusedThreadAfterTurn(unusedThreadRef.current, threadId)
      // The thread's title and its last-updated time changed on the server, and a
      // first turn is what puts a thread in the list at all (D-80), so the list is
      // re-read rather than guessed at, whether or not the reply is shown.
      reloadConversations()

      // D-77, rule 4: a reply for a thread the address no longer names is dropped.
      // Back and Forward cannot be disabled while asking, and an answer can take
      // minutes (D-49). The server has the turn, and the next read of that thread
      // shows it. Nothing else changes: no turn, no acknowledgement, no focus, no
      // address, and the question stays in the field.
      if (!isStill(threadId, threadId)) return

      // The mapping lives in src/utils/turns.js, with the live turn and the stored
      // turn beside each other: they are rendered by one branch below, so the two
      // shapes have to carry the same keys and that is easiest to keep true in one
      // place. A live turn can never be in the provenance-removed state — its
      // citations were written in the same transaction as the answer.
      const turn = liveTurnFrom(reply, { question: asked })
      const { statements, sources, answered } = turn
      appendTurn(turn)
      setQuestion('')
      setTouched(false)
      setAcknowledgement(answered ? TEXT.answerReady(statements.length, sources.length) : TEXT.noAnswerReady)
      pendingTurnFocus.current = { thread: threadId }
    } catch (error) {
      // Kept for a 503, a 400 and either 429 — no turn was written, so the thread is
      // still empty and still where the next attempt belongs — and dropped for a
      // 404. A 429 on the create made no thread, and what is kept is the null there
      // was before it, so the next attempt creates again. src/utils/threads.js
      // carries the reasoning. Applied whether or not the failure is shown, because
      // it describes the thread, not the screen.
      unusedThreadRef.current = unusedThreadAfterFailure(
        unusedThreadRef.current,
        error instanceof ApiError ? error.status : null,
      )
      // A failure for a thread the address no longer names is dropped as its reply
      // would be: a 404 for one thread must not clear another, or rewrite the
      // address the reader has moved to. A create that failed has no thread, and is
      // judged against where the question was asked from.
      const shown = threadKnown ? isStill(threadId, threadId) : isStill(askedFromAddress, askedFromThread)
      if (shown) handleFailure(error)
    } finally {
      setAsking(false)
    }
  }

  /**
   * FR-13: "the active thread can be cleared to begin a new topic."
   *
   * A thread with no turns in it is not cleared, because there is nothing in it to
   * clear: it already is a new topic, and starting another would leave it behind
   * empty and permanent. So this drops a thread that has turns and keeps one that
   * does not.
   *
   * The thread it leaves on screen is written to the address as a new history
   * entry, so Back returns to the thread that was cleared (D-77, rule 2): `/ask`, or
   * `/ask?c=<id>` when an empty thread is reused. When the screen already shows no
   * turns it writes nothing, so pressing it again adds no entry. Either way the
   * acknowledgement is given and focus goes to the field.
   */
  function handleNewTopic() {
    setFailure(null)
    setFieldError(null)
    setTouched(false)
    setAcknowledgement(TEXT.threadNew)
    questionRef.current?.focus()

    if (turns.length === 0 && !opening) return
    const next = threadAfterNewTopic(unusedThreadRef.current)
    // On screen before it is in the address, so the read effect has nothing to read.
    showThread(next)
    setTurns([])
    if (addressRef.current.search !== searchForThread(next)) writeAddress(next)
  }

  /**
   * FR-13: "previous conversations are listed and can be reopened."
   *
   * Reopening writes the thread to the address as a new history entry, and the read
   * effect above does the reading (D-77, rule 2). Focus goes to the thread's last
   * turn once that thread's read lands.
   */
  function handleOpenConversation(id) {
    if (id === shownThreadRef.current) {
      // Already on screen: no history entry and no read. Focus goes where the read
      // would have put it.
      const node = lastTurnRef.current
      if (node) {
        node.focus()
        node.scrollIntoView({ block: 'nearest' })
      }
      return
    }
    pendingTurnFocus.current = { thread: id }
    if (id === addressRef.current.thread) {
      // The address already names it and the screen does not show it, because its
      // read failed. Read it again, without a second entry for the same address.
      setReadAttempt((attempt) => attempt + 1)
      return
    }
    writeAddress(id)
  }

  const threads = conversations.data ?? []

  let conversationList
  if (conversations.loading) {
    conversationList = <p role="status">{TEXT.loadingConversations}</p>
  } else if (conversations.error) {
    conversationList = (
      <>
        <Notice variant="error" title={TEXT.conversationsLoadFailed}>
          {conversations.error.message}
        </Notice>
        <Button variant="secondary" onClick={conversations.reload}>
          Try again
        </Button>
      </>
    )
  } else if (threads.length === 0) {
    conversationList = <p className="ask-threads__empty">{TEXT.noConversations}</p>
  } else {
    conversationList = (
      <ul className="ask-threads__list">
        {threads.map((thread) => {
          const current = thread.conversation_id === shownThreadId
          return (
            <li key={thread.conversation_id}>
              <button
                type="button"
                className="ask-threads__item"
                // Marks which thread is on screen for assistive technology as well
                // as visually, so the current one is not identified by shading alone.
                aria-current={current ? 'true' : undefined}
                aria-label={TEXT.conversationOpen(thread.title)}
                disabled={opening || asking}
                onClick={() => handleOpenConversation(thread.conversation_id)}
              >
                <span className="ask-threads__title">{thread.title}</span>
                <span className="ask-threads__date">
                  <time dateTime={thread.last_updated_at}>{formatDate(thread.last_updated_at)}</time>
                  {current ? ` · ${TEXT.conversationCurrent}` : ''}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    )
  }

  return (
    <div className="repository-page ask-page">
      <h1>{TEXT.askHeading}</h1>

      <div className="ask-layout">
        <div className="ask-main">
          <section aria-labelledby="ask-form-heading" className="ask-form">
            {/* The page heading already says what this is; the section still needs a
                name for the landmark, so the heading is present and not repeated
                visually. */}
            <h2 id="ask-form-heading" className="visually-hidden">
              Ask a question
            </h2>
            {failure ? (
              <Notice variant={failure.variant} title={failure.title}>
                {failure.text}
              </Notice>
            ) : null}
            <form onSubmit={handleSubmit} noValidate>
              <TextAreaInput
                ref={questionRef}
                id="ask-question"
                label={TEXT.askFieldLabel}
                hint={TEXT.askHint}
                name="question"
                rows={3}
                value={question}
                error={shownFieldError}
                disabled={asking}
                maxLength={QUESTION_MAXIMUM_LENGTH}
                onBlur={() => setTouched(true)}
                onChange={(event) => {
                  setQuestion(event.target.value)
                  if (fieldError) setFieldError(null)
                }}
              />
              <p className="ask-form__count">
                {question.length} of {QUESTION_MAXIMUM_LENGTH} characters
              </p>
              <div className="repository-page__actions">
                {/* Disabled until the question is askable — FR-01's pattern, applied
                    to FR-12's bounds. The server enforces them regardless. Both are
                    disabled while a thread is read, as the list is, so nothing is
                    asked into or cleared from a thread not yet on screen. */}
                <Button type="submit" loading={asking} disabled={asking || opening || refusal !== null}>
                  {asking ? TEXT.asking : TEXT.askSubmit}
                </Button>
                <Button variant="secondary" disabled={asking || opening} onClick={handleNewTopic}>
                  {TEXT.newTopic}
                </Button>
              </div>
              <p className="ask-form__hint">{TEXT.newTopicHint}</p>
              {/* Visible and live at once. Usability finding 1: an acknowledgement
                  only assistive technology receives is half a signal, so the words
                  that are announced are the words on the screen. */}
              <p className="ask-form__status" role="status" aria-live="polite">
                {asking ? TEXT.asking : acknowledgement}
              </p>
            </form>
          </section>

          <section aria-labelledby="ask-thread-heading" className="ask-thread">
            <h2 id="ask-thread-heading">Conversation</h2>
            {opening ? <p role="status">{TEXT.loadingConversation}</p> : null}
            {/* No note qualifies a reopened thread: its turns carry their passages
                and their Sources panels as live turns do (D-78). */}
            {turns.length === 0 && !opening ? <p className="ask-thread__empty">{TEXT.threadEmpty}</p> : null}

            {turns.map((turn, index) => {
              const questionId = `${turn.key}-question`
              return (
                <article
                  key={turn.key}
                  className="ask-turn"
                  // Labelled by the question, so focusing the turn announces which
                  // question this answer belongs to.
                  aria-labelledby={questionId}
                  tabIndex={-1}
                  ref={index === turns.length - 1 ? lastTurnRef : null}
                >
                  <p className="ask-turn__question" id={questionId}>
                    <span className="ask-turn__label">{TEXT.askQuestionLabel}: </span>
                    {turn.question}
                    {turn.askedAt ? (
                      <span className="ask-turn__date">
                        {' '}
                        <time dateTime={turn.askedAt}>{formatDate(turn.askedAt)}</time>
                      </span>
                    ) : null}
                  </p>

                  {/* The three states a turn can be in, and which of them may be
                      told apart from which, live in src/components/Answer.jsx
                      beside the answer presentation itself. */}
                  <TurnBody turn={turn} />
                </article>
              )
            })}
          </section>
        </div>

        {/* After the main column in the DOM, so the tab order reaches the question
            field before the list of old ones. */}
        <aside aria-labelledby="ask-threads-heading" className="ask-threads">
          <h2 id="ask-threads-heading">{TEXT.conversationsHeading}</h2>
          {conversationList}
        </aside>
      </div>
    </div>
  )
}
