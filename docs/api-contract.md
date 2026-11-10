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
409 on registration, which FR-01 specifies. Every response under `/api/`, whatever its status,
carries `Cache-Control: max-age=0, no-cache, no-store, must-revalidate, private` and an
`Expires` header (D-76). The one route that answers with something other than JSON is FR-15's
download, which returns the stored original (D-75).

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
per client address and answer `429` past the rate (D-26). Since Stage 5 item 5, asks, ingestion
and thread creation are limited per user as well; "Stage 5 item 5" below lists every throttled
route (D-79).

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
- Unmatched path under `/api/`: JSON `404 {"detail": "Not found."}`. Since Stage 5 item 9 a path
  outside `/api/` is the SPA's (see "Stage 5 item 9" at the end of this file).
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
| POST | `/api/documents` | session + `contribute_content` | `201` document object, carrying `doc_id`, and since FR-10 `classification` (the object or `null`; see NIT3004 — FR-10) | `400` no file, or an empty title, or a `visible_to_roles` that is empty or names an unknown role; `401`; `403` the role lacks `contribute_content`, or the list excludes the uploader's own role (*convention*, D-29); `409` a document with the same content already exists; `413` over 50 MB, or a DOCX or XLSX whose members declare more decompressed content than a parser may inflate (*convention*, Stage 4 item 12b — a size rejection of decompressed size, carrying its own message, not the 415); `415` the file signature is not one of the four accepted formats; `422` the document was stored but no text could be extracted, or it holds too little text to index, or it is too large to index (D-51; for a PDF, any of D-81's bounds), or every chunk failed to embed; `429` past `INGESTION_THROTTLE_RATE`, shared with meeting ingest, reprocess and, since FR-10, classify (D-79, D-105); `429 {"detail": "...", "code": "ingestion_in_flight"}` while another upload, transcript or reprocess of this user's is still being processed, nothing stored (D-85) |
| POST | `/api/documents/{id}/reprocess` | session + `contribute_content` | `201` the document object, now `Indexed` or `Partially indexed`, with `classification` since FR-10 (NIT3004 — FR-10) | `401`; `403` the role lacks `contribute_content`; `404` no such document, or one outside the caller's scope; `409` already indexed, or restoring its content hash collided with a copy indexed meanwhile; `422` the reprocess failed the same way the upload did, or the document has no stored original: its `file_path` is blank or names a file missing from disk or outside the media folder (`NO_STORED_ORIGINAL_MESSAGE`, D-75); `429` past the ingestion rate (D-79); `429 {"detail": "...", "code": "ingestion_in_flight"}` while another upload, transcript or reprocess of this user's is still being processed, the document left as it was (D-85) |
| GET | `/api/documents` | session | `200 [document object, ...]`, newest first, scoped to the caller's role | `401` |
| GET | `/api/documents/{id}` | session | `200` document object, with the detail fields Stage 5 adds (`extracted_text`, `tags`, `can_delete`; see Stage 5 — FR-15) | `401`; `404` no such document, or one outside the caller's scope |

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

**What "scoped to the caller's role" means everywhere in this file (D-66).** A document,
meeting or chunk is in scope when its `visible_to_roles` overlaps the caller's *effective
roles*: an Employee reads rows naming `Employee`, and an Administrator reads rows naming
either role, because Administrator generalises Employee in scope as well as in
permissions. So an Employee-only document is listed, found and readable for an
Administrator, and an Administrator-only one is never any of those for an Employee. What
an upload may *write* into `visible_to_roles` is unchanged (D-29).

### FR-09 — meeting transcripts

