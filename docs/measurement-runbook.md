# Item 6 measurement runbook

Stage 5 item 6, as D-83, D-84, D-85, D-86 and D-87 settle it. These are the exact steps, in
order, for one measured run:

- a fresh database holding exactly Objective 02's corpus, and a snapshot of it;
- the thirty questions, then NFR-08's k6 run (Objective 03);
- FR-13 end to end: the harness's thread run, then the HTTP check;
- NFR-09's k6 run, last.

Every step says what it writes and where. Windows PowerShell 5.1, on the NPU laptop.

**Nothing here may start until both sets are approved and committed** (D-84 §2, D-86 §7):

- `corpus/objective-02/questions.json`, the thirty questions;
- `corpus/objective-02/threads.json`, FR-13's threads, with its scoring rule.

Both are drafts until Benjamin and Sagarika approve them. On approval, each file's `status` field
is changed to say so, in one commit, and that commit is the freeze. Every run records the SHA-256
of the set it used, so the run can be checked against the frozen file.

The rules that hold throughout:

- **`kmp` is never touched** (D-84 §1). Every script below refuses a database named `kmp`.
- **The questions and the threads run before NFR-09, or the snapshot is restored first.** NFR-09
  uploads documents, which become retrieval candidates. The harness refuses a recorded run when
  the indexed corpus is not exactly the manifest's 25 items, so a forgotten restore is caught.
- **The server is Waitress with 24 threads, under `DEBUG=False`** (D-85). Wherever a run goes
  through it, the run records the server, its version and its thread count, observed. Where a
  run is in-process (the harness), the record says so instead.
- **`DEBUG=False` is set in the shell, every time.** The repo's `.env` sets `DEBUG=True`, and a
  value set in the shell is the only thing that overrides it (D-87 §2). Step 1's block sets it,
  and step 5 sets it again on the line before the server starts.
- **The server is restarted before each run that goes through it:** NFR-08, the HTTP check and
  NFR-09 (D-87 §1). Throttle counters and in-flight slots left by one run then cannot 429 the
  next. `run.ps1` refuses NFR-08 or NFR-09 on a server that started before the last run in
  `$runs` ended; nothing checks the HTTP check's restart, so step 12b is the operator's.
- **All item 6's code is committed before the first measured run,** front end included (D-87
  §1), so the SHA recorded beside each result is the code that ran.
- **The dump and the media copy live outside every git checkout.** The dump holds every
  account's password hash and is never committed (CLAUDE.md §7). The snapshot script refuses a
  folder inside a checkout.
- **Every gate exits 2 when it refuses**, and says why. Stop there; do not work around it.

## The order (D-87 §1)

D-87 §1 settles it:

1. the thirty questions (step 9);
2. NFR-08's k6 run (step 11), on a freshly started server;
3. FR-13's thread run (step 12a), with the server stopped;
4. the HTTP check (step 12b), on a freshly started server;
5. NFR-09's k6 run (step 13), on a freshly started server, last.

D-86 made two statements about order that conflict if read literally: §1, "Objective 03 runs
first. FR-13 end to end is built alongside it, and never delays it", and §6, the HTTP check "runs
after the harness and before k6". D-87 reads §6's "before k6" as protecting the corpus from
NFR-09's uploads.

**Why.**

- **§1 is a priority rule.** FR-13 is "never ahead of" Objective 03, in D-86's own title. With
  this order, Objective 03's p90 is measured exactly as it would be without FR-13. Moving FR-13
  ahead of NFR-08 would add 10–15 minutes of NPU work before it.
- **§6's "before k6" protects the corpus, and that is what it is read as here: before NFR-09.**
  NFR-09 uploads a document every round (D-84 §1). NFR-08 only asks. Its asks write `QueryLog`
  and `Conversation` rows, which are not retrieval candidates, and nothing in FR-13's runs reads
  them:
  - the harness reads chunks;
  - the HTTP check reads only its own fresh threads.

  So NFR-08 cannot change what FR-13 measures, and nothing needs restoring between them.
