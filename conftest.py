"""Shared pytest fixtures for the whole suite.

No test ever reaches a live AI provider (docs/ai-provider.md section 6). Two
autouse fixtures below enforce that:

- stub_ai_service replaces apps.ai.get_ai_service with a StubAIService for every
  test. Code under test must obtain the service through that function, looked up
  on the apps.ai module at call time, for the stub to apply.
- no_live_provider points every provider endpoint at a closed loopback port and
  blanks every key, so anything that bypasses the stub fails at once with a
  connection error instead of quietly succeeding against a running FLM server.

The model fixtures give every test the same small, realistic set of rows: one
user per role and one document with one chunk, visible to Employees.

The client fixtures cover the dual-role gate (CLAUDE.md section 8): api_client is
anonymous, employee_client and administrator_client are logged in as one role, and
session_client is parametrised over both roles so a test written once against it
runs from an Employee session and from an Administrator session.
"""

from dataclasses import dataclass

import pytest
from django.conf import settings
from django.test import override_settings

import apps.ai
from apps.ai.testing import UNROUTABLE_PROVIDER_HOST, UNROUTABLE_PROVIDER_URL, StubAIService
from apps.core.constants import ADMINISTRATOR_ROLE_NAME, EMPLOYEE_ROLE_NAME, ROLE_NAMES, SOURCE_TYPES

PASSWORD = "correct horse battery staple"


@pytest.fixture(autouse=True)
def stub_ai_service(monkeypatch):
    stub = StubAIService()
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: stub)
    return stub


@pytest.fixture(autouse=True)
def no_live_provider(monkeypatch):
    # config/settings.py has no ANTHROPIC_BASE_URL; the anthropic SDK reads this
    # environment variable instead, so it gets the same closed port.
    monkeypatch.setenv("ANTHROPIC_BASE_URL", UNROUTABLE_PROVIDER_HOST)
    with override_settings(
        FLM_BASE_URL=UNROUTABLE_PROVIDER_URL,
        VOYAGE_BASE_URL=UNROUTABLE_PROVIDER_URL,
        ANTHROPIC_API_KEY="",  # nothing in a developer's .env can reach a metered API
        VOYAGE_API_KEY="",
    ):
        yield


@pytest.fixture
def employee_role(db):
    from apps.accounts.models import Role

    return Role.objects.get(role_name=EMPLOYEE_ROLE_NAME)


@pytest.fixture
def administrator_role(db):
    from apps.accounts.models import Role

    return Role.objects.get(role_name=ADMINISTRATOR_ROLE_NAME)


@pytest.fixture
def employee(db):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        "employee@example.com", PASSWORD, name="Erin Employee"
    )


@pytest.fixture
def administrator(db):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_superuser(
        "admin@example.com", PASSWORD, name="Ada Administrator"
    )


@pytest.fixture
def document(employee):
    from apps.documents.models import Document

    return Document.objects.create(
        title="Leave policy",
        file_type="pdf",
        uploaded_by=employee,
        visible_to_roles=[EMPLOYEE_ROLE_NAME],
    )


@pytest.fixture
def content_chunk(document):
    from apps.documents.models import ContentChunk

    return ContentChunk.objects.create(
        source_type=SOURCE_TYPES[0],
        source_id=document.id,
        chunk_index=0,
        chunk_text="Leave requests need a manager's approval.",
        embedding=[0.0] * settings.EMBEDDING_DIMENSION,
        embedding_model="stub-embed",
        embedding_dimension=settings.EMBEDDING_DIMENSION,
    )


# --- API clients (docs/decisions.md D-21: session cookie) ------------------------------


@pytest.fixture
def api_client():
    """Anonymous client. CSRF is not enforced, as on Django's test client; the tests
    that prove the cookie flow build their own client with enforce_csrf_checks."""
    from rest_framework.test import APIClient

    return APIClient()


def _logged_in(user):
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_login(user)
    return client


@pytest.fixture
def employee_client(employee):
    return _logged_in(employee)


@pytest.fixture
def administrator_client(administrator):
    return _logged_in(administrator)


@dataclass
class RoleSession:
    role_name: str
    user: object
    client: object


@pytest.fixture(params=ROLE_NAMES, ids=[name.lower() for name in ROLE_NAMES])
def session_client(request):
    """One logged-in client per role, so a test runs from both roles (CLAUDE.md
    section 8 item 2). The fixture named after the role supplies the user."""
    user = request.getfixturevalue(request.param.lower())
    return RoleSession(request.param, user, _logged_in(user))
