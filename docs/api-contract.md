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
| POST | `/api/documents` | session + `contribute_content` | `201` document object, carrying `doc_id` | `400` no file, or an empty title, or a `visible_to_roles` that is empty or names an unknown role; `401`; `403` the role lacks `contribute_content`, or the list excludes the uploader's own role (*convention*, D-29); `409` a document with the same content already exists; `413` over 50 MB; `415` the file signature is not one of the four accepted formats; `422` the document was stored but no text could be extracted, or it holds too little text to index, or every chunk failed to embed |
| POST | `/api/documents/{id}/reprocess` | session + `contribute_content` | `201` the document object, now `Indexed` or `Partially indexed` | `401`; `403` the role lacks `contribute_content`; `404` no such document, or one outside the caller's scope; `409` already indexed, or restoring its content hash collided with a copy indexed meanwhile; `422` the reprocess failed the same way the upload did |
| GET | `/api/documents` | session | `200 [document object, ...]`, newest first, scoped to the caller's role | `401` |

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
then signature (415), then size (413), then title (400), then duplicate (409). §7.2
says why the permission is first — "it is the cheapest rejection, and the user's role
may have changed during a transfer of up to 50 MB".

**The size ceiling is applied twice**: once against the declared `Content-Length`,
before the body is parsed, so a 50 MB transfer is refused without being buffered; and
once against the bytes actually received, for a client that lies about or omits the
header.

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
