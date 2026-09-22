# FLM citation baseline

Stage 4 item 0 of `M6-BUILD-PROMPT.md`, run before any retrieval code exists, to
establish whether the provider's structured output is reliable enough to build
FR-12 on. Produced by `scripts/citation_harness.py`.

> **The three rates below were measured against an index that no longer exists.**
> Stage 4 item 2a adopted EmbeddingGemma's task prefixes on 23 September 2026 and
> re-indexed the corpus (D-38), so every vector behind the numbers in "The three
> rates" and in "Tuning RELEVANCE_THRESHOLD" was rebuilt. The score distributions are
> re-measured in "23 September 2026 — adopting the task prefixes" below. The three
> rates themselves are re-measured against the real pipeline at Stage 4 item 6, not
> here; treat the figures in the next two sections as the go/no-go evidence they were
> taken for and not as a description of the shipped system.

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
| Threshold used | **0.30** — see "Tuning RELEVANCE_THRESHOLD" |

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

`apps/core/constants.py` marks `RELEVANCE_THRESHOLD = 0.3`
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
sits clear of the scoped maximum. The constant is now 0.30 (D-37); this section
is the evidence for that decision, and both are void if the corpus, the embedding
prefixes or the FLM build change.

**The embedding prefixes changed on 23 September 2026, so this section is void by its
own last sentence.** The distribution above is superseded by the one in "23 September
2026 — adopting the task prefixes" below, which is the re-measurement D-37 required on
exactly this trigger. The value itself does not move: 0.30 admits 44/48 answerable
and 6/16 unanswerable on the rebuilt index, and still sits clear of the scoped
maximum. The table is left here as written rather than edited in place, because it is
the evidence D-37 was decided on and rewriting it would leave that decision citing
numbers nobody ever measured.

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
twice and require a cosine near 1.0. `scripts/check_flm.py` originally passed on a
broken version, because its sanity check was "vectors are non-zero and differ
between the two inputs", which noise satisfies trivially. That single missing
assertion is why this went undetected from Stage 0 until the harness ran.

It is no longer missing. `check_flm.py` now asserts determinism at
`DETERMINISM_TOLERANCE = 0.999`, both for the same input twice within one request
and for the same input across two separate requests — the second catching a server
that is deterministic within a batch but not between calls — and then checks that
two unrelated inputs still discriminate.

The assertion was added and exercised **before** the downgrade, which is what makes
it worth anything:

| | v1.0.6 (broken) | v0.9.39 (good) |
|---|---|---|
| same input, one batch | — | 1.0000 |
| same input, two calls | 0.0939 — **failed** | 1.0000 |
| two unrelated inputs | — | 0.1299 |

A check that has only ever passed does not evidence that it can fail. This one has
a demonstrated failure mode on a version known to be broken, so the pass on v0.9.39
means something.

`python manage.py reindex --provider <name>` now exists and is what rebuilds the
corpus after a version or provider change.

## Known caveats

- **These are local-model baselines, not the platform's capability.** The
  proposal's production path is Claude plus Voyage. Do not present these numbers as
  what the system can do (`docs/ai-provider.md` section 7).
- **The corpus is a placeholder.** Six chunks over five sources is small enough
  that a single chunk's wording moves a rate by two percentage points. (The count
  read 9 between 22 and 23 September; it was corrected against `ContentChunk` and
  the rates above were measured on these 6 chunks — see D-37's erratum.) The rates
  are a go/no-go signal for building FR-12, not a quality measurement. Re-run
  against the real corpus when there is one; the question-set path is a CLI
  argument precisely so that replacement is a flag, not an edit.
- ~~**We do not send EmbeddingGemma's task prefixes.**~~ **Adopted on 23 September
  2026, and the explanation offered here was wrong.** This caveat used to read that
  the missing prefixes "likely explain why query-to-chunk scores (0.18–0.66) sit
  below chunk-to-chunk scores (mean 0.488)". They do not. The prefixes were adopted
  and the corpus re-indexed (D-38), and the answerable median moved from 0.3892 to
  0.3937 — **+0.0045**, which on this corpus is nothing. The query band is now
  0.22–0.69 rather than 0.18–0.66. Had the two-spaces hypothesis been the main cause,
  the query band would have moved substantially toward the chunk-to-chunk range; it
  did not, so whatever holds query-to-chunk scores below chunk-to-chunk scores is
  still unidentified. The prefixes are kept because the model is documented to expect
  them, not because they were measured to help. See the dated section below.
- **Conformance was measured on the happy path.** No malformed response occurred,
  so nothing here evidences the retry-then-503 behaviour NFR-19 requires.

## 23 September 2026 — adopting the task prefixes

Stage 4 item 2a. EmbeddingGemma is documented to expect a task prefix on each side of
a search — `task: search result | query: {content}` for a query and
`title: {title} | text: {content}` for a document. The project sent raw text in both
directions. `apps/ai/prefixes.py` now applies both, the corpus was re-indexed with
`manage.py reindex --provider flm`, and the harness was re-run over the same 64
questions, the same 6 chunks and the same 0.30 threshold. Settled as D-38.

