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

**Where it runs from (D-88).**

- **Its own worktree, `KMP_Prototype-alpha`,** checked out *detached* at `main`'s commit. The main
  checkout is left alone, and GitHub Desktop can still switch it to `main`.
- **Its own `.venv`.** A `uv pip sync` from an older checkout into a shared venv would remove
  WhiteNoise, and a local `.venv` makes every `$root\.venv` path below work as written.
- **Its own `.env`,** naming the alpha's database, `kmp_demo_20261101`, its `MEDIA_ROOT` and its
  own log paths.

**Its database is `kmp_demo_20261101`,** restored once from item 6's measured snapshot (D-88).
The media and logs live in `C:\kmp-demo\2026-11-01`, outside every checkout.

- **Never point the alpha at `kmp` or at the measurement database `kmp_obj02_20261101`.**
- **Do not re-index, reprocess or delete** between building the demonstration threads and
  demonstrating them (D-40).

**The measured run uses the same port.** `docs/measurement-runbook.md` serves Waitress on
`127.0.0.1:8000` from its own database. Only one server can listen there, so stop the measurement
server first.

**Before you start:**

- the commit to deploy is merged to `main`, and CI passed on it;
- Docker Desktop is running, with the database up (`docker compose up -d`);
- `flm` is v0.9.39, with `gemma3:4b` and `embed-gemma` pulled (`README.md`, D-83);
- Node and npm are installed (`node --version`), and so is `uv`.

## 1. The code

The first time, from the main checkout, which this step does not change:

```powershell
$main = 'C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype'
$root = 'C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-alpha'
git -C $main fetch origin
git -C $main worktree add --detach $root origin/main
```

Every time, including the first:

