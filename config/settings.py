"""Django settings for Project 8, the Organisational Knowledge Management Platform.

Every value is read from the environment through django-environ. No credential,
key or host is hard-coded: the only literals below are the documented, non-secret
development defaults from CLAUDE.md section 4. ``SECRET_KEY`` and ``DATABASE_URL``
have no default and the process refuses to start without them.

A ``.env`` file at the repository root is read if present (copy ``.env.example``).
Variables already set in the process environment take precedence over the file.
"""

from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

import environ
from django.core.exceptions import ImproperlyConfigured

from apps.core.constants import (
    ACTION_ITEM_THROTTLE_RATE,
    ASK_THROTTLE_RATE,
    AUTHENTICATION_THROTTLE_RATE,
    CACHE_MAX_ENTRIES,
    CONVERSATION_CREATE_THROTTLE_RATE,
    EMAIL_TIMEOUT_SECONDS,
    EMBEDDING_DIMENSION_BY_PROVIDER,
    INGESTION_THROTTLE_RATE,
    LOCKOUT_DURATION as DEFAULT_LOCKOUT_DURATION,
    LOCKOUT_DURATION_MAXIMUM,
    LOCKOUT_THRESHOLD as DEFAULT_LOCKOUT_THRESHOLD,
    KNOWLEDGE_MAP_THROTTLE_RATE,
    PASSWORD_CHANGE_THROTTLE_RATE,
    PASSWORD_RESET_LINK_MINUTES,
    PICTURE_THROTTLE_RATE,
    SEARCH_THROTTLE_RATE,
    TAGGING_THROTTLE_RATE,
    TRANSCRIPTION_THROTTLE_RATE,
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

# --- Account lockout (FR-02 enforces, FR-03's configuration clause, D-130 decision 7) --------
# FR-03: "threshold and lockout duration are configuration values rather than literals, so the
# policy can be tightened without code changes." So they are .env variables, defaulting to
# apps/core/constants.py's LOCKOUT_THRESHOLD and LOCKOUT_DURATION (five failures, 15 minutes).
# - **Who reads them:** LoginView, at request time. The sign-in page reads them from GET
#   /api/auth/lockout-policy, so a change needs no front-end rebuild.
# - **When a change takes effect:** settings are read when the process starts, so a change
#   applies after a restart.
# - **The notice ceiling follows the threshold:** it is LOCKOUT_NOTICE_CEILING_FACTOR times it
#   (D-26).
# - **Tightened only** (Benjamin's decision 8, D-130): the server refuses to start on a threshold
#   outside 1 to 5, a duration outside 15 minutes to 365 days, or a value that is not a whole
#   number. Each refusal is an ImproperlyConfigured that names the variable. NFR-04's five attempts
#   and 15 minutes are the loosest the policy can be.

_DEFAULT_LOCKOUT_MINUTES = int(DEFAULT_LOCKOUT_DURATION.total_seconds() // 60)
_MAXIMUM_LOCKOUT_MINUTES = int(LOCKOUT_DURATION_MAXIMUM.total_seconds() // 60)
try:
    LOCKOUT_THRESHOLD = env.int("LOCKOUT_THRESHOLD", default=DEFAULT_LOCKOUT_THRESHOLD)
    _lockout_minutes = env.int("LOCKOUT_DURATION_MINUTES", default=_DEFAULT_LOCKOUT_MINUTES)
except ValueError as error:
    raise ImproperlyConfigured(
        "LOCKOUT_THRESHOLD and LOCKOUT_DURATION_MINUTES must be whole numbers"
    ) from error
if not 1 <= LOCKOUT_THRESHOLD <= DEFAULT_LOCKOUT_THRESHOLD:
    raise ImproperlyConfigured(
        f"LOCKOUT_THRESHOLD must be from 1 to {DEFAULT_LOCKOUT_THRESHOLD}: the policy may only be "
        f"tightened (FR-03, NFR-04), not {LOCKOUT_THRESHOLD}"
    )
# Compared as minutes before any timedelta is built, so no value can overflow one.
if not _DEFAULT_LOCKOUT_MINUTES <= _lockout_minutes <= _MAXIMUM_LOCKOUT_MINUTES:
    raise ImproperlyConfigured(
        f"LOCKOUT_DURATION_MINUTES must be from {_DEFAULT_LOCKOUT_MINUTES} to "
        f"{_MAXIMUM_LOCKOUT_MINUTES}: the policy may only be tightened (FR-03, NFR-04), not "
        f"{_lockout_minutes}"
    )
LOCKOUT_DURATION = timedelta(minutes=_lockout_minutes)

# --- The self-service password reset and its email (D-137) -----------------------------------
# D-137 (Benjamin's decision of 16 November 2026) builds the reset flow the proposal's section 1.9
# left out of scope. POST /api/auth/password-reset mails a link, and POST
# /api/auth/password-reset/confirm uses it (apps/accounts/password_reset.py). How the email goes is
# his answer, "A file outbox, SMTP optional":
#
# - **Without EMAIL_HOST, the default: the file outbox.** Each email is written as a file in
#   EMAIL_FILE_PATH, by default outbox/ under the repository root, which is gitignored. Nothing is
#   sent. Django makes the folder when it writes the first email.
# - **With EMAIL_HOST: SMTP,** on EMAIL_PORT (587) with STARTTLS (EMAIL_USE_TLS, on) or with SSL
#   from the first byte (EMAIL_USE_SSL, off). The two cannot both be on. Django's SMTP backend
#   would refuse that only when the first email is sent, in the background thread, where every
#   reset email would then fail unseen, so these settings refuse to load instead. EMAIL_TIMEOUT
#   bounds each wait on the mail server; Django's own default is no limit.
# - **A reset link's address comes from PUBLIC_BASE_URL alone,** never from the request or its Host
#   header. A link built from the Host header is the classic way to have a working reset link
#   mailed to a victim, pointing at someone else's site (D-137). The default is the alpha's own
#   address (D-64). A value that is not an absolute http or https address, or that carries a query
#   or a fragment, would make every link wrong, so it stops the server starting.
# - **A link works for PASSWORD_RESET_LINK_MINUTES** (60), Django's PASSWORD_RESET_TIMEOUT in
#   seconds, and once: a completed reset changes the password hash its token was made from.

EMAIL_HOST = env.str("EMAIL_HOST", default="")
if EMAIL_HOST:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_PORT = env.int("EMAIL_PORT", default=587)
    EMAIL_HOST_USER = env.str("EMAIL_HOST_USER", default="")
    EMAIL_HOST_PASSWORD = env.str("EMAIL_HOST_PASSWORD", default="")
    EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
    EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
    if EMAIL_USE_TLS and EMAIL_USE_SSL:
        raise ImproperlyConfigured(
            "EMAIL_USE_TLS and EMAIL_USE_SSL cannot both be true. For SMTP over SSL, usually on port "
            "465, set EMAIL_USE_SSL=True and EMAIL_USE_TLS=False; for STARTTLS, usually on port 587, "
            "leave EMAIL_USE_SSL unset"
        )
    EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=EMAIL_TIMEOUT_SECONDS)
else:
    EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
    EMAIL_FILE_PATH = Path(env.str("EMAIL_FILE_PATH", default=str(BASE_DIR / "outbox")))
DEFAULT_FROM_EMAIL = env.str("DEFAULT_FROM_EMAIL", default="no-reply@localhost")

PUBLIC_BASE_URL = env.str("PUBLIC_BASE_URL", default="http://127.0.0.1:8000").rstrip("/")
_public_base_url = urlsplit(PUBLIC_BASE_URL)
if (
    _public_base_url.scheme not in ("http", "https")
    or not _public_base_url.netloc
    or _public_base_url.query
    or _public_base_url.fragment
):
    raise ImproperlyConfigured(
        "PUBLIC_BASE_URL must be the absolute http:// or https:// address the platform is opened at, "
        f"with no query or fragment, not {PUBLIC_BASE_URL!r}"
    )

PASSWORD_RESET_TIMEOUT = PASSWORD_RESET_LINK_MINUTES * 60
# Where a reset email's work happens: "thread", a daemon thread per request, so the request does the
# same work whether or not the address has an account (D-25). The suite sets "inline", the caller's
# thread (conftest.py). Not read from the environment, because inline on a server would make a
# registered address take longer to answer, the difference the thread exists to remove.
PASSWORD_RESET_EMAIL_RUNNER = "thread"

# --- REST framework (CLAUDE.md section 6 invariant 4, D-21) -----------------------
# Every route is protected unless it opts out explicitly: registration and login (D-21), the
# lockout policy (D-130) and the two password-reset routes (D-137).
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
    #   it (D-26). Since D-137 also the password reset's two routes, on the same budget: each
    #   asking for a link starts a thread, and each setting a password runs the hasher.
    # - "ask", "ingestion" and "conversation_create": per signed-in user (D-79, D-80).
    #   "ingestion" is one budget shared by the three routes that ingest.
    # - "search" and "tagging": per signed-in user too, keyword search and a person applying a
    #   tag (D-79's two notes of 10 November 2026).
    # - "transcription": per signed-in user, one recording segment sent for transcription
    #   (D-123).
    # - "password_change": per signed-in user, a password change, wrong current passwords
    #   included (D-137).
    # - "picture": per signed-in user, a profile picture uploaded, refused ones included (D-137).
    # - "knowledge_map": per signed-in user, the knowledge map's two views in one budget
    #   (D-138).
    #
    # The counters live in the default cache, CACHES below: a per-process LocMemCache, so the one
    # Waitress process (D-64) shares them, a restart clears them, and a multi-process server would
    # need a shared cache.
    "DEFAULT_THROTTLE_RATES": {
        "auth": AUTHENTICATION_THROTTLE_RATE,
        "ask": ASK_THROTTLE_RATE,
        "ingestion": INGESTION_THROTTLE_RATE,
        "conversation_create": CONVERSATION_CREATE_THROTTLE_RATE,
        "search": SEARCH_THROTTLE_RATE,
        "knowledge_map": KNOWLEDGE_MAP_THROTTLE_RATE,
        "tagging": TAGGING_THROTTLE_RATE,
        "transcription": TRANSCRIPTION_THROTTLE_RATE,
        "action_items": ACTION_ITEM_THROTTLE_RATE,
        "password_change": PASSWORD_CHANGE_THROTTLE_RATE,
        "picture": PICTURE_THROTTLE_RATE,
    },
    # X-Forwarded-For is not trusted: an anonymous throttle is keyed on REMOTE_ADDR, the
    # connecting address. Unset, DRF keys it on the client-sent header, so the auth limit
    # could be dodged by changing that header on every request (D-79). Nothing sits in front
    # of the server today; if Stage 5 item 9 puts a reverse proxy there, it makes this 1.
    "NUM_PROXIES": 0,
}

# --- The default cache (the review of 17 November 2026, COR-2) -------------------------------
# It holds the throttle counts above, the in-flight slots (D-79, D-85, D-123) and D-137's password
# reset cooldown. Until 17 November no CACHES was set, so it was Django's LocMemCache with 300
# entries, which then dropped its least recently used third, expired or not: a slot or a cooldown,
# written once and never read, went first, and any 300 newer entries could push out a count. Still a
# per-process LocMemCache (apps/core/cache.py), with CACHE_MAX_ENTRIES places, dropping expired
# entries before live ones. Not read from the environment: it holds no credential or host.
CACHES = {
    "default": {
        "BACKEND": "apps.core.cache.ExpiredFirstLocMemCache",
        "OPTIONS": {"MAX_ENTRIES": CACHE_MAX_ENTRIES},
    }
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
# memory. A body over the ceiling never gets this far: the upload routes refuse it by its
# declared length before it is parsed (FR-08: "enforced before the file is written to
# storage"), and nothing upstream parses it (D-124).
#
# **Corrected 11 November 2026 (D-124).** From Stage 3 until then, this comment said the
# declared-length check ran "before the body is parsed at all". For any signed-in session
# holding the CSRF cookie it did not: DRF's CSRF check read request.POST, which parsed the whole
# body, multipart spooled past this threshold, before the 403, the 429 and the 413. Only
# Waitress's default 1 GB body limit bounded it. Now the CSRF check reads the header only
# (apps/api/authentication.py), and waitress-serve's --max-request-body-size
# (MAX_REQUEST_BODY_BYTES) bounds what is received on every route.
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

# anthropic (Claude + Voyage) is the default since D-122, after every tuned value was measured on
# it. flm (FastFlowLM on the NPU) is the local, offline alternative. The provider is chosen once,
# at setup, and a database keeps it (D-131): a change of provider means a new database.
AI_PROVIDER = env.str("AI_PROVIDER", default="anthropic")

# FastFlowLM on the local NPU: the offline alternative, AI_PROVIDER=flm, pinned to v0.9.39 (D-83).
FLM_BASE_URL = env.str("FLM_BASE_URL", default="http://127.0.0.1:52625/v1")
FLM_API_KEY = env.str("FLM_API_KEY", default="flm")  # placeholder, not a credential
FLM_CHAT_MODEL = env.str("FLM_CHAT_MODEL", default="gemma3:4b")
FLM_EMBED_MODEL = env.str("FLM_EMBED_MODEL", default="embed-gemma")

# Recording transcription (D-123), selected independently of AI_PROVIDER, because only FLM
# has speech-to-text: Claude and Voyage have none. "none" (the default) leaves it off, so a host
# without the NPU (D-114) offers no control that cannot work; "flm" sends each segment to
# whisper-v3:turbo on the FLM server at FLM_BASE_URL, which must be started with --asr 1.
TRANSCRIPTION_PROVIDER = env.str("TRANSCRIPTION_PROVIDER", default="none")
FLM_ASR_MODEL = env.str("FLM_ASR_MODEL", default="whisper-v3:turbo")

# Where a meeting summary's run happens (FR-16, D-125). The route that asks for one answers 202
# and the run follows: "thread" (the default) is a background thread of this server process,
# because the stack has no task queue; "inline" runs it in the caller's thread, which the test
# suite uses. apps/meetings/summary_runner.py reads it.
SUMMARY_RUNNER = env.str("SUMMARY_RUNNER", default="thread")
if SUMMARY_RUNNER not in ("thread", "inline"):
    raise ImproperlyConfigured(f"Unknown SUMMARY_RUNNER: {SUMMARY_RUNNER!r} (expected 'thread' or 'inline')")

# Length of the vectors the configured embedding model returns (docs/decisions.md D-03). It follows
# the provider (D-131): EMBEDDING_DIMENSION_BY_PROVIDER, 1024 for voyage-4 and 768 for FLM's
# embed-gemma. The pgvector columns are sized from this when the first migrate runs, and a database
# keeps that width. An EMBEDDING_DIMENSION in .env is still read, so an existing .env keeps working,
# but one that disagrees with the provider stops every command that runs the checks (ai.E004).
# An unknown AI_PROVIDER is refused at startup (ai.E002), so its fallback is only a placeholder.
EMBEDDING_DIMENSION = env.int(
    "EMBEDDING_DIMENSION",
    default=EMBEDDING_DIMENSION_BY_PROVIDER.get(AI_PROVIDER, EMBEDDING_DIMENSION_BY_PROVIDER["anthropic"]),
)

# Claude + Voyage: the proposal's production configuration, funded since D-113 and the default
# since D-122.
ANTHROPIC_API_KEY = env.str("ANTHROPIC_API_KEY", default="")
# Haiku 5.5 (D-121): it matched Sonnet 5.5 on every bar of the Haiku round, faster and at a
# twentieth of the price. ANTHROPIC_MODEL=claude-sonnet-5-5 goes back to D-115's model. The same
# setting selects FR-10's classification model; Haiku's confidence threshold is D-122's.
ANTHROPIC_MODEL = env.str("ANTHROPIC_MODEL", default="claude-haiku-5-5")
VOYAGE_API_KEY = env.str("VOYAGE_API_KEY", default="")
VOYAGE_MODEL = env.str("VOYAGE_MODEL", default="voyage-4")
VOYAGE_BASE_URL = env.str("VOYAGE_BASE_URL", default="https://api.voyageai.com/v1")
