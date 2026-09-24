import { SOURCE_TYPE, TEXT } from '../constants.js'

/**
 * Where a search result or a consulted source is read, and what the link to it
 * says.
 *
 * FR-12 requires that a citation "links to the source document or meeting", and
 * the two types do not have symmetrical routes:
 *
 * - A **meeting** has a screen of its own at `/meetings/{id}`, served by
 *   `GET /api/meetings/{id}`, which returns the transcript in full (FR-09).
 * - A **document** has no detail route, because the API has no
 *   `GET /api/documents/{id}` to build one on — the repository list at
 *   `/documents` is the only read route for a document. So the link goes there
 *   and says so, rather than promising a page that does not exist. FR-15's
 *   document detail is Stage 5 work and needs an endpoint that is not in the
 *   contract yet; this is noted rather than invented.
 *
 * An unrecognised `source_type` gets no link at all. The vocabulary is fixed
 * (docs/schema-v1.md §3), so this is the branch that stops a value added later
 * from being rendered as a broken route.
 *
 * @param {{source_type?: string, source_id?: string}} source
 * @returns {{to: string, label: string} | null}
 */
export function sourceLinkFor(source) {
  const id = source?.source_id
  if (!id) return null
  if (source.source_type === SOURCE_TYPE.meeting) {
    return { to: `/meetings/${encodeURIComponent(id)}`, label: TEXT.viewMeeting }
  }
  if (source.source_type === SOURCE_TYPE.document) {
    return { to: '/documents', label: TEXT.viewDocument }
  }
  return null
}

/** The type of a source in words, for a screen that shows results of both kinds. */
export function sourceTypeLabel(sourceType) {
  if (sourceType === SOURCE_TYPE.meeting) return TEXT.sourceTypeMeeting
  if (sourceType === SOURCE_TYPE.document) return TEXT.sourceTypeDocument
  // Never rendered in colour or by an icon alone, and never left blank: an
  // unknown type shows as itself rather than being relabelled as one of the two.
  return sourceType ?? ''
}
