"""Self-service password reset by an emailed link (D-137): ``POST /api/auth/password-reset`` and
``POST /api/auth/password-reset/confirm``.

D-137 (Benjamin Morovan, lead, 16 November 2026) overrules the proposal's section 1.9, which listed
"Self-service password reset flow" as out of scope. FR-03 is unchanged. What this file holds, each
from D-137, from the values the build was given, or from a rule the project already has:

- **Asking for a link.** A missing or malformed address is a 400. Every well-formed address gets the
  same 200 and the same body, whether or not an account uses it (D-25), and only an account gets an
  email: one plain-text message to its stored address, carrying
  ``{PUBLIC_BASE_URL}/reset-password?uid=...&token=...``, and saying that the link works once, within
  60 minutes, and that the password is unchanged for someone who did not ask. The link's host is
  PUBLIC_BASE_URL's, whatever the request's Host header says. An account gets at most one email in
  300 seconds, silently. A locked account may still ask. A retired one (an unusable password, D-89)
  is sent nothing.
- **The request does the same work either way.** On a server the email is sent from a daemon thread:
  the request path looks nothing up and answers without waiting for it. A failure to send is logged
  and changes nothing in the answer. At most MAXIMUM_PASSWORD_RESET_EMAILS_IN_FLIGHT threads run at
  once.
- **Using the link.** It sets the new password, which must pass registration's validators for that
  account, and answers 200. A bad uid, a wrong, expired or used token and an unknown account are one
  400 with one message. A link works for 60 minutes and once, even for two confirms at once. Every
  session of the account ends, remembered ones included. Nobody is signed in, and FR-03's lock and
  count are left as they were.
- **The settings.** The file outbox is the default, and SMTP is used once EMAIL_HOST is set, on port
  587 with TLS. TLS and SSL together stop the settings loading. PUBLIC_BASE_URL is read from the
  environment and must be an absolute http or https address.

The ``auth`` throttle on both routes is tested with the other scopes in
``apps/api/tests/test_throttles.py``. The suite sends the email inline (conftest.py's
``password_reset_emails_send_inline``). The tests under "On a server" put it back on a thread and
join every thread they start, and the two that need a thread to read committed rows are marked
``transaction=True``, as apps/api/tests/test_login_concurrency.py's are, for the reason its docstring
gives. Every test about an account runs once for an Employee's and once for an Administrator's.
"""

from __future__ import annotations

import datetime
import logging
import smtplib
import threading
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import PasswordResetTokenGenerator, default_token_generator
from django.contrib.sessions.models import Session
from django.core.cache.backends import locmem
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import connection, connections
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import base36_to_int, int_to_base36, urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework.test import APIClient

from apps.accounts import password_reset
from apps.accounts.models import Role
from apps.api.tests.test_production_settings import load_settings
from apps.api.views import (
    ACCOUNT_LOCKED_CODE,
    PASSWORD_RESET_COMPLETE_MESSAGE,
    PASSWORD_RESET_LINK_REFUSED_MESSAGE,
    PASSWORD_RESET_REQUESTED_MESSAGE,
)
from apps.core.constants import (
    EMAIL_TIMEOUT_SECONDS,
    LOCKOUT_THRESHOLD,
    MAXIMUM_PASSWORD_RESET_EMAILS_IN_FLIGHT,
    PASSWORD_RESET_COOLDOWN_SECONDS,
    PASSWORD_RESET_LINK_MINUTES,
    REMEMBERED_SESSION_DAYS,
    ROLE_NAMES,
)
from conftest import PASSWORD

User = get_user_model()

pytestmark = pytest.mark.django_db

REQUEST = reverse("auth-password-reset")
CONFIRM = reverse("auth-password-reset-confirm")
LOGIN = reverse("auth-login")
ME = reverse("auth-me")

# Each passes AUTH_PASSWORD_VALIDATORS for both fixture users.
NEW_PASSWORD = "Fresh-Lantern-42-Orbit"
OTHER_PASSWORD = "Second-Harbour-77-Kite"
UNKNOWN_ADDRESS = "nobody@example.com"
LINK_SECONDS = PASSWORD_RESET_LINK_MINUTES * 60
REFUSED_LINK = {"detail": PASSWORD_RESET_LINK_REFUSED_MESSAGE}

REQUIRED = ["This field is required."]
BLANK = ["This field may not be blank."]
NULL = ["This field may not be null."]

# The longest a thread test waits for something that must happen before it fails instead.
PATIENCE = 30
_real_time = time.time


@pytest.fixture(params=ROLE_NAMES, ids=[name.lower() for name in ROLE_NAMES])
def account(request):
    """One user per role, so each test runs for an Employee's account and an Administrator's."""
    return request.getfixturevalue(request.param.lower())


# --- Helpers ------------------------------------------------------------------------------------


def ask(email, client=None, **extra):
    """POST /api/auth/password-reset for ``email``, from a client of its own unless one is given."""
    return (client or APIClient()).post(REQUEST, {"email": email}, format="json", **extra)


def confirm(uid, token, new_password=NEW_PASSWORD, client=None):
    body = {"uid": uid, "token": token, "new_password": new_password}
    return (client or APIClient()).post(CONFIRM, body, format="json")


