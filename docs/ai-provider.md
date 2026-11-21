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

Which provider is the default, and which one M8 runs on, is chosen by measurement. A database
keeps the provider it was set up with (§4, D-131).

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
    departments: tuple[str, ...]  # the active department list's names admitted for the audience (D-129)
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
    input_truncated: bool         # the classifier read only the opening, CLASSIFICATION_INPUT_TOKENS
    summary: str = ""             # D-139 — from a provider never empty, at most MAXIMUM_SUMMARY_CHARACTERS
    key_points: tuple[str, ...] = ()  # D-139 — from a provider 1 to MAXIMUM_KEY_POINTS strings
    summary_truncated: bool = False   # D-139 — more than MAXIMUM_SUMMARY_SECTIONS sections: only the first are summarised

@dataclass(frozen=True)
class Transcription:              # D-123 — one recording segment's text, a draft
    text: str                     # the speech model's text, stripped; may be empty
    model: str                    # FLM_ASR_MODEL, whisper-v3:turbo

class TranscriptionDisabled(ProviderUnavailable): ...  # TRANSCRIPTION_PROVIDER=none

@dataclass(frozen=True)
class SummaryElement:             # FR-16 — one narrative sentence, decision or highlight (D-125)
    text: str
    passages: tuple[int, ...]     # passage numbers as the reply gave them; NOT yet verified

@dataclass(frozen=True)
class ExtractedActionItem:
    description: str
    owner: str | None             # the name as the transcript gives it, or None
    due: str | None               # the deadline as said ("next Friday"), or None
    passages: tuple[int, ...]

@dataclass(frozen=True)
class MeetingSummaryDraft:
    narrative: tuple[SummaryElement, ...]     # 1 to MAXIMUM_SUMMARY_SENTENCES
    decisions: tuple[SummaryElement, ...]
    highlights: tuple[SummaryElement, ...]
    action_items: tuple[ExtractedActionItem, ...]   # may be empty; the key may not be missing
    model: str                    # the chat model that answered, for the summary's record

class MalformedSummary(ProviderUnavailable): ...  # two replies broke SUMMARY_SCHEMA (FR-16)

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
    def summarise_meeting(self, title: str, passages: list[str]) -> MeetingSummaryDraft: ...
