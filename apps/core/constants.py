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
DOCUMENT_STATUS_VALUES = ("Processing", "Extraction failed", "Insufficient content",
                          "Indexing failed", "Partially indexed", "Indexed")
# Named so ingestion never spells a status as a literal and a typo is an
# ImportError rather than a row nothing can filter on.
(DOCUMENT_PROCESSING, DOCUMENT_EXTRACTION_FAILED, DOCUMENT_INSUFFICIENT_CONTENT,
 DOCUMENT_INDEXING_FAILED, DOCUMENT_PARTIALLY_INDEXED, DOCUMENT_INDEXED) = DOCUMENT_STATUS_VALUES

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
