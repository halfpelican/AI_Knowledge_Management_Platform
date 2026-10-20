"""Project middleware.

``NeverCacheApiMiddleware`` marks every ``/api/`` response never-cache (docs/decisions.md D-76).
"""

from django.utils.cache import add_never_cache_headers

# Everything the platform serves lives under this prefix (config/urls.py).
API_PATH_PREFIX = "/api/"


class NeverCacheApiMiddleware:
    """Apply ``add_never_cache_headers`` to every response under ``/api/``, whatever its status.

    That sets ``Cache-Control: max-age=0, no-cache, no-store, must-revalidate, private`` and an
    ``Expires`` header. Django's function, not a hand-built header string, for the reason D-75
    uses ``FileResponse`` rather than a hand-built ``Content-Disposition``.

    **Why every API response (D-76).** The detail route returns a document's whole extracted
    text (D-73), the ask and search routes return text drawn from documents, and the download
    returns the original (D-75). ``no-store`` keeps those out of a browser's disk cache on a
    shared machine and out of any proxy a deployment puts in front. The 401s, 403s and 404s
    are marked too, so a cached error can never stand in for a later answer.

    **Matched on ``path_info``**, the path the URL conf resolves, so the test agrees with
    ``config/urls.py`` about what "under /api/" means even if a deployment mounts the site
    under a script prefix, where ``request.path`` would carry the prefix and match nothing.

    **Nothing outside /api/ is touched**, so the single-page app's pages and assets stay
    cacheable once Stage 5 item 9 serves them.

    First in ``MIDDLEWARE``, so it is the outermost layer and sees every response: DRF's 401
    and 403, CSRF's 403, the URL resolver's 404 from ``handler404``, a 500, and any response
    another middleware returns early.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path_info.startswith(API_PATH_PREFIX):
            add_never_cache_headers(response)
        return response
