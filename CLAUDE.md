# CLAUDE.md — Project 8, Organisational Knowledge Management Platform

Read this before touching anything. It is the single source of truth for how this
repository is built. Where this file and a chat instruction disagree, say so rather
than silently following one.

---

## 1. What this is

A VU IT Capstone (NIT3003 / NIT3004) build: an AI-powered organisational knowledge
management platform. Documents and meeting transcripts are ingested, chunked,
embedded and indexed; users ask questions in natural language; the system answers
**only** from retrieved passages the asking user is permitted to see, with every
statement carrying a verified citation.

The full specification is `Project_8-proposal_complete_V4.5.docx` in the Claude
project. Functional requirements are referenced throughout this repo by ID
(FR-01 … FR-20). Never invent a requirement. If a behaviour is not in the proposal,
raise it rather than building it.

**Team.** Benjamin Morovan (BM, lead — AI & RAG pipeline, extraction, indexing,
front-end build) · Sagarika Dey (SD — REST API layer, meeting intelligence,
assistant, documentation) · Haseeb Malik (HM — database, auth & RBAC, retrieval
scoping, security, NFR verification).

### Companion documents

| File | What it settles |
|---|---|
| `M6-BUILD-PROMPT.md` | The Stage 5 brief. Earlier stages' briefs are in its git history |
| `docs/api-contract.md` | Every route and response shape. The front end builds against it |
| `docs/stage-4-open-items.md` | What Stage 4 left open, each item naming the record that holds it |
| `docs/schema-v1.md` | Table definitions, deferred tables, fixed vocabularies, schema gaps |
| `docs/ai-provider.md` | The `AIService` contract, FLM configuration, structured-output strategy |
| `docs/decisions.md` | Every settled decision, numbered, with rationale and date |

---

## 2. The only deadline that matters right now

**M6 — Sunday 1 November 2026 — mandatory gate.** All **twelve** MUST-HAVE
requirements demonstrable end-to-end on a deployed alpha build.

| | | |
|---|---|---|
| FR-01 | User registration | Auth |
| FR-02 | User login | Auth |
| FR-04 | Logout & session management | Auth |
| FR-05 | Role management | Auth |
| FR-06 | RBAC enforcement, server-side on every protected route | Auth |
| FR-08 | Document upload, extraction & indexing | Ingestion |
| FR-09 | Meeting transcript ingestion | Ingestion |
| FR-11 | Permission-aware retrieval scoping | Retrieval |
| FR-12 | Knowledge search & answer generation | Retrieval |
| FR-13 | Conversational knowledge assistant | Retrieval |
| FR-14 | Dashboard overview | Presentation |
| FR-15 | Document repository & filtered browsing | Presentation |

**Not in the gate.** FR-03 and FR-10 (SHOULD) and FR-16 sit in NIT3004.
FR-07, FR-17, FR-18, FR-19, FR-20 (COULD) are protective — they are dropped in that
order if the schedule slips, and dropping them does not move the M6 number.

Older documents say "fourteen MUST-HAVE (FR-01 to FR-14)". That range is wrong: it
excludes FR-15, which is MUST, and includes FR-03, FR-07 and FR-10, which are not.
The corrected list is the table above. Build to the table.

**Breadth beats depth at this gate.** Twelve requirements working simply scores
better than eight working well. When you are behind, cut depth inside a
requirement — fewer filter dimensions on FR-15, a leaner FR-14 dashboard — never
cut a requirement.

---

## 3. Stack

| Layer | Choice |
|---|---|
| Backend | Django 5.x + Django REST Framework |
| Database | PostgreSQL 16 + pgvector (via `pgvector-django`) |
| Frontend | React + Vite |
| Generation & embeddings | **FastFlowLM (FLM)** on the AMD Ryzen AI NPU — see §4 |
| Extraction | `pypdf`, `python-docx`, `openpyxl`; TXT read directly |
| Tests | `pytest-django`; Vitest + Testing Library + jsdom for `frontend/` (D-62) |
| Python | **3.12** — matches the CI runner. Pinned in `.python-version` and CI. |

One database serves both the relational schema and the vectors, so a record and its
embedding are written in the same ACID transaction (NFR-21).

