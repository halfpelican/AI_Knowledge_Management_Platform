# AI provider contract

Every AI call in this system goes through one interface with two implementations.
Nothing else in the codebase knows which model is answering.

- **`flm`** — FastFlowLM on the AMD Ryzen AI NPU. Local, free, offline. **Default for
  all development, testing and demonstration.**
- **`anthropic`** — Claude for generation, Voyage for embeddings. The production
  configuration documented in the proposal. Kept working, not used day to day.

Two things are easy to confuse and worth separating once: **Claude Code is the tool
building this repository; FLM is what the built application calls at runtime.**
Swapping the application's provider to FLM does not change how the code is written.

---

## 1. The interface

`apps/ai/base.py`

```python
from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True)
class Passage:
    chunk_id: str          # the identifier verification will check against
    text: str

@dataclass(frozen=True)
class Statement:
    text: str
    chunk_id: str          # the passage this statement was drawn from

@dataclass(frozen=True)
class StatementList:
    statements: list[Statement]

@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]
    model: str             # recorded against every chunk — see FR-08
    dimension: int

@dataclass(frozen=True)
class ProviderHealth:
    available: bool
    detail: str

class AIService(Protocol):
    def embed(self, texts: list[str]) -> EmbeddingResult: ...
    def generate_statements(self, question: str, passages: list[Passage]) -> StatementList: ...
    def health(self) -> ProviderHealth: ...
```

Three operations, deliberately. Classification (FR-10) and summarisation (FR-16) are
NIT3004 work and get their own methods later — do not add them speculatively.

`generate_statements` raises `ProviderUnavailable` after
`MAXIMUM_GENERATION_ATTEMPTS`, which the view turns into 503 with the NFR-19 notice.
A response that does not conform to the statement schema counts as a failed attempt,
not as an answer.

---

## 2. Selection

`apps/ai/__init__.py`

```python
def get_ai_service() -> AIService:
    provider = settings.AI_PROVIDER
    if provider == "flm":
        return FLMService()
    if provider == "anthropic":
        return AnthropicService()
    raise ImproperlyConfigured(f"Unknown AI_PROVIDER: {provider}")
```

Call `get_ai_service()`. Never instantiate an implementation directly outside
`apps/ai/`, and never import `openai` or `anthropic` outside that package. The
auditor greps for exactly this.

---

## 3. FLM implementation

FLM speaks the OpenAI wire format, so the `openai` package is the client for both
providers — only the base URL, key and model names differ.

```python
from openai import OpenAI

class FLMService:
    def __init__(self):
        self._client = OpenAI(
            base_url=settings.FLM_BASE_URL,   # http://127.0.0.1:52625/v1
            api_key=settings.FLM_API_KEY,     # "flm" — a placeholder, not a credential
        )
```

### Running the server

In its own PowerShell window, left running for the session:

```powershell
flm serve gemma3:4b --embed 1
```

`--embed 1` loads EmbeddingGemma alongside the chat model; the embedding model must
be co-resident with an LLM in server mode. Endpoints then available at
`http://127.0.0.1:52625/v1`: `/models`, `/chat/completions`, `/embeddings`,
`/audio/transcriptions`.

| Setting | Value |
|---|---|
| Chat model | `gemma3:4b` |
| Embedding model | `embed-gemma` (embeddinggemma-300m, Q4_1) |
| Embedding dimension | 768 |
| Max embedding chunk | 2048 tokens — our 500-token chunks are well inside it |
| Requires | XDNA2 NPU (Strix, Strix Halo, Kraken, Gorgon Point), driver ≥ 32.0.203.304 |

### Why native Windows, not WSL

The NPU is not visible from inside WSL2. Django, the tests and the FLM server all run
on the Windows side, so `127.0.0.1:52625` is the same machine for all of them and
there is no host-IP indirection to get wrong.

Confirm the server is up before debugging anything else:

```powershell
curl.exe http://127.0.0.1:52625/v1/models
```

