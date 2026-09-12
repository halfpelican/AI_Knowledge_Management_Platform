"""CLAUDE.md section 5: every tuned constant is defined once, in apps.core.constants."""

from datetime import timedelta

import pytest

from apps.core import constants

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


@pytest.mark.parametrize("name", SECTION_5_NAMES)
def test_every_section_5_constant_is_defined(name):
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