```

The operations are the ones listed on `AIService`, and the list is the source of truth, not a
count. `classify_document` arrived with FR-10 on 9 November 2026 (D-104), when NIT3004 asked for
it; it lives in its own module, `apps/ai/classification.py`, so nothing in the generation prompt
or its loop changed for it — section 5b. `transcribe` and `transcription_health` arrived on 10
November 2026 with recording transcription (D-123), when the user asked for it — section 5c.
`summarise_meeting` arrived on 11 November 2026 with FR-16 (D-125), in its own module,
`apps/ai/summarisation.py` — section 5d.

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

Since D-139 (21 November 2026) the same operation returns the document's summary and key points,
and it is one operation that may make several requests. A text within
`CLASSIFICATION_INPUT_TOKENS` is one request. A longer text is one request per section and then
a final request, each with `MAXIMUM_CLASSIFY_ATTEMPTS` of its own. If any request uses its
attempts up, the operation raises `ProviderUnavailable` and returns nothing; a `ProviderRefused`
from any request is re-raised at once. No operation was added and the signature did not change
(section 5b).

`transcribe` raises `TranscriptionDisabled` before any call when `TRANSCRIPTION_PROVIDER` is
`none`, and otherwise `ProviderUnavailable` after `MAXIMUM_TRANSCRIBE_ATTEMPTS`, with a 4xx handled
as for generation (D-118). `POST /api/transcriptions` answers either with a 503 carrying its own
code. `transcription_health` never raises (section 5c).

`summarise_meeting` raises `ProviderUnavailable` after `MAXIMUM_SUMMARY_ATTEMPTS` failed calls,
`ProviderRefused` at once for a 4xx other than a 429 (D-118), and `MalformedSummary` after the
second reply that breaks `SUMMARY_SCHEMA`, because FR-16 allows a malformed response one retry
(section 5d). No route waits on it: the run is in the background, and the caller marks the
summary Unavailable and queues it for retry (NFR-20).

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
beside `gemma3:4b` and `embed-gemma` (`flm pull whisper-v3:turbo` first, 623 MB):

```powershell
flm serve gemma3:4b --embed 1 --asr 1
```

Measured on v0.9.39 on 6 November 2026: one server holds the chat, embedding and speech models, and
`scripts/check_flm.py` still passes with speech loaded. **Before starting a server, check for one
already running** (`Get-Process flm`): Windows lets a second `flm serve` process listen on 8625 beside the first at
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
3. The pgvector column dimension is `settings.EMBEDDING_DIMENSION`, never a literal, and
   `EMBEDDING_DIMENSION` follows `AI_PROVIDER` (`EMBEDDING_DIMENSION_BY_PROVIDER`, D-131). An
   `EMBEDDING_DIMENSION` in `.env` that disagrees is refused at startup (ai.E004).
4. A database keeps the provider it was set up with (D-131).
   - Migration 0002 sizes the column when it first runs, and nothing resizes it afterwards:
     `--resize-column` (D-117) was removed.
   - Changing provider means a new database, set up under that provider and ingested again.
   - Within one provider, `python manage.py reindex` rebuilds every chunk with the configured
     model, after a change of chunking or of the model at the same width.
5. A startup check compares `EMBEDDING_DIMENSION` against the dimension the provider
   actually returns for a probe string and refuses to start on a mismatch. Silent
   dimension drift is the failure this prevents. A second check compares the database's
   vector columns with `EMBEDDING_DIMENSION` and refuses a database set up for another
   provider (ai.E005). Rows embedded by another model are a warning (ai.W003).
6. The relevance threshold and the partial-match floor belong to the model too (D-120).
   `ranking.admit` and `partial_matches` are given the question's embedding model and look
   up its own values. A model that is not listed gets EmbeddingGemma's.

| Provider | Model | Dimension | Threshold / floor |
|---|---|---|---|
| `flm` | `embed-gemma` | 768 | 0.30 / none (D-102) |
| `anthropic` | `voyage-4` | 1024, Voyage's default. 256, 512 and 2048 are offered, never 768 (Voyage's API reference, checked 10 November 2026) | 0.2687 / 0.2468 (D-120) |

So the two providers never share a database. A Voyage database is set up under
`AI_PROVIDER=anthropic` from its first `migrate`, as the alpha's was on 13 November 2026 (D-131).

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
   reject anything still unparseable. What decoding refuses besides a syntax error is
   listed below.
4. Any response that does not parse into the schema is a **failed attempt**, retried
   up to `MAXIMUM_GENERATION_ATTEMPTS`, then 503. Never a partial answer.
5. If FLM exposes constrained decoding or a grammar option in a later release, use
   it and delete steps 2 and 3.

**What decoding refuses (13 November 2026).** All three parsers, for statements,
classification and summaries, decode through `loads_reply` in `apps/ai/schema.py`. Besides a
syntax error, it refuses four replies, each a violation with a fixed message that quotes
nothing of the reply:

- nesting past the decoder's limit, a few thousand levels (`RecursionError`);
- an integer literal past Python's 4,300-digit limit (`ValueError`);
- a string holding a NUL, which PostgreSQL text refuses;
- a string holding an unpaired surrogate, which neither the database nor DRF's renderer can
  encode as UTF-8.

Until then the first two escaped the attempt loops, and the last two failed wherever the string
was stored or rendered, which a statement or an element that verification discarded never is.
When either happened, the ask and classify routes answered 500 instead of NFR-19's 503, and a
meeting summary's run ended as "error" in the background runner, or stopped
`retry_meeting_summaries` or `summarise_meetings` outright.

Since 21 November 2026 the classification and section parsers also pass `unique_keys`, which
refuses an object that repeats a key (§5b). The statement and meeting-summary parsers do not.

**What the repairs leave alone (16 November 2026, D-136).** No repair touches text inside a JSON
string. Three backticks inside a string are not a code fence, and a comma before a closing bracket
or brace inside a string is not a trailing comma. A string is read as the object extraction reads
one: from a double quote inside braces to the next double quote that no backslash escapes. Before
that date, a reply that quoted a code block in a string was refused. A reply that needed the comma
repair had any "a, ]" in a string decoded as "a]". The trailing-comma repair is
`remove_trailing_commas` in `apps/ai/schema.py`; the regex it replaced, `TRAILING_COMMA_PATTERN`, is
gone.

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

Since 21 November 2026 (D-139) the same reply carries the document's **summary and key points**,
FR-10's "single structured request issued at upload returns the classification, the summary and
key points, and the tag assignments together, at the cost of one call rather than three". D-104
had deferred them. A document too long for one request is summarised in sections first; see
"Long documents" below.

**Required schema** (`CLASSIFICATION_SCHEMA`)

```json
{
  "doc_type":   {"value": "Procedure", "confidence": 0.92},
  "department": {"value": "Lantern Room", "confidence": 0.88},
  "tags": [
    {"dimension": "Process", "value": "wick trimming", "confidence": 0.9}
  ],
  "summary": "Each evening before the lamp is lit, the keeper trims both wicks and wipes the lens.",
  "key_points": ["The lens is wiped with a dry cloth."]
}
```

- Exactly five keys, three until D-139. `doc_type.value` **must be one of the scheme's `doc_types`** (DOCUMENT_TYPES:
  Policy, Procedure, Report, Meeting Paper), or the reply is a `SchemaViolation` — a type outside
  the fixed list is not a classification (invariant 10; FR-10: "selected from a fixed list rather
  than generated freely"). `department.value` is any non-empty string that decoding admits (§5:
  not one holding a NUL or an unpaired surrogate); whether it is in the scheme is decided in
  `apps/documents` (D-105), never by the provider.
- `tags` holds at most `MAXIMUM_TAG_SUGGESTIONS` (8) objects, each with `dimension` one of
  Project, Process or Topic, a non-empty `value` and a `confidence`. More than the cap is a
  violation, counted as returned; nothing is trimmed to fit.
- Every `confidence` is a number in [0, 1]. A string, a boolean or a number outside the range is a
  violation, not repaired.
- A tag with the same dimension and name as an earlier one, after `normalise_tag_name` (lower
  case, single spaces), is dropped and the first kept. That is a shape tolerance — two spellings of
  one tag are one suggestion — not a repair of content.
- `summary` (D-139) is a string of 1 to `MAXIMUM_SUMMARY_CHARACTERS` (600) characters, and
  `key_points` an array of 1 to `MAXIMUM_KEY_POINTS` (5) strings of 1 to
  `MAXIMUM_KEY_POINT_CHARACTERS` (200) characters each. Lengths are counted after surrounding
  whitespace is stripped. A missing key, an empty value, a value of the wrong type, an empty
  array, a sixth key point or one character too many is a violation. **Nothing is trimmed or
  repaired into shape:** an over-long summary is not cut and a sixth key point is not dropped.
  A summary or key point holding a NUL or an unpaired surrogate is refused at the decode step
  (§5), since neither can be stored.
- No violation's message quotes a summary or a key point: it gives a length or a position.
- An object that repeats a key, at the top level or nested, is a violation (21 November 2026,
  the review of D-139). json keeps the last of two equal keys, so a reply carrying an over-long
  `summary` and then a short one used to conform: a silent fourth repair. The refusal is
  `loads_reply`'s `unique_keys`, which only this parser and the section parser pass; its message
  is fixed and quotes nothing. The statement and meeting-summary parsers keep json's rule.

**Prompt strategy, in order** (`CLASSIFICATION_SYSTEM_PROMPT`, `build_classification_messages`)

1. A strict system prompt: JSON only; the type from the fixed list, copied exactly; the department
   from the listed departments; tags only from the values listed per dimension, except that a NEW
   Topic value may be proposed when no listed one fits — never a new Project, Process or
   department; at most eight tags; confidence as the model's honest estimate; no explanation.
   D-139 changed rule 2's count of keys, from three to five, and added rules 9 to 11 after rule
   8: the summary as one string of one to three sentences, the key points as one to five short
   sentences, and the grounding sentence. The header, rule 1, rules 3 to 8 and the example's
   declaration are word for word what they were, and
   `apps/ai/tests/test_classification_prompt.py` holds them to a copy of the earlier text. The
   reply's keys keep their order, the summary last, so the type, the department and the tags are
   written before a word of it.
2. One worked example whose subject (lighthouse keeping) and whose departments and tag values are
   alien to any organisation, for the reason the comment above `SYSTEM_PROMPT` in
   `apps/ai/prompting.py` records: a worked example is training data for the response, and this
   prompt carries no identifiers, so the lesson applies to content. The example's reply uses
   listed values only and proposes no new Topic — a demonstrated invention would be copied onto
   every document. The only values it shares with a real prompt are the four fixed types.
   `apps/ai/tests/test_classification_prompt.py` asserts the example's values appear in no real
   scheme (the corpus manifest) and in no real user turn. Since D-139 the example's reply also
   holds a summary and three key points about its lighthouse text: one sentence, well under the
   limits, and fewer key points than the cap, because a demonstrated count is copied too. Every
   word of them is a word of the example's text, but for three the test lists. The summary sets
   the text's statements side by side, as the text does, and gives no cause: until 21 November
   2026 it joined them with "because", a cause the text never states (the review of D-139).
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
What bounds it: the type is held to the fixed list by the parser, and the department and tag
values are held to the scheme by the application (D-105). A person does not confirm every
suggestion: a value in the scheme at or above its threshold (D-122, D-129) is applied **without**
a person's confirmation, so a steered suggestion can be applied, though only as a value the scheme
already holds. A value below its threshold, and a new Topic at any confidence, wait for a person.
Since D-139 the text that can try to steer the type, the department and the tags is not the
opening alone but the first `MAXIMUM_SUMMARY_SECTIONS` × `CLASSIFICATION_INPUT_TOKENS` tokens
(12,000), because a section's summary enters the final request.

**A summary has fewer bounds than a tag (D-139).** Nobody confirms a summary and nothing holds
its content to a list, so a body that instructs the model can put its own words beneath the
title. What bounds it: its length; that it is text; that it is display only, never embedded,
retrieved or matched by search, so it cannot reach an answer; that it is shown only where the
document itself is in scope; and the AI mark (NFR-15).

**Grounding** (`GROUNDING_SENTENCE`, D-139). FR-10: "the summarisation prompt constrains output
to content present in the document." One sentence, in both prompts, as rule 11 of the
classification prompt and rule 5 of the section prompt: "The summary and the key points state
only what the document's text says, with nothing from outside it". A test asserts it is in each.
**That is the whole of the grounding.** No code compares a summary with the text and no second
model call judges it: invariant 5's limitation, conceded the same way.

**Truncation** (`classification_input`). The model reads the title and the first
`CLASSIFICATION_INPUT_TOKENS` (1,500) whitespace tokens of the extracted text — D-31's token —
joined by single spaces. Whether anything was cut is returned as `input_truncated` on the
`DocumentClassification` and kept on the record rather than hidden. The cut is made by the
provider and again at the prompt boundary (it is idempotent), so no caller can send more. Since
D-139 the flag means the type, the department and the tags were chosen from the opening. The
rest of the text, up to `MAXIMUM_SUMMARY_SECTIONS` sections in all, is summarised in sections;
past them it is unread, and `summary_truncated` says so.

**Long documents** (`summary_sections`, `classify_and_summarise`, D-139). FR-10: "Documents
exceeding the model's context limit are summarised in sections and consolidated, rather than
being truncated and summarised from a fragment without the user being told." D-139 reads the
limit as `CLASSIFICATION_INPUT_TOKENS`, which did not change.

- **Within the cap: one request,** exactly as before D-139, whose reply now holds all five keys.
- **Past the cap: one request per section, then one final request.** `summary_sections` cuts the
  text into sections of `CLASSIFICATION_INPUT_TOKENS` tokens with no overlap, at most
  `MAXIMUM_SUMMARY_SECTIONS` (8). Each section goes out in order under
  `SECTION_SUMMARY_SYSTEM_PROMPT`, with the title and "Section n of m", and returns that
  section's summary and key points against `SECTION_SUMMARY_SCHEMA`: the same two keys under
  the same bounds, parsed by `parse_section_summary` with the same three repairs. A section is
  not classified. The final request is the classification prompt again; its user turn carries
  the title, the opening exactly as `classification_input` cuts it, each section's summary and
  key points in order, and an instruction to choose the type, department and tags from the
  title and the opening and to write the summary and key points from the section summaries.
- **So n sections are n + 1 requests,** each with its own `MAXIMUM_CLASSIFY_ATTEMPTS`: at most
  (8 + 1) × 3 = 27 calls for one document, one after another.
- **Past the ceiling the record says so.** A text of more than 8 sections (12,000 tokens) has
  only its first 8 summarised, and `summary_truncated` is True. A text of exactly 8 is
  summarised whole and is not flagged.
- **And so do the requests** (21 November 2026, the review of D-139). Until then the last
  section of a cut text was labelled "Section 8 of 8" and the final request asked for the
  document "as a whole". Now every "Section n of m", in a section's turn, in the final turn and
  in the attempt log, counts the document's real sections, ceil(tokens / 1,500): "Section 8 of
  20". The final turn carries `TRUNCATED_SECTIONED_NOTICE` and
  `TRUNCATED_CONSOLIDATION_INSTRUCTION` in place of `SECTIONED_NOTICE` and
  `CONSOLIDATION_INSTRUCTION`: the section summaries cover only the first 8 sections, the rest
  of the document was not read, and the summary must never present that part as the whole. A
  text within the ceiling is sent exactly what it was before, byte for byte.
- **A failure anywhere returns nothing.** No later section is sent and no final request is
  made, and the sections that did succeed are not turned into a result.
- **Both providers call `classify_and_summarise`,** passing only a function that makes one call
  with a system prompt and a user turn. They cannot differ in what they ask or how often, and
  `apps/ai/tests/test_classification_providers.py` compares them request for request.

**Retry policy** (`run_classification_attempts`): `run_generation_attempts`' exactly, with
`MAXIMUM_CLASSIFY_ATTEMPTS` (3) as the total — 1 initial call + 2 retries. A transport failure
or a 5xx is a failed attempt; a non-conforming reply is a failed attempt; a 4xx propagates after
one call and consumes no retry; after the last attempt, `ProviderUnavailable` naming the
provider and the last failure. Every attempt is recorded through `apps/ai/attempt_log.py` under
the step `classification`, at WARNING when it failed and INFO when it parsed, quoting nothing of
the reply. A section's request has the same policy through the same loop
(`run_section_summary_attempts`), recorded under the step `section summary` with the section
named. On FLM, `temperature` is 0.0 and `max_tokens` is `CLASSIFICATION_MAX_TOKENS`: 1,200 since
D-139, 400 before. The longest conforming reply, every limit filled, is about 920 tokens by
arithmetic (`apps/ai/classification.py` shows it); **no reply to this prompt has been counted on
gemma3:4b.** On Claude there is no sampling parameter, which current models refuse, and
`max_tokens` is `CLAUDE_MAX_TOKENS`, generation's Claude ceiling, because thinking counts against
it and FLM's ceiling could cut the reply off before its JSON (#67, D-115). Every call, a
section's and the final one, carries `CLASSIFICATION_TIMEOUT_SECONDS` (300). `model` on
the result is `FLM_CHAT_MODEL` or `ANTHROPIC_MODEL`, whichever answered.

**The stub** (`StubAIService.classify_document`). Deterministic and derived from the scheme: the
first document type, the first department (or `STUB_OUT_OF_SCHEME_DEPARTMENT` when the scheme
lists none), one tag per dimension that lists a value, every confidence `STUB_CONFIDENCE`,
`model` `STUB_CHAT_MODEL`, and the real `input_truncated`. Since D-139 also
`summary=stub_document_summary(title)`, `key_points=STUB_KEY_POINTS` (two strings) and the real
`summary_truncated`, from `summary_sections`; both names are importable from `apps.ai.testing`.
The stub is one call whatever the text's length. Every call is recorded in
`classify_calls`. A test overrides it with `StubAIService(classification=...)` or by setting the
`classification` attribute on the suite's stub: a `DocumentClassification` is returned as-is, a
callable is called with `(title, text, scheme)` and may raise `ProviderUnavailable` to stand in
for an outage.

**What has been measured.** Section 5's rates were established with `scripts/citation_harness.py`
before anything was built on them. The classification prompt's measurements are D-106's sweeps on
the development documents and Objective 05's runs:

- **On gemma3:4b:** the threshold of 0.95, and the runs in D-106's notes.
- **On claude-haiku-5-5:** the threshold of 0.72 (D-122), and three draws of Objective 05 (#85),
  all on this prompt.

*Dated note, 13 November 2026:* D-128 revised rules 6 and 7 for one day, and D-106's sweep ran on
that revision (`corpus/objective-05/runs/2026-11-12/dev-sweep-haiku-d127/`). D-129 reversed it,
so the prompt above is the one those measurements describe.

*Dated note, 21 November 2026 (D-139):* **every measurement above describes the prompt before
D-139.** Rule 2 changed, rules 9 to 11 and two reply keys were added, and FLM's reply ceiling rose
from 400 to 1,200. Rules 3 to 8 were kept word for word and the summary comes last in the reply,
to disturb the classification as little as a prompt change can; that is a precaution, not
evidence. One run has been made on D-139's prompt: Objective 05's check of 21 November 2026
(`corpus/objective-05/runs/2026-11-21-d139/`), one draw on claude-haiku-5-5, with all three
clauses met and nothing re-tuned. It is also the only run in which a model has answered a
section's request, or a final request carrying section summaries: one document of six sections
(D04), whose seven requests conformed at their first attempt, as every other request of that draw
did. It ran at `186be70`, before the worked example's summary was reworded that day (the review of
D-139), so it describes the prompt as it stood then. Not measured on either provider:

- whether the types, departments, tags and confidences come out as they did, which the
  thresholds depend on (0.95 on gemma3:4b; 0.72, and 0.30 for departments, on claude-haiku-5-5):
  D-106's sweep has not been run on D-139's prompt, nothing has been run on it on FLM, and one
  draw of Objective 05 is a check, not a re-derivation;
- the schema conformance rate of the five-key reply and of a section's reply, beyond that one
  draw's twenty and six requests, and how often a reply is refused over its summary or a key
  point running past its limit;
- a last section of fewer than `MINIMUM_CONTENT_LENGTH` (50) tokens, which a text 1 to 49 tokens
  past a multiple of `CLASSIFICATION_INPUT_TOKENS` sends, and which must still return 1 to 5 key
  points: no measured document has one (D04's last section is 857 tokens);
- on FLM, where `temperature` is 0.0 and a retry repeats the same request, whether a reply that
  breaks a limit recovers at all;
- how long a sectioned document takes: Objective 02's bound, a document of twenty pages or fewer
  processed within sixty seconds, and NFR-13's two minutes from upload to visible confirmation,
  each under sectioning. Both are being re-timed on anthropic; on FLM both are expected to be
  exceeded, and whether the final request's longer prompt fits `CLASSIFICATION_TIMEOUT_SECONDS`
  on the NPU is not known.

`scripts/classification_dev_sweep.py` measures nothing of a long document. Its development
documents are each within one request, at most 344 words, so it sends no section request, and it
records each document's result rather than each request's attempts.

---

## 5c. Recording transcription (D-123)

`apps/ai/transcription.py` holds the one call the FLM and Anthropic providers make, because Claude and Voyage have
no speech-to-text: a multipart POST to FLM's `/v1/audio/transcriptions` with `FLM_ASR_MODEL`,
`language=en`, `response_format=json` and the segment as a WAV part, carrying
`TRANSCRIPTION_TIMEOUT_SECONDS`. The FLM provider passes its own client; the Anthropic provider
builds an FLM client from `FLM_BASE_URL` only when the setting is `flm`.

- **One segment per call.** The page cuts a recording into WAV segments of at most
  `TRANSCRIPTION_SEGMENT_SECONDS` and sends them one at a time. The server never decodes MP4, M4A
  or MP3; it accepts only a 16-bit PCM mono WAV at 16 kHz, which Python's `wave` reads.
- **At most `MAXIMUM_TRANSCRIPTIONS_IN_FLIGHT` (2) calls at once** across the server, since FLM's one
  NPU takes them in turn; past that the route answers 429 `transcription_busy` before any call.
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

## 5d. Meeting summaries (FR-16, D-125)

`apps/ai/summarisation.py` holds the prompt, the schema, the tolerant parser and the attempt loop
for `summarise_meeting`, as `classification.py` does for FR-10. Both providers call the loop with
their one-call function (`_chat_once`, `_claude_once`), so the prompt strings are the same either
way.

- **One request returns everything:** FR-16's "single structured request returning both the
  summary and the action items against a defined schema rather than prose". The reply is one JSON
  object with exactly four keys: `summary` (1 to 6 narrative sentences), `decisions`, `highlights`
  and `action_items`. All four are required and the last three may be empty arrays, so a reply
  that omits the action-item section is a violation and one that lists none is a result (UC-04 A1).
- **The transcript is sent as numbered passages.** The caller passes FR-09's own chunks of the
  transcript, and the prompt heads them `[P1]` to `[Pn]`. Every element of the reply must carry
  `passages`, at least one label of the form `P<n>`: UC-04's "every element of the summary carries
  a reference to the passage of the transcript it was drawn from", as a schema rule.
- **The parser checks a label's shape and nothing else.** Whether that passage was sent is set
  membership, done by the caller in `apps/meetings/summaries.py`, as FR-12's citations are
  verified outside the provider (invariant 5). A label whose number is past Python's 4,300-digit
  limit cannot be read at all, and is a violation (13 November 2026).
- **The worked example's labels start at P41,** above the most passages any request carries
  (`SUMMARY_INPUT_TOKENS // CHUNK_SIZE + 1`, 21). A label copied from the example therefore names
  no real passage and verification drops it. An example using P1 would let a copied reference
  silently cite the real first passage. `build_summary_user_prompt` refuses more passages than
  that, so the guarantee is local.
