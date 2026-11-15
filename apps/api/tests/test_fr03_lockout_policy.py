"""FR-03's configuration clause, made true by D-130 decision 7: "threshold and lockout duration are
configuration values rather than literals, so the policy can be tightened without code changes."

- **The settings.** ``config/settings.py`` reads ``LOCKOUT_THRESHOLD`` and
  ``LOCKOUT_DURATION_MINUTES`` from .env, defaulting to ``apps/core/constants.py``'s values, and
  refuses to start on a value under 1.
- **Login follows them** at request time: the lock, its length, ``retry_after`` and D-26's notice
  ceiling, which is a multiple of the threshold.
- **``GET /api/auth/lockout-policy`` gives them to the sign-in page,** so a change needs no
  front-end rebuild. It is anonymous and the same for every caller, so it discloses nothing about
  any account. It is asked here anonymously, as an Employee and as an Administrator.

Each test changes the running values through pytest-django's ``settings`` fixture, which is what
a different .env gives a restarted server.
"""

import importlib.util
from datetime import timedelta
from pathlib import Path

import environ
import pytest
from django.conf import settings as live_settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse
from django.utils import timezone

from apps.core.constants import LOCKOUT_DURATION, LOCKOUT_NOTICE_CEILING_FACTOR, LOCKOUT_THRESHOLD
from conftest import PASSWORD

User = get_user_model()

pytestmark = pytest.mark.django_db

LOGIN = reverse("auth-login")
POLICY = reverse("auth-lockout-policy")
WRONG_PASSWORD = "Wrong-Horse-9-Battery"
SETTINGS_FILE = Path(live_settings.BASE_DIR) / "config" / "settings.py"
POLICY_VARIABLES = ("LOCKOUT_THRESHOLD", "LOCKOUT_DURATION_MINUTES")


def login(client, email, password):
    return client.post(LOGIN, {"email": email, "password": password}, format="json")


def load_settings(monkeypatch, **environment):
    """``config/settings.py`` executed as a new module, as test_production_settings.py does: .env
    not read, the two policy variables unset, then ``environment`` set. Nothing here touches the
    live settings."""
    for name in POLICY_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SECRET_KEY", "settings-under-test")
    monkeypatch.setenv("DATABASE_URL", "postgres://user:password@127.0.0.1:5432/no_such_database")
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(environ.Env, "read_env", staticmethod(lambda *args, **kwargs: None))
    spec = importlib.util.spec_from_file_location("lockout_settings_under_test", SETTINGS_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- The settings ------------------------------------------------------------------------------


def test_the_policy_defaults_to_the_constants(monkeypatch):
    loaded = load_settings(monkeypatch)

    assert loaded.LOCKOUT_THRESHOLD == LOCKOUT_THRESHOLD
    assert loaded.LOCKOUT_DURATION == LOCKOUT_DURATION


def test_the_policy_is_read_from_the_environment(monkeypatch):
    """Tightening the policy is a .env change, not a code change (FR-03, D-130 decision 7)."""
    loaded = load_settings(monkeypatch, LOCKOUT_THRESHOLD="3", LOCKOUT_DURATION_MINUTES="30")

    assert loaded.LOCKOUT_THRESHOLD == 3
    assert loaded.LOCKOUT_DURATION == timedelta(minutes=30)


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        # Under 1: a threshold of 0 would lock every account before its first attempt.
        ("LOCKOUT_THRESHOLD", "0"),
        ("LOCKOUT_THRESHOLD", "-1"),
        # Looser than NFR-04: the policy may only be tightened (decision 8).
        ("LOCKOUT_THRESHOLD", "6"),
        ("LOCKOUT_DURATION_MINUTES", "14"),
        ("LOCKOUT_DURATION_MINUTES", "0"),
        # Longer than 365 days, including one that would overflow a timedelta or the lock's
        # timestamp at the threshold failure (the final security review, M1).
        ("LOCKOUT_DURATION_MINUTES", "525601"),
        ("LOCKOUT_DURATION_MINUTES", "9999999999"),
        ("LOCKOUT_DURATION_MINUTES", "99999999999999"),
        # Not a whole number (the final security review, I1).
        ("LOCKOUT_THRESHOLD", "three"),
        ("LOCKOUT_DURATION_MINUTES", "15.5"),
    ],
)
def test_a_policy_outside_its_bounds_refuses_to_start(monkeypatch, variable, value):
    with pytest.raises(ImproperlyConfigured, match=variable):
        load_settings(monkeypatch, **{variable: value})


