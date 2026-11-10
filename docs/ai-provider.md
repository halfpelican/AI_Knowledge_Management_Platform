# AI provider contract

Every AI call in this system goes through one interface with two implementations.
Nothing else in the codebase knows which model is answering.

- **`anthropic`** — Claude for generation and classification (Haiku 5.5, D-121), Voyage
  `voyage-4` for embeddings. The production configuration documented in the proposal.
  **The default since 10 November 2026 (D-122),** after every tuned value was re-derived on
  it, each per model. **Funded from 10 November 2026** by the Max plan's monthly Claude
  API credits (D-113); M8 can be hosted on any device with the platform in place (D-114).
- **`flm`** — FastFlowLM on the AMD Ryzen AI NPU. Local, free, offline. **The default until
  10 November 2026,** when every earlier measurement ran on it, and now the offline
  alternative.

Which provider is the default, and which one M8 runs on, is chosen by measurement; a switch
is a full re-index (§4).

Two things are easy to confuse and worth separating once: **Claude Code is the tool
building this repository; the provider is what the built application calls at runtime.**
Swapping the application's provider does not change how the code is written.

---

## 1. The interface

`apps/ai/base.py`

```python
from dataclasses import dataclass
from typing import Callable, Literal, Protocol

InputType = Literal["query", "document"]   # what embed()'s texts are (D-116)

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

@dataclass(frozen=True)
class GenerationAttempt:          # apps/ai/generation.py — the observer's record
    number: int                   # 1-based; the last is MAXIMUM_GENERATION_ATTEMPTS
    outcome: str                  # "parsed" | "schema-violation" | "call-failed"
    seconds: float
    raw: str | None = None        # the reply text, None where the call itself failed
    detail: str | None = None     # the violation message or the failure description
    statements: int | None = None

@dataclass(frozen=True)
class TagScheme:                  # FR-10 — the scheme one document is classified against (D-104)
    doc_types: tuple[str, ...]    # DOCUMENT_TYPES
    departments: tuple[str, ...]  # distinct non-blank Documents.department values in the audience
    tags: dict[str, tuple[str, ...]]  # Project, Process, Topic -> active tag names

@dataclass(frozen=True)
class Assignment:
    value: str
    confidence: float             # the model's own estimate, in [0, 1]

@dataclass(frozen=True)
class TagSuggestion:
    dimension: str                # Project, Process or Topic
    value: str
    confidence: float

@dataclass(frozen=True)
class DocumentClassification:
    doc_type: Assignment          # value is one of the scheme's doc_types; any other reply is rejected
    department: Assignment        # as suggested; whether it is in the scheme is apps/documents' call (D-105)
    tags: tuple[TagSuggestion, ...]
    model: str                    # the chat model that answered, for the DocumentAnalysis record
    input_truncated: bool         # the text was cut at CLASSIFICATION_INPUT_TOKENS before it was sent

@dataclass(frozen=True)
class Transcription:              # D-123 — one recording segment's text, a draft
    text: str                     # the speech model's text, stripped; may be empty
    model: str                    # FLM_ASR_MODEL, whisper-v3:turbo

class TranscriptionDisabled(ProviderUnavailable): ...  # TRANSCRIPTION_PROVIDER=none

class AIService(Protocol):
    def embed(self, texts: list[str], *, input_type: InputType | None = None) -> EmbeddingResult: ...
    def generate_statements(
        self,
        question: str,
        passages: list[Passage],
        *,
        on_attempt: Callable[[GenerationAttempt], None] | None = None,
    ) -> StatementList: ...
    def health(self) -> ProviderHealth: ...
    def classify_document(self, title: str, text: str, scheme: TagScheme) -> DocumentClassification: ...
    def transcribe(self, audio: bytes, *, filename: str = "segment.wav") -> Transcription: ...
    def transcription_health(self) -> ProviderHealth: ...
```