- **FR-13 still comes after the harness's thirty**, as §6 says. And both of FR-13's runs come
  before the one k6 run that changes the corpus.

Changing the order is a decision, not an edit to make on the day.

## 0. Before the day

1. Both sets are approved and committed, and so is every script change being measured. A SHA
   names a commit, not a working tree. Every record notes whether tracked files had uncommitted
   changes.
2. **Waitress is installed in the venv** (D-85 §1). This must print a version, `3.0.2` when this
   was written:

   ```powershell
   & 'C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype\.venv\Scripts\python.exe' -c "import importlib.metadata as m; print(m.version('waitress'))"
   ```

   If it fails, sync the venv with `requirements.txt` first.
3. k6 is installed and on `PATH` (for steps 11 and 13 only).
4. **Nothing else is listening on port 8000.** The everyday development server serves `kmp` on
   that port. A second server there would take the uploads, the asks and the load test.

   ```powershell
   Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue   # must print nothing
   ```

   **This check can be wrong in both directions on this laptop** (D-87's notes of 11 and 12
   November 2026). Windows has reported a serving socket in another state, so it can print nothing
   while a server is listening. It has also left a row whose `OwningProcess` is 0 after a server
   stopped, which is not a server. And with two servers on the port it prints one of them. When in
   doubt, ask the script the pre-flight uses. It reads netstat and the port's own rows as well, and
   takes about a minute to give up. The two paths are spelled out because `$py` and `$repo` are set
   in section 1, below:

   ```powershell
   & 'C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype\.venv\Scripts\python.exe' `
     'C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype\scripts\server_record.py' http://127.0.0.1:8000
   ```

   The port is free only when its `notes` say that nothing is listening. A note that no single
   process holds the port means something does. A note that it is not known means a lookup could
   not be read: look again before treating the port as free.

## 1. The names, in every PowerShell window used below

Each step runs in a PowerShell window that has this block pasted into it. Environment variables
belong to one window, and a value set in the shell wins over `.env`. A window without this block
writes to whatever `.env` names, which in the main checkout is `kmp`.

```powershell
$repo = 'C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype'   # the checkout at the commit under test
$py   = 'C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype\.venv\Scripts\python.exe'
$waitress = Join-Path (Split-Path $py) 'waitress-serve.exe'   # D-85's server, from the same venv
Set-Location $repo

$run  = '2026-10-28'                      # the day of the run; set it once and reuse it
$db   = 'kmp_obj02_' + ($run -replace '-', '')
$root = "C:\kmp-measurement\$run"         # outside every checkout
$runs = "corpus\objective-02\runs\$run"   # the run's evidence, committed afterwards

# This run's own database, media and logs (D-84 §1). DATABASE_URL is .env's with only the
# database name swapped, and it is never printed.
$line = Get-Content .env | Where-Object { $_ -match '^DATABASE_URL=' } | Select-Object -First 1
$env:DATABASE_URL   = (($line -replace '^DATABASE_URL=', '').Trim()) -replace '/[^/]+$', "/$db"
$env:MEDIA_ROOT     = "$root\media"
$env:AUDIT_LOG_PATH = "$root\logs\audit.log"
$env:ERROR_LOG_PATH = "$root\logs\errors.log"
$env:WAITRESS_LOG_PATH = "$root\logs\waitress.log"  # Waitress's own lines (D-87 §3); run.ps1 reads it too
$env:ATTEMPTS_LOG_PATH = "$root\logs\attempts.log"  # every generation attempt, parsed or failed (step 7)
$env:DEBUG          = 'False'                       # overrides .env's DEBUG=True (D-64, D-85, D-87 §2)
$env:FLM_BASE_URL   = 'http://127.0.0.1:8625/v1'    # check_flm.py and run.ps1 read the shell, not .env

