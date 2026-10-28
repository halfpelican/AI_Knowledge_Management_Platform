"""Which HTTP server a measurement went through, observed where it can be (D-85). Standard library only.

D-85 decision 4: "Recorded beside every result: the server, its version and the thread
count." The measured run is served by

    waitress-serve --listen=127.0.0.1:8000 --threads=24 config.wsgi:application

Waitress answers no request with its thread count, so a client cannot ask it. The
operating system can say which process is listening on the port and with what command
line, and that command line carries ``--threads``. So the record is OBSERVED, not stated:

- the listening process and its command line, from ``Get-NetTCPConnection`` and
  ``Win32_Process`` (Windows, where the laptop runs; elsewhere the record says it was not
  looked up);
- the server and the thread count, parsed from that command line. A Waitress started
  without ``--threads`` runs Waitress's default of 4, and the record says so;
- the ``Server`` header of a reply, which Waitress sets to ``waitress``;
- the version, from the installed package in this process's environment. The runbook
  starts the server from the same venv, so it is the server's.

``problems()`` lists how a record differs from D-85's server. Scripts warn on it; the ones
that refuse do so only on a positive difference (another server, another thread count),
never on a lookup that failed, because a missing observation is not evidence.

Run on its own, it prints the record for a server at a URL::

    .venv\\Scripts\\python.exe scripts\\server_record.py http://127.0.0.1:8000
"""

from __future__ import annotations

import importlib.metadata
import json
import re
import subprocess
import sys
from urllib.parse import urlsplit

D85_SERVER = "waitress"
D85_THREADS = 24
D85_LISTEN = "127.0.0.1:8000"
D85_COMMAND = f"waitress-serve --listen={D85_LISTEN} --threads={D85_THREADS} config.wsgi:application"
WAITRESS_DEFAULT_THREADS = 4  # waitress.adjustments.Adjustments.threads
LOOKUP_TIMEOUT_SECONDS = 30

THREADS_PATTERN = re.compile(r"--threads(?:=|\s+)(\d+)")
LISTEN_PATTERN = re.compile(r"--listen(?:=|\s+)(\S+)")


def in_process(script: str) -> dict:
    """The record for a run that went through no server: the harness calls the pipeline itself."""
    return {
        "via": "in-process",
        "server": None,
        "version": None,
        "threads": None,
        "note": f"{script} calls the pipeline's functions in its own process; no HTTP server is involved",
    }


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def describe(command_line: str | None) -> dict:
    """The server, thread count and listen address a command line starts, as far as it says."""
    if not command_line:
        return {"server": None, "threads": None, "threads_source": None, "listen": None}
    lowered = command_line.lower()
    if "waitress" in lowered:
        server = "waitress"
    elif "runserver" in lowered:
        server = "django runserver"
    else:
        server = "unknown"
    threads = THREADS_PATTERN.search(command_line)
    listen = LISTEN_PATTERN.search(command_line)
    if threads:
        count, source = int(threads.group(1)), "--threads on the command line"
    elif server == "waitress":
        count, source = WAITRESS_DEFAULT_THREADS, "Waitress's default: no --threads on the command line"
    else:
        count, source = None, None
    return {
        "server": server,
        "threads": count,
        "threads_source": source,
        "listen": listen.group(1).strip("'\"") if listen else None,
    }


