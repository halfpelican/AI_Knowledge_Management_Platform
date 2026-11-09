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

from apps.core.constants import (
    ASK_THROTTLE_RATE,
    AUTHENTICATION_THROTTLE_RATE,
    CONVERSATION_CREATE_THROTTLE_RATE,
    INGESTION_THROTTLE_RATE,
    PASSWORD_MINIMUM_LENGTH,
    SESSION_INACTIVITY_MINUTES,
)
from apps.core.logging_config import platform_logging

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()

ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    env.read_env(ENV_FILE)

# --- Core ----------------------------------------------------------------------

SECRET_KEY = env.str("SECRET_KEY")  # required, no default
DEBUG = env.bool("DEBUG", default=False)
# The M6 alpha is served on loopback (D-64), so the defaults are the loopback values. Exposing it
# beyond the laptop is a .env change and a new decision, not a code change.
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["127.0.0.1", "localhost"])
# The origins an unsafe request may come from besides its own. The alpha's pages and /api share
# one origin (D-21), so Django's own same-origin check already passes them; these are D-64's
# loopback defaults, for waitress-serve's port 8000.
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS", default=["http://127.0.0.1:8000", "http://localhost:8000"]
)

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.postgres",
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
    # Every /api/ response is marked never-cache (D-76). First, so it is the outermost
    # layer and sees every response, including one another middleware returns early.
    "config.middleware.NeverCacheApiMiddleware",
    # Also sets X-Content-Type-Options: nosniff, which is what binds a download to the
    # Content-Type its signature chose (D-75).
    "django.middleware.security.SecurityMiddleware",
    # Serves the built SPA's files (WHITENOISE_ROOT below) before any session or view work,
    # directly after SecurityMiddleware as WhiteNoise's documentation places it (Stage 5 item 9).
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    # Resolves the session cookie to request.user, which DRF's session
    # authentication reads (D-21). Must follow SessionMiddleware.
    "django.contrib.auth.middleware.AuthenticationMiddleware",
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

# bcrypt is the hasher the proposal names for password_hash (FR-01). It is listed
# first so every new hash is bcrypt; Django's defaults follow so any other format
# can still be verified. A test asserts new hashes start with "bcrypt_sha256$".
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

# Django's four default validators, plus FR-01's own complexity rule. FR-01 states
# it as "min 8 chars, 1 uppercase, 1 number, 1 special character"; none of Django's
# defaults check a character class, so ComplexityValidator is what makes the clause
# true. MinimumLengthValidator reads the same constant as ComplexityValidator, so
# the two statements of the minimum cannot drift. The similarity validator is
# pointed at the two user attributes this model has; Django's default list names
# columns it does not.
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
        "OPTIONS": {"user_attributes": ["name", "email"]},
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": PASSWORD_MINIMUM_LENGTH},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    {"NAME": "apps.accounts.validators.ComplexityValidator"},
]

# --- Sessions (FR-04, docs/decisions.md D-10) --------------------------------------
# Django's own session framework, database-backed: no Sessions table of our own.
# Saving on every request makes SESSION_COOKIE_AGE an inactivity expiry.

SESSION_COOKIE_AGE = SESSION_INACTIVITY_MINUTES * 60
SESSION_SAVE_EVERY_REQUEST = True
# The session cookie is the credential (D-21): never readable by scripts, and
# not sent on cross-site requests. The CSRF cookie must stay readable because the
# front end copies it into the X-CSRFToken header on every unsafe request.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"
# Off by default: the alpha is plain HTTP on loopback (D-64), and whether a browser returns a
# Secure cookie over plain HTTP, even on loopback, varies by browser. Turn both on in .env when
# the same build is served over HTTPS.
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=False)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=False)

