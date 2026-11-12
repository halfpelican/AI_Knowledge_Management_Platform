"""Which HTTP server a measurement went through, observed where it can be (D-85, D-87). Standard library only.

D-85 decision 4: "Recorded beside every result: the server, its version and the thread
count." The measured run is served by

    waitress-serve --listen=127.0.0.1:8000 --threads=24 --max-request-body-size=54525952 config.wsgi:application

under ``DEBUG=False``. ``--max-request-body-size`` is D-124's ceiling on any request body: it does
not change what a measurement measures, and nothing here checks it. Waitress answers no request
with its thread count, so a client cannot ask it. The operating system can say which process is
listening on the port, with what command line and since when, and that command line carries
``--threads``. So the record is OBSERVED, not stated:

- the listening process, its command line and its start time, from ``Get-NetTCPConnection``
  and ``Win32_Process`` (Windows, where the laptop runs; elsewhere the record says it was not
  looked up). Windows can report a serving socket's state wrongly, so ``listening_process``
  reads ``netstat`` and the port's own socket rows as well as the Listen row. It takes a
  process only when that process alone holds the port, and tries again before it gives up
  (D-87's notes of 11 and 12 November 2026). The record says which lookup found the process;
- the server and the thread count, parsed from that command line. A Waitress started without
  ``--threads`` runs Waitress's default of 4, and the record says so;
- the version: the Waitress installed in the venv the command line runs from (the venv's
  ``Scripts\\waitress-serve.exe`` is on it), and where no venv can be read from it, the
  installed package in this process's environment. The record says which;
- the ``Server`` header of a reply, which Waitress sets to ``waitress``;
- ``DEBUG`` (D-87 decision 2): an unmatched ``/api/`` path is answered with handler404's JSON
  404 when ``DEBUG`` is off, and with Django's HTML debug page when it is on.

``problems()`` lists how a record differs from D-85's server. The scripts that observe the
server for themselves (the ingestion, the HTTP check) warn on it, and refuse only on a positive
difference (another server, another thread count, ``DEBUG`` on), never on a lookup that failed,
because a missing observation is not evidence. ``tests/load/run.ps1`` is stricter (D-87
decision 2): its pre-flight refuses unless the server is OBSERVED to be D-85's.

Run on its own, it prints the record for a server at a URL::

    .venv\\Scripts\\python.exe scripts\\server_record.py http://127.0.0.1:8000

``tests/load/run.ps1`` runs its two subcommands::

    server_record.py preflight --base-url URL --waitress-log FILE --results-dir DIR ...
                               --threads-stated N [--override-threads] --out FILE --env-out FILE
    server_record.py finalise  --preflight FILE --summary FILE --window-start ISO
                               --window-end ISO [--copy-to DIR]

- **preflight**, before k6: observes the server, confirms ``DEBUG`` off, reads the server's
  last start from Waitress's log, and compares it with the end of the last run recorded in the
  results folders (D-87 decision 1: the server is restarted before each run through HTTP). It
  prints ``PREFLIGHT: READY`` and exits 0 only when the run may start, and exits 2 otherwise.
- **finalise**, after k6: copies the log's "Task queue depth" lines from the run's window into
  the k6 summary, with every pre-flight observation (D-87 decisions 2 and 3), and marks the run
  INVALID if the server restarted during it or another process is listening at the end. It
  prints ``FINALISED:`` and exits 0, or exits 3 when there is no summary from this run.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path, PureWindowsPath
from urllib.parse import urlsplit

D85_SERVER = "waitress"
D85_THREADS = 24
D85_LISTEN = "127.0.0.1:8000"
# D-124: Waitress's ceiling on a request body, a copy of apps.core.constants.MAX_REQUEST_BODY_BYTES
# (this script imports nothing from the project). apps/api/tests/test_request_body_bound.py ties
# the two.
D85_MAX_REQUEST_BODY_BYTES = 54525952
D85_COMMAND = (
    f"waitress-serve --listen={D85_LISTEN} --threads={D85_THREADS} "
    f"--max-request-body-size={D85_MAX_REQUEST_BODY_BYTES} config.wsgi:application"
)
WAITRESS_DEFAULT_THREADS = 4  # waitress.adjustments.Adjustments.threads
LOOKUP_TIMEOUT_SECONDS = 30
# listening_process tries again this often, for about this long, before it gives up (D-87's notes
# of 11 and 12 November 2026). The values are the ones NFR-08's run 6 ran with.
LOOKUP_RETRY_SECONDS = 60
LOOKUP_RETRY_INTERVAL_SECONDS = 10
# Which lookup found the listening process: listening_process's ``found_by``.
FOUND_BY_LISTEN_ROW = "Get-NetTCPConnection -State Listen"
FOUND_BY_NETSTAT = "netstat -ano, a LISTENING line"
FOUND_BY_PORT_ROW = "the port's own socket row (remote port 0), whatever state is reported"

THREADS_PATTERN = re.compile(r"--threads(?:=|\s+)(\d+)")
LISTEN_PATTERN = re.compile(r"--listen(?:=|\s+)(\S+)")
# One token of a Windows command line: a quoted run, or a run of non-spaces.
COMMAND_TOKEN = re.compile(r'"([^"]*)"|(\S+)')

# --- DEBUG (D-87 decision 2) -------------------------------------------------------------
# A path config/urls.py does not match. With DEBUG off, Django answers it with handler404
# (apps/api/views.py not_found): status 404, application/json, exactly this body. With DEBUG
# on, Django bypasses handler404 and serves its HTML debug page, which says "DEBUG = True".
DEBUG_PROBE_PATH = "/api/__preflight_not_a_route__"
HANDLER404_BODY = {"detail": "Not found."}
DJANGO_DEBUG_PAGE_MARK = "DEBUG = True"
PROBE_READ_BYTES = 64 * 1024
DEBUG_OFF, DEBUG_ON, DEBUG_UNKNOWN = "off", "on", "unknown"

# --- Waitress's log (D-87 decision 3) ----------------------------------------------------
# Waitress 3.0.2 logs "Serving on http://host:port" (logger "waitress", INFO, from
# waitress/__init__.py serve() through server.print_listen) and "Task queue depth is N"
# (logger "waitress.queue", WARNING, from task.py ThreadedTaskDispatcher.add_task, when a
# request arrives and no thread is idle). apps/core/logging_config.py writes them as
#   2026-10-28 18:20:16,549 INFO waitress Serving on http://127.0.0.1:8000
#   2026-10-28 18:20:39,784 WARNING waitress.queue Task queue depth is 1
# The timestamp is local time with no zone, Python logging's default asctime. Parsed
# defensively: "T" or a space, "," or "." before the fraction, and a zone if one is ever
# added. A line with no timestamp at all (Waitress's own basicConfig format,
# "INFO:waitress:Serving on ...") is kept as untimed, never placed in a window.
LOG_TIMESTAMP = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})[ T](?P<time>\d{2}:\d{2}:\d{2})(?:[,.](?P<fraction>\d{1,6}))?"
    r"(?P<zone>Z|[+-]\d{2}:?\d{2})?(?=\s|$)"
)
SERVING_ON = re.compile(r"\bServing on (?P<url>https?://\S+)")
QUEUE_DEPTH = re.compile(r"\bTask queue depth is (?P<depth>\d+)\b")
# config/settings.py reads the server's log path from this variable.
WAITRESS_LOG_ENV = "WAITRESS_LOG_PATH"
# "Serving on" is logged after the process has started and imported the app, so it is never
# earlier than the listening process's own start. This allows for rounding between the two
# clocks' readings; a line earlier than that is not this process's.
PROCESS_START_TOLERANCE = timedelta(seconds=2)
# How far a k6 summary's finished_at may sit outside the run's window and still be this run's.
SUMMARY_TOLERANCE = timedelta(seconds=5)

READY_LINE = "PREFLIGHT: READY"
REFUSED_LINE = "PREFLIGHT: REFUSED"
FINALISED_LINE = "FINALISED:"
REFUSED = 2
NOT_MERGED = 3
INVALID_VERDICT = "INVALID RUN"
OBSERVED_BY = "scripts/server_record.py preflight, run by tests/load/run.ps1"

# No proxy for these requests: they are to a server on this machine, and a proxy set in the
# environment would answer for it.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


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
    # Waitress reads its options with getopt, so a --threads given twice takes the last.
    threads = THREADS_PATTERN.findall(command_line)
    listen = LISTEN_PATTERN.search(command_line)
    if threads:
        count, source = int(threads[-1]), "--threads on the command line"
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


def server_venv(command_line: str | None) -> Path | None:
    """The venv a command line runs from, or None if no token on it names one.

    A venv's ``waitress-serve`` (or its ``python``) sits in its ``Scripts`` folder (``bin``
    elsewhere), and the folder above that holds ``pyvenv.cfg``. On the laptop the listening
    process is the base interpreter, run by the venv's launcher as
    ``"<base python>"  "<venv>\\Scripts\\waitress-serve.exe" --listen=... --threads=...``, so the
    venv is read from the waitress-serve token, which is tried first.
    """
    if not command_line:
        return None
    candidates: list[Path] = []
    for quoted, bare in COMMAND_TOKEN.findall(command_line):
        token = quoted or bare
        path = PureWindowsPath(token) if "\\" in token else Path(token)
        if path.parent.name.lower() not in ("scripts", "bin"):
            continue
        name = path.name.lower()
        root = Path(str(path.parent.parent))
        if name.startswith("waitress-serve"):
            candidates.insert(0, root)
        elif name in ("python.exe", "pythonw.exe", "python", "python3"):
            candidates.append(root)
    for root in candidates:
        if (root / "pyvenv.cfg").is_file():
            return root
    return None


def venv_package_version(venv: Path, name: str) -> str | None:
    """``name``'s version as installed in ``venv``, read from its metadata, never imported."""
    folders = [venv / "Lib" / "site-packages", *sorted((venv / "lib").glob("python*/site-packages"))]
    wanted = name.lower().replace("_", "-")
    for folder in folders:
        if not folder.is_dir():
            continue
        for distribution in importlib.metadata.distributions(path=[str(folder)]):
            if (distribution.metadata["Name"] or "").lower().replace("_", "-") == wanted:
                return distribution.version
    return None


