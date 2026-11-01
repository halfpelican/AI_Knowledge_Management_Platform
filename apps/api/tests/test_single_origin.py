"""Stage 5 item 9: the built SPA and /api from one origin (D-21, D-64).

WhiteNoise serves the build's files at their own paths, ``config.spa.index`` answers every other
path outside ``/api`` and ``/assets/`` with the build's ``index.html``, and ``/api/`` keeps its own
JSON 404 through ``handler404``. The suite runs with no build (conftest.py's ``spa_not_built``), so
each test here that needs one makes a small stand-in with ``spa_build``: an ``index.html``, one
hashed script under ``assets/`` named the way Vite names them, and a ``favicon.svg`` at the root,
as ``frontend/public`` puts it there.

The SPA's pages are not protected endpoints: the shell is the same for everyone and every call it
makes is checked server-side. The tests that read them from a session do so to show that a session
changes nothing, not for the dual-role matrix, which covers ``/api/`` only.
"""

import uuid

import pytest
from django.conf import settings

pytestmark = pytest.mark.django_db

INDEX_HTML = (
    b'<!doctype html><html lang="en"><head>'
    b'<script type="module" crossorigin src="/assets/index-BXk3a8_c.js"></script>'
    b'</head><body><div id="root"></div></body></html>'
)
ASSET = "assets/index-BXk3a8_c.js"
ASSET_BODY = b"console.log('the stand-in bundle');"
FAVICON_BODY = b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"

API_NOT_FOUND = {"detail": "Not found."}

# WhiteNoise's FOREVER (ten years) for a file WHITENOISE_IMMUTABLE_FILE_TEST matches, and its
# default max_age under DEBUG=False for any other file.
IMMUTABLE = "max-age=315360000, public, immutable"
SHORT = "max-age=60, public"

CLIENT_ROUTES = [
    "/",
    "/login",
    "/dashboard",
    "/documents",
    f"/documents/{uuid.uuid4()}",
    "/admin/roles",
    "/ask",
    "/no-such-page",
    "/documents/",
    "/apix/documents",  # starts with "api" but is not /api
]

API_PATHS_NO_ROUTE_MATCHES = ["/api/__nope__", "/api/no-such-route", "/api/documents/not-a-uuid", "/api/documents/"]