The operations are the ones listed on `AIService`, and the list is the source of truth, not a
count. `classify_document` arrived with FR-10 on 9 November 2026 (D-104), when NIT3004 asked for
it; it lives in its own module, `apps/ai/classification.py`, so nothing in the generation prompt
or its loop changed for it — section 5b. `transcribe` and `transcription_health` arrived on 10
November 2026 with recording transcription (D-123), when the user asked for it — section 5c.
Summarisation (FR-16) gets its own method the same way when its requirement is built, not
speculatively before.

`generate_statements` raises `ProviderUnavailable` after
`MAXIMUM_GENERATION_ATTEMPTS`, which the view turns into 503 with the NFR-19 notice.
A transport failure, a 5xx and, since D-118, a 429 each count as a failed attempt. Any
other 4xx is `ProviderRefused`, a `ProviderUnavailable` that ends the attempts at once,
because the same request would be refused again (`apps/ai/_status.py`). The provider logs
every 4xx with its status and body first, a 429 as a WARNING and anything else as an
ERROR. So a rate limit or an exhausted credit ends in the 503, not a 500.
A response that does not conform to the statement schema counts as a failed attempt,
not as an answer.

`classify_document` raises `ProviderUnavailable` after `MAXIMUM_CLASSIFY_ATTEMPTS`; ingestion
catches it and leaves the document unclassified (invariant 8, NFR-20). A reply that does not
conform to `CLASSIFICATION_SCHEMA`, including a type outside the fixed list, counts as a failed
attempt, not as a classification. A 4xx is handled as for generation (D-118), because
classification makes its calls through the same `_chat_once` and `_claude_once`: a 429 is a
failed attempt, and any other 4xx ends the attempts at once.

`transcribe` raises `TranscriptionDisabled` before any call when `TRANSCRIPTION_PROVIDER` is
`none`, and otherwise `ProviderUnavailable` after `MAXIMUM_TRANSCRIBE_ATTEMPTS`, with a 4xx handled
as for generation (D-118). `POST /api/transcriptions` answers either with a 503 carrying its own
code. `transcription_health` never raises (section 5c).

### `on_attempt` — an observer, not an operation

`on_attempt` is keyword-only, defaults to `None`, and is called once per generation
attempt with a `GenerationAttempt` the method already computes and would otherwise
discard. It **cannot change what is asked of the model or what comes back**: it receives
a record after the fact, its return value is ignored, and an exception raised inside it is
caught and discarded in `apps/ai/generation.py`, so the attempt loop proceeds exactly as
it would with no callback — the same number of provider calls, the same return value, the
same `ProviderUnavailable` at the end. That last point is the reason the guarantee is
written down: NFR-19's fault-injection test asserts the provider was called exactly three
times before the 503, and a measuring instrument must not be able to move the number it is
measuring.

**Nothing under `apps/` passes it.** The only caller in the repository is
`scripts/citation_harness.py`, which needs per-attempt records to report schema
conformance **per response**, with the first-attempt rate separately, the way
`docs/flm-baseline.md` does. Without the observer the harness would have to run its own
retry loop, and a second retry loop beside the shipped one is exactly the duplication
Stage 4 item 5 removed. `apps/ai/tests/test_observer_is_not_used_in_application_code.py`
reads the source of every module under `apps/` and fails if one appears as a caller.

The observer is not an operation: the operations are the ones listed above, and a keyword on an
existing one adds nothing to the interface a caller must implement — every implementation
already computes what it reports. A parameter that changed what the model is asked, such as
FR-13's conversation history, would be a different question and is argued on its own merits
when item 9 reaches it. `classify_document` has no observer: nothing measures classification per
attempt, and a second route from a raw model reply into `apps/` is not opened for it.

It is declared in the Protocol signature itself, not only in the implementations: a
contract and its implementations differing by a parameter is the defect this project keeps
finding in other people's code, and it is not worth shipping deliberately.

### `input_type` — what the texts are (D-116)

