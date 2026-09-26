"""Tuned constants and fixed vocabularies for the platform.

CLAUDE.md section 5 constants and the docs/schema-v1.md section 3 vocabularies live
here and nowhere else. Application code imports the name; it never restates the
value. Values marked PROVISIONAL are placeholders that a named later step settles;
change them in this one place when that step runs.
"""

import string
from datetime import timedelta

# --- Chunking (FR-08), in tokens ---------------------------------------------------
# Overlap must stay below size or the chunking loop cannot advance.
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

# Most chunks one document or transcript may produce before ingestion refuses to index
# it (Stage 4 item 12a). Not a size limit — MAX_UPLOAD_BYTES is that — but a ceiling on
# the WORK one synchronous request may commit itself to.
#
# **The measurement.** 2.4 MB of extracted text yields 1,111 chunks, so a chunk costs
# about 2.2 KB of text. A 50 MB TXT at MAX_UPLOAD_BYTES therefore extrapolates to
# ~23,300 chunks, and every one of them is a SEPARATE, SEQUENTIAL embed call to the NPU
# inside one ``transaction.atomic()`` block in one synchronous request — a request
# holding a worker, a database transaction and the NPU for as long as it takes.
#
# **Why 1,000, against the Objective 02 figures.** Objective 02's verification on
# 2 October requires 20 documents and a 20-page file ingested in under 60 seconds. A
# 20-page document is roughly 11,000 whitespace tokens, which at CHUNK_SIZE 500 with
# CHUNK_OVERLAP 50 is about 25 chunks — so the cap sits about FORTY TIMES above the
# largest file Objective 02 names, and cannot interfere with it. In the other direction
# it is ~2.2 MB of extracted text, about 900 pages: larger than any document this
# corpus holds, and 23 times less work than the 50 MB worst case. Round, so it reads as
# a policy rather than as a measurement of one machine.
#
# **What the cap is and is not.** It is not a promise that a document AT the cap is fast
# — 1,000 sequential embed calls is minutes, not seconds. It is the point at which the
# platform refuses the work instead of attempting it, and the refusal is decided after
# chunking and BEFORE the first embed call, so a rejected file costs extraction and
# chunking (in-process, fast) and zero NPU time. Objective 02 protection first, an
# availability measure second.
MAXIMUM_CHUNKS_PER_SOURCE = 1000

# --- Retrieval (FR-11, FR-12) -------------------------------------------------------
# Candidate passages fetched per query, after permission filtering. Tuned in Stage 4.
TOP_K = 25

# Cosine-similarity floor for admitting a passage. Measured in Stage 4 step 0
# against the placeholder corpus; see docs/flm-baseline.md. Provisional — the
# corpus is 6 chunks and the value moves with the corpus and the embedding model.
RELEVANCE_THRESHOLD = 0.3

# PROVISIONAL: ceiling on grounding-context tokens per generation call. Tuned in
# Stage 4 once the prompt and the model's context window are measured.
MAXIMUM_CONTEXT_TOKENS = 4000

# --- Resilience (NFR-19, NFR-20; docs/decisions.md D-19) ----------------------------
# Total attempts, not retries: one initial attempt plus two retries, confirmed as
# the uniform policy in D-19. After the last attempt the view answers 503 with the
# NFR-19 notice.
MAXIMUM_GENERATION_ATTEMPTS = 3
# Same policy: one attempt plus two retries, after which the item is flagged.
MAXIMUM_EMBED_ATTEMPTS = 3
# Same policy for classification (FR-10, NIT3004). Named here now so the retry
# policy is uniform across every AI call, not so anything uses it before Stage 6.
MAXIMUM_CLASSIFY_ATTEMPTS = 3

# --- Question bounds (FR-12, FR-13), in characters -----------------------------------
MINIMUM_QUESTION_LENGTH = 10
MAXIMUM_QUESTION_LENGTH = 500

