# Decisions log

Architectural decisions that the proposal (`Project_8-proposal_complete_V4.5.docx`)
leaves open, or that were settled by choosing a provider. One entry per decision,
each with its status, date, the decision itself, the rationale and what follows from
it. Stage 0 of `M6-BUILD-PROMPT.md` exits only when nothing here is still open.

Rules for this file:

- A decision that is not recorded here is not settled. If you hit one while
  building, stop and ask; do not pick silently (`CLAUDE.md` §9).
- A change of environment that alters setup for everyone is recorded here too, for
  example anyone moving development into WSL (`docs/ai-provider.md` §3).
- To change a settled decision, add a dated entry that supersedes it rather than
  editing the original.

| ID | Decision | Status | Date |
|---|---|---|---|
| D-01 | Python version: 3.12 for all developers and CI | Settled | 2026-09-12 |
| D-02 | Login field for FR-01 / FR-02: email address | Settled | 2026-09-12 |
| D-03 | Embedding model and dimension: embed-gemma, 768 | Settled by the FLM decision | 2026-09-12 |
| D-04 | API key ownership and spend caps: none needed for the build phase | Settled by the FLM decision | 2026-09-12 |
| D-05 | Uploaded files live in a local media directory | Settled by the team plan of 1 Sep 2026 | 2026-09-12 |
| D-06 | Front-end language: JavaScript with JSX, not TypeScript | Settled | 2026-09-12 |
| D-07 | ContentChunks source reference: source_type + source_id, no database FK (G1) | Settled per docs/schema-v1.md §4 | 2026-09-12 |
| D-08 | ContentChunks carries embedding, embedding_model, embedding_dimension (G2) | Settled per docs/schema-v1.md §4 | 2026-09-12 |
| D-09 | Documents column is `department`, not `department_tag` (G3) | Settled per docs/schema-v1.md §4 | 2026-09-12 |
| D-10 | Sessions use Django's session framework, no Sessions table of our own (G4) | Settled per docs/schema-v1.md §4 | 2026-09-12 |
| D-11 | Documents.visible_to_roles stays text[] of role names (G5) | Settled per docs/schema-v1.md §4 | 2026-09-12 |
| D-12 | Foreign-key deletion policy for migration v1 | Settled | 2026-09-12 |

---

## D-01 · Python version

**Status:** Settled · **Date:** 2026-09-12

**Decision.** Python **3.12** everywhere: all three developers and CI. The version is
pinned once, in `.python-version` at the repository root, and CI reads that file
rather than repeating the number.

**Rationale.** Benjamin is on 3.14, Haseeb on 3.13, and the CI runner is 3.12. Code
written against the lowest of those runs on all of them; code written against 3.13
or 3.14 can pass locally and fail in CI after merge. The lowest common version is the
one that cannot produce a "works on my machine" failure, so it is the standard.

**Consequences.**

- `.python-version` (`3.12`) is added in the Stage 0 commit. `uv` and `pyenv` both
  read it when creating an environment.
- CI is pinned in Stage 1 item 7, when the GitHub Actions workflow is created:
  `actions/setup-python` with `python-version-file: .python-version`, so the file
  stays the single source of truth. Stage 0 builds no workflow because there is
  nothing for one to run yet.
- Every developer creates the virtual environment from 3.12, for example
  `uv python install 3.12` then `uv venv --python 3.12`. Running the suite on 3.13 or
  3.14 is not a supported configuration; a green run there proves nothing about CI.
- Checked on 2026-09-12: Benjamin's machine has 3.14 only, so 3.12 must be installed
  before Stage 1 starts.

## D-02 · Login field

**Status:** Settled · **Date:** 2026-09-12

**Decision.** Users register (FR-01) and log in (FR-02) with **email address and
password**. Email is the unique identifier of an account. There is no separate
username field.

**Rationale.**

- This is a workplace platform. Every employee already has exactly one work email
  address, it is already unique, and it is the identifier they use for everything
  else. A username would be a second identifier to invent, check for collisions and
  forget.
- Registration has to collect an email address regardless. Making it the login key
  removes a field and a uniqueness rule instead of adding one.
- A custom `User` model is required anyway, because the schema uses UUID primary
  keys (Stage 1). Setting `USERNAME_FIELD = "email"` on that model costs nothing,
  but Django fixes the user model at the first migration, which is why this could
  not stay open past Stage 0.
- FR-03 account lockout (NIT3004) counts failed attempts per account; the email
  address is a stable key for that.
- Not chosen: username. It is Django's default, but the default `User` model is not
  being used, and a second identifier buys nothing here.

**Consequences.**

- `apps/accounts` `User`: `USERNAME_FIELD = "email"`, no `username` column, `email`
  unique case-insensitively (normalise to lower case on save and on login).
- FR-01 validates the address format and rejects a duplicate with the status code
  the FR-01 section names.
- FR-02 returns one generic failure message for an unknown address and a wrong
  password. Login must not disclose whether an address is registered.
- If the proposal's `Users` table definition names a `username` column, that is a
  contradiction to raise here before the Stage 1 migration is written. Do not add
  both.

