"""FR-03's administrator release: ``POST /api/users/{id}/unlock`` (docs/api-contract.md, "NIT3004 -
FR-03"; D-130).

FR-03 Responses: "200 OK on release; 403 Forbidden where the requester does not hold the
Administrator role or is the account holder; 404 Not Found for an unknown account; 409 Conflict
where the account is not currently locked." Its administrator-release clause: "releasing a lock
clears the expiry and resets the failed-attempt count, returning the account to the state it would
reach when the window expires naturally. The Administrator does not see, set or reset the user's
password; releasing a lock restores the ability to attempt authentication and nothing more. Every
release is recorded with the Administrator who performed it, the account affected and the time."

The route is exercised anonymously (401), from an Employee session (403, before any lookup, so a
real id and an invented one answer alike) and from an Administrator session (404, 403 for their
own account, 409 and 200), as CLAUDE.md section 8 requires. Every refusal is checked to change
nothing: every account's row is read back, and no LoginAttempts row may exist afterwards.
"""

import datetime
import uuid

import pytest
from django.contrib.auth import SESSION_KEY, get_user_model
from django.contrib.sessions.models import Session
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import LoginAttempt
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    EMPLOYEE_ROLE_NAME,
    LOCKOUT_DURATION,
    LOCKOUT_NOTICE_CEILING,
    LOCKOUT_THRESHOLD,
    LOGIN_ATTEMPT_LOCKOUT,
    LOGIN_ATTEMPT_RELEASE,
)
from conftest import PASSWORD

User = get_user_model()

pytestmark = pytest.mark.django_db

LOGIN = reverse("auth-login")
ME = reverse("auth-me")
WRONG_PASSWORD = "Wrong-Horse-9-Battery"
USER_OBJECT_KEYS = {"id", "name", "email", "role", "created_at"}
SECRET_COLUMNS = {"password", "password_hash", "failed_attempts", "locked_until", "last_login"}

# The five bodies the route refuses with, quoted from the contract (docs/api-contract.md, "NIT3004 -
# FR-03"). The first three are DRF's and Django's own; the last two are FR-03's.
NOT_SIGNED_IN = {"detail": "Authentication credentials were not provided."}
NOT_PERMITTED = {"detail": "Your role does not hold the 'release_account_locks' permission."}
UNKNOWN_USER = {"detail": "No User matches the given query."}
OWN_ACCOUNT = {"detail": "You cannot release a lock on your own account."}
NOT_LOCKED = {"detail": "This account is not locked."}


def unlock_url(user_or_id):
    return reverse("user-unlock", kwargs={"pk": getattr(user_or_id, "pk", user_or_id)})


def unlock(client, user_or_id, **extra):
    """The release, as the front end sends it: a POST with no body (the route reads none)."""
    return client.post(unlock_url(user_or_id), format="json", **extra)


def login(client, email, password):
    return client.post(LOGIN, {"email": email, "password": password}, format="json")


def logged_in(user):
    client = APIClient()
    client.force_login(user)
    return client


def lock(user, remaining=LOCKOUT_DURATION, failed_attempts=LOCKOUT_THRESHOLD):
    """Lock ``user`` directly, as login's threshold failure would, with ``remaining`` left."""
    user.failed_attempts = failed_attempts
    user.locked_until = timezone.now() + remaining
    user.save(update_fields=["failed_attempts", "locked_until"])
    return user


def row_of(user):
    """Everything on the account a release could touch, read back from the database."""
    stored = User.objects.get(pk=user.pk)
    return {
        "failed_attempts": stored.failed_attempts,
        "locked_until": stored.locked_until,
        "password_hash": stored.password,
        "role": stored.role_id,
        "last_login": stored.last_login,
    }


def every_row():
    return {user.pk: row_of(user) for user in User.objects.all()}


def sessions_signed_in_as(user) -> int:
    return sum(
        1 for session in Session.objects.all() if session.get_decoded().get(SESSION_KEY) == str(user.pk)
    )


def assert_refused_and_nothing_changed(response, status, body, before):
    assert (response.status_code, response.json()) == (status, body)
    assert every_row() == before
    assert not LoginAttempt.objects.exists(), "a refused release wrote a LoginAttempts row"


@pytest.fixture
def colleague(db):
    return User.objects.create_user("colleague@example.com", PASSWORD, name="Cal Colleague")


@pytest.fixture
def second_administrator(administrator_role):
    return User.objects.create_user(
        "second.admin@example.com", PASSWORD, name="Sam Second", role=administrator_role
    )


# --- 401: no session -----------------------------------------------------------------------------


def test_unlock_is_401_anonymously_and_changes_nothing(api_client, employee):
    lock(employee)
    before = every_row()

    response = unlock(api_client, employee)

    assert_refused_and_nothing_changed(response, 401, NOT_SIGNED_IN, before)