# --- Conversation context (FR-13), in turns -------------------------------------------
# How many earlier turns of a conversation are folded into a follow-up question.
# FR-13 Validation: context "is truncated to a maximum number of prior turns to control
# prompt size and cost". Three, chosen for a 4B model (gemma3:4b) against the 4000-token
# MAXIMUM_CONTEXT_TOKENS ceiling above, which the retrieved passages also draw on: the
# prior questions compete with the grounding material for that budget, and passages are
# the only thing an answer can be cited from, so the history gets the smaller share.
# A turn costs ONE question here, never a question and an answer — prior ANSWERS are
# never folded in, because no model-generated text may re-enter a prompt
# (apps/retrieval/conversation.py argues it).
MAXIMUM_CONVERSATION_TURNS = 3

# The floor on FR-12's OTHER path, the keyword search field, also in characters. FR-12
# Validation words it client-side — "queries shorter than two characters are rejected
# client-side" — and apps/retrieval/search.py enforces the same number on the server as
# well, because a browser check is a courtesy to the person typing and the server check
# is the rule (CLAUDE.md invariant 4). Two characters exactly, as the clause words it, so
# the two checks agree and nobody is refused by one and accepted by the other. It lives
# beside the question bounds because it is the same family of validation constant on the
# same requirement, not because the two paths share a bound: they do not, and a search
# term is not a question.
MINIMUM_SEARCH_LENGTH = 2

# --- Ingestion (FR-08, FR-09) -------------------------------------------------------
# Extracted text shorter than this is marked "Insufficient content" and is not
# embedded: a fragment produces an unreliable vector that matches unpredictably and
# pollutes every later search. Measured in TOKENS, not characters — the proposal's
# section 7.8 tests `lengthInTokens(plainText) < MINIMUM_CONTENT_LENGTH`, and a
# token here is a whitespace-delimited word (docs/decisions.md D-31). Section 7.0
# marks the value "To be tuned"; 50 tokens is roughly two sentences, set
# permissively because short memos and brief FR-09 transcripts are legitimate.
MINIMUM_CONTENT_LENGTH = 50

# The proposal's section 7.0 names this MAXIMUM_UPLOAD_SIZE; CLAUDE.md section 5
# names it MAX_UPLOAD_BYTES, and the byte unit is in the name here. Enforced before
# the file is read into memory (FR-08 Validation).
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB

# Formats admitted at upload, established from the file's CONTENT (FR-08:
# "confirmed by inspecting the file signature rather than the extension alone").
# Exactly four, per docs/decisions.md D-15: legacy DOC and XLS need an external
# binary to extract and would always be answered 415, so they are not accepted.
# These are also the Documents.file_type values.
ACCEPTED_FORMATS = frozenset({"pdf", "docx", "xlsx", "txt"})

# Filename suffixes the interface offers and checks before transfer (FR-08
# Front-End; proposal section 7.1). Deliberately distinct from ACCEPTED_FORMATS,
# since an extension is a claim and a signature is evidence: this set gates the
# upload control's own convenience check and admits nothing on the server.
ACCEPTED_EXTENSIONS = frozenset({f".{name}" for name in ACCEPTED_FORMATS})

# Leading bytes read to identify a file's format: enough to carry the longest
# signature in use (proposal section 7.0).
SIGNATURE_LENGTH = 8

