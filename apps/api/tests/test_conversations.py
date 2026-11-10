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

The questions in the create and list sections go through ``POST /api/ask`` with the autouse
stub and an empty corpus, so every turn is no-answer path A. That is deliberate: what is
under test there is where a thread's title comes from, which does not depend on an answer
having been produced.

**A reopened turn carries the sources it consulted (D-78).** A later section asks through
the real ``POST /api/ask`` with a controlled double installed as the suite installs every
provider double, then reopens the thread and compares. The reopened panel is the live
panel, byte for byte: every item consulted, cited or not, in rank order, with its passages.
A turn that renders unanswered carries none, and the two no-answer paths still reopen as one
body even though only path B's row holds identifiers.

**The list leaves out a thread nobody has asked anything in (D-80).** The last section tests
that, and the list tests above give each thread a turn (``log_a_turn``) so that what they
assert is order and ownership. Creating a thread is throttled; ``test_throttles.py`` covers that.
"""

import json
import uuid
from datetime import date, timedelta
from math import sqrt

import pytest
from django.conf import settings
from django.utils import timezone

import apps.ai
from apps.ai.base import EmbeddingResult, Statement, StatementList
from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.api.answers import RECORD_ONLY_FIELDS
from apps.api.views import NEW_CONVERSATION_TITLE
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    EMPLOYEE_ROLE_NAME,
    MAXIMUM_QUESTION_LENGTH,
    MINIMUM_QUESTION_LENGTH,
    NO_ANSWER_MESSAGE,
    NO_RELEVANT_PASSAGE,
    NO_STATEMENT_VERIFIED,
    RELEVANCE_THRESHOLD,
    SOURCE_TYPES,
)
from apps.core.models import NAME_MAX_LENGTH
from apps.documents.models import ContentChunk, Document
from apps.meetings.models import Meeting
from apps.retrieval.models import AnswerCitation, Conversation, QueryLog
from apps.retrieval.tests.scopes import unreadable_scope

pytestmark = pytest.mark.django_db

CONVERSATIONS_URL = "/api/conversations"
ASK_URL = "/api/ask"

QUESTION = "How do I request annual leave?"
SECOND_QUESTION = "And who signs it off for me?"
assert MINIMUM_QUESTION_LENGTH <= len(QUESTION) <= MAXIMUM_QUESTION_LENGTH

CONVERSATION_FIELDS = {"conversation_id", "title", "last_updated_at"}
# Every turn carries ``sources`` since D-78, answered or not.
TURN_FIELDS = {"question", "answered", "asked_at", "message", "statements", "sources"}


def detail_url(conversation_id):
    return f"{CONVERSATIONS_URL}/{conversation_id}"


def ask_in(client, conversation_id, question=QUESTION):
    return client.post(
        ASK_URL, {"question": question, "conversation_id": str(conversation_id)}, format="json"
    )


def log_a_turn(conversation, question=QUESTION):
    """A no-answer path-A row against ``conversation``, written directly, as ``record_query``
    writes one. The thread list leaves out a thread with no turn (D-80), so a test about the
    list's order or ownership gives each thread a turn. Writing the row moves nothing:
    ``last_updated_at`` is touched by the pipeline, not by the row."""
    return QueryLog.objects.create(
        user=conversation.user,
        conversation=conversation,
        question=question,
        answer_text=None,
        retrieved_chunk_ids=[],
        answered=False,
        no_answer_reason=NO_RELEVANT_PASSAGE,
        rejected_count=None,
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
    by nothing in the reply. Every thread has a turn, so ownership is the only reason one is
    left out (D-80 leaves out a thread with none).
    """
    other = administrator if session_client.user == employee else employee
    older = Conversation.objects.create(user=session_client.user, title="Older thread")
    newer = Conversation.objects.create(user=session_client.user, title="Newer thread")
    theirs = Conversation.objects.create(user=other, title="Someone else's thread")
    for conversation in (older, newer, theirs):
        log_a_turn(conversation)
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
    # Each already has a turn, so both are listed before the one below (D-80).
    log_a_turn(first, "An earlier question in First")
    log_a_turn(second, "An earlier question in Second")
    # Order is what this test asserts, so the two rows must not tie on last_updated_at.
    # timezone.now() is ~15.6 ms granular on this platform — six consecutive calls can
    # return the identical microsecond — so two rows created back to back share the
    # timestamp, "-last_updated_at, pk" then tie-breaks on a random UUID, and the first
    # assertion below becomes a coin flip. An UPDATE sets the column directly, bypassing
    # auto_now, which a save() would overwrite.
    #
    # BOTH are pushed into the PAST, "First" the further, rather than either into the
    # future. The turn below touches "First" with a real timezone.now(), which could never
    # beat a timestamp set ahead of the clock. And it has to beat "Second": had "Second" kept
    # the timestamp it was created with, the turn could land in the same step of the clock
    # and tie it, and the last assertion would be the coin flip instead.
    an_hour_ago = timezone.now() - timedelta(hours=1)
    Conversation.objects.filter(pk=second.pk).update(last_updated_at=an_hour_ago)
    Conversation.objects.filter(pk=first.pk).update(
        last_updated_at=an_hour_ago - timedelta(minutes=1)
    )
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

    **The cited chunk is stamped for both roles here, and it has to be.** A thread read
    re-scopes every stored citation through ``scoped_chunks`` under the reader's current role,
    so a statement cited to the shared ``content_chunk`` fixture — which is deliberately
    unstamped, ``visible_to_roles == []``, readable by no role at all (conftest.py) — would be
    dropped and the turn would render as the no-answer state. That re-scoping is the subject
    of ``test_fr11_thread_scope.py``; what this file tests is the read of a thread whose
    citations the reader may still see, so the premise is made true rather than assumed.
    """
    chunk.visible_to_roles = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]
    chunk.save(update_fields=["visible_to_roles"])
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
            query=answered, chunk=chunk, chunk_uuid=chunk.id, statement_text=text,
            position=position,
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
    # A minute apart, as stated rather than left to the clock: the read orders turns by
    # answered_at, and two rows written back to back can share one (the clock steps at
    # anything from about 0.3 ms to about 15.6 ms here, D-107's note), which leaves their
    # order to two random UUIDs. Both in the past, in the order asked. answered_at is
    # auto_now_add, which overwrites a value given to create(), so an UPDATE sets it.
    asked_at = timezone.now() - timedelta(hours=1)
    QueryLog.objects.filter(pk=answered.pk).update(answered_at=asked_at)
    QueryLog.objects.filter(pk=unanswered.pk).update(answered_at=asked_at + timedelta(minutes=1))
    answered.refresh_from_db(fields=["answered_at"])
    unanswered.refresh_from_db(fields=["answered_at"])
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
    so the reopened thread reads as it did when it was live. The answered turn carries its
    Sources panel (D-78), its date the string ``GET /api/documents/{id}`` gives for the same
    row; the unanswered one carries none.
    """
    conversation, _, _ = thread

    response = session_client.client.get(detail_url(conversation.pk))

    assert response.status_code == 200
    body = response.json()
    assert set(body) == CONVERSATION_FIELDS | {"turns"}
    first, second = body["turns"]
    assert set(first) == set(second) == TURN_FIELDS
    assert first["question"] == QUESTION
    assert first["answered"] is True
    assert first["message"] is None
    assert [statement["position"] for statement in first["statements"]] == [1, 2]
    assert [statement["text"] for statement in first["statements"]] == STATEMENT_TEXTS
    assert {statement["chunk_id"] for statement in first["statements"]} == {str(content_chunk.id)}
    document_body = session_client.client.get(f"/api/documents/{content_chunk.source_id}").json()
    assert first["sources"] == [
        {
            "source_type": SOURCE_TYPES[0],
            "source_id": str(content_chunk.source_id),
            "title": document_body["title"],
            "date": document_body["uploaded_at"],
            "passages": [{"chunk_id": str(content_chunk.id), "text": content_chunk.chunk_text}],
        }
    ]
    assert second["question"] == SECOND_QUESTION
    assert second["answered"] is False
    assert second["message"] == NO_ANSWER_MESSAGE
    assert second["statements"] == []
    assert second["sources"] == []


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
    # Nor the column of identifiers put in front of the model. An answered turn's consulted
    # chunks are shown as its Sources panel, which is what the live reply showed (D-78); the
    # unanswered turn's are never read, and the column itself is never a field.
    assert "retrieved_chunk_ids" not in raw
    assert employee_client.get(detail_url(conversation.pk)).json()["turns"][1]["sources"] == []


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


