"""retrieval 0003 backfills ``chunk_uuid`` going forward and reverses cleanly (D-67).

The suite's first forward-and-backward data test of a migration. ``apps/core/tests/
test_schema.py`` uses ``MigrationExecutor`` only for the migration PLAN; this file drives the
executor itself, retrieval only, from 0002 to 0003 and back.

**How it stays out of every other test's way.** It runs in the ordinary per-test transaction,
not a transactional test: PostgreSQL's DDL is transactional, so the ALTERs, the
``django_migrations`` rows and the data are all rolled back when the test ends, pass or fail,
and the seeded roles a transactional flush would wipe are never touched. It ends at the
retrieval leaf anyway — 0004 since step 7 phase 4 added ``QueryLog.retrieval_rewrite`` — so
that a reader of the test can see the schema the rest of the suite expects is the one it
leaves. The query row is written through the historical registry for the same reason the
citation rows always were: at 0002 the live QueryLog model names a column the table does
not hold yet.

**``SET CONSTRAINTS ALL IMMEDIATE`` first, and why it is not a workaround for the migration.**
Django creates PostgreSQL foreign keys ``DEFERRABLE INITIALLY DEFERRED``, so a row inserted
inside a transaction leaves a pending trigger event on its table until commit, and PostgreSQL
refuses ``ALTER TABLE`` on a table with pending trigger events. In this test every citation
row is inserted inside the same transaction as the migration that alters the table. In a real
``migrate`` the rows were committed long before, the backfill changes no foreign-key column,
and nothing is pending. Making the checks immediate here fires each one at the end of its own
statement, which is what a committed row has already been through.

**What this file does not cover.**

- Migrating any app but retrieval. Every other app stays at its leaf throughout.
- A table large enough for the backfill's single ``UPDATE`` to matter. The demonstration
  corpus's query log is small, and the statement is one ``UPDATE ... SET chunk_uuid =
  chunk_id``.
"""

import pytest
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.core.constants import SOURCE_TYPES
from apps.documents.models import ContentChunk
from apps.retrieval.models import QueryLog

pytestmark = pytest.mark.django_db

BEFORE = ("retrieval", "0002_querylog_rejected_count")
AFTER = ("retrieval", "0003_answercitation_chunk_set_null")
# The retrieval leaf, which the test returns to at its end so it leaves the schema the
# rest of the suite expects (the transaction rollback would restore it regardless).
LATEST = ("retrieval", "0004_querylog_retrieval_rewrite")


def migrate_retrieval_to(node):
    """Move retrieval to ``node`` and leave every other app at its leaf.

    Returns the historical app registry at that state, so the test reads and writes the
    citation table through the model as it was at that migration rather than as it is now.
    A fresh executor each time, because one that has migrated keeps a stale view of what is
    applied.
    """
    executor = MigrationExecutor(connection)
    targets = [
        leaf for leaf in executor.loader.graph.leaf_nodes() if leaf[0] != "retrieval"
    ] + [node]
    executor.migrate(targets)
    executor.loader.build_graph()
    return executor.loader.project_state(targets).apps


def is_nullable(table, column):
    """``"YES"``, ``"NO"``, or None where the column does not exist."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s AND column_name = %s",
            [table, column],
        )
        row = cursor.fetchone()
    return None if row is None else row[0]


def make_chunk(document, index):
    return ContentChunk.objects.create(
        source_type=SOURCE_TYPES[0],
        source_id=document.id,
        chunk_index=index,
        chunk_text=f"Passage {index}.",
        embedding=[0.1] * settings.EMBEDDING_DIMENSION,
        embedding_model=STUB_EMBEDDING_MODEL,
        embedding_dimension=settings.EMBEDDING_DIMENSION,
    )


def test_0003_backfills_chunk_uuid_and_reverses_deleting_only_rows_whose_chunk_is_gone(
    employee, document
):
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")  # see the module docstring

    # --- At 0002: the old schema, and rows written under it ---------------------------------
    old_apps = migrate_retrieval_to(BEFORE)
    assert is_nullable("answer_citations", "chunk_id") == "NO"
    assert is_nullable("answer_citations", "chunk_uuid") is None

    kept_chunk = make_chunk(document, 0)
    lost_chunk = make_chunk(document, 1)
    # Written through the HISTORICAL model, not the live QueryLog: the table is at 0002
    # here, and the live model has gained a column since (retrieval 0004's
    # retrieval_rewrite, step 7 phase 4), so an INSERT through the live model would name
    # a column this state does not hold. The citation rows below were already written
    # through the historical registry for the same reason.
    OldQueryLog = old_apps.get_model("retrieval", "QueryLog")
    query = OldQueryLog.objects.create(
        user_id=employee.pk,
        question="How much annual leave do I accrue?",
        answer_text="Kept. Lost.",
        retrieved_chunk_ids=[kept_chunk.id, lost_chunk.id],
        answered=True,
        rejected_count=0,
    )
    OldCitation = old_apps.get_model("retrieval", "AnswerCitation")
    kept = OldCitation.objects.create(
        query_id=query.pk, chunk_id=kept_chunk.pk, statement_text="Kept.", position=1
    )
    lost = OldCitation.objects.create(
        query_id=query.pk, chunk_id=lost_chunk.pk, statement_text="Lost.", position=2
    )

    # --- Forward: chunk_uuid is backfilled from chunk_id, row by row ------------------------
    new_apps = migrate_retrieval_to(AFTER)
    assert is_nullable("answer_citations", "chunk_id") == "YES"
    assert is_nullable("answer_citations", "chunk_uuid") == "NO"
    Citation = new_apps.get_model("retrieval", "AnswerCitation")
    assert set(Citation.objects.values_list("pk", "chunk_id", "chunk_uuid")) == {
        (kept.pk, kept_chunk.pk, kept_chunk.pk),
        (lost.pk, lost_chunk.pk, lost_chunk.pk),
    }

    # The chunk behind one citation is deleted, through the CURRENT model, so the NULL comes
    # from on_delete=SET_NULL rather than being written by the test. (delete() clears the
    # instance's pk, so the identifier is taken first.)
    lost_chunk_id = lost_chunk.pk
    lost_chunk.delete()
    assert Citation.objects.get(pk=lost.pk).chunk_id is None
    assert Citation.objects.get(pk=lost.pk).chunk_uuid == lost_chunk_id

    # --- Reverse: exactly the row 0002's CASCADE would have deleted goes, and no other ------
    old_apps = migrate_retrieval_to(BEFORE)
    assert is_nullable("answer_citations", "chunk_id") == "NO"
    assert is_nullable("answer_citations", "chunk_uuid") is None
    OldCitation = old_apps.get_model("retrieval", "AnswerCitation")
    assert list(
        OldCitation.objects.values_list("pk", "query_id", "chunk_id", "statement_text", "position")
    ) == [(kept.pk, query.pk, kept_chunk.pk, "Kept.", 1)]
    # The query log is not a citation and is not touched by either direction (D-12).
    assert QueryLog.objects.filter(pk=query.pk).exists()

    # --- Forward again: the backfill runs over what the reverse left ------------------------
    new_apps = migrate_retrieval_to(AFTER)
    Citation = new_apps.get_model("retrieval", "AnswerCitation")
    assert list(Citation.objects.values_list("pk", "chunk_id", "chunk_uuid")) == [
        (kept.pk, kept_chunk.pk, kept_chunk.pk)
    ]

    # Leave retrieval at its leaf (see the module docstring); the row survives 0004 too.
    migrate_retrieval_to(LATEST)
    assert QueryLog.objects.get(pk=query.pk).retrieval_rewrite is None
