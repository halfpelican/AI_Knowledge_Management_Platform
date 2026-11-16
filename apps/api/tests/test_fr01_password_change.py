"""A signed-in user changes their own password: ``POST /api/auth/change-password`` (D-137).

D-137 (Benjamin Morovan, lead, 16 November 2026) gives PR #119's Profile page a server. What this
file holds, each from D-137 or from a rule the project already has:

- **Both roles, a session and nothing more.** No session is the project's 401 for a protected
  route. CSRF is checked as on every other unsafe request from a session.
- **The body is ``{"current_password", "new_password"}``,** both required, each a 400 with a field
  error when missing, blank or null.
- **A wrong current password is a 400 on ``current_password``, never a 401.** The front end treats
  every 401 as an expired session and signs the user out. A wrong one touches neither
  ``failed_attempts`` nor ``locked_until``, and the session that sent it stays signed in.
- **The new password passes registration's ``AUTH_PASSWORD_VALIDATORS``** against this user (FR-01)
  and may not be the current one. Either failure is a 400 on ``new_password``.
- **A success is a 200 with a short ``detail``.** The new password signs in and the old one does
  not. The session that made the change stays, under a new key, with its expiry, a remembered one
  included. Every other session of the user ends, and other users' sessions do not.
- **The change touches the password alone.** FR-03's lock and count stay as they were, and a role
  change committed while the request ran is not written back over.

The ``password_change`` throttle, 10 an hour per user, is tested with the other scopes in
``apps/api/tests/test_throttles.py``. Every test here that holds a session runs once for an Employee
and once for an Administrator (CLAUDE.md section 8).
"""

import datetime
from dataclasses import dataclass

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

import apps.api.serializers
from apps.accounts.models import Role
from apps.api.serializers import CURRENT_PASSWORD_INCORRECT_MESSAGE, NEW_PASSWORD_UNCHANGED_MESSAGE
from apps.api.views import ACCOUNT_LOCKED_CODE, PASSWORD_CHANGED_MESSAGE
from apps.core.constants import (
    LOCKOUT_THRESHOLD,
    REMEMBERED_SESSION_DAYS,
    ROLE_NAMES,
    SESSION_INACTIVITY_MINUTES,
)
from conftest import PASSWORD

User = get_user_model()

pytestmark = pytest.mark.django_db

CHANGE = reverse("auth-change-password")
LOGIN = reverse("auth-login")
LOGOUT = reverse("auth-logout")
ME = reverse("auth-me")

# Passes AUTH_PASSWORD_VALIDATORS for both fixture users.
NEW_PASSWORD = "Fresh-Lantern-42-Orbit"
REMEMBERED_SECONDS = REMEMBERED_SESSION_DAYS * 24 * 60 * 60
UNREMEMBERED_SECONDS = SESSION_INACTIVITY_MINUTES * 60

REQUIRED = ["This field is required."]
BLANK = ["This field may not be blank."]
NULL = ["This field may not be null."]


@pytest.fixture(params=ROLE_NAMES, ids=[name.lower() for name in ROLE_NAMES])
def account(request):
    """One user per role, so each test runs for an Employee and for an Administrator."""
    return request.getfixturevalue(request.param.lower())


@dataclass
class Clock:
    """The time Django reads, stopped, and moved only by ``advance()``, as in
    test_fr04_remember_me.py, whose docstring says why the clock is moved rather than the row."""

    now: datetime.datetime

    def read(self):
        return self.now

    def advance(self, **delta):
        self.now += datetime.timedelta(**delta)


@pytest.fixture
def clock(monkeypatch):
    clock = Clock(timezone.now())
    monkeypatch.setattr(timezone, "now", clock.read)
    return clock


def change(client, current_password=PASSWORD, new_password=NEW_PASSWORD, **headers):
    body = {"current_password": current_password, "new_password": new_password}
    return client.post(CHANGE, body, format="json", **headers)


def signed_in(user, *, remember=False, enforce_csrf=False):
    """A client signed in through POST /api/auth/login, as a browser is."""
    client = APIClient(enforce_csrf_checks=enforce_csrf)
    body = {"email": user.email, "password": PASSWORD, "remember": remember}
    assert client.post(LOGIN, body, format="json").status_code == 200
    return client


