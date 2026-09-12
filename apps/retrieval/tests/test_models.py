"""Conversations, QueryLog, SearchLogs and AnswerCitations (FR-12, FR-13, D-12)."""

import pytest
from django.core.exceptions import ValidationError
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


def test_citation_cascades_when_its_chunk_is_deleted(employee, content_chunk):
    query = make_query(employee, answered=True, answer_text="Twenty days.", no_answer_reason=None)
    AnswerCitation.objects.create(query=query, chunk=content_chunk, statement_text="Twenty days.", position=0)
    content_chunk.delete()
    assert AnswerCitation.objects.count() == 0
    assert QueryLog.objects.filter(pk=query.pk).exists()  # the log survives (D-12)


def test_citation_cascades_when_its_query_is_deleted(employee, content_chunk):
    query = make_query(employee, answered=True, answer_text="Twenty days.", no_answer_reason=None)
    AnswerCitation.objects.create(query=query, chunk=content_chunk, statement_text="Twenty days.", position=0)
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
