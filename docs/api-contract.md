# API contract

The request and response shapes every endpoint honours. The front end builds against
this file; the tests assert it. Each stage appends its own endpoints. Status codes
marked *convention* were chosen where the FR section available to the build session
did not state one and must be confirmed against the proposal.

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

| Method | Path | Auth | Success | Failures |
|---|---|---|---|---|
| POST | `/api/auth/register` | none | `201` user object; role is Employee | `400` validation (name required, email invalid, password fails the validators); `409` email already registered (FR-01) |
| POST | `/api/auth/login` | none | `200` user object; sets the session cookie and the `csrftoken` cookie | `400` malformed body; `401 {"detail": "Invalid email or password."}` for unknown email or wrong password (same message for both) |
| POST | `/api/auth/logout` | session | `204`; session destroyed server-side | `401` no valid session |
| GET | `/api/auth/me` | session | `200` user object; refreshes the `csrftoken` cookie | `401` |
| GET | `/api/roles` | session | `200 [{"name": "Employee", "description": "...", "permissions": ["..."]}]` | `401` |
| GET | `/api/users` | Administrator | `200 [user object, ...]` ordered by `created_at` | `401`; `403` Employee |
| PATCH | `/api/users/{id}/role` | Administrator | `200` updated user object; writes an audit entry | `400 {"role": [...]}` unknown role name; `401`; `403` Employee; `404` unknown user (*convention*) |

Login side effects (FR-02, `docs/schema-v1.md` Users notes): a failed attempt
increments `failed_attempts`; the fifth consecutive failure sets `locked_until` to
now plus `LOCKOUT_DURATION`; a success resets `failed_attempts` to 0 and sets
`last_login_at`. Enforcing the lock is FR-03 (NIT3004) and is **not** part of Stage 2.

Registration (*convention*, to confirm): `201` rather than `200`; password rules are
Django's default validators (minimum length 8, not entirely numeric, not too common,
not too similar to the name or email).

Session: 60-minute inactivity expiry (D-10). An expired or invalid session cookie is
`401` on every route that needs one.