def _listen_row_process(port: int) -> dict:
    """The owner of ``port``'s Listen row, from ``Get-NetTCPConnection -State Listen``.

    ``listening_process``'s first lookup, and until 11 November 2026 its only one. ``pid``,
    ``command`` (its command line) and ``started_at`` (its start, UTC, ISO 8601), each None when
    unknown, and ``note`` saying why when the lookup itself failed.
    """
    found: dict = {"pid": None, "command": None, "started_at": None, "note": None}
    if sys.platform != "win32":
        found["note"] = "the listening process is only looked up on Windows"
        return found
    script = (
        f"$c = Get-NetTCPConnection -LocalPort {int(port)} -State Listen -ErrorAction SilentlyContinue"
        " | Select-Object -First 1; if ($c) { $p = Get-CimInstance Win32_Process -Filter"
        " ('ProcessId=' + $c.OwningProcess); $s = ''; if ($p -and $p.CreationDate) {"
        " $s = $p.CreationDate.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ',"
        " [Globalization.CultureInfo]::InvariantCulture) }; [pscustomobject]@{"
        " pid = [int]$c.OwningProcess; command = [string]$p.CommandLine; started = $s }"
        " | ConvertTo-Json -Compress }; exit 0"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=LOOKUP_TIMEOUT_SECONDS, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        found["note"] = f"the listening process could not be looked up ({type(exc).__name__})"
        return found
    output = (completed.stdout or "").strip()
    if completed.returncode != 0:
        found["note"] = f"the process lookup exited {completed.returncode}"
        return found
    if not output:
        found["note"] = f"nothing is listening on port {port}"
        return found
    try:
        reply = json.loads(output)
    except ValueError:
        found["note"] = "the process lookup printed something that is not JSON"
        return found
    if reply.get("pid") == 0:
        # Process 0 is Windows' System Idle Process. It listens on nothing, and its start is the
        # machine's boot. The HTTP check of 10 November 2026 recorded it as the server, with that
        # start (D-112's note of 11 November 2026, section (c), defect 1). It is not an observation.
        found["note"] = (f"the Listen row for port {port} names process 0, the System Idle Process, "
                         "which is not a server: the listening process is unknown")
        return found
    found.update(pid=reply.get("pid"), command=reply.get("command") or None,
                 started_at=reply.get("started") or None)
    return found


def parse_netstat_listening(text: str, port: int) -> set[int]:
    """The PIDs ``netstat -ano`` lists as LISTENING on TCP ``port``, IPv4 or IPv6."""
    pids: set[int] = set()
    for line in text.splitlines():
        parts = line.split()
        # TCP    127.0.0.1:8000    0.0.0.0:0    LISTENING    46608
        if (len(parts) >= 5 and parts[0].upper() == "TCP" and parts[3].upper() == "LISTENING"
                and parts[1].rsplit(":", 1)[-1] == str(int(port)) and parts[4].isdigit()):
            pids.add(int(parts[4]))
    return pids


def _netstat_listening_pids(port: int) -> tuple[set[int], str | None]:
    """The PIDs netstat lists as LISTENING on ``port``, and why not when netstat could not be run."""
    try:
        completed = subprocess.run(["netstat", "-ano"], capture_output=True, text=True,
                                   timeout=LOOKUP_TIMEOUT_SECONDS, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return set(), f"netstat could not be run ({type(exc).__name__})"
    return parse_netstat_listening(completed.stdout or "", port), None


def _port_row_owners(port: int) -> tuple[list[dict], str | None]:
    """Every live process that owns a remote-port-0 row on ``port``, whatever state is reported.

    Returns ([{pid, command, started_at, states}, ...], None), or ([], why) when the rows could
    not be read. ``command`` is None for a process whose command line cannot be read: it is still
    an owner, and still counts (D-87's note of 12 November 2026). Two kinds of row are left out,
    because neither names a process: one owned by PID 0, and one whose owner no longer exists.
    """
    script = (
        f"$rows = @(Get-CimInstance -Namespace root/StandardCimv2 -ClassName MSFT_NetTCPConnection"
        f" -Filter 'LocalPort={int(port)} AND RemotePort=0' -ErrorAction SilentlyContinue); $found = @();"
        " foreach ($o in ($rows | ForEach-Object { [int]$_.OwningProcess } | Sort-Object -Unique)) {"
        " if ($o -eq 0) { continue }; $p = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $o);"
        " if (-not $p) { continue }; $s = ''; if ($p.CreationDate) {"
        " $s = $p.CreationDate.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ',"
        " [Globalization.CultureInfo]::InvariantCulture) };"
        " $states = (($rows | Where-Object { [int]$_.OwningProcess -eq $o } | ForEach-Object { [int]$_.State }) -join ',');"
        " $found += [pscustomobject]@{ pid = $o; command = [string]$p.CommandLine; started = $s; states = $states } };"
        " ConvertTo-Json -InputObject @($found) -Compress; exit 0"
    )
    try:
        completed = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                                   capture_output=True, text=True, timeout=LOOKUP_TIMEOUT_SECONDS, check=False)
        reply = json.loads((completed.stdout or "").strip() or "[]")
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return [], f"the port's socket rows could not be read ({type(exc).__name__})"
    owners = []
    for owner in (reply if isinstance(reply, list) else [reply]):
        if isinstance(owner, dict) and isinstance(owner.get("pid"), int) and owner["pid"] != 0:
            owners.append({"pid": owner["pid"], "command": owner.get("command") or None,
                           "started_at": owner.get("started") or None, "states": owner.get("states")})
    return owners, None


def sole_owner(port: int, netstat_pids: set[int], netstat_error: str | None,
               owners: list[dict], rows_error: str | None) -> tuple[dict | None, str, bool]:
    """The one process the fallback lookups may take for the listener on ``port``, or None.

    Returns (owner, what was seen in words, whether any candidate was seen). A candidate is a
    live owner of a remote-port-0 row on the port, or a PID other than 0 that netstat lists as
    LISTENING on it. The owner is taken only when all of these hold:

    - the port's rows could be read;
    - there is exactly one candidate;
    - it owns a row;
    - its command line can be read.

    So a second process holding the port is never passed over, readable or not: with two
    candidates nothing is taken, and the caller refuses as it did before the fallbacks existed.
    PID 0 is never a candidate: it is not a process.
    """
    netstat_live = sorted(pid for pid in netstat_pids if pid != 0)
    if netstat_error:
        netstat_says = netstat_error
    elif netstat_live:
        netstat_says = f"netstat -ano lists {_pids(netstat_live)} LISTENING"
    elif netstat_pids:
        netstat_says = "netstat -ano lists only PID 0 LISTENING, which is not a process"
    else:
        netstat_says = f"netstat -ano lists no LISTENING line for port {port}"
    if rows_error:
        return None, f"{netstat_says}; {rows_error}", bool(netstat_live)
    candidates = sorted({owner["pid"] for owner in owners} | set(netstat_live))
    if not candidates:
        return None, f"{netstat_says}; no live process owns a remote-port-0 row on port {port}", False
    if len(candidates) > 1:
        return None, f"{netstat_says}; more than one process holds port {port}: {_pids(candidates)}", True
    owner = next((owner for owner in owners if owner["pid"] == candidates[0]), None)
    if owner is None:
        return None, f"{netstat_says}, but it owns no remote-port-0 row on port {port}", True
    if not owner["command"]:
        return None, (f"{netstat_says}; the port's own row (remote port 0) is owned by pid {owner['pid']} "
                      "alone, whose command line cannot be read"), True
    return owner, (f"{netstat_says}; the port's own row (remote port 0) is owned by pid {owner['pid']} "
                   f"alone, reported state {owner['states']} (2 is Listen), read through Win32_Process"), True


def _pids(pids: list[int]) -> str:
    return "pid " + str(pids[0]) if len(pids) == 1 else "pids " + ", ".join(str(pid) for pid in pids)


def listening_process(port: int) -> dict:
    """The process listening on ``port`` on this machine.

    ``pid``, ``command`` (its command line) and ``started_at`` (its start, UTC, ISO 8601), each
    None when unknown, and ``note`` saying why when the lookup itself failed. ``found_by`` names
    the lookup that found a process whose command line could be read (a FOUND_BY_* value, None
    when none did), and ``lookup`` lists what each try saw.

    Windows can report a serving socket's state wrongly (D-87's note of 11 November 2026). The
    listening row of a Waitress that was answering requests has read as state 0 or 1, where 2 is
    Listen, and netstat has shown no line for it, or CLOSED. A Listen row and a netstat line
    naming PID 0 have also been seen, beside the real listener's own row and after a listener
    had gone. So the Listen row is not the only lookup, and no lookup takes a process while
    another holds the port (D-87's note of 12 November 2026):

    1. The Listen row (``_listen_row_process``), taken when its process's command line can be read
       and neither ``netstat -ano`` nor the port's own socket rows show another live process on the
       port. Two servers can listen on one address and port on Windows, and then the Listen row
       names one of them, while the port's CIM rows, which share one key, show only one; netstat
       lists both. A second listener on another address has a row of its own, which netstat may
       miss when the state is misreported. When neither source can be read, the Listen row is taken
       as it was before these checks, and the trace says why.
    2. Otherwise two more are read, and one process is taken only when they agree on it
       (``sole_owner``):

       - ``netstat -ano``: the PIDs with a LISTENING line on the port;
       - the port's own socket rows, local port ``port`` and remote port 0, whatever state is
         reported: every live process that owns one, whether or not its command line can be read.

       The process is taken when it is the only candidate, owns a row and has a readable command
       line. ``found_by`` is netstat's when netstat lists it LISTENING, and the port's row
       otherwise. A second candidate, readable or not, means nothing is taken.

    When no process is taken, the lookups are tried again every LOOKUP_RETRY_INTERVAL_SECONDS. The
    last try starts within LOOKUP_RETRY_SECONDS of the first, so the whole wait is about a minute
    (57 to 62 seconds in the trials of 12 November 2026), and longer if a lookup times out. Then
    the Listen row's own result is returned, as it
    always was: nothing listening, or a PID with no command line. It is never process 0:
    ``_listen_row_process`` reports a row that names it as unknown, with a note (D-112's note of
    12 November 2026). Two things differ from the Listen row's own answer, and in neither does
    ``note`` say that nothing is listening: when a candidate was seen and none could be taken,
    ``note`` says so; and when netstat or the port's rows could not be read, ``note`` says that
    whether anything holds the port is not known.

    Each try is printed to stderr as it happens, so a wait shows its reason. Only how the
    process is found changes here. What a caller requires of it does not: the pre-flight still
    reads the server and its threads from this process's command line, and the closing check
    still requires the same PID as before the run.
    """
    if sys.platform != "win32":
        return {**_listen_row_process(port), "found_by": None, "lookup": []}
    trace: list[str] = []

    def say(line: str) -> None:
        trace.append(line)
        print(f"listener lookup, {line}", file=sys.stderr)

    deadline = time.monotonic() + LOOKUP_RETRY_SECONDS
    tries = 0
    while True:
        tries += 1
        found = _listen_row_process(port)
        netstat_pids, netstat_error = _netstat_listening_pids(port)
        owners, rows_error = _port_row_owners(port)
        if found["pid"] is not None and found["command"]:
            others = sorted((set(netstat_pids) | {owner["pid"] for owner in owners}) - {0, found["pid"]})
            if not others:
                unread = [error for error in (netstat_error, rows_error) if error]
                say(f"try {tries}: the Listen row names pid {found['pid']}"
                    + "".join(f"; {error}" for error in unread))
                return {**found, "found_by": FOUND_BY_LISTEN_ROW, "lookup": trace}
            listen_row = (f"the Listen row names pid {found['pid']}, and netstat -ano or the port's own rows "
                          f"show {_pids(others)} on port {port} as well")
            # Not taken, and not returned at the end either: a run must not be READY on one of two.
            found = {"pid": None, "command": None, "started_at": None, "note": None}
        else:
            listen_row = found["note"] or f"the Listen row names pid {found['pid']}, whose command line could not be read"
        owner, why, candidate_seen = sole_owner(port, netstat_pids, netstat_error, owners, rows_error)
        if owner is not None:
            say(f"try {tries}: {listen_row}; {why}")
            return {"pid": owner["pid"], "command": owner["command"], "started_at": owner["started_at"],
                    "note": None, "lookup": trace,
                    "found_by": FOUND_BY_NETSTAT if owner["pid"] in netstat_pids else FOUND_BY_PORT_ROW}
        seen = f"try {tries}: {listen_row}; {why}"
        if time.monotonic() + LOOKUP_RETRY_INTERVAL_SECONDS > deadline:
            say(f"{seen}. Giving up")
            result = {**found, "found_by": None, "lookup": trace}
            if candidate_seen:
                # Something holds the port and could not be taken for the listener. Saying that
                # nothing is listening would be wrong, and wrong in the unsafe direction for
                # anyone checking that the port is free.
                result["note"] = f"no single process with a readable command line holds port {port}: {why}"
            elif netstat_error or rows_error:
                # A lookup that could not be read cannot show that nothing holds the port: the
                # misreported state hides a listener from the Listen row and netstat, and only the
                # port's rows show it (D-87's note of 12 November 2026).
                result["note"] = (f"whether anything holds port {port} is not known, because a lookup could not "
                                  f"be read: {why}")
            return result
        say(f"{seen}. Trying again in {LOOKUP_RETRY_INTERVAL_SECONDS} s")
        time.sleep(LOOKUP_RETRY_INTERVAL_SECONDS)


def debug_probe(base_url: str) -> dict:
    """Whether the server at ``base_url`` runs with DEBUG off, from its answer to an unmatched
    ``/api/`` path (D-87 decision 2). Never raises.

    ``debug`` is ``off`` only for handler404's JSON 404, and ``on`` only for Django's HTML
    debug page, which names ``DEBUG = True``. Anything else, including no reply, is ``unknown``
    with a ``reason``. An HTML body is never kept: Django's debug pages list the URL patterns.
    """
    url = base_url.rstrip("/") + DEBUG_PROBE_PATH
    result: dict = {"path": DEBUG_PROBE_PATH, "url": url, "status": None, "content_type": None,
                    "server_header": None, "body": None, "body_bytes": None,
                    "debug": DEBUG_UNKNOWN, "reason": None}
    try:
        with _OPENER.open(url, timeout=LOOKUP_TIMEOUT_SECONDS) as response:
            status, headers, raw = response.status, response.headers, response.read(PROBE_READ_BYTES)
    except urllib.error.HTTPError as exc:
        status, headers = exc.code, exc.headers
        try:
            raw = exc.read(PROBE_READ_BYTES)
        except OSError:
            raw = b""
    except (urllib.error.URLError, OSError) as exc:
        result["reason"] = f"no reply from {url} ({type(exc).__name__}: {getattr(exc, 'reason', exc)})"
        return result
    content_type = headers.get("Content-Type") or ""
    media_type = content_type.split(";")[0].strip().lower()
    result.update(status=status, content_type=content_type or None,
                  server_header=headers.get("Server"), body_bytes=len(raw))
    text = raw.decode("utf-8", errors="replace")
    if media_type == "application/json":
        result["body"] = text[:500]
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
        if status == 404 and parsed == HANDLER404_BODY:
            result.update(debug=DEBUG_OFF, reason="a 404 in handler404's JSON, which Django sends only with DEBUG off")
        else:
            result["reason"] = (f"a {status} JSON reply that is not handler404's 404 "
                                f"{json.dumps(HANDLER404_BODY)}")
    elif media_type == "text/html":
        if status == 404 and DJANGO_DEBUG_PAGE_MARK in text:
            result.update(debug=DEBUG_ON, reason=(
                "a 404 as Django's HTML debug page, which says DEBUG = True; with DEBUG off, "
                "handler404 answers in JSON"))
        else:
            result["reason"] = f"a {status} HTML page, not handler404's JSON 404" + (
                "; Django sends a 400 page for a Host that is not in ALLOWED_HOSTS" if status == 400 else "")
    else:
        result["reason"] = f"a {status} reply with Content-Type {content_type or 'none'}, not handler404's JSON 404"
    return result


def observe(base_url: str, server_header: str | None = None, *, probe_debug: bool = True) -> dict:
    """The server record for a run that goes through ``base_url``. Never raises.

    With ``probe_debug`` (the default) it also sends the DEBUG probe, a second GET, and keeps
    its result as ``debug``.
    """
    parts = urlsplit(base_url)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    notes: list[str] = []
    local = parts.hostname in ("127.0.0.1", "localhost", "::1")
    process: dict = {"pid": None, "command": None, "started_at": None, "note": None}
    if local:
        process = listening_process(port)
        if process["note"]:
            notes.append(process["note"])
    else:
        notes.append(f"{parts.hostname} is not this machine, so its process is not looked up")
    command = process["command"]
    described = describe(command)
    server = described["server"]
    if server is None and server_header and "waitress" in server_header.lower():
        server = "waitress"
        notes.append("the server is named from its Server header only; its thread count is unknown")
    venv = server_venv(command) if server == "waitress" else None
    version = version_source = None
    if server == "waitress":
        in_venv = venv_package_version(venv, "waitress") if venv else None
        if in_venv:
            version = in_venv
            version_source = f"the Waitress installed in {venv}, the venv the listening process's command line runs from"
        else:
            version = package_version("waitress")
            if version:
                version_source = "the installed package in this process's environment: " + (
                    "the listening process's command line names no venv" if venv is None
                    else f"{venv} holds no Waitress")
    elif server == "django runserver":
        version = package_version("Django")
        version_source = "the installed package in this process's environment" if version else None
    record = {
        "via": "http",
        "base_url": base_url,
        "server": server,
        "version": version,
        "version_source": version_source,
        "version_in_this_python": package_version("waitress"),
        "venv": str(venv) if venv else None,
        "threads": described["threads"],
        "threads_source": described["threads_source"],
        "listen": described["listen"],
        "pid": process["pid"],
        "process_started_at": process["started_at"],
        "process_found_by": process.get("found_by"),
        "process_lookup": process.get("lookup") or [],
        "command_line": command,
        "server_header": server_header,
        "d85_command": D85_COMMAND,
        "notes": notes,
    }
    if probe_debug:
        record["debug"] = debug_probe(base_url)
    return record


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
    debug = record.get("debug")
    if debug and debug.get("debug") != DEBUG_OFF:
        found.append(f"DEBUG is not confirmed off: {debug.get('reason')} (D-85 decision 2, D-87 decision 2)")
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
    debug = record.get("debug")
    if debug and debug.get("debug") == DEBUG_ON:
        found.append(f"the server runs with DEBUG on: {debug.get('reason')} (D-85 decision 2)")
    return found


def summary(record: dict) -> str:
    """One line for a console header or a results file."""
    if record.get("via") == "in-process":
        return "none, in-process"
    threads = record.get("threads")
    debug = record.get("debug")
    return (f"{record.get('server') or 'unknown'} {record.get('version') or ''}".strip()
            + f", {threads if threads is not None else 'unknown'} threads"
            + (f" ({record['threads_source']})" if record.get("threads_source") else "")
            + (f", pid {record['pid']}" if record.get("pid") else "")
            + (f", DEBUG {debug.get('debug')}" if debug else ""))


def fetch_server_header(base_url: str) -> str | None:
    """The Server header of a GET of ``base_url``, error replies included; None if none came."""
    try:
        with _OPENER.open(base_url, timeout=LOOKUP_TIMEOUT_SECONDS) as response:
            return response.headers.get("Server")
    except urllib.error.HTTPError as exc:
        return exc.headers.get("Server")
    except (urllib.error.URLError, OSError):
        return None


# --- Waitress's log, and the runs before this one (D-87 decisions 1 and 3) -------------------


def parse_time(text: str | None) -> datetime | None:
    """An ISO 8601 time as an aware datetime; a time with no zone is local. None if unreadable."""
    if not text or not isinstance(text, str):
        return None
    try:
        stamp = datetime.fromisoformat(text.strip())
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.astimezone()


def iso(stamp: datetime | None) -> str | None:
    return stamp.isoformat(timespec="milliseconds") if stamp else None


def log_time(line: str) -> datetime | None:
    """The timestamp a log line starts with, as an aware datetime, or None if it has none."""
    match = LOG_TIMESTAMP.match(line)
    if not match:
        return None
    zone = match["zone"] or ""
    if zone == "Z":
        zone = "+00:00"
    elif zone and ":" not in zone:
        zone = zone[:3] + ":" + zone[3:]
    fraction = (match["fraction"] or "0").ljust(6, "0")
    return parse_time(f"{match['date']}T{match['time']}.{fraction}{zone}")


def url_port(url: str) -> int | None:
    try:
        parts = urlsplit(url)
        return parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        return None


def read_waitress_log(path: Path) -> list[dict]:
    """Every "Serving on" and "Task queue depth" line in ``path``, in file order.

    Each is ``{"line_number", "line", "at", "kind"}``, with ``url`` and ``port`` for
    ``serving_on`` and ``depth`` for ``queue_depth``. ``at`` is None for a line with no
    timestamp. Raises OSError if the file cannot be read.
    """
    raw = Path(path).read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = raw.decode("utf-16", errors="replace")
    else:
        text = raw.decode("utf-8-sig", errors="replace")
    entries: list[dict] = []
    for number, line in enumerate(text.splitlines(), 1):
        serving = SERVING_ON.search(line)
        depth = QUEUE_DEPTH.search(line)
        if not serving and not depth:
            continue
        entry = {"line_number": number, "line": line.rstrip(), "at": log_time(line)}
        if serving:
            url = serving["url"].rstrip(".,;")
            entry.update(kind="serving_on", url=url, port=url_port(url))
        else:
            entry.update(kind="queue_depth", depth=int(depth["depth"]))
        entries.append(entry)
    return entries


def last_server_start(entries: list[dict], port: int | None, before: datetime) -> dict | None:
    """The last "Serving on" line for ``port`` that is not after ``before``, untimed ones included."""
    found = None
    for entry in entries:
        if entry["kind"] != "serving_on" or entry["port"] != port:
            continue
        if entry["at"] is None or entry["at"] <= before:
            found = entry
    return found


def previous_run_end(folders: list[Path]) -> dict | None:
    """The latest end among the run records in ``folders``: ``{"file", "ended_at", "from"}``.

    Every ``*.json`` directly in a folder counts as a run's record. Its end is when the file
    was last written, or its ``finished_at`` (what a k6 summary records) if that is later. A
    file is written when its run finishes, so the latest is the previous run's end.
    """
    latest: dict | None = None
    seen: set[str] = set()
    for folder in folders:
        folder = Path(folder)
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.json")):
            key = str(path.resolve()).lower()
            if key in seen or not path.is_file():
                continue
            seen.add(key)
            ended = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).astimezone()
            source = "when the file was last written"
            try:
                finished = json.loads(path.read_text(encoding="utf-8")).get("finished_at")
            except (OSError, ValueError, AttributeError):
                finished = None
            finished_at = parse_time(finished)
            if finished_at and finished_at > ended:
                ended, source = finished_at, "its finished_at"
            if latest is None or ended > latest["ended_at"]:
                latest = {"file": str(path), "ended_at": ended, "from": source}
    return latest


