export const APP_TITLE = 'Organisational Knowledge Platform'

/** Role names as the API returns them (FR-05). */
export const ROLES = {
  employee: 'Employee',
  administrator: 'Administrator',
}

/**
 * FR-02: "On success, user is redirected to a role-specific dashboard (e.g.,
 * Administrator -> Admin Console; Employee -> Knowledge Dashboard)."
 *
 * The dashboards themselves are FR-14 and arrive in Stage 5. These routes exist
 * now so the redirect is genuinely role-specific today; Stage 5 replaces what they
 * render, not where they live. See docs/decisions.md D-25.
 */
export const DASHBOARD_PATHS = {
  [ROLES.administrator]: '/admin',
  [ROLES.employee]: '/dashboard',
}

/** Where a signed-in user belongs. Falls back to the shared placeholder. */
export function dashboardPathForRole(role) {
  return DASHBOARD_PATHS[role] ?? '/'
}

/**
 * The two document statuses a 201 can carry (docs/schema-v1.md §3, mirrored in
 * apps/core/constants.py DOCUMENT_STATUS_VALUES). The interface branches on
 * these two and displays whatever status the server actually recorded, so a
 * value added later shows up rather than being silently rendered as "Indexed".
 */
export const DOCUMENT_STATUS = {
  indexed: 'Indexed',
  partiallyIndexed: 'Partially indexed',
  // The three the 422 paths record. Each gets its own retry wording (D-32),
  // because only one of them describes a failure a retry can actually recover.
  extractionFailed: 'Extraction failed',
  insufficientContent: 'Insufficient content',
  indexingFailed: 'Indexing failed',
}

/**
 * FR-09: a transcript arrives "as a file or pasted text", never as both —
 * supplying both is a 400, because whichever the server picked, the other would
 * be discarded without the user knowing which. The form offers one or the other
 * and this is the choice.
 */
export const TRANSCRIPT_SOURCE = {
  text: 'text',
  file: 'file',
}

/**
 * FR-08 upload limits, mirroring apps/core/constants.py (ACCEPTED_EXTENSIONS,
 * MAX_UPLOAD_BYTES).
 *
 * Both are convenience checks only. The server decides what it accepts, and it
 * decides on evidence rather than on a claim: the format from the file's own
 * signature and the size from the bytes it actually received (CLAUDE.md §6,
 * invariant 4). A file that passes both checks here can still come back 415 or
 * 413, and the upload screen shows that answer against the file's row. Four
 * formats, not the six FR-08's upload area names: D-15.
 */
export const ACCEPTED_EXTENSIONS = ['.pdf', '.docx', '.xlsx', '.txt']
export const ACCEPTED_FORMATS_LABEL = 'PDF, DOCX, XLSX, TXT'
export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024
export const MAX_UPLOAD_LABEL = '50 MB'

/**
 * Said by the upload queue against a finished file and by the repository against
 * a "Partially indexed" row, so the one sentence has one copy.
 */
const PARTIALLY_INDEXED_DETAIL =
  'Some passages could not be indexed, so parts of this document will not appear in search results.'

/**
 * FR-12 search and question bounds, mirroring apps/core/constants.py
 * (MINIMUM_SEARCH_LENGTH, MINIMUM_QUESTION_LENGTH, MAXIMUM_QUESTION_LENGTH).
 *
 * FR-12 asks for the search minimum client-side in as many words — "queries
 * shorter than two characters are rejected client-side" — and the question bounds
 * are mirrored so the submit button can be disabled until the question is
 * askable, the pattern FR-01's password rules already use. Both remain the
 * server's decision: `GET /api/search` answers 400 `{"q": [...]}` and
 * `POST /api/ask` answers 400 `{"question": [...]}` regardless of what the
 * browser allowed (CLAUDE.md §6, invariant 4). Both question bounds are
 * inclusive.
 */