If someone on the team later wants to develop in WSL, they must run `flm serve` on
the Windows host and set `FLM_BASE_URL` to the host IP — `127.0.0.1` inside WSL is
the WSL VM, not Windows. Record it in `docs/decisions.md` if that happens, because it
changes the setup instructions for everyone.

---

## 4. Embedding consistency — FR-08

Vectors from different models are not comparable, but comparing them still returns a
plausible-looking similarity score. There is no error, only quietly wrong answers.
This is risk R10 in the register.

Rules, enforced in code rather than remembered:

1. Every `ContentChunk` stores `embedding_model` and `embedding_dimension` as written.
2. Retrieval filters to chunks whose `embedding_model` equals the current query
   model. Mismatched chunks are excluded from the candidate set — not ranked lower,
   excluded.
3. The pgvector column dimension is `settings.EMBEDDING_DIMENSION`, never a literal.
4. Changing provider or model means re-indexing:
   `python manage.py reindex --provider <name>`.
5. A startup check compares `EMBEDDING_DIMENSION` against the dimension the provider
   actually returns for a probe string and refuses to start on a mismatch. Silent
   dimension drift is the failure this prevents.

| Provider | Model | Dimension |
|---|---|---|
| `flm` | `embed-gemma` | 768 |
| `anthropic` | `voyage-4` | per Voyage's model card — confirm before switching |

Dev and production are therefore **two separate indexes**. Do not point a
FLM-embedded database at a Voyage query path and wonder why retrieval got worse.

---

## 5. Structured output — the real risk

FR-12 requires the model to return discrete statements, each tagged with the
identifier of the passage it came from. Free prose cannot be verified statement by
statement, so the structure is what makes verification possible at all.

FLM's OpenAI-compatible surface does not currently advertise a `response_format` /
JSON-schema mode. Treat reliable JSON as something you must **establish and measure**,
not assume.

**Required schema**

```json
{
  "statements": [
    {"text": "Purchase orders above $10,000 require two approvals.", "chunk_id": "c_4471"}
  ]
}
```

**Strategy, in order:**

1. A strict system prompt: return only JSON matching the schema, no prose, no code
   fence, use only the chunk IDs supplied, and if the passages do not answer the
   question return `{"statements": []}`.
2. One worked example in the prompt. Small models follow a demonstration far better
   than a description.
3. A tolerant parser — strip code fences, take the outermost balanced JSON object,
   reject anything still unparseable.
4. Any response that does not parse into the schema is a **failed attempt**, retried
   up to `MAXIMUM_GENERATION_ATTEMPTS`, then 503. Never a partial answer.
5. If FLM exposes constrained decoding or a grammar option in a later release, use
   it and delete steps 2 and 3.

**Measure it before building on it.** `scripts/citation_harness.py` runs a fixed
question set against a fixed corpus and reports:

- schema conformance rate (target ≥ 95%)
- fabricated-identifier rate — IDs not present in the prompt
- empty-answer rate where an answer was in fact available

Record the numbers in `docs/flm-baseline.md`. They are worth having at the
demonstration: "our local model conforms to the citation schema 97% of the time and
fabricated an identifier in 2% of responses, which verification then stripped" is a
much stronger answer than an assurance.

---

## 6. Testing

Tests never reach a live FLM server. Inject a stub `AIService` returning fixed
vectors and fixed statement lists, so the suite passes in CI and on a machine with no
NPU. Provider-specific behaviour — JSON repair, retry, the 503 path — is tested
against recorded responses, including deliberately malformed ones.

---

## 7. What this buys the project

- **No metered API cost during development** — risk R11 largely closed.
- **No uploaded content leaving the machine during development** — risk R12 largely
  closed for the build phase, which is worth stating at the demonstration.
- **A demonstration that does not depend on the network.**
- A defensible architecture point: the AI Service boundary in the UC-07 sequence
  diagram is satisfied by either implementation. That is provider independence,
  demonstrated rather than claimed.

What it does not buy: answer quality equal to Claude. Do not benchmark the platform's
answer quality on FLM output and present those numbers as the system's capability.
Report them as what they are — local-model baselines.
