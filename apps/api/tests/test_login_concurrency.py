"""FR-02's lockout under concurrent logins: the login race, security finding H1 (D-130).

``LoginView`` used to decide "locked or not" on ``locked_until`` read without a lock, before the
bcrypt-long ``authenticate()``, and ``_record_failed_attempt`` reset any ``locked_until`` it found
set, on the stated assumption that a live lock never reached it. Two requests for one account
could each decide on a state the other had already changed. The fix runs ``authenticate()``
first, then makes the whole decision in one transaction, on the account row read with
``select_for_update()``. These tests put requests in that window on purpose:

1. Five wrong passwords at once must leave the account locked, with every attempt counted.
2. A right password that has authenticated must get no session once a concurrent request has
   locked the account. FR-03 Validation: "No session is issued for a locked account under any
   circumstance, regardless of the password submitted."
3. A password verified against one account must not count for another: the account check the fix
   adds, for an address deleted and registered again while the hash ran.

**Deterministic, not timed.** Each concurrent request runs in a thread of its own, with its own
``APIClient`` and so its own database connection, which the thread closes when it ends.
``apps.api.views.authenticate`` is patched with a wrapper that calls the real one, so bcrypt still
runs, and then holds the request: at a ``threading.Barrier`` until every request has authenticated
(test 1), or on an ``Event`` until the other request has finished (test 2). Nothing is ordered by
a sleep or told apart by a timestamp (Windows' clock ticks at about 15.6 ms), and every wait has a
timeout, so a regression fails rather than hangs.

**``transaction=True``.** A thread's connection cannot see a test transaction's uncommitted rows,
so these tests commit for real and the database is flushed after each. ``serialized_rollback``
restores the rows the migrations seeded, among them the roles the user fixtures need, before each
one, as in apps/meetings/tests/test_summary_runner.py. Test 3 needs no thread; it shares the mark
so that the whole file works one way.
"""

from __future__ import annotations

import datetime
import threading

import pytest
from django.conf import settings
from django.contrib.auth import SESSION_KEY, get_user_model
from django.contrib.sessions.models import Session
from django.db import connections
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

import apps.api.views as views
from apps.api.views import ACCOUNT_LOCKED_CODE, ACCOUNT_LOCKED_MESSAGE, INVALID_CREDENTIALS_MESSAGE
from apps.core.constants import LOCKOUT_DURATION, LOCKOUT_NOTICE_CEILING, LOCKOUT_THRESHOLD
from conftest import PASSWORD

User = get_user_model()

pytestmark = pytest.mark.django_db(transaction=True, serialized_rollback=True)

LOGIN = reverse("auth-login")
WRONG_PASSWORD = "Wrong-Horse-9-Battery"
CONCURRENT_WRONG_PASSWORDS = 5
# The longest any wait here lasts before the test fails instead. A bcrypt check takes a fraction
# of a second, so only a regression ever reaches it.
PATIENCE = 30


def login(client, email, password):
    return client.post(LOGIN, {"email": email, "password": password}, format="json")


class LoginThread(threading.Thread):
    """One login request in a thread of its own, with its own client and so its own database
    connection, closed when the request ends. What the request raised is kept for ``finish``."""

    def __init__(self, name: str, email: str, password: str):
        super().__init__(name=f"login-{name}", daemon=True)
        self.email = email
        self.password = password
        self.client = APIClient()
        self.response = None
        self.error: BaseException | None = None

    def run(self):
        try:
            self.response = login(self.client, self.email, self.password)
        except BaseException as error:  # re-raised in the test's own thread by finish()
            self.error = error
        finally:
            # Connections are per thread, so this closes this request's and no other. One left
            # open would stop the test database from being dropped at the end of the run.
            connections.close_all()


def finish(*threads: LoginThread) -> None:
    """Join every thread that was started, then re-raise the first error any of them kept. A
    thread still running after PATIENCE fails the test rather than hanging it."""
    started = [thread for thread in threads if thread.ident is not None]
    for thread in started:
        thread.join(PATIENCE)
    stuck = [thread.name for thread in started if thread.is_alive()]
    assert not stuck, f"still running after {PATIENCE}s: {stuck}"
    for thread in started:
        if thread.error is not None:
            raise thread.error