def login_with(user, password):
    """POST /api/auth/login for ``user`` with ``password``, from a client of its own."""
    return APIClient().post(LOGIN, {"email": user.email, "password": password}, format="json")


def session_key(client):
    return client.cookies[settings.SESSION_COOKIE_NAME].value


def replay(key):
    """A fresh client carrying nothing but a session cookie's value."""
    client = APIClient()
    client.cookies[settings.SESSION_COOKIE_NAME] = key
    return client


def csrf_header(client):
    return {"HTTP_X_CSRFTOKEN": client.cookies[settings.CSRF_COOKIE_NAME].value}


def stored_hash(user):
    return User.objects.get(pk=user.pk).password


def validator_messages(password, user):
    """What registration's AUTH_PASSWORD_VALIDATORS say about ``password`` for ``user``."""
    with pytest.raises(ValidationError) as refused:
        validate_password(password, user)
    return refused.value.messages


# --- A change ----------------------------------------------------------------------------------------


def test_a_change_is_200_and_the_new_password_signs_in_where_the_old_one_no_longer_does(session_client):
    user = session_client.user

    response = change(session_client.client)

    assert response.status_code == 200
    assert response.json() == {"detail": PASSWORD_CHANGED_MESSAGE}
    # FR-01's bcrypt, read before any sign-in, since a sign-in would upgrade another hash to it.
    assert stored_hash(user).startswith("bcrypt_sha256$")
    assert login_with(user, PASSWORD).status_code == 401
    assert login_with(user, NEW_PASSWORD).status_code == 200


def test_the_session_that_made_the_change_stays_signed_in_under_a_new_key(session_client):
    """update_session_auth_hash() cycles the key, keeping the data, so the old key names nothing. A
    session that was not remembered keeps FR-04's 60 minutes."""
    client = session_client.client
    before = session_key(client)

    response = change(client)

    assert response.status_code == 200
    assert session_key(client) != before
    assert not Session.objects.filter(session_key=before).exists()
    assert replay(before).get(ME).status_code == 401
    assert response.cookies[settings.SESSION_COOKIE_NAME]["max-age"] == UNREMEMBERED_SECONDS
    me = client.get(ME)
    assert me.status_code == 200
    assert me.json()["email"] == session_client.user.email


def test_every_other_session_of_the_user_ends_and_other_users_sessions_do_not(account):
    first = signed_in(account)
    second = signed_in(account)
    remembered = signed_in(account, remember=True)
    colleague = User.objects.create_user("colleague@example.com", PASSWORD, name="Casey Colleague")
    colleagues_session = signed_in(colleague)
    ended = [session_key(second), session_key(remembered)]

    assert change(first).status_code == 200

    assert first.get(ME).status_code == 200
    assert second.get(ME).status_code == 401
    assert remembered.get(ME).status_code == 401
    # Each was flushed on that request, so nothing is left to come back to.
    assert not Session.objects.filter(session_key__in=ended).exists()
    assert colleagues_session.get(ME).status_code == 200


def test_a_remembered_session_keeps_its_seven_days_through_a_change(clock, account):
    """D-137's "Remember me": the seven days are the session's data, which the cycled key keeps. So
    the session outlives 60 idle minutes after the change, and still ends seven idle days later."""
    client = signed_in(account, remember=True)

    response = change(client)

    assert response.status_code == 200
    assert response.cookies[settings.SESSION_COOKIE_NAME]["max-age"] == REMEMBERED_SECONDS
    row = Session.objects.get(session_key=session_key(client))
    assert row.expire_date == clock.now + datetime.timedelta(seconds=REMEMBERED_SECONDS)
    clock.advance(minutes=SESSION_INACTIVITY_MINUTES, seconds=1)
    assert client.get(ME).status_code == 200
    clock.advance(days=REMEMBERED_SESSION_DAYS, seconds=1)
    assert client.get(ME).status_code == 401