def _product(header: str | None) -> str:
    return re.split(r"[/\s]", (header or "").strip())[0].lower()


def preflight(*, base_url: str, waitress_log: str | None, waitress_log_from: str | None,
              results_dirs: list[str], threads_stated: int, override_threads: bool,
              now: datetime | None = None) -> dict:
    """Everything tests/load/run.ps1 must observe before k6 starts (D-87), and why it may not.

    ``refusals`` is empty, and ``ready`` true, only when the run may start.
    """
    now = (now or datetime.now(timezone.utc)).astimezone()
    port = url_port(base_url)
    server = observe(base_url, fetch_server_header(base_url.rstrip("/") + "/api/"))
    refusals: list[str] = []
    restart_hint = f"Stop it (Ctrl+C) and start it as `{D85_COMMAND}`, under DEBUG=False."

    # 1. Waitress, from the listening process's command line, not from a header alone.
    named = describe(server.get("command_line"))["server"]
    if named != D85_SERVER:
        what = named or "not observed"
        why = f" ({'; '.join(server['notes'])})" if server.get("notes") else ""
        refusals.append(f"the server listening on port {port} is {what}{why}, not Waitress "
                        f"(D-85 decision 2, D-87 decision 2). {restart_hint}")

    # 2. The thread count, observed. A missing --threads is Waitress's default, 4.
    threads, source = server.get("threads"), server.get("threads_source")
    if named == D85_SERVER and threads is None:
        refusals.append("the listening Waitress's thread count was not observed, and a run is not "
                        "started on a thread count nobody saw (D-87 decision 2)")
    elif named == D85_SERVER and override_threads and threads != threads_stated:
        refusals.append(f"-ServerThreads states {threads_stated}, and the listening Waitress runs "
                        f"{threads} threads ({source}). With -OverrideServerThreads the stated count "
                        "must be the one observed.")
    elif named == D85_SERVER and not override_threads and threads != D85_THREADS:
        refusals.append(f"the listening Waitress runs {threads} threads ({source}), not D-85's "
                        f"{D85_THREADS} (D-85 decision 3). {restart_hint} For a run that is deliberately "
                        f"not D-85's, pass -OverrideServerThreads -ServerThreads {threads}.")
    if not override_threads and threads_stated != D85_THREADS:
        refusals.append(f"{threads_stated} threads is stated without the override, and D-85 measures "
                        f"at {D85_THREADS}")

    # 3. The replies come from Waitress: the Server header of GET /api/ and of the probe.
    debug = server.get("debug") or {}
    for label, header in (("GET /api/", server.get("server_header")),
                          (f"GET {DEBUG_PROBE_PATH}", debug.get("server_header"))):
        if not header:
            refusals.append(f"{label} came back with no Server header, so nothing shows Waitress "
                            "answered it")
        elif _product(header) != D85_SERVER:
            refusals.append(f"{label} was answered by {header!r}, not Waitress")

    # 4. DEBUG off: handler404's JSON 404, never Django's HTML page.
    if debug.get("debug") != DEBUG_OFF:
        refusals.append(
            f"DEBUG is not confirmed off: GET {DEBUG_PROBE_PATH} got {debug.get('reason') or 'no reply'} "
            "(D-87 decision 2). Start the server with $env:DEBUG = 'False' set in its window: the "
            "repo's .env sets DEBUG=True, and only a value set in the shell overrides it.")

    # 5. Waitress's log: this server's last start.
    log: dict = {"path": waitress_log, "path_from": waitress_log_from, "exists": False,
                 "server_started_at": None, "serving_on_line": None, "serving_on_line_number": None,
                 "process_started_at": server.get("process_started_at")}
    started = None
    if not waitress_log:
        refusals.append(f"no Waitress log was named: pass -WaitressLog, or set {WAITRESS_LOG_ENV} "
                        "in this window as in the server's (D-87 decision 3)")
    elif not Path(waitress_log).is_file():
        refusals.append(f"there is no Waitress log at {waitress_log}. Waitress writes it from its first "
                        f"line, 'Serving on', when {WAITRESS_LOG_ENV} names it in the server's window "
                        "(D-87 decision 3). Is it the same path in both windows?")
    else:
        log["exists"] = True
        try:
            entries = read_waitress_log(Path(waitress_log))
        except OSError as exc:
            entries = None
            refusals.append(f"Waitress's log at {waitress_log} could not be read ({exc})")
        start = last_server_start(entries, port, now) if entries is not None else None
        process_started = parse_time(server.get("process_started_at"))
        if entries is not None and start is None:
            refusals.append(f"{waitress_log} has no 'Serving on' line for port {port}, so the server's "
                            "start cannot be read from it. Is it this server's log?")
        elif start is not None and start["at"] is None:
            refusals.append(f"the last 'Serving on' line for port {port} in {waitress_log} has no "
                            f"timestamp ({start['line']!r}), so the server's start cannot be read from "
                            "it. Is it the file apps/core/logging_config.py writes?")
        elif start is not None:
            started = start["at"]
            log.update(server_started_at=iso(started), serving_on_line=start["line"],
                       serving_on_line_number=start["line_number"])
            if process_started and started < process_started - PROCESS_START_TOLERANCE:
                refusals.append(
                    f"the last 'Serving on' line for port {port} in {waitress_log} is from "
                    f"{iso(started)}, before the listening process started at "
                    f"{iso(process_started.astimezone())}, so it is not that process's log. Is "
                    f"{WAITRESS_LOG_ENV} the same in the server's window and this one?")
                started = None

    # 6. Restarted since the previous run through it (D-87 decision 1).
    previous = previous_run_end([Path(folder) for folder in results_dirs])
    restarted = None
    if started is not None:
        restarted = previous is None or started > previous["ended_at"]
        if not restarted:
            refusals.append(
                f"Waitress last started at {iso(started)} (its log's 'Serving on'), before the "
                f"previous run recorded in {Path(previous['file']).parent} ended: "
                f"{Path(previous['file']).name} was written at {iso(previous['ended_at'])} "
                f"({previous['from']}). The server was not restarted after that run (D-87 decision "
                "1), so its throttle counters and in-flight slots are not empty. Stop it (Ctrl+C), "
                "start it again, and run this again.")

    return {
        "observed_at": iso(now),
        "observed_by": OBSERVED_BY,
        "base_url": base_url,
        "server": server,
        "stated": {"server": D85_SERVER, "threads": threads_stated, "override_threads": override_threads},
        "waitress_log": log,
        "restart": {
            "server_started_at": iso(started),
            "previous_run": ({"file": previous["file"], "ended_at": iso(previous["ended_at"]),
                              "from": previous["from"]} if previous else None),
            "results_dirs": [str(folder) for folder in results_dirs],
            "restarted_after_previous_run": restarted,
        },
        "refusals": refusals,
        "ready": not refusals,
    }


