# FLM citation baseline

Stage 4 item 0 of `M6-BUILD-PROMPT.md`, run before any retrieval code exists, to
establish whether the provider's structured output is reliable enough to build
FR-12 on. Produced by `scripts/citation_harness.py`.

| | |
|---|---|
| Date | 22 September 2026 |
| Provider | `flm` (FastFlowLM, local, on the AMD Ryzen AI NPU) |
| **FLM version** | **v0.9.39 — see "The version this must be run on" below** |
| Endpoint | `http://127.0.0.1:8625/v1` |
| Chat model | `gemma3:4b` |
| Embedding model | `embed-gemma` (embeddinggemma-300m) |
| Embedding dimension | 768 |
| Corpus | the placeholder Meridian fixture set, 6 chunks, all recorded against `embed-gemma` |
| Question set | `scripts/citation_questions.json`, 64 questions |
| Constants | `TOP_K=25`, `MAXIMUM_CONTEXT_TOKENS=4000`, `MAXIMUM_GENERATION_ATTEMPTS=3` |
| Threshold used | **0.30**, not the constant's provisional 0.5 — see "Tuning RELEVANCE_THRESHOLD" |

## The three rates

| Rate | Result |
|---|---|
| **Schema conformance** | **100.0%** (46/46 responses), first-attempt 100.0% |
| **Fabricated-identifier rate** | **2.4%** (1 of 42 statements); 1.6% of questions (1/64) |
| **Empty-answer rate where an answer was in fact available** | **14.6%** (7 of 48 ordinary questions) |

46 of the 64 questions reached generation; the other 18 took no-answer path A and
called the provider zero times.

### The scoped and no-answer kinds, reported separately

An empty answer is the **correct** outcome for these, so folding them into the
empty-answer rate would measure the opposite of what that number is for.

| Kind | n | Correctly empty |
|---|---|---|
| scoped (answer exists, but only in a document the asking role cannot see) | 8 | **100%** (8/8) |
| no-answer (nothing in the corpus answers it, for any role) | 8 | **100%** (8/8) |

**Out-of-scope chunks appearing in any prompt or any answer: 0.** The harness
checks every question against the set of chunks the asking role may not see, and
asserts absence from both the passages supplied and the statements returned.

Diagnostic, not one of the three rates: the expected answer was found in 72.9%
(35/48) of ordinary questions, comparing with whitespace normalised on both sides.

## What the numbers say

**Conformance is the gate, and it passes outright.** `gemma3:4b` produced a
response conforming to `STATEMENT_LIST_SCHEMA` on the first attempt every single
time. The retry path and the NFR-19 503 were never exercised in this run, which is
a result about the happy path only — the retry policy still needs its own
fault-injection test, and that is Stage 4 item 5's work, not something this run
evidences.

**The two no-answer paths are both real, and path B earns its place.** Four
no-answer questions scored above the threshold and reached generation anyway; the
model returned `{"statements": []}` for all four. The threshold alone could not
have screened those out (see below), so path B is what caught them. That is
precisely the division of labour CLAUDE.md invariant 7 describes, observed rather
than assumed.

**Verification is not optional.** Even at 2.4%, identifiers that were never
supplied do come back, and the one that did was a well-formed UUID — exactly the
shape that looks legitimate to a human reading the answer. `verifyCitations()` is
what removes it, and it is application code checking set membership, never a
model judgement (invariant 5).

## Tuning RELEVANCE_THRESHOLD

`apps/core/constants.py` marks `RELEVANCE_THRESHOLD = 0.5` PROVISIONAL and names
this step as the one that settles it: "0.5 is a placeholder, not a measured value."
Reproduce the evidence with `python scripts/citation_harness.py --scores-only`.

Top-score distribution over the rebuilt corpus:

| Kind | n | min | median | max |
|---|---|---|---|---|
| ordinary (answerable) | 48 | 0.219 | 0.390 | 0.661 |
| scoped | 8 | 0.179 | 0.252 | 0.286 |
| no-answer | 8 | 0.180 | 0.474 | 0.535 |

Two conclusions:

1. **0.5 is far too strict.** It admits only 10 of 48 answerable questions, so the
   system would return no-answer on four fifths of the questions it can actually
   answer.
2. **No threshold separates answerable from unanswerable.** The no-answer set
   reaches 0.535, overlapping the top third of the answerable range. Excluding
   every unanswerable question needs 0.54, which discards 41 of the 48 real
   answers. The scoped questions are the clean case, topping out at 0.286 — but
   that is the *role filter* doing the work before ranking, not the threshold.

0.30 was used for this run: it admits 41/48 answerable and 5/16 unanswerable, and
sits clear of the scoped maximum. **The constant has not been changed.** Writing a
value into `apps/core/constants.py` is a decision for the coordinator, and this
document is the evidence for making it.

