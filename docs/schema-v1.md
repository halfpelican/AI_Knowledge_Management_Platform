# Schema v1 — table definitions

Compiled from the table definitions in `Project_8-proposal_complete_V4.5.docx`, which
state them per functional requirement rather than in one place. This file is the
authoritative source for migration v1. Where the proposal is silent or inconsistent,
that is marked explicitly in §4 rather than resolved silently.

Conventions: UUID primary keys throughout. Status fields use fixed vocabularies, not
free text. All timestamps are timezone-aware.

---

## 1. Tables in migration v1 (M6 scope)

### Users — FR-01, FR-02, FR-05

| Field | Type | Notes |
|---|---|---|
| `user_id` | UUID PK | |
| `name` | text | required |
| `email` | text | unique; 409 Conflict on duplicate registration |
| `password_hash` | text | bcrypt; never returned in any response |
| `role_id` | UUID FK → Roles | defaults to Employee on registration |
| `created_at` | timestamp | |
| `failed_attempts` | integer | default 0; incremented on failed login (FR-02) |
| `locked_until` | timestamp, nullable | five consecutive failures → 15 minutes (FR-02) |
| `last_login_at` | timestamp, nullable | |

`failed_attempts` and `locked_until` are written by FR-02 and read by FR-03. FR-02 is
MUST, so the columns belong in v1 even though the full lockout interface is FR-03
(SHOULD, NIT3004).

### Roles — FR-05, FR-06, FR-11

| Field | Type | Notes |
|---|---|---|
| `role_id` | UUID PK | |
| `role_name` | text | "Employee", "Administrator" |
| `description` | text | e.g. "Can curate and approve knowledge records" |

Two roles only. Administrator generalises Employee.

### Permissions — FR-06

| Field | Type | Notes |
|---|---|---|
| `permission_id` | UUID PK | |
| `permission_name` | text | e.g. `manage_documents` |

### RolePermissions — FR-06, FR-11

| Field | Type | Notes |
|---|---|---|
| `role_id` | UUID FK → Roles | composite PK with `permission_id` |
| `permission_id` | UUID FK → Permissions | |

Permissions are held against roles, never against individual users.

### Documents — FR-08, FR-11, FR-14, FR-15

| Field | Type | Notes |
|---|---|---|
| `doc_id` | UUID PK | |
| `title` | text | required; 400 if empty |
| `file_type` | text | "pdf", "docx", "xlsx", "txt" |
| `uploaded_by` | UUID FK → Users | |
| `status` | text | fixed vocabulary — see §3 |
| `uploaded_at` | timestamp | |
| `department` | text | see gap G3 |
| `visible_to_roles` | text[] | the FR-11 permission filter; set at upload, both roles when omitted — D-29 |
| `file_path` | text (FileField) | **v2** — where the stored original lives under `MEDIA_ROOT`; G7, D-18, D-05 |
| `content_hash` | text, unique, nullable | **v2** — SHA-256 of the uploaded bytes; FR-08's 409 compares content, not filename (§7.2) |
| `file_size_bytes` | bigint, nullable | **v2** — recorded on the document by §7.8 |

### ExtractedContent — FR-08, FR-15

| Field | Type | Notes |
|---|---|---|
| `content_id` | UUID PK | |
| `doc_id` | UUID FK → Documents | cascade delete |
| `extracted_text` | text (long) | |
| `extracted_at` | timestamp | |

Stored separately from the original file so text is reusable without re-parsing.

### ContentChunks — FR-08, FR-09, FR-12, FR-14, FR-15

| Field | Type | Notes |
|---|---|---|
| `chunk_id` | UUID PK | the identifier citation verification checks against |
| `source_type` | text | `document` or `meeting` — see gap G1 |
| `source_id` | UUID | Documents.doc_id or Meetings.meeting_id |
| `chunk_index` | integer | position within the source |
| `chunk_text` | text | |
| `embedding` | vector(`EMBEDDING_DIMENSION`) | pgvector; dimension from settings, never a literal |
| `embedding_model` | text | e.g. `embed-gemma` — see gap G2 |
| `embedding_dimension` | integer | 768 for embed-gemma |
| `created_at` | timestamp | |
| `visible_to_roles` | text[] | stamped from the source at ingestion so the filter and the vector share a table — D-17 |
| `ai_generated` | boolean, default false | true only for a passage of a meeting's AI-generated summary (FR-16); added by `documents 0012_content_chunk_ai_generated` — D-125 |

Index on `(source_type, source_id)` and on `embedding_model` — retrieval filters by
recorded model before ranking.

**A meeting's summary is indexed as chunks of the meeting itself (FR-16, UC-04; D-125).** They
carry `source_type` "meeting" and the meeting's id, so D-47's cascade re-stamps them with the
transcript's chunks and deleting the meeting removes them, with no second branch anywhere.
`ai_generated` is what tells them apart: it is how a Regenerate and `reindex` replace them, why
FR-12's title-only snippet never takes one for the opening of the transcript, and what the answer
and search payloads report so the interface can mark the passage as AI content (NFR-15). Their
`chunk_index` starts at 0 again, so `(source_type, source_id, chunk_index)` is not unique for a
meeting; nothing relies on it being so.

