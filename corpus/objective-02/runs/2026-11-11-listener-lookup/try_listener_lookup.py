"""A trial of scripts/server_record.py's listener lookup on this laptop (D-87's note of 11 November 2026).

It starts ``python -m http.server`` on a scratch loopback port as a child of this process, shows
what each of the three lookups says while it answers, calls ``listening_process``, stops the
listener, and calls ``listening_process`` again. It touches no database, no project server and
no other process. Standard library only.

Usage, from the repository root, in PowerShell::

    & $py corpus\\objective-02\\runs\\2026-11-11-listener-lookup\\try_listener_lookup.py 8767

The second lookup waits for ``listening_process``'s retries, about a minute.
"""

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]  # corpus/objective-02/runs/<this folder>/<this file>
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))
import server_record  # noqa: E402


def show(label: str, found: dict, seconds: float) -> None:
    print(f"{label}: pid {found['pid']}, found_by {found['found_by']!r}, note {found['note']!r}, "
          f"started_at {found['started_at']}, command {str(found['command'])[:110]!r}, "
          f"{len(found['lookup'])} tries, in {seconds:.1f} s", flush=True)


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8767
    print(f"port {port}, platform {sys.platform}, python {sys.version.split()[0]}", flush=True)
    print(f"before: Listen row {server_record._listen_row_process(port)['note']!r}; "
          f"netstat {server_record._netstat_listening_pid(port)}", flush=True)
    child = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        answered = False
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2).read(1)
                answered = True
                break
            except OSError:
                time.sleep(0.2)
        print(f"listener started as child pid {child.pid}; it answers HTTP: {answered}. "
              "(A venv's python.exe is a launcher, so the process that listens can be its child.)", flush=True)
        print("each lookup on its own, while the listener answers:", flush=True)
        print("  1. Listen row :", json.dumps(server_record._listen_row_process(port))[:260], flush=True)
        print("  2. netstat    :", server_record._netstat_listening_pid(port), flush=True)
        owner, why = server_record._port_row_owner(port)
        print("  3. port's row :", (json.dumps(owner)[:260] if owner else None), "|", why, flush=True)
        started = time.monotonic()
        show("listening_process, listener answering", server_record.listening_process(port), time.monotonic() - started)
    finally:
        child.terminate()
        child.wait(timeout=20)
    time.sleep(1)
    print("listener stopped; listening_process again (this waits for its retries):", flush=True)
    started = time.monotonic()
    show("listening_process, listener stopped", server_record.listening_process(port), time.monotonic() - started)
    return 0


if __name__ == "__main__":
    sys.exit(main())
