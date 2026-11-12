"""D-87's pre-flight and finalise step in scripts/server_record.py.

Drafted by the test-engineer agent beside the change and moved here by the coordinating
session, because pytest collects only from apps/. Written in the style of
test_fr13_measurement_scripts.py, whose ``scripts`` fixture this one repeats. Nothing here
reaches FLM, and the only server is a stub on an ephemeral loopback port, started and
stopped by the test that uses it.
"""

import importlib
import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPOSITORY_ROOT / "scripts"
WAITRESS_24 = r'"C:\py\python.exe"  "C:\venv\Scripts\waitress-serve.exe" --listen=127.0.0.1:8000 --threads=24 config.wsgi:application'


@pytest.fixture
def scripts(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))

    def load(name):
        sys.modules.pop(name, None)
        return importlib.import_module(name)

    return load


# --- the command line ------------------------------------------------------------------------


def test_a_second_threads_option_wins_as_getopt_reads_it(scripts):
    record = scripts("server_record").describe(WAITRESS_24.replace("--threads=24", "--threads=4 --threads=24"))
    assert (record["threads"], record["threads_source"]) == (24, "--threads on the command line")


def test_the_venv_and_its_waitress_are_read_from_the_command_line(scripts, tmp_path):
    server_record = scripts("server_record")
    venv = tmp_path / "venv"
    (venv / "Scripts").mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text("home = x\n")
    metadata = venv / "Lib" / "site-packages" / "waitress-3.0.2.dist-info"
    metadata.mkdir(parents=True)
    (metadata / "METADATA").write_text("Metadata-Version: 2.1\nName: waitress\nVersion: 3.0.2\n")
    command = f'"C:\\py\\python.exe"  "{venv / "Scripts" / "waitress-serve.exe"}" --listen=127.0.0.1:8000'
    assert server_record.server_venv(command) == venv
    assert server_record.venv_package_version(venv, "waitress") == "3.0.2"
    assert server_record.server_venv('"C:\\py\\python.exe" -m waitress --threads=24 app') is None


# --- DEBUG: the unmatched /api/ path -------------------------------------------------------------

DJANGO_DEBUG_PAGE = b"<html><title>Page not found at /api/x</title>you have <code>DEBUG = True</code></html>"
REPLIES = {
    "json404": (404, "application/json", b'{"detail": "Not found."}'),
    "html404": (404, "text/html; charset=utf-8", DJANGO_DEBUG_PAGE),
    "html400": (400, "text/html", b"<h1>Bad Request (400)</h1>"),
    "otherjson": (404, "application/json", b'{"detail": "Nope."}'),
    "html404plain": (404, "text/html", b"<h1>Not Found</h1>"),
}


