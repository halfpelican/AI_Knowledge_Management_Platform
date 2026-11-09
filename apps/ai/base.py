"""The AI service contract: docs/ai-provider.md section 1.

The operations are exactly the ones listed on ``AIService`` below, and the list is the
source of truth, not a count. Every AI call in the system goes through an AIService
obtained from apps.ai.get_ai_service(); no module outside apps/ai imports a vendor SDK
(CLAUDE.md section 4). ``classify_document`` arrived with FR-10 on 9 November 2026
(docs/decisions.md D-104), when NIT3004 asked for it and not before. Summarisation (FR-16)
gets its own method the same way, then, not speculatively now.
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


# --- FR-10 classification (D-104) -------------------------------------------------------


@dataclass(frozen=True)
class TagScheme:
    """The established scheme one document is classified against (FR-10).

    Built by apps/documents/classification.py for the document's own audience, every role
    in its ``visible_to_roles`` (D-105): a value linked only to documents some member of that
    audience cannot read is left out, so a suggestion can never name a restricted project to
    a reader who may not know it exists (invariant 1). A value with no links at all is
    vocabulary only and is always in. ``doc_types`` is DOCUMENT_TYPES; ``departments`` are
    distinct non-blank ``Documents.department`` values; ``tags`` maps each of Project,
    Process and Topic to its active tag names.
    """

    doc_types: tuple[str, ...]
    departments: tuple[str, ...]
    tags: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class Assignment:
    """One suggested value and the confidence the model reported for it, in [0, 1]."""

    value: str
    confidence: float


@dataclass(frozen=True)
class TagSuggestion:
    """One suggested tag: its dimension (Project, Process or Topic), value and confidence."""

    dimension: str
    value: str
    confidence: float


@dataclass(frozen=True)
class DocumentClassification:
    """What ``classify_document`` returns: a conforming reply, and nothing else (invariant 10).

    ``doc_type.value`` is one of the scheme's ``doc_types``; the parser rejects any other reply.
    ``department`` and ``tags`` are the model's suggestions AS MADE: whether a value is in the
    scheme, provisional or applied is decided by application code afterwards
    (apps/documents/classification.py, D-105), never here. ``model`` names the chat model, for
    the DocumentAnalysis record. ``input_truncated`` says the text was cut at
    CLASSIFICATION_INPUT_TOKENS before it was sent, which the record keeps rather than hides.
    """

    doc_type: Assignment
    department: Assignment
    tags: tuple[TagSuggestion, ...]
    model: str
    input_truncated: bool


class ProviderUnavailable(Exception):
    """The provider could not be reached or did not respond usably.

    Raised by embed() on transport failures and server errors, by
    generate_statements() after MAXIMUM_GENERATION_ATTEMPTS, and by classify_document()
    after MAXIMUM_CLASSIFY_ATTEMPTS. The view layer turns it into 503 with the NFR-19
    notice; ingestion catches it and leaves the document unclassified (invariant 8, D-33).
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

    def classify_document(
        self, title: str, text: str, scheme: TagScheme
    ) -> DocumentClassification:
        """FR-10: the type, department and tags of one document, in one structured call.

        The prompt shows the model the scheme's fixed types, departments and tag values and
        the document's title and opening text (apps/ai/classification.py). A reply that does
        not conform to CLASSIFICATION_SCHEMA, including a ``doc_type`` outside the four, is
        no reply: retried to MAXIMUM_CLASSIFY_ATTEMPTS (1 initial call + 2 retries), then
        ProviderUnavailable. The scheme rule, the provisional rule and provenance are
        application code over the returned suggestions, not the model's judgement (D-105).
        """
        ...
