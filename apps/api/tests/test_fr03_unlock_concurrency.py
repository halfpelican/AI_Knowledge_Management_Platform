"""FR-03's release and FR-05's role change on the same account at the same time (D-130).

``UserUnlockView.post`` locks the Administrators' rows, ordered by primary key, before it locks the
target, as ``UserRoleView.patch`` does (D-26). Without that, the two could deadlock:

- the role change holds every Administrator's row FOR UPDATE and waits for the target's;
- the release holds the target's row and, when it commits, waits for a key-share lock on the
  requester's row. The release row's ``released_by`` foreign key takes it, and Django creates
  foreign keys DEFERRABLE INITIALLY DEFERRED, so the check runs at commit.

Postgres then aborts one of the two after ``deadlock_timeout``, and that request fails with a 500.
With the Administrators' rows locked first, the release already holds the requester's row, and
whichever of the two takes the Administrators' rows first finishes first.

**Deterministic, not timed.** The release runs in a thread and is held just before it writes its
LoginAttempts row, by patching ``LoginAttempt`` in the view module: by then it holds every lock it
takes before committing. The role change then starts in a second thread, and the test waits until
Postgres reports that request waiting on a lock (``pg_stat_activity``), or until it has finished,
before letting the release go on. The interleaving that deadlocks without the ordering is forced
rather than hoped for: the role change is already waiting when the release reaches its commit.
Every wait has a timeout, so a regression fails rather than hangs.

**``transaction=True``**, as in test_login_concurrency.py: each thread has its own connection,
which cannot see a test transaction's uncommitted rows, so these tests commit for real.
``serialized_rollback`` restores the rows the migrations seeded before the next test.
"""

from __future__ import annotations

import threading
import time

import pytest
from django.contrib.auth import get_user_model
from django.db import connection, connections
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

import apps.api.views as views
from apps.accounts.models import LoginAttempt, Role
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    EMPLOYEE_ROLE_NAME,
    LOCKOUT_DURATION,
    LOCKOUT_THRESHOLD,
    LOGIN_ATTEMPT_RELEASE,
)
from conftest import PASSWORD

User = get_user_model()

pytestmark = pytest.mark.django_db(transaction=True, serialized_rollback=True)

# The longest any wait here lasts before the test fails instead. Only a regression reaches it.
PATIENCE = 30


class RequestThread(threading.Thread):
    """One request from a signed-in client, in a thread of its own and so on its own database
    connection, closed when the request ends. What the request raised is kept for ``finish``."""

    def __init__(self, name, user, send):
        super().__init__(name=name, daemon=True)
        self.client = APIClient()
        self.client.force_login(user)
        self.send = send
        self.response = None
        self.error: BaseException | None = None

    def run(self):
        try:
            self.response = self.send(self.client)
        except BaseException as error:  # re-raised in the test's own thread by finish()
            self.error = error
        finally:
            connections.close_all()


def finish(*threads: RequestThread) -> None:
    started = [thread for thread in threads if thread.ident is not None]
    for thread in started:
        thread.join(PATIENCE)
    stuck = [thread.name for thread in started if thread.is_alive()]
    assert not stuck, f"still running after {PATIENCE}s: {stuck}"
    for thread in started:
        if thread.error is not None:
            raise thread.error


def another_request_is_waiting_on_a_lock() -> bool:
    """Whether a connection to this test database, other than this one, is waiting on a lock.
    The test's own connection is in autocommit, so each read is a fresh snapshot."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
            "AND pid <> pg_backend_pid() AND wait_event_type = 'Lock'"
        )
        return cursor.fetchone()[0] > 0


def wait_until_waiting_on_a_lock_or_finished(thread: RequestThread) -> bool:
    """True once another connection waits on a lock; False if ``thread`` finished first."""
    deadline = time.monotonic() + PATIENCE
    while time.monotonic() < deadline:
        if another_request_is_waiting_on_a_lock():
            return True
        thread.join(0.01)  # paces the poll, and notices the thread finishing
        if not thread.is_alive():
            return another_request_is_waiting_on_a_lock()
    raise AssertionError(f"{thread.name} neither waited on a lock nor finished within {PATIENCE}s")


def test_a_release_and_a_role_change_on_the_same_account_both_complete(monkeypatch, administrator, employee):
    second = User.objects.create_user(
        "second.admin@example.com", PASSWORD, name="Sam Second",
        role=Role.objects.get(role_name=ADMINISTRATOR_ROLE_NAME),
    )
    employee.failed_attempts = LOCKOUT_THRESHOLD
    employee.locked_until = timezone.now() + LOCKOUT_DURATION
    employee.save(update_fields=["failed_attempts", "locked_until"])
    employee_role_id = str(Role.objects.get(role_name=EMPLOYEE_ROLE_NAME).pk)

    release_holds_its_locks = threading.Event()
    role_change_has_waited = threading.Event()

    class LoginAttemptHeldBeforeTheRow:
        """Stands in for the model in the view module: holds the release just before it writes
        its row, then writes it through the real model."""

        class objects:
            @staticmethod
            def create(**fields):
                release_holds_its_locks.set()
                if not role_change_has_waited.wait(PATIENCE):
                    raise AssertionError(f"the role change was not started within {PATIENCE}s")
                return LoginAttempt.objects.create(**fields)

    monkeypatch.setattr(views, "LoginAttempt", LoginAttemptHeldBeforeTheRow)
    release = RequestThread(
        "release", administrator,
        lambda client: client.post(reverse("user-unlock", kwargs={"pk": employee.pk}), format="json"),
    )
    role_change = RequestThread(
        "role-change", second,
        lambda client: client.patch(
            reverse("user-role", kwargs={"pk": employee.pk}), {"role_id": employee_role_id}, format="json"
        ),
    )

    waited = None
    release.start()
    try:
        assert release_holds_its_locks.wait(PATIENCE), "the release never reached its LoginAttempts row"
        role_change.start()
        waited = wait_until_waiting_on_a_lock_or_finished(role_change)
    finally:
        role_change_has_waited.set()  # never leave the release held, whatever happened above
        finish(release, role_change)

    # The overlap was real: the role change had to wait for the release's locks.
    assert waited is True
    assert (release.response.status_code, role_change.response.status_code) == (200, 200)
    stored = User.objects.select_related("role").get(pk=employee.pk)
    assert (stored.failed_attempts, stored.locked_until, stored.role.role_name) == (0, None, EMPLOYEE_ROLE_NAME)
    release_row = LoginAttempt.objects.get()
    assert (release_row.event, release_row.user_id, release_row.released_by_id) == (
        LOGIN_ATTEMPT_RELEASE, employee.pk, administrator.pk,
    )
