# Alpha deployment runbook

Stage 5 item 9, as D-64 settles it: the alpha runs on this laptop and is used on it. It is served
by Waitress with 24 threads (D-85), under `DEBUG=False`, with the production build of the front end
and `/api` on one origin, `http://127.0.0.1:8000`. **Since 13 November 2026 it runs on the
anthropic provider** (Claude Haiku 5.5 and Voyage `voyage-4`), on a database built for that
provider (D-131). These are the exact steps to deploy it from `main`, in native Windows PowerShell.

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
- **Its own `.env`,** naming the alpha's database, `kmp_alpha_20261113`, its `MEDIA_ROOT`, its own
  log paths, the provider and its two keys.

**Its database is `kmp_alpha_20261113`,** built once, on 13 November 2026, from item 6's corpus
under the anthropic provider (D-131, and "Building the database" below). The media and logs live
in `C:\kmp-demo\2026-11-13`, outside every checkout.

- **A database keeps the provider it was set up with** (D-131). The alpha's is an anthropic
  database. Never point the alpha at one set up for FLM, and never switch this one.
- **The FLM alpha's database, `kmp_demo_20261101`,** restored from item 6's snapshot (D-88), is
  kept as it was. Its `.env` is kept beside the alpha's as `.env.flm-20261101`, and it ran
  `8598d19`.
- **Never point the alpha at `kmp` or at the measurement database `kmp_obj02_20261101`.**
- **Do not re-index, reprocess or delete** between building the demonstration threads and
  demonstrating them (D-40).

**The measured run uses the same port.** `docs/measurement-runbook.md` serves Waitress on
`127.0.0.1:8000` from its own database. Only one server can listen there, so stop the measurement
server first.

**Before you start:**

- the commit to deploy is merged to `main`, and CI passed on it;
- Docker Desktop is running, with the database up (`docker compose up -d`);
- the alpha's `.env` holds `ANTHROPIC_API_KEY` and `VOYAGE_API_KEY` (step 4), and the laptop can
  reach both APIs;
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

## 2. The provider

Nothing to start. The anthropic provider is reached over the network with the two keys in `.env`.
Step 4's `check --deploy` shows whether it answers: Django probes it before any command, and
`ai.W001` means it did not. FLM takes no part. Recording transcription (D-123) stays off unless
`.env` sets `TRANSCRIPTION_PROVIDER=flm`.

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

That makes this venv match `requirements.txt` exactly, `whitenoise==6.12.0` included, and since
D-137 `pillow==13.0.0`, which re-encodes every profile picture uploaded. Nothing else syncs into
it. The API imports Pillow, so a venv last synced before D-137 fails `manage.py check`, and step 6
then does not start the server.

## 4. The environment, then the database

**The first time, write `$root\.env`** with these values and nothing else. Generate the key with
`& $py -c "import secrets; print(secrets.token_urlsafe(50))"`. It uses letters, digits, `-` and
`_` only, so `.env` reads it as written. `.env` is gitignored; never commit it.

```
SECRET_KEY=<the generated key>
DEBUG=False
ALLOWED_HOSTS=127.0.0.1,localhost
DATABASE_URL=postgres://kmp:kmp@127.0.0.1:5432/kmp_alpha_20261113
MEDIA_ROOT=C:\kmp-demo\2026-11-13\media
AUDIT_LOG_PATH=C:\kmp-demo\2026-11-13\logs\audit.log
ERROR_LOG_PATH=C:\kmp-demo\2026-11-13\logs\errors.log
WAITRESS_LOG_PATH=C:\kmp-demo\2026-11-13\logs\waitress.log
ATTEMPTS_LOG_PATH=C:\kmp-demo\2026-11-13\logs\attempts.log
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=<the key>
ANTHROPIC_MODEL=claude-haiku-5-5
VOYAGE_API_KEY=<the key>
VOYAGE_MODEL=voyage-4
VOYAGE_BASE_URL=https://api.voyageai.com/v1
```

The width follows `AI_PROVIDER` (D-131), so the template names no `EMBEDDING_DIMENSION`. The
alpha's `.env` of 13 November also has `EMBEDDING_DIMENSION=1024`, which agrees with the provider
and so is accepted. The keys are the ones in the main checkout's `.env`. Never print them, and never commit either
file. On 13 November 2026 the alpha's `.env` kept its four `FLM_*` lines from the FLM alpha. They
are read only for recording transcription, which is off.

