"""Test double for the AI service (docs/ai-provider.md section 6).

The suite never reaches a live provider: the root conftest.py installs a
StubAIService for every test through apps.ai.get_ai_service. A test that needs
different behaviour (another dimension, an outage) builds its own instance and
patches it in the same way; apps/ai/tests/test_checks.py shows how.

As a second layer, conftest.py also points every provider endpoint at
UNROUTABLE_PROVIDER_URL for every test: a closed port on loopback, so a call that
bypasses the stub is refused at once instead of quietly answered by a developer's
running FLM server. apps/ai/tests/test_no_live_provider.py asserts both layers.
"""

import hashlib
import random

# The SDKs are imported here, inside apps/ai, so tests elsewhere can run a real provider
# against a scripted endpoint without importing a vendor SDK themselves (CLAUDE.md
# section 4, apps/ai/tests/test_boundary.py). ``import anthropic`` is the installed SDK,
# never apps/ai/anthropic.py: Python 3 imports are absolute.
import anthropic as anthropic_sdk
import httpx2
import openai
from django.conf import settings

from apps.ai.base import (
    Assignment,
    DocumentClassification,
    EmbeddingResult,
    InputType,
    Passage,
    ProviderHealth,
    Statement,
    StatementList,
    TagScheme,
    TagSuggestion,
    Transcription,
)
from apps.ai.classification import classification_input
from apps.core.constants import REPOSITORY_TAG_DIMENSIONS

STUB_EMBEDDING_MODEL = "stub-embed"
# What the stub's classify_document reports (FR-10, D-104): a model name no provider has, one
# fixed confidence for every assignment, and a department no scheme lists, returned when the
# scheme has no departments so that a test of the scheme rule has an out-of-scheme value to
# see without building one.
#
# STUB_CONFIDENCE is 1.0, the top of the range, so the stub's assignments are applied whatever
# CLASSIFICATION_CONFIDENCE_THRESHOLD is. It was 0.9 until D-106's sweep moved the threshold to
# 0.95 (10 November 2026), and six route, command and hook tests that classify through the
# default stub then read their applied outcomes as held. A test of the provisional rule builds
# its own classification, with confidences derived from the threshold
# (apps/documents/tests/classification_builders.py), and never relies on this value.
STUB_CHAT_MODEL = "stub-chat"
STUB_CONFIDENCE = 1.0
STUB_OUT_OF_SCHEME_DEPARTMENT = "stub department"
# What the stub's transcribe reports (D-123): a model name no provider has, and a fixed
# text per segment, numbered by call so a test that sends several segments can see each one's
# text land in order.
STUB_ASR_MODEL = "stub-asr"


def stub_transcript_text(number: int) -> str:
    """The stub's text for the ``number``-th segment it transcribes, counting from 1."""
    return f"Stub transcript of segment {number}."

# Port 9 (discard) is closed on every development machine and CI runner, so a
# connect is actively refused rather than left to time out: about 2 s per attempt
# on Windows (measured, WinError 10061), less on Linux. Loopback, so nothing leaves
# the machine even in error.
UNROUTABLE_PROVIDER_HOST = "http://127.0.0.1:9"
UNROUTABLE_PROVIDER_URL = f"{UNROUTABLE_PROVIDER_HOST}/v1"


