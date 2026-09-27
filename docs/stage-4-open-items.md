# Stage 4 open items

Everything Stage 4 leaves open, in one place, as at `0f49608` — the merge that closed
the stage on 28 September 2026. Closures and owners added later the same day are dated
in place rather than deleted, so the file reads as a record and not only as a snapshot.

**This file is an index, not a source of truth.** Every item below is held by a decision
record, an audit verdict or a path in the tree, and that holder is named on the item. If
this file and the holder disagree, the holder wins and this file is wrong. It exists
because the closing audit's verdict (D-61) is written as a verdict — it answers "is
Stage 4 done" — and nobody can work from it. `M6-BUILD-PROMPT.md` is the brief for the
next stage and carries only what Stage 5 was scoped to do. Neither is a list of what is
open, and the gap between them is where the items in section 2 were sitting.

Per the coverage rule in `docs/decisions.md`, every item names its owner or names that it
has none, and section 9 says what this file does not cover. Items are named, never
counted: a count here would go stale the first time one closed.

---

## 1. Status at the closing commit

| | |
|---|---|
| Stage 4 requirements | FR-11, FR-12, FR-13 |
| Closing audit | `requirements-auditor` at `2ba4de9`, verdict **INCOMPLETE**, recorded verbatim in D-61 |
| §8 done | **No**, for all three |
| §8 condition 4 | **Declined**, not failed — D-60. The commits are on `main`; it cannot be fixed |
| §8 condition 5 | **Fails** — the audit reports gaps. It stands until an audit returns clean |
| M6-demonstrable | **Yes, locally**, for all three. No deployed alpha exists |
| Permission boundary | Invariant 1 passes over every route the audit walked. This is the strongest part of the stage |

The distinction in rows three and four is deliberate and is the wording used in PR #19:
a declined condition is a decision with a reason, a failed condition is an outcome. They
are not reported as the same thing.

---

## 2. Carried into Stage 5 by name

These are the rows D-61's table marks **no Stage 5 item**, which was a finding against
`M6-BUILD-PROMPT.md` rather than against the code. **Discharged 28 September:** that file
now carries them as items 1a, 4a, 4b and a bullet of item 5, and each subsection below
names its owner. They stay in this file because this is the index; the brief is where
work is scheduled. Unowned, they would have surfaced at Stage 5 item 10 — the set-level
audit — three days before the gate.

### 2.1 The active thread is lost on any navigation, including a citation's own link

**Gap 3 · §8 gap · high demo risk · recorded nowhere before D-61 · FR-13 "retaining the
thread", and FR-12's "links to the source document".**

`frontend/src/pages/Ask.jsx:129-130` holds `conversationId` and `turns` in `useState`
only. Nothing uses the URL or storage. The citation's "View document/meeting" link
(`frontend/src/components/Answer.jsx:54-58`) is a same-tab `<Link>`, so following it
unmounts the Ask screen, and Back returns an empty conversation. The only way back is to
reopen the thread from the list — and then its citations no longer expand, which is 2.2.

This is the flow an assessor walks: ask a question, click a citation to check it, come
back. It is the one gap in this file that is most likely to be seen live.

- Smallest fix: put the active thread in the URL (`/ask?c=<id>`) and call
  `fetchConversation` on mount. Stopgap: open source links in a new tab.
- Effort, as the audit estimates it: about a day of front-end work.
- **Owner: Stage 5 item 4a** (28 September). Its test lands in the same commit, in the
  front-end suite, because only the interface can satisfy the clause.

### 2.2 A reopened turn has no expansion, no source link and no Sources panel

**Gap 4 · §8 gap · FR-12's citation clauses, on the reopen path.**

`GET /api/conversations/{id}` returns statements with no passages and no sources
(`apps/api/serializers.py:744-755`), and `frontend/src/utils/turns.js` `savedTurnFrom`
sets `sources: []` and `expandable: false`. Live replies are correct; reopened ones are
inert. The clause audit says "Owner: Stage 5" and no Stage 5 item names it.