@pytest.fixture
def stub_server():
    """A loopback stub answering every GET with the reply its ``mode`` names."""
    state = {"mode": "json404"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            status, content_type, body = REPLIES[state["mode"]]
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def version_string(self):
            return "waitress"

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield state, f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.mark.parametrize("mode, debug, because", [
    ("json404", "off", "handler404's JSON"),
    ("html404", "on", "DEBUG = True"),
    ("html400", "unknown", "ALLOWED_HOSTS"),
    ("otherjson", "unknown", "not handler404's 404"),
    ("html404plain", "unknown", "not handler404's JSON 404"),
])
def test_debug_is_read_from_the_unmatched_api_path(scripts, stub_server, mode, debug, because):
    state, url = stub_server
    state["mode"] = mode
    probe = scripts("server_record").debug_probe(url)
    assert (probe["debug"], probe["path"]) == (debug, "/api/__preflight_not_a_route__")
    assert because in probe["reason"]
    assert probe["server_header"] == "waitress"
    if mode.startswith("html"):
        assert probe["body"] is None   # Django's debug page lists the URL patterns: never kept


def test_no_reply_is_unknown_not_off(scripts):
    with __import__("socket").socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    probe = scripts("server_record").debug_probe(f"http://127.0.0.1:{port}")
    assert probe["debug"] == "unknown" and probe["reason"].startswith("no reply")


def test_debug_on_contradicts_d85_and_unknown_only_warns(scripts):
    server_record = scripts("server_record")
    record = {"server": "waitress", "threads": 24, "threads_source": "--threads", "server_header": "waitress"}
    on = dict(record, debug={"debug": "on", "reason": "the HTML debug page"})
    unknown = dict(record, debug={"debug": "unknown", "reason": "no reply"})
    off = dict(record, debug={"debug": "off", "reason": "JSON"})
    assert any("DEBUG on" in c for c in server_record.contradicts_d85(on))
    assert server_record.contradicts_d85(unknown) == []
    assert any("DEBUG is not confirmed off" in p for p in server_record.problems(unknown))
    assert server_record.problems(off) == [] and server_record.contradicts_d85(off) == []


# --- Waitress's log ---------------------------------------------------------------------------


def stamp(at):
    return at.strftime("%Y-%m-%d %H:%M:%S,") + f"{at.microsecond // 1000:03d}"


def test_the_log_formats_waitress_lines_are_read_in(scripts, tmp_path):
    server_record = scripts("server_record")
    log = tmp_path / "waitress.log"
    log.write_text(
        "2026-10-28 18:20:16,549 INFO waitress Serving on http://127.0.0.1:8000\n"
        "Traceback (most recent call last): a continuation line\n"
        "2026-10-28 18:20:39,784 WARNING waitress.queue Task queue depth is 1\n"
        "2026-10-28T18:21:00.5Z WARNING waitress.queue Task queue depth is 12\n"
        "INFO:waitress:Serving on http://127.0.0.1:8001\n"
        "2026-10-28 18:22:00,000 INFO waitress Serving on http://[::1]:8000\n",
        encoding="utf-8")
    entries = server_record.read_waitress_log(log)
    assert [(e["kind"], e.get("port"), e.get("depth")) for e in entries] == [
        ("serving_on", 8000, None), ("queue_depth", None, 1), ("queue_depth", None, 12),
        ("serving_on", 8001, None), ("serving_on", 8000, None)]
    assert entries[0]["at"] == datetime(2026, 10, 28, 18, 20, 16, 549000).astimezone()
    assert entries[2]["at"] == datetime(2026, 10, 28, 18, 21, 0, 500000, tzinfo=timezone.utc)
    assert entries[3]["at"] is None
    before = datetime(2026, 10, 28, 18, 21, 30).astimezone()
    assert server_record.last_server_start(entries, 8000, before)["line_number"] == 1
    assert server_record.last_server_start(entries, 8001, before)["at"] is None
    assert server_record.last_server_start(entries, 9999, before) is None


def test_the_previous_run_ends_at_its_latest_evidence(scripts, tmp_path):
    server_record = scripts("server_record")
    old = tmp_path / "nfr08_summary.json"
    old.write_text(json.dumps({"finished_at": "2099-01-01T00:00:00.000Z"}), encoding="utf-8")
    other = tmp_path / "http_check.json"
    other.write_text("[]", encoding="utf-8")
    found = server_record.previous_run_end([tmp_path, tmp_path / "missing"])
    assert Path(found["file"]).name == "nfr08_summary.json" and found["from"] == "its finished_at"
    old.write_text(json.dumps({"finished_at": "2000-01-01T00:00:00.000Z"}), encoding="utf-8")
    os.utime(old, (0, 0))
    found = server_record.previous_run_end([tmp_path])
    assert Path(found["file"]).name == "http_check.json" and found["from"] == "when the file was last written"
    assert server_record.previous_run_end([tmp_path / "missing"]) is None


# --- the pre-flight's refusals ---------------------------------------------------------------------


def observed(**overrides):
    record = {"via": "http", "server": "waitress", "version": "3.0.2", "version_source": "the venv",
              "threads": 24, "threads_source": "--threads on the command line", "pid": 7,
              "process_started_at": None, "command_line": WAITRESS_24, "server_header": "waitress",
              "notes": [], "debug": {"debug": "off", "reason": "handler404's JSON", "server_header": "waitress",
                                     "status": 404, "content_type": "application/json"}}
    record.update(overrides)
    return record


@pytest.fixture
def preflight(scripts, monkeypatch, tmp_path):
    """server_record with observe() returning the record a test sets, and a log whose server
    started a minute ago."""
    server_record = scripts("server_record")
    state = {"record": observed()}
    monkeypatch.setattr(server_record, "fetch_server_header", lambda url: "waitress")
    monkeypatch.setattr(server_record, "observe", lambda url, header: state["record"])
    log = tmp_path / "waitress.log"
    started = datetime.now() - timedelta(minutes=1)
    log.write_text(f"{stamp(started)} INFO waitress Serving on http://127.0.0.1:8000\n", encoding="utf-8")
    results = tmp_path / "results"
    results.mkdir()

    def run(**kw):
        arguments = dict(base_url="http://127.0.0.1:8000", waitress_log=str(log), waitress_log_from="-WaitressLog",
                         results_dirs=[str(results)], threads_stated=24, override_threads=False)
        arguments.update(kw)
        return server_record.preflight(**arguments)

    return server_record, state, run, log, results, started


def test_d85s_server_restarted_since_the_last_run_is_ready(preflight):
    server_record, state, run, log, results, started = preflight
    old = results / "harness.json"
    old.write_text("{}", encoding="utf-8")
    os.utime(old, ((started - timedelta(minutes=5)).timestamp(),) * 2)
    record = run()
    assert record["refusals"] == [] and record["ready"] is True
    assert record["restart"]["restarted_after_previous_run"] is True
    assert record["waitress_log"]["serving_on_line"].endswith("Serving on http://127.0.0.1:8000")
    env = server_record.k6_environment(record)
    assert (env["SERVER"], env["SERVER_THREADS"], env["SERVER_DEBUG"], env["PREFLIGHT_READY"]) == ("waitress", "24", "off", "yes")
    assert not any('"' in value or "\n" in value for value in env.values())


@pytest.mark.parametrize("record, kw, because", [
    (observed(command_line=WAITRESS_24.replace(" --threads=24", ""), threads=4,
              threads_source="Waitress's default: no --threads on the command line"), {},
     "runs 4 threads (Waitress's default"),
    (observed(threads=4, threads_source="Waitress's default"), {"threads_stated": 8, "override_threads": True},
     "-ServerThreads states 8, and the listening Waitress runs 4"),
    (observed(debug={"debug": "on", "reason": "Django's HTML debug page", "server_header": "waitress"}), {},
     "DEBUG is not confirmed off"),
    (observed(debug={"debug": "unknown", "reason": "no reply", "server_header": None}), {},
     "came back with no Server header"),
    (observed(command_line=None, server="waitress", threads=None, notes=["nothing is listening on port 8000"]), {},
     "is not observed (nothing is listening on port 8000), not Waitress"),
    (observed(command_line=r'"C:\py\python.exe" -m http.server 8000', server="unknown", threads=None), {},
     "is unknown, not Waitress"),
])
def test_the_preflight_refuses_what_is_not_d85s(preflight, record, kw, because):
    _, state, run, *_ = preflight
    state["record"] = record
    result = run(**kw)
    assert result["ready"] is False
    assert any(because in refusal for refusal in result["refusals"]), result["refusals"]


def test_a_missing_threads_option_is_refused_as_4_not_as_unknown(preflight):
    """D-87 decision 2: no --threads reads as Waitress's default, so the refusal names 4."""
    server_record, state, run, *_ = preflight
    command = WAITRESS_24.replace(" --threads=24", "")
    state["record"] = observed(command_line=command, **{k: v for k, v in server_record.describe(command).items()
                                                        if k in ("threads", "threads_source")})
    refusals = run()["refusals"]
    assert any("runs 4 threads (Waitress's default: no --threads on the command line)" in r for r in refusals), refusals


def test_a_server_not_restarted_since_the_last_run_is_refused(preflight):
    _, _, run, _, results, _ = preflight
    (results / "http_check.json").write_text("{}", encoding="utf-8")   # written after the server started
    result = run()
    assert result["restart"]["restarted_after_previous_run"] is False
    assert any("was not restarted after that run" in r and "http_check.json" in r for r in result["refusals"])


def test_a_log_from_before_the_listening_process_is_not_its_log(preflight):
    _, state, run, *_ = preflight
    state["record"] = observed(process_started_at=datetime.now(timezone.utc).isoformat())
    result = run()
    assert any("so it is not that process's log" in r for r in result["refusals"])
    assert result["restart"]["server_started_at"] is None


@pytest.mark.parametrize("contents, because", [
    (None, "there is no Waitress log at"),
    ("2026-10-28 10:00:00,000 INFO waitress Serving on http://127.0.0.1:9\n", "has no 'Serving on' line for port 8000"),
    ("INFO:waitress:Serving on http://127.0.0.1:8000\n", "has no timestamp"),
])
def test_a_log_that_cannot_give_the_start_is_refused(preflight, contents, because):
    _, _, run, log, *_ = preflight
    if contents is None:
        log.unlink()
    else:
        log.write_text(contents, encoding="utf-8")
    assert any(because in r for r in run()["refusals"])


# --- finalise: the run's window, into the summary --------------------------------------------------


@pytest.fixture
def finalise(scripts, monkeypatch, tmp_path):
    server_record = scripts("server_record")
    state = {"pid": 7}
    monkeypatch.setattr(server_record, "listening_process",
                        lambda port: {"pid": state["pid"], "command": None, "started_at": None, "note": None})
    start = datetime.now().astimezone() - timedelta(minutes=10)
    end = start + timedelta(minutes=5)
    log = tmp_path / "waitress.log"
    lines = [
        f"{stamp(start - timedelta(minutes=1))} INFO waitress Serving on http://127.0.0.1:8000",
        f"{stamp(start - timedelta(seconds=1))} WARNING waitress.queue Task queue depth is 1",
        f"{stamp(start + timedelta(minutes=1))} WARNING waitress.queue Task queue depth is 3",
        f"{stamp(start + timedelta(minutes=2))} WARNING waitress.queue Task queue depth is 6",
        f"{stamp(end + timedelta(seconds=1))} WARNING waitress.queue Task queue depth is 9",
        "WARNING:waitress.queue:Task queue depth is 4",
    ]
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    summary = tmp_path / "results" / "nfr08_summary.json"
    summary.parent.mkdir()
    summary.write_text(json.dumps({"verdict": "PASS", "run_valid": True, "invalid_reasons": [],
                                   "waitress_log": {"path": str(log), "queue_depth": "not added"},
                                   "finished_at": (end - timedelta(seconds=2)).isoformat()}), encoding="utf-8")
    record = {"base_url": "http://127.0.0.1:8000", "server": {"pid": 7}, "refusals": [],
              "restart": {"restarted_after_previous_run": True},
              "waitress_log": {"path": str(log), "path_from": "-WaitressLog", "server_started_at": "x",
                               "serving_on_line": lines[0], "process_started_at": None}}

    def run(**kw):
        return server_record.finalise(preflight_record=record, summary_path=summary, window_start=start,
                                      window_end=end, **kw)

    return server_record, state, run, log, summary, lines, (start, end)


def test_only_the_windows_queue_lines_are_copied(finalise, tmp_path):
    server_record, _, run, _, summary, lines, _ = finalise
    copy = tmp_path / "run_folder"
    copy.mkdir()
    code, printed = run(copy_to=copy)
    report = json.loads(summary.read_text(encoding="utf-8"))
    log = report["waitress_log"]
    assert code == 0 and printed[-1].startswith("FINALISED:")
    assert log["queue_depth_lines"] == [lines[2], lines[3]]
    assert (log["max_queue_depth_in_window"], log["queue_depth_lines_before_window"],
            log["queue_depth_lines_after_window"]) == (6, 1, 1)
    assert log["queue_depth_lines_untimed"] == [lines[5]]
    assert report["verdict"] == "PASS" and report["server_at_end"]["same_process"] is True
    assert report["server_preflight"]["server"]["pid"] == 7
    assert json.loads((copy / "nfr08_summary.json").read_text(encoding="utf-8")) == report


def test_none_in_the_window_is_recorded_as_none(finalise):
    _, _, run, log, summary, lines, _ = finalise
    log.write_text(lines[0] + "\n" + lines[1] + "\n", encoding="utf-8")
    run()
    log_block = json.loads(summary.read_text(encoding="utf-8"))["waitress_log"]
    assert log_block["queue_depth"] == "none in the run's window" and log_block["queue_depth_lines"] == []


def test_a_restart_inside_the_window_makes_the_run_invalid(finalise):
    _, _, run, log, summary, _, (start, _) = finalise
    with log.open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp(start + timedelta(minutes=3))} INFO waitress Serving on http://127.0.0.1:8000\n")
    run()
    report = json.loads(summary.read_text(encoding="utf-8"))
    assert report["verdict"] == "INVALID RUN" and report["run_valid"] is False
    assert any("Waitress started again during the run" in r for r in report["invalid_reasons"])