`ATTEMPTS_LOG_PATH` (step 7, 7 November 2026) is where every generation attempt is logged, parsed or
failed, with what its reply reported; `errors.log` keeps the failures only. A commit from before
the statement cap ignores it.

**The password reset's email (D-137) needs no line in `.env`.** `.env.example` documents each
setting, and each default suits the alpha:

- **`PUBLIC_BASE_URL`** is the address people open the alpha at. Every reset link is built from
  it, never from the request. The default is the alpha's own, `http://127.0.0.1:8000`. A value
  that is not an absolute `http://` or `https://` address, or that carries a query or a fragment,
  stops Django loading its settings, so `migrate`, `check` and the server all refuse to start.
- **`DEFAULT_FROM_EMAIL`** is the sender each email names, `no-reply@localhost` by default.
- **`EMAIL_HOST` names an SMTP server, or is left out.**
  - **Left out, as above, nothing is sent.** Each email is written as a file to `EMAIL_FILE_PATH`,
    by default the worktree's `outbox` folder, `$root\outbox`, which is gitignored. Each reset
    email there holds a link that lets whoever opens it set that account's password, once, within
    60 minutes, so keep the folder as private as the database.
  - **With `EMAIL_HOST` set, the email goes by SMTP,** with the port, encryption and account the
    other `EMAIL_*` settings give, as `.env.example` lists them. `EMAIL_USE_TLS` and
    `EMAIL_USE_SSL` both true stops Django starting too.

Then, in the deployment window:

```powershell
& $py manage.py migrate
& $py manage.py check --deploy
```

`migrate` is safe to run on a database that already holds the demonstration corpus. Re-indexing,
reprocessing or deleting is not (D-40).

**The first `migrate` after FR-10's department list (#102, D-129)** applies `documents` 0012 to 0015.
- **0015** creates the department list the AI assigns departments from, and seeds it from the
  departments the documents already carry.
- **0012** marks each stored proposal as a Topic.
- **On `kmp_alpha_20261113`,** checked read-only on 15 November 2026
  (`corpus/objective-05/runs/2026-11-15-alpha-seed-check/`), 0015 seeds six departments.
  Finance, Human Resources, Information Technology, Legal and Compliance and Operations are
  ordinary. Projects is hidden, because only Administrator-only documents carry it.
- **Nothing needs classifying again.** Every document there carries the department typed at upload,
  which FR-10 never replaces.
  - `classify_documents --all` would mark 9 department suggestions applied rather than awaiting
    confirmation, because they matched the typed department below the old 0.72.
  - It would also replace the one unanswered proposal, and re-score the 15 held tags.
  - It costs a model call per document (since D-139 more for a document longer than about five
    pages, which is summarised in sections), and it is the user's call.

**The first `migrate` after FR-10's document summaries (D-139)** applies `documents` 0016, which
adds the summary columns to every document's classification, empty.
- **From then on** each upload, reprocess and classify writes the document's summary and key points
  with its classification, from the same request.
- **A document classified before it has no summary,** and its page says none has been generated,
  until the backfill gives it one. In the deployment window, after `migrate`:

  ```powershell
  & $py manage.py summarise_documents --out <a new record path>.json
  ```

- **What it changes:** the summary and key points of each classified document that has none, and
  nothing else. Every type, department, tag, proposal and confirmation stays as it is.
  `classify_documents --all` would write the summaries too, but it applies every classification
  again, with the consequences the paragraph above lists.
- **What it costs:** a model call per document (more for a document longer than about five pages,
  which is summarised in sections). It is the user's call, as reclassifying is.
- **A document with no classification is skipped and listed,** with a line pointing at
  `classify_documents`. `--id <uuid>` summarises chosen documents, and `--force` summarises again
  documents that already have a summary. The record is never written over an existing file.