def link_in(message) -> str:
    """The email's one line that is the link."""
    [link] = [line for line in message.body.splitlines() if "/reset-password?" in line]
    return link


def parameters_of(link) -> dict:
    """The link's uid and token, each given once and nothing else given."""
    query = parse_qs(urlsplit(link).query, strict_parsing=True)
    assert set(query) == {"uid", "token"}, query
    assert all(len(values) == 1 for values in query.values()), query
    return {name: values[0] for name, values in query.items()}


def mailed_link(account, mailoutbox) -> dict:
    """Ask for a reset for ``account`` and return the uid and token of the one email it is sent."""
    before = len(mailoutbox)
    assert ask(account.email).status_code == 200
    assert len(mailoutbox) == before + 1
    message = mailoutbox[-1]
    assert message.to == [account.email]
    return parameters_of(link_in(message))


def uid_of(user) -> str:
    return urlsafe_base64_encode(force_bytes(user.pk))


def stored(user):
    return User.objects.get(pk=user.pk)


def signed_in(user, *, remember=False, enforce_csrf=False):
    """A client signed in through POST /api/auth/login, as a browser is."""
    client = APIClient(enforce_csrf_checks=enforce_csrf)
    body = {"email": user.email, "password": PASSWORD, "remember": remember}
    assert client.post(LOGIN, body, format="json").status_code == 200
    return client


def login_with(user, password):
    return APIClient().post(LOGIN, {"email": user.email, "password": password}, format="json")


def session_key(client):
    return client.cookies[settings.SESSION_COOKIE_NAME].value


def csrf_header(client):
    return {"HTTP_X_CSRFTOKEN": client.cookies[settings.CSRF_COOKIE_NAME].value}


def validator_messages(password, user):
    """What registration's AUTH_PASSWORD_VALIDATORS say about ``password`` for ``user``."""
    with pytest.raises(ValidationError) as refused:
        validate_password(password, user)
    return refused.value.messages


@dataclass
class TokenClock:
    """The time the token generator reads, stopped, and moved only by ``advance()``. Its own clock is
    naive local time, ``datetime.now()``, which its ``_now`` exists to let a test replace."""

    now: datetime.datetime

    def read(self, generator=None):
        return self.now

    def advance(self, **delta):
        self.now += datetime.timedelta(**delta)


@pytest.fixture
def token_clock(monkeypatch):
    clock = TokenClock(datetime.datetime.now())
    monkeypatch.setattr(PasswordResetTokenGenerator, "_now", clock.read)
    return clock


class LaterTime:
    """``time`` as LocMemCache reads it to decide whether an entry has expired, ``seconds`` ahead.

    Only that reading moves. The expiry was stamped by the base cache class, which reads the real
    clock, so an entry made now is seen as expired once ``seconds`` passes its timeout."""

    def __init__(self, seconds):
        self.seconds = seconds

    def time(self):
        return _real_time() + self.seconds


def move_the_cache_clock(monkeypatch, seconds):
    monkeypatch.setattr(locmem, "time", LaterTime(seconds))


def reset_threads():
    return [thread for thread in threading.enumerate() if thread.name == password_reset.THREAD_NAME]


def join_reset_threads():
    """Join every reset email thread. One still running after PATIENCE fails the test."""
    for thread in reset_threads():
        thread.join(PATIENCE)
    assert reset_threads() == [], "a reset email thread outlived its test"


# --- Asking for a link: the answer ---------------------------------------------------------------


def test_an_account_and_an_unknown_address_get_the_same_200_and_only_the_account_an_email(
    account, mailoutbox
):
    """D-25: the answer must not tell an anonymous caller whether an address is registered."""
    for_the_account = ask(account.email)
    for_nobody = ask(UNKNOWN_ADDRESS)

    assert for_the_account.status_code == for_nobody.status_code == 200
    assert for_the_account.content == for_nobody.content
    assert for_the_account["Content-Type"] == for_nobody["Content-Type"]
    assert for_the_account.json() == {"detail": PASSWORD_RESET_REQUESTED_MESSAGE}
    assert [message.to for message in mailoutbox] == [[account.email]]


def test_the_address_is_matched_as_login_matches_it_and_mailed_as_stored(account, mailoutbox):
    """Trimmed and lower-cased (D-02). The email goes to the stored address, never to the one typed."""
    response = ask(f"  {account.email.upper()}  ")

    assert response.status_code == 200
    assert response.json() == {"detail": PASSWORD_RESET_REQUESTED_MESSAGE}
    assert [message.to for message in mailoutbox] == [[account.email]]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"email": ""},
        {"email": None},
        {"email": "not-an-address"},
        {"email": "two@at@example.com"},
        {"email": f"{'a' * 250}@example.com"},
        {"email": "employee\u0000@example.com"},
    ],
    ids=["no field", "blank", "null", "no at sign", "two at signs", "longer than the column", "a NUL"],
)
def test_a_missing_or_malformed_address_is_a_400_and_sends_nothing(employee, mailoutbox, body):
    response = APIClient().post(REQUEST, body, format="json")

    assert response.status_code == 400
    assert set(response.json()) == {"email"}
    assert mailoutbox == []


# --- Asking for a link: the email ----------------------------------------------------------------


