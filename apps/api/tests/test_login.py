"""FR-02 login: POST /api/auth/login, and GET /api/auth/me (docs/api-contract.md).

200 with the user object, the session cookie and the csrftoken cookie; 400 for a
malformed body; 401 with one generic message for an unknown address and a wrong
password alike (D-02). Side effects: failed_attempts, locked_until, last_login.
"""

import datetime

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.constants import ADMINISTRATOR_ROLE_NAME, LOCKOUT_DURATION, LOCKOUT_THRESHOLD
from conftest import PASSWORD

User = get_user_model()

pytestmark = pytest.mark.django_db

LOGIN = reverse("auth-login")
ME = reverse("auth-me")
INVALID = {"detail": "Invalid email or password."}
USER_OBJECT_KEYS = {"id", "name", "email", "role", "created_at"}
SECRET_COLUMNS = {"password", "password_hash", "failed_attempts", "locked_until", "last_login"}


def login(client, email, password=PASSWORD):
    return client.post(LOGIN, {"email": email, "password": password}, format="json")


# --- Happy path -------------------------------------------------------------------------------------


def test_login_returns_the_user_object(api_client, employee):
    response = login(api_client, employee.email)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == USER_OBJECT_KEYS
    assert body["id"] == str(employee.id)
    assert body["email"] == employee.email
    assert body["role"] == employee.role.role_name


def test_login_sets_the_session_and_csrf_cookies(api_client, employee):
    response = login(api_client, employee.email)
    session = response.cookies[settings.SESSION_COOKIE_NAME]
    csrf = response.cookies[settings.CSRF_COOKIE_NAME]
    assert session.value and csrf.value
    assert session["httponly"] is True
    assert session["samesite"] == "Lax"
    assert not csrf["httponly"]  # the front end reads it for X-CSRFToken


def test_the_session_cookie_authenticates_later_requests(employee):
    client = APIClient()
    login(client, employee.email)
    session_key = client.cookies[settings.SESSION_COOKIE_NAME].value

    # A fresh client carrying only that cookie value is the same session.
    replay = APIClient()
    replay.cookies[settings.SESSION_COOKIE_NAME] = session_key
    response = replay.get(ME)
    assert response.status_code == 200
    assert response.json()["id"] == str(employee.id)


def test_login_email_is_case_insensitive(api_client, employee):
    assert login(api_client, "  Employee@EXAMPLE.com ").status_code == 200


def test_login_works_for_an_administrator(api_client, administrator):
    response = login(api_client, administrator.email)
    assert response.status_code == 200
    assert response.json()["role"] == ADMINISTRATOR_ROLE_NAME


def test_login_response_never_exposes_secret_columns(api_client, employee):
    assert SECRET_COLUMNS.isdisjoint(login(api_client, employee.email).json())


# --- 401: one message, whichever half of the credential is wrong --------------------------------------


def test_unknown_email_is_401_with_the_generic_message(api_client, employee):
    response = login(api_client, "nobody@example.com")
    assert response.status_code == 401
    assert response.json() == INVALID
    assert settings.SESSION_COOKIE_NAME not in response.cookies


def test_wrong_password_is_401_with_the_same_message(api_client, employee):
    response = login(api_client, employee.email, "wrong password")
    assert response.status_code == 401
    assert response.json() == INVALID
    assert settings.SESSION_COOKIE_NAME not in response.cookies


def test_a_failed_login_does_not_authenticate(api_client, employee):
    login(api_client, employee.email, "wrong password")
    assert api_client.get(ME).status_code == 401


# --- 400 malformed body ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [{}, {"email": "employee@example.com"}, {"password": PASSWORD}, {"email": "", "password": ""}],
)
def test_malformed_login_body_is_400(api_client, employee, payload):
    response = api_client.post(LOGIN, payload, format="json")
    assert response.status_code == 400
    assert set(response.json()) <= {"email", "password"}


# --- Side effects (docs/api-contract.md "Login side effects") --------------------------------------------