**The first `migrate` after D-137** applies `accounts` 0012, which adds `picture` and
`picture_updated_at` to `users` for profile pictures. It needs no data step: every existing
account starts with no picture.
- **An uploaded picture is stored under `MEDIA_ROOT`,** in `profile-pictures\`, as a PNG. It leaves
  only through its own route, to signed-in users. Nothing serves `MEDIA_ROOT`.
- **A database at `accounts` 0008 gets FR-03's 0009 and 0010 and FR-20's 0011 first,** in the same
  `migrate` (step 11).

**`check --deploy` on loopback HTTP** should report exactly four warnings, all about HTTPS, which
D-64 puts out of scope for the alpha (NFR-03's scan moves to round 2):

- `security.W004` (HSTS)
- `security.W008` (SSL redirect)
- `security.W012` (`SESSION_COOKIE_SECURE`)
- `security.W016` (`CSRF_COOKIE_SECURE`)

Anything else is a stop:

- `ai.W001` means the provider did not answer. Check the keys in `.env` and the network (step 2).
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
and the server starts only if that is `kmp_alpha_20261113`. The same block, reading the database URL
from `.env` instead of naming it, is `C:\kmp-demo\2026-11-13\serve-alpha.ps1`, outside the
repository:

```powershell
$root = 'C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-alpha'
$py   = "$root\.venv\Scripts\python.exe"
Set-Location $root
$env:DEBUG                 = 'False'
$env:DATABASE_URL          = 'postgres://kmp:kmp@127.0.0.1:5432/kmp_alpha_20261113'
$env:MEDIA_ROOT            = 'C:\kmp-demo\2026-11-13\media'
$env:ALLOWED_HOSTS         = '127.0.0.1,localhost'
$env:CSRF_TRUSTED_ORIGINS  = 'http://127.0.0.1:8000,http://localhost:8000'
$env:SESSION_COOKIE_SECURE = 'False'      # plain HTTP on loopback (D-64)
$env:CSRF_COOKIE_SECURE    = 'False'
$env:SPA_DIST_DIR          = "$root\frontend\dist"
$env:WAITRESS_LOG_PATH     = 'C:\kmp-demo\2026-11-13\logs\waitress.log'
$name = & $py manage.py shell --no-imports -c "from django.db import connection; connection.ensure_connection(); print(connection.settings_dict['NAME'])"
if ($LASTEXITCODE -ne 0) { throw "Not starting: the database did not answer." }
"Django will connect to: $name"
if ($name -ne 'kmp_alpha_20261113') { throw "Not starting: the database is '$name', not kmp_alpha_20261113." }
& $py manage.py check
if ($LASTEXITCODE -ne 0) { throw "Not starting: manage.py check reported an error." }
& "$root\.venv\Scripts\waitress-serve.exe" --listen=127.0.0.1:8000 --threads=24 --max-request-body-size=54525952 config.wsgi:application
```

- **`manage.py check` runs first, because Waitress runs no system checks.** It refuses a database
  set up for another provider (ai.E005) and an `EMBEDDING_DIMENSION` that disagrees with the
  provider (ai.E004), and probes the provider once (D-131).
- **The line that names the database connects to it first.** A database that is not up yet, as
  after a restart before Docker Desktop is started, stops the start there. The check would only
  warn that it could not read it (ai.W004), and Waitress would then serve a database nobody
  checked.

- **`--no-imports` matters.** Without it, Django 5.2's `shell` first prints "N objects imported
  automatically", so `$name` holds two lines, never equals `kmp_alpha_20261113`, and the check
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
  window, `Get-Content C:\kmp-demo\2026-11-13\logs\waitress.log -Tail 1` shows
  `Serving on http://127.0.0.1:8000`.
- **`UserWarning: No directory at: ...frontend\dist\`** in the console means there is no build at
  `SPA_DIST_DIR`. Stop the server, do step 5, and start it again.
- **Errors** go to `C:\kmp-demo\2026-11-13\logs\errors.log` (D-75), with failed provider attempts
  as WARNINGs (D-82's note).
- **To stop:** Ctrl+C. A restart also clears the throttle counters, the in-flight slots and the
  password reset's 300-second cooldowns, which live in the process's memory (D-79, D-137).
  Ctrl+C also drops any reset email still being written or sent in its thread. Nothing retries
  it, and the person can ask again.

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
$waitress = & $py -c "import importlib.metadata as m; print(m.version('waitress'))"
"$(Get-Date -Format o)  commit $sha  dirty=$dirty  database kmp_alpha_20261113  provider anthropic: claude-haiku-5-5, voyage-4 at 1024  waitress $waitress threads=24  DEBUG=False  http://127.0.0.1:8000" |
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
.\scripts\register_knowledge_gap_schedule.ps1 -LogDirectory C:\kmp-demo\2026-11-13
```

- **It registers a task for the current Windows user,** daily at 02:00. `-At` sets another time,
  and running the script again replaces the task. The task runs `manage.py aggregate_knowledge_gaps`
  with this worktree's `.venv` and `.env`, and appends its output to `knowledge-gaps.log` in the log
  directory.