class StubAIService:
    """Deterministic AIService: fixed vectors, fixed statements, a scheme-derived
    classification, a numbered transcript per segment, no network, a call log."""

    def __init__(
        self,
        dimension: int | None = None,
        available: bool = True,
        detail: str = "stub provider",
        classification=None,
        transcription=None,
        transcription_available: bool = True,
    ):
        self.dimension = settings.EMBEDDING_DIMENSION if dimension is None else dimension
        self.available = available
        self.detail = detail
        # What classify_document returns instead of the scheme-derived default: a
        # DocumentClassification, or a callable of (title, text, scheme). See the method.
        self.classification = classification
        # What transcribe returns instead of the numbered default: a Transcription, or a
        # callable of (audio, filename). See the method. And what transcription_health reports.
        self.transcription = transcription
        self.transcription_available = transcription_available
        self.embed_calls: list[list[str]] = []
        # The input_type each embed() call carried (D-116), one entry per call, in step
        # with embed_calls.
        self.embed_input_types: list[InputType | None] = []
        self.generate_calls: list[tuple[str, list[Passage]]] = []
        self.classify_calls: list[tuple[str, str, TagScheme]] = []
        # One (audio bytes, filename) per transcribe() call (D-123).
        self.transcribe_calls: list[tuple[bytes, str]] = []

    def vector_for(self, text: str) -> list[float]:
        # Seeded from a content hash so the same text embeds to the same vector in
        # every process; Python's own hash() is salted per process.
        seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
        rng = random.Random(seed)
        return [rng.uniform(-1.0, 1.0) for _ in range(self.dimension)]

    def embed(self, texts: list[str], *, input_type: InputType | None = None) -> EmbeddingResult:
        if not texts:
            raise ValueError("embed() needs at least one text")
        self.embed_calls.append(list(texts))
        self.embed_input_types.append(input_type)
        return EmbeddingResult(
            vectors=[self.vector_for(text) for text in texts],
            model=STUB_EMBEDDING_MODEL,
            dimension=self.dimension,
        )

    def generate_statements(self, question: str, passages: list[Passage]) -> StatementList:
        self.generate_calls.append((question, list(passages)))
        if not passages:
            return StatementList(statements=[])
        first = passages[0]
        return StatementList(
            statements=[
                Statement(text=f"Stub statement answering {question!r}.", chunk_id=first.chunk_id)
            ]
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth(available=self.available, detail=self.detail)

    def classify_document(
        self, title: str, text: str, scheme: TagScheme
    ) -> DocumentClassification:
        """FR-10's operation, deterministic and derived from the scheme (D-104).

        By default: the scheme's FIRST document type; its FIRST department, or
        STUB_OUT_OF_SCHEME_DEPARTMENT (a value no scheme lists) when it has none; one tag per
        dimension that lists a value, that dimension's first, in Project, Process, Topic
        order; every confidence STUB_CONFIDENCE; ``model`` STUB_CHAT_MODEL; and
        ``input_truncated`` from the real ``classification_input``, so a long text is
        reported cut exactly as a provider would report it. The same scheme gives the same
        reply in every process.

        **Overriding it.** Pass ``classification=`` to the constructor, or set the attribute
        on an instance (the autouse ``stub_ai_service`` fixture's, for example). A
        DocumentClassification is returned as-is for every call. A callable is called with
        ``(title, text, scheme)`` and its return value returned, so a test can vary the
        reply per document, or raise ProviderUnavailable to stand in for an outage. Either
        way the call is recorded in ``classify_calls`` first.
        """
        self.classify_calls.append((title, text, scheme))
        override = self.classification
        if callable(override):
            return override(title, text, scheme)
        if override is not None:
            return override
        if not scheme.doc_types:
            raise ValueError("classify_document() needs a scheme with at least one document type")
        department = scheme.departments[0] if scheme.departments else STUB_OUT_OF_SCHEME_DEPARTMENT
        return DocumentClassification(
            doc_type=Assignment(value=scheme.doc_types[0], confidence=STUB_CONFIDENCE),
            department=Assignment(value=department, confidence=STUB_CONFIDENCE),
            tags=tuple(
                TagSuggestion(dimension=dimension, value=values[0], confidence=STUB_CONFIDENCE)
                for dimension in REPOSITORY_TAG_DIMENSIONS
                for values in [scheme.tags.get(dimension, ())]
                if values
            ),
            model=STUB_CHAT_MODEL,
            input_truncated=classification_input(text)[1],
        )

    def transcribe(self, audio: bytes, *, filename: str = "segment.wav") -> Transcription:
        """D-123's operation, deterministic: the n-th call returns ``stub_transcript_text(n)``.

        It does not read TRANSCRIPTION_PROVIDER: the route asks ``apps.ai.transcription_enabled()``
        before it calls this, and the providers' own refusal is tested against them
        (apps/ai/tests/test_transcription.py).

        **Overriding it.** Pass ``transcription=`` to the constructor, or set the attribute on an
        instance (the autouse ``stub_ai_service`` fixture's, for example). A Transcription is
        returned as-is for every call. A callable is called with ``(audio, filename)`` and its
        return value returned, so a test can raise ProviderUnavailable or ProviderRefused to stand
        in for an outage or a refusal. Either way the call is recorded in ``transcribe_calls``
        first.
        """
        self.transcribe_calls.append((audio, filename))
        override = self.transcription
        if callable(override):
            return override(audio, filename)
        if override is not None:
            return override
        return Transcription(text=stub_transcript_text(len(self.transcribe_calls)), model=STUB_ASR_MODEL)

    def transcription_health(self) -> ProviderHealth:
        return ProviderHealth(
            available=self.transcription_available,
            detail="stub transcription" if self.transcription_available else "stub transcription down",
        )


def scripted_openai_client(base_url: str, handler) -> openai.OpenAI:
    """An openai client whose every request ``handler`` answers in-process.

    ``handler`` takes an httpx2 request and returns an httpx2 response, as a MockTransport
    handler does. For instance, it can stand in for Voyage's /embeddings endpoint in the
    D-118 route tests. ``max_retries=0``, as production builds it (apps/ai/_openai_compat.py).
    """
    return openai.OpenAI(
        base_url=base_url,
        api_key="test-key",
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )


def anthropic_status_error(status: int, message: str) -> anthropic_sdk.APIStatusError:
    """The APIStatusError the anthropic SDK raises for ``status``, built without a live call."""
    request = httpx2.Request("POST", "https://api.anthropic.test/v1/messages")
    response = httpx2.Response(
        status, json={"type": "error", "error": {"message": message}}, request=request
    )
    return anthropic_sdk.APIStatusError(message, response=response, body=None)
