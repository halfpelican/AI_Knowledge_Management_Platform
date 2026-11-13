# The stricter listener lookup tried on the laptop, 12 and 13 November 2026

Four runs of `try_strict_lookup.py`, a trial of `scripts/server_record.py`'s `listening_process`
for D-87's note of 12 and 13 November. Each run starts `python -m http.server` on a scratch loopback
port, looks it up, starts a second listener on the same port, looks again, stops both and looks a
third time. One run of `check_rows_query.py`, below, ran the port's rows query alone. No database
and no project server was involved.

**The fault was absent in all of them.** The laptop had been up since 17:07 on 11 November, and every
socket row read state 2 (Listen). So these runs show the lookup with one and two healthy
listeners. They do not show it against the misreported state; the trials of 11 November
(`../2026-11-11-listener-lookup/`) showed that state, with the earlier lookup.

| | `console.txt` | `console-2.txt` | `console-3.txt` | `console-4.txt` |
|---|---|---|---|---|
| commit | `89f71f0` | `b40a425`, step 1 reads netstat | `79fe3d8`, step 1 reads netstat and the port's rows | `011d342`, nothing taken when either cannot be read |
| date | 12 November | 12 November | 12 November | 13 November |
| port | 8768 | 8769 | 8770 | 8771 |
| one listener | found by its Listen row, 1.2 s | found by its Listen row, 1.0 s | found by its Listen row, 1.8 s | found by its Listen row, 3.1 s |
| two listeners | **step 1 took one of them** | **nothing taken**, after six tries, 60.4 s | **nothing taken**, after six tries, 61.4 s | **nothing taken**, after five tries, 55.7 s |
| none | "nothing is listening", 59.6 s | "nothing is listening", 57.2 s | "nothing is listening", 57.4 s | "nothing is listening", 51.4 s |

**With two listeners on one address and port,** which Windows allowed:
- netstat listed both PIDs LISTENING;
- the port's CIM rows showed only one, because the two rows share one key;
- the Listen row named one of the two, and not the same one on every try (`console-2.txt`, tries 1
  to 6).

So in `console.txt` step 1 took whichever the Listen row named. From `b40a425` a Listen row is taken
only when netstat lists no other process listening on the port, and from `79fe3d8` only when the
port's own rows show none either. The one-listener lookup took 1.0 to 3.1 s across the four runs,
one sample each, so they do not measure what the extra reads cost. The tries on 13 November were
slower, so five fitted in the minute where six had.

No run had a lookup that could not be read, so nothing here shows the refusal on an unread source
(from `011d342`); the tests do.

## The rows query through real PowerShell, 13 November

No test runs the PowerShell itself. `check_rows_query.py` runs `_port_row_owners` for real on port
8772 at `011d342` (`rows-query-check.txt`):

| | exit code | printed | read as |
|---|---|---|---|
| nothing on the port | 0 | `[]` | no owner |
| one listener | 0 | its row, state 2 | that owner |
| a query that fails inside PowerShell (a CIM class that does not exist), as the script now has it | 3 | nothing | **unread** |
| the same failing query, as the script had it at `bbbda8c` (loaded from git) | 0 | `[]` | **no owner** |

The last row is the re-audit's finding on `bbbda8c`, which it found by reading the code: a failed
query read as "no rows".

## Files

- `try_strict_lookup.py`: the trial, committed before the first run (`89f71f0`) and unchanged since.
- `console.txt`, `console-2.txt`, `console-3.txt`, `console-4.txt`: the four runs.
- `check_rows_query.py`: the rows-query check, committed with its run (`rows-query-check.txt`).
