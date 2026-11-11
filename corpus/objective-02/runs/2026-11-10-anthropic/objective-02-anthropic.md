# Objective 02 on the anthropic provider, 10 November 2026: ingestion through the server, with Voyage and Haiku at upload

**The result: met.** The script ended "Missed: none; over the bound: none", exit 0:
- every valid item reached its indexed status and was found by its phrase;
- every Administrator-only item was found by the Administrator and left no trace for the Employee;
- every invalid item was refused with its documented error;
- no document of twenty pages or fewer took more than sixty seconds.

**Timings.** The slowest such document took 9.9 s: D01, the run's first upload. The 26-page D04,
outside the bound's page limit, took 9.8 s.

**Against FLM.** Both FLM runs also met the objective. The like-for-like FLM run is #82's, which
also classifies at upload; on it the slowest such document took 24.5 s and D04 61.3 s.

`ingestion/results.json` and `results.md` are the copied script's own output, unedited.

## How it ran

`docs/measurement-runbook.md` steps 1 to 8, adapted for the anthropic provider. PR #82's FLM
re-time was the model for the accounts.

| | |
|---|---|
| commit | `df73de5`: main at `12eb81f` (#82 merged; its only changes since PR #81's `a9934eb` are evidence and a note) plus this folder's copy and driver, committed before the run. No uncommitted tracked changes |
| configuration | provider `anthropic`: Voyage `voyage-4` at 1024 for every chunk, and Claude `claude-haiku-5-5` (D-121) for FR-10's classification at upload (D-105). Values: D-120's 0.2687 / 0.2468, and D-122's classification threshold 0.72 |
| step 1, the environment | the run's own `DATABASE_URL` (`.env`'s, with only the name swapped, never printed), `MEDIA_ROOT`, the four log paths under `C:\kmp-measurement\2026-11-10-obj02-anthropic`, the provider variables and `DEBUG=False`, set in each shell. `.env` was left alone |
| step 2, the FLM gate | not run: FLM takes no part. The copy's provider gate stands in for it. It checks this process's settings, both keys (present, never printed), the database name and the three tuned values |
| step 3, the database | `kmp_obj02_anthropic_20261110`, new and empty, made by `snapshot_measurement_db.py create` with the user's approval, then `manage.py migrate` from nothing at `EMBEDDING_DIMENSION` 1024. Both vector columns are `vector(1024)` (`setup/create.txt`, `setup/migrate.txt`) |
| step 4, the Administrator | `corpus.admin@example.com`, made by `createsuperuser --noinput` in the driver's process. No load-test accounts; NFR-08 makes and retires its own (D-89) |
| step 5, the server | started by the user in their own PowerShell window with the run's environment: `waitress-serve --listen=127.0.0.1:8000 --threads=24 config.wsgi:application` (D-85), Waitress 3.0.2, `DEBUG` off ("Serving on" at 23:36:19) |
| step 6, the Employee | `corpus.employee@example.com`, registered through FR-01's own route, `POST /api/auth/register`: 201, role Employee |
| step 7, the ingestion | `ingest_objective02_anthropic.py`, a copy of `scripts/ingest_objective02.py` changed only where FLM was named (`.diff` beside it), run by `run_ingestion_with_accounts.py` (`ingestion/`) |
| step 8, the snapshot | with the server stopped: dump `6e514170055c685f32f839a22f3a3d2f7571e98ea69bb2b58150d770ec9fe6fc`, 23 media files, in `C:\kmp-measurement\2026-11-10-obj02-anthropic\snapshot`, outside every checkout. `snapshot.json` here is its record; the snapshot script's FLM line records whatever FLM server is reachable, and FLM took no part |

**The passwords and the server's database.** Both passwords came from a CSPRNG in the driver's
process, were checked against the password validators, and were never printed or written anywhere.
Nobody can sign in as either account now. Before anything was sent through the server, the driver
signed in through it as the new Administrator: 200, Administrator. That password existed only in
`kmp_obj02_anthropic_20261110`, so the server was serving that database, and the ingestion's own two
sign-ins showed it again.

**The server's thread count.** It was observed apart from the copy's own record, and the record
says "unknown".
- The copy observes the server before uploading. In this tool environment its
  `Get-NetTCPConnection` lookup found no listener, so `results.json` records the thread count as
  unknown. Its D-85 gate refuses only on evidence, so it went on.