- Fix: for each surviving citation return its passage text and source title and date,
  taken from the same `permitted_citation_chunk_ids` result
  (`apps/api/serializers.py:550-566`), so it is re-scoped on read rather than trusted.
- This is a response-contract change. It needs a contract decision, not just code.
- **Owner: Stage 5 item 4b** (28 September).

### 2.3 `AnswerCitation.chunk` is `CASCADE`, so a reprocess or reindex destroys citations

**Gap 5 · §8 gap · FR-12 traceability · D-48 · pinned by
`apps/api/tests/test_fr12_traceability_lost_on_reprocess.py`.**

`apps/retrieval/models.py:114-116`. The loss is reachable in normal use, not only by an
administrator: `apps/api/views.py:863` requires only `contribute_content`, and `:870`
blocks only documents already Indexed — so a partially indexed document with cited
chunks can be reprocessed by an Employee. `manage.py reindex` does the same.

It is likely to fire before the demo rather than after it: any provider switch is a
mandated re-index (CLAUDE.md §4), and a re-index is also what D-40's mitigation forbids
before the demo. So this interacts with 5.2 and with 8.8.

- Fix: a migration to `SET_NULL`, plus a stored `chunk_uuid` and a passage-text snapshot
  on `AnswerCitation`, so the audit trail survives the chunk.
- **Owner: Stage 5 item 1a** (28 September), which states that it lands before any
  re-index — item 6's, a provider switch's, or the demonstration's.

### 2.4 An unused "New conversation" can outlive its session

**Gap 12 · minor · D-58.** Orphaned empty `Conversations` rows accumulate. **Owner:
Stage 5 item 5** (28 September), beside the throttle and the PDF bomb. Cheap to fix and
cheap to leave; it is here so the choice is made rather than forgotten.

---

## 3. Owned by a named Stage 5 item

Listed so the file is complete. These need no new decision; they need the item to be done.

