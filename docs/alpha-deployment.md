# Alpha deployment runbook

Stage 5 item 9, as D-64 settles it: the M6 alpha runs on the NPU laptop and is used on that
laptop. It is served by Waitress with 24 threads (D-85), under `DEBUG=False`, with the production
build of the front end and `/api` on one origin, `http://127.0.0.1:8000`. These are the exact
steps to deploy it from `main`, in native Windows PowerShell (not WSL: the NPU is not visible
there).

> **Registration (FR-01) is open to anyone who can reach the address.** That is why the alpha
> stays on loopback. `--listen=127.0.0.1:8000` accepts connections from this laptop only. Do not
> listen on `0.0.0.0` or a LAN address, open a firewall port, or put a tunnel in front of it. Each
> of those would let anyone who can reach the laptop register an Employee account, and each is a
> new decision with that question attached (D-64), not a change to this runbook.

**The measured run uses the same port.** `docs/measurement-runbook.md` serves Waitress on
`127.0.0.1:8000` from its own database. Only one server can listen there, so finish or stop the
measured run first. Never point the alpha at the measurement database.

**Before you start:**

- the commit to deploy is merged to `main`, and CI passed on it;
- Docker Desktop is running, with the database up (`docker compose up -d`);
- `flm` is v0.9.39, with `gemma3:4b` and `embed-gemma` pulled (`README.md`, D-83);
- Node and npm are installed (`node --version`).

## 1. The code

```powershell
$root = 'C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype'
$py   = "$root\.venv\Scripts\python.exe"
Set-Location $root
git switch main
git pull --ff-only
git status --porcelain     # must print nothing, so the commit recorded in step 7 is what runs
```

## 2. FLM

In its own PowerShell window, left running:

```powershell
flm serve gemma3:4b --embed 1
```

Then, in the deployment window:

```powershell
flm version                                     # must say v0.9.39 (D-83). Anything else: stop here.
$env:FLM_BASE_URL = 'http://127.0.0.1:8625/v1'  # the URL .env names; check_flm.py reads the shell, not .env
& $py scripts\check_flm.py
$LASTEXITCODE                                   # must be 0
```

`check_flm.py` exits 1 if the embeddings are not deterministic. Do not deploy past that.

## 3. Python dependencies

```powershell
uv pip sync --python .venv/Scripts/python.exe requirements.txt
```

That makes the venv match `requirements.txt` exactly. Since item 9 that includes
`whitenoise==6.12.0`, which serves the built SPA. The venv is shared by every worktree, so a
later sync from a checkout whose `requirements.txt` predates item 9 removes WhiteNoise again.

## 4. The environment, then the database

Set these in the window that will run the server. They apply to the `manage.py` commands run in
the same window too.

```powershell
$env:DEBUG                 = 'False'      # .env sets DEBUG=True; the shell's value wins over .env
$env:ALLOWED_HOSTS         = '127.0.0.1,localhost'
$env:CSRF_TRUSTED_ORIGINS  = 'http://127.0.0.1:8000,http://localhost:8000'
$env:SESSION_COOKIE_SECURE = 'False'      # plain HTTP on loopback (D-64)
$env:CSRF_COOKIE_SECURE    = 'False'
$env:SPA_DIST_DIR          = "$root\frontend\dist"
$env:WAITRESS_LOG_PATH     = "$root\logs\waitress.log"   # Waitress's own log (D-87)
$env:FLM_BASE_URL          = 'http://127.0.0.1:8625/v1'
```

- **Only `DEBUG` differs from its default.** The others are set anyway, so the window shows the
  configuration that runs, and a stray line in `.env` cannot change it.
- **`DATABASE_URL` and `MEDIA_ROOT` come from `.env`** unless the demonstration database is a
  different one. Then set both here, together, because a database's documents are stored in its
  `MEDIA_ROOT`.

```powershell
& $py manage.py migrate
& $py manage.py check --deploy
```

`migrate` is safe to run on a database that already holds the demonstration corpus. Re-indexing,
reprocessing or deleting is not (D-40).

