# The HTTP check on Voyage with Claude: 10 November 2026

FR-13's three `http_check` threads, run through a server on the `anthropic` provider with D-120's
values. The comparison is FLM's HTTP check on 8 November (`../../2026-11-08/after-030/`). The
user approved the run after #75 merged (D-113). It is evidence for the provider decision, not
that decision.

**Shared by the run:**

- **Commit:** `58b9c27` on `feat/FR-13-voyage-http-check`, with no uncommitted tracked changes.
  That is `main` at `4c31d78` plus the commit that adds this folder's copy of the check.
- **Script:** `conversation_http_check_voyage.py`, a generated copy of
  `scripts/conversation_http_check.py` at `4c31d78`.
  - It changes only where FLM was named, and adds a per-thread jitter margin.
  - `conversation_http_check_voyage.diff` is the whole difference.
  - A provider gate replaces the `check_flm.py` gate. It passed.
- **Provider:**
  - Voyage `voyage-4` at 1024 embeds the questions.
  - Claude `claude-sonnet-5-5` generates (D-115).
  - The values are D-120's threshold 0.2687 and floor 0.2468.
- **The dump:** `80ff46d482d7d36029060e4afa2646ee9f07683331d35dbdb17b97fb6fc0d1e4`, database
  `kmp_voyage_20261110`. The corpus gate found exactly the manifest's 25 items.
- **The thread set:** `threads.json`, sha256 `acfe3d47…`, scoring rule v2, frozen and unedited.
- **The server:** D-85's command, `waitress-serve --listen=127.0.0.1:8000 --threads=24
  config.wsgi:application`.
  - It started fresh at 16:33:46, with `DATABASE_URL` set to the copy, the copy's media root,
    `AI_PROVIDER=anthropic`, `EMBEDDING_DIMENSION=1024` and `DEBUG=False`.
  - Its logs are in `C:\kmp-measurement\2026-11-10-voyage\logs\http-check\`.
  - The record names it Waitress 3.0.2 with `DEBUG` off, read from its replies.
- **The record holds the server's thread count and pid as unknown.**
  `scripts/server_record.py` finds the listener with `Get-NetTCPConnection -State Listen`. From
  inside the agent's sandbox, the listening socket's state does not read as Listen.
  - A first start from the Bash tool at 16:31 showed the same, and was stopped before any ask.
  - `server_observed.txt` holds the process's command line, read with `Get-CimInstance`. It shows
    `--threads=24`. The D-85 gate refuses only on positive evidence, so it did not refuse.
- **The accounts.** Throwaway passwords were set on `corpus.admin@example.com` and
  `corpus.employee@example.com` at 05:35:35Z.
  - They were generated in memory and passed to the check in its environment. They were never
    printed or written down.
  - At 05:36:43Z both accounts' original password hashes were written back.
  - The throwaway passwords no longer work, and neither does any session made with them: Django's
    session hash follows the password hash, and the API uses Django sessions (D-21).

## The result (`http_check.json`, 16:35–16:36)

| | FLM, 8 November | **Voyage + Claude** |
|---|---|---|
| verdict | WIRED 3/3 | **WIRED 3/3** |
| turn two correct, by the frozen rule | 1/3 (t04) | **3/3** |
| leaks | 0 | **0** |
| smallest gap between asks | 12.48 s | 7.0 s, the pacing floor |
| seconds per ask | 12.5 to 74.8 | 2.5 to 3.1, after a 13.2 s first ask |

- **t03, as the Employee** ("Which company handles our catering?", then "How do I place an
  order with them?"): turn two gave Ridgeline Catering's contact from the vendor register.
  FLM's turn two named another vendor, Lantern Grove.
- **t04, as the Employee** (the fleet vehicles, then "What records do they need to keep?"): the
  logbook rule, as on FLM.
- **t06, as the Administrator** (supplier reviews, then "Are we relying too heavily on just a few
  of them?"): "Three suppliers account for almost half of the organisation's spend", from the
  expected source. FLM found the same phrase but cited another source, which the rule scores as
  not correct.
- **Both rows of every thread hold the questions as asked** (D-42), and the thread reads back
  with two turns.
- **The server supplied exactly the passages in-process retrieval gives for the composed
  string,** in the same order.

## Voyage's jitter, and why the verdicts stand

Voyage is not bit-for-bit deterministic. Two passes over the frozen thirty differed by up to
0.00047 in 12 of 34 top scores (`../voyage-frozen/`). The original check relied on FLM's
determinism, so jitter can be wrong about a verdict in two ways:

- **A false MISMATCH:** a passage at the edge flips between the server's embedding and this
  process's. That did not happen. All three threads matched exactly, and a second in-process
  pass gave the same sets (`same_set_as_first_pass` in the record).
- **A false WIRED:** a server that ignored history happens to supply the composed set.
  `history_effect.py` measures how far the bare follow-up's ranking would have to move for
  that. The answer is 0.037 for t03, 0.217 for t04 and 0.222 for t06, against the 0.00094 that
  two jittered scores can move apart. **No WIRED verdict here can have come from the jitter.**

The margins in the record (`jitter`) show where the sets sit:

| thread | composed: margin, admitted / kept | bare follow-up: margin, admitted / kept |
|---|---|---|
| t03 | 0.0234, 1 / 1 | 0.0372, 0 / 0 |
| t04 | **0.0003**, 21 / 8 | 0.0012, 20 / 8 |
| t06 | **0.0004**, 22 / 9 | 0.0723, 0 / 0 |

- **The composed sets of t04 and t06 meet the context budget's cut within the jitter,** so their
  exact membership could differ between two embeddings. The server and both in-process passes
  agreed here.
- **The margin is conservative.** It counts any near-tie up to the cut, and a swap there changes
  the set only if it moves the cut.
- **A future run could show a MISMATCH** on t04 or t06 that is jitter, not wiring.
  `history_effect.py`'s reading tells the two apart.

## What the run wrote

- **To the copy, through the server:** 3 Conversation rows, 6 QueryLog rows and 11
  AnswerCitation rows, plus sessions and last-login times. None is a retrieval candidate
  (D-86 decision 6).
- **The corpus is unchanged:** 23 documents, 5 meetings and 43 chunks. The copy now differs from
  its snapshot only in those rows, the sessions, and the two accounts' last-login times. Their
  password hashes are the originals again.

## Spend

- **Claude:** 6 calls, all parsed on the first attempt, with 30,476 input and 845 output
  tokens. That is about $0.07 at D-115's prices. The counts are the server's attempt log's;
  the Console's figure governs.
- **Voyage:** this process's embeddings are on its free tokens. That is three per thread for
  the comparison, two per thread for the margins, and `history_effect.py`'s three.

## Not done here

Each needs the user's go-ahead:

- **NFR-08 on this provider.** Check the Console's rate limits first.
- **The provider decision.**

## Files

- `conversation_http_check_voyage.py`, `conversation_http_check_voyage.diff`: the copy that ran,
  and its whole difference from the original.
- `http_check.json`, `http_check.txt`: the record and the console.
- `history_effect.py`, `history_effect.txt`: the shift a history-blind server would need.
- `server_observed.txt`: the server's command line and start, read with `Get-CimInstance`.
- **The server's logs stay outside the checkout,** in
  `C:\kmp-measurement\2026-11-10-voyage\logs\http-check\`:
  - `waitress.log`, with both starts;
  - `attempts.log`, with the six attempts.
  - It has no `errors.log` and no `audit.log`. Nothing failed, and the audit logger records role
    changes only (`config/settings.py`), so signing in wrote no audit line.
- **This folder's `logs/` is the check process's own,** and git ignores it.