@pytest.mark.parametrize(
    ("threshold", "minutes"),
    [("1", "15"), ("5", "15"), ("5", "525600"), ("3", "60")],
)
def test_a_policy_at_or_inside_its_bounds_starts(monkeypatch, threshold, minutes):
    loaded = load_settings(monkeypatch, LOCKOUT_THRESHOLD=threshold, LOCKOUT_DURATION_MINUTES=minutes)

    assert loaded.LOCKOUT_THRESHOLD == int(threshold)
    assert loaded.LOCKOUT_DURATION == timedelta(minutes=int(minutes))


# --- Login follows the running values ----------------------------------------------------------


def test_login_locks_at_the_running_threshold_for_the_running_duration(api_client, employee, settings):
    settings.LOCKOUT_THRESHOLD = 3
    settings.LOCKOUT_DURATION = timedelta(minutes=20)

    for _ in range(2):
        assert login(api_client, employee.email, WRONG_PASSWORD).status_code == 401
    employee.refresh_from_db()
    assert employee.locked_until is None

    before = timezone.now()
    assert login(api_client, employee.email, WRONG_PASSWORD).status_code == 401
    after = timezone.now()
    employee.refresh_from_db()
    assert employee.failed_attempts == 3
    assert before + timedelta(minutes=20) <= employee.locked_until <= after + timedelta(minutes=20)

    locked = login(api_client, employee.email, PASSWORD)
    assert locked.status_code == 403
    # Longer than the default 15 minutes, so the running duration is what set it.
    assert 900 < locked.json()["retry_after"] <= 1200


def test_the_notice_ceiling_follows_the_running_threshold(api_client, employee, settings):
    """D-26: past twice the threshold, even the right password gets the generic 401."""
    settings.LOCKOUT_THRESHOLD = 2
    # The ceiling below is four attempts: the factor times the running threshold.
    assert settings.LOCKOUT_THRESHOLD * LOCKOUT_NOTICE_CEILING_FACTOR == 4

    for _ in range(2):
        login(api_client, employee.email, WRONG_PASSWORD)
    # Attempts three and four are within the ceiling, so the right password gets the notice.
    assert login(api_client, employee.email, PASSWORD).status_code == 403
    assert login(api_client, employee.email, PASSWORD).status_code == 403
    # The fifth attempt passes it: the right password gets the 401, as for anyone.
    assert login(api_client, employee.email, PASSWORD).status_code == 401


# --- GET /api/auth/lockout-policy --------------------------------------------------------------


def test_the_policy_route_gives_the_running_values_to_an_anonymous_caller(api_client, settings):
    settings.LOCKOUT_THRESHOLD = 4
    settings.LOCKOUT_DURATION = timedelta(minutes=20)

    response = api_client.get(POLICY)

    assert response.status_code == 200
    assert response.json() == {"lockout_threshold": 4, "lockout_duration_seconds": 1200}


def test_the_policy_route_defaults_to_the_constants(api_client):
    response = api_client.get(POLICY)

    assert response.json() == {
        "lockout_threshold": LOCKOUT_THRESHOLD,
        "lockout_duration_seconds": int(LOCKOUT_DURATION.total_seconds()),
    }


def test_the_policy_route_answers_every_caller_alike(api_client, session_client):
    """Anonymous, Employee and Administrator get the same two numbers: nothing in it depends on
    who asks, so it says nothing about any account."""
    anonymous = api_client.get(POLICY)
    signed_in = session_client.client.get(POLICY)

    assert signed_in.status_code == anonymous.status_code == 200
    assert signed_in.content == anonymous.content


def test_the_policy_route_is_read_only(api_client):
    # POST, PUT, PATCH and DELETE are refused. HEAD and OPTIONS answer 200, as on every DRF view:
    # HEAD as GET, and OPTIONS with DRF's metadata, which names the view and quotes its docstring
    # (the final security review, I2).
    for method in ("post", "put", "patch", "delete"):
        assert getattr(api_client, method)(POLICY, {}, format="json").status_code == 405, method
    assert api_client.head(POLICY).status_code == 200
    assert api_client.options(POLICY).status_code == 200
