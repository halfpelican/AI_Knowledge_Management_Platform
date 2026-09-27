import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { askQuestion } from '../api/ask.js'
import { ApiError } from '../api/client.js'
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
 * **A thread is created lazily, on the first question.** FR-13's interface never
 * asks the user to name a topic before typing, so `POST /api/conversations` is sent
 * with no title: the thread is created as "New conversation" and the first turn
 * replaces that with the question itself (D-43). Creating it on the first ask
 * rather than on the button press is what keeps the list free of empty threads
 * nobody asked anything in.
 *
 * **Four states that are not each other**, and the screen keeps them apart
 * because a user who confuses them retries the wrong thing. The second was added
 * at Stage 4 item 1c, by separating it from the first:
 *
 * - *No answer* (200, `answered: false`) — the corpus has nothing to answer from.
 *   A designed outcome, stated plainly, with no speculative answer and no empty
 *   answer frame pretending to be one. A turn the reader's current role may no
 *   longer see renders as this state too, and deliberately cannot be told from it:
 *   see `src/utils/turns.js`, which holds that argument and the one below.
 * - *Sources no longer on record* (a stored turn carrying `provenance_removed`) —
 *   the turn was answered and the record of what it was drawn from has been
 *   destroyed by a reprocess or a re-index. No statements, and not the no-answer
 *   copy either, because "this cannot be answered from the knowledge base" is
 *   false of a question whose material is still indexed.
 * - *AI unavailable* (503) — the question could not be asked at all. NFR-19's
 *   notice, shown the moment the API answers, and the question is kept in the
 *   field because no `QueryLog` row was written and it can be asked again.
 * - *Rejected* (400) — the question itself was not acceptable, shown under the
 *   field.
 *
 * **Invariant 6 holds by construction.** No reply carries a rejected statement, a
 * rejection count or a no-answer reason, so there is nothing on this screen to
 * render greyed out, behind a disclosure or in a withheld panel, and nothing here
 * invents an affordance for one.
 */
export default function Ask() {
  useDocumentTitle('Ask')
  const [params] = useSearchParams()
  // Arriving from the search screen's "Ask this as a question" link. Prefilled
  // and never submitted for the user: the question is theirs to send.
  const [question, setQuestion] = useState(params.get('q') ?? '')
  const [touched, setTouched] = useState(false)
  const [fieldError, setFieldError] = useState(null)
  const [failure, setFailure] = useState(null)
  const [asking, setAsking] = useState(false)
  const [acknowledgement, setAcknowledgement] = useState('')

  // The active thread. Null means the next question starts a new conversation.
  const [conversationId, setConversationId] = useState(null)
  const [turns, setTurns] = useState([])
  const [reopened, setReopened] = useState(false)
  const [opening, setOpening] = useState(false)

  const conversations = useApiResource(listConversations)
  const turnCounter = useRef(0)
  const lastTurnRef = useRef(null)
  const questionRef = useRef(null)
  // A ref rather than state: it is a one-shot instruction to the effect below and
  // nothing renders from it, so it must not cause a render of its own.
  const pendingTurnFocus = useRef(false)

  /**
   * Where the visible acknowledgement is completed for a keyboard and screen
   * reader user: the reply is scrolled to and focused, so the next tab stop is the
   * answer's own citations rather than something above the fold.
   *
   * It runs after the turn it focuses has rendered, which is why `turns` is the
   * dependency.
   */
  useEffect(() => {
    if (!pendingTurnFocus.current) return
    pendingTurnFocus.current = false
    const node = lastTurnRef.current
    if (!node) return
    node.focus()
    // No smooth scrolling: an instant jump respects a reduced-motion preference
    // without needing to ask about one.
    node.scrollIntoView({ block: 'nearest' })
  }, [turns])

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
    if (error.status === 404) {
      // The thread is not there, or is not this caller's — one answer for both, and
      // the screen distinguishes neither (CLAUDE.md §6, invariant 1). The thread is
      // cleared so the next question starts a new one.
      setConversationId(null)
      setTurns([])
      setReopened(false)
      conversations.reload()
      setFailure({ variant: 'error', title: TEXT.conversationLoadFailed, text: TEXT.conversationNotFound })
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

  async function handleSubmit(event) {
    event.preventDefault()
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
    try {
      // Lazily create the thread, so a follow-up has something to be a turn of
      // (FR-13) and an untouched "New topic" leaves nothing behind (D-43).
      let threadId = conversationId
      if (!threadId) {
        const created = await createConversation()
        threadId = created?.conversation_id ?? null
        if (threadId) setConversationId(threadId)
      }

      const reply = await askQuestion({ question: asked, conversationId: threadId ?? undefined })
      if (reply?.conversation?.conversation_id) setConversationId(reply.conversation.conversation_id)

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
      pendingTurnFocus.current = true
      // The thread's title and its last-updated time changed on the server, so the
      // list is re-read rather than guessed at.
      conversations.reload()
    } catch (error) {
      handleFailure(error)
    } finally {
      setAsking(false)
    }
  }

  /** FR-13: "the active thread can be cleared to begin a new topic." */
  function handleNewTopic() {
    setConversationId(null)
    setTurns([])
    setReopened(false)
    setFailure(null)
    setFieldError(null)
    setTouched(false)
    setAcknowledgement(TEXT.threadNew)
    questionRef.current?.focus()
  }

  /** FR-13: "previous conversations are listed and can be reopened." */
  async function handleOpenConversation(id) {
    setOpening(true)
    setFailure(null)
    setAcknowledgement('')
    try {
      const thread = await fetchConversation(id)
      // src/utils/turns.js holds the mapping and the three states a stored turn can
      // be in, including the one where the answer's citation records no longer exist.
      const saved = (thread?.turns ?? []).map((turn, index) =>
        savedTurnFrom(turn, { key: `saved-${id}-${index}` }),
      )
      setConversationId(thread?.conversation_id ?? id)
      setTurns(saved)
      setReopened(true)
      turnCounter.current = 0
      if (saved.length > 0) pendingTurnFocus.current = true
    } catch (error) {
      handleFailure(error)
    } finally {
      setOpening(false)
    }
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
          const current = thread.conversation_id === conversationId
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
                    to FR-12's bounds. The server enforces them regardless. */}
                <Button type="submit" loading={asking} disabled={asking || refusal !== null}>
                  {asking ? TEXT.asking : TEXT.askSubmit}
                </Button>
                <Button variant="secondary" disabled={asking} onClick={handleNewTopic}>
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
            {/* Shown only while a turn on screen actually came back from the server
                without its passages. A live turn asked after reopening has them, so
                the note disappears once every turn present can expand. */}
            {reopened && turns.some((turn) => !turn.expandable) ? (
              <p className="ask-thread__note">{TEXT.threadReopenedNote}</p>
            ) : null}
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
