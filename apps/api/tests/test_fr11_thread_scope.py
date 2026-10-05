"""A reopened thread is re-scoped on read: ``GET /api/conversations/{id}`` under FR-11.

**The measured leak.** An Administrator asks a question answered from Administrator-only
material, is demoted to Employee, reopens the thread, and is served the statement prose and
the restricted ``chunk_id`` again. The route was filtered by OWNER and never re-scoped: the
queryset answers "is this thread yours", which says nothing about whether what its answers
were generated from is still readable by the role you hold now.

**The class of bug, of which this is one instance.** A derived record does not carry
visibility and nothing re-derives it. A ``ContentChunk`` is stamped from its source at
ingestion; a ``QueryLog`` answer is generated under the role its asker held at the time; a
thread read replays those. When the source's visibility or the reader's role changes
afterwards, something has to revisit the derived record — eagerly for the chunk stamp, which
retrieval trusts as a stored predicate (``apps/core/visibility.py``), and on read for a
stored answer, which is this file.

**What is actually withheld is the PROSE, and the obvious framing understates it.** It is
tempting to say a turn returns no passage text, so at worst an identifier leaks and an
identifier is not content. That is wrong, and it is the reason this file asserts the SENTENCE
is absent before it asserts the id is. A statement generated from an Administrator-only
passage carries that passage's substance in natural language: "Directors accrue annual leave
at twice the ordinary rate" IS the restricted fact, written out, and it is no less so for
having been produced by a model. The identifier is the lesser half of the leak.

**One predicate, not two.** The stored ``chunk_id``s are filtered through
``apps.retrieval.scoping.scoped_chunks`` — the same function the answer path and the keyword
search run — because invariant 3's reasoning applies here exactly: a second scoping mechanism
means two code paths through the single filter that matters most, and they can disagree.

**A turn that loses every statement renders as the existing no-answer state**, the one item 7
built: ``answered`` false, the fixed message, an empty list. Not blank, and not "content
withheld", not a removed-count and not a gap in the citation numbers — each of those is
itself a disclosure that material exists which this role may not read, which is invariant 1.
So the assertions here are not only "the prose is gone" but "nothing says anything is gone",
including a key-set equality so that a helpful new field cannot become the notice.

**The question text stays**, which is not an oversight: it is the user's own words, stored
verbatim, the same reasoning D-42 gives for passing prior questions into a later turn. And
the thread title stays, because it is either what the user typed or their own first question
truncated (D-43).

**Both directions.** A demotion must remove; a promotion must not add. The stored citations
are what they are, so a reader whose role widens sees the turns they were given and no more —
FR-19's record of what was answered is not retrospectively improved.
"""

import uuid
from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model

from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.api.answers import RECORD_ONLY_FIELDS
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    EMPLOYEE_ROLE_NAME,
    NO_ANSWER_MESSAGE,
    NO_ANSWER_REASONS,
    SOURCE_TYPES,
)
from apps.documents.models import ContentChunk, Document
from apps.retrieval.models import AnswerCitation, Conversation, QueryLog

pytestmark = pytest.mark.django_db

CONVERSATIONS_URL = "/api/conversations"
DOCUMENT_SOURCE_TYPE, MEETING_SOURCE_TYPE = SOURCE_TYPES
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]
ADMINISTRATOR_ONLY = [ADMINISTRATOR_ROLE_NAME]

TURN_FIELDS = {"question", "answered", "asked_at", "message", "statements"}
CONVERSATION_FIELDS = {"conversation_id", "title", "last_updated_at"}

QUESTION = "How is annual leave accrued for senior staff?"
SECOND_QUESTION = "And who signs those accruals off each year?"

# The statement drawn from the restricted passage. This sentence is the leak: it is the
# passage's substance in prose, and asserting its absence is the assertion that matters.
RESTRICTED_STATEMENT = "Directors accrue annual leave at twice the ordinary rate."
SHARED_STATEMENT = "Staff may take annual leave once probation has ended."
RESTRICTED_DOCUMENT_TITLE = "Board remuneration review"
SHARED_DOCUMENT_TITLE = "Employee handbook"

# Words an implementation might reach for if it decided to tell the reader something had been
# taken out. Each of them is an existence disclosure (invariant 1) and none may appear.
REMOVAL_WORDS = (
    "withheld",
    "removed",
    "restricted",
    "redacted",
    "hidden",
    "permission",
    "not permitted",
    "unavailable",
)