def test_another_process_at_the_end_makes_the_run_invalid(finalise):
    _, state, run, _, summary, *_ = finalise
    state["pid"] = 99
    run()
    report = json.loads(summary.read_text(encoding="utf-8"))
    assert report["verdict"] == "INVALID RUN"
    assert any("(pid 99) is not the one observed before it (pid 7)" in r for r in report["invalid_reasons"])


def test_a_summary_from_another_run_is_left_alone(finalise):
    server_record, _, run, _, summary, *_ = finalise
    summary.write_text(json.dumps({"verdict": "PASS", "finished_at": "2020-01-01T00:00:00Z"}), encoding="utf-8")
    before = summary.read_text(encoding="utf-8")
    code, printed = run()
    assert code == server_record.NOT_MERGED and "is not this run's" in printed[0]
    assert summary.read_text(encoding="utf-8") == before
    summary.unlink()
    assert run()[0] == server_record.NOT_MERGED


# --- the listening process, when Windows misreports its socket (D-87's notes of 11 and 12 November 2026) ---
# Nothing here runs PowerShell or netstat: each lookup is scripted, or its command's output is.

STARTED = "2026-11-11T00:00:00.000Z"
NOTHING_LISTENING = {"pid": None, "command": None, "started_at": None, "note": "nothing is listening on port 8000"}
# What _listen_row_process gives for a row that names process 0 (D-112's note of 12 November 2026).
PROCESS_0_ROW = {"pid": None, "command": None, "started_at": None,
                 "note": ("the Listen row for port 8000 names process 0, the System Idle Process, "
                          "which is not a server: the listening process is unknown")}
