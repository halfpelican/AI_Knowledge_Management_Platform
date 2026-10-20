"""A stored turn whose cited chunks were deleted stops claiming the question is
unanswerable — and a RE-SCOPED turn still says nothing at all (Stage 4 item 1c).

``ConversationTurnSerializer`` rendered three states as two. The two that must stay
indistinguishable still are; the third is separated here:

1. ``answered`` False — never answered. The silent no-answer state. **Unchanged.**
2. ``answered`` True, a citation row **still points at an existing chunk**, and none survives
   the reader's scope — re-scoped. **Byte-for-byte state 1**, which is
   ``apps/api/tests/test_fr11_thread_scope.py``'s whole subject and invariant 1's requirement:
   a notice that something was taken out is itself a disclosure that material exists which
   this role may not read.
3. ``answered`` True and **no citation row points at a chunk that still exists** — both
   ``reprocess_document`` and ``manage.py reindex`` delete a source's chunks and write new
   ones with fresh UUIDs, while the passage still exists, word for word, under a new
   identifier. Until D-67 (Stage 5 item 1a) ``AnswerCitation.chunk`` was
   ``on_delete=CASCADE`` (D-12) and the citation rows were destroyed with the chunks; since
   D-67 it is SET_NULL, the rows survive with ``chunk_id`` NULL, and the serializer reads such
   a row exactly as a destroyed one. ``apps/api/tests/test_fr12_traceability_survives_reprocess.py``
   asserts what happens to the rows; this file is about what the reader is then told.

**Why separating 3 is safe, which is the argument the whole file rests on.** State 3 says
nothing whatever about permissions. The discriminator is whether any citation row still points
at an existing chunk, read before any scoping, not whether one survived scoping: an operation
deleted the chunks the record pointed at, and on a re-index the material is still there and
this reader may well be entitled to every word of it. Saying "this answer's sources are no
longer on record" therefore discloses nothing about restricted content, where saying a turn
was re-scoped would disclose exactly that.

**What state 3 must not say, and what it must not stay silent about.** No statements —
invariant 6 stands, and a statement without its citation is what it forbids. But not
NO_ANSWER_MESSAGE either: that text says the question cannot be answered from the available
knowledge base, which is false of a turn that WAS answered from material still in the corpus.
The interface stating something untrue about the corpus is not a security measure, it is a
lie, and a user who acts on it stops asking a question the system can answer.

**The pairing test is what holds the two apart.** States 2 and 3 are asserted in one body, on
one thread, read by one reader — because either half alone would still pass if a refactor
simplified ``not has_live_citation_rows`` into "no surviving citations", which is the
simplification that collapses 2 into 3 and reopens the invariant-1 disclosure.

**How each state is reached here, and why not always by the shipped route.** The
end-to-end test drives ``manage.py reindex``, the real path CLAUDE.md section 4 mandates on
any provider change — the cheaper of the two, since it rebuilds from
``ExtractedContent.extracted_text`` and needs no uploaded file. Since D-67 it leaves the
citation row in place with ``chunk_id`` NULL. The pairing test cannot use it: a re-index
rebuilds EVERY source, so it would take both turns' chunks and leave no state 2 to compare
against. There, the rows are deleted directly, which is what the cascade did before D-67. A
turn with no rows at all still renders state 3 after D-67, which this keeps asserted;
``test_null_chunk_citations_on_a_reopened_turn.py`` makes the same pairing with the chunk
deleted and the row left NULL, the way SET_NULL now produces it.

**What this file does not cover.**

- **The front end.** ``frontend/src/`` has no test runner. ``frontend/src/utils/turns.js`` is
  the pure mapping the screen branches on, hand-verified against bodies captured from this
  suite; the JSX around it is verified by build, lint and reading.
- **The live ``POST /api/ask`` reply**, which cannot be in state 3: its citation rows are
  written in the same transaction as the answer (``apps/retrieval/query_log.py``), so there
  is no window in which the reply could be rendered without them.
- **Whether the rows should be destroyed at all.** D-67 decided they should not;
  ``test_fr12_traceability_survives_reprocess.py`` asserts that they are not.
"""

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from datetime import timedelta

from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.api.answers import RECORD_ONLY_FIELDS
from apps.api.serializers import PROVENANCE_REMOVED_FIELD
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    DOCUMENT_INDEXED,
    EMPLOYEE_ROLE_NAME,
    NO_ANSWER_MESSAGE,
    NO_ANSWER_REASONS,
    PROVENANCE_REMOVED_MESSAGE,
    SOURCE_TYPES,
)
from apps.documents.models import ContentChunk, Document, ExtractedContent
from apps.retrieval.models import AnswerCitation, Conversation, QueryLog
from apps.retrieval.scoping import scoped_chunks

pytestmark = pytest.mark.django_db

