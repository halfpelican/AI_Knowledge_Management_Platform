/**
 * FR-10 tag administration, per docs/api-contract.md "Tag administration (D-119
 * finding 5; D-105's dated note of 10 November 2026, night; D-128)". Thin wrappers
 * over the one API client; no fetch and no XMLHttpRequest here.
 *
 * Every route needs a session **and** `manage_tags`, which accounts 0008 gives the
 * Administrator alone: 401 without a session, 403 for a role that lacks the code,
 * checked before anything else on the request. The screen that calls these is
 * offered to an Administrator only, and that is usability: the server checks the
 * code on every request whatever the interface showed (CLAUDE.md §6, invariant 4).
 */
import { TAG_OPTION_DIMENSIONS } from './documents.js'
import { get, post, requestWithStatus } from './client.js'

/**
 * The dimensions `createTag` accepts, in the order the screen offers them: the three
 * tag dimensions, mirroring apps/core/constants.py REPOSITORY_TAG_DIMENSIONS, the same
 * three a person applies a tag in. Department is the document's own field, not a tag
 * (D-72). The server answers 400 `{"dimension": [...]}` for any other, whatever the
 * screen offered.
 */
export const CREATE_TAG_DIMENSIONS = TAG_OPTION_DIMENSIONS

/**
 * `GET /api/tags` — every Tag in Project, Process and Topic, active or not,
 * ordered by dimension (alphabetically: Process, Project, Topic) then by name. The
 * order is the server's, and the screen keeps it.
 *
 * 200 with a list of `{tag_id, dimension, tag_name, active, item_count}`, `[]` for
 * none, no pagination. `item_count` is the number of sources, documents and
 * meetings alike, with a link to the tag that is neither provisional nor removed,
 * each counted once. It is not scoped, because the one role that may ask reads
 * every source (D-66). 401; 403.
 *
 * @param {object} [options]
 * @param {AbortSignal} [options.signal]
 */
export function listTags(options = {}) {
  return get('/tags', options)
}

/**
 * `POST /api/tags` — an Administrator adds a value to a dimension (D-128; FR-10's
 * CRUD line gives Tags "Create"). Body `{dimension, tag_name}`; the server trims the
 * name, single-spaces it and lower-cases it.
 *
 * 201 with the new entry, `{tag_id, dimension, tag_name, active: true, item_count:
 * 0}`, `tag_name` as stored. The value is vocabulary: offered in every document's
 * `tag_options` and listed for the AI when it classifies any document, whatever the
 * document's audience. 409 `{detail, tag_id}` when a tag of that name is already in
 * the dimension, active or retired; `error.details.tag_id` is that tag, and nothing
 * is changed: a retired tag is not brought back here. 400 keyed on `dimension` (any
 * other than Project, Process and Topic) or `tag_name` (blank or over 255
 * characters). 429 past the `tagging` limit, the one adding a tag to a document
 * counts against too, with `error.retryAfter`. 403 without `manage_tags`; 401.
 *
 * @param {{dimension: string, tagName: string}} value
 * @param {object} [options]
 * @param {AbortSignal} [options.signal]
 * @returns {Promise<object>} The 201's entry.
 */
export function createTag({ dimension, tagName }, options = {}) {
  return post('/tags', { dimension, tag_name: tagName }, options)
}

/**
 * `DELETE /api/tags/{id}` — FR-10: "Tags are deactivated rather than deleted where
 * content still references them, preserving historical classification", and its
 * CRUD line gives Tags "Delete".
 *
 * 200 with the entry, now `active: false`, when any link references the tag, in
 * any state, held and removed links included, so a tag whose `item_count` is 0 can
 * still be deactivated rather than deleted; 200 again for one already inactive and
 * still referenced. 204, no body, when nothing references it: the tag is deleted.
 * 404 `{"detail": "No Tag matches the given query."}` for an id naming no tag;
 * 403 before the id is looked at; 401. There is no route that reactivates a tag.
 *
 * @param {string} tagId
 * @param {object} [options]
 * @param {AbortSignal} [options.signal]
 * @returns {Promise<{deleted: true} | {deleted: false, tag: object|null}>}
 *   `deleted` is the 204; otherwise `tag` is the 200's entry.
 */
export async function deleteTag(tagId, options = {}) {
  const { status, data } = await requestWithStatus(`/tags/${encodeURIComponent(tagId)}`, {
    ...options,
    method: 'DELETE',
  })
  return status === 204 ? { deleted: true } : { deleted: false, tag: data }
}
