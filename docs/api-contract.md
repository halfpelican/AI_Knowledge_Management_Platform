# API contract

The request and response shapes every endpoint honours. The front end builds against
this file; the tests assert it. Each stage appends its own endpoints.

**Stage 2 was rewritten on 2026-09-13 against the proposal's own FR text**, which
arrived after the endpoints were built. The earlier version was written from the
requirement summaries available at the time and was wrong in four places: the logout
status code, the code for an unknown role, the code for a malformed login address,
and the password rules. Where a status code below is still a *convention*, the FR
enumerates no code for that case and the choice is recorded in `docs/decisions.md`.

Conventions: JSON bodies; `Content-Type: application/json`; all paths under `/api/`;
authentication per D-21 (session cookie, `X-CSRFToken` on unsafe methods);
authorisation errors are `401 {"detail": "..."}` for no valid session and
`403 {"detail": "..."}` for a session whose role lacks the permission (`CLAUDE.md` §6
invariant 4). Validation errors are `400 {"field": ["message"], ...}` in DRF's shape.
Error messages never disclose whether an email address is registered, except the
409 on registration, which FR-01 specifies.

The user object, wherever a user is returned:

```json
{"id": "uuid", "name": "Ada Lovelace", "email": "ada@example.com",
 "role": "Employee", "created_at": "2026-09-12T10:00:00+10:00"}
```

Never `password_hash`, `failed_attempts` or `locked_until`.

## Stage 2 — FR-01, FR-02, FR-04, FR-05, FR-06

Every code below is quoted from the FR's own Responses clause unless marked
*convention*.

| Method | Path | Auth | Success | Failures |
|---|---|---|---|---|
| POST | `/api/auth/register` | none | `201` user object; role is Employee | `400` a field is missing, the address is not a valid format, or the password fails the complexity rules; `409` the address is already registered |
| POST | `/api/auth/login` | none | `200` user object; sets the session cookie and the `csrftoken` cookie | `400` a field is missing, or the address is not a valid format (checked before the database lookup); `401 {"detail": "Invalid email or password."}` for an unknown address, a wrong password, or a locked account whose password was also wrong, byte-identical in every case; `403 {"detail": "...", "code": "account_locked"}` only when the account is locked **and** the password matched |
| POST | `/api/auth/logout` | session | `200`; the session record is destroyed server-side | `401` no valid session |
| GET | `/api/auth/me` | session | `200` user object; refreshes the `csrftoken` cookie | `401` |
| GET | `/api/roles` | session | `200 [{"role_id": "uuid", "name": "Employee", "description": "...", "permissions": ["..."]}]` | `401` |
| GET | `/api/users` | Administrator | `200 [user object, ...]` ordered by `created_at` | `401`; `403` Employee |
| GET | `/api/users/directory` | session | `200 [{"id", "name", "email"}, ...]` ordered by name | `401` |
| PATCH | `/api/users/{id}/role` | Administrator | `200` updated user object; writes an audit entry | `400` the body is missing `role_id` or it is not a UUID; `401`; `403` Employee, or an administrator demoting themselves (*convention*: FR-05 enumerates only 200, 403 and 404); `404` the user or the role does not exist |

**The directory is not the user list (D-34).** `GET /api/users/directory` carries a
name and an address and nothing else — no role, no timestamps, no account state. It
exists because FR-09 gives attendee association to *any* user, while `GET /api/users`
is Administrator-only: it carries the role each person holds and drives role
management, so an Employee had no way to populate an attendee picker and FR-09's
clause was unreachable for them. Relaxing `GET /api/users` would have handed every
Employee the role of every colleague to satisfy a requirement that needs only their
name, so the two stay separate and a test asserts `GET /api/users` is still `403`
for an Employee. What the directory does disclose, stated rather than glossed: every
signed-in user can read every registered user's name and address. That is what a
staff directory is.

**FR-01 password complexity.** "min 8 chars, 1 uppercase, 1 number, 1 special
character", enforced server-side. The client shows the same rules as the user types
and keeps submit disabled until they all pass. Both derive from one policy so they
cannot drift.

**Rate limiting.** `POST /api/auth/register` and `POST /api/auth/login` are limited
per client address and answer `429` past the rate. No other route is throttled (D-26).

**FR-02 login side effects.** A failed attempt increments `failed_attempts`; five
consecutive failures lock the account for `LOCKOUT_DURATION`. While the lock holds,
login is `403` **only when the password also matched**; a wrong password against a
locked account is the ordinary `401`, indistinguishable from an unregistered address.
Past twice the threshold the lock stops being announced at all and every attempt gets
the `401`, so the lock bounds guessing and not merely the session (D-26).
Announcing the lock to anyone who merely knows an address would make it an
account-enumeration oracle, which is why the proposal's own login pseudocode branches
there. A success resets `failed_attempts` to 0, clears
`locked_until`, and sets `last_login_at`. The lock is FR-02's own clause and is
enforced here; FR-03 adds only the warning interface and stays out of the gate
(D-25).

