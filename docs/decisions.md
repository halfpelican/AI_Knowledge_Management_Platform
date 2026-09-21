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
| D-13 | Query, search, citation and conversation models live in apps/retrieval | Settled | 2026-09-12 |
| D-14 | RBAC uses the project's Roles/Permissions tables only, never Django's Group/Permission | Settled | 2026-09-12 |
| D-15 | Accepted upload formats: four, PDF DOCX XLSX TXT (user label D-06) | Settled by the user | 2026-09-12 |
| D-16 | G6: Meetings.visible_to_roles in schema v1, not scoped by attendance (user label D-07) | Settled by the user | 2026-09-12 |
| D-17 | visible_to_roles denormalised onto ContentChunks at ingestion (user label D-08) | Settled by the user | 2026-09-12 |
| D-18 | G7: Documents storage path deferred to migration v2 in Stage 3 (user label D-09) | Settled by the user | 2026-09-12 |
| D-19 | Retry semantics: 3 total attempts, 1 initial plus 2 retries (user label D-10) | Settled by the user | 2026-09-12 |
| D-20 | Logged in-place dependency edit to meetings 0001 (CLAUDE.md §7 exception) | Recorded | 2026-09-12 |
| D-21 | API authentication is the Django session cookie with CSRF; Vite dev proxy keeps it same-origin | Settled | 2026-09-12 |
| D-22 | Audit-log entries are JSON lines in a file (AUDIT_LOG_PATH); schema v1 has no audit table | Settled provisionally, confirm | 2026-09-13 |
| D-23 | Stage 2 conventions: registration starts no session, administrators may change their own role, Django password validators | Settled | 2026-09-13 |
| D-24 | Security review findings and accepted residues for Stage 2 | Settled | 2026-09-13 |
| D-25 | Stage 2 corrected against the proposal FR text; supersedes parts of D-23 and D-24 | Settled | 2026-09-13 |
| D-26 | Stage 2 security review round two: throttling, a bounded lockout oracle, the last-administrator guard | Settled | 2026-09-13 |
| D-27 | NO_ANSWER_MESSAGE wording, the PROVISIONAL marker removed | Settled | 2026-09-14 |
| D-28 | Document status vocabulary: the proposal's six values, superseding schema v1's five | Settled by the user | 2026-09-21 |
| D-29 | visible_to_roles at ingestion: optional on upload, both roles when omitted | Settled by the user | 2026-09-21 |
| D-30 | FR-08's contribute permission: role-level `contribute_content`, no knowledge areas | Settled by the user | 2026-09-21 |
| D-31 | A token is a whitespace-delimited word; MINIMUM_CONTENT_LENGTH is 50 tokens | Settled by the user | 2026-09-21 |
| D-32 | FR-08's retry re-runs ingestion on the stored original; a failed ingestion reserves no duplicate slot | Settled by the user | 2026-09-21 |
| D-33 | Stage 3 audit: FR-08 classification deferred with FR-10; FR-09's 422; the 409 existence oracle | Recorded | 2026-09-21 |

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

## D-13 · Placement of the query models

**Status:** Settled · **Date:** 2026-09-12

**Decision.** `Conversations`, `QueryLog`, `SearchLogs` and `AnswerCitations` are
models in `apps/retrieval`. The app holds models and migrations only until Stage 4,
when the rag-pipeline agent adds retrieval logic to it.

**Rationale.** The Stage 1 layout describes `apps/retrieval` as "empty for now", but
schema v1 has to put these four tables somewhere and they are retrieval's domain.
Putting them in `apps/api` would place models in the API layer; putting them in
`apps/core` would make core a dumping ground.

**Consequences.** Stage 4 must not assume an empty app. Stage 2 (FR-13) reads and
writes `Conversation` through these models.

## D-14 · Django's auth tables are not the RBAC tables

**Status:** Settled · **Date:** 2026-09-12

**Decision.** FR-05 and FR-06 use only the project's `roles`, `permissions` and
`role_permissions` tables. Django's `auth_permission`, `auth_group` and
`auth_group_permissions` exist in the database because `django.contrib.auth` is
required by Django REST Framework, but no code reads or writes them, and no
authorisation decision ever consults `User.has_perm`, groups or Django permissions.

**Rationale.** Two permission systems in one database is the "implemented twice
under different names" hazard the set-level audit checks for. The proposal specifies
the project's tables; Django's are incidental.

**Consequences.** Stage 2's RBAC permission classes resolve the user's role and its
`RolePermissions` rows, nothing else. The `User` model has no `PermissionsMixin`.

## D-15 · Accepted upload formats: four (user label D-06)

**Status:** Settled by the user · **Date:** 2026-09-12

**Decision.** `ACCEPTED_FORMATS` is exactly PDF, DOCX, XLSX and TXT.

**Rationale (as given).** The proposal is internally inconsistent: six formats in
FR-08's upload area, four parsers in §9.2, three in FR-08's own example error
message. DOC and XLS are legacy binary formats requiring an external binary
(LibreOffice or antiword) that must work on three development machines and in CI.
Accepting a format that always returns 415 is a demonstrable defect.

**Consequences.** `ACCEPTED_FORMATS` and the client-side rejection message (Stage 3
upload screen) both name the same four. `CLAUDE.md` §5 is amended to match.
`Documents.file_type` choices are the same four; the change lands as migration
`documents 0004` because the branch was already pushed.