def k6_environment(record: dict) -> dict[str, str]:
    """The observed values run.ps1 passes to k6 with -e: strings on one line, never a quote."""
    server = record["server"]
    previous = record["restart"]["previous_run"] or {}
    values = {
        "PREFLIGHT_READY": "yes" if record["ready"] else "no",
        "SERVER": server.get("server") or "",
        "SERVER_VERSION": server.get("version") or "",
        "SERVER_VERSION_SOURCE": server.get("version_source") or "",
        "SERVER_THREADS": "" if server.get("threads") is None else str(server["threads"]),
        "SERVER_THREADS_SOURCE": server.get("threads_source") or "",
        "SERVER_PID": "" if server.get("pid") is None else str(server["pid"]),
        "SERVER_DEBUG": (server.get("debug") or {}).get("debug") or "",
        "SERVER_STARTED_AT": record["restart"]["server_started_at"] or "",
        "PREVIOUS_RUN_FILE": previous.get("file") or "none",
        "PREVIOUS_RUN_ENDED_AT": previous.get("ended_at") or "none",
        "SERVER_OBSERVED_BY": OBSERVED_BY,
    }
    return {name: " ".join(str(value).split()).replace('"', "'") for name, value in values.items()}


def preflight_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="server_record.py preflight", description=preflight.__doc__.splitlines()[0])
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--waitress-log", default=None)
    parser.add_argument("--waitress-log-from", default="--waitress-log")
    parser.add_argument("--results-dir", action="append", default=[])
    parser.add_argument("--threads-stated", type=int, required=True)
    parser.add_argument("--override-threads", action="store_true")
    parser.add_argument("--out", type=Path, required=True, help="the pre-flight record, JSON")
    parser.add_argument("--env-out", type=Path, help="the -e values for k6, NAME=value lines")
    arguments = parser.parse_args(argv)
    record = preflight(base_url=arguments.base_url, waitress_log=arguments.waitress_log,
                       waitress_log_from=arguments.waitress_log_from, results_dirs=arguments.results_dir,
                       threads_stated=arguments.threads_stated, override_threads=arguments.override_threads)
    arguments.out.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    if arguments.env_out:
        arguments.env_out.write_text(
            "".join(f"{name}={value}\n" for name, value in k6_environment(record).items()), encoding="utf-8")

    server, log, restart = record["server"], record["waitress_log"], record["restart"]
    debug = server.get("debug") or {}
    previous = restart["previous_run"]
    print(f"server         : {summary(server)}")
    print(f"command line   : {server.get('command_line') or 'not observed'}")
    print(f"process start  : {server.get('process_started_at') or 'not observed'}")
    print(f"found by       : {server.get('process_found_by') or 'no lookup found it'}")
    print(f"version from   : {server.get('version_source') or 'not read'}")
    print(f"Server header  : {server.get('server_header') or 'none'} (GET /api/), "
          f"{debug.get('server_header') or 'none'} (the DEBUG probe)")
    print(f"DEBUG          : {debug.get('debug', DEBUG_UNKNOWN)}: GET {DEBUG_PROBE_PATH} -> "
          f"{debug.get('status')} {debug.get('content_type')}; {debug.get('reason')}")
    print(f"Waitress log   : {log['path'] or 'not named'} (from {log['path_from']})")
    print(f"server started : {log['server_started_at'] or 'not read'}"
          + (f" (line {log['serving_on_line_number']}: {log['serving_on_line']})" if log["serving_on_line"] else ""))
    print("previous run   : " + (f"{previous['file']}, ended {previous['ended_at']} ({previous['from']})"
                                 if previous else f"none recorded in {', '.join(restart['results_dirs']) or 'no folder'}"))
    for refusal in record["refusals"]:
        print(f"REFUSED: {refusal}")
    print(READY_LINE if record["ready"] else REFUSED_LINE)
    return 0 if record["ready"] else REFUSED