def detail_url(conversation_id):
    return f"{CONVERSATIONS_URL}/{conversation_id}"


def make_chunk(*, source_id, roles, text):
    return ContentChunk.objects.create(
        source_type=DOCUMENT_SOURCE_TYPE,
        source_id=source_id,
        chunk_index=0,
        chunk_text=text,
        embedding=[0.1] * settings.EMBEDDING_DIMENSION,
        embedding_model=STUB_EMBEDDING_MODEL,
        embedding_dimension=settings.EMBEDDING_DIMENSION,
        visible_to_roles=roles,
    )


def make_document(uploader, *, title, roles, text):
    document = Document.objects.create(
        title=title,
        file_type="pdf",
        uploaded_by=uploader,
        visible_to_roles=roles,
    )
    return document, make_chunk(source_id=document.id, roles=roles, text=text)


def log_turn(user, conversation, *, question, citations, answered=True):
    """One logged turn, with its AnswerCitations, exactly as ``record_query`` writes them.

    Built directly rather than through ``POST /api/ask`` because what is under test is the
    READ of a row that already exists: the turn is legitimate — the asker's role admitted
    every passage at the time — and the change happens afterwards.
    """
    turn = QueryLog.objects.create(
        user=user,
        conversation=conversation,
        question=question,
        answer_text=" ".join(text for text, _ in citations) if citations else None,
        retrieved_chunk_ids=[chunk.id for _, chunk in citations],
        answered=answered,
        rejected_count=0 if answered else None,
    )
    for position, (text, chunk) in enumerate(citations, start=1):
        AnswerCitation.objects.create(
            query=turn, chunk=chunk, chunk_uuid=chunk.id, statement_text=text, position=position
        )
    return turn


@pytest.fixture
def answered_thread(administrator, employee):
    """An Administrator's thread with two answered turns, over two permission levels.

    Turn one cites the restricted passage and then the shared one, in that order, so that
    dropping the first is also the case where the surviving statement's stored number is 2 and
    a gap would show. Turn two cites the restricted passage alone, so it is the turn that
    loses everything.
    """
    _, restricted_chunk = make_document(
        administrator,
        title=RESTRICTED_DOCUMENT_TITLE,
        roles=ADMINISTRATOR_ONLY,
        text="Directors accrue leave at twice the ordinary rate.",
    )
    shared_document, shared_chunk = make_document(
        employee,
        title=SHARED_DOCUMENT_TITLE,
        roles=BOTH_ROLES,
        text="Staff may take leave once probation has ended.",
    )
    conversation = Conversation.objects.create(user=administrator, title=QUESTION)
    mixed = log_turn(
        administrator,
        conversation,
        question=QUESTION,
        citations=[(RESTRICTED_STATEMENT, restricted_chunk), (SHARED_STATEMENT, shared_chunk)],
    )
    restricted_only = log_turn(
        administrator,
        conversation,
        question=SECOND_QUESTION,
        citations=[(RESTRICTED_STATEMENT, restricted_chunk)],
    )
    # timezone.now() is coarse enough here that two rows made in one tick can share an
    # answered_at, and the read orders by it. Forced apart so the turns are told apart by
    # position in the list rather than by luck.
    QueryLog.objects.filter(pk=restricted_only.pk).update(
        answered_at=mixed.answered_at + timedelta(seconds=1)
    )
    return {
        "conversation": conversation,
        "restricted_chunk": restricted_chunk,
        "shared_chunk": shared_chunk,
        "shared_document": shared_document,
        "mixed": mixed,
        "restricted_only": restricted_only,
    }


def demote(user, employee_role):
    """A role change written straight to the row, touching no session and no instance."""
    get_user_model().objects.filter(pk=user.pk).update(role=employee_role)


# --- The negative control, first: nothing is re-scoped away from the role that holds it ----