NETSTAT = """
Active Connections

  Proto  Local Address          Foreign Address        State           PID
  TCP    0.0.0.0:135            0.0.0.0:0              LISTENING       1480
  TCP    127.0.0.1:8000         0.0.0.0:0              LISTENING       46608
  TCP    127.0.0.1:18000        0.0.0.0:0              LISTENING       500
  TCP    127.0.0.1:800          0.0.0.0:0              LISTENING       501
  TCP    127.0.0.1:53124        127.0.0.1:8000         ESTABLISHED     502
  TCP    127.0.0.1:8000         127.0.0.1:53124        ESTABLISHED     46608
  TCP    [::1]:8001             [::]:0                 LISTENING       503
  UDP    0.0.0.0:8000           *:*                                    504
"""
SECOND_LISTENER = "  TCP    [::1]:8000             [::]:0                 LISTENING       777\n"
NETSTAT_CLOSED = NETSTAT.replace("LISTENING       46608", "CLOSED          46608")


class FakeClock:
    """``time`` for server_record: a wait advances the clock and is recorded, and nothing sleeps."""

    def __init__(self):
        self.now, self.slept = 1000.0, []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


class FakeSubprocess:
    """``subprocess`` for server_record: ``run`` returns the scripted output, or raises it."""

    TimeoutExpired = subprocess.TimeoutExpired

    def __init__(self, stdout):
        self.stdout, self.commands = stdout, []

    def run(self, command, **kwargs):
        self.commands.append(command)
        if isinstance(self.stdout, BaseException):
            raise self.stdout
        return type("Completed", (), {"stdout": self.stdout, "stderr": "", "returncode": 0})()


def owner(pid, states="0", command=WAITRESS_24):
    """A live owner of a remote-port-0 row, as ``_port_row_owners`` returns one. ``command`` is
    None for a process whose command line cannot be read."""
    return {"pid": pid, "command": command, "started_at": STARTED, "states": states}


