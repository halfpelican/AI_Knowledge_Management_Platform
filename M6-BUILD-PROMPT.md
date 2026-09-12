# M6 build prompt

The implementation plan for Project 8, from an empty repository to the mandatory
gate. Work through it **one stage at a time** — paste a single stage into Claude
Code, finish it, commit, then move on. Pasting the whole file at once produces a
plausible-looking skeleton with nothing working underneath it, which is the failure
mode this document exists to prevent.

---

## Where things stand

| | |
|---|---|
| Today | 12 September 2026 |
| Repository | empty — README only |
| M2 (environment & schema) | was due 4 September — **not started** |
| M3 (authentication & RBAC) | due 18 September — **6 days** |
| M6 (mandatory gate) | Sunday 1 November — **7 weeks** |

M2 is late and M3 will be a few days late. That is recoverable, because the original
estimates for the two heaviest AI tasks were deliberately pessimistic at two weeks
each, and because the gate measures breadth rather than polish. It is only
recoverable if the front end of the schedule is compressed rather than the back end,
so Stages 0 to 2 run hot and the RAG work keeps its full allowance.

The schedule below re-aligns to the original milestone dates by the end of Stage 3.

| Stage | Delivers | Milestone | Target |
|---|---|---|---|
| 0 | Decisions settled, FLM proven | — | Sun 14 Sep |
| 1 | Scaffolds, schema, pgvector, CI | M2 | Thu 17 Sep |
| 2 | FR-01, 02, 04, 05, 06 | M3 | Tue 22 Sep |
| 3 | FR-08, FR-09 | M4 | Fri 2 Oct |
| 4 | FR-11, FR-12, FR-13 | M5 | Fri 23 Oct |
| 5 | FR-14, FR-15, integration, alpha | **M6** | Sat 31 Oct |

---

## Rules for every session

Give these to Claude Code once at the start of each session, or rely on `CLAUDE.md`
being read — but state them again when starting a new stage.

```
Read CLAUDE.md and docs/ai-provider.md before your first edit.

Rules for this session:
- Build only what the stage asks for. Do not scaffold ahead to future stages.
- Use the subagents in .claude/agents/. Each is scoped to a slice and carries the
  invariants for that slice.
- Commit at every numbered commit point. Do not batch commits to the end.
- If a decision is not settled in docs/decisions.md, stop and ask. Do not pick
  silently.
- Tests land in the same commit as the code they test.
- When you finish the stage, run the requirements-auditor and report its verdict
  verbatim. Do not summarise it favourably.
```

---

# Stage 0 — Settle the decisions and prove FLM
**Target: Sunday 14 September · no milestone · nothing else can start until this is done**

Four architectural decisions are open. Two of them are settled by choosing FLM, and
leaving the other two open will cost a day of rework each later.

```
We are starting implementation of Project 8. The repository is empty.

Create docs/decisions.md recording these four decisions, each with the decision,
the rationale and the date:

1. Python version — standardise on 3.12 across all three developers and CI.
   Benjamin is on 3.14 and Haseeb on 3.13; the CI runner is 3.12, and the lowest
   common version is the one that cannot produce a "works on my machine" failure.
   Add .python-version and pin it in CI.

2. Login field — decide username or email for FR-01 and FR-02 and record it. This
   blocks the User model, so it cannot stay open past today.

3. Embedding model and dimension — SETTLED by the FLM decision.
   embed-gemma (embeddinggemma-300m), 768 dimensions, recorded against every chunk
   per FR-08. Voyage remains the documented production path and is a re-index event.

4. API key ownership and spend caps — SETTLED by the FLM decision.
   Development and testing use local inference with no key and no metered cost.
   An Anthropic key is needed only if the production path is exercised. Note that
   this closes risks R11 (cost overrun) and substantially reduces R12 (sensitive
   content sent to an overseas provider) for the whole build phase.

Then prove the local inference path actually works, before any application code
depends on it:

5. Write scripts/check_flm.py. It must:
   - read FLM_BASE_URL from the environment
   - GET /models and print what is loaded
   - POST /chat/completions with a trivial prompt and print the reply
   - POST /embeddings for two strings, print the returned dimension, and assert it
     equals 768
   - print a clear pass/fail summary
   Development is native Windows under PowerShell, so 127.0.0.1:52625 is the same
   machine. Do not add WSL host-IP handling.

Tell me exactly how to start the FLM server in a second PowerShell window.
```

