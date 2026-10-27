# Project 8 — Organisational Knowledge Management Platform

VU IT Capstone (NIT3003 / NIT3004). Django 5 + DRF backend, PostgreSQL 16 with
pgvector, React + Vite frontend, and local AI inference through FastFlowLM on the
AMD Ryzen AI NPU. Read `CLAUDE.md` before changing anything; the build plan is
`M6-BUILD-PROMPT.md` and open decisions live in `docs/decisions.md`.

## Prerequisites

- Windows 11, native PowerShell (not WSL: the NPU is not visible from WSL2)
- [uv](https://docs.astral.sh/uv/) for Python and package management
- Docker Desktop, for the local PostgreSQL + pgvector database
- FastFlowLM (`flm`) with the `gemma3:4b` and `embed-gemma` models pulled

## Setup

```powershell
# 1. Python 3.12 (pinned in .python-version) and a virtual environment.
#    Windows Smart App Control blocks the uv-built venv's unsigned python.exe
#    ("An Application Control policy has blocked this file"). Turning Smart App
#    Control off may not be reversible without reinstalling Windows.
uv python install 3.12
uv venv --python 3.12
uv pip sync --python .venv/Scripts/python.exe requirements.txt

# 2. Local configuration (.env is gitignored; never commit it)
Copy-Item .env.example .env

# 3. PostgreSQL 16 + pgvector, the same database for every developer
docker compose up -d

# 4. Build the schema from empty
.venv/Scripts/python.exe manage.py migrate

# 5. Run the suite (never touches the AI provider or the network)
.venv/Scripts/python.exe manage.py check
.venv/Scripts/python.exe -m pytest
```

## Starting the AI provider

In a second PowerShell window, left running for the session:

```powershell
flm serve gemma3:4b --embed 1
```

That serves `gemma3:4b` for generation and `embed-gemma` (768 dimensions) for
embeddings at `http://127.0.0.1:8625/v1`. Confirm it with
`python scripts/check_flm.py`. `manage.py check`, `migrate` and `runserver` probe
the provider on start: a warning if it is unreachable, a hard stop if the
embedding dimension does not match `EMBEDDING_DIMENSION` (`docs/ai-provider.md`
section 4).

## Running the application

Two more windows, alongside the provider above. The API first:

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

Open **http://localhost:5173/**. Vite listens on the IPv6 loopback, so
`http://127.0.0.1:5173/` is refused where `localhost:5173` answers; on this stack the
two names are not interchangeable.

Both servers have to be running. The browser only ever talks to Vite: `/api` is
proxied from there to Django on port 8000, so the session cookie is same-origin and
there is no CORS configuration anywhere (D-21). Port 8000 serves the API and nothing
else — no server-rendered pages, no admin site — so it is the wrong address to open
in a browser. With Django stopped, the interface loads and every request from it
fails. `frontend/README.md` has the rest: Node version, the component sheet, lint
and build.

## First-run accounts

A migrated database holds the two roles and no users, and there is no seed command
and no Django admin to make the first one with (D-26). Make it from the command line:

```powershell
.venv/Scripts/python.exe manage.py createsuperuser
```

It prompts for an email address, a name and a password. "Superuser" is Django's word
for the command, not a concept this product has: the user model carries no staff or
superuser flag and there is no admin site to sign in to, so `create_superuser()`
assigns the **Administrator** role and that is the whole of its effect. Sign in
with it at `/login`.

Registering at `/register` will not produce one. FR-01 gives every registration the
Employee role — in the manager rather than the view, and with no field on the request
that could ask for another — which is what the requirement specifies, and is also why
a database whose accounts all came through the form has no Administrator in it, and
so no way to reach `/admin/roles` (FR-05).

To promote an account that has already registered, including your own if you signed
up through the form before reading this, do it once from the shell:

```powershell
.venv/Scripts/python.exe manage.py shell
```

```python
from apps.accounts.models import Role, User

user = User.objects.get(email="you@example.com")
user.role = Role.objects.get(role_name="Administrator")
user.save(update_fields=["role"])
```

That writes the column directly and so goes around FR-05's guard against emptying
the administrator set (D-26): promoting can only add one, but the same snippet with
`Employee` would happily remove the last. Once an Administrator exists, every further
role change belongs on `/admin/roles`, which enforces the guard.

Passwords must satisfy FR-01's complexity rules, on this path as on any other.
`apps/accounts/validators.py` (`ComplexityValidator`) states them for the server and
`frontend/src/utils/password.js` mirrors them for the registration form; those two
are the only statement of the rules, and this file deliberately does not become a
third.

## Dependencies

`requirements.in` lists the direct dependencies, pinned. `requirements.txt` is the
compiled lock that CI and every developer install. To change a dependency, edit
`requirements.in`, then:

```powershell
uv pip compile requirements.in -o requirements.txt --python-version 3.12
uv pip sync --python .venv/Scripts/python.exe requirements.txt
```