CONVERSATIONS_URL = "/api/conversations"
DOCUMENT_SOURCE_TYPE = SOURCE_TYPES[0]
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]
ADMINISTRATOR_ONLY = [ADMINISTRATOR_ROLE_NAME]

# The keys every turn carries: five since item 11, and ``sources`` since D-78, on every turn so
# the states change together. ``provenance_removed`` is the seventh and appears only in state 3,
# which is the guarantee asserted below rather than a convenience.
TURN_FIELDS = {"question", "answered", "asked_at", "message", "statements", "sources"}

QUESTION = "How much annual leave do I accrue each year?"
SECOND_QUESTION = "And who signs those accruals off each year?"
PASSAGE_TEXT = "Staff accrue twenty days of annual leave a year."
STATEMENT = "Staff accrue twenty days of annual leave a year."
RESTRICTED_PASSAGE_TEXT = "Directors accrue leave at twice the ordinary rate."
RESTRICTED_STATEMENT = "Directors accrue annual leave at twice the ordinary rate."

# Words that would turn this state, or the re-scoped one, into a disclosure about
# permissions. The message may say what happened to the RECORD and nothing about who may read
# what: the same list ``test_fr11_thread_scope.py`` holds the re-scoped body to.
PERMISSION_WORDS = (
    "withheld",
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


def make_indexed_document(uploader, *, title, roles, text):
    """A document as ingestion leaves it: Indexed, with its extracted text and one chunk.

    The ``ExtractedContent`` row is what makes it re-indexable — ``manage.py reindex``
    rebuilds from the stored text and skips a document that has none.
    """
    document = Document.objects.create(
        title=title,
        file_type="txt",
        uploaded_by=uploader,
        visible_to_roles=roles,
        status=DOCUMENT_INDEXED,
    )
    ExtractedContent.objects.create(document=document, extracted_text=text)
    return document, make_chunk(source_id=document.id, roles=roles, text=text)


def log_turn(user, conversation, *, question, citations, answered=True, consulted=None):
    """One logged turn with its citations, exactly as ``record_query`` writes them.

    ``consulted`` is its ``retrieved_chunk_ids`` in rank order, every chunk supplied whether
    cited or not; by default the cited chunks alone.
    """
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


def order_after(earlier, later):
    """Force the second turn's timestamp past the first.

    ``timezone.now()`` is about 15.6 ms granular on this platform, so two rows written in one
    tick can share an ``answered_at`` and the read orders by it. The turns are told apart by
    position in the list, so the order is made rather than hoped for.
    """
    QueryLog.objects.filter(pk=later.pk).update(
        answered_at=earlier.answered_at + timedelta(seconds=1)
    )


# --- State 3, reached by the path CLAUDE.md section 4 mandates ------------------------------


def test_a_turn_whose_cited_chunks_were_deleted_says_so_instead_of_no_answer(
    session_client,
):
    """``manage.py reindex``, then reopen the thread — from an Employee session and an
    Administrator session, because either role's threads are affected by one operator's
    re-index and neither is told anything the other is not. (Named
    ``..._whose_citation_rows_were_destroyed_...`` until D-67: the re-index used to delete the
    row, and now leaves it with ``chunk_id`` NULL. The rendering asserted is the same.)

    The reader is told the answer's sources are no longer on record. They are NOT told the
    question cannot be answered from the knowledge base, which is what the turn said before
    this change and which is false: the material is still there, re-embedded, under new
    identifiers.
    """
    user = session_client.user
    document, chunk = make_indexed_document(
        user, title="Leave policy", roles=BOTH_ROLES, text=PASSAGE_TEXT
    )
    conversation = Conversation.objects.create(user=user, title=QUESTION)
    turn = log_turn(user, conversation, question=QUESTION, citations=[(STATEMENT, chunk)])
    assert AnswerCitation.objects.filter(query=turn).count() == 1

    call_command("reindex")

    response = session_client.client.get(detail_url(conversation.pk))

    assert response.status_code == 200
    [rendered] = response.json()["turns"]
    assert set(rendered) == TURN_FIELDS | {PROVENANCE_REMOVED_FIELD}
    assert rendered[PROVENANCE_REMOVED_FIELD] is True
    assert rendered["answered"] is False  # nothing may be shown without its citation
    assert rendered["statements"] == []  # invariant 6
    assert rendered["sources"] == []  # no panel under a turn that shows no answer (D-78)
    assert rendered["message"] == PROVENANCE_REMOVED_MESSAGE
    raw = response.content.decode()
    assert NO_ANSWER_MESSAGE not in raw  # the sentence that would have been the lie
    assert STATEMENT not in raw  # invariant 6: no statement without its citation
    # The question is the user's own words and stays, as does the title (D-42, D-43).
    assert rendered["question"] == QUESTION
    # And the material really is still there, which is what makes the message true.
    assert ContentChunk.objects.filter(
        source_type=DOCUMENT_SOURCE_TYPE, source_id=document.id
    ).exists()
    assert QueryLog.objects.get(pk=turn.pk).answered is True  # the record is untouched


def test_the_message_says_what_happened_to_the_record_and_nothing_about_permissions(
    employee_client, employee
):
    """The copy itself, asserted like D-51 asserts that "Too large to index" contains no
    "failed": a message that reached for permission vocabulary would make this state read as
    a re-scope, which is the one thing it must never look like.

    Also asserted: the state 3 body carries no record-only field and no no-answer reason, so
    the new rendering is not a second route past the two columns item 11 kept out of it.
    """
    document, chunk = make_indexed_document(
        employee, title="Leave policy", roles=BOTH_ROLES, text=PASSAGE_TEXT
    )
    conversation = Conversation.objects.create(user=employee, title=QUESTION)
    log_turn(employee, conversation, question=QUESTION, citations=[(STATEMENT, chunk)])
    call_command("reindex")

    response = employee_client.get(detail_url(conversation.pk))

    lowered = PROVENANCE_REMOVED_MESSAGE.lower()
    for word in PERMISSION_WORDS:
        assert word not in lowered, word
    raw = response.content.decode().lower()
    for field in RECORD_ONLY_FIELDS + NO_ANSWER_REASONS:
        assert field.lower() not in raw, field
    # No count of anything: a number here would be the "something was taken out" notice in
    # numeric form, and this state has no more use for one than the re-scoped state does.
    assert "count" not in raw


# --- State 1 unchanged, and state 2 still indistinguishable from it ------------------------


def test_a_never_answered_turn_carries_no_new_field_and_the_same_message(employee_client, employee):
    """State 1, asserted so that the field cannot quietly appear on every turn."""
    conversation = Conversation.objects.create(user=employee, title=QUESTION)
    log_turn(employee, conversation, question=QUESTION, citations=[], answered=False)

    response = employee_client.get(detail_url(conversation.pk))

    [rendered] = response.json()["turns"]
    assert set(rendered) == TURN_FIELDS
    assert rendered["answered"] is False
    assert rendered["message"] == NO_ANSWER_MESSAGE
    assert rendered["sources"] == []
    assert PROVENANCE_REMOVED_FIELD not in response.content.decode()


def test_a_re_scoped_turn_renders_exactly_as_a_never_answered_one(
    administrator_client, administrator, employee, employee_role
):
    """State 2, which item 1c must not weaken: the invariant-1 case.

    One thread, two turns, one reader. The first was never answered; the second was answered
    from Administrator-only material and the reader has since been demoted. Their rendered
    bodies are compared FIELD BY FIELD, excluding only the timestamp and the question text
    they cannot share — so a new key, a changed message or a changed ``answered`` on either
    one fails here. The stronger form of the existing removal-vocabulary assertions: instead
    of listing words a notice might use, this asserts the two states are the same body.

    **The re-scoped turn also consulted a passage the demoted reader may STILL read**, and
    cited nothing from it (D-78). Its panel would not be empty if one were built, so this is
    where a panel built for a turn stored as answered, rather than one that renders as
    answered, shows: the re-scoped turn would list the handbook and the never-answered one
    could not.
    """
    _, restricted_chunk = make_indexed_document(
        administrator,
        title="Board remuneration review",
        roles=ADMINISTRATOR_ONLY,
        text=RESTRICTED_PASSAGE_TEXT,
    )
    _, readable_chunk = make_indexed_document(
        administrator, title="Employee handbook", roles=BOTH_ROLES, text=PASSAGE_TEXT
    )
    conversation = Conversation.objects.create(user=administrator, title=QUESTION)
    never_answered = log_turn(
        administrator, conversation, question=QUESTION, citations=[], answered=False
    )
    re_scoped = log_turn(
        administrator,
        conversation,
        question=SECOND_QUESTION,
        citations=[(RESTRICTED_STATEMENT, restricted_chunk)],
        consulted=[restricted_chunk, readable_chunk],
    )
    order_after(never_answered, re_scoped)
    get_user_model().objects.filter(pk=administrator.pk).update(role=employee_role)
    # The premise: the uncited consulted passage is still in the demoted reader's scope.
    assert scoped_chunks(role_name=EMPLOYEE_ROLE_NAME).filter(id=readable_chunk.id).exists()

    response = administrator_client.get(detail_url(conversation.pk))

    first, second = response.json()["turns"]
    variable = {"asked_at", "question"}
    assert {key: value for key, value in first.items() if key not in variable} == {
        key: value for key, value in second.items() if key not in variable
    }
    assert second["message"] == NO_ANSWER_MESSAGE
    assert second["sources"] == []
    raw = response.content.decode()
    assert PROVENANCE_REMOVED_FIELD not in raw
    assert PROVENANCE_REMOVED_MESSAGE not in raw
    assert RESTRICTED_STATEMENT not in raw
    assert str(restricted_chunk.id) not in raw
    assert str(readable_chunk.id) not in raw
    assert "Employee handbook" not in raw
    # The rows are all still there; only this reader may not see them (FR-19's evidence).
    assert AnswerCitation.objects.filter(query=re_scoped).count() == 1


# --- The pairing: both states in one body, so neither half can be collapsed ----------------


def test_a_re_scoped_turn_and_a_provenance_removed_turn_are_told_apart_in_one_thread(
    administrator_client, administrator, employee_role
):
    """The discriminator, asserted as a pair (the shape D-51 argues for).

    Turn one cites a chunk that STILL EXISTS and is now out of the reader's scope; turn two's
    citation rows are GONE. Either assertion alone would still pass under the refactor worth
    fearing — ``not has_live_citation_rows`` simplified to "no surviving citations" — which
    would label turn one as provenance-removed and tell a demoted reader that something had
    been taken out of their own thread. Both in one test, so the collapse fails.

    The rows are deleted here rather than re-indexed away, because a re-index rebuilds every
    source and would leave no turn in state 2 to compare against. Deleting them is what the
    ``on_delete=CASCADE`` did before D-67; since D-67 a deleted chunk leaves the row with
    ``chunk_id`` NULL instead, and ``test_null_chunk_citations_on_a_reopened_turn.py`` makes
    this same pairing that way. ``test_fr12_traceability_survives_reprocess.py`` is where the
    two shipped routes that delete chunks are exercised.
    """
    _, restricted_chunk = make_indexed_document(
        administrator,
        title="Board remuneration review",
        roles=ADMINISTRATOR_ONLY,
        text=RESTRICTED_PASSAGE_TEXT,
    )
    _, shared_chunk = make_indexed_document(
        administrator, title="Employee handbook", roles=BOTH_ROLES, text=PASSAGE_TEXT
    )
    conversation = Conversation.objects.create(user=administrator, title=QUESTION)
    re_scoped = log_turn(
        administrator,
        conversation,
        question=QUESTION,
        citations=[(RESTRICTED_STATEMENT, restricted_chunk)],
    )
    destroyed = log_turn(
        administrator,
        conversation,
        question=SECOND_QUESTION,
        citations=[(STATEMENT, shared_chunk)],
    )
    order_after(re_scoped, destroyed)
    # What the cascade did, before D-67, when the chunk was deleted and rewritten. A turn
    # with no rows at all must still render state 3.
    AnswerCitation.objects.filter(query=destroyed).delete()
    get_user_model().objects.filter(pk=administrator.pk).update(role=employee_role)

    body = administrator_client.get(detail_url(conversation.pk)).json()

    first, second = body["turns"]
    # State 2: silent, six keys, the fixed no-answer text, no sources.
    assert set(first) == TURN_FIELDS
    assert first["answered"] is False
    assert first["message"] == NO_ANSWER_MESSAGE
    assert first["sources"] == []
    # State 3: named, seven keys, its own message, no sources.
    assert set(second) == TURN_FIELDS | {PROVENANCE_REMOVED_FIELD}
    assert second[PROVENANCE_REMOVED_FIELD] is True
    assert second["answered"] is False
    assert second["statements"] == []
    assert second["sources"] == []
    assert second["message"] == PROVENANCE_REMOVED_MESSAGE


def test_an_answered_turn_carries_neither_the_field_nor_the_message(session_client):
    """The negative control every absence above is paired with: an ordinary readable turn.

    From both roles, since this is the state the route serves most of the time and the one a
    regression would be noticed in last. It carries its Sources panel (D-78), so the empty
    panels above are absences of something an answered turn has.
    """
    user = session_client.user
    document, chunk = make_indexed_document(
        user, title="Employee handbook", roles=BOTH_ROLES, text=PASSAGE_TEXT
    )
    conversation = Conversation.objects.create(user=user, title=QUESTION)
    log_turn(user, conversation, question=QUESTION, citations=[(STATEMENT, chunk)])

    response = session_client.client.get(detail_url(conversation.pk))

    [rendered] = response.json()["turns"]
    assert set(rendered) == TURN_FIELDS
    assert rendered["answered"] is True
    assert rendered["message"] is None
    assert [statement["text"] for statement in rendered["statements"]] == [STATEMENT]
    assert [(source["source_id"], source["passages"]) for source in rendered["sources"]] == [
        (str(document.id), [{"chunk_id": str(chunk.id), "text": PASSAGE_TEXT}])
    ]
    raw = response.content.decode()
    assert PROVENANCE_REMOVED_FIELD not in raw
    assert PROVENANCE_REMOVED_MESSAGE not in raw