**Commit point 0.1** — `chore: record open decisions and add FLM connectivity check`

**Done when:** `python scripts/check_flm.py` passes from the environment you will
actually develop in, and `docs/decisions.md` has no decision still marked open.

> If `check_flm.py` cannot reach the server, fix that now. Every later stage assumes
> it works, and diagnosing it through a Django stack trace in three weeks is far
> worse than diagnosing it through a twelve-line script today.

---

# Stage 1 — Scaffolds, schema and CI
**Target: Thursday 17 September · milestone M2**

```
Stage 1: environment and schema. Milestone M2.

Use the django-backend agent for 1-4 and 6, react-frontend for 5.

1. Django 5 project. Layout:
     config/                settings (env-driven, no hard-coded values), urls, wsgi
     apps/core/             constants.py, shared base models, UUID PK mixin
     apps/accounts/         users, roles, permissions
     apps/documents/        documents, content chunks
     apps/meetings/         meetings, attendees
     apps/ingestion/        (empty for now — owned by rag-pipeline in Stage 3)
     apps/retrieval/        (empty for now — owned by rag-pipeline in Stage 4)
     apps/ai/               provider abstraction
     apps/api/              DRF serializers, viewsets, routers
   Settings read from environment with django-environ. requirements.txt pinned.

2. apps/core/constants.py — every constant from CLAUDE.md section 5, with the
   proposal's values. Nothing inline anywhere else, ever.

3. PostgreSQL 16 + pgvector. docker-compose.yml for local Postgres so all three
   developers get the same database. Enable the vector extension in a migration.

4. Schema migration v1, matching the proposal's table definitions:
     Users, Roles, Permissions, RolePermissions
     Documents, ContentChunks, Meetings, MeetingAttendees
     QueryLog
   UUID primary keys. ContentChunks carries the vector column sized from
   settings.EMBEDDING_DIMENSION, plus embedding_model and embedding_dimension
   columns. Fixed vocabularies for status fields, not free text.

5. React + Vite scaffold in frontend/. Router, one API client module, design tokens,
   and a component sheet stub. No feature screens yet.

6. apps/ai/ per docs/ai-provider.md: base.py with the Protocol and dataclasses,
   flm.py, anthropic.py, __init__.py with get_ai_service(), and the startup check
   that refuses to boot on an embedding-dimension mismatch.

7. GitHub Actions: install on Python 3.12, run migrations against a Postgres
   service container, run pytest. It must pass before this stage is done.

8. pytest-django configured, with a stub AIService fixture that the whole suite will
   use. No test ever reaches a live FLM server.
```

**Commit points** — commit after each of 1, 3–4, 5, 6, 7. Five commits minimum.

**Done when:** `pytest` passes locally and in CI; `python manage.py migrate` builds
the schema from empty; the vector column dimension comes from settings; all three
developers can run the same database from `docker-compose up`.

**Then run:**
```
Run the requirements-auditor over the schema against the proposal's table
definitions. Report its verdict verbatim.
```

---

# Stage 2 — Authentication and RBAC
**Target: Tuesday 22 September · milestone M3 · FR-01, FR-02, FR-04, FR-05, FR-06**

This is on the critical path. FR-11 filters retrieval by role *before* ranking, so
permission-scoped retrieval cannot be built until roles and server-side enforcement
exist. Nothing downstream is trustworthy until this stage is genuinely finished —
which is why it is tested from both roles rather than from one.