### Meetings — FR-09, FR-14

| Field | Type | Notes |
|---|---|---|
| `meeting_id` | UUID PK | |
| `title` | text | required |
| `meeting_date` | date | required; may not be in the future |
| `transcript_text` | text (long) | must exceed minimum length |
| `status` | text | fixed vocabulary — see §3 |
| `created_at` | timestamp | |
| `visible_to_roles` | text[] | the FR-11 permission filter, mirrors Documents — G6, D-16 |

### MeetingAttendees — FR-09

| Field | Type | Notes |
|---|---|---|
| `attendee_id` | UUID PK | |
| `meeting_id` | UUID FK → Meetings | |
| `user_id` | UUID FK → Users | |

A participation record, never an access rule (D-16). Since FR-16 it is also read to decide
whose name an action item's owner means: an extracted item's owner is always one of the meeting's
attendees, and one whose role can read the meeting (D-125, its third note). Nothing about who may
see a meeting consults it.

### MeetingSummaries — FR-16

Added by `meetings 0003_fr16_meeting_summaries` (D-125). One row per summary run. The first five
fields are the proposal's field table; the rest are UC-04's (the decisions, the highlights, every
element's passages, "a record of the model that produced it and the date") and NFR-20's (the retry
flag).

| Field | Type | Notes |
|---|---|---|
| `summary_id` | UUID PK | |
| `meeting_id` | UUID FK → Meetings | deleted with the meeting |
| `summary_text` | text | the narrative's sentences joined; blank until the run is Ready |
| `status` | text | fixed vocabulary — see §3. Created `Processing`, ends `Ready` or `Unavailable` |
| `generated_at` | timestamp, nullable | when the run became Ready |
| `run_number` | integer | 1, 2, 3… per meeting, unique with `meeting_id`; "latest" is the highest, never a timestamp |
| `narrative`, `decisions`, `highlights` | JSON | lists of `{text, passages}`, holding only references to passages that were sent |
| `passages` | JSON | the text of every transcript passage an element names, by number |
| `model` | text | the chat model that answered |
| `input_truncated`, `passages_sent`, `passages_total` | boolean, integer, integer | how much of the transcript one request carried (`SUMMARY_INPUT_TOKENS`, `SUMMARY_INPUT_CHARACTERS`) |
| `action_items_extracted` | integer, nullable | how many items the run extracted; 0 is UC-04 A1's section recorded as empty |
| `requested_by` | UUID FK → Users, nullable | who pressed Generate or Regenerate; null for the run ingestion starts; **set NULL** if the user is deleted |
| `requested_at`, `started_at` | timestamp | `started_at` is when the current attempt began: a `Processing` row much older is an orphan |
| `queued_for_retry` | boolean | NFR-20's "flagged for automatic retry"; indexed |
| `retry_runs` | integer | queued runs made so far, at most `MAXIMUM_SUMMARY_RETRY_RUNS`; a malformed failure is queued only while it is below `MAXIMUM_MALFORMED_RETRY_RUNS` |
| `failure_reason` | text | fixed vocabulary — see §3; blank unless `Unavailable`; never shown to a user |

**The table is Create and Read in substance.** A row's status moves during its own run, and
`summary_text` and the element lists are written once, when it is Ready, and never edited; a
Regenerate makes a new row. The meeting's current summary is its latest Ready row. A failed row
holds no text and is never presented or cited (UC-04, on failure).

### ActionItems — FR-16

Added by the same migration. **The proposal names this table and gives it no field table**
(D-125): the columns are taken from FR-16's "description, suggested owner and due date" and
UC-04's "the person or role it was assigned to and, where the transcript states one, the date by
which it falls due".

| Field | Type | Notes |
|---|---|---|
| `action_item_id` | UUID PK | |
| `meeting_id` | UUID FK → Meetings | the item belongs to the meeting, so a person's additions and edits outlive a Regenerate |
| `summary_id` | UUID FK → MeetingSummaries, nullable | the run that extracted it; null for an item a person added; **set NULL** if that row goes |
| `description` | text | |
| `owner_id` | UUID FK → Users, nullable | **null is unassigned**: FR-16 stores an item without a confident match that way; **set NULL** if the user is deleted |
| `owner_name` | text | the owner as the transcript named them ("Alex", "the facilities team"); blank where it named nobody |
| `due_date` | date, nullable | converted from `due_text` by the meeting's date, or set by a person; null where the phrase fixes no date |
| `due_text` | text | the deadline as said ("next Friday") |
| `passages` | JSON | passage numbers into the extracting summary's `passages`; empty for a person's item |
| `origin` | text | `ai` or `user` — see §3 |
| `position` | integer | the panel's order: an extracted item's place in the reply; a person's item after every item then present |
| `edited` | boolean | a person changed an extracted item; a Regenerate then leaves it alone |
| `created_by` | UUID FK → Users, nullable | who added the item; null for an extracted one; **set NULL** if the user is deleted. Never returned (D-125's third note: the security review of 12 November asked for it) |
| `updated_by` | UUID FK → Users, nullable | who last changed the item; null until a person does; **set NULL** if the user is deleted. Never returned (D-125's third note) |
| `created_at`, `updated_at` | timestamp | |

At most `MAXIMUM_ACTION_ITEMS_PER_MEETING` (200) items per meeting: a person's addition past it is
refused (D-125's third note).

### Conversations — FR-13

| Field | Type | Notes |
|---|---|---|
| `conversation_id` | UUID PK | |
| `user_id` | UUID FK → Users | |
| `title` | text | e.g. "Leave policy questions" |
| `last_updated_at` | timestamp | |

### QueryLog — FR-12, FR-13, FR-14

| Field | Type | Notes |
|---|---|---|
| `query_id` | UUID PK | |
| `user_id` | UUID FK → Users | |
| `conversation_id` | UUID FK → Conversations, nullable | null for a one-off question |
| `question` | text | |
| `answer_text` | text, nullable | null where no answer was returned |
| `retrieved_chunk_ids` | UUID[] | FR-12 traceability |
| `answered` | boolean | |
| `no_answer_reason` | text, nullable | see §3 — the two paths are recorded distinctly |
| `answered_at` | timestamp | |
| `rejected_count` | integer, nullable | statements verification removed; null where generation was not called |

`no_answer_reason` is the one field in this table the proposal does not name
explicitly, but FR-12 requires the two no-answer cases be "recorded separately", and
this is how. Without it the platform cannot tell a threshold that is too high from
retrieval that is returning irrelevant passages.

`rejected_count` is the second such field, added on 24 September 2026 and justified
the same way. Invariant 7 requires that no-answer path B's two kinds stay separable,
and `no_answer_reason` alone cannot do it: a model that proposes nothing and a model
whose every citation is rejected both arrive as `no_statement_verified`. The evidence
is the Stage 4 item 6 live runs — before the prompt fix, 2 questions where the model
declined and 3 where verification rejected everything; after it, 6 and 0. **The
aggregate moved 5 to 6, which on its own reads as "no effect"**, while what actually
happened was one failure mode removed and the other grown. Only the split shows it.

It is populated on **every call that reached generation**, answered rows included: an
answered row with `rejected_count` above zero is fabrication that has not yet cost
anyone an answer, which is the earliest warning the system produces. **Null means
generation was not called** — no-answer path A, and the keyword search path. It never
means "path B did not occur" and it never means zero.

It stores a count and never the claimed identifier, which section 7.9's rejection log
would also record. A fabricated identifier has no referent, so storing one invites a
later reader to resolve it against `ContentChunks` and read a hit or a miss as
provenance. A database column is a surface, and invariant 6 applies to it.

`rejected_count` and `no_answer_reason` are **record-only**. No serializer may expose
either: both would hand a caller the path-A/path-B distinction that the two paths'
identical reply exists to hide.

### SearchLogs — FR-12

| Field | Type | Notes |
|---|---|---|
| `search_id` | UUID PK | |
| `user_id` | UUID FK → Users | |
| `query_text` | text | |
| `result_count` | integer | computed **after** permission filtering |
| `searched_at` | timestamp | |

### AnswerCitations — FR-12

| Field | Type | Notes |
|---|---|---|
| `citation_id` | UUID PK | |
| `query_id` | UUID FK → QueryLog | cascade delete with its query |
| `chunk_id` | UUID FK → ContentChunks, nullable | **set NULL** when the chunk is deleted — D-67 |
| `chunk_uuid` | UUID | **post-v1** — the cited chunk's identifier, kept when `chunk_id` is set NULL — D-67 |
| `statement_text` | text | the statement this citation supports |
| `position` | integer | order within the answer |

Rows are written only for statements that **survived** verification. A rejected
statement is not stored, consistent with there being no state in which an uncited
statement exists.

`chunk_id` was NOT NULL with cascade delete until 5 October 2026 (D-12), so a reprocess,
`manage.py reindex` or FR-15's deletion destroyed every citation of the chunks it
removed, and FR-12's traceability record with them. Retrieval migration `0003` makes it
nullable and `SET NULL`, and adds `chunk_uuid`, written with the same identifier by
`record_query` and backfilled from `chunk_id` for existing rows. A citation now outlives
its chunk.

**No passage text is stored, deliberately.** FR-15 removes a deleted document's content
"so that deleted material cannot subsequently be surfaced through search"; a snapshot
would be that material surviving the delete. **A row whose `chunk_id` is NULL is removed
for every reader**: its statement and identifier are not shown, exactly as when the
cascade deleted the row.

### Tags — FR-10, FR-15

| Field | Type | Notes |
|---|---|---|
| `tag_id` | UUID PK | |
| `tag_name` | text | unique within a dimension, case- and whitespace-normalised |
| `dimension` | text | `Department`, `Project`, `Process`, `Topic` |
| `active` | boolean | deactivated rather than deleted while content references it |
| `grown` | boolean | **`documents 0010`; its meaning since `documents 0011`: not vocabulary.** A tag that is not grown is in every document's scheme, whatever its links; a grown tag is in only where every role in the audience reads a source carrying it (D-105's dated note of 10 November 2026, night: the security review). Set on a Topic a person's `POST /api/documents/{id}/tags` name form or confirmation of a proposed topic creates or reactivates (an active Topic either one reuses keeps its value, so vocabulary stays vocabulary); by `documents 0011` on every tag that then had links and no link on a source every role reads; and by `seed_objective02_tags.py`'s linked mode on the seeded values only restricted material carries. A value an Administrator adds through `POST /api/tags` (D-128) is not grown: it is vocabulary. A person's confirmation of a proposal, or their Topic name form, reactivates a retired tag only through a document every role can read (D-128's security review). For one day D-128 also had the classifier create and reactivate values; D-129 reversed it. Never unset |

### ContentTags — FR-10, FR-15

| Field | Type | Notes |
|---|---|---|
| `content_tag_id` | UUID PK | |
| `tag_id` | UUID FK → Tags | |
| `source_type` | text | `document` or `meeting` |
| `source_id` | UUID | |
| `applied_by` | text | `ai` or `user` — provenance |
| `confirmed` | boolean | a user-confirmed tag is not altered by reprocessing |
| `confidence` | decimal(4,3), nullable | **v2** — the model's confidence for an AI-applied link, to three places; null for a link a person applied (FR-10, D-105; `documents 0008`) |
| `provisional` | boolean | **v2** — an AI link whose confidence was below `CLASSIFICATION_CONFIDENCE_THRESHOLD`: held for confirmation and not a tag of the document until confirmed (FR-10, D-105; `documents 0008`) |
| `removed` | boolean | **v2** — a person removed this link, the machine's or a person's: kept, an AI link with its `confidence` and `provisional` as the machine set them, read by nothing, and neither re-linked nor altered by reprocessing (FR-10's correction clause; D-105's dated note of 10 November 2026, night; `documents 0009`). A person's link was deleted on removal until the requirements re-audit of that night |

**Tags and ContentTags are in v1 even though FR-10 is NIT3004 work.** FR-15 is a
MUST-HAVE and its browse mode queries `ContentTags` directly. The tables will be
sparsely populated until FR-10 lands — browse by tag will simply return little — but
the schema and the query path must exist at M6, and adding them later means a
migration during the most congested week of the project.

**The two v2 columns (8 November 2026, D-105).** FR-10: "a confidence value is recorded with
each assignment. Assignments below the configured threshold are marked provisional and
presented for confirmation rather than applied silently." A provisional link is therefore not
a tag of the document: FR-15's readers in `apps/api/repository.py` (`tags_of`, the facets and
the tag filters) must exclude `provisional=True`, a change that follows the apply layer. A
confirmation (`confirm_tag`) sets `confirmed=True, provisional=False` and leaves `applied_by`
as `ai`, so provenance survives the confirmation; a rejection deletes the link.

> **10 November 2026 (night), `documents 0009`: a rejection no longer deletes an AI link.** It
> sets `removed=True` and keeps the row, so the machine's assignment survives beside the
> person's decision (FR-10: "the machine assignment is retained alongside it") and the next
> classify or reprocess does not link the tag again. A link a person applied was still deleted,
> holding no machine assignment, until the requirements re-audit the same night: deleted, it was
> linked again by the next run that suggested it, so it is kept, marked removed, too. Every reader
> that excludes `provisional=True` excludes `removed=True` as well, `tag_details` included, while
> `tag_scheme` still counts a removed link as a link (D-105's dated note of that night; D-119
> finding 3).

### DocumentAnalysis — FR-10

Added on 8 November 2026 by `documents 0008_fr10_document_analysis` (migration v2; D-105),
when FR-10 was built. One row per document; written by `apps/documents/classification.py` and
by nothing else.

| Field | Type | Notes |
|---|---|---|
| `analysis_id` | UUID PK | |
| `doc_id` | UUID FK → Documents, unique | one-to-one; cascade delete |
| `machine_doc_type` | text, nullable | the model's type, one of `DOCUMENT_TYPES`; overwritten by every run |
| `machine_doc_type_confidence` | decimal(4,3), nullable | |
| `machine_department` | text | the model's department as suggested, stripped; blank for none |
| `machine_department_confidence` | decimal(4,3), nullable | |
| `doc_type` | text, nullable | the **effective** type, one of `DOCUMENT_TYPES`; null while a provisional suggestion awaits confirmation |
| `doc_type_outcome` | text, nullable | `ASSIGNMENT_OUTCOMES` — see §3 |
| `department_outcome` | text, nullable | `ASSIGNMENT_OUTCOMES` |
| `department_applied_by` | text, nullable | **`documents 0009`** — whose value `Documents.department` holds, in `TAG_APPLIED_BY_VALUES`: `user` a person gave it (typed at upload, or written through the confirm route); `ai` a run wrote its suggestion into a blank department and no person has written it since; null for no department, or a row classified before 0009 and not set since (D-119 finding 10) |
| `user_edited` | boolean | true once a person confirmed or edited the type or department; a re-run then updates only the `machine_*` columns, `model`, `input_truncated` and `classified_at` |
| `proposed_topics` (model field `proposed_tags`) | jsonb | **`documents 0012_proposed_tags`, D-128:** out-of-scheme Topic suggestions held for a person, at any confidence, `[{"dimension", "value", "confidence"}]` with `dimension` "Topic", deduplicated by normalised value; replaced by each run. The column keeps its first name (`db_column`) so that 0012 changes no column. 0012 stamped the earlier entries `"dimension": "Topic"`. For one day (D-128) it also held Project and Process values below the threshold; D-129 reversed that |
| `discarded_suggestions` | jsonb | suggestions that do not become a tag or a proposal, `[{"dimension", "value", "confidence"}]`; never shown; replaced by each run. The out-of-scheme Project and Process suggestions (Objective 05's clause 3), and since D-128 a value that cannot be stored (U+0000 or a lone surrogate), recorded with U+FFFD so that the column accepts it (D-129) |
| `rejected_tags` | jsonb | **`documents 0013_rejected_tags`, D-128 (the audit of 13 November):** proposals a person rejected on this document, `[{"dimension", "value", "confidence"}]`, one entry per dimension and value. The confidence is the machine's, kept beside the person's decision. Later runs neither propose, create nor link that value for this document, in any dimension, even after it enters the scheme. A person may still apply it. Never shown; never replaced by a run. A rejection made before 0013 was never recorded, so it is not honoured: existing rows start at `[]`, and none is guessed |
| `model` | text | the chat model that produced the run |
| `input_truncated` | boolean | the text was cut at `CLASSIFICATION_INPUT_TOKENS` before it was sent |
| `classified_at` | timestamp | set by each run, not `auto_now`: a confirmation edits the row without reclassifying it |

**Departures from the proposal's field table**, which gives `doc_type`, `department`, one
`confidence` and `user_edited`:

- **Two confidences, not one.** FR-10: "a confidence value is recorded with each assignment".
  The type and the department are two assignments, so each keeps its own, beside the machine
  value it belongs to.
- **The effective department is `Documents.department`**, not a column here. D-72 made that
  column the one source FR-14's and FR-15's department filters read, so the department FR-10
  applies is written there and there stays one source. The machine's suggestion stays in
  `machine_department`, so "the machine assignment is retained alongside it so that
  classification accuracy can be measured over time rather than being overwritten and lost".
- **An outcome per assignment** — `applied`, `provisional`, `discarded` or `confirmed` — so the
  record states how the rule disposed of each suggestion rather than leaving it to be inferred
  from which columns are null.
- **Two JSON lists, then three.**
  - **As first built (D-105),** a Topic outside the scheme "may be proposed only in the Topic
    dimension and requires user confirmation before it is created", so no `Tags` row could exist
    for it while it waited. A Project or Process outside the scheme was "discarded", and the
    discard was kept as evidence of that clause.
  - **Since D-128 (12 November 2026),** the list is `proposed_tags`, its entries carrying a
    dimension. For one day the classifier also created values at or above the threshold. Since
    D-129 it proposes a Topic outside the scheme at any confidence and discards a Project or
    Process value, as before.
  - **Since the audit of 13 November (D-128),** `rejected_tags` (`documents 0013`) keeps each
    proposal a person rejected, with the machine's confidence. Later runs skip that value for that
    document: FR-10's correction clause, "retained and is not overwritten by later reprocessing,
    and the machine assignment is retained alongside it".

No column holds a summary or key points: FR-10's front-end clause names them, and a *document's*
summary is still not built (D-104's note of 10 November 2026). FR-16's `summarise_meeting`
(D-125) summarises meetings, into `MeetingSummaries` above, and is not that.

### KnowledgeGaps — FR-19, FR-14

Added on 9 November 2026 by `retrieval 0004_fr19_knowledge_gaps` (migration v2; D-107), when
FR-19 was built. In `apps/retrieval`, beside the logs it aggregates (D-13). Written by
`apps/retrieval/gaps.py::run_cycle` and by `PATCH /api/knowledge-gaps/{id}`, and by nothing
else.

| Field | Type | Notes |
|---|---|---|
| `gap_id` | UUID PK | |
| `subject` | text | the first member's wording, verbatim; no model writes it |
| `occurrence_count` | integer | equals the entry's number of `KnowledgeGapItems` rows, always |
| `status` | text | `Open` or `Addressed` — see §3; new entries are `Open` |
| `first_seen_at` | timestamp | **v2** — the earliest member's time (not in the proposal's table) |
| `last_seen_at` | timestamp | the newest member's time |
| `embedding` | vector(`EMBEDDING_DIMENSION`), nullable | **v2** — the mean of the members' vectors; its direction is D-109's centroid |
| `embedding_model` | text | **v2** — the model the members were embedded by; a join candidate only for an item from the same model (risk R10) |

**Departures from the proposal's field table**, which gives `gap_id`, `subject`,
`occurrence_count`, `status` and `last_seen_at`:

- **`first_seen_at`**, so an entry says how long a subject has been asked about as well as when it
  was last asked.
- **`embedding` and `embedding_model`**, for D-109's grouping by similarity. They follow
  `ContentChunks`' rule: a provider switch starts new entries instead of comparing vectors that
  cannot be compared. **The column stores the mean of the members' vectors, not its normalised
  form.** D-109 compares an item with "the normalised mean of its members' vectors" by cosine,
  which ignores length, so the two give identical join decisions; the mean is kept because the
  next member's exact update, `(n * mean + v) / (n + 1)`, needs the length normalising discards.

No column holds an asker, a role, a department or a reason (D-107, D-108).

### KnowledgeGapItems — FR-19

Added by `retrieval 0004` with `KnowledgeGaps` (D-107). One row per log row in the gap log.

| Field | Type | Notes |
|---|---|---|
| `gap_item_id` | UUID PK | |
| `gap_id` | UUID FK → KnowledgeGaps | cascade delete |
| `query_id` | UUID FK → QueryLog, unique, nullable | **protect** on delete |
| `search_id` | UUID FK → SearchLogs, unique, nullable | **protect** on delete |
| `added_at` | timestamp | |

A check constraint, `knowledge_gap_item_exactly_one_source`, requires exactly one of `query_id`
and `search_id`. Both are unique, so a log row is counted once across every cycle, and a row
re-scanned in a later cycle's grace window is skipped. **FR-19 writes neither `QueryLog` nor
`SearchLogs`** (its CRUD line says Read): this table is how a row's membership is remembered
without a column on it. Both foreign keys **protect**, so `occurrence_count` cannot fall behind
its items through a deleted log row; nothing in the product deletes one. Only rows that survived
D-108's permission exclusion become members, and a row left out is recorded nowhere.

### KnowledgeGapCycles — FR-19

Added by `retrieval 0004` with `KnowledgeGaps` (D-107). One row per aggregation cycle, written last,
in the cycle's transaction.

| Field | Type | Notes |
|---|---|---|
| `cycle_id` | UUID PK | |
| `started_at` | timestamp | bounds the next cycle's window, less `CYCLE_GRACE_SECONDS` |
| `finished_at` | timestamp | |
| `triggered_by` | UUID FK → Users, nullable | the Administrator behind `POST /api/knowledge-gaps/cycles`; null for `manage.py aggregate_knowledge_gaps`; **set NULL** if the user is deleted |
| `queries_considered` | integer | `QueryLog` rows this cycle added to the log |
| `searches_considered` | integer | `SearchLogs` rows this cycle added to the log |
| `entries_created` | integer | entries this cycle started |
| `entries_updated` | integer | entries that existed when the cycle began and gained a member |

**The counts are of rows that entered the log, never of rows read.** D-107: "No count of rows
left out is stored or returned anywhere." A count of the window's rows, less the rows added, would
be that number, so no such count exists.

---

## 2. Deferred to NIT3004 — not in migration v1

| Table | Requirement | Tier |
|---|---|---|
| `LoginAttempts` | FR-03 account lockout interface | SHOULD |
| `MFARecoveryCodes`, `Users.mfa_enabled`, `Users.mfa_secret` | FR-07 | COULD |

Add these in migration v2 when their requirement is built. Do not create empty tables
now for work that may be descoped.

> **8 November 2026.** `DocumentAnalysis` (FR-10 classification, confidence) left this table
> for §1 when FR-10 was built: `documents 0008_fr10_document_analysis` creates it and adds
> `confidence` and `provisional` to `ContentTags` (D-105). The summary the row was deferred
> with is not in it; see the §1 entry.

> **9 November 2026.** `KnowledgeGaps` (FR-19 gap log) left this table for §1 when FR-19 was
> built: `retrieval 0004_fr19_knowledge_gaps` creates it, with `KnowledgeGapItems` and
> `KnowledgeGapCycles` (D-107). FR-14's `KnowledgeGaps (Read)`, deferred by D-69, is now the
> dashboard's knowledge-gap panel.

> **11 November 2026.** `MeetingSummaries` and `ActionItems` (FR-16) were never listed here, though
> they were deferred with the rest of NIT3004. `meetings 0003_fr16_meeting_summaries` creates both
> and `documents 0012_content_chunk_ai_generated` adds `ContentChunks.ai_generated` (D-125). The
> summary of a *document* that FR-10's front-end clause names is still not built (D-104's note).

---

## 3. Fixed vocabularies

```python
DOCUMENT_STATUS_VALUES = ("Processing", "Extraction failed", "Insufficient content",
                          "Too large to index", "Indexing failed", "Partially indexed",
                          "Indexed")
MEETING_STATUS_VALUES  = ("Received", "Indexed", "Processing failed")
CLASSIFICATION_DIMENSIONS = ("Department", "Project", "Process", "Topic")
SOURCE_TYPES = ("document", "meeting")
NO_ANSWER_REASONS = ("no_relevant_passage",     # nothing above RELEVANCE_THRESHOLD
                     "no_statement_verified")   # retrieved, but verification stripped all
# FR-10 (D-105), 8 November 2026:
DOCUMENT_TYPES = ("Policy", "Procedure", "Report", "Meeting Paper")
ASSIGNMENT_OUTCOMES = ("applied", "provisional", "discarded", "confirmed")
# FR-19 (D-107), 9 November 2026:
KNOWLEDGE_GAP_STATUS_VALUES = ("Open", "Addressed")
# FR-16 (D-125), 11 November 2026:
SUMMARY_STATUS_VALUES = ("Processing", "Ready", "Unavailable")
SUMMARY_FAILURE_REASONS = ("provider_unavailable", "provider_refused", "malformed",
                           "no_verified_narrative", "indexing_failed", "orphaned", "error", "busy")
ACTION_ITEM_ORIGINS = ("ai", "user")
```

These live in `apps/core/constants.py`. Status values are fixed rather than free text
so a status can be filtered on and its meaning does not drift.

`DOCUMENT_TYPES` is FR-10's fixed list: "the type must be selected from a fixed list rather
than generated freely, so that filtering remains consistent". `ASSIGNMENT_OUTCOMES` is how the
apply layer disposed of one assignment (`DocumentAnalysis.doc_type_outcome`,
`department_outcome`): **applied**, at or above `CLASSIFICATION_CONFIDENCE_THRESHOLD` and
written to the effective field, still marked AI-generated and editable; **provisional**, below
the threshold, held for confirmation and not written; **discarded**, outside the established
scheme (the department only — the type is always in the fixed list because the parser refuses
anything else); **confirmed**, a person confirmed or edited it, after which reprocessing leaves
it alone.

`KNOWLEDGE_GAP_STATUS_VALUES` is FR-19's "the ability to mark an entry as addressed": an entry
starts `Open`, and `PATCH /api/knowledge-gaps/{id}` moves it to `Addressed` and back. Only an `Open`
entry is a join candidate for D-109's grouping, so a subject that recurs after being addressed
opens a new entry.

`SUMMARY_STATUS_VALUES` are FR-16's own words: a summary is processing, "Ready" (the proposal's
example value), or "marked unavailable". `SUMMARY_FAILURE_REASONS` says why a run ended
Unavailable, for the operator and never for a user: the provider was unreachable after
`MAXIMUM_SUMMARY_ATTEMPTS`, it refused the request (D-118), two replies broke the schema, **no
narrative sentence named a passage that was sent** (FR-12's no-answer path (b) for a summary,
kept apart as invariant 7 keeps the two no-answer paths apart), the summary could not be
embedded, the server stopped mid-run, or something unexpected was raised. `ACTION_ITEM_ORIGINS`
is where an item came from: extracted by the model, or added by a person. `SOURCE_TYPES` did not
gain a value for a summary: its passages are the meeting's (D-125, choice 1).