## D-16 · G6: Meetings.visible_to_roles in schema v1 (user label D-07)

**Status:** Settled by the user · **Date:** 2026-09-12

**Decision.** `Meetings.visible_to_roles` is added, mirroring `Documents` exactly.

**Rationale (as given).** Meetings are not scoped by attendance: knowledge must
outlive its participants, and a second scoping mechanism would mean two code paths
through the FR-11 filter. `MeetingAttendees` remains a participation record for
FR-20, not an access control.

**Consequences.** Lands as migration `meetings 0002` (the branch was pushed).
`docs/schema-v1.md` §1 gains the column and §4 gains G6.

## D-17 · visible_to_roles denormalised onto ContentChunks (user label D-08)

**Status:** Settled by the user · **Date:** 2026-09-12

**Decision.** Every `ContentChunks` row carries `visible_to_roles`, stamped from its
source at ingestion.

**Rationale (as given).** This makes the FR-11 "filter before ranking" invariant
structurally true: the permission predicate and the vector live on one table, so no
query shape can rank first. Changing a source's visibility re-stamps its chunks.

**Consequences.** Lands as migration `documents 0005`. Stage 3 ingestion stamps the
column; Stage 4 retrieval filters on it before any similarity computation; a
visibility change on a document or meeting re-stamps its chunks in the same
transaction.

## D-18 · G7: Documents storage path deferred to migration v2 (user label D-09)

**Status:** Settled by the user · **Date:** 2026-09-12

**Decision.** The column recording where a stored original lives is added in
migration v2, at the start of Stage 3, not in schema v1.

**Rationale (as given).** Its shape depends on the storage implementation: a Django
`FileField` would be the column. Defining it before that decision would pre-empt it.

**Consequences.** Stage 3 item 1 begins with that migration. D-05 still fixes the
storage location as a local media directory.

## D-19 · Retry semantics: three total attempts (user label D-10)

**Status:** Settled by the user · **Date:** 2026-09-12

**Decision.** Three total attempts, one initial plus two retries, uniformly for
`MAXIMUM_GENERATION_ATTEMPTS`, `MAXIMUM_EMBED_ATTEMPTS` and
`MAXIMUM_CLASSIFY_ATTEMPTS`.

**Rationale (as given).** Matches the proposal's "2 retries" wording and the
presentation prep sheet, which supersedes the earlier one-retry statement.

**Consequences.** NFR-19's test asserts exactly three provider calls before the 503.
The SDK clients are constructed with `max_retries=0` so these constants are the only
retry policy.

## D-20 · In-place dependency edit to a pushed migration

**Status:** Recorded under the `CLAUDE.md` §7 migrations exception · **Date:** 2026-09-12

**What was edited.** Commit `e08da51` added `("documents", "0001_initial")` to the
`dependencies` of `apps/meetings/migrations/0001_initial.py` after the branch had
been pushed, so that `migrate` applies Documents before Meetings as
`docs/schema-v1.md` §5 lists. No operation changed.

**Evidence that no other environment had applied it.** The branch
`chore/stage-1-environment-and-schema` was unmerged and had been pushed for under an
hour; the only databases that had run the migration were the author's local
docker-compose database, rebuilt from empty in the same session, and GitHub Actions
service containers, which are discarded after each run. A missing dependency cannot
be supplied by a later migration, which is why the exception exists.

**Why it is here.** The build session first reported that no pushed migration had
been edited; the auditor found the diff. This entry corrects the record.

## D-21 · API authentication: session cookie with CSRF, same-origin in development

**Status:** Settled · **Date:** 2026-09-12

**Decision.** The API authenticates requests with Django's session cookie
(`rest_framework.authentication.SessionAuthentication`), which is the session
framework D-10 already chose. There are no bearer tokens. Unsafe requests carry the
CSRF token in the `X-CSRFToken` header, read from the `csrftoken` cookie that the
login and current-user responses set. `DEFAULT_PERMISSION_CLASSES` is
`IsAuthenticated` (`CLAUDE.md` §6 invariant 4); the registration and login endpoints
opt out explicitly. In development the Vite dev server proxies `/api` to Django so
the browser sees one origin and no CORS configuration exists; in the alpha
deployment the built front end is served from the same origin as the API.

**Rationale.** FR-04 requires server-side session destruction on logout and a
60-minute inactivity expiry, both of which the session framework provides and a
bearer token would have to reimplement. One origin removes cross-site cookie and
CORS configuration, the most common way a capstone login "works locally and fails
deployed". The session cookie is `HttpOnly`, so the front end never handles a
credential.

**Consequences.** "A token must stop working after logout" (Stage 2 item 2) is
tested by replaying the session cookie after logout and asserting 401. The
`Authorization: Bearer` support in the front-end API client is removed. Role changes
take effect on the next request because the role is read from the database per
request, never cached in the session.

## D-22 · Audit-log medium for role changes

**Status:** Settled provisionally, to confirm against the proposal · **Date:** 2026-09-13

**Decision.** FR-05's "role changes write an audit-log entry" is satisfied by one JSON
line per change on a dedicated `audit` logger, written to the file named by
`AUDIT_LOG_PATH` (default `logs/audit.log`, gitignored): timestamp, event, actor id
and email, target id and email, old role, new role.

