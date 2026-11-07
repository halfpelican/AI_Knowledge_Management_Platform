# Generation observed per attempt: 7 November 2026

Step 7, phase 1, of the user's post-M6 order: "Observe before changing anything: log each attempt's
finish_reason and completion-token count; reproduce the 503 on 'How are records managed and
retained?'". Nothing in how generation behaves was changed: `GENERATION_MAX_TOKENS` (800), the
prompt, the temperature (0.0), the attempt count (3) and the schema are as shipped. The note on D-82
dated 7 November 2026 records what this shows.

## What ran

| | |
|---|---|
| When (local, +11:00) | 16:22:09 to 16:51:56; the ranking check at 16:54:41 |
| Code | `4a37e4b` (main after #53) with this commit's four `apps/ai/` files in the working tree: `attempt_log.py`, `generation.py`, `flm.py`, `anthropic.py`, git blobs `fac39a9`, `9eb780c`, `4e091f4`, `b6aeb4c`. The commit records the same blobs. Nothing in the generation or retrieval path differs from NFR-08 run 3's `eed8249`; `apps/core/constants.py` differs by a permission code only |
| FLM | v0.9.39, CLI and server, `scripts/check_flm.py` passing at 16:22 (`check_flm.txt`). The server already running on 127.0.0.1:8625; it was not started or restarted for this |
| Database | `kmp_obj02_20261101`, the database NFR-08's runs used. 43 chunks, unchanged |
| How | In-process, no server: `observe_generation.py` calls the shipped `answer_question`, the way `tests/load/common.js` asks: an Employee (`loadtest01`), no conversation |
| Rows | Each ask ran inside `transaction.atomic()` and was rolled back. An answered ask inserts its `QueryLog` and `AnswerCitation` rows, and the rollback removes them; nothing was committed. Counts before and after: `QueryLog` 83, `AnswerCitation` 199, `Conversation` 3, `ContentChunk` 43 (`counts.json`) |

**The questions, in this order** (19 asks):

1. "How are records managed and retained?" (`QUESTIONS[3]`), 5 times;
2. three that NFR-08 answered: "What is the leave policy for annual leave?" (`QUESTIONS[0]`), "What are
   the rules for acceptable use of IT equipment?" (`QUESTIONS[1]`), "How do I make a complaint?"
   (`QUESTIONS[5]`);
3. `QUESTIONS[3]` 5 more times;
4. the three comparison questions twice more.

**What each attempt records** comes from two places, which agree on every attempt:

- the shipped attempt log's own line (`apps/ai/attempt_log.py`), with the logger lowered to INFO so
  parsed attempts are seen too. Verbatim in `generation_attempts.log`;
- a wrapper around `FLMService._chat_once` that records and changes nothing: the reply text and
  its SHA-256, and a SHA-256 of the messages sent, so identical prompts can be told from different
  ones. In `generation_attempts.jsonl`, one line per ask.

`summary.txt` is derived from the JSONL. `ranking_check.txt` is `check_ranking.py`'s output: the
question embedded five times, read only.

## What was observed

### Every attempt

| | Attempts | `finish_reason` | Completion tokens | `max_tokens` sent |
|---|---|---|---|---|
| Parsed | 23 | `stop` on 23 | 90 to 796 | 800 |
| Schema violation, "unbalanced JSON object in the response" | 15 | `stop` on 15 | **800 on all 15** | 800 |
| Call failed | 0 | | | |

- **`finish_reason` was `stop` on all 38 attempts. `length` was never reported,** including on the
  15 replies that ended at exactly 800 of 800 tokens with the JSON still open. A raw call earlier
  the same day did the same: `max_tokens` 20, 20 completion tokens, cut mid-list, `stop`.
- **Every failed attempt ended at exactly `max_tokens`, and every parsed attempt below it.**
- **No retry recovered an ask.** Every answered ask parsed on attempt 1. Every ask whose first
  attempt failed failed all three, so it was a 503.
- No timeouts and no FLM errors. No question-embedding attempt failed.

### Per question

| Question | Asks | 503 | Prompt tokens | Completion tokens, per attempt |
|---|---|---|---|---|
| Records (`QUESTIONS[3]`) | 10 | **4** | 5,671 | parsed 252 ×4, 442, 796; cut at 800 ×12 |
| IT equipment (`QUESTIONS[1]`) | 3 | **1** | 5,716 | parsed 336 ×2; cut at 800 ×3 |
| Leave (`QUESTIONS[0]`) | 3 | 0 | 5,182 | 101 ×3, the same text each time |
| Complaint (`QUESTIONS[5]`) | 3 | 0 | 1,416 | 90 ×3, the same text each time |

### The records question had two prompts

- **Asks 1 to 5 sent prompt A and asks 9 to 13 sent prompt B.** The two hold the same 8 passages,
  with the 6th and 7th swapped (`886a7e4a` and `5f0c9590`).
- **Those two passages score 0.545650 and 0.545642**, a gap of 0.000008 (`ranking_check.txt`).
- **At 16:54, five embeddings of the question were identical, and every one gave B's order.**
  Ranking is deterministic for a given vector, so during asks 1 to 5 the query vector was not the
  one embedded at 16:54. Its value then was not recorded.
- **Under prompt A:** 5 attempts, 5 parsed: 252 tokens (3 statements) four times with the same text,
  and 442 (5 statements) once. All 5 asks were answered.
- **Under prompt B:** 13 attempts, 1 parsed: 796 tokens, 10 statements (ask 9). The other 12 were
  cut at 800. 1 of 5 asks was answered.

### The failed replies

- **What they are.** Each is a statement list in a ```` ```json ```` fence, cut off at 800 tokens.
  The records replies have 10 complete statements, with an 11th opened or about to be. The IT
  replies have 7 or 8.
- **They are not one text cut at different points, and not one string repeating.** Under prompt
  B, all five distinct texts open with the same first statement, the first 296 characters. After
  that, any two share 296 to 2,058 of about 2,330 characters, then diverge at a word or a
  `chunk_id`. Ask 9's 796-token reply, which did close, shares 2,058 with ask 10's first attempt.
  The IT question's five texts share 547 to 775.
- **Most statements are distinct.** The attempt-2 replies restate two earlier statements, cited
  to a different `chunk_id`.
- **The fence.** All 38 replies, failed or parsed, were fenced in ```` ```json ````, which the
  parser strips.

### Retries at temperature 0

- **The text varies.** Under prompt B, 13 attempts gave 5 distinct texts. The IT question's one
  prompt gave 5 distinct texts in 5 attempts.
- **Each 503 ask's three attempts gave three different texts.** But asks 11, 12 and 13 gave the
  same three texts, in the same order. Ask 10's second and third matched them; its first did not.
- **Leave and complaint gave the same text every time.**

### Time per attempt

- **Uncontended:** 79.4 to 113.3 s for an attempt that reached 800 tokens, most of them 79 to 84 s,
  and about 41 s for a 252-token reply.
- **On 1 November,** run 3's uncontended failed attempts took 55.8 to 58.6 s.

## What this shows, and what it does not

**It shows:**

- **The 503 reproduces at one user, in-process, with nothing else asking:** 4 of 10 asks of the
  records question, and 1 of 3 of the IT question.
- **Every failure seen was a reply cut off at `max_tokens`:** 800 of 800 completion tokens, with
  the JSON not yet closed. "Unbalanced JSON object in the response" is that cut, as the parser
  reports it.
- **FLM v0.9.39's `finish_reason` does not show the cut.** The completion-token count does.
- **Retrying at temperature 0 changed the text but not the outcome.** No retry was shorter than the
  ceiling.
- **On the records question, the outcome followed the passage order.** Under A, 5 of 5 asks were
  answered. Under B, 1 of 5. The order was decided by a cosine gap of 0.000008.

**It does not show:**

- **What the 1 November replies were.** Their token counts were not recorded. The question, the
  code path and the violation message match. The time does not: 56 to 59 s then, against 79 to 113
  s for an 800-token reply today. So "cut off at 800 on 1 November" is still inferred, not observed.
- **Why identical requests got different replies, or why the query vector moved between asks 1 to 5
  and 16:54.** The repeat by attempt position is consistent with FLM's output depending on what it
  served before. This run did not isolate that.
- **Whether a higher `max_tokens`, or a shorter answer, would end the 503s.** The cut replies were
  still adding statements at 10 or 11. Nothing was changed to test it; that is phase 2.
- **That the comparison questions "normally succeed".** One of the three, the IT question, failed
  once in three.
