"""FR-13's follow-up rewrite over the HTTP boundary: record-only, in name and in value.

apps/retrieval/tests/test_followup_rewrite.py tests the pipeline — what is embedded,
what falls back, what the row records. This file tests the one property that only
exists once there is a response body: **nothing the server sends carries the rewrite**,
neither the field name nor the rewrite's own text, on the ask reply or on the reopened
thread. The assertions are against ``response.content`` — every byte the client is
sent — for the reason test_ask.py gives: a parsed-field assertion would pass a body
that carried the value in a key this test did not think to look at.

``RECORD_ONLY_FIELDS`` is pinned here too: the existing disclosure tests iterate that
tuple against raw bodies, so the one line that keeps them covering this column is the
line asserting the column is in it.

The double restates test_ask.py's ControlledService premise — a fixed query vector, so
a chunk built at ``at_cosine(v)`` scores exactly ``v`` — plus a scripted rewrite, which
with a fixed vector changes nothing about ranking: ranking is the pipeline file's
subject, and this file's subject is the body bytes.
"""

from datetime import date
from math import sqrt

import pytest
from django.conf import settings

import apps.ai
from apps.ai.base import EmbeddingResult, FollowupRewrite, Statement, StatementList
from apps.api.answers import RECORD_ONLY_FIELDS
from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    EMPLOYEE_ROLE_NAME,
    RELEVANCE_THRESHOLD,
    SOURCE_TYPES,
)
from apps.documents.models import ContentChunk, Document
from apps.retrieval.models import Conversation, QueryLog

pytestmark = pytest.mark.django_db

ASK_URL = "/api/ask"
QUESTION = "How much annual leave do I get?"
FOLLOW_UP = "And who approves it for me?"
# Distinctive enough that a substring hit in a response body means the rewrite leaked,
# not that an ordinary word collided.
REWRITE = "Who approves annual leave requests for staff members?"
ABOVE = 0.80
assert ABOVE > RELEVANCE_THRESHOLD


def wide(*components):
    return list(components) + [0.0] * (settings.EMBEDDING_DIMENSION - len(components))


QUERY = wide(1.0)


def at_cosine(value):
    return wide(value, sqrt(1.0 - value * value))


class RewritingService:
    """test_ask.py's ControlledService, plus a scripted rewrite."""

    def __init__(self, *, rewrite=REWRITE):
        self.rewrite = rewrite
        self.embed_calls: list[list[str]] = []
        self.generate_calls: list[tuple] = []
        self.rewrite_calls: list[tuple] = []

    def embed(self, texts):
        self.embed_calls.append(list(texts))
        return EmbeddingResult(
            vectors=[list(QUERY)], model=STUB_EMBEDDING_MODEL,
            dimension=settings.EMBEDDING_DIMENSION,
        )

    def generate_statements(self, question, passages):
        self.generate_calls.append((question, list(passages)))
        # Echoes the question string it was handed, as test_ask.py's double does: if the
        # rewrite ever reached the prompt, its text would land in the statement, in the
        # reply bytes, and in the assertions below — the leak made observable.
        return StatementList(
            statements=[
                Statement(text=f"Grounded in: {question}", chunk_id=passages[0].chunk_id)
            ]
        )

    def rewrite_followup(self, question, prior_questions):
        self.rewrite_calls.append((question, list(prior_questions)))
        return FollowupRewrite(question=self.rewrite)

    def health(self):  # pragma: no cover - the answer path does not check health
        raise AssertionError("the answer path does not check provider health")


@pytest.fixture
def service(monkeypatch):
    double = RewritingService()
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: double)
    return double


@pytest.fixture
def answerable(employee):
    document = Document.objects.create(
        title="Leave policy", file_type="pdf", uploaded_by=employee,
        visible_to_roles=[EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME],
    )
    ContentChunk.objects.create(
        source_type=SOURCE_TYPES[0], source_id=document.id, chunk_index=0,
        chunk_text="Staff accrue twenty days of annual leave a year.",
        embedding=at_cosine(ABOVE), embedding_model=STUB_EMBEDDING_MODEL,
        embedding_dimension=settings.EMBEDDING_DIMENSION,
        visible_to_roles=[EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME],
    )
    return document


def two_turns(session_client, service):
    """Turn 1 and the follow-up in one thread; returns the two ask responses."""
    conversation = Conversation.objects.create(user=session_client.user, title="Leave")
    first = session_client.client.post(
        ASK_URL, {"question": QUESTION, "conversation_id": str(conversation.pk)}, format="json"
    )
    second = session_client.client.post(
        ASK_URL, {"question": FOLLOW_UP, "conversation_id": str(conversation.pk)}, format="json"
    )
    return conversation, first, second


def test_retrieval_rewrite_is_a_record_only_field():
    """The one line that keeps every RECORD_ONLY_FIELDS disclosure test covering it."""
    assert "retrieval_rewrite" in RECORD_ONLY_FIELDS


def test_no_reply_byte_carries_the_rewrite_in_name_or_value(
    session_client, service, answerable
):
    """Both turns' replies, from both roles: no field named for it, no text of it."""
    conversation, first, second = two_turns(session_client, service)

    assert first.status_code == 200 and second.status_code == 200
    assert service.rewrite_calls == [(FOLLOW_UP, [QUESTION])]  # the rewrite genuinely ran
    row = QueryLog.objects.get(question=FOLLOW_UP)
    assert row.retrieval_rewrite == REWRITE  # and the row genuinely records it
    for response in (first, second):
        raw = response.content.decode()
        assert "retrieval_rewrite" not in raw
        assert REWRITE not in raw


def test_the_reopened_thread_carries_the_rewrite_nowhere(session_client, service, answerable):
    """The other reader of these rows: GET /api/conversations/{id}, raw bytes."""
    conversation, first, second = two_turns(session_client, service)
    assert QueryLog.objects.get(question=FOLLOW_UP).retrieval_rewrite == REWRITE

    reopened = session_client.client.get(f"/api/conversations/{conversation.pk}")

    assert reopened.status_code == 200
    raw = reopened.content.decode()
    assert "retrieval_rewrite" not in raw
    assert REWRITE not in raw
    # The turns still hold the questions as asked — the rewrite replaced neither.
    assert QUESTION in raw and FOLLOW_UP in raw
