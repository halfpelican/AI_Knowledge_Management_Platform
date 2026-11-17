"""FR-04 as D-137 amends it: "Remember me" on POST /api/auth/login keeps a session for seven days
without use.

D-137 (Benjamin Morovan, lead, 16 November 2026) supersedes FR-04's "Sessions also expire
automatically after 60 minutes of inactivity", and NFR-06's "User authentication sessions must
expire after 60 minutes of inactivity" (named in D-137 on 17 November 2026), for a session started
with "Remember me" ticked, and for no other session. So:

- ``"remember": true`` gives the session REMEMBERED_SESSION_DAYS (7) days without use, for both
  roles. The cookie's Max-Age and the django_session row's expire_date both say so.
- The seven days slide with use, as the 60 minutes do. Django keeps an expiry given in whole seconds
  as an inactivity age, which SESSION_SAVE_EVERY_REQUEST restarts on every request, and one given as
  a timedelta or a datetime as a fixed end.
- ``"remember": false``, or no ``remember``, leaves the session as FR-04 has it: 60 minutes without
  use. An unticked sign-in after a remembered one, on the same session, ends the seven days.
- Logout destroys a remembered session server-side, as it does any other (D-10).
- A ``remember`` that is not a boolean is a 400 with a field error, in DRF's words, which the
  contract quotes. ``remember`` is read as DRF's BooleanField reads it, so ``"true"`` and ``1`` are
  true. A bad one is judged with email and password, before any account is read, so it is one 400
  for every address and never a failed attempt.
- A sign-in that fails starts no session, ticked or not, and leaves a session the browser already
  holds with the expiry it had. Only a session started by a sign-in with "Remember me" ticked gets
  seven days.

**These tests move Django's clock** (``django.utils.timezone.now``), the clock Django reads both
when it saves a session's expire_date and when it decides on loading one whether it has expired.
Rewriting expire_date in the database, as test_logout.py does for the 60 minutes, can show that an
expired session is refused, but it cannot show what a week of use does to the expiry. A session used
at six days and again six days later is alive only if the expiry slides. A fixed end seven days
after sign-in has passed by then.

Login is an open route (D-21), so there is no anonymous 401 to test. Every test here runs once for
an Employee and once for an Administrator, through the ``account`` fixture (CLAUDE.md section 8).
"""

import datetime
from dataclasses import dataclass

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.constants import (
    LOCKOUT_THRESHOLD,
    REMEMBERED_SESSION_DAYS,
    ROLE_NAMES,
    SESSION_INACTIVITY_MINUTES,
)
from conftest import PASSWORD

User = get_user_model()

pytestmark = pytest.mark.django_db

LOGIN = reverse("auth-login")
LOGOUT = reverse("auth-logout")
ME = reverse("auth-me")
# "picture" since D-137: the profile picture's address, or null.
USER_OBJECT_KEYS = {"id", "name", "email", "role", "created_at", "picture"}

REMEMBERED_SECONDS = REMEMBERED_SESSION_DAYS * 24 * 60 * 60
UNREMEMBERED_SECONDS = SESSION_INACTIVITY_MINUTES * 60
UNTICKED = [{}, {"remember": False}]
UNTICKED_IDS = ["absent", "false"]
WRONG_PASSWORD = "Wrong-Guess-1!"
UNKNOWN_ADDRESS = "nobody@example.com"
# docs/api-contract.md, "Remember me" on sign-in, quotes both 400 messages word for word.
NOT_A_BOOLEAN = "Must be a valid boolean."
NULL = "This field may not be null."


@dataclass
class Clock:
    """The time Django reads, stopped, and moved only by ``advance()``."""

    now: datetime.datetime

    def read(self):
        return self.now

    def advance(self, **delta):
        self.now += datetime.timedelta(**delta)


@pytest.fixture
def clock(monkeypatch):
    """Django's clock, stopped at the real time when the test starts.

    django.contrib.sessions reads the time only through ``django.utils.timezone.now``, looked up
    on the module at call time: once when a save computes expire_date, and once when a load keeps
    only a row whose expire_date is after now. Patching the module attribute reaches both.
    """
    clock = Clock(timezone.now())
    monkeypatch.setattr(timezone, "now", clock.read)
    return clock


