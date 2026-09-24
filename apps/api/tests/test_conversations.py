"""``/api/conversations`` — FR-13's threads: list, create, and reopen with the thread.

FR-13's Database clause is ``Conversations (Create, Read, Update)``. What its Front-End
clause needs from those three is here: "previous conversations are listed and can be
reopened", and "the active thread can be cleared to begin a new topic", which is starting
a new conversation rather than deleting one — so there is no delete route and a test says
so.

Three properties carry more than their line count:

- **Every route is scoped to ``request.user``, and someone else's id is 404.** A 403 would
  confirm the id names a real thread, so a caller could enumerate the existence of other
  people's conversations one request at a time (CLAUDE.md invariant 1, and the rule
  ``GET /api/meetings/{id}`` already follows).
- **A reopened thread renders from the server**, so the questions and cited statements a
  user sees after signing in on another machine are the ones that were logged.
- **A reopened thread discloses no more than the live reply did.** ``no_answer_reason`` and
  ``rejected_count`` are record-only, and a thread read is a second route past them. The
  assertion is against the raw rendered body, for the reason test_ask.py gives.

The questions here go through ``POST /api/ask`` with the autouse stub and an empty corpus,
so every turn is no-answer path A. That is deliberate: what is under test is where a
thread's title comes from and what a thread read returns, neither of which depends on an
answer having been produced.
"""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.api.answers import RECORD_ONLY_FIELDS
from apps.api.views import NEW_CONVERSATION_TITLE
from apps.core.constants import (
    MAXIMUM_QUESTION_LENGTH,
    MINIMUM_QUESTION_LENGTH,
    NO_ANSWER_MESSAGE,
    NO_STATEMENT_VERIFIED,
)
from apps.core.models import NAME_MAX_LENGTH
from apps.retrieval.models import AnswerCitation, Conversation, QueryLog

pytestmark = pytest.mark.django_db

CONVERSATIONS_URL = "/api/conversations"
ASK_URL = "/api/ask"

QUESTION = "How do I request annual leave?"
SECOND_QUESTION = "And who signs it off for me?"
assert MINIMUM_QUESTION_LENGTH <= len(QUESTION) <= MAXIMUM_QUESTION_LENGTH

CONVERSATION_FIELDS = {"conversation_id", "title", "last_updated_at"}


def detail_url(conversation_id):
    return f"{CONVERSATIONS_URL}/{conversation_id}"


def ask_in(client, conversation_id, question=QUESTION):
    return client.post(
        ASK_URL, {"question": question, "conversation_id": str(conversation_id)}, format="json"
    )


# --- Create ---------------------------------------------------------------------------------