```
Stage 2: authentication and RBAC. Milestone M3. FR-01, FR-02, FR-04, FR-05, FR-06.

Use the django-backend agent, then test-engineer, then security-reviewer.

1. FR-01 registration and FR-02 login. bcrypt hashing. The login field is whatever
   docs/decisions.md settled. Correct status codes from the FR sections.

2. FR-04 logout and session management. Server-side invalidation — a token must stop
   working after logout, and there is a test that proves it.

3. FR-05 role management. Employee and Administrator, Administrator generalising
   Employee. Permissions held against roles, never against individual users. Role
   changes write an audit-log entry.

4. FR-06 RBAC enforcement middleware or permission classes, applied server-side to
   every protected route. 401 invalid or expired token; 403 valid token, wrong role.

5. Authentication and role-management screens (react-frontend). Role management is a
   MUST-HAVE with no route in the original wireframes — it needs a real screen.

6. test-engineer: build the dual-role coverage matrix. Enumerate protected routes
   from the URL conf, assert every one has both an Employee and an Administrator
   test, and fail the suite when a route has no coverage. Report the percentage.

7. security-reviewer: adversarial pass over auth and RBAC before this stage is
   claimed complete.
```

**Commit points** — one per numbered item. Seven commits.

**Done when:** the dual-role matrix reports **100%**, the security review is clean or
its findings are fixed, and an Administrator can change a user's role and see it take
effect on the next request without re-login.

> This is the milestone the team named as its own slip trigger: a miss here is
> visible at week 8 with six weeks of runway, rather than on 1 November with none. If
> Stage 2 is not done by 22 September, that is the moment to tell the supervisor,
> not later.

---

# Stage 3 — Ingestion pipeline
**Target: Friday 2 October · milestone M4 · FR-08, FR-09**

```
Stage 3: ingestion. Milestone M4. FR-08, FR-09.

Use the rag-pipeline agent, then test-engineer.

1. Upload endpoint. File-signature validation, not extension. 50 MB cap enforced
   before reading the file into memory. Title required. Correct status codes.

2. extractPlainText() routing to pypdf / python-docx / openpyxl / direct read. A
   format in ACCEPTED_FORMATS with no parser raises UnsupportedFormatError loudly
   rather than producing empty text later. Original file and extracted text stored
   separately.

3. splitIntoOverlappingChunks() — 500 tokens, 50 overlap. Terminate on
   endPosition >= totalTokens, NOT on start position. Test at three boundaries:
   shorter than one chunk, exactly one chunk, one chunk plus one token.

4. Embedding and indexing through AIService.embed(). Two retries then flag.
   embedding_model and embedding_dimension recorded on every chunk row. The document,
   its chunks and its vectors commit in ONE transaction (NFR-21).

5. Content below MINIMUM_CONTENT_LENGTH marked "insufficient content", not embedded.

6. FR-09 meeting transcript ingestion, file upload or pasted text. Title and date
   required, date not in the future, minimum length enforced. Same chunking and
   embedding path. NO speaker or timestamp parsing — explicitly out of scope.

7. Upload screen and document repository list (react-frontend): per-file progress,
   client-side format rejection with the message naming accepted formats, "Indexed"
   status, and the "Processing failed. Please try again" action.

8. test-engineer: disguised-file rejection, oversize rejection, the three chunking
   boundaries, and a mid-ingestion failure leaving either a complete record or
   nothing.
```

**Commit points** — one per numbered item. Eight commits.

**Done when:** a real PDF, DOCX, XLSX and TXT each upload, extract, chunk, embed and
index end-to-end; a transcript does the same; an injected mid-ingestion failure
leaves no partial row; `pytest` passes.

**Then run:**
```
Run the requirements-auditor over FR-08 and FR-09 clause by clause. Report verbatim.
```

---

# Stage 4 — Retrieval, RAG and the assistant
**Target: Friday 23 October · milestone M5 · FR-11, FR-12, FR-13**

The heart of the project and the work Benjamin owns. Two things here decide whether
the demonstration survives questioning: the permission boundary, and what happens
when the system cannot answer.