# Byte patterns by which each accepted format is recognised (proposal section 7.3).
# Fixed by the format specifications rather than tunable. PDF is decisive on its own;
# DOCX and XLSX share the ZIP container signature and are separated afterwards by the
# archive's own declared content type. TXT has no signature of its own, which is why
# it is the last resort rather than the default.
PDF_SIGNATURE = b"%PDF-"
ZIP_SIGNATURE = b"PK\x03\x04"
FORMAT_SIGNATURES = {"pdf": PDF_SIGNATURE, "zip-container": ZIP_SIGNATURE}
WORD_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
EXCEL_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# --- Password complexity (FR-01) -----------------------------------------------------
# FR-01 Server-End, Validation rules: "Password must meet complexity rules (min 8
# chars, 1 uppercase, 1 number, 1 special character)." The four conditions are
# enforced by apps.accounts.validators.ComplexityValidator; Django's
# MinimumLengthValidator is configured from PASSWORD_MINIMUM_LENGTH in
# config/settings.py so the two statements of the length cannot drift.
PASSWORD_MINIMUM_LENGTH = 8
PASSWORD_MINIMUM_UPPERCASE = 1
PASSWORD_MINIMUM_DIGITS = 1
PASSWORD_MINIMUM_SPECIAL = 1
# What counts as a "special character": ASCII punctuation, which is the set the
# registration form's strength meter shows. Whitespace is not special; a space in
# a passphrase must not stand in for punctuation.
PASSWORD_SPECIAL_CHARACTERS = frozenset(string.punctuation)

# --- Account lockout (FR-02 Server-End; FR-03, NIT3004) -------------------------------
# FR-02 Business Logic: "Failed attempts increment a counter; five consecutive
# failures lock the account for 15 minutes", and FR-02 Responses: "403 forbidden if
# account is locked". Enforcement is therefore FR-02's, not FR-03's; FR-03 adds the
# interface (remaining-attempt warning, countdown) and the administrator release.
# Configuration values rather than literals, as FR-03 Business logic requires.
LOCKOUT_THRESHOLD = 5
LOCKOUT_DURATION = timedelta(minutes=15)
# How many failed attempts in total may still be answered with the distinct
# "account is locked" notice. Past this, a locked account answers every attempt with
# the generic message, right password or wrong. Without a ceiling the lock withheld
# the session but not the answer: guessing during the window was unlimited and each
# response said whether that guess was correct (D-26). Twice the threshold leaves a
# user who mistypes once after locking themselves out with the useful message.
LOCKOUT_NOTICE_CEILING = LOCKOUT_THRESHOLD * 2

# Requests per minute allowed to the two anonymous authentication endpoints, per
# client address. Lockout without a throttle is a denial-of-service primitive:
# registration's mandatory 409 identifies a registered address and five requests
# then lock it, so every account in the organisation can be held locked by anyone
# (D-26). Generous enough that a person typing a password never meets it.
AUTHENTICATION_THROTTLE_RATE = "20/min"

# --- No-answer response (FR-12; CLAUDE.md invariants 6 and 7) ------------------------
# replace it with the proposal's text when the coordinator has it. Defined once.
NO_ANSWER_MESSAGE = "This question cannot be answered from the available knowledge base."

# --- Fixed vocabularies (docs/schema-v1.md section 3) --------------------------------
# Status values are fixed rather than free text so a status can be filtered on and
# its meaning does not drift. Every model ``choices=`` is derived from these tuples.

# The proposal's section 7.0 set, which supersedes schema v1's five values
# (docs/decisions.md D-28). Sections 7.7 and 7.8 set the last three directly, and
# the superseded set could not express a document whose chunks partly embedded.
# "Partially indexed" and "Indexing failed" are terminal, committed outcomes inside
# the one NFR-21 transaction, not half-written records: an unexpected failure still
# rolls the whole ingestion back (CLAUDE.md invariant 9).
#
# **The seventh value, "Too large to index" (Stage 4 item 12b).** Added beside
# "Insufficient content" rather than appended, because it belongs to the same kind: this
# vocabulary already separates REFUSED BEFORE ATTEMPTING, on a property of the content
# ("Insufficient content"), from ATTEMPTED AND FAILED ("Indexing failed"). A document over
# MAXIMUM_CHUNKS_PER_SOURCE is the first kind and had no term, so item 12a put it on
# "Indexing failed", which says an attempt was made and every chunk failed — and no attempt
# was made at all. This COMPLETES AN EXISTING DISTINCTION rather than introducing one, which
# is the same argument D-28 made one state earlier when five values could not express a
# document whose chunks partly embedded.
#
# The difference is user-visible, which is why the message was not enough: FR-08 offers
# "Processing failed. Please try again" against a document that did not index, and a
# reprocess of an over-cap document fails identically every time, because nothing about the
# file has changed. D-32's retry cases MAY succeed — a provider outage does — and this one
# cannot; worse, D-32 re-runs ingestion on the stored original, so every attempt redoes
# extraction and chunking in full before failing at the identical point.
#
# The proposal is SILENT here, not contrary: MAXIMUM_CHUNKS_PER_SOURCE was settled this week
# and the proposal predates it. The name says what happened and does not imply an attempt —
# not a variant of "failed".
DOCUMENT_STATUS_VALUES = ("Processing", "Extraction failed", "Insufficient content",
                          "Too large to index", "Indexing failed", "Partially indexed",
                          "Indexed")
