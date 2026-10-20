"""A citation whose chunk was deleted is REMOVED for every reader of a reopened turn (D-67).

Since Stage 5 item 1a ``AnswerCitation.chunk`` is ``on_delete=SET_NULL``: deleting a chunk —
by a reprocess, by ``manage.py reindex``, or by FR-15's document deletion when it lands —
leaves the citation row in place with ``chunk_id`` NULL and ``chunk_uuid`` naming what was
cited, so FR-12's traceability record survives (``test_fr12_traceability_survives_reprocess.py``).

**The record surviving must not put the statement back on screen.** Before D-67 the cascade
deleted the row, and with it the statement, the identifier and the citation number. That
outcome came about by accident; this file asserts it on purpose. A NULL-chunk row is read
exactly as a row the cascade had deleted:

- its statement is not shown, and its text appears nowhere in the response bytes;
- its identifier — ``chunk_uuid``, which once equalled ``chunk_id`` — appears nowhere either;
- it takes no citation number, so the statements that remain are renumbered from 1;
- a turn left with no row pointing at an existing chunk is state 3, ``provenance_removed``,
  exactly as a turn with no rows was;
- a turn with a NULL-chunk row AND a row whose chunk exists but is out of the reader's scope is
  state 2 — silent, byte-for-byte a never-answered turn — exactly as it was when the NULL row
  would have been gone. The rows whose chunk exists decide it, before any scope is applied,
  and a predicate that read the NULL rows instead would get this case wrong.

The statement text is still in the row. It is the record of what was answered and is never
rendered from it: FR-15 promises deleted material "cannot subsequently be surfaced", and a
statement drawn from a passage carries that passage's substance in prose (D-48).

Chunks are deleted here with ``ContentChunk.objects.filter(source_type=..., source_id=...)
.delete()``, the same call ``reprocess_document`` and ``manage.py reindex`` make, so the NULL is
produced by the model's own ``on_delete`` rather than written by the test.

**Item 4b's Sources panel reads a NULL-chunk row as removed too (D-78).** A reopened answered
turn now carries the passages it consulted, read from the chunk rows themselves, so a deleted
chunk has no passage to return and its item drops out of the panel; a provenance-removed turn
carries no panel at all, even where a passage it consulted but did not cite is still readable.
Both are asserted below.

**What this file does not cover.**

- **The front end.** The response shape is unchanged, so ``frontend/src/utils/turns.js`` sees
  the same states, in the same bodies, that it saw before D-67.
- **The live ``POST /api/ask`` reply.** Its citation rows are written in the same transaction
  as the answer, every one with ``chunk_id`` set, so it cannot hold a NULL-chunk row.
"""

from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model

from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.api.serializers import (
    PROVENANCE_REMOVED_FIELD,
    ConversationTurnSerializer,
    readable_thread_chunks,
)
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    DOCUMENT_INDEXED,
    EMPLOYEE_ROLE_NAME,
    NO_ANSWER_MESSAGE,
    PROVENANCE_REMOVED_MESSAGE,
    SOURCE_TYPES,
)
from apps.documents.models import ContentChunk, Document
from apps.retrieval.models import AnswerCitation, Conversation, QueryLog

pytestmark = pytest.mark.django_db

CONVERSATIONS_URL = "/api/conversations"
DOCUMENT_SOURCE_TYPE = SOURCE_TYPES[0]
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]
ADMINISTRATOR_ONLY = [ADMINISTRATOR_ROLE_NAME]

# The keys every turn carries: five since item 11, and ``sources`` since D-78.
# ``provenance_removed`` is the seventh and appears only in state 3.
TURN_FIELDS = {"question", "answered", "asked_at", "message", "statements", "sources"}

QUESTION = "How much annual leave do I accrue each year?"
SECOND_QUESTION = "And who signs those accruals off each year?"
THIRD_QUESTION = "Does unused leave carry over to the next year?"

# Drawn from a document that is then deleted. This sentence is the deleted material in prose,
# and asserting its absence from the bytes is the assertion that matters.
DELETED_STATEMENT = "Contractors accrue leave at a pro rata rate set in their contract."
DELETED_PASSAGE = "Contractors accrue leave pro rata, at the rate their contract sets."
LIVE_STATEMENT = "Staff accrue twenty days of annual leave a year."
LIVE_PASSAGE = "Staff accrue twenty days of annual leave a year."
RESTRICTED_STATEMENT = "Directors accrue annual leave at twice the ordinary rate."
RESTRICTED_PASSAGE = "Directors accrue leave at twice the ordinary rate."


