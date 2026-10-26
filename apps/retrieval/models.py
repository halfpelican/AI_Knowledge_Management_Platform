"""Retrieval records: Conversations, QueryLog, SearchLogs and AnswerCitations
(docs/schema-v1.md section 1).

Models only. The retrieval logic itself is built in Stage 4 (FR-11, FR-12, FR-13).
Query and search logs are the project's main quality signal, so they survive
deletions: a deleted conversation leaves its queries behind (D-12), and a deleted chunk
leaves its citations behind with a NULL chunk and the identifier kept (D-67).
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
    """One row per question that reached retrieval: FR-12 traceability and FR-19 evidence.

    Written by ``apps.retrieval.query_log.record_query`` at all three of the pipeline's
    exits — answered, no-answer path A and no-answer path B — with its AnswerCitations in
    the same transaction.

    **``no_answer_reason`` and ``rejected_count`` are RECORD-ONLY. Item 11's serializer
    must not expose either, and no serializer after it may.** The two no-answer paths
    return byte-for-byte the same reply on purpose: a caller who could tell them apart
    would know that material exists which could not be cited, which is the disclosure
    invariant 1 forbids and which a user would act on. These two columns are the only
    place the distinction lives, and they are for the team reading the log, not for the
    person who asked the question.

    **``rejected_count`` is NULL exactly when generation was not called.** NULL means
    "the model was never asked", which today is no-answer path A — nothing cleared
    RELEVANCE_THRESHOLD, so there was nothing to generate from — and will also be the
    keyword-search path when it exists. **NULL never means "path B did not occur", and it
    never means zero.** Where generation ran the column holds an integer, including 0 for
    a response whose every citation checked out, and including answered rows: an answered
    row with ``rejected_count`` 1 is the early warning, the case where fabrication is
    happening but has not yet cost an answer, and it would be invisible if the column were
    written on the no-answer path alone.

    Like ``no_answer_reason``, this is a field the proposal does not name explicitly, added
    because a stated requirement needs a distinction recorded (docs/schema-v1.md section 1
    makes the same argument for the other one). Invariant 7 requires the two kinds of path
    B to be separable — the model declining with an empty statement list, versus
    verification rejecting every statement it proposed — and both carry the same reason
    code, because 7.10 step 10 folds them into one and NO_ANSWER_REASONS holds exactly two
    values. This column is how they are told apart. Stage 4 item 6's live runs are the
    evidence: before the prompt fix, 2 questions where the model declined and 3 where
    verification rejected everything; after it, 6 and 0. The aggregate moved 5 to 6 and
    would have read as "no effect". The finding — that the fix removed one failure mode
    while the other grew — does not exist without the split.

    A count, and never the claimed identifier, though 7.9 logs both: a fabricated
    identifier has no referent, and storing one invites a later reader to resolve it
    against ContentChunks and treat a hit or a miss as provenance. The count carries the
    whole diagnostic and nothing that could be mistaken for a source.
    """

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
    # The two no-answer paths are recorded distinctly (CLAUDE.md invariant 7). Record-only:
    # no serializer exposes it. See the class docstring.
    no_answer_reason = vocabulary_field(NO_ANSWER_REASONS, null=True, blank=True)
    # Statements whose citation was not one of the identifiers supplied to the model.
    # NULL where generation was not called; 0 where it was called and nothing was
    # rejected. Record-only, like the reason above. See the class docstring for why the
    # null semantics matter and why this is a count rather than the claimed identifier.
    rejected_count = models.PositiveIntegerField(null=True, blank=True)
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
    """One verified statement of a logged answer and the chunk it cited (FR-12 traceability).

    Rows exist only for statements that survived verification (CLAUDE.md invariant 6).

    **``chunk`` is SET_NULL and ``chunk_uuid`` keeps the identifier (D-67, Stage 5 item 1a).**
    Until retrieval 0003 the foreign key was CASCADE (D-12), so a reprocess, a
    ``manage.py reindex`` or FR-15's deletion destroyed every citation of the chunks it
    removed, and FR-12's traceability record with them. Now the row survives the chunk:
    ``chunk_id`` becomes NULL, and ``chunk_uuid`` still names the chunk that was cited, so
    the question, the identifiers and the verified citations can be traced after the
    source is gone. ``record_query`` writes both columns with the same UUID.

    **No passage text is stored here, and none may be.** FR-15 deletes a document's
    extracted content and embeddings "so that deleted material cannot subsequently be
    surfaced through search"; a snapshot of the passage would be that material surviving
    the delete. ``chunk_uuid`` is an identifier and resolves to nothing once the chunk is
    gone, which is the point.

    **A row whose ``chunk_id`` is NULL is REMOVED for every reader**, which is to say it is
    read exactly as a row the old CASCADE had deleted: its statement is not shown, its
    identifier is not shown, and a turn left with no other row is rendered as if it had no
    rows at all. The reopened-turn serializer (``apps/api/serializers.py``) is the reader,
    and since Stage 5 item 4b (D-78) it builds a reopened turn's passage expansion and
    Sources panel under the same rule: a NULL-chunk row contributes nothing to either. Any
    later reader must treat it the same way. The statement text stays in the row, as the
    record of what was answered, and is never rendered from it.
    """

    id = uuid_primary_key("citation_id")
    query = models.ForeignKey(QueryLog, on_delete=models.CASCADE, related_name="citations")
    # NULL once the chunk is deleted. NULL means "the chunk no longer exists", and nothing
    # else: the database foreign key still refuses a chunk_id that names no row.
    chunk = models.ForeignKey(
        "documents.ContentChunk", null=True, on_delete=models.SET_NULL, related_name="citations"
    )
    # The cited chunk's identifier, written with chunk_id and kept when chunk_id is nulled.
    # An identifier and never text: see the class docstring.
    chunk_uuid = models.UUIDField()
    statement_text = models.TextField()
    position = models.PositiveIntegerField()  # order within the answer

    class Meta:
        db_table = "answer_citations"
