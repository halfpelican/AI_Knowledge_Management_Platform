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
