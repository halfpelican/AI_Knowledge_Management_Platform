"""The row locks FR-10's writers take, in one order: document, then analysis, then tags, then links
(the focused re-audit of ``5c60564``, finding N1; apps/documents/classification.py, "Lock order").

Two transactions on separate connections, each calling the real functions. Each test makes the
interleaving that deadlocks if the order is broken, and asserts that both transactions commit:

1. **A classification run and a person confirming the department.** Reprocess holds the document row
   while classification runs (apps/ingestion/documents.py), and ``apply_classification`` takes the
   document, then the analysis row. ``confirm_classification`` used to take the analysis row and
   then write the document row: the opposite order. The auditor's probe got
   ``OperationalError: deadlock detected`` from the run.
2. **A person confirming a proposal and an Administrator deleting the document.**
   ``confirm_proposed_tag`` takes the analysis row, then the tag, then the document's existing link.
   ``delete_document`` used to take the document, then the links, and only then the analysis row,
   through the cascade: links before analysis, the opposite order again.

The order is forced, never timed. The first transaction takes its first lock and says so with an
event. The second runs until PostgreSQL shows it waiting for a lock (``pg_locks``, read from the main
thread's own connection). Only then is the first allowed to go on. Every transaction has a
``lock_timeout`` so that a regression fails the test rather than hanging the suite.
"""

import threading
import time

import pytest
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.utils import timezone

from apps.core.constants import (
    AI_APPLIED,
    ASSIGNMENT_CONFIRMED,
    EMPLOYEE_ROLE_NAME,
    PROJECT_DIMENSION,
    SOURCE_TYPES,
)
from apps.documents.classification import (
    apply_classification,
    confirm_classification,
    confirm_proposed_tag,
)
from apps.documents.deletion import delete_document
from apps.documents.models import ContentTag, Document, DocumentAnalysis, Tag

from .classification_builders import classification, scheme

# Real transactions on two connections, so ``transaction=True``. A transactional test empties every
# table when it ends, the roles the data migrations seeded included. ``serialized_rollback`` loads
# that seeded data again at the start of each one, so the second test here can still create a user.
# pytest-django runs the transactional tests after the other database tests. Only tests that use no
# database follow them, so no test that needs the seeded data meets the emptied database. These are
# the suite's only transactional tests. ANY transactional test added later must also use
# ``serialized_rollback=True``. Without it, it meets an empty database (no roles), and its own
# teardown recreates the content types that a serialized test after it then fails to load (the
# re-audit of 7377d38, observation N4).
pytestmark = pytest.mark.django_db(transaction=True, serialized_rollback=True)

DOCUMENT_SOURCE_TYPE = SOURCE_TYPES[0]
GUARD = "SET LOCAL lock_timeout = '10s'"  # a regression fails the test instead of hanging the suite
WAIT_SECONDS = 10


def make_document(title):
    user = get_user_model().objects.create_user(
        f"{title.lower().replace(' ', '.')}@example.com", "Lock-order-pass-1!", name=title
    )
    return Document.objects.create(
        title=title, file_type="txt", uploaded_by=user, visible_to_roles=[EMPLOYEE_ROLE_NAME]
    )


def backend_pid():
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_backend_pid()")
        return cursor.fetchone()[0]


def guarded():
    with connection.cursor() as cursor:
        cursor.execute(GUARD)


def wait_until_waiting_for_a_lock(pid):
    """True once the backend ``pid`` is waiting for a lock, False after WAIT_SECONDS. ``pg_locks`` is
    read live on each call (unlike ``pg_stat_activity``, it keeps no per-transaction snapshot), from
    the main thread's connection, outside both transactions."""
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        with connection.cursor() as cursor:
            cursor.execute("SELECT EXISTS (SELECT 1 FROM pg_locks WHERE pid = %s AND NOT granted)", [pid])
            if cursor.fetchone()[0]:
                return True
        threading.Event().wait(0.01)  # the next look, not an ordering
    return False


