"""Stage 5 item 9: the alpha's production settings (D-64), and JSON 400 and 500 under /api/.

**The settings.** D-64 has ``ALLOWED_HOSTS``, ``CSRF_TRUSTED_ORIGINS``, ``SESSION_COOKIE_SECURE``
and ``CSRF_COOKIE_SECURE`` read from the environment and defaulting to the loopback values, and
item 9 adds ``SPA_DIST_DIR``. The live settings carry whatever the developer's ``.env`` says, so
the defaults are read by executing ``config/settings.py`` afresh with ``.env`` not read and those
variables unset (``load_settings``).

**The error pages.** Under ``DEBUG=False`` Django answers an unhandled exception through
``handler500`` and a disallowed ``Host`` through ``handler400``, both HTML by default. Under
``/api/`` they are ``{"detail": "..."}`` now (config/errors.py); outside it they are Django's own
pages, unchanged. The test client re-raises a view's exception unless it is built with
``raise_request_exception=False``, which is what lets a 500 reach the handler here.
"""

import importlib.util
from pathlib import Path

import environ
import pytest
from django.conf import settings
from django.test import Client

from apps.api import views
from config.errors import BAD_REQUEST_MESSAGE, SERVER_ERROR_MESSAGE

SETTINGS_FILE = Path(settings.BASE_DIR) / "config" / "settings.py"

DEPLOYMENT_VARIABLES = (
    "DEBUG",
    "ALLOWED_HOSTS",
    "CSRF_TRUSTED_ORIGINS",
    "SESSION_COOKIE_SECURE",
    "CSRF_COOKIE_SECURE",
    "SPA_DIST_DIR",
)

# What add_never_cache_headers sets (D-76), as test_never_cache.py states it.
NEVER_CACHE_DIRECTIVES = {"max-age=0", "no-cache", "no-store", "must-revalidate", "private"}

A_SECRET_IN_THE_EXCEPTION = "connection string postgres://kmp:hunter2@db"


def load_settings(monkeypatch, **environment):
    """``config/settings.py`` executed as a new module: ``.env`` not read, the deployment
    variables unset, then ``environment`` set. SECRET_KEY and DATABASE_URL have no default, so
    they are given placeholders. Nothing here touches the live settings."""
    for name in DEPLOYMENT_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SECRET_KEY", "settings-under-test")
    monkeypatch.setenv("DATABASE_URL", "postgres://user:password@127.0.0.1:5432/no_such_database")
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(environ.Env, "read_env", staticmethod(lambda *args, **kwargs: None))
    spec = importlib.util.spec_from_file_location("settings_under_test", SETTINGS_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- The settings (D-64) ------------------------------------------------------------------------


def test_the_deployment_settings_default_to_the_loopback_values(monkeypatch):
    loaded = load_settings(monkeypatch)

    assert loaded.DEBUG is False
    assert loaded.ALLOWED_HOSTS == ["127.0.0.1", "localhost"]
    assert loaded.CSRF_TRUSTED_ORIGINS == ["http://127.0.0.1:8000", "http://localhost:8000"]
    # Plain HTTP on loopback: no Secure flag on either cookie.
    assert loaded.SESSION_COOKIE_SECURE is False
    assert loaded.CSRF_COOKIE_SECURE is False
    assert loaded.SPA_DIST_DIR == Path(settings.BASE_DIR) / "frontend" / "dist"
    assert loaded.WHITENOISE_ROOT == loaded.SPA_DIST_DIR


def test_each_deployment_setting_is_read_from_the_environment(monkeypatch, tmp_path):
    """Serving the same build over HTTPS later is a .env change, not a code change (D-64)."""
    build = tmp_path / "build"
    loaded = load_settings(
        monkeypatch,
        DEBUG="True",
        ALLOWED_HOSTS="kmp.example.edu.au",
        CSRF_TRUSTED_ORIGINS="https://kmp.example.edu.au",
        SESSION_COOKIE_SECURE="True",
        CSRF_COOKIE_SECURE="True",
        SPA_DIST_DIR=str(build),
    )

    assert loaded.DEBUG is True
    assert loaded.ALLOWED_HOSTS == ["kmp.example.edu.au"]
    assert loaded.CSRF_TRUSTED_ORIGINS == ["https://kmp.example.edu.au"]
    assert loaded.SESSION_COOKIE_SECURE is True
    assert loaded.CSRF_COOKIE_SECURE is True
    assert loaded.SPA_DIST_DIR == build
    assert loaded.WHITENOISE_ROOT == build


def test_debug_set_in_the_shell_overrides_debug_in_dotenv(monkeypatch, tmp_path):
    """The runbook's premise: the repository's .env says DEBUG=True, and ``$env:DEBUG='False'``
    set before waitress-serve wins, because reading .env never overwrites a variable already set."""
    dotenv = tmp_path / ".env"
    dotenv.write_text("DEBUG=True\n", encoding="utf-8")
    monkeypatch.setenv("DEBUG", "False")

    environ.Env.read_env(str(dotenv))

    assert environ.Env().bool("DEBUG") is False


# --- handler500 ---------------------------------------------------------------------------------


def raise_inside_the_view(*args, **kwargs):
    raise RuntimeError(A_SECRET_IN_THE_EXCEPTION)


@pytest.mark.django_db
def test_an_unhandled_error_under_the_api_is_a_json_500(session_client, monkeypatch, settings, error_log_file):
    settings.DEBUG = False
    monkeypatch.setattr(views.DashboardView, "get", raise_inside_the_view)
    client = Client(raise_request_exception=False)
    client.force_login(session_client.user)

    response = client.get("/api/dashboard")

    assert response.status_code == 500
    assert response["Content-Type"] == "application/json"
    assert response.json() == {"detail": SERVER_ERROR_MESSAGE}
    assert A_SECRET_IN_THE_EXCEPTION.encode() not in response.content
    # Still marked never-cache like every other /api/ response (D-76).
    directives = {directive.strip() for directive in response["Cache-Control"].split(",")}
    assert directives == NEVER_CACHE_DIRECTIVES
    # The traceback went to the error file instead (D-75).
    logged = error_log_file.read_text(encoding="utf-8")
    assert "Internal Server Error: /api/dashboard" in logged
    assert A_SECRET_IN_THE_EXCEPTION in logged


@pytest.mark.django_db
def test_an_unhandled_error_outside_the_api_is_still_djangos_html_500(api_client, settings, tmp_path):
    """index.html as a folder: reading it raises an OSError other than FileNotFoundError, which
    config.spa.index lets through, so the catch-all fails the way any view might."""
    settings.DEBUG = False
    broken = tmp_path / "dist"
    (broken / "index.html").mkdir(parents=True)
    settings.SPA_DIST_DIR = broken
    client = Client(raise_request_exception=False)

    response = client.get("/documents")

    assert response.status_code == 500
    assert response["Content-Type"].startswith("text/html")
    assert b"Server Error (500)" in response.content


# --- handler400 ---------------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_host_outside_allowed_hosts_is_a_json_400_under_the_api(settings):
    settings.DEBUG = False
    response = Client().get("/api/", HTTP_HOST="kmp.attacker.example")

    assert response.status_code == 400
    assert response["Content-Type"] == "application/json"
    assert response.json() == {"detail": BAD_REQUEST_MESSAGE}


@pytest.mark.django_db
def test_a_host_outside_allowed_hosts_is_still_djangos_html_400_outside_the_api(settings):
    settings.DEBUG = False
    response = Client().get("/documents", HTTP_HOST="kmp.attacker.example")

    assert response.status_code == 400
    assert response["Content-Type"].startswith("text/html")
