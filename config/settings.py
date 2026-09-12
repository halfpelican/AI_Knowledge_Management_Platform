"""Django settings for Project 8, the Organisational Knowledge Management Platform.

Every value is read from the environment through django-environ. No credential,
key or host is hard-coded: the only literals below are the documented, non-secret
development defaults from CLAUDE.md section 4. ``SECRET_KEY`` and ``DATABASE_URL``
have no default and the process refuses to start without them.

A ``.env`` file at the repository root is read if present (copy ``.env.example``).
Variables already set in the process environment take precedence over the file.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()

ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    env.read_env(ENV_FILE)

# --- Core ----------------------------------------------------------------------

SECRET_KEY = env.str("SECRET_KEY")  # required, no default
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["127.0.0.1", "localhost"])

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "apps.core",
    "apps.accounts",
    "apps.documents",
    "apps.meetings",
    "apps.ingestion",
    "apps.retrieval",
    "apps.ai",
    "apps.api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
            ],
        },
    },
]

# --- Database: PostgreSQL 16 + pgvector through psycopg 3 ----------------------
# ``postgres://user:password@host:port/name`` maps to django.db.backends.postgresql.
# One database holds both the relational schema and the vectors (NFR-21).

DATABASES = {"default": env.db("DATABASE_URL")}  # required, no default

# --- Authentication -------------------------------------------------------------
# Email is the login identifier (docs/decisions.md D-02); the model is a UUID-keyed
# shell that the proposal's Users table definition extends in a later migration.

AUTH_USER_MODEL = "accounts.User"

# --- Internationalisation -------------------------------------------------------

LANGUAGE_CODE = "en-au"
TIME_ZONE = "Australia/Melbourne"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- AI provider (CLAUDE.md section 4, docs/ai-provider.md) ---------------------
# Application code never reads these directly; it calls apps.ai.get_ai_service().

AI_PROVIDER = env.str("AI_PROVIDER", default="flm")

# FastFlowLM on the local NPU: the default for development, testing and demonstration.
FLM_BASE_URL = env.str("FLM_BASE_URL", default="http://127.0.0.1:52625/v1")
FLM_API_KEY = env.str("FLM_API_KEY", default="flm")  # placeholder, not a credential
FLM_CHAT_MODEL = env.str("FLM_CHAT_MODEL", default="gemma3:4b")
FLM_EMBED_MODEL = env.str("FLM_EMBED_MODEL", default="embed-gemma")

# Length of the vectors the configured embedding model returns (docs/decisions.md
# D-03). The pgvector column is sized from this and the startup check verifies it.
EMBEDDING_DIMENSION = env.int("EMBEDDING_DIMENSION", default=768)

# Claude + Voyage: the documented production configuration, not used day to day.
ANTHROPIC_API_KEY = env.str("ANTHROPIC_API_KEY", default="")
ANTHROPIC_MODEL = env.str("ANTHROPIC_MODEL", default="claude-opus-5")
VOYAGE_API_KEY = env.str("VOYAGE_API_KEY", default="")
VOYAGE_MODEL = env.str("VOYAGE_MODEL", default="voyage-4")
VOYAGE_BASE_URL = env.str("VOYAGE_BASE_URL", default="https://api.voyageai.com/v1")
