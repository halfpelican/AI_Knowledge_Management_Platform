/**
 * The account routes #119's Profile page uses, built on the server by D-137, per
 * docs/api-contract.md, "FR-04 — account self-service". Thin wrappers over the one
 * API client; no fetch here.
 */
import { del, post, upload } from './client.js'

/**
 * The `code` on the picture upload's 429 while the server is decoding as many
 * pictures as it allows, anyone's (`picture_busy`, with `Retry-After: 5`). The page
 * tells it from the `picture` rate's 429, which carries no code, by this, and never
 * by `detail`. apps/api/tests/test_in_flight_codes_agreement.py holds every
 * exported `*_CODE` to the constant of the same name in apps/api/views.py.
 */
export const PICTURE_BUSY_CODE = 'picture_busy'

/**
 * D-137, under FR-01's password rules. 200 `{"detail": "Your password has been
 * changed."}`: this session stays signed in under a new key, and every other
 * session of the user ends. 400 field errors on `current_password` and
 * `new_password`, a wrong current password included, never a 401; 401 no session;
 * 403 CSRF; 429 past the `password_change` rate, with `Retry-After`.
 *
 * One change at a time (the contract's CHG-3): a request this browser sends while a
 * change is in flight carries the session key the change replaces, and if it is
 * answered after the change, its 401 clears the new key's cookie. The page sends
 * nothing else until the change has answered.
 */
export function changePassword({ currentPassword, newPassword }) {
  return post('/auth/change-password', {
    current_password: currentPassword,
    new_password: newPassword,
  })
}

/**
 * D-137. Multipart, one file part, `picture`: a PNG, JPEG or WebP of at most 5 MB.
 * 200 the user object, its `picture` the new address. 400 no `picture` part; 413
 * too large, in bytes or in pixels; 415 not one of the three formats, or damaged;
 * 429 past the `picture` rate, or `picture_busy`; nothing is stored for any of them.
 */
export function uploadProfilePicture(file) {
  const formData = new FormData()
  formData.append('picture', file)
  return upload('/users/me/picture', formData)
}

/**
 * D-137. 200 the user object with `picture` null, idempotent: a user with no picture
 * gets the same 200. No body is sent. 401; 403 CSRF.
 */
export function removeProfilePicture() {
  return del('/users/me/picture')
}
