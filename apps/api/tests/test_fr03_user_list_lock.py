"""FR-03's ``lock`` on ``GET /api/users`` (docs/api-contract.md, "NIT3004 - FR-03"; D-130).

FR-03: "An Administrator viewing a locked account can release the lock immediately." The list a
holder of ``release_account_locks`` receives adds ``lock`` to each user:

- ``null`` unless ``locked_until`` is after now, so an expired lock reads as unlocked;
- otherwise ``{"locked_until", "locked_at", "source_ip"}``, the last two taken from the lockout row
  whose ``locked_until`` equals the account's, which is the row that set this lock and not merely
  the latest one (security finding L5), and both null when there is no such row.

A requester without the code gets the plain user object, and the list's gate is still
``manage_roles``. The lockout rows are prefetched, so the list's queries do not grow with the number
of locked accounts. The plain user object on every other route is held to its five keys by
test_login.py, test_register.py and test_roles.py; GET /api/users's own Employee 403 by
test_roles.py and test_rbac.py.
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import LoginAttempt, Permission, RolePermission
from apps.core.constants import (
    LOCKOUT_DURATION,
    LOCKOUT_THRESHOLD,
    LOGIN_ATTEMPT_LOCKOUT,
    LOGIN_ATTEMPT_RELEASE,
    MANAGE_ROLES_PERMISSION,
    RELEASE_ACCOUNT_LOCKS_PERMISSION,
)
from conftest import PASSWORD

User = get_user_model()

pytestmark = pytest.mark.django_db

USERS = reverse("user-list")
LOGIN = reverse("auth-login")
USER_OBJECT_KEYS = {"id", "name", "email", "role", "created_at"}
LOCK_KEYS = {"locked_until", "locked_at", "source_ip"}


def set_lock(user, locked_until, failed_attempts=LOCKOUT_THRESHOLD):
    User.objects.filter(pk=user.pk).update(failed_attempts=failed_attempts, locked_until=locked_until)


def lockout_row(user, *, locked_until, attempted_at, source_ip):
    return LoginAttempt.objects.create(
        event=LOGIN_ATTEMPT_LOCKOUT,
        attempted_email=user.email,
        source_ip=source_ip,
        success=False,
        attempted_at=attempted_at,
        user=user,
        locked_until=locked_until,
    )


def listed(client):
    response = client.get(USERS)
    assert response.status_code == 200
    return {entry["id"]: entry for entry in response.json()}


def instant(text):
    """An ISO timestamp from the response, compared as an instant rather than as text."""
    return None if text is None else datetime.datetime.fromisoformat(text)


def new_user(email, name):
    return User.objects.create_user(email, PASSWORD, name=name)


# --- null unless the lock is live ----------------------------------------------------------------


def test_lock_is_null_for_an_unlocked_account_and_for_an_expired_lock(
    administrator_client, administrator, employee
):
    """A ``locked_until`` that has passed is not a lock, even with the lockout row that set it."""
    expired = new_user("expired@example.com", "Eli Expired")
    ended = timezone.now() - datetime.timedelta(seconds=1)
    set_lock(expired, ended)
    lockout_row(expired, locked_until=ended, attempted_at=ended - LOCKOUT_DURATION, source_ip="203.0.113.42")

    entries = listed(administrator_client)

    assert entries[str(employee.id)]["lock"] is None
    assert entries[str(expired.id)]["lock"] is None
    assert entries[str(administrator.id)]["lock"] is None


# --- a live lock, with the row that set it ----------------------------------------------------------


def test_a_live_lock_is_listed_with_when_and_from_where_it_was_set(administrator_client, administrator, employee):
    """End to end: five wrong passwords from one address lock the account and write the lockout
    row, and the list shows the lock with that row's time and address."""
    for attempt in range(LOCKOUT_THRESHOLD):
        response = APIClient().post(
            LOGIN, {"email": employee.email, "password": "Wrong-Horse-9-Battery"}, format="json",
            REMOTE_ADDR="203.0.113.42",
        )
        assert response.status_code == 401, attempt
    employee.refresh_from_db()
    row = LoginAttempt.objects.get()

    entries = listed(administrator_client)

    lock = entries[str(employee.id)]["lock"]
    assert set(lock) == LOCK_KEYS
    assert instant(lock["locked_until"]) == employee.locked_until
    assert instant(lock["locked_at"]) == row.attempted_at
    assert lock["source_ip"] == "203.0.113.42"
    assert entries[str(administrator.id)]["lock"] is None


