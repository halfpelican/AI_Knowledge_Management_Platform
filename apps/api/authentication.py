"""Session authentication that answers 401, not 403, when there is no session, and that checks
CSRF without reading the request body.

**401, not 403.** The API authenticates with the Django session cookie (docs/decisions.md D-21).
DRF's own SessionAuthentication returns no ``WWW-Authenticate`` scheme, and DRF downgrades
NotAuthenticated to 403 whenever the first authenticator has none. That collides with CLAUDE.md
section 6 invariant 4 (401 for no valid session, 403 for a session whose role lacks the
permission), so this subclass names the scheme and DRF keeps the 401.

**The CSRF token is read from the ``X-CSRFToken`` header only (D-124).** DRF runs Django's CSRF
check while it authenticates, before any permission, throttle or view code. Django's check reads
``request.POST`` for a ``csrfmiddlewaretoken`` form field before it falls back to the header, and
on a DRF request ``POST`` runs the view's parser over the body.

- A multipart upload was parsed whole, its files spooled to temporary files, with no ceiling but
  the web server's.
- A JSON body was read and parsed if it was within Django's ``DATA_UPLOAD_MAX_MEMORY_SIZE``
  (2.5 MiB). DRF parses JSON from ``request.body``, which refuses a larger declared length unread,
  with a 400.

So until D-124, every POST from a signed-in session that held the CSRF cookie had its body parsed
before the 403, the 429 or the view's own 413 could refuse it. That held whether or not the
request carried the header.

The check here is DRF's own, shown the request with an empty ``POST``, so it goes straight to the
header and never reads the body. The only thing this gives up is the form field as a second place
for the token, which nothing uses: the SPA sends the header on every unsafe request
(``frontend/src/api/client.js``), and so do the measurement scripts and the load test. Everything
else Django checks is unchanged: the CSRF cookie, the token's match against it and the Origin
header. ``apps/api/tests/test_request_body_bound.py`` tests both: the body is not read, and the
check still refuses.

**Django's own CSRF check read bodies on three more routes,** before DRF ran at all, signed in or
not. ``ensure_csrf_cookie`` ran it on login and ``/api/auth/me``, and ``CsrfViewMiddleware`` ran it
on the SPA's catch-all, which was not exempt. D-124 removed the check from all three:
``SendsCsrfCookieMixin`` in ``apps/api/views.py`` keeps the cookie without the check, and
``config/spa.py`` exempts a view that makes no write.
"""

from django.http import QueryDict
from rest_framework import authentication


class _RequestWithoutBody:
    """The request as Django's CSRF check is shown it here: everything except the body.

    ``POST`` is empty, so the check takes the token from the ``X-CSRFToken`` header. Any other
    attribute read is the wrapped request's own. One set on the wrapper (the check's
    ``csrf_processing_done``) stays on the wrapper, which is discarded once the check is done.
    """

    def __init__(self, request):
        self._request = request

    @property
    def POST(self):
        return QueryDict()

    def __getattr__(self, name):
        return getattr(self._request, name)


class SessionAuthentication(authentication.SessionAuthentication):
    def authenticate_header(self, request):
        return "Session"

    def enforce_csrf(self, request):
        # DRF's own check, exactly as written, shown the request without its body (D-124).
        super().enforce_csrf(_RequestWithoutBody(request))