**Rationale.** `docs/schema-v1.md` defines no audit table in §1 or §2, and inventing
one would violate the schema rule. A structured log file satisfies the clause with no
schema change and can be replayed into a table later if the proposal turns out to
require one.

**Consequences.** If the proposal's FR-05 section names a table, migration v2 adds it
and the logger call becomes a row insert; the call site is one function in
`apps/accounts/audit.py`.

## D-23 · Stage 2 conventions the contract did not state

**Status:** Partly superseded by D-25 on 2026-09-13 · **Date:** 2026-09-13

> Read D-25 before relying on anything here. The proposal's FR text overturned two
> of the conventions below: an Administrator may **not** change their own role, and
> the password rules are FR-01's complexity clause rather than Django's defaults.
> The entry is left standing, as this file's rules require, so the superseded
> reasoning stays legible.

- Registration returns 201 and starts no session; the client signs in through login.
- An Administrator may change any user's role, including their own, and a same-role
  change still writes an audit entry. Nothing in the available text forbids
  self-demotion; revisit if the proposal does.
- Password rules are Django's four default validators, with similarity checked
  against name and email.
- `locked_until` is stamped on every failure at or beyond `LOCKOUT_THRESHOLD` and is
  not cleared by a successful login; enforcing and clearing it is FR-03 (NIT3004).
- Unmatched API paths return a JSON 404 body.

## D-24 · Stage 2 security review: fixes and accepted residues

**Status:** Partly superseded by D-25 on 2026-09-13 · **Date:** 2026-09-13

> The second accepted residue below — that lockout enforcement is FR-03's and
> `locked_until` is never cleared — is overturned by D-25. The lock is FR-02's own
> clause and is now enforced. The rest of this entry stands.

The adversarial review of FR-01, FR-02, FR-04, FR-05 and FR-06 confirmed two defects.
Both are fixed, with a regression test each.

**Fixed: login accepted a cross-site form POST.** DRF applies `csrf_exempt` to every
view and enforces CSRF only after it has found a session user, so an anonymous POST
was never checked. A hidden cross-site form could therefore sign a victim's browser
into the attacker's account; `SESSION_COOKIE_SAMESITE` does not help, because it
governs when a cookie is sent and not when one is set. The fix is
`DEFAULT_PARSER_CLASSES` of `JSONParser` alone, which is what
`docs/api-contract.md` always said: a cross-site HTML form can send only form or
multipart bodies, and a cross-site `fetch` sending JSON is held by a preflight that
this same-origin deployment (D-21) never answers. Not taken: also enforcing CSRF on
login unconditionally. It would cost the client nothing, because the current-user
call already sets the cookie before the form is submitted, and it remains available
if the deployment ever stops being same-origin.

**Fixed: registration returned 500 for an address longer than the column.** The
serializer's email field was unbounded, so an over-long address passed validation and
the insert raised `DataError`, a sibling of `IntegrityError` rather than a subclass,
which the 409 handler did not catch. The field is now bounded by the column's own
length, so the two cannot drift, and the contract's 400 is returned.

**Accepted, not fixed.**

- *Login timing distinguishes a registered address from an unknown one by roughly one
  to two percent.* The failed-attempt update runs only when the address exists;
  bcrypt runs either way, which equalises the expensive half. FR-01 mandates a 409 on
  duplicate registration, which is an exact, unthrottled enumeration oracle for every
  address in the organisation, so closing a one percent timing channel would change
  nothing. Say that plainly rather than claiming login is non-enumerable.
- *Nothing rate-limits login or registration, and `locked_until` is written but never
  read.* Enforcement is FR-03 (SHOULD, NIT3004) and out of the M6 gate. The columns
  are populated now so FR-03 has the history it needs.
- *`locked_until` is not cleared by a successful login* (D-23). Whoever builds FR-03
  must clear it explicitly, or a user who succeeds after five failures stays locked
  for the rest of the window. Recorded here because the trap is invisible until the
  field is first read.
- *The JSON 404 for an unmatched path is only returned when `DEBUG` is false.* Django
  bypasses `handler404` under `DEBUG`, so the development default shows the technical
  404 page instead. The contract line holds for the alpha deployment, not for a
  developer's machine.
- *The audit log covers role changes only* (D-22), which is FR-05's clause. It is not
  a general audit trail: there is no entry for login, logout, a failed login or a
  refused privilege escalation.

**Clean.** No route lacks a server-side check; no privilege escalation through a
request body, including a role supplied at registration; 401 and 403 do not leak
account existence; no password or hash in any response or log; logout destroys the
session server-side so a captured cookie stops working; no session fixation; no
authorisation decided only in React; no secret committed.

## D-25 · Stage 2 corrected against the proposal's FR text

**Status:** Settled, one bullet amended by D-26 · **Date:** 2026-09-13 · **Supersedes:** parts of D-23 and D-24

> One rule below is out of date: this entry says a failed attempt during an
> active lock neither moves the counter nor extends the window. D-26 changes the
> first half. The counter does move, so that a locked account can stop announcing
> whether a guess was right once guessing passes a ceiling; the window is still
> never extended. Everything else here stands.

