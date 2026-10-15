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
    # Stage 5 item 2: FR-15's list view, filters, sort and facets in one request (D-72).
    # Before the <uuid:pk> route below; "browse" is not a UUID, so they cannot collide.
    path("documents/browse", views.DocumentBrowseView.as_view(), name="document-browse"),
    # Before the <uuid:pk> route below for the reading habit's sake; "reprocess" is not a
    # UUID so the two cannot collide either way.
    path("documents/<uuid:pk>/reprocess", views.DocumentReprocessView.as_view(),
         name="document-reprocess"),  # FR-08 "Please try again" (D-32)
    # Stage 5 item 2a: FR-15's download link, the stored original as an attachment (D-75).
    path("documents/<uuid:pk>/download", views.DocumentDownloadView.as_view(),
         name="document-download"),
    # Stage 4 item 10b: the route a document citation links to, so FR-12's "links to the
    # source document or meeting" reaches the document rather than the repository (D-46).
    # Stage 5 item 2 adds FR-15's detail fields to its GET, and the DELETE method (D-73).
    path("documents/<uuid:pk>", views.DocumentDetailView.as_view(), name="document-detail"),
    # Stage 3: FR-09
    path("meetings", views.MeetingsView.as_view(), name="meeting-list"),
    path("meetings/<uuid:pk>", views.MeetingDetailView.as_view(), name="meeting-detail"),
    # Stage 4: FR-12 keyword search, the Front-End clause's grouped results (D-41).
    path("search", views.SearchView.as_view(), name="search"),
    # Stage 4: FR-12's question-and-answer path, which is also FR-13's turn when the body
    # names a conversation (section 7.10).
    path("ask", views.AskView.as_view(), name="ask"),
    # Stage 4: FR-13. Conversations are Create, Read, Update — there is no delete route,
    # because FR-13's Database clause has no Delete and clearing the active thread means
    # starting a new conversation rather than destroying one.
    path("conversations", views.ConversationsView.as_view(), name="conversation-list"),
    path("conversations/<uuid:pk>", views.ConversationDetailView.as_view(),
         name="conversation-detail"),
    # Stage 5 item 3: FR-14's one aggregating endpoint, every dashboard panel in one request.
    path("dashboard", views.DashboardView.as_view(), name="dashboard"),
] + router.urls
