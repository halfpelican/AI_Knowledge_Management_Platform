"""Retrieval records: Conversations, QueryLog, SearchLogs and AnswerCitations
(docs/schema-v1.md section 1).

Models only. The retrieval logic itself is built in Stage 4 (FR-11, FR-12, FR-13).
Query and search logs are the project's main quality signal, so they survive
deletions: a deleted conversation leaves its queries behind (D-12).
"""

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.core.constants import NO_ANSWER_REASONS
from apps.core.models import NAME_MAX_LENGTH, uuid_primary_key, vocabulary_field


class Conversation(models.Model):
    id = uuid_primary_key("conversation_id")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="conversations"
    )
    title = models.CharField(max_length=NAME_MAX_LENGTH)
    last_updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "conversations"

    def __str__(self):
        return self.title


class QueryLog(models.Model):
    id = uuid_primary_key("query_id")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="queries")
    # Null for a one-off question, and set null when the conversation is deleted (D-12).
    conversation = models.ForeignKey(
        Conversation, on_delete=models.SET_NULL, null=True, blank=True, related_name="queries"
    )
    question = models.TextField()
    answer_text = models.TextField(null=True, blank=True)  # null where no answer was returned
    retrieved_chunk_ids = ArrayField(models.UUIDField(), default=list, blank=True)  # FR-12 traceability
    answered = models.BooleanField()
    # The two no-answer paths are recorded distinctly (CLAUDE.md invariant 5).
    no_answer_reason = vocabulary_field(NO_ANSWER_REASONS, null=True, blank=True)
    answered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "query_log"


class SearchLog(models.Model):
    id = uuid_primary_key("search_id")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="searches")
    query_text = models.TextField()
    result_count = models.PositiveIntegerField()  # computed after permission filtering
    searched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "search_logs"


class AnswerCitation(models.Model):
    # Rows exist only for statements that survived verification (CLAUDE.md invariant 4).
    id = uuid_primary_key("citation_id")
    query = models.ForeignKey(QueryLog, on_delete=models.CASCADE, related_name="citations")
    chunk = models.ForeignKey(
        "documents.ContentChunk", on_delete=models.CASCADE, related_name="citations"
    )
    statement_text = models.TextField()
    position = models.PositiveIntegerField()  # order within the answer

    class Meta:
        db_table = "answer_citations"