def test_a_thread_is_created_with_the_title_the_client_sent(session_client):
    """201 with the conversation object, from an Employee session and an Administrator
    session. The row belongs to the caller; no request body names a user."""
    response = session_client.client.post(
        CONVERSATIONS_URL, {"title": "Leave policy questions"}, format="json"
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == CONVERSATION_FIELDS
    assert body["title"] == "Leave policy questions"
    conversation = Conversation.objects.get(pk=body["conversation_id"])
    assert conversation.user == session_client.user


def test_a_conversation_object_never_carries_the_user(employee_client):
    """Every thread a caller can reach is their own, so a user id in the object would only
    echo the requester back and would invite a client to send one."""
    response = employee_client.post(CONVERSATIONS_URL, {"title": "Leave"}, format="json")

    assert set(response.json()) == CONVERSATION_FIELDS
    assert "user" not in response.content.decode()


def test_a_thread_created_without_a_title_is_named_from_its_first_question(employee_client):
    """D-43. FR-13's interface clears the thread and lets the user start typing; it never
    asks them to name a topic first, so a title is optional on create and the first
    question supplies one. Until then the placeholder keeps the list entry legible."""
    created = employee_client.post(CONVERSATIONS_URL, {}, format="json").json()
    assert created["title"] == NEW_CONVERSATION_TITLE

    assert ask_in(employee_client, created["conversation_id"]).status_code == 200

    [listed] = employee_client.get(CONVERSATIONS_URL).json()
    assert listed["title"] == QUESTION


def test_a_second_question_does_not_rename_the_thread(employee_client):
    """The name comes from the first question of the thread and then stands: a list whose
    entries changed under the user every time they asked something would be unusable."""
    created = employee_client.post(CONVERSATIONS_URL, {}, format="json").json()
    ask_in(employee_client, created["conversation_id"])
    ask_in(employee_client, created["conversation_id"], SECOND_QUESTION)

    [listed] = employee_client.get(CONVERSATIONS_URL).json()
    assert listed["title"] == QUESTION


def test_a_title_the_user_chose_is_never_overwritten(employee_client):
    created = employee_client.post(
        CONVERSATIONS_URL, {"title": "My own name for this"}, format="json"
    ).json()

    ask_in(employee_client, created["conversation_id"])

    [listed] = employee_client.get(CONVERSATIONS_URL).json()
    assert listed["title"] == "My own name for this"


def test_a_long_first_question_is_truncated_to_fit_the_title(employee_client):
    """MAXIMUM_QUESTION_LENGTH is 500 and ``Conversations.title`` holds 255, so the derived
    title is truncated rather than the turn refused."""
    long_question = "Why " + "x" * (MAXIMUM_QUESTION_LENGTH - 10) + "?"
    created = employee_client.post(CONVERSATIONS_URL, {}, format="json").json()

    assert ask_in(employee_client, created["conversation_id"], long_question).status_code == 200

    conversation = Conversation.objects.get(pk=created["conversation_id"])
    assert 0 < len(conversation.title) <= NAME_MAX_LENGTH
    assert conversation.title != NEW_CONVERSATION_TITLE
    # And the question itself is stored in full: the truncation is a display name only.
    assert QueryLog.objects.get().question == long_question


def test_a_blank_title_falls_back_to_the_placeholder(employee_client):
    body = employee_client.post(CONVERSATIONS_URL, {"title": "   "}, format="json").json()

    assert body["title"] == NEW_CONVERSATION_TITLE


# --- Read: the list ---------------------------------------------------------------------------


def test_only_the_callers_own_threads_are_listed_newest_activity_first(
    session_client, employee, administrator
):
    """"Previous conversations are listed" — the caller's, in the order they were last
    used, which is the order a person scans them in.

    A thread belonging to the other role's user is absent, and its existence is disclosed
    by nothing in the reply.
    """
    other = administrator if session_client.user == employee else employee
    older = Conversation.objects.create(user=session_client.user, title="Older thread")
    newer = Conversation.objects.create(user=session_client.user, title="Newer thread")
    theirs = Conversation.objects.create(user=other, title="Someone else's thread")
    # last_updated_at is auto_now, so a turn is what moves a thread up. Set it directly
    # here: this test is about the ordering, not about how it comes to be.
    Conversation.objects.filter(pk=older.pk).update(
        last_updated_at=timezone.now() - timedelta(hours=1)
    )

    response = session_client.client.get(CONVERSATIONS_URL)

    assert response.status_code == 200
    body = response.json()
    assert [entry["conversation_id"] for entry in body] == [str(newer.pk), str(older.pk)]
    raw = response.content.decode()
    assert str(theirs.pk) not in raw
    assert "Someone else's thread" not in raw


def test_a_turn_moves_its_thread_to_the_top_of_the_list(employee_client, employee):
    first = Conversation.objects.create(user=employee, title="First")
    second = Conversation.objects.create(user=employee, title="Second")
    assert [entry["title"] for entry in employee_client.get(CONVERSATIONS_URL).json()] == [
        "Second",
        "First",
    ]

    assert ask_in(employee_client, first.pk).status_code == 200

    # "First" keeps the name its owner gave it and moves to the top, because the pipeline
    # touched last_updated_at inside the log transaction for that turn.
    assert [entry["title"] for entry in employee_client.get(CONVERSATIONS_URL).json()] == [
        "First",
        "Second",
    ]


# --- Read: one thread and its turns -------------------------------------------------------------


STATEMENT_TEXTS = ["Twenty days.", "Your manager approves it."]


def build_thread(user, chunk):
    """A thread with two logged turns: one answered with two citations, one not answered.

    The rows are built directly rather than asked for through the pipeline, because what is
    under test is the read: a thread reopened long after the turns happened, from rows that
    are all the server has. The unanswered row carries a ``no_answer_reason`` and a
    ``rejected_count`` precisely so the leak test below has something to fail on.
    """
    conversation = Conversation.objects.create(user=user, title="Leave")
    answered = QueryLog.objects.create(
        user=user,
        conversation=conversation,
        question=QUESTION,
        answer_text=" ".join(STATEMENT_TEXTS),
        retrieved_chunk_ids=[chunk.id],
        answered=True,
        rejected_count=0,
    )
    for position, text in enumerate(STATEMENT_TEXTS, start=1):
        AnswerCitation.objects.create(
            query=answered, chunk=chunk, statement_text=text, position=position
        )
    unanswered = QueryLog.objects.create(
        user=user,
        conversation=conversation,
        question=SECOND_QUESTION,
        answer_text=None,
        retrieved_chunk_ids=[chunk.id],
        answered=False,
        no_answer_reason=NO_STATEMENT_VERIFIED,
        rejected_count=3,
    )
    return conversation, answered, unanswered


@pytest.fixture
def thread(session_client, content_chunk):
    """``build_thread`` for whichever role this parametrisation is running as."""
    return build_thread(session_client.user, content_chunk)


def test_a_reopened_thread_carries_its_turns_with_their_verified_citations(
    session_client, thread, content_chunk
):
    """FR-13: "previous conversations are listed and can be reopened", from both roles.

    Chronological, with each answered turn's statements in the order they were numbered in,
    so the reopened thread reads as it did when it was live.
    """
    conversation, _, _ = thread

    response = session_client.client.get(detail_url(conversation.pk))

    assert response.status_code == 200
    body = response.json()
    assert set(body) == CONVERSATION_FIELDS | {"turns"}
    first, second = body["turns"]
    assert set(first) == {"question", "answered", "asked_at", "message", "statements"}
    assert first["question"] == QUESTION
    assert first["answered"] is True
    assert first["message"] is None
    assert [statement["position"] for statement in first["statements"]] == [1, 2]
    assert [statement["text"] for statement in first["statements"]] == STATEMENT_TEXTS
    assert {statement["chunk_id"] for statement in first["statements"]} == {str(content_chunk.id)}
    assert second["question"] == SECOND_QUESTION
    assert second["answered"] is False
    assert second["message"] == NO_ANSWER_MESSAGE
    assert second["statements"] == []


def test_a_reopened_thread_discloses_neither_the_reason_nor_the_rejected_count(
    employee_client, employee, content_chunk
):
    """A thread read is a second route past two record-only columns, so it gets the same
    assertion the live reply gets: against every byte the client is sent."""
    conversation, _, unanswered = build_thread(employee, content_chunk)
    assert unanswered.no_answer_reason == NO_STATEMENT_VERIFIED and unanswered.rejected_count == 3

    raw = employee_client.get(detail_url(conversation.pk)).content.decode()

    for field in RECORD_ONLY_FIELDS:
        assert field not in raw
    assert NO_STATEMENT_VERIFIED not in raw
    # Nor the identifiers of everything that was put in front of the model: that is the
    # traceability record, not what the reader was shown.
    assert "retrieved_chunk_ids" not in raw


def test_an_empty_thread_reads_as_a_thread_with_no_turns(employee_client, employee):
    conversation = Conversation.objects.create(user=employee, title="Nothing asked yet")

    body = employee_client.get(detail_url(conversation.pk)).json()

    assert body["turns"] == []
    assert body["title"] == "Nothing asked yet"


# --- 404: someone else's thread, and one that does not exist -------------------------------------


def test_another_users_thread_is_404_on_read(session_client, employee, administrator):
    """Not 403: a 403 confirms the id names a real thread, and a caller must not be able to
    enumerate the existence of another user's conversations."""
    other = administrator if session_client.user == employee else employee
    theirs = Conversation.objects.create(user=other, title="Their thread")

    response = session_client.client.get(detail_url(theirs.pk))

    assert response.status_code == 404
    assert "Their thread" not in response.content.decode()


def test_an_unknown_thread_is_404(employee_client):
    assert employee_client.get(detail_url(uuid.uuid4())).status_code == 404


# --- 401 -------------------------------------------------------------------------------------------


def test_the_conversation_routes_are_401_anonymously(api_client, employee):
    conversation = Conversation.objects.create(user=employee, title="Leave")

    assert api_client.get(CONVERSATIONS_URL).status_code == 401
    assert api_client.post(CONVERSATIONS_URL, {"title": "Mine now"}, format="json").status_code == 401
    assert api_client.get(detail_url(conversation.pk)).status_code == 401
    assert Conversation.objects.count() == 1


# --- No Delete ---------------------------------------------------------------------------------------


def test_there_is_no_delete_route(employee_client, employee):
    """FR-13's Database clause is Create, Read, Update. Clearing the active thread to begin
    a new topic is starting a new conversation, and the old one is FR-19 evidence: its
    QueryLog rows survive a deletion on purpose (D-12), so deleting the thread would remove
    only the part a user could still read."""
    conversation = Conversation.objects.create(user=employee, title="Leave")

    assert employee_client.delete(detail_url(conversation.pk)).status_code == 405
    assert employee_client.delete(CONVERSATIONS_URL).status_code == 405
    assert Conversation.objects.filter(pk=conversation.pk).exists()
