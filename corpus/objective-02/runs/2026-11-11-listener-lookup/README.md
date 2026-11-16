# The listener lookup tried on the laptop, 11 November 2026

Three trials of `scripts/server_record.py`'s `listening_process` against a real listener, for D-87's
note of 11 November. Each started `python -m http.server` on a scratch loopback port, looked it up
while it answered, stopped it, and looked again. No database and no project server was involved.

**What they show:**
- **With the fault present** (trials 1 and 2), the Listen row and netstat did not name the listener,
  and the port's own socket row did. The lookup found it by that row.
- **After the laptop restarted at 17:07** (trial 3), the fault did not show, and the lookup found
  the listener by its Listen row, as it always had.
- **With nothing listening,** the lookup says so after its retries, in 51 to 54 s.

**Only trial 3 has a console file.** Trials 1 and 2 were run from the session's scratchpad while the
change was being written, and their output was not teed. The figures below for those two are quoted
from the session's console.

| | Trial 1 | Trial 2 | Trial 3 |
|---|---|---|---|
| when (local) | 14:42 | 14:44 | 19:15 |
| laptop up since | 9 November | 9 November | 17:07 that day |
| port | 8765 | 8766 | 8767 |
| the script | a draft | as committed in `421f9ed` | `421f9ed`, no uncommitted tracked changes |
| console | not kept | not kept | `console.txt` |

## Listener answering

| Lookup | Trial 1 | Trial 2 | Trial 3 |
|---|---|---|---|
| 1. Listen row | **PID 0**, no command line | nothing | the listener's PID |
| 2. `netstat -ano` | **PID 0** LISTENING | no line | the listener's PID |
| 3. the port's own row | the listener's PID, state 0 | the listener's PID, state 0, then 1 | the listener's PID, state 2 |
| `listening_process` found it by | the port's row, in 4.5 s | the port's row, in 2.8 s | the Listen row, in 1.5 s |

State 2 is Listen. State 0 is undefined and 1 is Closed.

## Listener stopped

| | Trial 1 | Trial 2 | Trial 3 |
|---|---|---|---|
| what the tries saw | a Listen row naming **PID 0** | nothing on tries 1 to 4; on try 5 a Listen row and a netstat line naming **PID 0** | nothing on any of 5 tries |
| `listening_process` returned | PID 0 at once, in 2.7 s | PID 0, no command line, credited to no lookup, after 53.8 s | "nothing is listening", after 50.8 s |

## What changed because of trial 1

The draft took any Listen row that named a PID. Trial 1 showed that Windows can leave, or show, a
Listen row owned by PID 0, which is not a process. The draft returned it at once.

The committed lookup takes a Listen row only when its process's command line can be read, as the
run-folder copy that NFR-08's run 6 ran with did (#88). So a row naming PID 0 does not end the
search, and the retries still run. `test_a_listen_row_and_a_netstat_line_naming_pid_0_do_not_end_the_search`
holds that.

## What this does not show

- **The committed script against the fault, with a console on file.** Trial 2 ran the script as
  committed, since it was not edited between that trial and `421f9ed`, but its console was not
  kept. By trial 3 the fault had gone.
- **Whether a restart clears the fault,** or for how long. It is one observation.
- **Waitress or `run.ps1`.** The listener here was Python's `http.server`. NFR-08's run 6 is the
  record of the same lookup with Waitress and `run.ps1` (#88).

## Files

- `try_listener_lookup.py`: the trial, committed before trial 3 ran (`421f9ed`).
- `console.txt`: trial 3.
