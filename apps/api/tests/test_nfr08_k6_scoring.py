"""NFR-08 counts a 503 as a miss, and a harness failure still invalidates the run (1 November 2026).

The rule since D-82's note of 1 November 2026:

- **A 503 is the system failing.** It is NFR-19's designed response, and so it is a result. It
  goes into the p90 sample ranked slower than any answered reply, because NFR-08 is an answer
  within 4 s for 90% of requests and a 503 got no answer. It is also counted on its own.
- **A 429, a k6 timeout or any other status is the harness failing,** and the run is INVALID.

These tests run the real ``tests/load/nfr08_query_p90.js`` under k6 against a stub of the two
routes it calls, at one VU, so the scoring is k6's own and not a reimplementation of it. The
stub answers each ask from a script. Each run takes about 30 to 45 s, set by the script's own
7 s floor between asks, and the three runs go in parallel. The tests are skipped where k6 is not
installed: the CI runner has no k6.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from django.conf import settings

NFR08_SCRIPT = Path(settings.BASE_DIR) / "tests" / "load" / "nfr08_query_p90.js"
WINDOWS_K6 = Path(r"C:\Program Files\k6\k6.exe")
K6 = shutil.which("k6") or (str(WINDOWS_K6) if WINDOWS_K6.exists() else None)

pytestmark = pytest.mark.skipif(K6 is None, reason="k6 is not installed (the CI runner has none)")

ANSWERED = (200, {"answered": True, "answer": "Twenty days.", "statements": [], "sources": []})
UNAVAILABLE = (503, {"detail": "The knowledge service is temporarily unavailable. Try again shortly."})
SERVER_ERROR = (500, {"detail": "A server error occurred."})
WARMUP = ANSWERED  # setup()'s two untimed asks come first


class _Stub(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, replies):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.replies = list(replies)
        self.lock = threading.Lock()


class _Handler(BaseHTTPRequestHandler):
    def version_string(self):
        return "waitress"  # observedServer() compares it with SERVER

    def log_message(self, *args):
        pass

    def _send(self, status, body, cookies=()):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        for cookie in cookies:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.path == "/api/auth/login":
            self._send(
                200,
                {"role": "Employee"},
                cookies=("csrftoken=stub-csrf; Path=/", "sessionid=stub-session; Path=/"),
            )
        elif self.path == "/api/ask":
            with self.server.lock:
                status, body = self.server.replies.pop(0)
            self._send(status, body)
        else:
            self._send(404, {"detail": "Not found."})


def _start_k6(tmp_path: Path, replies):
    """Start one k6 run of NFR-08 at one VU against a stub that answers ``replies`` in turn."""
    stub = _Stub(replies)
    threading.Thread(target=stub.serve_forever, daemon=True).start()
    (tmp_path / "tests" / "load" / "results").mkdir(parents=True)
    values = {
        "BASE_URL": f"http://127.0.0.1:{stub.server_address[1]}",
        "VUS": "1",
        "ITERATIONS": str(len(replies) - 2),
        "TEST_PASSWORD": "stub-password",
        "GIT_SHA": "0" * 40,
        "FLM_VERSION": "v0.9.39",
        "DB_DUMP_SHA256": "0" * 64,
        "SERVER": "waitress",
        "SERVER_VERSION": "3.0.2",
        "SERVER_THREADS": "24",
        "SERVER_OBSERVED_BY": "the test's stub",
        "SERVER_DEBUG": "off",
        "FLM_CHECK_PASSED_AT": "2026-11-01T00:00:00Z",
    }
    command = [K6, "run", "--quiet", "--address", "127.0.0.1:0"]
    for name, value in values.items():
        command += ["-e", f"{name}={value}"]
    command.append(str(NFR08_SCRIPT))
    process = subprocess.Popen(
        command,
        cwd=tmp_path,  # handleSummary writes tests/load/results/ relative to it
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={**os.environ, "K6_NO_USAGE_REPORT": "true"},
    )
    return stub, process, tmp_path / "tests" / "load" / "results" / "nfr08_summary.json"


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    """Three runs in parallel, each with its own stub: all answered, one 503, one 500."""
    scripts = {
        "answered": [WARMUP, WARMUP, ANSWERED, ANSWERED, ANSWERED],
        "with_503": [WARMUP, WARMUP, ANSWERED, UNAVAILABLE, ANSWERED, ANSWERED],
        "with_500": [WARMUP, WARMUP, ANSWERED, SERVER_ERROR],
    }
    started = {name: _start_k6(tmp_path_factory.mktemp(name), replies) for name, replies in scripts.items()}
    results = {}
    for name, (stub, process, summary) in started.items():
        output, _ = process.communicate(timeout=300)
        stub.shutdown()
        assert summary.exists(), f"k6 wrote no summary for {name}:\n{output.decode(errors='replace')}"
        results[name] = json.loads(summary.read_text(encoding="utf-8"))
    return results


def test_a_run_with_every_ask_answered_has_a_p90_in_milliseconds(runs):
    report = runs["answered"]
    assert report["run_valid"] is True, report["invalid_reasons"]
    assert report["verdict"] == "PASS"
    assert report["p90_falls_on_a_503"] is False
    assert report["p90_ms"] is not None and report["p90_ms"] < report["limit_ms"]
    assert report["p90_samples"] == 3
    assert report["server_503"] == 0


def test_a_503_is_a_result_counted_as_a_miss_slower_than_any_answer(runs):
    """One 503 in four asks: the run stays valid, and checks rate>0.99 and http_req_failed do
    not invalidate it. The 90th-percentile request is the 503, so the p90 has no time and the
    verdict is FAIL, although every answered reply came back in milliseconds."""
    report = runs["with_503"]
    assert report["run_valid"] is True, report["invalid_reasons"]
    assert report["invalid_reasons"] == []
    assert report["server_503"] == 1
    assert report["p90_samples"] == 4
    assert report["p90_falls_on_a_503"] is True
    assert report["p90_ms"] is None
    assert report["verdict"] == "FAIL"
    # Without the 503, as run 1 reported it: fast.
    assert report["p90_answered_ms"] < report["limit_ms"]
    assert report["answered_samples"] == 3


def test_any_other_status_is_a_harness_failure_and_the_run_is_invalid(runs):
    report = runs["with_500"]
    assert report["run_valid"] is False
    assert report["verdict"] == "INVALID RUN"
    assert report["unexpected_status"] == 1
    assert report["server_503"] == 0
    reasons = " | ".join(report["invalid_reasons"])
    assert "got neither a 200, nor the documented 503, nor a 429" in reasons
    assert "http_req_failed{name:ask} rate<0.01 was not met" in reasons