**FR-05 role change.** The body is `{"role_id": "<uuid>"}`, matching the FR's
`{ user_id, new_role_id }`; the user id travels in the path. A user cannot remove
their own administrator role, and no change may empty the administrator set, so the
last administrator cannot be locked out by either route. Both refusals are `403`.

**FR-02 role-specific dashboard.** Login sends an Administrator to `/admin` and an
Employee to `/dashboard`, unless the user was bounced off a guarded route, in which
case they return there. Both routes exist; FR-14 replaces what they render in Stage 5,
so today the destination differs by role and the content does not.

Session: 60-minute inactivity expiry (D-10). An expired or invalid session cookie is
`401` on every route that needs one.

Response bodies the front end relies on (Stage 2 implementation):

- `409` on registration: `{"detail": "This email address is already registered."}`.
  The client shows it under the email field, as FR-01 requires, rather than as a
  form-level banner.
- `403`: `{"detail": "Your role does not hold the 'manage_roles' permission."}`.
- Unmatched path: JSON `404 {"detail": "Not found."}`.
- CSRF: `POST /api/auth/logout` and `PATCH` always require `X-CSRFToken`; so does
  `POST /api/auth/login` when the browser already holds a session.
- `POST /api/auth/register` starts no session (D-23).
- Any endpoint, a request body that is not `application/json`: `415`. The API parses
  JSON only, which is what stops a cross-site form from posting credentials (D-24).

## Stage 3 — FR-08, FR-09

Every code below is quoted from the FR's own Responses clause unless marked
*convention*.

| Method | Path | Auth | Success | Failures |
|---|---|---|---|---|
| POST | `/api/documents` | session + `contribute_content` | `201` document object, carrying `doc_id` | `400` no file, or an empty title, or a `visible_to_roles` that is empty or names an unknown role; `401`; `403` the role lacks `contribute_content`, or the list excludes the uploader's own role (*convention*, D-29); `409` a document with the same content already exists; `413` over 50 MB, or a DOCX or XLSX whose members declare more decompressed content than a parser may inflate (*convention*, Stage 4 item 12b — a size rejection of decompressed size, carrying its own message, not the 415); `415` the file signature is not one of the four accepted formats; `422` the document was stored but no text could be extracted, or it holds too little text to index, or every chunk failed to embed |
| POST | `/api/documents/{id}/reprocess` | session + `contribute_content` | `201` the document object, now `Indexed` or `Partially indexed` | `401`; `403` the role lacks `contribute_content`; `404` no such document, or one outside the caller's scope; `409` already indexed, or restoring its content hash collided with a copy indexed meanwhile; `422` the reprocess failed the same way the upload did |
| GET | `/api/documents` | session | `200 [document object, ...]`, newest first, scoped to the caller's role | `401` |
| GET | `/api/documents/{id}` | session | `200` document object | `401`; `404` no such document, or one outside the caller's scope |

The document object:

```json
{"doc_id": "uuid", "title": "Leave Policy 2026", "file_type": "pdf",
 "status": "Indexed", "uploaded_at": "2026-09-21T10:00:00+10:00",
 "department": "", "visible_to_roles": ["Employee", "Administrator"],
 "file_size_bytes": 14203, "uploaded_by": "erin@example.com"}
```

Never `file_path` (a path inside `MEDIA_ROOT`, of no use to a client and an
invitation to construct one) and never `content_hash` (it exists to answer the 409,
and echoing it would let a caller probe whether a document they cannot see has
already been uploaded).

**The request is `multipart/form-data`**, and this is the only endpoint that accepts
anything other than JSON. The global JSON-only parser (D-24) is what stops a
cross-site HTML form reaching an *anonymous* endpoint; it is not what protects this
one. This route requires a session, and DRF enforces CSRF as soon as its session
authenticator resolves a user, so a cross-site multipart POST is rejected for want of
the token.

Fields: `file` (required), `title` (required, non-blank), `department` (optional),
`visible_to_roles` (optional, repeated field, each value a role name).

**The rejection order is fixed** by the proposal's §7.2 `validateUpload()` and is
part of the contract, not an implementation detail: contribute permission (403),
then signature (415, **or the 413 below where the archive declares more decompressed
content than may be inflated — the same step, a different rejection**), then size
(413), then title (400), then duplicate (409). §7.2
says why the permission is first — "it is the cheapest rejection, and the user's role
may have changed during a transfer of up to 50 MB".

**The size ceiling is applied twice**: once against the declared `Content-Length`,
before the body is parsed, so a 50 MB transfer is refused without being buffered; and
once against the bytes actually received, for a client that lies about or omits the
header.