# --- D-78: a reopened turn carries the sources it consulted, as the live reply did ---------------
#
# ``ControlledService`` is the double ``test_ask.py`` uses, restated here following this suite's
# habit of a test stating its own premise: the query vector is fixed, so a chunk built at
# ``at_cosine(v)`` scores exactly ``v`` and the rank order is known. It is installed through
# ``apps.ai.get_ai_service``, exactly as the autouse stub is, so the turn takes the real pipeline,
# the real ``record_query`` and the real reply.

DOCUMENT_SOURCE_TYPE, MEETING_SOURCE_TYPE = SOURCE_TYPES
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]

POLICY_TITLE = "Leave policy"
POLICY_PASSAGE = "Staff accrue twenty days of annual leave a year."
POLICY_SECOND_PASSAGE = "Leave requests go to your line manager for approval."
PLANNING_TITLE = "Leave planning"
PLANNING_PASSAGE = "The group agreed the leave embargo ends in March."
SCHEDULE_TITLE = "Leave accrual schedule"
SCHEDULE_PASSAGE = "Accrual is calculated monthly and credited on the first of the month."


def _wide(*components) -> list[float]:
    return list(components) + [0.0] * (settings.EMBEDDING_DIMENSION - len(components))


QUERY = _wide(1.0)
# Orthogonal to every chunk ``at_cosine`` builds, so the same corpus takes no-answer path A.
ELSEWHERE = _wide(0.0, 0.0, 1.0)


