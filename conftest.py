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
user per role, and one document visible to Employees carrying one chunk.

The chunk is NOT stamped: ``content_chunk.visible_to_roles`` is ``[]``, the model
default, because stamping it from the source is ingestion's job (D-17) and
apps/documents/tests/test_models.py asserts the unstamped default here. Under FR-11
an unstamped chunk is visible to no role at all, so a retrieval test must build its
own chunks with an explicit scope rather than reach for this one and wonder why the
candidate set came back empty (apps/retrieval/tests/test_scoping.py does that).

The client fixtures cover the dual-role gate (CLAUDE.md section 8): api_client is
anonymous, employee_client and administrator_client are logged in as one role, and
session_client is parametrised over both roles so a test written once against it
runs from an Employee session and from an Administrator session. Whether every
protected endpoint was in fact reached from both roles is not taken from fixture
names: apps/api/tests/dual_role_matrix.py records the role the server resolved on
each request and fails a full run below 100%.
"""

from dataclasses import dataclass
from pathlib import Path

import pytest

# The dual-role coverage matrix (CLAUDE.md section 8 item 2). Registered here so it
# observes every request the suite makes; see the module docstring.
pytest_plugins = ["apps.api.tests.dual_role_matrix"]
from django.conf import settings
from django.core.cache import cache
from django.test import override_settings

import logging.config

import apps.ai
from apps.ai.testing import UNROUTABLE_PROVIDER_HOST, UNROUTABLE_PROVIDER_URL, StubAIService
from apps.core.constants import ADMINISTRATOR_ROLE_NAME, EMPLOYEE_ROLE_NAME, ROLE_NAMES, SOURCE_TYPES
from apps.core.logging_config import ERROR_FILE_HANDLER, platform_logging

# The suite's one password. It satisfies FR-01's complexity rules (min 8 characters,
# an uppercase letter, a number and a special character) so that a test may register
# it through the API; apps/api/tests/test_register.py is where non-complying
# passwords are asserted to be refused.
PASSWORD = "Correct-Horse-9-Battery"


@pytest.fixture(autouse=True)
def reset_request_throttles():
    """Clear the throttle counters and the in-flight slots between tests.

    Registration and login are rate limited per client address (D-26), and asks, ingestion,
    thread creation, keyword search and a person applying a tag per user (D-79 and its notes of
    10 November 2026). ``cache.clear()`` empties every scope at once, so a new scope needs nothing
    here. DRF keeps those counts in the cache, which outlives
    a test, and so do each user's in-flight ask slot (apps/api/ask_slot.py) and in-flight
    ingestion slot (apps/api/ingestion_slot.py, D-85). Without this,
    a test that signs in a few times would 429 the next test rather than failing on its own
    merits, and every test signs in from the same address. The per-user counters would leak
    less, since each test's users are new rows with new ids, but a slot or a count left by a
    test that failed halfway is cleared all the same. Throttling itself stays on: the real
    rates are tested in apps/api/tests/test_throttles.py.
    """
    cache.clear()
    yield
    cache.clear()


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
        # Recording transcription is off, as it is by default (D-123), whatever a
        # developer's .env says: a test that needs it on says so with override_settings.
        TRANSCRIPTION_PROVIDER="none",
    ):
        yield


@pytest.fixture(autouse=True)
def summaries_run_inline(settings):
    """FR-16's summary runs in the caller's thread, never in a background one (D-125).

    The server starts each run in a thread after the requesting transaction commits
    (apps/meetings/summary_runner.py). A thread would outlive the test that started it and write
    through its own database connection, outside the test's transaction. Inline, a test that
    executes the commit callbacks (``django_capture_on_commit_callbacks(execute=True)``) sees the
    finished summary, and one that does not sees the run still Processing, which is the state the
    202 reports. The thread path has its own tests, which override this.
    """
    settings.SUMMARY_RUNNER = "inline"


@dataclass
class LogFiles:
    """The four log files one test's logging writes."""

    audit: Path
    errors: Path
    waitress: Path
    attempts: Path


def _configure_logging(config):
    """``dictConfig(config)``, keeping the handlers pytest has attached to the root logger.

    The platform's configuration names a root handler (D-75's error file), and a
    non-incremental ``dictConfig`` with a ``root`` entry removes every handler the root
    logger had. While a fixture runs, those include pytest's own: the capture handler for
    the setup phase and the live-log and log-file handlers it attaches once per session.
    Removing them would silently end ``--log-cli-level`` output after the first test.
    """
    root = logging.getLogger()
    pytests_handlers = [handler for handler in root.handlers if handler.get_name() != ERROR_FILE_HANDLER]
    logging.config.dictConfig(config)
    for handler in pytests_handlers:
        if handler not in root.handlers:
            root.addHandler(handler)