@pytest.fixture(params=ROLE_NAMES, ids=[name.lower() for name in ROLE_NAMES])
def account(request):
    """One user per role, so each test runs for an Employee and for an Administrator. D-137 gives
    "Remember me" to both roles."""
    return request.getfixturevalue(request.param.lower())


def sign_in(client, user, extra=None, **headers):
    """POST /api/auth/login for ``user`` with the suite's password, ``extra`` added to the body."""
    body = {"email": user.email, "password": PASSWORD, **(extra or {})}
    return client.post(LOGIN, body, format="json", **headers)


def csrf_header(client):
    return {"HTTP_X_CSRFTOKEN": client.cookies[settings.CSRF_COOKIE_NAME].value}


def session_key(client):
    return client.cookies[settings.SESSION_COOKIE_NAME].value


def expire_date(client):
    return Session.objects.get(session_key=session_key(client)).expire_date


def replay(key):
    """A fresh client carrying nothing but the session cookie's value."""
    client = APIClient()
    client.cookies[settings.SESSION_COOKIE_NAME] = key
    return client


# --- What a sign-in sets ----------------------------------------------------------------------------


def test_a_remembered_sign_in_gives_the_cookie_and_the_row_seven_days(clock, account):
    client = APIClient()

    response = sign_in(client, account, {"remember": True})

    assert response.status_code == 200
    assert set(response.json()) == USER_OBJECT_KEYS  # the response itself is unchanged
    assert response.cookies[settings.SESSION_COOKIE_NAME]["max-age"] == REMEMBERED_SECONDS
    assert expire_date(client) == clock.now + datetime.timedelta(seconds=REMEMBERED_SECONDS)


@pytest.mark.parametrize("extra", UNTICKED, ids=UNTICKED_IDS)
def test_an_unticked_sign_in_keeps_fr04s_sixty_minutes(clock, account, extra):
    client = APIClient()

    response = sign_in(client, account, extra)

    assert response.status_code == 200
    assert response.cookies[settings.SESSION_COOKIE_NAME]["max-age"] == UNREMEMBERED_SECONDS
    assert expire_date(client) == clock.now + datetime.timedelta(seconds=UNREMEMBERED_SECONDS)


# --- How long a session lasts without use -----------------------------------------------------------


def test_a_remembered_session_outlives_sixty_minutes_without_use(clock, account):
    client = APIClient()
    sign_in(client, account, {"remember": True})

    clock.advance(minutes=SESSION_INACTIVITY_MINUTES, seconds=1)

    assert client.get(ME).status_code == 200


def test_a_remembered_session_slides_with_use(clock, account):
    """Used at six days and again six days after that, it is alive both times. Twelve days after
    sign-in is five days past a fixed end at seven. Each use moves the cookie and the row seven
    days on, and seven days without use after the last one end it."""
    client = APIClient()
    sign_in(client, account, {"remember": True})

    clock.advance(days=6)
    response = client.get(ME)
    assert response.status_code == 200
    assert response.cookies[settings.SESSION_COOKIE_NAME]["max-age"] == REMEMBERED_SECONDS

    clock.advance(days=6)
    response = client.get(ME)
    assert response.status_code == 200
    assert response.cookies[settings.SESSION_COOKIE_NAME]["max-age"] == REMEMBERED_SECONDS
    assert expire_date(client) == clock.now + datetime.timedelta(seconds=REMEMBERED_SECONDS)

    clock.advance(days=REMEMBERED_SESSION_DAYS, seconds=1)
    assert client.get(ME).status_code == 401


def test_a_remembered_session_ends_after_seven_days_without_use(clock, account):
    client = APIClient()
    sign_in(client, account, {"remember": True})

    clock.advance(days=REMEMBERED_SESSION_DAYS, seconds=1)

    assert client.get(ME).status_code == 401


@pytest.mark.parametrize("extra", UNTICKED, ids=UNTICKED_IDS)
def test_an_unremembered_session_ends_after_sixty_minutes_without_use(clock, account, extra):
    client = APIClient()
    sign_in(client, account, extra)

    clock.advance(minutes=SESSION_INACTIVITY_MINUTES, seconds=1)

    assert client.get(ME).status_code == 401