- **Owners and deadlines are copied, never resolved.** The prompt tells the model to copy an
  owner exactly as the transcript names them, to take an "I'll" from the speaker's label, to leave
  the owner null where nobody is named, and to copy a deadline word for word. Matching the name to
  a user and converting the phrase to a date are application code (`apps/meetings/owners.py`,
  `due_dates.py`).
- **Untrusted text:** the label's header form inside a transcript or a title, `[P3]`, has its
  square brackets turned round, D-45's transformation. A transcript that instructs the model in
  prose can still steer the reply; what bounds it is the schema, the verified references, the
  user list, the date parser, and a person who can edit every action item and regenerate.
- **Attempts:** a failed call (a transport failure, a 5xx or a 429) is retried to
  `MAXIMUM_SUMMARY_ATTEMPTS`, 1 initial call + 2 retries. A malformed reply gets exactly one
  retry: the second is `MalformedSummary` even with an attempt left
  (`MAXIMUM_MALFORMED_SUMMARY_REPLIES`). Any other 4xx is `ProviderRefused` at once. Each attempt
  is logged under the step `summarisation` with the provider's token counts and no reply text.
- **Ceilings:** FLM takes `SUMMARY_MAX_TOKENS` (3,000); Claude takes `CLAUDE_MAX_TOKENS`, because
  its thinking counts against the ceiling (D-115). Both carry `SUMMARY_TIMEOUT_SECONDS` (600).

**Not measured on `gemma3:4b`, and Objective 04 not measured at all.** Only the development set
has been run, three draws on the `anthropic` provider, scored against a development reference
Claude wrote (`corpus/objective-04/runs/2026-11-11/`, which says it is not the objective's
result). Objective 04 waits for a reference set written by people (D-125). On FLM the prompt is a
first version with a tested parser and a tested retry path. A transcript near
`SUMMARY_INPUT_TOKENS` is a far longer prompt than anything FLM has been measured on here.

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

The stub's `summarise_meeting` returns one narrative sentence, one decision and one action item,
each citing a passage that was sent, so the default survives verification; `summary=` overrides it
with a draft or a callable. `conftest.py` also sets `SUMMARY_RUNNER` to `inline`, so a summary's
run happens in the test's own thread when the test executes the commit callbacks, and never in a
background thread that would outlive the test.

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