| Method | Path | Auth | Success | Failures |
|---|---|---|---|---|
| POST | `/api/meetings` | session + `contribute_content` | `201` meeting object, carrying `meeting_id` | `422` the transcript was stored but every chunk failed to embed (*convention*: FR-09 enumerates only 201 and 400, and this mirrors FR-08's code for the same condition); `400` a missing or empty title, a missing date, a date in the future, a transcript below the minimum length, neither text nor file, both text and file, an unreadable file, a PDF file over one of D-81's extraction bounds (`{"file": ["..."]}` with that bound's own message, nothing stored), or an attendee who is not a registered user; `401`; `403` the role lacks `contribute_content`, or `visible_to_roles` excludes the ingester's own role; `429` past the ingestion rate (D-79); `429 {"detail": "...", "code": "ingestion_in_flight"}` while another upload, transcript or reprocess of this user's is still being processed, nothing stored (D-85) |
| GET | `/api/meetings` | session | `200 [meeting object without `transcript_text`, ...]`, newest first, scoped to the caller's role | `401` |
| GET | `/api/meetings/{id}` | session | `200` meeting object **with** `transcript_text`, and `can_delete` since D-99 (see Meeting deletion, below FR-15) | `401`; `404` no such meeting, or one outside the caller's scope |
| DELETE | `/api/meetings/{id}` | session + `manage_meetings` | `204` no body (D-99; not in the proposal, see Meeting deletion, below FR-15) | `401`; `404` no such meeting, or one outside the caller's scope, checked **before** the permission; `403` the meeting is in scope and the role lacks `manage_meetings` |

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

**The term is stored exactly as typed, and matched with whitespace collapsed (D-71).**
There is no sanitiser. The term reaches the database only as a bound parameter of an ORM
lookup, and `%` or `_` in a term match those characters rather than acting as wildcards.
The two-character minimum is measured on the term as typed. For matching, every run of
whitespace (spaces, tabs, line breaks) is collapsed to one space in the term and in the
stored text and title alike. So `escalation ladder` finds a passage that wraps as
`escalation⏎ladder`, and each snippet is shown with its whitespace collapsed. One
consequence, stated rather than hidden: a two-character query of whitespace is long enough
and lists everything the caller may already list. That is odd-looking, but every row it can
reach is in scope.

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
| POST | `/api/ask` | session | `200` the answer: verified statements, each with its `chunk_id`, and the sources consulted; also `200` with `answered: false`, the fixed no-answer message and any partially related items found | `400 {"question": ["..."]}` no question was sent, or its length is outside `MINIMUM_QUESTION_LENGTH`–`MAXIMUM_QUESTION_LENGTH`; `400 {"conversation_id": ["..."]}` the id is not a UUID; `401`; `404` (*convention*) a well-formed `conversation_id` that is not this caller's; `503` the AI service could not be reached after `MAXIMUM_GENERATION_ATTEMPTS`; `429` past `ASK_THROTTLE_RATE`, with DRF's body and `Retry-After`; `429 {"detail": "...", "code": "ask_in_flight"}` while this user's previous question is still being answered (D-79) |

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
  threshold, above a lower floor of its own.** It is taken from the output of ranking
  *before* `RELEVANCE_THRESHOLD` is applied, so an item that came close is offered whether
  or not it cleared the threshold, provided its best passage reaches `PARTIAL_MATCH_FLOOR`
  (`apps/core/constants.py`, D-56's floor). **It is 0.0, so there is no floor, and D-56 stays
  open:** at the 0.30 threshold kept in step 7, the margin rule could not set one. Any floor is
  below the threshold, so every item a path-B reply admitted is offered, and a path-A reply
  offers only items in the band between the two. With a floor above zero, a question nothing
  in the caller's scope comes near is offered `[]`, which says path A ran; with none, `[]`
  means the scope held nothing rankable. A non-empty list is consistent with either path. The
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
  `partial_matches` for a past turn: nothing records what a turn's ranking found, and the
  field would have to be invented to be filled. It does return `sources` since D-78, because
  `retrieved_chunk_ids` records what was supplied to generation; nothing records the
  candidates that fell below the threshold.

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
statement happened to cite would misdescribe what the answer was drawn from. An item whose
own source row the caller's role may not read is omitted from `sources` and from
`partial_matches`, even where its chunk was admitted (D-53: fail closed). The visibility
cascade keeps the two in agreement on every shipped write path, so this changes no reply
in normal use. The shape is unchanged. Each entry
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
| GET | `/api/conversations` | session | `200 [conversation object, ...]`, newest activity first, the caller's own only, and only threads with at least one turn (D-80) | `401` |
| POST | `/api/conversations` | session | `201` conversation object | `400` a title over 255 characters; `401`; `429` past the create rate (D-79, D-80) |
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
                            "chunk_id": "uuid-1"}],
            "sources": [{"source_type": "document", "source_id": "uuid",
                         "title": "Leave policy", "date": "2026-08-01T10:00:00+10:00",
                         "passages": [{"chunk_id": "uuid-1", "text": "..."},
                                      {"chunk_id": "uuid-2", "text": "..."}]}]}]}