([uri]$env:DATABASE_URL).AbsolutePath               # prints /kmp_obj02_<date>: the name only
```

`DEBUG=False` matches D-64 and D-85. It is also why `create_load_test_users` needs
`--i-know-this-is-local` below.

## 2. FLM: the version, then the gate

In its own window, left running for the whole run:

```powershell
flm version                         # must print: FLM v0.9.39 (D-83)
flm serve gemma3:4b --embed 1
```

Then, in the step 1 window:

```powershell
& $py scripts\check_flm.py          # must end: RESULT: PASS (all 3 checks passed against ...)
```

It prints the FLM version twice: from `flm version`, and from the running server's
`/v1/version`. Both must be `v0.9.39`.

**Writes nothing.**

## 3. The fresh database

```powershell
& $py scripts\snapshot_measurement_db.py create --database $db
& $py manage.py migrate
```

- **`create`** runs `createdb` in the `kmp_prototype-db-1` container, as the container's own
  user. It refuses `kmp`, and it fails if the database already exists.
- **`migrate`** builds the schema, including the pgvector extension, from empty.

**Writes:** a new empty database, then its schema, in the container's volume.

## 4. The accounts

```powershell
& $py manage.py createsuperuser     # the Administrator the ingestion signs in as: email, name, password

$env:LOAD_TEST_PASSWORD = '<a password meeting FR-01, with no double quote>'
& $py manage.py create_load_test_users --count 21 --i-know-this-is-local
```

- **`createsuperuser`** is the only way to make an Administrator (README, "First-run accounts").
- **The 21 Employees** are `loadtest01`–`loadtest21`, for k6 (tests/load/README.md). They are
  made here so that the snapshot holds them, and a restore keeps them.
- **The harness needs no account.** It reads the database in-process and takes each run's role
  from its set.

**Writes:** 22 user rows in `$db`.

## 5. The server, in its own window

Paste the step 1 block, then, every time the server starts:

```powershell
$env:DEBUG = 'False'                                 # .env says True; only the shell overrides it
$env:WAITRESS_LOG_PATH = "$root\logs\waitress.log"   # the same path the run.ps1 window has
& $waitress --listen=127.0.0.1:8000 --threads=24 --max-request-body-size=54525952 config.wsgi:application
```

This is D-85 §2's command with D-124's body cap,
`waitress-serve --listen=127.0.0.1:8000 --threads=24 --max-request-body-size=54525952 config.wsgi:application`,
run from the venv's `Scripts` folder so that it is the venv's Waitress.
The two lines before it repeat step 1's on purpose: a server started from a window without them
runs under `.env`'s `DEBUG=True` and logs Waitress's lines to the checkout's `logs\waitress.log`.

- **`DEBUG=False` is explicit** (D-87 §2). With `DEBUG` on, Django serves its HTML debug pages,
  and every run that checks refuses: `run.ps1`, the ingestion and the HTTP check all request an
  unmatched `/api/` path and require handler404's JSON 404.
- **`--threads=24` is set explicitly** (D-85 §3). Waitress's default is 4, which NFR-08's five
  users already exceed. 24 is NFR-09's 20 users plus 4 for screens, logins and uploads, so a load
  run waits on the NPU, not in Waitress.
- **`--max-request-body-size=54525952` caps any request body** (D-124), at
  `MAX_REQUEST_BODY_BYTES`, 2 MB over the 50 MB upload limit. Without it Waitress takes bodies up to
  1 GB. It changes nothing a run measures. The largest measured request is the ingestion's
  oversized item I02, generated 1 MB past 50 MB, so it stays under the cap and still gets the API's
  own 413; a test ties the two. `run.ps1` does not check the flag.
- **Waitress writes its own log** to `$root\logs\waitress.log` (D-87 §3). Its first line is
  `Serving on http://127.0.0.1:8000`, with a timestamp: that line is how `run.ps1` knows when the
  server started. A `Task queue depth is N` line means a request arrived with no thread free;
  `run.ps1` copies those from each k6 run's window into its results.
