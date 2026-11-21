"""The stub's classify_document (apps/ai/testing.py): deterministic, scheme-derived, overridable (FR-10).

apps/documents' tests drive the apply rules (D-105) through this stub without a live model, so
what it returns by default, and how a test replaces that, are pinned here.

Since D-139 the default carries a summary and key points: ``stub_document_summary(title)`` and
STUB_KEY_POINTS, with ``summary_truncated`` from the real ``summary_sections``.
"""

import json

import pytest

import apps.ai
from apps.ai.base import Assignment, DocumentClassification, ProviderUnavailable, TagScheme, TagSuggestion
from apps.ai.classification import parse_section_summary, summary_sections
from apps.ai.testing import (
    STUB_CHAT_MODEL,
    STUB_CONFIDENCE,
    STUB_KEY_POINTS,
    STUB_OUT_OF_SCHEME_DEPARTMENT,
    StubAIService,
    stub_document_summary,
)
from apps.core.constants import (
    CLASSIFICATION_INPUT_TOKENS,
    DOCUMENT_TYPES,
    MAXIMUM_KEY_POINT_CHARACTERS,
    MAXIMUM_KEY_POINTS,
    MAXIMUM_SUMMARY_CHARACTERS,
    MAXIMUM_SUMMARY_SECTIONS,
)

SCHEME = TagScheme(
    doc_types=DOCUMENT_TYPES,
    departments=("Finance", "Human Resources"),
    tags={"Project": ("atlas", "office move"), "Process": (), "Topic": ("safety", "finance")},
)
OVERRIDE = DocumentClassification(
    doc_type=Assignment(value="Report", confidence=0.51),
    department=Assignment(value="Catering", confidence=0.2),
    tags=(TagSuggestion(dimension="Topic", value="ergonomics", confidence=0.3),),
    model="scripted",
    input_truncated=True,
)


def test_the_default_is_derived_from_the_scheme():
    result = StubAIService().classify_document("Title", "Some text.", SCHEME)

    assert isinstance(result, DocumentClassification)
    assert result.doc_type == Assignment(value=DOCUMENT_TYPES[0], confidence=STUB_CONFIDENCE)
    assert result.department == Assignment(value="Finance", confidence=STUB_CONFIDENCE)
    # One tag per dimension that lists a value, that dimension's first, in Project, Process, Topic
    # order; Process lists nothing here, so it has none.
    assert result.tags == (
        TagSuggestion(dimension="Project", value="atlas", confidence=STUB_CONFIDENCE),
        TagSuggestion(dimension="Topic", value="safety", confidence=STUB_CONFIDENCE),
    )
    assert result.model == STUB_CHAT_MODEL
    assert result.input_truncated is False


def test_the_default_is_deterministic_across_instances():
    assert StubAIService().classify_document("T", "x", SCHEME) == StubAIService().classify_document("T", "x", SCHEME)


def test_a_scheme_without_departments_gets_an_out_of_scheme_placeholder():
    scheme = TagScheme(doc_types=DOCUMENT_TYPES, departments=(), tags={})
    result = StubAIService().classify_document("T", "x", scheme)
    assert result.department.value == STUB_OUT_OF_SCHEME_DEPARTMENT
    assert STUB_OUT_OF_SCHEME_DEPARTMENT not in SCHEME.departments
    assert result.tags == ()


def test_a_scheme_missing_a_dimension_key_is_tolerated():
    scheme = TagScheme(doc_types=DOCUMENT_TYPES, departments=("Finance",), tags={"Topic": ("safety",)})
    assert [t.dimension for t in StubAIService().classify_document("T", "x", scheme).tags] == ["Topic"]


def test_a_scheme_without_document_types_is_a_callers_bug():
    with pytest.raises(ValueError, match="at least one document type"):
        StubAIService().classify_document("T", "x", TagScheme(doc_types=(), departments=(), tags={}))


def test_input_truncated_is_the_real_flag():
    stub = StubAIService()
    assert stub.classify_document("T", " ".join(["w"] * CLASSIFICATION_INPUT_TOKENS), SCHEME).input_truncated is False
    assert stub.classify_document("T", " ".join(["w"] * (CLASSIFICATION_INPUT_TOKENS + 1)), SCHEME).input_truncated is True


# --- The summary (D-139) ----------------------------------------------------------------------


def test_the_default_carries_a_summary_naming_the_title_and_the_two_stub_key_points():
    result = StubAIService().classify_document("Leave policy", "Some text.", SCHEME)

    assert result.summary == stub_document_summary("Leave policy") == "Stub summary of the document 'Leave policy'."
    assert result.key_points == STUB_KEY_POINTS == ("Stub key point one.", "Stub key point two.")
    assert result.summary_truncated is False


def test_the_stubs_summary_tells_two_documents_apart():
    stub = StubAIService()
    first = stub.classify_document("Leave policy", "x", SCHEME)
    second = stub.classify_document("Travel policy", "x", SCHEME)
    assert first.summary != second.summary
    assert "Leave policy" in first.summary and "Travel policy" in second.summary