def test_the_email_is_one_plain_text_message_with_the_link_and_what_it_means(account, mailoutbox, settings):
    settings.DEFAULT_FROM_EMAIL = "platform@example.edu.au"

    assert ask(account.email).status_code == 200

    [message] = mailoutbox
    assert message.subject == password_reset.EMAIL_SUBJECT
    assert message.from_email == "platform@example.edu.au"
    assert message.to == [account.email]
    assert (message.cc, message.bcc, message.attachments) == ([], [], [])
    assert message.content_subtype == "plain"
    assert getattr(message, "alternatives", []) == []
    link = link_in(message)
    assert link.startswith(f"{settings.PUBLIC_BASE_URL}/reset-password?uid=")
    assert link.index("uid=") < link.index("&token=")
    carried = parameters_of(link)
    assert uuid.UUID(urlsafe_base64_decode(carried["uid"]).decode()) == account.pk
    assert carried["uid"] == uid_of(account)
    assert default_token_generator.check_token(account, carried["token"])
    assert "The link works once" in message.body
    assert f"within {PASSWORD_RESET_LINK_MINUTES} minutes" in message.body
    assert "your password is unchanged" in message.body


def test_the_link_is_built_from_public_base_url_never_from_the_request(account, mailoutbox, settings):
    """D-137: a link built from the Host header would mail a victim a working link to someone else's
    site. The Host here is one ALLOWED_HOSTS admits, so the request is served, and still unused."""
    settings.PUBLIC_BASE_URL = "https://kmp.example.edu.au"
    settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, "attacker.example"]

    response = ask(
        account.email, HTTP_HOST="attacker.example", HTTP_X_FORWARDED_HOST="attacker.example", secure=True
    )

    assert response.status_code == 200
    [message] = mailoutbox
    assert link_in(message).startswith("https://kmp.example.edu.au/reset-password?uid=")
    assert "attacker.example" not in message.body


def test_the_file_outbox_writes_the_email_to_a_file(account, settings, tmp_path):
    """The default backend, as D-137 has it: the email is a file in EMAIL_FILE_PATH, link and all."""
    settings.EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
    settings.EMAIL_FILE_PATH = tmp_path / "outbox"

    assert ask(account.email).status_code == 200

    [written] = list((tmp_path / "outbox").iterdir())
    text = written.read_text(encoding="utf-8")
    assert f"To: {account.email}" in text
    assert f"{settings.PUBLIC_BASE_URL}/reset-password?uid={uid_of(account)}&token=" in text


# --- Asking for a link: who is sent one ----------------------------------------------------------


def test_an_account_is_sent_one_email_in_300_seconds_and_the_answer_never_says_so(
    account, mailoutbox, monkeypatch
):
    """The cooldown is silent: inside it the answer is byte for byte the one any address gets."""
    nobody = ask(UNKNOWN_ADDRESS).content
    assert ask(account.email).content == nobody
    assert ask(account.email).content == nobody
    assert len(mailoutbox) == 1

    move_the_cache_clock(monkeypatch, PASSWORD_RESET_COOLDOWN_SECONDS - 10)
    assert ask(account.email).content == nobody
    assert len(mailoutbox) == 1

    move_the_cache_clock(monkeypatch, PASSWORD_RESET_COOLDOWN_SECONDS + 1)
    assert ask(account.email).content == nobody
    assert [message.to for message in mailoutbox] == [[account.email], [account.email]]


def test_the_cooldown_is_each_accounts_own(employee, administrator, mailoutbox):
    assert ask(employee.email).status_code == 200
    assert ask(administrator.email).status_code == 200

    assert sorted(message.to[0] for message in mailoutbox) == sorted([employee.email, administrator.email])


def test_a_locked_account_may_still_ask_for_a_link(account, mailoutbox):
    User.objects.filter(pk=account.pk).update(
        failed_attempts=LOCKOUT_THRESHOLD, locked_until=timezone.now() + datetime.timedelta(minutes=10)
    )

    assert ask(account.email).status_code == 200

    assert [message.to for message in mailoutbox] == [[account.email]]


def test_an_account_retired_with_an_unusable_password_is_sent_nothing(account, mailoutbox):
    """D-89 retires an account by making its password unusable, since users have no is_active. A
    link would bring it back, so none is sent, as Django's own reset form sends none."""
    account.set_unusable_password()
    account.save(update_fields=["password"])

    response = ask(account.email)

    assert response.status_code == 200
    assert response.content == ask(UNKNOWN_ADDRESS).content
    assert mailoutbox == []


def test_a_failure_to_send_is_logged_and_the_answer_is_unchanged(account, mailoutbox, monkeypatch, error_log_file):
    """Inline, as here, a failure that reached the response would tell a registered address from an
    unknown one. It is logged with its traceback and nothing else happens."""

    def server_gone(*args, **kwargs):
        raise smtplib.SMTPServerDisconnected("the mail server went away")

    monkeypatch.setattr(password_reset, "send_mail", server_gone)

    response = ask(account.email)

    assert response.status_code == 200
    assert response.content == ask(UNKNOWN_ADDRESS).content
    assert mailoutbox == []
    logged = error_log_file.read_text(encoding="utf-8")
    assert "A password reset email could not be sent" in logged
    assert "the mail server went away" in logged


