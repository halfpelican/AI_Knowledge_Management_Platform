# Objective 02 — ingestion results

Run started 2026-10-06T09:49:46+11:00 against `http://127.0.0.1:8000`, by `scripts/ingest_objective02.py`, from
`manifest.json`. Times are the wall-clock time of the synchronous upload or paste request,
which includes extraction, chunking and embedding on the NPU. The chunk count is the one
check made outside the API: a read-only ORM count after the run.

`manifest.json` in this folder is the only manifest the script reads. The team's
`Objective02_Manifest.xlsx` was the source it was transcribed from, and is not read.

**The search columns were re-run on 2026-10-06T10:06:35+11:00** with `--search-only`, against the
manifest's current phrases, after D-71 made keyword search collapse whitespace. Every
other column is from the ingestion run above. Nothing was uploaded a second time.

| ID | Kind | Scope | HTTP | Status | Seconds | Pages | Chunks | Admin finds | Employee finds | Result |
|---|---|---|---|---|---|---|---|---|---|---|
| D01 | document | Employee, Administrator | 201 | Indexed | 1.1 | 1 | 1 | yes | yes | PASS |
| D02 | document | Employee, Administrator | 201 | Indexed | 0.9 | 1 | 1 | yes | yes | PASS |
| D03 | document | Employee, Administrator | 201 | Indexed | 1.0 | 1 | 1 | yes | yes | PASS |
| D04 | document | Employee, Administrator | 201 | Indexed | 21.8 | 26 | 19 | yes | yes | PASS |
| D05 | document | Employee, Administrator | 201 | Indexed | 1.0 | 1 | 1 | yes | yes | PASS |
| D06 | document | Employee, Administrator | 201 | Indexed | 1.0 | 1 | 1 | yes | yes | PASS |
| D07 | document | Employee, Administrator | 201 | Indexed | 1.0 | — | 1 | yes | yes | PASS |
| D08 | document | Employee, Administrator | 201 | Indexed | 1.0 | — | 1 | yes | yes | PASS |
| D09 | document | Administrator | 201 | Indexed | 0.9 | — | 1 | yes | no | PASS |
| D10 | document | Employee, Administrator | 201 | Indexed | 0.9 | — | 1 | yes | yes | PASS |
| D11 | document | Employee, Administrator | 201 | Indexed | 0.9 | — | 1 | yes | yes | PASS |
| D12 | document | Employee, Administrator | 201 | Indexed | 1.2 | — | 1 | yes | yes | PASS |
| D13 | document | Employee, Administrator | 201 | Indexed | 1.1 | — | 1 | yes | yes | PASS |
| D14 | document | Employee, Administrator | 201 | Indexed | 1.2 | — | 1 | yes | yes | PASS |
| D15 | document | Administrator | 201 | Indexed | 1.1 | — | 1 | yes | no | PASS |
| D16 | document | Administrator | 201 | Indexed | 1.0 | — | 1 | yes | no | PASS |
| D17 | document | Employee, Administrator | 201 | Indexed | 0.9 | — | 1 | yes | yes | PASS |
| D18 | document | Employee, Administrator | 201 | Indexed | 0.9 | — | 1 | yes | yes | PASS |
| D19 | document | Employee, Administrator | 201 | Indexed | 0.9 | — | 1 | yes | yes | PASS |
| D20 | document | Employee, Administrator | 201 | Indexed | 0.9 | — | 1 | yes | yes | PASS |
| T01 | transcript | Employee, Administrator | 201 | Indexed | 1.1 | — | — | yes | yes | PASS |
| T02 | transcript | Administrator | 201 | Indexed | 0.9 | — | — | yes | no | PASS |
| T03 | transcript | Employee, Administrator | 201 | Indexed | 0.9 | — | — | yes | yes | PASS |
| T04 | transcript | Employee, Administrator | 201 | Indexed | 0.8 | — | — | yes | yes | PASS |
| T05 | transcript | Administrator | 201 | Indexed | 0.8 | — | — | yes | no | PASS |
| I01 | invalid | Employee, Administrator | 415 | — | 0.1 | — | — | — | — | PASS |
| I02 | invalid | Employee, Administrator | 413 | — | 0.1 | — | — | — | — | PASS |
| I03 | invalid | Employee, Administrator | 422 | Extraction failed | 0.1 | 1 | 0 | — | — | PASS |
| I04 | invalid | Employee, Administrator | 422 | Insufficient content | 0.0 | — | 0 | — | — | PASS |
| I05 | invalid | Employee, Administrator | 422 | Extraction failed | 0.1 | — | 0 | — | — | PASS |
| B01 | invalid | Employee, Administrator | 409 | — | 0.1 | 1 | — | — | — | PASS |

Items that missed their expected result: none.
Documents of 20 pages or fewer over 60s: none.