**A third size rejection shares the 413 and does not share the message** (Stage 4
item 12b). Both checks above are checks on the *upload*, and a 199 KB DOCX whose
`word/document.xml` declares 200 MB passes both: the size that matters there is the
decompressed one. The signature step now reads every member's declared size out of the
archive's central directory — no member is inflated to do it — and refuses a DOCX or
XLSX declaring more than `MEMBER_MAXIMUM_BYTES` in one member or
`ARCHIVE_MAXIMUM_DECLARED_BYTES` across all of them (`apps/ingestion/signatures.py`,
which also records why a declared size cannot usefully lie). It is **413 and
deliberately not the neighbouring 415**: the file's format is not the problem, it is a
real DOCX, and answering "File type not supported" would send its uploader to convert
something that was never the wrong type — the argument that made a NUL byte in a
search term its own rejection rather than "too short". Its message names decompressed
size and never the 50 MB transfer limit, which does not apply to it. **The protection
is OOXML-only: PDF is not covered**, because `pypdf` inflates object streams with no
ZIP involved, and that gap is stated rather than implied.

The same bound applies to an uploaded FR-09 transcript file, which reports it as a
`400` on the `file` field with the same message, because FR-09 enumerates only `201`
and `400`.

**Format is decided by content, never by extension.** FR-08: "file type is confirmed
by inspecting the file signature rather than the extension alone, preventing a
disguised file from being accepted". `ACCEPTED_EXTENSIONS` gates only the upload
control's own pre-transfer check, client-side, and admits nothing on the server.

**Duplicates are compared by content hash, not filename** (§7.2), "so that the same
document uploaded under two different names is still caught".

**`visible_to_roles` (D-29).** Omitted means both roles: a document nobody thought
about is visible to everybody, so an omitted field can never accidentally hide
content. An empty list is `400` — "visible to nobody" is not something anyone means
to ask for, and FR-11 would filter such a document out of every search in silence. A
list excluding the uploader's own role is `403`, because uploading into a scope you
cannot read is how content is lost.

**The retry re-runs ingestion on the stored original (D-32).** FR-08's interface
shows a "Processing failed. Please try again" action against a document that did not
index. That action calls `POST /api/documents/{id}/reprocess`, which re-reads the
file already under `MEDIA_ROOT` — invariant 8 kept it — rather than asking for the
upload again: a re-upload would create a second row per attempt and leave FR-15's
list full of near-identical entries.

**A failed ingestion reserves no duplicate slot.** On every `422` the row is
committed with `content_hash` NULL, so re-sending the same bytes is an ordinary
fresh upload rather than a `409`. A successful reprocess restores the hash, so an
indexed document is protected by the duplicate check exactly as one indexed on the
first attempt is. Several failed attempts at one file coexist, because Postgres
permits many NULLs under a unique constraint.

**What the retry can and cannot do.** FR-08 ties the action to extraction failing,
but a scanned PDF with no text layer parses identically however many times the same
bytes are submitted. The retry genuinely recovers only an `Indexing failed` — a
provider outage. The action is shown in every case the clause names; its wording
differs by status so it stops promising what identical bytes cannot deliver. D-32
records this as a flaw in the requirement rather than in the build.

**`GET /api/documents/{id}` was added at Stage 4 item 10b, for FR-12 (D-46).** It is in
this table rather than in the Stage 4 section because it is a document route and a reader
asking what the API offers for a document should find all three in one place — and because
FR-15 (Stage 5) reads it for its detail screen rather than adding one of its own, so it
outlives the clause that prompted it. The clause that prompted it is FR-12's "each
citation … links to the source document or meeting": `GET /api/meetings/{id}` had served
the meeting half since Stage 3, and a document citation could only be pointed at the list.

Its authorisation is `GET /api/documents`'s exactly — a session, and no permission beyond
it, because reading a document one's role may see is not a privileged action and a citation
must stay followable for the role the answer was generated for. **A document outside the
caller's scope is `404`, never `403`.** A 403 distinguishes "exists but you may not see it"
from "does not exist", which is the disclosure `CLAUDE.md` invariant 1 forbids by name; the
precedent is D-33's treatment of the upload `409` as an existence oracle, and the sibling
behaviour is `GET /api/meetings/{id}`. An unknown id and an out-of-scope id are answered by
the same scoped query, so the two replies are identical in status and in body. The response
is the document object above, so `file_path` and `content_hash` are absent here for the
same reasons.

**`GET /api/documents` is scoped by `visible_to_roles` from the first day it exists.**
FR-11 is Stage 4 work and this is not that filter, but a list disclosing documents
outside the caller's scope would be a leak to remove later rather than a feature
(`CLAUDE.md` §6 invariant 1: not by a result count, a total, or an error message).
FR-15's filtered browsing builds on this in Stage 5.

### FR-09 — meeting transcripts

