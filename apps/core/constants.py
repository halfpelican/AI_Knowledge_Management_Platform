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

# PROVISIONAL: cosine-similarity floor for admitting a passage. Tuned in Stage 4
# step 0 against the fixture corpus; 0.5 is a placeholder, not a measured value.
RELEVANCE_THRESHOLD = 0.5

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

# --- Ingestion (FR-08, FR-09) -------------------------------------------------------
# PROVISIONAL: extracted text shorter than this, in characters, is marked
# "insufficient content" and not embedded. The proposal's value is not available on
# this machine; replace it with the proposal's number when the coordinator has it.
MINIMUM_CONTENT_LENGTH = 200

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB

# Lower-case file extensions accepted for upload (FR-08). Exactly four, per
# docs/decisions.md D-15: legacy DOC and XLS need an external binary to extract and
# would always be answered 415, so they are not accepted. Callers lower-case the
# extension before testing membership. The content signature is checked separately;
# the extension alone admits nothing.
ACCEPTED_FORMATS = frozenset({"pdf", "docx", "xlsx", "txt"})

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

DOCUMENT_STATUS_VALUES = ("Uploaded", "Extracting", "Indexed",
                          "Insufficient content", "Processing failed")
MEETING_STATUS_VALUES  = ("Received", "Indexed", "Processing failed")
CLASSIFICATION_DIMENSIONS = ("Department", "Project", "Process", "Topic")
SOURCE_TYPES = ("document", "meeting")
NO_ANSWER_REASONS = ("no_relevant_passage",     # nothing above RELEVANCE_THRESHOLD
                     "no_statement_verified")   # retrieved, but verification stripped all

# A new record starts in the first value of its vocabulary.
DEFAULT_DOCUMENT_STATUS = DOCUMENT_STATUS_VALUES[0]
DEFAULT_MEETING_STATUS = MEETING_STATUS_VALUES[0]

# The two roles (FR-05). Administrator generalises Employee; registration defaults
# to Employee (docs/schema-v1.md, Users.role_id).
ROLE_NAMES = ("Employee", "Administrator")
EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME = ROLE_NAMES

# Permission codes (FR-05, FR-06; docs/decisions.md D-14). Held against roles in
# role_permissions, seeded by accounts migration 0003; a test asserts the two agree.
MANAGE_ROLES_PERMISSION = "manage_roles"

# Provenance of a ContentTags row (FR-10, FR-15).
TAG_APPLIED_BY_VALUES = ("ai", "user")

# --- Sessions (FR-04, docs/decisions.md D-10) -----------------------------------------
# Inactivity expiry; config/settings.py derives SESSION_COOKIE_AGE from it.
SESSION_INACTIVITY_MINUTES = 60
