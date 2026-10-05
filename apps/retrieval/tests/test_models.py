"""Conversations, QueryLog, SearchLogs and AnswerCitations (FR-12, FR-13, D-12, D-67)."""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.core.constants import NO_ANSWER_REASONS
from apps.retrieval.models import AnswerCitation, Conversation, QueryLog, SearchLog

pytestmark = pytest.mark.django_db


def make_query(user, conversation=None, **overrides):
    values = {
        "user": user,
        "conversation": conversation,
        "question": "How much annual leave do I get?",
        "answered": False,
        "no_answer_reason": NO_ANSWER_REASONS[0],
    }
    values.update(overrides)
    return QueryLog.objects.create(**values)


def test_deleting_a_conversation_leaves_its_queries_as_one_offs(employee):
    conversation = Conversation.objects.create(user=employee, title="Leave policy questions")
    query = make_query(employee, conversation)
    conversation.delete()
    query.refresh_from_db()
    assert query.conversation is None
    assert QueryLog.objects.count() == 1


def test_no_answer_reason_vocabulary_and_nullability(employee):
    assert [choice for choice, _ in QueryLog._meta.get_field("no_answer_reason").choices] == list(NO_ANSWER_REASONS)
    answered = make_query(employee, answered=True, answer_text="Twenty days.", no_answer_reason=None)
    answered.full_clean()
    answered.no_answer_reason = "model_declined"
    with pytest.raises(ValidationError) as excinfo:
        answered.full_clean()
    assert "no_answer_reason" in excinfo.value.error_dict


def test_retrieved_chunk_ids_is_an_array_of_uuids(employee, content_chunk):
    query = make_query(employee, retrieved_chunk_ids=[content_chunk.id])
    query.refresh_from_db()
    assert query.retrieved_chunk_ids == [content_chunk.id]
    assert make_query(employee).retrieved_chunk_ids == []


def make_citation(query, chunk):
    """A citation as ``record_query`` writes one: ``chunk_id`` and ``chunk_uuid`` the same."""
    return AnswerCitation.objects.create(
        query=query, chunk=chunk, chunk_uuid=chunk.id, statement_text="Twenty days.", position=1
    )


def test_citation_survives_its_chunk_with_the_chunk_nulled_and_the_identifier_kept(
    employee, content_chunk
):
    """SET_NULL, not CASCADE (D-67, Stage 5 item 1a; this test asserted the cascade until then).

    FR-12's traceability clause: the verified citations are logged "so that any answer can
    later be traced to the material that produced it". The row outlives the chunk, the
    foreign key is NULL because there is nothing left to point at, and ``chunk_uuid`` still
    names what was cited. The statement and its position are untouched.
    """
    query = make_query(employee, answered=True, answer_text="Twenty days.", no_answer_reason=None)
    citation = make_citation(query, content_chunk)
    cited = content_chunk.id

    content_chunk.delete()

    citation.refresh_from_db()
    assert citation.chunk_id is None
    assert citation.chunk_uuid == cited
    assert citation.statement_text == "Twenty days."
    assert citation.position == 1
    assert QueryLog.objects.filter(pk=query.pk).exists()  # the log survives (D-12)


def test_chunk_uuid_is_required(employee, content_chunk):
    """A citation that cannot be traced once its chunk is gone is refused at the database.

    ``chunk_uuid`` has no default and is NOT NULL, so a writer that sets ``chunk`` and forgets
    the identifier fails here rather than storing a row that loses its provenance on the
    first re-index.
    """
    query = make_query(employee, answered=True, answer_text="Twenty days.", no_answer_reason=None)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            AnswerCitation.objects.create(
                query=query, chunk=content_chunk, statement_text="Twenty days.", position=1
            )


def test_citation_cascades_when_its_query_is_deleted(employee, content_chunk):
    query = make_query(employee, answered=True, answer_text="Twenty days.", no_answer_reason=None)
    make_citation(query, content_chunk)
    query.delete()
    assert AnswerCitation.objects.count() == 0


def test_deleting_a_user_with_queries_or_searches_is_protected(employee):
    make_query(employee)
    with pytest.raises(ProtectedError):
        employee.delete()
    QueryLog.objects.all().delete()
    SearchLog.objects.create(user=employee, query_text="leave", result_count=0)
    with pytest.raises(ProtectedError):
        employee.delete()


def test_search_log_records_the_post_filter_result_count(employee):
    search = SearchLog.objects.create(user=employee, query_text="annual leave", result_count=3)
    search.refresh_from_db()
    assert search.result_count == 3
    assert search.searched_at is not None
