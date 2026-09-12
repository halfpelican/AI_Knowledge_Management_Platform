"""Tuned constants for the platform: CLAUDE.md section 5.

Every value here lives here and nowhere else. Application code imports the name; it
never restates the number. Values marked PROVISIONAL are placeholders that a named
later step settles; change them in this one place when that step runs.
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

# --- Resilience (NFR-19, NFR-20) ----------------------------------------------------
# Total attempts, not retries: one attempt plus the two retries CLAUDE.md section 5
# names, after which the view answers 503 with the NFR-19 notice.
MAXIMUM_GENERATION_ATTEMPTS = 3
# Same reasoning: one attempt plus two retries, after which the item is flagged.
MAXIMUM_EMBED_ATTEMPTS = 3

# --- Question bounds (FR-12, FR-13), in characters -----------------------------------
MINIMUM_QUESTION_LENGTH = 10
MAXIMUM_QUESTION_LENGTH = 500

# --- Ingestion (FR-08, FR-09) -------------------------------------------------------
# PROVISIONAL: extracted text shorter than this, in characters, is marked
# "insufficient content" and not embedded. The proposal's value is not available on
# this machine; replace it with the proposal's number when the coordinator has it.
MINIMUM_CONTENT_LENGTH = 200

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB

# Lower-case file extensions accepted for upload (FR-08). Callers lower-case the
# extension before testing membership. The content signature is checked separately;
# the extension alone admits nothing.
ACCEPTED_FORMATS = frozenset({"pdf", "docx", "doc", "xlsx", "xls", "txt"})

# --- Account lockout (FR-03, NIT3004) ------------------------------------------------
LOCKOUT_THRESHOLD = 5
LOCKOUT_DURATION = timedelta(minutes=15)

# --- No-answer response (FR-12; CLAUDE.md invariants 4 and 5) ------------------------
# PROVISIONAL: the proposal's exact wording is not available on this machine;
# replace it with the proposal's text when the coordinator has it. Defined once.
NO_ANSWER_MESSAGE = "No answer could be found in the material you have access to."
