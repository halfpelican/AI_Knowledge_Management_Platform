"""FR-03's lockout record and what it changes in login's responses (D-130).

FR-03 Business logic (configuration): "Every lockout is recorded with the attempted email, source
address, and timestamp." Benjamin's decision 5 (D-130): LoginAttempts records lockouts and
releases only, so an ordinary attempt and an unregistered address are never stored. The lockout
row is written by login in the transaction that sets ``locked_until``, and only there: an attempt
during a live lock never extends the window, so it never writes one.

The login 403 gains ``retry_after``, whole seconds until the lock ends, rounded up, from which the
sign-in page runs FR-03's countdown. The 401 does not change at all (security finding M1): it stays
byte-identical for an unknown address, a wrong password, a locked account given a wrong password,
and a locked account given the right one past LOCKOUT_NOTICE_CEILING, and neither status carries a
Retry-After header. The locked notice now names an administrator who can unlock the account
(FR-03's Front-End clause).

Windows' clock ticks at about 15.6 ms, so nothing here is told apart by a timestamp: an instant is
asserted to lie between two readings taken around the request, and ``retry_after`` against the
real clock is held to a small range. Where an exact value is the point, the view's clock is pinned.
"""

import datetime
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

import apps.api.views as views
from apps.accounts.models import LoginAttempt
from apps.core.constants import (
    LOCKOUT_DURATION,
    LOCKOUT_NOTICE_CEILING,
    LOCKOUT_THRESHOLD,
    LOGIN_ATTEMPT_LOCKOUT,
)
from conftest import PASSWORD

User = get_user_model()

pytestmark = pytest.mark.django_db

LOGIN = reverse("auth-login")
WRONG_PASSWORD = "Wrong-Horse-9-Battery"
LOCK_SECONDS = int(LOCKOUT_DURATION.total_seconds())
# Response headers whose value is the time the response was made. ``Expires`` is set by D-76's
# never-cache middleware to the moment of the response, at one-second resolution, so two
# otherwise identical responses a second apart differ in it. Their names are still compared.
TIME_HEADERS = {"Date", "Expires"}


def login(client, email, password, **extra):
    return client.post(LOGIN, {"email": email, "password": password}, format="json", **extra)


def lock(user, remaining=LOCKOUT_DURATION, failed_attempts=LOCKOUT_THRESHOLD):
    user.failed_attempts = failed_attempts
    user.locked_until = timezone.now() + remaining
    user.save(update_fields=["failed_attempts", "locked_until"])
    return user


def fail_until_locked(client, email, **extra):
    for attempt in range(LOCKOUT_THRESHOLD):
        assert login(client, email, WRONG_PASSWORD, **extra).status_code == 401, attempt


def fields_of(row):
    return {
        "event": row.event,
        "attempted_email": row.attempted_email,
        "source_ip": row.source_ip,
        "success": row.success,
        "user": row.user_id,
        "released_by": row.released_by_id,
        "locked_until": row.locked_until,
    }


# --- The lockout row ---------------------------------------------------------------------------------


def test_the_threshold_failure_writes_one_lockout_row_with_every_field(api_client, employee):
    """The address is recorded as login normalised it, in lower case, whatever case it was typed
    in. None is written below the threshold."""
    typed = "  Employee@EXAMPLE.com "
    for attempt in range(LOCKOUT_THRESHOLD - 1):
        assert login(api_client, typed, WRONG_PASSWORD).status_code == 401, attempt
    assert not LoginAttempt.objects.exists(), "a failure below the threshold wrote a row"

    started = timezone.now()
    assert login(api_client, typed, WRONG_PASSWORD).status_code == 401
    finished = timezone.now()

    employee.refresh_from_db()
    row = LoginAttempt.objects.get()
    assert fields_of(row) == {
        "event": LOGIN_ATTEMPT_LOCKOUT,
        "attempted_email": "employee@example.com",
        "source_ip": "127.0.0.1",
        "success": False,
        "user": employee.pk,
        "released_by": None,
        "locked_until": employee.locked_until,
    }
    assert row.success is False  # not None: the attempt that locked the account failed
    assert started <= row.attempted_at <= finished
    # Both timestamps come from the one instant the lock was set at.
    assert row.locked_until - row.attempted_at == LOCKOUT_DURATION