export const SEARCH_MINIMUM_LENGTH = 2
export const QUESTION_MINIMUM_LENGTH = 10
export const QUESTION_MAXIMUM_LENGTH = 500

/**
 * The two source types, from the fixed vocabulary the chunks, the search results
 * and the consulted sources all use (docs/schema-v1.md §3).
 */
export const SOURCE_TYPE = {
  document: 'document',
  meeting: 'meeting',
}

/**
 * Client-side validation text. Fixed here so every form says the same thing.
 * The password rules themselves live in src/utils/password.js, which is the
 * single copy of the policy the server also enforces (FR-01).
 */
export const VALIDATION = {
  nameRequired: 'Enter your name.',
  emailRequired: 'Enter your email address.',
  emailInvalid: 'Enter a valid email address.',
  emailTaken: 'That email address is already registered.',
  passwordRequired: 'Enter a password.',
  passwordRequirements: 'Your password does not meet all of the requirements listed below.',
  confirmPasswordRequired: 'Re-enter your password.',
  passwordMismatch: 'The two passwords do not match.',
  // FR-08: "Unsupported formats are rejected immediately client-side with a
  // message (E.g., File type not supported. Accepted formats: PDF, DOCX,
  // XLSX)". The FR's example omits TXT because it is an example; the list is the
  // four in ACCEPTED_EXTENSIONS (D-15), and the server's own 415 message names
  // the same four (apps/api/views.py UNSUPPORTED_FORMAT_MESSAGE).
  fileTypeUnsupported: `File type not supported. Accepted formats: ${ACCEPTED_FORMATS_LABEL}.`,
  fileTooLarge: `File is larger than ${MAX_UPLOAD_LABEL}. Choose a smaller file.`,
  // FR-08's upload area collects "a title for each file".
  documentTitleRequired: 'Enter a title for this file.',
  meetingTitleRequired: 'Enter a meeting title.',
  meetingDateRequired: 'Enter the date of the meeting.',
  // FR-09 Validation: "the date may not be in the future". The server compares in
  // the project timezone and refuses one anyway.
  meetingDateFuture: 'A meeting date may not be in the future.',
  transcriptRequired: 'Paste the transcript text.',
  transcriptFileRequired: 'Choose a transcript file.',
  // FR-12: "queries shorter than two characters are rejected client-side". The
  // message names the minimum, so a refusal says what would be accepted.
  searchTermRequired: 'Enter something to search for.',
  searchTermTooShort: `Enter at least ${SEARCH_MINIMUM_LENGTH} characters to search.`,
  // FR-12's question bounds. Named in the message for the same reason.
  questionRequired: 'Enter a question.',
  questionTooShort: `A question needs at least ${QUESTION_MINIMUM_LENGTH} characters.`,
  questionTooLong: `A question can be at most ${QUESTION_MAXIMUM_LENGTH} characters.`,
}

/**
 * Fixed, user-facing text for every screen: auth and roles, then ingestion and
 * the repository. One copy of each string, so two screens saying the same thing
 * cannot come to say it differently.
 */