`Project_8-proposal_complete_V4.5.docx` reached this machine on 2026-09-13, after
Stage 2 was built. Until then the endpoints were built from
`docs/api-contract.md`, which the build session had compiled from the requirement
summaries available to it. The requirements auditor then checked all five
requirements clause by clause against the FR text and returned CONTRADICTS SPEC:
five clauses were implemented as the opposite of what the FR states and eight more
were absent. This entry records the corrections. The contract's Stage 2 section was
rewritten against the FR text first, because the tests and the front end had both
been built from it and every further hour of work compounded the error.

**Overturned by the FR text.**

| Clause | Was | Now | FR wording |
|---|---|---|---|
| FR-01 password rules | Django's four default validators (D-23) | min 8 characters, 1 uppercase, 1 number, 1 special character, enforced server-side | "Password must meet complexity rules (min 8 chars, 1 uppercase, 1 number, 1 special character)" |
| FR-02 locked account | recorded only, never enforced (D-24) | `403` when the lock holds **and** the password matched, the ordinary `401` when it did not; a success clears `locked_until` | "403 forbidden if account is locked"; "five consecutive failures lock the account for 15 minutes" |
| FR-02 malformed address | `401`, treated as an unknown address | `400`, checked before the database lookup | "Email format checked before database lookup"; the login pseudocode returns 400 explicitly |
| FR-04 logout | `204` | `200` | "200 OK on success" |
| FR-05 unknown role | `400` | `404` | "404 Not Found if user/role doesn't exist" |
| FR-05 request body | the role's name | `{"role_id": "<uuid>"}` | "Receives { user_id, new_role_id }" |
| FR-05 self-demotion | permitted (D-23) | refused | "a user cannot remove their own administrator role, preventing accidental lockout of the last administrator" |

The self-demotion clause was the highest risk of the seven. Permissions are held only
against roles (D-14), there is no Django admin, and `manage_roles` is the only
permission, so a demonstrator who demoted themselves removed role management from the
running system with no in-product way back.

**Correction, 2026-09-13, after the first implementation.** This entry first read
FR-02's "403 forbidden if account is locked" as unqualified and specified a 403
whatever the password. That was wrong, and the build agent caught it: the proposal's
`handleLoginAttempt()` pseudocode branches on the password result inside the locked
case and returns 401 where the password was wrong, giving the reason in the document
itself — "Confirming a lock to anyone who merely knows the email address would
convert a protective measure into an account-enumeration tool." FR-03's messaging
clause says the same. A uniform 403 would have meant five wrong passwords return 401
for an unregistered address and 403 for a registered one, which is precisely the
oracle the proposal set out to avoid. The Responses line is the summary; the
pseudocode is the detail, and the detail wins. The code, the contract and the row
above now say: 403 only where the password matched, otherwise the ordinary 401,
byte-identical to an unknown address, with a test asserting that equality.

**Two further conventions inside the lockout, neither settled by the proposal.**

- A failed attempt made *during* an active lock neither moves the counter nor
  extends the window, so "locks the account for 15 minutes" stays literally true
  rather than becoming indefinite under a sustained attack.
- `failed_attempts` resets once the lock window expires, taken from FR-03's "the
  counter also resets automatically once the lockout window expires". Without it a
  single wrong password after the window would re-lock the account at once, and
  FR-02's "five consecutive failures" would be false of it.

**A gap that arrived with enforcement.** FR-03 also defines a `LoginAttempts` table
and an administrator release route, both out of the M6 gate and both unbuilt. So a
lockout now has no evidence trail (a forgotten password and a distributed attempt
look alike) and a locked user's only remedy is to wait out the window. Worth stating
at the demonstration rather than being asked.

**A departure from FR-02's wording, recorded because the auditor found it
undocumented.** FR-02's Business Logic says "On success a session is established
carrying the user's role identifier." The session carries no role; a test asserts it
(`test_rbac.py`). The role is re-read from `role_permissions` on every request
instead (D-21). The substitution is deliberate and stronger: a role stamped into the
session at login would go stale the moment an administrator changed it, and FR-05's
change would not take effect until the user logged out and back in. Re-reading per
request is what makes "a role change takes effect on the next request without
re-login" true, which Stage 2's own exit condition requires. The literal clause is
not met; its purpose is exceeded. Stated here so an assessor reading FR-02 against
the test sees a decision rather than a mismatch.

**Conventions that remain, because the FR enumerates no code.**

- Refusing a self-demotion answers `403`. FR-05 lists only 200, 403 and 404.
- Registration answers `201`. The FR states it, so this is no longer a convention;
  it is recorded here only because D-23 previously listed it as one.

**Deferred, with the reason on record.**

- FR-02 redirects to a role-specific dashboard on success. The dashboards are FR-14,
  built in Stage 5, so the branch on role lands with them. Recorded rather than
  overlooked.
- FR-03's lockout interface (the "2 attempts remaining" warning and the countdown)
  stays out of the M6 gate. Only the enforcement moved, because the 403 sits in
  FR-02's own Responses list.

