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
and thread creation are limited per user as well, and keyword search and a person applying a tag
since 10 November 2026, and a recording segment sent for transcription since D-123;
"Stage 5 item 5" below lists every throttled route (D-79).

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
  - **The token is read from that header only, never from a `csrfmiddlewaretoken` form field
    (D-124).** That is so the check never reads the request body. Every client already sends the
    header.
  - **A refusal is `403 {"detail": "CSRF Failed: ..."}`,** given before any permission check,
    throttle or body is read.
- `POST /api/auth/register` starts no session (D-23).
- Any endpoint, a request body that is not `application/json`: `415`. The API parses
  JSON only, which is what stops a cross-site form from posting credentials (D-24).
- Any endpoint that reads a JSON body, one declaring more than 2.5 MiB:
  `400 {"detail": "Bad request."}`, refused unread.
  - **Why:** DRF parses JSON from `request.body`, which applies Django's
    `DATA_UPLOAD_MAX_MEMORY_SIZE` to the declared length.
  - **Not new:** it held from the start and was first written down at D-124. The one body it does
    not cover is FR-09's pasted transcript above 50 MB, which gets the upload ceiling's `413`.
- Any endpoint, a body declaring `MAX_REQUEST_BODY_BYTES` (54,525,952) or more: `413` from Waitress,
  not from the API (D-124).
  - **It is Waitress's own plain-text page, not JSON.** Waitress gives it at the request's headers,
    before reading the body, then closes the connection. A client still sending may see the
    connection reset instead.
  - **A chunked body declares no length.** Waitress counts it as it arrives and refuses it when it
    reaches the cap, so up to the cap is received first.
  - **It applies only where the server is started as `docs/alpha-deployment.md` starts it.**

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

**The size ceiling is applied twice**: once against the declared `Content-Length`, before the
body is read, and once against the bytes actually received. The second is defence in depth:
Django reads no more of a body than its declared length, so a body cannot carry a larger file than
it declares.

- **One step runs ahead of the order above, as it has since Stage 3.** The declared-length 413
  comes before the signature's 415, because the signature cannot be read without reading the body.
  So an oversized disguised file is `413`, not `415`.
- **Every step after it** runs in §7.2's order.
- **Nothing reads the body before the view** (D-124). The view reads it only after the 403, the 429
  and the declared-length 413.

> **Corrected 11 November 2026 (D-124).** From Stage 3 until then, this paragraph said the first
> check refused a 50 MB transfer "without being buffered".
>
> - **For every signed-in browser session it did not.** DRF's CSRF check read `request.POST`, which
>   parsed the whole body, spooling the upload to temporary files. That happened before the 403,
>   the 429 and this 413, so §7.2's "cheapest rejection" was not cheap.
> - **The suite did not catch it,** because the test client enforces CSRF only when asked.
> - **The fix:** the CSRF check now reads its token from the `X-CSRFToken` header and parses
>   nothing.

