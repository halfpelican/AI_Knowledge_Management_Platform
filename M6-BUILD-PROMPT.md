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
| Objective 02 — ingestion verification | due **2 October** · corpus not yet assembled |
| Objective 03 — search verification | due **23 October** · p90 measured at 8.90s against a 4-second target |
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

```
Stage 5: presentation, integration and the alpha. Milestone M6.

Before item 2, enumerate FR-14's and FR-15's clauses exhaustively and tick each
against what exists — every MUST, every front-end line. That method is what found
FR-12's scope gaps in Stage 4, and it found most of them after the code was believed
finished. docs/stage-4-clause-audit.md is the worked example.

Decide the deployment topology before item 2, not at item 9. No deployment exists and
FLM runs on one laptop's NPU, so a deployed alpha means either that laptop is the host
or a switch to anthropic. A switch is a full re-index; a re-index destroys the FR-12
audit trail until item 1a lands; and D-40 forbids re-indexing between building the
demonstration threads and demonstrating them. Deciding this in the last week makes
item 1a too late to help.

1. Shared scoping helpers: scoped_documents() and scoped_meetings(), alongside the
   existing chunk predicate. The FR-11 predicate is hand-written at each of these
   sites: apps/api/views.py:501, :652, :751, :843, :867;
   apps/retrieval/scoping.py:112; apps/retrieval/search.py:458, :465. The ones in
   views.py read the role directly rather than through permission_scope. FR-15's
   browse and download routes add more callers. This lands FIRST, because after
   FR-15 and FR-14 are written it is a refactor rather than a helper. It also closes
   D-61's gap 10: apps/api/answers.py:261-280 fails OPEN where
   apps/retrieval/search.py:456-469 fails closed, and one helper is how the two stop
   being able to disagree.

1a. AnswerCitation.chunk is on_delete=CASCADE (apps/retrieval/models.py:114-116), so
   a reprocess or a reindex destroys the FR-12 audit trail. D-61's gap 5, D-48,
   pinned by apps/api/tests/test_fr12_traceability_lost_on_reprocess.py. It is not
   an administrator-only path: apps/api/views.py:863 requires only
   contribute_content and :870 blocks only documents already Indexed, so a partially
   indexed document with cited chunks can be reprocessed by an Employee.
   manage.py reindex does the same. Migrate to SET_NULL and store a chunk_uuid and a
   passage-text snapshot on AnswerCitation, so a citation outlives its chunk.

   THIS LANDS BEFORE ANY RE-INDEX. Item 6 re-measures against Objective 02's corpus,
   which means indexing it. A provider switch is a mandated re-index (CLAUDE.md §4).
   D-40 forbids one before the demonstration. If the migration is later than the
   first of those, the trail is already gone and no migration brings it back.

2. FR-15 document repository and filtered browsing — metadata, filtering,
   permissioned deletion, browsing by tag or category without composing a search
   query. The detail view shows metadata and a download link; it does not show
   extracted content (see the decision recorded for that cut). Scope depth to
   what the time allows: fewer filter dimensions is an acceptable cut, the
   requirement missing is not.

2a. The document download route. D-18 deferred the Documents storage path to
   migration v2 and that has to be settled first, so this is schema-adjacent and
   not a button. It is another route through the permission boundary and the
   first that returns the ORIGINAL BYTES rather than derived content: scope it
   through item 1's helper, 404 rather than 403 outside scope (D-46's precedent),
   Content-Disposition: attachment, and content type from the stored signature
   rather than the uploaded name (D-15's principle, applied on the way out).
   Note in the decision that retrieval scopes at the chunk level while a download
   can only consult the document's stamp — those agree only while the visibility
   cascade holds.

3. FR-14 dashboard — recent documents, meetings and queries, scoped to the
   requesting user. "Scoped to the requesting user" is role scoping, not
   attendance scoping: D-16 forbids the second, and invariant 3's verdict is an
   absence proof that FR-14 is the most likely thing to break.

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
   owns its behaviour, in the same commit as the code. Items 4a and 4b are the two
   that change behaviour rather than only adding evidence.

4a. FR-13's "retaining the thread", with FR-12's citation link. D-61's gap 3: the one
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

4b. FR-12's citation expansion, source link and Sources panel on a REOPENED turn.
   D-61's gap 4. GET /api/conversations/{id} returns statements with no passages and
   no sources (apps/api/serializers.py:744-755), and frontend/src/utils/turns.js
   savedTurnFrom sets sources: [] and expandable: false. Live replies are correct;
   reopened ones are inert. Return each surviving citation's passage text and its
   source title and date from the same permitted_citation_chunk_ids result
   (apps/api/serializers.py:550-566), so it is re-scoped on read rather than trusted.
   This is a response-contract change: record the decision before writing the
   serializer, and state in it that a citation whose chunk is gone is item 1a's case,
   not an error.

5. Stage 4's deferred fixes: the throttle scope on /api/ask and the ingestion
   POSTs (deferred with its evidence — worst case is one request holding a worker
   ~900s); PDF decompression bombs, which D-50 left open because it closes the
   OOXML path only; orphaned empty conversations, which outlive the session that
   created them (D-58, D-61's gap 12); and — done on 27 September, not carried
   forward — D-51's retry affordance, which the front end withdrew in the Stage 4
   finishing pass (item 2).

6. Re-measurement, once Objective 02's corpus exists. Everything here is
   currently fitted to six chunks: RELEVANCE_THRESHOLD (D-37, provisional by its
   own terms, and D-38's trigger has already fired), the partial-matches
   relevance floor, the three citation rates, p90, and FR-13 end to end — which
   item 9a deliberately did not measure, because it held retrieval constant so
   the history block's effect would be attributable. Do not re-measure before the
   corpus lands; doing it twice is the only way to get it wrong twice.

7. Accessibility pass: contrast ratios documented, focus states, tab order, text
   equivalents for non-text content, component sheet complete. docs/usability-
   findings.md records the findings from hand-testing Stage 3 — close them here.
   Note that jsdom applies no stylesheet, so nothing in item 4's suite catches a CSS
   rule that hides an element; the acknowledgement line is the known case.

8. End-to-end integration pass across all twelve MUST-HAVEs. Both roles, real
   files, the real corpus.

9. Alpha deployment and a demonstration script that exercises all twelve in
   order. The script carries two conditions from D-40, not just the decision:
   screen every demonstration question for top-score margin, because about 6% of
   admitted passages sit within 0.005 of the threshold and two questions swapped
   answers across three identical runs; and DO NOT RE-INDEX OR REPROCESS between
   building the demonstration threads and demonstrating them. Make the D-35
   screen recording before any re-index, not after.

10. requirements-auditor: full set-level audit against the M6 gate list. Not
   requirement by requirement — the SET. Every one of the twelve owned,
   implemented, tested, nothing duplicated, nothing in the wrong layer, nothing
   satisfied only in the UI. Tell it to assume a claim in docs/decisions.md is
   true where it was written and false where it is used, and to hunt for one.
   Finding none is a legitimate verdict; a manufactured finding is not.

11. security-reviewer: final pass. Walk every model field mechanically and ask
   whether it stores content, an identifier or a count derived from a scoped
   query, and whether anything re-derives it on read. The known instances are
   ContentChunk, a reopened thread, QueryLog.answer_text, SearchLog.result_count and
   AnswerCitations. Hunt the pattern, not the list.
```

**Commit points** — one per numbered item, the lettered ones included. Do not merge
two items into one commit to save a round trip.

**Done when the auditor's set-level verdict is COMPLETE.** Not before, and not on
anyone's assurance that it is basically there.

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
- [ ] p90 response time, against NFR-08's 4 seconds, reported as a local-model
      baseline per `docs/ai-provider.md` §7
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
