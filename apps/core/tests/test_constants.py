"""CLAUDE.md section 5 and docs/schema-v1.md section 3: every constant is defined once."""

from datetime import timedelta

import pytest

from apps.core import constants
from apps.core.models import VOCABULARY_MAX_LENGTH

SECTION_5_NAMES = [
    "CHUNK_SIZE",
    "CHUNK_OVERLAP",
    "TOP_K",
    "RELEVANCE_THRESHOLD",
    "MAXIMUM_CONTEXT_TOKENS",
    "MAXIMUM_GENERATION_ATTEMPTS",
    "MAXIMUM_EMBED_ATTEMPTS",
    "MAXIMUM_CLASSIFY_ATTEMPTS",
    "MAXIMUM_TRANSCRIBE_ATTEMPTS",
    "MINIMUM_QUESTION_LENGTH",
    "MAXIMUM_QUESTION_LENGTH",
    "MINIMUM_CONTENT_LENGTH",
    "MAX_UPLOAD_BYTES",
    "ACCEPTED_FORMATS",
    "LOCKOUT_THRESHOLD",
    "LOCKOUT_DURATION",
    "NO_ANSWER_MESSAGE",
]

# FR-01's complexity rules, stated once here and nowhere else (D-25).
PASSWORD_NAMES = [
    "PASSWORD_MINIMUM_LENGTH",
    "PASSWORD_MINIMUM_UPPERCASE",
    "PASSWORD_MINIMUM_DIGITS",
    "PASSWORD_MINIMUM_SPECIAL",
    "PASSWORD_SPECIAL_CHARACTERS",
]

VOCABULARIES = [
    "DOCUMENT_STATUS_VALUES",
    "MEETING_STATUS_VALUES",
    "CLASSIFICATION_DIMENSIONS",
    "SOURCE_TYPES",
    "NO_ANSWER_REASONS",
    "ROLE_NAMES",
    "TAG_APPLIED_BY_VALUES",
    # FR-10 (D-105), 8 November 2026: the fixed type list and the per-assignment outcomes.
    "DOCUMENT_TYPES",
    "ASSIGNMENT_OUTCOMES",
    # FR-19 (D-107), 9 November 2026: a knowledge-gap entry's status.
    "KNOWLEDGE_GAP_STATUS_VALUES",
]


@pytest.mark.parametrize(
    "name", SECTION_5_NAMES + PASSWORD_NAMES + VOCABULARIES + ["SESSION_INACTIVITY_MINUTES"]
)
def test_every_constant_is_defined(name):
    assert hasattr(constants, name), f"{name} missing from apps.core.constants"


def test_chunk_overlap_is_smaller_than_chunk_size():
    # An overlap at or above the size would stop the chunking loop advancing.
    assert 0 <= constants.CHUNK_OVERLAP < constants.CHUNK_SIZE
    assert constants.CHUNK_SIZE == 500
    assert constants.CHUNK_OVERLAP == 50


def test_accepted_formats_is_a_frozenset_of_exactly_four_bare_lower_case_extensions():
    # docs/decisions.md D-15: four formats; legacy doc and xls are not accepted.
    assert isinstance(constants.ACCEPTED_FORMATS, frozenset)
    assert constants.ACCEPTED_FORMATS == {"pdf", "docx", "xlsx", "txt"}
    for extension in constants.ACCEPTED_FORMATS:
        assert extension == extension.lower()
        assert not extension.startswith(".")


@pytest.mark.parametrize("extension", ["pdf", "docx", "xlsx", "txt"])
def test_accepted_format_membership(extension):
    assert extension in constants.ACCEPTED_FORMATS


@pytest.mark.parametrize("extension", ["doc", "xls", "exe", "zip", "md", "html", ".pdf", "PDF", ""])
def test_unaccepted_format_membership(extension):
    # doc and xls per D-15; upper-case and dotted forms are deliberately absent
    # because callers normalise first.
    assert extension not in constants.ACCEPTED_FORMATS


