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
# 1. Python 3.12 (pinned in .python-version) and a virtual environment
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
embeddings at `http://127.0.0.1:52625/v1`. Confirm it with
`python scripts/check_flm.py`. `manage.py check`, `migrate` and `runserver` probe
the provider on start: a warning if it is unreachable, a hard stop if the
embedding dimension does not match `EMBEDDING_DIMENSION` (`docs/ai-provider.md`
section 4).

## Dependencies

`requirements.in` lists the direct dependencies, pinned. `requirements.txt` is the
compiled lock that CI and every developer install. To change a dependency, edit
`requirements.in`, then:

```powershell
uv pip compile requirements.in -o requirements.txt --python-version 3.12
uv pip sync --python .venv/Scripts/python.exe requirements.txt
```
