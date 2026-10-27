# Item 6 measurement runbook

Stage 5 item 6, as D-83 and D-84 settle it. These are the exact steps, in order, for one
measured run: a fresh database holding exactly Objective 02's corpus, a snapshot of it, the
thirty questions, then the k6 runs. Every step says what it writes and where. Windows
PowerShell 5.1, on the NPU laptop.

**Nothing here may start until the thirty-question set is approved and committed** (D-84 §2).
`corpus/objective-02/questions.json` is a draft until Benjamin and Sagarika approve it. On
approval, its `status` field is changed to say so, and the commit is the freeze. The harness
records the file's SHA-256 with every run, so the run can be checked against the frozen file.

The rules that hold throughout:

- **`kmp` is never touched** (D-84 §1). Every script below refuses a database named `kmp`.
- **The questions run before the load tests, or the snapshot is restored first.** NFR-09 uploads
  documents, which become retrieval candidates. The harness refuses a recorded run when the
  indexed corpus is not exactly the manifest's 25 items, so a forgotten restore is caught.
- **The dump and the media copy live outside every git checkout.** The dump holds every
  account's password hash and is never committed (CLAUDE.md §7). The snapshot script refuses a
  folder inside a checkout.
- **Every gate exits 2 when it refuses**, and says why. Stop there; do not work around it.

## 0. Before the day

1. The questions are approved and committed, and so is every script change being measured. A
   SHA names a commit, not a working tree. Every record notes whether tracked files had
   uncommitted changes.
2. k6 is installed and on `PATH` (for steps 11 and 12 only).
3. **Nothing else is listening on port 8000.** The everyday development server serves `kmp` on
   that port. A second server there would take the uploads and the load test.

   ```powershell
   Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue   # must print nothing
   ```

## 1. The names, in every PowerShell window used below

Each step runs in a PowerShell window that has this block pasted into it. Environment variables
belong to one window, and a value set in the shell wins over `.env`. A window without this block
writes to whatever `.env` names, which in the main checkout is `kmp`.

```powershell
$repo = 'C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype'   # the checkout at the commit under test
$py   = 'C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype\.venv\Scripts\python.exe'
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
$env:DEBUG          = 'False'                       # as the alpha runs (D-64)
$env:FLM_BASE_URL   = 'http://127.0.0.1:8625/v1'    # check_flm.py and run.ps1 read the shell, not .env

([uri]$env:DATABASE_URL).AbsolutePath               # prints /kmp_obj02_<date>: the name only
```

`DEBUG=False` matches D-64. It is also why `create_load_test_users` needs
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
- **The harness needs no account.** It reads the database in-process and takes each
  question's role from the question set.

**Writes:** 22 user rows in `$db`.

## 5. The server, in its own window

Paste the step 1 block, then:

```powershell
& $py manage.py runserver 127.0.0.1:8000 --noreload
```

**This is `runserver`, not Waitress.** Waitress is not in `requirements.txt` until item 9 builds
the alpha deployment, so the run measures the development server. Record that beside the k6
result. `--noreload` keeps it one process: the throttle counters live in that process (D-79),
and a reload would restart them halfway through a run.

**Writes:** uploads to `$root\media`, the audit log and the error log to `$root\logs`, and rows
in `$db`. It writes nothing to `kmp` or to the checkout's `media\`.

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

FR-01's own path: it creates an Employee.

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
- FLM is not v0.9.39, by the CLI and by the server.

**What it records:** the commit SHA, the FLM version and the database name.

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

- the question set is malformed;
- the database is `kmp`;
- `check_flm.py`'s checks fail;
- FLM is not v0.9.39;
- the indexed corpus is not exactly the manifest's 25 items: anything extra, missing, orphaned,
  or embedded by another model.

**What each run records:** the commit, the FLM version, the dump hash, the database name and
the question file's hash. Per run, it also records the partial matches the reply would offer,
with scores (D-56), and the rank and score of the expected source (D-37).

To keep the console text as well, add `*>&1 | Tee-Object "$runs\harness.txt"`. Windows
PowerShell 5.1 writes that file as UTF-16.

