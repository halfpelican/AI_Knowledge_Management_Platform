"""documents 0015: Departments, seeded from the departments documents carry (D-129, the lead's decision
of 13 November 2026).

- **Forward** creates the table and seeds one row per distinct non-blank ``Documents.department``,
  each name normalised as ``Department.save()`` normalises it (stripped, spacing collapsed, the case
  kept), deduplicated ignoring case, keeping the spelling most documents use (a tie: the first by code
  point). Every row is active.
- **The hidden flag:** a row is grown when no document carrying its kept spelling exactly is readable
  by EVERY role, documents 0011's reasoning, with an Administrator reading Employee material (D-66).
- **Backwards** drops the table; forward again seeds it again from the documents.

Built as the 0011 and 0013 tests are: the executor itself is driven, for ``documents`` only, from 0014
to 0015 and back, in the ordinary per-test transaction, and each test ends at the leaf. 0015 changes
nothing on ``documents``, so the documents are written through the current model while ``documents``
stands at 0014, and the seeded rows are read through the historical model of 0015's state.
"""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.core.constants import ADMINISTRATOR_ROLE_NAME, EMPLOYEE_ROLE_NAME
from apps.documents.models import Department, Document

pytestmark = pytest.mark.django_db

BEFORE = ("documents", "0014_merge_fr16_and_d128")
AFTER = ("documents", "0015_departments")
TABLE = "departments"
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]


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


def public_tables():
    with connection.cursor() as cursor:
        cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        return {row[0] for row in cursor.fetchall()}


def seeded(apps):
    """``{name: (active, grown)}`` of every row, through the historical model."""
    model = apps.get_model("documents", "Department")
    return {name: (active, grown) for name, active, grown in model.objects.values_list("name", "active", "grown")}


@pytest.fixture(autouse=True)
def immediate_constraints():
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")  # as the 0008 to 0013 tests do


@pytest.fixture
def make(employee):
    def document(department, roles=None, title=None):
        return Document.objects.create(
            title=title or f"Document {Document.objects.count() + 1}", file_type="txt",
            uploaded_by=employee, department=department,
            visible_to_roles=BOTH_ROLES if roles is None else roles,
        )

    return document


def test_0015_is_the_leaf_of_documents():
    assert documents_leaf() == AFTER


def test_0015_seeds_one_department_per_name_ignoring_case_and_hides_one_no_role_but_some_can_read(make):
    migrate_documents_to(BEFORE)
    assert TABLE not in public_tables()
    administrators_only = [ADMINISTRATOR_ROLE_NAME]
    # Most documents use "Human Resources": that spelling is kept, and every role reads it.
    make("Human Resources")
    make("Human Resources", roles=[EMPLOYEE_ROLE_NAME])  # an Administrator reads it too (D-66)
    make("human resources")
    # Normalised as save() normalises: stripped and spacing collapsed, the case kept.
    make("  Finance  ")
    make("Finance")
    make("Board  Office", roles=administrators_only)
    # The majority spelling is on Administrator-only documents alone, so it is hidden, although
    # another spelling of the name is on a document every role reads.
    make("Legal", roles=administrators_only)
    make("Legal", roles=administrators_only)
    make("legal")
    # A tie: the first by code point ("OPS" < "Ops").
    make("Ops")
    make("OPS")
    # On a document nobody reads: no role reads it, so it is hidden.
    make("Archive", roles=[])
    # On an Employee-only document: every role reads it.
    make("Payroll", roles=[EMPLOYEE_ROLE_NAME])
    # Blank, after normalising: nothing.
    make("")
    make("   ")

    new_apps = migrate_documents_to(AFTER)

    assert seeded(new_apps) == {
        "Human Resources": (True, False),
        "Finance": (True, False),
        "Board Office": (True, True),
        "Legal": (True, True),
        "OPS": (True, False),
        "Archive": (True, True),
        "Payroll": (True, False),
    }
    # The documents are untouched: the list is the scheme, not the documents' field (D-72).
    assert Document.objects.filter(department="  Finance  ").count() == 1
    assert Document.objects.filter(department="legal").count() == 1

    migrate_documents_to(documents_leaf())  # the leaf, as the rest of the suite expects


def test_0015_seeds_nothing_where_no_document_has_a_department(make):
    migrate_documents_to(BEFORE)
    make("")

    new_apps = migrate_documents_to(AFTER)

    assert seeded(new_apps) == {}
    migrate_documents_to(documents_leaf())


def test_0015_backwards_drops_the_table_and_forward_seeds_it_again(make):
    new_apps = migrate_documents_to(AFTER)
    new_apps.get_model("documents", "Department").objects.create(name="Added By Hand", grown=False)
    make("Finance")

    migrate_documents_to(BEFORE)

    assert TABLE not in public_tables()
    assert Document.objects.filter(department="Finance").exists()  # the documents keep theirs

    migrate_documents_to(documents_leaf())
    # Forward again: the table is back, seeded from the documents alone.
    assert sorted(Department.objects.values_list("name", "active", "grown")) == [("Finance", True, False)]