## D-03 · Embedding model and dimension

**Status:** Settled by the FLM decision (`CLAUDE.md` §4) · **Date:** 2026-09-12

**Decision.** Development, testing and demonstration embed with **embed-gemma**
(embeddinggemma-300m, served by FastFlowLM) at **768 dimensions**.
`EMBEDDING_DIMENSION=768`. Every `ContentChunk` row records `embedding_model` and
`embedding_dimension` (FR-08).

**Rationale.** FLM is the default provider, so the embedding model is whatever FLM
serves alongside the chat model, and that is embed-gemma at 768 dimensions.
Vectors from different models are not comparable but still produce a plausible
similarity score, so the model and dimension are fixed here, recorded on every
chunk, and retrieval compares only chunks whose recorded model matches the query
model (risk R10). Verified on 2026-09-12: `scripts/check_flm.py` received
768-dimensional vectors from `embed-gemma` on FLM v1.0.2.

**Consequences.**

- The pgvector column is sized from `settings.EMBEDDING_DIMENSION`, never a literal.
- The startup check built in Stage 1 refuses to boot when the provider's probe
  embedding does not match `EMBEDDING_DIMENSION`.
- Voyage (`voyage-4`, per `docs/ai-provider.md` §4) remains the documented
  production path. Switching to it is a full re-index event:
  `python manage.py reindex --provider anthropic`, with the Voyage dimension
  confirmed against its model card first. Development and production are two
  separate indexes.

## D-04 · API key ownership and spend caps

**Status:** Settled by the FLM decision (`CLAUDE.md` §4) · **Date:** 2026-09-12

**Decision.** No AI API key is provisioned for the build phase. Development, testing
and demonstration use local inference on the NPU through FLM: no key
(`FLM_API_KEY=flm` is a placeholder, not a credential), no metered cost, and no
uploaded content leaving the machine. An Anthropic key, and a Voyage key for
embeddings, are needed only if the `anthropic` production path is exercised.

**Rationale.** Local inference removes the two costs a hosted provider carries
during development: money and data exposure. Risk R11 (cost overrun) is closed for
the whole build phase. Risk R12 (sensitive content sent to an overseas provider) is
substantially reduced for the build phase, because nothing leaves the developer's
machine; it returns only if the production path is switched on.

**Consequences.**

- Should the production path be exercised, the key is provisioned and held by the
  team lead, with a spend cap set when the key is created, kept only in `.env` and
  never committed (`CLAUDE.md` §7). Switching provider also triggers D-03's re-index.
- The test suite never needs a key: it injects a stub `AIService`
  (`docs/ai-provider.md` §6), so CI runs with no AI credentials at all.

## D-05 · Uploaded file storage

**Status:** Settled by the team plan of 1 September 2026, recorded here · **Date:** 2026-09-12

**Decision.** Uploaded originals are stored on the local filesystem under a media
directory configured from the environment (`MEDIA_ROOT`), not inside the database
and not in cloud object storage. Cloud storage is a later change behind the same
storage interface.

**Rationale.** The team's 1 September work assignment lists "Where do uploaded
files live?" among the five things that quietly cost a week if left open, and
settles it as "local media directory for now, cloud storage later. Decide, write it
down, don't drift." The alpha runs on one machine, a directory is the boring option,
and Django's file storage abstraction means a later move to object storage does not
touch application code.

**Consequences.**

- `MEDIA_ROOT` is read from the environment when FR-08 lands in Stage 3, defaulting
  to `media/` under the repository root, which is gitignored.
- The original file and the extracted plain text are stored separately
  (`CLAUDE.md` §6 and the rag-pipeline rules), so the original is never re-parsed
  for retrieval.
- Stored filenames are sanitised. No upload may write outside the media directory.

## D-06 · Front-end language

**Status:** Settled · **Date:** 2026-09-12

**Decision.** The React application is written in JavaScript with JSX, from Vite's
`react` template. Not TypeScript.

**Rationale.** The team's 1 September plan says of the front end: "React is our
weakest skill and it will expand to fill whatever room it is given." TypeScript adds
a type layer, a build-time failure class and configuration to learn, while the M6
gate is scored on the breadth of working requirements. JavaScript is the boring
choice (`CLAUDE.md` §9). The API contract is enforced by server-side validation and
tests, not by front-end types.

**Consequences.**

- Files under `frontend/src/` are `.jsx` and `.js`. No `tsconfig`, no type
  packages. ESLint from the Vite template is the only static check.
- Decided by the build session on 2026-09-12 under the Stage 1 delegation because
  the scaffold could not be created without choosing. Overturn it before the first
  feature screen is written in Stage 2; after that a conversion costs days.

## D-07 · ContentChunks source reference is polymorphic (schema gap G1)

**Status:** Settled, applying the recommendation in `docs/schema-v1.md` §4 · **Date:** 2026-09-12

**Decision.** `ContentChunks` references its source with two columns,
`source_type` (fixed vocabulary `document` | `meeting`) and `source_id` (UUID), with
no database-level foreign key. Referential integrity is enforced in application code,
and deleting a document or a meeting deletes its chunks explicitly, in the same
transaction, in application code.

