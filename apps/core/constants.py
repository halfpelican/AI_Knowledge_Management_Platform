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

# --- PDF extraction bounds (FR-08, FR-09; docs/decisions.md D-81) ---------------------
# Four bounds on the work pypdf may do for one PDF (two per-stream caps, the page cap and
# the operator budget), plus the text ceiling, which is MAXIMUM_CHUNKS_PER_SOURCE above
# read during extraction (apps/ingestion/extraction.py). Every one of them that refuses a
# document lands it on "Too large to index" (D-51's status).

# Most bytes one PDF stream may decompress to. apps/ingestion/extraction.py sets every
# pypdf ``Configuration`` field named ``*_maximum_output_length`` to this, with
# ``pypdf.apply_configuration`` around the reader and the page loop, so it is scoped to
# the extracting thread (D-81 item 1). pypdf 6.19.0's own default is 75,000,000.
#
# **Why about 10 MB.** pypdf's memory while parsing a content stream is about 67 times
# its decoded size (D-81's measurement: a 10 MB stream, +671 MB), so this bounds one page
# near 700 MB, where the 75 MB default allowed roughly 5 GB. It is far above a real page:
# the corpus PDFs are 3-38 KB files, and a vector-heavy drawing page is a few MB decoded.
# A 2 MB cap failed the measured 10 MB page in 0.01 s (D-81), and this one fails anything
# over it as fast, because decompression stops at the cap before parsing starts.
#
# Measured on this laptop, 21 October 2026, pypdf 6.19.0, Python 3.12: one page whose
# single stream decodes to exactly this many bytes of ``q Q`` (5,000,000 operators, a
# 10 KB file) took 14.9-15.7 s to extract over three runs. That is the "one parse at the
# per-stream cap" in PDF_MAXIMUM_OPERATORS' worst case below.
PDF_MAXIMUM_STREAM_BYTES = 10_000_000

# Most bytes one PDF stream may occupy AS STORED in the file. apps/ingestion/extraction.py
# sets pypdf's ``maximum_declared_stream_length`` to this in the same
# ``apply_configuration`` call as PDF_MAXIMUM_STREAM_BYTES. pypdf 6.19.0's default is
# 75,000,000. Settled by the user, 26 October 2026, closing the gap the first build of D-81
# left open.
#
# **Its own constant, because stored size and decoded size are different limits.** The
# decompression caps above never see a stream stored without a filter, since nothing is
# decompressed, so an uncompressed content stream escaped the 10 MB cap and was bounded
# only by pypdf's 75 MB default and the 50 MB upload ceiling. This limit reads the stored
# length, which for an uncompressed stream is its decoded length too.
#
# **What the user measured, pypdf 6.19.0, with this limit at 10 MB:**
# - a 12 MB image drawn on a page did NOT fail the document: pypdf skipped it, logged
#   "Impossible to decode XFormObject", and the page's text still came out;
# - a 12 MB embedded font program that the page's text uses DID fail, with
#   LimitReachedError, with or without /ToUnicode;
# - pypdf reads every font program a page uses but never decodes it during extraction (a
#   Flate font decoding to 12 MB passed under the 10 MB decompression cap), so for a font
#   only the stored size counts.
#
# **Why 20 MB.** A PDF that embeds a whole CJK font rather than a subset can store more than
# 10 MB of font program, and a 10 MB limit would refuse that document for its font. 20 MB
# admits those fonts and still bounds an uncompressed content stream well under the 50 MB
# upload ceiling: about 1.3 GB of parser memory at the measured ~67 times.
#
# **What it refuses and what it skips.** pypdf swallows an over-limit XObject, image or form,
# and carries on, so those are SKIPPED rather than refused: the page's other text is still
# extracted. Only a page content stream or a font program over it reaches "Too large to
# index", with the per-stream message.
PDF_MAXIMUM_STORED_STREAM_BYTES = 20_000_000

# Most pages a PDF may have, counted with ``len(reader.pages)`` before any page is parsed
# (D-81 item 2). pypdf counts the page tree it walks, not the /Count the file declares, so
# a tree that under-declares its pages is still counted in full. 2,000 is well above the
# roughly 820 pages of text MAXIMUM_CHUNKS_PER_SOURCE allows, so a document refused here
# could never have been indexed whole.
MAXIMUM_PDF_PAGES = 2000

