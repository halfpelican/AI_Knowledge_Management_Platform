"""API URL configuration.

A single DRF router. Viewsets register on it from Stage 2 onwards; until then it
exposes only the API root at ``/api/``.
"""

from rest_framework.routers import DefaultRouter

router = DefaultRouter()

urlpatterns = router.urls