# --- 403: a role without release_account_locks, before any lookup ---------------------------------


@pytest.mark.parametrize("target", ["a locked colleague", "their own locked account", "an unknown id"])
def test_unlock_is_403_for_an_employee_whatever_the_id(
    employee_client, employee, colleague, target
):
    """FR-03: "Only a user holding the Administrator role may release a lock." The permission is
    checked before the account is looked up, so an Employee gets the same 403, never a 404, for a
    real account and an invented id, and cannot use the route to learn which ids exist."""
    lock(colleague)
    lock(employee)
    target_id = {
        "a locked colleague": colleague.pk,
        "their own locked account": employee.pk,
        "an unknown id": uuid.uuid4(),
    }[target]
    before = every_row()

    response = unlock(employee_client, target_id)

    assert_refused_and_nothing_changed(response, 403, NOT_PERMITTED, before)


# --- 404: an unknown account -----------------------------------------------------------------------


def test_an_unknown_id_is_404_for_an_administrator(administrator_client, employee):
    lock(employee)
    before = every_row()

    response = unlock(administrator_client, uuid.uuid4())

    assert_refused_and_nothing_changed(response, 404, UNKNOWN_USER, before)


# --- 403: the account holder ------------------------------------------------------------------------


@pytest.mark.parametrize("locked", [True, False], ids=["locked", "not locked"])
def test_an_administrator_cannot_release_their_own_account(administrator_client, administrator, locked):
    """FR-03: "An Administrator cannot release a lock on their own account, since an account locked
    by a brute-force attempt against it must not be releasable by whoever currently holds that
    session." The 403 is given whether or not the account is locked ("is the account holder"), so
    it is checked before the lock is: an unlocked own account is a 403, not a 409."""
    if locked:
        lock(administrator)
    before = every_row()

    response = unlock(administrator_client, administrator)

    assert_refused_and_nothing_changed(response, 403, OWN_ACCOUNT, before)
    if locked:
        # The session that asked is still signed in, and the lock it asked to release stays.
        assert User.objects.get(pk=administrator.pk).locked_until > timezone.now()


# --- 409: not currently locked -----------------------------------------------------------------------


def test_an_account_that_is_not_locked_is_409_and_its_count_is_left_alone(administrator_client, employee):
    """A count below the threshold is not a lock, so the release does not reset it either."""
    employee.failed_attempts = LOCKOUT_THRESHOLD - 2
    employee.save(update_fields=["failed_attempts"])
    before = every_row()

    response = unlock(administrator_client, employee)

    assert_refused_and_nothing_changed(response, 409, NOT_LOCKED, before)


def test_an_expired_lock_is_409_and_is_left_exactly_as_it_was(administrator_client, employee):
    """FR-03's 409 is for an account "not currently locked", and a window that has passed is not
    current. The stale ``locked_until`` and the count stay as they were (D-130): login's own reset
    on the next attempt is what clears them, as it always has (D-25)."""
    lock(employee, remaining=-datetime.timedelta(seconds=1))
    before = every_row()
    assert before[employee.pk]["locked_until"] is not None  # the stale value really is there

    response = unlock(administrator_client, employee)

    assert_refused_and_nothing_changed(response, 409, NOT_LOCKED, before)


# --- 200: another user's lock -------------------------------------------------------------------------


def test_an_administrator_releases_another_users_lock(
    administrator_client, administrator, employee, employee_client
):
    """The release clears the expiry and the count and touches nothing else: not the password, not
    the role, not last_login, and not the session the user already holds elsewhere. It writes
    exactly one LoginAttempts row naming who released which lock, from where and when."""
    # A count past the notice ceiling, as a sustained guess against the account leaves it (D-26).
    lock(employee, failed_attempts=LOCKOUT_NOTICE_CEILING + 3)
    before = row_of(employee)
    # A lock never ended a session (D-26), so the user can still be signed in somewhere else.
    assert employee_client.get(ME).status_code == 200
    sessions_before = sessions_signed_in_as(employee)
    assert sessions_before == 1

    started = timezone.now()
    response = unlock(administrator_client, employee)
    finished = timezone.now()

    assert response.status_code == 200
    body = response.json()
    # The user as GET /api/users lists it to an Administrator, with the lock now gone.
    assert set(body) == USER_OBJECT_KEYS | {"lock"}
    assert body["lock"] is None
    assert (body["id"], body["email"], body["role"]) == (str(employee.id), employee.email, EMPLOYEE_ROLE_NAME)
    assert SECRET_COLUMNS.isdisjoint(body)

    # "the state it would reach when the window expires naturally", and nothing else changed.
    assert row_of(employee) == {**before, "failed_attempts": 0, "locked_until": None}

    # The session the user already held is untouched and still signs them in.
    assert sessions_signed_in_as(employee) == sessions_before
    me = employee_client.get(ME)
    assert (me.status_code, me.json()["id"]) == (200, str(employee.id))

    release = LoginAttempt.objects.get()  # exactly one row, and it is the release
    assert {
        "event": release.event,
        "attempted_email": release.attempted_email,
        "source_ip": release.source_ip,
        "success": release.success,
        "user": release.user_id,
        "released_by": release.released_by_id,
        "locked_until": release.locked_until,
    } == {
        "event": LOGIN_ATTEMPT_RELEASE,
        "attempted_email": employee.email,
        "source_ip": "127.0.0.1",
        "success": None,  # a release is not an authentication attempt
        "user": employee.pk,
        "released_by": administrator.pk,
        "locked_until": before["locked_until"],  # the lock it cleared
    }
    assert started <= release.attempted_at <= finished