def test_netstat_names_the_pid_listening_on_the_port_and_no_other(scripts):
    parse = scripts("server_record").parse_netstat_listening
    assert parse(NETSTAT, 8000) == {46608}          # not 18000 or 800, not the ESTABLISHED rows, not UDP
    assert parse(NETSTAT, 8001) == {503}            # IPv6
    assert parse(NETSTAT, 53124) == set()           # a client's port
    assert parse(NETSTAT_CLOSED, 8000) == set()
    assert parse(NETSTAT + SECOND_LISTENER, 8000) == {46608, 777}
    assert parse("", 8000) == set()


@pytest.mark.parametrize("stdout, pids, because", [
    (NETSTAT, {46608}, None),
    (NETSTAT + SECOND_LISTENER, {46608, 777}, None),
    (NETSTAT_CLOSED, set(), None),
    (FileNotFoundError("netstat"), set(), "netstat could not be run (FileNotFoundError)"),
], ids=["one process", "two processes", "none listening", "netstat missing"])
def test_netstat_gives_every_listening_pid_or_says_why_not(scripts, monkeypatch, stdout, pids, because):
    """Both of two processes are reported. Choosing between them is ``sole_owner``'s, and it never does."""
    server_record = scripts("server_record")
    monkeypatch.setattr(server_record, "subprocess", FakeSubprocess(stdout))
    found, why = server_record._netstat_listening_pids(8000)
    assert found == pids
    assert why is None if because is None else because in why


WAITRESS_ROW = {"pid": 46608, "command": WAITRESS_24, "started": STARTED, "states": "0"}
UNREADABLE_ROW = {"pid": 4, "command": "", "started": "2026-11-09T11:19:15.787Z", "states": "2"}


@pytest.mark.parametrize("stdout, owners, because", [
    (json.dumps([WAITRESS_ROW]), [(46608, WAITRESS_24)], None),
    (json.dumps(WAITRESS_ROW), [(46608, WAITRESS_24)], None),
    (json.dumps([WAITRESS_ROW, UNREADABLE_ROW]), [(46608, WAITRESS_24), (4, None)], None),
    (json.dumps([{**WAITRESS_ROW, "pid": 0}, WAITRESS_ROW]), [(46608, WAITRESS_24)], None),
    ("[]", [], None),
    ("", [], None),
    ("Get-CimInstance : Access denied", [], "could not be read"),
], ids=["one owner", "one owner, not in a list", "an owner nobody can read is still an owner",
        "process 0 is not an owner", "no owner", "no output", "not JSON"])
def test_the_ports_own_rows_give_every_live_owner(scripts, monkeypatch, stdout, owners, because):
    """Every live owner counts whatever state Windows reports for its row, and whether or not its
    command line can be read. Until 12 November 2026 an owner nobody could read was dropped here,
    so a second listener of that kind was passed over (the requirements audit of that day, B1)."""
    server_record = scripts("server_record")
    fake = FakeSubprocess(stdout)
    monkeypatch.setattr(server_record, "subprocess", fake)
    found, why = server_record._port_row_owners(8000)
    assert [(one["pid"], one["command"]) for one in found] == owners
    assert why is None if because is None else because in why
    if owners:
        assert (found[0]["started_at"], found[0]["states"]) == (STARTED, "0")
    # The command asks for the port's own rows in any state, and leaves out only what is not a
    # process: PID 0, and a row whose owner is gone. It does not ask for a readable command line.
    script = fake.commands[0][-1]
    assert "-Filter 'LocalPort=8000 AND RemotePort=0'" in script
    assert "if ($o -eq 0) { continue }" in script and "if (-not $p) { continue }" in script
    assert "$p.CommandLine)" not in script and "-le 4" not in script


@pytest.mark.parametrize("netstat, owners, taken, seen, because", [
    ({46608}, [owner(46608, "2")], 46608, True, "owned by pid 46608 alone"),
    (set(), [owner(46608)], 46608, True, "reported state 0 (2 is Listen)"),
    ({0}, [owner(84664)], 84664, True, "netstat -ano lists only PID 0 LISTENING, which is not a process"),
    (set(), [], None, False, "no live process owns a remote-port-0 row on port 8000"),
    ({0}, [], None, False, "no live process owns a remote-port-0 row on port 8000"),
    (set(), [owner(46608), owner(4, "2", None)], None, True, "more than one process holds port 8000: pids 4, 46608"),
    (set(), [owner(46608), owner(777)], None, True, "more than one process holds port 8000: pids 777, 46608"),
    ({777}, [owner(46608)], None, True, "more than one process holds port 8000: pids 777, 46608"),
    ({777}, [], None, True, "but it owns no remote-port-0 row on port 8000"),
    (set(), [owner(4321, "2", None)], None, True, "owned by pid 4321 alone, whose command line cannot be read"),
], ids=["netstat and the row agree", "the row alone, in state 0", "netstat names process 0 beside it",
        "nothing", "process 0 only", "a second owner nobody can read", "two readable owners",
        "netstat names another process", "netstat's process owns no row", "one owner nobody can read"])
