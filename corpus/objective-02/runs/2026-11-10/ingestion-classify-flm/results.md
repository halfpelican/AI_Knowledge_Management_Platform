# Objective 02 — ingestion results

Run started 2026-11-10T21:54:25+11:00 against `http://127.0.0.1:8000`, by `scripts/ingest_objective02.py`, from
`corpus/objective-02/manifest.json`. Times are the wall-clock time of the synchronous upload
or paste request, which includes extraction, chunking and embedding on the NPU. The chunk
count is the one check made outside the API: a read-only ORM count after the run.

`corpus/objective-02/manifest.json` is the only manifest the script reads. The team's
`Objective02_Manifest.xlsx` was the source it was transcribed from, and is not read.

Commit `749a68964771350912dccc2bd120ca29df58d1db`. FLM `v0.9.39` by `flm version`,
`v0.9.39` by the server. Database `kmp_obj02_20261110classify`.
Server: waitress 3.0.2, unknown threads, DEBUG off.

| ID | Kind | Scope | HTTP | Status | Seconds | Pages | Chunks | Admin finds | Employee finds | Result |
|---|---|---|---|---|---|---|---|---|---|---|
| D01 | document | Employee, Administrator | 201 | Indexed | 19.3 | 1 | 1 | yes | yes | PASS |
| D02 | document | Employee, Administrator | 201 | Indexed | 14.9 | 1 | 1 | yes | yes | PASS |
| D03 | document | Employee, Administrator | 201 | Indexed | 15.2 | 1 | 1 | yes | yes | PASS |
| D04 | document | Employee, Administrator | 201 | Indexed | 61.3 | 26 | 19 | yes | yes | PASS |
| D05 | document | Employee, Administrator | 201 | Indexed | 15.1 | 1 | 1 | yes | yes | PASS |
| D06 | document | Employee, Administrator | 201 | Indexed | 13.9 | 1 | 1 | yes | yes | PASS |
| D07 | document | Employee, Administrator | 201 | Indexed | 13.0 | — | 1 | yes | yes | PASS |
| D08 | document | Employee, Administrator | 201 | Indexed | 12.8 | — | 1 | yes | yes | PASS |
| D09 | document | Administrator | 201 | Indexed | 12.4 | — | 1 | yes | no | PASS |
| D10 | document | Employee, Administrator | 201 | Indexed | 12.3 | — | 1 | yes | yes | PASS |
| D11 | document | Employee, Administrator | 201 | Indexed | 12.7 | — | 1 | yes | yes | PASS |
| D12 | document | Employee, Administrator | 201 | Indexed | 13.1 | — | 1 | yes | yes | PASS |
| D13 | document | Employee, Administrator | 201 | Indexed | 20.0 | — | 1 | yes | yes | PASS |
| D14 | document | Employee, Administrator | 201 | Indexed | 11.8 | — | 1 | yes | yes | PASS |
| D15 | document | Administrator | 201 | Indexed | 13.2 | — | 1 | yes | no | PASS |
| D16 | document | Administrator | 201 | Indexed | 14.9 | — | 1 | yes | no | PASS |
| D17 | document | Employee, Administrator | 201 | Indexed | 11.6 | — | 1 | yes | yes | PASS |
| D18 | document | Employee, Administrator | 201 | Indexed | 15.1 | — | 1 | yes | yes | PASS |
| D19 | document | Employee, Administrator | 201 | Indexed | 24.5 | — | 1 | yes | yes | PASS |
| D20 | document | Employee, Administrator | 201 | Indexed | 14.6 | — | 1 | yes | yes | PASS |
| T01 | transcript | Employee, Administrator | 201 | Indexed | 2.4 | — | — | yes | yes | PASS |
| T02 | transcript | Administrator | 201 | Indexed | 2.2 | — | — | yes | no | PASS |
| T03 | transcript | Employee, Administrator | 201 | Indexed | 2.1 | — | — | yes | yes | PASS |
| T04 | transcript | Employee, Administrator | 201 | Indexed | 2.1 | — | — | yes | yes | PASS |
| T05 | transcript | Administrator | 201 | Indexed | 1.6 | — | — | yes | no | PASS |
| I01 | invalid | Employee, Administrator | 415 | — | 0.1 | — | — | — | — | PASS |
| I02 | invalid | Employee, Administrator | 413 | — | 0.7 | — | — | — | — | PASS |
| I03 | invalid | Employee, Administrator | 422 | Extraction failed | 0.1 | 1 | 0 | — | — | PASS |
| I04 | invalid | Employee, Administrator | 422 | Insufficient content | 0.1 | — | 0 | — | — | PASS |
| I05 | invalid | Employee, Administrator | 422 | Extraction failed | 0.1 | — | 0 | — | — | PASS |
| B01 | invalid | Employee, Administrator | 409 | — | 0.1 | 1 | — | — | — | PASS |

Items that missed their expected result: none.
Documents of 20 pages or fewer over 60s: none.