| Method | Path | Auth | Success | Failures |
|---|---|---|---|---|
| POST | `/api/meetings` | session + `contribute_content` | `201` meeting object, carrying `meeting_id` | `422` the transcript was stored but every chunk failed to embed (*convention*: FR-09 enumerates only 201 and 400, and this mirrors FR-08's code for the same condition); `400` a missing or empty title, a missing date, a date in the future, a transcript below the minimum length, neither text nor file, both text and file, an unreadable file, or an attendee who is not a registered user; `401`; `403` the role lacks `contribute_content`, or `visible_to_roles` excludes the ingester's own role |
| GET | `/api/meetings` | session | `200 [meeting object without `transcript_text`, ...]`, newest first, scoped to the caller's role | `401` |
| GET | `/api/meetings/{id}` | session | `200` meeting object **with** `transcript_text` | `401`; `404` no such meeting, or one outside the caller's scope |

The meeting object:

```json
{"meeting_id": "uuid", "title": "Q3 Planning Sync", "meeting_date": "2026-07-28",
 "status": "Indexed", "created_at": "2026-09-21T10:00:00+10:00",
 "visible_to_roles": ["Employee", "Administrator"],
 "attendees": ["erin@example.com"], "transcript_text": "..."}
```

**The transcript arrives as pasted text or as a file**, which is FR-09's "upload a
transcript file or paste transcript text directly into a form". JSON carries
`transcript_text`; multipart carries `file`. Supplying both is `400` rather than a
silent preference, because whichever the server picked the other would be discarded
without the user knowing which. An uploaded file goes through the same signature
check and the same parsers as FR-08 — FR-09 says the transcript is "passed to the
chunking and embedding process in FR-08", and a second extraction path would be a
second thing to keep correct.

**Too little content is `400` here and `422` on a document.** FR-09's Responses
clause names "400 Bad Request for missing fields or insufficient content"; FR-08's
names 422. Each requirement gets the code its own clause names rather than one being
made to match the other. The threshold itself is the same `MINIMUM_CONTENT_LENGTH`,
counted by the same token definition the chunker uses (D-31).

**The date may not be in the future**, compared in the project's own timezone
(`TIME_ZONE`) rather than UTC — a meeting minuted this morning in Melbourne is
otherwise "tomorrow" for part of the day. Today is accepted; the boundary has a test.

**Speaker and timestamp parsing is out of scope for this version**, which FR-09
states explicitly. The transcript is stored verbatim — out of scope means untouched,
not quietly stripped, and a test asserts the labels survive into the stored chunks.

**Attendees are a participation record, never an access control (D-16).** Meetings
are scoped by `visible_to_roles`, mirroring documents exactly, and the scoping code
does not consult `MeetingAttendees` at all. An Employee who attended a meeting
visible only to Administrators still cannot read it; there is a test that says so by
name. Knowledge has to outlive the people who were in the room, and a second scoping
mechanism would mean two code paths through the one filter that matters most.

**A meeting outside the caller's scope is `404`, not `403`.** A 403 would confirm
that the id names something real (`CLAUDE.md` §6 invariant 1).

## Stage 4 — FR-12, FR-13

FR-12 is two paths, and both are contracted here: the keyword search immediately below,
and `POST /api/ask` further down, which returns an answer built from cited statements and
is also FR-13's conversational turn.

### FR-12 — keyword search

FR-12's Responses clause names `200 OK with grouped results` and `400` for an invalid
query; the codes below are its own except where marked *convention*.

| Method | Path | Auth | Success | Failures |
|---|---|---|---|---|
| GET | `/api/search?q=<term>` | session | `200` grouped results, scoped to the caller's role; also `200` when nothing matched | `400 {"q": ["..."]}` `q` was not sent, or the term is shorter than `MINIMUM_SEARCH_LENGTH` (2 characters), which includes `?q=`; `401` |

The reply:

```json
{"query": "annual leave",
 "documents": {"count": 2, "results": [ ... ]},
 "meetings":  {"count": 1, "results": [ ... ]},
 "total_count": 3}
```

Each result in either group:

```json
{"source_type": "document", "source_id": "uuid", "title": "Leave policy",
 "snippet": "...may take annual leave once probation has ended...",
 "department": "People", "date": "2026-09-21T10:00:00+10:00"}
```

Those are the four things FR-12's Front-End clause says a result shows — "its title, the
matching passage as a snippet, its department, and its date" — plus the type and
identifier the front end links with. `source_type` is `"document"` or `"meeting"`, from
the same fixed vocabulary the chunks use. Never `file_path` and never `content_hash`,
for the two reasons the document object gives above; a search result is built from the
scoped query's own output and not from the `Document`, `Meeting` or `ContentChunk` row,
so neither column is reachable from it at all.

**No route of this endpoint adds a role permission.** A session is the whole
authorisation, exactly as on `GET /api/documents`: what a search may find is decided by
the scope, not by a permission code, and a role that may list the repository may search
it.

**The counts are computed after permission filtering, so a total never discloses
inaccessible content.** `count` is derived from the rows in the group it labels and
`total_count` from the two counts, in `apps/retrieval/search.py`, as properties rather
than stored integers — the serializer reads them and computes nothing. There is
therefore no "showing n of m" anywhere in the reply, and no wider figure exists to be
put there: `CLAUDE.md` §6 invariant 1 forbids disclosing out-of-scope material "by a
result count, a total, or an error message", and a grouped search reply is mostly
counts.

**The same term returns different counts to different roles, and that is by design.**
An Employee and an Administrator searching one word over one corpus are told different
numbers whenever a matching source is Administrator-only. The Employee's count is what
the Employee can see, not what exists, and there is no signal — no count, no total, no
message, no altered wording — that anything was withheld. A test asserts the restricted
title, passage and identifier appear nowhere in the Employee's rendered body.

**Results are ordered by recency, never by relevance.** Documents newest-uploaded first,
meetings newest-met first, character for character the orderings `GET /api/documents`
and `GET /api/meetings` use, so one corpus does not appear in two orders in one
interface. Nothing on this path embeds, ranks or scores: §7.10 excludes it from the
pseudocode because "it is a filtered read rather than an algorithm", and an order
presented as relevance that was not computed from relevance is precisely what FR-12
rejects on its other path. A result is one item, not one matching chunk, so
`"documents": {"count": 3}` means three documents.

**A title match counts as a match.** A search for the name of a handbook finds the
handbook even where the title appears nowhere in its body. Two visible consequences: a
source that matched only by title carries the opening of its first passage as its
snippet, which does not contain the search term; and a source with no indexed passage at
all — an FR-08 "Insufficient content" document — carries `"snippet": ""`. Both are
honest renderings rather than invented text.

**`department` is `""` for every meeting**, permanently and by decision: schema v1 gives
`Meetings` no department, deriving one from attendees would reintroduce attendance into
a role-scoped path (D-16), and a literal like "Meeting" would put the item's type in the
column that says which part of the organisation it came from. A document may also have a
blank department, so an absent one is already a case the front end renders.

**Every search writes one `SearchLog` row**, including one that found nothing — a term
that returns nothing twice a day is a knowledge gap, which is FR-19's evidence.
`result_count` is the same post-filter total the caller is given, so the record and the
screen cannot disagree. A `400` writes no row at all: a query too short to run was not a
search, and counting it would put noise into that evidence.

**The term is stored and matched exactly as typed**, with no stripping and no sanitiser.
It reaches the database only as a bound parameter of an ORM lookup, and `%` or `_` in a
term match those characters rather than acting as wildcards. One consequence stated
rather than hidden: a two-character query of whitespace is long enough and matches
almost everything the caller may already list — odd-looking, but every row it can reach
is in scope.

### FR-12 — the answer path, which is also FR-13's turn

One endpoint serves both, because FR-13 says so: "Answer generation and citation
verification follow FR-12 unchanged", and each turn "triggers a fresh retrieval based on
the resolved question rather than reusing the previous turn's passages". A separate
conversational route would be the same call with a conversation attached, and two routes
through generation is two places for the permission scope to be got wrong.

Every code below is FR-12's own except where marked *convention*: its Responses clause
names `200 OK with ... answer and citations`, `200 OK with answered: false where nothing
was sufficiently relevant or no statement survived verification`, `400` for an invalid
query and `503 Service Unavailable where the AI service cannot be reached after retries`.

| Method | Path | Auth | Success | Failures |
|---|---|---|---|---|
| POST | `/api/ask` | session | `200` the answer: verified statements, each with its `chunk_id`, and the sources consulted; also `200` with `answered: false`, the fixed no-answer message and any partially related items found | `400 {"question": ["..."]}` no question was sent, or its length is outside `MINIMUM_QUESTION_LENGTH`–`MAXIMUM_QUESTION_LENGTH`; `400 {"conversation_id": ["..."]}` the id is not a UUID; `401`; `404` (*convention*) a well-formed `conversation_id` that is not this caller's; `503` the AI service could not be reached after `MAXIMUM_GENERATION_ATTEMPTS` |

The request:

```json
{"question": "How much annual leave do I get?", "conversation_id": "uuid"}
```

`conversation_id` is optional. Omitted, the question is a one-off and its `QueryLog.conversation`
stays NULL, which is that column's documented meaning (D-12). Present, the question is a
turn of that thread and the prior questions of it are composed into the retrieval and the
prompt (D-42).

The reply, answered:

```json
{"answered": true, "message": null, "result_count": 2,
 "statements": [{"position": 1, "text": "Staff accrue twenty days a year.",
                 "chunk_id": "uuid"}],
 "sources": [{"source_type": "document", "source_id": "uuid",
              "title": "Leave Policy 2026", "date": "2026-09-21T10:00:00+10:00",
              "passages": [{"chunk_id": "uuid", "text": "Staff may take annual leave..."}]}],
 "partial_matches": [],
 "conversation": {"conversation_id": "uuid", "title": "Leave policy questions",
                  "last_updated_at": "2026-09-24T09:26:00+10:00"}}
```

The reply, not answered:

```json
{"answered": false,
 "message": "This question cannot be answered from the available knowledge base.",
 "result_count": 0, "statements": [], "sources": [],
 "partial_matches": [{"source_type": "document", "source_id": "uuid",
                      "title": "Parental leave guidance",
                      "date": "2026-07-14T11:30:00+10:00"}],
 "conversation": null}
```

**The key set is the same on every exit**, so the two shapes above are one shape with
different contents. That is one branch in the front end rather than two response formats,
and it is what makes the paragraph below true without the serializer arranging anything.

**The two no-answer paths are one reply, byte for byte.** Section 7.10 returns
`response(200, answered = FALSE, message = NO_ANSWER_MESSAGE)` from step 6 — nothing
cleared `RELEVANCE_THRESHOLD`, so generation was never called — and identically from step
10, where passages were supplied and no statement survived verification. A caller must not
be able to tell which happened: the second discloses that material exists which could not
be cited, which is the disclosure `CLAUDE.md` §6 invariant 1 forbids and the one a user
would act on ("there *is* something there, keep asking"). **`no_answer_reason` and
`rejected_count` are therefore record-only and no response body carries either**, on this
route or on the conversation read below. They live in `QueryLog`, for the team reading the
log, and invariant 7 is what they are for. A test asserts both are absent from the raw
rendered body, and that the two paths' bodies compare equal while their rows carry
different reasons.

**A no-answer reply carries `result_count` 0 and no sources**, on both paths. On path B
passages genuinely were supplied to generation, so a non-zero count would be the more
literal report of what happened, and it is still wrong: any other value would make the
count the field that leaks which path was taken. The identifiers of what was supplied are
in `QueryLog.retrieved_chunk_ids`, which is the traceability record and is not part of any
reply.

**`partial_matches` is FR-12's "partially related items", and it is present on every
reply.** The clause is one sentence of the Front-End section: "Where no sufficiently
relevant content is retrieved, the interface states plainly that it cannot answer from the
available knowledge base and does not present a speculative answer. Any partially related
items found are offered, clearly labelled as partial matches." Each entry carries exactly
four sub-fields — the same four shapes a search result and a Sources panel entry use:

```json
{"source_type": "document", "source_id": "uuid", "title": "Parental leave guidance",
 "date": "2026-07-14T11:30:00+10:00"}
```

`source_type` is `"document"` or `"meeting"` from the same fixed vocabulary; `date` is the
source's own date, `uploaded_at` or `meeting_date`, rendered by the same field the listing
endpoints use.

- **Derived from the ranked, permission-scoped candidates, irrespective of the
  threshold.** It is taken from the output of ranking *before* `RELEVANCE_THRESHOLD` is
  applied, so an item that came close is offered whether or not it cleared the floor. The
  scope is not in question and is not applied twice: the candidate set was restricted in the
  query before it was ranked (invariant 1), so every item named is one the asking role may
  read, and a second filter here could only disagree with the first. A test asserts that an
  Administrator-only document nearer the question than anything an Employee may read appears
  nowhere in the Employee's rendered body, and that the same document *is* offered to an
  Administrator asking the same question — the weakest way to pass the first assertion would
  be a field that is empty for everybody.
- **Identical on both no-answer paths, by design.** It is derived once, from the
  pre-threshold ranked list, above the point where path A returns, and both no-answer
  replies are built from that one value. A list derived from anything that differs between
  the paths — the admitted set, the passages supplied to generation, the statements
  verification rejected, or a count of any of them — would hand a caller the distinction the
  paragraphs above keep in `QueryLog`: that material existed which could not be cited. A
  test asserts the two rendered bodies compare equal with the list non-empty on both.
- **No passage text, and no score.** There is no `snippet`, no `text` and no `passages` key,
  and the objects behind the field have no attribute for any of them. A fragment of source
  text sitting under a message that has just said the question cannot be answered reads as a
  partial answer — an uncited factual statement in all but name, which is invariant 6
  arriving by a side door, and FR-12's own "does not present a speculative answer" in the
  sentence before. A title, a type and a date are an offer to go and read something, which
  is what the clause asks for. A score is withheld for the reason it is withheld everywhere
  else in this API: it would invite the reader to treat the nearest item as the answer.
- **One entry per source, capped, in rank order.** A document with five near-miss passages
  is one item, because a list whose length counts chunks misdescribes the corpus — the rule
  `GET /api/search` already follows. The cap is `MAXIMUM_PARTIAL_MATCHES` in
  `apps/retrieval/partial_matches.py` (5): `TOP_K` is 25, and twenty-five items under a
  notice saying the question cannot be answered stop reading as "you might look at these"
  and start reading as the result set the notice has just denied.
- **Present on every exit, and empty on an answered reply.** The key set does not vary
  between outcomes — `message` is present and null on an answered reply for the same reason
  — so one client branch renders both. An answered reply carries `[]`: the clause is about
  the no-answer state, that reply already lists every item consulted with its date, and a
  second list of items that did *not* make it into the answer, beside statements citing the
  ones that did, would present unadmitted material as though it supported the answer. It is
  also `[]`, rather than absent, where the caller's scope holds nothing rankable at all.
- **A stored turn carries none.** The conversation detail route returns no
  `partial_matches` for a past turn, as it returns no `sources`: nothing records what a
  turn's ranking found, and the field would have to be invented to be filled.

This replaced a front-end heuristic. Until Stage 4 item 10a the screen built this list
itself, from `GET /api/search` on one word plucked out of the question, because the search
endpoint matches a term as a single substring and a whole question matches nothing. Those
were keyword hits rather than near misses, and each no-answer cost an extra request and an
extra `SearchLog` row. Both are gone.

**Every statement carries its `chunk_id`, and there is no field for one that does not.**
Invariant 6: there is no interface state that shows an uncited factual statement. A
statement whose citation was absent, unrecognised or fabricated is removed by
`verifyCitations` before the pipeline returns, and `RetrievalOutcome` carries no list of
rejected statements for a serializer to reach — so the guarantee is that the text is
unreachable rather than that no view chose to render it. `position` starts at 1 and is the
same number stored on that statement's `AnswerCitation` row, so FR-12's "numbered inline
citations" and the traceability record cannot disagree. No prose is composed server-side:
the statements arrive as a list and the interface places the markers, because a single
string with "[1]" spliced into it cannot be re-checked against anything afterwards.

**`sources` is every item CONSULTED, not only every item cited.** FR-12: "a Sources panel
lists every item consulted with its date, allowing the user to judge how current the
underlying material is", which is section 7.10 step 11's
`resolveSourceDetails(suppliedPassageIds)`. A panel listing only the items a surviving
statement happened to cite would misdescribe what the answer was drawn from. Each entry
carries the passages of that item that were supplied, because FR-12 also requires that
"each citation expands to display the source passage and links to the source document or
meeting" and no endpoint in this API returns a chunk — so the passage travels with the
answer built from it. `date` is the source's own date, `uploaded_at` for a document and
`meeting_date` for a meeting, rendered by the same field `GET /api/documents` and
`GET /api/meetings` use, so one row never appears with two date strings in one interface.
FR-12's "links to the source document or meeting" is `GET /api/meetings/{id}` for a meeting
and `GET /api/documents/{id}` for a document — the second added at Stage 4 item 10b (D-46),
before which a document citation could only be pointed at the repository list.
**No similarity score is exposed**: it is a tuning signal for the team, and an interface
showing it would present relevance as a fact about the answer.

**A `conversation_id` that is not the caller's is `404`, never `403`.** This is the one
status code on this route that the FR does not name, and it is load-bearing rather than
tidy. A 403 confirms that the id names a real thread, which is the disclosure invariant 1
forbids and the rule `GET /api/meetings/{id}` already follows. It also has a second job: the
conversation history read is filtered by conversation **and** user, so passing a foreign
thread would yield no history rather than someone else's questions — but the turn's
`QueryLog` row would still be written against that thread, and would then surface in its
owner's reopened thread as a turn that is not theirs. The row is fetched with the user as a
predicate and anything else is 404; a test asserts that no `QueryLog` row was written.

**The length rule is the pipeline's, and the request serializer does not restate it.**
`MINIMUM_QUESTION_LENGTH` and `MAXIMUM_QUESTION_LENGTH` are checked in
`apps/retrieval/pipeline.py`, which raises, and the view maps the exception — the same
arrangement the keyword search uses for its minimum term length (D-41), so there is one
definition of "too short" and the two cannot drift. Both bounds are inclusive. The question
travels character for character, with no trimming and no sanitiser, and `QueryLog.question`
stores it as asked.

**One sequence is neutralised on the way into the prompt, and only there (D-45).** A
question containing the prompt's own passage label, `[chunk_id: <uuid>]`, would inject a
pseudo-passage into the asker's own prompt, so those square brackets become round ones
before the question reaches generation — every other character is untouched, and nothing is
trimmed. It is a targeted transformation of one known sequence and not a sanitiser; D-45
says at length why a general sanitiser is the wrong instrument here. It changes nothing a
caller can observe: the reply is unaffected, and `QueryLog.question` still holds the
question as asked, delimiter included, because the record is evidence of what was typed.

**`503` is NFR-19's**, which requires "a 503 Service Unavailable response with an
informative notice, rather than crashing or hanging indefinitely". It is reached after
`MAXIMUM_GENERATION_ATTEMPTS` — one initial call and two retries — or on a transport
failure while embedding the question. **An outage is never converted into a no-answer**:
"the system could not ask" and "the corpus has no answer" are different events and
invariant 7's signal depends on them staying apart. No `QueryLog` row is written, as 7.10
returns its 503 without calling `recordQuery`, so the notice says the question was not
recorded and can safely be asked again.

**A question outside the caller's scope cannot reach the reply, the log or the provider.**
The candidate set is restricted in the query, before ranking (invariant 1), and there is a
test asserting that an Administrator-only passage nearer the question than any visible one
appears nowhere in an Employee's rendered body, moves their `result_count` by nothing, and
was never put in front of the AI service.

### FR-13 — conversations

FR-13's Database clause is `Conversations (Create, Read, Update)`, and its Front-End clause
needs three things of them: previous conversations listed, a conversation reopened with its
thread, and the active thread cleared to begin a new topic — which is starting a new
conversation, not deleting one. FR-13 enumerates only `200 OK with the answer and updated
conversation state`, which describes the turn rather than the thread, so every code below
is *convention* and follows the rest of this contract.

| Method | Path | Auth | Success | Failures |
|---|---|---|---|---|
| GET | `/api/conversations` | session | `200 [conversation object, ...]`, newest activity first, the caller's own only | `401` |
| POST | `/api/conversations` | session | `201` conversation object | `400` a title over 255 characters; `401` |
| GET | `/api/conversations/{id}` | session | `200` conversation object **with** `turns` | `401`; `404` no such thread, or one that is not the caller's |

The conversation object, which is also the `conversation` field of an `/api/ask` reply:

```json
{"conversation_id": "uuid", "title": "Leave policy questions",
 "last_updated_at": "2026-09-24T09:26:00+10:00"}
```

Never `user`: every thread a caller can reach is their own, so the field would only echo
the requester back to themselves and would invite a client to send one.

The thread, on the detail route:

```json
{"conversation_id": "uuid", "title": "How do I request annual leave?",
 "last_updated_at": "2026-09-24T09:26:00+10:00",
 "turns": [{"question": "How do I request annual leave?", "answered": true,
            "asked_at": "2026-09-24T09:25:00+10:00", "message": null,
            "statements": [{"position": 1, "text": "Your manager approves it.",
                            "chunk_id": "uuid"}]}]}
```

Turns are chronological and each answered turn's statements are in the order they were
numbered in, so a reopened thread reads as it did when it was live. An unanswered turn
carries `answered: false`, the same fixed `message` the live reply carried, and no
statements. **A turn carries no `no_answer_reason`, no `rejected_count` and no
`retrieved_chunk_ids`**: the first two for the reason the answer path gives — a thread read
is a second route past them — and the third because it records what was put in front of the
model, including passages nothing cited, which is traceability rather than something the
reader was shown.

**One turn in three states, and a sixth key on exactly one of them** (Stage 4 item 1c):

| State | `answered` | `message` | `provenance_removed` |
|---|---|---|---|
| answered, and still readable by this reader | `true` | `null` | absent |
| never answered, **or** answered and re-scoped away from this reader | `false` | `NO_ANSWER_MESSAGE` | absent |
| answered, and its citation rows no longer exist | `false` | `PROVENANCE_REMOVED_MESSAGE` | `true` |

The second row is two states in one rendering **on purpose**: a turn whose statements were
drawn from material the reader's current role may no longer see is byte-for-byte a turn that
was never answered, because a notice that something was removed is itself a disclosure that
material exists which this role may not read (invariant 1). `provenance_removed` is therefore
**absent unless it is true** — a key present and false on a re-scoped turn would be a new
place for that notice to grow.

The third state is not a permission state at all and says nothing about one.
`AnswerCitation.chunk` is `on_delete=CASCADE` (D-12), and both
`POST /api/documents/{id}/reprocess` and `manage.py reindex` delete a source's chunks and
write new ones with fresh identifiers, so every citation of the old ones is destroyed while
the passage still exists, word for word, under a new id. The turn carries no statements
(invariant 6) and its own message, because `NO_ANSWER_MESSAGE` would tell the reader their
question cannot be answered from the knowledge base, which is false of material that is still
indexed. **No count of what was lost**, in either state.

**Where a title comes from (D-43).** `Conversations.title` is a non-blank column and FR-13's
interface never asks the user to name a topic before typing — it clears the thread and lets
them start. So `title` is **optional on create**: supplied, it is used as sent; omitted or
blank, the thread is created as "New conversation" and **the first turn through
`POST /api/ask` replaces that with that turn's question**, truncated to the column width.
That replacement is the `Update` in FR-13's CRUD, alongside the `last_updated_at` the
pipeline touches on every turn. Both conditions are required for the rename — the
placeholder still standing and no turn logged yet — so a title the user chose is never
overwritten and a thread in use is never renamed under them. What keeps the list legible is
therefore the question itself, which is what the user would have typed as a name anyway;
the placeholder is visible only in the gap between creating a thread and asking in it.

**There is no rename route and no delete route.** FR-13's CRUD has no Delete, and its
interface has no rename control, so the two server-side updates above are the whole of
`Update`; `DELETE` on either path is `405`. Clearing the active thread is `POST
/api/conversations`, and the old thread's `QueryLog` rows are FR-19 evidence that survives
deletion on purpose (D-12) — deleting the thread would remove only the part a user could
still read. If a rename is wanted later it is one `PATCH` on an existing route rather than a
new resource.

**Every conversation route is scoped to `request.user`, and someone else's id is `404`**,
for the same reason `POST /api/ask` answers 404: a caller must not be able to enumerate the
existence of another user's threads one request at a time. The list is filtered by user
rather than filtered after reading, so no count or ordering can reflect a thread that is
not the caller's.

**The permission scope is re-resolved on every turn, never cached from the first.** That is
FR-13's Validation clause — "so that a follow-up cannot inherit access the user no longer
holds" — and it is structural rather than remembered: `answer_question` reads the role from
the user row on each call and the conversation carries no scope for a follow-up to inherit.
A test demotes and promotes across two turns of one thread, on one session cookie with no
re-login, and asserts the second turn's answer changed with the role.