def test_a_browser_holding_a_session_sends_the_csrf_header_on_both_routes_as_on_login(account, mailoutbox):
    """The same CSRF handling as login and registration: none for an anonymous request, and DRF's
    check from X-CSRFToken for a request carrying a session."""
    browser = signed_in(account, enforce_csrf=True)
    dead_link = {"uid": "x", "token": "y", "new_password": NEW_PASSWORD}

    for refused in (
        browser.post(REQUEST, {"email": account.email}, format="json"),
        browser.post(CONFIRM, dead_link, format="json"),
    ):
        assert refused.status_code == 403
        assert "CSRF" in refused.json()["detail"]
    assert mailoutbox == []

    assert browser.post(REQUEST, {"email": account.email}, format="json", **csrf_header(browser)).status_code == 200
    assert browser.post(CONFIRM, dead_link, format="json", **csrf_header(browser)).json() == REFUSED_LINK
    assert len(mailoutbox) == 1

    anonymous = APIClient(enforce_csrf_checks=True)
    assert anonymous.post(REQUEST, {"email": UNKNOWN_ADDRESS}, format="json").status_code == 200
    assert anonymous.post(CONFIRM, dead_link, format="json").json() == REFUSED_LINK


# --- Using the link ------------------------------------------------------------------------------


def test_the_mailed_link_sets_the_new_password_and_answers_200(account, mailoutbox):
    link = mailed_link(account, mailoutbox)

    response = confirm(**link)

    assert response.status_code == 200
    assert response.json() == {"detail": PASSWORD_RESET_COMPLETE_MESSAGE}
    # FR-01's bcrypt, read before any sign-in, since a sign-in would upgrade another hash to it.
    assert stored(account).password.startswith("bcrypt_sha256$")
    assert login_with(account, PASSWORD).status_code == 401
    assert login_with(account, NEW_PASSWORD).status_code == 200


def test_a_link_works_once(account, mailoutbox):
    link = mailed_link(account, mailoutbox)
    assert confirm(**link).status_code == 200

    again = confirm(**link, new_password=OTHER_PASSWORD)

    assert again.status_code == 400
    assert again.json() == REFUSED_LINK
    assert stored(account).check_password(NEW_PASSWORD)


def test_a_link_still_works_60_minutes_after_it_was_made(account, mailoutbox, token_clock):
    link = mailed_link(account, mailoutbox)
    token_clock.advance(seconds=LINK_SECONDS)

    assert confirm(**link).status_code == 200
    assert stored(account).check_password(NEW_PASSWORD)


def test_a_link_has_expired_a_second_after_60_minutes(account, mailoutbox, token_clock):
    link = mailed_link(account, mailoutbox)
    token_clock.advance(seconds=LINK_SECONDS + 1)

    response = confirm(**link)

    assert response.status_code == 400
    assert response.json() == REFUSED_LINK
    assert stored(account).check_password(PASSWORD)


def _not_base64(account, token):
    return "!!not*base64!!", token


def _not_a_uuid(account, token):
    return urlsafe_base64_encode(b"not-a-uuid"), token


def _nobodys_uuid(account, token):
    return urlsafe_base64_encode(force_bytes(uuid.uuid4())), token


def _a_wrong_token(account, token):
    return uid_of(account), f"{token.split('-')[0]}-{'0' * 32}"


def _a_token_with_no_dash(account, token):
    return uid_of(account), token.replace("-", "")


def _a_token_with_its_time_moved_on(account, token):
    stamp, signature = token.split("-")
    return uid_of(account), f"{int_to_base36(base36_to_int(stamp) + LINK_SECONDS)}-{signature}"


def _another_accounts_token(account, token):
    other = User.objects.create_user("colleague@example.com", PASSWORD, name="Casey Colleague")
    return uid_of(account), default_token_generator.make_token(other)


def _another_accounts_uid(account, token):
    other = User.objects.create_user("colleague@example.com", PASSWORD, name="Casey Colleague")
    return uid_of(other), token


@pytest.mark.parametrize(
    "spoil",
    [
        _not_base64,
        _not_a_uuid,
        _nobodys_uuid,
        _a_wrong_token,
        _a_token_with_no_dash,
        _a_token_with_its_time_moved_on,
        _another_accounts_token,
        _another_accounts_uid,
    ],
    ids=[
        "uid not base64",
        "uid not a UUID",
        "uid of no account",
        "wrong token",
        "token with no dash",
        "token with its time moved on",
        "another account's token",
        "another account's uid",
    ],
)
def test_every_link_that_does_not_work_is_the_one_400_and_changes_nothing(account, mailoutbox, spoil):
    link = mailed_link(account, mailoutbox)
    uid, token = spoil(account, link["token"])

    response = confirm(uid, token)

    assert response.status_code == 400
    assert response.json() == REFUSED_LINK
    assert stored(account).check_password(PASSWORD)
    # A refused link spoils nothing: the real one still works.
    assert confirm(**link).status_code == 200


def test_an_account_retired_after_its_link_was_made_can_use_no_link(account, mailoutbox):
    """Retiring an account makes its password unusable, which ends the link it was mailed. A token made
    for the account as it now is, which only the server could make, is refused too: a reset must not
    bring a retired account back (D-89)."""
    link = mailed_link(account, mailoutbox)
    account.set_unusable_password()
    account.save(update_fields=["password"])

    assert confirm(**link).json() == REFUSED_LINK
    made_now = confirm(uid_of(account), default_token_generator.make_token(account))

    assert made_now.status_code == 400
    assert made_now.json() == REFUSED_LINK
    assert not stored(account).has_usable_password()


