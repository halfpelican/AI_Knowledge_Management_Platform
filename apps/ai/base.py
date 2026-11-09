"""The AI service contract: docs/ai-provider.md section 1.

Three operations, deliberately. Every AI call in the system goes through an
AIService obtained from apps.ai.get_ai_service(); no module outside apps/ai imports
a vendor SDK (CLAUDE.md section 4). Classification (FR-10) and summarisation
(FR-16) are NIT3004 work and get their own methods then, not speculatively now.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Literal, Protocol

if TYPE_CHECKING:
    # The observer's record type. Imported for type checkers only: it lives beside the
    # attempt loop that builds it (apps/ai/generation.py), which imports this module, so
    # a runtime import here would be a cycle.
    from apps.ai.generation import GenerationAttempt

# What the texts passed to embed() are (D-116): a question being asked, or a passage
# being indexed. These are Voyage's own two values for its ``input_type`` field.
INPUT_TYPE_QUERY = "query"
INPUT_TYPE_DOCUMENT = "document"
InputType = Literal["query", "document"]


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


class ProviderUnavailable(Exception):
    """The provider could not be reached or did not respond usably.

    Raised by embed() on transport failures and server errors, and by
    generate_statements() after MAXIMUM_GENERATION_ATTEMPTS. The view layer turns it
    into 503 with the NFR-19 notice.
    """


class AIService(Protocol):
    def embed(self, texts: list[str], *, input_type: InputType | None = None) -> EmbeddingResult:
        """One vector per text, with the model and width that produced them.

        ``input_type`` says what the texts are: INPUT_TYPE_QUERY for a question,
        INPUT_TYPE_DOCUMENT for a passage being indexed, or None where it makes no
        difference, as in a dimension probe. It is keyword-only and defaults to None.
        Unlike ``on_attempt`` it does change what the model is asked, which is why it
        has a decision of its own (D-116): Voyage puts a different instruction in
        front of each side. EmbeddingGemma learns the same thing from the task prefix
        in the text itself (apps/ai/prefixes.py), so the FLM provider accepts the
        argument and sends nothing for it.
        """
        ...

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
