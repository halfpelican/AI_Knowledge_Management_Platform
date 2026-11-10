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
 * Both render FR-14's dashboard (Stage 5 item 3, D-70): the routes were made in
 * Stage 2 so the redirect was role-specific from the start (D-25), and FR-14
 * replaced what they render rather than where they live. The content is the same
 * on both, because the server scopes every panel to the caller's role.
 */
export const DASHBOARD_PATHS = {
  [ROLES.administrator]: '/admin',
  [ROLES.employee]: '/dashboard',
}

/**
 * Where a signed-in user belongs. A role this table does not name still gets the
 * dashboard: `/dashboard` asks only for a session, and the home route redirects a
 * signed-in user here, so a fallback of `/` would send it back to itself.
 */
export function dashboardPathForRole(role) {
  return DASHBOARD_PATHS[role] ?? DASHBOARD_PATHS[ROLES.employee]
}

/**
 * The two document statuses a 201 can carry (docs/schema-v1.md §3, mirrored in
 * apps/core/constants.py DOCUMENT_STATUS_VALUES). The interface branches on
 * these two and displays whatever status the server actually recorded, so a
 * value added later shows up rather than being silently rendered as "Indexed".
 *
 * **Displaying an unknown value is not the same as handling one.** The seventh
 * value, "Too large to index", was added backend-side at Stage 4 item 12b and the
 * rows did show it — while `canReprocess` went on offering FR-08's retry for it
 * and `statusMessageFor` went on calling it a transient failure. The fall-through
 * protects the *status text*, never the rule that goes with it, so a new value
 * has to be listed here as well (D-51, and D-57 on how it came to be missed).
 */