# --- The change touches the password alone -------------------------------------------------------


def test_a_locked_account_stays_locked_through_a_change(session_client):
    """D-26's residue: a lock does not end a session already open. A change made from that session,
    wrong current password or right, leaves FR-03's lock and count as they were, as D-137 has a
    completed reset leave them, and a sign-in with the new password still meets the lock."""
    client = session_client.client
    user = session_client.user
    locked_until = timezone.now() + datetime.timedelta(minutes=10)
    User.objects.filter(pk=user.pk).update(failed_attempts=LOCKOUT_THRESHOLD, locked_until=locked_until)

    assert change(client, current_password="Wrong-Guess-1!").status_code == 400
    assert change(client).status_code == 200

    user.refresh_from_db()
    assert (user.failed_attempts, user.locked_until) == (LOCKOUT_THRESHOLD, locked_until)
    assert user.check_password(NEW_PASSWORD)
    assert client.get(ME).status_code == 200
    refused = login_with(user, NEW_PASSWORD)
    assert refused.status_code == 403
    assert refused.json()["code"] == ACCOUNT_LOCKED_CODE


def test_a_role_change_committed_while_the_password_changes_is_not_written_back_over(
    session_client, monkeypatch
):
    """The user row was read when the request was authenticated. A role change by an Administrator
    and a count FR-02 wrote, committed while the request runs, must survive its save. Here both land
    after the current password is checked, as the validators run."""
    client = session_client.client
    account = session_client.user
    other_role = Role.objects.exclude(pk=account.role_id).get()
    real_validate_password = apps.api.serializers.validate_password

    def validate_after_a_concurrent_write(password, user=None, password_validators=None):
        User.objects.filter(pk=user.pk).update(role=other_role, failed_attempts=3)
        return real_validate_password(password, user=user, password_validators=password_validators)

    monkeypatch.setattr(apps.api.serializers, "validate_password", validate_after_a_concurrent_write)

    assert change(client).status_code == 200

    stored = User.objects.get(pk=account.pk)
    assert (stored.role_id, stored.failed_attempts) == (other_role.pk, 3)
    assert stored.check_password(NEW_PASSWORD)
    assert client.get(ME).json()["role"] == other_role.role_name


# --- 400: the current password ---------------------------------------------------------------------


def test_a_wrong_current_password_is_400_never_401_and_touches_no_counter(session_client):
    """One more wrong guess than the lockout threshold. None counts as a failed sign-in, so the
    account is not locked, and the session that sent them stays signed in. The count starts where an
    earlier failed sign-in left it, so a reset to zero would show as well as a rise."""
    client = session_client.client
    user = session_client.user
    User.objects.filter(pk=user.pk).update(failed_attempts=2)
    hash_before = stored_hash(user)

    for number in range(LOCKOUT_THRESHOLD + 1):
        response = change(client, current_password=f"Wrong-Guess-{number}!")
        assert response.status_code == 400, number
        assert response.json() == {"current_password": [CURRENT_PASSWORD_INCORRECT_MESSAGE]}

    user.refresh_from_db()
    assert (user.failed_attempts, user.locked_until) == (2, None)
    assert user.password == hash_before
    assert client.get(ME).status_code == 200
    assert login_with(user, PASSWORD).status_code == 200


def test_a_wrong_current_password_and_a_weak_new_one_are_named_together(session_client):
    weak = "abcdefg1!"

    response = change(session_client.client, current_password="Wrong-Guess-1!", new_password=weak)

    assert response.status_code == 400
    assert response.json() == {
        "current_password": [CURRENT_PASSWORD_INCORRECT_MESSAGE],
        "new_password": validator_messages(weak, session_client.user),
    }


def test_the_new_password_is_compared_with_the_current_one_only_once_that_is_verified(session_client):
    """A new password equal to a wrong current one is not "the current password", so it gets no
    unchanged-password message. Only the wrong current password is named."""
    guess = "Wrong-Guess-1!"

    response = change(session_client.client, current_password=guess, new_password=guess)

    assert response.status_code == 400
    assert response.json() == {"current_password": [CURRENT_PASSWORD_INCORRECT_MESSAGE]}


