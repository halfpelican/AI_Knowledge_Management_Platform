# M6 build prompt

Stage 5 only. Stages 0 to 4 are complete; their briefs are in this file's history
and their outcomes in `docs/decisions.md`. Work the stage **one numbered item at a
time**, committing at each. Pasting the whole stage at once produces a
plausible-looking skeleton with nothing working underneath it, which is the failure
mode this document exists to prevent.

---

## Where things stand

| | |
|---|---|
| Today | 28 September 2026 |
| Built | FR-01, 02, 04, 05, 06, 08, 09, 11, 12, 13. FR-14 and FR-15 remain |
| Stage 4 | Closed 28 September at `0f49608` (PR #19). The closing audit returned INCOMPLETE and is recorded verbatim as D-61 |
| Stage 4's open items | `docs/stage-4-open-items.md` — the index. Every item there names the record that holds it, and that holder wins if the two disagree |
| Objective 02 — ingestion verification | due **2 October** · corpus not yet assembled. The proposal fixes it: twenty documents across PDF, DOCX, XLSX and TXT, five pasted transcripts, five malformed or oversized files — see item 6 |
| Objective 03 — search verification | due **23 October** · thirty questions with known answers; p90 by load test against 4 seconds. The 8.90s baseline is one user, sequential, on the six-chunk corpus |
| Proposal milestone M5 | **23 October** · "FR-11 to FR-14" — FR-14 is due here, FR-15 at M6. Hence item 3 before item 2 |
| Stage 5 | target Saturday 31 October |
| M6 — mandatory gate | **Sunday 1 November** |

Stage 5 carries what Stage 4 deferred, and that list is longer than the two remaining
requirements: the `/api/ask` throttle, PDF decompression bombs, FR-13's end-to-end
measurement, D-40's demonstration mitigation, and every measurement currently fitted to
a six-chunk corpus. The front-end test decision is no longer on it — item 4 was taken
first and landed (D-62).

It also carries the gaps D-61's table marks "no Stage 5 item", which was a finding
against this file. They are items 1a, 4a, 4b and a bullet of item 5 below. Until that
edit they had no owner anywhere, which is how the lost-thread defect reached a closing
audit without appearing in the repository at all. None of this appeared in Stage 4's
brief either, which is why it is written down here rather than discovered at the
integration pass.

---

## Rules for every session

Give these to Claude Code once at the start of each session, or rely on `CLAUDE.md`
being read — but state them again when starting a new item.

```
Read CLAUDE.md and docs/ai-provider.md before your first edit.

Rules for this session:
- Build only what the item asks for. Do not scaffold ahead.
- Use the subagents in .claude/agents/. Each is scoped to a slice and carries the
  invariants for that slice. A bounded single-slice item you already hold the
  context for may be done directly — say in your report that you did it that way.
  A rule broken quietly is worse than a rule scoped honestly.
- Commit at every numbered commit point. Do not batch commits to the end.
- Every commit SUBJECT carries the FR ID or IDs the work touches. That is what
  CLAUDE.md §7 asks for and what §8 condition 4 is graded on. The item number and
  the D-number go in the body, not instead of the FR ID. This instruction used to
  read "cites its item number or its D-number", and that wording produced the §7
  breaches D-59 records and three more in Stage 5 item 4. If an item truly touches
  no requirement, say so in the body.
- If a decision is not settled in docs/decisions.md, stop and ask. Do not pick
  silently.
- A decision that claims coverage names what it does not cover.
- Tests land in the same commit as the code they test.
- A clause only the interface can satisfy is tested in the front-end suite
  (frontend/tests/, npm test) in that same commit — CLAUDE.md §8 condition 2, D-62.
  Mock at fetch through tests/fakeApi.js. tests/setup.js fails any test that reaches
  the network, and is not to be loosened.
- A route added or a response shape changed updates docs/api-contract.md in the same
  commit. The front end builds against that file, not against the serializer.
- Branch by the primary requirement: feat/FR-15-document-repository,
  fix/FR-12-citation-cascade. An item-numbered branch breaks CLAUDE.md §7 — D-61's
  gap 14, repeated by item 4's branch.
- Report repository state from git log and git status, not from memory. A
  subagent's report is scoped to that subagent: "nothing committed" means it
  committed nothing, not that the branch is empty.
- When you finish an item, say what is open as plainly as what is done.
- When you finish the stage, run the requirements-auditor and report its verdict
  verbatim. Do not summarise it favourably.
```

---

# Stage 5 — Presentation, integration and alpha

**Target: Saturday 31 October · milestone M6 · FR-14, FR-15, and Stage 4's
carry-forwards**

> **Amended 5 October 2026, so the plan in the repository is the plan that ran.** Stage 5
> was first written without the named agents that Stages 1 to 4 carried. The block below
> now names them: a routing paragraph after the order, and an owner on each item. Item 9a,
> a test-engineer step committed on its own before the audits, is new. Three questions this
> brief left open were settled before item 3, as D-64 (hosting), D-65 (D-54's query
> parameters) and D-66 (Administrator generalises Employee in scope). Each is noted where
> the brief raises it. The owners of items 1a, 4a, 4b, 5, 6 and 8 were not named in the
> amendment; they are assigned here from each agent file's stated scope.

```
Stage 5: presentation, integration and the alpha. Milestone M6.

Order: item 1, item 1a, then item 3 before item 2. The proposal's milestone M5
(23 October) includes FR-14; FR-15 is due at M6. Item 1a precedes item 2 because
FR-15's deletion destroys citations by design.

Agents. Use django-backend for the FR-14 and FR-15 endpoints (items 2, 2a and 3) and
the alpha deployment settings (item 9); react-frontend for their screens (items 2 and
3) and the accessibility pass (item 7); then test-engineer (item 9a, committed on its
own); then requirements-auditor (item 10) and security-reviewer (item 11). Anything
already built is not redone: its owning agent reviews it against its agent file and
fixes what it finds. Each item below names its agent.

Before either requirement's first line of code, enumerate FR-14's and FR-15's clauses
exhaustively and tick each against what exists — every MUST, every front-end line.
That method is what found FR-12's scope gaps in Stage 4, and it found most of them
after the code was believed finished. docs/stage-4-clause-audit.md is the worked
example. Items 2 and 3 quote each requirement's clauses, so the enumeration starts
from the proposal rather than from a summary of it.

Decide how the alpha is hosted before item 3, not at item 9. The project has no budget
for the anthropic provider, so the alpha runs on flm, and FLM runs only on the NPU
laptop: that laptop is the host. A provider switch is not an option, and nothing
below should be planned around one. What remains open is how an assessor reaches the
laptop — the same network, a tunnel, or the laptop itself — and that answer sets
HTTPS, ALLOWED_HOSTS and CSRF_TRUSTED_ORIGINS for item 9. Record it as a decision.
DECIDED 5 October, D-64: the laptop itself, over loopback, in production mode
(DEBUG=False, the built SPA, Waitress), with ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS and
the Secure cookie flags env-driven and defaulting to the loopback values. Scoped to
the M6 alpha; M8 hosting is a later decision, and NFR-03's TLS scan moves to NFR
round 2.

1. Shared scoping helpers: scoped_documents() and scoped_meetings(), alongside the
   existing chunk predicate. The FR-11 predicate is hand-written at each of these
   sites: apps/api/views.py:501, :652, :751, :843, :867;
   apps/retrieval/scoping.py:112; apps/retrieval/search.py:458, :465. The ones in
   views.py read the role directly rather than through permission_scope. FR-14's
   aggregation and FR-15's list, browse, detail and download routes add more
   callers. This lands FIRST, because after FR-15 and FR-14 are written it is a
   refactor rather than a helper. It also closes D-61's gap 10 (D-53):
   apps/api/answers.py:261-280 fails OPEN where apps/retrieval/search.py:456-469
   fails closed, and one helper is how they stop being able to disagree.

   Settle D-54 here as well. It is open, and it comes due with the first filter
   either requirement adds: every query parameter read off request.query_params into
   an ORM lookup reopens the NUL-byte 500 that Stage 4 closed inside search() only,
   and under DEBUG=True that page carries the traceback and the requester's session
   cookie. FR-14's date range and department, and FR-15's department, tag, status,
   sort and text filter, are all such parameters. Decide between a shared
   query-parameter reader and a serializer field for every parameter before either
   requirement writes its first filter.

   DONE 5 October, 1d06d0e, by the coordinating session directly rather than through
   an agent: it spans rag-pipeline's apps/retrieval and django-backend's apps/api, and
   the session held the context for both. D-54 is settled as D-65 (a DRF serializer
   for every query parameter). Followed by D-66 in the same helpers and nowhere else:
   Administrator generalises Employee in scope as well as in permissions, so that an
   Employee-only document is in an Administrator's scope and FR-15's scoped-first
   deletion can reach it.

1a. rag-pipeline: the model, the migration, the citation write in query_log, and the
   reopened-turn citation filter (FR-12's traceability clause).
   AnswerCitation.chunk is on_delete=CASCADE (apps/retrieval/models.py:114-116), so
   deleting a chunk deletes the citations that point at it, and the FR-12 audit trail
   with them. D-61's gap 5, D-48, pinned by
   apps/api/tests/test_fr12_traceability_lost_on_reprocess.py. Chunks are deleted by
   reprocess — apps/api/views.py:863 requires only contribute_content and :870
   blocks only documents already Indexed, so an Employee can reach it — by
   manage.py reindex, and, from item 2, by FR-15's document deletion. Adding
   documents deletes nothing, so ingesting Objective 02's corpus is not one of them.

   Migrate to on_delete=SET_NULL with null=True, and add a chunk_uuid column holding
   the chunk's identifier, backfilled for existing rows in the same reversible
   migration (RunPython with a reverse). That is what FR-12's traceability clause
   asks for: the question, the chunk ids and the verified citations survive, so an
   answer can still be traced after its source is gone.

   Do NOT store passage text on AnswerCitation. D-61 suggested a snapshot, but FR-15
   says deleting a document removes its extracted content, embeddings and tag links
   "so that deleted material cannot subsequently be surfaced through search" — and a
   snapshot is that material surviving the delete. With item 4b returning passage
   text for reopened turns, it would put deleted text back on screen. A citation
   whose chunk is null is REMOVED for every reader: the reopened-turn serializer,
   4b's expansion, the Sources panel, and invariant 6, which then hides a statement
   left with no surviving citation. Today CASCADE produces that outcome by accident.
   After 1a it has to be produced on purpose, and tested.

   Order: before item 2, and before the demonstration threads are built. After
   either, the citations that matter are exposed to a delete, and no migration
   brings a deleted row back.

2. FR-15 document repository and filtered browsing: django-backend for the endpoints,
   react-frontend for the screens. The clause, to be ticked line by line:
   - a list view showing title, type, uploader, upload date and status, with
     sorting and a text filter;
   - browsing by Department, Project, Process or Topic without composing a query;
     filters combine, with an item count against each available value;
   - a detail view showing metadata, extracted content and a download link — D-63
     restores the extracted content D-52 cut;
   - deletion that asks for confirmation, offered only to a user holding
     manage_documents;
   - 200 for a list or a detail, 204 for a filter combination with no accessible
     matches, 403 without permission, 404 for an unknown document.

   Deletion is where this item is most likely to go wrong. ContentChunk.source_id and
   ContentTag.source_id have no database foreign key — D-07: integrity and cascade
   deletion are application code — so document.delete() removes the document and its
   ExtractedContent and LEAVES ITS CHUNKS embedded, stamped and retrievable. The
   deleted document keeps answering questions. Delete the chunks (by source_type and
   source_id), the ContentTags and the document in one transaction (invariant 9), and
   remove the stored file in transaction.on_commit so a rolled-back delete keeps it.
   Test what FR-15 promises: after the delete, a phrase known to be in the document
   returns nothing from /api/search, and a question only it answered takes no-answer
   path A. Resolve the document through the scoped helper first — 404 outside scope,
   D-46 — and check manage_documents second, 403. In the other order the status code
   tells a user whether a document they cannot see exists. manage_documents is
   seeded Administrator-only by accounts 0005 (settled 5 October). D-66 puts every
   Employee-only document in an Administrator's scope, so no document is undeletable.

   The values a filter offers, and the count against each, come from the documents
   the user may see — never from the Tags table. A tag or department that exists only
   on restricted documents discloses them by being offered at all (invariant 1).

   Browse will demonstrate empty unless something writes ContentTags, and nothing
   does: AI tagging is FR-10 and Objective 05, due 13 November. Seed tags on the
   demonstration corpus with applied_by="user", and record the decision.

   Keep the filter state in the URL query string. A detail view opened from a
   filtered list and left with Back must land on the same filters — gap 3's defect,
   waiting in a new screen.

   Extracted content (D-63) is read from ExtractedContent.extracted_text through the
   same scoped lookup as the detail view, never reassembled from chunks, and rendered
   as text, never as HTML. A document with no ExtractedContent row shows a stated
   empty state, keyed on the row existing rather than on the status.

   Front-end tests, for the clauses only the interface can satisfy: the empty state
   for a 204, the delete confirmation, no delete control without manage_documents,
   filters surviving a round trip through a detail view, and extracted content
   rendered as text. Fewer filter dimensions is an acceptable cut; the requirement
   missing is not.

2a. django-backend. The document download route — FR-15's download link, and not
   built: D-52 said
   it was, and it never existed. The storage is settled: Document.file_path has been a
   FileField under MEDIA_ROOT since documents 0006 (docs/schema-v1.md, G7, closed 21
   September), so this is a view, not a migration. It is another route through the
   permission boundary and the first that returns the ORIGINAL BYTES rather than
   derived content: scope it through item 1's helper, answer 404 rather than 403
   outside scope (D-46's precedent), and respond with FileResponse(as_attachment=True,
   filename=...) rather than a hand-built Content-Disposition header, taking the
   content type from the stored signature rather than the uploaded name (D-15's
   principle, applied on the way out). The link points at this view, never at
   file_path.url: that is /media/<path> with the original filename in it, and
   config/urls.py deliberately serves nothing outside /api/. Do not add
   static(MEDIA_URL) to make such a link work — it would serve every document to
   anyone who has its path. Note in the decision that retrieval scopes at the chunk
   level while a download can only consult the document's stamp — those agree only
   while the visibility cascade holds.

3. FR-14 dashboard — taken before item 2 (see the order above): django-backend for
   the endpoint, react-frontend for the screen. The clause, to be ticked line by line:
   - the landing page after login, with panels for recent documents, recent
     meetings, total indexed items and recent questions asked;
   - each panel links through to its full view and shows a loading state;
   - filterable by date range and by team or department;
   - ONE endpoint aggregates the counts and recent items in a single request, not a
     call per panel;
   - counts computed after permission filtering, as in FR-11, so a total never
     reveals inaccessible content;
   - 200 with a summary payload, 401 for an invalid session.

   Documents, meetings and totals are role-scoped through item 1's helpers.
   "Scoped to the requesting user" is role scoping, not attendance scoping, for
   those: D-16 forbids attendance scoping, and invariant 3's verdict is an absence proof
   that FR-14 is the most likely thing to break. Recent QUESTIONS are different.
   Show the requesting user's own QueryLog rows, and the question only: role scoping
   would show one user's questions to another, and QueryLog.answer_text is derived
   from sources that may since have left the reader's scope (item 11's known
   instance). Record the reading as a decision.

   The department filter offers only departments present on content the user may
   see, as item 2's filters do.

   Replace the landing route for EACH role. Login sends an Administrator to /admin
   and an Employee to /dashboard (DASHBOARD_PATHS in frontend/src/constants.js), and
   each renders the <Home /> placeholder today (frontend/src/App.jsx). Whichever role an
   assessor signs in as first has to land on the dashboard.

   FR-14's database clause reads KnowledgeGaps, a table deferred to NIT3004 with
   FR-19 and Objective 06, due 13 November (docs/schema-v1.md §2). Record that as a
   decision before the auditor records it as a gap.

4. DONE, 28 September, D-62 — taken first, out of order. Vitest 5.0.2, Testing
   Library 16.3.3 and jsdom 30.1.1 in frontend/vite.config.js, a frontend job in
   .github/workflows/ci.yml, the named tests in frontend/tests/, and CLAUDE.md §8
   condition 2 rewritten to require both pytest and the front-end suite — and to
   require that a clause only the interface can satisfy is tested in the front-end
   suite, where an API test and hand-testing do not stand in for it. Do not redo
   this item. Do not extend the suite as an end in itself.

   What it leaves: the amended condition 2 raises the bar, so MORE of FR-12 and
   FR-13 now fail it than before. D-62 lists the front-end clauses with no test.
   That list is not a work item of its own — each clause is tested by whichever item
   owns its behaviour, in the same commit as the code. Items 4a and 4b change
   behaviour rather than only adding evidence.

4a. react-frontend. FR-13's "retaining the thread", with FR-12's citation link.
   D-61's gap 3: the one
   finding the closing audit recorded that existed nowhere in the repository, and the
   one on the path an assessor walks. frontend/src/pages/Ask.jsx:129-130 holds
   conversationId and turns in useState only, and the citation's own
   "View document/meeting" link (frontend/src/components/Answer.jsx:54-58) is a
   same-tab <Link>, so following it unmounts the Ask screen and Back returns an empty
   conversation. The only way back is to reopen the thread from the list, and then
   its citations are inert, which is 4b. Put the active thread in the URL
   (/ask?c=<id>) and call fetchConversation on mount; opening source links in a new
   tab is a stopgap, not the fix. About a day of front-end work. Its test lands in
   the same commit and in the front-end suite, because only the interface can satisfy
   the clause.

4b. django-backend for the contract and the serializer, then react-frontend for the
   reopened turn. FR-12's citation expansion, source link and Sources panel on a
   REOPENED turn.
   D-61's gap 4. GET /api/conversations/{id} returns statements with no passages and
   no sources (apps/api/serializers.py:744-755), and frontend/src/utils/turns.js
   savedTurnFrom sets sources: [] and expandable: false. Live replies are correct;
   reopened ones are inert. Return each surviving citation's passage text and its
   source title and date from the same permitted_citation_chunk_ids result
   (apps/api/serializers.py:550-566), so it is re-scoped on read rather than trusted.
   This is a response-contract change: record the decision and update
   docs/api-contract.md before writing the serializer. A citation whose chunk is null
   after item 1a is REMOVED, not expanded: no passage text is returned for it from
   anywhere, because FR-15's deletion promises that deleted material is not surfaced
   again. That case renders the provenance-removed state, which D-62 records as
   untested — test it here, in the front-end suite.

5. django-backend for the throttle and the orphaned conversations, rag-pipeline for
   the PDF bomb. Stage 4's deferred fixes: the throttle scope on /api/ask and the
   ingestion
   POSTs (deferred with its evidence — worst case is one request holding a worker
   ~900s); PDF decompression bombs, which D-50 left open because it closes the
   OOXML path only; orphaned empty conversations, which outlive the session that
   created them (D-58, D-61's gap 12); and — done on 27 September, not carried
   forward — D-51's retry affordance, which the front end withdrew in the Stage 4
   finishing pass (item 2).

6. rag-pipeline. Re-measurement, once Objective 02's corpus exists. Everything here
   is
   currently fitted to six chunks: RELEVANCE_THRESHOLD (D-37, provisional by its
   own terms, and D-38's trigger has already fired), the partial-matches
   relevance floor, the three citation rates, p90, and FR-13 end to end — which
   Stage 4's item 9a deliberately did not measure, because it held retrieval
   constant so
   the history block's effect would be attributable. Do not re-measure before the
   corpus lands; doing it twice is the only way to get it wrong twice. Ingesting the
   corpus adds chunks and deletes none, so it is not a re-index and does not wait on
   item 1a.

   Objective 02 (2 October) specifies the corpus exactly: twenty documents across
   PDF, DOCX, XLSX and TXT, five pasted transcripts, and five malformed or oversized
   files. Every valid item must reach indexed status and return its own content when
   searched for a phrase known to be in it; every invalid item must be refused with
   its documented error rather than partly ingested; a document of twenty pages or
   fewer must finish processing within sixty seconds. Keep the phrase list with the
   corpus — it is the evidence.

   Objective 03 (23 October) measures p90 by LOAD-TESTING the query endpoint, and
   citation integrity over thirty questions with known answers. The 8.90s baseline
   is one user, sequential. Generation on a single NPU very likely queues concurrent
   requests, so a load test will read higher, not lower. The proposal fixes no
   concurrency: choose one, record it in the decision, and report p90 against it.

7. react-frontend. Accessibility pass: contrast ratios documented, focus states,
   tab order, text
   equivalents for non-text content, component sheet complete. docs/usability-
   findings.md records the findings from hand-testing Stage 3 — close them here.
   Note that jsdom applies no stylesheet, so nothing in item 4's suite catches a CSS
   rule that hides an element; the acknowledgement line is the known case.

8. test-engineer, with the coordinating session for the live run. End-to-end
   integration pass across all twelve MUST-HAVEs. Both roles, real
   files, the real corpus.

9. django-backend for the settings and the server, react-frontend for the production
   build. Alpha deployment and a demonstration script that exercises all twelve in
   order. None of the deployment exists, and the development setup does not carry
   over:
   - D-21's single origin is the Vite development proxy. A production build
     (frontend/dist) has no proxy, and nothing serves it. Keep one origin: the built
     SPA and /api from the same host — Django with a static-files layer and a
     catch-all for client routes that leaves /api/ answering its own JSON 404s, or a
     reverse proxy in front of the SPA and /api. Do not point VITE_API_BASE_URL at another
     origin: the session and CSRF cookies are SameSite=Lax, so login would appear to
     succeed and every call after it would fail.
   - requirements.txt has no production server, and gunicorn does not run on native
     Windows, which is where FLM and the NPU are. waitress does.
   - DEBUG=False; ALLOWED_HOSTS and CSRF_TRUSTED_ORIGINS for the chosen host;
     SESSION_COOKIE_SECURE and CSRF_COOKIE_SECURE if it is served over HTTPS.
   - If it is reachable beyond the laptop, registration (FR-01) is open to anyone
     with the address.
   The script carries D-40's conditions, not just the decision: screen every
   demonstration question for top-score margin, because about 6% of admitted
   passages sat within 0.005 of the threshold on the six-chunk corpus (re-read that
   figure after item 6) and two questions swapped answers across three identical
   runs; and DO NOT RE-INDEX, REPROCESS OR DELETE between building the
   demonstration threads and demonstrating them. Make the D-35 screen recording
   before any re-index, not after.

9a. test-engineer: FR-14 and FR-15 leakage tests, a test step committed on its own,
   before items 10 and 11. Not item 6, which stays re-measurement.
   - An Employee's dashboard totals and browse-facet counts are identical with and
     without Administrator-only documents in the database.
   - After a delete, a question whose only answer lived in that document returns
     no-answer, and none of its chunks remain.
   - An unknown department and a restricted-only one return the same 204 on FR-15's
     browse, and the same 200 payload on FR-14's dashboard, which lists no 204.
   - An Administrator can delete a document visible only to Employees (D-66).
   - The dual-role matrix stays at 100% with the new routes.

10. requirements-auditor: full set-level audit against the M6 gate list. Not
   requirement by requirement — the SET. Every one of the twelve owned,
   implemented, tested, nothing duplicated, nothing in the wrong layer, nothing
   satisfied only in the UI. Tell it to assume a claim in docs/decisions.md is
   true where it was written and false where it is used, and to hunt for one.
   Finding none is a legitimate verdict; a manufactured finding is not.

11. security-reviewer: final pass. Walk every model field mechanically and ask
   whether it stores content, an identifier or a count derived from a scoped
   query, and whether anything re-derives it on read. The known instances are
   ContentChunk, a reopened thread, QueryLog.answer_text, SearchLog.result_count,
   AnswerCitations, and ExtractedContent.extracted_text — a document's whole
   content, which the detail view now shows (D-63). Hunt the pattern, not the list.
   This pass reviews the deployed alpha, so the configuration it runs with is in
   scope: DEBUG, ALLOWED_HOSTS, the cookie flags, the single origin, and that nothing
   serves MEDIA_ROOT. The agent's own prompt says so for this pass.
```

**Commit points** — one per numbered item, the lettered ones included. Do not merge
two items into one commit to save a round trip.

**Done when the auditor's set-level verdict is COMPLETE, apart from D-60's accepted decline of
§8 condition 4 for FR-11, FR-12 and FR-13.** Not before, and not on anyone's assurance that it
is basically there.

---

## Gate checklist — 1 November

Twelve requirements, each demonstrable end-to-end on the deployed alpha:

- [ ] FR-01 registration
- [ ] FR-02 login
- [ ] FR-04 logout and session management
- [ ] FR-05 role management
- [ ] FR-06 RBAC enforced server-side on every protected route
- [ ] FR-08 document upload, extraction and indexing
- [ ] FR-09 meeting transcript ingestion
- [ ] FR-11 permission-aware retrieval scoping
- [ ] FR-12 knowledge search and answer generation with verified citations
- [ ] FR-13 conversational assistant, permission re-checked per turn
- [ ] FR-14 dashboard overview
- [ ] FR-15 document repository and filtered browsing

The numbers worth having ready when asked:

- [ ] Dual-role protected-endpoint coverage — and the honest caveat that the
      matrix count is a weaker statement than `CLAUDE.md` §8 asks for
- [ ] Citation schema conformance and first-attempt rate, from `docs/flm-baseline.md`
- [ ] Fabricated-identifier rate, and the fact that verification strips them
- [ ] p90 response time, against NFR-08's 4 seconds, measured by load test at a
      stated concurrency (Objective 03) and reported as a local-model baseline per
      `docs/ai-provider.md` §7
- [ ] Every audit run so far has found no route across the permission boundary — the
      trail is D-57 to D-61, and the closing audit walked /api/ask, /api/search,
      /api/conversations*, /api/documents/{id}, /api/meetings/{id} and reprocess

The answers worth having ready before they are asked:

- [ ] Can a citation point at a passage that does not support its statement? Yes —
      three times, measured, at item 9a. Invariant 5 concedes it by design.
- [ ] Does the same question always answer the same way? No — D-40, open and
      unidentified.
- [ ] What is not verified by any test? Since D-62 a named set of interface
      behaviours is, and D-62 lists what is still not — including every page except
      Ask. Give that list, not "the front end is tested".
- [ ] Where does the build fall short of a clause on purpose? D-45 (no input
      sanitiser; the defence is parameterised SQL, React escaping and the delimiter)
      and D-42 (prior questions are passed, not prior answers). Present each as a
      deviation with its reason — never as a tick.

---

## If you fall behind

Cut **depth inside a requirement**, never a requirement. Fewer filter dimensions on
FR-15. A leaner FR-14 dashboard. A plainer assistant UI. Twelve requirements working
simply beats eight working well, because the gate measures breadth.

Stop COULD-HAVE work entirely — FR-07, FR-17, FR-18, FR-19, FR-20 — and note that
dropping them does not move the M6 number, because they were never in it. The
protective value of that tier is spent *during* implementation by not starting it,
not afterwards by abandoning it.

Track completions against dated tasks, not hours worked. "Are we behind" should be
countable, and meeting minutes will not tell you that FR-12 is late.
