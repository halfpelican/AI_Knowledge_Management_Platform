/**
 * FR-20's knowledge map, per docs/api-contract.md "NIT3004 — FR-20 knowledge map
 * (D-132)". A thin wrapper over the one API client; no fetch here.
 *
 * The route needs a session **and** `view_knowledge_map`, which accounts 0011 gives
 * both roles: 401 without a session, 403 for a role that lacks the code. The page
 * that calls this is offered to every signed-in user, and that is usability: the
 * server checks the code on every request (CLAUDE.md §6, invariant 4).
 *
 * **This module holds no cache** (D-132, the design review's security finding F9).
 * Every call is a request, and nothing a reply carried is kept here, so a map read
 * by one session can never be shown to the next one signed in on the same tab.
 */
import { get } from './client.js'
import { knowledgeMapQuery } from '../utils/knowledgeMap.js'

/**
 * `GET /api/knowledge-map` — the overview — or, with a focus,
 * `GET /api/knowledge-map?focus_type=<type>&focus_id=<uuid>` — the walk from that
 * node. The query is built with `URLSearchParams` (src/utils/knowledgeMap.js).
 *
 * 200 with the map object, always, from a permitted session:
 * `{focus, nodes, edges, truncated, truncated_by, maximum_node_count,
 * maximum_traversal_depth}`. Everything in it is already scoped to the caller's
 * role, capped and counted by the server (CLAUDE.md §6, invariant 1), and the page
 * renders it as sent.
 *
 * - `focus` is `null` for the overview and for a focus that is not one of the
 *   returned nodes; otherwise `{type, id}`, the identifier in canonical form. The
 *   page marks the selected node from this, never from its own address.
 * - A focus that is not in the caller's own map gets the empty map object, whatever
 *   the reason, so the reply never says whether the identifier names something.
 *
 * 400 `{"<parameter>": ["..."]}` for a `focus_type` outside the vocabulary, a
 * `focus_id` that is not a UUID, or one given without the other; 401; 403.
 *
 * @param {{type: string, id: string}|null} [focus] The selection, or null for the overview.
 * @param {object} [options]
 * @param {AbortSignal} [options.signal]
 * @returns {Promise<object>} The map object.
 */
export function fetchKnowledgeMap(focus = null, options = {}) {
  const query = knowledgeMapQuery(focus)
  return get(query ? `/knowledge-map?${query}` : '/knowledge-map', options)
}

/** The second view's route, relative to the API base (D-138). */
const EVIDENCE_MAP_ROUTE = '/knowledge-map/evidence'

/**
 * `GET /api/knowledge-map/evidence` — the second view's overview (D-138): claims and
 * the passages they cite — or, with a focus,
 * `GET /api/knowledge-map/evidence?focus_type=<claim|passage>&focus_id=<id>` — the walk
 * from that node. The same permission, the same status codes and the same two
 * parameters as the route above, so the query is built by the same function.
 *
 * 200 with the first view's seven keys. A node also carries `detail`: a claim's
 * `{answer_count, passage_count, first_admitted_at, last_admitted_at}`, a passage's
 * `{source_type, source_id, source_title, position, ai_generated}`. An edge reads
 * "claim, cites, passage" and also carries `weight`, how often that pairing was
 * admitted. A claim's `item_id` is 64 hexadecimal digits and a passage's is a UUID.
 * Everything is already scoped to the caller's role, capped and counted by the
 * server, and the page renders it as sent. Nothing is cached here either.
 *
 * @param {{type: string, id: string}|null} [selection] The selection, or null for the overview.
 * @param {object} [options]
 * @param {AbortSignal} [options.signal]
 * @returns {Promise<object>} The map object.
 */
export function fetchEvidenceMap(selection = null, options = {}) {
  const search = knowledgeMapQuery(selection)
  return get(search ? `${EVIDENCE_MAP_ROUTE}?${search}` : EVIDENCE_MAP_ROUTE, options)
}
