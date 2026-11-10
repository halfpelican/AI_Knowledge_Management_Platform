# Objective 02's sixty-second bound at twenty pages, with classification at upload (FLM), 10 November 2026

**The result: within the bound on every one of five uploads, 43.5 to 51.6 s.** Each upload's
classification succeeded at the first attempt. A retry would add one more attempt, and could take
a twenty-page document past sixty seconds.

This follows the corpus re-time (`../ingestion-classify-flm/retime.md`). That run could not test a
document near the bound: the corpus's only multi-page PDF has 26 pages, outside it, and every
document the bound covers is one page or has no pages. The user asked for a twenty-page document to
be timed directly.

## What was uploaded

- **The cut:** pages 1 to 20 of D04, `corpus/objective-02/documents/D04_records_management_handbook.pdf`
  (26 pages, SHA-256 `67456517c0cea1166f65ff0c511248eb22f1ae55cf48e51f51850f0a4368719b`), cut with
  pypdf 6.19.0.
- **Five copies,** identical but for their PDF `/Title`, so each has its own content hash and none is
  refused 409 as a duplicate (FR-08 compares the SHA-256 of the whole file). Each copy's size and
  SHA-256 are in `results.json`.
  - The copies were not kept: they were in the run's folder, deleted with the user's approval.
  - The cut can be made again from the recorded source and method. A different pypdf version may
    write different bytes.
- **The upload:** each through `POST /api/documents`, with D04's department (Legal and Compliance)
  and audience (Employee and Administrator), one after another.
  - The account was an Administrator made for this run, its password generated in the uploading
    process and never printed or written.
  - Each upload was timed by `scripts/ingest_objective02.py`'s own `ApiSession`: the wall-clock time
    of the synchronous request.
- **Configuration:**
  - the corpus run's database, `kmp_obj02_20261110classify`, after that run;
  - its server set-up: Waitress 3.0.2 started with `--threads=24`, `DEBUG` off;
  - FLM v0.9.39, with `scripts/check_flm.py` passing just before and nothing else using FLM;
  - `AI_PROVIDER=flm`, commit `e182c7a`.

## The five uploads

| Copy | HTTP | Status | Chunks | Total (s) | Classification (s) | The rest (s) |
|---|---|---|---|---|---|---|
| 1 | 201 | Indexed | 15 | 51.6 | 17.1 | 34.4 |
| 2 | 201 | Indexed | 15 | 45.8 | 15.1 | 30.7 |
| 3 | 201 | Indexed | 15 | 43.5 | 15.3 | 28.2 |
| 4 | 201 | Indexed | 15 | 45.4 | 15.1 | 30.3 |
| 5 | 201 | Indexed | 15 | 43.7 | 15.4 | 28.3 |

- **"Classification"** is the one attempt's time from the attempts log (`attempts.log` beside this
  file, which holds this run's five lines). Every attempt was the first of three, and parsed.
- **"The rest"** is extraction, chunking, embedding the 15 chunks on the NPU, and the transaction.
- **The margin:** the slowest upload left 8.4 s. The first was the slowest, and the first upload
  after the server starts may carry warm-up cost; that is not separated here.

## What a retry would do

- **When one happens:** when an attempt's reply fails the schema, `MAXIMUM_CLASSIFY_ATTEMPTS` allows
  two more. The corpus run that night saw one such failure in 21 calls (D19: invalid JSON after
  9.4 s), and this run none in 5: one in 26 in all, too few to give a rate.
- **What it costs:** one retry adds one more attempt. That is about 9 s if the failed reply comes
  back early, as D19's did, up to the 15 to 17 s an attempt takes on this text.
- **The estimate:** that would put these uploads at about 53 to 69 s. Some of them would pass sixty
  seconds. Two retries would pass it on every one.
- **This is arithmetic on measured parts, not a measured retry.** No retry happened at twenty pages.

## What this does not show

- **Other twenty-page documents.** All five uploads were the same text, so the spread is FLM's
  timing variance on one input. A twenty-page document that chunks into more passages, or classifies
  more slowly, would take longer.
- **The bound on `anthropic`.** D-122 is about to make it the default. If M8 runs there, the bound is
  re-timed on a Voyage-indexed database (`../ingestion-classify-flm/retime.md`).