export const DOCUMENT_STATUS = {
  indexed: 'Indexed',
  // Transient: set inside the ingestion transaction before extraction begins, so a client
  // normally never sees it — an unexpected failure rolls the row back rather than leaving it
  // here. Listed anyway, because the fall-through below protects the status TEXT and not the
  // rule that goes with it, and this was the one of the server's seven values that was missing
  // (found by the 27 September re-audit). Unlisted, it fell through to "Processing failed.
  // Please try again.", so a row would have read "Processing — Processing failed."
  processing: 'Processing',
  partiallyIndexed: 'Partially indexed',
  // The three the 422 paths record. Each gets its own retry wording (D-32),
  // because only one of them describes a failure a retry can actually recover.
  extractionFailed: 'Extraction failed',
  insufficientContent: 'Insufficient content',
  indexingFailed: 'Indexing failed',
  // The fourth a 422 can record, and the only one of them that is refused FR-08's
  // retry: the document was turned away before extraction was attempted, on a
  // property of the content, so there is no attempt for a second press to vary
  // (D-51, and src/utils/documentStatus.js for the argument).
  tooLargeToIndex: 'Too large to index',
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
// The upper bound on a search term, mirroring MAXIMUM_SEARCH_LENGTH (D-79's note of
// 10 November 2026). The server answers 400 above it whatever the browser allowed.
export const SEARCH_MAXIMUM_LENGTH = 500
export const QUESTION_MINIMUM_LENGTH = 10
export const QUESTION_MAXIMUM_LENGTH = 500

/**
 * FR-10's new Topic name: at most this many characters, mirroring apps/core/models.py
 * NAME_MAX_LENGTH, the width of `Tags.tag_name` and the `max_length` of the apply
 * route's `tag_name` (docs/api-contract.md, NIT3004 FR-10). Counted after trimming and
 * single-spacing, the form the name is sent in (src/utils/validation.js
 * `spacedTagName`), so the server measures what the screen measured. A convenience:
 * the server answers 400 `{"tag_name": [...]}` above it whatever the browser allowed
 * (CLAUDE.md §6, invariant 4). apps/api/tests/test_front_end_constants_agreement.py
 * fails when the two drift.
 */
export const TAG_NAME_MAXIMUM_LENGTH = 255

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
  // The upper bound (D-79's note), named in the message for the same reason.
  searchTermTooLong: `A search term can be at most ${SEARCH_MAXIMUM_LENGTH} characters.`,
  // FR-12's question bounds. Named in the message for the same reason.
  questionRequired: 'Enter a question.',
  questionTooShort: `A question needs at least ${QUESTION_MINIMUM_LENGTH} characters.`,
  questionTooLong: `A question can be at most ${QUESTION_MAXIMUM_LENGTH} characters.`,
  // FR-10's new Topic name, refused before any request when it is empty or longer
  // than the server's column, both measured as the name is sent: trimmed, and each
  // run of spaces one space. The limit is named, so a refusal says what would do.
  tagNameRequired: 'Enter a name for the new topic.',
  tagNameTooLong: `A topic name can be at most ${TAG_NAME_MAXIMUM_LENGTH} characters.`,
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

  /* ---- D-79's limits and D-85's in-flight refusal, on every screen that can meet one */
  // Login and registration keep the API client's own 429 text (D-26). These are
  // the per-user limits D-79 added, kept together so every 429 the interface can
  // show is read in one place. None of them restates a rate: the rates are the
  // server's (apps/core/constants.py), and what a screen says is only when the
  // limit lifts, from the reply's `Retry-After`.
  //
  // When, in words, from `Retry-After` rounded up (src/utils/retryAfter.js): whole
  // seconds under a minute, whole minutes from there. "later" where the reply
  // carried no usable `Retry-After`, so nothing is promised that was not sent.
  retryInSeconds: (seconds) => (seconds === 1 ? 'in 1 second' : `in ${seconds} seconds`),
  retryInMinutes: (minutes) => (minutes === 1 ? 'in 1 minute' : `in ${minutes} minutes`),
  retryNow: 'now',
  retryLater: 'later',
  // The in-flight 429 (`code` "ask_in_flight"). Not NFR-19's notice: nothing is
  // unavailable, the user's own previous question is still being answered — in
  // another tab, or in this one before the screen was left and come back to, or
  // reloaded (D-77). An information notice, not an alert,
  // and it promises no time, because the reply carries none and an answer can take
  // minutes. Nothing was recorded, and the question stays in the field.
  askInFlightTitle: 'Your previous question is still being answered',
  askInFlight:
    'Only one question is answered at a time, and an answer can take several minutes. ' +
    'This question was not recorded, so you can send it again once the previous one has been answered.',
  // The rate 429 on POST /api/ask, and on the create that precedes a first question
  // (POST /api/conversations, its own budget at the same rate, D-80). Either way
  // nothing was recorded and the question stays in the field.
  askRateLimitedTitle: 'Too many questions in a short time',
  askRateLimited: (when) =>
    `You have asked too many questions in a short time. You can ask again ${when}. ` +
    'This question was not recorded, so you can send it again then.',
  // The ingestion 429: one budget for document upload, meeting ingestion and
  // reprocess. "The upload limit" names it alike on all three, so the one limit is
  // recognisably one. The limit is the user's and not the file's, so nothing here
  // says the file was wrong, and each says what became of the material.
  uploadLimitedStatus: 'Not uploaded',
  uploadLimitReached: (when) =>
    `The upload limit has been reached, so this file was not stored. It stays in the queue, and you can upload again ${when}.`,
  reprocessLimitReached: (when) =>
    `The upload limit has been reached, so this document was not processed again. You can try again ${when}.`,
  meetingLimitReached: (when) =>
    `The upload limit has been reached, so this transcript was not stored. What you entered is still in the form, and you can add it ${when}.`,
  // D-85's in-flight 429 on the same three routes (`code` "ingestion_in_flight"):
  // another upload, transcript or reprocess of this user's is still being processed,
  // in another tab or from a screen that was left before it answered. Not the limit,
  // so none of these says "limit". They promise no time, because the reply carries
  // none and an ingestion takes as long as its file does. "Upload" is the word for
  // adding material on all three, as "the upload limit" is.
  uploadInFlight:
    'Your previous upload is still being processed, so this file was not stored. ' +
    'It stays in the queue, and you can upload it again once the previous upload has finished.',
  reprocessInFlight:
    'Your previous upload is still being processed, so this document was not processed again. ' +
    'You can try again once the previous upload has finished.',
  meetingInFlight:
    'Your previous upload is still being processed, so this transcript was not stored. ' +
    'What you entered is still in the form, and you can add it once the previous upload has finished.',

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
  // Usability findings 1 and 2: what the drop zone itself says after a pick or a
  // drop, where the pointer was released, rather than the browser's own "No file
  // chosen". Every file goes into the queue, a refused one with its reason, so the
  // sentence counts what was added and says how many of those cannot be sent.
  dropZoneAdded: (names, refused) => {
    const what = names.length === 1 ? names[0] : `${names.length} files`
    let tail = ''
    if (refused > 0 && names.length === 1) tail = ' It cannot be uploaded; the reason is shown beside it.'
    else if (refused > 0 && refused === names.length) tail = ' None of them can be uploaded; the reason is shown beside each.'
    else if (refused > 0) tail = ` ${refused} of them cannot be uploaded; the reason is shown beside each.`
    return `Added ${what} to the queue below.${tail}`
  },
  // Finding 4: while the queue is sending, the zone says why it takes nothing, and a
  // drop made meanwhile is answered rather than vanishing.
  dropZoneBusy: 'Uploading. You can add more files once these have finished.',
  dropZoneRefused: 'Nothing was added, because files are still uploading. Add more once they have finished.',
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
  //
  // One status is refused the action outright, and it is not one FR-08's clause
  // names: "Too large to index", where the file was never extracted at all
  // (D-51). See `documentTooLargeToIndex` below.
  processingFailed: 'Processing failed. Please try again.',
  processingFailedExtraction:
    'Processing failed. No text could be read from this file. Trying again will ' +
    'read the same file, so it will only help if you upload a text-based or ' +
    'OCR’d copy instead.',
  processingFailedInsufficient:
    'Processing failed. This file holds too little text to index, so trying again ' +
    'will not change the result.',
  // D-51's seventh status, and the one row with a sentence and no button beside
  // it. It says three things: that the document is not searchable, why there is
  // nothing to press — D-32's retry re-runs ingestion on the same stored file, so
  // every attempt would redo extraction and chunking in full and stop at the
  // identical point — and what would actually get the material indexed. It does
  // not say "Processing failed", because nothing was attempted: the document was
  // refused on a property of its content, which is the distinction D-51 exists to
  // draw.
  documentTooLargeToIndex:
    'This document is too large to index, so it will not appear in search results. ' +
    'Indexing it again would repeat the same work and stop at the same point, which ' +
    'is why no retry is offered. A shorter document, or this one split into parts, ' +
    'can be indexed.',
  // "Processing" is transient — set inside the ingestion transaction before extraction
  // begins — so a client should never see it, and an unexpected failure rolls the row
  // back rather than leaving it here. It has wording anyway because the status is now
  // listed: nothing has failed, so it must not fall through to the retry sentence and
  // tell the user that a document still being worked on had failed.
  documentProcessing: 'This document is still being processed.',
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
  repositoryHeading: 'Documents',
  repositoryIntro:
    'Every document you are permitted to see. Browse by department, project, process or topic, filter by title, and sort by title, type, uploader, upload date or status.',
  repositoryUploadLink: 'Upload a document',
  repositoryResultsHeading: 'Results',
  loadingDocuments: 'Loading documents…',
  // The unfiltered 200 with an empty list. It does not say "nothing has been
  // uploaded": an Employee is told the same whether nothing exists or nothing is
  // theirs to see, because the screen is not told which (CLAUDE.md §6, invariant 1).
  noDocuments: 'There are no documents to show yet.',
  documentsLoadFailed: 'Could not load documents',
  // FR-15's text filter: the title contains it (D-71's whitespace rule is the
  // server's). Applied on submit, so typing does not add a history entry per key.
  repositoryFilterLabel: 'Filter by title',
  repositoryFilterHint: 'Shows documents whose title contains these words.',
  repositoryFilterSubmit: 'Filter',
  repositoryFilterFormLabel: 'Filter documents by title',
  // FR-15's browse mode: "navigation by Department, Project, Process or Topic
  // without composing a query". The counts are the server's, computed over the
  // caller's scope after every other active filter (D-72), so each says how many
  // documents choosing that value would show.
  repositoryBrowseHeading: 'Browse',
  repositoryBrowseHint:
    'Choose a value to narrow the list, and choose it again to remove it. The number beside each value is how many documents choosing it would show.',
  repositoryLoadingFacets: 'Loading the values to browse by…',
  // A 204 carries no facets, and the screen does not borrow an earlier reply's
  // (D-72), so it says why the values are missing rather than showing stale ones.
  repositoryBrowseNoMatch: 'There are no values to browse by while nothing matches. Remove a filter to see them again.',
  repositoryBrowseUnavailable: 'The values to browse by are not available. See the message below.',
  repositoryFacetEmpty: 'None in the documents shown.',
  // The noun for the count beside a value; the number itself is on screen.
  repositoryFacetCount: (count) => (count === 1 ? '1 document' : `${count} documents`),
  // The names a filter is shown under, by its parameter (docs/api-contract.md).
  // `status` has no control on this screen; a status in the address is still
  // applied by the server, so it is shown and can be removed like the others.
  repositoryFilterNameQ: 'Title contains',
  repositoryFilterNameStatus: 'Status',
  repositoryFilterNameDepartment: 'Department',
  repositoryFilterNameProject: 'Project',
  repositoryFilterNameProcess: 'Process',
  repositoryFilterNameTopic: 'Topic',
  // Not a filter (D-72), so never in the active filters; named only when a 400
  // refuses one.
  repositoryFilterNameSort: 'Sort order',
  repositoryActiveFilters: 'Active filters',
  repositoryRemoveFilter: 'Remove',
  // The accessible name of each Remove button, so a column of "Remove" names the
  // filter it removes (WCAG 2.1 SC 2.4.6), and starts with the visible word
  // (SC 2.5.3).
  repositoryRemoveFilterLabel: (name, value) => `Remove filter ${name}: ${value}`,
  repositoryClearFilters: 'Clear filters',
  // FR-15's 204: a filter combination with no accessible matches. An ordinary
  // state, not an error, and it says nothing about material outside the caller's
  // scope (invariant 1).
  repositoryNoMatchTitle: 'No documents match these filters',
  repositoryNoMatch: 'Remove a filter, or clear them all, to see more documents.',
  repositoryResultCount: (count) => (count === 1 ? 'Showing 1 document.' : `Showing ${count} documents.`),
  // A 400 on a filter or the sort. Only the address can produce one, since every
  // control writes a value the server accepts.
  repositoryCheckFilters: 'One of the filters or the sort order could not be applied.',
  repositoryShowAll: 'Show all documents',
  // The column headings, which are also the sort controls (FR-15: "with sorting").
  repositoryColumnTitle: 'Title',
  repositoryColumnType: 'Type',
  repositoryColumnUploader: 'Uploaded by',
  repositoryColumnUploaded: 'Uploaded',
  repositoryColumnStatus: 'Status',
  repositoryColumnDepartment: 'Department',
  repositorySortedAscending: 'sorted ascending',
  repositorySortedDescending: 'sorted descending',
  repositoryTableCaption: 'Documents in the knowledge base. Every column heading but Department is a button that sorts by that column.',
  // Shown on the list a successful delete returns to.
  repositoryDeleted: (title) => `“${title}” was deleted.`,
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
  // FR-15's detail view, which is also the screen a citation links to (D-46). A
  // document outside the caller's scope answers 404, exactly as an id that names
  // nothing does, so this message covers both and distinguishes neither
  // (CLAUDE.md §6, invariant 1).
  loadingDocument: 'Loading the document…',
  documentLoadFailed: 'Could not load the document',
  documentRecordNotFound: 'That document could not be found.',
  documentNotFoundTitle: 'Not found',
  documentBackToList: 'Back to documents',
  documentFieldType: 'Type',
  documentFieldUploader: 'Uploaded by',
  documentFieldUploaded: 'Uploaded',
  documentFieldStatus: 'Status',
  documentFieldDepartment: 'Department',
  documentFieldVisibleTo: 'Visible to',
  documentFieldProject: 'Project',
  documentFieldProcess: 'Process',
  documentFieldTopic: 'Topic',
  documentNotRecorded: 'Not recorded',
  documentNoTags: 'None recorded',
  // D-63: the extracted content, read from the document's stored extracted text
  // and never reassembled from passages. It is plain text, so the note says what
  // a reader will not get (D-63, "formatting fidelity").
  documentExtractedHeading: 'Extracted content',
  documentExtractedNote:
    'The text read from the file when it was indexed, shown as plain text. Layout, headings and table structure are not reproduced.',
  // `extracted_text` is null: the document has no extracted content. Keyed on
  // the null and not on the status, because which statuses leave text behind is a
  // fact of the ingestion path (D-63).
  documentExtractedEmpty: 'No text was extracted from this document, so there is nothing to show here.',
  // FR-15's "download link" (D-75). It is the link's whole accessible name, so it
  // says what arrives: the file as it was uploaded, and not the extracted text
  // shown on the same screen. Offered on every document whatever its status,
  // because the original is stored whether or not it was indexed.
  documentDownload: 'Download the original file',
  // FR-15's deletion: "requires confirmation and is available only to users
  // holding the appropriate permission". The control shows only when the detail
  // says `can_delete`; the server checks the permission on every delete
  // whatever this screen showed (CLAUDE.md §6, invariant 4).
  documentDelete: 'Delete document',
  documentDeleteConfirm: (title) => `Delete “${title}”?`,
  // What FR-15 promises a delete does, and what D-67 does to answers that cited
  // it. Nothing more: there is no undo, and the dialogue says so.
  documentDeleteBody:
    'The document, its extracted text and its search index entries are removed, so it will no longer be found by search or used to answer questions. Earlier answers that cited it will no longer show it as a source. This cannot be undone.',
  documentDeleting: 'Deleting…',
  documentDeleteCancel: 'Cancel',
  documentDeleteFailed: 'Could not delete the document',
  documentDeleteNotPermitted: 'You do not have permission to delete documents.',
  // FR-10's classification section on the detail view (src/components/
  // Classification.jsx, D-104, D-105). Every AI value is said to be one in words,
  // never by colour or position alone: "each marked as AI-generated" is the FR's
  // clause, and a mark a screen reader cannot read is not a mark.
  classificationHeading: 'Classification',
  classificationIntro:
    'The type, the department and some tags are suggested by AI and are marked as such. A suggestion can be confirmed, edited or removed; what a person confirms or edits is kept by later reprocessing.',
  // `classification` is null: nothing has been suggested. An ordinary state.
  classificationNone: 'Not classified yet.',
  classificationNoneHint: 'No type, department or tags have been suggested for this document.',
  classifyNow: 'Classify now',
  classifying: 'Classifying…',
  // The request itself is the wait: the AI reads the opening of the document and
  // answers in ten to sixty seconds. Announced as well as spun.
  classifyingStatus: 'Classifying this document. This can take up to a minute.',
  classifyDone: 'The document has been classified.',
  classifyFailedTitle: 'Could not classify this document',
  // FR-10's 422: there is no extracted text to classify. It says what would help.
  classifyNoText:
    'No text was extracted from this document, so there is nothing to classify. A text-based or OCR’d copy can be.',
  // The 503 is NFR-19's notice; this sentence follows the client's fixed 503 text and
  // says what became of the record: nothing.
  classifyNotDone: 'The document was not classified, so nothing here has changed.',
  // The ingestion 429 (D-79), the budget classification shares with upload,
  // meeting ingestion and reprocess. Named "the upload limit" as the other three
  // name it, so the one limit is recognisably one.
  classifyLimitReached: (when) =>
    `The upload limit has been reached, so this document was not classified. You can try again ${when}.`,
  classificationFieldType: 'Document type',
  classificationFieldDepartment: 'Department',
  // The document's type while the only suggestion is provisional: `doc_type` is
  // null, and the screen says so rather than showing the held suggestion in its
  // place (FR-10: "presented for confirmation rather than applied silently").
  classificationNotAssigned: 'Not yet assigned',
  classificationSuggestedByAI: 'Suggested by AI',
  // D-119 finding 10: an applied department whose `department_applied_by` is "user" is
  // one a person gave, typed at upload or written through the confirm route, which the
  // machine's suggestion matched. It is the person's, so it does not read "Suggested by
  // AI"; the second sentence keeps the machine's assignment beside it (FR-10).
  classificationGivenByPerson: 'Given by a person',
  classificationSuggestionMatched: 'The AI’s suggestion matched it',
  classificationAwaiting: 'Awaiting your confirmation',
  classificationConfirmed: 'Confirmed by a person',
  classificationConfidence: (percent) => `${percent}% confidence`,
  // A provisional value, named beside the "not yet assigned" effective value, so
  // the reader sees what confirming would apply.
  classificationSuggestion: (value) => `The AI suggested ${value}`,
  // A held department suggestion beside a different department already on the
  // document, which since 10 November stays until a person accepts the suggestion
  // (D-105's note). The empty-body confirm writes the suggestion over it, and this
  // says so, so "Confirm" is not read as confirming the department on screen.
  classificationConfirmReplaces: (current, suggested) => `Confirming replaces ${current} with ${suggested}.`,
  // A department outside the known departments is discarded, never written
  // (FR-10's controlled taxonomy growth). The department shown is the document's
  // own, and this sentence says what happened to the suggestion.
  classificationDiscardedDepartment: (value) =>
    `The AI suggested “${value}”, which is not one of the known departments, so it was not applied.`,
  classificationDiscardedDepartmentUnnamed:
    'The AI’s department suggestion was not one of the known departments, so it was not applied.',
  // One request confirms both suggestions as they stand; the edit form sends the
  // chosen values in one request as well.
  classificationConfirmAll: 'Confirm type and department',
  classificationConfirming: 'Confirming…',
  classificationConfirmedAll: 'The type and department are confirmed.',
  classificationEdit: 'Edit type and department',
  classificationEditLegend: 'Edit the type and department',
  classificationDepartmentHint: 'Leave empty to record no department.',
  classificationSave: 'Save',
  classificationSaving: 'Saving…',
  classificationCancel: 'Cancel',
  classificationSaved: 'The type and department have been saved.',
  classificationFailed: 'Could not update the classification',
  // The 400 on the edit form, whose message is already under the field.
  classificationCheckFields: 'Check the highlighted field and try again.',
  // A 403 on any action: the role may not change classifications, so the
  // controls go, and the sentence says why in words. The record stays.
  classificationNotPermitted: 'Your role may not change classifications, so these controls are not available.',
  classificationTagsHeading: 'Tags',
  // Provenance per tag, in words (FR-10: "tags applied automatically are visually
  // distinguished from those applied by a person"). A word, not only a border.
  tagAddedByPerson: 'Added by a person',
  tagSuggestedByAI: 'Suggested by AI',
  tagConfirmedAI: 'Suggested by AI, confirmed by a person',
  tagConfirm: 'Confirm',
  tagRemove: 'Remove',
  tagReject: 'Reject',
  // The accessible names, so a column of "Confirm" and "Remove" buttons each name
  // their tag (WCAG 2.1 SC 2.4.6), starting with the visible word (SC 2.5.3).
  tagConfirmLabel: (name) => `Confirm tag ${name}`,
  tagRemoveLabel: (name) => `Remove tag ${name}`,
  tagRejectLabel: (name) => `Reject suggested tag ${name}`,
  tagConfirmed: (name) => `“${name}” is now a confirmed tag.`,
  tagRemoved: (name) => `“${name}” was removed.`,
  tagRejected: (name) => `The suggestion “${name}” was rejected.`,
  // Held suggestions: provisional AI tags and proposed new Topic values. They are
  // not the document's tags until confirmed (FR-10), and the heading says so.
  suggestedTagsHeading: 'Suggested tags awaiting confirmation',
  suggestedTagsIntro:
    'These are suggestions, not tags of the document. Confirm one to add it as a tag, or reject it.',
  // A Topic value the AI proposed that is not yet in the list of topics: FR-10
  // allows a new value in Topic only, and only once a person confirms it.
  proposedTopicLabel: 'New topic, not yet in the list of topics',
  proposedTopicConfirmLabel: (value) => `Confirm new topic ${value}`,
  proposedTopicRejectLabel: (value) => `Reject new topic ${value}`,
  proposedTopicConfirmed: (value) => `“${value}” was added as a topic tag.`,
  proposedTopicRejected: (value) => `The proposed topic “${value}” was rejected.`,
  // FR-10's provenance clause and UC-09 A3: a person applies a tag, choosing one the
  // document's own classification scheme offers (`tag_options`) or typing a new
  // Topic, the one dimension FR-10 lets grow. What they add reads as a person's tag.
  tagAddHeading: 'Add a tag',
  tagAddIntro:
    'Choose a tag offered for this document, or type a new topic. A tag you add is marked as added by a person.',
  tagChooseLegend: 'Choose an existing tag',
  tagDimensionLabel: 'Dimension',
  tagChooseLabel: 'Tag',
  // A dimension with nothing to offer is said to have none, rather than shown as an
  // empty list. It speaks of this document's options only (invariant 1).
  tagChooseNone: (dimension) => `No ${dimension} tags are offered for this document.`,
  tagAdd: 'Add tag',
  // The accessible name says which tag the press applies, after the visible words
  // (WCAG 2.1 SC 2.4.6, SC 2.5.3).
  tagAddLabel: (name) => `Add tag ${name}`,
  tagAdding: 'Adding…',
  tagNewTopicLegend: 'Type a new topic',
  tagNewTopicLabel: 'New topic',
  tagNewTopicHint: `Only a topic can be new; a project or process is chosen from the existing tags. Up to ${TAG_NAME_MAXIMUM_LENGTH} characters.`,
  tagNewTopicAdd: 'Add topic',
  // The 201 and the 200 are worded apart: a new link, or a tag the document already
  // had, which the server confirmed (a held suggestion), restored (one removed) or
  // left as it was. After either, the tag is among the document's tags.
  tagApplied: (name) => `“${name}” was added as a tag.`,
  tagAlreadyApplied: (name) => `“${name}” was already on this document and is among its tags.`,
  // FR-10's 409, word for word as the server sends it (apps/api/views.py
  // TOPIC_ALREADY_OFFERED_MESSAGE). Shown from this copy, because the screen never
  // renders a backend string; tests/documentClassification.test.jsx fails when the two
  // drift.
  tagAlreadyOffered: 'A Topic with this name is already offered for this document. Choose it from the tag options.',
  // Said after it only when the tag the 409 named was found and selected.
  tagAlreadyOfferedSelected: 'It is now selected under “Choose an existing tag”, so pressing Add tag applies it.',
  // `input_truncated`: only the opening of a long document was read (D-104). Said
  // rather than hidden, which is why the record keeps the flag.
  classificationTruncated: 'Only the opening of this document was read to classify it.',
  // The meeting delete, which is not in the proposal and mirrors the document
  // delete above (src/pages/MeetingDetail.jsx). The control shows only when the
  // meeting detail says `can_delete`; the server checks `manage_meetings` on
  // every delete whatever this screen showed (CLAUDE.md §6, invariant 4). Its
  // 404 reuses `meetingNotFound` below, the detail's own 404 message, so a
  // meeting already gone and one now out of scope read the same.
  meetingDelete: 'Delete meeting',
  meetingDeleteConfirm: (title) => `Delete “${title}”?`,
  // What the delete removes, and what D-67 does to answers that cited it.
  // Nothing more: there is no undo, and the dialogue says so.
  meetingDeleteBody:
    'The meeting, its transcript and its indexed passages are removed, so it will no longer be found by search or used to answer questions. Earlier answers that cited it will no longer show it as a source. This cannot be undone.',
  meetingDeleting: 'Deleting…',
  meetingDeleteCancel: 'Cancel',
  meetingDeleteFailed: 'Could not delete the meeting',
  meetingDeleteNotPermitted: 'You do not have permission to delete meetings.',
  // Shown on the meetings list a successful delete returns to.
  meetingsDeleted: (title) => `“${title}” was deleted.`,

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
  // The transcript file's drop zone states its own state (usability finding 2).
  meetingFileNone: 'No file chosen yet.',
  meetingFileChosen: (name) => `Chosen: ${name}`,
  meetingFileBusy: 'Adding the transcript. The file cannot be changed until it has finished.',
  // FR-09: attendees are a participation record and never an access control
  // (D-16, CLAUDE.md §6, invariant 3).
  attendeesHint:
    'A record of who took part. Attendees do not control who can read the transcript; visibility does.',
  loadingAttendees: 'Loading the list of people…',
  // Usability finding 5: the picker adds one person at a time to a visible list,
  // with no modifier keys. These are its words.
  attendeeAddLabel: 'Add an attendee',
  attendeeChoosePrompt: 'Choose a person…',
  attendeeAllAdded: 'Everyone in the directory has been added.',
  attendeeAddButton: 'Add',
  attendeeListLabel: 'Attendees to be recorded',
  attendeeNoneYet: 'No attendees added yet.',
  attendeeRemove: 'Remove',
  attendeeRemoveLabel: (person) => `Remove ${person}`,
  attendeeAdded: (person) => `${person} added to the attendees.`,
  attendeeRemoved: (person) => `${person} removed from the attendees.`,
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
  sourcesHeading: 'Sources',
  // FR-12: "a 'Sources' panel lists every item consulted with its date, allowing
  // the user to judge how current the underlying material is". Consulted, which
  // is a wider set than cited, and the panel says so rather than implying that
  // everything listed was quoted.
  sourcesIntro:
    'Every item consulted to build this answer, with its date. Some were consulted without being cited.',
  sourcePassageCount: (count) => (count === 1 ? '1 passage consulted' : `${count} passages consulted`),
  // FR-12's "links to the source document or meeting". Both types now have a
  // screen of their own, served by `GET /api/meetings/{id}` and
  // `GET /api/documents/{id}` (D-46) — until Stage 4 item 10b a document citation
  // could only be pointed at the repository list, which is a link and not a link
  // to the source.
  viewMeeting: 'View the transcript',
  viewDocument: 'View the document',
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
  // A stored turn that WAS answered and none of whose citations still points at a
  // chunk — `provenance_removed` on the turn (Stage 4 item 1c, D-67). Not the
  // no-answer copy above, which would tell the reader their question cannot be
  // answered from the knowledge base. That is a claim about the corpus, and this
  // state makes none: after a re-index or a successful reprocess the material is
  // still indexed under new identifiers, and a user who believed the no-answer
  // sentence would stop asking a question the system can answer; after a failed
  // reprocess or FR-15's deletion the material is gone. No statements are shown,
  // because a statement without its citation is what invariant 6 forbids.
  //
  // The wording says what happened to the RECORD. It says nothing about
  // permissions, because this state has nothing to do with them: the chunks the
  // answer cited are gone for every reader alike. A turn the reader may no longer
  // see renders as the silent no-answer state above and says nothing whatever
  // (invariant 1), which is why the two do not share copy.
  provenanceRemovedTitle: 'The sources for this answer can no longer be shown',
  // Must match apps/core/constants.py PROVENANCE_REMOVED_MESSAGE. It promises NOTHING
  // about the corpus: a failed reprocess leaves the document with zero chunks, and
  // FR-15's deletion removes the material for good, so "ask again for an answer from
  // the current material" — which this string said until the 27 September audit found
  // it shipping in the bundle — is false on two of the four paths that reach the state.
  // tests/askReopened.test.jsx fails when the two copies drift, as tests/ask.test.jsx
  // does for NO_ANSWER_MESSAGE (D-61's gap 13).
  provenanceRemovedFallback:
    'The citations for this answer are no longer on record, so the answer cannot be shown. You can ask the question again.',
  // FR-12: "Any partially related items found are offered, clearly labelled as
  // partial matches." These arrive on the ask reply as `partial_matches`: the items
  // its own permission-scoped, ranked candidates found, whatever they scored. They
  // are offered as links to sources and never as answer content, which is why the
  // reply carries no passage text for them and nothing here shows a snippet.
  partialMatchesHeading: 'Partial matches',
  partialMatchesIntro:
    'These items are related to your question. They are not an answer and nothing in them was cited — open one to read it yourself.',

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
  // **The promise is qualified rather than dropped, because it was not true as
  // written** (Stage 4 item 1c). "Your previous conversations are kept" full stop
  // was read by a user as "everything on this screen will still be here", and an
  // answer's citations do not survive a reprocess, a re-index or FR-15's deletion
  // of the material they came from: since D-67 each survives only as a record
  // whose chunk is NULL, which no reader is shown. The thread, the questions and
  // the answers that still have their sources are kept, which is what it now says.
  newTopicHint:
    'Clears the thread on screen and begins a new conversation. Your previous conversations are kept, though an answer whose sources have left the record can no longer be shown.',
  threadEmpty: 'Ask a question to start this conversation. Follow-up questions can refer back to it.',
  threadNew: 'New topic. Your first question will start a new conversation.',

  /* ---- Home, for a visitor who is not signed in ------------------------- */
  // A signed-in user never sees this: the home route sends them to their dashboard.
  homeHeading: 'Welcome',
  homeIntro:
    'Search and ask questions of your organisation’s documents and meeting transcripts. Every answer cites the material it came from.',

  /* ---- FR-14 dashboard --------------------------------------------------- */
  // FR-14: the platform's entry point after login. "It exists to orient the user
  // rather than to hold functionality of its own: each panel is a route into the
  // module that owns it."
  dashboardHeading: 'Dashboard',
  dashboardIntro: 'What is new in the material you can see. Each panel heading opens its full view.',
  dashboardFiltersLabel: 'Dashboard filters',
  dashboardDateRange: 'Date range',
  // D-70: each type filters on its own date. Said here because "the last month"
  // means something different for each panel, and a reader cannot see that.
  dashboardDateRangeHint:
    'Documents by the date they were uploaded, meetings by the date they were held, and your questions by the date you asked them. Both dates are included.',
  dashboardDateFrom: 'From',
  dashboardDateTo: 'To',
  dashboardDepartment: 'Department',
  dashboardAllDepartments: 'All departments',
  // D-70: only documents carry a department, so the filter narrows the recent
  // documents and the documents figure and nothing else, and the screen says so
  // next to the control rather than leaving the other panels to look ignored.
  dashboardDepartmentHint:
    'Applies to documents only. Meetings and questions have no department, so it does not narrow them.',
  dashboardApplyFilters: 'Apply filters',
  dashboardClearFilters: 'Clear filters',
  // Refused before the request is sent. The server refuses the same range with a
  // 400 under `date_to` in the same words, so whichever side refuses it, the user
  // reads one sentence in one place.
  dashboardRangeInverted: 'The end date must be on or after the start date.',
  // The 400 whose message is already under the control it concerns.
  dashboardCheckFilters: 'Check the highlighted filter and try again.',
  // The active filters, read from the reply's `filters` — what the server applied,
  // not what the form holds (D-70: "the screen shows the active range").
  dashboardActiveDates: 'Dates shown:',
  dashboardActiveDepartment: 'Department:',
  dashboardAllDates: 'All dates',
  dashboardRangeBetween: (from, to) => `${from} to ${to}`,
  dashboardRangeFrom: (from) => `From ${from}`,
  dashboardRangeUntil: (to) => `Up to ${to}`,
  dashboardDepartmentApplied: (department) => `${department} (documents only)`,
  dashboardLoadFailed: 'Could not load the dashboard',
  // A panel's state when the one request failed. Plain text: the failure itself
  // is announced once, above the panels, rather than four times.
  dashboardPanelUnavailable: 'Not available. See the message above the panels.',
  dashboardDocumentsHeading: 'Recent documents',
  dashboardMeetingsHeading: 'Recent meetings',
  dashboardTotalsHeading: 'Indexed items',
  // D-68: the caller's own questions, and the question only.
  dashboardQuestionsHeading: 'Your recent questions',
  dashboardLoadingDocuments: 'Loading recent documents…',
  dashboardLoadingMeetings: 'Loading recent meetings…',
  dashboardLoadingTotals: 'Loading indexed totals…',
  dashboardLoadingQuestions: 'Loading your recent questions…',
  // Empty is an ordinary state, and it says nothing about material outside the
  // caller's scope: the screen is not told of any (CLAUDE.md §6, invariant 1).
  dashboardNoDocuments: 'No documents to show.',
  dashboardNoMeetings: 'No meeting transcripts to show.',
  dashboardNoQuestions: 'No questions to show. Questions you ask appear here.',
  dashboardTotalsDocuments: 'Documents',
  dashboardTotalsMeetings: 'Meetings',
  dashboardTotalsSum: 'Total',
  // D-70: the total counts status "Indexed" only, by type, after the filters.
  dashboardTotalsHint: 'Documents and meetings whose status is Indexed, within the active filters.',
  dashboardUploaded: 'Uploaded',
  dashboardHeld: 'Held',
  dashboardAsked: 'Asked',

  /* ---- FR-19 knowledge-gap log (NIT3004, Objective 06) ------------------ */
  // FR-19: "A list, visible to Administrators, of questions the system could not
  // answer and searches returning no results, grouped by subject with an
  // occurrence count and the ability to mark an entry as addressed." The screen
  // (src/pages/KnowledgeGaps.jsx) and FR-14's panel show what an entry carries and
  // nothing else. No payload names who asked, their role, or why a question was
  // left out of the log, and none counts what was left out (D-107, D-108), so no
  // sentence here mentions any of them or implies that they exist.
  // The page heading, the navigation link and the dashboard panel's heading: the
  // link and the panel name the screen they open.
  gapsHeading: 'Knowledge gaps',
  // D-107: `subject` is the first member's wording, verbatim, and no model writes it.
  gapsIntro:
    'Questions the knowledge base could not answer and searches that returned no results, grouped by subject. ' +
    'Each entry is named by the first question or search in it, worded as it was typed, and counts how many times its subject came up. ' +
    'Mark an entry addressed once the knowledge base covers it.',
  gapsListHeading: 'Entries',
  loadingGaps: 'Loading the knowledge-gap log…',
  gapsLoadFailed: 'Could not load the knowledge-gap log',
  // The 200 with an empty list: before the first cycle, or when nothing has gone
  // unanswered since.
  noGaps: 'No knowledge gaps have been recorded.',
  // The server's order, which the screen keeps (docs/api-contract.md).
  gapsTableCaption: 'Knowledge gaps: open entries first, the most frequent at the top, then addressed entries.',
  gapsColumnSubject: 'Subject',
  gapsColumnOccurrences: 'Occurrences',
  gapsColumnStatus: 'Status',
  gapsColumnFirstSeen: 'First seen',
  gapsColumnLastSeen: 'Last seen',
  gapsColumnAction: 'Action',
  // One action per entry: "Mark addressed" on an Open entry, "Reopen" on an
  // Addressed one (PATCH's two values). A column of buttons all named "Mark
  // addressed" names nothing to someone moving between controls, so each one's
  // accessible name adds its entry, after the visible words (WCAG 2.1 SC 2.4.6,
  // SC 2.5.3).
  gapMarkAddressed: 'Mark addressed',
  gapReopen: 'Reopen',
  gapMarkAddressedLabel: (subject) => `Mark addressed: ${subject}`,
  gapReopenLabel: (subject) => `Reopen: ${subject}`,
  gapUpdateFailed: 'Could not change the entry',
  // The PATCH 404: the entry is gone, so the list on screen is out of date and is
  // read again.
  gapNotFound: 'That entry no longer exists. The list has been reloaded.',
  // A 403 on a change or on a cycle: the role does not hold review_knowledge_gaps
  // now, whatever it held when the list was read. Every action is withdrawn.
  gapsNotPermitted:
    'Your role may not review the knowledge-gap log, so its entries cannot be changed and the aggregation cannot be run.',
  // "Run aggregation now" runs one cycle synchronously (D-107). The hint does not
  // promise a schedule: whether one is set up is the deployment's, not the screen's.
  gapsCycleHeading: 'Aggregation',
  gapsCycleHint:
    'Questions and searches are added to the log when the aggregation runs. Run it now to add the ones recorded since it last ran.',
  gapsCycleRun: 'Run aggregation now',
  gapsCycleRunning: 'Running aggregation…',
  // Announced as well as shown while the cycle runs: it embeds every new question
  // and search, so it is not instant.
  gapsCycleWait: 'Running the aggregation. This can take a minute.',
  // The 201 in words, from the four counts it carries and no others. Its two
  // "added" counts are the rows that entered the log (the contract), so nothing
  // here says how many were read. When any of the four is missing, only
  // `gapsCycleDone` is said, so no number appears that the reply did not carry.
  gapsCycleDone: 'Aggregation finished.',
  gapsCycleQuestions: (count) =>
    count === 1 ? '1 question that could not be answered' : `${count} questions that could not be answered`,
  gapsCycleSearches: (count) =>
    count === 1 ? '1 search that returned no results' : `${count} searches that returned no results`,
  gapsCycleAdded: (questions, searches) => `Added to the log: ${questions} and ${searches}.`,
  gapsCycleCreated: (count) => (count === 1 ? '1 new entry started' : `${count} new entries started`),
  gapsCycleUpdated: (count) => (count === 1 ? '1 existing entry updated' : `${count} existing entries updated`),
  gapsCycleEntries: (created, updated) => `In the list: ${created} and ${updated}.`,
  gapsCycleFailed: 'Could not run the aggregation',
  // The 503 (NFR-19), after the client's own 503 sentence: the cycle rolled back.
  gapsCycleNotRun: 'No aggregation ran and nothing in the log was changed.',
  gapOccurrences: (count) => (count === 1 ? '1 occurrence' : `${count} occurrences`),
  // FR-14's panel (D-69, closed by D-107). Present only when the payload carries
  // `knowledge_gaps`; there is no copy for its absence, because nothing is shown.
  dashboardGapsOpen: 'Open entries',
  dashboardLoadingGaps: 'Loading knowledge gaps…',
  dashboardNoGaps: 'No open entries to show.',
  // The contract: the dashboard's filters narrow neither the count nor the list.
  dashboardGapsNote: 'The open entries that came up most often. The filters above do not apply to this panel.',
}
