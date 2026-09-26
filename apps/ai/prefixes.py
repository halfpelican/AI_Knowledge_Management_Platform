"""EmbeddingGemma's task prefixes (docs/ai-provider.md section 4, risk R10).

EmbeddingGemma is trained with a task prefix on each side of a search, and the two
sides are not the same prefix: a query is embedded as
``task: search result | query: {content}`` and a document as
``title: {title} | text: {content}``, with ``title: none`` where the source has no
title. Sending raw text on both sides embeds questions and passages into one space
rather than the two the model was trained to relate, which is what a query-to-chunk
score band sitting below the chunk-to-chunk mean looks like from the outside.

This module lives in apps/ai because a prefix convention is a fact about a specific
embedding model, and model specifics live here (CLAUDE.md section 4). It is the only
place the two format strings are written.

**Dispatch is on the embedding model in use, not on the provider.** The rule belongs
to EmbeddingGemma, so a future FLM build serving some other embedding model must not
inherit it, and any name this module does not recognise gets its text back unchanged.
Voyage is the case that makes "unchanged" load-bearing rather than merely tidy: it
takes an ``input_type`` parameter on the request instead of a string prefix, so
prefixing its text would corrupt the documented production path to no purpose.

Applying a prefix is a RE-INDEX EVENT. Vectors built from prefixed text are not
comparable with vectors built from raw text, and the similarity score does not
announce the difference — it just gets quietly worse. ``manage.py reindex`` rebuilds
the corpus; nothing here reads or writes the database.
"""

from django.conf import settings

# The two forms, exactly as EmbeddingGemma documents them. Written once, here.
QUERY_TEMPLATE = "task: search result | query: {content}"
DOCUMENT_TEMPLATE = "title: {title} | text: {content}"
# What the document form carries in place of a title it does not have.
MISSING_TITLE = "none"

# Names that mean EmbeddingGemma. FLM serves it as "embed-gemma"; upstream and other
# servers spell it differently, and matching a few known spellings is honest about
# what this module knows rather than guessing from a substring like "gemma", which
# would also match the chat model.
EMBEDDING_GEMMA_NAMES = ("embed-gemma", "embedding-gemma", "embeddinggemma", "embedgemma")


def _configured_embedding_model() -> str:
    """The name of the model that will actually embed, for the provider in use.

    The provider is consulted only to learn WHICH model name is in play; the prefix
    rule below is then a property of that name. Reading FLM_EMBED_MODEL
    unconditionally would apply an EmbeddingGemma convention to Voyage whenever a
    developer left the FLM default in place, which is the corruption this module
    exists to avoid.
    """
    if settings.AI_PROVIDER == "anthropic":
        return settings.VOYAGE_MODEL
    return settings.FLM_EMBED_MODEL


def _wants_task_prefixes() -> bool:
    """Whether the configured embedding model is an EmbeddingGemma."""
    name = (_configured_embedding_model() or "").strip().lower()
    return any(known in name for known in EMBEDDING_GEMMA_NAMES)


def query_text(question: str) -> str:
    """The question as the embedding model should receive it.

    Returns the question unchanged for any model that does not take task prefixes.
    """
    if not _wants_task_prefixes():
        return question
    return QUERY_TEMPLATE.format(content=question)


def document_text(title: str | None, text: str) -> str:
    """A passage as the embedding model should receive it.

    ``title`` is the owning Document's or Meeting's title; an empty or missing one
    becomes ``title: none`` rather than an empty field, because the model was trained
    with the token present. Returns ``text`` unchanged for any model that does not
    take task prefixes.

    The caller stores the UNPREFIXED text. What is returned here is what goes to the
    provider and nothing else: a prefix written into ContentChunk.chunk_text would be
    read back out into answers, citations and snippets (FR-12), and
    apps/ingestion/chunking.py keeps each chunk a verbatim substring of its source
    precisely so that cannot happen.
    """
    if not _wants_task_prefixes():
        return text
    heading = title.strip() if title and title.strip() else MISSING_TITLE
    return DOCUMENT_TEMPLATE.format(title=heading, content=text)