def finalise(*, preflight_record: dict, summary_path: Path, window_start: datetime, window_end: datetime,
             copy_to: Path | None = None) -> tuple[int, list[str]]:
    """Adds Waitress's log for the run's window and the pre-flight record to the k6 summary.

    Returns (exit code, the lines to print). Marks the run INVALID if Waitress started again
    inside the window, if another process (or none) is listening at the end, or if the
    pre-flight's own checks did not hold. Leaves a summary that is not this run's untouched.
    """
    lines: list[str] = []
    port = url_port(preflight_record["base_url"])
    log_path = preflight_record["waitress_log"]["path"]
    block: dict = {
        "path": log_path,
        "path_from": preflight_record["waitress_log"]["path_from"],
        "window": {"start": iso(window_start), "end": iso(window_end)},
        "server_started_at": preflight_record["waitress_log"]["server_started_at"],
        "serving_on_line": preflight_record["waitress_log"]["serving_on_line"],
        "process_started_at": preflight_record["waitress_log"]["process_started_at"],
    }
    try:
        entries = read_waitress_log(Path(log_path)) if log_path else None
        if entries is None:
            block["error"] = "no Waitress log was named"
    except OSError as exc:
        entries = None
        block["error"] = f"the log could not be read after the run ({exc})"
    in_window, before, after, untimed, restarts = [], 0, 0, [], []
    for entry in entries or []:
        if entry["kind"] == "queue_depth":
            if entry["at"] is None:
                untimed.append(entry["line"])
            elif entry["at"] < window_start:
                before += 1
            elif entry["at"] > window_end:
                after += 1
            else:
                in_window.append(entry)
        elif entry["port"] == port and entry["at"] and window_start <= entry["at"] <= window_end:
            restarts.append(entry["line"])
    deepest = max((entry["depth"] for entry in in_window), default=None)
    block.update(
        queue_depth=("none in the run's window" if not in_window else
                     f"{len(in_window)} line(s) in the run's window, the deepest {deepest}"),
        queue_depth_lines=[entry["line"] for entry in in_window],
        queue_depth_lines_in_window=len(in_window),
        max_queue_depth_in_window=deepest,
        queue_depth_lines_before_window=before,
        queue_depth_lines_after_window=after,
        queue_depth_lines_untimed=untimed,
        serving_on_lines_in_window=restarts,
    )
    if entries is None:
        block["queue_depth"] = "not known: the log was not read after the run"

    expected_pid = preflight_record["server"].get("pid")
    at_end = listening_process(port) if port else {"pid": None, "note": "no port"}
    server_at_end = {"pid": at_end["pid"], "pid_before_the_run": expected_pid,
                     "same_process": at_end["pid"] is not None and at_end["pid"] == expected_pid,
                     "note": at_end.get("note"), "found_by": at_end.get("found_by"),
                     "lookup": at_end.get("lookup") or []}

    reasons: list[str] = []
    if restarts:
        reasons.append(f"Waitress started again during the run ({restarts[0]!r}, inside the run's window), "
                       "so the server observed before the run is not the one that answered all of it, and "
                       "its throttle counters and slots were emptied part-way (D-87 decisions 1 and 3)")
    if not server_at_end["same_process"]:
        now_listening = f"pid {at_end['pid']}" if at_end["pid"] is not None else (at_end.get("note") or "nothing")
        reasons.append(f"the process listening on port {port} after the run ({now_listening}) is not the one "
                       f"observed before it (pid {expected_pid}) (D-87 decision 2)")
    if entries is None:
        reasons.append("Waitress's log could not be read after the run, so neither its queueing nor a "
                       "restart during the run is known (D-87 decision 3)")
    if preflight_record.get("refusals"):
        reasons.append("the pre-flight refused, so k6 should not have run: "
                       + "; ".join(preflight_record["refusals"]))
    if preflight_record["restart"].get("restarted_after_previous_run") is False:
        reasons.append("the server was not restarted after the previous run (D-87 decision 1)")

    if not summary_path.is_file():
        lines.append(f"NOT MERGED: k6 wrote no summary at {summary_path}.")
        return NOT_MERGED, lines
    try:
        report = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        lines.append(f"NOT MERGED: {summary_path} could not be read as JSON ({exc}).")
        return NOT_MERGED, lines
    finished = parse_time(report.get("finished_at")) if isinstance(report, dict) else None
    if finished is None or not (window_start - SUMMARY_TOLERANCE <= finished <= window_end + SUMMARY_TOLERANCE):
        lines.append(f"NOT MERGED: {summary_path} is not this run's: its finished_at is "
                     f"{report.get('finished_at') if isinstance(report, dict) else None}, outside the run's "
                     f"window {iso(window_start)} to {iso(window_end)}. It was left as it was.")
        return NOT_MERGED, lines

    report["waitress_log"] = block
    report["server_at_end"] = server_at_end
    report["server_preflight"] = preflight_record
    verdict_was = report.get("verdict")
    if reasons:
        report["verdict"] = INVALID_VERDICT
        report["run_valid"] = False
        report["invalid_reasons"] = list(report.get("invalid_reasons") or []) + reasons
    summary_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    copied = None
    if copy_to is not None:
        target = Path(copy_to) / summary_path.name
        if target.resolve() != summary_path.resolve():
            shutil.copy2(summary_path, target)
            copied = target

    lines.append(f"queue depth    : {block['queue_depth']}")
    for line in block["queue_depth_lines"]:
        lines.append(f"  {line}")
    lines.append(f"outside window : {before} before, {after} after, {len(untimed)} untimed (not copied)")
    lines.append(f"restart inside : {len(restarts)} 'Serving on' line(s) in the window")
    lines.append(f"at the end     : pid {at_end['pid']} listening on port {port}"
                 + ("" if server_at_end["same_process"] else f", NOT pid {expected_pid} as before the run"))
    for reason in reasons:
        lines.append(f"INVALID: {reason}")
    if reasons and verdict_was != INVALID_VERDICT:
        lines.append(f"verdict        : {verdict_was} -> {INVALID_VERDICT}")
    else:
        lines.append(f"verdict        : {report.get('verdict')}")
    lines.append(f"{FINALISED_LINE} {summary_path}" + (f", copied to {copied}" if copied else ""))
    return 0, lines