**What is not refused unread: receiving.** Waitress reads the whole body before Django sees the
request. The serve command's `--max-request-body-size` caps that, on every route, at
`MAX_REQUEST_BODY_BYTES`: 54,525,952 bytes, 2 MiB over the upload ceiling (D-124). A body at or
over that cap is refused by Waitress itself (see Stage 2's last bullet), as is a chunked one when it
reaches the cap. A body over 50 MB and under the cap gets this route's JSON `413`.

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
| POST | `/api/meetings` | session + `contribute_content` | `201` meeting object, carrying `meeting_id` | `422` the transcript was stored but every chunk failed to embed (*convention*: FR-09 enumerates only 201 and 400, and this mirrors FR-08's code for the same condition); `400` a missing or empty title, a missing date, a date in the future, a transcript below the minimum length, neither text nor file, both text and file, an unreadable file, a PDF file over one of D-81's extraction bounds (`{"file": ["..."]}` with that bound's own message, nothing stored), or an attendee who is not a registered user; `401`; `403` the role lacks `contribute_content`, or `visible_to_roles` excludes the ingester's own role; `413 {"detail": "Transcript exceeds the maximum permitted size of 50 MB."}` a body, pasted or a file, declaring more than 50 MB, refused before it is read, after the 403 and the 429, nothing stored (*convention*, D-124: FR-09 enumerates only 201 and 400, and a body refused unread has no field to report on); `400 {"detail": "Bad request."}` a pasted transcript whose JSON body declares between 2.5 MiB and 50 MB, refused unread by Django's `DATA_UPLOAD_MAX_MEMORY_SIZE`, nothing stored (always so; first written down at D-124); `429` past the ingestion rate (D-79); `429 {"detail": "...", "code": "ingestion_in_flight"}` while another upload, transcript or reprocess of this user's is still being processed, nothing stored (D-85) |
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
| GET | `/api/search?q=<term>` | session | `200` grouped results, scoped to the caller's role; also `200` when nothing matched | `400 {"q": ["..."]}` `q` was not sent, or the term is shorter than `MINIMUM_SEARCH_LENGTH` (2 characters), which includes `?q=`, or longer than `MAXIMUM_SEARCH_LENGTH` (500, D-79's note of 10 November 2026), and no `SearchLog` row is written; `401`; `429` past `SEARCH_THROTTLE_RATE`, with DRF's body and `Retry-After`, and no row written (D-79's note) |

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
D-68 (recent questions), D-69 (KnowledgeGaps deferred, closed by D-107 on 9 November 2026), D-70
(filters and totals), D-65 (how the query parameters are read), D-66 (what "scoped to the caller's
role" means).

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
- **`knowledge_gaps`** is present **only** for a caller whose role holds
  `review_knowledge_gaps`, and absent from every other payload, so an Employee's dashboard has
  exactly the six keys above. Its shape is under FR-19 below (D-107).

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

**The detail object adds three fields** to the document object (D-63, D-73), and since FR-10 three
more, `classification`, `tag_details` and `tag_options` (NIT3004 — FR-10, at the end of this file):

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
| `ingestion` | `POST /api/documents`, `POST /api/meetings`, `POST /api/documents/{id}/reprocess`, since FR-10 `POST /api/documents/{id}/classify` (D-105), and since FR-16 `POST /api/meetings/{id}/summary` (D-125), one shared budget | 60/hour |
| `conversation_create` | `POST /api/conversations` | 10/min, its own budget |
| `search` | `GET /api/search`, since D-79's note of 10 November 2026 | 30/min |
| `tagging` | `POST /api/documents/{id}/tags`, since D-79's note on tagging of the same night; checked before the document is looked up, so past the rate the `429` comes before the `404` and the `403`. Since D-128 also `POST /api/tags`, the Administrator's add, checked after its `401` and `403`; one budget per user across both routes | 30/min |
| `transcription` | `POST /api/transcriptions`, one recording segment per request, and `GET /api/transcriptions/status`, which asks FLM each time (D-123; see "Recording transcription" at the end of this file) | 60/min |
| `action_items` | FR-16's `POST /api/meetings/{id}/action-items` and `PATCH` and `DELETE /api/meetings/{id}/action-items/{item_id}`, one budget (the security review of 12 November 2026, D-125's third note); checked before the meeting is looked up, so past the rate the `429` comes before the `404` and the `403` | 30/min |

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
- **It is separate from the ask's slot.** A user may have a question and an ingestion in flight
  at once, and since D-123 a recording segment in transcription as well.
- The client tells the kinds of 429 apart by `code`: none for the rate, `ask_in_flight`,
  `ingestion_in_flight` and, on the transcription route, `transcription_in_flight` and
  `transcription_busy` (D-123). It does not parse `detail`.

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
| any other path, another method | `405`, and nothing is read. Until D-124, Django's CSRF check ran first: it could answer its `403` page, and it parsed a multipart body to look for a form-field token. The catch-all is exempt now, because it makes no write |
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
(D-105, D-128, D-129). Each value is compared with the classifying model's confidence threshold
(`confidence_threshold`).

- **The type:** **applied** at or above the threshold, **provisional** below it.
- **The department:** likewise, and **discarded** outside the established scheme.
- **A tag in the scheme:** linked `applied_by: "ai"`, provisional below the threshold.
- **A value outside the scheme,** Objective 05's clause 3 as written:
  - **a Topic** is **proposed** in `proposed_tags`, at any confidence, for a person to confirm (which
    creates it) or reject. The classifier never creates, links or reactivates one;
  - **a Project or Process value** is **discarded**;
  - **a value that cannot be stored,** one holding U+0000 or a lone surrogate, is discarded too, with
    U+FFFD in its place. Neither discard is exposed;
  - **a value this document's readers removed or rejected** is neither linked nor proposed again.

  For one day (12 November, D-128) the classifier created values at or above the threshold. D-129
  reversed it.

The scheme is built for the document's own audience, so the classifier is never shown a value that
exists only on material some reader of the document may not see (invariant 1). A value outside the
scheme gets the same treatment whether no Tag has it, a grown Tag carried only by restricted
material has it, or a retired Tag has it, so no reply tells a reader which (D-105, D-129). A person's
decision (`user_edited`, a confirmed or removed link) is never overwritten by a later run; the
machine's values are recorded alongside it.

Every route below: a session; the document resolved through the caller's scope **first**, so an
unknown id and one outside the scope are the same `404 {"detail": "No Document matches the given
query."}` (D-46); then `contribute_content`, held by both roles (D-105), `403` without it, checked
after the 404 as D-73 orders it; then the body. No body says more than the 404 would: a link, a
proposal or an analysis that is not this document's gets that same 404, word for word. Two of the
routes are rate limited per user: classify, in the `ingestion` scope, and applying a tag, in
`tagging` (D-79 and its note on tagging). The rate is checked after the session and before the
document is looked up, so past it the `429` comes before the `404` and the `403`, and is the same
for every id.

| Method | Path | Auth | Success | Errors |
|---|---|---|---|---|
| POST | `/api/documents/{id}/classify` | session + `contribute_content` | `200 {"classification": ..., "tag_details": [...], "department": "Finance"}` after one provider call and the apply rules, in one transaction; a second call updates the one analysis. `department` is the document's `department` column after the classification, re-read from the row: an applied in-scheme suggestion fills a blank department, and a different department already there is kept, with the suggestion held as `department_outcome: "provisional"` (D-105's note of 10 November) | `401`; `404`; `403`; `422 {"detail": "..."}` no extracted text (FR-10: "where insufficient text was extracted"), before any provider call; `503 {"detail": "..."}` the provider failed after `MAXIMUM_CLASSIFY_ATTEMPTS` (NFR-19), nothing written; `429` past the ingestion rate, one budget with upload, meeting ingest and reprocess (D-79); no in-flight slot |
| POST | `/api/documents/{id}/classification` | session + `contribute_content` | `200 {"classification": ..., "department": "Finance"}`, where `department` is the document's `department` column after the confirm or edit, so the client need not infer it from the outcome. Body `{"doc_type"?: string, "department"?: string}`: both omitted confirms as it stands (a provisional type is applied; a provisional department is written to `department`); `doc_type` must be one of `DOCUMENT_TYPES`; `department` may be blank, which clears it; `null` means omitted | `401`; `404`, also when the document has no classification yet; `403`; `400 {"doc_type": ["..."]}` or `{"department": ["..."]}` |
| POST | `/api/documents/{id}/tags/{content_tag_id}/confirm` | session + `contribute_content` | `200` the `tag_details` entry, now `confirmed: true, provisional: false`, `applied_by` unchanged | `401`; `404`, also when the link is not this document's or has been removed; `403` |
| DELETE | `/api/documents/{id}/tags/{content_tag_id}` | session + `contribute_content` | `204` no body: the tag is removed (FR-10: "accepted or removed in a single action"). The link is **kept, marked removed**, a person's (`applied_by: "user"`) as well as an AI link (`applied_by: "ai"`, held or applied, confirmed or not, with the confidence the machine gave it), and no read lists it again; a later classify, reprocess or `classify_documents` run neither links it again nor alters it, and a removed value is neither proposed, created nor reactivated again on this document, in any dimension (D-128; a removed Topic until then). Applying the tag again restores it (`200` on the POST below). A person's link was deleted until the requirements re-audit of 10 November 2026 (D-105). The `Tags` row stays | `401`; `404`, also when the link is not this document's or has already been removed; `403` |
| POST | `/api/documents/{id}/tags` | session + `contribute_content` | A person applies a tag (D-105's dated note of 10 November 2026, night). Body, exactly one of: `{"tag_id": "uuid"}`, an existing tag from the detail's `tag_options`; or `{"dimension": "Topic", "tag_name": string}`, a new Topic, matched after normalisation (trimmed, single spaces, lower case). `201 {"tag_details": [...]}` when a new link was made: `applied_by: "user"`, `confirmed: true`, `provisional: false`, `confidence: null`. `200` with the same shape when the tag was already on the document: a held AI link is confirmed, a removed one is restored and confirmed (its `applied_by` and confidence kept), and an applied or confirmed one is left as it is. `tag_details` is the document's whole current list | `401`; `404`; `403`; `400 {"tag_id": ["Choose a tag from this document's tag options."]}` for a `tag_id` that is unknown, inactive, a Department tag or not offered for this document, **one body for all of them**; `400 {"dimension": ["..."]}` a dimension other than `Topic` in the name form, or none given with `tag_name`; `400 {"tag_name": ["..."]}` blank, over 255 characters or missing; `400 {"tag_id": ["..."]}` not a UUID; `400 {"non_field_errors": ["..."]}` neither form, or both; `409 {"detail": "A Topic with this name is already offered for this document. Choose it from the tag options.", "tag_id": "uuid"}` the name is a Topic already in `tag_options`, whose id this is; `429` past `TAGGING_THROTTLE_RATE` (30 a minute per user), with DRF's body and `Retry-After`, nothing written, and answered before the document is looked up, so the same for every id (D-79's note on tagging) |
| POST | `/api/documents/{id}/proposed-tags/confirm` | session + `contribute_content` | `200 {"classification": ..., "tag_details": [...]}`. Body `{"dimension": "Project"\|"Process"\|"Topic", "value": string}`, both required; the value is matched after normalisation (lower case, single spaces) within that dimension. The tag is created, or reused and reactivated, and linked `applied_by: "ai", confirmed: true`. A tag it creates or reactivates is grown, and an active one it reuses keeps its state, so a vocabulary value stays vocabulary (D-105). The proposal leaves `proposed_tags`. Replaces `/proposed-topics/confirm`, which took Topics only (D-128) | `401`; `404`, also when that value is not proposed under that dimension on this document; `403`; `400 {"dimension": ["..."]}` missing or not one of the three; `400 {"value": ["..."]}` blank or over 255 characters |
| POST | `/api/documents/{id}/proposed-tags/reject` | session + `contribute_content` | `200 {"classification": ..., "tag_details": [...]}`: the proposal is dropped and no tag is created. **The rejection is kept** on the document (`rejected_tags`, not exposed, with the machine's confidence; the requirements audit of 13 November, D-128). A later classify, reprocess or `classify_documents` run then neither proposes, creates nor links that value for this document, in any dimension, even after the value has entered the scheme (FR-10's correction clause). A person may still apply it themselves. Same body. Replaces `/proposed-topics/reject` (D-128) | the same |

The classification object (`null` for a document never classified):

```json
{"doc_type": "Policy", "doc_type_outcome": "applied", "department_outcome": "provisional",
 "department_applied_by": "user",
 "machine_doc_type": "Policy", "machine_doc_type_confidence": 0.9,
 "machine_department": "Finance", "machine_department_confidence": 0.6,
 "user_edited": false,
 "proposed_tags": [{"dimension": "Topic", "value": "budget planning", "confidence": 0.6},
                   {"dimension": "Project", "value": "harbour upgrade", "confidence": 0.5}],
 "classified_at": "2026-11-09T10:00:00+11:00", "model": "gemma3:4b", "input_truncated": false}
```

- **The effective department is the document object's `department`** (D-72); `department_outcome`
  says how the machine's suggestion was disposed of. `doc_type` is `null` while the type is
  provisional. The outcomes are `applied`, `provisional`, `discarded` and `confirmed`
  (`docs/schema-v1.md` §3). Confidences are numbers to three places. `discarded_suggestions` is not
  exposed: it is a record for the Objective 05 measurement (D-106). It holds the out-of-scheme
  Project and Process suggestions, and a value that cannot be stored (U+0000 or a lone surrogate)
  with U+FFFD in its place (D-129). `rejected_tags`, the proposals a person rejected, is not
  exposed either.
- **`proposed_tags`** (D-128, replacing `proposed_topics`) lists the out-of-scheme Topic values held
  for a person, at any confidence, each `{dimension, value, confidence}` with `dimension` "Topic". It
  is deduplicated by value and replaced by each run.
  - **D-129:** the shape carries a dimension because, for one day (D-128), Project and Process values
    below the threshold were proposed too.
- **`department_applied_by`** says whose value the document's department is, in the tags'
  provenance vocabulary (D-119 finding 10; D-105's dated note of 10 November 2026, night):
  - `"user"`: a person gave it, typed at upload or written through the confirm route. With
    `department_outcome: "applied"` this is a department a person supplied that the machine's
    suggestion **matched**: show it as the person's, not as "Suggested by AI".
  - `"ai"`: a classification run wrote its suggestion into a blank department, and no person has
    written the department since. A person who confirms that value as it stands keeps it `"ai"`,
    with `department_outcome: "confirmed"`, as a confirmed AI tag keeps `applied_by: "ai"`.
  - `null`: the document has no department, or its classification was recorded before
    `documents 0009` and no run or confirmation has set the field since. Treat it as before the
    field existed.

  It is in the object wherever the object is: the detail, the classify and confirm replies, the
  proposed-tag replies and the upload's and reprocess's 201 bodies.

A `tag_details` entry, one per `ContentTags` link in Project, Process or Topic, provisional
included and removed excluded, sorted by dimension then name:

```json
{"content_tag_id": "uuid", "dimension": "Project", "name": "bridge maintenance",
 "applied_by": "ai", "confirmed": false, "provisional": true, "confidence": 0.6}
```

**The detail** `GET /api/documents/{id}` carries both, `classification` and `tag_details`, beside
FR-15's fields. `tags` is unchanged in shape and lists **applied** links only.

**The detail also carries `tag_options`** (D-105's dated note of 10 November 2026, night): the tags a
person may apply to this document, which are the document's own classification scheme, each
dimension sorted by name and always present:

```json
"tag_options": {
  "Project": [{"tag_id": "uuid", "tag_name": "bridge maintenance"}],
  "Process": [{"tag_id": "uuid", "tag_name": "purchasing"}],
  "Topic":   []
}
```

- **It discloses nothing to anyone who may read the document.** A tag is offered if it is **not
  grown**, whatever its links, or if every role in the document's audience can read a source
  carrying it. A caller reaches the detail only if their role reads the document, so every grown
  value offered is on material the caller could open (D-105's dated note of 10 November 2026,
  night: the security review).
  - A tag that is not grown is vocabulary, offered to every reader: the Project, Process and Topic
    values a database is seeded with, and since D-128 those an Administrator adds with
    `POST /api/tags`. Its being offered says nothing about any source.
  - A grown tag is one of three kinds:
    - a Topic a person's name created or brought back from retirement, typed on this route;
    - a Topic that a person's confirmation of a proposal created or brought back (D-105). For one
      day, D-128 also had the classifier create values; D-129 reversed it;
    - a value that only material some role cannot read carried when the database was seeded, or
      when `documents 0011` ran.
  - An inactive tag never is.
- **What can appear or disappear.** Nothing here moves because a link on material the caller cannot
  read was made or destroyed.
  - A grown tag appears when a source every role in the audience reads comes to carry it, and
    disappears only when the last such source is deleted, or the tag is retired: a removed link is
    kept and still counts.
  - A tag that is not grown never moves while it is active: no link anyone makes or destroys changes
    whether it is offered, a person confirming a proposal of its name made before it was vocabulary
    included. It leaves only when an Administrator retires or deletes it. A retired value comes
    back grown: a Topic a person names again, and since D-128 any value a person confirms from a
    proposal or the classifier suggests at or above the threshold.
- **It includes tags already on the document,** held, applied or removed: applying one of those
  is the `200` above.
- **A `409` names a tag in this list:** the interface can select it rather than create a duplicate.
- **A Topic name that is not in this list but exists** (grown and on no source the document's
  whole audience reads, or inactive) is linked and answered `201` exactly as a new Topic is, unless
  this document already holds a link to it, live or removed: that link is kept, or restored if
  removed, and the answer is `200`. Either answer depends only on this document's own links, so it
  never tells the caller that a value they cannot see exists. After that the Topic is
  in this document's list, and it stays there after a person removes it, since the removed link is
  kept: a person who applies a new Topic, removes it and applies it again by name gets `201`, `204`,
  `409`, whatever exists elsewhere, and the `409` names the Topic, which its id restores (`200`).

**The 201 bodies** of `POST /api/documents` and `POST /api/documents/{id}/reprocess` carry
`classification` (section 7.8 line 100): the object, or `null` when classification failed or the
provider was unavailable, in which case the document is indexed and unclassified (invariant 8,
D-33 part 1). A 422 body does not carry it, and neither do the list and browse routes.

**FR-15's reads and provisional links (D-105).** A provisional link is held, not applied: it is not
in the detail's `tags`, not a browse facet value and not a filter hit until it is confirmed.
`tag_details` is where a held suggestion is seen.

**Removed links (D-105's dated note of 10 November 2026, night).** A link a person removed, the
machine's or a person's, is in **no** read: not the detail's `tags` or `tag_details`, not the
classify, confirm or proposed-tag replies' `tag_details`, not a browse facet value and not a
filter hit. Its id answers `404` on the confirm and remove routes, exactly as an unknown id does.
It stays in the database for FR-10's correction clause, for two reasons:

- an AI link, so that the machine's assignment is kept beside the person's decision;
- a person's link, so that a later classify or reprocess neither links the value again nor
  proposes it again ("not overwritten by later reprocessing").

Since D-128 any removed link on the document, the machine's or a person's, keeps a later run from
proposing, creating or reactivating that value for this document, in any dimension.

Applying the tag again restores the link (`200`).

**The management command** `python manage.py classify_documents --all | --document <uuid>...
[--out record.json]` runs the same path per document and writes the Objective 05 record (D-106:
database, commit, per-document values, outcomes, links, seconds or error). It refuses the
database `kmp`.

### Tag administration (D-119 finding 5; D-105's dated note of 10 November 2026, night)

FR-10's taxonomy clause: "Tags are deactivated rather than deleted where content still references
them, preserving historical classification"; its CRUD line gives Tags "Create" and "Delete" (Create since D-128). Every route needs a
session **and** `manage_tags`, which accounts 0008 gives the Administrator alone: `401` without a
session, `403` for a role that lacks the code (invariant 4), checked before anything else on the
request, since nothing on these routes is scoped.

| Method | Path | Auth | Success | Errors |
|---|---|---|---|---|
| GET | `/api/tags` | session + `manage_tags` | `200` a list of tag entries (below): every Tag in Project, Process and Topic, active or not, ordered by dimension (alphabetically: Process, Project, Topic) then name. `[]` when there are none. No pagination | `401`; `403` |
| POST | `/api/tags` | session + `manage_tags` | **D-128:** an Administrator adds a value to the established scheme. Body `{"dimension": "Project"\|"Process"\|"Topic", "tag_name": string}`, the name trimmed and normalised (single spaces, lower case). `201` the tag entry, `active: true`, `item_count: 0`. The new Tag is **vocabulary** (not grown): offered in every document's `tag_options` and listed in every classification prompt, whatever the document's audience, as a seeded value is | `401`; `403`, before the body is read; `400 {"dimension": ["..."]}` missing or not one of the three (`Department` included); `400 {"tag_name": ["..."]}` blank, missing or over 255 characters; `409 {"detail": "...", "tag_id": "uuid"}` a Tag with that normalised name already exists in that dimension, **active or retired** (a concurrent create of the same name included). It is not reactivated, and its `grown` is not changed. `429` past `TAGGING_THROTTLE_RATE`, the `tagging` scope, after the 401 and the 403; `GET` is not throttled |
| DELETE | `/api/tags/{id}` | session + `manage_tags` | `200` the tag entry, now `active: false`, when any `ContentTags` row references the tag, in **any** state (held and removed links included); `200` again for a tag already inactive and still referenced. `204` no body when nothing references it: the tag is deleted | `401`; `403`, before the id is looked at; `404 {"detail": "No Tag matches the given query."}` no tag with that id in Project, Process or Topic (a Department tag included) |

The tag entry, in the list, in the `POST`'s `201` and in the `DELETE`'s `200`:

```json
{"tag_id": "uuid", "dimension": "Project", "tag_name": "bridge maintenance", "active": true,
 "item_count": 3}
```

- **`item_count`** is the number of sources, documents and meetings alike, with a link to the tag
  that is neither provisional nor removed, each source counted once. It is not scoped: an
  Administrator reads every source (D-66), so a count discloses nothing to the one role that may
  ask for it, and a test holds that every role given `manage_tags` has the Administrator's scope.
- **A retired tag** (`active: false`) leaves every document's `tag_options` and cannot be applied
  by `tag_id` (the `400`). The classifier is no longer shown it.
  - **A suggestion of it is treated as a new value:** a Topic one is proposed, and a Project or
    Process one is discarded (D-129, as before D-128). The classifier never reactivates it.
  - **A person's confirmation of a proposed Topic,** or their Topic name form below, reactivates it,
    grown, only through a document every role can read: the security review of D-128, finding 1.
    - Through any other document, it is linked and stays retired. Reactivating it there would put
      the value back in front of every reader of material that already carries it, though nothing
      they read had changed.
    - The readers of such a document are Administrators, who see retired tags in `GET /api/tags`.
  - **It stays on the documents that carry it:** FR-15's reads do not consult `active` (D-72), so
    it is still in their `tags` and `tag_details`, a facet value and a filter.
- **There is no reactivation route,** and `POST /api/tags` answers `409` for a retired name rather
  than reactivating it. A retired Topic comes back in two ways, each only through a document every
  role can read (D-128's security review); through any other document it is linked and stays
  retired:
  - a person types the name of a retired Topic on `POST /api/documents/{id}/tags`, where it is
    linked and reactivated and answered `201` exactly as a new Topic would be. If that document
    already holds a link to it, live or removed, the link is kept or restored: `200`;
  - a person confirms a proposal of it.

  Applying it by `tag_id` is the `400`: an inactive tag is never offered. A retired Project or
  Process tag stays retired (D-129; for one day D-128 let the classifier bring one back).

## NIT3004 — FR-19, Objective 06

### FR-19 — knowledge-gap log

The Administrator's list of "questions the system could not answer and searches returning no
results, grouped by subject with an occurrence count and the ability to mark an entry as
addressed". Decisions: D-107 (the tables, the cycle, the routes, the permission and the dashboard
panel), D-108 (the permission exclusion), D-109 (similarity grouping), D-126 (the exclusion's rule
per embedding model) and D-127 (a follow-up's two strings). Every route needs a
session **and** `review_knowledge_gaps`, which accounts 0007 gives the Administrator alone: `401`
without a session, `403` for a role that lacks the code (invariant 4), checked before anything
else on the request.

| Method | Path | Auth | Success | Errors |
|---|---|---|---|---|
| GET | `/api/knowledge-gaps` | session + `review_knowledge_gaps` | `200` a list of entry objects (below): Open entries first, by `occurrence_count` descending then `last_seen_at` descending, then Addressed entries in the same order. `[]` before any cycle. No pagination | `401`; `403` |
| POST | `/api/knowledge-gaps/cycles` | session + `review_knowledge_gaps` | `201` the cycle object (below). One aggregation cycle runs synchronously, in one transaction | `401`; `403`; `503 {"detail": "The knowledge service is temporarily unavailable, so the aggregation cycle did not run and nothing was changed. Please try again shortly."}` when embedding fails after `MAXIMUM_EMBED_ATTEMPTS` (NFR-19); the cycle rolls back |
| PATCH | `/api/knowledge-gaps/{id}` | session + `review_knowledge_gaps` | `200` the updated entry object. Body `{"status": "Addressed"}` or `{"status": "Open"}`; only the status changes | `401`; `403`; `404` no entry with that id, checked before the body; `400 {"status": ["..."]}` any other value, or none |

The entry object, in the list, in `PATCH`'s reply and in the dashboard's `knowledge_gaps.top`:

```json
{"gap_id": "uuid", "subject": "What is the WFH stipend policy?", "occurrence_count": 6,
 "status": "Open", "first_seen_at": "2026-11-02T09:14:00+11:00",
 "last_seen_at": "2026-11-09T09:25:00+11:00"}
```

The cycle object:

```json
{"cycle_id": "uuid", "started_at": "2026-11-09T21:40:02+11:00",
 "finished_at": "2026-11-09T21:40:05+11:00", "queries_considered": 4,
 "searches_considered": 1, "entries_created": 2, "entries_updated": 1}
```

The dashboard's addition, in `GET /api/dashboard` for a role holding `review_knowledge_gaps`
only:

```json
"knowledge_gaps": {"open_count": 7, "top": [entry object, ...]}
```

- **`subject`** is the first member's wording, verbatim: no model writes it (D-107).
- **`occurrence_count`** is the number of questions and searches grouped into the entry, and
  equals its membership rows. **No payload names who asked, their role, or why a question went
  unanswered**, and none counts the rows left out (D-107, D-108).
- **The cycle's counts are of rows that entered the log:** `queries_considered` and
  `searches_considered` are the `QueryLog` and `SearchLog` rows the cycle added, `entries_created`
  the entries it started, and `entries_updated` the entries that already existed and gained a
  member. A row left out on permission grounds appears in no count.
- **`top`** holds up to `DASHBOARD_GAP_ITEMS` (5) **Open** entries, in the list's order, and
  `open_count` counts every Open entry. The dashboard's `date_from`, `date_to` and `department`
  filters do not narrow either: an entry has no department, and its dates are its own.

**What a cycle does** (D-107 to D-109, D-126, D-127). The scheduled trigger is `python manage.py
aggregate_knowledge_gaps`, which prints the database name, runs one cycle and prints its counts,
and exits 1 on a provider outage. The route runs the same cycle on demand.

1. **The window** is every unanswered `QueryLog` row (FR-13 turns included) and every `SearchLog`
   row with `result_count` 0, timestamped from the previous cycle's start less
   `CYCLE_GRACE_SECONDS` (60) up to this cycle's start, and not already in the log. The first
   cycle takes everything before it.
2. **A row is left out when the asker's role explains it** (D-108, D-126, D-127). A question is
   embedded and ranked over the Administrator's whole scope. A one-off question is decided on its
   own wording. A conversation follow-up is decided first on the string retrieval ranked, its
   earlier turns and then the question as the ask composed them, and then, unless that left it
   out, on its own wording; either can leave it out. A question from a role that reads nothing is
   left out before anything is embedded. Which passage decides is the embedding model's rule
   (`GAP_EXCLUSION_RULE_BY_MODEL`):
   - **rank-one,** for every model the map does not list, EmbeddingGemma included: the top-ranked
     passage, whether or not it clears `RELEVANCE_THRESHOLD`;
   - **threshold-first,** for `voyage-4`: the top passage at or above the model's own relevance
     threshold. If no passage reaches it, nobody could have been answered, and that string does not
     leave the row out.

   If a string's deciding passage is one the asker's role cannot read, the row is left out.
   Otherwise that string does not leave it out, as when no passage of the question's embedding
   model exists. A row that no string leaves out is kept. A search is
   counted again as the Administrator, writing no `SearchLog` row; above zero, it is left out. A
   kept search term longer than `MAXIMUM_QUESTION_LENGTH` is cut to that length before it is
   embedded and stored as a subject. Nothing records a row that was left out.
3. **Kept rows are grouped by similarity** (D-109): in timestamp order, each joins the nearest
   Open entry, embedded by the same model, whose centroid's cosine is at least the model's
   grouping threshold (`GAP_GROUPING_THRESHOLD`, or its own value in
   `GAP_GROUPING_THRESHOLD_BY_MODEL`, D-122), or starts a new entry. A follow-up is grouped, and
   shown as a subject, on its own wording. An Addressed entry is never joined, so a subject that
   recurs after being addressed opens a new one.

## Recording transcription (D-123)

Not in the proposal: §1.9 puts live transcription and native recording capture out of scope, and
FR-09 takes a transcript file or pasted text. The user decided on 10 November 2026 that a person
with a meeting **recording** can have it transcribed into a **draft**, which they review before it
is added. These routes, the status and the segment, turn the recording into the draft's text. **Neither stores anything**:
no meeting, no chunk, no file and no row. The reviewed draft is added through FR-09's
`POST /api/meetings` as `transcript_text`, exactly as pasted text is, which stays the one path
into the index.

| Method | Path | Auth | Success | Failures |
|---|---|---|---|---|
| GET | `/api/transcriptions/status` | session + `contribute_content` | `200 {"enabled": bool, "available": bool, "segment_seconds": 30, "maximum_segment_seconds": 60}` | `401`; `403` the role lacks `contribute_content`; `429` past `TRANSCRIPTION_THROTTLE_RATE`, one budget with the segments |
| POST | `/api/transcriptions` | session + `contribute_content` | `200 {"status": "transcribed", "text": "...", "model": "whisper-v3:turbo", "duration_seconds": 29.6, "loudest_dbfs": -18.4}`, or `200 {"status": "silent", "text": "", "model": null, "duration_seconds": 30.0, "loudest_dbfs": -61.2}` | `401`; `403` the role lacks `contribute_content`; `429` past `TRANSCRIPTION_THROTTLE_RATE` (DRF's body, with `Retry-After`); `503 {"detail": "...", "code": "transcription_disabled"}` transcription is not enabled on this server; `413` a declared `Content-Length` over 50 MB, or a segment over it; `400 {"audio": ["..."]}` no `audio` part, a segment with no audio frames, or one longer than `MAXIMUM_TRANSCRIPTION_SEGMENT_SECONDS`; `415` not a 16-bit PCM mono WAV at 16 kHz, or a body that is not multipart; `429 {"detail": "...", "code": "transcription_in_flight"}` another segment of this user's is with the provider; `429 {"detail": "...", "code": "transcription_busy"}` with `Retry-After` (5 s), the server is already transcribing `MAXIMUM_TRANSCRIPTIONS_IN_FLIGHT` (2) segments; `503 {"detail": "...", "code": "transcription_unavailable"}` the provider failed after `MAXIMUM_TRANSCRIBE_ATTEMPTS`, or refused the segment (D-118) |

**The request is `multipart/form-data`**, one field, `audio`: one segment of the recording as a
16-bit PCM WAV. The page decodes the recording in the browser, resamples it to 16 kHz mono and cuts
it into segments of at most `segment_seconds`, at the quietest tenth of a second in each segment's
last third (the last may run up to a second longer), then sends them one at a time. The recording itself never reaches the server, so the
50 MB ceiling bounds each segment, not the recording; the page bounds the recording at
`MAXIMUM_RECORDING_BYTES` (500 MB), which only the client enforces. A cross-site multipart POST is
refused for want of the CSRF token, as on the upload.

**The rejection order** is fixed, each before any provider call: `401`, `403`, the `429` rate, the
`503` `transcription_disabled`, the `413` on the declared length, the `400` for no `audio`, the `413`
on the bytes received, the `415`, the `400` for an empty or over-long segment. Then a silent segment
is answered `200` `silent`, then the in-flight `429`, then the busy `429`, then the provider.

**Since D-124 the order is of the reading too.** Nothing reads the body before the declared-length
`413`, so a body refused there or earlier is never parsed.

- **How:** the CSRF check takes its token from the `X-CSRFToken` header and parses nothing.
- **What still bounds receiving:** Waitress's cap, `MAX_REQUEST_BODY_BYTES` (see Stage 2).
- **Corrected 11 November 2026.** Until D-124 this paragraph said, truly, that a session sending its
  CSRF token had its whole multipart body parsed by DRF while authenticating, before any of these
  answers. D-123 recorded that as open, and its dated note records the close.

**Only what the page sends is accepted:** a 16-bit PCM mono WAV at 16 kHz.

**Format is decided by the bytes.** A WAV is a RIFF file whose form type is `WAVE`; the filename
and the part's declared type are never consulted.

**Silence never reaches Whisper.** The server measures the segment's loudest half second, and below
`TRANSCRIPTION_SILENCE_DBFS` (-45 dBFS) answers `silent` without calling the provider: Whisper
invents text from silence. Every reply carries that level as `loudest_dbfs`, rounded to a tenth,
and `null` for digital silence, so the threshold (*tune*) can be checked on real recordings. What is sent to the provider is a WAV rebuilt from exactly the frames
measured, so a header that understates its data cannot carry more audio past the checks.

**The 503s are told apart by `code`.** `transcription_disabled` means paste or upload the
transcript instead; `transcription_unavailable` means nothing was stored and the same segment can
be sent again. The page keeps the recording and the draft through either (invariant 8). After
`transcription_unavailable` it resumes from the failed segment; after `transcription_disabled` there
is nothing to resume until transcription is switched on again.

**`available` means FLM answered, not that its speech model is loaded.** FLM's model list names
its chat catalogue, not `whisper-v3:turbo`, so a server started without `--asr 1` reports
available and fails the first segment, which the page shows as unavailable. No provider detail is
returned: it names an internal address.

**Transcription is off by default** (`TRANSCRIPTION_PROVIDER=none`), so a host without the NPU
offers no control that cannot work (D-114). Such a host still ingests a transcript made elsewhere,
saved from the page as a text file, through FR-09's file option.


## NIT3004 — FR-16 meeting summary and action items (D-125)

"A "Summary" panel on the meeting page", "A "Regenerate Summary" button", and "An "Action Items"
panel [that] lists each extracted item with description, suggested owner and due date, all
editable." One decision, D-125, holds the operation, the schema, the retrieval exposure, the retry
queue and every route below.

**Scope first, permission second, on every route.** The meeting is resolved through the caller's
scope, so a meeting the caller cannot see and one that does not exist are the same
`404 {"detail": "No Meeting matches the given query."}` (invariant 1). Reading needs only a
session. The four writes then need `contribute_content`, which both roles hold (D-30), checked
inside the method after that lookup: `403` for a role without it (invariant 4).

| Method | Path | Auth | Success | Errors |
|---|---|---|---|---|
| GET | `/api/meetings/{id}/summary` | session, meeting in scope | `200` the summary state (below) when nothing is pending; **`202`** with the same body while a run is `Processing` or queued for its automatic retry | `401`; `404`; **`422`** the same body plus `detail` when the transcript is under `MINIMUM_SUMMARY_TRANSCRIPT_LENGTH` (200 words) |
| POST | `/api/meetings/{id}/summary` | session + `contribute_content` | **`202`** the summary state, with `status` `"Processing"`. Starts a run, or reports the one already in flight for this meeting. No body is read | `401`; `404`; `403`; `422` too short, nothing started; `429` past the "ingestion" rate |
| POST | `/api/meetings/{id}/action-items` | session + `contribute_content` | `201` the action item object. Body `{"description": "...", "owner_id": "uuid" or null, "due_date": "YYYY-MM-DD" or null}`; only `description` is required | `401`; `404`; `403`; `400 {"description": [...]}` blank, missing or over 1,000 characters; `400 {"owner_id": ["No user has this id."]}`; `400 {"owner_id": ["This person cannot see this meeting, so its action items cannot be theirs."]}` a user whose role cannot read the meeting (D-125's third note; only an Administrator can meet it, on a meeting marked for Administrators only, since every role reads what an Employee can reach, D-66); `400 {"due_date": [...]}`; `409 {"detail": "This meeting already has 200 action items, the most one meeting can hold. Delete one to add another."}` at `MAXIMUM_ACTION_ITEMS_PER_MEETING`, every item counted, nothing written (D-125's third note); `429` past the `action_items` rate |
| PATCH | `/api/meetings/{id}/action-items/{item_id}` | session + `contribute_content` | `200` the updated item. Body: any of `description`, `owner_id`, `due_date`; a field left out is unchanged, and `null` clears the owner or the date | `401`; `404` the meeting, or an `item_id` that is not one of this meeting's (the same body); `403`; `400` as above, and `400 {"non_field_errors": ["Send at least one of description, owner_id and due_date."]}` for an empty body; `429` past the `action_items` rate |
| DELETE | `/api/meetings/{id}/action-items/{item_id}` | session + `contribute_content` | `204`, no body | `401`; `404` as PATCH; `403`; `429` past the `action_items` rate |

The summary state, from both summary routes at every status code they answer:

```json
{"status": "Ready",
 "queued_for_retry": false,
 "summary": {
   "summary_id": "uuid",
   "summary_text": "The team reviewed the first quarter. It froze discretionary travel until January.",
   "narrative": [{"text": "The team reviewed the first quarter.", "passages": [1]},
                 {"text": "It froze discretionary travel until January.", "passages": [1, 2]}],
   "decisions": [{"text": "Discretionary travel is frozen until 31 January.", "passages": [2]}],
   "highlights": [{"text": "Travel was twice its budget.", "passages": [1]}],
   "passages": {"1": "Ravi: Thanks, everyone. This is the first-quarter review ...",
                "2": "... So the decision is that discretionary travel is frozen ..."},
   "model": "claude-haiku-5-5",
   "generated_at": "2026-11-11T14:02:11+11:00",
   "input_truncated": false,
   "passages_sent": 2,
   "passages_total": 2,
   "action_items_extracted": 4},
 "action_items": [action item object, ...],
 "can_edit": true}
```

- **`status`** is the latest run's: `"Processing"`, `"Ready"` or `"Unavailable"`, or `null` where
  no summary was ever requested for this meeting (one ingested before FR-16, or one too short).
- **`queued_for_retry`** is NFR-20's flag on that run. `"Unavailable"` with it true means the
  hourly retry will run it again, and the route answers `202`. `"Unavailable"` with it false means
  the retries are spent, and only Generate will try again; the route answers `200`.
- **A run left `"Processing"` for more than `SUMMARY_STALE_AFTER_SECONDS` (2,400 s) is reported
  as `"Unavailable"` with `queued_for_retry` true.** Such a run was left by a server that stopped
  mid-run, and that is what the next scheduled retry makes of it. The page then stops asking and
  offers Generate, and a POST closes the stale run and starts a new one.
- **`summary`** is the meeting's latest **Ready** summary, or `null`. It is never a failed one:
  "in the failed state it is never presented to a user" (UC-04). While a Regenerate runs, and
  after one fails, it is still the previous Ready summary, so `status` and `summary` can differ.
- **`narrative`, `decisions`, `highlights`:** each element's `passages` are numbers into the
  summary's `passages` object, which holds the text of every transcript passage an element names
  (UC-04: "every element of the summary carries a reference to the passage of the transcript it
  was drawn from"). `summary_text` is the narrative's sentences joined. Every reference was
  checked by the application to be a passage that was sent to the model; an element that named
  none is not here (invariant 5).
- **`model`, `generated_at`:** UC-04's "record of the model that produced it and the date".
- **`input_truncated`:** true when the transcript was longer than one request carries
  (`SUMMARY_INPUT_TOKENS`, or `SUMMARY_INPUT_CHARACTERS`, which real speech does not reach). The
  summary then covers the first `passages_sent` of `passages_total` passages, and the page says so.
- **`action_items_extracted`** is how many items that run extracted. 0 is UC-04 A1's meeting
  that raised none, "recorded as empty rather than omitted".
- **`can_edit`** is whether the caller's role holds `contribute_content`: a hint for showing the
  controls. Every write checks the permission itself.

The action item object:

```json
{"action_item_id": "uuid",
 "description": "Reconcile the September card statements",
 "owner": {"id": "uuid", "name": "Alex Morgan"},
 "owner_name": "Alex",
 "due_date": "2026-10-23",
 "due_text": "next Friday",
 "passages": [2],
 "origin": "ai",
 "edited": false,
 "created_at": "2026-11-11T14:02:11+11:00",
 "updated_at": "2026-11-11T14:02:11+11:00"}
```

- **`owner`** is the user the item is assigned to, or `null`: **unassigned**. The server assigns
  an extracted item only where the transcript's name, a full name or a lone first name, matches
  exactly one of the meeting's recorded attendees, and that attendee's role can read the meeting.
  Anything else is unassigned, "rather than attributed to the wrong person". Until the security
  review of 12 November a full name was matched against every user (D-125's third note).
  `GET /api/users/directory` lists the people a person may choose; one whose role cannot read the
  meeting is refused with a `400` keyed on `owner_id`.
- **`owner_name`** and **`due_text`** are the transcript's own words for the owner and the
  deadline ("the facilities team", "next Friday"), blank where it said nothing and on an item a
  person added. An edit does not change them.
- **`due_date`** is the date the server converted `due_text` to, from the meeting's date, or
  `null` where the phrase fixes none ("next week", "before the move"). A date is never invented.
- **`passages`** are numbers into the extracting summary's `passages`; `[]` on an item a person
  added. After a Regenerate, a kept item's numbers still name the transcript's own passages, but
  the current summary's `passages` object holds only the passages *it* cites, so the page shows a
  passage where it has the text and the number alone where it does not.
- **`origin`** is `"ai"` (extracted) or `"user"` (added by a person). **`edited`** is true once a
  person has changed an extracted item. NFR-15's badge reads both: "Suggested by AI",
  "Suggested by AI, edited by a person", and none for `"user"`.
- **Order:** the latest run's extracted items in the model's order, then the items a person
  edited or added, in the order they already had. A Regenerate renumbers them so this stays true.

**What a run does** (D-125). It starts automatically when `POST /api/meetings` stores a transcript
of 200 words or more, and again on `POST .../summary`. One run is in flight per meeting.

1. The transcript's own passages (FR-09's chunks) are sent in one request, up to
   `SUMMARY_INPUT_TOKENS` and `SUMMARY_INPUT_CHARACTERS` (D-125's third note: a whitespace token
   has no length limit). The reply must match `SUMMARY_SCHEMA`, whose every limit the prompt
   states: a malformed reply gets one
   retry, a failed call two (`MAXIMUM_SUMMARY_ATTEMPTS`, three in total), and a `429` is retried
   while any other `4xx` ends the run at once (D-118).
2. Every reference is checked against the passages sent. Owners are matched and dates converted
   by the application.
3. The summary, its action items and its search index entries are written in one transaction.
   The extracted items nobody touched are replaced; **items a person added or edited are kept**.
4. A run that fails is `"Unavailable"` and queued. `python manage.py retry_meeting_summaries`,
   scheduled hourly (`scripts/register_meeting_summary_schedule.ps1`), runs each queued summary
   again, up to `MAXIMUM_SUMMARY_RETRY_RUNS` (3) times; a run that failed because no reply
   conformed is queued once (`MAXIMUM_MALFORMED_RETRY_RUNS`, D-125's third note). A run the server
   has no room to start, with `MAXIMUM_SUMMARIES_WAITING` already waiting, is queued the same way
   without reaching the provider. The transcript is stored and searchable throughout: a summary's
   failure never touches it (invariant 8, NFR-20).

**`POST /api/meetings` is unchanged.** Its `201` body does not mention the summary; the meeting
page asks `GET .../summary`.

### The summary as source material (UC-04, D-125 choice 1)

A Ready summary's narrative, decisions and highlights are indexed as passages of **the meeting
itself**, under the meeting's own `visible_to_roles`, so FR-12 can find and cite them. Its action
items are not indexed. Two existing payloads gain one field each, so that an AI-written passage
is never shown as the transcript's words (NFR-15):

- **`POST /api/ask` and `GET /api/conversations/{id}`:** each object in `sources[].passages`
  gains **`"ai_generated": true | false`**. True for a passage of a meeting's AI-generated
  summary. Such a passage's `text` is the summary's own sentences (the narrative, then each
  decision and highlight, one to a line) with nothing added, so the flag is the only thing that
  says it is AI content. Its source is the meeting, as for any other passage of it.
- **`GET /api/search`:** each result gains **`"snippet_ai_generated": true | false`**. True where
  the snippet shown comes from the meeting's AI-generated summary, which happens only when the
  term occurs in the summary and nowhere in the transcript. A meeting found through its summary
  alone is still one result, in the meetings group, counted once.
