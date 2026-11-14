# Objective 02 — ingestion results

Run started 2026-11-13T16:42:20+11:00 against `http://127.0.0.1:8000`, by `scripts/ingest_objective02.py`, from
`corpus/objective-02/manifest.json`. Times are the wall-clock time of the synchronous upload
or paste request, which includes extraction, chunking, embedding by Voyage and, for a
document, classification by Claude at upload (FR-10). The chunk
count is the one check made outside the API: a read-only ORM count after the run.

`corpus/objective-02/manifest.json` is the only manifest the script reads. The team's
`Objective02_Manifest.xlsx` was the source it was transcribed from, and is not read.

Commit `6e1efd1115bfe9e85ff211000c1c0885e603505e`. Provider `anthropic`:
`claude-haiku-5-5` and `voyage-4` at 1024, by this process's settings; FLM takes no part.
Database `kmp_alpha_20261113`.
Server: waitress 3.0.2, 24 threads (--threads on the command line), pid 62952, DEBUG off.

| ID | Kind | Scope | HTTP | Status | Seconds | Pages | Chunks | Admin finds | Employee finds | Result |
|---|---|---|---|---|---|---|---|---|---|---|
| D01 | document | Employee, Administrator | 201 | Indexed | 10.4 | 1 | 1 | yes | yes | PASS |
| D02 | document | Employee, Administrator | 201 | Indexed | 2.4 | 1 | 1 | yes | yes | PASS |
| D03 | document | Employee, Administrator | 201 | Indexed | 2.8 | 1 | 1 | yes | yes | PASS |
| D04 | document | Employee, Administrator | 201 | Indexed | 12.6 | 26 | 19 | yes | yes | PASS |
| D05 | document | Employee, Administrator | 201 | Indexed | 2.7 | 1 | 1 | yes | yes | PASS |
| D06 | document | Employee, Administrator | 201 | Indexed | 2.1 | 1 | 1 | yes | yes | PASS |
| D07 | document | Employee, Administrator | 201 | Indexed | 1.6 | — | 1 | yes | yes | PASS |
| D08 | document | Employee, Administrator | 201 | Indexed | 2.9 | — | 1 | yes | yes | PASS |
| D09 | document | Administrator | 201 | Indexed | 3.3 | — | 1 | yes | no | PASS |
| D10 | document | Employee, Administrator | 201 | Indexed | 3.1 | — | 1 | yes | yes | PASS |
| D11 | document | Employee, Administrator | 201 | Indexed | 3.5 | — | 1 | yes | yes | PASS |
| D12 | document | Employee, Administrator | 201 | Indexed | 3.3 | — | 1 | yes | yes | PASS |
| D13 | document | Employee, Administrator | 201 | Indexed | 2.5 | — | 1 | yes | yes | PASS |
| D14 | document | Employee, Administrator | 201 | Indexed | 3.1 | — | 1 | yes | yes | PASS |
| D15 | document | Administrator | 201 | Indexed | 3.3 | — | 1 | yes | no | PASS |
| D16 | document | Administrator | 201 | Indexed | 3.1 | — | 1 | yes | no | PASS |
| D17 | document | Employee, Administrator | 201 | Indexed | 2.1 | — | 1 | yes | yes | PASS |
| D18 | document | Employee, Administrator | 201 | Indexed | 2.4 | — | 1 | yes | yes | PASS |
| D19 | document | Employee, Administrator | 201 | Indexed | 2.0 | — | 1 | yes | yes | PASS |
| D20 | document | Employee, Administrator | 201 | Indexed | 2.8 | — | 1 | yes | yes | PASS |
| T01 | transcript | Employee, Administrator | 201 | Indexed | 0.8 | — | — | yes | yes | PASS |
| T02 | transcript | Administrator | 201 | Indexed | 1.1 | — | — | yes | no | PASS |
| T03 | transcript | Employee, Administrator | 201 | Indexed | 0.5 | — | — | yes | yes | PASS |
| T04 | transcript | Employee, Administrator | 201 | Indexed | 0.5 | — | — | yes | yes | PASS |
| T05 | transcript | Administrator | 201 | Indexed | 0.6 | — | — | yes | no | PASS |
| I01 | invalid | Employee, Administrator | 415 | — | 0.1 | — | — | — | — | PASS |
| I02 | invalid | Employee, Administrator | 413 | — | 0.6 | — | — | — | — | PASS |
| I03 | invalid | Employee, Administrator | 422 | Extraction failed | 0.2 | 1 | 0 | — | — | PASS |
| I04 | invalid | Employee, Administrator | 422 | Insufficient content | 0.2 | — | 0 | — | — | PASS |
| I05 | invalid | Employee, Administrator | 422 | Extraction failed | 0.2 | — | 0 | — | — | PASS |
| B01 | invalid | Employee, Administrator | 409 | — | 0.1 | 1 | — | — | — | PASS |

Items that missed their expected result: none.
Documents of 20 pages or fewer over 60s: none.