`DOCUMENT_STATUS_VALUES` is the proposal's own §7.0 set. It **supersedes** the five
values this section carried until 2026-09-21 — `Uploaded`, `Extracting`, `Indexed`,
`Insufficient content`, `Processing failed` — which were written from the requirement
summaries, before `Project_8-proposal_complete_V4.5.docx` reached the team. See
**D-28** for the mapping and for why `Partially indexed` had to exist: §7.7 abandons a
chunk after `MAXIMUM_EMBED_ATTEMPTS`, and the superseded set had no status for a
document whose chunks partly embedded.

**`Too large to index` is the seventh value**, added on 2026-09-26 by Stage 4 item 12b
(`documents 0007_document_status_too_large_to_index`). `MAXIMUM_CHUNKS_PER_SOURCE`
refuses a document before the first embed call, and item 12a recorded that refusal as
`Indexing failed` — which in this vocabulary means *attempted, and every chunk failed*.
Nothing was attempted. The set already separated **refused before attempting, on a
property of the content** (`Insufficient content`) from **attempted and failed**
(`Indexing failed`), so the new value completes that distinction rather than
introducing one, which is D-28's own argument one state further on; it sits beside
`Insufficient content` for that reason rather than at the end. The proposal is silent
here, not contrary: `MAXIMUM_CHUNKS_PER_SOURCE` was settled in the week the value was
added and the proposal predates it.

