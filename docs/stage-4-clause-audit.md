# Stage 4 clause audit

Every clause of the requirements Stage 4 owns, ticked against what is in the repository.
Produced on 25 September 2026, at item 10, because **FR-12 had by then produced three
scope gaps in one stage** and a fourth found at Stage 5's set-level audit would be a
31 October problem rather than a September one.

This table is the input to item 12's `requirements-auditor` run and to Stage 5 item 6's
set-level audit. It is not a substitute for either: it is the author's own reading, and an
auditor reading the same clauses independently is the point of having one.

**How to read the states.** ✅ built and tested. ⚠️ partly built, with the shortfall named.
🔧 deliberately not built, with a numbered decision recording why. Every ⚠️ and 🔧 names
the decision or the stage that owns it — a clause with no state and no decision beside it
is the thing this document exists to prevent.

---

## FR-12 — Knowledge Search and Answer Generation (MUST)

Nineteen clauses, plus the database CRUD line.

### Front-End

| # | Clause | State | Where |
|---|---|---|---|
| 1 | Search field available from every page; results grouped by type (Documents and Meetings) with a count per group | ✅ | item 8a (endpoint), item 10 (field in the shell, grouped screen) |
| 2 | Each result shows its title, the matching passage as a snippet, its department, and its date | ✅ | item 8a, item 10 |
| 3 | A question field accepting natural language, returning a written answer with numbered inline citations | ✅ | item 9 (endpoint), item 10 (screen); numbering renders the server's `position`, never the array index |
| 4 | Each citation expands to display the source passage | ✅ | item 10; passages travel with the reply (D-44), so no second request |
| 5 | …**and links to the source document or meeting** | ✅ | item 10 for meetings; item 10b adds `GET /api/documents/{id}` and the document route (D-46) |
| 6 | A "Sources" panel lists every item consulted with its date | ✅ | item 9 (reply), item 10 (panel). "Consulted" is every supplied passage's source, not only the cited ones (D-44) |
| 7 | Every factual statement displayed carries a citation; no interface state shows an uncited factual statement | ✅ | items 6, 7, 10. Enforced by omission: the reply carries no rejected or unverified text, and no withheld affordance exists |
| 8 | Where nothing sufficiently relevant is retrieved, the interface states plainly it cannot answer and presents no speculative answer | ✅ | items 4, 7, 10 |
| 9 | …**any partially related items found are offered, clearly labelled as partial matches** | ✅ | item 10a. Derived from the top-ranked scoped candidates irrespective of the threshold, so it is identical on both no-answer paths; source identity and date only, never passage text |

### Server-End

| # | Clause | State | Where |
|---|---|---|---|
| 10 | Queries shorter than two characters rejected client-side | ✅ | item 8a (`MINIMUM_SEARCH_LENGTH`, enforced server-side too — the client check is usability, the server check is the rule) |
| 11 | Question length is capped | ✅ | item 4, in characters, both bounds inclusive |
| 12 | **Input is sanitised before use** | 🔧 | **D-45.** No stripping or escaping pass: SQL is parameterised, render is escaped by React, length is capped, and prompt content is constrained by grounding plus citation verification. The one case where the argument does not hold — a question containing the prompt's own `[chunk_id: …]` delimiter — is neutralised and tested |
| 13 | Retrieval executes only over chunks whose recorded model version matches the current query model | ✅ | item 2; excluded from the candidate set entirely, not ranked lower (risk R10) |
| 14 | Retrieved context truncated to fit the window, discarding the lowest-ranked passages first | ✅ | item 5; exits on the first passage that will not fit, per 7.10 lines 96-103 |
| 15 | Scoping: results restricted by FR-11 **before** ranking, not by filtering a ranked list afterwards | ✅ | item 1; a predicate on the query, asserted against the compiled SQL |
| 16 | Ranking: query vectorised with the recorded model; cosine over stored vectors; highest-scoring in rank order; below-threshold excluded; similarity computed in the application | ✅ | items 2, 3. The proposal contradicts itself on where ranking happens; item 3's docstring records which clause governs and concedes the scaling objection |
| 17 | Grounding: the prompt contains only the retrieved passages, each with its chunk identifier, constraining the model to answer solely from them | ✅ | item 5. FR-13's prior-questions block is the one addition, declared in the prompt as non-citable and recorded in D-42 |
| 18 | Structured output: discrete statements, each tagged with its passage identifier, not free prose | ✅ | item 5, `STATEMENT_LIST_SCHEMA` |
| 19 | Deterministic verification: each returned identifier checked against the supplied set; absent, unrecognised or fabricated statements removed; the check is application code | ✅ | item 6. Invariant 5's limitation — it cannot judge whether a passage supports a statement — is conceded, and item 9a observed it with three real examples |
| 20 | No answer: path A returns without invoking generation; path B returns the same response; the two cases are recorded separately | ✅ | items 4, 7, 8. One reply, two reasons; `rejected_count` separates path B's two kinds |
| 21 | Gap evidence: every query logged with its result count and answered status | ✅ | item 8. The count is `len(retrieved_chunk_ids)`, derived rather than stored, argued in `query_log.py` |
| 22 | Traceability: the question, the retrieved chunk identifiers, the answer and its verified citations are logged | ✅ | item 8 |
| 23 | Responses: 200 with grouped results; 200 with answer and citations; 200 with `answered: false`; 503 where the AI service cannot be reached after retries | ✅ | items 8a, 9 |

