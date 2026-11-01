"""Root URL configuration.

Everything the platform exposes lives under ``/api/`` and is defined in
``apps.api.urls``. There is no admin site and no server-rendered UI: every other path
is the single-page app's (Stage 5 item 9, D-64), served by WhiteNoise and the
catch-all below.
"""

from django.urls import include, path, re_path

from config import spa

urlpatterns = [
    path("api/", include("apps.api.urls")),
    # Last, and never /api or /assets/ (spa.CLIENT_ROUTE_PATTERN): a client route answers the
    # SPA's index.html, while an unmatched /api/ path still falls through to handler404 below.
    re_path(spa.CLIENT_ROUTE_PATTERN, spa.index, name="spa"),
]

# A path that matches no route is answered in JSON like every other error, not
# with Django's HTML page. Since item 9 that is an unmatched /api/ path, a missing
# /assets/ file, or any path when the SPA has not been built.
handler404 = "apps.api.views.not_found"
# Under /api/, JSON in place of Django's HTML 400 and 500 pages (config/errors.py).
handler400 = "config.errors.bad_request"
handler500 = "config.errors.server_error"