def test_one_process_is_taken_only_when_it_alone_holds_the_port(scripts, netstat, owners, taken, seen, because):
    """A second process on the port, readable or not, means nothing is taken (D-87's note of 12
    November 2026). Process 0 is never a candidate."""
    found, why, candidate_seen = scripts("server_record").sole_owner(8000, netstat, None, owners, None)
    assert (found or {}).get("pid") == taken
    assert candidate_seen is seen and because in why


def test_nothing_is_taken_when_the_ports_rows_could_not_be_read(scripts):
    """netstat alone never names the listener: whether a second process holds the port is unknown."""
    sole_owner = scripts("server_record").sole_owner
    unread = "the port's socket rows could not be read (TimeoutExpired)"
    found, why, seen = sole_owner(8000, {46608}, None, [], unread)
    assert found is None and seen is True and why.endswith(unread)
    found, why, seen = sole_owner(8000, set(), "netstat could not be run (FileNotFoundError)", [], unread)
    assert found is None and seen is False and "netstat could not be run" in why


@pytest.fixture
def lookup(scripts, monkeypatch):
    """listening_process on Windows, with its lookups scripted and a clock that does not wait.

    ``script`` maps each lookup to its answers, one per try, the last one repeating. ``asked``
    counts how often each lookup was asked.
    """
    server_record = scripts("server_record")
    monkeypatch.setattr(sys, "platform", "win32")
    clock = FakeClock()
    monkeypatch.setattr(server_record, "time", clock)
    script = {"listen_row": [NOTHING_LISTENING], "netstat": [(set(), None)], "owners": [([], None)]}
    asked = {"listen_row": 0, "netstat": 0, "owners": 0}

    def answer(name):
        asked[name] += 1
        return script[name][min(asked[name], len(script[name])) - 1]

    monkeypatch.setattr(server_record, "_listen_row_process", lambda port: dict(answer("listen_row")))
    monkeypatch.setattr(server_record, "_netstat_listening_pids", lambda port: answer("netstat"))
    monkeypatch.setattr(server_record, "_port_row_owners", lambda port: answer("owners"))
    return server_record, script, asked, clock


@pytest.mark.parametrize("netstat", [({7}, None), ({0, 7}, None), (set(), None),
                                     (set(), "netstat could not be run (FileNotFoundError)")],
                         ids=["netstat lists it", "netstat lists it and process 0", "netstat lists nothing",
                              "netstat missing"])
def test_a_listen_row_is_taken_when_netstat_lists_no_other_listener(lookup, netstat):
    """The Listen row is taken at once, and the port's rows are not read, when netstat names no
    other process LISTENING on the port. Process 0 is not a process, and with netstat missing the
    row is taken as it was before these checks."""
    server_record, script, asked, clock = lookup
    script["listen_row"] = [{"pid": 7, "command": WAITRESS_24, "started_at": STARTED, "note": None}]
    script["netstat"] = [netstat]
    found = server_record.listening_process(8000)
    assert (found["pid"], found["command"], found["started_at"], found["note"]) == (7, WAITRESS_24, STARTED, None)
    assert found["found_by"] == server_record.FOUND_BY_LISTEN_ROW
    assert (asked["netstat"], asked["owners"], clock.slept) == (1, 0, [])
    if netstat[1]:
        assert "so no other listener could be looked for" in found["lookup"][-1]


def test_a_readable_listen_row_is_not_taken_while_netstat_lists_another_listener(lookup):
    """The trial of 12 November 2026, stage 2: two servers on one address and port. The Listen row
    names one, netstat lists both, and the port's rows show one. Nothing is taken, the process the
    Listen row named is not returned at the end, and the note says why."""
    server_record, script, asked, clock = lookup
    script["listen_row"] = [{"pid": 48404, "command": WAITRESS_24, "started_at": STARTED, "note": None}]
    script["netstat"] = [({42280, 48404}, None)]
    script["owners"] = [([owner(48404, "2")], None)]
    found = server_record.listening_process(8000)
    assert (found["pid"], found["command"], found["started_at"], found["found_by"]) == (None, None, None, None)
    assert found["note"].startswith("no single process with a readable command line holds port 8000")
    assert "more than one process holds port 8000: pids 42280, 48404" in found["note"]
    assert "netstat -ano lists pid 42280 LISTENING on port 8000 as well" in found["lookup"][-1]
    assert sum(clock.slept) == server_record.LOOKUP_RETRY_SECONDS
    # So the pre-flight refuses: no command line, so not Waitress.
    assert server_record.describe(found["command"])["server"] is None


def test_a_second_listener_that_goes_away_lets_the_listen_row_be_taken(lookup):
    """A second listener that is stopping: the retries see it gone, and the Listen row is taken."""
    server_record, script, asked, clock = lookup
    script["listen_row"] = [{"pid": 7, "command": WAITRESS_24, "started_at": STARTED, "note": None}]
    script["netstat"] = [({7, 9}, None), ({7}, None)]
    script["owners"] = [([owner(7, "2"), owner(9, "2")], None)]
    found = server_record.listening_process(8000)
    assert (found["pid"], found["found_by"]) == (7, server_record.FOUND_BY_LISTEN_ROW)
    assert clock.slept == [server_record.LOOKUP_RETRY_INTERVAL_SECONDS]