The difference is user-visible, which is why the detail message was not enough. FR-08's
interface offers "Processing failed. Please try again" against a document that did not
index; a reprocess of an over-cap document fails identically every time, because nothing
about the file has changed, and D-32's retry re-runs extraction and chunking in full
before failing at the same point. **The front end suppresses the retry affordance for this
status** — done on 27 September 2026, not deferred to Stage 5: `canReprocess()` refuses it,
and the row carries a sentence explaining why no retry is offered rather than a button that
cannot honour one.

`MEETING_STATUS_VALUES` is untouched. The proposal defines no status column on
`Meetings` at all, only FR-09's CRUD line "Meetings (Create, Read, Update status)", so
these three values have nothing to contradict.

`MINIMUM_CONTENT_LENGTH` is counted in **tokens**, not characters, and a token is a
whitespace-delimited word (**D-31**). §7.5 and §7.8 both call `lengthInTokens()`, and
one function serves both the chunker and the insufficient-content check so the two
cannot drift.

---

## 4. Gaps and inconsistencies in the proposal

These are places where the source document does not settle the question. Each needs a
line in `docs/decisions.md`. Do not resolve them silently in code.

**G1 — `ContentChunks.source_id` is polymorphic.** The proposal writes it as
`UUID (FK → Documents/Meetings)`, which cannot be a real foreign key to two tables.
Recommendation: `source_type` + `source_id` with no database-level FK, matching the
pattern FR-10 already uses for `ContentTags` ("keyed on source type and identifier").
Enforce referential integrity in the application and cascade deletes explicitly. The
alternative — two nullable FK columns with a check constraint — keeps FK enforcement
but does not match the ContentTags pattern, so one join path would differ from the
other.

