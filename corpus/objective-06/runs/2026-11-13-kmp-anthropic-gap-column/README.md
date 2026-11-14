# kmp_anthropic's gap column widened, and the survey behind D-117's note of 13 November 2026

`kmp_anthropic` was moved from FLM to voyage-4 with `reindex --resize-column` (D-122). That command
resized only the chunks' column, so FR-19's `knowledge_gaps.embedding` stayed `vector(768)` beside
chunks at 1024, and FR-19's cycle failed there (D-117's note of 12 November). The database is on the
never-write list. On 13 November 2026 the user approved this one statement (D-131, point 4).

| File | What |
|---|---|
| `survey.py` | Read-only, over every local `kmp*` database: both vector columns' widths, the chunks' embedding models, and the gap tables' rows. Every session is opened with `default_transaction_read_only=on`. |
| `survey-2026-11-13.txt` | Its output on 13 November 2026, before the alter, transcribed from the session's tool output. The console was not saved to a file then. |
| `survey-2026-11-14.txt` | Its output on 14 November 2026, captured: `kmp_anthropic` now has both columns at 1024, and `kmp_alpha_20261113` (D-131) has both at 1024 too. |
| `alter_gap_column.py` | The alter, as run at 16:17 on 13 November 2026. In one transaction it locks the table and checks four things: no row in it, the gap column `vector(768)`, the chunks' column `vector(1024)`, and every chunk `voyage-4`. Then it alters the column and reads the width back after the commit. Run again, it refuses, because the column is already 1024. |
| `console-2026-11-13.txt` | Its output, transcribed from the session's tool output. |

The alter ran at 16:17:19+11:00, and the transaction committed straight after. Nothing was lost,
because the table held no row.

**What the survey also found:** `kmp_obj05_d128_20261113`, the FR-10 session's, has chunks at 768 and
its gap column at 1024. A database restored from a dump made before FR-19's tables existed, then
migrated under a 1024 `.env`, would look like that. That is the session's inference: how it was made
is not recorded here. It is not this session's, and was left as it is.
