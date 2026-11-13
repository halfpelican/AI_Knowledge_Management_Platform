"""The AI service contract: docs/ai-provider.md section 1.

The operations are exactly the ones listed on ``AIService`` below, and the list is the
source of truth, not a count. Every AI call in the system goes through an AIService
obtained from apps.ai.get_ai_service(); no module outside apps/ai imports a vendor SDK
(CLAUDE.md section 4). ``classify_document`` arrived with FR-10 on 9 November 2026
(docs/decisions.md D-104), when NIT3004 asked for it and not before. ``transcribe`` and
``transcription_health`` arrived on 10 November 2026 with recording transcription
(D-123), when the user asked for it. ``summarise_meeting`` arrived on 11 November 2026 with
FR-16 (D-125), the same way.
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


# --- FR-10 classification (D-104) -------------------------------------------------------


@dataclass(frozen=True)
class TagScheme:
    """The established scheme one document is classified against (FR-10).

    Built by apps/documents/classification.py for the document's own audience, every role
    in its ``visible_to_roles`` (D-105): a grown value linked only to documents some member of
    that audience cannot read is left out, so a suggestion can never name a restricted project
    to a reader who may not know it exists (invariant 1). A value that is not grown (``Tag.grown``)
    is vocabulary and is in whatever its links; a grown one is in only while every role in the
    audience reads a source carrying it (D-105's dated note of 10 November 2026, night).
    ``doc_types`` is DOCUMENT_TYPES; ``departments`` are the active names of the department
    list an Administrator keeps on the Tags page (``Department``, D-129), a hidden (grown) one
    only while every role in the audience reads a document carrying it; ``tags`` maps each of
    Project, Process and Topic to its active tag names.
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


# --- Recording transcription (D-123) ---------------------------------------------


@dataclass(frozen=True)
class Transcription:
    """What ``transcribe`` returns for one recording segment: its text and the model that wrote it.

    ``text`` is the speech model's text as returned, with surrounding whitespace removed, and may
    be empty for a segment it found nothing to say about. It is a draft: nothing here is indexed,
    and a person corrects and confirms the whole transcript before FR-09 ingests it.
    """

    text: str
    model: str


# --- FR-16 meeting summaries (D-125) -------------------------------------------------------


@dataclass(frozen=True)
class SummaryElement:
    """One narrative sentence, decision or highlight, and the passages it names.

    ``passages`` are passage numbers as the reply gave them (``"P3"`` is 3), in the reply's
    order, without repeats. They are NOT verified here: whether each was among the passages
    sent is set membership done by the caller (apps/meetings/summaries.py, invariant 5).
    """

    text: str
    passages: tuple[int, ...]


@dataclass(frozen=True)
class ExtractedActionItem:
    """One action item as the model extracted it (FR-16, UC-04).

    ``owner`` and ``due`` are the transcript's own words, or None where it says nothing: the
    name as given ("Alex", "the facilities team") and the deadline as said ("next Friday"). Who
    that owner is on the system, and which date the phrase means, are application code
    (apps/meetings/owners.py and due_dates.py), never the model's judgement (D-125).
    """

    description: str
    owner: str | None
    due: str | None
    passages: tuple[int, ...]


@dataclass(frozen=True)
class MeetingSummaryDraft:
    """What ``summarise_meeting`` returns: a conforming reply, and nothing else (invariant 10).

    ``narrative`` holds 1 to MAXIMUM_SUMMARY_SENTENCES sentences; the other three may be empty,
    and an empty ``action_items`` is UC-04 A1's "section recorded as empty", not an omission,
    because the reply must carry the key. ``model`` names the chat model, for the summary's
    record (UC-04: "a record of the model that produced it").
    """

    narrative: tuple[SummaryElement, ...]
    decisions: tuple[SummaryElement, ...]
    highlights: tuple[SummaryElement, ...]
    action_items: tuple[ExtractedActionItem, ...]
    model: str


class ProviderUnavailable(Exception):
    """The provider could not be reached or did not respond usably.

    Raised by embed() on transport failures and server errors, by
    generate_statements() after MAXIMUM_GENERATION_ATTEMPTS, and by classify_document()
    after MAXIMUM_CLASSIFY_ATTEMPTS. The view layer turns it into 503 with the NFR-19
    notice; ingestion catches it and leaves the document unclassified (invariant 8, D-33).
    """


class ProviderRefused(ProviderUnavailable):
    """The provider refused the request with a 4xx other than a rate limit (D-118).

    A bad key, an unknown model, a malformed request or an exhausted credit: the same
    request would be refused again, so the retry loops stop at once instead of spending
    their remaining attempts. It is a ProviderUnavailable, so everything that catches that
    still does: the ask view answers NFR-19's 503 with its fixed notice, and classification
    leaves the document unclassified. The provider logs the cause before raising it
    (apps/ai/attempt_log.py). A 429 is not this: a rate limit passes, so it is a plain
    ProviderUnavailable and is retried.
    """


class MalformedSummary(ProviderUnavailable):
    """A meeting summary's replies broke SUMMARY_SCHEMA twice: the one retry FR-16 allows is spent.

    FR-16: "a malformed response triggers one retry". Raised by ``summarise_meeting`` after the
    second malformed reply, even with an attempt left (MAXIMUM_MALFORMED_SUMMARY_REPLIES,
    D-125). A ProviderUnavailable, so a caller that knows only outages still marks the run
    failed; apps/meetings records it under its own reason.
    """


class TranscriptionDisabled(ProviderUnavailable):
    """Recording transcription is switched off on this server: ``TRANSCRIPTION_PROVIDER=none``.

    Raised by ``transcribe`` before any call is made (D-123). It is a ProviderUnavailable,
    so a caller that only knows about outages still answers 503; the transcription route catches
    it first, to tell the page that transcription is not enabled here rather than that FLM is
    down. Never retried: the setting does not change between attempts.
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

    def transcribe(self, audio: bytes, *, filename: str = "segment.wav") -> Transcription:
        """The text of one recording segment, a 16-bit PCM WAV, as a draft (D-123).

        Only FLM has speech-to-text, so both providers send it to FLM's
        ``/v1/audio/transcriptions`` with ``FLM_ASR_MODEL``, whatever ``AI_PROVIDER`` is
        (apps/ai/transcription.py). Raises TranscriptionDisabled at once when
        ``TRANSCRIPTION_PROVIDER`` is ``none``. Otherwise a transport failure, a 5xx or a 429 is
        retried to MAXIMUM_TRANSCRIBE_ATTEMPTS (1 initial call + 2 retries), then
        ProviderUnavailable; any other 4xx is ProviderRefused at once (D-118).

        The caller has already refused a silent segment (apps/ingestion/audio.py): Whisper
        invents text from silence, so a segment that reaches this method is one worth sending.
        """
        ...

    def transcription_health(self) -> ProviderHealth:
        """Whether a segment sent now could be transcribed: a report that never raises.

        Unavailable when ``TRANSCRIPTION_PROVIDER`` is ``none`` or FLM does not answer. Available
        means FLM answered; it cannot mean that Whisper is loaded, because FLM's model list names
        its chat catalogue and not the speech model (D-123, "What it does not cover").
        """
        ...

    def summarise_meeting(self, title: str, passages: list[str]) -> MeetingSummaryDraft:
        """FR-16: one meeting's summary and action items, in one structured call (D-125).

        ``passages`` are the transcript's passages in order, FR-09's own chunks as the caller
        split them; the prompt labels them ``[P1]`` to ``[Pn]`` and every element of the reply
        must name at least one (apps/ai/summarisation.py). A reply that does not conform to
        SUMMARY_SCHEMA is no reply: a malformed reply gets one retry
        (MAXIMUM_MALFORMED_SUMMARY_REPLIES) and a failed call two (MAXIMUM_SUMMARY_ATTEMPTS,
        1 initial call + 2 retries), then ProviderUnavailable; any other 4xx is ProviderRefused
        at once (D-118). Verifying the passage numbers, matching owners and converting dates
        are application code over the returned draft, not the model's judgement.
        """
        ...