def test_every_accepted_format_has_exactly_the_download_content_type_d_75_names():
    """FR-15's download types a file by the format its signature proved (D-75's table). A
    format added to ACCEPTED_FORMATS without a type here would make its download a 500."""
    assert constants.DOWNLOAD_CONTENT_TYPES == {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "txt": "text/plain; charset=utf-8",
    }
    assert set(constants.DOWNLOAD_CONTENT_TYPES) == constants.ACCEPTED_FORMATS
    # The two OOXML types are the ones the signature detector already reads the manifest for.
    assert constants.DOWNLOAD_CONTENT_TYPES["docx"] == constants.WORD_CONTENT_TYPE
    assert constants.DOWNLOAD_CONTENT_TYPES["xlsx"] == constants.EXCEL_CONTENT_TYPE


def test_lockout_values():
    # FR-02 Business Logic: "five consecutive failures lock the account for 15
    # minutes". Enforcement is FR-02's, not FR-03's (D-25).
    assert constants.LOCKOUT_THRESHOLD == 5
    assert constants.LOCKOUT_DURATION == timedelta(minutes=15)


def test_password_complexity_constants_are_fr_01s_four_rules():
    # FR-01: "min 8 chars, 1 uppercase, 1 number, 1 special character" (D-25).
    assert constants.PASSWORD_MINIMUM_LENGTH == 8
    assert constants.PASSWORD_MINIMUM_UPPERCASE == 1
    assert constants.PASSWORD_MINIMUM_DIGITS == 1
    assert constants.PASSWORD_MINIMUM_SPECIAL == 1


def test_special_characters_are_ascii_punctuation_and_exclude_whitespace():
    """The server's definition of "special character" is the authoritative one, and
    the front end's strength meter narrows to it: ASCII punctuation, 32 characters.
    A space is not special, or a passphrase would satisfy the rule by accident."""
    import string

    assert constants.PASSWORD_SPECIAL_CHARACTERS == frozenset(string.punctuation)
    assert len(constants.PASSWORD_SPECIAL_CHARACTERS) == 32
    for character in " \t\n":
        assert character not in constants.PASSWORD_SPECIAL_CHARACTERS
    for character in string.ascii_letters + string.digits:
        assert character not in constants.PASSWORD_SPECIAL_CHARACTERS


def test_question_length_bounds_are_ordered():
    assert 0 < constants.MINIMUM_QUESTION_LENGTH < constants.MAXIMUM_QUESTION_LENGTH
    assert constants.MINIMUM_QUESTION_LENGTH == 10
    assert constants.MAXIMUM_QUESTION_LENGTH == 500


def test_upload_limit_is_fifty_megabytes():
    assert constants.MAX_UPLOAD_BYTES == 50 * 1024 * 1024


def test_attempt_counts_are_one_attempt_plus_two_retries():
    # docs/decisions.md D-19: three total attempts, uniform across every AI call,
    # including classification (FR-10, NIT3004), whose attempt loop in apps/ai/classification.py
    # has used it since D-104.
    assert constants.MAXIMUM_GENERATION_ATTEMPTS == 3
    assert constants.MAXIMUM_EMBED_ATTEMPTS == 3
    assert constants.MAXIMUM_CLASSIFY_ATTEMPTS == 3
    # And recording transcription's (D-123), 1 initial call + 2 retries like the rest.
    assert constants.MAXIMUM_TRANSCRIBE_ATTEMPTS == 3


def test_the_transcription_bounds_are_ordered():
    """D-123: the page's segment fits under the server's ceiling with room for a tail, the sample
    rate the page sends is inside the accepted range, and silence is measured in dBFS."""
    assert 0 < constants.TRANSCRIPTION_SEGMENT_SECONDS < constants.MAXIMUM_TRANSCRIPTION_SEGMENT_SECONDS
    assert (
        constants.MINIMUM_TRANSCRIPTION_SAMPLE_RATE
        <= constants.TRANSCRIPTION_SAMPLE_RATE
        <= constants.MAXIMUM_TRANSCRIPTION_SAMPLE_RATE
    )
    assert constants.TRANSCRIPTION_SILENCE_DBFS < 0
    assert 0 < constants.TRANSCRIPTION_SILENCE_WINDOW_SECONDS < constants.TRANSCRIPTION_SEGMENT_SECONDS
    assert constants.MAXIMUM_RECORDING_BYTES > constants.MAX_UPLOAD_BYTES


def test_top_k_is_positive():
    assert constants.TOP_K == 25


def test_relevance_threshold_is_a_cosine_similarity():
    assert 0.0 <= constants.RELEVANCE_THRESHOLD <= 1.0