| Item | Open work |
|---|---|
| Item 1 | `apps/api/answers.py:261-280` resolves titles with no source-side predicate and fails **open**; `apps/retrieval/search.py:456-469` does the same job and fails **closed** (gap 10, D-53). Not reachable from any shipped route today — only via `bulk_create(update_conflicts=True)` or raw SQL. Item 1's shared `scoped_documents()`/`scoped_meetings()` helpers are what remove the asymmetry |
| Item 4 | **Done 28 September, D-62.** Vitest, Testing Library and jsdom, a `frontend` CI job, the named tests under `frontend/tests/`, and `CLAUDE.md` §8 condition 2 amended. Gap 9 is closed. The residue is not "extend the suite": D-62 lists the front-end clauses with no test, and each belongs to the item that owns its behaviour. Gaps 3 and 4 remain neither tested nor fixed — see 2.1 and 2.2 |
| Item 5 | `/api/ask` is unthrottled — only the two auth endpoints are throttled (D-26) — worst case one request holding a worker ~900 s. PDF decompression bombs: D-50 closed the class for OOXML only, because `pypdf` inflates object streams with no ZIP involved |
| Item 6 | Everything currently fitted to the six-chunk placeholder corpus: `RELEVANCE_THRESHOLD` (D-37, provisional by its own terms, and D-38's trigger has fired), the partial-matches relevance floor, the three citation rates, p90, and FR-13 end to end. Do not re-measure before the corpus lands |
| Item 6 | `apps/retrieval/partial_matches.py:119-148` has no relevance floor, so an off-topic question offers the five nearest in-scope titles as "partially related" (gap 6, D-56) |
| Item 9 | Deployment topology for the FLM-backed alpha is undecided (gap 15). See 5.2 — this one should not wait for item 9 |

---

## 4. Deliberate deviations — to present, not to fix

Both are defensible and both are ✗ against the clause as written. They are gate items
because an assessor reads the clause, not the reasoning.

- **FR-12 "input is sanitised before use"** (gap 7, D-45). There is no sanitiser. The
  defence is parameterised SQL, React escaping, and neutralising the `[chunk_id:`
  delimiter (`apps/ai/prompting.py:204,408`). Prose injection through a document body is
  open (D-45 case c) and an Employee can trigger it; D-49 establishes it cannot widen
  scope. Must be presented as a deviation, never ticked.
- **FR-13 "passes prior turns"** (gap 8, D-42). Only prior questions are passed, never
  prior answers (`apps/retrieval/conversation.py:123-179`). A follow-up referring to
  something in the previous answer does not resolve. A deliberate narrowing.

---

## 5. On the demonstration path

Not a severity ranking — a list of what an assessor can see happen.

1. **2.1**, the thread lost on a citation link. The audit's own words: "That is the exact
   flow an assessor will try."
2. **Deployment topology, and why it is not an item-9 problem.** No deployment exists —
   only a database `docker-compose.yml` — and FLM runs on one laptop's NPU. A deployed
   alpha of FR-11/12/13 therefore means either that laptop is the host, or a switch to
   `anthropic`. A switch is a full re-index, which triggers 2.3 and breaks D-40's rule of
   no re-index before the demo. Deciding this at item 9, in the last week, makes 2.3
   unfixable in time. Decide it now.
3. **D-40, open and unidentified.** Answers change between identical runs near the
   threshold. Recorded 24 September, cause not established. The mitigation (rounding
   similarity before the threshold comparison) is itself a re-measure event.
4. **Latency.** p90 8.90 s against NFR-08's 4 s target (`docs/flm-baseline.md:562-563`);
   min 2.80 s, median 6.90 s, max 9.90 s over 50 attempts. Objective 03 measures p90 on
   23 October.

---

## 6. Minor, recorded so they are not rediscovered

- **Provenance state leaks a maintenance event.** `apps/api/serializers.py:710-716`
  returns state 3 regardless of scope, so a reader demoted since asking can tell whether
  a now-out-of-scope source was reprocessed or re-indexed (state 3) or not (state 2).
  Maintenance events only, never content, and they were entitled to the answer when they
  asked (gap 11).
- **Front-end constants duplicated.** `frontend/src/constants.js:109-111` restates 2, 10
  and 500 outside `apps/core/constants.py`, with no test catching drift.
  `apps/api/views.py:121` has a literal "50 MB" in a message (FR-08) (gap 13).
- **Branch naming.** `feat/M5-retrieval-and-generation` is not the per-FR name §7
  requires (gap 14). Historical; nothing to do.

---

## 7. §8, stated exactly

- **Condition 4 — declined, D-60.** `116a422` ("fix(item 1c): separate a destroyed
  provenance record from a re-scoped turn") changes FR-12 and FR-13 behaviour in
  `apps/api/serializers.py` and `frontend/src/components/Answer.jsx` and carries no FR ID
  anywhere in its message. D-59 names `72c26ed` and `96b4bbe` as the others. All are on
  `main`. A rewrite is impossible without rewriting merged history, and would not make §8
  pass, because condition 5 fails for a reason no rewrite touches.
- **Condition 5 — fails.** The closing audit reports gaps. Closing every item in section
  2 and re-running the auditor is the only route to condition 5, and the audit trail from
  D-57 to D-61 is the record of how many passes that has taken so far.

---

## 8. Open items no audit raised

These came out of review outside the auditor's remit. Each is here because it is either
a cause of something above, or a claim in the repository that is not true where it is read.

1. **CLOSED 28 September — `CLAUDE.md` §8 condition 2 named only `pytest`.** It is the
   definition of done and it was written entirely in back-end terms, which is why
   front-end clauses passed four stages with no automated evidence: nothing in the
   definition asked for any. `9d04f3c` rewrote it to require both suites, and to require
   that a clause only the interface can satisfy is tested in the front-end suite, where
   an API test and hand-testing do not stand in for it. A dated note in §8 explains the
   old wording, and §3's Tests row now names the front-end tools so the two sections do
   not contradict each other. It stays in this file because the consequence is
   counter-intuitive and belongs beside the open items rather than only in D-62:
   **the amendment raises the bar, so more of FR-12 and FR-13 fail condition 2 than
   before, not fewer.** It reaches forward, never back; it passes nothing.
2. **D-59 states, in the present tense, that the branch "is the head of open PR #17".**
   PR #17 was merged as `e71a0f9` on 27 September at 21:31. The sentence appears in the
   paragraph withdrawing an earlier claim about a mutable ref, which makes it an instance
   of the defect the entry was written to record. Correct it the way D-37's chunk count was
   corrected — a dated erratum, not a rewrite, because the error is part of the record.
3. **The FR-11 predicate is hand-written at each of these sites:** `apps/api/views.py:501`,
   `:652`, `:751`, `:843`, `:867`; `apps/retrieval/scoping.py:112`;
   `apps/retrieval/search.py:458`, `:465`. Every copy is a place the predicate can be
   omitted in a future edit with the others still passing their tests. Stage 5 item 1's
   shared helpers are the fix; until they land, this is the shape of the next scope defect.
   The list is written out rather than counted, so adding a site does not make this line
   false — it makes it incomplete, which is visible.
4. **`MAXIMUM_CONTEXT_TOKENS = 4000` is marked PROVISIONAL** in
   `apps/core/constants.py:53-55` with no decision record anywhere. `RELEVANCE_THRESHOLD`
   has D-37, D-38 and D-40; this constant has nothing. It cannot be re-tuned on evidence
   because no evidence was recorded for the current value.
5. **The repository has no cross-platform setup path.** The README documents one machine.
   A teammate on macOS cannot follow it, and the NPU-only prerequisites are not separated
   from the ones every developer needs. `docs/ai-provider.md` §6 and the autouse fixture
   in `conftest.py` mean the absence of an NPU does not block `pytest` — but nothing in
   the README says so, so it reads as though it does.
6. **The coverage-claim class is not closed structurally.** The rule is in
   `docs/decisions.md` and the named instances are fixed. Nothing prevents the next one:
   the loop stopped because it was decided to stop it, as D-60 records, not because a pass
   returned clean. "Name, don't count" — a claim whose truth depends on a set's size or
   order — is the form to look for.
7. **Objective 02's verification corpus is due 2 October and is not assembled.** The
   placeholder corpus that every current measurement is fitted to is a different, smaller
   thing and is not it. Item 6 is blocked on this, and the date is before Stage 5 starts.
8. **The §7 subject-line breach recurred in Stage 5 item 4, and the window to fix it is
   still open.** `ec6f39b` (`ci(D-25):`), `9d04f3c` and `90fbbe7` (both `docs(D-62):`)
   carry no FR ID in the subject; `ec6f39b` and `9d04f3c` carry none in the body either,
   so §8 condition 4 fails for those two as well as §7. It is the same substitution D-59
   records — a D-number standing where the FR ID belongs — and the cause was in
   `M6-BUILD-PROMPT.md`, whose session rules told the session to cite "its item number or
   its D-number". That wording is corrected. Unlike D-59's case these commits are
   **unpushed**, so amending the subjects costs one rebase; once pushed and merged, the
   record says "left as found" for the second time.

---

## 9. What this file does not cover

- **The verdicts themselves.** D-61 holds the closing audit verbatim, D-60 the §8
  conditions, D-57 to D-59 the earlier passes. Nothing here restates a verdict; read the
  entry.
- **The clause-by-clause position.** `docs/stage-4-clause-audit.md` and D-61's coverage
  tables have it. This file lists what is open, not what is satisfied.
- **Stage 3's usability findings.** `docs/usability-findings.md`, owned by Stage 5 item 7.
- **Anything about the state of work in progress.** What is open here was open at
  `0f49608`; closures and owners added on 28 September are dated in place. Beyond those,
  `git log` is the record of what has been done, and this file is not maintained against
  it. A commit or branch named here is named as history, never as current state.
- **The twelve requirements outside Stage 4.** FR-14 and FR-15 are unbuilt and are the
  body of Stage 5; FR-03's lockout is built ahead of them, which the audit notes as
  SHOULD-tier effort spent early.