`input_type` is keyword-only and defaults to `None`. Callers set it as follows:

- **Retrieval** passes `"query"` when it embeds a question (`apps/retrieval/query_embedding.py`).
- **FR-19's aggregation cycle** embeds unanswered questions and zero-result search terms through
  the same `embed_question`, so they go as `"query"` (`apps/retrieval/gaps.py`). Keyword search
  never called a provider; since FR-19 a kept zero-result term does, cut to
  `MAXIMUM_QUESTION_LENGTH`, and on `anthropic` that provider is Voyage (D-107's note of
  10 November).
- **Ingestion** passes `"document"` for every chunk (`apps/ingestion/embedding.py`).
- **The width probes** in `apps/ai/checks.py` and `reindex` pass nothing.

Each provider then does this with it:

- **Voyage** gets it as its own `input_type` field and puts a different instruction in front of
  each side. Voyage documents better retrieval with it, and says vectors made with and without it
  stay comparable.
- **FLM** accepts it and sends nothing. EmbeddingGemma learns the same thing from the task prefix
  the callers put in the text (`apps/ai/prefixes.py`), and Voyage never receives that prefix.

Unlike `on_attempt`, this parameter changes what the model is asked. So it was argued on its own
merits, as the paragraph above requires, and settled as D-116. Changing it re-indexes documents,
just as changing a prefix does.

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

**Recording transcription has a setting of its own** (D-123): `TRANSCRIPTION_PROVIDER`,
`none` (the default) or `flm`. It is independent of `AI_PROVIDER`, because only FLM has
speech-to-text, so a deployment on the `anthropic` default still transcribes through FLM when the
setting is `flm`. `apps.ai.transcription_enabled()` reads it without calling anything; the
transcription itself still goes through `get_ai_service().transcribe()` (section 5c). An unknown
value is `ImproperlyConfigured`, and the startup check reports it as `ai.E003`.

---

## 3. FLM implementation

FLM speaks the OpenAI wire format, so the `openai` package is the client for both
providers — only the base URL, key and model names differ.

```python
from openai import OpenAI

class FLMService:
    def __init__(self):
        self._client = OpenAI(
            base_url=settings.FLM_BASE_URL,   # http://127.0.0.1:8625/v1
            api_key=settings.FLM_API_KEY,     # "flm" — a placeholder, not a credential
        )
```

### Running the server

In its own PowerShell window, left running for the session:

```powershell
flm serve gemma3:4b --embed 1
```