```

Turns are chronological and each answered turn's statements are in the order they were
numbered in, so a reopened thread reads as it did when it was live. An unanswered turn
carries `answered: false`, the same fixed `message` the live reply carried, and no
statements. **A turn carries no `no_answer_reason`, no `rejected_count` and no
`retrieved_chunk_ids`**. The first two are left out for the reason the answer path gives: a
thread read is a second route past them. The third is not a field either, but an answered
turn's `sources` is built from it (D-78). On an answered turn it is exactly the list the live
Sources panel was built from (D-44), so the reader was shown it. On a turn stored as unanswered
it is never read, because `answered` plus its length tells the two no-answer paths apart.

**`sources` (D-78)** has the live reply's shape (D-44): every item consulted, in rank order, with
its passages. It is rebuilt on every read from one `scoped_chunks` query over the whole thread.
A consulted item that is now outside the reader's scope, deleted or re-indexed is absent, with
no count and no marker. Passage text is read from the chunk itself, and nothing stores a copy
(D-67), so deleted material is not surfaced again. Every passage a statement cites is in the
same list, unless D-53's fail-closed read dropped its source, which leaves that citation with
nothing to expand to, as on the live reply. A turn that does not render as answered, in the second or third state below, carries
`sources: []`. A turn carries no `partial_matches`, because nothing records them.

**One turn in three states, and a seventh key on exactly one of them** (Stage 4 item 1c;
`sources` since D-78):

| State | `answered` | `message` | `sources` | `provenance_removed` |
|---|---|---|---|---|
| answered, and still readable by this reader | `true` | `null` | the consulted items still readable | absent |
| never answered, **or** answered and re-scoped away from this reader | `false` | `NO_ANSWER_MESSAGE` | `[]` | absent |
| answered, and none of its citation rows still points at an existing chunk | `false` | `PROVENANCE_REMOVED_MESSAGE` | `[]` | `true` |

The second row is two states in one rendering **on purpose**: a turn whose statements were
drawn from material the reader's current role may no longer see is byte-for-byte a turn that
was never answered, because a notice that something was removed is itself a disclosure that
material exists which this role may not read (invariant 1). `provenance_removed` is therefore
**absent unless it is true** — a key present and false on a re-scoped turn would be a new
place for that notice to grow.

The third state is not a permission state at all and says nothing about one.
`POST /api/documents/{id}/reprocess`, `manage.py reindex` and FR-15's deletion when it lands
**each** delete a source's chunks. Since D-67 `AnswerCitation.chunk` is `on_delete=SET_NULL`,
so every citation of the deleted chunks survives as a record with `chunk_id` NULL and
`chunk_uuid` naming what it cited, for FR-12's traceability clause. **A citation whose chunk
is NULL is removed for every reader**: its statement and identifier never appear in a body,
and it does not count as a row when the state is decided. A turn none of whose rows still
points at an existing chunk is this third state, which is what a turn whose rows had been
destroyed was until D-67, when the foreign key cascaded (D-12). A turn with a NULL-chunk row
beside a row whose chunk exists but is out of the reader's scope is the **second** state,
silent, decided by the row whose chunk exists. A re-index and a successful reprocess write new chunks
with fresh identifiers, so the passage still exists word for word under a new id; **a
reprocess that fails leaves none at all**, because it deletes the chunks before running the
pipeline and a decided failure commits, and FR-15's deletion removes the material for good. The turn carries no statements
(invariant 6) and its own message, because `NO_ANSWER_MESSAGE` would tell the reader their
question cannot be answered from the knowledge base, which asserts a corpus state that is false on a failed
reprocess and on FR-15's deletion. Its own message promises nothing about the corpus for that
reason. **No count of what was lost**, in either state. The response shape did not change
with D-67: no field carries `chunk_uuid`, and no passage text is stored to return. Since D-78 a
turn carries passage text, read from the chunk itself, and a citation whose chunk is NULL has
none to read.

**Where a title comes from (D-43).** `Conversations.title` is a non-blank column and FR-13's
interface never asks the user to name a topic before typing — it clears the thread and lets
them start. So `title` is **optional on create**: supplied, it is used as sent; omitted or
blank, the thread is created as "New conversation" and **the first turn through
`POST /api/ask` replaces that with that turn's question**, truncated to the column width.
That replacement is the `Update` in FR-13's CRUD, alongside the `last_updated_at` the
pipeline touches on every turn. Both conditions are required for the rename — the
placeholder still standing and no turn logged yet — so a title the user chose is never
overwritten and a thread in use is never renamed under them. What keeps the list legible is
therefore the question itself, which is what the user would have typed as a name anyway.
Since D-80 a thread with no turn is not listed, so the list shows the placeholder only on a
thread whose first question was nothing but whitespace, which leaves nothing to name it with.

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

## Stage 5 — FR-14, FR-15

### FR-14 — dashboard

One endpoint aggregates every panel, in one request (FR-14's Server-End clause). Decisions:
D-68 (recent questions), D-69 (KnowledgeGaps deferred), D-70 (filters and totals), D-65 (how
the query parameters are read), D-66 (what "scoped to the caller's role" means).

| Method | Path | Auth | Success | Errors |
|---|---|---|---|---|
| GET | `/api/dashboard?date_from=&date_to=&department=` | session | `200` the summary object below, including when every list is empty and every count is 0 | `400 {"<parameter>": ["..."]}` a date that is not `YYYY-MM-DD`, `date_from` later than `date_to` (keyed on `date_to`), or a department that is not a string up to 255 characters (*convention*: FR-14 lists no 400; D-65); `401` no valid session |

All three parameters are optional, and an empty value for any of them (`date_from=`, `date_to=`, `department=`) is the same as leaving it out. `department` is trimmed of surrounding spaces first, so a department of spaces only is empty too.

```json
{
  "filters": {"date_from": "2026-09-01", "date_to": "2026-09-30", "department": "Finance"},
  "departments": ["Finance", "Human Resources", "Operations"],
  "indexed_totals": {"documents": 4, "meetings": 2, "total": 6},
  "recent_documents": [document object, ...],
  "recent_meetings": [meeting object without transcript_text, ...],
  "recent_questions": [
    {"question": "How is annual leave accrued?", "asked_at": "2026-09-14T10:02:11+10:00",
     "conversation_id": "uuid or null"}
  ]
}
```

- **`filters`** echoes the filters the server applied, after validation, with `null` for any
  not applied. The screen shows the active range from it (D-70).
- **`departments`** lists the distinct non-blank `department` values of the documents in the
  caller's scope, sorted, and is not narrowed by the active filters. It never lists a
  department found only on documents the caller cannot see (invariant 1).
- **`indexed_totals`** counts documents with status `Indexed` and meetings with status
  `Indexed`, in scope and after the filters, and `total` is their sum. `ContentChunks` is not
  read (D-70).
- **`recent_documents`** holds up to `DASHBOARD_RECENT_ITEMS` (5) documents in scope, newest
  `uploaded_at` first, in any status. They are the same document object `GET /api/documents`
  returns.
- **`recent_meetings`** holds up to 5 meetings in scope, newest `meeting_date` first. They are
  the same object `GET /api/meetings` returns.
- **`recent_questions`** holds up to 5 of the **caller's own** `QueryLog` rows, newest
  `answered_at` first: the question as asked, when, and its conversation if any. There is no
  answer text, no `answered` flag and no reason field (D-68).

**What each filter narrows (D-70):**

| | `date_from` / `date_to` (inclusive) | `department` |
|---|---|---|
| `recent_documents`, `indexed_totals.documents` | `uploaded_at`, by its Melbourne date | yes |
| `recent_meetings`, `indexed_totals.meetings` | `meeting_date` | **no** |
| `recent_questions` | `answered_at`, by its Melbourne date | **no** |

**No count discloses anything out of scope.** Every number and list is computed over the rows
`scoped_documents` and `scoped_meetings` return, or over the caller's own `QueryLog` rows, and
never over a wider set filtered afterwards (FR-14's "counts are computed after permission
filtering"; invariant 1). A `department` the caller cannot see and one that does not exist
return the identical payload apart from `filters.department`, which echoes the value sent: the
value is validated for shape and never looked up (D-65).

### FR-15 — document repository

The repository screen reads `GET /api/documents/browse`. `GET /api/documents` is unchanged: it
stays as FR-08's contracted list, although after Stage 5 item 2 no screen calls it (D-72's
dated note). Both routes build their documents through one scoped query function (D-72). Decisions: D-72 (browse), D-73 (deletion and the detail fields), D-74 (the
demonstration tags), D-65 (how parameters are read), D-66 (what scope means), D-63 (extracted
content), D-75 (the download, Stage 5 item 2a).

| Method | Path | Auth | Success | Errors |
|---|---|---|---|---|
| GET | `/api/documents/browse?q=&status=&department=&project=&process=&topic=&sort=` | session | `200` the browse object below; also `200` when no filter is set and nothing is in scope | `204` no body: at least one filter is set and no document in the caller's scope matches (FR-15); `400 {"<parameter>": ["..."]}` a `status` or `sort` outside its vocabulary, a NUL byte, or a value over 255 characters (*convention*, D-65); `401` |
| GET | `/api/documents/{id}` | session | `200` the document object **with** `extracted_text`, `tags` and `can_delete` (below) | `401`; `404` no such document, or one outside the caller's scope |
| GET | `/api/documents/{id}/download` | session | `200` the stored original as an attachment (below) | `401`; `404` no such document, one outside the caller's scope, or one whose original is not stored or is missing from disk or outside the media folder, with the **same body** in every case |
| DELETE | `/api/documents/{id}` | session + `manage_documents` | `204` no body. The document, its extracted content, its chunks and its tag links are deleted in one transaction; the stored file is removed when that transaction commits (*convention*: FR-15 names no success code for a delete) | `401`; `404` no such document, or one outside the caller's scope, checked **before** the permission; `403` the document is in scope and the role lacks `manage_documents` |

**Parameters.** All are optional, and an empty value is the same as leaving it out. A value is
trimmed of surrounding spaces first.

| Parameter | Meaning |
|---|---|
| `q` | Text filter: the title contains it, case-insensitively, with runs of whitespace collapsed on both sides (D-71) |
| `status` | One of the document statuses in `docs/schema-v1.md` §3 |
| `department` | Exact match on the document's `department` column (D-72) |
| `project`, `process`, `topic` | A tag name in that dimension, matched after the same normalisation `Tags` applies: lower case, single spaces |
| `sort` | `title`, `file_type`, `uploaded_by`, `uploaded_at` or `status`, each optionally prefixed `-` for descending. The default is `-uploaded_at`, newest first, and the primary key breaks ties. `title` sorts case-insensitively, `uploaded_by` by the uploader's address (the value the document object carries), and `status` alphabetically |

`q`, `status`, `department`, `project`, `process` and `topic` are filters, and they combine with
AND. `sort` is not a filter: it never causes a 204.

```json
{
  "filters": {"q": null, "status": null, "department": "Finance", "project": null,
              "process": "purchasing", "topic": null, "sort": "-uploaded_at"},
  "facets": {
    "department": [{"value": "Finance", "count": 3}, {"value": "Operations", "count": 1}],
    "project":    [{"value": "supplier review", "count": 3}],
    "process":    [{"value": "purchasing", "count": 3}],
    "topic":      [{"value": "finance", "count": 3}]
  },
  "documents": [document object, ...]
}
```

- **`filters`** echoes what the server applied after validation, with `null` for any filter not
  applied. `sort` is always present. Tag names are echoed normalised; `q` is echoed trimmed and
  otherwise as sent, because collapsing its whitespace is part of the match, not of the value.
- **`facets`** gives, for each dimension, the values found on documents in the caller's scope
  that match **every active filter except that dimension's own**, each with its count (the number
  of those documents carrying the value), sorted by value, with zero counts omitted (D-72). The values are read from the scoped documents and their
  tag links, never from the `Tags` table, so a value used only on documents the caller cannot see
  is never offered.
- **`documents`** is the document object `GET /api/documents` returns, filtered and sorted, with
  no paging.

**The detail object adds three fields** to the document object (D-63, D-73), and since FR-10 two
more, `classification` and `tag_details` (NIT3004 — FR-10, at the end of this file):

```json
{
  "...document object...": "...",
  "extracted_text": "Employees may request annual leave...",
  "tags": {"project": ["policy refresh"], "process": [], "topic": ["people"]},
  "can_delete": false
}
```

- **`extracted_text`** is `ExtractedContent.extracted_text`, read through the same scoped lookup,
  never reassembled from chunks. It is `null` when the document has no `ExtractedContent` row,
  for example "Extraction failed" or "Insufficient content". The client keys its empty state on
  `null`, not on the status. It is plain text and is rendered as text, never as HTML.
- **`tags`** lists the document's tag names in each of the three tag dimensions, sorted, each
  once, with every dimension present. Department is the `department` field (D-72).
- **`can_delete`** says whether the caller's role holds `manage_documents`. It is a hint for
  showing the delete control. The server checks the permission on every `DELETE` whatever the
  screen did (invariant 4).

**After a delete,** a phrase that was in the document is found by neither `GET /api/search` nor
`POST /api/ask`, because its chunks are gone (FR-15: "so that deleted material cannot
subsequently be surfaced through search"). Answers that cited it keep their `QueryLog` and
`AnswerCitation` rows, with the citation's chunk null (D-67), and a reopened turn renders them as
D-67 describes.

**The download** (D-75) returns the stored original's bytes, not JSON, for a document in any
status. The client links to this route, never to a `/media/` path, which nothing serves.

- **`Content-Type`** comes from the format the file's signature proved at upload, never from its
  name: `application/pdf`; `application/vnd.openxmlformats-officedocument.wordprocessingml.document`;
  `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`; or
  `text/plain; charset=utf-8`. The response also carries `X-Content-Type-Options: nosniff`.
- **`Content-Disposition`** is `attachment` with the stored original filename, its last extension
  corrected to the signature's. The comparison ignores case, and an extension is added when there
  is none.

  | Uploaded as | Proven format | Downloads as |
  |---|---|---|
  | `Report.PDF` | pdf | `Report.PDF` |
  | `Q3_budget.vbs` | txt | `Q3_budget.txt` |
  | `invoice.html` | txt | `invoice.txt` |
  | `report.pdf.exe` | txt | `report.pdf.txt` |
  | `minutes` | docx | `minutes.docx` |
- **A 404 body** is `{"detail": "No Document matches the given query."}` for an unknown id, an id
  outside the caller's scope and a document with no file alike. A missing file is logged on the
  server and not described to the client.
- **`Accept` is not consulted** on this route, so it never answers 406. Every other route
  negotiates as usual and answers 406 to an `Accept` that excludes JSON; here that would refuse
  `Accept: application/pdf` before the view ran. The route's 401 and 404 are JSON whatever the
  client asked for.

### Meeting deletion (D-99)

**Not in the proposal.** FR-09 gives Meetings Create, Read and Update status only, and FR-15's
permissioned deletion covers documents. The lead asked for meeting deletion on 7 November 2026.
It mirrors the document delete (D-73) clause for clause, under a permission of its own,
`manage_meetings`, seeded by accounts 0006 and held by Administrator only. `manage_documents` does
not grant it, and it does not grant `manage_documents`.

| Method | Path | Auth | Success | Errors |
|---|---|---|---|---|
| GET | `/api/meetings/{id}` | session | `200` the meeting object **with** `transcript_text` and `can_delete` (below) | `401`; `404` no such meeting, or one outside the caller's scope |
| DELETE | `/api/meetings/{id}` | session + `manage_meetings` | `204` no body. The meeting, its attendees, its chunks and its tag links are deleted in one transaction (*convention*: the document delete's code) | `401`; `404` no such meeting, or one outside the caller's scope, checked **before** the permission, with the **same body** for both; `403` the meeting is in scope and the role lacks `manage_meetings` |

```json
{
  "...meeting object with transcript_text...": "...",
  "can_delete": false
}
```

- **`can_delete`** says whether the caller's role holds `manage_meetings`. It is a hint for showing
  the delete control. The server checks the permission on every `DELETE` whatever the screen did
  (invariant 4). Only the detail carries it: `GET /api/meetings`, `POST /api/meetings` and the
  dashboard's `recent_meetings` return the meeting object without it.
- **There is no file to remove.** A transcript uploaded as a file is read for its text and not
  stored, so unlike the document delete nothing waits for the commit.
- **After a delete,** the meeting is gone from `GET /api/meetings`, the detail and the dashboard,
  and a question only it answered takes no-answer path A from `POST /api/ask`, because its chunks
  are gone. Answers that cited it keep their `QueryLog` and `AnswerCitation` rows, with the
  citation's chunk null (D-67), and a reopened turn renders them as D-67 describes. The users who
  attended are not touched.

## Stage 5 item 5 — throttles, the in-flight ask and empty threads

**Rate limits (D-79)** are per user, through DRF's `ScopedRateThrottle`. Each rate is a constant in
`apps/core/constants.py`.

| Scope | Routes | Rate |
|---|---|---|
| `auth` | `POST /api/auth/register`, `POST /api/auth/login`, per client address (D-26) | 20/min |
| `ask` | `POST /api/ask` | 10/min |
| `ingestion` | `POST /api/documents`, `POST /api/meetings`, `POST /api/documents/{id}/reprocess` and, since FR-10, `POST /api/documents/{id}/classify` (D-105), one shared budget | 60/hour |
| `conversation_create` | `POST /api/conversations` | 10/min, its own budget |

A request over its rate is answered with DRF's 429, `{"detail": "Request was throttled. Expected
available in N seconds."}`, and a `Retry-After` header in seconds. The rate is checked before the
body is validated, so a rejected request counts as well. `X-Forwarded-For` is not trusted
(`NUM_PROXIES = 0`), so the `auth` limit is keyed on the connecting address.

**One ask in flight per user (D-79).** While a user's question is being answered, another
`POST /api/ask` from the same user answers at once:

```json
{"detail": "Your previous question is still being answered.", "code": "ask_in_flight"}
```

That 429 carries no `Retry-After`, because an answer can take a long time: about 46 minutes in the worst case, since the question's embedding has no timeout of its own (D-79's note). The client tells
the two 429s apart by `code`, and does not parse `detail`. The check runs after validation and the
conversation check, so a 400 or a 404 is returned as before, and a rejected ask writes no
`QueryLog` row.

