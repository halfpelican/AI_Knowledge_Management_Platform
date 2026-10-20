"""D-76: every ``/api/`` response is marked never-cache, by one middleware, and nothing else is.

``config.middleware.NeverCacheApiMiddleware`` applies Django's ``add_never_cache_headers`` to every
response whose path is under ``/api/``, whatever its status. The detail route returns a document's
whole extracted text, the ask and search routes return text drawn from documents, and the download
returns the original, so none of them may sit in a browser's disk cache or a proxy.

The walks below go through ``enumerate_endpoints()`` as ``test_rbac.py`` does, so a route added
later is covered without being listed here: anonymously (401), from an Employee and from an
Administrator session (with unknown ids, so every route naming one is a 404), and from each role
with its permissions revoked (so every route guarded by a permission is a 403). The 404 the URL
resolver gives an unknown path, a CSRF refusal and a path outside ``/api/`` are tested on their own.
"""

import uuid

import pytest
from django.conf import settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import Role, RolePermission
from apps.api.tests.dual_role_matrix import enumerate_endpoints
from apps.core.constants import ADMINISTRATOR_ROLE_NAME, EMPLOYEE_ROLE_NAME
from apps.documents.models import Document

pytestmark = pytest.mark.django_db

# What add_never_cache_headers sets on a response: Cache-Control with these directives, and Expires.
NEVER_CACHE_DIRECTIVES = {"max-age=0", "no-cache", "no-store", "must-revalidate", "private"}

# The two routes D-21 leaves open (test_rbac.py's OPEN_ROUTES).
OPEN_ROUTES = {"auth-register", "auth-login"}

# Routes guarded by a role permission, checked before anything else on the request: with the
# role's permissions revoked, each must answer 403. document-detail's DELETE checks its permission
# AFTER the scoped lookup (D-73), so it is tested on a document in scope, below.
PERMISSION_GUARDED = {
    ("api/users", "GET"),  # manage_roles
    ("api/users/<uuid:pk>/role", "PATCH"),  # manage_roles
    ("api/documents", "POST"),  # contribute_content
    ("api/documents/<uuid:pk>/reprocess", "POST"),  # contribute_content
    ("api/meetings", "POST"),  # contribute_content
}


def read_to_the_end(response) -> bytes:
    """A streamed response (the download) is closed by reading it to the end; see
    test_document_download.py's module docstring for why not ``response.close()``."""
    if response.streaming:
        return b"".join(response.streaming_content)
    return response.content


def assert_never_cached(response, where):
    assert "Cache-Control" in response, where
    directives = {directive.strip() for directive in response["Cache-Control"].split(",")}
    assert directives == NEVER_CACHE_DIRECTIVES, (where, response["Cache-Control"])
    assert "Expires" in response, where


def logged_in(user):
    client = APIClient()
    client.force_login(user)
    return client


def walk(new_client) -> dict:
    """Send every (route, method) in the URL conf an empty JSON body, each from a fresh client so
    that logging out on one route cannot sign the next one out. Asserts never-cache on every
    response and returns the statuses by (route, method)."""
    statuses = {}
    for endpoint in enumerate_endpoints():
        url = reverse(endpoint.name, kwargs=endpoint.reverse_kwargs)
        response = new_client().generic(endpoint.method, url, data="{}", content_type="application/json")
        read_to_the_end(response)
        assert_never_cached(response, (endpoint.method, url, response.status_code))
        statuses[endpoint.key] = response.status_code
    return statuses


def routes_naming_an_id() -> set:
    return {endpoint.key for endpoint in enumerate_endpoints() if "pk" in endpoint.reverse_kwargs}


# --- Every route, every way in -----------------------------------------------------------------


def test_every_api_route_is_never_cached_when_it_answers_401():
    statuses = walk(APIClient)

    for endpoint in enumerate_endpoints():
        expected = 400 if endpoint.name in OPEN_ROUTES else 401
        assert statuses[endpoint.key] == expected, endpoint