---

## 4. AI provider — the most important rule in this file

**No application code may import an AI vendor SDK directly.** Every AI call goes
through `apps/ai/provider.py`, which exposes exactly three operations:

```python
class AIService(Protocol):
    def embed(self, texts: list[str]) -> EmbeddingResult: ...
    def generate_statements(self, question: str, passages: list[Passage]) -> StatementList: ...
    def health(self) -> ProviderHealth: ...
```

Two implementations, selected by the `AI_PROVIDER` environment variable:

- `flm` — **the default for all development, testing and demonstration.**
  FastFlowLM, local, on the NPU. Free, offline, no key.
- `anthropic` — Claude + Voyage. The documented production configuration. Kept
  working so the proposal's §9.2 remains true, but not used day to day — and not
  available to this project in practice, because there is no budget for it. The
  alpha and the demonstration run on `flm`. Plan nothing around a provider switch.

If you find yourself writing `import anthropic` or `from openai import OpenAI`
anywhere outside `apps/ai/`, stop — that is the bug.

Full contract in `docs/ai-provider.md`.

### FLM configuration

Development runs on **native Windows with PowerShell** — not WSL. The NPU is not
visible from inside WSL2, so keeping everything on the Windows side means
`127.0.0.1` genuinely is the same machine and there is no host-IP indirection.

```powershell
# In its own PowerShell window, left running
flm serve gemma3:4b --embed 1
```

```
AI_PROVIDER=flm
FLM_BASE_URL=http://127.0.0.1:8625/v1
FLM_API_KEY=flm                          # placeholder, no real credential
FLM_CHAT_MODEL=gemma3:4b
FLM_EMBED_MODEL=embed-gemma
EMBEDDING_DIMENSION=768
```

FLM speaks the OpenAI wire format, so the `openai` Python package is the client for
both providers — only `base_url`, `api_key` and model names differ.

### Embedding consistency (FR-08 — this will bite you)

Vectors from different models are not comparable but still return a plausible
similarity score, so a model change is a silent corruption, not an error. Therefore:

- Every `ContentChunk` row stores `embedding_model` and `embedding_dimension`.
- Retrieval executes **only** over chunks whose recorded model matches the current
  query model. Mismatched chunks are excluded, not ranked.
- The pgvector column dimension comes from `EMBEDDING_DIMENSION`, never a literal.
- Switching providers is a full re-index event. There is a management command for
  it: `python manage.py reindex --provider <name>`.

This is risk R10 in the register. It is the highest-scoring technical risk and the
one most likely to be discovered the night before the demo.

---

## 5. Tuned constants

These live in `apps/core/constants.py` and nowhere else. Values marked *tune* are
set during evaluation, not guessed in a code review.

| Constant | Value |
|---|---|
| `CHUNK_SIZE` | 500 tokens |
| `CHUNK_OVERLAP` | 50 tokens |
| `TOP_K` | 25 initially, *tune* |
| `RELEVANCE_THRESHOLD` | *tune* — cosine similarity floor for admitting a passage |
| `MAXIMUM_CONTEXT_TOKENS` | *tune* — ceiling on grounding context per call |
| `MAXIMUM_GENERATION_ATTEMPTS` | **3** — 1 initial call + 2 retries, then 503 (NFR-19) |
| `MAXIMUM_EMBED_ATTEMPTS` | **3** — 1 initial call + 2 retries, then flag the item |
| `MAXIMUM_CLASSIFY_ATTEMPTS` | **3** — 1 initial call + 2 retries (FR-10, NIT3004) |
| `MINIMUM_QUESTION_LENGTH` | ~10 characters |
| `MAXIMUM_QUESTION_LENGTH` | ~500 characters |
| `MINIMUM_CONTENT_LENGTH` | below this, mark "insufficient content", do not embed |
| `MAX_UPLOAD_BYTES` | 50 MB |
| `ACCEPTED_FORMATS` | **PDF, DOCX, XLSX, TXT** — four, per D-15 |
| `LOCKOUT_THRESHOLD` / `LOCKOUT_DURATION` | 5 attempts / 15 minutes (FR-03, NIT3004) |
| `NO_ANSWER_MESSAGE` | fixed text, defined once |