def finalise_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="server_record.py finalise", description=finalise.__doc__.splitlines()[0])
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--window-start", required=True)
    parser.add_argument("--window-end", required=True)
    parser.add_argument("--copy-to", type=Path)
    arguments = parser.parse_args(argv)
    start, end = parse_time(arguments.window_start), parse_time(arguments.window_end)
    if start is None or end is None or end < start:
        print(f"NOT MERGED: the window {arguments.window_start} to {arguments.window_end} is not two times in order.")
        return NOT_MERGED
    try:
        record = json.loads(arguments.preflight.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"NOT MERGED: the pre-flight record {arguments.preflight} could not be read ({exc}).")
        return NOT_MERGED
    code, lines = finalise(preflight_record=record, summary_path=arguments.summary, window_start=start,
                           window_end=end, copy_to=arguments.copy_to)
    for line in lines:
        print(line)
    return code


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    # run.ps1 reads this output through a pipe, where Python writes the ANSI code page. A
    # command line or path it cannot encode is shown with a replacement, not a traceback.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    if arguments and arguments[0] == "preflight":
        return preflight_main(arguments[1:])
    if arguments and arguments[0] == "finalise":
        return finalise_main(arguments[1:])
    base_url = arguments[0] if arguments else f"http://{D85_LISTEN}"
    record = observe(base_url, fetch_server_header(base_url))
    print(json.dumps(record, indent=2))
    for problem in problems(record):
        print(f"NOT D-85: {problem}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