**`check --deploy` on loopback HTTP** should report exactly four warnings, all about HTTPS, which
D-64 puts out of scope for the alpha (NFR-03's scan moves to round 2):

- `security.W004` (HSTS)
- `security.W008` (SSL redirect)
- `security.W012` (`SESSION_COOKIE_SECURE`)
- `security.W016` (`CSRF_COOKIE_SECURE`)

Anything else is a stop:

- `ai.W001` means FLM is unreachable. Go back to step 2.
- `security.W009` means `SECRET_KEY` is weak, as `.env.example`'s `change-me-dev-only` is. Generate
  one, put it in `.env` as `SECRET_KEY=...`, and run the check again:

  ```powershell
  & $py -c "import secrets; print(secrets.token_urlsafe(50))"
  ```

  The key uses letters, digits, `-` and `_` only, so `.env` reads it as written. Changing the key
  signs everyone out, because sessions are signed with it. Stored passwords and data are not
  affected.

## 5. The front end

```powershell
Set-Location "$root\frontend"
npm ci
npm run build
Set-Location $root
Get-ChildItem "$root\frontend\dist", "$root\frontend\dist\assets"
```

The build writes `frontend\dist`: `index.html`, `favicon.svg`, and `assets\index-<hash>.js` and
`.css`.

- **Leave `VITE_API_BASE_URL` unset, or `/api`.** The SPA must call `/api` on its own origin. The
  session and CSRF cookies are `SameSite=Lax`, so with an address on another origin, sign-in would
  appear to succeed and every call after it would fail.
- **There is no `collectstatic`.** WhiteNoise serves `frontend\dist` where it is
  (`WHITENOISE_ROOT`), and `django.contrib.staticfiles` is not installed.
- **Build before starting the server.** WhiteNoise reads the folder once, at start-up, so a rebuild
  needs a restart.

## 6. Start the server

In the window from step 4:

```powershell
& "$root\.venv\Scripts\waitress-serve.exe" --listen=127.0.0.1:8000 --threads=24 config.wsgi:application
```

- **24 threads, set explicitly** (D-85). Waitress defaults to 4.
- **The console stays quiet.** Waitress's own lines go to `WAITRESS_LOG_PATH` (D-87). From another
  window, `Get-Content "$root\logs\waitress.log" -Tail 1` shows
  `Serving on http://127.0.0.1:8000`.
- **`UserWarning: No directory at: ...frontend\dist\`** in the console means there is no build at
  `SPA_DIST_DIR`. Stop the server, do step 5, and start it again.
- **Errors** go to `logs\errors.log` (D-75).
- **To stop:** Ctrl+C. A restart also clears the throttle counters and in-flight slots, which live
  in the process's memory (D-79).

## 7. Record the deployed commit

In a second window. The record is kept outside the repository, so it is never committed, and a
checkout does not change it.

```powershell
$root   = 'C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype'
$py     = "$root\.venv\Scripts\python.exe"
$record = "$env:USERPROFILE\Documents\KMP-alpha-deployments.txt"
Set-Location $root
$sha      = git rev-parse HEAD
$dirty    = [bool](git status --porcelain)
$flm      = flm version | Select-Object -First 1
$waitress = & $py -c "import importlib.metadata as m; print(m.version('waitress'))"
"$(Get-Date -Format o)  commit $sha  dirty=$dirty  flm '$flm'  waitress $waitress threads=24  DEBUG=False  http://127.0.0.1:8000" |
    Add-Content $record
Get-Content $record -Tail 1
```

`dirty=True` means the running code is not the commit recorded. Stop and go back to step 1.

## 8. Smoke check

In the second window. Type `curl.exe`, not `curl`: in Windows PowerShell 5.1, `curl` is an alias
for `Invoke-WebRequest`.

```powershell
$base = 'http://127.0.0.1:8000'

# The SPA: 200, text/html, Cache-Control: no-cache, Server: waitress, and <div id="root"> in the body
curl.exe -s -i "$base/"

# A client route: 200 text/html; charset=utf-8, the same index.html
curl.exe -s -o NUL -w '%{http_code} %{content_type}\n' "$base/documents"

# An asset: 200, Cache-Control: max-age=315360000, public, immutable
$asset = (Get-ChildItem "$root\frontend\dist\assets\*.js" | Select-Object -First 1).Name
curl.exe -s -I "$base/assets/$asset"

# The API, signed out: {"detail":"Authentication credentials were not provided."} 401
curl.exe -s -w ' %{http_code}\n' "$base/api/"

# An unmatched API path: {"detail": "Not found."} 404
curl.exe -s -w ' %{http_code}\n' "$base/api/__nope__"
```

**If a check fails:**

- **`/api/__nope__` answers an HTML page:** `DEBUG` is on. Under `DEBUG`, Django bypasses
  `handler404` (D-87). Stop the server, set `$env:DEBUG = 'False'` in its window, and start it
  again.
- **`/` answers `{"detail": "Not found."}`:** there is no build at `SPA_DIST_DIR`. Go back to
  step 5, then restart.
- **`/` answers `400`:** the `Host` the browser or curl sent is not in `ALLOWED_HOSTS`. Use
  `127.0.0.1` or `localhost`.

When all five checks pass, open `http://127.0.0.1:8000` in the browser on this laptop and sign in.

## Redeploying

1. Ctrl+C in the server window.
2. Repeat steps 1 to 8. Step 7 appends a new line, so the record keeps every deployment in order.

## What this deployment does not do

- **No TLS.** NFR-03's scan moves to NFR verification round 2 (D-64). Hence the four HTTPS warnings
  in step 4 and the cookie flags left off.
- **No access from another machine.** That is the registration point at the top.
- **It is not M8's hosting.** Where the system is hosted for M8 is a later decision (D-64).
