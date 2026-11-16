"""The stub's classify_document (apps/ai/testing.py): deterministic, scheme-derived, overridable (FR-10).

apps/documents' tests drive the apply rules (D-105) through this stub without a live model, so
what it returns by default, and how a test replaces that, are pinned here.
"""

import pytest

import apps.ai
from apps.ai.base import Assignment, DocumentClassification, ProviderUnavailable, TagScheme, TagSuggestion
from apps.ai.testing import (
    STUB_CHAT_MODEL,
    STUB_CONFIDENCE,
    STUB_OUT_OF_SCHEME_DEPARTMENT,
    StubAIService,
)
from apps.core.constants import CLASSIFICATION_INPUT_TOKENS, DOCUMENT_TYPES

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