def _like_the_email(user):
    return user.email.capitalize() + "1"


def _like_the_name(user):
    return user.name.replace(" ", "") + "1!"


@pytest.mark.parametrize(
    "candidate",
    [
        lambda user: "Ab1!efg",
        lambda user: "abcdefg1!",
        lambda user: "Lantern42Orbit",
        lambda user: "Password1!",
        _like_the_email,
        _like_the_name,
    ],
    ids=["too short", "no uppercase", "no special", "common", "like the email", "like the name"],
)
def test_a_new_password_registration_would_refuse_is_a_400_on_it_and_the_link_still_works(
    account, mailoutbox, candidate
):
    """FR-01's rules, as registration applies them, for the account the link names: the last two pass
    every rule but the similarity validator's, which only a check against this account meets."""
    link = mailed_link(account, mailoutbox)
    new_password = candidate(account)
    expected = validator_messages(new_password, account)

    response = confirm(**link, new_password=new_password)

    assert response.status_code == 400
    assert response.json() == {"new_password": expected}
    assert stored(account).check_password(PASSWORD)
    assert confirm(**link).status_code == 200


def test_the_new_password_is_taken_as_typed_spaces_and_all(account, mailoutbox):
    """As registration, login and the password change take a password: never trimmed."""
    spaced = f"  {NEW_PASSWORD}  "
    link = mailed_link(account, mailoutbox)

    assert confirm(**link, new_password=spaced).status_code == 200

    assert login_with(account, spaced).status_code == 200
    assert login_with(account, NEW_PASSWORD).status_code == 401


def test_a_link_that_does_not_work_is_refused_before_the_new_password_is_judged(account):
    response = confirm(uid_of(account), "1-nothing", new_password="weak")

    assert response.status_code == 400
    assert response.json() == REFUSED_LINK


@pytest.mark.parametrize(
    "body, errors",
    [
        ({}, {"uid": REQUIRED, "token": REQUIRED, "new_password": REQUIRED}),
        ({"uid": "", "token": "", "new_password": ""}, {"uid": BLANK, "token": BLANK, "new_password": BLANK}),
        ({"uid": None, "token": None, "new_password": None}, {"uid": NULL, "token": NULL, "new_password": NULL}),
    ],
    ids=["empty body", "blank", "null"],
)
def test_a_missing_blank_or_null_field_is_a_400_with_its_field_error(employee, body, errors):
    response = APIClient().post(CONFIRM, body, format="json")

    assert response.status_code == 400
    assert response.json() == errors
    assert stored(employee).check_password(PASSWORD)


# --- What a reset does, and does not do ------------------------------------------------------------


def test_a_reset_ends_every_session_of_the_account_remembered_ones_included(account, mailoutbox):
    """D-137. Each session holds a hash of the old password, so each is flushed on its next request,
    which is a 401. Another user's session is not touched. The sign-ins come first, since a sign-in
    after the link was made would end the link."""
    plain = signed_in(account)
    remembered = signed_in(account, remember=True)
    colleague = User.objects.create_user("colleague@example.com", PASSWORD, name="Casey Colleague")
    colleagues_session = signed_in(colleague)
    ended = [session_key(plain), session_key(remembered)]
    remembered_until = Session.objects.get(session_key=session_key(remembered)).expire_date
    assert remembered_until > timezone.now() + datetime.timedelta(days=REMEMBERED_SESSION_DAYS - 1)
    assert plain.get(ME).status_code == 200
    assert remembered.get(ME).status_code == 200
    link = mailed_link(account, mailoutbox)

    assert confirm(**link).status_code == 200

    assert plain.get(ME).status_code == 401
    assert remembered.get(ME).status_code == 401
    assert not Session.objects.filter(session_key__in=ended).exists()
    assert colleagues_session.get(ME).status_code == 200


def test_a_reset_signs_nobody_in(account, mailoutbox):
    link = mailed_link(account, mailoutbox)
    client = APIClient()
    sessions_before = Session.objects.count()

    response = confirm(**link, client=client)

    assert response.status_code == 200
    assert settings.SESSION_COOKIE_NAME not in response.cookies
    assert client.get(ME).status_code == 401
    assert Session.objects.count() == sessions_before


def test_a_reset_leaves_the_lock_and_the_count_as_they_were(account, mailoutbox):
    """D-137: "No, the lock stays." A locked account can ask and reset, and the new password then meets
    the lock's 403 at sign-in, as FR-03 has it, until the lock ends or an Administrator releases it."""
    locked_until = timezone.now() + datetime.timedelta(minutes=10)
    User.objects.filter(pk=account.pk).update(failed_attempts=LOCKOUT_THRESHOLD, locked_until=locked_until)
    link = mailed_link(account, mailoutbox)

    assert confirm(**link).status_code == 200

    after = stored(account)
    assert (after.failed_attempts, after.locked_until) == (LOCKOUT_THRESHOLD, locked_until)
    assert after.check_password(NEW_PASSWORD)
    refused = login_with(account, NEW_PASSWORD)
    assert refused.status_code == 403
    assert refused.json()["code"] == ACCOUNT_LOCKED_CODE