**One ingestion in flight per user (D-85, Stage 5 item 6).** The three ingestion routes,
`POST /api/documents`, `POST /api/meetings` and `POST /api/documents/{id}/reprocess`, share one
slot per user, as they share the `ingestion` rate. While one of them is being processed for a
user, another from the same user, on any of the three, answers at once:

```json
{"detail": "Your previous upload is still being processed.", "code": "ingestion_in_flight"}
```

- **Nothing is stored.** No document, meeting, file or chunk is written, a reprocessed document is
  left as it was, and no provider is called.
- **No `Retry-After`**, because how long an ingestion takes depends on the file. Retrying once the
  earlier request has answered is enough.
- **Every refusal comes first.** The check runs after every rejection a route decides before
  ingesting: the upload's 400, 403, 409, 413 and 415, the meeting's 400 and 403, and reprocess's
  404, 409 and the 422 for a missing original. Those are answered as before. A 422 for content
  stored but not indexed is ingestion's own outcome, reached inside the slot. The rate is checked
  before the slot, so this 429 counts against the rate.
- **It is separate from the ask's slot.** A user may have one question and one ingestion in
  flight at once.
- The client tells the three kinds of 429 apart by `code`: none for the rate, `ask_in_flight`,
  and `ingestion_in_flight`. It does not parse `detail`.

