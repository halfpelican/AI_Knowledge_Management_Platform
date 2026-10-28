/**
 * What the three ingestion routes share: `POST /api/documents` and
 * `POST /api/documents/{id}/reprocess` (src/api/documents.js), and
 * `POST /api/meetings` (src/api/meetings.js). They share one per-user rate (D-79)
 * and, since D-85, one slot per user, so a constant read by all three screens lives
 * here rather than in either module.
 */

/**
 * The `code` D-85's in-flight 429 carries on all three routes, `{"detail": "...",
 * "code": "ingestion_in_flight"}`, with no `Retry-After`: another upload, transcript
 * or reprocess of this user's is still being processed, and nothing was stored. It
 * is how a screen tells that 429 from the ingestion rate's, which carries no `code`
 * and a `Retry-After` in seconds. `detail` is never parsed (docs/api-contract.md,
 * "One ingestion in flight per user"). Copied from the contract, as
 * `ASK_IN_FLIGHT_CODE` is in src/api/ask.js.
 */
export const INGESTION_IN_FLIGHT_CODE = 'ingestion_in_flight'