## The worked example was fabricating identifiers

First run of this harness measured a **23.8%** fabricated-identifier rate. The
cause was not the model: 9 of the 10 fabricated identifiers were `c_4471` or
`c_8802`, the two example IDs from the system prompt's worked example, and the
other two were the example's *shape* applied to real data (`c_` prefixed onto a
genuine UUID, and the literal string `chunk_id: 2`). The model was copying the
demonstration rather than the passages.

Replacing the example's short fake IDs with UUID-shaped ones, and stating
explicitly that the example identifiers appear nowhere in the real passages,
dropped the rate from **23.8% to 2.4%** with no other change. The single remaining
fabrication is still one of the example IDs, so the residual has the same cause and
is simply rarer.

This is worth recording because it is a general trap: a worked example is training
data for the response, and any identifier in it is a candidate for being cited.

## The version this must be run on

**FastFlowLM's `/v1/embeddings` is broken from v1.0.4 onward** — upstream issue
[ROCm/FastFlowLM#732](https://github.com/ROCm/FastFlowLM/issues/732), open at the
time of writing, and v1.0.6's release notes contain no embedding fix. On an
affected version the endpoint returns correctly-shaped, correctly-normalised
768-dimensional vectors that are **statistically uncorrelated with the input**:
the same string embedded twice scored between -0.05 and +0.80 against itself.

Nothing errors. The endpoint answers HTTP 200 for any model name at all — it
returned 768 floats for the *chat* model `gemma3:4b` — so a wrong configuration and
a right one are indistinguishable from the response. An index built on an affected
version is noise, and every similarity score computed from it is meaningless while
looking entirely plausible.

This corpus was rebuilt on **v0.9.39**, the last known-good version. Evidence that
the vectors are real this time:

- the same string embedded twice scores **1.000000** against itself;
- the two consecutive, 50-token-overlapping chunks of the Employee Handbook score
  **0.733**, against a cross-document mean of 0.488. On the broken version that
  same pair scored 0.099, *below* the 0.640 maximum between unrelated documents.

**Before trusting any embedding work, assert determinism** — embed one string
twice and require a cosine near 1.0. `scripts/check_flm.py` passes on a broken
version, because its sanity check is "vectors are non-zero and differ between the
two inputs", which noise satisfies trivially. That single missing assertion is why
this went undetected from Stage 0 until the harness ran.

`python manage.py reindex --provider <name>` now exists and is what rebuilds the
corpus after a version or provider change.

## Known caveats

- **These are local-model baselines, not the platform's capability.** The
  proposal's production path is Claude plus Voyage. Do not present these numbers as
  what the system can do (`docs/ai-provider.md` section 7).
- **The corpus is a placeholder.** Six chunks over five sources is small enough
  that a single chunk's wording moves a rate by two percentage points. The rates
  are a go/no-go signal for building FR-12, not a quality measurement. Re-run
  against the real corpus when there is one; the question-set path is a CLI
  argument precisely so that replacement is a flag, not an edit.
- **We do not send EmbeddingGemma's task prefixes.** The model is documented to
  expect `task: search result | query: …` for queries and `title: … | text: …` for
  documents. We embed raw text through one code path for both. This likely explains
  why query-to-chunk scores (0.18–0.66) sit below chunk-to-chunk scores (mean
  0.488). Adopting the prefixes would shift every score in this document and is a
  full re-index event; it has not been done and is not scheduled.
- **Conformance was measured on the happy path.** No malformed response occurred,
  so nothing here evidences the retry-then-503 behaviour NFR-19 requires.

## Temporary duplication — deliberate, and with an expiry

`scripts/citation_harness.py` currently defines three things that Stage 4 item 5
(FR-12 grounded generation) will own inside `apps/ai/`:

- `STATEMENT_LIST_SCHEMA` — the required response shape
- `SYSTEM_PROMPT` — strict instructions plus the worked example
- `parse_statement_list()` — the tolerant parser

They live in `scripts/` because item 0 runs **before** item 5 exists, which is the
whole point of the ordering: the schema, the prompt and the parser can be iterated
against a live model without touching production code or its tests. The 23.8% → 2.4%
fix above is exactly that iteration, and it happened without a single change under
`apps/`.

They are written as clean, liftable units with no harness-specific coupling, so item
5 can move them into `apps/ai/` verbatim.

**When item 5 lands, the harness must delete its copies and import from `apps/ai/`,
and call `FLMService.generate_statements()` instead of `build_generation_messages()`
plus a raw chat call.** Two definitions of the schema that drift apart would be
invisible until a citation silently stopped being verified — the same failure mode
as a front-end password rule drifting from `ComplexityValidator`, and harder to
notice. This note exists so that the duplication reads as a decision with a
termination condition rather than as a stray second implementation.
