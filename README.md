# Project 8 — Organisational Knowledge Management Platform

VU IT Capstone (NIT3003 / NIT3004). The backend is Django 5 with DRF, the database is PostgreSQL 16
with pgvector, and the frontend is React with Vite. Answers, document classification and summaries,
and meeting summaries come from **Claude Haiku 5.5**, and embeddings from **Voyage `voyage-4`**: the
`anthropic` provider, the default since D-122. FastFlowLM on the AMD Ryzen AI NPU is the offline
alternative.

Read `CLAUDE.md` before changing anything. The other documents you will reach for:

- **`docs/decisions.md`** holds every settled decision, numbered from D-01. It is long, so search it
  for the number.
- **`docs/api-contract.md`** lists every route and its request and response shapes. The front end
  builds against it.
- **`docs/schema-v1.md`** defines every table and the fixed vocabularies.
- **`docs/ai-provider.md`** defines the contract every AI provider must meet.
- **`docs/alpha-deployment.md`** is the runbook for the deployed alpha.
- **`docs/measurement-runbook.md`** gives the exact steps for one measured run (Objectives 02 and
  03).
- **`docs/demonstration-script.md`** walks the twelve M6 requirements on the alpha.
- **`M6-BUILD-PROMPT.md`** is Stage 5's brief for the M6 gate. Its closing audits are D-140 and
  D-141, and the briefs of earlier stages are in its git history.
- **`frontend/README.md`** holds the front end's own notes.

## Prerequisites

- **Windows 11 with native PowerShell.** The commands below, the scripts and the runbooks are written
  for it. With the default provider nothing depends on the NPU, but no other platform has been
  tested.