def test_the_details_come_from_the_row_that_set_the_current_lock_not_the_latest(
    administrator_client, employee
):
    """Security finding L5. Another lockout row on the account, with a different ``locked_until``
    still in the future and a later ``attempted_at``, is written first, so neither "the latest row"
    nor "the first row" names the lock the account holds. Only matching on ``locked_until`` does."""
    now = timezone.now()
    current = now + datetime.timedelta(minutes=10)
    lockout_row(
        employee, locked_until=now + datetime.timedelta(minutes=14),
        attempted_at=now - datetime.timedelta(minutes=1), source_ip="198.51.100.66",
    )
    matching = lockout_row(
        employee, locked_until=current, attempted_at=now - datetime.timedelta(minutes=5),
        source_ip="203.0.113.42",
    )
    set_lock(employee, current)

    lock = listed(administrator_client)[str(employee.id)]["lock"]

    assert instant(lock["locked_until"]) == current
    assert (instant(lock["locked_at"]), lock["source_ip"]) == (matching.attempted_at, "203.0.113.42")


def test_a_live_lock_without_its_lockout_row_has_null_details(administrator_client, employee):
    """A lock older than the table has no row. Nor does a row on another account count, even one
    naming the very same ``locked_until``, or a release row on this one."""
    current = timezone.now() + datetime.timedelta(minutes=10)
    set_lock(employee, current)
    other = new_user("other@example.com", "Oli Other")
    set_lock(other, current)
    other_row = lockout_row(
        other, locked_until=current, attempted_at=current - LOCKOUT_DURATION, source_ip="198.51.100.66"
    )
    LoginAttempt.objects.create(
        event=LOGIN_ATTEMPT_RELEASE, attempted_email=employee.email, source_ip="198.51.100.77",
        success=None, attempted_at=timezone.now(), user=employee, released_by=other,
        locked_until=current,
    )

    entries = listed(administrator_client)

    lock = entries[str(employee.id)]["lock"]
    assert set(lock) == LOCK_KEYS
    assert instant(lock["locked_until"]) == current
    assert (lock["locked_at"], lock["source_ip"]) == (None, None)
    # The other account's lock has its own row's details.
    other_lock = entries[str(other.id)]["lock"]
    assert (instant(other_lock["locked_at"]), other_lock["source_ip"]) == (other_row.attempted_at, "198.51.100.66")


# --- only a holder of release_account_locks sees it -----------------------------------------------


def test_an_administrator_role_without_the_code_gets_the_plain_list(
    administrator_client, administrator_role, employee
):
    """The list is still served, because its gate is manage_roles, but without ``lock``."""
    RolePermission.objects.filter(
        role=administrator_role, permission__permission_name=RELEASE_ACCOUNT_LOCKS_PERMISSION
    ).delete()
    current = timezone.now() + datetime.timedelta(minutes=10)
    set_lock(employee, current)
    lockout_row(employee, locked_until=current, attempted_at=current - LOCKOUT_DURATION, source_ip="203.0.113.42")

    response = administrator_client.get(USERS)

    assert response.status_code == 200
    body = response.json()
    assert {entry["id"] for entry in body} >= {str(employee.id)}
    assert all(set(entry) == USER_OBJECT_KEYS for entry in body)


def test_an_employee_granted_manage_roles_alone_gets_the_plain_list(employee_client, employee_role, administrator):
    """The same from an Employee session: a role holding manage_roles and not
    release_account_locks reads the list, and no account's lock state."""
    RolePermission.objects.create(
        role=employee_role, permission=Permission.objects.get(permission_name=MANAGE_ROLES_PERMISSION)
    )
    set_lock(administrator, timezone.now() + datetime.timedelta(minutes=10))

    response = employee_client.get(USERS)

    assert response.status_code == 200
    assert all(set(entry) == USER_OBJECT_KEYS for entry in response.json())


# --- one query for every lock ------------------------------------------------------------------------


def test_the_lists_queries_do_not_grow_with_the_number_of_locked_accounts(administrator_client):
    """The lockout rows come in one prefetch for the whole list, never one query per user."""

    def lock_a_new_account(number):
        user = new_user(f"locked{number}@example.com", f"Locked {number}")
        current = timezone.now() + datetime.timedelta(minutes=10)
        set_lock(user, current)
        lockout_row(user, locked_until=current, attempted_at=current - LOCKOUT_DURATION, source_ip=f"203.0.113.{number}")

    lock_a_new_account(1)
    listed(administrator_client)  # once first, so nothing a first request does is counted
    with CaptureQueriesContext(connection) as one_locked:
        listed(administrator_client)

    for number in range(2, 6):
        lock_a_new_account(number)
    with CaptureQueriesContext(connection) as five_locked:
        entries = listed(administrator_client)

    # Not vacuous: all five locks were listed with their rows' details.
    assert sorted(entry["lock"]["source_ip"] for entry in entries.values() if entry["lock"]) == [
        f"203.0.113.{number}" for number in range(1, 6)
    ]
    assert len(five_locked) == len(one_locked), [query["sql"] for query in five_locked.captured_queries]
