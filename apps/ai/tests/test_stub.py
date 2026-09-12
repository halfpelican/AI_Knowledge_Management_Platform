"""The stub the whole suite relies on behaves like the contract it stands in for."""

import pytest
from django.conf import settings

from apps.ai.base import EmbeddingResult, Passage, StatementList
from apps.ai.testing import STUB_EMBEDDING_MODEL, StubAIService


def test_embed_is_deterministic_and_sized_from_settings(stub_ai_service):
    first = stub_ai_service.embed(["alpha", "beta"])
    second = StubAIService().embed(["alpha", "beta"])

    assert isinstance(first, EmbeddingResult)
    assert first.model == STUB_EMBEDDING_MODEL
    assert first.dimension == settings.EMBEDDING_DIMENSION
    assert all(len(vector) == settings.EMBEDDING_DIMENSION for vector in first.vectors)
    assert first.vectors == second.vectors  # same text, same vector, in any process
    assert first.vectors[0] != first.vectors[1]  # different texts differ
    assert stub_ai_service.embed_calls == [["alpha", "beta"]]


def test_embed_rejects_an_empty_list(stub_ai_service):
    with pytest.raises(ValueError):
        stub_ai_service.embed([])


def test_generate_statements_cites_the_first_passage(stub_ai_service):
    passages = [Passage(chunk_id="c_1", text="one"), Passage(chunk_id="c_2", text="two")]
    result = stub_ai_service.generate_statements("What is one?", passages)

    assert isinstance(result, StatementList)
    assert [statement.chunk_id for statement in result.statements] == ["c_1"]
    assert stub_ai_service.generate_calls == [("What is one?", passages)]


def test_generate_statements_returns_nothing_without_passages(stub_ai_service):
    assert stub_ai_service.generate_statements("Anything?", []) == StatementList(statements=[])


def test_health_reflects_the_configured_availability():
    assert StubAIService().health().available is True
    down = StubAIService(available=False, detail="down").health()
    assert down.available is False
    assert down.detail == "down"