@pytest.mark.parametrize("extra", UNTICKED, ids=UNTICKED_IDS)
def test_an_unticked_sign_in_after_a_remembered_one_ends_the_seven_days(clock, account, extra):
    """Django's login() neither flushes nor cycles the session when the same user signs in again
    on it, so the seven days would survive an unticked sign-in unless the view clears them."""
    client = APIClient(enforce_csrf_checks=True)
    assert sign_in(client, account, {"remember": True}).status_code == 200
    remembered = session_key(client)

    # The browser already holds a session, so the sign-in carries X-CSRFToken (D-21).
    response = sign_in(client, account, extra, **csrf_header(client))

    assert response.status_code == 200
    assert session_key(client) == remembered  # the same session: the case login() leaves alone
    assert response.cookies[settings.SESSION_COOKIE_NAME]["max-age"] == UNREMEMBERED_SECONDS
    assert expire_date(client) == clock.now + datetime.timedelta(seconds=UNREMEMBERED_SECONDS)
    clock.advance(minutes=SESSION_INACTIVITY_MINUTES, seconds=1)
    assert client.get(ME).status_code == 401


# --- Logout -----------------------------------------------------------------------------------------


def test_logout_ends_a_remembered_session(account):
    client = APIClient(enforce_csrf_checks=True)
    assert sign_in(client, account, {"remember": True}).status_code == 200
    key = session_key(client)
    assert replay(key).get(ME).status_code == 200

    response = client.post(LOGOUT, **csrf_header(client))

    assert response.status_code == 200
    assert not Session.objects.filter(session_key=key).exists()
    assert replay(key).get(ME).status_code == 401


# --- 400 ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    ["sometimes", 2, "", None, [True], {"remember": True}],
    ids=["word", "two", "empty-string", "null", "list", "object"],
)
def test_a_remember_that_is_not_a_boolean_is_400(api_client, account, value):
    response = sign_in(api_client, account, {"remember": value})

    assert response.status_code == 400
    assert list(response.json()) == ["remember"]
    assert settings.SESSION_COOKIE_NAME not in response.cookies
    assert api_client.get(ME).status_code == 401


@pytest.mark.parametrize(
    "value, message",
    [
        ("sometimes", NOT_A_BOOLEAN),
        (2, NOT_A_BOOLEAN),
        ("", NOT_A_BOOLEAN),
        ([True], NOT_A_BOOLEAN),
        ({"remember": True}, NOT_A_BOOLEAN),
        (None, NULL),
    ],
    ids=["word", "two", "empty-string", "list", "object", "null"],
)
def test_a_remember_that_is_not_a_boolean_is_400_in_the_contracts_words(api_client, account, value, message):
    """The contract quotes both messages: ``["Must be a valid boolean."]``, and
    ``["This field may not be null."]`` for null. The test above checks only which field is named."""
    response = sign_in(api_client, account, {"remember": value})

    assert response.status_code == 400
    assert response.json() == {"remember": [message]}


@pytest.mark.parametrize("value", ["sometimes", None], ids=["word", "null"])
def test_a_bad_remember_is_judged_before_any_account_so_it_is_one_400_and_no_failed_attempt(
    api_client, account, value
):
    """The contract: a bad ``remember`` "is checked with email and password, before any account is
    read, so like their 400s it is the same for every address and is not a failed attempt". So a
    wrong password, an unknown address and the right password all get the same 400, and FR-02's
    count and lock are untouched. Judged after the account, the wrong password would be a counted
    401 and the unknown address a 401, which would tell the two apart."""
    attempts = [
        {"email": account.email, "password": WRONG_PASSWORD},
        {"email": UNKNOWN_ADDRESS, "password": WRONG_PASSWORD},
        {"email": account.email, "password": PASSWORD},
    ]

    responses = [api_client.post(LOGIN, {**body, "remember": value}, format="json") for body in attempts]

    assert [response.status_code for response in responses] == [400, 400, 400]
    assert len({response.content for response in responses}) == 1
    assert set(responses[0].json()) == {"remember"}
    account.refresh_from_db()
    assert (account.failed_attempts, account.locked_until) == (0, None)
    assert api_client.get(ME).status_code == 401


