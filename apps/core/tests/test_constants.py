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
    "MINIMUM_QUESTION_LENGTH",
    "MAXIMUM_QUESTION_LENGTH",
    "MINIMUM_CONTENT_LENGTH",
    "MAX_UPLOAD_BYTES",
    "ACCEPTED_FORMATS",
    "LOCKOUT_THRESHOLD",
    "LOCKOUT_DURATION",
    "NO_ANSWER_MESSAGE",
]

VOCABULARIES = [
    "DOCUMENT_STATUS_VALUES",
    "MEETING_STATUS_VALUES",
    "CLASSIFICATION_DIMENSIONS",
    "SOURCE_TYPES",
    "NO_ANSWER_REASONS",
    "ROLE_NAMES",
    "TAG_APPLIED_BY_VALUES",
]


@pytest.mark.parametrize("name", SECTION_5_NAMES + VOCABULARIES + ["SESSION_INACTIVITY_MINUTES"])
def test_every_constant_is_defined(name):
    assert hasattr(constants, name), f"{name} missing from apps.core.constants"


def test_chunk_overlap_is_smaller_than_chunk_size():
    # An overlap at or above the size would stop the chunking loop advancing.
    assert 0 <= constants.CHUNK_OVERLAP < constants.CHUNK_SIZE
    assert constants.CHUNK_SIZE == 500
    assert constants.CHUNK_OVERLAP == 50


def test_accepted_formats_is_a_frozenset_of_bare_lower_case_extensions():
    assert isinstance(constants.ACCEPTED_FORMATS, frozenset)
    assert constants.ACCEPTED_FORMATS == {"pdf", "docx", "doc", "xlsx", "xls", "txt"}
    for extension in constants.ACCEPTED_FORMATS:
        assert extension == extension.lower()
        assert not extension.startswith(".")


@pytest.mark.parametrize("extension", ["pdf", "docx", "doc", "xlsx", "xls", "txt"])
def test_accepted_format_membership(extension):
    assert extension in constants.ACCEPTED_FORMATS


@pytest.mark.parametrize("extension", ["exe", "zip", "md", "html", ".pdf", "PDF", ""])
def test_unaccepted_format_membership(extension):
    # Upper-case and dotted forms are deliberately absent: callers normalise first.
    assert extension not in constants.ACCEPTED_FORMATS


def test_lockout_values():
    assert constants.LOCKOUT_THRESHOLD == 5
    assert constants.LOCKOUT_DURATION == timedelta(minutes=15)


def test_question_length_bounds_are_ordered():
    assert 0 < constants.MINIMUM_QUESTION_LENGTH < constants.MAXIMUM_QUESTION_LENGTH
    assert constants.MINIMUM_QUESTION_LENGTH == 10
    assert constants.MAXIMUM_QUESTION_LENGTH == 500


def test_upload_limit_is_fifty_megabytes():
    assert constants.MAX_UPLOAD_BYTES == 50 * 1024 * 1024


def test_attempt_counts_are_one_attempt_plus_two_retries():
    assert constants.MAXIMUM_GENERATION_ATTEMPTS == 3
    assert constants.MAXIMUM_EMBED_ATTEMPTS == 3


def test_top_k_is_positive():
    assert constants.TOP_K == 25


def test_relevance_threshold_is_a_cosine_similarity():
    assert 0.0 <= constants.RELEVANCE_THRESHOLD <= 1.0


def test_context_and_content_limits_are_positive():
    assert constants.MAXIMUM_CONTEXT_TOKENS > 0
    assert constants.MINIMUM_CONTENT_LENGTH > 0


def test_no_answer_message_is_fixed_non_empty_text():
    assert isinstance(constants.NO_ANSWER_MESSAGE, str)
    assert constants.NO_ANSWER_MESSAGE.strip()


def test_schema_v1_vocabularies_match_the_document():
    assert constants.DOCUMENT_STATUS_VALUES == (
        "Uploaded", "Extracting", "Indexed", "Insufficient content", "Processing failed"
    )
    assert constants.MEETING_STATUS_VALUES == ("Received", "Indexed", "Processing failed")
    assert constants.CLASSIFICATION_DIMENSIONS == ("Department", "Project", "Process", "Topic")
    assert constants.SOURCE_TYPES == ("document", "meeting")
    assert constants.NO_ANSWER_REASONS == ("no_relevant_passage", "no_statement_verified")
    assert constants.ROLE_NAMES == ("Employee", "Administrator")
    assert constants.TAG_APPLIED_BY_VALUES == ("ai", "user")


def test_derived_names_point_into_their_vocabularies():
    assert constants.DEFAULT_DOCUMENT_STATUS == "Uploaded"
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


def test_session_inactivity_is_sixty_minutes():
    # FR-04, docs/decisions.md D-10.
    assert constants.SESSION_INACTIVITY_MINUTES == 60
