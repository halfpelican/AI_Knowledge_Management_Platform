"""FR-04 logout and session management: POST /api/auth/logout and the session's
60-minute inactivity expiry (docs/decisions.md D-10, D-21).

The proof the FR asks for: a session cookie replayed after logout gets 401 and
its django_session row is gone. These tests use real login and logout requests
with CSRF enforced, exactly as the browser does it.

FR-04 Responses: "200 OK on success" (D-25). It was 204 before.
"""

import datetime

import pytest
from django.conf import settings
from django.contrib.sessions.models import Session
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.constants import SESSION_INACTIVITY_MINUTES
from conftest import PASSWORD

pytestmark = pytest.mark.django_db

LOGIN = reverse("auth-login")
LOGOUT = reverse("auth-logout")
ME = reverse("auth-me")


def browser_login(user):
    """A client that enforces CSRF like a browser would, logged in over HTTP."""
    client = APIClient(enforce_csrf_checks=True)
    response = client.post(LOGIN, {"email": user.email, "password": PASSWORD}, format="json")
    assert response.status_code == 200
    return client


def csrf_header(client):
    return {"HTTP_X_CSRFTOKEN": client.cookies[settings.CSRF_COOKIE_NAME].value}


def replay(session_key):
    client = APIClient()
    client.cookies[settings.SESSION_COOKIE_NAME] = session_key
    return client


# --- Logout ------------------------------------------------------------------------------------------


def test_logout_invalidates_the_session_server_side(employee):
    client = browser_login(employee)
    session_key = client.cookies[settings.SESSION_COOKIE_NAME].value
    assert Session.objects.filter(session_key=session_key).exists()
    assert replay(session_key).get(ME).status_code == 200

    response = client.post(LOGOUT, **csrf_header(client))

    assert response.status_code == 200
    assert response.json() == {"detail": "You have been logged out."}
    # The cookie value the client kept no longer names anything on the server.
    assert replay(session_key).get(ME).status_code == 401
    assert not Session.objects.filter(session_key=session_key).exists()


def test_logout_tells_the_browser_to_drop_the_cookie(employee):
    client = browser_login(employee)
    response = client.post(LOGOUT, **csrf_header(client))
    assert response.cookies[settings.SESSION_COOKIE_NAME]["max-age"] == 0


def test_logout_from_either_role(session_client):
    response = session_client.client.post(LOGOUT)
    assert response.status_code == 200
    assert response.json() == {"detail": "You have been logged out."}
    assert session_client.client.get(ME).status_code == 401


def test_logout_answers_json_not_an_empty_body(session_client):
    """FR-04 says 200, not 204, so there is a body; the front end shows the
    confirmation the FR names rather than inventing one for an empty response."""
    response = session_client.client.post(LOGOUT)
    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/json")
    assert response.content


def test_logout_is_401_anonymously(api_client):
    response = api_client.post(LOGOUT)
    assert response.status_code == 401
    assert response["WWW-Authenticate"] == "Session"


def test_logout_needs_the_csrf_header(employee):
    # Unsafe methods carry X-CSRFToken (D-21); without it the session is untouched.
    client = browser_login(employee)
    session_key = client.cookies[settings.SESSION_COOKIE_NAME].value
    response = client.post(LOGOUT)
    assert response.status_code == 403
    assert "CSRF" in response.json()["detail"]
    assert Session.objects.filter(session_key=session_key).exists()


def test_logging_out_one_session_leaves_another_alone(employee):
    first = browser_login(employee)
    second = browser_login(employee)
    first.post(LOGOUT, **csrf_header(first))
    assert second.get(ME).status_code == 200


# --- Inactivity expiry (D-10) --------------------------------------------------------------------------


def test_session_age_is_the_inactivity_window():
    assert settings.SESSION_COOKIE_AGE == SESSION_INACTIVITY_MINUTES * 60
    assert settings.SESSION_SAVE_EVERY_REQUEST is True


def test_an_expired_session_is_401(session_client):
    client = session_client.client
    session_key = client.cookies[settings.SESSION_COOKIE_NAME].value
    assert client.get(ME).status_code == 200

    # The clock has moved past the last activity plus the window.
    Session.objects.filter(session_key=session_key).update(
        expire_date=timezone.now() - datetime.timedelta(seconds=1)
    )

    assert client.get(ME).status_code == 401


def test_each_request_restarts_the_inactivity_clock(employee_client):
    session_key = employee_client.cookies[settings.SESSION_COOKIE_NAME].value
    nearly_expired = timezone.now() + datetime.timedelta(seconds=30)
    Session.objects.filter(session_key=session_key).update(expire_date=nearly_expired)

    before = timezone.now()
    assert employee_client.get(ME).status_code == 200

    expire_date = Session.objects.get(session_key=session_key).expire_date
    window = datetime.timedelta(seconds=settings.SESSION_COOKIE_AGE)
    assert before + window <= expire_date <= timezone.now() + window