**Rationale.** The proposal writes the column as `UUID (FK → Documents/Meetings)`,
which cannot be a real foreign key to two tables. The chosen shape matches the pattern
FR-10 already uses for `ContentTags` ("keyed on source type and identifier"), so both
join paths look the same. The alternative, two nullable FK columns with a check
constraint, keeps database enforcement but makes one join path differ from the other.

**Consequences.** `SOURCE_TYPES` lives in `apps/core/constants.py`. An index on
`(source_type, source_id)` supports the join. Stage 3 ingestion and Stage 4 retrieval
must never assume the database will reject a dangling `source_id`.

## D-08 · Embedding columns on ContentChunks (schema gap G2)

**Status:** Settled, applying the recommendation in `docs/schema-v1.md` §4 · **Date:** 2026-09-12

**Decision.** `ContentChunks` carries `embedding` (pgvector `vector`, dimension from
`settings.EMBEDDING_DIMENSION`), `embedding_model` (text) and `embedding_dimension`
(integer), indexed on `embedding_model`.

**Rationale.** The proposal's table list omits any embedding column even though FR-08
requires that "the embedding model and dimension are recorded against every stored
vector". The three columns are the minimum that satisfies the clause. The omission is
a documentation gap, not a design choice, and it is what makes D-03 and risk R10
enforceable in code.

**Consequences.** Retrieval filters on `embedding_model` before ranking. The column
dimension is never a literal in code.

## D-09 · Documents.department (schema gap G3)

**Status:** Settled, applying the recommendation in `docs/schema-v1.md` §4 · **Date:** 2026-09-12

**Decision.** The column is `department`. The name `department_tag` is not used
anywhere: not in the schema, the API contract, the front end or the tests.

**Rationale.** FR-11 says `department_tag`; FR-12 and FR-14 say `department`. One name
must be used everywhere, and two of the three sections use `department`.

## D-10 · Sessions (schema gap G4)

**Status:** Settled, applying the recommendation in `docs/schema-v1.md` §4 · **Date:** 2026-09-12

**Decision.** There is no hand-rolled `Sessions` table. FR-04 is satisfied by Django's
own session framework: `django.contrib.sessions` with database-backed storage,
`SESSION_COOKIE_AGE` of 60 minutes read from `apps/core/constants.py`, and
`SESSION_SAVE_EVERY_REQUEST = True` so the 60 minutes is an inactivity expiry.
Logout flushes the session on the server, which is the "Sessions (Delete)" operation
FR-04 lists.

**Rationale.** FR-04 lists `Sessions (Delete)` in its CRUD and requires server-side
destruction on logout plus a 60-minute inactivity expiry, but gives no field list.
Django's framework provides server-side storage, deletion on logout and the inactivity
expiry without inventing a table the proposal never specified.

**Consequences.** The `django_session` table is created by Django's migration, not by
migration v1. Stage 2 (FR-02, FR-04) builds login and logout on this framework; a
token a client keeps after logout must stop working, and there is a test for that.

## D-11 · Documents.visible_to_roles stays text[] (schema gap G5)

**Status:** Settled, applying the recommendation in `docs/schema-v1.md` §4 · **Date:** 2026-09-12

**Decision.** `visible_to_roles` is a Postgres text array holding role names, exactly
the proposal's shape. It is the FR-11 permission filter.

**Rationale.** FR-11 is written against this shape, and the two roles in this project
will never be renamed. Keeping the proposal's shape avoids rewriting FR-11's logic.

**Consequences.** The role name is denormalised into every document row, and renaming
a role would break the filter. That is a known limitation to state plainly if asked at
the demonstration, not a strength.

## D-12 · Foreign-key deletion policy for migration v1

**Status:** Settled · **Date:** 2026-09-12

**Decision.** The proposal specifies deletion behaviour only for `ExtractedContent`
(cascade). Migration v1 applies one policy everywhere else:

- References to `Users`, `Roles` and `Tags` are `PROTECT`. A user, role or tag that
  something still references cannot be deleted; tags are deactivated instead
  (`Tags.active`), as the schema already says.
- Rows owned by a parent cascade with it: `ExtractedContent` and `MeetingAttendees`
  with their parent, `RolePermissions` with its role or permission,
  `AnswerCitations` with its query or its chunk, `ContentTags` with nothing (its
  polymorphic source is handled in application code, see D-07).
- `QueryLog.conversation_id` is `SET NULL`: a deleted conversation leaves its queries
  behind as one-off records, so the query log is never silently thinned.

**Rationale.** Query and search logs are the project's main quality signal (the two
no-answer paths) and must survive deletions. FR-15 requires permissioned document
deletion, so a citation row must not block deleting a document; with the chunk gone
the citation has nothing to cite. Protecting user, role and tag rows prevents an
accidental cascade from destroying audit history.

**Consequences.** Deleting a document in Stage 5 (FR-15) deletes its extracted content
and chunks (D-07) in one transaction; the database then cascades citations. Decided by
the build session on 2026-09-12 because migration v1 cannot be written without it;
overturn before FR-15 is built if the team disagrees.