def test_the_thread_reads_in_full_for_the_role_that_asked_it(
    administrator_client, answered_thread
):
    """**The presence every absence below is paired with.**

    Without this, every assertion in this file would pass against a route that returned no
    statements to anybody, which is the weakest possible way to satisfy invariant 1. The
    Administrator's thread is whole: both statements on turn one, numbered 1 and 2, the
    restricted prose and the restricted identifier both present, and turn two answered.
    """
    thread = answered_thread

    response = administrator_client.get(detail_url(thread["conversation"].pk))

    assert response.status_code == 200
    body = response.json()
    first, second = body["turns"]
    assert first["answered"] is True and first["message"] is None
    assert [statement["text"] for statement in first["statements"]] == [
        RESTRICTED_STATEMENT,
        SHARED_STATEMENT,
    ]
    assert [statement["position"] for statement in first["statements"]] == [1, 2]
    assert first["statements"][0]["chunk_id"] == str(thread["restricted_chunk"].id)
    assert second["answered"] is True
    assert [statement["text"] for statement in second["statements"]] == [RESTRICTED_STATEMENT]


# --- The demotion: the sequence that was measured -----------------------------------------


def test_a_demoted_reader_loses_the_statement_drawn_from_material_they_may_no_longer_see(
    administrator_client, administrator, employee_role, answered_thread
):
    """Ask as an Administrator, demote, reopen: the restricted statement is gone.

    Same thread, same session cookie, no re-login — the role is changed with an UPDATE that
    does not touch the in-memory user, so an implementation resolving the role once per
    session, or caching it from the turn that was logged, would still serve the statement.

    The prose is asserted absent first, and against the raw body, because a field-by-field
    check passes a response that carried the sentence in a key the test did not think to look
    at. The surviving statement is renumbered to 1: its stored position is 2, and rendering
    2 without a 1 would announce that something had been taken out.
    """
    thread = answered_thread
    demote(administrator, employee_role)

    response = administrator_client.get(detail_url(thread["conversation"].pk))

    assert response.status_code == 200
    raw = response.content.decode()
    assert RESTRICTED_STATEMENT not in raw
    assert str(thread["restricted_chunk"].id) not in raw
    first, _ = response.json()["turns"]
    assert first["answered"] is True  # one statement survived, so this turn still has an answer
    assert [statement["text"] for statement in first["statements"]] == [SHARED_STATEMENT]
    assert [statement["position"] for statement in first["statements"]] == [1]
    assert first["statements"][0]["chunk_id"] == str(thread["shared_chunk"].id)
    # The record itself is untouched: FR-19's evidence of what was answered is not rewritten
    # because somebody's role changed.
    assert AnswerCitation.objects.filter(query=thread["mixed"]).count() == 2
    assert QueryLog.objects.get(pk=thread["mixed"].pk).answer_text.startswith(
        RESTRICTED_STATEMENT
    )


def test_a_turn_that_loses_every_statement_renders_as_the_no_answer_state(
    administrator_client, administrator, employee_role, answered_thread
):
    """Turn two cited the restricted passage alone, so after the demotion there is nothing of
    it left to show: the turn renders exactly as a turn that was never answered.

    ``answered`` false, the one fixed NO_ANSWER_MESSAGE, an empty statement list, the same
    five keys. That is the state item 7 already built and the front end already renders, which
    is why it is reused rather than invented: a reader cannot tell this turn from one whose
    question the corpus could not answer, and that indistinguishability is the requirement.
    """
    thread = answered_thread
    demote(administrator, employee_role)

    body = administrator_client.get(detail_url(thread["conversation"].pk)).json()

    _, second = body["turns"]
    assert set(second) == TURN_FIELDS
    assert second["answered"] is False
    assert second["message"] == NO_ANSWER_MESSAGE
    assert second["statements"] == []
    # The question is the user's own words and stays (D-42's reasoning), as does the title.
    assert second["question"] == SECOND_QUESTION
    assert body["title"] == QUESTION


def test_nothing_in_a_re_scoped_thread_says_that_anything_was_removed(
    administrator_client, administrator, employee_role, answered_thread
):
    """The disclosure this is most likely to be "improved" into.

    A "content withheld" panel, a greyed-out statement, a count of what was dropped or a
    ``rejected_count``-shaped number are all the same disclosure: that material exists which
    this role may not read (invariant 1, and invariant 6 for why there is no partial state).
    Asserted three ways — no removal vocabulary anywhere in the bytes, no record-only field,
    and an exact key set on every object, so a new field cannot become the notice.
    """
    thread = answered_thread
    demote(administrator, employee_role)

    response = administrator_client.get(detail_url(thread["conversation"].pk))

    raw = response.content.decode().lower()
    for word in REMOVAL_WORDS:
        assert word not in raw, word
    for field in RECORD_ONLY_FIELDS + NO_ANSWER_REASONS:
        assert field.lower() not in raw, field
    body = response.json()
    assert set(body) == CONVERSATION_FIELDS | {"turns"}
    for turn in body["turns"]:
        assert set(turn) == TURN_FIELDS
        for statement in turn["statements"]:
            assert set(statement) == {"position", "text", "chunk_id"}
    # And no number anywhere counts what was dropped: turn one shows one statement and turn
    # two shows none, which is what a thread with those contents would show anyway.
    assert [len(turn["statements"]) for turn in body["turns"]] == [1, 0]


