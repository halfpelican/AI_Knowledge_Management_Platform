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

## 23 September 2026 — item 6, the first measurement of the shipped pipeline

Stage 4 item 6. Everything before this was measured with the harness's own prompt,
schema and parser; item 5 moved those into `apps/ai/`, so these runs measure the code
the application actually runs. Two runs, because the first found a defect in our own
prompt, which was fixed and re-measured once (D-39).

**Counts are given beside every rate.** At 38–44 statements a single event moves the
fabrication rate by more than two points, so a percentage alone overstates how much is
known — the same caution the 6-chunk corpus already earns.

| | baseline (prototype, pre-prefix) | item 6 before fix | item 6 after fix |
|---|---|---|---|
| Schema conformance | 100.0% (46/46) | **100.0% (50/50)** | **100.0% (50/50)** |
| First-attempt conformance | 100.0% | **100.0% (50/50)** | **100.0% (50/50)** |
| Fabricated identifiers | 2.4% (1 of 42) | **6.8% (3 of 44)** | **0.0% (0 of 38)** |
| Statements proposed / verified | — | 44 / 41 | 38 / 38 |
| Empty where an answer existed | 14.6% (7 of 48) | 18.8% (9 of 48) | **20.8% (10 of 48)** |
| Expected-answer match (diagnostic) | 72.9% (35/48) | 66.7% (32/48) | 70.8% (34/48) |
| Scoped correctly empty | 8/8 | **8/8** | **8/8** |
| No-answer correctly empty | 8/8 | **8/8** | **8/8** |
| **Out-of-scope in any prompt or answer** | 0 | **0** | **0** |

**Invariant 1 holds against the real retrieval path.** The baseline's zero was measured
over a candidate set the harness assembled itself; this one is measured through
`scoping.candidate_chunks`, over 64 questions in each run and 36 more in the stability
runs below. No out-of-scope identifier reached any prompt, statement or count in any of
them. The harness checks the *proposed* statements, not only the verified ones, so a
model naming a restricted chunk would be a finding even where verification then
discarded it.

### Two definitions of "answered", and which number compares with which

The harness's `answered` now means `bool(verified_statements)` — what
`RetrievalOutcome.answered` means, now that the harness runs the shipped pipeline. The
baseline meant "the model returned at least one statement", which counts an answer whose
every citation was fabricated as answered.

The new definition is the correct one and it stays. It also moves the number, so both
are recorded:

| | before fix | after fix |
|---|---|---|
| empty-answer, `bool(verified_statements)` (current) | 18.8% (9/48) | 20.8% (10/48) |
| empty-answer, baseline's "model returned at least one statement" | **12.5% (6/48)** | 20.8% (10/48) |

**12.5% is the figure comparable with the baseline's 14.6%, and it is lower.** 18.8%
against 14.6% is not like-for-like and must not be quoted as though it were. After the
fix the two definitions coincide, because nothing was fabricated for verification to
strip.

### What the D-38 projection got right, and what it got wrong

D-38 projected that empty-answer-where-available would fall to about 8.3% (4/48),
because the prefix change admitted 44 of 48 answerable questions instead of 41.

**The retrieval half was exactly right.** In both runs precisely 4 ordinary questions
took no-answer path A — q23, q25, q45, q47 — with top scores of 0.218 to 0.298 against
the 0.30 floor. That is 8.3%, question for question, in both runs.

**The generation half was wrong.** Every remaining empty answer is generation or
verification, not the threshold. Before the fix: 4 path A, 2 the model declined with
passages in front of it, 3 that lost every statement to verification. After: 4 path A,
6 declined, 0 lost to verification. The projection assumed generation would answer what
retrieval admitted; it does not always.

### The fabrication rose because of our own prompt, and the fix removed the mechanism

D-39 records the three fabrications. Two cited `8b5d04e2-…`, the *uncited* second
identifier from the worked example, while answering purchase-approval questions
correctly out of the real AUD threshold table: the example's subject matter collided
with the corpus. The third was a section heading lifted from a passage body.

After removing both halves of the cause — an alien example domain, and no uncited
identifier left to borrow — no identifier was invented across 64 questions, nor across
the 36 question-runs of the stability measurement. The three statements verification had
been correctly discarding are now correctly cited.

**This is not "fabrication is solved."** It is 0 of 38 on one run of a 6-chunk corpus,
the same n that D-37 says cannot adjudicate small differences.

## 24 September 2026 — measurement stability, and a threshold exposed

The fix appeared to cost four answers: q04, q06, q07 and q46 answered before it and
returned `{"statements": []}` after. Before attributing that to the prompt, the shipped
prompt was run again unchanged — 12 questions, the 4 that flipped plus 8 that did not,
chosen to span and interleave the same score band, three times, in three separate
processes, with nothing else altered.

**Different questions came back empty in different runs.** The empty sets were
{q06, q12, q14, q46}, then {q04, q12, q14, q46}, then {q04, q12, q14, q46} — q04 and q06
swap. The four-question regression is therefore largely a draw rather than a result:

| | across 3 runs | reading |
|---|---|---|
| q07 | answered 3 of 3 | its "loss" in the after-run was an unlucky draw |
| q04 | answered 1 of 3 | unstable |
| q06 | answered 2 of 3 | unstable |
| q46 | empty 3 of 3 | the only one with a claim to being a real change, and one question is not a finding |

For the other ten questions there was **no variance observed across 3 runs on 12
questions**, in statement count or in statement text — the verified statements are
character-identical, `chunk_id` included. That is an absence of observed variance on a
small sample. It is **not** evidence that generation is deterministic at temperature 0.
A check that has never failed cannot support that claim, which is the lesson this
repository paid the most for (D-36, and `check_flm.py` passing on a broken build).

