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
    # NIT3004: FR-10's classification routes (D-104, D-105). Each has a non-UUID segment after the
    # id, so none can collide with documents/<uuid:pk> below; listed before it for the reading
    # habit's sake, as reprocess and download are. Scoped 404 first, then contribute_content.
    path("documents/<uuid:pk>/classify", views.DocumentClassifyView.as_view(),
         name="document-classify"),
    path("documents/<uuid:pk>/classification", views.DocumentClassificationView.as_view(),
         name="document-classification"),
    # A person applies a tag: an existing one offered for the document, or a new Topic (D-105's
    # dated note of 10 November 2026, night). POST only.
    path("documents/<uuid:pk>/tags", views.DocumentTagsView.as_view(), name="document-tags"),
    path("documents/<uuid:pk>/tags/<uuid:content_tag_id>/confirm",
         views.DocumentTagConfirmView.as_view(), name="document-tag-confirm"),
    path("documents/<uuid:pk>/tags/<uuid:content_tag_id>", views.DocumentTagView.as_view(),
         name="document-tag"),
    path("documents/<uuid:pk>/proposed-topics/confirm",
         views.DocumentProposedTopicConfirmView.as_view(), name="document-proposed-topic-confirm"),
    path("documents/<uuid:pk>/proposed-topics/reject",
         views.DocumentProposedTopicRejectView.as_view(), name="document-proposed-topic-reject"),
    # Stage 4 item 10b: the route a document citation links to, so FR-12's "links to the
    # source document or meeting" reaches the document rather than the repository (D-46).
    # Stage 5 item 2 adds FR-15's detail fields to its GET, and the DELETE method (D-73).
    path("documents/<uuid:pk>", views.DocumentDetailView.as_view(), name="document-detail"),
    # Stage 3: FR-09
    path("meetings", views.MeetingsView.as_view(), name="meeting-list"),
    # D-99 adds can_delete to its GET, and the DELETE method, mirroring documents/<uuid:pk>.
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
    # NIT3004, Objective 06: FR-19's knowledge-gap log (D-107), every route behind
    # review_knowledge_gaps. The list, sorted Open first by occurrence count.
    path("knowledge-gaps", views.KnowledgeGapListView.as_view(), name="knowledge-gap-list"),
    # One aggregation cycle, run now (D-107); the scheduled one is manage.py
    # aggregate_knowledge_gaps. Before the <uuid:pk> route below; "cycles" is not a UUID, so the
    # two cannot collide.
    path("knowledge-gaps/cycles", views.KnowledgeGapCyclesView.as_view(),
         name="knowledge-gap-cycles"),
    # FR-19's "mark an entry as addressed" (D-107): PATCH {"status": "Addressed" | "Open"}.
    path("knowledge-gaps/<uuid:pk>", views.KnowledgeGapDetailView.as_view(),
         name="knowledge-gap-detail"),
    # NIT3004: FR-10's tag administration (D-119 finding 5), both routes behind manage_tags. The
    # inventory with item counts, and DELETE: deactivate a tag in use, delete an unused one.
    path("tags", views.TagListView.as_view(), name="tag-list"),
    path("tags/<uuid:pk>", views.TagDetailView.as_view(), name="tag-detail"),
] + router.urls