**The conversation list leaves out empty threads (D-80).** `GET /api/conversations` returns only
threads with at least one turn, answered or not. It never filters on the title, or on what a turn
renders, so a thread whose every turn is re-scoped stays listed. An empty thread is not deleted:
`GET /api/conversations/{id}` still returns it, and the Ask screen reuses it by its address (D-77).

**PDF extraction bounds (D-81).** A PDF that trips any of D-81's bounds is refused with that
bound's own sentence, which says whether splitting the file would help. The bounds are the stored
and decoded size of one stream, the page count, the drawing operators across the document, and
the text ceiling.

- **On `POST /api/documents` and reprocess** the answer is `422` with status "Too large to index".
  The `detail` is "The document was stored but not indexed." followed by the sentence. The original
  stays stored.
- **On `POST /api/meetings`, with a PDF file,** the answer is `400 {"file": ["..."]}` with the
  sentence alone. Nothing is stored.
- **The text ceiling keeps its existing wording on both routes.**

## Stage 5 item 9 — one origin for the SPA and the API, and JSON 400 and 500

The alpha serves the production build of `frontend/` and `/api` from one origin, Django under
Waitress, on loopback (D-64). `docs/alpha-deployment.md` is the runbook.

| Path | Answer |
|---|---|
| `/api/...` | as every section above states; an unmatched one is `404 {"detail": "Not found."}` |
| `/api` | `301` to `/api/` |
| a file in the build, such as `/assets/index-<hash>.js` or `/favicon.svg` | `200` the file. Under `/assets/`, `Cache-Control: max-age=315360000, public, immutable`, because Vite puts a content hash in every name there; anything else, `max-age=60, public` |
| `/assets/...` naming no file in the build | `404 {"detail": "Not found."}`, never `index.html` |
| any other path, for `GET` or `HEAD` | `200` the build's `index.html`, `Cache-Control: no-cache`, so the React router answers a reload or a typed address on a client route |
| any other path, another method | `405`, or Django's `403` page first when the CSRF check refuses it |
| any path outside `/api/`, with no build in `SPA_DIST_DIR` | `404 {"detail": "Not found."}`, as before item 9 |

