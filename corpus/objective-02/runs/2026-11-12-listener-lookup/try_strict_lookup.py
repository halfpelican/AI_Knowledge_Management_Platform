"""A trial of scripts/server_record.py's stricter listener lookup on this laptop (D-87's note of 12 November 2026).

Three stages, each on a scratch loopback port, with listeners this process starts and stops:

1. **One listener,** ``python -m http.server``. Each lookup on its own, ``sole_owner`` on what the
   fallbacks read, and ``listening_process``.
2. **A second listener on the same port,** where Windows lets it bind (Python's HTTP server asks
   for SO_REUSEADDR). The same again. This is the state the requirements audit of 12 November
   found the lookup merged on 11 November could pass (its finding B1).
3. **Both stopped:** ``listening_process`` again, which waits for its retries.

It touches no database, no project server and no process it did not start. A listener is stopped
by terminating the process it started. If a scratch listener is still on the port after that, it
is stopped by PID, and only when its command line is this script's own ``http.server`` command for
this port. Standard library only.

Usage, from the repository root, in PowerShell::

    & $py corpus\\objective-02\\runs\\2026-11-12-listener-lookup\\try_strict_lookup.py 8768
"""

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]  # corpus/objective-02/runs/<this folder>/<this file>
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))
import server_record  # noqa: E402


def say(text: str) -> None:
    print(text, flush=True)


def start(port: int) -> subprocess.Popen:
    child = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        if child.poll() is not None:
            break
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2).read(1)
            break
        except OSError:
            time.sleep(0.2)
    time.sleep(1.5)
    say(f"started child pid {child.pid}: {'still running' if child.poll() is None else f'exited with {child.returncode}'}. "
        "(A venv's python.exe is a launcher, so the process that listens can be its child.)")
    return child


def look(port: int, label: str) -> None:
    say(f"--- {label} ---")
    row = server_record._listen_row_process(port)
    say(f"  1. Listen row : {json.dumps(row)[:300]}")
    netstat_pids, netstat_error = server_record._netstat_listening_pids(port)
    say(f"  2. netstat    : LISTENING pids {sorted(netstat_pids)}" + (f"; {netstat_error}" if netstat_error else ""))
    owners, rows_error = server_record._port_row_owners(port)
    for owner in owners:
        say(f"  3. port's row : pid {owner['pid']}, states {owner['states']}, command "
            f"{str(owner['command'])[:110]!r}")
    if not owners:
        say(f"  3. port's row : no live owner" + (f"; {rows_error}" if rows_error else ""))
    taken, why, seen = server_record.sole_owner(port, netstat_pids, netstat_error, owners, rows_error)
    say(f"  sole_owner    : {'pid ' + str(taken['pid']) if taken else 'nothing taken'}; candidate seen {seen}; {why}")
    started = time.monotonic()
    found = server_record.listening_process(port)
    say(f"  listening_process: pid {found['pid']}, found_by {found['found_by']!r}, note {found['note']!r}, "
        f"{len(found['lookup'])} tries, in {time.monotonic() - started:.1f} s")


def stop(children: list[subprocess.Popen], port: int) -> None:
    for child in children:
        child.terminate()
        try:
            child.wait(timeout=20)
        except subprocess.TimeoutExpired:
            say(f"child pid {child.pid} did not exit within 20 s")
    time.sleep(1)
    own_command = f"-m http.server {port} --bind 127.0.0.1"
    owners, _ = server_record._port_row_owners(port)
    for owner in owners:
        if owner["command"] and own_command in owner["command"]:
            say(f"scratch listener pid {owner['pid']} outlived its launcher; stopping it by PID")
            os.kill(owner["pid"], signal.SIGTERM)
    say("listeners stopped")


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8768
    say(f"port {port}, platform {sys.platform}, python {sys.version.split()[0]}")
    if server_record._port_row_owners(port)[0]:
        say("REFUSED: something already owns a row on this port; choose another.")
        return 2
    children = []
    try:
        children.append(start(port))
        look(port, "one listener")
        children.append(start(port))
        look(port, "a second listener started on the same port")
    finally:
        stop(children, port)
    look(port, "both stopped (this waits for the retries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