**G2 — `ContentChunks` has no embedding column in the proposal's tables**, despite
FR-08 requiring that "the embedding model and dimension are recorded against every
stored vector". The three columns above are the minimum that satisfies that clause.
This is an omission in the document, not a design choice.

**G3 — `Documents.department` vs `department_tag`.** FR-11 calls the column
`department_tag`; FR-12 and FR-14 call it `department`. Pick one and use it
everywhere. Recommendation: `department`, since two of the three sections use it.

**G4 — No `Sessions` table is defined.** FR-04 lists `Sessions (Delete)` in its CRUD
and requires server-side destruction on logout plus 60-minute inactivity expiry, but
gives no field list. Recommendation: use Django's own session framework rather than a
hand-rolled table — `django.contrib.sessions` gives server-side storage, deletion on
logout, and an inactivity expiry from `SESSION_COOKIE_AGE` with
`SESSION_SAVE_EVERY_REQUEST = True`. Record this as the decision; it satisfies the
requirement without inventing a table the proposal never specified.

**G5 — `visible_to_roles` as `text[]` is the proposal's shape**, holding role names
rather than role IDs. That denormalises the role name into every document row and
breaks if a role is renamed. Recommendation: keep the proposal's shape for v1 since
FR-11 is written against it and two roles will never be renamed in this project, but
note the limitation rather than presenting it as a design strength if asked at the
demonstration.

