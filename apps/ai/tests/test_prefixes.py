"""EmbeddingGemma's task prefixes (apps/ai/prefixes.py).

No database and no provider: these are two pure functions over settings. The forms
asserted here are the model's documented ones, written out in full rather than built
from the module's own templates, so a test would fail if a template were edited into
something the model does not expect.
"""

from django.test import override_settings

from apps.ai.prefixes import MISSING_TITLE, document_text, query_text

EMBEDDING_GEMMA = "embed-gemma"
QUESTION = "How much annual leave do I get?"
PASSAGE = "Leave accrues monthly and is approved by a manager."


@override_settings(AI_PROVIDER="flm", FLM_EMBED_MODEL=EMBEDDING_GEMMA)
def test_a_query_carries_the_search_result_task_prefix():
    assert query_text(QUESTION) == f"task: search result | query: {QUESTION}"


@override_settings(AI_PROVIDER="flm", FLM_EMBED_MODEL=EMBEDDING_GEMMA)
def test_a_document_carries_its_title_and_text():
    assert document_text("Leave policy", PASSAGE) == f"title: Leave policy | text: {PASSAGE}"


@override_settings(AI_PROVIDER="flm", FLM_EMBED_MODEL=EMBEDDING_GEMMA)
def test_a_missing_title_is_the_word_none_rather_than_an_empty_field():
    """The model was trained with the token present, so it is always present."""
    expected = f"title: {MISSING_TITLE} | text: {PASSAGE}"
    assert document_text(None, PASSAGE) == expected
    assert document_text("", PASSAGE) == expected
    assert document_text("   ", PASSAGE) == expected  # whitespace is not a title


@override_settings(AI_PROVIDER="flm", FLM_EMBED_MODEL=EMBEDDING_GEMMA)
def test_neither_function_mutates_what_it_is_given():
    question = QUESTION
    passage = PASSAGE
    query_text(question)
    document_text("Leave policy", passage)
    assert question == QUESTION
    assert passage == PASSAGE
    # And the prefixed form contains the original verbatim, so nothing is rewritten.
    assert QUESTION in query_text(QUESTION)
    assert PASSAGE in document_text("Leave policy", PASSAGE)


@override_settings(AI_PROVIDER="flm", FLM_EMBED_MODEL="some-other-embedding-model")
def test_a_model_that_is_not_embeddinggemma_gets_its_text_back_unchanged():
    """The rule belongs to EmbeddingGemma, not to FLM.

    A future FLM build serving a different embedding model must not inherit a prefix
    convention that model was not trained with.
    """
    assert query_text(QUESTION) == QUESTION
    assert document_text("Leave policy", PASSAGE) == PASSAGE


@override_settings(AI_PROVIDER="anthropic", VOYAGE_MODEL="voyage-3", FLM_EMBED_MODEL=EMBEDDING_GEMMA)
def test_voyage_gets_its_text_back_unchanged_even_with_the_flm_default_in_place():
    """Voyage takes an input_type parameter on the request, not a string prefix.

    FLM_EMBED_MODEL keeps its default in most .env files, so reading that name
    unconditionally would prefix text bound for Voyage and corrupt the documented
    production path for nothing. The model that will actually embed is the one that
    decides.
    """
    assert query_text(QUESTION) == QUESTION
    assert document_text("Leave policy", PASSAGE) == PASSAGE