- **It is one process with no reloader.** The throttle counters and the in-flight slots live in
  its memory (D-79). Stopping it (Ctrl+C) empties them, which is why it is restarted before each
  run through it: NFR-08, the HTTP check and NFR-09 (D-87 §1). **Restart** below means: Ctrl+C in
  this window, then the three lines above again.
- **What is listening can be checked**, in the step 1 window:

  ```powershell
  & $py scripts\server_record.py http://127.0.0.1:8000
  ```

  It prints the server, its version, its thread count and `DEBUG`. They are read from the process
  listening on port 8000, from the reply's `Server` header and from an unmatched `/api/` path,
  not stated. It prints a `NOT D-85:` line for anything that differs. The ingestion and the HTTP
  check record the same observation themselves, and refuse a server with `DEBUG` on.

**Writes:** uploads to `$root\media`; the audit, error and Waitress logs to `$root\logs`; and rows
in `$db`. It writes nothing to `kmp` or to the checkout's `media\` or `logs\`.

## 6. The Employee the ingestion signs in as

In the step 1 window, with the server running:

```powershell
$env:KMP_CORPUS_ADMIN_EMAIL       = '<the Administrator from step 4>'
$env:KMP_CORPUS_ADMIN_PASSWORD    = '<its password>'
$env:KMP_CORPUS_EMPLOYEE_EMAIL    = 'corpus.employee@example.com'
$env:KMP_CORPUS_EMPLOYEE_PASSWORD = '<a password meeting FR-01>'

$body = @{ name = 'Corpus Employee'; email = $env:KMP_CORPUS_EMPLOYEE_EMAIL;
           password = $env:KMP_CORPUS_EMPLOYEE_PASSWORD } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/auth/register `
                  -ContentType 'application/json' -Body $body
```

FR-01's own path: it creates an Employee. The same two accounts are used again in step 12b, so
keep this window, or set the four variables again there.

**Writes:** one user row in `$db`, and one audit entry.

## 7. Ingest the corpus

```powershell
& $py scripts\ingest_objective02.py --output-dir $runs
```

**It refuses (exit 2) before uploading anything if:**

- `$runs` already holds a `results.json` (the 6 October results beside the manifest are never
  overwritten);
- the database its own process reads is `kmp`;
- `check_flm.py`'s checks fail;
- FLM is not v0.9.39, by the CLI and by the server;
- the server at port 8000 is positively not D-85's: another server, or Waitress with a thread
  count other than 24. It refuses only on evidence. If the lookup itself fails, it warns and
  records "unknown". `--any-server` overrides the refusal, and the results then say the server was
  not D-85's.

**What it records:**

- the commit SHA, the FLM version and the database name;
- the server, observed: its name, version and thread count, the listening process and its
  command line, and the `Server` header. `results.md` has it on one line.

**It must end:** `Missed: none; over the bound: none`, with exit code 0. If anything missed, do
not snapshot. A partial corpus is not Objective 02's. Investigate, then start again from step 3
with a new `$run` (for example `2026-10-28b`), so that nothing is reused.

**Writes:**

- `$runs\results.json` and `$runs\results.md`;
- 25 documents and meetings, their chunks and vectors, and the six invalid items' records, in
  `$db`;
- the originals in `$root\media`.

## 8. Snapshot and hash, with the server stopped

Stop the step 5 server (Ctrl+C), so nothing writes while the media is copied. Then:

```powershell
& $py scripts\snapshot_measurement_db.py snapshot --database $db --media-root $env:MEDIA_ROOT --out-dir "$root\snapshot"
Copy-Item "$root\snapshot\snapshot.json" "$runs\snapshot.json"
$hash = (Get-Content "$root\snapshot\snapshot.json" -Raw | ConvertFrom-Json).dump_sha256
$hash                                # equals (Get-FileHash "$root\snapshot\$db.dump").Hash, lower-cased
```

**What the snapshot runs:** `pg_dump` in custom format, through the container, as its own user.

**What it records:** the dump's SHA-256 with the commit SHA, the FLM version, `pg_dump`'s
version and a hash of the media tree. The hash goes to every later step.

**Writes:** in `$root\snapshot`:

- `$db.dump` and `$db.dump.sha256`;
- `media\`, a copy of `MEDIA_ROOT`;
- `snapshot.json`.

Its copy goes to `$runs\snapshot.json`. Nothing in `$root` is ever committed.

## 9. The thirty questions

The server stays stopped. The harness reads the database in-process and calls FLM itself.

```powershell
& $py scripts\citation_harness.py --questions corpus\objective-02\questions.json `
      --scores-only --dump-sha256 $hash --out "$runs\scores.json"
& $py scripts\citation_harness.py --questions corpus\objective-02\questions.json `
      --dump-sha256 $hash --out "$runs\harness.json"
