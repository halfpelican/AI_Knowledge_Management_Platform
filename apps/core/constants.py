"""Tuned constants and fixed vocabularies for the platform.

CLAUDE.md section 5 constants and the docs/schema-v1.md section 3 vocabularies live
here and nowhere else. Application code imports the name; it never restates the
value. Values marked PROVISIONAL are placeholders that a named later step settles;
change them in this one place when that step runs.
"""

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

# --- Account lockout (FR-03, NIT3004) ------------------------------------------------
LOCKOUT_THRESHOLD = 5
LOCKOUT_DURATION = timedelta(minutes=15)

# --- No-answer response (FR-12; CLAUDE.md invariants 6 and 7) ------------------------
# PROVISIONAL: the proposal's exact wording is not available on this machine;
# replace it with the proposal's text when the coordinator has it. Defined once.
NO_ANSWER_MESSAGE = "No answer could be found in the material you have access to."

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