**Conflict to resolve in `CLAUDE.md`.** §5 annotates `LOCKOUT_THRESHOLD` and
`LOCKOUT_DURATION` as "(FR-03, NIT3004)". The proposal puts the lock in FR-02's
Business Logic and the 403 in FR-02's Responses, and FR-02 is a MUST-HAVE in the M6
gate. The code now follows the proposal, per `CLAUDE.md` §1 ("The full specification
is `Project_8-proposal_complete_V4.5.docx`... Never invent a requirement"). The
annotation in §5 should be corrected to FR-02, but `CLAUDE.md` is the team's file and
this entry raises the conflict rather than editing it.

**Still open, for the team.** The front end has no test runner and no CI step, so
eight of the thirteen gaps the auditor found were in the untested layer. Whether
front-end testing is in scope for M6 is not settled anywhere and needs a decision
before Stage 3, which ships more screens.

## D-26 · Stage 2 security review, round two

**Status:** Settled · **Date:** 2026-09-13 · **Amends:** one bullet of D-25

The adversarial review of the code that landed for D-25 confirmed five defects, each
reproduced with a live probe. All five are fixed, with tests.

**1. The lock withheld the session but not the answer.** While an account was locked
the password was still verified and the response said which guess was right, and the
attempt was not counted, so guessing during the window was unlimited. The lock
bounded nothing. Now a failed attempt during a lock is counted, and past
`LOCKOUT_NOTICE_CEILING` (twice the threshold) every attempt gets the generic
message whatever the password. The window is still never extended, so "locks the
account for 15 minutes" stays literally true, and the ceiling is high enough that a
user who locks themselves out and then types the right password still learns why
they cannot get in.

This **amends D-25**, which said a failed attempt during a lock "neither moves the
counter nor extends the window". The counter now moves; only the window is fixed.
It also departs from the proposal's own `handleLoginAttempt()` pseudocode, which
verifies the password inside the locked branch and counts nothing. The pseudocode's
hole is real, and the question "what stops me guessing ten thousand passwords?" has
to have an answer at the demonstration.

The password is still verified on every path, including the ones that no longer
report the result. Skipping the hash once the ceiling is passed would have made
those responses measurably faster than the response for an unknown address, which
would have rebuilt the enumeration oracle that D-25 removed.

**2. Anyone could lock every account in the organisation.** Registration's mandatory
409 identifies a registered address, five login requests then lock it, and repeating
every fifteen minutes holds it locked. Administrators lock on the same terms, there
is no release route, no password reset and no Django admin, so the only remedy was a
shell on the host. Both anonymous endpoints now carry a scoped rate limit
(`AUTHENTICATION_THROTTLE_RATE`, 20 requests per minute per client address), which
is generous for a person typing a password and useless for this attack. The counters
live in Django's default per-process cache, so under several worker processes the
effective rate is that many times higher and a restart clears it. Adequate for the
alpha; a shared cache is the fix if the limit ever has to be exact. D-24 noted
the absence of throttling while the lockout was inert; enforcement turned that
residue into a live denial-of-service primitive, which is a change in what can be
demonstrated rather than production hardening.

**3. Two administrators could race each other to zero.** The guard checked only
self-demotion, so A demoting B while B demoted A touched different rows, both
committed, and no administrator remained, with `manage_roles` held by that role
alone (D-14) and no way back through the product. The transaction now takes a row
lock over the whole administrator set before reading it and refuses any change that
would empty it. That is FR-05's stated purpose, "preventing accidental lockout of
the last administrator", rather than only its letter.

**4. The locked-account notice promised a release that does not exist.** It read "An
Administrator can release it." FR-03 defines that route and FR-03 is out of the M6
gate, so the text was false in this build. It now says the account is temporarily
locked and to try again later, which is true and discloses no more.

**5. The client enabled submit for a password the server refuses.** The length rule
counted UTF-16 code units while the server counts code points, so an emoji password
passed the form and was rejected server-side. It now counts code points, and the
module's claim that it only ever errs the safe way is corrected.

**Recorded, not fixed: a lock does not end an existing session.** Nothing on the
session path reads `locked_until`, and the model has no `is_active` flag, so an
administrator cannot revoke anyone's access by any route the product exposes. Role
changes take effect on the next request, but a session can only be ended by its
owner. That is a fair question against FR-04 "session management" and the honest
answer is that ending sessions is not in the M6 scope.

**Also confirmed clean by the same review:** a locked account's 401 is byte-identical
to the response for an unregistered address, headers included, which is the case that
matters because the 403 is by design the one distinguishable outcome;
the counter and window cannot be set by a caller; no path authenticates except the
login view; no mass assignment through the role change; and the two 403 bodies,
though different, are only ever visible to someone who already holds the permission.

## D-27  NO_ANSWER_MESSAGE wording — "This question cannot be answered from the available knowledge base."  2026-09-14
**The PROVISIONAL marker is removed: the proposal never specifies this string.**
The constants table defines it only as "Fixed text"; the pseudocode references
the name; UC-06's "No relevant information could be found" is prefaced with
"something like". There was nothing to wait for.
The previous wording, "No answer could be found in the material you have access
to", disclosed the permission boundary. FR-11 Front-End: "the interface gives
no indication that withheld content exists", and FR-11 Validation returns this
same message where the scope resolves to no accessible content "rather than an
error disclosing that restricted material exists". The wording now follows
FR-12's own clause — states plainly it cannot answer from the available
knowledge base, no speculation, no hint that scoping exists.

## D-28 · Document status vocabulary: the proposal's six values

**Status:** Settled by the user · **Date:** 2026-09-21 · **Supersedes:** `docs/schema-v1.md` §3's `DOCUMENT_STATUS_VALUES`

**Decision.** `DOCUMENT_STATUS_VALUES` is the proposal's own set, from its §7.0
configuration table:

```python
DOCUMENT_STATUS_VALUES = ("Processing", "Extraction failed", "Insufficient content",
                          "Indexing failed", "Partially indexed", "Indexed")
```

**Rationale (as given).** The same principle as D-25: the FR text wins over the
contract compiled before the proposal arrived. Schema v1 named five values —
`Uploaded`, `Extracting`, `Indexed`, `Insufficient content`, `Processing failed` —
written from the requirement summaries, before
`Project_8-proposal_complete_V4.5.docx` reached this machine on 2026-09-13. The
proposal's §7.7 `embedAndStoreChunks()` and §7.8 `ingestAndIndexDocument()` set
`Indexing failed` and `Partially indexed` directly, and schema v1's set cannot
express a document whose chunks partly embedded: it would have to call that document
`Indexed` and lose the fact, or `Processing failed` and lose the chunks that worked.

**Mapping from the superseded set.**

| Schema v1 | Proposal §7.0 |
|---|---|
| `Uploaded`, `Extracting` | `Processing` (one in-flight state, since ingestion is synchronous) |
| `Processing failed` | `Extraction failed` or `Indexing failed`, according to which step failed |
| `Insufficient content`, `Indexed` | unchanged |
| — | `Partially indexed` (new) |

**Consequences.**

- `apps/core/constants.py` and `docs/schema-v1.md` §3 are corrected together.
- Lands as migration `documents 0006`, the schema v2 migration D-18 places at the
  start of Stage 3. There are no rows to migrate: no document has been ingested.
- `DEFAULT_DOCUMENT_STATUS` becomes `Processing`, which is what §7.8 message 13
  writes when the record is created, before extraction begins.
- **`Partially indexed` is a terminal status, not a half-written record.** It is
  committed inside the one NFR-21 transaction, and only where a chunk was abandoned
  after `MAXIMUM_EMBED_ATTEMPTS` attempts (D-19). It does not weaken CLAUDE.md
  invariant 9: an *unexpected* failure part-way through ingestion still rolls the
  whole transaction back and leaves nothing. The distinction is between an outcome
  the pipeline decided and recorded, and a crash.
- `MEETING_STATUS_VALUES` is untouched. The proposal's Meetings table defines no
  status column at all, only FR-09's CRUD line "Meetings (Create, Read, Update
  status)", so schema v1's three values are an invention with nothing to contradict.