```

**The two runs:**

- **`--scores-only`** embeds and ranks only. It produces the top-score distribution and the
  threshold sweep (D-37): about a minute.
- **The full run** asks the 34 runs: 22 ordinary, 4 scoped as the Administrator, 4 scoped as an
  Employee, and 4 no-answer. It reports the three rates, scoped and no-answer correctness, the
  out-of-scope count, and its own sequential timing. About six to eight minutes.

**Both refuse (exit 2) before asking anything if:**

- the `--out` file already exists;
- the question set is malformed;
- the database is `kmp`;
- `check_flm.py`'s checks fail;
- FLM is not v0.9.39;
- the indexed corpus is not exactly the manifest's 25 items: anything extra, missing, orphaned,
  or embedded by another model.

**What each run records:**

- the commit, the FLM version, the dump hash, the database name and the question file's hash;
- the server, as "none, in-process": the harness calls the pipeline's functions itself, and no
  HTTP server is involved (D-85 §4);
- per run, the partial matches the reply would offer, with scores (D-56), and the rank and score
  of the expected source (D-37).

To keep the console text as well, add `*>&1 | Tee-Object "$runs\harness.txt"`. Windows
PowerShell 5.1 writes that file as UTF-16.

**Writes:** `$runs\scores.json` and `$runs\harness.json`. Nothing in the database.

## 10. Restore, if anything wrote documents or meetings since step 8

Run this if anything uploaded, deleted, reprocessed or pasted since the snapshot: a browser
session, a test upload, an earlier NFR-09 run. The harness's corpus gate refuses in that case, so
its refusal is the signal. With the server stopped:

```powershell
& $py scripts\snapshot_measurement_db.py restore --database $db --media-root $env:MEDIA_ROOT --from-dir "$root\snapshot"
```

**Before it touches anything,** it checks the dump and the media copy against `snapshot.json`,
and refuses on any difference.

**Then it:**

1. drops and recreates `$db`;
2. restores the dump;
3. replaces `MEDIA_ROOT` with the copy;
4. checks the media tree's hash again.

**Writes:** `$db`, replaced, and `$root\media`, replaced.

**The account passwords are the snapshot's.** That is the step 4 password. Run
`create_load_test_users` again if it has changed.

## 11. NFR-08, Objective 03's p90 at five users (D-84 §3)

**Start the server** (step 5), after step 9's harness has finished. It must start after
everything already in `$runs` was written, or `run.ps1` refuses it as not restarted (D-87 §1).
Then, in the step 1 window:

```powershell
$env:LOAD_TEST_PASSWORD = '<the step 4 password>'
.\tests\load\run.ps1 -Test nfr08 -DbDumpSha256 $hash -Python $py -ResultsDir $runs
```

- **Leave `VUS` unset.** Five users is D-84 §3, decided before the run.
- **Leave `-ServerThreads` at its default of 24.** It is the statement; the thread count recorded
  is the one observed on the listening process's command line.
- **`WAITRESS_LOG_PATH` comes from the step 1 block**, the same path the server window set.
  `-ResultsDir $runs` is where the summary is copied, and where the restart check looks for
  earlier runs.

**`run.ps1` refuses (exit 2) before k6 starts if:**

- Waitress is not installed in the venv, or `-ServerThreads` is not 24 without the override;
- no Waitress log is named, or it does not exist;
- FLM is not v0.9.39, or `check_flm.py` does not pass;
- the process listening on port 8000 is not Waitress, or its command line has no `--threads=24`
  (no `--threads` at all is Waitress's default, 4, and is refused as 4);
- `GET /api/__preflight_not_a_route__` is not handler404's JSON 404, so `DEBUG` is not
  confirmed off;
- Waitress's log has no timestamped `Serving on` line for port 8000 from after the listening
  process started;
- that start is earlier than the end of the latest run recorded in `$runs` or
  `tests\load\results`: the server was not restarted.

**After k6**, it copies every `Task queue depth` line from the run's window out of
`$root\logs\waitress.log` into the summary, or records that there were none (D-87 §3). It marks
the run INVALID if the server started again during it. It exits 3 if k6 wrote no summary for this
run, and the run is then not recorded.

It records the commit, the FLM version, the dump hash and every observed value in the summary:
the server, its version and thread count, its pid, `DEBUG`, its start, the previous run, the
queueing, and the whole pre-flight record. The stated values sit beside them.

**Read the verdict in the JSON, not k6's exit code.** tests/load/README.md has the rest:

- pacing;
- the INVALID and NO DATA verdicts;
- not logging in from a browser while `setup()` runs.

**Report, with the dump hash, commit, FLM version and server** (D-84 §3, D-85 §4):

- `p90_ms` against 4 s: answered replies and 503s, each 503 a miss ranked slower than any answer
  (D-82's note of 1 November 2026);
- beside it, the 503 count, the answered-only p90, the all-replies p90, the answered rate, the
  8.90 s baseline and the single-user end-to-end baseline;
- the run's queueing, `waitress_log.queue_depth` (D-87 §3);
- the failed provider attempts and 503 causes in the run's window: `WARNING apps.ai.attempts` lines
  in `$root\logs\errors.log`.

**Writes:**

- `tests\load\results\nfr08_summary.json`, copied to `$runs\nfr08_summary.json` by `run.ps1`;
- QueryLog and Conversation rows in `$db`;
- log lines in `$root\logs`.

NFR-08 writes no document, meeting or chunk, so step 12 needs no restore after it.

## 12. FR-13 end to end (D-86)

### 12a. The thread run, with the server stopped

Stop the step 11 server (Ctrl+C). Then, in the step 1 window:

```powershell
& $py scripts\citation_harness.py --threads corpus\objective-02\threads.json `
      --dump-sha256 $hash --out "$runs\threads.json"
```

