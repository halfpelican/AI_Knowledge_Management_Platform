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
    # Before the <uuid:pk> route below; "directory" is not a UUID so the two
    # cannot collide, but reading first is the habit that keeps it true.
    path("users/directory", views.UserDirectoryView.as_view(), name="user-directory"),
    path("users/<uuid:pk>/role", views.UserRoleView.as_view(), name="user-role"),
    # Stage 3: FR-08
    path("documents", views.DocumentsView.as_view(), name="document-list"),
    path("documents/<uuid:pk>/reprocess", views.DocumentReprocessView.as_view(),
         name="document-reprocess"),  # FR-08 "Please try again" (D-32)
    # Stage 3: FR-09
    path("meetings", views.MeetingsView.as_view(), name="meeting-list"),
    path("meetings/<uuid:pk>", views.MeetingDetailView.as_view(), name="meeting-detail"),
] + router.urls