**FLM must be v0.9.39** (D-83). From v1.0.4 onward its embeddings are non-deterministic
(upstream ROCm/FastFlowLM#732): the same text embeds to a different vector each time, so
retrieval silently returns noise while chat still works. Check with `flm version`, and run
`scripts/check_flm.py` before any measurement, load test or demonstration; it fails on a
noisy build. Newer releases are evaluated after M8, and a version whose vectors differ means a
full re-index.

`--embed 1` loads EmbeddingGemma alongside the chat model; the embedding model must
be co-resident with an LLM in server mode. Endpoints then available at
`http://127.0.0.1:8625/v1`: `/models`, `/chat/completions`, `/embeddings`,
`/audio/transcriptions`.

**For recording transcription (D-123), add `--asr 1`**, which loads `whisper-v3:turbo`
beside the other two (`flm pull whisper-v3:turbo` first, 623 MB):

```powershell
flm serve gemma3:4b --embed 1 --asr 1
```

Measured on v0.9.39 on 6 November 2026: one server holds all three models, and
`scripts/check_flm.py` still passes with speech loaded. **Before starting a server, check for one
already running** (`Get-Process flm`): Windows lets two `flm serve` processes listen on 8625 at
once, requests then go to either, and the second could not load its model.

| Setting | Value |
|---|---|
| Chat model | `gemma3:4b` |
| Embedding model | `embed-gemma` (embeddinggemma-300m, Q4_1) |
| Embedding dimension | 768 |
| Speech model | `whisper-v3:turbo`, with `--asr 1` (D-123) |
| Max embedding chunk | 2048 tokens — our 500-token chunks are well inside it |
| Requires | XDNA2 NPU (Strix, Strix Halo, Kraken, Gorgon Point), driver ≥ 32.0.203.304 |

### Why native Windows, not WSL

The NPU is not visible from inside WSL2. Django, the tests and the FLM server all run
on the Windows side, so `127.0.0.1:8625` is the same machine for all of them and
there is no host-IP indirection to get wrong.

Confirm the server is up before debugging anything else:

```powershell
curl.exe http://127.0.0.1:8625/v1/models
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
   `python manage.py reindex --provider <name>`. A new width also needs
   `--resize-column <database>`. Migration 0002 sizes the column from `EMBEDDING_DIMENSION`
   when it first runs, so `migrate` cannot resize an existing column (D-117).
5. A startup check compares `EMBEDDING_DIMENSION` against the dimension the provider
   actually returns for a probe string and refuses to start on a mismatch. Silent
   dimension drift is the failure this prevents.
6. The relevance threshold and the partial-match floor belong to the model too (D-120).
   `ranking.admit` and `partial_matches` are given the question's embedding model and look
   up its own values. A model that is not listed gets EmbeddingGemma's.

| Provider | Model | Dimension | Threshold / floor |
|---|---|---|---|
| `flm` | `embed-gemma` | 768 | 0.30 / none (D-102) |
| `anthropic` | `voyage-4` | 1024, Voyage's default. 256, 512 and 2048 are offered, never 768 (Voyage's API reference, checked 10 November 2026) | 0.2687 / 0.2468 (D-120) |

So moving to Voyage resizes the column. Set `EMBEDDING_DIMENSION=1024`, then run
`reindex --provider anthropic --resize-column <database>` on a database copied for it
(D-113, D-117).

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

**The statement cap (step 7 phase 2a, 7 November 2026).** The schema's `statements` array
has `maxItems` = `MAXIMUM_STATEMENTS`, a tuned constant in `apps/core/constants.py`. Each
attempt's user prompt says how many statements it may give, and rule 8 of the system
prompt tells the model to keep to it.

- **Over the cap is a failed attempt,** like any other schema violation. Nothing is trimmed
  to fit (invariant 10).
- **The first attempt asks for `MAXIMUM_STATEMENTS`.** After a reply that reached
  `max_tokens` or broke the cap, the next attempt asks for half as many (at least one);
  after any other failure the number stays.
- **Three attempts in total, as before.**
- **Why.** Phase 1 found every 503 was a reply still listing statements at the 800-token
  ceiling, and repeating the identical request never recovered it (D-82's note of
  7 November 2026).

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

## 5b. Classification output (FR-10)

`apps/ai/classification.py`, added with FR-10 on 9 November 2026 (D-104). One structured call
returns a document's type, department and tags against the scheme the caller passes
(`TagScheme`, built by `apps/documents/classification.py` for the document's own audience). The
same approach as section 5, because it is the same risk: a small local model and free-form JSON.

**Required schema** (`CLASSIFICATION_SCHEMA`)

```json
{
  "doc_type":   {"value": "Procedure", "confidence": 0.92},
  "department": {"value": "Lantern Room", "confidence": 0.88},
  "tags": [
    {"dimension": "Process", "value": "wick trimming", "confidence": 0.9}
  ]
}
```

- Exactly three keys. `doc_type.value` **must be one of the scheme's `doc_types`** (DOCUMENT_TYPES:
  Policy, Procedure, Report, Meeting Paper), or the reply is a `SchemaViolation` — a type outside
  the fixed list is not a classification (invariant 10; FR-10: "selected from a fixed list rather
  than generated freely"). `department.value` is any non-empty string; whether it is in the scheme
  is decided in `apps/documents` (D-105), never by the provider.
- `tags` holds at most `MAXIMUM_TAG_SUGGESTIONS` (8) objects, each with `dimension` one of
  Project, Process or Topic, a non-empty `value` and a `confidence`. More than the cap is a
  violation, counted as returned; nothing is trimmed to fit.
- Every `confidence` is a number in [0, 1]. A string, a boolean or a number outside the range is a
  violation, not repaired.
- A tag with the same dimension and name as an earlier one, after `normalise_tag_name` (lower
  case, single spaces), is dropped and the first kept. That is a shape tolerance — two spellings of
  one tag are one suggestion — not a repair of content.

**Prompt strategy, in order** (`CLASSIFICATION_SYSTEM_PROMPT`, `build_classification_messages`)

1. A strict system prompt: JSON only; the type from the fixed list, copied exactly; the department
   from the listed departments; tags only from the values listed per dimension, except that a NEW
   Topic value may be proposed when no listed one fits — never a new Project, Process or
   department; at most eight tags; confidence as the model's honest estimate; no explanation.
2. One worked example whose subject (lighthouse keeping) and whose departments and tag values are
   alien to any organisation, for the reason the comment above `SYSTEM_PROMPT` in
   `apps/ai/prompting.py` records: a worked example is training data for the response, and this
   prompt carries no identifiers, so the lesson applies to content. The example's reply uses
   listed values only and proposes no new Topic — a demonstrated invention would be copied onto
   every document. The only values it shares with a real prompt are the four fixed types.
   `apps/ai/tests/test_classification_prompt.py` asserts the example's values appear in no real
   scheme (the corpus manifest) and in no real user turn.
3. The user turn carries the scheme's lists (document types, departments, Project, Process and
   Topic tags — `(none listed)` where a dimension is empty), then the title, then the text, then
   the instruction to reply with the JSON object only.
4. The same tolerant parser as generation — code fence, preamble, trailing comma, nothing else —
   through the same three pieces of code, imported from `apps/ai/schema.py` under public names
   rather than copied.
5. A reply that does not parse is a failed attempt (below).

**Untrusted text.** The title and text are an uploaded document's. Nothing in them is transformed:
this prompt cites no identifier, so unlike the generation prompt (D-45) it has no delimiter whose
forgery converts into an accepted citation, and no neutralisation is applied. The residual is a
body that steers the model in prose or forges a scheme line; shape validation cannot detect it.
What bounds it: the type is held to the fixed list by the parser, the department and tag values
are held to the scheme by the application (D-105), and a person confirms the suggestions.

**Truncation** (`classification_input`). The model reads the title and the first
`CLASSIFICATION_INPUT_TOKENS` (1,500) whitespace tokens of the extracted text — D-31's token —
joined by single spaces. Whether anything was cut is returned as `input_truncated` on the
`DocumentClassification` and kept on the record rather than hidden. The cut is made by the
provider and again at the prompt boundary (it is idempotent), so no caller can send more.

**Retry policy** (`run_classification_attempts`): `run_generation_attempts`' exactly, with
`MAXIMUM_CLASSIFY_ATTEMPTS` (3) as the total — 1 initial call + 2 retries. A transport failure
or a 5xx is a failed attempt; a non-conforming reply is a failed attempt; a 4xx propagates after
one call and consumes no retry; after the last attempt, `ProviderUnavailable` naming the
provider and the last failure. Every attempt is recorded through `apps/ai/attempt_log.py` under
the step `classification`, at WARNING when it failed and INFO when it parsed, quoting nothing of
the reply. On FLM, `temperature` is 0.0 and `max_tokens` is `CLASSIFICATION_MAX_TOKENS` (400).
On Claude there is no sampling parameter, which current models refuse, and `max_tokens` is
`CLAUDE_MAX_TOKENS`, generation's Claude ceiling, because thinking counts against it and 400 would
cut the reply off before its JSON (#67, D-115). Every call carries
`CLASSIFICATION_TIMEOUT_SECONDS` (300). Both providers call the one loop; `model` on
the result is `FLM_CHAT_MODEL` or `ANTHROPIC_MODEL`, whichever answered.

**The stub** (`StubAIService.classify_document`). Deterministic and derived from the scheme: the
first document type, the first department (or `STUB_OUT_OF_SCHEME_DEPARTMENT` when the scheme
lists none), one tag per dimension that lists a value, every confidence `STUB_CONFIDENCE`,
`model` `STUB_CHAT_MODEL`, and the real `input_truncated`. Every call is recorded in
`classify_calls`. A test overrides it with `StubAIService(classification=...)` or by setting the
`classification` attribute on the suite's stub: a `DocumentClassification` is returned as-is, a
callable is called with `(title, text, scheme)` and may raise `ProviderUnavailable` to stand in
for an outage.

**Not measured yet.** Section 5's rates were established with `scripts/citation_harness.py`
before anything was built on them. The classification prompt has no harness run behind it: its
conformance rate on `gemma3:4b` is unmeasured, and D-106's sweep on the development documents is
where it gets one. Until then, treat the prompt as a first version with a tested parser and a
tested retry path, not as a measured one.

---

## 5c. Recording transcription (D-123)

`apps/ai/transcription.py` holds the one call both providers make, because Claude and Voyage have
no speech-to-text: a multipart POST to FLM's `/v1/audio/transcriptions` with `FLM_ASR_MODEL`,
`language=en`, `response_format=json` and the segment as a WAV part, carrying
`TRANSCRIPTION_TIMEOUT_SECONDS`. The FLM provider passes its own client; the Anthropic provider
builds an FLM client from `FLM_BASE_URL` only when the setting is `flm`.

- **One segment per call.** The page cuts a recording into WAV segments of at most
  `TRANSCRIPTION_SEGMENT_SECONDS` and sends them one at a time. The server never decodes MP4, M4A
  or MP3; it receives only 16-bit PCM WAV, which Python's `wave` reads.
- **Silence never reaches the provider.** `apps/ingestion/audio.py` refuses a segment whose loudest
  half second is below `TRANSCRIPTION_SILENCE_DBFS` before any call, because Whisper invents text
  from silence. What it sends is a WAV rebuilt from exactly the frames it measured.
- **Attempts:** `MAXIMUM_TRANSCRIBE_ATTEMPTS` (1 initial call + 2 retries) for a transport failure,
  a 5xx, a 429 or a 200 with no text; any other 4xx is `ProviderRefused` at once (D-118). Each
  failed attempt is logged under the step `transcription`.
- **Health** is FLM's model list answering within `HEALTH_TIMEOUT_SECONDS`. It cannot show that
  Whisper is loaded: FLM's `/v1/models` lists its chat catalogue and names neither
  `whisper-v3:turbo` nor `embed-gemma`. A server started without `--asr 1` fails the first segment.

Nothing returned is indexed. The page assembles the text into a draft that a person reviews, and
the confirmed draft goes in through FR-09's `POST /api/meetings`.

---

## 6. Testing

Tests never reach a live FLM server. Inject a stub `AIService` returning fixed
vectors and fixed statement lists, so the suite passes in CI and on a machine with no
NPU. Provider-specific behaviour — JSON repair, retry, the 503 path — is tested
against recorded responses, including deliberately malformed ones.

Enforced, not just stated: an autouse fixture in `conftest.py` points `FLM_BASE_URL`,
`VOYAGE_BASE_URL` and the Anthropic SDK at a closed loopback port and blanks every API
key for the whole suite, so an accidental live call fails with a connection error
instead of quietly succeeding against a developer's running server. The same fixture
sets `TRANSCRIPTION_PROVIDER` to `none` whatever a developer's `.env` says; a test that needs
transcription on says so. The stub's `transcribe` returns a numbered text per segment
(`stub_transcript_text`), and `transcription=` overrides it as `classification=` does.

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