def at_cosine(value: float) -> list[float]:
    """A unit vector whose cosine with QUERY is exactly ``value``."""
    return _wide(value, sqrt(1.0 - value * value))


class ControlledService:
    """The query vector is ``vector``; the reply cites the first passage it was given, or, with
    ``fabricate``, an identifier that was never supplied, which verification removes (path B)."""

    def __init__(self, *, vector=None, fabricate=False):
        self.vector = QUERY if vector is None else vector
        self.fabricate = fabricate
        self.generate_calls = []

    def embed(self, texts, *, input_type=None):
        return EmbeddingResult(
            vectors=[list(self.vector)], model=STUB_EMBEDDING_MODEL,
            dimension=settings.EMBEDDING_DIMENSION,
        )

    def generate_statements(self, question, passages):
        self.generate_calls.append((question, list(passages)))
        cited = str(uuid.uuid4()) if self.fabricate else passages[0].chunk_id
        return StatementList(statements=[Statement(text=f"Grounded in: {question}", chunk_id=cited)])

    def health(self):  # pragma: no cover - the answer path does not check provider health
        raise AssertionError("not called")


def install(monkeypatch, double):
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: double)
    return double


def consulted_chunk(*, source_type, source_id, text, cosine, index=0):
    return ContentChunk.objects.create(
        source_type=source_type,
        source_id=source_id,
        chunk_index=index,
        chunk_text=text,
        embedding=at_cosine(cosine),
        embedding_model=STUB_EMBEDDING_MODEL,
        embedding_dimension=settings.EMBEDDING_DIMENSION,
        visible_to_roles=BOTH_ROLES,
    )