def detail_url(conversation_id):
    return f"{CONVERSATIONS_URL}/{conversation_id}"


def make_document_with_chunk(uploader, *, title, roles, text):
    document = Document.objects.create(
        title=title,
        file_type="txt",
        uploaded_by=uploader,
        visible_to_roles=roles,
        status=DOCUMENT_INDEXED,
    )
    chunk = ContentChunk.objects.create(
        source_type=DOCUMENT_SOURCE_TYPE,
        source_id=document.id,
        chunk_index=0,
        chunk_text=text,
        embedding=[0.1] * settings.EMBEDDING_DIMENSION,
        embedding_model=STUB_EMBEDDING_MODEL,
        embedding_dimension=settings.EMBEDDING_DIMENSION,
        visible_to_roles=roles,
    )
    return document, chunk


def log_turn(user, conversation, *, question, citations, answered=True, consulted=None):
    """One logged turn with its citations, exactly as ``record_query`` writes them: one row per
    statement, positions from 1, ``chunk_id`` and ``chunk_uuid`` the same identifier.

    ``consulted`` is its ``retrieved_chunk_ids`` in rank order, every chunk supplied whether
    cited or not; by default the cited chunks alone."""
    consulted = [chunk for _, chunk in citations] if consulted is None else consulted
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


def delete_chunks_of(document):
    """The call ``reprocess_document`` and ``manage.py reindex`` make, and the one FR-15's
    deletion will make (D-07: no database foreign key from a chunk to its source)."""
    ContentChunk.objects.filter(source_type=DOCUMENT_SOURCE_TYPE, source_id=document.id).delete()


def order_after(earlier, later):
    """Force the later turn's timestamp past the earlier one's. ``timezone.now()`` is about
    15.6 ms granular on this platform, so two rows written in one tick can share an
    ``answered_at``, and the read orders by it."""
    QueryLog.objects.filter(pk=later.pk).update(
        answered_at=earlier.answered_at + timedelta(seconds=1)
    )


def demote(user, employee_role):
    get_user_model().objects.filter(pk=user.pk).update(role=employee_role)


# --- The precondition, asserted once rather than assumed in every test below ---------------


def test_deleting_the_chunk_leaves_the_row_with_a_null_chunk_and_the_identifier(employee):
    """What every test below reads: the row is still there, ``chunk_id`` NULL, ``chunk_uuid``
    still the identifier it cited. If this ever fails, the rest of the file is testing the
    rendering of a state that no longer arises."""
    document, chunk = make_document_with_chunk(
        employee, title="Contractor terms", roles=BOTH_ROLES, text=DELETED_PASSAGE
    )
    conversation = Conversation.objects.create(user=employee, title=QUESTION)
    turn = log_turn(employee, conversation, question=QUESTION, citations=[(DELETED_STATEMENT, chunk)])
    cited = chunk.id

    delete_chunks_of(document)

    [citation] = AnswerCitation.objects.filter(query=turn)
    assert citation.chunk_id is None
    assert citation.chunk_uuid == cited
    assert citation.statement_text == DELETED_STATEMENT  # the record keeps it; no reader shows it


# --- State 3: the only citation lost its chunk ---------------------------------------------


def test_a_turn_whose_only_citation_lost_its_chunk_renders_provenance_removed(session_client):
    """From an Employee session and an Administrator session.

    The turn renders exactly as a turn whose rows the cascade had deleted: six keys,
    ``provenance_removed`` true, ``answered`` false, no statements, PROVENANCE_REMOVED_MESSAGE.
    The deleted statement and its identifier are nowhere in the bytes.
    """
    user = session_client.user
    document, chunk = make_document_with_chunk(
        user, title="Contractor terms", roles=BOTH_ROLES, text=DELETED_PASSAGE
    )
    conversation = Conversation.objects.create(user=user, title=QUESTION)
    log_turn(user, conversation, question=QUESTION, citations=[(DELETED_STATEMENT, chunk)])
    cited = str(chunk.id)

    delete_chunks_of(document)
    response = session_client.client.get(detail_url(conversation.pk))

    assert response.status_code == 200
    [rendered] = response.json()["turns"]
    assert set(rendered) == TURN_FIELDS | {PROVENANCE_REMOVED_FIELD}
    assert rendered[PROVENANCE_REMOVED_FIELD] is True
    assert rendered["answered"] is False
    assert rendered["statements"] == []
    assert rendered["sources"] == []
    assert rendered["message"] == PROVENANCE_REMOVED_MESSAGE
    raw = response.content.decode()
    assert DELETED_STATEMENT not in raw
    assert DELETED_PASSAGE not in raw
    assert cited not in raw
    assert NO_ANSWER_MESSAGE not in raw