def test_a_role_change_committed_while_the_password_is_reset_is_not_written_back_over(
    account, mailoutbox, monkeypatch
):
    """The account's row was read when the link was judged. A role change and a count FR-02 wrote,
    committed after that, as the validators run, must survive the save: the password column alone is
    written."""
    link = mailed_link(account, mailoutbox)
    other_role = Role.objects.exclude(pk=account.role_id).get()
    real_validate_password = password_reset.validate_password

    def validate_after_a_concurrent_write(password, user=None, password_validators=None):
        User.objects.filter(pk=user.pk).update(role=other_role, failed_attempts=3)
        return real_validate_password(password, user=user, password_validators=password_validators)

    monkeypatch.setattr(password_reset, "validate_password", validate_after_a_concurrent_write)

    assert confirm(**link).status_code == 200

    after = stored(account)
    assert (after.role_id, after.failed_attempts) == (other_role.pk, 3)
    assert after.check_password(NEW_PASSWORD)


def test_a_link_used_by_another_confirm_after_this_one_judged_it_is_refused(account, mailoutbox, monkeypatch):
    """The token is checked again on the row read under the lock, before the save. Here the other
    confirm commits after this one judged the link, as the validators run, so this one finds a
    password the token no longer matches."""
    link = mailed_link(account, mailoutbox)
    real_validate_password = password_reset.validate_password

    def validate_after_the_other_confirm_commits(password, user=None, password_validators=None):
        User.objects.filter(pk=user.pk).update(password=make_password(OTHER_PASSWORD))
        return real_validate_password(password, user=user, password_validators=password_validators)

    monkeypatch.setattr(password_reset, "validate_password", validate_after_the_other_confirm_commits)

    response = confirm(**link)

    assert response.status_code == 400
    assert response.json() == REFUSED_LINK
    assert stored(account).check_password(OTHER_PASSWORD)


class ConfirmThread(threading.Thread):
    """One confirm in a thread of its own, with its own client and so its own database connection,
    closed when the request ends. What the request raised is kept for ``finish``."""

    def __init__(self, name, uid, token, new_password):
        super().__init__(name=f"confirm-{name}", daemon=True)
        self.uid, self.token, self.new_password = uid, token, new_password
        self.response = None
        self.error: BaseException | None = None

    def run(self):
        try:
            self.response = confirm(self.uid, self.token, self.new_password)
        except BaseException as error:  # re-raised in the test's own thread by finish()
            self.error = error
        finally:
            connections.close_all()


def finish(*threads):
    started = [thread for thread in threads if thread.ident is not None]
    for thread in started:
        thread.join(PATIENCE)
    stuck = [thread.name for thread in started if thread.is_alive()]
    assert not stuck, f"still running after {PATIENCE}s: {stuck}"
    for thread in started:
        if thread.error is not None:
            raise thread.error


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_two_confirms_with_one_link_at_once_set_one_password(account, monkeypatch):
    """A link works once even for two confirms at once. A judges the link and is held inside its
    transaction, on the row it locked, after its second check and before its save. B then judges the
    same link good, since A has not committed, and must wait for A's row lock. Released, A commits,
    and B, checking again on the row as A left it, is refused.

    Without the row lock B would check the old row, save over A and answer 200 while A was held: the
    one wait for something that must not happen, two seconds, is for B to finish in that time."""
    uid, token = uid_of(account), default_token_generator.make_token(account)
    calls = Counter()
    a_holds_the_row, release_a, b_judged_the_link = threading.Event(), threading.Event(), threading.Event()
    real_generator = default_token_generator

    class HeldGenerator:
        def make_token(self, user):
            return real_generator.make_token(user)

        def check_token(self, user, token):
            result = real_generator.check_token(user, token)
            name = threading.current_thread().name
            calls[name] += 1
            if name == "confirm-A" and calls[name] == 2:  # the check made under the row lock
                a_holds_the_row.set()
                if not release_a.wait(PATIENCE):
                    raise AssertionError("the test never released the first confirm")
            if name == "confirm-B" and calls[name] == 1 and result:
                b_judged_the_link.set()
            return result

    monkeypatch.setattr(password_reset, "default_token_generator", HeldGenerator())
    first = ConfirmThread("A", uid, token, NEW_PASSWORD)
    second = ConfirmThread("B", uid, token, OTHER_PASSWORD)
    try:
        first.start()
        assert a_holds_the_row.wait(PATIENCE), "the first confirm never reached its second check"
        second.start()
        assert b_judged_the_link.wait(PATIENCE), "the second confirm never judged the link good"
        second.join(2)
        assert second.is_alive(), "the second confirm finished while the first held the account's row"
    finally:
        release_a.set()
        finish(first, second)

    assert first.response.status_code == 200
    assert second.response.status_code == 400
    assert second.response.json() == REFUSED_LINK
    assert stored(account).check_password(NEW_PASSWORD)


# --- On a server: the email goes from a thread ----------------------------------------------------