def test_after_a_release_the_user_signs_in_with_the_right_password(administrator_client, employee):
    """"releasing a lock restores the ability to attempt authentication": the right password, which
    got the locked notice a moment ago, now signs the user in."""
    lock(employee)
    assert login(APIClient(), employee.email, PASSWORD).status_code == 403

    assert unlock(administrator_client, employee).status_code == 200

    response = login(APIClient(), employee.email, PASSWORD)
    assert response.status_code == 200
    assert response.json()["id"] == str(employee.id)


def test_a_release_gives_back_five_attempts_and_the_notice_after_the_next_lock(
    administrator_client, employee
):
    """The count is reset as well as the expiry. Left past LOCKOUT_NOTICE_CEILING, the next wrong
    password would lock the account again at once, and the right password after it would get the
    ordinary 401 instead of the locked notice (D-26). Reset, the user has the full five attempts,
    and once locked again the right password gets the 403 notice again."""
    lock(employee, failed_attempts=LOCKOUT_NOTICE_CEILING + 3)
    assert unlock(administrator_client, employee).status_code == 200

    client = APIClient()
    for attempt in range(LOCKOUT_THRESHOLD - 1):
        assert login(client, employee.email, WRONG_PASSWORD).status_code == 401, attempt
    assert User.objects.get(pk=employee.pk).locked_until is None  # four mistypes do not lock it

    assert login(client, employee.email, WRONG_PASSWORD).status_code == 401  # the fifth does
    assert User.objects.get(pk=employee.pk).locked_until > timezone.now()

    notice = login(client, employee.email, PASSWORD)
    assert notice.status_code == 403
    assert notice.json()["code"] == "account_locked"


def test_one_administrator_releases_another_administrators_lock(administrator, second_administrator):
    """FR-03 forbids an Administrator only their own account, not another Administrator's."""
    lock(administrator)

    response = unlock(logged_in(second_administrator), administrator)

    assert response.status_code == 200
    assert (response.json()["role"], response.json()["lock"]) == (ADMINISTRATOR_ROLE_NAME, None)
    stored = User.objects.get(pk=administrator.pk)
    assert (stored.failed_attempts, stored.locked_until) == (0, None)
    release = LoginAttempt.objects.get()
    assert (release.event, release.user_id, release.released_by_id) == (
        LOGIN_ATTEMPT_RELEASE, administrator.pk, second_administrator.pk,
    )


def test_the_release_row_records_the_connecting_address_not_x_forwarded_for(administrator_client, employee):
    """The source address is the connecting one, REMOTE_ADDR under NUM_PROXIES = 0, the key the
    sign-in throttle uses. A client can write any address into X-Forwarded-For (D-79)."""
    lock(employee)

    response = unlock(administrator_client, employee, HTTP_X_FORWARDED_FOR="203.0.113.9")

    assert response.status_code == 200
    assert LoginAttempt.objects.get().source_ip == "127.0.0.1"


def test_a_lock_set_by_login_and_its_release_are_two_rows_naming_the_same_lock(
    api_client, administrator_client, administrator, employee
):
    """End to end: five wrong passwords write the lockout row, the release writes its own row
    naming the same ``locked_until``, and the lockout row is left as it was."""
    for _ in range(LOCKOUT_THRESHOLD):
        assert login(api_client, employee.email, WRONG_PASSWORD).status_code == 401
    lockout = LoginAttempt.objects.get()
    assert lockout.event == LOGIN_ATTEMPT_LOCKOUT
    lockout_as_written = LoginAttempt.objects.filter(pk=lockout.pk).values().get()

    assert unlock(administrator_client, employee).status_code == 200

    assert LoginAttempt.objects.count() == 2
    release = LoginAttempt.objects.get(event=LOGIN_ATTEMPT_RELEASE)
    assert release.locked_until == lockout.locked_until
    assert (release.user_id, release.released_by_id) == (employee.pk, administrator.pk)
    assert LoginAttempt.objects.filter(pk=lockout.pk).values().get() == lockout_as_written