def listening_process(port: int) -> tuple[int | None, str | None, str | None]:
    """(pid, command line, note) of the process listening on ``port`` on this machine."""
    if sys.platform != "win32":
        return None, None, "the listening process is only looked up on Windows"
    script = (
        f"$c = Get-NetTCPConnection -LocalPort {int(port)} -State Listen -ErrorAction SilentlyContinue"
        " | Select-Object -First 1; if ($c) { $p = Get-CimInstance Win32_Process -Filter"
        " ('ProcessId=' + $c.OwningProcess); [pscustomobject]@{ pid = [int]$c.OwningProcess;"
        " command = [string]$p.CommandLine } | ConvertTo-Json -Compress }; exit 0"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=LOOKUP_TIMEOUT_SECONDS, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, None, f"the listening process could not be looked up ({type(exc).__name__})"
    output = (completed.stdout or "").strip()
    if completed.returncode != 0:
        return None, None, f"the process lookup exited {completed.returncode}"
    if not output:
        return None, None, f"nothing is listening on port {port}"
    try:
        found = json.loads(output)
    except ValueError:
        return None, None, "the process lookup printed something that is not JSON"
    return found.get("pid"), (found.get("command") or None), None


def observe(base_url: str, server_header: str | None = None) -> dict:
    """The server record for a run that goes through ``base_url``. Never raises."""
    parts = urlsplit(base_url)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    notes: list[str] = []
    local = parts.hostname in ("127.0.0.1", "localhost", "::1")
    pid = command = None
    if local:
        pid, command, note = listening_process(port)
        if note:
            notes.append(note)
    else:
        notes.append(f"{parts.hostname} is not this machine, so its process is not looked up")
    described = describe(command)
    server = described["server"]
    if server is None and server_header and "waitress" in server_header.lower():
        server = "waitress"
        notes.append("the server is named from its Server header only; its thread count is unknown")
    version = package_version("waitress") if server == "waitress" else (
        package_version("Django") if server == "django runserver" else None
    )
    return {
        "via": "http",
        "base_url": base_url,
        "server": server,
        "version": version,
        "version_source": "the installed package in this process's environment" if version else None,
        "threads": described["threads"],
        "threads_source": described["threads_source"],
        "listen": described["listen"],
        "pid": pid,
        "command_line": command,
        "server_header": server_header,
        "d85_command": D85_COMMAND,
        "notes": notes,
    }


def problems(record: dict) -> list[str]:
    """How ``record`` differs from D-85's server. Empty means it is D-85's."""
    found: list[str] = []
    if record.get("server") != D85_SERVER:
        found.append(f"the server is {record.get('server') or 'unknown'}, not {D85_SERVER} (D-85 decision 2)")
    if record.get("threads") != D85_THREADS:
        found.append(f"the thread count is {record.get('threads') or 'unknown'}, not {D85_THREADS} (D-85 decision 3)")
    header = record.get("server_header")
    if header and record.get("server") == D85_SERVER and D85_SERVER not in header.lower():
        found.append(f"the reply's Server header is {header!r}, so the reply did not come from Waitress")
    return found


def contradicts_d85(record: dict) -> list[str]:
    """The problems that are positive evidence of another server, not a failed lookup."""
    found: list[str] = []
    if record.get("server") not in (None, D85_SERVER):
        found.append(f"the listening server is {record['server']}, not {D85_SERVER} (D-85 decision 2)")
    if record.get("threads") is not None and record["threads"] != D85_THREADS:
        found.append(f"the server runs {record['threads']} threads ({record['threads_source']}), "
                     f"not {D85_THREADS} (D-85 decision 3)")
    header = record.get("server_header")
    if header and D85_SERVER not in header.lower():
        found.append(f"the reply's Server header is {header!r}, not Waitress's")
    return found


def summary(record: dict) -> str:
    """One line for a console header or a results file."""
    if record.get("via") == "in-process":
        return "none, in-process"
    threads = record.get("threads")
    return (f"{record.get('server') or 'unknown'} {record.get('version') or ''}".strip()
            + f", {threads if threads is not None else 'unknown'} threads"
            + (f" ({record['threads_source']})" if record.get("threads_source") else "")
            + (f", pid {record['pid']}" if record.get("pid") else ""))


def fetch_server_header(base_url: str) -> str | None:
    """The Server header of a GET of ``base_url``, error replies included; None if none came."""
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(base_url, timeout=LOOKUP_TIMEOUT_SECONDS) as response:
            return response.headers.get("Server")
    except urllib.error.HTTPError as exc:
        return exc.headers.get("Server")
    except (urllib.error.URLError, OSError):
        return None


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    base_url = arguments[0] if arguments else f"http://{D85_LISTEN}"
    record = observe(base_url, fetch_server_header(base_url))
    print(json.dumps(record, indent=2))
    for problem in problems(record):
        print(f"NOT D-85: {problem}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