## D-29 · visible_to_roles at ingestion

**Status:** Settled by the user · **Date:** 2026-09-21

**Decision.** The FR-08 upload request and the FR-09 transcript request each accept
an optional `visible_to_roles` list, validated against `ROLE_NAMES`.

- Omitted: both roles. A document nobody thought about is visible to everybody.
- Present but empty: `400`. An empty list means "visible to nobody", which is not a
  thing anyone means to ask for, and FR-11 would filter it out of every search
  silently.
- A list excluding the uploader's own role: `403`. Uploading into a scope you cannot
  read is how content is lost.

Chunks are stamped from the source row inside the item-4 transaction (D-17).

**Rationale (as given).** Neither FR-08 nor FR-09 mentions the column; FR-11 filters
on it. Whatever Stage 3 writes at ingestion is what Stage 4 retrieval filters against
and what the M6 demonstration shows, so it cannot stay open past the upload endpoint.
Defaulting to both roles means an omitted field never accidentally hides content,
while an uploader who does set the field gives FR-11 something real to scope against
in Stage 4 without a separate administration screen.

**Consequences.**

- **The chunk row is what FR-11 filters on**, so FR-15's visibility edit in Stage 5
  MUST re-stamp every chunk of that source in the same transaction, or retrieval
  keeps enforcing the stale scope. That cascade is D-17's model-level guarantee and
  has its own test; this entry is the reminder that Stage 5 is where it is first
  exercised for real.