def test_a_listener_with_no_listen_row_is_found_when_netstat_and_its_row_agree(lookup):
    """The fault of 11 November 2026: the server answers, and its row is not in state Listen."""
    server_record, script, asked, clock = lookup
    script["netstat"] = [({46608}, None)]
    script["owners"] = [([owner(46608, "2")], None)]
    found = server_record.listening_process(8000)
    assert (found["pid"], found["command"], found["started_at"], found["note"]) == (46608, WAITRESS_24, STARTED, None)
    assert found["found_by"] == server_record.FOUND_BY_NETSTAT and clock.slept == []


def test_when_netstat_misreports_too_the_ports_own_row_names_the_process(lookup):
    """NFR-08's run 6: netstat showed the serving socket as CLOSED, and its own row named the PID."""
    server_record, script, asked, clock = lookup
    script["owners"] = [([owner(46608)], None)]
    found = server_record.listening_process(8000)
    assert (found["pid"], found["command"], found["started_at"], found["note"]) == (46608, WAITRESS_24, STARTED, None)
    assert found["found_by"] == server_record.FOUND_BY_PORT_ROW
    assert "reported state 0" in found["lookup"][-1] and clock.slept == []


def test_a_second_process_on_the_port_that_nobody_can_read_is_not_passed_over(lookup):
    """The audit's case (B1). The Listen row names a process whose command line cannot be read,
    and Waitress owns a row on the port too. The lookup merged on 11 November dropped the first
    and returned Waitress, so the pre-flight was READY. The Listen-row lookup alone had returned
    the unreadable process, and the pre-flight refused."""
    server_record, script, asked, clock = lookup
    script["listen_row"] = [{"pid": 4, "command": None, "started_at": "2026-11-09T11:19:15.787Z", "note": None}]
    script["owners"] = [([owner(46608), owner(4, "2", None)], None)]
    found = server_record.listening_process(8000)
    assert (found["pid"], found["command"], found["found_by"]) == (4, None, None)
    assert found["note"].startswith("no single process with a readable command line holds port 8000")
    assert "more than one process holds port 8000: pids 4, 46608" in found["note"]
    assert sum(clock.slept) == server_record.LOOKUP_RETRY_SECONDS
    # The pre-flight reads the server from the command line, and there is none: not Waitress.
    assert server_record.describe(found["command"])["server"] is None


def test_two_readable_listeners_are_never_reported_as_nothing_listening(lookup):
    """The audit's B4. The runbook asks this script whether the port is free, and "nothing is
    listening" would be the wrong answer in the unsafe direction."""
    server_record, script, asked, clock = lookup
    script["netstat"] = [({46608, 777}, None)]
    script["owners"] = [([owner(46608, "2"), owner(777, "2")], None)]
    found = server_record.listening_process(8000)
    assert (found["pid"], found["command"], found["found_by"]) == (None, None, None)
    assert "nothing is listening" not in found["note"]
    assert "more than one process holds port 8000: pids 777, 46608" in found["note"]


def test_the_lookup_is_tried_again_before_it_says_nothing_is_listening(lookup):
    server_record, script, asked, clock = lookup
    script["owners"] = [([], None), ([], None), ([owner(46608, "1")], None)]
    found = server_record.listening_process(8000)
    assert (found["pid"], found["found_by"]) == (46608, server_record.FOUND_BY_PORT_ROW)
    assert clock.slept == [server_record.LOOKUP_RETRY_INTERVAL_SECONDS] * 2
    assert asked == {"listen_row": 3, "netstat": 3, "owners": 3} and len(found["lookup"]) == 3


def test_nothing_listening_is_said_only_after_the_wait_and_in_the_same_words(lookup):
    server_record, script, asked, clock = lookup
    found = server_record.listening_process(8000)
    assert (found["pid"], found["command"], found["found_by"]) == (None, None, None)
    assert found["note"] == "nothing is listening on port 8000"
    assert set(clock.slept) == {server_record.LOOKUP_RETRY_INTERVAL_SECONDS}
    assert sum(clock.slept) == server_record.LOOKUP_RETRY_SECONDS
    assert "Giving up" in found["lookup"][-1]


def test_a_listen_row_and_a_netstat_line_naming_process_0_do_not_end_the_search(lookup):
    """Seen on 11 November 2026 with a listener answering on a scratch port: the Listen row and
    netstat both named PID 0, and the port's own row named the process, in state 0."""
    server_record, script, asked, clock = lookup
    script["listen_row"] = [PROCESS_0_ROW]
    script["netstat"] = [({0}, None)]
    script["owners"] = [([owner(84664)], None)]
    found = server_record.listening_process(8000)
    assert (found["pid"], found["command"], found["started_at"]) == (84664, WAITRESS_24, STARTED)
    assert found["found_by"] == server_record.FOUND_BY_PORT_ROW and clock.slept == []
    assert "names process 0" in found["lookup"][-1]


