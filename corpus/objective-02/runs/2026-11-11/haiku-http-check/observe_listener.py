"""Which process is serving port 8000, observed from the operating system, for server_observed.txt.

scripts/server_record.py finds the listener with ``Get-NetTCPConnection -State Listen``. On this
laptop that lookup has returned nothing for a Waitress that was answering, and once process 0
(D-112's note of 11 November 2026, section (c), defect 1; the NFR-08 runs under
../../2026-11-10-anthropic/nfr08/). So the HTTP check's record may hold the listener as unknown,
and this file records it beside the record, as server_observed.txt did on 10 November.

It reads, and changes nothing:

- every socket row on the port with remote port 0, whatever state Windows reports (2 is Listen),
  with its owning process. This is the port-row lookup of
  ../../2026-11-10-anthropic/load/server_record.py;
- each owning process's command line and start, from ``Win32_Process``, and its parents up to
  the shell that started it. The venv's ``waitress-serve.exe`` is a launcher: the process that
  listens is the base interpreter it starts, so ``--threads`` is read from the chain;
- what ``scripts/server_record.py``'s own lookup returns at the same moment;
- the Waitress log's last "Serving on" line.

Usage, with the server running:
    python observe_listener.py --waitress-log <the server's waitress.log> --out server_observed.txt
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parents[4]  # corpus/objective-02/runs/2026-11-11/<this folder>
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

import server_record  # noqa: E402  scripts/server_record.py

PORT = 8000
ROWS = (
    f"$rows = @(Get-CimInstance -Namespace root/StandardCimv2 -ClassName MSFT_NetTCPConnection"
    f" -Filter 'LocalPort={PORT} AND RemotePort=0' -ErrorAction SilentlyContinue | ForEach-Object {{"
    " [pscustomobject]@{ address = [string]$_.LocalAddress; state = [int]$_.State; pid = [int]$_.OwningProcess } });"
    " ConvertTo-Json -InputObject @($rows) -Compress"
)
PROCESS = (
    "$p = Get-CimInstance Win32_Process -Filter 'ProcessId={pid}'; if ($p) {{ $s = '';"
    " if ($p.CreationDate) {{ $s = $p.CreationDate.ToString('yyyy-MM-ddTHH:mm:ss.fffzzz',"
    " [Globalization.CultureInfo]::InvariantCulture) }}; [pscustomobject]@{{ pid = [int]$p.ProcessId;"
    " parent = [int]$p.ParentProcessId; name = [string]$p.Name; command = [string]$p.CommandLine; started = $s }}"
    " | ConvertTo-Json -Compress }}"
)


def powershell(script: str):
    completed = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                               capture_output=True, text=True, timeout=60, check=False)
    text = (completed.stdout or "").strip()
    return json.loads(text) if text else None


def process(pid: int) -> dict | None:
    return powershell(PROCESS.format(pid=int(pid)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--waitress-log", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.out.exists():
        print(f"REFUSED: {arguments.out} exists, and an observation is never overwritten")
        return 2

    lines = [f"Port {PORT}, observed at {datetime.now().astimezone().isoformat(timespec='seconds')} "
             "by observe_listener.py (read only).", ""]
    rows = powershell(ROWS) or []
    rows = rows if isinstance(rows, list) else [rows]
    lines.append(f"Socket rows on local port {PORT} with remote port 0 (state 2 is Listen): {len(rows)}")
    for row in rows:
        lines.append(f"  {row['address']}:{PORT}  state {row['state']}  owning process {row['pid']}")
    owners = sorted({row["pid"] for row in rows if row["pid"] > 4})
    for owner in owners:
        lines += ["", f"Owning process {owner}, and the processes that started it:"]
        pid, seen = owner, set()
        while pid and pid not in seen and len(seen) < 6:
            seen.add(pid)
            found = process(pid)
            if not found:
                lines.append(f"  pid {pid}: no longer running, or not readable")
                break
            lines.append(f"  pid {found['pid']} ({found['name']}), started {found['started']}, parent {found['parent']}")
            lines.append(f"    {found['command'] or '(command line not readable)'}")
            described = server_record.describe(found["command"])
            if described["server"] == "waitress":
                lines.append(f"    -> Waitress, {described['threads']} threads ({described['threads_source']}), "
                             f"listen {described['listen']}")
            pid = found["parent"]
    if not owners:
        lines += ["", "No live process owns such a row."]

    looked_up = server_record.listening_process(PORT)
    lines += ["", "scripts/server_record.py's own lookup (Get-NetTCPConnection -State Listen), at the same moment:",
              f"  pid {looked_up['pid']}, started {looked_up['started_at']}, note: {looked_up['note']}"]

    lines += ["", f"Waitress log ({arguments.waitress_log}), its 'Serving on' lines:"]
    try:
        serving = [entry for entry in server_record.read_waitress_log(arguments.waitress_log)
                   if entry["kind"] == "serving_on"]
        lines += [f"  {entry['line']}" for entry in serving] or ["  none"]
    except OSError as exc:
        lines.append(f"  could not be read ({exc})")

    text = "\n".join(lines) + "\n"
    arguments.out.write_text(text, encoding="utf-8", newline="\n")
    print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