- Role names are denormalised into document, meeting and chunk rows, so renaming a
  role breaks the filter (D-11's known limitation, now reaching three tables).

## D-30 · FR-08's contribute permission is role-level

**Status:** Settled by the user · **Date:** 2026-09-21

**Decision.** A `contribute_content` permission is seeded in an accounts migration
and held by **both** Employee and Administrator. The FR-08 upload endpoint and the
FR-09 transcript endpoint carry it in their `permission_classes`, so the `403`
precedes the signature, size and title checks exactly as §7.2 `validateUpload()`
orders them. The permission name lives in `apps/core/constants.py`.

`knowledgeArea` is dropped from the check. Schema v1 models no knowledge area, so
the check is role-level rather than per-area.

**Rationale (as given).** §7.2's first line is
`hasContributePermission(user.userId, file.knowledgeArea)` returning `403`, and its
comment says why it is first: "it is the cheapest rejection, and the user's role may
have changed during a transfer of up to 50 MB". The repository seeds one permission,
`manage_roles` (D-14), so without this the requirement's first server-side check
would simply be absent. Per-area scoping would need a new table, seeding and an
administration surface, and is out of the M6 gate.

**Consequences.**

- A test constructs a role **without** the permission and asserts `403` on both
  endpoints, so the gate is proven rather than assumed.
- Both new endpoints need an Employee test and an Administrator test for the
  dual-role matrix (`CLAUDE.md` §8 item 2).
- Because both roles hold it, the permission refuses nobody in the shipped seed. It
  is enforcement machinery with its own test, not a demonstrable restriction; say
  that plainly rather than presenting it as access control that does something.

## D-31 · A token is a whitespace-delimited word

**Status:** Settled by the user · **Date:** 2026-09-21

**Decision.** `length_in_tokens()` splits on whitespace. It is one function, used by
both `split_into_overlapping_chunks()` and the insufficient-content check, so the two
definitions cannot drift. `CHUNK_SIZE` (500) and `CHUNK_OVERLAP` (50) are unchanged.

`MINIMUM_CONTENT_LENGTH` becomes **50 tokens**. This is a unit change: the constant
previously read 200 *characters*.

**Rationale (as given).** §7.5 and §7.8 both count in tokens (`lengthInTokens`), and
no tokeniser is in the stack. The proposal says "approximately 500 tokens"
throughout, and embed-gemma's 2048-token ceiling leaves ample headroom for
whitespace words undercounting real subword tokens by the usual factor of about 1.3.
`tiktoken` was rejected: it is OpenAI's BPE, not gemma's SentencePiece, so a new
pinned dependency would buy precision against the wrong tokeniser. The floor is set
permissively because FR-09 transcripts and short memos are legitimate content; §7.0
marks the value "To be tuned", so there was never a number to wait for.

**Consequences.**

- `apps/core/constants.py` and `docs/schema-v1.md` are updated together, and the
  constant's PROVISIONAL marker is removed — like D-27, there is nothing pending.
- Chunk text is cut on the original string's own whitespace spans, so a stored chunk
  is a verbatim substring of the extracted text, newlines and all, rather than a
  space-joined reconstruction. FR-12 shows the passage to a reader, so it must be
  the passage.


## D-32 · FR-08's retry re-runs ingestion on the stored original

**Status:** Settled by the user · **Date:** 2026-09-21

**The problem.** FR-08's Front-End clause requires that "if extraction fails, a
'Processing failed. Please try again' action is shown". The action was built in Stage
3 item 7 and could not succeed. Ingestion commits the document row on every 422 path,
so that the source survives a failed step (`CLAUDE.md` invariant 8, NFR-20), and that
row carries the `content_hash`. Re-sending the same bytes therefore met §7.2's
duplicate check and was answered `409`.

**The proposal's own flaw, recorded as the reason for the departure below.** FR-08
ties the retry to extraction failing. But a scanned, image-only PDF has no text
layer, and re-submitting identical bytes to the same parser fails identically, every
time, forever. "Please try again" can only ever help where the failure was
*transient* — an embedding provider that was down, which is `Indexing failed`. The
requirement asks for a control whose label is wrong for the case it names. Rather
than implement a button that cannot work, or drop a clause the gate is scored on,
both are addressed:

**Decision, three parts.**

1. **A failed ingestion reserves no duplicate slot.** On every 422 outcome —
   `Extraction failed`, `Insufficient content`, `Indexing failed` — the row is
   committed with `content_hash` set to NULL. The column is nullable and Postgres
   permits many NULLs under a unique constraint (schema v2, `documents 0006`), so
   re-sending the same bytes is an ordinary fresh upload rather than a `409`. A
   successful reprocess restores the hash, so a document that reaches `Indexed` is
   protected by the duplicate check exactly as one indexed on the first attempt is.

2. **The retry re-runs ingestion against the stored original, and does not re-POST
   the file.** `POST /api/documents/{doc_id}/reprocess` re-opens the file already
   under `MEDIA_ROOT` — invariant 8 has kept it — and runs extraction, chunking and
   embedding again, replacing any `ExtractedContent` and `ContentChunks` for that
   document in one transaction. Chosen over a re-upload because a re-upload creates a
   second row per attempt: three retries would leave three near-identical entries in
   FR-15's repository list, and the user would have to find the file on disk again to
   retry at all. One document, one row, however many attempts it took.

3. **The retry's wording differs by status**, because the honest message differs:

   | Status | Action shown | Text |
   |---|---|---|
   | `Indexing failed` | Retry | "Processing failed. Please try again." — the failure was transient and a retry may well work |
   | `Extraction failed` | Retry, as FR-08 requires | names what would actually change the outcome: a text-based or OCR'd copy of the file |
   | `Insufficient content` | Retry | says the file holds too little text to index, so a retry of the same file will not change it |

   FR-08's action is present in every case the clause names. Only its text stops
   promising something the same bytes cannot deliver.

**Consequences.**

- The reprocess route is protected by `contribute_content` (D-30) and scoped by
  `visible_to_roles`; a document outside the caller's scope is `404`, not `403`
  (`CLAUDE.md` invariant 1). It needs an Employee test and an Administrator test like
  every other protected endpoint.
- Reprocessing a document that is already `Indexed` is `409`. Re-indexing healthy
  content is FR-15's business, not a retry's.
- Restoring the hash on success can collide, if the same file was uploaded and
  indexed successfully while this one sat failed. That is a `409` on the reprocess,
  which is the truthful answer: an indexed copy now exists.
- `docs/api-contract.md` gains the route, and the `422` that was missing from the
  `POST /api/documents` row although the implementation and the prose both had it.


## D-33 · Stage 3 requirements audit: what is deferred, and what is conceded

**Status:** Recorded · **Date:** 2026-09-21

The requirements audit of FR-08 and FR-09 returned **INCOMPLETE** on 2026-09-21. Two
findings were defects and are fixed in the same commit as this entry. The rest are
recorded here, because the auditor's point about the first of them applies to all
three: *nothing in the repository recorded that these clauses had been considered and
set aside, which is how they turn into a surprise at the gate.*

**Fixed, not recorded.** The §7.2 rejection order was claimed in a comment and not
implemented — the serializer validated the whole body before the signature and size
checks, so a blank title on a disguised binary was answered 400 where §7.2 fixes 415.
No test pinned it because every test varied one condition at a time. The view now
reads the file part and checks signature and size before the serializer runs, and
four tests combine conditions to pin the order. The `disguised_utf8.pdf` NUL-rule gap
was the same shape and is fixed in `0951ea1`.

### 1. FR-08's classification hand-off is deferred with FR-10

**The clause.** FR-08 Business logic (classification): "on successful extraction the
document is passed to FR-10 for classification. A failure of classification marks the
document unclassified but never prevents it reaching indexed status". §7.8 step 4
calls `classifyAndTagDocument()` and §7.8 line 100 returns `classification` in the
201 payload.

**Status: unmet, and it stays unmet.** There is no classification call in
`apps/ingestion/`, the 201 body carries no `classification` key, and no
`Unclassified` state exists.

**Why.** FR-10 is SHOULD and sits in NIT3004, outside the twelve MUST-HAVEs of the M6
gate (`CLAUDE.md` §2). `MAXIMUM_CLASSIFY_ATTEMPTS` is already named in
`apps/core/constants.py` so the retry policy is uniform when FR-10 is built, but
nothing uses it and nothing should before then. Building it now is the exact trade
`CLAUDE.md` §2 warns against: depth inside a requirement bought at the cost of
breadth across the twelve.

**What is owed.** Not code. A sentence in the demonstration script: FR-08's
classification hand-off is deferred with FR-10, which is NIT3004 work. When FR-10 is
built, §7.8 step 4 goes between `ExtractedContent` and chunking in
`ingest_and_index_document()`, and it must be unable to fail the document — a
classification failure marks it unclassified and never revokes indexed status
(`CLAUDE.md` invariant 8).

### 2. FR-09 returns a 422 its Responses clause does not enumerate

**The clause.** FR-09 Responses: "201 Created with the meeting ID; 400 Bad Request
for missing fields or insufficient content." Two codes, and no more.

**What is built.** `apps/ingestion/meetings.py` answers **422** when every chunk fails
to embed: the transcript is stored, the record carries `Processing failed`, and the
caller is told it is not searchable.

**Why the departure.** The alternative is to answer 201 for a transcript that is not
searchable, which is the one thing a caller must not be told. `CLAUDE.md` invariant 8
requires the transcript survive the failed AI step, so the record must exist; FR-09
simply has no code for "stored but not indexable" because its Responses clause does
not contemplate an embedding provider being down. FR-08's 422 covers the identical
condition, so the same code is used rather than a new convention.

**Conceded:** this is a code FR-09 does not name. It is in `docs/api-contract.md`
marked *convention*, and the front end handles it. Say so plainly if asked rather
than presenting FR-09's Responses clause as fully met.

### 3. The 409 duplicate check is a cross-scope existence oracle

**The conflict.** §7.2 specifies an unqualified duplicate check: "IF
findByContentHash(contentHash) EXISTS THEN RETURN FAILURE WITH response(409)". The
check in `apps/api/views.py` is global, as written. But `CLAUDE.md` §6 invariant 1
forbids disclosing the existence of out-of-scope material "not by a result count, a
total, or an error message". An Employee who happens to hold the same bytes as an
Administrator-only document learns that document exists.

**Decision: leave the behaviour, record the conflict.** Scoping the duplicate check
to the caller's `visible_to_roles` would let two copies of one file exist in the
knowledge base, which is the thing §7.2 exists to prevent, and duplicate passages in
retrieval are a worse outcome at the gate than a narrow oracle. The oracle also
requires the attacker to already hold the exact bytes, which is a much weaker
disclosure than a search result or a count.

Note what this does *not* undo: `DocumentSerializer` still withholds `content_hash`
from every response, so a caller cannot probe for a document by asking about a hash —
only by possessing the file itself.

**Also recorded, as statements to make rather than work to do:**

- An Employee cannot record meeting attendees through the interface, because the
  attendee picker reads `GET /api/users`, which is Administrator-only (FR-05). The
  API accepts attendees from either role; only the control is missing. FR-09's
  Front-End clause is therefore partial for an Employee.
- FR-08's retry action exists only in the upload screen's in-session queue. A
  document left at `Indexing failed` and revisited after a page reload has no route
  back to `POST /api/documents/{id}/reprocess`, although the endpoint works and is
  tested. One button in the repository row closes it.
- There is still no front-end test runner, so every Front-End clause above is graded
  by reading code. Stage 3 shipped four more screens against that gap.