**What it runs.** 9 threads as 11 thread-and-role pairs, so 44 runs:

- each first turn once;
- each follow-up three ways:
  - **with history**: composed with the first question by `compose()`, which `POST /api/ask`
    uses;
  - **cold**: the follow-up alone;
  - **spelled out**: by hand.

It embeds the composed join and prompts the composed block, as the pipeline does. About eight to
ten minutes.

**What it reports, per follow-up and per way** (D-86 §4), by the scoring rule frozen with the
set:

- whether the run was answered, the expected source's rank, and the expected-answer match;
- the split between path A, path B (declined or rejected) and unavailable;
- fabrication, first-attempt conformance, and the out-of-scope count, which must be 0;
- per follow-up: a reading ("history works", "cold-answerable" and so on);
- for t06 and t07: whether scoping was shown.

**It refuses (exit 2) before asking anything** on the same gates as step 9, with the thread set in
place of the question set. It also refuses `--threads` combined with `--questions`,
`--with-history`, `--scores-only` or `--kind`.

**What it records:** what step 9 records, with the thread file's SHA-256 and the scoring rule's
version in place of the question file's. The server is "none, in-process".

**Exit code:**

- **1** if anything out of scope reached any run, or schema conformance fell below 95%;
- **0** otherwise. The readings are the result, not the exit code.

**Writes:** `$runs\threads.json`. Nothing in the database.

### 12b. The HTTP check, with the server started fresh

