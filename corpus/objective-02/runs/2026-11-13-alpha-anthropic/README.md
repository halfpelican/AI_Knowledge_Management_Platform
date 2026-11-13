# The alpha's database built under Anthropic, 13 November 2026

The user decided on 13 November 2026 that the alpha runs on the anthropic provider, and that a
database keeps the provider it was set up with (D-131). So the alpha did not switch
`kmp_demo_20261101`, the FLM alpha's database, which stays as it was (D-88). It moved to a new
database, `kmp_alpha_20261113`, built here from item 6's corpus under Anthropic. The user approved
creating it.

## What ran, in order

| Step | What | Record |
|---|---|---|
| 1 | The alpha worktree moved, detached, to `origin/main` at `6e1efd1`, clean. Its venv synced from `requirements.txt` (no change needed). | |
| 2 | Its FLM `.env` kept byte for byte as `.env.flm-20261101` (gitignored). A new `.env` names `kmp_alpha_20261113`, `C:\kmp-demo\2026-11-13\media` and `...\logs`, `AI_PROVIDER=anthropic`, `claude-haiku-5-5`, `voyage-4` at 1024, and the two keys, copied from the main checkout's `.env` without printing them. | |
| 3 | `CREATE DATABASE kmp_alpha_20261113`, refusing an existing or protected name. | `setup/create.txt` |
| 4 | `manage.py migrate` from the alpha worktree, after Django named the database. | `setup/migrate.txt` |
| 5 | Both vector columns read back: `content_chunks.embedding` and `knowledge_gaps.embedding` are `vector(1024)`. | `setup/vector-widths.txt` |
| 6 | `manage.py check --deploy`: exactly the four HTTPS warnings D-64 expects, and no `ai.W001`, so Voyage answered. | `setup/check-deploy.txt` |
| 7 | The front end built (`npm ci`, `npm run build`). | |
| 8 | Waitress started in its own window, as `docs/alpha-deployment.md` step 6 does, from `C:\kmp-demo\2026-11-13\serve-alpha.ps1`. That script reads the database URL from the alpha's `.env` and refuses to start unless Django names `kmp_alpha_20261113`. | `server-logs/waitress.log` |
| 9 | The two accounts and the corpus, through the alpha's own server: `run_ingestion_with_accounts.py` and `ingest_objective02_anthropic.py`, this folder's copies of the 10 November anthropic run's, with only the database name changed (`*.diff`). | `ingestion/` |
| 10 | Item 6's tags: `scripts/seed_objective02_tags.py`, a dry run and then the run. | `tags/` |
| 11 | Every indexed document classified again against those tags: `manage.py classify_documents --all`. | `classification/` |
| 12 | The runbook's five smoke checks passed, and the deployment was recorded in `KMP-alpha-deployments.txt`, outside the repository: commit `6e1efd1`, `dirty=False`. | |

## What it holds

- **Accounts:** `corpus.admin@example.com`, the Administrator, made by `createsuperuser --noinput`.
  `corpus.employee@example.com`, an Employee, registered through FR-01's route. Their passwords
  came from `secrets`, were held in memory only, and were never shown or stored. So nobody can sign
  in as either until the user sets a password with `manage.py changepassword`, as D-88 arranged for
  the FLM alpha.
- **The corpus:** D01 to D20 indexed, and T01 to T05, the meetings, indexed. The invalid items were
  refused with their documented errors: I01 415, I02 413, I03 and I05 422 extraction failed, I04 422
  insufficient content, and B01 409. "Missed: none; over the bound: none."
- **Chunks:** 48, every one `voyage-4` at 1024. 38 are from documents. Of the 10 from meetings, 5
  are transcripts and 5 are FR-16 summaries, marked `ai_generated`. All five summaries are Ready,
  with 25 action items.
- **Tags:**
  - 14 tags: Process 4, Project 4 and Topic 6. One Project value, `atlas`, is marked grown, because
    only material some role cannot read carries it.
  - 48 links from item 6's manifest, `applied_by="user"` and confirmed.
  - 15 links FR-10 applied when the documents were classified again (`applied_by="ai"`, not yet
    confirmed).
  - One topic proposal waits for review: "customer complaints".

## The tag order, and why the documents were classified twice

The ingestion classified each document at upload (FR-10, D-105). That happened before the tags
existed, because this run followed D-88's order, seeding after the corpus, and D-88 predates
classification at upload. `scripts/seed_objective02_tags.py` says to run it before any document is
classified. So after the ingestion there were no tags, only 13 topic proposals across 10
documents.

The user then chose to seed and classify again. The seed restored item 6's tags as the FLM alpha
had them, with `atlas` withheld from Employees. `classify_documents --all` then classified all 20
documents against that vocabulary: 20 classified, 0 failed.

## Cost

- **Claude, in the server** (`server-logs/attempts.log`):
  - 20 classifications at upload: 38,509 prompt tokens and 4,989 completion tokens;
  - 5 meeting summaries: 11,705 and 3,848.
- **Claude, in the process that classified again:** 20 calls of the same kind. Their tokens are not
  in the server's log.
- **Voyage:** 48 chunks and the startup probes.
- **Total:** well under $1.

## Not done here

- **Steps 9 and 10 of `docs/alpha-deployment.md`,** the scheduled FR-19 cycle and FR-16 retry. The
  session's permission check refused to register scheduled tasks, so the user registers them.
- **The passwords,** which are the user's to set.
- **D-40's screening of demonstration questions** on this database. The threads and questions
  screened for the FLM alpha were screened on EmbeddingGemma's vectors.
