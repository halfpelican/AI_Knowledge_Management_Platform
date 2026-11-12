# The stricter listener lookup tried on the laptop, 12 November 2026

Three runs of `try_strict_lookup.py`, a trial of `scripts/server_record.py`'s `listening_process`
for D-87's note of 12 November. Each run starts `python -m http.server` on a scratch loopback port,
looks it up, starts a second listener on the same port, looks again, stops both and looks a third
time. No database and no project server was involved.

**The fault was absent in all three.** The laptop had been up since 17:07 on 11 November, and every
socket row read state 2 (Listen). So these runs show the lookup with one and two healthy
listeners. They do not show it against the misreported state; the trials of 11 November
(`../2026-11-11-listener-lookup/`) showed that state, with the earlier lookup.

| | `console.txt` | `console-2.txt` | `console-3.txt` |
|---|---|---|---|
| commit | `89f71f0` | `b40a425`, step 1 reads netstat | `79fe3d8`, step 1 reads netstat and the port's rows |
| port | 8768 | 8769 | 8770 |
| one listener | found by its Listen row, 1.2 s | found by its Listen row, 1.0 s | found by its Listen row, 1.8 s |
| two listeners | **step 1 took one of them** | **nothing taken**, after six tries, 60.4 s | **nothing taken**, after six tries, 61.4 s |
| none | "nothing is listening", 59.6 s | "nothing is listening", 57.2 s | "nothing is listening", 57.4 s |

**With two listeners on one address and port,** which Windows allowed:
- netstat listed both PIDs LISTENING;
- the port's CIM rows showed only one, because the two rows share one key;
- the Listen row named one of the two, and not the same one on every try (`console-2.txt`, tries 1
  to 6).

So in `console.txt` step 1 took whichever the Listen row named. From `b40a425` a Listen row is taken
only when netstat lists no other process listening on the port, and from `79fe3d8` only when the
port's own rows show none either. The extra read made the one-listener lookup about half a second
slower.

## Files

- `try_strict_lookup.py`: the trial, committed before the first run (`89f71f0`) and unchanged since.
- `console.txt`, `console-2.txt`, `console-3.txt`: the three runs.
