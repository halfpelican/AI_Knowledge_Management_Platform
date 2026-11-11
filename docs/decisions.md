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
- **A decision that claims coverage names what it does not cover.** If an entry says
  something is closed, enforced, covered or tested, it lists the paths it covers and
  the paths it does not, as a list rather than as prose. Every instance in the table
  below described the case in front of its author rather than the class it belonged
  to. Write the boundary, not just the fix.
- **Count nothing you can list.** This is the sharper statement of the same defect,
  reached on 27 September 2026. Every instance found so far is prose that *counts*, or
  names a member *by reference*, where it could have enumerated: "four entries",
  "nineteen clauses", "two of the three paths", "both", "three statuses", "nine of
  eleven", "the sixth instance", "the only FR IDs in any subject are", "the two rows
  above", "nothing in this branch's history names". Each asserts a fact about a set it
  does not list, and the next addition to the set falsifies it — repeatedly in the same
  commit that wrote the sentence. **Text that enumerates its members cannot go stale by
  miscounting.** So name them; do not count them. A commit range, an explicit list, a
  table row, a `git` hash: each is durable where a number or a position is not.
  **To record another instance, add a row below. There is deliberately no total to
  increment, and no ordinals — a row is identified by where it is, not by its number.**

  Entries that have been true where they were read and false where they were used:

  | Where | The claim |
  |---|---|
  | D-17, and `CLAUDE.md` invariant 2 | the visibility cascade was written as a model-level guarantee with its own test, and for thirteen days was neither |
  | D-45 | which inputs the sanitiser exempts |
  | D-47 | which ORM write paths carry the cascade |
  | D-49 | which archive members the decompression bound covers |
  | D-48 | the sentence about rows the re-scope leaves untouched |
  | D-51 | how many follow-up paths the status could honour |
  | `PROVENANCE_REMOVED_MESSAGE` | promised "an answer from the current material" on the paths that leave no material — a failed reprocess and FR-15's deletion |
  | D-59 | "nothing in this branch's history names FR-11, FR-12 or FR-13", written from a reading of subject lines, in a commit whose own subject is `fix(FR-11/FR-12/FR-13)` |
  | this rule, in `9508442..e81c6e6` | said "Four entries" in every commit of `9508442..52ff2b7`, then "Seven" in `e81c6e6`, the commit that introduced the D-59 instance it did not count |
  | this rule, until `403087f` | "the last introduced by the very commit that corrected the one before it" — `116a422` introduced it and touches no decision entry; `4400b7b`, two commits later, corrected the previous one |
  | this rule, until `403087f` | "Four audits have each found one", set immediately beneath a list of seven |
  | `apps/core/constants.py` | called the `PROVENANCE_REMOVED_MESSAGE` instance "the sixth" while the same commit's subject called it "the seventh" |
  | `frontend/src/utils/documentStatus.js` | "Three statuses are refused it" over a list of two, in the commit that corrected the same docstring's "Two" |
  | `docs/stage-4-clause-audit.md` | "one row below the two that had just been corrected" — the re-audit corrected rows 9, 14, 22 and FR-11's Database row, none of them in that table |
  | D-60, in `403087f` | "It returned six instances in that one commit" over a list of seven, then "All six are fixed" and "five of the six" — the last naming a subset it never identifies |
  | D-60, in `403087f` | "Five passes have now run", "the four before it", "A sixth pass" — counts and ordinals over audit passes listed nowhere, falsified by the next pass to run |
  | D-60, in `403087f` | "D-59 names the nine subjects … and the three messages", and "the two D-59 sentences above" — counts of lists held in another entry, and a position |
  | this table, in `403087f` | rows keyed "until the fifth pass", and "this list's last entry" — ordinals and a position, in the table whose rule forbids them; the last was falsified by the next row added |
  | this table, in `403087f` | "for the eleven commits in which it was being enforced … the commit that made it eight", and "the two paths that leave no material" — counts where a range, a hash and a list existed |
  | D-59, in `403087f` | "The other nine name a requirement in the body", and D-57 "found three departures" — counts over sets listed elsewhere or not at all |
  | `frontend/src/pages/Ask.jsx`, in `403087f` | "the four paths enumerated at" `apps/core/constants.py` — a count of a list held in another file |
  | D-52, and `M6-BUILD-PROMPT.md` item 2a | the download link "is built" and its storage path "depends on D-18" — the link was never built, and migration 0006 had closed the storage question on 21 September; and extracted text "is `ContentChunk.chunk_text`", while `ExtractedContent` held it whole |

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
| D-34 | A staff directory endpoint, separate from FR-05's user list, so any role may name attendees | Settled | 2026-09-21 |
| D-35 | No external AI spend; demonstration runs on one machine | Settled | 2026-09-22 |
| D-36 | FastFlowLM pinned to v0.9.39; `check_flm.py` asserts embedding determinism | Settled | 2026-09-22 |
| D-37 | RELEVANCE_THRESHOLD lowered to 0.30; no threshold separates answerable from unanswerable | Settled | 2026-09-22 |
| D-38 | EmbeddingGemma's task prefixes adopted; kept on correctness, not on the measurement | Settled by the user | 2026-09-23 |
| D-39 | A worked example is training data in its content as well as its identifiers | Settled by the user | 2026-09-24 |
| D-40 | Retrieval is unstable at the threshold; generation determinism unestablished | Open — recorded, not resolved | 2026-09-24 |
| D-41 | FR-12's keyword search path, missing from the Stage 4 brief, built as item 8a | Settled by the user | 2026-09-24 |
| D-42 | FR-13 passes prior questions only, folded into the question argument | Settled by the user | 2026-09-23 |
| D-43 | A conversation's title is optional on create, derived from its first question | Settled here, by the agent that built the endpoints | 2026-09-24 |
| D-44 | The Sources panel lists every item consulted, with its passages nested under it | Settled here, by the agent that built the endpoints | 2026-09-24 |
| D-45 | FR-12's "input is sanitised before use": not a sanitiser, with one exception that is | Settled by the user | 2026-09-25 |
| D-46 | `GET /api/documents/{id}`, so a citation can link to its source | Settled by the user | 2026-09-25 |
| D-47 | The visibility cascade is a save() override and a manager, not a signal | Settled | 2026-09-25 |
| D-48 | A reopened thread is re-scoped on read and its statements renumbered | Settled by the user | 2026-09-25 |
| D-49 | Stage 4 security review: what closed, what deferred, what stands conceded | Settled by the user | 2026-09-25 |
| D-50 | An oversized archive member is a 413; the bomb class is closed for OOXML only | Settled by the user | 2026-09-26 |
| D-51 | A seventh document status: "Too large to index" | Settled by the user | 2026-09-26 |
| D-52 | FR-15's detail view shows metadata and a download link, not extracted content | **Superseded by D-63** | 2026-09-27 |
| D-53 | Fail closed on a source/chunk visibility disagreement; one helper, not two predicates | Settled · implemented 2026-10-05, Stage 5 item 1 | 2026-09-27 |
| D-54 | The NUL-byte rejection is fixed at the instance; the class reopens with FR-15 | **Settled by D-65** (2026-10-05) | 2026-09-27 |
| D-55 | `rejected_count` on QueryLog — numbering a column that shipped without one | Settled retroactively | 2026-09-27 |
| D-56 | Partial matches are a reply field derived before the threshold | Settled retroactively · **one gap open**: no relevance floor | 2026-09-27 |
| D-57 | Three Stage 4 commit-discipline departures | Recorded | 2026-09-27 |
| D-58 | An unused conversation can outlive a session; closing it needs a contract addition | **Open** | 2026-09-27 |
| D-59 | Most finishing-pass subjects omit the FR ID; the entry's first draft was an instance of the rule | Recorded | 2026-09-27 |
| D-60 | Stage 4 closes with §8 condition 4 declined and condition 5 failed; both recorded | Recorded · **4 declined, 5 failed** | 2026-09-28 |
| D-61 | The Stage 4 closing audit: INCOMPLETE, recorded verbatim; its findings are carried to Stage 5 unfixed | Recorded · **findings open against Stage 5** | 2026-09-28 |
| D-62 | A front-end test runner lands; the interface is no longer accepted as untested; §8 condition 2 names pytest and the front-end suite | Settled by the user | 2026-09-28 |
| D-63 | FR-15's detail view shows extracted content after all; D-52's reasons for cutting it were false | Settled by the user | 2026-09-28 |
| D-64 | The M6 alpha is hosted on the NPU laptop and reached on that laptop, over loopback; it replaces the proposal's GCP deployment for the alpha only | Settled by the user · scoped to M6 | 2026-10-05 |
| D-65 | Every query parameter passes a DRF serializer: ChoiceField for fixed vocabularies, shape-only for department and tag, an inclusive date range; the 400 is a convention | Settled by the user · settles D-54 | 2026-10-05 |
| D-66 | Administrator generalises Employee in scope as well as in permissions: scope is overlap with EFFECTIVE_ROLES, in the item 1 helpers only | Settled by the user | 2026-10-05 |
| D-67 | `AnswerCitation.chunk` is SET_NULL and `chunk_uuid` keeps the cited identifier; no passage text is stored, and a NULL-chunk citation is removed for every reader | Settled by the user, in the Stage 5 brief, item 1a · supersedes D-12 for this column and D-48's "not before M6" · closes D-61's gap 5 | 2026-10-05 |
| D-68 | FR-14's recent questions are the requester's own QueryLog rows, and the question only | Settled by the user, in the Stage 5 brief, item 3 | 2026-10-06 |
| D-69 | FR-14's KnowledgeGaps read is deferred with FR-19 (NIT3004, Objective 06) | Settled by the user, in the Stage 5 brief, item 3 | 2026-10-06 |
| D-70 | FR-14: department narrows documents only, labelled; the indexed total counts "Indexed" by type; each type filters on its own date | Settled by the user | 2026-10-06 |
| D-71 | FR-12 keyword search collapses whitespace on both sides before matching, so a phrase that wraps a line is found | Settled by the user | 2026-10-06 |
| D-72 | FR-15 browse: a separate endpoint sharing the list's scoped query; Department from the column, a deliberate departure; 204 only when a filter matches nothing | Settled by the user | 2026-10-06 |
| D-73 | FR-15 deletion: manage_documents for Administrators (accounts 0005), scoped-first 404 then 403, chunks, tags and document in one transaction, file on commit, 204 | Settled by the user | 2026-10-06 |
| D-74 | The demonstration corpus is tagged from the manifest by an idempotent script, applied_by="user", against kmp (corrected 2026-11-01: the alpha's database is kmp_demo_20261101, D-88) | Settled by the user | 2026-10-06 |
| D-75 | FR-15 download: a scoped route returning the original as an attachment, typed by its signature and named with the signature's extension; a missing file is the same 404; errors.log | Settled by the user | 2026-10-13 |
| D-76 | Every /api/ response is marked never-cache by one middleware (add_never_cache_headers); nothing outside /api/ | Settled by the user | 2026-10-13 |

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

**Status:** Settled, one bullet amended by D-26, its front-end testing question closed by D-62 · **Date:** 2026-09-13 · **Supersedes:** parts of D-23 and D-24

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

> **2 November 2026: the lockout is FR-02's, as this entry ruled, and the record now says so
> everywhere** (the user's decision 1).
>
> - **What FR-02 and FR-03 each own.** FR-02's own text locks an account for 15 minutes after five
>   failures, and gives a locked account a 403 (`apps/core/constants.py:286-289` quotes it). FR-03
>   adds only the warning, the countdown and the administrator release.
> - **`CLAUDE.md:185` is corrected,** with the user's approval, from "(FR-03, NIT3004)" to
>   "(FR-02 enforces, D-25; FR-03 adds the interface, NIT3004)".
> - **The 1 November walk left out an FR-02 clause:** the lock, its 403 and the locked-account
>   message. `docs/demonstration-script.md` called the lockout FR-03, and `docs/stage-5-item-8-walk.md`
>   followed it. Item 10 found this (its H2, D-90).
> - **It is shown in an extra, recorded walk on the alpha,** with a newly registered throwaway
>   account. That is step 3 of the user's post-M6 order. The server side is already tested
>   (`test_login.py`), and the front-end message is step 6's (D-94).

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

**Dated note, 11 November 2026: the 403 came first among the answers, but not before the body
was read (D-124).** This entry says the permission "precedes the signature, size and title checks
exactly as §7.2 `validateUpload()` orders them". Its rationale quotes §7.2's reason: "it is the
cheapest rejection".

- **The order of the answers was true. The cheapness was not.** Until D-124, every signed-in
  session holding the CSRF cookie had its whole request body parsed by DRF's CSRF check while it
  authenticated, before this 403. A multipart upload was parsed whole, with its files spooled to
  temporary files. A JSON transcript was read and parsed if it was within Django's 2.5 MiB
  `DATA_UPLOAD_MAX_MEMORY_SIZE`, and refused unread if it was larger. The security review of
  `feat/FR-09-recording-transcription` found it on 11 November 2026.
- **D-124 makes the reason true.** The CSRF check reads its token from the header only, so nothing
  reads the body before this 403, and Waitress's `--max-request-body-size` caps what is received.
- **`DocumentsView`'s docstring** cited this entry for "before the body is parsed at all". It is
  corrected, with the same date.

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

**Also recorded. Two of these three were statements to make when this entry was
written on 2026-09-21; both were built the same day and are struck through here
rather than deleted, so the record of what was found still reads straight.**

- ~~An Employee cannot record meeting attendees through the interface, because the
  attendee picker reads `GET /api/users`, which is Administrator-only (FR-05). The
  API accepts attendees from either role; only the control is missing. FR-09's
  Front-End clause is therefore partial for an Employee.~~
  **Closed.** The gap was server-side and it was an absence, not a wrong rule: the
  API never restricted attendee *association*, only the user *listing* the picker
  needed. `GET /api/users/directory` supplies it and FR-05's list is untouched. See
  **D-34**, which also states what the directory discloses.
- ~~FR-08's retry action exists only in the upload screen's in-session queue. A
  document left at `Indexing failed` and revisited after a page reload has no route
  back to `POST /api/documents/{id}/reprocess`, although the endpoint works and is
  tested. One button in the repository row closes it.~~
  **Closed.** The repository row carries the action for any status that is not
  `Indexed`, refreshed from the response rather than assumed, and D-32's
  status-specific wording moved to `src/utils/documentStatus.js` so both screens
  read one copy of it.
- **Still open.** There is still no front-end test runner, so every Front-End clause
  above is graded by reading code. Stage 3 shipped five screens against that gap, and
  the two fixes above added an untested retry control and an untested attendee
  picker to it. This is the one of the three that did not get smaller.


## D-34 · A staff directory, separate from FR-05's user list

**Status:** Settled · **Date:** 2026-09-21 · **Closes:** Stage 3 audit finding 4

**The finding.** FR-09's Front-End clause has any user associate a transcript "with a
meeting title, date, and attendees". In practice only an Administrator could: the
interface populated its attendee picker from `GET /api/users`, which is
Administrator-only, so an Employee was shown a note instead of a control. The M6 gate
is demonstrated from both roles, and an Employee demonstrating FR-09 could not show
the clause at all.

**Which side was wrong.** The server never restricted the *association*.
`POST /api/meetings` accepts attendees from any holder of `contribute_content`, which
is both roles (D-30), and a test now proves an Employee can name attendees
end-to-end. What it restricted was the only user *listing*. Removing the interface
gate alone would therefore not have produced a 403 on the transcript — it would have
produced one on the directory read that fills the picker, on every page load.

So the gap was server-side, and it was an absence rather than a wrong rule.

**Decision.** `GET /api/users/directory`, readable by any signed-in session, returning
`id`, `name` and `email` and nothing else. FR-05's `GET /api/users` is untouched and
stays Administrator-only.

**Rationale.** The obvious shortcut — relax `GET /api/users` to `IsAuthenticated` —
would have handed every Employee the role every colleague holds, plus their account
timestamps, in order to satisfy a requirement that needs only a name. That is a fix
worse than the finding it closes. `GET /api/users` also *is* FR-05's list: it drives
role management, the contract marks it Administrator-only, and
`test_users_is_403_for_an_employee` pins that. Two endpoints with two audiences is
the boring shape.

Three fields were chosen, not four. `role` is deliberately absent: naming an attendee
needs a person, not their standing in the organisation, and who holds which role
stays FR-05's business.

**What this discloses, stated rather than glossed.** Every signed-in user can now read
the name and address of every registered user. That is what a staff directory is, and
naming a colleague as an attendee is not possible without one. It is worth saying out
loud at the demonstration rather than leaving for someone to notice: the platform
assumes an organisation whose staff list is not itself confidential. Nothing about
roles, account state or history goes with it, and a test asserts the response carries
exactly the three keys.

**Consequences.**

- One more protected endpoint in the dual-role matrix: 13, still 100%.
- `MeetingAttendees` remains a participation record and never an access control
  (D-16, `CLAUDE.md` invariant 3). The end-to-end test has an Employee name an
  Administrator as an attendee and asserts nobody's access changed.
- If the organisation ever needs a confidential staff list, this endpoint is the one
  place to scope, and FR-09's picker is its only consumer.

## D-35 · No external AI spend; the demonstration runs on one machine

**Status:** Settled · **Date:** 2026-09-22 · **Closes:** the API key and spend cap
question left open by the team plan of 1 September 2026

**Decision.** The platform runs on FastFlowLM only. No Anthropic or Voyage keys are
purchased and no API spend is incurred. The team has no budget, and no member funds
it personally.

**Rationale.** The question of whose API keys and who pays has been open since
1 September. Leaving it open is itself a risk: Stage 4 cannot be built without an
embedding and generation provider, and the decision would otherwise be made by
default at the worst moment. FLM on the NPU is free, local, and already the
documented default for development, testing and demonstration
(`docs/ai-provider.md`). An unfunded student project should not be financed out of a
student's own pocket, and the constraint is defensible when it is chosen and
recorded rather than discovered.

**Consequences.** FLM requires an XDNA2 NPU, which one machine in the team has.
All end-to-end development, the Stage 4 baseline, and the November demonstration
therefore run on that machine. This is a single point of failure and is accepted
knowingly.

The `anthropic` provider path stays implemented and stub-tested, so that switching
providers is a configuration change rather than a rewrite should funding ever
exist. Note that the two produce different vectors — 768-dimension `embed-gemma`
against Voyage's own — so a switch is a full re-index event, not a toggle
(`docs/ai-provider.md` section 4).

Mitigations, all of which cost nothing:

- The Stage 4 corpus is ingested by script, so the index can be rebuilt on any
  machine in one command rather than by hand.
- A screen recording of the complete flow is made once Stage 4 works, as
  demonstration-day insurance. Assessors generally accept a recording where the
  live system is unavailable; they do not accept a description.
- The AMD driver version the NPU depends on is recorded, after a
  `VIDEO_SCHEDULER_INTERNAL_ERROR` bugcheck under FLM load on 21 September 2026.

**Dated note, 10 November 2026: superseded by D-113 and D-114.** The premise, "The team has no
budget", no longer holds. The user's Max plan includes $100 of Claude API credits each billing
cycle, so the `anthropic` provider is funded and brought into use (D-113). The demonstration is no
longer tied to one machine: M8 can be hosted on any device with the platform in place (D-114). What
this entry records about the past stays true where it was written.

## D-36 · FastFlowLM pinned to v0.9.39, and what the health check has to prove

**Status:** Settled · **Date:** 2026-09-22 · **Closes:** the implicit assumption that
the current FastFlowLM release is the right one to run

**Decision.** FastFlowLM is pinned to **v0.9.39**. Upgrading is a deliberate act that
requires `scripts/check_flm.py` to pass on the new version first, and a re-index if
any embedding changes. The version is recorded in `README.md` and
`docs/ai-provider.md` alongside the AMD driver version (D-35).

**Why.** FastFlowLM's `/v1/embeddings` endpoint has been broken since v1.0.4
(ROCm/FastFlowLM issue #732, open at the time of writing). It returns vectors of the
correct shape and magnitude that are statistically uncorrelated with their input. The
weights on disk are identical across the affected versions; only the serving path is
wrong. The project had been running v1.0.6.

This was not caught by inspection. It was caught on 22 September when
`scripts/citation_harness.py` ran for the first time and every retrieval result was
incoherent. The measurements that identified the cause:

| Measured on v1.0.6 | Cosine |
|---|---|
| The same string embedded twice in one batch | 0.4833 |
| Two consecutive chunks of one document, sharing 50 tokens of literal text | 0.0992 |
| Two unrelated documents | 0.6398 |

Three identical `curl` calls returned three different vectors. An embedding function
that does not return the same vector for the same input is not an embedding function.

After downgrading to v0.9.39, the same checks return cosine **1.0000** for a repeated
input within a batch, **1.0000** across separate calls, and **0.1299** between two
unrelated sentences. Three embeddings take **1.0 second** against **95.6 seconds** on
the broken build — the latency was itself a symptom nobody read as one.

**The real finding is about the check, not the version.** `check_flm.py` had passed
every day for two weeks. Its embeddings check asserted that the vectors were non-zero
and that two different inputs produced different vectors. Random noise satisfies both.
The check was written to confirm the endpoint responds, and it was read as confirming
the endpoint works.

It now asserts the properties that actually define an embedding, at
`DETERMINISM_TOLERANCE = 0.999`:

1. The same input embedded twice **in one batch** returns the same vector.
2. The same input embedded again in a **separate call** returns the same vector.
3. Two unrelated inputs score **lower** than a repeated one.

The order of work was deliberate and is worth stating: the strengthened check was
written and run against the known-broken v1.0.6 **before** the downgrade, where it
failed at cosine 0.0939. Only then was the version changed. A check that has never
been observed to fail is not evidence; it is a check that passed once on an unknown
system. The subsequent pass on v0.9.39 means something because the failure came first.

**Consequences.**

- The stored index built before 22 September was noise. `manage.py reindex` rebuilt
  it against the working provider and is the supported way to do so again.
- FLM upgrades are blocked pending issue #732. When it closes, the upgrade path is:
  run `check_flm.py` on the new version, and if it passes, re-index — the vectors are
  not guaranteed comparable across versions even when both are correct.
- The generalised lesson applies beyond FLM: an invariant test that asserts a value is
  *present and non-identical* asserts almost nothing. Where the project tests an
  external provider, the test asserts a property the provider could fail, and is run
  against a failing case before it is trusted.
- `docs/flm-baseline.md` records the three rates that this pin makes meaningful. Every
  number in it is invalid on any other FLM version.

## D-37 · RELEVANCE_THRESHOLD is 0.30, and why no value would be the right one

**Status:** Settled · **Date:** 2026-09-22 · **Closes:** the placeholder value carried
since Stage 1 · **Provisional:** re-measured against a real corpus

**Erratum, 23 September 2026.** This record first gave the corpus as 9 chunks. It is
**6** — four documents and one meeting, of which only the Employee Handbook splits,
into two. The count was read back from `ContentChunk`, and `--scores-only` was re-run
against those rows: it reproduced the distribution below to the three decimal places
the table prints, so the numbers were measured on these 6 chunks and only the count
was wrong. The chunk rows were all written at 11:22 on 22 September and nothing wrote
a chunk between then and this decision, which is the evidence that no other corpus
was ever involved. The 0.30 value and every argument here stand, and `TOP_K = 25`
binds even less at 6 than at 9.

**Decision.** `RELEVANCE_THRESHOLD` in `apps/core/constants.py` moves from 0.5 to
**0.30**.

**The measurement.** Top-score distribution over the placeholder corpus, all 64
questions in `scripts/citation_questions.json`, after the reindex on the pinned FLM
build (D-36):

| Kind | n | min | median | max |
|---|---|---|---|---|
| Ordinary (answerable) | 48 | 0.219 | 0.390 | 0.661 |
| Scoped (Employee asking an Administrator-only question) | 8 | 0.179 | 0.252 | 0.286 |
| No-answer | 8 | 0.180 | 0.474 | 0.535 |

0.5 admits 10 of the 48 answerable questions. It was never measured; it was a round
number chosen before any retrieval existed, and it discards most of the corpus by
construction. At 0.5 the empty-answer-where-available rate was 81.2%. At 0.30 it is
14.6%.

**The finding that matters more than the number.** No threshold separates answerable
from unanswerable on this corpus. The no-answer questions reach 0.535, overlapping
the top third of the genuinely answerable ones. Admitting 41 of 48 answerable
questions costs 5 of 16 unanswerable ones reaching generation; excluding every
unanswerable question requires a floor of 0.54, which keeps 7 of the 48 real answers.
There is no setting that buys both.

This is not a tuning failure. It is what cosine similarity over an embedding model
measures — topical relatedness, not whether a passage contains the answer. Q15 in the
question set was written to make exactly that point: it shares vocabulary with the
Administrator-only postmortem without being answerable from anything in the corpus.

**Rationale.** If the threshold cannot decide answerable from unanswerable, then
invariant 7(b) must, and the baseline run shows it does. Four no-answer questions
cleared 0.30, reached generation, and came back with an empty statement list. Path B
is therefore load-bearing rather than a leftover branch, and the threshold's remaining
job shrinks to cutting obvious noise cheaply — one candidate filter before an NPU
call, not an accuracy mechanism.

A threshold with that job should sit low enough not to throw away real answers, since
generation catches what gets through. 0.30 sits below the answerable median by a clear
margin and above the floor of the distribution, and the cost of the questions it
wrongly admits is a generation call, not a wrong answer.

**Consequences.**

- **Invariant 7(b) is now demonstrated, not assumed.** The Stage 4 test suite tests it
  directly rather than treating it as the branch that happens to be left over, and the
  two no-answer reason codes must stay distinguishable in the query log — a rising
  rate of (b) is the only signal that generation is degrading.
- **The value is provisional and the comment in `constants.py` says so.** It is
  measured against 6 chunks. At that size `TOP_K = 25` never binds, so the threshold
  is currently performing all the selection in the pipeline. It is re-measured when a
  real corpus arrives.
- **It is re-measured again if the EmbeddingGemma task prefixes are adopted.** The
  model expects `task: search result | query: …` for queries and `title: … | text: …`
  for documents; the project sends raw text. Query-to-chunk scores (0.18–0.66) sitting
  below chunk-to-chunk scores (mean 0.488) is the signature of that omission, and
  correcting it moves the whole distribution.
- **Every rate in `docs/flm-baseline.md` is specific to this threshold and this FLM
  build.** Changing either invalidates the document, which is why both are recorded
  decisions rather than configuration someone adjusts in passing.

**What this decision does not establish.** The scoped questions top out at 0.286
because the role filter removed the Administrator-only content from the candidate set
before ranking. That is correct behaviour and it is invariant 1 working, but it means
the scoped result measures the filter's output, not the filter under test. FR-11 is
evidenced at Stage 4 item 11, not here.
## D-38 · EmbeddingGemma's task prefixes are adopted, and the reason is not the measurement

**Status:** Settled by the user · **Date:** 2026-09-23 · **Stage:** 4 item 2a ·
**Re-index event:** yes · **Supersedes:** the "we do not send the task prefixes"
caveat in `docs/flm-baseline.md`

**Decision.** `apps/ai/prefixes.py` applies EmbeddingGemma's two documented task
prefixes — `task: search result | query: {content}` for a query and
`title: {title} | text: {content}` for a document, with `title: none` where a source
has none. The corpus was re-indexed on the pinned FLM build (D-36). The prefixes are
kept **because the model is documented to expect them**, not because adopting them
was measured to improve anything.

**The hypothesis that motivated the change is disproved.** `docs/flm-baseline.md`
reasoned that the absent prefixes likely explained why query-to-chunk scores
(0.18–0.66) sat below the chunk-to-chunk mean of 0.488 — query and document being
embedded into one space rather than the two the model relates. After adopting both
prefixes and rebuilding every vector, the answerable median moved from 0.3892 to
**0.3937: +0.0045**, and the query band moved from 0.18–0.66 to 0.22–0.69. Had the
two-spaces account been the main cause, the query band would have moved substantially
toward the chunk-to-chunk range. It did not. Whatever depresses query-to-chunk scores
relative to chunk-to-chunk scores is still unidentified, and the baseline no longer
offers a candidate for it. This is the finding of item 2a, not a footnote to it.

**Rationale (as given).** On 6 chunks and 64 questions every delta is inside noise, so
the measurement cannot adjudicate the change in either direction — and a measurement
that cannot adjudicate is not a reason to keep the code or to remove it. What settles
it is that the model is documented to expect these prefixes and was previously not
being given them. *"We use the model as documented"* survives a question at the
demonstration; *"we measured no difference on six chunks, so we kept the undocumented
usage"* does not.

**What the numbers did show.**

| | before | after |
|---|---|---|
| answerable admitted at 0.30 | 41/48 (85.4%) | **44/48 (91.7%)** |
| unanswerable admitted at 0.30 | 5/16 (31.3%) | 6/16 (37.5%) |
| answerable median / max | 0.3892 / 0.6607 | 0.3937 / 0.6856 |
| unanswerable ceiling | 0.5348 | 0.5067 |
| answerable max − unanswerable ceiling | 0.126 | **0.179** |

Three more answerable questions admitted for one more unanswerable one: a **3:1
recall-to-wasted-call trade**. An unanswerable question clearing the threshold is a
wasted NPU call that no-answer path B catches. It is deliberately not called a leak
anywhere in this record: a leak is out-of-scope content reaching the prompt, which the
role filter prevents before ranking and which the harness asserts at zero on every
question (invariant 1). One is a cost; the other would be a failure of the thing this
project is most often asked about, and the vocabulary should not blur them.

That trade should improve the worst of the three baseline rates.
Empty-answer-where-available was 14.6% (7 of 48), and all seven were questions the
threshold excluded rather than ones generation declined; four are now excluded, which
projects **14.6% → about 8.3% (4/48), down by a third.** A projection, not a
measurement: generation's behaviour on the three newly admitted questions is untested,
and Stage 4 item 6 re-runs the full harness against the real pipeline to settle it.

**Consequences.**

- **`docs/flm-baseline.md`'s three rates now describe a superseded index**, and the
  document says so at the top rather than only in the new dated section. Its
  "Tuning RELEVANCE_THRESHOLD" table is void by its own closing sentence, which named
  a change of embedding prefixes as one of the three things that would void it. The
  table is left as written rather than edited in place, because it is the evidence
  D-37 was decided on and rewriting it would leave that decision citing numbers nobody
  measured.
- **D-37's re-measurement trigger has fired and is discharged, not deferred.** D-37
  recorded that the threshold "is re-measured again if the EmbeddingGemma task
  prefixes are adopted". The `--scores-only` sweep in the new dated section is that
  re-measurement, and it does not move the value: 0.30 still admits 91.7% of
  answerable questions and still clears the scoped ceiling. `RELEVANCE_THRESHOLD` is
  **not** re-tuned in Stage 4, and would not be worth re-tuning against 6 chunks in
  any case. The re-measure that matters is **Stage 5 item 3**, the end-to-end
  integration pass over a real corpus.
- **D-37's central finding stands.** 0.5067 still sits well above the answerable
  median of 0.3937; the first threshold admitting no unanswerable question is 0.52,
  which keeps 10 of 48 real answers. No threshold separates answerable from
  unanswerable on this corpus, so invariant 7(b) is still doing the work the threshold
  cannot.
- **A thin margin worth watching, and not a regression.** The scoped ceiling rose
  0.2856 → 0.2947, so headroom under the 0.30 threshold fell from 0.0144 to 0.0053.
  Reading that as a regression would repeat the error D-37 corrected: a scoped
  question's top score measures the best of what the role filter *left*, not the
  filter. Nothing depends on the headroom — the role filter, never the threshold, is
  what keeps scoped content out, and a scoped question crossing 0.30 reaches
  generation over permitted passages only. It is a retrieval-quality signal to watch
  as the corpus grows, not a security one.
- **The prefix never enters `chunk_text`.** The prefixed string goes to the provider;
  the stored chunk stays the verbatim substring `apps/ingestion/chunking.py` produced,
  because a prefix in that column would be read back out into answers, citations and
  snippets (FR-12). Asserted as two separate assertions — what was sent, and what was
  stored — in `apps/ingestion/tests/test_embedding.py`.
- **Dispatch is on the embedding model's name, not on `AI_PROVIDER`**, so a future FLM
  build serving some other embedding model inherits nothing. The provider is consulted
  only to learn which model name is in play: reading `FLM_EMBED_MODEL` unconditionally
  would have applied an EmbeddingGemma convention to Voyage in every environment that
  left the FLM default in place, which is every environment. A test covers Voyage with
  the FLM default present.
- **`scripts/citation_harness.py` now embeds its questions through
  `apps.retrieval.query_embedding.embed_question()`** rather than a raw
  `service.embed()` of its own. Without that the harness would have measured raw
  queries against a prefixed index — the worst of both configurations, and a
  measurement of something the shipped system will never do. It is the same reason
  item 5 makes the harness import the prompt and the schema instead of defining them:
  a second copy of a code path stops describing the first one the day they diverge.
- Switching the provider remains a full re-index event, and adopting or dropping a
  prefix now is too.

## D-39 · The worked example is training data for the response, in its content as well as its identifiers

**Status:** Settled by the user · **Date:** 2026-09-24 · **Stage:** 4 item 6 ·
**Supersedes:** the item-0 conclusion that UUID-shaping the example identifiers was the
whole fix

**Decision.** `SYSTEM_PROMPT` in `apps/ai/prompting.py` gets a new worked example, and
both halves of the cause are removed: the example moves to an **alien domain**
(houseplant care — no policy, procedure, approval, money, staff, meeting or IT content),
and it carries **one identifier, which its own reply cites**. A second example
demonstrating the empty-array reply reuses the same passage rather than introducing a
second identifier, so the prompt contains nothing uncited to borrow.

**The finding.** The first live run of the shipped pipeline measured a fabricated-
identifier rate of **6.8% (3 of 44)**, up from the prototype's 2.4% (1 of 42). All three
had one cause and it was ours:

- **q30** and **q31**, both purchase-approval questions, cited
  `8b5d04e2-1a7f-4c93-b620-de91f3805c47`. That is the worked example's **second**
  identifier — the one the example's own reply does *not* cite. Both statements were
  factually correct, drawn from the corpus's real AUD approval-threshold table, and
  both were discarded by `verifyCitations()` because the citation was invented.
- **q21** cited `5. Offboarding`, a section heading lifted from a passage body.

The example's subject matter — "Purchase orders above $10,000 require two approvals" —
collided directly with the corpus's real approval-threshold table. The model was asked a
purchase-approval question, answered it correctly from the corpus, and reached into the
example for the citation.

**Rationale (as given).** Item 0 found that 9 of 10 fabrications were the example's own
short identifiers, gave the examples UUID shapes, and the rate fell from 23.8% to 2.4%.
That fix was right but the conclusion drawn from it was too narrow: it treated identifier
*shape* as the mechanism. The mechanism is that **a worked example is training data for
the response, in its identifiers and in its content**, and the second recurrence is what
shows the first conclusion was incomplete. Deferring the fix to Stage 5 was rejected:
the cause was identified and specific, Stage 5 has seven items including the integration
pass, the accessibility pass, deployment and two audits by 31 October, and shipping a
documented rate that describes a system we already intend to change is not a saving.

**The re-measurement, bounded to one run.** Fabricated identifiers went **3 of 44 to 0
of 38**, and no identifier was invented in the 36 further question-runs of the stability
measurement. The three statements verification had been correctly discarding are now
correctly cited. **This does not establish that fabrication is solved** — it is 0 of 38
on one run of a 6-chunk corpus, at an n D-37 already says cannot adjudicate small
differences. One fix, one re-measure, deliberately: iterating the prompt against this
question set at n=3 would be tuning noise.

**Consequences.**

- **The lesson is now an assertion, not a comment.**
  `test_no_identifier_appears_in_the_prompt_without_its_example_reply_citing_it` checks
  `shown == cited` over whatever identifiers the prompt contains, so a future
  three-passage example fails in under a second instead of in a six-minute live run. A
  subject-matter guard asserts the example text contains none of the corpus's own
  vocabulary (purchase, approval, invoice, procurement, policy, leave, onboarding,
  offboarding, employee, staff, manager, meeting, incident, account, password, AUD, `$`).
- **The block comment above `SYSTEM_PROMPT` records both recurrences**, not just the
  first. Recording only the first would again suggest UUID-shaping was the whole fix,
  which is the conclusion that permitted the second.
- **Verification did its job in the before-run and that is the point worth keeping.**
  Three fabricated citations reached verification and none reached an answer. The
  measurable cost was two correct answers withheld — which is the trade invariant 5
  exists to make, made in the right direction.
- **Every rate in `docs/flm-baseline.md` before 23 September describes the old prompt.**
  The before and after runs are both recorded there, because the before-run is the only
  evidence for the mechanism.

## D-40 · Retrieval is unstable at the threshold, and FLM's stability is not established

**Status:** Open — recorded, not resolved · **Date:** 2026-09-24 · **Stage:** 4 item 6 ·
**Owner:** unassigned · **Re-measure at:** Stage 5 item 3, over a real corpus

**The observation.** Running the shipped prompt three times, unchanged, over the same 12
questions in three separate processes, two questions changed answer between runs — q04
answered in 1 run of 3, q06 in 2 of 3, swapping with each other. The other ten were
stable in count *and* in character-identical statement text.

**The mechanism, as far as it is established.** Both flips were retrieval, not
generation. A chunk sitting **0.0003 to 0.0014 above `RELEVANCE_THRESHOLD`** crossed the
floor in opposite directions on the two questions, changing how many passages reached the
prompt. Across 14 distinct (question, supplied-passage-set) groups, identical input gave
identical output every time, so **the generator is not implicated on this evidence.**

Two facts make it matter:

1. **About 6% of admitted passages sit on the floor.** 5 of 86 admitted passages are
   within 0.005 of 0.30, three within 0.0017. q04 and q06 are two of those five.
2. **Query embeddings vary by roughly 1e-4 on some questions and not others**, which is
   what moves a passage across the floor. Reproduced independently: q04's top score was
   0.358032 on one invocation and 0.358459 on two others.

**What is NOT established, and is deliberately left open rather than guessed.** The
trigger for the embedding variation is unknown. Two plausible candidates were tested and
ruled out: embedding the same questions in three separate processes gave bit-identical
vectors (elementwise difference 0.000e+00), and interleaving a chat completion between
two embeddings inside one process also gave bit-identical vectors. Every observation so
far shows the first run of a sequence differing and later runs agreeing, but what
distinguishes that first run is not known.

**`scripts/check_flm.py` does not catch this, and that is a gap rather than a fault.** It
requires cosine ≥ 0.999 between repeated embeddings; the variation here is around 1e-4,
four orders of magnitude inside that tolerance. The check was built for the v1.0.4 bug
where a string scored 0.09 against itself (D-36) and it still does that job. It simply
does not measure at the resolution retrieval turns out to need at a threshold boundary.

**Why this is recorded before it causes a visible failure.** Generation determinism on
the NPU was assumed and never measured until 24 September, exactly as embedding
determinism was assumed until D-36 — where the assumption turned out to be load-bearing
and wrong, and an index of pure noise looked entirely plausible for four days. If FLM
output is not stable run to run, **every rate in `docs/flm-baseline.md` is one draw from
a distribution rather than a measurement, including the first-attempt conformance of 100%
from which NFR-19's retry policy is reasoned.** Nothing observed so far says that is the
case for generation. The point is that it has not been shown either way, and the wording
in the baseline says "no variance observed across 3 runs on 12 questions" rather than
anything stronger.

**Consequences.**

- **`RELEVANCE_THRESHOLD` is NOT re-tuned on this.** D-37 and D-38 both say the value is
  not tuned against a 6-chunk corpus, and moving a floor to dodge two questions that sit
  on it would be fitting a constant to noise. The instability is a property of where the
  corpus happens to land, not evidence about where the floor belongs.
- **A demonstration can show the same question answering differently on two runs.** That
  is worth knowing before 1 November rather than discovering it live. It is not a
  correctness failure — both outcomes are honest, and the no-answer response is a
  legitimate reply — but it will be asked about.
- **It changes nothing about the permission boundary.** Out-of-scope chunks were 0 in
  every run, before the fix, after it, and in all three stability runs. Instability at
  the floor moves passages the asking role may already read.
- **Any future claim of determinism needs a measurement, not an absence of failures.**
  That is the D-36 lesson restated, and it is why this entry stays open rather than
  closing with "appears stable".

## D-41 · FR-12's keyword search path was missing from the Stage 4 brief, and is built as item 8a

**Status:** Settled by the user · **Date:** 2026-09-24 · **Stage:** 4, item 8a ·
**Effect:** Stage 4's commit points go from thirteen to **fourteen**

**The gap.** FR-12 is two paths. Its Server-End clause and section 7.10
(`generateGroundedAnswer`) describe the question-and-answer path, which Stage 4 items 1
to 9 build. Its **Front-End** clause also requires "a search field available from every
page, returning results grouped by type (Documents and Meetings) with a count per
group", where each result shows "its title, the matching passage as a snippet, its
department, and its date".

Nothing in the Stage 4 brief's numbered items builds that. Item 10 names the
"Search / Ask / Sources front end", which assumes a backend the items never create.
Section 7.10 says why it is absent from the pseudocode — "the keyword search path in
the same requirement returns matching items grouped by type and is not reproduced here,
as it is a filtered read rather than an algorithm" — and that exclusion from the
*algorithm* section appears to have been read, when the stage was planned, as an
exclusion from the *stage*. `SearchLog` has existed unwritten since migration v1 as the
visible symptom.

Found at item 7, while checking what would still be unbuilt when the stage's own
definition of done was assessed.

**Decision.** Build it, in this stage, as **item 8a** — after query logging and before
the front end. The endpoint is item 8a; the search field on every page stays part of
item 10. Separate commit points, so the stage's shape stays legible against its brief.

**Rationale (as given).** The deciding reason is not that FR-12 is a MUST-HAVE, though
it is. It is that **items 11 and 12 are the scoping test and the security review, and a
search endpoint is a second route through the permission boundary.** Its grouped counts
are the likeliest count-disclosure in the system — invariant 1 names result counts and
totals explicitly, and a search that returns "4 documents" where one is
Administrator-only discloses the existence of restricted material without returning a
single restricted row. Reviewing the permission boundary before that route exists would
review half the surface, and the review is the artefact the M6 demonstration is
defended with.

Deferring it to Stage 5 beside FR-15's filtered browsing was considered and rejected on
schedule: Stage 5 carries seven items to 31 October, including the end-to-end
integration pass, the accessibility pass, the alpha deployment and two audits.

**Consequences.**

- **It stays a filtered read.** 7.10 calling it "a filtered read rather than an
  algorithm" is the proposal licensing the boring implementation: case-insensitive
  substring match, a snippet windowed around the hit, a stable non-relevance ordering,
  no ranking, no scoring, no embedding and no NPU call. A second ranked path would be a
  second thing to keep correct and a second place for the permission filter to be got
  wrong.
- **Counts come from the post-filter set**, and `SearchLog.result_count` records that
  same post-filter number. The test that proves it is an Employee and an Administrator
  searching one term and receiving different counts, with the Employee's count equal to
  what the Employee can see.
- **The new endpoint joins the dual-role matrix.** Objective 01 requires 100% of
  protected endpoints exercised from both roles, and the matrix fails a full run below
  that — so an endpoint outside it is the failure, and covering both roles is the work
  rather than a cost of doing it.
- **`SearchLog` stops being a dead table**, and item 8's argument for why `QueryLog`
  needs no `result_count` column gains its other half: a keyword search stores no
  identifiers, so there an integer is the only record available.
- **The stage's commit count no longer matches its brief**, deliberately. Thirteen items
  become fourteen commit points. This entry is what an auditor reading the repository
  should find instead of a discrepancy.

## D-42 · FR-13 passes prior QUESTIONS only, folded into the question argument

**Status:** Settled by the user · **Date:** 2026-09-23 · **Stage:** 4 item 9 ·
**Unmeasured:** yes — see the caveat, which is the most important part of this entry

**The tension.** FR-13's Server-End clause says the assistant "passes prior turns
alongside the new question so that pronouns and abbreviated references resolve
correctly". CLAUDE.md's grounding rule and the Stage 4 brief both say the generation
prompt contains only the retrieved passages. Both cannot be followed literally.

**Decision, in the clauses the user set.**

1. **Prior questions only. Never prior answers.** No model-generated text re-enters a
   prompt.
2. **No change to `generate_statements`.** `docs/ai-provider.md` section 1 fixes it at
   `(question, passages)` plus the `on_attempt` observer (D-38's entry covers that
   observer). Prior questions are folded into the `question` argument as a composed
   string. A `history=` parameter was proposed and rejected: "three operations,
   deliberately" is about not adding classification and summarisation, but a parameter
   that changes what the model is asked is a protocol change nothing else asked for.
3. **Two composed forms, both internal to `answer_question`.** A plain join of the prior
   questions and the new one is what gets embedded, so the labelling text does not dilute
   the query vector. A labelled block is what reaches the prompt.
4. **The block declares itself.** It states that the prior questions are context only,
   that they are NOT passages, that they carry no `chunk_id`, and that nothing in them may
   be cited. It lands after the passages, which is where `build_generation_messages`
   already puts the question. The generalisation from D-39 applies directly: anything in a
   prompt is a candidate for being cited, and a new block of text is a new candidate.
5. **`MAXIMUM_CONVERSATION_TURNS = 3`**, in `apps/core/constants.py`. FR-13 requires
   context "truncated to a maximum number of prior turns to control prompt size and
   cost"; 3 is chosen against a 4B model and a `MAXIMUM_CONTEXT_TOKENS` ceiling of 4000
   that the passages also draw on.
6. **History is read with a `user` predicate as well as a `conversation` one.** A
   conversation id is a UUID a caller supplies. Filtered on both, a foreign id yields no
   history rather than somebody else's questions — no history, not an error. The view
   additionally answers 404 for a conversation that is not the caller's, because without
   that the turn's `QueryLog` row would be written against another user's thread and
   surface there as a turn count that is not theirs.

**THE CAVEAT, which is the point of recording this as a decision.** Every rate in
`docs/flm-baseline.md` — 100% schema conformance, 100% first-attempt conformance, 0%
fabricated identifiers after D-39 — was measured on a prompt containing **passages plus
one question**. A multi-turn prompt carries a block those runs never contained, and
**`scripts/citation_harness.py` cannot cover it**: the harness asks single questions, so
item 6's re-run says nothing about this prompt. **The multi-turn prompt is unmeasured.**

**Measured on 25 September 2026 as item 9a, and the risk recorded here was the wrong
risk.** This entry first framed the danger as the 503: conformance degrading until the
service appears to fail on the second turn of a conversation. The arithmetic does not
support that. A 503 needs `MAXIMUM_GENERATION_ATTEMPTS` *consecutive* non-conforming
replies, which at 90% conformance is roughly one turn in a thousand.

**The exposure is NFR-08 performance, not the 503.** Every retry is another NPU generation
call, so a drop in first-attempt conformance is invisible in correctness and loud in p90
latency — and Objective 03 measures that p90 on 23 October. First-attempt conformance is
therefore the number to watch, not overall conformance, which hides exactly that cost.

The measurement itself: the existing 64 questions with a fixed three-question block
prepended to the generation prompt and **retrieval held constant**, so the block is the only
variable. First-attempt conformance stayed at 100% (50/50) with zero retries, no identifier
was fabricated (0 of 42), out-of-scope stayed 0, and no statement's content traced to the
block rather than to a passage. The defensible claim is no degradation. `docs/flm-baseline.md`
has the run, its limits, and the three mis-citations it incidentally exposed.

**FR-13 end to end is still unmeasured**, because holding retrieval constant deliberately
excluded the composed join that FR-13 embeds — the half that changes which passages are
retrieved, and on D-40's evidence the half likelier to move answers. That needs a
question-then-follow-up set, which does not exist.

**Consequences.**

- **The design's cost is real and conceded.** A follow-up referring into the previous
  *answer* — "what about the second one?" after an answer that listed three — does not
  resolve, because the list was in the answer and answers are not passed. FR-13's "follow-up
  questions need not restate the subject" holds for subject nouns and not for references
  into an answer's wording. Worth saying in the demonstration script rather than
  discovering live.
- **The history block is a citable surface until proven otherwise**, so a statement citing
  an identifier that appeared only in a prior question must be rejected by
  `verifyCitations`. That has its own test, arranged so the identifier belongs to a chunk
  the asking role may not read — it carries invariant 1 as well as D-39.
- **History markers are `- `, not `1.`** One of item 6's three fabrications was
  `5. Offboarding`, a numbered heading returned as a `chunk_id`. A numbered history list
  would add tokens of exactly that shape.
- **The scope is re-resolved every turn**, which `answer_question` already did per call, so
  FR-13's "re-evaluated on every turn rather than cached from the first" is structural
  rather than remembered. A test proves it across two turns of one conversation: a role
  demoted between turns does not inherit the first turn's access.
- **Every logged turn counts toward the history, answered or not.** A user whose question
  was not answered rephrases it, so filtering to answered rows would drop exactly the
  turns a follow-up is most likely to be shortening.
- `QueryLog.question` stores the bare question, never the composed string, or every
  follow-up row would contain its predecessors and the log would stop being readable.

> **2 November 2026: the 1 November screen contradicts this entry's boundary** (the user's
> decision 2, D-91).
>
> - **The boundary.** Follow-ups that need not restate a subject noun resolve; only references
>   into an answer do not. D-86 decision 2 predicted the same: only t09, whose referent is in the
>   answer, should fail.
> - **What the screen supports.** In the three threads where the first turn was correct on every
>   trial and the follow-up expected an answer, the follow-up was not correct on any trial: t01,
>   t04, and t06 asked by the Administrator. The referent is named in the first question in all
>   three. This is the stored statements rescored with the frozen rule (version 2), with nothing
>   re-run. The table is in D-91.
> - **What it does not support:**
>   - a count over all seven question-referent threads, because four are confounded by a first
>     turn that was itself not correct;
>   - a cause, because the model was not separated from the prompt.
> - **The screen is not D-86's measurement.** It was an informal look, on `kmp_demo_screen` with
>   two extra documents. The measured reason comes from step 5's run: the nine threads with
>   history, cold and spelled out, then the HTTP check.
> - **FR-13 is partial at the gate** (D-91).

## D-43 · A conversation's title is optional on create and derived from its first question

**Status:** Settled here, by the agent that built the endpoints · **Date:** 2026-09-24 ·
**Stage:** 4 item 9, API half · **Effect:** `POST /api/conversations` accepts no title;
`POST /api/ask` performs FR-13's `Update`

**The gap.** `Conversations.title` is a `CharField` with no blank allowed (schema v1, and
the proposal's own Conversations table gives the example `"Leave policy questions"`). FR-13
requires that "previous conversations are listed and can be reopened", so the list has to be
legible — a thread a user cannot tell apart in a list is a failed requirement. But FR-13's
interface never asks for a title: it has "the active thread can be cleared to begin a new
topic", which is a user clearing the pane and typing a question. Nothing in the proposal says
where the string comes from.

**Decision.** `title` is optional on `POST /api/conversations`.

- Supplied and non-blank: used as sent, trimmed, bounded by the column (255). A title over
  that is `400`, not a silent truncation.
- Omitted or blank: the thread is created as **"New conversation"**, and the **first turn**
  through `POST /api/ask` replaces that with the turn's question, truncated to 255 with
  Django's `Truncator`. The turn itself stores the question in full; the truncation is a
  display name.
- The rename happens only while **both** conditions hold — the placeholder still stands and
  no `QueryLog` row exists for the thread. So a title the user chose is never overwritten,
  and a thread already in use is never renamed under them.

**Rationale.** Requiring a title would add a field FR-13's interface does not have, and
would put a naming dialogue in front of the first question of every conversation. Deriving
it from the first question costs nothing and produces exactly what a user would have typed:
the question is the topic. The window in which the placeholder is visible is the gap between
creating a thread and asking in it, which in the built interface is one request.

This is also the `Update` in FR-13's `Conversations (Create, Read, Update)`, alongside the
`last_updated_at` the pipeline touches inside the log transaction on every turn. Those two
are the whole of `Update`: **no rename route and no `PATCH` were built**, because FR-13's
interface has no rename control and inventing one would be inventing a requirement. If it is
wanted later it is a `PATCH` on an existing path rather than a new resource.

**Consequences.**

- A thread named from a no-answer turn is named all the same. The turn happened, it is
  logged, and the user will look for it by what they asked.
- A question of nothing but whitespace is long enough to be asked (the length rule counts
  characters) and leaves nothing to name a thread with, so the placeholder stands. A blank
  list entry is the worst case of the problem this decision exists to avoid.
- `name_thread_from` saves with `update_fields=["title"]` only. `last_updated_at` is
  `auto_now`, so it is written only when named, and the pipeline has already set it for that
  turn — naming it here would move the thread's timestamp on after the reply was composed
  from it.

## D-44 · The Sources panel carries every item consulted, with its passages nested under it

**Status:** Settled here, by the agent that built the endpoints · **Date:** 2026-09-24 ·
**Stage:** 4 item 9, API half · **Effect:** the shape of `sources` in a `POST /api/ask` reply

**The question the proposal half-answers.** Section 7.10 step 11 is
`SET sourceList TO resolveSourceDetails(suppliedPassageIds) // title, date`, and FR-12's
Front-End clause says a "Sources panel lists every item consulted with its date". That fixes
*which* items (the supplied passages' items, not the cited ones) and *what* of them (title,
date). It does not say how a citation gets the passage text that the same clause requires it
to expand into: "each citation expands to display the source passage and links to the source
document or meeting".

**Decision.** One list, `sources`, one entry per item consulted in rank order, each carrying
`source_type`, `source_id`, `title`, `date` and `passages` — the supplied passages of that
item, each with its `chunk_id` and text. A statement's `chunk_id` is looked up inside the
entry it belongs to.

**Rationale.** The alternative was two flat lists, `sources` and `passages`, with the client
joining them on `source_id`. Nesting answers "which item did this citation come from" with
the shape of the reply instead of with a join the client has to get right, and no endpoint in
the API returns a chunk, so the text has to travel with the answer that was drawn from it or
the expansion cannot be built at all.

**What this does not do.** It exposes no similarity score — a tuning number the team reads,
and an interface that displayed it would present relevance as a fact about the answer. It
exposes no `file_path` and no `content_hash`, for the two reasons the document object gives.
It resolves **no permission predicate of its own**: every passage reached the reply through
`candidate_chunks`, whose query carries both FR-11 predicates, so the chunk's stamped
`visible_to_roles` already admitted this role and the source row is read for a title and a
date only. A second filter in a second place is two filters that can disagree, and D-17's
re-stamping cascade is what makes the chunk the authoritative record.

**Conceded.** A passage that was consulted but cited by nothing appears in the panel with its
text. That is retrieved corpus text inside the caller's scope rather than a model-generated
statement, so invariant 6 — which is about uncited *statements* — is not engaged; and the
panel's stated purpose is to show what the answer was drawn from. If it proves noisy in the
interface, the fix is client-side collapsing, not a narrower reply, because narrowing it to
cited items only would make the panel misdescribe the retrieval.

## D-45 · FR-12's "input is sanitised before use" is not a sanitiser, with one exception that is

**Status:** Settled by the user · **Date:** 2026-09-25 · **Stage:** 4, items 4 and 10b ·
**Clause:** FR-12 Server-End, Validation

**Decision.** No stripping, escaping or filtering pass is applied to a question or a search
term. The clause is satisfied by the mechanisms that actually protect each path, named
below — **except** for one case where that argument does not hold, which is neutralised in
code and tested.

**Why a general sanitiser is the wrong instrument here.** Each thing a sanitiser would be
protecting against is already handled somewhere it cannot be forgotten:

| Concern | What handles it |
|---|---|
| SQL injection | The question is a bound parameter in every query and is never interpolated. The ORM does this; no call site can opt out |
| Cross-site scripting | React escapes text nodes on render. The question is never inserted as HTML |
| Length and resource abuse | `MINIMUM_QUESTION_LENGTH` / `MAXIMUM_QUESTION_LENGTH`, checked before any provider call (item 4), and `MINIMUM_SEARCH_LENGTH` for search |
| Prompt injection aimed at the model | The grounding constraint plus citation verification. A statement survives only if it carries an identifier from the supplied set, so an instruction in the question cannot manufacture a citable source |

A stripping rule on top of those has no attack left to prevent, and it has a cost: it
silently mangles legitimate questions. A question about a currency amount, a file path, an
SQL keyword or a piece of XML is a question a knowledge platform should answer, and
whitespace is not normalised either, because 7.10 measures the question as given and a
trimming rule is a requirement nobody wrote.

**THE EXCEPTION, which is why "a sanitiser is a no-op" would have been too strong.** The
generation prompt labels each passage `[chunk_id: <uuid>]` in `build_user_prompt`. A
question containing that literal syntax injects a **pseudo-passage into the user's own
prompt** — text that looks to the model exactly like a supplied passage, carrying an
identifier of the asker's choosing.

It is not a security hole, and it is worth being precise about why: `verifyCitations`
checks returned identifiers against the set built from the **retrieval result**, never
against anything parsed out of the prompt, so an identifier smuggled in this way is not in
the supplied set and every statement carrying it is removed. Nor is it a cross-user
disclosure: the injected text is the asker's own.

It is a **demonstration hole**. A question crafted that way can make the model return
statements drawn from text the asker wrote, which verification then strips — producing a
no-answer for a question that looked answerable, or, if the asker also echoes a real
identifier, a statement attributed to a passage that does not support it. Either is an
awkward thing to have happen in front of an examiner, and neither needs a vulnerability to
be embarrassing.

**So the delimiter sequence is neutralised in user-supplied text, and tested.** That is a
targeted transformation of one known-harmful sequence, not a general sanitiser, and the
distinction matters: it can be stated exactly, it cannot mangle an ordinary question, and
its test names the attack it prevents.

**The transformation, recorded because "neutralised" is not specific enough to reproduce.**
The label's square brackets become round ones: a question containing
`[chunk_id: 9f2…]` reaches the prompt as `(chunk_id: 9f2…)`. Chosen over deleting, masking
or substituting a marker for four reasons:

- **Readable.** Every word, digit and space survives in place, so the question reads the
  same to the model and to a human comparing it against the stored original.
- **Cannot change an ordinary question.** At most two characters move, and only where `[` is
  immediately followed by the label and its colon. Prose about `chunk_id`, a quoted
  `chunk_id:` value, and square brackets around anything else all pass through byte for
  byte. Length is preserved exactly and nothing is trimmed.
- **The header shape is what goes.** `SYSTEM_PROMPT` tells the model to copy the identifier
  "exactly as it appears in the passage header", and the header *is* the square-bracketed
  label. Removing the brackets removes the resemblance.
- **Idempotent**, since `(chunk_id:` contains no `[chunk_id:`, which is what makes applying
  it twice harmless.

Two patterns, one sequence: the whole label including its closing bracket, so the output is
balanced rather than `(chunk_id: 9f2…]`; and the same opening where the asker never closed
it, which is still header-shaped. Case and inner spacing are matched loosely and preserved
exactly, because `[CHUNK_ID :` is as header-shaped to a model as the canonical form.

**Applied at three sites, corrected 27 September 2026.** This paragraph said "two" and said
"**Passage text is not transformed**". Item 12a made both false on 26 September, and neither
sentence was revised — the same error D-47 made about `bulk_update`, and the one this file's
header rule now exists to prevent: **wrong in the safe direction**, so a reader believes a
guarantee is absent and has no reason to preserve it.

Written as the rule requires — the paths covered and the path deliberately not:

| Site | Neutralised | Since |
|---|---|---|
| `build_user_prompt`, the question argument | yes | D-45, item 10b |
| `build_conversational_question`, the new question and each prior question | yes — a delimiter smuggled into turn one cannot inject through turn two's history block | D-45, item 10b |
| `build_user_prompt`, **each passage's text** | **yes** | **item 12a**, when the security review found an uploaded document body could forge a passage header |
| `ConversationContext.for_retrieval` | **no, deliberately** | the string is embedded and never prompted; a vector has no delimiters to forge. This exemption was named nowhere before today |

Idempotency is what lets the three passes compose without double-transforming.

**And the exception is no longer the only one.** This entry was written when a question forging
the header was the single case. There are three, and the third cannot be closed by any
transformation:

1. a **question** forging the header — closed;
2. a **document body** forging the header — closed at the prompt boundary by item 12a;
3. a **document body directing the model in prose** — **not closed, and not closable** by
   set-membership verification, because `verify_citations` tests identifiers and a prose
   directive carries none. `apps/ai/prompting.py` states this at length. `contribute_content`
   is held by both roles (D-30), so it is Employee-reachable into every Administrator's answers
   over the same corpus.

The boundary that does hold, and the sentence to use if asked: **the permission scope**, because
it is applied in application code before generation. D-49 records the proof — injection can
misattribute, and it cannot widen.

**An adjacent case this does NOT settle.** A *document* whose own body contains `[chunk_id:`
produces a genuine passage whose text carries the sequence, and passage text is deliberately
left alone. That is prompt injection through ingested content rather than through user
input, which is a different threat with a different owner: the Stage 4 security review
covers it explicitly, and whether ingestion should notice such content is a question for
that pass rather than this decision.

**Consequences.**

- The audit table in `docs/stage-4-clause-audit.md` marks this clause 🔧 rather than ✅ and
  points here. A requirements-auditor reading FR-12 will find a clause with no sanitiser
  behind it, and should find this argument rather than an apparent oversight.
- "Input is sanitised" remains, on the whole, a requirement written for a different
  architecture — one where the question is concatenated into SQL or into HTML. Saying so is
  more useful than implementing a no-op to satisfy the wording.
- If a future prompt gains another structural delimiter, it inherits this problem. The
  neutralisation lives beside the prompt for that reason, so the two are read together.

## D-46 · `GET /api/documents/{id}`, so a citation can link to its source

**Status:** Settled by the user · **Date:** 2026-09-25 · **Stage:** 4, item 10b ·
**Clause:** FR-12 Front-End ("each citation … links to the source document or meeting")

**Decision.** Add `GET /api/documents/{id}`, scoped to the caller's role, answering **404**
for a document that does not exist *and* for one outside the caller's scope. Add a minimal
front-end document route so a citation resolves to its own source rather than to the
repository list.

**Why it was missing.** FR-12 requires a citation to link to its source document or
meeting. `GET /api/meetings/{id}` has existed since Stage 3, so meeting citations already
resolved; documents had no detail endpoint and no route, so item 10 linked them to the
repository list with a label saying to find it there. That satisfies "a link" and not "links
to the source document".

**Rationale (as given).** Two reasons, and the second is the one that fixed the timing.
First, the clause plainly asks for it. Second, **it is another route through the permission
boundary, and items 11 and 12 are the scoping test and the security review** — the same
argument that moved the keyword search path into this stage as item 8a (D-41). A route added
after the review is a route the review never saw.

**404 and never 403.** A 403 distinguishes "exists but you may not see it" from "does not
exist", which is the disclosure invariant 1 forbids by name. The precedent to cite is
**D-33's treatment of the 409 existence oracle** on upload, and the sibling behaviour is
`GET /api/meetings/{id}`, which already answers 404 for a meeting outside the caller's
scope for exactly this reason.

**Consequences.**

- **The endpoint is shared infrastructure, not a duplicate of Stage 5's work.** FR-15
  (Stage 5 item 1) owns document presentation — filtered browsing, metadata, permissioned
  deletion — and will read this endpoint rather than replace it. The front-end route added
  here is deliberately minimal: enough for a citation to reach its source, no more, so that
  FR-15 is building on it rather than around it.
- It joins the dual-role coverage matrix, which fails a full suite run below 100%, so it
  carries an Employee test and an Administrator test. As with D-41, that is the work rather
  than a cost of doing it.
- The response reuses the existing document object, so `file_path` and `content_hash` stay
  out of it for the reasons `GET /api/documents` already excludes them: a path inside
  `MEDIA_ROOT` is of no use to a client and an invitation to construct one, and echoing a
  content hash would let a caller probe whether a document they cannot see has been
  uploaded.
- **The contract entry sits in the Stage 3 FR-08 table, not the Stage 4 section**, with a
  one-sentence cross-reference from the Stage 4 `sources` paragraph. A reader asking what
  the API offers for a document should find all three document routes in one place, and the
  endpoint outlives the clause that prompted it — FR-15 reads it rather than adding its own.
- Unknown and out-of-scope are answered by **one** code path: a single scoped queryset plus
  `get_object_or_404`, so there is no branch that could come to distinguish them. That is
  the same shape `MeetingDetailView` uses, and it is stronger than two branches that return
  the same status today.

## D-47 · The visibility cascade is a save() override and a manager, not a signal

**Status:** Settled · **Date:** 2026-09-25 · **Stage:** 4 item 11a ·
**Closes:** a claim CLAUDE.md invariant 2 made from 12 September and did not keep

**What was wrong.** Invariant 2 stated that changing a source's visibility "re-stamps every
one of its chunks in the same transaction — that cascade is a model-level guarantee, not a
convention, and it has its own test". There was no `save()` override, no signal and no test.
Measured consequence: narrow a document to `[Administrator]`, and `GET /api/documents`
correctly returns `[]` while `POST /api/ask` still answers an Employee **with a citation
from that document**. The row filter and the chunk filter disagreed, and retrieval uses the
chunk filter.

**Latent is not the same as unreachable.** No shipped route mutates `visible_to_roles` after
ingestion, so the API could not trigger it. But the corpus loads by script, `README.md`
documents a `manage.py shell` snippet for direct row edits, and demonstration preparation is
precisely when somebody narrows a document by hand. FR-15 in Stage 5 adds the repository
control that would have made it routine.

**Decision: a `save()` override on `Document` and `Meeting`, plus a `QuerySet` manager for
`update()`.** Not a signal, and invariant 2's own two words decide it:

- *"in the same transaction"* — a `post_save` receiver on a save in autocommit, which is
  every `document.save()` outside an `atomic()` block, runs **after** the source row has
  committed. The phrase would be literally false, and a failing cascade would leave the
  source narrowed and its chunks wide. The override opens the `atomic()` itself.
  `test_a_failed_cascade_rolls_the_sources_own_change_back` patches the cascade to raise and
  asserts the source keeps its old scope.
- *"a model-level guarantee"* — a receiver is connected only if its module is imported, which
  is one `AppConfig` edit away from being silently absent. That is a convention.

`QuerySet.update()` is covered by a manager on both models, because `update()` bypasses
`save()` and every signal and is already used in this codebase for single-column writes. Two
subtleties are tested: affected primary keys are read **before** the UPDATE, so filtering on
the old value still cascades; and the new scope is read back **from the rows**, so a database
expression cascades per row.

**Coverage, corrected on 25 September after measuring it.** This paragraph originally said
`bulk_update` and `bulk_create` were not covered. That was **wrong**, and wrong in the safe
direction, which is worse for maintenance than being wrong the other way: a reader who
believes `bulk_update` is uncovered does not write a test for it. Measured on Django 5.2.17:

| write path | cascades |
|---|---|
| `save()`, `save(update_fields=["visible_to_roles"])` | yes |
| `QuerySet.update()`, including filtered on the column being written | yes |
| expression update (`F()`, `Func`) — and it re-stamps the value the database stored | yes |
| `bulk_update()` | **yes** |
| `update_or_create()` | **yes** |
| `bulk_create(update_conflicts=True, update_fields=["visible_to_roles"])` | **no** |
| raw SQL, `psql` | no |

**`bulk_update` cascades by accident, not by design**, because Django implements it internally
as `self.filter(pk__in=pks).update(**kwargs)` and so inherits the `update()` override. That is
coverage held hostage to a dependency's implementation detail: a Django release reimplementing
it as a single `CASE` statement would make invariant 2 false again **with every existing test
still green** — the same shape as the original defect, true where checked and false where used.

The test that guards it is therefore **behavioural**: it asserts the condition invariant 2
states (every chunk carries its source's scope) over every ORM write path, so it fails on a
Django upgrade rather than on a refactor of the override. The `bulk_create` upsert hole is
pinned by a test asserting it does **not** cascade, named so the gap reads as known rather than
believed closed — an unpinned "not covered" claim is exactly how invariant 2's own falsehood
survived thirteen days.

`manage.py reindex` re-derives the stamp correctly by a different route, because it rebuilds
the chunk.

**Expressed as a condition to restore, not a diff to apply.** One UPDATE saying every chunk
of this source carries this scope, with an `exclude()` guard so a save that did not change
the scope writes zero rows. No change detection and no shadow copy. A
`save(update_fields=[...])` that does not name the column skips the cascade, because the
cascade mirrors what the save wrote and not what the instance holds — which is what keeps
ingestion's frequent status saves cheap.

**Consequences.**

- **The test was written failing and flips green in the implementing commit**, which is the
  D-36 property: a check with a demonstrated failure mode is better evidence than one that
  has only ever passed. It was a `strict` xfail, so leaving it behind was impossible — an
  unexpected pass is a failure.
- No migration. A plain mixin rather than an abstract model, and an `as_manager()` manager,
  change nothing the autodetector records.
- CLAUDE.md invariant 2 now carries a **dated** correction rather than a silent edit. The
  claim stands; the note records that it was untrue for thirteen days and how it was found.

## D-48 · A reopened thread is re-scoped on read, and its statements are renumbered

**Status:** Settled by the user · **Date:** 2026-09-25 · **Stage:** 4 item 11b ·
**Class:** the same bug as D-47, one instance further on

**The leak, framed correctly.** `GET /api/conversations/{id}` was filtered by owner and never
re-scoped, so an Administrator who asked a question answered from Administrator-only
material, was then demoted, and reopened the thread still received it.

It is tempting to record this as "only an identifier leaked, since no route resolves a
`chunk_id` to passage text". **That understates it, and the understatement is the thing worth
recording.** A statement generated from a restricted passage carries that passage's substance
in natural language: the sentence *is* the restricted fact, written out. The identifier is
the lesser half.

**Decision.** Re-scope on read. Stored `chunk_id`s are filtered through
`scoping.scoped_chunks` under the reader's current role, and a statement whose citation is no
longer permitted is dropped. **The same predicate, not a second implementation** — invariant
3's argument is that a second scoping mechanism means two code paths through the one filter
that matters most, and it applies here unchanged.

FR-13's Validation clause already requires that a follow-up "cannot inherit access the user
no longer holds". A thread read is that principle one step on, and every other route in the
system re-resolves the scope per request.

**A turn that loses every statement renders as the existing no-answer state**, reusing what
item 7 built. Not blank, and not a "content withheld" notice or a removed-count: such a
notice is itself an existence disclosure, which invariant 1 forbids. Asserted three ways —
no removal vocabulary in the bytes, no record-only field, and exact key sets.

**Surviving statements are renumbered contiguously**, and this is the part the proposal does
not settle. Rendering the stored positions would show `[1] … [3]`, and **a gap in citation
numbering is itself an indication that something was removed.** Where nothing is dropped the
renumbering is the identity, so an ordinary read is unchanged, and `AnswerCitation.position`
is never rewritten — the mutation is in memory only.

**The stored rows are untouched**, deliberately. `QueryLog` and `AnswerCitation` are FR-19's
record of what was actually answered at the time. Re-scoping is a read concern; rewriting
history to match a role change would destroy the evidence while fixing the disclosure. The
question text and the thread title stay, for the reason D-42 passes prior questions: they are
the user's own words.

> **QUALIFIED, 27 September 2026, and this entry is the fourth instance of the pattern in this
> file's own header rule.** The sentence above is true of the re-scoping path it was written
> about and false of the system. **Two shipped paths destroy `AnswerCitation` rows outright**,
> because `AnswerCitation.chunk` is `on_delete=CASCADE`:
>
> | Path | Reachable by | Effect |
> |---|---|---|
> | `POST /api/documents/{id}/reprocess` | either role — it is gated on `contribute_content`, which D-30 gives to both | deletes the source's chunks, recreates them with fresh UUIDs, and every citation row naming the old ones dies with them |
> | `manage.py reindex` | anyone with a shell; **CLAUDE.md §4 mandates it on any provider or embedding-model change** | the same, for every source in the corpus |
>
> Measured against the live database in a rolled-back transaction: citations 1 → 0, the
> `QueryLog` row survives, `answered` is still `True`, `answer_text` survives, and
> `retrieved_chunk_ids` is left naming rows that no longer exist.
>
> **What this entry covers:** a role narrowing, a source's scope narrowing, and a reader whose
> permissions changed between writing a turn and reading it. Stored rows genuinely are
> untouched on all three.
>
> **What it does not cover:** any operation that deletes a chunk row. Reprocess, re-index, and
> FR-15's permissioned document deletion when it lands.
>
> **Why the original closure was as wide as its instance.** D-12 settled the cascade on
> `AnswerCitations` by reasoning about exactly one case — FR-15's document deletion, where
> "with the chunk gone the citation has nothing to cite" is a fair argument, because the
> material really is gone. Reprocess and re-index delete chunks for material that **still
> exists**: the same text, re-chunked, under new identifiers. Nothing in the repository
> connected D-12's model-layer decision to FR-12's traceability clause or to the FR-13 route
> that reads those rows, and Stage 1's own
> `test_citation_cascades_when_its_chunk_is_deleted` asserted the deletion *as desirable*,
> which is why three stages passed without anyone joining the two.
>
> **Consequences, recorded rather than fixed before M6.** FR-12's traceability clause — "the
> question, the retrieved chunk identifiers, the answer and its verified citations are logged,
> so that any answer can later be traced to the material that produced it" — is satisfied at
> write time and not afterwards. The behaviour is pinned by a test at the FR level (item 1a)
> rather than assumed. The rendering consequence is separated from the re-scoping case in item
> 1c, because a turn whose provenance was destroyed by maintenance is not the same state as a
> turn whose citations this reader may no longer see, and only the second must stay silent.
>
> Changing `on_delete` to `SET_NULL` with a nullable identifier snapshot would make the
> original sentence true. That is a migration and a serializer decision, and it is not being
> made before M6.

**THE CLASS, which is the reason this entry exists as well as the instance.** Derived records
do not carry visibility, and nothing re-derives it. Four instances, three found and one by
inspection:

1. **`ContentChunk`** — stamped at ingestion, never re-stamped when the source changed. Fixed
   as D-47.
2. **A reopened thread** — statements replayed under the role that asked, not the role
   reading. Fixed here.
3. **`QueryLog.answer_text`** — generated under the role held at the time, and it is a stored
   record rather than a response, so it is correct that it is not re-scoped. It becomes a
   disclosure the moment anything renders it: **FR-14's dashboard of recent queries (Stage 5)
   is the next reader**, and it must reuse `ConversationTurnSerializer`'s treatment rather
   than reading the column.
4. **`SearchLog.result_count`** — a post-filter total computed under the role held at the
   time. A demoted user's own search history therefore records counts from a scope they have
   lost. Nothing renders it today.

The pattern to hunt, and the Stage 4 security review is asked to: **any column whose value
was derived under a permission scope, read back later without re-deriving it.**

**The review walked the schema and found NINE, not four-plus-one** (D-49). The five above, plus:

6. **`QueryLog.retrieved_chunk_ids`** — identifiers of passages supplied under the asker's
   scope. `answered` plus `len(retrieved_chunk_ids)` also reconstructs the path A/B distinction,
   which `query_log.py` states explicitly, so any reader leaks that too.
7. **`QueryLog.answered`** — `ConversationTurnSerializer` correctly **re-derives** it as
   `answered AND surviving citations`. A reader that trusts the column reports "answered" for a
   turn whose every statement is now unreadable. FR-14 must reuse that serializer, not the
   column.
8. **`ContentTag` and `Tag`** — the one that was missed by inspection and is next to bite.
   FR-10 derives tags from content; neither table carries `visible_to_roles` and nothing
   re-derives one. A tag list or a facet count built from them discloses the **topics and the
   volume** of restricted material without returning a word of it. `apps/documents/models.py`
   says Tags are in v1 "because FR-15's browse mode queries them" — so **FR-15 browse-by-tag,
   Stage 5 item 1, is the reader that opens it.**
9. **`ExtractedContent.extracted_text`** — derived from a document with no visibility column at
   all, reachable only through its `doc_id` foreign key, so the join is the guard rather than a
   stamp. Any future "view extracted text" surface inherits the problem.

**The generalisation.** There are exactly two safe treatments — re-stamp eagerly at the moment
of the change (instance 1), or re-scope on read through `scoped_chunks` (instance 2) — and a
third that is safe only by accident, which is having no reader (3, 4, 6, 7, 8, 9). **Stage 5
adds readers to two of them.** The cheapest structural guard is the one
`ConversationTurnSerializer` already uses: read `permitted_chunk_ids` from context **with no
default**, so a new reader that forgets the scope raises instead of quietly returning a body.

That the class had nine members when it was written with five is the point of recording a class
at all — and that instance 8 was found by walking the schema rather than by inspection is the
argument for enumerating rather than listing.

**Consequence worth knowing.** `ConversationTurnSerializer` reads `permitted_chunk_ids` from
its context with **no default**, so a caller that renders turns without supplying it raises
rather than returning a body. Deliberate: permitting everything is the leak, and permitting
nothing would look like a retrieval fault, so failing loudly is the only safe default.

## D-49 · The Stage 4 security review: what was closed, what was deferred, what stands conceded

**Status:** Settled by the user · **Date:** 2026-09-25 · **Stage:** 4 items 12 and 12a

The review executed its findings against the real database rather than reasoning about them,
and separated what it demonstrated from what it traced. This entry records the disposition.

### The gate criterion is met, and it was proved rather than asserted

Stage 4's "done when" requires that **a user cannot retrieve across the permission boundary by
any route the security review could find.** The review attacked it and could not: with a
document body echoing an Administrator-only chunk's identifier, and a model double that
honours the forged header, an Employee received no-answer path B, the restricted passage
appeared in no payload sent to the provider, and its text appeared nowhere in the response
bytes.

**Misattribution is reachable; widening is not.** The reason is structural and is the answer to
give if asked: scoping is a predicate on the query in `candidate_chunks`, so nothing the model
emits is consulted when the candidate set is built. Invariant 1 does not depend on the model
behaving.

### Closed before the stage ended (item 12a)

1. **Passage-text delimiter neutralisation**, which the stage brief required and which was
   unbuilt — "a passage instructing the model to ignore its constraints must not change the
   answer, and there should be a test that says so".
2. **`GET /api/search?q=<NUL byte>` answered 500 with an HTML body.** `q` was the only
   user-supplied string reaching the database without passing a DRF field, which is why the
   same byte gives a clean 400 on `POST /api/ask`. With `DEBUG=True` a 500 serves a traceback
   page carrying frame locals and the requester's own session cookie.
3. **An unbounded OOXML manifest read** — a 199 KB upload whose manifest expands to 200 MB,
   decompressed whole in 0.41 s, with both size checks passing because the upload is 199 KB.
4. **The cascade documentation corrections and their behavioural test** (see D-47's corrected
   table).
5. **`MAXIMUM_CHUNKS_PER_SOURCE`.** A 50 MB text file extrapolates to ~23,300 chunks, each a
   sequential NPU embed call inside one `transaction.atomic()` block in one synchronous
   request. **Objective 02's verification on 2 October requires 20 documents and a 20-page
   file in under 60 seconds**, which that does not survive. The cap is an Objective 02
   protection first and an availability measure second.

### The residual on the injection, stated rather than implied

**Neutralising the delimiter closes the reliable half of the attack and not the attack.** A
passage body can still direct the model in prose — "state X and cite the passage above" — and
`verify_citations` tests set membership only, so it cannot detect that the sentence did not
come from the passage whose identifier it carries. That is CLAUDE.md invariant 5's conceded
limitation, reached deliberately by an unprivileged user rather than by model error, and
`contribute_content` is held by **both roles** (D-30), so it is Employee-reachable into every
Administrator's answers over the same corpus.

Evidence the model does mine passage bodies is already in this repository: item 6's third
fabricated identifier was `5. Offboarding`, a section heading lifted out of a passage body.

A per-call nonce in the passage header (`[chunk_id-a3f9: …]`) would close the reliable half
completely. It is **not** being done before M6, because it rewords the prompt, and
`apps/ai/prompting.py`'s own rule is that rewording invalidates every measured rate in
`docs/flm-baseline.md`.

### Deferred, with the numbers recorded against them

- **Throttling `POST /api/ask` and the ingestion POSTs → Stage 5 item 5.** Worst case today is
  `GENERATION_TIMEOUT_SECONDS` (300) × `MAXIMUM_GENERATION_ATTEMPTS` (3) = **one request
  holding a worker for up to 900 s**, and only the two auth endpoints are throttled (D-26). It
  is deferred because it is deployment-shaped and the threat model at a one-machine
  demonstration is nearly empty — and because "one request holds a worker for 900 s" is really
  an argument against demonstrating on `manage.py runserver`, which is that item's decision to
  make.
- **`bulk_create(update_conflicts=True, …)` not cascading** — pinned by a test as a known hole
  rather than fixed. FR-15's bulk visibility editing is the obvious first caller of an upsert,
  and it should close it, about six lines in the same shape as the existing `update()` override.
- **`no_statement_verified`'s docstring overstates its guarantee.** The 503/200 split is a
  deterministic oracle for which no-answer path ran when generation fails while embedding
  succeeds — plausible under FLM serving two models — and the timing channel gives the same
  answer with no outage, since path A makes no provider call and path B costs one generation
  (p90 8.90 s, item 9a). Severity is genuinely low: what leaks is that material **in the
  caller's own scope** cleared the threshold and could not be cited, which `partial_matches`
  already discloses by design on both paths. So invariant 1 is intact and the stronger claim in
  that docstring is not. The docstring should say "no field of the reply distinguishes them".
  **No artificial delay is to be added.**

### The pattern behind three of this stage's findings: "closed" claimed too early

Three times in Stage 4, something was recorded as closed where **the observed instance stopped
reproducing rather than where the class did.**

1. **CLAUDE.md invariant 2** claimed the visibility cascade "has its own test". The claim held
   where it was read and failed where it was used — there was no test and no cascade (D-47).
2. **D-47** then claimed `bulk_update` was not covered. It is. Wrong in the *safe* direction,
   which is worse for maintenance: a reader who believes a path is uncovered never writes the
   test, so the real coverage stayed hostage to a Django implementation detail.
3. **This entry's own Part C** claimed the decompression bomb closed after bounding the
   manifest read. The manifest stopped working; the class did not — `word/document.xml` was
   still unbounded, and a per-member bound then turned out to need a whole-archive bound beside
   it, because 800 honest members of 63 MB each pass a per-member check (D-50).

The instruction this yields is durable and outlives Stage 4: **treat every "closed" in this
file as a claim to verify**, the same way invariant 2 taught this project to read CLAUDE.md. A
closure is only as wide as the thing that was measured, and the measurement is usually the
instance.

Applied immediately: D-50 declares the bomb class **closed for OOXML and open for PDF**, because
`pypdf` inflates object streams with no ZIP involved and nothing in item 12b touches it. No
docstring, comment or document in this repository says the class is closed.

### Confirmed clean, which is worth recording as much as the findings

Upload path traversal (sanitised twice, stored under the document's own UUID); `MEDIA_ROOT`
unreachable — no media route, no download view, and `file_path`/`content_hash` absent from
every serializer including the new `GET /api/documents/{id}`; the 503 body carrying no provider
detail, host, question or stack; all 19 protected routes carrying a server-side check
enumerated from the URL conf rather than trusted; 404-not-403 through a single scoped queryset
on every object route, so there is no branch to time; no header, `Content-Length` or ordering
channel between the two no-answer paths (measured identical, 323/323, `Vary: Cookie` on both);
session invalidation intact and untouched by Stage 4; and no secret, question, prompt or
passage written by any logger — the only logger in `apps/` is FR-05's audit log.

## D-50 · An oversized archive member is a 413 with its own message, and the bomb class is closed for OOXML only

**Status:** Settled by the user · **Date:** 2026-09-26 · **Stage:** 4 item 12b ·
**Supersedes:** item 12a's partial closure of the same finding

**The defect.** `_ooxml_format` read `[Content_Types].xml` unbounded: a 199 KB upload whose
manifest expanded to 200 MB was decompressed whole in 0.41 s, with both of FR-08's size checks
passing because the *upload* was 199 KB. Item 12a bounded that read — **and did not close the
class**, because the parsers run after the format is accepted and are unbounded too, so the
same archive with the payload in `word/document.xml` still decompressed whole inside the
ingestion transaction.

**Decision.** In `_ooxml_format`, with the archive handle already open, reject an archive whose
members declare more than `MEMBER_MAXIMUM_BYTES` individually or
`ARCHIVE_MAXIMUM_DECLARED_BYTES` in total, before any parser runs.

**Why a declared size can be trusted, and what that trust depends on.** The obvious objection is
that the declaration is attacker-supplied. It cannot usefully lie, and the reason is **not** item
12a's read bound (that covers the manifest only): **Python's `zipfile` caps decompressed output
at `zinfo.file_size`.** Measured on this interpreter — an archive declaring 1,024 bytes over
20 MB of payload raises `BadZipFile: Bad CRC-32` on `ZipFile.open(...).read()`, on
`ZipFile.read(...)` and on a bounded read; and with the CRC patched to match the truncated
prefix it returns **exactly 1,024 bytes with no exception**. So the *cap* is the guarantee and
the CRC error is only how it usually surfaces.

**That guarantee is inherited, not ours, and it is recorded with its dependency:** it holds
because `python-docx` (`docx.opc.phys_pkg`) and `openpyxl` (`openpyxl.reader.excel`) read
through `zipfile`. **A parser bringing its own inflate would void it.** Asserted by a test
rather than left as a comment.

A member that lies downwards is therefore not caught by the 413 at all — it declares 2 KB and
passes. It is caught one step later: the parser cannot get more than the declaration out of it,
`zipfile` raises, extraction turns that into `ExtractionError`, and the document lands on
"Extraction failed" with the original kept. The test is named for that mechanism rather than
implying the 413 covers it.

**413, not 415, and this is the third instance of one principle.** The file really is a DOCX or
an XLSX; its manifest names the Word or Excel content type. "File type not supported" would be a
false statement about the request, and an uploader acting on it would convert a file whose format
was never the problem. It is a size rejection — of decompressed size rather than transfer size —
and FR-08 already gives 413 to size, after signature. Its message deliberately never says
"50 MB", because the upload that earns it is about 100 KB.

The principle, now applied three times in this stage: **an error that misstates its reason is
worse than a generic one.** A NUL byte in a search term is not "too short" (item 12a); an
oversized member is not "unsupported format"; and a refused-before-attempting document is not
"Indexing failed" (D-51).

**The whole-archive bound was necessary and went beyond the brief.** A per-member bound alone
does not close what it claims: at deflate's ~1032:1, a 50 MB upload can honestly declare ~51 GB
spread over 800 members of 63 MB, every one inside the per-member bound. That is the same
"closed where the instance stops" error one layer in, so the sum is bounded too.

**The values are deliberately generous, because a false rejection is the expensive direction.**
64 MB per member is *larger than the entire 50 MB upload ceiling*, so an archive storing a member
uncompressed can never be refused for it. The measurement that justifies the generosity: a
minimal real DOCX of one paragraph is a 36 KB archive declaring **827 KB across 17 members**,
the largest being `word/stylesWithEffects.xml` at 438 KB — **a real document is itself a 22:1
expansion**, and a tight bound would have refused every DOCX this stack writes.

**Ordering inside the detector is deliberate.** The member scan runs only after the manifest has
named an accepted content type, so item 12a's oversized-*manifest* case stays 415, and a plain
ZIP of photos with a 200 MB member stays 415 — a 413 there would imply a smaller ZIP would have
been indexed. Both pinned by tests.

**PDF IS OPEN AND IS NOT CLAIMED OTHERWISE.** `pypdf` inflates object streams with no ZIP
involved, so nothing here touches it, and a PDF object-stream bomb is a live hole in ingestion.
Closing it means a pre-parse scan of `/Length` declarations or a memory ceiling around the
parser — not a five-line check, and it needs its own item. **The class is closed for OOXML and
open for PDF**, and no docstring, comment or document in this repository says otherwise.

**Residue, recorded rather than smoothed:** this is validation doing extraction's job. It was
chosen because one check with the archive handle already open beats three guards across three
libraries.

## D-51 · A seventh document status: "Too large to index"

**Status:** Settled by the user · **Date:** 2026-09-26 · **Stage:** 4 item 12b ·
**Migration:** `documents/0007_document_status_too_large_to_index` — additive, reversible,
choices only

**Decision.** `DOCUMENT_STATUS_VALUES` gains `"Too large to index"`, fourth in the tuple beside
`"Insufficient content"`. A document exceeding `MAXIMUM_CHUNKS_PER_SOURCE` lands there rather
than on `"Indexing failed"`.

**Why this is completing a distinction and not inventing a requirement.** The vocabulary already
separates *refused before attempting, on a property of the content* — `Insufficient content` —
from *attempted and failed* — `Indexing failed`. An over-cap document is the first kind and had
no term. **D-28 extended schema v1's five values to the proposal's six because five could not
express a state the system had; this is that argument one state further on.** The proposal is
**silent, not contrary**: `MAXIMUM_CHUNKS_PER_SOURCE` was settled in the same week and the
proposal predates it.

**Why the overload it replaces was not acceptable.** Item 12a put the over-cap case on
`Indexing failed`, which means *attempted and every chunk failed*. The new case is *refused
before attempting*, and the difference is user-visible: FR-08's "Processing failed. Please try
again" offers a retry that cannot work, because nothing about the file has changed.

**D-32 does not cover this, and filing it there would have been wrong.** D-32 records that
FR-08's retry recovers only an `Indexing failed` caused by a provider outage, and that a scanned
PDF parses identically however many times it is submitted. Those cases *may* succeed. This one
cannot — and D-32's own rule makes it worse, because the retry re-runs ingestion on the stored
original, so **every attempt redoes extraction and chunking in full before failing at the
identical point.**

**The name.** It states a property of the content and makes no claim that anything was
attempted; a test asserts the string contains no "failed". Its one imprecision is recorded: the
trigger is chunk count rather than bytes, so "large" is the user's word rather than the code's —
`"Too many chunks to index"` would leak an implementation term into a column a person reads.

**Consequences.**

- **The pairing test is what keeps the two values apart.** Over-cap lands on the new value and
  **not** on `Indexing failed`, with zero embed calls; a document whose every chunk genuinely
  fails lands on `Indexing failed` and **not** on the new value, having spent
  `MAXIMUM_EMBED_ATTEMPTS`. One test, both halves — either alone would still pass if a refactor
  collapsed them.
- `docs/schema-v1.md` §3 and `apps/core/tests/test_schema.py` both carry the value, because that
  test transcribes that document. The migration had to be placed immediately after `0006` in the
  test's plan rather than at the end, which is where the executor plans it.
- ~~**REQUIRED FOLLOW-UP, Stage 5 presentation work: the front end must suppress FR-08's retry
  affordance for this status.**~~ **DONE 27 September 2026**, in the Stage 4 finishing pass
  rather than in Stage 5: `canReprocess()` refuses the status, and because `DocumentTable` only
  rendered its status sentence for retryable rows, the rule was split into `canReprocess` and
  `statusMessageFor` so the one row nobody can act on is not also the only row with no
  explanation. The same defect existed a second time in the upload queue, where `failureFor`'s
  422 branch marked every failure retryable and a first upload over the cap is a 422 carrying
  this status.

  It was recorded in `documents.py` and `docs/schema-v1.md`, both now corrected — and this
  bullet said "`constants.py`" as a third, which was never true: that file carries the
  reasoning and never carried the not-done note. A follow-up recorded in one place fewer than
  claimed is the same defect as a closure wider than measured, in the other direction.
- **The meetings asymmetry is deliberate and explicit.** An over-cap transcript keeps
  `Processing failed`: the proposal defines no meeting status column (D-28), and FR-09 offers no
  retry affordance to mislead. If FR-09 ever grows one, it needs the same treatment.
- `manage.py reindex` has no chunk-cap guard, which is harmless today only because the over-cap
  branch writes no `ExtractedContent` row for it to rebuild from. That is a fragile reason and
  deserves an item if `reindex` ever learns to re-extract.
## D-52 · FR-15's detail view shows metadata and a download link, not extracted content

**Status:** Settled by the user · **Date:** 2026-09-27 · **Closes:** what the document
detail view built early in Stage 4 as D-46 is required to grow into

> **Superseded on 28 September 2026 by D-63.** Its statements that extracted text
> exists only as overlapping chunks, and that the download link was built, were false
> when written. D-63 restores the extracted content. This entry is left as written so
> the error stays visible, per the rule at the head of this file.
>
> **The download link was built on 13 October 2026, by Stage 5 item 2a (D-75).**

**Decision.** FR-15 reads: "Selecting a document opens a detail view showing its
metadata, extracted content, and a download link." The detail view shows **metadata
and a download link**. It does not show extracted content.

**Rationale.** `CLAUDE.md` §2 directs that depth is cut inside a requirement rather
than a requirement being cut, and names FR-15 as the example — "fewer filter
dimensions on FR-15". Two of three parts of one clause is depth.

The extracted content is already surfaced where it answers the question a reader
actually has. A citation on the Ask screen expands to its source passage, and that
passage *is* extracted content, at the granularity of "what text did this answer come
from". A document-scale panel would show the same material divorced from any
question. The cut removes a second presentation, not a capability.

It also avoids a schema decision the clause does not otherwise force. The stored form
of extracted text is `ContentChunk.chunk_text`, and `CHUNK_OVERLAP` is 50 tokens, so
the chunks cannot simply be concatenated to reconstruct the document — the text would
repeat fifty tokens at every boundary. Honouring the clause would require either
de-overlapping on read, which couples the detail view to the chunker's contract, or
storing the extracted text on `Documents`, which is a column and a migration. Neither
is warranted for a second presentation of material already shown.

**Consequences.**

- FR-15's clause is satisfied in two parts of three. The requirements-auditor should
  mark it **declined**, not missed. That distinction is the point of recording this.
- The answer to "how do you know extraction was faithful?" is the citation expansion
  and the Sources panel, not this page. That is the answer to give at the
  demonstration, and it is a better one than a wall of text.
- A document's title links to its record; the download action lives on that record.
  The Ask screen's link is to the record, and is labelled as such.
- Four of the seven document statuses would have had no extracted content to show in
  any case — "Extraction failed", "Insufficient content", "Indexing failed", and
  D-51's "Too large to index". The cut removes the need to define a display for each.
  The download link still works for all four, because the stored original exists
  whether or not it was indexed.

**What this decision does not cover.**

- **The download link**, which is FR-15's third part and is built. Its storage path
  depends on D-18 and its scoping on the shared `scoped_documents()` helper.
- **Extracted content anywhere else.** The citation expansion continues to show
  passage text and the Sources panel continues to list every item consulted; this
  decision removes one presentation, at one place.
- **Whether the detail view should show extracted content after M6.** This is a
  decision about the gate, not about the product. Revisiting it means settling the
  de-overlap-or-store question above, which this decision deliberately leaves open.

## D-53 · Fail closed on a source/chunk visibility disagreement, and the mechanism is one helper

**Status:** Settled · **Date:** 2026-09-27 · **Comes due:** FR-15, Stage 5 item 1 ·
**Closes:** a contradiction nobody decided

Two modules resolve source rows for chunks that scoping already admitted, and they disagree:

| Module | Behaviour | Its own argument |
|---|---|---|
| `apps/retrieval/search.py` | **fails closed** — a source whose chunks are stamped visible while the source is not simply does not appear | "the cheap direction to be wrong in is the one that returns less" |
| `apps/api/answers.py` | **fails open** — no `visible_to_roles` predicate when resolving titles and dates | the chunk stamp already admitted the role, and "two filters that can disagree is worse than one that cannot" |

Both are documented; they contradict each other; nobody decided which is right. Harmless while
D-47's cascade holds — and `bulk_create(update_conflicts=True, update_fields=["visible_to_roles"])`
is the hole D-47 pins as **open**, which is exactly the route FR-15's bulk visibility editing will
take. When it does, the Sources panel and the partial-match list will name a source the source
table says the reader may not see, while search hides it.

**Decision: fail closed is authoritative.** Invariant 1's cost is asymmetric — returning less is a
usability defect, returning more is a disclosure — and FR-11's clause is about what must never be
disclosed rather than what must always appear.

**But `answers.py`'s argument is also right, and the resolution is not "add a second predicate".**
It is that there should be **one** predicate for source rows, in one place, as `scoped_chunks` is
the one predicate for chunk rows. There is none: `visible_to_roles__contains=[...]` is written
**eight times** by hand — `apps/api/views.py` ×5 (documents list, document detail, meetings list,
meeting detail, document reprocess), `apps/retrieval/search.py` ×2, `apps/retrieval/scoping.py` ×1
— and the five in `views.py` read the role off `request.user.role.role_name` rather than through
`permission_scope`, which exists so that no caller has to remember to resolve it. Equivalent today
because DRF loads the user per request; that is luck, not design.

Invariant 2's stated purpose is that invariant 1 be "a predicate on the same table as the vector
rather than a discipline someone has to remember". One layer up it **is** a discipline someone has
to remember, eight times, and **FR-15 is the ninth caller.**

**What is owed before FR-15 writes that ninth copy:** `scoped_documents()` and `scoped_meetings()`
beside `scoped_chunks`, both failing closed; `answers.py` and the five `views.py` sites moved onto
them; and **one test enumerating the routes that return source rows, asserting each carries the
predicate** — because the dual-role matrix would credit a route that returned everything, so long
as both roles got a 200 from it.

**What this entry covers:** the direction to fail in, and where the predicate belongs. **What it
does not:** the code. Nothing changes today, and the disagreement stays harmless until the
`bulk_create` hole is reached.

> **Implemented on 5 October 2026, Stage 5 item 1.** `scoped_documents()` and
> `scoped_meetings()` sit beside `scoped_chunks()` in `apps/retrieval/scoping.py`, and fail
> closed. The predicate is now written only there. These callers moved onto the helpers:
>
> - `apps/api/views.py`: `DocumentsView.get`, `DocumentDetailView.get`, `MeetingsView.get`,
>   `MeetingDetailView.get` and `DocumentReprocessView.post`. Each now resolves the role
>   through `permission_scope` instead of reading `request.user.role.role_name`;
> - `apps/retrieval/search.py`: the document and meeting querysets of `search()`;
> - `apps/api/answers.py`: `_titles_and_dates`, which used to fail **open**. `reply_for`
>   now takes the user and resolves the scope itself, as `search()` and
>   `answer_question()` do, so no view passes it a role.
>
> `apps/api/tests/test_source_rows_fail_closed.py` is the test this entry asked for. It has
> three parts: a scan that fails if the predicate is spelled outside the scoping module, or
> if a request-serving module reads a source manager directly outside a named exception; a
> table that every route in the URL conf must appear in, either as returning source rows
> with a probe or as returning none with a reason; and a probe per source-returning route
> against a source whose chunks are stamped wider than the source itself. Each probe has an
> Administrator mirror. The `POST /api/ask` probe failed against the code before this
> change, because the Sources panel named the source.
>
> **What the implementation covers:** the title, date and identifier of every Document and
> Meeting row that a request-serving route returns, for the routes in the test's table.
>
> **What it does not cover:**
>
> - **The statements of a live answer.** In the disagreement state the chunk stamp admits the
>   passage, so it is a retrieval candidate and is sent to the model, and a statement citing
>   it survives verification. Failing closed on the source drops the item from `sources` and
>   `partial_matches` and nothing more. The statement is then shown with a citation that has
>   no passage to expand to. Stopping the passage from reaching the model would need the
>   source predicate inside the candidate set, a join that D-17 exists to avoid. The defence
>   for that case is still D-47's cascade.
> - **A reopened turn.** `GET /api/conversations/{id}` re-scopes through `scoped_chunks` only
>   (D-48), so in the disagreement state it shows the same statements the live reply did. It
>   returns no source rows until Stage 5 item 4b, and the test's table says that route must
>   move across with a probe when it does.
> - **`bulk_create(update_conflicts=True)`**, D-47's pinned hole. Nothing here closes it.
> - **Reads of `ExtractedContent`, `ContentTag`, `Tag`, `QueryLog` and `AnswerCitation`.**
>   The scan watches `Document`, `Meeting` and `ContentChunk` managers only. FR-15 adds
>   readers of the first three, and must scope them through a scoped document.
> - **`apps/ingestion`**, including `manage.py reindex`. Neither is a route.
> - **The D-29 checks on upload and transcript ingestion.** They still read
>   `request.user.role.role_name`. They test whether the caller's own role is in the scope
>   being written, and do not filter what is returned.

## D-54 · The NUL-byte rejection is fixed at the instance; the class reopens with FR-15

**Status:** Open — recorded, not resolved · **Date:** 2026-09-27 · **Comes due:** FR-15,
Stage 5 item 1

> **Settled on 5 October 2026 by D-65**: every query parameter passes a DRF serializer.
> This entry is left as written.

`GET /api/search?q=<NUL>` raised `psycopg.DataError` out of an ORM `icontains` lookup, uncaught,
answered **500 with an HTML body** — and under `DEBUG=True` that page carries the traceback, the
frame locals and the requester's own session cookie. Item 12a closed it with a distinct exception
raised in `search()` before any query runs.

The fix is right, and its docstring's claim is **verified rather than asserted**: `q` is the only
user-supplied string reaching the database without passing a DRF field, because
`request.query_params` and `request.GET` appear in exactly one place in production code. DRF's
`CharField` carries `ProhibitNullCharactersValidator`, which is why `POST /api/ask` answers a clean
400 for the same byte.

**What it covers:** `q` on `GET /api/search`. **What it does not cover:** every query parameter
that does not exist yet.

**FR-15 is "document repository and *filtered* browsing".** The moment it adds `?department=`,
`?tag=`, `?status=` or a date range read off `query_params` into an ORM lookup, each reopens the
identical class — and the fix will not carry forward, because it lives **inside `search()`** rather
than at the request boundary.

This is D-49's pattern once more: the payload moves and the class does not close. The remedy is a
shared query-parameter reader, or a rule that every query parameter goes through a serializer
field — decided **before** FR-15 writes its first filter rather than after.

## D-55 · `rejected_count` on QueryLog — numbering a column that shipped without a decision

**Status:** Settled retroactively · **Date:** 2026-09-27 · **Numbers:** commit `964f73e`,
Stage 4 item 8 · **Migration:** `retrieval/0002_querylog_rejected_count`

`964f73e` added a column and a migration beyond the proposal's `QueryLog` table, carrying no
D-number. CLAUDE.md §9 requires settled decisions to be numbered and the number cited in code and
commit messages; the argument existed in `docs/schema-v1.md` and in three docstrings, in none of
them as a decision. Both auditors named it. This entry is the number.

**Decision.** `QueryLog.rejected_count`, nullable, populated on every call that reached
generation — including answered ones.

**Rationale.** Invariant 7 requires no-answer path B's two kinds to stay separable, and
`no_answer_reason` cannot do it: a model that proposes nothing and a model whose every citation is
rejected both arrive as `no_statement_verified`. Item 6's live runs moved 2 declined / 3
all-rejected before the prompt fix to 6 / 0 after, while the aggregate moved 5 → 6 — **the
aggregate alone reads as "no effect"**, and the whole finding lives in the split.

Answered rows are populated too, and that is the point rather than an edge case: `verifyCitations`
strips individual statements, so `answered=True` with `rejected_count=1` is fabrication that has
not yet cost anyone an answer — the earliest warning the system produces.

**What it covers:** every call that reached generation. **What it does not:** a call that did not —
no-answer path A and the keyword search path, where it is NULL. NULL never means "path B did not
occur" and never means zero.

**Why a count and never the claimed identifier.** §7.9's rejection log would record both. A
fabricated identifier has no referent, so storing one invites a later reader to resolve it against
`ContentChunks` and read a hit or a miss as provenance. A database column is a surface, and
invariant 6 applies to it.

**Record-only.** No serializer may expose `rejected_count` or `no_answer_reason`; either hands a
caller the path-A/path-B distinction that the identical reply exists to hide.

## D-56 · Partial matches are a reply field, derived before the threshold

**Status:** Settled retroactively · **Date:** 2026-09-27 · **Numbers:** commit `2c10364`,
Stage 4 item 10a · **One gap open:** no relevance floor

The second auditor called this "the largest untraced change of the stage": a new module, a new
field on every `POST /api/ask`, a presentation dataclass and serializer, a cap constant, a change
to the disclosure surface of both no-answer paths, and the deletion of a shipped front-end
heuristic — argued well in `apps/retrieval/partial_matches.py` and recorded in no decision. D-44 is
the Sources panel, not this.

**Decision.** FR-12's "any partially related items found are offered, clearly labelled as partial
matches" is served by a `partial_matches` field on the ask reply, derived from `rank(...)` output
**before** `admit()` applies `RELEVANCE_THRESHOLD`, deduplicated to one entry per source in rank
order, capped at `MAXIMUM_PARTIAL_MATCHES = 5`.

**It replaced a front-end keyword heuristic** that took one word from the question and searched on
it, because a whole question is a single substring matching nothing — measured, a full question
returned `total_count: 0` while one of its words found the right meeting. That worked, put a
server-side job in the client, and returned keyword hits rather than the near misses the clause
describes.

**Derived identically on both no-answer paths, which is the constraint that shaped it.** Not from
the admitted set, not from the rejected statements, not from anything differing between the paths:
item 7 made the two replies byte-identical on purpose and item 8 keeps the record-only fields out
of every serializer for the same reason. Both no-answer constructors **require** the argument
rather than defaulting it, so the two branches cannot be built with different values.

**Source identity and date only, never passage text**, and structurally so — the objects carry no
attribute for text, passages or score. A snippet beside a message that has just said the question
cannot be answered reads as a partial answer: invariant 6 through a side door.

**What it covers:** both no-answer paths, identically, and an answered reply carries the key empty
so the shape never varies between outcomes. **What it does not cover: any relevance floor at all.**
The list is the five nearest in-scope sources whatever their score, so on a corpus holding nothing
related it offers five titles that are not partially related to anything. On six chunks that is
invisible; on a real corpus it is a screen recommending five documents to someone who asked about a
subject the platform does not hold. **Unresolved** — either a floor or an explicit acknowledgement
is owed, and Stage 5 item 3's re-measurement against a real corpus is when the evidence to choose
will exist.

## D-57 · Three Stage 4 commit-discipline departures, recorded rather than left to be found

**Status:** Recorded · **Date:** 2026-09-27 · **Concerns:** commits `964f73e`, `2c10364`,
`9d5b5f7`

Both auditors checked every Stage 4 commit against CLAUDE.md §7 and §9. Twenty of twenty-three
trace cleanly to a numbered item or decision. Three did not.

1. **`964f73e`** — a column and a migration with no D-number. Numbered now as **D-55**.
2. **`2c10364`** — a reply field, a module, a serializer and a constant with no D-number, plus the
   deletion of a shipped front-end heuristic. Numbered now as **D-56**.
3. **`9d5b5f7`** — **items 12, 12a and 12b in one commit**, against §7's "commit at every stage
   increment ... at each numbered step". D-50 explicitly *supersedes* item 12a's partial closure, so
   that commit contains both a decision and the decision correcting it.

   **And its subject is wrong in a way that matters for the M6 write-up.** It reads
   `fix(FR-11/FR-12)` while much of its content is **FR-08**: `MAXIMUM_CHUNKS_PER_SOURCE`, the
   archive member and total bounds, migration `documents/0007`, and D-51's seventh document status.
   **Anyone grepping the history for FR-08 will not find the seventh document status.** Per §7 a
   pushed commit's message is not rewritten, so this entry is the cross-reference: FR-08 work landed
   in `9d5b5f7` under an FR-11/FR-12 subject.

**The lesson, and the reason to record this at all.** Three increments in one commit is what let
D-51's front-end half ship missing: the seventh status went in backend-side and the retry affordance
that contradicts it sat in the same commit's blast radius with nothing forcing a second look. Item 2
of this finishing pass is that affordance — a defect whose direct cause is the departure recorded
here.

**A fourth, from this finishing pass itself, for the same reason.** Items 4, 5, 6 and 7 were first
committed together under a subject naming only item 4, one commit after this entry was drafted. It
was reset and split before being pushed. Recorded because a rule its own author breaks within the
hour is evidence about the rule's difficulty, not only about the author: the pressure is always to
batch documentation edits that touch one file.

## D-58 · An unused conversation can outlive a session, and closing it needs a contract addition

**Status:** Open — recorded, not resolved · **Date:** 2026-09-27 · **Comes due:** Stage 5 ·
**Arises from:** the finishing pass's item 3

`POST /api/ask` attaches a turn to a thread and **creates none**: an omitted `conversation_id`
means `QueryLog.conversation` stays NULL and the reply's `conversation` is `null`. So the client
must create the thread *before* asking, and a first question that fails — a 503 on NFR-19's own
demonstration path, or a 400 the client pre-check missed — leaves a thread with nothing in it.

**Create-then-ask is forced by the contract, and the obvious fix is worse than the defect.**
Creating the thread only after a reply succeeds would make the first question a one-off that no
thread can adopt: the thread would reopen without its own first question, and the prior questions
a follow-up resolves against are read from that thread's `QueryLog` rows (D-42). That trades a
cosmetic defect for an FR-13 one.

**What item 3 fixed:** abandonment. A thread whose question failed is reused rather than
abandoned, "start a new topic" keeps an unused thread instead of stranding it, a reply of either
kind retires the reuse, and a 404 drops the id. One failed first question now costs **at most one**
thread per session however many retries or topic clears follow, where each cycle previously cost
another.

**What is not fixed, and is not claimed to be:** a thread created for a question that failed, after
which the user leaves, persists. Nothing under `frontend/` can remove it and nothing was invented
to try.

**The two ways to close it, neither chosen here.**

1. **`has_turns`, or a turn count, on the `GET /api/conversations` list object.** A thread nobody
   asked anything in is then omitted from the list. Cheapest: no new route, no new verb, no
   departure from FR-13's CRUD line.
2. **A Delete route.** FR-13's Database clause is Create, Read, Update, so this would be a verb the
   requirement does not specify — and D-43 already argued against inventing FR-13 controls the
   interface does not ask for.

Option 1 is the likelier answer and it is still a contract addition, so it is raised rather than
taken.

**One thing deliberately not done.** Emptiness is *not* inferred from the `"New conversation"`
title. D-43's own consequence is that a whitespace-only question leaves the placeholder standing,
so a title test would be a heuristic on a display string — the class of thing this file has spent
the stage removing.

## D-59 · The finishing pass omits the FR ID from most commit subjects, and this entry's first draft was an instance of the rule above

**Status:** Recorded · **Date:** 2026-09-27, corrected 2026-09-28 · **Concerns:** every
commit in `9508442..e81c6e6` · **Breaches:** CLAUDE.md §7, and §8 condition 4 in part

CLAUDE.md §7 requires "Conventional commits, FR ID in the subject". §8 condition 4
requires the work "committed on its branch with the FR ID in the message". Those are
different tests and the finishing pass fails them by different margins. Both are
measured here over the range `9508442..e81c6e6`, so this entry cannot go stale the way
its first draft did.

**§7, the FR ID in the *subject* — these nine fail:** `6949343`, `72c26ed`, `033879f`,
`96b4bbe`, `33534ea`, `116a422`, `a05692d`, `4400b7b`, `52ff2b7`. **These three
comply:** `6e563cf` (FR-15), `ba5382f` (FR-08), `e81c6e6` (FR-11/FR-12/FR-13). Each of
the nine cites its item number instead — `docs(item 4):`, `fix(item 1c):` — which was
the instruction for the pass and traces a finding to its fix, but is not what §7 asks
for, and the two are not alternatives: an item number means nothing to a reader without
the finishing-pass brief, and that brief is not in the repository.

**§8 condition 4, the FR ID anywhere in the *message* — these three fail:** `72c26ed`,
`96b4bbe`, `116a422`. Every other commit in the range names a requirement in the body.

**This entry's first draft was itself an instance of the rule above, and it is
corrected here rather than quietly rewritten.** It said *"the only FR IDs in any
subject are FR-08 and FR-15"* and *"Nothing in this branch's history names FR-11,
FR-12 or FR-13."* Both were false when committed. `e81c6e6`, the commit carrying that
text, has the subject `fix(FR-11/FR-12/FR-13): close the fourth audit, including the
seventh instance`; the bodies of `6949343`, `033879f`, `33534ea`, `a05692d` and
`52ff2b7` name those requirements; and across the whole history reachable from that
commit, forty messages do. The error was not arithmetic — it was reading subject lines
and writing a sentence about messages, in the entry recording a breach of the rule
against exactly that. It was found by running `git log --format=%B` over the range,
which is the only difference between the two drafts.

**Two further claims of the first draft, withdrawn.** It said the commits were
"**unpushed** — `origin/feat/M5-retrieval-and-generation` is still at `9508442`", and
reasoned from that that the subjects could be rewritten cheaply. True when written, and false
before the end of the same session: the reflog dates the commit of `e81c6e6` at 21:07:52
and its push at 21:20:20, the branch is the head of **open PR #17**, and `5a4ed61`
merges `main` back into it. It also said the
branch "already had a merged pull request (#15)"; there are two, #15 (`39a183b`) and
#16 (`6d6c619`), and #16 is the one that pushed `9508442`. A claim about a mutable ref
is the same failure mode as a count — `origin/<branch>` is not a list of hashes.

**What this entry covers:** the twelve commits in `9508442..e81c6e6`. **What it does
not:** the commits of PR #15, audited by D-57, which names the departures it found;
and the commit of PR #16.

**The subjects were not rewritten.** D-60 records why, and the short reason is that
rewriting them cannot make §8 pass, because condition 5 fails for a reason no rewrite
touches.


## D-60 · Stage 4 closes with §8 condition 4 declined and condition 5 failed, both recorded rather than described as met

**Status:** Recorded · condition 4 **declined**, condition 5 **failed** · **Date:**
2026-09-28, corrected the same day · **Concerns:** CLAUDE.md §8 conditions 4 and 5 for
FR-11, FR-12 and FR-13 · **Supersedes:** the closing paragraph of D-59's first draft

CLAUDE.md §8 says a requirement is done when **all** five conditions hold, "not four of
five". Conditions 4 and 5 do not hold for this stage, and they do not hold for different
reasons: condition 5 failed on measurement, and condition 4 was declined. **This entry's
first version framed the two as pointed at each other — do both or neither — and that
framing was wrong.** They are independent in both directions. No commit subject changes
what an audit finds, which is why rewording could not have made §8 *pass*; but equally no
audit finding stopped the subjects being reworded, so condition 4 could have been *met*
on its own. The first version let the first fact stand in for the second.

**Condition 4 — "committed on its branch with the FR ID in the message" — DECLINED.**
D-59 lists the subjects in `9508442..e81c6e6` that omit the FR ID under §7, and the
messages that omit it entirely. Condition 4 was independently achievable while those
commits were unpushed: rewording them was a local rebase, touching no shared ref, at no
risk to anyone, and requiring nothing of condition 5. **It was declined.** The first
version of this paragraph said only that condition 4 "fails", and called it "a decision
for the repository's owner" as if the decision were still pending — from which a reader
infers it could not be done. That is the same shape of defect the rule at the head of
this file exists to prevent, in the entry recording that rule's own outcome, and it is
corrected here rather than quietly rewritten.

**It stays declined, and the reason is that the window has closed.** The commits in
`9508442..e81c6e6` were pushed at 21:20:20 on 27 September and merged to `main` by PR
#17 (`e71a0f9`) at 21:31:49 that evening. `403087f`, the commit carrying this entry's
first version, is pushed and merged to `main` by PR #18 (`1220e96`). Rewording the
subjects now would rewrite `main`'s history beneath merged pull requests — a force-push
to the shared default branch — and an FR ID in a subject line is not worth that. The
first version also called PR #17 **open** and said no commit in the range was an ancestor
of `main`. Both were false when committed: `403087f` is dated 08:00:30 on 28 September,
and #17 had merged at 21:31:49 the evening before. A claim about the state of a pull
request is a claim about a mutable ref, which D-59 already names as the same failure mode
as a count.

**Condition 5 — "`requirements-auditor` has checked it against the FR text and reported
no gaps" — fails, and this is why rewording would not have helped.** The two conditions
are independent: no commit subject affects what an audit finds. The pass over
`e81c6e6` was deliberately bounded — scoped to that commit's diff alone, with a single
stated pass condition, "does this commit introduce another instance of the coverage
rule?" — because unbounded passes had become a loop with no fixed point: the audit reads
text, and every fix writes new text. A bounded pass can come back clean rather than
merely come back. **It did not come back clean.** It returned these, in that one commit,
all verified independently before being accepted: D-59's "the only FR IDs in any subject
are FR-08 and FR-15" and "Nothing in this branch's history names FR-11, FR-12 or FR-13";
this file's rule saying "Seven"; its "the last introduced by the very commit that corrected the one
before it" (`116a422` introduced it and touches no decision entry, and `4400b7b`
corrected the previous one two commits later); its "Four audits have each found one" set
beneath a list of seven; `apps/core/constants.py` calling that entry "the sixth" while
the same commit's subject called it "the seventh"; `frontend/src/utils/documentStatus.js`
saying "Three statuses are refused it" over a list of two, in the commit correcting that
docstring's "Two"; and `docs/stage-4-clause-audit.md` placing a correction "one row below
the two that had just been corrected" when the rows corrected were 9, 14, 22 and FR-11's
Database row, none of them in that table.

**What the pass over `e81c6e6` changes, and what it does not.** Each of those is fixed
in `403087f`, and fixed *structurally* — by deleting the count or the positional
reference and substituting a list, a range or a commit hash — because a corrected number
is still a number, and the next addition falsifies it. That is the amendment the rule
above now carries: prose that enumerates cannot be falsified by the next addition.
**It does not make condition 5 pass.** No pass has reported no gaps.

**The pass over `403087f`, and where the loop stops.** `403087f` was then given the same
bounded pass, with its condition stated in advance: does this commit introduce a further
instance of a coverage claim that counts, enumerates or refers by position instead of
listing? The expectation was a clean result, since that fix was structural rather than
corrective. **It was not clean.** The table stayed free of totals, but two of its own row
keys carried ordinals, and the prose written around it — this entry, D-59, `Ask.jsx` —
counted sets it did not list. The findings are rows in the table at the head of this file,
each keyed "in `403087f`", and they are fixed in the commit that adds those rows. **That
fix is deliberately not audited.** Auditing the fix is the recursion the bound exists to
end, so the loop stops here by decision, not at a demonstrated fixed point: the table
closes the class structurally, and prose outside it is not yet shown to.

**Consequence, stated plainly.** FR-11, FR-12 and FR-13 meet conditions 1, 2 and 3 —
the behaviour, the dual-role tests at 19/19, and a failure path each. They do not meet
conditions 4 and 5. By §8's own wording that means they are **not done**, and the M6
gate list carries them that way: condition 4 is declined for `9508442..e81c6e6` and will
not pass, and condition 5 stands failed unless a later audit returns clean — the Stage 4
closing audit, recorded in D-61, did not. What is
demonstrable is unaffected: the pipeline, the permission
boundary and the assistant work, and the defects the audit passes found were in prose
describing the work, apart from the shipped no-answer string, which is fixed at both
sites with the bundle rebuilt.

## D-61 · The Stage 4 closing audit returned INCOMPLETE, and its verdict is recorded here verbatim

**Status:** Recorded · findings **open against Stage 5** · **Date:** 2026-09-28 ·
**Concerns:** FR-11, FR-12, FR-13 · **Audited:** `2ba4de9`

One full `requirements-auditor` run against Stage 4, at `2ba4de9`, after D-60 was
corrected and the bounded pass over `403087f` was fixed. It is recorded here because a
verdict that lives only in a terminal is the same failure mode as an invariant that lives
only in a document. **Nothing it found was fixed in the session that ran it**, by
instruction: the stage closed that day whatever the verdict, and the findings are
carried to Stage 5 below.

**What it settles.** It found no route by which out-of-scope material reaches the AI
service, contributes to an answer, or has its existence disclosed, and it passes
invariant 1 over `/api/ask`, `/api/search`, `/api/conversations*`, `/api/documents/{id}`,
`/api/meetings/{id}` and reprocess. It marks each of FR-11, FR-12 and FR-13 as
demonstrable locally, and none as done under §8. Condition 5 fails on this audit, as
D-60 said it stands until an audit returns clean.

**What it adds that was recorded nowhere before:** its gap 3. The active thread in
`frontend/src/pages/Ask.jsx` lives only in component state, so following a citation's
same-tab source link and pressing Back returns an empty conversation. This is on the
path an assessor will walk.

**Carried to Stage 5, unfixed.** The owner column records what the audit reports. Where
the audit names no Stage 5 item, the row says so; that is a finding against
`M6-BUILD-PROMPT.md`, not an assignment made here.

| Audit gap | Stage 5 owner, as the audit reports it |
|---|---|
| 1 — §8 condition 5 | none; recorded in D-60 and here |
| 2 — §8 condition 4 | none; declined in D-60, and cannot be fixed |
| 3 — thread lost on navigation, including a citation link | **no Stage 5 item** |
| 4 — reopened turns: no expansion, no source link, no Sources panel | **no Stage 5 item** |
| 5 — `AnswerCitation.chunk` `CASCADE` (D-48) | **no Stage 5 item** |
| 6 — partial matches have no relevance floor (D-56) | Stage 5 item 6 |
| 7 — "input is sanitised" deliberately not done (D-45) | none named; to be presented as a deviation |
| 8 — prior questions only (D-42) | none named; a deliberate narrowing |
| 9 — no front-end test runner (D-25) | Stage 5 item 4 |
| 10 — `answers.py` fails open against `search.py` (D-53) | Stage 5 item 1 |
| 11 — provenance state discloses maintenance on out-of-scope sources | none named |
| 12 — orphaned empty conversations (D-58) | **no Stage 5 item** |
| 13 — front-end constants duplicated; literal "50 MB" | none named |
| 14 — branch name breaks §7's per-FR convention | none; historical |
| 15 — deployment topology undecided; a provider switch triggers gap 5 | Stage 5 item 9 |

**The verdict, verbatim.** Reproduced as the auditor returned it, quoted rather than
re-headed so its structure does not interleave with this file's.

> ## Audit: Stage 4 (FR-11, FR-12, FR-13), branch feat/M5-retrieval-and-generation @ 2ba4de9, 2026-09-28
>
> **Verdict:** INCOMPLETE
>
> Source text: I read the FR-11, FR-12 and FR-13 clauses directly from `proposal.txt` lines 729–936, which is the text extracted from the .docx, so I did not rely on the clause audit's quotations. I made no file edits and did not re-run pytest. The only commands I ran were read-only git and grep.
>
> Short version: I found no route by which out-of-scope material reaches the AI service, contributes to an answer, or has its existence disclosed. The permission boundary is the strongest part of the stage and it is well tested. The stage is still not done under §8. Condition 4 is declined (D-60) and condition 5 fails because this audit reports gaps. Several clauses are partial, and one front-end defect is recorded nowhere in the repository and sits on the exact demo path.
>
> ---
>
> ### Clause coverage — FR-11
>
> | Clause | Status | Evidence |
> |---|---|---|
> | FE: no dedicated interface; different results per role; no hint that anything was withheld | satisfied | `apps/api/tests/test_fr11_scoping.py:557` (Admin gets the answer the Employee was refused), `:585` (Employee reply is byte-identical whether or not the restricted rows exist), `:679` (search counts differ per role) |
> | Permission filter built from the role before retrieval, applied as a query condition | satisfied | `apps/retrieval/scoping.py:99-112`, `:115-133`. The predicate is asserted in the compiled SQL at `apps/retrieval/tests/test_scoping.py:90`. The tests are shown to fail when the predicate is removed: `apps/api/tests/test_fr11_scoping_bites.py:64-105` |
> | Validation: invalid session rejected before any retrieval | satisfied | `config/settings.py:143-144`; 401 subclass `apps/api/authentication.py`; `test_ask.py:817` asserts 401, no QueryLog row, zero embed calls |
> | Validation: an empty scope returns FR-12's no-answer, not an error | satisfied | `pipeline.py:468-486`; `test_pipeline.py:221`; `test_fr11_scoping.py:1183` |
> | Filtering at retrieval, not at generation | satisfied | `pipeline.py:449-505`. The generation payload is asserted clean at `test_fr11_scoping.py:458-471`, on all three exits (`:483`) |
> | Counts computed after filtering | satisfied | `pipeline.py:379` (`len(passages)`); `search.py:228-252` (derived properties); `test_fr11_scoping.py:453-456` |
> | Responses: a scoped result set or an empty set | satisfied | `views.py:917-992`, `:662-721` |
> | CRUD: Roles, RolePermissions, Documents (Read) | partial | Retrieval reads Roles (`scoping.py:87-92`) and `visible_to_roles` from the chunk stamp. It never reads RolePermissions. This is by design (D-11/D-17) and the clause audit already records it. |
>
> ### Clause coverage — FR-12
>
> | Clause | Status | Evidence |
> |---|---|---|
> | Search field on every page | satisfied (no automated test) | `frontend/src/App.jsx:111-115,132` |
> | Results grouped by type with a count per group | satisfied | `search.py:215-252,471-494`; `test_search.py:131` |
> | Each result shows title, snippet, department, date | satisfied | `search.py:181-212`; `SearchResults.jsx:19-45`; `test_search.py:152` |
> | Natural-language question returns an answer with numbered inline citations | satisfied (live reply) | `answers.py:180-191`; `Answer.jsx:80-131` (renders the server's `position`) |
> | Each citation expands to show the source passage | **partial** | Works on a live reply (`answers.py:194-224`, `Answer.jsx:106-127`). On a reopened turn it does not expand: `utils/turns.js` `savedTurnFrom` sets `sources: []` and `expandable: false`. |
> | …and links to the source document or meeting | **partial** | Works live (`utils/sources.js`, `views.py:621-656`). A reopened turn has no link at all. |
> | Sources panel lists every item consulted, with its date | **partial** | Works live (`answers.py:194-224`, `Answer.jsx:175-194`). A reopened turn has no Sources panel. |
> | No interface state shows an uncited factual statement | satisfied at the API; **untested at the UI** | `pipeline.py:255-273` (no field for rejected statements); `test_pipeline.py:712`; no front-end test runner exists |
> | No-answer stated plainly, with no speculative answer | satisfied | `Answer.jsx:313-324`; `test_ask.py:379` |
> | Partially related items offered, labelled as partial matches | **partial** | `partial_matches.py:119-148`. There is no relevance floor, so the five nearest in-scope sources are offered even when none is related (D-56 is open). |
> | Queries under two characters rejected client-side | satisfied | `utils/validation.js` `searchTermError`; also enforced on the server at `search.py:432` |
> | Question length capped | satisfied | `pipeline.py:418-424`; `test_pipeline.py:332-382` |
> | Input sanitised before use | **partial (deliberate deviation)** | D-45: no sanitiser. The only change is neutralising the `[chunk_id:` delimiter (`apps/ai/prompting.py:204,408`). Prose injection through a document body is open (D-45 case c). |
> | Retrieval only over chunks whose recorded model matches the query model | satisfied | `scoping.py:133`; `test_pipeline.py:239`; `test_scoping.py:244,279` |
> | Context truncated to the window, lowest-ranked dropped first | satisfied (never triggered on the demo corpus) | `ranking.py:178-222`; `test_pipeline.py:648,1070` |
> | Scoping applied before ranking | satisfied | `pipeline.py:449-454` |
> | Ranking: recorded model, cosine similarity in the application, rank order, threshold exclusion | satisfied | `ranking.py:68-175`; constants `apps/core/constants.py:46,51` (`RELEVANCE_THRESHOLD` provisional, D-37/D-40) |
> | Grounding: prompt holds only the passages plus their ids | satisfied | `pipeline.py:501-505`; `test_pipeline.py:609`. The FR-13 history block is the one addition (D-42). |
> | Structured output of discrete tagged statements | satisfied | `apps/ai/schema.py`; `generation.py:95-121` |
> | Deterministic verification in application code | satisfied | `verification.py:90-121`; `test_pipeline.py:674,1143` |
> | No-answer path A without generation; path B returns the same reply; the two recorded separately | satisfied | `pipeline.py:468-486,526-543`; `test_pipeline.py:186` (generation called zero times), `:839`; `test_ask.py:418` (bodies byte-identical) |
> | Gap evidence: every query logged with result count and answered status | satisfied (narrow reading) | `query_log.py:242-288`. The count is derived from `retrieved_chunk_ids`. 503s and 400s write no row, following 7.10. |
> | Traceability: question, chunk ids, answer and verified citations logged so any answer can later be traced | **partial** | The write is correct (`query_log.py:242-280`). `AnswerCitation.chunk` is `on_delete=CASCADE` (`apps/retrieval/models.py:114-116`), so a reprocess or reindex destroys citations. The loss is pinned by `test_fr12_traceability_lost_on_reprocess.py` (D-48). |
> | Responses: 200 grouped / 200 answer / 200 `answered:false` / 503 | satisfied | `views.py:960-992`; `test_ask.py:791`; three-attempt count asserted at `apps/ai/tests/test_generation.py:190,361` |
> | CRUD: read ContentChunks, Documents, Meetings; create SearchLogs, QueryLog, AnswerCitations | satisfied | `search.py:496-500`; `query_log.py:243-280` |
>
> ### Clause coverage — FR-13
>
> | Clause | Status | Evidence |
> |---|---|---|
> | Interface reachable from any page | satisfied (it is a nav link) | `App.jsx:67` |
> | …retaining the thread so follow-ups need not restate the subject | **partial** | The thread lives only in component state (`Ask.jsx:129-130`), with no URL or storage persistence. See gap 3. |
> | Previous conversations listed and reopenable | **partial** | `views.py:1031-1039,1086-1092` work. Reopened citations cannot expand and there is no Sources panel (see FR-12 above). |
> | Active thread can be cleared for a new topic | satisfied | `Ask.jsx:291-300` |
> | Context kept per session; prior turns passed with the new question | **partial** | Only prior questions are passed, never prior answers (`conversation.py:123-179`, D-42). A follow-up that refers to something in the previous answer does not resolve. |
> | Validation: context truncated to a maximum number of prior turns | satisfied | `constants.py:82`; `conversation.py:154`; `test_conversation.py:439` |
> | Validation: scope re-evaluated on every turn | satisfied | `pipeline.py:431`; `test_fr11_scoping.py:606,631` (same cookie, role changed by UPDATE) |
> | Each turn does a fresh retrieval | satisfied | `test_conversation.py:572` |
> | Generation and verification follow FR-12 unchanged | satisfied | Same `answer_question` path; `test_conversation.py:612` |
> | Responses: 200 with the answer and updated conversation state | satisfied | `answers.py:175-177`; `serializers.py:520`; `test_ask.py:842` |
> | CRUD: Conversations (Create, Read, Update); QueryLog (Create) | satisfied | Create `views.py:1041-1055`; Read `:1031,1086`; Update happens server-side through the title (`views.py:899-914`) and `last_updated_at` (`query_log.py:287`). The database operation exists; there is no PATCH route (D-43). |
>
> ---
>
> ### Missing or partial
>
> 1. **FR-11/12/13: §8 condition 5 fails.** This audit reports gaps, so condition 5 fails whatever else is fixed.
> 2. **FR-11/12/13: §8 condition 4 fails.** Commit `116a422` ("fix(item 1c): separate a destroyed provenance record from a re-scoped turn") changes FR-12/FR-13 behaviour in `serializers.py` and `Answer.jsx` and has no FR ID anywhere in its message. D-59 lists the other two, `72c26ed` and `96b4bbe`. D-60 records this as declined, and the commits are now on `main`. It cannot be fixed.
> 3. **FR-13 "retaining the thread" (plus FR-12's citation link): not recorded anywhere in the repo.** `Ask.jsx:129-130` holds `conversationId` and `turns` in `useState` only, and nothing uses the URL or storage. The citation's own "View document/meeting" link (`Answer.jsx:54-58`, a same-tab `<Link>`) unmounts the Ask screen. Pressing Back returns to an empty conversation. The only way back is to reopen the thread from the list, and then its citations no longer expand (gap 4). That is the exact flow an assessor will try. I found no mention of this in `docs/` or `frontend/`.
>    - Smallest fix: put the active thread in the URL (`/ask?c=<id>`) and on mount call `fetchConversation`. Or open source links in a new tab as a stopgap.
>    - Severity: §8 gap, high demo risk.
> 4. **FR-12 citation expansion, link and Sources panel on a reopened thread.** `GET /api/conversations/{id}` returns statements with no passages and no sources (`serializers.py:744-755`, `turns.js` `savedTurnFrom`).
>    - The clause audit says "Owner: Stage 5", but no Stage 5 item in `M6-BUILD-PROMPT.md` names it. I grepped for reopen, D-48, D-58 and expand, and the only hit is item 11's field walk.
>    - Fix: for each surviving citation, return its passage text and source title/date, taken from the same `permitted_citation_chunk_ids` result (`serializers.py:550-566`) so it is re-scoped on read.
>    - Severity: §8 gap.
> 5. **FR-12 traceability (D-48).** `apps/retrieval/models.py:114-116` has `AnswerCitation.chunk` as `on_delete=CASCADE`.
>    - Reprocess can be run by an Employee: `views.py:863` needs only `contribute_content`, and `views.py:870` blocks only already-Indexed documents, so a "Partially indexed" document that has cited chunks can be reprocessed. `manage.py reindex` does the same damage.
>    - Project memory already calls for pinning FLM to v0.9.39 and re-indexing, and any provider switch is a mandated re-index (CLAUDE.md §4). So this is likely to happen before the demo.
>    - No Stage 5 item owns it.
>    - Fix: a migration adding `SET_NULL` plus a stored `chunk_uuid` and passage-text snapshot on `AnswerCitation`.
>    - Severity: §8 gap.
> 6. **FR-12 partial matches (D-56).** `partial_matches.py:119-148` has no relevance floor, so on an off-topic question it offers five unrelated titles as "partially related". Stage 5 item 6 owns this. Severity: §8 gap.
> 7. **FR-12 "input is sanitised before use" (D-45).** The code deliberately does not do what the clause says. The argument is defensible (parameterised SQL, React escaping, delimiter neutralisation), but it has to be presented to the assessor as a deviation, not as ✅. Prose injection through a document body is open and can be triggered by an Employee. It cannot widen scope (D-49). Severity: §8 gap (low).
> 8. **FR-13 "passes prior turns" (D-42).** Only questions are passed, so a follow-up that refers to something in the previous answer does not resolve. This is a deliberate narrowing. Severity: §8 gap (low).
> 9. **No automated evidence for any front-end clause.** That covers FR-12's search field, grouping, citations, expansion, links, Sources panel, no-answer state and partial-match label; FR-13's thread, list, reopen and clear; and invariant 6 at the interface. There is no runner (D-25). Gap 3 is exactly the kind of defect this lets through. Stage 5 item 4 owns it. Severity: §8 gap (evidence).
> 10. **D-53 fail-open.** `answers.py:261-280` resolves titles with no source-side predicate, and the prompt trusts the chunk stamp alone. `search.py:456-469` does the opposite and fails closed. Today this is reachable only through `bulk_create(update_conflicts=True)` or raw SQL, and no shipped route uses either (I grepped). Stage 5 item 1 owns it. Severity: minor.
> 11. **Minor disclosure through the provenance state.** `serializers.py:710-716` shows state 3 regardless of scope. A reader demoted since asking can therefore tell whether a source now outside their scope has been reprocessed or re-indexed (state 3) or not (state 2, silent). That leaks a maintenance event on restricted material, not its content, and they were entitled to the answer when they asked. Severity: minor.
> 12. **D-58.** An unused "New conversation" can outlive the session that created it. No Stage 5 item owns this. Severity: minor.
> 13. **Duplicated constants.** `frontend/src/constants.js:109-111` restates 2, 10 and 500 outside `apps/core/constants.py`, and no test catches drift. `apps/api/views.py:121` has a literal "50 MB" in a message (FR-08). Severity: minor.
> 14. **§7 branch naming.** The branch is `feat/M5-retrieval-and-generation`, not per-FR as §7 requires. Severity: minor.
>
> ### Invariant check
>
> 1. Filter before ranking, no disclosure: **pass.** I checked `/api/ask` (all three exits), `/api/search` (both the body branch and the title branch), `/api/conversations*` (owner check plus re-scope on read), `/api/documents/{id}`, `/api/meetings/{id}` and reprocess. Every one is scoped in the query, and out-of-scope ids return 404, never 403. The latent risk is gap 10.
> 2. Denormalised stamp plus cascade: **pass.** Covered by `save()`/`update()`/`bulk_update`. The `bulk_create` upsert hole is pinned by a test and not reachable from any shipped code.
> 3. Role, not attendance: **pass.** `MeetingAttendees` is never consulted under `apps/retrieval`; tests at `test_fr11_scoping.py:881,913,943`.
> 4. Server-side authorisation, 401/403: **pass.**
> 5. Verification is set membership: **pass.**
> 6. No uncited statement shown: **pass at the API, unverified at the UI.**
> 7. Two no-answer paths logged separately: **pass.**
> 8. A failed AI step discards nothing: **pass** for this slice (an outage writes no row and deletes nothing).
> 9. Atomic writes: **pass.** QueryLog and its citations commit in one transaction (`query_log.py:242`).
> 10. Structured output or 503: **pass** (`generation.py:95-121`).
> - No AI SDK import outside `apps/ai/`: **pass** (I grepped the whole repo).
> - Every chunk write records model and dimension: **pass.** There is one write site, `apps/ingestion/embedding.py:78-89`.
> - Constants: **pass** on the Python side; front-end duplication is gap 13.
>
> ### Set-level notes
>
> - **No deployment exists** (only a DB `docker-compose.yml`), and FLM runs on one laptop's NPU. A "deployed alpha" of FR-11/12/13 either means that laptop is the host, or it means switching to `anthropic`. A switch is a full re-index, which triggers gap 5 and breaks D-40's rule of no re-index before the demo. Decide the deployment topology now, not at Stage 5 item 9.
> - **Demo risks outside the clauses:** D-40 (answers change between identical runs near the threshold), p90 of 8.90 s against NFR-08's 4 s, and `RELEVANCE_THRESHOLD`/`MAXIMUM_CONTEXT_TOKENS` still provisional.
> - **FR-03 lockout** is already implemented (`views.py:220-260`). That is SHOULD-tier effort spent before FR-14 and FR-15 exist. Do nothing more on FR-03, FR-07 or FR-10 until the twelve are demonstrable.
>
> ### Gate impact
>
> None of these gaps stops FR-11, FR-12 or FR-13 being demonstrated locally today. Gap 3 is the one an assessor is most likely to hit live, and it is about a day's front-end work. Gaps 4 and 5 need a contract change and a migration and have no Stage 5 owner, so add them to Stage 5 explicitly or they will surface at item 10. None of the three can be claimed "done" under §8: condition 4 is permanently declined and condition 5 fails.
>
> ---
>
> ## VERDICT
>
> | Requirement | §8 done | Failing conditions | M6-demonstrable |
> |---|---|---|---|
> | FR-11 | **No** | 4 (declined, D-60), 5 (this audit) | **Yes, locally.** Not yet on a deployed alpha, because none exists. |
> | FR-12 | **No** | 1 (partial: traceability, partial-match floor, sanitisation deviation, reopened-thread citations), 4, 5 | **Yes, locally,** with D-40, latency and re-index risks |
> | FR-13 | **No** | 1 (partial: prior questions only, thread not kept across navigation, reopened citations inert), 4 (includes `116a422`), 5 | **Yes, locally.** The navigation defect is visible if a citation link is followed. |
>
> Every gap:
> 1. §8 condition 5 fails for FR-11/12/13 because this audit reports gaps. **§8 gap**
> 2. §8 condition 4: `116a422` (plus `72c26ed`, `96b4bbe` per D-59) has no FR ID in its message; declined in D-60. **§8 gap**
> 3. `frontend/src/pages/Ask.jsx:129-130` with `frontend/src/components/Answer.jsx:54-58`: the active thread is lost on any navigation, including following a citation link. Not recorded anywhere. **§8 gap, high demo risk**
> 4. `apps/api/serializers.py:744-755` and `frontend/src/utils/turns.js` (`savedTurnFrom`): reopened turns have no passage expansion, no source link and no Sources panel. No Stage 5 owner. **§8 gap**
> 5. `apps/retrieval/models.py:114-116`: `CASCADE` destroys citations on reprocess (Employee-reachable, `apps/api/views.py:863,870`) and on reindex (D-48). No Stage 5 owner. **§8 gap**
> 6. `apps/retrieval/partial_matches.py:119-148`: no relevance floor (D-56). **§8 gap**
> 7. `apps/retrieval/pipeline.py:75-88` and `apps/ai/prompting.py:204`: "input is sanitised" deliberately not done (D-45); prose injection open. **§8 gap (low)**
> 8. `apps/retrieval/conversation.py:123-179`: prior questions only, not prior turns (D-42). **§8 gap (low)**
> 9. No front-end test runner, so every FE clause of FR-12/13 and invariant 6 at the UI has no automated evidence. **§8 gap**
> 10. `apps/api/answers.py:261-280`: fails open against `apps/retrieval/search.py:456-469`, which fails closed (D-53); not currently reachable. **minor**
> 11. `apps/api/serializers.py:710-716`: provenance state reveals reprocess/reindex events on out-of-scope sources to a demoted reader. **minor**
> 12. D-58: orphaned empty threads; no Stage 5 owner. **minor**
> 13. `frontend/src/constants.js:109-111` duplicates tuned constants; `apps/api/views.py:121` has a literal "50 MB". **minor**
> 14. Branch `feat/M5-retrieval-and-generation` breaks the §7 per-FR branch convention. **minor**
> 15. Deployment topology for the FLM-backed alpha is undecided; switching provider forces a re-index and triggers gap 5. **Gate risk (set-level, Stage 5 item 9)**
>
> **Stage 4 is INCOMPLETE:** the permission boundary holds, but none of FR-11, FR-12 or FR-13 meets §8, and gap 3 sits on the path the assessor will walk.

## D-62 · A front-end test runner lands, and the interface stops being accepted as untested

**Status:** Settled by the user · **Date:** 2026-09-28 · **Closes:** D-25's "Still open,
for the team" (`docs/stage-4-clause-audit.md` cites it as "D-25, audit finding 8"),
D-33's "Still open" bullet, and D-61's gap 9 · **Answers:** Stage 5 item 4 ·
**Commits:** `ec6f39b` (runner and CI job), `7b4dc33` (tests), `9d04f3c` (`CLAUDE.md` §8)

**The fork is decided.** Stage 5 item 4 offered two defensible outcomes: land a runner,
or record that invariant 6 is verified at the API boundary only and accept the
interface as untested. The runner landed. **The alternative is declined, not left
open.**

**What landed.**

- Vitest 5.0.2, `@testing-library/react` 16.3.3 with its `@testing-library/dom` 10.4.2
  peer, and jsdom 30.1.1, at the versions npm resolved against Vite 8.3.0 and React
  19.3.0. Configured in `frontend/vite.config.js`. `npm test` runs `vitest run`.
- A `frontend` job in `.github/workflows/ci.yml`, beside `backend`: Node 24, `npm ci`,
  lint, build, test.
- `frontend/tests/setup.js` stubs `fetch` and `XMLHttpRequest` before every test.
  These are the only transports `src/api/client.js` uses. Every call that reaches
  them is recorded, and the test fails in `afterEach`. Refusing the call is not
  enough on its own: `request()` turns a transport failure into an ordinary
  `ApiError`, so a refused call would otherwise show as a normal failure state and
  the test would pass. This is the front-end version of `conftest.py`'s
  `no_live_provider`.
- Tests mock at `fetch` (`frontend/tests/fakeApi.js`), beneath the API client. The
  client's own 503 message, `ApiError` and JSON handling therefore run as shipped.
  They live in `frontend/tests/`, outside `src/`.

**What the suite covers.** Each test was shown to fail against a mutation of
`frontend/src` that broke its property. The mutations are listed in `7b4dc33`'s
message.

| Test | Defends |
|---|---|
| a rejected statement renders nothing at all | invariant 6: a reply given leaked `rejected_statements`, `rejected_count` and `no_answer_reason` renders byte-identically to the same reply without them |
| the no-answer state renders `NO_ANSWER_MESSAGE`, identically on path A and path B | invariant 7 at the screen, and `TEXT.noAnswerFallback` agreeing with `apps/core/constants.py`, which the test reads rather than copies |
| a re-scoped turn renders the no-answer state | invariant 1 on a reopened thread (D-48): not blank, not `provenanceRemovedTitle`, no wording about removal, withholding, restriction or permission |
| a 503 renders the NFR-19 notice | the `alert` notice, the client's 503 text, `askNotRecorded`, and the question kept in the field |
| an arriving answer is acknowledged visibly | usability finding 1: the `role="status"` text is on the page, with no `visually-hidden` class or `hidden` ancestor |
| `canReprocess` is false for "Too large to index" | D-51's regression |
| the withdrawn sentence is absent from `frontend/src` | D-60's shipped string, "Ask the question again for an answer from the current material." |

**What it does not cover.** Per the rule at the head of this file, as a list. The suite
tests the behaviours in the table above and nothing else. It is not coverage of
`frontend/src`, and no coverage is measured or targeted.

- **Any file under `frontend/src` that none of the tests above renders or imports.**
  That takes in every file in `src/pages/` except `Ask.jsx`: `AccessDenied`,
  `DocumentDetail`, `DocumentRepository`, `Home`, `Login`, `MeetingDetail`,
  `Meetings`, `Register`, `RoleManagement`, `Search` and `Upload`. It also takes in the
  `RequireAuth` and `RequireRole` guards, and every component the Ask screen does not
  mount.
- **FR-12 and FR-13 front-end clauses outside the table**, each graded "satisfied" or
  "partial" by reading code in D-61: the search field on every page; results grouped
  by type with a count; a citation expanding to its passage; the link to the source;
  the Sources panel listing every item consulted with its date; partial matches
  labelled as such; the two-character search minimum; the assistant reachable from
  any page; the thread retained across follow-ups; previous conversations listed and
  reopenable; the thread cleared for a new topic.
- **A malformed `statements` entry.** The invariant 6 test covers fields a reply
  should not carry. It does not cover a statement inside `statements` that has no
  `chunk_id`, or one whose `chunk_id` is not among the passages in `sources`.
  `Answer.jsx` renders that statement with a plain citation number. The server is
  the only defence there.
- **The provenance-removed state.** Nothing renders it. Nothing checks that
  `TEXT.provenanceRemovedFallback` agrees with `PROVENANCE_REMOVED_MESSAGE`, although
  the comment on that constant in `src/constants.js` names a runner as the thing
  that would.
- **The repository row's use of `canReprocess`.** The test calls the function. It
  does not render a "Too large to index" row and check that no retry button
  appears. `statusMessageFor`, and `canReprocess` for other statuses, are untested.
- **Other withdrawn text.** The string check covers the D-60 sentence only, and
  `frontend/src` only, not `frontend/dist`. D-27's earlier no-answer wording, "No
  answer could be found in the material you have access to.", is not checked.
- **Styling.** jsdom applies no stylesheet. The acknowledgement test would not catch
  a CSS rule that hid the status line, and nothing checks contrast or focus
  appearance. Those belong to Stage 5 item 7.
- **Transports other than `fetch` and `XMLHttpRequest`.** `WebSocket`, `EventSource`
  and `navigator.sendBeacon` are not stubbed. `src/` uses none of them.
- **Roles.** The front-end tests run no session, so §8's dual-role requirement stays
  with `pytest`, where the server enforces it.
- **D-61's gaps 3 and 4** (the thread lost on navigation, reopened turns that cannot
  expand). They are neither tested nor fixed.

**The standard moves with the runner.** `CLAUDE.md` §8 condition 2 read "`pytest`
passes". A front-end test could not satisfy that wording and it could not demand
one, so the definition of done excluded the interface from Stage 2 until this item.
`9d04f3c` rewrites the condition to require pytest and the front-end suite, and to
test in the front-end suite any clause that only the interface can satisfy.
**Under the amended wording, the FR-12 and FR-13 clauses listed above do not meet
condition 2.** The amendment raises the bar. It does not reach back and pass
anything. It sits beside D-60's record of conditions 4 and 5 and does not change it.

**Verified locally only.** `npm run lint`, `npm run build` and `npm test` pass on Node
24.16.0 on the development machine. The `frontend` CI job has not run on GitHub as of
this entry, because nothing on this branch has been pushed.

> **2 November 2026: this entry's list of what the front-end suite does not cover is superseded**
> (item 10's H3, D-90).
>
> - **What changed since.** `documentRepository.test.jsx` tests DocumentRepository and
>   DocumentDetail, `askReopened.test.jsx` renders the provenance-removed state, and D-77 and D-78
>   fixed and tested D-61's gaps 3 and 4.
> - **The current list** is `docs/demonstration-script.md`'s "What is not verified by any test",
>   derived from `frontend/tests` on 2 November. Step 6 (D-94) writes the full enumeration, clause
>   by clause, to `docs/stage-5-front-end-clauses.md`, and that file supersedes both.
> - **What stands:** this entry's amendment of CLAUDE.md §8 condition 2.

## D-63 · FR-15's detail view shows extracted content after all; D-52's reasons for cutting it were false

**Status:** Settled by the user · **Date:** 2026-09-28 · **Supersedes:** D-52 ·
**Concerns:** FR-15 · **Owner:** Stage 5 item 2

**Decision.** The document detail view shows the whole of FR-15's clause — "its
metadata, extracted content, and a download link". The extracted content is read from
`ExtractedContent.extracted_text` and carried on the existing `GET /api/documents/{id}`
response, because that route is already scoped to the caller's role and already
answers 404 outside scope (D-46). It is never reassembled from chunks.

**Why D-52 is superseded.** Its cost argument rested on statements that were false
when it was written:

- *"The stored form of extracted text is `ContentChunk.chunk_text`"*, so that showing
  it would need de-overlapping on read, or a new column and a migration.
  `ExtractedContent` has held each document's whole extracted text since Stage 3:
  `apps/ingestion/documents.py:243` writes it at ingestion — "stored separately from
  the original so that search and AI processing never require the document to be
  parsed a second time" — and `manage.py reindex` re-embeds from it.
  `docs/schema-v1.md` tags the table FR-15. Honouring the clause is a scoped read of a
  table that already exists.
- *"The download link, which is FR-15's third part and is built."* No download route
  exists in `apps/api/urls.py` or `apps/api/views.py`; it is Stage 5 item 2a. The
  same sentence's "its storage path depends on D-18" was stale as well:
  `docs/schema-v1.md` records G7 closed on 21 September by
  `documents 0006_schema_v2_storage_and_status`.

D-52 was drafted from the chunk model without reading the ingestion path or the
routes. Searching `apps/` for `ExtractedContent`, and `apps/api/` for a download
route, shows each error above. The cut was settled on the
cost D-52 stated. With the cost corrected, the user restored the clause.

**What follows.**

- Extracted text is a document's whole content. Reading it is exactly as sensitive as
  downloading the file, so it travels only on the scoped route, and a test asserts
  that an Employee asking for an Administrator-only document receives 404 and no text.
- It is rendered as text, never as HTML. It is untrusted input.
- A document with no `ExtractedContent` row shows a stated empty state. The view keys
  on the row existing, not on the document's status: which statuses leave a row is a
  fact of the ingestion path, and D-52 enumerated them by status without reading it.
- FR-15's deletion removes the row through its `CASCADE` foreign key. The document's
  chunks and tags have no foreign key and need application code (D-07); Stage 5
  item 2 carries that.
- The response shape changes, so `docs/api-contract.md` changes in the same commit.
- The detail-view clause is audited on its evidence. D-52's instruction to mark it
  declined no longer applies.

**What this decision does not cover.**

- **The download link.** Stage 5 item 2a builds it; nothing here does.
- **Formatting fidelity.** Extracted text is plain text. A PDF's layout, a DOCX's
  headings and an XLSX's cell grid are not reproduced, and nothing here promises
  that they are.
- **Meetings.** FR-15's detail clause is about documents. Nothing here changes the
  meeting view.
- **Length.** A long document yields long text. Whether the view truncates, pages or
  collapses it is a presentation choice for item 2; it reads the text from the scoped
  route and from nowhere else.

## D-64 · The M6 alpha is hosted on the NPU laptop and reached on that laptop, over loopback

**Status:** Settled by the user · **Date:** 2026-10-05 · **Scope:** the M6 alpha only ·
**Answers:** `M6-BUILD-PROMPT.md`'s "decide how the alpha is hosted before item 3", and
D-61's gap 15 · **Implemented by:** Stage 5 item 9, not by this entry

**Decision.** The M6 alpha runs on the laptop whose NPU serves FLM, and an assessor uses it
on that laptop: in person, or with its screen projected. The built SPA and `/api` are served
from one origin on loopback (`http://127.0.0.1`), in production mode:

- `DEBUG=False`;
- the production build of the front end (`frontend/dist`), not the Vite development server;
- Waitress as the WSGI server.

**It replaces the proposal's deployment for the alpha, and only for the alpha.** The
proposal's deployment section specifies a Google Cloud Compute Engine VM on Ubuntu 22.04,
with Django under Gunicorn behind Nginx, and Nginx terminating TLS (NFR-03) and serving the
compiled bundle. The alpha cannot run there, because FLM runs only on this laptop's NPU
(D-35, D-36) and there is no budget for the `anthropic` provider, so no switch is coming.
Gunicorn does not run on native Windows, and native Windows is the only place the NPU is
visible (`docs/ai-provider.md` §3). Waitress does run there.

**The settings stay environment-driven, with loopback defaults**, so that serving the same
build over HTTPS later is a `.env` change and not a code change:

| Setting | Default for this decision | Today |
|---|---|---|
| `ALLOWED_HOSTS` | `127.0.0.1,localhost` | already env-driven with this default (`config/settings.py`) |
| `CSRF_TRUSTED_ORIGINS` | the loopback origin(s) | not set; item 9 adds it |
| `SESSION_COOKIE_SECURE` | `False` | not set; item 9 adds it |
| `CSRF_COOKIE_SECURE` | `False` | not set; item 9 adds it |

**What this decision covers:**

- how an assessor reaches the M6 alpha: on the laptop;
- the server and mode it runs in: Waitress, `DEBUG=False`, the built SPA, and one origin, so
  D-21's single origin is kept in the deployment as well as in development;
- the defaults of `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SESSION_COOKIE_SECURE` and
  `CSRF_COOKIE_SECURE`, and the fact that each is read from the environment.

**What it does not cover:**

- **The M8 final deployment (27 November).** Where the delivered system is hosted for M8 is
  a separate decision, to be taken later. Nothing here commits M8 to loopback, and nothing
  here withdraws the proposal's GCP design for it.
- **NFR-03, encryption in transit.** Its verification is "an SSL/TLS scan … against the
  deployed application", and a loopback alpha serves no TLS, so there is nothing to scan.
  The scan moves from NFR verification round 1 to round 2. The user named that as timeline
  task 2.24. The task list is not in `proposal.txt` or anywhere in this repository, so this
  entry cannot quote it.
- **How one origin is achieved**: Django with a static-files layer and a catch-all for
  client routes, or a reverse proxy in front of both. Item 9 decides that. Either way
  `/api/` must keep answering its own JSON 404s.
- **Throttling `/api/ask` and the ingestion POSTs.** That is item 5. D-49's 900-second
  worst case argues against `manage.py runserver`, and Waitress answers that argument only
  in part: one request can still hold one of its threads for that long.
- **Open registration.** Item 9 notes that FR-01 is open to anyone with the address if the
  alpha is reachable beyond the laptop. Under this decision it is not reachable beyond the
  laptop, so the point does not arise. It returns with any later decision that exposes the
  service, including a tunnel or a LAN address.

**Consequences.**

- D-61's gap 15, "deployment topology undecided", is answered as a decision. The
  configuration is still unbuilt and belongs to item 9.
- The demonstration needs no network, which matches D-35 and `docs/ai-provider.md` §7.
- Exposing the alpha later means setting `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`,
  `SESSION_COOKIE_SECURE` and `CSRF_COOKIE_SECURE` in `.env`, and putting something in front
  that terminates TLS. That is a new
  decision with the registration question attached, not an edit to this one.

> **1 November 2026: item 9 built the configuration, with Django serving the build.** The brief
> allowed either Django with a static-files layer and a catch-all, or a reverse proxy in front.
> This is the first, because it adds no second process to the laptop. `docs/alpha-deployment.md`
> is the runbook, and `docs/api-contract.md`'s "Stage 5 item 9" section lists every path's answer.
>
> - **WhiteNoise 6.12.0 serves `frontend/dist` from its own folder** (`WHITENOISE_ROOT`), with no
>   `collectstatic` and no `django.contrib.staticfiles`. It reads the folder at start-up, so the
>   SPA is built before the server starts and a rebuild needs a restart.
> - **`config/spa.py`'s catch-all answers every other path with `index.html`.**
>   - It answers `GET` and `HEAD` only; anything else is a 405.
>   - It leaves out `/api` and `/assets/`. An unmatched `/api/` path keeps its JSON 404, and a
>     missing asset is a 404 rather than HTML served as a script.
>   - With no build, it is the JSON 404, as before item 9.
> - **Caching:**
>   - `index.html` is `no-cache`;
>   - `/assets/` is immutable, because Vite content-hashes those names and `vite.config.js` now
>     writes `assetsDir` out;
>   - everything else gets WhiteNoise's 60 s.
>   - WhiteNoise also serves `/index.html` itself, with the 60 s, but only a typed address reaches
>     it.
> - **Nothing serves `MEDIA_ROOT`.** `/media/...` is a client route, and a test pins it.
> - **JSON 400 and 500 under `/api/`** (`config/errors.py`), with fixed sentences and never the
>   exception. The traceback still reaches the error file (D-75). `handler400` covers the
>   disallowed `Host` that D-85's note left to item 9. Outside `/api/`, Django's pages are
>   unchanged.
> - **The settings this decision names** (`CSRF_TRUSTED_ORIGINS` and both `*_COOKIE_SECURE`) are
>   read from the environment, with the loopback defaults. `DEBUG` already defaulted to `False`.
> - **The build refuses another origin.** `vite.config.js` refuses a `VITE_API_BASE_URL` that is
>   another origin or a relative path, because the SameSite=Lax cookies would then never reach
>   `/api`.
> - **Not covered:**
>   - **The demonstration script that item 9's brief also asks for,** with D-40's conditions. It
>     needs the deployed alpha's database, to screen each question's top-score margin.
>   - **Which database the alpha serves.**
>   - **A path that is neither `/api` nor a client route** shows the SPA's shell with an empty main
>     area, as it does in development.
>   - **`npm ci` reports 5 advisories** (2 moderate, 3 high), which nobody has looked into.

**Dated note, 7 November 2026: M8's hosting is decided.** This entry's scope was the M6 alpha
only, and D-88 left "M8's hosting and database" open. The user has settled the hosting part.

- **M8 is hosted on the NPU laptop, with FastFlowLM,** the same machine as the alpha. The
  proposal's Google Cloud VM cannot run FastFlowLM, which needs the laptop's NPU, and there is no
  budget for the Claude provider (D-35).
- **FastFlowLM stays pinned at v0.9.39** (D-83). Newer releases are evaluated only after M8.
- **Still open:**
  - which database M8 serves;
  - whether M8 stays on loopback as the alpha does, given that registration (FR-01) is open to
    anyone who can reach it;
  - how NFR-03's TLS scan is met. This entry put HTTPS out of scope for the alpha, and moved that
    scan to round 2.

**Dated note, 10 November 2026: the 7 November note's hosting is superseded by D-114.** M8 can be
hosted on any device with the platform in place. The note's reason, that FastFlowLM needs this
laptop's NPU and there is no budget for Claude, fell with D-113. The laptop with FLM remains one
valid host. The three open points above stay open, and D-114 restates them. This entry's M6 alpha
decision is unchanged.

## D-65 · Every query parameter passes a DRF serializer; D-54 is settled

**Status:** Settled by the user · **Date:** 2026-10-05 · **Settles:** D-54 · **Stage:** 5
item 1 · **Concerns:** FR-14's and FR-15's filters, and every later route that reads a
query parameter

**Decision.** A view reads its query parameters by passing them to a DRF `Serializer`, as
`SomeQuerySerializer(data=request.query_params)`, and uses only `validated_data`. No view
reads `request.query_params` or `request.GET` into an ORM lookup itself. The NUL-byte class
that D-54 left open is then closed at the request boundary for each new parameter rather than
inside one function: DRF's `CharField` carries `ProhibitNullCharactersValidator`, and a NUL
byte is not a valid date, UUID or choice either.

**How each kind of parameter is declared:**

| Parameter kind | Field | Validated against |
|---|---|---|
| A fixed vocabulary from `apps/core/constants.py`: `status`, `sort` | `ChoiceField` over the constant | the constant |
| `department`, a tag name | `CharField` with a `max_length` constant | shape only |
| a tag identifier | `UUIDField` | shape only |
| a date range | `DateField` for `date_from` and for `date_to` | shape, plus the cross-field rule below |

**`ChoiceField` only for fixed vocabularies, and never a lookup against the database.**
Department and tag values are checked for shape and never checked for existence. An
unknown department and a department used only on restricted content must give the same
answer, which is FR-15's 204 for a filter combination with no accessible matches. A field
that looked the value up would answer 400 for one and 204 for the other, and the status code
would tell the caller whether restricted material carries that department. That is the
existence oracle invariant 1 forbids, at the validation layer instead of the query.

**Date ranges.** `validate()` rejects `date_from` later than `date_to`. The end date is
inclusive, so `date_to` filters with `__date__lte`, and a range of one day returns that day's
items.

**The 400 is a convention, recorded as one.** Neither FR-14 nor FR-15 lists a 400 among its
Responses. A malformed parameter is answered 400 in DRF's usual body, keyed on the parameter's
own name, the same shape every other 400 in this API uses. The status code comes from this
API's convention for a malformed request, and is not read out of either requirement.

**Enforced by a test, not by this entry.**
`apps/api/tests/test_query_parameters_pass_a_serializer.py` parses every production module
under `apps/` and fails on any read of `.query_params` or `.GET` that is not the `data=`
argument of a call to a `…Serializer`. The test is shown to fail on a direct read before it
is trusted to pass.

**What this covers:** every query parameter read by a view under `apps/`, from Stage 5 item 1
onwards, including FR-14's date range and department and FR-15's department, tag, status,
sort and text filter as each lands.

**What it does not cover:**

- **`q` on `GET /api/search`.** It is the one named exception to the test, at
  `apps/api/views.py` `SearchView.get`. Stage 4 item 12a closed it inside
  `apps/retrieval/search.py` with its own exception and message, and moving it onto a
  serializer would replace a tested message with DRF's generic one for no gain in safety.
- **Request bodies.** Those already pass serializers.
- **Path parameters.** Django's `<uuid:pk>` converter refuses anything that is not a UUID
  before a view runs.
- **Headers and cookies.** No view reads one into an ORM lookup.
- **What a filter does once it is valid.** Scoping, counts and the 204 are item 2's and item
  3's work, and they are tested there.

**D-54's status changes from Open to Settled by this entry.** D-54 itself is left as written.

## D-66 · Administrator generalises Employee in scope as well as in permissions

**Status:** Settled by the user · **Date:** 2026-10-05 · **Stage:** 5, after item 1, in item
1's helpers · **Concerns:** FR-11, and through it FR-12, FR-13, FR-14 and FR-15 ·
**Supersedes:** the reading in `apps/retrieval/scoping.py` that membership of the reader's own
role is the whole scope test

**Decision.** A role reads every row whose `visible_to_roles` overlaps that role's
**effective roles**, set by `EFFECTIVE_ROLES` in `apps/core/constants.py`:

| Role | Effective roles |
|---|---|
| Employee | Employee |
| Administrator | Administrator, Employee |

`scoped_chunks`, `scoped_documents` and `scoped_meetings` test overlap
(`visible_to_roles__overlap`) instead of membership of the single role name
(`visible_to_roles__contains`). The change is in item 1's helpers and nowhere else, so every
caller inherits it.

**Why.** The proposal's role model makes Administrator a generalisation of Employee. Its
use-case diagram draws `Employee <|-- Admin` with the note "each role adds capability to the
one below", and `docs/schema-v1.md` says "Administrator generalises Employee". The build
applied that to permissions (accounts 0003 and 0004, whose tests assert Administrator's
permissions are a superset of Employee's) and not to scope. `apps/retrieval/scoping.py` said
outright that "an Administrator does not implicitly see Employee-scoped content".

That reading made an `["Employee"]` document invisible to every Administrator: absent from
the repository list and 404 on detail. Under FR-15's scoped-first deletion, which is 404
outside scope and 403 after that, no Administrator could ever delete it. The question came up
when `manage_documents` was settled as Administrator-only, together with the requirement that
no document be undeletable.

**What does not change:**

- **An Employee's scope, by construction.** Their effective roles are `Employee` alone, and
  overlap with a one-element list is the membership test it replaces.
  `test_an_employees_scope_is_exactly_the_content_marked_for_employees` asserts it for
  documents, meetings and chunks.
- **D-29.** D-29 settles what ingestion *writes* into `visible_to_roles` (both roles by
  default, 400 for an empty list, 403 for a list excluding the uploader's role). This entry
  settles how scope is *read*. D-29 stands as written.
- **The stored arrays.** There is no data migration. Documents, meetings and chunks carry the
  arrays they carried, so D-47's cascade and D-53's source/chunk agreement are untouched.
- **FR-15's deletion order.** Scoped-first, as Stage 5 item 2 says: 404 outside scope, then
  403 without `manage_documents`. Because an Administrator's scope now includes every
  Employee-only document, the delete control works from the interface as well as the API.
- **Meetings are still scoped by role, never by attendance** (D-16).

**What this covers:** every read through `scoped_chunks`, `scoped_documents` and
`scoped_meetings`. Today those are `POST /api/ask` (candidate set, Sources panel, partial
matches), `GET /api/search`, the document list, detail and reprocess routes, the meeting list
and detail routes, and the re-scope of a reopened thread (`permitted_citation_chunk_ids`).
FR-14 and FR-15 inherit it as they land.

**What it does not cover:**

- **D-29's upload refusal.** An Administrator uploading with `visible_to_roles=["Employee"]`
  is still refused 403, because the check compares the uploader's own role name with the list.
  D-29's reason, "uploading into a scope you cannot read is how content is lost", no longer
  holds for an Administrator under this entry, so that check is now stricter than its reason.
  It is left as it is: this entry changes reads and not what ingestion accepts.
- **A third role.** A role missing from `EFFECTIVE_ROLES` reads nothing, which fails closed.
  Adding a role means adding its row here.
- **A renamed role.** D-11's limitation stands, now in `EFFECTIVE_ROLES` as well as in the
  stored arrays.
- **Permissions.** FR-05 and FR-06 read `RolePermissions` and are unchanged.
- **Records written before this change.** `QueryLog` and `AnswerCitation` rows record what
  was answered under the old reading. A reopened thread is re-scoped on read, so an
  Administrator reopening an old turn now sees anything Employee-only it cites. Nothing is
  rewritten.

**Consequences.**

- `test_the_scope_is_symmetrical_no_role_generalisation` asserted the old reading and is
  replaced by two tests, one per role, in `apps/retrieval/tests/test_scoping.py`. Every other
  test that assumed an Administrator could not read Employee-only content is listed in the
  commit that lands this entry, with what each now asserts.
- FR-11 is still demonstrated by role, but in one direction only: Administrator-only material
  withheld from an Employee. An Administrator now sees everything an Employee sees, and more.
- `apps/retrieval/scoping.py` carries a dated note of the reading it replaced.

## D-67 · `AnswerCitation.chunk` is SET_NULL, `chunk_uuid` keeps the identifier, and no passage text is stored

**Status:** Settled by the user, in the Stage 5 brief (`M6-BUILD-PROMPT.md` item 1a) · implemented
2026-10-05 · **Date:** 2026-10-05 · **Stage:** 5 item 1a · **Concerns:** FR-12's traceability
clause, and through it FR-13's reopened thread and FR-15's deletion · **Supersedes:** D-12's
"`AnswerCitations` with its query or its chunk", for the chunk only; and D-48's 27 September
qualification where it says the change "is not being made before M6" · **Closes:** D-61's
gap 5

**Decision.**

- `AnswerCitation.chunk` is `ForeignKey("documents.ContentChunk", null=True,
  on_delete=SET_NULL)`.
- `AnswerCitation.chunk_uuid` is a NOT NULL `UUIDField` holding the identifier of the chunk
  the statement cited. `record_query` writes it with the same UUID as `chunk_id`.
- Retrieval migration `0003_answercitation_chunk_set_null` does both, and backfills
  `chunk_uuid` from `chunk_id` on existing rows. It is reversible: the reverse deletes the
  citation rows whose `chunk_id` is NULL, which 0002's cascade could never have left behind,
  and touches no other row. The migration's docstring argues why.
- **A citation whose `chunk_id` is NULL is REMOVED for every reader.** It is read exactly as a
  row the cascade had deleted: its statement and its identifier are not shown, it takes no
  citation number, and it does not count as a row when a reopened turn's state is decided.

**Why.** FR-12's traceability clause says "the question, the retrieved chunk identifiers, the
answer and its verified citations are logged, so that any answer can later be traced to the
material that produced it." Under CASCADE that held at write time and not afterwards. These
operations delete chunks, and each destroyed every citation of them:

- `POST /api/documents/{id}/reprocess` (`reprocess_document`), which D-30 opens to every role
  holding `contribute_content`;
- `manage.py reindex`, which `CLAUDE.md` §4 mandates on any provider or embedding-model change;
- FR-15's document deletion, from Stage 5 item 2.

With SET_NULL the row survives the chunk. `chunk_id` goes NULL, because there is nothing left
to point at, and `chunk_uuid` still names what was cited.

**No passage-text snapshot.** D-61's audit proposed `chunk_uuid` plus a snapshot of the
passage text. The snapshot is refused. FR-15 says deleting a document removes its extracted
content, embeddings and tag links "so that deleted material cannot subsequently be surfaced
through search", and a snapshot is that material surviving the delete. Item 4b will return
passage text for reopened turns, so a snapshot would put deleted text back on screen.
Traceability needs the identifier, not the text. The identifier names what was cited and
resolves to nothing once the chunk is gone, and that is intended.

**What a reader sees is unchanged, and is now produced on purpose.** Under CASCADE, removing
the statement happened as a side effect of the row being deleted. It is now a rule in the
serializer, and it is tested. `ConversationTurnSerializer`'s states, after this entry:

| State | Was decided by | Is decided by |
|---|---|---|
| 1, never answered | `answered` false | unchanged |
| 2, re-scoped: silent, identical to state 1 | answered, citation rows exist, none in the reader's scope | answered, some row still points at an existing chunk, none of those in the reader's scope |
| 3, `provenance_removed` | answered, no citation rows | answered, no row points at an existing chunk |

A turn holding a NULL-chunk row beside a row whose chunk exists but is out of scope is state 2,
which is what the cascade produced when the NULL row would have been gone. The discriminator
stays a fact about the record, read before any scoping. `permitted_citation_chunk_ids` skips
NULL identifiers before its scope query, and `surviving_citations` excludes a NULL-chunk row by
name, not by NULL happening to be absent from the permitted set.

**What this covers:**

- the writer: `record_query`, the only production code that creates `AnswerCitation` rows;
- the chunk deletions that reach the column through `QuerySet.delete()`, and therefore through
  Django's `on_delete`: `reprocess_document`, `manage.py reindex` for documents and for
  meetings, and FR-15's deletion once item 2 deletes chunks the same way;
- the readers that exist today: `permitted_citation_chunk_ids` and `ConversationTurnSerializer`
  (`surviving_citations`, `has_live_citation_rows`, `get_provenance_removed`), behind
  `GET /api/conversations/{id}`;
- the tests:
  `apps/api/tests/test_fr12_traceability_survives_reprocess.py` (renamed from
  `test_fr12_traceability_lost_on_reprocess.py`, its docstring recording what it used to
  pin), `apps/api/tests/test_null_chunk_citations_on_a_reopened_turn.py`,
  `apps/retrieval/tests/test_migration_0003_citation_set_null.py`,
  `apps/retrieval/tests/test_models.py::test_citation_survives_its_chunk_with_the_chunk_nulled_and_the_identifier_kept`
  (formerly `test_citation_cascades_when_its_chunk_is_deleted`) and
  `::test_chunk_uuid_is_required`, and the `chunk_uuid` assertions in
  `apps/retrieval/tests/test_query_log.py`.

**What it does not cover:**

- **`QueryLog.retrieved_chunk_ids`** still names deleted chunks by identifier. It always did,
  and it is an array with no foreign key, so nothing nulls it. It now agrees with `chunk_uuid`.
  Before, it was the only trace left.
- **Item 4b's passage expansion and Sources panel on a reopened turn**, which are not built.
  They must treat a NULL chunk as removed: no passage text for it, from anywhere.
- **FR-15's deletion** will produce NULL rows. Item 2 builds and tests that path. This entry
  guarantees only that the rows it leaves are read as removed.
- **`AnswerCitation.statement_text` and `QueryLog.answer_text`** still hold the prose of a
  statement whose chunk was deleted. They are the record of what was answered (FR-19) and no
  reader renders them for a NULL-chunk row. Item 3 shows a user's recent questions only, and
  any new reader of either column must apply the same rule.
- **A chunk deleted outside Django's `on_delete`**: raw SQL, or `QuerySet._raw_delete`.
  `SET_NULL` is emulated by Django, and the database foreign key has no `ON DELETE` action, so
  such a delete fails on the deferred constraint at commit instead of leaving a dangling
  identifier. No shipped path deletes chunks that way.
- **Equality of `chunk_uuid` and `chunk_id` at write time** is not enforced by the database.
  `record_query` is the only production writer and `test_query_log.py` asserts the equality.
  A `CHECK (chunk_id IS NULL OR chunk_id = chunk_uuid)` would make it a database guarantee
  and was not added.
- **Resolving `chunk_uuid` to the chunk that replaced it** after a re-index. No route does
  that, and a re-index need not reproduce the old chunk boundaries.
- **D-61's gap 11** is unchanged. State 3 is shown whatever the reader's scope, so a demoted
  reader can still tell that a source now outside their scope was reprocessed, re-indexed or
  deleted. This entry reproduces the old rendering exactly, gap included.
- **`PROVENANCE_REMOVED_MESSAGE`** is unchanged. Its first clause, "The citations for this
  answer are no longer on record", is now looser than it was, because the citation rows are on
  record and the chunks they cited are not. The copy and the response shape are not this
  item's. Recorded so the next change to the copy can take it up.
- **The migration's reverse** is lossy for the NULL-chunk rows it deletes. Their `chunk_uuid`
  was the only record of what they cited.
- **Front-end comments** still describe the cascade in `frontend/src/constants.js`,
  `frontend/src/utils/turns.js` and `frontend/src/components/Answer.jsx`. The response shape is
  unchanged, so behaviour is unaffected. The wording is react-frontend's to correct.
- **`docs/stage-4-open-items.md` §2.3 and `docs/stage-4-clause-audit.md` row 22** still
  describe the gap as open. They are records as at their dates, and the open-items index says
  its holders win where they disagree with it.

**Consequences.**

- D-12 stands for every other foreign key it set, including `AnswerCitation.query`, which still
  cascades with its query.
- D-48's original sentence, that the stored rows are untouched, is now true of a chunk
  deletion as well as of a re-scope. It is made true with an identifier and no text, rather
  than with the "nullable identifier snapshot" its qualification described.
- Item 2's FR-15 deletion can delete chunks without destroying the FR-12 record. The brief put
  this item before item 2 for that reason.

## D-68 · FR-14's recent questions are the requester's own, and the question only

**Status:** Settled by the user, in the Stage 5 brief (`M6-BUILD-PROMPT.md` item 3) ·
**Date:** 2026-10-06 · **Concerns:** FR-14's "recent questions asked" panel

**Decision.** The recent-questions panel shows the requesting user's **own** `QueryLog` rows,
newest first, and for each one only the question as asked, when it was asked, and the
conversation it belongs to, if any. It returns no answer text, no `answered` flag, no
`no_answer_reason`, no `rejected_count` and no `retrieved_chunk_ids`.

**Why the owner, and not the role.** FR-14 says content is "restricted to items the user's role
permits them to see". For documents, meetings and totals that is role scoping (D-16, D-66). A
question is not content the organisation holds, though. It is something a person typed, and role
scoping would show one Employee every other Employee's questions. That is a disclosure FR-14
does not ask for and no clause anywhere licenses.

**Why the question only.** `QueryLog` is a derived record, and D-48 named its columns among the
fields that carry a permission scope nobody re-derives:

- `answer_text` was generated under the role the asker held at the time, from passages that may
  since have left their scope (D-48's instance 3). Shown on a dashboard, it is an answer nobody
  re-scoped.
- `answered` must be re-derived from the surviving citations, not trusted (D-48's instance 7,
  which `ConversationTurnSerializer` does). A dashboard panel is not the place to re-derive it.
- `no_answer_reason` and `rejected_count` are record-only (D-55, `QueryLog`'s docstring).

The question text itself is the user's own words, which is the reason D-42 passes prior
questions and D-48 keeps them on a reopened thread.

**What this covers:** the `recent_questions` field of `GET /api/dashboard`.

**What it does not cover:**

- **An Administrator's view of everyone's questions.** That is FR-19's knowledge-gap log, COULD
  tier and NIT3004 (D-69). Nothing here builds it.
- **Whether a recent question was answered.** A user who wants that reopens the thread on
  `/ask`, where it is re-derived per turn.
- **One-off questions with no thread.** They are listed like any other, with
  `conversation_id` null, and their panel link goes to `/ask` rather than to a thread.

## D-69 · FR-14's KnowledgeGaps read is deferred with FR-19

**Status:** Settled by the user, in the Stage 5 brief (`M6-BUILD-PROMPT.md` item 3) ·
**Date:** 2026-10-06 · **Concerns:** FR-14's Database clause

**Decision.** FR-14's Database clause lists `KnowledgeGaps (Read)`. The dashboard does not read
it, because the table does not exist. `docs/schema-v1.md` §2 defers `KnowledgeGaps` to NIT3004
with FR-19 (Knowledge Gap Log, COULD), whose verification is Objective 06, due 13 November. That
section's rule is "add these in migration v2 when their requirement is built. Do not create empty
tables now for work that may be descoped."

**Why it is recorded now.** The brief requires this to be a decision before the
requirements-auditor finds it as a gap. A clause the build deliberately does not meet, with a
reason, is a deviation; the same clause unrecorded is a defect.

**What this covers:** the `KnowledgeGaps (Read)` entry of FR-14's CRUD line.

**What it does not cover:**

- **FR-19 itself**, or any gap panel. When FR-19 lands, a dashboard panel reading its table is
  FR-14 work to revisit, scoped as FR-19 then specifies.
- **The evidence FR-19 will read.** `QueryLog` and `SearchLog` already record every question and
  search with its result count (FR-12's gap-evidence clause), so nothing is lost by deferring.

**Dated note, 10 November 2026: FR-19 supplies the table** (D-107). On `feat/FR-19-knowledge-gaps`
the dashboard reads `KnowledgeGaps` for a role holding `review_knowledge_gaps`, which migration
`accounts 0007` gives the Administrator alone: its payload gains `knowledge_gaps`, the number of
Open entries and up to `DASHBOARD_GAP_ITEMS` of them in the list's order. An Employee's payload keeps
its keys. This entry's deferral ends when that branch merges to `main`.

## D-70 · FR-14's filters and totals: department narrows documents, the total counts "Indexed" by type, each type filters on its own date

**Status:** Settled by the user · **Date:** 2026-10-06 · **Concerns:** FR-14's Front-End
filter clause, Server-End validation clause and the "total indexed items" panel ·
**Builds on:** D-65 (how the parameters are read), D-66 (what scope means)

**"Team/department" means department.** Nothing in the schema models a team: `Users` has no team
column and `Documents.department` is the only organisational unit (D-09). The filter is
`department`.

**Department narrows documents only, and the screen says so.** Only documents carry a department.
Meetings have none (`apps/retrieval/search.py`'s `SearchResult` docstring argues why it is not
invented), and a user's questions have none. With a department set:

- the recent-documents panel and the **documents** figure of the indexed total are narrowed;
- the recent-meetings panel, the **meetings** figure and the recent-questions panel are not, and
  the screen states that the department filter applies to documents.

The indexed total is shown **split by type** (documents N, meetings M, and the sum), so the
department visibly narrows only the documents figure, rather than moving a single number in a way
the reader cannot account for.

**The indexed total counts status "Indexed" only.** Documents whose status is `Indexed`, plus
meetings whose status is `Indexed`, within the caller's scope and the active filters. A
`Partially indexed` document is not counted.

**Why FR-14 does not read `ContentChunks`, despite its CRUD line.** Ingestion is atomic
(CLAUDE.md invariant 9, NFR-21). A document or meeting reaches `Indexed` in the same transaction
that writes its chunks, so a source's status already tells you whether its chunks exist.
Counting chunks to answer "how many items are indexed" would be a second, slower route to the
same fact. The CRUD line is satisfied by the status and recorded as deliberately not read.

**Each type filters on its own date, and the total is narrowed by the same range:**

| Panel or figure | Date compared |
|---|---|
| recent documents; documents in the total | `Documents.uploaded_at` |
| recent meetings; meetings in the total | `Meetings.meeting_date` |
| recent questions | `QueryLog.answered_at` |

- `answered_at` is set on every `QueryLog` row, unanswered ones included, so no question drops out
  of a range for not having been answered.
- Timestamps compare by their **Melbourne date**: `TIME_ZONE` is `Australia/Melbourne` and D-65's
  inclusive range is applied with `__date__gte` and `__date__lte`. `meeting_date` is already a
  date and compares directly.
- A transcript added this week for an older meeting falls in the older meeting's range. That is
  accepted, so that the meetings panel and the meetings figure always agree with each other.
- The screen shows the active range.

**Offered values, and why they cannot disclose anything.** The department filter offers the
distinct non-blank departments of the documents in the caller's scope, never the departments of
every document. A department used only on restricted documents would otherwise disclose them by
being offered at all (invariant 1). The offered list is not narrowed by the active filters, so
the control does not change under the user. A department the caller cannot see, or one that does
not exist, gives the identical 200 payload: D-65 validates its shape and never looks it up.

**Landing, links and size.**

- Both FR-02 destinations render the dashboard: `/dashboard` for an Employee and `/admin` for an
  Administrator. The brief requires the dashboard whichever role signs in first.
- Each panel links to its module's own view, which is the proposal's "each panel is a route into
  the module that owns it":
  - recent documents and the documents figure → `/documents`;
  - recent meetings and the meetings figure → `/meetings`;
  - recent questions → `/ask`.
- Each recent panel shows up to `DASHBOARD_RECENT_ITEMS` items (5), a presentation constant
  chosen by the build and not tuned.

**What this covers:** `GET /api/dashboard`'s parameters, its `indexed_totals`, the date and
department behaviour of each panel, and the two landing routes.

**What it does not cover:**

- **NFR-10's two-second load.** One endpoint is what makes it achievable. Nothing here measures it.
- **FR-15's filters**, which item 2 settles for the repository and must keep consistent with this
  entry for department.
- **A link from a recent question to its own thread.** That needs item 4a's `/ask?c=<id>`. Until
  then the panel links to `/ask`.
- **Meetings' department.** Not modelled, and not invented here.

> **Clarified on 6 October 2026, when item 3 was built.** None of these changes the decision.
> Each makes its wording match what was built.
>
> - "The identical 200 payload" for an unknown department and a restricted-only one means
>   identical **apart from `filters.department`**, which echoes the value sent. The echo is the
>   caller's own input, so it discloses nothing.
> - A reversed range (`date_from` later than `date_to`) is a 400 keyed on **`date_to`**, the
>   field the screen marks. This is the same convention as D-65's other 400s.
> - `department` is trimmed of surrounding spaces, so a value of spaces only means "not
>   applied", as an empty one does.
> - `/admin` is not restricted to Administrators. Typed by an Employee, it shows that
>   Employee's own scoped dashboard, because both landing routes render the same screen. No
>   administrative function lives there.

> **Built on 20 October 2026, outside a numbered item, at the user's request.** Each recent
> question that carries a `conversation_id` links to its thread at `/ask?c=<id>` (D-77), and a
> one-off question stays plain text. The payload already carried the id (D-68), so nothing on the
> server changed. This closes the "link from a recent question to its own thread" bullet above.
> Tested in `frontend/tests/dashboard.test.jsx`.

## D-71 · FR-12 keyword search collapses whitespace on both sides before matching

**Status:** Settled by the user · **Date:** 2026-10-06 · **Concerns:** FR-12's keyword search
(`GET /api/search`) · **Found by:** Objective 02, item D06

**The defect.** Keyword search matched `chunk_text` with a plain case-insensitive substring
test, and chunk text keeps the extracted text's line breaks verbatim (D-31). So any phrase that
wrapped a line in the source could never be found. Objective 02's D06 showed it: "Willow Bridge
escalation ladder" is in the PDF, and its extracted text reads "escalation\nladder". The user
ruled this an FR-12 defect rather than a quirk of the corpus.

**Decision.** For matching, every run of whitespace is collapsed to one space on both sides:

- in the stored text, inside the query, with `REGEXP_REPLACE(chunk_text, '\s+', ' ', 'g')`,
  and the same for the source's title;
- in the term, with Python's `" ".join(term.split())`.

The term is still logged in `SearchLog` and echoed in the reply exactly as typed, and the
two-character minimum is still measured on it. A snippet is windowed over the collapsed text,
so a match that wrapped a line is shown as one run.

**What this covers:** both branches of `GET /api/search`, the chunk-text match and the title
match, for documents and meetings.

**What it does not cover:**

- **The answer path.** `POST /api/ask` ranks by embedding similarity and has no substring test.
- **Non-breaking and other Unicode spaces.** Postgres's `\s` and Python's `str.split()` agree on
  spaces, tabs, line breaks and carriage returns. They are not guaranteed to agree on every
  Unicode space, so a phrase separated by one may still not match.
- **Hyphenation across a line.** A word split as "escal-\nation" stays split.
- **Speed.** The collapse runs per row, inside the query, and no index serves it. At this corpus
  size that is immaterial; it is noted for scale.
- **Whitespace-only queries.** One of two or more characters still passes the length rule, and
  now collapses to the empty term, which lists everything in scope. Before this change the same
  query matched almost everything. Neither is a disclosure.

**Evidence.**

- `apps/retrieval/tests/test_search.py` covers the D06 shape ("escalation ladder" against
  "escalation\nladder"), CRLF with indentation, a tab, extra spaces and a line break in the
  query, a title, the permission boundary, and the term logged as typed. The new tests were run
  before the fix, and all of them except the logging test failed.
- Objective 02's D06 phrase is restored to the team's original and re-searched in
  `corpus/objective-02/results.*`.

## D-72 · FR-15's browse: a separate endpoint, Department from the column, and 204 only for a filter that matches nothing

**Status:** Settled by the user · **Date:** 2026-10-06 · **Stage:** 5 item 2 · **Concerns:** FR-15's
list, browse, filter and count clauses · **Builds on:** D-09, D-53, D-65, D-66, D-70

**A separate browse endpoint, sharing one query with the list.** The repository screen reads
`GET /api/documents/browse`, which returns `{filters, facets, documents}` in one request.
`GET /api/documents` stays a bare list for the FR-08 upload flow and its existing consumers. Both
routes build their documents through **one scoped query function**, and browse adds the filters,
the sort and the facets to it. That way the two cannot drift, and the set-level audit does not
find the list implemented twice.

**Department comes from `Documents.department`, not from `ContentTags`. This is a deliberate
departure from FR-15's server clause**, which says browse "executes filtered queries against
ContentTags". The column (D-09) is the source FR-14's department filter uses (D-70), so the
dashboard and the repository cannot disagree about which department a document belongs to.
Project, Process and Topic query `ContentTags`, as the clause says, and no `Department` tags are
seeded. When FR-10 lands, the department it assigns should write this column, so there stays one
source.

**Filters and counts:**

- Filters combine with AND across dimensions, one value per dimension.
- The text filter matches the title, case-insensitively, with D-71's whitespace collapsing.
- `status` and `sort` are fixed vocabularies read through `ChoiceField`. Department and tag
  values are checked for shape only, never looked up (D-65).
- `sort` takes title, type, uploader, upload date or status, in either direction. The default is
  newest first.
- Each dimension's values and counts are computed over the documents in the caller's scope that
  match **every active filter except that dimension's own**. That is FR-15's "counts per remaining
  filter value": the alternatives in the dimension being browsed stay visible, and each count
  says how many documents choosing that value would leave.
- Values come from the scoped documents and never from the `Tag` table. A tag or department used
  only on restricted documents is not offered (invariant 1).

**When it is 204.** Only when at least one filter is set — the text filter, `status`,
`department`, `project`, `process` or `topic` — and nothing in scope matches. `sort` on its own is
not a filter. An unfiltered, empty repository is **200** with an empty list, because there is no
filter combination to fail.

A 204 has no body, so **the screen must not rely on the last facets it received**. A filtered URL
opened fresh, by Back after a delete or from a bookmark, has none. On a 204 the screen shows the
empty state, the active filters read from the URL, and a "Clear filters" action. The front-end
test for the 204 opens a filtered URL directly.

**What this covers:** `GET /api/documents/browse`, its parameters, facets, sort and 204, and the
query it shares with `GET /api/documents`.

**What it does not cover:**

- **Multiple values within one dimension.** Not offered.
- **Browsing meetings.** FR-15 is the document repository. Its CRUD line names `Meetings (Read)`,
  but no clause uses it.
- **The `Department` tag dimension.** It stays in the vocabulary for FR-10 and is not read here.

> **Corrected and clarified on 7 October 2026, when item 2 was built.**
>
> - **Correction.** The decision says `GET /api/documents` stays "for the FR-08 upload flow and its
>   existing consumers". The upload flow never called it: `Upload.jsx` imports only
>   `uploadDocument` and `reprocessDocument`. Its one front-end caller was the repository screen,
>   which now reads browse, and `listDocuments` is gone from `frontend/src/api/documents.js`. The
>   route stays as FR-08's contracted list, used by its own tests and by nothing else. The wording
>   came from the question put to the user and was not checked against the code when it was
>   recorded; the react-frontend agent found it.
> - **Sort.** `title` sorts case-insensitively, `uploaded_by` sorts by the uploader's email,
>   `status` sorts alphabetically rather than in vocabulary order, and the primary key breaks
>   ties.
> - **Echoes.** `q` is echoed trimmed but not collapsed. Tag values are echoed in their normalised
>   form, so `filters` shows what was matched.
> - **Counts.** A facet count is the number of documents carrying the value; a document tagged
>   twice with one value counts once.
> - **`Tag.active` is not consulted.** A deactivated tag that is still linked to a document is
>   filtered on and offered like any other. Nothing deactivates tags before FR-10.
> - **A repeated parameter** takes its last value, which is DRF's behaviour. This is not tested.
> - **The screen** compares a facet value exactly, so a hand-typed `project=Supplier Review`
>   filters correctly (the server normalises it) and appears as an active filter, but its facet
>   button does not show as pressed.

## D-73 · FR-15's deletion: `manage_documents` for Administrators, scoped-first, everything in one transaction

**Status:** Settled by the user · **Date:** 2026-10-06 (the permission on 5 October) · **Stage:**
5 item 2 · **Concerns:** FR-15's deletion clauses and its 403 and 404 · **Builds on:** D-07, D-46,
D-66, D-67

**The permission.** `manage_documents` is seeded by migration `accounts 0005`, the way 0003 seeds
`manage_roles`, and held by Administrator only. There is no ownership rule: FR-15 makes deletion
a role permission. Because D-66 puts every Employee-only document in an Administrator's scope, no
document can become undeletable. A test asserts that an Administrator can delete a document whose
`visible_to_roles` is `["Employee"]`.

**`DELETE /api/documents/{id}`:**

1. The document is resolved through `scoped_documents()`. Unknown or out of scope is **404**,
   from one query, as on the detail route (D-46).
2. Then `manage_documents` is checked. Without it the answer is **403**. In the other order, the
   status code would tell a caller whether a document they cannot see exists.
3. In **one transaction** (invariant 9): the document's `ContentChunk` rows (by `source_type` and
   `source_id`, since they have no foreign key, D-07), its `ContentTag` rows, and the document.
   `ExtractedContent` goes with the document by its foreign key. `AnswerCitation.chunk` is
   `SET_NULL` (D-67), so the FR-12 record of what was answered survives without its text.
4. The stored file is removed in `transaction.on_commit`, so a rolled-back delete keeps it.
5. **204 No Content.** FR-15 names no success code for a delete, so this is a convention.

**What FR-15 promises, and the tests that hold it to that:** after a delete, a phrase known to be
in the document returns nothing from `/api/search`, and a question only it answered takes
no-answer path A.

**The screen's delete control.** The detail response carries a server-computed `can_delete`
boolean: whether the caller holds `manage_documents`. The control shows only when it is true, and
asks for confirmation. This is usability; the server checks the permission on every delete
whatever the screen showed (invariant 4).

**Detail view.** It also carries `extracted_text`, read from `ExtractedContent` through the same
scoped lookup (D-63). It is `null` when the document has no `ExtractedContent` row, and the
screen shows a stated empty state keyed on that `null`, not on the status. The text is returned
whole and rendered as text, never as HTML. The detail also carries the document's tags by
dimension.

**What this covers:** `DELETE /api/documents/{id}`, the `manage_documents` seed, and the fields
the detail response gains.

**What it does not cover:**

- **The download link and route.** That is Stage 5 item 2a.
- **Bulk deletion and visibility editing.** FR-15 asks for neither. D-47's
  `bulk_create(update_conflicts=True)` hole stays pinned, not closed.
- **Deleting meetings.** FR-15 is about documents.

> **Clarified on 7 October 2026, when item 2 was built.** None of these changes the decision.
>
> - **More than one `ExtractedContent` row:** the detail shows the newest by `extracted_at`, with
>   the primary key breaking ties. This matches `manage.py reindex`, which reads the same row. No
>   shipped path leaves more than one.
> - **The document row is locked (`select_for_update`) before its chunks are deleted**, as
>   reprocess and re-index lock it. A reprocess in flight would otherwise commit fresh chunks for
>   a document that no longer exists. Pinned by the SQL order in a test, not by a concurrency
>   test.
> - **The file is removed with `on_commit(..., robust=True)`.** If removal fails after the rows
>   are committed, Django logs it and the delete still answers 204, leaving an unserved file;
>   `config/urls.py` serves nothing under `MEDIA_ROOT`. The empty `media/documents/<id>/`
>   directory is also left behind.
> - **`Tag` rows stay** when their last link is deleted. They are a vocabulary, and D-72's facets
>   never offer a value no document carries.
> - **The deletion function lives in `apps/documents/deletion.py`**, outside the request-serving
>   packages the D-53 scan watches, as `apps/ingestion` is. Reads of `ContentTag` and
>   `ExtractedContent` in `apps/api/repository.py` go through scoped documents, but the scan does
>   not watch those models, so that is enforced by the tests rather than by the scan.

> **Clarified on 13 October 2026, by item 2a (D-75).**
>
> - **"Django logs it" was untrue with `DEBUG=False` until D-75.** `LOGGING` configured only the
>   audit logger, so the failed removal's log record had nowhere to go. D-75's ERROR-level root
>   handler writes it to `logs/errors.log`.
> - **When the removal fails.** On Windows, a download keeps the file open, and a delete that
>   commits while it is open is exactly when the removal fails. The row is gone and the file
>   stays. D-75's route resolves rows, so it never serves that file.

## D-74 · The demonstration corpus is tagged by a script, from the manifest, with `applied_by="user"`

**Status:** Settled by the user · **Date:** 2026-10-06 · **Stage:** 5 item 2 · **Concerns:**
FR-15's browse, which shows nothing without tags · **Owner of real tagging:** FR-10 (Objective 05,
13 November)

**Decision.** Nothing writes `ContentTags` until FR-10's AI classification. To make browse
demonstrable now:

- `corpus/objective-02/manifest.json` gives each document Project, Process and Topic tags.
- `scripts/seed_objective02_tags.py` writes `Tag` and `ContentTag` rows through the ORM, with
  `applied_by="user"` and `confirmed=True`, finding each document by its manifest title.

There is no tagging API route: tagging is FR-10's surface, and building part of it early is work
the proposal places elsewhere.

**The script:**

- **Idempotent.** Re-running it adds nothing.
- **Run against `kmp`**, the database the alpha runs on and the one holding the corpus, not a
  worktree's test database.
- Writes no `Department` tags (D-72).

**The values are shaped for the demonstration:**

- Each dimension has a few values, each shared across several documents, so the counts mean
  something and two filters can be shown narrowing the list.
- One Project value is used only on Administrator-only documents. An Employee is never offered it,
  which demonstrates that facets disclose nothing.
- At least one combination of filters an Employee can choose matches nothing, which demonstrates
  the 204 empty state.

**What this covers:** tags on the Objective 02 documents in the development database.

**What it does not cover:**

- **Meetings.** FR-15 browses documents only.
- **Anything FR-10 will do.** AI-applied tags, confidence, confirmation workflows and tag
  administration are FR-10's.
- **A fresh database.** The seed needs the corpus ingested first (`scripts/ingest_objective02.py`)
  and does nothing for documents that are not there.

> **Corrected 1 November 2026: the alpha's database is `kmp_demo_20261101`, not `kmp`** (D-88).
> This decision called `kmp` "the database the alpha runs on". That was true when it was written,
> and D-84 then left the demonstration database open. The script ran against `kmp_demo_20261101`
> on 1 November, because the snapshot it was restored from has no tags. It created 14 tags and 48
> links, and a second run created none. `kmp` is unchanged by this.

> **2 November 2026 (item 10's H5, D-90): this entry's empty-state claim could not hold, from the
> day it was written.**
>
> - **The rule that defeats it.** Under D-72's facet rule, each facet's values are counted over the
>   documents matching every other active filter. So no pair of facet choices can match nothing,
>   and "at least one combination of filters an Employee can choose matches nothing" was false for
>   facets when both entries were written. It is not only false "after either is chosen", as the
>   walk record first put it.
> - **The 204 empty state is still reachable,** and tested in both suites. It is reached through
>   the page address, which holds the filters (`/documents?project=supplier%20review&topic=safety`),
>   or through a title filter that matches nothing. `docs/demonstration-script.md` uses the address.

## D-75 · FR-15's download: a scoped view returning the original as an attachment, typed and named by its signature

**Status:** Settled by the user · **Date:** 2026-10-13 · **Stage:** 5 item 2a · **Closes:** FR-15's
download link, which D-52 said was built and which never existed (D-52's superseded note)

**Decision.**

- **The route.** `GET /api/documents/{id}/download`. The detail view's link points at it, never at
  `file_path.url`: that is `/media/<path>` with the original filename in it, and `config/urls.py`
  serves nothing outside `/api/`. `static(MEDIA_URL)` is not added. It would serve every document
  to anyone who has its path.
- **Scope.** The document is resolved through `scoped_documents` (item 1's helper), exactly as the
  detail view resolves it. Unknown and out of scope are both 404 (D-46's precedent), never 403. No
  permission is needed beyond scope, because FR-15 names none for the link. Every status
  downloads: as D-52 noted, the stored original exists whether or not it was indexed.
- **The response.** `FileResponse(handle, as_attachment=True, filename=...)`, not a hand-built
  `Content-Disposition`. The content type comes from `file_type`, which `read_file_signature` set
  from the bytes at upload. This is D-15's principle applied on the way out:

  | `file_type` | `Content-Type` |
  |---|---|
  | pdf | `application/pdf` |
  | docx | `WORD_CONTENT_TYPE` |
  | xlsx | `EXCEL_CONTENT_TYPE` |
  | txt | `text/plain; charset=utf-8` (the signature admits only valid UTF-8) |

  `X-Content-Type-Options: nosniff`, which `SecurityMiddleware` already sets, is what makes that
  type binding. Its tests assert it on this response.
- **The filename** is the stored original filename with its extension corrected to the signature's.
  Extensions are compared case-insensitively, so `Report.PDF` stays as it is. Only the last
  extension is replaced, so `report.pdf.exe` becomes `report.pdf.txt`. One is added when the name
  has none.

  The reason is security. The server never reads the extension; `ACCEPTED_EXTENSIONS` only gates
  the upload control. So an API upload of UTF-8 text named `Q3_budget.vbs` or `invoice.html` is
  accepted as txt and stored under that name. Served unchanged, it would download as something a
  colleague could run. Corrected, it downloads as `Q3_budget.txt` and `invoice.txt`, and both cases
  are tested.
- **A document with no file.** The route answers 404 with the same body as out of scope, and the
  detail view shows the link on every document.
  - The scoped lookup runs first, then the file checks. An out-of-scope document gets the plain
    404 and logs nothing, even when its file is also missing.
  - `if not document.file_path` is checked before opening, because opening a blank `FieldFile`
    raises `ValueError`, not `OSError`.
  - The file is then opened inside `try/except OSError` before the `FileResponse` is built. A
    delete that commits between the lookup and the open answers 404, not 500.
  - The body is the same on purpose. DRF passes `get_object_or_404`'s message through, so this
    route's out-of-scope body is `{"detail": "No Document matches the given query."}`. A bare
    `Http404()` or `NotFound()` would give `{"detail": "Not found."}` and tell the two apart. The
    missing-file 404s raise the lookup's message. Tests compare against a real out-of-scope
    response, not a hard-coded string.
  - A missing file is logged at ERROR with the document id and the stored name.
- **Why 404 here and 422 for reprocess** (`NO_STORED_ORIGINAL_MESSAGE`). A GET for bytes that are
  not there is "not found". Reprocess is an action that cannot proceed.
- **A file with no row.** If D-73's on-commit removal fails, the file stays with no row. This route
  resolves rows, so it never reaches that file.
- **The error log.** `LOGGING` configured only the audit logger. With `DEBUG=False`, Django's own
  errors were dropped: its console handler needs `DEBUG`, and `mail_admins` has no `ADMINS`. An
  app logger reached stderr only through Python's last-resort handler, with no time or level. An
  ERROR-level root handler in `apps/core/logging_config.py` now writes `logs/errors.log` beside
  `audit.log`, tested the way the audit file is.

**Two scopes that agree only while the cascade holds.** Retrieval scopes at the chunk level, on
`ContentChunk.visible_to_roles`. A download can consult only the document's stamp,
`Document.visible_to_roles`, because the original is one file. The two agree only while the
visibility cascade holds: invariant 2, D-17 and D-47's `VisibilityCascadeMixin`. The D-53 probe for
this route seeds that disagreement, as it does for the others.

**Found while settling this, for item 5.** Reprocess answers Django's HTML 500 when the file is
missing from disk: `reprocess_document` opens it with no `OSError` handling, and `config/urls.py`
sets no `handler500`. That was found by reading the code, not by running it.

**What this decision does not cover.**

- **Inline viewing or a preview.** The response is an attachment only.
- **Meeting transcripts.** FR-09 stores a transcript as text, and no requirement asks to download
  it.
- **Range requests, `ETag` and `Last-Modified`.** None are set.
- **Logging who downloaded what.** No requirement asks for it.
- **Files on disk with no row.** Nothing cleans them up.

> **Corrected and clarified on 14 October 2026, when item 2a was built.**
>
> - **Correction.** The type table says the signature admits "only valid UTF-8". It admits a file
>   whose first 8 KB decode as UTF-8: `_text_format` reads no further. A text file with invalid
>   bytes later is accepted as txt and served as `text/plain; charset=utf-8`. With `nosniff` and an
>   attachment response, nothing renders it, so the label is wrong but harmless. The django-backend
>   agent found this.
> - **`Accept` is not consulted on this route.** DRF negotiates before the view runs, and the API's
>   only renderer is JSON, so `Accept: application/pdf` was answered 406. A browser's navigation
>   header ends in `*/*` and was never refused, but a script or download manager naming the type
>   was. The view uses DRF's documented `IgnoreClientContentNegotiation`
>   (`apps/api/negotiation.py`), so its 401 and 404 are still JSON. Every other route negotiates
>   as before. The contract says so.
> - **"Logs nothing" means nothing at ERROR.** Django's `django.request` logs a WARNING
>   `Not Found: <path>` for every 404. An out-of-scope document's WARNING is identical to an
>   unknown id's, and it is below the error file's level. The test asserts exactly that.
> - **The 404 message is restated as a constant**, `DOCUMENT_NOT_FOUND_MESSAGE`, built as Django 5.2
>   builds it. The tests compare against real out-of-scope responses, so a Django rewording fails
>   them rather than going unnoticed.
> - **An unknown `file_type` would be a 500** (`DOWNLOAD_CONTENT_TYPES[...]`). It is unreachable
>   through the vocabulary, and a test pins the map's keys to `ACCEPTED_FORMATS`. There is no
>   fallback type.
> - **What counts as an extension** is `os.path.splitext`'s rule on the stored name's last
>   component: `.profile` as txt becomes `.profile.txt`, and `notes.` becomes `notes.txt`. A
>   genuine PDF named `notes.txt` downloads as `notes.pdf`.
> - **The missing-file log line** names the document id and the stored name. The `OSError` case
>   carries its traceback, so the filesystem path appears in the server's log and never in the
>   response.
> - **The error file's format** is `%(asctime)s %(levelname)s %(name)s %(message)s`, UTF-8,
>   created on the first ERROR. `ERROR_LOG_PATH` is env-driven and, like `AUDIT_LOG_PATH`, not
>   in `.env.example`.
> - **Tests never write the real log files.** `conftest.py`'s autouse `log_files` fixture points
>   both at temporary paths. It also re-attaches pytest's own root handlers after `dictConfig`,
>   because a configuration with a `root` entry removes them.
> - **Found, and outside this item:** a `file_path` naming a path outside `MEDIA_ROOT`, which
>   only a script could write, raises `SuspiciousFileOperation` rather than `OSError`, and gets
>   Django's 400 rather than the 404. Left with item 5's missing-file work.

> **Settled on 21 October 2026 and built on 26 October, in Stage 5 item 5, as the notes above
> said it would be.** This note was first committed on 21 October as if already built; it is
> corrected here.
>
> - **Reprocess, missing file.** Reprocess no longer answers Django's HTML 500 when the stored file
>   is missing from disk. It answers the existing 422 with `NO_STORED_ORIGINAL_MESSAGE`, as a blank
>   `file_path` already did, and logs at ERROR with the document id and the stored name.
> - **A path outside the media folder.** A `file_path` there raises `SuspiciousFileOperation`
>   rather than `OSError`. It is now treated as a missing file on both routes: the download's 404,
>   with the out-of-scope body, and reprocess's 422.
> - **The order of reprocess's checks** is 404 (scope), 409 (already indexed), 422 (blank
>   path), then 422 (file can't be opened). So an indexed document with a missing file still
>   answers 409. A blank path is now logged as well, as on the download.
> - **Not covered:** a file removed between that check and the reprocess's own open still
>   gives a 500, with the transaction rolled back.

> **1 November 2026: the error file also holds WARNINGs from one logger, `apps.ai.attempts`.**
> They record failed provider attempts and the cause of each `POST /api/ask` 503 (D-82's later
> note of the same day). The root's handler stays at ERROR, so `django.request`'s 4xx WARNINGs
> still stay out. The new logger has its own WARNING handler on the same file, and its lines
> keep this decision's format.

## D-76 · Every `/api/` response is marked never-cache, by one middleware

**Status:** Settled by the user · **Date:** 2026-10-13 · **Stage:** 5 item 2a · **Concerns:** every
route that returns scoped content (FR-11, FR-12, FR-13, FR-15)

**Decision.** One small middleware applies Django's `add_never_cache_headers` to every response
under `/api/`, including 401s, 403s and 404s. That sets `Cache-Control: max-age=0, no-cache,
no-store, must-revalidate, private` and an `Expires` header. It uses Django's function rather than
a hand-built header string, for the same reason D-75 uses `FileResponse` rather than a hand-built
`Content-Disposition`. Nothing outside `/api/` is touched, so the SPA's pages and assets stay
cacheable once item 9 serves them.

**Why the whole API, not the download alone.** `GET /api/documents/{id}` already returns the whole
document as `extracted_text` (D-73). The ask and search routes return text drawn from documents.
None of them carried cache headers before this.

**What it buys.** Without the header, a browser would not normally reuse a download after a role
change anyway: the responses have no freshness or validator headers, no `Last-Modified` and no
`ETag`. What `no-store` buys is no copy in the browser's disk cache on a shared machine, and none in
a proxy that item 9 or M8 may put in front (D-64 leaves both open). It cannot remove the copy the
user saves to Downloads; that is what a download is. OWASP's testing guide checks sensitive
responses for this header (WSTG-ATHN-06), so item 11 would raise it anyway.

**Tested** the way `test_rbac.py` walks `enumerate_endpoints()`: every `/api/` route answers with
`no-store`, including its 403s and 404s.

**What this decision does not cover.**

- **Responses outside `/api/`.** Item 9 decides how the SPA is served and cached.
- **The copy a user saves.** See above.

> **Clarified on 14 October 2026, when item 2a was built.**
>
> - **Matched on `request.path_info`, not `request.path`.** `path_info` is what the URL conf
>   resolves. Under a script-prefix deployment, `request.path` would carry the prefix, match
>   nothing, and leave the API silently uncached. The two are identical today.
> - **First in `MIDDLEWARE`**, the outermost layer, so it also marks responses another middleware
>   returns early: CSRF's 403 and the URL resolver's 404 through `handler404`. Both are tested.
> - **Not covered: `GET /api` without its slash.** `CommonMiddleware` answers it with a 301 to
>   `/api/`. That redirect isn't under `/api/`, so it isn't marked, and it carries no content.

## D-77 · FR-13's active thread lives in the address, and switching threads adds a history entry

**Status:** Settled by the user · **Date:** 2026-10-15 · **Stage:** 5 item 4a · **Closes:** D-61's
gap 3, FR-13's "retaining the thread" with FR-12's citation link (`docs/stage-4-open-items.md`
§2.1)

**Decision.** The address is the only source of truth for the active thread. `/ask?c=<id>` names
it, and `/ask` with no `c` means there is none.

1. **Reading.** An effect keyed on `c` calls `fetchConversation`, on mount and whenever `c`
   changes: Back, Forward, a link. It has a cleanup flag, so a slow read for thread Y can't land
   after Back to thread X. It reads only when `c` differs from the thread on screen, so the
   screen's own writes never trigger a re-read that would overwrite a live turn. The turns always
   come from the server and are never restored from the browser. A read is re-scoped (D-48), so a
   source deleted in the meantime is not shown again (FR-15).
2. **Push on a switch.** Reopening a thread from the list and "Start a new topic" navigate, adding
   a history entry, so Back returns to the previous thread.
   - Start a new topic writes whatever `threadAfterNewTopic` returns: `/ask`, or `/ask?c=<id>`
     when it reuses an empty thread.
   - Reopening the thread already on screen writes nothing. So does Start a new topic when the
     thread on screen is already empty. Neither adds a duplicate entry.
3. **Replace on create.** `/ask` becomes `/ask?c=<id>` as soon as `createConversation` returns,
   before the answer, because `handleSubmit` already has the id then. Any `q` from Search's
   `/ask?q=` link is dropped at the same time. Back from a new thread never lands on an empty
   `/ask`.
4. **A reply for a thread the address no longer names is dropped.** Back and Forward can't be
   disabled the way the list is while asking, and an answer can take minutes (D-49). A reply is
   applied only if `c`, read through a ref, still names the thread it was asked in. Otherwise it
   is dropped: the server has it, and the next read of that thread shows it. Today `handleSubmit`
   appends the turn and calls `setConversationId` unconditionally. One question stays in flight at
   a time, as now.
5. **A `c` that answers 404 is replaced.** That covers an unknown id, another user's thread and an
   id that isn't a UUID, which get one answer (invariant 1). The address becomes `/ask`, so Back
   never returns to the dead address. Today's "conversation not found" notice is shown and is still
   showing after the replace.
6. **The tab title stays a static "Ask"**, never the thread's title. With push, every thread
   visited stays in the Back button's history list, where anyone at the machine can read it.

**Why push.** The dashboard's filters already add an entry per change (D-70). An assessor who
follows a citation, or opens an older thread, expects Back to return to the conversation they
left.

**No route or response shape changes**, so `docs/api-contract.md` doesn't change.

**Tested** in `frontend/tests/`, through `MemoryRouter` with a probe that exposes the location and
`navigate(-1)`:

- the first question replaces the entry rather than pushing one;
- following a citation link and pressing Back re-reads X;
- reopening Y and pressing Back re-reads X;
- a reply for X that resolves after Back to Y appears neither in Y nor in the address;
- a `c` that answers 404 ends at `/ask` with the notice still showing, and Back skips it;
- reopening the thread already open adds no entry.

**What this decision does not cover.**

- **A re-read thread's citations stay inert until item 4b.** After Back from a citation, the
  thread returns with each statement and its number, but with no expansion, no source link and no
  Sources panel (D-61's gap 4). The screen's existing note says so.
- **Partial matches on a re-read turn.** No route returns a past turn's candidates, so a no-answer
  turn's partial matches are gone after Back. Reopening from the list behaves the same way today.
- **Where the reader was.** Back lands at the top of the screen, not at the citation followed.
- **The draft in the question field** does not survive leaving the screen.
- **D-70's recent-questions link.** Item 4a unblocks it as a follow-up (`Dashboard.jsx:364`).
  Each recent question already carries `conversation_id` (D-68), so the link is front-end work
  only. No Stage 5 item names it yet.
- **D-58 is narrowed, not closed.** An empty thread now survives a reload and a return, because
  the address names it. One the user leaves for good still persists.

> **Clarified on 15 October 2026, when item 4a was built.** None of this changes the decision. It
> records what D-77 left to the implementation.
>
> **Set by the coordinating session's brief:**
>
> - **Focus.** A read the address asks for on its own (mount, Back, Forward, a link) moves no
>   focus, as no page load does. A click in the list still focuses the thread's last turn once
>   that thread's read lands. The pending focus carries the thread it was set for, so another
>   read cannot spend it.
> - **While a thread is read,** Ask and Start a new topic are disabled, as the list already was.
>   Nothing is asked into or cleared from a thread that is not yet on screen. `opening` starts
>   true when the address names a thread, so this holds from the first render.
> - **A dropped reply still updates the bookkeeping.** `unusedThreadAfterTurn` and
>   `unusedThreadAfterFailure` are applied, and a successful reply re-reads the list. It adds no
>   turn, no acknowledgement and no focus, writes no address, and leaves the field alone. A
>   failure for a thread the address no longer names is dropped the same way, so a 404 for X
>   never clears Y.
> - **Every navigation after an await is guarded:** the screen must still be mounted and the
>   address must still name what it named. React Router's `navigate` works after unmount, so
>   without the guard a citation followed while a question was in flight could be undone.
> - **Rule 3 covers a reused empty thread** as well as a created one. Before the ask, if the
>   address doesn't name the thread being asked in, it is replaced with it.
> - **When the address comes to name no thread** (the nav's Ask link, or Back to `/ask`), the
>   turns, notice, field error and acknowledgement are cleared. The draft is kept.
> - **Start a new topic** still acknowledges and moves focus to the field, even when it writes
>   nothing. "Already empty" means no turns on screen and no read in flight.
>
> **Chosen by the react-frontend agent:**
>
> - **The address ref is updated at the moment of the screen's own writes**, and on commit for
>   Back, Forward and links. React Router commits a navigation as a transition, so without the
>   first update the existing 503 test dropped its own failure.
>   - **Not covered:** a reply or read 404 landing between a Back and its commit, one render
>     wide, is judged against the old address. Closing that would need React Router's
>     `UNSAFE_` navigation context.
> - **A read failure other than 404** (a 500, or no network) keeps the thread that was on screen,
>   under `conversationLoadFailed` and the client's fixed message. Until the user chooses again,
>   the address names the thread that failed while the screen shows the one before it, so here
>   the two disagree. Choosing that thread in the list reads it again without adding an entry.
>   Before this item, a failed reopen showed `askRejected`, which is untrue of a read.
> - **Choosing the thread already open** writes and reads nothing, and focuses its last turn,
>   which is where a read would have put focus. The focus move is not tested.
> - **If the address moves or the screen unmounts while the thread is being created,** the
>   question is still sent and its reply is dropped. Not sending it would leave a permanent empty
>   thread (D-58).
> - **A 404 on the ask itself** is handled like a read's: the screen is cleared, the list re-read
>   and the address replaced with `/ask`, behind the same guard.
> - **The reply's `conversation.conversation_id` no longer sets the thread on screen.** The id the
>   address names is the one shown, so the address and the screen agree exactly.
>
> **What the deliberate breaks found.** Fifteen breaks were run against
> `askThread.test.jsx` and `ask.test.jsx`, each restored and checked by hash.
>
> - **Removing the check that stops a click on the open thread** failed no test. The click falls
>   through to the branch for an address that already names it, which writes nothing either. The
>   guard is redundant except for the immediate focus move. Removing both checks fails "adds no
>   entry and sends no read when the thread already open is chosen again".
> - **Removing the "already empty" guard** at first failed no test, because the test used an
>   empty `/ask`, where the address check also stops the write. A test for the case where the
>   guard is the only defence was added: an empty thread the address names, after a reload. The
>   unchanged break fails it.

> **The D-70 follow-up was built on 20 October 2026**, outside a numbered item: a recent question
> with a thread links to `/ask?c=<id>`. See D-70's note.

## D-78 · A reopened turn carries every source it consulted, re-scoped on read from one result

**Status:** Settled by the user · **Date:** 2026-10-20 · **Stage:** 5 item 4b · **Closes:** D-61's
gap 4: FR-12's citation expansion, source link and Sources panel on a reopened turn
(`docs/stage-4-open-items.md` §2.2)

**Decision.** `GET /api/conversations/{id}` gives every turn a `sources` key in the live reply's
shape (D-44): one entry per item consulted, in rank order, each with its title, its date and its
passages (`chunk_id` and text). A citation on a reopened turn then expands to its passage and links
to its source, and the turn has a Sources panel, as it did when it was live.

1. **Read only for a turn that renders as answered.**
   - `retrieved_chunk_ids` is read only for turns stored as answered. A turn stored as unanswered
     never has it read: `answered` plus `len(retrieved_chunk_ids)` tells the two no-answer paths
     apart (`apps/retrieval/query_log.py`, D-48's item 6).
   - Sources are built only for a turn that renders as answered. A never-answered turn, a
     re-scoped one and a provenance-removed one all carry `sources: []`. A re-scoped turn stays
     byte for byte a never-answered one.
   - Every turn carries the key, so the two states change together. `TURN_FIELDS` in
     `apps/api/tests/test_fr11_thread_scope.py` gains `sources` for both at once.
2. **One `scoped_chunks` query for the whole thread.** It covers the cited ids plus the retrieved
   ids of turns stored as answered. The surviving citations and the panel are both derived from
   that one result, so a citation can never expand to a passage the panel doesn't list.
3. **The entries are built by `answers.resolve_sources`**, fed the scoped chunks in logged order.
   Grouping, rank order and the fail-closed title and date read (D-53) are the live reply's own
   code, not a copy.
4. **A consulted chunk that is now restricted, deleted or re-indexed drops the same way**, with no
   count and no marker. There is no snapshot to fall back on, since D-67 stores no passage text,
   and that keeps FR-15's promise that deleted material is not surfaced again.

**Why consulted, not cited.**

- FR-12's clause says the Sources panel "lists every item consulted". D-44 settled that and
  rejected narrowing it to cited items as a misdescription of the retrieval.
- Since D-77, Back re-reads the thread. A cited-only panel would visibly shrink on the citation
  round trip.
- The brief's "from the same `permitted_citation_chunk_ids` result" is read as the re-scoping
  requirement: re-scoped on read, from one result. It is not read as a narrowing.

**A correction this makes.** `ConversationTurnSerializer`'s docstring, and the contract, said
`retrieved_chunk_ids` "is not part of what the user was shown". Since D-44 it is, on an answered
turn: it is exactly the list the live Sources panel was built from. It is still not a field of a
turn.

**The front end.** `savedTurnFrom` carries the turn's `sources`, so its citations expand. The
reopened-thread note goes, because nothing on screen is left for it to be true of. The
provenance-removed state, untested since D-62, gets its front-end test here, as the brief asks.

**`docs/api-contract.md`** is updated in the same commit as this decision.

**Tested**, in `pytest` from both roles:

- a reopened turn's `sources` equal the live reply's `sources` for the same turn;
- an uncited consulted passage is present;
- after the reader's role narrows, an out-of-scope consulted source is absent, with nothing
  marking it;
- a path-B turn reopens identical to a path-A one;
- a consulted but uncited document deleted under D-73 is gone from the panel.

And in the front-end suite: a reopened turn's citation expands to its passage and links to its
source; its Sources panel is shown; and the provenance-removed state shows its own title and
message and no statements.

**What this decision does not cover.**

- **Partial matches on a reopened no-answer turn.** Nothing records them, so none are returned.
- **A source dropped by D-53's fail-closed read** leaves its citation with nothing to expand to, as
  on the live reply.
- **The cost of a thread read.** It is now one scope query per thread plus `resolve_sources`'
  reads. It is not measured.

> **Clarified on 20 October 2026, when item 4b was built.** None of this changes the decision. It
> records what D-78 left to the implementation, what the deliberate breaks found, and two contract
> sentences corrected in the same commit.
>
> **Chosen by the django-backend agent:**
>
> - **The panel lists only `retrieved_chunk_ids`.** It never adds a cited id the turn didn't log
>   as consulted. On rows `record_query` writes, the cited ids are a subset of the retrieved ones,
>   because verification checks against that same list.
> - **`permitted_citation_chunk_ids` became `readable_thread_chunks`**, which returns the scoped
>   rows rather than their ids. The context key is now `readable_chunks`. `consulted_chunk_ids(turn)`
>   is the one place the "only if stored as answered" rule is written. The query fetches four
>   columns and never the embedding.
> - **`resolve_sources` runs once per answered turn**, unchanged, so the role is re-read for each.
>   Batching across turns would have meant changing the live path.
>   - **Measured:** a thread with three answered turns and one unanswered turn went from 11 queries
>     to 20. The chunk query is still exactly one, and a test asserts that.
> - **"Never read" is asserted at the SQL level.** A path-B turn's id appears in no query. A
>   control assertion, that an answered turn's uncited consulted id does appear, makes sure the
>   test can't pass vacuously.
> - **Role narrowing is tested from an Administrator session only**, since only that role can be
>   narrowed. Its dual-role counterpart narrows the source instead.
> - **The live-equals-reopened test uses a restated `ControlledService`**, the `test_ask.py`
>   pattern, so rank order is fixed. The autouse stub's seeded random vectors would make it
>   unpredictable.
>
> **Chosen by the react-frontend agent:**
>
> - **`expandable` is removed** rather than left always true. `savedTurnFrom` falls back to `[]`
>   for a body with no `sources` key.
> - **The front end does not filter `sources` on a turn that isn't answered.** The no-answer and
>   provenance branches never render them. That is tested for the provenance branch, with a
>   fixture that leaks a statement and a source, and not for the no-answer branch.
> - **The note's text and style are deleted**, and its absence is tested by the thread section's
>   structure. Any element later added between the heading and the turns will fail that test.
> - **A test for D-53's plain-number fallback** was added, though not asked for.
>
> **What the deliberate breaks found.**
>
> - **Reading the retrieved ids of unanswered turns as well** changed no body: the rule that only
>   a turn rendering as answered gets sources still returned `[]`. Only the SQL-level test failed.
>   The two rules defend each other.
> - **An unscoped chunk read for the panel** at first failed only the one-query test and the
>   source-row scan. `resolve_sources`' scoped read of the source row hid the leak wherever a
>   chunk and its source agree. `test_an_unstamped_consulted_passage_is_shown_to_nobody` was added,
>   and the same break then failed it from both roles.
>
> **Two contract sentences, corrected in the same commit:**
>
> - The partial-matches section said a stored turn "returns no `sources`".
> - "Every passage a statement cites is in the same list" now names D-53's exception, where a
>   dropped source leaves its citation with nothing to expand to.
>
> **A known limitation, added after review.** A reopened unanswered turn has no partial matches.
> They were never logged, and re-deriving them would mean re-running retrieval against today's
> corpus, which would offer items the turn never saw. The query cost above stands as recorded.

## D-79 · Asks, ingestion and thread creation are throttled per user, and a user has at most one ask in flight

**Status:** Settled by the user · **Date:** 2026-10-21 · **Stage:** 5 item 5 · **Closes:** the
throttle D-49 deferred to item 5

**Decision.**

1. **Rate throttles, per user.** DRF's `ScopedRateThrottle`. Each rate lives in
   `apps/core/constants.py` and is passed through `DEFAULT_THROTTLE_RATES`, as D-26 does for
   `auth`.

   | Scope | Routes | Rate |
   |---|---|---|
   | `ask` | `POST /api/ask` | `ASK_THROTTLE_RATE` = 10/min |
   | `ingestion` | `POST /api/documents`, `POST /api/meetings`, `POST /api/documents/{id}/reprocess`, one scope shared by the three | `INGESTION_THROTTLE_RATE` = 60/hour |
   | `conversation_create` | `POST /api/conversations` (D-80) | the ask rate, in its own scope |

   Rejected uploads count too, so a full Objective 02 run, about 31 requests, fits once an hour.
2. **One ask in flight per user.**
   - **How it's held.** `cache.add` on the default cache, keyed by the user and carrying a token.
     That is atomic because Waitress runs one process (D-64) and no `CACHES` is set, so it is the
     same per-process `LocMemCache` the auth throttle already uses. A multi-process server would
     need a shared cache.
   - **Its timeout** is derived from `GENERATION_TIMEOUT_SECONDS × MAXIMUM_GENERATION_ATTEMPTS`
     plus a margin, not a new literal. It is released in `finally`, and only if the token still
     matches.
   - **When it's taken.** After validation and the conversation check, right before the
     pipeline. A 400 or a 404 never holds it, and a rejected ask writes no `QueryLog` row.
3. **Two kinds of 429, told apart.**
   - **In flight:** `{"detail": ASK_IN_FLIGHT_MESSAGE, "code": "ask_in_flight"}`. The Ask screen
     says the previous question is still being answered.
   - **Rate:** DRF's 429 with its `Retry-After` header. The screens use `Retry-After`.
   - The client's only 429 text today is login's "Please wait a minute" (`client.js:52`). It is
     wrong for an answer that can run 15 minutes and for an hourly upload limit, so each kind
     gets its own text.
4. **`NUM_PROXIES = 0`** in `REST_FRAMEWORK`. Unset, DRF keys anonymous throttles on the
   client-sent `X-Forwarded-For` header, so D-26's login throttle could be dodged by changing
   that header on each request. If item 9 puts a reverse proxy in front, it makes this 1.

**Why.** One ask can hold a worker for up to 900 s, and only the two auth endpoints were throttled
(D-49). A rate limit bounds how many requests a user sends. The in-flight slot bounds what one
user's asks can hold: one Waitress thread.

**Tested:**

- an ask while the slot is held gets 429 at once and writes nothing;
- the slot frees after a 503 and after an exception;
- the two 429s are told apart by `code`;
- each scope answers 429 past its rate;
- two different `X-Forwarded-For` values from one address share one login limit.

**What this decision does not cover.**

- **Many users at once.** The slot is per user. Enough users asking together can still hold every
  Waitress thread. Nothing bounds the total.
- **Ingestion's worker hold.** Ingestion is rate-limited only, and an upload still embeds
  synchronously.
- **A multi-process server, and restarts.** The counters and the slot live in one process's
  memory, so a restart clears them, as D-26 says of the auth throttle.
- **The question's embedding** runs inside the slot as well. The margin must cover it, and
  whether that call has its own timeout is checked when it is built.

> **Clarified on 26 October 2026, when item 5 was built.** None of this changes the decision. It
> records one correction, what D-79 left to the implementation, and what the deliberate breaks
> found.
>
> **A correction: one ask can hold a worker much longer than 900 s.**
>
> - **The cause.** The question's embedding call passes no timeout, so it inherits the openai
>   SDK's default: connect 5 s, read 600 s. `MAXIMUM_EMBED_ATTEMPTS` makes three attempts, so the
>   embedding alone can take about 1,815 s before generation's 900 s.
> - **The slot's timeout follows from that.** It is 900 s plus `ASK_IN_FLIGHT_MARGIN_SECONDS`
>   (3 × (5 + 600) + 60 = 1,875 s), which is 2,775 s, about 46 minutes.
> - **A test pins it.** It compares the margin with both providers' real client timeouts, so an SDK
>   upgrade that lengthens them fails the suite. These are httpx per-operation timeouts, not
>   totals.
> - **The contract's "up to 15 minutes"** is corrected in the same commit.
> - **Not covered:** a timeout on the embed call itself, in `apps/ai/`. That is the cleaner fix,
>   and it was not made.
>
> **Chosen by the django-backend agent:**
>
> - **Where the timeout is built.** `ASK_SLOT_TIMEOUT_SECONDS` is built in `apps/api/ask_slot.py`,
>   because `constants.py` cannot import `apps.ai.generation`.
> - **The slot itself.**
>   - The key is `ask_in_flight_<user pk>`, and the token is a fresh `uuid4`.
>   - Release is a get then a delete, which is not atomic. That window is not defended, given the
>     46-minute timeout.
>   - The slot is held through naming the thread and building the reply, not only through the
>     pipeline.
> - **The length check moved.** The 400 for a question of the wrong length is now raised before
>   the slot is taken, by `check_question_length`, moved out of the pipeline's first step
>   (`apps/retrieval/pipeline.py`). Without that, a too-short question sent while another was in
>   flight would get 429, not 400. The message is unchanged.
> - **Where the in-flight text lives.** `ASK_IN_FLIGHT_MESSAGE` and `ASK_IN_FLIGHT_CODE` sit in
>   `views.py`, beside `ACCOUNT_LOCKED_MESSAGE` and its code.
> - **What counts against a rate.** This follows DRF's order: a 401 or a 403 is not counted; a 400,
>   404, 413 or 415 is; the in-flight 429 is counted against the ask rate.
> - **A view's GET is not throttled.** `ThrottlePostOnlyMixin` throttles a view's POST only, so
>   `GET /api/conversations` stays unlimited. A test walks every route and method and asserts the
>   throttled set is exactly the seven POSTs.
> - **No accidental 429s.** `conftest.py`'s autouse fixture already clears the cache around every
>   test. A probe recorded every 429 the full suite received: 44, each in a test written to
>   produce one.
>
> **Chosen by the react-frontend agent:**
>
> - **Login's text is kept by path.** Login and registration keep "Too many attempts. Please wait a
>   minute and try again." Any other 429 a screen doesn't handle gets a general fallback.
> - **What the client reads.** `code` is read from the error body, and `detail` never is.
>   `Retry-After` is read only on a 429, and only as seconds, rounded up; an HTTP date reads as
>   "later". `ASK_IN_FLIGHT_CODE` is copied into `src/api/ask.js` from the contract.
> - **The upload queue stops at its first 429.** That file and every file still queued behind it
>   show "Not uploaded", in neutral styling, with the limit message. Pressing Upload sends them
>   again.
> - **No re-read after a 429.** After a 429, neither the meetings form nor the repository list is
>   re-read.
> - **The wording**, with `{when}` given as "in N seconds" or "in N minutes", rounded up:
>   - Ask, in flight: "Your previous question is still being answered".
>   - Ask, past its rate: "Too many questions in a short time".
>   - Uploads, reprocess and meetings: "The upload limit has been reached".
>
> **What the deliberate breaks found.**
>
> - **Server:** ten breaks, and each failed the tests its builder had predicted.
> - **Screen:** thirteen breaks.
>   - **The unused-thread record.** Dropping it on a 429 (`threads.js`) at first failed no test.
>     Since D-77 the created thread is already the one on screen, so a plain retry goes back into
>     it anyway.
>   - **Where it does matter.** The record only matters when the user leaves the empty thread and
>     then presses "Start a new topic". A test for that was added, and the break then failed it.

**Dated note, 10 November 2026 (night): keyword search gets a scope, `search`, at 30 a minute, and a
term an upper bound of 500 characters.** The user's decision on the FR-19 security review's L1 and
L2 (D-107's note; D-119). Keyword search was unthrottled and bounded a term from below only. So one
Employee could log terms as fast and as long as they liked into `SearchLog`, which FR-19's cycle
reads. That opened a timing signal on the shared NPU (L1) and let them put chosen text at the top of
the Administrator's gap list (L2).

- **`SEARCH_THROTTLE_RATE = "30/min"`,** per user, through `ScopedRateThrottle` like the other
  scopes. Search spends no NPU time, so the rate is not about the NPU, as the ask rate is; it bounds
  how fast one user can fill the log. The page sends one request per submitted term, so a person
  searching never meets it, and no load test calls search.
- **`MAXIMUM_SEARCH_LENGTH = 500`,** the question's ceiling, refused with FR-12's 400 before any
  query runs and before any row is written, and refused in the browser first with a message that
  names it. `search` applies it and `search_total` does not: FR-19's cycle recounts terms logged
  before the bound existed, and a refusal there would roll back that cycle and every later one. The
  cycle's own cut to `MAXIMUM_QUESTION_LENGTH` (D-107's note, M1) stays for those rows.
- **What it does not do:** a user can still repeat one term 30 times a minute. The rate slows L2 and
  shrinks L1's signal, but does not remove either, and occurrence counts still count rows rather
  than people, which Objective 06's "accurate occurrence count" requires.
- **A throttled search is DRF's 429 with `Retry-After`,** and the search page shows the client's
  rate-limit text with Try again.

**Dated note, 10 November 2026 (night): applying a tag gets a scope, `tagging`, at 30 a minute.**
The user's decision on finding 4 of the security review in D-105's dated note of the same night (the
tag corrections). `POST /api/documents/{id}/tags` was unthrottled, and each new Topic name a person
types there becomes a permanent `Tag`. The Topic is grown, so it joins the scheme of every document
whose whole audience reads a source carrying it: every document, when it was typed on one every
role reads. The scheme is what `apps/ai/classification.py` lists in each classification prompt,
every value with no cap, and what the detail offers as `tag_options`.

- **`TAGGING_THROTTLE_RATE = "30/min"`,** per user, through `ScopedRateThrottle` like the other
  scopes, on that route alone (`DocumentTagsView`). As with search, the rate is not about the NPU,
  since applying a tag calls no provider; it bounds how fast one user can grow the vocabulary. The
  page sends one request per tag a person adds, so a person tagging by hand never meets it, and no
  script or load test calls the route.
- **Where the 429 sits.** DRF checks throttles in `initial()`, after authentication and the
  permission classes and before the view's method runs. The route's one permission class is
  `IsAuthenticated`, so an anonymous request is still 401, and past the rate the 429 comes before
  the scoped 404 and `contribute_content`'s 403. It is the same answer for every id, so it
  discloses nothing, as the search throttle answers before any query runs. Every request the
  throttle admits counts, a 400, 403, 404 or 409 included, and a throttled apply writes nothing.
- **The other tag routes stay unthrottled.** Confirming or removing a link and rejecting a proposal
  create no `Tag`. Confirming a proposed Topic can create one, but only from a proposal the
  classifier made, and classification is reached over HTTP only through upload, reprocess and
  classify, which share the `ingestion` budget.
- **What it does not do.** One user can still create 30 Topics a minute. Each stays in the scheme,
  and so in every later prompt and `tag_options` its audience reaches, until an Administrator
  retires it, and a person naming a retired Topic brings it back (D-105's finding 6, accepted).
  Capping the Topics the prompt lists would change the classifier's input, so it stays deferred.
- **Tested** in `apps/api/tests/test_throttles.py`, from both roles: past the rate an apply is
  DRF's 429 with `Retry-After` and writes no `Tag` and no link; past it, an id naming nothing, an
  Administrator-only document and a readable document the caller may not tag all get the same 429,
  where below it they were told apart by 404 and 403; and one user's budget is not another's, each
  way round. `test_configuration.py`'s walk of every route lists this one in the `tagging` scope.
- **The interface's 429 text** (`6b3e565`). The classification panel answered every 429 in
  classify's words, "The upload limit has been reached". The Add tag control now says the limit on
  adding tags was reached, with when to try again from `Retry-After`, and classify keeps its own
  words. Tested in `frontend/tests/documentClassification.test.jsx`, for the chooser and for a new
  topic.

## D-80 · The conversation list leaves out a thread nobody has asked anything in

**Status:** Settled by the user · **Date:** 2026-10-21 · **Stage:** 5 item 5 · **Closes:** D-58,
and D-61's gap 12

**Decision.** `GET /api/conversations` lists only the threads that have at least one `QueryLog`
row.

1. **The filter is an `Exists` subquery on `QueryLog`.** It is never on the "New conversation"
   title, which D-58 rules out, and never on what a turn renders. A thread whose every turn is now
   re-scoped, or whose only turn was a no-answer, still has rows and stays listed. Otherwise the
   list would show that something was withheld.
2. **`POST /api/conversations` is throttled per user**, in its own scope at the ask rate (D-79),
   so creating a thread doesn't spend the ask budget. It was unthrottled, and once empty threads
   are unlisted, nobody would see a script making them. The Ask screen creates at most one per
   first question, and #30's scripts never call it.
3. **Nothing is deleted.** FR-13's database clause is Create, Read, Update, and D-43 argued against
   inventing a verb. An empty thread stays reachable by its address (D-77) and is reused there.

**`docs/api-contract.md`** changes with this decision.

**Tested:**

- an empty thread is absent from the list, but `GET /api/conversations/{id}` still returns it;
- it appears once its first turn lands, answered or not;
- a thread whose turns are all re-scoped stays listed;
- a thread still titled "New conversation" that has a turn is listed;
- the create route answers 429 past its rate.

On the screen: an empty active thread is not in the list, and after its first turn it appears,
marked as current.

**What this decision does not cover.** Empty threads still accumulate as rows, bounded by the
create throttle. Nothing removes them.

> **Built on 26 October 2026, in item 5.**
>
> - **Three wrong filters were each tried as a deliberate break:** on the title, on
>   `answered = True`, and on readable citations. Each failed the tests written for it.
>   - The `answered` and citation filters also failed every list test whose threads held only
>     no-answer turns, or no citations.
> - **The contract's D-43 paragraph is corrected.** A thread with no turn is no longer listed, so
>   the placeholder title shows only on a thread whose first question was nothing but whitespace.

## D-81 · PDF extraction is bounded per stream and per document, and every PDF bound lands on "Too large to index"

**Status:** Settled by the user · **Date:** 2026-10-21 · **Stage:** 5 item 5 · **Corrects:** D-50,
which said PDF is open

**What D-50 missed.** pypdf 6.19.0 already caps each decompressed stream at 75 MB and raises
`LimitReachedError`. That does not bound one page. The user's measurements, with pypdf 6.19.0:

- **One page, one stream.** A 10 MB stream of `q Q` operators, in a 10 KB file, took 17.6 s and
  +671 MB, about 67 times the decoded size. At the default 75 MB that is roughly 5 GB for one page.
- **Pages sharing one stream** each re-parse it.
- **A form XObject is re-parsed on every `Do`**, and its content is not in the page's `/Contents`.
  A 2.7 KB file whose page calls one 2 MB form three times took 6.7 s, while its page content was
  a few bytes.

**Decision.**

1. **A lower per-stream cap.**
   - Every `*_maximum_output_length` field is lowered with `pypdf.apply_configuration(...)`,
     around both the `PdfReader` construction and the page loop. It is ContextVar-scoped, so
     other Waitress threads are untouched. `overwrite_configuration` is not used.
   - The value lives in `constants.py` with its reasoning, since the 3–38 KB corpus PDFs cannot
     size it. About 10 MB keeps vector-heavy real pages and bounds one page near 700 MB. A 2 MB
     cap failed the measured page in 0.01 s.
2. **A page cap.** `MAXIMUM_PDF_PAGES` = 2000, checked with `len(reader.pages)` before any page is
   parsed. That counts the real page tree, not the declared `/Count`. It sits well above the
   roughly 820 pages the text ceiling allows.
3. **An operator budget, counted across the whole document.**
   - It is counted with `extract_text(visitor_operand_before=...)`, which also sees operators
     inside forms and fires before each `Do`.
   - pypdf swallows an exception raised inside a form (it logs "Impossible to decode
     XFormObject"). So once the count is over budget, the counter keeps raising on every call,
     and the next page-level operator propagates it.
   - The value is set from a measurement on the laptop, in operators per second, for about 60 s
     worst case. It is not set from the user's sandbox figure of 1.76 s per MB. With a 1.5M budget
     the form file stopped after 4.6 s.
   - The recorded worst case is the budget plus one parse at the per-stream cap.
4. **A text ceiling.** Extraction stops once the whitespace-token count passes what
   `chunk_count_for_tokens` would refuse, and returns the text read so far, so the existing check
   in `documents.py` refuses it. That keeps one refusal path, not two.
5. **Every PDF bound lands on "Too large to index"**, the per-stream cap included.
   - `canReprocess` offers a retry on "Extraction failed", and a stream over the cap fails the
     same way on every retry (D-51's argument).
   - `pypdf.errors.LimitReachedError`, which is its own class and not a `PdfReadError`, is caught
     before the broad `except`.
   - Each limit has its own message, so the uploader knows whether splitting the file would help.
6. **D-50 is corrected.** pypdf's limits now live in `pypdf.Configuration`, and the module
   constants are deprecated.

**Tested:**

- **The bomb fixtures are real.** A crafted bomb page carries a `/Resources` font; without one,
  pypdf returns "" without parsing, and the test proves nothing. A form carries its own
  `/Resources`, for the same reason.
- **The per-stream cap:** a capped page fails fast. A stream over the cap reaches "Too large to
  index", which `canReprocess` refuses.
- **The operator budget:** a form-repetition bomb is stopped by it, and so is a shared-stream
  multi-page bomb.
- **The page cap:** a page tree that declares fewer pages than it holds is refused by it.
- **The text ceiling:** a document just under it indexes, and one just over gets "Too large to
  index".
- **The configuration itself.** A test reads the applied configuration during extraction, so a
  pypdf upgrade that renames the fields fails loudly instead of quietly returning to 75 MB.

**What this decision does not cover.**

- **The residual.** One page is still bounded only by the lowered cap times about 67 in memory.
  The worst case in time is the budget plus one parse at the cap.
- **A hard bound.** A subprocess with `setrlimit` is the hard bound if M8 runs on Linux. On
  Windows it would need Job objects.
- **DOCX and XLSX.** D-50 covers them, and nothing changes for them.

> **Clarified on 26–27 October 2026, when item 5 was built.** This adds one limit the user settled
> during the build, records the measured values, and corrects the messages.
>
> **A seventh setting: a stored-size cap, settled by the user during the build.** The decoded-size
> caps never see a stream stored without a filter, so an uncompressed content stream was bounded
> only by pypdf's 75 MB declared-length default and the 50 MB upload ceiling.
> `PDF_MAXIMUM_STORED_STREAM_BYTES` = 20 MB, its own constant, sets
> `maximum_declared_stream_length` in the same `apply_configuration` call. It is kept separate
> because stored size and decoded size are different limits.
>
> - **The user's measurements**, on pypdf 6.19.0 with the stored cap at 10 MB:
>   - A 12 MB image drawn on a page did not fail the document. pypdf skipped it, logged
>     "Impossible to decode XFormObject", and the page's text still came out.
>   - A 12 MB embedded font program that the page's text uses did fail, with or without
>     `/ToUnicode`. pypdf reads every font program a page uses but never decodes it, so only its
>     stored size counts.
>   - A PDF that embeds a whole CJK font, instead of a subset, can store more than 10 MB.
> - **Why 20 MB.** It admits those fonts, and it still bounds an uncompressed content stream at
>   about 1.3 GB, at the measured 67 times.
> - **An over-cap image or form is skipped, not refused.** Only page content streams and font
>   programs reach "Too large to index".
>
> **The values, measured on the laptop by the rag-pipeline agent** (pypdf 6.19.0, three runs per
> shape, other suites running):
>
> | Content | Operators per second |
> |---|---|
> | `q Q` on one page | 250,570–480,564 |
> | A form drawn five times | 208,913–301,245 |
> | One stream shared by ten pages | 215,299–349,260 |
> | Text lines (`BT`, `Tf`, `Td`, `Tj`, `ET`) | 31,979–72,114 |
> | `cm` | 21,671–23,337 |
>
> - **`PDF_MAXIMUM_OPERATORS` = 1,300,000:** 60 s at the slowest rate. That is `cm`, which yields
>   no text, so the text ceiling never stops it. D-81's 1.5M was the user's illustration.
> - **One parse at the 10 MB per-stream cap** (`PDF_MAXIMUM_STREAM_BYTES` = 10,000,000) took
>   14.9–15.7 s.
> - **The worst case is about 75 s:** the 60 s budget plus one parse at the cap. pypdf parses a
>   stream whole before the visitor sees its first operator, so the budget stops the next stream,
>   not the current one. The 75 s is arithmetic from the two measurements, not a measured run.
> - **Real documents sit far below the budget.** That is an estimate: no large real PDF was
>   measured.
> - **`MAXIMUM_PDF_PAGES` = 2000**, as settled.
> - **The pypdf fields set** are `array_based_stream_maximum_output_length`,
>   `jbig2_maximum_output_length`, `lzw_maximum_output_length`,
>   `run_length_maximum_output_length` and `zlib_maximum_output_length`, which bound decoded size,
>   and `maximum_declared_stream_length`, which bounds stored size. A renamed field makes
>   `apply_configuration` raise, and a test reads the configuration during extraction.
>
> **The messages, corrected.** Each D-81 bound has its own sentence saying whether splitting the
> file would help. The sentences first began "The document was stored, but …", and the meeting
> route also sends them, although nothing is stored there.
>
> - **The sentence stands alone now.** `TooLargeToExtractError.limit_message` carries just the
>   limit sentence.
> - **On `POST /api/documents` and reprocess,** the 422 detail is "The document was stored but not
>   indexed." followed by that sentence.
> - **On `POST /api/meetings`, with a PDF file,** the 400 `{"file": [...]}` carries the sentence
>   alone. Before this item, the route answered "No readable text could be extracted", which
>   misstated a size refusal. A test asserts the meeting message does not say "stored".
> - **The text ceiling keeps its own wording on both routes.** A meeting over it is stored, with
>   its transcript cut at the ceiling, so "The transcript was stored, but …" is true there.
>
> **Chosen by the rag-pipeline agent:**
>
> - **A second check for the operator budget.** As well as the counter that keeps raising, a
>   backstop check runs after each page.
> - **`TooLargeToExtractError` subclasses `ExtractionError`,** so a caller that doesn't know the new
>   class still never lets a bound escape as a 500.
> - **The page that crosses the text ceiling is returned whole.**
> - **pypdf's other `LimitReachedError`s get the per-stream message.** That covers page-tree depth
>   and arrays of 10,000 or more elements.
> - **The tests patch each bound down for speed.** The real values are used where it costs little:
>   the 12 MB font, the uncompressed stream over 20 MB, and the shipped-values test.
>
> **What the deliberate breaks found.** Six breaks, each restored and checked by hash.
>
> - **Two at first failed no test.** The counter raising only once was saved by the after-page
>   backstop. A missing text ceiling was saved by the chunk check in `documents.py`. Each got a test
>   of its own, and each break then failed it.
> - **The stored cap left at pypdf's default** fails the stored-limit tests. It does not fail the
>   12 MB font test, by design: that test guards against a false refusal.
>
> **Not covered.**
>
> - **Encrypted PDFs.** For an encrypted PDF, pypdf counts pages from the declared `/Count`. This is
>   untested.
> - **A long PDF transcript is stored cut short.** On the meeting route, a PDF transcript over the
>   text ceiling is refused by `meetings.py`'s chunk check, as before, with a 422. Since this item,
>   though, the transcript it stores holds only the text read up to the ceiling, not the whole
>   file. That takes a transcript of roughly 820 pages or more, and nothing tests it.

## D-82 · Item 5's branch carries the load tests, with one account per virtual user

**Status:** Settled by the user · **Date:** 2026-10-21 · **Stage:** 5 item 5 · **Concerns:**
NFR-08, NFR-09 and PR #30

**Context.**

- **Ownership.** Haseeb is leaving the project, so #30 is the user's now.
- **The collision.** Its two k6 scripts each log in once in `setup()` and hand that one session to
  every virtual user, so NFR-09's 20 VUs, and NFR-08's 5, would collide with D-79's limits.
- **How it was merged.** #30 is merged into item 5's branch as it is, so his commits stay his. The
  changes below are made on top of it, in item 5's PR. It was not merged to main directly,
  because a changes-requested review blocks it.
- **The run.** The user runs Objective 03 on 23 October against item 5's branch, then merges it.

**Decision.**

1. **One account per VU.** `setup()` logs in one account per VU, and each VU takes its own session
   by VU number. Both scripts do this.
2. **Paced logins.** Logins are at least 3 s apart. They all come from 127.0.0.1, and D-26 allows
   20 a minute per address, so the 21st would get 429.
3. **A baseline account.** NFR-09's baseline gets its own account, so its 50 uploads don't share
   an hour's budget with a load-phase user.
4. **Every account stays inside the limits.** VUs are sequential, which satisfies one in flight.
   Each iteration lasts at least 6 s, so no account passes 10 asks a minute when no-answer replies
   return quickly.
5. **Any 429 makes the run INVALID** in the validity gate, rather than a latency pass or fail.
6. **Test accounts.** A management command creates the test Employees on a local database. The
   password is taken from the environment and is never stored in the repo.
7. **Recording.** The results JSON records the commit SHA. The server is restarted before each run,
   so the in-memory throttle counters start empty.

**What this decision does not cover.**

- **NFR-09's uploads.** Its iterations each upload as well as ask. At 60/hour an account can make
  at most 60 uploads in the 10-minute load phase, which needs iterations of 10 s or more; a 6 s
  floor would allow 100. The build checks this against rule 4 and raises it rather than changing
  a rate. Rule 5 catches it either way.
- **Running the tests.** Nothing here runs Objective 03. The user does, on 23 October.

> **Clarified on 26 October 2026, when item 5 was built.** The rules stand. The test-engineer
> agent made three of the paces stricter than D-82's minimums, all of which D-82 states as "at
> least", for the reasons below.
>
> - **NFR-08's floor is 7 s, not 6 s.** DRF stamps a request when the view runs, and with 4
>   Waitress threads for 5 users a request can wait in the queue first. At 6 s, 11 asks span exactly
>   60 s, so one late stamp turns the 11th into a 429. A spacing of at least 60 / 9 = 6.67 s holds
>   however late the stamp. In the simulation, 6 s gave 429s as soon as queue waits reached 50 ms;
>   7 s gave none.
> - **Logins are 3.5 s apart, not 3 s,** for the same reason: 60 / 19 = 3.16 s. This one was not
>   tested separately.
> - **NFR-09's floor is 10.5 s, not 10 s.** At 10 s an account makes exactly 60 uploads in the
>   phase, which is the limit itself. At 10.5 s it makes at most 58. This is a precaution, not a
>   demonstrated failure.
> - **Each script refuses to start if a value falls below the bound it relies on.**
>
> **Other choices:**
>
> - **`setupTimeout`** is computed in code from each setup step's worst case.
> - **`GIT_SHA` is required.** Without 7–40 hex digits the script refuses to start.
> - **The baseline account is chosen by scenario,** not by VU number.
> - **Every login must be an Employee.**
> - **No silent PASS.** A run that measured nothing reports NO DATA, not PASS.
> - **The 300 s ask timeout is kept.** It is shorter than the server's worst case.
> - **The account command.** It refuses to run with `DEBUG` off unless `--i-know-this-is-local` is
>   passed, and the alpha runs with `DEBUG=False` (D-64). It resets an existing account's password
>   and lockout, and refuses outright if an existing account isn't an Employee.
>
> **Not covered.**
>
> - **k6 was never run.** It is not installed on the laptop. The scripts were run only in a Node
>   simulation of k6's modules, so k6's own parser, its scheduler and its cookie handling are
>   unverified.
> - **The verdict is in the results JSON, not the exit code.** k6's exit code does not reflect the
>   429 gate.
> - **Cleanup.** One NFR-09 run leaves up to 1,210 TXT documents behind, in department
>   `LoadTest`, uploaded by Employees. #30's review called that blocking, and nothing here cleans
>   them up.
> - **Objective 03 on 23 October** could not run against this branch: item 5 was not built until
>   26 October.

> **1 November 2026: "the 300 s ask timeout is kept" no longer holds. k6's ask timeout now
> outlasts the server's in-flight slot,** at the user's instruction.
>
> - **Why.** NFR-08's first run (5 VUs, 100 asks) was INVALID for exactly the gap this decision
>   accepted. k6 abandoned asks at 300 s while the server was still answering them, and each
>   account's next asks were refused with `ask_in_flight`: 67 of them. The summary is kept as
>   evidence in `corpus/objective-02/runs/2026-11-01/`.
> - **The new value.** `ASK_TIMEOUT_S` is `ASK_SLOT_TIMEOUT_S` + 60 s, 2,835 s. `common.js`
>   copies the slot's 2,775 s, and `apps/api/tests/test_load_test_timeout_agreement.py` holds the
>   copy equal to the server's.
> - **NFR-08's other changes:**
>   - `maxDuration` is derived from the ask timeout, so k6 never interrupts an ask in flight;
>   - `ITERATIONS` drops from 100 to 25, so the rerun fits the gate day;
>   - concurrency stays 5.
> - **A single-user end-to-end baseline** (1 VU, 20 asks) runs first, as its own result. The
>   8.90 s baseline times generation alone.
> - **Where it is recorded.** The run record, `nfr08-runs.md` in the same folder, was written
>   before the rerun. It also holds what the logs show about generation attempts in the first
>   run.
> - **Not covered:**
>   - NFR-09 inherits the timeout. Its phase durations were not revisited.
>   - A 503 still counts as a failed request, so one 503 in 25 asks invalidates the rerun.
>     *Superseded the same day by the note below.*

> **1 November 2026, later: in NFR-08 a 503 is scored as a miss, not treated as a harness failure,**
> at the user's instruction.
>
> - **The rule changed after run 1 showed two 503s in 100 asks.** Under the old rule, one 503 in
>   the rerun's 25 asks would have invalidated it.
> - **The reason.**
>   - A 429 or a timeout means the harness failed: the run did not measure what it set out to.
>   - A 503 means the system failed. It is NFR-19's designed response, so it is a result.
> - **How a 503 is scored.** NFR-08 is an answer within 4 s for 90% of requests, and a 503 is a
>   request that got no answer within 4 s. So each 503 is a miss:
>   - it goes into the p90 sample, ranked slower than any answered reply;
>   - it is also reported on its own, as `server_503`;
>   - the verdict's p90 is `p90_ms`. When the 90th-percentile request is a 503, `p90_ms` is `null`
>     and the verdict is FAIL.
> - **What still makes a run INVALID:** a 429, a k6 timeout, any other status, or a missing SHA.
>   `http_req_failed` treats only 200 and 503 as expected for the measured asks, and the check
>   accepts the documented 503 body, so `checks rate>0.99` no longer fails on one.
> - **Run 1 is not re-scored.** It stays INVALID as recorded, and its answered-only p90 is
>   reported as `p90_answered_ms`, which every run still carries.
> - **Tested.** `apps/api/tests/test_nfr08_k6_scoring.py` runs the real script under k6 against a
>   stub, with three outcomes:
>   - every ask answered: PASS, with a p90 in milliseconds;
>   - one 503: the run is valid, and the p90 falls on the 503, so it reads FAIL;
>   - one 500: INVALID.
>
>   It is skipped where k6 is not installed, which includes CI.
> - **Failed provider attempts are now logged** (`apps/ai/attempt_log.py`), also at the user's
>   instruction, so the rerun can show what run 1 could not.
>   - **What a line holds:** each failed generation or question-embedding attempt, with its cause,
>     its seconds and the account, and the cause of each 503. They are WARNINGs on
>     `apps.ai.attempts`, written to the error file by a handler of their own.
>   - **What stays the same:** behaviour and attempt counts.
>
>   The rerun runs on a later commit than the single-user baseline, and the server code differs
>   only by this logging.

> **1 November 2026: NFR-08's results, and NFR-09 not run.** The evidence is in
> `corpus/objective-02/runs/2026-11-01/`. Every run used dump `3bf98403…6f59`, FLM v0.9.39, and
> Waitress at 24 threads.
>
> | Run | Users / asks | Commit | Result |
> |---|---|---|---|
> | 1 | 5 / 100 | `b8d8304` | INVALID under the old rule (67 × 429 after k6's 300 s timeout; 2 × 503) |
> | 2 | 1 / 20 | `945fd02` | INVALID under the old rule (2 × 503); answered-only p90 51 s |
> | 3 | 5 / 25 | `eed8249` | **Valid, FAIL:** 3 × 503, so the p90 falls on a 503; answered-only p90 277 s |
>
> - **What run 3's attempt log confirms:**
>   - One 4B model on one NPU divides its time among concurrent asks, as D-35 implies. A failing
>     generation took about 58 s alone and up to 174.5 s with others running.
>   - All 13 failed attempts were replies that stopped before their JSON closed. None timed out.
>     So the 503s are not caused by queueing. The same question failed the same way at one user.
>   - Those discarded attempts also took NPU time from every other ask.
>   - The reply being cut off at `GENERATION_MAX_TOKENS` is the likely reading, not observed.
> - **Not tuned.** NFR-08 is not in the M6 gate.
> - **NFR-09 was not run,** by the user's decision on the evidence of runs 2 and 3. At 5 users the
>   answered-only p90 is already about +440% over one user, and NFR-09 allows 25% at 20 users.
>   Its failure is recorded as a prediction, not a result.

**Dated note, 7 November 2026: the team is two people.** This entry's "Haseeb is leaving the
project" is now complete. At the user's request he is removed from the project's current
documents.

- **`CLAUDE.md` §1 lists two members:** Benjamin Morovan and Sagarika Dey.
- **Haseeb's areas pass to Benjamin Morovan:** database, auth & RBAC, retrieval scoping, security
  and NFR verification. So does any task still assigned to him, such as the final security
  review (item 11). That was the user's decision.
- **Two transcripts in code that used his name now use a fictional speaker:** a test fixture
  (`apps/ingestion/tests/test_meetings.py`) and the component sheet's sample.
- **Records of what he did stay as written:** this entry, D-01's Python versions, and
  `docs/two-week-plan.md`. So do his commits.

**Dated note, 7 November 2026: the 503 is reproduced, and every failed attempt observed was a reply
cut off at `max_tokens`.** This is step 7, phase 1, of the user's post-M6 order: "Observe before
changing anything". The 1 November note above calls a cut-off at `GENERATION_MAX_TOKENS` "the
likely reading, not observed". The evidence is in `corpus/objective-02/runs/2026-11-07/`.

- **What changed: logging only.** Every generation attempt now logs its `finish_reason`,
  completion and prompt tokens, and the `max_tokens` sent (`apps/ai/attempt_log.py`).
  - A failed attempt is a WARNING, as before. A parsed attempt is an INFO line.
  - The shipped LOGGING keeps that logger at WARNING, so a running server does not record the INFO
    line.
  - `max_tokens` (800), the prompt, the temperature (0.0), the three attempts and the schema are
    unchanged.
- **How it ran.**
  - In-process, through the shipped `answer_question`, as an Employee (`loadtest01`, with no
    conversation, as `tests/load/common.js` asks), on `kmp_obj02_20261101` with FLM v0.9.39.
  - 19 asks: "How are records managed and retained?" 10 times, interleaved with three questions
    NFR-08 answered, 3 times each.
  - Each ask was rolled back, so no row was committed.
- **What was observed:**
  - **The 503 reproduced:** 4 of 10 asks of the records question, and 1 of 3 of "What are the
    rules for acceptable use of IT equipment?". Leave and complaint answered 3 of 3.
  - **38 attempts:** 23 parsed and 15 schema violations, every one "unbalanced JSON object in the
    response". No timeouts and no FLM errors.
  - **All 15 failed attempts ended at exactly 800 of 800 completion tokens,** with the JSON still
    open. Every parsed attempt ended below 800, between 90 and 796.
  - **`finish_reason` was `stop` on all 38.** FLM v0.9.39 never reported `length`, even for a reply
    cut off at the ceiling. So `finish_reason` cannot show the cut; the token count can.
  - **No retry recovered an ask.** Each answered ask parsed on attempt 1. Each ask whose attempt 1
    failed failed all three.
  - **Retries at temperature 0 changed the text, not the length.** Each 503 ask's three attempts
    were three different texts, all cut at 800. Asks 11, 12 and 13 repeated the same three texts
    in the same order. On 1 November, two asks recovered on attempt 3; here none did.
  - **The cut replies are long statement lists.** Each holds 10 complete statements (7 or 8 for the
    IT question), with the next one open. They diverge from each other after a shared opening;
    they are not one text cut at different points.
  - **On the records question, the outcome followed the passage order.** Retrieval supplied the
    same 8 passages in two orders, with the 6th and 7th swapped. Their cosine scores differ by
    0.000008.
    - Order A: 5 of 5 asks answered, at 252 or 442 tokens.
    - Order B: 1 of 5 answered, at 796 tokens. The other four were 503s.
    - Which order a given ask got was not controlled.
- **What it does not show:**
  - **The 1 November replies themselves.** Their token counts were not recorded. The question, the
    code path and the message match, but the time does not: run 3's uncontended failures took 56
    to 59 s; an 800-token reply today took 79 to 113 s. So a cut-off at 800 on 1 November is still
    inferred.
  - **Why identical requests got different replies, or why the query vector moved during the
    run.** Neither was isolated.
  - **Whether a higher ceiling or a shorter answer would end the 503s.** Nothing was changed to test
    that. Those are phase 2 decisions.

## D-83 · FLM is pinned to v0.9.39, and `check_flm.py` gates every measurement run and the alpha

**Status:** Settled by the user · **Date:** 2026-10-27 · **Stage:** 5 item 6 · **Found:** FLM
v1.0.9 installed on 15 October, with its embeddings noise again

**What happened.** On 27 October, while item 6 was being planned, `C:\Program Files\flm\flm.exe`
was found at **v1.0.9**, with the file dated 15 October. `scripts/check_flm.py` failed. The same
input embedded twice in one request gave a cosine of 0.6046, against the 0.999 required. Chat still
worked. So for twelve days every question embedded as noise against a good stored index, and
retrieval could not have found the right passages. Nothing caught it: the suite runs on a stub
provider, so CI cannot see FLM, and nothing ran `check_flm.py`.

**Decision.**

1. **The required version is v0.9.39.** From v1.0.4 onward, FLM's embeddings are non-deterministic
   (upstream issue ROCm/FastFlowLM#732, still open). The version is recorded in `CLAUDE.md` §4,
   `docs/ai-provider.md` §3 and the README's setup steps, not only in a session's memory.
2. **The stored index was checked after the reinstall.** `check_flm.py` passes on v0.9.39. Chunks
   sampled from each upload date in `kmp` were re-embedded exactly as ingestion embeds them and
   compared with their stored vectors:
   - 22 September: cosine 1.00000;
   - 5 October: at least 0.99983.

   Both are above 0.999. Nothing was embedded after 15 October, so nothing is re-indexed.
3. **`check_flm.py` is a gate.** Item 6's measurement runs, the k6 runs and the alpha runbook
   (item 9) call it first and stop on a non-zero exit. Every results file records the FLM version.
4. **Newer FLM releases are evaluated after M8.** A version whose vectors differ means a full
   re-index and a re-run of Objective 02's search checks.

**What this decision does not cover.**

- **What upgraded FLM on 15 October.** Nothing records whether it was a manual install or an
  updater.
- **An enforced pin.** Nothing stops an installer upgrading FLM again. The gate catches it; it
  doesn't prevent it.
- **CI** still cannot see FLM.

## D-84 · Item 6 measures a fresh Objective 02 database, on a frozen thirty-question set, and Objective 03's p90 at five users

**Status:** Settled by the user · **Date:** 2026-10-27 · **Stage:** 5 item 6 · **Concerns:**
Objective 03, FR-12, FR-13, NFR-08

**Decision.**

1. **The database: a fresh one holding exactly Objective 02's corpus**, ingested by
   `scripts/ingest_objective02.py` on working FLM. `kmp` stays as it is.
   - **The 6 October evidence is kept.** The script always writes
     `corpus/objective-02/results.json` and `results.md`, so a second run would overwrite them. It
     gains an output-directory option, and this run writes to a dated folder.
   - **Its own paths.** The measurement server has its own `DATABASE_URL`, `MEDIA_ROOT`,
     `AUDIT_LOG_PATH` and `ERROR_LOG_PATH`. Otherwise the corpus files and the load test's uploads
     would land in `kmp`'s media folder. All four are already read from the environment.
   - **A snapshot first.** Right after ingestion, before anything is measured, the database is
     dumped and its media copied. The dump's hash is recorded with the commit SHA and the FLM
     version.
   - **Order of the runs.** The thirty questions run before the load test, or the dump is restored
     first. NFR-09 uploads a kitchen-roster document every round, and those would become retrieval
     candidates for the questions.
   - **The demo database is a separate decision.** Whether the 1 November demo runs on `kmp` or on
     the restored measurement database is not decided here.
2. **The question set.**
   - **Drafted by the rag-pipeline agent** from the corpus files and the manifest only, never from
     the system's answers.
   - **Worded the way a staff member would ask it**, not by copying the manifest's phrase. That
     would only test word overlap.
   - **The 64-set's proportions:** 22 ordinary, 4 scoped and 4 no-answer. They are spread across
     all four formats and the five transcripts, and each has an expected answer and its source
     item id.
   - **Every scoped question is asked under both roles.** There are five Administrator-only items,
     and a scoped question only shows scoping if the Administrator gets the answer and the
     Employee gets the no-answer state.
   - **Benjamin and Sagarika review and approve the set.** It is then committed, and frozen before
     the first measured run. Any later change is recorded with its reason. The report says an agent
     drafted the set and they reviewed it.
3. **Objective 03's p90 is measured at five concurrent users.** That is NFR-08's script default and
   a small-team load. 20 users is kept for NFR-09's degradation test. The choice is recorded here,
   before the run, so it can't look picked for the result.
   - **A miss is expected.** The single-user p90 is already 8.90 s, and one NPU answers one
     question at a time, so five users queue.
   - **What is reported:** the answered-only p90 against 4 s, with the all-replies p90, the
     answered rate and the 8.90 s baseline beside it, plus the commit SHA, the FLM version and the
     dump hash.
   - **A miss is then recorded as a decision**, as the risk register says: a local-model baseline,
     not a dropped NFR.
   - **How it runs.** It is gated on `check_flm.py`, with the server restarted first. NFR-09 runs
     separately afterwards. The user installs k6 and runs it.
4. **What item 6 re-measures**, from the brief: `RELEVANCE_THRESHOLD` (D-37), the partial-matches
   floor (D-56), the three citation rates, p90, and FR-13 end to end.

**What this decision does not cover.**

- **The demo database** for 1 November.
- **The measured values.** A new threshold or a partial-matches floor is a later decision, made
  from this measurement.
- **The k6 runs themselves.** The user runs them.

> **The thirty questions are frozen, on 1 November 2026.** Benjamin Morovan and Sagarika Dey
> approved them as written on 1 November.
>
> - **Accepted alternatives were added before the freeze, at the user's request.** The harness
>   scored the expected phrase as a literal substring, and 17 of the 26 answerable questions expect
>   number words or a date, so a correct "12 characters", "$75", "10%" or "7 am to 6 pm" would have
>   scored as not found.
>   - **What each question now carries.** It has an `accepted` list: digit, currency, percent, date
>     and time forms of the same fact.
>   - **How they match.** An alternative matches only as whole tokens, so "5 years" can't match a
>     wrong "15 years", nor "23" match "2023". The expected phrase still matches as a substring, so
>     the approved set scores as it did.
>   - **Recorded per run:** which form matched.
> - **No question, expected answer or source changed.** This was checked field by field against
>   the approved file.
> - **Benjamin Morovan asked some of the questions informally before the set was frozen.** No
>   question, expected answer or source was changed because of what the system answered.
> - **Neither retrieval nor the prompt was tuned against this set** before the measured run.
> - **The harness reports each miss:**
>   - whether the expected source was a candidate for the role, and at what rank;
>   - its best score against `RELEVANCE_THRESHOLD`;
>   - where the run ended: path A, path B, unavailable, or answered without the expected answer.
>
>   So the fixes after M6 aim at causes. The coordinating session built this directly, after the
>   rag-pipeline agent stalled.

> **1 November 2026: the demo database is decided, by D-88.** It is `kmp_demo_20261101`, restored
> from this decision's measured snapshot. It is neither `kmp` nor the measurement database. That
> closes "the demo database for 1 November", which this decision left open.

## D-85 · The measured run is served by Waitress with 24 threads, the value the alpha will use

**Status:** Settled by the user · **Date:** 2026-10-27 · **Stage:** 5 item 6, pulling forward the
slice of item 9 that the measurement needs · **Concerns:** Objective 03, NFR-08, NFR-09, D-64

**Decision.**

1. **Waitress is added now**, to `requirements.in`, with `requirements.txt` recompiled. It is pure
   Python, so there are no compiled parts for CI or the laptop to trip on.
2. **The measured run is served by**
   `waitress-serve --listen=127.0.0.1:8000 --threads=24 config.wsgi:application`, under
   `DEBUG=False`. The thread count is set explicitly: Waitress defaults to 4, which NFR-08's five
   users already exceed and NFR-09's twenty far exceed.
3. **24 threads, chosen before the run.** That is NFR-09's stated 20 concurrent users plus 4 for
   screens, logins and uploads. A load run then waits on the NPU rather than in Waitress, and the
   app's other routes stay answerable while asks wait. FLM answers one question at a time, so
   threads change where a request waits, not how fast it is answered.
4. **Recorded beside every result:** the server, its version and the thread count.
5. **Still item 9's:** serving the built SPA from one origin, `CSRF_TRUSTED_ORIGINS` and the cookie
   flags. The load test calls only `/api/`.

**What this decision does not cover.**

- **Holding every thread.** With 24 threads, asks alone need 24 users asking at once to hold them
  all. Ingestion, though, is rate-limited only (D-79), so one user firing uploads concurrently
  could still hold them.
  - No client of ours sends uploads concurrently. The Upload screen sends one at a time, and the
    ingest script and the k6 virtual users are sequential.
  - The in-flight slot is extended to the three ingestion routes if that is cheap. Otherwise the
    gap is recorded here.

> **Built on 27–28 October 2026, in item 6's phase 2.** This records what was built and what the
> build found.
>
> - **Waitress 3.0.2** is pinned in `requirements.in`. The recompiled `requirements.txt` adds only
>   that line.
>   - **The shared venv.** The venv is shared with the main checkout, whose `requirements.txt` has no
>     Waitress, so a `uv pip sync` run there would remove it until this branch merges.
> - **The serve probe.** It ran Waitress with `--threads=24` and `DEBUG=False`, against a database
>   that doesn't exist. `/api/` answered 401 JSON with `Server: waitress`. Non-API paths answered
>   the JSON 404, because nothing serves the SPA yet; that is item 9's job.
> - **The ingestion slot was cheap, and is built.**
>   - **One slot per user**, shared by upload, meeting ingest and reprocess. It is separate from the
>     ask slot, so one user can hold at most two threads.
>   - **When it's held.** It is taken after each route's own refusals, and released in `finally`
>     straight after the ingest call, with the token check.
>   - **No timeout.** The derivation D-79 used would give about three weeks, and a timeout could
>     only free the slot while its ingestion still held a thread.
>   - **The 429.** It is `{"detail": "Your previous upload is still being processed.", "code":
>     "ingestion_in_flight"}`, with no `Retry-After`, and it counts against the ingestion rate.
> - **The premise was not quite true.** D-85 said no client of ours sends uploads concurrently, but
>   the Upload screen could. A failed row's retry was pressable while the queue ran, and a retry
>   re-enabled the Upload button mid-queue.
>   - Both are fixed. A row's retry is disabled while the page is busy, and busy is now a count of
>     runs in progress.
>   - Each screen shows the in-flight 429 in its own words, with no time given.
> - **The k6 scripts** record the server, Waitress's version and the thread count, and count 429s by
>   `code`. Each run also records the `Server` header its logins saw, and a mismatch with the stated
>   server is INVALID.
>   - **The thread count is as stated by the operator.**
>   - **`server_record.py` observes it** from the listening process's command line. The runbook
>     saves that observation next to each k6 summary.
> - **Found, and left to item 9:**
>   - **500s are HTML.** Under `DEBUG=False`, a 500 is Django's HTML page, not JSON, because no
>     `handler500` is set.
>   - **A disallowed `Host`** gets a 400 HTML page.
>   - **Waitress's own log lines are dropped** by `LOGGING`. That includes the "Task queue depth"
>     warning, the one that shows all 24 threads busy.
> - **Found on the Upload screen, and not fixed:**
>   - removing a queued file, or editing its title, while the queue runs has no effect;
>   - a successful retry still offers "Try again", which then answers 409;
>   - leaving the screen mid-queue doesn't stop the queue.
> - **Not covered.**
>   - **The two in-flight codes can drift.** Nothing tests that the client's copies match the
>     server's.
>   - **The cache can evict a slot.** `LocMemCache` culls entries past its default of 300, which
>     could evict a slot or a counter early under many active users. That is not reachable at the
>     alpha's scale.

> **Followed up on 28 October 2026, before the measured run.** The user had three of the Upload
> screen's findings above fixed, and the fourth recorded for item 8. The entries above stand as
> what was true when they were written.
>
> - **A queued file is held while the queue runs.** Its title field and its Remove button are
>   disabled until the queue finishes, then given back. The queue sends the rows as they were when
>   Upload was pressed, so an edit was ignored, and a removed file was still uploaded. An Employee
>   could not then delete it, because deletion is Administrator-only (D-73). Rows the queue never
>   held, such as a file refused client-side, keep their actions.
> - **A successful retry withdraws "Try again"**, as an upload that succeeds first time offers none.
> - **The client's codes are tied to the server's.** `apps/api/tests/test_in_flight_codes_agreement.py`
>   reads `ASK_IN_FLIGHT_CODE` and `INGESTION_IN_FLIGHT_CODE` from the front-end files and fails if
>   either differs from `apps/api/views.py`. It also fails if any other `*_CODE` the client exports
>   has no server constant of the same value. "The two in-flight codes can drift" above no longer
>   holds.
> - **Left for item 8's live run:** leaving the Upload screen mid-queue still doesn't stop the
>   queue. It is recorded with the other manual checks in `docs/stage-5-clause-audit.md`.
> - **What the hold does not cover.** It is the `disabled` attribute. A Remove landing in the same
>   instant as Upload, before the screen re-renders, would still be uploaded. Item 6's retry test
>   shows that window exists. For a retry the server's in-flight 429 closes it; for a removal
>   nothing does.

**Dated note, 11 November 2026: the serve command gains a body cap (D-124).** Decision 2's command
becomes
`waitress-serve --listen=127.0.0.1:8000 --threads=24 --max-request-body-size=54525952 config.wsgi:application`.

- **What the flag does:** it caps any request body at `MAX_REQUEST_BODY_BYTES`. Waitress's default
  is 1 GB.
- **What it does not touch:** anything a measurement measures. `scripts/server_record.py` neither
  records nor checks the flag. Its `D85_COMMAND`, the command the scripts print when they refuse a
  server, now includes it.
- **Runs recorded before this date** were served without it.

## D-86 · FR-13 is measured end to end on frozen two-turn threads, built beside Objective 03 and never ahead of it

**Status:** Settled by the user · **Date:** 2026-10-27 · **Stage:** 5 item 6 · **Concerns:**
FR-13, D-42, D-84 §4

**Why it needs its own set.** The harness's `--with-history` mode holds retrieval constant on
purpose: it embeds the bare question. So it does not measure FR-13 end to end. FR-13 really
embeds the plain join of the earlier questions and the new one.

**Decision.**

1. **Objective 03 runs first.** FR-13 end to end is built alongside it, and never delays it.
2. **A thread set.** About eight two-turn threads, drafted by the rag-pipeline agent from the corpus
   files only, as the thirty were.
   - **No follow-up can be answered cold.** Each one depends on the first turn, through a pronoun
     or a dropped subject. A follow-up that already works cold proves nothing about history.
   - **Two threads turn to Administrator-only material.** Each is run under both roles, so the
     Employee's no-answer shows scoping, not a retrieval miss, and nothing may leak.
   - **One thread changes topic.**
   - **One thread's follow-up refers to something only in the previous answer.** Under D-42 it
     should fail. Measuring that turns the deviation into evidence rather than an argument.
3. **One frozen scoring rule.** It is frozen with the threads and is the same for all three ways
   each follow-up is run: with history, asked cold, and spelled out in full.
4. **What is reported per follow-up:**
   - the answered rate;
   - the expected source's rank;
   - the expected-answer match;
   - the split between no-answer paths A and B;
   - the fabrication rate;
   - first-attempt conformance;
   - the out-of-scope count, which must be 0.
5. **How it is run.** A harness `--threads` mode composes the retrieval string and the prompt with
   the shipped code. `apps/retrieval/conversation.py` exposes a pure `compose(question,
   prior_questions)`, and a test pins the two together. The harness writes nothing.
6. **A small HTTP check.** Two or three threads go through `/api/conversations` and `/api/ask`,
   to prove the history read from `QueryLog` is wired correctly. It runs after the harness and
   before k6, with asks paced at least 7 s apart. It writes only `QueryLog` and `Conversation`
   rows, which are not retrieval candidates.
7. **Review and freeze.** Benjamin and Sagarika review the threads with the thirty, and both sets
   freeze together.

**What this decision does not cover.**

- **Threads longer than two turns.** History is truncated at `MAXIMUM_CONVERSATION_TURNS`, and
  that limit is not measured.
- **Prior answers.** D-42 still passes prior questions only. The previous-answer thread measures
  the cost of that; it does not change it.

> **Built on 27–28 October 2026, in item 6's phase 2.** The thread set is a DRAFT until Benjamin and
> Sagarika approve it with the thirty.
>
> - **Nine threads, not eight.**
>   - Five ordinary threads, one per format.
>   - The two scoped threads, each run under both roles.
>   - The topic change.
>   - The previous-answer thread.
>
>   That is 11 thread-and-role pairs, and 44 runs.
> - **The scoring rule is version 1, frozen in `threads.json` and `threads.md`.** It sets:
>   - what a run is, and what counts as answered;
>   - one outcome per run (answered, path A, path B declined, path B rejected, or unavailable);
>   - the expected-answer match: a listed phrase, and a cited listed source;
>   - what counts as a leak;
>   - the readings and the predictions, decided before the run.
>
>   A failed prediction is reported as measured, never re-scored.
> - **`compose()` is pinned to the shipped pipeline** three ways by `test_compose.py`. Behaviour is
>   unchanged.
> - **The harness's candidate set now uses D-66's effective roles**, as `scoping.py` does. On this
>   corpus it selects the same chunks.
> - **Where the build departs from D-86 as written:**
>   - **The topic change can be answered cold.** It has nothing to refer back to, so it is the
>     declared exception: it measures whether carrying the first question hurts.
>   - **The HTTP check writes more than D-86 says.** As well as `QueryLog` and `Conversation`, it
>     writes an answered turn's citation rows, a session, the last-login time and an audit line.
>     None of them is a retrieval candidate.
>   - **t09 may not fail.** D20, which its first question retrieves, names the facilities team. The
>     result is reported as measured.
>   - **Each way is run once**, so the answered rate is a rate across follow-ups.
> - **The run order the agent chose.** First the thirty questions, then NFR-08, FR-13's thread run,
>   the HTTP check, and NFR-09 last.
>   - **Why.** §1's "never delays it" read as a priority rule, and §6's "before k6" read as
>     protecting the corpus from NFR-09's uploads. NFR-08 writes nothing the thread run reads.
>   - **Still open.** It is put to the user, as is whether `run.ps1` should call `server_record.py`
>     to observe the thread count rather than take it as stated.

> **The nine threads are frozen, on 1 November 2026.** Benjamin Morovan and Sagarika Dey approved
> them with the thirty on 1 November.
>
> - **The scoring rule is now version 2.** Each turn gained the same kind of accepted alternatives
>   as the thirty, matched only as whole tokens. Part 4 says so, and the rule records the change and
>   its reason.
> - **Nothing else changed:** no phrase, source or expectation. The informal-asking note applies to
>   the threads too.
> - **D-87 settled the order.** FR-13's thread run follows NFR-08, and the user has moved it after
>   the gate.

## D-87 · The measured run's order and pre-flight: the server observed, `DEBUG` confirmed off, and Waitress's queueing logged

**Status:** Settled by the user · **Date:** 2026-10-28 · **Stage:** 5 item 6 · **Concerns:** D-84,
D-85, D-86, Objective 03, NFR-08, NFR-09

**Decision.**

1. **The order:**
   1. the thirty questions;
   2. NFR-08 (k6);
   3. FR-13's thread run;
   4. the HTTP check;
   5. NFR-09 (k6), last.

   This settles the choice D-86's note left open. D-86 §6's "before k6" is read as protecting the
   corpus from NFR-09's uploads. NFR-08 writes nothing the thread run reads.
   - **All item 6's code is committed before the first measured run,** front end included, so the
     SHA recorded beside each result is the code that ran.
   - **The server is restarted before each run that goes through HTTP:** NFR-08, the HTTP check and
     NFR-09. Throttle counters and in-flight slots left in memory by one run then can't 429 the
     next.
2. **`run.ps1` observes the server and doesn't take it as stated.** Before k6, it runs
   `scripts/server_record.py` and refuses unless it observes Waitress with `--threads=24`, or the
   override.
   - **A missing `--threads` reads as 4.** That is Waitress's default, so the run is refused rather
     than reported as "unknown".
   - **`DEBUG` is confirmed off.** The wrapper requests an unmatched `/api/` path and requires the
     JSON 404. Under `DEBUG`, Django bypasses `handler404` and serves its HTML page. The repo's
     `.env` sets `DEBUG=True`, so a server started from the usual shell runs in debug unless the
     runbook overrides it.
   - **`check_flm.py` still runs first.**
   - **Every observed value is written into the results file.**
3. **A `waitress` logger, before the measured run.** It logs at INFO, with timestamps, to its own
   file beside `errors.log`, at a path read from the environment like the others.
   - **It keeps propagating,** so a Waitress ERROR still reaches `errors.log`.
   - **`run.ps1` copies any "Task queue depth" lines** from the run's window into the results, or
     records that there were none. Queueing is then observed and reported, not left in a file.
   - **Why nothing shows today.** `waitress-serve` imports the app first, and Django's `LOGGING`
     gives the root logger its ERROR handler. So Waitress's own `logging.basicConfig()` does
     nothing, and even its "Serving on" line is dropped. The new file brings it back.

**What this decision does not cover.**

- **The restart is a runbook step.** Nothing proves the operator restarted the server, beyond
  whatever the new log shows.
- **The thread count is observed from the command line,** not from inside Waitress.

> **Built on 28–31 October 2026, in item 6's phase 3.** This records what was built, and the choices
> D-87 left open.
>
> **The `waitress` logger** (django-backend agent):
>
> - **Where it writes.** It logs at INFO to `WAITRESS_LOG_PATH`, which defaults to
>   `logs/waitress.log`, in the error file's format: `%(asctime)s %(levelname)s %(name)s
>   %(message)s`, in local time with no zone.
> - **How it's set up.** It propagates, so a Waitress ERROR also reaches `errors.log`. It has no
>   console handler, and with `delay=True` no empty file is created.
> - **A test pins the logger names** `waitress` and `waitress.queue` to Waitress 3.0.2's own
>   loggers, so a version that renames them fails a test rather than going silent.
> - **Proven on a real Waitress**, with one thread and no database. Before the change nothing was
>   written at all, not even "Serving on", which confirms D-87's cause. After it, the file held the
>   "Serving on" line and 65 forced "Task queue depth" lines, each timestamped.
>
> **`run.ps1`'s pre-flight** (test-engineer agent):
>
> - **The order of checks.** `check_flm.py` still runs first. `scripts/server_record.py
>   preflight` then reads:
>   - the listening process's command line, where the last `--threads` wins and a missing one
>     reads as 4;
>   - its start time;
>   - Waitress's version, from the server's own venv;
>   - the DEBUG probe. That is off only for the exact JSON 404 on `/api/__preflight_not_a_route__`,
>     on only for Django's HTML debug page, and unknown otherwise.
> - **Each rule is enforced twice,** in `server_record.py` and again in `run.ps1` on the values it
>   passes to k6.
> - **The restart is checked from the log.** The last "Serving on" line before the run must be
>   later than the newest record in `tests/load/results` and in `-ResultsDir`. That includes the
>   harness's and the HTTP check's records, so the server must start after each of those runs.
> - **Two checks beyond D-87:**
>   - the log's start must not predate the listening process's, so the log can't be another
>     server's;
>   - the process listening at the end must be the one observed at the start.
> - **After k6, a `finalise` step** copies the run window's "Task queue depth" lines into the
>   results, or records that there were none. It marks the run INVALID if a "Serving on" line falls
>   inside the window. Exit code 3 means k6 ran but the run is not recorded.
> - **The log's path** comes from `-WaitressLog`, else from `WAITRESS_LOG_PATH`, else the run is
>   refused.
> - **Refusals shown on the real Waitress**, on scratch ports and against a database that doesn't
>   exist:
>   - no `--threads`;
>   - a stated count that differs from the observed one;
>   - DEBUG on;
>   - a server not restarted;
>   - a log from before the listening process;
>   - no log;
>   - a server that isn't Waitress;
>   - nothing listening.
>
>   One real run at one thread copied 23 genuine queue-depth lines.
> - **The runbook and `tests/load/README.md`** follow D-87 §1's order. They set `DEBUG='False'` and
>   `WAITRESS_LOG_PATH` before each server start, and require a restart before NFR-08, the HTTP check
>   and NFR-09.
> - **Its 29 tests were moved into `apps/`.** The agent drafted them in the scratchpad, because its
>   brief kept it out of `apps/`, and the coordinating session moved them to
>   `apps/ai/tests/test_server_record_preflight.py`, since pytest collects only from `apps/`. Seven
>   deliberate breaks of `server_record.py` each failed a named test.
>
> **Not covered.**
>
> - **`run.ps1` itself has no automated test,** only the scenarios above.
> - **k6 has still never run**, so the k6 changes ran only under the Node simulation.
> - **Nothing checks that the server was restarted before the HTTP check.**
> - **The restart check rests on file times.**

**Dated note, 11 November 2026: the listening process is found three ways, because Windows can
report a serving socket's state wrongly.** The user asked for this on main after NFR-08's runs on
`anthropic` (#88).

- **The fault,** on this laptop (Windows 11, build 26300). `scripts/server_record.py` found the
  listening process with `Get-NetTCPConnection -State Listen` only. With Waitress answering on
  127.0.0.1:8000:
  - the TCP table reported its listening socket in state 0, which is undefined, or 1 (Closed),
    where 2 is Listen;
  - `netstat -ano` showed no line for it, or CLOSED;
  - the socket's own row was there throughout, with the Waitress PID.

  So decision 2's pre-flight refused D-85's server as nothing listening, and the closing check
  marked measured runs INVALID. NFR-08's runs 1 and 5 on `anthropic` were measured and marked
  INVALID that way, and runs 2 and 4 were refused before k6
  (`corpus/objective-02/runs/2026-11-10-anthropic/nfr08-anthropic.md`, #88).
- **The fault can refuse a run or invalidate it. It cannot pass one.** A lookup that finds
  nothing fails the pre-flight and the closing check alike.
- **The lookup now** (`listening_process`), in this order:
  1. the Listen row, as before, taken when its process's command line can be read;
  2. `netstat -ano`: the one PID with a LISTENING line on the port;
  3. the port's own socket row, local port and remote port 0, whatever state is reported, when
     exactly one live process with a readable command line owns such a row. PID 0 and PID 4 never
     qualify.

  Two candidates in step 2 or 3 is not found. When none of the three names a process that can be
  read, they are tried again every 10 s for about 60 s. Then the Listen row's own answer is
  returned, as it always was.
- **Where it came from.** NFR-08's run 6, the valid one, ran a run-folder copy of the script with
  this lookup, which the user approved before it ran (#88, `154915c`). This is that copy's lookup,
  with what follows added.
- **Recorded:** which lookup found the process, and what each try saw:
  - in the pre-flight record: `process_found_by` and `process_lookup`;
  - on the pre-flight's console: `found by`;
  - in the summary's `server_at_end`: `found_by` and `lookup`.
- **What does not change.** Decision 2's rules, and the built note's two checks beyond D-87:
  - the server and its thread count are still read from the found process's command line;
  - the process at the end must still be the one observed before the run. Another PID, no
    process, or a "Serving on" line inside the window still marks the run INVALID.
- **Tried on the laptop on 11 November,** with `python -m http.server` on scratch ports. The
  record is `corpus/objective-02/runs/2026-11-11-listener-lookup/`, and its `README.md` gives
  each trial.
  - **At 14:44, with the fault present.** With the listener answering, the Listen row and netstat
    showed nothing for it, and the port's own row named its PID, in state 0 and then 1. Step 3
    found it, in 2.8 s. With the listener stopped, the lookup gave up after 53.8 s.
  - **A Listen row naming PID 0, and at times a netstat LISTENING line naming it too,** were seen
    in that trial and in the one before it, at 14:42:
    - beside an answering listener's own row, and again just after it stopped (14:42);
    - about 40 s after a listener had stopped (14:44).

    PID 0 is not a process. Step 1 takes a Listen row only with a readable command line, so such
    a row does not end the search. A first draft of this change took any Listen row that named a
    PID, and returned PID 0 in the 14:42 trial. It was corrected before it was committed.
  - **At 19:15, after the laptop had restarted at 17:07, the fault did not show.** The committed
    script (`421f9ed`) found the listener by its Listen row in 1.5 s. Netstat and the port's row
    named the same PID, in state 2. With nothing listening, it said so after 50.8 s.
  - **Only the 19:15 trial has a console on file.** The two earlier ones were not teed, and the
    README quotes the session's console for them.
  - **Whether a restart clears the fault is not known.** It is one observation.
- **Tests,** in `apps/ai/tests/test_server_record_preflight.py`. Each fails under at least one
  deliberate break of the script, named after the list:
  - `test_netstat_names_the_pid_listening_on_the_port_and_no_other`: S5;
  - `test_netstat_gives_one_listening_pid_or_none`: S2, S5;
  - `test_the_ports_own_row_gives_one_owner_or_none`: S3, S7, S11;
  - `test_a_listen_row_is_taken_first_and_nothing_else_is_asked`: S13;
  - `test_a_listener_with_no_listen_row_is_found_through_netstat`: S1;
  - `test_when_netstat_misreports_too_the_ports_own_row_names_the_process`: S1;
  - `test_the_lookup_is_tried_again_before_it_says_nothing_is_listening`: S1, S4;
  - `test_nothing_listening_is_said_only_after_the_wait_and_in_the_same_words`: S1, S4;
  - `test_a_listen_row_and_a_netstat_line_naming_pid_0_do_not_end_the_search`: S1, S10;
  - `test_a_process_no_lookup_can_read_is_returned_after_the_wait_as_it_always_was`: S1, S4, S10;
  - `test_off_windows_the_process_is_not_looked_up_and_nothing_waits`: S6;
  - `test_the_record_says_which_lookup_found_the_process`: S8;
  - `test_the_closing_check_says_how_it_found_the_process`: S12;
  - `test_another_process_found_by_a_fallback_still_makes_the_run_invalid`: S14;
  - `test_no_process_found_at_the_end_still_makes_the_run_invalid`: S9.

  The breaks:
  - S1: only the Listen row is asked, as before this note;
  - S2: netstat picks one of two LISTENING processes;
  - S3: the port's row picks the first of two owners;
  - S4: no second try;
  - S5: netstat's port is matched as a suffix, so 18000 reads as 8000;
  - S6: the fallbacks run off Windows;
  - S7: the port's row is asked for in state Listen only;
  - S8: the record does not say which lookup found the process;
  - S9: no process at the end reads as the same process;
  - S10: a Listen row is taken without a readable command line;
  - S11: PID 0 and PID 4 may own the port's row;
  - S12: the closing check does not record how the process was found;
  - S13: a Listen row is never taken;
  - S14: any process at the end reads as the same process. The existing
    `test_another_process_at_the_end_makes_the_run_invalid` fails under it too.
- **The runbook's own check** has the same fault. Its step 4 runs
  `Get-NetTCPConnection -LocalPort 8000 -State Listen` and expects nothing. That can print
  nothing while a server listens, and a leftover row with `OwningProcess` 0 after one stops. The
  runbook now says so and names `scripts\server_record.py` as the check.
- **Not covered:**
  - **Why Windows misreports the state.** It is observed, not explained, and another build may
    differ.
  - **A listener whose process cannot be read,** such as another user's or PID 4's. No lookup is
    credited with it, and the answer is the one given before, after the wait.
  - **The PowerShell and netstat commands themselves in the test suite.** The tests script each
    lookup's output. The commands ran on the laptop only, in the trials above.
  - **The committed script against the fault, with a console on file.** The 14:44 trial ran the
    script as committed, and its console was not kept. By 19:15 the fault had gone.
  - **`run.ps1`,** which still has no automated test (the built note's first "Not covered" line).
  - **NFR-08 again with this code.** Run 6's copy had the same lookup without the record fields.
  - **Measured runs before 11 November.** They are not re-examined for this fault.

## D-88 · The M6 alpha serves `kmp_demo_20261101`, restored from item 6's snapshot, from a worktree of its own

**Status:** Settled by the user · **Date:** 2026-11-01 · **Stage:** 5 item 9 · **Closes:** D-84's
open item, "the demo database for 1 November" · **Corrects:** D-74, `scripts/seed_objective02_tags.py`

**The database.** The alpha and the demonstration use `kmp_demo_20261101`, a new database restored
from item 6's measured snapshot (dump `3bf98403…6f59`). So they show Objective 02's corpus exactly as
it was measured.

- **Not `kmp`,** which stays as it is (D-84 decision 1).
- **Not the measurement database `kmp_obj02_20261101`,** which holds the runs' QueryLog rows and
  the load-test accounts.

**How it was restored, on 1 November.**

- **The checks came first.** `scripts/snapshot_measurement_db.py restore` refuses a name other than
  the one snapshotted, so its own checks (`verify_snapshot`) would not run for a new name. The same
  checks ran instead, using the module's own functions, before anything was created:
  - `snapshot.json` matched the committed copy;
  - the dump's SHA-256 matched it;
  - the media copy's tree hash, `5284aae1…64d5` (23 files), matched it;
  - the name is not a protected one;
  - the media destination is outside every checkout, and new.
- **Then the restore:**
  - `createdb kmp_demo_20261101`, which fails if the database exists, so nothing can be overwritten;
  - `pg_restore`;
  - the media copied to `C:\kmp-demo\2026-11-01\media`, with its tree hash checked again.
- **Tags.** `scripts/seed_objective02_tags.py` ran against it, because the snapshot has none and
  FR-15's browse needs them (D-74). It created 14 tags and 48 links, and a second run created none.
- **Accounts.** `loadtest01` to `loadtest21` were deleted: 21 rows, none of which owned anything in
  the snapshot. Two accounts remain:
  - `corpus.admin@example.com`, the Administrator;
  - `corpus.employee@example.com`, an Employee.

  **Nobody knows their passwords.** Both were generated in memory during item 6's run and never
  shown or stored. The user sets the Administrator's with `manage.py changepassword` before the
  walk, and the Employee for the walk registers through FR-01.

**Where it runs from** (`docs/alpha-deployment.md`):

- **A worktree of its own, `KMP_Prototype-alpha`, checked out detached at `main`'s commit.** The main
  checkout is not touched, and GitHub Desktop can still switch it to `main`.
- **A venv of its own,** made with `uv venv` and synced from that commit's `requirements.txt`. A sync
  from an older checkout into the shared venv would remove WhiteNoise.
- **A `.env` of its own,** naming:
  - `kmp_demo_20261101`;
  - `MEDIA_ROOT=C:\kmp-demo\2026-11-01\media`;
  - logs in `C:\kmp-demo\2026-11-01\logs`.
- **The server window:**
  - `DATABASE_URL` and `MEDIA_ROOT` are set together in it;
  - it is a fresh PowerShell window, never the measurement one;
  - Waitress starts only after Django has printed the database it will connect to and that name is
    `kmp_demo_20261101`.

**Not covered.**

- **The demonstration script and D-40's screening** of its questions. They are the rest of item 9,
  run against this database.
- **The rule from here on: no re-index, reprocess or delete** between building the demonstration's
  threads and demonstrating them (D-40). A second restore resets everything, so it may only come
  before that point.
- **M8's hosting and database** (D-64).

## D-89 · The load-test accounts are retired: unusable on the measurement database, deleted elsewhere

**Status:** Settled by the user · **Date:** 2026-11-02 · **Stage:** 5, after the gate · **Concerns:**
D-82, D-84, D-88, FR-02

**Why.** `loadtest01` to `loadtest21` (`manage.py create_load_test_users --count 21`, D-82) were
made for item 6's NFR-08 runs, all with one throwaway password. That password was shown once in
the 1 November session. While any of them can sign in, they are an open door with a known key.

**What was done, on 2 November.** Read-only counts came first, in four databases, and the alpha's
count had to be 0 before anything was written.

| Database | Before | Action | After |
|---|---|---|---|
| `kmp_demo_20261101` (the alpha) | 0 | none; D-88 deleted them on 1 November | 0 |
| `kmp_obj02_20261101` (item 6's measurement) | 21, all with a usable password | passwords made **unusable**; rows kept | 21, none usable |
| `kmp_demo_screen` (the demonstration screen) | 21, all with a usable password | rows **deleted**; no PROTECT refusal, since the screen never used them | 0 |
| `kmp` (development) | 0 | none | 0 |

- **Why the measurement database keeps its rows.** QueryLog, Conversation and SearchLog point at
  users with PROTECT, so a delete would fail. Those rows are NFR-08's evidence. The user model has
  no `is_active` column, so an unusable password is how an account is retired.
- **The users table of `kmp_obj02_20261101` has changed since its snapshot.** The dump `3bf98403…`
  still holds the 21 accounts with their old password hash.
- **Afterwards:** no usable load-test password in any of the four databases.

**What still applies.**

- **Every restore of the snapshot must repeat the delete,** or retire them as above, because the
  dump holds the accounts.
- **Re-running `create_load_test_users` re-enables them.** It resets an existing account's password
  to `LOAD_TEST_PASSWORD`. Run it only for a load test, and retire the accounts again afterwards.
- **The password shown in that session must be changed wherever it was used.**

**Not covered.** The k6 summaries already committed name the accounts but hold no password, so
nothing in the repository needs changing.

## D-90 · Item 10's audit returned INCOMPLETE, and its verdict is recorded here verbatim

**Status:** Recorded · **Date:** 2026-11-02 · **Stage:** 5 item 10 · **Concerns:** the twelve gate
requirements · **Audited:** `d697392`

One `requirements-auditor` run, read only, on `d697392`: `main` after #39, plus item 8's walk
record (#40). It audited the twelve as a set, and hunted for a claim in this file that is true
where written and false where used. It edited nothing and ran nothing. It is recorded here because
a verdict that lives only in a terminal is the failure mode D-61 names. **Nothing it found was
fixed in the session that ran it.**

**What the user decided on it, 2 November.**

| Finding | Decided by |
|---|---|
| H2: the lockout is FR-02's | D-25's dated note; `CLAUDE.md:185` corrected; an extra recorded walk |
| H1 and FR-13 | D-91 (FR-13 partial at the gate), D-42's dated note |
| S3: D-56 | D-93 (acknowledged, with the floor owed by a new dev set) |
| S1 and S4's drift test | D-94 (front-end tests now, as step 6) |
| §8 condition 4 | D-92 (D-60's decline accepted, scoped) |
| NFR-08, a note rather than a decision | D-95 |
| H3: D-62's list | D-62's dated note |
| H5: D-74's empty state | D-74's dated note |
| S2, H4, H6, and the script's FR-13 wording | `docs/demonstration-script.md`, amended 2 November |

**Where the report overstates, verified against the repository:**

- **H1 reads `as_expected_every_trial: false` as "fail on every run".** It means "not as expected
  on every trial". D-91 gives what the stored trials support, rescored with the frozen rule.
- **H1's verdict word, "falsified", is stronger than the screen supports.** The screen was informal
  and on another corpus, and four of the seven threads it counts are confounded (D-91).
- **Its fix 4 conflicts with the user's tuning rule.** It suggests taking a floor from item 6's
  `harness.json`, and D-93 settles that the frozen sets are not tuning sets.

**The verdict, verbatim.** Reproduced as the auditor returned it, quoted rather than edited. Its
line numbers are against `d697392`.

> ## Audit: M6 gate, the twelve MUST-HAVEs as a set. Branch test/FR-12-live-walk-record @ d697392, 2026-11-02
>
> **Verdict:** INCOMPLETE
>
> All twelve requirements have an owner and are implemented on the server with a UI on top. Every one was walked live on the alpha and confirmed on the server. I found no requirement that is enforced only in the UI. The set is still not complete, for four reasons:
>
> 1. **FR-13 is partial.** Its follow-up clause fails when measured, and the failures fall in the very case D-42 says works.
> 2. **FR-12's partial-matches gap (D-56) has no owner.** Item 6, which owned it, finished without closing it.
> 3. **Seven requirements fail §8 condition 2.** Their UI-only clauses have no front-end test.
> 4. **The demonstration script presents two deviations where the record holds about ten.**
>
> Separately, §8 condition 4 is permanently declined for FR-11, FR-12 and FR-13 (D-60). So under §8 as written, the set cannot reach COMPLETE until that decline is accepted explicitly.
>
> I edited nothing and ran nothing: no tests and no database access. I read files and git history only, and I read the CI results and the walk as evidence rather than re-running them.
>
> ---
>
> ### 1. The twelve
>
> | FR | Owner and where it lives | Implemented | Tested | UI only? | Status |
> |---|---|---|---|---|---|
> | 01 | django-backend and react-frontend. `apps/api/views.py:273-299`, `apps/accounts/validators.py`, `frontend/src/pages/Register.jsx` | Server: 201, 400 and 409, with password complexity checked on the server. UI: the form | `test_register.py`. The route is anonymous, so the dual-role rule does not apply. Front end: only the 429 text (`authThrottle.test.jsx:53`). Submit-disabled, the inline field error and the password rules have no front-end test | No | Met on the server. §8 condition 2 **not met** |
> | 02 | Same agents. `views.py:354-416`, `Login.jsx` | 200, 400, 401, and 403 for a locked account. The UI lands each role on its dashboard | `test_login.py`, including the lock tests at `:230-274`. Front end: the role landing (`dashboard.test.jsx`) and the 429 text. The "distinct message" for a locked account (`Login.jsx:124-129`) has no front-end test | No | Met, with a recorded deviation (D-25: the session carries no role). The lockout was left out of the walk on a misclassification (H2). §8 condition 2 partial |
> | 04 | django-backend. `views.py:422-432`, `config/settings.py:144-147`, `Login.jsx:20` | The session is destroyed on the server, with a 60-minute inactivity expiry | `test_logout.py` (both roles, an expired session gives 401, the inactivity clock). Front end: nothing for the logout confirmation or the redirect | No | Met on the server. §8 condition 2 **not met** |
> | 05 | django-backend. `views.py:489-542`, `apps/accounts/audit.py`, `RoleManagement.jsx` | PATCH; 403 for self-demotion or removing the last Administrator; 404; an audit entry | `test_roles.py` and `test_rbac.py`. Front end: none | No | Met on the server. §8 condition 2 **not met**. D-22 is still "provisional, to confirm" (`decisions.md:570`) |
> | 06 | django-backend. `config/settings.py:168`, `apps/api/permissions.py`, `RequireRole.jsx`, `AccessDenied.jsx` | Every route checked on the server | The dual-role matrix covers 23 of 23 endpoints (CI), plus `test_rbac.py`. The front-end guard has no test | No | Met on the server. The guard is usability only and untested |
> | 08 | rag-pipeline, django-backend and react-frontend. `views.py:548-724` and `:1152-1237`, `apps/ingestion/`, `Upload.jsx` | 403, 415 (by file signature), 413, 400, 409 and 422. There is one chunk write site, and it records the model and dimension (`embedding.py:78-89`) | Many pytest files. Front end: `uploadQueue.test.jsx` and `ingestionLimits.test.jsx` cover the queue, the retry and the 429s. Nothing tests the client-side format refusal or the per-file progress bar | No | Met, with recorded deviations (D-15, D-30, D-33 §1) that the script never presents. §8 condition 2 partial |
> | 09 | rag-pipeline and django-backend. `views.py:1005-1149`, `apps/ingestion/meetings.py`, `Meetings.jsx` | 201 and 400, plus a 422 by convention. A future meeting date is refused on the server (`serializers.py:319-324`) | `test_meeting_ingestion.py`. Front end: the 429 messages only | No | Met, with a recorded deviation (D-33 §2). §8 condition 2 partial |
> | 11 | rag-pipeline. One predicate, `apps/retrieval/scoping.py:114-190` | The FR gives it no interface of its own | `test_fr11_scoping.py`, `test_scoping.py`, `test_fr11_scoping_bites.py`, `test_source_rows_fail_closed.py` | No | Met. §8 condition 4 declined (D-60) |
> | 12 | rag-pipeline. `apps/retrieval/{pipeline,ranking,verification,query_log,search,partial_matches}.py`, `apps/api/answers.py`, `Ask.jsx`, `Answer.jsx`, `Search.jsx` | Grounded generation, verification, both no-answer paths, and a 503 after three attempts | Extensive pytest. Front end: the `ask*.test.jsx` files. Nothing front-end tests the search field on every page, the grouping, the two-character minimum, the Search screen or the partial-match label | No | **Partial.** D-56's missing floor is open with no owner (S3). D-45 is a deviation. §8 condition 2 partial; condition 4 declined |
> | 13 | django-backend for the endpoints, rag-pipeline for `apps/retrieval/conversation.py`, react-frontend for `Ask.jsx` | History is prior questions only. Scope is re-resolved every turn. The thread lives in the URL | `test_conversations.py`, `test_fr11_scoping.py:608,633`, `test_fr11_thread_scope.py`. Front end: `askThread`, `askReopened`, `askThreadList` | No | **Partial.** Follow-up resolution fails when measured (H1). D-42 and D-43. §8 condition 4 declined |
> | 14 | django-backend and react-frontend. `views.py:1500-1605`, `Dashboard.jsx` | One scoped endpoint, with counts taken after the scope filter | `test_dashboard.py` (both roles, byte-identical with and without restricted rows). `dashboard.test.jsx` | No | Met, with recorded deviations (D-69, D-70) the script never presents |
> | 15 | django-backend and react-frontend. `views.py:727-934`, `apps/api/repository.py`, `apps/documents/deletion.py`, `DocumentRepository.jsx`, `DocumentDetail.jsx` | Browse, detail, download and delete, each resolved through the scope first | The `test_document_*` files and `apps/documents/tests/test_deletion.py`. `documentRepository.test.jsx` | No | Met, with a recorded deviation (D-72) the script never presents |
>
> ---
>
> ### 2. Set-level findings
>
> **S1. §8 condition 2 is met for FR-14, FR-15 and most of FR-12 and FR-13, and nowhere else.**
> - **The gap.** The UI-only clauses of FR-01, FR-02, FR-04, FR-05, FR-06, FR-08, FR-09 and FR-12's search half have no front-end test.
> - **It is recorded.** D-62 lists every page except Ask as untested (`decisions.md:3289-3294`) and says the amended condition "does not reach back and pass anything" (`:3332-3334`).
> - **Nobody owns it.** `M6-BUILD-PROMPT.md:300-303` assigns each clause to "whichever item owns its behaviour". No Stage 5 item owns FR-01, 02, 04, 05, 06 or 09, so these tests were never owed by anyone.
> - **The walk does not stand in.** Item 8's walk is hand-testing, which §8 says does not count.
>
> **S2. The demonstration script ticks deviations the record says must not be ticked.**
> - **What it lists.** `demonstration-script.md:384-388` gives D-45 and D-42 as the build's only on-purpose shortfalls. That list was copied from `M6-BUILD-PROMPT.md:484-487`, written on 28 September.
> - **What the record holds against the twelve:**
>   - D-25: FR-02's session carries no role (`decisions.md:732-742`).
>   - D-33 §1: FR-08's classification hand-off is deferred. D-33 says "What is owed. Not code. A sentence in the demonstration script" (`:1104-1109`). That sentence is absent.
>   - D-33 §2: FR-09's 422.
>   - D-43: FR-13's Update has no PATCH.
>   - D-56: FR-12's partial matches have no floor.
>   - D-69: FR-14 does not read KnowledgeGaps.
>   - D-70: FR-14's department filter narrows documents only.
>   - D-72: FR-15's Department comes from the column, "a deliberate departure from FR-15's server clause" (`:4006-4007`).
>   - D-15: four formats, not six.
> - **The consequence.** The walk marks FR-02, FR-08, FR-09, FR-14 and FR-15 PASS without naming any of these.
>
> **S3. D-56 has lost its owner.**
> - `apps/retrieval/partial_matches.py:119-148` still has no relevance floor.
> - D-56 says "either a floor or an explicit acknowledgement is owed" (`decisions.md:2817-2819`).
> - D-61 gap 6 and `stage-4-open-items.md:127-128` gave it to item 6. D-84 deferred it to "a later decision, made from this measurement" (`:5238-5239`).
> - Item 6 has merged (`fe456d9`). Its `harness.json` records partial matches for all 34 runs, but no decision followed.
> - It is on the walk path. FR-11 step 1 (top score 0.193) and FR-12 step 3 (0.2526) are path-A no-answers, so each offers up to five nearest titles labelled "partial matches".
>
> **S4. Duplication, minor.**
> - **Server constants restated in the front end, with no drift test (D-61 gap 13, still unowned):** `frontend/src/constants.js:91-92` (50 MB) and `:114-116` (2, 10, 500), and the literal "50 MB" in `apps/api/views.py:151`.
> - **The meeting list order is written twice:** `views.py:1039` and `:1583`.
> - **D-29's self-exclusion check is written twice:** `views.py:673-682` and `:1062-1067`.
>
> **Other set-level checks, nothing found:**
> - **Wrong layer:** none.
> - **UI-only enforcement:** none. Every UI guard I checked has a server check behind it: format and size by signature (`views.py:642-665`), the search minimum, the future meeting date, the delete (`:804-806`), and the role screen (`/api/users` answers 403).
> - **AI SDK imports outside `apps/ai/`:** none.
> - **Inline literals in Python:** none outside `constants.py`, apart from `views.py:151`.
>
> ---
>
> ### 3. The decisions.md hunt
>
> **These claims fail where they are used:**
>
> **H1. D-42's boundary for FR-13 (the main finding).**
> - **The claim.** `decisions.md:1794-1798` (23 September): "follow-up questions need not restate the subject" holds for subject nouns, not for references into an answer. It was written while "FR-13 end to end is still unmeasured" (`:1787-1790`).
> - **Where it is used:**
>   - `stage-4-clause-audit.md:84`: "Holds for subject nouns".
>   - `stage-5-clause-audit.md:346` and `:400`: FR-13's first row stays partial "for D-42".
>   - `stage-4-open-items.md:143-145`.
>   - D-86 decision 2 (`decisions.md:5392-5393`): only the thread whose referent is in the answer "should fail".
>   - `demonstration-script.md:388`: D-42 is offered as the deviation.
> - **What the measurement shows.** `corpus/objective-02/threads.md:34-35` designs t01 to t07 so that turn 1's question names the referent, which is the class D-42 says works. Only t09 needs the answer.
> - **The 1 November screen** (`corpus/demo/screening-2026-11-01.json`, `second_pass.trials`):
>   - t01, t02, t03, t04, t06 and t07 fail on every run (`as_expected_every_trial: false`).
>   - t05 scores as expected, but cites another transcript.
>   - t09 fails, as predicted.
> - **Verdict.** Six of the seven threads whose referent is in the question fail. D-42's boundary is falsified, and FR-13's shortfall is the clause's ordinary case, not its conceded edge.
>
> **H2. Which requirement the lockout belongs to.**
> - **The record.** D-25 (`decisions.md:690`, `:759-765`) puts the five-failure lock and its 403 in FR-02, and raised the conflicting CLAUDE.md annotation on 13 September. `apps/core/constants.py:286-289` agrees: "Enforcement is therefore FR-02's".
> - **The stale claims.** `CLAUDE.md:185` still says "(FR-03, NIT3004)". D-61's verbatim audit (`decisions.md:3206`) calls the lockout "SHOULD-tier effort".
> - **Where they are used:**
>   - `demonstration-script.md:92`: "FR-03, not in the gate. Do not show it."
>   - `stage-5-item-8-walk.md:199`.
> - **Result.** A gate clause was excluded from the walk: FR-02's business-logic lock, its 403 response, and the locked-account message on screen. The server side is tested; the front-end message is not.
>
> **H3. D-62's list of what the front-end suite does not cover.**
> - **The claim.** `decisions.md:3285-3325`, written 28 September.
> - **Where it is used.** `demonstration-script.md:383` says "Give D-62's list". `M6-BUILD-PROMPT.md:481-483` says the same.
> - **It is now wrong.** It calls DocumentRepository and DocumentDetail untested, but they are tested in `documentRepository.test.jsx`. It says nothing renders the provenance-removed state, but `askReopened.test.jsx:174-175` does. It calls D-61's gaps 3 and 4 "neither tested nor fixed", but D-77 and D-78 fixed and tested both.
>
> **H4. D-61's permission-boundary claim.**
> - **The claim** covers six named routes (`decisions.md:3051-3054`).
> - **Where it is used.** `demonstration-script.md:130-131` and `:368` repeat it as "every audit found no route across it", without the route list.
> - **The gap.** No audit has walked these four (item 11 has not run):
>   - `GET /api/dashboard`;
>   - `GET /api/documents/browse`;
>   - `GET /api/documents/{id}/download`;
>   - `DELETE /api/documents/{id}`.
> - They do have leakage tests, so the boundary is tested. The sentence just claims more than any audit checked.
>
> **H5. D-74's empty state.**
> - **The claim.** `decisions.md:4180-4181`: "At least one combination of filters an Employee can choose matches nothing".
> - **Why it cannot hold.** Under D-72's facet rule (`:4022-4025`), each facet's values are counted over the documents matching every other active filter. So no pair of facet choices can match nothing. The claim was false for facets on the day both decisions were written, not only "after either is chosen" (walk `:163`).
> - D-74 carries no correction for this.
>
> **H6. Which item 9a.**
> - **The claim.** `demonstration-script.md:376`: "Item 9a's measurement of it comes after the gate."
> - **Why it is wrong.** The mis-citation measurement is Stage 4's item 9a, which exists (`flm-baseline.md:583`). Stage 5's item 9a is the leakage tests. Minor.
>
> **These hold where they are used:**
> - **D-66.** Its D-29 residue is named at `:3631-3635`.
> - **D-65.** The `q` exception is named.
> - **D-53.** Every source read goes through the scoped helpers.
> - **D-70.** A status reflects its chunks: there is one write site, and reindex works one source per transaction.
> - **D-75 and D-47.** No route writes `visible_to_roles`, and the upsert hole is pinned by a test.
> - **D-79 and D-85.** One Waitress process with the in-process cache.
> - **D-83.** `check_flm.py` fails a noisy build: 0.6046 against 0.999 required.
> - **D-64, D-67, D-68, D-73, D-76, D-88.**
>
> ---
>
> ### 4. The items already recorded, and how they are classified
>
> **FR-13 follow-ups.** The shortfall is disclosed (walk `:200-202`, script `:235-240`, `:379-382`), but it is misclassified in four places:
> - **The walk headline.** It marks FR-13 PASS with no qualifier (walk `:23`, `:119`). It should read partial.
> - **The cause.** It is blamed on D-42 (see H1), but the failures fall in the case D-42 says works.
> - **The wording.** "The same way on all three runs" (script `:237`, `:320-321`) is false for t02, t04 and t09 (`identical_across_trials: false`).
> - **The failures are answered.** They come back with citations, often to the wrong source. t01 cites the Expense Claims Guide. t04 cites the Records Management Handbook. t07 cites the Weekly Operations Standup, and for the Administrator, the Project Atlas Kickoff Brief. So on follow-ups, invariant 5's conceded limitation is the common case.
> - **The attribution.** "This is the 4B model's behaviour" (script `:325`) is unsupported: D-86's cold and spelled-out modes, which would separate the model from the prompt, were not run.
> - **Per-turn re-scoping.** "The permission is checked again on every turn" (script `:231-232`): two sessions holding two roles cannot show re-evaluation. The evidence is `test_fr11_scoping.py:633`, and the script should cite it.
>
> **FR-15 empty state.** Correctly not a gate failure. The 204 is reachable from the UI's own title filter (script `:264-265`) and is tested in both suites. Its root cause is H5.
>
> **NFR-08 and NFR-09.** Correctly outside the gate. The results are recorded as a note under D-82 (`:5125-5145`), not as the decision D-84 asks for (`:5228-5229`).
>
> **Items 7, 9a and 11.** All five of 9a's assertions already exist in item 2 and item 3 tests (for example `test_document_delete.py:206`), so deferring 9a costs little. Item 11 not having run is what H4's wording hides.
>
> **Also open:** the walk does not record whether the D-35 screen recording was made (walk `:203`). Confirm it exists.
>
> ---
>
> ### Invariant check
>
> - **Pass: invariants 1, 2, 3, 4, 7, 8, 9 and 10.**
> - **Pass: invariant 5.** Verification is set membership. The follow-up mis-citations are its conceded limit, not a breach.
> - **Pass: invariant 6.** Tested at the UI (`ask.test.jsx:58-80`).
> - **Pass: no AI SDK import outside `apps/ai/`.**
> - **Pass: every chunk write records model and dimension.**
> - **Fail, minor: constants.** S4.
>
> ### Gate impact
>
> None of this means a requirement cannot be shown. Smallest fixes, in order:
>
> 1. **Documentation only, for FR-13.** Add a dated note to D-42 recording the screen. Re-mark FR-13 as partial for the measured reason. Qualify the walk's FR-13 PASS. Fix script `:237`, `:320-321` and `:325`.
> 2. **The lockout.** Correct `CLAUDE.md:185` to FR-02 and fix script `:92`. If the lockout is shown, use a throwaway account.
> 3. **The script.** Add S2's deviations list. Replace "Give D-62's list" with a current one. Restore D-61's route list. Fix `:376`.
> 4. **D-56.** Choose a floor from item 6's `harness.json`, or record the acknowledgement D-56 says is owed.
> 5. **Front-end tests for S1, the largest piece.** One test file per screen: Register, the Login locked message, the logout confirmation, RoleManagement, RequireRole and AccessDenied, the Upload client-side refusal, the Meetings processing indicator, and Search with the partial-match label.
> 6. **§8 condition 4.** Accept D-60 explicitly in the stage exit criterion, or `M6-BUILD-PROMPT.md:440` cannot be met.
>
> **INCOMPLETE:** all twelve were demonstrated, but FR-13's follow-up clause fails when measured, under a decision that says it holds. FR-12's partial-match gap has no owner. Seven requirements have untested UI-only clauses. The script presents recorded deviations as passes.

## D-91 · FR-13 is partial at the gate

**Status:** Settled by the user · **Date:** 2026-11-02 · **Concerns:** FR-13, D-42, D-86 ·
**Measured reason:** step 5 of the user's post-M6 order, not yet run

**Decision.** FR-13 is partial at M6. Its thread, its reopening and its per-turn scoping work. A
follow-up that relies on the earlier turn did not resolve in the 1 November screen. The measured
reason comes from step 5's run: the nine frozen threads, with history, cold and spelled out
(D-86), then the HTTP check, on `kmp_obj02_20261101`.

**What the screen supports.** These are the stored statements in
`corpus/demo/screening-2026-11-01.json` (`second_pass.trials`), rescored per trial with the frozen
rule, version 2. A run that should be answered is correct if it is answered, contains an expected
phrase or an accepted form, and cites one of the turn's sources. A run that should not be answered
is correct if it is not. Nothing was re-run. Leaks (part 7) cannot be judged from what the screen
stored.

| Thread, role | Turn 1 correct | Turn 2 expected | Turn 2 correct | Reading |
|---|---|---|---|---|
| t01, Employee | 3/3 | answer | 0/3 | **clean case; the follow-up failed every trial** |
| t04, Employee | 3/3 | answer | 0/3 | **clean case; failed every trial** (the replies varied) |
| t06, Administrator | 3/3 | answer | 0/3 | **clean case; failed every trial** |
| t02, Employee | 0/3 (right phrase, wrong source) | answer | 0/3 | confounded |
| t03, Employee | 0/3 | answer | 0/3 | confounded |
| t05, Employee | 0/3 | answer | 0/3 (phrase found, another transcript cited) | confounded |
| t07, Administrator | 0/3 | answer | 0/3 | confounded |
| t07, Employee | 0/3 (right phrase, wrong source) | no-answer | 0/3, answered | confounded; answered from material the Employee may read, which is no leak, but a different failure from one that does not resolve |
| t06, Employee | 3/3 | no-answer | 0/3, answered | the same different failure |
| t08, Employee (topic change) | 3/3 | answer | 3/3 | as predicted |
| t09, Employee (previous answer) | 3/3 | answer | 0/3 | as predicted (D-86 decision 2) |

- **The three clean cases all name their referent in the first question,** the class D-42 says
  resolves. None resolved on any trial.
- **The other question-referent threads say nothing about history.** Their first turn was not
  correct on every trial.
- **The screen's own flag differs from the rule.** Its `as_expected_every_trial` checked the
  phrase, not the source. So t02's and t07's first turns, and t05's follow-up, looked better there
  than under the rule. The user's reading of 2 November counted t02 as clean, and had t02 and t04
  failing on "at least one" trial. The rescore puts t02 among the confounded and t04 at 0/3.

**Limits.**

- **Not D-86's measurement.** The screen ran on `kmp_demo_screen`, with D21 and T06 added, not on
  the corpus `threads.json` is frozen against. It ran with history only, and the per-trial verdicts
  were not stored.
- **No cause.** The model was not separated from the prompt. Cold and spelled-out runs do that,
  and they are step 5's.

**Where it applies.**

- `docs/stage-5-clause-audit.md`, "After item 10": FR-13's first row is partial for this reason,
  pending step 5.
- `docs/stage-5-item-8-walk.md`: the FR-13 PASS is qualified in a dated note.
- D-42: a dated note.

**Dated note, 3 November 2026: step 5 has measured it.** D-86's run was made at `2f65a8e` on
`kmp_obj02_20261101`: the thread run, then the HTTP check
(`corpus/objective-02/runs/2026-11-03/fr13-before.md`).

- **The decision stands. FR-13 is partial, now by measurement rather than by the screen.**
- **The history is wired.** It changes what is retrieved, in-process and through the server (WIRED
  3 of 3).
- **The follow-ups are not answered.** With history, 1 of 9 answerable follow-ups matched (t08,
  which is cold-answerable). Spelled out, 3 of 9 matched. 7 of the other 9 answered with-history
  replies restate the first turn, as the screen saw.
- **The cause is split.** For t01 and t05, history is the limit, because spelling the question out
  works. For six others, spelling it out fails too, so generation or retrieval limits it as well.
- **The clean cases agree with the screen.** t01, t04 and t06 as the Administrator did not resolve
  with history. t08 passed, and t09 failed, as expected.
- **No leak.** 0 out-of-scope passages in every run. The Employee's t06 and t07 follow-ups were
  answered from material the Employee may read, when no answer was expected: the "different
  failure" this decision's table names.
- **Step 7 starts from this baseline,** and its "after" runs the same threads again.

**Dated note, 10 November 2026: settled by D-112.** Three measured attempts were not adopted (D-103,
D-111). FR-13's follow-up clause is accepted as partial for NIT3003, as a recorded deviation, and the
generation-side lever moves to NIT3004. "Work continuing" no longer describes it, for the FLM build.

## D-92 · §8 condition 4: D-60's decline is accepted, for 9508442..e81c6e6 only

**Status:** Settled by the user · **Date:** 2026-11-02 · **Concerns:** CLAUDE.md §8 condition 4,
FR-11, FR-12, FR-13, D-60, `M6-BUILD-PROMPT.md:440`

**Decision.** D-60 recorded that Stage 4 closed with §8 condition 4 declined for FR-11, FR-12 and
FR-13. Condition 4 is "the work is committed on its branch with the FR ID in the message", and the
stage's commit subjects were not reworded. The user accepts that decline explicitly.

- **Scope:** commits `9508442` ("docs(M6): the coverage rule, the decision index, and Stage 5
  rewritten") to `e81c6e6` ("fix(FR-11/FR-12/FR-13): close the fourth audit, including the seventh
  instance").
- **It excuses nothing later.** A commit outside that range that lacks its FR ID fails condition
  4 as before.

**The exit criterion.** `M6-BUILD-PROMPT.md:440` is amended, with the user's approval, to "Done
when the auditor's set-level verdict is COMPLETE, apart from D-60's accepted decline of §8
condition 4 for FR-11, FR-12 and FR-13."

## D-93 · D-56's floor is owed by step 7, from a new dev set; the frozen sets are test sets, not tuning sets

**Status:** Settled by the user · **Date:** 2026-11-02 · **Concerns:** FR-12, D-56, D-37, D-84,
`RELEVANCE_THRESHOLD` · **Supersedes:** D-84's "a later decision, made from this measurement"

**The acknowledgement D-56 says is owed.**

- **The gap.** Partial matches are derived before the threshold, with no relevance floor
  (`apps/retrieval/partial_matches.py`).
- **So:** a path-A no-answer still offers up to five nearest titles as "partial matches", however
  weak. Two of the walk's questions show this: FR-11 step 1 and FR-12 step 3.
- **Owner:** step 7 of the user's post-M6 order (RAG answer quality, rag-pipeline), which chooses
  the floor.

**The rule for choosing it, and any threshold.**

- **The floor is chosen in step 7 from a new dev question set,** drafted from the corpus. It is
  never chosen from item 6's `harness.json`.
- **This supersedes D-84's "made from this measurement",** for the partial-matches floor and for
  `RELEVANCE_THRESHOLD` alike.
- **Why.** `corpus/objective-02/questions.json` and `threads.json` are test sets, not tuning sets.
  Nothing is tuned against them, and they measure the result.
- **So the record holds one rule.** Item 10's fix 4, a floor taken from `harness.json`, is not
  taken.

**Not covered.** The floor's value, and whether `RELEVANCE_THRESHOLD` moves. Both are step 7's,
from the dev set.

## D-94 · S1's front-end tests are in scope now, as step 6, before item 7

**Status:** Settled by the user · **Date:** 2026-11-02 · **Concerns:** CLAUDE.md §8 condition 2,
FR-01, FR-02, FR-04, FR-05, FR-06, FR-08, FR-09, FR-12, D-62, D-61 gap 13

**Decision.**

- **What is in scope.** The UI-only clauses item 10 found untested (its S1) are tested now, as step
  6 of the user's post-M6 order, before item 7. That is FR-01, FR-02, FR-04, FR-05, FR-06, FR-08,
  FR-09, and FR-12's search half.
- **Owners:** test-engineer, with react-frontend, on branch `test/FR-01-front-end-clauses`.
- **How:**
  - the UI-only clauses are enumerated from the FR text and ticked against `frontend/tests` first;
  - then only the missing tests are written;
  - they mock at `fetch` through `tests/fakeApi.js`, and `tests/setup.js` is not loosened;
  - each new test must fail under a deliberate break, named in its commit.
- **Included: the front-end constants drift test** (S4, D-61 gap 13). It holds
  `frontend/src/constants.js` to `apps/core/constants.py`, built like
  `test_in_flight_codes_agreement.py`.

**Not covered**, and still open: S4's duplicated server logic (`views.py:1039` and `:1583`;
`:673-682` and `:1062-1067`) and the "50 MB" literal at `views.py:151`.

## D-95 · NFR-08's miss is a local-model baseline, not a dropped NFR

**Status:** Settled by the user · **Date:** 2026-11-02 · **Concerns:** NFR-08, NFR-09, D-35,
D-82, D-84 §3

**Decision.** D-84 §3 asks for this decision: "A miss is then recorded as a decision, as the risk
register says: a local-model baseline, not a dropped NFR." Until now the results stood only as a
note under D-82.

- **NFR-08 stays a requirement.** It is not dropped.
- **On this hardware it is missed.** One 4B model on one NPU, with no external provider (D-35),
  gives the following, measured on 1 November (`corpus/objective-02/runs/2026-11-01/nfr08-runs.md`):

  | Run | Users / asks | Result |
  |---|---|---|
  | 2 | 1 / 20 | answered-only p90 51,206 ms |
  | 3 | 5 / 25 | valid FAIL: 3 × 503, so the p90 falls on a 503; answered-only p90 276,689 ms |

  The limit is 4,000 ms. Every run used dump `3bf98403…6f59`, FLM v0.9.39, Waitress at 24 threads
  and `DEBUG` off.
- **These numbers are the baseline later changes are measured against.**
- **The 503s are investigated by step 7,** which observes first: each attempt's `finish_reason` and
  completion tokens are logged before anything is changed. D-82's note that the same question
  "failed the same way at one user" was inferred, not observed, because run 2 logged no cause.
- **NFR-09 was not run.** Its failure is recorded as a prediction, not a result (D-82's note).

## D-96 · Pull requests: green CI before the user merges; review welcome, not required

**Status:** Settled by the user · **Date:** 2026-11-02 · **Concerns:** the merge process,
CLAUDE.md §7

**Decision.** The process the repository follows, written down.

- **Green CI is required before the user merges a pull request.**
- **The user merges,** using the branch protection bypass where the rule asks for a review.
- **Sagarika Dey's review is welcome, but not required.**
- **The coordinating session and its agents never merge and never use the bypass.** They open the
  pull request, and say when CI is green.

**How far back this is the practice.** Checked with `gh` on 2 November 2026:

- **#1 to #40 are all merged, and none has a review from Sagarika Dey.**
- **The only reviews in the history are the repository owner's (`halfpelican`):** #24 approved, and
  #30 changes-requested twice and merged anyway.
- **#23 shows no review decision.** Every other pull request was merged with the review still
  required.

So this decision describes what the repository has done since #1. It replaces an in-session
instruction that the user would merge after Sagarika's review.

**What stands.** Nothing in the repository claims a pull request was reviewed. The "approved by
Benjamin Morovan and Sagarika Dey" lines are about the frozen question and thread sets (D-84's and
D-86's notes), not pull requests, and they stand.

## D-97 · FR-04's logout confirmation is fixed now, in its own pull request, before step 5

**Status:** Settled by the user · **Date:** 2026-11-03 · **Concerns:** FR-04, FR-02, D-62, D-94,
`docs/stage-5-item-8-walk.md`

**What was found.**

- **The defect.** FR-04 Front-End: "On activation, user is immediately redirected to the Login page
  with a brief confirmation 'You've been logged out'." The redirect happened, but the confirmation
  never appeared after a logout from a guarded route, which is every screen a signed-in user works
  on.
- **How it was found.** Step 6 found it: a front-end test asserting it failed against `main` (PR #44,
  `docs/stage-5-front-end-clauses.md`, defect 1). The user then confirmed it in a browser on the
  alpha on 3 November, at the end of step 3's lockout walk (PR #45).
- **Why the walk missed it.** Item 8's FR-04 PASS recorded the redirect only. The 1 November walk
  never looked for the confirmation.
- **The cause.** React Router 7 applies a navigation inside `startTransition`. Logout cleared the
  user as an ordinary update, which rendered first, at the old address. `RequireAuth`'s redirect
  from there then replaced the logout's navigation, and the notice with it. The same race lost the
  session-expired notice, and it lost Login's return to the route the user was sent away from,
  which Login's own redirect to `/` replaced.

**Decision.** The user chose from three options: fix it in its own pull request before step 5; fold
it into item 7; or record it and fix it after step 10.

- **Fixed now,** on `fix/FR-04-logout-confirmation`, before step 5. Step 5's "before" is
  unaffected, because the fix does not touch answer generation.
- **Tests first.** test-engineer wrote the tests and showed each one failing on `main`, 10 runs out
  of 10. react-frontend fixed the cause. The tests and the fix are one commit.
- **The fix.**
  - Signing out clears the user inside a transition (`signOut` in `AuthProvider.jsx`). React Router
    already applies its navigation in one, so the two render together, and no render has a
    cleared user at the old address. Deliberate break F1, clearing the user outside the
    transition, brings the defect back. F2, moving the navigation outside it, does not: only the
    user's update needs moving.
  - After sign-in, Login's redirect is the only navigation, aimed at the route the user came from,
    or else their role's dashboard.

**What it does not change.**

- **The alpha keeps the defect until it is redeployed.** Redeploying waits on the D-35 recording
  (step 7's precondition). Until then the demonstration script tells the presenter not to claim
  the confirmation (PR #45).
- **Still open:** three gaps that predate the fix and are not FR failures.
  - A logout that fails with a 5xx clears the user in the page, while the server session may still
    be live. No test pins this either way (break F13 changed it, and nothing failed). Whether it
    should is the user's call.
  - The "Could not sign out" notice stays on screen after the user signs back in.
  - A sign-in whose follow-up `/me` fails leaves the user on the form with no message.

## D-98 · The D-35 recording is accepted as partial; no demonstration submission is required

**Status:** Settled by the user · **Date:** 2026-11-07 · **Concerns:** D-35, D-40, step 7's
precondition, `docs/stage-5-item-8-walk.md`

**What exists.** One recording of the walk on the alpha, made on 6 November:
`2026-11-06 16-45-32.mp4`.

- It runs 11 minutes 34 seconds, at 3840×2400. It is kept on the laptop and never committed.
- Its SHA-256 and its contents are in the walk record's 6 November note.
- **It covers FR-01 to FR-13,** so far as the server shows.
- **It does not cover FR-14, FR-15, D21's deletion, or three FR-11 and FR-12 questions.** These
  were walked after the recording stopped.

**Decision.** The user accepts the recording as partial, and records no part 2.

- **Why:** the platform was demonstrated live in class, so a demonstration submission is not
  required.
- **What changes:** the "NOT MADE" line in the user's post-M6 order no longer holds, and step 7 may
  begin.
- **What is still true:** D-35's other half stands. The demonstration runs on one machine, with no
  external AI spend.

**Kept, and still open:**

- **From the 4 November restore:** `kmp_demo_20261101_pre_d35` and
  `C:\kmp-demo\2026-11-01\media.pre-d35`, which hold the 2 and 3 November walks' state. Deleting
  them is the user's call.
- **The alpha itself:** it now holds the 6 November walk's state.

**Dated note, 7 November 2026: the lecturer's words, and what follows from them.** The user
corrected the reason above.

- **The demonstration in class was unscripted,** and it did not run on the alpha. The lecturer was
  satisfied with what he saw, and asked for a recorded demonstration only if there is anything
  new.
- **So no recording is owed for what was shown.** The "Why" above put it more broadly than that.
- **A recording becomes due again for work shown after 7 November:** meeting deletion, live
  meeting ingestion, and the NIT3004 work (FR-10, FR-16, FR-19).
- **Record it on the build that carries that work,** following the demonstration script's
  recording advice: OBS's Display Capture, under 2 GB.
- **The server cannot confirm what the class demonstration showed.** The two onboarding
  questions on the alpha on 7 November, at 10:52 and 10:54, came from a separate session.

## D-99 · An Administrator can delete a meeting: `manage_meetings`, scoped first, one transaction

**Status:** Settled by the user · **Date:** 2026-11-07 · **Concerns:** FR-09, FR-15, invariants 1,
4 and 9 · **Builds on:** D-07, D-46, D-67, D-73

**Not in the proposal.** FR-09 gives Meetings only Create, Read and Update status, and FR-15's
permissioned deletion covers documents only ("Documents (Read, Delete) … Meetings (Read)"). The
lead asked for it on 7 November. CLAUDE.md §1 says a behaviour outside the proposal is raised, not
built silently: it was raised, and the user decided.

**The user's choices:**

- **A new permission, `manage_meetings`,** not `manage_documents`. The proposal ties
  `manage_documents` to documents, and the two can then be given to different roles later.
  Migration `accounts 0006` seeds it, held by Administrator only, as 0005 seeds `manage_documents`.
- **Built now, before step 7,** on `feat/FR-15-meeting-deletion`. It does not touch answer
  generation, so step 5's baseline stands.

**`DELETE /api/meetings/{id}`, mirroring D-73 clause for clause:**

1. **Scope first.** The meeting is resolved through `scoped_meetings()`, as the detail is. Unknown
   or out of scope is **404**, from one query, with the same body either way (invariant 1, D-46).
2. **Then the permission.** Without `manage_meetings`, the answer is **403**. In the other order,
   the status code would tell a caller whether a meeting they cannot see exists.
3. **One transaction** (`apps/meetings/deletion.py`, invariant 9):
   - the meeting row is locked first, as `manage.py reindex` locks it before rewriting its chunks;
   - its `ContentChunk` rows go, by `source_type` and `source_id` (D-07);
   - its `ContentTag` rows go. Nothing writes meeting tags yet, but the table admits them;
   - the meeting goes, and its `MeetingAttendee` rows with it, through their CASCADE.

   `AnswerCitation.chunk` is `SET_NULL` (D-67), so earlier answers keep their record without the
   text. No other model has a foreign key to `Meeting`.
4. **204 No Content.**

**Where it differs from D-73:**

- **No file to remove on commit.** FR-09 reads an uploaded transcript for its text and discards
  the file, so `transcript_text` is the only copy, and no `on_commit` callback is registered.
- **Attendees cascade,** where a document's `ExtractedContent` does.
- **The detail gains `can_delete` only,** true for a holder of `manage_meetings`. The front end
  shows the Delete control from it. It is usability only: the server decides (invariant 4).
- **No audit line,** because the document delete writes none.

**The interface** mirrors the document's:

- a "Delete meeting" control, shown only when `can_delete` is true;
- a confirmation that says the meeting, its transcript and its indexed passages go, and that it
  cannot be undone;
- on success, the meetings list with a notice. On a 403 or a 404, a message in words, which never
  says more than a 404 would.

**Evidence:**

- **The server side:** `pytest` 2,280 passed, with dual-role coverage 24/24. Of 14 deliberate breaks,
  13 were caught, and the fourteenth (a file removed before commit) does not apply.
- **The front end:** `npm test` 183 passed. 17 of 17 deliberate breaks were caught.
- **Both break tables** are in the commit that carries this entry.

**Open:** the document delete's own test does not catch a missing double-submit guard. The meeting
test was written to catch it (break B17), and the document test was not changed.

## D-100 · Answers are capped at 6 statements, and a retry after a cut-off asks for fewer

**Status:** Settled by the user · **Date:** 2026-11-07 · **Concerns:** FR-12, NFR-08, NFR-19,
invariant 10, D-82, D-93 · **Stage:** step 7 of the post-M6 order, phase 2a

**What phase 1 observed** (D-82's 7 November note, PR #54):

- **Every failed generation attempt was a reply cut off at exactly 800 of 800 completion tokens,**
  with its JSON still open: 15 of 15 attempts.
- **FLM reports `finish_reason: stop` even then,** so only the token count shows the cut.
- **No retry recovered an ask.** A repeated request came back just as long.

**The user's decisions:**

1. **Fewer statements, and a smarter retry.** Each answer is capped at `MAXIMUM_STATEMENTS`, in the
   prompt and in the schema check. A reply over the cap is a schema violation, so it is treated as
   no response and retried, never trimmed (invariant 10).
   - After a ceiling hit or a cap violation, the next attempt asks for fewer: 6, then 3, then 1.
   - After any other failure, the cap stays.
   - There are still three attempts in total (NFR-19).
   - The user declined the other options: raising the ceiling, which doubles a long reply's time and
     keeps the padding, and keeping the complete statements of a cut reply, which breaks invariant
     10.
2. **Successful attempts are logged to their own file,** `ATTEMPTS_LOG_PATH` (default
   `logs/attempts.log`), and never to `errors.log`. Failed attempts stay WARNINGs.
3. **The scripts that produced the evidence stay beside it,** as provenance.

**How 6 was chosen: on a new development set, never the frozen ones (D-93).**

- **The set:** `corpus/objective-02/dev-set.json` holds 28 questions in 31 runs: 24 expect an
  answer, 7 do not, and both roles are covered.
- **No overlap with the frozen sets:** a four-way check against all 56 frozen questions and turns
  flagged none.
- **The rule, set in advance:** zero ceiling hits and zero 503s first, then the best expected-answer
  match, then the smaller cap. One pass per setting, in-process on `kmp_obj02_20261101`, with every
  ask rolled back.

| | no cap | 3 | 4 | 5 | **6** |
|---|---|---|---|---|---|
| ceiling hits | 8 | 0 | 0 | 0 | **0** |
| 503s | 2 | 0 | 1 | 1 | **0** |
| match, with an expected source cited (of 24) | 9 | 13 | 14 | 15 | **15** |
| declined where no answer is expected (of 7) | 6 | 3 | 3 | 3 | **5** |
| slowest ask, seconds | 351 | 43 | 155 | 164 | **76** |

**Accepted with its trade-off.** The cap of 6 declined one fewer of the 7 no-answer questions than
the uncapped baseline.

- **No leak:** every cited item was within the asking role's scope.
- **The user accepted it.** The tool for questions with no real answer is the relevance threshold,
  which phase 2b sets from the same development set.

**Open:**

- **Two 503s were malformed JSON, not length:** under the caps of 4 and 5, a stray `})` and an
  unclosed object. The cap stays after those, so all three attempts repeated the error. This did
  not happen under 6, but it can happen at any cap.
- **The reduced retry never fired live.** No capped attempt hit the ceiling or broke its cap, so only
  the tests show it working.
- **Wrong-passage citations remain.** The right sentence often cites a different supplied item:
  under 6, the expected phrase appears in 20 of 24 runs, but only 15 match.
- **The summarise-the-onboarding question (d02) never matched,** under any setting.
- **One scoped question answered for the Employee (d11) grew with the cap,** from 1 statement to 6.
  None of its citations was out of scope.
- **The evidence:** `corpus/objective-02/runs/2026-11-07/statement-cap-sweep.md`.

## D-101 · `RELEVANCE_THRESHOLD` is 0.4231 and partial matches have a floor of 0.4036, chosen on the development set with a margin

**Status:** Settled by the user · **Date:** 2026-11-08 · **Concerns:** FR-12, D-37, D-40, D-56,
D-93, D-100 · **Stage:** step 7 of the post-M6 order, phase 2b · **Supersedes:** D-37's 0.30

**The order:** "Choose the D-56 floor, and any threshold change, from the dev set alone." The frozen
sets stay test sets (D-93). The development set is `corpus/objective-02/dev-set.json`: 31 runs, 24
expecting an answer and 7 not. The evidence is in
`corpus/objective-02/runs/2026-11-08/threshold-floor.md`.

**The rule the user approved first, and why its values were set aside.**

- **The rule:** the threshold that declines the most no-answer runs before generation without losing
  an answerable run, and the lowest floor at which no no-answer run is offered a partial match. On
  a tie, the middle of the tied interval.
- **It gave a threshold of 0.4472 and a floor of 0.4458** (commit `3c839bb`). On the development
  set, every answerable run was answered and every no-answer run was declined.
- **But the margins were 0.0015 for the threshold and 0.000085 for the floor.** Both are smaller
  than the query-vector drift D-40 recorded (about 0.003), which phase 1 also saw move mid-run.
- **And a floor 0.0014 under the threshold would almost never offer a partial match,** so FR-12's
  partial-match offer would rarely appear.
- **The perfect score was measured on the runs the values were chosen from.**

**The rule the user then approved, fixed before any new run: the same rule, with a margin of
`m = 0.006`,** twice D-40's drift.

- **Threshold:** declines a no-answer run only if its top score is at most T − m, and every
  answerable run's lowest expected-source score must be at least T + m.
  - The tied interval is [0.403550, 0.442714]. Its middle, rounded to four places, is **0.4231**.
  - That leaves **0.0256** on each side: 0.025550 above the highest declined no-answer score, d24
    at 0.397550, and 0.025614 below the lowest answerable expected-source score, d17 at 0.448714.
- **Floor:** at least the highest partial match offered to a run that path A declines, plus m (d24's
  D01, 0.397550), and at most T − m.
  - That gives **0.4036**, rounded up, and 0.006050 above D01.
  - Path A can offer partial matches in a band from 0.4036 to 0.4231.

**On the development set** (one pass, cap 6, every ask rolled back):

| | phase 2a (T 0.30, no floor) | literal rule (0.4472, 0.4458) | **margin rule (0.4231, 0.4036)** |
|---|---|---|---|
| 503s / cut-offs | 0 / 0 | 0 / 0 | **0 / 0** |
| answered where expected | 24/24 | 24/24 | **24/24** |
| declined where expected | 5/7 | 7/7 | **5/7**, all before generation |
| match with an expected source | 15/24 | 24/24 | **23/24** |
| out-of-scope citations | 0 | 0 | **0** |
| seconds per ask, median / max | 31.7 / 75.7 | 23.5 / 50.7 | **25.7 / 55.4** |

**What it costs:**

- **The two no-answer runs that score highest are answered wrongly:** d25, parking at the new
  office, and d26, the smoking policy. Each scores just above the threshold, so one passage reaches
  the model, which answers from it with a real, in-scope citation.
  - Verification cannot catch this, because it checks identifiers, not support (invariant 5's
    conceded limit).
  - Phase 2a missed two other runs, d11 and d21 for the Employee. Both are now declined before
    generation.
- **One answerable run lost its match** (d13): a second passage was admitted, and a statement cited
  the wrong one of the two.
- **Most answers now draw on one passage.** At 0.30 the median was five. Questions that need several
  sources are untested beyond this set.

**Not yet measured, and therefore the real test:**

- the frozen thirty questions and the nine threads (the step 7 "after");
- the demonstration script's D-40 screen, which required a top score of 0.35 when the threshold was
  0.30;
- the alpha. It is not redeployed with these values until they are re-scored.

**Open:**

- **An empty partial-match offer now implies the question never reached generation.** It discloses
  nothing outside the caller's scope (`partial_matches.py`, `docs/api-contract.md`).
- **CLAUDE.md §5** now shows both values, with the user's approval of 8 November.

**Dated note, 8 November 2026: the threshold does not carry over to the frozen thirty.** The step 7
"after" ran the frozen question set on `a53c5de`, `main` after #56. The evidence is in
`corpus/objective-02/runs/2026-11-08/after/after-thirty.md`.

- **Seven answerable questions took path A,** where 1 November had two: q06, q13, q15, q18, q21,
  q22, and s03 for the Administrator.
  - The right source was retrieved for each, ranked first in six of the seven and second in q22.
    It scored 0.33 to 0.42, under 0.4231.
  - The expected-answer match stayed at 16 of 22. The misses moved from wrong answers to no answer.
- **What held:** 100% first-attempt conformance, no 503s, no fabricated identifiers and no leaks.
- **Why:** the development set's questions were written from the documents, so they score higher
  than questions phrased as users ask them. The threshold suited the development set and does not
  carry over.
- **The user's decision:** rebuild the development set in users' wording, and re-choose the
  threshold and floor by the same margin rule.
- **Disclosed:** any value chosen from now on has been informed by this frozen result, so the frozen
  thirty no longer independently tests the threshold.
- **The rest of the "after"** (the threads, the HTTP check and NFR-08) waits for the re-chosen values.

## D-102 · `RELEVANCE_THRESHOLD` stays at 0.30 and there is no partial-match floor; retrieval scores cannot separate answerable from unanswerable questions in users' wording

**Status:** Settled by the user · **Date:** 2026-11-08 · **Concerns:** FR-12, D-37, D-56, D-93,
D-100 · **Supersedes:** D-101's values (0.4231, 0.4036) · **Stage:** step 7 of the post-M6 order,
phase 2c

**What was tried, in order:**

1. **D-101: 0.4231 and 0.4036,** chosen with a margin on `dev-set.json`. That set's questions were
   written from the documents.
2. **The frozen thirty on `main`** (D-101's note, PR #57) turned 7 answerable questions away. The
   right source was retrieved for each, but scored 0.33 to 0.42.
3. **The user rebuilt the development set in users' wording** (`corpus/objective-02/dev-set-v2.json`:
   37 questions in 40 runs, 32 answerable and 8 not). Its questions share half as much of the
   documents' wording as the first set's (median 0.33, against 0.67). It does not overlap the frozen
   sets.
4. **The same margin rule on v2 gave 0.24 and a floor of 0.206** (`2ea9e95`). Only 1 no-answer run
   could be declined with a margin, because the lowest answerable score is 0.28.

**What v2 showed:** no threshold separates the two groups. Five no-answer runs outscore three
answerable ones, and "how do I apply for parental leave?" outscores 22 of them. End to end on v2,
with the cap of 6 and every ask rolled back:

| | **0.30, no floor** | 0.24, floor 0.206 |
|---|---|---|
| declined where no answer is expected | **7/8** (2 before generation, 5 by generation) | 3/8 |
| match with an expected source | **22/32** | 15/32 |
| answerable runs ending in no answer | 3 | 2 |
| 503s / out-of-scope citations | 0 / 0 | 0 / 0 |

- **0.24 did worse:** up to 13 passages reached the prompt, with more wrong-passage citations and
  more unanswerable questions answered.
- **0.4231 loses answerable questions phrased as users phrase them.** 14 of v2's 32 answerable runs
  score below it, and the frozen thirty lost 7.

**Decision (the user's):**

- **`RELEVANCE_THRESHOLD` stays at 0.30,** D-37's value.
- **The cap of 6 stays** (D-100). At 0.30, generation does most of the declining, and the cap keeps
  its replies short enough to finish.
- **No partial-match floor:** `PARTIAL_MATCH_FLOOR = 0.0`. The margin rule cannot set one at 0.30.
  Its lower bound, u24's offer at 0.292898 + 0.006 → 0.2989, is above its ceiling, T − 0.006 =
  0.294. Counting only no-answer runs would fit (0.2936), but it would also remove the offers that
  point u07 and u24, two answerable runs, at their expected sources. So D-56's gap stays open:
  unrelated items are still offered to unanswerable questions.

**What this establishes:** a threshold chosen from retrieval scores alone cannot decide whether a
question is answerable, once questions are worded as users word them. That decision falls to
generation, with verification behind it.

**Open:**

- **The frozen thirty no longer independently tests the threshold** (D-101's note). It still tests
  the cap, which no frozen result informed.
- **The "after" continues on the build with these values:** the frozen thirty again (the first run of
  the cap at 0.30 on held-out questions), the nine threads, the HTTP check and NFR-08.
- **D-56** (partial-match relevance) and wrong-passage citations remain.
- **`CLAUDE.md` §5's two rows are corrected,** under the user's approval of keeping that table true.

**Dated note, 8 November 2026: the step 7 "after" on these values.** All four runs were made on
`19c98a8`. The evidence is in `corpus/objective-02/runs/2026-11-08/after-030/after.md`.

- **The frozen thirty:**
  - ordinary questions answered correctly rose to 19 of 22, from 16 of 22 on 1 November;
  - none was left unanswered;
  - 100% first-attempt conformance, and no leaks.
  - **But correct declines fell from 6 of 8 to 2 of 8.** Three scoped questions asked by the
    Employee, and three no-answer questions, were answered from material the asker may see.
  - **No out-of-scope chunk was used**, so invariant 1 holds. Still, those questions should get the
    no-answer reply.
  - For the cap, this is a held-out result. Whether the cap sentence, prompt rule 8 or D-40's
    variance causes it is not isolated. **Open.**
- **NFR-08 (D-95):** 0 503s, against run 3's 3, and 25 of 25 answered. The p90 was 350,407 ms, a
  valid FAIL against 4,000 ms: still a local-model baseline. The 503s D-82 traced are gone under
  load.
- **FR-13 (D-91):** follow-ups answered correctly with history rose from 1 of 9 to 2 of 9 (t04 now
  resolves), and spelled out from 3 of 9 to 6 of 9. Schema conformance reached 100%.
  - The HTTP check: WIRED 3 of 3, 0 leaks. t04's second turn was correct through the server.
  - FR-13 stays partial: most follow-ups that need the earlier turn still fail.

## D-103 · FR-13's follow-up options 1 and 2 were built, measured and not adopted; a single-run delta on these sets sits inside a measured ±1–2-run band

**9 November 2026 · Step 7 phase 3 · Evidence: `corpus/objective-02/runs/2026-11-08/fr13-phase3-dev/`
and `runs/2026-11-09/fr13-phase3/` · Branch `fix/FR-13-follow-up-focus`, commits `b2ebba8`, `d19a027`.**

**What was tried,** against D-91's open failure (follow-ups restate turn 1), approved 8 November:

- **Option 1:** a conversational-block instruction to answer only the question asked and not restate
  facts that answer the earlier questions. Single-turn prompts stayed byte-identical, under test.
- **Option 2:** rank each in-scope candidate by the larger of its score against the composed
  retrieval string and against the follow-up alone. Scope filtering untouched, before ranking.

**The rule, fixed before any run:** adopt only what raises with-history matching on a new
development thread set without lowering first-turn, spelled-out, correct declines, conformance, or
the zero out-of-scope count. Tuning ran on `corpus/objective-02/dev-threads.json` (12 user-worded
threads, t20–t31; automated overlap against both frozen sets at phase 2a's thresholds, 0 of 1,960
pairs flagged), never on the frozen sets (D-93).

| config | with-history | first-turn | spelled-out | cold | declines | schema | out-of-scope |
|---|---|---|---|---|---|---|---|
| main | 8/12 | 8/14 | 9/12 | 6/12 | 3/6 | 52/52 | 0 |
| option 1 | 8/12 | 8/14 | 9/12 | 6/12 | 3/6 | 52/52 | 0 |
| option 2 | 7/12 | 7/14 | 9/12 | 7/12 | 3/6 | 52/52 | 0 |
| both | 6/12 | 8/14 | 9/12 | 7/12 | 3/6 | 52/52 | 0 |

**Decision: neither is adopted.** `apps/` and `scripts/` stay byte-identical to `711fcda`. The full
candidate — both options, their 11 break-tested tests, the harness and HTTP-check updates — is
preserved at `runs/2026-11-08/fr13-phase3-dev/candidate_code.diff`, one `git apply` from returning.

- **Option 1 moved nothing:** 8/12 against 8/12 — two threads gained, two lost, each by a single run.
- **Option 2 admitted more passages at 0.30** (t21, t22, t24, t27), and the extra passages correlated
  with lost matches — the direction D-102 measured at 0.24. Where it worked exactly as designed
  (t28-admin: the right source from unsupplied to rank 2, supplied), generation still answered from
  turn 1's material. The restatement failure is in generation's use of the context, not in what
  retrieval supplies.
- **For D-102's open decline problem:** correct declines sat at 3/6 in every configuration — the
  option 1 instruction did not move the scoped answering behaviour at all — and t29-admin cited D14
  over the supplied D15 in all four configurations, giving the wrong-passage problem a reproducible
  case. Any retrieval change that admits more passages at 0.30 should be expected to push declines
  further down.

**The variance band, now measured rather than suspected.** The frozen nine were re-run on code
byte-identical to the 8 November "after": with-history came back **3/9 against 2/9**, exactly one of
44 runs flipped — on an identical supplied passage set — and after-030's four cold fabrications did
not recur. On sets of 9–12 threads, a single-pass delta of ±1–2 runs is noise. After-030's "1/9 →
2/9" and this run's 3/9 are the same number inside that band, and no future FR-13 delta may be read
as an effect unless it clears it.

**Why the development set could not detect the fix it was built to tune:** 8 of its 10 answerable
follow-ups keep their source inside turn 1's item, so retrieving turn 1's material still supplies
the right passage and the frozen failure mode — cross-source follow-ups — does not reproduce
(main: 8/12 with history on the development threads, 3/9 frozen).

**Before any further attempt:** a cross-source development thread set, and repeated draws per
configuration so the rule compares means, not single passes. Until then FR-13 stays partial (D-91)
and D-56 stays open.

**Disclosure (under D-93):** the builder read `runs/2026-11-07/dev_set_overlap.txt` — phase 2a's
console record, which quotes ~25 frozen questions — while studying the overlap method, before
drafting. The drafts avoided those topics and the identifier-only automated check is the control.
On the record; whether that console file should be redacted from the repository is open.

## D-104 · FR-10's classification is the fourth AI operation, `classify_document`, in its own module

**Status:** Settled by the user · **Date:** 2026-11-08 · **Concerns:** CLAUDE.md §4,
docs/ai-provider.md §1, `apps/ai/base.py`, invariant 10, D-19, D-33 · **Stage:** Objectives 05 and 06
(NIT3004), due 13 November 2026 · **Builds on:** D-33 part 1, which deferred FR-08's classification
hand-off to FR-10

**The question.** CLAUDE.md §4 said the AI service exposes "exactly three operations", and
`apps/ai/base.py` said classification "gets its own method then". NIT3004 asked for it on 8 November
(Objective 05). The lead chose the shape; the alternatives are at the end.

**Decision.**

- **A fourth operation,** `classify_document(title: str, text: str, scheme: TagScheme) ->
  DocumentClassification`, on `AIService`, implemented by `FLMService`, `AnthropicService` and the
  test stub. CLAUDE.md §4, `docs/ai-provider.md` §1 and `apps/ai/base.py` now name the operations as a
  list rather than a count ("exactly the operations listed here"), with the date, so the next
  operation leaves no stale number behind. CLAUDE.md §4 also names `apps/ai/base.py`, the file the
  contract has always lived in (it said `apps/ai/provider.py`, which never existed).
- **One structured request returns the type, the department and the tag suggestions together,**
  FR-10's Server-End clause: "a single structured request issued at upload returns the classification,
  the summary and key points, and the tag assignments together, at the cost of one call rather than
  three". The summary and key points are not requested yet: the lead's decision of 7 November is
  breadth over depth, and they are built only if time allows after both verifications pass. The schema
  gains them then.
- **The reply schema, `CLASSIFICATION_SCHEMA`** (`apps/ai/classification.py`): `doc_type` and
  `department`, each `{value, confidence}`, and `tags`, a list of `{dimension, value, confidence}`,
  every confidence a number in [0, 1]. `doc_type.value` must be one of `DOCUMENT_TYPES` (Policy,
  Procedure, Report, Meeting Paper, FR-10's fixed list); any other value is a schema violation, because
  a type outside the fixed list is not a classification. A reply that does not conform is no reply:
  retried to `MAXIMUM_CLASSIFY_ATTEMPTS`, a total of 1 initial call + 2 retries (D-19), then
  `ProviderUnavailable`. Invariant 10 applies to this operation exactly as to generation.
- **Its own module.** The prompt, the schema, the tolerant parser and the attempt loop live together in
  `apps/ai/classification.py`. `prompting.py` and `generation.py` are untouched: a sibling branch
  (`fix/FR-13-follow-up-focus`) is changing `prompting.py`, and the generation loop carries the
  statement-cap policy (D-100) that classification does not share. The JSON extraction is shared with
  `schema.py` through public aliases, so there is one copy of it.
- **What is sent:** the title and the opening `CLASSIFICATION_INPUT_TOKENS` (1,500) whitespace tokens
  of the extracted text, D-31's token. The record keeps `input_truncated`. FR-10's "summarised in
  sections and consolidated" for long documents is deferred with the summary; the opening of a
  document is where its kind is stated, and the one corpus document over the limit (D04, 8,357 words)
  says in its first chapter that it holds procedures.
- **The prompt shows the model the scheme** (D-105's audience-scoped scheme: the four types, the
  departments, the tag values per dimension) and asks for values from it, allowing a new value in Topic
  only. The application enforces the scheme rule regardless of what the model says.
- **The provisional rule, the scheme rule and provenance are application code** (D-105), never the
  model's judgement: the same division invariant 5 makes for citations. The operation returns the
  suggestions as made.

**Why not the alternatives.**

- *Generalise `run_generation_attempts` into one shared loop first.* Cleaner in the long run, and about
  a day of the five, on the path NFR-19's fault-injection test guards.
- *Prompt in `prompting.py`, schema in `schema.py`.* One file for prompts, and a near-certain merge
  conflict with the FR-13 branch.

**Not covered:** the confidence threshold's value and how it is chosen (D-106); the summary and key
points; FR-16's summarisation, which gets its own method the same way, when it is built.

**Dated note, 10 November 2026 (night): the summary, the key points, sectioned summarising and the
summary's grounding are not built in NIT3004.** The user's decision on the requirements audit
(D-119, its finding 1). This entry built them "only if time allows after both verifications pass",
and neither objective passed on its independent run (D-106, D-110). FR-10 therefore stays
INCOMPLETE on its summary clauses:

- the short summary and key points beneath the title in search results;
- one request returning them together with the classification;
- sectioned summarising and consolidation of long documents;
- the summarisation prompt's grounding;
- the summary in the classify route's 200.

What the classifier reads stays capped at `CLASSIFICATION_INPUT_TOKENS`, with `input_truncated`
recorded and shown, as before.

## D-105 · Schema v2 for FR-10: `DocumentAnalysis`, two `ContentTags` columns, the audience-scoped scheme, and how a suggestion becomes a record

**Status:** Settled by the user · **Date:** 2026-11-08 · **Concerns:** FR-10, FR-15, invariants 1, 4
and 8, D-17, D-30, D-33, D-72, D-73, D-74, docs/schema-v1.md §1 and §2 · **Builds on:** D-104

**The tables.** `docs/schema-v1.md` §2 deferred `DocumentAnalysis` to migration v2 "when its
requirement is built". It is built now, as `documents 0008`, additive and reversible.

**`DocumentAnalysis`, one row per document,** with these departures from the proposal's field table
(`analysis_id, doc_id, doc_type, department, confidence, user_edited`), each for a stated reason:

- **Two confidences, not one:** `machine_doc_type_confidence` and `machine_department_confidence`.
  FR-10 says "any assignment falling below the configured confidence threshold must be marked
  provisional"; the type and the department are two assignments, and one column cannot hold one
  provisional and the other applied.
- **The machine's values are kept beside the person's:** `machine_doc_type` and `machine_department`
  are always the latest machine assignment; `doc_type` is the effective type, null while a provisional
  suggestion waits. FR-10: "the machine assignment is retained alongside it so that classification
  accuracy can be measured over time". Only the latest machine value is kept; a history is not.
- **The effective department is `Documents.department`,** not a column here. D-72 made that column the
  one source FR-14 and FR-15 read and said FR-10 "should write this column, so there stays one source".
- **An outcome per assignment,** `doc_type_outcome` and `department_outcome`, from a fixed vocabulary
  `ASSIGNMENT_OUTCOMES = ("applied", "provisional", "discarded", "confirmed")` in
  `apps/core/constants.py`: *applied*, at or above `CLASSIFICATION_CONFIDENCE_THRESHOLD` and written
  to the effective field, still marked AI-generated and editable; *provisional*, below it, held and not
  written; *discarded*, outside the scheme (the department only: the parser refuses a type outside the
  fixed list); *confirmed*, a person confirmed or edited it. The lead approved two booleans for this;
  the vocabulary holds the same facts plus the discarded state, which a boolean could not.
- **`user_edited`:** true once a person confirmed or edited the type or the department. From then on a
  re-run records new machine values and touches nothing else (FR-10: "any value a user edits are
  retained and is not overwritten by later reprocessing").
- **`proposed_topics`, JSON:** out-of-scheme Topic suggestions awaiting confirmation, as
  `{value, confidence}`. FR-10 says a new value "requires user confirmation before it is created", so
  no `Tags` row may exist for it until then. **`discarded_suggestions`, JSON:** out-of-scheme Project
  and Process suggestions, kept for Objective 05's evidence of the scheme clause and never shown as
  tags.
- **`model`, `input_truncated`, `classified_at`:** provenance of the record.

**`ContentTags` gains `confidence` and `provisional`.** A provisional AI tag is held, not applied: it is
not read by FR-15's browse facets, filters or the detail's `tags`, and appears only as a suggestion
awaiting confirmation. `applied_by` and `confirmed` keep their meaning (D-74).

**The scheme a document is classified against is the vocabulary readable by its own audience.**
`apps/documents/classification.py::tag_scheme(document)` builds it for every role in the document's
`visible_to_roles`: the four types; the distinct non-blank `Documents.department` values, except one
that some role in the audience can read no document of; the active `Tags` per dimension, except one
that is linked only to sources some role in the audience cannot read. A tag with no links is vocabulary
only and is always in; a document nobody may read gets the full scheme. The scope predicates are
`scoped_documents` and `scoped_meetings` (invariant 1's one helper), never a hand-written one.
**Why:** D-74 built the demonstration so that an Employee "is never offered" the Project value
`atlas`, which exists only on Administrator-only documents. A classifier proposing `atlas` on an
Employee-visible document would hand every Employee that name. The same holds for the department
`Projects`, carried only by D09 and D15.

**How a suggestion becomes a record** (`apply_classification`, one transaction):

1. The analysis row is created or updated; the machine values, `model`, `input_truncated` and
   `classified_at` are always overwritten.
2. **The type:** provisional below the threshold, applied at or above it; `doc_type` is written only
   when applied. Untouched when `user_edited`.
3. **The department:** discarded when not in the scheme; provisional below the threshold, with
   `Documents.department` untouched; applied at or above it, written to `Documents.department`.
   Untouched when `user_edited`.
4. **Each tag suggestion,** normalised with `normalise_tag_name`: in the scheme, a `ContentTags` link
   is created with `applied_by="ai"`, `confirmed=False`, its confidence and `provisional` by the
   threshold; an existing confirmed or user-applied link is left alone (FR-10: "a tag confirmed by a
   user is marked confirmed and is not altered by later reprocessing"); an earlier unconfirmed AI link
   takes the new confidence. Out of the scheme, Topic goes to `proposed_topics` and Project or Process
   to `discarded_suggestions` (FR-10's controlled taxonomy growth). Links a re-run no longer mentions
   are left in place.

**Who may confirm, edit or reject: `contribute_content`, on documents in the caller's scope.** FR-10
says "users holding the appropriate permission" and names none. Both roles hold `contribute_content`
(D-30), so an uploader confirms the suggestions on their own document, which is the demonstration
flow. The server checks it on every confirm, edit and reject, after the scoped 404 (D-73's order,
invariant 4). *Declined:* `manage_documents` only, which would stop Employees acting on their own
uploads; a new code, which nothing yet needs.

**The routes** (built in the step after this entry; recorded here so the contract has one source):
`GET /api/documents/{id}` gains `classification` and `tag_details`; one confirm-or-edit action for
the type and department; one confirm and one reject action each for a tag link and for a proposed
topic; `POST /api/documents/{id}/classify` re-runs classification (200 with the classification, 422
where no text was extracted, FR-10's code, 503 after `MAXIMUM_CLASSIFY_ATTEMPTS`); and
`manage.py classify_documents` for the Objective 05 run, calling the same function. Exact paths and
bodies are in `docs/api-contract.md`.

**Classification at upload** (D-33 part 1, invariant 8): after the ingestion pipeline has decided the
document's status, inside a savepoint of its own, with every exception caught and logged. A failed
classification leaves no analysis row, which is what "unclassified" means; the document's status is
never changed by it, and a reprocess (D-32) runs it again while confirmed and edited values survive.

**FR-10's `409 Conflict on a duplicate tag name within a dimension` is not reachable by design,**
and is recorded as a convention: matching against the scheme happens at suggestion time, and
confirming a proposed topic finds or creates the `Tags` row by normalised name.

**Not covered:** the tag browser with item counts (FR-15's facets already count tags); the summary and
key points; a history of machine assignments; meetings, which nothing classifies.

**Build notes, 9 November 2026** (the django-backend agent's choices where the brief was silent,
accepted as written):

- The provisional comparison uses the float the model reported; the columns store it quantised to
  three decimals, so a confidence within 0.0005 of the threshold can read differently from its
  outcome. `discarded_suggestions`, like `proposed_topics`, is replaced on every run, deduplicated by
  dimension and normalised value. An empty department suggestion is `discarded`. A type outside
  `DOCUMENT_TYPES` reaching the apply layer raises before anything is written. The document row is
  locked for the apply, as deletion and reprocess lock it.
- Confirming or editing the classification of a document that has no analysis is a 404: the type of a
  never-classified document is edited after `classify` runs, not instead of it. A blank department
  given by a person is written blank and marked confirmed.
- **Open, recorded rather than built:** a rejected proposed topic is proposed again by a later run; a
  document's scheme is built for its audience at classification time, so widening its visibility later
  does not reclassify it; a suggestion in a dimension outside the three is logged and counted nowhere
  durable. `confirm_proposed_topic` reactivates a deactivated Topic tag of the same name rather than
  creating a duplicate.
- The routes: `POST /api/documents/{id}/classify` (200, 422 insufficient text, 503 provider; the
  "ingestion" throttle scope, no in-flight slot), `POST /api/documents/{id}/classification`
  (confirm or edit; 400 invalid type), `POST .../tags/{content_tag_id}/confirm`, `DELETE
  .../tags/{content_tag_id}`, `POST .../proposed-topics/confirm` and `.../reject`; the detail gains
  `classification` and `tag_details`, and the 201 upload and reprocess bodies gain `classification`.
  Lists and browse do not. `manage.py classify_documents --all|--document <uuid> --out <json>` is the
  Objective 05 instrument.

**Dated note, 10 November 2026: two decisions after the routes were built** (the user's, on the
django-backend agent's report).

- **The machine fills only a blank department.** As first built, an in-scheme department suggestion
  at or above the threshold replaced the department the uploader typed, on upload and on every
  reprocess, until someone confirmed. FR-10 says a value a person gives "is not overwritten by later
  reprocessing". Now: a blank `Documents.department` takes an applied suggestion; one that already
  holds the suggested value stays and the outcome is applied; one holding a different value stays,
  and the suggestion is provisional, held for a person to accept. The value already there may have
  been typed by the uploader, confirmed, or written by an earlier run; none of them is replaced by a
  later run. Out of scheme is still discarded, and below the threshold still provisional. On the
  twenty, which all carry uploader departments, Objective 05's department outcomes stay measurable
  and no department is changed. *Declined:* marking a typed department confirmed, which would show
  no department behaviour on the reference set; keeping the overwrite.
- **Classification stays at upload, and its cost is recorded.** Every upload and reprocess now waits
  for one classification call, inside the ingestion transaction and holding the document's row lock,
  where the proposal's 7.8 places it and where it cannot fail the document. On FLM one call took
  7.6 to 21.2 s in D-106's sweeps, and up to `MAXIMUM_CLASSIFY_ATTEMPTS` are made. **An estimate,
  not a measurement:** D04 (26 pages) ingested in 33.3 s on 1 November, so with classification about
  41 to 55 s, and a retry could take a large document past Objective 02's 60-second bound for a
  document of twenty pages or fewer. **Owed before M8:** re-time that bound with classification on,
  on the host D-114's choice lands on. *Declined:* moving the call after the ingestion commit, which
  does not shorten the upload; re-timing now on a throwaway database.

**Dated note, 10 November 2026 (night): a correction to "Classification at upload".** That paragraph
says the call runs "after the ingestion pipeline has decided the document's status". It does not. It
runs between storing the extracted text and chunking (`apps/ingestion/documents.py`, section 7.8
step 4), before the status is decided, as this entry's note on the upload's cost already describes.
The rest of the paragraph stands: the call has its own savepoint, catches and logs every exception,
and never changes the document's status. Found by the requirements audit (D-119, its finding 7).

**Dated note, 10 November 2026 (night): the tag corrections (D-119's findings 3, 4, 5 and 10).**
The user's decisions on the requirements audit (D-119's table), built on
`feat/FR-10-tag-corrections`, server side only; the interface half follows on the same branch. Each
decision is recorded with its reason, and each build choice the brief left open is named as one.
*Corrected the same night, after the requirements re-audit of `5377e3a`: the interface half
landed on the same branch, in `1641693`, `c6f59d4`, `607feaa` and `4d53cb7`.*

- **A removal is kept (finding 3).** FR-10's correction clause: "any value a user edits are retained
  and is not overwritten by later reprocessing, and the machine assignment is retained alongside
  it". `reject_tag` deleted the link, so the machine's assignment was lost and the next classify or
  reprocess linked the tag again. `documents 0009` adds `ContentTags.removed`, additive and
  reversible.
  - **Removing an AI link** (held or applied, confirmed or not) sets `removed` and keeps the row,
    with the confidence and provisional flag the machine gave it. **Removing a person's link
    deletes it**: it holds no machine assignment to keep. The route keeps its URL and its 204.
    *Changed the same night, after the requirements re-audit of `5377e3a`: a person's link is kept
    and marked removed too, because deleting it let the next run link the value again (the last
    bullet of this note).*
  - **No read lists a removed link.** Every read that excluded a provisional link excludes it: FR-15's
    facets, filters and the detail's `tags`. So does `tag_details`, which does list provisional
    links: a held suggestion waits for a decision, and a removed one has had it.
  - **Reprocessing respects it.** A later classify or reprocess neither links the tag again nor
    alters the removed row, so the confidence it keeps is the machine's at the time of the removal.
    A Topic removed from a document is not proposed for it again, even once its Tag is retired.
  - **`tag_scheme` still counts a removed link as a link,** as it counts a provisional one. A removed
    suggestion on a restricted document is still a fact about that document, and not counting it
    would turn a value carried only by restricted material into vocabulary every audience is
    offered (invariant 1). *Corrected the same night, after the requirements re-audit of
    `5377e3a`: the behaviour stands, but this reason has not held since `824c536`, where a tag that
    is not grown is vocabulary whatever its links and a grown one never is. What counting a removed
    link does now: the tag stays in its own document's scheme, offered there to be applied again
    (`200`) and shown to the classifier, which leaves the removed link alone.*
  - *Build choices:* a removed link's id is the same 404 as an unknown one on the confirm and remove
    routes, because nothing ever shows it; confirming a proposed Topic whose link was removed
    restores that link; `manage.py classify_documents` flags removed links in its record and counts
    them apart in its summary line.
  - *Declined:* recording the removal in a table of its own, which is a second home for one boolean.
- **The department label (finding 10).** When the department the uploader typed equals the AI's
  suggestion, the outcome is "applied", and the interface labelled the department "Suggested by AI"
  although a person supplied it. The outcome cannot tell that case from a run that wrote its
  suggestion into a blank department: both read "applied" with the department equal to the
  machine's value. `documents 0009` adds `DocumentAnalysis.department_applied_by`, in the tags'
  provenance vocabulary:
  - `"user"`: a person gave the department, typed at upload or written through the confirm route.
  - `"ai"`: a run wrote it into a blank department, and no person has written it since. A person
    confirming that value as it stands keeps `"ai"`, as a confirmed AI tag keeps
    `applied_by: "ai"`.
  - `null`: no department.

  Rule 3 of `apply_classification` sets it, and `confirm_classification` sets it where a person
  writes the department. It needs history, which is why it is a column rather than something worked
  out on each read: a second run that finds the machine's own earlier value equal to its suggestion
  is the same state as finding 10's case, except for who wrote the value.
  - **Rows classified before 0009 read null** until their next run or confirmation, and the
    interface treats null as before. Their history is recorded nowhere, so none is guessed. A
    department a run wrote into a blank before 0009 reads as the person's after its next run, which
    is the one way this field can still be wrong. The Objective 05 twenty should hold none: all
    twenty carry uploader departments (this entry's note of 10 November), and both measurement runs
    (`aee5374`, `caf9e22`) descend from `2a85c9a`, where the machine began filling only a blank
    department. That is checked against the git history, not against the database.
  - *Declined:* a fifth outcome, which would change what "applied" means in Objective 05's records
    and in `scripts/objective05_verify.py`; marking a typed department "confirmed", which this
    entry's note of 10 November already declined.
- **The stale comment (finding 10).** The comment above `MAXIMUM_CLASSIFY_ATTEMPTS` said it was named
  "not so anything uses it before Stage 6". `apps/ai/classification.py`'s attempt loop has used it
  since D-104. Corrected, and the same stale phrase in `apps/core/tests/test_constants.py` with it.
- **A person applies a tag (finding 4).** FR-10's provenance clause speaks of tags "applied by a
  person", and UC-09 A3 of a person who "adds one it did not", but only the D-74 seed script ever
  wrote a person's link. `POST /api/documents/{id}/tags` (`apply_tag`) is guarded as the other FR-10
  routes are: 401, then the scoped 404, then `contribute_content`'s 403 (D-73's order). Its body is
  exactly one of two forms:
  - `{"tag_id"}`: an existing tag, which must be active and in the document's scheme.
  - `{"dimension": "Topic", "tag_name"}`: a new Topic, normalised as `Tags` normalises a name.
    Only Topic may grow, by FR-10's controlled taxonomy growth, so any other dimension is a 400.
  - **One 400 for a `tag_id` that cannot be applied.** Unknown, inactive, a Department tag or
    withheld from the document's audience all get the same body, so the route cannot be used to
    learn that a restricted tag exists (invariant 1).
  - **The 409, and why an out-of-scheme name answers as created.** FR-10's "409 Conflict on a
    duplicate tag name within a dimension" is answered only for a Topic already in the document's
    scheme. The caller is offered that Topic anyway, and the 409 carries its id. A Topic of that
    name that exists but is outside the scheme is carried only by material some reader of the
    document cannot see, or is inactive. *Corrected the same night, after the requirements re-audit
    of `5377e3a`: since `84b5771` it may also be a grown Topic that nothing links, and since
    `824c536` it is always a grown Topic that no source every reader of the document can read
    carries, one nothing links included, or an inactive one, as `classification.py` and the
    contract say.* Answering 409 for it would tell the caller that a value they cannot see exists.
    So it is linked as it stands, reactivated if it was inactive (as `confirm_proposed_topic`
    already does), and answered 201 exactly as a new Topic is. *Corrected the same night, after the
    focused re-audit of `88a488d`: unless this document already holds a link to it, live or
    removed, which is kept or restored: 200. Since a person's removal is kept, a Topic typed,
    removed, retired and typed again on the same document is that case. The answer depends only on
    the document's own links.* A test
    compares the two replies byte for byte, with only the new link's id masked: `Tags` has no
    timestamp, and the reply carries no tag id, so nothing in it tells them apart. Timing is not
    claimed to be indistinguishable. This entry's "the 409 is not reachable by design" is
    superseded: it is reachable now, for an offered name.
  - **The new link** is `applied_by: "user"`, `confirmed: true` (the D-74 seed's choice: a person's
    tag is a decision already made), not provisional, not removed, confidence null, and the route
    answers 201. A tag already on the document answers 200 with no new row:
    - held: confirmed, as the confirm route does;
    - removed: restored and confirmed, keeping its `applied_by` and the machine's confidence;
    - applied or confirmed: left as it is, which includes an applied AI link nobody has confirmed.
  - *Build choices:* a restored link is also no longer provisional, since a confirmed link is never
    held (`confirm_tag` clears both together); the brief named the other fields and not this one.
    The reply is `{"tag_details": [...]}`, the document's whole list in the classify reply's
    shape, wrapped as the proposed-topic replies wrap theirs. The 409 carries the offered tag's id.
- **`tag_options`, the choices (finding 4).** The brief asked for the document's scheme on "the
  classification GET route". There is no such route: the interface reads the classification from
  `GET /api/documents/{id}`, so `tag_options` is carried there, recorded as a correction to the
  brief. It is `tag_scheme`'s tags with their ids, `{Project, Process, Topic: [{tag_id, tag_name}]}`
  (`offered_tags`, `tag_options`).
  - **Why every value in it is readable by the caller.** *Corrected the same night, after the
    focused re-audit of `88a488d`: every grown value in it. A tag that is not grown is vocabulary,
    readable through no source and disclosing none, as the correction after the next bullet says.*
    A linked value is offered only if every role in the audience reads a source carrying it. A
    caller reaches the detail only if their role reads the document, so some audience role is one
    the caller's role reads, and EFFECTIVE_ROLES is closed under generalisation (D-66).
  - **What the brief's sentence overstates.** "Every value in it is readable by every role in the
    document's audience" is true of linked values only. An unlinked tag is in every scheme as
    vocabulary (this entry's rule), and so in every document's `tag_options`, readable through no
    source at all. That has always reached the classification prompt; `tag_options` now lists it
    to every reader. Since the oracle bullet below, this holds for unlinked tags that are not
    grown: Project and Process tags, and seeded Topics.
    *Corrected the same night, after the requirements re-audit of `5377e3a`: since `824c536` (the
    security review's bullet below) a tag that is not grown is offered whatever its links, and only
    a grown tag needs every audience role to read a source carrying it. Read "linked values" in
    these two bullets as grown ones, and "unlinked tags that are not grown" as every tag that is not
    grown.*
  - **A residual, for the lead.** A tag becomes unlinked when its last link is deleted, and two
    paths delete links: removing a person's own tag (this note's rule, since it holds no machine
    assignment) and deleting a document (D-73). So a Topic a person typed on an Administrator-only
    document and then removed would be listed, by name, to Employees. The kept AI removal does not
    do this, because a removed AI link still counts as a link. Two changes would close the path:
    keeping a person's removed link too, or an Administrator deleting the unused tag (finding 5's
    route). Neither is built as a rule; the decision is the lead's. The lead's review found the
    worse half of it the same night, and the oracle bullet below closes it for every Topic a
    person brought in by name. *Since the requirements re-audit of `5377e3a` a person's removed link
    is kept too (the last bullet of this note), so only deleting a document or a meeting deletes a
    link.*
- **An Administrator retires a tag (finding 5).** FR-10: "Tags are deactivated rather than deleted
  where content still references them, preserving historical classification", and its CRUD line
  gives Tags "Delete". Only the schema held either (`Tags.active`, and `PROTECT`, D-12).
  - **`manage_tags`,** a new permission code (`MANAGE_TAGS_PERMISSION`), seeded to the Administrator
    alone by `accounts 0008`, additive and reversible, as 0007 seeds `review_knowledge_gaps`. Its
    test holds that every role given the code has the Administrator's scope, as FR-19's seed test
    does (the security review's L3). *Declined:* `manage_documents`, so that granting one never
    grants the other, D-99's reason.
  - **`GET /api/tags`**: 401, then 403 without `manage_tags`, checked before anything else, because
    nothing on the route is scoped. It lists every Tag in Project, Process and Topic, active or
    not, ordered by dimension then name, each with `item_count`: the sources, documents and
    meetings alike, with a link to it that is neither provisional nor removed, each counted once.
    An Administrator reads every source (D-66), so no count tells them anything they could not
    read. This is the Administrator's list of every value with its count; FR-15's facets, recorded
    above as FR-10's tag browser, are unchanged.
  - **`DELETE /api/tags/{id}`: deactivate versus delete.** 401, then 403, then 404 for an id that
    names no tag in those three dimensions (a Department tag included, since nothing reads one,
    D-72). A tag any `ContentTag` row references, in **any** state, is deactivated and kept, and
    the route answers 200 with it in the list's shape; again for one already inactive. A tag
    nothing references is deleted, 204. Any reference keeps it, a removed or held link included:
    `PROTECT` refuses the delete, and a removed link exists precisely to keep the machine's
    assignment, which needs its tag. The tag row is locked for the check and the delete.
  - **What retiring does, and does not, do.** An inactive tag leaves `tag_scheme`, so neither the
    machine nor a person can newly apply it by id, and it leaves every document's `tag_options`.
    FR-15's reads keep their treatment of `active` unchanged: they do not consult it (D-72's
    clarification of 7 October). So a retired tag still shows on the documents that carry it, in
    `tags` and `tag_details`, as a facet value and as a filter. That is FR-10's "preserving
    historical classification".
  - **No reactivation route.** A retired Topic comes back the way `confirm_proposed_topic` has
    always brought one back: a person names it, and `apply_tag` links and reactivates it, answered
    as a new Topic would be (a retired value is in no scheme, so a 409 would disclose it).
    *Corrected the same night, after the focused re-audit of `88a488d`: answered 200 instead when
    the document already holds a link to it, live or removed, which is kept or restored.* A retired
    Project or Process tag stays retired. *Declined:* a route that only reactivates, which nothing
    in FR-10 asks for.
- **The 409 rule's existence oracle, closed (the lead's review, the same night).** The rule as first
  built (`90ebc51`) left one, found in the lead's review of `4b5cf65`. Two roles suffice:
  1. An Employee holding `contribute_content` applies a Topic name to a document their role reads.
     It answers 201 whether or not a Topic of that name exists on Administrator-only material, as
     intended.
  2. They remove it. A person's link is deleted, so it answers 204 either way. *(Since the
     requirements re-audit of `5377e3a` the link is kept and marked removed; still 204.)*
  3. They apply the name again. A name nothing else carried was now an unlinked Tag, admitted as
     vocabulary and offered, so it answered 409. A name carried only by Administrator-only material
     was still linked and unreadable, not offered, so it answered 201. `tag_options` differed the
     same way after step 2.

  So the three steps told an Employee whether a restricted Topic name exists, which breaks invariant
  1. Deleting the only document carrying a tag does the same, but only a `manage_documents` holder
  can delete.
  - **The rule change (the lead's decisions).** The root cause: an unlinked tag was admitted while
    a tag linked only on unreadable material was not, and Topics are the only names a person can
    probe. `documents 0010` adds `Tags.grown`, additive and reversible. It is set on the Topic a
    person's `apply_tag` name form links and on the Topic `confirm_proposed_topic` links, whether
    created or fetched (restricted or inactive), and by nothing else. The `tag_id` form does not
    set it, because an offered tag is already readable or vocabulary. In `tag_scheme` a tag is in
    if every audience role reads a source carrying it, or if nothing links it and it is not grown.
    Project and Process tags are never grown, so they are unchanged, and a seeded, unlinked Topic is
    vocabulary. The empty-audience branch is unchanged, and so is `reject_tag`. A fetched Topic is
    marked as well as a created one: otherwise a retired, seeded, unlinked Topic a person names
    would come back as vocabulary after the removal, and answer 201, 204, 409 where a new name
    answers 201, 204, 201. *Superseded the same night, marked after the requirements re-audit of
    `5377e3a`: `824c536` admits a tag that is not grown whatever its links (the security review's
    bullet below), `c99857c` grows only a Topic a name creates or reactivates, and since the
    re-audit a person's removal is kept, so the sequence answers 201, 204, 409 in every variant.*
  - *Dated line, 10 November 2026 (night): narrowed the same night.* `11a610f` first took every
    unlinked Topic out of every scheme. That changed Objective 05's measured configuration, six
    seeded, unlinked Topics shown to the classifier, and FR-10's "established scheme" for anyone who
    seeds Topics, so the lead narrowed it the same night to the rule above. The configuration is now
    as measured.
  - **What follows.** A person naming a grown Topic that nothing links links it as it stands,
    answered 201, like any out-of-scheme Topic. `tag_options` and the classification prompt list a
    seeded, unlinked Topic as vocabulary, as they did before `11a610f`, and never list a grown one
    that nothing links. The residual in this note's `tag_options` bullet is closed for every Topic
    a person brought in by name. For a seeded tag of any dimension it stood, and not only by
    deleting the documents that carry it: an Employee removing its readable person links reached it
    too (the security review's finding 1, below). *Corrected the same night: this said "reachable
    only by deleting the documents".* The vocabulary rule below closes it.
  - **What this does not close.** A seeded tag whose only links are on restricted material is
    withheld from a narrower audience, so watching `tag_options` over time can show that restricted
    material has taken up a seeded value. That was so under this entry's rule from the start, for
    every dimension, and neither `11a610f` nor this rule changed it. *Corrected the same night: this
    said "An Employee cannot bring it about". The security review's finding 1, below, shows one
    could, by removing a seeded value's readable person links.* The vocabulary rule below closes it.
  - **Objective 05's runs met unlinked Topics, and this rule keeps them in.** Both recorded runs
    began with all six seeded Topic values (compliance, finance, people, safety, technology,
    workplace) unlinked:
    - the first after `seed_objective02_tags.py --scheme-only` created the fourteen values with no
      links (`corpus/objective-05/runs/2026-11-10/objective-05.md`, "before the run"; the script's
      `--scheme-only` mode exists for this database, D-106);
    - the informed re-run after the first run's 38 AI links were deleted (`rerun/rerun.md`).

    Under the rule as it then was, all six were in the scheme when each run began. `11a610f`'s rule
    would have kept all six out, because the run creates no link to a readable source before
    classifying (it links only values already in the scheme and proposes the rest), so a re-run
    under it on a scheme-only database would have proposed every Topic suggestion rather than
    linked it. Under this rule the six are seeded and not grown, so they are in the scheme exactly
    as when the runs began. A test runs `seed_objective02_tags.py --scheme-only` and checks that
    all of its Topics are in the scheme. The runs' starting state is shown from the seed script and
    the committed run records, not from the database.
- **The security review of `84b5771` (the same night): the vocabulary rule.** The review found the
  oracle's root cause still open in `tag_scheme`. Its vocabulary half read every `ContentTag`, links
  nobody in the document's audience can read included, so what a reader was offered moved when
  links on material they cannot read were made or destroyed. The lead checked findings 1 to 3
  against the code. The dispositions:
  - **1 (high): fixed.** An Employee holding `contribute_content` removed the readable person links
    of a seeded value: the D-74 seed's links are a person's, `reject_tag` deleted a person's link
    (*until the requirements re-audit of `5377e3a`, the last bullet of this note*), and there is no
    ownership check. The value then vanished from `tag_options` exactly when
    Administrator-only material still carried it. The name form's 201 against 409, and the
    `tag_id` form's 400 against 201, said the same. On the objective-02 manifest, `purchasing`,
    `onboarding`, `finance` and `people` have such carriers (D15, D16). This refutes "An Employee
    cannot bring it about", above, corrected in place.
  - **2 (medium): fixed.** An unlinked seeded value dropped out of every Employee's `tag_options`
    when Administrator-only material took it up, a held AI suggestion at upload included, and any
    reader saw it with a GET.
  - **3 (medium): fixed.** An Administrator removing the person links of a value only
    Administrator-only material carried, or deleting those documents, left it unlinked and not
    grown, so every Employee was offered it. That contradicted `classification.py`, `deletion.py`
    ("a tag left with no links is never offered to anyone") and the contract.
  - **The rule (the lead's decision).** `tag_scheme` admits a tag if every audience role reads a
    source carrying it, or if it is not grown, and no longer reads which tags have links at all.
    `grown` now means "not vocabulary": a tag that is not grown is in every scheme whatever its
    links, and a grown one only where every audience role reads a source carrying it, every link
    counting as before. Nothing a reader can see moves when links on material they cannot read are
    made or destroyed. One exception, found while building the rule, was closed the same night: the
    last item below.
  - **`documents 0011`** marks grown every Tag, of any dimension, with at least one link and no link
    on a source readable by every role. Documents and meetings both count; "readable by role r" is
    the source's `visible_to_roles` overlapping r's effective roles, as `_in_scope` reads it; and
    every link counts, held and removed ones included. That is exactly the set today's rule withholds
    from some audience, so nothing becomes visible anywhere that was not.
    - It is a RunPython whose reverse does nothing, with the role mapping frozen as literals and
      historical models only, as accounts 0007 and 0008 freeze their names.
    - It depends on `meetings 0002`, so a clean start now plans that migration before `documents
      0002`. Its operations are unchanged.
  - **The seed's linked mode** marks the same way after linking; on the objective-02 manifest that
    is `atlas` alone, carried only by D09 and D15. `--scheme-only` links nothing and marks nothing.
  - **Consequences.** For an audience role that scoping does not know, every grown tag is withheld,
    as `scoped_documents` fails closed, while vocabulary that is not grown is in: it names no
    source. Tests that model "a value only restricted material carries" now set `grown=True`, as
    the backfill and the seed do; a value on restricted material that is not grown is in, as
    vocabulary.
  - **Objective 05: a departure from the measured configuration.** Its scheme-only start is
    unchanged, fourteen unlinked values and none grown; what differs is during a run. Under the
    rule the runs used, a seeded value first linked only on material some audience role could not
    read dropped out of later documents' schemes. It happened once in each recorded run:
    - in the first run, the ninth document, D09 (Administrator-only), applied `atlas` before any
      other document carried it, so `atlas` was out of the schemes of the nine later Employee-
      visible documents, D10 to D14 and D17 to D20;
    - in the re-run, the sixteenth, D16 (Administrator-only), held `people` first, so `people` was
      out of D17 to D20's schemes.

    Under this rule both stay. The old rule's behaviour there was finding 2's leak, seen in the
    measurement itself: the scheme an Employee-visible document's prompt received, the same scheme
    its `tag_options` offers, changed because Administrator-only material had taken up a seeded
    value. This is shown from the runs' `classify.json` records, in their processing order, and the
    manifest's `visible_to_roles`, which `scripts/ingest_objective02.py` writes; not from the
    database. The recorded runs and verdicts stand as records of the old rule, and nothing re-runs
    them.
  - **4 (low): the throttle half done, on `fix/FR-10-tag-throttle`; the prompt cap deferred.** An
    unthrottled `POST /api/documents/{id}/tags`, and Topic growth reaching every classification
    prompt. The user decided the same night: a per-user throttle on that route, scope `tagging`, 30
    a minute (`TAGGING_THROTTLE_RATE`), recorded in D-79's note on tagging. Capping the prompt would
    change the classification input, so it is deferred, and one user can still create 30 Topics a
    minute. *Until that branch this read "4: open", and "A throttle is the user's question, which
    the lead will put."*
  - **5 (low): fixed in the following commit.** Reversing `documents 0009` kept removed AI links,
    which the 0008-era code shows as live tags again. 0009's reverse now deletes them, before it
    drops the column; live links are untouched. 0009 is edited in place rather than followed by a
    new migration. It is unpushed (CLAUDE.md §7 forbids editing a pushed migration's operations),
    its author applied it only to test databases, and the appended operation does nothing forwards,
    so a database that did apply it is in the state the edited migration reaches.
  - **6, accepted residual.** An Employee holding `contribute_content` can undo an Administrator's
    retirement: naming a retired Topic reactivates it (`_bring_into_use`). The oracle closure
    depends on that, because linking without reactivating would make `tag_options` differ between
    a retired name and a new one. Also, nothing records who removed a person's tag.
  - **7 (info): tested.** `tag_options`' guarantee needs EFFECTIVE_ROLES to be closed under
    generalisation. `apps/core/tests/test_constants.py` now asserts it.
  - **8 (info): fixed.** Topics confirmed before `documents 0010` read not grown. 0011 marks those
    that only restricted material carries; one a readable source carries is vocabulary, which
    every reader of that source could already see. Confirming a proposal of such a Topic's name
    made before it existed leaves it vocabulary (the last item below).
  - **9, accepted residual (integrity, not disclosure).** `normalise_tag_name` does no Unicode
    normalisation (NFC/NFKC) or casefolding, and keeps zero-width and bidi characters, so
    look-alike duplicate Topics get past FR-10's `409`. No `500` was found: DRF's `CharField`
    rejects NUL and lone surrogates, and `apply_tag` re-checks the length after normalising.
  - **10, accepted residual.** Races give rare `500`s and no corruption:
    - a link racing `retire_tag`'s delete fails its deferred foreign-key check at commit
      (`taxonomy.py` says so);
    - `_bring_into_use`'s save on a tag deleted in the meantime raises `DatabaseError`;
    - `Tag.objects.get` can miss after the offered check.

    Applies on one document are serialised by the document lock, and `get_or_create` absorbs the
    concurrent-create `IntegrityError`.
  - **11, accepted residual.** Timing:
    - The name form's first probe of a name does different database work: an insert plus an update
      for a new name, an update for an inactive one, neither for an already-grown one. That is one
      sample per name and sub-millisecond, and D-105 makes no timing claim.
    - The detail's cost grows with the total number of tag links, restricted ones included. That
      reveals volume only.
  - **Found while building the rule, not one of the review's findings: one exception, fixed the
    same night, two commits after the rule.** `confirm_proposed_topic` grew the Topic it fetched:
    `_bring_into_use` marked it whether it was created or fetched (the lead's oracle review), and
    that included an active vocabulary Topic.
    - No route could bring that about. A vocabulary Topic is in every scheme, so the machine links
      it rather than proposing it, and the name form answers `409` for it.
    - A proposal still pending from before its name became vocabulary could. Two ways make one:
      `seed_objective02_tags.py` creating the Topic after the proposal; or a person bringing the
      name in on another document before `documents 0010`, when 0011 then left it as vocabulary
      because a source every role reads carries it.
    - Confirmed on restricted material, the Topic was grown and left an audience's options once no
      source that whole audience reads carried it: at once in the first case, and in the second
      when its readable links went.
    - **The fix (the lead's decision):** `_bring_into_use` grows a Topic only when it creates it or
      reactivates it, and an active one keeps its value, so vocabulary stays vocabulary. The name
      form never fetches an active vocabulary Topic, since it answers `409` first, so only
      confirmation changed. A retired seeded Topic a person names is still grown, which 84b5771's
      three-sequence test covers.
    - The seed script's docstring says to run it before any document is classified, which is still
      good advice: a document classified first holds its seeded suggestions as proposals or
      discarded suggestions until a person acts or it is classified again.
- **The requirements re-audit of `5377e3a` (the same night): a person's removed link is kept too.**
  The re-audit's finding 3, partial. `reject_tag` deleted a person's link, so the next classify
  route, reprocess or `classify_documents` run that suggested the value linked it again, through
  `_link_tag`'s create branch, as `applied_by: "ai"`, and a Topic the person had typed was proposed
  again. That breaks FR-10's correction clause, "any value a user edits [is] retained and is not
  overwritten by later reprocessing" (UC-09 A3 step 3), and nothing tested or recorded it.
  - **The decision (the lead's, the re-audit's option (a)).** `reject_tag` keeps a person's link
    too, marked `removed`, exactly as it keeps an AI link. `_link_tag`, `removed_topics` and
    `_apply_link` already handled a removed row, so nothing else in the apply layer changed.
  - **The apply, remove, apply sequences** now answer 201, 204, 409 for a new name, a Topic only
    restricted material carries and a retired seeded Topic alike, and list the name in
    `tag_options` after the removal in every variant. The removed link still counts as a link, so
    the document itself carries the name, and the name form answers the 409 that names it. The
    answers are still identical, so the oracle stays closed. Each variant's Topic is its own row
    with a random id (`uuid4`), which says nothing about whether it existed before.
  - **Applying the tag again restores the link,** 200, by its id, as `_apply_link` restores a
    removed AI link.
  - **`DELETE /api/tags/{id}`** deactivates a tag whose only links are removed (200): they still
    reference it. It deletes only a tag nothing references.
  - **Links are now deleted only with their source,** a document (D-73) or a meeting. So removing a
    link never takes a tag out of anyone's options; a grown tag leaves an audience's options when
    the last source that audience reads carrying it is deleted, or the tag is retired (*"or the tag
    is retired" added the same night, after the focused re-audit of `88a488d`*).
  - **What the sequences no longer show.** Whether a Topic a name brings in is grown, created or
    reactivated, no longer shows in them, since the document carries the name either way. A route
    test holds it instead: a new name, or a retired seeded Topic, named on Administrator-only
    material stays out of the Employee's options.
  - **The contract** says a person's link is kept, and its 400 list for the name form now names a
    missing `dimension` too (`serializers.py`).

**Dated note, 10 November 2026 (night): Objective 02's bound re-timed with classification at upload,
on FLM. It is met.** This was the "owed before M8" item in this entry's note on the upload's cost,
and gap 9 of the requirements audit (D-119).
- **How:** `docs/measurement-runbook.md`, steps 1 to 7, at `749a689`, on a fresh database
  (`kmp_obj02_20261110classify`), with FLM v0.9.39, `check_flm.py` passing, and Waitress started
  with `--threads=24`.
- **The result:** every valid item was Indexed and found, every invalid item was refused with its
  documented error, and no document of twenty pages or fewer took more than 60 s. The slowest took
  24.5 s.
- **What classification added:** 10 to 28 s per document. There were 21 calls for 20 documents, of
  9.3 to 17.8 s each, and one second attempt after a reply that was not valid JSON. D04, 26 pages
  and outside the bound, took 61.3 s against 33.3 s, above this entry's estimate of 41 to 55 s.
- **Evidence:** `corpus/objective-02/runs/2026-11-10/ingestion-classify-flm/` (`results.json`,
  `results.md`, `retime.md`, and the run's own log lines).
- **At twenty pages, timed directly the same night** (the user's request), because the corpus has
  no document near the bound: its only multi-page PDF has 26 pages.
  - **The result:** five uploads of D04's first twenty pages took 43.5 to 51.6 s, each with one
    classification attempt (15.1 to 17.1 s), so all were within the bound.
  - **Not measured:** a retry adds one more attempt of about 9 to 17 s, which on that arithmetic
    takes some twenty-page uploads past 60 s. No retry happened at twenty pages, and the night saw
    one in 26 calls.
  - **Evidence:** `corpus/objective-02/runs/2026-11-10/ingestion-twenty-pages-flm/`.
- **Not shown:**
  - **The bound on `anthropic`.** D-114 chooses M8's host with its provider, and D-122 is about to
    make `anthropic` the default. If M8 runs there, the bound is re-timed on a Voyage-indexed
    database, and this FLM run does not stand in for it.

## D-106 · Objective 05's measurement: the reference set is frozen, the database is `kmp_obj0506_20261101`, and the confidence threshold is chosen on development documents by a rule fixed in advance

**Status:** Settled by the user · **Date:** 2026-11-08 · **Concerns:** Objective 05, FR-10, D-84,
D-88, D-93, `CLASSIFICATION_CONFIDENCE_THRESHOLD` · **Builds on:** D-104, D-105

**The reference set.** `corpus/objective-05/reference.json` gives each of the twenty indexed
documents its reference type, decided from the document's own text with the evidence quoted
(`reference.md`). The lead approved it as drafted on 8 November: Policy 7, Procedure 6, Report 6,
Meeting Paper 1; eight strong fits, eight fair, four weak and flagged (D07, a template, as Policy; D09,
a kickoff brief, as Meeting Paper; D13, a schedule, and D20, an announcement, as Report). The
alternatives for the weak fits are recorded in the file and were not taken. Department and the
Project, Process and Topic tags come from `corpus/objective-02/manifest.json`. **The set is frozen:**
a test set, never a tuning set (D-93's rule), and nothing is chosen against it after this date.

**What the verification counts.** The 75% type match is computed over all twenty suggested types,
provisional or not: a held suggestion is still "a suggested document type", and holding it is the
second clause, not an exemption from the first. Department is reported beside it and is not in the
75%. Tags are reported against the manifest for information, and for the provisional and scheme
behaviours the objective names.

**The database: `kmp_obj0506_20261101`,** created on 8 November from the 1 November dump
`3bf98403…6f59` (D-84's snapshot, the one D-88 restored the alpha from), after the checks ran first:
the snapshot folder's `snapshot.json` equal to the committed copy, the dump's SHA-256 equal to the
recorded one, the name not a protected one, and `createdb` refusing an existing name, so nothing could
be overwritten. **No media copy:** classification reads `ExtractedContent` and asks read chunks, so
no file is needed, and downloads are not measured. Migration v2 is applied to it with FR-10's pull
request. The fourteen tag values are seeded as the scheme only, `Tags` rows and no links, so the
documents arrive untagged and the scheme exists. Objective 06's writes go to the same database.
`kmp`, `kmp_demo_20261101` and `kmp_obj02_20261101` are untouched. The worktree's own `.env` names
`kmp_obj0506`, pytest's base name, which is never created.

**The confidence threshold is chosen on development documents, never on the twenty.** The
development set is `corpus/demo/D21_bicycle_end_of_trip_facilities.docx` and eleven one-page
documents written for the purpose under `corpus/objective-05/dev-documents/`, three per type,
none on a subject the twenty cover. Each is classified three times against the corpus's scheme (its
six departments and fourteen tag values). **The rule, fixed before the run:** the threshold that best
separates correct from wrong type assignments on the development set, the value maximising the
number of correct assignments at or above it plus wrong assignments below it; a tie goes to the
higher value; then a margin, the threshold is capped at the lowest confidence seen on a correct
assignment minus 0.05. If the model's confidences do not separate correct from wrong at all, that is
reported as the finding, and the threshold is set at the lowest confidence seen on a correct
assignment. The result replaces the PROVISIONAL 0.70 in `apps/core/constants.py`, with the sweep
recorded under `corpus/objective-05/runs/`.

**Before the run:** `scripts/check_flm.py` passes, FLM is v0.9.39 (D-83), and the record carries the
commit SHA, the dump hash and the FLM version, as every measurement does (D-84).

**Declined:** a fixed 0.70 declared untuned, which D-93's rule rules out for a tunable; the five
transcripts as the development set, which are all one kind.

**Not covered:** Objective 06, whose decisions follow.

**Dated note, 10 November 2026: the threshold is 0.95, and on gemma3:4b the type's confidence does
not separate right from wrong.** Two development sweeps ran, 12 documents three times each, on FLM
v0.9.39 with nothing read from or written to a database. The evidence is
`corpus/objective-05/runs/2026-11-09/dev-sweep/` and
`corpus/objective-05/runs/2026-11-10/dev-sweep-2/`. The twenty reference documents were not
consulted.

| | First sweep, `fb9e18a` | Second sweep, `b40dc0f` |
|---|---|---|
| type matches | 24 of 33 (72.7%) | **33 of 36 (91.7%)** |
| Meeting Paper suggested where expected | 0 of 9 | 6 of 9 |
| classifications that failed | 3 (D21, every attempt) | 0 |
| type confidence, right | 0.95 to 0.98 | 0.95 to 0.98 |
| type confidence, wrong | 0.95 to 0.96 | 0.95 |
| what the rule gives | 0.90 | **0.95** |

- **One prompt revision between the two, by the user's decision of 9 November, on development
  material only** (`b40dc0f`). The first sweep never suggested Meeting Paper. It also failed D21 on
  every attempt, because the model gave a tag an empty value and temperature 0 repeated it. The
  prompt now defines each type by its purpose, and it forbids an empty value, telling the model to
  leave the dimension out instead.
- **The rule's first branch, with the cap, on the first sweep.** The separating value was 0.98,
  which held all 9 wrong types and 7 of 24 right ones. The cap, at the lowest right confidence minus
  0.05, lowered it to 0.90, where nothing is held. The cap defeats any separation found at the top
  of the range; that is a flaw in how the rule was drafted. The user kept the rule as fixed, cap
  included, and applied it to the second sweep.
- **The rule's second branch on the second sweep.** No threshold beats applying everything: all
  three wrong types score 0.95, the same as the lowest right ones. So, as the rule fixed in advance
  says, the confidences do not separate correct from wrong, and the threshold is the lowest
  confidence seen on a correct assignment: **`CLASSIFICATION_CONFIDENCE_THRESHOLD = 0.95`**.
- **What 0.95 does:**
  - **No type is held.** Every type suggestion scored at least 0.95, so the type is always applied
    as an AI suggestion that a person can confirm or edit.
  - **Departments and tags are held.** On the second sweep, 24 of 36 department suggestions and 71
    of 84 tag suggestions fall below 0.95 and would be held for confirmation, against 12 and 13
    applied.
  - **So Objective 05's provisional clause is exercised on departments and tags, not on types.** The
    model's own confidence is close to a constant for the type, and that is recorded as a finding
    about gemma3:4b, not hidden by the value.
- **An FLM-configuration value** (D-113, D-114). The threshold was chosen on gemma3:4b's
  self-reported confidences, and a threshold chosen on one model's confidences does not carry over
  to another's. Before the `anthropic` provider is relied on, it is re-derived on the same
  development documents by this rule. Claude is not deterministic on this path (no temperature,
  D-115), so each development document is classified over repeated draws there, as D-103 measured
  FLM's band. `scripts/classification_dev_sweep.py` gates on FLM today, so that run needs a
  provider-aware gate, built when the re-derivation is.
- **If M8 runs on `anthropic`,** Objective 05 is verified again on that configuration, its
  type-match rate over repeated draws.
- **Every Objective 05 result records its configuration** from now on: the provider, the chat model
  and the embedding model. The two sweeps above ran on `flm`, `gemma3:4b`; classification calls no
  embedding model.
- **Not covered:** a confidence derived from anything but the model's own report.

**Dated note, 10 November 2026 (evening): Objective 05's verification. Clause 1 is not met on the FLM
configuration; clauses 2 and 3 are met.** The evidence is under `corpus/objective-05/runs/2026-11-10/`:
`objective-05.md` for the first run and `rerun/rerun.md` for the second.

| | First run, `aee5374` | Re-run, `caf9e22` |
|---|---|---|
| status | **the independent test** | informed by the first run |
| clause 1, types matching the frozen reference | **12 of 20 (60%)**, not met | **14 of 20 (70%)**, not met |
| clause 2, below-threshold assignments held | 48 of 48, met | 47 of 47, met |
| clause 3, out-of-scheme values | 3 departments and 6 Project or Process values discarded, 2 Topics proposed, none linked; met | 1 department and 6 Project or Process values discarded, 2 Topics proposed, none linked; met |

- **The first run is the frozen reference set's one independent use.** It ran on provider `flm`,
  `gemma3:4b`, FLM v0.9.39, `kmp_obj0506_20261101` (dump `3bf98403…6f59`), threshold 0.95, after
  `documents 0008` and `accounts 0006` were applied and the 14 tag values seeded without links. Its
  eight misses were three shapes the twelve development documents lacked: spreadsheet registers and
  trackers, a schedule, a booking-rules document and an announcement called Meeting Paper, and two
  guides given the reference's own alternative. Every miss scored 0.95.
- **The user's decision: one disclosed revision, then one re-run.** The type definitions were revised
  once and seven development documents of the failing shapes were added (`caf9e22`; the manifest says
  when and why). On the third development sweep the first twelve stayed at 35 of 35 and the seven new
  ones matched 7 of 21: the register and the guide were fixed, while a roster, an announcement and a
  rules document whose title mentions meetings were still called Meeting Paper. Type confidences
  still did not separate, so the threshold stayed 0.95. The first run's 20 analysis rows and 38 AI
  tag links were deleted, after their counts were checked, and the twenty were classified again.
- **The re-run gained two:** D03, D12 and D17 were fixed and D04 was lost. **It is not an independent
  test:** the revision was made because of the first run, so the frozen twenty no longer
  independently test classification, as D-101's note said of the thirty. The 60% stands as the
  independent figure.
- **For information only, not the rule:** counting the reference's recorded alternatives would give
  14 of 20 on the first run and 16 of 20 on the re-run. The frozen rule counts the reference column.
- **No further revision is made** (the user's decision: one). What remains is recorded rather than
  fixed: on gemma3:4b the type's confidence carries almost no information, and Meeting Paper attracts
  documents that mention meetings, schedules or events whatever the prompt says. Whether Claude does
  better is unmeasured; it would be measured as its own configuration, over repeated draws (this
  entry's note on the FLM configuration).

**Dated note, 10 November 2026 (night): the revision is a departure from D-93, and is named as
one.** The reference set's status line says "never tuned against (D-93)". Since `caf9e22` that is not
true of the type definitions: they were revised once because of the first run's misses, and they
name the misses' shapes (register, inventory, schedule, roster, tracker, announcement). D-93 settles
that the frozen sets are not tuning sets, so this was a departure from it. It was made once, by the
user's decision, and disclosed, with the first run kept as the independent figure. The file is
frozen and is not edited; this note supersedes its line. The prompt now shipped has no independent
accuracy figure (the requirements audit, D-119, its finding 8).

**Dated note, 10 November 2026: claude-haiku-5-5's own value is 0.72 (D-122).** D-106's rule ran on
the development documents through the shipped `classify_document` on Haiku 5.5: 19 documents, three
times each (`corpus/objective-05/runs/2026-11-10/dev-sweep-haiku/`).

- **Haiku typed all 57 right,** so nothing beat applying everything. The rule's fallback applies: the
  lowest confidence seen on a correct assignment, **0.72**.
- **The threshold is now per classifying model** (`CLASSIFICATION_CONFIDENCE_THRESHOLD_BY_MODEL`),
  keyed by the model the classification carries. gemma3:4b keeps 0.95.
- **The development set had grown to 19 documents** (caf9e22) since 0.95 was chosen on twelve.

## D-107 · Schema v2 for FR-19: `KnowledgeGap`, its items and cycles, the `review_knowledge_gaps` permission, the aggregation cycle and its routes

**Status:** Settled by the user · **Date:** 2026-11-08 · **Concerns:** FR-19, FR-14 (D-69), invariants 1
and 4, D-13, D-14, D-66, D-99, docs/schema-v1.md §2 · **Stage:** Objective 06, due 13 November 2026

**The tables** (`retrieval 0004`, additive and reversible; placed in `apps/retrieval` because the logs
they aggregate live there, D-13):

- **`KnowledgeGap`**, the proposal's table: `gap_id`, `subject`, `occurrence_count`, `status` (`Open` or
  `Addressed`, a fixed vocabulary in `apps/core/constants.py`), `last_seen_at`; plus `first_seen_at`,
  and `embedding` with `embedding_model` for D-109's grouping. The embedding columns follow
  `ContentChunks`' rule (risk R10): a gap is a join candidate only for an item embedded by the same
  model, and a provider switch starts new gaps rather than comparing vectors that cannot be compared.
  `subject` is the first member's wording, verbatim: no model writes it, so no model-generated text
  enters the record, and the Administrator reads what was actually asked.
- **`KnowledgeGapItem`**: `gap`, and exactly one of `query` (a `QueryLog` row) or `search` (a
  `SearchLog` row), each unique, with `added_at`. A log row is therefore counted once across every
  cycle, and `occurrence_count` is a column the proposal names that a test can check against a count
  of items.
- **`KnowledgeGapCycle`**: `started_at`, `finished_at`, `triggered_by` (null for the command),
  `queries_considered`, `searches_considered`, `entries_created`, `entries_updated`. It is the
  evidence for "within one aggregation cycle", and it bounds the next cycle's window. **No count of
  rows left out is stored or returned anywhere.**

**FR-19 reads `QueryLog` and `SearchLogs` and writes neither.** Its CRUD line says Read, and the
membership table is how a row is remembered without a column on it.

**The cycle** (`apps/retrieval/gaps.py::run_cycle`, one transaction):

1. The window is `[previous cycle's started_at − CYCLE_GRACE_SECONDS, this cycle's started_at)`,
   over `QueryLog.answered_at` where `answered = False` and over `SearchLog.searched_at` where
   `result_count = 0`; the first cycle has no lower bound. The grace of 60 seconds covers a row whose
   timestamp was set before the previous cycle started and committed after it read; re-scanning is
   harmless, because a row already a member is skipped by the unique constraint and a row left out on
   permission grounds is left out again by the same rule. Windows timestamps tick at about 15.6 ms,
   so no rule here depends on two timestamps differing.
2. Each row is tested by D-108's rule. A row the asker's permissions explain is left out, and nothing
   records that it was.
3. Each remaining row is embedded (one batched call per cycle) and grouped by D-109's rule into an
   Open gap or a new one; `occurrence_count` and `last_seen_at` move with it.
4. The cycle row is written last, with its counts.

**Trigger and surface.** "On a scheduled basis" is `manage.py aggregate_knowledge_gaps`, which a
scheduler runs (Task Scheduler on the laptop); `POST /api/knowledge-gaps/cycles` runs one cycle
synchronously for the demonstration and answers 201 with the cycle row. `GET /api/knowledge-gaps`
lists entries, Open first by `occurrence_count` then `last_seen_at`, then Addressed, each as
`{gap_id, subject, occurrence_count, status, first_seen_at, last_seen_at}`. `PATCH
/api/knowledge-gaps/{id}` with `{"status": "Addressed"}` or `"Open"` is the proposal's "mark an entry
as addressed"; 404 for an unknown id. **No asker, no role and no reason appears in any payload.**

**The permission is a code, `review_knowledge_gaps`,** seeded for Administrator by `accounts 0007`,
D-99's pattern, and checked on every one of the four routes: 401 without a session, 403 for a role
that lacks it (invariant 4). *Declined:* testing the role name directly, which every other
Administrator-only route does not do.

**FR-14's panel** (closes D-69): the dashboard payload gains `knowledge_gaps`, `{open_count, top}`
with up to `DASHBOARD_RECENT_ITEMS` Open entries, **present only for a caller whose role holds
`review_knowledge_gaps` and absent otherwise**, so an Employee's payload keeps today's shape. The
dashboard's date and department filters do not narrow it: a gap has no department and its dates are
its own.

**Not covered:** FR-18, which does not exist; a gap's department or asker breakdown ("asked repeatedly
across departments" is visible only as the count); deleting a gap.

**Build notes, 10 November 2026** (the django-backend agent's choices where this entry was silent or,
in the first case, was overtaken; accepted as written):

- **One `embed_question` call per item, not step 3's "one batched call per cycle".** D-108 needs a
  question's vector before it can decide whether the row stays, and says it is embedded as retrieval
  embeds it; and D-113's Voyage work encodes queries inside `embed_question`, so FR-19 follows it only
  by calling it (D-109's note of 10 November). A source-level test holds this.
- **What the cycle counts mean.** `queries_considered` and `searches_considered` count the rows added
  to the log, the survivors, not the rows read: the rows read minus the rows added would be exactly
  the number this entry says is stored nowhere. `entries_updated` counts entries that existed before
  the cycle and gained a member; one created and joined in the same cycle counts once, as created.
- **The centroid** stores the members' mean, updated as `(n*mean + v)/(n+1)`. Its direction is D-109's
  normalised mean and cosine ignores length, so every join decision is the same; normalising would
  lose the length the exact update needs.
- **On a join,** `last_seen_at` is the later and `first_seen_at` the earlier of the entry's and the
  item's, because the grace window can deliver a row older than an entry's newest member.
- **Cycles are serialised** by a PostgreSQL advisory transaction lock, and `started_at` is taken after
  it is acquired; two concurrent cycles would otherwise meet the one-to-one constraint as a 500. The
  cycle locks the Open entries it may join, and PATCH locks its own row, so a status change made
  during a cycle waits for it.
- **An item's foreign keys to `QueryLog` and `SearchLogs` are PROTECT,** so `occurrence_count` cannot
  fall behind its items.
- **The cycle's 503 carries its own text,** not the ask's, and is logged on the attempts logger.
- **A role missing from `EFFECTIVE_ROLES`** has every one of its rows left out: the exclusion fails
  closed.
- **`search_total(role_name=...)`** departs from `search.py`'s user-only convention, because it has no
  user and writes no row; the module says so.
- **Existing tests amended because of the new code and routes:** the two whole-payload dashboard tests
  expect `knowledge_gaps` for the Administrator only; the seed tests follow accounts 0007; and
  `test_rbac`'s new check that each permissioned route checks its own code found
  `document-reprocess` missing from its list of permissioned routes, a gap older than this work,
  now added.
- **`POST /api/knowledge-gaps/cycles` is not throttled** (decided on 10 November, when the merge with
  main raised it). It is Administrator-only; the advisory lock already runs one cycle at a time; and a
  cycle considers only rows logged since the previous one, plus the grace, so pressing it again costs
  almost nothing. D-79's budgets exist to stop one user's asks and ingestions monopolising the NPU,
  and a cycle adds no NPU work beyond embedding rows already logged.

**Dated note, 10 November 2026 (night): the security review of FR-19 at `45d5c25`.** One
`security-reviewer` run, read only, taking an authenticated Employee and an Administrator who reads
the log. It found nothing critical or high. An Employee reaches none of the three routes, nor the
dashboard key, by any method or path variant. No payload carries an asker, a role, a reason or a
count of rows left out. The exclusion discloses nothing to anyone who could not already read the
content, because only the Administrator reads the log and D-66 lets them read every chunk.

| Finding | Severity | What was done |
|---|---|---|
| M1. Keyword search bounds a term from below only, and the cycle embedded a kept zero-result term whole. A provider error on one very long term would roll that cycle back, and every later cycle would meet the same row and fail the same way | medium | **Fixed.** A kept term is cut to `MAXIMUM_QUESTION_LENGTH` (500 characters) before it is embedded and stored as a subject; the recount still uses the whole term. A test runs a cycle over a term of about 36,000 characters, then a second cycle |
| L1. A zero-result search the recount leaves out is never embedded, so whether restricted content contains a term changes how much NPU work a cycle does: a timing signal on a resource every user shares | low | Open, with L2 |
| L2. Search is unthrottled, so any Employee can repeat a term to put chosen text at the top of the Administrator's list and dashboard. It renders as text, never HTML | low | Open, with L1 |
| L3. The exclusion discloses nothing only while every holder of `review_knowledge_gaps` reads what the Administrator reads, and nothing enforced that | low, latent | **Tested.** Every role holding the code must have the Administrator's effective roles |
| I1. `first_seen_at` and `last_seen_at` are exact to the microsecond | informational | Accepted. No route gives an Administrator another user's activity to match them against, and a verbatim subject can identify its author anyway (accepted above) |
| I2. Zero-result search terms now reach the AI provider, which keyword search never did | informational | **Recorded** in `docs/ai-provider.md`, where `input_type`'s callers are listed |
| I3. A provider 4xx made `POST /api/knowledge-gaps/cycles` answer 500 | informational | **Closed by the merge with `main`:** under D-118 a 4xx is `ProviderRefused`, a `ProviderUnavailable`, so the route answers its 503 notice |
| I4. `search_total`'s docstring said it builds no snippets | informational | **Corrected** |
| I5. D-110's note still said the exclusion admits at `RELEVANCE_THRESHOLD` | informational | **Corrected** there, marked as a correction |
| I6. `POST /api/knowledge-gaps/cycles` waits on the advisory lock with no timeout | informational | Accepted: the route is the Administrator's alone |

- **L1 and L2 share one fix, and it is not FR-19's:** a throttle on `GET /api/search` and an upper
  bound on a term, both on FR-12's route. They are left to the user rather than changed here.
- **Also not FR-19's:** the embedding call sets no timeout of its own, so the client's default of
  600 seconds applies to every embedding in the system. M1's cut removes the one input only the
  cycle could send; a provider that hangs affects asks and ingestion the same way.

**Dated note, 10 November 2026 (night): the schedule is daily, and it is in the repository.** The
requirements audit of that night (D-119, its finding 11) found "on a scheduled basis" unmet as built:
"Trigger and surface" above names "Task Scheduler on the laptop" but no script, interval or set-up
step, and D-114 has since let M8 run on any device. The user's decision: a daily run.

- **`scripts/register_knowledge_gap_schedule.ps1`** registers `manage.py aggregate_knowledge_gaps`
  in Windows Task Scheduler for the current user, daily at 02:00 by default, starting a missed run
  when the machine is next on and stopping a run after two hours. No password is asked for or
  stored, so the task runs while that user is logged on. `docs/alpha-deployment.md` section 9 gives
  the steps and a crontab line for a Linux host.
- **Registering it on the host is the user's step,** since it changes that machine's settings.
- **A run that cannot reach the provider changes nothing,** and the next takes the rows it missed,
  because each cycle's window starts at the last committed cycle.
- **This supersedes "Task Scheduler on the laptop" above.**
- **Tests** pin the script's contract: it runs the command from the checkout's venv, daily, and
  takes no password; the runbook names it.

**Dated note, 10 November 2026 (night): L1 and L2 are taken up** by a `search` throttle and an upper
bound on a search term, on FR-12's route (D-79's note of the same night). Each is reduced, not
removed: that note says what remains.

## D-108 · FR-19's permission exclusion: the top-ranked passage over the Administrator's scope decides, and a zero-result search is recounted as the Administrator

**Status:** Settled by the user · **Date:** 2026-11-08 · **Concerns:** FR-19's Validation clause,
invariant 1, FR-11, D-37, D-66, D-102 · **Builds on:** D-107

**The clause.** "Queries that returned nothing because the user lacked access are excluded, since
these represent a permission boundary rather than a documentation gap, and including them would both
distort the list and imply the existence of restricted content." Objective 06 tests it from both
sides: every genuinely unanswerable query must appear, and "no query returning nothing on permission
grounds may appear in the log at all".

**The constraint.** Deciding that a no-answer was caused by scope means checking the question against
content the asker cannot see. That check runs only inside the Administrator-only cycle (D-107), on
the server, after the fact. It never runs in the asker's request, so no reply, count, partial-match
offer or timing differs from today for any user (invariant 1), and nothing is written that says why a
row was left out.

**The rule for a question** (an unanswered `QueryLog` row, FR-13 turns included):

1. The asker's role is read from the user row now. (A role changed since the ask is a known
   limitation: the log holds no role of its own, and FR-19 may not write one.)
2. The question is embedded with the query prefix, as retrieval embeds it. A conversation turn is
   embedded on its own wording, not composed with its earlier turns as the pipeline did (D-42); the
   simpler form was chosen for the five days, and the row is aggregated either way.
3. It is ranked over `candidate_chunks(role_name="Administrator", ...)`: the whole corpus, through the
   one scoping helper, with no new unscoped query shape. D-66 makes the Administrator's scope every
   chunk, so this is "what an Administrator would have found".
4. The ranked list is admitted at `RELEVANCE_THRESHOLD`. If nothing is admitted, nobody could have
   been answered: the row is a gap. If the **top admitted passage** is one the asker's role cannot
   read (its `visible_to_roles` has no overlap with the asker's effective roles), the row is
   permission-affected and left out. Otherwise the best match was readable by the asker, so their
   no-answer was not a permission matter: the row is a gap.

**The rule for a search** (a `SearchLog` row with `result_count` 0): the same keyword search is
counted again as the Administrator, through a non-logging total in `apps/retrieval/search.py`. More
than zero means the asker's role withheld it; zero means nobody could find it, and it is a gap.
Keyword matching is deterministic, so this side has no error.

**Why rank one, and not the alternatives.** *Any withheld passage above the threshold* would leave out
more genuine gaps: D-102 found that in users' wording unrelated passages often clear 0.30. *A margin
between the best withheld and the best readable score* is the most discriminating rule, costs one more
tuned constant, and is the fallback. *Re-running generation as the Administrator* is the most literal
reading, but it spends one model call per logged row per cycle and lets a model that over-answers
(D-102's 8 November note) decide the exclusion.

**The known risk, and how it is checked before the frozen run.** A genuine gap whose best spurious
match over the whole corpus happens to be an Administrator-only chunk is wrongly left out. The rule is
checked first on development material, `corpus/objective-02/dev-set-v2.json`'s no-answer and scoped
questions and `dev-set.json`'s, asked as the Employee: scoped questions should be left out and
no-answer questions kept. If that check fails, the margin rule is chosen on the same material before
the thirty are run. The thirty are never used to choose.

**What the Administrator can and cannot learn.** The list shows questions Employees asked, verbatim,
without who asked them; that is FR-19's design and the proposal's example. An Administrator already
reads every document (D-66), so a subject in the list discloses no content. An absent row is
indistinguishable from a question nobody asked.

**Not covered:** FR-13 composition in the cycle; a role recorded at ask time; re-evaluating rows when
a document's visibility later changes.

**Dated note, 10 November 2026: the development check passes, so the rank-one rule stands and no margin
is chosen.** `scripts/exclusion_dev_check.py` called the cycle's own decision
(`_question_explained_by_permissions`) with the cycle's Administrator scope and `embed_question`, on
commit `3ee2d43`, FLM v0.9.39 (`embed-gemma`), `kmp_obj0506_20261101`, `RELEVANCE_THRESHOLD` 0.30,
every question asked as the Employee; nothing was written. The evidence is
`corpus/objective-06/runs/2026-11-10/exclusion-dev-check/`.

- **Scoped questions left out: 6 of 6** (u30, u31, u32, d11, d21, d22).
- **No-answer questions kept: 9 of 9** (u33 to u37, d24 to d27), with top passages from 0.30 to 0.49,
  every one readable by the Employee.
- **Ordinary questions, for information: 46 of 50 kept.** Three of the four left out are right: u28,
  u29 and d23 have Administrator-only sources (D15, T02, D09), so for an Employee they are permission
  boundaries. **One is the known risk, observed:** u07, "I clicked a dodgy link in an email, what
  now?", whose answer is in D02, which the Employee can read, ranks the Administrator-only phishing
  debrief (T05) first at 0.3485. Had an Employee's u07 gone unanswered, it would have been left out
  of the log. That is a retrieval miss rather than a documentation gap, since the answer exists where
  the asker can read it, so the cost is small, but it is a real false exclusion and it is recorded
  as one.
- **An FLM-configuration result,** like D-109's and D-110's values: repeated on the new configuration
  before the thirty are run there (D-110's note).

**Dated note, 10 November 2026 (evening): the rule now decides on the top-ranked passage even below
the threshold.** The user's decision, after Objective 06's first cycle on the frozen thirty (D-110's
note) kept P02: its answer exists only in the Administrator-only Atlas brief, which scored 0.2977 to
0.2983 across the Administrator's scope, under `RELEVANCE_THRESHOLD` and inside D-40's drift, and
step 4 above kept every row with nothing admitted.

- **The rule from `333be14`:** rank the question over the Administrator's scope and take the
  top-ranked passage, whether or not it clears the threshold. If its `visible_to_roles` has no
  overlap with the asker's effective roles, the best evidence for an answer is where the asker cannot
  read it, and the row is left out. If the asker may read it, the row is a gap. If no passage of the
  question's embedding model exists, the row is a gap.
- **Development check repeated on the new rule** (`corpus/objective-06/runs/2026-11-10/
  exclusion-dev-check-2/`): scoped questions left out 6 of 6, no-answer questions kept 9 of 9,
  ordinary questions kept 46 of 50, exactly as under the old rule. Both rules score 15 of 15, so the
  development set did not choose between them: the frozen result did, and this is disclosed as such.
- **The known cost:** a genuine gap whose weak best match happens to be a restricted passage is left
  out. Neither the development questions nor the frozen thirty's unanswerable asks have that shape
  (every one's top passage is readable), so its size is unmeasured.
- **Tests:** two below-threshold cases replace the old "nothing above the threshold is kept" test;
  the restricted one failed under a break restoring the old condition.

**Dated note, 10 November 2026 (night): two additions, from the requirements audit and the security
review of that night.**

- **The second development check's table shows the top admitted passage, not the top-ranked one.**
  Its score and readable columns came from the passages that cleared `RELEVANCE_THRESHOLD`, as the
  script then stood, so a question the new rule decided below the threshold shows `None` in them.
  Its outcome column calls the cycle's own function, so the 15 of 15 holds. The script now reports
  the top-ranked passage.
- **This entry's argument that the log discloses nothing rests on its readers reading every chunk**
  (D-66). A test now requires every role holding `review_knowledge_gaps` to have the
  Administrator's effective roles (D-107's note of the same night, L3).

**Dated note, 11 November 2026: on voyage-4 the development check fails under rank-one, and the user
chose threshold-first for that model (D-126).**

- **The check was not repeated before the thirty ran on `anthropic`,** as this entry's note of 10
  November and D-110's note on the FLM configuration ask. That was an oversight, owned in #86's
  write-up. Run afterwards, on commit `9527cd7` and `kmp_obj0506_anthropic_20261110`
  (`corpus/objective-06/runs/2026-11-10-anthropic/exclusion-dev-check-voyage/`), it fails:
  - scoped questions left out: u30, u31, u32, d11, d21, d22, as they should be;
  - no-answer questions kept: u33, u34, u35, u37, d24, d25, d26;
  - **no-answer questions left out: u36 and d27.** Their top-ranked passages score 0.230 and 0.238,
    under voyage-4's 0.2687, and are Administrator-only.
- **That is the evening note's "known cost", now observed.** On embed-gemma no development or frozen
  question had the shape. On voyage-4 u36, d27 and the thirty's U01 have it.
- **The fallback was not followed as written.** This entry says the margin rule is chosen on the
  development material when the check fails, and that the thirty are never used to choose. On
  voyage-4 the margin rule and step 4's threshold-first both pass the check, and the user chose
  threshold-first, informed by the thirty. D-126 records the choice and both departures.
- **Rank-one is still the rule for every model `GAP_EXCLUSION_RULE_BY_MODEL` does not list,**
  embed-gemma included. No FLM result in this entry changes.

## D-109 · Gaps are grouped by cosine similarity to an Open entry's centroid, and `GAP_GROUPING_THRESHOLD` is chosen on a development paraphrase set

**Status:** Settled by the user · **Date:** 2026-11-08 · **Concerns:** FR-19's Business logic clause,
Objective 06's second clause, D-38, D-40, D-93 · **Builds on:** D-107, D-108

**The clause.** "Entries are grouped by similarity rather than exact wording, so that differently
phrased questions about one subject aggregate into a single entry", tested as "differently worded
questions on a single subject must group into one entry with an accurate occurrence count".

**The rule.** Each item that survives D-108, a question or a search term, is embedded with
`embed-gemma`'s query prefix (D-38), the same way a question is embedded for retrieval. In timestamp
order, each item is compared with every **Open** gap whose `embedding_model` matches: it joins the
nearest one whose centroid cosine is at least `GAP_GROUPING_THRESHOLD`, and that gap's centroid
becomes the normalised mean of its members' vectors, its count rises by one and `last_seen_at` moves;
otherwise it starts a new gap with its own wording as the subject and its vector as the centroid.
An Addressed gap is not a candidate: a subject that recurs after being addressed opens a new entry,
which is what an Administrator needs to see.

**Why a centroid and not single linkage.** Joining on any one member chains: over several cycles two
unrelated subjects can meet through an intermediate wording. A centroid moves slowly and keeps a gap
about one thing. *Exact normalised text* was declined because it fails the clause by construction.

**How the threshold is chosen: on `corpus/objective-06/dev-paraphrases.json`, never on the thirty.**
Twelve subjects the corpus can answer, each in two differently phrased questions and one search-style
term; the within-subject pairs are the positives and every cross-subject pair is a negative, with six
hard pairs (same document or shared vocabulary) reported on their own. If the lowest positive
similarity exceeds the highest negative, the threshold is their midpoint; otherwise the value with the
best pairwise F1. The gap between the two, against D-40's drift of 0.003, is reported either way. The
set shares no subject with the thirty seeded queries, so the thirty remain a test set (D-93). The
result replaces the PROVISIONAL value in `apps/core/constants.py`, with the sweep under
`corpus/objective-06/runs/`.

**Known limits.** Greedy order dependence: an item that arrives before a gap it would better fit
starts its own. A search term of two words and a full question on one subject may sit further apart
than two questions do; the development set includes a search term in every subject so the threshold
accounts for it.

**Not covered:** merging or splitting gaps by hand; a model-written subject; re-grouping existing
entries after the threshold changes.

**Dated note, 9 November 2026: the sweep ran, and `GAP_GROUPING_THRESHOLD` is 0.5256.** Commit
`4a1ed3d`, FLM v0.9.39, `embed-gemma` with the query prefix, 36 items, 36 within-subject and 594
cross-subject pairs; nothing read from or written to a database. The evidence is
`corpus/objective-06/runs/2026-11-09/grouping-sweep/`.

- **Pairwise similarities do not separate.** The lowest within-subject pair is 0.5322 ("For how many
  years must finance records be retained?" / "When can old accounting paperwork be destroyed?"); the
  highest cross-subject pair is 0.5876 ("password length" / "password reset window"), one of the
  six hard pairs. A second hard pair, the two D04 subjects, reaches 0.5788. So the rule's second
  branch applies: the best pairwise F1, **0.5256**.
- **Centroid grouping, simulated at 0.5256 in the set's order,** forms exactly 12 entries of 3 from
  the 36 items, none mixing subjects. The centroid does better than any single pairwise cut, because
  a search term and a question on one subject both move towards the subject's mean.
- **The margin is thin:** the lowest within-subject pair is 0.0066 above the threshold, about twice
  D-40's drift. Short search terms that share a word across subjects ("password …") are the
  near-miss case. Re-measure with the corpus, the embedding model or the prefix.

**Dated note, 10 November 2026: an FLM-configuration value, and what a provider switch does to the
log.** D-113 funds the `anthropic` provider (Claude with Voyage embeddings) and leaves the default to
measurement.

- **0.5256 is an `embed-gemma` cosine,** 0.0066 above the lowest within-subject pair. Voyage's
  similarities are distributed differently, so before `anthropic` is relied on, the value is
  re-derived on the same development paraphrase set by this rule, as D-113 requires for FR-12's
  values. `scripts/grouping_dev_sweep.py` records the provider, the chat model and the embedding model
  with its result from now on.
- **Matching on `embedding_model` (R10) makes a switch safe but visible.** Open gaps written under
  `embed-gemma` are never candidates for a Voyage vector, so a subject that recurs after a switch opens
  a second entry beside the first. Two entries is the safe failure; vectors from two models are never
  compared. An Administrator can mark the older entry addressed.
- **FR-19 embeds only through `apps.retrieval.query_embedding`,** the one query-embedding path, and
  never applies a query prefix itself, so a provider-specific encoding added there (Voyage's input type
  in place of `embed-gemma`'s prefix) reaches the cycle without a change in `apps/retrieval/gaps.py`.
  A test holds this.

**Dated note, 10 November 2026: voyage-4's own value is 0.5054 (D-122).** This rule, run on the same
paraphrase set with Voyage's query embeddings (`corpus/objective-06/runs/2026-11-10/grouping-sweep-voyage/`):

- **The pairs again do not separate.** The lowest within-subject pair is 0.5157 and the highest
  cross-subject pair 0.5297, the same password pair. So the best pairwise F1 gives **0.5054**.
- **Centroid grouping at 0.5054** forms 12 entries of 3, none mixed.
- **The margin is wider than FLM's:** 0.0103, about twenty times Voyage's re-embedding jitter
  (0.00047).
- **The threshold is now per embedding model** (`GAP_GROUPING_THRESHOLD_BY_MODEL`, read through
  `gaps.grouping_threshold`). embed-gemma keeps 0.5256.

## D-110 · Objective 06's thirty are frozen, with the unanswerable asks screened on retrieval scores; FR-12's decline weakness stays open

**Status:** Settled by the user · **Date:** 2026-11-09 · **Concerns:** Objective 06, FR-12, FR-19,
D-93, D-102, D-107 to D-109 · **Evidence:** `corpus/objective-06/runs/2026-11-08/pre-measurement/`,
`corpus/objective-06/runs/2026-11-09/screening.md`

**The risk the brief named, measured.** A question that FR-12 answers wrongly is logged as answered and
never reaches the gap log, so Objective 06's first clause ("every genuinely unanswerable query … must
appear in the log within one aggregation cycle") can fail for FR-12's reason alone. The pre-measurement
ran the draft's 8 unanswerable and 6 permission-only asks through the shipped pipeline twice, at
`711fcda`, with nothing written: **2 of 8 unanswerable asks reached a no-answer**, the other six were
answered from readable material scoring 0.32 to 0.42 with real in-scope citations (a salary question
cited the onboarding checklist). 4 of 6 permission-only asks reached path A. The two runs agreed on every
question; a third was cut off by the session ending.

**The user's decision: screen the ask wordings on retrieval scores, then freeze.**

- **Method.** Candidate wordings for the same four genuinely unanswerable subjects (salary review,
  corporate card, christmas shutdown, jury duty), each scored by `citation_harness.py --scores-only`:
  embed and rank over the asking role's scope, no generation. Kept: per subject, the two
  lowest-scoring wordings with a top in-scope score **at most 0.25**, one per role where the scores
  allow. The floor is 0.25, not 0.28: embeddings are deterministic on FLM v0.9.39, but a re-chunk or a
  corpus edit moves scores, and 0.05 of headroom under `RELEVANCE_THRESHOLD` (0.30) costs nothing
  today.
- **Three rounds,** 53 wordings in all. Round 1 (24) gave four; round 2 (17) two more; round 3 (12),
  approved for the two subjects still short with a replacement subject as the fallback, completed the
  eight.
- **The kept eight and their scores:** U01 0.2125 (Employee), U02 0.2173 (Administrator), U04 0.2413
  (Employee), U05 0.2447 (Administrator), U07 0.1913 (Employee), U08 0.2304 (Administrator), U10
  0.2421 (Employee), U11 0.2387 (Administrator). Wordings and nearest items are in `screening.md`
  and in `queries.json`'s `screened_top_score`.
- **Unchanged from the lead's approval of 8 November:** the ten answerable queries (each ask clears
  0.30 with its expected source ranked first), the four zero-result search terms (no chunk contains
  them), and the eight permission-only queries, which were not screened.
- **Frozen:** `corpus/objective-06/queries.json`, SHA-256
  `e78314b71b0096b95640939374b803d19e05f3f55e5fca273637f414c66e34b7`. Nothing is tuned against it
  from here (D-93).

**What this is, and what it is not.**

- **A verification choice, not a fix.** Objective 06 then tests FR-19's aggregation, exclusion and
  grouping on queries that reach a no-answer on the shipped build. It does not show that FR-12 declines
  the questions it should.
- **FR-12's decline weakness stays an open finding** (D-102's 8 November note; the item 10 audit ruled
  it carriable, not an FR breach). The screening makes the cause visible: a wording that shares the
  corpus's vocabulary pulls a readable passage over 0.30 and generation answers from it. **In real use
  the gap log will under-capture unanswerable questions that sit near the corpus's subject matter**
  until generation declines reliably.
- **The acceptance test for any future decline fix** is an unscreened re-run of the draft's original
  eight wordings (`pre-measurement-asks.json`) and of these thirty. The thirty stay frozen either way.

**Not covered:** the permission-only asks P04 and P07, answered from readable material in the
pre-measurement, which therefore do not exercise the exclusion; the exclusion is exercised by P01,
P02, P06, P08, the two permission-only searches and the database's five pre-existing Employee searches
for Administrator-only phrases.

**Dated note, 10 November 2026: the screening holds for the FLM configuration only** (D-113, D-114).

- **The path-A guarantee is an `embed-gemma` fact.** The kept eight scored at most 0.25 on
  `embed-gemma`, under `RELEVANCE_THRESHOLD` 0.30. Neither number carries over to Voyage and a
  re-derived threshold. The thirty stay frozen, so on `anthropic` Objective 06's first clause becomes
  an unscreened test, which is what this entry already names as the acceptance test for a decline fix.
- **D-108's exclusion depends on the active provider's embeddings,** because it decides on the
  top-ranked passage over the Administrator's scope. Its development check (D-108's known-risk
  paragraph) is repeated on the new configuration before the thirty are run there. *(Corrected the
  same night: as first written this bullet said the exclusion admits at `RELEVANCE_THRESHOLD`, which
  stopped being true at `333be14`, D-108's evening note.)*
- **If M8 runs on `anthropic`,** Objective 06 is verified again on that configuration. Generation on
  Claude is not deterministic (no temperature, D-115), so the seeding is repeated and the outcome
  reported per draw, as D-103 measured FLM's band.
- **Every Objective 06 result records its configuration:** the provider, the chat model and the
  embedding model, in the seeding, sweep and verification records.

**Dated note, 10 November 2026 (evening): Objective 06's verification. The first cycle meets clauses 1
and 2 and not clause 3; after one disclosed rule change, a second cycle meets all three.** The
evidence is `corpus/objective-06/runs/2026-11-10/objective-06.md`, with `seed/`, `cycle/`,
`verification/` and `rerun/`.

| | Cycle 1, `ce886e7` | Cycle 2, `333be14` |
|---|---|---|
| status | **the independent test** | informed by cycle 1 (D-108's note) |
| clause 1, unanswerable queries and zero-result searches in the log | 12 of 12, met | 12 of 12, met |
| clause 2, one entry per subject, count accurate | 4 entries of 3, met | 4 entries of 3, met |
| clause 3, no permission-only query in the log | **P02 in the log, not met** | none, met |

- **The seeding** went through the shipped `answer_question` and `search` as each query's user: the 8
  screened unanswerable asks all took no-answer path A, the 7 answerable asks were answered, and of
  the 6 permission-only asks 4 reached a no-answer while P04 and P07 were answered from readable
  material, as the pre-measurement found. A first attempt stopped after its first ask on a script
  error; that ask's one logged row was deleted and the thirty were seeded once.
- **Cycle 2 ran over the same seeded logs,** after cycle 1's 5 entries, 13 items and 1 cycle record
  were deleted.
- **Cycle 1 stands as the independent figure** for clause 3. The four subjects grouped correctly on
  both cycles, and no answerable query entered the log on either.
- **Correction to this entry's freeze line:** the SHA-256 given above, `e78314b7…`, is the file with
  Windows line endings as written before commit. Git stores it with LF endings (`core.autocrlf
  input`), and the committed file, which the seeding read, hashes to
  `e40a589c91893be6cca1ccd77d175571df8090d51d9ebdcaadade95be4dc1462`. The two differ only in line
  endings.

**Dated note, 10 November 2026 (night): the rule change is a departure from D-93, and is named as
one.** The thirty's status line says "Never tuned against again (D-93)". Since `333be14` that is
not true of the exclusion: the first cycle on the thirty chose the rule now shipped (D-108's evening
note). D-93 settles that the frozen sets are not tuning sets, so this was a departure from it. It
was made once, by the user's decision, and disclosed, with the first cycle kept as the independent
result. The file is frozen and is not edited; this note supersedes its line. The rule now shipped
has no independent figure (the requirements audit, D-119, its finding 8). The thirty remain the
acceptance test for a decline fix, as above.

**Dated note, 11 November 2026: the thirty informed a second rule choice, for voyage-4, and it is
named as a departure from D-93 (D-126).** The thirty's first cycle on `anthropic` left U01 out under
rank-one (#86: clause 1 not met, clauses 2 and 3 met). The user then chose threshold-first for
voyage-4, and the choice between it and the margin rule used the thirty's P02 and U01. So the night
note's "made once" is true of `333be14` only. As there, the first cycle on that configuration stays
the independent result, the rule now shipped for voyage-4 has no independent figure, and the file is
frozen and is not edited. The repeated seeding that this entry's note on the FLM configuration asks for
on `anthropic` was run as draws 1, 2 and 3: they are in D-126 and
`corpus/objective-06/runs/2026-11-11-anthropic/objective-06-d126.md`. FR-12's declines are not scored
there.

## D-111 · FR-13's option 3, the retrieval-only follow-up rewrite, was measured over three draws and not adopted; its code is withdrawn and its evidence kept

**Status:** Settled by the user · **Date:** 2026-11-10 · **Concerns:** FR-13, D-42, D-86, D-91,
D-103 · **Evidence:** `corpus/objective-02/runs/2026-11-09/fr13-phase4-dev/phase4.md` and
`runs/2026-11-09/fr13-phase4/` · **Commits:** `48c20cf` (the candidate), `9226b1b` (the
measurement), `a1fb201` (the withdrawal), on `feat/FR-13-followup-rewrite`.

**Why option 3.** D-103 found the restatement failure was in generation's use of the context, while
the spelled-out arm answered 6 of 9 frozen follow-ups. Option 3 had the model rewrite a follow-up
into a standalone question, embedded for retrieval only. The rewrite reached no prompt, reply or
citation, and only questions entered it (D-42).

**What was built** (`48c20cf`):
- a fourth `AIService` operation, `rewrite_followup`, with one attempt and then the composed join as
  a fallback, so an ask never failed because the rewrite did;
- a record-only `QueryLog.retrieval_rewrite` column;
- the measuring tools re-running the server's stored rewrite.

It came with 21 break-tested tests, and the full suite passed 2,369.

**The rule, fixed before any run.** The arms were means over three draws on the development threads.
Those were extended with seven cross-source threads, t32 to t38: their overlap check against both
frozen sets flagged 0 of 3,136 pairs. Option 3 would be adopted only if all of these held:
- its mean with-history match beat `main`'s by **more than 2 runs**;
- no guard arm's mean fell by more than 1;
- conformance held;
- 0 passages out of scope.

| arm | with-history (/19) | first-turn (/22) | spelled-out (/19) | correct declines | out of scope |
|---|---|---|---|---|---|
| `main`, three draws | 10, 9, 9 (mean 9.33) | 14, 14, 14 | 12, 12, 12 | 5/9, 2/6, 2/6 | 0 |
| option 3, three draws | 10, 10, 10 (mean 10.00) | 14, 14, 14 | 12, 12, 12 | 6/9, 3/6, 3/6 | 0 |

**Decision (the user's): not adopted.** The gain was +0.67 runs, inside D-103's band.
- **No guard fell.** Correct declines were a mean of 1 better under option 3.
- **The code is withdrawn by `a1fb201`.** It reverts `48c20cf` except the development threads, so
  `apps/`, `scripts/`, `CLAUDE.md` and `docs/` are as they were. Retrieval migration 0004 was never
  pushed, and `kmp_obj02_20261101` ends at 0003, as checked.
- **Kept:** t32 to t38, and the phase 4 evidence.
- **Restoring it is reverting `a1fb201`.** The phase 4 runner scripts under `corpus/` need it to run.

**What the measurement found.**
- **The rewrite itself was reliable in form.** All 66 with-history runs used it, with no fallback.
  The median call took 4.1 s, p90 5.3 s, and at most 6.7 s.
- **But gemma3:4b often failed to merge the referent.** The rewrite redistributed which follow-ups
  resolved, rather than adding to them:
  - **Gained:** t36 and t38, the cross-source shape that fails on the frozen set; t28 for the
    Administrator; and t22, where a wrong-passage citation was corrected.
  - **Lost:** t23 and t24 to rewrites that dropped the referent, and t27, its one lucky draw.
  - **t31's "match" under `main`** was an accident of join retrieval on a previous-answer thread.
    Option 3 declines it, as D-42 and D-86's decision 2 predict.
- **On t32, t34 and t35, the expected source was supplied at rank 1,** and generation still answered
  from the turn-1-adjacent passage below it. D-103's reading is reproduced with retrieval clean.
- **The frozen nine were run once, after the rule had decided, on `main`'s configuration.**
  - With history: **2/9**, beside 2/9 (8 November) and 3/9 (9 November) on identical code.
  - Spelled out 6/9, first turn 7/11, cold 1/9; schema 38/38; 0 leaks.
  - Nothing was changed after this result.

**If the generation model changes,** that is a separate decision. This one's premise was
gemma3:4b's ability to rewrite, so option 3 is a cheap candidate to measure again on the new model:
revert `a1fb201`, then run the same rule.

## D-112 · FR-13's follow-up clause is accepted as partial for NIT3003, and Stage 5 may close with it as a recorded deviation

**Status:** Settled by the user · **Date:** 2026-11-10 · **Concerns:** FR-13, D-60, D-91, D-92,
D-103, D-111, Stage 5 item 10 · **Supersedes:** D-91's "partial, with work continuing" status, for
the FLM build

**The clause.** FR-13, Server-End: "Maintains conversation context per session and passes prior
turns alongside the new question so that pronouns and abbreviated references resolve correctly."

**Its measured state on the shipped build** (FLM v0.9.39, gemma3:4b, the frozen nine threads):

| | with history | spelled out | out of scope |
|---|---|---|---|
| 8 November (the step 7 "after") | 2/9 | 6/9 | 0 |
| 9 November, phase 3, identical code | 3/9 | 6/9 | 0 |
| 9 November, phase 4, identical code | 2/9 | 6/9 | 0 |

- **What holds:** the history is wired (WIRED 3/3 through the server), it is re-scoped every turn,
  and there were 0 leaks.
- **What does not:** follow-ups that need the earlier turn mostly fail. The clause is half met: prior
  turns are passed, but pronouns do not resolve reliably.

**Three attempts, each measured under a rule fixed before it ran, and none adopted:**
- option 1, a prompt instruction (D-103);
- option 2, max-of-two retrieval scores (D-103);
- option 3, a standalone rewrite for retrieval (D-111).

**The evidence converges.** On several threads the right passage was supplied at rank 1, and
generation answered from the turn-1-adjacent passage. That is the same lever as D-102's open decline
finding: generation's use of supplied context. Its next step is one experiment, deferred:
- isolate the cap sentence from prompt rule 8;
- then try a prompt-level fix, under the same measurement rules.

**Decision (the user's, 10 November):**

- **FR-13's follow-up clause is accepted as partial for NIT3003.** The generation-side lever moves
  to NIT3004.
- **Stage 5's exit criterion is amended.** `M6-BUILD-PROMPT.md`'s Done line admitted only D-60's
  decline. It now also admits this accepted deviation, with a dated amendment there.
  - The set-level verdict can be COMPLETE with FR-13's clause presented as a deviation, giving its
    reason and these numbers: in the closing audit, the demonstration script's deviations list, and
    any assessment answer.
  - It is never presented as a tick.
- **This acceptance describes the FLM build.** If the generation or embedding provider changes
  (that is pending as its own decision), FR-13 is measured again on the new provider under the same
  rules. This record does not carry over to it.

**Where it applies:** D-91 (a dated note), `M6-BUILD-PROMPT.md`'s Done line, and Stage 5 item 10's
closing run.

**Dated note, 11 November 2026: FR-13 was re-audited after D-122 made `anthropic` the default, and
the verdict is recorded here verbatim.** One `requirements-auditor` run, read only, at `bd95f92`,
which was `main` when it ran, over every FR-13 clause against the proposal's text. It edited
nothing, and it ran no suite, server, database or provider. No measurement was made for this note.
The verdict is recorded here because a verdict that lives only in a terminal is the failure mode
D-61 names. Its one line: FR-13 is INCOMPLETE. The text above this note is left as written.

When this note was written, `main` had moved to `d63518b`, by #85, #86 and #87. They add only run
folders: under `corpus/objective-05/`, under `corpus/objective-06/`, and
`corpus/objective-02/runs/2026-11-10-anthropic/`. So no file the audit read had changed.

**FR-13's status after the re-audit, per provider.**

- **On `anthropic`, the default (Claude Haiku 5.5 with Voyage `voyage-4`): the follow-up clause is
  partial and unconfirmed.** It is not recorded as met.
  - **What was measured:** with history, the frozen nine threads scored 9/9 on Haiku's draw
    (`e04aab1`) and 9/9 on Sonnet's (`54f15cc`). Each model ran once.
  - **Through the server:** WIRED 3/3, with turn two correct 3/3, on Sonnet only (`58b9c27`). Haiku
    has no HTTP check.
  - **Why it is unconfirmed:** no noise band has been measured on this provider, and D-115 says
    FLM's is not carried over.
  - **This entry's acceptance does not cover it.** The decision above says "This acceptance
    describes the FLM build" and "This record does not carry over to it". So on the default build
    the clause is neither an accepted deviation nor a confirmed pass.
- **On `flm`, the offline alternative (gemma3:4b with EmbeddingGemma, FLM v0.9.39): the follow-up
  clause is partial, the deviation this entry accepted for NIT3003.** That is unchanged.
  - **The table above describes `main` run on FLM,** on 8 and 9 November.
  - **The deployed alpha runs older code.** It is at `8598d19`. Its answer path is `2f65a8e`'s,
    which was measured once, on 3 November: 1/9 with history
    (`corpus/objective-02/runs/2026-11-03/threads.json`).
- **On both providers:**
  - **D-42 passes prior questions, never prior answers,** so "passes prior turns" is declined in
    part. No frozen follow-up tests that cost. t09 matched on Claude because retrieval found a
    passage that names its referent, not because the earlier answer was used.
  - **"Reachable from any page" has no front-end test** (`CLAUDE.md` §8 condition 2, D-62). The
    link itself is built (`frontend/src/App.jsx:72`).
- **Every other FR-13 clause was read as satisfied.** The clause table is in the verdict below.

**These sentences above are corrected by this note, and left as written** (the verdict's section
(d), items 1 and 2):

- **"Its measured state on the shipped build".** The table is `main` run on FLM. Since D-122,
  `main` defaults to `anthropic`, and the deployed alpha runs the code measured on 3 November.
- **"prior turns are passed".** Prior questions are passed (D-42).

**What the user decided on it, 11 November.**

| Question | Decided |
|---|---|
| The verdict says `anthropic` needs more draws before FR-13 can be recorded as met there | **Record now, draws later.** This note records the verdict as returned. The draws are a task of their own: two further Haiku draws of the frozen nine on `kmp_voyage_20261110`, and one HTTP check on Haiku, with the pass rule committed before the first draw. A further dated note here records their result |
| The records that the verdict's section (d) lists as stale | **Listed here, fixed in a follow-up pull request.** Section (d) below is the list, by file and line. The Done line's new wording is put to the user before it is written |

**What this note's commit changes, and what it leaves.**

- **Changed:** this note, and `docs/stage-5-clause-audit.md`, which gains the section "After the
  re-audit (11 November 2026)". Those answer section (d)'s items 1, 2, 3 and 16.
- **Left for the follow-up pull request:** every other item of section (d).
- **Left without an owner yet:**
  - the front-end test for the Ask link (the verdict's "Missing or partial", item 4);
  - `scripts/server_record.py:263`, which recorded process 0 as the server (section (c), defect 1);
  - section (c)'s other defects: no snapshot record is committed for dump `80ff46d4…`, and the
    runbook and the committed measurement scripts can only measure FLM.
- **Left to the user: Stage 5's exit criterion.** `M6-BUILD-PROMPT.md`'s amendment of 10 November
  admits this deviation "on the FLM build". Until the draws are read, the closing audit (item 10)
  has neither an accepted deviation nor a confirmed pass to cite for FR-13 on the default build.

**Where the report is imprecise, checked against the repository.** None of these changes its
verdict.

- **Its line numbers are against `bd95f92`.** This note sits above D-113. So every line of this
  file that the report cites below `:8177` has moved down by this note's length: its citations of
  D-113, D-115, D-121 and D-122.
- **"The same ranked lists and scores"** (section (b)). The ranked lists are the same in every run
  of the two draws, and so are the input tokens. The scores are not: they differ by up to 0.00072.
  That is more than the 0.00047 it quotes from the frozen thirty, and more than t04's and t06's
  margins at the context cut (0.0003 and 0.0004). So its point there is stronger than it says.
- **"Reads seven follow-ups as 'history works'"** (section (a)). Each Claude record's
  `summary.readings` gives that label to t01, t02, t03, t04, t05, t06 and t07 asked by the
  Administrator, and t09. The report's list leaves out t09, which it treats separately.
- **"t09 was 'not resolved with history', as predicted"** (section (a)). The label is as stated in
  the FLM records of 3, 8 and 9 November. Each of them also holds `prediction_held: false` for
  t09. The frozen prediction says t09 is correct when spelled out, and on FLM it was not.
- **"Nothing references `TEXT.askNavLabel`"** (the clause table). Nothing under `frontend/tests`
  does. `frontend/src/App.jsx:72` renders it.
- **Section (d), item 19.** `apps/retrieval/conversation.py:80-82` already says that Stage 4's
  item 9a measured the block, and that the end-to-end measurement is D-86's. What is stale is the
  bold sentence at `:71` and "What is NOT known" at `:76-78`.
- **Section (d), item 21.** The walk's citation is at `docs/stage-5-item-8-walk.md:228`, not
  `:229`.
- **Re-read and found as stated:**
  - the scores in section (b)'s table, read from the records;
  - the alpha's answer path against `2f65a8e`: no diff;
  - the HTTP check record's process 0, against `server_observed.txt`'s listener (pid 44868) and the
    machine's boot at 11:19:05Z on 9 November;
  - no test under `frontend/tests` asserts the Ask link;
  - D-106's repeated draws for FR-10 on Claude;
  - no snapshot record committed for dump `80ff46d4…`. The `snapshot.json` that #87 adds is for
    another database, `kmp_obj02_anthropic_20261110`, at dump `6e514170…`;
  - CI run 42932385814, green on `bd95f92`;
  - the lines it cites in D-42, D-91, D-121, `M6-BUILD-PROMPT.md`,
    `docs/demonstration-script.md` and `docs/flm-baseline.md`.

**The verdict, verbatim.** Reproduced as the auditor returned it, quoted rather than edited.

> ## Audit: FR-13 Conversational Knowledge Assistant, re-audited after D-122 — 11 November 2026
>
> This audit covers the repository at `bd95f92`, which is `origin/main`, checked out on `docs/FR-13-follow-up-reaudit`. It is checked against the proposal's FR-13 section: `proposal.txt` lines 880–937, which is untracked and not in the repository. Nothing was edited. No suite, server, database or provider was run.
>
> **Verdict:** INCOMPLETE
>
> ### Clause coverage
>
> | # | Clause (proposal.txt:880–890) | Status | Evidence |
> |---|---|---|---|
> | FE-1a | "A conversational interface reachable from any page" | **Partial.** It is built, but no front-end test covers it (§8 condition 2, D-62) | `frontend/src/App.jsx:64-74` puts a link to `/ask` in the shell's primary navigation for every signed-in user (`App.jsx:142-154`). No test in `frontend/tests` asserts that link. Nothing references `TEXT.askNavLabel` (`frontend/src/constants.js:871`), and `frontend/tests/tabOrder.test.jsx:242` mentions the link only in a comment. |
> | FE-1b | "…retaining the thread…" | Satisfied | The thread lives in the address (D-77): `frontend/tests/askThread.test.jsx:221`, `:300`, `:341`. A follow-up is posted to the active thread: `askThread.test.jsx:466`, `askThreadList.test.jsx:159`, `askLimits.test.jsx:240`. Server side: `apps/api/tests/test_ask.py:972`, both roles. |
> | FE-1c | "…so follow-up questions need not restate the subject" | **flm: partial**, an accepted deviation (D-112). **anthropic: partial and unconfirmed**, with one draw per model | This is the outcome of SE-1c. See (a) and (b). |
> | FE-2a | "Previous conversations are listed" | Satisfied | `apps/api/views.py:2165-2181`; `frontend/src/pages/Ask.jsx:183`, `:632-643`, `:762`. Tests: `apps/api/tests/test_conversations.py:196`, `:681`, `:701` (both roles); `frontend/tests/askThreadList.test.jsx:99`, `:134`. |
> | FE-2b | "…and can be reopened" | Satisfied | `apps/api/views.py:2233-2239`; `apps/api/serializers.py:1164`. Tests: `test_conversations.py:334`, `:408`; `apps/api/tests/test_fr11_thread_scope.py:260-854`; `askThread.test.jsx:369`, `:610`; `frontend/tests/askReopened.test.jsx:112`, `:129`, `:147`. |
> | FE-2c | "the active thread can be cleared to begin a new topic" | Satisfied | The "Start a new topic" control is at `frontend/src/pages/Ask.jsx:706`. Tests: `askThread.test.jsx:404`, `:420`, `:436`. There is deliberately no delete route: `apps/api/urls.py:77-82`, `test_conversations.py:439`. |
> | SE-1a | "Maintains conversation context per session" | Satisfied, reading "session" as per conversation | History is read from `QueryLog` per conversation and per user (`apps/retrieval/conversation.py:136-169`, `:199-215`), so it outlives a login session. Tests: `apps/retrieval/tests/test_conversation.py:328`, `:409`, `:503`. |
> | SE-1b | "…passes prior turns alongside the new question…" | **Declined in part (D-42):** only prior questions are passed | `conversation.py:164-168` reads `question` only, and `QueryLog.answer_text` is never read (`:10-19`). The questions are composed into the retrieval string and the labelled prompt block (`:172-196`; `apps/retrieval/pipeline.py:453`, `:460`, `:522-525`). Tests: `test_conversation.py:434`, `test_ask.py:972`. D-42's stated reason, that no model text re-enters a prompt, is what the code does. |
> | SE-1c | "…so that pronouns and abbreviated references resolve correctly" | **flm: partial**, accepted as a deviation for NIT3003 (D-112). **anthropic: partial and unconfirmed:** 9/9, but on one draw per model | FLM: 2/9, 3/9 and 2/9 on `main`'s FLM build. The alpha's code scored 1/9. Claude: 9/9 on Haiku and 9/9 on Sonnet, and turn two 3/3 through the server on Sonnet. Files are listed in (b). |
> | V-1 | "context is truncated to a maximum number of prior turns" | Satisfied | `apps/core/constants.py:244` (3); `conversation.py:164-168`; `test_conversation.py:475`. The value 3 was chosen for a 4B model (D-42 §5) and its effect is unmeasured (D-86). The clause asks only for a maximum. |
> | V-2 | "The permission scope in FR-11 is re-evaluated on every turn" | Satisfied | `pipeline.py:441-446`. Tests: `test_conversation.py:549`, `test_ask.py:1004`, `apps/api/tests/test_fr11_scoping.py:610` and `:635`. On reopen: `test_fr11_thread_scope.py:298`, `:483`. |
> | BL-1 | "each turn triggers a fresh retrieval based on the resolved question rather than reusing the previous turn's passages" | Satisfied | `pipeline.py:460-469` runs on every call, and nothing is carried between turns. Test: `test_conversation.py:613`. "The resolved question" is implemented as the plain join of the prior questions and the new one (D-42 §3). The standalone rewrite was withdrawn (D-111). |
> | BL-2 | "Answer generation and citation verification follow FR-12 unchanged" | Satisfied | One endpoint serves both (`apps/api/views.py:2006-2116`; `pipeline.py:521-539`). An identifier that appears only in the history block is rejected: `test_conversation.py:653`, `test_ask.py:1116`. |
> | R-1 | "200 OK with the answer and updated conversation state" | Satisfied | `views.py:2106-2116`; `apps/api/answers.py:193-195`, `:335`; `apps/api/serializers.py:723-735`, `:768-770`. `last_updated_at` is set in the log transaction (`apps/retrieval/query_log.py:294-299`). Test: `test_ask.py:944`, both roles. |
> | DB-1 | Conversations: Create | Satisfied | `views.py:2183-2197`; `test_conversations.py:113`, both roles. |
> | DB-2 | Conversations: Read | Satisfied | `views.py:2165-2181`, `:2233-2239`. Another user's thread is 404 (`test_conversations.py:408`); no session is 401 (`:427`). |
> | DB-3 | Conversations: Update | Satisfied as database operations. There is no client rename route (D-43) | The title comes from the first question (`views.py:1988-2003`, `:2106-2107`), and `last_updated_at` moves every turn (`query_log.py:294-299`). Tests: `test_conversations.py:137`, `:150`, `:161`, `:172`, `:228`; `test_conversation.py:745`, `:774`. |
> | DB-4 | QueryLog: Create | Satisfied | Every exit records: `pipeline.py:495-505`, `:555-562`, `:574-581`. Tests: `test_ask.py:930`, `:944`; `test_conversation.py:718`. |
> | DB-5 | The fields of both tables | Satisfied | `apps/retrieval/models.py:29-35`, `:87-105`. |
>
> ### Missing or partial
>
> 1. **SE-1c on `anthropic` cannot be recorded yet.** It rests on one draw per model, and no noise band has been measured on this provider. Two more Haiku draws and one HTTP check on Haiku are needed (see (b)).
> 2. **SE-1c on `flm` is partial, accepted for NIT3003 (D-112).** D-112's figures describe `main`'s FLM build on 8–9 November. The deployed alpha runs older code that was measured once, at 1/9. D-112's sentence "prior turns are passed" (`docs/decisions.md:8148-8149`) overstates the code, which passes prior questions only.
> 3. **SE-1b is declined in part on both providers (D-42).** The frozen set has no follow-up whose referent exists only in an earlier answer's wording, so the cost D-42 concedes is untested on both providers.
> 4. **FE-1a has no front-end test (D-62).** The smallest fix is one test that renders `App` signed in as each role, on a route other than `/ask`, and asserts that the primary navigation's link named `TEXT.askNavLabel` has `href="/ask"`.
> 5. **The measurement records have defects (see (c)):**
>    - The HTTP check's server block records process 0, with that process's start time.
>    - The dump hash has no committed snapshot record.
>    - The runbook has no procedure for `anthropic`, and the committed measurement scripts can only run on FLM.
> 6. **Records about FR-13 are stale (see (d)).** In particular:
>    - D-112 has no dated note.
>    - `M6-BUILD-PROMPT.md:447-451` admits the deviation for the FLM build only.
>    - `docs/demonstration-script.md:477-502` leaves out D-112's deviation, which D-112 itself requires there (`docs/decisions.md:8168-8170`).
>    - `docs/stage-5-clause-audit.md` stops at 3 November.
>
> ### Invariant check
>
> 1. **Pass.** Filtering is before ranking:
>    - The role predicate is in the candidate query (`pipeline.py:464`), and the history read carries both the conversation and the user predicate (`conversation.py:165`).
>    - Another user's thread is 404, not 403 (`views.py:2127-2129`, `:2234-2236`; `test_ask.py:834`).
>    - In the Claude runs, 0 passages were out of scope in every way of asking, and scoping was shown for t06 and t07.
> 2. **Pass** for this slice. A reopened thread is re-scoped through the stamped chunks (`test_fr11_thread_scope.py:529`).
> 3. **Pass.** t06's follow-up source, T02, is an Administrator-only transcript. Both Claude models declined the Employee, and nothing in `apps/retrieval/` consults attendance.
> 4. **Pass.** The dual-role matrix lists `ask`, `conversation-list` and `conversation-detail` (`apps/api/tests/test_rbac.py:57-58`); `test_conversations.py:427` covers the 401.
> 5. **Pass.** `pipeline.py:539`; `test_conversation.py:653`.
> 6. **Pass.** `frontend/tests/ask.test.jsx:59`, `:103`.
> 7. **Pass.** `pipeline.py:495-505` and `:555-562`. The Claude records split the outcomes: path A for seven cold runs, path B declined for the scoped Employee runs.
> 8. and 9. Not applicable.
> 10. **Pass.** Schema conformance was 37/37 on each Claude model, through the generation loop FR-12 uses.
>
> Set-level checks for this slice:
> - **Owners.** django-backend has the endpoints, rag-pipeline has `conversation.py`, and react-frontend has `Ask.jsx`.
> - **One composition.** `compose()` is the only one, pinned to the pipeline by `apps/retrieval/tests/test_compose.py:243`. The measuring tools, however, now exist as three copies of the harness (`scripts/`, `corpus/objective-02/runs/2026-11-10/voyage-frozen/`, `…/haiku/`) and two of the HTTP check.
> - **Constants.** No literal 500, 50 or 25 appears inline in FR-13's code path. `NEW_CONVERSATION_TITLE` is defined at `apps/api/views.py:302` rather than in `apps/core/constants.py`; it is a fixed text, not a tuned value.
> - **No AI SDK import outside `apps/ai/`.** I searched `apps/`, `scripts/`, `config/` and `corpus/`.
>
> ### §8 definition of done
>
> 1. **Not met.** SE-1c is partial on both providers, and SE-1b is declined in part.
> 2. **Partly met.**
>    - CI passed both suites on `bd95f92` (run 42932385814).
>    - Server tests for every FR-13 route run from both roles (`conftest.py:275-280`).
>    - FE-1a has no front-end test.
> 3. **Met.** The happy path is tested, and so are the 404, 400, 401, re-scoping and no-answer paths.
> 4. **Met**, with D-60's decline as accepted in D-92. The later FR-13 commits carry FR-13 in the subject. The Claude thread draws are committed under FR-12 (`718ccaa`, `60de33d`), which `CLAUDE.md` §7 allows for work spanning requirements.
> 5. **Not met.** This audit reports gaps.
>
> ### Gate impact
>
> M6, on 1 November, is past. FR-13 was demonstrated on the FLM alpha and recorded as partial (D-91), and nothing here changes that.
>
> What this blocks now:
> - recording FR-13 as met on the default build;
> - Stage 5's exit criterion (`M6-BUILD-PROMPT.md:443-451`), which admits FR-13's deviation only for the FLM build — on the default build there is neither an accepted deviation nor a confirmed pass;
> - §8 condition 2 for FE-1a.
>
> The smallest fix, in order:
> 1. Two Haiku draws of the frozen nine and one Haiku HTTP check, with the rule fixed first. This costs about five cents.
> 2. The one front-end test described above.
> 3. Dated notes on the items in (d).
> 4. In `scripts/server_record.py:263`, treat a returned process 0 as unknown.
>
> FR-10's threshold on this provider was derived over three draws (`docs/decisions.md:7599-7606`). FR-13, a MUST, has had one.
>
> ## (a) Per provider: is the follow-up clause met?
>
> ### `anthropic`: partial and unconfirmed
>
> This is the default since D-122: Claude Haiku 5.5, with Voyage `voyage-4` at 1024. The resolution half passed on the only draw made with each model. It cannot yet be recorded as met (see (b)), and the passing half is narrowed by D-42 here exactly as on FLM.
>
> **What the 9/9 shows.**
> - Every answerable follow-up asked with history matched an expected phrase and cited an expected source. This held in-process, through the shipped `compose()` and pipeline, on both models:
>   - Haiku: `corpus/objective-02/runs/2026-11-10/haiku/threads.json`;
>   - Sonnet: `corpus/objective-02/runs/2026-11-10/voyage-frozen/threads.json`.
> - Counting the two scoped Employee follow-ups that should be declined, with-history runs were correct 11/11 on both models, with 0 leaks and 0 fabricated identifiers.
> - The frozen rule (part 10) reads seven follow-ups as "history works": correct with history and not correct cold. Each referent is named in the first question, so these seven are the evidence that pronouns resolve:
>   - t01 ("it"), t02 ("that"), t03 ("them"), t04 ("they"), t05 ("it");
>   - t06 and t07 asked by the Administrator ("them", "it").
> - Spelled out also scored 9/9, so neither retrieval nor generation limited any of them.
> - Through the server, on Sonnet only, the history was WIRED in all three threads. Turn two was correct 3/3 (`corpus/objective-02/runs/2026-11-10/voyage-http-check/http_check.json`).
>
> **What it does not show.**
> - **That resolution is reliable.** Each model ran once, Claude takes no sampling parameters, and no repeat exists.
> - **Anything from t08.** It is the topic change, answerable cold by design, and both models read it as "cold-answerable: proves nothing about history". With history, retrieval ranked T04 above D03 and the reply still came from D03. That shows carrying the first question did no harm, and nothing more.
> - **That a reference into an earlier answer resolves.** t09's follow-up is "What do they have to approve?". "They" is the facilities team, which only the first turn's answer names, and answers are never passed.
>   - t09's frozen prediction, that it fails with history, did not hold on either model. The rule reads it as "history works" with `prediction_held: false`.
>   - The records show why. The joined questions ranked D20 first (0.570), and D20 names the facilities team. They admitted D17 third (0.339). Both models answered from D17's sentence: "…must be approved by the facilities team at least one week in advance."
>   - So the match came from retrieval admitting the one approval passage that names the referent itself, not from the earlier answer (`voyage-frozen.md:103-111`; `haiku-round.md:103-104`). D-86's own note warned of this (`docs/decisions.md:5690-5691`).
>   - On all four FLM draws, t09 was "not resolved with history", as predicted.
> - **"Abbreviated references" beyond dropped subjects.** The nine follow-ups use pronouns and demonstratives only. None uses a shortened name or an acronym.
> - **Threads longer than two turns.** So nothing is shown about the truncation at `MAXIMUM_CONVERSATION_TURNS`.
> - **Haiku through the server.** The HTTP check ran on Sonnet only.
>
> ### `flm`: partial, an accepted deviation for NIT3003 (D-112)
>
> This is gemma3:4b with EmbeddingGemma on FLM v0.9.39. On `main`'s FLM build, with history matched:
> - 2/9 on 8 November (`runs/2026-11-08/after-030/threads.json`, `19c98a8`);
> - 3/9 on 9 November (`runs/2026-11-09/fr13-phase3/threads.json`, `b2ebba8`, whose `apps/` and `scripts/` are byte-identical to `19c98a8`'s);
> - 2/9 on 9 November (`runs/2026-11-09/fr13-phase4/threads.json`, `48c20cf`, with the in-process passthrough pin in `run_frozen_main.py`).
>
> Spelled out was 6/9 each time, with 0 leaks. t08 was cold-answerable, and t09 not resolved, on every draw.
>
> **The deployed alpha is not that build.**
> - `KMP_Prototype-alpha` is at `8598d19`, from 1 November. That commit defaults to `flm` and a dimension of 768.
> - Its answer path is byte-identical to `2f65a8e`'s: there is no diff over `apps/ai/`, `apps/retrieval/`, `apps/core/constants.py` and `config/settings.py`.
> - That code was measured once, on 3 November (`runs/2026-11-03/threads.json`): with history 1/9, spelled out 3/9, cold 1/9, first turn 7/11, 0 leaks.
> - D-112's table therefore describes `main` on FLM, not what is deployed.
>
> ### D-42 on both providers
>
> The clause says "passes prior turns". The code passes prior questions only. That part is declined in part by D-42 on both providers.
> - **On FLM**, the narrowing is not what limits the clause. The subject-noun follow-ups that D-42 said would resolve did not (D-91). D-103 and D-111 place the limit in how generation uses the supplied context.
> - **On `anthropic`**, the narrowing's cost did not surface. That is only because no frozen follow-up has a referent that exists solely in an answer and in no passage the joined questions retrieve. D-42's own example is "what about the second one?" after an answer that listed three.
> - That case is untested on both providers. By design it can resolve only when the referent is also in a passage that is retrieved again. It remains a recorded deviation, whatever further draws show.
>
> ## (b) How many draws does the 9/9 rest on?
>
> | Run | Commit | Database, dump | Model | First turn | With history | Spelled out | Cold | Leaks |
> |---|---|---|---|---|---|---|---|---|
> | 3 Nov (the alpha's code) | `2f65a8e` | `kmp_obj02_20261101`, `3bf98403…` | gemma3:4b | 7/11 | 1/9 | 3/9 | 1/9 | 0 |
> | 8 Nov | `19c98a8` | same | gemma3:4b | 6/11 | 2/9 | 6/9 | 1/9 | 0 |
> | 9 Nov, phase 3 | `b2ebba8` | same | gemma3:4b | 6/11 | 3/9 | 6/9 | 1/9 | 0 |
> | 9 Nov, phase 4 | `48c20cf` + pin | same | gemma3:4b | 7/11 | 2/9 | 6/9 | 1/9 | 0 |
> | 10 Nov | `54f15cc` | `kmp_voyage_20261110`, `80ff46d4…` | claude-sonnet-5-5 | 11/11 | 9/9 | 9/9 | 1/9 | 0 |
> | 10 Nov | `e04aab1` | same | claude-haiku-5-5 | 11/11 | 9/9 | 9/9 | 1/9 | 0 |
>
> All six records name the same frozen set (`acfe3d47…`) and scoring rule version 2.
>
> **Draws per model.**
> - **Haiku 5.5, the default:** one draw, and no HTTP check.
> - **Sonnet 5.5:** one draw of the nine, and one HTTP check of three threads (t03 and t04 as the Employee, t06 as the Administrator; `58b9c27`).
> - **The two thread draws are not repeats of one configuration.** Their retrieval was identical: the same ranked lists and scores, and the same 188,557 input tokens over 37 calls. Their agreement shows the result does not depend on which of the two models generates. It is not a repeat.
>
> **No noise band has been measured on `anthropic`.**
> - The only repeat on this provider is of Voyage's embedding scores. Two passes over the frozen thirty differed by up to 0.00047 (`voyage-http-check.md:70-71`).
> - That matters here: t04's and t06's composed sets sit within that jitter of the context-budget cut, with margins of 0.0003 and 0.0004 (`voyage-http-check.md:84-88`). Even the supplied passages can differ between draws.
> - No generation repeat exists. The records say so themselves (`haiku-round.md:138`; `voyage-frozen.md:115-116`; D-121, `docs/decisions.md:9274-9275`).
>
> **The rules.**
> - **D-103:** a single-pass delta of ±1–2 runs is noise, and no FR-13 delta may be read as an effect unless it clears the band. Further attempts need "repeated draws per configuration so the rule compares means, not single passes" (`docs/decisions.md:6782-6787`, `:6794-6796`).
> - **D-112:** FLM's verdict rests on three draws on identical code (`:8140-8144`). On a provider change, FR-13 "is measured again on the new provider under the same rules" (`:8172-8174`).
> - **D-115:** "the noise band is measured on this provider, not carried over from D-103" (`:8324-8326`).
> - **D-113:** lists D-103's band among the FLM baselines to re-derive before `anthropic` is relied on (`:8226-8234`).
> - **FR-10 on this provider:** the repository applies the same rule there. D-106's note requires repeated draws on Claude (`:7540-7548`), and Haiku's threshold was derived over 19 documents three times each (`:7599-7606`).
>
> **Conclusion: yes. The `anthropic` verdict needs more draws before it can be recorded.**
> - "Met" claims that resolution is reliable at the ceiling. One draw per model cannot carry that claim under these rules.
> - The comparison with FLM needs no further draw. 9/9 against 2/9, 3/9 and 2/9 is six or seven runs, far outside FLM's band.
>
> **The draw that would settle it.**
> - **Two further recorded draws** of the frozen nine (`corpus/objective-02/threads.json`, sha256 `acfe3d47…`, rule version 2), on the default configuration:
>   - `claude-haiku-5-5`, with `voyage-4` at 1024;
>   - D-120's threshold 0.2687 and floor 0.2468;
>   - effort `"low"`, `CLAUDE_MAX_TOKENS` 16000, `MAXIMUM_STATEMENTS` 6, `MAXIMUM_CONTEXT_TOKENS` 4000.
> - **On `kmp_voyage_20261110` at dump `80ff46d4…`**, so they join `e04aab1`'s draw as three draws of one configuration. The HTTP check's rows there are not retrieval candidates, and the corpus gate checks the chunk set.
> - **At a clean commit** whose answer path matches `bd95f92`'s. It has been byte-identical since `e04aab1`.
> - **With a rule written and committed before the first draw.** For example, `haiku-round.md`'s own bar applied to every draw: with history at least 8/9, 0 leaks, 0 fabricated identifiers. The spread across the three draws then becomes this provider's first measured band.
> - **Plus one HTTP check on Haiku** through a freshly started server, since the default model has none.
> - **The tools.** The committed scripts cannot make these runs (see (c)).
>   - `corpus/objective-02/runs/2026-11-10/haiku/citation_harness_haiku.py` can, unchanged, with each record in a new run folder.
>   - The HTTP check needs a copy of `voyage-http-check/conversation_http_check_voyage.py` with the model changed.
> - **Cost.** At the recorded rate of about $0.023 per thread draw, two draws cost about $0.05. The HTTP check costs under a cent at Haiku's prices.
> - **Reading the result.** If every draw passes, the resolution half is recorded as met on `anthropic`, with D-42 still a recorded deviation. If any draw falls short, FR-13 is partial on `anthropic` too, with the band reported.
>
> ## (c) Do the Claude records carry their commit, configuration and database?
>
> | Field | `haiku/threads.json` | `voyage-frozen/threads.json` | `voyage-http-check/http_check.json` |
> |---|---|---|---|
> | `recorded_at` | 2026-11-10T19:38:27+11:00 | 15:57:36+11:00 | 16:35:42+11:00 |
> | `commit_sha` | `e04aab1…` | `54f15cc…` | `58b9c27…` |
> | commit exists / on `main` / ancestor of HEAD | yes / yes / yes | yes / yes / yes | yes / yes / yes |
> | agrees with its markdown | yes (`haiku-round.md:88`) | yes (`voyage-frozen.md:10-13`; parents `8ecb2c6`, `20f4375`) | yes (`voyage-http-check.md:10-11`; parent `4c31d78`) |
> | uncommitted changes | false, `[]` | false, `[]` | false, `[]` |
> | dump / database | `80ff46d4…d1e4` / `kmp_voyage_20261110` | same | same |
> | provider / chat model | anthropic / claude-haiku-5-5 | anthropic / claude-sonnet-5-5 | anthropic / claude-sonnet-5-5 |
> | embedding model / dimension | voyage-4 / 1024 | same | same |
> | threshold / floor | 0.2687 / 0.2468 | same | same |
> | thread-set hash / rule | `acfe3d47…` / v2 | same | same |
> | server | in-process, names the copy | in-process, names the copy | http: waitress 3.0.2, threads null, **pid 0, started 2026-11-09T11:19:15.787Z**, DEBUG off |
>
> **What was verified.**
> - **The commits.** `git cat-file -t` returns `commit` for all three. `git branch -a --contains` lists `main` and `origin/main` for each, and `git merge-base --is-ancestor` succeeds for each. Each commit adds the copy that ran, and each copy is unchanged from its run commit to HEAD.
> - **The thread-set hash.** The SHA-256 of `corpus/objective-02/threads.json`, at HEAD and at all three commits, is `acfe3d47afed7d97c2f1952d0528a9612cb6b9b65706f1491ad32f16cf2aee87`. The file last changed at `5314d86`, the 1 November freeze.
> - **The configuration.** The Haiku record is today's default:
>   - `config/settings.py:328` (`anthropic`), `:346` (1024), `:354` (`claude-haiku-5-5`) and `:356-357` (`voyage-4` and the recorded URL);
>   - `.env.example:34`, `:43`, `:45-46`, `:64`;
>   - `apps/core/constants.py:191-192`.
> - **The answer path since the Haiku run.** FR-13's answer path is byte-identical between `e04aab1` and `bd95f92`:
>   - no diff in `apps/retrieval/{pipeline,conversation,ranking,scoping,verification,query_embedding,partial_matches,query_log}.py` or `apps/ai/{prompting,generation,schema,_openai_compat}.py`;
>   - `apps/ai/anthropic.py` changed only to add transcription (D-123);
>   - `apps/core/constants.py` changed no value FR-13 reads.
> - **The Sonnet records** differ from the default only in the generation model.
>
> **Defects found.**
> 1. **The HTTP check's server block describes Windows' System Idle Process, not the server.**
>    - It records `pid: 0` and `process_started_at: "2026-11-09T11:19:15.787Z"`. Process 0's start time on this machine is exactly that, and the machine booted at 11:19:05Z that day (both read on 11 November with `Get-CimInstance`).
>    - The markdown says the server "started fresh at 16:33:46" (`voyage-http-check.md:26`) and that the record holds the pid "as unknown" (`:30`). `server_observed.txt` gives the listener as pid 44868, started 2026-11-10T16:33:43.
>    - The cause is `scripts/server_record.py:263`, which records whatever `OwningProcess` the lookup returns, 0 included.
>    - Read literally, the record says the server had been running since 9 November, which is the opposite of the restart step 12b requires. Nothing checks that restart (`docs/measurement-runbook.md:493-494`).
> 2. **The server's thread count and version were not observed.**
>    - `threads`, `listen` and `command_line` are null, and the console warned "the thread count is unknown, not 24" (`http_check.txt:5`). D-85's 24 threads are evidenced only outside the record, in `server_observed.txt`.
>    - The version 3.0.2 came from the check's own environment (`version_source`). The markdown's "read from its replies" (`voyage-http-check.md:29`) is true of `DEBUG` and the server name only.
> 3. **The dump hash cannot be checked from the repository.**
>    - No snapshot record for `80ff46d4…` is committed. Step 8 says the run folder receives a copy of `snapshot.json` (`docs/measurement-runbook.md:295`, `:311`). The only committed snapshot record is FLM's, `corpus/objective-02/runs/2026-11-01/snapshot.json`.
>    - The harness records the hash it is given without checking the database against it (`scripts/measurement_record.py:180-191`).
> 4. **The measurement rules have no path for `anthropic`.**
>    - Steps 9, 12a and 12b gate on `check_flm.py` and FLM v0.9.39 (`docs/measurement-runbook.md:337-338`, `:477-479`, `:532`). The section "A copy for another provider" (`:622-660`) covers only making and re-indexing the database.
>    - The committed scripts can only run on FLM (`scripts/citation_harness.py:137`, `:1388-1400`; `scripts/conversation_http_check.py:363-396`).
>    - All three records came from run-folder copies with a provider gate in place of the FLM gates. Each copy and its full diff are committed beside the record, so the recorded commit does name the code that ran.
> 5. **The call parameters are in the commit, not the record.** None of these is in the records; all are fixed by the commit and unchanged at HEAD:
>    - `CLAUDE_EFFORT` (`apps/ai/anthropic.py:60`) and `CLAUDE_MAX_TOKENS` (`:56`);
>    - `MAXIMUM_STATEMENTS` and `MAXIMUM_CONVERSATION_TURNS`.
>
>    D-115 calls the call parameters provisional. The records hold the configured model name, not any identifier the API returned.
> 6. **The recorded commit alone does not reproduce the configuration.** At the recorded commits, `config/settings.py` still defaulted to `flm` and `claude-sonnet-5-5`. Each copy set the environment before Django started (`haiku/citation_harness_haiku.diff:38-42`), so the configuration is reproducible from the commit together with its copy.
>
> Nothing else is missing, unknown or inconsistent.
>
> ## (d) What is now stale
>
> **In `docs/decisions.md`:**
>
> 1. **`:8138` (D-112)** says "Its measured state on the shipped build (FLM v0.9.39…)". Since D-122, `main` ships `anthropic` by default, and the deployed alpha measured 1/9 on older code. "The shipped build" now describes neither.
> 2. **`:8148-8149` (D-112)** says "prior turns are passed". The code passes only prior questions.
> 3. **`:8172-8174` (D-112)** says the provider change is "pending as its own decision". D-122 made that decision, and the re-measurement exists only as one draw per model. D-112 has no dated note.
> 4. **`:1763` and `:1824-1827` (D-42)** say "Unmeasured: yes" and "FR-13 end to end is still unmeasured… a set… which does not exist." The set has existed since 1 November and has been run six times.
> 5. **`:1831-1836` (D-42)** say follow-ups hold "for subject nouns and not for references into an answer's wording". That was falsified on FLM (`:1854-1872`). On Claude, subject-noun follow-ups resolved on one draw and t09 resolved through retrieval. The 2 November note there ends at D-91 and records nothing later.
> 6. **`:6148` (D-91)** says the measured reason is "not yet run". It was measured on 3 November (`:6200`). The 10 November note at `:6219-6221` covers the FLM build only.
> 7. **`:9282-9283` (D-121)** says "The default provider is still FLM". D-122 overtook this the same day, and there is no dated note.
> 8. **`:9303-9305` (D-122)** counts the threads' 9/9 and the HTTP check toward the switch. It does not say that they are one draw per model, that the HTTP check was Sonnet's, or what FR-13's status is. This is silence rather than staleness.
>
> **In `M6-BUILD-PROMPT.md`:**
>
> 9. **`:443-451`.** The Done line's amendment admits the deviation "on the FLM build". The default build has neither an accepted deviation nor a confirmed pass.
> 10. **`:494-497`** lists D-45 and D-42 as the deliberate shortfalls, and leaves out D-112's deviation.
>
> **In `docs/demonstration-script.md`:**
>
> 11. **`:298-305`** says to avoid follow-ups, that FR-13 is "partial at the gate", and that its measurement "comes after the gate". It has since been measured. The advice is still right for the FLM alpha and wrong for the default provider.
> 12. **`:398-401`** says the cold and spelled-out runs "are step 5's" and that the measurement "comes after the gate". Step 5 and step 7 have both run since.
> 13. **`:456-459`** says "The measurement is step 5's". That is overtaken.
> 14. **`:477-502`.** The deviations list lacks D-112's reason and numbers, which D-112 requires there (`docs/decisions.md:8168-8170`). The script has had no amendment since 7 November.
>
> **In the stage records:**
>
> 15. **`docs/stage-5-item-8-walk.md:225-227`** says "the measured reason is step 5's", and there is no note for D-112. The walk itself remains true of the FLM alpha.
> 16. **`docs/stage-5-clause-audit.md:500-507`.** FR-13's last entry is the 3 November FLM baseline. Nothing records 8–9 November, D-112, D-122 or the Claude runs.
> 17. **`docs/stage-4-clause-audit.md:84`** says FR-13 "holds for subject nouns" and that previous-answer follow-ups do not resolve. This is a record at its date: it was falsified on FLM and did not hold for t09 on Claude.
>     - `:85` was closed by item 4b (`docs/stage-5-clause-audit.md:382`).
>     - `:86` and `:92` still hold.
>
> **Elsewhere:**
>
> 18. **`docs/flm-baseline.md:17-21` and `:611-617`** say FR-13 end to end "remains unmeasured" and that the set "does not exist". Both were overtaken on 3 November.
> 19. **`apps/retrieval/conversation.py:71-79`** says "THE MULTI-TURN PROMPT IS UNMEASURED". It has been measured: 38/38 on FLM and 37/37 on each Claude model.
> 20. **`docs/stage-4-open-items.md:149-151`** says previous-answer follow-ups do not resolve. That is true of the design in general; t09 resolved on Claude.
> 21. **Line references have drifted.** `docs/demonstration-script.md:294-295` and `:457`, `docs/stage-5-clause-audit.md:478-479` and `docs/stage-5-item-8-walk.md:229` cite `test_fr11_scoping.py:608` and `:633`. At HEAD those tests begin at `:610` and `:635`.
> 22. **`README.md` and `CLAUDE.md`** state nothing about FR-13's status, numbers or provider, so nothing in them is stale on FR-13.
>
> ## What I could not check
>
> - **I ran no suite.** The suites' result here is CI's: run 42932385814 on `bd95f92` succeeded on both jobs, and the checks on PR #84 were green.
> - **I re-scored no run.** I read the stored scores and checked t02, t08 and t09 by eye.
> - **I could not verify the dump, the media hash or the HTTP check's logs.** None is in the repository, and I read nothing outside it.
> - **I read no `.env`.** So I cannot confirm which database the running alpha serves. I verified only that the alpha's worktree is at `8598d19` and what that commit's defaults are.
> - **I did not check the provider consoles** for spend or for model snapshots.
> - **I read the front-end tests without running them.**
>
> **Verdict: FR-13 is INCOMPLETE.**
> - On `flm`, its follow-up clause is partial, an accepted deviation for NIT3003 (D-112); the deployed alpha scored 1/9.
> - On `anthropic`, it is partial and unconfirmed: 9/9 on one draw per model, with no measured noise band.
> - On both providers, D-42 narrows "prior turns" to prior questions, and "reachable from any page" has no front-end test.

## D-113 · D-35 is superseded: the `anthropic` provider is funded by the Max plan's monthly Claude API credits, and is brought into use

**Status:** Settled by the user · **Date:** 2026-11-10 · **Concerns:** D-35, D-03, D-04, D-36, D-67,
D-83, D-102, D-112, `CLAUDE.md` §4, `docs/ai-provider.md` · **Supersedes:** D-35's "no external AI
spend", and `CLAUDE.md` §4's "no budget … Plan nothing around a provider switch"

**What changed.** D-35 rested on one premise: "The team has no budget, and no member funds it
personally." The user's Claude Max plan includes Claude API credits, $100 USD per billing cycle. The
user showed Anthropic's "API credits for Max, Ultra, and Team plans" page on 9 November.
- **How they work:** they are claimed by linking a Claude Console organisation to the plan, with no
  payment method. They cover the Claude API, not Claude Code. They expire each cycle, with no
  rollover.
- **Voyage is not covered.** It is a separate company. It has 200M free tokens, limited to 3 requests
  and 10K tokens a minute until a payment method is added.

**Decision (the user's):**

- **The `anthropic` provider is funded and brought into use** for development, measurement and
  demonstration: Claude for generation, Voyage for embeddings, the proposal's §9.2 configuration.
  The user is implementing it. The live-call path was dormant until now, and its first fixes are on
  `fix/FR-12-claude-live-call`.
- **`flm` remains implemented, pinned at v0.9.39 (D-83), and available.** D-35's other half also
  falls: the demonstration no longer depends on one machine. D-114 records what that means for M8.
- **The keys:** a Console API key from the linked organisation, never the Max sign-in, plus a Voyage
  key. Both live in `.env` only and are never committed or pasted into a chat. Adding a payment
  method to Voyage, which NFR-08's load test and normal use need beyond the free rate limit, is the
  user's to do.
- **Spend stays within the monthly credit.** A run expected to exceed it needs the user's say-so
  first.
- **`CLAUDE.md` §4 and `docs/ai-provider.md` §1 are amended** to say this, with the user's approval
  of 10 November.

**Consequences, all following from rules already settled:**

- **A provider switch is a full re-index (R10).** Voyage's vectors are not comparable with
  `embed-gemma`'s 768 dimensions (D-03).
  - If the chosen Voyage model does not output 768 dimensions, the pgvector column changes, and that
    is a schema migration under `CLAUDE.md` §7.
    - **Dated note, 10 November 2026: corrected by D-117.** voyage-4 never outputs 768. No
      migration can change the width either, because migration 0002 already sizes the column from
      `EMBEDDING_DIMENSION`. The column is resized by `reindex --resize-column` instead.
- **`manage.py reindex` deletes and recreates every chunk.** On a database with conversation history,
  every `AnswerCitation.chunk` is then nulled (`SET_NULL`, D-67), and every reopened thread shows its
  provenance as removed.
  - So re-index a **new database restored from the snapshot.** Never re-index in place on
    `kmp_obj02_20261101` (the FLM measurement baseline) or `kmp_demo_20261101` (the alpha). Creating
    that database needs the user's word, as every database operation does.
- **Every tuned value and baseline describes FLM's vectors and gemma3:4b:**
  - `RELEVANCE_THRESHOLD = 0.30` is an `embed-gemma` cosine (D-102);
  - D-100's cap was chosen against gemma3:4b's truncation;
  - D-103's ±1–2-run band;
  - the frozen thirty, the nine threads, NFR-08's p90.

  Before `anthropic` is relied on, its threshold is re-derived on development material
  (`dev-set-v2.json`). Then the frozen sets and NFR-08 are run on it under
  `docs/measurement-runbook.md`, and FR-13 is measured again (D-112). `questions.json` and
  `threads.json` stay frozen. Nothing is tuned against them.
- **Document text and questions leave the machine** for Anthropic and Voyage while this provider is
  selected. That is the proposal's production design, accepted with this decision.
- **Records that cite D-35 for the past stay true where written:** the NFR-08 local-model baseline,
  the M6 walk, the recording (D-98) and the code comments on the dormant path. The code comments are
  for the session implementing the provider to update.
- **Which provider is the default and which one M8 runs on are not decided here.** They are measured
  first. D-114 decides only that the host is no longer tied to the NPU.

**Where it applies:** D-35 (a dated note), `CLAUDE.md` §4, `docs/ai-provider.md` §1, and dated notes
in `M6-BUILD-PROMPT.md` (the hosting paragraph) and `docs/stage-4-open-items.md` §2.3.

## D-114 · M8 can be hosted on any device with the platform in place; the NPU laptop is no longer required

**Status:** Settled by the user · **Date:** 2026-11-10 · **Concerns:** D-64 and its 7 November note,
D-35, D-88, D-113, NFR-03, FR-01 · **Supersedes:** D-64's 7 November note, "M8 is hosted on the NPU
laptop, with FastFlowLM"

**Decision (the user's).** M8, the final deployment on 27 November, can be hosted on any device that
has the platform in place:
- PostgreSQL 16 with pgvector;
- the Django back end under its WSGI server;
- the built front end;
- a `.env` naming the database and the provider.

On the `anthropic` provider, generation and embedding run as API calls (D-113), so no NPU is needed.
**The NPU laptop with FLM remains a valid host.**

**What this changes:**

- **The 7 November note's reason no longer holds.** It gave two: the proposal's Google Cloud VM
  cannot run FastFlowLM, and there was no budget for Claude. The VM design (Gunicorn behind Nginx
  terminating TLS, Ubuntu 22.04) is available again for M8, as are the team's other machines and the
  laptop itself.
- **The host device is chosen later,** with the provider, once `anthropic` has been measured
  (D-113). FLM still needs the laptop (D-36).
- **Gunicorn runs on Linux and macOS, Waitress anywhere.** On a non-Windows host, item 9's
  Waitress-specific notes in `docs/alpha-deployment.md` need their Gunicorn equivalent. The
  configuration itself is environment-driven and carries over:
  - `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`;
  - the cookie flags;
  - WhiteNoise's single origin;
  - nothing serving `MEDIA_ROOT`.

**Still open, from the 7 November note, and sharper now:**

- **Which database M8 serves.** On `anthropic` it must be a Voyage-indexed copy, re-indexed fresh
  (D-113).
- **Whether M8 stays on loopback.** A host reached over a network exposes open registration (FR-01),
  and needs:
  - `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` and the `*_COOKIE_SECURE` flags set;
  - TLS in front;
  - Postgres bound to loopback (PR #62's fix, which item 11's early pass found).

  D-64 says exposing it is a new decision, with the registration question attached.
- **NFR-03's TLS scan.** It needs a TLS-terminated deployment. Any host that is not loopback-only
  makes it possible.
- **Item 11's closing run reviews whichever host and configuration are chosen.** Its live checklist
  was written for the loopback laptop and gains the network checks if the host is exposed.

**Where it applies:** D-64 (a dated note) and `CLAUDE.md` §4's `anthropic` bullet.

## D-115 · Sonnet 5.5 is the `anthropic` provider's default generation model, as the configuration under test

**Status:** Settled by the user (the model); provisional (the call parameters) · **Date:** 2026-11-10 ·
**Concerns:** D-113, D-102, D-103, D-111, FR-12, FR-13, `config/settings.py`, `apps/ai/anthropic.py`

> **The model was superseded on 10 November 2026 by D-121.** Haiku 5.5 is now the default, after
> the Haiku round matched this model on every bar. The call parameters below stand: Haiku was
> measured with them. This entry is left as written, per the rule at the head of this file.

**Decision (the user's, 10 November):** `ANTHROPIC_MODEL` defaults to `claude-sonnet-5-5` in
`config/settings.py` and `.env.example`. It replaces `claude-opus-5`, which was a release behind.

- **Why Sonnet:** it costs $2 / $10 per million tokens, against Opus 5.5's $4 / $20, so D-113's monthly
  credit goes about twice as far. At roughly 5K tokens in and 1–2K out, a question costs 2–3 cents:
  about 4,000 questions a month, fewer when attempts are retried.
- **This is the configuration under test, not a verdict.** D-113 left the default provider and the M8
  provider to measurement, and the model follows the same rule. The threshold re-derivation, the
  frozen thirty, the nine threads and NFR-08 run on Sonnet 5.5 first. Moving to another model after
  that is a new decision and a new run.
- **Changing the generation model is not a re-index.** Embeddings come from Voyage, so the vectors do
  not depend on the Claude model.
- **A `.env` that sets `ANTHROPIC_MODEL` overrides the default.** The development `.env` was changed
  to match on 10 November.

**The call parameters.** The implementing session set these on 10 November (`apps/ai/anthropic.py`,
3a706d9). They are provisional until measured:

- **No `temperature`.** The pinned SDK (anthropic 1.5.0) has no sampling parameters, and current Claude
  models refuse them. Generation on this path is therefore not deterministic run to run, unlike FLM at
  temperature 0, so the noise band is measured on this provider, not carried over from D-103.
- **`thinking` is left at the model's default.** Disabling it is a 400 on Sonnet 5.5.
- **`effort` is `"low"`,** because the task is extraction from supplied passages. It is the first
  value to tune if the declines (D-102) or the rank-1 misreadings (D-111) persist.
- **`CLAUDE_MAX_TOKENS = 16000`** is Claude's own ceiling, because the thinking counts against
  `max_tokens`. FLM's 800 would cut replies off.

**Not adopted: Anthropic's server-side refusal fallback for Sonnet 5.5.** It needs the beta endpoint,
and a refusal on policy documents is unlikely. A refusal reaches the shared loop as an empty reply,
fails the schema, and counts as a failed attempt.

**Where it applies:** `config/settings.py`, `.env.example`, `apps/ai/anthropic.py`.

## D-116 · `AIService.embed()` takes a keyword-only `input_type`, so Voyage is told whether it is embedding a question or a passage

**Status:** Settled by the user · **Date:** 2026-11-10 · **Concerns:** D-113, FR-08, FR-12, R10,
`apps/ai/base.py`, `apps/ai/anthropic.py`, `apps/ai/flm.py`, `apps/ai/prefixes.py`,
`docs/ai-provider.md` §1

**What prompted it.** Voyage marks each text as a question or a passage with an `input_type` field
on the request, and puts a different instruction in front of each side. Voyage documents better
retrieval with it. `embed(texts)` had no way to say which side a text is on.
- `apps/ai/prefixes.py` already said that Voyage is told on the request rather than by a prefix,
  but nothing passed it.
- `docs/ai-provider.md` §1 says a parameter that changes what the model is asked is argued on its
  own merits. This one does, so it was put to the user.

**Decision (the user's, 10 November):**

- **`embed(texts, *, input_type=None)`,** on the Protocol and on every implementation. The values
  are Voyage's own, `"query"` and `"document"`, named `INPUT_TYPE_QUERY` and
  `INPUT_TYPE_DOCUMENT` in `apps/ai/base.py`.
- **Retrieval passes `"query"`** (`embed_question`). **Ingestion passes `"document"`** for every
  chunk, `reindex` included. The width probes in `apps/ai/checks.py` and `reindex` pass nothing,
  because the width does not depend on it.
- **Voyage sends it,** and sends nothing when it is `None`, which is Voyage's default.
- **FLM accepts it and sends nothing.** EmbeddingGemma's task prefixes already carry the side. They
  stay in the callers, because the document prefix needs the title, which `embed()` never sees.
- **The test doubles take the keyword too,** about twenty of them, under `apps/ai/base.py`'s rule
  that a contract and its implementations do not differ by a parameter.
  `apps/ai/tests/test_embed_input_type.py` checks the Protocol, both providers and the stub.

**Consequences:**

- **It changes Voyage's document vectors, so it had to land before the first Voyage re-index.** No
  Voyage chunk exists yet. Voyage says vectors made with and without it stay comparable, but the
  threshold re-derived under D-113 will describe vectors made with it.
- **FLM is unchanged.** No FLM request carries the field, so nothing on the FLM baseline moves.
- **`CLAUDE.md` §4's `AIService` snippet does not show the keyword,** just as it does not show
  `on_attempt`. `docs/ai-provider.md` §1 does.
- **#68 (FR-10) merged first,** on 10 November. It added `classify_document` to the same files, and
  the merge into #69 kept both. Classification embeds nothing, so it passes no `input_type`.

**Where it applies:** `apps/ai/base.py`, `apps/ai/_openai_compat.py`, `apps/ai/anthropic.py`,
`apps/ai/flm.py`, `apps/ai/testing.py`, `apps/retrieval/query_embedding.py`,
`apps/ingestion/embedding.py`, `docs/ai-provider.md` §1.

## D-117 · A new embedding width is applied by `reindex --resize-column <database>`, not by a migration

**Status:** Settled by the user (the resize flag); proposed by the implementing session (the
database name as confirmation) · **Date:** 2026-11-10 · **Concerns:** D-03, D-08, D-28, D-67, D-113,
R10, FR-08, `apps/ingestion/management/commands/reindex.py`, `docs/ai-provider.md` §4 ·
**Corrects:** D-113's "that is a schema migration under `CLAUDE.md` §7"

**What prompted it.**

- **voyage-4 never outputs 768.** It outputs 1024 dimensions by default, and 256, 512 or 2048 on
  request (Voyage's API reference, checked 10 November 2026). Moving to Voyage changes the
  column's width.
- **D-113 said that change "is a schema migration". It cannot be.** Migration 0002 sizes the column
  from `EMBEDDING_DIMENSION` when it first runs, and the model reads the same setting, so the
  migration state always matches the model.
  - With `EMBEDDING_DIMENSION=1024`, `makemigrations --check` reports "No changes detected"
    (checked offline, 10 November), and `migrate` has nothing to apply.
  - A database restored from the FLM snapshot therefore keeps `vector(768)`.
- **`reindex`'s own refusal gave advice that did nothing.** It told the operator to "run
  makemigrations and migrate to resize the column".

**Options put to the user:**

- the resize inside `reindex`, behind an explicit flag;
- a fresh database built by `migrate` at 1024 and loaded by script rather than restored from the
  snapshot. That needs no resize code, but it departs from D-113, and the rows would not match the
  FLM baseline's;
- an unsized `vector` column. Any width fits, but Postgres stops refusing a wrong width and
  `CLAUDE.md` §4's rule changes.

**Decision (the user's, 10 November): `reindex --resize-column`.**

- **Without the flag,** when the stored column's width is not `EMBEDDING_DIMENSION`, `reindex`
  refuses and says why `migrate` cannot help.
- **With it,** one transaction deletes every chunk through the ORM and alters the column to
  `vector(EMBEDDING_DIMENSION)`. Deleting through the ORM sets each `AnswerCitation.chunk` to null
  (D-67). The rebuild then runs as before, one source per transaction.
- **None of the old vectors survive,** because they cannot be cast to the new width.
  - A source that fails to rebuild afterwards has no chunks left. Its status is set to
    `Indexing failed` (for a meeting, `Processing failed`) rather than left at `Indexed`.
  - Running `reindex` again without the flag rebuilds those sources. A run interrupted after the
    resize is finished the same way.
- **`--dry-run`** reports the resize and changes nothing.

**The flag's value is the connected database's name.** This is the implementing session's proposal,
from the coordinating session's suggestion, and the user can drop it.
- Deleting every chunk nulls every citation, so the command must be told which database it is
  connected to: `reindex --resize-column <database>`.
- A name that does not match is refused even when no resize is needed. The caller then believes
  they are connected somewhere else, and an ordinary re-index nulls citations too.
- This is what keeps `kmp_obj02_20261101` and `kmp_demo_20261101` safe from a slip.

**Consequences:**

- **The switch on a restored copy:** set `AI_PROVIDER=anthropic`, `EMBEDDING_DIMENSION=1024` and the
  two keys in `.env`. Then run
  `python manage.py reindex --provider anthropic --resize-column <database>`. A database built by
  `migrate` at 1024 needs no flag.
- **Voyage's free tier cannot carry a re-index.** Each chunk is its own request (D-28), and the free
  tier allows 3 requests a minute. Under D-118 a 429 is retried, but with no wait, so a rate-limited
  chunk uses up its three attempts in moments and fails. The payment method D-113 leaves to the
  user comes first: Tier 1 allows 2,000 requests and 8M tokens a minute. The user said on
  10 November that they are adding it.
- **The schema is unchanged.** There is no migration and no model change, so `makemigrations --check`
  still passes. Postgres still refuses a vector of the wrong width.
- **Django's foreign keys are deferred,** so the delete leaves checks pending, and Postgres refuses
  to alter a table while they are. The command runs them first, with `connection.check_constraints()`.

**Where it applies:** `apps/ingestion/management/commands/reindex.py`, `docs/ai-provider.md` §4,
`.env.example`, and a dated note on D-113.

## D-118 · A provider's 4xx ends in NFR-19's 503: a rate limit is retried, any other 4xx is refused at once, and each is logged

**Status:** Settled by the user · **Date:** 2026-11-10 · **Concerns:** NFR-19, FR-08, FR-10, FR-12,
D-19, D-104, D-113, D-117, `apps/ai/_status.py`, `apps/ai/base.py`, `apps/ai/_openai_compat.py`,
`apps/ai/anthropic.py`, `apps/ai/flm.py`, `apps/ai/generation.py`, `apps/ai/classification.py`,
`apps/retrieval/query_embedding.py`, `apps/ingestion/embedding.py`, `apps/ai/attempt_log.py` ·
**Supersedes:** the rule, in those modules and their tests, that a 4xx "surfaces unchanged and
consumes no retries"

**What prompted it.** The coordinating session found it on 10 November by reading the code, before
any live run, and the implementing session confirmed it.
- **Both providers let a 4xx surface as itself.** Only a transport failure or a 5xx became
  `ProviderUnavailable`.
- **Nothing above them catches anything else.** The generation loop, the question embedding and
  the ask view catch only `ProviderUnavailable`, and there is no DRF `EXCEPTION_HANDLER`. So a 4xx
  reached the user as a 500.
- **On FLM that never arose,** because FLM does not send 4xx. On the `anthropic` provider they are
  routine:
  - a 429 under NFR-08's concurrency, or on Voyage's free tier of 3 requests a minute;
  - the 400 Anthropic sends once the monthly credit (D-113) has run out.
- **NFR-19 requires the opposite:** "return a 503 … rather than crashing".

**Decision (the user's, 10 November): retry a 429, and answer the rest with the 503.** In the
user's words, a rate limit counts as a failed attempt: three tries, then the 503 notice. Every other
provider error, an empty credit balance included, shows the 503 notice and logs the real cause.

- **One rule, in one place** (`apps/ai/_status.py`). It is used wherever a status error is caught:
  the shared embed call (FLM and Voyage), FLM's chat call and Claude's call.
  - **A 429 is `ProviderUnavailable`.** It uses up an attempt, like an outage. After the three
    attempts of D-19 (`MAXIMUM_GENERATION_ATTEMPTS`, `MAXIMUM_EMBED_ATTEMPTS`,
    `MAXIMUM_CLASSIFY_ATTEMPTS`), the ask answers the 503.
  - **Any other 4xx is `ProviderRefused`,** a new subclass of `ProviderUnavailable` in
    `apps/ai/base.py`. The retry loops stop on it at once, because the same request would be
    refused again. Since it is a `ProviderUnavailable`, everything that catches that still does,
    so the ask view answers the 503 without a change.
  - **A 5xx is unchanged:** an outage, retried under D-19.
- **Each 4xx is logged where it happens,** with the status and the provider's message, cut at 300
  characters, on the attempts logger (`attempt_log.refused`):
  - a **429 as a WARNING,** because a rate limit passes;
  - **anything else as an ERROR,** because it needs a person.

  Logging at the provider covers ingestion and `reindex`, which log no attempts of their own.
- **Where it lands:**
  - **the ask:** the 503 with its fixed notice, from question embedding or from generation;
  - **ingestion:** the chunk fails, after three attempts for a 429 and after one for a refusal, and
    the document's status says so (D-28);
  - **classification:** FR-10 (#68, D-104) merged the same day. `classify_document` uses the same
    `_chat_once` and `_claude_once`, so the document is left unclassified (invariant 8). The merge
    into #69 rewrote #68's two tests that asserted a 4xx propagates after one call.
- **No wait on `Retry-After`.** Pausing inside a user's request is its own question, and three
  quick attempts at a rate limit end in the 503 that says "try again shortly". Waiting is a
  candidate for `reindex`, where nobody is waiting, if rate limits turn out to matter there.

**How it got here, the same day.** The first version (2436f61) retried every 4xx three times. The
user's answer narrowed retries to the 429 before the pull request merged. That removes the first
version's cost: a mistyped model name or a bad key no longer spends two wasted calls.

**What it gives up, accepted:**

- **A misconfiguration now reads as a 503** to the user, not as a traceback to a developer. The old
  rule kept the traceback so that a typo would not look like an outage. The ERROR line now names the
  status and the provider's message instead.
- **The startup check gains,** though. A probe refused with a 4xx is now `ai.W001`, with the status
  in its message. Before, the exception escaped the check.

**Tests:**

- `apps/ai/tests/test_status.py` pins the rule:
  - a 5xx is an outage, and is not logged there;
  - a 429 is retryable, and a WARNING;
  - any other 4xx is a refusal, and an ERROR.
- `apps/api/tests/test_ask_provider_refusals.py` runs the real `AnthropicService` through
  `POST /api/ask`, from both roles. Each case gives the 503 and writes no `QueryLog` row:
  - a Voyage 429 at question embedding, after three calls, and a 401 after one;
  - a Claude 429 at generation, after three calls, and the credit-exhausted 400 after one.
- The generation, classification and provider tests assert both counts and the log levels.
  `apps/ingestion/tests/test_embedding.py` asserts a refused chunk fails on its first attempt.
- NFR-19's fault-injection count is unchanged: three calls, then the 503.
- The SDK-shaped builders the route tests need live in `apps/ai/testing.py`, because a vendor SDK
  may not be imported outside `apps/ai`, tests included.

**Where it applies:** the modules under **Concerns**, `docs/ai-provider.md` §1, and D-117's free-tier
note.

## D-119 · The audit of FR-10, FR-19 and Objectives 05 and 06 returned INCOMPLETE, and its verdict is recorded here verbatim

**Status:** Recorded, with the user's decisions on it · **Date:** 2026-11-10 · **Concerns:** FR-10,
FR-19, FR-14 (D-69), Objectives 05 and 06 · **Audited:** FR-10 at `6357fe0` (PR #70, merged as
`d3a9892`) and FR-19 at `45d5c25`

One `requirements-auditor` run, read only, over both worktrees. It checked the proposal's text for
FR-10, FR-19 and FR-14's `KnowledgeGaps` read, Objectives 05 and 06, and CLAUDE.md §8. It edited
nothing and ran nothing. It is recorded here because a verdict that lives only in a terminal is the
failure mode D-61 names. Its one line: FR-10 INCOMPLETE, FR-19 INCOMPLETE, Objective 05 NOT MET
(clause 1), Objective 06 NOT MET on its independent run (clause 3). Neither requirement is in the M6
twelve.

**What the user decided on it, 10 November.**

| Finding | Decided |
|---|---|
| 1: FR-10's summary, key points, sectioned summarising and grounding | **Not built in NIT3004.** D-104's own condition, "only if time allows after both verifications pass", is not met, and FR-10 stays INCOMPLETE on those clauses (D-104's dated note) |
| 3, 4, 5: a removed AI tag comes back; a person cannot apply a tag; nothing deactivates or deletes a tag | **All three are built,** on a branch of their own: a removal kept beside the machine's assignment; a person applying an existing tag or a new Topic, with the 409 on a duplicate name; an Administrator deactivating a tag in use or deleting an unused one (D-105's dated note when that branch lands) |
| 11: FR-19's "on a scheduled basis" | **Daily,** registered by a committed script (D-107's note, `027640e`) |
| The security review's L1 and L2 (D-107's note), on FR-12's route | **A 500-character cap on a search term and a D-79 `search` throttle of 30 per minute,** in their own pull request (D-79's dated note when it lands) |

**What was done on it the same night, on `feat/FR-19-knowledge-gaps`.**

| Finding | Done |
|---|---|
| 7: D-105's sentence on when classification runs | A dated correction on D-105 |
| 8: the frozen sets' status lines | D-106's and D-110's notes name both revisions as departures from D-93 (D-110's in `027640e`). Neither frozen file is edited |
| 11 | `scripts/register_knowledge_gap_schedule.ps1` and section 9 of `docs/alpha-deployment.md` (`027640e`). Registering it on the host is the user's step |
| 12: three passages describe the exclusion as it was before `333be14` | Corrected in `8c6156f`: `docs/api-contract.md`, D-110's note (marked as a correction) and `objective-06.md` |
| 13: CLAUDE.md §8 condition 2 is not shown at `45d5c25`, and #70 is not merged in | At `45d5c25`, pytest 2786 passed, matrix 33/33. `main` merged in `3e5357f` (#69 and #70). At `8c6156f`, pytest 2839 passed, matrix 33/33; npm test 317 passed; lint, build and `makemigrations --check` clean. CI runs on the pull request |
| 14: D-69 has no forward note | Added in `8c6156f` |
| 15: the second development check's columns | Recorded on D-108; the script now reports the top-ranked passage (`8c6156f`) |

**Left as recorded, or owed.**

- **2: the tag browser is FR-15's facets.** A recorded deviation (D-105), unchanged.
- **6 and 10:** the front-end test of the truncation notice, the department label and the stale
  comment go with the tag branch.
- **9: Objective 02's 60-second bound is not re-timed with classification at upload.** Still owed
  before M8 (D-105); it needs FLM.
- **16: the exclusion's residual risk is unmeasured** (D-108).
- **Objective 05's clause 1 and Objective 06's clause 3 stay NOT MET on their independent runs.** The
  informed re-runs are recorded as informed (D-106, D-108, D-110), and no further run is planned.

**Where the report is out of date or overstates, checked against the repository.**

- **Its line numbers are against `6357fe0` and `45d5c25`,** and findings 7, 8 and 11 to 15 were dealt
  with after it, as above. Its "FR-19's full suite at 45d5c25 is unknown" is now known: 2786 passed.
- **Its first correction is to the brief, not to the repository.** The brief called PR #70 open when
  it had already merged.
- **No overstatement found** in the claims re-read against the code and this file: D-104's condition
  (finding 1), `reject_tag` deleting the link (finding 3), the order of classification and chunking
  at upload (finding 7), and the stale comment (finding 10).

**The verdict, verbatim.** Reproduced as the auditor returned it, quoted rather than edited.

> ## Audit: FR-10, FR-19, Objectives 05 and 06 (NIT3004), 10 November 2026
>
> **Verdict**
> - **FR-10 (Document Classification & Metadata Extraction, SHOULD): INCOMPLETE.** Five clauses are deferred by D-104: the summary, key points, sectioned summarising, grounding, and the summary in the 200. Three more partials are not recorded anywhere (gaps 3–5).
> - **FR-19 (Knowledge Gap Log, COULD): INCOMPLETE.** "On a scheduled basis" is only partly met, and nothing records that. The interface contract contradicts the exclusion rule as it now works. CLAUDE.md §8 condition 2 is not shown at HEAD 45d5c25.
> - **Objective 05: NOT MET.**
>   - Clause 1: NOT MET. 12 of 20 (60%) on the independent run; 14 of 20 (70%) on the informed re-run.
>   - Clause 2: MET.
>   - Clause 3: MET.
> - **Objective 06: NOT MET as independently verified.**
>   - Clause 1: MET as measured, but only on wordings screened so that FR-12 declines them (D-110).
>   - Clause 2: MET.
>   - Clause 3: NOT MET on cycle 1, the independent run (P02 in the log). It is met on cycle 2, but cycle 2 is informed by cycle 1 and is not independent.
>
> **Corrections to the brief**
> - **PR #70 is merged, not open.** `gh pr view 70` says MERGED at 2026-11-10T01:12:16Z, as d3a9892 on origin/main. CI was SUCCESS on head 6357fe0 for both jobs (Django on Python 3.12 with Postgres 16, and React lint, build and test). The worktree's local branch is `feat/FR-10-classification`; the remote branch is `fix/FR-10-objective-05`.
> - **The FR-19 branch does not contain PR #70.** d3a9892 is not an ancestor of 45d5c25. Both sides changed four files since dae8792:
>   - `apps/api/views.py`
>   - `docs/api-contract.md`
>   - `docs/decisions.md`
>   - `frontend/src/constants.js`
>
> ### Clause coverage: FR-10 (worktree C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506)
>
> | Clause (proposal.txt) | Status | Evidence |
> |---|---|---|
> | 683 "displays an automatically assigned type … and department, each marked as AI-generated and editable by users holding the appropriate permission" | Satisfied (one minor mislabel, gap 10) | C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506\frontend\src\components\Classification.jsx:586-657; ...\apps\api\views.py:1400-1432 (scoped 404, then contribute_content, 772-781); ...\frontend\tests\documentClassification.test.jsx:198-399; ...\apps\api\tests\test_document_classification.py:308-383 (both roles through session_client) |
> | 684 "a short summary and a list of key points, shown beneath the title in search results" | **Declined, D-104** | Not built anywhere. ...\docs\decisions.md:6729-6734 |
> | 685 "tags across four dimensions … shown separately" | Satisfied on the detail page | Classification.jsx:586-601 and 663-688. Department is a column, not a tag (D-72, D-105), recorded. |
> | 685 "A tag browser lists all values with item counts" | **Partial, recorded (D-105)** | decisions.md:6864 says "FR-15's facets already count tags". The facets (...\apps\api\repository.py:260-285) list only values on documents in scope that match the other filters, so not "all values". |
> | 687 "A single structured request issued at upload returns the classification, the summary and key points, and the tag assignments together" | **Partial** | One call at upload returns the type, department and tags: ...\apps\ingestion\documents.py:276-280 and 303-334, ...\apps\ai\classification.py:109-144. No summary or key points (D-104). |
> | 688 "the type must be selected from a fixed list" | Satisfied | ...\apps\ai\classification.py:220-224; ...\apps\documents\classification.py:265-269; serializer ChoiceField; Classification.jsx:629-637; test_document_classification.py:363; documentClassification.test.jsx:497-512 |
> | 688 "Tag names must be unique within a dimension after normalising case and whitespace" | Satisfied | ...\apps\documents\models.py:159-169; ...\apps\documents\tests\test_models.py:127-134; parser dedup at ...\apps\ai\classification.py:234-242 |
> | 688 "Documents exceeding the model's context limit are summarised in sections and consolidated, rather than being truncated … without the user being told" | **Declined, D-104** (decisions.md:6747-6751) | The classifier reads the first 1,500 tokens (...\apps\core\constants.py:557) and records `input_truncated`. The detail tells the user (Classification.jsx:602-604), but that sentence has no front-end test (gap 6). |
> | 689 confidence: "recorded with each assignment … below the configured threshold are marked provisional and presented for confirmation" | Satisfied | ...\apps\documents\classification.py:290-312, 355-357, 375-398; FR-15 reads exclude held links (repository.py:174, 228, 281); test_classification_apply.py:71-230; test_fr15_reads_exclude_provisional.py:51-79; documentClassification.test.jsx:218-237 and 562-586 |
> | 690 controlled taxonomy growth, including "A tag confirmed by a user … is not altered by later reprocessing" | Satisfied | ...\apps\documents\classification.py:299-300, 323-344, 393-394, 468-514; test_classification_apply.py:121-131, 230-265, 322-347; ...\apps\ingestion\tests\test_classification_hook.py:131 |
> | 691 provenance: "visually distinguished from those applied by a person and either may be accepted or removed in a single action" | **Partial, unrecorded** (gap 4) | The distinction and one-action accept/remove work (Classification.jsx:158-198; views.py:1435-1464). No route lets a person apply a tag. |
> | 692 correction: "any value a user edits are retained and is not overwritten by later reprocessing, and the machine assignment is retained alongside it" | **Partial, unrecorded** (gap 3) | Type and department are satisfied (classification.py:281-312; test_classification_confirm.py:146). A removed AI tag comes back. |
> | 693 grounding: "the summarisation prompt constrains output to content present in the document" | **Declined with the summary, D-104** | No summarisation prompt exists. |
> | 694 taxonomy: one Tags table, one ContentTags join, "Tags are deactivated rather than deleted where content still references them" | **Partial** | The structure is there (models.py:152-192), and PROTECT stops a referenced tag being deleted (D-12). Nothing deactivates or deletes a tag (gap 5). Meetings are never classified (D-105, recorded). |
> | 695 "200 OK with the classification, summary and tags" | **Partial** | views.py:1390-1397 returns `{classification, tag_details, department}`, with no summary. |
> | 695 "409 Conflict on a duplicate tag name within a dimension" | **Declined, D-105** (decisions.md:6860-6862) | Unreachable because no route creates a tag from a typed name; confirm_proposed_topic uses get_or_create (classification.py:484). This is honest, but it holds only because gap 4 exists. |
> | 695 "422 Unprocessable Entity where insufficient text was extracted" | Satisfied | views.py:1377-1381; classification.py:213-214; documents below the minimum have no ExtractedContent (ingestion\documents.py:221-234); test_document_classification.py:212-220; documentClassification.test.jsx:763 |
> | 697 "DocumentAnalysis (Create, Read, Update); Tags, ContentTags (Create, Read, Delete)" | **Partial** | Everything is met except Tags Delete, which has no operation (gap 5). Departures from the field table are recorded (D-105). |
>
> ### Clause coverage: FR-19 (worktree C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506-fr19)
>
> | Clause | Status | Evidence |
> |---|---|---|
> | 1266 "A list, visible to Administrators … grouped by subject with an occurrence count and the ability to mark an entry as addressed" | Satisfied | ...\frontend\src\pages\KnowledgeGaps.jsx:81-142 and 195-217; ...\apps\api\views.py:1908-1974 (CanReviewKnowledgeGaps on every route); ...\frontend\tests\knowledgeGaps.test.jsx:185-545; ...\apps\api\tests\test_knowledge_gaps.py:104-170 and 289-329 |
> | 1268 "Aggregates unanswered queries and zero-result searches from FR-12 on a scheduled basis, including those arising through FR-13 and FR-18" | **Partial** | Aggregation works, including FR-13 turns (...\apps\retrieval\gaps.py:172-249; ...\apps\retrieval\tests\test_knowledge_gaps.py:241-317). FR-18 is not built (D-107, recorded). The schedule is not set up anywhere (gap 11). |
> | 1269 "queries that returned nothing because the user lacked access are excluded" | Satisfied by a heuristic, with residual risk recorded in D-108 | gaps.py:252-267 (the top-ranked passage decides, even below the threshold, since 333be14); searches are recounted as the Administrator (...\apps\retrieval\search.py:526-556); test_knowledge_gaps.py:376-501; test_search_total.py:79-122. The current rule has been tested only on the set that chose it. |
> | 1270 "grouped by similarity rather than exact wording … asked repeatedly across departments" | Satisfied | Centroid cosine at 0.5256 (gaps.py:270-336; tests :516-711). Departments are not modelled, so "across departments" shows only as the count (D-107, recorded). |
> | 1271 "200 OK with the gap list" | Satisfied | views.py:1918-1921; test_knowledge_gaps.py:110-120 and 177-209 |
> | 1273 "KnowledgeGaps (Create, Read, Update); QueryLog, SearchLogs (Read)" | Satisfied | Created and updated by run_cycle; updated by PATCH; logs are read only, with PROTECT foreign keys (...\apps\retrieval\models.py:215-251); search_total writes no row (test_search_total.py:104). Extra columns recorded (D-107). |
> | FR-14, 952 "KnowledgeGaps (Read)" | Satisfied on this branch, for a role holding `review_knowledge_gaps` | views.py:1892-1901; Dashboard.jsx gap panel; frontend\tests\dashboard.test.jsx gap tests; test_knowledge_gaps.py:348-405. This closes D-69 (D-107), but not on main until FR-19 merges. |
>
> ### Objective clauses against the evidence
>
> **Objective 05.** Evidence: C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506\corpus\objective-05\runs\2026-11-10\
>
> - **What the records carry, and what I checked.**
>   - Each record names its commit with no uncommitted tracked files: aee5374 for the first run, caf9e22 for the re-run.
>   - Each names FLM v0.9.39 (CLI and server), the configuration flm / gemma3:4b / embed-gemma, the full dump hash 3bf98403…6f59, the database and threshold 0.95.
>   - The reference-set SHA is 763e9a62…. I recomputed it: the committed blob and the working file both match. reference.json has not changed since fb9e18a (9 November, 17:31), which is before any run on the twenty.
>   - The first-run evidence exists twice, as cac299f (on aee5374) and f187201 (on the follow-up). The files are identical.
> - **Headline.** It is built, with Department as `Documents.department` rather than a tag (D-72, D-105, recorded). AI tags at or above 0.95 are applied immediately but labelled "Suggested by AI", with Confirm and Remove. That matches FR-10's confidence clause and the objective's own clause 2.
> - **Clause 1: NOT MET.** 12 of 20 (60%) on the independent run (verification\verification.md, "Clause 1"); 14 of 20 on the informed re-run (rerun\verification\verification.md).
> - **Clause 2: MET.** 48 of 48 below the threshold held, 27 of 27 at or above applied, no violations. The re-run: 47 of 47 and 25 of 25.
> - **Clause 3: MET.** I checked the three discarded departments against the corpus's six; none of them is among the six. The script checks out-of-scheme links by dimension only (...\scripts\objective05_verify.py:196-198). Links are in-scheme by construction (classification.py:323-329).
> - **Labelling.** The revision is honestly labelled. The type definitions in caf9e22 name the frozen misses' shapes: register, inventory, schedule, roster, tracker, announcement. So the prompt now shipped has no independent accuracy figure.
>
> **Objective 06.** Evidence: C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506-fr19\corpus\objective-06\runs\2026-11-10\
>
> - **What the records carry, and what I checked.**
>   - Commits: ce886e7 for the seeding and cycle 1; 333be14 for cycle 2.
>   - FLM version, configuration and dump hash are all recorded.
>   - Query-set SHA: I recomputed it. The committed blob is e40a589c…; the CRLF working file is e78314b7…, as D-110's correction says.
> - **Clause 1: MET, 12 of 12 on both cycles.** The 8 unanswerable asks were screened to a top in-scope score of at most 0.25. On the draft's unscreened wordings, FR-12 answered 6 of 8, so they would never reach the log (...\corpus\objective-06\runs\2026-11-08\pre-measurement\pre-measurement.md:36-39 and 53-58). D-110 records this.
> - **Clause 2: MET.** 4 entries of 3, each count equal to its items.
> - **Clause 3: NOT MET on cycle 1, met on cycle 2.**
>   - Cycle 1: verification\verification.md:30 and 40 show P02 in the log.
>   - Cycle 2: met (rerun\verification\verification.md:40).
>   - The development set scored both rules 15 of 15 (decisions.md:7215-7218), so the frozen thirty chose the rule.
>   - P04 and P07 never exercised the clause.
> - **Labelling.** The change is honestly labelled. The rule now shipped has no independent figure.
>
> ### Missing or partial (numbered)
>
> 1. **FR-10: summary, key points, sectioned summarising and grounding** (684, 687, 688 sentence 3, 693, and the summary in 695). Recorded as deferred in D-104 (decisions.md:6729-6734 and 6747-6751), which is honest. But D-104 builds them "only if time allows after both verifications pass", and neither objective passed independently. FR-10 cannot be complete without them; the record should say they will not be built.
> 2. **FR-10: the tag browser is FR-15's facets** (685). Partial, recorded (D-105, decisions.md:6864). Values with no in-scope document are never listed, and counts depend on the active filters.
> 3. **FR-10: a removed AI tag comes back** (692, "any value a user edits are retained and is not overwritten by later reprocessing, and the machine assignment is retained alongside it").
>    - `reject_tag` deletes the link: ...\apps\documents\classification.py:462-465.
>    - The next classify or reprocess creates it again: rule 4 at :323-329 calls `_link_tag` at :383-392.
>    - Nothing keeps the machine's assignment. No test covers this.
>    - **Unrecorded.** D-105 records only the proposed-topic version (decisions.md:6879).
> 4. **FR-10: a person cannot apply a tag** (691, "those applied by a person"; UC-09 A3, "adds one it did not").
>    - ...\apps\api\urls.py:40-54 has confirm and delete only. `applied_by="user"` links come only from the D-74 seed script.
>    - **Unrecorded.** The 409 is unreachable precisely because of this.
> 5. **FR-10: no operation deactivates or deletes a Tag** (694, "Tags are deactivated rather than deleted"; 697, Tags "Delete"). Only the schema holds this: `active` at models.py:156-157, and PROTECT. **Unrecorded** for FR-10.
> 6. **FR-10: the truncation notice is untested in the front-end suite.** The test fixture only ever has `input_truncated: false` (documentClassification.test.jsx:54). CLAUDE.md §8 condition 2 is not met for that sentence.
> 7. **FR-10: D-105 says classification at upload runs "after the ingestion pipeline has decided the document's status"** (decisions.md:6855-6858). That is false: it runs before chunking (...\apps\ingestion\documents.py:276-282). The note of 10 November is correct, but the sentence needs a dated correction.
> 8. **The frozen files' status lines are now untrue.**
>    - C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506\corpus\objective-05\reference.json says "never tuned against".
>    - C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506-fr19\corpus\objective-06\queries.json says "Never tuned against again".
>    - Both sets later chose a change (caf9e22 and 333be14). The departure from D-93 is disclosed in substance in the D-106 and D-108 notes, but neither note names it as a departure from D-93.
> 9. **FR-10 at upload affects FR-08, an M6 MUST.**
>    - Classification runs inside the ingestion transaction while holding the row lock.
>    - Objective 02's 60-second bound has not been re-timed; D-105 says this is "owed before M8" (decisions.md:6906-6914).
>    - The worst case is 3 calls × 300 s (...\apps\ai\classification.py:89; flm.py uses that timeout).
>    - Recorded as owed.
> 10. **Minor (FR-10).**
>     - A department the uploader typed is labelled "Suggested by AI" when the AI's suggestion matched it (classification.py:303-305; Classification.jsx:89-90).
>     - The comment at ...\apps\core\constants.py:200-202 ("not so anything uses it before Stage 6") is stale.
> 11. **FR-19: "on a scheduled basis"** (1268). Partial, **unrecorded**: D-107 asserts it is met.
>     - There is a command (...\apps\retrieval\management\commands\aggregate_knowledge_gaps.py:3-6).
>     - No schedule, interval, script or set-up instruction exists in the repository.
>     - D-107 says "Task Scheduler on the laptop" (decisions.md:7063-7064), but D-114 has removed the laptop as the M8 host.
> 12. **FR-19: the documents describe the old exclusion rule.**
>     - C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506-fr19\docs\api-contract.md:1187-1190 says "if the top passage above `RELEVANCE_THRESHOLD` … otherwise, including when nothing clears the threshold, it is kept". This contradicts the code since 333be14.
>     - The same staleness is in decisions.md:7362-7364 (D-110's note says the exclusion "admits at RELEVANCE_THRESHOLD") and in ...\corpus\objective-06\runs\2026-11-10\objective-06.md:69-71.
> 13. **FR-19: §8 condition 2 is not shown at HEAD 45d5c25.**
>     - After 333be14, only apps/retrieval/tests were run (350 passed); the full suite is pending.
>     - There is no PR, so CI has not run.
>     - PR #70 is not merged into the branch, and four files overlap.
>     - The 33/33 matrix result predates the change. The change touched no route, but the matrix has not been re-run.
> 14. **D-69 has no forward note.** decisions.md:3901-3902 still says the dashboard does not read KnowledgeGaps "because the table does not exist".
> 15. **The second exclusion check's table does not show why the current rule decided.** Its top-score and readable columns come from admitted passages only (...\scripts\exclusion_dev_check.py:102-111). So d27 shows "None" where the rule's evidence should be. The outcome column does call the cycle's own function (:100), so the pass is valid.
> 16. **FR-19's residual risk is unmeasured.** A genuine gap whose weak nearest passage is Administrator-only is now left out. Recorded (D-108, decisions.md:7219-7221). 5 of the 25 sources are Administrator-only.
>
> ### Invariant check
> - **1 (scope before ranking, no disclosure): pass.**
>   - FR-10's scheme is built for the document's audience through scoped_documents and scoped_meetings (...\apps\documents\classification.py:101-185).
>   - FR-19's check of Administrator scope runs only in the Administrator-only cycle. Nothing records a row that was left out.
> - **4 (server-side authorisation): pass.** FR-10 checks contribute_content after the scoped 404 on all six routes. FR-19 checks review_knowledge_gaps on all three routes, and on the dashboard key through role_holds.
> - **7 (two no-answer paths): pass.** Path B is aggregated (test_knowledge_gaps.py:444).
> - **8 (a failed AI step never discards the source): pass.** test_classification_hook.py:88 and 110; a failed cycle rolls back.
> - **9 (atomic ingestion): pass.** test_classification_hook.py:73.
> - **10 (structured output or nothing): pass.** Non-conforming replies are retried to MAXIMUM_CLASSIFY_ATTEMPTS, then the route answers 503.
> - **Set-level checks: pass, with two observations.**
>   - No AI SDK is imported outside apps/ai in either worktree.
>   - No inline threshold literals.
>   - FR-10 and FR-19 write no chunks.
>   - `MAXIMUM_TAG_SUGGESTIONS = 8` sits in apps/ai/classification.py:82, following GENERATION_MAX_TOKENS' precedent.
>   - KnowledgeGap stores `embedding_model` but not a dimension; it is not a chunk.
>
> ### CLAUDE.md §8, per requirement
> | Condition | FR-10 | FR-19 |
> |---|---|---|
> | 1. Behaves as the FR section says | No (gaps 1–5) | No (gap 11) |
> | 2. Both suites; both roles; UI-only clauses tested in the front end | CI green on 6357fe0; both roles covered; truncation notice untested | Not shown at HEAD (gap 13) |
> | 3. Happy path and a failure path | Yes | Yes |
> | 4. Committed with the FR ID | Yes | Yes |
> | 5. requirements-auditor reports no gaps | No | No |
>
> ### Gate impact
> - Neither requirement is in the M6 twelve.
> - The MUSTs this work touches:
>   - FR-08: Objective 02's 60-second bound is not re-timed (gap 9).
>   - FR-14: the Administrator's dashboard gains a key; this is tested.
>   - FR-12: search.py was refactored for search_total. FR-12's tests passed in the full run before the rule change, and that change did not touch search.py.
> - Smallest fixes:
>   - **FR-19:**
>     - Correct the three stale passages (gap 12).
>     - Commit a schedule or record on-demand only (gap 11).
>     - Merge d3a9892, run both suites and open the PR (gap 13).
>     - Add a note to D-69.
>   - **FR-10:**
>     - Record that the summary will not be built, or build it (gap 1).
>     - Make a tag removal durable (gap 3).
>     - Add a person-applies-a-tag route, or record its absence (gap 4).
>     - Record the Tags Delete and deactivation gap (gap 5).
>     - Add one front-end test (gap 6).
>     - Correct D-105 (gap 7).
>     - Re-time Objective 02 (gap 9).
>
> ### Could not verify
> - **The test counts.** I did not run them. FR-10's are corroborated by PR #70's body and green CI. FR-19's full suite at 45d5c25 is unknown.
> - **The reference set's 8 November approval.** Its earliest commit is 9 November.
> - **The deletions between runs.**
> - **That the twenty were not consulted during the development sweeps.**
> - **Live interface behaviour.** I read the code and the tests only.
> - **Determinism.** The sweeps vary across repetitions at temperature 0 (X06, X15, and X07's first repetition failed), so the 60% is one draw. A 15-point shortfall makes it unlikely that a second draw would change the verdict.
> - **Outside the FR text, not counted as gaps:** UC-09 E1's queue and A1's "undetermined" record; UC-10 E2 (sensitive questions kept verbatim), E3 (spurious questions), A2 (outdated knowledge) and A3 (partial answers). None of these is recorded.
>
> **One line:** FR-10 INCOMPLETE, FR-19 INCOMPLETE, Objective 05 NOT MET (clause 1), Objective 06 NOT MET on its independent run (clause 3).

**Dated note, 10 November 2026 (night): the tag corrections were re-audited twice, and both verdicts
are recorded here verbatim.** Two `requirements-auditor` runs, read only, on
`feat/FR-10-tag-corrections`, after this entry's decisions on findings 3, 4, 5, 6 and 10 were built,
together with two rounds of security fixes (D-105's dated note of the same night). Each verdict is
recorded here, rather than left in a terminal, for the reason this entry gives.

| Run | At | Its one line | What followed |
|---|---|---|---|
| First | `5377e3a` | The tag corrections INCOMPLETE. Findings 4, 5, 6 and 10 MET. Finding 3 PARTIAL: a tag a person applied came back on the next classify after it was removed, untested and unrecorded. Neither suite shown passing at that commit | Finding 3 took the auditor's option (a) in `88a488d`: a person's removed link is kept, as an AI link is (D-105's dated note). The stale passages it listed were corrected or marked in place in the same commit. The suites at `5377e3a`, run while it audited: pytest 3031 passed on a fresh test database, dual-role matrix 36/36; npm test 353 passed; lint and build clean |
| Second, focused | `88a488d` | Findings 3, 4, 5, 6 and 10 MET. Not ready to merge, for two contradictions in the contract (D1, D2) and one trivial wording (D3), all in the docs. FR-10 overall INCOMPLETE only for reasons already decided | D1 to D3 fixed, and its three optional tests added, in `ece4f32`. That commit has not been re-audited. The suites at `88a488d`: pytest 3043 passed on a fresh test database, matrix 36/36; npm test 353 passed; lint and build clean |

**Where FR-10 stands.** As a requirement it is INCOMPLETE, by decision: the summary, key points,
sectioned summarising and grounding are not built (D-104's dated note), and the tag browser is FR-15's
facets plus an Administrator-only inventory (D-105). The tag corrections decided on 10 November are MET
on the second audit, with the doc corrections it asked for made after it.

**The first re-audit, verbatim** (at `5377e3a`).

> ## Audit: FR-10 tag corrections (D-119 findings 3, 4, 5, 6, 10), feat/FR-10-tag-corrections at 5377e3a, 10 November 2026
>
> **One line:** The tag corrections are INCOMPLETE. Findings 4, 5, 6 and 10 are MET. Finding 3 is PARTIAL: a tag a *person* applied still comes back on the next classify after it is removed. Neither suite has been shown passing at 5377e3a. FR-10 overall is INCOMPLETE.
>
> **Verdict:** INCOMPLETE
>
> Method: read only. I ran no pytest, npm, manage.py or migration. I checked against FR-10's text in `C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype\proposal.txt` (lines 681-697) and UC-09 A3 (lines 2067-2070). All code paths below are under `C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506\`, and I give each one in full.
>
> ---
>
> ### Finding 3: a removed AI tag comes back. **PARTIAL**
>
> **What is met: the case D-119 named, an AI link.**
> 1. **Behaviour.**
>    - `reject_tag` keeps an AI link with `removed=True`, leaving its confidence and provisional flag alone: `C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506\apps\documents\classification.py:614-637` (633-635).
>    - `_link_tag` leaves a removed link alone (same file, 534-537).
>    - A Topic removed from a document is not proposed for it again (432-437, 452-453).
>    - `_link_on` treats a removed link as not found (835-854, `removed=False` at 846).
>    - Every FR-15 read excludes removed links: `C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506\apps\api\repository.py:181, 215, 239, 293`. I checked every other reader of `ContentTag`: only the `classify_documents` record lists removed links, and it flags them.
>    - The column comes from `documents 0009`.
> 2. **Error paths.** A removed link's id gets the same 404 body as an unknown id, on both confirm and remove. The DELETE route keeps its 204.
> 3. **Both roles.** All 11 tests in `C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506\apps\api\tests\test_fr10_removed_tags.py` use `session_client`, which is parametrised over `ROLE_NAMES` (`C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506\conftest.py:270-275`):
>    - keep: 106
>    - 404: 130-140
>    - the four reads: 146-163
>    - re-classify: 169-185
>    - reprocess: 188-215
>
>    The unit tests are in `C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506\apps\documents\tests\test_classification_removal.py` (6 tests, 8 cases).
> 4. **Front end.** No interface change was needed: the URL and the 204 are unchanged. Existing Remove tests are at `C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506\frontend\tests\documentClassification.test.jsx:575, 583, 889`.
> 5. **Happy path and failure path:** both tested.
>
> **What is not met: the correction clause (proposal.txt:692; UC-09 A3 step 3, :2070) for a link a person applied.**
> - `reject_tag` deletes a person's link (classification.py:636-637). Nothing then records that a person took that value off the document.
> - So the next classify route call, reprocess or `manage.py classify_documents` that suggests the value creates it again through `_link_tag`'s create branch (classification.py:524-533), now as `applied_by="ai"`:
>   - at or above the threshold it is applied: in `tags`, in the facets, a filter hit, labelled "Suggested by AI";
>   - below it, it is held and the person is asked again.
> - This covers every D-74 seeded link, which is a person's link, and every link the new apply route makes.
> - The interface offers Remove on a person's tag (`C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506\frontend\src\components\Classification.jsx:253-261`). It offers "Classify now" only on an unclassified document, but the classify route and the command re-run on any document.
> - **No test covers this.** The only person-removal tests are `C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506\apps\documents\tests\test_classification_confirm.py:202-209` and test_fr10_removed_tags.py:115-127, and neither re-classifies.
> - **It is not recorded.** D-105's note (`C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506\docs\decisions.md:6977-6978`) gives the choice ("it holds no machine assignment to keep"). That reason answers the clause's machine-assignment half, not its "not overwritten by later reprocessing" half.
>
> **Smallest fix (the lead's decision).** Either:
> - **(a)** Have `reject_tag` mark a person's link `removed=True` too. `_link_tag`, `removed_topics` and `_apply_link` already handle a removed row correctly. This changes some expected results:
>   - the apply–remove–apply tests' third code goes from 201 to 409, for the new name and the restricted name alike, so the two answers stay identical and the oracle stays closed;
>   - the two person-removal tests change.
> - **(b)** Record it in D-105 as an accepted deviation from the correction clause.
>
> Add a test either way: remove a person's link, then classify with that value suggested.
>
> ---
>
> ### Finding 4: a person cannot apply a tag. **MET** (open items are recorded)
> 1. **Behaviour.**
>    - `POST /api/documents/{id}/tags`: `C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506\apps\api\urls.py:49`, `C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506\apps\api\views.py:1503-1543`, classification.py:640-695, and `_apply_link` at 725-760.
>    - `tag_options` on the detail: `C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506\apps\api\serializers.py:220, 243` and classification.py:233-283.
>    - A new link is `applied_by "user"`, confirmed, confidence null, and gets 201. An existing link gets 200: a held one is confirmed, a removed one restored, an applied one left alone.
>    - A person's link is shown "Added by a person" (Classification.jsx:226-230).
> 2. **Error paths.**
>    - 401: the route walk in `C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506\apps\api\tests\test_rbac.py:167-177`.
>    - The scoped 404, then the 403: `ROUTES` in `C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506\apps\api\tests\test_document_classification.py:130-140`, used at 263-307.
>    - In `C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506\apps\api\tests\test_fr10_person_applied_tags.py`:
>      - one 400 body for an unknown, inactive, withheld or Department tag: 145-165;
>      - shape 400s: 303-324;
>      - another dimension: 291-300;
>      - the 409 with `tag_id`: 240-251;
>      - an existing Topic outside the scheme answered byte for byte as a new one: 254-288.
> 3. **Both roles.** That file uses `session_client` throughout, except:
>    - the Administrator mirror (358-368);
>    - the function-level guard (371-376);
>    - two Employee oracle sequences (393-412, 428-461), whose mirror runs from both roles (415-425).
> 4. **Front end.** documentClassification.test.jsx:970-1283 has 14 tests:
>    - the chooser, its 201 and the re-read of options;
>    - a 200 worded differently from a 201;
>    - a new Topic sent single-spaced;
>    - the client-side checks;
>    - the 409 selecting the tag and moving focus, and re-reading options without showing backend text;
>    - a 400 on each field;
>    - an empty dimension;
>    - a name rendered as text;
>    - a 403 removing the control;
>    - a 404 and a network failure;
>    - the 409 sentence tied to views.py.
> 5. **Happy path and failure path:** both tested.
>
> **FR-10's 409 (proposal.txt:695)** is answered only for a Topic already in the document's scheme. An existing Topic outside the scheme is linked and answered 201. **Declined in part, D-105** (decisions.md:7034-7044), for invariant 1. I checked the stated reason against the code and the byte-for-byte test, and it holds. No duplicate row is created in either case (get_or_create, classification.py:693).
>
> **Open items, recorded:**
> - the route is unthrottled (decisions.md:7232-7234);
> - an Employee can reactivate a Topic the Administrator retired (residual 6, 7241-7244), which weakens finding 5 for Topics;
> - names that differ only by look-alike Unicode get past the 409 (residual 9, 7251-7254).
>
> ---
>
> ### Finding 5: nothing deactivates or deletes a tag. **MET**
> 1. **Behaviour.**
>    - `GET /api/tags` and `DELETE /api/tags/{id}`: urls.py:92-93; views.py:1614-1649; `C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506\apps\documents\taxonomy.py:38-94`.
>    - A tag referenced in any state is deactivated and answered 200 with its entry; an unreferenced tag is deleted, 204. The tag row is locked for the check (taxonomy.py:80-87).
>    - A retired tag stays on the documents that carry it and leaves `tag_scheme` and `tag_options`. That is "preserving historical classification".
>    - `manage_tags` goes to the Administrator alone (accounts 0008).
>    - `ContentTag` is the only foreign key to `Tag` (`C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506\apps\documents\models.py:185`), so the reference check is complete.
> 2. **Error paths**, in `C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506\apps\api\tests\test_fr10_tag_administration.py`:
>    - 401: 96-97;
>    - 403 before the lookup: 83-93, 140-152, 198-206;
>    - 404 for an unknown tag and for a Department tag: 198-218;
>    - 200 again for a tag already retired: 186-195.
> 3. **Both roles.** Tests at 83, 140, 198, 224 and 250 use `session_client`. The Administrator-only behaviour tests (100, 155, 186, 209) are matched for the Employee by the 403 tests. The seed test holds every holder of `manage_tags` to the Administrator's scope: `C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506\apps\accounts\tests\test_manage_tags_seed.py:120-133`.
> 4. **Front end.** `C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506\frontend\tests\tags.test.jsx` has 14 tests covering:
>    - the list: order, count, name as text;
>    - the confirmation's wording;
>    - the rows and notices after a 200, 204 and 404;
>    - one DELETE per confirmation;
>    - a 403 withdrawing every action;
>    - a 500 in fixed words;
>    - the empty, loading, failed and retry states, and a 403 on the list;
>    - the guards for each role.
> 5. **Happy path and failure path:** both tested.
>
> **Note:** a retired Project or Process tag has no way back except the shell. A reactivation route was declined (decisions.md:7107-7111).
>
> ---
>
> ### Finding 6: the truncation notice had no front-end test. **MET**
> documentClassification.test.jsx:285-299:
> - `input_truncated: true` shows `TEXT.classificationTruncated`;
> - `false` does not, and the test checks the assignments rendered so the absence is real.
>
> The component is Classification.jsx:818-820. This clause belongs to the interface alone, so no server test is needed.
>
> ---
>
> ### Finding 10: the department label and the stale comment. **MET** (with a recorded residual)
> - **Server.** `documents 0009` adds `department_applied_by`. It is set by rule 3 (classification.py:401-422, `_department_provenance` at 497-513) and by `confirm_classification` (588-596), and serialised at serializers.py:301.
> - **Both roles.** test_fr10_removed_tags.py:221-256 checks the classify, confirm and detail replies. The unit tests are in `C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506\apps\documents\tests\test_classification_department_provenance.py` (9 tests, 10 cases).
> - **Front end.** Classification.jsx:150-158. documentClassification.test.jsx:301-327 tests three cases:
>   - `"user"` reads "Given by a person…" and not "Suggested by AI";
>   - `"ai"` and `null` keep "Suggested by AI".
> - **Stale comment.** Fixed at `C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506\apps\core\constants.py:219-222`, which now carries §5's "1 initial call + 2 retries", and in `C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506\apps\core\tests\test_constants.py:145-146`.
> - **Residual, recorded** (decisions.md:7010-7016):
>   - rows classified before 0009 read `null`, so they keep the old mislabel until their next run or confirmation;
>   - a department a run wrote into a blank before 0009 reads `"user"` after its next run.
>
>   The note's "should hold none" covers the Objective 05 twenty only, checked against git history. Other databases are not addressed.
>
> ---
>
> ### FR-10 overall, after this branch
> | Clause | Status |
> |---|---|
> | 683 type and department, AI-marked, editable | Satisfied (label fixed) |
> | 684 summary and key points | **Declined, D-104** (dated note, 10 Nov night) |
> | 685 four dimensions shown separately | Satisfied |
> | 685 tag browser | **Partial, recorded (D-105).** An Administrator-only inventory now lists every value with its count; Employees still have FR-15's scoped facets |
> | 687 one request returns classification, summary and tags | Partial: no summary (**D-104**) |
> | 688 fixed type list; unique names | Satisfied (residual 9 accepted) |
> | 688 sectioned summarising | **Declined, D-104.** The notice is now tested in the front end |
> | 689, 690 | Satisfied |
> | 691 provenance | Satisfied |
> | 692 correction | **Partial, unrecorded** (finding 3's residual) |
> | 693 grounding | **Declined, D-104** |
> | 694 deactivate rather than delete | Satisfied |
> | 695 the 200 | Partial: no summary (**D-104**) |
> | 695 the 409 | Satisfied for an offered name; **narrowed by D-105** for invariant 1 |
> | 695 the 422 | Satisfied |
> | 697 CRUD | Satisfied. Tags Delete now exists. Removing an AI link is a soft delete, as the correction clause requires |
>
> ### Decision log and contract against the code
> **Accurate**, checked against the code:
> - the guard order;
> - the one-body 400;
> - the 409 rule and the byte-for-byte 201;
> - the new link's fields and the 200 cases;
> - "no read lists a removed link";
> - `tag_options` is `tag_scheme`'s tags;
> - the final `tag_scheme` rule (classification.py:208-212), as the contract's `tag_options` bullets state it;
> - `grown` is set only on create or reactivate (`_bring_into_use`, 698-722), by 0011 and by the seed script's linked mode;
> - 0011's frozen literals equal constants.py:531-545, and its overlap predicate matches `C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506\apps\retrieval\scoping.py:114-126`;
> - the `DELETE /api/tags` semantics and `manage_tags`;
> - `docs\schema-v1.md`'s rows for `grown`, `removed` and `department_applied_by`.
>
> **Stale or wrong: the docs claim what the code does not do.**
> 1. **decisions.md:7060-7069** (D-105 note, the `tag_options` bullet) says:
>    - "A linked value is offered only if every role in the audience reads a source carrying it";
>    - "true of linked values only… holds for unlinked tags that are not grown".
>
>    Since 824c536, a tag that is not grown is offered whatever its links. By design, that includes a seeded value carried only by Administrator-only material. Neither sentence was corrected in place, unlike the two that 824c536 did correct (7149-7150, 7154-7156). Add a dated line.
> 2. **decisions.md:7128-7134** states 84b5771's rule ("…or if nothing links it and it is not grown") with no superseded marker. The code follows the vocabulary rule at 7192-7196.
> 3. **decisions.md:6985-6988.** The reason given for counting a removed link ("would turn a value… into vocabulary") no longer holds under the final rule. The behaviour itself is still true.
> 4. **decisions.md:7036-7038** leaves out a grown Topic that nothing links. classification.py:652-655 and the contract both include it.
> 5. **decisions.md:6968** says "server side only; the interface half follows". The interface has landed (1641693, c6f59d4, 607feaa, 4d53cb7), and the note does not say so.
> 6. **`C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506\frontend\src\api\documents.js:220`** says "Nothing in it is on material a reader… may not see". That is false for vocabulary linked on restricted material. The contract's wording, "discloses nothing", is the right one.
> 7. **`C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506\apps\documents\tests\test_classification_scheme.py:4-7`**: the module docstring states the original rule.
>
> **The reverse: the code does what the docs do not say.** Finding 3's residual. The contract truthfully says a person's link "is deleted", but not that reprocessing then brings it back.
>
> **Trivial.** The contract lists a `dimension` 400 only for "a dimension other than Topic". A missing `dimension` gives the same key (serializers.py:411).
>
> ### Migrations
> - **documents 0009** is additive: two AddFields, plus a RunPython that does nothing forwards. It is reversible, tested through the executor (`C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506\apps\documents\tests\test_migration_0009_tag_corrections.py:72-116`). The reverse deliberately deletes removed links (decisions.md:7235-7240).
> - **The 0009 edit in place (880448b) is consistent with §7's wording.** §7 forbids editing a *pushed* migration.
>   - No remote-tracking ref contains eb203ba, 880448b or 5377e3a. The only FR-10 remote branch is `origin/fix/FR-10-objective-05` at 6357fe0.
>   - The appended operation does nothing forwards.
>   - The edit is logged in the docstring (lines 26-29) and in D-105.
>   - "Applied only to test databases" cannot be verified, and does not matter given the no-op forward.
>   - Note: the worktree `C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506-fr19` sits at 8c06f13, which has the 0009 from before the edit.
> - **documents 0010** is one AddField, reversible and tested.
> - **documents 0011** is a data UPDATE with a no-op reverse. Django can reverse it, and the test asserts the marks survive the reverse. It is not strictly additive, and reversing it does not restore the old values. The docstring explains why, and I confirmed that direction is safe for invariant 1. Its new dependency on meetings 0002 creates no cycle.
> - **accounts 0008** has a real reverse, tested through the executor (test_manage_tags_seed.py:81-117).
>
> ### Overstatement
> - **Test counts in the commit messages match the files:** 11/22, 6/8, 9/10, 13/38, 14 and 14. The npm totals (322, 325, 339, 353) are consistent with the tests added.
> - **Run claims are honest, and they show the gap.**
>   - The last full pytest run is claimed at 11a610f: 2965 passed, matrix 36/36.
>   - Every later commit claims targeted runs only: 728, 422, 789, 796, 108.
>   - npm is last claimed at 4d53cb7: 353 passed.
>   - So **at 5377e3a neither suite is shown, and CI has not run**: nothing is pushed, and there is no PR.
> - The "every test failed under a deliberate break" claims cannot be verified read-only.
> - I found no other overstatement.
>
> ### Invariant check
> - **1 (no disclosure): pass**, on what I read. The one-body 400, the byte-for-byte 201, the apply–remove–apply tests and the vocabulary-movement tests (`C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506\apps\api\tests\test_fr10_tag_vocabulary.py`) all support it.
> - **3 (meetings by role): pass.** Meetings are scoped through `scoped_meetings`.
> - **4 (server-side authorisation): pass.**
> - **8 and 9: pass.**
> - **2, 5, 6, 7 and 10:** not applicable.
> - **Set-level: pass.**
>   - No AI SDK is imported outside `apps/ai`.
>   - No tuned literal sits inline. The front end's `TAG_NAME_MAXIMUM_LENGTH = 255` is tied by pytest to `NAME_MAX_LENGTH`.
>   - This slice writes no chunks.
>   - Nothing is enforced only in the interface.
>   - 0011 and the seed script's `mark_restricted_only_values_grown` compute the same set in two places. That is necessary, because a migration cannot import app code, and each is tested.
>
> ### CLAUDE.md §8
> | | 3 | 4 | 5 | 6 | 10 |
> |---|---|---|---|---|---|
> | 1. Behaves as specified | No (person-link residual) | Yes | Yes | Yes | Yes |
> | 2. Both suites pass, both roles, front-end tests where needed | Both roles and tests exist; **passing not shown at HEAD** | same | same | same | same |
> | 3. Happy path and failure path | Yes | Yes | Yes | Yes | Yes |
> | 4. Committed with the FR ID | Yes | Yes | Yes | Yes | Yes |
> | 5. Auditor reports no gaps | No | Yes | Yes | Yes | Yes |
>
> ### Gate impact
> - FR-10 is not in the M6 twelve, and M6 has passed.
> - The branch does change FR-15 (a MUST):
>   - every repository read gains `removed=False`;
>   - `GET /api/documents/{id}` now computes `tag_scheme` for every reader, and its cost grows with the total number of links (residual 11).
> - FR-15's regression evidence at HEAD is targeted runs only until the full run finishes.
>
> **Smallest fixes:**
> 1. Decide finding 3's residual and add its test.
> 2. Add dated corrections to D-105's stale lines (items 1-5 above).
> 3. Run full pytest and npm at 5377e3a, then open the PR so CI runs.
>
> ### Could not check
> - Any test result. The full run was in progress, and I did not read its output.
> - The deliberate-break claims.
> - Any database: where 0009 was applied, and the pre-0009 rows.
> - Live interface behaviour.
> - Pushes from another clone.
>
> **One line:** The tag corrections are INCOMPLETE: findings 4, 5, 6 and 10 are MET, and finding 3 is PARTIAL because a removed person's tag returns on re-classification, unrecorded and untested. Neither suite is shown passing at 5377e3a. FR-10 overall is INCOMPLETE.

**The second re-audit, verbatim** (at `88a488d`).

> ## Audit: FR-10 tag corrections, follow-up on finding 3 at 88a488d (10 November 2026)
>
> **Verdict.** Findings 3, 4, 5, 6 and 10 are MET against FR-10's text at 88a488d, but the branch is not ready to merge: 88a488d left the contract contradicting itself in two places (defects D1 and D2 below). Both are doc-only fixes. Finding 3 now satisfies the correction clause and is tested from both roles. Findings 4, 5, 6 and 10: 88a488d changed only docstrings on their paths, so they stand as MET from my 5377e3a audit. FR-10 overall stays INCOMPLETE, and only for reasons already decided: the summary clauses the user declined (D-104's dated note) and the recorded tag-browser deviation (D-105). I did not run or see the suites at 88a488d.
>
> Read-only throughout. HEAD is 88a488d and the tree is clean. Root: C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-obj0506
>
> ---
>
> ### Check 1: finding 3 against proposal.txt:692 and UC-09 A3 — MET
>
> proposal.txt is at C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype\proposal.txt. Line 692 says a user's value "is not overwritten by later reprocessing". UC-09 A3 (lines 2071-2074) says "retains both" and "The corrected classification governs how the document is found from that point".
>
> | Clause | Status | Evidence |
> |---|---|---|
> | `reject_tag` keeps a person's link, marked removed | Satisfied | ...\apps\documents\classification.py:632-635. Every link is set `removed=True`; there is no longer a branch on `applied_by`. The route still answers 204 (...\apps\api\views.py:1546-1562). Test: ...\apps\api\tests\test_fr10_removed_tags.py:119-137 checks the same pk, `removed`, `applied_by` "user" and empty `tag_details`. Unit test: ...\apps\documents\tests\test_classification_confirm.py:202-212 |
> | A later classify does not link it again | Satisfied | The route (views.py:1428) calls `classify_document_now`. An in-scheme suggestion reaches `_link_tag` (classification.py:443-449), which finds any existing row, removed ones included (519-523), and returns a removed one untouched (534-537). The create branch (524-533) runs only when no row exists. `tag_scheme` counts removed links (195-200 has no `removed` filter), so a typed grown Topic stays in its own document's scheme. Test: test_fr10_removed_tags.py:248-285, classify case, for a seeded Process value and a typed Topic |
> | …and does not propose it again | Satisfied | An in-scheme suggestion stops at line 449. An out-of-scheme Topic (retired, or withheld from the scheme) is skipped through `removed_topics` (432-437, no `applied_by` filter; skip at 452-453). The test asserts there is no proposal (test_fr10_removed_tags.py:283-285) |
> | A reprocess does not undo it | Satisfied | Reprocess deletes only `ExtractedContent` and chunks, never `ContentTag` (...\apps\ingestion\documents.py:181-184), then classifies through `classify_document_now` (:323). Test: the same test's reprocess case asserts one classify call |
> | A `classify_documents` run does not undo it | Satisfied by construction; no test for a person's link | ...\apps\documents\management\commands\classify_documents.py:221 calls the same `classify_document_now`. Its own test covers a removed AI link only (...\apps\documents\tests\test_classify_documents_command.py:166-185) |
> | Re-applying restores the link | Satisfied | The restore branch of `_apply_link` (classification.py:740-748) returns `created=False`, which the view answers 200 (views.py:1542). Test, both roles: ...\apps\api\tests\test_fr10_person_applied_tags.py:423-447 asserts 201, 204, 409, then 200 by `tag_id` with the same pk, `removed` False, `confirmed` True and `applied_by` "user". Re-applying by name is a 409 that names the tag; the screen then selects it so one press restores it (...\frontend\src\components\Classification.jsx:691-699, 721-733) |
> | Nothing else overwrites the removal | Satisfied | `ContentTag` rows are deleted only with their source: ...\apps\documents\deletion.py:75-77 and ...\apps\meetings\deletion.py:72-74. The seed script's `get_or_create` (...\scripts\seed_objective02_tags.py:122-127) finds a removed row and leaves it removed |
> | Reads exclude a person's removed link | Satisfied | Every reader filters `removed=False` whatever `applied_by` says: ...\apps\api\repository.py:174-185, 208-216, 236-240 and 288-300, and ...\apps\documents\taxonomy.py:53 |
> | The change is recorded | Satisfied | D-105's closing bullet (...\docs\decisions.md:7315-7342), the contract's DELETE row (...\docs\api-contract.md:1082), and ...\docs\schema-v1.md:237 and 253-261 |
> | Tested from both roles, happy path and a failure path | Satisfied | `session_client` runs every test as both roles (...\conftest.py:270-275). Failure paths from both roles: the 409 on re-applying by name (test_fr10_person_applied_tags.py:423-447), and the 404 for confirming or removing a link that is already removed (test_fr10_removed_tags.py:140-150). That 404 test uses an **AI link only**. A person's link goes through the same filter (classification.py:845) but has no 404 test of its own. Minor gap |
>
> Reading the code, the new classify/reprocess test would fail at 5377e3a: the Topic case would propose "night shifts", and the Process case would create an AI link. I did not re-run the commit's mutation checks.
>
> ### Check 2: the stale passages
>
> | Passage (5377e3a line numbers) | At 88a488d |
> |---|---|
> | decisions.md 6968, "server side only; the interface half follows" | Marked at 6970-6971. The four commits it names (1641693, c6f59d4, 607feaa, 4d53cb7) each touch `frontend/`. Accurate |
> | 6985-6988, counting a removed link "for invariant 1" | Marked at 6993-6997. The new reason matches `tag_scheme` (classification.py:208-212) |
> | 7036-7038, what an out-of-scheme Topic can be | Marked at 7047-7051. Matches the code and the `apply_tag` docstring (classification.py:648-653) |
> | 7060-7069, "linked value" | Marked at 7083-7087. Acceptable. The substitution it asks for is loose: "readable through no source at all" doesn't fit every non-grown tag, and the heading "every value in it is readable" is still broad. The next bullet qualifies both |
> | 7128-7134, the rule change | Marked superseded at 7158-7161. Accurate |
> | frontend\src\api\documents.js:220 | Corrected. It now matches the `tag_options` docstring (classification.py:250-261) |
> | Module docstring of test_classification_scheme.py | Corrected. It matches the fixtures: grown Project at line 80, grown held Topic at line 86. It omits the retired-Project fixture at line 89, which is harmless |
> | The contract's 400 for a missing dimension | Corrected at api-contract.md:1083. Matches serializers.py:411-412. The test checks only the status code, not the `dimension` key (test_fr10_person_applied_tags.py:308, 315-324). Minor gap |
> | The four more passages 88a488d marked: person link deleted (6978), the residual (7088), the oracle's step 2 (7137), the review's finding 1 (7202) | All four marked: at 6981-6983, 7096-7098, 7137-7138 and 7203-7205 |
>
> ### Check 3: contradictions or overstatement 88a488d introduced
>
> **What holds:**
> - **The oracle stays closed.** All three variants answer 201, 204, 409 and list the name in `tag_options` after the removal. That works because the document's own removed link counts, and `scoped_documents` has no status filter (...\apps\retrieval\scoping.py:143-159), so every role in the audience reads the document. I also traced a retired Topic that restricted material still links, and it gives the same answers. The options before step 1 are the same in every variant. The 409's `tag_id` is a uuid4 the Employee has never seen in any other reply.
> - **`DELETE /api/tags/{id}` with only removed links answers 200 and deactivates the tag, and the contract says so.** api-contract.md:1201 says any reference "in any state (held and removed links included)", and `item_count` excludes removed links (:1210-1211). The new test is ...\apps\api\tests\test_fr10_tag_administration.py:198-214. The Tags page already expects this (...\frontend\src\pages\Tags.jsx:97-105).
>
> **Defects:**
>
> **D1. The contract's "Removed links" paragraph still describes AI links only.** api-contract.md:1179-1183 reads "An AI link a person removed is in **no** read … It stays in the database only so that the machine's assignment is kept beside the person's decision." That contradicts the DELETE row at :1082 and D-105's closing bullet. A person's removed link has no machine assignment; it is kept so that a later run neither links it again nor proposes it. The same stale wording is in:
> - ...\apps\api\repository.py:43-46 and :208
> - ...\apps\core\tests\test_schema.py:83-84
> - ...\apps\documents\migrations\0009_fr10_tag_corrections.py:3 (a historical description; fixing it is optional)
>
> Fix: cover both kinds of link, and give both reasons.
>
> **D2. The claim that a retired Topic, typed again, is answered 201 no longer holds on an ordinary path.**
> 1. A person types T on document D: 201.
> 2. They remove it: 204, and the link is kept.
> 3. The Administrator deletes T on the Tags page. It shows `item_count` 0, but the removed link still references it, so the answer is 200 and T is deactivated. Before 88a488d this was 204 and T was gone.
> 4. The person types T on D again:
>    - classification.py:690-694 fetches the inactive T;
>    - `_bring_into_use` reactivates it (711-721);
>    - `_apply_link` restores the removed row (740-748);
>    - the answer is **200**.
>
> These places still say 201:
> - api-contract.md:1163-1165 ("or inactive) is linked and answered `201` exactly as a new Topic is") and :1219-1221
> - decisions.md:7053 and 7128-7129
> - classification.py:655-656
> - the docstring at test_fr10_tag_administration.py:270-272. The test itself types the name on a different document (`other`, :275-287), so it cannot catch this.
>
> Nothing is disclosed: the 200 depends only on D's own links, which the caller can read. Fix: add "unless this document already holds a link to it, live or removed, which is restored: 200" to each statement, and optionally add a test for the same-document sequence.
>
> **D3. Trivial wording.** "disappears only when the last such source is deleted" (api-contract.md:1155; classification.py:266-268). The "only" leaves out retirement, which is stated nearby at :1151 and :1158.
>
> **Usability (not an FR-10 clause).** Restoring a removed tag is now the normal result of re-adding one a person just removed. The screen announces it as "“X” was already on this document and is among its tags." (...\frontend\src\constants.js:647, chosen at Classification.jsx:657). The models.py comment says a removed link "is no longer a tag of its document".
>
> I found no other contradiction in the code, in schema-v1.md, or in the front-end client's comments (documents.js:311-330 already describes the 200 restore).
>
> ### Check 4: suites
> I did not run them, as instructed, and I cannot see the run in progress, so I am not counting it as a gap. Two things I could check by reading:
> - 88a488d changes only comments in models.py, so it should not affect migrations.
> - No test outside the files 88a488d changed expects a person's removed link to be deleted. The removal tests elsewhere all use AI links: test_document_classification.py:429-441, test_fr15_reads_exclude_provisional.py:79-90 and test_classify_documents_command.py:166-185.
>
> ### Invariant check
> - 1 (filter before ranking, no disclosure): pass. `tag_scheme` is unchanged, the oracle stays closed, and D2's 200 depends only on a document the caller can read.
> - 4 (server-side authorisation): pass. No route changed; the order is still the scoped 404, then the 403 (views.py:1556-1557).
> - 9 (atomic writes): pass. `reject_tag` runs inside `transaction.atomic` (classification.py:632).
> - 8: not touched. No new literal constants in app code, no AI SDK import, no chunk writes.
>
> ### Gate impact
> FR-10 is a SHOULD for NIT3004 and not one of the M6 twelve, so there is no M6 impact. The smallest fix before merge is doc-only: rewrite api-contract.md:1179-1183 (D1) and add the qualification to the D2 statements. Optional additions:
> - a test for typing a retired Topic again on the same document;
> - a 404 test for removing a person's link a second time;
> - an assertion on the `dimension` key in the missing-dimension 400.
>
> ### What I could not check
> - pytest, npm test, lint, build, `makemigrations --check` and CI at 88a488d.
> - The commit's mutation checks ("breaks").
> - D2's 200 comes from tracing the code. I did not run it, and no test exercises it.

## D-120 · The relevance threshold and the partial-match floor are per embedding model: `voyage-4` gets 0.2687 and 0.2468, and EmbeddingGemma keeps 0.30 and no floor

**Status:** Settled by the user · **Date:** 2026-11-10 · **Concerns:** FR-12, D-37, D-56, D-101,
D-102, D-113, D-117, R10, `apps/core/constants.py`, `apps/retrieval/ranking.py`,
`apps/retrieval/partial_matches.py`, `apps/retrieval/pipeline.py`, `scripts/citation_harness.py`,
`scripts/conversation_http_check.py`, `CLAUDE.md` §5

**What prompted it.** D-113 requires the threshold to be re-derived on development material before
the `anthropic` provider is relied on. `RELEVANCE_THRESHOLD = 0.30` and `PARTIAL_MATCH_FLOOR = 0.0`
were chosen on EmbeddingGemma's scores (D-102). A cosine value means something only for the model
whose scores it was chosen on (R10).

**The measurement used D-101's and D-102's procedure, unchanged.** The evidence is in
`corpus/objective-02/runs/2026-11-10/voyage-threshold/`.

- **The database** is `kmp_voyage_20261110`, the 1 November snapshot re-indexed with Voyage (D-117,
  PR #71).
- **Scores:** dev-set-v2's 40 runs, each embedded three times, with D-101's margin rule
  (`m = 0.006`).
  - It gave T 0.2687 and F 0.2468.
  - It declines 4 of 8 no-answer runs with margin (EmbeddingGemma: 1 of 8) and keeps all 32
    answerable runs.
  - The floor holds (F ≤ T − m), which it could not on EmbeddingGemma.
- **End to end:** both values against 0.30 with no floor, on v2, with Claude Sonnet 5.5 (D-115)
  and the cap of 6. Every ask was rolled back.

| dev-set-v2 | EmbeddingGemma 0.30 (D-102) | Voyage 0.30 | **Voyage 0.2687 / 0.2468** |
|---|---|---|---|
| answered where expected | 29/32 | 31/32 | **32/32** |
| declined where no answer is expected | 7/8 | 8/8 | **8/8** |
| match with an expected source | 22/32 | 31/32 | **32/32** |
| median seconds per ask | 16.1 | 2.8 | **2.6** |

- **The difference between the two Voyage settings is u07,** whose expected source scores 0.2968.
  0.30 declines it before generation.
- **The floor stops unrelated offers.** At 0.30 with no floor, every no-answer run was offered its
  five nearest items, down to 0.12. At 0.2468, the four runs declined before generation were offered
  nothing.

**Decision (the user's, 10 November): adopt Voyage's values, as values of the embedding model.**

- **The tables:** `RELEVANCE_THRESHOLD_BY_MODEL = {"voyage-4": 0.2687}` and
  `PARTIAL_MATCH_FLOOR_BY_MODEL = {"voyage-4": 0.2468}`, in `apps/core/constants.py`.
- **The default:** a model not listed, EmbeddingGemma included, keeps `RELEVANCE_THRESHOLD = 0.30`
  and `PARTIAL_MATCH_FLOOR = 0.0`. Both are unchanged, so FLM's behaviour and its measurements are
  untouched.
- **The code:** `ranking.admit()` and `partial_matches.partial_matches()` take the embedding model as
  a required keyword and look the value up (`relevance_threshold`, `partial_match_floor`).
  - The pipeline passes the model the question was embedded with, which is the model every
    candidate chunk was recorded against (R10).
  - The keyword is required, so a caller cannot forget it and quietly use EmbeddingGemma's value
    for Voyage's scores.
- **The measurement scripts:** the citation harness and the HTTP check pass the model too. The
  harness's default threshold is now the model's own, and `--threshold` still overrides it.
- **The key is the model name the provider answers with** (`settings.VOYAGE_MODEL`). Another Voyage
  model falls back to the default until it is measured, because these values are `voyage-4`'s.

**What it costs, and what remains:**

- **A small, contaminated set.** It is 40 runs, and v2 was written after the frozen results were
  seen (D-101's note). So the frozen thirty does not independently test this value.
- **The scores still overlap.** Three no-answer runs score above an answerable one. Generation
  declined them on this set.
- **D-56 is narrowed on Voyage and stays open on EmbeddingGemma.**
- **Next:** the frozen thirty, the nine threads, the HTTP check and NFR-08 on Voyage with these
  values (D-113), within D-113's spend rule.
- **FR-19's exclusion check** (`scripts/exclusion_dev_check.py`, on its branch) calls `admit`, and it
  needs the model once the two branches meet.

**Where it applies:** the modules under **Concerns**, `CLAUDE.md` §5 (both rows, with the user's
adoption of 10 November) and `docs/ai-provider.md` §4.

## D-121 · Haiku 5.5 is the `anthropic` provider's default generation model, after it matched Sonnet 5.5 on every bar

**Status:** Settled by the user · **Date:** 2026-11-10 · **Concerns:** D-115, D-113, D-102, D-120,
FR-10, FR-12, FR-13, `config/settings.py`, `.env.example`

**Decision (the user's, 10 November):** `ANTHROPIC_MODEL` defaults to `claude-haiku-5-5` in
`config/settings.py` and `.env.example`, replacing D-115's `claude-sonnet-5-5`. The development
`.env` was changed to match. Sonnet stays one setting away: `ANTHROPIC_MODEL=claude-sonnet-5-5`.

- **Why:** the user asked whether Haiku could cut cost without losing performance. The Haiku round
  (`corpus/objective-02/runs/2026-11-10/haiku/haiku-round.md`) measured no loss. Haiku costs a
  twentieth of Sonnet per token ($0.10 / $0.50 against $2 / $10 per million) and was faster.
- **The bar was fixed before any Haiku call,** in `0f184ca`, from Sonnet's own results. Only the
  model changed: the embedder stayed Voyage `voyage-4`, with D-120's values, effort `"low"`, and
  the same database and dump.

| | Sonnet 5.5 | Haiku 5.5 |
|---|---|---|
| dev-set-v2 end to end: answered / declined / matched | 32/32 · 8/8 · 32/32 | 32/32 · 8/8 · 32/32 |
| frozen thirty: runs right | 34/34 | 34/34 |
| threads: follow-ups with history | 9/9 | 9/9 |
| fabricated identifiers, leaks | 0, 0 | 0, 0 |
| frozen thirty: answered question, median | 2.5 s | 1.7 s |
| Claude spend for the three sets | $1.04 | $0.055 |

- **D-115's call parameters stand.** They are effort `"low"`, thinking at the model's default, no
  sampling parameters, and `CLAUDE_MAX_TOKENS` 16000. Haiku was measured with them, and Haiku 5.5
  accepts all four.
- **Changing the generation model is not a re-index,** as D-115 says: the vectors are Voyage's.

**What it costs, and what remains:**

- **There was one behavioural difference.** Asked t02's follow-up cold ("How often does that get
  reviewed?"), Sonnet declined and Haiku answered from another document, with genuine citations.
  - Both score as not correct, and a cold follow-up is predicted to fail, so no bar moved.
  - It is still the failure the round was watching for: answering an underspecified question.
- **The sets cannot separate the two models further.** Both scored at the ceiling, each set ran
  once, and Claude takes no sampling parameters.
- **FR-10 classification moves to Haiku too, unmeasured.**
  - `classify_document` reads the same setting.
  - Classification has not been measured on either Claude model; FR-10's records (D-106) are
    FLM's.
  - Measure it, or give it a setting of its own, before relying on it on this provider.
- **NFR-08 has not run on either Claude model.**
- **The default provider is still FLM** (D-113). This decision sets the `anthropic` provider's
  model; it does not choose the provider.

**Where it applies:** `config/settings.py`, `.env.example` and the development `.env`. D-115
carries a dated note.

## D-122 · `anthropic` (Claude Haiku 5.5 + Voyage `voyage-4`) is the default provider, after FR-10's and FR-19's tuned values were re-derived on it

**Status:** Settled by the user · **Date:** 2026-11-10 · **Concerns:** D-113, D-114, D-117, D-120,
D-121, D-106, D-109, FR-08, FR-10, FR-12, FR-13, FR-19, `config/settings.py`, `.env.example`,
`.github/workflows/ci.yml`, `README.md`, `CLAUDE.md` §3 and §4

**Decision (the user's, 10 November):** `AI_PROVIDER` defaults to `anthropic` and
`EMBEDDING_DIMENSION` to 1024. This applies in `config/settings.py`, `.env.example` and CI. FLM stays
as the offline alternative: `AI_PROVIDER=flm`, `EMBEDDING_DIMENSION=768`, and a database indexed by
FLM.

**A measured switch, as `CLAUDE.md` §4 requires.** Every tuned value was re-derived on this provider
before the default moved:

- **Answers and retrieval:**
  - D-120's threshold and floor for voyage-4;
  - the frozen thirty (34/34), the nine threads (9/9 with history) and the HTTP check (WIRED 3/3),
    in #75 and #76;
  - Haiku 5.5 matching Sonnet 5.5 on every bar, in D-121.
- **The two values that were still FLM's, re-derived first by their own fixed rules (the user's
  choice):**
  - **FR-19's grouping threshold: 0.5054 for voyage-4,** where embed-gemma has 0.5256. This is
    D-109's rule on the development paraphrases, with 12 entries of 3 and none mixed (D-109's dated
    note).
  - **FR-10's confidence threshold: 0.72 for claude-haiku-5-5,** where gemma3:4b has 0.95. This is
    D-106's rule on the 19 development documents, with all 57 typed right (D-106's dated note).
  - **Both are per model** (`..._BY_MODEL`), as D-120's are. The code reads the value for the
    model that produced the vector or the classification, and FLM keeps its own values.

**The local setup (the user's choice): a fresh database, `kmp_anthropic`.**

- **How it was made:** restored from the 1 November snapshot (dump `3bf98403…`) with
  `restore --into`, migrated, and re-indexed by Voyage with `--resize-column`: 25 sources rebuilt,
  3 skipped as in every copy, 0 failed, 43 chunks.
- **Its files:** media in `C:\kmp-dev\kmp_anthropic\media`, and its own snapshot (dump `8e79cb37…`)
  in `C:\kmp-dev\kmp_anthropic\snapshot`, so it resets without a re-index.
- **The development `.env`** now points at it, on the `anthropic` provider at 1024. `kmp` is
  untouched and stays FLM-indexed at 768.

**CI runs on the default too:** `AI_PROVIDER=anthropic`, `EMBEDDING_DIMENSION=1024`. It holds no key,
so the startup check warns ("ANTHROPIC_API_KEY is not set") and calls nothing. The suite uses the
stub provider and passed locally under that configuration.

**What it costs, and what remains:**

- **The spend:** about $0.02 for FR-10's sweep (57 Haiku calls). The Voyage embeddings fall within
  its free allowance.
- **FLM databases are not converted.** These stay at 768 and run with `AI_PROVIDER=flm` and
  `EMBEDDING_DIMENSION=768`:
  - the alpha, `kmp_demo_20261101`;
  - the FLM measurement baseline, `kmp_obj02_20261101`;
  - `kmp_obj0506_20261101`;
  - `kmp`.

  A database moves across with `reindex --resize-column` (D-117), onto a copy.
- **`MAXIMUM_STATEMENTS` (6) was tuned on FLM's generation and is not re-swept.** On Claude, the
  development set and the frozen sets show no ceiling hit, no cap violation and no 503 at 6, with
  every expected answer matched. That is the rule's first test passing; caps 3 to 5 were not
  compared.
- **`MAXIMUM_CONTEXT_TOKENS` (4000, still PROVISIONAL) now binds on Voyage for broad questions.**
  The HTTP check's t04 and t06 had 21 and 22 passages above the threshold, of which 8 and 9 fit.
  Every result above was measured with it at 4000, so it stands. It is no longer untested merely
  because it never binds.
- **`TOP_K` (25) still does not bind.** The most passages seen above the threshold is 22.
- **NFR-08 has not run on this provider.** Its rate limits depend on the Anthropic account's tier.
- **Objectives 05 and 06 stay as verified, on FLM.** Re-running their verification on this provider
  is separate work.
- **Old gaps are not joined across the switch.** Open knowledge-gap entries written under
  embed-gemma are never joined by a Voyage vector (R10), so a recurring subject opens a second entry
  (D-109's note).

**Where it applies:**

- **Configuration:** `config/settings.py`, `.env.example`, `.github/workflows/ci.yml`.
- **Code:** `apps/core/constants.py` (the two maps), `apps/retrieval/gaps.py`,
  `apps/documents/classification.py`, `scripts/objective05_verify.py`.
- **Documentation:** `README.md`, `CLAUDE.md` §3 and §4, `docs/ai-provider.md`. D-106 and D-109
  carry dated notes.

## D-123 · A meeting recording is transcribed by Whisper on FLM into a draft that a person must confirm, then ingested through FR-09 unchanged; live transcription stays out of scope

**Status:** Settled by the user · **Date:** 2026-11-10 · **Concerns:** FR-09, the proposal's §1.9,
NFR-19, NFR-20, D-19, D-79, D-83, D-85, D-113, D-114, D-118, D-122, `apps/ai/base.py`,
`apps/ai/transcription.py`, `apps/ai/flm.py`, `apps/ai/anthropic.py`, `apps/ai/testing.py`,
`apps/ai/__init__.py`, `apps/ai/checks.py`, `apps/ingestion/audio.py`, `apps/api/views.py`,
`apps/api/transcription_slot.py`,
`apps/core/constants.py`, `config/settings.py`, `frontend/src/pages/Meetings.jsx`,
`frontend/src/components/RecordingTranscriber.jsx`, `frontend/src/utils/audio.js`,
`docs/api-contract.md`, `docs/ai-provider.md`, `README.md`, `CLAUDE.md` §4 and §5 · **Area:**
meeting intelligence, Sagarika Dey's (`CLAUDE.md` §1), built from Benjamin Morovan's session at his
request

**What prompted it.** On 10 November the user asked for the app to transcribe meetings with Whisper
on FLM. The proposal does not provide for that:

- **§1.9 "Out of scope"** lists "Live, real-time transcription during an active meeting" and
  "Native video conferencing/meeting recording capture (assumes recordings are uploaded)". The
  conclusion repeats that live meeting transcription was left out on purpose.
- **FR-09** takes "a transcript file or paste transcript text", and nothing else.

`CLAUDE.md` §1 says a behaviour the proposal does not contain is raised, not built, so it was put to
the user before any code.

**What was measured first** (6 November, FLM v0.9.39, the D-83 pin, model `whisper-v3:turbo`):

- **Setup.** `flm pull whisper-v3:turbo` is 623 MB. One server holds `gemma3:4b`, `embed-gemma` and
  `whisper-v3:turbo` together: `flm serve gemma3:4b --embed 1 --asr 1`. `scripts/check_flm.py` still passes with speech loaded.
- **Speed.** 0.24–0.31× real time: 2.5 minutes took 40–47 s, 5 minutes 79 s, 11 minutes 157 s. The
  text was the same on every run. FLM took WAV and MP4/AAC directly.
- **Accuracy.** About 4% of words wrong on synthesised speech, and 9.6% on the user's own voice
  through the laptop microphone. One garbled sentence there ("from 1 March" became "from 1st to
  March") produced a cited wrong answer three times out of three. Whisper writes US dates ("March 1,
  2027").
- **Silence.** A recording whose audio track was silent (-90 dBFS) came back as invented text ("E
  ai E ai...").

**Decision (the user's, 10 November):**

- **An uploaded recording, after the meeting. Not live.** In the user's words: "Uploaded recording
  but not an audio file, it will transcribed by whisper and be text file." The platform never
  records, so §1.9's exclusions of live transcription and of native recording capture stand. The change is narrower: a person who already has a
  recording can have the platform turn it into a transcript.
- **A draft first.** Nothing is indexed until a person has ticked that they reviewed and corrected
  the draft, and confirmed it. The tick is the interface's to ask for; it cannot prove the reading
  (see "What it does not cover").
  The confirmed text goes in through `POST /api/meetings` as pasted text: FR-09's own route,
  unchanged, and still the only path into the index.
- **Its own setting.** `TRANSCRIPTION_PROVIDER`, `none` or `flm`, independent of `AI_PROVIDER` and
  `none` by default. In the user's words: "the transcription needs this laptop's NPU, but the
  result is just a text file. The platform, hosted anywhere under D-114, ingests it the same way."
- **Video recordings are accepted as well as audio.** The user's own recordings on 6 November were
  Game Bar MP4s.
- **No audio is kept on the server.** The user stated no preference, so this is the default
  proposed to them: the server transcribes each segment and keeps nothing, and the browser holds the
  recording until the transcript is submitted or the page is left.

**Why each part:**

- **An uploaded recording, because it sits inside the proposal's own assumption.**
  - §1.9 rules out live transcription and native recording capture. Its capture line assumes that
    recordings are uploaded, and nothing in it excludes transcribing one that was.
  - Live transcription from the microphone, the other reading put to the user, would have
    overturned those exclusions, live transcription and native recording capture.
  - It is still an addition, not a requirement the proposal contains: no FR transcribes audio, and
    FR-09 takes a transcript.
- **The draft, confirmed through FR-09, because that keeps one path into the index.**
  - The transcription route stores nothing.
  - What is indexed is the text a person confirmed, sent to `POST /api/meetings` with FR-09's
    validation, the visibility rule (D-29) and FR-08's chunking and embedding unchanged.
- **The review, because of the measurements above.**
  - On the user's real voice, 9.6% of words came back wrong.
  - One misheard date became a cited wrong answer three times out of three. An answer cites its
    source, so a transcription error indexed unread comes back as a cited fact.
  - Whisper writes dates the US way, which needs a person on its own.
  - At about 0.25× real time, an hour's meeting is a draft in about fifteen minutes. The review
    asks a person to read that draft and correct it, not to transcribe the meeting themselves.
- **The setting, because only FLM has speech-to-text.** Claude and Voyage (D-113, the default since
  D-122) have none. D-114 wants M8 hostable on any device, so transcription is off unless the host
  runs FLM. A host without it still ingests a transcript made elsewhere, as a TXT file, through
  FR-09's file option.
- **Off by default, because a page offering a control that cannot work is worse than no control.**
  With the setting `none`, the recording option says plainly that transcription is not enabled on
  this server.

**How it is built.** This is the shape the decision fixes; the code comments cite this entry.

- **`AIService` gains `transcribe` and `transcription_health`** (`apps/ai/base.py`;
  `docs/ai-provider.md` §1).
  - `transcribe` takes one WAV segment and returns its text and the model that produced it.
  - `transcription_health` is a report that never raises, as `health` is. It lets the page say
    before a long run starts that FLM cannot be reached.
  - The FLM and Anthropic providers implement them through `apps/ai/transcription.py`. It calls FLM's
    OpenAI-compatible `/v1/audio/transcriptions` with `FLM_ASR_MODEL` (`whisper-v3:turbo`) through
    the `openai` client, whichever `AI_PROVIDER` is set. No vendor SDK is imported outside
    `apps/ai/`.
  - **Attempts:** `MAXIMUM_TRANSCRIBE_ATTEMPTS` is 3 (1 initial call + 2 retries), as D-19's other
    attempt totals are. D-118's rule applies: a transport failure, a 5xx or a 429 is retried; any
    other 4xx is `ProviderRefused` and is not.
  - **With the setting `none`,** `transcribe` raises `TranscriptionDisabled`, a
    `ProviderUnavailable`, on either provider, and `transcription_health` reports transcription
    unavailable without raising.
- **The browser cuts the recording into segments.** Each is a 16 kHz mono 16-bit PCM WAV of at most
  `TRANSCRIPTION_SEGMENT_SECONDS` (30 s), cut at the quietest tenth of a second in its last third, so
  that a cut rarely falls inside a word. The last segment may run up to a second longer rather than
  leave a sliver to be sent alone, which the server's 60 s ceiling admits. The reasons for cutting in
  the browser:
  - **Request length.** At 0.25× real time, an hour's recording is about fifteen minutes of
    transcription. One request that long would hold a Waitress thread throughout and lose everything
    if it failed near the end.
  - **Decoding.** Nothing in the stack decodes MP4, M4A or MP3 (there is no ffmpeg), and the
    browser decodes every common audio and video format. The server accepts only what the page
    sends, a 16-bit PCM mono WAV at 16 kHz, which Python's `wave` reads. It accepted any rate from
    8 to 48 kHz, mono or stereo, until the security review of 11 November measured a 60 s, 48 kHz
    stereo segment at about thirteen times the CPU of the page's own.
- **The routes** (`docs/api-contract.md`, "Recording transcription"):
  - `GET /api/transcriptions/status`: whether transcription is enabled here, and whether FLM
    answered.
  - `POST /api/transcriptions`: one segment in, its text out. It creates nothing: no meeting, no
    chunk, no row.
  - **Each needs a session and `contribute_content`** (FR-06), and each is tested from an Employee
    and an Administrator session (Objective 01).
  - **Each is throttled per user in one scope,** `transcription` (`TRANSCRIPTION_THROTTLE_RATE`,
    D-79). The status is in it because each request asks FLM for its model list.
  - **The POST holds one transcription in flight per user** (`apps/api/transcription_slot.py`,
    D-85's mechanism under its own key), **and `MAXIMUM_TRANSCRIPTIONS_IN_FLIGHT` (2) across the
    server.** FLM's one NPU takes segments in turn, so without the server's cap, accounts
    registered for the purpose could hold every Waitress thread with one segment each (the
    security review of 11 November, finding 2). Past it a segment is answered 429
    `transcription_busy` with a Retry-After, which the page waits out by itself.
  - **Each segment is held to `MAX_UPLOAD_BYTES`** (the answer is 413) **and to
    `MAXIMUM_TRANSCRIPTION_SEGMENT_SECONDS` of audio** (400), and no more than one frame past that
    is ever read from it. The size is checked against the declared length and again against the
    bytes that arrived, as on the upload; the second check is for a client that understates its
    length, which the test client cannot send, so it is untested, as the upload's is.
- **Silence never reaches Whisper.** The server measures each segment's loudest half second. Below
  `TRANSCRIPTION_SILENCE_DBFS`, the segment is answered `200` with `"status": "silent"` and no text,
  and the provider is not called. A segment with no audio frames at all is a `400`.
- **The recording itself never reaches the server**, so `MAX_UPLOAD_BYTES` does not bound it.
  `MAXIMUM_RECORDING_BYTES` bounds what the browser will decode, since the whole file and its
  decoded audio sit in the page's memory. Only the client enforces it, and the agreement test ties
  the client's copy.
- **Invariant 8 and NFR-20: a failed transcription discards nothing.**
  - **A failed segment stops the run and keeps it.** The decoded recording and the draft stay in
    the page, through a look at another source as well, and Resume retries from the failed segment.
    The exception is the 503 that says transcription has been switched off on the server: the draft
    is kept, and there is nothing to resume until it is switched on again.
  - **The draft can be saved as a TXT file at any point,** while segments are still arriving too.
  - **The browser asks before a tab holding an unadded draft is closed or reloaded.** It cannot ask
    on a move within the app (see "What it does not cover").
  - **The server keeps nothing,** so nothing on it can be lost. Nothing persistent, that is: a
    segment larger than Waitress's in-memory buffer (512 KB; a 30 s segment is about 960 KB)
    passes through the web server's own self-deleting temporary file while the request is read.
- **The review is the interface's to enforce.** A transcript from a recording cannot be submitted
  until the person ticks that they have reviewed it, and any text Whisper adds after the tick takes
  it back, so a run stopped, ticked and resumed cannot carry its later segments in unread (the
  requirements audit of 11 November found that it could). The notice above the draft names what Whisper
  gets wrong: names, numbers and US dates. The server cannot tell a reviewed transcript from a
  pasted one, so the front-end suite holds this clause (`CLAUDE.md` §8 item 2).

**What it does not cover:**

- **Live transcription, microphone capture and native recording capture.** Still out of scope
  under §1.9.
- **Speaker labels and timestamps.** Still out of scope under FR-09. Whisper's text carries none,
  and nothing parses them.
- **A CPU Whisper (for example faster-whisper) for hosts without the NPU.** It would be another
  `TRANSCRIPTION_PROVIDER` value. It is not built and is untested here; the user named it as the
  route for a host without the laptop.
- **Provenance on the meeting.** A stored meeting does not record that its transcript came from
  Whisper, because schema v1 has no column for it.
- **Whether the person actually corrected anything.** The tick box proves a person was asked; it
  cannot prove they read.
- **Whether Whisper is loaded.** FLM's `/v1/models` lists its chat catalogue and names neither
  `whisper-v3:turbo` nor `embed-gemma`, so the status check proves that FLM is reachable, not that
  it was started with `--asr 1`. A server without it fails the first segment, which the page
  reports as unavailable.
- **Recordings too large to decode in the page.** The cap is set from what a browser tab can hold,
  not measured on every browser.
- **Leaving the page within the app.** The app's router (`BrowserRouter`) offers no way to stop a
  move to another page, so following a link inside the app leaves an unadded draft and a paused run
  behind without asking. Only closing or reloading the tab asks. Saving the draft as a text file is
  the way to keep it.
- **Real recordings in a real browser, before the end-to-end trial.** The suites replace the
  browser's decoder. In Chromium on 11 November a 44.1 kHz stereo WAV and a WebM/Opus recording
  decoded to 16 kHz at their full length, but an MP4/AAC file recorded by the browser itself decoded
  to 1.06 s of 2 s, which may be the recorder's doing rather than the decoder's. A Game Bar or Voice
  Recorder file is the trial's to check.
- **What a request body costs before it is refused.** The size check orders the answers, not the
  reading. A session that sends its CSRF token, as the page always does, has its whole multipart
  body parsed by DRF while authenticating, because DRF's CSRF check reads `request.POST`, and so
  before the 403, the 429, the 503 and the 413 (the security review of 11 November found it,
  driving the view with CSRF enforced). What bounds the reading is the web server's own body
  limit, which the alpha's `waitress-serve` line leaves at Waitress's default of 1 GB. **This is
  not the transcription route's alone:** `POST /api/documents` and `POST /api/meetings` share the
  cause, and `config/settings.py` and D-30 claim the declared-length check refuses a body "before
  it is parsed". Fixing it for every route (a body limit on the web server, or a length check
  ahead of DRF) and correcting those claims is a separate change, proposed on 11 November and not
  made here.
- **Retries and a busy NPU.** A segment that times out is retried at once. Whether FLM goes on
  working on the abandoned request, so that the retry queues behind it, is not measured.
- **The silence threshold is a starting value.** `TRANSCRIPTION_SILENCE_DBFS` is *tune*: set from
  the -90 dBFS silent track above and ordinary speech levels, and to be checked on the user's real
  recordings in the end-to-end trial.

**The end-to-end trial, 11 November 2026** (`docs/recording-transcription-trial.md`):

- **The path worked end to end on real audio.** A narrated recording of between 9.3 and 14.5
  minutes went from the page to a cited answer under the `anthropic` provider, transcribed by
  Whisper on FLM.
- **The transcription:** 28 segments in 2 min 45 s, every one answered 200, one skipped as silent,
  and no invented text in the draft.
- **The review did not stop the errors.** The person ticked the review and added the draft
  uncorrected, so its errors went into the index: an inverted "cannot", a wrong upload limit and
  garbled terms. That is this entry's conceded limitation of the tick, observed rather than
  predicted.
- **Not measured:** the per-segment levels, so the margin of `TRANSCRIPTION_SILENCE_DBFS` is
  unchecked, and the recording's exact length and format.

**Dated note, 11 November 2026: "What a request body costs before it is refused" is closed by
D-124.**

- **What changed:** the CSRF check reads its token from the header only, so nothing reads a body
  before the view. `POST /api/transcriptions`' declared-length 413, and its 403, 429 and 503 before
  it, now refuse a body unread. That is tested by counting the bytes read
  (`apps/api/tests/test_request_body_bound.py`). Waitress's `--max-request-body-size` caps
  receiving at `MAX_REQUEST_BODY_BYTES`. The claims this item named, in `config/settings.py` and
  D-30, are corrected.
- **The item understated the old defect in two ways:**
  - **The CSRF cookie alone was enough.** The body was parsed before the header was looked for,
    so a session that did not send its token had its body parsed too, and was then refused.
  - **Django ran the same check on login, `/api/auth/me` and the SPA's catch-all,** signed out
    and on a made-up cookie. D-124 removed it there too.
- **Still this entry's own question:** the route accepts a segment of up to `MAX_UPLOAD_BYTES`,
  where a valid one is about 1.92 MB, and reads the whole part into memory.
- **The view's docstring and the contract's section** were corrected on the same day.

## D-124 · Request bodies are bounded before they are read: no CSRF check reads a body, and Waitress caps every body at 54,525,952 bytes

**Status:** Settled by the user · **Date:** 2026-11-11 · **Concerns:** FR-08, FR-09, FR-02, FR-06,
D-21, D-30, D-85, D-123, `apps/api/authentication.py`, `apps/api/views.py`, `config/spa.py`,
`apps/core/constants.py`, `config/settings.py`, `scripts/server_record.py`,
`scripts/ingest_objective02.py`, `docs/api-contract.md`, `docs/alpha-deployment.md`,
`docs/measurement-runbook.md`, `tests/load/README.md`, `apps/api/tests/test_transcriptions.py`

**The defect.** The security review of `feat/FR-09-recording-transcription` found it (D-123). That
branch recorded it as open and left the shared fix out of its scope. It was verified again here.

- **Django's CSRF check reads `request.POST`**, looking for a `csrfmiddlewaretoken` form field,
  before it falls back to the `X-CSRFToken` header. That read parses the body. The check ran on two
  paths.
  - **DRF's session authentication** (`SessionAuthentication.enforce_csrf`), on every request from a
    signed-in session. There `request.POST` runs the view's parser.
    - A multipart upload was parsed whole, its files spooled to temporary files past
      `FILE_UPLOAD_MAX_MEMORY_SIZE`.
    - A JSON body was read and parsed if it was within Django's `DATA_UPLOAD_MAX_MEMORY_SIZE`
      (2.5 MiB). DRF 3.18 parses JSON from `request.body`, which refuses a larger declared length
      unread, with a 400.
  - **Django itself, before DRF ran,** signed in or not.
    - **Where:** `ensure_csrf_cookie` ran it on `POST /api/auth/login` and `/api/auth/me`, and
      `CsrfViewMiddleware` ran it on the SPA's catch-all, which was not exempt.
    - **What it took:** a well-formed `csrftoken` cookie, which a client can make up.
    - **What it read:** Django parses a multipart body whole to answer `request.POST`.
- **So a body was parsed before any refusal:**
  - the 401, the 403 and the 429;
  - the upload routes' declared-length 413;
  - CSRF's own 403 for a missing header.

  Only a multipart body's files had no ceiling of their own. Their only limit was Waitress's, which
  the alpha's serve command left at its default, 1 GB. A signed-in Employee could send 1 GB uploads
  again and again, each received, spooled and parsed before it was refused. On the three routes
  Django checked, anyone could, signed in or not.
- **The suite did not see it.** The test client enforces CSRF only when asked, and with CSRF off
  Django's check returns before it reads anything. The one test that claimed the body went
  unparsed used such a client.
- **Measured here,** by running the new tests against the old CSRF paths:
  - the whole 52,428,801-byte upload was read on all three upload routes, before the 403, the 429
    and the 413 (and the transcription route's 503), from both roles;
  - the whole upload was read on login, `/api/auth/me`, `/` and `/documents`, from a client with a
    made-up cookie and no session;
  - 2,048-byte JSON bodies were read on reprocess, and on the ask route before its 429.

**The options weighed.** The choice touched FR-08's documented order of refusals, which §7.2
`validateUpload()` fixes as permission first, so the user decided it (`CLAUDE.md` §9).

- **(a) Waitress's `--max-request-body-size` on the serve command.** It bounds receiving, on every
  route. A body under the cap was still parsed before the 403.
- **(b) A middleware ahead of DRF** that answers 413 when the declared length is over the route's
  ceiling.
  - It bounds parsing only above the ceiling.
  - It puts that 413 before the 401, the 403 and the 429, which changes FR-08's documented order.
  - It does not bound what Waitress receives.
- **(c) Both (a) and (b).**
- **(d) The CSRF check takes its token from the header only,** so nothing parses a body before the
  view. Offered together with (a).

**The user chose (a) with (d), on 11 November 2026.** The three Django-checked routes came to light
in review, after the choice. Removing the check there is (d) carried to its end, and changes no
documented answer except the one in decision 2.

**Decision.**

1. **DRF's CSRF check reads the `X-CSRFToken` header only** (`apps/api/authentication.py`).
   - **How:** the project's `SessionAuthentication` runs DRF's own `enforce_csrf` on a stand-in
     for the request whose `POST` is empty. Django's check then goes straight to the header.
   - **Unchanged:** everything else Django checks, which is the CSRF cookie, the token's match
     against it, and the Origin and Referer headers.
   - **Given up:** the `csrfmiddlewaretoken` form field as a second place for the token. Nothing
     uses it. The SPA, the measurement scripts and the load test all send the header, which is
     what D-21 and the contract already describe.
2. **Django no longer runs its own check on the three routes that had it.**
   - **Login and `/api/auth/me` drop `ensure_csrf_cookie`.** `SendsCsrfCookieMixin` in
     `apps/api/views.py` keeps what the decorator was there for: the `csrftoken` cookie, sent with
     every response, a 401 or 429 included. It calls `get_token()` in `finalize_response`.
   - **Why that loses nothing:** the check the decorator ran never refused anything, because
     `ensure_csrf_cookie` does not reject. A session's unsafe request to these views is still
     checked by DRF.
   - **The SPA's catch-all (`config/spa.py`) is `csrf_exempt`.** It makes no write: `require_safe`
     answers every unsafe method 405, and that 405 now comes first. The contract's "or Django's
     `403` page first" for such a request goes with it.
3. **So nothing reads a body before the view, on any route, under Waitress** (runserver is below).
   - **DRF views:** decision 1.
   - **Login, `/api/auth/me` and the catch-all:** decision 2.
   - **A path that matches no route:** never reaches a view or a CSRF check.
   - **A built file:** WhiteNoise answers an unsafe method 405 without reading the body.
   - **The upload's order:** FR-08's order now holds for reading as well as for answering: 401,
     403, 429, the declared-length 413, then the rest of §7.2. The upload's 403 is now "the
     cheapest rejection" in fact (D-30's dated note).
   - **Unchanged since Stage 3:** the declared-length 413 still comes before the signature's 415,
     because the signature cannot be read without reading the body. The contract now says so.
4. **`POST /api/meetings` gets the upload's declared-length check.**
   - **The answer:** a body over `MAX_UPLOAD_BYTES` is 413 `TRANSCRIPT_TOO_LARGE_MESSAGE`. It comes
     after the 403 and the 429, and before the body is read.
   - **A *convention*:** FR-09 enumerates only 201 and 400, and a body refused unread has no field
     to report an error on.
   - **A transcript file** had no ceiling before this but Waitress's 1 GB.
   - **A pasted transcript** was already held to 2.5 MiB by Django. Between 2.5 MiB and 50 MB it is
     `400 {"detail": "Bad request."}`, refused unread, which the contract now lists. Above 50 MB the
     new 413 replaces that 400.
   - **One helper serves every upload route:** `declares_a_body_over_the_upload_ceiling` in
     `apps/api/views.py`. That is the document upload, the meeting ingest and, since D-123 merged,
     the transcription route, which had its own copy of the check.
5. **`POST /api/documents/{id}/reprocess` takes no body, and now reads none,** so it needs no
   ceiling of its own.
6. **Waitress caps every request body at `MAX_REQUEST_BODY_BYTES`, 54,525,952 bytes,** which is
   2 MiB over `MAX_UPLOAD_BYTES`.
   - **Where:** `--max-request-body-size=54525952` is on every documented serve command:
     `docs/alpha-deployment.md`, `docs/measurement-runbook.md`, `tests/load/README.md`, and
     `scripts/server_record.py`'s `D85_COMMAND` (D-85's dated note).
   - **How Waitress refuses:** a declared length at or over the cap is refused at the headers,
     before the body is read, with Waitress's own plain-text 413, and the connection is closed. A
     chunked body declares no length, so Waitress counts it as it arrives and refuses it at the
     cap.
   - **Why 2 MiB of margin:** a body a little over the upload ceiling still gets the API's JSON
     413. That includes the Objective 02 ingestion's oversized item I02, which is generated 1 MiB
     past the ceiling, so its recorded outcome is unchanged.

**Claims corrected, each with its date:**

- the `FILE_UPLOAD_MAX_MEMORY_SIZE` comment in `config/settings.py`;
- D-30, in a dated note: the 403 came first among the answers, but not before the reading;
- `docs/api-contract.md`:
  - Stage 3's "The size ceiling is applied twice: once against the declared `Content-Length`,
    before the body is parsed";
  - item 9's "or Django's `403` page first";
- in `apps/api/views.py`:
  - `DocumentsView`'s docstring and its `post` comment;
  - `MeetingsView._transcript_from`'s "the transcript path cannot answer 413";
- the docstring of `test_an_oversized_body_is_refused_before_it_is_parsed` in
  `apps/api/tests/test_document_upload.py`;
- the comment in `scripts/ingest_objective02.py` that had the view's 413 answer "before reading
  the whole body". Under Waitress, the view answers only after the whole body has been received.

**What it covers:**

- **Every route, for reading before the view, under Waitress** (decision 3).
- **The three upload routes' bodies over `MAX_UPLOAD_BYTES`,** refused unread by their declared
  length:
  - `POST /api/documents`;
  - `POST /api/meetings`;
  - `POST /api/transcriptions`, merged with D-123 on 11 November after this entry was first
    written. It now uses the same helper, and D-123's dated note closes its open item.
- **Every route's body declared at or over `MAX_REQUEST_BODY_BYTES`,** refused by Waitress before
  it is received, where the server is started as documented. A chunked one is refused when it
  reaches the cap.

**What it does not cover:**

- **A server started without the flag.** The cap is a command-line option, so nothing in the
  application can enforce it.
  - `scripts/server_record.py` records the observed command line, which shows the flag when it is
    there, but it checks only the server and the thread count.
  - A server started with an old command still takes bodies up to 1 GB. The application still
    refuses such a body unread past the upload ceiling, but Waitress has already received it and
    spooled it to a temporary file.
- **Receiving under the cap.** Waitress reads a body of up to 54,525,952 bytes before Django sees
  it, whatever the route, and whether or not the body is then refused. A chunked body is received
  up to the cap before Waitress refuses it.
- **Django's runserver.** After the response, runserver's handler reads whatever the application
  left unread, in a single read, and runserver has no body limit. So "refused unread" holds under
  Waitress only. Runserver is for development.
- **JSON bodies under Django's ceiling.**
  - **The cost:** a JSON body of up to 2.5 MiB is read and parsed in memory, now in the view, after
    the 403 and the 429. The security review measured `json.load`'s peak at about 25 times the
    body for a body of many small objects: 126 MB for a 5 MB body, measured outside the app. That
    is about 60 MB at the ceiling.
  - **Who can send them:** a route without a throttle takes such bodies as fast as it answers them.
    Login and registration take them from signed-out clients, within the auth throttle's 20 a
    minute per address.
  - **Not part of this change:** a smaller JSON ceiling.
- **`POST /api/transcriptions`' own ceiling.** Whether the route should accept a segment of up to
  `MAX_UPLOAD_BYTES` is D-123's own question, raised in its dated note. A valid segment is about
  1.92 MB, and the route reads the whole part into memory.
- **The response above the cap.** Waitress's 413 is plain text, not the contract's JSON, and a
  client still sending when Waitress closes the connection may see a reset instead. The SPA never
  sends that much: the upload and meeting forms screen a file's size before sending it.
- **The meeting form's answers.** It shows its generic refusal for the 413, which the page reaches
  only with a pasted transcript over 50 MB, and for Django's 400 between 2.5 MiB and 50 MB.
- **A file within a few hundred bytes of 50 MB.** The declared-length check refuses it, because the
  body adds the multipart framing to the file. That is unchanged since Stage 3.

**Tests:** `apps/api/tests/test_request_body_bound.py`.

- **How each request is sent:** as the SPA sends it, with CSRF enforced and the `csrftoken` cookie
  from `GET /api/auth/me` returned in `X-CSRFToken`, from an Employee session and an Administrator
  session. The exceptions are signed-out requests carrying a made-up cookie.
- **How a read is detected:** the body is a stream that counts what is read from it, installed as
  `wsgi.input`, so it sees any reader. A multipart body is a well-formed upload of one file. Bytes
  read are asserted before status.
- **What they check:**
  - an oversized body gets a 413 and is not read, on all three upload routes: documents and
    meetings, multipart and JSON, and transcriptions;
  - a pasted transcript between 2.5 MiB and 50 MB gets Django's 400, unread;
  - no body is read before the 401, the 403 or the 429 on any upload route, nor before the
    transcription route's 503 while transcription is off, and the 403 comes before the 413;
  - reprocess reads no body, and `/api/ask` reads none before its 429;
  - login, `/api/auth/me`, `/` and `/documents` read nothing, signed out with a made-up cookie or
    signed in, and login and `/api/auth/me` still send the cookie;
  - the CSRF check still refuses, without reading: no header, a wrong token, the token only in a
    form field, a foreign Origin, no cookie;
  - an upload and a transcript sent with the header are stored;
  - Waitress refuses a body at the cap at its headers, without calling the application;
  - every documented serve command carries the flag, `D85_COMMAND` included, and I02 stays under
    the cap.
- **Checked against the code before the fix:** the old `apps/api/authentication.py`, the two
  `ensure_csrf_cookie` decorators and the old `config/spa.py` were put back, on the code merged
  with D-123. Then 40 of the 72 tests fail.
  - 38 fail because the body was read: 52,428,801, 2,048 or 136 bytes.
  - 2 fail because Django answered its own 400 where the 413 is expected, for a JSON transcript
    over 2.5 MiB, which it refused unread even then.

**Reviewed on 11 November 2026.** A security review and a requirements audit ran on the first
version of this change, and found the three Django-checked routes and a false premise about JSON.
This entry and the code carry both corrections, and the tests above were re-run against the old
code.

## D-126 · FR-19's permission exclusion is per embedding model: voyage-4 is threshold-first, D-108's rule as first written, and EmbeddingGemma keeps rank-one

**Status:** Settled by the user · **Date:** 2026-11-11 · **Concerns:** FR-19, Objective 06, D-108,
D-110, D-93, D-120, D-122, `apps/core/constants.py`, `apps/retrieval/gaps.py` · **Departs from:**
D-93 and D-108's fallback, both disclosed below

**What prompted it:** Objective 06's verification on the `anthropic` provider (#86,
`corpus/objective-06/runs/2026-11-10-anthropic/`).

- **The thirty's first cycle on voyage-4** met clauses 2 and 3, and not clause 1: U01 was missing
  from the log.
  - U01 ("Will my salary rise with inflation?", asked by the Employee) is a genuine gap, and D-108's
    rank-one rule left it out.
  - Its top-ranked passage over the Administrator's scope scores 0.197 and is Administrator-only.
    The best readable one scores 0.1875.
- **D-108's development check came after that cycle.** D-108's note of 10 November and D-110's note
  on the FLM configuration ask for it on a new configuration before the thirty run there. On
  voyage-4 it was not run first, an oversight owned in #86's write-up.
  - Run afterwards, it fails. The scoped questions are all left out, as they should be. Of the
    no-answer questions, u36 and d27 are left out too, in U01's way (0.230 and 0.238,
    Administrator-only).
  - On embed-gemma it passed (D-108's notes of 10 November).
- **The cause:** the rank-one rule meets Voyage's lower scores for out-of-corpus questions. A
  genuine gap's best match is weak, and it can fall on restricted material. This is the "known cost"
  of D-108's evening note. It was unmeasured on embed-gemma, where no question had the shape.

**The options put to the user.** D-108 says that when the check fails, the margin rule is chosen on
the development material. On voyage-4 two rules pass the check
(`corpus/objective-06/runs/2026-11-11-anthropic/exclusion-rule-exploration/`):

- **The margin rule.** A row is left out when its restricted top passage beats the best readable
  one by at least m. Here m = 0.0939, the midpoint between d27's margin (0.0659, the larger of the
  no-answer margins, u36's and d27's) and d21's (0.1218, the smallest scoped margin).
- **Threshold-first,** step 4 of D-108's rule as first written, at the model's own threshold
  (0.2687, D-120). It needs no new constant.

The development questions cannot choose between them. On the frozen thirty they differ. That is
arithmetic on the diagnosis of #86's cycle (`exclusion_diagnosis.txt` there), not a new run:

- the margin rule would keep P02, whose margin is 0.0448, so a permission-only question would be in
  the log and clause 3 would not be met;
- threshold-first leaves P02 out (0.2812, above 0.2687) and keeps U01 (0.197, below it).

**Decision (the user's, 11 November): threshold-first for voyage-4.**

- **The map:** `GAP_EXCLUSION_RULE_BY_MODEL = {"voyage-4": "threshold-first"}`. Any model not
  listed, embed-gemma included, keeps `GAP_EXCLUSION_RULE = "rank-one"` (`333be14`).
  `gaps.exclusion_rule()` reads both at call time, as `grouping_threshold()` reads its map.
- **The rule:** if no passage reaches the model's own relevance threshold (`ranking.admit`), nobody
  could have been answered, and the row is a gap. Otherwise the top admitted passage decides, as
  before.
- **Why embed-gemma keeps rank-one:** threshold-first kept P02 there, at 0.2977 to 0.2983 against
  0.30 (D-108's evening note). Nothing was measured again on embed-gemma for this entry.

**Two departures, disclosed.**

- **From D-93.** The choice between the two passing rules used the frozen thirty's P02 and U01. The
  earlier departures on frozen sets are named in D-106's and D-110's notes of 10 November (night);
  this one is on the same thirty as D-110's, which now carries its own note. The thirty's first
  cycle on voyage-4 (#86) stays the independent result. The rule now shipped for voyage-4 has no
  independent figure.
- **From D-108's fallback.** D-108 says the margin rule is chosen when the check fails, and that the
  thirty are never used to choose. The margin rule was not chosen, and the thirty were used. D-108
  carries a dated note.

**Verified** on `fix/FR-19-exclusion-voyage`. The evidence is
`corpus/objective-06/runs/2026-11-11-anthropic/`, and `objective-06-d126.md` there is the write-up.

- **Tests,** in `apps/retrieval/tests/test_knowledge_gaps.py`, each named with the deliberate
  breaks of `gaps.py` under which it fails. The breaks are listed after the table.

  | Test | Fails under |
  |---|---|
  | `test_the_exclusion_rule_is_the_embedding_models_own` | A, B |
  | `test_on_voyage_a_restricted_best_match_under_the_threshold_is_a_gap` (U01's shape) | A, D |
  | `test_on_voyage_a_readable_best_match_under_the_threshold_is_a_gap` | D |
  | `test_on_voyage_a_restricted_top_admitted_passage_is_left_out` | E |
  | `test_on_voyage_a_restricted_answer_between_the_two_thresholds_is_left_out` (P02's shape) | C, E |
  | `test_on_voyage_the_top_admitted_passage_decides_when_both_are_admitted` | E |
  | `test_on_voyage_an_administrators_question_is_always_kept` | D, F |
  | `test_rank_one_still_decides_below_the_threshold_for_a_model_not_listed` | B |

  - A: voyage-4 forced back to rank-one.
  - B: every model forced to threshold-first. The existing
    `test_a_question_whose_best_passage_is_restricted_is_left_out_below_the_threshold` fails too.
  - C: threshold-first judged by EmbeddingGemma's threshold instead of the model's own.
  - D: threshold-first, with nothing admitted meaning left out.
  - E: threshold-first never leaving an admitted row out.
  - F: every asker judged as an Employee. The existing
    `test_an_administrators_unanswered_question_is_always_kept` and
    `test_the_asker_role_is_read_from_the_user_row_at_cycle_time` fail too.
  - **A correction to `b854288`'s message.** It says every new test failed under a deliberate
    break. Under its two breaks, A and B, that was true of the first, second and last rows above
    only. The test for P02's shape and breaks C to F were added afterwards, in `14d9629`.
- **D-108's check on the shipped code,** run twice at `462e8e9`
  (`exclusion-dev-check-threshold-first/`): it passes both times. Scoped questions left out: u30,
  u31, u32, d11, d21, d22. No-answer questions kept: u33, u34, u35, u36, u37, d24, d25, d26, d27.
- **Objective 06 on `anthropic`, three draws** (D-110's note asks for repeated seeding there, and
  the user asked for three):
  - draw 1, on rank-one (#86): clause 1 not met, U01 missing; clauses 2 and 3 met;
  - draws 2 and 3, on this rule at `462e8e9`: all three clauses met on each. Every expected query
    is in the log, each of the four subjects has one entry counting its three queries, and no
    permission-only query is in the log;
  - generation's outcome was the same on the three draws: A01 to A07 answered; U04, U05, P07 and
    P08 declined after generation (path B); every other ask a no-answer on path A.

**What it costs:**

- **A possible leak.** A permission-only question whose restricted answer scores under 0.2687 would
  be kept, so its wording would reach the gap log, which FR-19's validation clause forbids. Neither
  the development questions nor the thirty have one: their restricted answers score from 0.2812
  (P02) to 0.56 (u32). P02 sits 0.0125 above the threshold, about 27 times Voyage's jitter of
  0.00047. The size of this cost beyond this corpus is unmeasured.
- **A coupling to D-120.** The rule rests on voyage-4's relevance threshold, so re-tuning that
  value moves the exclusion too. The test for P02's shape is designed from the threshold, not a
  literal, and follows it.

**Not covered:**

- embed-gemma, or any model other than voyage-4, under threshold-first: not measured for this entry.
- An independent test of the voyage-4 rule: none exists, as above.
- A permission-only question scoring under 0.2687: none in either set, so the leak's rate is not
  known.
- The zero-result search side: unchanged. D-108's recount as the Administrator does not use this
  rule.
- FR-12's declines on these draws: not scored here. Each draw's rows are exported
  (`draw-N/export.json`) for that scoring.
- D-108's own "Not covered" list (FR-13 composition, a role recorded at ask time, re-evaluation
  after a visibility change): it stands.

**Where it applies:** `apps/core/constants.py`, `apps/retrieval/gaps.py` and
`apps/retrieval/tests/test_knowledge_gaps.py`. D-108 and D-110 carry dated notes.