def test_a_provenance_removed_turn_carries_no_sources_though_a_consulted_passage_is_readable(
    session_client,
):
    """D-78 item 1, from an Employee session and an Administrator session.

    The turn cited one chunk, which is then deleted, and consulted a second it did not cite,
    which is still in the corpus and readable by this reader. The turn is state 3 — no row
    points at an existing chunk — and so carries ``sources: []``: a Sources panel is built only
    for a turn that RENDERS as answered, and listing the survivor under a turn whose answer
    cannot be shown would be a panel of nothing.
    """
    user = session_client.user
    deleted_document, deleted_chunk = make_document_with_chunk(
        user, title="Contractor terms", roles=BOTH_ROLES, text=DELETED_PASSAGE
    )
    _, consulted_chunk = make_document_with_chunk(
        user, title="Employee handbook", roles=BOTH_ROLES, text=LIVE_PASSAGE
    )
    conversation = Conversation.objects.create(user=user, title=QUESTION)
    log_turn(
        user, conversation, question=QUESTION,
        citations=[(DELETED_STATEMENT, deleted_chunk)],
        consulted=[deleted_chunk, consulted_chunk],
    )

    delete_chunks_of(deleted_document)
    response = session_client.client.get(detail_url(conversation.pk))

    [rendered] = response.json()["turns"]
    assert rendered[PROVENANCE_REMOVED_FIELD] is True
    assert rendered["statements"] == []
    assert rendered["sources"] == []
    raw = response.content.decode()
    assert str(consulted_chunk.id) not in raw
    assert LIVE_PASSAGE not in raw
    assert "Employee handbook" not in raw


# --- One live permitted citation beside a NULL one -----------------------------------------


def test_a_null_citation_beside_a_live_one_shows_only_the_live_statement_numbered_from_one(
    session_client,
):
    """From an Employee session and an Administrator session.

    The deleted document's statement came FIRST, so the live statement's stored position is 2.
    It renders as 1: a "[2]" with no "[1]" would announce that something was taken out. The
    turn is answered, carries five keys and no ``provenance_removed``, and the deleted
    statement's text and identifier are nowhere in the bytes. The stored positions are not
    rewritten.
    """
    user = session_client.user
    deleted_document, deleted_chunk = make_document_with_chunk(
        user, title="Contractor terms", roles=BOTH_ROLES, text=DELETED_PASSAGE
    )
    live_document, live_chunk = make_document_with_chunk(
        user, title="Employee handbook", roles=BOTH_ROLES, text=LIVE_PASSAGE
    )
    conversation = Conversation.objects.create(user=user, title=QUESTION)
    turn = log_turn(
        user,
        conversation,
        question=QUESTION,
        citations=[(DELETED_STATEMENT, deleted_chunk), (LIVE_STATEMENT, live_chunk)],
    )
    deleted_id = str(deleted_chunk.id)

    delete_chunks_of(deleted_document)
    response = session_client.client.get(detail_url(conversation.pk))

    assert response.status_code == 200
    [rendered] = response.json()["turns"]
    assert set(rendered) == TURN_FIELDS
    assert rendered["answered"] is True
    assert rendered["message"] is None
    assert rendered["statements"] == [
        {"position": 1, "text": LIVE_STATEMENT, "chunk_id": str(live_chunk.id)}
    ]
    # The panel lists the live document alone: the deleted chunk has no passage to return,
    # and nothing stands in for it (D-78 item 4).
    assert [(source["source_id"], source["passages"]) for source in rendered["sources"]] == [
        (str(live_document.id), [{"chunk_id": str(live_chunk.id), "text": LIVE_PASSAGE}])
    ]
    raw = response.content.decode()
    assert DELETED_STATEMENT not in raw
    assert DELETED_PASSAGE not in raw
    assert "Contractor terms" not in raw
    assert deleted_id not in raw
    assert PROVENANCE_REMOVED_FIELD not in raw
    assert PROVENANCE_REMOVED_MESSAGE not in raw
    # The record is not renumbered: the rows keep the positions the original reader saw.
    assert sorted(
        AnswerCitation.objects.filter(query=turn).values_list("position", "chunk_id")
    ) == [(1, None), (2, live_chunk.id)]


