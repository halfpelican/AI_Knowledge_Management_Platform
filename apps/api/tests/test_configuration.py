"""The settings and wiring every Stage 2 endpoint relies on.

CLAUDE.md section 6 invariant 4 (401 without a session), docs/decisions.md D-21
(session-cookie authentication, IsAuthenticated by default) and FR-01's bcrypt.
"""

import pytest
from django.conf import settings
from django.contrib.auth.hashers import get_hasher, make_password
from django.urls import reverse

from apps.core.constants import PASSWORD_MINIMUM_LENGTH
from conftest import PASSWORD

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
    assert make_password(PASSWORD).startswith("bcrypt_sha256$")


def test_the_password_validators_are_djangos_four_plus_fr_01_complexity():
    # D-25: FR-01 states "min 8 chars, 1 uppercase, 1 number, 1 special character",
    # and none of Django's defaults check a character class.
    names = [validator["NAME"].rsplit(".", 1)[1] for validator in settings.AUTH_PASSWORD_VALIDATORS]
    assert names == [
        "UserAttributeSimilarityValidator",
        "MinimumLengthValidator",
        "CommonPasswordValidator",
        "NumericPasswordValidator",
        "ComplexityValidator",
    ]
    assert settings.AUTH_PASSWORD_VALIDATORS[0]["OPTIONS"] == {"user_attributes": ["name", "email"]}


def test_the_minimum_length_is_stated_once():
    """MinimumLengthValidator and ComplexityValidator both check the length, so they
    read the same constant; a literal in either would let them disagree."""
    minimum_length = settings.AUTH_PASSWORD_VALIDATORS[1]["OPTIONS"]["min_length"]
    assert minimum_length == PASSWORD_MINIMUM_LENGTH == 8

    from apps.accounts.validators import ComplexityValidator

    assert ComplexityValidator().minimum_length == PASSWORD_MINIMUM_LENGTH


# --- Cookie flags (D-21) ---------------------------------------------------------------------


def test_session_cookie_is_http_only_and_same_site():
    assert settings.SESSION_COOKIE_HTTPONLY is True
    assert settings.SESSION_COOKIE_SAMESITE == "Lax"


def test_csrf_cookie_is_readable_by_the_front_end():
    assert settings.CSRF_COOKIE_HTTPONLY is False
    assert settings.CSRF_COOKIE_SAMESITE == "Lax"


def test_the_api_parses_json_only():
    """docs/api-contract.md says JSON bodies. The form parsers are also the login
    CSRF vector (security review, Stage 2 item 7): DRF never checks CSRF on an
    anonymous request, so an HTML form from another origin could post credentials."""
    from rest_framework.settings import api_settings

    assert [cls.__name__ for cls in api_settings.DEFAULT_PARSER_CLASSES] == ["JSONParser"]


# --- The anonymous endpoints are rate limited (D-26) -------------------------------------------


def _set_auth_rate(monkeypatch, rate):
    """DRF binds THROTTLE_RATES to a class attribute at import, so overriding the
    setting has no effect on an already-imported throttle. Patch the attribute."""
    from rest_framework.throttling import ScopedRateThrottle

    monkeypatch.setattr(
        ScopedRateThrottle, "THROTTLE_RATES", {**ScopedRateThrottle.THROTTLE_RATES, "auth": rate}
    )


@pytest.mark.django_db
def test_login_is_rate_limited_per_client(api_client, monkeypatch):
    """With FR-02's lockout enforced, an unthrottled login is a denial-of-service
    primitive: five requests lock any account, and registration's mandatory 409
    identifies which addresses exist. Nothing in the product releases a lock, so
    every account could be held locked indefinitely by anyone."""
    from django.core.cache import cache
    from django.urls import reverse

    _set_auth_rate(monkeypatch, "3/min")
    cache.clear()
    url = reverse("auth-login")
    body = {"email": "nobody@example.com", "password": "Wrong-Password-1!"}

    statuses = [api_client.post(url, body, format="json").status_code for _ in range(4)]

    assert statuses[:3] == [401, 401, 401]
    assert statuses[3] == 429


@pytest.mark.django_db
def test_registration_is_rate_limited_per_client(api_client, monkeypatch):
    """The same throttle scope covers the address oracle that feeds the attack."""
    from django.core.cache import cache
    from django.urls import reverse

    _set_auth_rate(monkeypatch, "2/min")
    cache.clear()
    url = reverse("auth-register")

    statuses = [
        api_client.post(
            url,
            {"name": "A Person", "email": f"person{index}@example.com", "password": "Str0ng-Pass!"},
            format="json",
        ).status_code
        for index in range(3)
    ]

    assert statuses[:2] == [201, 201]
    assert statuses[2] == 429


def test_the_authenticated_routes_are_not_throttled():
    """Only the two anonymous endpoints carry the scope; a signed-in user browsing
    the repository must not be rate limited by an auth throttle."""
    from apps.api import views

    assert views.LoginView.throttle_scope == views.RegisterView.throttle_scope == "auth"
    for view in (views.LogoutView, views.MeView, views.RoleListView, views.UserListView):
        assert not getattr(view, "throttle_classes", [])