def test_every_api_route_is_never_cached_from_both_roles_and_its_unknown_ids_are_404s(session_client):
    statuses = walk(lambda: logged_in(session_client.user))

    # Every route that names an id was asked about one that names nothing, and its 404 was
    # checked above like every other response. The role route validates its body first, so the
    # empty one is a 400 for the Administrator and a 403 for the Employee; its 404 is below.
    role_route = ("api/users/<uuid:pk>/role", "PATCH")
    for key in routes_naming_an_id() - {role_route}:
        assert statuses[key] == 404, key
    expected_role_status = 400 if session_client.role_name == ADMINISTRATOR_ROLE_NAME else 403
    assert statuses[role_route] == expected_role_status


def test_every_permission_guarded_route_is_never_cached_when_it_answers_403(session_client):
    """Each role with its permissions revoked (D-14: permissions are the role's), so both roles
    meet every 403 a permission class gives."""
    RolePermission.objects.filter(role__role_name=session_client.role_name).delete()

    statuses = walk(lambda: logged_in(session_client.user))

    for key in PERMISSION_GUARDED:
        assert statuses[key] == 403, key


def test_a_delete_refused_for_want_of_manage_documents_is_never_cached(session_client, employee):
    """document-detail's DELETE answers 403 only for a document in scope (D-73). The Administrator
    holds manage_documents, so it is revoked from the role here."""
    document = Document.objects.create(
        title="In scope for both roles", file_type="pdf", uploaded_by=employee,
        visible_to_roles=[EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME],
    )
    RolePermission.objects.filter(role__role_name=session_client.role_name).delete()

    response = session_client.client.delete(f"/api/documents/{document.id}")

    assert response.status_code == 403
    assert_never_cached(response, "DELETE in scope without manage_documents")


def test_the_role_route_is_never_cached_when_its_user_is_unknown(administrator_client):
    response = administrator_client.patch(
        reverse("user-role", kwargs={"pk": uuid.uuid4()}),
        {"role_id": str(Role.objects.get(role_name=EMPLOYEE_ROLE_NAME).pk)},
        format="json",
    )
    assert response.status_code == 404
    assert_never_cached(response, "PATCH users/<unknown>/role")


def test_a_csrf_refusal_is_never_cached(session_client):
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(session_client.user)

    response = client.post("/api/conversations", {}, format="json")

    assert response.status_code == 403
    assert "CSRF" in response.json()["detail"]
    assert_never_cached(response, "CSRF refusal")


# --- The edges: an unknown /api/ path, and everything outside /api/ ---------------------------


@pytest.mark.parametrize("path", ["/api/no-such-route", "/api/documents/not-a-uuid", "/api/documents/"])
def test_an_api_path_the_url_conf_does_not_know_is_never_cached(api_client, session_client, path):
    """The URL resolver's 404 is ``handler404``'s JSON, produced outside every view."""
    for client in (api_client, session_client.client):
        response = client.get(path)
        assert response.status_code == 404
        assert response.json() == {"detail": "Not found."}
        assert_never_cached(response, path)


@pytest.mark.parametrize("path", ["/", "/no-such-page", "/media/documents/x/report.pdf", "/apix/documents"])
def test_a_path_outside_the_api_gets_no_cache_headers_from_the_middleware(api_client, session_client, path):
    """D-76 touches nothing outside /api/, so the SPA's pages and assets stay cacheable once Stage 5
    item 9 serves them. Nothing else in the stack sets either header on these paths, so their
    absence is this middleware leaving them alone."""
    for client in (api_client, session_client.client):
        response = client.get(path)
        assert "Cache-Control" not in response, path
        assert "Expires" not in response, path


def test_the_middleware_is_the_outermost_layer():
    """First in MIDDLEWARE, so it sees every response, including one another middleware returns
    before the view is reached."""
    assert settings.MIDDLEWARE[0] == "config.middleware.NeverCacheApiMiddleware"