def test_a_failed_attempt_increments_failed_attempts(api_client, employee):
    login(api_client, employee.email, "wrong password")
    employee.refresh_from_db()
    assert employee.failed_attempts == 1
    assert employee.locked_until is None


def test_the_threshold_failure_sets_locked_until(api_client, employee):
    employee.failed_attempts = LOCKOUT_THRESHOLD - 1
    employee.save(update_fields=["failed_attempts"])

    before = timezone.now()
    login(api_client, employee.email, "wrong password")
    after = timezone.now()

    employee.refresh_from_db()
    assert employee.failed_attempts == LOCKOUT_THRESHOLD
    assert before + LOCKOUT_DURATION <= employee.locked_until <= after + LOCKOUT_DURATION


def test_a_success_resets_failed_attempts_and_sets_last_login(api_client, employee):
    employee.failed_attempts = LOCKOUT_THRESHOLD - 2
    employee.save(update_fields=["failed_attempts"])
    assert employee.last_login is None

    before = timezone.now()
    assert login(api_client, employee.email).status_code == 200

    employee.refresh_from_db()
    assert employee.failed_attempts == 0
    assert employee.last_login is not None
    assert before <= employee.last_login <= timezone.now()


def test_an_unknown_email_records_nothing(api_client, employee):
    before = User.objects.count()
    login(api_client, "nobody@example.com")
    employee.refresh_from_db()
    assert employee.failed_attempts == 0
    assert User.objects.count() == before


def test_a_locked_account_can_still_log_in_with_the_right_password(api_client, employee):
    # docs/api-contract.md: "Enforcing the lock is FR-03 (NIT3004) and is not part of
    # Stage 2." FR-02 records locked_until; nothing in Stage 2 reads it.
    employee.failed_attempts = LOCKOUT_THRESHOLD
    employee.locked_until = timezone.now() + LOCKOUT_DURATION
    employee.save(update_fields=["failed_attempts", "locked_until"])

    assert login(api_client, employee.email).status_code == 200
    employee.refresh_from_db()
    assert employee.failed_attempts == 0


# --- GET /api/auth/me ------------------------------------------------------------------------------------


def test_me_is_401_anonymously(api_client):
    response = api_client.get(ME)
    assert response.status_code == 401
    assert response["WWW-Authenticate"] == "Session"


def test_me_with_a_forged_session_cookie_is_401(api_client, employee):
    api_client.cookies[settings.SESSION_COOKIE_NAME] = "not-a-session-key"
    assert api_client.get(ME).status_code == 401


def test_me_returns_the_session_user(session_client):
    response = session_client.client.get(ME)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == USER_OBJECT_KEYS
    assert body["id"] == str(session_client.user.id)
    assert body["role"] == session_client.role_name
    assert SECRET_COLUMNS.isdisjoint(body)


def test_me_refreshes_the_csrf_cookie(session_client):
    response = session_client.client.get(ME)
    assert response.cookies[settings.CSRF_COOKIE_NAME].value


def test_me_reads_the_role_from_the_database_on_every_request(employee_client, employee, administrator_role):
    # Nothing about the role is cached in the session (D-21).
    employee.role = administrator_role
    employee.save(update_fields=["role"])
    assert employee_client.get(ME).json()["role"] == ADMINISTRATOR_ROLE_NAME


def test_a_cross_site_form_post_cannot_sign_a_browser_in(api_client, employee):
    """Login CSRF (security review, Stage 2 item 7). A hidden cross-site form
    posting valid credentials would have signed the victim's browser into the
    attacker's account, and SameSite=Lax does not help because it governs when a
    cookie is sent, not when one is set. JSON-only parsing refuses the form body
    before any credential is read."""
    response = api_client.post(
        LOGIN, data={"email": employee.email, "password": PASSWORD}
    )  # urlencoded, as an HTML form sends
    assert response.status_code == 415
    assert "sessionid" not in response.cookies
