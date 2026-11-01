"""Embedding the question (FR-12 step 2, proposal section 7.10).

One call, one vector, and one name: the ``EmbeddingResult`` returned here carries
both the query vector and the model that produced it, and that model name is what
``scoping.candidate_chunks`` matches against every chunk's recorded
``embedding_model``. Taking the name from the response rather than from
``settings.FLM_EMBED_MODEL`` is the point of the return type. Ingestion records what
the provider answered with (apps/ingestion/embedding.py); retrieval asks the same
question of the same place. A name copied from configuration on either side would
describe what was expected instead of what happened, and the two sides could then
disagree while both looked correct — which is exactly the silent corruption risk R10
is about (docs/ai-provider.md section 4).

The retry policy is the project's uniform one: MAXIMUM_EMBED_ATTEMPTS is a TOTAL of
one initial call plus two retries (D-19), and ProviderUnavailable is allowed out
after the third. The view layer turns that into a 503 carrying the NFR-19 notice;
it is not caught and converted into a no-answer, because a provider outage is not
the same event as "nothing in the corpus answers this" and the two must not share a
code path (CLAUDE.md invariant 7).

What is sent is the question wrapped in the embedding model's query task prefix
(apps/ai/prefixes.py), which is how EmbeddingGemma is told it is embedding a question
rather than a passage. The prefix exists only on the wire: the caller's question is
what is logged, shown and stored, and a model that does not take prefixes receives
the question unchanged.

Two failures, one exception, and deliberately different attempt counts. A transient
outage is retried to MAXIMUM_EMBED_ATTEMPTS, because the next call may well succeed.
A response that arrives looking fine and is not usable — the wrong number of vectors,
a declared width that is not EMBEDDING_DIMENSION, or a vector whose actual width is
not the one declared — is a misconfigured provider, and it is NOT retried: three
identical wrong answers are the same wrong answer three times.
apps/ingestion/embedding.py settled this for the chunk side, where its ``_is_usable``
check is followed by "Retrying a misconfigured provider cannot help, so the chunk
fails now rather than after two more identical answers". A query is the same event
with a different consequence — a query has no partially indexed state to fail into —
so it raises instead of being counted and skipped. Both failures leave as
ProviderUnavailable, because the view's 503 is the right answer to either: the system
could not answer for a reason that is nothing to do with the question.

Allowing an unusable response through would be worse than either. Ranking would hit
an empty ``vectors`` as an IndexError — a 500 that tells the user nothing — or
compute a cosine over mismatched widths and return a plausible wrong answer, which is
precisely the silent corruption risk R10 exists to prevent.

Question length is not validated here. FR-12's bounds, MINIMUM_QUESTION_LENGTH and
MAXIMUM_QUESTION_LENGTH, are checked once at the pipeline's entry point so that the
400 is returned before any provider is called at all; this function embeds what it
is given.
"""

from django.conf import settings

import time

import apps.ai
from apps.ai import attempt_log
from apps.ai.base import EmbeddingResult, ProviderUnavailable
from apps.ai.prefixes import query_text
from apps.core.constants import MAXIMUM_EMBED_ATTEMPTS


def embed_question(question: str) -> EmbeddingResult:
    """The question's vector and the model that produced it.

    Raises ProviderUnavailable when the provider was unreachable for every attempt,
    or when it answered once with something that cannot be used as a query vector.
    """
    # Looked up on the module at call time, never from-imported: the suite's autouse
    # fixture replaces this attribute with a stub, and a name bound at import time
    # would quietly reach a real provider instead (docs/ai-provider.md section 6).
    service = apps.ai.get_ai_service()
    # The query side of the model's task prefixes (apps/ai/prefixes.py). The prefixed
    # string is what the provider sees; nothing else is affected, and the question the
    # caller passed in is what gets logged and shown.
    prefixed = query_text(question)

    for attempt in range(1, MAXIMUM_EMBED_ATTEMPTS + 1):  # 1 initial call + 2 retries
        started = time.perf_counter()
        try:
            result = service.embed([prefixed])
        except ProviderUnavailable as exc:
            attempt_log.failed_attempt(
                "question embedding", attempt, MAXIMUM_EMBED_ATTEMPTS, time.perf_counter() - started,
                attempt_log.cause_of(exc), str(exc),
            )
            # A transient outage. Retry; the loop bound is the whole policy, and the
            # last failure is re-raised with its own message rather than replaced.
            if attempt == MAXIMUM_EMBED_ATTEMPTS:
                raise
            continue
        problem = _usability_problem(result)
        if problem is not None:
            attempt_log.failed_attempt(
                "question embedding", attempt, MAXIMUM_EMBED_ATTEMPTS, time.perf_counter() - started,
                "unusable reply", problem,
            )
            # Not retried, and not on the next attempt either: the remaining attempts
            # would spend two more calls collecting the same answer.
            raise ProviderUnavailable(f"The embedding provider {problem}.")
        return result
    raise AssertionError("unreachable: the loop returns or raises")  # pragma: no cover


def _usability_problem(result: EmbeddingResult) -> str | None:
    """What is wrong with this response, or None if it can be used as a query vector.

    The three conditions are the ones apps/ingestion/embedding.py::_is_usable()
    checks, for the reasons given there, and the two must not diverge: a response the
    chunk side would refuse to store is not one the query side may rank against.
    Written out here rather than imported, because ``_is_usable`` is private to
    ingestion, answers only true or false, and this needs to say what was wrong so the
    503 and its log line name the misconfiguration instead of merely reporting it.
    """
    if len(result.vectors) != 1:
        return f"returned {len(result.vectors)} vectors for one question, not exactly one"
    if result.dimension != settings.EMBEDDING_DIMENSION:
        return (
            f"declared dimension {result.dimension}, but this index is built at "
            f"{settings.EMBEDDING_DIMENSION}"
        )
    if len(result.vectors[0]) != result.dimension:
        # The least visible form: both numbers look plausible and only the pair is
        # wrong. pgvector catches it on the chunk side; nothing would catch it here.
        return (
            f"declared dimension {result.dimension} but returned a vector of width "
            f"{len(result.vectors[0])}"
        )
    return None