@pytest.fixture
def spa_build(tmp_path, settings):
    """A stand-in for ``frontend/dist`` that both settings point at, as config/settings.py does."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_bytes(INDEX_HTML)
    (dist / ASSET).write_bytes(ASSET_BODY)
    (dist / "favicon.svg").write_bytes(FAVICON_BODY)
    settings.SPA_DIST_DIR = dist
    settings.WHITENOISE_ROOT = dist
    return dist


def body(response) -> bytes:
    """WhiteNoise answers with a streamed FileResponse; read either kind to the end."""
    if response.streaming:
        return b"".join(response.streaming_content)
    return response.content


def assert_is_the_spa(response, where):
    assert response.status_code == 200, (where, response.status_code)
    assert body(response) == INDEX_HTML, where
    assert response["Content-Type"] == "text/html; charset=utf-8", where
    # Revalidated on every load, so a redeployment's new asset names are picked up, and never
    # given D-76's never-cache set, which belongs to /api/ alone.
    assert response["Cache-Control"] == "no-cache", where
    assert "Expires" not in response, where


def assert_is_the_api_404(response, where):
    assert response.status_code == 404, (where, response.status_code)
    assert response["Content-Type"] == "application/json", where
    assert response.json() == API_NOT_FOUND, where
    assert body(response) != INDEX_HTML, where


# --- The catch-all ----------------------------------------------------------------------------


@pytest.mark.parametrize("path", CLIENT_ROUTES)
def test_a_client_route_answers_the_spas_index_html(api_client, session_client, spa_build, path):
    """A reload or a typed address on a client route reaches the React router, signed in or not."""
    for client in (api_client, session_client.client):
        assert_is_the_spa(client.get(path), path)


def test_the_catch_all_answers_reads_only(api_client, spa_build):
    assert api_client.head("/documents").status_code == 200
    for method in ("post", "put", "patch", "delete"):
        response = getattr(api_client, method)("/documents")
        assert response.status_code == 405, method
        assert body(response) != INDEX_HTML, method


@pytest.mark.parametrize("path", API_PATHS_NO_ROUTE_MATCHES)
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_an_unmatched_api_path_is_still_the_json_404_with_the_spa_built(
    api_client, session_client, spa_build, method, path
):
    """The catch-all must not swallow /api/: a typo in a call is a JSON 404 the client can read,
    never index.html with a 200."""
    for client in (api_client, session_client.client):
        response = client.generic(method, path, data="{}", content_type="application/json")
        assert_is_the_api_404(response, (method, path))


def test_api_without_its_slash_is_redirected_to_the_api_root_not_served_the_spa(api_client, spa_build):
    """``/api`` is outside the catch-all too, so APPEND_SLASH still sends it to ``/api/``."""
    response = api_client.get("/api")
    assert response.status_code == 301
    assert response["Location"] == "/api/"


def test_the_api_root_still_answers_401_json_with_the_spa_built(api_client, spa_build):
    response = api_client.get("/api/")
    assert response.status_code == 401
    assert response["Content-Type"] == "application/json"
    assert "detail" in response.json()


def test_a_signed_in_api_call_is_still_answered_by_the_api(session_client, spa_build):
    response = session_client.client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json()["role"] == session_client.role_name


# --- The build's files ------------------------------------------------------------------------


def test_a_built_asset_is_served_and_cached_for_good(api_client, spa_build):
    response = api_client.get(f"/{ASSET}")

    assert response.status_code == 200
    assert body(response) == ASSET_BODY
    assert response["Content-Type"].startswith("text/javascript")
    assert response["Cache-Control"] == IMMUTABLE
    # One origin, so nothing needs the bundle cross-origin (WHITENOISE_ALLOW_ALL_ORIGINS).
    assert "Access-Control-Allow-Origin" not in response


def test_a_file_at_the_root_of_the_build_is_served_with_a_short_cache(api_client, spa_build):
    """favicon.svg has no hash in its name, so it is not cached for good."""
    response = api_client.get("/favicon.svg")

    assert response.status_code == 200
    assert body(response) == FAVICON_BODY
    assert response["Cache-Control"] == SHORT


@pytest.mark.parametrize("path", ["/assets/index-Missing0.js", "/assets/", "/assets"])
def test_a_missing_asset_is_a_404_and_never_the_spa(api_client, spa_build, path):
    """index.html served in place of a script would be a 200 the browser then fails to run."""
    assert_is_the_api_404(api_client.get(path), path)


def test_nothing_serves_the_media_folder(api_client, session_client, spa_build, media_root):
    """A stored original leaves only through FR-15's scoped download: /media/ is a client route
    like any other, so it answers the SPA and never the file."""
    stored = media_root / "documents" / "2026" / "report.pdf"
    stored.parent.mkdir(parents=True)
    stored.write_bytes(b"%PDF-1.7 a stored original")

    for client in (api_client, session_client.client):
        response = client.get("/media/documents/2026/report.pdf")
        assert_is_the_spa(response, "/media/")
        assert b"stored original" not in body(response)


# --- Without a build --------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/", "/documents", f"/{ASSET}", "/favicon.svg"])
def test_without_a_build_a_path_outside_the_api_is_the_json_404(api_client, path):
    """The development setup, where Vite's server serves the pages: as before item 9."""
    assert_is_the_api_404(api_client.get(path), path)


def test_whitenoise_sits_directly_after_the_security_middleware():
    middleware = settings.MIDDLEWARE
    security = middleware.index("django.middleware.security.SecurityMiddleware")
    assert middleware[security + 1] == "whitenoise.middleware.WhiteNoiseMiddleware"
    assert middleware.index("whitenoise.middleware.WhiteNoiseMiddleware") < middleware.index(
        "django.contrib.sessions.middleware.SessionMiddleware"
    )
