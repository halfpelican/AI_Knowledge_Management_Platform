# Objective 02's sixty-second bound at twenty pages, on anthropic, with D-139's summary at upload, 21 November 2026

**The result: within the bound on every one of five uploads, 23.4 to 32.1 s.** Each upload made six
classification requests where the upload made one before D-139: five sections, then the final
request. One upload needed a retry, and stayed within the bound.

**Why it was run.** D-139 summarises a document longer than `CLASSIFICATION_INPUT_TOKENS` in
sections, inside the upload. The bound had been timed at twenty pages on FLM only, with one
classification request (`../2026-11-10/ingestion-twenty-pages-flm/twenty-pages.md`), and never on
`anthropic`. The user's decision of 21 November 2026: time it once on `anthropic` with D-139's code,
on a new scratch database, and record that on FLM the bound is expected to be exceeded.

## What was uploaded

- **The cut:** pages 1 to 20 of D04, `corpus/objective-02/documents/D04_records_management_handbook.pdf`
  (26 pages, SHA-256 `67456517…719b`), cut with pypdf 6.19.0, as on 10 November. It holds 6,539
  whitespace tokens, so D-139 cuts it into five sections.
- **Five copies,** identical but for their PDF `/Title`, so none is refused 409 as a duplicate. Each
  copy's size and SHA-256 are in `run/results.json`. The copies are in
  `C:\kmp-measurement\2026-11-21-obj02-d139\copies`, outside every checkout.
- **The upload:** each through `POST /api/documents`, with D04's department (Legal and Compliance)
  and audience (Employee and Administrator), one after another, timed by
  `scripts/ingest_objective02.py`'s own `ApiSession`: the wall-clock time of the synchronous request.
- **The account:** an Administrator made for this run, its password generated in the uploading
  process and never printed or written, and made unusable when the run ended (D-89).
- **Configuration:**
  - commit `789c05a`, a clean checkout, no uncommitted tracked files;
  - the database `kmp_obj02_d139_20261121`, new: the anthropic snapshot of 10 November (dump
    `6e514170…e6fc`, the corpus already ingested) restored into it and migrated. One rehearsal upload
    of one copy was made on it earlier the same evening, on `186be70`'s code, to check this driver;
  - Waitress 3.0.2 on `127.0.0.1:8011`, started with `--threads=24`, `DEBUG` off;
  - `AI_PROVIDER=anthropic`, `claude-haiku-5-5`, `voyage-4` at 1024.
- **Other load on the machine:** an agent was running pytest break runs in another worktree that
  evening, and may have been during the uploads. That can only have made these times longer.

## The five uploads

| Copy | HTTP | Status | Chunks | Total (s) | Classification (s) | Requests | The rest (s) |
|---|---|---|---|---|---|---|---|
| 1 | 201 | Indexed | 15 | 32.1 | 17.1 | 6 | 15.0 |
| 2 | 201 | Indexed | 15 | 23.4 | 14.6 | 6 | 8.8 |
| 3 | 201 | Indexed | 15 | 24.0 | 16.1 | 6 | 7.9 |
| 4 | 201 | Indexed | 15 | 24.3 | 14.7 | 6 | 9.6 |
| 5 | 201 | Indexed | 15 | 28.2 | 19.7 | 6, and one retry | 8.5 |

- **"Classification"** is the sum of the seconds the server's attempts log reports for the lines
  each upload added (`run/attempts.log`: 31 lines, 25 for sections and 6 for final requests).
- **"The rest"** is extraction, chunking, Voyage's embedding of the 15 chunks, and the transaction.
- **Every upload stored a summary** of 285 to 502 characters with five key points, and none was
  marked as covering only part of the document.
- **The margin:** the slowest upload left 27.9 s. It was the first after the server started.

## The retry

Copy 5's final request was refused once: `'summary' has 652 characters, more than the 600 allowed`.
A reply that breaks a bound is no reply (invariant 10), so the request was sent again, and the
second reply conformed. The refused attempt took 4.1 s and the second 3.7 s.

- **This is D-139's recorded cost (d) happening:** one reply carries the classification and the
  summary, so an over-long summary costs the whole reply.
- **How often, so far:** of the seven final requests a sectioned document has made on Haiku (this
  run's five, the rehearsal's one, and D04's in Objective 05's check), one was refused over its
  summary. That is far too few to give a rate.
- **What three in a row would do:** the document would be stored and indexed, and left without a
  classification or a summary (invariant 8). That has not been seen.

## Beside FLM's run of 10 November

| | FLM, one request per upload (`e182c7a`) | **anthropic, six requests per upload (`789c05a`)** |
|---|---|---|
| total | 43.5 to 51.6 s | 23.4 to 32.1 s |
| classification | 15.1 to 17.1 s | 14.6 to 19.7 s |
| the rest | 28.2 to 34.4 s | 7.9 to 15.0 s |
| the bound | met | met |

## What this does not show

- **FLM under D-139. It is expected to exceed the bound, and that is not measured.** D-139 adds five
  requests to this upload. FLM's fastest attempt on 10 November took 9.3 s, so the five would add at
  least 46 s to 43.5 to 51.6 s. This is arithmetic on measured parts, not a run. By the user's
  decision, Objective 02 stands verified on `anthropic` only.
- **Other twenty-page documents.** All five uploads were the same text.
- **A longer document.** The bound covers twenty pages or fewer. A document past 12,000 tokens makes
  nine requests; D04 whole (8,357 tokens, seven requests) took 14.0 s to classify in Objective 05's
  check the same day.
- **Concurrency.** One sequential client, as in every Objective 02 run; NFR-08 and NFR-13 were not
  re-run.
- **Repeatability.** This is one run. Voyage and Claude are network services, so their times vary.