@pytest.fixture
def consulted_corpus(employee):
    """Three items, four passages, all above the threshold and readable by both roles.

    Rank order is policy (0.95), planning (0.85), policy again (0.70), schedule (0.60), so the
    live panel groups the policy's two passages under one entry, puts a meeting second, and the
    double cites the policy's first passage alone: three of the four are consulted and uncited.
    """
    assert RELEVANCE_THRESHOLD < 0.60
    policy = Document.objects.create(
        title=POLICY_TITLE, file_type="pdf", uploaded_by=employee, visible_to_roles=BOTH_ROLES
    )
    planning = Meeting.objects.create(
        title=PLANNING_TITLE, meeting_date=date(2026, 1, 5), transcript_text=PLANNING_PASSAGE,
        visible_to_roles=BOTH_ROLES,
    )
    schedule = Document.objects.create(
        title=SCHEDULE_TITLE, file_type="pdf", uploaded_by=employee, visible_to_roles=BOTH_ROLES
    )
    chunks = {
        "policy": consulted_chunk(source_type=DOCUMENT_SOURCE_TYPE, source_id=policy.id,
                                  text=POLICY_PASSAGE, cosine=0.95),
        "planning": consulted_chunk(source_type=MEETING_SOURCE_TYPE, source_id=planning.id,
                                    text=PLANNING_PASSAGE, cosine=0.85),
        "policy_second": consulted_chunk(source_type=DOCUMENT_SOURCE_TYPE, source_id=policy.id,
                                         text=POLICY_SECOND_PASSAGE, cosine=0.70, index=1),
        "schedule": consulted_chunk(source_type=DOCUMENT_SOURCE_TYPE, source_id=schedule.id,
                                    text=SCHEDULE_PASSAGE, cosine=0.60),
    }
    return {"policy": policy, "planning": planning, "schedule": schedule, "chunks": chunks}


def asked_in_a_thread(client, user):
    """One answered turn through ``POST /api/ask``, in a new thread, and its live reply."""
    conversation = Conversation.objects.create(user=user, title="Leave")
    live = ask_in(client, conversation.pk)
    assert live.status_code == 200
    assert live.json()["answered"] is True
    return conversation, live.json()


def test_a_reopened_turns_sources_are_the_live_replys_sources(
    session_client, monkeypatch, consulted_corpus
):
    """D-78, from an Employee session and an Administrator session: ask, reopen, compare.

    The reopened ``sources`` equal the live reply's byte for byte, key order included: the same
    items in the same rank order, the same grouping of passages under their item, the same
    date strings for a document and for a meeting, and the same passage identifiers. That is
    what makes a reopened citation expand and link exactly as the live one did. The live
    panel is asserted first to be the non-trivial one the corpus was built for, so the
    equality is not met by two empty lists.
    """
    install(monkeypatch, ControlledService())
    conversation, live = asked_in_a_thread(session_client.client, session_client.user)
    assert [source["title"] for source in live["sources"]] == [
        POLICY_TITLE, PLANNING_TITLE, SCHEDULE_TITLE
    ]
    assert [len(source["passages"]) for source in live["sources"]] == [2, 1, 1]

    response = session_client.client.get(detail_url(conversation.pk))

    assert response.status_code == 200
    [turn] = response.json()["turns"]
    assert json.dumps(turn["sources"]) == json.dumps(live["sources"])
    assert turn["statements"] == live["statements"]
    # And every citation expands to a passage the panel lists.
    listed = {passage["chunk_id"] for source in turn["sources"] for passage in source["passages"]}
    assert {statement["chunk_id"] for statement in turn["statements"]} <= listed


def test_an_uncited_consulted_passage_is_in_the_reopened_panel(
    session_client, monkeypatch, consulted_corpus
):
    """Consulted, not cited (D-78, D-44): the panel lists every item the answer was drawn from,
    including the ones no surviving statement cites. From both roles.

    The schedule's passage was supplied to generation and cited by nothing. It is in the
    reopened panel with its text, under its own item, last in rank order.
    """
    install(monkeypatch, ControlledService())
    conversation, _ = asked_in_a_thread(session_client.client, session_client.user)
    schedule = consulted_corpus["schedule"]
    schedule_chunk = consulted_corpus["chunks"]["schedule"]

    [turn] = session_client.client.get(detail_url(conversation.pk)).json()["turns"]

    cited = {statement["chunk_id"] for statement in turn["statements"]}
    assert str(schedule_chunk.id) not in cited
    assert turn["sources"][-1]["source_id"] == str(schedule.id)
    assert turn["sources"][-1]["title"] == SCHEDULE_TITLE
    assert turn["sources"][-1]["passages"] == [
        {"chunk_id": str(schedule_chunk.id), "text": SCHEDULE_PASSAGE}
    ]


