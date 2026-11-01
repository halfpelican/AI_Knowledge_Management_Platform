"""JSON error responses for ``/api/`` that Django would otherwise answer with an HTML page.

Under ``DEBUG=False`` Django answers an unhandled exception with ``handler500`` and a request it
refuses before any view (a ``Host`` outside ``ALLOWED_HOSTS``) with ``handler400``. Their defaults
are HTML pages, which item 6 found on ``/api/`` (D-85's note). Every other ``/api/`` error is JSON,
the front end reads ``detail``, and docs/api-contract.md promises JSON, so under ``/api/`` these two
answer ``{"detail": "..."}`` with a fixed sentence. Outside ``/api/`` they are Django's own pages,
unchanged.

**Fixed sentences, never the exception.** The 500's body says nothing about what failed; the
traceback goes to the error file (D-75), because Django logs every 500 through ``django.request``
whatever its handler returns. Neither handler touches the database or the session, so neither can fail the
way the request did.

``handler404`` stays ``apps.api.views.not_found``, as before item 9.
"""

from django.http import JsonResponse
from django.views import defaults

from config.middleware import API_PATH_PREFIX

SERVER_ERROR_MESSAGE = "A server error occurred."
BAD_REQUEST_MESSAGE = "Bad request."


def _is_api(request) -> bool:
    # path_info, as NeverCacheApiMiddleware matches it, so the two agree on "under /api/".
    return request.path_info.startswith(API_PATH_PREFIX)


def server_error(request):
    """handler500: ``500 {"detail": SERVER_ERROR_MESSAGE}`` under ``/api/``, Django's page elsewhere."""
    if _is_api(request):
        return JsonResponse({"detail": SERVER_ERROR_MESSAGE}, status=500)
    return defaults.server_error(request)


def bad_request(request, exception):
    """handler400: ``400 {"detail": BAD_REQUEST_MESSAGE}`` under ``/api/``, Django's page elsewhere.

    Reached for a ``SuspiciousOperation`` raised outside a view, chiefly a ``Host`` header not in
    ``ALLOWED_HOSTS``. A DRF view's own 400s are its validation errors and never come here.
    """
    if _is_api(request):
        return JsonResponse({"detail": BAD_REQUEST_MESSAGE}, status=400)
    return defaults.bad_request(request, exception)