Start the server (step 5) again, so the throttle counters NFR-08 left are empty (D-87 §1). Nothing
checks this restart: the HTTP check observes the server's threads and `DEBUG`, not its start. Then,
in a window with the step 1 block and step 6's four `KMP_CORPUS_*` variables:

```powershell
& $py scripts\conversation_http_check.py --dump-sha256 $hash --out "$runs\http_check.json"
```

**What it runs.** Three threads from `threads.json`'s `http_check` list, through the server:

- t03 and t04 as the Employee;
- t06 as the Administrator.

**For each thread:**

1. `POST /api/conversations`;
2. `POST /api/ask` with the first question, then with the follow-up;
3. `GET /api/conversations/{id}`;
4. a read of the thread's two `QueryLog` rows.

**Pacing.** Asks are at least 7 s apart, start to start, and never overlap (D-79: ten asks a
minute, one ask in flight per user). The gaps achieved are recorded. About two minutes.

**The verdict per thread is WIRED** when all of these hold:

- the server's second-turn row supplied exactly the passages that `compose(follow-up, [first
  question])` retrieves in this process;
- those are not the ones the follow-up alone retrieves;
- both rows hold the questions as asked.

That is the history, read from `QueryLog`, changing what was retrieved. The reply to turn two is
also scored by the frozen rule and checked for a leak.

**It refuses (exit 2), with no request sent, if:**

- the `--out` file exists;
- the thread set is malformed;
- the database is `kmp`, recorded or not, because this run writes through the server;
- a `KMP_CORPUS_*` variable is not set;
- `check_flm.py`'s checks fail, or FLM is not v0.9.39;
- the corpus is not exactly the manifest's 25 items.

**It also refuses:**

- after two unauthenticated GETs, `/api/` and the DEBUG probe: if the server is positively not
  D-85's (another server, another thread count, or `DEBUG` on), unless `--any-server` is given;
- after signing in, before any thread is created: if the server lists documents or meetings that
  this process's database does not hold. That means it is serving another database.

**What it records:**

- the commit, the FLM version, the dump hash, the database name and the thread file's hash;
- the server, observed: name, version and thread count;
- the gaps between asks;
- per thread: the replies' statements and sources (no passage text), the rows' supplied
  passages, the in-process comparison and the verdict.

**Exit code:** 0 only if every thread is WIRED and nothing leaked.

**Writes:**

- per thread, through the server: one Conversation row, two QueryLog rows, and an answered
  turn's AnswerCitation rows. None is a retrieval candidate, so no restore is needed;
- signing in also writes a session, the last-login time and an audit line;
- `$runs\http_check.json`.

## 13. NFR-09, separately, last

**Restart the server** (step 5: Ctrl+C, then its three lines again), after the HTTP check has
finished. `run.ps1` refuses a server that started before `$runs\http_check.json` was written
(D-87 §1). Then, in the step 1 window:

```powershell
.\tests\load\run.ps1 -Test nfr09 -DbDumpSha256 $hash -Python $py -ResultsDir $runs
```

It refuses on the same conditions as step 11, and copies the run's queueing into the summary
afterwards in the same way. At 24 threads, a `Task queue depth` line appears only when more than
24 requests are inside Waitress at once; NFR-09's 20 users should not do that, so any line in the
window is worth reporting.

It takes 32–37 minutes. **Afterwards `$db` is no longer the snapshot.** It holds up to 1,210
`LoadTest` uploads in `$db` and `$root\media`. Before anything else is measured on it, restore
(step 10). That includes a second NFR-08 run, and a second thread run.

**Writes:**

- `tests\load\results\nfr09_summary.json`, copied to `$runs\nfr09_summary.json` by `run.ps1`;
- up to 1,210 documents, their chunks and their originals.

## 14. Keep the evidence

```powershell
git add $runs
git status                          # only files under the run folder; never a dump, media or logs
```

**`$runs` holds:**

- `results.json` and `results.md` (step 7);
- `snapshot.json` (step 8);
- `scores.json` and `harness.json` (step 9);
- `nfr08_summary.json` (step 11), with the server observed and the run's queueing;
- `threads.json` and `http_check.json` (step 12);
- `nfr09_summary.json` (step 13), likewise.

`$root`, which holds the dump, the media and the logs, Waitress's included, stays on the laptop.
The summaries carry the log's lines from each k6 run's window, so the log itself is not needed. The demonstration
database for 1 November is a separate decision (D-84). Nothing here makes `$db` the demo
database.

## What each step writes

| Step | Writes | Where |
|---|---|---|
| 2 `check_flm.py` | nothing | — |
| 3 `create`, `migrate` | an empty database, then its schema | `$db` in `kmp_prototype-db-1` |
| 4 accounts | 1 Administrator, 21 load-test Employees | `$db` |
| 5 server | uploads; audit, error and Waitress logs | `$root\media`, `$root\logs` |
| 6 register | 1 Employee | `$db` |
| 7 ingest | the corpus; results, with the server | `$db`, `$root\media`; `$runs\results.json`, `results.md` |
| 8 snapshot | dump, its hash, media copy, record | `$root\snapshot`; `$runs\snapshot.json` |
| 9 harness | scores and full records | `$runs\scores.json`, `$runs\harness.json` |
| 10 restore | the database and media, replaced from the snapshot | `$db`, `$root\media` |
| 11 NFR-08 | asks and conversations; summary, with the server observed and its queueing | `$db`, `$root\logs`; `$runs\nfr08_summary.json` |
| 12a threads | the thread run's records | `$runs\threads.json` |
| 12b HTTP check | 3 conversations, 6 asks, their citations; sign-ins; record | `$db`, `$root\logs`; `$runs\http_check.json` |
| 13 NFR-09 | up to 1,210 uploads; summary, with the server observed and its queueing | `$db`, `$root\media`; `$runs\nfr09_summary.json` |

## A copy for another provider (D-113, D-117)

Measuring the `anthropic` provider needs the same corpus, indexed by Voyage. The FLM measurement
database must stay as it is. So the copy is made from its snapshot, under a new name, in a new
session:

```powershell
$py      = 'C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype\.venv\Scripts\python.exe'
$from    = 'kmp_obj02_20261101'                    # the snapshot's database: checked, never touched
$copy    = 'kmp_voyage_20261110'
$copyRoot = 'C:\kmp-measurement\2026-11-10-voyage'  # outside every checkout

