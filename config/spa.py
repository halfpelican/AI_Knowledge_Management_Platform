"""The single-page app's catch-all: client routes answer the build's ``index.html``.

The alpha serves the built SPA and ``/api`` from one origin (D-21, D-64, Stage 5 item 9).
WhiteNoise serves the build's files at their own paths (``config/settings.py``); this view
answers the rest, so a reload or a typed address on a client route such as ``/documents/<id>``
reaches the React router rather than a 404.

**What it does not answer.** ``/api`` and everything under ``/api/``, which keep their own JSON
404 through ``handler404``, and everything under ``/assets/``, where a file WhiteNoise does not
have is a 404 rather than ``index.html`` served in place of a script. ``CLIENT_ROUTE_PATTERN``
states both.
"""

from pathlib import Path

from django.conf import settings
from django.http import Http404, HttpResponse
from django.utils.cache import patch_cache_control
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_safe

# Every path except ``api`` (alone, or followed by a slash) and ``assets`` (likewise). Django
# matches it against the path without its leading slash, so ``/`` is the empty string and matches.
# ``assets`` is Vite's default build.assetsDir; config/settings.py's
# WHITENOISE_IMMUTABLE_FILE_TEST names the same folder.
CLIENT_ROUTE_PATTERN = r"^(?!api(?:/|$)|assets(?:/|$)).*$"


@csrf_exempt  # it makes no write; see "Exempt from CSRF" below (D-124)
@require_safe
def index(request):
    """``index.html`` from ``settings.SPA_DIST_DIR``, read on each request.

    **Not cached by the browser without asking.** ``Cache-Control: no-cache``: the page names the
    build's hashed asset files, so a copy kept past a redeployment would ask for files that no
    longer exist. The assets themselves are cached for good, because their names change.

    **Without a build it is the JSON 404**, as every non-API path was before item 9. That is the
    development setup, where Vite's server serves the pages, and the deployment runbook's smoke
    check is what catches a deployment that forgot to build.

    **Reads and HEADs only.** Anything else is a 405, so the catch-all cannot answer a write.

    **Exempt from CSRF, because it makes no write** (D-124). Without the exemption, Django's CSRF
    middleware checked an unsafe request before ``require_safe`` could answer 405. That check reads
    ``request.POST``, and Django parses a multipart body to answer it, spooling its files. Anyone
    holding a well-formed ``csrftoken`` cookie, which a client can make up, could have a body up to
    Waitress's cap parsed here, signed in or not. Exempt, the 405 comes first and nothing is read.
    The exemption cannot let a cross-site write through, because there is no write here to let
    through.
    """
    try:
        html = (Path(settings.SPA_DIST_DIR) / "index.html").read_bytes()
    except FileNotFoundError:
        raise Http404("The front end has not been built.") from None
    response = HttpResponse(html, content_type="text/html; charset=utf-8")
    patch_cache_control(response, no_cache=True)
    return response