# Step 7 (8 November 2026). RELEVANCE_THRESHOLD is D-37's 0.30, kept by the user's decision after
# the margin rule gave 0.4231 (dev-set.json) and 0.24 (dev-set-v2.json); PARTIAL_MATCH_FLOOR is
# 0.0, no floor, because the margin rule cannot set one at 0.30. The evidence is in
# corpus/objective-02/runs/2026-11-08/dev-set-v2.md. Pinned exactly, as TOP_K is, so that a
# change is a decision with evidence rather than an edit nobody notices.
MARGIN = 0.006  # twice the query-vector drift D-40 recorded
# The highest partial match offered to any dev-set-v2 run that path A declines at 0.30:
# u24's D20. (The runs are u30@Employee, u31@Employee, u07 and u24.)
HIGHEST_PATH_A_OFFER_AT_THE_THRESHOLD = 0.292898


def test_the_relevance_threshold_is_d37s_value_as_the_user_decided():
    assert isinstance(constants.RELEVANCE_THRESHOLD, float)
    assert constants.RELEVANCE_THRESHOLD == 0.30


def test_no_partial_match_floor_is_set_because_the_rule_cannot_set_one():
    assert isinstance(constants.PARTIAL_MATCH_FLOOR, float)
    assert constants.PARTIAL_MATCH_FLOOR == 0.0
    # The rule's lower bound (the highest path-A offer plus the margin) is above its ceiling
    # (the threshold less the margin), so it sets nothing, and D-56 stays open.
    lower_bound = HIGHEST_PATH_A_OFFER_AT_THE_THRESHOLD + MARGIN
    assert lower_bound > constants.RELEVANCE_THRESHOLD - MARGIN


def test_the_partial_match_floor_is_the_margin_below_the_threshold():
    # A real band of partial matches survives on path A, below the threshold: the floor is at
    # most the threshold less the margin, and the rule says stop rather than ship otherwise.
    assert 0.0 <= constants.PARTIAL_MATCH_FLOOR <= constants.RELEVANCE_THRESHOLD - MARGIN
    assert constants.RELEVANCE_THRESHOLD <= 1.0


def test_the_statement_cap_is_a_positive_whole_number():
    # Step 7 phase 2a (7 November 2026). Tuned on the development set; the prompt and the
    # schema both read it (apps/ai/prompting.py, apps/ai/schema.py).
    assert isinstance(constants.MAXIMUM_STATEMENTS, int)
    assert constants.MAXIMUM_STATEMENTS >= 1


def test_context_and_content_limits_are_positive():
    assert constants.MAXIMUM_CONTEXT_TOKENS > 0
    assert constants.MINIMUM_CONTENT_LENGTH > 0


def test_no_answer_message_is_fixed_non_empty_text():
    assert isinstance(constants.NO_ANSWER_MESSAGE, str)
    assert constants.NO_ANSWER_MESSAGE.strip()


def test_schema_v1_vocabularies_match_the_document():
    # DOCUMENT_STATUS_VALUES is the proposal's section 7.0 set, which supersedes the
    # five values schema v1 wrote before the proposal reached this machine (D-28).
    # "Too large to index" is the seventh, added by Stage 4 item 12b and recorded in
    # docs/schema-v1.md §3: MAXIMUM_CHUNKS_PER_SOURCE refuses a document before the first
    # embed call, and "Indexing failed" means an attempt was made and every chunk failed.
    # It sits beside "Insufficient content" because that is the kind it belongs to —
    # refused before attempting, on a property of the content.
    assert constants.DOCUMENT_STATUS_VALUES == (
        "Processing", "Extraction failed", "Insufficient content",
        "Too large to index", "Indexing failed", "Partially indexed", "Indexed",
    )
    assert constants.MEETING_STATUS_VALUES == ("Received", "Indexed", "Processing failed")
    assert constants.CLASSIFICATION_DIMENSIONS == ("Department", "Project", "Process", "Topic")
    assert constants.SOURCE_TYPES == ("document", "meeting")
    assert constants.NO_ANSWER_REASONS == ("no_relevant_passage", "no_statement_verified")
    assert constants.ROLE_NAMES == ("Employee", "Administrator")
    assert constants.TAG_APPLIED_BY_VALUES == ("ai", "user")


