"""API URL configuration: every path in docs/api-contract.md, under ``/api/``.

Paths carry no trailing slash, exactly as the contract writes them. The router
exposes the API root at ``/api/`` and takes viewsets from later stages.
"""

from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()

urlpatterns = [
    # Stage 2: FR-01, FR-02
    path("auth/register", views.RegisterView.as_view(), name="auth-register"),
    path("auth/login", views.LoginView.as_view(), name="auth-login"),
    # Stage 2: FR-04
    path("auth/logout", views.LogoutView.as_view(), name="auth-logout"),
    path("auth/me", views.MeView.as_view(), name="auth-me"),
    # Stage 2: FR-05
    path("roles", views.RoleListView.as_view(), name="role-list"),
    path("users", views.UserListView.as_view(), name="user-list"),
    path("users/<uuid:pk>/role", views.UserRoleView.as_view(), name="user-role"),
    # Stage 3: FR-08
    path("documents", views.DocumentsView.as_view(), name="document-list"),
] + router.urls