# --- The pairing, made the D-67 way: a NULL row against a re-scoped row -------------------


def test_a_null_chunk_turn_and_a_re_scoped_turn_are_told_apart_in_one_thread(
    administrator_client, administrator, employee_role
):
    """``test_provenance_removed_turn.py``'s pairing, with state 3 reached by SET_NULL
    rather than by deleting the rows.

    Turn one cites an Administrator-only chunk that still exists; the reader is then demoted,
    so it is out of scope — state 2, silent. Turn two's chunk is deleted, so its only row has
    ``chunk_id`` NULL — state 3. Under the refactor worth fearing, "no surviving citations"
    for "no row pointing at an existing chunk", turn one would be labelled provenance-removed
    and the demoted reader told that something had been taken out of their thread.
    """
    _, restricted_chunk = make_document_with_chunk(
        administrator, title="Board remuneration review", roles=ADMINISTRATOR_ONLY,
        text=RESTRICTED_PASSAGE,
    )
    deleted_document, deleted_chunk = make_document_with_chunk(
        administrator, title="Contractor terms", roles=BOTH_ROLES, text=DELETED_PASSAGE
    )
    conversation = Conversation.objects.create(user=administrator, title=QUESTION)
    re_scoped = log_turn(
        administrator, conversation, question=QUESTION,
        citations=[(RESTRICTED_STATEMENT, restricted_chunk)],
    )
    nulled = log_turn(
        administrator, conversation, question=SECOND_QUESTION,
        citations=[(DELETED_STATEMENT, deleted_chunk)],
    )
    order_after(re_scoped, nulled)
    delete_chunks_of(deleted_document)
    demote(administrator, employee_role)

    response = administrator_client.get(detail_url(conversation.pk))

    first, second = response.json()["turns"]
    # State 2: silent, six keys, the fixed no-answer text, no sources.
    assert set(first) == TURN_FIELDS
    assert first["answered"] is False
    assert first["message"] == NO_ANSWER_MESSAGE
    assert first["sources"] == []
    # State 3: named, seven keys, its own message, no sources.
    assert set(second) == TURN_FIELDS | {PROVENANCE_REMOVED_FIELD}
    assert second[PROVENANCE_REMOVED_FIELD] is True
    assert second["statements"] == []
    assert second["sources"] == []
    assert second["message"] == PROVENANCE_REMOVED_MESSAGE
    raw = response.content.decode()
    assert RESTRICTED_STATEMENT not in raw
    assert DELETED_STATEMENT not in raw


# --- Mixed: a NULL row and a live out-of-scope row is state 2, not state 3 ----------------


def test_a_null_citation_beside_a_live_out_of_scope_one_is_the_silent_state(
    administrator_client, administrator, employee_role
):
    """One turn cites a document that is then deleted, and an Administrator-only document that
    still exists; the reader is then demoted.

    Before D-67 the first row would simply be gone, leaving one row whose chunk exists and is
    out of this reader's scope: state 2, silent. It must still be state 2. The discriminator
    is whether any row still points at an existing chunk, read before scoping, and one does.
    Two plausible wrong predicates would render state 3 here: "some row lost its chunk", which
    reads the NULL rows instead of the live ones, and "no row survived scoping", which is the
    collapse ``test_provenance_removed_turn.py`` guards against. Either would also tell this
    reader that the turn's citations are no longer on record, when one of them is and is
    merely not theirs to read.

    Compared FIELD BY FIELD with a never-answered turn in the same thread, as
    ``test_provenance_removed_turn.py`` compares state 2 with state 1, so a new key, a
    changed message or a changed ``answered`` fails here.
    """
    _, restricted_chunk = make_document_with_chunk(
        administrator, title="Board remuneration review", roles=ADMINISTRATOR_ONLY,
        text=RESTRICTED_PASSAGE,
    )
    deleted_document, deleted_chunk = make_document_with_chunk(
        administrator, title="Contractor terms", roles=BOTH_ROLES, text=DELETED_PASSAGE
    )
    conversation = Conversation.objects.create(user=administrator, title=QUESTION)
    never_answered = log_turn(
        administrator, conversation, question=QUESTION, citations=[], answered=False
    )
    mixed = log_turn(
        administrator, conversation, question=THIRD_QUESTION,
        citations=[(DELETED_STATEMENT, deleted_chunk), (RESTRICTED_STATEMENT, restricted_chunk)],
    )
    order_after(never_answered, mixed)
    delete_chunks_of(deleted_document)
    demote(administrator, employee_role)

    response = administrator_client.get(detail_url(conversation.pk))

    first, second = response.json()["turns"]
    assert set(second) == TURN_FIELDS
    variable = {"asked_at", "question"}
    assert {key: value for key, value in first.items() if key not in variable} == {
        key: value for key, value in second.items() if key not in variable
    }
    assert second["message"] == NO_ANSWER_MESSAGE
    raw = response.content.decode()
    assert PROVENANCE_REMOVED_FIELD not in raw
    assert PROVENANCE_REMOVED_MESSAGE not in raw
    assert RESTRICTED_STATEMENT not in raw
    assert DELETED_STATEMENT not in raw
    assert str(restricted_chunk.id) not in raw
    # Both rows are still on record; one has lost its chunk, the other its reader.
    assert sorted(
        (chunk_id is None) for chunk_id in
        AnswerCitation.objects.filter(query=mixed).values_list("chunk_id", flat=True)
    ) == [False, True]