**Writes:** `$runs\scores.json` and `$runs\harness.json`. Nothing in the database.

**FR-13 end to end has no tool yet.** It is a proposal in item 6's report, not a step. If it is
built, it runs here, after the harness and before k6. It writes Conversation and QueryLog rows,
which are not retrieval candidates, so it needs no restore.

## 10. Restore, if anything wrote documents or meetings since step 8

Run this if anything uploaded, deleted, reprocessed or pasted since the snapshot: a browser
session, a test upload, an earlier NFR-09 run. Step 9's corpus gate refuses in that case, so
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

**Start the server** (step 5) fresh. A restart before each k6 run empties the throttle counters
(D-82 rule 7). Then, in the step 1 window:

```powershell
$env:LOAD_TEST_PASSWORD = '<the step 4 password>'
.\tests\load\run.ps1 -Test nfr08 -DbDumpSha256 $hash -Python $py
Copy-Item tests\load\results\nfr08_summary.json "$runs\nfr08_summary.json"
```

**Leave `VUS` unset.** Five users is D-84 §3, decided before the run.

**`run.ps1` refuses (exit 2) before k6 starts if:**

- FLM is not v0.9.39;
- `check_flm.py` does not pass.

It records the commit, the FLM version and the dump hash in the results.

**Read the verdict in the JSON, not k6's exit code.** tests/load/README.md has the rest:

- pacing;
- the INVALID and NO DATA verdicts;
- not logging in from a browser while `setup()` runs.

**Report, with the dump hash, commit and FLM version** (D-84 §3):

- the answered-only p90 against 4 s;
- beside it, the all-replies p90, the answered rate and the 8.90 s baseline.

**Writes:**

- `tests\load\results\nfr08_summary.json`, copied to `$runs`;
- QueryLog and Conversation rows in `$db`;
- log lines in `$root\logs`.

## 12. NFR-09, separately, last

Stop the server and start it again, then:

```powershell
.\tests\load\run.ps1 -Test nfr09 -DbDumpSha256 $hash -Python $py
Copy-Item tests\load\results\nfr09_summary.json "$runs\nfr09_summary.json"
```

It takes 32–37 minutes. **Afterwards `$db` is no longer the snapshot.** It holds up to 1,210
`LoadTest` uploads in `$db` and `$root\media`. Before anything else is measured on it, restore
(step 10), including a second NFR-08 run.

**Writes:**

- `tests\load\results\nfr09_summary.json`, copied to `$runs`;
- up to 1,210 documents, their chunks and their originals.

## 13. Keep the evidence

```powershell
git add $runs
git status                          # only files under the run folder; never a dump, media or logs
```

**`$runs` holds:**

- `results.json` and `results.md` (step 7);
- `snapshot.json` (step 8);
- `scores.json` and `harness.json` (step 9);
- the two k6 summaries (steps 11 and 12).

`$root`, which holds the dump, the media and the logs, stays on the laptop. The demonstration
database for 1 November is a separate decision (D-84). Nothing here makes `$db` the demo
database.

## What each step writes

| Step | Writes | Where |
|---|---|---|
| 2 `check_flm.py` | nothing | — |
| 3 `create`, `migrate` | an empty database, then its schema | `$db` in `kmp_prototype-db-1` |
| 4 accounts | 1 Administrator, 21 load-test Employees | `$db` |
| 5 server | uploads; audit and error logs | `$root\media`, `$root\logs` |
| 6 register | 1 Employee | `$db` |
| 7 ingest | the corpus; results | `$db`, `$root\media`; `$runs\results.json`, `results.md` |
| 8 snapshot | dump, its hash, media copy, record | `$root\snapshot`; `$runs\snapshot.json` |
| 9 harness | scores and full records | `$runs\scores.json`, `$runs\harness.json` |
| 10 restore | the database and media, replaced from the snapshot | `$db`, `$root\media` |
| 11 NFR-08 | asks and conversations; summary | `$db`, `$root\logs`; `$runs\nfr08_summary.json` |
| 12 NFR-09 | up to 1,210 uploads; summary | `$db`, `$root\media`; `$runs\nfr09_summary.json` |