- **`/media/` is a client route like any other.** It answers `index.html` and never a stored file.
  An original leaves only through FR-15's scoped download.
- **Under `DEBUG=False`, two errors that were Django's HTML pages are JSON under `/api/`:**
  - an unhandled exception is `500 {"detail": "A server error occurred."}`. The body never
    carries the exception; the traceback goes to the error file (D-75).
  - a `Host` header outside `ALLOWED_HOSTS` is `400 {"detail": "Bad request."}`.

  Both carry D-76's never-cache headers like every other `/api/` response. Outside `/api/` both
  stay Django's own HTML pages. Under `DEBUG=True` Django shows its debug pages instead, which is
  one reason the alpha runs with `DEBUG=False`.
- **Nothing outside `/api/` is marked never-cache** by D-76's middleware: `index.html` is
  `no-cache` (stored, but revalidated on every load) and the assets are cached as above.

## NIT3004 — FR-10 document classification (D-104, D-105)

FR-10's server side, 8 and 9 November 2026. The AI operation is `AIService.classify_document`
(D-104). What becomes of its suggestions is application code in `apps/documents/classification.py`
(D-105): the type is **applied** at or above `CLASSIFICATION_CONFIDENCE_THRESHOLD` and
**provisional** below it; the department likewise, and **discarded** outside the established
scheme; a tag in the scheme is linked `applied_by: "ai"`, provisional below the threshold; a Topic
outside the scheme is **proposed** and created only when a person confirms it; a Project or Process
outside the scheme is discarded and recorded. The scheme is built for the document's own audience,
so no suggestion names a value that exists only on material some reader of the document may not
see (invariant 1). A person's decision (`user_edited`, a confirmed link) is never overwritten by a
later run; the machine's values are recorded alongside it.