@pytest.mark.parametrize(
    "value, remembered",
    [("true", True), (1, True), ("false", False), (0, False)],
    ids=["the-string-true", "the-number-1", "the-string-false", "the-number-0"],
)
def test_remember_is_read_as_drfs_boolean_field_reads_it(clock, account, value, remembered):
    """The contract: "JSON ``true`` and ``false``, and the strings and numbers that field accepts for
    them, such as ``"true"`` and ``1``." Every other test here sends JSON booleans."""
    client = APIClient()

    response = sign_in(client, account, {"remember": value})

    assert response.status_code == 200
    seconds = REMEMBERED_SECONDS if remembered else UNREMEMBERED_SECONDS
    assert response.cookies[settings.SESSION_COOKIE_NAME]["max-age"] == seconds
    assert expire_date(client) == clock.now + datetime.timedelta(seconds=seconds)


# --- A sign-in that fails -----------------------------------------------------------------------------


def lock(user):
    """FR-03's lock on ``user``, as LOCKOUT_THRESHOLD failed sign-ins leave it."""
    User.objects.filter(pk=user.pk).update(
        failed_attempts=LOCKOUT_THRESHOLD, locked_until=timezone.now() + datetime.timedelta(minutes=10)
    )


@pytest.mark.parametrize(
    "attempt, expected_status",
    [("wrong password", 401), ("unknown address", 401), ("locked account", 403)],
    ids=["wrong-password", "unknown-address", "locked-account"],
)
def test_a_remembered_sign_in_that_fails_starts_no_session(account, attempt, expected_status):
    """D-137's seven days are for "a session started with 'Remember me' ticked". A sign-in that
    fails starts no session, so ticked it still sets no cookie and writes no django_session row, as
    test_login.py has it for an unticked one: nothing else about login changes, its 401 and 403
    included."""
    body = {"email": account.email, "password": PASSWORD, "remember": True}
    if attempt == "wrong password":
        body["password"] = WRONG_PASSWORD
    elif attempt == "unknown address":
        body["email"] = UNKNOWN_ADDRESS
    else:
        lock(account)
    sessions_before = Session.objects.count()
    client = APIClient()

    response = client.post(LOGIN, body, format="json")

    assert response.status_code == expected_status
    assert settings.SESSION_COOKIE_NAME not in response.cookies
    assert Session.objects.count() == sessions_before
    assert client.get(ME).status_code == 401


@pytest.mark.parametrize(
    "held, attempt, remembered",
    [({}, {"remember": True}, False), ({"remember": True}, {"remember": False}, True)],
    ids=["an-hour-session-then-a-ticked-failure", "a-remembered-session-then-an-unticked-failure"],
)
def test_a_sign_in_that_fails_leaves_the_browsers_session_with_the_expiry_it_had(
    clock, account, held, attempt, remembered
):
    """D-137 gives seven days to a session started with "Remember me" ticked, "and for no other
    session", and the latest *sign-in* decides. A failed sign-in from a browser already holding a
    session decides nothing: ticked, it does not give an hour's session seven days, and unticked, it
    does not take them from a remembered one."""
    client = APIClient(enforce_csrf_checks=True)
    assert sign_in(client, account, held).status_code == 200
    key = session_key(client)
    seconds = REMEMBERED_SECONDS if remembered else UNREMEMBERED_SECONDS

    # The browser holds a session, so the sign-in carries X-CSRFToken (D-21).
    response = client.post(
        LOGIN,
        {"email": account.email, "password": WRONG_PASSWORD, **attempt},
        format="json",
        **csrf_header(client),
    )

    assert response.status_code == 401
    assert session_key(client) == key
    assert expire_date(client) == clock.now + datetime.timedelta(seconds=seconds)
    clock.advance(minutes=SESSION_INACTIVITY_MINUTES, seconds=1)
    assert client.get(ME).status_code == (200 if remembered else 401)