# Most content-stream operators extraction will process across the WHOLE document, counted
# by ``extract_text(visitor_operand_before=...)``, which also sees the operators inside form
# XObjects (D-81 item 3). It bounds the repeated parsing a per-stream cap cannot: pages that
# share one stream, and a form drawn many times, each parse their content again.
#
# **The measurement**, on this laptop, 21 October 2026, pypdf 6.19.0, Python 3.12, while
# other test suites were running on the same machine: a counting visitor, and the wall time
# of the whole extraction (reader, parse and processing), three runs per shape.
#
#   ``q Q`` on one page, 1M operators             250,570 - 480,564 operators/s
#   a form of 200k operators drawn 5 times        208,913 - 301,245 operators/s
#   one stream shared by 10 pages, 1M operators   215,299 - 349,260 operators/s
#   text lines (BT Tf Td Tj ET), one page          31,979 -  72,114 operators/s
#   ``1 0 0 1 0 0 cm`` on one page, 200k-400k      21,671 -  23,337 operators/s
#
# **The value** is 60 s at the slowest rate measured, 21,671 operators/s for ``cm``, which
# produces no text and so is never stopped by the text ceiling: 60 x 21,671 = 1,300,260,
# rounded to 1,300,000. The ``q Q`` shapes reach it in about 3-6 s. It is NOT set from the
# sandbox figure of 1.76 s per MB, which D-81 rules out.
#
# **The recorded worst case is about 75 s**: the budget at the slowest rate, about 60 s,
# plus one parse at PDF_MAXIMUM_STREAM_BYTES, about 15 s. The second term exists because a
# stream is parsed whole before the visitor sees its first operator, so the budget can stop
# the NEXT stream and never the one being parsed (D-81, "What this decision does not cover").
#
# **Legitimate documents should sit well below it, and this is an estimate, not a
# measurement.** pypdf calls the visitor once per operator, and a TJ array counts once however
# many words it holds, so a typical text page is a few hundred operators; the ~820 pages of
# text the text ceiling allows would be a few hundred thousand. No real large PDF was
# measured against it.
PDF_MAXIMUM_OPERATORS = 1_300_000

# --- Retrieval (FR-11, FR-12) -------------------------------------------------------
# Candidate passages fetched per query, after permission filtering. Tuned in Stage 4.
TOP_K = 25

# Cosine-similarity floor for admitting a passage (apps/retrieval/ranking.py admit(), ``>=``).
# Below it on every in-scope passage, the question takes no-answer path A and generation is
# never called (invariant 7a). It was 0.3 from D-37 (22 September 2026, a 6-chunk corpus).
# TUNED in step 7 phase 2c (8 November 2026) on corpus/objective-02/dev-set-v2.json, questions in
# users' wording, never on questions.json or threads.json (D-93), by the user's rule with a
# margin m = 0.006 fixed in advance (twice the query-vector drift D-40 recorded): decline the
# most no-answer runs WITH MARGIN (top in-scope score <= T - m, so path A and no generation)
# while every answerable run keeps its expected source WITH MARGIN (its best expected-source
# score >= T + m). On kmp_obj02_20261101 (43 chunks, FLM v0.9.39) the bound is u07's 0.280085
# - m = 0.274085, and only 1 of the 8 no-answer runs can be declined with margin
# (u30@Employee, top 0.199907): every T in [0.205907, 0.274085] declines it and keeps all 32.
# Its middle, 0.239996, rounded to the nearest four places, is 0.2400: 0.040093 above u30's
# 0.199907 and 0.040085 below u07's 0.280085. The other 7 no-answer runs (0.287538 to 0.487314)
# score above it and reach generation; path B is what declines them, when it does.
# This is LOWER than D-37's 0.3. Phase 2b's 0.4231, chosen on dev-set.json, whose questions
# share the documents' wording, put seven of the frozen set's answerable questions on path A
# (corpus/objective-02/runs/2026-11-08/after/); questions as users word them score lower
# (dev-set-v2's median wording overlap with the source is 0.33 against dev-set.json's 0.67).
# The frozen sets informed the decision to rebuild the dev set, so they no longer test this
# value independently (D-101's note). Re-tune with the corpus or the embedding model.
# The scores: corpus/objective-02/runs/2026-11-08/dev-set-v2.md.
RELEVANCE_THRESHOLD = 0.24