- **No password is asked for or stored,** so the task runs while that user is logged on. If the
  host must run it while logged off, set "Run whether user is logged on or not" in Task Scheduler
  yourself; Windows asks for the password there.
- **It runs on battery.** Task Scheduler's defaults hold a task while a laptop is on battery and
  stop one that is unplugged mid-run, and the script turns both off (D-107's note of 15 November
  2026). A task that stays `Queued` after `Start-ScheduledTask` is waiting on a condition like
  these.
- **A task registered by an earlier version of the script keeps those defaults.** Put it right in
  either of two ways:
  - **Run this version of the script again.** That replaces the whole task, so anything set by hand
    in Task Scheduler, such as "Run whether user is logged on or not", has to be set again.
  - **Change the two conditions in place:**

    ```powershell
    $task = Get-ScheduledTask -TaskName "KMP knowledge-gap aggregation"
    $task.Settings.DisallowStartIfOnBatteries = $false
    $task.Settings.StopIfGoingOnBatteries = $false
    $task | Set-ScheduledTask
    ```

    If the task is already `Queued`, `Stop-ScheduledTask` and then `Start-ScheduledTask`, with the
    same name, start it again.
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
.\scripts\register_meeting_summary_schedule.ps1 -LogDirectory C:\kmp-demo\2026-11-13
```

- **It registers a task for the current Windows user,** repeating every 60 minutes.
  `-EveryMinutes` sets another interval, and running the script again replaces the task. The task
  runs `manage.py retry_meeting_summaries` with this worktree's `.venv` and `.env`, and appends its
  output to `meeting-summaries.log` in the log directory.
- **No password is asked for or stored,** so the task runs while that user is logged on, as the
  knowledge-gap task does.
- **It runs on battery,** as the knowledge-gap task does. A task registered by an earlier version
  of the script does not. Put it right either of the knowledge-gap task's two ways, with this
  task's name, "KMP meeting summary retry".
- **What one run does:**
  1. It closes any summary a stopped server left `Processing` for over 40 minutes, and queues it.
  2. It runs every queued summary again, one at a time.

  A summary leaves the queue when it is ready, or after three queued runs have failed. After that,
  only **Generate Summary** on the meeting page tries again.
- **Exit status:** 0 when the queue was empty or every summary it ran came back ready. 1 when any
  summary it ran is still unavailable, so the task's last result shows it. A summary that has left
  the queue waits for **Generate Summary** and does not change the exit status. Nothing is lost
  either way: the transcript stays stored and searchable, and a failed run changes only its own
  summary's row.
- **Restarting the server mid-summary is safe.** The meeting page stops waiting once the run is
  40 minutes old and offers **Generate Summary** again. The summary's row stays `Processing`, and the
  next run after the 40 minutes picks it up.
- **Check it** with `Get-ScheduledTask -TaskName "KMP meeting summary retry"`, and run the queue now
  with `Start-ScheduledTask` and the same name. **Remove it** with
  `Unregister-ScheduledTask -TaskName "KMP meeting summary retry" -Confirm:$false`.
- **On a Linux host,** one crontab line does the same:
  `0 * * * * cd /path/to/checkout && .venv/bin/python manage.py retry_meeting_summaries >> logs/meeting-summaries.log 2>&1`

**Meetings stored before FR-16 have no summary.** Give each its first one with
`manage.py summarise_meetings --missing`, once, after `migrate`. It costs one model call per
meeting, and it skips a transcript under 200 words.

## 11. Confirm the knowledge map's permission (FR-20)

The knowledge map (`/knowledge-map`, D-132) is behind the permission `view_knowledge_map`, which
both roles hold only once `accounts 0011_seed_view_knowledge_map` has run. Until then
`GET /api/knowledge-map` answers 403 to everybody, and the screen says the user is not permitted.

- **After step 4's `migrate`,** sign in in the browser and open `http://127.0.0.1:8000/api/roles`.
  Both roles must list `view_knowledge_map`.
- **`accounts 0011` follows FR-03's `0009` and `0010` in one line, and D-137's `0012` follows
  it.** A database at 0008 gets all four from step 4's `migrate`, in order, 0009 to 0012. There is
  no merge migration:
  - 0011 was re-pointed onto 0010 before it was pushed or applied anywhere (D-132's dated note of
    15 November 2026; D-130);
  - 0012 was re-pointed onto 0011 in the merge of 17 November 2026, before it was pushed (its
    docstring, `apps/accounts/migrations/0012_user_picture.py`).

