# Objective 02 — ingestion results

Run started 2026-11-10T23:37:52+11:00 against `http://127.0.0.1:8000`, by `scripts/ingest_objective02.py`, from
`corpus/objective-02/manifest.json`. Times are the wall-clock time of the synchronous upload
or paste request, which includes extraction, chunking, embedding by Voyage and, for a
document, classification by Claude at upload (FR-10). The chunk
count is the one check made outside the API: a read-only ORM count after the run.

`corpus/objective-02/manifest.json` is the only manifest the script reads. The team's
`Objective02_Manifest.xlsx` was the source it was transcribed from, and is not read.

Commit `df73de5c5e33cc0f998257600c2d54923f972c1c`. Provider `anthropic`:
`claude-haiku-5-5` and `voyage-4` at 1024, by this process's settings; FLM takes no part.
Database `kmp_obj02_anthropic_20261110`.
Server: waitress 3.0.2, unknown threads, DEBUG off.

| ID | Kind | Scope | HTTP | Status | Seconds | Pages | Chunks | Admin finds | Employee finds | Result |
|---|---|---|---|---|---|---|---|---|---|---|
| D01 | document | Employee, Administrator | 201 | Indexed | 9.9 | 1 | 1 | yes | yes | PASS |
| D02 | document | Employee, Administrator | 201 | Indexed | 2.0 | 1 | 1 | yes | yes | PASS |
| D03 | document | Employee, Administrator | 201 | Indexed | 3.8 | 1 | 1 | yes | yes | PASS |
| D04 | document | Employee, Administrator | 201 | Indexed | 9.8 | 26 | 19 | yes | yes | PASS |
| D05 | document | Employee, Administrator | 201 | Indexed | 2.0 | 1 | 1 | yes | yes | PASS |
| D06 | document | Employee, Administrator | 201 | Indexed | 2.4 | 1 | 1 | yes | yes | PASS |
| D07 | document | Employee, Administrator | 201 | Indexed | 3.3 | — | 1 | yes | yes | PASS |
| D08 | document | Employee, Administrator | 201 | Indexed | 3.5 | — | 1 | yes | yes | PASS |
| D09 | document | Administrator | 201 | Indexed | 4.1 | — | 1 | yes | no | PASS |
| D10 | document | Employee, Administrator | 201 | Indexed | 3.7 | — | 1 | yes | yes | PASS |
| D11 | document | Employee, Administrator | 201 | Indexed | 2.3 | — | 1 | yes | yes | PASS |
| D12 | document | Employee, Administrator | 201 | Indexed | 3.1 | — | 1 | yes | yes | PASS |
| D13 | document | Employee, Administrator | 201 | Indexed | 2.3 | — | 1 | yes | yes | PASS |
| D14 | document | Employee, Administrator | 201 | Indexed | 4.1 | — | 1 | yes | yes | PASS |
| D15 | document | Administrator | 201 | Indexed | 2.7 | — | 1 | yes | no | PASS |
| D16 | document | Administrator | 201 | Indexed | 2.2 | — | 1 | yes | no | PASS |
| D17 | document | Employee, Administrator | 201 | Indexed | 3.4 | — | 1 | yes | yes | PASS |
| D18 | document | Employee, Administrator | 201 | Indexed | 3.7 | — | 1 | yes | yes | PASS |
| D19 | document | Employee, Administrator | 201 | Indexed | 4.0 | — | 1 | yes | yes | PASS |
| D20 | document | Employee, Administrator | 201 | Indexed | 2.7 | — | 1 | yes | yes | PASS |
| T01 | transcript | Employee, Administrator | 201 | Indexed | 0.7 | — | — | yes | yes | PASS |
| T02 | transcript | Administrator | 201 | Indexed | 0.6 | — | — | yes | no | PASS |
| T03 | transcript | Employee, Administrator | 201 | Indexed | 1.2 | — | — | yes | yes | PASS |
| T04 | transcript | Employee, Administrator | 201 | Indexed | 0.7 | — | — | yes | yes | PASS |
| T05 | transcript | Administrator | 201 | Indexed | 0.7 | — | — | yes | no | PASS |
| I01 | invalid | Employee, Administrator | 415 | — | 0.1 | — | — | — | — | PASS |
| I02 | invalid | Employee, Administrator | 413 | — | 0.7 | — | — | — | — | PASS |
| I03 | invalid | Employee, Administrator | 422 | Extraction failed | 0.1 | 1 | 0 | — | — | PASS |
| I04 | invalid | Employee, Administrator | 422 | Insufficient content | 0.1 | — | 0 | — | — | PASS |
| I05 | invalid | Employee, Administrator | 422 | Extraction failed | 0.1 | — | 0 | — | — | PASS |
| B01 | invalid | Employee, Administrator | 409 | — | 0.1 | 1 | — | — | — | PASS |

Items that missed their expected result: none.
Documents of 20 pages or fewer over 60s: none.