def test_the_stubs_summary_is_one_a_provider_could_return():
    """The stub stands in for the contract, so its default is inside the parser's bounds: a
    non-empty summary within the limit, and between 1 and MAXIMUM_KEY_POINTS key points, each
    within its own. A reply built from the default parses."""
    result = StubAIService().classify_document("T" * 255, "x", SCHEME)

    assert 0 < len(result.summary) <= MAXIMUM_SUMMARY_CHARACTERS
    assert isinstance(result.key_points, tuple) and len(result.key_points) == 2
    assert 1 <= len(result.key_points) <= MAXIMUM_KEY_POINTS
    assert all(0 < len(point) <= MAXIMUM_KEY_POINT_CHARACTERS for point in result.key_points)
    parsed = parse_section_summary(json.dumps({"summary": result.summary, "key_points": list(result.key_points)}))
    assert (parsed.summary, parsed.key_points) == (result.summary, result.key_points)


def test_summary_truncated_is_the_real_flag():
    """From ``summary_sections``, as ``input_truncated`` is from ``classification_input``: False
    at exactly MAXIMUM_SUMMARY_SECTIONS sections, True one token past them. And the two flags
    are different facts: a text of two sections is cut for classification and summarised whole."""
    stub = StubAIService()
    ceiling = MAXIMUM_SUMMARY_SECTIONS * CLASSIFICATION_INPUT_TOKENS
    at, past = " ".join(["w"] * ceiling), " ".join(["w"] * (ceiling + 1))

    assert stub.classify_document("T", at, SCHEME).summary_truncated is False
    assert stub.classify_document("T", past, SCHEME).summary_truncated is True
    assert (summary_sections(at)[1], summary_sections(past)[1]) == (False, True)
    two_sections = stub.classify_document("T", " ".join(["w"] * (CLASSIFICATION_INPUT_TOKENS + 1)), SCHEME)
    assert (two_sections.input_truncated, two_sections.summary_truncated) == (True, False)


def test_the_stub_is_one_call_however_long_the_text():
    """A provider makes a request per section of a long text; the stub makes none. One entry in
    ``classify_calls`` whatever the length, so a test counting calls counts operations."""
    stub = StubAIService()
    stub.classify_document("T", " ".join(["w"] * (3 * CLASSIFICATION_INPUT_TOKENS)), SCHEME)
    assert len(stub.classify_calls) == 1


def test_an_override_is_returned_as_given_with_no_summary_added():
    """The dataclass's defaults, not the stub's: an override built without a summary has none,
    which is how a test of a document with no summary gets one."""
    result = StubAIService(classification=OVERRIDE).classify_document("T", "x", SCHEME)
    assert result is OVERRIDE
    assert (result.summary, result.key_points, result.summary_truncated) == ("", (), False)


def test_every_call_is_recorded_with_its_arguments():
    stub = StubAIService()
    stub.classify_document("Title", "Text.", SCHEME)
    assert stub.classify_calls == [("Title", "Text.", SCHEME)]


def test_the_constructor_argument_overrides_the_default_for_every_call():
    stub = StubAIService(classification=OVERRIDE)
    assert stub.classify_document("A", "a", SCHEME) is OVERRIDE
    assert stub.classify_document("B", "b", SCHEME) is OVERRIDE
    assert len(stub.classify_calls) == 2


def test_the_attribute_overrides_the_default_on_the_suites_own_stub(stub_ai_service):
    """The autouse fixture's instance, as an apps/documents test would use it."""
    assert apps.ai.get_ai_service() is stub_ai_service
    stub_ai_service.classification = OVERRIDE
    assert apps.ai.get_ai_service().classify_document("T", "x", SCHEME) is OVERRIDE
    stub_ai_service.classification = None
    assert apps.ai.get_ai_service().classify_document("T", "x", SCHEME).model == STUB_CHAT_MODEL


def test_a_callable_override_receives_the_arguments_and_its_value_is_returned():
    received = []

    def scripted(title, text, scheme):
        received.append((title, text, scheme))
        return OVERRIDE

    stub = StubAIService(classification=scripted)
    assert stub.classify_document("Title", "Text.", SCHEME) is OVERRIDE
    assert received == [("Title", "Text.", SCHEME)]
    assert stub.classify_calls == received


def test_a_callable_override_can_stand_in_for_an_outage():
    """invariant 8's tests need the provider to fail: the call is still recorded first."""

    def down(title, text, scheme):
        raise ProviderUnavailable("FLM at http://127.0.0.1:9/v1 returned no response conforming to CLASSIFICATION_SCHEMA")

    stub = StubAIService(classification=down)
    with pytest.raises(ProviderUnavailable):
        stub.classify_document("T", "x", SCHEME)
    assert len(stub.classify_calls) == 1


def test_the_stub_makes_no_network_call(stub_ai_service):
    """Nothing in the default path touches a client: the autouse stub answers under the unroutable
    settings every test runs with (apps/ai/tests/test_no_live_provider.py)."""
    result = stub_ai_service.classify_document("T", "x", SCHEME)
    assert result.model == STUB_CHAT_MODEL
    assert stub_ai_service.embed_calls == [] and stub_ai_service.generate_calls == []