- The same lookup by `scripts/server_record.py`, minutes before, did see the listener: Waitress
  3.0.2, `--threads=24` on pid 65868's command line, `DEBUG` off
  (`setup/server_observed_before_ingestion_2.txt`).
- The process chain's command lines are in `setup/server_processes.txt`: `waitress-serve.exe`,
  then the venv's python, then the listener, all with `--threads=24`.
- A first lookup, seconds after the start, had also missed the listener
  (`setup/server_observed_before_ingestion.txt`).

## What the server wrote, read back

- **Chunks:** 43, every one `voyage-4` at 1024: 38 for documents, 5 for meetings.
- **Classifications:** 20, one per indexed document, each by `claude-haiku-5-5`, each parsed on its
  first attempt (`ingestion/attempts.log`).
- **Documents:** 20 Indexed, 2 Extraction failed and 1 Insufficient content: the stored invalid items
  I03, I05 and I04. Meetings: 5 Indexed.
- **Users:** the two accounts above, and no others.
- **Logs:** Waitress logged no queueing (`ingestion/waitress.log`), and no errors log was written.

## Beside FLM's runs

| | FLM, 1 November (`5314d86`) | FLM with classification at upload, #82 (`749a689`) | **anthropic, this run (`df73de5`)** |
|---|---|---|---|
| what an upload includes | extraction, chunking, embedding on the NPU | the same, plus gemma3:4b's classification | extraction, chunking, Voyage's embedding, Haiku's classification |
| items as expected | 31 of 31 | 31 of 31 | 31 of 31 |
| documents of 20 pages or fewer: fastest, median, slowest | 1.2, 1.3, 6.5 s | 11.6, 13.9, 24.5 s | 2.0, 3.3, 9.9 s |
| D04, 26 pages, 19 chunks (outside the bound) | 33.3 s | 61.3 s | 9.8 s |
| transcripts: fastest, median, slowest | 1.4, 1.4, 1.7 s | 1.6, 2.1, 2.4 s | 0.6, 0.7, 1.2 s |
| the bound | met | met | met |

- **The first upload is the slowest one-page document** on both the 1 November run and this one: D01
  at 6.5 s and 9.9 s. That is consistent with first-request warm-up, but it was not separated from
  D01 itself here.
- **Classification adds to every document's time,** and on Haiku it adds less than on gemma3:4b.
  The attempts logs show it:
  - Haiku took 1.4 to 3.0 s per classification (median 2.1 s), all 20 parsed on the first attempt.
  - On #82's FLM run, attempts took 9.3 to 17.8 s (median 11.9 s), and one document needed a second
    attempt.

## What this result does not show

- **A twenty-page document timed directly.** The corpus's documents are one page, or have no pages
  (DOCX, XLSX, TXT), except D04 at 26. #82 timed D04's first twenty pages directly on FLM. That was
  not repeated here, so the bound on anthropic is shown for this corpus's documents, and D04's 9.8 s
  is an outside figure only.
- **Concurrency.** One sequential client, as in every Objective 02 run; NFR-08 is item 4.
- **Classification quality at upload.** It is Objective 05's to judge (item 1).
- **Repeatability.** This is one run. Voyage and Claude are network services, so their times vary
  run to run in a way the NPU's did not.

## Spend

| | |
|---|---|
| Claude (Haiku 5.5) | 20 classification calls made by the server at upload, 38,509 tokens in and 5,749 out, about **$0.0067**, summed from the server's attempts log (`ingestion/attempts.log`), since the calls happen in the server, not in the script's process |
| Voyage (voyage-4) | the 43 chunk embeddings and the startup probes. Within Voyage's free allowance |

## Files

- `ingest_objective02_anthropic.py` and `.diff`: the copy, and `run_ingestion_with_accounts.py`, the
  driver. Both committed before the run (`df73de5`).
- `setup/`: the database creation and migration, the server observations and process command lines,
  and the snapshot console.
- `ingestion/`: the script's `results.json` and `results.md`, the driver's console, and the server's
  attempts and Waitress logs. The attempts log carries token counts and timings and quotes nothing of
  the replies.
- `snapshot.json`: step 8's record. The dump and media stay in `C:\kmp-measurement`.
