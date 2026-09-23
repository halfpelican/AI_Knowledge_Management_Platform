# Two-week plan — 24 September to 7 October 2026

A living copy of this plan is shared with the team; this file is the repository's
record of it. If the two disagree, the shared doc is the one people are reading.

---

## The window and what is fixed

Two weeks, Wednesday 24 September to Tuesday 7 October. One deadline falls inside
it: Objective 02's ingestion verification, due 2 October — and the corpus it needs
does not exist yet.

| Date | What has to be true | Source |
| --- | --- | --- |
| 2 Oct | Objective 02 verified: 20 documents across the four accepted formats, 5 pasted transcripts, 5 malformed or oversized files. Every valid item reaches indexed status and returns its own content when searched for a phrase known to appear in it. Every invalid item refused with the documented error. A 20-page document processed in under 60 seconds. | Proposal, Objective 02 |
| 23 Oct | Objective 03 verified: 4-second p90 on the query endpoint under load test, 30 questions with known answers where every displayed statement carries a resolving citation, Employee and Administrator result sets consistent with each role and no count disclosing withheld content. | Proposal, Objective 03 |
| 31 Oct | Stage 5 complete | `M6-BUILD-PROMPT.md` |
| 1 Nov | M6 gate: twelve MUST-HAVE requirements demonstrable end to end on a deployed alpha build | `CLAUDE.md` §2 |

Objective 02's corpus is roughly five times the placeholder set in the repository,
which holds four documents and one meeting. Assembling it needs no NPU and no
knowledge of the retrieval code, which makes it the natural first real task for
someone joining this week.

## Where the build stands

All 87 commits are Benjamin's, from the initial commit on 12 September to `4fa0024`.
Stages 0 to 3 are merged. The full suite runs at 730 tests, dual-role coverage 13/13.

Stage 4 — FR-11, FR-12, FR-13 — is in flight on `feat/M5-retrieval-and-generation`.
Items 1, 2 and 2a are done. Ten items remain, ending with a security review and a
set-level requirements audit.

Two of the twelve MUST-HAVEs are not started: FR-14 (dashboard) and FR-15 (document
repository and filtered browsing). Both are Stage 5, both presentation-layer, neither
depends on the NPU.

Every estimate below for Sagarika and Haseeb is a first estimate with no track record
behind it. Treat week one as a measurement of throughput, not a commitment.

## Benjamin — Stage 4 to merged, then Stage 5 opens

| Week | Work | Ends with |
| --- | --- | --- |
| 24–30 Sep | Stage 4 items 3–12 | Stage 4 merged to `main` by PR, pytest green, dual-role matrix 100%, auditor verdict recorded verbatim |
| 1–7 Oct | Stage 5 items 1 and 2 (FR-15, FR-14); run the Objective 02 corpus; record the D-35 screen capture | Both remaining MUST-HAVEs started; Objective 02 evidence captured |

Only Benjamin can run `manage.py reindex`, `scripts/citation_harness.py` and
`scripts/check_flm.py`; execute the Objective 02 ingestion run; and execute the
Objective 03 load test. Everything else below happens without him.

Review load is the real constraint. One review window a day, not continuous
interruption.

## What the missing NPU rules out, and what it does not

D-35 records that FastFlowLM needs an XDNA2 NPU and one machine has it.

**Ruled out** on the other two machines: `manage.py reindex`, the citation harness,
`check_flm.py`, and any manual click-through of Search or Ask against a live model.

**Not ruled out:** the test suite. `docs/ai-provider.md` §6 is explicit that tests
never reach a live FLM server — an autouse fixture in `conftest.py` points every
provider base URL at a closed loopback port and blanks the keys. All 730 tests run on
a laptop with no NPU.

Setup on a fresh machine:

1. Python 3.12 — pinned in `.python-version`, matched by CI. Not 3.13 or 3.14.
2. `docker compose up` for PostgreSQL 16 with pgvector.
3. `.env` copied from `.env.example`. Leave `AI_PROVIDER=flm`; tests never call it.
4. `pip install -r requirements.txt`, then `python manage.py migrate`.
5. `pytest -q` — expect 730 passed. If it does not, stop and say so before writing code.

Step 5 is the gate. Budget the whole first day for it.

## Sagarika — API layer and documentation

**Week 1 (24–30 Sep)**

1. Environment to a green suite. Day one.
2. Read `CLAUDE.md`, `docs/api-contract.md`, `docs/schema-v1.md`, then
   `docs/decisions.md` — skim the register, read D-15, D-19, D-21, D-25, D-30 in full.
