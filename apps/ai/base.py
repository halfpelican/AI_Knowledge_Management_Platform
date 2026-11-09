"""The AI service contract: docs/ai-provider.md section 1.

The operations are exactly the ones ``AIService`` declares below — the enumerated list
is the source of truth, not a count. Every AI call in the system goes through an
AIService obtained from apps.ai.get_ai_service(); no module outside apps/ai imports
a vendor SDK (CLAUDE.md section 4). Nothing is added speculatively: summarisation
(FR-16) is NIT3004 work and gets its own method then.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Protocol

if TYPE_CHECKING:
    # The observer's record type. Imported for type checkers only: it lives beside the
    # attempt loop that builds it (apps/ai/generation.py), which imports this module, so
    # a runtime import here would be a cycle.
    from apps.ai.generation import GenerationAttempt


@dataclass(frozen=True)
class Passage:
    chunk_id: str  # the identifier citation verification checks against
    text: str


@dataclass(frozen=True)
class Statement:
    text: str
    chunk_id: str  # the passage this statement was drawn from


@dataclass(frozen=True)
class StatementList:
    statements: list[Statement]


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]
    model: str  # recorded against every chunk (FR-08, risk R10)
    dimension: int


@dataclass(frozen=True)
class ProviderHealth:
    available: bool
    detail: str


@dataclass(frozen=True)
class FollowupRewrite:
    """One standalone question, rewritten from a follow-up and its prior questions (FR-13).

    USED FOR RETRIEVAL ONLY. The string is embedded as the query in place of the plain
    composed join; it never enters a generation prompt, a reply, a citation or any
    user-visible text, and apps/retrieval/pipeline.py is the one consumer. One field,
    deliberately: anything else a rewrite could carry would be something a later reader
    might surface.
    """

    question: str


class ProviderUnavailable(Exception):
    """The provider could not be reached or did not respond usably.

    Raised by embed() on transport failures and server errors, and by
    generate_statements() after MAXIMUM_GENERATION_ATTEMPTS. The view layer turns it
    into 503 with the NFR-19 notice.
    """


class AIService(Protocol):
    def embed(self, texts: list[str]) -> EmbeddingResult: ...

    def generate_statements(
        self,
        question: str,
        passages: list[Passage],
        *,
        on_attempt: Callable[["GenerationAttempt"], None] | None = None,
    ) -> StatementList:
        """Statements drawn only from ``passages``, each tagged with a passage id.

        ``on_attempt`` is an OBSERVER, not an operation. It is keyword-only, defaults to
        None, and is called once per generation attempt with a record the method already
        computes and would otherwise discard. It cannot change what is asked of the model
        or what comes back, and an exception raised inside it is swallowed
        (apps/ai/generation.py), so a measuring instrument cannot alter the attempt count
        it is measuring. Nothing under ``apps/`` passes it — asserted by
        apps/ai/tests/test_observer_is_not_used_in_application_code.py — and it exists so
        scripts/citation_harness.py can report schema conformance per response with a
        separate first-attempt rate, as docs/flm-baseline.md does.

        It is declared here, in the signature, rather than left to the implementations:
        a contract and its implementations differing by a parameter is the defect this
        project keeps finding elsewhere, and it is not worth shipping deliberately.
        """
        ...

    def health(self) -> ProviderHealth: ...

    def rewrite_followup(self, question: str, prior_questions: list[str]) -> FollowupRewrite:
        """One standalone question merging the prior questions' referents into this one (FR-13).

        The input is QUESTIONS ONLY, never answers (D-42), and the output is used for
        RETRIEVAL ONLY: the pipeline embeds it in place of the plain composed join and
        nothing else reads it. It never enters a prompt, a reply or a citation.

        ONE attempt, no retry constant. A reply that does not conform to the one-field
        rewrite schema is no reply at all (invariant 10's shape): the implementation
        raises — RewriteViolation for a non-conforming or over-length reply,
        ProviderUnavailable for a transport failure — and the CALLER falls back to the
        composed join, so an ask can never fail because the rewrite did
        (apps/retrieval/pipeline.py holds the fallback; apps/ai/rewrite.py the schema,
        the prompt and the single-attempt runner both implementations share).
        """
        ...