def test_no_attempt_during_a_live_lock_writes_a_row(api_client, employee):
    """Right password or wrong, within the notice ceiling or past it: none extends the window, so
    none writes a row."""
    fail_until_locked(api_client, employee.email)
    [lockout] = LoginAttempt.objects.all()
    locked_until = User.objects.get(pk=employee.pk).locked_until

    statuses = [
        login(api_client, employee.email, PASSWORD).status_code,  # the locked notice
        login(api_client, employee.email, WRONG_PASSWORD).status_code,
    ]
    # On to the notice ceiling, after which the right password too gets the 401 (D-26).
    for _ in range(LOCKOUT_NOTICE_CEILING - LOCKOUT_THRESHOLD - 2):
        statuses.append(login(api_client, employee.email, WRONG_PASSWORD).status_code)
    statuses.append(login(api_client, employee.email, PASSWORD).status_code)

    assert statuses == [403] + [401] * (LOCKOUT_NOTICE_CEILING - LOCKOUT_THRESHOLD)
    assert User.objects.get(pk=employee.pk).failed_attempts == LOCKOUT_NOTICE_CEILING + 1
    assert list(LoginAttempt.objects.values_list("pk", flat=True)) == [lockout.pk]
    assert User.objects.get(pk=employee.pk).locked_until == locked_until


def test_an_unknown_address_writes_no_row(api_client, employee):
    """An address with no account is never stored (D-130 decision 5), however often it fails."""
    for attempt in range(LOCKOUT_THRESHOLD + 1):
        assert login(api_client, "nobody@example.com", WRONG_PASSWORD).status_code == 401, attempt
    assert not LoginAttempt.objects.exists()


def test_after_a_lock_expires_the_next_threshold_writes_a_second_row(api_client, employee):
    """The expired window resets the count (D-25), so the second lock takes five more failures,
    and its row names the new lock. The first row is left as it was."""
    fail_until_locked(api_client, employee.email)
    first = LoginAttempt.objects.get()
    first_as_written = fields_of(first)
    User.objects.filter(pk=employee.pk).update(
        locked_until=timezone.now() - datetime.timedelta(seconds=1)
    )

    for attempt in range(LOCKOUT_THRESHOLD - 1):
        assert login(api_client, employee.email, WRONG_PASSWORD).status_code == 401, attempt
    assert LoginAttempt.objects.count() == 1
    assert login(api_client, employee.email, WRONG_PASSWORD).status_code == 401

    employee.refresh_from_db()
    second = LoginAttempt.objects.exclude(pk=first.pk).get()
    assert fields_of(second) == {**first_as_written, "locked_until": employee.locked_until}
    assert second.locked_until > first.locked_until
    assert fields_of(LoginAttempt.objects.get(pk=first.pk)) == first_as_written


@pytest.mark.parametrize(
    "extra, recorded",
    [
        ({"HTTP_X_FORWARDED_FOR": "203.0.113.9"}, "127.0.0.1"),
        ({"REMOTE_ADDR": "198.51.100.7"}, "198.51.100.7"),
    ],
    ids=["x-forwarded-for is ignored", "the connecting address is recorded"],
)
def test_the_lockout_row_records_the_connecting_address(api_client, employee, extra, recorded):
    """``source_ip`` is DRF's ``get_ident()``, REMOTE_ADDR under NUM_PROXIES = 0, the key the
    sign-in throttle counts against. X-Forwarded-For is never read: a client can write any address
    into it (D-79)."""
    fail_until_locked(api_client, employee.email, **extra)
    assert LoginAttempt.objects.get().source_ip == recorded


# --- retry_after on the locked notice ---------------------------------------------------------------


def test_retry_after_is_whole_seconds_within_the_lock(api_client, employee):
    fail_until_locked(api_client, employee.email)

    response = login(api_client, employee.email, PASSWORD)

    assert response.status_code == 403
    retry_after = response.json()["retry_after"]
    assert type(retry_after) is int
    assert 1 <= retry_after <= LOCK_SECONDS
    # The lock was set a moment ago, so nearly all of it is left.
    assert retry_after >= LOCK_SECONDS - 60


def test_retry_after_is_the_time_left_on_the_accounts_lock(api_client, employee):
    """Computed from the account's own ``locked_until``, not from LOCKOUT_DURATION. The view reads
    the clock after bcrypt has run, so a little time has passed: rounded up, the value is 100 or a
    little less, and never more, because the clock does not run backwards."""
    lock(employee, remaining=datetime.timedelta(seconds=100))

    response = login(api_client, employee.email, PASSWORD)

    assert response.status_code == 403
    assert 90 <= response.json()["retry_after"] <= 100