# --- 400: the new password ---------------------------------------------------------------------------


def _like_the_email(user):
    return user.email.capitalize() + "1"


def _like_the_name(user):
    return user.name.replace(" ", "") + "1!"


@pytest.mark.parametrize(
    "candidate",
    [
        lambda user: "Ab1!efg",
        lambda user: "abcdefg1!",
        lambda user: "Abcdefgh!",
        lambda user: "Lantern42Orbit",
        lambda user: "Password1!",
        _like_the_email,
        _like_the_name,
    ],
    ids=["too short", "no uppercase", "no number", "no special", "common", "like the email", "like the name"],
)
def test_a_new_password_registration_would_refuse_is_400_with_registrations_messages(
    session_client, candidate
):
    """FR-01's rules, as registration applies them: the 400 carries exactly what
    AUTH_PASSWORD_VALIDATORS say about the password for this user. The last two pass every rule but
    the similarity validator's, which only a check against this user's own name and address meets."""
    user = session_client.user
    new_password = candidate(user)
    expected = validator_messages(new_password, user)

    response = change(session_client.client, new_password=new_password)

    assert response.status_code == 400
    assert response.json() == {"new_password": expected}
    assert User.objects.get(pk=user.pk).check_password(PASSWORD)


def test_a_new_password_equal_to_the_current_one_is_400_and_changes_nothing(session_client):
    """Not re-hashed and not saved, so no other session ends either."""
    client = session_client.client
    user = session_client.user
    other_session = APIClient()
    other_session.force_login(user)
    hash_before = stored_hash(user)

    response = change(client, new_password=PASSWORD)

    assert response.status_code == 400
    assert response.json() == {"new_password": [NEW_PASSWORD_UNCHANGED_MESSAGE]}
    assert stored_hash(user) == hash_before
    assert other_session.get(ME).status_code == 200
    assert client.get(ME).status_code == 200


# --- 400: a field missing, blank or null -------------------------------------------------------------


@pytest.mark.parametrize(
    "body, errors",
    [
        ({}, {"current_password": REQUIRED, "new_password": REQUIRED}),
        ({"current_password": PASSWORD}, {"new_password": REQUIRED}),
        ({"new_password": NEW_PASSWORD}, {"current_password": REQUIRED}),
        ({"current_password": "", "new_password": ""}, {"current_password": BLANK, "new_password": BLANK}),
        ({"current_password": None, "new_password": None}, {"current_password": NULL, "new_password": NULL}),
    ],
    ids=["empty body", "no new password", "no current password", "blank", "null"],
)
def test_a_missing_blank_or_null_field_is_400_with_its_field_error(session_client, body, errors):
    response = session_client.client.post(CHANGE, body, format="json")

    assert response.status_code == 400
    assert response.json() == errors
    assert User.objects.get(pk=session_client.user.pk).check_password(PASSWORD)


# --- 401 and CSRF --------------------------------------------------------------------------------------


def test_no_session_is_401_and_changes_nothing(api_client, employee, administrator):
    response = change(api_client)

    assert response.status_code == 401
    assert response["WWW-Authenticate"] == "Session"
    for user in (employee, administrator):
        assert User.objects.get(pk=user.pk).check_password(PASSWORD)


def test_a_forged_session_is_401(api_client, employee):
    api_client.cookies[settings.SESSION_COOKIE_NAME] = "forged-session-key"

    assert change(api_client).status_code == 401
    assert User.objects.get(pk=employee.pk).check_password(PASSWORD)


def test_the_change_needs_the_csrf_header_as_every_unsafe_request_does(account):
    client = signed_in(account, enforce_csrf=True)

    refused = change(client)

    assert refused.status_code == 403
    assert "CSRF" in refused.json()["detail"]
    assert User.objects.get(pk=account.pk).check_password(PASSWORD)
    assert change(client, **csrf_header(client)).status_code == 200
    # The CSRF token is not rotated, so the page's next unsafe request still carries a good one.
    assert client.post(LOGOUT, **csrf_header(client)).status_code == 200
