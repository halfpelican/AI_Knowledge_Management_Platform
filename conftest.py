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
"""

import pytest
from django.conf import settings
from django.test import override_settings

import apps.ai
from apps.ai.testing import UNROUTABLE_PROVIDER_HOST, UNROUTABLE_PROVIDER_URL, StubAIService
from apps.core.constants import ADMINISTRATOR_ROLE_NAME, EMPLOYEE_ROLE_NAME, SOURCE_TYPES

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
