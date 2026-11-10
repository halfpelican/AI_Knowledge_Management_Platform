"""Embedding and indexing of chunks (proposal section 7.7, FR-08).

One embed call per chunk, not one call for the document. Section 7.7 loops per chunk
so that a transient provider failure costs one chunk rather than the whole upload,
which is what makes "Partially indexed" a reachable outcome rather than dead code
(D-28). Batching would make every failure total.

Three things every row carries, and each is an invariant rather than a convenience:

- ``embedding_model`` and ``embedding_dimension`` come from the EmbeddingResult the
  provider actually returned, never from settings. Retrieval executes only over
  chunks whose recorded model matches the query model (CLAUDE.md section 4, risk
  R10), so a value copied from configuration rather than from the response would
  describe what was expected instead of what happened — and a model change would
  then be silent corruption rather than an exclusion.
- ``visible_to_roles`` is stamped from the owning Document or Meeting (D-17), so the
  FR-11 permission predicate and the vector are on one table and filtering before
  ranking is structural rather than remembered.
- ``source_type`` and ``source_id`` identify the owner polymorphically, with no
  database foreign key (D-07).

Two failure classes, deliberately not the same thing:

- A provider that is unavailable, or answers unusably, fails the CHUNK. It is
  retried to MAXIMUM_EMBED_ATTEMPTS, then counted and skipped, a rate limit (429)
  included since D-118. A refusal, any other 4xx (ProviderRefused), fails the chunk on
  its first attempt, because a retry would be refused the same way. The provider logs
  every 4xx (apps/ai/_status.py), since nothing here logs attempts. The document still
  commits, carrying the status that says so (CLAUDE.md invariant 8, NFR-20).
- Anything else propagates. An unexpected exception is not an outcome the pipeline
  decided, so it rolls the caller's transaction back and leaves nothing behind
  (NFR-21, CLAUDE.md invariant 9).
"""

from django.conf import settings

import apps.ai
from apps.ai.base import INPUT_TYPE_DOCUMENT, EmbeddingResult, ProviderRefused, ProviderUnavailable
from apps.ai.prefixes import document_text
from apps.core.constants import MAXIMUM_EMBED_ATTEMPTS, SOURCE_TYPES
from apps.documents.models import ContentChunk

# Named so nothing here spells a source type as a literal; the vocabulary itself is
# fixed in apps/core/constants.py (docs/schema-v1.md section 3).
DOCUMENT_SOURCE_TYPE, MEETING_SOURCE_TYPE = SOURCE_TYPES


def embed_and_store_chunks(
    *, chunks, source_type: str, source_id, visible_to_roles, title: str | None = None
) -> int:
    """Embed each chunk and write its ContentChunk row. Returns failed_chunk_count.

    ``chunks`` is a sequence of chunking.Chunk. The caller runs this inside its own
    transaction.atomic() block, so the rows written here commit with the source
    record or not at all.

    ``title`` is the owning Document's or Meeting's title, and it goes into the
    document task prefix the embedding model is sent (apps/ai/prefixes.py). The
    prefixed string is what the provider receives; ``chunk.text`` is what is stored.
    Each request also says it is a passage (``input_type=INPUT_TYPE_DOCUMENT``,
    D-116), which is how Voyage learns what EmbeddingGemma reads from the prefix.

    A chunk that exhausts MAXIMUM_EMBED_ATTEMPTS, or that the provider answers
    unusably for, is counted and gets no row. Every other chunk gets one. The caller
    turns the count into a status: all failed is "Indexing failed", some failed is
    "Partially indexed", none failed is "Indexed" (section 7.8).
    """
    # Looked up on the module at call time, never from-imported: the suite's autouse
    # fixture replaces this attribute with a stub, and a name bound at import time
    # would quietly reach a real provider instead (docs/ai-provider.md section 6).
    service = apps.ai.get_ai_service()

    failed_chunk_count = 0
    for chunk in chunks:
        # Two different strings, deliberately: the prefixed one is embedded, the
        # verbatim one is stored. A prefix in chunk_text would be read back out into
        # answers, citations and snippets (FR-12), and chunking.py keeps each chunk a
        # verbatim substring of its source so that cannot happen.
        result = _embed_one(service, document_text(title, chunk.text))
        if result is None:
            failed_chunk_count += 1
            continue
        ContentChunk.objects.create(
            source_type=source_type,
            source_id=source_id,
            chunk_index=chunk.index,
            chunk_text=chunk.text,  # never the prefixed form
            embedding=result.vectors[0],
            # From the response, not from settings (risk R10).
            embedding_model=result.model,
            embedding_dimension=result.dimension,
            # Stamped from the source, so FR-11 filters before ranking (D-17).
            visible_to_roles=list(visible_to_roles),
        )
    return failed_chunk_count


def _embed_one(service, text: str) -> EmbeddingResult | None:
    """One chunk's embedding, or None when the chunk could not be embedded.

    MAXIMUM_EMBED_ATTEMPTS is a TOTAL: one initial call plus two retries (D-19).
    NFR-19's sibling test asserts the provider was called exactly three times before
    the item was flagged, which is what stops the constant being read as a retry
    count and quietly reduced to 2.
    """
    for _attempt in range(MAXIMUM_EMBED_ATTEMPTS):
        try:
            result = service.embed([text], input_type=INPUT_TYPE_DOCUMENT)
        except ProviderRefused:
            # A bad key or an exhausted quota (D-118): a retry would be refused the same
            # way, so the chunk fails now. The provider has logged the cause.
            return None
        except ProviderUnavailable:
            # A transient outage, or a rate limit. Retry; the loop bound is the whole policy.
            continue
        if _is_usable(result):
            return result
        # A usable-looking response that is not usable — see _is_usable. Retrying a
        # misconfigured provider cannot help, so the chunk fails now rather than
        # after two more identical answers.
        return None
    return None


def _is_usable(result) -> bool:
    """Whether a response can be stored as a vector for exactly one chunk.

    The dimension check is the FR-08 embedding-consistency clause at its earliest
    enforceable point. pgvector would refuse a vector of the wrong width anyway, but
    as an opaque database error part-way through a transaction that also holds the
    document row; failing the chunk deliberately keeps the reason legible and lets
    the rest of the document index. Switching providers is a full re-index event
    (``manage.py reindex``), never a mixed table.
    """
    if not result.vectors or len(result.vectors) != 1:
        return False
    if result.dimension != settings.EMBEDDING_DIMENSION:
        return False
    # A provider that declares one width and returns another would store a vector
    # the recorded dimension does not describe.
    return len(result.vectors[0]) == result.dimension
