"""Builders for the FR-10 apply-layer tests: classifications and schemes made by hand (D-105).

Not named test_*.py, so pytest collects the tests and not the builders, as
apps/ingestion/tests/builders.py is arranged. The three confidences are derived from
CLASSIFICATION_CONFIDENCE_THRESHOLD and never written as numbers, so the tests follow the
constant when D-106's sweep moves it. EPSILON is the resolution of the decimal(4,3) columns:
the smallest difference the record can show.
"""

from apps.ai.base import Assignment, DocumentClassification, TagScheme, TagSuggestion
from apps.ai.testing import StubAIService
from apps.core.constants import (
    CLASSIFICATION_CONFIDENCE_THRESHOLD,
    DOCUMENT_TYPES,
    PROCESS_DIMENSION,
    PROJECT_DIMENSION,
    TOPIC_DIMENSION,
)
from apps.documents.models import Department

EPSILON = 0.001
BELOW_THRESHOLD = round(CLASSIFICATION_CONFIDENCE_THRESHOLD - EPSILON, 3)
AT_THRESHOLD = CLASSIFICATION_CONFIDENCE_THRESHOLD
ABOVE_THRESHOLD = round(min(1.0, CLASSIFICATION_CONFIDENCE_THRESHOLD + EPSILON), 3)

POLICY, PROCEDURE, REPORT, MEETING_PAPER = DOCUMENT_TYPES
STUB_CHAT_MODEL = "stub-chat"


def classification(
    *,
    doc_type=POLICY,
    type_confidence=ABOVE_THRESHOLD,
    department="",
    department_confidence=ABOVE_THRESHOLD,
    tags=(),
    model=STUB_CHAT_MODEL,
    input_truncated=False,
) -> DocumentClassification:
    """A DocumentClassification as the parser would return it.

    ``tags`` is a sequence of ``(dimension, value, confidence)`` triples.
    """
    return DocumentClassification(
        doc_type=Assignment(value=doc_type, confidence=type_confidence),
        department=Assignment(value=department, confidence=department_confidence),
        tags=tuple(
            TagSuggestion(dimension=dimension, value=value, confidence=confidence)
            for dimension, value, confidence in tags
        ),
        model=model,
        input_truncated=input_truncated,
    )


def scheme(*, departments=(), project=(), process=(), topic=()) -> TagScheme:
    """A scheme written by hand, so the apply tests do not depend on ``tag_scheme``.

    **Each department it lists is made an active ``Department`` row,** unless a row of that name
    exists already, ignoring case as the list's uniqueness does. That is what ``tag_scheme``'s
    departments always are, and rule 3 relies on it: it discards a listed department with no active
    row, as one retired or deleted since the scheme was built (D-129's security review, finding F2).
    A row that exists is left as it is, so a test can retire a department and still list it. The
    database writes mean callers must be database tests, as every one is.
    """
    for name in departments:
        if not Department.objects.filter(name__iexact=name).exists():
            Department.objects.create(name=name)
    return TagScheme(
        doc_types=tuple(DOCUMENT_TYPES),
        departments=tuple(departments),
        tags={
            PROJECT_DIMENSION: tuple(project),
            PROCESS_DIMENSION: tuple(process),
            TOPIC_DIMENSION: tuple(topic),
        },
    )


class RecordingClassifier(StubAIService):
    """The suite's stub plus a scripted ``classify_document`` that records every call.

    Installed the way conftest.py installs the stub, ``monkeypatch.setattr(apps.ai,
    "get_ai_service", lambda: service)``, because ``classify_document_now`` looks the function
    up on the module at call time.
    """

    def __init__(self, result=None, error=None):
        super().__init__()
        self.result = result
        self.error = error
        self.classify_calls: list[tuple[str, str, TagScheme]] = []

    def classify_document(self, title, text, scheme):
        self.classify_calls.append((title, text, scheme))
        if self.error is not None:
            raise self.error
        return self.result