The map reads existing tables only, so it needs no data step: a document's uploader, a meeting's
attendees and the applied tags are what it draws.

## Redeploying

1. Ctrl+C in the server window, and close it.
2. In the deployment window, repeat step 1's every-time block. It moves the worktree, detached, to
   the new `origin/main`. Then do steps 2, 3's sync, 4's `migrate` and `check --deploy`, and 5.
   On the first redeploy after FR-10's document summaries (D-139), run step 4's
   `summarise_documents` after `migrate`, so the documents classified before it get a summary.
3. Start the server in a **new** window (step 6), then do steps 7 and 8. Step 7 appends a new line,
   so the record keeps every deployment in order.

Redeploying does not touch the database. Building it again resets the demonstration's threads
and accounts, so do that only before the demonstration threads are built (D-40).

## Building the database (once)

`kmp_alpha_20261113` was built on 13 November 2026, with the user's approval, as
`corpus/objective-02/runs/2026-11-13-alpha-anthropic/README.md` records step by step:

1. `CREATE DATABASE`, then step 4's `migrate` and `check --deploy`. Both vector columns are
   `vector(1024)`, because the database was set up under the anthropic provider.
2. The server, as in step 6.
3. That folder's `run_ingestion_with_accounts.py`. It makes the Administrator with `createsuperuser
   --noinput` and registers the Employee through FR-01, each with a password held only in memory.
   It then ingests item 6's corpus through the server, classifying each document at upload (FR-10).
4. `scripts/seed_objective02_tags.py`, which adds item 6's tags (D-74) and marks `atlas` grown.
   It finds each document by title, so it runs after the ingestion.
5. `manage.py classify_documents --all`, so FR-10 classifies every document against those tags.
   The ingestion classified them at upload, before any tag existed. Since D-139 each upload and
   this step also write every document's summary, so a database built this way needs no
   `summarise_documents` run. A `--scheme-only` seed before the ingestion would let the upload's
   classification see the vocabulary instead. That order was not tried, and it is not a safe
   substitute as written: `--scheme-only` marks nothing grown, so `atlas` would be offered to
   Employees, and a held AI link on a document every role reads would keep the full seed from
   marking it grown later.

**Building it again after FR-10's department list (#102, D-129).** `documents` 0015 seeds the
department list when it runs, from the documents present at that moment. Step 1's `migrate` runs
before any document exists, so the list would start empty. Every document's page would then show
the AI's department as "not one of the known departments", and the Tags page would list none.
- **The fix:** after step 3, apply 0015 again, so it seeds the list from the ingested documents, as
  `migrate` does on the database above:

  ```powershell
  & $py manage.py migrate documents 0014
  & $py manage.py migrate
  ```

- **What it does:** the first command reverses 0015, which drops the department table, empty at
  that point. The second applies 0015 again. A department that only Administrator-only documents
  carry is seeded hidden.
- **It is tested:** `apps/documents/tests/test_migration_0015_departments.py`'s
  `test_0015_backwards_drops_the_table_and_forward_seeds_it_again` runs exactly this.
- **Do not add the departments by hand on the Tags page instead.** A department added there is
  never hidden.
- **When it is safe:** while no later migration depends on 0015, and before anyone has added a
  department by hand, because the reversal drops any such department.
- **Then steps 4 and 5,** so the classification sees the list.

**Nobody knows either account's password.** Before the walk, set the Administrator's from this
worktree, with its `.env`:

```powershell
& $py manage.py changepassword corpus.admin@example.com
```

The Employee for a walk registers through FR-01, or has its password set the same way.

## What this deployment does not do

- **No TLS.** NFR-03's scan moves to NFR verification round 2 (D-64). Hence the four HTTPS warnings
  in step 4 and the cookie flags left off.
- **No access from another machine.** That is the registration point at the top.
- **No real email,** unless `.env` names an SMTP server (D-137). A password reset email is a file
  in the outbox (step 4).
- **It is not M8's hosting.** Where the system is hosted for M8 is a later decision (D-64).
- **It does not switch providers.** A database keeps the provider it was set up with (D-131). To
  bring back the FLM alpha, check out `8598d19` and restore `.env.flm-20261101` as `.env`, with FLM
  running as that commit's runbook says. It serves `kmp_demo_20261101`, which is unchanged.