export const TEXT = {
  sessionExpired: 'Your session has expired. Please sign in again.',
  // FR-04 wording: "a brief confirmation 'You've been logged out'".
  loggedOut: 'You’ve been logged out.',
  registered: 'Your account has been created. Sign in to continue.',
  // FR-02: "Where the account is locked and the submitted password was correct,
  // a distinct message is shown." Distinct from the 401 text, and it names no
  // account detail, so it discloses nothing a 401 does not.
  accountLocked:
    'This account is temporarily locked after too many failed sign-in attempts. ' +
    'Please try again later.',
  // FR-06: the "403 - Access Denied" page a guarded route redirects to. It never
  // describes what the requested screen would have contained.
  accessDeniedTitle: '403 – Access Denied',
  accessDenied: 'You do not have permission to view this page.',
  notPermittedTitle: 'Not permitted',
  notPermitted: 'You do not have permission to view this page.',
  checkingSession: 'Checking your session…',
  loadingUsers: 'Loading users…',
  noUsers: 'There are no users to show.',
  roleSaved: (name, role) => `${name}'s role is now ${role}.`,
  // FR-05 confirmation dialogue, worded as the FR's own example
  // ("Change Jane Doe's role to Admin?").
  roleChangeConfirm: (name, role) => `Change ${name}'s role to ${role}?`,
  roleChangeStale: 'That user or role no longer exists. The list has been reloaded.',
  // FR-05: "a user cannot remove their own administrator role, preventing
  // accidental lockout of the last administrator."
  roleChangeSelfDemotion:
    'You cannot remove your own Administrator role. Ask another Administrator to change it for you.',

  /* ---- Visibility, shared by FR-08 and FR-09 (D-29) --------------------- */
  // Omitting the field means both roles, so "Everyone" sends nothing at all. A
  // scope excluding the contributor's own role is refused by the server with a
  // 403, so it is never offered here — uploading into a scope you cannot read is
  // how content is lost.
  visibilityEveryone: 'Everyone (Employees and Administrators)',
  visibilityAdministrators: 'Administrators only',
  visibilityHint: 'Who can find this in search.',
  visibilityFixed: 'Content you add is visible to everyone in the organisation.',

  /* ---- FR-08 document upload ------------------------------------------- */
  uploadDropHint: `Accepted formats: ${ACCEPTED_FORMATS_LABEL}. Up to ${MAX_UPLOAD_LABEL} per file.`,
  uploadDropTarget: 'Drop files here',
  uploadQueueEmpty: 'No files chosen yet.',
  uploadTransferring: 'Uploading',
  // The transfer has finished and the server is extracting, chunking and
  // embedding. Ingestion is synchronous (FR-08), so this is the wait.
  uploadProcessing: 'Processing…',
  uploadIndexed: 'Indexed. This document can now be found in search.',
  // The 201 whose status is "Partially indexed": some chunks failed to embed.
  uploadPartiallyIndexed: `Partially indexed. ${PARTIALLY_INDEXED_DETAIL}`,
  // FR-08 Front-End, verbatim: "if extraction fails, a 'Processing failed.
  // Please try again' action is shown." The action calls the reprocess endpoint,
  // which re-runs ingestion against the original already stored on the server
  // rather than sending the file a second time (D-32).
  //
  // The wording differs by status because the honest message differs. FR-08 ties
  // the action to extraction failing, but a scanned PDF with no text layer parses
  // identically however many times the same bytes are read: only an "Indexing
  // failed" — a provider outage — is a failure a retry genuinely recovers. The
  // action is offered in every case the clause names; its text stops promising
  // what identical bytes cannot deliver. D-32 records this as a flaw in the
  // requirement rather than in the build.
  processingFailed: 'Processing failed. Please try again.',
  processingFailedExtraction:
    'Processing failed. No text could be read from this file. Trying again will ' +
    'read the same file, so it will only help if you upload a text-based or ' +
    'OCR’d copy instead.',
  processingFailedInsufficient:
    'Processing failed. This file holds too little text to index, so trying again ' +
    'will not change the result.',
  // Not a failure, so it does not claim to be one: the document is searchable and
  // some of its passages are not. Running ingestion again over the stored file is
  // worth offering, because a provider outage is the usual reason a chunk did not
  // embed.
  reprocessPartiallyIndexed: `${PARTIALLY_INDEXED_DETAIL} Trying again re-runs indexing on the stored file.`,
  uploadRetry: 'Try again',
  uploadRemove: 'Remove',
  // FR-08's 409 is a duplicate document, compared by content and not by
  // filename; the client's generic 409 text is FR-01's duplicate address, which
  // is why this screen supplies its own.
  uploadDuplicate: 'A document with these contents has already been uploaded.',
  uploadNotPermitted: 'You do not have permission to add documents.',
  uploadRejected: 'That file was rejected. Check the title and try again.',
  // What the live region announces when one record's status changes: the record
  // named, then the same words that are on screen against it. Used by the upload
  // queue and by the repository list, which is why it names neither.
  statusAnnouncement: (name, message) => `${name}: ${message}`,

  /* ---- FR-08 / FR-15 document repository -------------------------------- */
  loadingDocuments: 'Loading documents…',
  noDocuments: 'No documents have been uploaded yet.',
  documentsLoadFailed: 'Could not load documents',
  // FR-08's retry, reachable from the list rather than only from the queue that
  // uploaded the file: a document left at a failed status has a route back after
  // the tab is closed. A column of buttons all named "Try again" names nothing to
  // anyone moving between controls, so each one names its own document.
  documentRetryLabel: (title) => `Try again for ${title}`,
  documentReprocessFailed: 'Could not process this document',
  // The 409: it is indexed already, or a copy was indexed while this list sat
  // open. Either way the list is out of date, so it is re-read.
  documentAlreadyIndexed: 'This document has already been indexed. The list has been reloaded.',
  // The 404, which is also the answer for a document outside the caller's scope.
  // One message covers both and distinguishes neither (CLAUDE.md §6, invariant 1).
  documentNotFound: 'That document could not be found. The list has been reloaded.',
  documentReprocessNotPermitted: 'You do not have permission to process documents.',

  /* ---- FR-09 meeting transcripts ---------------------------------------- */
  loadingMeetings: 'Loading meetings…',
  noMeetings: 'No meeting transcripts have been added yet.',
  meetingsLoadFailed: 'Could not load meetings',
  loadingMeeting: 'Loading the transcript…',
  meetingLoadFailed: 'Could not load the transcript',
  // FR-09 Front-End: "a processing indicator is displayed while ingestion runs".
  // Ingestion is synchronous, so the request itself is the wait.
  meetingProcessing: 'Processing the transcript. This can take a moment.',
  meetingIndexed: (title) => `${title} was stored and indexed.`,
  // The 422: the transcript is kept whatever the AI step did (NFR-20), and the
  // record says why it cannot be searched.
  meetingStoredNotIndexed:
    'The transcript was stored, but it could not be indexed, so it will not appear in search results.',
  meetingNotPermitted: 'You do not have permission to add meeting transcripts.',
  meetingRejected: 'That transcript was rejected. Check the form and try again.',
  // The error summary a failed client-side check focuses, so a keyboard user is
  // taken to the reason rather than left where they pressed the button.
  checkHighlightedFields: 'Check the highlighted fields and try again.',
  // A meeting outside the caller's scope answers 404, exactly as an id that names
  // nothing does, so this message covers both and distinguishes neither
  // (CLAUDE.md §6, invariant 1).
  meetingNotFound: 'That meeting transcript could not be found.',
  meetingSourceText: 'Paste the transcript text',
  meetingSourceFile: 'Upload a transcript file',
  meetingSourceLegend: 'How are you supplying the transcript?',
  // FR-09: attendees are a participation record and never an access control
  // (D-16, CLAUDE.md §6, invariant 3).
  attendeesHint:
    'A record of who took part. Attendees do not control who can read the transcript; visibility does.',
  loadingAttendees: 'Loading the list of people…',
  // No longer "only an Administrator can do this": FR-09's association is open to
  // every role, and the picker reads the directory any session may read (D-34).
  // This is the note for having nobody to choose from — a failed read, or a
  // directory that came back empty — and it says what is still possible.
  attendeesUnavailable:
    'There is nobody to choose from at the moment, so attendees cannot be recorded with this transcript. ' +
    'The transcript itself can still be added.',
  transcriptHeading: 'Transcript',
  // FR-09 states that speaker and timestamp parsing is out of scope for this
  // version, so the stored text is shown exactly as it was supplied.
  transcriptVerbatim:
    'Stored and shown exactly as it was supplied, including any speaker labels and timestamps.',

  /* ---- FR-12 keyword search --------------------------------------------- */
  searchFieldLabel: 'Search',
  searchNavLabel: 'Search the knowledge base',
  searchSubmit: 'Search',
  searchHeading: 'Search',
  searchHint: `Searches document and meeting titles and their indexed passages. At least ${SEARCH_MINIMUM_LENGTH} characters.`,
  // No term yet: a prompt, not an error. Typing a URL with no `q` lands here too.
  searchPrompt: 'Enter a word or phrase to search the documents and meeting transcripts you can see.',
  searching: 'Searching…',
  searchFailed: 'Could not run that search',
  searchResultsFor: (term) => `Results for “${term}”`,
  // Nothing matched is an ordinary empty state and never an error. It says
  // nothing about what exists outside the caller's scope, because the screen is
  // not told and there is nothing to say (CLAUDE.md §6, invariant 1).
  searchNothingMatched: (term) => `Nothing in the knowledge base matched “${term}”.`,
  searchNothingMatchedHint: 'Try a different word, or ask the question in your own words instead.',
  searchDocumentsHeading: 'Documents',
  searchMeetingsHeading: 'Meeting transcripts',
  // A group with no results still reads as zero rather than vanishing, so the
  // two groups FR-12 names are always both on the screen.
  searchGroupEmptyDocuments: 'No documents matched.',
  searchGroupEmptyMeetings: 'No meeting transcripts matched.',
  searchGroupCount: (count) => (count === 1 ? '1 result' : `${count} results`),
  searchTotalAnnouncement: (term, total) =>
    total === 1 ? `1 result for ${term}.` : `${total} results for ${term}.`,
  // `snippet` is "" only where the source has no indexed passage at all — an
  // FR-08 "Insufficient content" document, matched on its title. An honest note
  // rather than invented text.
  searchSnippetUnavailable: 'Matched on its title. This item has no indexed passage to show.',
  searchAskInstead: 'Ask this as a question',

  /* ---- FR-12 the answer path, FR-13 the assistant ----------------------- */
  askNavLabel: 'Ask',
  askHeading: 'Ask the knowledge base',
  askFieldLabel: 'Your question',
  askHint: `Ask in your own words, between ${QUESTION_MINIMUM_LENGTH} and ${QUESTION_MAXIMUM_LENGTH} characters. Answers come only from material you can see, and every statement carries a citation.`,
  askSubmit: 'Ask',
  // Retrieval, generation and citation verification all happen inside the
  // request, so this is the wait. It is announced as well as spun.
  asking: 'Looking for an answer…',
  askRejected: 'That question was not accepted. Check it and try again.',
  // FR-12's 503 is NFR-19's notice: shown the moment the API answers, in place of
  // a spinner that never resolves. Distinct from the no-answer state below,
  // because "we could not ask" and "the corpus has no answer" are different
  // events and a user who conflates them retries the wrong thing.
  askUnavailableTitle: 'The AI service is unavailable',
  askNotRecorded: 'Your question was not recorded, so you can ask it again in a moment.',
  askQuestionLabel: 'You asked',
  answerHeading: 'Answer',
  // The visible acknowledgement a reply lands with. Usability finding 1: an
  // announcement that only assistive technology receives is half a signal, so
  // this text is on the screen and in a live region at once.
  answerReady: (statements, sources) =>
    `Answer ready: ${statements === 1 ? '1 statement' : `${statements} statements`} from ` +
    `${sources === 1 ? '1 source' : `${sources} sources`}.`,
  noAnswerReady: 'No answer could be found in the knowledge base.',
  // Every statement carries a citation and the number rendered is the `position`
  // the server stored, so the screen and the AnswerCitation row are the same
  // number (FR-12 "numbered inline citations").
  citationToggleLabel: (position) => `Source for statement ${position}`,
  citationPassageHeading: 'Source passage',
  // Defensive only: the contract makes `sources` a superset of the cited chunks,
  // so a citation whose passage is not in the reply should not occur. If one
  // does, the number stays on the screen as plain text — the statement is cited,
  // and inventing a passage or hiding the citation would both be worse.
  citationPassageUnavailable: 'The source passage did not arrive with this answer.',
  sourcesHeading: 'Sources',
  // FR-12: "a 'Sources' panel lists every item consulted with its date, allowing
  // the user to judge how current the underlying material is". Consulted, which
  // is a wider set than cited, and the panel says so rather than implying that
  // everything listed was quoted.
  sourcesIntro:
    'Every item consulted to build this answer, with its date. Some were consulted without being cited.',
  sourcePassageCount: (count) => (count === 1 ? '1 passage consulted' : `${count} passages consulted`),
  // FR-12's "links to the source document or meeting". A meeting has a screen of
  // its own; a document is reached through the repository, which is the only read
  // route the API offers for one.
  viewMeeting: 'View the transcript',
  viewDocument: 'Find in the document repository',
  sourceTypeDocument: 'Document',
  sourceTypeMeeting: 'Meeting',

  /* ---- FR-12 no answer, and the partial matches beside it ---------------- */
  // FR-12: "the interface states plainly that it cannot answer from the available
  // knowledge base and does not present a speculative answer". There is no empty
  // answer frame here pretending to be one, and no fragment: nothing that failed
  // citation verification reaches the browser at all (invariant 6).
  noAnswerTitle: 'This cannot be answered from the knowledge base',
  // The server sends the fixed text; this is the copy used only if a reply
  // somehow carries none, so the state always says something plain.
  noAnswerFallback: 'This question cannot be answered from the available knowledge base.',
  // FR-12: "Any partially related items found are offered, clearly labelled as
  // partial matches." The no-answer reply deliberately carries no passages, so
  // these come from the keyword search over the same question — in scope by
  // construction, since search applies the same permission filter. They are
  // offered as links to sources and never as answer content, which is why no
  // snippet is shown here.
  partialMatchesHeading: 'Partial matches',
  partialMatchesIntro:
    'These items are related to your question. They are not an answer and nothing in them was cited — open one to read it yourself.',
  // The search runs on one word taken from the question, because the endpoint
  // matches a term as a single substring and a whole question matches nothing
  // (src/utils/partialMatches.js). The word is named so nobody has to guess why an
  // item is in the list.
  partialMatchesTerm: (term) => `Found by searching for “${term}”.`,

  /* ---- FR-13 the conversation thread ------------------------------------ */
  conversationsHeading: 'Your conversations',
  loadingConversations: 'Loading your conversations…',
  conversationsLoadFailed: 'Could not load your conversations',
  noConversations: 'You have no previous conversations yet.',
  loadingConversation: 'Opening that conversation…',
  conversationLoadFailed: 'Could not open that conversation',
  // The 404, which is the answer both for a thread that does not exist and for
  // one that is not the caller's. One message, and it distinguishes neither.
  conversationNotFound: 'That conversation could not be found. Your list has been reloaded.',
  conversationOpen: (title) => `Open the conversation “${title}”`,
  conversationCurrent: 'Current conversation',
  // FR-13: "the active thread can be cleared to begin a new topic" — which is
  // starting a new conversation, not deleting one. There is no delete route and
  // no rename route, so there is no control for either.
  newTopic: 'Start a new topic',
  newTopicHint: 'Clears the thread on screen and begins a new conversation. Your previous conversations are kept.',
  threadEmpty: 'Ask a question to start this conversation. Follow-up questions can refer back to it.',
  threadNew: 'New topic. Your first question will start a new conversation.',
  // A reopened thread keeps each statement and its citation number. It cannot
  // expand a citation, because no route returns the passages a past turn was
  // built from. Said plainly rather than left as a control that does nothing.
  threadReopenedNote:
    'Source passages are shown with a live answer. A reopened conversation keeps each statement and its citation number.',
}
