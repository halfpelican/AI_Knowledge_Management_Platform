"""retrieval 0004 applies and reverses: FR-19's three tables (D-107).

Follows ``apps/documents/tests/test_migration_0008_document_analysis.py``: the executor itself is
driven, for ``retrieval`` only, from 0003 to 0004 and back and forward again, in the ordinary
per-test transaction. PostgreSQL's DDL is transactional, so the CREATEs, the DROPs, the
``django_migrations`` rows and the data roll back when the test ends, and the test ends at 0004 so
the schema it leaves is the one the rest of the suite expects.

``SET CONSTRAINTS ALL IMMEDIATE`` first, for the reason test_migration_0003_citation_set_null.py
gives: rows inserted in this transaction leave pending deferred foreign-key checks, and PostgreSQL
refuses to drop a table while one is pending. In a real ``migrate`` the rows were committed long
before.

What this file does not cover: migrating any app but ``retrieval``.
"""

import pytest
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.core.constants import NO_RELEVANT_PASSAGE
from apps.retrieval.models import KnowledgeGap, QueryLog

pytestmark = pytest.mark.django_db

BEFORE = ("retrieval", "0003_answercitation_chunk_set_null")
AFTER = ("retrieval", "0004_fr19_knowledge_gaps")
TABLES = ("knowledge_gaps", "knowledge_gap_items", "knowledge_gap_cycles")


def migrate_retrieval_to(node):
    executor = MigrationExecutor(connection)
    targets = [leaf for leaf in executor.loader.graph.leaf_nodes() if leaf[0] != "retrieval"] + [node]
    executor.migrate(targets)
    executor.loader.build_graph()
    return executor.loader.project_state(targets).apps


def columns_of(table):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s",
            [table],
        )
        return {row[0] for row in cursor.fetchall()}


def test_0004_is_the_leaf_of_retrieval():
    leaves = [key for key in MigrationExecutor(connection).loader.graph.leaf_nodes() if key[0] == "retrieval"]
    assert leaves == [AFTER]


def test_0004_applies_and_reverses_leaving_the_logs_as_they_were(employee):
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")  # see the module docstring
    question = QueryLog.objects.create(
        user=employee, question="Where is the parking permit form?", answered=False,
        no_answer_reason=NO_RELEVANT_PASSAGE,
    )

    # --- At 0003: none of the three tables ------------------------------------------------------
    migrate_retrieval_to(BEFORE)
    assert all(columns_of(table) == set() for table in TABLES)

    # --- Forward: the three tables, with the columns docs/schema-v1.md section 1 gives -----------
    new_apps = migrate_retrieval_to(AFTER)
    assert columns_of("knowledge_gaps") == {
        "gap_id", "subject", "occurrence_count", "status", "first_seen_at", "last_seen_at",
        "embedding", "embedding_model",
    }
    assert columns_of("knowledge_gap_items") == {"gap_item_id", "gap_id", "query_id", "search_id", "added_at"}
    assert columns_of("knowledge_gap_cycles") == {
        "cycle_id", "started_at", "finished_at", "triggered_by", "queries_considered",
        "searches_considered", "entries_created", "entries_updated",
    }
    Gap = new_apps.get_model("retrieval", "KnowledgeGap")
    Item = new_apps.get_model("retrieval", "KnowledgeGapItem")
    now = timezone.now()
    gap = Gap.objects.create(
        subject=question.question, occurrence_count=1, first_seen_at=now, last_seen_at=now,
        embedding=[0.5] * settings.EMBEDDING_DIMENSION, embedding_model="stub-embed",
    )
    Item.objects.create(gap_id=gap.pk, query_id=question.pk)

    # --- Reverse: the three tables go, the log row stays -----------------------------------------
    old_apps = migrate_retrieval_to(BEFORE)
    assert all(columns_of(table) == set() for table in TABLES)
    OldQueryLog = old_apps.get_model("retrieval", "QueryLog")
    assert list(OldQueryLog.objects.values_list("pk", "question", "answered")) == [
        (question.pk, "Where is the parking permit form?", False)
    ]

    # --- Forward again, through the current models -----------------------------------------------
    migrate_retrieval_to(AFTER)
    assert KnowledgeGap.objects.count() == 0
    assert QueryLog.objects.filter(pk=question.pk).exists()


def test_the_entry_embedding_is_a_vector_sized_from_settings():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a "
            "WHERE a.attrelid = 'knowledge_gaps'::regclass AND a.attname = 'embedding'"
        )
        (type_name,) = cursor.fetchone()
    assert type_name == f"vector({settings.EMBEDDING_DIMENSION})"
