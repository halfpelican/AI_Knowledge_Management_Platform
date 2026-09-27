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
| Today | 27 September 2026 |
| Built | FR-01, 02, 04, 05, 06, 08, 09, 11, 12, 13 — ten of the twelve |
| Stage 4 | 23 commits; two independent audits returned INCOMPLETE; fixes in progress |
| Objective 02 — ingestion verification | due **2 October** · corpus not yet assembled |
| Objective 03 — search verification | due **23 October** · p90 measured at 8.90s against a 4-second target |
| Stage 5 | target Saturday 31 October |
| M6 — mandatory gate | **Sunday 1 November** |

FR-14 and FR-15 remain. Stage 5 also carries what Stage 4 deferred, and that list is
longer than the two requirements: the `/api/ask` throttle, PDF decompression bombs,
FR-13's end-to-end measurement, D-40's demonstration mitigation, the
affordance, the front-end test decision, and every measurement currently fitted to a
six-chunk corpus. None of those appeared in Stage 4's brief either, which is why they
are written down here rather than discovered at the integration pass.

---

## Rules for every session

Give these to Claude Code once at the start of each session, or rely on `CLAUDE.md`
being read — but state them again when starting a new item.

```
Read CLAUDE.md and docs/ai-provider.md before your first edit.

Rules for this session:
- Build only what the item asks for. Do not scaffold ahead.
- Use the subagents in .claude/agents/. Each is scoped to a slice and carries the
  invariants for that slice.
- Commit at every numbered commit point. Do not batch commits to the end. Every
  commit subject cites its item number or its D-number.
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
against what exists — every MUST, every front-end line. That method found four
gaps in FR-12 during Stage 4, three of them after the code was believed finished.

1. Shared scoping helpers: scoped_documents() and scoped_meetings(), alongside
   the existing chunk predicate. The FR-11 predicate currently exists in eight
   hand-written copies, five of which read the role directly rather than through
   permission_scope. FR-15 is the ninth caller. This lands FIRST, because after
   FR-15 and FR-14 are written it is a refactor rather than a helper.

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

4. The front-end test decision, made rather than deferred a fourth time. Either
   a runner lands here — Vitest, Testing Library, jsdom, and a small number of
   tests covering invariant 6, the no-answer state, the 503 notice and the two
   regressions Stage 4 introduced — or a numbered decision records that invariant
   6 is verified at the API boundary only and the interface is accepted as
   untested. Both are defensible. A fourth deferral is not. Eleven of Stage 4's
   clauses were front-end clauses with no automated evidence of any kind.

5. Stage 4's deferred fixes: the throttle scope on /api/ask and the ingestion
   POSTs (deferred with its evidence — worst case is one request holding a worker
   ~900s); PDF decompression bombs, which D-50 left open because it closes the
   OOXML path only; and — done on 27 September, not carried forward — D-51's retry
   affordance, which the front end withdrew in the Stage 4 finishing pass (item 2).

6. Re-measurement, once Objective 02's corpus exists. Everything here is
   currently fitted to six chunks: RELEVANCE_THRESHOLD (D-37, provisional by its
   own terms, and D-38's trigger has already fired), the partial-matches
   relevance floor, the three citation rates, p90, and FR-13 end to end — which
   item 9a deliberately did not measure, because it held retrieval constant so
   the history block's effect would be attributable. Do not re-measure before the
   corpus lands; doing it twice is the only way to get it wrong twice.

7. Accessibility pass: contrast ratios documented, focus states, tab order, text
   equivalents for non-text content, component sheet complete. docs/usability-
   findings.md records six findings from hand-testing Stage 3 — close them here.

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
   query, and whether anything re-derives it on read. Five instances are known
   (ContentChunk, a reopened thread, QueryLog.answer_text, SearchLog.result_count,
   AnswerCitations). Hunt the pattern, not the list.
```

**Commit points** — one per numbered item, twelve including 2a.

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
- [ ] Two independent security audits found no route across the permission boundary

The answers worth having ready before they are asked:

- [ ] Can a citation point at a passage that does not support its statement? Yes —
      three times, measured, at item 9a. Invariant 5 concedes it by design.
- [ ] Does the same question always answer the same way? No — D-40, open and
      unidentified.
- [ ] What is not verified by any test? The interface, unless item 4 changed that.

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
