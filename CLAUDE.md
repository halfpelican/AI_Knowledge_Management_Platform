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
| Tests | `pytest-django` |
| Python | **3.12** — matches the CI runner. Pinned in `.python-version` and CI. |

One database serves both the relational schema and the vectors, so a record and its
embedding are written in the same ACID transaction (NFR-21).

---

## 4. AI provider — the most important rule in this file

**No application code may import an AI vendor SDK directly.** Every AI call goes
through `apps/ai/provider.py`, which exposes exactly three operations:

```python
class AIService(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...
    def generate_statements(self, question: str, passages: list[Passage]) -> StatementList: ...
    def health(self) -> ProviderHealth: ...
```

Two implementations, selected by the `AI_PROVIDER` environment variable:

- `flm` — **the default for all development, testing and demonstration.**
  FastFlowLM, local, on the NPU. Free, offline, no key.
- `anthropic` — Claude + Voyage. The documented production configuration. Kept
  working so the proposal's §9.2 remains true, but not used day to day.

If you find yourself writing `import anthropic` or `from openai import OpenAI`
anywhere outside `apps/ai/`, stop — that is the bug.

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
FLM_BASE_URL=http://127.0.0.1:52625/v1
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
| `MAXIMUM_GENERATION_ATTEMPTS` | 2 retries, then 503 (NFR-19) |
| `MAXIMUM_EMBED_ATTEMPTS` | 2 retries, then flag the item |
| `MINIMUM_QUESTION_LENGTH` | ~10 characters |
| `MAXIMUM_QUESTION_LENGTH` | ~500 characters |
| `MINIMUM_CONTENT_LENGTH` | below this, mark "insufficient content", do not embed |
| `MAX_UPLOAD_BYTES` | 50 MB |
| `ACCEPTED_FORMATS` | PDF, DOCX, XLSX, TXT (four, per D-15; DOC and XLS dropped) |
| `LOCKOUT_THRESHOLD` / `LOCKOUT_DURATION` | 5 attempts / 15 minutes (FR-03, NIT3004) |
| `NO_ANSWER_MESSAGE` | fixed text, defined once |

---

## 6. Invariants — breaking one of these fails the project, not just a test

1. **Permission filtering happens before ranking, never after.** FR-11 restricts the
   candidate set at retrieval. Material outside the user's scope must never reach
   the AI service, must never contribute to an answer, and its existence must not be
   disclosed. Filtering a ranked list afterwards is the wrong shape and will be
   caught in the demo.
2. **Authorisation is server-side, always.** Hiding a UI element is usability, not
   security. Every protected route checks the role on the server. 401 for an invalid
   or expired token, 403 for a role lacking the permission.
3. **Citation verification is application code, not a model judgement.**
   `verifyCitations()` receives passage *identifiers* and checks set membership
   against the IDs supplied in the prompt. Any statement whose identifier is absent,
   unrecognised or fabricated is removed before the answer is returned. It cannot
   and does not assess whether a passage actually supports the statement — that
   limitation is known, conceded, and must not be papered over with a second model
   call.
4. **There is no interface state that shows an uncited factual statement.** If
   nothing survives verification, the no-answer response is returned — not a
   fragment.
5. **No-answer has two distinct paths, logged separately.** (a) No passage exceeded
   `RELEVANCE_THRESHOLD` — return without invoking generation at all. (b) Passages
   retrieved but no statement survived verification. A rising rate of (b) means
   retrieval is admitting passages that do not answer the question.
6. **A failed AI step never discards the source.** Transcript storage, document
   storage and indexing status are independent of summarisation or classification
   success (NFR-20).
7. **Ingestion is atomic.** A document record and its chunks and vectors commit
   together or not at all (NFR-21). No orphaned or half-indexed rows.
8. **Structured output or nothing.** A generation response that does not conform to
   `STATEMENT_LIST_SCHEMA` is treated as no response and retried, then 503.

---

## 7. Git discipline

**Commit at every stage increment.** Not at the end of a session, not when a feature
is "finished" — at each numbered step in the build plan. A stage that ends without a
commit did not happen.

- Branch per requirement: `feat/FR-08-document-ingestion`.
- Conventional commits, FR ID in the subject:
  `feat(FR-08): extract text from PDF, DOCX, XLSX and TXT`
- Never commit `.env`, an API key, or a database dump.
- Tests for a requirement land in the same commit as the requirement.
- `main` stays runnable. If `pytest` fails on `main`, that is the only priority.

---

## 8. Definition of done

A requirement is done when **all** of these hold — not four of five:

1. The endpoint or component behaves as its FR section specifies, including the
   error paths and the stated HTTP status codes.
2. `pytest` passes, including a test exercising the requirement from **both** an
   Employee and an Administrator session (Objective 01 requires 100% of protected
   endpoints covered from both roles).
3. The happy path and at least one failure path are both tested.
4. The work is committed on its branch with the FR ID in the message.
5. `requirements-auditor` has checked it against the FR text and reported no gaps.

---

## 9. How to work here

- Six subagents live in `.claude/agents/`. Use them — each is scoped to a slice of
  the system and carries the invariants for that slice.
- Follow `M6-BUILD-PROMPT.md` stage by stage. Do not skip ahead; the ordering is the
  critical path, and authentication genuinely gates retrieval scoping.
- When a decision is not settled, stop and ask rather than picking silently. Open
  decisions are tracked in `docs/decisions.md`.
- Prefer the boring implementation. This is a capstone with a fixed gate, not a
  product. Cleverness that costs a day is a bad trade.
