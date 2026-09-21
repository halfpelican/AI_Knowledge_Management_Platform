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
}