3. First PR, deliberately small: audit `docs/api-contract.md` against the endpoints
   that actually exist in `apps/api/` and correct the drift.

**Week 2 (1–7 Oct)**

4. FR-15's API surface — document repository list endpoint with filters,
   permission-scoped, tests from both roles. Lives in `apps/api/` and
   `apps/documents/`, away from Benjamin's Stage 4 work.
5. Begin the NIT3003 documentation deliverables.

If item 3 lands by Friday, item 4 is realistic. If not, drop item 4 and keep her on
documentation, which blocks nobody.

## Haseeb — verification, and the corpus due 2 October

**Week 1 (24–30 Sep)**

1. Environment to a green suite. Day one.
2. Assemble the Objective 02 test corpus: 20 documents across PDF, DOCX, XLSX and
   TXT; 5 pasted transcripts; 5 deliberately malformed or oversized files. At least
   one document of 20+ pages. Record for each item the expected outcome and a phrase
   known to appear in it.
3. Hand the corpus to Benjamin by Thursday, leaving a day of slack before 2 October.

**Week 2 (1–7 Oct)**

4. Write the load-test scripts for the query endpoint (k6 or JMeter). NFR-08: 4-second
   p90. NFR-09: 20 concurrent users, ≤25% degradation. Writing needs no NPU; running
   happens on Benjamin's machine once Stage 4 merges.
5. Record the first measured p90. Finding a miss on 7 October is recoverable; finding
   it on 23 October is not.

The Stage 4 security review stays with Benjamin because it runs inside the build
session. Haseeb takes the Stage 5 final pass.

## How three people work on this without colliding

**Ownership by directory, these two weeks only.** Benjamin: `apps/retrieval/`,
`apps/ai/`, `scripts/`, `frontend/src/` until Stage 4 merges. Sagarika: `apps/api/`,
`docs/api-contract.md`. Haseeb: the test corpus and the load-test scripts. Nobody
edits `apps/core/constants.py`, `docs/decisions.md` or `CLAUDE.md` without saying so.

**`CLAUDE.md` §7 applies to everyone now.** Branch per requirement. Conventional
commits with the FR ID. Tests in the same commit as the code. `main` stays runnable.
Everything merges by pull request.

**Review.** Benjamin reviews every PR, in one window a day.

**Decisions.** If it is not settled in `docs/decisions.md`, stop and ask. Cite the
number in the commit message rather than restating the reasoning.

**Checkpoints.** Monday, Wednesday, Friday. Fifteen minutes. What merged, what is
blocked, what did you have to decide without asking.

## Risks

| Risk | Signal | Response |
| --- | --- | --- |
| Onboarding costs more review time than it returns | By 30 Sep neither teammate has a merged PR and Stage 4 has slipped | Stop assigning code; both move to documentation, corpus and load tests |
| Objective 02 misses 2 Oct | Corpus not assembled by Thursday 1 Oct | Run against a partial corpus and record honestly what was covered |
| One machine, one NPU | D-35 accepted this knowingly | Record the screen capture as soon as Stage 4 works, not in the last week |
| NFR-08's 4 seconds unreachable on a local 4B model | First measured p90 well over 4 seconds | Report as a local-model baseline per `docs/ai-provider.md` §7 and record a decision; do not quietly drop the NFR |
| Alpha deployment unscoped | Stage 5 item 5 says "alpha deployment"; nothing says where or how | Decide in week 2 and record it |

`CLAUDE.md` names the drop order if the schedule slips — FR-07, then FR-17, FR-18,
FR-19, FR-20 — none of which move the M6 number. Breadth beats depth: cut depth inside
FR-14 and FR-15, never the requirement.

## Done means, on 7 October

- [ ] Stage 4 merged to `main` by PR; pytest green; dual-role matrix 100%; auditor verdict recorded verbatim
- [ ] A question answers with verified inline citations; a question with no relevant material returns no-answer without calling the model; a fabricated identifier is stripped
- [ ] Objective 02 run and its evidence recorded
- [ ] FR-15 and FR-14 both started, each with at least one merged commit
- [ ] Sagarika and Haseeb each have at least one merged pull request
- [ ] Load-test scripts exist and have produced one measured p90
- [ ] The D-35 screen recording exists for the Stage 4 flow
- [ ] The alpha deployment target is decided and recorded as a numbered decision
