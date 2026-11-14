"""documents 0012: ``DocumentAnalysis.proposed_topics`` becomes ``proposed_tags``, and each entry names
its dimension (D-128, 12 November 2026).

- **Forward** stamps ``"dimension": "Topic"`` on every existing entry, since until D-128 only a Topic
  could be proposed. An entry that is not an object is left as it is.
- **Reverse** strips ``dimension`` from each Topic entry and moves each Project or Process entry into
  ``discarded_suggestions`` as ``{"dimension", "value", "confidence"}``, which is what the rule
  before D-128 recorded for such a value, so the old schema loses nothing it could hold.
- **The column keeps its name,** ``proposed_topics``, in both directions: CLAUDE.md section 7 requires
  additive migrations, so 0012 renames the field over an explicit ``db_column`` and emits no ALTER.

Built as the 0010 and 0011 tests are: the executor itself is driven, for ``documents`` only, from 0011
to 0012 and back, in the ordinary per-test transaction, and each test ends at the leaf. Rows are
written and read through the historical models of the state the database is at.
"""

import io

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.core.constants import EMPLOYEE_ROLE_NAME, PROCESS_DIMENSION, PROJECT_DIMENSION, TOPIC_DIMENSION
from apps.documents.models import Document, DocumentAnalysis

pytestmark = pytest.mark.django_db

BEFORE = ("documents", "0011_grown_marks_withheld_tags")
AFTER = ("documents", "0012_proposed_tags")
TABLE = "document_analysis"


def migrate_documents_to(node):
    """Move ``documents`` to ``node`` and leave every other app at its leaf; returns the historical
    app registry at that state. A fresh executor each time, because one that has migrated keeps a
    stale view of what is applied."""
    executor = MigrationExecutor(connection)
    targets = [
        leaf for leaf in executor.loader.graph.leaf_nodes() if leaf[0] != "documents"
    ] + [node]
    executor.migrate(targets)
    executor.loader.build_graph()
    return executor.loader.project_state(targets).apps


def documents_leaf():
    [leaf] = [
        key for key in MigrationExecutor(connection).loader.graph.leaf_nodes()
        if key[0] == "documents"
    ]
    return leaf


def columns_of(table):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s",
            [table],
        )
        return {row[0] for row in cursor.fetchall()}


def make_document(user, title):
    """Through the current model: 0012 changes no table, so the schema is the same at 0011."""
    return Document.objects.create(
        title=title, file_type="txt", uploaded_by=user, visible_to_roles=[EMPLOYEE_ROLE_NAME]
    )


@pytest.fixture(autouse=True)
def immediate_constraints():
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")  # as the 0008 to 0011 tests do


def test_0012_is_on_the_path_to_the_leaf_of_documents():
    graph = MigrationExecutor(connection).loader.graph
    assert AFTER in graph.forwards_plan(documents_leaf())


def test_0012_forward_stamps_the_topic_dimension_on_every_existing_entry(employee):
    old_apps = migrate_documents_to(BEFORE)
    OldAnalysis = old_apps.get_model("documents", "DocumentAnalysis")
    proposed = make_document(employee, "Budget memo")
    empty = make_document(employee, "Site notice")
    discarded = [{"dimension": PROJECT_DIMENSION, "value": "harbour upgrade", "confidence": 0.9}]
    OldAnalysis.objects.create(
        document_id=proposed.pk, classified_at=timezone.now(), discarded_suggestions=discarded,
        proposed_topics=[
            {"value": "budget planning", "confidence": 0.8},
            {"value": "risk appetite", "confidence": 0.7},
            "not an object",
        ],
    )
    OldAnalysis.objects.create(document_id=empty.pk, classified_at=timezone.now(), proposed_topics=[])

    new_apps = migrate_documents_to(AFTER)

    NewAnalysis = new_apps.get_model("documents", "DocumentAnalysis")
    row = NewAnalysis.objects.get(document_id=proposed.pk)
    assert row.proposed_tags == [
        {"dimension": TOPIC_DIMENSION, "value": "budget planning", "confidence": 0.8},
        {"dimension": TOPIC_DIMENSION, "value": "risk appetite", "confidence": 0.7},
        "not an object",
    ]
    assert row.discarded_suggestions == discarded
    assert NewAnalysis.objects.get(document_id=empty.pk).proposed_tags == []

    migrate_documents_to(documents_leaf())  # the leaf, as the rest of the suite expects


def test_0012_reverse_strips_the_dimension_and_moves_project_and_process_entries_to_discarded(employee):
    new_apps = migrate_documents_to(AFTER)
    document = make_document(employee, "Harbour works plan")
    already = {"dimension": PROJECT_DIMENSION, "value": "x" * 300, "confidence": 0.99}
    topic = {"dimension": TOPIC_DIMENSION, "value": "budget planning", "confidence": 0.8}
    project = {"dimension": PROJECT_DIMENSION, "value": "harbour upgrade", "confidence": 0.6}
    process = {"dimension": PROCESS_DIMENSION, "value": "vendor onboarding", "confidence": 0.5}
    new_apps.get_model("documents", "DocumentAnalysis").objects.create(
        document_id=document.pk, classified_at=timezone.now(), discarded_suggestions=[already],
        proposed_tags=[topic, project, process, {"value": "no dimension", "confidence": 0.4}, "not an object"],
    )

    old_apps = migrate_documents_to(BEFORE)

    row = old_apps.get_model("documents", "DocumentAnalysis").objects.get(document_id=document.pk)
    assert row.proposed_topics == [
        {"value": "budget planning", "confidence": 0.8},
        {"value": "no dimension", "confidence": 0.4},  # read as a Topic, as before D-128
        "not an object",
    ]
    assert row.discarded_suggestions == [already, project, process]

    # Forward again, to the leaf: the Topics are stamped once more, and the Project and Process
    # values stay discarded, which is where the old schema put them.
    migrate_documents_to(documents_leaf())
    row = DocumentAnalysis.objects.get(document=document)
    assert row.proposed_tags == [
        topic, {"dimension": TOPIC_DIMENSION, "value": "no dimension", "confidence": 0.4}, "not an object",
    ]
    assert row.discarded_suggestions == [already, project, process]


def test_the_column_keeps_its_name_both_ways_and_0012_emits_no_alter():
    migrate_documents_to(BEFORE)
    assert {"proposed_topics", "proposed_tags"} & columns_of(TABLE) == {"proposed_topics"}

    migrate_documents_to(AFTER)
    assert {"proposed_topics", "proposed_tags"} & columns_of(TABLE) == {"proposed_topics"}

    for backwards in (False, True):
        output = io.StringIO()
        call_command("sqlmigrate", "documents", AFTER[1], backwards=backwards, stdout=output)
        statements = [
            line.strip() for line in output.getvalue().splitlines()
            if line.strip() and not line.strip().startswith("--")
        ]
        # Every operation is a no-op in SQL: the transaction around them is all that is printed.
        assert statements == ["BEGIN;", "COMMIT;"], (backwards, statements)

    migrate_documents_to(documents_leaf())
    assert {"proposed_topics", "proposed_tags"} & columns_of(TABLE) == {"proposed_topics"}
