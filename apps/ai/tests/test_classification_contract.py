"""The AIService contract and its implementations agree on classify_document (FR-10, D-104).

No existing test asserted that the Protocol in apps/ai/base.py and the three implementations
(FLMService, AnthropicService, StubAIService) agree in signature, so this one does, for every
operation the Protocol lists: the same method names, and for ``classify_document`` the same
parameter names in the same order. "A contract and its implementations differing by a parameter
is the defect this project keeps finding in other people's code" (apps/ai/base.py), and the stub
is included because the whole suite stands on it standing in for the contract.
"""

import dataclasses
import inspect

import pytest

from apps.ai.anthropic import AnthropicService
from apps.ai.base import AIService, Assignment, DocumentClassification
from apps.ai.flm import FLMService
from apps.ai.testing import StubAIService

IMPLEMENTATIONS = [FLMService, AnthropicService, StubAIService]


def operations(cls) -> list[str]:
    """The public callables a class declares, in definition order."""
    return [name for name, value in vars(cls).items() if callable(value) and not name.startswith("_")]


def parameter_names(function) -> list[str]:
    return list(inspect.signature(function).parameters)


def test_the_protocol_lists_classify_document_with_title_text_and_scheme():
    assert parameter_names(AIService.classify_document) == ["self", "title", "text", "scheme"]
    assert "classify_document" in operations(AIService)


def test_d139_added_no_operation_and_no_parameter():
    """D-139, decision 2: the summary arrives through ``classify_document`` as it stands. The
    operations are the seven CLAUDE.md section 4 lists, and this one still takes a title, a text
    and a scheme: one call from the application, however many requests a provider makes."""
    assert operations(AIService) == [
        "embed", "generate_statements", "health", "classify_document",
        "transcribe", "transcription_health", "summarise_meeting",
    ]
    assert parameter_names(AIService.classify_document) == ["self", "title", "text", "scheme"]


def test_document_classification_gained_three_fields_with_defaults_after_the_five_it_had():
    """D-139: ``summary``, ``key_points`` and ``summary_truncated``, each with a default and all
    after the original five, so every construction written before D-139 still stands, by keyword
    or by position, and reads as a classification with no summary."""
    fields = dataclasses.fields(DocumentClassification)
    assert [field.name for field in fields] == [
        "doc_type", "department", "tags", "model", "input_truncated",
        "summary", "key_points", "summary_truncated",
    ]
    assert [field.default for field in fields[5:]] == ["", (), False]
    assert all(field.default is dataclasses.MISSING for field in fields[:5])  # the five stay required

    assignment = Assignment(value="Policy", confidence=0.9)
    by_keyword = DocumentClassification(
        doc_type=assignment, department=assignment, tags=(), model="m", input_truncated=False
    )
    by_position = DocumentClassification(assignment, assignment, (), "m", False)
    assert by_keyword == by_position
    assert (by_keyword.summary, by_keyword.key_points, by_keyword.summary_truncated) == ("", (), False)


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS, ids=lambda cls: cls.__name__)
def test_every_implementation_has_every_operation_the_protocol_lists(implementation):
    missing = [name for name in operations(AIService) if not callable(getattr(implementation, name, None))]
    assert missing == [], f"{implementation.__name__} lacks {missing}"


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS, ids=lambda cls: cls.__name__)
def test_classify_document_has_the_protocols_parameters_in_every_implementation(implementation):
    assert parameter_names(implementation.classify_document) == parameter_names(AIService.classify_document)


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS, ids=lambda cls: cls.__name__)
def test_the_other_operations_keep_the_protocols_positional_parameters(implementation):
    """embed, generate_statements and health: the positional names agree too. (generate_statements'
    keyword-only observer is the contract's, declared in the Protocol; the stub does not take it,
    which is pre-existing and recorded here rather than hidden.)"""
    for name in ("embed", "health"):
        assert parameter_names(getattr(implementation, name)) == parameter_names(getattr(AIService, name))
    positional = lambda f: [n for n, p in inspect.signature(f).parameters.items() if p.kind is p.POSITIONAL_OR_KEYWORD]  # noqa: E731
    assert positional(implementation.generate_statements) == positional(AIService.generate_statements)