def test_on_a_server_the_request_looks_nothing_up_and_answers_while_its_thread_works(
    settings, monkeypatch, account, mailoutbox
):
    """D-25's timing, on the request path: for an account and for an unknown address alike, the
    request runs no query and hands the address to a daemon thread, and both are answered while their
    threads are still at work. The thread's work is held on an Event, so nothing is timed."""
    settings.PASSWORD_RESET_EMAIL_RUNNER = password_reset.THREAD_RUNNER
    entered, release = threading.Semaphore(0), threading.Event()
    seen = []

    def held(email):
        seen.append((email, threading.current_thread()))
        entered.release()
        if not release.wait(PATIENCE):
            raise AssertionError("the test never released the thread")
        return False

    monkeypatch.setattr(password_reset, "send_reset_email", held)
    try:
        with CaptureQueriesContext(connection) as queries:
            for_the_account = ask(account.email.upper())
            for_nobody = ask(UNKNOWN_ADDRESS)
        assert for_the_account.status_code == for_nobody.status_code == 200
        assert for_the_account.content == for_nobody.content
        assert len(queries) == 0, [query["sql"] for query in queries]
        assert entered.acquire(timeout=PATIENCE) and entered.acquire(timeout=PATIENCE)
        assert sorted(email for email, _ in seen) == sorted([account.email, UNKNOWN_ADDRESS])
        for _, thread in seen:
            assert thread is not threading.current_thread()
            assert thread.name == password_reset.THREAD_NAME
            assert thread.daemon is True  # it dies with the server rather than holding it open
            assert thread.is_alive()
        assert password_reset.emails_in_flight() == 2
        assert mailoutbox == []
    finally:
        release.set()
        join_reset_threads()
    assert password_reset.emails_in_flight() == 0


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_on_a_server_the_thread_finds_the_account_and_sends_its_email_after_the_answer(
    settings, monkeypatch, account, mailoutbox
):
    """The thread's real work, through its own database connection: it finds the account and sends
    the email. The send is held, so the answer is seen to arrive first, with nothing sent."""
    settings.PASSWORD_RESET_EMAIL_RUNNER = password_reset.THREAD_RUNNER
    sending, release = threading.Event(), threading.Event()
    real_send_mail = password_reset.send_mail

    def held_send_mail(*args, **kwargs):
        sending.set()
        if not release.wait(PATIENCE):
            raise AssertionError("the test never released the send")
        return real_send_mail(*args, **kwargs)

    monkeypatch.setattr(password_reset, "send_mail", held_send_mail)
    try:
        response = ask(account.email)
        assert response.status_code == 200
        assert response.json() == {"detail": PASSWORD_RESET_REQUESTED_MESSAGE}
        assert sending.wait(PATIENCE), "the thread never reached the send"
        assert mailoutbox == []
    finally:
        release.set()
        join_reset_threads()

    [message] = mailoutbox
    assert message.to == [account.email]
    assert confirm(**parameters_of(link_in(message))).status_code == 200


def test_no_more_than_the_limit_of_reset_emails_are_worked_on_at_once(settings, monkeypatch, caplog):
    """A request past MAXIMUM_PASSWORD_RESET_EMAILS_IN_FLIGHT starts no thread and is logged, and its
    answer is every other's. Once the threads end, their places are free again."""
    settings.PASSWORD_RESET_EMAIL_RUNNER = password_reset.THREAD_RUNNER
    entered, release = threading.Semaphore(0), threading.Event()

    def held(email):
        entered.release()
        if not release.wait(PATIENCE):
            raise AssertionError("the test never released the threads")
        return False

    monkeypatch.setattr(password_reset, "send_reset_email", held)
    limit = MAXIMUM_PASSWORD_RESET_EMAILS_IN_FLIGHT
    try:
        answers = [ask(f"person{number}@example.com") for number in range(limit)]
        for _ in range(limit):
            assert entered.acquire(timeout=PATIENCE), "fewer threads than the limit started"
        with caplog.at_level(logging.ERROR, logger=password_reset.__name__):
            past_the_limit = ask("one-more@example.com")
        assert past_the_limit.status_code == 200
        assert past_the_limit.content == answers[0].content
        assert len(reset_threads()) == limit
        assert password_reset.emails_in_flight() == limit
        assert f"A password reset email was not started: {limit} were already in flight" in caplog.text
    finally:
        release.set()
        join_reset_threads()
    assert password_reset.emails_in_flight() == 0

    assert ask("after-the-others@example.com").status_code == 200
    assert entered.acquire(timeout=PATIENCE), "no thread started once the places were free"
    join_reset_threads()


def test_on_a_server_a_thread_that_fails_is_logged_frees_its_place_and_closes_its_connection(
    settings, monkeypatch, error_log_file
):
    """Django opens a database connection per thread and closes it only at the end of a request,
    which a thread never reaches, so the thread closes its own, after a failure as after a success."""
    settings.PASSWORD_RESET_EMAIL_RUNNER = password_reset.THREAD_RUNNER
    closed_in = []
    real_connections = password_reset.connections

    class Connections:
        def close_all(self):
            closed_in.append(threading.current_thread())
            real_connections.close_all()

    def fails(email):
        raise RuntimeError("the email could not be built")

    monkeypatch.setattr(password_reset, "connections", Connections())
    monkeypatch.setattr(password_reset, "send_reset_email", fails)

    assert ask(UNKNOWN_ADDRESS).status_code == 200
    join_reset_threads()

    assert password_reset.emails_in_flight() == 0
    assert [thread.name for thread in closed_in] == [password_reset.THREAD_NAME]
    logged = error_log_file.read_text(encoding="utf-8")
    assert "A password reset email could not be sent" in logged
    assert "the email could not be built" in logged