def invalid_credentials_body() -> bytes:
    """The body of the 401 an address with no account gets. Every 401 in this file must match it
    byte for byte, or the response would tell a caller which case it had hit (D-02, D-25). Taken
    before ``authenticate()`` is patched, so nothing holds this request."""
    response = login(APIClient(), "nobody@example.com", WRONG_PASSWORD)
    assert response.status_code == 401
    assert response.json() == {"detail": INVALID_CREDENTIALS_MESSAGE}
    return response.content


def sessions_signed_in_as(user) -> int:
    """How many ``django_session`` rows, decoded, sign in ``user``."""
    return sum(
        1
        for session in Session.objects.all()
        if session.get_decoded().get(SESSION_KEY) == str(user.pk)
    )


def test_concurrent_wrong_passwords_leave_the_lock_in_place(monkeypatch, employee):
    """Five wrong passwords arrive together at a count of 1. All five are counted, and the lock
    set when the count reaches the threshold is still there after the fifth.

    The barrier releases the five only once every one has verified its password, so all five
    reach the decision together. On the old order each had read "unlocked" by then: the writes
    went 2, 3, 4, then 5 with the lock set, and the fifth, finding locked_until set, took it for
    an expired lock and reset it, leaving a count of 1 and no lock. On the fix they decide one
    after another on the row read under lock, and the fifth is counted during the lock (D-26).

    Against the old order this is deterministic, because every request's unlocked read came
    before authenticate(). Against the fixed order without the row lock, the five would read
    together and overwrite one another's counts: the barrier makes that the likely interleaving
    but cannot force it, so that regression is caught in practice rather than by construction.
    """
    employee.failed_attempts = 1
    employee.save(update_fields=["failed_attempts"])
    invalid_credentials = invalid_credentials_body()

    real_authenticate = views.authenticate
    everyone_has_authenticated = threading.Barrier(CONCURRENT_WRONG_PASSWORDS)
    held = []

    def authenticate_then_wait_for_the_others(request=None, **credentials):
        user = real_authenticate(request, **credentials)
        held.append(credentials["username"])
        # BrokenBarrierError in every waiting request if one of them never arrives.
        everyone_has_authenticated.wait(PATIENCE)
        return user

    monkeypatch.setattr(views, "authenticate", authenticate_then_wait_for_the_others)
    requests = [
        LoginThread(str(number), employee.email, WRONG_PASSWORD)
        for number in range(CONCURRENT_WRONG_PASSWORDS)
    ]
    before = timezone.now()
    for thread in requests:
        thread.start()
    finish(*requests)
    after = timezone.now()

    assert held == [employee.email] * CONCURRENT_WRONG_PASSWORDS  # every request was held
    assert [thread.response.status_code for thread in requests] == [401] * CONCURRENT_WRONG_PASSWORDS
    assert all(thread.response.content == invalid_credentials for thread in requests)
    employee.refresh_from_db()
    assert {
        "failed_attempts": employee.failed_attempts,
        "locked": employee.locked_until is not None and employee.locked_until > timezone.now(),
    } == {"failed_attempts": 1 + CONCURRENT_WRONG_PASSWORDS, "locked": True}
    # Set by one of these five requests, for LOCKOUT_DURATION.
    assert before + LOCKOUT_DURATION <= employee.locked_until <= after + LOCKOUT_DURATION