@pytest.fixture(autouse=True)
def log_files(tmp_path, settings):
    """The FR-05 audit file, D-75's error file, D-87's Waitress file and the provider
    attempts file for this test: AUDIT_LOG_PATH, ERROR_LOG_PATH, WAITRESS_LOG_PATH,
    ATTEMPTS_LOG_PATH and LOGGING are overridden to temporary paths and logging is
    reconfigured from them exactly as config/settings.py builds it, so no test ever appends
    to logs/audit.log, logs/errors.log, logs/waitress.log or logs/attempts.log."""
    original = settings.LOGGING
    audit_path = tmp_path / "audit.log"
    error_path = tmp_path / "errors.log"
    waitress_path = tmp_path / "waitress.log"
    attempts_path = tmp_path / "attempts.log"
    settings.AUDIT_LOG_PATH = audit_path
    settings.ERROR_LOG_PATH = error_path
    settings.WAITRESS_LOG_PATH = waitress_path
    settings.ATTEMPTS_LOG_PATH = attempts_path
    settings.LOGGING = platform_logging(
        audit_path=audit_path, error_path=error_path, waitress_path=waitress_path,
        attempts_path=attempts_path,
    )
    _configure_logging(settings.LOGGING)
    yield LogFiles(audit=audit_path, errors=error_path, waitress=waitress_path, attempts=attempts_path)
    _configure_logging(original)


@pytest.fixture
def audit_file(log_files):
    """The FR-05 audit file this test's logging writes (see ``log_files``)."""
    return log_files.audit


@pytest.fixture
def error_log_file(log_files):
    """D-75's error file this test's logging writes (see ``log_files``)."""
    return log_files.errors


@pytest.fixture
def waitress_log_file(log_files):
    """D-87's Waitress file this test's logging writes (see ``log_files``)."""
    return log_files.waitress


@pytest.fixture
def attempts_log_file(log_files):
    """The provider attempts file this test's logging writes (see ``log_files``)."""
    return log_files.attempts


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


# --- Ingestion (FR-08, FR-09) ---------------------------------------------------------

# The committed fixture corpus: a real PDF, DOCX, XLSX and TXT, plus two executables
# renamed .pdf. Built by apps/ingestion/tests/fixtures/build_fixtures.py, which
# documents what each one is for.
FIXTURE_CORPUS = Path(__file__).resolve().parent / "apps" / "ingestion" / "tests" / "fixtures"


@pytest.fixture(autouse=True)
def media_root(tmp_path, settings):
    """Every test writes uploads into its own temporary directory.

    Without this the suite would write real files into the repository's own media/
    and leave them there: MEDIA_ROOT defaults to media/ under the repository root
    (D-05), gitignored but not self-cleaning, and a test asserting "the stored file
    was removed" would be reading a directory every other test had also written to.
    """
    root = tmp_path / "media"
    root.mkdir()
    settings.MEDIA_ROOT = root
    return root


@pytest.fixture(autouse=True)
def spa_not_built(tmp_path, settings):
    """Every test sees no SPA build unless it builds one (Stage 5 item 9).

    SPA_DIST_DIR defaults to frontend/dist, which exists on a laptop that has run
    ``npm run build`` and never in CI. Without this, a path outside /api/ would answer
    index.html on one machine and the JSON 404 on the other, and WhiteNoise would scan
    the build for every test client. A test that needs the SPA points both settings at a
    build of its own (apps/api/tests/test_single_origin.py)."""
    settings.SPA_DIST_DIR = tmp_path / "spa-not-built"
    settings.WHITENOISE_ROOT = None


@pytest.fixture
def corpus():
    """The directory holding the committed sample files."""
    return FIXTURE_CORPUS


@pytest.fixture
def upload():
    """Build an in-memory upload from a file in the corpus.

    ``upload("sample.pdf")`` sends it under its own name; ``upload("disguised.pdf")``
    is the renamed executable. ``name=`` overrides the filename the client claims,
    which is how a test disguises one format as another: the server reads the
    signature and never the extension (FR-08).
    """
    from django.core.files.uploadedfile import SimpleUploadedFile

    def build(fixture_name, name=None, content_type="application/octet-stream"):
        return SimpleUploadedFile(
            name or fixture_name,
            (FIXTURE_CORPUS / fixture_name).read_bytes(),
            content_type=content_type,
        )

    return build