def test_only_rows_naming_process_0_are_reported_as_the_listen_row_reports_them(lookup):
    """A leftover row after a listener has gone. Process 0 is not a candidate, so nothing was
    seen, and the Listen row's own note is the answer, after the wait."""
    server_record, script, asked, clock = lookup
    script["listen_row"] = [PROCESS_0_ROW]
    script["netstat"] = [({0}, None)]
    found = server_record.listening_process(8000)
    assert (found["pid"], found["command"], found["found_by"]) == (None, None, None)
    assert found["note"] == PROCESS_0_ROW["note"]
    assert sum(clock.slept) == server_record.LOOKUP_RETRY_SECONDS and "Giving up" in found["lookup"][-1]


def test_a_process_nobody_can_read_is_returned_after_the_wait_with_a_note_that_says_so(lookup):
    """The answer the Listen row always gave, a PID with no command line. No lookup is credited
    with finding it, and the note says a process holds the port."""
    server_record, script, asked, clock = lookup
    script["listen_row"] = [{"pid": 4321, "command": None, "started_at": None, "note": None}]
    script["owners"] = [([owner(4321, "2", None)], None)]
    found = server_record.listening_process(8000)
    assert (found["pid"], found["command"], found["found_by"]) == (4321, None, None)
    assert "owned by pid 4321 alone, whose command line cannot be read" in found["note"]
    assert sum(clock.slept) == server_record.LOOKUP_RETRY_SECONDS


def test_off_windows_the_process_is_not_looked_up_and_nothing_waits(scripts, monkeypatch):
    server_record = scripts("server_record")
    monkeypatch.setattr(sys, "platform", "linux")
    clock = FakeClock()
    monkeypatch.setattr(server_record, "time", clock)

    def never(*args, **kwargs):
        raise AssertionError("no lookup runs off Windows")

    for name in ("_netstat_listening_pids", "_port_row_owners", "sole_owner"):
        monkeypatch.setattr(server_record, name, never)
    monkeypatch.setattr(server_record, "subprocess", FakeSubprocess(AssertionError("no command runs off Windows")))
    found = server_record.listening_process(8000)
    assert found["pid"] is None and found["note"] == "the listening process is only looked up on Windows"
    assert (found["found_by"], found["lookup"], clock.slept) == (None, [], [])


def test_the_record_says_which_lookup_found_the_process(scripts, monkeypatch):
    server_record = scripts("server_record")
    trace = ["try 1: nothing is listening on port 8000; the port's own row (remote port 0) is owned by pid 46608"]
    monkeypatch.setattr(server_record, "listening_process", lambda port: {
        "pid": 46608, "command": WAITRESS_24, "started_at": STARTED, "note": None,
        "found_by": server_record.FOUND_BY_PORT_ROW, "lookup": trace})
    record = server_record.observe("http://127.0.0.1:8000", "waitress", probe_debug=False)
    assert (record["pid"], record["server"], record["threads"]) == (46608, "waitress", 24)
    assert (record["process_found_by"], record["process_lookup"]) == (server_record.FOUND_BY_PORT_ROW, trace)
    # What is required of the process is unchanged: it is D-85's by its command line, however found.
    assert server_record.problems(record) == []


def test_the_closing_check_says_how_it_found_the_process(finalise, monkeypatch):
    server_record, state, run, _, summary, *_ = finalise
    monkeypatch.setattr(server_record, "listening_process", lambda port: {
        "pid": state["pid"], "command": WAITRESS_24, "started_at": STARTED, "note": None,
        "found_by": server_record.FOUND_BY_PORT_ROW, "lookup": ["try 1: the port's own row"]})
    run()
    report = json.loads(summary.read_text(encoding="utf-8"))
    at_end = report["server_at_end"]
    assert report["verdict"] == "PASS" and at_end["same_process"] is True
    assert (at_end["found_by"], at_end["lookup"]) == (server_record.FOUND_BY_PORT_ROW, ["try 1: the port's own row"])


def test_another_process_found_by_a_fallback_still_makes_the_run_invalid(finalise, monkeypatch):
    """D-87's rule is unchanged: the same PID before and after, however the lookup found it."""
    server_record, _, run, _, summary, *_ = finalise
    monkeypatch.setattr(server_record, "listening_process", lambda port: {
        "pid": 99, "command": WAITRESS_24, "started_at": STARTED, "note": None,
        "found_by": server_record.FOUND_BY_NETSTAT, "lookup": []})
    run()
    report = json.loads(summary.read_text(encoding="utf-8"))
    assert report["verdict"] == "INVALID RUN"
    assert any("(pid 99) is not the one observed before it (pid 7)" in r for r in report["invalid_reasons"])


def test_no_process_found_at_the_end_still_makes_the_run_invalid(finalise, monkeypatch):
    server_record, _, run, _, summary, *_ = finalise
    monkeypatch.setattr(server_record, "listening_process", lambda port: {**NOTHING_LISTENING, "found_by": None,
                                                                         "lookup": ["try 7: ... Giving up"]})
    run()
    report = json.loads(summary.read_text(encoding="utf-8"))
    assert report["verdict"] == "INVALID RUN"
    assert any("(nothing is listening on port 8000) is not the one observed before it (pid 7)" in r
               for r in report["invalid_reasons"])