**The three attempt constants are totals, not retry counts.** The proposal words them
as "2 retries", which is the same thing said differently. Comment each one
`# 1 initial call + 2 retries` so nobody helpfully corrects them to 2. NFR-19's
fault-injection test asserts the provider was called exactly three times before the
503 — that test is what keeps this honest.

`ACCEPTED_FORMATS` is four formats, not the six named in FR-08's upload area. DOC and
XLS are legacy binary formats with no parser in the stack, and accepting a format
that always returns 415 is a defect rather than a feature. The client-side rejection
message names the same four. See D-15.

Fixed vocabularies — document and meeting status values, classification dimensions,
source types, no-answer reasons — are in `docs/schema-v1.md` §3 and live in the same
constants module.

---

## 6. Invariants — breaking one of these fails the project, not just a test

1. **Permission filtering happens before ranking, never after.** FR-11 restricts the
   candidate set at retrieval. Material outside the user's scope must never reach
   the AI service, must never contribute to an answer, and its existence must not be
   disclosed — not by a result count, a total, or an error message that distinguishes
   "not found" from "not permitted". Filtering a ranked list afterwards is the wrong
   shape and will be caught in the demo.
2. **`visible_to_roles` is denormalised onto `ContentChunks`**, stamped at ingestion
   from the owning Document or Meeting, so invariant 1 is a predicate on the same
   table as the vector rather than a discipline someone has to remember. No query
   shape can rank first. Changing a source's visibility **re-stamps every one of its
   chunks in the same transaction** — that cascade is a model-level guarantee, not a
   convention, and it has its own test. See D-17 and D-47.

   > **This invariant asserted something untrue from 12 September to 25 September
   > 2026, and the correction is dated rather than quietly applied.** The cascade was
   > written here as a model-level guarantee with its own test; it was neither. There
   > was no `save()` override, no signal, and no test. It was found by the FR-11
   > scoping work at Stage 4 item 11, after the clause enumeration, and implemented
   > the same day as item 11a. The measured consequence was invariant 1 broken with
   > evidence: narrow a document to `[Administrator]`, and `GET /api/documents`
   > correctly returned `[]` while `POST /api/ask` still answered an Employee with a
   > citation from that document. It was latent only in the sense that no shipped
   > route mutated the column — the corpus loads by script and `README.md` documents
   > a `manage.py shell` snippet for direct row edits, which is how it would have
   > been reached in practice. The lesson is about this file: an invariant that
   > describes its own enforcement is a claim, and a claim in a document nobody tests
   > is indistinguishable from an intention. Nine of the other ten were audited as
   > claims at the same time; `docs/stage-4-clause-audit.md` records what that
   > found.
3. **Meetings are scoped by role, never by attendance.** `Meetings.visible_to_roles`
   mirrors `Documents` exactly. Knowledge has to outlive the people who were in the
   room, and a second scoping mechanism would mean two code paths through the single
   filter that matters most. `MeetingAttendees` is a participation record for FR-20,
   not an access control. See D-16.
4. **Authorisation is server-side, always.** Hiding a UI element is usability, not
   security. Every protected route checks the role on the server. 401 for an invalid
   or expired token, 403 for a role lacking the permission. DRF defaults to
   `AllowAny`, so `DEFAULT_PERMISSION_CLASSES` is set to `IsAuthenticated` before the
   first protected route exists — until that line lands, FR-06 is not partly done, it
   is inverted.
5. **Citation verification is application code, not a model judgement.**
   `verifyCitations()` receives passage *identifiers* and checks set membership
   against the IDs supplied in the prompt. Any statement whose identifier is absent,
   unrecognised or fabricated is removed before the answer is returned. It cannot
   and does not assess whether a passage actually supports the statement — that
   limitation is known, conceded, and must not be papered over with a second model
   call.
6. **There is no interface state that shows an uncited factual statement.** If
   nothing survives verification, the no-answer response is returned — not a
   fragment, not greyed-out text, not a "withheld" panel.