# --- The two helpers, against an argument built to tempt them ------------------------------


def test_the_scope_query_never_asks_about_a_null_chunk(employee):
    """``readable_thread_chunks`` returns the live readable chunks and nothing else. A turn
    whose every row is NULL yields an empty mapping rather than one keyed by None. (Until D-78
    this was ``permitted_citation_chunk_ids``, returning identifiers only; the one scope result
    now carries the rows, so the panel's passages come from the same query.)"""
    deleted_document, deleted_chunk = make_document_with_chunk(
        employee, title="Contractor terms", roles=BOTH_ROLES, text=DELETED_PASSAGE
    )
    _, live_chunk = make_document_with_chunk(
        employee, title="Employee handbook", roles=BOTH_ROLES, text=LIVE_PASSAGE
    )
    conversation = Conversation.objects.create(user=employee, title=QUESTION)
    both = log_turn(
        employee, conversation, question=QUESTION,
        citations=[(DELETED_STATEMENT, deleted_chunk), (LIVE_STATEMENT, live_chunk)],
    )
    only_deleted = log_turn(
        employee, conversation, question=SECOND_QUESTION,
        citations=[(DELETED_STATEMENT, deleted_chunk)],
    )
    delete_chunks_of(deleted_document)

    readable = readable_thread_chunks(
        [QueryLog.objects.get(pk=both.pk)], role_name=EMPLOYEE_ROLE_NAME
    )
    assert set(readable) == {live_chunk.id}
    assert readable[live_chunk.id].chunk_text == LIVE_PASSAGE
    assert readable_thread_chunks(
        [QueryLog.objects.get(pk=only_deleted.pk)], role_name=EMPLOYEE_ROLE_NAME
    ) == {}


def test_surviving_citations_never_returns_a_null_chunk_row_whatever_it_is_handed(employee):
    """The exclusion is by name, not by NULL happening to be absent from the permitted set.

    The context here is deliberately wrong — it holds a "readable" chunk under the key None —
    which no caller in the tree builds. A later change to how that mapping is assembled must not
    be able to let a NULL-chunk statement through.
    """
    deleted_document, deleted_chunk = make_document_with_chunk(
        employee, title="Contractor terms", roles=BOTH_ROLES, text=DELETED_PASSAGE
    )
    _, live_chunk = make_document_with_chunk(
        employee, title="Employee handbook", roles=BOTH_ROLES, text=LIVE_PASSAGE
    )
    conversation = Conversation.objects.create(user=employee, title=QUESTION)
    turn = log_turn(
        employee, conversation, question=QUESTION,
        citations=[(DELETED_STATEMENT, deleted_chunk), (LIVE_STATEMENT, live_chunk)],
    )
    delete_chunks_of(deleted_document)
    turn = QueryLog.objects.prefetch_related("citations").get(pk=turn.pk)

    serializer = ConversationTurnSerializer(
        context={"readable_chunks": {None: live_chunk, live_chunk.id: live_chunk}}
    )

    surviving = serializer.surviving_citations(turn)
    assert [citation.statement_text for citation in surviving] == [LIVE_STATEMENT]
    assert all(citation.chunk_id is not None for citation in surviving)
