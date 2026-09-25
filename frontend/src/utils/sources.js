import { SOURCE_TYPE, TEXT } from '../constants.js'

/**
 * Where a search result or a consulted source is read, and what the link to it
 * says.
 *
 * FR-12 requires that a citation "links to the source document or meeting", and
 * both types now have a screen of their own:
 *
 * - A **meeting** is at `/meetings/{id}`, served by `GET /api/meetings/{id}`,
 *   which returns the transcript in full (FR-09).
 * - A **document** is at `/documents/{id}`, served by `GET /api/documents/{id}`
 *   (D-46, Stage 4 item 10b). Until that endpoint existed the link went to the
 *   repository list with a label saying to find the document there, which
 *   satisfied "a link" and not "links to the source document".
 *
 * Either route answers 404 both for an id that names nothing and for a source
 * outside the caller's scope, so following a link is not a way to learn that an
 * id is real (CLAUDE.md §6, invariant 1). A citation cannot lead anywhere the
 * asker was not entitled to go in any case: it names a passage that was supplied
 * to generation, and the candidate set was restricted to their scope before
 * ranking.
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
    return { to: `/documents/${encodeURIComponent(id)}`, label: TEXT.viewDocument }
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