# --- REST framework (CLAUDE.md section 6 invariant 4, D-21) -----------------------
# Every route is protected unless it opts out explicitly (registration and login).
# apps.api.authentication.SessionAuthentication names its scheme so DRF answers an
# unauthenticated request with 401 rather than its 403 fallback.

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.api.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    # JSON only, as docs/api-contract.md states. This is also what stops a
    # cross-site login: DRF applies csrf_exempt to every view and only enforces
    # CSRF once a session user has been found, so an anonymous POST is never
    # checked. Dropping the form parsers means a cross-site HTML form cannot
    # reach the API at all, and a cross-site fetch sending application/json is
    # held by the preflight that this same-origin deployment never answers.
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    # No DEFAULT_THROTTLE_CLASSES: a view is throttled only where it names a scope.
    #
    # - "auth": registration and login, per client address. Anonymous and, with FR-02's
    #   lockout enforced, unthrottled they are a denial-of-service primitive: the mandatory
    #   409 on a duplicate address identifies a registered one and five requests then lock
    #   it (D-26).
    # - "ask", "ingestion" and "conversation_create": per signed-in user (D-79, D-80).
    #   "ingestion" is one budget shared by the three routes that ingest.
    #
    # The counters live in the default cache. No CACHES is set, so that is Django's
    # per-process LocMemCache: the one Waitress process (D-64) shares them, a restart clears
    # them, and a multi-process server would need a shared cache.
    "DEFAULT_THROTTLE_RATES": {
        "auth": AUTHENTICATION_THROTTLE_RATE,
        "ask": ASK_THROTTLE_RATE,
        "ingestion": INGESTION_THROTTLE_RATE,
        "conversation_create": CONVERSATION_CREATE_THROTTLE_RATE,
    },
    # X-Forwarded-For is not trusted: an anonymous throttle is keyed on REMOTE_ADDR, the
    # connecting address. Unset, DRF keys it on the client-sent header, so the auth limit
    # could be dodged by changing that header on every request (D-79). Nothing sits in front
    # of the server today; if Stage 5 item 9 puts a reverse proxy there, it makes this 1.
    "NUM_PROXIES": 0,
}

# --- Audit log (FR-05) -------------------------------------------------------------
# A role change is one JSON line written by the "audit" logger
# (apps.accounts.audit). Schema v1 has no audit table, so the medium is a file
# until docs/decisions.md records one; the path is read from the environment.

AUDIT_LOG_PATH = Path(env.str("AUDIT_LOG_PATH", default=str(BASE_DIR / "logs" / "audit.log")))
AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

# --- Error log (docs/decisions.md D-75) ----------------------------------------------
# Every record at ERROR or above that reaches the root logger, Django's own included, is
# appended here. Without it an error with DEBUG=False went nowhere: Django's console
# handler needs DEBUG and mail_admins has no ADMINS. Beside audit.log by default, and
# gitignored with it (logs/).

ERROR_LOG_PATH = Path(env.str("ERROR_LOG_PATH", default=str(BASE_DIR / "logs" / "errors.log")))
ERROR_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

# --- Waitress's log (docs/decisions.md D-87 section 3) ------------------------------------
# Waitress's own records at INFO and above, timestamped: "Serving on ..." at start-up, and
# "Task queue depth is N" whenever a request arrives with every thread busy. Before this file
# existed they went nowhere, for the reason apps/core/logging_config.py records. Beside
# errors.log by default, and gitignored with it (logs/).

WAITRESS_LOG_PATH = Path(env.str("WAITRESS_LOG_PATH", default=str(BASE_DIR / "logs" / "waitress.log")))
WAITRESS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

# --- The provider attempts log (step 7 phase 2a, 7 November 2026) ------------------------
# Every generation attempt, parsed or failed, with what its reply reported, at INFO
# (apps/ai/attempt_log.py). The error file keeps only the failures. Beside errors.log by
# default, and gitignored with it (logs/).

ATTEMPTS_LOG_PATH = Path(env.str("ATTEMPTS_LOG_PATH", default=str(BASE_DIR / "logs" / "attempts.log")))
ATTEMPTS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

LOGGING = platform_logging(
    audit_path=AUDIT_LOG_PATH,
    error_path=ERROR_LOG_PATH,
    waitress_path=WAITRESS_LOG_PATH,
    attempts_path=ATTEMPTS_LOG_PATH,
)