Every route below: a session; the document resolved through the caller's scope **first**, so an
unknown id and one outside the scope are the same `404 {"detail": "No Document matches the given
query."}` (D-46); then `contribute_content`, held by both roles (D-105), `403` without it, checked
after the 404 as D-73 orders it; then the body. No body says more than the 404 would: a link, a
proposal or an analysis that is not this document's gets that same 404, word for word.

| Method | Path | Auth | Success | Errors |
|---|---|---|---|---|
| POST | `/api/documents/{id}/classify` | session + `contribute_content` | `200 {"classification": ..., "tag_details": [...], "department": "Finance"}` after one provider call and the apply rules, in one transaction; a second call updates the one analysis. `department` is the document's `department` column after the classification, re-read from the row: an applied in-scheme suggestion fills a blank department, and a different department already there is kept, with the suggestion held as `department_outcome: "provisional"` (D-105's note of 10 November) | `401`; `404`; `403`; `422 {"detail": "..."}` no extracted text (FR-10: "where insufficient text was extracted"), before any provider call; `503 {"detail": "..."}` the provider failed after `MAXIMUM_CLASSIFY_ATTEMPTS` (NFR-19), nothing written; `429` past the ingestion rate, one budget with upload, meeting ingest and reprocess (D-79); no in-flight slot |
| POST | `/api/documents/{id}/classification` | session + `contribute_content` | `200 {"classification": ..., "department": "Finance"}`, where `department` is the document's `department` column after the confirm or edit, so the client need not infer it from the outcome. Body `{"doc_type"?: string, "department"?: string}`: both omitted confirms as it stands (a provisional type is applied; a provisional department is written to `department`); `doc_type` must be one of `DOCUMENT_TYPES`; `department` may be blank, which clears it; `null` means omitted | `401`; `404`, also when the document has no classification yet; `403`; `400 {"doc_type": ["..."]}` or `{"department": ["..."]}` |
| POST | `/api/documents/{id}/tags/{content_tag_id}/confirm` | session + `contribute_content` | `200` the `tag_details` entry, now `confirmed: true, provisional: false`, `applied_by` unchanged | `401`; `404`, also when the link is not this document's; `403` |
| DELETE | `/api/documents/{id}/tags/{content_tag_id}` | session + `contribute_content` | `204` no body: the link is removed (FR-10: "accepted or removed in a single action"); the `Tags` row stays | `401`; `404`, also when the link is not this document's; `403` |
| POST | `/api/documents/{id}/proposed-topics/confirm` | session + `contribute_content` | `200 {"classification": ..., "tag_details": [...]}`. Body `{"value": string}`, matched after normalisation (lower case, single spaces); the Topic tag is created, or reused and reactivated, and linked `applied_by: "ai", confirmed: true`; the proposal leaves `proposed_topics` | `401`; `404`, also when the value is not proposed on this document; `403`; `400 {"value": ["..."]}` blank or over 255 characters |
| POST | `/api/documents/{id}/proposed-topics/reject` | session + `contribute_content` | `200 {"classification": ..., "tag_details": [...]}`: the proposal is dropped and no tag is created | the same |