def run_two(first, second):
    """Run ``first(go_on)`` and ``second()`` in two threads, each on its own connection.

    ``first`` takes its first lock, sets ``holding`` and waits for ``go_on``. ``second`` starts once
    ``first`` holds that lock, and ``go_on`` is set only once ``second`` is seen waiting for a lock.
    Returns ``(outcome by name, whether second was seen waiting)``.
    """
    holding, go_on, ready = threading.Event(), threading.Event(), threading.Event()
    pids, outcome = {}, {}

    def thread(name, body):
        try:
            pids[name] = backend_pid()
            if name == "second":
                ready.set()
            body()
            outcome[name] = "committed"
        except Exception as exc:  # recorded, so the assertion names it
            outcome[name] = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
        finally:
            connection.close()

    threads = [
        threading.Thread(target=thread, args=("first", lambda: first(holding, go_on))),
        threading.Thread(target=thread, args=("second", lambda: (holding.wait(WAIT_SECONDS), second()))),
    ]
    for each in threads:
        each.start()
    seen_waiting = (
        holding.wait(WAIT_SECONDS) and ready.wait(WAIT_SECONDS)
        and wait_until_waiting_for_a_lock(pids["second"])
    )
    go_on.set()  # whatever was seen, so that no thread is left waiting
    for each in threads:
        each.join(3 * WAIT_SECONDS)
    return outcome, seen_waiting


def test_a_run_holding_the_document_and_a_person_confirming_the_department_both_commit():
    document = make_document("Lock order")
    DocumentAnalysis.objects.create(document=document, classified_at=timezone.now(), machine_doc_type="Policy")

    def the_run(holding, go_on):
        with transaction.atomic():
            guarded()
            Document.objects.select_for_update().get(pk=document.pk)  # as reprocess holds it
            holding.set()
            go_on.wait(WAIT_SECONDS)
            apply_classification(
                Document.objects.get(pk=document.pk),
                classification(department="Finance"), scheme=scheme(departments=["Finance"]),
            )

    def the_person():
        with transaction.atomic():
            guarded()
            confirm_classification(Document.objects.get(pk=document.pk), department="Operations")

    outcome, seen_waiting = run_two(the_run, the_person)

    assert outcome == {"first": "committed", "second": "committed"}, outcome
    assert seen_waiting  # the person did wait on the run: the interleaving was the one intended
    # The person's decision came second and stands.
    document.refresh_from_db()
    analysis = DocumentAnalysis.objects.get(document=document)
    assert (document.department, analysis.department_outcome, analysis.user_edited) == (
        "Operations", ASSIGNMENT_CONFIRMED, True,
    )


def test_a_person_confirming_a_proposal_and_a_deletion_of_the_document_both_commit():
    document = make_document("Harbour works plan")
    tag = Tag.objects.create(tag_name="harbour upgrade", dimension=PROJECT_DIMENSION)
    ContentTag.objects.create(  # a held AI link, which the confirmation puts on the document
        tag=tag, source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk,
        applied_by=AI_APPLIED, confirmed=False, provisional=True,
    )
    DocumentAnalysis.objects.create(
        document=document, classified_at=timezone.now(),
        proposed_tags=[{"dimension": PROJECT_DIMENSION, "value": "harbour upgrade", "confidence": 0.5}],
    )

    def the_person(holding, go_on):
        with transaction.atomic():
            guarded()
            # confirm_proposed_tag's first lock, taken first so the interleaving is the one that
            # deadlocks if the deletion takes the links before the analysis row.
            DocumentAnalysis.objects.select_for_update().get(document_id=document.pk)
            holding.set()
            go_on.wait(WAIT_SECONDS)
            confirm_proposed_tag(Document.objects.get(pk=document.pk), PROJECT_DIMENSION, "harbour upgrade")

    def the_deletion():
        with transaction.atomic():
            guarded()
            delete_document(Document.objects.get(pk=document.pk))

    outcome, seen_waiting = run_two(the_person, the_deletion)

    assert outcome == {"first": "committed", "second": "committed"}, outcome
    assert seen_waiting  # the deletion did wait on the person
    # The deletion came second: the document, its analysis and its links are gone; the Tag stays.
    assert not Document.objects.filter(pk=document.pk).exists()
    assert not DocumentAnalysis.objects.filter(document_id=document.pk).exists()
    assert not ContentTag.objects.filter(source_id=document.pk).exists()
    assert Tag.objects.filter(pk=tag.pk).exists()
