"""The settings and wiring every Stage 2 endpoint relies on.

CLAUDE.md section 6 invariant 4 (401 without a session), docs/decisions.md D-21
(session-cookie authentication, IsAuthenticated by default) and FR-01's bcrypt.
"""

import pytest
from django.conf import settings
from django.contrib.auth.hashers import get_hasher, make_password
from django.urls import reverse

pytestmark = pytest.mark.django_db


# --- Global DRF defaults (D-21) ----------------------------------------------------------


def test_every_route_is_protected_unless_it_opts_out():
    assert settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] == [
        "rest_framework.permissions.IsAuthenticated"
    ]


def test_authentication_is_the_session_cookie():
    assert settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] == [
        "apps.api.authentication.SessionAuthentication"
    ]


def test_the_api_renders_json_only():
    assert settings.REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] == [
        "rest_framework.renderers.JSONRenderer"
    ]


def test_there_is_no_browsable_api(employee_client):
    # A client that accepts only HTML is refused, in JSON: nothing renders HTML.
    response = employee_client.get(reverse("api-root"), HTTP_ACCEPT="text/html")
    assert response.status_code == 406
    assert response["Content-Type"].startswith("application/json")


# --- The API root: 401 anonymously, reachable from either role ----------------------------


def test_api_root_is_401_anonymously(api_client):
    response = api_client.get(reverse("api-root"))
    assert response.status_code == 401
    assert response["WWW-Authenticate"] == "Session"
    assert response.json() == {"detail": "Authentication credentials were not provided."}


def test_api_root_is_reachable_from_a_session(session_client):
    assert session_client.client.get(reverse("api-root")).status_code == 200


# --- Password hashing (FR-01) --------------------------------------------------------------


def test_bcrypt_is_the_hasher_for_new_passwords():
    assert settings.PASSWORD_HASHERS[0] == "django.contrib.auth.hashers.BCryptSHA256PasswordHasher"
    assert get_hasher().algorithm == "bcrypt_sha256"
    assert make_password("correct horse battery staple").startswith("bcrypt_sha256$")


def test_the_four_default_password_validators_are_configured():
    names = [validator["NAME"].rsplit(".", 1)[1] for validator in settings.AUTH_PASSWORD_VALIDATORS]
    assert names == [
        "UserAttributeSimilarityValidator",
        "MinimumLengthValidator",
        "CommonPasswordValidator",
        "NumericPasswordValidator",
    ]
    assert settings.AUTH_PASSWORD_VALIDATORS[0]["OPTIONS"] == {"user_attributes": ["name", "email"]}


# --- Cookie flags (D-21) ---------------------------------------------------------------------


def test_session_cookie_is_http_only_and_same_site():
    assert settings.SESSION_COOKIE_HTTPONLY is True
    assert settings.SESSION_COOKIE_SAMESITE == "Lax"


def test_csrf_cookie_is_readable_by_the_front_end():
    assert settings.CSRF_COOKIE_HTTPONLY is False
    assert settings.CSRF_COOKIE_SAMESITE == "Lax"