### Database

| Clause | State | Where |
|---|---|---|
| ContentChunks, Documents, Meetings (Read); SearchLogs, QueryLog, AnswerCitations (Create) | ✅ | items 8, 8a. `SearchLog` was an unwritten table from migration v1 until item 8a — its emptiness was the visible symptom of gap 9 above |

---

## FR-11 — Permission-Aware Retrieval Scoping (MUST)

| Clause | State | Where |
|---|---|---|
| No dedicated interface; two users asking the same question may receive different results, and the interface gives no indication that withheld content exists | ✅ | items 1, 8a, 10. The search endpoint tells two roles different counts for one term by design |
| Builds a permission filter from the requesting role before retrieval and applies it as a condition on the query rather than to the returned results | ✅ | item 1, asserted against the compiled SQL — the assertion a post-filter would fail while passing every other test in the file |
| Validation: an invalid session is rejected before any retrieval occurs | ✅ | Stage 2's global `IsAuthenticated`, plus `UnscopedRequestError` as an uncaught backstop |
| Validation: where the scope resolves to no accessible content, FR-12's no-answer response is returned rather than an error disclosing that restricted material exists | ✅ | item 4; an empty candidate set and an all-below-threshold set are indistinguishable in the reply |
| Filtering at retrieval, not at generation | ✅ | item 1. Out-of-scope material reaches no prompt: 0 occurrences across every harness run |
| Result counts computed after filtering | ✅ | items 1, 7, 8a. Search counts are properties over post-filter rows; a no-answer reply counts 0 on both paths |
| Database: Roles, RolePermissions, Documents (Read) | ✅ | Stage 2 seeds, item 1 reads |

---

## FR-13 — Conversational Knowledge Assistant (MUST)

| Clause | State | Where |
|---|---|---|
| A conversational interface reachable from any page, retaining the thread so follow-ups need not restate the subject | ⚠️ | items 9, 10. Holds for subject nouns; a follow-up referring into the previous **answer** does not resolve, because prior answers are never passed (D-42, conceded) |
| Previous conversations listed and reopenable; the active thread can be cleared to begin a new topic | ⚠️ | items 9, 10. Listed, reopened and cleared — but a reopened thread cannot expand its citations, because `GET /api/conversations/{id}` carries statements without sources or passage text. The thread says so once rather than rendering dead controls. Owner: Stage 5 |
| Maintains conversation context per session and passes prior turns alongside the new question | ✅ | item 9, as prior questions only (D-42) |
| Validation: context truncated to a maximum number of prior turns | ✅ | item 9, `MAXIMUM_CONVERSATION_TURNS = 3` |
| Validation: FR-11's scope re-evaluated on every turn rather than cached from the first | ✅ | item 9. Structural — the scope is re-resolved per call — and tested by demoting a role between two turns of one thread on one session cookie |
| Business logic: each turn triggers a fresh retrieval on the resolved question, not the previous turn's passages | ✅ | item 9 |
| Business logic: answer generation and citation verification follow FR-12 unchanged | ✅ | item 9. The prompt gains the history block; nothing else changes |
| Responses: 200 with the answer and updated conversation state | ✅ | item 9 |
| Database: Conversations (Create, Read, Update); QueryLog (Create) | ⚠️ | item 9. Create and Read have routes; **Update has no mutating verb** — the two updates are the title derivation and `last_updated_at`, both server-side, because FR-13's interface has no rename control (D-43). An auditor reading `Update` as requiring a `PATCH` will flag this; the argument rather than the route is the answer |

---

## What is measured, and what is not

Not a clause audit, but the same kind of honesty and the auditor will want it.

| | |
|---|---|
| Schema conformance, fabrication, no-answer rates | Measured on the shipped pipeline — `docs/flm-baseline.md`, item 6 |
| FR-13's history block's effect on generation | Measured — item 9a, retrieval held constant. First-attempt conformance unmoved |
| **FR-13 end to end** | **Unmeasured.** Item 9a deliberately held retrieval constant, so the composed join FR-13 embeds — which changes which passages are retrieved — is untested. On D-40's evidence that is the half likelier to move answers |
| **Retrieval stability at the threshold** | **Open — D-40.** Query embeddings wander by ~1e-4; about 6% of admitted passages sit within 0.005 of the floor; two questions swapped answers across three identical runs. `check_flm.py`'s 0.999 tolerance is four orders of magnitude too coarse to see it |
| **Latency** | **No baseline.** No earlier run recorded timings, so Objective 03's p90 on 23 October has nothing to compare against. Item 9a measured p90 8.90 s over 50 attempts |
| **The front end** | **No test runner at all** (D-25, audit finding 8, open across two stages). Items 10 and 10a are verified by `npm run build`, oxlint, live API calls and a one-off server-render harness. None of it is a regression test |