7. **No-answer has two distinct paths, logged separately.** (a) No passage exceeded
   `RELEVANCE_THRESHOLD` — return without invoking generation at all. (b) Passages
   retrieved but no statement survived verification. A rising rate of (b) means
   retrieval is admitting passages that do not answer the question. The distinction
   lives in `QueryLog.no_answer_reason`.
8. **A failed AI step never discards the source.** Transcript storage, document
   storage and indexing status are independent of summarisation or classification
   success (NFR-20).
9. **Ingestion is atomic.** A document record and its chunks and vectors commit
   together or not at all (NFR-21). No orphaned or half-indexed rows.
10. **Structured output or nothing.** A generation response that does not conform to
    `STATEMENT_LIST_SCHEMA` is treated as no response and retried, then 503.

---

## 7. Git discipline

**Commit at every stage increment.** Not at the end of a session, not when a feature
is "finished" — at each numbered step in the build plan. A stage that ends without a
commit did not happen.

- Branch per requirement: `feat/FR-08-document-ingestion`. Work that spans
  requirements branches by its primary one (`fix/FR-12-citation-cascade`); a
  stage- or item-numbered branch breaks this rule (D-61's gap 14).
- Conventional commits, FR ID in the subject:
  `feat(FR-08): extract text from PDF, DOCX, XLSX and TXT`
- Never commit `.env`, an API key, or a database dump.
- Tests for a requirement land in the same commit as the requirement.
- `main` stays runnable. If either suite fails on `main` — `pytest`, or `npm test`
  in `frontend/` — that is the only priority.
- Each stage merges to `main` by pull request before the next begins. A branch that
  CI has only ever seen in isolation has not been integrated, and teammates need a
  real base to branch from.

### Migrations

These rules apply to **every** agent that writes a migration, not only
`django-backend`.

- Migrations are additive and reversible.
- Never edit a **pushed** migration's operations — add a new one.
- The one exception is a missing `dependencies` entry, which no later migration can
  supply, since dependencies are a property of the node rather than an operation.
  Correct it in place, only while no other environment has applied it, and log the
  edit in `docs/decisions.md` with that evidence.
- `python manage.py makemigrations --check --dry-run` runs in CI. Models and
  migrations agreeing is a permanent condition, not a one-off check.

---

## 8. Definition of done

A requirement is done when **all** of these hold — not four of five:

1. The endpoint or component behaves as its FR section specifies, including the
   error paths and the stated HTTP status codes.
2. **Both suites pass: `pytest`, and the front-end suite (`npm test` in
   `frontend/`).** The server side is tested from **both** an Employee and an
   Administrator session (Objective 01 requires 100% of protected endpoints
   covered from both roles). A clause that only the interface can satisfy — what
   a screen shows, withholds or offers — is tested in the front-end suite. An API
   test does not stand in for it, and neither does hand-testing.

   > **Amended 28 September 2026 (D-62).** This condition used to read "`pytest`
   > passes", and that wording is why the front end had no automated evidence from
   > Stage 2 until Stage 5 item 4. A front-end test could not satisfy it, and the
   > condition could not require one, so this file's definition of done left out a
   > whole layer. D-25 raised the gap and it stayed open.
3. The happy path and at least one failure path are both tested.
4. The work is committed on its branch with the FR ID in the message.
5. `requirements-auditor` has checked it against the FR text and reported no gaps.

---

## 9. How to work here

- Six subagents live in `.claude/agents/`. Use them — each is scoped to a slice of
  the system and carries the invariants for that slice. Rules that apply to more than
  one agent live in this file, not in an agent file, so that every agent sees them.
- Follow `M6-BUILD-PROMPT.md` stage by stage. Do not skip ahead; the ordering is the
  critical path, and authentication genuinely gates retrieval scoping.
- When a decision is not settled, stop and ask rather than picking silently. Settled
  decisions are numbered in `docs/decisions.md`; cite the number in code comments and
  commit messages rather than restating the rationale.
- Report what is actually true. An overstated summary is worse than a blocker,
  because the auditor reads the repository rather than the summary and the
  discrepancy surfaces later and more expensively.
- Prefer the boring implementation. This is a capstone with a fixed gate, not a
  product. Cleverness that costs a day is a bad trade.