**The hypothesis this change was built on is disproved.** The caveat above reasoned
that the missing prefixes likely explained why query-to-chunk scores sat below the
chunk-to-chunk mean. The answerable median moved **from 0.3892 to 0.3937: +0.0045.**
On a corpus where a single chunk's wording moves a rate by two percentage points that
is not a result at all. The gap between query-to-chunk and chunk-to-chunk scores has
some other cause, and this document no longer offers a candidate for it.

**The prefixes were kept anyway, and the reason is correctness of use rather than
measurement.** On 6 chunks and 64 questions every delta below is inside noise, so the
measurement cannot adjudicate the change in either direction. What is not inside
noise is that the model is documented to expect these prefixes and was previously not
being given them. "We use the model as documented" answers a question at the
demonstration; "we measured no difference on six chunks, so we kept the undocumented
usage" does not.

### The distributions, before and after

| | before | after | delta |
|---|---|---|---|
| ordinary (answerable), n=48 — min / median / max | 0.2192 / 0.3892 / 0.6607 | 0.2179 / 0.3937 / 0.6856 | −0.0013 / **+0.0045** / +0.0249 |
| scoped, n=8 — min / median / max | 0.1786 / 0.2522 / 0.2856 | 0.1982 / 0.2761 / 0.2947 | +0.0196 / +0.0239 / +0.0091 |
| no-answer, n=8 — min / median / max | 0.1795 / 0.4745 / 0.5348 | 0.2063 / 0.4452 / 0.5067 | +0.0268 / −0.0293 / −0.0281 |

At the settled 0.30 threshold:

| | before | after |
|---|---|---|
| answerable admitted | 41/48 (85.4%) | **44/48 (91.7%)** |
| unanswerable admitted | 5/16 (31.3%) | 6/16 (37.5%) |

**Three more answerable questions admitted for one more unanswerable one: a 3:1
recall-to-wasted-call trade.** An unanswerable question clearing the threshold is a
wasted NPU call that no-answer path B then catches; it is not a leak. A leak is
out-of-scope content reaching the prompt, which the role filter prevents before
ranking and which the harness asserts at zero on every question (invariant 1). The
two are worth keeping apart in the vocabulary, because one is a cost and the other
would be a failure.

That trade should improve the worst of the three baseline rates.
Empty-answer-where-available was 14.6% (7 of 48), and all seven were questions the
threshold excluded rather than questions generation declined. Four are now excluded,
which projects **14.6% → about 8.3% (4/48), down by a third.** It is a projection, not
a measurement: generation's behaviour on the three newly admitted questions is
unmeasured, and item 6 re-runs the full harness against the real pipeline to settle
it.

### Separation widened, and D-37's central finding still stands

The answerable maximum rose to 0.6856 while the unanswerable ceiling fell to 0.5067,
so the gap between them widened **from 0.126 to 0.179**. The most damaging kind of
overlap — an irrelevant passage outscoring the genuinely answerable range — got less
severe.

**It did not get less real.** 0.5067 still sits well above the answerable median of
0.3937, so a threshold high enough to exclude every unanswerable question still
discards most of the answerable ones: the first zero-admission row in the after sweep
is 0.52, which keeps 10 of 48. D-37's central finding is unchanged by this work — no
threshold separates answerable from unanswerable on this corpus — and invariant 7(b)
is still what does the work the threshold cannot.

### The scoped questions, and a margin worth watching

The scoped band rose: ceiling 0.2856 → 0.2947, median 0.2522 → 0.2761. This is not a
regression, and reading it as one would repeat the error D-37 already corrected: a
scoped question's top score measures the best of what the role filter *left*, not the
filter itself. The filter removed the Administrator-only content before ranking, so
the number describes the permitted remainder.

What it does affect is a margin. **The headroom between the scoped ceiling and the
0.30 threshold has fallen from 0.0144 to 0.0053.** Nothing depends on that headroom —
the role filter, not the threshold, is what keeps scoped content out, and a scoped
question crossing 0.30 would reach generation over permitted passages and return an
honest answer or an honest no-answer. But it is thin enough to be worth watching if
the corpus grows, because a scoped question scoring above the threshold is a question
whose permitted remainder looks relevant, and that is a retrieval-quality signal
rather than a security one.

### RELEVANCE_THRESHOLD is not re-tuned here

D-37 recorded that the value "is re-measured again if the EmbeddingGemma task
prefixes are adopted". **That trigger has now fired, and the sweep above is the
re-measurement.** It does not move the value: 0.30 still admits 91.7% of answerable
questions and still sits clear of the scoped ceiling at 0.2947. Re-tuning is
explicitly out of scope for Stage 4, and re-tuning against 6 chunks would in any case
be fitting a constant to a corpus nobody intends to ship.

The re-measure that matters is deferred to **Stage 5 item 3**, the end-to-end
integration pass over a real corpus, which is the first point at which the question
can be answered with evidence rather than with six chunks.

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