# Cosine-similarity floor for OFFERING an item as one of FR-12's partial matches beside a
# no-answer (D-56; apps/retrieval/partial_matches.py, ``>=``). An item is offered only if its
# best ranked passage reaches this. Before it, the five nearest were offered however weak, so
# a question the corpus cannot answer was shown five unrelated titles (D-93).
# TUNED in the same pass, on dev-set-v2.json and nothing else, by the same margin rule: the
# lowest value at least m above the highest-scoring partial match the real offer path gave any
# run that path A declines at the threshold, and at most RELEVANCE_THRESHOLD - m. The one such
# run is u30@Employee, whose best offer is D04 at 0.199907, so 0.205907, rounded UP to four
# places: 0.2060, 0.006093 above it and 0.0280 under the 0.2340 ceiling. It stays BELOW
# RELEVANCE_THRESHOLD, so path A offers items scoring in [0.2060, 0.2400), a band 0.0340 wide;
# on path B every admitted item clears it. It rests on ONE declined run.
PARTIAL_MATCH_FLOOR = 0.206

# PROVISIONAL: ceiling on grounding-context tokens per generation call. Tuned in
# Stage 4 once the prompt and the model's context window are measured.
MAXIMUM_CONTEXT_TOKENS = 4000

# The most statements one answer may hold (FR-12; step 7 phase 2a, 7 November 2026). The
# prompt asks for at most this many (apps/ai/prompting.py) and the schema enforces it
# (STATEMENT_LIST_SCHEMA's maxItems, apps/ai/schema.py): a reply with more is a schema
# violation, retried and never trimmed (invariant 10). The FIRST attempt asks for this many;
# an attempt after a reply that hit max_tokens or broke the cap asks for fewer
# (apps/ai/generation.py). Phase 1 saw every 503 come from a reply still listing statements
# at the 800-token ceiling (D-82's note of 7 November 2026).
# TUNED on corpus/objective-02/dev-set.json, never on questions.json or threads.json (D-93):
# zero ceiling hits and zero 503s first, then the best expected-answer match, then the
# smaller value on a tie. On 7 November 2026 (one pass of 31 runs each), 3 and 6 had zero
# of both; 4 and 5 had one 503 each, from malformed JSON. 6 matched 15 of 24 against 3's
# 13 of 24, so 6. The sweep is in corpus/objective-02/runs/2026-11-07/.
MAXIMUM_STATEMENTS = 6

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

# --- Dashboard (FR-14) ----------------------------------------------------------------
# How many items each of the dashboard's recent panels shows: recent documents, recent
# meetings and the caller's own recent questions (docs/decisions.md D-70). A presentation
# constant chosen by the build, not a tuned value: the dashboard orients the user and each
# panel links through to its module's full view, so five shows what is new without the
# panel becoming the list it links to.
DASHBOARD_RECENT_ITEMS = 5

# --- Document repository (FR-15) -------------------------------------------------------
# The columns FR-15's list view may be sorted by (docs/decisions.md D-72): its title, type,
# uploader, upload date and status, which are the five things FR-15 says the list shows. Each
# is accepted bare for ascending or with DESCENDING_SORT_PREFIX for descending, and the whole
# set is a fixed vocabulary read through a ChoiceField, never a column name taken from the
# request (D-65). ``uploaded_by`` sorts by the uploader's address, the value the list displays.
DOCUMENT_SORT_KEYS = ("title", "file_type", "uploaded_by", "uploaded_at", "status")
DESCENDING_SORT_PREFIX = "-"
DOCUMENT_SORT_VALUES = DOCUMENT_SORT_KEYS + tuple(
    f"{DESCENDING_SORT_PREFIX}{key}" for key in DOCUMENT_SORT_KEYS
)
# Newest first: the order GET /api/documents has always returned, so the browse route's
# default and the plain list agree (D-72).
DEFAULT_DOCUMENT_SORT = f"{DESCENDING_SORT_PREFIX}uploaded_at"

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
PDF_CONTENT_TYPE = "application/pdf"
# The signature admits a file as TXT only when its sample decodes as UTF-8, so the charset is
# stated rather than left for the browser to guess.
TEXT_CONTENT_TYPE = "text/plain; charset=utf-8"

# The Content-Type FR-15's download serves a stored original with, keyed by the format
# read_file_signature proved from its bytes at upload (Documents.file_type), never by its name
# (docs/decisions.md D-75: D-15's principle applied on the way out). One entry per accepted
# format; apps/core/tests/test_constants.py asserts the keys are exactly ACCEPTED_FORMATS.
DOWNLOAD_CONTENT_TYPES = {
    "pdf": PDF_CONTENT_TYPE,
    "docx": WORD_CONTENT_TYPE,
    "xlsx": EXCEL_CONTENT_TYPE,
    "txt": TEXT_CONTENT_TYPE,
}

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