def test_the_list_route_shows_the_thread_unchanged_after_the_demotion(
    administrator_client, administrator, employee_role, answered_thread
):
    """``GET /api/conversations`` needs no re-scoping and gets none.

    A thread object carries a title and a timestamp. The title is the user's own words — what
    they typed, or their first question truncated (D-43) — so there is nothing in the list
    derived from a passage. Asserted so that the list is not quietly assumed to be the same
    kind of surface as the read.
    """
    demote(administrator, employee_role)

    body = administrator_client.get(CONVERSATIONS_URL).json()

    assert [row["title"] for row in body] == [QUESTION]
    assert set(body[0]) == CONVERSATION_FIELDS


# --- The other direction: a promotion adds nothing -----------------------------------------


def test_a_promoted_reader_gains_no_statements_that_were_never_generated(
    employee_client, employee, administrator, administrator_role
):
    """Promotion widens what can be RETRIEVED, not what was ANSWERED.

    An Employee's thread was answered from the shared document; the restricted document
    existed all along and was never cited, because the turn was generated under a scope that
    excluded it. Promoting the reader must not invent the statement they would have got had
    they asked as an Administrator: the stored citations are the record of what was actually
    answered, and re-scoping only ever removes from that record.
    """
    _, restricted_chunk = make_document(
        administrator,
        title=RESTRICTED_DOCUMENT_TITLE,
        roles=ADMINISTRATOR_ONLY,
        text="Directors accrue leave at twice the ordinary rate.",
    )
    _, shared_chunk = make_document(
        employee,
        title=SHARED_DOCUMENT_TITLE,
        roles=BOTH_ROLES,
        text="Staff may take leave once probation has ended.",
    )
    conversation = Conversation.objects.create(user=employee, title=QUESTION)
    log_turn(
        employee,
        conversation,
        question=QUESTION,
        citations=[(SHARED_STATEMENT, shared_chunk)],
    )

    before = employee_client.get(detail_url(conversation.pk))
    get_user_model().objects.filter(pk=employee.pk).update(role=administrator_role)
    after = employee_client.get(detail_url(conversation.pk))

    assert before.status_code == after.status_code == 200
    assert before.content == after.content  # byte for byte: nothing was added
    [turn] = after.json()["turns"]
    assert [statement["text"] for statement in turn["statements"]] == [SHARED_STATEMENT]
    assert RESTRICTED_STATEMENT not in after.content.decode()
    assert str(restricted_chunk.id) not in after.content.decode()


# --- The same read, re-scoped by the SOURCE changing instead of the ROLE -------------------


def test_narrowing_the_source_re_scopes_a_thread_that_cited_it(
    employee_client, employee, answered_thread
):
    """The two halves of the same class of bug meeting on one route.

    Nobody's role changes here. The DOCUMENT is narrowed after the answer was given, which
    re-stamps its chunks in the same transaction (invariant 2, ``apps/core/visibility.py``),
    and the thread read then filters the stored citation through the same chunk predicate the
    answer path uses — so one visibility edit reaches a stored answer without either mechanism
    knowing about the other. That is the whole argument for the stamp being on the chunk and
    for the read using ``scoped_chunks`` rather than a rule of its own.
    """
    thread = answered_thread
    conversation = Conversation.objects.create(user=employee, title=QUESTION)
    log_turn(
        employee,
        conversation,
        question=QUESTION,
        citations=[(SHARED_STATEMENT, thread["shared_chunk"])],
    )
    assert employee_client.get(detail_url(conversation.pk)).json()["turns"][0]["answered"] is True

    thread["shared_document"].visible_to_roles = ADMINISTRATOR_ONLY
    thread["shared_document"].save()

    response = employee_client.get(detail_url(conversation.pk))

    assert response.status_code == 200
    [turn] = response.json()["turns"]
    assert turn["answered"] is False
    assert turn["message"] == NO_ANSWER_MESSAGE
    assert turn["statements"] == []
    raw = response.content.decode()
    assert SHARED_STATEMENT not in raw
    assert str(thread["shared_chunk"].id) not in raw