### The cause is a threshold crossing, and the generator is not implicated

Both flips changed how many passages the question was given:

```
q04  run 1:    supplied 2  ->  answered     chunk fe61bb55 BELOW the floor
     runs 2,3: supplied 3  ->  empty        chunk fe61bb55 at 0.301412  (+0.0014)

q06  run 1:    supplied 3  ->  empty        chunk 39d5c220 at 0.300344  (+0.0003)
     runs 2,3: supplied 2  ->  answered     chunk 39d5c220 BELOW the floor
```

A passage sitting 0.0003 to 0.0014 above `RELEVANCE_THRESHOLD` crossed it, in opposite
directions on two questions. In both cases 2 supplied passages produced an answer and 3
produced an empty list — the same relationship both ways.

**Across 14 distinct (question, supplied-passage-set) groups, identical input produced
identical output every time.** Every difference observed traces to the input set
changing, not to the model's reply to a fixed input.

**About 6% of admitted passages are effectively coin flips.** In the item-6 run, 5 of 86
admitted passages sit within 0.005 of the 0.30 floor and three within 0.0017: q06
+0.00056, q12 +0.00070, q04 +0.00111, q08 +0.00157, q13 +0.00165. q04 and q06 are two of
those five, which is why they are the two that moved.

### An unexplained source of variation in query embeddings, which check_flm.py misses

Those scores move because the query vector moves, by roughly 1e-4 to 1e-3, on some
questions and not others. Reproduced independently while checking this write-up: q04's
top score was 0.358032 on one invocation of the real pipeline and 0.358459 on two
others.

**The trigger is not established, and two plausible ones were ruled out.** Embedding the
same four questions in three separate processes gave **bit-identical** vectors (maximum
elementwise difference 0.000e+00, cosine 1.000000000), so a process boundary alone does
not cause it. Interleaving a chat completion between two embeddings of the same question
inside one process also gave bit-identical vectors, so chat/embed alternation on the NPU
is not obviously the cause either. The pattern in every observation so far is that the
first run of a sequence differs and later runs agree, but what distinguishes that first
run is not known. It is recorded as unidentified rather than guessed at.

**`scripts/check_flm.py` asserts embedding determinism, passes, and does not catch
this.** It embeds one string twice within a request and once in a second request, and
requires cosine ≥ 0.999. The variation here is around 1e-4 — four orders of magnitude
inside that tolerance and invisible to it. That is not a fault in the check, which was
built to catch the v1.0.4 noise bug where a string scored 0.09 against itself; it is a
gap between what it proves and what retrieval needs at a threshold boundary.

**Why this is recorded now rather than when it bites.** Generation determinism on the
NPU was assumed and never measured until today, exactly as embedding determinism was
before D-36. If FLM output is not stable run to run, every rate in this document is one
draw from a distribution rather than a measurement — **including the first-attempt
conformance of 100%, which is what NFR-19's retry policy is reasoned from.** On the
evidence here the generator itself is not implicated: identical inputs gave identical
outputs in all 14 groups tested. The instability that was found lives in the query
embedding, and a threshold that a handful of real passages sit on is what turns it into
visible behaviour. Both remain open, and D-40 records them.

## The duplication is over — item 5 landed on 23 September 2026

This section used to record a deliberate, temporary copy: `scripts/citation_harness.py`
defined `STATEMENT_LIST_SCHEMA`, `SYSTEM_PROMPT` and `parse_statement_list()` itself,
because item 0 ran before item 5 existed and the three had to be iterated against a
live model without touching production code or its tests. The 23.8% → 2.4%
fabrication fix above is exactly that iteration, and it happened without a single
change under `apps/`.

**Its termination condition has been met.** Stage 4 item 5 moved all three, and the
harness now imports them and calls `FLMService.generate_statements()` rather than
building messages and making a raw chat call of its own.

| What | Where it lives now |
|---|---|
| `STATEMENT_LIST_SCHEMA`, `SchemaViolation`, `parse_statement_list()` | `apps/ai/schema.py` |
| `SYSTEM_PROMPT`, `build_user_prompt()`, `build_generation_messages()` | `apps/ai/prompting.py` |
| the attempt loop, `GENERATION_MAX_TOKENS`, `GENERATION_TIMEOUT_SECONDS` | `apps/ai/generation.py` |

The harness also gave up its own `cosine_similarity`, `rank`, `truncate_to_context`
and `count_tokens`, which now come from `apps/retrieval/ranking.py` and
`apps/ingestion/chunking.py`. It defines none of them.

**The note that used to live here is now an assertion.**
`apps/ai/tests/test_prompt_is_not_duplicated.py` reads the harness's *source text* —
not its imported namespace, since an imported name would satisfy a namespace check
while a copied literal sat beside it — and fails if any of the three is redefined
there. A second test asserts that nothing under `apps/` passes the `on_attempt`
observer, so the harness stays its only caller. An assertion in the suite outlives an
instruction in a document, which is the whole reason this section could be retired
rather than merely updated.

**What this buys the numbers above.** The prompt, the schema and the parser that
produced the three rates are now the ones the application runs, so the rates describe
the shipped system rather than a copy of it. The three units moved with only imports
and docstrings changed — no wording, no rule, no parser branch altered — so the
measurements above carry over by construction. Item 6 re-runs the harness against the
real pipeline and reports them again; until that run, the figures in "The three rates"
remain the last measurement, taken on the pre-prefix index (see the notice at the top
of this document).