# Named so ingestion never spells a status as a literal and a typo is an
# ImportError rather than a row nothing can filter on.
(DOCUMENT_PROCESSING, DOCUMENT_EXTRACTION_FAILED, DOCUMENT_INSUFFICIENT_CONTENT,
 DOCUMENT_TOO_LARGE_TO_INDEX, DOCUMENT_INDEXING_FAILED, DOCUMENT_PARTIALLY_INDEXED,
 DOCUMENT_INDEXED) = DOCUMENT_STATUS_VALUES

# The proposal defines no status column on Meetings at all, only FR-09's CRUD line
# "Meetings (Create, Read, Update status)", so schema v1's three values stand: there
# is nothing for them to contradict (D-28).
MEETING_STATUS_VALUES  = ("Received", "Indexed", "Processing failed")
(MEETING_RECEIVED, MEETING_INDEXED, MEETING_PROCESSING_FAILED) = MEETING_STATUS_VALUES
CLASSIFICATION_DIMENSIONS = ("Department", "Project", "Process", "Topic")
SOURCE_TYPES = ("document", "meeting")
NO_ANSWER_REASONS = ("no_relevant_passage",     # nothing above RELEVANCE_THRESHOLD
                     "no_statement_verified")   # retrieved, but verification stripped all
# Named for the same reason as the status values above, and it matters more here:
# CLAUDE.md invariant 7 turns on these two staying distinguishable, and a reason
# misspelt as a literal would collapse the two paths into one unreadable signal.
(NO_RELEVANT_PASSAGE, NO_STATEMENT_VERIFIED) = NO_ANSWER_REASONS

# A new record starts in the first value of its vocabulary.
DEFAULT_DOCUMENT_STATUS = DOCUMENT_STATUS_VALUES[0]
DEFAULT_MEETING_STATUS = MEETING_STATUS_VALUES[0]

# The two roles (FR-05). Administrator generalises Employee; registration defaults
# to Employee (docs/schema-v1.md, Users.role_id).
ROLE_NAMES = ("Employee", "Administrator")
EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME = ROLE_NAMES

# Permission codes (FR-05, FR-06; docs/decisions.md D-14). Held against roles in
# role_permissions, seeded by accounts migrations 0003 and 0004; a test asserts the
# constants and the seed agree.
MANAGE_ROLES_PERMISSION = "manage_roles"
# FR-08's section 7.2 validateUpload() opens with hasContributePermission(), before
# the signature, size and title checks, because it is the cheapest rejection and the
# user's role may have changed during a transfer of up to 50 MB. Held by BOTH roles
# (docs/decisions.md D-30), so in the shipped seed it refuses nobody: it is the
# enforcement point the clause requires, not a demonstrable restriction. The
# proposal's knowledgeArea argument is dropped — schema v1 models no knowledge area.
CONTRIBUTE_CONTENT_PERMISSION = "contribute_content"

# Provenance of a ContentTags row (FR-10, FR-15).
TAG_APPLIED_BY_VALUES = ("ai", "user")

# --- Sessions (FR-04, docs/decisions.md D-10) -----------------------------------------
# Inactivity expiry; config/settings.py derives SESSION_COOKIE_AGE from it.
SESSION_INACTIVITY_MINUTES = 60
