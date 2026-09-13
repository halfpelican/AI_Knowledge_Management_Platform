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
| PATCH | `/api/users/{id}/role` | Administrator | `200` updated user object; writes an audit entry | `400` the body is missing `role_id` or it is not a UUID; `401`; `403` Employee, or an administrator demoting themselves (*convention*: FR-05 enumerates only 200, 403 and 404); `404` the user or the role does not exist |

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

**FR-02 role-specific dashboard.** The FR redirects to a dashboard chosen by role.
The dashboards are FR-14, so this is deferred to Stage 5 and recorded in D-25.

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