def test_a_right_password_gets_no_session_once_a_concurrent_request_has_locked_the_account(
    monkeypatch, employee
):
    """Request A sends the right password at one failure short of the threshold and is held
    after authenticate(). Request B sends a wrong one, locks the account and finishes. Released,
    A must get the 403 and no session.

    On the old order A had read "unlocked" before it verified its password, so it signed in, and
    its counter reset erased B's lock. FR-03 Validation: "No session is issued for a locked
    account under any circumstance, regardless of the password submitted", and "A matching
    password submitted during an active lockout window neither clears the lock nor resets the
    counter." On the fix A decides on the row read under lock, after B committed: locked, so A's
    attempt is counted (D-26) and, the password having matched and the total being within
    LOCKOUT_NOTICE_CEILING, the lock is announced (D-25).
    """
    employee.failed_attempts = LOCKOUT_THRESHOLD - 1
    employee.last_login = timezone.now() - datetime.timedelta(days=1)
    employee.save(update_fields=["failed_attempts", "last_login"])
    last_login = User.objects.get(pk=employee.pk).last_login  # as stored
    invalid_credentials = invalid_credentials_body()

    real_authenticate = views.authenticate
    a_authenticated, b_done = threading.Event(), threading.Event()

    def authenticate_then_hold_the_right_password(request=None, **credentials):
        user = real_authenticate(request, **credentials)
        if credentials["password"] == PASSWORD:  # A. B's wrong password passes straight through.
            a_authenticated.set()
            if not b_done.wait(PATIENCE):
                raise AssertionError(f"request B did not finish within {PATIENCE}s")
        return user

    monkeypatch.setattr(views, "authenticate", authenticate_then_hold_the_right_password)
    a = LoginThread("A", employee.email, PASSWORD)
    b = LoginThread("B", employee.email, WRONG_PASSWORD)
    a.start()
    try:
        assert a_authenticated.wait(PATIENCE), "request A never got through authenticate()"
        b.start()
        b.join(PATIENCE)
        locked_by_b = User.objects.get(pk=employee.pk)  # B has finished, and A is still held
    finally:
        b_done.set()  # never leave A held, whatever happened above
        finish(a, b)

    # B is the ordinary 401, and it locked the account.
    assert b.response.status_code == 401
    assert b.response.content == invalid_credentials
    assert locked_by_b.failed_attempts == LOCKOUT_THRESHOLD
    assert locked_by_b.locked_until is not None and locked_by_b.locked_until > timezone.now()

    employee.refresh_from_db()
    assert {
        "status": a.response.status_code,
        "code": a.response.json().get("code"),
        "session cookie": settings.SESSION_COOKIE_NAME in a.response.cookies,
        "sessions signed in as the account": sessions_signed_in_as(employee),
        "last_login": employee.last_login,
        "locked_until": employee.locked_until,
        "failed_attempts": employee.failed_attempts,
    } == {
        "status": 403,
        "code": ACCOUNT_LOCKED_CODE,
        "session cookie": False,
        "sessions signed in as the account": 0,
        "last_login": last_login,  # unchanged: nobody signed in
        "locked_until": locked_by_b.locked_until,  # B's lock, neither cleared nor extended
        "failed_attempts": LOCKOUT_THRESHOLD + 1,  # A's attempt, counted during the lock (D-26)
    }
    assert a.response.json()["detail"] == ACCOUNT_LOCKED_MESSAGE
    assert employee.failed_attempts <= LOCKOUT_NOTICE_CEILING  # why the lock could be announced


def test_a_password_verified_against_another_account_does_not_count(monkeypatch, employee):
    """``authenticate()`` runs before the row lock, so the row it checked the password against
    may not be the row the decision reads: an account deleted, and its address registered again,
    while the hash ran. The fix counts the password only when both are the same account
    (``user.pk == account.pk``, D-130).

    Simulated simply: for the submitted address, ``authenticate()`` returns a different, real
    account. The right password is sent, so the account check is all that stands between this
    request and a session for the wrong person. It must be the ordinary 401, sign in neither
    account, and count as one failure against the account that holds the address.
    """
    former_holder = User.objects.create_user(
        "former-holder@example.com", PASSWORD, name="Fran Former"
    )
    failed_before = employee.failed_attempts
    invalid_credentials = invalid_credentials_body()

    real_authenticate = views.authenticate
    returned = []

    def authenticate_against_another_account(request=None, **credentials):
        verified = real_authenticate(request, **credentials)
        if credentials["username"] == employee.email:
            # Returned as authenticate() returns a user: carrying the backend that verified it.
            former_holder.backend = verified.backend
            verified = former_holder
        returned.append(verified)
        return verified

    monkeypatch.setattr(views, "authenticate", authenticate_against_another_account)
    response = login(APIClient(), employee.email, PASSWORD)

    assert returned == [former_holder]  # the request reached the patch
    employee.refresh_from_db()
    former_holder.refresh_from_db()
    assert {
        "status": response.status_code,
        "body is the 401's": response.content == invalid_credentials,
        "session cookie": settings.SESSION_COOKIE_NAME in response.cookies,
        "sessions signed in as the address's account": sessions_signed_in_as(employee),
        "sessions signed in as the other account": sessions_signed_in_as(former_holder),
        "the other account's last_login": former_holder.last_login,
        "failed_attempts": employee.failed_attempts,
    } == {
        "status": 401,
        "body is the 401's": True,
        "session cookie": False,
        "sessions signed in as the address's account": 0,
        "sessions signed in as the other account": 0,
        "the other account's last_login": None,
        "failed_attempts": failed_before + 1,  # one failure, against the address's account
    }
