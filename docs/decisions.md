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
| D-74 | The demonstration corpus is tagged from the manifest by an idempotent script, applied_by="user", against kmp | Settled by the user | 2026-10-06 |
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