- **[uv](https://docs.astral.sh/uv/),** for Python and package management.
- **Docker Desktop,** for the local PostgreSQL + pgvector database.
- **Node.js 24, version 24.15 or later, with npm,** for the front end. The front-end suite runs in
  jsdom, which needs 24.15, and CI uses Node 24.
- **An Anthropic API key and a Voyage API key.** Both go in `.env` only, never in a commit or a
  chat.
  - At Haiku 5.5's measured rate a question costs about 0.05¢ (D-121).
  - Your Anthropic account's usage tier sets its rate limits.
- **Optional: FastFlowLM (`flm`) v0.9.39 exactly,** for the offline provider and for transcribing
  meeting recordings, both below.

## Setup

```powershell
# 1. Python 3.12 (pinned in .python-version) and a virtual environment.
#    Windows Smart App Control blocks the uv-built venv's unsigned python.exe
#    ("An Application Control policy has blocked this file"). Turning Smart App
#    Control off may not be reversible without reinstalling Windows.
uv python install 3.12
uv venv --python 3.12
uv pip sync --python .venv/Scripts/python.exe requirements.txt

# 2. Local configuration (.env is gitignored; never commit it). Choose the provider now:
#    AI_PROVIDER=anthropic, with ANTHROPIC_API_KEY and VOYAGE_API_KEY, or flm. A database
#    keeps the provider it was set up with (D-131), so this is chosen once.
Copy-Item .env.example .env

# 3. PostgreSQL 16 + pgvector, the same database for every developer
docker compose up -d

# 4. Build the schema from empty. The vector columns take AI_PROVIDER's width, and keep it:
#    1024 for anthropic (voyage-4), 768 for flm (embed-gemma).
.venv/Scripts/python.exe manage.py migrate

# 5. Check the provider, then run the back-end suite (it never touches a provider or the network)
.venv/Scripts/python.exe manage.py check
.venv/Scripts/python.exe -m pytest
```

`manage.py check`, `migrate` and `runserver` probe the provider when they start:

- **Anthropic's health check and one Voyage embedding,** checking the vectors are
  `EMBEDDING_DIMENSION` wide.
- **A missing key or an unreachable provider is a warning.** The command continues, and the API
  answers 503 until the provider is back.
- **A dimension mismatch is a hard stop** (`docs/ai-provider.md` section 4).
- **So is a database set up for the other provider** (ai.E005), and an `EMBEDDING_DIMENSION` in
  `.env` that disagrees with `AI_PROVIDER` (ai.E004). The width follows the provider, so `.env`
  needs no `EMBEDDING_DIMENSION` (D-131).

**The password reset's email (D-137) needs nothing in `.env` to run.** `.env.example` documents
its settings:

- **Without `EMAIL_HOST`, nothing is sent.** Each email is written as a file to `outbox/`
  (`EMAIL_FILE_PATH`), which is gitignored. A reset email there holds a link that lets whoever
  opens it set that account's password, once, within 60 minutes, so keep the folder as private as
  the database. `EMAIL_HOST` and the other `EMAIL_*` settings send by SMTP instead, and
  `DEFAULT_FROM_EMAIL` names the sender.
- **Every reset link starts with `PUBLIC_BASE_URL`,** never with the request's address. The
  default, `http://127.0.0.1:8000`, is the alpha's. In development the browser talks to Vite
  (below), so for a link to open there, put `PUBLIC_BASE_URL=http://localhost:5173` in `.env`. A
  malformed value stops Django starting.

## The AI provider

`AI_PROVIDER` in `.env` selects it. Application code never names a provider; it calls
`apps.ai.get_ai_service()` (`CLAUDE.md` section 4).

### Anthropic + Voyage (the default)

Nothing to start. With both keys in `.env`, the server calls Claude and Voyage directly.

- **Generation, FR-10's classification and summaries, and FR-16's meeting summaries use
  `ANTHROPIC_MODEL`,** `claude-haiku-5-5` by default (D-121). `claude-sonnet-5-5` is the
  alternative: on generation it measured the same results at twenty times the price.
- **Embeddings come from `voyage-4` at 1024 dimensions.** Questions and passages are embedded as
  queries and documents respectively (D-116).
- **These tuned values were measured on this provider before it became the default** (D-122):
  - the relevance threshold and the partial-match floor (D-120);
  - FR-19's grouping threshold;
  - FR-10's confidence threshold.

  Each is per model, so FLM keeps its own values.
- **One check was not run first:** D-108's check of FR-19's permission exclusion. Run the day after
  the default moved, it failed on voyage-4, and the exclusion rule became per model too (D-126).

### FastFlowLM, the offline alternative

FastFlowLM runs `gemma3:4b` and `embed-gemma` on the NPU. It needs no keys and no network, and
embeds at 768 dimensions. In `.env`:

```
AI_PROVIDER=flm
```

The width, 768, follows from it. Point `DATABASE_URL` at a database set up under FLM.

**Set FastFlowLM's port first, once on each machine.** FastFlowLM's own default is 52625, which can
fall inside a range Windows reserves for Hyper-V, so this project uses 8625, the port in
`FLM_BASE_URL`:

```powershell
[Environment]::SetEnvironmentVariable('FLM_SERVE_PORT', '8625', 'User')
```

Open a new PowerShell window afterwards and run `flm port`, which must print 8625. Passing
`--port 8625` to every `flm serve` command in this file does the same without the variable.

Then start the server in a second PowerShell window, left running for the session:

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

### Transcribing meeting recordings (Whisper on FLM)

The meetings page can turn a meeting recording into a draft transcript, which a person reviews
and then adds as an ordinary transcript (D-123). Only FLM has speech-to-text, so this needs
FLM on the NPU laptop whichever `AI_PROVIDER` is set. It is off unless `.env` says:

```
TRANSCRIPTION_PROVIDER=flm
```

Set FastFlowLM's port to 8625 first, as "FastFlowLM, the offline alternative" above describes:
`flm port` must print 8625. Pull the speech model once (623 MB), then serve it beside `gemma3:4b`
and `embed-gemma` with `--asr 1`:

```powershell
flm pull whisper-v3:turbo
```

```powershell
flm serve gemma3:4b --embed 1 --asr 1
```

- **Check for an FLM server already running first** (`Get-Process flm`). Windows lets a second
  `flm serve` process listen on port 8625 beside the first; requests then go to either, and the
  newer one could not load its model. Stop the old one before starting this one.
- **The recording stays in the browser.** The page decodes it (audio, or the sound of a video such
  as a Game Bar MP4, up to 500 MB) and sends it to `POST /api/transcriptions` in WAV segments of
  about 30 s. FLM transcribes at about a quarter of real time, so an hour's meeting takes about fifteen
  minutes.
- **Nothing is added until a person ticks that they reviewed the draft.** Whisper mishears names,
  numbers and dates, and writes dates the US way.
- **A host without the NPU** keeps `TRANSCRIPTION_PROVIDER=none`. The draft can be saved as a text
  file on the laptop and added on that host as a transcript file.

### One database, one provider

**You cannot change providers once a database has been set up for one.** The provider is chosen
once, with `AI_PROVIDER` in `.env` before the first `migrate`, and the database keeps it (D-131):

- **Its vector columns have one width,** fixed by its first `migrate`: 1024 for Voyage, 768 for
  FLM.
- **Retrieval only reads chunks embedded by the model the question is embedded with** (risk R10).
- **The startup check refuses a database set up for the other provider** (ai.E005), so
  `runserver`, `migrate` and `check` stop rather than use it.

**No command moves a database to the other provider.** `reindex --resize-column`, which did
(D-117), was removed with D-131, and `reindex` now rebuilds chunks with the database's own provider
only.

**The other provider needs a database of its own,** set up from empty:
1. create it, under a new name, in the database container:

   ```powershell
   docker compose exec db createdb -U kmp kmp_flm
   ```

2. in that checkout's `.env`, point `DATABASE_URL` at it
   (`postgres://kmp:kmp@127.0.0.1:5432/kmp_flm`) and set `AI_PROVIDER`;
3. run `migrate`;
4. ingest the content again through the API.

The alpha's database was built that way on 13 November 2026
(`corpus/objective-02/runs/2026-11-13-alpha-anthropic/`).

## Running the application

Two windows (three on FLM, with its server above). The API first:

```powershell
# The API, on http://127.0.0.1:8000/
.venv/Scripts/python.exe manage.py runserver
```

Then the front end, in its own window:

```powershell
cd frontend
npm ci          # after a fresh clone, and after any pull that changes package-lock.json
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

**The front end has its own suite,** and `main` must pass it as well as `pytest` (`CLAUDE.md`
section 7). It needs no server: `tests/setup.js` fails any test that reaches the network. From
`frontend`:

```powershell
npm test
```

CI also runs `npm run lint` and `npm run build`.

**The alpha is different** (Stage 5 item 9, D-64).

- **How it serves:** Django under Waitress serves the production build (`frontend/dist`) and `/api`
  from one origin, `http://127.0.0.1:8000`, with `DEBUG=False` and no Vite server.
- **It ran on FLM** at M6, on `kmp_demo_20261101`, which is kept. Since 13 November 2026 it runs
  on Anthropic, on `kmp_alpha_20261113`, a database built for it (D-131).
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

Passwords must satisfy FR-01's complexity rules, on this path as on any other. The numbers are in
`apps/core/constants.py`:

- **The server applies them** through `ComplexityValidator` in `apps/accounts/validators.py`, and
  the minimum length also through Django's `MinimumLengthValidator` in `config/settings.py`.
- **`frontend/src/utils/password.js` holds its own copy,** for the registration, password-reset and
  profile forms. `apps/accounts/tests/test_password_policy_agreement.py` fails when the two differ.

This file deliberately does not state them.

## Dependencies

`requirements.in` lists the direct dependencies, pinned. `requirements.txt` is the compiled lock
that CI and every developer install. To change a dependency, edit `requirements.in`, then:

```powershell
uv pip compile requirements.in -o requirements.txt --python-version 3.12
uv pip sync --python .venv/Scripts/python.exe requirements.txt
```

Sync again after any pull that changes `requirements.txt`. D-137's Pillow, which re-encodes
profile pictures, is one: the API imports it, so a venv synced before it fails `manage.py check`.

## After a pull

- **Python packages:** sync again when `requirements.txt` changed (above).
- **Front-end packages:** run `npm ci` in `frontend` when `package-lock.json` changed.
- **Schema:** run `.venv/Scripts/python.exe manage.py migrate`.

**A database set up before a feature keeps its older rows without it.** Documents classified
before `documents` 0016 have no summary (D-139), and meetings stored before FR-16 have none
(D-125). After `migrate`, two commands write them through the provider. A meeting costs one
request. A document costs one request, or, where it is longer than 1,500 tokens
(`CLASSIFICATION_INPUT_TOKENS`), one request per section, up to eight, and a final one (D-139). A
request that fails is tried up to three times:

```powershell
.venv/Scripts/python.exe manage.py summarise_documents
.venv/Scripts/python.exe manage.py summarise_meetings --missing
```

Both refuse the database named `kmp`, the one `.env.example` and `docker-compose.yml` set up (D-84
decision 1). On `kmp`, **Generate Summary** on a meeting's page writes that meeting's summary. A
document that is already classified has no such control: **Classify now** shows only on a document
that was never classified.