```powershell
$root = 'C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-alpha'
$py   = "$root\.venv\Scripts\python.exe"
Set-Location $root
git fetch origin
git switch --detach origin/main
git status --porcelain     # must print nothing, so the commit recorded in step 7 is what runs
git log --oneline -1
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

`check_flm.py` exits 1 if the embeddings are not deterministic. Do not deploy past that. The first
time, run this step after step 3, because `$py` does not exist until then.

## 3. Python dependencies, in the worktree's own venv

The first time:

```powershell
uv venv --python 3.12 .venv
& $py --version                 # Python 3.12.x
```

Every time:

```powershell
uv pip sync --python .venv\Scripts\python.exe requirements.txt
```

That makes this venv match `requirements.txt` exactly, `whitenoise==6.12.0` included. Nothing
else syncs into it.

## 4. The environment, then the database

**The first time, write `$root\.env`** with these values and nothing else. Generate the key with
`& $py -c "import secrets; print(secrets.token_urlsafe(50))"`. It uses letters, digits, `-` and
`_` only, so `.env` reads it as written. `.env` is gitignored; never commit it.

```
SECRET_KEY=<the generated key>
DEBUG=False
ALLOWED_HOSTS=127.0.0.1,localhost
DATABASE_URL=postgres://kmp:kmp@127.0.0.1:5432/kmp_demo_20261101
MEDIA_ROOT=C:\kmp-demo\2026-11-01\media
AUDIT_LOG_PATH=C:\kmp-demo\2026-11-01\logs\audit.log
ERROR_LOG_PATH=C:\kmp-demo\2026-11-01\logs\errors.log
WAITRESS_LOG_PATH=C:\kmp-demo\2026-11-01\logs\waitress.log
ATTEMPTS_LOG_PATH=C:\kmp-demo\2026-11-01\logs\attempts.log
AI_PROVIDER=flm
FLM_BASE_URL=http://127.0.0.1:8625/v1
FLM_API_KEY=flm
FLM_CHAT_MODEL=gemma3:4b
FLM_EMBED_MODEL=embed-gemma
EMBEDDING_DIMENSION=768
```

`ATTEMPTS_LOG_PATH` (step 7, 7 November 2026) is where every generation attempt is logged, parsed or
failed, with what its reply reported; `errors.log` keeps the failures only. A commit from before
the statement cap ignores it.

Then, in the deployment window:

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
- `security.W009` means `SECRET_KEY` is weak. Put a generated one in `.env`, as above. Changing the
  key signs everyone out, because sessions are signed with it. Stored passwords and data are not
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

## 6. Start the server, in a fresh window

**Open a new PowerShell window for the server.** Never use the measurement window, or any window
that has set `DATABASE_URL` or `MEDIA_ROOT` for something else. In it, the database and its media
are set together, as `.env` names them. Django is then asked which database it will connect to,
and the server starts only if that is `kmp_demo_20261101`:

```powershell
$root = 'C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-alpha'
$py   = "$root\.venv\Scripts\python.exe"
Set-Location $root
$env:DEBUG                 = 'False'
$env:DATABASE_URL          = 'postgres://kmp:kmp@127.0.0.1:5432/kmp_demo_20261101'
$env:MEDIA_ROOT            = 'C:\kmp-demo\2026-11-01\media'
$env:ALLOWED_HOSTS         = '127.0.0.1,localhost'
$env:CSRF_TRUSTED_ORIGINS  = 'http://127.0.0.1:8000,http://localhost:8000'
$env:SESSION_COOKIE_SECURE = 'False'      # plain HTTP on loopback (D-64)
$env:CSRF_COOKIE_SECURE    = 'False'
$env:SPA_DIST_DIR          = "$root\frontend\dist"
$env:WAITRESS_LOG_PATH     = 'C:\kmp-demo\2026-11-01\logs\waitress.log'
$env:FLM_BASE_URL          = 'http://127.0.0.1:8625/v1'
$name = & $py manage.py shell --no-imports -c "from django.db import connection; print(connection.settings_dict['NAME'])"
"Django will connect to: $name"
if ($name -ne 'kmp_demo_20261101') { throw "Not starting: the database is '$name', not kmp_demo_20261101." }
& "$root\.venv\Scripts\waitress-serve.exe" --listen=127.0.0.1:8000 --threads=24 --max-request-body-size=54525952 config.wsgi:application
```

- **`--no-imports` matters.** Without it, Django 5.2's `shell` first prints "N objects imported
  automatically", so `$name` holds two lines, never equals `kmp_demo_20261101`, and the check
  refuses even the right database.
- **24 threads, set explicitly** (D-85). Waitress defaults to 4.
- **A request body is capped at 54,525,952 bytes, set explicitly** (D-124). That is
  `MAX_REQUEST_BODY_BYTES`, 2 MB over the 50 MB upload limit.
  - **Why:** without the flag, Waitress accepts any body up to 1 GB. It reads the body, spooling it
    to a temporary file, before the application sees the request, so nothing in Django can refuse
    it sooner.
  - **Above the cap:** Waitress refuses the body unread, at its headers, with its own plain-text
    413 instead of the API's JSON. It then closes the connection, so a client still sending may
    see the connection reset instead of the 413. A chunked body declares no length, so it is
    refused once it reaches the cap. The SPA never sends that much: it refuses a file over 50 MB
    before sending it.
  - **Under the cap:** a body over 50 MB still gets the API's own 413.
- **The console stays quiet.** Waitress's own lines go to `WAITRESS_LOG_PATH` (D-87). From another
  window, `Get-Content C:\kmp-demo\2026-11-01\logs\waitress.log -Tail 1` shows
  `Serving on http://127.0.0.1:8000`.
- **`UserWarning: No directory at: ...frontend\dist\`** in the console means there is no build at
  `SPA_DIST_DIR`. Stop the server, do step 5, and start it again.
- **Errors** go to `C:\kmp-demo\2026-11-01\logs\errors.log` (D-75), with failed provider attempts
  as WARNINGs (D-82's note).
- **To stop:** Ctrl+C. A restart also clears the throttle counters and in-flight slots, which live
  in the process's memory (D-79).

## 7. Record the deployed commit

In a second window. The record is kept outside the repository, so it is never committed, and a
checkout does not change it.

```powershell
$root   = 'C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-alpha'
$py     = "$root\.venv\Scripts\python.exe"
$record = "$env:USERPROFILE\Documents\KMP-alpha-deployments.txt"
Set-Location $root
$sha      = git rev-parse HEAD
$dirty    = [bool](git status --porcelain)
$flm      = flm version | Select-Object -First 1
$waitress = & $py -c "import importlib.metadata as m; print(m.version('waitress'))"
"$(Get-Date -Format o)  commit $sha  dirty=$dirty  database kmp_demo_20261101  flm '$flm'  waitress $waitress threads=24  DEBUG=False  http://127.0.0.1:8000" |
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

## 9. Schedule the knowledge-gap cycle (FR-19)

FR-19 aggregates unanswered questions and zero-result searches "on a scheduled basis": once a day,
by the user's decision of 10 November 2026 (D-107's note). Register it once on the host, from this
worktree, in PowerShell:

```powershell
cd $root
.\scripts\register_knowledge_gap_schedule.ps1 -LogDirectory C:\kmp-demo\2026-11-01
```