# --- Both roles reach the route and each is re-scoped to its own -----------------------------


def test_both_roles_read_a_thread_re_scoped_to_their_own_role(
    session_client, employee, administrator
):
    """The dual-role pairing on ``GET /api/conversations/{id}`` (CLAUDE.md section 8 item 2).

    One thread per role, each with a turn citing the Administrator-only passage. The
    Administrator is served it and the Employee is not, from the same route, the same stored
    rows and the same predicate — FR-11's "two users asking the same question may receive
    different results", holding on a read of an answer rather than on the asking of one.
    """
    _, restricted_chunk = make_document(
        administrator,
        title=RESTRICTED_DOCUMENT_TITLE,
        roles=ADMINISTRATOR_ONLY,
        text="Directors accrue leave at twice the ordinary rate.",
    )
    conversation = Conversation.objects.create(user=session_client.user, title=QUESTION)
    log_turn(
        session_client.user,
        conversation,
        question=QUESTION,
        citations=[(RESTRICTED_STATEMENT, restricted_chunk)],
    )

    response = session_client.client.get(detail_url(conversation.pk))

    assert response.status_code == 200
    [turn] = response.json()["turns"]
    raw = response.content.decode()
    if session_client.role_name == ADMINISTRATOR_ROLE_NAME:
        assert turn["answered"] is True
        assert [statement["text"] for statement in turn["statements"]] == [RESTRICTED_STATEMENT]
    else:
        assert turn["answered"] is False
        assert turn["message"] == NO_ANSWER_MESSAGE
        assert RESTRICTED_STATEMENT not in raw
        assert str(restricted_chunk.id) not in raw


def test_an_unstamped_chunks_statement_is_shown_to_nobody(session_client, employee):
    """A citation to a chunk stamped for no role: the read fails closed for both roles.

    D-29 makes an empty ``visible_to_roles`` a 400 at upload so this should not arise; what is
    asserted is what the route does if it ever does, and it is the same thing
    ``test_fr11_scoping.py`` section 7 asserts for the answer path — absence, through the same
    predicate, with no role for which a mirror could hold.
    """
    document, chunk = make_document(
        employee, title=SHARED_DOCUMENT_TITLE, roles=BOTH_ROLES, text="No role may read this."
    )
    ContentChunk.objects.filter(pk=chunk.pk).update(visible_to_roles=[])
    conversation = Conversation.objects.create(user=session_client.user, title=QUESTION)
    log_turn(
        session_client.user, conversation, question=QUESTION, citations=[(SHARED_STATEMENT, chunk)]
    )

    response = session_client.client.get(detail_url(conversation.pk))

    [turn] = response.json()["turns"]
    assert turn["answered"] is False
    assert turn["statements"] == []
    assert SHARED_STATEMENT not in response.content.decode()
    # The document ROW is still in scope and still listable: row visibility is a separate
    # fact, as section 7 of the evidence file says, and this test claims nothing about it.
    assert document.visible_to_roles == BOTH_ROLES


def test_a_thread_with_no_turns_still_reads_after_a_demotion(
    administrator_client, administrator, employee_role
):
    """The empty case, because the re-scoping query must not be issued with an empty set of
    identifiers and must not fail on a thread that has nothing to filter."""
    conversation = Conversation.objects.create(user=administrator, title="Nothing asked yet")
    demote(administrator, employee_role)

    response = administrator_client.get(detail_url(conversation.pk))

    assert response.status_code == 200
    assert response.json()["turns"] == []


def test_someone_elses_thread_is_still_404_after_a_demotion(
    administrator_client, administrator, employee, employee_role, answered_thread
):
    """Re-scoping is in addition to the owner filter, not instead of it: a demoted reader does
    not get somebody else's thread as a re-scoped one, they get the same 404 as an id that does
    not exist."""
    theirs = Conversation.objects.create(user=employee, title="Not yours")
    demote(administrator, employee_role)

    refused = administrator_client.get(detail_url(theirs.pk))
    unknown = administrator_client.get(detail_url(uuid.uuid4()))

    assert refused.status_code == unknown.status_code == 404
    assert refused.content == unknown.content