@pytest.mark.parametrize(
    "remaining, retry_after",
    [(datetime.timedelta(seconds=0.2), 1), (datetime.timedelta(seconds=99.2), 100)],
    ids=["0.2 s left is 1 s, the minimum", "99.2 s left rounds up to 100"],
)
def test_retry_after_rounds_up_so_the_page_never_reopens_early(
    monkeypatch, api_client, employee, remaining, retry_after
):
    """Whole seconds, rounded up, so the countdown can never reach zero before the lock does.

    The view's clock is pinned to the instant the lock is set from. Against the real clock a 0.2 s
    lock would be over before the view decides, since bcrypt alone takes longer than that.
    ``timezone`` is replaced in the view module only, so nothing else's clock moves."""
    pinned = timezone.now()
    employee.failed_attempts = LOCKOUT_THRESHOLD
    employee.locked_until = pinned + remaining
    employee.save(update_fields=["failed_attempts", "locked_until"])
    monkeypatch.setattr(views, "timezone", SimpleNamespace(now=lambda: pinned))

    response = login(api_client, employee.email, PASSWORD)

    assert response.status_code == 403
    assert response.json()["retry_after"] == retry_after


def test_the_locked_notice_carries_no_retry_after_header(api_client, employee):
    """In this contract Retry-After is the throttle's, on a 429, and the client reads it there
    (frontend/src/api/client.js). The countdown comes from the body."""
    lock(employee)

    response = login(api_client, employee.email, PASSWORD)

    assert response.status_code == 403
    assert "retry_after" in response.json()
    assert "Retry-After" not in response


def test_the_locked_notice_names_an_administrator_who_can_unlock_the_account(api_client, employee):
    """FR-03: "The lockout message states that an administrator can unlock the account, so a
    locked-out user has a route forward." D-26 finding 4 removed that sentence while no release
    existed; POST /api/users/{id}/unlock is the release, so it is back (D-130)."""
    lock(employee)

    detail = login(api_client, employee.email, PASSWORD).json()["detail"]

    assert detail == views.ACCOUNT_LOCKED_MESSAGE
    assert "administrator" in detail
    assert "unlock" in detail


# --- M1: every 401 is the same response -------------------------------------------------------------


def comparable(response):
    """What a caller can read from a response, less the values that are only the time of day and
    the csrftoken cookie's value, which login sends on every response and which is random."""
    return {
        "status": response.status_code,
        "body": response.content,
        "header names": set(response.headers),
        "headers": {
            name: value for name, value in response.headers.items() if name not in TIME_HEADERS
        },
        "cookie names": set(response.cookies),
    }


def unknown_address(employee):
    return "someone-else@example.com", WRONG_PASSWORD, None


def registered_wrong_password(employee):
    return employee.email, WRONG_PASSWORD, {"failed_attempts": 1, "locked": False}


def locked_wrong_password(employee):
    lock(employee)
    return employee.email, WRONG_PASSWORD, {"failed_attempts": LOCKOUT_THRESHOLD + 1, "locked": True}


def locked_past_the_ceiling_right_password(employee):
    lock(employee, failed_attempts=LOCKOUT_NOTICE_CEILING)
    return employee.email, PASSWORD, {"failed_attempts": LOCKOUT_NOTICE_CEILING + 1, "locked": True}


@pytest.mark.parametrize(
    "case",
    [unknown_address, registered_wrong_password, locked_wrong_password, locked_past_the_ceiling_right_password],
    ids=lambda case: case.__name__.replace("_", " "),
)
def test_every_401_is_byte_identical_to_an_unknown_addresses(employee, case):
    """Security finding M1. Any byte, header or cookie that differed between these would tell a
    caller which case it had hit, and so whether an address is registered, or locked, or whether
    a guess during a lock was right. Neither carries retry_after or a Retry-After header."""
    reference = login(APIClient(), "nobody@example.com", WRONG_PASSWORD)
    email, password, account_afterwards = case(employee)

    response = login(APIClient(), email, password)

    assert reference.status_code == 401
    assert comparable(response) == comparable(reference)
    for each in (reference, response):
        assert b"retry_after" not in each.content
        assert "Retry-After" not in each
    if account_afterwards is not None:
        # The request reached the branch the case names, so the comparison is not vacuous.
        stored = User.objects.get(pk=employee.pk)
        assert {
            "failed_attempts": stored.failed_attempts,
            "locked": stored.locked_until is not None and stored.locked_until > timezone.now(),
        } == account_afterwards