def test_derived_names_point_into_their_vocabularies():
    # Section 7.8 creates the record with status "Processing", before extraction
    # begins, so the vocabulary's first value is what a new row holds (D-28).
    assert constants.DEFAULT_DOCUMENT_STATUS == "Processing"
    assert constants.DEFAULT_MEETING_STATUS == "Received"
    assert constants.EMPLOYEE_ROLE_NAME == "Employee"
    assert constants.ADMINISTRATOR_ROLE_NAME == "Administrator"


@pytest.mark.parametrize("name", VOCABULARIES)
def test_vocabulary_values_are_distinct_strings_that_fit_the_column(name):
    values = getattr(constants, name)
    assert isinstance(values, tuple)
    assert len(set(values)) == len(values)
    for value in values:
        assert isinstance(value, str) and value
        assert len(value) <= VOCABULARY_MAX_LENGTH


def test_the_knowledge_gap_constants_are_d107s_and_d109s():
    """FR-19 (D-107 to D-109). The status vocabulary and its default, the grace of the window, the
    permission code and the panel size are the decisions' values; the grouping threshold is a
    cosine similarity chosen by D-109's sweep on the development paraphrase set (9 November 2026,
    corpus/objective-06/runs/2026-11-09/grouping-sweep/), and pinned so a change is a decision."""
    assert constants.KNOWLEDGE_GAP_STATUS_VALUES == ("Open", "Addressed")
    assert constants.KNOWLEDGE_GAP_OPEN == "Open"
    assert constants.KNOWLEDGE_GAP_ADDRESSED == "Addressed"
    assert constants.DEFAULT_KNOWLEDGE_GAP_STATUS == constants.KNOWLEDGE_GAP_OPEN
    assert isinstance(constants.GAP_GROUPING_THRESHOLD, float)
    assert 0.0 < constants.GAP_GROUPING_THRESHOLD <= 1.0
    assert constants.GAP_GROUPING_THRESHOLD == 0.5256
    # The sweep's own margin: its lowest within-subject pair, 0.5322, is above the value.
    assert constants.GAP_GROUPING_THRESHOLD < 0.5322
    # D-122: voyage-4's own value, by D-109's rule on Voyage's vectors (10 November 2026,
    # corpus/objective-06/runs/2026-11-10/grouping-sweep-voyage/), below that sweep's lowest
    # within-subject pair, 0.5157. No other model is listed, so EmbeddingGemma keeps 0.5256.
    assert constants.GAP_GROUPING_THRESHOLD_BY_MODEL == {"voyage-4": 0.5054}
    assert constants.GAP_GROUPING_THRESHOLD_BY_MODEL["voyage-4"] < 0.5157
    assert constants.CYCLE_GRACE_SECONDS == 60
    assert constants.REVIEW_KNOWLEDGE_GAPS_PERMISSION == "review_knowledge_gaps"
    assert constants.DASHBOARD_GAP_ITEMS == constants.DASHBOARD_RECENT_ITEMS


def test_session_inactivity_is_sixty_minutes():
    # FR-04, docs/decisions.md D-10.
    assert constants.SESSION_INACTIVITY_MINUTES == 60


def test_effective_roles_are_closed_under_generalisation():
    """The security review's finding 7 (D-105's dated note of 10 November 2026, night). FR-10's
    tag_options discloses nothing only because whatever a role in a role's effective set reads,
    that role reads too: for every role C and every R in EFFECTIVE_ROLES[C], EFFECTIVE_ROLES[R] is a
    subset of EFFECTIVE_ROLES[C]. A role missing from the map reads nothing, which is a subset of
    anything."""
    for role, effective in constants.EFFECTIVE_ROLES.items():
        for included in effective:
            assert set(constants.EFFECTIVE_ROLES.get(included, ())) <= set(effective), (role, included)


def test_fr10s_confidence_threshold_is_per_classifying_model():
    """D-122: claude-haiku-5-5's own value, by D-106's rule on the development documents (10 November
    2026, corpus/objective-05/runs/2026-11-10/dev-sweep-haiku/): the lowest confidence on a correct type
    assignment, since Haiku typed all 57 right. Every other model keeps CLASSIFICATION_CONFIDENCE_THRESHOLD."""
    assert constants.CLASSIFICATION_CONFIDENCE_THRESHOLD_BY_MODEL == {"claude-haiku-5-5": 0.72}
    assert 0.0 < constants.CLASSIFICATION_CONFIDENCE_THRESHOLD_BY_MODEL["claude-haiku-5-5"] <= 1.0
