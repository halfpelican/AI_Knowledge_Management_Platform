# Project 8 — Organisational Knowledge Management Platform

VU IT Capstone (NIT3003 / NIT3004). The backend is Django 5 with DRF, the database is PostgreSQL 16
with pgvector, and the frontend is React with Vite. Answers and document classification come from
**Claude Haiku 5.5**, and embeddings from **Voyage `voyage-4`**: the `anthropic` provider, the
default since D-122. FastFlowLM on the AMD Ryzen AI NPU is the offline alternative.

Read `CLAUDE.md` before changing anything. The build plan is `M6-BUILD-PROMPT.md`, and every
settled decision is in `docs/decisions.md`.

## Prerequisites

- **Windows 11 with native PowerShell.** The commands below, the scripts and the runbooks are written
  for it. With the default provider nothing depends on the NPU, but no other platform has been
  tested.
- **[uv](https://docs.astral.sh/uv/),** for Python and package management.
- **Docker Desktop,** for the local PostgreSQL + pgvector database.
- **An Anthropic API key and a Voyage API key.** Both go in `.env` only, never in a commit or a
  chat.
  - At Haiku 5.5's measured rate a question costs about 0.05¢ (D-121).
  - Your Anthropic account's usage tier sets its rate limits.
- **Optional: FastFlowLM (`flm`) v0.9.39 exactly,** only for the offline provider below.

## Setup

```powershell
# 1. Python 3.12 (pinned in .python-version) and a virtual environment.
#    Windows Smart App Control blocks the uv-built venv's unsigned python.exe
#    ("An Application Control policy has blocked this file"). Turning Smart App
#    Control off may not be reversible without reinstalling Windows.
uv python install 3.12
uv venv --python 3.12
uv pip sync --python .venv/Scripts/python.exe requirements.txt

# 2. Local configuration (.env is gitignored; never commit it). Then open .env and set
#    ANTHROPIC_API_KEY and VOYAGE_API_KEY.
Copy-Item .env.example .env

# 3. PostgreSQL 16 + pgvector, the same database for every developer
docker compose up -d

# 4. Build the schema from empty. The vector column is created EMBEDDING_DIMENSION wide:
#    1024, Voyage's width, unless .env says otherwise.
.venv/Scripts/python.exe manage.py migrate

# 5. Check the provider, then run the suite (the suite never touches a provider or the network)
.venv/Scripts/python.exe manage.py check
.venv/Scripts/python.exe -m pytest
```

`manage.py check`, `migrate` and `runserver` probe the provider when they start:

- **Anthropic's health check and one Voyage embedding,** checking the vectors are
  `EMBEDDING_DIMENSION` wide.
- **A missing key or an unreachable provider is a warning.** The command continues, and the API
  answers 503 until the provider is back.
- **A dimension mismatch is a hard stop** (`docs/ai-provider.md` section 4).

## The AI provider

`AI_PROVIDER` in `.env` selects it. Application code never names a provider; it calls
`apps.ai.get_ai_service()` (`CLAUDE.md` section 4).

### Anthropic + Voyage (the default)

Nothing to start. With both keys in `.env`, the server calls Claude and Voyage directly.

- **Generation and FR-10's classification use `ANTHROPIC_MODEL`,** `claude-haiku-5-5` by default
  (D-121). `claude-sonnet-5-5` is the alternative, measured to the same results at twenty times the
  price.
- **Embeddings come from `voyage-4` at 1024 dimensions.** Questions and passages are embedded as
  queries and documents respectively (D-116).
- **Every tuned value was measured on this provider before it became the default** (D-122):
  - the relevance threshold and the partial-match floor (D-120);
  - FR-19's grouping threshold;
  - FR-10's confidence threshold.

  Each is per model, so FLM keeps its own values.

### FastFlowLM, the offline alternative

FastFlowLM runs `gemma3:4b` and `embed-gemma` on the NPU. It needs no keys and no network, and
embeds at 768 dimensions. In `.env`:

```
AI_PROVIDER=flm
EMBEDDING_DIMENSION=768
```

Point `DATABASE_URL` at a database indexed by FLM, then start the server in a second PowerShell
window, left running for the session:

```powershell
flm serve gemma3:4b --embed 1
```

That serves both models at `http://127.0.0.1:8625/v1`.

- **The version must be v0.9.39** (`flm version`). From v1.0.4 onward its embeddings are
  non-deterministic (upstream ROCm/FastFlowLM#732), so retrieval returns noise while chat still
  works (D-83).
- **Before any measurement, load test or demonstration on FLM,** run
  `.venv/Scripts/python.exe scripts/check_flm.py`. It fails, exiting 1, when the embeddings are not
  deterministic.

### Switching an existing database

A database is indexed for one provider at a time:

- **The vector column has one width:** 1024 for Voyage, 768 for FLM.
- **Retrieval only reads chunks embedded by the model the question is embedded with** (risk R10). A
  database indexed for the other provider therefore answers nothing, rather than answering wrongly.

To move a database across, set the provider and the dimension in `.env`, then rebuild its chunks:

```powershell
.venv/Scripts/python.exe manage.py reindex --provider anthropic --resize-column <database name>
```

- **What it does:** it deletes every chunk, resizes the column and re-embeds every document and
  transcript (D-117).
- **What it refuses:** the name must match the database `.env` connects to.
- **Going back:** `--provider flm` with `EMBEDDING_DIMENSION=768` returns a database to FLM.

`CLAUDE.md` asks for a provider switch to land on a fresh database. The usual way is a copy:
restore a snapshot under a new name with `scripts/snapshot_measurement_db.py restore --into`, then
re-index that copy. `docs/measurement-runbook.md` ("A copy for another provider") has the commands.

## Running the application

Two windows (three on FLM, with its server above). The API first:

```powershell
# The API, on http://127.0.0.1:8000/
.venv/Scripts/python.exe manage.py runserver
```

Then the front end, in its own window:

```powershell
cd frontend
npm install     # first clone only
npm run dev
```

Open **http://localhost:5173/**. Vite listens on the IPv6 loopback, so `http://127.0.0.1:5173/` is
refused where `localhost:5173` answers: on this stack the two names are not interchangeable.

Both servers have to be running. The browser only ever talks to Vite:

- **`/api` is proxied** from Vite to Django on port 8000, so the session cookie is same-origin and
  there is no CORS configuration anywhere (D-21).
- **In development, port 8000 serves the API and nothing else:** no server-rendered pages, no admin
  site. So it is the wrong address to open in a browser.
- **With Django stopped,** the interface loads but every request from it fails.

`frontend/README.md` has the rest: Node version, the component sheet, lint and build.

**The alpha is different** (Stage 5 item 9, D-64).

- **How it serves:** Django under Waitress serves the production build (`frontend/dist`) and `/api`
  from one origin, `http://127.0.0.1:8000`, with `DEBUG=False` and no Vite server.
- **It ran on FLM** at M6. Its database is indexed at 768, so running it as it was needs
  `AI_PROVIDER=flm` and `EMBEDDING_DIMENSION=768`.
- **The runbook** is `docs/alpha-deployment.md`.
- **`frontend/dist` also affects development.** Once it has been built, `runserver` on port 8000
  serves that build too, so delete `frontend/dist` to get development's API-only port 8000 back.

## First-run accounts

A migrated database holds the two roles and no users. There is no seed command, and no Django admin
to make the first one with (D-26). Make it from the command line:

```powershell
.venv/Scripts/python.exe manage.py createsuperuser
```

It prompts for an email address, a name and a password.

- **"Superuser" is Django's word for the command,** not a concept this product has. The user model
  carries no staff or superuser flag, and there is no admin site to sign in to.
- **So `create_superuser()` assigns the Administrator role,** and that is the whole of its effect.
  Sign in with it at `/login`.

Registering at `/register` will not produce one. FR-01 gives every registration the Employee role:

- **The role is set in the manager,** not the view, and no field on the request could ask for
  another. That is what the requirement specifies.
- **So a database whose accounts all came through the form has no Administrator,** and no way to
  reach `/admin/roles` (FR-05).

To promote an account that has already registered, including your own if you signed up through the
form first, do it once from the shell:

```powershell
.venv/Scripts/python.exe manage.py shell
```

```python
from apps.accounts.models import Role, User

user = User.objects.get(email="you@example.com")
user.role = Role.objects.get(role_name="Administrator")
user.save(update_fields=["role"])
```

That writes the column directly, and so goes around FR-05's guard against emptying the
Administrator set (D-26). Promoting can only add one, but the same snippet with `Employee` would
happily remove the last. Once an Administrator exists, every further role change belongs on
`/admin/roles`, which enforces the guard.

Passwords must satisfy FR-01's complexity rules, on this path as on any other. Only two places state
them:

- **`apps/accounts/validators.py`** (`ComplexityValidator`), for the server;
- **`frontend/src/utils/password.js`,** which mirrors them for the registration form.

This file deliberately does not become a third.

## Dependencies

`requirements.in` lists the direct dependencies, pinned. `requirements.txt` is the compiled lock
that CI and every developer install. To change a dependency, edit `requirements.in`, then:

```powershell
uv pip compile requirements.in -o requirements.txt --python-version 3.12
uv pip sync --python .venv/Scripts/python.exe requirements.txt
```