# --- Per-user rate limits and the in-flight ask (docs/decisions.md D-79) -------------------
# Each rate is a DRF ScopedRateThrottle scope, passed through REST_FRAMEWORK's
# DEFAULT_THROTTLE_RATES as the auth rate above is, and counted per signed-in user rather than
# per address. A request is counted before its body is validated, so a rejected one counts too.
#
# POST /api/ask, scope "ask".
ASK_THROTTLE_RATE = "10/min"
# Scope "ingestion": one budget shared by POST /api/documents, POST /api/meetings and
# POST /api/documents/{id}/reprocess. A full Objective 02 run, about 31 requests, fits in an hour.
INGESTION_THROTTLE_RATE = "60/hour"
# POST /api/conversations, scope "conversation_create": the ask rate in a budget of its own, so
# creating a thread does not spend the ask budget (D-80).
CONVERSATION_CREATE_THROTTLE_RATE = ASK_THROTTLE_RATE

# How much longer than generation's worst case a user's in-flight ask slot is held before it
# expires on its own, in seconds. The slot's timeout is GENERATION_TIMEOUT_SECONDS times
# MAXIMUM_GENERATION_ATTEMPTS plus this (apps/api/ask_slot.py builds it; the product cannot be
# built here, because apps/ai/generation.py imports this module).
#
# The margin has to cover the question's embedding, which runs inside the slot. That call sets
# no timeout of its own: apps/ai/_openai_compat.py builds its client with none, so it inherits
# the openai client's default of 5 s to connect and 600 s to read. MAXIMUM_EMBED_ATTEMPTS of
# those is 1,815 s. The 60 s on top covers the database work either side. The two SDK figures
# are restated rather than imported, because nothing outside apps/ai/ may import the SDK
# (CLAUDE.md section 4); apps/api/tests/test_ask_in_flight.py compares them with the timeout of
# the client the provider actually builds, so an SDK change that lengthens it fails a test.
ASK_IN_FLIGHT_MARGIN_SECONDS = MAXIMUM_EMBED_ATTEMPTS * (5 + 600) + 60  # 1,875 s

# --- No-answer response (FR-12; CLAUDE.md invariants 6 and 7) ------------------------
# replace it with the proposal's text when the coordinator has it. Defined once.
NO_ANSWER_MESSAGE = "This question cannot be answered from the available knowledge base."

# What a STORED turn says when none of its citation rows still points at an existing chunk
# (Stage 4 item 1c; the condition restated by D-67, Stage 5 item 1a).
#
# **Not NO_ANSWER_MESSAGE, because that text would be false.** Both ``reprocess_document`` and
# ``manage.py reindex`` delete a source's chunks and write new ones with fresh identifiers, so
# every citation of the old ones loses its chunk while the material itself still exists. Until
# D-67 ``AnswerCitation.chunk`` was ``on_delete=CASCADE`` (D-12) and those citation rows were
# destroyed; since D-67 it is SET_NULL, the rows survive with ``chunk_id`` NULL and
# ``chunk_uuid`` kept for FR-12's traceability record, and the serializer reads a NULL-chunk
# row exactly as a destroyed one. A turn in that state was answered, and nothing about the
# knowledge base has stopped being able to answer it — so telling the reader their question
# "cannot be answered from the available knowledge base" is the interface stating something
# untrue about the corpus. ``apps/api/tests/test_fr12_traceability_survives_reprocess.py``
# records what happens to the rows.
#
# **What it may and may not say.** It says the answer's own sources are no longer on record.
# It does not mention permissions, withholding or restriction in any form: this state says
# nothing whatever about what the reader may see, and a re-scoped turn — a turn with a
# citation row whose chunk DOES exist but is no longer readable by this role — must stay
# indistinguishable from a never-answered one, which is invariant 1 and which
# ``ConversationTurnSerializer`` keeps by discriminating on whether a row still points at an
# existing chunk, before any scoping. No count of anything removed, for the same reason.
# Shown for a turn that WAS answered and none of whose AnswerCitation rows still points at a
# chunk. It is a second fixed text rather than a reuse of NO_ANSWER_MESSAGE, because that one
# says the question cannot be answered from the available knowledge base, which is a claim about
# the corpus and is not what happened here.
#
# The second sentence deliberately promises NOTHING about what asking again will return. An
# earlier version said "for an answer from the current material", and that was false on two of
# the FOUR paths that reach this state — an instance of the coverage rule in docs/decisions.md,
# which that file's table NAMES rather than numbers. This comment called it "the sixth" while the
# same commit's own subject called it "the seventh": an ordinal over a set the sentence does not
# list is the defect itself, so the ordinal is gone and the table is the list. (It also said
# "three" over a list of four until the fourth pass caught it: the same miscount, in the fix for
# the miscount.)
#
# WHAT REACHES THIS STATE, all four paths, because two of them make any promise about the
# corpus wrong:
#   1. manage.py reindex — the material is re-chunked and still indexed. Asking again works.
#   2. A SUCCESSFUL reprocess — same.
#   3. A reprocess that FAILS — reprocess_document deletes ExtractedContent and every chunk
#      before running the pipeline, and a decided failure is committed, so an FLM outage during
#      the retry leaves the document with ZERO chunks and "Indexing failed". Asking again returns
#      no-answer. This is reachable today, and it is reachable precisely when the retry button is
#      most likely to be pressed.
#   4. FR-15's permissioned deletion, Stage 5 — the material is gone for good. D-48's own
#      not-covered list names it; nothing in item 1c's material carried it forward.
PROVENANCE_REMOVED_MESSAGE = (
    "The citations for this answer are no longer on record, so the answer cannot be shown. "
    "You can ask the question again."
)

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
(DEPARTMENT_DIMENSION, PROJECT_DIMENSION, PROCESS_DIMENSION,
 TOPIC_DIMENSION) = CLASSIFICATION_DIMENSIONS
