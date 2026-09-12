"""The AI service contract: docs/ai-provider.md section 1.

Three operations, deliberately. Every AI call in the system goes through an
AIService obtained from apps.ai.get_ai_service(); no module outside apps/ai imports
a vendor SDK (CLAUDE.md section 4). Classification (FR-10) and summarisation
(FR-16) are NIT3004 work and get their own methods then, not speculatively now.
"""

from dataclasses import dataclass
from typing import Protocol


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
    def embed(self, texts: list[str]) -> EmbeddingResult: ...

    def generate_statements(self, question: str, passages: list[Passage]) -> StatementList: ...

    def health(self) -> ProviderHealth: ...