# --- The settings --------------------------------------------------------------------------------

EMAIL_VARIABLES = (
    "EMAIL_HOST",
    "EMAIL_PORT",
    "EMAIL_HOST_USER",
    "EMAIL_HOST_PASSWORD",
    "EMAIL_USE_TLS",
    "EMAIL_USE_SSL",
    "EMAIL_TIMEOUT",
    "EMAIL_FILE_PATH",
    "DEFAULT_FROM_EMAIL",
    "PUBLIC_BASE_URL",
)


def load_email_settings(monkeypatch, **environment):
    """``config/settings.py`` executed afresh, as test_production_settings.py's ``load_settings`` does,
    with every email variable unset first, then ``environment`` set."""
    for name in EMAIL_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    return load_settings(monkeypatch, **environment)


def test_without_email_host_each_email_is_a_file_in_the_outbox(monkeypatch):
    loaded = load_email_settings(monkeypatch)

    assert loaded.EMAIL_BACKEND == "django.core.mail.backends.filebased.EmailBackend"
    assert loaded.EMAIL_FILE_PATH == Path(settings.BASE_DIR) / "outbox"
    assert loaded.DEFAULT_FROM_EMAIL == "no-reply@localhost"
    assert loaded.PUBLIC_BASE_URL == "http://127.0.0.1:8000"
    assert loaded.PASSWORD_RESET_TIMEOUT == LINK_SECONDS == 3600
    assert loaded.PASSWORD_RESET_EMAIL_RUNNER == password_reset.THREAD_RUNNER
    # The outbox is gitignored, as media/ and logs/ are.
    ignored = (Path(settings.BASE_DIR) / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "outbox/" in ignored


def test_with_email_host_set_email_goes_by_smtp_on_587_with_tls(monkeypatch):
    loaded = load_email_settings(
        monkeypatch,
        EMAIL_HOST="smtp.example.edu.au",
        EMAIL_HOST_USER="platform@example.edu.au",
        EMAIL_HOST_PASSWORD="placeholder-not-a-secret",
    )

    assert loaded.EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend"
    assert loaded.EMAIL_HOST == "smtp.example.edu.au"
    assert loaded.EMAIL_PORT == 587
    assert (loaded.EMAIL_USE_TLS, loaded.EMAIL_USE_SSL) == (True, False)
    assert loaded.EMAIL_HOST_USER == "platform@example.edu.au"
    assert loaded.EMAIL_HOST_PASSWORD == "placeholder-not-a-secret"
    assert loaded.EMAIL_TIMEOUT == EMAIL_TIMEOUT_SECONDS


def test_smtp_over_ssl_is_ssl_on_with_tls_turned_off(monkeypatch):
    loaded = load_email_settings(
        monkeypatch,
        EMAIL_HOST="smtp.example.edu.au",
        EMAIL_PORT="465",
        EMAIL_USE_TLS="False",
        EMAIL_USE_SSL="True",
        EMAIL_TIMEOUT="12",
    )

    assert (loaded.EMAIL_PORT, loaded.EMAIL_USE_TLS, loaded.EMAIL_USE_SSL) == (465, False, True)
    assert loaded.EMAIL_TIMEOUT == 12


@pytest.mark.parametrize(
    "environment",
    [{"EMAIL_USE_SSL": "True"}, {"EMAIL_USE_TLS": "True", "EMAIL_USE_SSL": "True"}],
    ids=["SSL with TLS left on by default", "both set"],
)
def test_tls_and_ssl_together_stop_the_settings_loading(monkeypatch, environment):
    with pytest.raises(ImproperlyConfigured, match="EMAIL_USE_TLS and EMAIL_USE_SSL cannot both be true"):
        load_email_settings(monkeypatch, EMAIL_HOST="smtp.example.edu.au", **environment)


def test_the_outbox_the_sender_and_the_public_address_are_read_from_the_environment(monkeypatch, tmp_path):
    loaded = load_email_settings(
        monkeypatch,
        EMAIL_FILE_PATH=str(tmp_path / "mail"),
        DEFAULT_FROM_EMAIL="Platform <platform@example.edu.au>",
        PUBLIC_BASE_URL="https://kmp.example.edu.au/",
    )

    assert loaded.EMAIL_FILE_PATH == tmp_path / "mail"
    assert loaded.DEFAULT_FROM_EMAIL == "Platform <platform@example.edu.au>"
    assert loaded.PUBLIC_BASE_URL == "https://kmp.example.edu.au"  # its trailing slash dropped


@pytest.mark.parametrize(
    "value",
    [
        "kmp.example.edu.au",
        "ftp://kmp.example.edu.au",
        "https://",
        "https://kmp.example.edu.au/?next=home",
        "https://kmp.example.edu.au/#top",
    ],
    ids=["no scheme", "not http", "no host", "a query", "a fragment"],
)
def test_a_public_base_url_no_link_can_start_with_stops_the_settings_loading(monkeypatch, value):
    with pytest.raises(ImproperlyConfigured, match="PUBLIC_BASE_URL"):
        load_email_settings(monkeypatch, PUBLIC_BASE_URL=value)
