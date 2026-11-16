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

**The Sources panel is re-scoped by the same read (D-78).** Since Stage 5 item 4b an answered
turn carries the items it consulted, cited or not, with their passages. They come from the
same single ``scoped_chunks`` query as the citations, so a consulted passage the reader may no
longer see drops out of the panel exactly as a statement drops out of the answer: no entry, no
count, no placeholder.
"""

import uuid
from datetime import date, timedelta

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.api.answers import RECORD_ONLY_FIELDS
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    EMPLOYEE_ROLE_NAME,
    NO_ANSWER_MESSAGE,
    NO_ANSWER_REASONS,
    NO_STATEMENT_VERIFIED,
    SOURCE_TYPES,
)
from apps.documents.models import ContentChunk, Document
from apps.meetings.models import Meeting
from apps.retrieval.models import AnswerCitation, Conversation, QueryLog
from apps.retrieval.scoping import scoped_chunks
from apps.retrieval.tests.scopes import unreadable_scope

pytestmark = pytest.mark.django_db

CONVERSATIONS_URL = "/api/conversations"
DOCUMENT_SOURCE_TYPE, MEETING_SOURCE_TYPE = SOURCE_TYPES
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]
ADMINISTRATOR_ONLY = [ADMINISTRATOR_ROLE_NAME]

# Every turn carries ``sources`` since D-78, answered or not, so the two states change together.
TURN_FIELDS = {"question", "answered", "asked_at", "message", "statements", "sources"}
CONVERSATION_FIELDS = {"conversation_id", "title", "last_updated_at"}
# The live reply's Sources panel entry and passage (D-44), exactly.
SOURCE_FIELDS = {"source_type", "source_id", "title", "date", "passages"}
# ``ai_generated`` since D-125: whether the passage is from a meeting's AI-generated summary. It is
# a property of the passage shown, so it says nothing about a passage that is not.
PASSAGE_FIELDS = {"chunk_id", "text", "ai_generated"}

# The table every chunk read hits, as it appears in captured SQL.
CHUNK_TABLE = '"content_chunks"'

QUESTION = "How is annual leave accrued for senior staff?"
SECOND_QUESTION = "And who signs those accruals off each year?"

# The statement drawn from the restricted passage. This sentence is the leak: it is the
# passage's substance in prose, and asserting its absence is the assertion that matters.
RESTRICTED_STATEMENT = "Directors accrue annual leave at twice the ordinary rate."
SHARED_STATEMENT = "Staff may take annual leave once probation has ended."
RESTRICTED_DOCUMENT_TITLE = "Board remuneration review"
SHARED_DOCUMENT_TITLE = "Employee handbook"
RESTRICTED_PASSAGE = "Directors accrue leave at twice the ordinary rate."
SHARED_PASSAGE = "Staff may take leave once probation has ended."
# A source a turn consulted and no statement cited: in the panel, and in no statement.
CONSULTED_DOCUMENT_TITLE = "Leave accrual schedule"
CONSULTED_PASSAGE = "Accrual is calculated monthly and credited on the first of the month."

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


def make_chunk(*, source_id, roles, text, source_type=DOCUMENT_SOURCE_TYPE):
    return ContentChunk.objects.create(
        source_type=source_type,
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


def log_turn(user, conversation, *, question, citations, answered=True, consulted=None):
    """One logged turn, with its AnswerCitations, exactly as ``record_query`` writes them.

    Built directly rather than through ``POST /api/ask`` because what is under test is the
    READ of a row that already exists: the turn is legitimate — the asker's role admitted
    every passage at the time — and the change happens afterwards.

    ``consulted`` is the turn's ``retrieved_chunk_ids`` in rank order: every chunk supplied to
    generation, cited or not. By default the cited chunks alone, as before D-78. Where it is
    given it must include every cited chunk, as verification guarantees on a real row.
    """
    consulted = [chunk for _, chunk in citations] if consulted is None else consulted
    assert {chunk.id for _, chunk in citations} <= {chunk.id for chunk in consulted}
    turn = QueryLog.objects.create(
        user=user,
        conversation=conversation,
        question=question,
        answer_text=" ".join(text for text, _ in citations) if citations else None,
        retrieved_chunk_ids=[chunk.id for chunk in consulted],
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
    restricted_document, restricted_chunk = make_document(
        administrator,
        title=RESTRICTED_DOCUMENT_TITLE,
        roles=ADMINISTRATOR_ONLY,
        text=RESTRICTED_PASSAGE,
    )
    shared_document, shared_chunk = make_document(
        employee,
        title=SHARED_DOCUMENT_TITLE,
        roles=BOTH_ROLES,
        text=SHARED_PASSAGE,
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
        "restricted_document": restricted_document,
        "shared_chunk": shared_chunk,
        "shared_document": shared_document,
        "mixed": mixed,
        "restricted_only": restricted_only,
    }


def panel(turn):
    """A turn's Sources panel as (title, source id, [(passage chunk id, passage text)])."""
    return [
        (
            source["title"],
            source["source_id"],
            [(passage["chunk_id"], passage["text"]) for passage in source["passages"]],
        )
        for source in turn["sources"]
    ]