The classification object (`null` for a document never classified):

```json
{"doc_type": "Policy", "doc_type_outcome": "applied", "department_outcome": "provisional",
 "machine_doc_type": "Policy", "machine_doc_type_confidence": 0.9,
 "machine_department": "Finance", "machine_department_confidence": 0.6,
 "user_edited": false, "proposed_topics": [{"value": "budget planning", "confidence": 0.8}],
 "classified_at": "2026-11-09T10:00:00+11:00", "model": "gemma3:4b", "input_truncated": false}
```

- **The effective department is the document object's `department`** (D-72); `department_outcome`
  says how it got there. `doc_type` is `null` while the type is provisional. The outcomes are
  `applied`, `provisional`, `discarded` and `confirmed` (`docs/schema-v1.md` §3). Confidences are
  numbers to three places. `discarded_suggestions` is not exposed: it is a record for the
  Objective 05 measurement (D-106).

A `tag_details` entry, one per `ContentTags` link in Project, Process or Topic, provisional
included, sorted by dimension then name:

```json
{"content_tag_id": "uuid", "dimension": "Project", "name": "bridge maintenance",
 "applied_by": "ai", "confirmed": false, "provisional": true, "confidence": 0.6}
```

**The detail** `GET /api/documents/{id}` carries both, `classification` and `tag_details`, beside
FR-15's fields. `tags` is unchanged in shape and lists **applied** links only.

**The 201 bodies** of `POST /api/documents` and `POST /api/documents/{id}/reprocess` carry
`classification` (section 7.8 line 100): the object, or `null` when classification failed or the
provider was unavailable, in which case the document is indexed and unclassified (invariant 8,
D-33 part 1). A 422 body does not carry it, and neither do the list and browse routes.

**FR-15's reads and provisional links (D-105).** A provisional link is held, not applied: it is not
in the detail's `tags`, not a browse facet value and not a filter hit until it is confirmed.
`tag_details` is where a held suggestion is seen.

**The management command** `python manage.py classify_documents --all | --document <uuid>...
[--out record.json]` runs the same path per document and writes the Objective 05 record (D-106:
database, commit, per-document values, outcomes, links, seconds or error). It refuses the
database `kmp`.