# The tag dimensions FR-15's browse and detail view read from ContentTags. Department is
# not among them: it is the documents.department column, the source FR-14's filter uses,
# and no Department tags are seeded (docs/decisions.md D-72, D-74).
REPOSITORY_TAG_DIMENSIONS = (PROJECT_DIMENSION, PROCESS_DIMENSION, TOPIC_DIMENSION)
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

# The role names whose content each role may read (FR-11, docs/decisions.md D-66).
# Administrator generalises Employee in scope as well as in permissions — the proposal's
# role model ("Employee <|-- Admin", each role adding capability to the one below) and
# docs/schema-v1.md's "Administrator generalises Employee". apps/retrieval/scoping.py
# admits a row when its visible_to_roles OVERLAPS these, so an Employee's scope is exactly
# what membership of "Employee" gave before, and an Administrator also reads everything
# marked for Employees. A role missing from this map reads nothing (scoping fails closed).
# This settles how scope is READ; what ingestion WRITES into visible_to_roles is D-29's.
EFFECTIVE_ROLES = {
    EMPLOYEE_ROLE_NAME: (EMPLOYEE_ROLE_NAME,),
    ADMINISTRATOR_ROLE_NAME: (ADMINISTRATOR_ROLE_NAME, EMPLOYEE_ROLE_NAME),
}

# Permission codes (FR-05, FR-06; docs/decisions.md D-14). Held against roles in
# role_permissions, seeded by accounts migrations 0003, 0004, 0005 and 0006; a test asserts
# the constants and the seed agree.
MANAGE_ROLES_PERMISSION = "manage_roles"
# FR-08's section 7.2 validateUpload() opens with hasContributePermission(), before
# the signature, size and title checks, because it is the cheapest rejection and the
# user's role may have changed during a transfer of up to 50 MB. Held by BOTH roles
# (docs/decisions.md D-30), so in the shipped seed it refuses nobody: it is the
# enforcement point the clause requires, not a demonstrable restriction. The
# proposal's knowledgeArea argument is dropped — schema v1 models no knowledge area.
CONTRIBUTE_CONTENT_PERMISSION = "contribute_content"
# FR-15 Server-End Validation: "the requesting user must hold manage_documents to delete".
# Held by Administrator only, seeded by accounts migration 0005 (docs/decisions.md D-73).
# There is no ownership rule: deletion is a role permission, and D-66 puts every
# Employee-only document in an Administrator's scope, so no document is undeletable.
MANAGE_DOCUMENTS_PERMISSION = "manage_documents"
# Deleting a meeting (docs/decisions.md D-99). NOT in the proposal: FR-09 gives Meetings Create,
# Read and Update status only, and FR-15's deletion covers documents. Added at the lead's request
# on 7 November 2026 as its own code rather than a reuse of manage_documents, so that granting
# one never grants the other. Held by Administrator only, seeded by accounts migration 0006.
# D-66 puts every Employee-only meeting in an Administrator's scope, so none is undeletable.
MANAGE_MEETINGS_PERMISSION = "manage_meetings"

# Provenance of a ContentTags row (FR-10, FR-15).
TAG_APPLIED_BY_VALUES = ("ai", "user")

# --- Sessions (FR-04, docs/decisions.md D-10) -----------------------------------------
# Inactivity expiry; config/settings.py derives SESSION_COOKIE_AGE from it.
SESSION_INACTIVITY_MINUTES = 60