**G6 — Meetings has no permission filter** although FR-11 must scope meeting chunks.
Resolved by D-16: `Meetings.visible_to_roles` mirrors Documents; attendance is not an
access control. D-17 additionally stamps `visible_to_roles` onto every chunk.

**G7 — Documents has no column for the stored original** although FR-08 stores it.
Resolved by D-18: deferred to migration v2 at the start of Stage 3, because its shape
depends on the storage implementation. **Closed on 2026-09-21** by
`documents 0006_schema_v2_storage_and_status`: D-05 fixes storage as a local media
directory, so the column is a Django `FileField` reading `MEDIA_ROOT` from the
environment. `content_hash` and `file_size_bytes` land in the same migration, because
§7.2 and §7.8 record both on the document and FR-08's 409 is a comparison of content
rather than of filenames.

---

## 5. Ordering

Migrate in dependency order: Roles → Permissions → RolePermissions → Users →
Documents → ExtractedContent → Meetings → MeetingAttendees → ContentChunks →
Conversations → QueryLog → SearchLogs → AnswerCitations → Tags → ContentTags.
`DocumentAnalysis` (v2, `documents 0008`) follows Documents and ContentTags; the executor
plans it immediately after `documents 0007`, `documents 0009` (`ContentTags.removed`,
`DocumentAnalysis.department_applied_by`) immediately after 0008, `documents 0010`
(`Tags.grown`) immediately after 0009, and `documents 0011` (the backfill that marks grown every tag
only restricted material carries) immediately after 0010. 0011's backfill reads meetings'
`visible_to_roles`, so it depends on `meetings 0002`, and a clean start now plans `meetings 0002`
directly after `meetings 0001`, before `documents 0002`. Two migrations numbered 0012 follow 0011,
from two branches built at the same time. `documents 0012_content_chunk_ai_generated`
(`ContentChunks.ai_generated`, FR-16, D-125) is one. `documents 0012_proposed_tags` (D-128: the
proposal list renamed `proposed_tags` on its unchanged column, its entries stamped with a dimension)
is the other, and `documents 0013_rejected_tags` (`DocumentAnalysis.rejected_tags`) follows it.
`documents 0014_merge_fr16_and_d128` joins the two branches. It has no operations; it only gives
the app one leaf again, so neither pushed migration was renumbered or edited. The executor plans
0012_proposed_tags, 0013, 0012_content_chunk_ai_generated, 0014, then
`meetings 0003_fr16_meeting_summaries`.
`KnowledgeGaps`, `KnowledgeGapCycles` and `KnowledgeGapItems` (v2, `retrieval 0004`) follow
QueryLog and SearchLogs; the executor plans them immediately after `retrieval 0003`, and
`accounts 0007` (the `review_knowledge_gaps` seed) immediately after `accounts 0006`, and
`accounts 0008` (the `manage_tags` seed, D-119 finding 5) immediately after `accounts 0007`.

Enable the `vector` extension in its own migration before any table carrying a vector
column.
