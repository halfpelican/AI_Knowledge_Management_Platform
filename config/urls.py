"""Root URL configuration.

Everything the platform exposes lives under ``/api/`` and is defined in
``apps.api.urls``. There is no admin site and no server-rendered UI.
"""

from django.urls import include, path

urlpatterns = [
    path("api/", include("apps.api.urls")),
]