def entry(document, *chunks):
    """What ``panel`` holds for ``document`` consulted through ``chunks``, in that order."""
    return (
        document.title,
        str(document.id),
        [(str(chunk.id), chunk.chunk_text) for chunk in chunks],
    )


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
    restricted prose and the restricted identifier both present, and turn two answered. Both
    turns' Sources panels list the restricted document with its passage (D-78), so the
    absences asserted below are of something that was there.
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
    assert panel(first) == [
        entry(thread["restricted_document"], thread["restricted_chunk"]),
        entry(thread["shared_document"], thread["shared_chunk"]),
    ]
    assert second["answered"] is True
    assert [statement["text"] for statement in second["statements"]] == [RESTRICTED_STATEMENT]
    assert panel(second) == [entry(thread["restricted_document"], thread["restricted_chunk"])]


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
    # The passage and its source went with the statement: the panel is re-scoped by the same
    # query (D-78), so the restricted text and title are nowhere either.
    assert RESTRICTED_PASSAGE not in raw
    assert RESTRICTED_DOCUMENT_TITLE not in raw
    assert str(thread["restricted_document"].id) not in raw
    first, _ = response.json()["turns"]
    assert first["answered"] is True  # one statement survived, so this turn still has an answer
    assert [statement["text"] for statement in first["statements"]] == [SHARED_STATEMENT]
    assert [statement["position"] for statement in first["statements"]] == [1]
    assert first["statements"][0]["chunk_id"] == str(thread["shared_chunk"].id)
    assert panel(first) == [entry(thread["shared_document"], thread["shared_chunk"])]
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

    ``answered`` false, the one fixed NO_ANSWER_MESSAGE, an empty statement list, no sources,
    the same six keys. That is the state item 7 already built and the front end already
    renders, which is why it is reused rather than invented: a reader cannot tell this turn
    from one whose question the corpus could not answer, and that indistinguishability is the
    requirement.
    """
    thread = answered_thread
    demote(administrator, employee_role)

    body = administrator_client.get(detail_url(thread["conversation"].pk)).json()

    _, second = body["turns"]
    assert set(second) == TURN_FIELDS
    assert second["answered"] is False
    assert second["message"] == NO_ANSWER_MESSAGE
    assert second["statements"] == []
    assert second["sources"] == []
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
        # The panel is the live reply's shape and nothing more (D-78): no count of what it
        # left out, on the entry or on a passage.
        for source in turn["sources"]:
            assert set(source) == SOURCE_FIELDS
            for passage in source["passages"]:
                assert set(passage) == PASSAGE_FIELDS
    # And no number anywhere counts what was dropped: turn one shows one statement and turn
    # two shows none, which is what a thread with those contents would show anyway.
    assert [len(turn["statements"]) for turn in body["turns"]] == [1, 0]
    assert [len(turn["sources"]) for turn in body["turns"]] == [1, 0]


def test_a_demoted_reader_loses_a_consulted_source_they_may_no_longer_see_without_a_trace(
    administrator_client, administrator, employee, employee_role
):
    """A source the turn consulted and NO statement cited, out of scope after a demotion.

    This is the case the statement re-scoping cannot reach: nothing cited the restricted
    passage, so no statement drops and the turn stays answered. The panel must still lose it
    (D-78 item 4), and lose it silently: the remaining entry is byte for byte what it was before,
    the list is one shorter, and nothing counts, names or stands in for what went.

    The restricted source ranked FIRST, so a placeholder or a gap would sit at the head of the
    list. From an Administrator session only, because only that role can be narrowed; the same
    property from both sessions is the next test, by moving the source instead.
    """
    restricted_document, restricted_chunk = make_document(
        administrator, title=RESTRICTED_DOCUMENT_TITLE, roles=ADMINISTRATOR_ONLY,
        text=RESTRICTED_PASSAGE,
    )
    shared_document, shared_chunk = make_document(
        employee, title=SHARED_DOCUMENT_TITLE, roles=BOTH_ROLES, text=SHARED_PASSAGE
    )
    conversation = Conversation.objects.create(user=administrator, title=QUESTION)
    log_turn(
        administrator, conversation, question=QUESTION,
        citations=[(SHARED_STATEMENT, shared_chunk)],
        consulted=[restricted_chunk, shared_chunk],
    )
    before = administrator_client.get(detail_url(conversation.pk)).json()["turns"][0]
    # The premise: consulted and listed, and cited by nothing.
    assert panel(before) == [
        entry(restricted_document, restricted_chunk),
        entry(shared_document, shared_chunk),
    ]
    assert [statement["chunk_id"] for statement in before["statements"]] == [str(shared_chunk.id)]

    demote(administrator, employee_role)
    response = administrator_client.get(detail_url(conversation.pk))

    [turn] = response.json()["turns"]
    assert turn["answered"] is True
    assert turn["statements"] == before["statements"]
    assert turn["sources"] == [before["sources"][1]]
    raw = response.content.decode()
    for trace in (
        RESTRICTED_DOCUMENT_TITLE, RESTRICTED_PASSAGE, str(restricted_document.id),
        str(restricted_chunk.id),
    ):
        assert trace not in raw, trace
    for word in REMOVAL_WORDS + ("count",):
        assert word not in raw.lower(), word
    assert set(turn) == TURN_FIELDS
    for source in turn["sources"]:
        assert set(source) == SOURCE_FIELDS


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
    assert turn["sources"] == []
    raw = response.content.decode()
    assert SHARED_STATEMENT not in raw
    assert str(thread["shared_chunk"].id) not in raw
    assert SHARED_PASSAGE not in raw


def test_both_roles_lose_a_consulted_source_moved_out_of_their_scope(session_client, employee):
    """D-78 item 4 from an Employee session and an Administrator session: a source the turn
    consulted and nothing cited is narrowed out of the reader's scope, and drops out of the
    panel without a trace, while the turn and its other source are untouched.

    The source is narrowed with ``save()``, so D-47's cascade restamps its chunk in the same
    transaction and the thread read finds it out of scope through the one chunk predicate. For
    an Employee the new scope is Administrator-only; for an Administrator it is the empty
    array, the only scope D-66 leaves that role unable to read (``scopes.unreadable_scope``).
    """
    reader = session_client.user
    cited_document, cited_chunk = make_document(
        employee, title=SHARED_DOCUMENT_TITLE, roles=BOTH_ROLES, text=SHARED_PASSAGE
    )
    consulted_document, consulted_chunk = make_document(
        employee, title=CONSULTED_DOCUMENT_TITLE, roles=BOTH_ROLES, text=CONSULTED_PASSAGE
    )
    conversation = Conversation.objects.create(user=reader, title=QUESTION)
    log_turn(
        reader, conversation, question=QUESTION,
        citations=[(SHARED_STATEMENT, cited_chunk)],
        consulted=[consulted_chunk, cited_chunk],
    )
    [before] = session_client.client.get(detail_url(conversation.pk)).json()["turns"]
    assert panel(before) == [  # the premise: listed, in rank order, before the change
        entry(consulted_document, consulted_chunk),
        entry(cited_document, cited_chunk),
    ]

    consulted_document.visible_to_roles = unreadable_scope(session_client.role_name)
    consulted_document.save()
    response = session_client.client.get(detail_url(conversation.pk))

    assert response.status_code == 200
    [turn] = response.json()["turns"]
    assert turn["answered"] is True
    assert turn["statements"] == before["statements"]
    assert turn["sources"] == [before["sources"][1]]
    raw = response.content.decode()
    for trace in (
        CONSULTED_DOCUMENT_TITLE, CONSULTED_PASSAGE, str(consulted_document.id),
        str(consulted_chunk.id),
    ):
        assert trace not in raw, trace


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
    restricted_document, restricted_chunk = make_document(
        administrator,
        title=RESTRICTED_DOCUMENT_TITLE,
        roles=ADMINISTRATOR_ONLY,
        text=RESTRICTED_PASSAGE,
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
        assert panel(turn) == [entry(restricted_document, restricted_chunk)]
    else:
        assert turn["answered"] is False
        assert turn["message"] == NO_ANSWER_MESSAGE
        assert turn["sources"] == []
        assert RESTRICTED_STATEMENT not in raw
        assert str(restricted_chunk.id) not in raw
        assert RESTRICTED_PASSAGE not in raw
        assert RESTRICTED_DOCUMENT_TITLE not in raw


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


def test_an_unstamped_consulted_passage_is_shown_to_nobody(session_client, employee):
    """The panel's half of the test above: a consulted passage is admitted by the CHUNK
    predicate, not by its source row, from an Employee session and an Administrator session.

    The uncited consulted chunk is stamped for no role while its document is readable by both,
    so the source-row read ``resolve_sources`` makes (D-53) would let the item through. Only the
    thread's one ``scoped_chunks`` query keeps the passage out, and it must: the text of a chunk
    no role may read is not shown because its document happens to be listable. The reverse
    disagreement, a widened chunk under a narrowed source, is
    ``test_source_rows_fail_closed.py``'s.
    """
    reader = session_client.user
    cited_document, cited_chunk = make_document(
        employee, title=SHARED_DOCUMENT_TITLE, roles=BOTH_ROLES, text=SHARED_PASSAGE
    )
    unstamped_document, unstamped_chunk = make_document(
        employee, title=CONSULTED_DOCUMENT_TITLE, roles=BOTH_ROLES, text=CONSULTED_PASSAGE
    )
    ContentChunk.objects.filter(pk=unstamped_chunk.pk).update(visible_to_roles=[])
    conversation = Conversation.objects.create(user=reader, title=QUESTION)
    log_turn(
        reader, conversation, question=QUESTION,
        citations=[(SHARED_STATEMENT, cited_chunk)],
        consulted=[unstamped_chunk, cited_chunk],
    )
    # The premise: the source row is readable by this reader, the chunk is not.
    assert session_client.client.get(f"/api/documents/{unstamped_document.id}").status_code == 200

    response = session_client.client.get(detail_url(conversation.pk))

    [turn] = response.json()["turns"]
    assert turn["answered"] is True
    assert panel(turn) == [entry(cited_document, cited_chunk)]
    raw = response.content.decode()
    assert CONSULTED_PASSAGE not in raw
    assert str(unstamped_chunk.id) not in raw
    assert CONSULTED_DOCUMENT_TITLE not in raw


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


# --- One chunk query for the thread, and what it is asked about (D-78 items 1 and 2) --------

PATH_B_DOCUMENT_TITLE = "Carry-over rules"
PATH_B_PASSAGE = "Up to five days of unused leave carry over into the next year."
MEETING_TITLE = "Leave planning"
MEETING_PASSAGE = "The group agreed the leave embargo ends in March."


def order_after(earlier, later):
    """Force ``later``'s timestamp past ``earlier``'s: ``timezone.now()`` is about 15.6 ms
    granular on this platform, and the read orders turns by it.

    ``later`` is refreshed, so that a chain — ``order_after(a, b)`` then ``order_after(b, c)``
    — puts each turn a second past the one before. Without the refresh, ``c`` was put a second
    past ``b``'s creation time, still in memory after ``b``'s UPDATE, so ``b`` and ``c`` tied
    whenever ``a`` and ``b`` had been created in one step of the clock."""
    QueryLog.objects.filter(pk=later.pk).update(answered_at=earlier.answered_at + timedelta(seconds=1))
    later.refresh_from_db(fields=["answered_at"])


def path_b_turn(user, conversation, *, question, consulted):
    """A turn stored as no-answer path B, as ``record_query`` writes one: unanswered, no
    citations, and the identifiers of what was supplied to generation."""
    return QueryLog.objects.create(
        user=user,
        conversation=conversation,
        question=question,
        answer_text=None,
        retrieved_chunk_ids=[chunk.id for chunk in consulted],
        answered=False,
        no_answer_reason=NO_STATEMENT_VERIFIED,
        rejected_count=1,
    )


def chunk_queries(captured):
    return [query["sql"] for query in captured.captured_queries if CHUNK_TABLE in query["sql"]]


def named_in(sql, identifier) -> bool:
    """Whether captured SQL names ``identifier``, in either form the driver might render."""
    return identifier.hex in sql or str(identifier) in sql


def test_one_chunk_query_serves_every_turns_citations_and_sources(session_client, employee):
    """D-78 item 2, from an Employee session and an Administrator session: one ``scoped_chunks``
    query for the whole thread, whatever its length, and both the citations and every Sources
    panel are derived from it.

    Counted at the database, so a second scope query by any route — a second call of the
    helper, or one queryset filtered twice — fails here. Two scope queries could be answered
    differently if a source's visibility changed between them, and a citation would then expand
    to a passage its own panel did not list. The panels are asserted in full, so the count of
    one is not met by building none.
    """
    reader = session_client.user
    document, document_chunk = make_document(
        employee, title=SHARED_DOCUMENT_TITLE, roles=BOTH_ROLES, text=SHARED_PASSAGE
    )
    consulted_document, consulted_chunk = make_document(
        employee, title=CONSULTED_DOCUMENT_TITLE, roles=BOTH_ROLES, text=CONSULTED_PASSAGE
    )
    meeting = Meeting.objects.create(
        title=MEETING_TITLE, meeting_date=date(2026, 9, 1), transcript_text=MEETING_PASSAGE,
        visible_to_roles=BOTH_ROLES,
    )
    meeting_chunk = make_chunk(
        source_id=meeting.id, roles=BOTH_ROLES, text=MEETING_PASSAGE,
        source_type=MEETING_SOURCE_TYPE,
    )
    conversation = Conversation.objects.create(user=reader, title=QUESTION)
    turns = [
        log_turn(reader, conversation, question=QUESTION,
                 citations=[(SHARED_STATEMENT, document_chunk)],
                 consulted=[document_chunk, meeting_chunk]),
        log_turn(reader, conversation, question=SECOND_QUESTION,
                 citations=[(SHARED_STATEMENT, meeting_chunk)],
                 consulted=[meeting_chunk, consulted_chunk]),
        path_b_turn(reader, conversation, question="And is that the same for contractors?",
                    consulted=[consulted_chunk]),
    ]
    for earlier, later in zip(turns, turns[1:]):
        order_after(earlier, later)

    with CaptureQueriesContext(connection) as captured:
        response = session_client.client.get(detail_url(conversation.pk))

    assert response.status_code == 200
    assert len(chunk_queries(captured)) == 1
    first, second, third = response.json()["turns"]
    assert panel(first) == [entry(document, document_chunk), entry(meeting, meeting_chunk)]
    assert panel(second) == [
        entry(meeting, meeting_chunk), entry(consulted_document, consulted_chunk)
    ]
    assert third["sources"] == []


def test_a_turn_stored_unanswered_never_has_its_retrieved_ids_read(session_client, employee):
    """D-78 item 1, from an Employee session and an Administrator session.

    On a row stored as unanswered, ``answered`` and ``len(retrieved_chunk_ids)`` are what tell
    no-answer path A from path B (D-48 item 6), so the read must not ask the store about those
    identifiers at all, even to render nothing from the answer. Asserted on every SQL statement
    the read sends: the path-B row's identifier is in none of them, though the reader may read
    that chunk, so an implementation that asked would have found it.

    The negative control is in the same body: the answered turn's uncited consulted chunk,
    which only its ``retrieved_chunk_ids`` names, IS in the SQL, so the scan can see an
    identifier when one is asked about.
    """
    reader = session_client.user
    _, cited_chunk = make_document(
        employee, title=SHARED_DOCUMENT_TITLE, roles=BOTH_ROLES, text=SHARED_PASSAGE
    )
    _, consulted_chunk = make_document(
        employee, title=CONSULTED_DOCUMENT_TITLE, roles=BOTH_ROLES, text=CONSULTED_PASSAGE
    )
    _, path_b_chunk = make_document(
        employee, title=PATH_B_DOCUMENT_TITLE, roles=BOTH_ROLES, text=PATH_B_PASSAGE
    )
    conversation = Conversation.objects.create(user=reader, title=QUESTION)
    answered = log_turn(
        reader, conversation, question=QUESTION,
        citations=[(SHARED_STATEMENT, cited_chunk)], consulted=[cited_chunk, consulted_chunk],
    )
    unanswered = path_b_turn(
        reader, conversation, question=SECOND_QUESTION, consulted=[path_b_chunk]
    )
    order_after(answered, unanswered)
    # The premise: readable by this reader, so a read that asked would find it.
    assert scoped_chunks(role_name=session_client.role_name).filter(id=path_b_chunk.id).exists()

    with CaptureQueriesContext(connection) as captured:
        response = session_client.client.get(detail_url(conversation.pk))

    assert response.status_code == 200
    sql = "\n".join(query["sql"] for query in captured.captured_queries)
    assert named_in(sql, consulted_chunk.id)
    assert not named_in(sql, path_b_chunk.id)
    _, second = response.json()["turns"]
    assert second["answered"] is False
    assert second["sources"] == []
    raw = response.content.decode()
    assert PATH_B_PASSAGE not in raw
    assert PATH_B_DOCUMENT_TITLE not in raw
