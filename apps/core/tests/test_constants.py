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
    # including classification (FR-10, NIT3004) which is named now but unused.
    assert constants.MAXIMUM_GENERATION_ATTEMPTS == 3
    assert constants.MAXIMUM_EMBED_ATTEMPTS == 3
    assert constants.MAXIMUM_CLASSIFY_ATTEMPTS == 3


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
    # DOCUMENT_STATUS_VALUES is the proposal's section 7.0 set, which supersedes the
    # five values schema v1 wrote before the proposal reached this machine (D-28).
    assert constants.DOCUMENT_STATUS_VALUES == (
        "Processing", "Extraction failed", "Insufficient content",
        "Indexing failed", "Partially indexed", "Indexed",
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


def test_session_inactivity_is_sixty_minutes():
    # FR-04, docs/decisions.md D-10.
    assert constants.SESSION_INACTIVITY_MINUTES == 60