```
Stage 4: retrieval and grounded generation. Milestone M5. FR-11, FR-12, FR-13.

Use the rag-pipeline agent throughout, then test-engineer, then security-reviewer.

Before writing retrieval code:

0. Run scripts/citation_harness.py over a fixed question set and a fixed corpus.
   Report schema conformance rate, fabricated-identifier rate and empty-answer rate.
   Record them in docs/flm-baseline.md. If conformance is below 95%, fix it at the
   prompt and parser level first. Do not build on an unreliable schema.

1. FR-11 permission-scoped retrieval. The scope is applied to the candidate set
   BEFORE ranking. Out-of-scope material is never retrieved, never sent to the AI
   service, never in the answer, and its existence is not disclosed — not by a result
   count, not by a total, not by an error message that distinguishes "not found" from
   "not permitted".

2. Query embedding using the model recorded against the indexed content. Chunks with
   a different recorded model are excluded from the candidate set entirely.

3. Cosine similarity in application code over stored vectors. TOP_K = 25, then drop
   everything below RELEVANCE_THRESHOLD.

4. No-answer path A: nothing above the threshold. Return the no-answer response
   WITHOUT calling generation at all. There is a test asserting the provider call
   count is zero.

5. Grounded generation. Prompt contains only retrieved passages, each labelled with
   its chunk identifier, constrained to answer solely from them. Truncate to
   MAXIMUM_CONTEXT_TOKENS by discarding the lowest-ranked passages first. Response
   must conform to STATEMENT_LIST_SCHEMA; a non-conforming response is a failed
   attempt, retried, then 503 after MAXIMUM_GENERATION_ATTEMPTS (NFR-19).

6. verifyCitations() — set membership of returned identifiers against the IDs
   supplied in the prompt. Unrecognised or fabricated identifiers mean the statement
   is removed. Application code, not a model call.

7. No-answer path B: passages retrieved but nothing survived verification. Same
   response, DIFFERENT logged reason code from path A.

8. Query logging: question, retrieved chunk IDs, answer, verified citations, result
   count, answered status.

9. FR-13 multi-turn assistant, permission re-checked on EVERY turn (django-backend).

10. Search / Ask / Sources front-end including the no-answer state and the AI-
    unavailable 503 notice (react-frontend). There is no interface state that
    displays an uncited statement — do not render rejected statements greyed out or
    in a "withheld" panel.

11. test-engineer: the scoping test above all — a user asks a question whose only
    good answer lives in a document their role cannot see. Assert absence from the
    answer, the sources, the count, and the payload sent to the AI service.

12. security-reviewer: full pass, with the leakage checklist and the prompt-injection
    check on ingested content.
```

**Commit points** — one per numbered item. Twelve commits.

**Done when:** a question answers with verified inline citations; a question with no
relevant material returns no-answer without calling the model; a fabricated
identifier is stripped; a user cannot retrieve across the permission boundary by any
route the security review could find; `pytest` passes.

---

# Stage 5 — Presentation, integration and alpha
**Target: Saturday 31 October · milestone M6 · FR-14, FR-15**

```
Stage 5: presentation layer and integration. Milestone M6.

1. FR-15 document repository and filtered browsing — metadata, filtering,
   permissioned deletion, browsing by tag or category without composing a search
   query. Scope depth to what the time allows: fewer filter dimensions is an
   acceptable cut, the requirement missing is not.

2. FR-14 dashboard — recent documents, meetings and queries, scoped to the requesting
   user.

3. End-to-end integration pass across all twelve MUST-HAVEs. Both roles, real files,
   a real corpus.

4. Accessibility pass: contrast ratios documented, focus states, tab order, text
   equivalents for non-text content, component sheet complete.

5. Alpha deployment and a demonstration script that exercises all twelve in order.

6. requirements-auditor: full set-level audit against the M6 gate list. Not
   requirement by requirement — the SET. Every one of the twelve owned, implemented,
   tested, nothing duplicated, nothing in the wrong layer, nothing satisfied only in
   the UI.

7. security-reviewer: final pass.
```

**Commit points** — one per numbered item. Seven commits.

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

And the three numbers worth having ready when asked:

- [ ] Dual-role protected-endpoint coverage: **100%**
- [ ] Citation schema conformance rate from `docs/flm-baseline.md`
- [ ] Fabricated-identifier rate, and the fact that verification strips them

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