def test_a_path_b_turn_reopens_identical_to_a_path_a_turn(
    session_client, monkeypatch, consulted_corpus
):
    """D-78 item 1, from both roles: two turns asked through the real route, one down each
    no-answer path, reopen as the same body.

    The premise is asserted on the rows: the path-B row holds the identifiers of the four
    passages supplied to generation and the path-A row holds none, so a read that consulted
    ``retrieved_chunk_ids`` on an unanswered turn would have something to tell them apart with.
    The reopened turns are compared field by field except for the question and the timestamp
    they cannot share, and none of the path-B identifiers appears anywhere in the body.

    The turns are told apart by their question, not their position: two asks in one tick of
    this platform's clock can share an ``answered_at``.
    """
    reader = session_client.user
    conversation = Conversation.objects.create(user=reader, title="Leave")
    install(monkeypatch, ControlledService(fabricate=True))
    assert ask_in(session_client.client, conversation.pk, QUESTION).json()["answered"] is False
    install(monkeypatch, ControlledService(vector=ELSEWHERE))
    assert ask_in(session_client.client, conversation.pk, SECOND_QUESTION).json()["answered"] is False

    path_b = QueryLog.objects.get(conversation=conversation, question=QUESTION)
    path_a = QueryLog.objects.get(conversation=conversation, question=SECOND_QUESTION)
    assert path_b.no_answer_reason == NO_STATEMENT_VERIFIED
    assert path_a.no_answer_reason == NO_RELEVANT_PASSAGE
    supplied = [chunk.id for chunk in consulted_corpus["chunks"].values()]
    assert path_b.retrieved_chunk_ids == supplied  # the premise: identifiers present on B
    assert path_a.retrieved_chunk_ids == []

    response = session_client.client.get(detail_url(conversation.pk))

    assert response.status_code == 200
    turns = {turn["question"]: turn for turn in response.json()["turns"]}
    variable = {"asked_at", "question"}
    path_b_body = {key: value for key, value in turns[QUESTION].items() if key not in variable}
    path_a_body = {key: value for key, value in turns[SECOND_QUESTION].items() if key not in variable}
    assert path_b_body == path_a_body
    assert set(turns[QUESTION]) == TURN_FIELDS
    assert path_b_body["sources"] == []
    raw = response.content.decode()
    for identifier in supplied:
        assert str(identifier) not in raw


# --- D-80: the list leaves out a thread nobody has asked anything in ------------------------------
#
# ``GET /api/conversations`` lists a thread once it has a ``QueryLog`` row, through an ``Exists``
# subquery. Never on the "New conversation" title, and never on what a turn renders. Each test below
# is the case one of the wrong filters would get wrong: a titled empty thread (a filter on the
# placeholder), a no-answer turn (a filter on answered rows), a re-scoped turn (a filter on readable
# citations), and a placeholder-titled thread with a turn (a filter on the title the other way).


def listed_ids(client):
    return [entry["conversation_id"] for entry in client.get(CONVERSATIONS_URL).json()]


def test_an_empty_thread_is_absent_from_the_list_but_its_address_still_reads_it(session_client):
    """D-80, from both roles. One empty thread carries the placeholder and one the title its owner
    typed, so a filter on the title would still list the second. Nothing is deleted (rule 3)."""
    client = session_client.client
    placeholder = client.post(CONVERSATIONS_URL, {}, format="json").json()
    titled = client.post(CONVERSATIONS_URL, {"title": "Budget questions"}, format="json").json()
    assert placeholder["title"] == NEW_CONVERSATION_TITLE  # the premise

    listing = client.get(CONVERSATIONS_URL)

    assert listing.status_code == 200
    assert listing.json() == []
    for created in (placeholder, titled):
        response = client.get(detail_url(created["conversation_id"]))
        assert response.status_code == 200
        assert response.json()["title"] == created["title"]
        assert response.json()["turns"] == []
    assert Conversation.objects.filter(user=session_client.user).count() == 2