- **It registers a task for the current Windows user,** daily at 02:00. `-At` sets another time,
  and running the script again replaces the task. The task runs `manage.py aggregate_knowledge_gaps`
  with this worktree's `.venv` and `.env`, and appends its output to `knowledge-gaps.log` in the log
  directory.
- **No password is asked for or stored,** so the task runs while that user is logged on. If the
  host must run it while logged off, set "Run whether user is logged on or not" in Task Scheduler
  yourself; Windows asks for the password there.
- **The provider must be reachable when it runs:** `flm serve` for `flm`, or the keys in `.env` for
  `anthropic`. A run that cannot reach it exits 1 and changes nothing, and the next run takes the
  rows it missed, because each cycle starts from the last committed one. A run missed while the
  machine was off starts when it is next on.
- **Check it** with `Get-ScheduledTask -TaskName "KMP knowledge-gap aggregation"`, and run one cycle
  now with `Start-ScheduledTask` and the same name. **Remove it** with
  `Unregister-ScheduledTask -TaskName "KMP knowledge-gap aggregation" -Confirm:$false`.
- **On a Linux host,** one crontab line does the same:
  `0 2 * * * cd /path/to/checkout && .venv/bin/python manage.py aggregate_knowledge_gaps >> logs/knowledge-gaps.log 2>&1`

The Administrator's **Run aggregation now** button on the knowledge-gap page runs the same cycle on
demand.

## 10. Schedule the meeting-summary retry (FR-16, NFR-20)

A meeting's summary is generated in the background after its transcript is stored, and a summary
that fails is "flagged for automatic retry" (NFR-20). The retry is `manage.py
retry_meeting_summaries`, run every hour (D-125). Register it once on the host, from this worktree,
in PowerShell:

```powershell
cd $root
.\scripts\register_meeting_summary_schedule.ps1 -LogDirectory C:\kmp-demo\2026-11-01
```

- **It registers a task for the current Windows user,** repeating every 60 minutes.
  `-EveryMinutes` sets another interval, and running the script again replaces the task. The task
  runs `manage.py retry_meeting_summaries` with this worktree's `.venv` and `.env`, and appends its
  output to `meeting-summaries.log` in the log directory.
- **No password is asked for or stored,** so the task runs while that user is logged on, as the
  knowledge-gap task does.
- **What one run does:**
  1. It closes any summary a stopped server left `Processing` for over 40 minutes, and queues it.
  2. It runs every queued summary again, one at a time.

  A summary leaves the queue when it is ready, or after three queued runs have failed. After that,
  only **Generate Summary** on the meeting page tries again.
- **Exit status:** 0 when the queue was empty or every summary came back ready. 1 when any is still
  unavailable, so the task's last result shows it. Nothing is lost either way: the transcript
  stays stored and searchable, and a failed run changes only its own summary's row.
- **Restarting the server mid-summary is safe.** The summary's row stays `Processing`, and the
  next run after the 40 minutes picks it up.
- **Check it** with `Get-ScheduledTask -TaskName "KMP meeting summary retry"`, and run the queue now
  with `Start-ScheduledTask` and the same name. **Remove it** with
  `Unregister-ScheduledTask -TaskName "KMP meeting summary retry" -Confirm:$false`.
- **On a Linux host,** one crontab line does the same:
  `0 * * * * cd /path/to/checkout && .venv/bin/python manage.py retry_meeting_summaries >> logs/meeting-summaries.log 2>&1`

**Meetings stored before FR-16 have no summary.** Give each its first one with
`manage.py summarise_meetings --missing`, once, after `migrate`. It costs one model call per
meeting, and it skips a transcript under 200 words.

## Redeploying

1. Ctrl+C in the server window, and close it.
2. In the deployment window, repeat step 1's every-time block. It moves the worktree, detached, to
   the new `origin/main`. Then do steps 2, 3's sync, 4's `migrate` and `check --deploy`, and 5.
3. Start the server in a **new** window (step 6), then do steps 7 and 8. Step 7 appends a new line,
   so the record keeps every deployment in order.

Redeploying does not touch the database. Restoring it again from the snapshot (D-88) resets the
demonstration's threads and accounts, so do that only before the demonstration threads are
built (D-40).

## What this deployment does not do

- **No TLS.** NFR-03's scan moves to NFR verification round 2 (D-64). Hence the four HTTPS warnings
  in step 4 and the cookie flags left off.
- **No access from another machine.** That is the registration point at the top.
- **It is not M8's hosting.** Where the system is hosted for M8 is a later decision (D-64).