& $py scripts\snapshot_measurement_db.py restore --database $from --into $copy `
    --media-root "$copyRoot\media" --from-dir C:\kmp-measurement\2026-11-01\snapshot

$line = Get-Content .env | Where-Object { $_ -match '^DATABASE_URL=' } | Select-Object -First 1
$env:DATABASE_URL = (($line -replace '^DATABASE_URL=', '').Trim()) -replace '/[^/]+$', "/$copy"
$env:MEDIA_ROOT   = "$copyRoot\media"
& $py manage.py migrate                            # migrations newer than the snapshot
```

**`restore --into`** checks the dump and media against `snapshot.json`, as a restore does. It then
creates `$copy`, failing if it exists, and restores into it. The media go into a folder that must be
new or empty. Nothing runs against `$from`.

**Then the switch,** in the same session, with the Voyage key in `.env`:

```powershell
$env:AI_PROVIDER = 'anthropic'
$env:EMBEDDING_DIMENSION = '1024'
& $py manage.py check                              # one Voyage probe: 1024 wide
& $py manage.py reindex --provider anthropic --resize-column $copy
& $py scripts\snapshot_measurement_db.py snapshot --database $copy --media-root "$copyRoot\media" --out-dir "$copyRoot\snapshot"
```

- **Leave `.env` as it is.** The variables set in a session override it, so the everyday setup
  stays on FLM.
- **The copy gets its own snapshot.** Later restores of the Voyage copy are plain restores of that
  snapshot. They need no re-index and spend no Voyage calls.