def test_a_thread_is_listed_once_its_first_turn_lands_answered_or_not(
    session_client, monkeypatch, consulted_corpus
):
    """D-80, from both roles: a thread appears with its first turn, whichever of the pipeline's
    three exits that turn took. Compared as a set, because two turns in one tick of this
    platform's clock can share a ``last_updated_at``."""
    client = session_client.client
    user = session_client.user
    answered = Conversation.objects.create(user=user, title="Answered")
    path_a = Conversation.objects.create(user=user, title="Nothing relevant")
    path_b = Conversation.objects.create(user=user, title="Nothing verified")
    assert listed_ids(client) == []

    install(monkeypatch, ControlledService())
    assert ask_in(client, answered.pk).json()["answered"] is True
    assert listed_ids(client) == [str(answered.pk)]

    install(monkeypatch, ControlledService(vector=ELSEWHERE))
    assert ask_in(client, path_a.pk).json()["answered"] is False
    install(monkeypatch, ControlledService(fabricate=True))
    assert ask_in(client, path_b.pk).json()["answered"] is False

    assert set(listed_ids(client)) == {str(answered.pk), str(path_a.pk), str(path_b.pk)}
    # The premise: the two unanswered turns took the two different no-answer paths.
    assert QueryLog.objects.get(conversation=path_a).no_answer_reason == NO_RELEVANT_PASSAGE
    assert QueryLog.objects.get(conversation=path_b).no_answer_reason == NO_STATEMENT_VERIFIED


def test_a_thread_whose_every_turn_is_re_scoped_stays_listed(
    session_client, monkeypatch, consulted_corpus
):
    """D-80 rule 1, from both roles. The thread's one turn was answered from sources the reader
    can no longer read, so it reopens exactly as a never-answered turn. The thread stays listed,
    under its title, so the list does not show that something was withheld.

    Every consulted source is narrowed through the model, so the cascade re-stamps its chunks
    (invariant 2), to a scope the reader's role does not read (D-66).
    """
    client = session_client.client
    install(monkeypatch, ControlledService())
    conversation, _ = asked_in_a_thread(client, session_client.user)
    assert listed_ids(client) == [str(conversation.pk)]

    for name in ("policy", "planning", "schedule"):
        source = consulted_corpus[name]
        source.visible_to_roles = unreadable_scope(session_client.role_name)
        source.save()

    [turn] = client.get(detail_url(conversation.pk)).json()["turns"]
    # The premise: re-scoped to the never-answered state.
    assert turn["answered"] is False
    assert turn["statements"] == [] and turn["sources"] == []
    assert turn["message"] == NO_ANSWER_MESSAGE
    [listed] = client.get(CONVERSATIONS_URL).json()
    assert listed["conversation_id"] == str(conversation.pk)
    assert listed["title"] == "Leave"


def test_a_thread_still_titled_new_conversation_with_a_turn_is_listed(session_client):
    """D-80 rule 1, from both roles: the filter is never the placeholder title. A question of
    nothing but whitespace is long enough to ask and leaves nothing to name the thread with
    (D-43), so the thread keeps "New conversation" with a turn in it, and it is listed."""
    client = session_client.client
    created = client.post(CONVERSATIONS_URL, {}, format="json").json()
    blank_question = " " * MINIMUM_QUESTION_LENGTH

    assert ask_in(client, created["conversation_id"], blank_question).status_code == 200

    [listed] = client.get(CONVERSATIONS_URL).json()
    assert listed["conversation_id"] == created["conversation_id"]
    assert listed["title"] == NEW_CONVERSATION_TITLE