# --- Uploaded files (FR-08, docs/decisions.md D-05) ------------------------------
# Originals are stored on the local filesystem, not in the database and not in cloud
# object storage; cloud storage is a later change behind Django's own storage
# interface. The path is read from the environment and defaults to media/ under the
# repository root, which is gitignored. The extracted plain text is stored
# separately, in extracted_content, so retrieval never re-parses the original.
#
# Stored names are sanitised by Django's storage (get_valid_name strips directory
# separators) and every write goes through a FileField, so no upload can name a path
# outside MEDIA_ROOT.

MEDIA_ROOT = Path(env.str("MEDIA_ROOT", default=str(BASE_DIR / "media")))
MEDIA_URL = "/media/"
# Django buffers an upload in memory below this and spools it to a temporary file
# above it. Held well under MAX_UPLOAD_BYTES so a 50 MB upload is never held in
# memory: the size ceiling is checked against the declared length before the body is
# parsed at all (FR-08: "enforced before the file is written to storage").
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024  # 2 MB
# Nothing serves MEDIA_ROOT. No URL pattern maps MEDIA_URL, WhiteNoise's root is the SPA build
# below and not this folder, and a stored original leaves only through FR-15's scoped download.

# --- The single-page app, from the same origin as /api (D-21, D-64, Stage 5 item 9) -------
# The production build of frontend/ (`npm run build`) is served by this process, so the SPA
# and /api share one origin and the SameSite=Lax cookies above are sent on every call. Two
# parts serve it:
#
# - WhiteNoise serves every file in the build at its own path: /assets/..., /favicon.svg.
#   It reads the folder once, at start-up, so the SPA is built BEFORE the server starts.
# - config.spa.index answers every other path outside /api/ and /assets/ with the build's
#   index.html, so a client route such as /documents/<id> survives a reload. /api/ keeps its
#   own JSON 404 (config/urls.py).
#
# An absolute path. Without a build, the catch-all answers the JSON 404 and WhiteNoise serves
# nothing. Under DEBUG=False WhiteNoise prints "UserWarning: No directory at: ..." to the
# server's console as it starts, and the deployment runbook's smoke check fails on GET /.

SPA_DIST_DIR = Path(env.str("SPA_DIST_DIR", default=str(BASE_DIR / "frontend" / "dist")))
WHITENOISE_ROOT = SPA_DIST_DIR
# Vite writes every file under assets/ (its default build.assetsDir) with a content hash in its
# name, so a changed file is a new URL and these can be cached for good: WhiteNoise then sends
# "max-age=315360000, public, immutable". Everything else in the build, such as favicon.svg,
# keeps WhiteNoise's 60 seconds. The URL conf's catch-all leaves /assets/ alone for the same
# reason, so a missing asset is a 404 rather than index.html served as JavaScript.
WHITENOISE_IMMUTABLE_FILE_TEST = r"^/assets/"
# No collectstatic and no django.contrib.staticfiles: the build is served from its own folder.
# Without this, under DEBUG WhiteNoise would ask the staticfiles finders about every request.
WHITENOISE_USE_FINDERS = False
# One origin, so nothing needs the build cross-origin. WhiteNoise's default is
# "Access-Control-Allow-Origin: *" on every file it serves.
WHITENOISE_ALLOW_ALL_ORIGINS = False

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

# Claude + Voyage: the proposal's production configuration, funded since D-113.
ANTHROPIC_API_KEY = env.str("ANTHROPIC_API_KEY", default="")
# Sonnet by the user's choice (10 November 2026): half Opus 5.5's per-token price.
ANTHROPIC_MODEL = env.str("ANTHROPIC_MODEL", default="claude-sonnet-5-5")
VOYAGE_API_KEY = env.str("VOYAGE_API_KEY", default="")
VOYAGE_MODEL = env.str("VOYAGE_MODEL", default="voyage-4")
VOYAGE_BASE_URL = env.str("VOYAGE_BASE_URL", default="https://api.voyageai.com/v1")
